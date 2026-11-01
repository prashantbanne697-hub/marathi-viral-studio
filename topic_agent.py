#!/usr/bin/env python3
"""
Topic research agent for Marathi Viral Studio.
Uses Gemini API to suggest topics; optionally enriches ideas with YouTube search
when a YouTube API key is supplied. No scraping or guaranteed virality.
"""
import argparse, json, os, urllib.parse, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"topic_queue.json"

def gemini_ideas(api_key, niche, audience, count):
    prompt=f"""You are a Marathi YouTube Shorts content strategist.
Generate {count} fresh, practical video topic ideas for niche: {niche}.
Audience: {audience}. Return valid JSON array only. Each object:
{{"topic":"Marathi title","hook":"first 2-second hook in Marathi",
"angle":"unique explanation/demo","format":"Short/Reel",
"keywords":["keyword1","keyword2"],"why":"brief reason"}}
Use natural Marathi. Avoid false claims, medical/financial guarantees, and copied titles."""
    url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key="+urllib.parse.quote(api_key)
    body={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"temperature":0.8,"maxOutputTokens":3000}}
    req=urllib.request.Request(url,data=json.dumps(body).encode(),headers={"Content-Type":"application/json"},method="POST")
    with urllib.request.urlopen(req,timeout=60) as r: data=json.loads(r.read().decode())
    raw="".join(p.get("text","") for p in data["candidates"][0]["content"]["parts"]).strip()
    raw=raw.removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw)

def youtube_search(api_key, query, max_results=5):
    params=urllib.parse.urlencode({"part":"snippet","q":query,"type":"video","order":"viewCount","publishedAfter":"2026-10-01T00:00:00Z","maxResults":max_results,"key":api_key})
    url="https://www.googleapis.com/youtube/v3/search?"+params
    with urllib.request.urlopen(url,timeout=30) as r: data=json.loads(r.read().decode())
    return [{"title":x["snippet"]["title"],"channel":x["snippet"]["channelTitle"],
             "publishedAt":x["snippet"]["publishedAt"],"videoId":x["id"]["videoId"],
             "url":"https://www.youtube.com/watch?v="+x["id"]["videoId"]} for x in data.get("items",[])]

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--niche",default="AI tools, Google Flow, Marathi tutorials")
    p.add_argument("--audience",default="Marathi beginners in India")
    p.add_argument("--count",type=int,default=10)
    args=p.parse_args()
    key=os.getenv("GEMINI_API_KEY")
    if not key: raise SystemExit("Set GEMINI_API_KEY environment variable first.")
    ideas=gemini_ideas(key,args.niche,args.audience,args.count)
    ytkey=os.getenv("YOUTUBE_API_KEY")
    for idea in ideas:
        idea["youtube_research"]=youtube_search(ytkey,idea.get("topic",args.niche),5) if ytkey else []
        idea["created_at"]=datetime.now(timezone.utc).isoformat()
        idea["status"]="IDEA — REVIEW REQUIRED"
    OUT.write_text(json.dumps(ideas,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Saved {len(ideas)} ideas to {OUT}")
    for i,x in enumerate(ideas,1): print(f'{i}. {x.get("topic")} — {x.get("hook","")}')

if __name__=="__main__": main()
