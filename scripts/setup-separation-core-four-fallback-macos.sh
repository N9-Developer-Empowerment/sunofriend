#!/bin/sh
set -eu

PROFILE_ID=demucs-infer-htdemucs-fallback-v1
RUNTIME_REVISION=4b79d5c756ce298503d90b0cca2abbc76c565416
MODEL_REVISION=955717e8-8726e21a
DATA_ROOT=${SUNOFRIEND_SEPARATION_ROOT:-"$HOME/.local/share/sunofriend/separation"}
MODEL_ROOT=${SUNOFRIEND_SEPARATION_MODEL_ROOT:-"$DATA_ROOT/$PROFILE_ID"}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
RUNTIME_REQUIREMENTS="$REPOSITORY_ROOT/separation-core-four-fallback-runtime-requirements.txt"
ACTION=plan
ACCEPTED=false

usage() {
    echo "Usage: scripts/setup-separation-core-four-fallback-macos.sh [--plan | --install --accept-model-terms]"
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

echo "Sunofriend core-four fallback setup"
echo "Profile: $PROFILE_ID (blocked; objective remediation exhausted)"
echo "Runtime: demucs-infer 4.2.2 source $RUNTIME_REVISION"
echo "Runtime wheel SHA-256: df07b115690021dcfa6b2a6de1b7b352741111bc46fad31ca83eaaba6afced8b"
echo "Runtime closure: 20 exact Apple-arm64/Python 3.13 wheels, including torch and torchaudio 2.8.0"
echo "Setup remediation: the first approved 19-wheel install stopped safely because Torch required setuptools"
echo "Added dependency: setuptools 83.0.0, MIT, 1008090-byte wheel"
echo "Added wheel SHA-256: 29b23c360f22f414dc7336bb39178cc7bcbf6021ed2733cde173f09dba19abb3"
echo "Remediation boundary: this revised closure is the one fallback remediation; another objective failure stops retries"
echo "Model: single htdemucs checkpoint $MODEL_REVISION"
echo "Weights SHA-256: 8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4"
echo "Weights bytes: 84141911"
echo "Install root: $MODEL_ROOT"
echo "Download: about 184 MB plus a separate Python environment"
echo "Terms: pinned demucs-infer repository declares MIT and identifies unchanged original Demucs weights; no contradictory weight restriction was found"
echo "Known terms limitation: the original checkpoint has no separate model-specific licence file"
echo "Network during approved setup: pypi.org, files.pythonhosted.org, raw.githubusercontent.com, dl.fbaipublicfiles.com"
echo "Inference: explicit local repo and network denial passed doctor; native Fraction segment failed the worker contract before inference"
echo "Device: Apple-arm64 CPU baseline; performance and 16 GiB resource qualification remain objective activation gates"
echo "Scope: opt-in vocals, drums, bass and grouped other; no automatic MIDI activation"
echo "Status: blocked after the revised install passed doctor but the synthetic worker failed before publication"
echo "Failure: loaded native segment is Fraction(39, 5), rejected by the pinned worker's int/float contract"
echo "Next: select a separately reviewed backend; do not reinstall or retry this profile"

if [ "$ACTION" = plan ]; then
    echo ""
    echo "Plan only; nothing was installed or downloaded."
    echo "New installs are disabled because the objective remediation budget is exhausted."
    exit 0
fi

echo "Refusing a new install of the objectively failed demucs-infer fallback; select a new reviewed backend" >&2
exit 2

if [ "$ACCEPTED" != true ]; then
    echo "--install requires --accept-model-terms after reviewing the exact identities and terms limitation above" >&2
    exit 2
fi
if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    echo "The first core-four fallback supports macOS on Apple silicon only" >&2
    exit 2
fi
for required_command in curl shasum; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        echo "$required_command is required" >&2
        exit 2
    fi
done
if [ -n "${SUNOFRIEND_SEPARATION_PYTHON_BIN:-}" ]; then
    PYTHON_BIN=$SUNOFRIEND_SEPARATION_PYTHON_BIN
elif command -v python3.13 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.13)
else
    echo "Python 3.13 is required for the exact fallback wheel lock" >&2
    exit 2
fi
if [ "$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" != 3.13 ]; then
    echo "Selected fallback Python must be 3.13: $PYTHON_BIN" >&2
    exit 2
fi
if [ -e "$MODEL_ROOT" ] || [ -L "$MODEL_ROOT" ]; then
    echo "Refusing to overwrite an existing profile root: $MODEL_ROOT" >&2
    exit 2
fi

mkdir -p "$DATA_ROOT"
STAGING=$(mktemp -d "$DATA_ROOT/.core-four-fallback.building.XXXXXX")
cleanup() {
    if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
        rm -rf "$STAGING"
    fi
}
trap cleanup EXIT HUP INT TERM
mkdir -p "$STAGING/model" "$STAGING/TERMS"

