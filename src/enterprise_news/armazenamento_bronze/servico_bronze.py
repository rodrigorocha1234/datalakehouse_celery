"""Serviço de escrita idempotente, quarentena e replay desde a camada Bronze em S3."""

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import final

from enterprise_news.armazenamento_bronze.checkpoints_bronze import (
    EstadoCheckpointLote,
    RepositorioCheckpointsBronzeSql,
)
from enterprise_news.armazenamento_bronze.cliente_s3 import ProtocoloArmazenamentoObjetosS3
from enterprise_news.gestao_configuracao.configuracao_bronze import ConfiguracaoCamadaBronze
from enterprise_news.gestao_configuracao.configuracao_rss import ConfiguracaoFeedRss
from enterprise_news.ingestao_rss.analisador_xml import (
    AnalisadorXmlRss,
    NoticiaRssColetada,
)
from enterprise_news.ingestao_rss.transporte_http import RespostaHttpBruta
from enterprise_news.nucleo_dominio.excecoes_dominio import (
    ErroAnaliseXmlRss,
    ErroArmazenamentoObjetos,
    ErroTransicaoCheckpoint,
)


@final
@dataclass(frozen=True)
class ResultadoPersistenciaBronze:
    """Resumo auditável da gravação ou replay de um lote na camada Bronze."""

    id_lote: str
    identificador_feed: str
    estado_final: EstadoCheckpointLote
    bucket_destino: str
    chave_s3_payload: str
    chaves_s3_itens: tuple[str, ...]
    payload_novo_gravado: bool
    itens_novos_gravados: int
    itens_idempotentes_ignorados: int
    enviado_quarentena: bool


