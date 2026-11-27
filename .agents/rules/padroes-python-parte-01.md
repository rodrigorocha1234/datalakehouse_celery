```python
from typing_extensions import override


class ModeloRidge(EstrategiaModelo):

    @override
    def criar_modelo(self) -> Ridge:
        ...
```

Isso ajuda o type checker a detectar mudanças incompatíveis.

---

# @final

Utilizar o decorador `@final` para indicar classes que não devem ser herdadas e métodos que não devem ser sobrescritos por subclasses.

Em Python 3.11, `final` já está disponível diretamente em `typing`:

```python
from typing import final
```

## Classes finais

Aplicar `@final` quando uma classe possuir uma implementação completa e não fizer sentido permitir sua especialização por herança.

Exemplo:

```python
from typing import final


@final
class CalculadoraMetricas:

    def calcular_rmse(
        self,
        valores_reais: list[float],
        valores_previstos: list[float],
    ) -> float:
        ...
```

Regras:

- Utilizar `@final` quando a classe não fizer parte de uma hierarquia extensível.
- Não aplicar `@final` em classes abstratas destinadas à herança.
- Não aplicar indiscriminadamente em todas as classes concretas.
- Preferir composição quando for necessário reutilizar funcionalidades de uma classe final.

## Métodos finais

Aplicar `@final` quando um método herdado não puder ter seu comportamento alterado por subclasses.

Exemplo:

```python
from typing import final
from typing_extensions import override


class TreinadorBase:

    def validar_modelo(self) -> bool:
        ...


class TreinadorRidge(TreinadorBase):

    @final
    @override
    def validar_modelo(self) -> bool:
        return True
```

Nesse exemplo, subclasses de `TreinadorRidge` não deverão sobrescrever `validar_modelo()`.

## Integração com `@override`

Quando um método sobrescrever outro da classe base e também precisar impedir novas sobrescritas, utilizar ambos os decoradores:

```python
@final
@override
def validar_modelo(self) -> bool:
    ...
```

## Validação estática

O decorador `@final` é utilizado principalmente por verificadores estáticos de tipos, como Pyright e mypy.

**Importante:** `@final` não impede herança ou sobrescrita durante a execução normal do Python. A restrição deve ser verificada pelo type checker configurado em modo `strict`.

## Regra arquitetural

Utilizar os decoradores conforme a responsabilidade:

| Decorador | Aplicação |
|---|---|
| `@final` | Impedir herança de classes ou sobrescrita de métodos no contrato estático. |
| `@override` | Declarar explicitamente a sobrescrita de um método herdado. |
| `@abstractmethod` | Exigir implementação de métodos em subclasses concretas. |
| `@property` | Controlar acesso, validação ou transformação de atributos. |
| `@staticmethod` | Definir operações que não dependem do estado da instância ou da classe. |
| `@classmethod` | Definir operações relacionadas à classe, incluindo métodos de fábrica. |

**Princípio:** utilizar `@final` para proteger contratos arquiteturais que não devem ser estendidos, sem prejudicar a extensibilidade legítima do projeto.

---

# Exceções

Criar exceções próprias em português.

Exemplo:

```python
class ErroCarregamentoDados(RuntimeError):
    pass
```

Preservar a exceção original:

```python
try:
    ...
except OSError as erro:
    raise ErroCarregamentoDados(
        "Não foi possível carregar os dados."
    ) from erro
```

Evitar:

```python
except Exception:
    pass
```

Nunca ignorar erros silenciosamente.

Evitar capturar `Exception` de forma indiscriminada.

---

# Configuração

Toda configuração variável deverá vir de arquivos YAML.

Evitar hardcoded de:

```text
parâmetros
hiperparâmetros
thresholds
features
target
modelos
scalers
encoders
tuning
validação cruzada
drift
métricas
infraestrutura
regras de negócio
```

O código Python deverá implementar comportamento.

O YAML deverá definir configuração.

---

# Pandas

Priorizar processamento vetorizado.

Evitar:

```python
iterrows()
itertuples()
apply(axis=1)
```

quando houver solução vetorizada.

Evitar:

```text
for sobre linhas
for sobre índices
atribuição célula a célula
transformação manual registro por registro
```

A ordem preferencial é:

```text
operações vetorizadas
↓
Series.str / Series.dt / Series.cat
↓
assign / where / mask
↓
numpy.where / numpy.select
↓
groupby.agg / groupby.transform
↓
merge / join
↓
isin / between
↓
fillna / replace / clip
```

Exemplo incorreto:

```python
for indice, linha in dataframe.iterrows():
    dataframe.loc[indice, "preco_m2"] = (
        linha["Valor_da_Venda"] / linha["Metragem"]
    )
```

Preferir:

```python
dataframe = dataframe.assign(
    preco_m2=dataframe["Valor_da_Venda"].div(
        dataframe["Metragem"]
    )
)
```

---

# Polars

Utilizar `polars` quando o processamento tabular se beneficiar de execução eficiente, avaliação lazy, paralelismo ou redução do consumo de memória.

A escolha entre `pandas` e `polars` deverá considerar o volume dos dados, as operações necessárias, a compatibilidade com as bibliotecas do projeto e a clareza do código. Não migrar automaticamente um fluxo para Polars sem benefício técnico demonstrável.

## Regras de uso

