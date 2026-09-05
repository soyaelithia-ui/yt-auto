# Systemd units (VPS)

Canonical deploy root: **`/srv/projects/yt-auto`**.

| Unit | Role |
|------|------|
| `yt-lanes-daemon.service` | Multi-lane producer (`main.py daemon`) |
| `yt-review-bot.service` | Sole Telegram callback poller (`deploy/tmux_review_bot.py`) |

`Environment=YT_AUTO_ROOT=/srv/projects/yt-auto` is the documented default. `WorkingDirectory=` / `ExecStart=` stay absolute at that same path (systemd limitation). See [docs/OPERACION.md](../../docs/OPERACION.md) §3 for install and drop-in overrides.
