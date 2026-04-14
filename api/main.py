import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from graph.neo4j_client import verify_connectivity, init_constraints, close_driver, execute_query
from graph import cypher_queries as Q
from api.extractor import extract_graph_data
from api.graph_builder import build_graph
from api.agents import run_expert_panel
from api.obsidian_writer import write_meeting_note
from api.notion_writer import write_meeting_note_to_notion
from api.stt import job_store, run_transcription


# ── 앱 생명주기 ───────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    import asyncio
    try:
        await asyncio.wait_for(verify_connectivity(), timeout=10)
        await init_constraints()
        print("[OK] Neo4j AuraDB connected")
    except Exception as e:
        print(f"[WARN] Neo4j unavailable: {e}")
        print("[WARN] Graph/agents endpoints will fail, but extract/obsidian still work")
    yield
    await close_driver()
    print("[BYE] Neo4j connection closed")


app = FastAPI(
    title="Meeting Summarizer + GraphRAG",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic 모델 ─────────────────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    meeting_id: str
    transcript: str
    title: str = ""
    date: str = ""
    project_id: str = "default"
    previous_meeting_id: str | None = None


class GraphBuildRequest(BaseModel):
    graph_data: dict


class ObsidianWriteRequest(BaseModel):
    meeting_id: str
    title: str = ""
    date: str = ""
    project_id: str = "default"
    summary: str = ""
    speakers: list = []
    topics: list = []
    decisions: list = []
    action_items: list = []
    entities: list = []
    node_count: int = 0
    edge_count: int = 0


class AgentsRequest(BaseModel):
    question: str
    meeting_id: str | None = None
    project_id: str | None = None


# ── STT ───────────────────────────────────────────────────────────────────────

@app.post("/stt")
async def transcribe(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: str = Form("default"),
    previous_meeting_id: str | None = Form(None),
    language: str | None = Form(None),
):
    meeting_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    file_bytes = await file.read()
    job_store[job_id] = {
        "status": "queued",
        "meeting_id": meeting_id,
        "project_id": project_id,
    }
    background_tasks.add_task(
        run_transcription,
        job_id,
        file_bytes,
        file.filename,
        meeting_id,
        project_id,
        previous_meeting_id,
        language,
    )
    return {"job_id": job_id, "meeting_id": meeting_id, "project_id": project_id}


@app.get("/stt/status/{job_id}")
async def stt_status(job_id: str):
    info = job_store.get(job_id)
    if not info:
        raise HTTPException(status_code=404, detail="job not found")
    return info


# ── 텍스트 직접 처리 (오디오 없이 transcript 바로 입력) ──────────────────────

@app.post("/process-text")
async def process_text(req: ExtractRequest):
    """텍스트를 받아 추출→그래프→노트까지 한 번에 수행하는 E2E 엔드포인트.

    같은 project_id의 이전 회차가 DB에 있으면 그 회차의 주제/엔티티/참석자
    이름 목록을 Claude 추출 단계에 주입해, 회차 간 동일 개념이 동일 이름으로
    정규화되도록 유도한다.
    """
    previous_topics = []
    previous_entities = []
    previous_speakers = []
    if req.project_id and req.project_id != "default":
        topic_rows = await execute_query(
            Q.PREVIOUS_TOPICS_BY_PROJECT, {"project_id": req.project_id}
        )
        previous_topics = [r["name"] for r in topic_rows if r.get("name")]
        entity_rows = await execute_query(
            Q.PREVIOUS_ENTITIES_BY_PROJECT, {"project_id": req.project_id}
        )
        previous_entities = [r["name"] for r in entity_rows if r.get("name")]
        speaker_rows = await execute_query(
            Q.PREVIOUS_SPEAKERS_BY_PROJECT, {"project_id": req.project_id}
        )
        previous_speakers = [r["name"] for r in speaker_rows if r.get("name")]

    graph_data = await extract_graph_data(
        req.transcript,
        req.meeting_id,
        req.title,
        project_id=req.project_id,
        previous_topics=previous_topics or None,
        previous_entities=previous_entities or None,
        previous_speakers=previous_speakers or None,
    )
    graph_data["date"] = req.date
    if req.previous_meeting_id:
        graph_data["previous_meeting_id"] = req.previous_meeting_id

    await build_graph(graph_data)

    stats = await execute_query(Q.GRAPH_STATS, {"meeting_id": req.meeting_id})
    node_count = sum(r["count"] for r in stats)
    graph_data["node_count"] = node_count

    note_path = write_meeting_note(graph_data)
    notion_url = write_meeting_note_to_notion(graph_data)
    return {
        "meeting_id": req.meeting_id,
        "project_id": req.project_id,
        "summary": graph_data["summary"],
        "node_count": node_count,
        "note_path": note_path,
        "notion_url": notion_url,
        "graph_data": graph_data,
    }


# ── n8n용 분리 엔드포인트 ─────────────────────────────────────────────────────

@app.post("/extract")
async def extract(req: ExtractRequest):
    graph_data = await extract_graph_data(
        req.transcript,
        req.meeting_id,
        req.title,
        project_id=req.project_id,
    )
    return {"graph_data": graph_data, "summary": graph_data["summary"]}


@app.post("/graph/build")
async def graph_build(req: GraphBuildRequest):
    await build_graph(req.graph_data)
    mid = req.graph_data.get("meeting_id")
    stats = await execute_query(Q.GRAPH_STATS, {"meeting_id": mid})
    node_count = sum(r["count"] for r in stats)
    return {"meeting_id": mid, "node_count": node_count}


@app.post("/obsidian/write")
async def obsidian_write(req: ObsidianWriteRequest):
    note_path = write_meeting_note(req.model_dump())
    return {"file_path": note_path}


# ── GraphRAG 에이전트 ─────────────────────────────────────────────────────────

@app.post("/agents")
async def agents(req: AgentsRequest):
    import traceback
    if not req.meeting_id and not req.project_id:
        raise HTTPException(
            status_code=400,
            detail="meeting_id 또는 project_id 중 하나가 필요합니다.",
        )
    try:
        result = await run_expert_panel(
            req.question,
            meeting_id=req.meeting_id,
            project_id=req.project_id,
        )
        return result
    except Exception as e:
        err = traceback.format_exc()
        with open("agents_error.log", "w", encoding="utf-8") as f:
            f.write(err)
        raise HTTPException(status_code=500, detail=str(e))


# ── 그래프 조회 ───────────────────────────────────────────────────────────────

@app.get("/graph/{meeting_id}")
async def graph_stats(meeting_id: str):
    stats = await execute_query(Q.GRAPH_STATS, {"meeting_id": meeting_id})
    total_nodes = sum(r["count"] for r in stats)
    return {"meeting_id": meeting_id, "nodes_by_label": stats, "total_nodes": total_nodes}


@app.get("/meetings")
async def list_meetings():
    rows = await execute_query(Q.ALL_MEETINGS)
    return {"meetings": rows}


@app.get("/health")
async def health():
    await verify_connectivity()
    return {"status": "ok"}
