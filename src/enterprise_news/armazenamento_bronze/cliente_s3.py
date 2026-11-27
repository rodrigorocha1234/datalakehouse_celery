"""Clientes de Object Storage compatível com S3 (RustFS / MinIO / S3)."""

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, final, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from enterprise_news.nucleo_dominio.excecoes_dominio import ErroArmazenamentoObjetos


@final
@dataclass(frozen=True)
class ObjetoArmazenadoS3:
    """Representa um objeto gravado no Object Storage compatível com S3."""

    bucket: str
    chave_objeto: str
    conteudo_bytes: bytes
    tipo_conteudo: str
    checksum_sha256: str
    metadados: Mapping[str, str]
    gravado_em_utc: datetime


@runtime_checkable
class ProtocoloArmazenamentoObjetosS3(Protocol):
    """Contrato para cliente de Object Storage S3-compatible (RustFS / MinIO / S3)."""

    def verificar_existencia_objeto(self, bucket: str, chave_objeto: str) -> bool:
        """Retorna True se a chave já existir no bucket informado."""
        ...

    def gravar_objeto_idempotente(
        self,
        bucket: str,
        chave_objeto: str,
        conteudo_bytes: bytes,
        tipo_conteudo: str,
        metadados: Mapping[str, str],
    ) -> tuple[ObjetoArmazenadoS3, bool]:
        """Grava o objeto caso não exista com o mesmo hash; retorna (objeto, foi_criado_agora)."""
        ...

    def ler_objeto(self, bucket: str, chave_objeto: str) -> ObjetoArmazenadoS3:
        """Recupera o objeto armazenado no bucket e chave informados."""
        ...

    def listar_chaves_prefixo(self, bucket: str, prefixo: str) -> tuple[str, ...]:
        """Lista todas as chaves de um bucket que iniciam com o prefixo informado."""
        ...


@final
class ClienteObjectStorageMemoriaS3:
    """Implementação S3-compatible em memória com validação SHA-256 e injeção de falhas."""

    def __init__(self) -> None:
        self._buckets: dict[str, dict[str, ObjetoArmazenadoS3]] = {}
        self._falhas_programadas_put: int = 0
        self._contador_chamadas_put: int = 0

    @property
    def contador_chamadas_put(self) -> int:
        return self._contador_chamadas_put

    def programar_falhas_put(self, quantidade_falhas: int) -> None:
        """Simula falhas transientes de rede/storage nas próximas N chamadas PUT."""
        self._falhas_programadas_put = max(0, quantidade_falhas)

    def verificar_existencia_objeto(self, bucket: str, chave_objeto: str) -> bool:
        return chave_objeto in self._buckets.get(bucket, {})

    def gravar_objeto_idempotente(
        self,
        bucket: str,
        chave_objeto: str,
        conteudo_bytes: bytes,
        tipo_conteudo: str,
        metadados: Mapping[str, str],
    ) -> tuple[ObjetoArmazenadoS3, bool]:
        self._contador_chamadas_put += 1
        if self._falhas_programadas_put > 0:
            self._falhas_programadas_put -= 1
            raise ErroArmazenamentoObjetos(
                f"Falha simulada de PUT S3 para 's3://{bucket}/{chave_objeto}'."
            )

        checksum = hashlib.sha256(conteudo_bytes).hexdigest()
        mapa_bucket = self._buckets.setdefault(bucket, {})
        existente = mapa_bucket.get(chave_objeto)
        if existente is not None and existente.checksum_sha256 == checksum:
            return existente, False

        novo_objeto = ObjetoArmazenadoS3(
            bucket=bucket,
            chave_objeto=chave_objeto,
            conteudo_bytes=conteudo_bytes,
            tipo_conteudo=tipo_conteudo,
            checksum_sha256=checksum,
            metadados=dict(metadados),
            gravado_em_utc=datetime.now(tz=UTC),
        )
        mapa_bucket[chave_objeto] = novo_objeto
        return novo_objeto, True

    def ler_objeto(self, bucket: str, chave_objeto: str) -> ObjetoArmazenadoS3:
        mapa_bucket = self._buckets.get(bucket, {})
        objeto = mapa_bucket.get(chave_objeto)
        if objeto is None:
            raise ErroArmazenamentoObjetos(
                f"Objeto 's3://{bucket}/{chave_objeto}' não encontrado."
            )
        return objeto

    def listar_chaves_prefixo(self, bucket: str, prefixo: str) -> tuple[str, ...]:
        mapa_bucket = self._buckets.get(bucket, {})
        chaves = sorted(chave for chave in mapa_bucket if chave.startswith(prefixo))
        return tuple(chaves)


