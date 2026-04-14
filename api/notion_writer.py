"""
Notion database 연동 (Obsidian writer와 병행).

동작
----
NOTION_ENABLED=true일 때만 활성화. 첫 호출 시 NOTION_PARENT_PAGE_ID 아래에
database를 자동 생성하고 database ID를 ./notion_db_id.json에 캐시한다. 이후
모든 회의는 이 database에 페이지로 누적된다.

graph_data를 Notion block 구조로 매핑하여 가독성 좋은 페이지를 생성한다:
  - 상단 Callout: AI 요약
  - Heading 2 "참석자" + bulleted list (발언 비중 포함)
  - Heading 2 "핵심 주제" + Toggle blocks (내부 summary)
  - Heading 2 "결정 사항" + Callout + Quote(근거)
  - Heading 2 "액션 아이템" + To-do blocks
  - Heading 2 "주요 엔티티" + bulleted list

에러 처리
--------
모든 Notion API 예외를 catch해서 warning 로그 + None 반환. 파이프라인의
다른 단계(Obsidian, Neo4j)에 영향을 주지 않는다.

환경변수
--------
NOTION_ENABLED       : "true"일 때만 동작
NOTION_TOKEN         : Integration secret (ntn_ 또는 secret_)
NOTION_PARENT_PAGE_ID: database가 만들어질 부모 페이지 (Integration 연결 필요)
NOTION_DATABASE_ID   : (선택) 기존 database ID를 직접 지정
"""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path
from typing import Any, Optional

_client = None
_db_id_cache: Optional[str] = None
CACHE_FILE = Path("notion_db_id.json")

TEXT_LIMIT = 1900  # Notion rich_text 한 블록 2000자 제한 여유


# ── 활성화 체크 + 클라이언트 ──────────────────────────────────────────

def is_enabled() -> bool:
    return os.getenv("NOTION_ENABLED", "").lower() in ("1", "true", "yes")


def _get_client():
    """lazy init. 환경변수가 없거나 미활성이면 None."""
    global _client
    if _client is not None:
        return _client
    if not is_enabled():
        return None
    token = os.getenv("NOTION_TOKEN")
    if not token:
        return None
    try:
        from notion_client import Client
        _client = Client(auth=token)
        return _client
    except Exception:
        traceback.print_exc()
        return None


# ── database 자동 생성 / 캐시 ─────────────────────────────────────────

def _load_cached_db_id() -> Optional[str]:
    """.env의 NOTION_DATABASE_ID를 우선. 없으면 로컬 JSON 캐시."""
    env_id = os.getenv("NOTION_DATABASE_ID", "").strip()
    if env_id:
        return env_id
    if CACHE_FILE.exists():
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            return data.get("database_id")
        except Exception:
            return None
    return None


def _save_cached_db_id(db_id: str) -> None:
    CACHE_FILE.write_text(
        json.dumps({"database_id": db_id}, indent=2),
        encoding="utf-8",
    )


def _create_database(client, parent_page_id: str) -> str:
    """parent_page_id 아래에 Meeting Summarizer database를 생성.

    Notion API 제약:
      - self-referencing relation은 database 생성 후 추가 update 단계 필요.
      - 초기 버전은 "Previous Meeting ID"를 rich_text로만 기록한다 (v2에서
        relation 승격).
    """
    db = client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "Meeting Summarizer — GraphRAG"}}],
        properties={
            "Title": {"title": {}},
            "Date": {"date": {}},
            "Project": {"rich_text": {}},
            "Participants": {"multi_select": {}},
            "Categories": {"multi_select": {}},
            "Meeting ID": {"rich_text": {}},
            "Previous Meeting ID": {"rich_text": {}},
        },
    )
    return db["id"]


def _get_or_create_database(client) -> Optional[str]:
    global _db_id_cache
    if _db_id_cache:
        return _db_id_cache

    cached = _load_cached_db_id()
    if cached:
        _db_id_cache = cached
        return cached

    parent_page_id = os.getenv("NOTION_PARENT_PAGE_ID", "").strip()
    if not parent_page_id:
        print("[notion] NOTION_PARENT_PAGE_ID is not set — cannot auto-create database")
        return None

    try:
        db_id = _create_database(client, parent_page_id)
        _save_cached_db_id(db_id)
        _db_id_cache = db_id
        print(f"[notion] created database: {db_id}")
        return db_id
    except Exception as e:
        print(f"[notion] database creation failed: {e}")
        print("[notion] hint: did you connect the integration to the parent page?")
        traceback.print_exc()
        return None


