from __future__ import annotations

import re
import unittest
from pathlib import Path

from tests.skill_assertions import ROOT

BANNED_TEXT = (
    "hw-native-sys/pypto",
    "hw-native-sys/simpler",
    "hw-native-sys/pypto-lib",
    "upstream/main",
    "origin/main",
    "AskUserQuestion",
    "EnterPlanMode",
    "Task tool",
)

DEPLOYABLE_ROOTS = (ROOT / "skills", ROOT / "lib")

REQUIRED_GITHUB_REFERENCES = (
    ROOT / "lib/github/setup.md",
    ROOT / "lib/github/lookup-pr.md",
    ROOT / "lib/github/branch-naming.md",
    ROOT / "lib/github/commit-and-push.md",
    ROOT / "lib/github/common-issues.md",
    ROOT / "lib/github/detect-permission.md",
    ROOT / "lib/github/fetch-comments.md",
    ROOT / "lib/github/reply-and-resolve.md",
    ROOT / "lib/github/checkout-fork-branch.md",
    ROOT / "lib/github/issue-context.md",
    ROOT / "lib/github/issue-templates.md",
)

REQUIRED_REPOSITORY_REFERENCES = (ROOT / "lib/repository/policy.md",)

GITHUB_CONTEXT_VARIABLES = (
    "REPO_ROOT",
    "CURRENT_BRANCH",
    "DEFAULT_BRANCH",
    "BASE_REMOTE",
    "BASE_REF",
    "PUSH_REMOTE",
    "PR_REPO",
    "PR_HEAD_PREFIX",
    "ROLE",
)

REFERENCE_INPUTS = {
    "setup.md": frozenset(),
    "lookup-pr.md": frozenset(
        {
            "CURRENT_BRANCH",
            "GITHUB_HOST",
            "PR_HEAD_BRANCH",
            "PR_HEAD_PREFIX",
            "PR_LOOKUP_ALLOW_NONE",
            "PR_LOOKUP_HELPER",
            "PR_NUMBER",
            "PR_REPO",
        }
    ),
    "branch-naming.md": frozenset(
        {"BRANCH_PREFIX", "BRANCH_SUMMARY", "CURRENT_BRANCH", "DEFAULT_BRANCH"}
    ),
    "commit-and-push.md": frozenset(
        {
            "BASE_REMOTE",
            "CURRENT_BRANCH",
            "DEFAULT_BRANCH",
            "GITHUB_HOST",
            "HEAD_REPO",
            "LOCAL_REPO",
            "MAINTAINER_CHECKOUT_VERIFIED",
            "PREPARE_PUSH_HELPER",
            "PR_HEAD_BRANCH",
            "PR_REPO",
            "PUSH_REMOTE",
            "PUSH_TRANSACTION_HELPER",
            "ROLE",
            "VALIDATION_SANDBOX",
            "WORK_BRANCH",
        }
    ),
    "common-issues.md": frozenset({"PR_NUMBER", "PR_REPO", "REPOSITORY_NODE_ID"}),
    "detect-permission.md": frozenset({"GITHUB_HOST", "PR_NUMBER", "PR_REPO"}),
    "fetch-comments.md": frozenset(
        {
            "COMMENTS_CURSOR",
            "PR_NUMBER",
            "PR_REPO",
            "REVIEWS_CURSOR",
            "THREADS_CURSOR",
        }
    ),
    "reply-and-resolve.md": frozenset(
        {
            "COMMENT_DATABASE_ID",
            "HANDLED_LEDGER",
            "HANDLED_NODE_IDS",
            "PR_NUMBER",
            "PR_REPO",
            "REPLY_BODY",
            "THREAD_ID",
        }
    ),
    "checkout-fork-branch.md": frozenset(
        {"HEAD_REPO", "PR_HEAD_BRANCH", "PR_NUMBER", "PUSH_REMOTE", "ROLE"}
    ),
    "issue-context.md": frozenset(),
    "issue-templates.md": frozenset(),
}

BASH_BLOCK_RE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
SHELL_VARIABLE_USE_RE = re.compile(r"\$(?:{!?([A-Z][A-Z0-9_]*)|([A-Z][A-Z0-9_]*))")
SHELL_ASSIGNMENT_RE = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=", re.MULTILINE)
SHELL_FOR_VARIABLE_RE = re.compile(r"^\s*for\s+([A-Z][A-Z0-9_]*)\s+in\b", re.MULTILINE)
SHELL_WHILE_READ_VARIABLE_RE = re.compile(
    r"^\s*while\b[^\n]*\bread(?:\s+-[A-Za-z]+)*\s+"
    r"([A-Z][A-Z0-9_]*)\s*;",
    re.MULTILINE,
)


