#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PLAN_SCRIPT="$REPOSITORY_ROOT/scripts/plan-separation-other-refinement-query-runtime.py"
INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-other-refinement-passt-checkpoint.py"
WHEEL_DOWNLOAD_SCRIPT="$REPOSITORY_ROOT/scripts/download-separation-other-refinement-query-runtime-wheels.py"
WHEEL_INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-other-refinement-query-runtime-wheels.py"
RUNTIME_IMPORT_SCRIPT="$REPOSITORY_ROOT/scripts/verify-separation-other-refinement-query-runtime-imports.py"
RUNTIME_REQUIREMENTS="$REPOSITORY_ROOT/separation-other-refinement-query-runtime-requirements.txt"
DATA_ROOT=${SUNOFRIEND_SEPARATION_ROOT:-"$HOME/.local/share/sunofriend/separation"}
EVIDENCE_ROOT=${SUNOFRIEND_PASST_EVIDENCE_ROOT:-"$DATA_ROOT/evidence/passt-openmic-v0.0.5"}
RUNTIME_WHEEL_EVIDENCE_ROOT=${SUNOFRIEND_QUERY_RUNTIME_WHEEL_EVIDENCE_ROOT:-"$DATA_ROOT/evidence/query-bandit-runtime-wheels-macos-arm64-py312-v1"}
RUNTIME_IMPORT_ROOT=${SUNOFRIEND_QUERY_RUNTIME_IMPORT_ROOT:-"$DATA_ROOT/evidence/query-bandit-runtime-import-macos-arm64-py312-v1"}
ACTION=plan
ACCEPTED_TERMS=false
ACCEPTED_CHECKPOINT_USE=false
ACCEPTED_RUNTIME_WHEEL_EVIDENCE=false
ACCEPTED_RUNTIME_INSTALL_AND_IMPORT=false
EXPECTED_BYTES=341546630
MAX_BYTES=393216000
RUNTIME_WHEEL_CAP_BYTES=1073741824
CHECKPOINT_URL='https://github.com/kkoutini/PaSST/releases/download/v0.0.5/openmic-passt-s-f128-10sec-p16-s10-ap.85.pt'

usage() {
    echo "Usage: scripts/setup-separation-other-refinement-query-runtime-macos.sh [--plan | --passt-evidence-only --accept-passt-terms --accept-passt-checkpoint-use | --runtime-wheel-evidence-only --accept-runtime-wheel-evidence | --install-runtime --accept-runtime-install-and-import]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan) ACTION=plan ;;
        --passt-evidence-only) ACTION=passt-evidence-only ;;
        --runtime-wheel-evidence-only) ACTION=runtime-wheel-evidence-only ;;
        --install-runtime) ACTION=install-runtime ;;
        --accept-passt-terms) ACCEPTED_TERMS=true ;;
        --accept-passt-checkpoint-use) ACCEPTED_CHECKPOINT_USE=true ;;
        --accept-runtime-wheel-evidence) ACCEPTED_RUNTIME_WHEEL_EVIDENCE=true ;;
        --accept-runtime-install-and-import) ACCEPTED_RUNTIME_INSTALL_AND_IMPORT=true ;;
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

