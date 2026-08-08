#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPOSITORY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PLAN_SCRIPT="$REPOSITORY_ROOT/scripts/plan-separation-other-refinement-next-challenger.py"
INSPECT_SCRIPT="$REPOSITORY_ROOT/scripts/inspect-separation-other-refinement-next-challenger-artifacts.py"
DATA_ROOT=${SUNOFRIEND_SEPARATION_ROOT:-"$HOME/.local/share/sunofriend/separation"}
EVIDENCE_ROOT=${SUNOFRIEND_MEGA53_EVIDENCE_ROOT:-"$DATA_ROOT/evidence/bs-roformer-mega-53-synth-v1"}
ACTION=plan
ACCEPTED_PROVISIONAL_TERMS=false
ACCEPTED_CHECKPOINT_USE=false
CHECKPOINT_FILE=mvsep_mega_model_bs_roformer_53_stems_v1.ckpt
CHECKPOINT_BYTES=1368919887
CHECKPOINT_SHA256=c62820893bbf86d4e734f966bd142d9157cfc8bb8e79e9d8f9ea553f3ff3519f
CHECKPOINT_URL='https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21/mvsep_mega_model_bs_roformer_53_stems_v1.ckpt'
CONFIG_FILE=mvsep_mega_model_bs_roformer_53_stems.yaml
CONFIG_BYTES=4184
CONFIG_SHA256=7e198062a251587088adb91215a4f44ab59e67bd62fcc805cf54d6e7dfc51103
CONFIG_URL='https://github.com/ZFTurbo/Music-Source-Separation-Training/releases/download/v1.0.21/mvsep_mega_model_bs_roformer_53_stems.yaml'
EXPECTED_TOTAL_BYTES=1368924071
MAX_DOWNLOAD_BYTES=1610612736

usage() {
    echo "Usage: scripts/setup-separation-other-refinement-next-challenger-macos.sh [--plan | --evidence-only --accept-provisional-local-noncommercial-terms --accept-checkpoint-use]"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --plan) ACTION=plan ;;
        --evidence-only) ACTION=evidence-only ;;
        --accept-provisional-local-noncommercial-terms) ACCEPTED_PROVISIONAL_TERMS=true ;;
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

if [ "$ACCEPTED_PROVISIONAL_TERMS" != true ] || [ "$ACCEPTED_CHECKPOINT_USE" != true ]; then
    echo "--evidence-only requires both acceptance flags after reviewing the plan" >&2
    exit 2
fi
for required_command in curl sandbox-exec; do
    if ! command -v "$required_command" >/dev/null 2>&1; then
        echo "$required_command is required" >&2
        exit 2
    fi
done
if [ "$EXPECTED_TOTAL_BYTES" -gt "$MAX_DOWNLOAD_BYTES" ]; then
    echo "Reviewed artifact identities exceed the approved 1.5 GiB cap" >&2
    exit 2
fi
if [ -e "$EVIDENCE_ROOT" ] || [ -L "$EVIDENCE_ROOT" ]; then
    echo "Refusing to overwrite existing Mega-53 evidence: $EVIDENCE_ROOT" >&2
    exit 2
fi

EVIDENCE_PARENT=$(dirname "$EVIDENCE_ROOT")
mkdir -p "$EVIDENCE_PARENT"
STAGING=$(mktemp -d "$EVIDENCE_PARENT/.bs-roformer-mega-53-synth-v1.building.XXXXXX")
preserve_failed_staging() {
    mega53_exit_code=$?
    if [ -n "${STAGING:-}" ] && [ -d "$STAGING" ]; then
        failed_root="$EVIDENCE_PARENT/bs-roformer-mega-53-synth-v1.failed.$$.evidence"
        if [ ! -e "$failed_root" ] && [ ! -L "$failed_root" ]; then
            chmod -R go-w "$STAGING" 2>/dev/null || true
            mv "$STAGING" "$failed_root"
            STAGING=
            echo "Preserved failed evidence staging: $failed_root" >&2
        fi
    fi
    exit "$mega53_exit_code"
}
trap preserve_failed_staging EXIT HUP INT TERM

