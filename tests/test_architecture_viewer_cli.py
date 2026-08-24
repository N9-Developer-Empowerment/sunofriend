from __future__ import annotations

import json
from pathlib import Path

import pytest

from devtools.architecture_viewer import __main__ as architecture_cli


def _repository(root: Path) -> None:
    package = root / "src" / "sunofriend"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "a.py").write_text("from .b import B\nclass A: pass\n", encoding="utf-8")
    (package / "b.py").write_text("class B: pass\n", encoding="utf-8")
    docs = root / "docs"
    docs.mkdir()
    (docs / "architecture-viewer-groups.json").write_text(
        json.dumps(
            {
                "schema": "sunofriend-architecture-groups.v2",
                "default_group": "all",
                "groups": [{"id": "all", "label": "All"}],
                "contracts": [
                    {
                        "id": "a-does-not-import-b",
                        "type": "forbidden",
                        "source": {"modules": ["a"]},
                        "target": {"modules": ["b"]},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


def test_cli_plan_check_query_and_private_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repository(tmp_path)
    monkeypatch.setattr(architecture_cli, "REPOSITORY_ROOT", tmp_path)

    assert architecture_cli.main(["--plan", "--no-tests"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["schema"] == "sunofriend-architecture-viewer.v2"
    assert plan["effects"]["writes"] == []

    assert architecture_cli.main(["--module", "a", "--no-tests"]) == 0
    query = json.loads(capsys.readouterr().out)
    assert query["kind"] == "module"
    assert query["module"]["name"] == "sunofriend.a"

    assert architecture_cli.main(["--check", "--no-tests"]) == 1
    check = json.loads(capsys.readouterr().out)
    assert check["status"] == "failed"
    assert check["violations"][0]["occurrences"][0]["line"] == 1

    snapshot = tmp_path / "private" / "architecture.json"
    assert architecture_cli.main(["--snapshot-out", str(snapshot), "--no-tests"]) == 0
    assert Path(capsys.readouterr().out.strip()) == snapshot
    assert snapshot.stat().st_mode & 0o777 == 0o600
    assert json.loads(snapshot.read_text(encoding="utf-8"))["architecture_sha256"]


def test_cli_rejects_ambiguous_operation_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _repository(tmp_path)
    monkeypatch.setattr(architecture_cli, "REPOSITORY_ROOT", tmp_path)

    with pytest.raises(SystemExit) as error:
        architecture_cli.main(["--plan", "--check", "--no-tests"])
    assert error.value.code == 2
    with pytest.raises(SystemExit) as error:
        architecture_cli.main(["--check", "--out", str(tmp_path / "viewer"), "--no-tests"])
    assert error.value.code == 2


def test_cli_preserves_existing_viewer_and_uses_numbered_fresh_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _repository(tmp_path)
    monkeypatch.setattr(architecture_cli, "REPOSITORY_ROOT", tmp_path)
    requested = tmp_path / "viewer"
    requested.mkdir()
    marker = requested / "keep.txt"
    marker.write_text("original snapshot", encoding="utf-8")
    (tmp_path / "viewer-2").mkdir()

    assert architecture_cli.main(["--out", str(requested), "--no-tests"]) == 0

    captured = capsys.readouterr()
    generated_index = Path(captured.out.strip())
    assert generated_index == tmp_path / "viewer-3" / "index.html"
    assert generated_index.is_file()
    assert "preserving it and using" in captured.err
    assert str(tmp_path / "viewer-3") in captured.err
    assert marker.read_text(encoding="utf-8") == "original snapshot"
