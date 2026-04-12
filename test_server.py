"""서버 없이 핵심 로직 직접 테스트 (Neo4j 연결 + extractor + graph_builder)"""
import asyncio
import sys
sys.path.insert(0, '.')

from dotenv import load_dotenv
load_dotenv()

from graph.neo4j_client import verify_connectivity, init_constraints, close_driver, execute_query
from graph import cypher_queries as Q
from api.extractor import extract_graph_data
from api.graph_builder import build_graph
from api.obsidian_writer import write_meeting_note


SAMPLE = open("tests/sample_transcript.txt", encoding="utf-8").read()
MEETING_ID = "test-graphrag-001"
TITLE = "Q2 임상시험 계획 검토"


async def main():
    print("\n[1] Neo4j 연결 확인...")
    await verify_connectivity()
    await init_constraints()
    print("    AuraDB 연결 성공")

    print("\n[2] Claude tool_use 추출 (약 10~20초)...")
    graph_data = await extract_graph_data(SAMPLE, MEETING_ID, TITLE)
    print("    추출 완료")
    print(f"    - 참석자: {[s['name'] for s in graph_data['speakers']]}")
    print(f"    - 주제: {[t['name'] for t in graph_data['topics']]}")
    print(f"    - 액션아이템: {len(graph_data['action_items'])}개")
    print(f"    - 결정사항: {len(graph_data['decisions'])}개")
    print(f"    - 엔티티: {[e['name'] for e in graph_data['entities']]}")

    print("\n[3] Neo4j 그래프 구축...")
    await build_graph(graph_data)
    stats = await execute_query(Q.GRAPH_STATS, {"meeting_id": MEETING_ID})
    for row in stats:
        print(f"    - {row['label']}: {row['count']}개")
    print("    그래프 구축 완료")

    print("\n[4] Obsidian 노트 생성...")
    graph_data["date"] = "2026-03-21"
    note_path = write_meeting_note(graph_data)
    print(f"    노트 생성: {note_path}")

    await close_driver()
    print("\n모든 테스트 통과!")


if __name__ == "__main__":
    asyncio.run(main())
