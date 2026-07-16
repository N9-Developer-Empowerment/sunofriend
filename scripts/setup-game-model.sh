#!/bin/sh
set -eu

VERSION=1.0.3
TAG="v$VERSION"
COMMIT=475a8ee781fe8cca980b3b12fbe6c80c768a813a
ASSET="GAME-$VERSION-small-onnx.zip"
ASSET_SHA256=00ba0c64115b6b874d9ea4afd3e6cf822abda2a04e52569233b0a044fd40e4e8
DATA_ROOT=${SUNOFRIEND_DATA_ROOT:-"$HOME/.local/share/sunofriend"}
CHECKOUT=${SUNOFRIEND_GAME_HOME:-"$DATA_ROOT/checkouts/GAME-$TAG"}
MODEL_PARENT=${SUNOFRIEND_GAME_MODEL_PARENT:-"$DATA_ROOT/models/game-$VERSION-small-onnx"}
BUNDLE="$MODEL_PARENT/GAME-$VERSION-small-onnx"
URL="https://github.com/openvpi/GAME/releases/download/$TAG/$ASSET"

for command in curl git shasum unzip; do
    if ! command -v "$command" >/dev/null 2>&1; then
        echo "$command is required" >&2
        exit 1
    fi
done

if [ -d "$CHECKOUT/.git" ]; then
    actual_commit=$(git -C "$CHECKOUT" rev-parse HEAD)
    if [ "$actual_commit" != "$COMMIT" ]; then
        echo "Existing GAME checkout is not the pinned $TAG commit: $CHECKOUT" >&2
        exit 1
    fi
else
    if [ -e "$CHECKOUT" ]; then
        echo "GAME checkout path exists but is not a Git checkout: $CHECKOUT" >&2
        exit 1
    fi
    mkdir -p "$(dirname "$CHECKOUT")"
    git clone --depth 1 --branch "$TAG" https://github.com/openvpi/GAME.git "$CHECKOUT"
    actual_commit=$(git -C "$CHECKOUT" rev-parse HEAD)
    if [ "$actual_commit" != "$COMMIT" ]; then
        echo "Downloaded GAME checkout did not match pinned commit $COMMIT" >&2
        exit 1
    fi
fi

verify_bundle() {
    (
        cd "$BUNDLE"
        shasum -a 256 -c <<'EOF'
60dfe7e7b57db29475604eeea9b2abf5f8cd2a49326f1f4bc0e1c14ed151a55e  config.json
a6868a702d9c88ccc06b19e54f49d88b7f8cba4a68517f20806bd81ef6f94e06  encoder.onnx
7724db4ba59a388fff5aba2f08f0ac025d4ca59caef80e7f474053a1455c88e5  segmenter.onnx
a84738b2504472a1f22773cc6b0eccad1353a8f36229ad490b8fea85388bb5e1  estimator.onnx
49d10d1ea186e43c51fd2c51cedb01a3852d363f1c7056ae77df50f7e8dd0996  dur2bd.onnx
6672d56b00f27a20e9bfaa92801c15e394bb520e49031d3ed2515b0a6cf27402  bd2dur.onnx
EOF
    )
}

if [ -d "$BUNDLE" ]; then
    verify_bundle
else
    temporary=$(mktemp -d "${TMPDIR:-/tmp}/sunofriend-game.XXXXXX")
    trap 'rm -rf "$temporary"' EXIT HUP INT TERM
    curl --fail --location "$URL" --output "$temporary/$ASSET"
    echo "$ASSET_SHA256  $temporary/$ASSET" | shasum -a 256 -c -
    mkdir -p "$MODEL_PARENT"
    unzip -q "$temporary/$ASSET" -d "$MODEL_PARENT"
    verify_bundle
fi

echo "GAME checkout: $CHECKOUT"
echo "GAME ONNX bundle: $BUNDLE"
echo "Run scripts/setup-ai-runtime.sh, then:"
echo ".venv/bin/sunofriend ai-doctor --require game"
