"""JSON sites -> in-site discovery -> page content and batch index."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

from . import __version__
from .application.batch import crawl_batch
from .domain.sites import select_sites
from .domain.urls import (
    DEFAULT_MAX_CRAWL_SECONDS,
    DEFAULT_MAX_PAGES,
    DEFAULT_MAX_QUEUE_SIZE,
    DEFAULT_MAX_REQUESTS,
    DEFAULT_MAX_SITEMAPS,
)
from .progress import ProgressReporter


def nonnegative_int(value: str) -> int:
    result = int(value)
    if result < 0:
        raise argparse.ArgumentTypeError("Must be nonnegative")
    return result


def nonnegative_float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise argparse.ArgumentTypeError("Must be finite and nonnegative")
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect in-site page content")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--sites-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("coleta"))
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--site", action="append", dest="sites_one")
    selection.add_argument("--sites", nargs="+", dest="sites_many")
    parser.add_argument("--workers", type=int, default=1)
    for option, default in (
        ("--max-pages-per-site", DEFAULT_MAX_PAGES),
        ("--max-requests-per-site", DEFAULT_MAX_REQUESTS),
        ("--max-queue-size", DEFAULT_MAX_QUEUE_SIZE),
        ("--max-sitemaps-per-site", DEFAULT_MAX_SITEMAPS),
    ):
        parser.add_argument(option, type=nonnegative_int, default=default)
    parser.add_argument(
        "--max-crawl-seconds", type=nonnegative_float, default=DEFAULT_MAX_CRAWL_SECONDS
    )
    parser.add_argument("--request-timeout", type=nonnegative_float, default=20.0)
    parser.add_argument("--crawl-max-age-hours", type=nonnegative_float, default=24.0)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--force-crawl", action="store_true")
    mode.add_argument("--recover-existing-crawls", action="store_true")
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--traceback", action="store_true")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive")
    if args.request_timeout == 0:
        parser.error("--request-timeout must be positive")
    return args


def crawl_config(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "max_pages": args.max_pages_per_site,
        "max_requests": args.max_requests_per_site,
        "max_queue_size": args.max_queue_size,
        "max_crawl_seconds": args.max_crawl_seconds,
        "max_sitemaps": args.max_sitemaps_per_site,
        "include_subdomains": False,
        "include_query_urls": False,
        "respect_robots": True,
        "request_timeout": args.request_timeout,
    }


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        configured = json.loads(args.sites_file.read_text(encoding="utf-8-sig"))
        selection = select_sites(configured, args.sites_many or args.sites_one)
        if selection.duplicates_skipped:
            print(
                f"Skipped {selection.duplicates_skipped} duplicate site entries "
                "(first occurrence kept).",
                file=sys.stderr,
            )
        reporter = ProgressReporter(enabled=not args.no_progress, stream=sys.stderr)
        batch = crawl_batch(
            selection,
            output_dir=args.output_dir,
            config=crawl_config(args),
            workers=args.workers,
            force_crawl=args.force_crawl,
            recover_existing=args.recover_existing_crawls,
            max_age_hours=args.crawl_max_age_hours,
            verbose=-1 if args.no_progress else max(1, args.verbose + 1),
            reporter=reporter,
            show_traceback=args.traceback,
        )
    except (OSError, ValueError, TypeError) as exc:
        print(f"INPUT/OUTPUT ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        f"BATCH SUMMARY: selected={batch['sites_selected']}, "
        f"completed={batch['sites_completed']}, failed={batch['sites_failed']}; "
        f"output={args.output_dir / 'batch.json'}"
    )
    return 1 if batch["sites_failed"] else 0
