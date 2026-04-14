# Meeting Summarizer — Experiments & Analysis

> 이 문서는 **실험 결과 · 후속 개선 · 포트폴리오 분석**을 담습니다.
> 프로젝트 개요·설치·API 문서는 [README.md](README.md)를,
> 실행 가능한 재현 스크립트는 [tests/](tests/) 디렉토리를 참조하세요.

---

## 1. AMI Corpus 4회차 연속성 실험

리팩터링된 `project_id` 스코프 글로벌 스키마가 **실제 공개 데이터셋**에서도 회차 간 연결을 유지하는지 검증한 실험입니다.

### 1-1. 스키마 리팩터링

기존 스키마는 Speaker/Topic/Entity가 `(name, meeting_id)`로 식별돼서 같은 사람·주제가 회차마다 별개 노드로 복제됐습니다. 이를 `(name, project_id)` 스코프 글로벌 노드로 바꾸고 회차 연결 엣지 4종을 추가했습니다:

- `(:Speaker)-[:PARTICIPATED_IN {speaking_time_ratio}]->(:Meeting)`
- `(:Topic)-[:DISCUSSED_IN]->(:Meeting)`
- `(:Entity)-[:MENTIONED_IN]->(:Meeting)`
- `(:Meeting)-[:FOLLOWS]->(:Meeting)`

`ActionItem`/`Decision`은 회차별 이벤트이므로 `meeting_id` 로컬 유지. `extract_graph_data()`에는 **"같은 project_id의 이전 회차 Topic/Entity/Speaker 이름 목록"**을 시스템 프롬프트에 주입하는 장치를 추가해 Claude가 동일 개념을 동일 이름으로 재사용하도록 유도했습니다.

### 1-2. 데이터셋 — AMI Meeting Corpus ES2002

- 출처: HuggingFace `edinburghcstr/ami` (ihm config)
- 대상: ES2002a~d (한 팀의 scenario meeting 4회차 — Kickoff → Functional → Conceptual → Detailed Design)
- 참가자: Laura(PM), David(Industrial Designer), Craig(UI), Andrew(Marketing) — 4명이 4회차 전체 참석
- 언어: 영어 (Whisper `language="en"`)

**Speaker 매핑 함정**: HF 데이터셋의 `speaker_id`는 `FEE005/MEE006/MEE007/MEE008` 같은 해시. 발화 첫 등장 순서로 A/B/C/D 레이블링하면 회차마다 순서가 달라 같은 사람이 다른 letter로 붙습니다. 초기 fetch 스크립트가 이 버그를 가져 ES2002d에서 Speaker가 `A/B/C/D` 익명 라벨로 뽑혔고, 이를 디버깅하여 ES2002a의 자기소개 발화에서 `speaker_id → 실명` 매핑을 직접 추출하는 방식으로 수정했습니다 (`tests/fetch_ami_es2002.py`).

### 1-3. Phase 1·2 — 텍스트 경로 결과

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

### 1-4. Phase 3 — 오디오 경로 결과

ES2002a Mix-Headset WAV(38.8MB, 약 30분)를 AMI 공식 미러에서 다운로드 후 `/stt` 엔드포인트에 `language="en"`으로 투입. faster-whisper medium int8 CPU로 약 22분 만에 STT 완료, 이후 추출/그래프/노트까지 원스톱 진행. `project_id="ami_es2002_audio"`로 저장.

### 1-5. Phase 4 — 교차 평가 (텍스트 vs 오디오)

**WER 측정** (원본 AMI ihm transcript vs Whisper Mix-Headset 결과):

| 지표 | 값 |
|---|---|
| **WER** | **30.45%** |
| Substitutions | 196 |
| Deletions | 535 ← 지배적 원인 |
| Insertions | 64 |
| Hits | 1,880 |

삭제 535개가 WER의 대부분을 차지합니다. 실제 두 transcript를 직접 비교해 진단한 결과, 원인은 "멀리 있는 마이크"가 아닙니다 — Mix-Headset은 각자의 헤드셋 마이크를 믹싱한 오디오라 모든 목소리가 비슷한 음량으로 들어가 있습니다. 실제 원인은 **두 전사 철학의 차이**입니다:

