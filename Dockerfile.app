# 로컬 풀스택 실행용 (FastAPI + Streamlit)
# HF Space용 경량 Dockerfile과 별도 — 이 파일은 docker-compose.yml이 사용.

FROM python:3.13-slim

WORKDIR /app

# 시스템 의존성 (faster-whisper가 요구)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 코드 복사
COPY api/ api/
COPY graph/ graph/
COPY frontend/ frontend/

# Streamlit 설정
RUN mkdir -p /root/.streamlit && \
    printf '[server]\nheadless = true\nenableCORS = false\nenableXsrfProtection = false\n' > /root/.streamlit/config.toml

EXPOSE 8000 8502
