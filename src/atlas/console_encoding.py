"""Windows' console defaults to cp1252; a single unicode character in a log line (a
non-breaking hyphen, an em-dash pulled from a paper's title) otherwise crashes the whole
process with a raw UnicodeEncodeError. Call this once, as early as possible, in every
process entrypoint — cli.py and api/main.py both do.
"""

from __future__ import annotations

import contextlib
import sys


def fix_windows_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
