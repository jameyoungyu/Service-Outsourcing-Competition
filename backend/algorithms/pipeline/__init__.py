"""Closed-loop pipeline plumbing: content-addressed caching and profile fingerprints."""

from algorithms.pipeline.cache import LineageCache, canonical_json, stage_key
from algorithms.pipeline.fingerprint import (
    FINGERPRINT_FIELDS,
    ProfileFingerprint,
    build_fingerprint,
    fingerprint_distance,
)

__all__ = [
    "FINGERPRINT_FIELDS",
    "LineageCache",
    "ProfileFingerprint",
    "build_fingerprint",
    "canonical_json",
    "fingerprint_distance",
    "stage_key",
]
