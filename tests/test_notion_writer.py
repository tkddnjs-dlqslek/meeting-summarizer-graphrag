"""api.notion_writer 단위 테스트.

전략
----
notion_client.Client를 MagicMock으로 교체해서 실 API 호출 없이 테스트.
CI에서 NOTION_ENABLED=false일 때는 write_meeting_note_to_notion이 조용히
None을 반환하는 경로만 타므로 빠르게 통과한다. 로컬에서는 monkeypatch로
Client를 주입하고 pages.create / databases.retrieve 호출 인자를 검증한다.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from api import notion_writer


# ── fixtures ────────────────────────────────────────────────────────

@pytest.fixture
def enable_notion(monkeypatch):
    """NOTION_ENABLED=true, 더미 token/parent를 env에 주입."""
    monkeypatch.setenv("NOTION_ENABLED", "true")
    monkeypatch.setenv("NOTION_TOKEN", "ntn_test_dummy_token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "test_parent_page_id")
    monkeypatch.delenv("NOTION_DATABASE_ID", raising=False)
    notion_writer.reset_cache()
    yield
    notion_writer.reset_cache()


@pytest.fixture
def disable_notion(monkeypatch):
    monkeypatch.setenv("NOTION_ENABLED", "false")
    notion_writer.reset_cache()
    yield
    notion_writer.reset_cache()


@pytest.fixture
def mock_client(monkeypatch, tmp_path):
    """_get_client를 MagicMock으로 교체. CACHE_FILE은 tmp_path로 격리."""
    client = MagicMock()
    # databases.retrieve → property types
    client.databases.retrieve.return_value = {
        "properties": {
            "Title": {"type": "title"},
            "Date": {"type": "date"},
            "Project": {"type": "rich_text"},
            "Participants": {"type": "multi_select"},
            "Categories": {"type": "multi_select"},
            "Meeting ID": {"type": "rich_text"},
            "Previous Meeting ID": {"type": "rich_text"},
        }
    }
    # databases.create → 생성된 database dict
    client.databases.create.return_value = {"id": "new_database_id_12345"}
    # pages.create → 생성된 page dict
    client.pages.create.return_value = {
        "id": "page_id_xyz",
        "url": "https://www.notion.so/test-meeting-xyz",
    }

    monkeypatch.setattr(notion_writer, "_get_client", lambda: client)
    monkeypatch.setattr(notion_writer, "CACHE_FILE", tmp_path / "notion_db_id.json")
    notion_writer.reset_cache()
    yield client
    notion_writer.reset_cache()


@pytest.fixture
def full_graph_data():
    return {
        "meeting_id": "test-notion-001",
        "project_id": "unit_test_project",
        "title": "Test Notion Meeting",
        "date": "2026-04-13",
        "summary": "테스트 회의 요약 — Notion 연동 검증용입니다.",
        "speakers": [
            {"name": "Alice", "role": "PM", "speaking_time_ratio": 0.4},
            {"name": "Bob",   "role": "Engineer", "speaking_time_ratio": 0.3},
            {"name": "Carol", "role": "Designer", "speaking_time_ratio": 0.2},
            {"name": "Dave",  "role": "QA", "speaking_time_ratio": 0.1},
        ],
        "topics": [
            {
                "name": "Sprint Planning",
                "category": "process",
                "summary": "다음 스프린트 범위 확정",
                "related_topics": ["Backlog Grooming"],
            },
            {
                "name": "Release Timeline",
                "category": "business",
                "summary": "Q2 릴리스 일정",
                "related_topics": [],
            },
        ],
        "decisions": [
            {
                "description": "릴리스를 2주 연기한다",
                "rationale": "QA 커버리지 부족",
                "related_topics": ["Release Timeline"],
            },
        ],
        "action_items": [
            {
                "description": "통합 테스트 자동화",
                "owner": "Bob",
                "deadline": "2026-04-25",
                "status": "pending",
            },
        ],
        "entities": [
            {"name": "Jenkins", "type": "tool"},
            {"name": "Figma",   "type": "tool"},
        ],
    }


# ── 1. 비활성 경로 ───────────────────────────────────────────────

def test_disabled_returns_none(disable_notion, full_graph_data):
    assert notion_writer.write_meeting_note_to_notion(full_graph_data) is None


def test_missing_token_returns_none(monkeypatch, full_graph_data):
    monkeypatch.setenv("NOTION_ENABLED", "true")
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    notion_writer.reset_cache()
    assert notion_writer.write_meeting_note_to_notion(full_graph_data) is None


def test_is_enabled_helper(monkeypatch):
    monkeypatch.setenv("NOTION_ENABLED", "true")
    assert notion_writer.is_enabled() is True
    monkeypatch.setenv("NOTION_ENABLED", "false")
    assert notion_writer.is_enabled() is False
    monkeypatch.delenv("NOTION_ENABLED", raising=False)
    assert notion_writer.is_enabled() is False


# ── 2. database 자동 생성 ────────────────────────────────────────

def test_creates_database_on_first_run(enable_notion, mock_client, full_graph_data):
    url = notion_writer.write_meeting_note_to_notion(full_graph_data)
    assert url == "https://www.notion.so/test-meeting-xyz"
    mock_client.databases.create.assert_called_once()
    # parent가 올바른 page_id로 전달됐는지
    args, kwargs = mock_client.databases.create.call_args
    assert kwargs["parent"]["page_id"] == "test_parent_page_id"
    # 필수 properties 7개가 정의에 포함됐는지
    props_def = kwargs["properties"]
    for name in ["Title", "Date", "Project", "Participants", "Categories", "Meeting ID", "Previous Meeting ID"]:
        assert name in props_def


def test_reuses_cached_database_id(enable_notion, mock_client, full_graph_data, tmp_path):
    cache_file = tmp_path / "notion_db_id.json"
    cache_file.write_text(json.dumps({"database_id": "cached_db_id_999"}), encoding="utf-8")

    url = notion_writer.write_meeting_note_to_notion(full_graph_data)
    assert url is not None
    # 캐시된 ID가 있으면 databases.create는 호출되지 않아야 함
    mock_client.databases.create.assert_not_called()
    # pages.create는 호출됐고, parent.database_id가 캐시 값
    args, kwargs = mock_client.pages.create.call_args
    assert kwargs["parent"]["database_id"] == "cached_db_id_999"


def test_env_database_id_wins_over_cache(
    enable_notion, mock_client, full_graph_data, tmp_path, monkeypatch
):
    """.env의 NOTION_DATABASE_ID가 로컬 캐시보다 우선."""
    cache_file = tmp_path / "notion_db_id.json"
    cache_file.write_text(json.dumps({"database_id": "cached_id"}), encoding="utf-8")
    monkeypatch.setenv("NOTION_DATABASE_ID", "env_override_id")

    notion_writer.write_meeting_note_to_notion(full_graph_data)
    args, kwargs = mock_client.pages.create.call_args
    assert kwargs["parent"]["database_id"] == "env_override_id"


def test_missing_parent_page_returns_none(
    enable_notion, mock_client, full_graph_data, monkeypatch
):
    """NOTION_PARENT_PAGE_ID가 없으면 database 생성 불가 → None."""
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    assert notion_writer.write_meeting_note_to_notion(full_graph_data) is None


# ── 3. properties 매핑 ──────────────────────────────────────────

def test_properties_include_title_and_date(enable_notion, mock_client, full_graph_data):
    notion_writer.write_meeting_note_to_notion(full_graph_data)
    args, kwargs = mock_client.pages.create.call_args
    props = kwargs["properties"]
    assert "Title" in props
    assert props["Title"]["title"][0]["text"]["content"] == "Test Notion Meeting"
    assert "Date" in props
    assert props["Date"]["date"]["start"] == "2026-04-13"


def test_participants_mapped_to_multi_select(enable_notion, mock_client, full_graph_data):
    notion_writer.write_meeting_note_to_notion(full_graph_data)
    args, kwargs = mock_client.pages.create.call_args
    props = kwargs["properties"]
    names = {item["name"] for item in props["Participants"]["multi_select"]}
    assert names == {"Alice", "Bob", "Carol", "Dave"}


def test_categories_mapped_to_multi_select(enable_notion, mock_client, full_graph_data):
    notion_writer.write_meeting_note_to_notion(full_graph_data)
    args, kwargs = mock_client.pages.create.call_args
    props = kwargs["properties"]
    cats = {item["name"] for item in props["Categories"]["multi_select"]}
    assert cats == {"process", "business"}


def test_skips_missing_property_types(
    enable_notion, mock_client, full_graph_data
):
    """database에 없는 property는 skip."""
    # 이번엔 Categories가 없는 database
    mock_client.databases.retrieve.return_value = {
        "properties": {
            "Title": {"type": "title"},
            "Date": {"type": "date"},
            "Project": {"type": "rich_text"},
            # Participants, Categories, Meeting ID, Previous Meeting ID 없음
        }
    }
    notion_writer.write_meeting_note_to_notion(full_graph_data)
    args, kwargs = mock_client.pages.create.call_args
    props = kwargs["properties"]
    assert "Title" in props
    assert "Date" in props
    assert "Project" in props
    assert "Participants" not in props
    assert "Categories" not in props
    assert "Meeting ID" not in props


# ── 4. blocks 구조 ──────────────────────────────────────────────

def test_blocks_contain_all_major_sections(enable_notion, mock_client, full_graph_data):
    notion_writer.write_meeting_note_to_notion(full_graph_data)
    args, kwargs = mock_client.pages.create.call_args
    blocks = kwargs["children"]

    # 어떤 type들이 들어갔나
    types = [b["type"] for b in blocks]
    assert "callout" in types  # summary + decisions
    assert "heading_2" in types  # 섹션 헤더들
    assert "bulleted_list_item" in types  # 참석자 · 엔티티
    assert "toggle" in types  # 핵심 주제
    assert "to_do" in types  # 액션 아이템
    assert "quote" in types  # 결정 근거
    assert "divider" in types


def test_summary_becomes_callout(enable_notion, mock_client, full_graph_data):
    notion_writer.write_meeting_note_to_notion(full_graph_data)
    args, kwargs = mock_client.pages.create.call_args
    first_callout = next(b for b in kwargs["children"] if b["type"] == "callout")
    text = first_callout["callout"]["rich_text"][0]["text"]["content"]
    assert "테스트 회의 요약" in text


def test_topics_become_toggle_blocks(enable_notion, mock_client, full_graph_data):
    notion_writer.write_meeting_note_to_notion(full_graph_data)
    args, kwargs = mock_client.pages.create.call_args
    toggles = [b for b in kwargs["children"] if b["type"] == "toggle"]
    assert len(toggles) == 2
    titles = [t["toggle"]["rich_text"][0]["text"]["content"] for t in toggles]
    assert any("Sprint Planning" in x for x in titles)
    assert any("Release Timeline" in x for x in titles)


def test_action_items_become_todos(enable_notion, mock_client, full_graph_data):
    notion_writer.write_meeting_note_to_notion(full_graph_data)
    args, kwargs = mock_client.pages.create.call_args
    todos = [b for b in kwargs["children"] if b["type"] == "to_do"]
    assert len(todos) == 1
    todo_text = todos[0]["to_do"]["rich_text"][0]["text"]["content"]
    assert "Bob" in todo_text
    assert "통합 테스트 자동화" in todo_text
    assert "2026-04-25" in todo_text
    assert todos[0]["to_do"]["checked"] is False


def test_decision_rationale_becomes_quote(enable_notion, mock_client, full_graph_data):
    notion_writer.write_meeting_note_to_notion(full_graph_data)
    args, kwargs = mock_client.pages.create.call_args
    quotes = [b for b in kwargs["children"] if b["type"] == "quote"]
    assert len(quotes) == 1
    text = quotes[0]["quote"]["rich_text"][0]["text"]["content"]
    assert "QA 커버리지 부족" in text


# ── 5. edge cases ────────────────────────────────────────────────

def test_minimal_graph_data(enable_notion, mock_client):
    minimal = {"meeting_id": "m1", "project_id": "p1"}
    url = notion_writer.write_meeting_note_to_notion(minimal)
    assert url is not None  # 빈 데이터도 페이지는 생성됨


def test_long_summary_is_split(enable_notion, mock_client):
    """summary가 2000자 초과 → 여러 블록으로 분할."""
    long_summary = "가나다라마바사. " * 300  # ~2400자
    data = {
        "meeting_id": "m-long",
        "project_id": "p1",
        "title": "Long",
        "date": "2026-04-13",
        "summary": long_summary,
    }
    notion_writer.write_meeting_note_to_notion(data)
    args, kwargs = mock_client.pages.create.call_args
    # summary 관련 블록이 여러 개여야
    text_blocks = [
        b for b in kwargs["children"]
        if b["type"] in ("callout", "paragraph")
        and b[b["type"]]["rich_text"]
        and "가나다" in b[b["type"]]["rich_text"][0]["text"]["content"]
    ]
    assert len(text_blocks) >= 2


def test_notion_api_failure_returns_none(enable_notion, mock_client, full_graph_data):
    """pages.create가 예외 던지면 None 반환, 전파하지 않음."""
    mock_client.pages.create.side_effect = Exception("API error")
    result = notion_writer.write_meeting_note_to_notion(full_graph_data)
    assert result is None  # 에러 catch 확인


def test_database_retrieve_failure_returns_none(enable_notion, mock_client, full_graph_data):
    mock_client.databases.retrieve.side_effect = Exception("DB not accessible")
    result = notion_writer.write_meeting_note_to_notion(full_graph_data)
    assert result is None
