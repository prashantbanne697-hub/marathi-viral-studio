#!/usr/bin/env python3
"""
Simple daily topic scheduler. Run continuously on an always-on PC/VM,
or schedule this script with Windows Task Scheduler / cron.
"""
import argparse, os, subprocess, sys
from datetime import datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--niche",default="AI tools, Google Flow, Marathi tutorials")
    p.add_argument("--count",type=int,default=10)
    args=p.parse_args()
    cmd=[sys.executable,str(ROOT/"topic_agent.py"),"--niche",args.niche,"--count",str(args.count)]
    log=ROOT/"scheduler.log"
    result=subprocess.run(cmd,cwd=ROOT,capture_output=True,text=True)
    with log.open("a",encoding="utf-8") as f:
        f.write(f"\n[{datetime.now().isoformat()}] exit={result.returncode}\n{result.stdout}\n{result.stderr}\n")
    if result.returncode: raise SystemExit(result.returncode)
    print("Daily topic research completed. Review topic_queue.json before production.")

if __name__=="__main__": main()
