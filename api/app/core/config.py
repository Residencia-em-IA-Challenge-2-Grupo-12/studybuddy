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
    # Timeouts (s) das chamadas ao Ollama: sem eles, uma geração travada prende a thread para sempre
    ollama_timeout_llm: float = 300
    ollama_timeout_embedding: float = 30

    # Porteiro: vazio = corte calibrado do embedding ativo; número = corte manual; "desligado" = sem porteiro
    porteiro_tau: str = ""

    # .env de api/, de onde quer que o processo seja iniciado.
    # extra="ignore": o api/.env também guarda chaves do notebook (OPENAI_API_KEY, LLM_PROVIDER...)
    model_config = SettingsConfigDict(env_file=API_DIR / ".env", extra="ignore")


settings = Settings()
