from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://social:social@localhost:5432/social"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "dev-secret-change-in-prod-please-use-a-real-secret-key"
    jwt_algorithm: str = "HS256"

    object_storage_backend: str = "local"
    local_storage_dir: str = "/tmp/social-storage"
    s3_bucket: str = "social-media"
    s3_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    api_host: str = "http://localhost:8000"
    storage_secret: str = "dev-storage-secret-change-in-prod"

    frontend_origin: str = "http://localhost:5173"
    debug: bool = False
    db_pool_size: int = 10
    db_max_overflow: int = 20


settings = Settings()