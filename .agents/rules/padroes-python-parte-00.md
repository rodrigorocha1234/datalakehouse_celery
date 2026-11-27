Regras gerais de Python do projeto

- Utilizar **Python 3.11** como versão oficial do projeto; não gerar sintaxe exclusiva de Python 3.12+.

- Usar **tipagem forte e explícita** em todo código próprio.

- É proibido utilizar:

```python
Any
typing.Any
```

- Não utilizar `Any` direta ou indiretamente como forma de contornar problemas de tipagem.

- Preferir recursos modernos de tipagem quando houver necessidade semântica real:

```python
Protocol
TypeVar
Generic
Self
Literal
Final
@final
ClassVar
TypeAlias
@override
@overload
@runtime_checkable
```

- Em Python 3.11, instalar `typing_extensions` e utilizar:

```python
from typing_extensions import override
```

- Não utilizar:

```python
from typing import *
```

- Importar somente os recursos efetivamente utilizados.

---

## Nomenclatura

- Nomes próprios do projeto deverão ser escritos em **português**.

Isso se aplica a:

```text
classes
métodos
funções
atributos
enums
protocolos
serviços
adapters
factories
repositórios
exceções
pacotes
módulos
```

- Bibliotecas externas deverão manter seus nomes oficiais.

Exemplo:

```python
from sklearn.pipeline import Pipeline
```

---

## Módulos e pacotes

- Todo módulo ou pacote Python próprio deverá possuir **exatamente duas palavras**, separadas por `_`.

Exemplos:

```text
registro_logs.py
contrato_dados.py
coletor_metricas.py
configuracao_logs.py
modelos_regressao/
motor_sklearn/
gestao_dados/
```

- Não utilizar hífen em módulos ou pacotes importáveis.

Evitar:

```text
registro-logs.py
```

- Exceções são permitidas quando o Python ou alguma ferramenta exigir nomes específicos:

```text
__init__.py
__main__.py
conftest.py
```

---

## Não sombrear bibliotecas

Não criar módulos ou pacotes próprios com nomes iguais aos da biblioteca padrão ou dependências externas.

Evitar:

```text
logging.py
json.py
typing.py
pathlib.py
asyncio.py
enum.py
dataclasses.py
statistics.py
random.py
collections.py
itertools.py
functools.py

pandas.py
numpy.py
sklearn.py
mlflow.py
requests.py
pyspark.py
```

---

## Métodos

- Métodos deverão representar ações claras.

Preferir:

```python
carregar_dados()
validar_schema()
separar_holdout()
treinar_modelo()
calcular_metricas()
registrar_resultado()
verificar_drift()
selecionar_modelo()
```

- Evitar nomes excessivamente genéricos:

```python
run()
execute()
process()
handle()
```

quando existir uma ação de domínio mais clara.

---

# Encapsulamento

O projeto deverá utilizar encapsulamento de forma consistente.

Em Python, os níveis de acesso são representados principalmente por convenções de nomenclatura.

## Atributos públicos

Atributos públicos podem ser acessados diretamente quando fizer sentido expô-los como parte da interface da classe.

Exemplo:

```python
class ResultadoModelo:
    def __init__(self, nome_modelo: str) -> None:
        self.nome_modelo = nome_modelo
```

Usar atributos públicos somente quando seu acesso direto não violar invariantes ou regras de domínio.

---

## Atributos protegidos

Atributos destinados ao uso interno da classe e de subclasses deverão utilizar um `_` inicial.

Exemplo:

```python
class ModeloBase:
    def __init__(self, nome_modelo: str) -> None:
        self._nome_modelo = nome_modelo
```

A convenção:

```text
_nome
```

significa:

```text
uso interno/protegido por convenção
```

Não significa proteção real em runtime.

---

## Atributos privados

Quando houver necessidade real de evitar colisões em subclasses ou proteger detalhes internos de implementação, utilizar `__`.

Exemplo:

