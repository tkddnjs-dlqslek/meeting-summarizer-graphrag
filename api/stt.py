import os
import asyncio
import tempfile
from datetime import date

from faster_whisper import WhisperModel
from dotenv import load_dotenv

from api.extractor import extract_graph_data
from api.graph_builder import build_graph
from api.obsidian_writer import write_meeting_note
from api.notion_writer import write_meeting_note_to_notion
from graph.neo4j_client import execute_query
from graph import cypher_queries as Q

load_dotenv()

_model: WhisperModel | None = None

# {job_id: {status, progress, transcript, meeting_id, error}}
job_store: dict[str, dict] = {}


def get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            os.getenv("WHISPER_MODEL", "medium"),
            compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
            device="cpu",
        )
    return _model


def transcribe_file(file_bytes: bytes, filename: str, language: str | None = None) -> str:
    model = get_model()
    lang = language or os.getenv("WHISPER_LANGUAGE", "ko")
    suffix = os.path.splitext(filename)[-1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        segments, _ = model.transcribe(tmp_path, language=lang, beam_size=5)
        return " ".join(seg.text.strip() for seg in segments)
    finally:
        os.unlink(tmp_path)


async def run_transcription(
    job_id: str,
    file_bytes: bytes,
    filename: str,
    meeting_id: str,
    project_id: str = "default",
    previous_meeting_id: str | None = None,
    language: str | None = None,
):
    job_store[job_id]["status"] = "processing"
    try:
        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(
            None, transcribe_file, file_bytes, filename, language
        )
        job_store[job_id].update({"status": "transcribed", "transcript": transcript})

        title = filename.rsplit(".", 1)[0]
        meeting_date = date.today().isoformat()

        # 같은 project_id의 이전 회차 컨텍스트 조회
        previous_topics = []
        previous_entities = []
        previous_speakers = []
        if project_id and project_id != "default":
            topic_rows = await execute_query(
                Q.PREVIOUS_TOPICS_BY_PROJECT, {"project_id": project_id}
            )
            previous_topics = [r["name"] for r in topic_rows if r.get("name")]
            entity_rows = await execute_query(
                Q.PREVIOUS_ENTITIES_BY_PROJECT, {"project_id": project_id}
            )
            previous_entities = [r["name"] for r in entity_rows if r.get("name")]
            speaker_rows = await execute_query(
                Q.PREVIOUS_SPEAKERS_BY_PROJECT, {"project_id": project_id}
            )
            previous_speakers = [r["name"] for r in speaker_rows if r.get("name")]

        graph_data = await extract_graph_data(
            transcript,
            meeting_id,
            title,
            project_id=project_id,
            previous_topics=previous_topics or None,
            previous_entities=previous_entities or None,
            previous_speakers=previous_speakers or None,
        )
        graph_data["date"] = meeting_date
        if previous_meeting_id:
            graph_data["previous_meeting_id"] = previous_meeting_id

        await build_graph(graph_data)

        stats = await execute_query(Q.GRAPH_STATS, {"meeting_id": meeting_id})
        node_count = sum(r["count"] for r in stats)
        graph_data["node_count"] = node_count
        note_path = write_meeting_note(graph_data)
        notion_url = write_meeting_note_to_notion(graph_data)

        job_store[job_id].update({
            "status": "done",
            "pipeline_result": {
                "meeting_id": meeting_id,
                "project_id": project_id,
                "summary": graph_data.get("summary", ""),
                "node_count": node_count,
                "note_path": note_path,
                "notion_url": notion_url,
            },
        })

    except Exception as e:
        job_store[job_id].update({"status": "error", "error": str(e)})
