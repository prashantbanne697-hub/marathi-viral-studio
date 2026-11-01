#!/usr/bin/env python3
"""
MARATHI VIRAL STUDIO — Phase 2 local/cloud-worker renderer
Requires FFmpeg installed and available as `ffmpeg` and `ffprobe`.
Put scene clips in assets/ as 01.mp4, 02.mp4, 03.mp4...
Optional narration.mp3 and music.mp3 in assets/.
Creates output/final_short.mp4 (vertical 1080x1920, H.264/AAC).
"""
import argparse, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
OUT = ROOT / "output" / "final_short.mp4"

def run(cmd):
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--clips", nargs="*", help="Clip paths; default assets/01.mp4, 02.mp4 ...")
    p.add_argument("--voice", default=str(ASSETS/"narration.mp3"))
    p.add_argument("--music", default=str(ASSETS/"music.mp3"))
    p.add_argument("--output", default=str(OUT))
    args = p.parse_args()

    clips = [Path(x) for x in args.clips] if args.clips else sorted(ASSETS.glob("[0-9][0-9].mp4"))
    clips = [x for x in clips if x.exists()]
    if not clips:
        sys.exit("No scene clips found. Add assets/01.mp4, 02.mp4, etc.")
    out = Path(args.output); out.parent.mkdir(parents=True, exist_ok=True)
    work = ROOT/"output"/"normalized"; work.mkdir(parents=True, exist_ok=True)
    normalized=[]
    for i, clip in enumerate(clips,1):
        target=work/f"scene_{i:02d}.mp4"
        # Center-crop to 9:16; scale to 1080x1920; normalize frame rate/audio.
        vf="scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1"
        run(["ffmpeg","-y","-i",str(clip),"-vf",vf,"-c:v","libx264","-preset","veryfast",
             "-crf","23","-pix_fmt","yuv420p","-an",str(target)])
        normalized.append(target)
    listfile=ROOT/"output"/"concat.txt"
    listfile.write_text("".join(f"file '{x.as_posix()}'\n" for x in normalized),encoding="utf-8")
    silent=ROOT/"output"/"silent.mp4"
    run(["ffmpeg","-y","-f","concat","-safe","0","-i",str(listfile),"-c","copy",str(silent)])

    voice=Path(args.voice); music=Path(args.music)
    if voice.exists() and music.exists():
        run(["ffmpeg","-y","-i",str(silent),"-i",str(voice),"-stream_loop","-1","-i",str(music),
             "-filter_complex","[1:a]volume=1.0[v];[2:a]volume=0.12[m];[v][m]amix=inputs=2:duration=first:dropout_transition=2[a]",
             "-map","0:v","-map","[a]","-c:v","copy","-c:a","aac","-b:a","192k","-shortest","-movflags","+faststart",str(out)])
    elif voice.exists():
        run(["ffmpeg","-y","-i",str(silent),"-i",str(voice),"-map","0:v","-map","1:a",
             "-c:v","copy","-c:a","aac","-shortest","-movflags","+faststart",str(out)])
    elif music.exists():
        run(["ffmpeg","-y","-i",str(silent),"-stream_loop","-1","-i",str(music),
             "-map","0:v","-map","1:a","-filter:a","volume=0.12","-c:v","copy","-c:a","aac",
             "-shortest","-movflags","+faststart",str(out)])
    else:
        run(["ffmpeg","-y","-i",str(silent),"-c","copy","-movflags","+faststart",str(out)])
    print(f"\nDONE: {out}\nReview the video before publishing.")

if __name__=="__main__":
    main()
