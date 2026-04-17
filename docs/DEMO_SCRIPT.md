# 데모 영상 녹화 스크립트 (Loom 기준, 약 2분 30초)

## 사전 준비

### 1. Loom 설치
- https://www.loom.com/download
- 무료 계정 (구글 로그인 1분)
- **추천 설정**: Screen + Camera off + Mic on (목소리만)

### 2. 녹화 전 브라우저 탭 3개 준비

| 탭 | URL | 역할 |
|---|---|---|
| 1 | https://huggingface.co/spaces/sangwongim922/meeting-summarizer-graphrag-demo | 메인 데모 |
| 2 | https://console.neo4j.io → 인스턴스 → **Open** → Neo4j Browser | 그래프 시각화 |
| 3 | https://github.com/tkddnjs-dlqslek/meeting-summarizer-graphrag | 코드/문서 (마지막에 잠깐) |

### 3. Neo4j Browser 사전 쿼리 준비
Neo4j Browser에 미리 이 쿼리를 복붙해두고 실행까진 하지 마세요 (녹화 중 실행):

```cypher
MATCH (s:Speaker {project_id: "ami_es2002_text"})-[:PARTICIPATED_IN]->(m:Meeting)
OPTIONAL MATCH (t:Topic {project_id: "ami_es2002_text"})-[:DISCUSSED_IN]->(m)
RETURN s, m, t LIMIT 80
```

### 4. HF Space 미리 워밍업
녹화 직전에 HF Space 페이지를 한번 열어두세요 — 콜드 스타트(30~60초)가 녹화 중에 걸리면 안 됨.

---

## 녹화 시나리오 (2분 30초)

### [0:00–0:15] 인트로 (15초)

**화면**: HF Space 메인 화면

**대사**:
> "안녕하세요. 회의록을 **지식 그래프로 구조화**해서 여러 회의를 가로지르는 질의응답을 할 수 있는 **Meeting Summarizer GraphRAG** 프로젝트를 소개합니다. 데모는 허깅페이스 스페이스에 올려놨고, AMI 코퍼스의 리모컨 디자인 4회차 회의로 실시간으로 보여드릴게요."

**액션**: 페이지 스크롤해서 제목·추천 질문 보여주기

---

### [0:15–0:45] GraphRAG 질의 시연 (30초)

**화면**: HF Space, Q&A 탭

**대사**:
> "이 프로젝트의 핵심은 **여러 회의를 가로지르는 질의**입니다. 예를 들어 '4회차에 걸쳐 어떤 결정이 번복됐는지'를 물으면—"

**액션**: 두 번째 추천 질문 **"어떤 결정이 번복됐고 그 이유는?"** 클릭

**대사 (로딩 중, 10초)**:
> "3개의 전문가 에이전트가 **주제·실행·맥락** 관점에서 병렬로 Neo4j 그래프를 탐색하고, Synthesizer가 통합 답변을 만듭니다."

**화면**: 답변 나오면 스크롤하면서 보여주기

---

### [0:45–1:15] 답변 분석 (30초)

**화면**: 답변 내용, 그리고 "전문가 개별 분석 보기" 펼치기

**대사**:
> "답변을 보시면 **배터리에서 키네틱으로 갔다가 다시 배터리로 번복된 과정**, **LCD가 2단계에 걸쳐 제거된 이유** 같은 회차 간 인과 관계가 정확히 추적됩니다. **클로바노트나 Notta 같은 범용 회의록 도구는 하지 못하는 일**이에요. 회의를 하나씩 독립적으로 요약하거든요."

**액션**: 개별 전문가 분석도 살짝 펼쳐서 보여주기

---

### [1:15–1:45] Neo4j 그래프 시각화 (30초)

**화면**: Neo4j Browser 탭으로 전환

**대사**:
> "내부는 이렇게 Neo4j 지식 그래프로 구성돼 있습니다."

**액션**: 준비해둔 Cypher 쿼리 **실행**

**대사 (그래프 렌더링 중)**:
> "4명의 참석자—Laura, Andrew, David, Craig—가 4회차 모두에 참석한 게 **각각 하나의 노드로** 병합돼 있고요, 주제·엔티티도 회차 간에 공유됩니다. 이게 **교차 회차 질의**의 기반이에요."

**액션**: 그래프 노드 드래그해서 구조 보여주기 (10초 정도)

---

### [1:45–2:15] 기술 요약 (30초)

**화면**: GitHub README 탭으로 전환

**대사**:
> "전체 스택은—Claude Sonnet 4.6의 tool_use로 구조화 추출, Neo4j에 project_id 스코프 글로벌 스키마로 저장, 출력은 Obsidian과 Notion에 병행으로 갑니다. Whisper STT는 로컬 faster-whisper로 돌고요. **83개 유닛 테스트와 GitHub Actions CI도 걸려 있습니다**."

**액션**: README의 Mermaid 다이어그램으로 스크롤 (잠깐 보여주기)

---

### [2:15–2:30] 아웃트로 (15초)

**화면**: HF Space 페이지로 다시

**대사**:
> "링크는 설명란에 있고, AMI 4회차 실험 결과와 포트폴리오 포지셔닝은 REPORT.md에 정리했습니다. 감사합니다."

**액션**: Loom 정지

---

## 녹화 팁

- **한 번에 완벽하게 찍으려 하지 마세요.** Loom은 녹화 후 **silence trimming**(침묵 자동 제거) 기능이 있어서 말 사이 뜸을 자동으로 잘라줍니다.
- **화면 전환 시 1초 쉬기** — 편집 때 자연스럽게 붙음.
- **Neo4j 그래프가 느리게 렌더링**되면 미리 한 번 실행해놓고 줌·드래그만 녹화.
- **대사 너무 외우지 말고**, 키 포인트만 기억하고 자연스럽게.

## 녹화 후

1. Loom이 자동으로 링크 생성 → 복사
2. README 상단(제목 아래 "Live Demo" 섹션)에 영상 임베드:

```markdown
## 🎥 Demo Video

[![Watch the demo](https://cdn.loom.com/sessions/thumbnails/YOUR_VIDEO_ID-with-play.gif)](https://www.loom.com/share/YOUR_VIDEO_ID)
```

또는 단순 링크:

```markdown
**[🎥 2분 30초 데모 영상 보기 →](https://www.loom.com/share/YOUR_VIDEO_ID)**
```

녹화가 끝나면 링크만 주세요. README 업데이트는 제가 해드릴게요.
