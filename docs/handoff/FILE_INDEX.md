# Project File Index

Use these tracked files as the navigation map. Open the relevant authority before editing; do not infer current truth from generated build output or ignored working notes.

## Common and Golden

- [Unified ModelConfig](../../config/default.json)
- [Configuration parser and validators](../../src/rfsoc_pulse_model/common/config.py)
- [Shared physical types](../../src/rfsoc_pulse_model/common/types.py)
- [Numeric format definitions](../../src/rfsoc_pulse_model/common/numeric_formats.py)
- [RFDC AXI types and packing](../../src/rfsoc_pulse_model/common/rfdc_axis.py)
- [Pulse event types](../../src/rfsoc_pulse_model/common/events.py)
- [Reflection public types](../../src/rfsoc_pulse_model/common/reflection_types.py)
- [Golden detector](../../src/rfsoc_pulse_model/golden/detector.py)
- [Golden receive path](../../src/rfsoc_pulse_model/golden/receive.py)
- [Golden reflection kernel](../../src/rfsoc_pulse_model/golden/reflection.py)
- [Golden continuous system](../../src/rfsoc_pulse_model/golden/system.py)
- [Golden transmit path](../../src/rfsoc_pulse_model/golden/transmit.py)

## Cycle and Verilog

- [Cycle expression DSL](../../src/rfsoc_pulse_model/cycle/dsl/expr.py)
- [Cycle module semantics](../../src/rfsoc_pulse_model/cycle/dsl/module.py)
- [Cycle simulator](../../src/rfsoc_pulse_model/cycle/dsl/simulator.py)
- [Verilog emitter](../../src/rfsoc_pulse_model/cycle/dsl/emitter.py)
- [Cycle module registry](../../src/rfsoc_pulse_model/cycle/registry.py)
- [Legacy 2SPC ingress model](../../src/rfsoc_pulse_model/cycle/hardware/rx_group_ingress.py)
- [Legacy TX AXIS boundary model](../../src/rfsoc_pulse_model/cycle/hardware/tx_iq_axis_boundary.py)
- [Top-level generator](../../src/rfsoc_pulse_model/generate.py)
- [Cycle ingress tests](../../tests/cycle/test_rx_group_ingress.py)
- [Generated ingress tests](../../tests/verilog/test_rx_group_ingress_emit.py)
- [Generated TX boundary tests](../../tests/verilog/test_tx_iq_axis_boundary_emit.py)

## RFDC, IP, and Connected Shell

- [Hardware architecture authority](../../config/ip_architecture.json)
- [Production IP lock](../../config/ip_lock.json)
- [PS platform authority](../../config/ps_platform.json)
- [Environment provenance and Phase-0 gate](../migration/environment-provenance.md)
- [Architecture object types](../../src/rfsoc_pulse_model/ip/types.py)
- [Architecture registry/readiness](../../src/rfsoc_pulse_model/ip/registry.py)
- [Catalog evidence](../../src/rfsoc_pulse_model/ip/evidence.py)
- [Production lock workflow](../../src/rfsoc_pulse_model/ip/lock.py)
- [PS platform parser](../../src/rfsoc_pulse_model/ip/platform.py)
- [RFDC-only probe](../../src/rfsoc_pulse_model/ip/rfdc_probe.py)
- [Pure connected request/evidence](../../src/rfsoc_pulse_model/ip/connected.py)
- [Connected Tcl generation](../../src/rfsoc_pulse_model/ip/connected_tcl.py)
- [Connected runner/lifecycle](../../src/rfsoc_pulse_model/ip/connected_runner.py)
- [Environment manifest/gate](../../src/rfsoc_pulse_model/ip/environment.py)
- [RFDC probe tests](../../tests/ip/test_rfdc_probe.py)
- [Connected evidence tests](../../tests/ip/test_connected.py)
- [Connected Tcl tests](../../tests/ip/test_connected_tcl.py)
- [Connected runner tests](../../tests/ip/test_connected_runner.py)

## Physical and Behavioral Contracts

- [ZU27DR physical channel map](../contracts/zu27dr-v2.1-physical-channel-map.md)
- [RFDC AXI word format](../contracts/rfdc-axis-word-format.md)
- [Fixed-point widths](../contracts/fixed-point-widths.md)
- [Fixed internal delay](../contracts/fixed-internal-delay.md)
- [Online stream and PDW semantics](../contracts/stream-status-online-pdw.md)
- [RCS anchor validity](../contracts/rcs-anchor-validity.md)
- [Cycle 2SPC ingress contract](../contracts/cycle-2spc-ingress.md)
- [AMD IP ownership](../contracts/amd-ip-ownership.md)

## Plans and Specifications

- [Golden system reference design](../superpowers/specs/2026-08-03-golden-system-reference-design.md)
- [Polarimetric reflection design](../superpowers/specs/2026-08-09-polarimetric-reflection-source-design.md)
- [AMD IP normalization design](../superpowers/specs/2026-08-11-ip-architecture-normalization-design.md)
- [Connected RFDC shell design](../superpowers/specs/2026-08-13-connected-rfdc-shell-design.md)
- [Connected RFDC shell plan](../superpowers/plans/2026-08-13-connected-rfdc-shell.md)
- [Portable handoff design](../superpowers/specs/2026-08-17-project-handoff-design.md)
- [Portable handoff plan](../superpowers/plans/2026-08-17-portable-project-handoff.md)

## Tests

- [Golden configuration tests](../../tests/golden/test_config.py)
- [Golden detector tests](../../tests/golden/test_detector.py)
- [Golden reflection system tests](../../tests/golden/test_reflection_system.py)
- [Golden streaming tests](../../tests/golden/test_reflection_stream.py)
- [Architecture configuration tests](../../tests/ip/test_architecture_config.py)
- [Platform authority tests](../../tests/ip/test_platform.py)
- [Registry/readiness tests](../../tests/ip/test_registry.py)
- [Lock workflow tests](../../tests/ip/test_lock.py)
- [Generator tests](../../tests/ip/test_generate_architecture.py)
- [Environment provenance tests](../../tests/ip/test_environment.py)

## Verification and Handoff

- [Polarimetric Golden acceptance](../verification/polarimetric-golden-acceptance.md)
- [AMD IP normalization acceptance](../verification/amd-ip-normalization-acceptance.md)
- [Current state](CURRENT_STATE.md)
- [Architecture summary](ARCHITECTURE.md)
- [Frozen decisions](DECISIONS.md)
- [Verification evidence](VERIFICATION_EVIDENCE.md)
- [Implementation history](IMPLEMENTATION_HISTORY.md)
- [Open issues](OPEN_ISSUES.md)
- [Ordered next steps](NEXT_STEPS.md)
- [Fresh-session prompt](NEW_CHAT_PROMPT.md)
