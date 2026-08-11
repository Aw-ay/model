"""AMD IP-first architecture contracts."""

from typing import TYPE_CHECKING

from .types import (
    ArchitectureBlockSpec,
    ArchitectureStatus,
    ConnectionStatus,
    HardwareArchitectureConfig,
    ImplementationKind,
    IntegrationProofStatus,
    IpFamilySpec,
    IpInstanceLifecycle,
    IpInstanceSpec,
    ParameterStatus,
    RFDC_2_6_VLNV,
    RequiredResponsibilitiesSpec,
    RfdcIntegrationMetadata,
)
from .evidence import (
    CatalogEvidence,
    CatalogResolutionStatus,
    ValidatedCatalogEvidence,
    build_candidate_lock,
    build_catalog_request,
    canonical_json_bytes,
    parse_catalog_evidence,
    validate_catalog_evidence,
)
if TYPE_CHECKING:
    from .lock import (
        GenerationMode,
        ProductionLock,
        ProductionLockValidation,
        promote_candidate_lock,
        validate_production_lock,
    )

__all__ = [
    "ArchitectureBlockSpec",
    "ArchitectureStatus",
    "ConnectionStatus",
    "GenerationMode",
    "CatalogEvidence",
    "CatalogResolutionStatus",
    "HardwareArchitectureConfig",
    "ImplementationKind",
    "IntegrationProofStatus",
    "IpFamilySpec",
    "IpInstanceLifecycle",
    "IpInstanceSpec",
    "ParameterStatus",
    "ProductionLock",
    "ProductionLockValidation",
    "RFDC_2_6_VLNV",
    "RequiredResponsibilitiesSpec",
    "RfdcIntegrationMetadata",
    "ValidatedCatalogEvidence",
    "build_candidate_lock",
    "build_catalog_request",
    "canonical_json_bytes",
    "parse_catalog_evidence",
    "promote_candidate_lock",
    "validate_catalog_evidence",
    "validate_production_lock",
]


_LOCK_EXPORTS = {
    "GenerationMode",
    "ProductionLock",
    "ProductionLockValidation",
    "promote_candidate_lock",
    "validate_production_lock",
}


def __getattr__(name: str) -> object:
    if name in _LOCK_EXPORTS:
        from . import lock

        return getattr(lock, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
