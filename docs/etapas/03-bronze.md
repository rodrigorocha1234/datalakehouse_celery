# Etapa 3 — Bronze, resiliência e persistência

- Conectar object storage S3-compatible dedicado (avaliar RustFS/MinIO disponível); bucket e credenciais exclusivos. Lakehouse nunca como diretório local persistente.
- Persistir payload original, metadados de origem/HTTP, feed_id, batch_id, hash e timestamps UTC em Bronze.
- PostgreSQL exclusivo para runs, feed checkpoints, locks e status; transições de estado consistentes e retomadas após falha.
- Aplicar escrita idempotente, reprocessamento desde Bronze, quarentena inicial e política de retenção documentada.
- Simular worker reiniciado, mensagem redelivered, PUT repetido, feed repetido e falha parcial.
- Aceite: replay e gravações sem duplicidade indevida; nenhuma perda silenciosa; volumes bind somente na raiz do projeto.
- Encerramento: **"Etapa 3 concluída. Deseja avançar para a Etapa 4?"**
