#!/usr/bin/env python3
"""Queue image(s) for the next Telegram reply (alias of attach_file for images)."""

from __future__ import annotations

import os
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ATTACH = os.path.join(SCRIPT_DIR, "attach_file.py")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: attach_image.py <image> [image ...]", file=sys.stderr)
        sys.exit(1)
    rc = subprocess.call([sys.executable, ATTACH] + sys.argv[1:])
    sys.exit(rc)


if __name__ == "__main__":
    main()
