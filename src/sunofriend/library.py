"""A local-first, content-addressed catalog for Sunofriend MIDI clips."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .clip import KeySignature, MidiClip


MAXIMUM_CLIP_COUNT = 10_000


@dataclass(frozen=True)
class ClipSummary:
    clip_id: str
    title: str
    revision: int
    parent_clip_id: str | None
    lineage_id: str
    key: str | None
    bpm: float
    role: str
    tags: tuple[str, ...]
    engine_version: str
    object_hash: str
    created_at: str


@dataclass(frozen=True)
class ClipAppendResult:
    """Result of one compare-and-swap append to an existing Clip library."""

    summary: ClipSummary
    replayed: bool


class ClipLibrary:
    """SQLite metadata plus immutable JSON objects addressed by SHA-256.

    SQLite remains small and easy to search or back up.  The musical document
    is stored separately under ``objects/ab/abcdef...json``.  That boundary can
    later map directly to DynamoDB metadata and S3 objects without changing the
    clip schema.
    """

    def __init__(self, root: str | Path, *, read_only: bool = False):
        self.root = Path(root).expanduser().resolve()
        self.database_path = self.root / "catalog.sqlite3"
        self.objects_path = self.root / "objects"
        self.read_only = bool(read_only)
        self.existing_only = False
        if self.read_only:
            self._validate_read_only_library()
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            self.objects_path.mkdir(parents=True, exist_ok=True)
            self._initialize()

    @classmethod
    def open_existing_writer(cls, root: str | Path) -> "ClipLibrary":
        """Open an existing catalog for narrowly controlled appends.

        Unlike the normal writable constructor, this entry point never creates
        directories, initializes tables, changes journal mode or migrates a
        schema.  It is intended for an already verified Workbench library whose
        exact catalog state will be supplied to :meth:`append_version_if_state`.
        """

        requested = Path(os.path.abspath(Path(root).expanduser()))
        if requested.is_symlink():
            raise ValueError("Append-only clip library root must not be a symlink")
        if (requested / "catalog.sqlite3").is_symlink():
            raise ValueError("Append-only clip library database must not be a symlink")
        if (requested / "objects").is_symlink():
            raise ValueError("Append-only clip library objects must not be a symlink")
        library = cls.__new__(cls)
        library.root = requested.resolve()
        library.database_path = library.root / "catalog.sqlite3"
        library.objects_path = library.root / "objects"
        library.read_only = False
        library.existing_only = True
        library._validate_existing_library(label="Append-only")
        return library

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            database_uri = f"{self.database_path.as_uri()}?mode=ro"
            connection = sqlite3.connect(database_uri, timeout=30.0, uri=True)
        elif self.existing_only:
            database_uri = f"{self.database_path.as_uri()}?mode=rw"
            connection = sqlite3.connect(database_uri, timeout=30.0, uri=True)
        else:
            connection = sqlite3.connect(str(self.database_path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        if self.read_only:
            connection.execute("PRAGMA query_only = ON")
        return connection

    def _validate_read_only_library(self) -> None:
        self._validate_existing_library(label="Read-only")

    def _validate_existing_library(self, *, label: str) -> None:
        if not self.root.exists():
            raise FileNotFoundError(f"{label} clip library root does not exist: {self.root}")
        if not self.root.is_dir():
            raise NotADirectoryError(f"{label} clip library root is not a directory: {self.root}")
        if not self.database_path.is_file():
            raise FileNotFoundError(
                f"{label} clip library database does not exist: {self.database_path}"
            )
        if not self.objects_path.exists():
            raise FileNotFoundError(
                f"{label} clip library objects directory does not exist: {self.objects_path}"
            )
        if not self.objects_path.is_dir():
            raise NotADirectoryError(
                f"{label} clip library objects path is not a directory: {self.objects_path}"
            )
        with self._connect() as connection:
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(clips)").fetchall()
            }
        required_columns = {
            "clip_id",
            "parent_clip_id",
            "lineage_id",
            "revision",
            "title",
            "key_tonic",
            "key_mode",
            "bpm",
            "role",
            "tags_json",
            "source_uri",
            "engine_version",
            "object_hash",
            "created_at",
        }
        missing_columns = sorted(required_columns - columns)
        if missing_columns:
            missing = ", ".join(missing_columns)
            raise RuntimeError(
                f"{label} clip library schema is missing required columns: {missing}"
            )

    def _require_writable(self, operation: str) -> None:
        if self.read_only:
            raise PermissionError(f"Clip library is read-only; cannot {operation}")

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS clips (
                    clip_id TEXT PRIMARY KEY,
                    parent_clip_id TEXT,
                    lineage_id TEXT NOT NULL,
                    revision INTEGER NOT NULL CHECK (revision >= 1),
                    title TEXT NOT NULL,
                    key_tonic TEXT,
                    key_mode TEXT,
                    bpm REAL NOT NULL CHECK (bpm > 0),
                    role TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    source_uri TEXT,
                    engine_version TEXT NOT NULL,
                    object_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS clips_lineage_revision ON clips(lineage_id, revision)"
            )
            connection.execute("CREATE INDEX IF NOT EXISTS clips_key ON clips(key_tonic, key_mode)")
            connection.execute("CREATE INDEX IF NOT EXISTS clips_bpm ON clips(bpm)")
            connection.execute("CREATE INDEX IF NOT EXISTS clips_role ON clips(role)")

    def object_path(self, object_hash: str) -> Path:
        if len(object_hash) != 64 or any(character not in "0123456789abcdef" for character in object_hash):
            raise ValueError("object_hash must be a lower-case SHA-256 digest")
        return self.objects_path / object_hash[:2] / f"{object_hash}.json"

    def add(self, clip: MidiClip) -> ClipSummary:
        """Add an immutable clip, idempotently when its ID/content already exist."""

        self._require_writable("add clips")
        payload = clip.canonical_bytes()
        object_hash = hashlib.sha256(payload).hexdigest()
        self._store_object(object_hash, payload)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM clips WHERE clip_id = ?", (clip.clip_id,)
            ).fetchone()
            if existing is not None:
                if existing["object_hash"] != object_hash:
                    raise ValueError(
                        f"clip_id {clip.clip_id!r} already exists with different immutable content"
                    )
                return self._summary(existing)

            lineage_id = clip.clip_id
            if clip.parent_clip_id is not None:
                parent = connection.execute(
                    "SELECT lineage_id, revision FROM clips WHERE clip_id = ?",
                    (clip.parent_clip_id,),
                ).fetchone()
                if parent is None:
                    raise KeyError(
                        f"Parent clip {clip.parent_clip_id!r} must be added before its child"
                    )
                if clip.revision != parent["revision"] + 1:
                    raise ValueError(
                        f"Child revision {clip.revision} must follow parent revision {parent['revision']}"
                    )
                lineage_id = parent["lineage_id"]

            connection.execute(
                """
                INSERT INTO clips (
                    clip_id, parent_clip_id, lineage_id, revision, title,
                    key_tonic, key_mode, bpm, role, tags_json, source_uri,
                    engine_version, object_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clip.clip_id,
                    clip.parent_clip_id,
                    lineage_id,
                    clip.revision,
                    clip.title,
                    None if clip.key is None else clip.key.tonic,
                    None if clip.key is None else clip.key.mode,
                    clip.bpm,
                    clip.instrument.role,
                    json.dumps(clip.tags, separators=(",", ":")),
                    clip.provenance.source_uri,
                    clip.engine_version,
                    object_hash,
                ),
            )
            row = connection.execute(
                "SELECT * FROM clips WHERE clip_id = ?", (clip.clip_id,)
            ).fetchone()
            assert row is not None
            return self._summary(row)

    def add_version(self, parent_clip_id: str, clip: MidiClip) -> ClipSummary:
        """Add a child version, making an accidental lineage mismatch explicit."""

        self._require_writable("add clip versions")
        if clip.parent_clip_id != parent_clip_id:
            raise ValueError("clip.parent_clip_id does not match parent_clip_id")
        return self.add(clip)

    def catalog_state_sha256(self) -> str:
        """Return the bounded Workbench catalog-state digest.

        Object bytes are verified by the read-only Workbench service.  This
        digest deliberately uses catalog pins only so it can also be evaluated
        while a SQLite ``BEGIN IMMEDIATE`` transaction holds the writer lock.
        """

        with self._connect() as connection:
            return self._catalog_state_sha256(connection)

    def append_version_if_state(
        self,
        parent_clip_id: str,
        clip: MidiClip,
        *,
        expected_state_sha256: str,
        expected_parent_object_hash: str,
    ) -> ClipAppendResult:
        """Append exactly one child when catalog and parent pins still match.

        The object is staged before the SQLite write lock is taken, published
        before the row commits, and removed after any rollback when it remains
        unreferenced.  A byte-identical deterministic child is an idempotent
        replay even after the first append changed the catalog-state digest.
        """

        self._require_writable("append a clip version")
        self._validate_append_paths()
        if clip.parent_clip_id != parent_clip_id:
            raise ValueError("clip.parent_clip_id does not match parent_clip_id")
        if not _is_sha256(expected_state_sha256):
            raise ValueError("expected_state_sha256 must be a lower-case SHA-256 digest")
        if not _is_sha256(expected_parent_object_hash):
            raise ValueError(
                "expected_parent_object_hash must be a lower-case SHA-256 digest"
            )

        payload = clip.canonical_bytes()
        object_hash = hashlib.sha256(payload).hexdigest()
        object_path = self.object_path(object_hash)
        temporary = self.objects_path / f".append-{uuid.uuid4().hex}.tmp"
        temporary.write_bytes(payload)
        published_here = False
        created_object_directory = False
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")

            # Retrying the exact create request is safe even though its first
            # successful append necessarily changed the catalog-state pin.
            existing = connection.execute(
                "SELECT * FROM clips WHERE clip_id = ?", (clip.clip_id,)
            ).fetchone()
            if existing is not None:
                if (
                    existing["object_hash"] != object_hash
                    or existing["parent_clip_id"] != parent_clip_id
                ):
                    raise ValueError(
                        f"clip_id {clip.clip_id!r} already exists with different immutable content"
                    )
                connection.rollback()
                return ClipAppendResult(self._summary(existing), replayed=True)

            if self._catalog_state_sha256(connection) != expected_state_sha256:
                raise RuntimeError("Clip library catalog state conflict")
            before_columns, before_rows = self._catalog_rows(connection)
            if len(before_rows) >= MAXIMUM_CLIP_COUNT:
                raise RuntimeError("Clip library maximum clip count reached")
            parent = connection.execute(
                "SELECT * FROM clips WHERE clip_id = ?", (parent_clip_id,)
            ).fetchone()
            if parent is None:
                raise KeyError(f"Unknown parent clip_id: {parent_clip_id}")
            if parent["object_hash"] != expected_parent_object_hash:
                raise RuntimeError("Parent Clip object state conflict")
            if clip.revision != parent["revision"] + 1:
                raise ValueError(
                    f"Child revision {clip.revision} must follow parent revision {parent['revision']}"
                )

            created_at_row = connection.execute(
                "SELECT strftime('%Y-%m-%dT%H:%M:%fZ', 'now') AS created_at"
            ).fetchone()
            assert created_at_row is not None
            created_at = str(created_at_row["created_at"])
            tags_json = json.dumps(clip.tags, separators=(",", ":"))
            connection.execute(
                """
                INSERT INTO clips (
                    clip_id, parent_clip_id, lineage_id, revision, title,
                    key_tonic, key_mode, bpm, role, tags_json, source_uri,
                    engine_version, object_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clip.clip_id,
                    parent_clip_id,
                    parent["lineage_id"],
                    clip.revision,
                    clip.title,
                    None if clip.key is None else clip.key.tonic,
                    None if clip.key is None else clip.key.mode,
                    clip.bpm,
                    clip.instrument.role,
                    tags_json,
                    clip.provenance.source_uri,
                    clip.engine_version,
                    object_hash,
                    created_at,
                ),
            )
            if not object_path.parent.exists():
                try:
                    object_path.parent.mkdir()
                    created_object_directory = True
                except FileExistsError:
                    # A concurrent process may have created the same two-hex
                    # shard after the existence check.  Validate it below.
                    pass
            self._validate_object_shard(object_path.parent)
            if object_path.exists():
                if object_path.is_symlink() or not object_path.is_file():
                    raise RuntimeError("Clip object path is not a regular non-symlink file")
                if object_path.read_bytes() != payload:
                    raise RuntimeError(f"Hash collision or corrupt object at {object_path}")
            else:
                os.replace(temporary, object_path)
                published_here = True
            row = connection.execute(
                "SELECT * FROM clips WHERE clip_id = ?", (clip.clip_id,)
            ).fetchone()
            if row is None:
                raise RuntimeError("Transform append child row is missing")
            self._validate_catalog_append(
                connection,
                before_columns=before_columns,
                before_rows=before_rows,
                expected_child={
                    "clip_id": clip.clip_id,
                    "parent_clip_id": parent_clip_id,
                    "lineage_id": parent["lineage_id"],
                    "revision": clip.revision,
                    "title": clip.title,
                    "key_tonic": None if clip.key is None else clip.key.tonic,
                    "key_mode": None if clip.key is None else clip.key.mode,
                    "bpm": clip.bpm,
                    "role": clip.instrument.role,
                    "tags_json": tags_json,
                    "source_uri": clip.provenance.source_uri,
                    "engine_version": clip.engine_version,
                    "object_hash": object_hash,
                    "created_at": created_at,
                },
            )
            connection.commit()
            return ClipAppendResult(self._summary(row), replayed=False)
        except Exception:
            try:
                connection.rollback()
            except sqlite3.Error:
                # A failed commit may already have closed its transaction.  We
                # still perform the reference check and orphan cleanup below.
                pass
            if published_here:
                self._remove_unreferenced_object(object_hash)
            if created_object_directory:
                try:
                    object_path.parent.rmdir()
                except OSError:
                    pass
            raise
        finally:
            connection.close()
            temporary.unlink(missing_ok=True)

    def get(self, clip_id: str) -> MidiClip:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT object_hash FROM clips WHERE clip_id = ?", (clip_id,)
            ).fetchone()
        if row is None:
            raise KeyError(f"Unknown clip_id: {clip_id}")
        path = self.object_path(row["object_hash"])
        try:
            payload = path.read_bytes()
        except FileNotFoundError as exc:
            raise RuntimeError(f"Clip object is missing: {path}") from exc
        actual_hash = hashlib.sha256(payload).hexdigest()
        if actual_hash != row["object_hash"]:
            raise RuntimeError(f"Clip object checksum mismatch: {path}")
        clip = MidiClip.from_json(payload)
        if clip.clip_id != clip_id:
            raise RuntimeError(f"Catalog/object clip ID mismatch for {clip_id}")
        return clip

    def list(self, *, limit: int = 100, offset: int = 0) -> tuple[ClipSummary, ...]:
        limit, offset = _page(limit, offset)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM clips
                ORDER BY created_at DESC, clip_id ASC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        return tuple(self._summary(row) for row in rows)

    def search(
        self,
        text: str | None = None,
        *,
        key: KeySignature | str | None = None,
        mode: str | None = None,
        bpm: float | None = None,
        bpm_tolerance: float = 0.01,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        role: str | None = None,
        tags: Iterable[str] = (),
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[ClipSummary, ...]:
        clauses: list[str] = []
        values: list[object] = []
        if text and text.strip():
            pattern = f"%{text.strip()}%"
            clauses.append("(title LIKE ? COLLATE NOCASE OR tags_json LIKE ? COLLATE NOCASE OR source_uri LIKE ? COLLATE NOCASE)")
            values.extend((pattern, pattern, pattern))
        if isinstance(key, str):
            key = KeySignature.parse(key)
        if key is not None:
            clauses.extend(("key_tonic = ?", "key_mode = ?"))
            values.extend((key.tonic, key.mode))
        elif mode is not None:
            normalized_mode = mode.strip().lower()
            if normalized_mode not in {"major", "minor"}:
                raise ValueError("mode must be 'major' or 'minor'")
            clauses.append("key_mode = ?")
            values.append(normalized_mode)
        if bpm is not None:
            if bpm_tolerance < 0:
                raise ValueError("bpm_tolerance cannot be negative")
            clauses.append("bpm BETWEEN ? AND ?")
            values.extend((float(bpm) - bpm_tolerance, float(bpm) + bpm_tolerance))
        if bpm_min is not None:
            clauses.append("bpm >= ?")
            values.append(float(bpm_min))
        if bpm_max is not None:
            clauses.append("bpm <= ?")
            values.append(float(bpm_max))
        if role:
            clauses.append("role = ? COLLATE NOCASE")
            values.append(role.strip().lower())
        for tag in tags:
            clauses.append("tags_json LIKE ?")
            values.append(f'%"{str(tag).strip()}"%')
        limit, offset = _page(limit, offset)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        query = (
            "SELECT * FROM clips"
            + where
            + " ORDER BY created_at DESC, clip_id ASC LIMIT ? OFFSET ?"
        )
        values.extend((limit, offset))
        with self._connect() as connection:
            rows = connection.execute(query, values).fetchall()
        return tuple(self._summary(row) for row in rows)

    def versions(self, clip_id: str) -> tuple[ClipSummary, ...]:
        """Return every version/branch in the queried clip's lineage."""

        with self._connect() as connection:
            found = connection.execute(
                "SELECT lineage_id FROM clips WHERE clip_id = ?", (clip_id,)
            ).fetchone()
            if found is None:
                raise KeyError(f"Unknown clip_id: {clip_id}")
            rows = connection.execute(
                """
                SELECT * FROM clips WHERE lineage_id = ?
                ORDER BY revision ASC, created_at ASC, clip_id ASC
                """,
                (found["lineage_id"],),
            ).fetchall()
        return tuple(self._summary(row) for row in rows)

    # Descriptive aliases for UI/application code.
    list_clips = list
    list_versions = versions

    def _store_object(self, object_hash: str, payload: bytes) -> None:
        self._require_writable("store clip objects")
        path = self.object_path(object_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != payload:
                raise RuntimeError(f"Hash collision or corrupt object at {path}")
            return
        temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_bytes(payload)
            # Another process may win this race.  Replacing with identical bytes
            # is safe and leaves the catalog pointing at a complete object.
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def _remove_unreferenced_object(self, object_hash: str) -> None:
        """Remove an object published by a rolled-back append, if still orphaned."""

        connection = self._connect()
        try:
            # Keep the reference check and unlink under one writer lock.  A
            # concurrent append may already have staged identical bytes, but
            # it cannot commit a reference between this query and the unlink;
            # after the lock is released it will republish the missing object.
            connection.execute("BEGIN IMMEDIATE")
            referenced = connection.execute(
                "SELECT 1 FROM clips WHERE object_hash = ? LIMIT 1", (object_hash,)
            ).fetchone()
            if referenced is None:
                self.object_path(object_hash).unlink(missing_ok=True)
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            raise
        finally:
            connection.close()

    def _validate_append_paths(self) -> None:
        """Recheck that the narrow writer still targets its original real paths."""

        if not self.root.is_dir() or self.root.is_symlink():
            raise RuntimeError("Append-only clip library root changed")
        if not self.database_path.is_file() or self.database_path.is_symlink():
            raise RuntimeError("Append-only clip library database changed")
        if not self.objects_path.is_dir() or self.objects_path.is_symlink():
            raise RuntimeError("Append-only clip library objects directory changed")
        if self.objects_path.resolve() != self.root.resolve() / "objects":
            raise RuntimeError("Append-only clip library objects escaped the library root")

    def _validate_object_shard(self, shard: Path) -> None:
        if not shard.is_dir() or shard.is_symlink():
            raise RuntimeError("Clip object shard must be a real directory")
        if shard.parent != self.objects_path or not shard.resolve().is_relative_to(
            self.objects_path.resolve()
        ):
            raise RuntimeError("Clip object shard escaped the objects directory")

    @staticmethod
    def _catalog_rows(
        connection: sqlite3.Connection,
    ) -> tuple[tuple[str, ...], dict[str, tuple[object, ...]]]:
        """Capture every catalog column for an exact in-transaction comparison."""

        columns = tuple(
            str(row["name"])
            for row in connection.execute("PRAGMA table_info(clips)").fetchall()
        )
        rows = connection.execute("SELECT * FROM clips ORDER BY clip_id ASC").fetchall()
        return columns, {
            str(row["clip_id"]): tuple(row[column] for column in columns)
            for row in rows
        }

    @classmethod
    def _validate_catalog_append(
        cls,
        connection: sqlite3.Connection,
        *,
        before_columns: tuple[str, ...],
        before_rows: dict[str, tuple[object, ...]],
        expected_child: dict[str, object],
    ) -> None:
        """Prove the requested child is the transaction's only catalog effect."""

        after_columns, after_rows = cls._catalog_rows(connection)
        child_id = str(expected_child["clip_id"])
        if after_columns != before_columns:
            raise RuntimeError("Clip library schema changed during transform append")
        if len(after_rows) > MAXIMUM_CLIP_COUNT:
            raise RuntimeError("Clip library maximum clip count exceeded")
        if set(after_rows) != set(before_rows) | {child_id}:
            raise RuntimeError("Transform append changed an unexpected Clip-library row")
        if len(after_rows) != len(before_rows) + 1:
            raise RuntimeError("Transform append did not add exactly one Clip-library row")
        if any(after_rows.get(clip_id) != row for clip_id, row in before_rows.items()):
            raise RuntimeError("Existing Clip metadata changed during transform append")

        child_row = connection.execute(
            "SELECT * FROM clips WHERE clip_id = ?", (child_id,)
        ).fetchone()
        if child_row is None or any(
            child_row[column] != expected
            for column, expected in expected_child.items()
        ):
            raise RuntimeError("Transform append child metadata does not match its projection")

    @staticmethod
    def _catalog_state_sha256(connection: sqlite3.Connection) -> str:
        rows = connection.execute(
            """
            SELECT clip_id, parent_clip_id, lineage_id, revision,
                   object_hash, created_at
            FROM clips
            ORDER BY clip_id ASC
            """
        ).fetchall()
        document = {
            "schema": "sunofriend.workbench-clip-library-state.v1",
            "clips": [
                {
                    "clip_id": row["clip_id"],
                    "parent_clip_id": row["parent_clip_id"],
                    "lineage_id": row["lineage_id"],
                    "revision": row["revision"],
                    "object_sha256": row["object_hash"],
                    "created_at": row["created_at"],
                    "canonical_sha256": row["object_hash"],
                }
                for row in rows
            ],
        }
        encoded = json.dumps(
            document,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _summary(row: sqlite3.Row) -> ClipSummary:
        key = None
        if row["key_tonic"] is not None:
            key = f"{row['key_tonic']} {row['key_mode']}"
        return ClipSummary(
            clip_id=row["clip_id"],
            title=row["title"],
            revision=row["revision"],
            parent_clip_id=row["parent_clip_id"],
            lineage_id=row["lineage_id"],
            key=key,
            bpm=row["bpm"],
            role=row["role"],
            tags=tuple(json.loads(row["tags_json"])),
            engine_version=row["engine_version"],
            object_hash=row["object_hash"],
            created_at=row["created_at"],
        )


def _page(limit: int, offset: int) -> tuple[int, int]:
    limit = int(limit)
    offset = int(offset)
    if not 1 <= limit <= 10_000:
        raise ValueError("limit must be between 1 and 10000")
    if offset < 0:
        raise ValueError("offset cannot be negative")
    return limit, offset


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


__all__ = [
    "ClipAppendResult",
    "ClipLibrary",
    "ClipSummary",
    "MAXIMUM_CLIP_COUNT",
]
