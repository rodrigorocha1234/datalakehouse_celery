"""Inspeção e validação estrutural do Docker Compose e volumes do projeto."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import final

from enterprise_news.gestao_configuracao.carregador_yaml import CarregadorConfiguracao
from enterprise_news.gestao_configuracao.validadores_yaml import (
    MapaYaml,
    ValorYaml,
    garantir_mapa,
)
from enterprise_news.nucleo_dominio.excecoes_dominio import ErroValidacaoConfiguracao


def _extrair_ambiente_servico(bloco_servico: MapaYaml, nome_servico: str) -> dict[str, str]:
    ambiente_bruto = bloco_servico.get("environment")
    if ambiente_bruto is None:
        return {}
    if isinstance(ambiente_bruto, Mapping):
        resultado: dict[str, str] = {}
        for chave, valor in ambiente_bruto.items():
            if isinstance(chave, str) and valor is not None:
                resultado[chave] = str(valor)
        return resultado
    if isinstance(ambiente_bruto, Sequence) and not isinstance(ambiente_bruto, (str, bytes)):
        resultado_lista: dict[str, str] = {}
        for item in ambiente_bruto:
            if isinstance(item, str) and "=" in item:
                chave, valor = item.split("=", 1)
                resultado_lista[chave.strip()] = valor.strip()
        return resultado_lista
    raise ErroValidacaoConfiguracao(
        f"Formato de 'environment' inválido no serviço '{nome_servico}'."
    )


def _extrair_volumes_servico(bloco_servico: MapaYaml) -> tuple[str, ...]:
    volumes_brutos: ValorYaml = bloco_servico.get("volumes")
    if volumes_brutos is None:
        return ()
    if not isinstance(volumes_brutos, Sequence) or isinstance(volumes_brutos, (str, bytes)):
        raise ErroValidacaoConfiguracao("O campo 'volumes' de um serviço deve ser uma lista.")
    montagens: list[str] = []
    for item in volumes_brutos:
        if isinstance(item, str):
            montagens.append(item)
    return tuple(montagens)


@final
@dataclass(frozen=True)
class ServicoComposeInspecionado:
    """Resumo estrutural de um serviço declarado no Docker Compose."""

    nome: str
    imagem_ou_build: str
    fuso_horario: str | None
    montagens_bind: tuple[str, ...]
    possui_healthcheck: bool
    exclusivo_enl: bool


@final
class InspetorInfraestrutura:
    """Inspeciona e valida as regras arquiteturais da Etapa 1 no Docker Compose."""

    SERVICOS_LEGADOS_PRESERVADOS: tuple[str, ...] = (
        "rabbitmq",
        "storage",
        "app",
        "worker_celery_beat",
        "worker_rss_ingestion",
        "worker_rss_processar_noticia",
        "worker_monitoramento",
        "flower",
        "prometheus",
        "grafana",
        "trino",
        "spark-master",
        "spark-worker",
        "pyspark",
    )

    SERVICOS_EXCLUSIVOS_ENL_FUNDACAO: tuple[str, ...] = (
        "enl_rabbitmq",
        "enl_postgres",
        "enl_storage",
    )

    def __init__(self, caminho_compose: Path, diretorio_raiz: Path) -> None:
        self._caminho_compose = caminho_compose
        self._diretorio_raiz = diretorio_raiz.resolve()

    def inspecionar_servicos(self) -> tuple[ServicoComposeInspecionado, ...]:
        """Lê o docker-compose.yaml e retorna os metadados de todos os serviços."""
        mapa_compose = CarregadorConfiguracao.carregar_mapa_yaml(self._caminho_compose)
        servicos_brutos = garantir_mapa(mapa_compose.get("services"), "services")
        inspecionados: list[ServicoComposeInspecionado] = []

        for nome_servico, definicao_bruta in servicos_brutos.items():
            bloco = garantir_mapa(definicao_bruta, f"services.{nome_servico}")
            imagem = bloco.get("image")
            imagem_ou_build = str(imagem) if isinstance(imagem, str) else "build_local"
            ambiente = _extrair_ambiente_servico(bloco, nome_servico)
            montagens = _extrair_volumes_servico(bloco)
            possui_hc = isinstance(bloco.get("healthcheck"), Mapping)

            inspecionados.append(
                ServicoComposeInspecionado(
                    nome=nome_servico,
                    imagem_ou_build=imagem_ou_build,
                    fuso_horario=ambiente.get("TZ"),
                    montagens_bind=montagens,
                    possui_healthcheck=possui_hc,
                    exclusivo_enl=nome_servico.startswith("enl_"),
                )
            )
        return tuple(inspecionados)

    def validar_isolamento_compose(self) -> tuple[ServicoComposeInspecionado, ...]:
        """Valida preservação de serviços legados e conformidade dos serviços enl_*."""
        servicos = self.inspecionar_servicos()
        mapa_por_nome = {servico.nome: servico for servico in servicos}

        ausentes_legados = [
            nome for nome in self.SERVICOS_LEGADOS_PRESERVADOS if nome not in mapa_por_nome
        ]
        if ausentes_legados:
            raise ErroValidacaoConfiguracao(
                "Serviços existentes foram removidos indevidamente do Compose: "
                f"{', '.join(ausentes_legados)}."
            )

        ausentes_enl = [
            nome for nome in self.SERVICOS_EXCLUSIVOS_ENL_FUNDACAO if nome not in mapa_por_nome
        ]
        if ausentes_enl:
            raise ErroValidacaoConfiguracao(
                "Serviços exclusivos obrigatórios da fundação ausentes no Compose: "
                f"{', '.join(ausentes_enl)}."
            )

        for servico in servicos:
            if not servico.exclusivo_enl:
                continue
            if servico.fuso_horario != "America/Sao_Paulo":
                raise ErroValidacaoConfiguracao(
                    f"Serviço '{servico.nome}' deve definir TZ=America/Sao_Paulo."
                )
            if not servico.possui_healthcheck:
                raise ErroValidacaoConfiguracao(
                    f"Serviço exclusivo '{servico.nome}' deve possuir healthcheck configurado."
                )
            for montagem in servico.montagens_bind:
                origem_host = montagem.split(":", 1)[0]
                if not origem_host.startswith("./volumes/enl_"):
                    raise ErroValidacaoConfiguracao(
                        f"Bind mount '{montagem}' do serviço '{servico.nome}' deve residir em "
                        "'./volumes/enl_*' na raiz do projeto."
                    )

        return servicos

    def garantir_diretorios_volumes(
        self, diretorios_relativos: Sequence[str]
    ) -> tuple[Path, ...]:
        """Garante a existência física dos diretórios ./volumes/enl_* na raiz do projeto."""
        criados: list[Path] = []
        for caminho_relativo in diretorios_relativos:
            if not caminho_relativo.startswith("./volumes/enl_"):
                raise ErroValidacaoConfiguracao(
                    f"Diretório '{caminho_relativo}' fora do padrão './volumes/enl_*'."
                )
            destino = (self._diretorio_raiz / caminho_relativo).resolve()
            destino.mkdir(parents=True, exist_ok=True)
            criados.append(destino)
        return tuple(criados)

