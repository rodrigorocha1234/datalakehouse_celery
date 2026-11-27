"""Testes automatizados da Etapa 2 — Ingestão assíncrona RSS e Celery."""

from collections.abc import Mapping
from pathlib import Path

import pytest

from enterprise_news.execucao_celery import OrquestradorIngestaoRss
from enterprise_news.gestao_configuracao import (
    CarregadorConfiguracao,
    ConfiguracaoFeedRss,
    ConfiguracaoRss,
)
from enterprise_news.ingestao_rss import (
    AnalisadorXmlRss,
    ColetorFeedRss,
    LimitadorTaxaDominio,
    RespostaHttpBruta,
)
from enterprise_news.nucleo_dominio import (
    ErroAnaliseXmlRss,
    ErroConcorrenciaFeed,
    ErroLimiteTaxaDominio,
    ErroTransporteHttpRss,
    ErroValidacaoConfiguracao,
)
from enterprise_news.persistencia_operacional import (
    RepositorioOperacionalMemoria,
    RepositorioOperacionalSql,
    StatusExecucaoFeed,
)

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

XML_RSS_EXEMPLO = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>G1 - Todas as notícias</title>
    <link>https://g1.globo.com/</link>
    <description>Notícias do G1</description>
    <item>
      <title>Notícia 1 sobre economia</title>
      <link>https://g1.globo.com/economia/noticia-1.ghtml</link>
      <guid>guid-noticia-1</guid>
      <pubDate>Thu, 26 Nov 2026 15:00:00 -0300</pubDate>
      <description>Resumo exclusivo do RSS da notícia 1.</description>
      <category>Economia</category>
    </item>
    <item>
      <title>Notícia 2 sobre tecnologia</title>
      <link>https://g1.globo.com/tecnologia/noticia-2.ghtml</link>
      <guid>guid-noticia-2</guid>
      <pubDate>Thu, 26 Nov 2026 16:30:00 -0300</pubDate>
      <description>Resumo exclusivo do RSS da notícia 2.</description>
      <category>Tecnologia</category>
    </item>
    <!-- Item duplicado dentro do mesmo XML -->
    <item>
      <title>Notícia 1 sobre economia</title>
      <link>https://g1.globo.com/economia/noticia-1.ghtml</link>
      <guid>guid-noticia-1</guid>
      <pubDate>Thu, 26 Nov 2026 15:00:00 -0300</pubDate>
      <description>Resumo exclusivo do RSS da notícia 1.</description>
      <category>Economia</category>
    </item>
  </channel>
