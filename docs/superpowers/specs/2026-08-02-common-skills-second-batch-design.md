# Common Skills Second-Batch Migration Design

## Context

The first migration batch established portable `github-pr`, `fix-pr`, and
`clean-branches` skills plus shared GitHub workflow contracts. The second batch
will migrate four related workflows from consumer repositories:

- `git-commit`
- `create-issue`
- `fix-issue`
- `auto-pr`

Their current copies encode assumptions from the repositories that host them:
fixed organizations and remotes, a `main` default branch, repository-specific
test commands, commit-message formats, issue templates, and project-board
fields. Moving those copies unchanged would make the shared repository appear
portable without actually being safe to reuse.

This batch will therefore extract workflow intent while making repository
policy and GitHub state explicit inputs. All four skills will ship in one pull
request, but each skill must independently pass a red-green-refactor migration
cycle before work starts on the next skill.

## Goals

- Provide portable versions of all four skills in one release batch.
- Preserve consumer-repository instructions as the authority for tests,
  reviews, hooks, commit messages, and documentation requirements.
- Discover GitHub repository state instead of assuming an organization,
  default branch, remote name, issue template, or project board.
- Make every external mutation reviewable and narrowly scoped.
- Reuse the first batch's GitHub workflow contracts where the workflows
  overlap.
- Demonstrate portability with foreign-repository scenarios and fake GitHub
  boundaries that perform no real external writes.

This batch will not migrate project-specific testing, code-review, changelog,
operator-development, profiling, or code-generation skills. It will not define
a universal commit convention, require a project board, or automate decisions
that need architectural judgment.

## Source Selection

The migration will compare the latest default-branch versions in PyPTO,
`simpler`, and `pypto-lib` where a skill exists. The source copies are evidence
of desired behavior, not files to concatenate:

- `git-commit` exists in all three repositories and exposes different commit,
  test, and review conventions.
- `create-issue` exists in all three repositories and exposes different issue
  forms, labels, and project metadata.
- `fix-issue` exists in PyPTO and `simpler` and combines issue state, branch
  setup, planning, and implementation.
- `auto-pr` exists in PyPTO and composes the already migrated `github-pr` and
  `fix-pr` workflows.

The shared version keeps behavior that is common or configurable. A behavior
that exists only because of one consumer repository becomes consumer policy or
is omitted.

## Chosen Approach

Use four self-contained skill directories backed by three small shared
contracts:

```text
skills/git-commit/
skills/create-issue/
skills/fix-issue/
skills/auto-pr/
lib/repository/policy.md
lib/github/issue-context.md
lib/github/issue-templates.md
tests/test_git_commit.py
tests/test_create_issue.py
tests/test_fix_issue.py
tests/test_auto_pr.py
```

Each skill retains its own entry point and can be installed independently.
Shared contracts contain only behavior used across multiple workflows or
behavior whose consistency is security-sensitive.

A single combined skill was rejected because consumers need to install and
invoke these workflows independently. Four fully duplicated skills were also
rejected because repository resolution, issue discovery, and policy lookup
would drift over time.

## Shared Repository Policy Contract

`lib/repository/policy.md` defines how a skill discovers and applies the
consumer repository's policy. The precedence is:

1. System and user instructions.
2. Repository instruction files applicable to the files in scope.
3. Documented repository workflows and configuration.
4. Established local history, only when written policy is absent.

This contract covers required tests, review steps, hooks, documentation,
branch naming, and commit-message format. It must not prescribe PyPTO,
`simpler`, or `pypto-lib` commands. When sources conflict or the required
policy remains ambiguous, the workflow stops and asks the user instead of
inventing a convention.

Repository policy also defines ownership boundaries. Existing modifications
belong to the user unless the current task clearly created them. Skills may
inspect all changes but may stage, edit, or commit only the authorized scope.

## Shared GitHub Issue Contracts

`lib/github/issue-context.md` defines read-only discovery for:

- the GitHub host and repository derived from the current checkout;
- the repository's default branch;
- the issue body, labels, assignees, state, and linked pull requests;
- current assignment or project status when relevant; and
- related open and closed issues used for duplicate assessment.

`lib/github/issue-templates.md` defines discovery and interpretation of issue
forms and legacy templates from the target repository. Required template
fields are completed from user-provided facts; missing facts remain visible
instead of being fabricated. A repository with no suitable template falls
back to a concise structured body.

