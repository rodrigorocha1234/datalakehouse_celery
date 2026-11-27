"""Política de backoff exponencial com jitter e relatórios de despacho Celery."""

import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import final

from enterprise_news.persistencia_operacional.modelos_operacionais import StatusExecucaoFeed


@final
@dataclass(frozen=True)
class PoliticaRetentativaCelery:
    """Política de backoff exponencial com jitter e encaminhamento DLX/DLQ."""

    maximo_tentativas: int
    recuo_base_segundos: int
    recuo_maximo_segundos: int
    usar_jitter: bool
    fila_origem: str
    fila_dlq: str
    exchange_dlx: str

    def calcular_atraso_segundos(
        self,
        numero_tentativa: int,
        gerador_aleatorio: Callable[[float, float], float] | None = None,
    ) -> float:
        """Calcula o atraso exponencial com jitter para a tentativa informada (base 1)."""
        tentativa_normalizada = max(1, numero_tentativa)
        atraso_exponencial = min(
            float(self.recuo_maximo_segundos),
            float(self.recuo_base_segundos) * (2.0 ** (tentativa_normalizada - 1)),
        )
        if not self.usar_jitter:
            return atraso_exponencial

        funcao_sorteio = (
            gerador_aleatorio if gerador_aleatorio is not None else random.uniform
        )
        return round(funcao_sorteio(atraso_exponencial * 0.5, atraso_exponencial), 3)


@final
@dataclass(frozen=True)
class ResultadoTarefaIngestaoFeed:
    """Resultado individual da execução de uma tarefa Celery por feed."""

    identificador_feed: str
    fila_celery: str
    status: StatusExecucaoFeed
    codigo_http: int | None
    noticias_inseridas: int
    noticias_duplicadas: int
    tentativas_executadas: int
    encaminhado_dlq: bool
    atrasos_retentativa_segundos: tuple[float, ...]
    mensagem_erro: str | None = None


@final
@dataclass(frozen=True)
class EspecificacaoDespachoFeed:
    """Especificação de agendamento e roteamento Celery para um único feed."""

    nome_tarefa: str
    identificador_feed: str
    fila_destino: str
    intervalo_segundos: int
    exchange_dlx: str
    routing_key_dlq: str


@final
@dataclass(frozen=True)
class RelatorioLoteIngestaoRss:
    """Resumo consolidado do despacho de 1..N feeds elegíveis em grupo."""

    total_feeds_configurados: int
    total_feeds_elegiveis: int
    resultados_por_feed: tuple[ResultadoTarefaIngestaoFeed, ...]

    @property
    def total_sucesso(self) -> int:
        return sum(
            1
            for item in self.resultados_por_feed
            if item.status
            in (StatusExecucaoFeed.SUCESSO, StatusExecucaoFeed.NAO_MODIFICADO_304)
        )

    @property
    def total_falhas_isoladas(self) -> int:
        return sum(
            1
            for item in self.resultados_por_feed
            if item.status
            in (StatusExecucaoFeed.FALHA_TRANSITORIA, StatusExecucaoFeed.ENVIADO_DLQ)
        )
