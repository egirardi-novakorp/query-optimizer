from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    GEMINI_API_KEY: str = ""
    SQLITE_DB: str = "/app/data/history.db"
    
    class Config:
        env_file = ".env"

settings = Settings()
