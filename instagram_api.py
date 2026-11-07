"""Instagram Login + Reels publishing for Marathi Viral Studio.

Required Render environment variables:
  INSTAGRAM_APP_ID, INSTAGRAM_APP_SECRET, FLASK_SECRET_KEY
Optional:
  INSTAGRAM_REDIRECT_URI (defaults to https://<host>/instagram/callback)
  META_GRAPH_VERSION (defaults to v26.0)

Tokens are kept in data/instagram_auth.json on the service filesystem. Render Free
instances have ephemeral storage; reconnect after a redeploy/restart unless durable
storage is configured. Never commit app secrets or access tokens to Git.
"""
import json
import os
import secrets
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for

instagram_bp = Blueprint("instagram", __name__)
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
AUTH_FILE = DATA_DIR / "instagram_auth.json"
PROJECTS_FILE = DATA_DIR / "projects.json"
GRAPH_VERSION = os.getenv("META_GRAPH_VERSION", "v26.0")
GRAPH_ROOT = f"https://graph.instagram.com/{GRAPH_VERSION}"


def _json_request(url, method="GET", form=None, timeout=45):
    data = urllib.parse.urlencode(form).encode("utf-8") if form is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Accept": "application/json", "User-Agent": "MarathiViralStudio/1.0",
                 **({"Content-Type": "application/x-www-form-urlencoded"} if data else {})},
        method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "replace")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(detail)
            detail = parsed.get("error", {}).get("message", detail)
        except Exception:
            pass
        raise RuntimeError(f"Instagram API HTTP {exc.code}: {str(detail)[:900]}") from exc


