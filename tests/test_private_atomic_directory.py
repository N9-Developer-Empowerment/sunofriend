from __future__ import annotations

import os
from pathlib import Path

import pytest

import sunofriend._private_atomic_directory as atomic_directory


@pytest.mark.parametrize(
    "value",
    ("", ".", "..", "nested/name", "/absolute", "nul\0suffix"),
)
def test_directory_entry_name_rejects_path_syntax(value: str) -> None:
    with pytest.raises(atomic_directory.UnsafeDirectoryEntryName):
        atomic_directory.require_safe_directory_entry_name(value)


def test_directory_entry_name_accepts_one_canonical_basename() -> None:
    assert (
        atomic_directory.require_safe_directory_entry_name("candidate-private")
        == "candidate-private"
    )


def test_absolute_directory_open_is_descriptor_bound_and_nofollow(
    tmp_path: Path,
) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    descriptor = atomic_directory.open_absolute_directory_nofollow(private)
    try:
        held = os.fstat(descriptor)
        visible = private.stat()
        assert (held.st_dev, held.st_ino) == (visible.st_dev, visible.st_ino)
        assert os.get_inheritable(descriptor) is False
    finally:
        os.close(descriptor)

    redirected = tmp_path / "redirected"
    redirected.symlink_to(private, target_is_directory=True)
    with pytest.raises(OSError):
        atomic_directory.open_absolute_directory_nofollow(redirected)


def test_absolute_directory_open_rejects_relative_path() -> None:
    with pytest.raises(atomic_directory.UnsafeDirectoryPath):
        atomic_directory.open_absolute_directory_nofollow(Path("relative"))


def test_atomic_rename_reports_unsupported_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(atomic_directory.sys, "platform", "unsupported-test")
    with pytest.raises(atomic_directory.AtomicDirectoryUnavailable):
        atomic_directory.exclusive_directory_rename_implementation()


def test_atomic_rename_uses_exact_held_parent_descriptor() -> None:
    calls: list[tuple[object, ...]] = []

    def rename(*arguments: object) -> int:
        calls.append(arguments)
        return 0

    atomic_directory.rename_directory_no_replace_at(
        91,
        "staging",
        "published",
        implementation=(rename, 37),
    )

    assert calls == [(91, b"staging", 91, b"published", 37)]


def test_raced_destination_is_preserved_and_source_survives(
    tmp_path: Path,
) -> None:
    staging = tmp_path / "staging"
    staging.mkdir(mode=0o700)
    source_sentinel = staging / "source-sentinel"
    source_sentinel.write_text("source", encoding="utf-8")
    destination = tmp_path / "published"
    destination.mkdir(mode=0o700)
    destination_sentinel = destination / "destination-sentinel"
    destination_sentinel.write_text("raced", encoding="utf-8")

    parent_descriptor = atomic_directory.open_absolute_directory_nofollow(tmp_path)
    try:
        with pytest.raises(FileExistsError):
            atomic_directory.rename_directory_no_replace_at(
                parent_descriptor,
                staging.name,
                destination.name,
            )
    finally:
        os.close(parent_descriptor)

    assert source_sentinel.read_text(encoding="utf-8") == "source"
    assert destination_sentinel.read_text(encoding="utf-8") == "raced"
