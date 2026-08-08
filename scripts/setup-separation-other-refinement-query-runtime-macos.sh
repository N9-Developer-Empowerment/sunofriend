#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PLAN_SCRIPT="$REPOSITORY_ROOT/scripts/plan-separation-other-refinement-query-runtime.py"
INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-other-refinement-passt-checkpoint.py"
WHEEL_DOWNLOAD_SCRIPT="$REPOSITORY_ROOT/scripts/download-separation-other-refinement-query-runtime-wheels.py"
WHEEL_INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-other-refinement-query-runtime-wheels.py"
DATA_ROOT=${SUNOFRIEND_SEPARATION_ROOT:-"$HOME/.local/share/sunofriend/separation"}
EVIDENCE_ROOT=${SUNOFRIEND_PASST_EVIDENCE_ROOT:-"$DATA_ROOT/evidence/passt-openmic-v0.0.5"}
RUNTIME_WHEEL_EVIDENCE_ROOT=${SUNOFRIEND_QUERY_RUNTIME_WHEEL_EVIDENCE_ROOT:-"$DATA_ROOT/evidence/query-bandit-runtime-wheels-macos-arm64-py312-v1"}
ACTION=plan
ACCEPTED_TERMS=false
ACCEPTED_CHECKPOINT_USE=false
ACCEPTED_RUNTIME_WHEEL_EVIDENCE=false
EXPECTED_BYTES=341546630
MAX_BYTES=393216000
RUNTIME_WHEEL_CAP_BYTES=1073741824
CHECKPOINT_URL='https://github.com/kkoutini/PaSST/releases/download/v0.0.5/openmic-passt-s-f128-10sec-p16-s10-ap.85.pt'

usage() {
    echo "Usage: scripts/setup-separation-other-refinement-query-runtime-macos.sh [--plan | --passt-evidence-only --accept-passt-terms --accept-passt-checkpoint-use | --runtime-wheel-evidence-only --accept-runtime-wheel-evidence]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan) ACTION=plan ;;
        --passt-evidence-only) ACTION=passt-evidence-only ;;
        --runtime-wheel-evidence-only) ACTION=runtime-wheel-evidence-only ;;
        --accept-passt-terms) ACCEPTED_TERMS=true ;;
        --accept-passt-checkpoint-use) ACCEPTED_CHECKPOINT_USE=true ;;
        --accept-runtime-wheel-evidence) ACCEPTED_RUNTIME_WHEEL_EVIDENCE=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [ -x "$REPOSITORY_ROOT/.venv/bin/python" ]; then
    PLAN_PYTHON="$REPOSITORY_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PLAN_PYTHON=$(command -v python3)
else
    echo "Python 3 is required for the evidence-only inspector" >&2
    exit 2
fi

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    "$PLAN_PYTHON" -B "$PLAN_SCRIPT"
if [ "$ACTION" = plan ]; then
    echo ""
    echo "Plan only; nothing was downloaded, installed, loaded or executed."
    exit 0
fi

