"""Modelos e contrato de persistência operacional para feeds RSS e DLQ."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol, final, runtime_checkable

from enterprise_news.ingestao_rss.analisador_xml import NoticiaRssColetada
from enterprise_news.ingestao_rss.transporte_http import CabecalhoCondicionalHttp


class StatusExecucaoFeed(StrEnum):
    """Estados operacionais de execução de um feed RSS."""

    OCIOSO = "OCIOSO"
    EM_EXECUCAO = "EM_EXECUCAO"
    SUCESSO = "SUCESSO"
    NAO_MODIFICADO_304 = "NAO_MODIFICADO_304"
    FALHA_TRANSITORIA = "FALHA_TRANSITORIA"
    ENVIADO_DLQ = "ENVIADO_DLQ"


@final
@dataclass(frozen=True)
class EstadoOperacionalFeed:
    """Registro operacional do estado de ingestão de um feed."""

    identificador_feed: str
    etag: str | None = None
    ultima_modificacao: str | None = None
    bloqueado_ate_utc: datetime | None = None
    ultimo_status: StatusExecucaoFeed = StatusExecucaoFeed.OCIOSO
    ultima_execucao_utc: datetime | None = None
    total_coletados: int = 0
    total_duplicados: int = 0
    total_falhas: int = 0
    ultimo_erro: str | None = None

    def obter_cabecalho_condicional(self) -> CabecalhoCondicionalHttp:
        """Retorna os metadados de ETag e Last-Modified armazenados para o feed."""
        return CabecalhoCondicionalHttp(
            etag=self.etag,
            ultima_modificacao=self.ultima_modificacao,
        )


@final
@dataclass(frozen=True)
class RegistroMensagemDlq:
    """Registro auditável de falha exaurida encaminhada para a Dead Letter Queue."""

    identificador_feed: str
    fila_origem: str
    fila_dlq: str
    exchange_dlx: str
    tentativas_executadas: int
    motivo_erro: str
    registrado_em_utc: datetime


@runtime_checkable
class ProtocoloRepositorioOperacional(Protocol):
    """Contrato para persistência operacional (PostgreSQL / SQLite) de ingestão RSS."""

    def adquirir_bloqueio_feed(
        self,
        identificador_feed: str,
        duracao_segundos: int,
        instante_utc: datetime | None = None,
    ) -> bool:
        """Adquire lock exclusivo por feed caso não haja execução ativa no momento."""
        ...

    def liberar_bloqueio_feed(self, identificador_feed: str) -> None:
        """Libera o lock exclusivo do feed."""
        ...

    def obter_estado_feed(self, identificador_feed: str) -> EstadoOperacionalFeed:
        """Recupera o estado operacional atual do feed."""
        ...

    def registrar_sucesso_coleta(
        self,
        identificador_feed: str,
        noticias_novas: Sequence[NoticiaRssColetada],
        duplicadas_intra_feed: int,
        novo_etag: str | None,
        nova_ultima_modificacao: str | None,
        nao_modificado_304: bool = False,
        instante_utc: datetime | None = None,
    ) -> tuple[int, int]:
        """Persiste metadados e hashes deduplicados, retornando (inseridas, duplicadas_total)."""
        ...

    def registrar_falha_coleta(
        self,
        identificador_feed: str,
        motivo_erro: str,
        enviado_dlq: bool = False,
        instante_utc: datetime | None = None,
    ) -> EstadoOperacionalFeed:
        """Registra falha transitória ou terminal e libera o lock do feed."""
        ...

    def registrar_envio_dlq(self, registro: RegistroMensagemDlq) -> None:
        """Armazena registro auditável na Dead Letter Queue operacional."""
        ...

    def listar_registros_dlq(self) -> tuple[RegistroMensagemDlq, ...]:
        """Retorna todos os registros encaminhados para a DLQ."""
        ...

