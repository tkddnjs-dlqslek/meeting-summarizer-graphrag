"""api.obsidian_writer 단위 테스트.

write_meeting_note()가 다양한 graph_data 입력에 대해 기대한 섹션과
프론트매터, 위키링크를 정확히 생성하는지 검증한다. Neo4j나 Claude API
호출은 없다 (파일 시스템만 사용).
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from api import obsidian_writer


@pytest.fixture
def tmp_vault(tmp_path, monkeypatch):
    """VAULT_PATH를 tmp_path로 교체해서 테스트 간 격리."""
    monkeypatch.setattr(obsidian_writer, "VAULT_PATH", tmp_path)
    return tmp_path


@pytest.fixture
def full_graph_data():
    """4명·주제·결정·액션·엔티티가 모두 있는 완전한 샘플."""
    return {
        "meeting_id": "test-001",
        "project_id": "unit_test",
        "title": "Test Meeting",
        "date": "2026-04-12",
        "summary": "테스트 회의 요약",
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
            {
                "description": "디자인 QA 세션",
                "owner": "Carol",
                "deadline": None,
                "status": "pending",
            },
        ],
        "entities": [
            {"name": "Jenkins", "type": "tool"},
            {"name": "Figma",   "type": "tool"},
        ],
        "node_count": 12,
    }


# ── 1. 기본 파일 생성 ──────────────────────────────────────────────

def test_creates_file_in_project_subfolder(tmp_vault, full_graph_data):
    path = obsidian_writer.write_meeting_note(full_graph_data)
    p = Path(path)
    assert p.exists()
    # 프로젝트별 서브폴더
    assert p.parent.name == "unit_test"
    assert p.parent.parent == tmp_vault


def test_filename_contains_date_and_title(tmp_vault, full_graph_data):
    path = obsidian_writer.write_meeting_note(full_graph_data)
    assert "2026-04-12" in Path(path).name
    assert "Test Meeting" in Path(path).name
    assert Path(path).suffix == ".md"


# ── 2. frontmatter ─────────────────────────────────────────────────

def test_frontmatter_contains_core_fields(tmp_vault, full_graph_data):
    path = obsidian_writer.write_meeting_note(full_graph_data)
    content = Path(path).read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "meeting_id: test-001" in content
    assert "project_id: unit_test" in content
    assert "date: 2026-04-12" in content
    assert 'title: "Test Meeting"' in content


def test_frontmatter_includes_all_participants(tmp_vault, full_graph_data):
    path = obsidian_writer.write_meeting_note(full_graph_data)
    content = Path(path).read_text(encoding="utf-8")
    # participants: [Alice, Bob, Carol, Dave]
    assert "participants:" in content
    for name in ["Alice", "Bob", "Carol", "Dave"]:
        assert name in content


# ── 3. 본문 섹션 ──────────────────────────────────────────────────

def test_has_all_major_sections(tmp_vault, full_graph_data):
    path = obsidian_writer.write_meeting_note(full_graph_data)
    content = Path(path).read_text(encoding="utf-8")
    for section in ["## 참석자", "## 핵심 주제", "## 결정 사항", "## 액션 아이템", "## 주요 엔티티", "## AI 요약"]:
        assert section in content, f"missing section: {section}"


def test_action_items_are_checkboxes(tmp_vault, full_graph_data):
    path = obsidian_writer.write_meeting_note(full_graph_data)
    content = Path(path).read_text(encoding="utf-8")
    assert "- [ ]" in content
    assert "통합 테스트 자동화" in content
    assert "2026-04-25" in content  # deadline
    assert "**Bob**" in content  # owner bold


def test_action_without_deadline_still_rendered(tmp_vault, full_graph_data):
    path = obsidian_writer.write_meeting_note(full_graph_data)
    content = Path(path).read_text(encoding="utf-8")
    assert "디자인 QA 세션" in content


def test_decision_rationale_rendered(tmp_vault, full_graph_data):
    path = obsidian_writer.write_meeting_note(full_graph_data)
    content = Path(path).read_text(encoding="utf-8")
    assert "릴리스를 2주 연기한다" in content
    assert "QA 커버리지 부족" in content


# ── 4. 위키링크 (관련 주제) ───────────────────────────────────────

def test_related_topics_render_as_wikilinks(tmp_vault, full_graph_data):
    path = obsidian_writer.write_meeting_note(full_graph_data)
    content = Path(path).read_text(encoding="utf-8")
    # Sprint Planning의 related: Backlog Grooming → [[Backlog Grooming]]
    assert "[[Backlog Grooming]]" in content


def test_decision_related_topics_wikilinks(tmp_vault, full_graph_data):
    path = obsidian_writer.write_meeting_note(full_graph_data)
    content = Path(path).read_text(encoding="utf-8")
    # 결정의 related_topics도 [[]]로
    assert "[[Release Timeline]]" in content


# ── 5. edge cases ────────────────────────────────────────────────

def test_missing_summary_falls_back(tmp_vault, full_graph_data):
    full_graph_data["summary"] = ""
    path = obsidian_writer.write_meeting_note(full_graph_data)
    content = Path(path).read_text(encoding="utf-8")
    assert "(요약 없음)" in content


def test_missing_decisions_shows_none(tmp_vault, full_graph_data):
    full_graph_data["decisions"] = []
    path = obsidian_writer.write_meeting_note(full_graph_data)
    content = Path(path).read_text(encoding="utf-8")
    assert "(없음)" in content


def test_missing_project_id_uses_default_folder(tmp_vault, full_graph_data):
    full_graph_data.pop("project_id")
    path = obsidian_writer.write_meeting_note(full_graph_data)
    assert Path(path).parent.name == "default"


def test_unsafe_title_is_sanitized(tmp_vault, full_graph_data):
    full_graph_data["title"] = "Team/Meeting:Q2?"
    path = obsidian_writer.write_meeting_note(full_graph_data)
    # 파일명에서 /, :, ? 가 제거됐는지
    fname = Path(path).name
    assert "/" not in fname
    assert ":" not in fname
    assert "?" not in fname


def test_minimal_graph_data(tmp_vault):
    """필수 필드만 있어도 에러 없이 생성."""
    minimal = {
        "meeting_id": "m1",
        "project_id": "p1",
    }
    path = obsidian_writer.write_meeting_note(minimal)
    assert Path(path).exists()
