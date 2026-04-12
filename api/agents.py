import os
import asyncio
import anthropic
from graph.neo4j_client import execute_query
from graph import cypher_queries as Q

from dotenv import load_dotenv
load_dotenv()

MODEL = "claude-sonnet-4-6"
_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


# ── Agent A: 주제 전문가 ──────────────────────────────────────────────────────

async def agent_topic_expert(
    question: str,
    meeting_id: str | None = None,
    project_id: str | None = None,
) -> str:
    if meeting_id:
        rows = await execute_query(Q.AGENT_A_TOPICS_BY_MEETING, {"meeting_id": meeting_id})
        scope_label = f"회차 {meeting_id}"
    elif project_id:
        rows = await execute_query(Q.AGENT_A_TOPICS_BY_PROJECT, {"project_id": project_id})
        scope_label = f"프로젝트 {project_id} 전체 회차"
    else:
        return "meeting_id 또는 project_id 중 하나가 필요합니다."

    if not rows:
        return f"{scope_label}에 주제 정보가 없습니다."

    context_lines = []
    for r in rows:
        line = f"주제: {r['topic']} (카테고리: {r.get('category', '')})"
        if r.get("summary"):
            line += f"\n  요약: {r['summary']}"
        if r.get("related_topics"):
            line += f"\n  관련 주제: {', '.join(r['related_topics'])}"
        if r.get("mentioned_by"):
            line += f"\n  언급자: {', '.join(r['mentioned_by'])}"
        if r.get("discussed_in"):
            line += f"\n  등장 회차: {', '.join(r['discussed_in'])}"
        context_lines.append(line)

    context = "\n\n".join(context_lines)
    prompt = (
        f"당신은 회의의 주제와 의제 흐름을 분석하는 전문가입니다.\n\n"
        f"[분석 범위] {scope_label}\n\n"
        f"[주제 그래프 데이터]\n{context}\n\n"
        f"[질문] {question}\n\n"
        "주제 간 연결 구조와 논의 흐름에 집중하여 답변하세요. "
        "여러 회차에 걸친 분석이라면 주제의 진화·반복·확장을 명시적으로 언급하세요."
    )
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ── Agent B: 실행 전문가 ──────────────────────────────────────────────────────

async def agent_action_expert(
    question: str,
    meeting_id: str | None = None,
    project_id: str | None = None,
) -> str:
    if meeting_id:
        actions = await execute_query(Q.AGENT_B_ACTIONS_BY_MEETING, {"meeting_id": meeting_id})
        decisions = await execute_query(Q.AGENT_B_DECISIONS_BY_MEETING, {"meeting_id": meeting_id})
        scope_label = f"회차 {meeting_id}"
    elif project_id:
        actions = await execute_query(Q.AGENT_B_ACTIONS_BY_PROJECT, {"project_id": project_id})
        decisions = await execute_query(Q.AGENT_B_DECISIONS_BY_PROJECT, {"project_id": project_id})
        scope_label = f"프로젝트 {project_id} 전체 회차"
    else:
        return "meeting_id 또는 project_id 중 하나가 필요합니다."

    action_lines = []
    for a in actions:
        line = f"- [{a.get('status', 'pending')}] {a['action']}"
        if a.get("owner"):
            line += f" (담당: {a['owner']})"
        if a.get("deadline"):
            line += f" (마감: {a['deadline']})"
        if a.get("meeting_id"):
            line += f" (회차: {a['meeting_id']})"
        action_lines.append(line)

    decision_lines = []
    for d in decisions:
        line = f"- {d['decision']}"
        if d.get("rationale"):
            line += f"\n  근거: {d['rationale']}"
        if d.get("related_topics"):
            line += f"\n  관련 주제: {', '.join(d['related_topics'])}"
        if d.get("meeting_id"):
            line += f"\n  회차: {d['meeting_id']}"
        decision_lines.append(line)

    context = (
        f"[액션 아이템]\n" + ("\n".join(action_lines) or "없음") +
        f"\n\n[결정 사항]\n" + ("\n".join(decision_lines) or "없음")
    )
    prompt = (
        f"당신은 회의의 실행 계획과 의사결정을 분석하는 전문가입니다.\n\n"
        f"[분석 범위] {scope_label}\n\n"
        f"[액션아이템 및 결정 데이터]\n{context}\n\n"
        f"[질문] {question}\n\n"
        "담당자, 마감일, 결정 근거에 집중하여 답변하세요. "
        "여러 회차에 걸친 분석이라면 결정이 번복되거나 액션이 이월된 패턴을 짚어주세요."
    )
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ── Agent C: 맥락 전문가 ──────────────────────────────────────────────────────