if [ "$ACTION" = install-runtime ]; then
    if [ "$ACCEPTED_RUNTIME_INSTALL_AND_IMPORT" != true ]; then
        echo "--install-runtime requires --accept-runtime-install-and-import after reviewing the exact isolated boundary" >&2
        exit 2
    fi
    if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
        echo "The approved isolated runtime targets macOS on Apple silicon only" >&2
        exit 2
    fi
    for required_command in sandbox-exec shasum df cmp; do
        if ! command -v "$required_command" >/dev/null 2>&1; then
            echo "$required_command is required for isolated runtime verification" >&2
            exit 2
        fi
    done
    if command -v python3.12 >/dev/null 2>&1; then
        RUNTIME_IMPORT_PYTHON=$(command -v python3.12)
    else
        echo "Python 3.12 is required for the exact isolated runtime" >&2
        exit 2
    fi
    if [ "$($RUNTIME_IMPORT_PYTHON -c 'import platform, sys; print(f"{sys.version_info.major}.{sys.version_info.minor}:{platform.machine()}")')" != 3.12:arm64 ]; then
        echo "Selected isolated runtime Python must be CPython 3.12 on arm64: $RUNTIME_IMPORT_PYTHON" >&2
        exit 2
    fi
    if [ -e "$RUNTIME_IMPORT_ROOT" ] || [ -L "$RUNTIME_IMPORT_ROOT" ]; then
        echo "Refusing to overwrite existing isolated runtime evidence: $RUNTIME_IMPORT_ROOT" >&2
        exit 2
    fi
    for required_evidence in \
        "$RUNTIME_WHEEL_EVIDENCE_ROOT/STATIC-EVIDENCE.json" \
        "$RUNTIME_WHEEL_EVIDENCE_ROOT/APPROVAL-RECEIPT.json" \
        "$RUNTIME_WHEEL_EVIDENCE_ROOT/HASHED-REQUIREMENTS.txt" \
        "$RUNTIME_WHEEL_EVIDENCE_ROOT/wheels"; do
        if [ ! -e "$required_evidence" ] || [ -L "$required_evidence" ]; then
            echo "Approved runtime wheel evidence is incomplete: $required_evidence" >&2
            exit 2
        fi
    done
    echo "28249f5d6ab80d4b72a5f256ac435f3a2d150b1baa30d751754af44049c33b92  $RUNTIME_REQUIREMENTS" | shasum -a 256 -c - >/dev/null
    if ! cmp -s "$RUNTIME_REQUIREMENTS" "$RUNTIME_WHEEL_EVIDENCE_ROOT/HASHED-REQUIREMENTS.txt"; then
        echo "Committed runtime lock differs from the approved local wheel evidence" >&2
        exit 2
    fi
    echo "8943cde3676faf17ee1199a09f11494df53a9d6a2e4d5829ea68c8931d88bc37  $RUNTIME_WHEEL_EVIDENCE_ROOT/STATIC-EVIDENCE.json" | shasum -a 256 -c - >/dev/null
    PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
        "$PLAN_PYTHON" -B "$WHEEL_INSPECT_SCRIPT" \
        "$RUNTIME_WHEEL_EVIDENCE_ROOT/wheels" \
        > /dev/null

    RUNTIME_IMPORT_PARENT=$(dirname "$RUNTIME_IMPORT_ROOT")
    mkdir -p "$RUNTIME_IMPORT_PARENT"
    available_bytes=$(df -Pk "$RUNTIME_IMPORT_PARENT" | awk 'NR == 2 {printf "%.0f", $4 * 1024}')
    if [ -z "$available_bytes" ] || [ "$available_bytes" -lt 2147483648 ]; then
        echo "Isolated runtime setup requires at least 2147483648 free bytes before staging" >&2
        exit 2
    fi
    STAGING=$(mktemp -d "$RUNTIME_IMPORT_PARENT/.query-runtime-import.building.XXXXXX")
    preserve_failed_runtime_import_staging() {
        runtime_import_exit_code=$?
        if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
            failed_root="$RUNTIME_IMPORT_PARENT/query-bandit-runtime-import.failed.$$.evidence"
            if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
                chmod -R go-w "$STAGING" 2>/dev/null || true
                mv "$STAGING" "$failed_root"
                STAGING=
                echo "Preserved failed isolated runtime evidence: $failed_root" >&2
            fi
        fi
        exit "$runtime_import_exit_code"
    }
    trap preserve_failed_runtime_import_staging EXIT HUP INT TERM
    mkdir -p "$STAGING/home/cache" "$STAGING/home/torch"
    cp "$RUNTIME_REQUIREMENTS" "$STAGING/LOCKED-REQUIREMENTS.txt"
    chmod 0444 "$STAGING/LOCKED-REQUIREMENTS.txt"

    "$RUNTIME_IMPORT_PYTHON" -m venv "$STAGING/runtime"
    (
        ulimit -f 2097152
        HOME="$STAGING/home" XDG_CACHE_HOME="$STAGING/home/cache" \
        TORCH_HOME="$STAGING/home/torch" PYTHONNOUSERSITE=1 \
        PYTHONDONTWRITEBYTECODE=1 PIP_CONFIG_FILE=/dev/null \
        sandbox-exec -p '(version 1)(allow default)(deny network*)' \
        "$STAGING/runtime/bin/python" -m pip --isolated install \
            --disable-pip-version-check --no-cache-dir --no-index \
            --find-links "$RUNTIME_WHEEL_EVIDENCE_ROOT/wheels" \
            --only-binary=:all: --require-hashes \
            -r "$STAGING/LOCKED-REQUIREMENTS.txt"
    ) > "$STAGING/PIP-INSTALL.log" 2>&1

    HOME="$STAGING/home" XDG_CACHE_HOME="$STAGING/home/cache" \
    TORCH_HOME="$STAGING/home/torch" PYTHONNOUSERSITE=1 \
    PYTHONDONTWRITEBYTECODE=1 PIP_CONFIG_FILE=/dev/null \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$STAGING/runtime/bin/python" -m pip --isolated check \
        > "$STAGING/PIP-CHECK.log" 2>&1

    HOME="$STAGING/home" XDG_CACHE_HOME="$STAGING/home/cache" \
    TORCH_HOME="$STAGING/home/torch" HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$STAGING/runtime/bin/python" -I -B "$RUNTIME_IMPORT_SCRIPT" \
        --runtime-root "$STAGING/runtime" \
        --requirements "$STAGING/LOCKED-REQUIREMENTS.txt" \
        > "$STAGING/IMPORT-REPORT.json"

    PYTHONDONTWRITEBYTECODE=1 "$PLAN_PYTHON" -B - \
        "$STAGING/IMPORT-REPORT.json" \
        "$STAGING/APPROVAL-RECEIPT.json" \
        "$RUNTIME_IMPORT_ROOT" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

