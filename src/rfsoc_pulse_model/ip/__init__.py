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
from .platform import Gem3BoardIoConfig, PS_VLNV, PsPlatformConfig
from .connected import (
    AxisInterface,
    ClockNet,
    ConnectedAuthorityBytes,
    ConnectedCell,
    ConnectedShellEvidence,
    ConnectedShellReadiness,
    ConnectedShellRequest,
    MtsGroup,
    ResetNet,
    RfdcProbeProvenance,
    RfdcSemantics,
    build_connected_request,
    canonical_connected_json_bytes,
    parse_connected_evidence,
    parse_connected_request,
    validate_connected_evidence,
)
from .rfdc_probe import (
    RFDC_PROBE_VLNV,
    RfdcProbeInterface,
    RfdcProbeResult,
    RfdcProbeScalarPin,
    build_rfdc_probe_evidence,
    canonical_rfdc_probe_json_bytes,
    emit_rfdc_probe_tcl,
    parse_rfdc_probe_evidence,
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
    "AxisInterface",
    "ConnectionStatus",
    "ClockNet",
    "ConnectedAuthorityBytes",
    "ConnectedCell",
    "ConnectedShellEvidence",
    "ConnectedShellReadiness",
    "ConnectedShellRequest",
    "GenerationMode",
    "Gem3BoardIoConfig",
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
    "PS_VLNV",
    "PsPlatformConfig",
    "RFDC_2_6_VLNV",
    "RequiredResponsibilitiesSpec",
    "RfdcIntegrationMetadata",
    "RfdcProbeProvenance",
    "RfdcProbeInterface",
    "RfdcProbeResult",
    "RfdcProbeScalarPin",
    "RFDC_PROBE_VLNV",
    "RfdcSemantics",
    "ResetNet",
    "MtsGroup",
    "ValidatedCatalogEvidence",
    "build_candidate_lock",
    "build_catalog_request",
    "build_connected_request",
    "build_rfdc_probe_evidence",
    "canonical_connected_json_bytes",
    "canonical_json_bytes",
    "canonical_rfdc_probe_json_bytes",
    "emit_rfdc_probe_tcl",
    "parse_catalog_evidence",
    "parse_connected_evidence",
    "parse_connected_request",
    "parse_rfdc_probe_evidence",
    "promote_candidate_lock",
    "validate_catalog_evidence",
    "validate_connected_evidence",
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
