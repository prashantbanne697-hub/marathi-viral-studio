import os, json, uuid, subprocess, sys, threading, time
from datetime import datetime
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory

ROOT=Path(__file__).resolve().parent
DATA=ROOT/"data"/"projects.json"
LOCK=threading.Lock()
app=Flask(__name__)
app.secret_key=os.getenv("FLASK_SECRET_KEY") or os.getenv("SECRET_KEY") or "CHANGE-ME-BEFORE-INSTAGRAM-OAUTH"
from instagram_api import instagram_bp
app.register_blueprint(instagram_bp)
from image_generator import image_bp
app.register_blueprint(image_bp)
def load():
    if not DATA.exists(): return []
    try: return json.loads(DATA.read_text(encoding="utf-8"))
    except Exception: return []

def save(items):
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps(items,ensure_ascii=False,indent=2),encoding="utf-8")

def update(pid, **fields):
    with LOCK:
        items=load()
        for p in items:
            if p["id"]==pid:
                p.update(fields); p["updated_at"]=datetime.now().isoformat(timespec="seconds")
                save(items); return p
    return None

def get_project(pid):
    return next((p for p in load() if p["id"]==pid),None)

def gemini(prompt):
    import urllib.request
    key=os.getenv("GEMINI_API_KEY")
    if not key: raise RuntimeError("GEMINI_API_KEY environment variable missing.")

    # Automatically try another currently supported Flash model during temporary overload.
    models=("gemini-3.8-flash","gemini-3.5-flash-lite","gemini-3.6-flash")
    transient_codes=(429,500,502,503,504)
    errors=[]

    for model in models:
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key="+key
        body={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.7,"maxOutputTokens":2200}}
        req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"},method="POST")

        for attempt, delay in enumerate((0,4), start=1):
            if delay: time.sleep(delay)
            try:
                with urllib.request.urlopen(req,timeout=180) as response:
                    result=json.loads(response.read().decode())
                candidates=result.get("candidates") or []
                if not candidates:
                    raise RuntimeError(f"{model} returned no candidates: {json.dumps(result)[:1000]}")
                parts=candidates[0].get("content",{}).get("parts",[])
                output="".join(x.get("text","") for x in parts).strip()
                if not output:
                    raise RuntimeError(f"{model} returned an empty response.")
                return output
            except urllib.error.HTTPError as e:
                error_body=e.read().decode("utf-8","replace")
                message=f"{model} HTTP {e.code}: {error_body[:900]}"
                errors.append(message)
                if e.code not in transient_codes:
                    raise RuntimeError(message) from e
                break
            except (urllib.error.URLError, TimeoutError) as e:
                errors.append(f"{model}: {e}")
                if attempt == 2:
                    break
            except Exception as e:
                errors.append(f"{model}: {type(e).__name__}: {e}")
                break

    raise RuntimeError("All Gemini fallback models are temporarily unavailable. " + " | ".join(errors[-3:]))

@app.get("/")
def home(): return render_template("index.html")

@app.get("/api/projects")
def projects(): return jsonify(load())

@app.post("/api/projects")
def create():
    data=request.json or {}
    topic=(data.get("topic") or "").strip()
    if not topic: return jsonify(error="Topic required"),400
    p={"id":"MVS-"+uuid.uuid4().hex[:8].upper(),"topic":topic,
       "format":data.get("format","YouTube Short"),"audience":data.get("audience","Marathi audience"),
       "status":"IDEA — REVIEW REQUIRED","script":"","scenes":"","caption":"",
       "approved":False,"created_at":datetime.now().isoformat(timespec="seconds")}
    items=load(); items.insert(0,p); save(items)
    return jsonify(p)

@app.post("/api/agent/<agent>")
def agent(agent):
    data=request.json or {}; p=get_project(data.get("id",""))
    if not p: return jsonify(error="Project not found"),404
    topic=p["topic"]
    if agent=="script":
        prompt=f'Write a punchy spoken Marathi {p["format"]} script on "{topic}" for {p["audience"]}. Strong 2-second hook, useful explanation, natural Marathi, CTA. Return script only.'
        field="script"
    elif agent=="scenes":
        if not p["script"]: return jsonify(error="Run Script Agent first."),400
        prompt=f'Convert this Marathi script into 5 scene-wise video prompts. Each: visuals, camera motion, Marathi on-screen text, sound/effects. Script:\n{p["script"]}'
        field="scenes"
    elif agent=="caption":
        prompt=f'Create Marathi YouTube Shorts title, description, 8 hashtags and thumbnail text for "{topic}". Script:\n{p["script"]}'
        field="caption"
    else: return jsonify(error="Unknown agent"),400
    try:
        output=gemini(prompt)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(error=str(e)),500
    try:
        saved=update(p["id"],**{field:output,"status":agent.upper()+" READY","approved":False})
        if not saved:
            return jsonify(error="Project could not be saved. Please refresh the project list and retry."),500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify(error=f"Agent generated output but saving failed: {type(e).__name__}: {e}"),500
    return jsonify(output=output)

@app.post("/api/approve")
def approve():
    d=request.json or {}; p=get_project(d.get("id",""))
    if not p: return jsonify(error="Project not found"),404
    if not p["script"]: return jsonify(error="Generate a script before approval."),400
    update(p["id"],approved=bool(d.get("approved")),status="APPROVED" if d.get("approved") else "CHANGES REQUESTED")
    return jsonify(ok=True)

