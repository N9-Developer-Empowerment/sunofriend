"""Filesystem and network guard for the approved private reference canary."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import sys
from typing import Any, Iterable
import urllib.request

import torch

from .separation_other_refinement_query_execution_guard import (
    AUDIO_SUFFIXES,
    CHECKPOINT_SUFFIXES,
)


class QueryReferenceExecutionGuard:
    """Permit only the exact approved audio/checkpoint effects in one process."""

    def __init__(
        self,
        checkpoint_paths: Iterable[Path],
        audio_input_paths: Iterable[Path],
        audio_output_paths: Iterable[Path],
    ) -> None:
        checkpoints = frozenset(path.resolve() for path in checkpoint_paths)
        inputs = frozenset(path.resolve() for path in audio_input_paths)
        outputs = frozenset(path.resolve() for path in audio_output_paths)
        if len(checkpoints) != 2:
            raise ValueError("reference guard requires two checkpoints")
        if len(inputs) != 6:
            raise ValueError("reference guard requires six audio inputs")
        if len(outputs) != 36 or inputs & outputs:
            raise ValueError("reference guard requires 36 distinct audio outputs")
        self.checkpoint_paths = checkpoints
        self.audio_input_paths = inputs
        self.audio_output_paths = outputs
        self.network_attempts: list[str] = []
        self.forbidden_audio_attempts: list[str] = []
        self.unapproved_checkpoint_attempts: list[str] = []
        self.approved_audio_open_events = 0
        self.load_calls: list[str] = []
        self._real_torch_load = torch.load
        self._installed = False

    @staticmethod
    def _is_write(event_args: tuple[Any, ...]) -> bool:
        mode = event_args[1] if len(event_args) > 1 else None
        flags = event_args[2] if len(event_args) > 2 else 0
        if isinstance(mode, str) and any(token in mode for token in "wax+"):
            return True
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        return isinstance(flags, int) and bool(flags & write_flags)

    def _audit(self, event: str, event_args: tuple[Any, ...]) -> None:
        if event.startswith("socket."):
            self.network_attempts.append(event)
            raise RuntimeError(f"network operation forbidden in reference canary: {event}")
        if event != "open" or not event_args:
            return
        target = event_args[0]
        if not isinstance(target, (str, bytes)):
            return
        path = Path(os.fsdecode(target)).resolve()
        lower = str(path).lower()
        if lower.endswith(AUDIO_SUFFIXES):
            writing = self._is_write(event_args)
            permitted = (path in self.audio_input_paths and not writing) or (
                path in self.audio_output_paths
            )
            if not permitted:
                self.forbidden_audio_attempts.append(str(path))
                raise RuntimeError("audio path or mode is outside the reference approval")
            self.approved_audio_open_events += 1
        if lower.endswith(CHECKPOINT_SUFFIXES) and path not in self.checkpoint_paths:
            self.unapproved_checkpoint_attempts.append(str(path))
            raise RuntimeError("checkpoint path is outside the reference approval")

    def _deny_network(self, *_args: Any, **_kwargs: Any) -> Any:
        self.network_attempts.append("python_network_api")
        raise RuntimeError("network API forbidden in reference canary")

    def _restricted_torch_load(
        self, path: str | Path, *args: Any, **kwargs: Any
    ) -> Any:
        resolved = Path(path).resolve()
        if resolved not in self.checkpoint_paths:
            raise RuntimeError("torch.load path is outside the approved checkpoints")
        if args or kwargs != {"weights_only": True, "map_location": "cpu"}:
            raise RuntimeError("torch.load must use the weights-only CPU contract")
        self.load_calls.append(str(resolved))
        return self._real_torch_load(
            resolved,
            weights_only=True,
            map_location="cpu",
        )

    def install(self) -> None:
        if self._installed:
            raise RuntimeError("reference execution guard is already installed")
        sys.addaudithook(self._audit)
        socket.create_connection = self._deny_network
        socket.getaddrinfo = self._deny_network
        urllib.request.urlopen = self._deny_network
        torch.load = self._restricted_torch_load
        self._installed = True

    def assert_no_forbidden_effects(self) -> None:
        if (
            self.network_attempts
            or self.forbidden_audio_attempts
            or self.unapproved_checkpoint_attempts
        ):
            raise RuntimeError("reference canary crossed an effects boundary")

    def report(self) -> dict[str, int | bool]:
        return {
            "os_network_denial_required": True,
            "network_attempts": len(self.network_attempts),
            "forbidden_audio_attempts": len(self.forbidden_audio_attempts),
            "unapproved_checkpoint_attempts": len(
                self.unapproved_checkpoint_attempts
            ),
            "approved_audio_open_events": self.approved_audio_open_events,
            "restricted_torch_load_calls": len(self.load_calls),
            "pretrained_network_resolution": False,
        }


__all__ = ["QueryReferenceExecutionGuard"]
