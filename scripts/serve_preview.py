#!/usr/bin/env python3
"""Локальный превью-сервер для sites/ и orgs/ (parser-kart root)."""
from __future__ import annotations

import argparse
import http.server
import socketserver
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PORT = 8777


class PreviewHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[preview] {self.address_string()} - {fmt % args}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Preview parser-kart sites locally")
    parser.add_argument("-p", "--port", type=int, default=DEFAULT_PORT)
    parser.add_argument(
        "--open",
        default="sites/only-ya/",
        help="Path to open in browser (relative to parser-kart root)",
    )
    args = parser.parse_args()

    with socketserver.TCPServer(("", args.port), PreviewHandler) as httpd:
        url = f"http://127.0.0.1:{args.port}/{args.open.lstrip('/')}"
        print(f"Serving {ROOT}")
        print(f"Open: {url}")
        print("Examples:")
        print(f"  http://127.0.0.1:{args.port}/sites/only-ya/")
        print(f"  http://127.0.0.1:{args.port}/orgs/001_Только_Я/profile.json")
        print("Press Ctrl+C to stop")
        try:
            webbrowser.open(url)
        except Exception:
            pass
        httpd.serve_forever()


if __name__ == "__main__":
    main()
