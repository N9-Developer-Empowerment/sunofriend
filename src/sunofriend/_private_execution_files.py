"""Process-local creation policy for private execution artifacts."""

from __future__ import annotations

import os


def restrict_private_file_creation() -> None:
    """Make every subsequently created file or directory owner-only by default.

    Private execution happens in a dedicated process.  The mask intentionally
    remains active for that process so recursive ``mkdir`` calls cannot leave
    intermediate aggregate directories group- or world-readable.
    """

    os.umask(0o077)


__all__ = ["restrict_private_file_creation"]
