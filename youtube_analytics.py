#!/usr/bin/env python3
"""
Basic public YouTube channel/video performance report using YouTube Data API v3.
This reads public statistics only. Private channel analytics (watch time, retention,
impressions, revenue) need YouTube Analytics API OAuth and are not included.
"""
import argparse, csv, json, os, urllib.parse, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def api(url):
    with urllib.request.urlopen(url,timeout=30) as r: return json.loads(r.read().decode())

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--channel-id",required=True)
    args=p.parse_args()
    key=os.getenv("YOUTUBE_API_KEY")
    if not key: raise SystemExit("Set YOUTUBE_API_KEY environment variable.")
    q=urllib.parse.urlencode({"part":"contentDetails,snippet,statistics","id":args.channel_id,"key":key})
    ch=api("https://www.googleapis.com/youtube/v3/channels?"+q)
    items=ch.get("items",[])
    if not items: raise SystemExit("Channel not found or API key lacks access.")
    c=items[0]; uploads=c["contentDetails"]["relatedPlaylists"]["uploads"]
    videos=[]; page=None
    for _ in range(4):
        params={"part":"snippet,contentDetails","playlistId":uploads,"maxResults":50,"key":key}
        if page: params["pageToken"]=page
        data=api("https://www.googleapis.com/youtube/v3/playlistItems?"+urllib.parse.urlencode(params))
        videos += data.get("items",[])
        page=data.get("nextPageToken")
        if not page: break
    ids=[v["contentDetails"]["videoId"] for v in videos]
    stats=[]
    for start in range(0,len(ids),50):
        params=urllib.parse.urlencode({"part":"snippet,statistics,contentDetails","id":",".join(ids[start:start+50]),"key":key})
        stats += api("https://www.googleapis.com/youtube/v3/videos?"+params).get("items",[])
    rows=[]
    for v in stats:
        s=v.get("statistics",{})
        views=int(s.get("viewCount",0)); likes=int(s.get("likeCount",0)); comments=int(s.get("commentCount",0))
        rows.append({"title":v["snippet"]["title"],"published_at":v["snippet"]["publishedAt"],
                     "views":views,"likes":likes,"comments":comments,
                     "like_rate_pct":round(likes/views*100,2) if views else 0,
                     "comment_rate_pct":round(comments/views*100,2) if views else 0,
                     "video_url":"https://www.youtube.com/watch?v="+v["id"]})
    rows.sort(key=lambda x:x["views"],reverse=True)
    out=ROOT/"channel_report.csv"
    if rows:
        with out.open("w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary={"channel":c["snippet"]["title"],"subscriber_count":c.get("statistics",{}).get("subscriberCount","hidden"),
             "channel_views":c.get("statistics",{}).get("viewCount","0"),"video_count":len(rows),
             "top_5":rows[:5],"csv":str(out)}
    (ROOT/"channel_report.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    print("\nNote: public stats are not private retention/watch-time/revenue analytics.")

if __name__=="__main__": main()
