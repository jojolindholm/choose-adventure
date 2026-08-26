"""Entry point for `saga-client`: play against a remote `saga-server`."""

from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path

from choose_adventure.client.api import RemoteStoryService
from choose_adventure.config import CyaConfig
from choose_adventure.ui.app import AdventureApp

DEFAULT_SERVER_URL = "http://localhost:8787"


def _load_defaults() -> dict[str, str]:
    """Read key=value defaults from ~/.config/choose-adventure/client.env, if present.

    Machine-local file (outside the repo) so shared secrets never land in
    source control. Same format as a shell env file: KEY=value, # comments.
    """
    path = Path.home() / ".config" / "choose-adventure" / "client.env"
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _pick(flag_value: str, env_name: str, defaults: dict[str, str], fallback: str) -> str:
    """Resolve a setting: CLI flag > env var > defaults file > built-in fallback."""
    if flag_value:
        return flag_value
    env_value = os.environ.get(env_name, "").strip()
    if env_value:
        return env_value
    return defaults.get(env_name, fallback)


def main() -> int:
    defaults = _load_defaults()

    parser = argparse.ArgumentParser(description="Play Saga against a remote saga-server")
    parser.add_argument("--server", default="", help="server base URL (env CYA_SERVER_URL)")
    parser.add_argument("--token", default="", help="shared secret (env CYA_SERVER_TOKEN)")
    parser.add_argument("--player", default="", help="player name (env CYA_PLAYER)")
    args = parser.parse_args()

    server = _pick(args.server, "CYA_SERVER_URL", defaults, DEFAULT_SERVER_URL)
    token = _pick(args.token, "CYA_SERVER_TOKEN", defaults, "")
    player = _pick(args.player, "CYA_PLAYER", defaults, getpass.getuser())

    if not token:
        print(
            "error: no server token. Pass --token, set CYA_SERVER_TOKEN, or add it to "
            "~/.config/choose-adventure/client.env",
            file=__import__("sys").stderr,
        )
        return 1

    remote = RemoteStoryService(base_url=server, token=token, player=player)

    # Pre-flight: fail fast with a clear message if the server is unreachable.
    try:
        health = remote._sync.get("/api/health")
        if health.status_code != 200:
            print(f"error: server at {server} not healthy (HTTP {health.status_code})")
            return 1
    except Exception as e:  # noqa: BLE001 - report any connection failure cleanly
        print(f"error: cannot reach server at {server}: {e}")
        return 1

    app = AdventureApp(CyaConfig(), remote, remote)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