@app.post("/api/render")
def render_video():
    d=request.json or {}; p=get_project(d.get("id",""))
    if not p: return jsonify(error="Project not found"),404
    if not p["approved"]: return jsonify(error="Approve the production before rendering."),400
    if not (ROOT/"render.py").exists(): return jsonify(error="render.py missing from package."),500
    clips=sorted((ROOT/"assets").glob("[0-9][0-9].mp4"))
    if not clips: return jsonify(error="Add scene clips to assets/ as 01.mp4, 02.mp4..."),400
    try:
        subprocess.run([sys.executable,str(ROOT/"render.py"),"--output",str(ROOT/"output"/"final_short.mp4")],
                       cwd=ROOT,check=True,capture_output=True,text=True)
        update(p["id"],status="VIDEO READY",video="output/final_short.mp4")
        return jsonify(ok=True,video="/video/final_short.mp4")
    except subprocess.CalledProcessError as e:
        return jsonify(error=(e.stderr or e.stdout)[-1800:]),500


@app.post("/api/voice-test")
def voice_test():
    d=request.json or {}
    text=(d.get("text") or "").strip()
    try:
        speaker=int(d.get("speaker",0))
    except (TypeError,ValueError):
        return jsonify(error="Invalid speaker ID."),400
    if not text:
        return jsonify(error="Please enter a Marathi sample sentence."),400
    if len(text)>350:
        return jsonify(error="Keep the sample under 350 characters."),400
    if speaker<0 or speaker>8:
        return jsonify(error="Choose speaker ID 0 to 8."),400
    voice_dir=ROOT/"data"/"piper-voices"
    output_dir=ROOT/"output"
    voice_dir.mkdir(parents=True,exist_ok=True)
    output_dir.mkdir(parents=True,exist_ok=True)
    filename=f"voice_test_{speaker}.wav"
    model_path=voice_dir/"mr_IN-google-medium.onnx"
    try:
        if not model_path.exists() or not Path(str(model_path)+".json").exists():
            download=subprocess.run(
                [sys.executable,"-m","piper.download_voices","--data-dir",str(voice_dir),"mr_IN-google-medium"],
                cwd=ROOT,capture_output=True,text=True,timeout=240
            )
            if download.returncode:
                return jsonify(error=("Piper model download failed: "+(download.stderr or download.stdout)[-1200:])),500
        result=subprocess.run(
            [sys.executable,"-m","piper","--model",str(model_path),
             "--speaker",str(speaker),"--output_file",str(output_dir/filename),
             "--data-dir",str(voice_dir),"--",text],
            cwd=ROOT,capture_output=True,text=True,timeout=180
        )
        if result.returncode:
            return jsonify(error=("Piper voice generation failed: "+(result.stderr or result.stdout)[-1200:])),500
        if not (output_dir/filename).exists():
            return jsonify(error="Piper did not create the audio file."),500
        return jsonify(ok=True,audio="/video/"+filename,speaker=speaker)
    except subprocess.TimeoutExpired:
        return jsonify(error="Voice generation timed out. Try a shorter sentence."),504
    except Exception as e:
        return jsonify(error=f"{type(e).__name__}: {e}"),500

@app.get("/video/<path:name>")
def video(name): return send_from_directory(ROOT/"output",name)

@app.post("/api/upload")
def upload():
    d=request.json or {}; p=get_project(d.get("id",""))
    if not p: return jsonify(error="Project not found"),404
    if not p.get("approved"): return jsonify(error="Approve before upload."),400
    video_path=ROOT/"output"/"final_short.mp4"
    if not video_path.exists(): return jsonify(error="Render final_short.mp4 first."),400
    cmd=[sys.executable,str(ROOT/"youtube_upload.py"),"--video",str(video_path),
         "--title",d.get("title") or p["topic"],"--description",d.get("description") or p.get("caption",""),
         "--privacy",d.get("privacy","private"),"--tags",d.get("tags","Marathi,Shorts,AI")]
    try:
        r=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True,timeout=900)
        if r.returncode: return jsonify(error=(r.stderr or r.stdout)[-1800:]),500
        update(p["id"],status="UPLOADED — VERIFY IN YOUTUBE STUDIO")
        return jsonify(ok=True,log=r.stdout[-1800:])
    except Exception as e: return jsonify(error=str(e)),500

@app.post("/api/topics")
def topics():
    d=request.json or {}
    if not (ROOT/"topic_agent.py").exists(): return jsonify(error="topic_agent.py missing."),500
    env=os.environ.copy()
    try:
        r=subprocess.run([sys.executable,str(ROOT/"topic_agent.py"),"--niche",d.get("niche","Marathi AI tutorials"),"--count",str(int(d.get("count",8)))],
                         cwd=ROOT,env=env,capture_output=True,text=True,timeout=180)
        if r.returncode: return jsonify(error=(r.stderr or r.stdout)[-1800:]),500
        q=ROOT/"topic_queue.json"
        return jsonify(log=r.stdout,ideas=json.loads(q.read_text(encoding="utf-8")) if q.exists() else [])
    except Exception as e: return jsonify(error=str(e)),500

@app.post("/api/analytics")
def analytics():
    d=request.json or {}
    if not (ROOT/"youtube_analytics.py").exists(): return jsonify(error="youtube_analytics.py missing."),500
    try:
        r=subprocess.run([sys.executable,str(ROOT/"youtube_analytics.py"),"--channel-id",d.get("channel_id","")],
                         cwd=ROOT,capture_output=True,text=True,timeout=180)
        if r.returncode: return jsonify(error=(r.stderr or r.stdout)[-1800:]),500
        report=ROOT/"channel_report.json"
        return jsonify(report=json.loads(report.read_text(encoding="utf-8")))
    except Exception as e: return jsonify(error=str(e)),500

if __name__=="__main__":
    print("MARATHI VIRAL STUDIO Master Control Room: http://127.0.0.1:5000")
    app.run(host="127.0.0.1",port=5000,debug=False)