```python
class GerenciadorModelo:
    def __init__(self, versao: str) -> None:
        self.__versao = versao
```

Python aplica *name mangling*, transformando internamente o atributo.

Entretanto, isso não representa privacidade absoluta como em Java ou C#.

Utilizar atributos privados somente quando houver justificativa de encapsulamento.

Não transformar todos os atributos em privados indiscriminadamente.

---

# Métodos públicos

Métodos públicos representam operações oferecidas oficialmente pela classe.

Exemplo:

```python
class TreinadorModelo:
    def treinar_modelo(self) -> None:
        ...
```

São a interface principal utilizada por outros componentes.

---

# Métodos protegidos

Métodos auxiliares destinados à própria classe ou subclasses deverão utilizar `_`.

Exemplo:

```python
class TreinadorBase:

    def treinar_modelo(self) -> None:
        dados = self._preparar_dados()
        self._ajustar_modelo(dados)

    def _preparar_dados(self) -> pd.DataFrame:
        ...

    def _ajustar_modelo(
        self,
        dados: pd.DataFrame,
    ) -> None:
        ...
```

---

# Métodos privados

Métodos estritamente internos poderão utilizar `__`.

Exemplo:

```python
class ValidadorDados:

    def validar_dados(self) -> bool:
        return self.__validar_regras_internas()

    def __validar_regras_internas(self) -> bool:
        ...
```

Utilizar apenas quando houver necessidade real.

Preferir métodos protegidos para extensibilidade quando subclasses puderem precisar sobrescrever o comportamento.

---

# Properties

Quando o acesso a um atributo exigir:

```text
validação
transformação
controle
cálculo
proteção de invariantes
```

utilizar `@property`.

Exemplo:

```python
class ConfiguracaoModelo:
    def __init__(self, nome_modelo: str) -> None:
        self._nome_modelo = nome_modelo

    @property
    def nome_modelo(self) -> str:
        return self._nome_modelo
```

Quando houver alteração controlada:

```python
class ConfiguracaoModelo:
    def __init__(self, limite: float) -> None:
        self._limite = limite

    @property
    def limite(self) -> float:
        return self._limite

    @limite.setter
    def limite(self, valor: float) -> None:
        if valor < 0:
            raise ValueError("O limite não pode ser negativo.")

        self._limite = valor
```

Não criar getters e setters artificiais no estilo:

```python
get_nome()
set_nome()
```

quando uma `property` representar melhor o contrato.

---

# Uma classe principal por arquivo

Preferir:

```text
uma classe principal por arquivo .py
```

Exceções podem existir para:

```text
dataclasses pequenas
Enums relacionados
estruturas fortemente coesas
```

Evitar:

```text
God Classes
classes gigantes
arquivos com dezenas de responsabilidades
```

---

# SOLID

Aplicar de forma prática:

```text
Single Responsibility Principle
Open/Closed Principle
Liskov Substitution Principle
Interface Segregation Principle
Dependency Inversion Principle
```

Não criar interfaces, factories ou abstrações apenas para demonstrar padrões de projeto.

Toda abstração deverá resolver um problema concreto.

---

# Composição e herança

Preferir:

```text
composição
```

quando não houver relação clara de:

```text
"é um"
```

Utilizar herança quando existir:

```text
contrato compartilhado
relação semântica apropriada
Template Method
comportamento comum legítimo
```

Evitar hierarquias profundas.

---

# Classes abstratas

Quando herança fizer parte do design, utilizar:

```python
from abc import ABC, abstractmethod
```

Exemplo:

```python
class EstrategiaModelo(ABC):

    @abstractmethod
    def criar_modelo(self) -> RegressorMixin:
        ...
```

Não utilizar permanentemente:

```python
raise NotImplementedError
```

como substituto de `@abstractmethod`.

---

# @override

Sempre utilizar `@override` quando um método sobrescrever explicitamente um método da classe base.

Exemplo:

