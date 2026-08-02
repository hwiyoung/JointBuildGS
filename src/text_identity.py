"""Portable identities for Git-owned UTF-8/text evidence.

Git blobs use LF.  A Windows checkout may expose CRLF for the same blob, so
bound text consumers normalize only CRLF pairs before checking byte count and
SHA-256.  A lone carriage return is never a line-ending conversion and fails
closed.
"""

from __future__ import annotations


class CanonicalTextError(ValueError):
    """Text bytes cannot be represented by CRLF-to-LF normalization alone."""


def canonical_lf_bytes(data: bytes) -> bytes:
    """Return Git-blob-style LF bytes, rejecting every unpaired CR byte."""

    if not isinstance(data, bytes):
        raise TypeError("canonical text identity requires bytes")
    without_pairs = data.replace(b"\r\n", b"")
    if b"\r" in without_pairs:
        raise CanonicalTextError("bound text contains a lone carriage return")
    if b"\r" not in data:
        return data
    return data.replace(b"\r\n", b"\n")
