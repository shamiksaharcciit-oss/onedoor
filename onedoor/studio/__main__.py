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
    default_db = "onedoor.db"
    # `default=None` rather than `default=default_db`: R086 §2D needs to know whether
    # `--db` was TYPED, not whether its value happens to equal the default string. An
    # operator who typed `--db onedoor.db` named it and should not be doubted; comparing
    # the parsed value against `default_db` would have called that "defaulted" too.
    # `args.db is None` is the only reliable signal argparse gives for "absent from argv".
    parser.add_argument("--db", default=None, help="the enforcer's store (read + ratify)")
    parser.add_argument("--studio-db", default=DEFAULT_STUDIO_DB, help="the drafts store")
    parser.add_argument("--host", default=DEFAULT_HOST, help="loopback only; anything else refused")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)
    db_defaulted = args.db is None
    db_path = args.db if args.db is not None else default_db
    try:
        serve(
            db_path,
            args.studio_db,
            host=args.host,
            port=args.port,
            db_defaulted=db_defaulted,
        )
    except BindRefused as exc:
        print(f"onedoor studio: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
