"""
Unit tests for CLI handler `main.py loop` (src/cli/handlers/loop.py).
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.cli.parser import build_parser, dispatch_cli
from src.core.catalog import LoopCatalogRepository, LoopRecord


class TestLoopCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_loops.db")
        self.catalog = LoopCatalogRepository(db_path=self.db_path)
        self.parser = build_parser()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cli_loop_list_empty(self):
        args = self.parser.parse_args(["-p", "test", "--db-path", self.db_path, "loop", "list", "-j"])
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = dispatch_cli(args, self.parser)
            self.assertEqual(code, 0)
            output = json.loads(mock_stdout.getvalue())
            self.assertEqual(output, [])

    def test_cli_loop_audit(self):
        args = self.parser.parse_args(["-p", "test", "--db-path", self.db_path, "loop", "audit", "-j"])
        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = dispatch_cli(args, self.parser)
            self.assertEqual(code, 0)
            report = json.loads(mock_stdout.getvalue())
            self.assertIn("total_checked", report)
            self.assertEqual(report["total_checked"], 0)

    @patch("src.cli.handlers.loop.LoopSynthesizerWorker")
    def test_cli_loop_generate_dispatches_worker(self, mock_worker_cls):
        mock_worker = MagicMock()
        mock_worker_cls.return_value = mock_worker
        dummy_rec = LoopRecord(
            loop_id="web_cosmic_v_99",
            category="cosmic_horror",
            technology="webgl_shader",
            orientation="vertical",
            width=1080,
            height=1920,
            duration_sec=6.0,
            fps=30,
            file_path="/tmp/fake.mp4",
            file_size_bytes=2048,
            sha256="abc",
        )
        mock_worker.synthesize_on_demand.return_value = dummy_rec

        args = self.parser.parse_args([
            "-p", "test",
            "--db-path", self.db_path,
            "loop", "generate",
            "-c", "cosmic_horror",
            "-o", "vertical",
            "-n", "1",
            "--duration", "6.0",
            "--seed", "99",
            "-j",
        ])

        with patch("sys.stdout", new_callable=io.StringIO) as mock_stdout:
            code = dispatch_cli(args, self.parser)
            self.assertEqual(code, 0)
            output = json.loads(mock_stdout.getvalue())
            self.assertEqual(len(output), 1)
            self.assertEqual(output[0]["loop_id"], "web_cosmic_v_99")
