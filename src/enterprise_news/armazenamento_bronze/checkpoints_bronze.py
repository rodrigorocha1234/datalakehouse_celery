"""Repositório SQL de checkpoints transacionais de lotes e itens da camada Bronze."""

import sqlite3
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import final

from enterprise_news.nucleo_dominio.excecoes_dominio import ErroTransicaoCheckpoint


class EstadoCheckpointLote(StrEnum):
    """Estados do ciclo de vida transacional de um lote (batch) na camada Bronze."""

    RECEBIDO = "RECEBIDO"
    PAYLOAD_GRAVADO = "PAYLOAD_GRAVADO"
    ITENS_PARCIAIS = "ITENS_PARCIAIS"
    CONCLUIDO = "CONCLUIDO"
    QUARENTENA = "QUARENTENA"
    FALHA_PARCIAL = "FALHA_PARCIAL"


@final
@dataclass(frozen=True)
class RegistroCheckpointBronze:
    """Registro persistido no banco operacional sobre o progresso de um lote Bronze."""

    id_lote: str
    identificador_feed: str
    hash_payload: str
    chave_s3_payload: str
    estado: EstadoCheckpointLote
    codigo_http: int
    total_itens_esperados: int
    total_itens_gravados: int
    iniciado_em_utc: datetime
    atualizado_em_utc: datetime
    motivo_erro: str | None = None


