from concurrent.futures import ThreadPoolExecutor
from io import StringIO

from institutional_site_snowballer import progress
from institutional_site_snowballer.progress import ProgressReporter


class Terminal(StringIO):
    def isatty(self):
        return True


def test_concurrent_crawl_progress(monkeypatch):
    monkeypatch.setattr(progress, "_terminal_color", lambda stream: True)
    stream = Terminal()
    reporter = ProgressReporter(stream=stream)
    reporter.begin("crawl", 20)
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda _: reporter.advance("crawl"), range(20)))
    assert "CRAWL PROGRESS: 20/20" in stream.getvalue()
    assert "\x1b[36m" in stream.getvalue()


def test_plain_logs_and_no_progress(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    stream = StringIO()
    reporter = ProgressReporter(stream=stream)
    reporter.begin("crawl", 1)
    reporter.advance("crawl", failed=True)
    assert "failed=1" in stream.getvalue()
    assert "\x1b[" not in stream.getvalue()
    quiet = StringIO()
    reporter = ProgressReporter(enabled=False, stream=quiet)
    reporter.begin("crawl", 1)
    reporter.advance("crawl")
    reporter.finish()
    assert quiet.getvalue() == ""
