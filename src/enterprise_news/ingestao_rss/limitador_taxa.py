"""Controlador de limite de requisições por minuto por domínio (rate limiter)."""

from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import final

from enterprise_news.nucleo_dominio.excecoes_dominio import ErroLimiteTaxaDominio


@final
class LimitadorTaxaDominio:
    """Controlador de limite de requisições por minuto por domínio usando janela deslizante."""

    def __init__(
        self,
        maximo_requisicoes_por_minuto: int,
        relogio_monotonico: Callable[[], float] | None = None,
        janela_segundos: float = 60.0,
    ) -> None:
        if maximo_requisicoes_por_minuto <= 0:
            raise ValueError("O limite de requisições por minuto deve ser positivo.")
        self._maximo_requisicoes = maximo_requisicoes_por_minuto
        self._janela_segundos = janela_segundos
        self._relogio = (
            relogio_monotonico if relogio_monotonico is not None else self._agora_padrao
        )
        self._historico_por_dominio: defaultdict[str, deque[float]] = defaultdict(deque)

    @staticmethod
    def _agora_padrao() -> float:
        return datetime.now(tz=UTC).timestamp()

    def registrar_acesso(self, dominio: str) -> None:
        """Verifica e registra acesso ao domínio ou lança ErroLimiteTaxaDominio."""
        dominio_chave = dominio.strip().lower()
        instante_atual = self._relogio()
        fila_tempos = self._historico_por_dominio[dominio_chave]

        limite_inferior = instante_atual - self._janela_segundos
        while fila_tempos and fila_tempos[0] <= limite_inferior:
            fila_tempos.popleft()

        if len(fila_tempos) >= self._maximo_requisicoes:
            tempo_restante = max(0.1, (fila_tempos[0] + self._janela_segundos) - instante_atual)
            raise ErroLimiteTaxaDominio(
                f"Limite de taxa atingido para o domínio '{dominio_chave}' "
                f"({self._maximo_requisicoes} req/{self._janela_segundos}s).",
                aguardar_segundos=tempo_restante,
            )

        fila_tempos.append(instante_atual)

