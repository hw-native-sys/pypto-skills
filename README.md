# PyPTO Skills

This repository is the canonical source for portable skills shared across
PyPTO-related repositories. It keeps reusable agent workflows and their common
GitHub mechanics together so they can be validated as one bundle.

## Validated skills

The validated bundle includes:

- `clean-branches`: identify and safely remove merged local and fork branches.
- `github-pr`: prepare, publish, create, or update pull requests across forks.
- `fix-pr`: resolve review feedback and failing checks through a bounded,
  verified repair loop.
- `git-commit`: review, verify, stage, commit, and confirm exactly the
  task-owned changes.
- `create-issue`: discover repository policy and create a confirmed,
  duplicate-checked issue.
- `fix-issue`: inspect issue state and implement an approved fix without
  crossing repository policy boundaries.
- `auto-pr`: orchestrate bounded objective repairs by composing the commit,
  pull-request, and pull-request-fix workflows.

The skills, shared references, helper scripts, metadata, and tests are
validated together. Consumers must therefore copy or sync the whole bundle
until a dedicated installer is designed.

## Consumer policy

Consuming repositories keep their local instruction files, test and review
workflows, issue forms, project configuration, and commit format. The common
bundle discovers those policies and stops when they are ambiguous.

## Layout

- `skills/` contains discoverable skills and their agent metadata.
- `lib/github/` contains shared Git and GitHub workflow references used by the
  skills.
- `tests/` validates skill structure, local links, and portability.

Consumer installation and synchronization are not yet defined. This repository
does not prescribe a submodule, vendoring, or synchronization mechanism.

## Validation

Run the standard-library test suite with:

```bash
python -m unittest discover -s tests -v
```

Install the pinned CI tools and run the same static checks with:

```bash
python -m pip install --requirement requirements-ci.txt
ruff check tests
ruff format --check tests
pyright
git ls-files -z -- '*.sh' | xargs -0 -r -n 1 bash -n
```

CI additionally installs Bubblewrap and requires the production validation
sandbox to execute successfully.
