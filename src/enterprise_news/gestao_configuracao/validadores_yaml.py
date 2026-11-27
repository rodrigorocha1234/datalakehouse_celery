"""Validadores e tipos auxiliares para estruturas YAML."""

from collections.abc import Mapping, Sequence
from typing import TypeAlias
from urllib.parse import urlparse

from enterprise_news.nucleo_dominio.excecoes_dominio import ErroValidacaoConfiguracao

ValorYamlPrimitivo: TypeAlias = str | int | float | bool | None
ValorYaml: TypeAlias = (
    ValorYamlPrimitivo
    | Sequence["ValorYaml"]
    | Mapping[str, "ValorYaml"]
)
MapaYaml: TypeAlias = Mapping[str, ValorYaml]


def garantir_mapa(valor: ValorYaml, contexto: str) -> MapaYaml:
    """Garante que o valor YAML é um mapeamento com chaves textuais."""
    if not isinstance(valor, Mapping):
        raise ErroValidacaoConfiguracao(f"Seção '{contexto}' deve ser um mapeamento YAML.")
    mapa_tipado: dict[str, ValorYaml] = {}
    for chave, item in valor.items():
        if not isinstance(chave, str):
            raise ErroValidacaoConfiguracao(f"Chave inválida em '{contexto}': esperado texto.")
        mapa_tipado[chave] = item
    return mapa_tipado


def garantir_sequencia(valor: ValorYaml, contexto: str) -> Sequence[ValorYaml]:
    """Garante que o valor YAML é uma lista/sequência (e não texto/bytes)."""
    if not isinstance(valor, Sequence) or isinstance(valor, (str, bytes)):
        raise ErroValidacaoConfiguracao(f"Campo '{contexto}' deve ser uma lista YAML.")
    return valor


def extrair_texto(mapa: MapaYaml, campo: str, contexto: str) -> str:
    """Extrai um campo textual obrigatório não vazio de um mapeamento YAML."""
    valor = mapa.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        raise ErroValidacaoConfiguracao(
            f"Campo '{campo}' em '{contexto}' deve ser texto não vazio."
        )
    return valor.strip()


def extrair_booleano(mapa: MapaYaml, campo: str, contexto: str) -> bool:
    """Extrai um campo booleano obrigatório de um mapeamento YAML."""
    valor = mapa.get(campo)
    if not isinstance(valor, bool):
        raise ErroValidacaoConfiguracao(
            f"Campo '{campo}' em '{contexto}' deve ser um booleano explícito."
        )
    return valor


def extrair_inteiro_positivo(mapa: MapaYaml, campo: str, contexto: str) -> int:
    """Extrai um inteiro estritamente positivo de um mapeamento YAML."""
    valor = mapa.get(campo)
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ErroValidacaoConfiguracao(
            f"Campo '{campo}' em '{contexto}' deve ser um inteiro positivo."
        )
    return valor


def validar_url_http(url: str, contexto: str, exigir_https: bool = False) -> str:
    """Valida se a URL possui esquema http/https (ou estritamente https) e domínio válido."""
    analisada = urlparse(url)
    esquemas_validos = ("https",) if exigir_https else ("http", "https")
    if analisada.scheme not in esquemas_validos or not analisada.netloc:
        esquema_msg = "https" if exigir_https else "http ou https"
        raise ErroValidacaoConfiguracao(
            f"URL inválida '{url}' em '{contexto}': deve usar {esquema_msg} com domínio válido."
        )
    return url

