# Meeting Summarizer + GraphRAG Expert Panel

회의 오디오/텍스트를 Neo4j 지식 그래프로 구조화하고, 멀티 에이전트 GraphRAG로 질의응답하며, Obsidian 노트까지 자동 생성하는 회의 분석 시스템입니다.

## 주요 특징

- **구조화된 지식 그래프**: 단순 요약이 아닌 Neo4j 노드·관계로 저장 (Meeting, Speaker, Topic, Entity, ActionItem, Decision)
- **멀티 에이전트 GraphRAG Q&A**: 주제·실행·맥락 3개 전문가 에이전트 병렬 분석 + Synthesizer 통합
- **Claude tool_use 2단계 추출**: 1차(참석자/주제/엔티티) → 2차(액션/결정/관계)로 구조적 정확도 확보
- **Obsidian 자동 노트**: 위키링크(`[[]]`) 기반으로 회의 간 주제 연결을 개인 지식베이스에 통합
- **프로젝트 스코프 지식 누적**: 여러 회차 회의가 같은 `project_id` 아래에서 동일 Speaker/Topic 노드를 공유 → 교차 회의 분석 가능

## 이런 팀에 적합합니다

### 1. 여러 회의가 누적되는 프로젝트의 "지식자산"을 쌓고 싶은 팀

클로바노트 같은 범용 회의 요약 도구는 회의를 **하나씩 독립적으로** 요약합니다. 하지만 임상시험, 제품 개발, 장기 연구 같은 프로젝트는 "4주차의 결정이 1주차 논의의 어떤 주장을 번복한 건지", "특정 주제가 프로젝트 전체에서 어떻게 진화했는지"를 추적해야 합니다. 본 시스템은 같은 프로젝트의 모든 회의를 **하나의 지식 그래프에 누적**하여, 회의를 가로지르는 질문에 답할 수 있습니다.

### 2. 민감한 회의를 외부 클라우드로 보낼 수 없는 팀

법률 자문, 의료 회의, R&D 미팅, 투자 심사 회의 등은 녹음 파일을 외부 SaaS로 업로드하기 곤란한 경우가 많습니다. 본 시스템은 **faster-whisper(로컬 STT) + 자체 호스팅 Neo4j + 자체 Obsidian vault**로 구성되어, Claude API 호출을 제외한 모든 데이터를 내부에 유지할 수 있습니다. Claude API 대신 로컬 LLM(예: Llama, Qwen)으로 교체도 가능하도록 추출 로직이 분리되어 있습니다.

### 3. 특정 도메인에 맞춰 커스터마이징이 필요한 팀

범용 SaaS는 Entity 타입, Topic 카테고리, 추출 프롬프트가 고정돼 있어서 도메인 특화 지식을 반영하기 어렵습니다. 본 시스템은 다음 위치에서 **코드 수준의 도메인 커스터마이징**이 가능합니다:

- `api/extractor.py`의 tool schema — Entity 타입 목록(drug/regulation/court 등), Topic 카테고리 정의
- 시스템 프롬프트 — 도메인 지침 추가 (예: "임상시험 회의에서는 부작용 언급을 반드시 Entity로 추출")
- `api/agents.py` — 에이전트 역할 분담을 도메인에 맞게 재정의 (예: 법률이면 "판례 전문가/쟁점 전문가/절차 전문가")
- `graph/cypher_queries.py` — 노드 라벨, 관계 타입을 도메인 용어로 확장

---

## 기술 스택

- **STT**: faster-whisper (medium, int8, CPU)
- **LLM**: Claude claude-sonnet-4-6 (tool_use 2단계 추출 + 3 agents + Synthesizer)
- **Graph DB**: Neo4j AuraDB (무료 클라우드 또는 self-hosted)
- **Backend**: FastAPI (port 8000)
- **Frontend**: Streamlit (port 8502)
- **Notes**: Obsidian vault → `MeetingNotes/`
- **Orchestration**: asyncio (STT BackgroundTask에서 추출→그래프→노트 인라인 체이닝 + 병렬 에이전트)

---

## 아키텍처

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
    build_graph() → Neo4j AuraDB (Cypher MERGE, project_id scoped)
                 ↓
    write_meeting_note() → MeetingNotes/*.md 생성 (Obsidian 위키링크)

[Streamlit Q&A]
POST /agents → asyncio.gather(Agent A, B, C) → Synthesizer
```

### GraphRAG 에이전트 구조

| 에이전트 | Neo4j 탐색 | 특화 분석 |
|---------|-----------|---------|
| A — 주제 전문가 | Topic ↔ RELATED_TO 2-hop | 주제 연결 구조, 의제 흐름 |
| B — 실행 전문가 | ActionItem + Decision | 담당자, 마감일, 결정 근거 |
| C — 맥락 전문가 | Entity + Speaker | 외부 요소, 발화자 입장 차이 |
| Synthesizer | 3개 답변 통합 | 최종 종합 답변 |

---

## 실행 방법

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정 (`.env`)

```
ANTHROPIC_API_KEY=sk-ant-...
NEO4J_URI=neo4j+s://xxxxxxxx.databases.neo4j.io
NEO4J_USERNAME=xxxxxxxx
NEO4J_PASSWORD=...
NEO4J_DATABASE=xxxxxxxx
WHISPER_MODEL=medium
WHISPER_COMPUTE_TYPE=int8
OBSIDIAN_VAULT_PATH=./MeetingNotes
```

### 3. FastAPI 백엔드

```bash
python -m uvicorn api.main:app --port 8000
```

Swagger UI: http://localhost:8000/docs

### 4. Streamlit 프론트엔드

```bash
python -m streamlit run frontend/app.py --server.port 8502
```

---

## 주요 API 엔드포인트

| Method | Path | 설명 |
|--------|------|------|
| POST | /stt | 오디오 → STT + 전체 파이프라인 (BackgroundTask) |
| GET | /stt/status/{job_id} | STT 진행 상태 |
| POST | /process-text | 텍스트 직접 처리 (추출→그래프→노트 E2E) |
| POST | /extract | Claude tool_use 추출만 |
| POST | /graph/build | Neo4j 그래프 구축만 |
| POST | /obsidian/write | Obsidian 노트 생성만 |
| POST | /agents | GraphRAG 패널 Q&A |
| GET | /graph/{meeting_id} | 그래프 통계 |
| GET | /meetings | 전체 회의 목록 |
| GET | /health | 헬스체크 |

---

## 라이선스

MIT
