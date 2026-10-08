from app.models import GitHubStatus


class GitHubError(Exception):
    """A GitHub API problem. ``detail`` is short and never contains tokens or response bodies."""

    def __init__(self, status: GitHubStatus, detail: str = "") -> None:
        super().__init__(f"{status.value}: {detail}" if detail else status.value)
        self.status = status
        self.detail = detail
