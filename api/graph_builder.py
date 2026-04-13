from graph.neo4j_client import execute_write, execute_query
from graph import cypher_queries as Q
from api.normalize import find_canonical_name


DEFAULT_PROJECT = "default"

# 카테고리별 유사도 임계값
# - Speaker는 보수적 (사람 이름은 표기가 비슷해도 다른 사람일 수 있음)
# - Topic/Entity는 표현 다양성이 크니 약간 낮게
SPEAKER_THRESHOLD = 0.92
TOPIC_THRESHOLD = 0.85
ENTITY_THRESHOLD = 0.88


async def _load_existing_names(project_id: str) -> tuple[list[str], list[str], list[str]]:
    """프로젝트에 이미 등록된 Speaker / Topic / Entity 이름 목록을 반환."""
    speaker_rows = await execute_query(
        Q.PREVIOUS_SPEAKERS_BY_PROJECT, {"project_id": project_id}
    )
    topic_rows = await execute_query(
        Q.PREVIOUS_TOPICS_BY_PROJECT, {"project_id": project_id}
    )
    entity_rows = await execute_query(
        Q.PREVIOUS_ENTITIES_BY_PROJECT, {"project_id": project_id}
    )
    return (
        [r["name"] for r in speaker_rows if r.get("name")],
        [r["name"] for r in topic_rows if r.get("name")],
        [r["name"] for r in entity_rows if r.get("name")],
    )


def _resolve(name: str, existing: list[str], mapping: dict[str, str], threshold: float) -> str:
    """이름 하나를 canonical로 해결. 결과를 mapping 캐시에 기록.

    existing 목록은 DB의 기존 이름 + 이번 배치에서 이미 확정된 canonical 이름을
    합친 것. 같은 배치 안에서 "Remote Control"과 "Remote control"이 동시에
    들어와도 같은 노드로 수렴하게 만든다.
    """
    if name in mapping:
        return mapping[name]
    canonical = find_canonical_name(name, existing, threshold=threshold)
    resolved = canonical if canonical else name
    mapping[name] = resolved
    if resolved not in existing:
        existing.append(resolved)
    return resolved