@final
class ClienteObjectStorageHttpS3:
    """Cliente HTTP S3-compatible (RustFS / MinIO) via REST path-style."""

    def __init__(self, endpoint_url: str, tempo_limite_segundos: int = 15) -> None:
        self._endpoint_url = endpoint_url.rstrip("/")
        self._tempo_limite = tempo_limite_segundos

    def _montar_url(self, bucket: str, chave_objeto: str) -> str:
        chave_limpa = chave_objeto.lstrip("/")
        return f"{self._endpoint_url}/{bucket}/{chave_limpa}"

    def verificar_existencia_objeto(self, bucket: str, chave_objeto: str) -> bool:
        req = Request(self._montar_url(bucket, chave_objeto), method="HEAD")
        try:
            with urlopen(req, timeout=self._tempo_limite) as resp:
                return int(resp.status) == 200
        except HTTPError as erro:
            if erro.code == 404:
                return False
            raise ErroArmazenamentoObjetos(
                f"Erro HTTP {erro.code} ao verificar 's3://{bucket}/{chave_objeto}'."
            ) from erro
        except URLError as erro:
            raise ErroArmazenamentoObjetos(
                f"Erro de rede S3 ao verificar 's3://{bucket}/{chave_objeto}': {erro}"
            ) from erro

    def gravar_objeto_idempotente(
        self,
        bucket: str,
        chave_objeto: str,
        conteudo_bytes: bytes,
        tipo_conteudo: str,
        metadados: Mapping[str, str],
    ) -> tuple[ObjetoArmazenadoS3, bool]:
        if self.verificar_existencia_objeto(bucket, chave_objeto):
            existente = self.ler_objeto(bucket, chave_objeto)
            checksum_novo = hashlib.sha256(conteudo_bytes).hexdigest()
            if existente.checksum_sha256 == checksum_novo:
                return existente, False

        checksum = hashlib.sha256(conteudo_bytes).hexdigest()
        cabecalhos = {
            "Content-Type": tipo_conteudo,
            "x-amz-content-sha256": checksum,
        }
        for chave_meta, valor_meta in metadados.items():
            cabecalhos[f"x-amz-meta-{chave_meta.lower()}"] = valor_meta

        req = Request(
            self._montar_url(bucket, chave_objeto),
            data=conteudo_bytes,
            headers=cabecalhos,
            method="PUT",
        )
        try:
            with urlopen(req, timeout=self._tempo_limite):
                pass
        except (HTTPError, URLError) as erro:
            raise ErroArmazenamentoObjetos(
                f"Falha ao gravar objeto 's3://{bucket}/{chave_objeto}': {erro}"
            ) from erro

        return (
            ObjetoArmazenadoS3(
                bucket=bucket,
                chave_objeto=chave_objeto,
                conteudo_bytes=conteudo_bytes,
                tipo_conteudo=tipo_conteudo,
                checksum_sha256=checksum,
                metadados=dict(metadados),
                gravado_em_utc=datetime.now(tz=UTC),
            ),
            True,
        )

    def ler_objeto(self, bucket: str, chave_objeto: str) -> ObjetoArmazenadoS3:
        req = Request(self._montar_url(bucket, chave_objeto), method="GET")
        try:
            with urlopen(req, timeout=self._tempo_limite) as resp:
                dados = resp.read()
                tipo = resp.headers.get("Content-Type", "application/octet-stream")
        except (HTTPError, URLError) as erro:
            raise ErroArmazenamentoObjetos(
                f"Falha ao ler objeto 's3://{bucket}/{chave_objeto}': {erro}"
            ) from erro

        return ObjetoArmazenadoS3(
            bucket=bucket,
            chave_objeto=chave_objeto,
            conteudo_bytes=dados,
            tipo_conteudo=tipo,
            checksum_sha256=hashlib.sha256(dados).hexdigest(),
            metadados={},
            gravado_em_utc=datetime.now(tz=UTC),
        )

    def listar_chaves_prefixo(self, bucket: str, prefixo: str) -> tuple[str, ...]:
        _ = (bucket, prefixo)
        return ()
