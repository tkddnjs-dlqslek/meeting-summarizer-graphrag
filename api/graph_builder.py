from graph.neo4j_client import execute_write
from graph import cypher_queries as Q


DEFAULT_PROJECT = "default"


async def build_graph(graph_data: dict):
    """
    extractor.extract_graph_data() 결과를 받아 Neo4j에 모든 노드/관계를 생성한다.

    스키마:
      - Speaker / Topic / Entity는 project_id 스코프 글로벌 노드
      - ActionItem / Decision은 meeting_id 로컬 노드
      - 회차 연결은 PARTICIPATED_IN / DISCUSSED_IN / MENTIONED_IN 엣지로 생성
      - previous_meeting_id가 graph_data에 있으면 Meeting-FOLLOWS-Meeting 엣지 생성
    """
    mid = graph_data["meeting_id"]
    pid = graph_data.get("project_id") or DEFAULT_PROJECT

    # ── Meeting 노드 ─────────────────────────────────────────────────────────
    await execute_write(Q.MERGE_MEETING, {
        "meeting_id": mid,
        "title": graph_data.get("title", ""),
        "date": graph_data.get("date", ""),
        "project_id": pid,
    })

    # ── Speaker (글로벌) + PARTICIPATED_IN ─────────────────────────────────
    for s in graph_data.get("speakers", []):
        await execute_write(Q.MERGE_SPEAKER, {
            "name": s["name"],
            "project_id": pid,
            "role": s.get("role", ""),
        })
        await execute_write(Q.REL_SPEAKER_PARTICIPATED_IN, {
            "speaker_name": s["name"],
            "project_id": pid,
            "meeting_id": mid,
            "speaking_time_ratio": s.get("speaking_time_ratio", 0.0),
        })

    # ── Topic (글로벌) + DISCUSSED_IN ─────────────────────────────────────
    for t in graph_data.get("topics", []):
        await execute_write(Q.MERGE_TOPIC, {
            "name": t["name"],
            "project_id": pid,
            "category": t.get("category", ""),
            "summary": t.get("summary", ""),
        })
        await execute_write(Q.REL_TOPIC_DISCUSSED_IN, {
            "topic_name": t["name"],
            "project_id": pid,
            "meeting_id": mid,
        })
        for related in t.get("related_topics", []):
            # 관련 주제는 같은 프로젝트 안에서만 연결
            await execute_write(Q.MERGE_TOPIC, {
                "name": related,
                "project_id": pid,
                "category": "",
                "summary": "",
            })
            await execute_write(Q.REL_TOPIC_RELATED_TO, {
                "topic1": t["name"],
                "topic2": related,
                "project_id": pid,
            })

    # ── Entity (글로벌) + MENTIONED_IN ────────────────────────────────────
    for e in graph_data.get("entities", []):
        await execute_write(Q.MERGE_ENTITY, {
            "name": e["name"],
            "project_id": pid,
            "type": e.get("type", ""),
        })
        await execute_write(Q.REL_ENTITY_MENTIONED_IN, {
            "entity_name": e["name"],
            "project_id": pid,
            "meeting_id": mid,
        })
        for topic_name in e.get("associated_topics", []):
            await execute_write(Q.REL_ENTITY_ASSOCIATED_WITH_TOPIC, {
                "entity_name": e["name"],
                "topic_name": topic_name,
                "project_id": pid,
            })

    # ── ActionItem (로컬) ─────────────────────────────────────────────────
    for a in graph_data.get("action_items", []):
        await execute_write(Q.MERGE_ACTION_ITEM, {
            "description": a["description"],
            "meeting_id": mid,
            "project_id": pid,
            "owner": a.get("owner", ""),
            "deadline": a.get("deadline"),
            "status": a.get("status", "pending"),
        })
        if a.get("owner"):
            await execute_write(Q.REL_SPEAKER_OWNS_ACTION, {
                "speaker_name": a["owner"],
                "project_id": pid,
                "action_description": a["description"],
                "meeting_id": mid,
            })

    # ── Decision (로컬) ───────────────────────────────────────────────────
    for d in graph_data.get("decisions", []):
        await execute_write(Q.MERGE_DECISION, {
            "description": d["description"],
            "meeting_id": mid,
            "project_id": pid,
            "rationale": d.get("rationale", ""),
        })
        for topic_name in d.get("related_topics", []):
            await execute_write(Q.REL_DECISION_ABOUT_TOPIC, {
                "decision_description": d["description"],
                "topic_name": topic_name,
                "meeting_id": mid,
                "project_id": pid,
            })

    # ── Speaker-MENTIONED-Topic ───────────────────────────────────────────
    for link in graph_data.get("speaker_topic_links", []):
        await execute_write(Q.REL_SPEAKER_MENTIONED_TOPIC, {
            "speaker_name": link["speaker_name"],
            "topic_name": link["topic_name"],
            "project_id": pid,
        })

    # ── Meeting FOLLOWS (이전 회차 명시된 경우만) ──────────────────────────
    prev_mid = graph_data.get("previous_meeting_id")
    if prev_mid:
        await execute_write(Q.REL_MEETING_FOLLOWS, {
            "meeting_id": mid,
            "previous_meeting_id": prev_mid,
        })
