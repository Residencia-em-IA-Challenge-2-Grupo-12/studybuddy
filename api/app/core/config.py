from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

API_DIR = Path(__file__).resolve().parents[2]  # api/


class Settings(BaseSettings):
    app_name: str = "desafio2-api"
    debug: bool = False
    cors_origins: list[str] = ["http://localhost:3000"]

    # Qual pipeline responde em /perguntar: "classico" (T3 + porteiro) ou "agentes" (Triagem + Planejador)
    pipeline: Literal["classico", "agentes"] = "classico"

    # Índice vetorial gerado pelo notebook (pesquisa/rag_pipeline_semana2.ipynb)
    chroma_dir: Path = API_DIR / "chroma_db"
    chroma_collection: str = "residencia_ia_semana2"
    top_k: int = 5

    # Modelos locais (Ollama). Mesmos nomes de variável do notebook.
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "bge-m3"
    ollama_llm_model: str = "qwen3:8b"
    # Triagem (diagnóstico em JSON). Por padrão, o mesmo modelo do gerador
    ollama_triagem_model: str = "qwen3:8b"
    # Analysis (técnica + justificativa de cada material, em JSON). A alocação não usa LLM.
    # Escolha em pesquisa/experimentos/modelos/analysis_escolha.md; alternativa leve: qwen3.5:4b
    ollama_analysis_model: str = "llama3.1:8b"
    # Communication (abertura da mensagem). Separado para trocar o modelo sem tocar no RAG
    ollama_communication_model: str = "qwen3:8b"
    # Guardrails (barreiras 4.4 a 4.7: injection, ódio, saúde e domínio).
    # Escolha justificada em pesquisa/experimentos/modelos/guardrails.md
    ollama_guardrails_model: str = "qwen3:4b-q8_0"
    ollama_guardrails_fallback_model: str = "phi4-mini"
    ollama_timeout_guardrails: float = 15.0
    # Timeouts (s) das chamadas ao Ollama: sem eles, uma geração travada prende a thread para sempre
    ollama_timeout_llm: float = 300
    ollama_timeout_embedding: float = 30

    # Analysis Agent: limiares do Pomodoro adaptativo (índice de capacidade do check-in, 0 a 1)
    analysis_indice_alto: float = 0.7    # >= isto: blocos longos (50/10)
    analysis_indice_baixo: float = 0.4   # < isto: fadiga (25/10)
    # Prioridade: prazo a até N dias do início da semana conta como urgente (entra primeiro e ganha +1 bloco)
    analysis_dias_urgencia: int = 3
    # Redução de danos (rota pedida pelo Maestro): só baixa carga, pausas maiores, poucos blocos por dia
    analysis_reducao_pausa_min: int = 15
    analysis_reducao_max_blocos_dia: int = 3
    # Validation determinístico (agenda, integridade circadiana e sobrecarga pelo check-in)
    validation_carga_max_diaria_min: int = 240       # carga máxima diária em condições normais (4h/dia)
    validation_bloco_continuo_max_min: int = 90      # máximo de foco contínuo sem pausa (1h30)
    validation_percentual_corte: float = 0.30        # corte máximo automático (30%) em estresse alto / privação de sono
    validation_margem_sono_min: int = 60             # margem de higiene do sono antes de dormir (1h)
    validation_estresse_alto: int = 4                # check-in estresse >= 4 (1..5) reduz limiares
    validation_sono_min_horas: float = 6.0           # check-in horas_sono < 6h (privação de sono) reduz limiares

    # Porteiro: vazio = corte calibrado do embedding ativo; número = corte manual; "desligado" = sem porteiro
    porteiro_tau: str = ""

    # .env de api/, de onde quer que o processo seja iniciado.
    # extra="ignore": o api/.env também guarda chaves do notebook (OPENAI_API_KEY, LLM_PROVIDER...)
    model_config = SettingsConfigDict(env_file=API_DIR / ".env", extra="ignore")


settings = Settings()
