"""Compute (and write) `PACK_DIGEST`. `python -m scripts.pack_digest [--write]`.

X-11: **digests are computed into documents by tooling, never retyped.** This is the
tooling. It exists so that the constant in `onedoor/templates/__init__.py` is a value
someone generated rather than a value someone believed, and so that
`tests/templates/test_pack_identity.py` is comparing a generated number against the
files rather than a typed number against a typo.

The same shape as `viewer/tokens.py`'s `SPEC_DIGEST`, for the same reason: a shipped
artifact that drifts quietly is the failure this product exists to prevent, and a digest
nobody regenerates is a comment.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from onedoor import templates

CONSTANT = re.compile(r'^PACK_DIGEST = "[0-9a-f]{64}"$', re.M)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.pack_digest", description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="update the constant in onedoor/templates/__init__.py"
    )
    args = parser.parse_args(argv)

    digest = templates.PAYMENTS.file_digest()
    source = Path(templates.__file__)
    text = source.read_text(encoding="utf-8")
    current = CONSTANT.search(text)
    if current is None:
        print("PACK_DIGEST constant not found in onedoor/templates/__init__.py", file=sys.stderr)
        return 2

    print(f"pack:      {templates.PAYMENTS.name}")
    print(f"files:     {', '.join(templates.PACK_FILES)}")
    print(f"computed:  {digest}")
    print(f"committed: {templates.PACK_DIGEST}")

    if digest == templates.PACK_DIGEST:
        print("MATCH")
        return 0
    if not args.write:
        print("DRIFT — rerun with --write once you have looked at what changed", file=sys.stderr)
        return 1
    source.write_text(
        CONSTANT.sub(f'PACK_DIGEST = "{digest}"', text, count=1), encoding="utf-8", newline="\n"
    )
    print("WROTE")
    return 0


if __name__ == "__main__":  # pragma: no cover - the entry point
    raise SystemExit(main())
