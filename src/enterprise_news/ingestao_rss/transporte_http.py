"""Transporte HTTP condicional (ETag / Last-Modified) para feeds RSS."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, final, runtime_checkable

import requests

from enterprise_news.nucleo_dominio.excecoes_dominio import ErroTransporteHttpRss


@final
@dataclass(frozen=True)
class CabecalhoCondicionalHttp:
    """Metadados HTTP para requisição condicional (ETag / Last-Modified)."""

    etag: str | None = None
    ultima_modificacao: str | None = None

    def para_cabecalhos_requisicao(self, agente_usuario: str) -> dict[str, str]:
        """Gera os cabeçalhos HTTP incluindo If-None-Match e If-Modified-Since."""
        cabecalhos: dict[str, str] = {
            "User-Agent": agente_usuario,
            "Accept": "application/rss+xml, application/xml;q=0.9, text/xml;q=0.8",
        }
        if self.etag:
            cabecalhos["If-None-Match"] = self.etag
        if self.ultima_modificacao:
            cabecalhos["If-Modified-Since"] = self.ultima_modificacao
        return cabecalhos


@final
@dataclass(frozen=True)
class RespostaHttpBruta:
    """Representa a resposta HTTP bruta de uma consulta de feed RSS."""

    codigo_status: int
    corpo_texto: str
    cabecalhos: Mapping[str, str]


@runtime_checkable
class ProtocoloTransporteHttp(Protocol):
    """Contrato para transporte HTTP desacoplado e testável."""

    def buscar_recurso(
        self,
        url: str,
        cabecalhos: Mapping[str, str],
        tempo_limite_segundos: int,
    ) -> RespostaHttpBruta:
        """Executa requisição HTTP GET e retorna status, corpo e cabeçalhos."""
        ...


@final
class TransporteRequestsHttp:
    """Implementação concreta de transporte HTTP usando requests."""

    def buscar_recurso(
        self,
        url: str,
        cabecalhos: Mapping[str, str],
        tempo_limite_segundos: int,
    ) -> RespostaHttpBruta:
        try:
            resposta = requests.get(
                url,
                headers=dict(cabecalhos),
                timeout=tempo_limite_segundos,
            )
        except requests.Timeout as erro:
            raise ErroTransporteHttpRss(
                f"Tempo limite excedido ({tempo_limite_segundos}s) ao consultar '{url}'."
            ) from erro
        except requests.RequestException as erro:
            raise ErroTransporteHttpRss(
                f"Erro de conexão HTTP ao consultar '{url}': {erro}"
            ) from erro

        cabecalhos_normalizados = {
            chave.lower(): valor for chave, valor in resposta.headers.items()
        }
        return RespostaHttpBruta(
            codigo_status=resposta.status_code,
            corpo_texto=resposta.text,
            cabecalhos=cabecalhos_normalizados,
        )

