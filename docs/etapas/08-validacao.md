# Etapa 8 — Testes, arquitetura e entrega

- Validar cenário de 100 feeds (reais permitidos ou fixtures claramente identificadas), isolamento de falhas, throughput, retries/backoff, idempotência, DLQ e recuperação.
- Verificar end-to-end RSS → Bronze → Silver → Gold → Trino → Superset; qualidade e lineage documentados.
- Fechar diagramas C4 C1/C2/C3/deployment, ADRs de trade-offs, data dictionary, LGPD e runbooks operacionais.
- Documentar configuração das variáveis, volumes `./volumes/enl_*`, comandos seguros, testes e limitações reais.
- Aceite: relatório final com métricas medidas e itens pendentes, sem inventar benchmarks.
- Encerramento: **"Etapa 8 concluída. Deseja iniciar uma nova rodada de melhorias?"**
