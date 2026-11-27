"""Serviço de coleta HTTP condicional de feeds RSS."""

from typing import final

from enterprise_news.gestao_configuracao.configuracao_rss import (
    ConfiguracaoFeedRss,
    ConfiguracaoRss,
)
from enterprise_news.ingestao_rss.analisador_xml import (
    AnalisadorXmlRss,
    ResultadoColetaFeed,
)
from enterprise_news.ingestao_rss.limitador_taxa import LimitadorTaxaDominio
from enterprise_news.ingestao_rss.transporte_http import (
    CabecalhoCondicionalHttp,
    ProtocoloTransporteHttp,
    TransporteRequestsHttp,
)
from enterprise_news.nucleo_dominio.excecoes_dominio import (
    ErroLimiteTaxaDominio,
    ErroTransporteHttpRss,
)


@final
class ColetorFeedRss:
    """Serviço de coleta HTTP condicional, rate limiting e parsing RSS."""

    def __init__(
        self,
        configuracao_rss: ConfiguracaoRss,
        transporte_http: ProtocoloTransporteHttp | None = None,
        limitador_taxa: LimitadorTaxaDominio | None = None,
    ) -> None:
        self._configuracao_rss = configuracao_rss
        self._transporte_http: ProtocoloTransporteHttp = (
            transporte_http if transporte_http is not None else TransporteRequestsHttp()
        )
        self._limitador_taxa = (
            limitador_taxa
            if limitador_taxa is not None
            else LimitadorTaxaDominio(
                maximo_requisicoes_por_minuto=configuracao_rss.limite_requisicoes_por_minuto
            )
        )

    def coletar_feed(
        self,
        feed: ConfiguracaoFeedRss,
        cabecalho_condicional: CabecalhoCondicionalHttp | None = None,
    ) -> ResultadoColetaFeed:
        """Executa a coleta de um feed RSS respeitando rate limit e ETag/Last-Modified."""
        self._limitador_taxa.registrar_acesso(feed.dominio)

        condicional = (
            cabecalho_condicional
            if cabecalho_condicional is not None
            else CabecalhoCondicionalHttp()
        )
        cabecalhos_req = condicional.para_cabecalhos_requisicao(
            agente_usuario=self._configuracao_rss.agente_usuario
        )

        resposta = self._transporte_http.buscar_recurso(
            url=feed.url,
            cabecalhos=cabecalhos_req,
            tempo_limite_segundos=self._configuracao_rss.tempo_limite_segundos,
        )

        cabecalhos_resp = {k.lower(): v for k, v in resposta.cabecalhos.items()}
        novo_etag = cabecalhos_resp.get("etag", condicional.etag)
        nova_modificacao = cabecalhos_resp.get(
            "last-modified", condicional.ultima_modificacao
        )

        if resposta.codigo_status == 304:
            return ResultadoColetaFeed(
                identificador_feed=feed.identificador,
                codigo_http=304,
                nao_modificado=True,
                novo_etag=novo_etag,
                nova_ultima_modificacao=nova_modificacao,
                noticias_unicas=(),
                quantidade_duplicadas_ignoradas=0,
            )

        if resposta.codigo_status == 429:
            retry_after_bruto = cabecalhos_resp.get("retry-after", "30")
            try:
                aguardar = max(1.0, float(retry_after_bruto))
            except ValueError:
                aguardar = 30.0
            raise ErroLimiteTaxaDominio(
                "Servidor retornou HTTP 429 (Too Many Requests) "
                f"para o feed '{feed.identificador}'.",
                aguardar_segundos=aguardar,
            )

        if resposta.codigo_status >= 400:
            raise ErroTransporteHttpRss(
                f"Falha HTTP {resposta.codigo_status} ao coletar feed '{feed.identificador}'.",
                codigo_http=resposta.codigo_status,
            )

        noticias, duplicadas = AnalisadorXmlRss.extrair_noticias(
            identificador_feed=feed.identificador,
            conteudo_xml=resposta.corpo_texto,
        )

        return ResultadoColetaFeed(
            identificador_feed=feed.identificador,
            codigo_http=resposta.codigo_status,
            nao_modificado=False,
            novo_etag=novo_etag,
            nova_ultima_modificacao=nova_modificacao,
            noticias_unicas=noticias,
            quantidade_duplicadas_ignoradas=duplicadas,
        )

