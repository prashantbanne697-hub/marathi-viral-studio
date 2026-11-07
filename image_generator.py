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
    reference = d.get("reference_image")
    mime_type = str(d.get("reference_mime_type", "image/jpeg"))
    if not project_exists(pid):
        return jsonify(error="Project not found. आधी project तयार करा."), 404
    if not prompt:
        return jsonify(error="Scene prompt आवश्यक आहे."), 400
    if not scene.isdigit() or not 1 <= int(scene) <= 20:
        return jsonify(error="Scene number 1 ते 20 असावा."), 400
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return jsonify(error="Render Environment मध्ये GEMINI_API_KEY उपलब्ध नाही."), 500

    image_prompt = prompt + (
        "\\nCreate one polished vertical 9:16 image for a Marathi YouTube Short. "
        "If a reference person image is supplied, use that same person's identity and facial features; "
        "do not substitute a different person. Preserve recognizable face and hairstyle. "
        "Professional cinematic office studio, clean details, no collage, no added text or watermark."
    )
    try:
        inputs = [{"type": "text", "text": image_prompt}]
        if reference:
            if mime_type not in ("image/jpeg", "image/png", "image/webp"):
                return jsonify(error="Reference photo JPG, PNG किंवा WEBP असावी."), 400
            try:
                raw = base64.b64decode(reference, validate=True)
            except Exception:
                return jsonify(error="Reference photo data वाचता आली नाही."), 400
            if len(raw) > 8 * 1024 * 1024:
                return jsonify(error="Reference photo 8 MB पेक्षा लहान ठेवा."), 413
            inputs.append({"type": "image", "mime_type": mime_type, "data": base64.b64encode(raw).decode("ascii")})

        payload = json.dumps({
            "model": "gemini-3.1-flash-image",
            "input": inputs,
            "response_format": {"type": "image", "aspect_ratio": "9:16"}
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://generativelanguage.googleapis.com/v1beta/interactions",
            data=payload,
            headers={"Content-Type": "application/json", "x-goog-api-key": key},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=240) as response:
            result = json.loads(response.read().decode("utf-8"))

        image_data = result.get("output_image", {}).get("data")
        if not image_data:
            for step in result.get("steps", []):
                if step.get("type") == "model_output":
                    for block in step.get("content", []):
                        if block.get("type") == "image" and block.get("data"):
                            image_data = block["data"]
                            break
                if image_data:
                    break
        if not image_data:
            raise RuntimeError("Gemini ने image परत केली नाही. API response मध्ये image output नाही.")

        image_bytes = base64.b64decode(image_data)
        folder = ROOT / "generated_images" / pid
        folder.mkdir(parents=True, exist_ok=True)
        name = f"scene_{int(scene):02d}.png"
        (folder / name).write_bytes(image_bytes)
        return jsonify(ok=True, scene=int(scene), url=f"/generated/{pid}/{name}", provider="Gemini 3.1 Flash Image")

    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:700]
        return jsonify(error=f"Gemini API error ({e.code}): {detail}"), 502
    except Exception as e:
        return jsonify(error=f"Image generation failed: {str(e)[:700]}"), 502


@image_bp.get("/api/image/list/<pid>")
def list_scene_images(pid):
    if not project_exists(pid):
        return jsonify(error="Project not found."), 404
    folder = ROOT / "generated_images" / pid
    files = sorted(list(folder.glob("scene_*.jpg")) + list(folder.glob("scene_*.png"))) if folder.exists() else []
    return jsonify(images=[{"name": f.name, "url": f"/generated/{pid}/{f.name}"} for f in files])


@image_bp.get("/generated/<pid>/<path:name>")
def serve_generated_image(pid, name):
    return send_from_directory(ROOT / "generated_images" / pid, name)