@final
class ServicoCamadaBronze:
    """Serviço de escrita idempotente, quarentena e replay desde a camada Bronze em S3."""

    def __init__(
        self,
        configuracao_bronze: ConfiguracaoCamadaBronze,
        cliente_s3: ProtocoloArmazenamentoObjetosS3,
        repositorio_checkpoints: RepositorioCheckpointsBronzeSql,
    ) -> None:
        self._config = configuracao_bronze
        self._cliente_s3 = cliente_s3
        self._checkpoints = repositorio_checkpoints

    @staticmethod
    def gerar_id_lote_deterministico(identificador_feed: str, hash_payload: str) -> str:
        """Gera batch_id determinístico para garantir idempotência em redeliveries."""
        return f"lote_{identificador_feed}_{hash_payload[:16]}"

    def _chave_s3_payload_bronze(
        self,
        identificador_feed: str,
        id_lote: str,
        momento_utc: datetime,
    ) -> str:
        data_particao = momento_utc.astimezone(UTC).strftime("%Y/%m/%d")
        prefixo = self._config.prefixo_objetos_bronze.strip("/")
        return f"{prefixo}/feed={identificador_feed}/dt={data_particao}/{id_lote}_payload.json"

    def _chave_s3_item_bronze(
        self,
        identificador_feed: str,
        noticia: NoticiaRssColetada,
    ) -> str:
        data_particao = noticia.publicado_em_utc.astimezone(UTC).strftime("%Y/%m/%d")
        prefixo = self._config.prefixo_objetos_bronze.strip("/")
        return (
            f"{prefixo}/feed={identificador_feed}/dt={data_particao}/"
            f"itens/{noticia.hash_deduplicacao}.json"
        )

    def _chave_s3_quarentena(
        self,
        identificador_feed: str,
        id_lote: str,
        momento_utc: datetime,
    ) -> str:
        data_particao = momento_utc.astimezone(UTC).strftime("%Y/%m/%d")
        prefixo = self._config.prefixo_objetos_quarentena.strip("/")
        return f"{prefixo}/feed={identificador_feed}/dt={data_particao}/{id_lote}_quarentena.json"

    def persistir_lote_bruto(
        self,
        feed: ConfiguracaoFeedRss,
        resposta_http: RespostaHttpBruta,
        momento_ingestao_utc: datetime | None = None,
    ) -> ResultadoPersistenciaBronze:
        """Grava payload bruto e itens na camada Bronze S3 com checkpoint e quarentena."""
        agora_utc = (
            momento_ingestao_utc.astimezone(UTC)
            if momento_ingestao_utc is not None
            else datetime.now(tz=UTC)
        )
        hash_payload = hashlib.sha256(
            resposta_http.corpo_texto.encode("utf-8")
        ).hexdigest()
        id_lote = self.gerar_id_lote_deterministico(feed.identificador, hash_payload)
        chave_payload = self._chave_s3_payload_bronze(
            feed.identificador, id_lote, agora_utc
        )

        checkpoint = self._checkpoints.iniciar_ou_retomar_lote(
            id_lote=id_lote,
            identificador_feed=feed.identificador,
            hash_payload=hash_payload,
            chave_s3_payload=chave_payload,
            codigo_http=resposta_http.codigo_status,
            instante_utc=agora_utc,
        )

        envelope_payload: dict[str, object] = {
            "batch_id": id_lote,
            "feed_id": feed.identificador,
            "feed_url": feed.url,
            "http_status": resposta_http.codigo_status,
            "http_headers": dict(resposta_http.cabecalhos),
            "payload_sha256": hash_payload,
            "ingested_at_utc": agora_utc.isoformat(),
            "raw_xml": resposta_http.corpo_texto,
        }
        bytes_payload = json.dumps(
            envelope_payload, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")

        try:
            noticias, _ = AnalisadorXmlRss.extrair_noticias(
                identificador_feed=feed.identificador,
                conteudo_xml=resposta_http.corpo_texto,
                momento_coleta_utc=agora_utc,
            )
        except ErroAnaliseXmlRss as erro_xml:
            return self._enviar_para_quarentena(
                feed=feed,
                id_lote=id_lote,
                envelope_payload=envelope_payload,
                motivo_erro=str(erro_xml),
                agora_utc=agora_utc,
            )

        _, payload_criado = self._cliente_s3.gravar_objeto_idempotente(
            bucket=self._config.bucket_bronze,
            chave_objeto=chave_payload,
            conteudo_bytes=bytes_payload,
            tipo_conteudo="application/json",
            metadados={
                "batch_id": id_lote,
                "feed_id": feed.identificador,
                "payload_sha256": hash_payload,
            },
        )

        if checkpoint.estado != EstadoCheckpointLote.CONCLUIDO:
            self._checkpoints.atualizar_estado_lote(
                id_lote=id_lote,
                novo_estado=EstadoCheckpointLote.PAYLOAD_GRAVADO,
                total_itens_esperados=len(noticias),
                instante_utc=agora_utc,
            )

        return self._gravar_itens_do_lote(
            id_lote=id_lote,
            identificador_feed=feed.identificador,
            chave_payload=chave_payload,
            noticias=noticias,
            payload_criado=payload_criado,
            agora_utc=agora_utc,
        )

    def _enviar_para_quarentena(
        self,
        feed: ConfiguracaoFeedRss,
        id_lote: str,
        envelope_payload: Mapping[str, object],
        motivo_erro: str,
        agora_utc: datetime,
    ) -> ResultadoPersistenciaBronze:
        chave_quarentena = self._chave_s3_quarentena(
            feed.identificador, id_lote, agora_utc
        )
        envelope_quarentena = dict(envelope_payload)
        envelope_quarentena["quarantine_reason"] = motivo_erro
        bytes_quarentena = json.dumps(
            envelope_quarentena, ensure_ascii=False, sort_keys=True
        ).encode("utf-8")

        _, criado = self._cliente_s3.gravar_objeto_idempotente(
            bucket=self._config.bucket_quarentena,
            chave_objeto=chave_quarentena,
            conteudo_bytes=bytes_quarentena,
            tipo_conteudo="application/json",
            metadados={
                "batch_id": id_lote,
                "feed_id": feed.identificador,
                "quarantine": "true",
            },
        )
        self._checkpoints.atualizar_estado_lote(
            id_lote=id_lote,
            novo_estado=EstadoCheckpointLote.QUARENTENA,
            motivo_erro=motivo_erro,
            instante_utc=agora_utc,
        )
        return ResultadoPersistenciaBronze(
            id_lote=id_lote,
            identificador_feed=feed.identificador,
            estado_final=EstadoCheckpointLote.QUARENTENA,
            bucket_destino=self._config.bucket_quarentena,
            chave_s3_payload=chave_quarentena,
            chaves_s3_itens=(),
            payload_novo_gravado=criado,
            itens_novos_gravados=0,
            itens_idempotentes_ignorados=0,
            enviado_quarentena=True,
        )

    def _gravar_itens_do_lote(
        self,
        id_lote: str,
        identificador_feed: str,
        chave_payload: str,
        noticias: Sequence[NoticiaRssColetada],
        payload_criado: bool,
        agora_utc: datetime,
    ) -> ResultadoPersistenciaBronze:
        chaves_itens: list[str] = []
        novos_gravados = 0
        ignorados_idempotencia = 0

        try:
            for noticia in noticias:
                chave_item = self._chave_s3_item_bronze(identificador_feed, noticia)
                documento_item = {
                    "batch_id": id_lote,
                    "feed_id": identificador_feed,
                    "guid": noticia.guid_item,
                    "title": noticia.titulo,
                    "link": noticia.link,
                    "summary": noticia.resumo,
                    "categories": list(noticia.categorias),
                    "published_at_utc": noticia.publicado_em_utc.isoformat(),
                    "collected_at_utc": noticia.coletado_em_utc.isoformat(),
                    "dedup_hash": noticia.hash_deduplicacao,
                }
                bytes_item = json.dumps(
                    documento_item, ensure_ascii=False, sort_keys=True
                ).encode("utf-8")

                _, item_s3_criado = self._cliente_s3.gravar_objeto_idempotente(
                    bucket=self._config.bucket_bronze,
                    chave_objeto=chave_item,
                    conteudo_bytes=bytes_item,
                    tipo_conteudo="application/json",
                    metadados={
                        "batch_id": id_lote,
                        "feed_id": identificador_feed,
                        "dedup_hash": noticia.hash_deduplicacao,
                    },
                )
                registrado_sql = self._checkpoints.registrar_item_bronze(
                    hash_deduplicacao=noticia.hash_deduplicacao,
                    id_lote=id_lote,
                    identificador_feed=identificador_feed,
                    chave_s3_item=chave_item,
                    publicado_em_utc=noticia.publicado_em_utc,
                    instante_utc=agora_utc,
                )
                chaves_itens.append(chave_item)
                if item_s3_criado and registrado_sql:
                    novos_gravados += 1
                else:
                    ignorados_idempotencia += 1
        except ErroArmazenamentoObjetos as erro_s3:
            self._checkpoints.atualizar_estado_lote(
                id_lote=id_lote,
                novo_estado=EstadoCheckpointLote.FALHA_PARCIAL,
                total_itens_esperados=len(noticias),
                total_itens_gravados=len(chaves_itens),
                motivo_erro=str(erro_s3),
                instante_utc=agora_utc,
            )
            raise

        self._checkpoints.atualizar_estado_lote(
            id_lote=id_lote,
            novo_estado=EstadoCheckpointLote.CONCLUIDO,
            total_itens_esperados=len(noticias),
            total_itens_gravados=len(chaves_itens),
            motivo_erro=None,
            instante_utc=agora_utc,
        )

        return ResultadoPersistenciaBronze(
            id_lote=id_lote,
            identificador_feed=identificador_feed,
            estado_final=EstadoCheckpointLote.CONCLUIDO,
            bucket_destino=self._config.bucket_bronze,
            chave_s3_payload=chave_payload,
            chaves_s3_itens=tuple(chaves_itens),
            payload_novo_gravado=payload_criado,
            itens_novos_gravados=novos_gravados,
            itens_idempotentes_ignorados=ignorados_idempotencia,
            enviado_quarentena=False,
        )

    def reprocessar_lote_desde_bronze(
        self,
        id_lote: str,
        momento_replay_utc: datetime | None = None,
    ) -> ResultadoPersistenciaBronze:
        """Executa replay a partir do payload bruto já persistido na camada Bronze S3."""
        agora_utc = (
            momento_replay_utc.astimezone(UTC)
            if momento_replay_utc is not None
            else datetime.now(tz=UTC)
        )
        checkpoint = self._checkpoints.obter_lote(id_lote)
        if checkpoint is None:
            raise ErroTransicaoCheckpoint(
                f"Não é possível executar replay: lote '{id_lote}' não encontrado."
            )

        objeto_payload = self._cliente_s3.ler_objeto(
            bucket=self._config.bucket_bronze,
            chave_objeto=checkpoint.chave_s3_payload,
        )
        mapa_envelope = json.loads(objeto_payload.conteudo_bytes.decode("utf-8"))
        xml_bruto = str(mapa_envelope.get("raw_xml", ""))

        noticias, _ = AnalisadorXmlRss.extrair_noticias(
            identificador_feed=checkpoint.identificador_feed,
            conteudo_xml=xml_bruto,
            momento_coleta_utc=agora_utc,
        )

        if checkpoint.estado != EstadoCheckpointLote.CONCLUIDO:
            self._checkpoints.atualizar_estado_lote(
                id_lote=id_lote,
                novo_estado=EstadoCheckpointLote.PAYLOAD_GRAVADO,
                total_itens_esperados=len(noticias),
                instante_utc=agora_utc,
            )

        return self._gravar_itens_do_lote(
            id_lote=id_lote,
            identificador_feed=checkpoint.identificador_feed,
            chave_payload=checkpoint.chave_s3_payload,
            noticias=noticias,
            payload_criado=False,
            agora_utc=agora_utc,
        )
