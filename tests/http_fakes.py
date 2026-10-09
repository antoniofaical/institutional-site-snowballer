"""HTTP response fixtures shared by batch and discovery tests."""

import requests

from institutional_site_snowballer.application import crawl


def response(url, text="", status=200, content_type="text/html"):
    value = requests.Response()
    value.url = url
    value.status_code = status
    value.encoding = "utf-8"
    value._content = text.encode("utf-8")
    value.headers["content-type"] = content_type
    return value


def install_http(monkeypatch, pages):
    calls = []

    class Session:
        def __init__(self):
            self.headers = {}

        def get(self, url, *, timeout):
            calls.append(url)
            return pages.get(url, response(url, status=404))

    monkeypatch.setattr(crawl.requests, "Session", Session)
    return calls
