import logging
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, PositiveInt, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; WebsiteMonitorBot/1.0; "
    "+https://github.com/RomanBlyshyn/website-monitor-bot)"
)
EXAMPLE_SOURCES_PATH = Path("sources.example.yaml")


class Settings(BaseSettings):
    BOT_TOKEN: str
    CHAT_ID: int
    ADMIN_CHAT_ID: int
    DB_PATH: str = "data/monitor.db"
    LOG_LEVEL: str = "INFO"
    SOURCES_PATH: str = "sources.yaml"
    USER_AGENT: str = DEFAULT_USER_AGENT

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
    """CSS selectors relative to each item node.

    Append ``::attr(name)`` to read an attribute instead of text,
    e.g. ``h3 a::attr(title)``. Use ``:scope`` to target the item node itself.
    """

    item: str
    title: str
    link: str
    price: str | None = None
    image: str | None = None


class JsonFields(BaseModel):
    """Dot-separated paths relative to each record (``a.b.0.c``)."""

    title: str
    link: str | None = None
    link_template: str | None = None
    price: str | None = None
    image: str | None = None
    currency: str | None = None

    @model_validator(mode="after")
    def require_link(self) -> "JsonFields":
        if not self.link and not self.link_template:
            raise ValueError("JSON fields need 'link' or 'link_template'")
        return self


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
    respect_robots: bool = True
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


def resolve_sources_path(path: str | Path) -> Path:
    """Return ``path`` or fall back to the bundled example config."""
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    if EXAMPLE_SOURCES_PATH.is_file():
        logger.warning(
            "%s not found; using %s. Copy it to %s to customize sources.",
            candidate,
            EXAMPLE_SOURCES_PATH,
            candidate,
        )
        return EXAMPLE_SOURCES_PATH
    raise FileNotFoundError(f"Sources config not found: {candidate}")


def load_sources(path: str | Path = "sources.yaml") -> list[SourceConfig]:
    with resolve_sources_path(path).open("r", encoding="utf-8") as source_file:
        raw_config = yaml.safe_load(source_file) or {}

    raw_sources = raw_config.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise ValueError("sources.yaml must contain a non-empty 'sources' list")

    sources = [SourceConfig.model_validate(source) for source in raw_sources]
    names = [source.name for source in sources]
    if len(names) != len(set(names)):
        raise ValueError("Source names must be unique")
    return sources
