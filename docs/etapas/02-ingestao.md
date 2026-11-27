# Etapa 2 — Ingestão assíncrona RSS

- Implementar carregador tipado/validado de `config/g1_rss.yaml` com 1/N feeds, IDs únicos, URLs HTTPS e intervalos por feed. Todo código próprio segue as três partes das regras Python (3.11, português, módulos de duas palavras, sem `Any`).
- Dispatcher elegibilidade por feed, Celery Beat, tarefas individuais e workers isolados; RabbitMQ com `enl.rss.ingestion` e rotas dedicadas.
- HTTP com timeout, conditional GET ETag/Last-Modified, rate limit por domínio; parser RSS robusto; só conteúdo presente no feed.
- Retries exponenciais com jitter, limites, DLX/DLQ, métricas e prevenção de concorrência duplicada por feed; registro operacional PostgreSQL.
- Testes com feeds simulados (sucesso, 304, 429, XML inválido, timeout, duplicado e indisponível).
- Aceite: 1 e N feeds, tarefas independentes, falha isolada, configurações carregadas e logs verificáveis.
- Encerramento: **"Etapa 2 concluída. Deseja avançar para a Etapa 3?"**
