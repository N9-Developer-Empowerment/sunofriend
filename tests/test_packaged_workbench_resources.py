from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class PackagedWorkbenchResourcesTests(unittest.TestCase):
    def test_installed_wheel_exposes_workbench_resources_to_cli(self) -> None:
        repository = Path(__file__).resolve().parents[1]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dist = root / "dist"
            installed = root / "installed"
            project = root / "empty-project"
            project.mkdir()
            (project / "smoke-keys.wav").write_bytes(b"RIFF-packaging-smoke")

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "build",
                    "--wheel",
                    "--no-isolation",
                    "--outdir",
                    str(dist),
                ],
                cwd=repository,
                check=True,
                capture_output=True,
                text=True,
            )
            wheels = list(dist.glob("sunofriend-*.whl"))
            self.assertEqual(len(wheels), 1)

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--no-compile",
                    "--no-deps",
                    "--target",
                    str(installed),
                    str(wheels[0]),
                ],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )

            probe = textwrap.dedent(
                """
                import io
                import json
                import sys
                from contextlib import redirect_stdout
                from pathlib import Path

                import sunofriend
                from sunofriend.cli import main
                from sunofriend.workbench_server import (
                    _workbench_html_bytes,
                    _workbench_transport_bytes,
                    _workbench_visualization_bytes,
                )

                installed = Path(sys.argv[1]).resolve()
                project = Path(sys.argv[2]).resolve()
                package = Path(sunofriend.__file__).resolve().parent
                package.relative_to(installed)

                loaders = {
                    "workbench.html": _workbench_html_bytes,
                    "workbench_transport.js": _workbench_transport_bytes,
                    "workbench_visualization.js": _workbench_visualization_bytes,
                }
                for name, load in loaders.items():
                    resource = package / name
                    assert resource.is_file(), name
                    payload = load()
                    assert payload == resource.read_bytes(), name
                    assert payload.strip(), name

                stdout = io.StringIO()
                with redirect_stdout(stdout):
                    status = main(["workbench", str(project), "--inspect"])
                report = json.loads(stdout.getvalue())
                assert status == 0
                assert report["status"] == "inspected"
                assert report["server_started"] is False
                """
            )
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(installed)
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    probe,
                    str(installed),
                    str(project),
                ],
                cwd=root,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
