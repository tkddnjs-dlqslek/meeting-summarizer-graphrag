# ── 그래프 구축 ──────────────────────────────────────────────────────────────
#
# 스키마 설계 원칙
#   - Speaker / Topic / Entity : project_id 스코프 글로벌 노드
#     (같은 프로젝트의 여러 회의에서 공유 → 교차 회의 연결)
#   - ActionItem / Decision    : meeting_id 스코프 로컬 노드
#     (특정 회차의 이벤트)
#   - Meeting                  : 독립 식별자 (meeting_id)
#
# 회차 연결 엣지
#   (:Speaker)-[:PARTICIPATED_IN {speaking_time_ratio}]->(:Meeting)
#   (:Topic)-[:DISCUSSED_IN]->(:Meeting)
#   (:Entity)-[:MENTIONED_IN]->(:Meeting)
#   (:Meeting)-[:FOLLOWS]->(:Meeting)   — 선행 회의를 지정하면 생성

MERGE_MEETING = """
MERGE (m:Meeting {meeting_id: $meeting_id})
SET m.title = $title,
    m.date = $date,
    m.project_id = $project_id
"""

MERGE_SPEAKER = """
MERGE (s:Speaker {name: $name, project_id: $project_id})
SET s.role = coalesce($role, s.role)
"""

MERGE_TOPIC = """
MERGE (t:Topic {name: $name, project_id: $project_id})
SET t.category = coalesce($category, t.category),
    t.summary = coalesce($summary, t.summary)
"""

MERGE_ENTITY = """
MERGE (e:Entity {name: $name, project_id: $project_id})
SET e.type = coalesce($type, e.type)
"""

MERGE_ACTION_ITEM = """
MERGE (a:ActionItem {description: $description, meeting_id: $meeting_id})
SET a.owner = $owner,
    a.deadline = $deadline,
    a.status = $status,
    a.project_id = $project_id
"""

MERGE_DECISION = """
MERGE (d:Decision {description: $description, meeting_id: $meeting_id})
SET d.rationale = $rationale,
    d.project_id = $project_id
"""

# ── 회차 연결 관계 ────────────────────────────────────────────────────────────

REL_SPEAKER_PARTICIPATED_IN = """
MATCH (s:Speaker {name: $speaker_name, project_id: $project_id})
MATCH (m:Meeting {meeting_id: $meeting_id})
MERGE (s)-[r:PARTICIPATED_IN]->(m)
SET r.speaking_time_ratio = $speaking_time_ratio
"""

REL_TOPIC_DISCUSSED_IN = """
MATCH (t:Topic {name: $topic_name, project_id: $project_id})
MATCH (m:Meeting {meeting_id: $meeting_id})
MERGE (t)-[:DISCUSSED_IN]->(m)
"""

REL_ENTITY_MENTIONED_IN = """
MATCH (e:Entity {name: $entity_name, project_id: $project_id})
MATCH (m:Meeting {meeting_id: $meeting_id})
MERGE (e)-[:MENTIONED_IN]->(m)
"""

REL_MEETING_FOLLOWS = """
MATCH (curr:Meeting {meeting_id: $meeting_id})
MATCH (prev:Meeting {meeting_id: $previous_meeting_id})
MERGE (curr)-[:FOLLOWS]->(prev)
"""

# ── 의미 관계 ────────────────────────────────────────────────────────────────

REL_SPEAKER_MENTIONED_TOPIC = """
MATCH (s:Speaker {name: $speaker_name, project_id: $project_id})
MATCH (t:Topic {name: $topic_name, project_id: $project_id})
MERGE (s)-[:MENTIONED]->(t)
"""

REL_SPEAKER_OWNS_ACTION = """
MATCH (s:Speaker {name: $speaker_name, project_id: $project_id})
MATCH (a:ActionItem {description: $action_description, meeting_id: $meeting_id})
MERGE (s)-[:OWNS]->(a)
"""

REL_TOPIC_RELATED_TO = """
MATCH (t1:Topic {name: $topic1, project_id: $project_id})
MATCH (t2:Topic {name: $topic2, project_id: $project_id})
MERGE (t1)-[:RELATED_TO]-(t2)
"""

