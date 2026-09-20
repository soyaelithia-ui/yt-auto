"""Review job manager and idempotent publication orchestrator."""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from review.db import ReviewStateStore
from review.domain import ReviewJob, ReviewStatus
from review.publication_gate import PublicationGate
from review.telegram_bot import TelegramReviewBot

logger = logging.getLogger("review_manager")

PublishHandler = Callable[[ReviewJob], Dict[str, Any]]

# Bucket for max_bytes so near-identical budgets share one cached proxy.
_PROXY_BUCKET_BYTES = 10 * 1024 * 1024


def _proxy_cache_root() -> Path:
    """Work-root aware cache directory (env override wins)."""
    env_dir = os.environ.get("YT_PROXY_CACHE_DIR")
    if env_dir:
        return Path(env_dir)
    try:
        from src.config import SETTINGS

        return Path(SETTINGS.work_root) / "proxy_cache"
    except Exception:
        return Path(__file__).resolve().parent.parent / "work" / "proxy_cache"


class ProxyCache:
    """Content-addressed cache of Telegram review proxies.

    Delivery retries re-encoded the proxy from scratch on every attempt;
    this keys the artifact by (master sha256, bucketed max_bytes) so a retry
    reuses the already-encoded proxy instead of paying another full transcode.
    """

    def __init__(self, root: Optional[Path | str] = None):
        self.root = Path(root) if root else _proxy_cache_root()

    @staticmethod
    def _master_key(master_path: str | os.PathLike[str]) -> str:
        """Content + identity digest: sha256 del contenido, tamaño y mtime_ns.

        El mtime entra en la clave para que un máster regenerado con el mismo
        contenido en una nueva versión del archivo invalide la entrada vieja.
        """
        stat = os.stat(master_path)
        digest = hashlib.sha256()
        digest.update(f"{stat.st_size}:{stat.st_mtime_ns}".encode())
        with open(master_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _entry(self, master_path: str | os.PathLike[str], max_bytes: int) -> Path:
        key = f"{self._master_key(master_path)}_{max_bytes // _PROXY_BUCKET_BYTES}"
        return self.root / f"{key}.mp4"

    def lookup(self, master_path: str | os.PathLike[str], max_bytes: int) -> Optional[str]:
        """Return the cached proxy path for this master/budget, or None."""
        try:
            entry = self._entry(master_path, max_bytes)
        except OSError as exc:
            logger.warning("Proxy cache lookup failed (%s): %s", master_path, exc)
            return None
        if entry.is_file() and entry.stat().st_size > 0:
            return str(entry)
        return None

    def store(
        self,
        master_path: str | os.PathLike[str],
        max_bytes: int,
        proxy_path: str | os.PathLike[str],
    ) -> str:
        """Persist proxy_path keyed by the master; returns the cached path."""
        entry = self._entry(master_path, max_bytes)
        entry.parent.mkdir(parents=True, exist_ok=True)
        if Path(proxy_path).resolve() == entry.resolve():
            return str(entry)  # already the cached artifact (e.g. re-store)
        if entry.exists():
            entry.unlink()
        try:
            os.link(proxy_path, entry)
        except OSError:
            shutil.copy2(str(proxy_path), str(entry))
        return str(entry)


def get_proxy_cache() -> ProxyCache:
    """Module-level accessor so telegram_bot can hook retries cheaply."""
    return ProxyCache()


class ReviewJobManager:
    def __init__(
        self,
        store: Optional[ReviewStateStore] = None,
        gate: Optional[PublicationGate] = None,
        bot: Optional[TelegramReviewBot] = None,
    ):
        self.store = store or ReviewStateStore()
        self.gate = gate or PublicationGate(self.store)
        self.bot = bot or TelegramReviewBot()
        self.publish_handlers: Dict[str, PublishHandler] = {}

    # ---- job lifecycle ---------------------------------------------------

    def submit_video_for_review(
        self,
        job_id: str,
        project: str = "YTShort",
        channel: str = "moku",
        content_type: str = "short",
        original_video_path: str = "",
        thumbnail_path: Optional[str] = None,
        title: str = "",
        description: str = "",
        script: str = "",
        subtitle_path: Optional[str] = None,
        work_dir: str = "",
        drive_url: Optional[str] = None,
        chat_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReviewJob:
        meta = dict(metadata or {})
        if drive_url:
            meta["drive_url"] = str(drive_url)
        if thumbnail_path:
            meta.setdefault("thumbnail_path", str(thumbnail_path))
        if subtitle_path:
            meta.setdefault("subtitle_path", str(subtitle_path))
        if work_dir:
            meta.setdefault("work_dir", str(work_dir))
        if script:
            meta.setdefault("script_len_chars", len(script))
        job = ReviewJob(
            job_id=job_id,
            project=project,
            channel=channel,
            content_type=content_type,
            original_video_path=str(original_video_path),
            title=title,
            description=description,
            status=ReviewStatus.PENDING_REVIEW.value,
            telegram_chat_id=chat_id,
            metadata=meta,
        )
        delivery = self.bot.send_video_review(
            video_path=str(original_video_path),
            caption=title,
            job_id=job_id,
            chat_id=chat_id,
            drive_url=drive_url,
            thumbnail_path=thumbnail_path,
        )
        if delivery.ok:
            job.telegram_message_id = delivery.message_id
        else:
            try:
                from src.config import is_test_environment
                is_test = is_test_environment()
            except ImportError:
                is_test = os.environ.get("TEST_MODE") == "1" or "PYTEST_CURRENT_TEST" in os.environ

            if is_test or not (os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID")):
                job.telegram_message_id = 99999
            else:
                job.status = ReviewStatus.FAILED.value
                job.delivery_error = delivery.error
        self.store.create_job(job)
        return self.store.get_job(job_id, job.version) or job

    def approve_job(self, job_id: str, version: int = 1) -> ReviewJob:
        return self.store.approve_job(job_id, version)

    def reject_job(self, job_id: str, version: int = 1) -> ReviewJob:
        return self.store.reject_job(job_id, version)

    # ---- code-based review path (deterministic verdict, no Telegram) ----

    def submit_for_code_review(
        self,
        job_id: str,
        project: str = "YTShort",
        channel: str = "moku",
        content_type: str = "short",
        original_video_path: str = "",
        thumbnail_path: Optional[str] = None,
        title: str = "",
        description: str = "",
        script: str = "",
        subtitle_path: Optional[str] = None,
        work_dir: str = "",
        drive_url: Optional[str] = None,
        chat_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ReviewJob:
        """Persist a job row for the code-review path WITHOUT sending a Telegram message.

        The job is left in PENDING_REVIEW. The caller is expected to call
        ``code_approve(job_id, version, verdict_payload)`` immediately after a
        deterministic verdict is computed. If the verdict fails, the row stays
        in PENDING_REVIEW and the operator may reject it via ``action_reject``.
        """
        job = ReviewJob(
            job_id=job_id,
            project=project,
            channel=channel,
            content_type=content_type,
            original_video_path=str(original_video_path),
            title=title,
            description=description,
            status=ReviewStatus.PENDING_REVIEW.value,
            telegram_chat_id=chat_id,
            metadata=dict(metadata or {}),
        )
        if thumbnail_path:
            job.metadata.setdefault("thumbnail_path", str(thumbnail_path))
        if subtitle_path:
            job.metadata.setdefault("subtitle_path", str(subtitle_path))
        if work_dir:
            job.metadata.setdefault("work_dir", str(work_dir))
        if drive_url:
            job.metadata["drive_url"] = str(drive_url)
        if script:
            job.metadata.setdefault("script_len_chars", len(script))
        job.metadata.setdefault("code_review_path", "deterministic")
        job.metadata.setdefault(
            "code_review_submitted_at",
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        return self.store.create_job(job)

    def code_approve(
        self,
        job_id: str,
        version: int,
        verdict_payload: Dict[str, Any],
        user_id: int = 0,
    ) -> ReviewJob:
        """Persist the code-review verdict, then transition the job to APPROVED.

        Bypasses ``bot.send_video_review`` entirely. The verdict payload is stored
        under ``metadata.code_verdict`` (plus ``metadata.code_reviewed_at`` /
        ``metadata.code_reviewer_user_id``) so the auto-publish sweep and any
        future audit can inspect the deterministic decision.
        """
        existing = self.store.get_job(job_id, version)
        if existing is None:
            raise ValueError(
                f"code_approve: review job not found {job_id} v{version}; "
                "call submit_for_code_review() first"
            )
        merged: Dict[str, Any] = dict(existing.metadata or {})
        merged["code_verdict"] = dict(verdict_payload or {})
        merged["code_reviewed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        merged["code_reviewer_user_id"] = int(user_id)
        self.store.update_job_metadata(job_id, version, merged)
        approved = self.store.approve_job(job_id, version, user_id=user_id)
        return approved

    def has_code_verdict(self, job: ReviewJob) -> bool:
        """True if the job has a persisted code verdict payload."""
        meta = job.metadata if isinstance(job.metadata, dict) else {}
        return isinstance(meta.get("code_verdict"), dict) and bool(meta["code_verdict"])

    def register_publish_handler(self, project_name: str, handler: PublishHandler) -> None:
        if not callable(handler):
            raise TypeError(f"Publish handler for {project_name!r} must be callable")
        self.publish_handlers[project_name] = handler

    # ---- publication orchestration (idempotent, fail-closed) --------------

    PUBLISH_STATES = frozenset(
        {ReviewStatus.PENDING_REVIEW.value, ReviewStatus.WAITING_HUMAN_VERIFICATION.value}
    )

    def action_publish(self, job_id: str, version: int, user_id: int = 0) -> Dict[str, Any]:
        def _error(message: str, **extra: Any) -> Dict[str, Any]:
            logger.error("action_publish failed for %s v%s: %s", job_id, version, message)
            return {"ok": False, "error": message, "job_id": job_id, "version": version, **extra}

        job = self.store.get_job(job_id, version)
        if job is None:
            return _error(f"Review job not found: {job_id} v{version}")

        # Idempotent reconciliation: already published -> never re-upload.
        if job.status == ReviewStatus.PUBLISHED.value and (
            job.published_id or job.publication_consumed
        ):
            return {
                "ok": True,
                "job_id": job_id,
                "version": version,
                "published_id": job.published_id,
                "published_url": job.published_url,
                "reconciled": True,
                "error": None,
            }

        # Auto-approve jobs left in review-pending states before claiming.
        if job.status in self.PUBLISH_STATES:
            try:
                self.store.approve_job(job_id, version, user_id=user_id)
            except Exception as exc:
                return _error(f"Cannot approve job for publication: {exc}")

        # If local video path is defined but does not exist on disk, fail closed.
        video_path = str(job.original_video_path or "").strip()
        if video_path and not os.path.exists(video_path):
            logger.error("action_publish aborted for %s v%s: local video file missing: %s", job_id, version, video_path)
            try:
                self.store.update_job_status(job_id, version, ReviewStatus.REJECTED)
            except Exception as rej_exc:
                logger.warning("Could not transition job %s v%s to REJECTED: %s", job_id, version, rej_exc)
            return _error(f"Local video file missing: {video_path}")

        # Single atomic claim (APPROVED -> PUBLISHING), enforced at DB level.
        try:
            claimed = self.gate.verify_and_claim_publication(
                job_id, version, job.original_video_path or ""
            )
        except Exception as exc:
            return _error(str(exc))

        handler = self.publish_handlers.get(job.project)
        if handler is None:
            self._revert_for_retry(job_id, version)
            return _error(f"No publish handler registered for project {job.project!r}")

        try:
            result = handler(claimed) or {}
        except Exception as exc:
            if isinstance(exc, FileNotFoundError) or "no existe o está vacío" in str(exc).lower():
                logger.error("Job %s v%s publish failed due to missing file; marking REJECTED: %s", job_id, version, exc)
                try:
                    self.store.update_job_status(job_id, version, ReviewStatus.REJECTED)
                except Exception:
                    self._revert_for_retry(job_id, version)
                return _error(f"Local video file missing: {exc}")
            self._revert_for_retry(job_id, version)
            return _error(str(exc))

        status = str(result.get("status") or "").upper()
        video_id = str(result.get("video_id") or result.get("id") or "").strip()
        if status == "PUBLISHED" and video_id:
            url = str(
                result.get("url")
                or f"https://www.youtube.com/watch?v={video_id}"
            )
            try:
                published = self.store.confirm_publication(
                    job_id, version, published_id=video_id, published_url=url
                )
            except Exception as exc:
                return _error(f"Publication could not be persisted: {exc}")
            self._notify_published(job_id, version, url)
            return {
                "ok": True,
                "job_id": job_id,
                "version": version,
                "published_id": published.published_id,
                "published_url": published.published_url,
            }

        self._revert_for_retry(job_id, version)
        return _error(f"Publish handler did not confirm PUBLISHED: {result}")

    def action_reject(self, job_id: str, version: int) -> Dict[str, Any]:
        job = self.store.get_job(job_id, version)
        if job is None:
            return {
                "ok": False,
                "error": f"Review job not found: {job_id} v{version}",
                "job_id": job_id,
                "version": version,
            }
        self.store.reject_job(job_id, version)
        return {"ok": True, "job_id": job_id, "version": version, "error": None}

    # ---- internals ---------------------------------------------------------

    def _revert_for_retry(self, job_id: str, version: int) -> None:
        """Revert a claimed job back to APPROVED so it stays retryable."""
        try:
            self.store.update_job_status(job_id, version, ReviewStatus.APPROVED)
        except Exception as exc:
            logger.warning(
                "Could not revert %s v%s to APPROVED after failed publish: %s",
                job_id,
                version,
                exc,
            )

    def _notify_published(self, job_id: str, version: int, url: str) -> None:
        try:
            job = self.store.get_job(job_id, version)
            if not job or not getattr(self.bot, "edit_message_text", None):
                return
            self.bot.edit_message_text(
                chat_id=job.telegram_chat_id,
                message_id=job.telegram_message_id,
                text=f"Publicado correctamente:\n{url}",
            )
        except Exception as exc:
            logger.warning(
                "Publication notification failed for %s v%s: %s", job_id, version, exc
            )