def deployable_files() -> list[Path]:
    return sorted(
        path
        for root in DEPLOYABLE_ROOTS
        if root.is_dir()
        for path in root.rglob("*")
        if path.is_file()
    )


def bash_source(path: Path) -> str:
    return "\n".join(BASH_BLOCK_RE.findall(path.read_text(encoding="utf-8")))


def shell_inputs(path: Path) -> set[str]:
    source = bash_source(path)
    definitions: dict[str, list[int]] = {}

    for pattern in (
        SHELL_ASSIGNMENT_RE,
        SHELL_FOR_VARIABLE_RE,
        SHELL_WHILE_READ_VARIABLE_RE,
    ):
        for match in pattern.finditer(source):
            line_end = source.find("\n", match.end())
            definition_position = len(source) if line_end < 0 else line_end
            definitions.setdefault(match.group(1), []).append(definition_position)

    inputs = set()
    for match in SHELL_VARIABLE_USE_RE.finditer(source):
        variable = match.group(1) or match.group(2)
        if not any(
            position < match.start() for position in definitions.get(variable, [])
        ):
            inputs.add(variable)
    return inputs


class PortabilityTests(unittest.TestCase):
    def test_deployable_content_has_no_banned_text(self) -> None:
        for path in deployable_files():
            text = path.read_text(encoding="utf-8")
            for banned in BANNED_TEXT:
                with self.subTest(path=path, banned=banned):
                    self.assertNotIn(banned, text)

    def test_required_github_references_exist(self) -> None:
        for path in REQUIRED_GITHUB_REFERENCES:
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"missing required reference: {path}")

    def test_required_repository_references_exist(self) -> None:
        for path in REQUIRED_REPOSITORY_REFERENCES:
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"missing required reference: {path}")

    def test_git_commit_delegates_consumer_repository_policy(self) -> None:
        skill = ROOT / "skills/git-commit/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn("../../lib/repository/policy.md", text)
        self.assertNotRegex(text, r"\b(?:pytest|cargo test|npm test)\b")
        self.assertNotRegex(text, r"\b(?:feat|fix|refactor|chore|docs|test)\([^)]*\):")
        self.assertNotRegex(text, r"(?m)^\s*git add (?:-A|--all|\.|\*)")

    def test_create_issue_has_no_fixed_repository_or_project_policy(self) -> None:
        skill = ROOT / "skills/create-issue/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn("../../lib/github/issue-context.md", text)
        self.assertIn("../../lib/github/issue-templates.md", text)
        self.assertNotRegex(text, r"(?i)project\s+#?\d+")
        self.assertNotRegex(text, r"(?m)^\s*gh issue create\b")
        self.assertLessEqual(len(text.splitlines()), 200)

    def test_fix_issue_has_no_fixed_repository_project_or_test_policy(self) -> None:
        skill = ROOT / "skills/fix-issue/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn("../../lib/repository/policy.md", text)
        self.assertIn("../../lib/github/issue-context.md", text)
        self.assertIn("../../lib/github/branch-naming.md", text)
        self.assertNotRegex(text, r"(?i)project\s+#?\d+")
        self.assertNotRegex(text, r"\b(?:pytest|cargo test|npm test)\b")
        self.assertNotRegex(text, r"(?m)^\s*(?:fix|feat|refactor|docs|support)/")
        self.assertLessEqual(len(text.splitlines()), 200)

    def test_setup_defines_context_contract(self) -> None:
        setup = ROOT / "lib/github/setup.md"
        self.assertTrue(setup.is_file(), f"missing required reference: {setup}")
        setup_text = setup.read_text(encoding="utf-8")
        definitions = set(
            re.findall(r"(?m)^\s*(?:export )?([A-Z][A-Z0-9_]*)=", setup_text)
        )

        for variable in GITHUB_CONTEXT_VARIABLES:
            with self.subTest(variable=variable):
                self.assertIn(variable, definitions)

    def test_references_consume_only_explicit_inputs_before_definition(
        self,
    ) -> None:
        self.assertEqual(
            {path.name for path in REQUIRED_GITHUB_REFERENCES},
            set(REFERENCE_INPUTS),
        )
        for path in REQUIRED_GITHUB_REFERENCES:
            with self.subTest(path=path):
                self.assertEqual(REFERENCE_INPUTS[path.name], shell_inputs(path))

    def test_remote_validation_covers_fetch_and_push_destinations(self) -> None:
        setup = bash_source(ROOT / "lib/github/setup.md")
        self.assertIn("GITHUB_HOST=", setup)
        self.assertIn("git remote get-url --all", setup)
        self.assertIn("git remote get-url --push --all", setup)
        self.assertIn("PUSH_URL_COUNT", setup)
        self.assertRegex(
            setup,
            r'\[ "\$REMOTE_HOST" != "\$GITHUB_HOST" \]',
        )

    def test_push_branch_requires_verified_role_context(self) -> None:
        reference = bash_source(ROOT / "lib/github/commit-and-push.md")
        self.assertIn("owner|fork)", reference)
        self.assertIn(
            '[ "$PR_HEAD_BRANCH" != "$CURRENT_BRANCH" ]',
            reference,
        )
        self.assertIn("MAINTAINER_CHECKOUT_VERIFIED", reference)
        self.assertIn(
            'remote_targets_repo "$PUSH_REMOTE" "$EXPECTED_PUSH_REPO"',
            reference,
        )

    def test_author_workflow_requires_head_repository_push_permission(
        self,
    ) -> None:
        reference = bash_source(ROOT / "lib/github/detect-permission.md")
        self.assertIn(
            'HEAD_CAN_PUSH=$(gh api --hostname "$GITHUB_HOST" "repos/$HEAD_REPO"',
            reference,
        )
        self.assertIn('[ "$HEAD_CAN_PUSH" != "true" ]', reference)

    def test_rewritten_pushes_use_force_with_lease(self) -> None:
        reference = ROOT / "lib/github/commit-and-push.md"
        self.assertTrue(reference.is_file(), f"missing required reference: {reference}")
        text = reference.read_text(encoding="utf-8")
        self.assertIn("git push --force-with-lease", text)
        self.assertNotRegex(text, r"git push\s+--force(?!-with-lease)")

    def test_github_pr_uses_all_shared_workflow_references(self) -> None:
        skill = ROOT / "skills/github-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        expected_links = (
            "../../lib/github/setup.md",
            "../../lib/github/lookup-pr.md",
            "../../lib/github/branch-naming.md",
            "../../lib/github/commit-and-push.md",
            "../../lib/github/detect-permission.md",
            "../../lib/github/checkout-fork-branch.md",
        )
        for link in expected_links:
            with self.subTest(link=link):
                self.assertIn(link, text)

    def test_pull_request_skills_fit_the_portable_instruction_budget(self) -> None:
        for relative_path in (
            "skills/auto-pr/SKILL.md",
            "skills/fix-pr/SKILL.md",
            "skills/github-pr/SKILL.md",
        ):
            path = ROOT / relative_path
            with self.subTest(path=relative_path):
                self.assertLessEqual(
                    len(path.read_text(encoding="utf-8").splitlines()),
                    200,
                )

    def test_auto_pr_contains_no_publication_or_repair_implementation(self) -> None:
        skill = ROOT / "skills/auto-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn("../git-commit/SKILL.md", text)
        self.assertIn("../github-pr/SKILL.md", text)
        self.assertIn("../fix-pr/SKILL.md", text)
        self.assertIn("../../lib/repository/policy.md", text)
        self.assertNotRegex(text, r"(?m)^\s*(?:gh|git)\s+(?:pr|api|push|commit)\b")
        self.assertNotIn("resolveReviewThread", text)
        self.assertNotIn("reviewThreads", text)

    def test_github_pr_selects_create_branch_before_push_authority(self) -> None:
        text = (ROOT / "skills/github-pr/SKILL.md").read_text(encoding="utf-8")
        branch_selection = text.find("## Select and verify the working branch")
        authority_capture = text.find("## Capture push authority before commit work")
        self.assertGreaterEqual(branch_selection, 0)
        self.assertGreater(authority_capture, branch_selection)

    def test_github_pr_fails_closed_when_branch_state_commands_fail(self) -> None:
        source = bash_source(ROOT / "skills/github-pr/SKILL.md")
        self.assertIn(
            "WORKTREE_STATUS=$(git status --porcelain) || {",
            source,
        )
        self.assertIn(
            'COMMITS_AHEAD=$(git rev-list --count "$BASE_REF"..HEAD) || {',
            source,
        )
        self.assertNotRegex(source, r'\[ [^\n]*"\$\(git (?:status|rev-list)')

    def test_github_pr_supports_create_and_existing_pr_update_routes(self) -> None:
        skill = ROOT / "skills/github-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertNotIn("gh pr create", text)
        self.assertIn('"$PR_CONTEXT_HELPER" create', text)
        self.assertIn("gh pr edit", text)
        self.assertIn("existing pull request", text.lower())
        self.assertIn("DEFAULT_BRANCH", text)
        self.assertIn("PR_REPO", text)
        self.assertIn("--force-with-lease", text)
        self.assertIn("PR_ROUTE=$(printf '%s' \"$PR_LOOKUP_RESULT\"", text)
        self.assertIn('[ "$PR_ROUTE" = "create" ]', text)
        self.assertIn('[ "$PR_ROUTE" = "update" ]', text)

    def test_github_pr_delegates_repository_commit_policy(self) -> None:
        skill = ROOT / "skills/github-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn("repository-local `git-commit` skill", text)
        self.assertNotRegex(text, r"\b(?:feat|fix|refactor|chore|docs|test)/")
        self.assertNotIn("## Testing\n- [ ]", text)

    def test_github_pr_is_host_aware_and_fork_safe(self) -> None:
        skill = ROOT / "skills/github-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn('GH_HOST="$GITHUB_HOST"', text)
        self.assertIn("../../lib/github/scripts/pr-context.sh", text)
        self.assertIn("HEAD_REPO=$LOCAL_REPO", text)
        self.assertIn("ROLE", text)
        self.assertIn("HEAD_REPO", text)
        self.assertIn("MAINTAINER_CHECKOUT_VERIFIED", text)

        guard = text.find('"$PR_CONTEXT_HELPER" guard-branch')
        commit = text.find("repository-local `git-commit` skill")
        self.assertGreaterEqual(guard, 0)
        self.assertGreater(commit, guard)

    def test_pull_request_lookup_uses_supported_host_pinned_rest_api(self) -> None:
        skill = ROOT / "skills/github-pr/SKILL.md"
        reference = ROOT / "lib/github/lookup-pr.md"
        helper = ROOT / "lib/github/scripts/pr-context.sh"
        for path in (skill, reference, helper):
            with self.subTest(path=path):
                self.assertTrue(path.is_file(), f"missing required file: {path}")
        if not all(path.is_file() for path in (skill, reference, helper)):
            return

        skill_text = skill.read_text(encoding="utf-8")
        reference_text = reference.read_text(encoding="utf-8")
        helper_text = helper.read_text(encoding="utf-8")
        self.assertIn("../../lib/github/scripts/pr-context.sh", skill_text)
        self.assertIn("scripts/pr-context.sh", reference_text)
        for document_text in (skill_text, reference_text):
            self.assertIn(
                'gh api --hostname "$GITHUB_HOST" --method GET',
                document_text,
            )
            self.assertIn('"repos/$PR_REPO/pulls"', document_text)
            self.assertIn('-f "head=$HEAD_SELECTOR"', document_text)
            self.assertIn("--paginate --slurp", document_text)
            self.assertIn("separately with `jq -e 'add'`", document_text)
            self.assertNotIn("--slurp --jq", document_text)
        self.assertNotRegex(bash_source(skill), r"gh pr list[\s\S]{0,200}--head")
        self.assertNotRegex(reference_text, r"gh pr list[\s\S]{0,200}--head")
        self.assertIn('gh api --hostname "$GITHUB_HOST" --method GET', helper_text)
        self.assertIn('"repos/$PR_REPO/pulls"', helper_text)
        self.assertIn('-f "head=$HEAD_SELECTOR"', helper_text)
        self.assertIn("--paginate --slurp", helper_text)
        self.assertIn("| jq -ce '", helper_text)
        self.assertNotIn("--slurp --jq", helper_text)

    def test_pull_request_creation_uses_host_pinned_rest_post(self) -> None:
        skill = ROOT / "skills/github-pr/SKILL.md"
        helper = ROOT / "lib/github/scripts/pr-context.sh"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        self.assertTrue(helper.is_file(), f"missing required helper: {helper}")
        if not skill.is_file() or not helper.is_file():
            return

        skill_text = skill.read_text(encoding="utf-8")
        helper_text = helper.read_text(encoding="utf-8")
        self.assertNotIn("gh pr create", skill_text)
        self.assertIn('"$PR_CONTEXT_HELPER" create', skill_text)
        for text in (skill_text, helper_text):
            self.assertIn('gh api --hostname "$GITHUB_HOST" --method POST', text)
            self.assertIn('"repos/$PR_REPO/pulls"', text)
            self.assertIn('"head_repo=$HEAD_REPO_NAME"', text)
            self.assertIn(".html_url", text)

    def test_author_guard_checks_branch_and_repository_before_commit(self) -> None:
        skill = ROOT / "skills/github-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        guard = text.find('"$PR_CONTEXT_HELPER" guard-branch')
        commit = text.find("repository-local `git-commit` skill")
        self.assertGreaterEqual(guard, 0)
        self.assertGreater(commit, guard)
        guard_block = text[guard:commit]
        self.assertIn('"$CURRENT_BRANCH" "$PR_HEAD_BRANCH"', guard_block)
        self.assertIn('"$LOCAL_REPO" "$HEAD_REPO"', guard_block)

    def test_known_pr_number_is_validated_before_positional_gh_use(self) -> None:
        skill = ROOT / "skills/github-pr/SKILL.md"
        reference = ROOT / "lib/github/lookup-pr.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        self.assertTrue(reference.is_file(), f"missing required reference: {reference}")
        if not skill.is_file() or not reference.is_file():
            return

        skill_text = skill.read_text(encoding="utf-8")
        reference_text = reference.read_text(encoding="utf-8")
        self.assertIn('"$PR_CONTEXT_HELPER" validate-number "$PR_NUMBER"', skill_text)
        validation = reference_text.find(
            '"$PR_LOOKUP_HELPER" validate-number "$PR_NUMBER"'
        )
        positional_use = reference_text.find('gh pr view "$PR_NUMBER"')
        self.assertGreaterEqual(validation, 0)
        self.assertGreater(positional_use, validation)

    def test_github_pr_derives_title_and_body_from_pr_commit_range(self) -> None:
        skill = ROOT / "skills/github-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertGreaterEqual(text.count('"$BASE_REF"..HEAD'), 2)
        self.assertNotIn("Brief description of changes", text)
        self.assertNotIn("Key change 1", text)

    def test_fix_pr_uses_all_shared_workflow_references(self) -> None:
        skill = ROOT / "skills/fix-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        expected_links = (
            "../../lib/github/setup.md",
            "../../lib/github/lookup-pr.md",
            "../../lib/github/fetch-comments.md",
            "../../lib/github/detect-permission.md",
            "../../lib/github/checkout-fork-branch.md",
            "../../lib/github/commit-and-push.md",
            "../../lib/github/reply-and-resolve.md",
            "../../lib/github/common-issues.md",
        )
        for link in expected_links:
            with self.subTest(link=link):
                self.assertIn(link, text)

    def test_fix_pr_fetches_every_feedback_surface_and_page(self) -> None:
        skill = ROOT / "skills/fix-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        for surface in ("reviewThreads", "reviews", "comments"):
            with self.subTest(surface=surface):
                self.assertIn(surface, text)
        self.assertIn("hasNextPage", text)
        self.assertIn("endCursor", text)
        self.assertIn("nested `comments`", text)
        self.assertIn("handled ledger", text)

    def test_fix_pr_waits_for_pending_ci_and_supports_external_checks(self) -> None:
        skill = ROOT / "skills/fix-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn("Pending checks are not clean", text)
        self.assertIn("whole-run logs", text)
        self.assertIn("completed", text)
        self.assertIn("external check", text.lower())
        self.assertIn("details URL", text)

    def test_fix_pr_is_host_aware_and_selects_a_verified_write_path(self) -> None:
        skill = ROOT / "skills/fix-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn('GH_HOST="$GITHUB_HOST"', text)
        permission = text.find("../../lib/github/detect-permission.md")
        checkout = text.find("../../lib/github/checkout-fork-branch.md")
        commit = text.find("../../lib/github/commit-and-push.md")
        self.assertGreaterEqual(permission, 0)
        self.assertGreater(checkout, permission)
        self.assertGreater(commit, checkout)
        for role in ("owner", "fork", "maintainer"):
            with self.subTest(role=role):
                self.assertIn(f"`{role}`", text)

    def test_fix_pr_requires_confirmation_before_scoped_fixes(self) -> None:
        skill = ROOT / "skills/fix-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        findings = text.find("## Classify and present findings")
        confirmation = text.find("## Explicit confirmation gate")
        fixes = text.find("## Apply selected fixes")
        self.assertGreaterEqual(findings, 0)
        self.assertGreater(confirmation, findings)
        self.assertGreater(fixes, confirmation)
        self.assertIn("fix immediately", text)

    def test_fix_pr_auto_pr_authorization_is_narrow_and_fail_closed(self) -> None:
        skill = ROOT / "skills/fix-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        findings = text.find("## Classify and present findings")
        composed = text.find("## Validate auto-pr composed authorization")
        confirmation = text.find("## Explicit confirmation gate")
        self.assertGreater(composed, findings)
        self.assertGreater(confirmation, composed)
        gate = text[confirmation : text.find("## Apply selected fixes")]
        self.assertIn("Do not edit until the user confirms", gate)
        self.assertIn("every direct invocation", text)
        self.assertRegex(text, r"only when the active caller is `auto-pr`")
        for requirement in (
            "active caller is `auto-pr`",
            "exact host, repository, number, and head",
            "unchanged numbered inventory entry and stable finding ID",
            "`ci-objective`, `correctness`, or `style-policy`",
            "successful guard iteration and attempt evidence",
            "standing authorization from an explicit `auto-pr` invocation",
            "independently revalidate",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, text)
        self.assertIn("fall back to the explicit confirmation gate", text)
        self.assertIn("unknown or deferred kind", text)
        for mismatch in (
            "identity or head mismatch",
            "inventory entry or stable finding ID mismatch",
            "kind or classification mismatch",
            "guard or ledger mismatch",
        ):
            with self.subTest(mismatch=mismatch):
                self.assertIn(mismatch, text)
        self.assertIn("do not auto-repair", text)
        self.assertIn("without incrementing it", text)
        self.assertRegex(text, r"scope\s+growth")
        self.assertIn("same stable key", text)

    def test_fix_pr_delegates_repository_policy(self) -> None:
        skill = ROOT / "skills/fix-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn("repository-local instructions", text)
        self.assertIn("repository-local testing skill", text)
        self.assertIn("repository-local `git-commit` skill", text)
        self.assertNotRegex(text, r"\b(?:pytest|cargo test|npm test)\b")
        self.assertNotIn('git commit -m "fix(pr)', text)

    def test_fix_pr_folds_commits_and_pushes_with_shared_safety(self) -> None:
        skill = ROOT / "skills/fix-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn("fixup", text)
        self.assertIn("autosquash", text)
        self.assertIn("PR-owned commit", text)
        self.assertIn("--force-with-lease", text)

    def test_fix_pr_replies_then_resolves_only_verified_fixes(self) -> None:
        skill = ROOT / "skills/fix-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        verified = text.find("Verify the selected fixes")
        reply = text.find("Reply first")
        resolve = text.find("Resolve second")
        self.assertGreaterEqual(verified, 0)
        self.assertGreater(reply, verified)
        self.assertGreater(resolve, reply)
        self.assertIn("isResolved", text)

    def test_fix_pr_rechecks_with_iteration_and_stuck_bounds(self) -> None:
        skill = ROOT / "skills/fix-pr/SKILL.md"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn("maximum of 5 iterations", text)
        self.assertIn("same fingerprint", text)
        self.assertIn("final recheck", text)
        self.assertIn("blocker", text)

    def test_clean_branches_uses_portable_safe_deletion_contract(self) -> None:
        skill = ROOT / "skills/clean-branches/SKILL.md"
        helper = ROOT / "skills/clean-branches/scripts/clean-branches.sh"
        self.assertTrue(skill.is_file(), f"missing required skill: {skill}")
        self.assertTrue(helper.is_file(), f"missing required helper: {helper}")
        if not skill.is_file():
            return

        text = skill.read_text(encoding="utf-8")
        self.assertIn("../../lib/github/setup.md", text)
        self.assertIn("scripts/clean-branches.sh", text)
        self.assertIn("DEFAULT_BRANCH", text)
        self.assertIn("headRefOid", text)
        self.assertIn("Approved OID", text)
        self.assertIn("Never delete from `$BASE_REMOTE`", text)

        approval = re.search(r"(?im)^## Explicit approval gate$", text)
        self.assertIsNotNone(approval)
        if approval is None:
            return

        destructive_commands = (
            '"$CLEAN_BRANCHES_HELPER" delete-local',
            '"$CLEAN_BRANCHES_HELPER" delete-remote',
        )
        for command in destructive_commands:
            with self.subTest(command=command):
                command_position = text.find(command)
                self.assertGreaterEqual(command_position, 0)
                self.assertLess(approval.start(), command_position)


if __name__ == "__main__":
    unittest.main()
