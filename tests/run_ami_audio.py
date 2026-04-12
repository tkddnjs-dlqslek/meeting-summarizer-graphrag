"""ES2002a Mix-Headset WAV → /stt → 오디오 파이프라인."""

import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx

API = "http://localhost:8000"
AUDIO_FILE = Path(__file__).parent.parent / "audio_cache" / "ES2002a.Mix-Headset.wav"
PROJECT_ID = "ami_es2002_audio"


async def main():
    print(f"[1] 파일: {AUDIO_FILE} ({AUDIO_FILE.stat().st_size/1024/1024:.1f} MB)")

    async with httpx.AsyncClient(timeout=60) as client:
        with open(AUDIO_FILE, "rb") as f:
            files = {"file": (AUDIO_FILE.name, f, "audio/wav")}
            data = {
                "project_id": PROJECT_ID,
                "language": "en",
            }
            print("[2] /stt POST 중...")
            r = await client.post(f"{API}/stt", files=files, data=data)
            r.raise_for_status()
            resp = r.json()
        job_id = resp["job_id"]
        meeting_id = resp["meeting_id"]
        print(f"  job_id={job_id}")
        print(f"  meeting_id={meeting_id}")

    print("[3] 폴링 시작 (STT + 추출 + 그래프 + 노트)")
    start = time.time()
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            r = await client.get(f"{API}/stt/status/{job_id}")
            info = r.json()
            status = info.get("status", "?")
            elapsed = int(time.time() - start)
            print(f"  [{elapsed:4d}s] status={status}", flush=True)

            if status == "done":
                print("\n[4] 완료")
                pr = info.get("pipeline_result", {})
                print(f"  meeting_id : {pr.get('meeting_id')}")
                print(f"  project_id : {pr.get('project_id')}")
                print(f"  node_count : {pr.get('node_count')}")
                print(f"  note_path  : {pr.get('note_path')}")
                print(f"\n  transcript 앞 400자:")
                print("  " + "-" * 60)
                t = info.get("transcript", "")[:400]
                for line in t.split("\n"):
                    print("  " + line)
                print("  " + "-" * 60)

                # STT 결과를 파일로 저장 (WER 측정용)
                out = Path(__file__).parent / "ami_ES2002a_whisper.txt"
                out.write_text(info.get("transcript", ""), encoding="utf-8")
                print(f"\n  Whisper transcript 저장: {out}")
                break
            if status == "error":
                print(f"  ERROR: {info.get('error')}")
                break
            await asyncio.sleep(20)


if __name__ == "__main__":
    asyncio.run(main())
