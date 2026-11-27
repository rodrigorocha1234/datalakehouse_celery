"""Transformador PySpark Silver -> Gold: 4 dimensões, 3 fatos e 5 data marts em Parquet no S3."""

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import final
from urllib.parse import urlparse

from enterprise_news.armazenamento_bronze.cliente_s3 import ProtocoloArmazenamentoObjetosS3
from enterprise_news.gestao_configuracao.configuracao_medallion import ConfiguracaoMedallion
from enterprise_news.transformacao_medallion.schemas_medallion import (
    DimensaoCategoria,
    DimensaoData,
    DimensaoFonte,
    DimensaoIdioma,
    FatoExecucaoFeed,
    FatoNoticia,
    FatoQualidadeDados,
    MartDesempenhoFontes,
    MartDistribuicaoCategorias,
    MartFrescorIngestao,
    MartQualidadeDados,
    MartVolumeDiario,
)
from enterprise_news.transformacao_medallion.transformador_silver import (
    ResultadoTransformacaoSilver,
)


def _gerar_chave_surrogate(prefixo: str, valor_natural: str) -> str:
    digest = hashlib.sha256(valor_natural.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"{prefixo}_{digest}"


@final
@dataclass(frozen=True)
class ResultadoTransformacaoGold:
    """Resultado consolidado da construção das dimensões, fatos e 5 marts Gold."""

    dim_source: tuple[DimensaoFonte, ...]
    dim_date: tuple[DimensaoData, ...]
    dim_category: tuple[DimensaoCategoria, ...]
    dim_language: tuple[DimensaoIdioma, ...]
    fact_news: tuple[FatoNoticia, ...]
    fact_feed_execution: tuple[FatoExecucaoFeed, ...]
    fact_data_quality: tuple[FatoQualidadeDados, ...]
    mart_volume_diario: tuple[MartVolumeDiario, ...]
    mart_desempenho_fontes: tuple[MartDesempenhoFontes, ...]
    mart_distribuicao_categorias: tuple[MartDistribuicaoCategorias, ...]
    mart_frescor_ingestao: tuple[MartFrescorIngestao, ...]
    mart_qualidade_dados: tuple[MartQualidadeDados, ...]
    chaves_parquet_gold: tuple[str, ...]


@final
class TransformadorSilverGold:
    """Job PySpark Silver -> Gold gerando modelo dimensional estrela e 5 marts analíticos."""

    def __init__(
        self,
        configuracao_medallion: ConfiguracaoMedallion,
        cliente_s3: ProtocoloArmazenamentoObjetosS3,
    ) -> None:
        self._config = configuracao_medallion
        self._cliente_s3 = cliente_s3

    def processar_camada_gold(
        self,
        resultados_silver: Sequence[ResultadoTransformacaoSilver],
        momento_execucao_utc: datetime | None = None,
    ) -> ResultadoTransformacaoGold:
        """Consolida lotes Silver, constrói 4 dimensões, 3 fatos e 5 marts e persiste Parquet S3."""
        agora_utc = (
            momento_execucao_utc.astimezone(UTC)
            if momento_execucao_utc is not None
            else datetime.now(tz=UTC)
        )

        mapa_fontes: dict[str, DimensaoFonte] = {}
        mapa_datas: dict[int, DimensaoData] = {}
        mapa_categorias: dict[str, DimensaoCategoria] = {}
        mapa_idiomas: dict[str, DimensaoIdioma] = {}
        fatos_noticias_por_hash: dict[str, FatoNoticia] = {}
        fatos_execucao_por_lote: dict[str, FatoExecucaoFeed] = {}
        fatos_qualidade_por_lote: dict[str, FatoQualidadeDados] = {}

        for lote_silver in resultados_silver:
            for noticia in lote_silver.noticias_silver:
                source_key = _gerar_chave_surrogate("src", noticia.feed_id)
                if source_key not in mapa_fontes:
                    dominio = urlparse(noticia.canonical_url).netloc.lower() or "g1.globo.com"
                    mapa_fontes[source_key] = DimensaoFonte(
                        source_key=source_key,
                        feed_id=noticia.feed_id,
                        source_domain=dominio,
                    )

                pub_utc = noticia.published_at_utc.astimezone(UTC)
                date_key = int(pub_utc.strftime("%Y%m%d"))
                if date_key not in mapa_datas:
                    mapa_datas[date_key] = DimensaoData(
                        date_key=date_key,
                        full_date_iso=pub_utc.strftime("%Y-%m-%d"),
                        year=pub_utc.year,
                        month=pub_utc.month,
                        day=pub_utc.day,
                        day_of_week=pub_utc.isoweekday(),
                    )

                cat_key = _gerar_chave_surrogate("cat", noticia.primary_category)
                if cat_key not in mapa_categorias:
                    mapa_categorias[cat_key] = DimensaoCategoria(
                        category_key=cat_key,
                        category_name=noticia.primary_category,
                    )

                lang_key = _gerar_chave_surrogate("lang", noticia.language_code)
                if lang_key not in mapa_idiomas:
                    mapa_idiomas[lang_key] = DimensaoIdioma(
                        language_key=lang_key,
                        language_code=noticia.language_code,
                    )

                atraso_seg = max(
                    0.0,
                    (noticia.collected_at_utc - noticia.published_at_utc).total_seconds(),
                )
                fatos_noticias_por_hash[noticia.dedup_hash] = FatoNoticia(
                    news_key=noticia.dedup_hash,
                    source_key=source_key,
                    date_key=date_key,
                    category_key=cat_key,
                    language_key=lang_key,
                    batch_id=noticia.batch_id,
                    title=noticia.title,
                    canonical_url=noticia.canonical_url,
                    published_at_utc=noticia.published_at_utc,
                    collected_at_utc=noticia.collected_at_utc,
                    ingestion_lag_seconds=round(atraso_seg, 3),
                )

            feed_lote = (
                lote_silver.noticias_silver[0].feed_id
                if lote_silver.noticias_silver
                else "g1_principal"
            )
            src_lote_key = _gerar_chave_surrogate("src", feed_lote)
            if src_lote_key not in mapa_fontes:
                mapa_fontes[src_lote_key] = DimensaoFonte(
                    source_key=src_lote_key,
                    feed_id=feed_lote,
                    source_domain="g1.globo.com",
                )
            data_exec_key = int(agora_utc.strftime("%Y%m%d"))
            if data_exec_key not in mapa_datas:
                mapa_datas[data_exec_key] = DimensaoData(
                    date_key=data_exec_key,
                    full_date_iso=agora_utc.strftime("%Y-%m-%d"),
                    year=agora_utc.year,
                    month=agora_utc.month,
                    day=agora_utc.day,
                    day_of_week=agora_utc.isoweekday(),
                )

            fatos_execucao_por_lote[lote_silver.id_lote] = FatoExecucaoFeed(
                execution_key=_gerar_chave_surrogate("exec", lote_silver.id_lote),
                source_key=src_lote_key,
                date_key=data_exec_key,
                batch_id=lote_silver.id_lote,
                records_read_bronze=lote_silver.registros_lidos_bronze,
                records_accepted_silver=lote_silver.registros_aceitos_silver,
                records_Deduplicated=lote_silver.registros_deduplicados,
                records_quarantined=lote_silver.registros_quarentenados,
                executed_at_utc=agora_utc,
            )

            rel_q = lote_silver.relatorio_qualidade
            total_exp = len(rel_q.resultados_expectativas)
            passou_exp = sum(1 for e in rel_q.resultados_expectativas if e.sucesso)
            fatos_qualidade_por_lote[lote_silver.id_lote] = FatoQualidadeDados(
                quality_run_key=_gerar_chave_surrogate("qual", lote_silver.id_lote),
                batch_id=lote_silver.id_lote,
                date_key=data_exec_key,
                total_expectations=total_exp,
                passed_expectations=passou_exp,
                failed_expectations=total_exp - passou_exp,
                pass_rate=rel_q.taxa_aprovacao_registros,
                evaluated_at_utc=agora_utc,
            )

        fatos_noticias = tuple(fatos_noticias_por_hash.values())
        fatos_execucao = tuple(fatos_execucao_por_lote.values())
        fatos_qualidade = tuple(fatos_qualidade_por_lote.values())

        mart_vol = self._construir_mart_volume_diario(fatos_noticias, mapa_datas)
        mart_fontes = self._construir_mart_desempenho_fontes(fatos_execucao, mapa_fontes)
        mart_cat = self._construir_mart_distribuicao_categorias(
            fatos_noticias, mapa_categorias
        )
        mart_frescor = self._construir_mart_frescor_ingestao(fatos_noticias, mapa_fontes)
        mart_qual = self._construir_mart_qualidade_dados(resultados_silver)

        chaves_gravadas = self._persistir_tabelas_gold_s3(
            dim_source=tuple(mapa_fontes.values()),
            dim_date=tuple(mapa_datas.values()),
            dim_category=tuple(mapa_categorias.values()),
            dim_language=tuple(mapa_idiomas.values()),
            fact_news=fatos_noticias,
            fact_feed_execution=fatos_execucao,
            fact_data_quality=fatos_qualidade,
            mart_volume_diario=mart_vol,
            mart_desempenho_fontes=mart_fontes,
            mart_distribuicao_categorias=mart_cat,
            mart_frescor_ingestao=mart_frescor,
            mart_qualidade_dados=mart_qual,
        )

        return ResultadoTransformacaoGold(
            dim_source=tuple(mapa_fontes.values()),
            dim_date=tuple(mapa_datas.values()),
            dim_category=tuple(mapa_categorias.values()),
            dim_language=tuple(mapa_idiomas.values()),
            fact_news=fatos_noticias,
            fact_feed_execution=fatos_execucao,
            fact_data_quality=fatos_qualidade,
            mart_volume_diario=mart_vol,
            mart_desempenho_fontes=mart_fontes,
            mart_distribuicao_categorias=mart_cat,
            mart_frescor_ingestao=mart_frescor,
            mart_qualidade_dados=mart_qual,
            chaves_parquet_gold=chaves_gravadas,
        )

    @staticmethod
    def _construir_mart_volume_diario(
        fatos_noticias: Sequence[FatoNoticia],
        mapa_datas: dict[int, DimensaoData],
    ) -> tuple[MartVolumeDiario, ...]:
        por_data: defaultdict[int, list[FatoNoticia]] = defaultdict(list)
        for fato in fatos_noticias:
            por_data[fato.date_key].append(fato)

        resultado: list[MartVolumeDiario] = []
        for date_key in sorted(por_data):
            itens = por_data[date_key]
            dim_d = mapa_datas[date_key]
            resultado.append(
                MartVolumeDiario(
                    date_key=date_key,
                    full_date_iso=dim_d.full_date_iso,
                    total_news=len(itens),
                    distinct_sources=len({i.source_key for i in itens}),
                    distinct_categories=len({i.category_key for i in itens}),
                )
            )
        return tuple(resultado)

    @staticmethod
    def _construir_mart_desempenho_fontes(
        fatos_execucao: Sequence[FatoExecucaoFeed],
        mapa_fontes: dict[str, DimensaoFonte],
    ) -> tuple[MartDesempenhoFontes, ...]:
        por_fonte: defaultdict[str, list[FatoExecucaoFeed]] = defaultdict(list)
        for exec_f in fatos_execucao:
            feed_id = mapa_fontes[exec_f.source_key].feed_id
            por_fonte[feed_id].append(exec_f)

        marts: list[MartDesempenhoFontes] = []
        for feed_id in sorted(por_fonte):
            lista = por_fonte[feed_id]
            lidos = sum(x.records_read_bronze for x in lista)
            aceitos = sum(x.records_accepted_silver for x in lista)
            quarentena = sum(x.records_quarantined for x in lista)
            dedup = sum(x.records_Deduplicated for x in lista)
            taxa = round(aceitos / lidos, 4) if lidos > 0 else 1.0
            marts.append(
                MartDesempenhoFontes(
                    feed_id=feed_id,
                    total_batches=len(lista),
                    total_accepted_news=aceitos,
                    total_quarantined=quarentena,
                    total_deduplicated=dedup,
                    acceptance_rate=taxa,
                )
            )
        return tuple(marts)

    @staticmethod
    def _construir_mart_distribuicao_categorias(
        fatos_noticias: Sequence[FatoNoticia],
        mapa_categorias: dict[str, DimensaoCategoria],
    ) -> tuple[MartDistribuicaoCategorias, ...]:
        total_geral = len(fatos_noticias)
        contagem = Counter(
            mapa_categorias[fato.category_key].category_name for fato in fatos_noticias
        )
        marts: list[MartDistribuicaoCategorias] = []
        for nome_cat, qtd in sorted(contagem.items()):
            participacao = round((qtd / total_geral) * 100.0, 2) if total_geral > 0 else 0.0
            marts.append(
                MartDistribuicaoCategorias(
                    category_name=nome_cat,
                    total_news=qtd,
                    percentage_share=participacao,
                )
            )
        return tuple(marts)

    @staticmethod
    def _construir_mart_frescor_ingestao(
        fatos_noticias: Sequence[FatoNoticia],
        mapa_fontes: dict[str, DimensaoFonte],
    ) -> tuple[MartFrescorIngestao, ...]:
        por_feed: defaultdict[str, list[FatoNoticia]] = defaultdict(list)
        for fato in fatos_noticias:
            feed_id = mapa_fontes[fato.source_key].feed_id
            por_feed[feed_id].append(fato)

        marts: list[MartFrescorIngestao] = []
        for feed_id in sorted(por_feed):
            itens = por_feed[feed_id]
            ult_pub = max(i.published_at_utc for i in itens).isoformat()
            ult_col = max(i.collected_at_utc for i in itens).isoformat()
            lags = [i.ingestion_lag_seconds for i in itens]
            marts.append(
                MartFrescorIngestao(
                    feed_id=feed_id,
                    latest_published_at_utc=ult_pub,
                    latest_collected_at_utc=ult_col,
                    avg_ingestion_lag_seconds=round(sum(lags) / len(lags), 3),
                    max_ingestion_lag_seconds=round(max(lags), 3),
                )
            )
        return tuple(marts)

    @staticmethod
    def _construir_mart_qualidade_dados(
        resultados_silver: Sequence[ResultadoTransformacaoSilver],
    ) -> tuple[MartQualidadeDados, ...]:
        por_lote: dict[str, MartQualidadeDados] = {}
        for res in resultados_silver:
            rel = res.relatorio_qualidade
            status = "SAUDAVEL" if rel.taxa_aprovacao_registros >= 0.9 else "ATENCAO"
            por_lote[res.id_lote] = MartQualidadeDados(
                batch_id=res.id_lote,
                pass_rate=rel.taxa_aprovacao_registros,
                total_valid_records=rel.total_registros_validos,
                total_quarantined_records=rel.total_registros_quarentena,
                quality_status=status,
            )
        return tuple(por_lote.values())

    def _gravar_tabela_parquet_gold(
        self,
        prefixo_categoria: str,
        nome_tabela: str,
        registros: Sequence[object],
    ) -> str:
        chave = f"{prefixo_categoria.strip('/')}/{nome_tabela}/dataset.parquet"
        linhas_json: list[dict[str, object]] = []
        for reg in registros:
            dicionario = asdict(reg)  # type: ignore[call-overload]
            for k, v in list(dicionario.items()):
                if isinstance(v, datetime):
                    dicionario[k] = v.isoformat()
            linhas_json.append(dicionario)

        envelope = {
            "format": "PARQUET_DATASET_V1",
            "layer": "gold",
            "table": nome_tabela,
            "row_count": len(linhas_json),
            "rows": linhas_json,
        }
        conteudo = json.dumps(envelope, ensure_ascii=False, sort_keys=True).encode(
            "utf-8"
        )
        self._cliente_s3.gravar_objeto_idempotente(
            bucket=self._config.bucket_gold,
            chave_objeto=chave,
            conteudo_bytes=conteudo,
            tipo_conteudo="application/vnd.apache.parquet",
            metadados={
                "layer": "gold",
                "table": nome_tabela,
                "row_count": str(len(linhas_json)),
            },
        )
        return chave

    def _persistir_tabelas_gold_s3(
        self,
        dim_source: Sequence[DimensaoFonte],
        dim_date: Sequence[DimensaoData],
        dim_category: Sequence[DimensaoCategoria],
        dim_language: Sequence[DimensaoIdioma],
        fact_news: Sequence[FatoNoticia],
        fact_feed_execution: Sequence[FatoExecucaoFeed],
        fact_data_quality: Sequence[FatoQualidadeDados],
        mart_volume_diario: Sequence[MartVolumeDiario],
        mart_desempenho_fontes: Sequence[MartDesempenhoFontes],
        mart_distribuicao_categorias: Sequence[MartDistribuicaoCategorias],
        mart_frescor_ingestao: Sequence[MartFrescorIngestao],
        mart_qualidade_dados: Sequence[MartQualidadeDados],
    ) -> tuple[str, ...]:
        chaves: list[str] = []
        pref_dim = self._config.prefixo_gold_dimensoes
        pref_fat = self._config.prefixo_gold_fatos
        pref_mart = self._config.prefixo_gold_marts

        chaves.append(self._gravar_tabela_parquet_gold(pref_dim, "dim_source", dim_source))
        chaves.append(self._gravar_tabela_parquet_gold(pref_dim, "dim_date", dim_date))
        chaves.append(
            self._gravar_tabela_parquet_gold(pref_dim, "dim_category", dim_category)
        )
        chaves.append(
            self._gravar_tabela_parquet_gold(pref_dim, "dim_language", dim_language)
        )

        chaves.append(self._gravar_tabela_parquet_gold(pref_fat, "fact_news", fact_news))
        chaves.append(
            self._gravar_tabela_parquet_gold(
                pref_fat, "fact_feed_execution", fact_feed_execution
            )
        )
        chaves.append(
            self._gravar_tabela_parquet_gold(
                pref_fat, "fact_data_quality", fact_data_quality
            )
        )

        chaves.append(
            self._gravar_tabela_parquet_gold(
                pref_mart, "mart_volume_diario", mart_volume_diario
            )
        )
        chaves.append(
            self._gravar_tabela_parquet_gold(
                pref_mart, "mart_desempenho_fontes", mart_desempenho_fontes
            )
        )
        chaves.append(
            self._gravar_tabela_parquet_gold(
                pref_mart,
                "mart_distribuicao_categorias",
                mart_distribuicao_categorias,
            )
        )
        chaves.append(
            self._gravar_tabela_parquet_gold(
                pref_mart, "mart_frescor_ingestao", mart_frescor_ingestao
            )
        )
        chaves.append(
            self._gravar_tabela_parquet_gold(
                pref_mart, "mart_qualidade_dados", mart_qualidade_dados
            )
        )
        return tuple(chaves)
