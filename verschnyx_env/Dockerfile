FROM python:3.11-slim

WORKDIR /app

# System-Deps fuer chromadb (SQLite, Build-Tools)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        sqlite3 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ChromaDB-Telemetrie abschalten (behebt den capture()-Bug)
ENV ANONYMIZED_TELEMETRY=false

COPY logic_core.py .
COPY indexer.py .
COPY system_prompt.txt .
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

# Verzeichnisse fuer Laufzeit
RUN mkdir -p /app/library /app/media /app/memory /app/vectorstore

ENTRYPOINT ["./entrypoint.sh"]
