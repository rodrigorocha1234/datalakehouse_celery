"""Repositório operacional SQL (PostgreSQL DDL e SQLite transacional)."""

import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import final

from enterprise_news.ingestao_rss.analisador_xml import NoticiaRssColetada
from enterprise_news.persistencia_operacional.modelos_operacionais import (
    EstadoOperacionalFeed,
    RegistroMensagemDlq,
    StatusExecucaoFeed,
)


@final
class RepositorioOperacionalSql:
    """Repositório operacional SQL (compatível com PostgreSQL DDL e SQLite transacional)."""

    DDL_TABELAS_POSTGRESQL: str = """
    CREATE TABLE IF NOT EXISTS enl_controle_feeds (
        identificador_feed VARCHAR(120) PRIMARY KEY,
        etag TEXT,
        ultima_modificacao TEXT,
        bloqueado_ate_utc TIMESTAMPTZ,
        ultimo_status VARCHAR(40) NOT NULL,
        ultima_execucao_utc TIMESTAMPTZ,
        total_coletados INTEGER NOT NULL DEFAULT 0,
        total_duplicados INTEGER NOT NULL DEFAULT 0,
        total_falhas INTEGER NOT NULL DEFAULT 0,
        ultimo_erro TEXT
    );
    CREATE TABLE IF NOT EXISTS enl_hashes_noticias (
        hash_deduplicacao VARCHAR(64) PRIMARY KEY,
        identificador_feed VARCHAR(120) NOT NULL,
        guid_item TEXT NOT NULL,
        publicado_em_utc TIMESTAMPTZ NOT NULL,
        coletado_em_utc TIMESTAMPTZ NOT NULL
    );
    CREATE TABLE IF NOT EXISTS enl_registros_dlq (
        identificador_feed VARCHAR(120) NOT NULL,
        fila_origem VARCHAR(120) NOT NULL,
        fila_dlq VARCHAR(120) NOT NULL,
        exchange_dlx VARCHAR(120) NOT NULL,
        tentativas_executadas INTEGER NOT NULL,
        motivo_erro TEXT NOT NULL,
        registrado_em_utc TIMESTAMPTZ NOT NULL
    );
    """

    def __init__(self, caminho_sqlite: str = ":memory:") -> None:
        self._conexao = sqlite3.connect(caminho_sqlite)
        self._inicializar_schema()

    def _inicializar_schema(self) -> None:
        with self._conexao:
            self._conexao.executescript(self.DDL_TABELAS_POSTGRESQL)

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
        atual = self.obter_estado_feed(identificador_feed)
        if atual.bloqueado_ate_utc is not None and atual.bloqueado_ate_utc > agora:
            return False

        bloqueado_ate = (agora + timedelta(seconds=duracao_segundos)).isoformat()
        with self._conexao:
            self._conexao.execute(
                """
                INSERT INTO enl_controle_feeds (
                    identificador_feed, bloqueado_ate_utc, ultimo_status
                ) VALUES (?, ?, ?)
                ON CONFLICT(identificador_feed) DO UPDATE SET
                    bloqueado_ate_utc = excluded.bloqueado_ate_utc,
                    ultimo_status = excluded.ultimo_status
                """,
                (identificador_feed, bloqueado_ate, StatusExecucaoFeed.EM_EXECUCAO.value),
            )
        return True

    def liberar_bloqueio_feed(self, identificador_feed: str) -> None:
        with self._conexao:
            self._conexao.execute(
                "UPDATE enl_controle_feeds SET bloqueado_ate_utc = NULL "
                "WHERE identificador_feed = ?",
                (identificador_feed,),
            )

    def obter_estado_feed(self, identificador_feed: str) -> EstadoOperacionalFeed:
        cursor = self._conexao.execute(
            """
            SELECT etag, ultima_modificacao, bloqueado_ate_utc, ultimo_status,
                   ultima_execucao_utc, total_coletados, total_duplicados,
                   total_falhas, ultimo_erro
            FROM enl_controle_feeds
            WHERE identificador_feed = ?
            """,
            (identificador_feed,),
        )
        linha = cursor.fetchone()
        if linha is None:
            return EstadoOperacionalFeed(identificador_feed=identificador_feed)

        etag_val: str | None = str(linha[0]) if linha[0] is not None else None
        mod_val: str | None = str(linha[1]) if linha[1] is not None else None
        bloq_val = (
            datetime.fromisoformat(str(linha[2])).astimezone(UTC)
            if linha[2] is not None
            else None
        )
        status_val = StatusExecucaoFeed(str(linha[3]))
        exec_val = (
            datetime.fromisoformat(str(linha[4])).astimezone(UTC)
            if linha[4] is not None
            else None
        )
        return EstadoOperacionalFeed(
            identificador_feed=identificador_feed,
            etag=etag_val,
            ultima_modificacao=mod_val,
            bloqueado_ate_utc=bloq_val,
            ultimo_status=status_val,
            ultima_execucao_utc=exec_val,
            total_coletados=int(linha[5]),
            total_duplicados=int(linha[6]),
            total_falhas=int(linha[7]),
            ultimo_erro=str(linha[8]) if linha[8] is not None else None,
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
        duplicadas_banco = 0

        with self._conexao:
            for noticia in noticias_novas:
                cursor = self._conexao.execute(
                    """
                    INSERT OR IGNORE INTO enl_hashes_noticias (
                        hash_deduplicacao, identificador_feed, guid_item,
                        publicado_em_utc, coletado_em_utc
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        noticia.hash_deduplicacao,
                        noticia.identificador_feed,
                        noticia.guid_item,
                        noticia.publicado_em_utc.isoformat(),
                        noticia.coletado_em_utc.isoformat(),
                    ),
                )
                if cursor.rowcount == 1:
                    inseridas += 1
                else:
                    duplicadas_banco += 1

            duplicadas_ciclo = duplicadas_intra_feed + duplicadas_banco
            novo_status = (
                StatusExecucaoFeed.NAO_MODIFICADO_304
                if nao_modificado_304
                else StatusExecucaoFeed.SUCESSO
            )
            etag_final = novo_etag if novo_etag is not None else atual.etag
            mod_final = (
                nova_ultima_modificacao
                if nova_ultima_modificacao is not None
                else atual.ultima_modificacao
            )

            self._conexao.execute(
                """
                INSERT INTO enl_controle_feeds (
                    identificador_feed, etag, ultima_modificacao, bloqueado_ate_utc,
                    ultimo_status, ultima_execucao_utc, total_coletados,
                    total_duplicados, total_falhas, ultimo_erro
                ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(identificador_feed) DO UPDATE SET
                    etag = excluded.etag,
                    ultima_modificacao = excluded.ultima_modificacao,
                    bloqueado_ate_utc = NULL,
                    ultimo_status = excluded.ultimo_status,
                    ultima_execucao_utc = excluded.ultima_execucao_utc,
                    total_coletados = excluded.total_coletados,
                    total_duplicados = excluded.total_duplicados,
                    ultimo_erro = NULL
                """,
                (
                    identificador_feed,
                    etag_final,
                    mod_final,
                    novo_status.value,
                    agora.isoformat(),
                    atual.total_coletados + inseridas,
                    atual.total_duplicados + duplicadas_ciclo,
                    atual.total_falhas,
                ),
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
        with self._conexao:
            self._conexao.execute(
                """
                INSERT INTO enl_controle_feeds (
                    identificador_feed, etag, ultima_modificacao, bloqueado_ate_utc,
                    ultimo_status, ultima_execucao_utc, total_coletados,
                    total_duplicados, total_falhas, ultimo_erro
                ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(identificador_feed) DO UPDATE SET
                    bloqueado_ate_utc = NULL,
                    ultimo_status = excluded.ultimo_status,
                    ultima_execucao_utc = excluded.ultima_execucao_utc,
                    total_falhas = excluded.total_falhas,
                    ultimo_erro = excluded.ultimo_erro
                """,
                (
                    identificador_feed,
                    atual.etag,
                    atual.ultima_modificacao,
                    status.value,
                    agora.isoformat(),
                    atual.total_coletados,
                    atual.total_duplicados,
                    atual.total_falhas + 1,
                    motivo_erro,
                ),
            )
        return self.obter_estado_feed(identificador_feed)

    def registrar_envio_dlq(self, registro: RegistroMensagemDlq) -> None:
        with self._conexao:
            self._conexao.execute(
                """
                INSERT INTO enl_registros_dlq (
                    identificador_feed, fila_origem, fila_dlq, exchange_dlx,
                    tentativas_executadas, motivo_erro, registrado_em_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    registro.identificador_feed,
                    registro.fila_origem,
                    registro.fila_dlq,
                    registro.exchange_dlx,
                    registro.tentativas_executadas,
                    registro.motivo_erro,
                    registro.registrado_em_utc.isoformat(),
                ),
            )

    def listar_registros_dlq(self) -> tuple[RegistroMensagemDlq, ...]:
        cursor = self._conexao.execute(
            """
            SELECT identificador_feed, fila_origem, fila_dlq, exchange_dlx,
                   tentativas_executadas, motivo_erro, registrado_em_utc
            FROM enl_registros_dlq
            """
        )
        registros: list[RegistroMensagemDlq] = []
        for linha in cursor.fetchall():
            registros.append(
                RegistroMensagemDlq(
                    identificador_feed=str(linha[0]),
                    fila_origem=str(linha[1]),
                    fila_dlq=str(linha[2]),
                    exchange_dlx=str(linha[3]),
                    tentativas_executadas=int(linha[4]),
                    motivo_erro=str(linha[5]),
                    registrado_em_utc=datetime.fromisoformat(str(linha[6])).astimezone(
                        UTC
                    ),
                )
            )
        return tuple(registros)
