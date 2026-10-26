from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://quantpilot:quantpilot@127.0.0.1:5432/quantpilot"
    apca_api_key_id: SecretStr = SecretStr("")
    apca_api_secret_key: SecretStr = SecretStr("")


settings = Settings()
