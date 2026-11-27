"""# Research Agent

Monta o `ContextoEstudante` (contrato em `../contratos.py`), integra o Google Calendar (`ProvedorAgenda`) e realiza a curadoria bibliotecária de evidências científicas no ChromaDB.

| Arquivo | O que faz |
| :-- | :-- |
| `banco.py` | Camada de persistência SQLite (`RepositorioEstudante`) com validação Pydantic para perfil do estudante, materiais, metas, check-ins e histórico ([2.1] #40) |
| `circadiano.py` | Quebra de sono na meia-noite, janelas de refeição, derivação de picos e vales circadianos por cronotipo e cálculo do `indice_capacidade` pelo check-in ([2.2] #13) |
| `acervo.py` | Ingestão, segmentação (`chunk_size=500`, `overlap=50`), catálogo de metadados ricos dos 20 artigos científicos, inferência de carga cognitiva e busca filtrada com porteiro L2 ([2.3] #14) |
| `agenda.py` | Protocolo `ProvedorAgenda`: `GoogleCalendarProvedor` (API v3 REST com leitura de janelas e gravação de blocos) e `AgendaFake` determinística ([2.4] #15) |
| `agente.py` | `AgenteResearch`: `montar_contexto()`, `pesquisar_evidencias()`, `curar_recomendacao()` (com LLM local e verificador de citações) e `sincronizar_agenda()` ([2.5] #16) |
"""
