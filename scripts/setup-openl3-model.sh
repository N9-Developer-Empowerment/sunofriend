#!/bin/sh
set -eu

MODEL_NAME=openl3-music-mel128-emb512-3
MODEL_SHA256=81c24c8a723054717fdea5c7448acb6023baaf70a0fc526deb030c2032db0ed3
DATA_ROOT=${SUNOFRIEND_DATA_ROOT:-"$HOME/.local/share/sunofriend"}
MODEL_DIR=${SUNOFRIEND_OPENL3_MODEL_DIR:-"$DATA_ROOT/models/$MODEL_NAME"}
MODEL=${SUNOFRIEND_OPENL3_MODEL:-"$MODEL_DIR/$MODEL_NAME.onnx"}
URL="https://essentia.upf.edu/models/feature-extractors/openl3/$MODEL_NAME.onnx"

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
        echo "OpenL3 model path exists but is not a file: $MODEL" >&2
        exit 1
    fi
    temporary=$(mktemp "${TMPDIR:-/tmp}/sunofriend-openl3.XXXXXX")
    trap 'rm -f "$temporary"' EXIT HUP INT TERM
    curl --fail --location "$URL" --output "$temporary"
    echo "$MODEL_SHA256  $temporary" | shasum -a 256 -c -
    mkdir -p "$(dirname "$MODEL")"
    mv "$temporary" "$MODEL"
    trap - EXIT HUP INT TERM
    verify_model
fi

echo "OpenL3 model weights: CC-BY-4.0"
echo "OpenL3 ONNX model: $MODEL"
echo "Use it explicitly with:"
echo ".venv/bin/sunofriend instrument-match STEM.wav ALIGNED.mid --kind bass --out-dir OUTPUT --embedding-model \"$MODEL\""
