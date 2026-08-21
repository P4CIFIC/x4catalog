# Content policy

X4 Catalog is two things:

1. **The software.** A local, loopback-only catalog you run on your own machine.
2. **The public gallery.** A snapshot we host at [x4catalog.com](https://www.x4catalog.com) so people can browse images prepared for the XTEINK X4.

## Local copies

Your library is yours. This project does not upload it. Do not open a pull request that includes SQLite databases, thumbnails, originals, OCR text from a private library, or device backups.

## Public gallery

The hosted gallery is a curated snapshot, not an open upload form.

- Images are 480×800 sleep-screen BMPs (or webp previews of them).
- Sensitive tags (`nsfw`, nudity, sexualized content, gore, graphic violence) are hidden by default. Visitors can turn them on.
- We do not claim copyright on images in the gallery. If you own an image and want it taken down, open an issue titled `takedown` with enough information to find it.
- Do not submit material that is illegal to host.

## What is not in this repository

Processing, conversion, OCR, and automatic labeling stay on the maintainer's machine for now. Cloud ingest, user submissions, and format conversion are out of scope until they are designed without turning the public host into an unbounded image pipeline. See the tracking issue in this repository.
