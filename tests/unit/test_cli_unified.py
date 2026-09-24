"""Comprehensive test suite for unified CLI parser, subcommands, POSIX short aliases, and backward compatibility."""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from main import (
    LOCK_FILE_PATH,
    _preparse_profile,
    acquire_lock,
    build_parser,
    main,
    register_signal_handlers,
    release_lock,
    run_pipeline_once,
)
from src.cli import (
    _is_daemon_running,
    cli_errors,
    cli_status,
    dispatch_cli,
    list_queue,
    print_errors,
    print_queue,
    print_status,
    translate_legacy_args,
)


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary initialized SQLite database for CLI tests."""
    from src.db import init_db

    db_path = str(tmp_path / "test_cli.db")
    init_db(db_path)
    return db_path


class TestCLIParserAndSubcommands:
    """Test ArgumentParser construction, subcommands, and short POSIX options."""

    def test_canonical_re_exports(self):
        """Verify all canonical symbols are exported from main.py and src.cli."""
        assert callable(acquire_lock)
        assert callable(release_lock)
        assert LOCK_FILE_PATH is not None
        assert callable(run_pipeline_once)
        assert callable(register_signal_handlers)
        assert callable(_preparse_profile)
        assert callable(build_parser)
        assert callable(main)
        assert callable(dispatch_cli)
        assert callable(cli_status)
        assert callable(list_queue)
        assert callable(print_status)
        assert callable(print_queue)
        assert callable(cli_errors)
        assert callable(print_errors)
        assert callable(_is_daemon_running)

    def test_preparse_profile(self, monkeypatch):
        """Verify _preparse_profile extracts YT_PROFILE from --profile or -p."""
        monkeypatch.delenv("YT_PROFILE", raising=False)
        _preparse_profile(["main.py", "--profile", "prod", "status"])
        assert os.environ.get("YT_PROFILE") == "prod"

        monkeypatch.delenv("YT_PROFILE", raising=False)
        _preparse_profile(["main.py", "-p", "test", "run"])
        assert os.environ.get("YT_PROFILE") == "test"

    def test_parser_subcommands_registration(self):
        """Verify all 8 canonical subcommands and service are registered in build_parser."""
        parser = build_parser()
        subparser_action = next(
            a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
        )
        assert "run" in subparser_action.choices
        assert "daemon" in subparser_action.choices
        assert "status" in subparser_action.choices
        assert "queue" in subparser_action.choices
        assert "clean" in subparser_action.choices
        assert "auth" in subparser_action.choices
        assert "backup" in subparser_action.choices
        assert "migrate" in subparser_action.choices
        assert "service" in subparser_action.choices
        assert "collect-links" in subparser_action.choices
        assert "sweep-24h" in subparser_action.choices
        assert "prune-underperforming" in subparser_action.choices

    def test_collect_links_subcommand_flags(self):
        """Verify collect-links subcommand flag parsing and dispatch."""
        parser = build_parser()
        args = parser.parse_args([
            "collect-links",
            "-c", "horror",
            "--limit", "10",
            "--live",
        ])
        assert args.subcommand == "collect-links"
        assert args.channel == "horror"
        assert args.limit == 10
        assert args.live is True

    def test_run_subcommand_flags_and_aliases(self):
        """Verify run subcommand flags; format flags are gone (lane-driven now)."""
        parser = build_parser()
        args = parser.parse_args([
            "run",
            "-c", "aelithia",
            "--lane", "aelithia-aita-long",
            "-s", "story_123",
            "-t", "Custom Topic",
            "--generate-only",
            "--dispatch-telegram",
            "--test-telegram",
            "-d",
            "--preflight",
        ])
        assert args.subcommand == "run"
        assert args.channel == "aelithia"
        assert args.lane == "aelithia-aita-long"
        assert args.story_id == "story_123"
        assert args.topic == "Custom Topic"
        assert args.generate_only is True
        assert args.dispatch_telegram is True
        assert args.test_telegram is True
        assert args.dry_run is True
        assert args.preflight is True

    def test_removed_format_flags_are_rejected(self):
        """Legacy format flags fail loudly with the migration path."""
        from src.cli.parser import translate_legacy_args

        for argv in (
            ["main.py", "run", "-c", "moku", "-f", "longform"],
            ["main.py", "run", "--video-mode", "short"],
            ["main.py", "run", "--duration", "5.5"],
            ["main.py", "run", "--short-test"],
        ):
            with pytest.raises(SystemExit) as excinfo:
                translate_legacy_args(argv)
            assert "config/lanes.json" in str(excinfo.value)

    def test_daemon_subcommand_flags_and_aliases(self):
        """Verify daemon subcommand flags and aliases (--lanes replaces -f)."""
        parser = build_parser()
        args = parser.parse_args([
            "daemon",
            "-i", "600",
            "-c", "moku",
            "--lanes", "moku-scp-shorts,moku-horror-long",
            "--sequential",
            "--mass-produce",
        ])
        assert args.subcommand == "daemon"
        assert args.interval == 600
        assert args.channel == "moku"
        assert args.lanes == "moku-scp-shorts,moku-horror-long"
        assert args.sequential is True
        assert args.mass_produce is True

    def test_status_subcommand_flags_and_aliases(self):
        """Verify status subcommand flags and aliases (-j, -l, -c, --apis, --errors, etc.)."""
        parser = build_parser()
        args = parser.parse_args([
            "status",
            "-j",
            "-c", "moku",
            "--apis",
            "--errors",
            "--since", "48h",
            "-l", "10",
            "--component", "tts",
            "--level", "ERROR",
            "--agent-review", "RUN_999",
            "--check-pub",
        ])
        assert args.subcommand == "status"
        assert args.json is True
        assert args.channel == "moku"
        assert args.apis is True
        assert args.errors is True
        assert args.since == "48h"
        assert args.limit == 10
        assert args.component == "tts"
        assert args.level == "ERROR"
        assert args.agent_review == "RUN_999"
        assert args.check_pub is True

    def test_queue_subcommand_flags_and_actions(self):
        """Verify queue subcommand actions (list, pause, resume, activate, sweep) and flags (-c, -l, -j)."""
        parser = build_parser()
        args1 = parser.parse_args(["queue", "pause", "moku", "-j"])
        assert args1.subcommand == "queue"
        assert args1.action == "pause"
        assert args1.target_channel == "moku"
        assert args1.json is True

        args2 = parser.parse_args(["queue", "list", "-l", "25", "-c", "aelithia"])
        assert args2.subcommand == "queue"
        assert args2.action == "list"
        assert args2.limit == 25
        assert args2.channel == "aelithia"

    def test_clean_subcommand_flags_and_aliases(self):
        """Verify clean subcommand flags (-d, --cache, --sessions)."""
        parser = build_parser()
        args = parser.parse_args(["clean", "-d", "--cache"])
        assert args.subcommand == "clean"
        assert args.dry_run is True
        assert args.cache is True

    def test_auth_subcommand_flags_and_actions(self):
        """Verify auth subcommand actions (url, exchange) and flags (-c, --code)."""
        parser = build_parser()
        args1 = parser.parse_args(["auth", "url", "-c", "aelithia"])
        assert args1.subcommand == "auth"
        assert args1.action == "url"
        assert args1.channel == "aelithia"

        args2 = parser.parse_args(["auth", "exchange", "auth_code_xyz", "-c", "moku"])
        assert args2.subcommand == "auth"
        assert args2.action == "exchange"
        assert args2.code == "auth_code_xyz"

    def test_backup_and_migrate_subcommand_flags(self):
        """Verify backup and migrate flags (-o, -d, -j)."""
        parser = build_parser()
        args1 = parser.parse_args(["backup", "-o", "/tmp/backup.db", "-j"])
        assert args1.subcommand == "backup"
        assert args1.destination == "/tmp/backup.db"
        assert args1.json is True

        args2 = parser.parse_args(["migrate", "-d", "-j"])
        assert args2.subcommand == "migrate"
        assert args2.dry_run is True
        assert args2.json is True


class TestLegacyArgumentTranslation:
    """Test translating historical commands and flat flags to canonical subcommands."""

    def test_translate_status_legacy(self):
        assert translate_legacy_args(["--status"]) == ["status"]
        assert translate_legacy_args(["status"]) == ["status"]

    def test_translate_run_legacy(self):
        assert translate_legacy_args(["--run-once", "--channel", "moku"]) == ["run", "--channel", "moku"]
        assert translate_legacy_args(["run-once", "--topic", "test"]) == ["run", "--topic", "test"]

    def test_translate_daemon_legacy(self):
        assert translate_legacy_args(["--daemon", "--interval", "300"]) == ["daemon", "--interval", "300"]
        assert translate_legacy_args(["start-daemon", "--mass-produce"]) == ["daemon", "--mass-produce"]

    def test_translate_queue_legacy(self):
        assert translate_legacy_args(["--list-queue", "--limit", "10"]) == ["queue", "list", "--limit", "10"]
        assert translate_legacy_args(["list-queue"]) == ["queue", "list"]
        assert translate_legacy_args(["queue"]) == ["queue"]
        assert translate_legacy_args(["pause", "moku"]) == ["queue", "pause", "moku"]

    def test_translate_clean_legacy(self):
        assert translate_legacy_args(["--clean-cache", "--dry-run"]) == ["clean", "--cache", "--dry-run"]
        assert translate_legacy_args(["clean-cache"]) == ["clean", "--cache"]

    def test_translate_auth_legacy(self):
        assert translate_legacy_args(["--auth-url"]) == ["auth", "url"]
        assert translate_legacy_args(["--auth-code", "abc"]) == ["auth", "exchange", "abc"]

    def test_translate_service_legacy(self):
        assert translate_legacy_args(["build"]) == ["service", "build"]
        assert translate_legacy_args(["logs"]) == ["service", "logs"]


class TestCLIExecutionAndHandlers:
    """Test running handlers via main() with temporary DB."""

    def test_status_json_execution(self, temp_db, capsys):
        """Verify status -j execution."""
        ret = main(["status", "-j", "--db-path", temp_db])
        assert ret == 0
        captured = capsys.readouterr().out
        data = json.loads(captured)
        assert "queue" in data
        assert "processed_count" in data

    def test_queue_list_and_json(self, temp_db, capsys):
        """Verify queue list -j execution."""
        ret = main(["queue", "list", "-j", "--db-path", temp_db])
        assert ret == 0
        captured = capsys.readouterr().out
        data = json.loads(captured)
        assert isinstance(data, list)

    def test_clean_dry_run(self, temp_db, capsys):
        """Verify clean -d execution."""
        ret = main(["clean", "-d", "--db-path", temp_db])
        assert ret == 0
        captured = capsys.readouterr().out
        assert "Tagged Project Work Cleanup Report" in captured
        assert "DRY RUN" in captured

    def test_migrate_dry_run_json(self, temp_db, capsys):
        """Verify migrate -d -j execution."""
        ret = main(["migrate", "-d", "-j", "--db-path", temp_db])
        assert ret == 0
        captured = capsys.readouterr().out
        data = json.loads(captured)
        assert "applied_versions" in data
        assert "dry_run" in data

    def test_backup_json(self, temp_db, tmp_path, capsys):
        """Verify backup -o <path> -j execution."""
        dest = str(tmp_path / "backup_out.db")
        ret = main(["backup", "-o", dest, "-j", "--db-path", temp_db])
        assert ret == 0
        captured = capsys.readouterr().out
        data = json.loads(captured)
        assert data["verified"] is True
        assert Path(dest).exists()

    def test_manage_facade_forwarding(self, temp_db, capsys):
        """Verify manage.py executes cleanly by delegating to main.py."""
        import manage

        assert callable(manage.main)
        assert callable(manage._preparse_profile)
        ret = manage.main(["status", "-j", "--db-path", temp_db])
        assert ret == 0
        captured = capsys.readouterr().out
        data = json.loads(captured)
        assert "queue" in data


class TestGlobalFlagsAndInheritance:
    """Test position independence and non-overwrite of global flags (-p, --db-path, -y)."""

    def test_global_db_path_before_and_after_subcommands(self):
        """Verify --db-path is preserved when placed before or after subcommand."""
        parser = build_parser()
        # Before subcommand
        args_before = parser.parse_args(["--db-path", "/tmp/custom.db", "status"])
        assert args_before.db_path == "/tmp/custom.db"
        assert args_before.subcommand == "status"

        # After subcommand
        args_after = parser.parse_args(["status", "--db-path", "/tmp/custom.db"])
        assert args_after.db_path == "/tmp/custom.db"
        assert args_after.subcommand == "status"

    def test_global_profile_before_and_after_subcommands(self):
        """Verify -p/--profile is preserved when placed before or after subcommand."""
        parser = build_parser()
        # Before subcommand
        args_before = parser.parse_args(["-p", "prod", "status"])
        assert args_before.profile == "prod"
        assert args_before.subcommand == "status"

        # After subcommand
        args_after = parser.parse_args(["status", "-p", "prod"])
        assert args_after.profile == "prod"
        assert args_after.subcommand == "status"

    def test_global_yes_before_and_after_subcommands(self):
        """Verify -y/--yes is preserved when placed before or after subcommand."""
        parser = build_parser()
        # Before subcommand
        args_before = parser.parse_args(["-y", "clean"])
        assert args_before.yes is True
        assert args_before.subcommand == "clean"

        # After subcommand
        args_after = parser.parse_args(["clean", "-y"])
        assert args_after.yes is True
        assert args_after.subcommand == "clean"

    def test_legacy_translated_global_flags_preservation(self):
        """Verify translated legacy invocations preserve db_path, profile, and yes flags."""
        parser = build_parser()
        # 1. --status --db-path /tmp/custom.db
        t1 = translate_legacy_args(["--status", "--db-path", "/tmp/custom.db"])
        args1 = parser.parse_args(t1)
        assert args1.subcommand == "status"
        assert args1.db_path == "/tmp/custom.db"

        # 2. --clean-cache --dry-run --db-path /tmp/custom.db -y
        t2 = translate_legacy_args(["--clean-cache", "--dry-run", "--db-path", "/tmp/custom.db", "-y"])
        args2 = parser.parse_args(t2)
        assert args2.subcommand == "clean"
        assert args2.cache is True
        assert args2.dry_run is True
        assert args2.db_path == "/tmp/custom.db"
        assert args2.yes is True

        # 3. list-queue --db-path /tmp/custom.db
        t3 = translate_legacy_args(["list-queue", "--db-path", "/tmp/custom.db"])
        args3 = parser.parse_args(t3)
        assert args3.subcommand == "queue"
        assert args3.action == "list"
        assert args3.db_path == "/tmp/custom.db"


class TestCLIEdgeCaseHandlers:
    """Test edge cases such as missing OAuth auth codes and invalid channel names."""

    def test_auth_exchange_missing_code_exits_2(self, temp_db, capsys):
        """Verify auth exchange without code returns exit code 2."""
        parser = build_parser()
        args = parser.parse_args(["auth", "exchange", "--db-path", temp_db])
        ret = dispatch_cli(args, parser=None)
        assert ret == 2
        err = capsys.readouterr().err
        assert "requiere un código de autorización" in err

    def test_run_invalid_channel_exits_2(self, temp_db, capsys):
        """Verify run with unknown channel returns exit code 2."""
        parser = build_parser()
        args = parser.parse_args(["run", "-c", "invalid_channel_name", "-d", "--db-path", temp_db])
        ret = dispatch_cli(args, parser=None)
        assert ret == 2
        err = capsys.readouterr().err
        assert "Canal desconocido o inválido" in err

    def test_queue_pause_invalid_channel_exits_2(self, temp_db, capsys):
        """Verify queue pause with unknown channel returns exit code 2."""
        parser = build_parser()
        args = parser.parse_args(["queue", "pause", "invalid_channel_xyz", "--db-path", temp_db])
        ret = dispatch_cli(args, parser=None)
        assert ret == 2
        err = capsys.readouterr().err
        assert "Canal desconocido o inválido" in err

