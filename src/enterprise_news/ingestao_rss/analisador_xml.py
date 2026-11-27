"""Parser XML seguro para feeds RSS 2.0 e Atom, restrito ao conteúdo presente no feed."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import final
from xml.etree import ElementTree as ET

from enterprise_news.nucleo_dominio.excecoes_dominio import ErroAnaliseXmlRss


@final
@dataclass(frozen=True)
class NoticiaRssColetada:
    """Item de notícia extraído exclusivamente do conteúdo presente no feed RSS."""

    identificador_feed: str
    guid_item: str
    titulo: str
    link: str
    resumo: str
    categorias: tuple[str, ...]
    publicado_em_utc: datetime
    coletado_em_utc: datetime
    hash_deduplicacao: str


@final
@dataclass(frozen=True)
class ResultadoColetaFeed:
    """Resultado consolidado da consulta e parsing de um feed RSS."""

    identificador_feed: str
    codigo_http: int
    nao_modificado: bool
    novo_etag: str | None
    nova_ultima_modificacao: str | None
    noticias_unicas: tuple[NoticiaRssColetada, ...]
    quantidade_duplicadas_ignoradas: int


def _normalizar_data_rss_para_utc(texto_data: str | None, padrao_utc: datetime) -> datetime:
    if not texto_data or not texto_data.strip():
        return padrao_utc
    texto_limpo = texto_data.strip()
    try:
        data_analisada = parsedate_to_datetime(texto_limpo)
        if data_analisada.tzinfo is None:
            return data_analisada.replace(tzinfo=UTC)
        return data_analisada.astimezone(UTC)
    except (TypeError, ValueError):
        pass

    try:
        iso_normalizado = texto_limpo.replace("Z", "+00:00")
        data_iso = datetime.fromisoformat(iso_normalizado)
        if data_iso.tzinfo is None:
            return data_iso.replace(tzinfo=UTC)
        return data_iso.astimezone(UTC)
    except ValueError:
        return padrao_utc


def _calcular_hash_noticia(
    identificador_feed: str,
    guid_item: str,
    link: str,
    titulo: str,
) -> str:
    chave_canonica = (
        f"{identificador_feed.strip()}|{guid_item.strip()}|"
        f"{link.strip()}|{titulo.strip()}"
    )
    return hashlib.sha256(chave_canonica.encode("utf-8")).hexdigest()


def _nome_local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1].lower()
    return tag.lower()


def _obter_texto_filho(elemento: ET.Element, nomes_possiveis: tuple[str, ...]) -> str:
    for filho in elemento:
        nome_local = _nome_local_tag(filho.tag)
        if nome_local in nomes_possiveis:
            if nome_local == "link" and not (filho.text and filho.text.strip()):
                href = filho.attrib.get("href", "").strip()
                if href:
                    return href
            texto = (filho.text or "").strip()
            if texto:
                return texto
    return ""


@final
class AnalisadorXmlRss:
    """Parser XML seguro para RSS 2.0 e Atom, restrito ao conteúdo presente no feed."""

    @staticmethod
    def extrair_noticias(
        identificador_feed: str,
        conteudo_xml: str,
        momento_coleta_utc: datetime | None = None,
    ) -> tuple[tuple[NoticiaRssColetada, ...], int]:
        """Extrai itens únicos do XML RSS/Atom e contabiliza duplicados intra-feed."""
        if not conteudo_xml or not conteudo_xml.strip():
            raise ErroAnaliseXmlRss(
                f"Conteúdo XML vazio recebido para o feed '{identificador_feed}'."
            )

        coleta_utc = (
            momento_coleta_utc.astimezone(UTC)
            if momento_coleta_utc is not None
            else datetime.now(tz=UTC)
        )

        try:
            raiz = ET.fromstring(conteudo_xml.strip())
        except ET.ParseError as erro:
            raise ErroAnaliseXmlRss(
                f"XML malformado no feed '{identificador_feed}': {erro}"
            ) from erro

        nome_raiz = _nome_local_tag(raiz.tag)
        if nome_raiz not in ("rss", "feed", "rdf"):
            raise ErroAnaliseXmlRss(
                f"Elemento raiz '{nome_raiz}' inválido no feed '{identificador_feed}'."
            )

        elementos_itens = [
            elem for elem in raiz.iter() if _nome_local_tag(elem.tag) in ("item", "entry")
        ]

        noticias_unicas: list[NoticiaRssColetada] = []
        hashes_vistos: set[str] = set()
        duplicadas_ignoradas = 0

        for elemento in elementos_itens:
            titulo = _obter_texto_filho(elemento, ("title",))
            link = _obter_texto_filho(elemento, ("link",))
            guid = _obter_texto_filho(elemento, ("guid", "id")) or link or titulo
            resumo = _obter_texto_filho(
                elemento, ("description", "summary", "encoded", "content")
            )
            texto_data = _obter_texto_filho(
                elemento, ("pubdate", "published", "updated", "date")
            )

            if not titulo and not link:
                continue

            categorias = tuple(
                (filho.text or filho.attrib.get("term", "")).strip()
                for filho in elemento
                if _nome_local_tag(filho.tag) == "category"
                and (filho.text or filho.attrib.get("term", "")).strip()
            )

            publicado_utc = _normalizar_data_rss_para_utc(texto_data, coleta_utc)
            hash_dedup = _calcular_hash_noticia(
                identificador_feed=identificador_feed,
                guid_item=guid,
                link=link,
                titulo=titulo,
            )

            if hash_dedup in hashes_vistos:
                duplicadas_ignoradas += 1
                continue

            hashes_vistos.add(hash_dedup)
            noticias_unicas.append(
                NoticiaRssColetada(
                    identificador_feed=identificador_feed,
                    guid_item=guid,
                    titulo=titulo,
                    link=link,
                    resumo=resumo,
                    categorias=categorias,
                    publicado_em_utc=publicado_utc,
                    coletado_em_utc=coleta_utc,
                    hash_deduplicacao=hash_dedup,
                )
            )

        return tuple(noticias_unicas), duplicadas_ignoradas
