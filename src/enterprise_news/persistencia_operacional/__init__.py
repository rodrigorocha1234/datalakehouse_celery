"""Subpacote de persistência operacional SQL e em memória (locks, ETag, deduplicação e DLQ)."""

from enterprise_news.persistencia_operacional.modelos_operacionais import (
    EstadoOperacionalFeed,
    ProtocoloRepositorioOperacional,
    RegistroMensagemDlq,
    StatusExecucaoFeed,
)
from enterprise_news.persistencia_operacional.repositorio_memoria import (
    RepositorioOperacionalMemoria,
)
from enterprise_news.persistencia_operacional.repositorio_sql import (
    RepositorioOperacionalSql,
)

__all__ = [
    "EstadoOperacionalFeed",
    "ProtocoloRepositorioOperacional",
    "RegistroMensagemDlq",
    "RepositorioOperacionalMemoria",
    "RepositorioOperacionalSql",
    "StatusExecucaoFeed",
]

