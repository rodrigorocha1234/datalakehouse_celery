"""Subpacote de domínio: exceções e erros de negócio do projeto."""

from enterprise_news.nucleo_dominio.excecoes_dominio import (
    ErroAnaliseXmlRss,
    ErroArmazenamentoObjetos,
    ErroArquivoConfiguracao,
    ErroCamadaBronze,
    ErroConcorrenciaFeed,
    ErroConfiguracaoProjeto,
    ErroIngestaoRss,
    ErroLimiteTaxaDominio,
    ErroTransicaoCheckpoint,
    ErroTransporteHttpRss,
    ErroValidacaoConfiguracao,
)

__all__ = [
    "ErroAnaliseXmlRss",
    "ErroArmazenamentoObjetos",
    "ErroArquivoConfiguracao",
    "ErroCamadaBronze",
    "ErroConcorrenciaFeed",
    "ErroConfiguracaoProjeto",
    "ErroIngestaoRss",
    "ErroLimiteTaxaDominio",
    "ErroTransicaoCheckpoint",
    "ErroTransporteHttpRss",
    "ErroValidacaoConfiguracao",
]

