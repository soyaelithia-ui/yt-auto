"""Domain contracts shared by the queue, scheduler and provider adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping
from urllib.parse import urlparse


class CanonicalChannel(str, Enum):
    MOKU = "moku"
    AELITHIA = "aelithia"
    SCIFI = "scifi"

    def __str__(self) -> str:
        return self.value

    @classmethod
    def _missing_(cls, value: object):
        val = str(value).lower()
        if val in ("horror", "terror", "canal1", "canal_1", "canal-1", "canal 1"):
            return cls.MOKU
        if val in ("drama", "soy_el_malo", "canal2", "canal_2", "canal-2", "canal 2"):
            return cls.AELITHIA
        return None


CanonicalChannel.HORROR = CanonicalChannel.MOKU
CanonicalChannel.DRAMA = CanonicalChannel.AELITHIA


CHANNEL_ALIASES: Final[Mapping[str, CanonicalChannel]] = {
    "horror": CanonicalChannel.MOKU,
    "drama": CanonicalChannel.AELITHIA,
    "scifi": CanonicalChannel.SCIFI,
    "canal1": CanonicalChannel.MOKU,
    "canal_1": CanonicalChannel.MOKU,
    "canal-1": CanonicalChannel.MOKU,
    "canal 1": CanonicalChannel.MOKU,
    "canal2": CanonicalChannel.AELITHIA,
    "canal_2": CanonicalChannel.AELITHIA,
    "canal-2": CanonicalChannel.AELITHIA,
    "canal 2": CanonicalChannel.AELITHIA,
    "moku": CanonicalChannel.MOKU,
    "terror": CanonicalChannel.MOKU,
    "moku_terror": CanonicalChannel.MOKU,
    "moku-terror": CanonicalChannel.MOKU,
    "moku_shorts": CanonicalChannel.MOKU,
    "scp": CanonicalChannel.MOKU,
    "scp_shorts": CanonicalChannel.MOKU,
    "scp-shorts": CanonicalChannel.MOKU,
    "mokuredit": CanonicalChannel.MOKU,
    "aelithia": CanonicalChannel.AELITHIA,
    "aelithia-c1f": CanonicalChannel.AELITHIA,
    "soy_el_malo": CanonicalChannel.AELITHIA,
    "soy-el-malo": CanonicalChannel.AELITHIA,
    "yo_soy_el_malo": CanonicalChannel.AELITHIA,
    "aita": CanonicalChannel.AELITHIA,
    "aita_drama": CanonicalChannel.AELITHIA,
    "aita-drama": CanonicalChannel.AELITHIA,
    "singularidad_scifi": CanonicalChannel.SCIFI,
    "singularidad-scifi": CanonicalChannel.SCIFI,
}

LEGACY_ALIASES: Final[frozenset[str]] = frozenset({"terror", "soy_el_malo", "scp_shorts", "moku_terror", "aita_drama"})


class DynamicChannelKey(str):
    """Dynamic channel identifier compatible with string and CanonicalChannel enum protocols."""
    @property
    def value(self) -> str:
        return str(self)


def canonical_channel(value: str | CanonicalChannel) -> CanonicalChannel | str:
    """Resolve input aliases but never guess an absent or unknown channel."""
    if isinstance(value, CanonicalChannel):
        return value
    raw_str = str(value or "").strip()
    if any(char in raw_str for char in (";", "&", "|", "`", "$", ">", "<", "\n", "\r")):
        raise ValueError(f"Canal inválido o sospechoso: {value!r}")
    normalized = raw_str.lower()
    if not normalized:
        raise ValueError(f"Canal desconocido o ausente: {value!r}")
    if normalized in CHANNEL_ALIASES:
        return CHANNEL_ALIASES[normalized]
    try:
        from src.core.channel_profile import ChannelProfileRegistry
        norm_cid = ChannelProfileRegistry.normalize_channel_id(normalized)
        if norm_cid in CHANNEL_ALIASES:
            return CHANNEL_ALIASES[norm_cid]
        active_ids = ChannelProfileRegistry.list_active_channel_ids()
        if norm_cid in active_ids or norm_cid in ChannelProfileRegistry._cache:
            return DynamicChannelKey(norm_cid)
    except Exception:
        pass
    raise ValueError(f"Canal desconocido o ausente: {value!r}")


class JobStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PENDING_REVIEW = "PENDING_REVIEW"
    PENDING_APPROVAL = "pending_approval"
    WAITING_LLM_QUOTA = "WAITING_LLM_QUOTA"
    WAITING_IMAGE_QUOTA = "WAITING_IMAGE_QUOTA"
    WAITING_YOUTUBE_LIMIT = "WAITING_YOUTUBE_LIMIT"
    RENDERED = "RENDERED"
    DRIVE_BACKED_UP = "DRIVE_BACKED_UP"
    UPLOAD_UNCONFIRMED = "UPLOAD_UNCONFIRMED"
    PUBLISHED = "PUBLISHED"
    RETRYABLE_FAILED = "RETRYABLE_FAILED"
    PERMANENT_FAILED = "PERMANENT_FAILED"


LEGACY_STATUSES: Final[frozenset[str]] = frozenset({"COMPLETED", "FAILED", "pending_approval"})
ALL_STATUSES: Final[frozenset[str]] = frozenset(
    status.value for status in JobStatus
) | LEGACY_STATUSES


class ProviderKind(str, Enum):
    AGY = "AGY"
    TTS = "TTS"
    DRIVE = "DRIVE"
    YOUTUBE_PLAYWRIGHT = "YOUTUBE_PLAYWRIGHT"
    YOUTUBE_API = "YOUTUBE_API"


class ProviderError(RuntimeError):
    code = "provider_error"
    retryable = True


class QuotaError(ProviderError):
    code = "quota"


class AIProviderChainExhausted(QuotaError):
    code = "ai_provider_chain_exhausted"


class YouTubeQuotaExceededError(QuotaError):
    code = "youtube_quota_exceeded"


class YouTubeUploadLimitError(ProviderError):
    code = "youtube_upload_limit"
    retryable = True


class AuthenticationError(ProviderError):
    code = "authentication"
    retryable = False


class ProviderTimeoutError(ProviderError):
    code = "timeout"


class LeaseOwnershipError(RuntimeError):
    code = "lease_lost"


class AmbiguousUploadError(ProviderError):
    code = "upload_ambiguous"


class ProviderValidationError(ProviderError):
    code = "validation"


class PermanentRejectionError(ProviderError):
    code = "permanent_rejection"
    retryable = False


class ManualInterventionRequired(ProviderError):
    code = "manual_intervention"
    retryable = False


@dataclass(frozen=True)
class PublicationProof:
    video_id: str
    channel: CanonicalChannel
    visibility: str
    title: str
    description: str
    thumbnail_confirmed: bool

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def validate(self) -> None:
        video_id = self.video_id.strip()
        if not video_id or len(video_id) < 6 or any(c.isspace() for c in video_id):
            raise ProviderValidationError("YouTube no devolvió un video_id verificable")
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or parsed.netloc != "www.youtube.com":
            raise ProviderValidationError("URL de publicación inválida")
        if self.visibility != "public":
            raise ProviderValidationError("La publicación de YouTube no está confirmada como pública")
        if not self.title.strip() or not self.description.strip():
            raise ProviderValidationError("Metadatos de publicación incompletos")
        if not self.thumbnail_confirmed:
            raise ProviderValidationError("Miniatura no confirmada")


class SCPCategory(str, Enum):
    ENTITY = "entity"
    MACHINE = "machine"
    OBJECT = "object"
    LOCATION = "location"
    PHENOMENON = "phenomenon"
    DOCUMENT = "document"


class ShotScale(str, Enum):
    ESTABLISHING_WIDE = "establishing_wide"
    MEDIUM_ACTION = "medium_action"
    CLOSEUP_DETAIL = "closeup_detail"
    MACRO_ANOMALY = "macro_anomaly"


@dataclass(frozen=True)
class VisualIdentity:
    primary_category: SCPCategory
    secondary_categories: tuple[SCPCategory, ...]
    scale_and_environment: str
    essential_components: tuple[str, ...]
    functional_sequence: tuple[str, ...]
    forbidden_substitutions: tuple[str, ...]
    differentiating_visual_anchors: tuple[str, ...]
    source_citations: tuple[str, ...]


@dataclass(frozen=True)
class AssetAudit:
    technical_pass: bool
    semantic_state: str  # ACCEPTED, REJECTED, UNCERTAIN, BLOCKED_ASSET
    detected_components: tuple[str, ...]
    confidence_score: float
    rejection_reason: str | None = None


@dataclass(frozen=True)
class SemanticAuditReport:
    dominant_subject: str
    present_elements: tuple[str, ...]
    forbidden_elements_found: tuple[str, ...]
    narrative_match_confidence: float
    decision: str
    rejection_reason: str | None = None


@dataclass(frozen=True)
class SceneSpec:
    scene_index: int
    start_sec: float
    end_sec: float
    script_snippet: str
    primary_subject: str
    required_entities: tuple[str, ...]
    forbidden_entities: tuple[str, ...]
    scene_type: str
    action_or_situation: str
    location: str
    visual_intent: str
    asset_priority: tuple[str, ...]
    search_query: str
    ai_prompt: str
    fallback_strategy: str
    scp_category: SCPCategory = SCPCategory.ENTITY
    shot_scale: ShotScale = ShotScale.MEDIUM_ACTION
    functional_step: str = "general_observation"
    essential_components_required: tuple[str, ...] = ()
    asset_origin: str = "pending"
    asset_url: str = ""
    asset_author: str = ""
    asset_license: str = ""
    asset_hash: str = ""
    validation_state: str = "pending"
    semantic_score: float = 0.0
    rejection_reason: str = ""
    attempt_count: int = 0
    narrative_purpose: str = ""
    entities: tuple[str, ...] = ()
    action: str = ""
    environment: str = ""
    lighting: str = ""
    shot_type: str = ""
    prohibited_elements: tuple[str, ...] = ()
    continuity_ref: str = ""
    camera_motion: str = "slow_zoom_in"



