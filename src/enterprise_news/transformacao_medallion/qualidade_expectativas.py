"""Validador de qualidade de dados no padrão Great Expectations para Silver e Gold."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import final
from urllib.parse import urlparse

from enterprise_news.gestao_configuracao.configuracao_medallion import ConfiguracaoMedallion
from enterprise_news.nucleo_dominio.excecoes_dominio import ErroQualidadeDados
from enterprise_news.transformacao_medallion.schemas_medallion import RegistroNoticiaSilver


@final
@dataclass(frozen=True)
class ResultadoExpectativaQualidade:
    """Resultado individual de uma expectativa de qualidade Great Expectations."""

    nome_expectativa: str
    coluna_alvo: str
    sucesso: bool
    total_avaliados: int
    total_falhas: int
    taxa_sucesso: float


@final
@dataclass(frozen=True)
class RelatorioQualidadeLote:
    """Relatório consolidado de execução de expectativas Great Expectations sobre um lote."""

    id_lote: str
    total_registros_entrada: int
    total_registros_validos: int
    total_registros_quarentena: int
    resultados_expectativas: tuple[ResultadoExpectativaQualidade, ...]
    taxa_aprovacao_registros: float
    aprovado: bool


@final
class ValidadorQualidadeExpectativas:
    """Executa suíte de expectativas de qualidade (Great Expectations) em Silver/Gold."""

    def __init__(self, configuracao_medallion: ConfiguracaoMedallion) -> None:
        self._config = configuracao_medallion

    def validar_registro_candidato(
        self,
        dedup_hash: str,
        titulo: str,
        url_canonica: str,
        publicado_em_iso: str,
    ) -> tuple[bool, str, str]:
        """Valida um registro antes de ingressar na Silver; retorna (valido, regra, motivo)."""
        if not dedup_hash.strip():
            return (
                False,
                "expect_column_values_to_not_be_null:dedup_hash",
                "Campo 'dedup_hash' nulo ou vazio.",
            )

        titulo_limpo = titulo.strip()
        if not titulo_limpo:
            return (
                False,
                "expect_column_values_to_not_be_null:title",
                "Campo 'title' nulo ou vazio.",
            )

        if len(titulo_limpo) < self._config.tamanho_minimo_titulo:
            return (
                False,
                "expect_column_value_lengths_to_be_between:title",
                f"Título menor que o tamanho mínimo ({self._config.tamanho_minimo_titulo}).",
            )

        analisada = urlparse(url_canonica)
        esquemas = ("https",) if self._config.exigir_url_https else ("http", "https")
        if analisada.scheme not in esquemas or not analisada.netloc:
            return (
                False,
                "expect_column_values_to_match_regex:canonical_url",
                f"URL canônica inválida ou fora do esquema exigido: '{url_canonica}'.",
            )

        if not publicado_em_iso.strip():
            return (
                False,
                "expect_column_values_to_not_be_null:published_at_utc",
                "Timestamp 'published_at_utc' ausente.",
            )

        return True, "aprovado", ""

    def avaliar_lote_silver(
        self,
        id_lote: str,
        registros_validos: Sequence[RegistroNoticiaSilver],
        quantidade_quarentena: int,
    ) -> RelatorioQualidadeLote:
        """Gera o relatório formal de expectativas de qualidade sobre o lote processado."""
        total_entrada = len(registros_validos) + quantidade_quarentena
        taxa_aprovacao = (
            float(len(registros_validos)) / float(total_entrada)
            if total_entrada > 0
            else 1.0
        )

        total_val = len(registros_validos)
        falhas_hash = sum(1 for r in registros_validos if not r.dedup_hash)
        falhas_titulo = sum(
            1
            for r in registros_validos
            if len(r.title) < self._config.tamanho_minimo_titulo
        )
        falhas_url = sum(
            1
            for r in registros_validos
            if not r.canonical_url.startswith("https://")
        )

        expectativas = (
            ResultadoExpectativaQualidade(
                nome_expectativa="expect_column_values_to_not_be_null",
                coluna_alvo="dedup_hash",
                sucesso=falhas_hash == 0,
                total_avaliados=total_val,
                total_falhas=falhas_hash,
                taxa_sucesso=1.0 if total_val == 0 else (total_val - falhas_hash) / total_val,
            ),
            ResultadoExpectativaQualidade(
                nome_expectativa="expect_column_value_lengths_to_be_between",
                coluna_alvo="title",
                sucesso=falhas_titulo == 0,
                total_avaliados=total_val,
                total_falhas=falhas_titulo,
                taxa_sucesso=1.0 if total_val == 0 else (total_val - falhas_titulo) / total_val,
            ),
            ResultadoExpectativaQualidade(
                nome_expectativa="expect_column_values_to_match_regex",
                coluna_alvo="canonical_url",
                sucesso=falhas_url == 0,
                total_avaliados=total_val,
                total_falhas=falhas_url,
                taxa_sucesso=1.0 if total_val == 0 else (total_val - falhas_url) / total_val,
            ),
            ResultadoExpectativaQualidade(
                nome_expectativa="expect_batch_acceptance_rate_to_be_at_least",
                coluna_alvo="__batch__",
                sucesso=taxa_aprovacao >= self._config.taxa_minima_aprovacao_lote,
                total_avaliados=total_entrada,
                total_falhas=quantidade_quarentena,
                taxa_sucesso=round(taxa_aprovacao, 4),
            ),
        )

        aprovado = all(exp.sucesso for exp in expectativas)
        if not aprovado:
            raise ErroQualidadeDados(
                f"Qualidade do lote '{id_lote}' reprovada: taxa de aprovação "
                f"{taxa_aprovacao:.2%} inferior ao mínimo "
                f"{self._config.taxa_minima_aprovacao_lote:.2%}."
            )

        return RelatorioQualidadeLote(
            id_lote=id_lote,
            total_registros_entrada=total_entrada,
            total_registros_validos=total_val,
            total_registros_quarentena=quantidade_quarentena,
            resultados_expectativas=expectativas,
            taxa_aprovacao_registros=round(taxa_aprovacao, 4),
            aprovado=True,
        )

