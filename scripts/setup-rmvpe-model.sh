#!/bin/sh
set -eu

PACKAGE_VERSION=0.2.3
MODEL_REVISION=b2c8cae96e3b05de46d36c5ef9970ef6cbccafba
MODEL_SHA256=5370e71ac80af8b4b7c793d27efd51fd8bf962de3a7ede0766dac0befa3660fd
DATA_ROOT=${SUNOFRIEND_DATA_ROOT:-"$HOME/.local/share/sunofriend"}
MODEL_DIR=${SUNOFRIEND_RMVPE_MODEL_DIR:-"$DATA_ROOT/models/rmvpe-onnx-$PACKAGE_VERSION"}
MODEL=${SUNOFRIEND_RMVPE_MODEL:-"$MODEL_DIR/rmvpe.onnx"}
URL="https://huggingface.co/lj1995/VoiceConversionWebUI/resolve/$MODEL_REVISION/rmvpe.onnx"

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
        echo "RMVPE model path exists but is not a file: $MODEL" >&2
        exit 1
    fi
    temporary=$(mktemp "${TMPDIR:-/tmp}/sunofriend-rmvpe.XXXXXX")
    trap 'rm -f "$temporary"' EXIT HUP INT TERM
    curl --fail --location "$URL" --output "$temporary"
    echo "$MODEL_SHA256  $temporary" | shasum -a 256 -c -
    mkdir -p "$(dirname "$MODEL")"
    mv "$temporary" "$MODEL"
    trap - EXIT HUP INT TERM
    verify_model
fi

echo "RMVPE package: rmvpe-onnx==$PACKAGE_VERSION"
echo "RMVPE model revision: $MODEL_REVISION"
echo "RMVPE ONNX model: $MODEL"
echo "Run scripts/setup-ai-runtime.sh, then:"
echo ".venv/bin/sunofriend ai-doctor --require rmvpe"
