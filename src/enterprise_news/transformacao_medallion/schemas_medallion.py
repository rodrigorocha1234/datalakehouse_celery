"""Schemas explícitos e modelos de dados das camadas Silver e Gold (Medallion)."""

from dataclasses import dataclass
from datetime import datetime
from typing import final


@final
@dataclass(frozen=True)
class EspecificacaoColunaSpark:
    """Declaração tipada de uma coluna de schema PySpark / Parquet."""

    nome: str
    tipo_spark: str
    anulavel: bool


@final
@dataclass(frozen=True)
class ContratoSchemaMedallion:
    """Catálogo de schemas explícitos para tabelas Silver e Gold."""

    SCHEMA_SILVER_NOTICIAS: tuple[EspecificacaoColunaSpark, ...] = (
        EspecificacaoColunaSpark("dedup_hash", "STRING", False),
        EspecificacaoColunaSpark("batch_id", "STRING", False),
        EspecificacaoColunaSpark("feed_id", "STRING", False),
        EspecificacaoColunaSpark("guid", "STRING", False),
        EspecificacaoColunaSpark("title", "STRING", False),
        EspecificacaoColunaSpark("canonical_url", "STRING", False),
        EspecificacaoColunaSpark("summary", "STRING", True),
        EspecificacaoColunaSpark("primary_category", "STRING", False),
        EspecificacaoColunaSpark("language_code", "STRING", False),
        EspecificacaoColunaSpark("published_at_utc", "TIMESTAMP", False),
        EspecificacaoColunaSpark("collected_at_utc", "TIMESTAMP", False),
        EspecificacaoColunaSpark("processed_at_utc", "TIMESTAMP", False),
    )

    SCHEMA_FACT_NEWS: tuple[EspecificacaoColunaSpark, ...] = (
        EspecificacaoColunaSpark("news_key", "STRING", False),
        EspecificacaoColunaSpark("source_key", "STRING", False),
        EspecificacaoColunaSpark("date_key", "INTEGER", False),
        EspecificacaoColunaSpark("category_key", "STRING", False),
        EspecificacaoColunaSpark("language_key", "STRING", False),
        EspecificacaoColunaSpark("batch_id", "STRING", False),
        EspecificacaoColunaSpark("title", "STRING", False),
        EspecificacaoColunaSpark("canonical_url", "STRING", False),
        EspecificacaoColunaSpark("published_at_utc", "TIMESTAMP", False),
        EspecificacaoColunaSpark("collected_at_utc", "TIMESTAMP", False),
        EspecificacaoColunaSpark("ingestion_lag_seconds", "DOUBLE", False),
    )


@final
@dataclass(frozen=True)
class RegistroNoticiaSilver:
    """Registro limpo, tipado, com URL canônica e timestamps UTC na camada Silver."""

    dedup_hash: str
    batch_id: str
    feed_id: str
    guid: str
    title: str
    canonical_url: str
    summary: str
    primary_category: str
    language_code: str
    published_at_utc: datetime
    collected_at_utc: datetime
    processed_at_utc: datetime


@final
@dataclass(frozen=True)
class RegistroQuarentenaSilver:
    """Registro rejeitado na transição Bronze -> Silver com motivo auditável."""

    batch_id: str
    feed_id: str
    dedup_hash_ou_id: str
    motivo_quarentena: str
    regra_violada: str
    payload_original_json: str
    rejeitado_em_utc: datetime


@final
@dataclass(frozen=True)
class DimensaoFonte:
    """Dimensão Gold: dim_source."""

    source_key: str
    feed_id: str
    source_domain: str


@final
@dataclass(frozen=True)
class DimensaoData:
    """Dimensão Gold: dim_date."""

    date_key: int
    full_date_iso: str
    year: int
    month: int
    day: int
    day_of_week: int


@final
@dataclass(frozen=True)
class DimensaoCategoria:
    """Dimensão Gold: dim_category."""

    category_key: str
    category_name: str


@final
@dataclass(frozen=True)
class DimensaoIdioma:
    """Dimensão Gold: dim_language."""

    language_key: str
    language_code: str


@final
@dataclass(frozen=True)
class FatoNoticia:
    """Fato Gold: fact_news."""

    news_key: str
    source_key: str
    date_key: int
    category_key: str
    language_key: str
    batch_id: str
    title: str
    canonical_url: str
    published_at_utc: datetime
    collected_at_utc: datetime
    ingestion_lag_seconds: float


@final
@dataclass(frozen=True)
class FatoExecucaoFeed:
    """Fato Gold: fact_feed_execution."""

    execution_key: str
    source_key: str
    date_key: int
    batch_id: str
    records_read_bronze: int
    records_accepted_silver: int
    records_Deduplicated: int
    records_quarantined: int
    executed_at_utc: datetime


@final
@dataclass(frozen=True)
class FatoQualidadeDados:
    """Fato Gold: fact_data_quality."""

    quality_run_key: str
    batch_id: str
    date_key: int
    total_expectations: int
    passed_expectations: int
    failed_expectations: int
    pass_rate: float
    evaluated_at_utc: datetime


@final
@dataclass(frozen=True)
class MartVolumeDiario:
    """Mart Gold 1: mart_volume_diario (News Overview)."""

    date_key: int
    full_date_iso: str
    total_news: int
    distinct_sources: int
    distinct_categories: int


@final
@dataclass(frozen=True)
class MartDesempenhoFontes:
    """Mart Gold 2: mart_desempenho_fontes (RSS Monitoring)."""

    feed_id: str
    total_batches: int
    total_accepted_news: int
    total_quarantined: int
    total_deduplicated: int
    acceptance_rate: float


@final
@dataclass(frozen=True)
class MartDistribuicaoCategorias:
    """Mart Gold 3: mart_distribuicao_categorias (News Analytics)."""

    category_name: str
    total_news: int
    percentage_share: float


@final
@dataclass(frozen=True)
class MartFrescorIngestao:
    """Mart Gold 4: mart_frescor_ingestao (Lakehouse Operations)."""

    feed_id: str
    latest_published_at_utc: str
    latest_collected_at_utc: str
    avg_ingestion_lag_seconds: float
    max_ingestion_lag_seconds: float


@final
@dataclass(frozen=True)
class MartQualidadeDados:
    """Mart Gold 5: mart_qualidade_dados (Data Quality)."""

    batch_id: str
    pass_rate: float
    total_valid_records: int
    total_quarantined_records: int
    quality_status: str
