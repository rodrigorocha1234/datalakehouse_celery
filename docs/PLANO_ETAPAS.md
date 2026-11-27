# Plano com gates de aprovação

| Etapa | Título | Evidência mínima |
|---|---|---|
| 1 | Inspeção e fundação | Compose inventariado, plano de isolamento, config validada |
| 2 | Ingestão RSS/Celery | 1 e N feeds, worker e retries testados |
| 3 | Bronze e resiliência | Object storage, checkpoint, replay e idempotência |
| 4 | Silver/Gold PySpark | Transformações e testes de qualidade |
| 5 | Trino/dbt e SQL | Data marts consultáveis e testados |
| 6 | OpenMetadata e governança | Catálogo, glossary e lineage comprovados |
| 7 | Superset e observabilidade | 5 dashboards, logs e alertas verificáveis |
| 8 | Hardening e entrega | 100 feeds simulados/reais, testes, C4/ADR/runbooks |

## Porta de aprovação obrigatória

Após cada etapa: (a) resumo do que foi feito; (b) arquivos alterados; (c) testes executados com resultados; (d) riscos e pendências; (e) pergunta explícita de avanço. **Parar sem executar qualquer ação da etapa seguinte**.

Para um bloqueio, explicar o problema e pedir orientação; nunca avançar para contorná-lo.
