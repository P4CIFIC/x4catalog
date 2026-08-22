# Hosting

One provider: **DigitalOcean**.

| Piece | Where |
| --- | --- |
| Public site (SPA) | App Platform static site from this repo |
| Thumbnails, optional BMPs, `catalog.json` | Spaces (S3-compatible) + Spaces CDN |
| Domain | `x4catalog.com` / `www.x4catalog.com` |

Do not put the 15k+ thumbnail files in git. App Platform builds the UI from `frontend/`; Spaces serves the snapshot.

## 1. Spaces

Create a Space named `x4catalog` (region of your choice, file listing off, CDN on).

Spaces access keys are **not** inside the Space file listing. In the
DigitalOcean control panel, open **Spaces Object Storage** in the left
menu, then the **Access Keys** tab. Create a key limited to the
`x4catalog` bucket. The secret is shown only once; if you lose it, use
**… → Regenerate key** on that row. Put the secret in your shell, never
in the repo.

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

`.do/app.yaml` is the spec. `deploy_on_push` is **off**. A merge to public
`main` must not ship production.

```bash
doctl apps create --spec .do/app.yaml
```

Build env: `VITE_HOSTED=1`, `VITE_BASE=/`. Catch-all document is `index.html` so `/browse`, `/device`, and `/docs` resolve.

Ship a build from GitHub: **Actions → Deploy production → Run workflow**,
or publish a GitHub Release. That job uses the `production` environment
(required reviewer, `main` only) and
`DIGITALOCEAN_ACCESS_TOKEN` (an App Platform token stored as a GitHub
Actions secret). You can also deploy locally with
`doctl apps create-deployment <app-id>`.

When DNS for `x4catalog.com` is live, add the domains in the App Platform spec. Websupport should CNAME `www` to the App Platform hostname and ANAME `@` the same way. Do not leave **Websupport webb** parking on; it injects virtual A/AAAA records that fight the App Platform certificate.

## 3. What not to host

- The FastAPI catalog. It is loopback-only and has no auth.
- OCR, labeling, or conversion workers. Those stay local until the cloud-ingest issue is designed.
- Original libraries. `--skip-sources` is the default public snapshot unless you explicitly publish BMPs.
