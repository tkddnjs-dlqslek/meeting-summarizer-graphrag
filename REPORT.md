# Meeting Summarizer + GraphRAG Expert Panel 개발 보고서

> 작성일: 2026-04-11
> 프로젝트 디렉토리: `C:/Users/user/Desktop/03_meeting_summarizer`

---

## 1. 프로젝트 개요

### 1-1. 이 프로젝트가 무엇인가?

**회의 녹음이나 회의록 텍스트를 넣으면, AI가 자동으로 내용을 분석하고, 지식 그래프로 저장하고, Obsidian 노트까지 생성해주는 시스템**입니다.

단순 요약이 아니라 **"누가 무슨 주제를 말했고, 어떤 결정이 내려졌고, 후속 액션은 누가 담당하는지"**를 구조적으로 추출하여 그래프 데이터베이스에 저장합니다. 이후 사용자가 질문을 하면 **3명의 AI 전문가 에이전트**가 각자의 관점에서 그래프를 탐색하고 분석한 뒤, 종합 답변을 제공합니다.

### 1-2. 왜 만들었는가?

일반적인 회의 요약 도구는 "텍스트 → 요약 텍스트" 수준에서 끝납니다. 이 프로젝트는 한 단계 더 나아가 다음을 시연합니다:

- **GraphRAG 패턴**: 단순 텍스트 검색이 아닌, 그래프 구조를 활용한 관계 기반 질의응답
- **멀티 에이전트 시스템**: 하나의 LLM이 아닌, 역할이 다른 3개의 에이전트가 동시에 분석
- **구조화된 정보 추출**: Claude의 tool_use 기능으로 비정형 텍스트에서 정형 데이터를 뽑아냄
- **실용적 산출물**: 분석 결과가 Obsidian 노트로 자동 생성되어 실무에서 바로 활용 가능

---

## 2. 기술 스택 및 각 기술의 역할

| 기술 | 버전/종류 | 역할 | 왜 이 기술인가? |
|------|----------|------|----------------|
| **FastAPI** | Python | 백엔드 API 서버 | 비동기 처리 지원, 자동 API 문서 생성(Swagger) |
| **Streamlit** | Python | 프론트엔드 웹 UI | 빠른 프로토타이핑, Python만으로 UI 구현 가능 |
| **Claude Sonnet** | claude-sonnet-4-6 | LLM (대규모 언어 모델) | tool_use 기능으로 구조화된 데이터 추출 가능 |
| **Neo4j AuraDB** | 무료 클라우드 | 그래프 데이터베이스 | 노드/관계 기반 저장 → 에이전트가 관계를 따라가며 탐색 |
| **faster-whisper** | medium, int8, CPU | 음성→텍스트 변환(STT) | 오프라인 실행 가능, 한국어 지원, GPU 없이 동작 |
| **Obsidian** | 마크다운 볼트 | 분석 결과 노트 저장소 | 위키링크(`[[]]`) 지원, 지식 관리에 최적화 |

---

## 3. 전체 데이터 흐름 (처음부터 끝까지)

시스템이 데이터를 처리하는 전체 과정을 순서대로 설명합니다.

```
[입력]                    [AI 추출]               [저장]              [활용]
                                              
오디오 파일  ─→  STT  ─┐                       ┌→ Neo4j 그래프  ─→  Q&A 에이전트
                       ├→ Claude 2단계 추출 ─→ ┤
텍스트 입력  ──────────┘                       └→ Obsidian 노트  ─→  팀 공유
```

### 3-1단계: 입력 수신

사용자는 두 가지 방식으로 회의 내용을 입력할 수 있습니다.

- **텍스트 직접 입력**: 회의록 텍스트를 붙여넣기 (PDF/DOCX 파일 업로드도 지원)
- **오디오 파일 업로드**: mp3, wav 등 → faster-whisper가 한국어 STT 수행

### 3-2단계: Claude 2단계 구조화 추출 (`api/extractor.py`)

회의록 텍스트를 Claude에게 보내면, **2번에 걸쳐** 구조화된 정보를 추출합니다. 왜 2단계인가? 1차에서 추출한 "참석자 목록"과 "주제 목록"을 2차에서 참조해야 하기 때문입니다.

#### 1차 추출 (사실 정보)

Claude에게 3개의 도구(tool)를 제공하고, 한 번의 API 호출로 동시에 사용하게 합니다:

| 도구 | 추출 대상 | 예시 |
|------|----------|------|
| `extract_speakers` | 참석자 이름, 역할, 발언 비중 | 김민준 (프로젝트 매니저) 35% |
| `extract_topics` | 논의 주제, 카테고리, 요약 | "식약처 IND 신청" (regulatory) |
| `extract_entities` | 외부 엔티티 (약물, 조직, 규정 등) | KR-204 (drug), TGA (organization) |

#### 2차 추출 (관계 및 실행 사항)

1차 결과를 컨텍스트로 넘기고, 새로운 3개 도구로 추출합니다:

