# Contributing

Issues and pull requests are welcome. This is a local catalog for 480×800
XTEINK X4 sleep-screen BMPs, plus a static public gallery. Keep that scope.

Cloud ingest, user submissions, and on-the-fly conversion are **not**
accepted as drive-by features. They have a tracking issue.

## Ground rules

- Do not commit personal paths, library dumps, device backups, screenshots
  of a private catalog, API keys, or `.env` files.
- Do not add a bind address other than `127.0.0.1`.
- Do not modify source BMPs. The catalog is read-only toward the library.
- Keep changes as small as the problem they solve.
- Use `x4catalog` in code and `X4 Catalog` in prose. Do not reintroduce
  “Archive” as the product name.

## Development setup

You need Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/P4CIFIC/x4catalog.git
cd x4catalog
uv sync --extra dev
uv run --extra dev pytest
```

Point `--source` at a folder of 480×800 BMP files, or create a tiny fixture
library for manual checks.

## Web UI

The UI lives in `frontend/` and is built into `static/`.

```bash
npm --prefix frontend ci
npm --prefix frontend run build
```

The build writes a stable `static/assets/app.js`. Do not add extra hashed
Vite leftovers.

## Pull requests

- Run `uv run --extra dev pytest`.
- Rebuild the frontend if you changed `frontend/`.
- Update the README when a flag, default, or safety behavior changes.
- Follow the [code of conduct](CODE_OF_CONDUCT.md).

## License

Contributions are accepted under the Unlicense. See [LICENSE](LICENSE).
