# AGENTS.md - crucible-Sept

<!-- GLOBAL-RULES v3-public BEGIN (2026-10-07). Maintained centrally; do not edit this block locally. -->
## Agent Rules (public-safe edition)

> Project-specific rules elsewhere in this file add to these and may be stricter. If one contradicts a rule below, stop and ask. Never pick one silently.

### 1. Environment
- Windows, PowerShell 7. Use PowerShell syntax for all commands.
- Model names are immutable. Never edit, "correct", or update a model name — your knowledge of models is always outdated.

### 2. Anchor the session before acting
- Confirm you are working in this repository before acting. Never infer the project from open editor tabs.
- You have no memory of earlier conversations. On "continue" / "pick up where we left off", first read this repo's
  AGENTS.md, BACKLOG.md (or equivalent), and recent git log/status; state what you found; then proceed.

### 3. Evidence standard — SHOWN, NOT CLAIMED
- Every claim about state, results, or behavior must rest on tool output from this session (a command run or a file read).
  Never describe a command you did not run or a result you did not see.
- In reports, label anything not verified this session as unverified or inherited.
- After every file write, read it back before calling it done.
- A failing check is a finding. Never weaken a test, threshold, or gate to make it pass.
- If an earlier claim of yours proves wrong, correct it explicitly before continuing.

### 4. Integrity — no fabricated work
- An honest "not done", "blocked", or "could not verify" is a successful outcome. A fabricated or inflated result is the one unrecoverable failure.
- Never make a check pass by: skipping, xfail-ing, deleting, or disabling tests; narrowing collection (-k, --deselect, ignore paths);
  hardcoding expected outputs or special-casing test inputs; mocking the unit under test; swallowing exceptions;
  writing assertions that cannot fail; lowering coverage or thresholds; or bypassing hooks or CI (--no-verify, SKIP=).
- Report every change to tests, fixtures, thresholds, or CI config as its own line item with the reason. Never fold it into "fixed".
- Every reported result states the exact command, exit code, and pass/fail/skip counts as printed. Never report counts you did not see.
- Acceptance and refusal tests are fixed in the spec before implementation. Changing them afterward needs approval.
- Never edit `.git/hooks`, CI workflows, or hook configs to get past a failure.

### 5. Boundaries
- "Read-only" / "probe" / "prepare" / "don't execute": reading files and running offline local checks is allowed;
  changing tracked files, git state, remotes, installed packages, or spending money is not.
- STOP means stop. At a stated phase boundary, report and wait.
- Live or paid runs (API calls, model evals) need an approved spend cap before launch.

### 6. Irreversible actions
- Before any commit, push, merge, or branch deletion, state: remote, account, branch, and exactly what is included.
- This repository is public: every push is publication. First confirm the diff contains no secrets, credentials,
  export-controlled material, client-identifying information, or confidential IP.
- Force-pushing or rewriting history requires explicit confirmation in the same turn.
- Fast-forward merges only.
- Commit trailers: follow this file. If it says nothing, ask before the first commit.
- A terse "push" / "commit" / "run it" gets the same checks as a detailed request.
- Deleting or overwriting files outside `scratch/` requires confirmation. Name the files first.

### 7. Engineering discipline
- Fix the blocker. If you cannot, say so plainly, name what is needed, and do not present lower-priority work as progress on it.
- For systems defined by their connections (APIs, pipelines, Docker stacks), write the integration test first; unit tests fill gaps.
- Specify and test what a module refuses before its happy path. A refusal or verification test counts only after
  you have seen it fail against a deliberately broken implementation.
- Priority: verification > refusal > observability > features.
- Be honest about novelty: novel research vs applied engineering vs standard implementation.
- Infrastructure (Docker, CI, .env, migrations) is code: edit → read back → validate → test.

### 8. New features
- Before writing feature code, follow the maintainer's adversarial review protocol. If it is not available in this environment, say so and stop.
- Write the feature spec in this repo's existing spec/design location (here: `experiment/PREREGISTRATION.md` conventions) or
  `docs/specs/YYYY-MM-DD-<feature>.md`. Specs are dated, append-only records. The spec names its acceptance and refusal tests;
  code is written only from that spec.

### 9. Hygiene
- Throwaway scripts and outputs go outside the repo or in a gitignored `scratch/`, never the repo root.
  Verification worth keeping is promoted into the test suite.
- Remove worktrees you created with `git worktree remove`, and their branches with `git branch -d` (never `-D`) once merged.
<!-- GLOBAL-RULES v3-public END -->
