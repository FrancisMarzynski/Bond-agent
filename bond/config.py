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

settings = Settings()