# ── rich_text helpers ─────────────────────────────────────────────────

def _rich(text: str) -> list[dict]:
    """문자열 하나를 Notion rich_text 배열로."""
    if not text:
        return []
    return [{"type": "text", "text": {"content": text[:TEXT_LIMIT]}}]


def _split_long_text(text: str, limit: int = TEXT_LIMIT) -> list[str]:
    """긴 문자열을 여러 조각으로. 블록 단위로 나눠 Notion 제한 우회."""
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while remaining:
        chunk = remaining[:limit]
        # 문장 경계에서 끊어주면 가독성 ↑
        if len(remaining) > limit:
            last_period = chunk.rfind(". ")
            if last_period > limit // 2:
                chunk = remaining[: last_period + 1]
        chunks.append(chunk)
        remaining = remaining[len(chunk):]
    return chunks


# ── 블록 빌더 ────────────────────────────────────────────────────────

def _heading_2(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _rich(text)},
    }


def _paragraph(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich(text)},
    }


def _bulleted(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich(text)},
    }


def _todo(text: str, checked: bool = False) -> dict:
    return {
        "object": "block",
        "type": "to_do",
        "to_do": {"rich_text": _rich(text), "checked": checked},
    }


def _callout(text: str, emoji: str = "💡", color: str = "default") -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _rich(text),
            "icon": {"type": "emoji", "emoji": emoji},
            "color": color,
        },
    }


def _quote(text: str) -> dict:
    return {
        "object": "block",
        "type": "quote",
        "quote": {"rich_text": _rich(text)},
    }


