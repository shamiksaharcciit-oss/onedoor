"""`create_app` installs a filter on uvicorn's own
`uvicorn.access` logger that redacts a by-link token out of the real
request line -- this module's own `log` already redacted it before this filter was added, but
`uvicorn.access` is a separate logger this module never
writes to, and it logs the real request line regardless of what any
handler does.

Tested against uvicorn's own `AccessFormatter`, with the exact format
string and record shape (`record.args` as `(client_addr, method,
full_path, http_version, status_code)`) its own default logging config
uses -- not a hand-rolled mock of what uvicorn might do.
"""

from __future__ import annotations

import io
import logging
import tempfile
from pathlib import Path

import pytest
from uvicorn.config import LOGGING_CONFIG
from uvicorn.logging import AccessFormatter

from onedoor.service.app import _ByLinkTokenRedactingFilter, create_app

ROOT = Path(__file__).parent.parent.parent
REAL_TOKEN = "a" * 60  # token-shaped: long, never appears in the output


def _formatted_access_line(path: str) -> str:
    logger = logging.getLogger("uvicorn.access")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(AccessFormatter(LOGGING_CONFIG["formatters"]["access"]["fmt"]))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        logger.info(
            '%s - "%s %s HTTP/%s" %d',
            "127.0.0.1:12345",
            "POST",
            path,
            "1.1",
            200,
        )
    finally:
        logger.removeHandler(handler)
    return stream.getvalue()


@pytest.fixture(autouse=True)
def _create_app_once() -> None:
    """Installing the filter is `create_app`'s own job -- exercised exactly
    as a deployment would trigger it, not by calling the filter directly."""
    create_app(
        db_path=tempfile.mktemp(suffix=".db"), policies=str(ROOT / "config" / "policies.yaml")
    )


def test_a_by_link_token_in_the_real_request_line_is_redacted() -> None:
    line = _formatted_access_line(f"/v1/approvals/by-link/{REAL_TOKEN}")
    assert REAL_TOKEN not in line
    assert "/v1/approvals/by-link/<token>" in line


def test_an_unrelated_request_line_is_unaffected() -> None:
    line = _formatted_access_line("/v1/health")
    assert "/v1/health" in line


def test_create_app_installs_exactly_one_filter_even_called_twice() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    create_app(
        db_path=tempfile.mktemp(suffix=".db"), policies=str(ROOT / "config" / "policies.yaml")
    )
    filters = [f for f in access_logger.filters if isinstance(f, _ByLinkTokenRedactingFilter)]
    assert len(filters) == 1
