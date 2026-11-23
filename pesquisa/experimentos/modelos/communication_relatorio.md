# Relatório: modelos locais no agente Communication

Data: 2026-11-23  
Máquina: Darwin 27.0.0, arm64, 24 GB de RAM, Ollama 0.32.5  
Experimento: `pesquisa/experimentos/modelos/communication_runner.py`

## Objetivo

Escolher o modelo local que escreve a abertura do agente Communication com a melhor
relação entre qualidade do texto e custo. O plano da semana é montado em código, sem LLM;
a comparação isola a única parte que o modelo produz: a abertura da mensagem.

## Método

- **Entrada fixa:** a mesma grade aprovada, as mesmas duas evidências e 10 check-ins rotulados
  (`communication_cenarios.json`). Para cada cenário, o tom esperado é validado pela regra do
  agente antes da rodada.
- **Execução:** `temperature=0`, 3 repetições por modelo × cenário (30 chamadas por modelo).
  O mesmo `montar_mensagem` do agente roda com um medidor em volta do `ChatOllama`.
- **Métricas automáticas:**
  - *plano fiel*: todo bloco da grade aparece no texto, na ordem;
  - *horários inventados*: horários no texto que não existem na grade;
  - *citações inválidas*: citações removidas pelo verificador;
  - *latência*: mediana e p95 da chamada ao LLM, em segundos;
  - *tokens/s* e *caracteres úteis*: vazão e tamanho do texto que chega ao usuário;
  - *fração descartada*: quanto da saída bruta era raciocínio removido antes de sair;
  - *VRAM*: memória do modelo em execução, lida em `/api/ps`.
- **Leitura cega:** aberturas embaralhadas, sem o nome do modelo, com notas humanas de 1 a 5
  para naturalidade e adequação ao tom.

Limite conhecido do método: as métricas de tom e de plano são determinísticas (não usam LLM),
então servem como trava contra regressão, não para ranquear modelos.

## Resultados automáticos

| modelo | n | erros | plano fiel | horários inventados | citações inválidas | latência mediana (s) | p95 (s) | tokens/s | chars úteis | descartado | VRAM (MB) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `llama3.1:8b` | 30 | 0 | 100% | 0 | 0 | 13,71 | 18,00 | 6,5 | 281 | 0% | 5.019,5 |
| `gemma3:12b` | 30 | 0 | 100% | 0 | 0 | 21,55 | 32,05 | 4,5 | 358 | 0% | 7.676,3 |
| `qwen3:4b` | 30 | 0 | 100% | 0 | 0 | **168,12** | **347,52** | 21,1 | 351 | **97%** | 3.022,9 |

Os três acertaram o tom em 100% dos casos, não inventaram horário nem citação. A diferença
está no custo e no texto.

O `qwen3:8b`, modelo padrão atual, não entrou nesta rodada. A execução anterior registrada em
[communication.md](communication.md) (n=10, prompt antigo) deu mediana de 10,59 s, p95 de
18,61 s, 14,9 tok/s, 323 caracteres úteis, 5.645 MB de VRAM e 0% descartado. Serve como pista,
não como comparação direta.

## Leitura cega (avaliação humana)

Notas médias de 10 aberturas por modelo, escala 1–5. A leitura foi feita sobre o **prompt antigo**,
que ainda chamava o estudante de "Tom" — por isso as notas do llama e do qwen3:4b estão contaminadas.

| modelo | naturalidade | tom | média | observação |
|---|---:|---:|---:|---|
| `gemma3:12b` | 3,50 | 3,70 | **3,60** | sem artefatos |
| `qwen3:8b` | 2,90 | 3,00 | 2,95 | sem artefatos |
| `qwen3:4b` | 2,40 | 2,60 | 2,50 | usou `[Nome]` e emojis em 4 de 10; sem esses casos, 2,67/2,83 |
| `llama3.1:8b` | 2,20 | 2,60 | 2,40 | chamou o estudante de "Tom" em 8 de 10; sem esses casos, 3,00/3,00 (n=2) |

As notas por item estão em [avaliacao_humana.csv](resultados/avaliacao_humana.csv).

## Análise

- **`qwen3:4b` está fora.** 168 s de mediana e 97% do que gera é raciocínio descartado. Mesmo que o
  texto final seja aceitável, o custo por mensagem torna o agente inviável.
- **`llama3.1:8b` é o mais barato.** Menor latência, menor memória, texto mais curto. A nota humana
  baixa mede o bug do "Tom", já corrigido no prompt — precisa ser reavaliada.
- **`gemma3:12b` tem o melhor texto.** Ganhou com folga na leitura humana, mas é ~60% mais lento e
  usa ~2,6 GB mais de memória que o llama.
- **`qwen3:8b` é o incumbente e o equilíbrio provável.** Nos dados antigos foi o mais rápido no caso
  típico, sem raciocínio descartado e sem artefatos de nome. Falta repetir a medição com o prompt
  corrigido para confirmar.

## Recomendação

1. **Se custo e previsibilidade pesam mais:** `llama3.1:8b`.
   p95 de 18,0 s contra 18,61 s do incumbente — dentro do limite de 2× do plano — e 5 GB de VRAM.
2. **Se qualidade do texto pesa mais:** `gemma3:12b`. Melhor nota humana; p95 de 32,05 s ainda
   abaixo do limite de 2× (37,2 s), mas com o dobro de memória.
3. **`qwen3:4b`:** descartar.
4. **Antes de fechar:** rodar `qwen3:8b` com o prompt corrigido e refazer a leitura cega de llama e
   gemma. Sem isso, a decisão fica apoiada em notas parciais.

## Limitações

- 10 cenários, não os 20 exigidos pelo PR-6.
- Sem juiz-LLM para naturalidade; só leitura humana.
- A leitura humana usou o prompt antigo e a atribuição modelo→abertura foi conferida pelo gabarito.
- `qwen3:8b` não foi medido nas mesmas condições dos demais.
- Latência e VRAM dependem desta máquina e da carga do Ollama; não são transferíveis.
- A execução antiga em `modelos/` foi feita com 1 repetição e prompt antigo; está aqui apenas como
  referência do incumbente.

## Como reproduzir

```bash
# 3 modelos, 10 cenários, 3 repetições
python pesquisa/experimentos/modelos/communication_runner.py \
  --modelos llama3.1:8b,gemma3:12b,qwen3:4b --repeticoes 3 \
  --saida pesquisa/experimentos/modelos/resultados

# incumbente com o prompt corrigido
python pesquisa/experimentos/modelos/communication_runner.py \
  --modelos qwen3:8b --repeticoes 3 \
  --saida pesquisa/experimentos/modelos/resultados/qwen3_8b
```

## Arquivos

- [communication.md](resultados/communication.md) — relatório automático mesclado
- [communication.csv](resultados/communication.csv) — uma linha por execução
- [communication_cego.md](resultados/communication_cego.md) — leitura cega das 30 aberturas
- [communication_gabarito.json](resultados/communication_gabarito.json) — gabarito da leitura cega
- [avaliacao_humana.csv](resultados/avaliacao_humana.csv) — notas da leitura cega por item