def _toggle(title: str, children: list[dict]) -> dict:
    return {
        "object": "block",
        "type": "toggle",
        "toggle": {"rich_text": _rich(title), "children": children},
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


# ── graph_data → blocks ──────────────────────────────────────────────

def _build_blocks(graph_data: dict) -> list[dict]:
    blocks: list[dict] = []

    # 상단 Callout: AI 요약
    summary = (graph_data.get("summary") or "").strip()
    if summary:
        for i, chunk in enumerate(_split_long_text(summary)):
            if i == 0:
                blocks.append(_callout(chunk, emoji="💬", color="blue_background"))
            else:
                blocks.append(_paragraph(chunk))

    blocks.append(_divider())

    # 참석자
    speakers = graph_data.get("speakers") or []
    if speakers:
        blocks.append(_heading_2("👥 참석자"))
        for s in speakers:
            name = s.get("name", "")
            role = s.get("role", "")
            ratio = s.get("speaking_time_ratio") or 0
            line = f"{name}"
            if role:
                line += f" ({role})"
            if ratio:
                line += f" — 발언 비중 {ratio:.0%}"
            blocks.append(_bulleted(line))

    # 핵심 주제
    topics = graph_data.get("topics") or []
    if topics:
        blocks.append(_heading_2("🎯 핵심 주제"))
        for t in topics:
            name = t.get("name", "")
            category = t.get("category", "")
            title = f"{name}"
            if category:
                title += f"  [{category}]"
            children: list[dict] = []
            t_summary = (t.get("summary") or "").strip()
            if t_summary:
                for chunk in _split_long_text(t_summary):
                    children.append(_paragraph(chunk))
            related = t.get("related_topics") or []
            if related:
                children.append(_paragraph("관련: " + " / ".join(related)))
            if not children:
                children.append(_paragraph("(상세 없음)"))
            blocks.append(_toggle(title, children))

    # 결정 사항
    decisions = graph_data.get("decisions") or []
    if decisions:
        blocks.append(_heading_2("✅ 결정 사항"))
        for d in decisions:
            desc = d.get("description", "")
            blocks.append(_callout(desc, emoji="🟢", color="green_background"))
            rationale = (d.get("rationale") or "").strip()
            if rationale:
                for chunk in _split_long_text(rationale):
                    blocks.append(_quote(f"근거: {chunk}"))
            related = d.get("related_topics") or []
            if related:
                blocks.append(_paragraph("관련 주제: " + ", ".join(related)))

    # 액션 아이템
    actions = graph_data.get("action_items") or []
    if actions:
        blocks.append(_heading_2("📌 액션 아이템"))
        for a in actions:
            desc = a.get("description", "")
            owner = a.get("owner", "")
            deadline = a.get("deadline")
            parts = []
            if owner:
                parts.append(f"[{owner}]")
            parts.append(desc)
            if deadline:
                parts.append(f"(due: {deadline})")
            blocks.append(_todo(" ".join(parts)))

    # 주요 엔티티
    entities = graph_data.get("entities") or []
    if entities:
        blocks.append(_heading_2("🏷️ 주요 엔티티"))
        for e in entities:
            etype = e.get("type", "")
            ename = e.get("name", "")
            line = f"{ename}"
            if etype:
                line = f"[{etype}] {ename}"
            blocks.append(_bulleted(line))

    return blocks


# ── properties 빌더 (실존 property만 채움) ──────────────────────────

def _build_properties(
    graph_data: dict,
    existing_property_types: dict[str, str],
) -> dict:
    """database에 실제로 있는 property만 채운다. 없는 건 skip.

    existing_property_types: property 이름 → type 매핑 (예: {"Title": "title", "Date": "date"})
    """
    props: dict[str, Any] = {}

    # Title
    if existing_property_types.get("Title") == "title":
        title = graph_data.get("title") or f"Meeting {graph_data.get('meeting_id', '')[:8]}"
        props["Title"] = {"title": _rich(title)}

    # Date
    if existing_property_types.get("Date") == "date":
        date_str = (graph_data.get("date") or "").strip()
        if date_str:
            props["Date"] = {"date": {"start": date_str}}

    # Project
    if existing_property_types.get("Project") == "rich_text":
        project_id = graph_data.get("project_id") or "default"
        props["Project"] = {"rich_text": _rich(project_id)}

    # Participants (multi_select)
    if existing_property_types.get("Participants") == "multi_select":
        speakers = graph_data.get("speakers") or []
        names = list({s.get("name", "") for s in speakers if s.get("name")})
        props["Participants"] = {
            "multi_select": [{"name": n[:100]} for n in names],
        }

    # Categories (multi_select)
    if existing_property_types.get("Categories") == "multi_select":
        topics = graph_data.get("topics") or []
        cats = list({t.get("category", "") for t in topics if t.get("category")})
        props["Categories"] = {
            "multi_select": [{"name": c[:100]} for c in cats],
        }

    # Meeting ID
    if existing_property_types.get("Meeting ID") == "rich_text":
        mid = graph_data.get("meeting_id", "")
        props["Meeting ID"] = {"rich_text": _rich(mid)}

    # Previous Meeting ID (v1은 rich_text로만)
    if existing_property_types.get("Previous Meeting ID") == "rich_text":
        prev_mid = graph_data.get("previous_meeting_id", "")
        if prev_mid:
            props["Previous Meeting ID"] = {"rich_text": _rich(prev_mid)}

    return props


def _fetch_property_types(client, database_id: str) -> dict[str, str]:
    """database를 조회해서 property 이름 → type 매핑을 반환."""
    try:
        db = client.databases.retrieve(database_id=database_id)
        return {name: meta.get("type", "") for name, meta in db.get("properties", {}).items()}
    except Exception as e:
        print(f"[notion] failed to retrieve database schema: {e}")
        return {}


# ── 엔트리 포인트 ────────────────────────────────────────────────────

def write_meeting_note_to_notion(graph_data: dict) -> Optional[str]:
    """graph_data를 Notion database에 새 페이지로 저장.

    Returns
    -------
    Optional[str]
        생성된 페이지 URL. 비활성·실패·부족한 설정 시 None.
    """
    if not is_enabled():
        return None

    client = _get_client()
    if client is None:
        return None

    database_id = _get_or_create_database(client)
    if database_id is None:
        return None

    try:
        prop_types = _fetch_property_types(client, database_id)
        if not prop_types:
            return None

        properties = _build_properties(graph_data, prop_types)
        blocks = _build_blocks(graph_data)

        page = client.pages.create(
            parent={"database_id": database_id},
            properties=properties,
            children=blocks,
        )
        url = page.get("url")
        return url
    except Exception as e:
        print(f"[notion] page creation failed: {e}")
        traceback.print_exc()
        return None


def reset_cache() -> None:
    """테스트용 — 모듈 레벨 캐시 초기화."""
    global _client, _db_id_cache
    _client = None
    _db_id_cache = None
