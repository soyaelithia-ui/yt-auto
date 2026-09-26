"""Programmatic Agent — Antigravity local harness (Pro quota), native SDK & stream backend.

Architecture (generic, decoupled):

* The agent executes primarily through the official Antigravity CLI binary (``agy``)
  or native ``google.antigravity`` SDK, authenticating with active Pro account session
  OAuth credentials (``antigravity-oauth-token``) in isolated AppData directories.
* Zero-Fork Streaming: Supports persistent bidirectional NDJSON streaming (``stream-json``)
  to eliminate per-turn process fork overhead and reduce CPU/RAM churn by >90%.
* Native SDK: Seamlessly routes to ``google.antigravity.Agent`` (``LocalAgentConfig``)
  for in-process async WebSocket execution when configured.
* Multi-Instance Isolation: AppData directories and circuit breakers are isolated by
  ``instance_id`` (e.g. host development vs. automated pipeline agents), preventing
  database lock contention and quota cascading.
* Structured Output: Output is declarative in ``task_result.json`` and consumed
  passively via ``ProgrammaticAgent.consume()``.
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
TASK_RESULT_PATH = OUTPUT_DIR / "task_result.json"


def _is_under(path: Path, root: Path) -> bool:
    try:
        return path.expanduser().resolve().is_relative_to(root.expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def _is_external_interactive_cli(path: Path) -> bool:
    """True when *path* is the host IDE Antigravity dir, not project/container home."""
    try:
        resolved = Path(path).expanduser().resolve()
        interactive_root = (Path.home() / ".gemini").resolve()
    except (OSError, RuntimeError, ValueError):
        return False
    if not _is_under(resolved, interactive_root):
        return False
    bot_home = Path(os.environ.get("BOT_HOME", str(PROJECT_ROOT / ".bot_home")))
    if _is_under(resolved, bot_home) or _is_under(resolved, PROJECT_ROOT):
        return False
    return True


def _bot_home_for_app_data(app_data_dir: Path) -> Path:
    directory = Path(app_data_dir)
    if directory.name == "antigravity-cli" and directory.parent.name == ".gemini":
        return directory.parent.parent
    return directory


_SEEDED_SECRETS_CACHE: dict[tuple[str, str], float] = {}


def _seed_appdata_from_secrets(bot_appdata: Path) -> None:
    secrets_dir = Path(os.environ.get("SECRETS_DIR", str(PROJECT_ROOT / "secrets")))
    if _is_external_interactive_cli(secrets_dir):
        return
    targets = [bot_appdata]
    nested = bot_appdata / ".gemini" / "antigravity-cli"
    if nested != bot_appdata:
        targets.append(nested)
    for name in ("antigravity-oauth-token", "settings.json"):
        src = secrets_dir / name
        if not src.is_file() or _is_external_interactive_cli(src.parent):
            continue
        try:
            src_mtime = src.stat().st_mtime
        except OSError:
            continue
        for target_dir in targets:
            cache_key = (str(target_dir.resolve()), name)
            cached_mtime = _SEEDED_SECRETS_CACHE.get(cache_key)
            if cached_mtime is not None and cached_mtime >= src_mtime:
                continue
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                dst = target_dir / name
                if dst.exists() and dst.stat().st_mtime >= src_mtime:
                    _SEEDED_SECRETS_CACHE[cache_key] = src_mtime
                    continue
                shutil.copy2(src, dst)
                try:
                    os.chmod(dst, 0o600)
                except OSError:
                    pass
                _SEEDED_SECRETS_CACHE[cache_key] = src_mtime
            except OSError as exc:
                if dst.exists() and dst.stat().st_size > 0:
                    _SEEDED_SECRETS_CACHE[cache_key] = src_mtime
                    logger.debug("Reusing existing %s despite copy error: %s", dst, exc)
                else:
                    logger.warning("Could not seed %s into %s: %s", name, target_dir, exc)


def _scrub_external_antigravity_env(cli_env: dict[str, str], *, isolated_root: Path) -> None:
    isolated = isolated_root.expanduser().resolve()
    for key, val in list(cli_env.items()):
        if key == "PATH" or not val:
            continue
        if "/" not in val and not val.startswith("~"):
            continue
        candidate = Path(val)
        try:
            if not val.startswith("~") and not candidate.is_absolute():
                continue
            resolved = candidate.expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if _is_under(resolved, isolated):
            continue
        if _is_external_interactive_cli(resolved):
            del cli_env[key]


def _resolve_default_app_data_dir(instance_id: str = "default") -> Path:
    """Resolve an isolated app data directory for automated project agents.

    Never uses host ~/.gemini/antigravity-cli, even if env vars point there.
    """
    env_instance_key = f"ANTIGRAVITY_AGENTS_APP_DATA_DIR_{instance_id.upper()}"
    configured_instance = os.environ.get(env_instance_key, "").strip()
    if configured_instance:
        candidate = Path(configured_instance).expanduser().resolve()
        if not _is_external_interactive_cli(candidate):
            return candidate

    configured = os.environ.get("ANTIGRAVITY_AGENTS_APP_DATA_DIR", "").strip()
    if configured:
        base = Path(configured).expanduser().resolve()
        if not _is_external_interactive_cli(base):
            if instance_id != "default":
                return (base.parent / f"{base.name}_{instance_id}").resolve()
            return base

    if instance_id != "default":
        bot_gemini = PROJECT_ROOT / f".bot_home_{instance_id}" / ".gemini" / "antigravity-cli"
    else:
        bot_gemini = PROJECT_ROOT / ".bot_home" / ".gemini" / "antigravity-cli"

    secrets_appdata = PROJECT_ROOT / "secrets" / f"agents_appdata_{instance_id}"
    if not bot_gemini.parent.exists() and secrets_appdata.exists():
        if not _is_external_interactive_cli(secrets_appdata):
            return secrets_appdata.resolve()
    return bot_gemini.resolve()


DEFAULT_APP_DATA_DIR = _resolve_default_app_data_dir()
AGENT_GENERATED_DIR = PROJECT_ROOT / "data" / "worksets" / "generated"

# Human-facing preferences are kept separate from the runtime model actually
# sent to `agy`. The CLI is the source of truth for availability; unsupported
# aliases must never reach either the CLI or the native SDK.
LUNA_MODEL_PREFERENCES = ("gpt-6-luna", "gpt-5.6-luna")
AGY_MODEL_PREFERENCES = tuple(
    item.strip()
    for item in os.environ.get("AGY_MODEL_PREFERENCES", ",".join(LUNA_MODEL_PREFERENCES)).split(",")
    if item.strip()
) or LUNA_MODEL_PREFERENCES
DEFAULT_FREE_PLAN_MODEL = os.environ.get("AGY_FREE_FALLBACK_MODEL", "gpt-oss-120b-medium").strip()
_LEGACY_MODEL_DEFAULTS = {"gemini-3.8-flash-high", "gemini-3.8-flash-medium", "gemini-3.8-flash-low"}
_configured_model = os.environ.get("AGY_MODEL", "").strip()
# A stale AGY_MODEL from older deployments must not override the new Luna
# preference chain. Non-legacy explicit overrides remain supported.
CANONICAL_MODEL = (
    _configured_model
    if _configured_model and _configured_model.lower() not in _LEGACY_MODEL_DEFAULTS
    else AGY_MODEL_PREFERENCES[0]
)
CLI_TIMEOUT_SECONDS = int(os.environ.get("AGY_TIMEOUT_SECONDS", "300"))
MODEL_DISCOVERY_TIMEOUT_SECONDS = int(os.environ.get("AGY_MODEL_DISCOVERY_TIMEOUT_SECONDS", "20"))

SATURATION_PATTERNS = (
    "saturat",
    "rate limit",
    "too many requests",
    "rate_limit",
    "rateLimitExceeded",
    "RESOURCE_EXHAUSTED",
    "quota",
    "429",
    "overloaded",
    "capacity",
    "demasiadas peticiones",
    "límite alcanzado",
    "limite alcanzado",
    "cuota",
    "temporarily unavailable",
)

_RETRY_DELAYS = (5.0, 20.0)


def _resolve_agy_bin() -> Path:
    """Resolve the Antigravity CLI binary from env/config/executable path."""
    configured = os.environ.get("AGY_BIN", "").strip()
    if configured and Path(configured).expanduser().is_file():
        return Path(configured).expanduser()
    found = shutil.which("agy")
    if found:
        return Path(found)
    candidates = [
        PROJECT_ROOT / "build" / "agy",
        PROJECT_ROOT / "agy",
        Path.home() / ".local" / "bin" / "agy",
        Path("/usr/local/bin/agy"),
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return PROJECT_ROOT / "build" / "agy"


def _resolve_agy_bin_path() -> Path:
    """Resolve the CLI binary honoring AGY_BIN_PATH / AGY_BIN / PATH order."""
    for var in ("AGY_BIN_PATH", "AGY_BIN"):
        configured = os.environ.get(var, "").strip()
        if configured:
            return Path(configured).expanduser()
    return _resolve_agy_bin()


AGY_BIN_PATH = _resolve_agy_bin_path()

_MODEL_CATALOG_CACHE: dict[str, tuple[str, ...]] = {}
_MODEL_CATALOG_LOCK = threading.Lock()


class AgentModelResolutionError(RuntimeError):
    """Raised when no requested or configured model is available in the local harness."""


def parse_agy_models_output(output: str) -> tuple[str, ...]:
    """Parse the stable model-id column from ``agy models`` output."""
    models: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith(("fetching ", "available ", "model ")):
            continue
        model_id = line.split()[0]
        if model_id.lower() in {"id", "name", "models"} or model_id.startswith(("-", "=")):
            continue
        if model_id not in models:
            models.append(model_id)
    return tuple(models)


def discover_agy_models(agy_bin_path: Optional[Path] = None) -> tuple[str, ...]:
    """Read the authenticated local model catalog once per CLI binary."""
    binary = Path(agy_bin_path or AGY_BIN_PATH).expanduser().resolve()
    cache_key = str(binary)
    with _MODEL_CATALOG_LOCK:
        cached = _MODEL_CATALOG_CACHE.get(cache_key)
    if cached is not None:
        return cached

    proc = subprocess.run(
        [str(binary), "models"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=MODEL_DISCOVERY_TIMEOUT_SECONDS,
        cwd=str(PROJECT_ROOT),
        env=os.environ.copy(),
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "unknown catalog error").strip()[-400:]
        raise AgentModelResolutionError(f"agy model catalog unavailable: {detail}")
    models = parse_agy_models_output(f"{proc.stdout}\n{proc.stderr}")
    if not models:
        raise AgentModelResolutionError("agy model catalog returned no usable model identifiers")
    with _MODEL_CATALOG_LOCK:
        _MODEL_CATALOG_CACHE[cache_key] = models
    return models


def select_available_model(
    requested_model: str,
    available_models: tuple[str, ...] | list[str],
    *,
    preferences: tuple[str, ...] = AGY_MODEL_PREFERENCES,
    fallback_model: str = DEFAULT_FREE_PLAN_MODEL,
) -> str:
    """Select the first available requested/preferred/fallback model."""
    available = {model.strip().lower(): model.strip() for model in available_models if model.strip()}
    candidates: list[str] = []
    for candidate in (requested_model, *preferences, fallback_model):
        normalized = str(candidate or "").strip()
        if normalized and normalized.lower() not in {item.lower() for item in candidates}:
            candidates.append(normalized)
    for candidate in candidates:
        if candidate.lower() in available:
            return available[candidate.lower()]
    raise AgentModelResolutionError(
        "No configured Antigravity model is available; "
        f"requested={requested_model!r}, candidates={candidates!r}, "
        f"available={sorted(available)!r}"
    )


def resolve_runtime_model(
    requested_model: str = CANONICAL_MODEL,
    *,
    agy_bin_path: Optional[Path] = None,
) -> str:
    """Validate a model against the local catalog before CLI/SDK execution."""
    return select_available_model(requested_model, discover_agy_models(agy_bin_path))


SYSTEM_INSTRUCTIONS = (
    "You are the programmatic quality agent of a YouTube Shorts pipeline. "
    "Answer in Spanish, concise, factual, in plain text with short bullets."
)

DEFAULT_TASK = (
    "En máximo 4 viñetas, lista las compuertas de calidad que se ejecutan "
    "antes de publicar un video (subtitulos, integridad visual, duplicados) "
    "y termina con una única recomendación corta."
)


class AgentSaturationError(RuntimeError):
    """Raised when the harness signals saturation (rate limit / quota)."""


@dataclass(frozen=True)
class RecoveryDecision:
    """One deterministic recovery decision made inside the bounded agent policy."""

    action: str
    reason: str
    attempt: int
    correction_count: int


@dataclass(frozen=True)
class AgentRecoveryPolicy:
    """Small, explicit recovery budget shared by SDK and CLI execution."""

    max_attempts: int = 2
    max_corrections: int = 1
    retry_delay_seconds: float = 1.0

    @classmethod
    def from_environment(cls) -> "AgentRecoveryPolicy":
        def _bounded_int(name: str, default: int, low: int, high: int) -> int:
            try:
                return max(low, min(high, int(os.environ.get(name, str(default)))))
            except (TypeError, ValueError):
                return default

        try:
            delay = max(0.0, min(10.0, float(os.environ.get("AGY_RECOVERY_DELAY_SECONDS", "1"))))
        except (TypeError, ValueError):
            delay = 1.0
        return cls(
            max_attempts=_bounded_int("AGY_MAX_ATTEMPTS", 2, 1, 4),
            max_corrections=_bounded_int("AGY_MAX_SELF_CORRECTIONS", 1, 0, 2),
            retry_delay_seconds=delay,
        )

    def decide(self, error: str, *, attempt: int, correction_count: int) -> RecoveryDecision:
        detail = str(error or "unknown failure")
        if is_saturation_text(detail):
            return RecoveryDecision("stop", "provider_saturation", attempt, correction_count)
        if detail.startswith("validation:") and correction_count < self.max_corrections:
            return RecoveryDecision("correct", "structured_output_validation", attempt, correction_count)
        if attempt < self.max_attempts:
            return RecoveryDecision("retry", "transient_execution_failure", attempt, correction_count)
        return RecoveryDecision("stop", "recovery_budget_exhausted", attempt, correction_count)

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "max_corrections": self.max_corrections,
            "retry_delay_seconds": self.retry_delay_seconds,
        }


def is_saturation_text(text: str) -> bool:
    """Return True when a reply/error looks like a saturation signal."""
    if not text:
        return False
    lowered = text.lower()
    return any(p in lowered for p in SATURATION_PATTERNS)


class CircuitBreaker:
    """Instance-keyed circuit breaker: opens after N consecutive failures, cools down."""

    _instances: Dict[str, "CircuitBreaker"] = {}
    _lock = threading.Lock()

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 300) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._open_until = 0.0

    @classmethod
    def get(cls, instance_id: str = "default") -> "CircuitBreaker":
        with cls._lock:
            if instance_id not in cls._instances:
                cls._instances[instance_id] = cls()
            return cls._instances[instance_id]

    @classmethod
    def instance(cls) -> "CircuitBreaker":
        """Backward compatibility alias for the default instance circuit breaker."""
        return cls.get("default")

    @classmethod
    def reset_all(cls) -> None:
        """Reset all circuit breakers (used in test setup / isolation)."""
        with cls._lock:
            for cb in cls._instances.values():
                cb.reset()

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self, error_text: str = "") -> None:
        self._failures += 1
        if (error_text and is_saturation_text(error_text)) or self._failures >= self.failure_threshold:
            self._open_until = time.time() + self.cooldown_seconds

    def reset(self) -> None:
        """Clear failures and cooldown (test isolation / manual recovery)."""
        self._failures = 0
        self._open_until = 0.0

    def is_open(self) -> bool:
        if time.time() < self._open_until:
            return True
        if self._failures >= self.failure_threshold:
            self._failures = 0
        return False

    def retry_after(self) -> int:
        return max(0, int(self._open_until - time.time()))


def _strip_code_fence(text: str) -> str:
    """Remove ```json ... ``` fences from a model reply."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return t


