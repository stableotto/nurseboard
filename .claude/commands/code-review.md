---
description: Adversarial multi-subagent review of the current diff (Boris-style)
argument-hint: [base ref, defaults to main]
---
Run a Boris-style parallel code review. Launch the following **in a single message with multiple Agent tool calls** so they run concurrently, then synthesize their findings:

1. `bug-hunter` subagent — adversarially hunt for correctness bugs, edge cases, and regressions.
2. `style-reviewer` subagent — check the diff against CLAUDE.md conventions and the surrounding code's style.
3. A `general-purpose` agent — read recent `git log` and `git blame` on the touched files and flag anything that contradicts a prior decision or re-introduces a reverted change.

Diff under review: !`git diff ${ARGUMENTS:-main}...HEAD 2>/dev/null || git diff HEAD`

After the subagents report, synthesize ONE prioritized list:
- **Blocking** issues first, then **important**, then **minor/nits**.
- Each finding: `file:line`, what's wrong, and a concrete fix.
- No praise padding. If something is clean, say so in one line and move on.
