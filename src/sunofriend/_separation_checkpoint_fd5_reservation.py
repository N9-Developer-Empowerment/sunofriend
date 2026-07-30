"""Pure records for one blocked checkpoint-FD5 lease reservation.

The reservation is parent-owned contract authority only.  It contains no
descriptor, path, lease, process or model operation and cannot install FD 5.
Live ownership and checkpoint remeasurement remain in the descriptor-lease
module under that lease's lock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ._separation_checkpoint_canonical import (
    canonical_sha256 as _hash,
    plain as _plain,
)
from ._separation_checkpoint_transport_records import (
    SeparationWorkerRequestV2Record,
    _validate_separation_worker_request_v2_record_shape,
)
from .separation_checkpoint_inspection import (
    SeparationCheckpointInspectionRequest,
)


_LOGICAL_REQUEST_FIELDS = (
    "preflight",
    "identities",
    "roles",
    "settings",
    "seed",
    "isolation",
)


class _CheckpointDescriptorFD5Reservation:
    """Zero-field, non-transferable authority for one blocked reservation."""

    __slots__ = ()

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError("checkpoint FD5 reservations are parent-issued only")

    def __init_subclass__(cls, **_kwargs: Any) -> None:
        raise TypeError("checkpoint FD5 reservations cannot be subclassed")

    def __repr__(self) -> str:
        return f"{type(self).__name__}()"

    def __copy__(self) -> Any:
        raise TypeError("checkpoint FD5 reservations cannot be copied")

    def __deepcopy__(self, _memo: Any) -> Any:
        raise TypeError("checkpoint FD5 reservations cannot be copied")

    def __reduce__(self) -> Any:
        raise TypeError("checkpoint FD5 reservations cannot be serialized")

    def __reduce_ex__(self, _protocol: int) -> Any:
        raise TypeError("checkpoint FD5 reservations cannot be serialized")


@dataclass(frozen=True)
class _FD5ReservationBinding:
    """Private exact-object binding retained only by the live lease state."""

    authority: _CheckpointDescriptorFD5Reservation
    worker_request_v2: SeparationWorkerRequestV2Record
    worker_request_v2_sha256: str
    inspection_request: SeparationCheckpointInspectionRequest
    lease_observation: Any
    lease_observation_sha256: str


def _new_fd5_reservation_binding(
    *,
    worker_request_v2: SeparationWorkerRequestV2Record,
    inspection_request: SeparationCheckpointInspectionRequest,
    lease_observation: Mapping[str, Any],
    expected_worker_request_v1: Mapping[str, Any],
    expected_inspection_request: SeparationCheckpointInspectionRequest,
    expected_inspection: Mapping[str, Any],
    expected_lease_observation: Mapping[str, Any],
) -> _FD5ReservationBinding:
    _validate_reservation_inputs(
        worker_request_v2=worker_request_v2,
        inspection_request=inspection_request,
        lease_observation=lease_observation,
        expected_worker_request_v1=expected_worker_request_v1,
        expected_inspection_request=expected_inspection_request,
        expected_inspection=expected_inspection,
        expected_lease_observation=expected_lease_observation,
    )
    authority = object.__new__(_CheckpointDescriptorFD5Reservation)
    return _FD5ReservationBinding(
        authority=authority,
        worker_request_v2=worker_request_v2,
        worker_request_v2_sha256=worker_request_v2["request_sha256"],
        inspection_request=inspection_request,
        lease_observation=lease_observation,
        lease_observation_sha256=lease_observation["observation_sha256"],
    )


def _validate_fd5_reservation_binding(
    binding: Any,
    *,
    expected_worker_request_v1: Mapping[str, Any],
    expected_inspection_request: SeparationCheckpointInspectionRequest,
    expected_inspection: Mapping[str, Any],
    expected_lease_observation: Mapping[str, Any],
) -> None:
    if type(binding) is not _FD5ReservationBinding:
        raise ValueError("checkpoint FD5 reservation binding is invalid")
    if (
        type(binding.authority) is not _CheckpointDescriptorFD5Reservation
        or binding.inspection_request is not expected_inspection_request
        or binding.worker_request_v2_sha256
        != binding.worker_request_v2["request_sha256"]
        or binding.lease_observation_sha256
        != expected_lease_observation["observation_sha256"]
    ):
        raise ValueError("checkpoint FD5 reservation authority changed")
    _validate_reservation_inputs(
        worker_request_v2=binding.worker_request_v2,
        inspection_request=binding.inspection_request,
        lease_observation=binding.lease_observation,
        expected_worker_request_v1=expected_worker_request_v1,
        expected_inspection_request=expected_inspection_request,
        expected_inspection=expected_inspection,
        expected_lease_observation=expected_lease_observation,
    )


def _require_fd5_reservation_authority(
    value: Any,
    binding: _FD5ReservationBinding,
) -> None:
    if (
        type(value) is not _CheckpointDescriptorFD5Reservation
        or value is not binding.authority
    ):
        raise ValueError(
            "checkpoint FD5 reservation must be the exact issued authority"
        )


def _validate_reservation_inputs(
    *,
    worker_request_v2: SeparationWorkerRequestV2Record,
    inspection_request: SeparationCheckpointInspectionRequest,
    lease_observation: Mapping[str, Any],
    expected_worker_request_v1: Mapping[str, Any],
    expected_inspection_request: SeparationCheckpointInspectionRequest,
    expected_inspection: Mapping[str, Any],
    expected_lease_observation: Mapping[str, Any],
) -> None:
    record = _validate_separation_worker_request_v2_record_shape(
        worker_request_v2
    )
    if inspection_request is not expected_inspection_request:
        raise ValueError("checkpoint inspection request was substituted")
    if (
        getattr(lease_observation, "_document", None)
        is not expected_lease_observation
    ):
        raise ValueError("checkpoint lease observation was substituted")
    if _hash(_plain(lease_observation)) != _hash(
        _plain(expected_lease_observation)
    ):
        raise ValueError("checkpoint lease observation is not current")

    request_v1 = _plain(expected_worker_request_v1)
    observation = _plain(expected_lease_observation)
    inspection = _plain(expected_inspection)
    bindings = _plain(record["bindings"])
    # Admission binding, runtime-artifact document and runtime-parent
    # measurements are deliberately absent here: the live lease does not own
    # those authorities.  Their exact values remain protected by the sealed
    # V2 record and its self-hash.
    expected_bindings = {
        "worker_request_sha256": request_v1["request_sha256"],
        "preflight_sha256": request_v1["preflight"]["preflight_sha256"],
        "acceptance_artifact_sha256": request_v1["preflight"]["bindings"][
            "acceptance_artifact_sha256"
        ],
        "separation_request_fingerprint_sha256": request_v1[
            "separation_request_fingerprint_sha256"
        ],
        "output_allowlist_sha256": _hash(request_v1["output_allowlist"]),
        "checkpoint_inspection_sha256": inspection["inspection_sha256"],
        "checkpoint_classification_evidence_sha256": inspection[
            "classification"
        ]["classification_evidence_sha256"],
        "lease_observation_sha256": observation["observation_sha256"],
        "checkpoint_sha256": observation["bindings"][
            "checkpoint_sha256"
        ],
        "checkpoint_bytes": observation["bindings"]["checkpoint_bytes"],
        "checkpoint_file_identity_sha256": observation["bindings"][
            "checkpoint_file_identity_sha256"
        ],
        "archive_evidence_sha256": observation["bindings"][
            "archive_evidence_sha256"
        ],
        "pickle_evidence_sha256": observation["bindings"][
            "pickle_evidence_sha256"
        ],
    }
    if any(bindings[key] != value for key, value in expected_bindings.items()):
        raise ValueError(
            "worker request v2 does not bind the live checkpoint lease"
        )

    logical_request = {
        key: request_v1[key] for key in _LOGICAL_REQUEST_FIELDS
    }
    if _hash(_plain(record["logical_request"])) != _hash(logical_request):
        raise ValueError(
            "worker request v2 logical projection does not match V1"
        )
