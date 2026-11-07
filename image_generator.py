import urllib.error
import os, json, base64, urllib.request
from pathlib import Path
from flask import Blueprint, request, jsonify, send_from_directory

image_bp = Blueprint("mvs_image", __name__)
ROOT = Path(__file__).resolve().parent

def project_exists(pid):
    path = ROOT / "data" / "projects.json"
    if not path.exists():
        return False
    try:
        return any(p.get("id") == pid for p in json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return False

@image_bp.post("/api/image/generate")
def generate_scene_image():
    d = request.get_json(silent=True) or {}
    pid, prompt = str(d.get("id", "")).strip(), str(d.get("prompt", "")).strip()
    scene = str(d.get("scene", "1")).strip()
    if not project_exists(pid):
        return jsonify(error="Project not found. आधी project तयार करा."), 404
    if not prompt:
        return jsonify(error="Scene prompt आवश्यक आहे."), 400
    if not scene.isdigit() or not 1 <= int(scene) <= 20:
        return jsonify(error="Scene number 1 ते 20 असावा."), 400
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return jsonify(error="Render Environment मध्ये GEMINI_API_KEY उपलब्ध नाही."), 500

    # Free fallback image provider: Pollinations legacy image endpoint.
    # It does not use or expose the user's Gemini API key.
    from urllib.parse import quote
    import time

    image_prompt = prompt + (
        "\\nCreate one polished vertical 9:16 image for a Marathi YouTube Short. "
        "Professional cinematic composition, clean details, no collage, no text artifacts."
    )
    encoded_prompt = quote(image_prompt, safe="")
    url = (
        "https://image.pollinations.ai/prompt/" + encoded_prompt
        + "?width=768&height=1365&seed=" + str(int(scene) * 137)
        + "&nologo=true"
    )

    try:
        image_bytes = None
        last_error = None
        for attempt in range(3):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "MarathiViralStudio/1.0", "Accept": "image/*"},
                    method="GET"
                )
                with urllib.request.urlopen(req, timeout=180) as response:
                    content_type = response.headers.get("Content-Type", "")
                    image_bytes = response.read()
                if not content_type.startswith("image/") or not image_bytes:
                    raise RuntimeError("Free image provider returned an invalid image response.")
                break
            except Exception as e:
                last_error = e
                if attempt < 2:
                    time.sleep(4 * (attempt + 1))
        if not image_bytes:
            raise RuntimeError(f"Free image generation failed: {last_error}")

        folder = ROOT / "generated_images" / pid
        folder.mkdir(parents=True, exist_ok=True)
        name = f"scene_{int(scene):02d}.jpg"
        (folder / name).write_bytes(image_bytes)
        return jsonify(ok=True, scene=int(scene), url=f"/generated/{pid}/{name}", provider="Pollinations (free fallback)")

    except Exception as e:
        return jsonify(error=f"Free image provider unavailable: {str(e)[:1000]}"), 502



@image_bp.get("/api/image/list/<pid>")
def list_scene_images(pid):
    if not project_exists(pid):
        return jsonify(error="Project not found."), 404
    folder = ROOT / "generated_images" / pid
    files = sorted(folder.glob("scene_*.jpg")) if folder.exists() else []
    return jsonify(images=[{"name": f.name, "url": f"/generated/{pid}/{f.name}"} for f in files])


@image_bp.get("/generated/<pid>/<path:name>")
def serve_generated_image(pid, name):
    return send_from_directory(ROOT / "generated_images" / pid, name)
