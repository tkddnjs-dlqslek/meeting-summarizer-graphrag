"""Phase 4 교차 평가
  - WER: 원본 AMI transcript vs Whisper 결과
  - 2개 질의를 text / audio 프로젝트에 각각 던져 답변 비교
"""

import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx
import jiwer

API = "http://localhost:8000"
TESTS = Path(__file__).parent

REF_PATH = TESTS / "ami_ES2002a.txt"
HYP_PATH = TESTS / "ami_ES2002a_whisper.txt"


def strip_speaker_prefix(text: str) -> str:
    """'Laura: ...' 같은 prefix 제거 → 텍스트만."""
    out_lines = []
    for line in text.splitlines():
        # 메타 라인 스킵
        if line.startswith("Meeting ID:") or line.startswith("Source:") or line.startswith("Speakers:"):
            continue
        # "Name: text" 패턴
        m = re.match(r"^[A-Za-z]+:\s*(.*)$", line)
        if m:
            out_lines.append(m.group(1))
        else:
            out_lines.append(line)
    return " ".join(out_lines)


def compute_wer():
    print("=" * 60)
    print("[Phase 4a] WER 측정 — AMI reference vs Whisper")
    print("=" * 60)

    ref_raw = REF_PATH.read_text(encoding="utf-8")
    hyp_raw = HYP_PATH.read_text(encoding="utf-8")

    ref = strip_speaker_prefix(ref_raw)
    hyp = hyp_raw

    # 정규화: 대문자, 구두점 제거, 다중 공백 단일화
    normalizer = jiwer.Compose([
        jiwer.ToLowerCase(),
        jiwer.RemovePunctuation(),
        jiwer.RemoveMultipleSpaces(),
        jiwer.Strip(),
        jiwer.ReduceToListOfListOfWords(),
    ])

    ref_words_len = len(" ".join(ref.split()).split())
    hyp_words_len = len(" ".join(hyp.split()).split())

    print(f"  reference 단어 수: {ref_words_len:,}")
    print(f"  whisper   단어 수: {hyp_words_len:,}")

    out = jiwer.process_words(
        ref, hyp,
        reference_transform=normalizer,
        hypothesis_transform=normalizer,
    )
    print(f"\n  WER : {out.wer*100:.2f}%  (word error rate)")
    print(f"  MER : {out.mer*100:.2f}%  (match error rate)")
    print(f"  WIL : {out.wil*100:.2f}%  (word information lost)")
    print(f"  substitutions: {out.substitutions}")
    print(f"  deletions    : {out.deletions}")
    print(f"  insertions   : {out.insertions}")
    print(f"  hits         : {out.hits}")
    print()


QUESTIONS = [
    ("Q1. 사실 추적",
     "In the ES2002a kick-off meeting, what are the participants' names and their assigned roles, and what is the target production cost of the remote control?"),
    ("Q2. 의제 흐름",
     "What were the main topics discussed in this meeting and in what order? What was the key decision made at the end?"),
]


async def run_agents(client, project_id, question):
    r = await client.post(
        f"{API}/agents",
        json={"question": question, "project_id": project_id},
    )
    r.raise_for_status()
    return r.json()["final_answer"]


async def compare_queries():
    print("=" * 60)
    print("[Phase 4b] 교차 질의 비교 — ES2002a만 공통 범위")
    print("=" * 60)
    # ami_es2002_audio는 ES2002a 1회차만 있고,
    # ami_es2002_text는 4회차 전부 있음.
    # 공정한 비교를 위해 질문을 "ES2002a 회차 수준"으로 제한.
    # 즉 text 프로젝트에도 project_id 모드지만 질문 내용이 ES2002a에 집중되도록.

    async with httpx.AsyncClient(timeout=300) as client:
        for label, q in QUESTIONS:
            print(f"\n{'-'*60}\n{label}\nQ: {q}\n{'-'*60}")

            text_ans, audio_ans = await asyncio.gather(
                run_agents(client, "ami_es2002_text", q),
                run_agents(client, "ami_es2002_audio", q),
            )

            print("\n[TEXT project] 답변:")
            print(text_ans[:1200])
            print()
            print("[AUDIO project] 답변:")
            print(audio_ans[:1200])


async def main():
    compute_wer()
    await compare_queries()


if __name__ == "__main__":
    asyncio.run(main())
