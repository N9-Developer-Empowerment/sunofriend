from __future__ import annotations

from copy import deepcopy

import pytest

from sunofriend.source_receipt import document_sha256
from sunofriend.vocal_tail_review import (
    create_vocal_tail_choice,
    create_vocal_tail_comparison,
    create_vocal_usable_base_review,
    validate_vocal_tail_choice,
    validate_vocal_tail_comparison,
    validate_vocal_usable_base_review,
)


def test_exact_tail_choice_and_usable_base_are_human_only_zero_effect() -> None:
    comparison = _comparison()
    choice = create_vocal_tail_choice(
        comparison, choice="b", heard_a=True, heard_b=True, notes="Stronger ending."
    )
    review = create_vocal_usable_base_review(
        comparison, choice, outcome="usable_base", notes="Useful pickup base."
    )

    assert choice["choice"] == "b"
    assert choice["heard"] == {"a": True, "b": True}
    assert review["outcome"] == "usable_base"
    assert review["selected_tail"] == "b"
    assert review["binding"]["comparison_sha256"] == comparison["document_sha256"]
    assert review["binding"]["tail_choice_sha256"] == choice["document_sha256"]
    for document in (comparison, choice, review):
        assert all(value is False for value in document["authority"].values())
        assert all(value is False for value in document["effects"].values())
        assert document["network_used"] is False


def test_neither_is_valid_but_cannot_become_usable_base() -> None:
    comparison = _comparison()
    choice = create_vocal_tail_choice(
        comparison, choice="neither", heard_a=True, heard_b=True
    )
    rejected = create_vocal_usable_base_review(
        comparison, choice, outcome="not_usable_base"
    )
    assert rejected["selected_tail"] is None
    with pytest.raises(ValueError, match="neither"):
        create_vocal_usable_base_review(comparison, choice, outcome="usable_base")


def test_tail_review_requires_both_listens_and_exact_parent_chain() -> None:
    comparison = _comparison()
    with pytest.raises(ValueError, match="A and B"):
        create_vocal_tail_choice(comparison, choice="a", heard_a=True, heard_b=False)
    choice = create_vocal_tail_choice(
        comparison, choice="a", heard_a=True, heard_b=True
    )
    foreign = _comparison(parent_hash="9" * 64)
    with pytest.raises(ValueError, match="binding"):
        validate_vocal_tail_choice(choice, foreign)


@pytest.mark.parametrize("target", ("comparison", "choice", "review"))
def test_rehashed_release_or_training_authority_is_rejected(target: str) -> None:
    comparison = _comparison()
    choice = create_vocal_tail_choice(
        comparison, choice="a", heard_a=True, heard_b=True
    )
    review = create_vocal_usable_base_review(comparison, choice, outcome="usable_base")
    document = deepcopy(
        {"comparison": comparison, "choice": choice, "review": review}[target]
    )
    document["authority"]["release_authorized"] = True
    _rehash(document)
    with pytest.raises(ValueError, match="release|authority"):
        if target == "comparison":
            validate_vocal_tail_comparison(document)
        elif target == "choice":
            validate_vocal_tail_choice(document, comparison)
        else:
            validate_vocal_usable_base_review(document, comparison, choice)


def test_comparison_rejects_invalid_window_duplicate_audio_and_extra_fields() -> None:
    with pytest.raises(ValueError, match="escapes"):
        create_vocal_tail_comparison(
            **_comparison_args(), tail_start_frame=47_000, tail_end_frame=49_000
        )
    args = _comparison_args()
    args["candidate_b_audio_sha256"] = args["candidate_a_audio_sha256"]
    with pytest.raises(ValueError, match="distinct"):
        create_vocal_tail_comparison(
            **args, tail_start_frame=44_000, tail_end_frame=47_000
        )
    expanded = _comparison()
    expanded["release_ready"] = True
    _rehash(expanded)
    with pytest.raises(ValueError, match="fields changed"):
        validate_vocal_tail_comparison(expanded)


def test_candidate_a_may_be_the_exact_dry_control() -> None:
    args = _comparison_args()
    args["candidate_a_audio_sha256"] = args["dry_excerpt_audio_sha256"]
    comparison = create_vocal_tail_comparison(
        **args, tail_start_frame=44_000, tail_end_frame=47_000
    )
    assert (
        comparison["audio"]["candidate_a_sha256"]
        == comparison["audio"]["dry_excerpt_sha256"]
    )


def test_comparison_rejects_non_dry_parent_result() -> None:
    args = _comparison_args()
    args["parent_result_schema"] = "sunofriend.synthetic-result.v0"
    with pytest.raises(ValueError, match="exact dry vocal render result"):
        create_vocal_tail_comparison(
            **args, tail_start_frame=44_000, tail_end_frame=47_000
        )


def _comparison(parent_hash: str = "1" * 64) -> dict:
    return create_vocal_tail_comparison(
        **_comparison_args(parent_hash), tail_start_frame=44_000, tail_end_frame=47_000
    )


def _comparison_args(parent_hash: str = "1" * 64) -> dict:
    return {
        "parent_result_schema": "sunofriend.vocal-comp-dry-render-result.v0",
        "parent_result_sha256": parent_hash,
        "phrase_id": "phrase-002",
        "dry_excerpt_audio_sha256": "2" * 64,
        "candidate_a_audio_sha256": "3" * 64,
        "candidate_b_audio_sha256": "4" * 64,
        "sample_rate": 48_000,
        "channels": 1,
        "excerpt_frames": 48_000,
    }


def _rehash(document: dict) -> None:
    document.pop("document_sha256", None)
    document["document_sha256"] = document_sha256(document)
