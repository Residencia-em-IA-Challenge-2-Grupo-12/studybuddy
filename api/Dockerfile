FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ANONYMIZED_TELEMETRY=False

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY demo.py .

# O índice chega montado só leitura em /indice e é copiado para dentro do container ao subir:
# cada ambiente fica com o seu ChromaDB, sem dois processos abrindo o mesmo arquivo SQLite.
ENV CHROMA_DIR=/app/chroma_db
EXPOSE 8000
CMD ["sh", "-c", "cp -r /indice/. /app/chroma_db/ && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
