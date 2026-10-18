"""Tests for sandbox PR manager."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from animus_kernel.sandbox.pr_manager import PRManager, PRStatus, PullRequest

# ═══════════════════════════════════════════════════════════════════
# PRManager tests (with temp git repos)
# ═══════════════════════════════════════════════════════════════════


def _init_git_repo(path: Path) -> None:
    """Initialize a minimal git repo for testing."""
    subprocess.run(
        ["git", "init", "--initial-branch=main"], cwd=str(path), capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(path),
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(path),
        capture_output=True,
        check=True,
    )
    (path / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=str(path), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(path),
        capture_output=True,
        check=True,
    )


class TestPRManager:
    def test_create_branch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)

            manager = PRManager(repo, default_branch="main")
            branch = manager.create_branch("test-123")
            assert branch == "animus-kernel-self-improve/test-123"
            assert manager.get_current_branch() == branch

    def test_commit_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)

            manager = PRManager(repo, default_branch="main")
            manager.create_branch("commit-test")

            (repo / "new.py").write_text("print('hello')")
            commit_hash = manager.commit_changes(["new.py"], "add new file")

            assert commit_hash is not None
            assert len(commit_hash) == 40
            assert not manager.has_uncommitted_changes()

    def test_has_uncommitted_changes_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)

            manager = PRManager(repo, default_branch="main")
            manager.create_branch("changes-test")

            (repo / "uncommitted.py").write_text("x")
            assert manager.has_uncommitted_changes() is True

    def test_create_pr_without_gh(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)

            manager = PRManager(repo, default_branch="main")
            branch = manager.create_branch("pr-test")

            pr = manager.create_pr(
                branch=branch,
                title="Test PR",
                description="A test PR",
                files_changed=["main.py"],
                draft=True,
            )

            assert isinstance(pr, PullRequest)
            assert pr.title == "Test PR"
            assert pr.status == PRStatus.DRAFT
            assert pr.branch == branch
            assert pr.url is None  # gh CLI not available in test
            assert len(pr.id) == 8

    def test_get_pr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)

            manager = PRManager(repo, default_branch="main")
            branch = manager.create_branch("pr-get-test")
            pr = manager.create_pr(
                branch=branch, title="T", description="D", files_changed=["a.py"]
            )

            fetched = manager.get_pr(pr.id)
            assert fetched is not None
            assert fetched.title == "T"

    def test_checkout_main(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)

            manager = PRManager(repo, default_branch="main")
            manager.create_branch("feature")
            assert manager.get_current_branch() == "animus-kernel-self-improve/feature"

            result = manager.checkout_main()
            assert result is True
            assert manager.get_current_branch() == "main"

    def test_delete_branch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)

            manager = PRManager(repo, default_branch="main")
            branch = manager.create_branch("to-delete")

            # Must checkout another branch before deleting current
            manager.checkout_main()
            result = manager.delete_branch(branch, force=True)
            assert result is True

            branches = subprocess.run(
                ["git", "branch", "-a"],
                cwd=str(repo),
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            assert "to-delete" not in branches

    def test_check_conflicts_no_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)

            manager = PRManager(repo, default_branch="main")
            branch = manager.create_branch("no-conflict")
            (repo / "new.py").write_text("x")
            subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "add"],
                cwd=str(repo),
                capture_output=True,
                check=True,
            )
            manager.checkout_main()

            conflict = manager.check_conflicts(branch)
            assert conflict.has_conflicts is False

    def test_check_conflicts_with_conflict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)
            (repo / "shared.py").write_text("original")
            subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "add shared"],
                cwd=str(repo),
                capture_output=True,
                check=True,
            )

            manager = PRManager(repo, default_branch="main")

            branch = manager.create_branch("conflict-branch")
            (repo / "shared.py").write_text("branch-change")
            subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "branch commit"],
                cwd=str(repo),
                capture_output=True,
                check=True,
            )

            manager.checkout_main()
            (repo / "shared.py").write_text("main-change")
            subprocess.run(["git", "add", "."], cwd=str(repo), capture_output=True, check=True)
            subprocess.run(
                ["git", "commit", "-m", "main commit"],
                cwd=str(repo),
                capture_output=True,
                check=True,
            )

            conflict = manager.check_conflicts(branch)
            assert conflict.has_conflicts is True
            assert "shared.py" in conflict.conflicting_files

    def test_close_pr_without_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            _init_git_repo(repo)

            manager = PRManager(repo, default_branch="main")
            branch = manager.create_branch("close-test")
            pr = manager.create_pr(
                branch=branch, title="T", description="D", files_changed=["a.py"]
            )

            result = manager.close_pr(pr.id, reason="abandoned")
            assert result is True
            closed = manager.get_pr(pr.id)
            assert closed.status == PRStatus.CLOSED


# ═══════════════════════════════════════════════════════════════════
# PullRequest dataclass tests
# ═══════════════════════════════════════════════════════════════════


class TestPullRequest:
    def test_default_status_is_draft(self):
        pr = PullRequest(id="abc", branch="feat", title="T", description="D")
        assert pr.status == PRStatus.DRAFT
        assert pr.url is None

    def test_custom_values(self):
        pr = PullRequest(
            id="abc",
            branch="feat",
            title="T",
            description="D",
            status=PRStatus.MERGED,
            url="https://github.com/...",
        )
        assert pr.status == PRStatus.MERGED
        assert pr.url == "https://github.com/..."
