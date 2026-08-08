#!/usr/bin/env python3
"""Download the Mega-53 target wheel closure under one aggregate byte cap."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import resource
import subprocess
import time


DIRECT_REQUIREMENTS = (
    "torch==2.2.2",
    "mlx==0.31.2",
    "mlx-spectro==0.7.0",
    "numpy==1.26.4",
    "soundfile==0.14.0",
    "ml-collections==1.1.0",
    "tqdm==4.70.0",
    "beartype==0.22.9",
    "rotary-embedding-torch==0.8.9",
    "einops==0.8.2",
    "PyYAML==6.0.3",
    "requests==2.34.2",
    "packaging==26.3",
)


def tree_bytes(root: Path) -> int:
    total = 0
    for directory, _, filenames in os.walk(root):
        for filename in filenames:
            path = Path(directory, filename)
            if not path.is_symlink():
                total += path.stat().st_size
    return total


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    parser.add_argument("--destination", required=True)
    parser.add_argument("--report")
    parser.add_argument("--cap-bytes", type=int, default=1_610_612_736)
    args = parser.parse_args()
    root = Path(args.destination).resolve()
    if root.exists():
        raise SystemExit("runtime wheel download destination must be fresh")
    root.mkdir(parents=True)
    wheels = root / "wheels"
    temporary = root / "tmp"
    wheels.mkdir()
    temporary.mkdir()
    log_path = root / "PIP-DOWNLOAD.log"
    command = [
        args.python,
        "-m",
        "pip",
        "download",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--only-binary=:all:",
        "--platform",
        "macosx_14_0_arm64",
        "--python-version",
        "3.12",
        "--implementation",
        "cp",
        "--abi",
        "cp312",
        "--dest",
        str(wheels),
        *DIRECT_REQUIREMENTS,
    ]
    environment = dict(os.environ)
    environment.update(
        {
            "TMPDIR": str(temporary),
            "PIP_DISABLE_PIP_VERSION_CHECK": "1",
            "PIP_NO_INPUT": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )

    def limit_single_file() -> None:
        resource.setrlimit(resource.RLIMIT_FSIZE, (args.cap_bytes, args.cap_bytes))

    started = datetime.now(timezone.utc)
    peak_bytes = tree_bytes(root)
    cap_exceeded = False
    with log_path.open("wb") as log:
        process = subprocess.Popen(
            command,
            cwd=root,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            preexec_fn=limit_single_file,
        )
        while process.poll() is None:
            observed = tree_bytes(root)
            peak_bytes = max(peak_bytes, observed)
            if observed > args.cap_bytes:
                cap_exceeded = True
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                break
            time.sleep(0.05)
        return_code = process.wait()
    final_staged_bytes = tree_bytes(root)
    peak_bytes = max(peak_bytes, final_staged_bytes)
    if cap_exceeded or peak_bytes > args.cap_bytes:
        raise SystemExit(
            f"runtime wheel evidence exceeded the {args.cap_bytes}-byte approval cap"
        )
    if return_code != 0:
        raise SystemExit(
            f"pip download failed with exit code {return_code}; see {log_path}"
        )
    downloaded = sorted(path.name for path in wheels.iterdir())
    if not downloaded or any(not name.endswith(".whl") for name in downloaded):
        raise SystemExit("pip did not produce an all-wheel closure")
    report = {
        "schema": "sunofriend.mega53-runtime-wheel-download.v1",
        "status": "evidence_only_download_complete_not_installed",
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "approved_cap_bytes": args.cap_bytes,
        "peak_staged_bytes": peak_bytes,
        "final_staged_bytes": final_staged_bytes,
        "target": {
            "platform": "macosx_14_0_arm64",
            "python": "3.12",
            "implementation": "cp",
            "abi": "cp312",
        },
        "runtime_source": {
            "repository": "https://github.com/openmirlab/bs-roformer-infer",
            "revision": "de35ada5817b878da0194ee2860253dda3a9c2b2",
            "git_archive_sha256": (
                "e64fe7733a45f5efc53091bbc2ab6dd04a0ee7373a639f1c9b27275502f26691"
            ),
            "installed_or_built": False,
        },
        "direct_requirements": list(DIRECT_REQUIREMENTS),
        "artifact_count": len(downloaded),
        "artifact_filenames": downloaded,
        "effects": {
            "network_used_for_approved_download": True,
            "dependency_installed": False,
            "package_imported": False,
            "checkpoint_loaded": False,
            "model_constructed": False,
            "inference_runs": 0,
            "audio_reads": 0,
            "public_activation": False,
            "source_selection": False,
            "midi_created": False,
            "hosting": False,
            "redistribution": False,
        },
    }
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.report:
        report_path = Path(args.report).resolve()
        if report_path.parent != root:
            raise SystemExit("download report must be written inside the evidence root")
        report_path.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
