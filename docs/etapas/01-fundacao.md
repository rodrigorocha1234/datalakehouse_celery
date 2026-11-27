# Etapa 1 — Inspeção e fundação

- Ler as três partes das regras de Python anexadas e quaisquer instruções adicionais disponíveis; identificar localização do Docker Compose real; inspecionar `docker compose config`, serviços, imagens, profiles, redes, portas, mounts e secrets, sem derrubar nada.
- Identificar Celery, RabbitMQ, RustFS/MinIO, Trino e PySpark existentes; mapear conflitos e propor reutilização do Compose com serviços **exclusivos**.
- Criar layout `src/enterprise_news/`, `config/`, `tests/`, `.env.example`, base de `pyproject.toml` e documentação de arquitetura C1/C2 inicial sem implementar pipelines.
- Se precisar alterar Compose, adicionar serviços pertinentes sem remover os antigos; bind mounts sempre em `./volumes/enl_*` na raiz do projeto do Compose, `TZ=America/Sao_Paulo`; healthchecks quando suportados.
- Validar sintaxe do Compose e do YAML; executar smoke tests somente dos serviços autorizados e seguros.
- Aceite: inventário, diff do Compose, configurações validadas, isolamento e plano de execução documentados.
- Encerramento: **"Etapa 1 concluída. Deseja avançar para a Etapa 2?"**
