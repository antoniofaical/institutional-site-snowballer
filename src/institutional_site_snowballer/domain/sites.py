"""Input validation and first-occurrence deduplication from the original CLI."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from .urls import canonicalize, evidence_directory_name, host


@dataclass(frozen=True)
class SiteSelection:
    sites: list[dict[str, str]]
    input_count: int
    duplicates_skipped: int


def select_sites(configured: object, names: list[str] | None = None) -> SiteSelection:
    if not isinstance(configured, list):
        raise TypeError("Sites file must contain a JSON list")
    unique: list[dict[str, str]] = []
    by_name: dict[str, dict[str, str]] = {}
    by_url: dict[tuple[str, int | None, str], dict[str, str]] = {}
    by_directory: set[str] = set()
    skipped = 0
    for site in configured:
        if (
            not isinstance(site, dict)
            or not isinstance(site.get("name"), str)
            or not isinstance(site.get("url"), str)
            or not site["name"].strip()
            or not site["url"].strip()
        ):
            raise ValueError("Each site needs a non-empty name and URL")
        url = canonicalize(site["url"], keep_query=False)
        if not url or not host(url):
            raise ValueError(f"Invalid site URL for {site['name']}: {site['url']}")
        parsed = urlparse(url)
        # Keep the original batch identity: ignore scheme, www, query and final /.
        url_key = (host(url), parsed.port, parsed.path.rstrip("/") or "/")
        directory = evidence_directory_name(site["name"]).casefold()
        original = by_name.get(site["name"]) or by_url.get(url_key)
        if original is not None:
            by_name[site["name"]] = original
            skipped += 1
            continue
        if directory in by_directory:
            raise ValueError("Site names collide on disk")
        if directory == "batch.json":
            raise ValueError("Site name conflicts with batch.json")
        device = directory.split(".", 1)[0].upper()
        if device in {"CON", "PRN", "AUX", "NUL"} or device in {
            f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
        }:
            raise ValueError("Site name is reserved on Windows")
        value = {"name": site["name"], "url": site["url"]}
        by_name[value["name"]] = value
        by_url[url_key] = value
        by_directory.add(directory)
        unique.append(value)
    if names and names != ["all"]:
        unknown = set(names) - by_name.keys()
        if unknown:
            raise ValueError(f"Unknown sites: {', '.join(sorted(unknown))}")
        selected = {by_name[name]["name"] for name in names}
        unique = [site for site in unique if site["name"] in selected]
    if not unique:
        raise ValueError("No sites selected")
    return SiteSelection(unique, len(configured), skipped)
