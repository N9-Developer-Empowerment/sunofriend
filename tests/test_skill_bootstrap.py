from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "sunofriend" / "scripts" / "bootstrap-macos.sh"
REPOSITORY_URL = "https://github.com/N9-Developer-Empowerment/sunofriend.git"


def run_bootstrap(
    tmp_path: Path,
    *arguments: str,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(exist_ok=True)
    uname = fake_bin / "uname"
    uname.write_text(
        "#!/bin/sh\n"
        'if [ "${1:-}" = "-s" ]; then echo Darwin; '
        'elif [ "${1:-}" = "-m" ]; then echo arm64; '
        "else echo Darwin; fi\n",
        encoding="utf-8",
    )
    uname.chmod(0o755)
    for executable in ("python3.11", "fluidsynth"):
        stub = fake_bin / executable
        stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        stub.chmod(0o755)
    environment = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
    }
    return subprocess.run(
        [str(SCRIPT), *arguments],
        check=False,
        capture_output=True,
        text=True,
        input=input_text,
        env=environment,
    )


def test_default_is_read_only_plan(tmp_path: Path) -> None:
    result = run_bootstrap(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "inspection only" in result.stdout
    assert (
        "No files, packages, repositories or settings are being changed."
        in result.stdout
    )
    assert (
        "Network destinations used only after a separately confirmed action"
        in result.stdout
    )
    assert "allow at least 1 GB free" in result.stdout
    assert "GeneralUser GS License v2.0" in result.stdout
    assert "this helper never invokes sudo" in result.stdout
    assert "no dependencies or audio assets are installed" in result.stdout
    assert "immutable Git archive of the approved commit" in result.stdout
    assert "installation is non-editable" in result.stdout
    assert "--prepare --checkout" in result.stdout
    assert not (tmp_path / "home").exists()


def test_apply_installs_only_an_immutable_approved_archive() -> None:
    script = SCRIPT.read_text(encoding="utf-8")

    assert 'git -C "${CHECKOUT_PATH}" archive "${EXPECTED_REVISION}"' in script
    assert "sunofriend-approved-source" in script
    assert "assert_approved_checkout" in script
    assert "-e '.[all]'" not in script


def test_rejects_relative_or_overly_broad_checkout(tmp_path: Path) -> None:
    relative = run_bootstrap(tmp_path, "--checkout", "sunofriend")
    broad = run_bootstrap(
        tmp_path,
        "--checkout",
        str(tmp_path / "home"),
    )

    assert relative.returncode == 2
    assert "absolute path" in relative.stderr
    assert broad.returncode == 2
    assert "too broad" in broad.stderr


def create_expected_checkout(target: Path) -> str:
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    subprocess.run(
        ["git", "-C", str(target), "remote", "add", "origin", REPOSITORY_URL],
        check=True,
    )
    (target / "constraints-audio-macos.txt").write_text("", encoding="utf-8")
    (target / "pyproject.toml").write_text(
        "[build-system]\nrequires = []\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(target), "add", "."], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(target),
            "-c",
            "user.name=Sunofriend Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "test fixture",
        ],
        check=True,
    )
    return subprocess.run(
        ["git", "-C", str(target), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_prepare_requires_confirmation_before_changes(tmp_path: Path) -> None:
    target = tmp_path / "checkout"
    result = run_bootstrap(
        tmp_path,
        "--prepare",
        "--checkout",
        str(target),
        input_text="",
    )

    assert result.returncode == 2
    assert "--prepare needs an interactive confirmation" in result.stderr
    assert not target.exists()


def test_apply_requires_exact_revision_and_confirmation(tmp_path: Path) -> None:
    target = tmp_path / "checkout"
    revision = create_expected_checkout(target)

    missing_revision = run_bootstrap(
        tmp_path,
        "--apply",
        "--checkout",
        str(target),
        input_text="",
    )
    assert missing_revision.returncode == 2
    assert "--apply requires --expected-revision" in missing_revision.stderr

    result = run_bootstrap(
        tmp_path,
        "--apply",
        "--expected-revision",
        revision,
        "--checkout",
        str(target),
        input_text="",
    )
    assert result.returncode == 2
    assert "--apply needs an interactive confirmation" in result.stderr


def test_apply_rejects_checkout_that_changed_after_review(tmp_path: Path) -> None:
    target = tmp_path / "checkout"
    create_expected_checkout(target)
    unapproved_revision = "a" * 40

    result = run_bootstrap(
        tmp_path,
        "--apply",
        "--yes",
        "--expected-revision",
        unapproved_revision,
        "--checkout",
        str(target),
    )

    assert result.returncode == 2
    assert "not approved commit" in result.stderr
    assert not (target / ".venv").exists()


def test_existing_unrelated_path_is_never_reused(tmp_path: Path) -> None:
    target = tmp_path / "checkout"
    target.mkdir()
    marker = target / "keep-me.txt"
    marker.write_text("unchanged", encoding="utf-8")

    result = run_bootstrap(tmp_path, "--checkout", str(target))

    assert result.returncode == 2
    assert "not a Git checkout" in result.stderr
    assert marker.read_text(encoding="utf-8") == "unchanged"


def test_existing_expected_checkout_is_inspected_without_update(tmp_path: Path) -> None:
    target = tmp_path / "checkout"
    subprocess.run(["git", "init", "-q", str(target)], check=True)
    subprocess.run(
        ["git", "-C", str(target), "remote", "add", "origin", REPOSITORY_URL],
        check=True,
    )
    marker = target / "local-work.txt"
    marker.write_text("preserve", encoding="utf-8")

    result = run_bootstrap(tmp_path, "--checkout", str(target))

    assert result.returncode == 0, result.stderr
    assert (
        "preserve it exactly; do not fetch, pull, reset or switch branches"
        in result.stdout
    )
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_wrong_soundfont_hash_is_reported_without_replacement(tmp_path: Path) -> None:
    soundfont = (
        tmp_path
        / "home"
        / ".local"
        / "share"
        / "sunofriend"
        / "soundfonts"
        / "GeneralUser-GS.sf2"
    )
    soundfont.parent.mkdir(parents=True)
    soundfont.write_bytes(b"not the verified soundfont")

    result = run_bootstrap(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "HASH MISMATCH" in result.stdout
    assert "will stop and will not replace this file" in result.stdout
    assert soundfont.read_bytes() == b"not the verified soundfont"


def test_apply_fails_before_other_changes_when_soundfont_hash_is_wrong(
    tmp_path: Path,
) -> None:
    target = tmp_path / "checkout"
    revision = create_expected_checkout(target)
    soundfont = (
        tmp_path
        / "home"
        / ".local"
        / "share"
        / "sunofriend"
        / "soundfonts"
        / "GeneralUser-GS.sf2"
    )
    soundfont.parent.mkdir(parents=True)
    soundfont.write_bytes(b"not the verified soundfont")

    result = run_bootstrap(
        tmp_path,
        "--apply",
        "--yes",
        "--expected-revision",
        revision,
        "--checkout",
        str(target),
    )

    assert result.returncode == 2
    assert "wrong hash and will not be replaced" in result.stderr
    assert not (target / ".venv").exists()
    assert soundfont.read_bytes() == b"not the verified soundfont"
