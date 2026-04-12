import asyncio
import sys
from graph.neo4j_client import execute_query, close_driver


async def check(meeting_id: str):
    # Meeting 연결 노드 통계
    rows = await execute_query(
        """
        MATCH (m:Meeting {meeting_id: $meeting_id})
        OPTIONAL MATCH (n)-[]-(m)
        WITH labels(n)[0] AS label, count(DISTINCT n) AS cnt
        RETURN label, cnt
        ORDER BY cnt DESC
        """,
        {"meeting_id": meeting_id},
    )
    print(f"=== 회차 {meeting_id} 연결 노드 ===")
    total = 0
    for r in rows:
        if r["label"]:
            print(f"  {r['label']}: {r['cnt']}")
            total += r["cnt"]
    print(f"  합계: {total}")

    # 엣지 통계
    edge_rows = await execute_query(
        """
        MATCH (m:Meeting {meeting_id: $meeting_id})-[r]-()
        RETURN type(r) AS rel, count(r) AS cnt
        ORDER BY cnt DESC
        """,
        {"meeting_id": meeting_id},
    )
    print("=== Meeting 직결 관계 ===")
    for r in edge_rows:
        print(f"  {r['rel']}: {r['cnt']}")

    await close_driver()


if __name__ == "__main__":
    mid = sys.argv[1] if len(sys.argv) > 1 else "test-001"
    asyncio.run(check(mid))
