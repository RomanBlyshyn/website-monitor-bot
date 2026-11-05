import asyncio
import logging
import time
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from app.config import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
ROBOTS_CACHE_SECONDS = 6 * 60 * 60


class RobotsDisallowedError(RuntimeError):
    pass


class HttpFetcher:
    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.user_agent = user_agent
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/json,application/rss+xml,"
                "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.8",
            },
            follow_redirects=True,
        )
        self._robots: dict[str, tuple[float, RobotFileParser | None]] = {}

    async def fetch(self, url: str) -> bytes:
        """GET ``url`` with up to ``MAX_RETRIES`` retries and exponential backoff."""
        for attempt in range(MAX_RETRIES + 1):
            last = attempt == MAX_RETRIES
            try:
                response = await self.client.get(url)
                response.raise_for_status()
                return response.content
            except httpx.HTTPStatusError as error:
                status = error.response.status_code
                if last or not (status == 429 or 500 <= status < 600):
                    raise
                reason = f"HTTP {status}"
            except httpx.RequestError as error:
                if last:
                    raise
                reason = type(error).__name__
            delay = 2**attempt
            logger.warning(
                "Fetch %s failed (%s); retry %s/%s in %ss",
                url,
                reason,
                attempt + 1,
                MAX_RETRIES,
                delay,
            )
            await asyncio.sleep(delay)
        raise RuntimeError(f"Request failed after retries: {url}")

    async def ensure_allowed(self, url: str) -> None:
        """Raise ``RobotsDisallowedError`` if robots.txt forbids fetching ``url``."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(origin)
        if cached is None or time.monotonic() - cached[0] > ROBOTS_CACHE_SECONDS:
            cached = (time.monotonic(), await self._load_robots(origin))
            self._robots[origin] = cached

        parser = cached[1]
        if parser is not None and not parser.can_fetch(self.user_agent, url):
            raise RobotsDisallowedError(f"robots.txt disallows {url}")

    async def _load_robots(self, origin: str) -> RobotFileParser | None:
        try:
            response = await self.client.get(f"{origin}/robots.txt")
        except httpx.RequestError as error:
            logger.warning("Could not load robots.txt for %s: %s", origin, error)
            return None
        if response.status_code >= 400:
            return None  # No robots.txt: everything is allowed.
        parser = RobotFileParser()
        parser.parse(response.text.splitlines())
        return parser

    async def close(self) -> None:
        await self.client.aclose()
