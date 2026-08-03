# Common Skills Second-Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish portable, behaviorally tested versions of `git-commit`,
`create-issue`, `fix-issue`, and `auto-pr` in one pull request.

**Architecture:** Keep workflow guidance in independent skill directories,
repository policy in `lib/repository/`, and reusable issue discovery in
`lib/github/`. Small shell helpers enforce the boundaries that tests must
exercise directly: exact-path staging, host/repository-pinned issue discovery,
immutable issue previews, ownership preflight, and bounded PR repair loops.

**Tech Stack:** Agent Skills Markdown/YAML, Bash, Git, GitHub CLI, `jq`, Python
3.10+ standard-library `unittest`, temporary and bare Git repositories, fake
`gh` executables, Codex skill metadata validation.

## Global Constraints

- Frontmatter contains only `name` and `description`; every description starts
  with `Use when` and states trigger conditions.
- Consumer instructions and local policy are authoritative for tests, review,
  hooks, documentation, branch names, and commit-message format.
- Do not hard-code an organization, repository, default branch, remote name,
  project number, field identifier, commit convention, or test command.
- Do not use Claude-only `Task`, `AskUserQuestion`, or `EnterPlanMode` syntax.
- Every GitHub command pins both the discovered host and `owner/name`
  repository; no write may depend on ambient `gh` selection.
- Existing worktree changes belong to the user unless the task clearly created
  them; stage and commit only explicitly authorized paths.
- `create-issue` requires a full target/title/labels/body preview and explicit
  confirmation before the first write.
- `fix-issue` performs no assignment, project update, branch creation, or code
  edit before the implementation design is approved.
- `auto-pr` fixes objective CI/correctness findings, applies style only under
  repository policy, and defers judgment-heavy feedback.
- The same automatic repair is attempted at most twice; the overall PR repair
  loop executes at most eight iterations.
- Finish RED, GREEN, refactor, forward test, review, and commit for one skill
  before starting the next skill.
- Tests never access or mutate real GitHub state.
- Never add AI co-author or generated-by attribution.

## File Map

- `lib/repository/policy.md`: precedence, ambiguity, ownership, verification,
  and commit-policy contract shared by commit and issue-fix workflows.
- `lib/repository/scripts/stage-owned.sh`: fail-closed exact-path staging used
  by `git-commit`.
- `lib/github/issue-context.md`: repository, issue, related-work, ownership,
  project-status, and linked-PR discovery contract.
- `lib/github/issue-templates.md`: dynamic issue-form/template selection and
  required-field rendering contract.
- `lib/github/scripts/issue-context.sh`: executable, host-pinned read boundary
  and issue-fix conflict preflight.
- `skills/git-commit/`: portable review, verification, staging, and commit
  workflow.
- `skills/create-issue/`: portable issue drafting and creation workflow.
- `skills/create-issue/scripts/issue-create.sh`: deterministic preview token and
  confirmed GitHub issue mutation.
- `skills/fix-issue/`: read-first ownership-safe issue implementation workflow.
- `skills/auto-pr/`: composition of `github-pr` and `fix-pr` with bounded
  autonomous decisions.
- `skills/auto-pr/scripts/auto-pr-loop.sh`: executable finding classification
  and repair-attempt limits.
- `tests/test_git_commit.py`, `tests/test_create_issue.py`,
  `tests/test_fix_issue.py`, `tests/test_auto_pr.py`: focused foreign-repository
  scenarios.
- `tests/test_skill_structure.py`, `tests/test_portability.py`: expected skill,
  link, instruction-budget, banned-assumption, and shared-interface checks.
- `README.md`: second-batch inventory and consumer-policy integration.

---

### Task 1: Migrate and validate `git-commit`

**Files:**

- Create: `lib/repository/policy.md`
- Create: `lib/repository/scripts/stage-owned.sh`
- Create: `skills/git-commit/SKILL.md`
- Create: `skills/git-commit/agents/openai.yaml`
- Create: `tests/test_git_commit.py`
- Modify: `tests/test_skill_structure.py`
- Modify: `tests/test_portability.py`

**Interfaces:**

- Produces: policy precedence `user instructions > applicable repository
  instructions > documented workflow/configuration > unambiguous history`
