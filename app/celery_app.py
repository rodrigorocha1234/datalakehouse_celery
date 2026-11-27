import os
from celery import Celery

BROKER_URL = os.getenv(
    "CELERY_BROKER_URL",
    "amqp://celery_news:123456@rabbitmq:5672/news_lakehouse",
)
RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "rpc://")

celery_app = Celery(
    "news_lakehouse",
    broker=BROKER_URL,
    backend=RESULT_BACKEND,
)

celery_app.conf.update(
    timezone=os.getenv("TZ", "America/Sao_Paulo"),
    enable_utc=True,
    task_default_queue="rss_ingestion",
    task_routes={
        "celery_app.ingest_rss": {"queue": "rss_ingestion"},
        "celery_app.processar_noticia": {"queue": "processar_noticia"},
        "celery_app.monitorar_pipeline": {"queue": "fila_monitoramento"},
    },
)


@celery_app.task(name="celery_app.ingest_rss")
def ingest_rss():
    return {"status": "ok", "task": "ingest_rss"}


@celery_app.task(name="celery_app.processar_noticia")
def processar_noticia(payload=None):
    return {"status": "ok", "task": "processar_noticia", "payload": payload}


@celery_app.task(name="celery_app.monitorar_pipeline")
def monitorar_pipeline():
    return {"status": "ok", "task": "monitorar_pipeline"}

