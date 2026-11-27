
Recursos úteis incluem:

```python
chain
combinations
combinations_with_replacement
permutations
product
islice
takewhile
dropwhile
groupby
cycle
repeat
accumulate
pairwise
zip_longest
```

Exemplos de aplicação no projeto:

```text
combinações de modelos
combinações de parâmetros
encadeamento de coleções
processamento lazy
comparações entre modelos
criação de pares
geração de produtos cartesianos
```

Exemplo:

```python
from itertools import combinations

pares_modelos = combinations(
    nomes_modelos,
    2,
)
```

Evitar materializar iteradores em listas sem necessidade.

---

# Iteradores e avaliação lazy

Quando possível, preservar processamento lazy.

Preferir:

```python
iterador = map(...)
```

quando não for necessário criar imediatamente uma lista.

Converter para:

```python
list(...)
tuple(...)
```

somente quando o consumidor exigir materialização.

Isso é especialmente importante para conjuntos grandes de dados que não estejam sendo manipulados por pandas.

---

# collections

Utilizar estruturas especializadas de `collections` quando representarem melhor o problema.

Recursos recomendados:

```python
Counter
defaultdict
deque
ChainMap
namedtuple
```

Usar somente quando houver vantagem sobre estruturas básicas.

---

# Counter

Utilizar:

```python
from collections import Counter
```

para contagem de elementos em iteráveis Python.

Exemplo:

```python
frequencias = Counter(nomes_modelos)
```

Para colunas pandas, normalmente preferir:

```python
serie.value_counts()
```

---

# defaultdict

Utilizar:

```python
from collections import defaultdict
```

quando houver necessidade legítima de valores padrão durante agrupamento ou acumulação.

Exemplo:

```python
resultados: defaultdict[str, list[float]] = defaultdict(list)
```

Não utilizar quando `dict` normal oferecer contrato mais explícito.

---

# deque

Utilizar:

```python
from collections import deque
```

quando houver necessidade de:

```text
fila
pilha
buffer
janela deslizante
inserções e remoções eficientes nas extremidades
```

Evitar `list.pop(0)` para implementação frequente de filas.

---

# ChainMap

Utilizar:

```python
from collections import ChainMap
```

quando for necessário representar múltiplas camadas de configuração sem copiar todos os dicionários.

Possíveis casos:

```text
configuração padrão
configuração de ambiente
configuração específica do modelo
override de execução
```

Utilizar apenas se o comportamento de precedência estiver claramente documentado.

---

# namedtuple

`namedtuple` poderá ser utilizado para estruturas leves e imutáveis.

Entretanto, quando houver regras de domínio, validação, tipos mais ricos ou comportamento associado, preferir:

```python
@dataclass(frozen=True)
```

ou uma classe de domínio dedicada.

---

# Compreensões

Compreensões são permitidas quando simples e legíveis:

```python
modelos_ativos = [
    nome
    for nome in nomes_modelos
    if nome in configuracoes
]
```

Evitar compreensões profundamente aninhadas ou contendo múltiplas regras de negócio.

Quando a lógica crescer, extrair para uma função com nome semântico.

---

# Generators e iterators

Utilizar `generators` e `iterators` para percorrer sequências de forma incremental, especialmente quando não for necessário manter todos os elementos simultaneamente em memória.

## Iterators

Um iterador é um objeto que fornece elementos um de cada vez e mantém seu estado de iteração. Em geral, pode ser consumido uma única vez.

- Preferir `iter()` e `next()` quando o controle explícito da iteração for necessário.
- Não presumir que um iterador possa ser reutilizado depois de consumido.
- Materializar com `list()` ou `tuple()` somente quando o contrato do consumidor exigir uma coleção concreta ou múltiplas passagens.
- Tratar o fim normal da iteração por meio do protocolo de iteração; evitar tratar `StopIteration` indiscriminadamente fora desse contexto.
- Documentar quando uma função retorna um iterador consumível uma única vez.

Exemplo:

```python
nomes_modelos = iter(("Ridge", "RandomForest", "HistGradientBoosting"))

primeiro_modelo = next(nomes_modelos)
```

## Generators

Um generator é uma forma de criar um iterador, normalmente usando uma função com `yield` ou uma generator expression.