async def build_graph(graph_data: dict):
    """
    extractor.extract_graph_data() 결과를 받아 Neo4j에 모든 노드/관계를 생성한다.

    스키마:
      - Speaker / Topic / Entity는 project_id 스코프 글로벌 노드
      - ActionItem / Decision은 meeting_id 로컬 노드
      - 회차 연결은 PARTICIPATED_IN / DISCUSSED_IN / MENTIONED_IN 엣지로 생성
      - previous_meeting_id가 graph_data에 있으면 Meeting-FOLLOWS-Meeting 엣지 생성

    정규화 (api/normalize.py):
      - Speaker / Topic / Entity 이름을 MERGE 전에 기존 이름과 임베딩 유사도로
        비교해 canonical 이름으로 치환한다. 치환 결과는 이 함수 안에서 유지되는
        매핑 테이블로 action_item.owner, decision.related_topics,
        entity.associated_topics, speaker_topic_links 등 파생 참조에도 전파된다.
    """
    mid = graph_data["meeting_id"]
    pid = graph_data.get("project_id") or DEFAULT_PROJECT

    # ── 기존 이름 조회 + 정규화 매핑 구축 ────────────────────────────────────
    existing_speakers, existing_topics, existing_entities = await _load_existing_names(pid)
    speaker_map: dict[str, str] = {}
    topic_map: dict[str, str] = {}
    entity_map: dict[str, str] = {}

    # ── Meeting 노드 ─────────────────────────────────────────────────────────
    await execute_write(Q.MERGE_MEETING, {
        "meeting_id": mid,
        "title": graph_data.get("title", ""),
        "date": graph_data.get("date", ""),
        "project_id": pid,
    })

    # ── Speaker (글로벌) + PARTICIPATED_IN ─────────────────────────────────
    for s in graph_data.get("speakers", []):
        canonical = _resolve(s["name"], existing_speakers, speaker_map, SPEAKER_THRESHOLD)
        await execute_write(Q.MERGE_SPEAKER, {
            "name": canonical,
            "project_id": pid,
            "role": s.get("role", ""),
        })
        await execute_write(Q.REL_SPEAKER_PARTICIPATED_IN, {
            "speaker_name": canonical,
            "project_id": pid,
            "meeting_id": mid,
            "speaking_time_ratio": s.get("speaking_time_ratio", 0.0),
        })

    # ── Topic (글로벌) + DISCUSSED_IN ─────────────────────────────────────
    for t in graph_data.get("topics", []):
        canonical = _resolve(t["name"], existing_topics, topic_map, TOPIC_THRESHOLD)
        await execute_write(Q.MERGE_TOPIC, {
            "name": canonical,
            "project_id": pid,
            "category": t.get("category", ""),
            "summary": t.get("summary", ""),
        })
        await execute_write(Q.REL_TOPIC_DISCUSSED_IN, {
            "topic_name": canonical,
            "project_id": pid,
            "meeting_id": mid,
        })
        for related in t.get("related_topics", []):
            related_canonical = _resolve(related, existing_topics, topic_map, TOPIC_THRESHOLD)
            # 관련 주제 노드 선 생성 (이번 회차에 DISCUSSED_IN은 안 붙임)
            await execute_write(Q.MERGE_TOPIC, {
                "name": related_canonical,
                "project_id": pid,
                "category": "",
                "summary": "",
            })
            await execute_write(Q.REL_TOPIC_RELATED_TO, {
                "topic1": canonical,
                "topic2": related_canonical,
                "project_id": pid,
            })

    # ── Entity (글로벌) + MENTIONED_IN ────────────────────────────────────
    for e in graph_data.get("entities", []):
        canonical = _resolve(e["name"], existing_entities, entity_map, ENTITY_THRESHOLD)
        await execute_write(Q.MERGE_ENTITY, {
            "name": canonical,
            "project_id": pid,
            "type": e.get("type", ""),
        })
        await execute_write(Q.REL_ENTITY_MENTIONED_IN, {
            "entity_name": canonical,
            "project_id": pid,
            "meeting_id": mid,
        })
        for topic_name in e.get("associated_topics", []):
            topic_canonical = topic_map.get(topic_name) or _resolve(
                topic_name, existing_topics, topic_map, TOPIC_THRESHOLD
            )
            await execute_write(Q.REL_ENTITY_ASSOCIATED_WITH_TOPIC, {
                "entity_name": canonical,
                "topic_name": topic_canonical,
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
        owner = a.get("owner")
        if owner:
            owner_canonical = speaker_map.get(owner) or _resolve(
                owner, existing_speakers, speaker_map, SPEAKER_THRESHOLD
            )
            await execute_write(Q.REL_SPEAKER_OWNS_ACTION, {
                "speaker_name": owner_canonical,
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
            topic_canonical = topic_map.get(topic_name) or _resolve(
                topic_name, existing_topics, topic_map, TOPIC_THRESHOLD
            )
            await execute_write(Q.REL_DECISION_ABOUT_TOPIC, {
                "decision_description": d["description"],
                "topic_name": topic_canonical,
                "meeting_id": mid,
                "project_id": pid,
            })

    # ── Speaker-MENTIONED-Topic ───────────────────────────────────────────
    for link in graph_data.get("speaker_topic_links", []):
        speaker_canonical = speaker_map.get(link["speaker_name"]) or _resolve(
            link["speaker_name"], existing_speakers, speaker_map, SPEAKER_THRESHOLD
        )
        topic_canonical = topic_map.get(link["topic_name"]) or _resolve(
            link["topic_name"], existing_topics, topic_map, TOPIC_THRESHOLD
        )
        await execute_write(Q.REL_SPEAKER_MENTIONED_TOPIC, {
            "speaker_name": speaker_canonical,
            "topic_name": topic_canonical,
            "project_id": pid,
        })

    # ── Meeting FOLLOWS (이전 회차 명시된 경우만) ──────────────────────────
    prev_mid = graph_data.get("previous_meeting_id")
    if prev_mid:
        await execute_write(Q.REL_MEETING_FOLLOWS, {
            "meeting_id": mid,
            "previous_meeting_id": prev_mid,
        })
