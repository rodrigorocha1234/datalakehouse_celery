# Agente para Google Antigravity — Enterprise News Lakehouse

Este pacote contém regras de workspace e uma skill de desenvolvimento por fases.

## Instalação

1. Extraia o ZIP na **raiz do workspace do Enterprise News Lakehouse** aberto no Antigravity, preservando `.agents/` e `AGENTS.md`.
2. Se o projeto já tiver `AGENTS.md` ou `.agents/`, **mescle sem sobrescrever** as regras existentes.
3. Mantenha o Docker Compose real onde ele já estiver. Não copie ou invente um Compose a partir deste pacote.
4. Abra o Agent Manager e solicite: **"Use a skill enterprise-news-stages. Execute somente a Etapa 1 do plano. Ao terminar, pergunte se desejo avançar."**
5. Quando solicitado, confirme o avanço; cada etapa terá sua própria porta de aprovação.

O pacote define instruções para o agente — não instala nem inicia serviços automaticamente.

Documentos principais: `docs/PLANO_ETAPAS.md`, `docs/etapas/01-*.md` até `08-*.md`, `config/g1_rss.yaml` e as três partes de `.agents/rules/padroes-python-parte-*` (regras Python originais adaptadas à versão 3.11).
