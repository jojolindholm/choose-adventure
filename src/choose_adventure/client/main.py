"""Entry point for `cya-client`: play against a remote `cya-server`."""

from __future__ import annotations

import argparse
import getpass
import os

from choose_adventure.client.api import RemoteStoryService
from choose_adventure.config import CyaConfig
from choose_adventure.ui.app import AdventureApp


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Play Choose Your Adventure against a remote cya-server"
    )
    parser.add_argument(
        "--server",
        default=os.environ.get("CYA_SERVER_URL", "http://localhost:8787"),
        help="server base URL (env CYA_SERVER_URL)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("CYA_SERVER_TOKEN", ""),
        help="shared secret (env CYA_SERVER_TOKEN)",
    )
    parser.add_argument(
        "--player",
        default=os.environ.get("CYA_PLAYER", getpass.getuser()),
        help="player name; each player gets their own story database (env CYA_PLAYER)",
    )
    args = parser.parse_args()

    if not args.token:
        print("error: --token required (or set CYA_SERVER_TOKEN)", file=__import__("sys").stderr)
        return 1

    remote = RemoteStoryService(base_url=args.server, token=args.token, player=args.player)

    # Pre-flight: fail fast with a clear message if the server is unreachable.
    try:
        health = remote._sync.get("/api/health")
        if health.status_code != 200:
            print(f"error: server at {args.server} not healthy (HTTP {health.status_code})")
            return 1
    except Exception as e:  # noqa: BLE001 - report any connection failure cleanly
        print(f"error: cannot reach server at {args.server}: {e}")
        return 1

    app = AdventureApp(CyaConfig(), remote, remote)
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
