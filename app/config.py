from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    CHAT_ID: int
    ADMIN_CHAT_ID: int
    DB_PATH: str = "data/monitor.db"
    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


class FiltersConfig(BaseModel):
    include_keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    min_price: float | None = None
    max_price: float | None = None


class HtmlSelectors(BaseModel):
    item: str
    title: str
    link: str
    price: str | None = None
    image: str | None = None


class JsonFields(BaseModel):
    title: str
    link: str
    price: str | None = None
    image: str | None = None
    currency: str | None = None


class SourceConfig(BaseModel):
    name: str
    url: str
    type: Literal["html", "rss", "json"]
    interval_minutes: PositiveInt
    selectors: HtmlSelectors | None = None
    fields: JsonFields | None = None
    item_path: str | None = None
    currency: str = ""
    use_browser: bool = False
    filters: FiltersConfig = Field(default_factory=FiltersConfig)

    @model_validator(mode="after")
    def validate_source_fields(self) -> "SourceConfig":
        if self.type == "html" and self.selectors is None:
            raise ValueError("HTML sources require selectors")
        if self.type == "json" and self.fields is None:
            raise ValueError("JSON sources require fields")
        if self.use_browser and self.type != "html":
            raise ValueError("use_browser is only supported for HTML sources")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def load_sources(path: str | Path = "sources.yaml") -> list[SourceConfig]:
    with Path(path).open("r", encoding="utf-8") as source_file:
        raw_config = yaml.safe_load(source_file) or {}

    raw_sources = raw_config.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("sources.yaml must contain a non-empty 'sources' list")

    sources = [SourceConfig.model_validate(source) for source in raw_sources]
    names = [source.name for source in sources]
    if len(names) != len(set(names)):
        raise ValueError("Source names must be unique")
    return sources
