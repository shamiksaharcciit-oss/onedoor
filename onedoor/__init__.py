"""OneDoor — a tiered guardrail engine for agentic systems. The model proposes; the policy layer disposes."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("onedoor")
except PackageNotFoundError:  # pragma: no cover - only in a source tree with no dist
    # Read from the installed distribution, never written here (X-11: a version typed
    # in two places is two versions). A source checkout with nothing installed has no
    # distribution to ask, and says so rather than inventing a number that would then
    # disagree with `pyproject.toml` the first time either moved.
    __version__ = "unknown"
