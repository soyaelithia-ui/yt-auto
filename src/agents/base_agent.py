"""Programmatic Agent — Antigravity local harness (Pro quota), CLI-native backend.

Architecture (generic, decoupled):

* The agent executes through the official Antigravity CLI binary (``agy``),
  which authenticates with the active Pro account session (OAuth app-data).
  This is the documented "Modo No Interactivo / Batch desde CLI" and the only
  proven path to use the Pro quota without an API key (verified empirically:
  the google-antigravity SDK local harness requires a real ``GEMINI_API_KEY``).
* When a real ``GEMINI_API_KEY`` is present, the SDK ``Agent`` path is used
  instead (documented SDK mode for API-key/Vertex setups).
* The agent is role-based: ``role_name`` + ``system_instructions`` define the
  behavior; output is structured and declarative in ``task_result.json``.
  Consumers read it passively via ``ProgrammaticAgent.consume()`` — no direct
  LLM/REST calls from the pipeline.
* Resilience: retry with backoff on transient errors, a shared circuit breaker
  (open after repeated failures), and explicit saturation detection so callers
  can fail gracefully instead of burning quota on a hammered account.

CLI:

    python -m src.agents.base_agent --task "describe the release cadence"

Library:

    from src.agents.base_agent import ProgrammaticAgent
    path = ProgrammaticAgent().run("describe the release cadence")
    result = ProgrammaticAgent.consume(path)
"""

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "output"
TASK_RESULT_PATH = OUTPUT_DIR / "task_result.json"


def _resolve_default_app_data_dir() -> Path:
    """Resolve an isolated app data directory for automated project agents.

    NEVER falls back to the host ~/.gemini/antigravity-cli unless explicitly
    set via ANTIGRAVITY_AGENTS_APP_DATA_DIR to prevent contaminating the
    developer's interactive Agy CLI sessions and brain trajectories.
    """
    configured = os.environ.get("ANTIGRAVITY_AGENTS_APP_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    bot_gemini = PROJECT_ROOT / ".bot_home" / ".gemini" / "antigravity-cli"
    if bot_gemini.parent.exists():
        return bot_gemini.resolve()
    secrets_appdata = PROJECT_ROOT / "secrets" / "agents_appdata"
    if secrets_appdata.exists():
        return secrets_appdata.resolve()
    return bot_gemini.resolve()


DEFAULT_APP_DATA_DIR = _resolve_default_app_data_dir()
AGENT_GENERATED_DIR = PROJECT_ROOT / "data" / "worksets" / "generated"
CANONICAL_MODEL = os.environ.get("AGY_MODEL", os.environ.get("GEMINI_MODEL", "gemini-3.7-flash"))
CLI_TIMEOUT_SECONDS = 300

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
    if configured:
        return Path(configured).expanduser()
    found = shutil.which("agy")
    if found:
        return Path(found)
    return PROJECT_ROOT / "agy"


def _resolve_agy_bin_path() -> Path:
    """Resolve the CLI binary honoring AGY_BIN_PATH / AGY_BIN / PATH order."""
    for var in ("AGY_BIN_PATH", "AGY_BIN"):
        configured = os.environ.get(var, "").strip()
        if configured:
            return Path(configured).expanduser()
    return _resolve_agy_bin()


AGY_BIN_PATH = _resolve_agy_bin_path()

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


def is_saturation_text(text: str) -> bool:
    """Return True when a reply/error looks like a saturation signal."""
    if not text:
        return False
    lowered = text.lower()
    return any(p in lowered for p in SATURATION_PATTERNS)


class CircuitBreaker:
    """Shared circuit breaker: opens after N consecutive failures, cools down."""

    _instance: Optional["CircuitBreaker"] = None

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: int = 300) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._open_until = 0.0

    @classmethod
    def instance(cls) -> "CircuitBreaker":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.failure_threshold:
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


