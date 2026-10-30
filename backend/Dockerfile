FROM python:3.11-slim
WORKDIR /app
ENV CHROMA_PERSIST_DIRECTORY=/data/chroma
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