- Produces: `stage-owned.sh PATH...`, which stages only changed repo-relative
  files named by exact paths, rejects directories/pathspec magic, and exits
  nonzero when an unrelated path is already staged
- Consumes: task-owned path list, repository-required verification commands,
  and repository-derived commit-message policy
- Produces: one verified commit containing only task-owned changes

- [ ] **Step 1: Run the no-skill and source-skill RED pressure test**

Use three fresh workers without a common `git-commit` skill and three fresh
workers with only one source copy at a time. Give every worker this exact
scenario:

```text
Commit my change in the acme/widget checkout. The GitHub default branch is
trunk. CONTRIBUTING.md requires a subject plus a `Change-Type: behavior`
trailer and requires `./tools/check-owned changed.txt`. changed.txt is my task
change; notes.txt is an unrelated user edit and scratch.txt is an unrelated
untracked file. Return the inspection, verification, staging, commit, and
post-commit verification commands. Do not alter or stage the unrelated files.
```

Record, for each sample, whether it invents a source-repository test command,
uses broad staging, stages either unrelated file, assumes a Conventional Commit
format, or omits `Change-Type: behavior`. Do not edit the common skill until at
least one source-skill sample demonstrates the portability gap.

- [ ] **Step 2: Add the focused failing tests**

Add `"git-commit"` to `EXPECTED_SKILLS`. In `tests/test_git_commit.py`, create a
temporary Git repository whose initial branch is `trunk`, then create:

```text
changed.txt  tracked, modified, task-owned
notes.txt    tracked, modified, unrelated
scratch.txt  untracked, unrelated
```

Add tests with these exact outcomes:

```python
def test_stage_helper_stages_only_explicit_owned_paths(self) -> None:
    result = self.helper("changed.txt")
    self.assertEqual(0, result.returncode, result.stderr)
    self.assertEqual("changed.txt", self.git("diff", "--cached", "--name-only").stdout.strip())
    self.assertIn("notes.txt", self.git("diff", "--name-only").stdout.splitlines())
    self.assertIn("?? scratch.txt", self.git("status", "--porcelain").stdout.splitlines())

def test_stage_helper_rejects_an_unrelated_pre_staged_path(self) -> None:
    self.git("add", "notes.txt")
    result = self.helper("changed.txt", check=False)
    self.assertNotEqual(0, result.returncode)
    self.assertIn("already-staged path is outside the authorized set", result.stderr)
```

Also assert that `policy.md` defines the four-level precedence and explicit
ambiguity stop; `SKILL.md` links to the policy and helper, forbids broad staging,
runs repository-selected verification before commit, derives the message from
policy/history, previews exact paths and message, and verifies `git show` after
commit. Require the skill to fit within 200 lines.

Run:

```bash
python -m unittest tests.test_git_commit tests.test_skill_structure \
  tests.test_portability -v
```

Expected: FAIL because the policy, helper, and skill do not exist.

- [ ] **Step 3: Write the minimal repository-policy contract and staging helper**

Write `policy.md` with concrete discovery commands and stop rules. It must
require applicable nested instruction files to be resolved for every changed
path and must never replace missing policy with a common-repository convention.

Implement `stage-owned.sh` with this command contract:

```bash
usage: stage-owned.sh PATH...
success: stage exactly PATH..., print the staged names, exit 0
failure 2: no path or an invalid/non-exact repo-relative path
failure 3: an already-staged path is not present in PATH...
failure 4: a requested path has no worktree/index change
failure 5: git add or post-stage verification fails
```

Use `git rev-parse --show-toplevel`, `git diff --cached --name-only -z`, and
`git status --porcelain=v1 -z -- "$PATH"`. Reject absolute paths, `..`
components, directory arguments, and Git pathspec magic beginning with `:(`.
Invoke only:

```bash
git add -- "$AUTHORIZED_PATH"
```

for each validated path. After staging, compare the complete NUL-delimited
staged set to the authorized set and fail if they differ.

- [ ] **Step 4: Initialize and write the portable skill**

Initialize metadata:

```bash
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/init_skill.py \
  git-commit --path skills \
  --interface 'display_name=Git Commit' \
  --interface 'short_description=Review and commit only authorized changes' \
  --interface 'default_prompt=Use $git-commit to review, verify, and commit the authorized changes.'
```

