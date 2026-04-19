"""GitHub REST API client using httpx.

Provides async methods for all GitHub operations needed by GitOps:
- User info / token validation
- Repository listing and search
- Branch management
- File upload via Contents API
- Pull request creation
"""

import base64

import httpx

from agent_compiler.observability.logging import get_logger

logger = get_logger(__name__)


class GitHubApiError(Exception):
    """Raised when a GitHub API call fails."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        super().__init__(message)


class GitHubClient:
    """Async GitHub REST API client."""

    def __init__(self, token: str):
        self.client = httpx.AsyncClient(
            base_url="https://api.github.com",
            headers={
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def _request(self, method: str, url: str, **kwargs) -> dict | list:
        response = await self.client.request(method, url, **kwargs)
        if response.status_code >= 400:
            try:
                body = response.json()
                msg = body.get("message", response.text)
            except Exception:
                msg = response.text
            raise GitHubApiError(response.status_code, msg)
        if response.status_code == 204:
            return {}
        return response.json()

    # ── User ──────────────────────────────────────────────────────────

    async def get_user(self) -> dict:
        """GET /user — validate token and get user info."""
        return await self._request("GET", "/user")

    # ── Repositories ──────────────────────────────────────────────────

    async def list_repos(
        self,
        query: str | None = None,
        page: int = 1,
        per_page: int = 30,
    ) -> list:
        """List repos for the authenticated user, optionally filtered."""
        if query:
            # Use search API for query filtering
            result = await self._request(
                "GET",
                "/search/repositories",
                params={
                    "q": f"{query} user:@me fork:true",
                    "sort": "updated",
                    "per_page": per_page,
                    "page": page,
                },
            )
            return result.get("items", [])
        else:
            return await self._request(
                "GET",
                "/user/repos",
                params={
                    "sort": "updated",
                    "per_page": per_page,
                    "page": page,
                    "affiliation": "owner,collaborator,organization_member",
                },
            )

    # ── Branches ──────────────────────────────────────────────────────

    async def list_branches(
        self, owner: str, repo: str, per_page: int = 100
    ) -> list:
        """GET /repos/{owner}/{repo}/branches"""
        return await self._request(
            "GET",
            f"/repos/{owner}/{repo}/branches",
            params={"per_page": per_page},
        )

    async def get_ref(self, owner: str, repo: str, ref: str) -> dict:
        """GET /repos/{owner}/{repo}/git/refs/heads/{ref}"""
        return await self._request(
            "GET", f"/repos/{owner}/{repo}/git/refs/heads/{ref}"
        )

    async def create_ref(
        self, owner: str, repo: str, ref: str, sha: str
    ) -> dict:
        """POST /repos/{owner}/{repo}/git/refs — create a branch."""
        return await self._request(
            "POST",
            f"/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/heads/{ref}", "sha": sha},
        )

    # ── File operations ───────────────────────────────────────────────

    async def get_contents(
        self, owner: str, repo: str, path: str, ref: str | None = None
    ) -> dict | list:
        """GET /repos/{owner}/{repo}/contents/{path} — get file SHA for updates."""
        params = {}
        if ref:
            params["ref"] = ref
        return await self._request(
            "GET", f"/repos/{owner}/{repo}/contents/{path}", params=params
        )

    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content_b64: str,
        message: str,
        branch: str,
        sha: str | None = None,
    ) -> dict:
        """PUT /repos/{owner}/{repo}/contents/{path} — create or update a file."""
        body: dict = {
            "message": message,
            "content": content_b64,
            "branch": branch,
        }
        if sha:
            body["sha"] = sha
        return await self._request(
            "PUT", f"/repos/{owner}/{repo}/contents/{path}", json=body
        )

    # ── Pull Requests ─────────────────────────────────────────────────

    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict:
        """POST /repos/{owner}/{repo}/pulls"""
        return await self._request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            json={
                "title": title,
                "body": body,
                "head": head,
                "base": base,
            },
        )

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def file_to_b64(content: bytes) -> str:
        """Encode file content as base64 string for the Contents API."""
        return base64.b64encode(content).decode("ascii")
