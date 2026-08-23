from __future__ import annotations

import pathlib

from pydantic import BaseModel


class CyaConfig(BaseModel, frozen=True):
    base_url: str = "http://llm.courtdata.se/v1"
    model: str = "huihui-qwen3.8-27b-abliterated"
    db_path: str = "~/.local/share/choose-adventure/stories.db"
    temperature: float = 0.8
    max_tokens: int = 1200
    timeout: float = 120.0

    @classmethod
    def from_args(cls, namespace) -> CyaConfig:
        """Create config from argparse namespace."""
        return cls(
            base_url=namespace.base_url,
            model=namespace.model,
            db_path=str(pathlib.Path(namespace.db).expanduser()),
        )