- Manter os nomes oficiais da biblioteca externa: `polars`, `pl.DataFrame`, `pl.LazyFrame` e demais APIs.
- Preferir operações nativas e expressões Polars a loops Python sobre linhas.
- Preferir `select`, `with_columns`, `filter`, `group_by`, `agg`, `join`, `when/then/otherwise` e expressões `pl.col(...)` quando forem adequadas.
- Preferir `LazyFrame` e a cadeia de operações lazy para fluxos tabulares extensos, permitindo ao otimizador planejar a execução.
- Utilizar `collect()` somente no ponto em que seja necessário materializar o resultado de uma consulta lazy.
- Usar `scan_csv`, `scan_parquet` ou outras funções de leitura lazy compatíveis com a fonte quando isso evitar carregar os dados antecipadamente.
- Evitar converter repetidamente entre `pandas.DataFrame`, `polars.DataFrame`, listas e dicionários sem necessidade.
- Não presumir que uma operação lazy será sempre mais rápida; medir o desempenho no fluxo real.
- Verificar a compatibilidade de cada modelo, transformador e ferramenta de Machine Learning antes de escolher Polars como formato de entrada.
- Não usar Polars como justificativa para ignorar validação de schema, tipagem, qualidade dos dados ou prevenção de data leakage.

## Exemplo vetorizado

```python
import polars as pl

dados = pl.DataFrame(
    {
        "Valor": [250_000.0, 320_000.0, 410_000.0],
        "Metragem": [70.0, 80.0, 100.0],
    }
)

dados = dados.with_columns(
    (pl.col("Valor") / pl.col("Metragem")).alias("preco_m2")
)
```

## Exemplo com avaliação lazy

```python
import polars as pl

consulta = (
    pl.scan_parquet("dados/imoveis.parquet")
    .filter(pl.col("Metragem") > 0)
    .with_columns(
        (pl.col("Valor") / pl.col("Metragem")).alias("preco_m2")
    )
    .group_by("Bairro")
    .agg(
        pl.col("Valor").median().alias("mediana_valor"),
        pl.col("preco_m2").mean().alias("media_preco_m2"),
    )
)

resultado = consulta.collect()
```

## Integração com Pandas e Machine Learning

- Escolher um formato de dados principal por etapa do pipeline, evitando conversões desnecessárias.
- Converter para Pandas apenas quando uma biblioteca ou API exigir esse formato, ou quando a conversão tiver sido validada como apropriada.
- Confirmar que a conversão preserva tipos, valores ausentes, categorias, ordem das colunas e semântica dos dados.
- Ajustar imputadores, encoders, scalers e demais transformadores exclusivamente nos dados de treino de cada fold.
- Em validação cruzada, construir e ajustar o pré-processamento dentro do pipeline de cada fold para evitar vazamento de dados.
- Testar resultados e métricas após qualquer mudança de Pandas para Polars; não assumir equivalência apenas porque as operações parecem semelhantes.

---

# Loops Python

Loops não são proibidos no projeto.

Podem ser utilizados para:

```text
modelos
folds
strategies
experimentos
arquivos
configurações
objetos
componentes de infraestrutura
```

A restrição aplica-se principalmente ao processamento tabular linha a linha no pandas quando houver solução vetorizada.

---

# map

`map()` poderá ser utilizado quando representar de forma clara uma transformação funcional.

Exemplo:

```python
nomes_normalizados = list(
    map(str.lower, nomes_modelos)
)
```

Preferir `map()` principalmente quando:

```text
a transformação já existe como função
não há necessidade de lógica complexa
a intenção permanecer clara
```

Não utilizar `map()` apenas para evitar uma compreensão mais legível.

---

# filter

`filter()` poderá ser utilizado para filtrar iteráveis quando houver um predicado claro.

Exemplo:

```python
modelos_ativos = list(
    filter(
        verificar_modelo_ativo,
        configuracoes_modelos,
    )
)
```

Para estruturas pandas, continuar priorizando:

```python
loc
query
isin
between
where
mask
```

em vez de converter dados para listas e usar `filter()`.

---

# reduce

Quando for necessário realizar uma redução funcional, utilizar:

```python
from functools import reduce
```

Exemplo:

```python
resultado = reduce(
    combinar_resultados,
    resultados_modelos,
)
```

Usar `reduce()` somente quando representar claramente uma composição/redução sucessiva.

Para operações simples, preferir funções nativas:

```python
sum()
min()
max()
all()
any()
```

---

# zip

Utilizar `zip()` para percorrer iteráveis relacionados em paralelo.

Exemplo:

```python
for nome_modelo, resultado in zip(
    nomes_modelos,
    resultados,
    strict=True,
):
    ...
```

Em Python moderno, quando os iteráveis deveriam obrigatoriamente possuir o mesmo tamanho, preferir:

```python
zip(..., strict=True)
```

Isso permite detectar inconsistências silenciosas.

---

# zip_longest

Quando os iteráveis puderem possuir comprimentos diferentes e isso for parte intencional da regra, utilizar:

```python
from itertools import zip_longest
```

Exemplo:

```python
for esperado, obtido in zip_longest(
    valores_esperados,
    valores_obtidos,
    fillvalue=None,
):
    ...
```

Não utilizar `zip_longest()` quando diferenças de tamanho representarem erro. Nesse caso, preferir:

```python
zip(..., strict=True)
```

---

# itertools

Preferir ferramentas da biblioteca padrão quando reduzirem código manual e deixarem a intenção clara.
