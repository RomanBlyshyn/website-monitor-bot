# Website Monitor Bot

Config-driven monitor (HTML/RSS/JSON → SQLite → Telegram alerts). Public portfolio project:
code, README, comments and bot messages are in English.

## Commands
- `uv run pytest` — tests (must pass before every commit)
- `uv run python -m app.main` — run locally (needs `.env`)
- `uv run python -m app.whoami` — print chat IDs that messaged the bot
- `docker compose up -d --build` / `docker compose logs -f`

## Notes
- Python 3.12 via uv; deps in `pyproject.toml` / `uv.lock` (no requirements.txt).
- `scheduler.check_once()` is the unit of work and must never raise; tests drive it with fakes.
- Item ID = sha256 of the absolute URL; first run of a source = silent baseline.
- `sources.yaml` and `.env` are gitignored; `sources.example.yaml` is the fallback and is
  baked into the image. DB lives in the `monitor-data` volume.
- Example sources must stay scrape-friendly (books.toscrape.com, dummyjson.com, GitHub feeds).
