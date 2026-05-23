# CtimeLI

**CLI See Time** — a macOS screen-edge countdown timer for time-blind / ADHD work.
It draws a shrinking stroke around every display, glows the edges as zero nears,
progressively blurs the desktop in the final stretch, and can hard-block the
screen at zero and tidy your windows away. Watch mode auto-starts timers from
your calendar.

## Quick start

```sh
cp .env.example .env   # optional — tune pulse/blur/calendar settings
./run 15               # 15-minute timer
./run watch            # calendar watch mode
```

## Development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # PyObjC — macOS only
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```

## Documentation

The [`docs/`](docs/) folder is the authoritative blueprint — architecture,
features, domain logic, port contracts, configuration, and porting guide.
Start with [`docs/README.md`](docs/README.md).

## Layout

```
src/ctimeli/    Python package (domain, app, adapters, cli)
tests/          pytest suite
docs/           specification
```