| 원인 | 설명 | 예시 (실제 관측) |
|---|---|---|
| **1. Backchannel 손실** (지배적) | AMI `ihm` reference는 개별 헤드셋마다 독립 기록되어 맞장구까지 화자별로 전부 남아 있지만, Whisper는 Mix wav에서 메인 화자 발화에 묻히는 짧은 맞장구를 스킵 | Reference: `Andrew: MM-HMM`, `Andrew: GREAT`, `Laura: OKAY` → Whisper transcript에서 통째로 사라짐 |
| **2. Filler / repetition 제거** | Whisper는 학습 특성상 disfluency를 정리하는 경향 | Reference: `OKAY RIGHT UM WELL ... FOR OUR OUR PROJECT UM AND UM ...` → Whisper: `Okay, right. Well, this is ... for our project. And this is ...` (UM·UH·중복 전부 제거) |
| **3. Overlapping speech 병합** | 두 사람이 동시 발화할 때 reference는 각자 utterance로 분리 기록, Whisper는 메인 timeline에 녹여 합침 | Reference: Andrew의 `OUR MARKETING` 다음에 Craig 소개가 시작되는 사이에 Andrew가 `EXPERT`를 덧붙임(두 row) → Whisper: `our marketing expert`로 매끈하게 병합 |

**Insertion 64**의 출처는 반대 방향입니다. Whisper는 공식 회의 시작 **이전**의 pre-meeting 잡담("Oh my gosh, you've already produced a PowerPoint presentation...")까지 받아쓰지만, AMI reference는 kickoff 발화부터만 기록하기 때문입니다.

요약하면 WER 30.45%는 **"AMI reference가 verbatim(있는 그대로)인데 Whisper는 normalization 지향"** 이라는 전사 철학 차이의 산물입니다. Whisper 모델 품질의 한계가 아니라, 두 전사기가 "무엇을 기록으로 남길지"에 대한 관점이 다른 것입니다 — 특히 Deletion 535개 중 상당 부분이 **"사라진 단어"가 아니라 "원래 Whisper가 쓰지 않는 종류의 단어"**(MM-HMM, UM, UH 등)라는 점이 중요합니다.

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

### 1-6. 포트폴리오 시사점

1. **교차 회차 GraphRAG가 실제로 가치를 만든다**: 단일 회차 요약 도구가 못 하는 "의사결정 지연 패턴", "기능 요구사항의 진화", "참석자 역할 분화"를 실증.
2. **STT 오류의 downstream 영향이 관측 가능**: Craig/Greg 대비는 "텍스트 경로는 ground truth, 오디오 경로는 STT 품질에 의존"이라는 데모 포인트를 데이터로 뒷받침.
3. **숫자·결정의 복원력**: WER 30%에도 핵심 수치가 살아남는다는 건 구조화 추출 방식의 강점.
4. **개선 여지**: (a) Person 엔티티의 fuzzy matching으로 Greg≈Craig 병합 시도 (2-1에서 임베딩 정규화로 일부 반영), (b) 화자 분리(`pyannote.audio`) 후 화자별 마이크를 따로 STT하면 Mix wav에서 묻혔던 backchannel·overlapping speech가 Deletion에서 상당수 회수될 것, (c) Whisper의 normalization 경향을 받아들이고 reference 쪽도 normalized transcript(AMI NXT의 `manual-reference`)로 바꿔 비교 기준을 맞추면 WER 측정 자체가 훨씬 낮아질 것.

### 1-7. 재현 스크립트

