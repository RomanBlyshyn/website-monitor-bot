# Website Monitor Bot

Website Monitor Bot watches configurable public listing and product pages for new items and price drops, then sends Telegram alerts. Add or adjust sources in YAML without changing the Python code.

<!-- Add a screenshot of a sample Telegram alert here. -->

## Features

- HTML, RSS/Atom, and JSON sources with per-source intervals and selectors/field paths
- Optional Playwright fetching for JavaScript-rendered HTML pages
- Persistent SQLite storage, first-run baseline, URL-based deduplication, and price-drop tracking
- Include/exclude keyword and price filters
- Admin-only `/start`, `/status`, `/pause`, `/resume`, and `/sources` commands
- Per-source retry/backoff, failure and recovery alerts, and a rate-limited Telegram queue
- Docker Compose deployment

## Quick start

1. Create a Telegram bot with [BotFather](https://t.me/BotFather) and copy its token.
2. Copy `.env.example` to `.env`. Set `BOT_TOKEN`, `CHAT_ID`, and `ADMIN_CHAT_ID`. `CHAT_ID` is where alerts are delivered; `ADMIN_CHAT_ID` is the chat allowed to use commands and receive source health alerts.
3. Copy `sources.example.yaml` to `sources.yaml` and customize its public sources.
4. Start the bot:

   ```sh
   docker compose up --build -d
   ```

5. Follow logs with `docker compose logs -f`.

The SQLite database is stored in `./data/`. The first successful poll for each source saves a baseline without sending old listings. Later polls notify on matching new listings and price reductions. The first poll runs on startup; subsequent polls use the configured interval plus 10–30% random jitter.

## Adding a source

Add a source entry to `sources.yaml`. For HTML, provide CSS selectors relative to each item card. For JSON, `item_path` locates the list and `fields` uses dot-separated paths relative to each record. RSS needs only its feed URL.

```yaml
sources:
  - name: Camera search
    url: https://shop.example/search?q=camera
    type: html
    interval_minutes: 30
    use_browser: false
    selectors:
      item: ".product-card"
      title: ".product-title"
      price: ".product-price"
      link: "a.product-link"
      image: "img"
    currency: USD
    filters:
      include_keywords: ["mirrorless"]
      exclude_keywords: ["case"]
      min_price: 100
      max_price: 2000
```

Set `use_browser: true` for a JavaScript-rendered HTML source. Keep polling intervals reasonable and configure selectors/paths to match the site's current markup.

## Configuration

Environment variables are documented in `.env.example`. `DB_PATH` defaults to `data/monitor.db`; Docker Compose sets it to `/data/monitor.db` inside the container. `LOG_LEVEL` defaults to `INFO`.

## Development

Use Python 3.12. Install dependencies with `pip install -r requirements-dev.txt`, copy the example environment/source files, and run the bot with `python -m app.main`. Run tests with `pytest`.

**Monitor only public pages and respect each site's terms and robots.txt.**