</rss>
"""


class TransporteHttpSimulado:
    """Stub tipado de transporte HTTP para simulação de cenários de feed RSS."""

    def __init__(
        self,
        respostas_por_url: Mapping[str, list[RespostaHttpBruta | Exception]],
    ) -> None:
        self._respostas: dict[str, list[RespostaHttpBruta | Exception]] = {
            url: list(lista) for url, lista in respostas_por_url.items()
        }
        self.cabecalhos_recebidos: dict[str, list[dict[str, str]]] = {}

    def buscar_recurso(
        self,
        url: str,
        cabecalhos: Mapping[str, str],
        tempo_limite_segundos: int,
    ) -> RespostaHttpBruta:
        assert tempo_limite_segundos > 0
        self.cabecalhos_recebidos.setdefault(url, []).append(dict(cabecalhos))
        fila = self._respostas.get(url, [])
        if not fila:
            raise ErroTransporteHttpRss(f"Sem resposta configurada para '{url}'.", codigo_http=503)
        proximo = fila.pop(0)
        if isinstance(proximo, Exception):
            raise proximo
        return proximo


def _criar_config_rss_teste(feeds: tuple[ConfiguracaoFeedRss, ...]) -> ConfiguracaoRss:
    return ConfiguracaoRss(
        fonte="g1",
        habilitado=True,
        intervalo_padrao_minutos=60,
        tempo_limite_segundos=15,
        maximo_tentativas=3,
        recuo_tentativa_segundos=10,
        fila_celery="enl.rss.ingestion",
        feeds=feeds,
        recuo_maximo_segundos=120,
        jitter_tentativa=True,
        limite_requisicoes_por_minuto=30,
        capacidade_maxima_feeds=100,
    )


def test_carregamento_g1_rss_com_multiplos_feeds_e_elegibilidade() -> None:
    config = CarregadorConfiguracao.carregar_configuracao_rss(
        RAIZ_PROJETO / "config" / "g1_rss.yaml"
    )
    assert len(config.feeds) == 4
    elegiveis = tuple(config.iterar_feeds_elegiveis())
    assert len(elegiveis) == 3
    ids_elegiveis = {f.identificador for f in elegiveis}
    assert "g1_principal" in ids_elegiveis
    assert "g1_economia" in ids_elegiveis
    assert "g1_tecnologia" in ids_elegiveis
    assert "g1_educacao_inativo" not in ids_elegiveis


def test_exigencia_https_em_feeds_rss() -> None:
    with pytest.raises(ErroValidacaoConfiguracao, match="https"):
        ConfiguracaoFeedRss(
            identificador="feed_inseguro",
            nome="Feed HTTP",
            url="http://g1.globo.com/rss/g1/",
            habilitado=True,
            categoria="noticias",
            idioma="pt-BR",
            intervalo_minutos=60,
        )


def test_sucesso_ingestao_1_feed_e_conditional_get_304() -> None:
    url = "https://g1.globo.com/rss/g1/"
    feed = ConfiguracaoFeedRss(
        identificador="g1_principal",
        nome="G1 Principal",
        url=url,
        habilitado=True,
        categoria="noticias",
        idioma="pt-BR",
        intervalo_minutos=60,
    )
    config = _criar_config_rss_teste((feed,))
    transporte = TransporteHttpSimulado(
        {
            url: [
                RespostaHttpBruta(
                    codigo_status=200,
                    corpo_texto=XML_RSS_EXEMPLO,
                    cabecalhos={
                        "ETag": '"etag-v1"',
                        "Last-Modified": "Thu, 26 Nov 2026 18:00:00 GMT",
                    },
                ),
                RespostaHttpBruta(
                    codigo_status=304,
                    corpo_texto="",
                    cabecalhos={"ETag": '"etag-v1"'},
                ),
            ]
        }
    )
    repositorio = RepositorioOperacionalSql(":memory:")
    coletor = ColetorFeedRss(configuracao_rss=config, transporte_http=transporte)
    orquestrador = OrquestradorIngestaoRss(
        configuracao_rss=config,
        coletor_rss=coletor,
        repositorio_operacional=repositorio,
    )

    # 1ª execução: 200 OK com 2 itens únicos e 1 duplicado intra-feed
    res_1 = orquestrador.executar_tarefa_feed("g1_principal")
    assert res_1.status == StatusExecucaoFeed.SUCESSO
    assert res_1.codigo_http == 200
    assert res_1.noticias_inseridas == 2
    assert res_1.noticias_duplicadas == 1
    assert res_1.tentativas_executadas == 1
    assert res_1.encaminhado_dlq is False

    # 2ª execução: envia If-None-Match e If-Modified-Since e recebe 304 Not Modified
    res_2 = orquestrador.executar_tarefa_feed("g1_principal")
    assert res_2.status == StatusExecucaoFeed.NAO_MODIFICADO_304
    assert res_2.codigo_http == 304
    assert res_2.noticias_inseridas == 0
    cabecalhos_segunda_req = transporte.cabecalhos_recebidos[url][1]
    assert cabecalhos_segunda_req.get("If-None-Match") == '"etag-v1"'
    assert cabecalhos_segunda_req.get("If-Modified-Since") == "Thu, 26 Nov 2026 18:00:00 GMT"


def test_ingestao_429_rate_limit_e_recuperacao_com_retry() -> None:
    url = "https://g1.globo.com/rss/g1/economia/"
    feed = ConfiguracaoFeedRss(
        identificador="g1_economia",
        nome="G1 Economia",
        url=url,
        habilitado=True,
        categoria="economia",
        idioma="pt-BR",
        intervalo_minutos=30,
    )
    config = _criar_config_rss_teste((feed,))
    transporte = TransporteHttpSimulado(
        {
            url: [
                RespostaHttpBruta(
                    codigo_status=429,
                    corpo_texto="Too Many Requests",
                    cabecalhos={"Retry-After": "12"},
                ),
                RespostaHttpBruta(
                    codigo_status=200,
                    corpo_texto=XML_RSS_EXEMPLO,
                    cabecalhos={},
                ),
            ]
        }
    )
    repositorio = RepositorioOperacionalMemoria()
    coletor = ColetorFeedRss(configuracao_rss=config, transporte_http=transporte)
    orquestrador = OrquestradorIngestaoRss(
        configuracao_rss=config,
        coletor_rss=coletor,
        repositorio_operacional=repositorio,
    )

    resultado = orquestrador.executar_tarefa_feed("g1_economia")
    assert resultado.status == StatusExecucaoFeed.SUCESSO
    assert resultado.tentativas_executadas == 2
    assert resultado.atrasos_retentativa_segundos == (12.0,)
    assert resultado.noticias_inseridas == 2


@pytest.mark.parametrize(
    ("cenario", "respostas_simuladas"),
    [
        (
            "xml_invalido",
            [
                RespostaHttpBruta(200, "<rss><channel><item><title>Incompleto", {}),
                RespostaHttpBruta(200, "<rss><channel><item><title>Incompleto", {}),
                RespostaHttpBruta(200, "<rss><channel><item><title>Incompleto", {}),
            ],
        ),
        (
            "timeout_persistente",
            [
                ErroTransporteHttpRss("Tempo limite excedido (15s)"),
                ErroTransporteHttpRss("Tempo limite excedido (15s)"),
                ErroTransporteHttpRss("Tempo limite excedido (15s)"),
            ],
        ),
        (
            "indisponivel_503",
            [
                RespostaHttpBruta(503, "Service Unavailable", {}),
                RespostaHttpBruta(503, "Service Unavailable", {}),
                RespostaHttpBruta(503, "Service Unavailable", {}),
            ],
        ),
    ],
)
def test_falhas_exauridas_encaminhadas_para_dlq(
    cenario: str,
    respostas_simuladas: list[RespostaHttpBruta | Exception],
) -> None:
    url = f"https://g1.globo.com/rss/{cenario}/"
    feed = ConfiguracaoFeedRss(
        identificador=f"feed_{cenario}",
        nome=f"Feed {cenario}",
        url=url,
        habilitado=True,
        categoria="teste",
        idioma="pt-BR",
        intervalo_minutos=15,
    )
    config = _criar_config_rss_teste((feed,))
    transporte = TransporteHttpSimulado({url: respostas_simuladas})
    repositorio = RepositorioOperacionalSql(":memory:")
    coletor = ColetorFeedRss(configuracao_rss=config, transporte_http=transporte)
    orquestrador = OrquestradorIngestaoRss(
        configuracao_rss=config,
        coletor_rss=coletor,
        repositorio_operacional=repositorio,
        gerador_jitter=lambda minimo, maximo: round((minimo + maximo) / 2.0, 2),
    )

    resultado = orquestrador.executar_tarefa_feed(feed.identificador)
    assert resultado.status == StatusExecucaoFeed.ENVIADO_DLQ
    assert resultado.encaminhado_dlq is True
    assert resultado.tentativas_executadas == 3
    assert len(resultado.atrasos_retentativa_segundos) == 2

    registros_dlq = repositorio.listar_registros_dlq()
    assert len(registros_dlq) == 1
    assert registros_dlq[0].identificador_feed == feed.identificador
    assert registros_dlq[0].fila_dlq == "enl.ops.dlq"
    assert registros_dlq[0].exchange_dlx == "enl.dlx"


def test_isolamento_falha_em_lote_n_feeds_e_deduplicacao_entre_ciclos() -> None:
    feed_ok = ConfiguracaoFeedRss(
        identificador="g1_ok",
        nome="G1 OK",
        url="https://g1.globo.com/rss/ok/",
        habilitado=True,
        categoria="noticias",
        idioma="pt-BR",
        intervalo_minutos=30,
    )
    feed_falha = ConfiguracaoFeedRss(
        identificador="g1_falha",
        nome="G1 Falha",
        url="https://g1.globo.com/rss/falha/",
        habilitado=True,
        categoria="noticias",
        idioma="pt-BR",
        intervalo_minutos=45,
    )
    feed_inativo = ConfiguracaoFeedRss(
        identificador="g1_inativo",
        nome="G1 Inativo",
        url="https://g1.globo.com/rss/inativo/",
        habilitado=False,
        categoria="noticias",
        idioma="pt-BR",
        intervalo_minutos=60,
    )
    config = _criar_config_rss_teste((feed_ok, feed_falha, feed_inativo))
    transporte = TransporteHttpSimulado(
        {
            feed_ok.url: [
                RespostaHttpBruta(200, XML_RSS_EXEMPLO, {}),
                RespostaHttpBruta(200, XML_RSS_EXEMPLO, {}),
            ],
            feed_falha.url: [
                RespostaHttpBruta(502, "Bad Gateway", {}),
                RespostaHttpBruta(502, "Bad Gateway", {}),
                RespostaHttpBruta(502, "Bad Gateway", {}),
            ],
        }
    )
    repositorio = RepositorioOperacionalMemoria()
    coletor = ColetorFeedRss(configuracao_rss=config, transporte_http=transporte)
    orquestrador = OrquestradorIngestaoRss(
        configuracao_rss=config,
        coletor_rss=coletor,
        repositorio_operacional=repositorio,
    )

    agenda_beat = orquestrador.construir_agenda_beat()
    assert len(agenda_beat) == 2
    assert "enl_beat_rss_g1_ok" in agenda_beat
    assert "enl_beat_rss_g1_falha" in agenda_beat

    relatorio = orquestrador.despachar_grupo_feeds_elegiveis()
    assert relatorio.total_feeds_configurados == 3
    assert relatorio.total_feeds_elegiveis == 2
    assert relatorio.total_sucesso == 1
    assert relatorio.total_falhas_isoladas == 1

    # Re-execução do feed_ok com o mesmo XML deve deduplicar 100% dos itens já conhecidos
    res_repetido = orquestrador.executar_tarefa_feed("g1_ok")
    assert res_repetido.noticias_inseridas == 0
    assert res_repetido.noticias_duplicadas == 3


def test_prevencao_concorrencia_duplicada_por_feed_e_rate_limit_dominio() -> None:
    feed = ConfiguracaoFeedRss(
        identificador="g1_lock",
        nome="G1 Lock",
        url="https://g1.globo.com/rss/lock/",
        habilitado=True,
        categoria="noticias",
        idioma="pt-BR",
        intervalo_minutos=30,
    )
    config = _criar_config_rss_teste((feed,))
    repositorio = RepositorioOperacionalMemoria()
    assert repositorio.adquirir_bloqueio_feed("g1_lock", duracao_segundos=300) is True

    coletor = ColetorFeedRss(
        configuracao_rss=config,
        transporte_http=TransporteHttpSimulado({}),
    )
    orquestrador = OrquestradorIngestaoRss(
        configuracao_rss=config,
        coletor_rss=coletor,
        repositorio_operacional=repositorio,
    )

    with pytest.raises(ErroConcorrenciaFeed, match="lock ativo"):
        orquestrador.executar_tarefa_feed("g1_lock")

    # Teste de rate limit por domínio (janela deslizante)
    relogio_fixo = lambda: 1000.0  # noqa: E731
    limitador = LimitadorTaxaDominio(
        maximo_requisicoes_por_minuto=2,
        relogio_monotonico=relogio_fixo,
    )
    limitador.registrar_acesso("g1.globo.com")
    limitador.registrar_acesso("g1.globo.com")
    with pytest.raises(ErroLimiteTaxaDominio):
        limitador.registrar_acesso("g1.globo.com")


def test_rejeicao_xml_vazio_ou_raiz_desconhecida() -> None:
    with pytest.raises(ErroAnaliseXmlRss, match="vazio"):
        AnalisadorXmlRss.extrair_noticias("g1_teste", "   ")

    with pytest.raises(ErroAnaliseXmlRss, match="raiz"):
        AnalisadorXmlRss.extrair_noticias("g1_teste", "<html><body>Nao e RSS</body></html>")