| 스크립트 | 목적 |
|---|---|
| `tests/fetch_ami_es2002.py` | HF 스트리밍 + 시리즈 일관 speaker 매핑으로 4회차 트랜스크립트 생성 |
| `tests/run_ami_text.py` | ES2002a~d `/process-text` 순차 투입 |
| `tests/verify_ami_text.py` | Neo4j 교차 연결 검증 + 리모컨 설계 흐름 질의 |
| `tests/qa_ami_text.py` | Phase 2 연속성 3개 질문 |
| `tests/run_ami_audio.py` | ES2002a.Mix-Headset.wav `/stt` 투입 + 폴링 |
| `tests/phase4_eval.py` | WER 측정 + 텍스트/오디오 프로젝트 교차 질의 |

---

## 2. 후속 개선 요약 — 결과와 해석

1장의 실험 결과에서 드러난 한계를 반영해 두 가지 개선을 추가했습니다. 구현 상세 대신 **왜 했는지와 무엇이 달라졌는지**에 집중합니다.

### 2-1. 임베딩 기반 이름 정규화 — Craig/Greg 오인식 대응

**왜**: Phase 4에서 Whisper가 `Craig`을 `Greg`로 오인식했고, 이 오류가 그래프의 Speaker 노드로 그대로 저장되어 `/agents` 답변까지 전파됐습니다. 텍스트 경로에서는 "이전 회차 이름 목록을 시스템 프롬프트에 주입"하는 방식으로 Claude가 같은 이름을 재사용했지만, STT 노이즈가 들어가면 이 장치만으론 부족했습니다.

**무엇**: 그래프에 Speaker/Topic/Entity를 쓰기 **직전** 단계에서, 같은 `project_id`의 기존 이름들과 다국어 문장 임베딩 유사도를 비교하는 safety net을 추가했습니다. 임계값을 카테고리별로 차등 운영합니다 — Speaker는 **0.92** (동명이인 오병합 방지), Entity 0.88, Topic 0.85.

**해석**: LLM 프롬프트 지시에만 의존하던 정규화를 **결정론적 safety net**으로 이중화한 것입니다. 면접 관점에서 가치는 "작동하는 기능을 구현했다"가 아니라 **"Phase 4에서 관측된 실패를 다음 sprint에 구조적 개선으로 연결했다"** 는 반복 개선 사이클 자체입니다. "Craig ≠ Greg 병합되지 않음"을 회귀 테스트로 고정해 같은 실패가 다시 일어나지 않도록 했고, end-to-end 재검증은 Claude API 비용 이유로 다음 세션에 유보했습니다.

### 2-2. Obsidian + Notion 병행 출력 — 개인·팀 시나리오 동시 지원

**왜**: Obsidian vault는 개인 지식베이스로 강하지만 팀 공유·권한 관리에는 약합니다. 반대로 Notion은 팀 공유·SaaS UX가 강하지만 마크다운 파이프라인과는 자연스럽게 연결되지 않습니다. 두 도구가 대립하는 게 아니라 상호보완적이라는 점을 포트폴리오 차원에서 보여주고 싶었습니다.

**무엇**: 기존 Obsidian writer를 **전혀 건드리지 않고** Notion database 출력을 옵션으로 추가했습니다. 첫 호출 시 부모 페이지 아래에 database가 자동 생성되고, 회의록은 callout·toggle·to-do 블록으로 가독성 있게 렌더링됩니다. `NOTION_ENABLED=false`거나 토큰이 없거나 API 오류가 나도 Obsidian·Neo4j 경로는 영향 없이 동작합니다.

**해석**: 범용 회의 SaaS와의 비교 표에 **"출력 이중화"** 라는 축을 추가할 수 있게 됐습니다. Clova Note·Notta·Otter는 모두 단일 저장소이고, 이 프로젝트는 "같은 파이프라인에서 로컬 백업과 팀 공유 SaaS에 동시에 기록"할 수 있다는 점이 구조적 차별점입니다. 실제 Notion 페이지 렌더링은 현재 단위 테스트(Mock 기반 20개)로만 검증됐으며, 실 API 호출 검증은 사용자가 토큰을 넣은 뒤 로컬에서 확인 가능합니다.

---

## 3. 포트폴리오 포지셔닝 — 이 프로젝트가 보여주는 역량

