from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    chroma_path: str = "./data/chroma"
    article_db_path: str = "./data/articles.db"
    low_corpus_threshold: int = 10
    rag_top_k: int = 5
    max_blog_posts: int = 50
    google_auth_method: str = "oauth"
    google_credentials_path: str = "./credentials.json"

    # Phase 2: Author Mode Backend
    checkpoint_db_path: str = "./data/bond_checkpoints.db"
    metadata_db_path: str = "./data/bond_metadata.db"
    research_model: str = "gpt-4o-mini"
    draft_model: str = "gpt-4o"
    min_word_count: int = 800
    duplicate_threshold: float = 0.85

settings = Settings()
