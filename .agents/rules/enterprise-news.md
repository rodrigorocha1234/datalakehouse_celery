---
description: Regras obrigatórias do agente Enterprise News Lakehouse
activation: always_on
---

# Regras gerais

1. Idioma de comunicação: português brasileiro. Projeto independente de G1 News RAG e de qualquer outro pipeline.
2. Stack obrigatória: Python, Celery, RabbitMQ exclusivo, PostgreSQL operacional exclusivo, object storage compatível com S3, PySpark, Trino, dbt Core, OpenMetadata, Great Expectations, Superset; Medallion Bronze/Silver/Gold. Não introduzir Flink, Airflow ou Dagster.
3. Usar o **Docker Compose existente** como ponto inicial. **Está autorizado alterar ou adicionar serviços no Docker Compose**, inclusive Celery, RabbitMQ, Trino, PySpark e demais dependências da etapa, após inspeção e análise de impacto. Preservar serviços, bancos, redes, dados e containers não relacionados; documentar diff e validar com `docker compose config` antes de subir.
4. **Sempre criar diretórios de volumes bind na raiz do projeto que contém o Compose** (ex.: `./volumes/enl_rabbitmq`, `./volumes/enl_postgres`, `./volumes/enl_storage`). Nunca criar dados persistentes em `/tmp`, em subpastas do código-fonte ou em paths fora da raiz do projeto. Se a convenção existente exigir volumes nomeados, consultar o usuário antes de contrariar esta regra. Não apagar volumes existentes.
5. Definir `TZ=America/Sao_Paulo` nos serviços do projeto; persistir timestamps analíticos em UTC. Não expor senhas em repositório. Criar `.env.example` e usar segredos fora do Git.
6. Antes de qualquer edição, inspecionar `AGENTS.md`, instruções Python e Docker Compose realmente disponíveis; se ausentes, registrar lacuna sem inventar conteúdo. Preservar alterações do usuário.
7. Código **Python 3.11** organizado em `src/enterprise_news/`, com tipagem estrita sem `Any`, identificadores próprios em português, módulos/pacotes de exatamente duas palavras separadas por `_` (respeitadas exceções do ecossistema), encapsulamento adequado, testes pytest e lint. A especificação adaptada para 3.11 e exemplos estão nas três partes de `.agents/rules/padroes-python-parte-*`; lê-las integralmente antes de programar. Não usar `eval` em configuração. Para `@override`, usar `typing_extensions.override`; `typing.final` é nativo; evitar PEP 695 e outras sintaxes de Python 3.12+.
8. Configurar uma ou várias URLs RSS do G1 em `config/g1_rss.yaml` com lista `rss.feeds`; IDs únicos, flags `enabled`, intervalos próprios e validação de URLs. Uma tarefa Celery por feed elegível; meta de 100, não coletar conteúdo fora do RSS sem permissão.
9. Celery + RabbitMQ: filas exclusivas `enl.*`, worker/beat próprios, retries/backoff com jitter, limites de conexão, idempotência, DLQ, controle de concorrência e semântica at-least-once. Preferir group para feeds independentes; chain quando houver dependência; chord só quando indispensável.
10. Dados brutos auditáveis em Bronze, tipagem/deduplicação/quarentena em Silver, fatos/dimensões e marts em Gold. Armazenamento em object storage; não persistir Lakehouse como arquivos locais.
11. OpenMetadata e Superset são entregas reais, não apenas entradas no Compose. Documentar LGPD, retenção, lineage, qualidade, C4, ADRs e runbooks.
12. Cada etapa exige testes verificáveis, relatório objetivo dos comandos e resultados, lista de arquivos alterados e riscos remanescentes. Não declarar serviços funcionais sem executar validação.
13. É proibido iniciar etapa posterior sem autorização explícita do usuário. Se bloqueado, perguntar como proceder e não contornar permissões.
14. Em conflito entre um exemplo de nome em inglês na documentação arquitetural e as regras Python, aplicar nomes em português a identificadores **próprios** de código; preservar nomes de bibliotecas, APIs, serviços, tabelas e interfaces externas quando seu contrato exigir.