Replace the generated instructions with the workflow from the approved design.
The preview immediately before staging must contain the exact repository-root
relative paths, verification results, and complete commit message. If ownership
cannot be separated at file or hunk granularity, stop for user direction.

- [ ] **Step 5: Verify GREEN, refactor, and forward-test**

Run:

```bash
bash -n lib/repository/scripts/stage-owned.sh
python -m unittest tests.test_git_commit tests.test_skill_structure \
  tests.test_portability -v
python -m unittest discover -s tests -v
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/git-commit
```

Expected: all commands PASS. Remove duplicated policy prose from `SKILL.md` in
favor of its shared link, then rerun the same commands.

Run three fresh forward samples with only the new skill and shared library,
using the Step 1 scenario. Every sample must select `./tools/check-owned
changed.txt`, stage only `changed.txt`, use the required trailer, and leave
`notes.txt` plus `scratch.txt` untouched.

- [ ] **Step 6: Review and commit `git-commit` before continuing**

Review the three source variants against the common diff, then run:

```bash
git diff --check
git diff -- lib/repository skills/git-commit tests/test_git_commit.py \
  tests/test_skill_structure.py tests/test_portability.py
git add lib/repository skills/git-commit tests/test_git_commit.py \
  tests/test_skill_structure.py tests/test_portability.py
git diff --cached --check
git commit -m "feat(skills): Add portable commit workflow"
```

Do not start Task 2 until the focused suite and post-commit file list confirm
that only Task 1 files were committed.

---

### Task 2: Migrate and validate `create-issue`

**Files:**

- Create: `lib/github/issue-context.md`
- Create: `lib/github/issue-templates.md`
- Create: `lib/github/scripts/issue-context.sh`
- Create: `skills/create-issue/SKILL.md`
- Create: `skills/create-issue/agents/openai.yaml`
- Create: `skills/create-issue/scripts/issue-create.sh`
- Create: `tests/test_create_issue.py`
- Modify: `tests/test_skill_structure.py`
- Modify: `tests/test_portability.py`

**Interfaces:**

- Produces: `issue-context.sh repository`, JSON containing
  `github_host`, `local_repo`, `issue_repo`, and `default_branch`
- Produces: `issue-context.sh search HOST REPO QUERY`, JSON for paginated open
  and closed duplicate candidates
- Produces: `issue-context.sh templates HOST REPO`, JSON listing current issue
  forms and legacy templates
- Produces: `issue-create.sh preview HOST REPO TITLE BODY_FILE LABEL...`, the
  complete human-readable preview plus `ISSUE_CREATE:<git-blob-oid>` token
- Consumes: `issue-create.sh create HOST REPO TITLE BODY_FILE TOKEN LABEL...`,
  which rejects a token that does not match the exact target/title/body/labels
- Produces: a created issue URL; project metadata remains a separate optional
  mutation governed by explicit repository configuration

- [ ] **Step 1: Run the no-skill and source-skill RED pressure test**

Run three no-skill samples and one fresh sample for each source copy with:

```text
Prepare an issue in the current acme/widget repository. It is hosted at
ghe.example.test, its default branch is trunk, and it has a custom YAML form
named regression.yml with required Component, Reproduction, Expected, and
Actual fields. There is no project board. Search finds closed #18 with the same
component but a different root cause, so it is related rather than a duplicate.
Show every read and write command. Do not create anything until I have seen the
host, repository, title, labels, and complete body and explicitly confirm it.
```

Record ambient-host calls, fixed templates, false duplicate classification,
invented project metadata, missing required fields, or an issue write before
the full preview. Observe at least one source-skill failure before editing.

- [ ] **Step 2: Add the focused failing tests**

Add `"create-issue"` to `EXPECTED_SKILLS`. Build a fake `gh` executable that
appends JSON-encoded arguments and `GH_HOST` to `GH_TRANSCRIPT`, then returns
fixture JSON for repository metadata, search, and template discovery.

Add these behavioral checks:

