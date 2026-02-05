from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://localhost:5432/growth_loop"

    model_config = {"env_prefix": ""}


settings = Settings()
