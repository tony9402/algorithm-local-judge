from __future__ import annotations

from problem_studio.core.templates import create_problem as create_problem_template
from problem_studio.web.app import create_app
from tests.e2e.helpers import (
    BrowserE2ETestCase,
    assert_visible_in_viewport,
    create_studio_problem,
    isolated_runtime,
    run_app,
    set_studio_editor_value,
    wait_for_studio_file_ready,
    wait_for_text,
)
from tests.e2e.problem_studio_fakes import (
    git,
)


class ProblemStudioGitE2ETest(BrowserE2ETestCase):
    def test_git_fetch_pull_main_branch_push_and_write_disabled_ui(self) -> None:
        with isolated_runtime("alj-problem-studio-git-policy-e2e-") as (_directory, root):
            remote = root / "remote.git"
            workspace = root / "workspace"
            git(root, "init", "--bare", str(remote))
            git(root, "clone", str(remote), str(workspace))
            git(workspace, "checkout", "-b", "main")
            git(workspace, "config", "user.email", "studio@example.com")
            git(workspace, "config", "user.name", "Problem Studio")
            (workspace / "problems").mkdir()
            (workspace / "problems" / ".gitkeep").write_text("", encoding="utf-8")
            git(workspace, "add", "problems/.gitkeep")
            git(workspace, "commit", "-m", "initial")
            git(workspace, "push", "-u", "origin", "main")

            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_text(page, "#gitStatus", "main")
                page.wait_for_function(
                    "() => document.getElementById('gitPushButton')?.disabled === false"
                )
                self.browser_errors.clear()
                page.locator("#gitPullButton").click()
                wait_for_text(page, "#gitStatus", "ahead 0 / behind 0")
                page.locator("#gitFetchButton").click()
                wait_for_text(page, "#gitStatus", "ahead 0 / behind 0")
                page.locator("#gitPushButton").click()
                wait_for_text(page, "#gitStatus", "ahead 0 / behind 0")
                self.assert_no_browser_errors()

            with run_app(create_app(workspace, git_write_enabled=False)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_text(page, "#gitStatus", "main")
                wait_for_text(page, "#gitStatus", "Git network/write actions are disabled")
                page.wait_for_function(
                    """() => {
                        const ids = [
                            "gitFetchButton",
                            "gitPullButton",
                            "gitCommitButton",
                            "gitPushButton",
                        ];
                        return ids.every((id) => document.getElementById(id)?.disabled === true);
                    }"""
                )
                self.assertTrue(page.locator("#gitFetchButton").is_disabled())
                self.assertTrue(page.locator("#gitPullButton").is_disabled())
                self.assertTrue(page.locator("#gitCommitButton").is_disabled())
                self.assertTrue(page.locator("#gitPushButton").is_disabled())
                self.browser_errors.clear()
                self.assert_no_browser_errors()

            with run_app(
                create_app(workspace, git_write_enabled=False, workspace_warning=True)
            ) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_text(page, "#workspaceStatus", "워크스페이스 열기와 파일 저장 API")
                wait_for_text(page, "#gitStatus", "Git network/write actions are disabled")
                self.browser_errors.clear()
                self.assert_no_browser_errors()

    def test_git_tool_repository_remote_is_warned_and_blocked_in_browser(self) -> None:
        with isolated_runtime("alj-problem-studio-git-wrong-repo-e2e-") as (_directory, root):
            remote = root / "remote.git"
            workspace = root / "workspace"
            git(root, "init", "--bare", str(remote))
            git(root, "clone", str(remote), str(workspace))
            git(workspace, "checkout", "-b", "feature/e2e")
            git(workspace, "config", "user.email", "studio@example.com")
            git(workspace, "config", "user.name", "Problem Studio")
            (workspace / "problems").mkdir()
            (workspace / "problems" / ".gitkeep").write_text("", encoding="utf-8")
            git(workspace, "add", "problems/.gitkeep")
            git(workspace, "commit", "-m", "initial")
            git(workspace, "push", "-u", "origin", "feature/e2e")
            git(
                workspace,
                "remote",
                "set-url",
                "origin",
                "https://github.com/tony9402/algorithm-local-judge.git",
            )

            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#newProblemButton").wait_for(state="visible")
                wait_for_text(page, "#gitStatus", "algorithm-local-judge")
                wait_for_text(page, "#gitStatus", "algorithm-package")
                wait_for_text(page, "#gitStatus", "Git 동기화 작업을 막았습니다")
                page.wait_for_function(
                    """() => {
                        const ids = [
                            "gitFetchButton",
                            "gitPullButton",
                            "gitCommitButton",
                            "gitPushButton",
                        ];
                        return ids.every((id) => document.getElementById(id)?.disabled === true);
                    }"""
                )
                self.assert_no_browser_errors()

    def test_git_status_commit_push_and_responsive_layout_in_browser(self) -> None:
        with isolated_runtime("alj-problem-studio-git-e2e-") as (_directory, root):
            remote = root / "remote.git"
            workspace = root / "workspace"
            git(root, "init", "--bare", str(remote))
            git(root, "clone", str(remote), str(workspace))
            git(workspace, "checkout", "-b", "feature/e2e")
            git(workspace, "config", "user.email", "studio@example.com")
            git(workspace, "config", "user.name", "Problem Studio")
            (workspace / "problems").mkdir()
            (workspace / "problems" / ".gitkeep").write_text("", encoding="utf-8")
            git(workspace, "add", "problems/.gitkeep")
            git(workspace, "commit", "-m", "initial")
            git(workspace, "push", "-u", "origin", "feature/e2e")

            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url, width=390, height=844)
                page.goto(server.url)
                page.locator("#sidebarToggle").wait_for(state="visible")
                page.locator("#sidebarToggle").click()
                page.locator("#newProblemButton").wait_for(state="visible")
                create_studio_problem(page, "gamma", "Gamma Git")
                wait_for_text(page, "#gitStatus", "커밋되지 않은 변경")
                page.locator("#sidebarClose").click()
                page.locator('[data-tab="generator"]').click()
                wait_for_studio_file_ready(page, "generator/cases.yml")
                set_studio_editor_value(
                    page,
                    "profiles:\n"
                    "  hidden:\n"
                    "    cases:\n"
                    "      - name: git-auto-save\n"
                    "        type: fixed\n"
                    "        content: |\n"
                    "          1\n",
                )
                wait_for_text(page, "#fileStatus", "수정됨")
                page.locator("#sidebarToggle").click()
                page.locator("#gitCommitMessage").wait_for(state="visible")
                page.locator("#gitCommitMessage").fill("Add gamma")
                page.locator("#gitCommitButton").click()
                wait_for_text(page, "#gitStatus", "clean", timeout=30_000)
                self.assertIn(
                    "git-auto-save",
                    (workspace / "problems" / "gamma" / "generator" / "cases.yml").read_text(
                        encoding="utf-8"
                    ),
                )
                page.locator("#gitPushButton").click()
                wait_for_text(page, "#gitStatus", "ahead 0 / behind 0", timeout=30_000)
                wait_for_text(page, "#problemTitle", "Gamma Git", timeout=30_000)

                page.locator("#newProblemButton").click()
                assert_visible_in_viewport(
                    self,
                    page.locator("#newProblemModal .modal-content"),
                )
                self.assert_no_browser_errors()

    def test_repository_clone_select_commit_and_push_in_browser(self) -> None:
        with isolated_runtime("alj-problem-studio-repository-clone-e2e-") as (_directory, root):
            remote = root / "remote.git"
            seed = root / "seed"
            workspace = root / "studio"
            git(root, "init", "--bare", str(remote))
            git(root, "clone", str(remote), str(seed))
            git(seed, "checkout", "-b", "main")
            git(seed, "config", "user.email", "studio@example.com")
            git(seed, "config", "user.name", "Problem Studio")
            (seed / "problems").mkdir()
            (seed / "problems" / ".gitkeep").write_text("", encoding="utf-8")
            git(seed, "add", "problems/.gitkeep")
            git(seed, "commit", "-m", "initial")
            git(seed, "push", "-u", "origin", "main")
            git(remote, "symbolic-ref", "HEAD", "refs/heads/main")

            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#repositoryCloneButton").wait_for(state="visible")
                page.locator("#repositoryCloneButton").click()
                page.locator("#repositoryUrlInput").fill(str(remote))
                page.locator("#repositoryNameInput").fill("algorithm-package")
                page.locator("#repositoryCloneStartButton").click()
                wait_for_text(page, "#repositoryStatus", "algorithm-package", timeout=30_000)
                wait_for_text(page, "#gitStatus", "algorithm-package", timeout=30_000)

                repository = workspace / "problems" / "algorithm-package"
                git(repository, "config", "user.email", "studio@example.com")
                git(repository, "config", "user.name", "Problem Studio")
                git(repository, "checkout", "-b", "feature/repository-ui")

                create_studio_problem(page, "delta", "Delta Repo")
                wait_for_text(page, "#gitStatus", "커밋되지 않은 변경")
                page.locator("#gitCommitMessage").fill("Add delta")
                page.locator("#gitCommitButton").click()
                wait_for_text(page, "#gitStatus", "clean", timeout=30_000)
                page.locator("#gitPushButton").click()
                wait_for_text(page, "#gitStatus", "origin/feature/repository-ui", timeout=30_000)
                wait_for_text(page, "#problemTitle", "Delta Repo", timeout=30_000)
                wait_for_text(page, "#problemList", "Delta Repo", timeout=30_000)

                refs = git(remote, "for-each-ref", "--format=%(refname:short)", "refs/heads")
                self.assertIn("feature/repository-ui", refs.splitlines())
                self.assertTrue((repository / "problems" / "delta" / "problem.json").exists())
                self.assert_no_browser_errors()

    def test_repository_selector_scopes_problem_list_in_browser(self) -> None:
        with isolated_runtime("alj-problem-studio-repository-switch-e2e-") as (_directory, root):
            workspace = root / "studio"
            repo_a = workspace / "problems" / "repo-a"
            repo_b = workspace / "problems" / "repo-b"
            create_problem_template(repo_a, "01", "Repo A One")
            create_problem_template(repo_b, "01", "Repo B One")
            git(repo_a, "init")
            git(repo_b, "init")

            with run_app(create_app(workspace)) as server:
                page = self.new_page(server.url)
                page.goto(server.url)
                page.locator("#repositorySelect").wait_for(state="visible")
                page.locator("#repositoryRefreshButton").click()
                page.locator("#repositoryCloneButton").click()
                page.locator("#repositoryNameInput").fill("repo-a")
                page.locator("#repositoryRegisterButton").click()
                wait_for_text(page, "#problemTitle", "Repo A One")
                wait_for_text(page, "#workspaceLabel", "repo-a")
                page.locator("#repositorySelect").select_option("repo-b")
                wait_for_text(page, "#problemTitle", "Repo B One")
                wait_for_text(page, "#workspaceLabel", "repo-b")
                self.assert_no_browser_errors()
