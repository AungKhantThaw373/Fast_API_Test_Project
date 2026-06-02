from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    user: str
    password: str
    host: str
    port: str
    dbname: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_KEY: str
    JWT_SECRET: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int



    model_config = SettingsConfigDict(env_file=".env")

# Load and validate settings
settings = Settings()
