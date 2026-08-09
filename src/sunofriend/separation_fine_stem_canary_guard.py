"""Exact filesystem/network guard for one bounded fine-stem canary process."""

from __future__ import annotations

import os
from pathlib import Path
import socket
import sys
from typing import Any, Iterable
import urllib.request


AUDIO_SUFFIXES = (".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".wav")
CHECKPOINT_SUFFIXES = (".ckpt", ".pt", ".pth", ".safetensors")


class FineStemCanaryExecutionGuard:
    """Permit one checkpoint, exact audio paths and a fixed forward-call budget."""

    def __init__(
        self,
        checkpoint: Path,
        *,
        audio_inputs: Iterable[Path],
        audio_outputs: Iterable[Path],
        expected_forward_calls: int,
    ) -> None:
        self.checkpoint = checkpoint.resolve()
        self.audio_inputs = frozenset(path.resolve() for path in audio_inputs)
        self.audio_outputs = frozenset(path.resolve() for path in audio_outputs)
        if not self.audio_inputs or self.audio_inputs & self.audio_outputs:
            raise ValueError("fine-stem canary audio authority differs")
        if expected_forward_calls <= 0:
            raise ValueError("fine-stem canary forward authority differs")
        self.expected_forward_calls = expected_forward_calls
        self.forward_calls = 0
        self.network_attempts = []
        self.local_socket_constructions = []
        self.forbidden_audio_attempts = []
        self.external_checkpoint_attempts = []
        self.approved_audio_open_events = 0
        self.load_calls = []
        self._real_torch_load = None
        self._installed = False

    @staticmethod
    def _is_write(event_args: tuple[Any, ...]) -> bool:
        mode = event_args[1] if len(event_args) > 1 else None
        flags = event_args[2] if len(event_args) > 2 else 0
        if isinstance(mode, str) and any(token in mode for token in "wax+"):
            return True
        write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        return isinstance(flags, int) and bool(flags & write_flags)

    def record_forward(self) -> None:
        if self.forward_calls >= self.expected_forward_calls:
            raise RuntimeError("fine-stem canary forward authority is exhausted")
        self.forward_calls += 1

    def _audit(self, event: str, event_args: tuple[Any, ...]) -> None:
        # urllib3 performs an import-time IPv6 capability probe by constructing
        # an unconnected local socket. Construction is not network resolution,
        # connection or transfer; subsequent socket operations remain denied.
        if event == "socket.__new__":
            self.local_socket_constructions.append(event)
            return
        if event.startswith("socket."):
            self.network_attempts.append(event)
            raise RuntimeError("network operation forbidden in fine-stem canary")
        if event != "open" or not event_args:
            return
        target = event_args[0]
        if not isinstance(target, (str, bytes)):
            return
        path = Path(os.fsdecode(target)).resolve()
        lower = str(path).lower()
        if lower.endswith(AUDIO_SUFFIXES):
            writing = self._is_write(event_args)
            permitted = (path in self.audio_inputs and not writing) or (
                path in self.audio_outputs
            )
            if not permitted:
                self.forbidden_audio_attempts.append(str(path))
                raise RuntimeError("audio path is outside fine-stem canary authority")
            self.approved_audio_open_events += 1
        if lower.endswith(CHECKPOINT_SUFFIXES) and path != self.checkpoint:
            self.external_checkpoint_attempts.append(str(path))
            raise RuntimeError("checkpoint is outside fine-stem canary authority")

    def _deny_network(self, *_args: Any, **_kwargs: Any) -> Any:
        self.network_attempts.append("python_network_api")
        raise RuntimeError("network API forbidden in fine-stem canary")

    def _restricted_torch_load(
        self, path: Any, *args: Any, **kwargs: Any
    ) -> Any:
        if Path(path).resolve() != self.checkpoint:
            raise RuntimeError("torch.load path is outside fine-stem authority")
        if args or kwargs != {"weights_only": True, "map_location": "cpu"}:
            raise RuntimeError("torch.load must use the exact weights-only CPU contract")
        if self.load_calls:
            raise RuntimeError("fine-stem checkpoint may be loaded exactly once")
        self.load_calls.append(str(self.checkpoint))
        return self._real_torch_load(
            self.checkpoint, weights_only=True, map_location="cpu"
        )

    def install(self) -> None:
        if self._installed:
            raise RuntimeError("fine-stem canary guard is already installed")
        import torch

        self._real_torch_load = torch.load
        sys.addaudithook(self._audit)
        socket.create_connection = self._deny_network
        socket.getaddrinfo = self._deny_network
        urllib.request.urlopen = self._deny_network
        torch.load = self._restricted_torch_load
        self._installed = True

    def assert_complete(self) -> None:
        if self.load_calls != [str(self.checkpoint)]:
            raise RuntimeError("fine-stem canary checkpoint load count differs")
        if (
            self.network_attempts
            or self.forbidden_audio_attempts
            or self.external_checkpoint_attempts
            or self.forward_calls != self.expected_forward_calls
        ):
            raise RuntimeError("fine-stem canary crossed its effects boundary")

    def report(self) -> dict[str, Any]:
        return {
            "network_attempts": len(self.network_attempts),
            "local_socket_constructions": len(self.local_socket_constructions),
            "forbidden_audio_attempts": len(self.forbidden_audio_attempts),
            "external_checkpoint_attempts": len(
                self.external_checkpoint_attempts
            ),
            "approved_audio_open_events": self.approved_audio_open_events,
            "restricted_torch_load_calls": len(self.load_calls),
            "forward_calls": self.forward_calls,
            "expected_forward_calls": self.expected_forward_calls,
            "os_network_denial_required": True,
        }


__all__ = ["FineStemCanaryExecutionGuard"]
