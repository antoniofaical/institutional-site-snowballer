"""Discovery must preserve scope, full text, coverage and deduplicated links."""

import gzip
from io import BytesIO
from itertools import count

import pytest
from http_fakes import install_http, response

from institutional_site_snowballer.adapters import extract
from institutional_site_snowballer.application import crawl
from institutional_site_snowballer.storage import read_json, read_jsonl


def test_sitemap_and_link_expansion_respects_robots_and_scope(tmp_path, monkeypatch):
    root = "https://company.test/"
    pages = {
        root + "robots.txt": response(
            root + "robots.txt",
            "User-agent: *\nDisallow: /private\nSitemap: https://company.test/catalog.xml",
        ),
        root + "catalog.xml": response(
            root + "catalog.xml",
            "<urlset><url><loc>https://company.test/product</loc></url>"
            "<url><loc>https://other.test/</loc></url></urlset>",
            content_type="application/xml",
        ),
        root: response(
            root,
            '<p>Home</p><a href="/private">Private</a>'
            '<a href="/about">About</a><a href="https://other.test/">External</a>'
            '<a href="https://sub.company.test/">Subdomain</a>',
        ),
        root + "product": response(
            root + "product", '<p>Product</p><a href="/details">Details</a>'
        ),
        root + "about": response(root + "about", "About", content_type="text/plain"),
        root + "details": response(
            root + "details", "Details", content_type="text/plain"
        ),
    }
    calls = install_http(monkeypatch, pages)
    directory = crawl.scrape_site(
        site_name="Company", root_url=root, evidence_root=tmp_path
    )
    urls = {record["url"] for record in read_jsonl(directory / "evidence.jsonl")}
    assert urls == {root, root + "product", root + "about", root + "details"}
    assert root + "private" not in calls
    assert "https://other.test/" not in calls
    assert "https://sub.company.test/" not in calls


def test_duplicate_text_does_not_discard_unique_iframe_links(tmp_path, monkeypatch):
    root = "https://company.test/"
    install_http(
        monkeypatch,
        {
            root: response(root, '<p>Home</p><a href="/a">A</a><a href="/b">B</a>'),
            root + "a": response(
                root + "a", '<p>Shared</p><iframe src="/child-a"></iframe>'
            ),
            root + "b": response(
                root + "b", '<p>Shared</p><iframe src="/child-b"></iframe>'
            ),
            root + "child-a": response(root + "child-a", "<p>Child A</p>"),
            root + "child-b": response(root + "child-b", "<p>Child B</p>"),
        },
    )
    directory = crawl.scrape_site(
        site_name="Company", root_url=root, evidence_root=tmp_path
    )
    records = read_jsonl(directory / "evidence.jsonl")
    urls = {record["url"] for record in records}
    assert root + "child-a" in urls and root + "child-b" in urls
    assert len(records) == 4
    assert (
        read_json(directory / "manifest.json")["urls_skipped_by_reason"][
            "duplicate_content"
        ]
        == 1
    )


@pytest.mark.parametrize(
    "limits,reason",
    [
        ({"max_requests": 1}, "request_limit"),
        ({"max_queue_size": 1}, "queue_limit"),
        ({"max_sitemaps": 1}, "sitemap_limit"),
    ],
)
def test_limits_are_visible(tmp_path, monkeypatch, limits, reason):
    root = "https://company.test/"
    install_http(
        monkeypatch,
        {root: response(root, '<p>Home</p><a href="/a">A</a><a href="/b">B</a>')},
    )
    directory = crawl.scrape_site(
        site_name="Company", root_url=root, evidence_root=tmp_path, **limits
    )
    manifest = read_json(directory / "manifest.json")
    assert manifest["crawl_limited"] is True
    assert reason in manifest["crawl_limit_reasons"]


def test_time_limit_keeps_partial_content(tmp_path, monkeypatch):
    root = "https://company.test/"
    clock = count()
    monkeypatch.setattr(crawl.time, "monotonic", lambda: next(clock))
    install_http(monkeypatch, {root: response(root, '<p>Home</p><a href="/a">A</a>')})
    directory = crawl.scrape_site(
        site_name="Company", root_url=root, evidence_root=tmp_path, max_crawl_seconds=5
    )
    assert len(read_jsonl(directory / "evidence.jsonl")) == 1
    assert "time_limit" in read_json(directory / "manifest.json")["crawl_limit_reasons"]


def test_extraction_retains_original_text_contract_and_language():
    html = '<html lang="pt-BR"><title>Title</title>'
    html += '<meta name="description" content="Description">'
    html += "<body><p>Full text</p><script>script excluded</script>"
    html += '<iframe src="/frame"></iframe></body></html>'
    text, links = extract.html_text_and_links("https://x.test/", html)
    assert text == "Title\nDescription\nTitle Full text"
    assert links == {"https://x.test/frame"}
    page = response("https://x.test/", html)
    assert extract.response_language_hint(page) == "pt-BR"
    page.headers["content-language"] = "en-US"
    assert extract.response_language_hint(page) == "en-US"


def test_pdf_optional_dependency_can_be_absent(monkeypatch):
    monkeypatch.setattr(extract, "PdfReader", None)
    pdf = response("https://x.test/file.pdf", "fake", content_type="application/pdf")
    assert extract.extract_response(pdf) == ("", set())


def test_gzip_sitemap_index_expands_nested_pages(tmp_path, monkeypatch):
    root = "https://company.test/"
    index_url = root + "sitemap.xml"
    child_url = root + "pages.xml.gz"
    index = response(
        index_url,
        f"<sitemapindex><sitemap><loc>{child_url}</loc></sitemap></sitemapindex>",
        content_type="application/xml",
    )
    child = response(child_url, content_type="application/xml")
    child._content = gzip.compress(
        f"<urlset><url><loc>{root}product</loc></url></urlset>".encode()
    )
    calls = install_http(
        monkeypatch,
        {
            index_url: index,
            child_url: child,
            root: response(root, "<p>Home</p>"),
            root + "product": response(root + "product", "<p>Product</p>"),
        },
    )
    directory = crawl.scrape_site(
        site_name="Company", root_url=root, evidence_root=tmp_path
    )
    assert child_url in calls
    assert {page["url"] for page in read_jsonl(directory / "evidence.jsonl")} == {
        root,
        root + "product",
    }


def test_real_textual_pdf_extraction():
    from pypdf import PdfWriter
    from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

    writer = PdfWriter()
    page = writer.add_blank_page(width=200, height=200)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        }
    )
    stream = DecodedStreamObject()
    stream.set_data(b"BT /F1 12 Tf 10 150 Td (Institutional site content) Tj ET")
    page[NameObject("/Contents")] = stream
    buffer = BytesIO()
    writer.write(buffer)
    pdf = response("https://x.test/file.pdf", content_type="application/pdf")
    pdf._content = buffer.getvalue()
    assert extract.extract_response(pdf) == ("Institutional site content", set())
