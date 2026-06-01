---
description: Run the project end-to-end to verify a change actually works (Boris-style verify-app)
argument-hint: [what to verify]
---
Verify the current change actually works by *running* the project, not by reading code. Focus: $ARGUMENTS

1. Identify the smallest real execution that exercises the change (a script, a server + request, or a test).
2. Run it. For this repo specifically:
   - **Python pipeline** — syntax gate: `python -c "import ast,glob; [ast.parse(open(f).read()) for f in glob.glob('pipeline/*.py')]"`, then run the relevant module/function on sample data.
   - **Frontend worker** — `node --check frontend/_worker.js`.
   - **Rendered output** — start `npx wrangler pages dev frontend` and `curl` the relevant path on loopback.
3. Observe the actual output/behavior and compare it to what's expected.
4. Report exactly what you ran, what you saw, and a clear **PASS/FAIL**. If it failed, diagnose. Never claim success without evidence.
