"""The content handoff preserves full pages, identity, cache and failures."""

import json
from pathlib import Path

import pytest
from http_fakes import install_http, response

from institutional_site_snowballer import cli
from institutional_site_snowballer.storage import read_json, read_jsonl, sha256_file


def run_cli(tmp_path, sites, *options):
    path = tmp_path / "sites.json"
    path.write_text(json.dumps(sites), encoding="utf-8")
    output = tmp_path / "content"
    code = cli.main(
        ["--sites-file", str(path), "--output-dir", str(output), "--no-progress"]
        + list(options)
    )
    return code, read_json(output / "batch.json"), output


def test_complete_content_with_failure_and_concurrent_workers(tmp_path, monkeypatch):
    root = "https://company.test/"
    failed = "https://failed.test/"
    content = "Árvore conteúdo sem truncar. " * 2_000
    install_http(
        monkeypatch,
        {
            root: response(
                root, '<html lang="pt-BR"><a href="/product">Product</a></html>'
            ),
            root + "product": response(root + "product", f"<p>{content}</p>"),
            failed: response(failed, status=503),
        },
    )
    code, batch, output = run_cli(
        tmp_path,
        [{"name": "Empresa A", "url": root}, {"name": "Empresa B", "url": failed}],
        "--workers",
        "2",
    )
    assert code == 1
    assert batch["status"] == "completed_with_failures"
    assert batch["sites_completed"] == batch["sites_failed"] == 1
    success, failure = batch["sites"]
    assert [entry["name"] for entry in batch["sites"]] == ["Empresa A", "Empresa B"]
    assert success["operation"] == "crawled"
    evidence = output / success["evidence_path"]
    records = read_jsonl(evidence)
    assert success["pages_saved"] == len(records) == 2
    product = next(record for record in records if record["url"].endswith("/product"))
    assert product["text"] == content.strip()
    assert set(product) == {"url", "content_type", "language_hint", "text"}
    assert records[0]["language_hint"] == "pt-BR"
    assert success["evidence_sha256"] == sha256_file(evidence)
    assert success["manifest_sha256"] == sha256_file(output / success["manifest_path"])
    assert not Path(success["evidence_path"]).is_absolute()
    assert failure["status"] == "failed" and failure["error"]
    for key in ("evidence_path", "manifest_path", "evidence_sha256"):
        assert failure[key] is None
    assert (output / failure["failed_attempt_path"] / "manifest.json").is_file()


def test_cache_force_and_changed_configuration(tmp_path, monkeypatch):
    root = "https://company.test/"
    calls = install_http(monkeypatch, {root: response(root, "<p>Company</p>")})
    sites = [{"name": "Company", "url": root}]
    _, first, _ = run_cli(tmp_path, sites)
    requests_before = len(calls)
    _, reused, _ = run_cli(tmp_path, sites)
    assert len(calls) == requests_before
    assert reused["sites"][0]["operation"] == "reused"
    assert first["sites"][0]["evidence_sha256"] == reused["sites"][0]["evidence_sha256"]
    run_cli(tmp_path, sites, "--force-crawl")
    assert len(calls) > requests_before
    requests_before = len(calls)
    run_cli(tmp_path, sites, "--max-pages-per-site", "20")
    assert len(calls) > requests_before


def test_failed_refresh_never_indexes_previous_content_as_current(
    tmp_path, monkeypatch
):
    root = "https://company.test/"
    sites = [{"name": "Company", "url": root}]
    install_http(monkeypatch, {root: response(root, "<p>Previously collected</p>")})
    _, old, output = run_cli(tmp_path, sites)
    old_evidence = output / old["sites"][0]["evidence_path"]
    original_hash = sha256_file(old_evidence)
    install_http(monkeypatch, {})
    code, current, _ = run_cli(tmp_path, sites, "--force-crawl")
    assert code == 1
    assert current["sites"][0]["status"] == "failed"
    assert current["sites"][0]["evidence_path"] is None
    assert current["sites"][0]["operation"] is None
    assert sha256_file(old_evidence) == original_hash


def test_recovery_is_offline_and_preserves_timestamp(tmp_path, monkeypatch):
    root = "https://company.test/"
    sites = [{"name": "Company", "url": root}]
    calls = install_http(monkeypatch, {root: response(root, "<p>Company</p>")})
    _, first, output = run_cli(tmp_path, sites)
    entry = first["sites"][0]
    manifest_time = read_json(output / entry["manifest_path"])["created_at"]
    (output / entry["crawl_state_path"]).unlink()
    requests_before = len(calls)
    code, recovered, _ = run_cli(tmp_path, sites, "--recover-existing-crawls")
    assert code == 0
    assert len(calls) == requests_before
    assert recovered["sites"][0]["operation"] == "recovered"
    state = read_json(output / recovered["sites"][0]["crawl_state_path"])
    assert state["completed_at"] == manifest_time


