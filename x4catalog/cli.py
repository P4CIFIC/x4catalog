from __future__ import annotations

import argparse
import json
from pathlib import Path

import uvicorn

from .analysis import cluster, embed, ocr, train_preference
from .automation import automate
from .catalog import build_exact_duplicates, build_variant_candidates, export_automatic, export_images, ingest, initialize_catalog, rebuild_views
from .config import BIND_HOST, CatalogPaths, default_root, default_source
from .labeling import auto_label, download_models, reclassify_predictions
from .publish import publish
from .service import create_app


def paths_from(args: argparse.Namespace) -> CatalogPaths:
    root = Path(args.root).expanduser() if args.root else default_root()
    source = Path(args.source).expanduser() if args.source else default_source()
    static_dir = Path(args.static).expanduser() if args.static else None
    return CatalogPaths(root=root, source=source, static_dir=static_dir)


def parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--root",
        default=None,
        help="Working directory for the database, thumbnails, models, views, and exports "
        "(default: $X4CATALOG_ROOT or the current directory)",
    )
    common.add_argument(
        "--source",
        default=None,
        help="Read-only folder of 480x800 BMP files "
        "(default: $X4CATALOG_SOURCE or ./library)",
    )
    common.add_argument(
        "--static",
        default=None,
        help="Web UI files (default: $X4CATALOG_STATIC or the bundled static/ directory)",
    )
    app = argparse.ArgumentParser(
        prog="x4catalog",
        description="Local, non-destructive catalog for XTEINK X4 sleep-screen BMPs",
    )
    sub = app.add_subparsers(dest="command", required=True)
    sub.add_parser("init", parents=[common])
    command = sub.add_parser("ingest", parents=[common])
    command.add_argument("--limit", type=int)
    command.add_argument("--pilot", action="store_true")
    command.add_argument("--full", action="store_true")
    sub.add_parser("duplicates", parents=[common])
    command = sub.add_parser("variants", parents=[common])
    command.add_argument("--max-distance", type=int, default=6)
    command = sub.add_parser("embed", parents=[common])
    command.add_argument("--limit", type=int)
    command.add_argument("--batch-size", type=int, default=12)
    command = sub.add_parser("ocr", parents=[common])
    command.add_argument("--limit", type=int)
    command.add_argument("--workers", type=int, default=4)
    command = sub.add_parser("cluster", parents=[common])
    command.add_argument("--count", type=int, default=200)
    sub.add_parser("train-preference", parents=[common])
    sub.add_parser("views", parents=[common])
    sub.add_parser("download-models", parents=[common])
    command = sub.add_parser("auto-label", parents=[common])
    command.add_argument("--limit", type=int)
    command.add_argument("--batch-size", type=int, default=8)
    command.add_argument("--models", nargs="+", default=["rampp", "wd14", "nsfw", "siglip"])
    sub.add_parser("calibrate-labels", parents=[common])
    command = sub.add_parser("automate", parents=[common])
    command.add_argument("--label-limit", type=int)
    command.add_argument("--batch-size", type=int, default=8)
    command.add_argument("--export-all", action="store_true")
    command = sub.add_parser("export", parents=[common])
    command.add_argument("name")
    command.add_argument("image_ids", nargs="+", type=int)
    command = sub.add_parser("serve", parents=[common])
    command.add_argument("--port", type=int, default=8765)
    command = sub.add_parser("publish", parents=[common])
    command.add_argument("--skip-sources", action="store_true", help="Copy thumbnails and catalog.json only")
    command.add_argument(
        "--public-base",
        default="",
        help="Absolute URL prefix for hosted thumbs and sources (DigitalOcean Spaces CDN)",
    )
    command.add_argument("--concurrency", type=int, default=8)
    return app


def main() -> None:
    args = parser().parse_args()
    paths = paths_from(args)
    if args.command == "init":
        result = initialize_catalog(paths)
    elif args.command == "ingest":
        if args.pilot and args.full:
            raise SystemExit("Choose either --pilot or --full, not both")
        if not args.pilot and not args.full:
            raise SystemExit("Specify --pilot for a bounded run or --full after freeing 50 GiB")
        pilot_limit = args.limit if args.limit is not None else 500
        result = ingest(paths, limit=pilot_limit if args.pilot else args.limit, full=args.full, pilot=args.pilot)
    elif args.command == "duplicates":
        result = {"exact_groups": build_exact_duplicates(paths)}
    elif args.command == "variants":
        result = {"candidates": build_variant_candidates(paths, args.max_distance)}
    elif args.command == "embed":
        result = embed(paths, batch_size=args.batch_size, limit=args.limit).__dict__
    elif args.command == "ocr":
        result = {"processed": ocr(paths, args.limit, workers=args.workers)}
    elif args.command == "cluster":
        result = {"cluster_count": cluster(paths, args.count)}
    elif args.command == "train-preference":
        result = {"model_id": train_preference(paths)}
    elif args.command == "views":
        result = {"symlink_count": rebuild_views(paths)}
    elif args.command == "download-models":
        result = download_models(paths)
    elif args.command == "auto-label":
        result = auto_label(paths, models=args.models, batch_size=args.batch_size, limit=args.limit)
    elif args.command == "calibrate-labels":
        result = reclassify_predictions(paths)
    elif args.command == "automate":
        result = automate(paths, export_all=args.export_all, label_limit=args.label_limit, batch_size=args.batch_size)
    elif args.command == "export":
        result = export_images(paths, args.name, args.image_ids)
    elif args.command == "publish":
        result = publish(
            paths,
            include_sources=not args.skip_sources,
            concurrency=args.concurrency,
            public_base=args.public_base,
            progress=lambda message: print(message),
        )
    elif args.command == "serve":
        initialize_catalog(paths)
        if not (paths.static / "index.html").is_file():
            raise SystemExit(
                f"Web UI not found at {paths.static}. Run from a git clone of this repository "
                "or pass --static /path/to/static."
            )
        # Loopback only: this app has no authentication and can read the local image library.
        uvicorn.run(create_app(paths), host=BIND_HOST, port=args.port, log_level="info")
        return
    else:
        raise AssertionError(args.command)
    print(json.dumps(result if isinstance(result, dict) else result.__dict__, indent=2, default=str))
