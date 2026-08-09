"""One-checkpoint effects guard for the Mega-53 construction/load process."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import sys
from typing import Any
import urllib.request

import torch


AUDIO_SUFFIXES = (".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".wav")
CHECKPOINT_SUFFIXES = (".ckpt", ".pt", ".pth", ".safetensors")


class Mega53RestrictedExecutionGuard:
    """Allow one exact weights-only load and reject network, audio and other models."""

    def __init__(self, checkpoint: Path) -> None:
        self.checkpoint = checkpoint.resolve()
        self.network_attempts: list[str] = []
        self.audio_open_attempts: list[str] = []
        self.external_checkpoint_open_attempts: list[str] = []
        self.load_calls: list[str] = []
        self.forward_calls = 0
        self._real_torch_load = torch.load
        self._installed = False

    def _audit(self, event: str, args: tuple[Any, ...]) -> None:
        if event.startswith("socket."):
            self.network_attempts.append(event)
            raise RuntimeError(f"network operation forbidden during Mega-53 load: {event}")
        if event != "open" or not args or not isinstance(args[0], (str, bytes)):
            return
        path = Path(os.fsdecode(args[0])).resolve()
        lower = str(path).lower()
        if lower.endswith(AUDIO_SUFFIXES):
            self.audio_open_attempts.append(lower)
            raise RuntimeError("audio open forbidden during Mega-53 model load")
        if lower.endswith(CHECKPOINT_SUFFIXES) and path != self.checkpoint:
            self.external_checkpoint_open_attempts.append(lower)
            raise RuntimeError("external checkpoint open forbidden during Mega-53 load")

    def _deny_network(self, *_args: Any, **_kwargs: Any) -> Any:
        self.network_attempts.append("python_network_api")
        raise RuntimeError("network API forbidden during Mega-53 model load")

    def _restricted_torch_load(
        self, path: str | Path, *args: Any, **kwargs: Any
    ) -> Any:
        if Path(path).resolve() != self.checkpoint:
            raise RuntimeError("torch.load path is outside the approved Mega-53 checkpoint")
        if args or kwargs != {"weights_only": True, "map_location": "cpu"}:
            raise RuntimeError("torch.load must use the exact weights-only CPU contract")
        if self.load_calls:
            raise RuntimeError("Mega-53 checkpoint may be loaded exactly once")
        self.load_calls.append(str(self.checkpoint))
        return self._real_torch_load(
            self.checkpoint, weights_only=True, map_location="cpu"
        )

    def install(self) -> None:
        if self._installed:
            raise RuntimeError("Mega-53 execution guard is already installed")
        sys.addaudithook(self._audit)
        socket.create_connection = self._deny_network
        socket.getaddrinfo = self._deny_network
        urllib.request.urlopen = self._deny_network
        torch.load = self._restricted_torch_load
        self._installed = True

    def assert_complete(self) -> None:
        if self.load_calls != [str(self.checkpoint)]:
            raise RuntimeError("Mega-53 restricted load count differs")
        if (
            self.network_attempts
            or self.audio_open_attempts
            or self.external_checkpoint_open_attempts
            or self.forward_calls
        ):
            raise RuntimeError("Mega-53 model load crossed a forbidden effects boundary")

    def report(self) -> dict[str, int | bool]:
        return {
            "audio_open_attempts": len(self.audio_open_attempts),
            "external_checkpoint_open_attempts": len(
                self.external_checkpoint_open_attempts
            ),
            "network_attempts": len(self.network_attempts),
            "os_network_denial_required": True,
            "restricted_torch_load_calls": len(self.load_calls),
            "forward_calls": self.forward_calls,
        }


__all__ = ["Mega53RestrictedExecutionGuard"]
