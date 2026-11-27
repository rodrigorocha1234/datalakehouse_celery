# Etapa 4 — PySpark, Silver e Gold

- Criar jobs PySpark Bronze → Silver e Silver → Gold, schemas explícitos, tratamento de datas UTC, URLs canônicas, deduplicação e quarentena com motivos.
- Produzir dimensões source/date/category/language, fatos news/feed_execution/data_quality e cinco marts previstos.
- Escrever datasets em Parquet no object storage; avaliar Iceberg em ADR, sem adicioná-lo automaticamente.
- Testes unitários Spark em dados sintéticos, integração incremental, replay, schema drift e qualidade.
- Aceite: datasets reproduzíveis, contagens reconciliadas e reprocessamento seguro.
- Encerramento: **"Etapa 4 concluída. Deseja avançar para a Etapa 5?"**
