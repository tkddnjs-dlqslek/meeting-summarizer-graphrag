---
name: meeting-analyzer
description: 회의록 텍스트를 Neo4j 지식 그래프로 구조화하고 GraphRAG 전문가 패널로 질의응답합니다. 같은 project_id로 여러 회의를 누적하면 회차 간 결정 번복·주제 진화·참석자 입장 변화를 추적할 수 있습니다.
---

# Meeting Analyzer Skill

회의록을 **Neo4j 지식 그래프 + GraphRAG**로 분석하는 스킬입니다.

## 전제조건

이 스킬을 쓰려면 먼저 FastAPI 백엔드가 `http://localhost:8000`에서 실행 중이어야 합니다:

```bash
cd /path/to/meeting-summarizer-graphrag
python -m uvicorn api.main:app --port 8000
```

그리고 `.env`에 `ANTHROPIC_API_KEY`, `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`가 설정돼 있어야 합니다.

## 언제 사용하나

사용자가 아래와 같이 말할 때:

- "이 회의록 분석해줘"
- "[프로젝트명]의 지난 회의 요약해줘"
- "[프로젝트명]에서 결정이 어떻게 번복됐나 보여줘"
- "이 회의에서 누가 어떤 주제를 주도했지?"
- "지난 4주간 이 주제에 대해 어떻게 논의했어?"
- "회의 간 연결된 결정 추적해줘"

## 주요 엔드포인트

### 1. 회의록 투입 (텍스트 경로)

`POST /process-text`

```json
{
  "meeting_id": "unique-id-v1",
  "transcript": "회의록 전체 텍스트...",
  "title": "회의 제목",
  "date": "2026-04-16",
  "project_id": "my_project",
  "previous_meeting_id": "unique-id-v0"
}
```

**응답**: 참석자·주제·엔티티·결정·액션 자동 추출, Neo4j 그래프 구축, Obsidian + Notion 노트 자동 생성.

`project_id`는 같은 프로젝트의 여러 회의를 묶는 핵심 키입니다. 같은 `project_id`로 회의를 계속 투입하면 Speaker·Topic·Entity가 회차 간에 자동 병합됩니다.

### 2. GraphRAG 전문가 패널 질의

`POST /agents`

```json
{
  "question": "4회차에 걸쳐 어떤 결정이 번복됐나?",
  "project_id": "my_project"
}
```

또는 특정 회의 하나만:

```json
{
  "question": "오늘 회의에서 결정된 액션 아이템은?",
  "meeting_id": "unique-id-v1"
}
```

**응답 구조**:

- `final_answer`: Synthesizer가 통합한 최종 답변 (bullet + 인사이트 형식, 한국어 해요체)
- `agent_topic` / `agent_action` / `agent_context`: 3명의 전문가 개별 분석
- `meeting_id` / `project_id`: 질의 스코프

### 3. 오디오 경로 (faster-whisper STT)

`POST /stt` (multipart)

```
file: audio.wav
project_id: my_project
language: ko (또는 en, 자동 감지면 생략)
previous_meeting_id: (선택)
```

**응답**: `job_id` 반환. `GET /stt/status/{job_id}`로 폴링.

## 사용 예시

### 시나리오 1 — 단일 회의 분석

사용자: "이 회의록 분석해줘 [붙여넣기]"

```
POST /process-text
{
  "meeting_id": "random-uuid",
  "transcript": "{붙여넣은 내용}",
  "project_id": "default"
}
```

응답의 `summary`, `note_path`, `notion_url`을 사용자에게 보고.

### 시나리오 2 — 프로젝트 지속 추적

사용자가 "같은 프로젝트의 N차 회의야"라고 말하면, 이전 meeting_id를 조회 후:

```
GET /meetings  → 같은 project_id의 이전 회차 찾기
POST /process-text
{
  "project_id": "{기존 프로젝트 ID}",
  "previous_meeting_id": "{직전 회차 ID}",
  ...
}
```

### 시나리오 3 — 교차 회차 질의

사용자: "이 프로젝트 전체에서 박지훈이 뭘 맡았는지 알려줘"

```
POST /agents
{
  "question": "박지훈이 맡은 액션 아이템과 담당한 주제는?",
  "project_id": "{프로젝트 ID}"
}
```

`final_answer`를 그대로 사용자에게 전달. 필요하면 `agent_action` (실행 전문가)의 세부 분석도 함께.

## 핵심 설계 원칙

- **회의 하나 = 단일 요약이 아님**. Speaker·Topic·Entity는 `project_id` 스코프 글로벌 노드로, 같은 프로젝트의 여러 회의에서 자동 병합됨.
- **회차 연결 엣지**: `PARTICIPATED_IN`, `DISCUSSED_IN`, `MENTIONED_IN`, `FOLLOWS`가 회차 간 그래프 탐색을 가능하게 함.
- **로컬 이벤트**: `ActionItem`, `Decision`은 `meeting_id` 로컬이라 "이번 회의에서 결정한 것"과 "저번 회의에서 결정한 것"이 섞이지 않음.

## 참고 리소스

- GitHub: https://github.com/tkddnjs-dlqslek/meeting-summarizer-graphrag
- Live Demo: https://huggingface.co/spaces/sangwongim922/meeting-summarizer-graphrag-demo
- REPORT.md (실험·분석): repository의 REPORT.md
- Swagger UI: http://localhost:8000/docs
