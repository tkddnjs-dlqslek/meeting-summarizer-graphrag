FROM python:3.13-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    anthropic>=0.85.0 \
    neo4j>=5.19.0 \
    python-dotenv>=1.0.0 \
    streamlit>=1.52.2 \
    nest_asyncio>=1.6.0

COPY api/__init__.py api/
COPY api/agents.py api/
COPY graph/__init__.py graph/
COPY graph/neo4j_client.py graph/
COPY graph/cypher_queries.py graph/
COPY app_demo.py .

RUN mkdir -p /app/.streamlit && \
    printf '[server]\nheadless = true\nport = 7860\nenableCORS = false\nenableXsrfProtection = false\n' > /app/.streamlit/config.toml

EXPOSE 7860

CMD ["streamlit", "run", "app_demo.py", "--server.port=7860", "--server.address=0.0.0.0"]
