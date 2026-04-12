"""4회차 투입 후 Neo4j 교차 연결만 검증. 투입은 run_4week_test.py 참조."""

import asyncio
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


async def main():
    print(f"=== {PROJECT_ID} 교차 연결 검증 ===\n")

    print("[STEP 6a] Speaker — 4회차 모두 참석한 사람")
    speaker_rows = await execute_query(
        """
        MATCH (s:Speaker {project_id: $pid})-[:PARTICIPATED_IN]->(m:Meeting)
        WITH s, collect(DISTINCT m.meeting_id) AS meetings
        RETURN s.name AS name, s.role AS role, meetings
        ORDER BY size(meetings) DESC, s.name
        """,
        {"pid": PROJECT_ID},
    )
    shared = 0
    for r in speaker_rows:
        marker = "[4/4]" if len(r["meetings"]) == 4 else f"[{len(r['meetings'])}/4]"
        print(f"  {marker} {r['name']} ({r['role']}) : {r['meetings']}")
        if len(r["meetings"]) == 4:
            shared += 1
    print(f"  >> 4회차 모두 참석한 공유 Speaker 노드: {shared}명")
    assert shared >= 3, f"FAIL: 4회차 공유 Speaker가 {shared}명뿐 (3명 이상 기대)"
    print("  PASS\n")

    print("[STEP 6b] Topic — 2회차 이상 반복된 주제 TOP 15")
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
    print(f"  >> 2회차 이상 공유 Topic 노드: {len(topic_rows)}개")
    for r in topic_rows:
        print(f"   [{len(r['meetings'])}x][{r['category']}] {r['name']} : {r['meetings']}")
    print()

    print("[STEP 6c] Entity — 2회차 이상 반복된 엔티티")
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
    print(f"  >> 2회차 이상 공유 Entity 노드: {len(entity_rows)}개")
    for r in entity_rows:
        print(f"   [{len(r['meetings'])}x][{r['type']}] {r['name']} : {r['meetings']}")
    print()

    print("[STEP 6d] Meeting FOLLOWS 체인")
    follows = await execute_query(
        """
        MATCH (curr:Meeting {project_id: $pid})-[:FOLLOWS]->(prev:Meeting)
        RETURN curr.meeting_id AS curr, prev.meeting_id AS prev
        ORDER BY curr.meeting_id
        """,
        {"pid": PROJECT_ID},
    )
    for r in follows:
        print(f"   {r['curr']} -> {r['prev']}")
    print(f"  >> FOLLOWS 엣지 총 {len(follows)}개")
    assert len(follows) == 3, f"FAIL: FOLLOWS 3개 기대, 실제 {len(follows)}개"
    print("  PASS\n")

    print("[STEP 6e] 전체 그래프 노드/엣지 통계 (project 스코프)")
    node_stats = await execute_query(
        """
        MATCH (n {project_id: $pid})
        WITH labels(n)[0] AS label, count(n) AS cnt
        RETURN label, cnt
        ORDER BY cnt DESC
        """,
        {"pid": PROJECT_ID},
    )
    for r in node_stats:
        print(f"   {r['label']}: {r['cnt']}")

    edge_stats = await execute_query(
        """
        MATCH (a {project_id: $pid})-[r]->(b)
        WHERE b.project_id = $pid OR b:Meeting
        RETURN type(r) AS rel, count(r) AS cnt
        ORDER BY cnt DESC
        """,
        {"pid": PROJECT_ID},
    )
    print("  --- 엣지 ---")
    for r in edge_stats:
        print(f"   {r['rel']}: {r['cnt']}")
    print()

    await close_driver()

    print("[STEP 6f] /agents project 모드 질의")
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
        print("  --- final_answer ---")
        print(result["final_answer"])
        print("  --- end ---")

    print("\n=== 검증 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