def test_partial_evidence_is_available_and_marked_partial(tmp_path, monkeypatch):
    root = "https://company.test/"
    install_http(
        monkeypatch, {root: response(root, '<p>Home</p><a href="/product">Product</a>')}
    )
    code, batch, output = run_cli(
        tmp_path, [{"name": "Company", "url": root}], "--max-pages-per-site", "1"
    )
    assert code == 0
    entry = batch["sites"][0]
    assert entry["status"] == "completed" and entry["evidence_is_partial"] is True
    assert (
        "page_limit"
        in read_json(output / entry["manifest_path"])["crawl_limit_reasons"]
    )


def test_hash_tampering_invalidates_cache(tmp_path, monkeypatch):
    root = "https://company.test/"
    sites = [{"name": "Company", "url": root}]
    calls = install_http(monkeypatch, {root: response(root, "<p>Company</p>")})
    _, first, output = run_cli(tmp_path, sites)
    evidence = output / first["sites"][0]["evidence_path"]
    evidence.write_text("tampered", encoding="utf-8")
    requests_before = len(calls)
    code, refreshed, _ = run_cli(tmp_path, sites)
    assert code == 0 and len(calls) > requests_before
    assert refreshed["sites"][0]["operation"] == "crawled"
    assert "Company" in read_jsonl(evidence)[0]["text"]


def test_pending_index_exists_before_work_starts(tmp_path, monkeypatch):
    from institutional_site_snowballer.application import batch as application

    root = "https://company.test/"
    snapshots = []
    original = application.scrape_site

    def inspecting_scraper(**kwargs):
        snapshots.append(read_json(tmp_path / "content/batch.json"))
        return original(**kwargs)

    monkeypatch.setattr(application, "scrape_site", inspecting_scraper)
    install_http(monkeypatch, {root: response(root, "<p>Company</p>")})
    run_cli(tmp_path, [{"name": "Company", "url": root}])
    assert snapshots[0]["status"] == "running"
    assert snapshots[0]["sites"][0]["status"] == "pending"
    assert snapshots[0]["sites"][0]["evidence_path"] is None


def test_recovery_cannot_relabel_a_limited_crawl(tmp_path, monkeypatch):
    root = "https://company.test/"
    sites = [{"name": "Company", "url": root}]
    install_http(monkeypatch, {root: response(root, '<p>Home</p><a href="/p">P</a>')})
    run_cli(tmp_path, sites, "--max-pages-per-site", "1")
    code, batch, _ = run_cli(tmp_path, sites, "--recover-existing-crawls")
    assert code == 1
    assert batch["sites"][0]["status"] == "failed"
    assert "configuration differs" in batch["sites"][0]["error"]["message"]


def test_recovery_rejects_empty_text(tmp_path, monkeypatch):
    root = "https://company.test/"
    sites = [{"name": "Company", "url": root}]
    install_http(monkeypatch, {root: response(root, "<p>Company</p>")})
    _, first, output = run_cli(tmp_path, sites)
    entry = first["sites"][0]
    (output / entry["evidence_path"]).write_text(
        json.dumps({"url": root, "text": ""}) + "\n", encoding="utf-8"
    )
    code, batch, _ = run_cli(tmp_path, sites, "--recover-existing-crawls")
    assert code == 1 and batch["sites"][0]["evidence_path"] is None
    assert "No textual evidence" in batch["sites"][0]["error"]["message"]


def test_invalid_json_creates_no_output(tmp_path, capsys):
    path = tmp_path / "sites.json"
    path.write_text("not json", encoding="utf-8")
    output = tmp_path / "out"
    assert cli.main(["--sites-file", str(path), "--output-dir", str(output)]) == 2
    assert not output.exists()
    assert "INPUT/OUTPUT ERROR" in capsys.readouterr().err


@pytest.mark.parametrize(
    "options",
    [
        ["--workers", "0"],
        ["--request-timeout", "0"],
        ["--max-crawl-seconds", "nan"],
        ["--force-crawl", "--recover-existing-crawls"],
    ],
)
def test_invalid_options(options):
    with pytest.raises(SystemExit):
        cli.parse_args(["--sites-file", "sites.json"] + options)
