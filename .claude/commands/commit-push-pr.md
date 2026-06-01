---
description: Commit current work, push to a feature branch, and open a PR (inner-loop command)
argument-hint: [optional PR title / one-line description]
allowed-tools: Bash(git:*), Bash(gh:*)
---
Boris-style inner-loop "commit → push → PR". This runs many times a day, so be fast and don't over-narrate.

Current state:
- Status: !`git status --short`
- Branch: !`git branch --show-current`
- Changes: !`git diff --stat HEAD 2>/dev/null`

Do this:
1. If on the default branch (`main`/`master`), create a short, descriptively-named feature branch first — never commit directly to the default branch.
2. Stage everything and write a clear, concise commit message that explains the *why*, following any commit conventions in CLAUDE.md.
3. Push with `git push -u origin <branch>` (retry on transient network errors).
4. Open a PR (`gh pr create`, or this project's GitHub tool if `gh` is unavailable). Use `$ARGUMENTS` as the title if provided; otherwise generate a tight title + a short bullet-point body.
5. Print the PR URL and stop.
