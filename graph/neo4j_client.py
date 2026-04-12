import os
from neo4j import AsyncGraphDatabase, AsyncDriver
from dotenv import load_dotenv

load_dotenv()

_driver: AsyncDriver | None = None


async def get_driver() -> AsyncDriver:
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(os.getenv("NEO4J_USERNAME"), os.getenv("NEO4J_PASSWORD")),
        )
    return _driver


async def close_driver():
    global _driver
    if _driver:
        await _driver.close()
        _driver = None


async def verify_connectivity():
    driver = await get_driver()
    await driver.verify_connectivity()


async def execute_query(cypher: str, params: dict = None) -> list[dict]:
    driver = await get_driver()
    db = os.getenv("NEO4J_DATABASE", "neo4j")
    async with driver.session(database=db) as session:
        result = await session.run(cypher, params or {})
        return [dict(record) async for record in result]


async def execute_write(cypher: str, params: dict = None):
    driver = await get_driver()
    db = os.getenv("NEO4J_DATABASE", "neo4j")
    async with driver.session(database=db) as session:
        await session.run(cypher, params or {})


async def init_constraints():
    """스키마 초기화 — 앱 시작 시 1회 실행.

    project_id 스코프 글로벌 노드 (Speaker/Topic/Entity)와 meeting_id 로컬 노드
    (ActionItem/Decision) 체계에 맞춰 유니크 제약을 재설정한다. 과거 스키마
    (meeting_id 박힌 Speaker/Topic)의 제약이 남아 있으면 제거한다.
    """
    # 과거 스키마 제약 제거 (존재할 때만)
    legacy = [
        "DROP CONSTRAINT speaker_unique IF EXISTS",
        "DROP CONSTRAINT topic_unique IF EXISTS",
        "DROP CONSTRAINT action_unique IF EXISTS",
        "DROP INDEX entity_meeting IF EXISTS",
        "DROP INDEX decision_meeting IF EXISTS",
    ]
    for cypher in legacy:
        try:
            await execute_write(cypher)
        except Exception:
            pass

    constraints = [
        "CREATE CONSTRAINT meeting_unique IF NOT EXISTS FOR (m:Meeting) REQUIRE m.meeting_id IS UNIQUE",
        "CREATE CONSTRAINT speaker_global IF NOT EXISTS FOR (s:Speaker) REQUIRE (s.name, s.project_id) IS UNIQUE",
        "CREATE CONSTRAINT topic_global IF NOT EXISTS FOR (t:Topic) REQUIRE (t.name, t.project_id) IS UNIQUE",
        "CREATE CONSTRAINT entity_global IF NOT EXISTS FOR (e:Entity) REQUIRE (e.name, e.project_id) IS UNIQUE",
        "CREATE CONSTRAINT action_local IF NOT EXISTS FOR (a:ActionItem) REQUIRE (a.description, a.meeting_id) IS UNIQUE",
        "CREATE CONSTRAINT decision_local IF NOT EXISTS FOR (d:Decision) REQUIRE (d.description, d.meeting_id) IS UNIQUE",
        "CREATE INDEX meeting_project IF NOT EXISTS FOR (m:Meeting) ON (m.project_id)",
    ]
    for cypher in constraints:
        await execute_write(cypher)
