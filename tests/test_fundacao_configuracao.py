"""Testes automatizados da Etapa 1 — Inspeção e Fundação."""

from pathlib import Path

import pytest

from enterprise_news.gestao_configuracao import (
    CarregadorConfiguracao,
    ConfiguracaoFeedRss,
    ConfiguracaoRss,
    ConfiguracaoVolumes,
    InspetorInfraestrutura,
)
from enterprise_news.nucleo_dominio import (
    ErroArquivoConfiguracao,
    ErroValidacaoConfiguracao,
)

RAIZ_PROJETO = Path(__file__).resolve().parent.parent


def test_carregamento_g1_rss_valido() -> None:
    caminho_rss = RAIZ_PROJETO / "config" / "g1_rss.yaml"
    config = CarregadorConfiguracao.carregar_configuracao_rss(caminho_rss)

    assert config.fonte == "g1"
    assert config.habilitado is True
    assert config.fila_celery == "enl.rss.ingestion"
    assert config.fila_celery.startswith("enl.")
    assert len(config.feeds) >= 1

    feeds_elegiveis = list(config.iterar_feeds_elegiveis())
    assert len(feeds_elegiveis) >= 1
    assert feeds_elegiveis[0].identificador == "g1_principal"
    assert feeds_elegiveis[0].url == "https://g1.globo.com/rss/g1/"


def test_carregamento_fundacao_e_criacao_volumes() -> None:
    caminho_fundacao = RAIZ_PROJETO / "config" / "fundacao_lakehouse.yaml"
    config = CarregadorConfiguracao.carregar_configuracao_fundacao(caminho_fundacao)

    assert config.fuso_horario_servicos == "America/Sao_Paulo"
    assert config.fuso_horario_analitico == "UTC"
    assert config.prefixo_filas == "enl."

    caminhos_validados = config.configuracao_volumes.validar_caminhos_raiz(RAIZ_PROJETO)
    assert len(caminhos_validados) >= 11

    inspetor = InspetorInfraestrutura(
        caminho_compose=RAIZ_PROJETO / "docker-compose.yaml",
        diretorio_raiz=RAIZ_PROJETO,
    )
    criados = inspetor.garantir_diretorios_volumes(
        config.configuracao_volumes.diretorios_obrigatorios
    )
    for diretorio in criados:
        assert diretorio.exists()
        assert diretorio.is_dir()
        assert diretorio.parent == (RAIZ_PROJETO / "volumes").resolve()
        assert diretorio.name.startswith("enl_")


def test_inspecao_docker_compose_preserva_legado_e_isola_enl() -> None:
    inspetor = InspetorInfraestrutura(
        caminho_compose=RAIZ_PROJETO / "docker-compose.yaml",
        diretorio_raiz=RAIZ_PROJETO,
    )
    servicos = inspetor.validar_isolamento_compose()
    nomes = {servico.nome for servico in servicos}

    for legado in InspetorInfraestrutura.SERVICOS_LEGADOS_PRESERVADOS:
        assert legado in nomes

    for exclusivo in InspetorInfraestrutura.SERVICOS_EXCLUSIVOS_ENL_FUNDACAO:
        assert exclusivo in nomes


@pytest.mark.parametrize(
    ("url_invalida", "intervalo"),
    [
        ("ftp://g1.globo.com/rss", 60),
        ("sem-esquema.com/rss", 60),
        ("https://g1.globo.com/rss", 0),
        ("https://g1.globo.com/rss", -15),
    ],
)
def test_rejeicao_feed_rss_invalido(url_invalida: str, intervalo: int) -> None:
    with pytest.raises(ErroValidacaoConfiguracao):
        ConfiguracaoFeedRss(
            identificador="feed_teste",
            nome="Feed Teste",
            url=url_invalida,
            habilitado=True,
            categoria="noticias",
            idioma="pt-BR",
            intervalo_minutos=intervalo,
        )


def test_rejeicao_ids_duplicados_ou_fila_sem_prefixo_enl() -> None:
    feed_a = ConfiguracaoFeedRss(
        identificador="duplicado",
        nome="Feed A",
        url="https://g1.globo.com/rss/g1/",
        habilitado=True,
        categoria="noticias",
        idioma="pt-BR",
        intervalo_minutos=30,
    )
    with pytest.raises(ErroValidacaoConfiguracao, match="duplicados"):
        ConfiguracaoRss(
            fonte="g1",
            habilitado=True,
            intervalo_padrao_minutos=60,
            tempo_limite_segundos=20,
            maximo_tentativas=3,
            recuo_tentativa_segundos=10,
            fila_celery="enl.rss.ingestion",
            feeds=(feed_a, feed_a),
        )

    with pytest.raises(ErroValidacaoConfiguracao, match="enl."):
        ConfiguracaoRss(
            fonte="g1",
            habilitado=True,
            intervalo_padrao_minutos=60,
            tempo_limite_segundos=20,
            maximo_tentativas=3,
            recuo_tentativa_segundos=10,
            fila_celery="fila_sem_prefixo",
            feeds=(feed_a,),
        )


def test_rejeicao_volume_fora_da_raiz() -> None:
    volumes_invalidos = ConfiguracaoVolumes(
        raiz_volumes="./volumes",
        prefixo_volumes="enl_",
        diretorios_obrigatorios=("/tmp/enl_proibido",),
    )
    with pytest.raises(ErroValidacaoConfiguracao):
        volumes_invalidos.validar_caminhos_raiz(RAIZ_PROJETO)


def test_erro_arquivo_configuracao_inexistente(tmp_path: Path) -> None:
    arquivo_ausente = tmp_path / "nao_existe.yaml"
    with pytest.raises(ErroArquivoConfiguracao):
        CarregadorConfiguracao.carregar_mapa_yaml(arquivo_ausente)

