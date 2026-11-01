from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Invoice Finance MVP"
    database_url: str = "postgresql+psycopg://invoice_app:invoice_app@localhost:5432/invoice_finance"
    raw_invoice_source_dir: Path = Path("/home/elmehdi/Desktop/invoices/test_invoices")
    raw_invoice_storage_dir: Path = Path("storage/raw/invoices")
    default_company_name: str = "Demo Company"
    database_search_path: str = "integration_pipeline,canonical"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
