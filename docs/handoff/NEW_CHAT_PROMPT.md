# Fresh Engineering Session Prompt

Copy the prompt below into a completely new engineering session after transferring the repository. No prior conversation data is required.

```text
Continue the ZU27DR RFSoC project from the tracked engineering handoff.

Read docs/handoff/README.md and CURRENT_STATE.md first.
Live-check git branch, HEAD, status, worktrees, and the current migration baseline commit a22c877.
Use FILE_INDEX.md to locate authorities before editing.
Treat Python, Vivado structural, CDC/timing, MTS runtime, DMA/Ethernet, and board validation as separate gates.
Task 4 hardening code is CLEAN, but fresh connected OOC evidence is not
available: the tracked fresh attempt stopped before catalog because Python
3.12 is absent. Install or recreate Python 3.12, then rerun catalog discovery,
RFDC probe, and the connected OOC shell in a new clean attempt. Do not reuse
old build, project, report, or success artifacts.
Use the current repository files as truth when a handoff statement has drifted.
Report any drift before changing code.

First return a short live-state audit containing:
1. current branch, full HEAD, clean/dirty status, and worktree layout;
2. whether the bundle source HEAD and its tracked environment-manifest SHA-256
   match, and whether the source HEAD is an ancestor of HEAD;
3. whether config root/package mirrors and the production lock still match;
4. whether the Python 3.12 recovery gate is still open and whether any fresh
   catalog/probe/OOC evidence has actually been generated;
5. the next ordered step from docs/handoff/NEXT_STEPS.md;
6. which validation layers have evidence and which remain open.

Do not modify files during that first audit. After reporting drift or confirming consistency, continue only with the first open gate and preserve the Golden -> Cycle -> generated Verilog authority chain.
```
