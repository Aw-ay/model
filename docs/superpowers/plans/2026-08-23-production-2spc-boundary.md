# Production 2SPC Boundary Candidate Plan

> Execute this plan in the current repository after the design approval recorded
> in the task conversation. Use TDD: tests first, then the smallest
> implementation that satisfies them.

## Guardrails

- Do not edit `config/default.json`, `config/ip_architecture.json`,
  `config/ip_lock.json`, or `config/ps_platform.json`.
- Do not copy or modify ignored Vivado build artifacts.
- Do not add the candidates to the production `HARDWARE_MODULES` registry.
- Do not create a new Vivado attempt.
- Keep `production_integration_ready` false.

## Steps

1. Add failing Cycle tests for a production RX ingress candidate. Cover exact
   8-channel/two-sample layout, one-cycle registered behavior, sample-base
   advancement by two, pre-arm ignore, sticky gap/format faults, and common
   clock/MTS configuration rejection.
2. Implement `RxContinuousIngress2Spc` as a new self-contained RTLModule with
   module name `rx_2spc_continuous_ingress`.
3. Add failing Cycle tests for `ContinuousStreamTimebase`. Cover first base zero,
   increments of two, missing-beat failure, discontinuity failure, upstream
   fault propagation, and reset recovery.
4. Implement the registered fail-closed timebase candidate with module name
   `continuous_stream_timebase`.
5. Add failing Cycle tests for a production TX egress candidate. Cover exact
   `{Q1,I1,Q0,I0}` packing, eight-way atomic ready, sticky underrun, disabled
   clear, and reset recovery.
6. Implement `TxContinuousEgress2Spc` as a new self-contained RTLModule with
   module name `tx_2spc_continuous_egress`.
7. Add a separate candidate registry and deterministic candidate RTL emission
   tests. Keep the existing legacy registry and manifest behavior unchanged.
8. Run targeted Cycle/Verilog tests, assert authority bytes and MTS values are
   unchanged, then run the full regression.
9. Update handoff status with candidate-only scope and the remaining promotion
   blockers. Commit the source, tests, spec, plan, and handoff update together.
