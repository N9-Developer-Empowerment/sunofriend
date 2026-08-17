"""ACE-Step REST implementation of the song-generation backend contract."""

from __future__ import annotations

import json
import http.client
import time
import uuid
from pathlib import Path
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

from .song_generation import (
    BackendCandidate,
    BackendRun,
    SONG_GENERATION_BACKEND,
    SongGenerationPlan,
)


_HTTP_REQUEST_TIMEOUT_SECONDS = 60.0
_AUDIO_DOWNLOAD_TIMEOUT_SECONDS = 600.0
_MAXIMUM_CANDIDATE_BYTES = 4 * 1024 * 1024 * 1024


class AceStepApiBackend:
    """Generate two songs through an existing ACE-Step asynchronous API server."""

    backend_id = SONG_GENERATION_BACKEND

    def __init__(self, *, api_token: str | None = None) -> None:
        token = str(api_token).strip() if api_token is not None else None
        self._api_token = token or None

    def request_payload(self, plan: SongGenerationPlan) -> dict[str, Any]:
        """Map the neutral request onto documented ACE-Step parameters."""

        mapping = plan.backend_configuration["strength_mapping"]
        payload = {
            "prompt": plan.style_description,
            "lyrics": plan.lyrics,
            "thinking": True,
            "vocal_language": plan.vocal_language,
            "audio_format": plan.output_format,
            "model": plan.backend_configuration["model"],
            "inference_steps": plan.backend_configuration["inference_steps"],
            "batch_size": plan.candidate_count,
            "task_type": "text2music",
            "reference_audio_path": str(plan.reference),
            "audio_cover_strength": mapping["reference_strength"]["value"],
            "guidance_scale": mapping["style_description_strength"]["value"],
            "use_random_seed": plan.seed is None,
            "seed": -1 if plan.seed is None else plan.seed,
            "use_cot_caption": False,
            "use_cot_language": True,
            "constrained_decoding": True,
        }
        optional_metadata = {
            "bpm": plan.bpm,
            "key_scale": plan.key,
            "time_signature": plan.time_signature,
            "audio_duration": plan.duration_seconds,
        }
        payload.update(
            {
                parameter: value
                for parameter, value in optional_metadata.items()
                if value is not None
            }
        )
        return payload

    def generate(self, plan: SongGenerationPlan, root: Path) -> BackendRun:
        base_url = str(plan.backend_configuration["api_base_url"])
        model_inventory = self._json_request(base_url, "GET", "/v1/models")
        self._require_model(model_inventory, str(plan.backend_configuration["model"]))
        payload = self.request_payload(plan)
        submitted = self._multipart_json_request(
            base_url,
            "/release_task",
            fields={
                key: value
                for key, value in payload.items()
                if key != "reference_audio_path"
            },
            file_field="reference_audio",
            file_path=plan.reference,
        )
        submission_data = _response_data(submitted, "ACE-Step task submission")
        if not isinstance(submission_data, Mapping):
            raise RuntimeError("ACE-Step task submission returned invalid data")
        task_id = str(submission_data.get("task_id", "")).strip()
        if not task_id:
            raise RuntimeError("ACE-Step task submission omitted task_id")
        records, terminal = self._wait_for_result(plan, base_url, task_id)
        if len(records) != plan.candidate_count:
            raise RuntimeError(
                f"ACE-Step returned {len(records)} successful audio records; "
                f"expected {plan.candidate_count}"
            )
        self._require_candidate_models(
            records,
            str(plan.backend_configuration["model"]),
        )
        candidates_dir = root / "candidates"
        candidates_dir.mkdir(parents=True, exist_ok=False)
        candidates: list[BackendCandidate] = []
        for index, record in enumerate(records, start=1):
            file_url = str(record.get("file", "")).strip()
            if not file_url:
                raise RuntimeError(f"ACE-Step candidate {index} omitted its audio URL")
            destination = candidates_dir / (
                f"candidate-{index:02d}.{_output_suffix(plan.output_format)}"
            )
            self._download(base_url, file_url, destination)
            candidates.append(
                BackendCandidate(
                    path=destination,
                    metadata=_candidate_metadata(record),
                )
            )
        seed_values = [
            candidate.metadata.get("seed_value")
            for candidate in candidates
            if candidate.metadata.get("seed_value") not in {None, ""}
        ]
        request_mapping = {
            "api": "ACE-Step /release_task",
            "transport": "multipart_file_upload",
            "parameters": {
                key: value
                for key, value in payload.items()
                if key not in {"reference_audio_path", "lyrics", "prompt"}
            },
            "reference": {
                "name": plan.reference.name,
                "sha256": plan.reference_sha256,
            },
            "prompt_source": "request.style_description",
            "lyrics_source": "request.annotated_lyrics.text",
        }
        execution_evidence = {
            "task_id": task_id,
            "model_inventory": _sanitise_model_inventory(model_inventory),
            "terminal_status": terminal.get("status"),
            "seed_values": seed_values,
        }
        return BackendRun(
            backend_id=self.backend_id,
            candidates=tuple(candidates),
            request_mapping=request_mapping,
            execution_evidence=execution_evidence,
            exact_reproduction_available=bool(seed_values),
        )

    def _wait_for_result(
        self, plan: SongGenerationPlan, base_url: str, task_id: str
    ) -> tuple[list[Mapping[str, Any]], Mapping[str, Any]]:
        deadline = time.monotonic() + float(
            plan.backend_configuration["timeout_seconds"]
        )
        poll_seconds = float(plan.backend_configuration["poll_seconds"])
        while True:
            response = self._json_request(
                base_url,
                "POST",
                "/query_result",
                payload={"task_id_list": [task_id]},
            )
            data = _response_data(response, "ACE-Step task query")
            if not isinstance(data, list) or len(data) != 1:
                raise RuntimeError("ACE-Step task query returned an invalid task list")
            terminal = data[0]
            if not isinstance(terminal, Mapping):
                raise RuntimeError("ACE-Step task query returned an invalid task record")
            status = terminal.get("status")
            if status in {1, "1", "succeeded", "success"}:
                return _result_records(terminal.get("result")), terminal
            if status in {2, "2", "failed", "failure"}:
                message = terminal.get("error") or terminal.get("status_message")
                raise RuntimeError(f"ACE-Step generation failed: {message or 'unknown error'}")
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "ACE-Step generation did not complete before timeout_seconds"
                )
            time.sleep(poll_seconds)

    def _require_model(self, response: Mapping[str, Any], expected: str) -> None:
        models = _model_inventory_records(response)
        if not models and _is_lazy_openai_inventory(response):
            return
        aliases = {
            alias
            for item in models
            for alias in _model_aliases(item)
        }
        if expected.casefold() not in aliases:
            available = ", ".join(_model_inventory_labels(models)) or "<none>"
            raise RuntimeError(
                f"ACE-Step model {expected!r} is not available; server reports: "
                f"{available}"
            )

    def _require_candidate_models(
        self,
        records: list[Mapping[str, Any]],
        expected: str,
    ) -> None:
        """Reject silent server-side checkpoint substitution in task results."""

        expected_name = _checkpoint_name(expected)
        reported = [
            _checkpoint_name(str(record.get("dit_model", "")))
            for record in records
        ]
        if any(not model for model in reported):
            raise RuntimeError(
                "ACE-Step candidate metadata omitted dit_model; requested checkpoint "
                f"{expected!r} cannot be verified"
            )
        mismatched = sorted({model for model in reported if model != expected_name})
        if mismatched:
            raise RuntimeError(
                f"ACE-Step substituted checkpoint(s) {', '.join(mismatched)!r}; "
                f"requested {expected_name!r}"
            )

    def _json_request(
        self,
        base_url: str,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode(
                "utf-8"
            )
            headers["Content-Type"] = "application/json"
        if self._api_token is not None:
            headers["Authorization"] = f"Bearer {self._api_token}"
        request = Request(
            urljoin(base_url + "/", path.lstrip("/")),
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=_HTTP_REQUEST_TIMEOUT_SECONDS) as response:
                body = response.read(16 * 1024 * 1024 + 1)
        except HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", errors="replace")
            raise RuntimeError(
                f"ACE-Step API returned HTTP {exc.code}: {detail}"
            ) from exc
        except (URLError, OSError) as exc:
            raise RuntimeError(f"ACE-Step API is unavailable: {exc}") from exc
        if len(body) > 16 * 1024 * 1024:
            raise RuntimeError("ACE-Step API JSON response exceeded the safety limit")
        try:
            document = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("ACE-Step API returned invalid UTF-8 JSON") from exc
        if not isinstance(document, Mapping):
            raise RuntimeError("ACE-Step API returned a non-object response")
        return document

    def _multipart_json_request(
        self,
        base_url: str,
        path: str,
        *,
        fields: Mapping[str, Any],
        file_field: str,
        file_path: Path,
    ) -> Mapping[str, Any]:
        """Stream one local audio file through ACE-Step multipart upload."""

        boundary = f"sunofriend-{uuid.uuid4().hex}"
        field_parts = [
            _multipart_field(boundary, key, value)
            for key, value in fields.items()
            if value is not None
        ]
        file_header = _multipart_file_header(
            boundary,
            field=file_field,
            filename=file_path.name,
        )
        closing = f"\r\n--{boundary}--\r\n".encode("ascii")
        content_length = (
            sum(len(part) for part in field_parts)
            + len(file_header)
            + file_path.stat().st_size
            + len(closing)
        )
        url = urlsplit(urljoin(base_url + "/", path.lstrip("/")))
        connection_type = (
            http.client.HTTPSConnection
            if url.scheme.casefold() == "https"
            else http.client.HTTPConnection
        )
        connection = connection_type(
            url.hostname,
            url.port,
            timeout=_AUDIO_DOWNLOAD_TIMEOUT_SECONDS,
        )
        request_path = url.path or "/"
        if url.query:
            request_path = f"{request_path}?{url.query}"
        try:
            connection.putrequest("POST", request_path)
            connection.putheader("Accept", "application/json")
            connection.putheader(
                "Content-Type", f"multipart/form-data; boundary={boundary}"
            )
            connection.putheader("Content-Length", str(content_length))
            if self._api_token is not None:
                connection.putheader("Authorization", f"Bearer {self._api_token}")
            connection.endheaders()
            for part in field_parts:
                connection.send(part)
            connection.send(file_header)
            with file_path.open("rb") as handle:
                while True:
                    block = handle.read(1024 * 1024)
                    if not block:
                        break
                    connection.send(block)
            connection.send(closing)
            response = connection.getresponse()
            body = response.read(16 * 1024 * 1024 + 1)
            if response.status >= 400:
                detail = body[:4096].decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"ACE-Step API returned HTTP {response.status}: {detail}"
                )
        except (OSError, http.client.HTTPException) as exc:
            raise RuntimeError(f"ACE-Step API is unavailable: {exc}") from exc
        finally:
            connection.close()
        if len(body) > 16 * 1024 * 1024:
            raise RuntimeError("ACE-Step API JSON response exceeded the safety limit")
        try:
            document = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("ACE-Step API returned invalid UTF-8 JSON") from exc
        if not isinstance(document, Mapping):
            raise RuntimeError("ACE-Step API returned a non-object response")
        return document

    def _download(self, base_url: str, value: str, destination: Path) -> None:
        url = urljoin(base_url + "/", value)
        if _origin(url) != _origin(base_url):
            raise RuntimeError("ACE-Step candidate URL escaped the configured API origin")
        headers = {"Accept": "audio/*"}
        if self._api_token is not None:
            headers["Authorization"] = f"Bearer {self._api_token}"
        request = Request(url, headers=headers, method="GET")
        try:
            with urlopen(request, timeout=_AUDIO_DOWNLOAD_TIMEOUT_SECONDS) as response:
                content_length = response.headers.get("Content-Length")
                if content_length is not None and int(content_length) > _MAXIMUM_CANDIDATE_BYTES:
                    raise RuntimeError("ACE-Step candidate exceeds the download limit")
                total = 0
                with destination.open("xb") as handle:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        total += len(block)
                        if total > _MAXIMUM_CANDIDATE_BYTES:
                            raise RuntimeError("ACE-Step candidate exceeds the download limit")
                        handle.write(block)
        except HTTPError as exc:
            raise RuntimeError(
                f"ACE-Step candidate download returned HTTP {exc.code}"
            ) from exc
        except (URLError, OSError) as exc:
            raise RuntimeError(f"ACE-Step candidate download failed: {exc}") from exc
        if not destination.is_file() or destination.stat().st_size <= 0:
            raise RuntimeError("ACE-Step candidate download was empty")


