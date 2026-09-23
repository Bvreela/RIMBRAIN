"""RimBrainAgent shared contracts package.

Schemas in ``schemas/`` are authoritative; this package ships the small set of
language-level helpers consumers need to interpret them identically — currently
canonical JSON (RFC 8785/JCS) serialization and hashing used for corpus,
fixture, and record identity.
"""

from contracts.canonical import CanonicalJSONError, canonical_bytes, canonical_hash, canonical_text

__all__ = ["CanonicalJSONError", "canonical_bytes", "canonical_hash", "canonical_text"]
__version__ = "0.1.0"