| 도구 | 추출 대상 | 예시 |
|------|----------|------|
| `extract_action_items` | 후속 할 일, 담당자, 마감일 | 박지훈 → 독성 연구 데이터 준비 (4/15) |
| `extract_decisions` | 결정 사항과 근거 | "6월 말 시작 목표 유지" (IRB 승인 완료 근거) |
| `build_relationships` | 발화자↔주제 연결 관계 | 박지훈 → "식약처 IND 신청" 주제 언급 |

#### 추출 결과 예시 (실제 테스트 데이터)

33줄짜리 임상시험 회의록에서 다음이 자동 추출되었습니다:

- **참석자 4명** (역할 + 발언 비중 포함)
- **주제 6개** (카테고리 분류 + 주제 간 관계 포함)
- **엔티티 11개** (약물, 조직, 규정, 인물)
- **액션 아이템 5개** (담당자, 마감일 포함)
- **결정 사항 5개** (결정 근거 포함)

### 3-3단계: Neo4j 그래프 구축 (`api/graph_builder.py`)

추출된 데이터를 Neo4j 그래프 데이터베이스에 저장합니다. "그래프 데이터베이스"란 데이터를 표(table)가 아닌 **노드(점)와 관계(선)**로 저장하는 데이터베이스입니다.

#### 노드 유형 (6종)

```
Meeting ─── 회의 자체
Speaker ─── 참석자
Topic ───── 논의 주제
Entity ──── 외부 엔티티 (약물, 조직, 규정 등)
ActionItem ─ 할 일
Decision ── 결정 사항
```

#### 관계 유형 (5종)

```
Speaker ──MENTIONED──→ Topic      (누가 어떤 주제를 언급했는가)
Speaker ──OWNS───────→ ActionItem (누가 어떤 할 일을 맡았는가)
Topic ────RELATED_TO── Topic      (주제 간 연관 관계)
Decision ─ABOUT──────→ Topic      (결정이 어떤 주제에 관한 것인가)
Entity ───ASSOCIATED_WITH→ Topic  (엔티티가 어떤 주제와 관련 있는가)
```

#### 왜 그래프인가?

일반 데이터베이스는 "임상시험과 관련된 결정 사항 중 박지훈이 담당하는 것"을 찾으려면 복잡한 JOIN 쿼리가 필요합니다. 그래프에서는 노드에서 관계를 따라가기만 하면 됩니다. 이것이 뒤에 나오는 에이전트 Q&A의 핵심 장점입니다.

#### 실제 저장 결과

```
전체 노드 수: 32개
  - Entity: 11, Topic: 6, ActionItem: 5, Decision: 5, Speaker: 4, Meeting: 1
관계 수: 112개
```

### 3-4단계: Obsidian 노트 생성 (`api/obsidian_writer.py`)

분석 결과를 Obsidian 마크다운 파일로 자동 생성합니다. 생성된 노트에는 다음이 포함됩니다:

- YAML frontmatter (meeting_id, 날짜, 참석자, 태그)
- 참석자 목록 (역할 + 발언 비중)
- 핵심 주제 (카테고리 + 요약 + `[[위키링크]]`로 관련 주제 연결)
- 결정 사항 (근거 포함)
- 액션 아이템 (체크리스트 형식, 담당자 + 마감일)
- 주요 엔티티
- AI 요약

생성 위치: `MeetingNotes/2026-03-21_Q2 임상시험 계획 검토.md`

### 3-5단계: GraphRAG 전문가 패널 Q&A (`api/agents.py`)

사용자가 질문을 하면 **3개의 AI 에이전트가 동시에(병렬로)** 각자의 관점에서 Neo4j 그래프를 탐색하고, 최종적으로 **Synthesizer가 3개의 답변을 통합**합니다.

```
        사용자 질문: "KR-204 임상시험의 주요 리스크는?"
                    │
    ┌───────────────┼───────────────┐
    ▼               ▼               ▼
┌────────┐   ┌────────┐   ┌────────┐
│Agent A │   │Agent B │   │Agent C │     ← 3개가 동시에 실행 (asyncio.gather)
│주제전문│   │실행전문│   │맥락전문│
└────┬───┘   └────┬───┘   └────┬───┘
     │            │            │
     ▼            ▼            ▼
  Topic        ActionItem    Speaker
  RELATED_TO   Decision      Entity
  (2-hop)      OWNS          ASSOCIATED_WITH
     │            │            │
     └────────────┼────────────┘
                  ▼
           ┌────────────┐
           │Synthesizer │     ← 3개 답변을 통합하여 최종 답변 생성
           └────────────┘
```

#### 각 에이전트의 역할

| 에이전트 | Neo4j에서 탐색하는 데이터 | 분석 관점 |
|---------|------------------------|----------|
| **Agent A (주제 전문가)** | Topic 노드 + RELATED_TO 관계 (2-hop) + 언급한 Speaker | 주제 간 연결 구조, 의제 흐름, 논의의 전체 맥락 |
| **Agent B (실행 전문가)** | ActionItem + Decision + OWNS 관계 | 누가 무엇을 해야 하는지, 마감일, 결정의 근거 |
| **Agent C (맥락 전문가)** | Speaker + Entity + ASSOCIATED_WITH 관계 | 참석자의 입장 차이, 외부 요인, 이해관계 |
| **Synthesizer** | 위 3개 에이전트의 답변 전체 | 중복 제거, 상충 의견 조율, 최종 종합 답변 |

