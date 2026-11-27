"""Modelos de configuração da camada Bronze, Object Storage S3 e retenção."""

from dataclasses import dataclass
from typing import final

from enterprise_news.gestao_configuracao.validadores_yaml import (
    MapaYaml,
    extrair_booleano,
    extrair_inteiro_positivo,
    extrair_texto,
    garantir_mapa,
)


@final
@dataclass(frozen=True)
class PoliticaRetencaoBronze:
    """Política de retenção e imutabilidade dos objetos da camada Bronze."""

    dias_retencao_payload_bruto: int
    dias_retencao_quarentena: int
    dias_retencao_checkpoints_sql: int
    politica_imutabilidade: str


@final
@dataclass(frozen=True)
class ConfiguracaoCamadaBronze:
    """Configuração tipada da camada Bronze carregada de config/camada_bronze.yaml."""

    endpoint_url: str
    regiao: str
    bucket_bronze: str
    bucket_quarentena: str
    prefixo_objetos_bronze: str
    prefixo_objetos_quarentena: str
    forcar_path_style: bool
    politica_retencao: PoliticaRetencaoBronze
    permitir_replay_lote_parcial: bool
    quarentenar_payload_invalido: bool
    validar_checksum_sha256: bool

    @classmethod
    def carregar_de_mapa(cls, raiz: MapaYaml) -> "ConfiguracaoCamadaBronze":
        """Constrói e valida ConfiguracaoCamadaBronze a partir de um mapa YAML."""
        secao_bronze = garantir_mapa(raiz.get("bronze"), "bronze")
        secao_s3 = garantir_mapa(
            secao_bronze.get("armazenamento_s3"), "bronze.armazenamento_s3"
        )
        secao_retencao = garantir_mapa(secao_bronze.get("retencao"), "bronze.retencao")
        secao_resiliencia = garantir_mapa(
            secao_bronze.get("resiliencia"), "bronze.resiliencia"
        )

        retencao = PoliticaRetencaoBronze(
            dias_retencao_payload_bruto=extrair_inteiro_positivo(
                secao_retencao, "dias_retencao_payload_bruto", "bronze.retencao"
            ),
            dias_retencao_quarentena=extrair_inteiro_positivo(
                secao_retencao, "dias_retencao_quarentena", "bronze.retencao"
            ),
            dias_retencao_checkpoints_sql=extrair_inteiro_positivo(
                secao_retencao, "dias_retencao_checkpoints_sql", "bronze.retencao"
            ),
            politica_imutabilidade=extrair_texto(
                secao_retencao, "politica_imutabilidade", "bronze.retencao"
            ),
        )

        return cls(
            endpoint_url=extrair_texto(
                secao_s3, "endpoint_url", "bronze.armazenamento_s3"
            ),
            regiao=extrair_texto(secao_s3, "regiao", "bronze.armazenamento_s3"),
            bucket_bronze=extrair_texto(
                secao_s3, "bucket_bronze", "bronze.armazenamento_s3"
            ),
            bucket_quarentena=extrair_texto(
                secao_s3, "bucket_quarentena", "bronze.armazenamento_s3"
            ),
            prefixo_objetos_bronze=extrair_texto(
                secao_s3, "prefixo_objetos_bronze", "bronze.armazenamento_s3"
            ),
            prefixo_objetos_quarentena=extrair_texto(
                secao_s3, "prefixo_objetos_quarentena", "bronze.armazenamento_s3"
            ),
            forcar_path_style=extrair_booleano(
                secao_s3, "forcar_path_style", "bronze.armazenamento_s3"
            ),
            politica_retencao=retencao,
            permitir_replay_lote_parcial=extrair_booleano(
                secao_resiliencia, "permitir_replay_lote_parcial", "bronze.resiliencia"
            ),
            quarentenar_payload_invalido=extrair_booleano(
                secao_resiliencia, "quarentenar_payload_invalido", "bronze.resiliencia"
            ),
            validar_checksum_sha256=extrair_booleano(
                secao_resiliencia, "validar_checksum_sha256", "bronze.resiliencia"
            ),
        )

