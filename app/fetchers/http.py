import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


class HttpFetcher:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(20.0, connect=10.0),
            headers={
                "User-Agent": (
                    "WebsiteMonitorBot/1.0 "
                    "(public-page monitoring; contact: configure-your-contact)"
                ),
                "Accept": "text/html,application/json,application/rss+xml,"
                "application/atom+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            follow_redirects=True,
        )

    async def fetch(self, url: str) -> bytes:
        for attempt in range(4):
            try:
                response = await self.client.get(url)
                response.raise_for_status()
                return response.content
            except httpx.HTTPStatusError as error:
                retryable = error.response.status_code == 429 or (
                    500 <= error.response.status_code < 600
                )
                if not retryable or attempt == 3:
                    raise
                delay = 2**attempt
                logger.warning(
                    "Retryable HTTP status %s for %s; retrying in %s seconds",
                    error.response.status_code,
                    url,
                    delay,
                )
            except httpx.RequestError:
                if attempt == 3:
                    raise
                delay = 2**attempt
                logger.warning(
                    "HTTP request failed for %s; retrying in %s seconds",
                    url,
                    delay,
                )
            await asyncio.sleep(delay)
        raise RuntimeError(f"Request failed after retries: {url}")

    async def close(self) -> None:
        await self.client.aclose()
