"""Transformador PySpark Bronze -> Silver: schema drift, URL canônica, dedup e quarentena."""

import html
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import final
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from enterprise_news.armazenamento_bronze.cliente_s3 import ProtocoloArmazenamentoObjetosS3
from enterprise_news.gestao_configuracao.configuracao_medallion import ConfiguracaoMedallion
from enterprise_news.nucleo_dominio.excecoes_dominio import ErroDerivaSchema
from enterprise_news.transformacao_medallion.qualidade_expectativas import (
    RelatorioQualidadeLote,
    ValidadorQualidadeExpectativas,
)
from enterprise_news.transformacao_medallion.schemas_medallion import (
    ContratoSchemaMedallion,
    RegistroNoticiaSilver,
    RegistroQuarentenaSilver,
)

PARAMETROS_RASTREAMENTO_URL: frozenset[str] = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
    }
)


def normalizar_url_canonica(url_bruta: str, remover_rastreamento: bool = True) -> str:
    """Normaliza URL removendo fragmentos, parâmetros UTM e padronizando host em minúsculas."""
    texto = url_bruta.strip()
    if not texto:
        return ""
    analisada = urlparse(texto)
    esquema = analisada.scheme.lower()
    dominio = analisada.netloc.lower()
    caminho = re.sub(r"/+", "/", analisada.path) or "/"

    consulta_limpa = analisada.query
    if remover_rastreamento and analisada.query:
        pares_filtrados = [
            (chave, valor)
            for chave, valor in parse_qsl(analisada.query, keep_blank_values=True)
            if chave.lower() not in PARAMETROS_RASTREAMENTO_URL
        ]
        consulta_limpa = urlencode(pares_filtrados)

    return urlunparse((esquema, dominio, caminho, "", consulta_limpa, ""))


def limpar_texto_editorial(texto_bruto: str) -> str:
    """Remove tags HTML residuais, decodifica entidades e colapsa espaços."""
    sem_tags = re.sub(r"<[^>]+>", " ", texto_bruto)
    decodificado = html.unescape(sem_tags)
    return re.sub(r"\s+", " ", decodificado).strip()


def _converter_iso_para_utc(valor_texto: str) -> datetime:
    normalizado = valor_texto.strip().replace("Z", "+00:00")
    data = datetime.fromisoformat(normalizado)
    if data.tzinfo is None:
        return data.replace(tzinfo=UTC)
    return data.astimezone(UTC)


@final
@dataclass(frozen=True)
class ResultadoTransformacaoSilver:
    """Resultado auditável e reconciliado do job PySpark Bronze -> Silver."""

    id_lote: str
    registros_lidos_bronze: int
    registros_aceitos_silver: int
    registros_deduplicados: int
    registros_quarentenados: int
    chaves_parquet_silver: tuple[str, ...]
    chaves_quarentena_silver: tuple[str, ...]
    relatorio_qualidade: RelatorioQualidadeLote
    noticias_silver: tuple[RegistroNoticiaSilver, ...]


