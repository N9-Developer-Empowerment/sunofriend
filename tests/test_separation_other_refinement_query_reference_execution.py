from __future__ import annotations

import json
from pathlib import Path
import threading
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import wave

import numpy as np
import pytest
import torch

from sunofriend import separation_other_refinement_query_forward_adapter as forward_module
from sunofriend import separation_other_refinement_query_reference_report as report_module
from sunofriend.separation_other_refinement_query_forward_adapter import (
    BoundedBanquetReferenceForward,
)
from sunofriend.separation_other_refinement_query_reference_audio import (
    build_pcm24_accounting,
    read_pcm24,
    read_wav_window,
    write_pcm24,
)
from sunofriend.separation_other_refinement_query_reference_contract import (
    build_query_reference_input_contract,
    validate_query_reference_input_contract,
)
from sunofriend.separation_other_refinement_query_reference_plan import (
    build_query_reference_plan,
)
from sunofriend.separation_other_refinement_query_reference_report import (
    build_query_reference_report,
    build_query_reference_review_server,
    render_query_reference_review,
    validate_query_reference_report,
)


def _write_pcm16(path: Path, samples: np.ndarray, rate: int) -> None:
    values = np.rint(np.clip(samples, -1, 1 - 1 / 32768) * 32768).astype("<i2")
    with wave.open(str(path), "wb") as target:
        target.setnchannels(2)
        target.setsampwidth(2)
        target.setframerate(rate)
        target.writeframes(values.tobytes())


def test_reference_input_contract_binds_frozen_plan_and_six_files() -> None:
    value = validate_query_reference_input_contract(
        build_query_reference_input_contract()
    )
    assert value["plan_document_sha256"] == build_query_reference_plan()[
        "document_sha256"
    ]
    assert len(value["inputs"]) == 6
    assert {item["label"] for item in value["inputs"]} == {
        "query:guitar",
        "query:keyboard",
        "query:synth",
        "mixture:be-alone",
        "mixture:in-the-way",
        "mixture:tell-me-that-i-do-it-bitch",
    }
    assert all(item["kind"].endswith(("not_truth", "original_mixture")) for item in value["inputs"])


def test_reference_wav_decode_resamples_exact_window(tmp_path: Path) -> None:
    rate = 48_000
    times = np.arange(rate * 2, dtype=np.float32) / rate
    source = np.column_stack(
        (0.1 * np.sin(2 * np.pi * 220 * times), 0.1 * np.sin(2 * np.pi * 330 * times))
    )
    path = tmp_path / "source.wav"
    _write_pcm16(path, source, rate)
    value = read_wav_window(
        path,
        start_seconds=0.5,
        end_seconds=1.5,
        expected_frames=44_100,
    )
    assert value.shape == (1, 2, 44_100)
    assert value.dtype == torch.float32
    assert torch.isfinite(value).all()


def test_pcm24_accounting_is_exact_after_shared_attenuation(tmp_path: Path) -> None:
    mixture = torch.linspace(-0.9, 0.9, 200, dtype=torch.float32).reshape(1, 2, 100)
    target = mixture * 2.4
    result = build_pcm24_accounting(mixture, target)
    assert 0 < result["shared_attenuation"] < 1
    assert result["maximum_reconstruction_error_lsb"] == 0
    paths = {name: tmp_path / f"{name}.wav" for name in ("source", "target", "residual")}
    for name, path in paths.items():
        write_pcm24(path, result[name])
    error = np.max(
        np.abs(
            read_pcm24(paths["target"])
            + read_pcm24(paths["residual"])
            - read_pcm24(paths["source"])
        )
    )
    assert error == 0


def test_reference_forward_consumes_exactly_nine_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake(_model: object, mixture: torch.Tensor, query: torch.Tensor) -> torch.Tensor:
        calls.append((mixture.shape, query.shape))
        return mixture * 0.5

    monkeypatch.setattr(forward_module, "_source_pinned_forward", fake)
    runner = BoundedBanquetReferenceForward(object())  # type: ignore[arg-type]
    mixture = torch.zeros((1, 2, 10), dtype=torch.float32)
    query = torch.zeros((1, 2, 20), dtype=torch.float32)
    for _ in range(9):
        assert torch.equal(runner.run_next(mixture, query), mixture)
    assert runner.attempts == 9
    assert len(calls) == 9
    with pytest.raises(RuntimeError, match="limit is exhausted"):
        runner.run_next(mixture, query)


