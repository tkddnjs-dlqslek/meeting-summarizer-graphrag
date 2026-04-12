import io
import time
import httpx
import streamlit as st


def extract_text_from_file(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    if name.endswith(".pdf"):
        import fitz
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    elif name.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(uploaded_file.read()))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    return ""

API = "http://localhost:8002"

st.set_page_config(
    page_title="Meeting Summarizer + GraphRAG",
    page_icon="🧠",
    layout="wide",
)
st.title("🧠 Meeting Summarizer + GraphRAG Expert Panel")

tab1, tab2, tab3, tab4 = st.tabs([
    "📁 회의 처리",
    "🕸️ 그래프 탐색",
    "💬 Q&A 패널",
    "📋 회의 목록",
])


# ── Tab 1: 회의 처리 ──────────────────────────────────────────────────────────

with tab1:
    st.header("회의록 처리")
    mode = st.radio("입력 방식", ["텍스트 직접 입력", "오디오 파일 업로드"], horizontal=True)

    if mode == "텍스트 직접 입력":
        title_input = st.text_input("회의 제목", placeholder="Q2 임상시험 계획 검토")
        date_input = st.date_input("회의 날짜")

        doc_file = st.file_uploader("PDF / DOCX 파일 업로드 (선택)", type=["pdf", "docx"])
        if doc_file:
            extracted = extract_text_from_file(doc_file)
            if extracted:
                st.session_state["imported_transcript"] = extracted
                st.success(f"✅ 파일에서 텍스트 추출 완료 ({len(extracted)}자)")
            else:
                st.warning("텍스트를 추출하지 못했습니다.")

        transcript_input = st.text_area(
            "회의록 텍스트",
            height=300,
            value=st.session_state.get("imported_transcript", ""),
            placeholder="회의록 전문을 붙여넣거나 위에서 파일을 업로드하세요...",
        )

        if st.button("🚀 분석 시작", type="primary", disabled=not transcript_input):
            import uuid
            meeting_id = str(uuid.uuid4())
            with st.spinner("Claude가 회의록을 분석하고 그래프를 구축하는 중..."):
                try:
                    resp = httpx.post(f"{API}/process-text", json={
                        "meeting_id": meeting_id,
                        "transcript": transcript_input,
                        "title": title_input or "미제목 회의",
                        "date": str(date_input),
                    }, timeout=120)
                    resp.raise_for_status()
                    result = resp.json()
                    st.session_state["tab1_result"] = result
                    st.session_state["last_meeting_id"] = result["meeting_id"]

                except httpx.HTTPError as e:
                    st.error(f"API 오류: {e}")

    # 결과는 session_state에서 꺼내서 항상 표시
    if "tab1_result" in st.session_state:
        result = st.session_state["tab1_result"]
        st.success("✅ 분석 완료!")
        st.code(result["meeting_id"], language=None)
        col1, col2 = st.columns(2)
        col1.metric("그래프 노드 수", result["node_count"])
        col2.metric("노트 생성", "✅")

        st.subheader("AI 요약")
        st.markdown(result["summary"])

        st.subheader("그래프 데이터 미리보기")
        gd = result["graph_data"]
        c1, c2 = st.columns(2)
        with c1:
            st.write("**참석자**")
            for s in gd.get("speakers", []):
                st.write(f"- {s['name']} ({s.get('role', '')})")
            st.write("**결정 사항**")
            for d in gd.get("decisions", []):
                st.write(f"- {d['description']}")
        with c2:
            st.write("**액션 아이템**")
            for a in gd.get("action_items", []):
                deadline = f" (마감: {a['deadline']})" if a.get("deadline") else ""
                st.write(f"- [{a.get('owner', '?')}] {a['description']}{deadline}")
            st.write("**주요 엔티티**")
            for e in gd.get("entities", []):
                st.write(f"- `{e['type']}` {e['name']}")

        st.info(f"📄 Obsidian 노트: `{result['note_path']}`")

    else:  # 오디오 파일 업로드
        if mode == "오디오 파일 업로드":
            audio_file = st.file_uploader("오디오 파일 업로드", type=["mp3", "wav", "m4a", "mp4", "webm"])

            if audio_file and st.button("🎙️ STT 시작", type="primary"):
                with st.spinner("STT 작업 등록 중..."):
                    resp = httpx.post(
                        f"{API}/stt",
                        files={"file": (audio_file.name, audio_file.read(), audio_file.type)},
                        timeout=30
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    job_id = data["job_id"]
                    meeting_id = data["meeting_id"]
                    st.session_state["stt_job_id"] = job_id
                    st.session_state["last_meeting_id"] = meeting_id
                    st.info(f"Job ID: `{job_id}`")

            if "stt_job_id" in st.session_state:
                job_id = st.session_state["stt_job_id"]
                progress_bar = st.progress(0, text="STT 처리 중...")
                status_placeholder = st.empty()

                for i in range(60):
                    resp = httpx.get(f"{API}/stt/status/{job_id}", timeout=10)
                    info = resp.json()
                    status = info.get("status", "unknown")

                    if status == "done":
                        progress_bar.progress(100, text="완료!")
                        status_placeholder.success("✅ STT + 파이프라인 처리 완료")
                        pipeline_result = info.get("pipeline_result")
                        if pipeline_result:
                            st.metric("그래프 노드 수", pipeline_result.get("node_count", "?"))
                            st.markdown(pipeline_result.get("summary", ""))
                            note_path = pipeline_result.get("note_path")
                            if note_path:
                                st.info(f"📄 Obsidian 노트: `{note_path}`")
                        break
                    elif status == "error":
                        progress_bar.empty()
                        status_placeholder.error(f"오류: {info.get('error')}")
                        break
                    else:
                        progress_bar.progress(min(i * 2, 90), text=f"처리 중... ({status})")
                        time.sleep(2)


# ── Tab 2: 그래프 탐색 ────────────────────────────────────────────────────────

with tab2:
    st.header("지식 그래프 탐색")

    meeting_id_input = st.text_input(
        "Meeting ID",
        value=st.session_state.get("last_meeting_id", ""),
        key="graph_meeting_id"
    )

    if st.button("📊 그래프 조회") and meeting_id_input:
        resp = httpx.get(f"{API}/graph/{meeting_id_input}", timeout=10)
        if resp.status_code == 200:
            st.session_state["tab2_result"] = resp.json()
        else:
            st.session_state.pop("tab2_result", None)
            st.warning("해당 meeting_id의 그래프가 없습니다.")

    if "tab2_result" in st.session_state:
        data = st.session_state["tab2_result"]
        st.metric("전체 노드 수", data["total_nodes"])

        st.subheader("노드 유형별 분포")
        cols = st.columns(len(data["nodes_by_label"]) or 1)
        for i, row in enumerate(data["nodes_by_label"]):
            cols[i].metric(row["label"], row["count"])

        st.subheader("노드 레이블 설명")
        st.markdown("""
| 레이블 | 의미 |
|--------|------|
| Speaker | 회의 참석자 |
| Topic | 논의 주제 |
| ActionItem | 액션 아이템 |
| Decision | 결정 사항 |
| Entity | 외부 엔티티 (약물, 규정, 조직 등) |
""")


# ── Tab 3: Q&A 패널 ───────────────────────────────────────────────────────────

with tab3:
    st.header("GraphRAG 전문가 패널 Q&A")
    st.caption("3개 전문가 에이전트(주제/실행/맥락)가 병렬 분석 후 종합 답변을 제공합니다.")

    qa_meeting_id = st.text_input(
        "Meeting ID",
        value=st.session_state.get("last_meeting_id", ""),
        key="qa_meeting_id"
    )

    example_questions = [
        "액션 아이템과 담당자를 정리해줘",
        "이번 회의의 핵심 결정 사항은?",
        "주요 리스크와 이슈가 뭐야?",
        "다음 회의 전까지 해야 할 일 목록을 만들어줘",
        "규제 관련 이슈를 요약해줘",
    ]
    selected_q = st.selectbox("예시 질문 선택 (또는 직접 입력)", ["직접 입력"] + example_questions)

    if selected_q == "직접 입력":
        question = st.text_input("질문 입력", placeholder="이번 회의에서 결정된 사항은 무엇인가요?")
    else:
        question = selected_q
        st.text_input("질문", value=question, disabled=True)

    if st.button("🔍 전문가 패널 분석", type="primary", disabled=not (question and qa_meeting_id)):
        with st.spinner("3명의 전문가가 병렬로 분석 중..."):
            resp = httpx.post(f"{API}/agents", json={
                "question": question,
                "meeting_id": qa_meeting_id,
            }, timeout=120)

            if resp.status_code == 200:
                st.session_state["tab3_result"] = resp.json()
            else:
                st.session_state.pop("tab3_result", None)
                st.error(f"오류 {resp.status_code}: {resp.text}")

    if "tab3_result" in st.session_state:
        result = st.session_state["tab3_result"]
        st.subheader("🏆 최종 종합 답변")
        st.markdown(result["final_answer"])

        st.divider()
        st.subheader("전문가별 분석 상세")

        with st.expander("🗂️ Agent A — 주제 전문가"):
            st.markdown(result["agent_topic"])
        with st.expander("✅ Agent B — 실행 전문가"):
            st.markdown(result["agent_action"])
        with st.expander("🔍 Agent C — 맥락 전문가"):
            st.markdown(result["agent_context"])


# ── Tab 4: 회의 목록 ──────────────────────────────────────────────────────────

with tab4:
    st.header("전체 회의 목록")

    if st.button("🔄 목록 새로고침"):
        resp = httpx.get(f"{API}/meetings", timeout=10)
        if resp.status_code == 200:
            st.session_state["tab4_meetings"] = resp.json().get("meetings", [])
        else:
            st.error("API 오류")

    if "tab4_meetings" in st.session_state:
        meetings = st.session_state["tab4_meetings"]
        if meetings:
            for m in meetings:
                participants = ", ".join(m.get("participants", []))
                title = m.get("title", "")
                col1, col2, col3 = st.columns([4, 4, 2])
                col1.code(m["meeting_id"])
                col2.write(f"**{title}**" if title else "*(제목 없음)*")
                col2.caption(f"참석자: {participants or '(없음)'}")
                if col3.button("Q&A로 이동", key=m["meeting_id"]):
                    st.session_state["last_meeting_id"] = m["meeting_id"]
                    st.rerun()
        else:
            st.info("처리된 회의가 없습니다.")
