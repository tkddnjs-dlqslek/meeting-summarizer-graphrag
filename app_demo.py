"""
HuggingFace Spaces 읽기 전용 데모.

AMI ES2002 4회차 프로젝트가 이미 Neo4j에 투입된 상태에서,
방문자가 GraphRAG 전문가 패널에 질문을 던져 교차 회차 답변을 받는 데모.

투입·STT 경로는 비활성 — API 비용 통제 + 악용 방지.
FastAPI 없이 Streamlit이 직접 api.agents를 호출.
"""

import os
import asyncio
import threading
import streamlit as st

from api.agents import run_expert_panel
from graph.neo4j_client import execute_query, get_driver

# ── async → sync 브릿지 ──────────────────────────────────────────────
# Streamlit은 매 interaction마다 스크립트를 처음부터 재실행한다.
# 그래서 asyncio event loop를 스크립트 레벨에서 만들면 매번 새 loop이
# 생기고, Neo4j async driver가 이전 loop에 묶여 있어서 충돌한다.
#
# 해결: st.cache_resource로 event loop + thread를 프로세스 수명 동안
# 딱 한 번만 생성. Neo4j driver도 같은 loop에서 초기화.


@st.cache_resource
def _init_async_bridge():
    """프로세스당 1회: 전용 event loop + Neo4j driver 초기화."""
    loop = asyncio.new_event_loop()

    def _run():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    threading.Thread(target=_run, daemon=True).start()

    # Neo4j driver를 이 loop에서 초기화 (이후 모든 쿼리가 같은 loop 사용)
    future = asyncio.run_coroutine_threadsafe(get_driver(), loop)
    future.result(timeout=30)

    return loop


_loop = _init_async_bridge()


def run_async(coro):
    """async 코루틴을 동기적으로 실행 (캐시된 전용 loop 사용)."""
    future = asyncio.run_coroutine_threadsafe(coro, _loop)
    return future.result(timeout=300)

# ── 설정 ──────────────────────────────────────────────────────────────

PROJECT_ID = "ami_es2002_text"
MAX_QUERIES = 5
GITHUB_URL = "https://github.com/tkddnjs-dlqslek/meeting-summarizer-graphrag"
REPORT_URL = f"{GITHUB_URL}/blob/main/REPORT.md"

st.set_page_config(
    page_title="Meeting Summarizer — GraphRAG Demo",
    page_icon="🎯",
    layout="wide",
)

# ── 세션 ──────────────────────────────────────────────────────────────

if "query_count" not in st.session_state:
    st.session_state.query_count = 0
if "last_result" not in st.session_state:
    st.session_state.last_result = None

# ── 헤더 ──────────────────────────────────────────────────────────────

st.title("🎯 Meeting Summarizer — GraphRAG Demo")
st.markdown(f"""
> **AMI ES2002** 리모컨 디자인 프로젝트 4회차 회의(Kick-off → Functional → Conceptual → Detailed Design)가
> Neo4j 지식 그래프에 구조화돼 있습니다. 3명의 AI 전문가 에이전트가 병렬로 분석한 뒤 Synthesizer가 통합 답변합니다.
>
> [GitHub]({GITHUB_URL}) · [Experiments & Analysis]({REPORT_URL})
""")

# ── 탭 ───────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["🎯 GraphRAG Q&A", "📊 그래프 탐색", "📖 프로젝트 소개"])

# ── Tab 1: Q&A ────────────────────────────────────────────────────────

with tab1:
    remaining = MAX_QUERIES - st.session_state.query_count
    st.info(f"AMI ES2002 프로젝트 · 세션당 {MAX_QUERIES}회 질의 가능 · 남은 횟수: **{remaining}**")

    st.markdown("**추천 질문** (클릭하면 바로 질의)")
    suggestions = [
        "설계 요구사항이 4회차에 걸쳐 어떻게 진화했나?",
        "어떤 결정이 번복됐고 그 이유는?",
        "팀원들은 어디서 가장 많이 충돌했나?",
    ]

    # 추천 질문 클릭 시 session_state에 저장
    if "pending_question" not in st.session_state:
        st.session_state.pending_question = ""

    cols = st.columns(3)
    for i, (col, q) in enumerate(zip(cols, suggestions)):
        with col:
            if st.button(q, key=f"sug_{i}", use_container_width=True):
                st.session_state.pending_question = q

    question = st.text_input(
        "질문을 입력하세요",
        value=st.session_state.pending_question,
        placeholder="예: 리모컨 디자인에서 가장 큰 트레이드오프는?",
    )

    # 추천 질문 클릭 시 자동 질의 (버튼 없이)
    auto_query = bool(st.session_state.pending_question)
    st.session_state.pending_question = ""  # 소비 후 리셋

    if st.button("🔍 질의하기", type="primary", disabled=(remaining <= 0)) or auto_query:
        if not question.strip():
            st.warning("질문을 입력해주세요.")
        elif remaining <= 0:
            st.error(f"세션당 {MAX_QUERIES}회 질의 제한에 도달했습니다.")
        else:
            with st.spinner("3명의 전문가 에이전트가 그래프를 탐색하고 있습니다..."):
                try:
                    result = run_async(run_expert_panel(question, project_id=PROJECT_ID))
                    st.session_state.query_count += 1
                    st.session_state.last_result = result
                except Exception as e:
                    st.error(f"오류: {e}")

    if st.session_state.last_result:
        result = st.session_state.last_result
        st.markdown("### 📝 통합 답변 (Synthesizer)")
        st.markdown(result["final_answer"])

        with st.expander("🔎 전문가 개별 분석 보기", expanded=False):
            st.markdown("**🎯 Agent A — 주제 전문가**")
            st.markdown(result["agent_topic"])
            st.divider()
            st.markdown("**📌 Agent B — 실행 전문가**")
            st.markdown(result["agent_action"])
            st.divider()
            st.markdown("**🌐 Agent C — 맥락 전문가**")
            st.markdown(result["agent_context"])