@final
class RepositorioCheckpointsBronzeSql:
    """Gerencia runs, checkpoints de lotes Bronze e itens gravados em SQL (PostgreSQL / SQLite)."""

    DDL_CHECKPOINTS_BRONZE: str = """
    CREATE TABLE IF NOT EXISTS enl_bronze_lotes (
        id_lote VARCHAR(80) PRIMARY KEY,
        identificador_feed VARCHAR(120) NOT NULL,
        hash_payload VARCHAR(64) NOT NULL,
        chave_s3_payload TEXT NOT NULL,
        estado VARCHAR(40) NOT NULL,
        codigo_http INTEGER NOT NULL,
        total_itens_esperados INTEGER NOT NULL DEFAULT 0,
        total_itens_gravados INTEGER NOT NULL DEFAULT 0,
        iniciado_em_utc TIMESTAMPTZ NOT NULL,
        atualizado_em_utc TIMESTAMPTZ NOT NULL,
        motivo_erro TEXT
    );
    CREATE TABLE IF NOT EXISTS enl_bronze_itens (
        hash_deduplicacao VARCHAR(64) PRIMARY KEY,
        id_lote VARCHAR(80) NOT NULL,
        identificador_feed VARCHAR(120) NOT NULL,
        chave_s3_item TEXT NOT NULL,
        publicado_em_utc TIMESTAMPTZ NOT NULL,
        gravado_em_utc TIMESTAMPTZ NOT NULL
    );
    """

    TRANSICOES_VALIDAS: Mapping[EstadoCheckpointLote, frozenset[EstadoCheckpointLote]] = {
        EstadoCheckpointLote.RECEBIDO: frozenset(
            {
                EstadoCheckpointLote.RECEBIDO,
                EstadoCheckpointLote.PAYLOAD_GRAVADO,
                EstadoCheckpointLote.QUARENTENA,
                EstadoCheckpointLote.FALHA_PARCIAL,
            }
        ),
        EstadoCheckpointLote.PAYLOAD_GRAVADO: frozenset(
            {
                EstadoCheckpointLote.PAYLOAD_GRAVADO,
                EstadoCheckpointLote.ITENS_PARCIAIS,
                EstadoCheckpointLote.CONCLUIDO,
                EstadoCheckpointLote.QUARENTENA,
                EstadoCheckpointLote.FALHA_PARCIAL,
            }
        ),
        EstadoCheckpointLote.ITENS_PARCIAIS: frozenset(
            {
                EstadoCheckpointLote.ITENS_PARCIAIS,
                EstadoCheckpointLote.CONCLUIDO,
                EstadoCheckpointLote.FALHA_PARCIAL,
            }
        ),
        EstadoCheckpointLote.FALHA_PARCIAL: frozenset(
            {
                EstadoCheckpointLote.PAYLOAD_GRAVADO,
                EstadoCheckpointLote.ITENS_PARCIAIS,
                EstadoCheckpointLote.CONCLUIDO,
                EstadoCheckpointLote.QUARENTENA,
                EstadoCheckpointLote.FALHA_PARCIAL,
            }
        ),
        EstadoCheckpointLote.CONCLUIDO: frozenset({EstadoCheckpointLote.CONCLUIDO}),
        EstadoCheckpointLote.QUARENTENA: frozenset({EstadoCheckpointLote.QUARENTENA}),
    }

    def __init__(self, caminho_sqlite: str = ":memory:") -> None:
        self._conexao = sqlite3.connect(caminho_sqlite)
        with self._conexao:
            self._conexao.executescript(self.DDL_CHECKPOINTS_BRONZE)

    def obter_lote(self, id_lote: str) -> RegistroCheckpointBronze | None:
        cursor = self._conexao.execute(
            """
            SELECT id_lote, identificador_feed, hash_payload, chave_s3_payload,
                   estado, codigo_http, total_itens_esperados, total_itens_gravados,
                   iniciado_em_utc, atualizado_em_utc, motivo_erro
            FROM enl_bronze_lotes
            WHERE id_lote = ?
            """,
            (id_lote,),
        )
        linha = cursor.fetchone()
        if linha is None:
            return None
        return RegistroCheckpointBronze(
            id_lote=str(linha[0]),
            identificador_feed=str(linha[1]),
            hash_payload=str(linha[2]),
            chave_s3_payload=str(linha[3]),
            estado=EstadoCheckpointLote(str(linha[4])),
            codigo_http=int(linha[5]),
            total_itens_esperados=int(linha[6]),
            total_itens_gravados=int(linha[7]),
            iniciado_em_utc=datetime.fromisoformat(str(linha[8])).astimezone(UTC),
            atualizado_em_utc=datetime.fromisoformat(str(linha[9])).astimezone(UTC),
            motivo_erro=str(linha[10]) if linha[10] is not None else None,
        )

    def iniciar_ou_retomar_lote(
        self,
        id_lote: str,
        identificador_feed: str,
        hash_payload: str,
        chave_s3_payload: str,
        codigo_http: int,
        instante_utc: datetime | None = None,
    ) -> RegistroCheckpointBronze:
        agora = instante_utc.astimezone(UTC) if instante_utc is not None else datetime.now(tz=UTC)
        existente = self.obter_lote(id_lote)
        if existente is not None:
            return existente

        with self._conexao:
            self._conexao.execute(
                """
                INSERT INTO enl_bronze_lotes (
                    id_lote, identificador_feed, hash_payload, chave_s3_payload,
                    estado, codigo_http, total_itens_esperados, total_itens_gravados,
                    iniciado_em_utc, atualizado_em_utc, motivo_erro
                ) VALUES (?, ?, ?, ?, ?, ?, 0, 0, ?, ?, NULL)
                """,
                (
                    id_lote,
                    identificador_feed,
                    hash_payload,
                    chave_s3_payload,
                    EstadoCheckpointLote.RECEBIDO.value,
                    codigo_http,
                    agora.isoformat(),
                    agora.isoformat(),
                ),
            )
        criado = self.obter_lote(id_lote)
        if criado is None:
            raise ErroTransicaoCheckpoint(f"Não foi possível inicializar o lote '{id_lote}'.")
        return criado

    def atualizar_estado_lote(
        self,
        id_lote: str,
        novo_estado: EstadoCheckpointLote,
        total_itens_esperados: int | None = None,
        total_itens_gravados: int | None = None,
        motivo_erro: str | None = None,
        instante_utc: datetime | None = None,
    ) -> RegistroCheckpointBronze:
        atual = self.obter_lote(id_lote)
        if atual is None:
            raise ErroTransicaoCheckpoint(f"Lote '{id_lote}' inexistente para transição.")

        permitidos = self.TRANSICOES_VALIDAS.get(atual.estado, frozenset())
        if novo_estado not in permitidos:
            raise ErroTransicaoCheckpoint(
                f"Transição inválida no lote '{id_lote}': '{atual.estado}' -> '{novo_estado}'."
            )

        agora = instante_utc.astimezone(UTC) if instante_utc is not None else datetime.now(tz=UTC)
        esperados = (
            total_itens_esperados
            if total_itens_esperados is not None
            else atual.total_itens_esperados
        )
        gravados = (
            total_itens_gravados
            if total_itens_gravados is not None
            else atual.total_itens_gravados
        )

        with self._conexao:
            self._conexao.execute(
                """
                UPDATE enl_bronze_lotes
                SET estado = ?,
                    total_itens_esperados = ?,
                    total_itens_gravados = ?,
                    atualizado_em_utc = ?,
                    motivo_erro = ?
                WHERE id_lote = ?
                """,
                (
                    novo_estado.value,
                    esperados,
                    gravados,
                    agora.isoformat(),
                    motivo_erro,
                    id_lote,
                ),
            )

        atualizado = self.obter_lote(id_lote)
        if atualizado is None:
            raise ErroTransicaoCheckpoint(f"Falha ao ler lote atualizado '{id_lote}'.")
        return atualizado

    def registrar_item_bronze(
        self,
        hash_deduplicacao: str,
        id_lote: str,
        identificador_feed: str,
        chave_s3_item: str,
        publicado_em_utc: datetime,
        instante_utc: datetime | None = None,
    ) -> bool:
        """Registra o item Bronze de forma idempotente; retorna True se inserido agora."""
        agora = instante_utc.astimezone(UTC) if instante_utc is not None else datetime.now(tz=UTC)
        with self._conexao:
            cursor = self._conexao.execute(
                """
                INSERT OR IGNORE INTO enl_bronze_itens (
                    hash_deduplicacao, id_lote, identificador_feed,
                    chave_s3_item, publicado_em_utc, gravado_em_utc
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    hash_deduplicacao,
                    id_lote,
                    identificador_feed,
                    chave_s3_item,
                    publicado_em_utc.astimezone(UTC).isoformat(),
                    agora.isoformat(),
                ),
            )
            return cursor.rowcount == 1

    def verificar_item_registrado(self, hash_deduplicacao: str) -> bool:
        cursor = self._conexao.execute(
            "SELECT 1 FROM enl_bronze_itens WHERE hash_deduplicacao = ?",
            (hash_deduplicacao,),
        )
        return cursor.fetchone() is not None

    def listar_lotes_incompletos(self) -> tuple[RegistroCheckpointBronze, ...]:
        cursor = self._conexao.execute(
            """
            SELECT id_lote
            FROM enl_bronze_lotes
            WHERE estado IN (?, ?, ?)
            ORDER BY iniciado_em_utc ASC
            """,
            (
                EstadoCheckpointLote.RECEBIDO.value,
                EstadoCheckpointLote.PAYLOAD_GRAVADO.value,
                EstadoCheckpointLote.FALHA_PARCIAL.value,
            ),
        )
        lotes: list[RegistroCheckpointBronze] = []
        for (id_lote_val,) in cursor.fetchall():
            lote = self.obter_lote(str(id_lote_val))
            if lote is not None:
                lotes.append(lote)
        return tuple(lotes)
