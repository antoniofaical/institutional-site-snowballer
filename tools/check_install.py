"""Exercise the installed command against a local site, without the source tree."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread

from institutional_site_snowballer import __version__


def main() -> None:
    assert __version__ == "0.1.0"
    for module in ("startup_adherence", "jsonschema", "pypdf"):
        assert importlib.util.find_spec(module) is None, module
    full_text = "Conteúdo integral. " * 3_000

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                status, content = (
                    200,
                    '<html lang="pt-BR"><a href="/product">Product</a></html>',
                )
            elif self.path == "/product":
                status, content = 200, f"<p>{full_text}</p>"
            elif self.path == "/failed":
                status, content = 503, "Unavailable"
            else:
                status, content = 404, "Not found"
            body = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with TemporaryDirectory() as temporary:
            work = Path(temporary)
            root = f"http://127.0.0.1:{server.server_port}/"
            (work / "sites.json").write_text(
                json.dumps(
                    [
                        {"name": "Company", "url": root},
                        {"name": "Failure", "url": root + "failed"},
                    ]
                ),
                encoding="utf-8",
            )
            executable = Path(sys.executable).parent / (
                "institutional-site-snowballer.exe"
                if os.name == "nt"
                else "institutional-site-snowballer"
            )
            env = dict(os.environ)
            env.pop("PYTHONPATH", None)
            result = subprocess.run(
                [
                    str(executable),
                    "--sites-file",
                    "sites.json",
                    "--output-dir",
                    "content",
                    "--workers",
                    "2",
                    "--no-progress",
                ],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert result.returncode == 1, (result.stdout, result.stderr)
            batch = json.loads(
                (work / "content/batch.json").read_text(encoding="utf-8")
            )
            assert batch["schema_version"] == 1
            assert batch["sites_completed"] == batch["sites_failed"] == 1
            success, failure = batch["sites"]
            pages = [
                json.loads(line)
                for line in (work / "content" / success["evidence_path"])
                .read_text(encoding="utf-8")
                .splitlines()
            ]
            assert len(pages) == 2
            assert (
                next(page["text"] for page in pages if page["url"].endswith("/product"))
                == full_text.strip()
            )
            assert failure["status"] == "failed" and failure["evidence_path"] is None
            assert "PROGRESS" not in result.stderr
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    print(
        "Installed wheel OK: independent CLI, complete page content, and mixed-success batch."
    )


if __name__ == "__main__":
    main()