if [ "$ACTION" = runtime-wheel-evidence-only ]; then
    if [ "$ACCEPTED_RUNTIME_WHEEL_EVIDENCE" != true ]; then
        echo "--runtime-wheel-evidence-only requires --accept-runtime-wheel-evidence after reviewing the exact boundary" >&2
        exit 2
    fi
    if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
        echo "The approved runtime wheel evidence targets macOS on Apple silicon only" >&2
        exit 2
    fi
    if ! command -v sandbox-exec >/dev/null 2>&1; then
        echo "sandbox-exec is required for network-denied static inspection" >&2
        exit 2
    fi
    if command -v python3.12 >/dev/null 2>&1; then
        RUNTIME_WHEEL_PYTHON=$(command -v python3.12)
    else
        echo "Python 3.12 with pip is required to resolve the approved target closure" >&2
        exit 2
    fi
    if [ "$($RUNTIME_WHEEL_PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != 3.12 ]; then
        echo "Selected runtime wheel resolver must be Python 3.12: $RUNTIME_WHEEL_PYTHON" >&2
        exit 2
    fi
    if [ -e "$RUNTIME_WHEEL_EVIDENCE_ROOT" ] || [ -L "$RUNTIME_WHEEL_EVIDENCE_ROOT" ]; then
        echo "Refusing to overwrite existing runtime wheel evidence: $RUNTIME_WHEEL_EVIDENCE_ROOT" >&2
        exit 2
    fi
    RUNTIME_WHEEL_EVIDENCE_PARENT=$(dirname "$RUNTIME_WHEEL_EVIDENCE_ROOT")
    mkdir -p "$RUNTIME_WHEEL_EVIDENCE_PARENT"
    STAGING=$(mktemp -d "$RUNTIME_WHEEL_EVIDENCE_PARENT/.query-runtime-wheels.building.XXXXXX")
    preserve_failed_runtime_wheel_staging() {
        runtime_wheel_exit_code=$?
        if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
            failed_root="$RUNTIME_WHEEL_EVIDENCE_PARENT/query-bandit-runtime-wheels.failed.$$.evidence"
            if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
                chmod -R go-w "$STAGING" 2>/dev/null || true
                mv "$STAGING" "$failed_root"
                STAGING=
                echo "Preserved failed runtime wheel evidence staging: $failed_root" >&2
            fi
        fi
        exit "$runtime_wheel_exit_code"
    }
    trap preserve_failed_runtime_wheel_staging EXIT HUP INT TERM

    PYTHONDONTWRITEBYTECODE=1 "$PLAN_PYTHON" -B "$WHEEL_DOWNLOAD_SCRIPT" \
        --python "$RUNTIME_WHEEL_PYTHON" \
        --destination "$STAGING" \
        --cap-bytes "$RUNTIME_WHEEL_CAP_BYTES" \
        > "$STAGING/DOWNLOAD-REPORT.json"
    rmdir "$STAGING/tmp"
    PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
        sandbox-exec -p '(version 1)(allow default)(deny network*)' \
        "$PLAN_PYTHON" -B "$WHEEL_INSPECT_SCRIPT" "$STAGING/wheels" \
        > "$STAGING/STATIC-EVIDENCE.json"

    PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
        "$PLAN_PYTHON" -B - \
        "$STAGING/DOWNLOAD-REPORT.json" \
        "$STAGING/STATIC-EVIDENCE.json" \
        "$STAGING/HASHED-REQUIREMENTS.txt" \
        "$STAGING/APPROVAL-RECEIPT.json" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

from sunofriend.separation_other_refinement_runtime_wheel_evidence import (
    validate_runtime_wheel_evidence,
)

download_path = Path(sys.argv[1])
evidence_path = Path(sys.argv[2])
requirements_path = Path(sys.argv[3])
receipt_path = Path(sys.argv[4])
download = json.loads(download_path.read_text(encoding="utf-8"))
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
validate_runtime_wheel_evidence(evidence)
assert download["approved_cap_bytes"] == 1_073_741_824
assert download["peak_staged_bytes"] <= download["approved_cap_bytes"]
assert download["effects"]["dependency_installed"] is False
assert evidence["effects"]["dependency_installed"] is False
assert evidence["effects"]["model_packages_imported"] is False
assert evidence["effects"]["checkpoint_loaded"] is False
assert evidence["effects"]["model_constructed"] is False
assert evidence["effects"]["inference_runs"] == 0
assert evidence["effects"]["audio_reads"] == 0

requirements = "\n".join(
    [
        "# Sunofriend query challenger runtime wheel lock",
        "# Target: CPython 3.12, macOS 11+, arm64; evidence-only, not installed",
        "--only-binary=:all:",
        *evidence["hash_locked_requirements"],
        "",
    ]
)
requirements_path.write_text(requirements, encoding="utf-8")

def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

receipt = {
    "schema": "sunofriend.other-refinement-query-runtime-wheel-approval.v1",
    "status": "hash_locked_evidence_complete_no_runtime_authority",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "profile_id": "query-bandit-ev-pre-aug-v1",
    "approved_cap_bytes": download["approved_cap_bytes"],
    "peak_staged_bytes": download["peak_staged_bytes"],
    "wheel_bytes": evidence["wheel_bytes"],
    "package_count": evidence["package_count"],
    "download_report_sha256": file_sha256(download_path),
    "static_evidence_sha256": evidence["evidence_sha256"],
    "hashed_requirements_sha256": file_sha256(requirements_path),
    "approved_action": (
        "target-specific dependency artifact download, SHA-256 and "
        "non-importing wheel metadata and licence inspection"
    ),
    "static_inspection_network_denied": True,
    "dependency_installed": False,
    "packages_imported": False,
    "not_approved": [
        "dependency_installation",
        "importing_model_packages",
        "checkpoint_loading",
        "model_construction",
        "inference",
        "audio_processing",
        "public_activation",
        "source_selection",
        "midi",
    ],
}
receipt_path.write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

    staged_bytes=$(du -sk "$STAGING" | awk '{printf "%.0f", $1 * 1024}')
    if [ -z "$staged_bytes" ] || [ "$staged_bytes" -gt "$RUNTIME_WHEEL_CAP_BYTES" ]; then
        echo "Runtime wheel evidence exceeds the approved 1 GiB ceiling" >&2
        exit 2
    fi
    chmod 0444 "$STAGING"/*.json "$STAGING/HASHED-REQUIREMENTS.txt" "$STAGING/PIP-DOWNLOAD.log" "$STAGING"/wheels/*.whl
    chmod -R go-w "$STAGING"
    mv "$STAGING" "$RUNTIME_WHEEL_EVIDENCE_ROOT"
    STAGING=
    trap - EXIT HUP INT TERM

    echo ""
    echo "Evidence-only runtime wheel closure complete: $RUNTIME_WHEEL_EVIDENCE_ROOT"
    echo "The exact macOS-arm64/Python-3.12 wheels were hashed and inspected under network denial."
    echo "Nothing was installed, imported, loaded, constructed, inferred, activated, selected or sent to MIDI."
    exit 0
fi

if [ "$ACCEPTED_TERMS" != true ] || [ "$ACCEPTED_CHECKPOINT_USE" != true ]; then
    echo "--passt-evidence-only requires both acceptance flags after reviewing the plan" >&2
    exit 2
fi
for required_command in curl sandbox-exec; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        echo "$required_command is required" >&2
        exit 2
    fi
done
if [ -e "$EVIDENCE_ROOT" ] || [ -L "$EVIDENCE_ROOT" ]; then
    echo "Refusing to overwrite existing PaSST evidence: $EVIDENCE_ROOT" >&2
    exit 2
fi

EVIDENCE_PARENT=$(dirname "$EVIDENCE_ROOT")
mkdir -p "$EVIDENCE_PARENT"
STAGING=$(mktemp -d "$EVIDENCE_PARENT/.passt-openmic-v0.0.5.building.XXXXXX")
preserve_failed_staging() {
    passt_exit_code=$?
    if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
        failed_root="$EVIDENCE_PARENT/passt-openmic-v0.0.5.failed.$$.evidence"
        if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
            chmod -R go-w "$STAGING" 2>/dev/null || true
            mv "$STAGING" "$failed_root"
            STAGING=
            echo "Preserved failed PaSST evidence staging: $failed_root" >&2
        fi
    fi
    exit "$passt_exit_code"
}
trap preserve_failed_staging EXIT HUP INT TERM

CHECKPOINT="$STAGING/openmic-passt-s-f128-10sec-p16-s10-ap.85.pt"
(
    ulimit -f 768000
    curl --fail --location --retry 3 --silent --show-error \
        --proto '=https' --tlsv1.2 --max-filesize "$MAX_BYTES" \
        "$CHECKPOINT_URL" --output "$CHECKPOINT"
)
ACTUAL_BYTES=$(wc -c < "$CHECKPOINT" | tr -d ' ')
if [ "$ACTUAL_BYTES" != "$EXPECTED_BYTES" ]; then
    echo "OpenMIC PaSST checkpoint byte count differs: $ACTUAL_BYTES" >&2
    exit 2
fi
chmod 0444 "$CHECKPOINT"

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$PLAN_PYTHON" -B "$INSPECT_SCRIPT" "$CHECKPOINT" \
    > "$STAGING/STATIC-EVIDENCE.json"

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    "$PLAN_PYTHON" -B - "$STAGING/STATIC-EVIDENCE.json" "$STAGING/APPROVAL-RECEIPT.json" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sunofriend.separation_other_refinement_passt_evidence import (
    validate_passt_checkpoint_evidence,
)

evidence_path = Path(sys.argv[1])
receipt_path = Path(sys.argv[2])
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
validate_passt_checkpoint_evidence(evidence)
assert evidence["checkpoint"]["bytes"] == 341_546_630
assert evidence["effects"]["checkpoint_deserialized"] is False
assert evidence["effects"]["dependency_installed"] is False
assert evidence["effects"]["model_constructed"] is False
assert evidence["effects"]["inference_runs"] == 0
assert evidence["effects"]["audio_reads"] == 0
receipt = {
    "schema": "sunofriend.other-refinement-passt-evidence-approval.v1",
    "status": "evidence_only_complete_no_runtime_authority",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "profile_id": "query-bandit-ev-pre-aug-v1",
    "checkpoint_evidence_sha256": evidence["evidence_sha256"],
    "checkpoint_sha256": evidence["checkpoint"]["sha256"],
    "terms_acknowledged": [
        "PaSST Apache-2.0 code and release evidence",
        "OpenMIC-2018 CC-BY-4.0 training-dataset evidence",
        "Banquet remains local noncommercial research under CC-BY-NC-SA-4.0",
    ],
    "checkpoint_use_approved": "capped evidence-only download and static inspection",
    "network_denied_during_static_inspection": True,
    "not_approved": [
        "dependency_installation",
        "checkpoint_loading",
        "model_construction",
        "inference",
        "audio_processing",
        "public_activation",
        "source_selection",
        "midi",
    ],
}
receipt_path.write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

chmod 0444 "$STAGING/STATIC-EVIDENCE.json" "$STAGING/APPROVAL-RECEIPT.json"
chmod -R go-w "$STAGING"
mv "$STAGING" "$EVIDENCE_ROOT"
STAGING=
trap - EXIT HUP INT TERM

echo ""
echo "Evidence-only OpenMIC PaSST cache complete: $EVIDENCE_ROOT"
echo "The checkpoint was hashed and its ZIP/pickle structure inspected under network denial."
echo "Nothing was installed, loaded, inferred, activated, selected or sent to MIDI."