- Preferir generators quando os elementos puderem ser produzidos sob demanda.
- Usar `yield` para emitir resultados incrementalmente sem construir uma coleção completa.
- Evitar guardar em memória todos os resultados de grandes sequências quando o consumidor puder processá-los um por vez.
- Não usar generators quando for necessário acessar elementos por índice, percorrer a sequência várias vezes ou disponibilizar uma coleção materializada.
- Manter funções geradoras simples, com responsabilidade clara e tipos de retorno explícitos, como `Iterator[ResultadoModelo]` ou `Generator[ResultadoModelo, None, None]`, conforme o contrato necessário.
- Não confundir avaliação lazy com execução paralela: um generator, por si só, não executa trabalho em paralelo.

Exemplo:

```python
from collections.abc import Iterator

def gerar_nomes_modelos() -> Iterator[str]:
    yield "Ridge"
    yield "RandomForest"
    yield "HistGradientBoosting"
```

## Aplicações no projeto

Generators e iterators podem ser úteis para:

```text
leitura incremental de registros
processamento de arquivos grandes
produção de resultados de experimentos
encadeamento de etapas compatíveis com iteráveis
avaliação sob demanda de combinações
redução do uso de memória fora de operações tabulares vetorizadas
```

Não utilizar generators para substituir operações vetorizadas de Pandas ou expressões nativas de Polars quando estas forem mais adequadas ao processamento tabular.

---

# Generator expressions

Preferir generator expressions quando não houver necessidade de materializar todos os elementos.

Exemplo:

```python
quantidade_ativos = sum(
    1
    for modelo in modelos
    if modelo.ativo
)
```

---

# enumerate

Quando for necessário índice e elemento ao mesmo tempo, utilizar:

```python
for indice, modelo in enumerate(modelos):
    ...
```

em vez de:

```python
for indice in range(len(modelos)):
    modelo = modelos[indice]
```

Essa regra não autoriza processamento linha a linha de `DataFrame`.

---

# Padrões de projeto

Utilizar quando resolverem problemas concretos:

```text
Strategy
Factory
Adapter
Observer
Repository
Facade
```

Outros padrões poderão ser utilizados quando tecnicamente justificados.

Não adicionar padrões apenas para aumentar a quantidade de abstrações do projeto.

---

# Qualidade arquitetural

O código deverá ser:

```text
desacoplado
testável
reutilizável
coeso
extensível
fortemente tipado
observável
configurável
```

Separar claramente:

```text
domínio
infraestrutura
configuração
persistência
orquestração
Machine Learning
observabilidade
regras de negócio
```

---

# Testes

Utilizar:

```text
pytest
```

Criar:

```text
testes unitários
testes de integração
testes de contrato
testes parametrizados
```

Utilizar quando apropriado:

```python
@pytest.fixture
@pytest.mark.parametrize
```

Mocks deverão ser utilizados principalmente para dependências externas e efeitos colaterais.

---

# Type checking

Configurar o type checker em modo:

```text
strict
```

Violações críticas de tipagem deverão falhar no CI.

O objetivo é detectar antecipadamente:

```text
tipos incompatíveis
retornos incorretos
parâmetros incorretos
atributos inexistentes
sobrescritas incompatíveis
uso indevido de Optional
```

---

# Regra de prioridade para código Python

Quando houver mais de uma solução possível, preferir nesta ordem:

```text
1. recurso nativo da linguagem
2. biblioteca padrão
3. operação vetorizada da biblioteca utilizada
4. recurso moderno e idiomático do pacote
5. abstração própria
6. implementação manual
```

Exemplo:

```text
sum()
```

é preferível a implementar manualmente um acumulador quando ambos resolvem exatamente o mesmo problema.

Da mesma forma:

```text
zip(..., strict=True)
itertools
collections
functools
```

devem ser preferidos a implementações manuais equivalentes quando aumentarem clareza, segurança e manutenção.

---

# Princípio geral

O projeto deve buscar código:

```text
Python moderno
+
tipagem forte
+
encapsulamento adequado
+
baixo acoplamento
+
alta coesão
+
configuração externa
+
processamento vetorizado
+
biblioteca padrão antes de reinventar soluções
+
testes automatizados
+
arquitetura extensível
```
