# X4 Catalog

Open-source catalog for [XTEINK X4](https://www.xteink.com/) sleep screens. 480×800 BMP, local-first, public domain.

- **Software:** run it on your computer. Source files are never modified.
- **Gallery:** browse a hosted snapshot at [x4catalog.com](https://www.x4catalog.com).
- **Device:** send files to an X4 on the same Wi-Fi. Short guide: [x4catalog.com/docs](https://x4catalog.com/docs). Details: [docs/device.md](docs/device.md).

## Local catalog

Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/P4CIFIC/x4catalog.git
cd x4catalog
uv sync --extra dev
uv run --extra dev pytest
uv run x4catalog init --source /path/to/your/480x800-bmps
uv run x4catalog ingest --pilot --source /path/to/your/480x800-bmps
uv run x4catalog serve --source /path/to/your/480x800-bmps
```

Open <http://127.0.0.1:8765>. The server binds to loopback only. There is no authentication.

Optional ML and OCR: `uv sync --extra ml`, then `download-models`, `ingest --full`, `embed`, `ocr`, `auto-label`, `views`. OCR uses Apple Vision and is macOS-only.

## Public gallery

The hosted site is a published snapshot (thumbnails + `catalog.json`). Reviews, labels, and OCR stay on the machine that runs the catalog until you publish again.

Sensitive tags are hidden until a visitor turns them on. Sending to an X4 is
explained in plain language at [x4catalog.com/docs](https://x4catalog.com/docs).
The protocol, mixed content, and firmware notes are in [docs/device.md](docs/device.md).

## Publish a snapshot

```bash
uv run x4catalog publish --skip-sources --public-base https://your-space.cdn.digitaloceanspaces.com
```

That copies webp thumbnails into `static/thumbs/` (gitignored) and writes a path-free `static/catalog.json`. Host the UI on DigitalOcean App Platform and the snapshot on Spaces. See [docs/hosting.md](docs/hosting.md).

## Web UI

```bash
npm --prefix frontend ci
npm --prefix frontend run build
```

The build writes `static/assets/app.js`. Hosted builds set `VITE_HOSTED=1` and `VITE_BASE=/`.

## License

Dedicated to the public domain under the [Unlicense](LICENSE). Optional model weights keep their own licenses; see [NOTICE.md](NOTICE.md).