download_verified() {
    download_url=$1
    download_target=$2
    expected_hash=$3
    expected_bytes=$4
    temporary=$(mktemp "${TMPDIR:-/tmp}/sunofriend-core-four-fallback.XXXXXX")
    if ! curl --fail --location --retry 3 "$download_url" --output "$temporary"; then
        rm -f "$temporary"
        exit 2
    fi
    actual_bytes=$(wc -c < "$temporary" | tr -d ' ')
    if [ "$actual_bytes" != "$expected_bytes" ]; then
        echo "Downloaded byte count differs for $download_url" >&2
        rm -f "$temporary"
        exit 2
    fi
    echo "$expected_hash  $temporary" | shasum -a 256 -c - >/dev/null
    mv "$temporary" "$download_target"
    chmod 0644 "$download_target"
}

SOURCE_BASE="https://raw.githubusercontent.com/openmirlab/demucs-infer/$RUNTIME_REVISION"
download_verified "https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/955717e8-8726e21a.th" "$STAGING/model/955717e8-8726e21a.th" 8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4 84141911
download_verified "$SOURCE_BASE/demucs_infer/remote/htdemucs.yaml" "$STAGING/model/htdemucs.yaml" 239c445d0b14454d541ad8bd9bb271c9e536d267e8a4625208744cbb2e7bb66c 21
download_verified "$SOURCE_BASE/LICENSE" "$STAGING/TERMS/demucs-infer-LICENSE" 761f67137c6e733d551b8ed1111e48e267e032c2c0fb0df07127cf55ddbeef5b 1400
download_verified "$SOURCE_BASE/README.md" "$STAGING/TERMS/demucs-infer-README.md" ace60d8646c7b74e6f631a4ed635ba9a2894e48e24490df0501e2e6b51cfd0a4 23660
download_verified "$SOURCE_BASE/pyproject.toml" "$STAGING/TERMS/demucs-infer-pyproject.toml" ad3e58df8469056f030cddc00f61be64dcffcaec3a3dcd03da2f100fde154aa8 3560
download_verified "$SOURCE_BASE/docs/checkpoints_provenance.json" "$STAGING/TERMS/checkpoints-provenance.json" e209056d816cdc8f91be9cfdf9c1883aec9e34f739fc4278de2ebb60d58e5b75 7467

"$PYTHON_BIN" -m venv "$STAGING/runtime"
"$STAGING/runtime/bin/python" -m pip install --disable-pip-version-check --no-cache-dir --require-hashes -r "$RUNTIME_REQUIREMENTS"
"$STAGING/runtime/bin/python" -c 'import importlib.metadata as m; expected={"cffi":"2.1.1","demucs-infer":"4.2.2","einops":"0.8.2","filelock":"3.32.2","fsspec":"2026.7.0","Jinja2":"3.1.6","julius":"0.2.8","MarkupSafe":"3.0.3","mpmath":"1.3.0","networkx":"3.6.1","numpy":"2.5.1","pycparser":"3.0","PyYAML":"6.0.3","setuptools":"83.0.0","soundfile":"0.14.0","sympy":"1.14.0","torch":"2.8.0","torchaudio":"2.8.0","tqdm":"4.70.0","typing-extensions":"4.16.0"}; actual={name:m.version(name) for name in expected}; assert actual == expected'

printf '%s\n' \
    '{' \
    '  "schema": "sunofriend.separation-installation.v1",' \
    '  "profile_id": "demucs-infer-htdemucs-fallback-v1",' \
    '  "model_terms_accepted": true,' \
    '  "model_revision": "955717e8-8726e21a",' \
    '  "runtime_source_revision": "4b79d5c756ce298503d90b0cca2abbc76c565416",' \
    '  "runtime_wheel_sha256": "df07b115690021dcfa6b2a6de1b7b352741111bc46fad31ca83eaaba6afced8b",' \
    '  "setup_remediation_cycles": 1,' \
    '  "runtime_packages": {"cffi":"2.1.1","demucs-infer":"4.2.2","einops":"0.8.2","filelock":"3.32.2","fsspec":"2026.7.0","Jinja2":"3.1.6","julius":"0.2.8","MarkupSafe":"3.0.3","mpmath":"1.3.0","networkx":"3.6.1","numpy":"2.5.1","pycparser":"3.0","PyYAML":"6.0.3","setuptools":"83.0.0","soundfile":"0.14.0","sympy":"1.14.0","torch":"2.8.0","torchaudio":"2.8.0","tqdm":"4.70.0","typing-extensions":"4.16.0"},' \
    '  "upstream_first_run_conversion_enabled": false,' \
    '  "inference_network_resolution_enabled": false' \
    '}' > "$STAGING/INSTALLATION.json"
chmod -R go-w "$STAGING"
mv "$STAGING" "$MODEL_ROOT"
STAGING=
trap - EXIT HUP INT TERM

echo ""
echo "Installation complete. The profile remains blocked pending doctor and finite objective canaries."
echo ".venv/bin/sunofriend-separate --model-root '$MODEL_ROOT' doctor --scope core-four-stems-v1"
