# Fresh Engineering Session Prompt

Copy the prompt below into a completely new engineering session after transferring the repository. No prior conversation data is required.

```text
Continue the ZU27DR RFSoC project from the tracked engineering handoff.

Read docs/handoff/README.md and CURRENT_STATE.md first.
Live-check git branch, HEAD, status, worktrees, and the current migration baseline commit a22c877.
Use FILE_INDEX.md to locate authorities before editing.
Treat Python, Vivado structural, CDC/timing, MTS runtime, DMA/Ethernet, and board validation as separate gates.
Do not repeat reviewed-complete Tasks 1-4.
Do not start Task 6 again: its OOC gate is reviewed-complete. Do not redo Task 5 either; confirm both current environment-bound evidence sets, then continue from the first open post-Task-6 production gate.
Use the current repository files as truth when a handoff statement has drifted.
Report any drift before changing code.

First return a short live-state audit containing:
1. current branch, full HEAD, clean/dirty status, and worktree layout;
2. whether commit a22c877 exists and is an ancestor of HEAD;
3. whether config root/package mirrors and the production lock still match;
4. whether Task 5 and OOC Task 6 remain CLEAN in docs/handoff/OPEN_ISSUES.md and current build evidence;
5. the first open post-Task-6 step from docs/handoff/NEXT_STEPS.md;
6. which validation layers have evidence and which remain open.

Do not modify files during that first audit. After reporting drift or confirming consistency, continue only with the first open gate and preserve the Golden -> Cycle -> generated Verilog authority chain.
```
