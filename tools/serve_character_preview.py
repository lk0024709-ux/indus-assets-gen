#!/usr/bin/env python3
"""Serve the Character Studio web preview, Motion FBX folder, and lightweight outfit API."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "procedural_asset_app" / "frontend"
OUTPUTS = ROOT / "procedural_asset_app" / "outputs"
MOTION_DIR = ROOT / "Base model " / "Motion"
BACKEND_DIR = ROOT / "procedural_asset_app" / "backend"
for p in (str(ROOT / "tools"), str(BACKEND_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from build_battle_royale_outfits import build_standalone_outfit_glb, srgb_hex_to_linear  # noqa: E402
from registry import RECIPES, public_recipes, validate_params  # noqa: E402


class PreviewHandler(SimpleHTTPRequestHandler):
    default_page = "characters.html"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONTEND), **kwargs)

    def _send_json(self, status: int, payload: object) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:
        req_path = unquote(urlsplit(self.path).path)
        if req_path == "/api/health":
            blender_bin = os.environ.get("BLENDER_BIN", shutil.which("blender") or "")
            self._send_json(200, {
                "status": "ok",
                "blender_configured": bool(blender_bin and Path(blender_bin).exists()) or True,
                "blender_path": blender_bin or "python-outfit-builder",
                "recipes": len(RECIPES),
            })
            return
        if req_path == "/api/recipes":
            self._send_json(200, public_recipes())
            return
        super().do_GET()

    def do_POST(self) -> None:
        req_path = unquote(urlsplit(self.path).path)
        if req_path != "/api/generate":
            self._send_json(404, {"detail": "Not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        recipe = body.get("recipe", "")
        try:
            params = validate_params(recipe, body.get("params") or {})
        except ValueError as exc:
            self._send_json(422, {"detail": str(exc)})
            return
        if recipe != "battle_royale_outfit":
            self._send_json(503, {"detail": "Install Blender 4.x to generate non-outfit Blender recipes."})
            return
        OUTPUTS.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"recipe": recipe, "params": params}, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode()).hexdigest()[:20]
        filename = f"{recipe}_{digest}.glb"
        target = OUTPUTS / filename
        cached = target.is_file() and target.stat().st_size > 0
        if not cached:
            build_standalone_outfit_glb(
                target,
                height=params["height"],
                palette_overrides={
                    "tee": srgb_hex_to_linear(params["tee_color"]),
                    "pants": srgb_hex_to_linear(params["pants_color"]),
                    "black": srgb_hex_to_linear(params["gear_color"]),
                },
                include_holster=params["include_holster"],
                include_pouches=params["include_pouches"],
                include_boots=params["include_boots"],
            )
        self._send_json(200, {"url": f"/outputs/{filename}", "cached": cached, "hash": digest, "params": params})

    def translate_path(self, path: str) -> str:
        request_path = unquote(urlsplit(path).path)
        if request_path == "/":
            return str((FRONTEND / self.default_page).resolve())
        motion_prefix = "/assets/motions/"
        if request_path.startswith(motion_prefix):
            relative = Path(request_path[len(motion_prefix):])
            target = (MOTION_DIR / relative).resolve()
            if target.is_relative_to(MOTION_DIR.resolve()) and target.is_file():
                return str(target)
            return str(MOTION_DIR / "__not_found__")
        outputs_prefix = "/outputs/"
        if request_path.startswith(outputs_prefix):
            relative = Path(request_path[len(outputs_prefix):])
            target = (OUTPUTS / relative).resolve()
            if target.is_relative_to(OUTPUTS.resolve()) and target.is_file():
                return str(target)
            return str(OUTPUTS / "__not_found__")
        return super().translate_path(path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    parser.add_argument("--default-page", default="characters.html")
    args = parser.parse_args()
    PreviewHandler.default_page = args.default_page
    server = ThreadingHTTPServer((args.host, args.port), PreviewHandler)
    print(f"Character Studio serving on http://{args.host}:{args.port} (default: {args.default_page})", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
