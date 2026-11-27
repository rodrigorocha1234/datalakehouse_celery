"""Modelos de configuração das camadas Silver e Gold (Medallion PySpark)."""

from dataclasses import dataclass
from typing import final

from enterprise_news.gestao_configuracao.validadores_yaml import (
    MapaYaml,
    extrair_booleano,
    extrair_inteiro_positivo,
    extrair_texto,
    garantir_mapa,
    garantir_sequencia,
)
from enterprise_news.nucleo_dominio.excecoes_dominio import ErroValidacaoConfiguracao


def _extrair_lista_textos(mapa: MapaYaml, campo: str, contexto: str) -> tuple[str, ...]:
    sequencia = garantir_sequencia(mapa.get(campo), f"{contexto}.{campo}")
    itens: list[str] = []
    for indice, valor in enumerate(sequencia):
        if not isinstance(valor, str) or not valor.strip():
            raise ErroValidacaoConfiguracao(
                f"Item '{contexto}.{campo}[{indice}]' deve ser texto não vazio."
            )
        itens.append(valor.strip())
    if not itens:
        raise ErroValidacaoConfiguracao(f"Lista '{contexto}.{campo}' não pode ser vazia.")
    return tuple(itens)


def _extrair_proporcao(mapa: MapaYaml, campo: str, contexto: str) -> float:
    valor = mapa.get(campo)
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        raise ErroValidacaoConfiguracao(
            f"Campo '{campo}' em '{contexto}' deve ser número entre 0.0 e 1.0."
        )
    proporcao = float(valor)
    if proporcao < 0.0 or proporcao > 1.0:
        raise ErroValidacaoConfiguracao(
            f"Campo '{campo}' em '{contexto}' deve estar no intervalo [0.0, 1.0]."
        )
    return proporcao


@final
@dataclass(frozen=True)
class ConfiguracaoMedallion:
    """Configuração tipada das camadas Silver e Gold carregada de config/camadas_medallion.yaml."""

    bucket_bronze: str
    bucket_silver: str
    bucket_gold: str
    bucket_quarentena: str
    prefixo_silver: str
    prefixo_quarentena_silver: str
    prefixo_gold_dimensoes: str
    prefixo_gold_fatos: str
    prefixo_gold_marts: str
    formato_arquivos: str
    exigir_url_https: bool
    tamanho_minimo_titulo: int
    remover_parametros_rastreamento_url: bool
    bloquear_schema_drift_campos_desconhecidos: bool
    campos_obrigatorios_bronze: tuple[str, ...]
    taxa_minima_aprovacao_lote: float
    regras_qualidade_ativas: tuple[str, ...]
    dimensoes_gold: tuple[str, ...]
    fatos_gold: tuple[str, ...]
    marts_gold: tuple[str, ...]

    @classmethod
    def carregar_de_mapa(cls, raiz: MapaYaml) -> "ConfiguracaoMedallion":
        """Constrói e valida ConfiguracaoMedallion a partir do mapa YAML."""
        secao_medallion = garantir_mapa(raiz.get("medallion"), "medallion")
        secao_arm = garantir_mapa(
            secao_medallion.get("armazenamento"), "medallion.armazenamento"
        )
        secao_silver = garantir_mapa(
            secao_medallion.get("regras_silver"), "medallion.regras_silver"
        )
        secao_ge = garantir_mapa(
            secao_medallion.get("qualidade_great_expectations"),
            "medallion.qualidade_great_expectations",
        )
        secao_gold = garantir_mapa(
            secao_medallion.get("catalogo_gold"), "medallion.catalogo_gold"
        )

        marts = _extrair_lista_textos(secao_gold, "marts", "medallion.catalogo_gold")
        if len(marts) != 5:
            raise ErroValidacaoConfiguracao(
                f"O catálogo Gold deve declarar exatamente 5 marts; encontrados {len(marts)}."
            )

        return cls(
            bucket_bronze=extrair_texto(
                secao_arm, "bucket_bronze", "medallion.armazenamento"
            ),
            bucket_silver=extrair_texto(
                secao_arm, "bucket_silver", "medallion.armazenamento"
            ),
            bucket_gold=extrair_texto(
                secao_arm, "bucket_gold", "medallion.armazenamento"
            ),
            bucket_quarentena=extrair_texto(
                secao_arm, "bucket_quarentena", "medallion.armazenamento"
            ),
            prefixo_silver=extrair_texto(
                secao_arm, "prefixo_silver", "medallion.armazenamento"
            ),
            prefixo_quarentena_silver=extrair_texto(
                secao_arm, "prefixo_quarentena_silver", "medallion.armazenamento"
            ),
            prefixo_gold_dimensoes=extrair_texto(
                secao_arm, "prefixo_gold_dimensoes", "medallion.armazenamento"
            ),
            prefixo_gold_fatos=extrair_texto(
                secao_arm, "prefixo_gold_fatos", "medallion.armazenamento"
            ),
            prefixo_gold_marts=extrair_texto(
                secao_arm, "prefixo_gold_marts", "medallion.armazenamento"
            ),
            formato_arquivos=extrair_texto(
                secao_arm, "formato_arquivos", "medallion.armazenamento"
            ),
            exigir_url_https=extrair_booleano(
                secao_silver, "exigir_url_https", "medallion.regras_silver"
            ),
            tamanho_minimo_titulo=extrair_inteiro_positivo(
                secao_silver, "tamanho_minimo_titulo", "medallion.regras_silver"
            ),
            remover_parametros_rastreamento_url=extrair_booleano(
                secao_silver,
                "remover_parametros_rastreamento_url",
                "medallion.regras_silver",
            ),
            bloquear_schema_drift_campos_desconhecidos=extrair_booleano(
                secao_silver,
                "bloquear_schema_drift_campos_desconhecidos",
                "medallion.regras_silver",
            ),
            campos_obrigatorios_bronze=_extrair_lista_textos(
                secao_silver, "campos_obrigatorios_bronze", "medallion.regras_silver"
            ),
            taxa_minima_aprovacao_lote=_extrair_proporcao(
                secao_ge,
                "taxa_minima_aprovacao_lote",
                "medallion.qualidade_great_expectations",
            ),
            regras_qualidade_ativas=_extrair_lista_textos(
                secao_ge,
                "regras_ativas",
                "medallion.qualidade_great_expectations",
            ),
            dimensoes_gold=_extrair_lista_textos(
                secao_gold, "dimensoes", "medallion.catalogo_gold"
            ),
            fatos_gold=_extrair_lista_textos(
                secao_gold, "fatos", "medallion.catalogo_gold"
            ),
            marts_gold=marts,
        )

