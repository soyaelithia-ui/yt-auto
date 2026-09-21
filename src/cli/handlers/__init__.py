"""CLI subcommand handlers package."""
from src.cli.handlers.auth import handle_auth
from src.cli.handlers.backup import handle_backup
from src.cli.handlers.clean import handle_clean
from src.cli.handlers.daemon import handle_daemon
from src.cli.handlers.inventory import handle_inventory
from src.cli.handlers.lanes import handle_lanes
from src.cli.handlers.loop import handle_loop
from src.cli.handlers.mcp import handle_mcp
from src.cli.handlers.migrate import handle_migrate
from src.cli.handlers.profile import handle_profile
from src.cli.handlers.queue import handle_queue
from src.cli.handlers.run import handle_run
from src.cli.handlers.service import handle_service
from src.cli.handlers.status import handle_status
from src.cli.handlers.test import handle_test

__all__ = [
    "handle_run",
    "handle_daemon",
    "handle_status",
    "handle_queue",
    "handle_clean",
    "handle_auth",
    "handle_backup",
    "handle_inventory",
    "handle_migrate",
    "handle_service",
    "handle_lanes",
    "handle_loop",
    "handle_profile",
    "handle_test",
    "handle_mcp",
]