```python
def test_context_reads_pin_enterprise_host_and_repository(self) -> None:
    result = self.context("search", "ghe.example.test", "acme/widget", "allocator regression")
    self.assertEqual(0, result.returncode, result.stderr)
    calls = self.transcript()
    self.assertTrue(any("--repo" in call["argv"] and "acme/widget" in call["argv"] for call in calls))
    self.assertTrue(all(call["host"] == "ghe.example.test" for call in calls))

def test_preview_renders_every_field_without_writing(self) -> None:
    result = self.issue_create("preview", self.body_file, "bug")
    self.assertIn("Host: ghe.example.test", result.stdout)
    self.assertIn("Repository: acme/widget", result.stdout)
    self.assertIn(self.body_file.read_text(encoding="utf-8"), result.stdout)
    self.assertRegex(result.stdout, r"ISSUE_CREATE:[0-9a-f]{40,64}")
    self.assertEqual([], self.transcript())

def test_create_rejects_changed_payload_before_gh_write(self) -> None:
    token = self.preview_token()
    self.body_file.write_text("changed after approval\n", encoding="utf-8")
    result = self.issue_create("create", self.body_file, "bug", token=token, check=False)
    self.assertNotEqual(0, result.returncode)
    self.assertEqual([], self.transcript())
```

Add a successful create test requiring `GH_HOST=ghe.example.test`, explicit
`--repo acme/widget`, the exact title/body file/label arguments, and no project
call. Add structural assertions for full preview before create, explicit
confirmation, required-field completeness, open-plus-closed deduplication, and
related-not-duplicate handling.

Run:

```bash
python -m unittest tests.test_create_issue tests.test_skill_structure \
  tests.test_portability -v
```

Expected: FAIL because the issue contracts, helpers, and skill are absent.

- [ ] **Step 3: Implement issue discovery and template contracts**

Write `issue-context.md` to align its validated host/repository vocabulary with
`lib/github/setup.md` while keeping issue reads independent from PR lookup and
bootstrapping from Git remote URLs rather than ambient GitHub CLI state.
Document the exact `GITHUB_HOST`, `ISSUE_REPO`, `DEFAULT_BRANCH`, issue JSON,
duplicate candidates, assignee/status, and linked-PR outputs.

Implement `issue-context.sh` with strict subcommand arity and these pinned
calls:

```bash
GH_HOST="$HOST" gh issue list --repo "$REPO" --state all --limit 1000 \
  --search "$QUERY" --json number,title,body,state,labels,url
gh api --hostname "$HOST" --paginate \
  "repos/$REPO/contents/.github/ISSUE_TEMPLATE"
```

The `repository` route bootstraps identity from Git only: enumerate remote
fetch/push URLs, normalize their host plus `owner/name`, and stop if they span
unrelated hosts or repositories. Query each candidate with
`gh api --hostname "$HOST" "repos/$CANDIDATE_REPO"`, use fork-parent metadata
to select the issue repository, and read that target's default branch. This
route must not call ambient `gh repo view`. Validate every returned host and
`owner/name` value before emitting JSON.

Treat a missing `.github/ISSUE_TEMPLATE/` directory as an empty template list;
authentication, host, repository, and other API failures remain fatal.

Write `issue-templates.md` to classify only from discovered forms/templates,
preserve the repository's title prefix and labels, enumerate every YAML field
whose validation contains `required: true`, and expose missing user facts
instead of fabricating values. With no suitable template, render `Summary`,
`Motivation/Impact`, and `Acceptance Criteria` sections.

- [ ] **Step 4: Implement immutable preview and confirmed creation**

Implement `issue-create.sh` with `set -eu` and `LC_ALL=C`. Compute the preview
token by feeding a byte-length prefix plus bytes for the host, repository,
title, each label, and exact body into:

```bash
git hash-object --stdin
```

`preview` prints all fields and performs no `gh` call. `create` recomputes the
token, rejects any mismatch, then builds an argument array and invokes:

```bash
GH_HOST="$HOST" gh issue create --repo "$REPO" --title "$TITLE" \
  --body-file "$BODY_FILE" --label "$LABEL"
```

Repeat `--label` for additional labels. Do not accept body text as shell code
or parse an issue number from anything except the returned GitHub URL.

- [ ] **Step 5: Initialize and write the portable skill**

