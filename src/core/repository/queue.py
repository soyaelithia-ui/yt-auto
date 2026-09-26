"""Story management, queue states, claims, deduplication, and production telemetry."""

from __future__ import annotations

import functools
import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Mapping, Sequence

from src.core.domain import (
    ALL_STATUSES,
    CHANNEL_ALIASES,
    CanonicalChannel,
    JobStatus,
    PublicationProof,
    canonical_channel,
)
from src.core.repository.migrations import _utc_now, connect

if TYPE_CHECKING:
    from src.core.contracts.story import StoryRecord


def to_signed_64(val: int | None) -> int | None:
    if val is None:
        return None
    val = int(val) & 0xFFFFFFFFFFFFFFFF
    return val if val < (1 << 63) else val - (1 << 64)


def to_unsigned_64(val: int | None) -> int:
    if val is None:
        return 0
    return int(val) & 0xFFFFFFFFFFFFFFFF


@functools.lru_cache(maxsize=2048)
def compute_simhash_64(text: str | None) -> int:
    """Compute a 64-bit SimHash over normalized text with word weights and bigrams."""
    if not text:
        return 0
    tokens = re.findall(r"\w+", text.lower(), re.UNICODE)
    if not tokens:
        return 0

    features: list[str] = []
    for token in tokens:
        weight = min(len(token), 4)
        features.extend([token] * weight)
    if len(tokens) >= 2:
        for i in range(len(tokens) - 1):
            features.append(f"{tokens[i]}_{tokens[i+1]}")

    v = [0] * 64
    for feature in features:
        h = int.from_bytes(hashlib.md5(feature.encode("utf-8")).digest()[:8], "big")
        for i in range(64):
            if (h >> i) & 1:
                v[i] += 1
            else:
                v[i] -= 1

    fingerprint = 0
    for i in range(64):
        if v[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def simhash_hamming_distance(h1: int | None, h2: int | None) -> int:
    """Compute Hamming distance (differing bits) between two 64-bit integers."""
    return (to_unsigned_64(h1) ^ to_unsigned_64(h2)).bit_count()


hamming_distance_64 = simhash_hamming_distance


def is_simhash_duplicate(h1: int | None, h2: int | None, max_distance: int = 3) -> bool:
    """Return True if Hamming distance <= max_distance (default 3 bits)."""
    return simhash_hamming_distance(h1, h2) <= max_distance


def re_full_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


class QueueOperationsMixin:
    """Operations related to queue stories, claims, state transitions, deduplication and metrics."""

    db_path: str

    def _execute_write(self, sql: str, params: Sequence[Any] = ()) -> None:
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(sql, params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def _fetch_all(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        with connect(self.db_path, read_only=True) as conn:
            return [dict(row) for row in conn.execute(sql, params)]

    def _fetch_one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        with connect(self.db_path, read_only=True) as conn:
            row = conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def enqueue(
        self,
        story_id: str,
        title: str,
        content: str,
        url: str,
        channel: str | CanonicalChannel,
        *,
        score: int = 0,
        upvote_ratio: float = 0.0,
        num_comments: int = 0,
        lane_id: str | None = None,
        source_license: str | None = None,
    ) -> bool:
        channel_key = canonical_channel(channel).value
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    "INSERT INTO stories("
                    "story_id, title, content, url, status, channel, "
                    "score, upvote_ratio, num_comments, lane_id, source_license"
                    ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        story_id,
                        title,
                        content,
                        url,
                        JobStatus.PENDING.value,
                        channel_key,
                        int(score),
                        float(upvote_ratio),
                        int(num_comments),
                        lane_id,
                        source_license,
                    ),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                conn.rollback()
                return False

    def claim(
        self,
        channel: str | CanonicalChannel,
        owner: str,
        *,
        lease_seconds: int = 900,
        mode: str = "publish",
        now: int | None = None,
    ) -> dict[str, Any] | None:
        channel_key = canonical_channel(channel).value
        if not owner.strip():
            raise ValueError("El propietario del lease es obligatorio")
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            paused = conn.execute(
                "SELECT paused FROM channel_controls WHERE channel = ?", (channel_key,)
            ).fetchone()
            if paused and paused["paused"]:
                conn.rollback()
                return None
            getattr(self, "_recover_expired_locked")(conn, current)
            if conn.execute(
                "SELECT 1 FROM leases WHERE channel = ?", (channel_key,)
            ).fetchone() or conn.execute(
                "SELECT 1 FROM lane_leases WHERE channel = ?", (channel_key,)
            ).fetchone():
                conn.rollback()
                return None
            order_by = (
                "score DESC, created_at, story_id"
                if os.environ.get("QUEUE_RANK_BY_SCORE", "") != "0"
                else "created_at, story_id"
            )
            aliases = [channel_key]
            for alias, target in CHANNEL_ALIASES.items():
                if getattr(target, "value", str(target)) == channel_key and alias not in aliases:
                    aliases.append(alias)
            placeholders = ",".join("?" for _ in aliases)
            row = conn.execute(
                f"""
                SELECT * FROM stories
                WHERE channel IN ({placeholders})
                  AND status IN (?, ?)
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY {order_by}
                LIMIT 1
                """,
                (
                    *aliases,
                    JobStatus.PENDING.value,
                    JobStatus.RETRYABLE_FAILED.value,
                    current,
                ),
            ).fetchone()
            if not row:
                conn.rollback()
                return None
            run_id = uuid.uuid4().hex
            getattr(self, "_bind_channel_lease_locked")(
                conn, run_id, channel_key, row["story_id"], mode, owner, current, lease_seconds
            )
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = ?, error_msg = NULL,
                    failure_code = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ?
                """,
                (JobStatus.PROCESSING.value, run_id, row["story_id"]),
            )
            conn.commit()
            result = dict(row)
            result.update(status=JobStatus.PROCESSING.value, run_id=run_id)
            return result

    def claim_exact(
        self,
        story_id: str,
        channel: str | CanonicalChannel,
        owner: str,
        *,
        lease_seconds: int = 900,
        mode: str = "directed-publish",
        now: int | None = None,
    ) -> dict[str, Any] | None:
        """Atomically claim one explicit story without recovering or touching others."""
        requested_id = str(story_id or "").strip()
        if not requested_id:
            raise ValueError("story_id es obligatorio para el claim dirigido")
        if not owner.strip():
            raise ValueError("El propietario del lease es obligatorio")
        channel_key = canonical_channel(channel).value
        current = int(time.time() if now is None else now)
        allowed = (
            JobStatus.PENDING.value,
            JobStatus.RETRYABLE_FAILED.value,
            JobStatus.WAITING_IMAGE_QUOTA.value,
            JobStatus.WAITING_LLM_QUOTA.value,
            JobStatus.WAITING_YOUTUBE_LIMIT.value,
        )
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            paused = conn.execute(
                "SELECT paused FROM channel_controls WHERE channel = ?", (channel_key,)
            ).fetchone()
            if paused and paused["paused"]:
                conn.rollback()
                return None
            getattr(self, "_recover_expired_exact_locked")(
                conn, requested_id, channel_key, current
            )
            if conn.execute(
                "SELECT 1 FROM leases WHERE channel = ?", (channel_key,)
            ).fetchone() or conn.execute(
                "SELECT 1 FROM lane_leases WHERE job_id = ?", (requested_id,)
            ).fetchone():
                conn.rollback()
                return None
            placeholders = ",".join("?" for _ in allowed)
            row = conn.execute(
                f"""
                SELECT * FROM stories
                WHERE story_id = ? AND channel = ?
                  AND status IN ({placeholders})
                  AND youtube_video_id IS NULL
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                """,
                (requested_id, channel_key, *allowed, current),
            ).fetchone()
            if not row:
                conn.rollback()
                return None
            run_id = uuid.uuid4().hex
            getattr(self, "_bind_channel_lease_locked")(
                conn, run_id, channel_key, requested_id, mode, owner, current, lease_seconds
            )
            updated = conn.execute(
                f"""
                UPDATE stories
                SET status = ?, run_id = ?, error_msg = NULL,
                    failure_code = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ? AND channel = ? AND status IN ({placeholders})
                """,
                (
                    JobStatus.PROCESSING.value,
                    run_id,
                    requested_id,
                    channel_key,
                    *allowed,
                ),
            )
            if updated.rowcount != 1:
                conn.rollback()
                return None
            conn.commit()
            result = dict(row)
            result.update(status=JobStatus.PROCESSING.value, run_id=run_id)
            return result

    def get_story_record(self, story_id: str) -> StoryRecord | None:
        """Fetch a story as a strongly-typed StoryRecord instance."""
        from src.core.contracts.story import StoryRecord

        with connect(self.db_path, read_only=True) as conn:
            row = conn.execute(
                "SELECT * FROM stories WHERE story_id = ?", (story_id,)
            ).fetchone()
            if not row:
                return None
            return StoryRecord.from_row(row)

    def require_single_story_run(self, run_id: str, story_id: str) -> None:
        with connect(self.db_path, read_only=True) as conn:
            rows = conn.execute(
                "SELECT story_id, position FROM run_stories WHERE run_id = ?",
                (run_id,),
            ).fetchall()
        if len(rows) != 1 or rows[0]["story_id"] != story_id or rows[0]["position"] != 0:
            raise RuntimeError(
                "El run dirigido debe contener exactamente una historia principal"
            )

    def set_status(
        self,
        story_id: str,
        status: str | JobStatus,
        *,
        error_code: str | None = None,
        error_detail: str | None = None,
        retry_at: int | None = None,
        run_id: str | None = None,
        owner: str | None = None,
        now: int | None = None,
    ) -> bool:
        value = status.value if isinstance(status, JobStatus) else str(status)
        if value not in ALL_STATUSES:
            raise ValueError(f"Estado operativo inválido: {value}")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT run_id, status FROM stories WHERE story_id = ?", (story_id,)
            ).fetchone()
            if not row:
                conn.rollback()
                raise KeyError(story_id)
            if row["status"] == JobStatus.PUBLISHED.value and value != JobStatus.PUBLISHED.value:
                conn.rollback()
                return False
            if (run_id is None) != (owner is None):
                conn.rollback()
                raise ValueError("run_id y owner deben proporcionarse juntos")
            active_run_id = row["run_id"]
            if run_id is not None:
                current = int(time.time() if now is None else now)
                lease = conn.execute(
                    """
                    SELECT 1 FROM leases
                    WHERE job_id = ? AND run_id = ? AND owner = ? AND expires_at > ?
                    """,
                    (story_id, run_id, owner, current),
                ).fetchone()
                if not lease:
                    lease = conn.execute(
                        """
                        SELECT 1 FROM lane_leases
                        WHERE job_id = ? AND run_id = ? AND owner = ? AND expires_at > ?
                        """,
                        (story_id, run_id, owner, current),
                    ).fetchone()
                if active_run_id != run_id or not lease:
                    conn.rollback()
                    return False
                active_run_id = run_id
            cursor = conn.execute(
                """
                UPDATE stories
                SET status = ?, failure_code = ?, error_msg = ?,
                    next_attempt_at = ?, retry_count = retry_count +
                        CASE WHEN ? = ? THEN 1 ELSE 0 END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ? AND status != ?
                """,
                (
                    value,
                    error_code,
                    error_detail,
                    retry_at,
                    value,
                    JobStatus.RETRYABLE_FAILED.value,
                    story_id,
                    JobStatus.PUBLISHED.value,
                ),
            )
            if not cursor.rowcount:
                conn.rollback()
                return False
            if active_run_id:
                release_states = {
                    JobStatus.PUBLISHED.value,
                    JobStatus.UPLOAD_UNCONFIRMED.value,
                    JobStatus.RETRYABLE_FAILED.value,
                    JobStatus.PERMANENT_FAILED.value,
                    JobStatus.WAITING_LLM_QUOTA.value,
                    JobStatus.WAITING_IMAGE_QUOTA.value,
                    JobStatus.WAITING_YOUTUBE_LIMIT.value,
                    "COMPLETED",
                    "FAILED",
                }
                finished = _utc_now() if value in release_states else None
                conn.execute(
                    """
                    UPDATE runs
                    SET status = ?, error_code = ?, error_detail = ?, finished_at = ?
                    WHERE run_id = ?
                    """,
                    (value, error_code, error_detail, finished, active_run_id),
                )
                if value in release_states:
                    conn.execute("DELETE FROM leases WHERE run_id = ?", (active_run_id,))
                    conn.execute("DELETE FROM lane_leases WHERE run_id = ?", (active_run_id,))
            conn.commit()
            return True

    def record_artifact(
        self,
        run_id: str,
        kind: str,
        *,
        local_path: str | None = None,
        remote_provider: str | None = None,
        remote_id: str | None = None,
        remote_name: str | None = None,
        size_bytes: int | None = None,
        sha256: str | None = None,
        verified: bool = False,
        story_key: str | None = None,
    ) -> None:
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                channel = "aelithia" if (story_key and "aelithia" in story_key) else "moku"
                now = _utc_now()
                conn.execute(
                    """
                    INSERT OR IGNORE INTO runs(
                        run_id, channel, story_id, mode, status, owner, started_at, heartbeat_at
                    ) VALUES (?, ?, NULL, 'publish', 'PROCESSING', 'checkpoint', ?, ?)
                    """,
                    (run_id, channel, now, now),
                )
                conn.execute(
                    """
                    INSERT INTO artifacts(
                        run_id, kind, local_path, remote_provider, remote_id,
                        remote_name, size_bytes, sha256, verified_at, created_at, story_key
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id, kind, local_path) DO UPDATE SET
                        remote_provider = excluded.remote_provider,
                        remote_id = excluded.remote_id,
                        remote_name = excluded.remote_name,
                        size_bytes = excluded.size_bytes,
                        sha256 = excluded.sha256,
                        verified_at = excluded.verified_at,
                        story_key = excluded.story_key
                    """,
                    (
                        run_id,
                        kind,
                        local_path,
                        remote_provider,
                        remote_id,
                        remote_name,
                        size_bytes,
                        sha256,
                        now if verified else None,
                        now,
                        story_key,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def record_youtube_upload_id(
        self,
        story_id: str,
        run_id: str,
        video_id: str,
        *,
        owner: str | None = None,
    ) -> None:
        """Persist a returned YouTube ID before any later verification can fail."""
        remote_id = str(video_id or "").strip()
        if not remote_id:
            raise ValueError("YouTube no devolvió un video_id persistible")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            story = conn.execute(
                "SELECT run_id FROM stories WHERE story_id = ?", (story_id,)
            ).fetchone()
            if not story or story["run_id"] != run_id:
                conn.rollback()
                raise RuntimeError("El video_id no pertenece al run activo")
            if owner is not None and not getattr(self, "_holds_lease")(conn, story_id, run_id, owner):
                conn.rollback()
                raise RuntimeError("Se perdió ownership antes de persistir video_id")
            existing = conn.execute(
                "SELECT youtube_video_id FROM stories WHERE story_id = ?",
                (story_id,),
            ).fetchone()[0]
            if existing and existing != remote_id:
                conn.rollback()
                raise RuntimeError("La historia ya conserva otro video_id de YouTube")
            conn.execute(
                "UPDATE stories SET youtube_video_id = ? WHERE story_id = ?",
                (remote_id, story_id),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO artifacts(
                    run_id, kind, remote_provider, remote_id, verified_at, created_at
                ) VALUES (?, 'youtube_video', 'youtube', ?, NULL, ?)
                """,
                (run_id, remote_id, _utc_now()),
            )
            conn.commit()

    def record_drive_upload_id(
        self,
        story_id: str,
        run_id: str,
        file_id: str,
        *,
        owner: str | None = None,
    ) -> None:
        """Persist a Drive ID immediately while fencing the active worker."""
        remote_id = str(file_id or "").strip()
        if not remote_id:
            raise ValueError("Drive no devolvió un file_id persistible")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            story = conn.execute(
                "SELECT run_id, drive_file_id FROM stories WHERE story_id = ?",
                (story_id,),
            ).fetchone()
            if not story or story["run_id"] != run_id:
                conn.rollback()
                raise RuntimeError("El file_id de Drive no pertenece al run activo")
            if owner is not None and not getattr(self, "_holds_lease")(conn, story_id, run_id, owner):
                conn.rollback()
                raise RuntimeError("Se perdió ownership antes de persistir file_id")
            if story["drive_file_id"] and story["drive_file_id"] != remote_id:
                conn.rollback()
                raise RuntimeError("La historia ya conserva otro file_id de Drive")
            conn.execute(
                "UPDATE stories SET drive_file_id = ? WHERE story_id = ? AND run_id = ?",
                (remote_id, story_id, run_id),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO artifacts(
                    run_id, kind, remote_provider, remote_id, verified_at, created_at
                ) VALUES (?, 'drive_video_pending', 'drive', ?, NULL, ?)
                """,
                (run_id, remote_id, _utc_now()),
            )
            conn.commit()

    def record_fingerprint(
        self,
        run_id: str,
        story_id: str,
        channel: str | CanonicalChannel,
        kind: str,
        payload: str | bytes,
        *,
        normalized_text: str | None = None,
        simhash: int | None = None,
    ) -> bool:
        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        digest = hashlib.sha256(raw).hexdigest()
        if simhash is None and isinstance(payload, str):
            simhash = compute_simhash_64(payload)
        elif simhash is None and normalized_text:
            simhash = compute_simhash_64(normalized_text)
        return self.record_fingerprint_digest(
            run_id,
            story_id,
            channel,
            kind,
            digest,
            normalized_text=normalized_text,
            simhash=simhash,
        )

    def record_fingerprint_digest(
        self,
        run_id: str,
        story_id: str,
        channel: str | CanonicalChannel,
        kind: str,
        digest: str,
        *,
        normalized_text: str | None = None,
        simhash: int | None = None,
    ) -> bool:
        if not re_full_sha256(digest):
            raise ValueError("Fingerprint SHA-256 inválido")
        channel_key = canonical_channel(channel).value
        calc_simhash = simhash
        if calc_simhash is None and normalized_text:
            calc_simhash = compute_simhash_64(normalized_text)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            now = _utc_now()
            conn.execute(
                """
                INSERT OR IGNORE INTO runs(
                    run_id, channel, story_id, mode, status, owner, started_at, heartbeat_at
                ) VALUES (?, ?, ?, 'publish', 'PROCESSING', 'fingerprint', ?, ?)
                """,
                (run_id, channel_key, story_id, now, now),
            )
            try:
                conn.execute(
                    """
                    INSERT INTO content_fingerprints(
                        run_id, story_id, channel, kind, sha256,
                        normalized_text, created_at, simhash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        story_id,
                        channel_key,
                        kind,
                        digest,
                        normalized_text,
                        now,
                        to_signed_64(calc_simhash),
                    ),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                conn.rollback()
                return False

    def has_near_duplicate(
        self,
        channel: str | CanonicalChannel,
        simhash_or_text: int | str,
        *,
        max_distance: int = 3,
    ) -> bool:
        channel_key = canonical_channel(channel).value
        target_simhash = (
            simhash_or_text
            if isinstance(simhash_or_text, int)
            else compute_simhash_64(simhash_or_text)
        )
        if target_simhash == 0:
            return False
        with connect(self.db_path, read_only=True) as conn:
            rows = conn.execute(
                """
                SELECT simhash
                FROM content_fingerprints
                WHERE channel = ? AND simhash IS NOT NULL
                """,
                (channel_key,),
            ).fetchall()
        for row in rows:
            existing = row["simhash"]
            if existing is not None and simhash_hamming_distance(target_simhash, existing) <= max_distance:
                return True
        return False

    def recent_published_texts(
        self,
        channel: str | CanonicalChannel,
        *,
        limit: int = 50,
    ) -> list[str]:
        channel_key = canonical_channel(channel).value
        with connect(self.db_path, read_only=True) as conn:
            return [
                str(row["normalized_text"])
                for row in conn.execute(
                    """
                    SELECT f.normalized_text
                    FROM content_fingerprints f
                    JOIN runs r ON r.run_id = f.run_id
                    WHERE f.channel = ? AND f.normalized_text IS NOT NULL
                      AND r.status = ?
                    ORDER BY f.created_at DESC LIMIT ?
                    """,
                    (channel_key, JobStatus.PUBLISHED.value, limit),
                )
            ]

    def has_published_fingerprint(
        self,
        channel: str | CanonicalChannel,
        kind: str,
        payload: str | bytes,
    ) -> bool:
        raw = payload.encode("utf-8") if isinstance(payload, str) else payload
        digest = hashlib.sha256(raw).hexdigest()
        return self.has_published_digest(channel, kind, digest)

    def has_published_digest(
        self,
        channel: str | CanonicalChannel,
        kind: str,
        digest: str,
    ) -> bool:
        if not re_full_sha256(digest):
            raise ValueError("Fingerprint SHA-256 inválido")
        channel_key = canonical_channel(channel).value
        with connect(self.db_path, read_only=True) as conn:
            return (
                conn.execute(
                    """
                    SELECT 1
                    FROM content_fingerprints f
                    JOIN runs r ON r.run_id = f.run_id
                    WHERE f.channel = ? AND f.kind = ? AND f.sha256 = ?
                      AND r.status = ?
                    """,
                    (channel_key, kind, digest, JobStatus.PUBLISHED.value),
                ).fetchone()
                is not None
            )

    def record_provider_attempt(
        self,
        run_id: str,
        provider: str,
        operation: str,
        *,
        outcome: str,
        error_code: str | None = None,
        error_detail: str | None = None,
    ) -> None:
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                attempt_no = int(
                    conn.execute(
                        """
                        SELECT COALESCE(MAX(attempt_no), 0) + 1
                        FROM provider_attempts
                        WHERE run_id = ? AND provider = ? AND operation = ?
                        """,
                        (run_id, provider, operation),
                    ).fetchone()[0]
                )
                now = _utc_now()
                conn.execute(
                    """
                    INSERT INTO provider_attempts(
                        run_id, provider, operation, attempt_no, started_at,
                        finished_at, outcome, error_code, error_detail
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        provider,
                        operation,
                        attempt_no,
                        now,
                        now,
                        outcome,
                        error_code,
                        error_detail,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def finish_run(
        self,
        run_id: str,
        status: str | JobStatus,
        *,
        owner: str | None = None,
    ) -> bool:
        value = status.value if isinstance(status, JobStatus) else str(status)
        if value not in ALL_STATUSES:
            raise ValueError(f"Estado operativo inválido: {value}")
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if owner is not None and not (
                conn.execute(
                    "SELECT 1 FROM leases WHERE run_id = ? AND owner = ? AND expires_at > ?",
                    (run_id, owner, int(time.time())),
                ).fetchone()
                or conn.execute(
                    "SELECT 1 FROM lane_leases WHERE run_id = ? AND owner = ? AND expires_at > ?",
                    (run_id, owner, int(time.time())),
                ).fetchone()
            ):
                conn.rollback()
                return False
            cursor = conn.execute(
                "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ? AND status != ?",
                (value, _utc_now(), run_id, JobStatus.PUBLISHED.value),
            )
            if not cursor.rowcount:
                conn.rollback()
                return False
            conn.execute("DELETE FROM leases WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM lane_leases WHERE run_id = ?", (run_id,))
            conn.commit()
            return True

    def _validate_publication_preconditions(
        self,
        conn: sqlite3.Connection,
        story_id: str,
        run_id: str,
        proof: PublicationProof,
        owner: str | None,
    ) -> list[dict[str, Any]]:
        story = conn.execute(
            "SELECT channel, run_id FROM stories WHERE story_id = ?", (story_id,)
        ).fetchone()
        if not story or story["run_id"] != run_id:
            raise RuntimeError("La publicación no pertenece al run activo")
        if owner is not None and not getattr(self, "_holds_lease")(conn, story_id, run_id, owner):
            raise RuntimeError("Se perdió ownership antes del commit de publicación")
        if canonical_channel(story["channel"]) != proof.channel:
            raise RuntimeError("El canal confirmado no coincide con el trabajo")
        linked = conn.execute(
            "SELECT story_id, position FROM run_stories WHERE run_id = ? ORDER BY position ASC",
            (run_id,),
        ).fetchall()
        if not linked:
            conn.execute(
                "INSERT INTO run_stories(run_id, story_id, position) VALUES (?, ?, 0)",
                (run_id, story_id),
            )
            linked = [{"story_id": story_id, "position": 0}]
        run_row = conn.execute(
            "SELECT mode FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        is_directed = run_row and "directed" in str(run_row["mode"] or "")
        if is_directed:
            if len(linked) != 1 or linked[0]["story_id"] != story_id or linked[0]["position"] != 0:
                raise RuntimeError("La publicación exige run_stories con una única historia principal")
        else:
            if not linked or linked[0]["story_id"] != story_id or linked[0]["position"] != 0:
                raise RuntimeError("La publicación exige que la historia principal esté en la posición 0")
        return [dict(item) for item in linked]

    def mark_published(
        self,
        story_id: str,
        run_id: str,
        proof: PublicationProof,
        *,
        provider: str,
        owner: str | None = None,
    ) -> None:
        proof.validate()
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                linked = self._validate_publication_preconditions(conn, story_id, run_id, proof, owner)
                conn.execute(
                    """
                    INSERT INTO publications(
                        run_id, story_id, provider, video_id, url, channel,
                        visibility, title, description, thumbnail_confirmed, verified_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """,
                    (
                        run_id,
                        story_id,
                        provider,
                        proof.video_id,
                        proof.url,
                        proof.channel.value,
                        proof.visibility,
                        proof.title,
                        proof.description,
                        _utc_now(),
                    ),
                )
                for item in linked:
                    conn.execute(
                        """
                        UPDATE stories
                        SET status = ?, youtube_video_id = ?, youtube_url = ?,
                            publication_visibility = ?, publication_channel = ?,
                            run_id = ?,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE story_id = ?
                        """,
                        (
                            JobStatus.PUBLISHED.value,
                            proof.video_id,
                            proof.url,
                            proof.visibility,
                            proof.channel.value,
                            run_id,
                            item["story_id"],
                        ),
                    )
                conn.execute(
                    "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ?",
                    (JobStatus.PUBLISHED.value, _utc_now(), run_id),
                )
                conn.execute("DELETE FROM leases WHERE run_id = ?", (run_id,))
                conn.execute("DELETE FROM lane_leases WHERE run_id = ?", (run_id,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def pause(self, channel: str | CanonicalChannel, reason: str | None = None) -> None:
        self._set_paused(channel, True, reason)

    def resume(self, channel: str | CanonicalChannel, *, resume_lanes: bool = True) -> None:
        self._set_paused(channel, False, None)
        if resume_lanes:
            channel_key = canonical_channel(channel).value
            with connect(self.db_path) as conn:
                conn.execute(
                    "UPDATE scheduler_lane_state SET paused = 0, pause_reason = NULL, updated_at = ? WHERE lane_id LIKE ?",
                    (_utc_now(), f"{channel_key}-%"),
                )
                conn.commit()

    def _set_paused(
        self,
        channel: str | CanonicalChannel,
        paused: bool,
        reason: str | None,
    ) -> None:
        channel_key = canonical_channel(channel).value
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO channel_controls(channel, paused, reason, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(channel) DO UPDATE SET
                        paused = excluded.paused,
                        reason = excluded.reason,
                        updated_at = excluded.updated_at
                    """,
                    (channel_key, int(paused), reason, _utc_now()),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    def queue_summary(self) -> dict[str, Any]:
        with connect(self.db_path, read_only=True) as conn:
            counts = {
                row["status"]: int(row["count"])
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS count FROM stories GROUP BY status"
                )
            }
            leases = [dict(row) for row in conn.execute("SELECT * FROM leases")]
            controls = [
                dict(row)
                for row in conn.execute(
                    "SELECT channel, paused, reason, updated_at FROM channel_controls"
                )
            ]
        return {"counts": counts, "leases": leases, "controls": controls}

    def is_channel_paused(self, channel: str | CanonicalChannel) -> bool:
        channel_key = canonical_channel(channel).value
        with connect(self.db_path, read_only=True) as conn:
            row = conn.execute(
                "SELECT paused FROM channel_controls WHERE channel = ?", (channel_key,)
            ).fetchone()
        return bool(row and row["paused"])

    def record_scene_assets(
        self,
        run_id: str,
        story_id: str,
        scene_assets: Sequence[dict[str, Any]],
    ) -> int:
        """Persist structured scene/shot asset lineage for a story run."""
        if not scene_assets:
            return 0
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                for asset in scene_assets:
                    conn.execute(
                        """
                        INSERT INTO story_scene_assets(
                            run_id, story_id, scene_index, shot_index,
                            asset_source, source_url_or_path, framing_type,
                            prompt_used, dhash, duration_sec
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            story_id,
                            int(asset.get("scene_index", 0)),
                            int(asset.get("shot_index", 0)),
                            str(asset.get("asset_source", "local_bank")),
                            str(asset.get("source_url_or_path", asset.get("image_path", ""))),
                            str(asset.get("framing_type", "WIDE_ESTABLISHING")),
                            asset.get("prompt_used") or asset.get("prompt"),
                            asset.get("dhash"),
                            float(asset.get("duration_sec", 0.0)),
                        ),
                    )
                conn.commit()
                return len(scene_assets)
            except Exception:
                conn.rollback()
                raise

    def get_scene_assets(self, story_id: str) -> list[dict[str, Any]]:
        """Retrieve all recorded scene assets for a story ordered by scene and shot."""
        return self._fetch_all(
            "SELECT * FROM story_scene_assets WHERE story_id = ? ORDER BY scene_index, shot_index, scene_asset_id",
            (story_id,),
        )

    def record_production_metrics(
        self,
        run_id: str,
        story_id: str,
        audio_duration_sec: float,
        render_time_sec: float,
        tts_time_sec: float | None = None,
        video_size_bytes: int = 0,
        integrated_lufs: float | None = None,
        qa_audit_passed: bool = True,
    ) -> bool:
        """Record pipeline execution telemetry for performance analysis."""
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO production_metrics(
                        run_id, story_id, audio_duration_sec, render_time_sec,
                        tts_time_sec, video_size_bytes, integrated_lufs,
                        qa_audit_passed, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(run_id) DO UPDATE SET
                        audio_duration_sec = excluded.audio_duration_sec,
                        render_time_sec = excluded.render_time_sec,
                        tts_time_sec = excluded.tts_time_sec,
                        video_size_bytes = excluded.video_size_bytes,
                        integrated_lufs = excluded.integrated_lufs,
                        qa_audit_passed = excluded.qa_audit_passed
                    """,
                    (
                        run_id,
                        story_id,
                        float(audio_duration_sec),
                        float(render_time_sec),
                        float(tts_time_sec) if tts_time_sec is not None else None,
                        int(video_size_bytes),
                        float(integrated_lufs) if integrated_lufs is not None else None,
                        1 if qa_audit_passed else 0,
                        _utc_now(),
                    ),
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def get_production_metrics(self, run_id: str) -> dict[str, Any] | None:
        """Retrieve production telemetry for a specific run."""
        return self._fetch_one("SELECT * FROM production_metrics WHERE run_id = ?", (run_id,))

    def record_analytics_snapshot(
        self,
        video_id: str,
        story_id: str,
        channel: str | CanonicalChannel,
        view_count: int = 0,
        like_count: int = 0,
        comment_count: int = 0,
        avg_view_duration_sec: float | None = None,
        retention_rate_pct: float | None = None,
        snapshot_interval: str = "24h",
        recorded_at: str | None = None,
    ) -> bool:
        """Record a point-in-time YouTube engagement snapshot."""
        channel_key = canonical_channel(channel).value
        ts = recorded_at or _utc_now()
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute(
                    """
                    INSERT INTO video_analytics_snapshots(
                        video_id, story_id, channel, view_count, like_count,
                        comment_count, avg_view_duration_sec, retention_rate_pct,
                        snapshot_interval, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        video_id,
                        story_id,
                        channel_key,
                        int(view_count),
                        int(like_count),
                        int(comment_count),
                        float(avg_view_duration_sec) if avg_view_duration_sec is not None else None,
                        float(retention_rate_pct) if retention_rate_pct is not None else None,
                        snapshot_interval,
                        ts,
                    ),
                )
                conn.commit()
                return True
            except Exception:
                conn.rollback()
                raise

    def get_analytics_snapshots(self, story_id: str) -> list[dict[str, Any]]:
        """Retrieve all historical analytics snapshots for a story."""
        return self._fetch_all(
            "SELECT * FROM video_analytics_snapshots WHERE story_id = ? ORDER BY recorded_at ASC, snapshot_id ASC",
            (story_id,),
        )

    def record_system_event(
        self,
        event_type: str,
        *,
        level: str = "INFO",
        run_id: str | None = None,
        story_id: str | None = None,
        channel: str | None = None,
        component: str | None = None,
        stage: str | None = None,
        error_code: str | None = None,
        message: str | None = None,
        details: dict[str, Any] | Mapping[str, Any] | None = None,
    ) -> int:
        """Persist one observability event and return its row id."""
        allowed_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        normalized_level = str(level).upper()
        if normalized_level not in allowed_levels:
            raise ValueError(f"Nivel de evento inválido: {level}")
        payload = json.dumps(
            dict(details) if details else {},
            ensure_ascii=False,
            default=str,
        )
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO system_events(
                        ts, level, event_type, run_id, story_id, channel,
                        component, stage, error_code, message, details_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _utc_now(),
                        normalized_level,
                        str(event_type),
                        run_id,
                        story_id,
                        channel,
                        component,
                        stage,
                        error_code,
                        message,
                        payload,
                    ),
                )
                conn.commit()
                return int(cursor.lastrowid)
            except Exception:
                conn.rollback()
                raise

    def query_system_events(
        self,
        *,
        level: str | None = None,
        event_type: str | None = None,
        run_id: str | None = None,
        component: str | None = None,
        since_ts: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Query observability events, newest first (read-only)."""
        clauses: list[str] = []
        params: list[Any] = []
        if level:
            clauses.append("level = ?")
            params.append(str(level).upper())
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        if run_id:
            clauses.append("run_id = ?")
            params.append(run_id)
        if component:
            clauses.append("component = ?")
            params.append(component)
        if since_ts:
            clauses.append("ts >= ?")
            params.append(since_ts)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, int(limit)))
        with connect(self.db_path, read_only=True) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    f"""
                    SELECT * FROM system_events {where}
                    ORDER BY event_id DESC LIMIT ?
                    """,
                    tuple(params),
                )
            ]

    def prune_system_events(
        self,
        *,
        retention_days: int = 30,
        max_rows: int = 50_000,
    ) -> int:
        """Delete events older than retention and cap table size; returns deleted count."""
        cutoff = (
            datetime.now(timezone.utc) - timedelta(days=max(0, int(retention_days)))
        ).isoformat(timespec="seconds")
        deleted = 0
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute(
                    "DELETE FROM system_events WHERE ts < ?", (cutoff,)
                )
                deleted += int(cursor.rowcount)
                excess = conn.execute(
                    "SELECT COUNT(*) FROM system_events"
                ).fetchone()[0] - max(0, int(max_rows))
                if excess > 0:
                    cursor = conn.execute(
                        """
                        DELETE FROM system_events WHERE event_id IN (
                            SELECT event_id FROM system_events
                            ORDER BY event_id ASC LIMIT ?
                        )
                        """,
                        (int(excess),),
                    )
                    deleted += int(cursor.rowcount)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return deleted

    def recent_failed_runs(self, *, limit: int = 10) -> list[dict[str, Any]]:
        """Latest runs that did not finish cleanly, newest first."""
        with connect(self.db_path, read_only=True) as conn:
            return [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT run_id, channel, story_id, status, started_at,
                           finished_at, error_code, error_detail
                    FROM runs
                    WHERE status NOT IN ('PUBLISHED', 'COMPLETED')
                    ORDER BY started_at DESC LIMIT ?
                    """,
                    (max(1, int(limit)),),
                )
            ]

    def get_run_artifact(self, run_id: str, kind: str) -> dict[str, Any] | None:
        """Return one recorded artifact of a run by kind (e.g. 'video')."""
        return self._fetch_one(
            "SELECT * FROM artifacts WHERE run_id = ? AND kind = ? ORDER BY artifact_id DESC LIMIT 1",
            (run_id, kind),
        )

    def ensure_lane_rows(
        self,
        lane_ids: Sequence[str] | Mapping[str, int],
        *,
        offsets: Mapping[str, int] | None = None,
        now: int | None = None,
    ) -> None:
        """Seed scheduler state rows for the configured lanes (runtime, not SQL)."""
        stamp = _utc_now()
        current = int(time.time() if now is None else now)
        items: list[tuple[str, int]] = []
        if isinstance(lane_ids, Mapping):
            items = [(str(lid), int(offset)) for lid, offset in lane_ids.items()]
        else:
            offsets_map = offsets or {}
            items = [(str(lid), int(offsets_map.get(str(lid), 0))) for lid in lane_ids]

        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            for lane_id, offset in items:
                conn.execute(
                    "INSERT OR IGNORE INTO scheduler_lane_state("
                    "lane_id, next_due_at, consecutive_empty, updated_at"
                    ") VALUES (?, ?, 0, ?)",
                    (lane_id, current + offset, stamp),
                )
            conn.commit()

    def due_lanes(self, *, now: int | None = None) -> list[dict[str, Any]]:
        """Lanes whose cadence ceiling expired, most-overdue first."""
        current = int(time.time() if now is None else now)
        with connect(self.db_path, read_only=True) as conn:
            rows = conn.execute(
                "SELECT * FROM scheduler_lane_state "
                "WHERE paused = 0 AND next_due_at <= ? "
                "ORDER BY next_due_at ASC, lane_id ASC",
                (current,),
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_lane_fired(
        self,
        lane_id: str,
        *,
        fired_at: int,
        next_due_at: int,
        run_id: str | None = None,
        empty: bool = False,
    ) -> None:
        """Persist the post-fire cadence ceiling (never accumulates missed turns)."""
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            if empty:
                conn.execute(
                    "UPDATE scheduler_lane_state SET next_due_at = ?, "
                    "consecutive_empty = consecutive_empty + 1, updated_at = ? "
                    "WHERE lane_id = ?",
                    (next_due_at, _utc_now(), lane_id),
                )
            else:
                conn.execute(
                    "UPDATE scheduler_lane_state SET next_due_at = ?, last_started_at = ?, "
                    "last_run_id = ?, consecutive_empty = 0, updated_at = ? WHERE lane_id = ?",
                    (next_due_at, fired_at, run_id, _utc_now(), lane_id),
                )
            conn.commit()

    def set_lane_paused(self, lane_id: str, paused: bool, reason: str | None = None) -> None:
        self._execute_write(
            """
            INSERT INTO scheduler_lane_state(lane_id, next_due_at, consecutive_empty, paused, pause_reason, updated_at)
            VALUES (?, 0, 0, ?, ?, ?)
            ON CONFLICT(lane_id) DO UPDATE SET
                paused = excluded.paused,
                pause_reason = excluded.pause_reason,
                updated_at = excluded.updated_at
            """,
            (lane_id, 1 if paused else 0, reason, _utc_now()),
        )

    def get_lane_state(self, lane_id: str) -> dict[str, Any] | None:
        return self._fetch_one("SELECT * FROM scheduler_lane_state WHERE lane_id = ?", (lane_id,))

    def claim_for_lane(
        self,
        lane_id: str,
        channel: str | CanonicalChannel,
        owner: str,
        *,
        lease_seconds: int = 900,
        mode: str = "publish",
        now: int | None = None,
    ) -> dict[str, Any] | None:
        """Claim one story for a lane using the parallel ``lane_leases`` table."""
        lane_key = str(lane_id or "").strip()
        if not lane_key:
            raise ValueError("lane_id es obligatorio para el claim por carril")
        channel_key = canonical_channel(channel).value
        if not owner.strip():
            raise ValueError("El propietario del lease es obligatorio")
        current = int(time.time() if now is None else now)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            paused = conn.execute(
                "SELECT paused FROM channel_controls WHERE channel = ?", (channel_key,)
            ).fetchone()
            if paused and paused["paused"]:
                conn.rollback()
                return None
            getattr(self, "_recover_expired_lanes_locked")(conn, current)
            if conn.execute(
                "SELECT 1 FROM lane_leases WHERE lane_id = ?", (lane_key,)
            ).fetchone() or conn.execute(
                "SELECT 1 FROM leases WHERE channel = ?", (channel_key,)
            ).fetchone():
                conn.rollback()
                return None
            row = conn.execute(
                """
                SELECT * FROM stories
                WHERE channel = ?
                  AND status IN (?, ?)
                  AND (lane_id IS NULL OR lane_id = ?)
                  AND (next_attempt_at IS NULL OR next_attempt_at <= ?)
                ORDER BY CASE WHEN lane_id = ? THEN 0 ELSE 1 END,
                         CASE WHEN status = ? THEN 0 ELSE 1 END,
                         created_at, story_id
                LIMIT 1
                """,
                (
                    channel_key,
                    JobStatus.PENDING.value,
                    JobStatus.RETRYABLE_FAILED.value,
                    lane_key,
                    current,
                    lane_key,
                    JobStatus.PENDING.value,
                ),
            ).fetchone()
            if not row:
                conn.rollback()
                return None
            run_id = uuid.uuid4().hex
            getattr(self, "_bind_lane_lease_locked")(
                conn, run_id, channel_key, row["story_id"], mode, owner, lane_key, current, lease_seconds
            )
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = ?, lane_id = ?, error_msg = NULL,
                    failure_code = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ?
                """,
                (JobStatus.PROCESSING.value, run_id, lane_key, row["story_id"]),
            )
            conn.commit()
            result = dict(row)
            result.update(status=JobStatus.PROCESSING.value, run_id=run_id)
            return result

    def _select_resumable_candidate(
        self,
        rows: Sequence[sqlite3.Row],
    ) -> tuple[sqlite3.Row, str] | None:
        from src.core.checkpoints import resumable_video_for_story
        review_store = None
        try:
            from review.db import ReviewStateStore
            review_store = ReviewStateStore()
        except Exception:
            pass

        for row in rows:
            sid = str(row["story_id"])
            if review_store is not None:
                try:
                    job = review_store.get_latest_job(sid)
                    if job and job.status in {
                        "PENDING_REVIEW",
                        "WAITING_HUMAN_VERIFICATION",
                        "APPROVED",
                        "PUBLISHED",
                    }:
                        continue
                except Exception:
                    pass
            video = resumable_video_for_story(str(row["candidate_run_id"]), db_path=self.db_path)
            if video is not None:
                return (row, str(video))
        return None

    def claim_resumable(
        self,
        lane_id: str,
        channel: str | CanonicalChannel,
        owner: str,
        *,
        lease_seconds: int = 900,
        mode: str = "resume-publish",
        now: int | None = None,
    ) -> dict[str, Any] | None:
        """Re-claim a stuck story (RENDERED/DRIVE_BACKED_UP/UPLOAD_UNCONFIRMED)."""
        lane_key = str(lane_id or "").strip()
        if not lane_key:
            raise ValueError("lane_id es obligatorio para el claim de reanudación")
        channel_key = canonical_channel(channel).value
        if not owner.strip():
            raise ValueError("El propietario del lease es obligatorio")
        current = int(time.time() if now is None else now)
        resumable_states = (
            JobStatus.RENDERED.value,
            JobStatus.DRIVE_BACKED_UP.value,
            JobStatus.UPLOAD_UNCONFIRMED.value,
            JobStatus.WAITING_YOUTUBE_LIMIT.value,
        )
        placeholders = ",".join("?" for _ in resumable_states)
        with connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            paused = conn.execute(
                "SELECT paused FROM channel_controls WHERE channel = ?", (channel_key,)
            ).fetchone()
            if paused and paused["paused"]:
                conn.rollback()
                return None
            getattr(self, "_recover_expired_lanes_locked")(conn, current)
            if conn.execute(
                "SELECT 1 FROM lane_leases WHERE lane_id = ?", (lane_key,)
            ).fetchone() or conn.execute(
                "SELECT 1 FROM leases WHERE channel = ?", (channel_key,)
            ).fetchone():
                conn.rollback()
                return None
            rows = conn.execute(
                f"""
                SELECT s.*, r.run_id AS candidate_run_id FROM stories s
                JOIN runs r ON r.story_id = s.story_id AND r.lane_id = ?
                WHERE s.channel = ? AND s.status IN ({placeholders})
                  AND (s.next_attempt_at IS NULL OR s.next_attempt_at <= ?)
                ORDER BY r.started_at DESC
                LIMIT 5
                """,
                (lane_key, channel_key, *resumable_states, current),
            ).fetchall()
            chosen = self._select_resumable_candidate(rows)
            if chosen is None:
                conn.rollback()
                return None
            row, video_path = chosen
            run_id = uuid.uuid4().hex
            getattr(self, "_bind_lane_lease_locked")(
                conn, run_id, channel_key, row["story_id"], mode, owner, lane_key, current, lease_seconds
            )
            conn.execute(
                """
                UPDATE stories
                SET status = ?, run_id = ?, lane_id = ?, error_msg = NULL,
                    failure_code = 'resumable_delivery', updated_at = CURRENT_TIMESTAMP
                WHERE story_id = ?
                """,
                (JobStatus.PROCESSING.value, run_id, lane_key, row["story_id"]),
            )
            conn.commit()
            result = dict(row)
            result.update(status=JobStatus.PROCESSING.value, run_id=run_id)
            result["resumable_video"] = str(video_path)
            result["previous_run_id"] = str(row["candidate_run_id"])
            return result
