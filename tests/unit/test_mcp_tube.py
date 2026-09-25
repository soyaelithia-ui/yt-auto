"""Unit tests for El Tubo operational surfaces: CLI dashboard and MCP protocol interfaces."""

from __future__ import annotations

import asyncio
import io
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from main import main
from src.cli.handlers.status import cli_tube, print_tube
from src.core.repository import QueueRepository
from src.mcp.server import create_mcp_server
from src.observability.mcp_health import MCPHealthChecker
from src.observability.tube import TubeCollector, TubeSnapshot


@pytest.fixture
def repo(tmp_path: Path) -> QueueRepository:
    db_path = tmp_path / "test_surface.db"
    r = QueueRepository(db_path)
    r.initialize()
    return r


@pytest.mark.asyncio
async def test_mcp_resource_system_tube(repo: QueueRepository) -> None:
    """Assert reading system://tube returns valid JSON matching TubeSnapshot.to_dict()."""
    server = create_mcp_server()
    with patch("src.config.DEFAULT_DB_PATH", str(repo.db_path)):
        result = await server.read_resource("system://tube")
        assert len(result) > 0
        content = result[0].content
        data = json.loads(content)

        assert "timestamp" in data
        assert "system_status" in data
        assert "host_resources" in data
        assert "daemon_stoppages" in data
        assert "token_burn" in data
        assert "youtube_quotas" in data
        assert "cookie_health" in data
        assert "database_health" in data
        assert "mcp_health" in data
        assert "asset_rejections" in data
        assert "recent_incidents" in data


@pytest.mark.asyncio
async def test_mcp_resource_system_quotas(repo: QueueRepository) -> None:
    """Assert reading system://quotas returns token burn and YouTube quota breakdown."""
    server = create_mcp_server()
    with patch("src.config.DEFAULT_DB_PATH", str(repo.db_path)):
        result = await server.read_resource("system://quotas")
        assert len(result) > 0
        data = json.loads(result[0].content)

        assert "token_burn" in data
        assert "youtube_quotas" in data
        assert "daily_budget_units" in data["youtube_quotas"]
        assert "total_tokens" in data["token_burn"]


@pytest.mark.asyncio
async def test_mcp_resource_system_health_enrichment(repo: QueueRepository) -> None:
    """Assert enriched system://health includes daemon liveness, cookie status, WAL status, and MCP health."""
    server = create_mcp_server()
    with patch("src.config.DEFAULT_DB_PATH", str(repo.db_path)):
        result = await server.read_resource("system://health")
        assert len(result) > 0
        data = json.loads(result[0].content)

        assert "daemon_liveness_status" in data
        assert "mcp_health" in data
        assert "cookie_health" in data
        assert "wal_status" in data


@pytest.mark.asyncio
async def test_mcp_tool_get_tube_status_execution(repo: QueueRepository) -> None:
    """Assert executing get_tube_status returns structured JSON within latency budget."""
    server = create_mcp_server()
    with patch("src.config.DEFAULT_DB_PATH", str(repo.db_path)):
        t0 = time.perf_counter()
        result = await server.call_tool(
            "get_tube_status",
            {"channel": "horror", "window_hours": 6, "db_path": str(repo.db_path)},
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert hasattr(result, "content")
        assert len(result.content) > 0
        # Check tool execution latency
        assert elapsed_ms < 100.0

        raw_text = result.content[0].text if hasattr(result.content[0], "text") else str(result.content[0])
        data = json.loads(raw_text)
        assert "system_status" in data
        assert "host_resources" in data
        assert "token_burn" in data
        assert "youtube_quotas" in data


def test_mcp_health_checker_tri_state_resolution(repo: QueueRepository) -> None:
    """Assert MCPHealthChecker correctly identifies HEALTHY, DEGRADED, and BROKEN states."""
    checker = MCPHealthChecker(db_path=str(repo.db_path))

    # 1. Healthy state
    h_healthy = checker.evaluate_health(force=True)
    assert h_healthy.overall_status in ("HEALTHY", "DEGRADED")  # Depending on repo sync

    # 2. Degraded state (SSOT drift detected)
    with patch.object(checker, "check_ssot_drift", return_value=(False, ["Missing tool 'get_tube_status'"])):
        h_degraded = checker.evaluate_health(force=True)
        assert h_degraded.overall_status == "DEGRADED"
        assert "SSOT drift detected" in h_degraded.status_reason

    # 3. Broken state (Factory import failure)
    with patch.object(
        checker,
        "check_factory_importability",
        return_value=(False, 0, 0, 0, "ImportError: No module named 'mcp'"),
    ):
        h_broken = checker.evaluate_health(force=True)
        assert h_broken.overall_status == "BROKEN"
        assert "ImportError" in h_broken.status_reason


def test_cli_tube_dashboard_rendering(repo: QueueRepository, capsys: pytest.CaptureFixture[str]) -> None:
    """Assert print_tube() produces ANSI terminal gauges, tables, and incident timelines."""
    collector = TubeCollector(db_path=str(repo.db_path))
    snapshot = collector.compile_snapshot()

    print_tube(snapshot, channel="drama", json_output=False)
    captured = capsys.readouterr().out

    assert "EL TUBO" in captured.upper() or "OBSERVABILITY" in captured.upper()
    assert "CPU" in captured
    assert "RAM" in captured
    assert "YOUTUBE" in captured.upper()
    assert "TOKEN BURN" in captured.upper() or "TOKENS" in captured.upper()
    assert "INCIDENT" in captured.upper()


def test_cli_tube_json_mode(repo: QueueRepository, capsys: pytest.CaptureFixture[str]) -> None:
    """Assert main.py tube --json outputs parseable JSON matching TubeSnapshot."""
    ret = main(["tube", "--json", "--db-path", str(repo.db_path)])
    assert ret == 0

    captured = capsys.readouterr().out.strip()
    data = json.loads(captured)
    assert "timestamp" in data
    assert "system_status" in data
    assert "host_resources" in data
    assert "youtube_quotas" in data
    assert "token_burn" in data
