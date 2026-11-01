#!/usr/bin/env python3
"""
YouTube upload agent. First run opens Google's OAuth consent in browser.
Requires: pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
Create OAuth Desktop client credentials in Google Cloud and save as client_secret.json here.
Enable YouTube Data API v3. Upload is private by default.
"""
import argparse, os
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle

SCOPES=["https://www.googleapis.com/auth/youtube.upload"]
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--video",default=str(ROOT/"output"/"final_short.mp4"))
    p.add_argument("--title",required=True)
    p.add_argument("--description",default="Created with Marathi Viral Studio.")
    p.add_argument("--privacy",choices=["private","unlisted","public"],default="private")
    p.add_argument("--tags",default="Marathi,Shorts,AI")
    args=p.parse_args()
    video=Path(args.video)
    if not video.exists(): raise SystemExit(f"Video not found: {video}")
    token=ROOT/"token.pickle"
    creds=None
    if token.exists():
        with token.open("rb") as f: creds=pickle.load(f)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            secret=ROOT/"client_secret.json"
            if not secret.exists(): raise SystemExit("Missing client_secret.json OAuth Desktop credentials.")
            flow=InstalledAppFlow.from_client_secrets_file(str(secret),SCOPES)
            creds=flow.run_local_server(port=0)
        with token.open("wb") as f: pickle.dump(creds,f)
    youtube=build("youtube","v3",credentials=creds)
    body={"snippet":{"title":args.title[:100],"description":args.description,
                     "tags":[t.strip() for t in args.tags.split(",") if t.strip()][:500],
                     "categoryId":"22"},
          "status":{"privacyStatus":args.privacy,"selfDeclaredMadeForKids":False}}
    media=MediaFileUpload(str(video),chunksize=-1,resumable=True,mimetype="video/*")
    request=youtube.videos().insert(part="snippet,status",body=body,media_body=media)
    response=None
    while response is None:
        status,response=request.next_chunk()
        if status: print(f"Upload progress: {int(status.progress()*100)}%")
    print("Uploaded video ID:",response.get("id"))
    print("Privacy:",args.privacy)
    print("Review in YouTube Studio before making public.")

if __name__=="__main__": main()
