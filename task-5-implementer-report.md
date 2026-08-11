# Task 5 implementation report

## Scope completed

- Added `GenerationMode`, strict `ProductionLock` parsing/validation, and the
  `python -m rfsoc_pulse_model.ip.lock promote` command.
- Production validation requires the exact 13-family set, concrete VLNVs,
  RFDC `xilinx.com:ip:usp_rf_data_converter:2.6`, current architecture,
  discovery-Tcl, catalog-request hashes, and current Vivado version.
- Lock validation deliberately has no realization-Tcl input or hash field.
- Candidate promotion validates before changes, canonicalizes bytes, and writes
  source/package targets through temporary files with rollback on replacement
  failure. Normal generation never promotes a candidate.
- Added `--ip-mode development|production`; development reports a missing or
  invalid source lock as `production_lock_valid=false`, while production fails
  before creating output for a missing or invalid packaged lock.
- Declared `ip_lock.json` package data without creating a production lock.

## TDD evidence

1. `tests.ip.test_lock` initially failed with the expected
   `ModuleNotFoundError: rfsoc_pulse_model.ip.lock`.
2. Generation-mode tests then failed with the expected unsupported positional
   mode argument and unrecognized `--ip-mode` CLI option.
3. The module-CLI warning regression test failed with the expected `runpy`
   pre-import warning before the public lock exports were made lazy.

## Verification

- Focused: `python -m unittest tests.ip.test_lock tests.ip.test_generate_architecture -v` — 12 passed.
- Full: `python -m unittest discover -s tests -v` — 182 passed.
- CLI in a fresh temporary directory: lock help exited 0; development exited 0
  and wrote `production_lock_valid=false`; production without a lock exited 1
  and did not create the requested output directory.

## Intentional boundary

No real `config/ip_lock.json` or packaged `ip_lock.json` was generated or
checked in. Producing that Vivado-evidence-derived lock remains Task 7.
