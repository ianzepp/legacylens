from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    pinecone_api_key: str = ""
    pinecone_index_name: str = "legacylens-bench-llama-1024-paragraph"
    pinecone_namespace: str = "carddemo"
    carddemo_path: str = ""

    embedding_provider: str = "pinecone"  # "pinecone" | "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    pinecone_model: str = "llama-text-embed-v2"
    chat_model: str = "google/gemini-2.5-flash-lite"
    top_k: int = 5

    use_ollama: bool = False
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
