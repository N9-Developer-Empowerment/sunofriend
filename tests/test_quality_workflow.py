from __future__ import annotations

from pathlib import Path


REPOSITORY_ROOT = Path(__file__).parents[1]


def _read(path: str) -> str:
    return (REPOSITORY_ROOT / path).read_text(encoding="utf-8")


def test_quality_workflow_compares_the_merge_candidate_with_its_exact_base() -> None:
    workflow = _read(".github/workflows/quality.yml")

    assert "pull_request_target" not in workflow
    assert "github.event.pull_request.base.sha" in workflow
    assert "git worktree add --detach" in workflow
    assert "--repository-root \"$BASE_ROOT\"" in workflow
    assert "base-code-risk.json" in workflow
    assert "current-code-risk.json" in workflow
    assert "scripts/check-code-risk-ratchet.py" in workflow
    assert "python -m coverage run -m pytest" in workflow


def test_mutation_workflow_is_bounded_to_changed_pilot_modules() -> None:
    workflow = _read(".github/workflows/quality.yml")

    for path in (
        "src/sunofriend/source_roles.py",
        "src/sunofriend/automatic_selection.py",
        "src/sunofriend/separation_review_transport.py",
    ):
        assert path in workflow
    assert "if: steps.changes.outputs.run == 'true'" in workflow
    assert 'python -m mutmut run --max-children 4 "${module}*"' in workflow
    assert 'module_args+=(--module "$module")' in workflow
    assert "--mutants-root mutants" in workflow


def test_complete_quality_remains_scheduled_and_manually_dispatchable() -> None:
    workflow = _read(".github/workflows/quality.yml")

    assert 'cron: "17 3 * * *"' in workflow
    assert "workflow_dispatch:" in workflow
    assert "Complete macOS quality baseline" in workflow
    assert "Complete three-module mutation pilot" in workflow
    assert "coverage-binding.json" in workflow
    assert "complete-mutation/mutation.json" in workflow


def test_agent_and_pull_request_guidance_require_deep_module_review() -> None:
    agents = _read("AGENTS.md")
    template = _read(".github/PULL_REQUEST_TEMPLATE.md")

    for concept in (
        "unique design knowledge",
        "Callers know fewer",
        "small, typed",
        "Errors, side effects",
        "musical authority",
        "change amplification",
    ):
        assert concept in agents or concept in template
    assert "proposed merged tree" in agents
    assert "separate Git branch" in agents
    assert "separate Git worktree" in agents
