# Security policy

The **local catalog** is a loopback-only tool. It is not designed to be
exposed to a network, and it has no authentication.

The **public site** is a static snapshot. It must not run FastAPI, OCR, or
labeling in production.

## Supported versions

Security fixes are accepted against the default branch.

## How to report a vulnerability

Please **do not** open a public issue for a vulnerability that could expose
someone's image library, device files, or local filesystem.

Use GitHub's private vulnerability reporting on this repository instead:

1. Open the repository's **Security** tab.
2. Choose **Report a vulnerability**.
3. Include steps to reproduce, affected versions, and the impact.

If private reporting is unavailable, open a GitHub issue that describes the
class of problem without a working exploit.

## What this project guarantees

- The review server binds to `127.0.0.1` only. There is no option to listen
  on a LAN or public interface.
- Source BMPs are never modified, renamed, or deleted by the catalog.
- A local catalog does not upload your library. Publishing a snapshot is an
  explicit command (`x4catalog publish`).
- FastAPI's interactive docs are disabled.

## What operators must not do

- Do not put the local server behind a reverse proxy, tunnel, or port forward.
- Do not bind it to `0.0.0.0` or another host. The CrossPoint proxy will
  make HTTP requests to a user-supplied hostname; that is only acceptable
  because the app is loopback-only and unauthenticated.
- Do not commit SQLite databases, thumbnails, exports, device backups, or
  `.env` files. Those paths are gitignored because they are private data.

## Scope

In scope: path traversal, source-library escape, CrossPoint host/path
validation, accidental network exposure, secret leakage in the repository.

Out of scope: running the local server on a public host, CrossPoint firmware
bugs, and third-party model weights downloaded from Hugging Face.