def _passing_report(root: Path) -> dict[str, object]:
    cases = []
    for track in ("one", "two", "three"):
        for target in ("guitar", "keyboard", "synth"):
            case_id = f"{track}--{target}"
            artifacts = {}
            for label in (
                "source_reference",
                "query_reference",
                "target",
                "residual",
            ):
                frames = 441_000 if label == "query_reference" else 661_500
                artifacts[label] = {
                    "relative_path": f"CASES/{case_id}/{label}.wav",
                    "bytes": frames * 6 + 44,
                    "sha256": "0" * 64,
                    "sample_rate_hz": 44_100,
                    "channels": 2,
                    "frames": frames,
                    "subtype": "PCM_24",
                }
            cases.append(
                {
                    "case_id": case_id,
                    "track_id": track,
                    "target_id": target,
                    "geometry": {"sample_rate_hz": 44_100, "channels": 2, "frames": 661_500},
                    "accounting": {
                        "finite": True,
                        "maximum_tensor_reconstruction_error": 0.0,
                        "maximum_reconstruction_error_lsb": 0,
                    },
                    "artifacts": artifacts,
                }
            )
    return build_query_reference_report(
        plan_sha256="a" * 64,
        input_contract_sha256="b" * 64,
        runtime={"device": "cpu"},
        model={"source_revision": "pinned"},
        cases=cases,
        guards={
            "network_attempts": 0,
            "restricted_torch_load_calls": 2,
        },
        elapsed_seconds=12.0,
        peak_resident_set_bytes=2_000_000_000,
    )


def test_reference_report_review_and_server_download_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = validate_query_reference_report(_passing_report(tmp_path))
    technical = tmp_path / "TECHNICAL"
    review = tmp_path / "REVIEW"
    technical.mkdir()
    review.mkdir()
    (technical / "REFERENCE-REPORT.json").write_text(json.dumps(report), encoding="utf-8")
    page = render_query_reference_review(report)
    (review / "review.html").write_text(page, encoding="utf-8")
    for case in report["cases"]:
        for artifact in case["artifacts"].values():
            path = tmp_path / artifact["relative_path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("wb") as handle:
                handle.truncate(artifact["bytes"])
    monkeypatch.setattr(report_module, "_file_sha256", lambda _path: "0" * 64)
    assert "/download-review" in page
    assert "Always-available JSON fallback" in page
    assert "provider query is an estimate" in page

    server = build_query_reference_review_server(tmp_path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with urlopen(f"http://127.0.0.1:{port}/healthz") as response:
            assert response.status == 200
        seed_start = page.index('<script id="seed" type="application/json">')
        seed_start = page.index(">", seed_start) + 1
        seed_end = page.index("</script>", seed_start)
        payload = page[seed_start:seed_end].replace("<\\/", "</")
        body = ("payload=" + quote_plus(payload)).encode()
        request = Request(
            f"http://127.0.0.1:{port}/download-review",
            data=body,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(request) as response:
            assert response.status == 200
            assert "attachment" in response.headers["Content-Disposition"]
            assert json.loads(response.read())["report_sha256"] == report["document_sha256"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_reference_runner_retains_authority_boundaries() -> None:
    source = Path("scripts/run-separation-other-refinement-query-reference.py").read_text(
        encoding="utf-8"
    )
    assert "--accept-approved-reference-canary" in source
    assert "BoundedBanquetReferenceForward" in source
    assert "forward.attempts != 9" in source
    assert "torch.use_deterministic_algorithms(True)" in source
    assert '"public_activation": False' in source
    assert '"source_selected": False' in source
    assert '"midi_created": False' in source
    assert "automatic_retry" in source