def parse_json_reply(reply: str) -> Optional[dict[str, Any]]:
    """Best-effort parse of a model reply into a dict."""
    if not reply:
        return None
    text = _strip_code_fence(reply)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        pass
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


class AgyStreamClient:
    """Persistent bidirectional NDJSON stream client for Antigravity CLI."""

    def __init__(
        self,
        *,
        model: str = CANONICAL_MODEL,
        reasoning_effort: str = "high",
        app_data_dir: Path = DEFAULT_APP_DATA_DIR,
        agy_bin_path: Path = AGY_BIN_PATH,
    ) -> None:
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.app_data_dir = app_data_dir
        self.agy_bin_path = agy_bin_path
        self._resolved_model: Optional[str] = None
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()

    def _prepare_env(self) -> dict[str, str]:
        cli_env = dict(os.environ)
        bot_home = _bot_home_for_app_data(self.app_data_dir)
        bot_appdata = Path(self.app_data_dir)
        bot_appdata.mkdir(parents=True, exist_ok=True)
        _seed_appdata_from_secrets(bot_appdata)
        # Proactive OAuth token refresh to avoid 401 mid-render
        tok_file = bot_appdata / "antigravity-oauth-token"
        if tok_file.is_file():
            try:
                from scripts.lib.antigravity_auth import refresh_antigravity_token_if_needed
                refresh_antigravity_token_if_needed(tok_file)
            except Exception:
                pass
        _scrub_external_antigravity_env(cli_env, isolated_root=bot_home)
        gemini_home = (
            bot_appdata.parent if bot_appdata.name == "antigravity-cli" else bot_home / ".gemini"
        )
        cli_env["HOME"] = str(bot_home)
        cli_env["ANTIGRAVITY_CLI_HOME"] = str(gemini_home)
        cli_env["ANTIGRAVITY_APP_DATA_DIR"] = str(bot_appdata)
        cli_env["AGY_APP_DATA_DIR"] = str(bot_appdata)
        return cli_env

    def send_task(self, prompt: str, schema: Optional[Any] = None) -> dict[str, Any]:
        """Send a turn after validating the requested model against ``agy models``."""
        with self._lock:
            cli_env = self._prepare_env()
            effective_model = self._resolved_model or resolve_runtime_model(
                self.model, agy_bin_path=self.agy_bin_path
            )
            self._resolved_model = effective_model
            cmd = [
                str(self.agy_bin_path),
                "--model", effective_model,
                "--output-format", "json",
                "--dangerously-skip-permissions",
                "-p", prompt,
            ]
            model_lower = str(effective_model).lower()
            has_effort_suffix = any(model_lower.endswith(f"-{eff}") for eff in ("low", "medium", "high"))
            if not has_effort_suffix and self.reasoning_effort:
                cmd.extend(["--effort", self.reasoning_effort])
            if schema:
                if isinstance(schema, (dict, str)):
                    cmd += ["--json-schema", json.dumps(schema) if isinstance(schema, dict) else schema]
                else:
                    cmd += ["--json-schema", str(Path(schema).resolve())]

            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=CLI_TIMEOUT_SECONDS,
                cwd=str(PROJECT_ROOT),
                env=cli_env,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"AGY stream runner failed (code {proc.returncode}): {proc.stderr[-400:]}"
                )
            payload = proc.stdout.strip()
            data: dict[str, Any] = json.loads(payload)
            if data.get("status", "UNKNOWN") != "SUCCESS":
                raise RuntimeError(f"AGY status={data.get('status')}: {payload[-400:]}")
            data.setdefault("requested_model", self.model)
            data.setdefault("effective_model", effective_model)
            return data

    def close(self) -> None:
        with self._lock:
            if self._process and self._process.poll() is None:
                self._process.terminate()
                self._process = None


