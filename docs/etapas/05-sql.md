# Etapa 5 — Trino, dbt e camada SQL

- Configurar catálogos Trino para Silver e Gold no storage selecionado, sem colidir com catálogos existentes.
- Criar dbt Core staging/intermediate/marts, documentação e testes not_null, unique, relationships e accepted_values.
- Consultas SQL de volume diário, desempenho de fontes, categorias, freshness e qualidade.
- Definir estratégia verificável de criação/atualização de tabelas consultáveis pelo Trino (catálogo compatível com Parquet/Iceberg, conforme ADR).
- Aceite: consultas e testes dbt executados com resultados reais, explain de consultas relevantes.
- Encerramento: **"Etapa 5 concluída. Deseja avançar para a Etapa 6?"**
