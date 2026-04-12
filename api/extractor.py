import os
import json
import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-sonnet-4-6"
_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client

# ── 1차 도구: 구조적 요소 추출 ────────────────────────────────────────────────

TOOLS_PASS1 = [
    {
        "name": "extract_speakers",
        "description": "회의 참석자와 역할을 추출합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "speakers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "참석자 이름"},
                            "role": {"type": "string", "description": "직책 또는 역할"},
                            "speaking_time_ratio": {"type": "number", "description": "전체 발언 비중 0~1"}
                        },
                        "required": ["name", "role"]
                    }
                }
            },
            "required": ["speakers"]
        }
    },
    {
        "name": "extract_topics",
        "description": "회의에서 논의된 주요 주제를 추출합니다. category는 technical/business/process/regulatory/hr 중 하나.",
        "input_schema": {
            "type": "object",
            "properties": {
                "topics": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "주제명 (간결하게)"},
                            "category": {"type": "string", "description": "technical/business/process/regulatory/hr"},
                            "summary": {"type": "string", "description": "주제 요약 1~2문장"},
                            "related_topics": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "관련 주제명 목록 (같은 회의 내)"
                            }
                        },
                        "required": ["name", "category", "summary"]
                    }
                }
            },
            "required": ["topics"]
        }
    },
    {
        "name": "extract_entities",
        "description": "회의에서 언급된 핵심 엔티티를 추출합니다. type은 drug/product/company/person/regulation/project/organization 중 하나.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string", "description": "drug/product/company/person/regulation/project/organization"},
                            "associated_topics": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "이 엔티티가 언급된 주제명 목록"
                            }
                        },
                        "required": ["name", "type"]
                    }
                }
            },
            "required": ["entities"]
        }
    }
]

# ── 2차 도구: 관계 및 실행 아이템 추출 ───────────────────────────────────────

def build_tools_pass2(speakers: list, topics: list) -> list:
    speaker_names = [s["name"] for s in speakers]
    topic_names = [t["name"] for t in topics]

    return [
        {
            "name": "extract_action_items",
            "description": "회의에서 도출된 액션 아이템을 추출합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "action_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string", "description": "할 일 내용"},
                                "owner": {
                                    "type": "string",
                                    "description": f"담당자. 반드시 다음 중 하나: {speaker_names}"
                                },
                                "deadline": {"type": "string", "description": "마감일 (YYYY-MM-DD 형식, 없으면 null)"},
                                "status": {"type": "string", "description": "pending/in_progress/done", "default": "pending"}
                            },
                            "required": ["description", "owner"]
                        }
                    }
                },
                "required": ["action_items"]
            }
        },
        {
            "name": "extract_decisions",
            "description": "회의에서 최종 결정된 사항을 추출합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "decisions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string", "description": "결정 내용"},
                                "rationale": {"type": "string", "description": "결정 근거 또는 배경"},
                                "related_topics": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": f"관련 주제. 반드시 다음 중에서: {topic_names}"
                                }
                            },
                            "required": ["description"]
                        }
                    }
                },
                "required": ["decisions"]
            }
        },
        {
            "name": "build_relationships",
            "description": "발화자-주제, 엔티티-주제 간 관계를 정의합니다.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "speaker_topic_links": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "speaker_name": {"type": "string"},
                                "topic_name": {"type": "string"}
                            },
                            "required": ["speaker_name", "topic_name"]
                        }
                    }
                },
                "required": ["speaker_topic_links"]
            }
        }
    ]


def _parse_tool_results(response) -> dict:
    result = {}
    for block in response.content:
        if block.type == "tool_use":
            result[block.name] = block.input
    return result


