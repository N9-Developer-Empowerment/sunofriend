#!/bin/sh
set -eu

PROFILE_ID=demucs-mlx-htdemucs-v1
MODEL_ID=mlx-community/demucs-mlx
MODEL_REVISION=d4519e24ddc2dd4a11d56a193092433d852c3961
RUNTIME_REVISION=b37e6ba3c5985af531f61c43564cf13c6ed349fd
DATA_ROOT=${SUNOFRIEND_SEPARATION_ROOT:-"$HOME/.local/share/sunofriend/separation"}
MODEL_ROOT=${SUNOFRIEND_SEPARATION_MODEL_ROOT:-"$DATA_ROOT/$PROFILE_ID"}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
BUILD_REQUIREMENTS="$REPOSITORY_ROOT/separation-core-four-build-requirements.txt"
RUNTIME_REQUIREMENTS="$REPOSITORY_ROOT/separation-core-four-runtime-requirements.txt"
ACTION=plan
ACCEPTED=false

usage() {
    echo "Usage: scripts/setup-separation-core-four-macos.sh [--plan | --install --accept-model-terms]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan) ACTION=plan ;;
        --install) ACTION=install ;;
        --accept-model-terms) ACCEPTED=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

echo "Sunofriend core-four experimental preview setup"
echo "Profile: $PROFILE_ID"
echo "Runtime: demucs-mlx 1.4.4 source $RUNTIME_REVISION"
echo "Runtime wheel SHA-256: dc40828b0a8591720082d2494696249790573d4ff6e5be72b16594e131b23e64"
echo "Model: $MODEL_ID htdemucs at $MODEL_REVISION"
echo "Weights SHA-256: 339d267a7a6983a11eedbdc00413c602a65e9b9103f695fb5c2b2a481cd9d297"
echo "Config SHA-256: 9258499513944fc062fbca0f11be425a446ec5702869a87e225323d7a57d2a01"
echo "Install root: $MODEL_ROOT"
echo "Download: about 230 MB plus a separate Python environment and build tools"
echo "Terms: pinned MIT runtime LICENSE and pinned model-card MIT metadata"
echo "Network during approved setup: pypi.org, files.pythonhosted.org, raw.githubusercontent.com, huggingface.co"
echo "Inference: explicit local cache, auto_convert=False, PyTorch-free, macOS network denial"
echo "Scope: opt-in vocals, drums, bass and grouped other; no automatic MIDI activation"
echo "Status: blocked after one baseline configuration and one failed remediation"
echo "Failure: pinned 39/5 segment remains a string inside HTDemucs training-length calculation"
echo "Next: qualify a separately pinned and approved fallback backend"

if [ "$ACTION" = plan ]; then
    echo ""
    echo "Plan only; nothing was installed or downloaded."
    echo "New installs are disabled because the objective remediation budget is exhausted."
    exit 0
fi

echo "Refusing a new install of the objectively failed demucs-mlx baseline; qualify the fallback backend" >&2
exit 2

if [ "$ACCEPTED" != true ]; then
    echo "--install requires --accept-model-terms after reviewing the identities and MIT evidence above" >&2
    exit 2
fi
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    echo "The first core-four preview supports macOS on Apple silicon only" >&2
    exit 2
fi
for command in curl shasum xcode-select; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "$command is required" >&2
        exit 2
    fi
done
if ! xcode-select -p >/dev/null 2>&1; then
    echo "Apple Command Line Tools are required to build pinned mlx-audio-io" >&2
    exit 2
fi
if [ -n "${SUNOFRIEND_SEPARATION_PYTHON_BIN:-}" ]; then
    PYTHON_BIN=$SUNOFRIEND_SEPARATION_PYTHON_BIN
elif command -v python3.13 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.13)
elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.12)
else
    echo "Python 3.12 or 3.13 is required" >&2
    exit 2
fi
case "$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" in
    3.12|3.13) ;;
    *) echo "Selected Python must be 3.12 or 3.13: $PYTHON_BIN" >&2; exit 2 ;;
esac
if [ -e "$MODEL_ROOT" ] || [ -L "$MODEL_ROOT" ]; then
    echo "Refusing to overwrite an existing profile root: $MODEL_ROOT" >&2
    exit 2
fi

mkdir -p "$DATA_ROOT"
STAGING=$(mktemp -d "$DATA_ROOT/.core-four.building.XXXXXX")
cleanup() {
    if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
        rm -rf "$STAGING"
    fi
}
trap cleanup EXIT HUP INT TERM
mkdir -p "$STAGING/model" "$STAGING/TERMS"

