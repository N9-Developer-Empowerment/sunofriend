#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PLAN_SCRIPT="$REPOSITORY_ROOT/scripts/plan-separation-other-refinement-demucs-mlx.py"
INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-other-refinement-demucs-mlx.py"
RUNTIME_REQUIREMENTS="$REPOSITORY_ROOT/separation-core-four-runtime-requirements.txt"
PROFILE_ID=demucs-mlx-htdemucs-6s-other-refinement-v1
MODEL_REVISION=d4519e24ddc2dd4a11d56a193092433d852c3961
RUNTIME_REVISION=b37e6ba3c5985af531f61c43564cf13c6ed349fd
DATA_ROOT=${SUNOFRIEND_SEPARATION_ROOT:-"$HOME/.local/share/sunofriend/separation"}
PROFILE_ROOT=${SUNOFRIEND_OTHER_REFINEMENT_MODEL_ROOT:-"$DATA_ROOT/$PROFILE_ID"}
ACTION=plan
ACCEPTED_TERMS=false
ACCEPTED_CHECKPOINT_USE=false

usage() {
    echo "Usage: scripts/setup-separation-other-refinement-demucs-mlx-macos.sh [--plan | --install --accept-model-terms --accept-checkpoint-use]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan) ACTION=plan ;;
        --install) ACTION=install ;;
        --accept-model-terms) ACCEPTED_TERMS=true ;;
        --accept-checkpoint-use) ACCEPTED_CHECKPOINT_USE=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [ -n "${SUNOFRIEND_OTHER_REFINEMENT_PLAN_PYTHON:-}" ]; then
    PLAN_PYTHON=$SUNOFRIEND_OTHER_REFINEMENT_PLAN_PYTHON
else
    PLAN_PYTHON="$REPOSITORY_ROOT/.venv/bin/python"
fi
if [ ! -x "$PLAN_PYTHON" ]; then
    echo "The Sunofriend workspace Python is required to inspect this plan: $PLAN_PYTHON" >&2
    exit 2
fi

"$PLAN_PYTHON" "$PLAN_SCRIPT"

if [ "$ACTION" = plan ]; then
    echo ""
    echo "Plan only; nothing was downloaded, installed, deserialized, constructed or executed."
    echo "The install command requires separate explicit approval and both acceptance flags."
    echo "Installation still will not authorize model construction, inference or private-audio processing."
    exit 0
fi

if [ "$ACCEPTED_TERMS" != true ] || [ "$ACCEPTED_CHECKPOINT_USE" != true ]; then
    echo "--install requires both --accept-model-terms and --accept-checkpoint-use after reviewing the exact plan" >&2
    exit 2
fi

if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    echo "The first six-source MLX setup supports macOS on Apple silicon only" >&2
    exit 2
fi
for required_command in curl shasum sandbox-exec df; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        echo "$required_command is required" >&2
        exit 2
    fi
done
if [ -n "${SUNOFRIEND_SEPARATION_PYTHON_BIN:-}" ]; then
    RUNTIME_PYTHON=$SUNOFRIEND_SEPARATION_PYTHON_BIN
elif command -v python3.13 >/dev/null 2>&1; then
    RUNTIME_PYTHON=$(command -v python3.13)
else
    echo "Python 3.13 is required for the exact six-source MLX wheel lock" >&2
    exit 2
