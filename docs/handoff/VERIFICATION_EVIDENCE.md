# Verification Evidence

## Current PR-hardening evidence

`docs/handoff/connected_evidence_bundle.json` is the immutable, tracked index
for the fresh evidence attempt. It is bound to base HEAD
`e70e774427df1179c6abdef307613c023c0c7013`, Phase-0 manifest SHA-256
`9569a9a5a9b005169322adc45e12c2220f9a91a4788b8ea57d762fb96c83cec7`, the
four unchanged authority hashes, and the exact 60-pair CDC-15 inventory hash.

Before writing the bundle, the following command completed with exit 0:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m unittest tests.cycle.test_fixed_point_expr tests.verilog.test_candidate_compile tests.ip.test_connected_tcl tests.ip.test_connected_runner -v
```

It ran 49 tests successfully and skipped one optional candidate elaboration
test because that test's executable discovery did not find a configured
Vivado 2025.2 path. The four authority SHA-256 values were re-read without
modifying authority JSON:

| Authority | SHA-256 |
|---|---|
| `config/default.json` | `d92c4a334728af441b22fa907e55cf4d6d236d899f46cbe3cd3ed7f26f9d5eb3` |
| `config/ip_architecture.json` | `36034e9c7b64061cdd449fb43030aea96368c95d6e88c8c6a0a9154da9e0bd96` |
| `config/ip_lock.json` | `0b1c92166b605a0a56c867fb144896d23599ade95538a29b72c9c274437fbe97` |
| `config/ps_platform.json` | `a1243d78a90ccb8e00f34749a8c3f18bf55870130c8f8372402407cf5591d11f` |

## Fresh connected-attempt result

A new detached worktree at the exact base HEAD was used specifically to avoid
reading, copying, or modifying old success artifacts. Its fresh Phase-0
manifest measured Vivado 2025.2 build 6299465 at
`C:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat`, but also measured Python
3.13.2. `prepare_environment` returned `ready=false` with the sole blocker
`python_3_12_required`; generation correctly stopped before catalog execution.

Accordingly, no fresh connected request, realization Tcl, verification Tcl,
CDC, clock-interaction, timing-summary, or utilization report exists for this
attempt. Their bundle hashes are null, and `bonded_iob_used` is null rather
than a fabricated `0`. A future successful attempt must publish all four
hashes, exact CDC-15 count 60/hash, and measured `bonded_iob_used=0` before
structural OOC readiness can be stated.

## Scope and regression provenance

The current focused calibrated H/V suite has 14 tests and the Cycle suite has
57 tests. The historical `327 tests / 8 skips` result is scoped only to
baseline `c118362`. No complete branch-wide Python regression is claimed
here; its status is unclaimed unless a fresh full run reaches a final summary.

All timing language remains `ooc_boundary_only`. This evidence does not show
post-route timing closure, full-top-level CDC, runtime MTS/SYSREF behavior,
board acceptance, or production data-path integration.
