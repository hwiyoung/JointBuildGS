"""Gate S0 common non-GT Stage-3 interface."""

from .interface import (
    CONDITIONS,
    derive_roofprint,
    make_roofer_request,
    synthetic_smoke_payload,
)

__all__ = [
    "CONDITIONS",
    "derive_roofprint",
    "make_roofer_request",
    "synthetic_smoke_payload",
]