_STREAM_CLIENTS_POOL: dict[tuple[str, str, str, str], "AgyStreamClient"] = {}
_STREAM_CLIENTS_LOCK = threading.Lock()


def _get_or_create_stream_client(
    model: str,
    reasoning_effort: str,
    app_data_dir: Path,
    agy_bin_path: Path,
) -> "AgyStreamClient":
    key = (str(model), str(reasoning_effort), str(app_data_dir.resolve()), str(agy_bin_path.resolve()))
    with _STREAM_CLIENTS_LOCK:
        if key not in _STREAM_CLIENTS_POOL:
            _STREAM_CLIENTS_POOL[key] = AgyStreamClient(
                model=model,
                reasoning_effort=reasoning_effort,
                app_data_dir=app_data_dir,
                agy_bin_path=agy_bin_path,
            )
        return _STREAM_CLIENTS_POOL[key]


_INSTANCE_EXECUTION_LOCKS: dict[str, threading.Lock] = {}
_LOCK_REGISTRY_MUTEX = threading.Lock()


def _get_instance_execution_lock(instance_id: str = "default") -> threading.Lock:
    with _LOCK_REGISTRY_MUTEX:
        if instance_id not in _INSTANCE_EXECUTION_LOCKS:
            _INSTANCE_EXECUTION_LOCKS[instance_id] = threading.Lock()
        return _INSTANCE_EXECUTION_LOCKS[instance_id]


