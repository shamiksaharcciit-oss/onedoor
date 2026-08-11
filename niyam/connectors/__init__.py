"""Connectors expose read_* (pure reads) and act_* (side effects).

act_* functions may only be invoked by the guardrail executor, via the injected
ConnectorRegistry. In M0 the only connector is the mock used to exercise the
engine and its tests — no real device/service connectors exist yet.
"""
