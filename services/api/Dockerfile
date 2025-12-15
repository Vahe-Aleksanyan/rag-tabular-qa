FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Include the seed Excel data so ingestion works inside the container
COPY data /app/data
COPY prompts /app/prompts
COPY app /app/app
COPY services/api /app/services/api

ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
