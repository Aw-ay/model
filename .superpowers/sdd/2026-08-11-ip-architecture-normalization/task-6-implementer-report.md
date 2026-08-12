# Task 6 implementation report

## Scope completed

- Classified every `HARDWARE_MODULES` entry by `production`: production RTL is
  emitted to `build/rtl/`; non-production Cycle RTL is emitted only to
  `build/reference_rtl/`.
- Published manifest `production_rtl` and `reference_rtl` arrays while keeping
  the compatibility `modules = production_rtl + reference_rtl` list.
- Made each generated RTL directory independently reject unregistered `.v`
  files, with the affected directory named in the failure.
- Added conservative migration for legacy files previously written under
  `build/rtl/`: only a registered non-production name whose bytes exactly equal
  the fresh reference bytes is removed. A different byte sequence fails as a
  possible hand edit; unknown files remain stale errors and are never removed.
- Derived and published architecture readiness after forming the explicit
  `production_rtl` list. A legacy registration in that list is reference-source
  contamination and adds `reference_rtl_in_production_sources`.
- Documented the production/reference RTL split, separate discovery and
  realization Tcl provenance, and the fact that production 2SPC ingress/egress
  responsibilities remain pending.

## TDD evidence

1. Added isolation, scoped-stale, byte-identical migration, hand-edit refusal,
   and legacy-production-contamination tests.
2. Before implementation, `python -m unittest tests.verilog.test_generate -v`
   failed as expected: old generation wrote both legacy modules to `rtl/`, had
   no `reference_rtl` manifest array, did not identify the stale scope, and did
   not fail closed on an edited legacy file.
3. After the minimal routing/readiness implementation, the focused generator
   and registry suite passed.

## Verification

- Focused: `python -m unittest tests.verilog.test_generate tests.ip.test_registry -v`
  passed 16 tests.
- Full: `python -m unittest discover -s tests -v` passed 204 tests; 2 Windows
  symlink-permission-gated lock tests were skipped.
- Generated `build/` twice in development mode. `manifest.json`,
  `metadata/ip_architecture.json`, and both reference RTL artifacts had identical
  SHA-256 values on both runs. Readback confirmed `production_rtl=[]`, the two
  expected `reference_rtl` paths, and no `.v` file under `build/rtl/`.
- The contamination probe patches a legacy registration into the production
  list and confirms readiness is false with
  `reference_rtl_in_production_sources`.

## Intentional boundary

No generated Verilog was hand-edited. This task does not implement the pending
production 2SPC boundaries, create a production IP lock, or perform Task 7
Vivado catalog/lock work.