def _load_auth():
    if not AUTH_FILE.exists():
        return {}
    try:
        return json.loads(AUTH_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_auth(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    temp = AUTH_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(AUTH_FILE)
    try:
        os.chmod(AUTH_FILE, 0o600)
    except OSError:
        pass


def _config():
    app_id = os.getenv("INSTAGRAM_APP_ID", "").strip()
    app_secret = os.getenv("INSTAGRAM_APP_SECRET", "").strip()
    redirect_uri = os.getenv("INSTAGRAM_REDIRECT_URI", "").strip()
    if not redirect_uri:
        redirect_uri = url_for("instagram.callback", _external=True)
    return app_id, app_secret, redirect_uri


def _auth_or_env():
    saved = _load_auth()
    token = saved.get("access_token") or os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    user_id = str(saved.get("user_id") or os.getenv("INSTAGRAM_USER_ID", "")).strip()
    if token and user_id:
        return {**saved, "access_token": token, "user_id": user_id}
    return {}


def _save_project(pid, changes):
    try:
        items = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return False
    found = False
    for item in items:
        if item.get("id") == pid:
            item.update(changes)
            item["updated_at"] = datetime.now().isoformat(timespec="seconds")
            found = True
            break
    if not found:
        return False
    temp = PROJECTS_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(PROJECTS_FILE)
    return True


@instagram_bp.get("/api/instagram/status")
def status():
    app_id, app_secret, _ = _config()
    auth = _auth_or_env()
    return jsonify({
        "configured": bool(app_id and app_secret),
        "connected": bool(auth),
        "username": auth.get("username", ""),
        "user_id": auth.get("user_id", ""),
        "token_source": "connected account" if auth else None,
        "graph_version": GRAPH_VERSION,
        "message": (
            "Instagram connected." if auth else
            "Meta App ID and App Secret are required in Render Environment before connecting."
            if not (app_id and app_secret) else
            "Ready to connect. Use a Professional Instagram account (Creator or Business)."
        )
    })


@instagram_bp.get("/instagram/connect")
def connect():
    app_id, app_secret, redirect_uri = _config()
    if not app_id or not app_secret:
        return "Instagram is not configured. Add INSTAGRAM_APP_ID and INSTAGRAM_APP_SECRET in Render Environment.", 503
    state = secrets.token_urlsafe(24)
    session["ig_oauth_state"] = state
    params = {
        "client_id": app_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "instagram_business_basic,instagram_business_content_publish",
        "state": state,
        "enable_fb_login": "0",
        "force_authentication": "1"
    }
    return redirect("https://www.instagram.com/oauth/authorize?" + urllib.parse.urlencode(params))


@instagram_bp.get("/instagram/callback")
def callback():
    if request.args.get("error"):
        return f"Instagram authorization cancelled or denied: {request.args.get('error_description', request.args.get('error'))}", 400
    state = request.args.get("state", "")
    expected = session.pop("ig_oauth_state", "")
    if not state or not expected or not secrets.compare_digest(state, expected):
        return "OAuth state check failed. Return to the dashboard and connect again.", 400
    code = request.args.get("code", "")
    if not code:
        return "Instagram did not return an authorization code.", 400

    app_id, app_secret, redirect_uri = _config()
    if not app_id or not app_secret:
        return "Instagram App ID/Secret missing in Render Environment.", 503
    token_data = _json_request(
        "https://api.instagram.com/oauth/access_token", method="POST",
        form={"client_id": app_id, "client_secret": app_secret,
              "grant_type": "authorization_code", "redirect_uri": redirect_uri,
              "code": code}
    )
    short_token = token_data.get("access_token")
    user_id = str(token_data.get("user_id", "")).strip()
    if not short_token or not user_id:
        return "Instagram token exchange did not return the expected account ID.", 502

    long_data = _json_request(
        "https://graph.instagram.com/access_token?" + urllib.parse.urlencode({
            "grant_type": "ig_exchange_token", "client_secret": app_secret,
            "access_token": short_token
        })
    )
    access_token = long_data.get("access_token", short_token)
    profile = _json_request(GRAPH_ROOT + "/me?" + urllib.parse.urlencode({
        "fields": "user_id,username", "access_token": access_token
    }))
    _save_auth({
        "access_token": access_token,
        "user_id": str(profile.get("user_id") or profile.get("id") or user_id),
        "username": profile.get("username", ""),
        "expires_in": long_data.get("expires_in"),
        "connected_at": datetime.now(timezone.utc).isoformat()
    })
    return redirect(url_for("home", instagram="connected"))


@instagram_bp.post("/api/instagram/disconnect")
def disconnect():
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()
    return jsonify(ok=True, connected=False)


@instagram_bp.post("/api/instagram/publish")
def publish_reel():
    d = request.get_json(silent=True) or {}
    pid = str(d.get("id", "")).strip()
    try:
        projects = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return jsonify(error="Project database unavailable."), 500
    project = next((p for p in projects if p.get("id") == pid), None)
    if not project:
        return jsonify(error="Project not found."), 404
    if not project.get("approved"):
        return jsonify(error="Approve this production before Instagram publishing."), 400
    video_rel = project.get("video") or "output/final_short.mp4"
    video_path = (ROOT / video_rel).resolve()
    if ROOT.resolve() not in video_path.parents or not video_path.exists():
        return jsonify(error="Final MP4 not found. Render and preview the video first."), 400
    auth = _auth_or_env()
    if not auth:
        return jsonify(error="Connect an Instagram Professional account first."), 401

    # Instagram fetches the video from a public HTTPS URL; it cannot fetch a local path.
    video_url = request.url_root.rstrip("/") + url_for("video", name=video_path.name)
    caption = str(d.get("caption") or project.get("caption") or project.get("topic") or "")
    caption = caption[:2200]
    container = _json_request(GRAPH_ROOT + f"/{auth['user_id']}/media", method="POST", form={
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": auth["access_token"]
    }, timeout=60)
    creation_id = container.get("id")
    if not creation_id:
        return jsonify(error="Instagram did not return a media container ID.", details=container), 502

    final_status = {}
    for _ in range(60):
        final_status = _json_request(GRAPH_ROOT + f"/{creation_id}?" + urllib.parse.urlencode({
            "fields": "status_code,status", "access_token": auth["access_token"]
        }))
        code = final_status.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            return jsonify(error=final_status.get("status") or f"Instagram container status: {code}"), 502
        time.sleep(3)
    else:
        return jsonify(error="Instagram video processing is taking too long. Try again later.",
                       container_id=creation_id, status=final_status), 504

    published = _json_request(GRAPH_ROOT + f"/{auth['user_id']}/media_publish", method="POST", form={
        "creation_id": creation_id, "access_token": auth["access_token"]
    }, timeout=60)
    media_id = published.get("id", "")
    _save_project(pid, {
        "instagram_status": "PUBLISHED",
        "instagram_media_id": media_id,
        "instagram_published_at": datetime.now(timezone.utc).isoformat()
    })
    return jsonify(ok=True, media_id=media_id, username=auth.get("username", ""),
                   status="PUBLISHED — check the Instagram profile.")


@instagram_bp.get("/api/instagram/recent")
def recent_media():
    auth = _auth_or_env()
    if not auth:
        return jsonify(error="Instagram account is not connected."), 401
    data = _json_request(GRAPH_ROOT + f"/{auth['user_id']}/media?" + urllib.parse.urlencode({
        "fields": "id,caption,media_type,permalink,timestamp",
        "limit": "12", "access_token": auth["access_token"]
    }))
    return jsonify(items=data.get("data", []), username=auth.get("username", ""))