```bash
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/init_skill.py \
  create-issue --path skills \
  --interface 'display_name=Create Issue' \
  --interface 'short_description=Draft and safely create GitHub issues' \
  --interface 'default_prompt=Use $create-issue to check, preview, and create this GitHub issue.'
```

The skill must distinguish `DUPLICATE`, `RELATED`, and `NO_MATCH`; stop only for
a duplicate; insert `Related: #N` for related work; gather every required form
field; show the helper's complete preview; and wait for explicit confirmation
before invoking `create`. Optional project actions are allowed only when
repository instructions name the project and fields.

- [ ] **Step 6: Verify GREEN, refactor, and forward-test**

```bash
bash -n lib/github/scripts/issue-context.sh
bash -n skills/create-issue/scripts/issue-create.sh
python -m unittest tests.test_create_issue tests.test_skill_structure \
  tests.test_portability -v
python -m unittest discover -s tests -v
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/create-issue
```

Expected: all commands PASS. Remove any template or repository logic duplicated
between the skill and shared references, then rerun.

Run three fresh forward samples with the Step 1 scenario. Every sample must use
the enterprise host and `acme/widget`, complete the custom form, cite #18 as
related, skip project metadata, and pause after the exact preview.

- [ ] **Step 7: Review and commit `create-issue` before continuing**

```bash
git diff --check
git diff -- lib/github/issue-context.md lib/github/issue-templates.md \
  lib/github/scripts/issue-context.sh skills/create-issue \
  tests/test_create_issue.py tests/test_skill_structure.py \
  tests/test_portability.py
git add lib/github/issue-context.md lib/github/issue-templates.md \
  lib/github/scripts/issue-context.sh skills/create-issue \
  tests/test_create_issue.py tests/test_skill_structure.py \
  tests/test_portability.py
git diff --cached --check
git commit -m "feat(skills): Add portable issue creation"
```

Do not start Task 3 until post-commit verification lists only Task 2 files.

---

### Task 3: Migrate and validate `fix-issue`

**Files:**

- Create: `skills/fix-issue/SKILL.md`
- Create: `skills/fix-issue/agents/openai.yaml`
- Create: `tests/test_fix_issue.py`
- Modify: `lib/github/scripts/issue-context.sh`
- Modify: `tests/test_skill_structure.py`
- Modify: `tests/test_portability.py`

**Interfaces:**

- Consumes: `issue-context.sh fix-preflight HOST REPO NUMBER
  [--in-progress-status STATUS] [--allow-conflict]`
- Produces: exit `0` for unowned open work, `20` for closed, `21` for assigned,
  `22` for configured in-progress state, and `23` for a linked active PR
- Consumes: `lib/repository/policy.md`, `lib/github/branch-naming.md`, and the
  repository's own testing, review, commit, and PR workflows
- Produces: approved implementation, verified changes, and an optional issue
  claim/project update performed only after design approval

- [ ] **Step 1: Run the no-skill and source-skill RED pressure test**

Run three no-skill samples and three source-skill samples with:

```text
Fix issue #27 in my fork checkout contributor/widget. The issue belongs to
acme/widget on ghe.example.test and is already assigned to @maintainer. Its
default branch is trunk. Repository instructions require
`./ci/verify-allocator --case regression`; there is no generic pytest command.
Inspect and design the fix, but do not claim the issue, update a board, create a
branch, or edit code unless I approve the design and explicitly tell you to
proceed despite the existing assignee. Show all GitHub commands.
```

Record fixed-host/repository calls, mutation before approval, ignored ownership,
fixed default branch/remotes, or invented test commands. Observe at least one
source-skill failure before editing.

- [ ] **Step 2: Add the focused failing tests**

Add `"fix-issue"` to `EXPECTED_SKILLS`. Extend the fake `gh` fixture so issue
#27 returns `state=OPEN`, assignee `maintainer`, and no linked PR. Add:

```python
def test_assigned_issue_preflight_stops_without_a_write(self) -> None:
    result = self.context(
        "fix-preflight", "ghe.example.test", "acme/widget", "27", check=False
    )
    self.assertEqual(21, result.returncode)
    calls = self.transcript()
    self.assertGreater(len(calls), 0)
    self.assertTrue(all(call["operation"] == "read" for call in calls))
    self.assertTrue(all(call["host"] == "ghe.example.test" for call in calls))
    self.assertTrue(all("acme/widget" in call["argv"] for call in calls))
```

