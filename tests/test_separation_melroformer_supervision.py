from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import sunofriend._separation_melroformer_supervision as supervision
from sunofriend._separation_checkpoint_canonical import plain
from sunofriend.interface_contract import DIRECT_TUI_COMMANDS, PUBLIC_COMMANDS
from sunofriend.separation_contract import _canonical_json_bytes


def test_real_worker_supervision_is_path_free_and_frozen() -> None:
    evidence = supervision._build_real_worker_supervision_observation(
        worker_signal_state=supervision._expected_post_cpython_signal_state(),
        outer_open_descriptors=[0, 1, 2],
        child_returncode=0,
    )

    assert evidence["status"] == "real_worker_supervision_bound_complete"
    assert evidence["outer_supervisor"]["open_descriptors"] == (0, 1, 2)
    assert evidence["terminal"]["exact_child_reaped"] is True
    assert evidence["terminal"]["process_group_supervision_bound"] is False
    assert evidence["scope"]["product_authority_granted"] is False
    assert "/Users/" not in repr(evidence)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("signal", "post-CPython signal state differs"),
        ("descriptor", "inherited unexpected descriptors"),
        ("returncode", "did not exit normally"),
    ],
)
def test_real_worker_supervision_rejects_boundary_drift(
    mutation: str,
    message: str,
) -> None:
    signal_state = supervision._expected_post_cpython_signal_state()
    descriptors = [0, 1, 2]
    returncode = 0
    if mutation == "signal":
        signal_state["handlers"]["SIGTERM"] = "ignored"
    elif mutation == "descriptor":
        descriptors.append(9)
    else:
        returncode = -15

    with pytest.raises(ValueError, match=message):
        supervision._build_real_worker_supervision_observation(
            worker_signal_state=signal_state,
            outer_open_descriptors=descriptors,
            child_returncode=returncode,
        )


def test_real_worker_supervision_self_hash_rejects_tampering() -> None:
    evidence = plain(
        supervision._build_real_worker_supervision_observation(
            worker_signal_state=supervision._expected_post_cpython_signal_state(),
            outer_open_descriptors=[0, 1, 2],
            child_returncode=0,
        )
    )
    evidence["terminal"]["process_group_supervision_bound"] = True
    unsigned = dict(evidence)
    unsigned.pop("observation_sha256")
    evidence["observation_sha256"] = hashlib.sha256(
        _canonical_json_bytes(unsigned)
    ).hexdigest()

    with pytest.raises(ValueError, match="terminal evidence differs"):
        supervision._validate_real_worker_supervision_observation(evidence)


def test_real_worker_supervision_has_no_product_route() -> None:
    assert "private-melroformer-supervision" not in PUBLIC_COMMANDS
    assert "private-melroformer-supervision" not in DIRECT_TUI_COMMANDS


def test_real_worker_observes_signal_state_before_model_loading() -> None:
    worker = (
        Path(__file__).parents[1] / "scripts" / "private-melroformer-worker.py"
    ).read_text(encoding="utf-8")

    assert 'parser.add_argument("--bind-real-worker-supervision"' in worker
    assert worker.index("signal_state = (") < worker.index(
        "_load_private_melroformer_model("
    )
