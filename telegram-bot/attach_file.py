#!/usr/bin/env python3
"""Copy file(s) into pending_attachments for the next bot reply."""

import os
import shutil
import sys
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PENDING_ATTACHMENTS_DIR = os.path.join(SCRIPT_DIR, "pending_attachments")


def main():
    if len(sys.argv) < 2:
        print("Usage: attach_file.py <file> [file ...]", file=sys.stderr)
        sys.exit(1)
    os.makedirs(PENDING_ATTACHMENTS_DIR, mode=0o700, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    for i, src in enumerate(sys.argv[1:]):
        if not os.path.isfile(src):
            print("attach_file: not a file:", src, file=sys.stderr)
            continue
        base = os.path.basename(src)
        name, ext = os.path.splitext(base)
        dest_name = "%s_%s_%s%s" % (name, stamp, i, ext) if i else "%s_%s%s" % (name, stamp, ext)
        dest = os.path.join(PENDING_ATTACHMENTS_DIR, dest_name)
        shutil.copy2(src, dest)
        print(dest)


if __name__ == "__main__":
    main()
