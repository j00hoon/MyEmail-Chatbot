import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
load_dotenv(BASE_DIR / ".env")


def _resolve_path(raw_path: str, default_path: Path):
    if not raw_path:
        return default_path
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0] == "backend":
        return BASE_DIR.parent / candidate
    return BASE_DIR / candidate


class Settings:
    app_env: str = os.getenv("APP_ENV", "local")
    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_chat_model: str = os.getenv("OPENAI_CHAT_MODEL", "gpt-5-mini")
    openai_embedding_model: str = os.getenv(
        "OPENAI_EMBEDDING_MODEL",
        "text-embedding-3-small",
    )
    database_url: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(DATA_DIR / 'metadata.db').as_posix()}",
    )
    vector_store_path: Path = _resolve_path(
        os.getenv("VECTOR_STORE_PATH", ""),
        DATA_DIR / "vector_store.json",
    )
    credentials_path: Path = _resolve_path(
        os.getenv("GMAIL_CREDENTIALS_PATH", ""),
        BASE_DIR / "credentials.json",
    )
    token_path: Path = _resolve_path(
        os.getenv("GMAIL_TOKEN_PATH", ""),
        BASE_DIR / "token.json",
    )
    cors_origins: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if origin.strip()
    ]


settings = Settings()
