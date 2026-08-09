#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PLAN_SCRIPT="$REPOSITORY_ROOT/scripts/plan-separation-other-refinement-next-challenger.py"
INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-other-refinement-next-challenger-artifacts.py"
WHEEL_DOWNLOAD_SCRIPT="$REPOSITORY_ROOT/scripts/download-separation-other-refinement-next-runtime-wheels.py"
WHEEL_INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-other-refinement-next-runtime-wheels.py"
RUNTIME_IMPORT_SCRIPT="$REPOSITORY_ROOT/scripts/verify-separation-other-refinement-next-runtime-imports.py"
SOURCE_INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-other-refinement-next-source.py"
MODEL_LOAD_SCRIPT="$REPOSITORY_ROOT/scripts/verify-separation-other-refinement-next-model-load.py"
MODEL_LOAD_RECEIPT_SCRIPT="$REPOSITORY_ROOT/scripts/record-separation-other-refinement-next-model-load.py"
RUNTIME_REQUIREMENTS="$REPOSITORY_ROOT/separation-other-refinement-next-runtime-requirements.txt"
DATA_ROOT=${SUNOFRIEND_SEPARATION_ROOT:-"$HOME/.local/share/sunofriend/separation"}
EVIDENCE_ROOT=${SUNOFRIEND_MEGA53_EVIDENCE_ROOT:-"$DATA_ROOT/evidence/bs-roformer-mega-53-synth-v1"}
RUNTIME_WHEEL_EVIDENCE_ROOT=${SUNOFRIEND_MEGA53_RUNTIME_WHEEL_EVIDENCE_ROOT:-"$DATA_ROOT/evidence/bs-roformer-mega-53-runtime-wheels-macos-arm64-py312-v1"}
RUNTIME_IMPORT_ROOT=${SUNOFRIEND_MEGA53_RUNTIME_IMPORT_ROOT:-"$DATA_ROOT/evidence/bs-roformer-mega-53-runtime-import-macos-arm64-py312-v1"}
SOURCE_EVIDENCE_ROOT=${SUNOFRIEND_MEGA53_SOURCE_EVIDENCE_ROOT:-"$DATA_ROOT/evidence/bs-roformer-infer-de35ada-source-v1"}
MODEL_LOAD_ROOT=${SUNOFRIEND_MEGA53_MODEL_LOAD_ROOT:-"$DATA_ROOT/evidence/bs-roformer-mega-53-model-load-v1"}
ACTION=plan
ACCEPTED_PROVISIONAL_TERMS=false
ACCEPTED_CHECKPOINT_USE=false
ACCEPTED_RUNTIME_WHEEL_EVIDENCE=false
ACCEPTED_RUNTIME_INSTALL_AND_IMPORT=false
ACCEPTED_SOURCE_EVIDENCE=false
ACCEPTED_RESTRICTED_MODEL_LOAD=false
CHECKPOINT_FILE=mvsep_mega_model_bs_roformer_53_stems_v1.ckpt
CHECKPOINT_BYTES=1368919887
CHECKPOINT_SHA256=c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f
CHECKPOINT_URL='https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt'
CONFIG_FILE=mvsep_mega_model_bs_roformer_53_stems.yaml
CONFIG_BYTES=4184
CONFIG_SHA256=7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103
CONFIG_URL='https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21/mvsep_mega_model_bs_roformer_53_stems.yaml'
EXPECTED_TOTAL_BYTES=1368924071
MAX_DOWNLOAD_BYTES=1610612736
RUNTIME_WHEEL_CAP_BYTES=1610612736
RUNTIME_REQUIREMENTS_SHA256=284d198c43e9074a4d645f005d937dd4e93b99e22aa21d942caaa1822b13d10b
SOURCE_REVISION=de35ada5817b878da0194ee2860253dda3a9c2b2
SOURCE_URL="https://github.com/openmirlab/bs-roformer-infer/archive/$SOURCE_REVISION.tar.gz"
SOURCE_CAP_BYTES=33554432

