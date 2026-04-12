"""
ES2002a~d 4회차 텍스트 경로 투입.
  project_id = "ami_es2002_text"
  previous_meeting_id 체인으로 FOLLOWS 엣지 구축
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx

API = "http://localhost:8000"
PROJECT_ID = "ami_es2002_text"
TESTS_DIR = Path(__file__).parent

MEETINGS = [
    ("ES2002a", "AMI ES2002a — Project Kick-off",      "2005-01-01", "ami_ES2002a.txt", None),
    ("ES2002b", "AMI ES2002b — Functional Design",     "2005-01-01", "ami_ES2002b.txt", "ES2002a"),
    ("ES2002c", "AMI ES2002c — Conceptual Design",     "2005-01-01", "ami_ES2002c.txt", "ES2002b"),
    ("ES2002d", "AMI ES2002d — Detailed Design",       "2005-01-01", "ami_ES2002d.txt", "ES2002c"),
]


async def main():
    print(f"=== AMI ES2002a~d 텍스트 투입 (project_id={PROJECT_ID}) ===\n")
    async with httpx.AsyncClient(timeout=600) as client:
        for mid, title, date, filename, prev in MEETINGS:
            path = TESTS_DIR / filename
            transcript = path.read_text(encoding="utf-8")
            n_chars = len(transcript)
            print(f"[투입] {mid} ({n_chars:,} chars) prev={prev}")

            payload = {
                "meeting_id": mid,
                "transcript": transcript,
                "title": title,
                "date": date,
                "project_id": PROJECT_ID,
            }
            if prev:
                payload["previous_meeting_id"] = prev

            r = await client.post(f"{API}/process-text", json=payload)
            r.raise_for_status()
            data = r.json()
            gd = data.get("graph_data", {})
            n_speakers = len(gd.get("speakers", []))
            n_topics = len(gd.get("topics", []))
            n_entities = len(gd.get("entities", []))
            n_actions = len(gd.get("action_items", []))
            n_decisions = len(gd.get("decisions", []))
            print(f"  -> node_count={data['node_count']}  "
                  f"[spk={n_speakers} top={n_topics} ent={n_entities} act={n_actions} dec={n_decisions}]")
            print(f"     note={data['note_path']}")

    print("\n[OK] 4회차 투입 완료")


if __name__ == "__main__":
    asyncio.run(main())