All GitHub commands explicitly pin the resolved host and repository. The
contracts must not rely on an ambient `gh` default, a fixed remote name, or a
fixed organization. Project-board updates occur only when the consumer
repository explicitly configures that workflow and exposes enough metadata to
perform it safely.

## `git-commit` Workflow

The portable `git-commit` skill will:

1. Resolve applicable repository instructions and inspect worktree state.
2. Separate task-owned changes from unrelated or uncertain changes.
3. Review the authorized diff and run the policy-required verification.
4. Derive a commit message from repository policy and local history.
5. Show the exact files and message, stage only those paths, commit, and verify
   the resulting commit.

It must never use broad staging such as `git add -A`. If an authorized file
contains overlapping user changes that cannot be separated safely, the skill
stops for direction. It must not assume Conventional Commits, a `Type:` trailer,
or any other universal message shape.

## `create-issue` Workflow

The portable `create-issue` skill will:

1. Resolve the exact host and repository.
2. Classify the request using the repository's current issue forms or
   templates.
3. Search both open and closed issues for duplicates and related work.
4. Draft the title, labels, and complete body using known facts.
5. Preview the target host/repository, title, labels, and full body.
6. Require explicit user confirmation before creating the issue.
7. Perform only configured follow-up metadata updates and report the result.

A related issue is not automatically a duplicate. The preview must identify
the relationship so the user can decide. Creating the issue, adding labels,
and updating a project are separate mutations; optional follow-up failure must
be reported accurately without claiming that issue creation failed.

The preview renders labels as a counted, byte-length-delimited sequence and
rejects control characters in titles or labels, so its human approval framing
is reversible. The token continues to bind the actual host, repository, title,
label arguments, and immutable body snapshot.

After the create command is invoked, classify failure conservatively. A
successful CLI exit with an invalid response is a created issue whose response
could not be validated; a nonzero exit after invocation has unknown server-side
outcome. Preserve stdout and stderr in private files without echoing unsafe raw
bytes. Never retry either case until a host- and repository-pinned read-only
lookup checks the approved title/body/labels and absence is sufficiently
established for fresh user approval.

Accept a returned URL only when it has the exact canonical path
`https://HOST/OWNER/REPO/issues/<positive-integer>` for the validated literal
host and repository, with no user information, port, extra path, query, or
fragment. Model interruption explicitly: signals before the logical mutation
boundary are confirmed not created; signals from that boundary through complete
validated URL output are unknown. Response captures remain available until the
success output completes, eliminating a cleanup-to-output classification gap.
Capture `SIGPIPE` under the same state machine and check the final stdout write
explicitly. Diagnostics use a stderr descriptor preserved at startup, avoiding
command-local redirection changes. If its consumer is also gone, append the
sanitized outcome, verification target, and retry block to the retained private
stderr capture as a best-effort forensic fallback; never echo raw response data.

## `fix-issue` Workflow

The portable `fix-issue` skill will:

1. Resolve and read the issue and repository context without mutation.
2. Check whether the issue is open, already assigned, already in progress, or
   associated with an active pull request.
3. Reproduce or validate the requested behavior and inspect relevant code.
4. Produce a concrete implementation and test design for user approval.
5. Only after design approval, perform configured claim/status actions, create
   an appropriate branch, and implement using repository policy.
6. Verify the change and hand off to the appropriate commit or PR workflow.

Before design approval it must not assign the issue, update a project board,
create implementation changes, or claim that work has started. If another
person owns the issue or it is already marked in progress, the skill stops and
asks before taking ownership or duplicating work. Fork-based checkouts and
nonstandard default branches are supported through discovery rather than
special cases.

Conflict approval uses one canonical envelope, not category names alone. The
envelope binds the fixed host/repository/issue identity and state plus sorted
assignee logins, matching project item/status identities, and active pull
request number/head/state records. The authoritative reread must match the
complete canonical payload; replacing an object inside the same conflict
category fails closed and requires new approval.

## `auto-pr` Workflow

The portable `auto-pr` skill composes `github-pr` and `fix-pr` rather than
duplicating them. It will:

1. Prepare and publish the authorized change through the shared commit and PR
   workflows.
2. Monitor only the pull request created or selected for the current task.
3. Classify failing checks and unresolved review feedback.
4. Automatically fix reproducible CI failures and objective correctness
   issues, then re-run repository-required verification.
