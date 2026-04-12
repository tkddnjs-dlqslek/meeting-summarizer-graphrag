"""
4회차 연속성 회귀 테스트

목적:
  1. project_id 스코프 글로벌 스키마가 4회차까지 깨지지 않고 동작하는지
  2. 같은 Speaker / Topic이 4회차에 걸쳐 실제로 공유 노드로 병합되는지
  3. /agents project 모드가 여러 회차에 걸친 답변을 만드는지

전제:
  - FastAPI 서버가 http://localhost:8000 에서 실행 중
  - Neo4j DB는 리팩터링 이후 비워진 상태
  - tests/sample_transcript.txt + kr204_week2~4 transcript 존재
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import httpx

from graph.neo4j_client import execute_query, close_driver

API = "http://localhost:8000"
PROJECT_ID = "kr204_phase2"
TESTS_DIR = Path(__file__).parent

MEETINGS = [
    ("kr204-w1", "KR-204 Phase 2 임상시험 계획 검토",    "2026-03-21", "sample_transcript.txt",       None),
    ("kr204-w2", "KR-204 Phase 2 임상시험 2차 진행 회의", "2026-04-20", "kr204_week2_transcript.txt", "kr204-w1"),
    ("kr204-w3", "KR-204 Phase 2 임상시험 3차 진행 회의", "2026-05-15", "kr204_week3_transcript.txt", "kr204-w2"),
    ("kr204-w4", "KR-204 Phase 2 임상시험 4차 진행 회의", "2026-06-30", "kr204_week4_transcript.txt", "kr204-w3"),
]


async def post_meeting(client: httpx.AsyncClient, meeting_id, title, date, filename, prev_id):
    transcript = (TESTS_DIR / filename).read_text(encoding="utf-8")
    payload = {
        "meeting_id": meeting_id,
        "transcript": transcript,
        "title": title,
        "date": date,
        "project_id": PROJECT_ID,
    }
    if prev_id:
        payload["previous_meeting_id"] = prev_id

    r = await client.post(f"{API}/process-text", json=payload, timeout=300)
    r.raise_for_status()
    data = r.json()
    return data


async def main():
    print(f"=== 4회차 회귀 테스트 (project_id={PROJECT_ID}) ===\n")

    # ── STEP 1: 단일 기본 프로젝트 회귀 테스트 ─────────────────────────────
    print("[STEP 3] default project 단일 회의 회귀 테스트")
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API}/process-text",
            json={
                "meeting_id": "regression-default-001",
                "transcript": (TESTS_DIR / "sample_transcript.txt").read_text(encoding="utf-8"),
                "title": "단일 회귀 테스트",
                "date": "2026-03-21",
                "project_id": "default",
            },
            timeout=300,
        )
        r.raise_for_status()
        data = r.json()
        print(f"  node_count={data['node_count']}, note={data['note_path']}")
        assert data["node_count"] > 0, "단일 회의에서 노드가 생성되지 않음"
        print("  PASS: 단일 회의 정상 동작\n")

    # ── STEP 2: 4회차 순차 투입 ────────────────────────────────────────────
    print("[STEP 4-5] test_series 4회차 순차 투입")
    async with httpx.AsyncClient() as client:
        for mid, title, date, filename, prev in MEETINGS:
            print(f"  투입: {mid} ({date}) prev={prev}")
            data = await post_meeting(client, mid, title, date, filename, prev)
            print(f"    -> node_count={data['node_count']}, note={data['note_path']}")

    # ── STEP 3: Neo4j 직접 쿼리로 교차 회차 병합 확인 ───────────────────────
    print("\n[STEP 6a] Speaker 공유 확인 — project 전체의 Speaker별 참석 회차 수")
    speaker_rows = await execute_query(
        """
        MATCH (s:Speaker {project_id: $pid})-[:PARTICIPATED_IN]->(m:Meeting)
        WITH s, collect(DISTINCT m.meeting_id) AS meetings
        RETURN s.name AS name, s.role AS role, meetings
        ORDER BY size(meetings) DESC, s.name
        """,
        {"pid": PROJECT_ID},
    )
    shared_speakers = 0
    for r in speaker_rows:
        marker = "***" if len(r["meetings"]) == 4 else "   "
        print(f"  {marker} {r['name']} ({r['role']}) — 참석 회차 {len(r['meetings'])}개: {r['meetings']}")
        if len(r["meetings"]) == 4:
            shared_speakers += 1

    if shared_speakers >= 3:
        print(f"  PASS: {shared_speakers}명이 4회차 모두에 공유 노드로 연결됨")
    else:
        print(f"  FAIL: 4회차 모두 참석한 공유 Speaker가 {shared_speakers}명뿐")

    print("\n[STEP 6b] Topic 공유 확인 — 같은 Topic이 여러 회차에서 등장")
    topic_rows = await execute_query(
        """
        MATCH (t:Topic {project_id: $pid})-[:DISCUSSED_IN]->(m:Meeting)
        WITH t, collect(DISTINCT m.meeting_id) AS meetings
        WHERE size(meetings) >= 2
        RETURN t.name AS name, t.category AS category, meetings
        ORDER BY size(meetings) DESC, t.name
        LIMIT 15
        """,
        {"pid": PROJECT_ID},
    )
    print(f"  2회차 이상에 등장하는 공유 Topic 수: {len(topic_rows)}")
    for r in topic_rows[:10]:
        print(f"  - [{r['category']}] {r['name']} ({len(r['meetings'])}회차: {r['meetings']})")

    print("\n[STEP 6c] Entity 공유 확인")
    entity_rows = await execute_query(
        """
        MATCH (e:Entity {project_id: $pid})-[:MENTIONED_IN]->(m:Meeting)
        WITH e, collect(DISTINCT m.meeting_id) AS meetings
        WHERE size(meetings) >= 2
        RETURN e.name AS name, e.type AS type, meetings
        ORDER BY size(meetings) DESC, e.name
        LIMIT 15
        """,
        {"pid": PROJECT_ID},
    )
    print(f"  2회차 이상에 등장하는 공유 Entity 수: {len(entity_rows)}")
    for r in entity_rows[:10]:
        print(f"  - [{r['type']}] {r['name']} ({len(r['meetings'])}회차: {r['meetings']})")

    print("\n[STEP 6d] FOLLOWS 체인 검증")
    follows = await execute_query(
        """
        MATCH (curr:Meeting {project_id: $pid})-[:FOLLOWS]->(prev:Meeting)
        RETURN curr.meeting_id AS curr, prev.meeting_id AS prev
        ORDER BY curr.meeting_id
        """,
        {"pid": PROJECT_ID},
    )
    print(f"  FOLLOWS 엣지 {len(follows)}개:")
    for r in follows:
        print(f"    {r['curr']} -> {r['prev']}")
    if len(follows) == 3:
        print("  PASS: w2->w1, w3->w2, w4->w3 체인 완성")
    else:
        print(f"  FAIL: FOLLOWS 체인이 3개가 아님 ({len(follows)}개)")

    await close_driver()

    # ── STEP 4: /agents project 모드 ──────────────────────────────────────
    print("\n[STEP 6e] /agents project 모드 질의 — 프로젝트 전체에 걸친 변화")
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{API}/agents",
            json={
                "question": "환자 등록 일정이 4회차에 걸쳐 어떻게 조정되었고, 그 이유는 무엇인가?",
                "project_id": PROJECT_ID,
            },
        )
        r.raise_for_status()
        result = r.json()
        print("  final_answer 일부:")
        print("  " + "-" * 60)
        for line in result["final_answer"].split("\n")[:15]:
            print("  " + line)
        print("  " + "-" * 60)

    print("\n=== 테스트 완료 ===")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))
    asyncio.run(main())
