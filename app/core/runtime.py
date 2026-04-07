from __future__ import annotations

from dataclasses import dataclass, asdict

from app.core import config


@dataclass
class RuntimeSettings:
    language: str = config.LANGUAGE
    currency: str = config.CURRENCY
    ai_model: str = config.AI_MODEL
    timezone: str = config.TIMEZONE

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def update(self, key: str, value: str) -> None:
        if not hasattr(self, key):
            raise KeyError(f"Unknown runtime setting: {key}")
        setattr(self, key, value)


runtime_settings = RuntimeSettings()