report_path = Path(sys.argv[1])
receipt_path = Path(sys.argv[2])
published_root = Path(sys.argv[3])
report = json.loads(report_path.read_text(encoding="utf-8"))
assert report["schema"] == "sunofriend.other-refinement-query-runtime-import-evidence.v1"
assert report["status"] == "isolated_hash_locked_runtime_imports_verified_network_denied"
assert report["locked_package_count"] == 28
assert len(report["locked_packages"]) == 28
assert report["runtime"]["implementation"] == "CPython"
assert report["runtime"]["python"].startswith("3.12.")
assert report["runtime"]["machine"] == "arm64"
assert report["runtime"]["virtual_environment"] is True
assert report["runtime"]["isolated_mode"] is True
assert report["runtime"]["user_site_enabled"] is False
assert set(report["bootstrap_packages"]) == {"pip"}
assert report["guards"] == {
    "audio_open_attempts": 0,
    "checkpoint_open_attempts": 0,
    "os_network_denial_required": True,
    "python_network_attempts": 0,
    "torch_load_calls": 0,
}
effects = report["effects"]
assert effects["dependency_installed"] is True
assert effects["checkpoint_loaded"] is False
assert effects["model_constructed"] is False
assert effects["inference_runs"] == 0
assert effects["audio_reads"] == 0
assert effects["audio_writes"] == 0
assert effects["public_activation"] is False
assert effects["source_selection"] is False
assert effects["midi_created"] is False

def document_sha256(value: dict) -> str:
    payload = {key: item for key, item in value.items() if key != "report_sha256"}
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()

assert report["report_sha256"] == document_sha256(report)
receipt = {
    "schema": "sunofriend.other-refinement-query-runtime-import-approval.v1",
    "status": "isolated_runtime_import_gate_complete_no_model_authority",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "profile_id": "query-bandit-ev-pre-aug-v1",
    "published_root": str(published_root),
    "runtime_requirements_sha256": "28249f5d6ab80d4b72a5f256ac435f3a2d150b1baa30d751754af44049c33b92",
    "wheel_static_evidence_file_sha256": "8943cde3676faf17ee1199a09f11494df53a9d6a2e4d5829ea68c8931d88bc37",
    "import_report_sha256": report["report_sha256"],
    "approved_action": (
        "install the exact 28-wheel hash-locked CPython 3.12 macOS-arm64 "
        "runtime into a fresh isolated environment and perform "
        "network-denied package-import verification only"
    ),
    "dependency_installed": True,
    "package_import_verified": True,
    "network_denied_during_install_and_import": True,
    "checkpoint_loaded": False,
    "model_constructed": False,
    "inference_performed": False,
    "audio_processed": False,
    "public_activation": False,
    "source_selection": False,
    "midi_created": False,
    "not_approved": [
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

    installed_bytes=$(du -sk "$STAGING" | awk '{printf "%.0f", $1 * 1024}')
    if [ -z "$installed_bytes" ] || [ "$installed_bytes" -gt 2147483648 ]; then
        echo "Isolated runtime staging exceeds the 2 GiB installation ceiling" >&2
        exit 2
    fi
    chmod 0444 "$STAGING"/*.json "$STAGING"/*.log
    chmod -R go-w "$STAGING"
    mv "$STAGING" "$RUNTIME_IMPORT_ROOT"
    STAGING=
    trap - EXIT HUP INT TERM

    echo ""
    echo "Isolated query runtime import gate complete: $RUNTIME_IMPORT_ROOT"
    echo "The exact 28-wheel runtime was installed from the approved local cache and imported under network denial."
    echo "No checkpoint was loaded, no model was constructed, no inference or audio ran, and nothing was activated, selected or sent to MIDI."
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
