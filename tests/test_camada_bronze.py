"""Testes automatizados da Etapa 3 — Camada Bronze, Object Storage S3, checkpoints e replay."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from enterprise_news.armazenamento_bronze import (
    ClienteObjectStorageMemoriaS3,
    EstadoCheckpointLote,
    RepositorioCheckpointsBronzeSql,
    ServicoCamadaBronze,
    carregar_configuracao_bronze_padrao,
)
from enterprise_news.gestao_configuracao import ConfiguracaoFeedRss
from enterprise_news.ingestao_rss import RespostaHttpBruta
from enterprise_news.nucleo_dominio import (
    ErroArmazenamentoObjetos,
    ErroTransicaoCheckpoint,
)

RAIZ_PROJETO = Path(__file__).resolve().parent.parent

XML_BRONZE_VALIDO = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>G1 - Bronze</title>
    <link>https://g1.globo.com/</link>
    <description>Feed para testes Bronze</description>
    <item>
      <title>Notícia Bronze A</title>
      <link>https://g1.globo.com/noticia-a.ghtml</link>
      <guid>guid-bronze-a</guid>
      <pubDate>Thu, 26 Nov 2026 12:00:00 -0300</pubDate>
      <description>Conteúdo A</description>
    </item>
    <item>
      <title>Notícia Bronze B</title>
      <link>https://g1.globo.com/noticia-b.ghtml</link>
      <guid>guid-bronze-b</guid>
      <pubDate>Thu, 26 Nov 2026 13:00:00 -0300</pubDate>
      <description>Conteúdo B</description>
    </item>
    <item>
      <title>Notícia Bronze C</title>
      <link>https://g1.globo.com/noticia-c.ghtml</link>
      <guid>guid-bronze-c</guid>
      <pubDate>Thu, 26 Nov 2026 14:00:00 -0300</pubDate>
      <description>Conteúdo C</description>
    </item>
  </channel>
</rss>
"""


def _criar_feed_padrao() -> ConfiguracaoFeedRss:
    return ConfiguracaoFeedRss(
        identificador="g1_principal",
        nome="G1 Principal",
        url="https://g1.globo.com/rss/g1/",
        habilitado=True,
        categoria="noticias",
        idioma="pt-BR",
        intervalo_minutos=60,
    )


def test_carregamento_configuracao_camada_bronze() -> None:
    caminho = str(RAIZ_PROJETO / "config" / "camada_bronze.yaml")
    config = carregar_configuracao_bronze_padrao(caminho)

    assert config.bucket_bronze == "enl-bronze"
    assert config.bucket_quarentena == "enl-quarentena"
    assert config.endpoint_url == "http://enl_storage:9000"
    assert config.politica_retencao.dias_retencao_payload_bruto == 365
    assert config.politica_retencao.dias_retencao_quarentena == 90
    assert config.politica_retencao.politica_imutabilidade == "append_only_idempotente"


def test_persistencia_idempotente_put_repetido_e_mensagem_redelivered() -> None:
    config = carregar_configuracao_bronze_padrao(
        str(RAIZ_PROJETO / "config" / "camada_bronze.yaml")
    )
    cliente_s3 = ClienteObjectStorageMemoriaS3()
    checkpoints = RepositorioCheckpointsBronzeSql(":memory:")
    servico = ServicoCamadaBronze(
        configuracao_bronze=config,
        cliente_s3=cliente_s3,
        repositorio_checkpoints=checkpoints,
    )
    feed = _criar_feed_padrao()
    resposta = RespostaHttpBruta(
        codigo_status=200,
        corpo_texto=XML_BRONZE_VALIDO,
        cabecalhos={"etag": '"v1"', "content-type": "application/rss+xml"},
    )
    instante_fixo = datetime(2026, 11, 26, 18, 0, 0, tzinfo=UTC)

    # 1ª entrega da mensagem Celery
    res_1 = servico.persistir_lote_bruto(feed, resposta, instante_fixo)
    assert res_1.estado_final == EstadoCheckpointLote.CONCLUIDO
    assert res_1.payload_novo_gravado is True
    assert res_1.itens_novos_gravados == 3
    assert res_1.itens_idempotentes_ignorados == 0
    assert res_1.enviado_quarentena is False

    chaves_s3 = cliente_s3.listar_chaves_prefixo("enl-bronze", "bronze/g1_rss")
    assert len(chaves_s3) == 4  # 1 payload bruto + 3 itens

    # 2ª entrega (mensagem redelivered / PUT repetido / feed repetido)
    res_2 = servico.persistir_lote_bruto(feed, resposta, instante_fixo)
    assert res_2.id_lote == res_1.id_lote
    assert res_2.estado_final == EstadoCheckpointLote.CONCLUIDO
    assert res_2.payload_novo_gravado is False
    assert res_2.itens_novos_gravados == 0
    assert res_2.itens_idempotentes_ignorados == 3
    assert len(cliente_s3.listar_chaves_prefixo("enl-bronze", "bronze/g1_rss")) == 4


