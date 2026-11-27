"""Modelos de configuração de feeds RSS do G1."""

from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from typing import final
from urllib.parse import urlparse

from enterprise_news.gestao_configuracao.validadores_yaml import validar_url_http
from enterprise_news.nucleo_dominio.excecoes_dominio import ErroValidacaoConfiguracao


@final
@dataclass(frozen=True)
class ConfiguracaoFeedRss:
    """Representa um item de feed RSS configurado e validado."""

    identificador: str
    nome: str
    url: str
    habilitado: bool
    categoria: str
    idioma: str
    intervalo_minutos: int

    def __post_init__(self) -> None:
        if not self.identificador.strip():
            raise ErroValidacaoConfiguracao("O identificador do feed não pode ser vazio.")
        validar_url_http(self.url, f"feed:{self.identificador}", exigir_https=True)
        if self.intervalo_minutos <= 0:
            raise ErroValidacaoConfiguracao(
                f"O intervalo do feed '{self.identificador}' deve ser positivo."
            )

    @property
    def dominio(self) -> str:
        """Retorna o domínio (netloc) da URL do feed em letras minúsculas."""
        return urlparse(self.url).netloc.lower()


@final
class ConfiguracaoRss:
    """Configuração global e coleção de feeds RSS do G1."""

    def __init__(
        self,
        fonte: str,
        habilitado: bool,
        intervalo_padrao_minutos: int,
        tempo_limite_segundos: int,
        maximo_tentativas: int,
        recuo_tentativa_segundos: int,
        fila_celery: str,
        feeds: tuple[ConfiguracaoFeedRss, ...],
        recuo_maximo_segundos: int = 300,
        jitter_tentativa: bool = True,
        limite_requisicoes_por_minuto: int = 30,
        capacidade_maxima_feeds: int = 100,
        agente_usuario: str = "EnterpriseNewsLakehouse/0.2",
        fila_dlq: str = "enl.ops.dlq",
        exchange_dlx: str = "enl.dlx",
        tempo_bloqueio_segundos: int = 300,
    ) -> None:
        self._fonte = fonte
        self._habilitado = habilitado
        self._intervalo_padrao_minutos = intervalo_padrao_minutos
        self._tempo_limite_segundos = tempo_limite_segundos
        self._maximo_tentativas = maximo_tentativas
        self._recuo_tentativa_segundos = recuo_tentativa_segundos
        self._fila_celery = fila_celery
        self._feeds = feeds
        self._recuo_maximo_segundos = recuo_maximo_segundos
        self._jitter_tentativa = jitter_tentativa
        self._limite_requisicoes_por_minuto = limite_requisicoes_por_minuto
        self._capacidade_maxima_feeds = capacidade_maxima_feeds
        self._agente_usuario = agente_usuario
        self._fila_dlq = fila_dlq
        self._exchange_dlx = exchange_dlx
        self._tempo_bloqueio_segundos = tempo_bloqueio_segundos
        self.__validar_invariantes()

    def __validar_invariantes(self) -> None:
        if not self._fila_celery.startswith("enl."):
            raise ErroValidacaoConfiguracao(
                f"A fila Celery '{self._fila_celery}' deve utilizar o prefixo exclusivo 'enl.'."
            )
        if not self._fila_dlq.startswith("enl."):
            raise ErroValidacaoConfiguracao(
                f"A fila DLQ '{self._fila_dlq}' deve utilizar o prefixo exclusivo 'enl.'."
            )
        if not self._feeds:
            raise ErroValidacaoConfiguracao("A lista 'rss.feeds' deve conter ao menos um feed.")
        if len(self._feeds) > self._capacidade_maxima_feeds:
            raise ErroValidacaoConfiguracao(
                f"A quantidade de feeds ({len(self._feeds)}) excede a capacidade máxima "
                f"configurada ({self._capacidade_maxima_feeds})."
            )
        contagem_ids = Counter(feed.identificador for feed in self._feeds)
        duplicados = [ident for ident, total in contagem_ids.items() if total > 1]
        if duplicados:
            raise ErroValidacaoConfiguracao(
                f"IDs de feeds duplicados detectados: {', '.join(sorted(duplicados))}."
            )

    @property
    def fonte(self) -> str:
        return self._fonte

    @property
    def habilitado(self) -> bool:
        return self._habilitado

    @property
    def intervalo_padrao_minutos(self) -> int:
        return self._intervalo_padrao_minutos

    @property
    def tempo_limite_segundos(self) -> int:
        return self._tempo_limite_segundos

    @property
    def maximo_tentativas(self) -> int:
        return self._maximo_tentativas

    @property
    def recuo_tentativa_segundos(self) -> int:
        return self._recuo_tentativa_segundos

    @property
    def recuo_maximo_segundos(self) -> int:
        return self._recuo_maximo_segundos

    @property
    def jitter_tentativa(self) -> bool:
        return self._jitter_tentativa

    @property
    def limite_requisicoes_por_minuto(self) -> int:
        return self._limite_requisicoes_por_minuto

    @property
    def capacidade_maxima_feeds(self) -> int:
        return self._capacidade_maxima_feeds

    @property
    def agente_usuario(self) -> str:
        return self._agente_usuario

    @property
    def fila_celery(self) -> str:
        return self._fila_celery

    @property
    def fila_dlq(self) -> str:
        return self._fila_dlq

    @property
    def exchange_dlx(self) -> str:
        return self._exchange_dlx

    @property
    def tempo_bloqueio_segundos(self) -> int:
        return self._tempo_bloqueio_segundos

    @property
    def feeds(self) -> tuple[ConfiguracaoFeedRss, ...]:
        return self._feeds

    def obter_feed_por_id(self, identificador: str) -> ConfiguracaoFeedRss:
        """Localiza um feed pelo seu ID único ou lança ErroValidacaoConfiguracao."""
        for feed in self._feeds:
            if feed.identificador == identificador:
                return feed
        raise ErroValidacaoConfiguracao(f"Feed '{identificador}' não encontrado na configuração.")

    def iterar_feeds_elegiveis(self) -> Iterator[ConfiguracaoFeedRss]:
        """Retorna um iterador consumível uma única vez com os feeds habilitados."""
        if not self._habilitado:
            return
        for feed in self._feeds:
            if feed.habilitado:
                yield feed

