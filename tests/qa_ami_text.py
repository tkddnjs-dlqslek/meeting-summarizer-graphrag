"""ami_es2002_text 프로젝트에 3가지 질의 실행."""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
try: sys.stdout.reconfigure(encoding="utf-8")
except: pass
import httpx

API = "http://localhost:8000"
PID = "ami_es2002_text"

QUESTIONS = [
    ("A. 설계 진화 (주제 중심)",
     "What functional requirements were added, removed, or changed as the remote control design evolved from ES2002a to ES2002d, and what drove those changes?"),
    ("B. 결정 번복 (실행 중심)",
     "Which early decisions were later reversed or modified across the four meetings, and what was the justification for each change?"),
    ("C. 갈등과 합의 (맥락 중심)",
     "Where did team members (Laura, Andrew, David, Craig) disagree the most, and how were those disagreements resolved?"),
]


async def main():
    async with httpx.AsyncClient(timeout=300) as c:
        for label, q in QUESTIONS:
            print(f"\n{'='*70}\n{label}\nQ: {q}\n{'-'*70}")
            r = await c.post(f"{API}/agents", json={"question": q, "project_id": PID})
            r.raise_for_status()
            print(r.json()["final_answer"])

asyncio.run(main())