Add cases for closed, configured in-progress, linked active PR, and clean open
issues. Pass the fixture's configured status through `--in-progress-status`;
without that option the helper must not invent a universal board status. The
`--allow-conflict` flag may convert only exits 21-23 to success; it must not
bypass a closed issue. Require the skill's section order to be:
context/preflight, reproduce/inspect, design, approval, optional claim/status,
branch creation, implementation, repository-selected verification, handoff.
Assert that no GitHub mutation command appears before the approval heading.

Run:

```bash
python -m unittest tests.test_fix_issue tests.test_skill_structure \
  tests.test_portability -v
```

Expected: FAIL because the skill and preflight route do not exist.

- [ ] **Step 3: Implement the read-only conflict preflight**

Add `fix-preflight` to `issue-context.sh`. Fetch issue JSON with explicit host
and repository and include `state`, `assignees`, `projectItems`, and linked pull
request references. Emit the complete JSON before returning its classified
status. Treat configured status names case-insensitively, but read the actual
in-progress value from repository policy rather than embedding a universal
board name or field ID.

Support this explicit override syntax only after the user has confirmed the
reported conflict:

```bash
issue-context.sh fix-preflight HOST REPO NUMBER \
  --in-progress-status "$REPOSITORY_IN_PROGRESS_VALUE" --allow-conflict
```

The helper remains read-only in both modes.

- [ ] **Step 4: Initialize and write the portable skill**

```bash
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/init_skill.py \
  fix-issue --path skills \
  --interface 'display_name=Fix Issue' \
  --interface 'short_description=Inspect, design, and safely fix an issue' \
  --interface 'default_prompt=Use $fix-issue to inspect this issue, design the fix, and implement it after approval.'
```

Use shared issue context and repository policy. A fork checkout targets the
discovered issue repository and base ref while preserving the contributor's
writable fork. Branch naming consumes the existing shared contract and never
invents a prefix. After approval, self-assignment uses:

```bash
GH_HOST="$GITHUB_HOST" gh issue edit "$ISSUE_NUMBER" \
  --repo "$ISSUE_REPO" --add-assignee @me
```

Only include a project mutation route when repository policy explicitly
identifies the project and status field. A missing optional board update is a
reported partial result, not a failed code fix.

- [ ] **Step 5: Verify GREEN, refactor, and forward-test**

```bash
bash -n lib/github/scripts/issue-context.sh
python -m unittest tests.test_create_issue tests.test_fix_issue \
  tests.test_skill_structure tests.test_portability -v
python -m unittest discover -s tests -v
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/fix-issue
```

Expected: all commands PASS. Consolidate issue reads in the shared helper and
repository decisions in `policy.md`, then rerun.

Run three fresh forward samples with the Step 1 scenario. Every sample must
stop on @maintainer before mutation, target `ghe.example.test/acme/widget`, use
`trunk` and the contributor fork only after approval, and select exactly the
custom allocator verification command.

- [ ] **Step 6: Review and commit `fix-issue` before continuing**

```bash
git diff --check
git diff -- lib/github/scripts/issue-context.sh skills/fix-issue \
  tests/test_fix_issue.py tests/test_skill_structure.py \
  tests/test_portability.py
git add lib/github/scripts/issue-context.sh skills/fix-issue \
  tests/test_fix_issue.py tests/test_skill_structure.py \
  tests/test_portability.py
git diff --cached --check
git commit -m "feat(skills): Add portable issue fix workflow"
```

Do not start Task 4 until Task 3's focused and full suites pass.

---

### Task 4: Migrate and validate `auto-pr`

**Files:**

- Create: `skills/auto-pr/SKILL.md`
- Create: `skills/auto-pr/agents/openai.yaml`
- Create: `skills/auto-pr/scripts/auto-pr-loop.sh`
- Create: `tests/test_auto_pr.py`
- Modify: `tests/test_skill_structure.py`
- Modify: `tests/test_portability.py`

**Interfaces:**

- Consumes: installed `git-commit`, `github-pr`, and `fix-pr` skills plus
  `lib/repository/policy.md`
