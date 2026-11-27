# ADR-001: Formato de Armazenamento Analítico nas Camadas Silver e Gold (Parquet vs. Apache Iceberg)

- **Status**: Aceito (Etapa 4)
- **Data**: 2026-11-26
- **Contexto**: O Enterprise News Lakehouse processa lotes incrementais da camada Bronze (`enl-bronze`) para as camadas Silver (`enl-silver`) e Gold (`enl-gold`) utilizando PySpark sob Object Storage S3-compatible (`rustfs/rustfs:1.0.0-alpha.83`) e consulta via Trino (`trinodb/trino:484`) + dbt Core.

## Opções Avaliadas

1. **Parquet Particionado Idempotente no Object Storage S3** (Padrão adotado):
   - Escrita de datasets Parquet particionados por data (`dt=YYYY-MM-DD`) com chaves determinísticas por `batch_id` e deduplicação por `dedup_hash`.
   - Não exige catálogo REST adicional nem Hive Metastore dedicado para operar com o cluster Spark Standalone (`apache/spark:3.5.6`) e Trino existentes.
2. **Apache Iceberg sobre S3**:
   - Oferece *time travel*, *schema evolution* transacional e *ACID commits* no nível de catálogo.
   - Exige um catálogo de metadados transacional (Iceberg REST Catalog, JDBC Catalog ou Hive Metastore) sincronizado entre os containers `spark-master`/`spark-worker` e `trino`.

## Decisão

Adotar **Parquet particionado idempotente no Object Storage S3** como formato primário nas camadas Silver e Gold nesta fase, mantendo os contratos de schema (`ContratoSchemaMedallion`) explícitos e compatíveis com futura migração transparente para catálogo Iceberg no Trino sem alterar os nomes das 4 dimensões (`dim_source`, `dim_date`, `dim_category`, `dim_language`), 3 fatos (`fact_news`, `fact_feed_execution`, `fact_data_quality`) e 5 marts (`mart_volume_diario`, `mart_desempenho_fontes`, `mart_distribuicao_categorias`, `mart_frescor_ingestao`, `mart_qualidade_dados`).

