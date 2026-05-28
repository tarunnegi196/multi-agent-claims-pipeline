import pathlib
from pydantic_settings import BaseSettings

_ROOT = pathlib.Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    gemini_api_key: str = ""
    db_path: str = str(pathlib.Path(__file__).parent.parent / "claims.db")
    policy_file: str = str(_ROOT / "data" / "policy_terms.json")
    upload_dir: str = str(pathlib.Path(__file__).parent.parent / "uploads")

    # Logging
    log_level: str = "INFO"    # DEBUG | INFO | WARNING | ERROR
    log_format: str = "pretty" # pretty (dev) | json (prod/cloud)

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
