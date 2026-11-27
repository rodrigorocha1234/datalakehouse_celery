"""Orquestrador de despacho Celery por feed elegível, locks, retries com jitter e DLQ."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import final

from enterprise_news.execucao_celery.politica_retentativa import (
    EspecificacaoDespachoFeed,
    PoliticaRetentativaCelery,
    RelatorioLoteIngestaoRss,
    ResultadoTarefaIngestaoFeed,
)
from enterprise_news.gestao_configuracao.configuracao_rss import (
    ConfiguracaoFeedRss,
    ConfiguracaoRss,
)
from enterprise_news.ingestao_rss.coletor_feed import ColetorFeedRss
from enterprise_news.nucleo_dominio.excecoes_dominio import (
    ErroConcorrenciaFeed,
    ErroIngestaoRss,
    ErroLimiteTaxaDominio,
)
from enterprise_news.persistencia_operacional.modelos_operacionais import (
    ProtocoloRepositorioOperacional,
    RegistroMensagemDlq,
    StatusExecucaoFeed,
)


@final
class OrquestradorIngestaoRss:
    """Orquestra o despacho por feed elegível, locks, retries com jitter e DLQ."""

    NOME_TAREFA_DISPATCHER: str = "enl.rss.despachar_feeds_elegiveis"
    NOME_TAREFA_COLETAR_FEED: str = "enl.rss.coletar_feed_individual"

    def __init__(
        self,
        configuracao_rss: ConfiguracaoRss,
        coletor_rss: ColetorFeedRss,
        repositorio_operacional: ProtocoloRepositorioOperacional,
        gerador_jitter: Callable[[float, float], float] | None = None,
    ) -> None:
        self._configuracao_rss = configuracao_rss
        self._coletor_rss = coletor_rss
        self._repositorio = repositorio_operacional
        self._gerador_jitter = gerador_jitter
        self._politica_retry = PoliticaRetentativaCelery(
            maximo_tentativas=configuracao_rss.maximo_tentativas,
            recuo_base_segundos=configuracao_rss.recuo_tentativa_segundos,
            recuo_maximo_segundos=configuracao_rss.recuo_maximo_segundos,
            usar_jitter=configuracao_rss.jitter_tentativa,
            fila_origem=configuracao_rss.fila_celery,
            fila_dlq=configuracao_rss.fila_dlq,
            exchange_dlx=configuracao_rss.exchange_dlx,
        )

    @property
    def politica_retentativa(self) -> PoliticaRetentativaCelery:
        return self._politica_retry

    def construir_plano_despacho(self) -> tuple[EspecificacaoDespachoFeed, ...]:
        """Gera uma especificação de tarefa Celery independente para cada feed elegível."""
        plano: list[EspecificacaoDespachoFeed] = []
        for feed in self._configuracao_rss.iterar_feeds_elegiveis():
            plano.append(
                EspecificacaoDespachoFeed(
                    nome_tarefa=self.NOME_TAREFA_COLETAR_FEED,
                    identificador_feed=feed.identificador,
                    fila_destino=self._configuracao_rss.fila_celery,
                    intervalo_segundos=feed.intervalo_minutos * 60,
                    exchange_dlx=self._configuracao_rss.exchange_dlx,
                    routing_key_dlq=self._configuracao_rss.fila_dlq,
                )
            )
        return tuple(plano)

    def construir_agenda_beat(self) -> dict[str, dict[str, str | int | tuple[str, ...]]]:
        """Gera a tabela de agendamento do Celery Beat respeitando o intervalo de cada feed."""
        agenda: dict[str, dict[str, str | int | tuple[str, ...]]] = {}
        for especificacao in self.construir_plano_despacho():
            chave_agenda = f"enl_beat_rss_{especificacao.identificador_feed}"
            agenda[chave_agenda] = {
                "task": especificacao.nome_tarefa,
                "schedule": especificacao.intervalo_segundos,
                "args": (especificacao.identificador_feed,),
                "queue": especificacao.fila_destino,
            }
        return agenda

    def executar_tarefa_feed(
        self,
        identificador_feed: str,
    ) -> ResultadoTarefaIngestaoFeed:
        """Executa a tarefa individual de um feed com lock de concorrência, retries e DLQ."""
        feed = self._configuracao_rss.obter_feed_por_id(identificador_feed)
        return self._processar_feed_com_retentativas(feed)

    def _processar_feed_com_retentativas(
        self,
        feed: ConfiguracaoFeedRss,
    ) -> ResultadoTarefaIngestaoFeed:
        bloqueio_adquirido = self._repositorio.adquirir_bloqueio_feed(
            identificador_feed=feed.identificador,
            duracao_segundos=self._configuracao_rss.tempo_bloqueio_segundos,
        )
        if not bloqueio_adquirido:
            raise ErroConcorrenciaFeed(
                "Execução concorrente bloqueada: "
                f"o feed '{feed.identificador}' já possui lock ativo."
            )

        atrasos_aplicados: list[float] = []
        tentativa_atual = 0
        limite_tentativas = self._politica_retry.maximo_tentativas

        try:
            while tentativa_atual < limite_tentativas:
                tentativa_atual += 1
                estado_anterior = self._repositorio.obter_estado_feed(feed.identificador)
                cabecalho_cond = estado_anterior.obter_cabecalho_condicional()

                try:
                    resultado_coleta = self._coletor_rss.coletar_feed(
                        feed=feed,
                        cabecalho_condicional=cabecalho_cond,
                    )
                    inseridas, duplicadas = self._repositorio.registrar_sucesso_coleta(
                        identificador_feed=feed.identificador,
                        noticias_novas=resultado_coleta.noticias_unicas,
                        duplicadas_intra_feed=resultado_coleta.quantidade_duplicadas_ignoradas,
                        novo_etag=resultado_coleta.novo_etag,
                        nova_ultima_modificacao=resultado_coleta.nova_ultima_modificacao,
                        nao_modificado_304=resultado_coleta.nao_modificado,
                    )
                    status_final = (
                        StatusExecucaoFeed.NAO_MODIFICADO_304
                        if resultado_coleta.nao_modificado
                        else StatusExecucaoFeed.SUCESSO
                    )
                    return ResultadoTarefaIngestaoFeed(
                        identificador_feed=feed.identificador,
                        fila_celery=self._configuracao_rss.fila_celery,
                        status=status_final,
                        codigo_http=resultado_coleta.codigo_http,
                        noticias_inseridas=inseridas,
                        noticias_duplicadas=duplicadas,
                        tentativas_executadas=tentativa_atual,
                        encaminhado_dlq=False,
                        atrasos_retentativa_segundos=tuple(atrasos_aplicados),
                    )
                except ErroIngestaoRss as erro_ingestao:
                    motivo = str(erro_ingestao)
                    esgotou_tentativas = tentativa_atual >= limite_tentativas

                    if not esgotou_tentativas:
                        if (
                            isinstance(erro_ingestao, ErroLimiteTaxaDominio)
                            and erro_ingestao.aguardar_segundos > 0
                        ):
                            atraso = erro_ingestao.aguardar_segundos
                        else:
                            atraso = self._politica_retry.calcular_atraso_segundos(
                                numero_tentativa=tentativa_atual,
                                gerador_aleatorio=self._gerador_jitter,
                            )
                        atrasos_aplicados.append(atraso)
                        continue

                    self._repositorio.registrar_falha_coleta(
                        identificador_feed=feed.identificador,
                        motivo_erro=motivo,
                        enviado_dlq=True,
                    )
                    self._repositorio.registrar_envio_dlq(
                        RegistroMensagemDlq(
                            identificador_feed=feed.identificador,
                            fila_origem=self._configuracao_rss.fila_celery,
                            fila_dlq=self._configuracao_rss.fila_dlq,
                            exchange_dlx=self._configuracao_rss.exchange_dlx,
                            tentativas_executadas=tentativa_atual,
                            motivo_erro=motivo,
                            registrado_em_utc=datetime.now(tz=UTC),
                        )
                    )
                    return ResultadoTarefaIngestaoFeed(
                        identificador_feed=feed.identificador,
                        fila_celery=self._configuracao_rss.fila_celery,
                        status=StatusExecucaoFeed.ENVIADO_DLQ,
                        codigo_http=None,
                        noticias_inseridas=0,
                        noticias_duplicadas=0,
                        tentativas_executadas=tentativa_atual,
                        encaminhado_dlq=True,
                        atrasos_retentativa_segundos=tuple(atrasos_aplicados),
                        mensagem_erro=motivo,
                    )
        finally:
            self._repositorio.liberar_bloqueio_feed(feed.identificador)

        raise RuntimeError("Fluxo inesperado de término de retentativas.")

    def despachar_grupo_feeds_elegiveis(self) -> RelatorioLoteIngestaoRss:
        """Despacha tarefas independentes (semântica group) para todos os feeds elegíveis."""
        feeds_elegiveis = tuple(self._configuracao_rss.iterar_feeds_elegiveis())
        resultados: list[ResultadoTarefaIngestaoFeed] = []

        for feed in feeds_elegiveis:
            resultado_individual = self._processar_feed_com_retentativas(feed)
            resultados.append(resultado_individual)

        return RelatorioLoteIngestaoRss(
            total_feeds_configurados=len(self._configuracao_rss.feeds),
            total_feeds_elegiveis=len(feeds_elegiveis),
            resultados_por_feed=tuple(resultados),
        )