#### 왜 에이전트가 3개인가?

하나의 LLM에게 모든 것을 물어보면 특정 관점이 누락되기 쉽습니다. 예를 들어 "리스크가 뭐야?"라고 물으면 주제 관점의 리스크만 나올 수 있습니다. 3개로 나누면:

- Agent A: "식약처 승인 지연 시 환자 등록 일정에 연쇄 영향" (주제 구조 분석)
- Agent B: "박지훈의 4/15 마감 미준수 시 전체 일정 붕괴" (실행 계획 분석)
- Agent C: "호주 TGA와의 규제 정합성 미확보 시 동시 임상 차질" (외부 맥락 분석)

이처럼 **관점이 다른 답변**이 나오고, Synthesizer가 이를 통합합니다.

---

## 4. 시스템 아키텍처 (구성 요소 간 관계)

```
┌─ Streamlit (port 8502) ──────────────────────────────────────┐
│  [Tab1] 회의 처리   → POST /process-text                     │
│  [Tab2] 그래프 탐색  → GET  /graph/{id}                       │
│  [Tab3] Q&A 패널    → POST /agents                           │
│  [Tab4] 회의 목록    → GET  /meetings                         │
└──────────────────────────────────┬────────────────────────────┘
                                   │ HTTP
┌─ FastAPI (port 8002) ────────────▼────────────────────────────┐
│                                                                │
│  /process-text ─→ extractor.py ─→ graph_builder.py            │
│                    (Claude API)    (Neo4j 저장)                │
│                         │              │                       │
│                         ▼              ▼                       │
│                  obsidian_writer.py  Neo4j AuraDB (클라우드)   │
│                  (마크다운 생성)                                │
│                                                                │
│  /agents ──────→ agents.py                                    │
│                  (3 에이전트 병렬) ←── Neo4j Cypher 쿼리       │
│                                                                │
│  /stt ─────────→ stt.py (faster-whisper, BackgroundTask)      │
│                         │                                      │
│                         ▼                                      │
│                  run_transcription() 내부에서                   │
│                  extractor → graph_builder → obsidian_writer   │
│                  를 인라인 체이닝 (별도 오케스트레이터 없음)     │
└────────────────────────────────────────────────────────────────┘
```

### 오디오 입력 경로

오디오 파일이 업로드되면 `/stt` 엔드포인트가 `BackgroundTask`로 `run_transcription()`을 실행합니다. 이 함수는 STT 완료 후 같은 프로세스 안에서 다음을 순차적으로 호출합니다:

```
faster-whisper → extract_graph_data() → build_graph() → write_meeting_note()
```

처리 결과는 `job_store[job_id]["pipeline_result"]`에 저장되고, Streamlit은 `/stt/status/{job_id}`를 폴링해서 완료 시점에 노드 수/요약/노트 경로를 표시합니다. 텍스트 입력 경로(`/process-text`)와 동일한 4단계지만, 호출 지점만 BackgroundTask인 셈입니다.

---

## 5. 프로젝트 파일 구조

```
03_meeting_summarizer/
│
├── api/                          ← 백엔드 핵심 로직 (694줄)
│   ├── main.py          (172줄)   FastAPI 앱, 10개 엔드포인트 정의
│   ├── extractor.py     (263줄)   Claude tool_use 2단계 추출 로직
│   ├── agents.py        (175줄)   3개 에이전트 + Synthesizer
│   ├── graph_builder.py  (89줄)   Neo4j 그래프 구축
│   ├── obsidian_writer.py(127줄)  Obsidian 마크다운 노트 생성
│   └── stt.py            (69줄)   faster-whisper STT 처리
│
├── graph/                        ← Neo4j 연결 및 쿼리 (206줄)
│   ├── neo4j_client.py   (57줄)   Neo4j 비동기 드라이버 래퍼
│   └── cypher_queries.py(149줄)   20개 이상의 Cypher 쿼리 정의
│
├── frontend/
│   └── app.py           (282줄)   Streamlit UI (4개 탭)
│
├── MeetingNotes/                 ← 생성된 Obsidian 노트 저장 폴더
├── tests/
│   └── sample_transcript.txt     테스트용 임상시험 회의록 (33줄)
│
├── .env                          환경변수 (API 키, DB 접속정보)
├── requirements.txt              Python 의존성 (12개 패키지)
└── CLAUDE.md                     프로젝트 문서
```

**총 코드량: 약 1,500줄**

---

## 6. API 엔드포인트 목록

