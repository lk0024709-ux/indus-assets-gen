#!/usr/bin/env python3
"""Serve the character web preview and expose the repository Motion folder by URL."""
from __future__ import annotations

import argparse
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "procedural_asset_app" / "frontend"
MOTION_DIR = ROOT / "Base model " / "Motion"


class PreviewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND), **kwargs)

    def translate_path(self, path: str) -> str:
        request_path = unquote(urlsplit(path).path)
        prefix = "/assets/motions/"
        if request_path.startswith(prefix):
            relative = Path(request_path[len(prefix):])
            target = (MOTION_DIR / relative).resolve()
            if target.is_relative_to(MOTION_DIR.resolve()) and target.is_file():
                return str(target)
            return str(MOTION_DIR / "__not_found__")
        return super().translate_path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), PreviewHandler)
    print(f"Character preview serving on http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
