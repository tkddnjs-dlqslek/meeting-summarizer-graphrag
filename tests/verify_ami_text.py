"""AMI ES2002 텍스트 프로젝트의 교차 연결 검증."""

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
PROJECT_ID = "ami_es2002_text"


async def main():
    print(f"=== {PROJECT_ID} 교차 연결 검증 ===\n")

    print("[1] Speaker — 4회차 참석 현황")
    rows = await execute_query(
        """
        MATCH (s:Speaker {project_id: $pid})-[:PARTICIPATED_IN]->(m:Meeting)
        WITH s, collect(DISTINCT m.meeting_id) AS meetings
        RETURN s.name AS name, s.role AS role, meetings
        ORDER BY size(meetings) DESC, s.name
        """,
        {"pid": PROJECT_ID},
    )
    shared = 0
    for r in rows:
        tag = f"[{len(r['meetings'])}/4]"
        print(f"  {tag} {r['name']} ({r['role']}) : {sorted(r['meetings'])}")
        if len(r["meetings"]) == 4:
            shared += 1
    print(f"  >> 4회차 모두 참석 공유 Speaker: {shared}명\n")

    print("[2] Topic — 회차 간 공유 (2회 이상)")
    topic_rows = await execute_query(
        """
        MATCH (t:Topic {project_id: $pid})-[:DISCUSSED_IN]->(m:Meeting)
        WITH t, collect(DISTINCT m.meeting_id) AS meetings
        WHERE size(meetings) >= 2
        RETURN t.name AS name, t.category AS category, meetings
        ORDER BY size(meetings) DESC, t.name
        LIMIT 20
        """,
        {"pid": PROJECT_ID},
    )
    print(f"  공유 Topic 노드: {len(topic_rows)}개")
    for r in topic_rows:
        print(f"   [{len(r['meetings'])}x][{r['category']}] {r['name']} : {sorted(r['meetings'])}")
    print()

    print("[3] Entity — 회차 간 공유 (2회 이상)")
    entity_rows = await execute_query(
        """
        MATCH (e:Entity {project_id: $pid})-[:MENTIONED_IN]->(m:Meeting)
        WITH e, collect(DISTINCT m.meeting_id) AS meetings
        WHERE size(meetings) >= 2
        RETURN e.name AS name, e.type AS type, meetings
        ORDER BY size(meetings) DESC, e.name
        LIMIT 20
        """,
        {"pid": PROJECT_ID},
    )
    print(f"  공유 Entity 노드: {len(entity_rows)}개")
    for r in entity_rows:
        print(f"   [{len(r['meetings'])}x][{r['type']}] {r['name']} : {sorted(r['meetings'])}")
    print()

    print("[4] Meeting FOLLOWS 체인")
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
    print(f"  >> FOLLOWS 엣지 {len(follows)}개\n")

    print("[5] 전체 통계")
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

    print("[6] /agents project 모드 — 리모컨 설계 흐름 질의")
    async with httpx.AsyncClient(timeout=300) as client:
        r = await client.post(
            f"{API}/agents",
            json={
                "question": "How did the remote control design evolve across the four meetings? What key decisions happened in each meeting and what trade-offs did the team face?",
                "project_id": PROJECT_ID,
            },
        )
        r.raise_for_status()
        result = r.json()
        print("  --- final_answer ---")
        print(result["final_answer"])
        print("  --- end ---")

    print("\n=== 완료 ===")


if __name__ == "__main__":
    asyncio.run(main())
