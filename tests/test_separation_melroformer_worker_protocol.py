from __future__ import annotations

import pytest

from sunofriend._separation_melroformer_worker_protocol import (
    _build_private_melroformer_worker_protocol,
    _validate_private_melroformer_worker_protocol,
)


def _case(case_id: str, value: str = "a") -> dict[str, object]:
    frames = 441_000
    return {
        "case_id": case_id,
        "source_id": f"source-{case_id}",
        "source_sha256": value * 64,
        "canonical_sha256": chr(ord(value) + 1) * 64,
        "bytes": 2_646_044,
        "geometry": {
            "sample_rate": 44_100,
            "channels": 2,
            "bits_per_sample": 24,
            "frames": frames,
            "duration_seconds": 10.0,
        },
    }


def _plain(value: object) -> object:
    if isinstance(value, dict) or hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}  # type: ignore[union-attr]
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def test_builds_hash_bound_non_executable_two_output_protocol() -> None:
    first = _build_private_melroformer_worker_protocol(cases=[_case("case-a")])
    second = _build_private_melroformer_worker_protocol(cases=[_case("case-a")])

    assert first == second
    assert first["status"] == "protocol_defined_worker_absent"
    assert list(first["request_shape"]["roles"]) == ["vocals", "instrumental"]
    assert first["request_shape"]["upstream_from_pretrained_permitted"] is False
    assert first["request_shape"]["synthetic_adapter_contract_defined"] is True
    assert first["request_shape"]["real_adapter_implemented"] is False
    assert first["request_shape"][
        "post_sanitisation_model_key_coverage_required"
    ] is True
    assert first["result_shape"]["instrumental_equation"] == (
        "instrumental = mixture - vocals"
    )
    assert first["result_shape"][
        "mixture_reconstruction_within_pcm_tolerance_required"
    ] is True
    assert first["permissions"]["worker_start_permitted"] is False
    assert first["permissions"]["checkpoint_download_permitted"] is False
    assert first["effects"]["filesystem_accessed"] is False
    assert len(first["protocol_sha256"]) == 64


def test_accepts_two_sorted_distinct_cases() -> None:
    protocol = _build_private_melroformer_worker_protocol(
        cases=[_case("case-a", "a"), _case("case-b", "c")]
    )
    assert protocol["batch"]["case_count"] == 2
    assert protocol["batch"]["model_reuse_between_cases"] is False


@pytest.mark.parametrize(
    ("cases", "message"),
    [
        ([], "one or two"),
        ([_case("case-b", "a"), _case("case-a", "c")], "sorted and unique"),
        ([_case("case-a", "a"), _case("case-b", "a")], "distinct canonical"),
    ],
)
def test_rejects_invalid_case_sets(cases: list[dict[str, object]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        _build_private_melroformer_worker_protocol(cases=cases)


def test_rejects_geometry_and_size_outside_bounds() -> None:
    case = _case("case-a")
    case["geometry"]["sample_rate"] = 48_000  # type: ignore[index]
    with pytest.raises(ValueError, match="geometry differs"):
        _build_private_melroformer_worker_protocol(cases=[case])

    case = _case("case-a")
    case["bytes"] = True
    with pytest.raises(ValueError, match="bytes is invalid"):
        _build_private_melroformer_worker_protocol(cases=[case])


def test_rejects_tampered_protocol_and_hash() -> None:
    protocol = _plain(_build_private_melroformer_worker_protocol(cases=[_case("case-a")]))
    assert isinstance(protocol, dict)
    protocol["permissions"]["inference_permitted"] = True
    with pytest.raises(ValueError, match="differs from fixed policy"):
        _validate_private_melroformer_worker_protocol(protocol)

    protocol = _plain(_build_private_melroformer_worker_protocol(cases=[_case("case-a")]))
    assert isinstance(protocol, dict)
    protocol["protocol_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="hash is invalid"):
        _validate_private_melroformer_worker_protocol(protocol)
