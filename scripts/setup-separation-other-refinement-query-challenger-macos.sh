#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PLAN_SCRIPT="$REPOSITORY_ROOT/scripts/plan-separation-other-refinement-query-challenger.py"
INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-other-refinement-query-checkpoint.py"
DATA_ROOT=${SUNOFRIEND_SEPARATION_ROOT:-"$HOME/.local/share/sunofriend/separation"}
EVIDENCE_ROOT=${SUNOFRIEND_QUERY_CHALLENGER_EVIDENCE_ROOT:-"$DATA_ROOT/evidence/query-bandit-ev-pre-aug-v1"}
ACTION=plan
ACCEPTED_TERMS=false
ACCEPTED_CHECKPOINT_USE=false
EXPECTED_BYTES=645470187
MAX_BYTES=734003200
EXPECTED_MD5=4dfb91d6d27c2dfd4992a15070915541
CHECKPOINT_URL='https://zenodo.org/api/records/13694558/files/ev-pre-aug.ckpt/content'

usage() {
    echo "Usage: scripts/setup-separation-other-refinement-query-challenger-macos.sh [--plan | --evidence-only --accept-model-terms --accept-checkpoint-use]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan) ACTION=plan ;;
        --evidence-only) ACTION=evidence-only ;;
        --accept-model-terms) ACCEPTED_TERMS=true ;;
        --accept-checkpoint-use) ACCEPTED_CHECKPOINT_USE=true ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
    shift
done

if [ -x "$REPOSITORY_ROOT/.venv/bin/python" ]; then
    PLAN_PYTHON="$REPOSITORY_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PLAN_PYTHON=$(command -v python3)
else
    echo "Python 3 is required for the evidence-only inspector" >&2
    exit 2
fi

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    "$PLAN_PYTHON" -B "$PLAN_SCRIPT"
if [ "$ACTION" = plan ]; then
    echo ""
    echo "Plan only; nothing was downloaded, installed, loaded or executed."
    exit 0
fi

if [ "$ACCEPTED_TERMS" != true ] || [ "$ACCEPTED_CHECKPOINT_USE" != true ]; then
    echo "--evidence-only requires both acceptance flags after reviewing the plan" >&2
    exit 2
fi
for required_command in curl sandbox-exec; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        echo "$required_command is required" >&2
        exit 2
    fi
done
if [ -e "$EVIDENCE_ROOT" ] || [ -L "$EVIDENCE_ROOT" ]; then
    echo "Refusing to overwrite existing query-checkpoint evidence: $EVIDENCE_ROOT" >&2
    exit 2
fi

EVIDENCE_PARENT=$(dirname "$EVIDENCE_ROOT")
mkdir -p "$EVIDENCE_PARENT"
STAGING=$(mktemp -d "$EVIDENCE_PARENT/.query-bandit-ev-pre-aug-v1.building.XXXXXX")
preserve_failed_staging() {
    query_exit_code=$?
    if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
        failed_root="$EVIDENCE_PARENT/query-bandit-ev-pre-aug-v1.failed.$$.evidence"
        if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
            chmod -R go-w "$STAGING" 2>/dev/null || true
            mv "$STAGING" "$failed_root"
            STAGING=
            echo "Preserved failed evidence staging: $failed_root" >&2
        fi
    fi
    exit "$query_exit_code"
}
trap preserve_failed_staging EXIT HUP INT TERM

CHECKPOINT="$STAGING/ev-pre-aug.ckpt"
(
    ulimit -f 1433600
    curl --fail --location --retry 3 --silent --show-error \
        --proto '=https' --tlsv1.2 --max-filesize "$MAX_BYTES" \
        "$CHECKPOINT_URL" --output "$CHECKPOINT"
)
ACTUAL_BYTES=$(wc -c < "$CHECKPOINT" | tr -d ' ')
if [ "$ACTUAL_BYTES" != "$EXPECTED_BYTES" ]; then
    echo "Banquet checkpoint byte count differs: $ACTUAL_BYTES" >&2
    exit 2
fi
chmod 0444 "$CHECKPOINT"

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$PLAN_PYTHON" -B "$INSPECT_SCRIPT" "$CHECKPOINT" \
    > "$STAGING/STATIC-EVIDENCE.json"

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    "$PLAN_PYTHON" -B - "$STAGING/STATIC-EVIDENCE.json" "$STAGING/APPROVAL-RECEIPT.json" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sunofriend.separation_other_refinement_query_evidence import (
    validate_query_checkpoint_evidence,
)

evidence_path = Path(sys.argv[1])
receipt_path = Path(sys.argv[2])
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
validate_query_checkpoint_evidence(evidence)
assert evidence["checkpoint"]["bytes"] == 645_470_187
assert evidence["checkpoint"]["observed_md5"] == "4dfb91d6d27c2dfd4992a15070915541"
assert evidence["effects"]["checkpoint_deserialized"] is False
assert evidence["effects"]["model_imported"] is False
assert evidence["effects"]["inference_runs"] == 0
assert evidence["effects"]["audio_reads"] == 0
receipt = {
    "schema": "sunofriend.other-refinement-query-evidence-approval.v1",
    "status": "evidence_only_complete_no_runtime_authority",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "profile_id": "query-bandit-ev-pre-aug-v1",
    "checkpoint_evidence_sha256": evidence["evidence_sha256"],
    "model_terms_acknowledged": "CC-BY-NC-SA-4.0 noncommercial boundary",
    "checkpoint_use_approved": "capped evidence-only download and static inspection",
    "network_denied_during_static_inspection": True,
    "not_approved": [
        "dependency_installation",
        "model_loading",
        "inference",
        "song_processing",
        "public_activation",
        "source_selection",
        "midi",
    ],
}
receipt_path.write_text(
    json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
)
PY

chmod 0444 "$STAGING/STATIC-EVIDENCE.json" "$STAGING/APPROVAL-RECEIPT.json"
chmod -R go-w "$STAGING"
mv "$STAGING" "$EVIDENCE_ROOT"
STAGING=
trap - EXIT HUP INT TERM

echo ""
echo "Evidence-only checkpoint cache complete: $EVIDENCE_ROOT"
echo "The checkpoint was hashed and its ZIP/pickle structure inspected under network denial."
echo "Nothing was installed, loaded, inferred, activated, selected or sent to MIDI."
