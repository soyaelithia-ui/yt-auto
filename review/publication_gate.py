"""Publication gate enforcement with atomic single-time claim."""
from __future__ import annotations

from typing import Optional, Union

from review.db import ReviewStateStore
from review.domain import ReviewJob, ReviewStatus


class PublicationGate:
    def __init__(self, store_or_db_path: Optional[Union[ReviewStateStore, str]] = None):
        if isinstance(store_or_db_path, ReviewStateStore) or hasattr(store_or_db_path, "get_job"):
            self.store = store_or_db_path
        elif store_or_db_path:
            self.store = ReviewStateStore(db_path=str(store_or_db_path))
        else:
            self.store = ReviewStateStore()

    @property
    def db_path(self) -> str:
        return self.store.db_path

    def is_approved_for_publication(
        self, job_id: str, version: int = 1
    ) -> bool:
        if self.store is None:
            return False
        job = self.store.get_job(job_id, version) if hasattr(self.store, "get_job") else None
        if not job:
            return False
        return job.status in (
            ReviewStatus.APPROVED.value,
            ReviewStatus.WAITING_HUMAN_VERIFICATION.value,
        )

    def verify_and_claim_publication(
        self, job_id: str, version: int, video_path: str = ""
    ) -> ReviewJob:
        """Atomically claim an APPROVED job for publication (APPROVED -> PUBLISHING)."""
        return self.store.claim_for_publication(job_id, version, video_path)

    def confirm_publication_success(
        self,
        job_id: str,
        version: int,
        published_id: Optional[str] = None,
        published_url: Optional[str] = None,
    ) -> ReviewJob:
        """Persist a verified publication and mark the job PUBLISHED (PUBLISHING -> PUBLISHED)."""
        return self.store.confirm_publication(
            job_id, version, published_id=str(published_id or ""), published_url=str(published_url or "")
        )