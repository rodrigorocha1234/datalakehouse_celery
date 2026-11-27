"""Modelos de configuração estrutural da fundação e diretórios de volumes."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import final

from enterprise_news.gestao_configuracao.validadores_yaml import validar_url_http
from enterprise_news.nucleo_dominio.excecoes_dominio import ErroValidacaoConfiguracao


@final
@dataclass(frozen=True)
class ConfiguracaoVolumes:
    """Política de diretórios persistentes de bind mount na raiz do projeto."""

    raiz_volumes: str
    prefixo_volumes: str
    diretorios_obrigatorios: tuple[str, ...]

    def validar_caminhos_raiz(self, diretorio_raiz_projeto: Path) -> tuple[Path, ...]:
        """Valida que todos os diretórios de volume pertencem a ./volumes/enl_* na raiz."""
        raiz_resolvida = diretorio_raiz_projeto.resolve()
        pasta_volumes_esperada = (raiz_resolvida / "volumes").resolve()
        caminhos_validados: list[Path] = []

        for caminho_relativo in self.diretorios_obrigatorios:
            if not caminho_relativo.startswith("./volumes/enl_"):
                raise ErroValidacaoConfiguracao(
                    f"Volume '{caminho_relativo}' inválido: deve iniciar com './volumes/enl_'."
                )
            caminho_absoluto = (raiz_resolvida / caminho_relativo).resolve()
            if caminho_absoluto.parent != pasta_volumes_esperada:
                raise ErroValidacaoConfiguracao(
                    f"Volume '{caminho_relativo}' escapa do diretório './volumes' da raiz."
                )
            if not caminho_absoluto.name.startswith(self.prefixo_volumes):
                raise ErroValidacaoConfiguracao(
                    f"Volume '{caminho_absoluto.name}' não respeita o prefixo "
                    f"'{self.prefixo_volumes}'."
                )
            caminhos_validados.append(caminho_absoluto)
        return tuple(caminhos_validados)


@final
class ConfiguracaoFundacao:
    """Configuração estrutural e de isolamento da Etapa 1."""

    def __init__(
        self,
        nome_projeto: str,
        ambiente: str,
        fuso_horario_servicos: str,
        fuso_horario_analitico: str,
        prefixo_filas: str,
        prefixo_servicos: str,
        vhost_rabbitmq: str,
        endpoint_armazenamento: str,
        filas_celery: Mapping[str, str],
        configuracao_volumes: ConfiguracaoVolumes,
    ) -> None:
        self._nome_projeto = nome_projeto
        self._ambiente = ambiente
        self._fuso_horario_servicos = fuso_horario_servicos
        self._fuso_horario_analitico = fuso_horario_analitico
        self._prefixo_filas = prefixo_filas
        self._prefixo_servicos = prefixo_servicos
        self._vhost_rabbitmq = vhost_rabbitmq
        self._endpoint_armazenamento = endpoint_armazenamento
        self._filas_celery = dict(filas_celery)
        self._configuracao_volumes = configuracao_volumes
        self.__validar_invariantes()

    def __validar_invariantes(self) -> None:
        if self._fuso_horario_servicos != "America/Sao_Paulo":
            raise ErroValidacaoConfiguracao(
                "O fuso horário dos serviços deve ser obrigatoriamente 'America/Sao_Paulo'."
            )
        if self._fuso_horario_analitico != "UTC":
            raise ErroValidacaoConfiguracao(
                "O fuso horário analítico deve ser obrigatoriamente 'UTC'."
            )
        if self._prefixo_filas != "enl.":
            raise ErroValidacaoConfiguracao("O prefixo de filas deve ser 'enl.'.")
        validar_url_http(self._endpoint_armazenamento, "armazenamento_objetos.endpoint_interno")
        for chave_fila, nome_fila in self._filas_celery.items():
            if not nome_fila.startswith(self._prefixo_filas):
                raise ErroValidacaoConfiguracao(
                    f"Fila '{chave_fila}' ('{nome_fila}') deve iniciar com '{self._prefixo_filas}'."
                )

    @property
    def nome_projeto(self) -> str:
        return self._nome_projeto

    @property
    def ambiente(self) -> str:
        return self._ambiente

    @property
    def fuso_horario_servicos(self) -> str:
        return self._fuso_horario_servicos

    @property
    def fuso_horario_analitico(self) -> str:
        return self._fuso_horario_analitico

    @property
    def prefixo_filas(self) -> str:
        return self._prefixo_filas

    @property
    def prefixo_servicos(self) -> str:
        return self._prefixo_servicos

    @property
    def vhost_rabbitmq(self) -> str:
        return self._vhost_rabbitmq

    @property
    def endpoint_armazenamento(self) -> str:
        return self._endpoint_armazenamento

    @property
    def filas_celery(self) -> Mapping[str, str]:
        return self._filas_celery

    @property
    def configuracao_volumes(self) -> ConfiguracaoVolumes:
        return self._configuracao_volumes

