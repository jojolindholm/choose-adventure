from __future__ import annotations

import os
import pathlib

from pydantic import BaseModel


class CyaConfig(BaseModel, frozen=True):
    base_url: str = "http://llm.courtdata.se/v1"
    model: str = "huihui-qwen3.8-27b-abliterated"
    db_path: str = "~/.local/share/choose-adventure/stories.db"
    temperature: float = 0.8
    max_tokens: int = 4000
    timeout: float = 300.0
    # Empty string => use the free no-auth endpoint (dummy key).
    api_key: str = ""

    @classmethod
    def from_args(cls, namespace) -> CyaConfig:
        """Create config from argparse namespace, honouring CYA_* env vars as defaults.

        Environment variables (CYA_BASE_URL / CYA_MODEL / CYA_API_KEY / CYA_DB) provide
        defaults; explicit CLI flags take precedence. Keeps secrets like the API key out
        of source control.
        """

        def _env(name: str, current: str) -> str:
            return os.environ.get(name, "").strip() or current

        return cls(
            base_url=_env("CYA_BASE_URL", namespace.base_url),
            model=_env("CYA_MODEL", namespace.model),
            db_path=str(pathlib.Path(_env("CYA_DB", namespace.db) or namespace.db).expanduser()),
            api_key=_env("CYA_API_KEY", namespace.api_key),
        )