def test_falha_parcial_worker_reiniciado_e_replay_desde_bronze() -> None:
    config = carregar_configuracao_bronze_padrao(
        str(RAIZ_PROJETO / "config" / "camada_bronze.yaml")
    )
    cliente_s3 = ClienteObjectStorageMemoriaS3()
    checkpoints = RepositorioCheckpointsBronzeSql(":memory:")
    servico = ServicoCamadaBronze(
        configuracao_bronze=config,
        cliente_s3=cliente_s3,
        repositorio_checkpoints=checkpoints,
    )
    feed = _criar_feed_padrao()
    resposta = RespostaHttpBruta(
        codigo_status=200,
        corpo_texto=XML_BRONZE_VALIDO,
        cabecalhos={"etag": '"v2"'},
    )
    instante_fixo = datetime(2026, 11, 26, 19, 0, 0, tzinfo=UTC)

    # Faz o payload bruto e o 1º item passarem, e injeta falha no 2º item (3º PUT)
    orig_gravar = cliente_s3.gravar_objeto_idempotente
    chamadas = 0

    def gravar_com_falha_no_terceiro_put(
        bucket: str,
        chave_objeto: str,
        conteudo_bytes: bytes,
        tipo_conteudo: str,
        metadados: dict[str, str],
    ) -> tuple[object, bool]:
        nonlocal chamadas
        chamadas += 1
        if chamadas == 3:
            raise ErroArmazenamentoObjetos("Worker interrompido no meio do lote Bronze.")
        return orig_gravar(bucket, chave_objeto, conteudo_bytes, tipo_conteudo, metadados)

    cliente_s3.gravar_objeto_idempotente = gravar_com_falha_no_terceiro_put  # type: ignore[method-assign]

    with pytest.raises(ErroArmazenamentoObjetos, match="interrompido"):
        servico.persistir_lote_bruto(feed, resposta, instante_fixo)

    # Restaura o cliente S3 (simulando novo worker saudável após restart)
    cliente_s3.gravar_objeto_idempotente = orig_gravar  # type: ignore[method-assign]

    incompletos = checkpoints.listar_lotes_incompletos()
    assert len(incompletos) == 1
    lote_parcial = incompletos[0]
    assert lote_parcial.estado == EstadoCheckpointLote.FALHA_PARCIAL
    assert lote_parcial.total_itens_esperados == 3
    assert lote_parcial.total_itens_gravados == 1

    # Executa replay diretamente a partir do payload bruto já salvo no Bronze S3
    res_replay = servico.reprocessar_lote_desde_bronze(
        id_lote=lote_parcial.id_lote,
        momento_replay_utc=instante_fixo,
    )
    assert res_replay.estado_final == EstadoCheckpointLote.CONCLUIDO
    assert res_replay.itens_novos_gravados == 2  # Apenas os 2 que faltavam
    assert res_replay.itens_idempotentes_ignorados == 1  # O 1º já estava gravado
    assert len(checkpoints.listar_lotes_incompletos()) == 0


def test_quarentena_inicial_para_payload_corrompido() -> None:
    config = carregar_configuracao_bronze_padrao(
        str(RAIZ_PROJETO / "config" / "camada_bronze.yaml")
    )
    cliente_s3 = ClienteObjectStorageMemoriaS3()
    checkpoints = RepositorioCheckpointsBronzeSql(":memory:")
    servico = ServicoCamadaBronze(
        configuracao_bronze=config,
        cliente_s3=cliente_s3,
        repositorio_checkpoints=checkpoints,
    )
    feed = _criar_feed_padrao()
    resposta_invalida = RespostaHttpBruta(
        codigo_status=200,
        corpo_texto="<rss><channel><item><title>XML quebrado sem fechamento",
        cabecalhos={},
    )

    resultado = servico.persistir_lote_bruto(feed, resposta_invalida)
    assert resultado.enviado_quarentena is True
    assert resultado.estado_final == EstadoCheckpointLote.QUARENTENA
    assert resultado.bucket_destino == "enl-quarentena"

    chaves_quarentena = cliente_s3.listar_chaves_prefixo(
        "enl-quarentena", "quarentena/g1_rss"
    )
    assert len(chaves_quarentena) == 1

    # Transição inválida a partir de QUARENTENA para CONCLUIDO deve ser bloqueada
    with pytest.raises(ErroTransicaoCheckpoint, match="Transição inválida"):
        checkpoints.atualizar_estado_lote(
            id_lote=resultado.id_lote,
            novo_estado=EstadoCheckpointLote.CONCLUIDO,
        )

