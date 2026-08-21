"""Vendored third-party sources, kept byte-identical to their origin.

Nothing here is onedoor's to edit, reformat or annotate. `canonical.py` is core's
receipt artifact module, pinned at v3 and copied verbatim from
`reference/rederivable-manifest/canonical.py`: onedoor **never reimplements the
canonical form**, because two implementations of a preimage that have not been
checked against each other will disagree, silently and in the permissive direction.
Same bytes by construction is the only version of "same" that survives.

`tests/reference/` asserts this copy is byte-identical to the reference copy, so the
two cannot drift. The package is excluded from ruff and from mypy --strict for the
same reason `.gitattributes` fences it from git: a formatter is a byte-rewriting
tool, and received data is not ours to normalise (E10, third layer).
"""
