from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).parents[1]
JAVASCRIPT = (ROOT / "src/sunofriend/vocal_session.js").read_text(encoding="utf-8")
HTML = (ROOT / "src/sunofriend/vocal_session.html").read_text(encoding="utf-8")
LAUNCHER = (ROOT / "scripts/private-vocal-session.py").read_text(encoding="utf-8")


def _function_body(name: str, *, next_name: str) -> str:
    start = f"function {name}"
    end = f"function {next_name}"
    assert start in JAVASCRIPT, f"missing JavaScript function {name}"
    assert end in JAVASCRIPT, f"missing JavaScript function {next_name}"
    return JAVASCRIPT.split(start, 1)[1].split(end, 1)[0]


def test_record_new_attempt_is_workflow_not_terminal_record_again_decision() -> None:
    """The recording action must not close a phrase before a take exists."""

    assert 'id="record-new-attempt"' in HTML
    assert 'querySelector("#record-new-attempt")' in JAVASCRIPT
    assert 'decide("record_again")' not in JAVASCRIPT


def test_active_audition_has_a_visible_source_state_before_decision() -> None:
    """Playing a source must visibly identify the source the Use action refers to."""

    render = _function_body("render", next_name="selectPhrase")
    source_tray = render.split("tray.replaceChildren", 1)[1].split("const current", 1)[
        0
    ]
    assert "activeSourceId" in source_tray
    assert re.search(
        r"active[-_ ]audition|auditioning|ariaPressed|aria-pressed", source_tray
    )


def test_source_playback_waits_for_metadata_before_seeking() -> None:
    """Phrase seeking must not race media metadata loading."""

    playback = _function_body("playSource", next_name="stopPlayback")
    metadata = playback.find("loadedmetadata")
    seek = playback.find("currentTime")
    assert metadata >= 0, "playSource must wait for loadedmetadata"
    assert seek >= 0, "playSource must seek to the reviewed phrase start"
    assert metadata < seek, "loadedmetadata must be awaited before currentTime is set"
    assert 'item.source_class === "human_vocal_phrase_capture"' in playback
    assert "Boolean(item.bound_phrase_id)" not in playback


def test_saved_decision_view_offers_reopen_and_record_new_attempt() -> None:
    """An immutable saved event must not make the phrase a dead end."""

    assert 'id="reopen-phrase"' in HTML
    assert 'id="record-new-attempt"' in HTML
    assert 'querySelector("#reopen-phrase")' in JAVASCRIPT
    render = _function_body("render", next_name="selectPhrase")
    saved_decision_branch = render.split("if (row.decision)", 1)[1].split(
        "} else {", 1
    )[0]
    assert "reopen-phrase" in saved_decision_branch
    assert "record-new-attempt" in saved_decision_branch


def test_context_controls_expose_original_phrase_section_and_song_scopes() -> None:
    """A singer can hear the source and progressively wider musical context."""

    assert 'id="play-original"' in HTML
    assert 'querySelector("#play-original")' in JAVASCRIPT
    for scope in ("phrase", "section", "song"):
        assert re.search(rf'(?:value|data-context-scope)="{scope}"', HTML), (
            f"missing {scope} context control"
        )
        assert re.search(rf"[\"']{scope}[\"']", JAVASCRIPT), (
            f"missing {scope} context playback implementation"
        )


def test_private_launcher_exposes_and_forwards_recording_configuration() -> None:
    """The supported recording server options must be reachable from its launcher."""

    assert '"--recording-cue-source-id"' in LAUNCHER
    assert '"--capture-output-dir"' in LAUNCHER
    assert '"--candidate-vault-dir"' in LAUNCHER
    invocation = LAUNCHER.split("run_vocal_session(", 1)[1]
    assert "recording_cue_source_id=args.recording_cue_source_id" in invocation
    assert "capture_output_dir=args.capture_output_dir" in invocation
    assert "candidate_vault_dir=args.candidate_vault_dir" in invocation


def test_provisional_candidate_uses_reversible_working_choice_not_decision() -> None:
    """A kept candidate may enter a draft without becoming musical authority."""

    candidate_filter = _function_body("isHumanSourceForPhrase", next_name="formatTime")
    assert '"unreviewed_vocal_candidate"' in candidate_filter
    render = _function_body("render", next_name="selectPhrase")
    assert "Use in draft" in render
    assert "Working choice" in render
    working_choice = JAVASCRIPT.split("async function useWorkingChoice", 1)[1].split(
        'document.querySelector("#use-human")', 1
    )[0]
    assert 'api("/api/working-choices"' in working_choice
    assert "expected_revision" in working_choice
    assert "decide(" not in working_choice


def test_recording_save_uses_server_declared_destination() -> None:
    """The same recorder supports legacy admission and the candidate vault."""

    save = _function_body("saveRecordedAttempt", next_name="showNotice")
    assert 'appState.recording.save_url === "/api/candidate"' in save
    assert "api(appState.recording.save_url" in save
    assert "working draft" in save


def test_large_song_navigation_has_status_filters_and_next_open_phrase() -> None:
    """A long phrase roster must not require scanning from the beginning."""

    for phrase_filter in ("open", "all", "decided"):
        assert f'data-phrase-filter="{phrase_filter}"' in HTML
    assert 'id="next-open-phrase"' in HTML
    assert "function selectNextOpenPhrase" in JAVASCRIPT
    assert 'querySelector("#next-open-phrase")' in JAVASCRIPT


def test_phrase_specific_common_zero_take_is_not_shown_on_other_phrases() -> None:
    """A padded pickup must not masquerade as a complete-song candidate."""

    source_filter = _function_body("isHumanSourceForPhrase", next_name="formatTime")
    assert "eligible_phrase_ids" in source_filter
    assert "includes(phraseId)" in source_filter