fi
if [ "$($RUNTIME_PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != 3.13 ]; then
    echo "Selected six-source MLX Python must be 3.13: $RUNTIME_PYTHON" >&2
    exit 2
fi
if [ -e "$PROFILE_ROOT" ] || [ -L "$PROFILE_ROOT" ]; then
    echo "Refusing to overwrite an existing six-source MLX profile root: $PROFILE_ROOT" >&2
    exit 2
fi
if [ "$(wc -c < "$RUNTIME_REQUIREMENTS" | tr -d ' ')" != 1640 ]; then
    echo "Six-source MLX runtime lock byte count changed" >&2
    exit 2
fi
echo "11af62d2ce759e8e4937bd10046892c03dc8ba61bf8cb2537b6a53f4a257587c  $RUNTIME_REQUIREMENTS" | shasum -a 256 -c - >/dev/null

mkdir -p "$DATA_ROOT"
available_bytes=$(df -Pk "$DATA_ROOT" | awk 'NR == 2 {printf "%.0f", $4 * 1024}')
if [ -z "$available_bytes" ] || [ "$available_bytes" -lt 2000000000 ]; then
    echo "Six-source MLX setup requires at least 2000000000 free bytes before staging" >&2
    exit 2
fi

STAGING=$(mktemp -d "$DATA_ROOT/.other-refinement-demucs-mlx.building.XXXXXX")
preserve_failed_staging() {
    refinement_exit_code=$?
    if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
        failed_root="$DATA_ROOT/$PROFILE_ID.failed.$$.evidence"
        if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
            chmod -R go-w "$STAGING" 2>/dev/null || true
            mv "$STAGING" "$failed_root"
            STAGING=
            echo "Preserved failed six-source MLX setup evidence: $failed_root" >&2
        fi
    fi
    exit "$refinement_exit_code"
}
trap preserve_failed_staging EXIT HUP INT TERM
mkdir -p "$STAGING/model" "$STAGING/TERMS"

download_verified() {
    refinement_url=$1
    refinement_target=$2
    refinement_expected_hash=$3
    refinement_expected_bytes=$4
    refinement_max_bytes=$5
    refinement_temporary=$(mktemp "$STAGING/.download.XXXXXX")
    if ! (
        ulimit -f 2097152
        curl --fail --location --retry 3 --silent --show-error \
            --max-filesize "$refinement_max_bytes" \
            "$refinement_url" --output "$refinement_temporary"
    ); then
        echo "Six-source MLX artifact download failed: $refinement_url" >&2
        exit 2
    fi
    refinement_actual_bytes=$(wc -c < "$refinement_temporary" | tr -d ' ')
    if [ "$refinement_actual_bytes" != "$refinement_expected_bytes" ]; then
        echo "Six-source MLX artifact byte mismatch: $refinement_url" >&2
        exit 2
    fi
    if ! echo "$refinement_expected_hash  $refinement_temporary" | shasum -a 256 -c - >/dev/null; then
        echo "Six-source MLX artifact SHA-256 mismatch: $refinement_url" >&2
        exit 2
    fi
    mv "$refinement_temporary" "$refinement_target"
    chmod 0444 "$refinement_target"
}

MODEL_BASE="https://huggingface.co/mlx-community/demucs-mlx/resolve/$MODEL_REVISION"
RUNTIME_BASE="https://raw.githubusercontent.com/ssmall256/demucs-mlx/$RUNTIME_REVISION"
download_verified "$MODEL_BASE/htdemucs_6s.safetensors" "$STAGING/model/htdemucs_6s.safetensors" d298f7f746bf53c21baad44fb08e88807ef47feb551dd22f1601a546c85b8e02 109726583 134217728
download_verified "$MODEL_BASE/htdemucs_6s_config.json" "$STAGING/model/htdemucs_6s_config.json" 97f8315891d8edc9aa6f59e56e0d352fbad5ebfb8a4faf46341ab2f1844596a9 1946 1048576
download_verified "$MODEL_BASE/README.md" "$STAGING/TERMS/model-README.md" 1f9e7231385b9a8356dbe443c9707e9ada483027277ef0fd4154143f516570ab 3971 1048576
download_verified "$RUNTIME_BASE/LICENSE" "$STAGING/TERMS/demucs-mlx-LICENSE" 15086279d32c0f00c577c0f52ff428daf98b8a1fec0264da1c717c88ad464f51 1117 1048576
download_verified "$RUNTIME_BASE/pyproject.toml" "$STAGING/TERMS/demucs-mlx-pyproject.toml" 3758e87bc8b8d2755e27c764fc7c464def17cd6e2ccef58817689524534ffe36 1672 1048576
cp "$RUNTIME_REQUIREMENTS" "$STAGING/TERMS/separation-runtime-requirements.txt"
chmod 0444 "$STAGING/TERMS/separation-runtime-requirements.txt"

"$RUNTIME_PYTHON" -m venv "$STAGING/runtime"
(
    ulimit -f 2097152
    "$STAGING/runtime/bin/python" -m pip install \
        --disable-pip-version-check --no-cache-dir --require-hashes \
        -r "$RUNTIME_REQUIREMENTS"
)

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$STAGING/runtime/bin/python" "$INSPECT_SCRIPT" "$STAGING" \
    > "$STAGING/STATIC-INSPECTION.json"
"$STAGING/runtime/bin/python" - "$STAGING/STATIC-INSPECTION.json" <<'PY'
import json
from pathlib import Path
import sys

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert document["schema"] == "sunofriend.other-refinement-demucs-mlx-inspection.v1"
assert document["status"] == "passed_static_identity_and_config_only"
assert document["config"]["normalization_in_memory_only"] is True
assert document["config"]["source_artifact_unchanged"] is True
assert document["effects"]["model_module_imported"] is False
assert document["effects"]["checkpoint_payload_opened"] is False
assert document["effects"]["model_constructed"] is False
assert document["effects"]["inference_runs"] == 0
assert document["effects"]["audio_reads"] == 0
PY

inspection_sha256=$(shasum -a 256 "$STAGING/STATIC-INSPECTION.json" | awk '{print $1}')
"$STAGING/runtime/bin/python" - "$STAGING/INSTALLATION.json" "$inspection_sha256" <<'PY'
import json
from pathlib import Path
import sys

document = {
    "schema": "sunofriend.other-refinement-demucs-mlx-installation.v1",
    "profile_id": "demucs-mlx-htdemucs-6s-other-refinement-v1",
    "model_terms_accepted": True,
    "checkpoint_use_accepted": True,
    "model_revision": "d4519e24ddc2dd4a11d56a193092433d852c3961",
    "runtime_source_revision": "b37e6ba3c5985af531f61c43564cf13c6ed349fd",
    "runtime_requirements_sha256": "11af62d2ce759e8e4937bd10046892c03dc8ba61bf8cb2537b6a53f4a257587c",
    "static_inspection_sha256": sys.argv[2],
    "direct_pinned_artifact_download_bytes": 109735289,
    "upstream_model_resolution_enabled": False,
    "static_inspection_network_denied": True,
    "checkpoint_payload_opened": False,
    "model_constructed": False,
    "inference_performed": False,
    "audio_processed": False,
    "public_execution_authorized": False,
    "source_or_midi_activation_authorized": False,
    "profile_status_after_setup": "blocked_pending_fraction_normalized_loader_and_synthetic_canary",
}
Path(sys.argv[1]).write_text(
    json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

installed_bytes=$(du -sk "$STAGING" | awk '{printf "%.0f", $1 * 1024}')
if [ -z "$installed_bytes" ] || [ "$installed_bytes" -gt 1073741824 ]; then
    echo "Six-source MLX staged installation exceeds the 1 GiB setup ceiling" >&2
    exit 2
fi

chmod -R go-w "$STAGING"
mv "$STAGING" "$PROFILE_ROOT"
STAGING=
trap - EXIT HUP INT TERM

echo ""
echo "Six-source MLX static setup complete: $PROFILE_ROOT"
echo "Exact files, packages and the in-memory fraction normalization contract were inspected under network denial."
echo "No model module or checkpoint payload was opened; no model was constructed and no audio or inference ran."
echo "A separately reviewed model-construction and synthetic-canary step remains required."