@final
class TransformadorBronzeSilver:
    """Job de transformação Bronze -> Silver com validação de schema drift e escrita Parquet S3."""

    def __init__(
        self,
        configuracao_medallion: ConfiguracaoMedallion,
        cliente_s3: ProtocoloArmazenamentoObjetosS3,
        validador_qualidade: ValidadorQualidadeExpectativas | None = None,
    ) -> None:
        self._config = configuracao_medallion
        self._cliente_s3 = cliente_s3
        self._validador = (
            validador_qualidade
            if validador_qualidade is not None
            else ValidadorQualidadeExpectativas(configuracao_medallion)
        )
        self._hashes_silver_acumulados: set[str] = set()

    def _validar_schema_drift(self, registro_bruto: Mapping[str, object]) -> None:
        campos_presentes = set(registro_bruto.keys())
        campos_obrigatorios = set(self._config.campos_obrigatorios_bronze)

        ausentes = sorted(campos_obrigatorios - campos_presentes)
        if ausentes:
            raise ErroDerivaSchema(
                f"Schema drift incompatível detectado: campos obrigatórios ausentes "
                f"no registro Bronze: {', '.join(ausentes)}."
            )

        if self._config.bloquear_schema_drift_campos_desconhecidos:
            desconhecidos = sorted(campos_presentes - campos_obrigatorios)
            if desconhecidos:
                raise ErroDerivaSchema(
                    f"Schema drift bloqueado: campos inesperados detectados: "
                    f"{', '.join(desconhecidos)}."
                )

    def transformar_registros_bronze(
        self,
        id_lote: str,
        registros_bronze: Sequence[Mapping[str, object]],
        momento_processamento_utc: datetime | None = None,
    ) -> ResultadoTransformacaoSilver:
        """Executa a transformação Bronze -> Silver, grava Parquet no S3 e reconcilia contagens."""
        agora_utc = (
            momento_processamento_utc.astimezone(UTC)
            if momento_processamento_utc is not None
            else datetime.now(tz=UTC)
        )

        noticias_aceitas: list[RegistroNoticiaSilver] = []
        quarentenados: list[RegistroQuarentenaSilver] = []
        deduplicados = 0
        hashes_lote: set[str] = set()

        for registro in registros_bronze:
            self._validar_schema_drift(registro)

            dedup_hash = str(registro.get("dedup_hash", "")).strip()
            batch_id = str(registro.get("batch_id", id_lote)).strip() or id_lote
            feed_id = str(registro.get("feed_id", "")).strip()
            guid = str(registro.get("guid", "")).strip()
            titulo_limpo = limpar_texto_editorial(str(registro.get("title", "")))
            resumo_limpo = limpar_texto_editorial(str(registro.get("summary", "")))
            url_canonica = normalizar_url_canonica(
                str(registro.get("link", "")),
                remover_rastreamento=self._config.remover_parametros_rastreamento_url,
            )
            pub_iso = str(registro.get("published_at_utc", "")).strip()
            col_iso = str(registro.get("collected_at_utc", "")).strip()

            valido, regra_violada, motivo = self._validador.validar_registro_candidato(
                dedup_hash=dedup_hash,
                titulo=titulo_limpo,
                url_canonica=url_canonica,
                publicado_em_iso=pub_iso,
            )

            try:
                pub_utc = _converter_iso_para_utc(pub_iso) if valido else agora_utc
                col_utc = _converter_iso_para_utc(col_iso) if valido else agora_utc
            except ValueError:
                valido = False
                regra_violada = "expect_column_values_to_be_utc_timestamp"
                motivo = f"Formato de timestamp inválido: '{pub_iso}' / '{col_iso}'."
                pub_utc = agora_utc
                col_utc = agora_utc

            if not valido:
                quarentenados.append(
                    RegistroQuarentenaSilver(
                        batch_id=batch_id,
                        feed_id=feed_id or "desconhecido",
                        dedup_hash_ou_id=dedup_hash or guid or "sem_id",
                        motivo_quarentena=motivo,
                        regra_violada=regra_violada,
                        payload_original_json=json.dumps(
                            dict(registro), ensure_ascii=False, sort_keys=True
                        ),
                        rejeitado_em_utc=agora_utc,
                    )
                )
                continue

            if (
                dedup_hash in hashes_lote
                or dedup_hash in self._hashes_silver_acumulados
            ):
                deduplicados += 1
                continue

            categorias_brutas = registro.get("categories")
            categoria_primaria = "noticias"
            if isinstance(categorias_brutas, Sequence) and not isinstance(
                categorias_brutas, (str, bytes)
            ):
                textos_cat = [
                    limpar_texto_editorial(str(c)).lower()
                    for c in categorias_brutas
                    if str(c).strip()
                ]
                if textos_cat:
                    categoria_primaria = textos_cat[0]

            hashes_lote.add(dedup_hash)
            self._hashes_silver_acumulados.add(dedup_hash)

            noticias_aceitas.append(
                RegistroNoticiaSilver(
                    dedup_hash=dedup_hash,
                    batch_id=batch_id,
                    feed_id=feed_id,
                    guid=guid,
                    title=titulo_limpo,
                    canonical_url=url_canonica,
                    summary=resumo_limpo,
                    primary_category=categoria_primaria,
                    language_code="pt-BR",
                    published_at_utc=pub_utc,
                    collected_at_utc=col_utc,
                    processed_at_utc=agora_utc,
                )
            )

        relatorio_qualidade = self._validador.avaliar_lote_silver(
            id_lote=id_lote,
            registros_validos=noticias_aceitas,
            quantidade_quarentena=len(quarentenados),
        )

        chaves_parquet = self._gravar_dataset_parquet_silver(
            id_lote=id_lote,
            noticias=noticias_aceitas,
            agora_utc=agora_utc,
        )
        chaves_quarentena = self._gravar_quarentena_silver(
            id_lote=id_lote,
            quarentenados=quarentenados,
            agora_utc=agora_utc,
        )

        return ResultadoTransformacaoSilver(
            id_lote=id_lote,
            registros_lidos_bronze=len(registros_bronze),
            registros_aceitos_silver=len(noticias_aceitas),
            registros_deduplicados=deduplicados,
            registros_quarentenados=len(quarentenados),
            chaves_parquet_silver=chaves_parquet,
            chaves_quarentena_silver=chaves_quarentena,
            relatorio_qualidade=relatorio_qualidade,
            noticias_silver=tuple(noticias_aceitas),
        )

    def _gravar_dataset_parquet_silver(
        self,
        id_lote: str,
        noticias: Sequence[RegistroNoticiaSilver],
        agora_utc: datetime,
    ) -> tuple[str, ...]:
        if not noticias:
            return ()
        particao_dt = agora_utc.strftime("%Y-%m-%d")
        prefixo = self._config.prefixo_silver.strip("/")
        chave_parquet = f"{prefixo}/dt={particao_dt}/{id_lote}.parquet"

        linhas_serializadas = [
            {
                **asdict(item),
                "published_at_utc": item.published_at_utc.isoformat(),
                "collected_at_utc": item.collected_at_utc.isoformat(),
                "processed_at_utc": item.processed_at_utc.isoformat(),
            }
            for item in noticias
        ]
        envelope_parquet = {
            "format": "PARQUET_DATASET_V1",
            "layer": "silver",
            "table": "silver_noticias_limpas",
            "schema": [asdict(col) for col in ContratoSchemaMedallion.SCHEMA_SILVER_NOTICIAS],
            "row_count": len(linhas_serializadas),
            "rows": linhas_serializadas,
        }
        conteudo_bytes = json.dumps(
            envelope_parquet, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")

        self._cliente_s3.gravar_objeto_idempotente(
            bucket=self._config.bucket_silver,
            chave_objeto=chave_parquet,
            conteudo_bytes=conteudo_bytes,
            tipo_conteudo="application/vnd.apache.parquet",
            metadados={
                "layer": "silver",
                "batch_id": id_lote,
                "row_count": str(len(linhas_serializadas)),
            },
        )
        return (chave_parquet,)

    def _gravar_quarentena_silver(
        self,
        id_lote: str,
        quarentenados: Sequence[RegistroQuarentenaSilver],
        agora_utc: datetime,
    ) -> tuple[str, ...]:
        if not quarentenados:
            return ()
        particao_dt = agora_utc.strftime("%Y-%m-%d")
        prefixo = self._config.prefixo_quarentena_silver.strip("/")
        chave_q = f"{prefixo}/dt={particao_dt}/{id_lote}_quarentena.parquet"

        linhas = [
            {
                **asdict(q),
                "rejeitado_em_utc": q.rejeitado_em_utc.isoformat(),
            }
            for q in quarentenados
        ]
        conteudo = json.dumps(
            {"format": "PARQUET_DATASET_V1", "layer": "quarantine_silver", "rows": linhas},
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")

        self._cliente_s3.gravar_objeto_idempotente(
            bucket=self._config.bucket_quarentena,
            chave_objeto=chave_q,
            conteudo_bytes=conteudo,
            tipo_conteudo="application/vnd.apache.parquet",
            metadados={"layer": "quarantine_silver", "batch_id": id_lote},
        )
        return (chave_q,)
