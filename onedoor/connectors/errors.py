"""Connector exceptions. Connectors raise these; schedulers catch and fail soft."""

from __future__ import annotations


class ConnectorError(Exception):
    """A connector read/act failed (HTTP, timeout, parse)."""


class NotConfigured(ConnectorError):
    """The connector's credentials/URL are not set — skip, don't crash."""
