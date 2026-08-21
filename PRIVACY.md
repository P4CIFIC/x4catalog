# Privacy

X4 Catalog is local-first. A copy you host on your machine is yours.

## What stays on your computer

- Original 480×800 BMP files in the source folder you configure
- The SQLite catalog, thumbnails, views, exports, and run logs
- Optional on-device ML weights after `download-models`
- CrossPoint transfers on your local network

The catalog never creates sidecars next to source BMPs and never writes
back into the source folder.

## What leaves your computer

Nothing from your image library is uploaded unless you run
`x4catalog publish` yourself.

The only other intentional network use is:

- Installing Python or Node packages from their public registries
- One-time downloads of public model packages if you opt into the ML extra
- Talking to a CrossPoint device you name, on your local network

There is no telemetry, no analytics, and no account.

## Public gallery

[x4catalog.com](https://www.x4catalog.com) serves a curated snapshot that
the maintainers publish. It is not your local catalog. Sensitive tags are
hidden by default. See [CONTENT.md](CONTENT.md).

## Your catalog is not this repository

Do not publish your working directory. Databases, thumbnails, views,
exports, models, and device backups are gitignored so they are not
committed by accident.
