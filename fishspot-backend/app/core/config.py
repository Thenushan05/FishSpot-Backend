from pydantic import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me"
    DATABASE_URL: str = "sqlite:///./fishspot.db"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7
    MODEL_PATH: str = "app/ml/xgb_classification_tuned.joblib"

    class Config:
        env_file = ".env"


settings = Settings()
