FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY services/ui /app/services/ui
COPY prompts /app/prompts

ENV PYTHONPATH=/app
ENV API_URL=http://api:8000

EXPOSE 8501
CMD ["streamlit", "run", "services/ui/streamlit_app.py", "--server.address=0.0.0.0", "--server.port=8501"]
