"""Testes automatizados da Etapa 4 — PySpark, Silver, Gold, Qualidade e Schema Drift."""

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from enterprise_news.armazenamento_bronze import ClienteObjectStorageMemoriaS3
from enterprise_news.gestao_configuracao import carregar_configuracao_medallion_padrao
from enterprise_news.nucleo_dominio import ErroDerivaSchema, ErroQualidadeDados
from enterprise_news.transformacao_medallion import (
    TransformadorBronzeSilver,
    TransformadorSilverGold,
    limpar_texto_editorial,
    normalizar_url_canonica,
)

RAIZ_PROJETO = Path(__file__).resolve().parent.parent


def _criar_registro_bronze_sintetico(
    dedup_hash: str,
    feed_id: str = "g1_economia",
    titulo: str = "<b>Inflação</b> recua em novembro &amp; mercado reage",
    link: str = "https://G1.Globo.com/economia/noticia-1.ghtml?utm_source=rss&fbclid=123#topo",
    categoria: str = "Economia",
    pub_utc: str = "2026-11-26T15:00:00+00:00",
    col_utc: str = "2026-11-26T15:02:00+00:00",
) -> dict[str, object]:
    return {
        "batch_id": "lote_teste_01",
        "feed_id": feed_id,
        "guid": f"guid_{dedup_hash}",
        "title": titulo,
        "link": link,
        "summary": "<p>Resumo da notícia com tags HTML.</p>",
        "categories": [categoria],
        "published_at_utc": pub_utc,
        "collected_at_utc": col_utc,
        "dedup_hash": dedup_hash,
    }


def test_carregamento_configuracao_medallion_e_normalizacao_url() -> None:
    config = carregar_configuracao_medallion_padrao(
        str(RAIZ_PROJETO / "config" / "camadas_medallion.yaml")
    )
    assert config.bucket_silver == "enl-silver"
    assert config.bucket_gold == "enl-gold"
    assert len(config.dimensoes_gold) == 4
    assert len(config.fatos_gold) == 3
    assert len(config.marts_gold) == 5

    url_limpa = normalizar_url_canonica(
        "https://G1.Globo.com//economia//item.ghtml?utm_source=g1&id=42#secao"
    )
    assert url_limpa == "https://g1.globo.com/economia/item.ghtml?id=42"
    assert limpar_texto_editorial("<b>Título &amp; Subtítulo</b>") == "Título & Subtítulo"


