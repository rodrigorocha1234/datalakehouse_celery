"""Subpacote de ingestão HTTP condicional, rate limiting e parsing XML de feeds RSS."""

from enterprise_news.ingestao_rss.analisador_xml import (
    AnalisadorXmlRss,
    NoticiaRssColetada,
    ResultadoColetaFeed,
)
from enterprise_news.ingestao_rss.coletor_feed import ColetorFeedRss
from enterprise_news.ingestao_rss.limitador_taxa import LimitadorTaxaDominio
from enterprise_news.ingestao_rss.transporte_http import (
    CabecalhoCondicionalHttp,
    ProtocoloTransporteHttp,
    RespostaHttpBruta,
    TransporteRequestsHttp,
)

__all__ = [
    "AnalisadorXmlRss",
    "CabecalhoCondicionalHttp",
    "ColetorFeedRss",
    "LimitadorTaxaDominio",
    "NoticiaRssColetada",
    "ProtocoloTransporteHttp",
    "RespostaHttpBruta",
    "ResultadoColetaFeed",
    "TransporteRequestsHttp",
]