| Method | Path | 설명 | 주요 입력 | 주요 출력 |
|--------|------|------|----------|----------|
| POST | `/process-text` | **E2E 파이프라인** (추출→그래프→노트) | transcript, title, date | summary, node_count, note_path |
| POST | `/extract` | Claude 구조화 추출만 수행 | transcript | graph_data (speakers, topics, ...) |
| POST | `/graph/build` | Neo4j 그래프 구축만 수행 | graph_data | node_count |
| POST | `/obsidian/write` | Obsidian 노트 생성만 수행 | graph_data | file_path |
| POST | `/agents` | GraphRAG 전문가 패널 Q&A | question, meeting_id | agent_topic/action/context + final_answer |
| POST | `/stt` | 오디오 → STT 시작 | audio file | job_id |
| GET | `/stt/status/{job_id}` | STT 진행 상태 조회 | - | status, transcript |
| GET | `/graph/{meeting_id}` | 그래프 통계 조회 | - | nodes_by_label, total_nodes |
| GET | `/meetings` | 전체 회의 목록 | - | meetings[] |
| GET | `/health` | 서버 상태 확인 | - | status: ok |

---

## 7. 실행 테스트 결과

2026-04-11 기준으로 수행한 E2E(End-to-End) 테스트 결과입니다.

### 7-1. 테스트 환경

- OS: Windows 11
- Python: 3.13
- Neo4j: AuraDB Free (인스턴스 ID: f6b3658f)
- LLM: Claude Sonnet (claude-sonnet-4-6)

### 7-2. 테스트 데이터

`tests/sample_transcript.txt` — Q2 임상시험 계획 검토 회의록 (33줄, 참석자 4명)

### 7-3. 테스트 결과 요약

| 테스트 항목 | 결과 | 상세 |
|-----------|------|------|
| 서버 기동 | **PASS** | Neo4j 연결 포함 정상 부팅 |
| 헬스체크 (`/health`) | **PASS** | `{"status":"ok"}` 반환 |
| Claude 추출 (`/extract`) | **PASS** | 4명 발화자, 6주제, 11엔티티, 5액션아이템, 5결정 정확 추출 |
| 그래프 구축 (`/graph/build`) | **PASS** | Neo4j에 32개 노드 생성 |
| Obsidian 노트 (`/obsidian/write`) | **PASS** | 마크다운 노트 정상 생성 |
| E2E 파이프라인 (`/process-text`) | **PASS** | 추출→그래프→노트 원스톱 완료 |
| 그래프 조회 (`/graph/{id}`) | **PASS** | 노드 유형별 통계 정상 반환 |
| 회의 목록 (`/meetings`) | **PASS** | 4개 회의 목록 반환 |
| 에이전트 Q&A (`/agents`) | **PASS** | 3개 에이전트 + Synthesizer 모두 정상 응답 |
| STT (`/stt`) | 미테스트 | 오디오 파일 필요 + faster-whisper 모델 다운로드 필요 |
| Streamlit UI | 미테스트 | 별도 실행 필요 |

### 7-4. 발견된 이슈 및 조치

| 이슈 | 원인 | 조치 |
|------|------|------|
| 서버 기동 실패 | Neo4j 연결 실패 시 서버 자체가 시작 안 됨 | `asyncio.wait_for(timeout=10)` 추가하여 graceful 처리 |
| Neo4j DNS resolve 실패 | AuraDB 무료 인스턴스 비활성 → 일시중지 상태 | Neo4j 콘솔에서 Resume 실행으로 복구 |

---

## 8. 실행 방법

### 8-1. 사전 준비

```bash
# 1. 의존성 설치
cd C:/Users/user/Desktop/03_meeting_summarizer
pip install -r requirements.txt

# 2. .env 파일에 API 키 설정 (이미 설정됨)
# ANTHROPIC_API_KEY, NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD 등
```

### 8-2. 서버 실행 (터미널 2~3개)

```bash
# 터미널 1: FastAPI 백엔드
cd C:/Users/user/Desktop/03_meeting_summarizer
python -m uvicorn api.main:app --port 8002

# 터미널 2: Streamlit 프론트엔드
python -m streamlit run frontend/app.py --server.port 8502
```

### 8-3. 빠른 테스트

Swagger UI(`http://localhost:8002/docs`)에서 `/process-text` 호출:

```json
{
  "meeting_id": "test-001",
  "transcript": "(tests/sample_transcript.txt 내용 붙여넣기)",
  "title": "Q2 임상시험 계획 검토",
  "date": "2026-03-21"
}
```

---

## 9. 주의사항 및 운영 이슈

### Neo4j AuraDB 무료 인스턴스