usage() {
    echo "Usage: scripts/setup-separation-other-refinement-next-challenger-macos.sh [--plan | --evidence-only --accept-provisional-local-noncommercial-terms --accept-checkpoint-use | --runtime-wheel-evidence-only --accept-runtime-wheel-evidence | --install-runtime --accept-runtime-install-and-import | --source-evidence-only --accept-source-evidence | --construct-and-load-model --accept-restricted-model-load]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan) ACTION=plan ;;
        --evidence-only) ACTION=evidence-only ;;
        --runtime-wheel-evidence-only) ACTION=runtime-wheel-evidence-only ;;
        --install-runtime) ACTION=install-runtime ;;
        --source-evidence-only) ACTION=source-evidence-only ;;
        --construct-and-load-model) ACTION=construct-and-load-model ;;
        --accept-provisional-local-noncommercial-terms) ACCEPTED_PROVISIONAL_TERMS=true ;;
        --accept-checkpoint-use) ACCEPTED_CHECKPOINT_USE=true ;;
        --accept-runtime-wheel-evidence) ACCEPTED_RUNTIME_WHEEL_EVIDENCE=true ;;
        --accept-runtime-install-and-import) ACCEPTED_RUNTIME_INSTALL_AND_IMPORT=true ;;
        --accept-source-evidence) ACCEPTED_SOURCE_EVIDENCE=true ;;
        --accept-restricted-model-load) ACCEPTED_RESTRICTED_MODEL_LOAD=true ;;
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

if [ "$ACTION" = source-evidence-only ]; then
    if [ "$ACCEPTED_SOURCE_EVIDENCE" != true ]; then
        echo "--source-evidence-only requires --accept-source-evidence after reviewing the exact source boundary" >&2
        exit 2
    fi
    for required_command in curl sandbox-exec shasum; do
        if ! command -v "$required_command" >/dev/null 2>&1; then
            echo "$required_command is required for Mega-53 source evidence" >&2
            exit 2
        fi
    done
    if [ -e "$SOURCE_EVIDENCE_ROOT" ] || [ -L "$SOURCE_EVIDENCE_ROOT" ]; then
        echo "Refusing to overwrite existing Mega-53 source evidence: $SOURCE_EVIDENCE_ROOT" >&2
        exit 2
    fi
    SOURCE_EVIDENCE_PARENT=$(dirname "$SOURCE_EVIDENCE_ROOT")
    mkdir -p "$SOURCE_EVIDENCE_PARENT"
    STAGING=$(mktemp -d "$SOURCE_EVIDENCE_PARENT/.bs-roformer-source.building.XXXXXX")
    preserve_failed_source_staging() {
        source_exit_code=$?
        if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
            failed_root="$SOURCE_EVIDENCE_PARENT/bs-roformer-infer-de35ada-source.failed.$$.evidence"
            if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
                chmod -R go-w "$STAGING" 2>/dev/null || true
                mv "$STAGING" "$failed_root"
                STAGING=
                echo "Preserved failed Mega-53 source evidence: $failed_root" >&2
            fi
        fi
        exit "$source_exit_code"
    }
    trap preserve_failed_source_staging EXIT HUP INT TERM
    SOURCE_ARCHIVE="$STAGING/bs-roformer-infer-$SOURCE_REVISION.tar.gz"
    (
        ulimit -f 65536
        curl --fail --location --retry 3 --silent --show-error \
            --proto '=https' --tlsv1.2 --max-filesize "$SOURCE_CAP_BYTES" \
            "$SOURCE_URL" --output "$SOURCE_ARCHIVE"
    )
    ACTUAL_SOURCE_BYTES=$(wc -c < "$SOURCE_ARCHIVE" | tr -d ' ')
    if [ "$ACTUAL_SOURCE_BYTES" -le 0 ] || [ "$ACTUAL_SOURCE_BYTES" -gt "$SOURCE_CAP_BYTES" ]; then
        echo "Mega-53 source archive exceeds the approved 32 MiB cap" >&2
        exit 2
    fi
    mkdir "$STAGING/source"
    PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
        sandbox-exec -p '(version 1)(allow default)(deny network*)' \
        "$PLAN_PYTHON" -B "$SOURCE_INSPECT_SCRIPT" "$SOURCE_ARCHIVE" \
        --extract-root "$STAGING/source" > "$STAGING/STATIC-EVIDENCE.json"

    PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
        "$PLAN_PYTHON" -B - "$STAGING/STATIC-EVIDENCE.json" \
        "$STAGING/APPROVAL-RECEIPT.json" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sunofriend.separation_other_refinement_next_source_evidence import (
    validate_source_evidence,
)

evidence = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
validate_source_evidence(evidence)
receipt = {
    "schema": "sunofriend.mega53-source-evidence-approval.v1",
    "status": "exact_source_materialized_no_model_authority_added",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "profile_id": "bs-roformer-mega-53-synth-v1",
    "source_revision": evidence["source_revision"],
    "source_evidence_sha256": evidence["evidence_sha256"],
    "archive": evidence["archive"],
    "network_denied_during_static_inspection": True,
    "source_imported": False,
    "checkpoint_loaded": False,
    "model_constructed": False,
    "inference_performed": False,
    "audio_processed": False,
    "not_approved": [
        "inference",
        "audio_processing",
        "public_activation",
        "source_selection",
        "midi",
        "hosting",
        "redistribution",
    ],
}
Path(sys.argv[2]).write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

    chmod 0444 "$SOURCE_ARCHIVE" "$STAGING/STATIC-EVIDENCE.json" "$STAGING/APPROVAL-RECEIPT.json"
    chmod -R a-w "$STAGING/source"
    chmod -R go-w "$STAGING"
    mv "$STAGING" "$SOURCE_EVIDENCE_ROOT"
    STAGING=
    trap - EXIT HUP INT TERM
    echo ""
    echo "Exact Mega-53 source evidence complete: $SOURCE_EVIDENCE_ROOT"
    echo "Observed source archive bytes: $ACTUAL_SOURCE_BYTES of $SOURCE_CAP_BYTES approved"
    echo "Static inspection ran with network denied; no source code was imported or executed."
    exit 0