REL_DECISION_ABOUT_TOPIC = """
MATCH (d:Decision {description: $decision_description, meeting_id: $meeting_id})
MATCH (t:Topic {name: $topic_name, project_id: $project_id})
MERGE (d)-[:ABOUT]->(t)
"""

REL_ENTITY_ASSOCIATED_WITH_TOPIC = """
MATCH (e:Entity {name: $entity_name, project_id: $project_id})
MATCH (t:Topic {name: $topic_name, project_id: $project_id})
MERGE (e)-[:ASSOCIATED_WITH]->(t)
"""

# ── Agent A: 주제 전문가 ──────────────────────────────────────────────────────
#
# meeting_id가 주어지면 해당 회차의 주제만, 없으면 project_id 전체의 주제를 반환.

AGENT_A_TOPICS_BY_MEETING = """
MATCH (t:Topic)-[:DISCUSSED_IN]->(m:Meeting {meeting_id: $meeting_id})
OPTIONAL MATCH (t)-[:RELATED_TO]-(t2:Topic)
OPTIONAL MATCH (s:Speaker)-[:MENTIONED]->(t)
WHERE s.project_id = t.project_id
RETURN
  t.name AS topic,
  t.category AS category,
  t.summary AS summary,
  collect(DISTINCT t2.name) AS related_topics,
  collect(DISTINCT s.name) AS mentioned_by
ORDER BY size(collect(DISTINCT s.name)) DESC
"""

AGENT_A_TOPICS_BY_PROJECT = """
MATCH (t:Topic {project_id: $project_id})
OPTIONAL MATCH (t)-[:RELATED_TO]-(t2:Topic {project_id: $project_id})
OPTIONAL MATCH (s:Speaker {project_id: $project_id})-[:MENTIONED]->(t)
OPTIONAL MATCH (t)-[:DISCUSSED_IN]->(m:Meeting)
RETURN
  t.name AS topic,
  t.category AS category,
  t.summary AS summary,
  collect(DISTINCT t2.name) AS related_topics,
  collect(DISTINCT s.name) AS mentioned_by,
  collect(DISTINCT m.meeting_id) AS discussed_in
ORDER BY size(collect(DISTINCT m.meeting_id)) DESC
"""

# ── Agent B: 실행 전문가 ──────────────────────────────────────────────────────

AGENT_B_ACTIONS_BY_MEETING = """
MATCH (a:ActionItem {meeting_id: $meeting_id})
OPTIONAL MATCH (s:Speaker)-[:OWNS]->(a)
RETURN
  a.description AS action,
  s.name AS owner,
  a.deadline AS deadline,
  a.status AS status,
  a.meeting_id AS meeting_id
ORDER BY a.deadline ASC
"""

AGENT_B_ACTIONS_BY_PROJECT = """
MATCH (a:ActionItem {project_id: $project_id})
OPTIONAL MATCH (s:Speaker {project_id: $project_id})-[:OWNS]->(a)
RETURN
  a.description AS action,
  s.name AS owner,
  a.deadline AS deadline,
  a.status AS status,
  a.meeting_id AS meeting_id
ORDER BY a.deadline ASC
"""

AGENT_B_DECISIONS_BY_MEETING = """
MATCH (d:Decision {meeting_id: $meeting_id})
OPTIONAL MATCH (d)-[:ABOUT]->(t:Topic)
RETURN
  d.description AS decision,
  d.rationale AS rationale,
  collect(DISTINCT t.name) AS related_topics,
  d.meeting_id AS meeting_id
"""

AGENT_B_DECISIONS_BY_PROJECT = """
MATCH (d:Decision {project_id: $project_id})
OPTIONAL MATCH (d)-[:ABOUT]->(t:Topic {project_id: $project_id})
RETURN
  d.description AS decision,
  d.rationale AS rationale,
  collect(DISTINCT t.name) AS related_topics,
  d.meeting_id AS meeting_id
"""

# ── Agent C: 맥락 전문가 ──────────────────────────────────────────────────────

