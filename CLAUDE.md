# Meeting Summarizer + GraphRAG Expert Panel

포트폴리오 3번 프로젝트 — 회의 오디오/텍스트 → Neo4j 지식 그래프 → GraphRAG 전문가 패널 Q&A → Obsidian 자동 노트

## 기술 스택
- STT: faster-whisper (medium, int8, CPU)
- LLM: Claude claude-sonnet-4-6 (tool_use 2단계 추출 + 3 agents)
- Graph DB: Neo4j AuraDB 무료 클라우드
- Orchestration: asyncio (STT BackgroundTask → 추출→그래프→노트 인라인 체이닝, 병렬 에이전트)
- Backend: FastAPI (port 8000)
- Frontend: Streamlit (port 8502)
- Notes: Obsidian vault → MeetingNotes/

---

## 실행 방법

### 1. pip install
```bash
cd C:/Users/user/Desktop/03_meeting_summarizer
pip install -r requirements.txt
```

### 2. .env 설정
`.env` 파일에서 `ANTHROPIC_API_KEY` 추가:
```
ANTHROPIC_API_KEY=sk-ant-...
```

### 3. FastAPI 백엔드
```bash
cd C:/Users/user/Desktop/03_meeting_summarizer
python -m uvicorn api.main:app --port 8002
```
- Swagger UI: http://localhost:8000/docs

### 4. Streamlit 프론트엔드
```bash
python -m streamlit run frontend/app.py --server.port 8502
```
- UI: http://localhost:8502

---

## 빠른 테스트

FastAPI Swagger(http://localhost:8000/docs)에서 `/process-text` 엔드포인트로 직접 테스트:

```json
{
  "meeting_id": "test-001",
  "transcript": "tests/sample_transcript.txt 내용 붙여넣기",
  "title": "Q2 임상시험 계획 검토",
  "date": "2026-03-21"
}
```

또는 curl:
```bash
curl -X POST http://localhost:8000/process-text \
  -H "Content-Type: application/json" \
  -d @- <<EOF
{
  "meeting_id": "test-001",
  "transcript": "$(cat tests/sample_transcript.txt)",
  "title": "Q2 임상시험 계획 검토",
  "date": "2026-03-21"
}
EOF
```

---

## 데이터 플로우

```
[오디오 입력]                          [텍스트 입력]
    ↓                                       ↓
POST /stt (BackgroundTask)                  │
  faster-whisper STT                        │
    ↓                                       ↓
  run_transcription()              POST /process-text
    └────────────┬──────────────────────────┘
                 ↓
    extract_graph_data() → Claude tool_use 2단계 추출
      1차: extract_speakers, extract_topics, extract_entities
      2차: extract_action_items, extract_decisions, build_relationships
                 ↓
    build_graph() → Neo4j AuraDB (Cypher MERGE)
                 ↓
    write_meeting_note() → MeetingNotes/*.md 생성

[Streamlit Q&A]
POST /agents → asyncio.gather(Agent A, B, C) → Synthesizer
```

---

## GraphRAG 에이전트 구조

| 에이전트 | Neo4j 탐색 | 특화 분석 |
|---------|-----------|---------|
| A — 주제 전문가 | Topic ↔ RELATED_TO 2-hop | 주제 연결 구조, 의제 흐름 |
| B — 실행 전문가 | ActionItem + Decision | 담당자, 마감일, 결정 근거 |
| C — 맥락 전문가 | Entity + Speaker | 외부 요소, 발화자 입장 차이 |
| Synthesizer | 3개 답변 통합 | 최종 종합 답변 |

---

## 주요 API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | /stt | 오디오 → STT (BackgroundTask) |
| GET  | /stt/status/{job_id} | STT 진행 상태 |
| POST | /process-text | 텍스트 직접 처리 (테스트용) |
| POST | /extract | Claude tool_use 추출 |
| POST | /graph/build | Neo4j 그래프 구축 |
| POST | /obsidian/write | Obsidian 노트 생성 |
| POST | /agents | GraphRAG 패널 Q&A |
| GET  | /graph/{meeting_id} | 그래프 통계 |
| GET  | /meetings | 전체 회의 목록 |
| GET  | /health | 헬스체크 |

---

## 환경변수 (.env)

```
ANTHROPIC_API_KEY=          # Anthropic API 키 (필수)

NEO4J_URI=neo4j+s://f6b3658f.databases.neo4j.io
NEO4J_USERNAME=f6b3658f
NEO4J_PASSWORD=...
NEO4J_DATABASE=f6b3658f

WHISPER_MODEL=medium         # tiny/base/small/medium/large-v3
WHISPER_COMPUTE_TYPE=int8    # int8(CPU) / float16(GPU)

OBSIDIAN_VAULT_PATH=C:/Users/user/Desktop/03_meeting_summarizer/MeetingNotes
```

---

## 트러블슈팅

### Neo4j AuraDB 연결 오류
- AuraDB Free는 **비활성 7일 후 일시중지, 30일 후 삭제됨**
- console.neo4j.io에서 인스턴스 상태 확인 후 Resume 클릭
- URI 형식: `neo4j+s://` (TLS 필수, `bolt://` 불가)

### faster-whisper 모델 없음
- 첫 실행 시 모델 자동 다운로드 (~500MB for medium)
- 시간이 걸릴 수 있음 — 로그에서 다운로드 진행 확인

### Claude API 오류
- ANTHROPIC_API_KEY 확인
- Claude Code 구독과 별개로 Anthropic API 유료 과금 발생

### Streamlit 포트 충돌
- 8502 포트 이미 사용 중이면: `--server.port 8503` 으로 변경
