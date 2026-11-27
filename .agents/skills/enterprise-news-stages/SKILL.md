---
name: enterprise-news-stages
description: Implementar o Enterprise News Lakehouse em oito etapas independentes, com inspeção de Docker Compose, volumes na raiz e confirmação do usuário entre fases.
---

# Implementação por etapas

1. Ler `AGENTS.md`, `.agents/rules/enterprise-news.md`, as três partes de `.agents/rules/padroes-python-parte-*` e `docs/PLANO_ETAPAS.md`.
2. Identificar a etapa **explicitamente autorizada** pelo usuário. Se nenhuma, perguntar se deseja iniciar a Etapa 1.
3. Abrir **somente** `docs/etapas/NN-*.md` correspondente e implementar o escopo completo dessa etapa, com testes. Dependências técnicas mínimas necessárias podem ser preparadas sem antecipar entregas de outras etapas.
4. Produzir relatório de aceite com evidências reais, arquivos alterados, comandos, testes e pendências.
5. Parar. Perguntar: **"Etapa N concluída. Deseja avançar para a Etapa N+1?"** e aguardar resposta explícita.
6. Não despachar outro agente, workflow ou tarefa assíncrona para começar fase posterior antes da confirmação.

As alterações no Docker Compose estão autorizadas dentro da etapa atual após inspeção. **Todos os diretórios persistentes de bind mounts devem ser criados sob a raiz do projeto do Compose**, em `./volumes/enl_*`.