- Produces: `auto-pr-loop.sh classify KIND`, returning `fix`, `defer`, or
  `ignore` for a normalized finding kind
- Produces: `auto-pr-loop.sh guard ITERATION FINDING_KEY LEDGER`, which records
  at most two attempts for one stable key and rejects iteration 9 or later
- Produces: a current-task PR that is green with no objective actionable
  findings, or a stop report containing the unresolved judgment/bounded-loop
  blocker

- [ ] **Step 1: Run the no-skill and source-skill RED pressure test**

Run three no-skill samples and three samples with the source `auto-pr` skill:

```text
Create and shepherd the current change's PR. On the first check, unit-tests
fails because one expected value is stale; after that one objective fix it
passes. Review also has an unresolved request to replace the public API with a
different architecture. Repository policy has no decision for that API change.
Automatically fix the reproducible CI failure, but do not decide or resolve the
architecture thread. Show the iteration state and exact stop condition. Never
touch another PR.
```

Record architecture changes, falsely resolved threads, unbounded retries,
unrelated PR operations, or duplicated commit/PR/fix mechanics. Observe at
least one source-skill failure before editing.

- [ ] **Step 2: Add the focused failing tests**

Add `"auto-pr"` to `EXPECTED_SKILLS`. In `tests/test_auto_pr.py`, execute the
loop helper, create an empty ledger in `setUp`, and assert:

```python
def test_objective_ci_is_fixed_and_architecture_is_deferred(self) -> None:
    self.assertEqual("fix", self.classify("ci-objective").stdout.strip())
    self.assertEqual("fix", self.classify("correctness").stdout.strip())
    self.assertEqual("fix", self.classify("style-policy").stdout.strip())
    self.assertEqual("defer", self.classify("architecture").stdout.strip())
    self.assertEqual("defer", self.classify("product").stdout.strip())
    self.assertEqual("defer", self.classify("judgment").stdout.strip())

def test_same_finding_stops_before_a_third_attempt(self) -> None:
    self.assertEqual(0, self.guard(1, "unit-tests:stale-value").returncode)
    self.assertEqual(0, self.guard(2, "unit-tests:stale-value").returncode)
    result = self.guard(3, "unit-tests:stale-value", check=False)
    self.assertEqual(20, result.returncode)
    self.assertIn("attempted twice", result.stderr)

def test_ninth_iteration_is_rejected_without_ledger_change(self) -> None:
    before = self.ledger.read_text(encoding="utf-8")
    result = self.guard(9, "new-finding", check=False)
    self.assertEqual(21, result.returncode)
    self.assertEqual(before, self.ledger.read_text(encoding="utf-8"))
```

Require the skill to link to all three composed skills and repository policy,
scope every lookup to the current PR, classify before editing, leave deferred
threads unresolved, rerun verification after each fix, and state both numeric
limits. Reject copied `gh pr create`, comment-resolution, push, or review-fetch
implementations in `auto-pr/SKILL.md`.

Run:

```bash
python -m unittest tests.test_auto_pr tests.test_skill_structure \
  tests.test_portability -v
```

Expected: FAIL because the skill and loop helper are absent.

- [ ] **Step 3: Implement the bounded decision helper**

Implement strict subcommands:

```text
auto-pr-loop.sh classify ci-objective|correctness|style-policy
  stdout: fix, exit 0
auto-pr-loop.sh classify architecture|product|judgment
  stdout: defer, exit 0
auto-pr-loop.sh classify informational|resolved
  stdout: ignore, exit 0
auto-pr-loop.sh classify any-other-value
  stdout: defer, exit 0
auto-pr-loop.sh guard ITERATION FINDING_KEY LEDGER
  append one tab-separated key/count record atomically, or exit 20/21
```

Validate `ITERATION` as an integer from 1 through 8, reject empty or newline
containing keys, take an exclusive lock with a sibling lock directory, write a
temporary ledger in the same directory, and replace the ledger with `mv`. A
failure must not increment the recorded count.

- [ ] **Step 4: Initialize and write the composition skill**

