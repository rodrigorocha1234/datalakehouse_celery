"""Implementação em memória do repositório operacional para testes rápidos."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import final

from enterprise_news.ingestao_rss.analisador_xml import NoticiaRssColetada
from enterprise_news.persistencia_operacional.modelos_operacionais import (
    EstadoOperacionalFeed,
    RegistroMensagemDlq,
    StatusExecucaoFeed,
)


@final
class RepositorioOperacionalMemoria:
    """Implementação em memória para testes unitários rápidos e determinísticos."""

    def __init__(self) -> None:
        self._estados: dict[str, EstadoOperacionalFeed] = {}
        self._hashes_conhecidos: set[str] = set()
        self._registros_dlq: list[RegistroMensagemDlq] = []

    def adquirir_bloqueio_feed(
        self,
        identificador_feed: str,
        duracao_segundos: int,
        instante_utc: datetime | None = None,
    ) -> bool:
        agora = (
            instante_utc.astimezone(UTC)
            if instante_utc is not None
            else datetime.now(tz=UTC)
        )
        atual = self._estados.get(
            identificador_feed,
            EstadoOperacionalFeed(identificador_feed=identificador_feed),
        )
        if atual.bloqueado_ate_utc is not None and atual.bloqueado_ate_utc > agora:
            return False

        self._estados[identificador_feed] = replace(
            atual,
            bloqueado_ate_utc=agora + timedelta(seconds=duracao_segundos),
            ultimo_status=StatusExecucaoFeed.EM_EXECUCAO,
        )
        return True

    def liberar_bloqueio_feed(self, identificador_feed: str) -> None:
        atual = self._estados.get(identificador_feed)
        if atual is not None:
            self._estados[identificador_feed] = replace(atual, bloqueado_ate_utc=None)

    def obter_estado_feed(self, identificador_feed: str) -> EstadoOperacionalFeed:
        return self._estados.get(
            identificador_feed,
            EstadoOperacionalFeed(identificador_feed=identificador_feed),
        )

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
        agora = (
            instante_utc.astimezone(UTC)
            if instante_utc is not None
            else datetime.now(tz=UTC)
        )
        atual = self.obter_estado_feed(identificador_feed)

        inseridas = 0
        duplicadas_historico = 0
        for noticia in noticias_novas:
            if noticia.hash_deduplicacao in self._hashes_conhecidos:
                duplicadas_historico += 1
            else:
                self._hashes_conhecidos.add(noticia.hash_deduplicacao)
                inseridas += 1

        duplicadas_ciclo = duplicadas_intra_feed + duplicadas_historico
        novo_status = (
            StatusExecucaoFeed.NAO_MODIFICADO_304
            if nao_modificado_304
            else StatusExecucaoFeed.SUCESSO
        )

        self._estados[identificador_feed] = replace(
            atual,
            etag=novo_etag if novo_etag is not None else atual.etag,
            ultima_modificacao=(
                nova_ultima_modificacao
                if nova_ultima_modificacao is not None
                else atual.ultima_modificacao
            ),
            bloqueado_ate_utc=None,
            ultimo_status=novo_status,
            ultima_execucao_utc=agora,
            total_coletados=atual.total_coletados + inseridas,
            total_duplicados=atual.total_duplicados + duplicadas_ciclo,
            ultimo_erro=None,
        )
        return inseridas, duplicadas_ciclo

    def registrar_falha_coleta(
        self,
        identificador_feed: str,
        motivo_erro: str,
        enviado_dlq: bool = False,
        instante_utc: datetime | None = None,
    ) -> EstadoOperacionalFeed:
        agora = (
            instante_utc.astimezone(UTC)
            if instante_utc is not None
            else datetime.now(tz=UTC)
        )
        atual = self.obter_estado_feed(identificador_feed)
        status = (
            StatusExecucaoFeed.ENVIADO_DLQ
            if enviado_dlq
            else StatusExecucaoFeed.FALHA_TRANSITORIA
        )
        novo_estado = replace(
            atual,
            bloqueado_ate_utc=None,
            ultimo_status=status,
            ultima_execucao_utc=agora,
            total_falhas=atual.total_falhas + 1,
            ultimo_erro=motivo_erro,
        )
        self._estados[identificador_feed] = novo_estado
        return novo_estado

    def registrar_envio_dlq(self, registro: RegistroMensagemDlq) -> None:
        self._registros_dlq.append(registro)

    def listar_registros_dlq(self) -> tuple[RegistroMensagemDlq, ...]:
        return tuple(self._registros_dlq)