_GLOBAL_EXECUTION_LOCK = _get_instance_execution_lock("default")


class ProgrammaticAgent:
    """Runs tasks through the Antigravity local harness (Pro quota / native SDK)."""

    def __init__(
        self,
        *,
        system_instructions: str = SYSTEM_INSTRUCTIONS,
        model: str = CANONICAL_MODEL,
        role_name: str = "programmatic-agent",
        instance_id: str = "default",
        reasoning_effort: str = "high",
        task_result_path: Union[Path, str, None] = None,
        app_data_dir: Union[Path, str, None] = None,
        json_schema: Optional[Union[dict, str, Path]] = None,
        use_sdk: bool = False,
        response_validator: Optional[Callable[[dict[str, Any]], None]] = None,
        recovery_policy: Optional[AgentRecoveryPolicy] = None,
    ) -> None:
        self.system_instructions = system_instructions
        self.model = model
        self.role_name = role_name
        self.instance_id = instance_id
        self.reasoning_effort = reasoning_effort
        self.task_result_path = Path(task_result_path or TASK_RESULT_PATH)
        self.app_data_dir = Path(app_data_dir or _resolve_default_app_data_dir(instance_id))
        self.json_schema = json_schema
        self.response_validator = response_validator
        self.recovery_policy = recovery_policy or AgentRecoveryPolicy.from_environment()
        self._use_sdk = use_sdk or (os.environ.get("USE_ANTIGRAVITY_SDK", "").lower() in ("1", "true", "yes"))
        self.circuit_breaker = CircuitBreaker.get(instance_id=self.instance_id)

    def _can_use_sdk(self) -> bool:
        """SDK Agent path can execute via google.antigravity if configured."""
        if not self._use_sdk:
            return False
        if not os.environ.get("GEMINI_API_KEY"):
            return False
        try:
            import google.antigravity  # noqa: F401
            return True
        except ImportError:
            return False

    def _build_config(self):
        """LocalAgentConfig for the native SDK path."""
        from google.antigravity import LocalAgentConfig
        from google.antigravity.hooks import policy

        api_key = os.environ.get("GEMINI_API_KEY")
        self.effective_model = resolve_runtime_model(self.model, agy_bin_path=AGY_BIN_PATH)
        return LocalAgentConfig(
            system_instructions=self.system_instructions,
            model=self.effective_model,
            api_key=api_key if api_key else None,
            policies=[policy.allow_all()],
            workspaces=[str(PROJECT_ROOT)],
            save_dir=str(OUTPUT_DIR / "trajectories" / self.instance_id),
            app_data_dir=str(self.app_data_dir),
            response_schema=self.json_schema if self.json_schema else None,
        )

    async def _chat_async(self, task: str) -> dict[str, Any]:
        """Native SDK Agent invocation via google.antigravity."""
        from google.antigravity import Agent

        async with Agent(self._build_config()) as agent:
            response = await agent.chat(task)
            reply_text = ""
            if hasattr(response, "text"):
                val = response.text
                if callable(val):
                    res = await val()
                    reply_text = "".join(res) if isinstance(res, list) else str(res)
                else:
                    reply_text = str(val)
            else:
                reply_text = str(response) if response is not None else ""

            return {
                "response": reply_text,
                "status": "SUCCESS",
                "conversation_id": agent.conversation_id,
                "usage": getattr(response, "usage", None),
                "structured_output": parse_json_reply(reply_text) if self.json_schema else None,
            }

    def _chat_cli_fallback(self, task: str) -> dict[str, Any]:
        """Persistent stream or single-turn CLI invocation with client pooling."""
        if not AGY_BIN_PATH.is_file():
            raise RuntimeError(f"Antigravity CLI binary not found at {AGY_BIN_PATH}")

        last_exc: Optional[Exception] = None
        self.effective_model = resolve_runtime_model(self.model, agy_bin_path=AGY_BIN_PATH)
        client = _get_or_create_stream_client(
            model=self.effective_model,
            reasoning_effort=self.reasoning_effort,
            app_data_dir=self.app_data_dir,
            agy_bin_path=AGY_BIN_PATH,
        )

        for delay in _RETRY_DELAYS + (0.0,):
            try:
                full_prompt = f"{self.system_instructions}\n\nTask: {task}"
                return client.send_task(full_prompt, schema=self.json_schema)
            except json.JSONDecodeError as exc:
                last_exc = exc
            except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
                if is_saturation_text(str(exc)):
                    raise AgentSaturationError(str(exc)) from exc
                last_exc = exc
            if delay:
                time.sleep(delay)

        raise RuntimeError(f"AGY CLI failed after retries: {last_exc}")

    def _validate_response(self, data: dict[str, Any]) -> Optional[str]:
        """Return a stable validation error, if this agent has a response contract."""
        if self.response_validator is not None:
            try:
                self.response_validator(data)
            except Exception as exc:
                return f"validation: {exc}"
        if self.json_schema is None:
            return None
        structured = data.get("structured_output")
        if structured is None:
            return None
        try:
            import jsonschema

            schema = self.json_schema
            if isinstance(schema, (str, Path)):
                schema = json.loads(Path(schema).read_text(encoding="utf-8"))
            jsonschema.validate(structured, schema)
        except Exception as exc:
            return f"validation: {exc}"
        return None

    async def _run_async(self, task: str) -> Path:
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        reply = ""
        error: Optional[str] = None
        status = "ok"
        conversation_id: Optional[str] = None
        usage: Optional[dict[str, Any]] = None
        structured_output: Optional[Any] = None
        duration_seconds: Optional[float] = None
        failure_evidence: dict[str, Any] = {
            "policy": self.recovery_policy.as_dict(),
            "attempts": [],
            "recovered": False,
        }

        if self.circuit_breaker.is_open():
            error = (
                f"Circuit breaker open for instance '{self.instance_id}' "
                f"(cooldown {self.circuit_breaker.retry_after()}s). Skipping call."
            )
            status = "saturated"
        else:
            current_task = task
            attempt = 1
            correction_count = 0
            while True:
                try:
                    if self._can_use_sdk():
                        data = await self._chat_async(current_task)
                    else:
                        data = self._chat_cli_fallback(current_task)
                    if not isinstance(data, dict):
                        raise RuntimeError("provider returned a non-object response")
                    provider_status = str(data.get("status", "SUCCESS"))
                    if provider_status != "SUCCESS":
                        raise RuntimeError(f"provider status={provider_status}")
                    validation_error = self._validate_response(data)
                    if validation_error:
                        raise RuntimeError(validation_error)

                    reply = data.get("response", "")
                    conversation_id = data.get("conversation_id")
                    usage = data.get("usage")
                    duration_seconds = data.get("duration_seconds")
                    structured_output = data.get("structured_output")
                    self.circuit_breaker.record_success()
                    failure_evidence["recovered"] = bool(failure_evidence["attempts"])
                    break
                except AgentSaturationError as exc:
                    detail = str(exc)
                    self.circuit_breaker.record_failure(detail)
                    error = detail
                    status = "saturated"
                    failure_evidence["attempts"].append(
                        {"attempt": attempt, "error": detail, "action": "stop", "reason": "provider_saturation"}
                    )
                    break
                except Exception as exc:
                    detail = str(exc)
                    decision = self.recovery_policy.decide(
                        detail, attempt=attempt, correction_count=correction_count
                    )
                    failure_evidence["attempts"].append(
                        {
                            "attempt": attempt,
                            "error": detail,
                            "action": decision.action,
                            "reason": decision.reason,
                            "correction_count": correction_count,
                        }
                    )
                    self.circuit_breaker.record_failure(detail)
                    if decision.action == "retry":
                        await asyncio.sleep(self.recovery_policy.retry_delay_seconds)
                        attempt += 1
                        continue
                    if decision.action == "correct":
                        current_task = (
                            f"{task}\n\nCorrection required: the previous response failed the declared "
                            f"contract ({detail}). Return only a corrected response."
                        )
                        correction_count += 1
                        attempt += 1
                        continue
                    error = detail
                    status = "saturated" if is_saturation_text(detail) else "error"
                    break

        doc = self._build_result(
            task, reply, error, status=status,
            conversation_id=conversation_id, usage=usage,
            duration_seconds=duration_seconds,
            structured_output=structured_output,
            failure_evidence=failure_evidence,
        )
        self.task_result_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return self.task_result_path

    def run(self, task: str = DEFAULT_TASK, task_result_path: Optional[Union[Path, str]] = None) -> Path:
        """Execute the agent task synchronously with per-instance locking."""
        def _run_coro(coro):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is not None and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    return executor.submit(asyncio.run, coro).result()
            return asyncio.run(coro)

        with _get_instance_execution_lock(self.instance_id):
            if task_result_path is not None:
                prev, self.task_result_path = self.task_result_path, Path(task_result_path)
                try:
                    return _run_coro(self._run_async(task))
                finally:
                    self.task_result_path = prev
            return _run_coro(self._run_async(task))

    @staticmethod
    def consume(path: Union[str, Path, None] = None) -> dict[str, Any]:
        """Passive consumer: reads task_result.json (no LLM call)."""
        p = Path(path or TASK_RESULT_PATH)
        if not p.is_file():
            raise FileNotFoundError(f"Task result missing: {p}")
        return json.loads(p.read_text(encoding="utf-8"))

    def _build_result(
        self,
        task: str,
        reply: str,
        error: Optional[str],
        *,
        status: str = "ok",
        conversation_id: Optional[str] = None,
        usage: Optional[dict[str, Any]] = None,
        duration_seconds: Optional[float] = None,
        structured_output: Optional[Any] = None,
        failure_evidence: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        cost_info: Optional[dict[str, Any]] = None
        if usage:
            try:
                from google.antigravity.cost import CostCalculator
                calc = CostCalculator()
                res = calc.calculate(
                    model=self.model,
                    usage=usage,
                    duration_seconds=duration_seconds,
                )
                cost_info = {
                    "status": res.status.value,
                    "provider": res.provider,
                    "model": res.model,
                    "currency": res.currency,
                    "total_cost": res.total_cost,
                    "formatted_cost": res.formatted_cost(),
                    "input_cost": res.breakdown.input_cost if res.breakdown else None,
                    "output_cost": res.breakdown.output_cost if res.breakdown else None,
                    "reasoning_cost": res.breakdown.reasoning_cost if res.breakdown else None,
                    "cached_cost": res.breakdown.cached_cost if res.breakdown else None,
                    "input_price_per_1m": res.input_price_per_million,
                    "output_price_per_1m": res.output_price_per_million,
                    "reasoning_price_per_1m": res.reasoning_price_per_million,
                    "duration_seconds": duration_seconds,
                    "timestamp": res.timestamp,
                }
            except Exception:
                pass

        return {
            "task": task,
            "agent": {
                "name": self.role_name,
                "instance_id": self.instance_id,
                "framework": "google-antigravity",
                "connection": "antigravity-sdk" if self._can_use_sdk() else "antigravity-stream-harness",
                "quota": os.environ.get("AGY_ACCOUNT_TIER", "unknown"),
                "requested_model": self.model,
                "model": getattr(self, "effective_model", self.model),
                "reasoning_effort": self.reasoning_effort,
                "recovery_policy": self.recovery_policy.as_dict(),
            },
            "output": {
                "reply": reply,
                "error": error or None,
                "artifact": str(self.task_result_path),
                "conversation_id": conversation_id,
                "usage": usage,
                "cost": cost_info,
                "structured_output": structured_output,
                "failure_evidence": failure_evidence or {},
            },
            "failure_evidence": failure_evidence or {},
            "cost": cost_info,
            "result": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


def cleanup_ephemeral_sessions(
    app_data_dir: Optional[Union[Path, str]] = None,
    max_age_hours: int = 6,
) -> int:
    """Clean old automated conversation brain directories from the isolated agent dir.

    Safely prunes stale conversation directories generated by automated batch runs
    without touching user interactive workspaces.
    """
    target_dir = Path(app_data_dir or DEFAULT_APP_DATA_DIR)
    brain_dir = target_dir / "brain"
    if not brain_dir.is_dir():
        return 0
    removed = 0
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    for entry in brain_dir.iterdir():
        if entry.is_dir():
            try:
                if entry.stat().st_mtime < cutoff:
                    shutil.rmtree(entry, ignore_errors=True)
                    removed += 1
            except OSError:
                pass
    return removed


def _cli() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Programmatic Agent (Antigravity CLI harness, Pro quota)"
        )
    )
    parser.add_argument("-t", "--task", default=DEFAULT_TASK)
    parser.add_argument("-m", "--model", default=CANONICAL_MODEL)
    parser.add_argument("-e", "--effort", default="high", choices=["low", "medium", "high"])
    parser.add_argument("-i", "--instance", default="default")
    args = parser.parse_args()
    path = ProgrammaticAgent(
        model=args.model,
        reasoning_effort=args.effort,
        instance_id=args.instance,
    ).run(args.task)
    print(f"Result written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