5. Apply style feedback only according to repository policy.
6. Defer architectural, product, or otherwise judgment-heavy feedback to the
   user, leaving it visibly unresolved.
7. Stop when the pull request is green and has no actionable unresolved
   feedback, or when a bounded-loop stop condition is reached.

The same underlying failure may be auto-fixed at most twice. The overall loop
is capped at eight iterations. Hitting either bound stops the workflow with a
diagnostic summary; it does not suppress checks, resolve comments without a
fix, or widen the task scope. Automation is scoped to the current pull request
and cannot mutate unrelated issues or pull requests.

## Skill Format and Portability Rules

Each skill uses only `name` and `description` in YAML frontmatter. Instructions
must describe observable actions and stop conditions without depending on
Claude-only tools such as `Task`, `AskUserQuestion`, or `EnterPlanMode`.

Tests and static checks will reject fixed occurrences of:

- `hw-native-sys` or another source organization;
- `main` as an assumed default branch;
- fixed remote names;
- project numbers or field identifiers; and
- repository-specific test commands.

Examples may use illustrative names only when they are clearly non-normative
and cannot be copied into an executable path.

## Sequential Migration and Test Strategy

The implementation order is:

1. `git-commit`
2. `create-issue`
3. `fix-issue`
4. `auto-pr`

For each skill, complete the following cycle before migrating the next one:

1. **RED:** run a foreign-repository pressure scenario without the common
   skill and record the specific incorrect or incomplete behavior.
2. Add a failing automated regression test that captures the observed gap.
3. **GREEN:** migrate the minimum instruction and shared-contract changes
   needed to make the scenario pass.
4. Re-run the focused test and full discovered test suite.
5. **REFACTOR:** remove repository assumptions, tighten ambiguous wording, and
   re-run the tests.
6. Review the skill against its source variants, shared contracts, and safety
   boundaries before proceeding.

The foreign-repository scenarios are:

- `git-commit`: the default branch is `trunk`, policy requires a
  `Change-Type:` commit field, and unrelated user edits are present.
- `create-issue`: the repository uses a custom issue form, has no project
  board, and search finds a related issue that is not a duplicate.
- `fix-issue`: the checkout uses a fork, the issue is already assigned, and
  repository policy specifies a custom test command.
- `auto-pr`: one objective CI failure can be fixed, while one unresolved review
  thread requires architectural judgment and must be deferred.

Automated tests use Python's standard-library `unittest`, temporary Git
repositories and bare remotes, and fake `gh` executables. They must not access
or mutate real GitHub state. Assertions inspect command arguments, staged
paths, rendered previews, mutation order, and stop behavior rather than merely
searching for reassuring prose.

Forward testing then exercises each completed skill in a fresh scenario to
look for loopholes not encoded by the regression test. Any newly observed
failure becomes another red test before the instruction is changed.

## Failure and Safety Behavior

- Ambiguous repository identity, policy, ownership, or required user intent is
  a stop condition.
- Read-only discovery may proceed without confirmation; external writes must
  remain within the requested workflow and use the required preview or
  approval boundary.
- No skill may expose credentials, use ambient repository selection, or write
  to a different host/repository than the previewed target.
- A partial external success is reported as partial success with the exact
  remaining action; it is never silently retried against a guessed target.
- A write whose server-side result cannot be disproved is an unknown outcome,
  not a confirmed failure; retain its private response and verify read-only
  against the fixed host/repository before considering a retry.
- Existing user changes and unrelated GitHub objects remain untouched.

## Acceptance Criteria

- All four skills are present, independently usable, and installed through the
  repository's existing distribution mechanism.
- Each skill has a recorded red-green-refactor cycle and a focused automated
  test covering its foreign-repository scenario.
- Shared contracts contain no consumer-specific organization, branch, remote,
  project, or test-command assumptions.
- `git-commit` stages only approved paths and follows discovered commit policy.
- `create-issue` previews the full mutation and requires confirmation.
- `fix-issue` performs no ownership or implementation mutation before design
  approval and stops on existing ownership conflicts.
- `auto-pr` defers judgment-heavy feedback and obeys both loop limits.
- The full unit suite, formatting, lint, type, shell, and Bubblewrap-backed CI
  checks pass.
- Documentation explains how consumer repositories supply their local policy
  without forking the common skills.