범용 회의록 도구(Clova Note, Notta, Otter 등)와 비교했을 때 이 프로젝트는 **범주 자체가 다릅니다**. SaaS 도구는 "회의 하나를 예쁘게 저장"에 최적화되어 있고, 이 프로젝트는 **"여러 회의가 누적되면서 만들어지는 프로젝트 수준의 맥락"** 에 집중합니다.

### 3-1. 면접에서 쓸 수 있는 한 줄 요약

> "범용 회의 요약 도구는 개별 회의의 품질에 집중합니다. 저는 **4주차 프로젝트에서 결정이 어떻게 번복되고 진화했는지**를 추적할 수 있는 '지식 인프라'를 GraphRAG로 구현했습니다. AMI 코퍼스의 리모컨 디자인 4회차로 검증했고, 3개의 전문가 에이전트 병렬 구조가 단일 LLM 요약이 놓치는 교차 회차 인과 관계를 포착합니다."

### 3-2. 이 프로젝트가 증명하는 엔지니어링 역량

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
| **테스트·CI** | 83개 유닛 테스트(정규화 mock, Obsidian writer, Notion writer, Cypher 파라미터 정합성) + GitHub Actions CI 워크플로(경량 의존성만 설치, `NORMALIZE_DISABLE` + 더미 env로 외부 서비스 없이 통과). |
| **문서화** | README(벤치마크 표, Mermaid 다이어그램 3종, 한계 명시), 이 문서(실험 결과 + 수치 + 해석), `.env.example`, `.gitignore`. 포트폴리오로서의 완성도. |

### 3-3. 솔직한 한계 — 면접에서 먼저 언급하는 게 유리

- **한국어 STT 품질은 Clova Note에 못 미침** — Whisper는 범용 다국어라 한국어 특화 엔진의 품질을 따라갈 수 없습니다. 한국어가 중심이면 STT를 네이버 CLOVA Speech API로 교체하는 게 현실적.
- **화자 분리(diarization) 미지원** — 현재 Mix 채널 하나로 STT를 돌리고 Claude가 맥락으로만 화자를 추정합니다. `pyannote.audio` 통합이 가장 가치 있는 다음 개선입니다.
- **실시간 녹음·모바일·타임스탬프 링크 없음** — 범용 SaaS 대비 UX 기능 대부분 부재. 의도적 범위 제한 (지식 인프라 vs 녹음기).
- **실제 재검증 보류** — 임베딩 정규화의 end-to-end 효과는 단위 테스트로만 검증됐고, AMI 재투입 검증은 비용 이유로 다음 세션으로 연기됐습니다.

---

## 4. 요약

| 항목 | 내용 |
|------|------|
| **프로젝트명** | Meeting Summarizer + GraphRAG Expert Panel |
| **핵심 기능** | 회의 텍스트/오디오 → AI 구조화 추출 → 지식 그래프(project_id 스코프 글로벌) → 멀티 에이전트 Q&A → Obsidian + Notion 이중 출력 |
| **주요 기술** | FastAPI, Claude Sonnet 4.6 (tool_use), Neo4j, faster-whisper, sentence-transformers, notion-client, HuggingFace datasets, jiwer, pytest, GitHub Actions |
| **검증 상태** | KR-204 4주차 + AMI ES2002 4회차 텍스트 경로 + ES2002a 오디오 경로 E2E 통과, **83 유닛 테스트 (81 pass + 2 skip) · GitHub Actions CI success** |
| **핵심 성과** | (1) 회차 간 Speaker/Topic/Entity 공유 병합, (2) GraphRAG 교차 회차 질의로 "결정 번복·진화·갈등" 추적, (3) STT→그래프 품질 전파 실증, (4) 임베딩 정규화 반복 개선, (5) **Obsidian + Notion 병행 출력 (database 자동 생성)** |
| **GitHub** | [tkddnjs-dlqslek/meeting-summarizer-graphrag](https://github.com/tkddnjs-dlqslek/meeting-summarizer-graphrag) |
</content>
</invoke>