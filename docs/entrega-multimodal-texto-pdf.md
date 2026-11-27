# Assistente multimodal de texto e PDF

## O que a demonstração suporta

A demonstração combina uma pergunta digitada com um PDF digital que contém texto selecionável. O sistema extrai texto por página com `pypdf` e usa o modelo local do Ollama para responder.

| Limite | Valor |
|---|---:|
| Tamanho do arquivo | 10 MiB |
| Páginas | 5 |
| Texto extraído | 20.000 caracteres |

O fluxo não usa OCR, embeddings, ChromaDB ou a rota HTTP existente. O arquivo fica em memória durante a execução e não é associado a uma conta.

## Instalação e configuração

Inicie o Ollama e instale as dependências da API:

```bash
cd api
python -m pip install -r requirements.txt
```

Confirme que o modelo escolhido está instalado com `ollama list`. O código usa `OLLAMA_LLM_MODEL`. Defina essa variável para um modelo disponível na máquina.

```bash
export OLLAMA_LLM_MODEL=llama3.2:latest
```

O endereço padrão do Ollama é `http://localhost:11434`. Defina `OLLAMA_BASE_URL` se o serviço estiver em outro endereço.

## Executar a demonstração

Execute o comando a partir de `api/`:

```bash
python demo_multimodal_pdf.py \
  tests/fixtures/multimodal/ementa_texto.pdf \
  "Quando será a prova de biologia?"
```

A saída mostra o estado, a resposta e as evidências:

```text
Status: RESPONDIDA
Resposta: A prova de biologia sera em 10 de junho.
Páginas: 2
  Página 2: "A prova de biologia sera em 10 de junho."
```

Se o PDF não sustentar a resposta, a demonstração imprime `SEM_EVIDENCIA` e não mostra citações. Arquivos inválidos e falhas do Ollama terminam com uma mensagem de erro e código de saída diferente de zero.

## Evidências e proteções

O sistema aceita uma resposta como fundamentada apenas se cada citação apontar para uma página existente e o trecho aparecer nessa página após a normalização de espaços. A aplicação substitui respostas sem evidência válida por uma recusa fixa.

A barreira `avaliar` verifica padrões conhecidos de prompt injection na pergunta e no texto extraído. O sistema também envolve a pergunta e o documento com `envolver_input` antes de enviá-los ao modelo.

Essa barreira não detecta toda instrução maliciosa. A validação confirma que a citação existe, mas não prova que ela sustenta semanticamente cada afirmação da resposta. Confira a saída antes de usar informações importantes.

## Limitações e falhas conhecidas

| Caso | Comportamento | Mitigação |
|---|---|---|
| PDF escaneado, sem texto extraível | A entrada é recusada | Use um PDF digital com texto selecionável |
| PDF inválido, protegido por senha ou acima dos limites | A entrada é recusada antes da chamada ao modelo | Corrija o arquivo ou use um PDF menor e sem senha |
| Pergunta ou documento contém um padrão conhecido de injection | A consulta é bloqueada antes do Ollama | Remova o trecho bloqueado ou revise o documento |
| Pergunta sem resposta sustentada pelo PDF | O sistema retorna `SEM_EVIDENCIA` | Consulte um documento que contenha a informação |
| Ollama indisponível ou resposta fora do formato | A demonstração mostra um erro e não apresenta resposta como sucesso | Inicie o Ollama, confirme o modelo e tente novamente |

Imagens, PDFs escaneados, OCR, áudio, vídeo, interface web, persistência de documentos e isolamento por estudante não fazem parte desta versão.

## Verificação local

Os testes automatizados não chamam o Ollama:

```bash
cd api
python -m pytest -q tests/test_multimodal_pdf.py
```

A demonstração acima foi executada com `llama3.2:latest` no Ollama local. A resposta citou a página 2. Uma pergunta sobre a capital da Austrália retornou `SEM_EVIDENCIA`.

O baseline da rota `POST /assistente/perguntar` não foi medido nesta execução porque `api/chroma_db/` não estava disponível. Não há comparação de latência ou alegação de desempenho.