# ── Tab 2: 그래프 통계 ────────────────────────────────────────────────

with tab2:
    st.header("Neo4j 그래프 통계 (AMI ES2002)")

    try:
        # 노드 통계
        node_stats = run_async(execute_query(
            """
            MATCH (n {project_id: $pid})
            WITH labels(n)[0] AS label, count(n) AS cnt
            RETURN label, cnt ORDER BY cnt DESC
            """,
            {"pid": PROJECT_ID},
        ))

        col1, col2 = st.columns(2)
        with col1:
            st.subheader("노드")
            for r in node_stats:
                st.metric(r["label"], r["cnt"])

        # Speaker 참석 현황
        speaker_stats = run_async(execute_query(
            """
            MATCH (s:Speaker {project_id: $pid})-[:PARTICIPATED_IN]->(m:Meeting)
            WITH s, collect(DISTINCT m.meeting_id) AS meetings
            RETURN s.name AS name, s.role AS role, size(meetings) AS meeting_count
            ORDER BY name
            """,
            {"pid": PROJECT_ID},
        ))

        with col2:
            st.subheader("참석자 × 회차")
            for r in speaker_stats:
                st.write(f"**{r['name']}** ({r['role']}) — {r['meeting_count']}/4 회차")

        # 공유 Topic
        shared_topics = run_async(execute_query(
            """
            MATCH (t:Topic {project_id: $pid})-[:DISCUSSED_IN]->(m:Meeting)
            WITH t, collect(DISTINCT m.meeting_id) AS meetings
            WHERE size(meetings) >= 2
            RETURN t.name AS name, t.category AS category, size(meetings) AS count
            ORDER BY count DESC LIMIT 10
            """,
            {"pid": PROJECT_ID},
        ))

        st.subheader("회차 간 공유 Topic (2회 이상)")
        for r in shared_topics:
            bar = "█" * r["count"]
            st.write(f"`{r['category']}` **{r['name']}** — {r['count']}회차 {bar}")

    except Exception as e:
        st.error(f"Neo4j 연결 실패: {e}")
        st.info("Neo4j AuraDB가 일시중지 상태일 수 있습니다. console.neo4j.io에서 Resume 후 새로고침해주세요.")

# ── Tab 3: 소개 ───────────────────────────────────────────────────────

with tab3:
    st.header("프로젝트 소개")

    st.markdown(f"""
### 이 프로젝트는 무엇인가?

회의 오디오/텍스트를 **Neo4j 지식 그래프**로 구조화하고,
**멀티 에이전트 GraphRAG**로 질의응답하며,
**Obsidian + Notion** 노트까지 자동 생성하는 회의 분석 시스템입니다.

### Clova Note / Notta와 뭐가 다른가?

범용 회의 요약 도구는 **회의 하나를 독립적으로** 요약합니다.
이 프로젝트는 **여러 회의가 누적되면서 생기는 프로젝트 수준의 맥락**을 다룹니다.

- "4주차의 결정이 1주차 논의를 번복한 건지?"
- "특정 주제가 프로젝트 전체에서 어떻게 진화했는지?"
- "참석자들의 입장이 회차에 걸쳐 어떻게 바뀌었는지?"

### AMI ES2002 데이터셋

이 데모에 사용된 데이터는 **AMI Meeting Corpus**의 ES2002 시리즈입니다.
4명(Laura/PM, Andrew/Marketing, David/Industrial Designer, Craig/UI)이
리모컨 디자인 프로젝트를 4회차에 걸쳐 진행한 실제 연구 회의 녹음입니다.

| 회차 | 주제 |
|------|------|
| ES2002a | Project Kick-off |
| ES2002b | Functional Design |
| ES2002c | Conceptual Design |
| ES2002d | Detailed Design |

### 기술 스택

| 구성요소 | 기술 |
|---------|------|
| LLM | Claude Sonnet 4.6 (tool_use 2-pass 추출 + 3 agents + Synthesizer) |
| Graph DB | Neo4j AuraDB |
| STT | faster-whisper (medium, int8, CPU) |
| Backend | FastAPI |
| Frontend | Streamlit |
| CI | GitHub Actions (83 tests) |

### 링크

- [GitHub Repository]({GITHUB_URL})
- [Experiments & Analysis (REPORT.md)]({REPORT_URL})
""")

# ── 사이드바 ──────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("### 🎯 Meeting Summarizer")
    st.markdown("GraphRAG Expert Panel Demo")
    st.divider()
    st.markdown(f"**Project**: `{PROJECT_ID}`")
    st.markdown(f"**질의 횟수**: {st.session_state.query_count}/{MAX_QUERIES}")
    st.divider()
    st.markdown(f"[GitHub]({GITHUB_URL})")
    st.markdown(f"[REPORT.md]({REPORT_URL})")
    st.divider()
    st.caption("이 데모는 읽기 전용입니다. 회의록 투입·STT는 비활성화돼 있습니다.")