class ProgrammaticAgent:
    """Runs tasks through the Antigravity local harness (Pro quota)."""

    def __init__(
        self,
        *,
        system_instructions: str = SYSTEM_INSTRUCTIONS,
        model: str = CANONICAL_MODEL,
        role_name: str = "programmatic-agent",
        task_result_path: Union[Path, str, None] = None,
        app_data_dir: Union[Path, str, None] = None,
        json_schema: Optional[Union[dict, str, Path]] = None,
        use_sdk: bool = False,
    ) -> None:
        self.system_instructions = system_instructions
        self.model = model
        self.role_name = role_name
        self.task_result_path = Path(task_result_path or TASK_RESULT_PATH)
        self.app_data_dir = Path(app_data_dir or DEFAULT_APP_DATA_DIR)
        self.json_schema = json_schema
        self._use_sdk = use_sdk
        self.circuit_breaker = CircuitBreaker.instance()

    def _can_use_sdk(self) -> bool:
        """SDK Agent path is only viable with a real API key."""
        return self._use_sdk and bool(os.environ.get("GEMINI_API_KEY"))

    def _build_config(self):
        """LocalAgentConfig for the optional SDK path (requires real API key)."""
        from google.antigravity import LocalAgentConfig, policy

        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise AgentSaturationError(
                "SDK path requires GEMINI_API_KEY; use the CLI harness backend instead."
            )
        return LocalAgentConfig(
            system_instructions=self.system_instructions,
            model=self.model,
            api_key=api_key,
            policies=[policy.allow_all()],
            workspaces=[str(PROJECT_ROOT)],
            save_dir=str(OUTPUT_DIR / "trajectories"),
            app_data_dir=str(self.app_data_dir),
        )

    async def _chat_async(self, task: str) -> str:
        """SDK Agent invocation (only when a real GEMINI_API_KEY is set)."""
        from google.antigravity import Agent

        async with Agent(self._build_config()) as agent:
            response = await agent.chat(task)
            if hasattr(response, "text"):
                val = response.text
                if callable(val):
                    res = await val()
                    if isinstance(res, list):
                        return "".join(res)
                    return str(res)
                return str(val)
            return str(response) if response is not None else ""

    def _build_cli_cmd(self, task: str) -> list[str]:
        cmd = [
            str(AGY_BIN_PATH),
            "--model", self.model,
            "--effort", "high",
            "--output-format", "json",
            "--dangerously-skip-permissions",
            "-p", f"{self.system_instructions}\n\nTask: {task}",
        ]
        if self.json_schema:
            schema = self.json_schema
            if isinstance(schema, (dict, str)):
                cmd += ["--json-schema", json.dumps(schema) if isinstance(schema, dict) else schema]
            else:
                cmd += ["--json-schema", str(Path(schema).resolve())]
        return cmd

    def _chat_cli_fallback(self, task: str) -> dict[str, Any]:
        """CLI harness invocation; returns parsed JSON envelope."""
        if not AGY_BIN_PATH.is_file():
            raise RuntimeError(f"Antigravity CLI binary not found at {AGY_BIN_PATH}")

        last_exc: Optional[Exception] = None
        cli_env = dict(os.environ)

        # AUD-SESSION-ISOLATION: Isolate agy runtime to .bot_home so automated agent
        # invocations never pollute the developer's interactive ~/.gemini/antigravity-cli sessions.
        bot_home = PROJECT_ROOT / ".bot_home"
        bot_appdata = bot_home / ".gemini" / "antigravity-cli"
        bot_appdata.mkdir(parents=True, exist_ok=True)
        host_appdata = Path.home() / ".gemini" / "antigravity-cli"
        for item in ["antigravity-oauth-token", "settings.json", "bin", "builtin"]:
            src = host_appdata / item
            dst = bot_appdata / item
            if src.exists() and not dst.exists():
                try:
                    dst.symlink_to(src)
                except Exception:
                    pass

        cli_env["HOME"] = str(bot_home)
        cli_env["ANTIGRAVITY_APP_DATA_DIR"] = str(self.app_data_dir)
        cli_env["AGY_APP_DATA_DIR"] = str(self.app_data_dir)
        self.app_data_dir.mkdir(parents=True, exist_ok=True)
        for delay in _RETRY_DELAYS + (0.0,):
            try:
                proc = subprocess.run(
                    self._build_cli_cmd(task),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=CLI_TIMEOUT_SECONDS,
                    cwd=str(PROJECT_ROOT),
                    env=cli_env,
                )
                if proc.returncode != 0:
                    raise RuntimeError(
                        f"AGY CLI execution failed (code {proc.returncode}): "
                        f"{proc.stderr[-400:]}"
                    )
                payload = proc.stdout.strip()
                data: dict[str, Any] = json.loads(payload)
                status = data.get("status", "UNKNOWN")
                if status != "SUCCESS":
                    raise RuntimeError(
                        f"AGY CLI status={status}: {payload[-400:]}"
                    )
                return data
            except json.JSONDecodeError as exc:
                last_exc = exc
            except (RuntimeError, OSError) as exc:
                if is_saturation_text(str(exc)):
                    raise AgentSaturationError(str(exc)) from exc
                last_exc = exc
            if delay:
                time.sleep(delay)

        raise RuntimeError(f"AGY CLI failed after retries: {last_exc}")

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

        if self.circuit_breaker.is_open():
            error = (
                f"Circuit breaker open (cooldown "
                f"{self.circuit_breaker.retry_after()}s). Skipping call."
            )
            status = "error"
        else:
            try:
                if self._can_use_sdk():
                    reply = await self._chat_async(task)
                else:
                    data = self._chat_cli_fallback(task)
                    reply = data.get("response", "")
                    conversation_id = data.get("conversation_id")
                    usage = data.get("usage")
                    duration_seconds = data.get("duration_seconds")
                    structured_output = data.get("structured_output")
            except AgentSaturationError as exc:
                self.circuit_breaker.record_failure()
                error = str(exc)
                status = "saturated"
            except Exception as exc:
                self.circuit_breaker.record_failure()
                error = str(exc)
                status = "error"
            else:
                self.circuit_breaker.record_success()

        doc = self._build_result(
            task, reply, error, status=status,
            conversation_id=conversation_id, usage=usage,
            duration_seconds=duration_seconds,
            structured_output=structured_output,
        )
        self.task_result_path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return self.task_result_path

    def run(self, task: str = DEFAULT_TASK, task_result_path: Optional[Union[Path, str]] = None) -> Path:
        """Execute the agent task synchronously.

        ``task_result_path`` overrides the per-instance result file for this
        call (used by parallel/worker invocations to avoid write races).
        """
        if task_result_path is not None:
            prev, self.task_result_path = self.task_result_path, Path(task_result_path)
            try:
                return asyncio.run(self._run_async(task))
            finally:
                self.task_result_path = prev
        return asyncio.run(self._run_async(task))

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
                "framework": "google-antigravity",
                "connection": "antigravity-cli-harness"
                if not self._can_use_sdk()
                else "google-antigravity-sdk",
                "quota": "pro-active-model",
                "model": self.model,
            },
            "output": {
                "reply": reply,
                "error": error or None,
                "artifact": str(self.task_result_path),
                "conversation_id": conversation_id,
                "usage": usage,
                "cost": cost_info,
                "structured_output": structured_output,
            },
            "cost": cost_info,
            "result": status,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }


def cleanup_ephemeral_sessions(
    app_data_dir: Optional[Union[Path, str]] = None,
    max_age_hours: int = 24,
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
    parser.add_argument("--task", default=DEFAULT_TASK)
    parser.add_argument("--model", default=CANONICAL_MODEL)
    args = parser.parse_args()
    path = ProgrammaticAgent(model=args.model).run(args.task)
    print(f"Result written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