async def agent_context_expert(
    question: str,
    meeting_id: str | None = None,
    project_id: str | None = None,
) -> str:
    if meeting_id:
        speakers = await execute_query(Q.AGENT_C_SPEAKERS_BY_MEETING, {"meeting_id": meeting_id})
        entities = await execute_query(Q.AGENT_C_ENTITIES_BY_MEETING, {"meeting_id": meeting_id})
        scope_label = f"회차 {meeting_id}"
    elif project_id:
        speakers = await execute_query(Q.AGENT_C_SPEAKERS_BY_PROJECT, {"project_id": project_id})
        entities = await execute_query(Q.AGENT_C_ENTITIES_BY_PROJECT, {"project_id": project_id})
        scope_label = f"프로젝트 {project_id} 전체 회차"
    else:
        return "meeting_id 또는 project_id 중 하나가 필요합니다."

    speaker_lines = []
    for s in speakers:
        ratio = s.get("speaking_time_ratio") or 0
        line = f"- {s['speaker']} ({s.get('role', '')}): 평균 발언 비중 {ratio:.0%}"
        if s.get("topics_mentioned"):
            line += f", 언급 주제: {', '.join(s['topics_mentioned'])}"
        if s.get("participated_meetings"):
            line += f", 참석 회차: {', '.join(s['participated_meetings'])}"
        speaker_lines.append(line)

    entity_lines = []
    for e in entities:
        line = f"- [{e.get('type', '')}] {e['entity']}"
        if e.get("associated_topics"):
            line += f" → 관련 주제: {', '.join(e['associated_topics'])}"
        entity_lines.append(line)

    context = (
        f"[참석자 현황]\n" + ("\n".join(speaker_lines) or "없음") +
        f"\n\n[주요 엔티티]\n" + ("\n".join(entity_lines) or "없음")
    )
    prompt = (
        f"당신은 회의의 참석자 역할과 외부 맥락(관련 조직, 규정, 제품 등)을 분석하는 전문가입니다.\n\n"
        f"[분석 범위] {scope_label}\n\n"
        f"[참석자 및 엔티티 데이터]\n{context}\n\n"
        f"[질문] {question}\n\n"
        "발화자의 입장 차이, 관련 외부 요소에 집중하여 답변하세요. "
        "여러 회차에 걸친 분석이라면 참석자의 입장 변화와 핵심 엔티티의 지속성을 평가하세요."
    )
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ── Synthesizer ───────────────────────────────────────────────────────────────

async def synthesizer(question: str, answers: list[str]) -> str:
    agent_labels = ["주제 전문가", "실행 전문가", "맥락 전문가"]
    panel_text = "\n\n".join(
        f"[{label}의 분석]\n{answer}"
        for label, answer in zip(agent_labels, answers)
    )
    prompt = (
        f"당신은 여러 전문가의 분석을 통합하는 수석 분석가입니다.\n\n"
        f"다음은 동일한 질문에 대한 3명의 전문가 분석입니다:\n\n{panel_text}\n\n"
        f"[원래 질문] {question}\n\n"
        "세 전문가의 관점을 통합하여 핵심을 중심으로 명확하고 실용적인 최종 답변을 작성하세요. "
        "중복을 제거하고, 상충하는 의견이 있다면 균형 있게 제시하세요."
    )
    response = get_client().messages.create(
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ── 진입점 ────────────────────────────────────────────────────────────────────

async def run_expert_panel(
    question: str,
    meeting_id: str | None = None,
    project_id: str | None = None,
) -> dict:
    """3개 에이전트 병렬 실행 후 synthesizer 통합.

    meeting_id를 주면 특정 회차 범위, project_id를 주면 프로젝트 전체 회차 범위로
    분석한다. 둘 다 없으면 오류.
    """
    if not meeting_id and not project_id:
        raise ValueError("meeting_id 또는 project_id 중 하나가 필요합니다.")

    answers = await asyncio.gather(
        agent_topic_expert(question, meeting_id, project_id),
        agent_action_expert(question, meeting_id, project_id),
        agent_context_expert(question, meeting_id, project_id),
    )
    final = await synthesizer(question, list(answers))
    return {
        "question": question,
        "meeting_id": meeting_id,
        "project_id": project_id,
        "agent_topic": answers[0],
        "agent_action": answers[1],
        "agent_context": answers[2],
        "final_answer": final,
    }
