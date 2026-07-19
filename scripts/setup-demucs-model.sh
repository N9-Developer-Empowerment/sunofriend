#!/bin/sh
set -eu

PACKAGE_VERSION=4.0.1
MODEL_SIGNATURE=955717e8
MODEL_FILENAME=955717e8-8726e21a.th
MODEL_SHA256=8726e21a993978c7ba086d3872e7608d7d5bfca646ca4aca459ffda844faa8b4
DATA_ROOT=${SUNOFRIEND_DATA_ROOT:-"$HOME/.local/share/sunofriend"}
MODEL_DIR=${SUNOFRIEND_DEMUCS_MODEL_DIR:-"$DATA_ROOT/models/demucs-$PACKAGE_VERSION-htdemucs"}
MODEL=${SUNOFRIEND_DEMUCS_MODEL:-"$MODEL_DIR/$MODEL_FILENAME"}
CACHE_MODEL=${SUNOFRIEND_DEMUCS_CACHE_MODEL:-"$HOME/.cache/torch/hub/checkpoints/$MODEL_FILENAME"}
URL="https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/$MODEL_FILENAME"

if [ "${SUNOFRIEND_ACCEPT_DEMUCS_PRIVATE_EVALUATION:-}" != "1" ]; then
    echo "Demucs code is MIT, but the official repository does not state separate" >&2
    echo "terms for its pretrained checkpoint. Sunofriend therefore uses this" >&2
    echo "checkpoint only for private local evaluation and never redistributes it." >&2
    echo "Re-run with SUNOFRIEND_ACCEPT_DEMUCS_PRIVATE_EVALUATION=1 to accept." >&2
    exit 1
fi

for command in curl shasum; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "$command is required" >&2
        exit 1
    fi
done

verify_model() {
    echo "$MODEL_SHA256  $MODEL" | shasum -a 256 -c -
}

if [ -f "$MODEL" ]; then
    verify_model
else
    if [ -e "$MODEL" ]; then
        echo "Demucs model path exists but is not a file: $MODEL" >&2
        exit 1
    fi
    temporary=$(mktemp "${TMPDIR:-/tmp}/sunofriend-demucs.XXXXXX")
    trap 'rm -f "$temporary"' EXIT HUP INT TERM
    if [ -f "$CACHE_MODEL" ]; then
        cp "$CACHE_MODEL" "$temporary"
    else
        curl --fail --location "$URL" --output "$temporary"
    fi
    echo "$MODEL_SHA256  $temporary" | shasum -a 256 -c -
    mkdir -p "$(dirname "$MODEL")"
    mv "$temporary" "$MODEL"
    trap - EXIT HUP INT TERM
    verify_model
fi

echo "Demucs package: demucs==$PACKAGE_VERSION"
echo "Demucs model: htdemucs/$MODEL_SIGNATURE"
echo "Demucs checkpoint: $MODEL"
echo "Private local evaluation only; do not vendor or redistribute the checkpoint."
echo "Run scripts/setup-ai-runtime.sh, then:"
echo ".venv/bin/sunofriend ai-doctor --require demucs"
