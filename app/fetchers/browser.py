import asyncio
import logging

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from app.config import DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)


class BrowserFetcher:
    """Lazily started headless Chromium for JavaScript-rendered pages."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT) -> None:
        self.user_agent = user_agent
        self._playwright = None
        self._browser = None
        self._lock = asyncio.Lock()

    async def _ensure_browser(self) -> None:
        async with self._lock:
            if self._browser is None:
                self._playwright = await async_playwright().start()
                self._browser = await self._playwright.chromium.launch(headless=True)

    async def fetch(self, url: str) -> str:
        for attempt in range(4):
            try:
                await self._ensure_browser()
                page = await self._browser.new_page(user_agent=self.user_agent)
                try:
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=30_000,
                    )
                    if response is not None and response.status >= 400:
                        if response.status != 429 and response.status < 500:
                            raise RuntimeError(
                                f"Browser request returned HTTP {response.status}: {url}"
                            )
                        if attempt == 3:
                            raise RuntimeError(
                                f"Browser request returned HTTP {response.status}: {url}"
                            )
                        await asyncio.sleep(2**attempt)
                        continue
                    try:
                        await page.wait_for_load_state("networkidle", timeout=10_000)
                    except PlaywrightTimeoutError:
                        pass  # Pages with long-polling never go idle; use what loaded.
                    return await page.content()
                finally:
                    await page.close()
            except PlaywrightError as error:
                if attempt == 3:
                    raise
                logger.warning("Browser fetch %s failed (%s); retrying", url, error)
                await asyncio.sleep(2**attempt)
        raise RuntimeError(f"Browser request failed after retries: {url}")

    async def close(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None
