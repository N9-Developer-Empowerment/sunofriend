from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
import subprocess
import tarfile

import pytest

from sunofriend.separation_other_refinement_next_source_evidence import (
    SOURCE_ARCHIVE_ROOT,
    inspect_source_archive,
    verify_extracted_source_tree,
)


ROOT = Path(__file__).resolve().parents[1]


def _archive(path: Path, files: dict[str, bytes]) -> None:
    root = SOURCE_ARCHIVE_ROOT
    with tarfile.open(path, mode="w:gz") as archive:
        for relative, payload in files.items():
            info = tarfile.TarInfo(f"{root}/{relative}")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))


def test_source_evidence_hashes_and_extracts_without_import(tmp_path: Path) -> None:
    files = {
        "LICENSE": b"MIT\n",
        "pyproject.toml": b"[project]\nname='fixture'\n",
    }
    expected = {name: hashlib.sha256(payload).hexdigest() for name, payload in files.items()}
    archive = tmp_path / "source.tar.gz"
    extracted = tmp_path / "source"
    _archive(archive, files)

    evidence = inspect_source_archive(
        archive,
        extract_root=extracted,
        expected_file_hashes=expected,
    )

    assert evidence["status"] == "exact_source_archive_verified_statically_not_imported"
    assert evidence["critical_file_hashes"] == expected
    assert evidence["inspection"]["source_imported"] is False
    assert evidence["effects"]["checkpoint_loaded"] is False
    assert (extracted / "LICENSE").read_bytes() == b"MIT\n"
    assert verify_extracted_source_tree(
        evidence, extracted, expected_file_hashes=expected
    ) == {
        "file_count": 2,
        "logical_bytes": sum(map(len, files.values())),
        "inventory_matches": True,
    }

    (extracted / "LICENSE").write_bytes(b"changed\n")
    with pytest.raises(ValueError, match="differs from sealed evidence"):
        verify_extracted_source_tree(
            evidence, extracted, expected_file_hashes=expected
        )


def test_source_evidence_rejects_unsafe_member(tmp_path: Path) -> None:
    archive = tmp_path / "unsafe.tar.gz"
    with tarfile.open(archive, mode="w:gz") as handle:
        info = tarfile.TarInfo(f"{SOURCE_ARCHIVE_ROOT}/../../escape")
        info.size = 1
        handle.addfile(info, io.BytesIO(b"x"))

    with pytest.raises(ValueError, match="unsafe source archive member path"):
        inspect_source_archive(archive, expected_file_hashes={})


def test_source_evidence_rejects_changed_critical_file(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar.gz"
    _archive(archive, {"LICENSE": b"changed\n"})

    with pytest.raises(ValueError, match="critical source-file hashes differ"):
        inspect_source_archive(
            archive,
            expected_file_hashes={"LICENSE": hashlib.sha256(b"expected\n").hexdigest()},
        )


def test_source_route_requires_specific_acceptance(tmp_path: Path) -> None:
    setup = ROOT / "scripts" / "setup-separation-other-refinement-next-challenger-macos.sh"
    result = subprocess.run(
        [str(setup), "--source-evidence-only"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "SUNOFRIEND_SEPARATION_ROOT": str(tmp_path / "separation"),
        },
    )

    assert result.returncode == 2
    assert "requires --accept-source-evidence" in result.stderr
    assert not (tmp_path / "separation").exists()


def test_source_route_is_capped_static_and_network_denied() -> None:
    setup = (
        ROOT / "scripts" / "setup-separation-other-refinement-next-challenger-macos.sh"
    ).read_text(encoding="utf-8")
    inspector = (
        ROOT / "scripts" / "inspect-separation-other-refinement-next-source.py"
    ).read_text(encoding="utf-8")

    assert "SOURCE_CAP_BYTES=33554432" in setup
    assert "--source-evidence-only" in setup
    assert "--accept-source-evidence" in setup
    assert "ulimit -f 65536" in setup
    assert '--max-filesize "$SOURCE_CAP_BYTES"' in setup
    assert "(deny network*)" in setup
    assert "tarfile" not in setup
    assert "inspect_source_archive" in inspector
    assert "verify_extracted_source_tree" in inspector