def test_pipeline_bronze_para_silver_e_gold_com_5_marts_e_reconciliacao() -> None:
    config = carregar_configuracao_medallion_padrao(
        str(RAIZ_PROJETO / "config" / "camadas_medallion.yaml")
    )
    cliente_s3 = ClienteObjectStorageMemoriaS3()
    job_silver = TransformadorBronzeSilver(config, cliente_s3)
    job_gold = TransformadorSilverGold(config, cliente_s3)

    registros_lote_1 = [
        _criar_registro_bronze_sintetico("hash_01", "g1_economia", categoria="Economia"),
        _criar_registro_bronze_sintetico("hash_02", "g1_tecnologia", categoria="Tecnologia"),
        # Duplicado no mesmo lote
        _criar_registro_bronze_sintetico("hash_01", "g1_economia", categoria="Economia"),
        # Inválido (URL HTTP não-HTTPS -> vai para quarentena Silver)
        _criar_registro_bronze_sintetico(
            "hash_invalido",
            "g1_economia",
            link="http://g1.globo.com/inseguro.ghtml",
        ),
    ]
    instante_proc = datetime(2026, 11, 26, 16, 0, 0, tzinfo=UTC)

    res_silver = job_silver.transformar_registros_bronze(
        id_lote="lote_01",
        registros_bronze=registros_lote_1,
        momento_processamento_utc=instante_proc,
    )

    # Reconciliação de contagens Silver: 4 lidos = 2 aceitos + 1 deduplicado + 1 quarentenado
    assert res_silver.registros_lidos_bronze == 4
    assert res_silver.registros_aceitos_silver == 2
    assert res_silver.registros_deduplicados == 1
    assert res_silver.registros_quarentenados == 1
    assert (
        res_silver.registros_aceitos_silver
        + res_silver.registros_deduplicados
        + res_silver.registros_quarentenados
        == res_silver.registros_lidos_bronze
    )
    assert res_silver.relatorio_qualidade.aprovado is True
    assert len(res_silver.chaves_parquet_silver) == 1
    assert len(res_silver.chaves_quarentena_silver) == 1

    # Replay / lote incremental com item já processado + 1 item novo
    registros_lote_2 = [
        _criar_registro_bronze_sintetico("hash_01", "g1_economia", categoria="Economia"),
        _criar_registro_bronze_sintetico("hash_03", "g1_principal", categoria="Política"),
    ]
    res_silver_2 = job_silver.transformar_registros_bronze(
        id_lote="lote_02",
        registros_bronze=registros_lote_2,
        momento_processamento_utc=instante_proc,
    )
    assert res_silver_2.registros_aceitos_silver == 1
    assert res_silver_2.registros_deduplicados == 1

    # Transformação Silver -> Gold (4 dimensões, 3 fatos, 5 marts)
    res_gold = job_gold.processar_camada_gold(
        resultados_silver=(res_silver, res_silver_2),
        momento_execucao_utc=instante_proc,
    )

    assert len(res_gold.dim_source) == 3
    assert len(res_gold.dim_date) == 1
    assert len(res_gold.dim_category) == 3
    assert len(res_gold.dim_language) == 1
    assert len(res_gold.fact_news) == 3
    assert len(res_gold.fact_feed_execution) == 2
    assert len(res_gold.fact_data_quality) == 2

    # Verifica os 5 data marts obrigatórios
    assert len(res_gold.mart_volume_diario) == 1
    assert res_gold.mart_volume_diario[0].total_news == 3
    assert len(res_gold.mart_desempenho_fontes) >= 2
    assert len(res_gold.mart_distribuicao_categorias) == 3
    assert len(res_gold.mart_frescor_ingestao) == 3
    assert len(res_gold.mart_qualidade_dados) == 2
    assert len(res_gold.chaves_parquet_gold) == 12  # 4 dims + 3 facts + 5 marts

    chaves_s3_gold = cliente_s3.listar_chaves_prefixo("enl-gold", "gold/")
    assert len(chaves_s3_gold) == 12


def test_deteccao_schema_drift_e_reprovacao_qualidade_lote() -> None:
    config = carregar_configuracao_medallion_padrao(
        str(RAIZ_PROJETO / "config" / "camadas_medallion.yaml")
    )
    cliente_s3 = ClienteObjectStorageMemoriaS3()
    job_silver = TransformadorBronzeSilver(config, cliente_s3)

    # 1. Schema drift por ausência de campo obrigatório
    registro_incompleto = {"batch_id": "lote_drift", "feed_id": "g1_principal"}
    with pytest.raises(ErroDerivaSchema, match="campos obrigatórios ausentes"):
        job_silver.transformar_registros_bronze("lote_drift", [registro_incompleto])

    # 2. Schema drift por campo desconhecido quando bloqueio estrito está ativo
    config_estrita = replace(config, bloquear_schema_drift_campos_desconhecidos=True)
    job_estrito = TransformadorBronzeSilver(config_estrita, cliente_s3)
    registro_com_extra = _criar_registro_bronze_sintetico("hash_extra")
    registro_com_extra["campo_nao_previsto"] = "valor"
    with pytest.raises(ErroDerivaSchema, match="campos inesperados"):
        job_estrito.transformar_registros_bronze("lote_extra", [registro_com_extra])

    # 3. Reprovação de qualidade quando todos os registros do lote falham nas expectativas
    registro_ruim = _criar_registro_bronze_sintetico("hash_ruim", titulo="abc")
    with pytest.raises(ErroQualidadeDados, match="reprovada"):
        job_silver.transformar_registros_bronze("lote_reprovado", [registro_ruim])