fi

if [ "$ACTION" = construct-and-load-model ]; then
    if [ "$ACCEPTED_RESTRICTED_MODEL_LOAD" != true ]; then
        echo "--construct-and-load-model requires --accept-restricted-model-load after reviewing the exact no-inference boundary" >&2
        exit 2
    fi
    if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
        echo "The approved Mega-53 model load targets macOS on Apple silicon only" >&2
        exit 2
    fi
    for required_command in sandbox-exec shasum; do
        if ! command -v "$required_command" >/dev/null 2>&1; then
            echo "$required_command is required for restricted Mega-53 model loading" >&2
            exit 2
        fi
    done
    if [ -e "$MODEL_LOAD_ROOT" ] || [ -L "$MODEL_LOAD_ROOT" ]; then
        echo "Refusing to overwrite existing Mega-53 model-load evidence: $MODEL_LOAD_ROOT" >&2
        exit 2
    fi
    for required_evidence in \
        "$EVIDENCE_ROOT/$CHECKPOINT_FILE" \
        "$EVIDENCE_ROOT/$CONFIG_FILE" \
        "$EVIDENCE_ROOT/STATIC-EVIDENCE.json" \
        "$RUNTIME_IMPORT_ROOT/IMPORT-REPORT.json" \
        "$RUNTIME_IMPORT_ROOT/APPROVAL-RECEIPT.json" \
        "$SOURCE_EVIDENCE_ROOT/STATIC-EVIDENCE.json" \
        "$SOURCE_EVIDENCE_ROOT/APPROVAL-RECEIPT.json" \
        "$SOURCE_EVIDENCE_ROOT/source"; do
        if [ ! -e "$required_evidence" ] || [ -L "$required_evidence" ]; then
            echo "Approved Mega-53 model-load prerequisite is missing: $required_evidence" >&2
            exit 2
        fi
    done
    if [ ! -x "$RUNTIME_IMPORT_ROOT/runtime/bin/python" ]; then
        echo "Approved Mega-53 runtime Python is not executable" >&2
        exit 2
    fi
    echo "$CHECKPOINT_SHA256  $EVIDENCE_ROOT/$CHECKPOINT_FILE" | shasum -a 256 -c - >/dev/null
    echo "$CONFIG_SHA256  $EVIDENCE_ROOT/$CONFIG_FILE" | shasum -a 256 -c - >/dev/null
    echo "567068a414c5ebc0cdb7cd47564934c5ec8f6b13c70425dd736c02af43892ac7  $RUNTIME_IMPORT_ROOT/IMPORT-REPORT.json" | shasum -a 256 -c - >/dev/null
    echo "1e4a7c3f661171b4e62cf0efae55971a71eb51e0b52cd9b29176214e160080ed  $RUNTIME_IMPORT_ROOT/APPROVAL-RECEIPT.json" | shasum -a 256 -c - >/dev/null
    echo "c6c6536708f27bb378e71ca19f6ab824b34e2ba99b8b4e87e058414f30d1a575  $SOURCE_EVIDENCE_ROOT/STATIC-EVIDENCE.json" | shasum -a 256 -c - >/dev/null
    echo "9b95036b8219eb5cd7be61a29868e6633dd42df0078eda55a0f3710123551c73  $SOURCE_EVIDENCE_ROOT/bs-roformer-infer-$SOURCE_REVISION.tar.gz" | shasum -a 256 -c - >/dev/null
    if [ "$("$RUNTIME_IMPORT_ROOT/runtime/bin/python" -c 'import platform, sys; print(f"{sys.version_info.major}.{sys.version_info.minor}:{platform.machine()}")')" != 3.12:arm64 ]; then
        echo "Approved Mega-53 model-load runtime identity differs" >&2
        exit 2
    fi

    MODEL_LOAD_PARENT=$(dirname "$MODEL_LOAD_ROOT")
    mkdir -p "$MODEL_LOAD_PARENT"
    STAGING=$(mktemp -d "$MODEL_LOAD_PARENT/.bs-roformer-mega-53-model-load.building.XXXXXX")
    preserve_failed_model_load_staging() {
        model_load_exit_code=$?
        if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
            failed_root="$MODEL_LOAD_PARENT/bs-roformer-mega-53-model-load.failed.$$.evidence"
            if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
                chmod -R go-w "$STAGING" 2>/dev/null || true
                mv "$STAGING" "$failed_root"
                STAGING=
                echo "Preserved failed Mega-53 model-load evidence: $failed_root" >&2
            fi
        fi
        exit "$model_load_exit_code"
    }
    trap preserve_failed_model_load_staging EXIT HUP INT TERM
    mkdir -p "$STAGING/home/cache" "$STAGING/home/torch"

    HOME="$STAGING/home" XDG_CACHE_HOME="$STAGING/home/cache" \
    TORCH_HOME="$STAGING/home/torch" HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
    MLX_ENABLE_COMPILE=0 MLX_AUDIO_SEPARATOR_ROFORMER_GROUPED_BAND_SPLIT=0 \
    MLX_AUDIO_SEPARATOR_ROFORMER_GROUPED_MASK_ESTIMATOR=0 \
    MLX_AUDIO_SEPARATOR_ROFORMER_COMPILE_FULLGRAPH=0 \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$RUNTIME_IMPORT_ROOT/runtime/bin/python" -I -B "$MODEL_LOAD_SCRIPT" \
        --checkpoint "$EVIDENCE_ROOT/$CHECKPOINT_FILE" \
        --config "$EVIDENCE_ROOT/$CONFIG_FILE" \
        --source-root "$SOURCE_EVIDENCE_ROOT/source" \
        --source-evidence "$SOURCE_EVIDENCE_ROOT/STATIC-EVIDENCE.json" \
        > "$STAGING/MODEL-LOAD-REPORT.json" \
        2> "$STAGING/CONSTRUCTION.log"

    PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
        "$PLAN_PYTHON" -B "$MODEL_LOAD_RECEIPT_SCRIPT" \
        --report "$STAGING/MODEL-LOAD-REPORT.json" \
        --receipt "$STAGING/APPROVAL-RECEIPT.json" \
        --published-root "$MODEL_LOAD_ROOT"

    chmod 0444 "$STAGING"/*.json "$STAGING"/*.log
    chmod -R go-w "$STAGING"
    mv "$STAGING" "$MODEL_LOAD_ROOT"
    STAGING=
    trap - EXIT HUP INT TERM
    echo ""
    echo "Restricted Mega-53 model-load gate complete: $MODEL_LOAD_ROOT"
    echo "The exact MLX model was constructed and loaded once with strict converted-state checks."
    echo "No inference or audio ran, and nothing was activated, selected or sent to MIDI."
    exit 0
fi

if [ "$ACTION" = install-runtime ]; then
    if [ "$ACCEPTED_RUNTIME_INSTALL_AND_IMPORT" != true ]; then
        echo "--install-runtime requires --accept-runtime-install-and-import after reviewing the exact isolated boundary" >&2
        exit 2
    fi
    if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
        echo "The approved isolated Mega-53 runtime targets macOS on Apple silicon only" >&2
        exit 2
    fi
    for required_command in sandbox-exec shasum df cmp; do
        if ! command -v "$required_command" >/dev/null 2>&1; then
            echo "$required_command is required for isolated Mega-53 runtime verification" >&2
            exit 2
        fi
    done
    if command -v python3.12 >/dev/null 2>&1; then
        RUNTIME_IMPORT_PYTHON=$(command -v python3.12)
    else
        echo "Python 3.12 is required for the exact isolated Mega-53 runtime" >&2
        exit 2
    fi
    if [ "$("$RUNTIME_IMPORT_PYTHON" -c 'import platform, sys; print(f"{sys.implementation.name}:{sys.version_info.major}.{sys.version_info.minor}:{platform.machine()}")')" != cpython:3.12:arm64 ]; then
        echo "Selected isolated Mega-53 runtime Python must be CPython 3.12 on arm64: $RUNTIME_IMPORT_PYTHON" >&2
        exit 2
    fi
    if [ -e "$RUNTIME_IMPORT_ROOT" ] || [ -L "$RUNTIME_IMPORT_ROOT" ]; then
        echo "Refusing to overwrite existing isolated Mega-53 runtime evidence: $RUNTIME_IMPORT_ROOT" >&2
        exit 2
    fi
    for required_evidence in \
        "$RUNTIME_WHEEL_EVIDENCE_ROOT/STATIC-EVIDENCE.json" \
        "$RUNTIME_WHEEL_EVIDENCE_ROOT/APPROVAL-RECEIPT.json" \
        "$RUNTIME_WHEEL_EVIDENCE_ROOT/requirements.txt" \
        "$RUNTIME_WHEEL_EVIDENCE_ROOT/wheels"; do
        if [ ! -e "$required_evidence" ] || [ -L "$required_evidence" ]; then
            echo "Approved Mega-53 runtime wheel evidence is incomplete: $required_evidence" >&2
            exit 2
        fi
    done
    ACTUAL_REQUIREMENTS_SHA256=$(shasum -a 256 "$RUNTIME_REQUIREMENTS" | awk '{print $1}')
    if [ "$ACTUAL_REQUIREMENTS_SHA256" != "$RUNTIME_REQUIREMENTS_SHA256" ]; then
        echo "Committed Mega-53 runtime lock SHA-256 differs: $ACTUAL_REQUIREMENTS_SHA256" >&2
        exit 2
    fi
    if ! cmp -s "$RUNTIME_REQUIREMENTS" "$RUNTIME_WHEEL_EVIDENCE_ROOT/requirements.txt"; then
        echo "Committed Mega-53 runtime lock differs from the approved local wheel evidence" >&2
        exit 2
    fi
    ACTUAL_STATIC_EVIDENCE_SHA256=$(shasum -a 256 "$RUNTIME_WHEEL_EVIDENCE_ROOT/STATIC-EVIDENCE.json" | awk '{print $1}')
    if [ "$ACTUAL_STATIC_EVIDENCE_SHA256" != 5121a18a25d617c17efadb8d95eab342ef8b442e40eb4690519b80987e70e19d ]; then
        echo "Mega-53 wheel static-evidence file SHA-256 differs: $ACTUAL_STATIC_EVIDENCE_SHA256" >&2
        exit 2
    fi
    PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
        sandbox-exec -p '(version 1)(allow default)(deny network*)' \
        "$PLAN_PYTHON" -B "$WHEEL_INSPECT_SCRIPT" \
        "$RUNTIME_WHEEL_EVIDENCE_ROOT/wheels" \
        > /dev/null

    RUNTIME_IMPORT_PARENT=$(dirname "$RUNTIME_IMPORT_ROOT")
    mkdir -p "$RUNTIME_IMPORT_PARENT"
    available_bytes=$(df -Pk "$RUNTIME_IMPORT_PARENT" | awk 'NR == 2 {printf "%.0f", $4 * 1024}')
    if [ -z "$available_bytes" ] || [ "$available_bytes" -lt 2147483648 ]; then
        echo "Isolated Mega-53 runtime setup requires at least 2147483648 free bytes before staging" >&2
        exit 2
    fi
    STAGING=$(mktemp -d "$RUNTIME_IMPORT_PARENT/.bs-roformer-mega-53-runtime-import.building.XXXXXX")
    preserve_failed_runtime_import_staging() {
        runtime_import_exit_code=$?
        if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
            failed_root="$RUNTIME_IMPORT_PARENT/bs-roformer-mega-53-runtime-import.failed.$$.evidence"
            if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
                chmod -R go-w "$STAGING" 2>/dev/null || true
                mv "$STAGING" "$failed_root"
                STAGING=
                echo "Preserved failed isolated Mega-53 runtime evidence: $failed_root" >&2
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
assert report["schema"] == "sunofriend.mega53-runtime-import-evidence.v1"
assert report["status"] == "isolated_hash_locked_runtime_imports_verified_network_denied"
assert report["locked_package_count"] == 29
assert len(report["locked_packages"]) == 29
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
    "local_bind_attempts": ["requests:socket.bind:('::1', 0)"],
    "os_network_denial_required": True,
    "python_network_attempts": 0,
    "socket_constructions": ["requests:socket.__new__"],
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
assert effects["hosting"] is False
assert effects["redistribution"] is False

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
    "schema": "sunofriend.mega53-runtime-import-approval.v1",
    "status": "isolated_runtime_import_gate_complete_no_model_authority",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "profile_id": "bs-roformer-mega-53-synth-v1",
    "published_root": str(published_root),
    "runtime_requirements_sha256": "284d198c43e9074a4d645f005d937dd4e93b99e22aa21d942caaa1822b13d10b",
    "wheel_static_evidence_file_sha256": "5121a18a25d617c17efadb8d95eab342ef8b442e40eb4690519b80987e70e19d",
    "import_report_sha256": report["report_sha256"],
    "approved_action": (
        "install the exact 29-wheel hash-locked CPython 3.12 macOS 14+ arm64 "
        "runtime into a fresh isolated Sunofriend evidence environment and "
        "perform network-denied package-import verification only"
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
    "hosting": False,
    "redistribution": False,
    "not_approved": [
        "checkpoint_loading",
        "model_construction",
        "inference",
        "audio_processing",
        "public_activation",
        "source_selection",
        "midi",
        "hosting",
        "redistribution",
    ],
}
receipt_path.write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

    installed_bytes=$(du -sk "$STAGING" | awk '{printf "%.0f", $1 * 1024}')
    if [ -z "$installed_bytes" ] || [ "$installed_bytes" -gt 2147483648 ]; then
        echo "Isolated Mega-53 runtime staging exceeds the 2 GiB installation ceiling" >&2
        exit 2
    fi
    chmod 0444 "$STAGING"/*.json "$STAGING"/*.log
    chmod -R go-w "$STAGING"
    mv "$STAGING" "$RUNTIME_IMPORT_ROOT"
    STAGING=
    trap - EXIT HUP INT TERM

    echo ""
    echo "Isolated Mega-53 runtime import gate complete: $RUNTIME_IMPORT_ROOT"
    echo "The exact 29-wheel runtime was installed from the approved local cache and imported under network denial."
    echo "No checkpoint was loaded, no model was constructed, no inference or audio ran, and nothing was activated, selected, sent to MIDI, hosted or redistributed."
    exit 0
fi

if [ "$ACTION" = runtime-wheel-evidence-only ]; then
    if [ "$ACCEPTED_RUNTIME_WHEEL_EVIDENCE" != true ]; then
        echo "--runtime-wheel-evidence-only requires --accept-runtime-wheel-evidence after reviewing the exact boundary" >&2
        exit 2
    fi
    if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
        echo "The approved wheel closure targets macOS on Apple silicon only" >&2
        exit 2
    fi
    for required_command in sandbox-exec shasum python3.12; do
        if ! command -v "$required_command" >/dev/null 2>&1; then
            echo "$required_command is required for runtime evidence" >&2
            exit 2
        fi
    done
    RUNTIME_WHEEL_PYTHON=$(command -v python3.12)
    if [ "$("$RUNTIME_WHEEL_PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != 3.12 ]; then
        echo "Selected Mega-53 resolver must be Python 3.12: $RUNTIME_WHEEL_PYTHON" >&2
        exit 2
    fi
    if [ -e "$RUNTIME_WHEEL_EVIDENCE_ROOT" ] || [ -L "$RUNTIME_WHEEL_EVIDENCE_ROOT" ]; then
        echo "Refusing to overwrite existing Mega-53 runtime wheel evidence: $RUNTIME_WHEEL_EVIDENCE_ROOT" >&2
        exit 2
    fi
    RUNTIME_WHEEL_PARENT=$(dirname "$RUNTIME_WHEEL_EVIDENCE_ROOT")
    mkdir -p "$RUNTIME_WHEEL_PARENT"
    RUNTIME_WHEEL_STAGING=$(mktemp -d "$RUNTIME_WHEEL_PARENT/.bs-roformer-mega-53-runtime-wrapper.XXXXXX")
    rmdir "$RUNTIME_WHEEL_STAGING"
    preserve_failed_runtime_staging() {
        mega53_runtime_exit_code=$?
        if [ -n "${RUNTIME_WHEEL_STAGING:-}" ] && [ -d "$RUNTIME_WHEEL_STAGING" ]; then
            failed_root="$RUNTIME_WHEEL_PARENT/bs-roformer-mega-53-runtime-wheels.failed.$$.evidence"
            if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
                chmod -R go-w "$RUNTIME_WHEEL_STAGING" 2>/dev/null || true
                mv "$RUNTIME_WHEEL_STAGING" "$failed_root"
                RUNTIME_WHEEL_STAGING=
                echo "Preserved failed runtime evidence staging: $failed_root" >&2
            fi
        fi
        exit "$mega53_runtime_exit_code"
    }
    trap preserve_failed_runtime_staging EXIT HUP INT TERM

    "$PLAN_PYTHON" -B "$WHEEL_DOWNLOAD_SCRIPT" \
        --python "$RUNTIME_WHEEL_PYTHON" \
        --destination "$RUNTIME_WHEEL_STAGING" \
        --cap-bytes "$RUNTIME_WHEEL_CAP_BYTES" \
        --report "$RUNTIME_WHEEL_STAGING/DOWNLOAD-RECEIPT.json"

    PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
        sandbox-exec -p '(version 1)(allow default)(deny network*)' \
        "$PLAN_PYTHON" -B "$WHEEL_INSPECT_SCRIPT" "$RUNTIME_WHEEL_STAGING/wheels" \
        > "$RUNTIME_WHEEL_STAGING/STATIC-EVIDENCE.json"

    PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
        sandbox-exec -p '(version 1)(allow default)(deny network*)' \
        "$PLAN_PYTHON" -B - \
        "$RUNTIME_WHEEL_STAGING/STATIC-EVIDENCE.json" \
        "$RUNTIME_WHEEL_STAGING/APPROVAL-RECEIPT.json" \
        "$RUNTIME_WHEEL_STAGING/requirements.txt" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sunofriend.separation_other_refinement_next_runtime_evidence import (
    validate_runtime_wheel_evidence,
)

evidence_path = Path(sys.argv[1])
receipt_path = Path(sys.argv[2])
requirements_path = Path(sys.argv[3])
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
validate_runtime_wheel_evidence(evidence)
requirements = [
    "# Mega-53 / BS-RoFormer CPython 3.12 macOS-arm64 wheel closure",
    "# Evidence only: installation and import require separate approval.",
    "--only-binary=:all:",
    *evidence["hash_locked_requirements"],
]
requirements_path.write_text("\n".join(requirements) + "\n", encoding="utf-8")
receipt = {
    "schema": "sunofriend.mega53-runtime-wheel-evidence-approval.v1",
    "status": "evidence_only_complete_no_install_or_import_authority",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "profile_id": "bs-roformer-mega-53-synth-v1",
    "runtime_source": evidence["runtime_source"],
    "runtime_wheel_evidence_sha256": evidence["evidence_sha256"],
    "package_count": evidence["package_count"],
    "wheel_bytes": evidence["wheel_bytes"],
    "approved_cap_bytes": 1_610_612_736,
    "network_denied_during_static_inspection": True,
    "not_approved": [
        "dependency_installation",
        "package_import",
        "checkpoint_loading",
        "model_construction",
        "inference",
        "audio_processing",
        "public_activation",
        "source_selection",
        "midi",
        "hosting",
        "redistribution",
    ],
}
receipt_path.write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

    GENERATED_REQUIREMENTS_SHA256=$(shasum -a 256 "$RUNTIME_WHEEL_STAGING/requirements.txt" | awk '{print $1}')
    if [ "$GENERATED_REQUIREMENTS_SHA256" != "$RUNTIME_REQUIREMENTS_SHA256" ]; then
        echo "Generated Mega-53 runtime lock SHA-256 differs: $GENERATED_REQUIREMENTS_SHA256" >&2
        exit 2
    fi
    if ! cmp -s "$RUNTIME_WHEEL_STAGING/requirements.txt" "$RUNTIME_REQUIREMENTS"; then
        echo "Generated Mega-53 runtime lock differs from the reviewed committed lock" >&2
        exit 2
    fi
    rmdir "$RUNTIME_WHEEL_STAGING/tmp"
    chmod 0444 \
        "$RUNTIME_WHEEL_STAGING/DOWNLOAD-RECEIPT.json" \
        "$RUNTIME_WHEEL_STAGING/STATIC-EVIDENCE.json" \
        "$RUNTIME_WHEEL_STAGING/APPROVAL-RECEIPT.json" \
        "$RUNTIME_WHEEL_STAGING/requirements.txt" \
        "$RUNTIME_WHEEL_STAGING/PIP-DOWNLOAD.log" \
        "$RUNTIME_WHEEL_STAGING"/wheels/*.whl
    chmod -R go-w "$RUNTIME_WHEEL_STAGING"
    mv "$RUNTIME_WHEEL_STAGING" "$RUNTIME_WHEEL_EVIDENCE_ROOT"
    RUNTIME_WHEEL_STAGING=
    trap - EXIT HUP INT TERM

    echo ""
    echo "Evidence-only Mega-53 runtime closure complete: $RUNTIME_WHEEL_EVIDENCE_ROOT"
    echo "No package was installed or imported; no checkpoint, model or audio was opened."
    exit 0
fi

if [ "$ACCEPTED_PROVISIONAL_TERMS" != true ] || [ "$ACCEPTED_CHECKPOINT_USE" != true ]; then
    echo "--evidence-only requires both acceptance flags after reviewing the plan" >&2
    exit 2
fi
for required_command in curl sandbox-exec; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        echo "$required_command is required" >&2
        exit 2
    fi
done
if [ "$EXPECTED_TOTAL_BYTES" -gt "$MAX_DOWNLOAD_BYTES" ]; then
    echo "Reviewed artifact identities exceed the approved 1.5 GiB cap" >&2
    exit 2
fi
if [ -e "$EVIDENCE_ROOT" ] || [ -L "$EVIDENCE_ROOT" ]; then
    echo "Refusing to overwrite existing Mega-53 evidence: $EVIDENCE_ROOT" >&2
    exit 2
fi

EVIDENCE_PARENT=$(dirname "$EVIDENCE_ROOT")
mkdir -p "$EVIDENCE_PARENT"
STAGING=$(mktemp -d "$EVIDENCE_PARENT/.bs-roformer-mega-53-synth-v1.building.XXXXXX")
preserve_failed_staging() {
    mega53_exit_code=$?
    if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
        failed_root="$EVIDENCE_PARENT/bs-roformer-mega-53-synth-v1.failed.$$.evidence"
        if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
            chmod -R go-w "$STAGING" 2>/dev/null || true
            mv "$STAGING" "$failed_root"
            STAGING=
            echo "Preserved failed evidence staging: $failed_root" >&2
        fi
    fi
    exit "$mega53_exit_code"
}
trap preserve_failed_staging EXIT HUP INT TERM

CHECKPOINT="$STAGING/$CHECKPOINT_FILE"
CONFIG="$STAGING/$CONFIG_FILE"
(
    ulimit -f 3145728
    curl --fail --location --retry 3 --silent --show-error \
        --proto '=https' --tlsv1.2 --max-filesize "$MAX_DOWNLOAD_BYTES" \
        "$CONFIG_URL" --output "$CONFIG"
    curl --fail --location --retry 3 --silent --show-error \
        --proto '=https' --tlsv1.2 --max-filesize "$MAX_DOWNLOAD_BYTES" \
        "$CHECKPOINT_URL" --output "$CHECKPOINT"
)

ACTUAL_CHECKPOINT_BYTES=$(wc -c < "$CHECKPOINT" | tr -d ' ')
ACTUAL_CONFIG_BYTES=$(wc -c < "$CONFIG" | tr -d ' ')
ACTUAL_TOTAL_BYTES=$((ACTUAL_CHECKPOINT_BYTES + ACTUAL_CONFIG_BYTES))
if [ "$ACTUAL_CHECKPOINT_BYTES" != "$CHECKPOINT_BYTES" ]; then
    echo "Mega-53 checkpoint byte count differs: $ACTUAL_CHECKPOINT_BYTES" >&2
    exit 2
fi
if [ "$ACTUAL_CONFIG_BYTES" != "$CONFIG_BYTES" ]; then
    echo "Mega-53 configuration byte count differs: $ACTUAL_CONFIG_BYTES" >&2
    exit 2
fi
if [ "$ACTUAL_TOTAL_BYTES" -gt "$MAX_DOWNLOAD_BYTES" ]; then
    echo "Downloaded artifacts exceed the approved 1.5 GiB cap" >&2
    exit 2
fi
chmod 0444 "$CHECKPOINT" "$CONFIG"

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$PLAN_PYTHON" -B "$INSPECT_SCRIPT" "$CHECKPOINT" "$CONFIG" \
    > "$STAGING/STATIC-EVIDENCE.json"

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$PLAN_PYTHON" -B - "$STAGING/STATIC-EVIDENCE.json" "$STAGING/APPROVAL-RECEIPT.json" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sunofriend.separation_other_refinement_next_challenger_evidence import (
    validate_mega53_artifact_evidence,
)

evidence_path = Path(sys.argv[1])
receipt_path = Path(sys.argv[2])
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
validate_mega53_artifact_evidence(evidence)
effects = evidence["effects"]
assert effects["checkpoint_deserialized"] is False
assert effects["torch_load_called"] is False
assert effects["dependency_installed"] is False
assert effects["model_imported"] is False
assert effects["model_constructed"] is False
assert effects["inference_runs"] == 0
assert effects["audio_reads"] == 0
receipt = {
    "schema": "sunofriend.mvsep-mega53-evidence-approval.v1",
    "status": "evidence_only_complete_no_runtime_authority",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "profile_id": "bs-roformer-mega-53-synth-v1",
    "artifact_evidence_sha256": evidence["evidence_sha256"],
    "terms_acknowledged": "provisional local noncommercial evaluation only",
    "checkpoint_use_approved": "capped evidence-only download and static inspection",
    "network_denied_during_static_inspection": True,
    "not_approved": [
        "dependency_installation",
        "checkpoint_loading",
        "model_construction",
        "inference",
        "private_audio_processing",
        "public_activation",
        "source_selection",
        "midi",
        "hosting",
        "checkpoint_redistribution",
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
echo "Evidence-only Mega-53 cache complete: $EVIDENCE_ROOT"
echo "Checkpoint SHA-256: $CHECKPOINT_SHA256"
echo "Configuration SHA-256: $CONFIG_SHA256"
echo "Observed total bytes: $ACTUAL_TOTAL_BYTES of $MAX_DOWNLOAD_BYTES approved"
echo "Static inspection ran with network denied and did not deserialize the checkpoint."
echo "Nothing was installed, imported, loaded, inferred, activated, selected or sent to MIDI."
