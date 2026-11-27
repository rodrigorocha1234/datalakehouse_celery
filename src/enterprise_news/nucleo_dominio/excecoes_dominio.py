"""Exceções de domínio e infraestrutura do Enterprise News Lakehouse."""

from typing import final


class ErroConfiguracaoProjeto(RuntimeError):
    """Exceção base para erros de configuração do projeto."""


@final
class ErroArquivoConfiguracao(ErroConfiguracaoProjeto):
    """Exceção lançada quando um arquivo YAML não pode ser lido ou parseado."""


@final
class ErroValidacaoConfiguracao(ErroConfiguracaoProjeto):
    """Exceção lançada quando o contrato ou invariantes da configuração são violados."""


class ErroIngestaoRss(RuntimeError):
    """Exceção base para falhas durante a ingestão de feeds RSS."""


@final
class ErroConcorrenciaFeed(ErroIngestaoRss):
    """Exceção lançada quando um feed já está em execução concorrente."""


@final
class ErroLimiteTaxaDominio(ErroIngestaoRss):
    """Exceção lançada quando o limite de taxa (rate limit / HTTP 429) é atingido."""

    def __init__(self, mensagem: str, aguardar_segundos: float = 0.0) -> None:
        super().__init__(mensagem)
        self._aguardar_segundos = aguardar_segundos

    @property
    def aguardar_segundos(self) -> float:
        return self._aguardar_segundos


@final
class ErroTransporteHttpRss(ErroIngestaoRss):
    """Exceção lançada em falhas HTTP transientes ou timeout ao consultar feed RSS."""

    def __init__(self, mensagem: str, codigo_http: int | None = None) -> None:
        super().__init__(mensagem)
        self._codigo_http = codigo_http

    @property
    def codigo_http(self) -> int | None:
        return self._codigo_http


@final
class ErroAnaliseXmlRss(ErroIngestaoRss):
    """Exceção lançada quando o payload XML/RSS é malformado ou inválido."""


class ErroCamadaBronze(RuntimeError):
    """Exceção base para falhas de persistência, quarentena ou replay na camada Bronze."""


@final
class ErroArmazenamentoObjetos(ErroCamadaBronze):
    """Exceção lançada quando uma operação S3 falha no Object Storage."""


@final
class ErroTransicaoCheckpoint(ErroCamadaBronze):
    """Exceção lançada quando ocorre uma transição de estado inválida em um lote Bronze."""

