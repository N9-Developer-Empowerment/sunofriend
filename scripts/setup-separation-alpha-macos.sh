#!/bin/sh
set -eu

MODEL_ID=mlx-community/mel-roformer-kim-vocal-2-mlx
MODEL_REVISION=64cbfcb004e39430e5f584552c05949440ec39ce
SOURCE_REVISION=41092c02db18efd5b9d8281b2fcc41d84801757a
PROFILE_NAME=kim-vocal-2-mlx-v1
DATA_ROOT=${SUNOFRIEND_SEPARATION_ROOT:-"$HOME/.local/share/sunofriend/separation"}
MODEL_ROOT=${SUNOFRIEND_SEPARATION_MODEL_ROOT:-"$DATA_ROOT/$PROFILE_NAME"}
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REQUIREMENTS="$REPOSITORY_ROOT/separation-runtime-requirements.txt"
ACTION=plan
ACCEPTED=false

usage() {
    echo "Usage: scripts/setup-separation-alpha-macos.sh [--plan | --install --accept-model-terms]"
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

echo "Sunofriend experimental separation setup"
echo "Platform: macOS 14+ on Apple silicon"
echo "Profile: $MODEL_ID at $MODEL_REVISION"
echo "Install root: $MODEL_ROOT"
echo "Download: about 500 MB plus a separate Python environment"
echo "Terms: MIT model card and LICENSE at https://huggingface.co/$MODEL_ID"
echo "Privacy: setup downloads public software/model files; later inference is local and offline"
echo "Scope: broad vocals plus complementary instrumental, experimental and human-reviewed"

if [ "$ACTION" = plan ]; then
    echo ""
    echo "Plan only; nothing was installed."
    echo "To proceed: scripts/setup-separation-alpha-macos.sh --install --accept-model-terms"
    exit 0
fi

if [ "$ACCEPTED" != true ]; then
    echo "--install requires --accept-model-terms after reading the linked MIT terms" >&2
    exit 2
fi

if [ "$(uname -s)" != Darwin ] || [ "$(uname -m)" != arm64 ]; then
    echo "This first public alpha supports macOS on Apple silicon only" >&2
    exit 2
fi

for command in curl shasum; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "$command is required" >&2
        exit 2
    fi
done

if [ -n "${SUNOFRIEND_SEPARATION_PYTHON_BIN:-}" ]; then
    PYTHON_BIN=$SUNOFRIEND_SEPARATION_PYTHON_BIN
elif command -v python3.13 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.13)
elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.12)
else
    echo "Python 3.12 or 3.13 is required. Let your coding agent or Homebrew install one, then rerun this command." >&2
    exit 2
fi

case "$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" in
    3.12|3.13) ;;
    *) echo "Selected Python must be 3.12 or 3.13: $PYTHON_BIN" >&2; exit 2 ;;
esac

mkdir -p "$MODEL_ROOT/mlx-audio-source/mlx_audio/sts/models/mel_roformer"
mkdir -p "$MODEL_ROOT/checkpoint-directory"

download_verified() {
    url=$1
    target=$2
    expected_hash=$3
    expected_bytes=$4
    if [ -L "$target" ]; then
        echo "Refusing symbolic-link target: $target" >&2
        exit 2
    fi
    if [ -f "$target" ]; then
        actual_bytes=$(wc -c < "$target" | tr -d ' ')
        if [ "$actual_bytes" != "$expected_bytes" ] || ! echo "$expected_hash  $target" | shasum -a 256 -c - >/dev/null 2>&1; then
            echo "Existing file has the wrong identity: $target" >&2
            exit 2
        fi
        echo "Verified existing $(basename "$target")"
        return
    fi
    if [ -e "$target" ]; then
        echo "Target exists but is not a regular file: $target" >&2
        exit 2
    fi
    temporary=$(mktemp "${TMPDIR:-/tmp}/sunofriend-separation.XXXXXX")
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
    echo "Installed $(basename "$target")"
}

SOURCE_BASE="https://raw.githubusercontent.com/Blaizzy/mlx-audio/$SOURCE_REVISION"
download_verified "$SOURCE_BASE/LICENSE" "$MODEL_ROOT/mlx-audio-source/LICENSE" 11d27e0259dec3a323fa6c04c330621d0950ab96c6760d5aac3e2e97229e6f22 1070
download_verified "$SOURCE_BASE/mlx_audio/__init__.py" "$MODEL_ROOT/mlx-audio-source/mlx_audio/__init__.py" 073f6435c675ac1d88884b6dcff150604f217a25cfe12f4fcba2ce23ef82d3b5 156
download_verified "$SOURCE_BASE/mlx_audio/dsp.py" "$MODEL_ROOT/mlx-audio-source/mlx_audio/dsp.py" 356ac7aca294d79983b56dc52f13c970c631a0ba029ac0283987c585cacff85b 30091
download_verified "$SOURCE_BASE/mlx_audio/sts/models/mel_roformer/config.py" "$MODEL_ROOT/mlx-audio-source/mlx_audio/sts/models/mel_roformer/config.py" 71773eb206e131d66c5d477d0ccb06973b647a949a20b4f1a8304c9127bd726b 6379
download_verified "$SOURCE_BASE/mlx_audio/sts/models/mel_roformer/model.py" "$MODEL_ROOT/mlx-audio-source/mlx_audio/sts/models/mel_roformer/model.py" 5ddf498eb247155e5dc5dfc63c5237458b2793bb55d9844fe01c43b81cf3cd10 27983
download_verified "$SOURCE_BASE/pyproject.toml" "$MODEL_ROOT/mlx-audio-source/pyproject.toml" d0b03193d3cba35e8a9de6fe538d6244dcec35c59049f90e9a63e61d63909cae 2790

MODEL_BASE="https://huggingface.co/$MODEL_ID/resolve/$MODEL_REVISION"
download_verified "$MODEL_BASE/config.json" "$MODEL_ROOT/checkpoint-directory/config.json" 3300eacac960ab46933ef6df6b838eb35de1f0321db9242c1b06e6d2a6a62b58 833
download_verified "$MODEL_BASE/LICENSE" "$MODEL_ROOT/checkpoint-directory/LICENSE" 1aa245b55067df5c63c847894e7040f76fa79ddde83e9e5ed8a5c29ef1865c14 1500
download_verified "$MODEL_BASE/model.safetensors" "$MODEL_ROOT/model.safetensors" 312c38e5b698f8dfaa4d6064e8f79010744825828917871a9d22673a43eb7fe5 456483463

if [ ! -x "$MODEL_ROOT/runtime/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$MODEL_ROOT/runtime"
fi
"$MODEL_ROOT/runtime/bin/python" -m pip install --disable-pip-version-check --only-binary=:all: --require-hashes -r "$REQUIREMENTS"

echo ""
echo "Installation complete. Verify without loading the model:"
echo ".venv/bin/sunofriend-separate doctor"
echo "Then read docs/STEM_SEPARATION_ALPHA.md before processing audio."