def _response_data(response: Mapping[str, Any], label: str) -> Any:
    code = response.get("code")
    if code not in {None, 200, "200"}:
        raise RuntimeError(f"{label} failed: {response.get('error') or code}")
    if response.get("error") not in {None, ""}:
        raise RuntimeError(f"{label} failed: {response['error']}")
    return response.get("data")


def _multipart_field(boundary: str, name: str, value: Any) -> bytes:
    rendered = _multipart_value(value)
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
        f"{rendered}\r\n"
    ).encode("utf-8")


def _multipart_file_header(
    boundary: str,
    *,
    field: str,
    filename: str,
) -> bytes:
    safe_name = filename.replace("\\", "_").replace('"', "_")
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; '
        f'filename="{safe_name}"\r\n'
        "Content-Type: audio/wav\r\n\r\n"
    ).encode("utf-8")


def _multipart_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _result_records(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuntimeError("ACE-Step task result contained invalid JSON") from exc
    if not isinstance(value, list):
        raise RuntimeError("ACE-Step task result was not a candidate list")
    records = [item for item in value if isinstance(item, Mapping)]
    successful = [
        item
        for item in records
        if item.get("status") in {None, 1, "1", "succeeded", "success"}
        and item.get("file")
    ]
    return successful


def _candidate_metadata(record: Mapping[str, Any]) -> dict[str, Any]:
    allowed = (
        "status",
        "create_time",
        "env",
        "metas",
        "generation_info",
        "seed_value",
        "lm_model",
        "dit_model",
    )
    return {key: record[key] for key in allowed if key in record}


def _sanitise_model_inventory(response: Mapping[str, Any]) -> dict[str, Any]:
    models = _model_inventory_records(response)
    records = [
        {
            key: item[key]
            for key in ("id", "name", "is_default", "is_loaded")
            if key in item
        }
        for item in models
    ]
    data = response.get("data")
    return {
        "models": records,
        "default_model": (
            data.get("default_model") if isinstance(data, Mapping) else None
        ),
        "inventory_format": (
            "openai-list" if isinstance(data, list) else "ace-step-wrapped"
        ),
    }


def _model_inventory_records(response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    data = _response_data(response, "ACE-Step model inventory")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, Mapping)]
    if isinstance(data, Mapping) and isinstance(data.get("models"), list):
        return [item for item in data["models"] if isinstance(item, Mapping)]
    raise RuntimeError("ACE-Step model inventory returned invalid data")


