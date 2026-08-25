"""Entry point for `cya-server`: run the FastAPI app under uvicorn."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from choose_adventure.server.app import DEFAULT_PORT, create_app


def main() -> int:
    token = os.environ.get("CYA_SERVER_TOKEN", "").strip()
    if not token:
        print(
            "error: CYA_SERVER_TOKEN must be set (shared secret for thin clients)",
            file=sys.stderr,
        )
        return 1

    data_dir = Path(os.environ.get("CYA_DATA_DIR", "./data"))
    port = int(os.environ.get("CYA_SERVER_PORT", str(DEFAULT_PORT)))

    import uvicorn

    app = create_app(data_dir=data_dir, token=token)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
