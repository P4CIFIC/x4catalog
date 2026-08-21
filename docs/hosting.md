# Hosting

One provider: **DigitalOcean**.

| Piece | Where |
| --- | --- |
| Public site (SPA) | App Platform static site from this repo |
| Thumbnails, optional BMPs, `catalog.json` | Spaces (S3-compatible) + Spaces CDN |
| Domain | `x4catalog.com` / `www.x4catalog.com` |

Do not put the 15k+ thumbnail files in git. App Platform builds the UI from `frontend/`; Spaces serves the snapshot.

## 1. Spaces

Create a Space named `x4catalog` (region of your choice, file listing off, CDN on). Create a Spaces access key limited to that bucket. Put the secret in your shell, never in the repo.

```bash
export AWS_ACCESS_KEY_ID="…"
export AWS_SECRET_ACCESS_KEY="…"
export SPACES_ENDPOINT="https://nyc3.digitaloceanspaces.com"
export SPACES_BUCKET="x4catalog"
export PUBLIC_BASE="https://x4catalog.nyc3.cdn.digitaloceanspaces.com"
```

Publish locally, then sync:

```bash
uv run x4catalog publish --skip-sources --public-base "$PUBLIC_BASE"
aws s3 sync static/thumbs "s3://$SPACES_BUCKET/thumbs" --endpoint-url "$SPACES_ENDPOINT" --acl public-read
aws s3 cp static/catalog.json "s3://$SPACES_BUCKET/catalog.json" --endpoint-url "$SPACES_ENDPOINT" --acl public-read --content-type application/json
```

`static/catalog-url.json` will then point at `$PUBLIC_BASE/catalog.json`. Commit that small pointer if the CDN URL is stable; do not commit `catalog.json` or `thumbs/`.

CORS on the Space should allow `GET` from `https://x4catalog.com` and `https://www.x4catalog.com`.

## 2. App Platform

`.do/app.yaml` is the spec. After the GitHub repo is `P4CIFIC/x4catalog` and public:

```bash
doctl apps create --spec .do/app.yaml
```

Build env: `VITE_HOSTED=1`, `VITE_BASE=/`. Catch-all document is `index.html` so `/browse`, `/device`, and `/docs` resolve.

When DNS for `x4catalog.com` is live, add the domains in the App Platform spec and point the registrar at DigitalOcean's nameservers or the CNAME App Platform gives you.

## 3. What not to host

- The FastAPI catalog. It is loopback-only and has no auth.
- OCR, labeling, or conversion workers. Those stay local until the cloud-ingest issue is designed.
- Original libraries. `--skip-sources` is the default public snapshot.

Vercel remains a possible static host for the SPA only. It is not the primary host, and it cannot store this thumbnail set without a separate object store.
