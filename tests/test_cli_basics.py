from __future__ import annotations

import io
import unittest
from contextlib import redirect_stdout

from sunofriend import __version__
from sunofriend.cli import main


class CliBasicsTests(unittest.TestCase):
    def test_version_uses_the_package_version(self) -> None:
        stdout = io.StringIO()
        with redirect_stdout(stdout), self.assertRaises(SystemExit) as raised:
            main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), f"sunofriend {__version__}")


if __name__ == "__main__":
    unittest.main()
