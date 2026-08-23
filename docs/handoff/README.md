# RFSoC Project Handoff

## Start Here

This directory is the sole entry point for resuming the RFSoC project in a fresh engineering session. Begin with [CURRENT_STATE.md](CURRENT_STATE.md), verify the live Git state, and then follow the route for the task at hand.

The repository working tree and Git history contain the durable project context. Previous conversation databases are neither required nor authoritative.

## Evidence Priority

When statements disagree, use this order:

1. live tracked configuration, source, tests, and Git commits;
2. independently reviewed specifications, plans, contracts, and acceptance records;
3. reproducible Python, generator, HDL, and Vivado results;
4. consolidated implementation history in this handoff package.

A lower-priority summary never overrides a higher-priority authority. Report drift before editing code.

## Reading Routes

| New task | Read next |
|---|---|
| Understand current state | [CURRENT_STATE.md](CURRENT_STATE.md), [OPEN_ISSUES.md](OPEN_ISSUES.md) |
| Change algorithms or models | [ARCHITECTURE.md](ARCHITECTURE.md), [DECISIONS.md](DECISIONS.md), [FILE_INDEX.md](FILE_INDEX.md) |
| Change RFDC, AMD IP, or Block Design | [ARCHITECTURE.md](ARCHITECTURE.md), [VERIFICATION_EVIDENCE.md](VERIFICATION_EVIDENCE.md), [OPEN_ISSUES.md](OPEN_ISSUES.md) |
| Continue implementation | [CURRENT_STATE.md](CURRENT_STATE.md), [NEXT_STEPS.md](NEXT_STEPS.md), [FILE_INDEX.md](FILE_INDEX.md) |
| Audit past work | [IMPLEMENTATION_HISTORY.md](IMPLEMENTATION_HISTORY.md), [VERIFICATION_EVIDENCE.md](VERIFICATION_EVIDENCE.md) |
| Start a fresh engineering session | [NEW_CHAT_PROMPT.md](NEW_CHAT_PROMPT.md) |

Read only the routed documents first. Use [FILE_INDEX.md](FILE_INDEX.md) to open the relevant authority files before making a change.

## Portability Rules

- Treat every machine-specific path as an observation, not a portable authority.
- Resolve files from the repository root and verify the actual branch and HEAD.
- External evidence is usable only when its role, SHA-256, locator rule, and fail-closed behavior are documented.
- Use an available Python 3.12 interpreter and set `PYTHONPATH=<repository>/src` for project tests.
- Re-run evidence that is cheap to reproduce; never assume a historical green result still applies to a changed checkout.

## What Is Deliberately Excluded

- raw conversations and internal agent exchanges;
- account state, authentication material, approval history, and application-local databases;
- temporary build directories and unreviewed conclusions;
- claims that cannot be tied to tracked files, commits, hashes, commands, or tool readback.

## First Verification Commands

Run from the repository root:

```powershell
git branch --show-current
git rev-parse HEAD
git status --short
git worktree list --porcelain
git cat-file -t a22c877
$env:PYTHONPATH = "$PWD\src"
& '<PYTHON_3_12>' -m unittest tests.handoff.test_handoff_docs -v
```

The live branch may contain documentation or production-candidate commits after the current migration baseline. That does not change the connected-shell readiness boundary described in [CURRENT_STATE.md](CURRENT_STATE.md).
