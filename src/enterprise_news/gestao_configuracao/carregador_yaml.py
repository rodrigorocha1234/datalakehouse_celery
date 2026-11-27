"""Carregador centralizado de arquivos de configuração YAML sem uso de eval."""

from pathlib import Path
from typing import final

import yaml

from enterprise_news.gestao_configuracao.configuracao_bronze import ConfiguracaoCamadaBronze
from enterprise_news.gestao_configuracao.configuracao_fundacao import (
    ConfiguracaoFundacao,
    ConfiguracaoVolumes,
)
from enterprise_news.gestao_configuracao.configuracao_rss import (
    ConfiguracaoFeedRss,
    ConfiguracaoRss,
)
from enterprise_news.gestao_configuracao.validadores_yaml import (
    MapaYaml,
    ValorYaml,
    extrair_booleano,
    extrair_inteiro_positivo,
    extrair_texto,
    garantir_mapa,
    garantir_sequencia,
)
from enterprise_news.nucleo_dominio.excecoes_dominio import (
    ErroArquivoConfiguracao,
    ErroValidacaoConfiguracao,
)


@final
class CarregadorConfiguracao:
    """Carregador seguro de configurações YAML sem uso de eval."""

    @staticmethod
    def carregar_mapa_yaml(caminho_arquivo: Path) -> MapaYaml:
        """Lê um arquivo YAML com yaml.safe_load e garante estrutura de mapeamento."""
        try:
            conteudo = caminho_arquivo.read_text(encoding="utf-8")
        except OSError as erro:
            raise ErroArquivoConfiguracao(
                f"Não foi possível ler o arquivo de configuração '{caminho_arquivo}'."
            ) from erro

        try:
            dados_brutos: ValorYaml = yaml.safe_load(conteudo)
        except yaml.YAMLError as erro:
            raise ErroArquivoConfiguracao(
                f"Erro de sintaxe YAML no arquivo '{caminho_arquivo}'."
            ) from erro

        return garantir_mapa(dados_brutos, str(caminho_arquivo))

    @classmethod
    def carregar_configuracao_rss(cls, caminho_arquivo: Path) -> ConfiguracaoRss:
        """Carrega e valida o arquivo config/g1_rss.yaml."""
        raiz = cls.carregar_mapa_yaml(caminho_arquivo)
        secao_rss = garantir_mapa(raiz.get("rss"), "rss")

        fonte = extrair_texto(secao_rss, "source", "rss")
        habilitado = extrair_booleano(secao_rss, "enabled", "rss")
        intervalo_padrao = extrair_inteiro_positivo(
            secao_rss, "default_interval_minutes", "rss"
        )
        tempo_limite = extrair_inteiro_positivo(
            secao_rss, "request_timeout_seconds", "rss"
        )
        maximo_tentativas = extrair_inteiro_positivo(secao_rss, "max_retries", "rss")
        recuo_tentativa = extrair_inteiro_positivo(
            secao_rss, "retry_backoff_seconds", "rss"
        )
        recuo_maximo = (
            extrair_inteiro_positivo(secao_rss, "retry_backoff_max_seconds", "rss")
            if "retry_backoff_max_seconds" in secao_rss
            else 300
        )
        jitter = (
            extrair_booleano(secao_rss, "retry_jitter", "rss")
            if "retry_jitter" in secao_rss
            else True
        )
        limite_rpm = (
            extrair_inteiro_positivo(secao_rss, "rate_limit_requests_per_minute", "rss")
            if "rate_limit_requests_per_minute" in secao_rss
            else 30
        )
        capacidade_feeds = (
            extrair_inteiro_positivo(secao_rss, "max_feeds_capacity", "rss")
            if "max_feeds_capacity" in secao_rss
            else 100
        )
        agente_usuario = (
            extrair_texto(secao_rss, "user_agent", "rss")
            if "user_agent" in secao_rss
            else "EnterpriseNewsLakehouse/0.2"
        )
        fila_celery = extrair_texto(secao_rss, "queue", "rss")
        fila_dlq = (
            extrair_texto(secao_rss, "dlq_queue", "rss")
            if "dlq_queue" in secao_rss
            else "enl.ops.dlq"
        )
        exchange_dlx = (
            extrair_texto(secao_rss, "dlx_exchange", "rss")
            if "dlx_exchange" in secao_rss
            else "enl.dlx"
        )
        tempo_bloqueio = (
            extrair_inteiro_positivo(secao_rss, "lock_ttl_seconds", "rss")
            if "lock_ttl_seconds" in secao_rss
            else 300
        )

        lista_feeds_bruta = garantir_sequencia(secao_rss.get("feeds"), "rss.feeds")
        feeds_validados: list[ConfiguracaoFeedRss] = []

        for indice, item_bruto in enumerate(lista_feeds_bruta):
            contexto_item = f"rss.feeds[{indice}]"
            mapa_item = garantir_mapa(item_bruto, contexto_item)
            identificador = extrair_texto(mapa_item, "id", contexto_item)
            nome = extrair_texto(mapa_item, "name", contexto_item)
            url = extrair_texto(mapa_item, "url", contexto_item)
            feed_habilitado = extrair_booleano(mapa_item, "enabled", contexto_item)
            categoria = (
                extrair_texto(mapa_item, "category", contexto_item)
                if "category" in mapa_item
                else "geral"
            )
            idioma = (
                extrair_texto(mapa_item, "language", contexto_item)
                if "language" in mapa_item
                else "pt-BR"
            )
            intervalo_feed = (
                extrair_inteiro_positivo(mapa_item, "interval_minutes", contexto_item)
                if "interval_minutes" in mapa_item
                else intervalo_padrao
            )
            feeds_validados.append(
                ConfiguracaoFeedRss(
                    identificador=identificador,
                    nome=nome,
                    url=url,
                    habilitado=feed_habilitado,
                    categoria=categoria,
                    idioma=idioma,
                    intervalo_minutos=intervalo_feed,
                )
            )

        return ConfiguracaoRss(
            fonte=fonte,
            habilitado=habilitado,
            intervalo_padrao_minutos=intervalo_padrao,
            tempo_limite_segundos=tempo_limite,
            maximo_tentativas=maximo_tentativas,
            recuo_tentativa_segundos=recuo_tentativa,
            fila_celery=fila_celery,
            feeds=tuple(feeds_validados),
            recuo_maximo_segundos=recuo_maximo,
            jitter_tentativa=jitter,
            limite_requisicoes_por_minuto=limite_rpm,
            capacidade_maxima_feeds=capacidade_feeds,
            agente_usuario=agente_usuario,
            fila_dlq=fila_dlq,
            exchange_dlx=exchange_dlx,
            tempo_bloqueio_segundos=tempo_bloqueio,
        )

    @classmethod
    def carregar_configuracao_fundacao(cls, caminho_arquivo: Path) -> ConfiguracaoFundacao:
        """Carrega e valida o arquivo config/fundacao_lakehouse.yaml."""
        raiz = cls.carregar_mapa_yaml(caminho_arquivo)
        secao_projeto = garantir_mapa(raiz.get("projeto"), "projeto")
        secao_isolamento = garantir_mapa(raiz.get("isolamento"), "isolamento")
        secao_armazenamento = garantir_mapa(
            raiz.get("armazenamento_objetos"), "armazenamento_objetos"
        )
        secao_filas = garantir_mapa(raiz.get("filas_celery"), "filas_celery")
        sequencia_volumes = garantir_sequencia(
            raiz.get("volumes_obrigatorios"), "volumes_obrigatorios"
        )

        filas_tipadas: dict[str, str] = {}
        for chave_fila in secao_filas:
            filas_tipadas[chave_fila] = extrair_texto(secao_filas, chave_fila, "filas_celery")

        diretorios_volumes: list[str] = []
        for indice, item_volume in enumerate(sequencia_volumes):
            if not isinstance(item_volume, str) or not item_volume.strip():
                raise ErroValidacaoConfiguracao(
                    f"Item 'volumes_obrigatorios[{indice}]' deve ser texto não vazio."
                )
            diretorios_volumes.append(item_volume.strip())

        config_volumes = ConfiguracaoVolumes(
            raiz_volumes=extrair_texto(secao_projeto, "raiz_volumes", "projeto"),
            prefixo_volumes=extrair_texto(secao_isolamento, "prefixo_volumes", "isolamento"),
            diretorios_obrigatorios=tuple(diretorios_volumes),
        )

        return ConfiguracaoFundacao(
            nome_projeto=extrair_texto(secao_projeto, "nome", "projeto"),
            ambiente=extrair_texto(secao_projeto, "ambiente", "projeto"),
            fuso_horario_servicos=extrair_texto(
                secao_projeto, "fuso_horario_servicos", "projeto"
            ),
            fuso_horario_analitico=extrair_texto(
                secao_projeto, "fuso_horario_analitico", "projeto"
            ),
            prefixo_filas=extrair_texto(secao_isolamento, "prefixo_filas", "isolamento"),
            prefixo_servicos=extrair_texto(secao_isolamento, "prefixo_servicos", "isolamento"),
            vhost_rabbitmq=extrair_texto(secao_isolamento, "vhost_rabbitmq", "isolamento"),
            endpoint_armazenamento=extrair_texto(
                secao_armazenamento, "endpoint_interno", "armazenamento_objetos"
            ),
            filas_celery=filas_tipadas,
            configuracao_volumes=config_volumes,
        )

    @classmethod
    def carregar_configuracao_bronze(cls, caminho_arquivo: Path) -> ConfiguracaoCamadaBronze:
        """Carrega e valida o arquivo config/camada_bronze.yaml."""
        mapa = cls.carregar_mapa_yaml(caminho_arquivo)
        return ConfiguracaoCamadaBronze.carregar_de_mapa(mapa)


def carregar_configuracao_bronze_padrao(
    caminho_yaml: str = "config/camada_bronze.yaml",
) -> ConfiguracaoCamadaBronze:
    """Carrega a configuração YAML da camada Bronze a partir do caminho informado."""
    return CarregadorConfiguracao.carregar_configuracao_bronze(Path(caminho_yaml))