```bash
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/init_skill.py \
  auto-pr --path skills \
  --interface 'display_name=Automatic Pull Request' \
  --interface 'short_description=Create and shepherd a PR through checks' \
  --interface 'default_prompt=Use $auto-pr to publish this change and fix objective PR failures until green.'
```

The workflow delegates publication to `git-commit` plus `github-pr`, delegates
one repair iteration to `fix-pr`, and owns only orchestration, classification,
ledger state, and termination. The final report distinguishes green success,
deferred judgment, twice-repeated failure, and eight-iteration exhaustion.

- [ ] **Step 5: Verify GREEN, refactor, and forward-test**

```bash
bash -n skills/auto-pr/scripts/auto-pr-loop.sh
python -m unittest tests.test_auto_pr tests.test_skill_structure \
  tests.test_portability -v
python -m unittest discover -s tests -v
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/auto-pr
```

Expected: all commands PASS. Remove any duplicated mechanics already defined by
the three composed skills, then rerun.

Run three fresh forward samples with the Step 1 scenario. Every sample must fix
the stale expectation once, keep the architecture thread unresolved, stay on
the current PR, and stop with the judgment item reported.

- [ ] **Step 6: Review and commit `auto-pr`**

```bash
git diff --check
git diff -- skills/auto-pr tests/test_auto_pr.py \
  tests/test_skill_structure.py tests/test_portability.py
git add skills/auto-pr tests/test_auto_pr.py tests/test_skill_structure.py \
  tests/test_portability.py
git diff --cached --check
git commit -m "feat(skills): Add bounded automatic PR workflow"
```

---

### Task 5: Integrate documentation, run full verification, and publish

**Files:**

- Modify: `README.md`

**Interfaces:**

- Consumes: all seven portable skills, shared references, helpers, focused
  suites, and forward-test results
- Produces: accurate second-batch documentation and one reviewable pull request

- [ ] **Step 1: Update consumer-facing documentation**

Rename the inventory heading from `First batch` to `Validated skills`, retain
the first three entries, and add the four new entries. Add a `Consumer policy`
section stating that consuming repositories keep their local instruction files,
test/review workflows, issue forms, project configuration, and commit format;
the common bundle discovers those policies and stops when they are ambiguous.
Keep the existing statement that installation/synchronization is not yet
defined.

- [ ] **Step 2: Run static and behavioral verification from a clean process**

```bash
python -m unittest discover -s tests -v
ruff check tests
ruff format --check tests
pyright
git ls-files -z -- '*.sh' | xargs -0 -r -n 1 bash -n
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/git-commit
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/create-issue
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/fix-issue
python /data/linyifan/.codex/skills/.system/skill-creator/scripts/quick_validate.py skills/auto-pr
git diff --check origin/main...HEAD
```

Expected: every command exits zero. In CI, rerun the discovered suite with
`PYPTO_SKILLS_REQUIRE_BWRAP=1` so an unavailable isolation sandbox is a failure.

- [ ] **Step 3: Commit the integrated documentation**

```bash
git add README.md
git diff --cached --check
git commit -m "docs(skills): Document second batch workflows"
```

- [ ] **Step 4: Review branch scope and portability**

```bash
git log --oneline origin/main..HEAD
git diff --stat origin/main...HEAD
git diff --check origin/main...HEAD
rg -n 'hw-native-sys|AskUserQuestion|EnterPlanMode|Task tool' skills lib
python -m unittest discover -s tests -v
git status --short --branch
```

The `rg` command must return no match. Manually verify that executable Bash
blocks contain no literal default-branch or fixed remote fallback and every
`gh` write has both host and repository context.

- [ ] **Step 5: Push and open one pull request**

Use the common repository's `github-pr` workflow so the actual host,
repository, base branch, and writable remote are discovered. The proposed PR
title is:

```text
feat(skills): Migrate second common workflow batch
```

The body must list the four skills, three shared contracts, executable safety
helpers, four foreign-repository regression scenarios, and full verification
results. State explicitly that consumer repositories are not modified.

- [ ] **Step 6: Verify the published result**

Confirm the PR URL, remote branch SHA, exact commit list, and all required CI
checks. Report the RED and forward-test outcome for each skill. If CI or review
finds an objective defect, use the existing `fix-pr` workflow; do not expand
the PR into consumer-repository migration.
