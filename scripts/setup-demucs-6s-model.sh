#!/bin/sh
set -eu

PACKAGE_VERSION=4.0.1
MODEL_SIGNATURE=5c90dfd2
MODEL_VARIANT=htdemucs_6s
MODEL_FILENAME=5c90dfd2-34c22ccb.th
MODEL_BYTES=54996327
MODEL_SHA256=34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd
DATA_ROOT=${SUNOFRIEND_DATA_ROOT:-"$HOME/.local/share/sunofriend"}
MODEL_DIR=${SUNOFRIEND_DEMUCS_6S_MODEL_DIR:-"$DATA_ROOT/models/demucs-$PACKAGE_VERSION-htdemucs-6s"}
MODEL=${SUNOFRIEND_DEMUCS_6S_MODEL:-"$MODEL_DIR/$MODEL_FILENAME"}
CACHE_MODEL=${SUNOFRIEND_DEMUCS_6S_CACHE_MODEL:-"$HOME/.cache/torch/hub/checkpoints/$MODEL_FILENAME"}
URL="https://dl.fbaipublicfiles.com/demucs/hybrid_transformer/$MODEL_FILENAME"

if [ "${SUNOFRIEND_ACCEPT_DEMUCS_6S_PRIVATE_EVALUATION:-}" != "1" ]; then
    echo "Demucs code is MIT, but the official repository does not state separate" >&2
    echo "terms for its pretrained checkpoint. The six-source model is explicitly" >&2
    echo "experimental and its piano output has substantial bleed and artifacts." >&2
    echo "Sunofriend will use it only for private local evaluation and will never" >&2
    echo "redistribute it. Re-run with" >&2
    echo "SUNOFRIEND_ACCEPT_DEMUCS_6S_PRIVATE_EVALUATION=1 to accept." >&2
    exit 1
fi

for command in curl shasum stat; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "$command is required" >&2
        exit 1
    fi
done

verify_model() {
    actual_bytes=$(stat -f %z "$MODEL")
    if [ "$actual_bytes" != "$MODEL_BYTES" ]; then
        echo "Demucs six-source model byte count changed: expected $MODEL_BYTES, got $actual_bytes" >&2
        exit 1
    fi
    echo "$MODEL_SHA256  $MODEL" | shasum -a 256 -c -
}

if [ -f "$MODEL" ]; then
    verify_model
else
    if [ -e "$MODEL" ]; then
        echo "Demucs six-source model path exists but is not a file: $MODEL" >&2
        exit 1
    fi
    temporary=$(mktemp "${TMPDIR:-/tmp}/sunofriend-demucs-6s.XXXXXX")
    trap 'rm -f "$temporary"' EXIT HUP INT TERM
    if [ -f "$CACHE_MODEL" ]; then
        cp "$CACHE_MODEL" "$temporary"
    else
        curl --fail --location "$URL" --output "$temporary"
    fi
    actual_bytes=$(stat -f %z "$temporary")
    if [ "$actual_bytes" != "$MODEL_BYTES" ]; then
        echo "Downloaded model byte count changed: expected $MODEL_BYTES, got $actual_bytes" >&2
        exit 1
    fi
    echo "$MODEL_SHA256  $temporary" | shasum -a 256 -c -
    mkdir -p "$(dirname "$MODEL")"
    chmod 700 "$(dirname "$MODEL")"
    chmod 600 "$temporary"
    mv "$temporary" "$MODEL"
    trap - EXIT HUP INT TERM
    verify_model
fi

echo "Demucs package: demucs==$PACKAGE_VERSION"
echo "Demucs model: $MODEL_VARIANT/$MODEL_SIGNATURE"
echo "Demucs checkpoint: $MODEL"
echo "Private local evaluation only; do not vendor or redistribute the checkpoint."
echo "This installer does not enable a CLI, TUI, Studio or Simple separator."
