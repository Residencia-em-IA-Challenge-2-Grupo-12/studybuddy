# Métricas do Research Agent: Pesquisa e Definição ([2.6] Issue #41)

> Documento espelhado em [`docs/research_metrics.md`](../../../../docs/research_metrics.md).

O **Research Agent** é o agente bibliotecário e montador de contexto do sistema multiagente. Ele possui duas frentes:

1. **Montagem Determinística do `ContextoEstudante` e Integração Externa (sem LLM):** persiste o perfil, acervo e histórico no banco do estudante (`RepositorioEstudante` SQLite, `[2.1]`), converte as escalas do check-in e calcula o `indice_capacidade` (`[2.2]`), deriva as janelas circadianas (`picos`, `vales`, `sono` com quebra na meia-noite e `refeicoes`, `[2.2]`) e lê/grava blocos de estudo no Google Calendar (`ProvedorAgenda`, `[2.4]`).
2. **Recuperação no Acervo Científico (ChromaDB RAG) e Curadoria via Modelo Local (com LLM):** formula consultas semânticas calibradas pelo cronotipo, check-in e carga cognitiva (`[2.3]`), recupera os trechos mais próximos no ChromaDB respeitando o porteiro de distância Euclidiana ($L_2$, $\tau = 1.026$) e sintetiza a orientação bibliotecária (`SaidaResearchLLM`) com citações conferidas pelo verificador determinístico (`[2.5]`).

```bash
# A partir de pesquisa/
python -m metricas.agentes.research.runner                          # determinístico + RAG (sem Ollama)
python -m metricas.agentes.research.runner --llm llama3.1:8b        # + curadoria pelo LLM local
python -m metricas.agentes.research.runner --llm llama3.1:8b --juiz # + fidelidade pelo LLM-juiz
python -m pytest -q metricas/agentes/research                       # testes unitários das métricas
```

Consulte [`docs/research_metrics.md`](../../../../docs/research_metrics.md) para as fórmulas detalhadas, faixas, metas (`metricas.METAS`) e referências bibliográficas completas.
