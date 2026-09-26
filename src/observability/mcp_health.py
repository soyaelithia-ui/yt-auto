"""Automated MCP Server health checker and Single Source of Truth (SSOT) drift monitor.

Validates:
1. Factory importability and runtime MCPServer instantiation via create_mcp_server()
2. SSOT bidirectional parity across code, documentation, and client configs
3. Runtime tool failure rate over rolling windows
"""

from __future__ import annotations

import logging
import os
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

from src.config import DEFAULT_DB_PATH
from src.core.repository.queue import connect

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MCPHealthMetrics:
    overall_status: str  # "HEALTHY" | "DEGRADED" | "BROKEN"
    import_ok: bool
    registered_tools_count: int
    registered_resources_count: int
    registered_prompts_count: int
    parity_ok: bool
    drift_errors: list[str]
    recent_tool_failure_rate: float
    status_reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


class MCPHealthChecker:
    """Evaluates runtime MCP server health and SSOT parity."""

    _CLASS_CACHED_METRICS: MCPHealthMetrics | None = None
    _CLASS_LAST_EVALUATED: float = 0.0

    def __init__(
        self,
        db_path: str | Path | None = None,
        repo_root: Path | None = None,
        cache_ttl_seconds: int = 60,
    ) -> None:
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            env_db = os.environ.get("DEFAULT_DB_PATH")
            self.db_path = Path(env_db) if env_db else Path(DEFAULT_DB_PATH)

        self.repo_root = (
            Path(repo_root).resolve()
            if repo_root is not None
            else Path(__file__).resolve().parent.parent.parent
        )
        if str(self.repo_root) not in sys.path:
            sys.path.insert(0, str(self.repo_root))

        self._cache_ttl = max(1, cache_ttl_seconds)
        self._cached_metrics: MCPHealthMetrics | None = None
        self._last_evaluated: float = 0.0

    def check_factory_importability(self) -> tuple[bool, int, int, int, str | None]:
        """Verify create_mcp_server() imports and instantiates cleanly."""
        try:
            from scripts.verify_mcp_sync import inspect_code_registrations

            code_ok, code_data, code_errors = inspect_code_registrations(self.repo_root)
            if not code_ok:
                err_msg = "; ".join(code_errors) if code_errors else "Failed to inspect code registrations"
                return False, 0, 0, 0, err_msg

            tools_count = len(code_data.get("tools", {}))
            resources_count = len(code_data.get("resources", {}))
            prompts_count = len(code_data.get("prompts", {}))
            return True, tools_count, resources_count, prompts_count, None
        except Exception as exc:
            logger.debug("MCP factory import error: %s", exc)
            return False, 0, 0, 0, str(exc)

    def check_ssot_drift(self) -> tuple[bool, list[str]]:
        """Verify 100% bidirectional parity against docs/MCP.md and canonical specs."""
        try:
            from scripts.verify_mcp_sync import verify_mcp_sync

            parity_ok, _, failures = verify_mcp_sync(self.repo_root)
            return parity_ok, failures
        except Exception as exc:
            logger.debug("MCP drift check error: %s", exc)
            return False, [f"Exception during drift verification: {exc}"]

    def check_tool_failure_rate(self, window_hours: int = 24) -> float:
        """Query system_events for mcp_tool_failure rate over the window."""
        hours = max(1, int(window_hours))
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")

        try:
            with connect(self.db_path, read_only=True) as conn:
                row = conn.execute(
                    """
                    SELECT
                        COUNT(*) as total_events,
                        SUM(CASE WHEN event_type = 'mcp_tool_failure' THEN 1 ELSE 0 END) as failures,
                        SUM(CASE WHEN event_type IN ('mcp_tool_execution', 'mcp_tool_success') THEN 1 ELSE 0 END) as successes
                    FROM system_events
                    WHERE ts >= ? AND (event_type IN ('mcp_tool_failure', 'mcp_tool_execution', 'mcp_tool_success') OR component = 'mcp')
                    """,
                    (cutoff,),
                ).fetchone()

                if not row or int(row["total_events"]) == 0:
                    return 0.0

                failures = int(row["failures"] or 0)
                successes = int(row["successes"] or 0)
                total = failures + successes
                if total == 0:
                    return 1.0 if failures > 0 else 0.0

                return round(failures / float(total), 4)
        except Exception as exc:
            logger.debug("Failed to query tool failure rate: %s", exc)
            return 0.0

    def evaluate_health(
        self, window_hours: int = 24, force: bool = False
    ) -> MCPHealthMetrics:
        """Evaluate MCP server health tri-state resolution."""
        now = time.time()
        cls = type(self)
        if (
            not force
            and cls._CLASS_CACHED_METRICS is not None
            and (now - cls._CLASS_LAST_EVALUATED) < self._cache_ttl
        ):
            return cls._CLASS_CACHED_METRICS

        import_ok, tools_cnt, res_cnt, prm_cnt, import_err = self.check_factory_importability()
        parity_ok, drift_errors = self.check_ssot_drift()
        tool_failure_rate = self.check_tool_failure_rate(window_hours=window_hours)

        if not import_ok:
            overall = "BROKEN"
            reason = import_err or "MCPServer factory import or instantiation failure"
        elif not parity_ok or tool_failure_rate > 0.20:
            overall = "DEGRADED"
            reasons: list[str] = []
            if not parity_ok:
                reasons.append(f"SSOT drift detected ({len(drift_errors)} mismatches)")
            if tool_failure_rate > 0.20:
                reasons.append(f"Tool failure rate elevated ({tool_failure_rate:.1%})")
            reason = "; ".join(reasons)
        else:
            overall = "HEALTHY"
            reason = "Nominal operation with zero SSOT drift and nominal tool error rate."

        metrics = MCPHealthMetrics(
            overall_status=overall,
            import_ok=import_ok,
            registered_tools_count=tools_cnt,
            registered_resources_count=res_cnt,
            registered_prompts_count=prm_cnt,
            parity_ok=parity_ok,
            drift_errors=drift_errors,
            recent_tool_failure_rate=tool_failure_rate,
            status_reason=reason,
        )

        cls._CLASS_CACHED_METRICS = metrics
        cls._CLASS_LAST_EVALUATED = now
        self._cached_metrics = metrics
        self._last_evaluated = now
        return metrics
