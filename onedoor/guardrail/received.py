"""Freezing received bytes verbatim, and knowing when you cannot (E10 / R004).

The rule has two halves and they are not symmetric:

* **Received data is frozen verbatim.** If an enforcement point sent bytes, those
  exact bytes are what the evidence row stores -- no parse, no re-serialize. Two
  semantically identical requests may arrive spelled differently, and the record must
  show what was *sent*, not what this PDP would have written.
* **Generated data is canonicalised.** The in-process binding is handed Python
  objects and there are no received bytes at all, so its frozen form is one canonical
  serialization at ingress.

Which of the two produced a row is itself evidence, so it is recorded rather than
inferred. `Provenance.RECEIVED` can be re-derived against what the caller
transmitted; `Provenance.SERIALIZED` can only be re-derived against what this PDP
would produce. Collapsing them would let the second be mistaken for the first.
"""

from __future__ import annotations

import json
from enum import StrEnum


class Provenance(StrEnum):
    """How the bytes in a params/payload column came to be."""

    RECEIVED = "received"
    """The exact bytes an enforcement point sent."""

    SERIALIZED = "serialized"
    """Objects handed to the in-process binding, serialized once here at ingress."""


def extract_raw_member(document: str, key: str) -> str | None:
    """Return the verbatim source text of a top-level member, or None.

    Used to freeze `params` exactly as it arrived inside a larger message, without
    re-serializing it. Returns None rather than guessing whenever the document is not
    a plain object with that member at the top level -- an approximate answer here
    would be worse than none, because the caller would record it as *verbatim*.

    Deliberately not a regex: JSON strings can contain braces, quotes and escapes, so
    a scanner that does not actually parse will eventually cut a value in half. This
    walks the real decoder and takes the span it consumed.
    """
    decoder = json.JSONDecoder()
    try:
        value, end = decoder.raw_decode(document.lstrip())
    except ValueError:
        return None
    if not isinstance(value, dict) or key not in value:
        return None

    # Re-scan for the member, using the decoder itself to find where its value ends.
    offset = len(document) - len(document.lstrip())
    idx = offset
    while True:
        idx = document.find(f'"{key}"', idx)
        if idx == -1:
            return None
        colon = document.find(":", idx + len(key) + 2)
        if colon == -1:
            return None
        start = colon + 1
        while start < len(document) and document[start] in " \t\n\r":
            start += 1
        try:
            _, member_end = decoder.raw_decode(document, start)
        except ValueError:
            idx += 1
            continue
        # Confirm this really was the top-level member and not a nested key that
        # happens to share the name: everything before it must parse as a prefix of
        # the same object.
        try:
            probe = json.loads(document[:idx].rstrip().rstrip(",") + "}")
        except ValueError:
            idx += 1
            continue
        if not isinstance(probe, dict):
            idx += 1
            continue
        return document[start:member_end]
