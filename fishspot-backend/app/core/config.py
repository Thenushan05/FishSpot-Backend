import os


class Settings:
    """Small env-backed settings object (avoids pydantic version issues in dev)."""
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me")
    DATABASE_URL: str = os.environ.get("DATABASE_URL", "sqlite:///./fishspot.db")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))
    REFRESH_TOKEN_EXPIRE_MINUTES: int = int(os.environ.get("REFRESH_TOKEN_EXPIRE_MINUTES", 60 * 24 * 30))
    MODEL_PATH: str = os.environ.get("MODEL_PATH", "app/ml/xgb_classification_tuned.joblib")


settings = Settings()