async def extract_graph_data(
    transcript: str,
    meeting_id: str,
    title: str = "",
    project_id: str = "default",
    previous_topics: list[str] | None = None,
    previous_entities: list[str] | None = None,
    previous_speakers: list[str] | None = None,
) -> dict:
    """
    transcript → 2단계 Claude tool_use → graph_data dict 반환.

    previous_* 인자가 주어지면 1차 추출 프롬프트에 "같은 프로젝트 이전 회차에서
    이미 등록된 이름들"로 주입되어, Claude가 동일한 개념을 동일 이름으로
    재사용하도록 유도한다. 이는 글로벌 MERGE가 회차 간에 실제로 병합되게
    만드는 핵심 장치이다.

    graph_data = {
        meeting_id, title, project_id,
        speakers, topics, entities,
        action_items, decisions,
        speaker_topic_links,
        summary
    }
    """
    base_system_prompt = (
        "당신은 회의록 분석 전문가입니다. "
        "주어진 회의록에서 구조화된 정보를 정확하게 추출하세요. "
        "모든 이름은 원문 그대로 사용하고, 추론하지 마세요."
    )

    # 이전 회차 컨텍스트 주입 (같은 프로젝트의 기존 이름 재사용 유도)
    continuity_hint = ""
    if previous_topics or previous_entities or previous_speakers:
        parts = [
            "\n\n이 회의는 진행 중인 프로젝트의 후속 회차입니다. "
            "아래는 같은 프로젝트의 이전 회차에서 이미 등록된 이름들입니다. "
            "이번 회의에서 같은 개념을 언급한다면 반드시 아래의 이름을 "
            "**그대로** 사용하세요 (철자, 띄어쓰기, 대소문자까지 동일하게). "
            "새로운 개념이면 새 이름을 자유롭게 지정하세요.",
        ]
        if previous_speakers:
            parts.append(
                f"\n이전 회차 참석자: {json.dumps(previous_speakers, ensure_ascii=False)}"
            )
        if previous_topics:
            parts.append(
                f"\n이전 회차 주제: {json.dumps(previous_topics, ensure_ascii=False)}"
            )
        if previous_entities:
            parts.append(
                f"\n이전 회차 엔티티: {json.dumps(previous_entities, ensure_ascii=False)}"
            )
        continuity_hint = "".join(parts)

    system_prompt = base_system_prompt + continuity_hint

    # ── 1차 추출 ───────────────────────────────────────────────────────────────
    response1 = get_client().messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        tools=TOOLS_PASS1,
        tool_choice={"type": "any"},
        messages=[
            {"role": "user", "content": f"다음 회의록을 분석해주세요:\n\n{transcript}"}
        ]
    )
    pass1 = _parse_tool_results(response1)

    speakers = pass1.get("extract_speakers", {}).get("speakers", [])
    topics = pass1.get("extract_topics", {}).get("topics", [])
    entities = pass1.get("extract_entities", {}).get("entities", [])

    # ── 2차 추출: 완전히 독립된 호출 (1차 결과를 텍스트로 제공) ─────────────────
    context = (
        f"다음 회의록을 분석해주세요:\n\n{transcript}\n\n"
        f"--- 참고: 이미 추출된 참석자 목록 ---\n"
        f"{json.dumps([s['name'] for s in speakers], ensure_ascii=False)}\n\n"
        f"--- 참고: 이미 추출된 주제 목록 ---\n"
        f"{json.dumps([t['name'] for t in topics], ensure_ascii=False)}\n\n"
        "위 참석자/주제 목록을 참고하여 액션 아이템, 결정 사항, 관계를 추출하세요."
    )

    response2 = get_client().messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        tools=build_tools_pass2(speakers, topics),
        tool_choice={"type": "any"},
        messages=[
            {"role": "user", "content": context}
        ]
    )
    pass2 = _parse_tool_results(response2)

    action_items = pass2.get("extract_action_items", {}).get("action_items", [])
    decisions = pass2.get("extract_decisions", {}).get("decisions", [])
    speaker_topic_links = pass2.get("build_relationships", {}).get("speaker_topic_links", [])

    # meeting summary (topic summaries 합치기)
    summary_lines = [f"- {t['name']}: {t.get('summary', '')}" for t in topics]
    summary = "\n".join(summary_lines)

    return {
        "meeting_id": meeting_id,
        "title": title,
        "project_id": project_id,
        "speakers": speakers,
        "topics": topics,
        "entities": entities,
        "action_items": action_items,
        "decisions": decisions,
        "speaker_topic_links": speaker_topic_links,
        "summary": summary,
    }