AGENT_C_SPEAKERS_BY_MEETING = """
MATCH (s:Speaker)-[r:PARTICIPATED_IN]->(m:Meeting {meeting_id: $meeting_id})
OPTIONAL MATCH (s)-[:MENTIONED]->(t:Topic)-[:DISCUSSED_IN]->(m)
RETURN
  s.name AS speaker,
  s.role AS role,
  r.speaking_time_ratio AS speaking_time_ratio,
  collect(DISTINCT t.name) AS topics_mentioned
ORDER BY r.speaking_time_ratio DESC
"""

AGENT_C_SPEAKERS_BY_PROJECT = """
MATCH (s:Speaker {project_id: $project_id})
OPTIONAL MATCH (s)-[r:PARTICIPATED_IN]->(m:Meeting)
OPTIONAL MATCH (s)-[:MENTIONED]->(t:Topic {project_id: $project_id})
WITH s, collect(DISTINCT m.meeting_id) AS meetings, avg(r.speaking_time_ratio) AS avg_ratio, collect(DISTINCT t.name) AS topics
RETURN
  s.name AS speaker,
  s.role AS role,
  avg_ratio AS speaking_time_ratio,
  topics AS topics_mentioned,
  meetings AS participated_meetings
ORDER BY avg_ratio DESC
"""

AGENT_C_ENTITIES_BY_MEETING = """
MATCH (e:Entity)-[:MENTIONED_IN]->(m:Meeting {meeting_id: $meeting_id})
OPTIONAL MATCH (e)-[:ASSOCIATED_WITH]->(t:Topic)
RETURN
  e.name AS entity,
  e.type AS type,
  collect(DISTINCT t.name) AS associated_topics
"""

AGENT_C_ENTITIES_BY_PROJECT = """
MATCH (e:Entity {project_id: $project_id})
OPTIONAL MATCH (e)-[:ASSOCIATED_WITH]->(t:Topic {project_id: $project_id})
RETURN
  e.name AS entity,
  e.type AS type,
  collect(DISTINCT t.name) AS associated_topics
"""

# ── 통계 & 목록 ───────────────────────────────────────────────────────────────

GRAPH_STATS = """
MATCH (m:Meeting {meeting_id: $meeting_id})
OPTIONAL MATCH (n)-[]->(m)
WITH m, labels(n)[0] AS label, count(n) AS cnt
RETURN label, cnt AS count
ORDER BY count DESC
"""

ALL_MEETINGS = """
MATCH (m:Meeting)
OPTIONAL MATCH (s:Speaker)-[:PARTICIPATED_IN]->(m)
RETURN
  m.meeting_id AS meeting_id,
  m.title AS title,
  m.date AS date,
  m.project_id AS project_id,
  collect(DISTINCT s.name) AS participants
ORDER BY m.date DESC, m.meeting_id DESC
"""

# ── 추출 컨텍스트 (이전 회차 주제/엔티티 이름 조회) ───────────────────────────

PREVIOUS_TOPICS_BY_PROJECT = """
MATCH (t:Topic {project_id: $project_id})
RETURN DISTINCT t.name AS name
ORDER BY name
"""

PREVIOUS_ENTITIES_BY_PROJECT = """
MATCH (e:Entity {project_id: $project_id})
RETURN DISTINCT e.name AS name, e.type AS type
ORDER BY name
"""

PREVIOUS_SPEAKERS_BY_PROJECT = """
MATCH (s:Speaker {project_id: $project_id})
RETURN DISTINCT s.name AS name, s.role AS role
ORDER BY name
"""

# ── 관리 ─────────────────────────────────────────────────────────────────────

DELETE_MEETING = """
MATCH (m:Meeting {meeting_id: $meeting_id})
OPTIONAL MATCH (a:ActionItem {meeting_id: $meeting_id})
OPTIONAL MATCH (d:Decision {meeting_id: $meeting_id})
DETACH DELETE m, a, d
"""

DELETE_PROJECT = """
MATCH (n {project_id: $project_id})
DETACH DELETE n
"""

DELETE_ALL = """
MATCH (n) DETACH DELETE n
"""
