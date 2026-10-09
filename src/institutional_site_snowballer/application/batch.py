"""Independent crawl jobs and a complete, ordered batch-content index."""

from __future__ import annotations

import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .. import __version__
from ..domain.sites import SiteSelection
from ..domain.urls import evidence_directory_name
from ..progress import ProgressReporter
from ..storage import read_json, read_jsonl, sha256_file, timestamp, write_json
from .crawl import scrape_site
from .crawl_state import recent_crawl, recover, write_state

BATCH_SCHEMA_VERSION = 1
SOURCE_REVISION = "dbd6c4cc4fb35bb820205b500b2bdf67eb84b34b"


def pending_entry(site: dict[str, str]) -> dict[str, Any]:
    return {
        **site,
        "status": "pending",
        "operation": None,
        "evidence_path": None,
        "manifest_path": None,
        "crawl_state_path": None,
        "evidence_sha256": None,
        "manifest_sha256": None,
        "pages_saved": 0,
        "has_text": False,
        "evidence_is_partial": None,
        "failed_stage": None,
        "error": None,
        "failed_attempt_path": None,
    }


def collect_site(
    site: dict[str, str],
    *,
    output_dir: Path,
    config: dict[str, Any],
    force_crawl: bool,
    recover_existing: bool,
    max_age_hours: float,
    verbose: int,
    message: Callable[[str], None] | None,
) -> dict[str, Any]:
    directory = output_dir / evidence_directory_name(site["name"])
    if message:
        message(f"[{site['name']}] crawl START {site['url']}")
    if recover_existing:
        recover(site, directory, config)
        operation = "recovered"
    elif not force_crawl and recent_crawl(site, directory, config, max_age_hours):
        operation = "reused"
    else:
        directory = scrape_site(
            site_name=site["name"],
            root_url=site["url"],
            evidence_root=output_dir,
            verbose=verbose,
            log_callback=message,
            **config,
        )
        write_state(site, directory, config)
        operation = "crawled"
    manifest = read_json(directory / "manifest.json")
    records = read_jsonl(directory / "evidence.jsonl")
    if len(records) != manifest.get("pages_saved") or not records:
        raise ValueError("Crawl page count mismatch")
    if manifest.get("site_name") != site["name"]:
        raise ValueError("Crawl identity mismatch")
    if any(not isinstance(record.get("text"), str) for record in records):
        raise ValueError("Invalid crawl page text")
    result = pending_entry(site)
    result.update(
        status="completed",
        operation=operation,
        evidence_path=(directory / "evidence.jsonl").relative_to(output_dir).as_posix(),
        manifest_path=(directory / "manifest.json").relative_to(output_dir).as_posix(),
        crawl_state_path=(directory / "crawl_state.json")
        .relative_to(output_dir)
        .as_posix(),
        evidence_sha256=sha256_file(directory / "evidence.jsonl"),
        manifest_sha256=sha256_file(directory / "manifest.json"),
        pages_saved=len(records),
        has_text=any(record["text"].strip() for record in records),
        evidence_is_partial=bool(
            manifest.get("crawl_limited") or manifest.get("page_errors")
        ),
    )
    if message:
        message(
            f"[{site['name']}] {operation}: pages={result['pages_saved']}; "
            f"partial={result['evidence_is_partial']}"
        )
    return result


def crawl_batch(
    selection: SiteSelection,
    *,
    output_dir: Path,
    config: dict[str, Any],
    workers: int = 1,
    force_crawl: bool = False,
    recover_existing: bool = False,
    max_age_hours: float = 24,
    verbose: int = 1,
    reporter: ProgressReporter | None = None,
    show_traceback: bool = False,
) -> dict[str, Any]:
    if workers < 1:
        raise ValueError("Workers must be positive")
    if force_crawl and recover_existing:
        raise ValueError("Recovery cannot be combined with force crawl")
    reporter = reporter or ProgressReporter(enabled=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    entries = [pending_entry(site) for site in selection.sites]
    batch = {
        "schema_version": BATCH_SCHEMA_VERSION,
        "producer": {
            "name": "institutional-site-snowballer",
            "version": __version__,
            "source_revision": SOURCE_REVISION,
        },
        "status": "running",
        "created_at": timestamp(),
        "completed_at": None,
        "input_count": selection.input_count,
        "duplicates_skipped": selection.duplicates_skipped,
        "sites_selected": len(entries),
        "sites_completed": 0,
        "sites_failed": 0,
        "sites": entries,
    }
    destination = output_dir / "batch.json"
    write_json(destination, batch)
    stage = "crawl_recovery" if recover_existing else "crawl"
    reporter.begin(stage, len(entries))
    try:
        with ThreadPoolExecutor(max_workers=min(workers, len(entries))) as executor:
            futures = {
                executor.submit(
                    collect_site,
                    site,
                    output_dir=output_dir,
                    config=config,
                    force_crawl=force_crawl,
                    recover_existing=recover_existing,
                    max_age_hours=max_age_hours,
                    verbose=verbose,
                    message=reporter.message if reporter.enabled else None,
                ): index
                for index, site in enumerate(selection.sites)
            }
            for future in as_completed(futures):
                index = futures[future]
                try:
                    entries[index] = future.result()
                    batch["sites_completed"] += 1
                except Exception as exc:  # noqa: BLE001 - isolate each site's failure
                    result = pending_entry(selection.sites[index])
                    result.update(
                        status="failed",
                        failed_stage=stage,
                        error={"type": type(exc).__name__, "message": str(exc)},
                    )
                    attempt = getattr(exc, "attempt_dir", None)
                    if attempt is not None:
                        result["failed_attempt_path"] = attempt.relative_to(
                            output_dir
                        ).as_posix()
                    entries[index] = result
                    batch["sites_failed"] += 1
                    reporter.message(
                        f"[{result['name']}] FAILED: {type(exc).__name__}: {exc}"
                    )
                    if show_traceback:
                        reporter.message(traceback.format_exc())
                write_json(destination, batch)
                reporter.advance(
                    stage,
                    site=entries[index]["name"],
                    failed=entries[index]["status"] == "failed",
                )
    finally:
        reporter.finish()
    batch["status"] = (
        "completed_with_failures" if batch["sites_failed"] else "completed"
    )
    batch["completed_at"] = timestamp()
    write_json(destination, batch)
    return batch
