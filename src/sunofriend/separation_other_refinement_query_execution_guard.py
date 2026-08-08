"""Reusable effects guard for restricted Banquet execution processes.

The guard is deliberately one-way because Python audit hooks cannot be removed.
Install it once, after resolving and hashing the two approved checkpoints, in a
short-lived process that also has operating-system network denial.  It permits
only the exact weights-only CPU ``torch.load`` contract and rejects audio opens,
extra checkpoints and Python network APIs.
"""

from __future__ import annotations

import os
from pathlib import Path
import socket
import sys
from typing import Any, Iterable
import urllib.request

import torch


AUDIO_SUFFIXES = (".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".wav")
CHECKPOINT_SUFFIXES = (".ckpt", ".pt", ".pth", ".safetensors")


class QueryRestrictedExecutionGuard:
    """Install irreversible process guards and retain objective attempt counts."""

    def __init__(self, allowed_checkpoint_paths: Iterable[Path], *, phase: str) -> None:
        paths = tuple(path.resolve() for path in allowed_checkpoint_paths)
        if len(paths) != 2 or len(set(paths)) != 2:
            raise ValueError("query execution requires exactly two checkpoint paths")
        if not phase:
            raise ValueError("query execution guard phase is required")
        self.allowed_checkpoint_paths = frozenset(paths)
        self.phase = phase
        self.network_attempts: list[str] = []
        self.audio_open_attempts: list[str] = []
        self.unapproved_checkpoint_open_attempts: list[str] = []
        self.load_calls: list[str] = []
        self._real_torch_load = torch.load
        self._installed = False

    def _audit(self, event: str, event_args: tuple[Any, ...]) -> None:
        if event.startswith("socket."):
            self.network_attempts.append(event)
            raise RuntimeError(
                f"network operation forbidden during {self.phase}: {event}"
            )
        if event != "open" or not event_args:
            return
        target = event_args[0]
        if not isinstance(target, (str, bytes)):
            return
        path = Path(os.fsdecode(target)).resolve()
        text = str(path).lower()
        if text.endswith(AUDIO_SUFFIXES):
            self.audio_open_attempts.append(text)
            raise RuntimeError(f"audio open forbidden during {self.phase}")
        if text.endswith(CHECKPOINT_SUFFIXES):
            if path not in self.allowed_checkpoint_paths:
                self.unapproved_checkpoint_open_attempts.append(text)
                raise RuntimeError(
                    f"unapproved checkpoint open during {self.phase}"
                )

    def _deny_network(self, *_args: Any, **_kwargs: Any) -> Any:
        self.network_attempts.append("python_network_api")
        raise RuntimeError(f"network API forbidden during {self.phase}")

    def _restricted_torch_load(
        self, path: str | Path, *args: Any, **kwargs: Any
    ) -> Any:
        resolved = Path(path).resolve()
        if resolved not in self.allowed_checkpoint_paths:
            raise RuntimeError("torch.load path is outside the two approved checkpoints")
        if args or kwargs != {"weights_only": True, "map_location": "cpu"}:
            raise RuntimeError("torch.load must use the exact weights-only CPU contract")
        self.load_calls.append(str(resolved))
        return self._real_torch_load(
            resolved,
            weights_only=True,
            map_location="cpu",
        )

    def install(self) -> None:
        """Install the one-way guard once in this short-lived process."""

        if self._installed:
            raise RuntimeError("query execution guard is already installed")
        sys.addaudithook(self._audit)
        socket.create_connection = self._deny_network
        socket.getaddrinfo = self._deny_network
        urllib.request.urlopen = self._deny_network
        torch.load = self._restricted_torch_load
        self._installed = True

    def assert_no_forbidden_effects(self) -> None:
        """Fail closed if a forbidden attempt was somehow retained."""

        if (
            self.network_attempts
            or self.audio_open_attempts
            or self.unapproved_checkpoint_open_attempts
        ):
            raise RuntimeError(f"{self.phase} crossed an effects boundary")

    def report(self) -> dict[str, int | bool]:
        """Return fields shared by restricted load and synthetic reports."""

        return {
            "os_network_denial_required": True,
            "network_attempts": len(self.network_attempts),
            "audio_open_attempts": len(self.audio_open_attempts),
            "unapproved_checkpoint_open_attempts": len(
                self.unapproved_checkpoint_open_attempts
            ),
            "restricted_torch_load_calls": len(self.load_calls),
            "pretrained_network_resolution": False,
        }


__all__ = ["QueryRestrictedExecutionGuard"]
