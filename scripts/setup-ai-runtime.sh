#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
AI_ENV=${SUNOFRIEND_AI_ENV:-"$ROOT/.venv-ai"}

if ! command -v uv >/dev/null 2>&1; then
    echo "uv is required. On macOS run: brew install uv" >&2
    exit 1
fi

uv venv --no-project --python 3.12 --allow-existing "$AI_ENV"
uv pip install \
    --python "$AI_ENV/bin/python" \
    --strict \
    --requirements "$ROOT/requirements-ai-macos.txt"

"$AI_ENV/bin/python" - <<'PY'
import json
import platform
import sys

import torch

print(json.dumps({
    "python": sys.version.split()[0],
    "platform": platform.platform(),
    "torch": torch.__version__,
    "mps_built": torch.backends.mps.is_built(),
    "mps_available": torch.backends.mps.is_available(),
}, indent=2, sort_keys=True))
PY

echo "AI runtime ready at $AI_ENV"
echo "No gated or model-specific checkpoints were downloaded."
