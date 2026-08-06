#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PLAN_SCRIPT="$REPOSITORY_ROOT/scripts/plan-separation-core-four-scnet.py"
INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-core-four-scnet.py"
RUNTIME_REQUIREMENTS="$REPOSITORY_ROOT/separation-core-four-scnet-runtime-requirements.txt"
PROFILE_ID=scnet-large-musdb-release-v1
SOURCE_REVISION=6236f8c559778dc271e1aea9baa3993ae655e905
DATA_ROOT=${SUNOFRIEND_SEPARATION_ROOT:-"$HOME/.local/share/sunofriend/separation"}
MODEL_ROOT=${SUNOFRIEND_SEPARATION_MODEL_ROOT:-"$DATA_ROOT/$PROFILE_ID"}
ACTION=plan
ACCEPTED_TERMS=false
ACCEPTED_CHECKPOINT_USE=false

usage() {
    echo "Usage: scripts/setup-separation-core-four-scnet-macos.sh [--plan | --install --accept-model-terms --accept-checkpoint-use]"
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

if [ -n "${SUNOFRIEND_SCNET_PLAN_PYTHON:-}" ]; then
    PYTHON_BIN=$SUNOFRIEND_SCNET_PLAN_PYTHON
else
    PYTHON_BIN="$REPOSITORY_ROOT/.venv/bin/python"
fi
if [ ! -x "$PYTHON_BIN" ]; then
    echo "The Sunofriend workspace Python is required to inspect this plan: $PYTHON_BIN" >&2
    exit 2
fi

"$PYTHON_BIN" "$PLAN_SCRIPT"

if [ "$ACTION" = plan ]; then
    echo ""
    echo "Plan only; nothing was downloaded, installed, deserialized or executed."
    echo "The install command requires separate explicit approval and both acceptance flags."
    exit 0
fi

if [ "$ACCEPTED_TERMS" != true ] || [ "$ACCEPTED_CHECKPOINT_USE" != true ]; then
    echo "--install requires both --accept-model-terms and --accept-checkpoint-use after reviewing the exact plan" >&2
    exit 2
fi

if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    echo "The first SCNet compatibility setup supports macOS on Apple silicon only" >&2
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
    echo "Python 3.13 is required for the exact SCNet wheel lock" >&2
    exit 2
fi
if [ "$($RUNTIME_PYTHON -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != 3.13 ]; then
    echo "Selected SCNet Python must be 3.13: $RUNTIME_PYTHON" >&2
    exit 2
fi
if [ -e "$MODEL_ROOT" ] || [ -L "$MODEL_ROOT" ]; then
    echo "Refusing to overwrite an existing SCNet profile root: $MODEL_ROOT" >&2
    exit 2
fi
if [ "$(wc -c < "$RUNTIME_REQUIREMENTS" | tr -d ' ')" != 1236 ]; then
    echo "SCNet runtime lock byte count changed" >&2
    exit 2
fi
echo "692c8c5fb0606c70e60e559be60eac5ba1c439b652dc2df26174effd66acc508  $RUNTIME_REQUIREMENTS" | shasum -a 256 -c - >/dev/null

mkdir -p "$DATA_ROOT"
available_bytes=$(df -Pk "$DATA_ROOT" | awk 'NR == 2 {printf "%.0f", $4 * 1024}')
if [ -z "$available_bytes" ] || [ "$available_bytes" -lt 2000000000 ]; then
    echo "SCNet setup requires at least 2000000000 free bytes before staging" >&2
    exit 2
fi

STAGING=$(mktemp -d "$DATA_ROOT/.scnet-release.building.XXXXXX")
FAILED_ROOT=
preserve_failed_staging() {
    scnet_exit_code=$?
    if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
        FAILED_ROOT="$DATA_ROOT/$PROFILE_ID.failed.$$.evidence"
        if [ ! -e "$FAILED_ROOT" ] && [ ! -L "$FAILED_ROOT" ]; then
            chmod -R go-w "$STAGING" 2>/dev/null || true
            mv "$STAGING" "$FAILED_ROOT"
            STAGING=
            echo "Preserved failed SCNet setup evidence: $FAILED_ROOT" >&2
        fi
    fi
    exit "$scnet_exit_code"
}
trap preserve_failed_staging EXIT HUP INT TERM
mkdir -p "$STAGING/model" "$STAGING/source/scnet" "$STAGING/TERMS"

download_verified() {
    scnet_url=$1
    scnet_target=$2
    scnet_expected_hash=$3
    scnet_expected_bytes=$4
    scnet_max_bytes=$5
    scnet_temporary=$(mktemp "${TMPDIR:-/tmp}/sunofriend-scnet-setup.XXXXXX")
    if ! (
        ulimit -f 2097152
        curl --fail --location --retry 3 --silent --show-error \
            --max-filesize "$scnet_max_bytes" \
            "$scnet_url" --output "$scnet_temporary"
    ); then
        rm -f "$scnet_temporary"
        echo "SCNet artifact download failed: $scnet_url" >&2
        exit 2
    fi
    scnet_actual_bytes=$(wc -c < "$scnet_temporary" | tr -d ' ')
    if [ "$scnet_actual_bytes" != "$scnet_expected_bytes" ]; then
        rm -f "$scnet_temporary"
        echo "SCNet artifact byte mismatch: $scnet_url" >&2
        exit 2
    fi
    if ! echo "$scnet_expected_hash  $scnet_temporary" | shasum -a 256 -c - >/dev/null; then
        rm -f "$scnet_temporary"
        echo "SCNet artifact SHA-256 mismatch: $scnet_url" >&2
        exit 2
    fi
    mv "$scnet_temporary" "$scnet_target"
    chmod 0444 "$scnet_target"
}

SOURCE_BASE="https://raw.githubusercontent.com/starrytong/SCNet/$SOURCE_REVISION"
download_verified 'https://drive.usercontent.google.com/download?id=1s7QvQwn8ag9oVstGDBQ6KZvacJkvyK7t&export=download&confirm=t' "$STAGING/model/SCNet-large.th" 719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070 168848417 1073741824
download_verified 'https://drive.usercontent.google.com/download?id=1qxK7SZx6-Gsp1s3wCrj98X7--UcI4O3K&export=download&confirm=t' "$STAGING/model/scnet-large-config.yaml" 629a4901184bf1d3a75b0b13904f35974785aa042cad3c010fd576248cdce3f0 1080 1080
download_verified "$SOURCE_BASE/LICENSE" "$STAGING/TERMS/SCNet-LICENSE" 0bdf1b69335198118ab16cfc50d337b496b8c6d90e83beeaba4643781ab62513 1067 1067
download_verified "$SOURCE_BASE/README.md" "$STAGING/TERMS/SCNet-README.md" 5216a5b0ae85715f7eedbadda4d8d71dd063fb2bc40ba2a90cb61cf3458136dc 2031 2031
download_verified "$SOURCE_BASE/requirements.txt" "$STAGING/TERMS/SCNet-requirements.txt" 892a58352a75ee9d6cd98c68de9a4b6c733fb4f2e5788f3c6bd2b07676c2b66f 136 136
download_verified "$SOURCE_BASE/scnet/SCNet.py" "$STAGING/source/scnet/SCNet.py" 5e77c363f7f0187432a984d8ae1aa511826295d732372f0c280e68e4fecd4550 13853 13853
download_verified "$SOURCE_BASE/scnet/separation.py" "$STAGING/source/scnet/separation.py" 43402dc6579436d3b5abb921990572684beed8fa10b377a112892b438f40713b 3783 3783
cp "$RUNTIME_REQUIREMENTS" "$STAGING/TERMS/scnet-runtime-requirements.txt"
chmod 0444 "$STAGING/TERMS/scnet-runtime-requirements.txt"

"$RUNTIME_PYTHON" -m venv "$STAGING/runtime"
"$STAGING/runtime/bin/python" -m pip install \
    --disable-pip-version-check --no-cache-dir --require-hashes \
    -r "$RUNTIME_REQUIREMENTS"
"$STAGING/runtime/bin/python" -c 'import importlib.metadata as m; expected={"filelock":"3.32.2","fsspec":"2026.7.0","Jinja2":"3.1.6","MarkupSafe":"3.0.3","mpmath":"1.3.0","networkx":"3.6.1","numpy":"2.5.1","PyYAML":"6.0.3","setuptools":"83.0.0","sympy":"1.14.0","torch":"2.8.0","typing-extensions":"4.16.0"}; actual={name:m.version(name) for name in expected}; assert actual == expected'

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$STAGING/runtime/bin/python" "$INSPECT_SCRIPT" "$STAGING" \
    > "$STAGING/COMPATIBILITY.json"
"$STAGING/runtime/bin/python" - "$STAGING/COMPATIBILITY.json" <<'PY'
import json
from pathlib import Path
import sys

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert document["schema"] == "sunofriend.scnet-compatibility.v1"
assert document["status"] == "passed"
assert document["compatibility"]["strict_state_dict"] is True
assert document["effects"]["forward_passes"] == 0
assert document["effects"]["audio_reads"] == []
assert document["effects"]["inference_runs"] == 0
PY

compatibility_sha256=$(shasum -a 256 "$STAGING/COMPATIBILITY.json" | awk '{print $1}')
"$STAGING/runtime/bin/python" - "$STAGING/INSTALLATION.json" "$compatibility_sha256" <<'PY'
import json
from pathlib import Path
import sys

document = {
    "schema": "sunofriend.separation-installation.v1",
    "profile_id": "scnet-large-musdb-release-v1",
    "model_terms_accepted": True,
    "checkpoint_use_accepted": True,
    "model_revision": "google-drive:1s7QvQwn8ag9oVstGDBQ6KZvacJkvyK7t:sha256:719e5abb8ed920305dad546ac3cd6fb0b1e9c3092d14ce21827bfc0423af3070",
    "runtime_source_revision": "6236f8c559778dc271e1aea9baa3993ae655e905",
    "runtime_requirements_sha256": "692c8c5fb0606c70e60e559be60eac5ba1c439b652dc2df26174effd66acc508",
    "compatibility_receipt_sha256": sys.argv[2],
    "setup_download_bytes": 264851903,
    "upstream_model_resolution_enabled": False,
    "compatibility_network_denied": True,
    "inference_performed": False,
    "audio_processed": False,
    "profile_status_after_setup": "blocked_pending_worker_and_objective_canaries",
}
Path(sys.argv[1]).write_text(
    json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

chmod -R go-w "$STAGING"
mv "$STAGING" "$MODEL_ROOT"
STAGING=
trap - EXIT HUP INT TERM

echo ""
echo "SCNet compatibility setup complete: $MODEL_ROOT"
echo "The weights-only strict compatibility receipt passed under network denial."
echo "No forward pass, audio read or inference occurred."
echo "Public availability is controlled by the immutable profile registry and recorded objective evidence."
