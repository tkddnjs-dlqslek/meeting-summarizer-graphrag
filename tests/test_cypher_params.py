"""graph.cypher_queries와 api.graph_builder의 파라미터 정합성 검증.

목적
----
Cypher 쿼리 문자열의 `$param` 플레이스홀더가 graph_builder.py에서 execute_write
호출 시 실제로 넘기는 키와 1:1 매칭되는지 static 분석으로 확인한다. 이
테스트는 Neo4j나 Claude API에 접근하지 않으므로 CI에서 시크릿 없이 통과한다.

놓치는 것
---------
- 실제 쿼리 의미 (MATCH가 정확한지, 타입이 맞는지)
- 런타임에 None이 들어가는 경우 Cypher가 허용하는지
이건 통합 테스트 (run_ami_text.py, run_4week_test.py 등)에서 검증된다.
여기선 "키 이름 오타·빠진 파라미터"만 잡는다.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from graph import cypher_queries as Q

# ── Cypher 쿼리에서 $param 추출 ─────────────────────────────────────

PARAM_RE = re.compile(r"\$([a-zA-Z_][a-zA-Z0-9_]*)")


def extract_params(cypher: str) -> set[str]:
    return set(PARAM_RE.findall(cypher))


# ── 1. 모든 WRITE 쿼리가 어떤 파라미터를 요구하는지 먼저 매핑 ──────

WRITE_QUERIES = {
    "MERGE_MEETING":                {"meeting_id", "title", "date", "project_id"},
    "MERGE_SPEAKER":                {"name", "project_id", "role"},
    "MERGE_TOPIC":                  {"name", "project_id", "category", "summary"},
    "MERGE_ENTITY":                 {"name", "project_id", "type"},
    "MERGE_ACTION_ITEM":            {"description", "meeting_id", "project_id", "owner", "deadline", "status"},
    "MERGE_DECISION":               {"description", "meeting_id", "project_id", "rationale"},
    "REL_SPEAKER_PARTICIPATED_IN":  {"speaker_name", "project_id", "meeting_id", "speaking_time_ratio"},
    "REL_TOPIC_DISCUSSED_IN":       {"topic_name", "project_id", "meeting_id"},
    "REL_ENTITY_MENTIONED_IN":      {"entity_name", "project_id", "meeting_id"},
    "REL_MEETING_FOLLOWS":          {"meeting_id", "previous_meeting_id"},
    "REL_SPEAKER_MENTIONED_TOPIC":  {"speaker_name", "project_id", "topic_name"},
    "REL_SPEAKER_OWNS_ACTION":      {"speaker_name", "project_id", "action_description", "meeting_id"},
    "REL_TOPIC_RELATED_TO":         {"topic1", "topic2", "project_id"},
    "REL_DECISION_ABOUT_TOPIC":     {"decision_description", "topic_name", "meeting_id", "project_id"},
    "REL_ENTITY_ASSOCIATED_WITH_TOPIC": {"entity_name", "topic_name", "project_id"},
}


@pytest.mark.parametrize("query_name,expected_params", WRITE_QUERIES.items())
def test_write_query_has_exact_parameters(query_name, expected_params):
    """각 WRITE 쿼리가 기대한 파라미터만 정확히 가지는지."""
    cypher = getattr(Q, query_name)
    actual = extract_params(cypher)
    assert actual == expected_params, (
        f"{query_name}: expected {expected_params}, got {actual}"
    )


# ── 2. Agent 쿼리 파라미터 ───────────────────────────────────────

AGENT_QUERIES = {
    "AGENT_A_TOPICS_BY_MEETING":  {"meeting_id"},
    "AGENT_A_TOPICS_BY_PROJECT":  {"project_id"},
    "AGENT_B_ACTIONS_BY_MEETING": {"meeting_id"},
    "AGENT_B_ACTIONS_BY_PROJECT": {"project_id"},
    "AGENT_B_DECISIONS_BY_MEETING": {"meeting_id"},
    "AGENT_B_DECISIONS_BY_PROJECT": {"project_id"},
    "AGENT_C_SPEAKERS_BY_MEETING": {"meeting_id"},
    "AGENT_C_SPEAKERS_BY_PROJECT": {"project_id"},
    "AGENT_C_ENTITIES_BY_MEETING": {"meeting_id"},
    "AGENT_C_ENTITIES_BY_PROJECT": {"project_id"},
}


@pytest.mark.parametrize("query_name,expected_params", AGENT_QUERIES.items())
def test_agent_query_has_exact_parameters(query_name, expected_params):
    cypher = getattr(Q, query_name)
    actual = extract_params(cypher)
    assert actual == expected_params, (
        f"{query_name}: expected {expected_params}, got {actual}"
    )


# ── 3. 관리 쿼리 ────────────────────────────────────────────────

MGMT_QUERIES = {
    "GRAPH_STATS":                 {"meeting_id"},
    "ALL_MEETINGS":                set(),
    "PREVIOUS_TOPICS_BY_PROJECT":  {"project_id"},
    "PREVIOUS_ENTITIES_BY_PROJECT": {"project_id"},
    "PREVIOUS_SPEAKERS_BY_PROJECT": {"project_id"},
    "DELETE_MEETING":              {"meeting_id"},
    "DELETE_PROJECT":               {"project_id"},
    "DELETE_ALL":                  set(),
}


@pytest.mark.parametrize("query_name,expected_params", MGMT_QUERIES.items())
def test_mgmt_query_parameters(query_name, expected_params):
    cypher = getattr(Q, query_name)
    actual = extract_params(cypher)
    assert actual == expected_params, (
        f"{query_name}: expected {expected_params}, got {actual}"
    )


# ── 4. 모든 쿼리가 파이썬 문자열로 존재하는지 smoke test ────────

def test_all_declared_queries_are_strings():
    """graph_builder와 agents가 참조하는 모든 Q.XXX가 실존하는지."""
    used = (
        list(WRITE_QUERIES.keys())
        + list(AGENT_QUERIES.keys())
        + list(MGMT_QUERIES.keys())
    )
    for name in used:
        val = getattr(Q, name, None)
        assert isinstance(val, str), f"Q.{name} not a string"
        assert val.strip(), f"Q.{name} is empty"


# ── 5. graph_builder가 호출하는 쿼리 스모크 ─────────────────────

def test_graph_builder_imports_cleanly():
    """graph_builder.py가 import 시점에 오류 없는지."""
    from api import graph_builder  # noqa: F401
    assert callable(graph_builder.build_graph)
