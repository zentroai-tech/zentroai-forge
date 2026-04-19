"""GitOps service for creating GitHub PRs via the REST API.

Replaces the previous git-CLI approach with httpx-based GitHub API calls.
Jobs are tracked in the gitops_jobs table for async polling.
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from agent_compiler.observability.logging import get_logger
from agent_compiler.services.github_client import GitHubClient, GitHubApiError

logger = get_logger(__name__)


class GitOpsError(Exception):
    """Raised when a GitOps operation fails."""

    pass


class GitOpsService:
    """Orchestrates GitHub PR creation as background jobs."""

    def __init__(self, engine: AsyncEngine):
        self.engine = engine

    async def create_job(
        self,
        export_id: str,
        repo: str,
        base_branch: str,
        branch_name: str,
        pr_title: str | None = None,
        pr_body: str | None = None,
    ) -> str:
        """Insert a new gitops_jobs row and return the job ID."""
        job_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        async with self.engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO gitops_jobs
                        (id, export_id, status, repo, base_branch, branch_name,
                         pr_title, pr_body, files_total, files_uploaded,
                         logs_json, created_at, updated_at)
                    VALUES
                        (:id, :export_id, 'pending', :repo, :base_branch, :branch_name,
                         :pr_title, :pr_body, 0, 0, '[]', :now, :now)
                """),
                {
                    "id": job_id,
                    "export_id": export_id,
                    "repo": repo,
                    "base_branch": base_branch,
                    "branch_name": branch_name,
                    "pr_title": pr_title,
                    "pr_body": pr_body,
                    "now": now,
                },
            )
        return job_id

    async def get_job(self, job_id: str) -> dict | None:
        """Fetch a job row as a dict."""
        async with self.engine.begin() as conn:
            result = await conn.execute(
                text("SELECT * FROM gitops_jobs WHERE id = :id"),
                {"id": job_id},
            )
            row = result.mappings().first()
            if not row:
                return None
            import json

            data = dict(row)
            data["logs"] = json.loads(data.get("logs_json") or "[]")
            data["job_id"] = data.pop("id")
            data.pop("logs_json", None)
            return data

    async def _update_job(self, job_id: str, **fields) -> None:
        """Update arbitrary fields on a job row."""
        import json

        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        set_clauses = ", ".join(f"{k} = :{k}" for k in fields)

        # Serialize logs list to JSON if present
        if "logs" in fields:
            fields["logs_json"] = json.dumps(fields.pop("logs"))
            set_clauses = set_clauses.replace("logs = :logs", "logs_json = :logs_json")

        async with self.engine.begin() as conn:
            await conn.execute(
                text(f"UPDATE gitops_jobs SET {set_clauses} WHERE id = :job_id"),
                {"job_id": job_id, **fields},
            )

    async def _append_log(self, job_id: str, message: str) -> None:
        """Append a log line to the job."""
        import json

        async with self.engine.begin() as conn:
            result = await conn.execute(
                text("SELECT logs_json FROM gitops_jobs WHERE id = :id"),
                {"id": job_id},
            )
            row = result.fetchone()
            logs = json.loads(row[0]) if row and row[0] else []
            logs.append(message)
            await conn.execute(
                text(
                    "UPDATE gitops_jobs SET logs_json = :logs, updated_at = :now WHERE id = :id"
                ),
                {
                    "id": job_id,
                    "logs": json.dumps(logs),
                    "now": datetime.now(timezone.utc).isoformat(),
                },
            )

    async def execute_job(
        self, job_id: str, export_dir: str, token: str, dry_run: bool = False
    ) -> None:
        """Main orchestration — runs as a background task.

        1. Update status to running
        2. Get base branch SHA
        3. Create new branch
        4. Upload each file via Contents API
        5. Create PR
        6. Mark success
        """
        client = GitHubClient(token)

        try:
            # Mark running
            await self._update_job(job_id, status="running")
            await self._append_log(job_id, "Job started")

            # Parse owner/repo
            job = await self.get_job(job_id)
            if not job:
                return
            repo_full = job["repo"]
            owner, repo = repo_full.split("/", 1)
            base_branch = job["base_branch"]
            branch_name = job["branch_name"]
            pr_title = job.get("pr_title") or f"Agent export to {branch_name}"
            pr_body = job.get("pr_body") or ""

            # Collect files
            export_path = Path(export_dir)
            if not export_path.exists():
                raise GitOpsError(f"Export directory not found: {export_dir}")

            files: list[tuple[str, bytes]] = []
            for file_path in sorted(export_path.rglob("*")):
                if file_path.is_file():
                    rel = file_path.relative_to(export_path).as_posix()
                    files.append((rel, file_path.read_bytes()))

            await self._update_job(job_id, files_total=len(files))
            await self._append_log(job_id, f"Found {len(files)} files to upload")

            if dry_run:
                await self._append_log(job_id, "Dry run — skipping GitHub operations")
                await self._update_job(job_id, status="success")
                return

            # Get base branch SHA
            await self._append_log(job_id, f"Getting base branch '{base_branch}'")
            ref_data = await client.get_ref(owner, repo, base_branch)
            base_sha = ref_data["object"]["sha"]

            # Create branch
            await self._append_log(job_id, f"Creating branch '{branch_name}'")
            try:
                await client.create_ref(owner, repo, branch_name, base_sha)
            except GitHubApiError as e:
                if e.status_code == 422 and "Reference already exists" in str(e):
                    await self._append_log(
                        job_id, f"Branch '{branch_name}' already exists, reusing"
                    )
                else:
                    raise

            # Upload files
            last_commit_sha = None
            for i, (rel_path, content) in enumerate(files, 1):
                await self._append_log(
                    job_id, f"Uploading ({i}/{len(files)}): {rel_path}"
                )

                content_b64 = GitHubClient.file_to_b64(content)

                # Check if file already exists (to get its SHA for update)
                existing_sha = None
                try:
                    existing = await client.get_contents(
                        owner, repo, rel_path, ref=branch_name
                    )
                    if isinstance(existing, dict):
                        existing_sha = existing.get("sha")
                except GitHubApiError:
                    pass  # File doesn't exist yet

                result = await client.create_or_update_file(
                    owner=owner,
                    repo=repo,
                    path=rel_path,
                    content_b64=content_b64,
                    message=f"Add {rel_path}",
                    branch=branch_name,
                    sha=existing_sha,
                )
                last_commit_sha = (
                    result.get("commit", {}).get("sha") or last_commit_sha
                )
                await self._update_job(job_id, files_uploaded=i)

            # Create PR
            await self._append_log(job_id, "Creating pull request")
            pr = await client.create_pull_request(
                owner=owner,
                repo=repo,
                title=pr_title,
                body=pr_body,
                head=branch_name,
                base=base_branch,
            )

            pr_url = pr.get("html_url", "")
            pr_number = pr.get("number")
            await self._append_log(job_id, f"Pull request #{pr_number} created")

            await self._update_job(
                job_id,
                status="success",
                pr_url=pr_url,
                pr_number=pr_number,
                commit_sha=last_commit_sha,
            )

        except GitHubApiError as e:
            error_msg = f"GitHub API error ({e.status_code}): {e}"
            logger.error(f"GitOps job {job_id} failed: {error_msg}")
            await self._append_log(job_id, error_msg)
            await self._update_job(
                job_id, status="failed", error_message=str(e)[:500]
            )
        except Exception as e:
            error_msg = str(e)[:500]
            logger.error(f"GitOps job {job_id} failed: {error_msg}")
            await self._append_log(job_id, f"Error: {error_msg}")
            await self._update_job(
                job_id, status="failed", error_message=error_msg
            )
        finally:
            await client.close()