download_verified() {
    url=$1
    target=$2
    expected_hash=$3
    expected_bytes=$4
    temporary=$(mktemp "${TMPDIR:-/tmp}/sunofriend-core-four.XXXXXX")
    if ! curl --fail --location --retry 3 "$url" --output "$temporary"; then
        rm -f "$temporary"
        exit 2
    fi
    actual_bytes=$(wc -c < "$temporary" | tr -d ' ')
    if [ "$actual_bytes" != "$expected_bytes" ]; then
        echo "Downloaded byte count differs for $url" >&2
        rm -f "$temporary"
        exit 2
    fi
    echo "$expected_hash  $temporary" | shasum -a 256 -c - >/dev/null
    mv "$temporary" "$target"
    chmod 0644 "$target"
}

MODEL_BASE="https://huggingface.co/$MODEL_ID/resolve/$MODEL_REVISION"
RUNTIME_BASE="https://raw.githubusercontent.com/ssmall256/demucs-mlx/$RUNTIME_REVISION"
download_verified "$MODEL_BASE/htdemucs.safetensors" "$STAGING/model/htdemucs.safetensors" 339d267a7a6983a11eedbdc00413c602a65e9b9103f695fb5c2b2a481cd9d297 168005865
download_verified "$MODEL_BASE/htdemucs_config.json" "$STAGING/model/htdemucs_config.json" 9258499513944fc062fbca0f11be425a446ec5702869a87e225323d7a57d2a01 1892
download_verified "$MODEL_BASE/README.md" "$STAGING/TERMS/model-README.md" 1f9e7231385b9a8356dbe443c9707e9ada483027277ef0fd4154143f516570ab 3971
download_verified "$RUNTIME_BASE/LICENSE" "$STAGING/TERMS/demucs-mlx-LICENSE" 15086279d32c0f00c577c0f52ff428daf98b8a1fec0264da1c717c88ad464f51 1117
download_verified "$RUNTIME_BASE/pyproject.toml" "$STAGING/TERMS/demucs-mlx-pyproject.toml" 3758e87bc8b8d2755e27c764fc7c464def17cd6e2ccef58817689524534ffe36 1672

"$PYTHON_BIN" -m venv "$STAGING/runtime"
"$STAGING/runtime/bin/python" -m pip install --disable-pip-version-check --no-cache-dir --require-hashes -r "$BUILD_REQUIREMENTS"
"$STAGING/runtime/bin/python" -m pip install --disable-pip-version-check --no-cache-dir --no-build-isolation --require-hashes -r "$RUNTIME_REQUIREMENTS"
"$STAGING/runtime/bin/python" -c 'import importlib.metadata as m; expected={"demucs-mlx":"1.4.4","mlx":"0.31.2","mlx-audio-io":"1.3.11","mlx-metal":"0.31.2","mlx-spectro":"0.7.0","numpy":"2.3.5","packaging":"25.0","safetensors":"0.6.2","tqdm":"4.67.1"}; actual={name:m.version(name) for name in expected}; assert actual == expected; import importlib.util; assert importlib.util.find_spec("torch") is None'

printf '%s\n' \
    '{' \
    '  "schema": "sunofriend.separation-installation.v1",' \
    '  "profile_id": "demucs-mlx-htdemucs-v1",' \
    '  "model_terms_accepted": true,' \
    '  "model_revision": "d4519e24ddc2dd4a11d56a193092433d852c3961",' \
    '  "runtime_source_revision": "b37e6ba3c5985af531f61c43564cf13c6ed349fd",' \
    '  "runtime_wheel_sha256": "dc40828b0a8591720082d2494696249790573d4ff6e5be72b16594e131b23e64",' \
    '  "runtime_packages": {"demucs-mlx":"1.4.4","mlx":"0.31.2","mlx-audio-io":"1.3.11","mlx-metal":"0.31.2","mlx-spectro":"0.7.0","numpy":"2.3.5","packaging":"25.0","safetensors":"0.6.2","tqdm":"4.67.1"},' \
    '  "upstream_first_run_conversion_enabled": false,' \
    '  "inference_network_resolution_enabled": false' \
    '}' > "$STAGING/INSTALLATION.json"
chmod -R go-w "$STAGING"
mv "$STAGING" "$MODEL_ROOT"
STAGING=
trap - EXIT HUP INT TERM

echo ""
echo "Installation complete. Verify without loading the model:"
echo ".venv/bin/sunofriend-separate --model-root '$MODEL_ROOT' doctor --scope core-four-stems-v1"
echo "Public activation remains gated on the bounded canary record; musical usefulness scores are not an admission gate."