- **7일 비활성 시 일시중지** → [console.neo4j.io](https://console.neo4j.io)에서 Resume 클릭
- **30일 비활성 시 완전 삭제** → 새로 생성 필요 (데이터 유실)
- 현재 인스턴스: `f6b3658f.databases.neo4j.io` (Resume 완료 상태)

### Claude API 비용

- Anthropic API 유료 과금 발생 (Claude Code 구독과 별개)
- 1회 `/process-text` 호출 시 Claude API 2회 호출 (1차 추출 + 2차 추출)
- 1회 `/agents` 호출 시 Claude API 4회 호출 (에이전트 3개 + Synthesizer 1개)

### faster-whisper 모델

- 첫 실행 시 모델 자동 다운로드 (~500MB for medium)
- CPU 모드(int8)로 동작 — GPU 불필요하지만 처리 속도가 느릴 수 있음

---

## 10. AMI Corpus 4회차 연속성 실험 (2026-04-12)

리팩터링된 `project_id` 스코프 글로벌 스키마가 **실제 공개 데이터셋**에서도 회차 간 연결을 유지하는지 검증한 실험입니다.

### 10-1. 스키마 리팩터링

기존 스키마는 Speaker/Topic/Entity가 `(name, meeting_id)`로 식별돼서 같은 사람·주제가 회차마다 별개 노드로 복제됐습니다. 이를 `(name, project_id)` 스코프 글로벌 노드로 바꾸고 회차 연결 엣지 4종을 추가했습니다:

- `(:Speaker)-[:PARTICIPATED_IN {speaking_time_ratio}]->(:Meeting)`
- `(:Topic)-[:DISCUSSED_IN]->(:Meeting)`
- `(:Entity)-[:MENTIONED_IN]->(:Meeting)`
- `(:Meeting)-[:FOLLOWS]->(:Meeting)`

`ActionItem`/`Decision`은 회차별 이벤트이므로 `meeting_id` 로컬 유지. `extract_graph_data()`에는 **"같은 project_id의 이전 회차 Topic/Entity/Speaker 이름 목록"**을 시스템 프롬프트에 주입하는 장치를 추가해 Claude가 동일 개념을 동일 이름으로 재사용하도록 유도했습니다.

### 10-2. 데이터셋 — AMI Meeting Corpus ES2002

- 출처: HuggingFace `edinburghcstr/ami` (ihm config)
- 대상: ES2002a~d (한 팀의 scenario meeting 4회차 — Kickoff → Functional → Conceptual → Detailed Design)
- 참가자: Laura(PM), David(Industrial Designer), Craig(UI), Andrew(Marketing) — 4명이 4회차 전체 참석
- 언어: 영어 (Whisper `language="en"`)

**Speaker 매핑 함정**: HF 데이터셋의 `speaker_id`는 `FEE005/MEE006/MEE007/MEE008` 같은 해시. 발화 첫 등장 순서로 A/B/C/D 레이블링하면 회차마다 순서가 달라 같은 사람이 다른 letter로 붙습니다. 초기 fetch 스크립트가 이 버그를 가져 ES2002d에서 Speaker가 `A/B/C/D` 익명 라벨로 뽑혔고, 이를 디버깅하여 ES2002a의 자기소개 발화에서 `speaker_id → 실명` 매핑을 직접 추출하는 방식으로 수정했습니다 (`tests/fetch_ami_es2002.py`).

### 10-3. Phase 1·2 — 텍스트 경로 결과

`project_id="ami_es2002_text"`로 ES2002a~d를 `/process-text`에 순차 투입.

| 검증 항목 | 결과 |
|---|---|
| Speaker 4회차 모두 참석 공유 | **4/4명 전부 ✅** (Laura, Andrew, David, Craig 각각 단일 노드) |
| 2회차 이상 공유 Topic | **10개** (리모컨 기능/재무 전략/다음 단계는 4회 전부, 기술 컴포넌트는 3회) |
| 2회차 이상 공유 Entity | **14개** (Remote Control/VCR/DVD/LCD/Jog Dial/Kinetic Power 등) |
| `Meeting-FOLLOWS-Meeting` 체인 | w2→w1, w3→w2, w4→w3 (3개 엣지) |
| 전체 그래프 | 4 Meeting, 4 Speaker, 14 Topic, 18 Entity, 14 ActionItem, 36 Decision |

Phase 2에서는 **연속성을 검증하는 3개 질문**을 `/agents project_id=...`로 던졌습니다:

1. **설계 진화** (a→d 기능 추가·제거·변경 + 동인) — "시장 판단 → 사용성 → 예산"의 깔때기 구조를 정확히 추적. 특히 "16.8€ → 12.5€ 예산 조정"이 LCD·키네틱 전원·고무 소재 제거를 연쇄적으로 강제한 과정을 포착.
2. **결정 번복** (이전 회차 결정이 후행 회차에서 뒤집힌 5가지 사례) — 전원 방식(배터리→키네틱→배터리), LCD 2단계 제거, 음성인식 조건부 유보 등 **회차 간 의사결정 흐름**을 정확히 식별.
3. **갈등과 합의** (누가 어디서 충돌했나) — Andrew(혁신 드라이버)/David(현실 검증자)/Laura(조율자)/Craig(기술 검토자)의 역할 분화를 대화 맥락에서 재구성.

세 답변 모두 **단일 회차 모드로는 나올 수 없는** 교차 회차 인과 추적을 포함했습니다. `project_id` 스코프 글로벌 스키마가 의도대로 작동한다는 실증.

### 10-4. Phase 3 — 오디오 경로 결과

ES2002a Mix-Headset WAV(38.8MB, 약 30분)를 AMI 공식 미러에서 다운로드 후 `/stt` 엔드포인트에 `language="en"`으로 투입. faster-whisper medium int8 CPU로 약 22분 만에 STT 완료, 이후 추출/그래프/노트까지 원스톱 진행. `project_id="ami_es2002_audio"`로 저장.

**Windows 심링크 이슈**: 초기 실행에서 HF Hub가 캐시 디렉토리에 심링크 생성 시 `OSError [WinError 1314]`로 실패. 해결: `snapshot_download(repo_id=..., local_dir="./models/whisper-medium")`로 프로젝트 내부 폴더에 복사 다운로드 후 `.env`의 `WHISPER_MODEL`을 로컬 경로로 변경.

### 10-5. Phase 4 — 교차 평가 (텍스트 vs 오디오)

**WER 측정** (원본 AMI ihm transcript vs Whisper Mix-Headset 결과):

| 지표 | 값 |
|---|---|
| **WER** | **30.45%** |
| Substitutions | 196 |
| Deletions | 535 ← 지배적 원인 |
| Insertions | 64 |
| Hits | 1,880 |

삭제 535개가 WER의 대부분을 차지합니다. 원인: AMI `ihm` reference는 개별 헤드셋 마이크 4개를 합친 발화이고, Whisper는 **Mix-Headset WAV 하나**만 본 것이라 overlapping speech와 멀리 있는 마이크 발화를 놓쳤습니다. STT 엔진 한계가 아니라 **입력 채널 불일치**가 주요 원인.

**Q1 (참가자·역할·목표 단가)** — 텍스트 vs 오디오 답변 비교:

| 항목 | TEXT 프로젝트 | AUDIO 프로젝트 |
|---|---|---|
| Laura/Andrew/David | 정확 | 정확 |
| 4번째 멤버 | **Craig** (UI) ✅ | **Greg** (UI) ❌ — Whisper 오인식 |
| 목표 단가 €12.50 | ✅ 정확 | ✅ 정확 |
| 16.8€ 초과 사례 언급 | ✅ (ES2002d 교차 참조) | ❌ (1회차만 보유) |

**핵심 관찰 1**: Whisper가 Craig을 Greg로 잘못 들은 오류가 그래프의 Speaker/Entity 노드로 **그대로 저장**되고, `/agents` 답변까지 전파됐습니다. **STT 품질이 하류 GraphRAG 결과에 직접 영향을 준다**는 실증.

**핵심 관찰 2**: WER 30%에도 **€25 / €12.50 / 5천만 유로** 같은 핵심 숫자는 완벽하게 보존됐습니다. 구조화 추출(tool_use)이 ASR noise에 어느 정도 **복원력**을 제공한다는 긍정 신호.

**Q2 (주제 흐름 + 마지막 결정)** — text는 자연스럽게 4회차 전체를 교차 참조해 답변(a/b/c/d 각 4~6개 소주제), audio는 ES2002a 1회차만 있어 해당 범위만 답변. `project_id` 스코프가 투입 범위에 맞춰 의도대로 동작.

### 10-6. 포트폴리오 시사점

1. **교차 회차 GraphRAG가 실제로 가치를 만든다**: 단일 회차 요약 도구가 못 하는 "의사결정 지연 패턴", "기능 요구사항의 진화", "참석자 역할 분화"를 실증.
2. **STT 오류의 downstream 영향이 관측 가능**: Craig/Greg 대비는 "텍스트 경로는 ground truth, 오디오 경로는 STT 품질에 의존"이라는 데모 포인트를 데이터로 뒷받침.
3. **숫자·결정의 복원력**: WER 30%에도 핵심 수치가 살아남는다는 건 구조화 추출 방식의 강점.
4. **개선 여지**: (a) Person 엔티티의 fuzzy matching으로 Greg≈Craig 병합 가능성, (b) AMI `ihm` 4채널을 화자별로 따로 STT 돌리면 Deletion 535개 대부분이 회수될 것.

### 10-7. 재현 스크립트

| 스크립트 | 목적 |
|---|---|
| `tests/fetch_ami_es2002.py` | HF 스트리밍 + 시리즈 일관 speaker 매핑으로 4회차 트랜스크립트 생성 |
| `tests/run_ami_text.py` | ES2002a~d `/process-text` 순차 투입 |
| `tests/verify_ami_text.py` | Neo4j 교차 연결 검증 + 리모컨 설계 흐름 질의 |
| `tests/qa_ami_text.py` | Phase 2 연속성 3개 질문 |
| `tests/run_ami_audio.py` | ES2002a.Mix-Headset.wav `/stt` 투입 + 폴링 |
| `tests/phase4_eval.py` | WER 측정 + 텍스트/오디오 프로젝트 교차 질의 |

---

## 11. 후속 개선 요약 — 결과와 해석

10장의 실험 결과에서 드러난 한계를 반영해 두 가지 개선을 추가했습니다. 구현 상세 대신 **왜 했는지와 무엇이 달라졌는지**에 집중합니다.

### 11-1. 임베딩 기반 이름 정규화 — Craig/Greg 오인식 대응

**왜**: Phase 4에서 Whisper가 `Craig`을 `Greg`로 오인식했고, 이 오류가 그래프의 Speaker 노드로 그대로 저장되어 `/agents` 답변까지 전파됐습니다. 텍스트 경로에서는 "이전 회차 이름 목록을 시스템 프롬프트에 주입"하는 방식으로 Claude가 같은 이름을 재사용했지만, STT 노이즈가 들어가면 이 장치만으론 부족했습니다.

**무엇**: 그래프에 Speaker/Topic/Entity를 쓰기 **직전** 단계에서, 같은 `project_id`의 기존 이름들과 다국어 문장 임베딩 유사도를 비교하는 safety net을 추가했습니다. 임계값을 카테고리별로 차등 운영합니다 — Speaker는 **0.92** (동명이인 오병합 방지), Entity 0.88, Topic 0.85.

**해석**: LLM 프롬프트 지시에만 의존하던 정규화를 **결정론적 safety net**으로 이중화한 것입니다. 면접 관점에서 가치는 "작동하는 기능을 구현했다"가 아니라 **"Phase 4에서 관측된 실패를 다음 sprint에 구조적 개선으로 연결했다"** 는 반복 개선 사이클 자체입니다. "Craig ≠ Greg 병합되지 않음"을 회귀 테스트로 고정해 같은 실패가 다시 일어나지 않도록 했고, end-to-end 재검증은 Claude API 비용 이유로 다음 세션에 유보했습니다.

### 11-2. Obsidian + Notion 병행 출력 — 개인·팀 시나리오 동시 지원

**왜**: Obsidian vault는 개인 지식베이스로 강하지만 팀 공유·권한 관리에는 약합니다. 반대로 Notion은 팀 공유·SaaS UX가 강하지만 마크다운 파이프라인과는 자연스럽게 연결되지 않습니다. 두 도구가 대립하는 게 아니라 상호보완적이라는 점을 포트폴리오 차원에서 보여주고 싶었습니다.

**무엇**: 기존 Obsidian writer를 **전혀 건드리지 않고** Notion database 출력을 옵션으로 추가했습니다. 첫 호출 시 부모 페이지 아래에 database가 자동 생성되고, 회의록은 callout·toggle·to-do 블록으로 가독성 있게 렌더링됩니다. `NOTION_ENABLED=false`거나 토큰이 없거나 API 오류가 나도 Obsidian·Neo4j 경로는 영향 없이 동작합니다.

**해석**: 범용 회의 SaaS와의 비교 표에 **"출력 이중화"** 라는 축을 추가할 수 있게 됐습니다. Clova Note·Notta·Otter는 모두 단일 저장소이고, 이 프로젝트는 "같은 파이프라인에서 로컬 백업과 팀 공유 SaaS에 동시에 기록"할 수 있다는 점이 구조적 차별점입니다. 실제 Notion 페이지 렌더링은 현재 단위 테스트(Mock 기반 20개)로만 검증됐으며, 실 API 호출 검증은 사용자가 토큰을 넣은 뒤 로컬에서 확인 가능합니다.

---

## 12. 포트폴리오 포지셔닝 — 이 프로젝트가 보여주는 역량

범용 회의록 도구(Clova Note, Notta, Otter 등)와 비교했을 때 이 프로젝트는 **범주 자체가 다릅니다**. SaaS 도구는 "회의 하나를 예쁘게 저장"에 최적화되어 있고, 이 프로젝트는 **"여러 회의가 누적되면서 만들어지는 프로젝트 수준의 맥락"** 에 집중합니다.

### 12-1. 면접에서 쓸 수 있는 한 줄 요약

> "범용 회의 요약 도구는 개별 회의의 품질에 집중합니다. 저는 **4주차 프로젝트에서 결정이 어떻게 번복되고 진화했는지**를 추적할 수 있는 '지식 인프라'를 GraphRAG로 구현했습니다. AMI 코퍼스의 리모컨 디자인 4회차로 검증했고, 3개의 전문가 에이전트 병렬 구조가 단일 LLM 요약이 놓치는 교차 회차 인과 관계를 포착합니다."

### 12-2. 이 프로젝트가 증명하는 엔지니어링 역량

| 역량 | 증거 |
|---|---|
| **스키마 설계·리팩터링** | 처음에는 Speaker/Topic/Entity를 `(name, meeting_id)`로 고정 → 회차 간 병합 안 되는 근본 한계 발견 → `(name, project_id)` 글로벌 + 회차 연결 엣지 4종으로 리팩터링 → AMI 4회차에서 의도대로 동작 확인. **문제 발견 → 원인 분석 → 재설계 → 검증** 의 전 사이클. |
| **LLM 도구 사용 (tool_use)** | Claude tool_use로 구조화 추출 2-pass 구성. 1차 결과를 2차 프롬프트에 컨텍스트로 재주입하여 관계 추출 정확도 확보. 시스템 프롬프트에 "이전 회차 이름 목록"을 주입하는 정규화 장치까지. |
| **멀티 에이전트 오케스트레이션** | `asyncio.gather`로 3개 전문가 에이전트 병렬 실행 + Synthesizer 통합. 에이전트별로 Neo4j 쿼리 프로필을 분리(주제 전문가는 2-hop RELATED_TO, 실행 전문가는 ActionItem+Decision, 맥락 전문가는 Speaker+Entity)하여 관점 누락 방지. |
| **GraphRAG 패턴 구현** | Cypher 쿼리 2세트(`BY_MEETING`, `BY_PROJECT`)로 단일 회차·전체 프로젝트 모드 모두 지원. 교차 회차 질의가 실제로 회차별 Decision/ActionItem을 가로질러 답변하는 것을 AMI Phase 2에서 실증. |
| **파이프라인 엔지니어링** | n8n 같은 외부 오케스트레이터를 걷어내고 STT BackgroundTask → extract → graph → Obsidian을 인라인 체이닝. 외부 웹훅 의존성·실패 표면 제거. |
| **실험 기반 반복 개선** | Phase 4에서 Craig/Greg 오인식 관측 → 다음 Sprint에서 임베딩 기반 정규화 구현. "LLM 프롬프트 주입이 약한 환경이 어디인지 데이터로 확인 → 결정론적 개선 추가" 의 반복 주기. |
| **외부 데이터셋 통합** | HuggingFace `edinburghcstr/ami` 데이터셋을 streaming 모드로 스캔, 오디오 컬럼을 `select_columns`로 제외해 torchcodec 의존성 우회, `speaker_id`를 발화 패턴으로 실명과 매핑하는 디버깅 스크립트 작성. |
| **성능 평가** | `jiwer`로 WER 측정, 텍스트·오디오 프로젝트에 동일 질문을 던져 답변 차이를 비교, "STT 품질이 GraphRAG 답변 품질에 미치는 영향"을 실증. |
| **테스트·CI** | 61개 유닛 테스트(정규화 mock, Obsidian writer, Cypher 파라미터 정합성) + GitHub Actions CI 워크플로(경량 의존성만 설치, `NORMALIZE_DISABLE` + 더미 env로 외부 서비스 없이 통과). |
| **문서화** | README(벤치마크 표, Mermaid 다이어그램, 한계 명시), REPORT(Phase별 실험 결과 + 수치), CLAUDE(프로젝트 컨텍스트), .env.example, gitignore. 포트폴리오로서의 완성도. |

### 12-3. 솔직한 한계 — 면접에서 먼저 언급하는 게 유리

- **한국어 STT 품질은 Clova Note에 못 미침** — Whisper는 범용 다국어라 한국어 특화 엔진의 품질을 따라갈 수 없습니다. 한국어가 중심이면 STT를 네이버 CLOVA Speech API로 교체하는 게 현실적.
- **화자 분리(diarization) 미지원** — 현재 Mix 채널 하나로 STT를 돌리고 Claude가 맥락으로만 화자를 추정합니다. `pyannote.audio` 통합이 가장 가치 있는 다음 개선입니다.
- **실시간 녹음·모바일·타임스탬프 링크 없음** — 범용 SaaS 대비 UX 기능 대부분 부재. 의도적 범위 제한 (지식 인프라 vs 녹음기).
- **실제 재검증 보류** — 임베딩 정규화의 end-to-end 효과는 단위 테스트로만 검증됐고, AMI 재투입 검증은 비용 이유로 다음 세션으로 연기됐습니다.

---

## 13. 요약

| 항목 | 내용 |
|------|------|
| **프로젝트명** | Meeting Summarizer + GraphRAG Expert Panel |
| **핵심 기능** | 회의 텍스트/오디오 → AI 구조화 추출 → 지식 그래프(project_id 스코프 글로벌) → 멀티 에이전트 Q&A → Obsidian 노트 |
| **총 코드량** | 약 3,000줄 (리팩터링 + 실험 스크립트 + 정규화 + Notion 통합 + 유닛 테스트 포함) |
| **주요 기술** | FastAPI, Claude Sonnet 4.6 (tool_use), Neo4j, faster-whisper, sentence-transformers, notion-client, HuggingFace datasets, jiwer, pytest, GitHub Actions |
| **검증 상태** | KR-204 4주차 + AMI ES2002 4회차 텍스트 경로 + ES2002a 오디오 경로 E2E 통과, **83 유닛 테스트 (81 pass + 2 skip) · GitHub Actions CI success** |
| **핵심 성과** | (1) 회차 간 Speaker/Topic/Entity 공유 병합, (2) GraphRAG 교차 회차 질의로 "결정 번복·진화·갈등" 추적, (3) STT→그래프 품질 전파 실증, (4) 임베딩 정규화 반복 개선, (5) README 시각화·한계 명시·CI 배지, (6) **Obsidian + Notion 병행 출력 (database 자동 생성)** |
| **GitHub** | [tkddnjs-dlqslek/meeting-summarizer-graphrag](https://github.com/tkddnjs-dlqslek/meeting-summarizer-graphrag) |
