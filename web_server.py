#!/usr/bin/env python3
"""Startet einen lokalen Webserver für das Rechnungs-Frontend."""

from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent / "web"), **kwargs)


def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 8080), Handler)
    print("Web-App läuft unter http://127.0.0.1:8080")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
