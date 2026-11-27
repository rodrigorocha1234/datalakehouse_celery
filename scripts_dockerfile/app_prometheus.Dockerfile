FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app /app

ENV PYTHONUNBUFFERED=1
ENV PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

RUN mkdir -p /tmp/prometheus

# teste de debug (IMPORTANTE)
RUN which gunicorn || echo "gunicorn not found"

EXPOSE 8000

CMD ["python", "-u", "app.py"]