CHECKPOINT="$STAGING/$CHECKPOINT_FILE"
CONFIG="$STAGING/$CONFIG_FILE"
(
    ulimit -f 3145728
    curl --fail --location --retry 3 --silent --show-error \
        --proto '=https' --tlsv1.2 --max-filesize "$MAX_DOWNLOAD_BYTES" \
        "$CONFIG_URL" --output "$CONFIG"
    curl --fail --location --retry 3 --silent --show-error \
        --proto '=https' --tlsv1.2 --max-filesize "$MAX_DOWNLOAD_BYTES" \
        "$CHECKPOINT_URL" --output "$CHECKPOINT"
)

ACTUAL_CHECKPOINT_BYTES=$(wc -c < "$CHECKPOINT" | tr -d ' ')
ACTUAL_CONFIG_BYTES=$(wc -c < "$CONFIG" | tr -d ' ')
ACTUAL_TOTAL_BYTES=$((ACTUAL_CHECKPOINT_BYTES + ACTUAL_CONFIG_BYTES))
if [ "$ACTUAL_CHECKPOINT_BYTES" != "$CHECKPOINT_BYTES" ]; then
    echo "Mega-53 checkpoint byte count differs: $ACTUAL_CHECKPOINT_BYTES" >&2
    exit 2
fi
if [ "$ACTUAL_CONFIG_BYTES" != "$CONFIG_BYTES" ]; then
    echo "Mega-53 configuration byte count differs: $ACTUAL_CONFIG_BYTES" >&2
    exit 2
fi
if [ "$ACTUAL_TOTAL_BYTES" -gt "$MAX_DOWNLOAD_BYTES" ]; then
    echo "Downloaded artifacts exceed the approved 1.5 GiB cap" >&2
    exit 2
fi
chmod 0444 "$CHECKPOINT" "$CONFIG"

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$PLAN_PYTHON" -B "$INSPECT_SCRIPT" "$CHECKPOINT" "$CONFIG" \
    > "$STAGING/STATIC-EVIDENCE.json"

PYTHONPATH="$REPOSITORY_ROOT/src" PYTHONDONTWRITEBYTECODE=1 \
    sandbox-exec -p '(version 1)(allow default)(deny network*)' \
    "$PLAN_PYTHON" -B - "$STAGING/STATIC-EVIDENCE.json" "$STAGING/APPROVAL-RECEIPT.json" <<'PY'
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys

from sunofriend.separation_other_refinement_next_challenger_evidence import (
    validate_mega53_artifact_evidence,
)

evidence_path = Path(sys.argv[1])
receipt_path = Path(sys.argv[2])
evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
validate_mega53_artifact_evidence(evidence)
effects = evidence["effects"]
assert effects["checkpoint_deserialized"] is False
assert effects["torch_load_called"] is False
assert effects["dependency_installed"] is False
assert effects["model_imported"] is False
assert effects["model_constructed"] is False
assert effects["inference_runs"] == 0
assert effects["audio_reads"] == 0
receipt = {
    "schema": "sunofriend.mvsep-mega53-evidence-approval.v1",
    "status": "evidence_only_complete_no_runtime_authority",
    "recorded_at": datetime.now(timezone.utc).isoformat(),
    "profile_id": "bs-roformer-mega-53-synth-v1",
    "artifact_evidence_sha256": evidence["evidence_sha256"],
    "terms_acknowledged": "provisional local noncommercial evaluation only",
    "checkpoint_use_approved": "capped evidence-only download and static inspection",
    "network_denied_during_static_inspection": True,
    "not_approved": [
        "dependency_installation",
        "checkpoint_loading",
        "model_construction",
        "inference",
        "private_audio_processing",
        "public_activation",
        "source_selection",
        "midi",
        "hosting",
        "checkpoint_redistribution",
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
echo "Evidence-only Mega-53 cache complete: $EVIDENCE_ROOT"
echo "Checkpoint SHA-256: $CHECKPOINT_SHA256"
echo "Configuration SHA-256: $CONFIG_SHA256"
echo "Observed total bytes: $ACTUAL_TOTAL_BYTES of $MAX_DOWNLOAD_BYTES approved"
echo "Static inspection ran with network denied and did not deserialize the checkpoint."
echo "Nothing was installed, imported, loaded, inferred, activated, selected or sent to MIDI."