def _is_lazy_openai_inventory(response: Mapping[str, Any]) -> bool:
    """Recognise the empty model list returned before current ACE-Step lazy init."""

    return response.get("object") == "list" and response.get("data") == []


def _model_aliases(item: Mapping[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for key in ("id", "name"):
        value = str(item.get(key, "")).strip()
        if not value:
            continue
        aliases.add(value.casefold())
        aliases.add(value.rsplit("/", 1)[-1].casefold())
        if value.casefold().startswith("ace-step "):
            aliases.add(value[len("ACE-Step ") :].casefold())
    return aliases


def _model_inventory_labels(models: list[Mapping[str, Any]]) -> list[str]:
    labels = {
        str(item.get("id") or item.get("name")).strip()
        for item in models
        if item.get("id") or item.get("name")
    }
    return sorted(labels)


def _checkpoint_name(value: str) -> str:
    """Return a case-insensitive checkpoint basename for result comparison."""

    return value.strip().replace("\\", "/").rsplit("/", 1)[-1].casefold()


def _origin(value: str) -> tuple[str, str, int | None]:
    parsed = urlsplit(value)
    return parsed.scheme.casefold(), (parsed.hostname or "").casefold(), parsed.port


def _output_suffix(value: str) -> str:
    return "wav" if value == "wav32" else value


__all__ = ["AceStepApiBackend"]
