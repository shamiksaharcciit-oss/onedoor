"""`python -m onedoor.studio` — run the policy canvas (ND-052 / S3-T2).

Loopback only. The host flag exists so a deployer can choose `::1` over `127.0.0.1`,
not so they can choose a routable address: `server.require_loopback` refuses anything
else **before a socket exists**, and there is no flag that turns the refusal off,
because a flag that turns it off is the config drift it exists to catch.
"""

from __future__ import annotations

import argparse
import sys

from onedoor.studio.server import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_STUDIO_DB, BindRefused, serve


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m onedoor.studio", description=__doc__)
    parser.add_argument("--db", default="onedoor.db", help="the enforcer's store (read + ratify)")
    parser.add_argument("--studio-db", default=DEFAULT_STUDIO_DB, help="the drafts store")
    parser.add_argument("--host", default=DEFAULT_HOST, help="loopback only; anything else refused")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    try:
        serve(args.db, args.studio_db, host=args.host, port=args.port)
    except BindRefused as exc:
        print(f"onedoor studio: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
