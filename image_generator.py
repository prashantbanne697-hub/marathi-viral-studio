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
    payload = {
        "model": "gemini-nano-banana-2.1",
        "input": prompt + "\\nCreate one polished vertical 9:16 image for a Marathi YouTube Short. No collage.",
        "response_format": {"type":"image","mime_type":"image/png","aspect_ratio":"9:16","image_size":"1K"}
    }
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type":"application/json","x-goog-api-key":key}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=240) as r:
            result = json.loads(r.read().decode("utf-8"))
        data = (result.get("output_image") or {}).get("data")
        if not data:
            raise RuntimeError(result.get("error",{}).get("message","Gemini ने image परत दिली नाही."))
        folder = ROOT/"generated_images"/pid
        folder.mkdir(parents=True, exist_ok=True)
        name = f"scene_{int(scene):02d}.png"
        (folder/name).write_bytes(base64.b64decode(data))
        return jsonify(ok=True, scene=int(scene), url=f"/generated/{pid}/{name}")
    except Exception as e:
        return jsonify(error=str(e)[:1200]), 502

@image_bp.get("/api/image/list/<pid>")
def list_scene_images(pid):
    if not project_exists(pid):
        return jsonify(error="Project not found."), 404
    folder = ROOT/"generated_images"/pid
    files = sorted(folder.glob("scene_*.png")) if folder.exists() else []
    return jsonify(images=[{"name":f.name,"url":f"/generated/{pid}/{f.name}"} for f in files])

@image_bp.get("/generated/<pid>/<path:name>")
def serve_generated_image(pid, name):
    return send_from_directory(ROOT/"generated_images"/pid, name)\n