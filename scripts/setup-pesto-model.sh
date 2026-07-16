#!/bin/sh
set -eu

PACKAGE_VERSION=2.0.1
MODEL_REVISION=62bc0c9702558f19af4593752947fb9db1eadac9
MODEL_SHA256=16c32e06ddd950e3e4866dfa3c7f8a87c4988f8adf43e57977b189f031f26f3e
DATA_ROOT=${SUNOFRIEND_DATA_ROOT:-"$HOME/.local/share/sunofriend"}
MODEL_DIR=${SUNOFRIEND_PESTO_MODEL_DIR:-"$DATA_ROOT/models/pesto-pitch-$PACKAGE_VERSION"}
MODEL=${SUNOFRIEND_PESTO_MODEL:-"$MODEL_DIR/mir-1k_g7.ckpt"}
URL="https://raw.githubusercontent.com/SonyCSLParis/pesto/$MODEL_REVISION/pesto/weights/mir-1k_g7.ckpt"

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
        echo "PESTO model path exists but is not a file: $MODEL" >&2
        exit 1
    fi
    temporary=$(mktemp "${TMPDIR:-/tmp}/sunofriend-pesto.XXXXXX")
    trap 'rm -f "$temporary"' EXIT HUP INT TERM
    curl --fail --location "$URL" --output "$temporary"
    echo "$MODEL_SHA256  $temporary" | shasum -a 256 -c -
    mkdir -p "$(dirname "$MODEL")"
    mv "$temporary" "$MODEL"
    trap - EXIT HUP INT TERM
    verify_model
fi

echo "PESTO package: pesto-pitch==$PACKAGE_VERSION"
echo "PESTO model revision: $MODEL_REVISION"
echo "PESTO checkpoint: $MODEL"
echo "Run scripts/setup-ai-runtime.sh, then:"
echo ".venv/bin/sunofriend ai-doctor --require pesto"
