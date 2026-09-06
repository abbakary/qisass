from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

    secret_key: str = "qisas-dev-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 14
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    gemini_api_key: str = ""
    openai_api_key: str = ""
    ai_provider: str = "auto"
    database_url: str = "sqlite:///./data/qisas.db"
    # Empty = backend/data. On Railway attach a volume and set e.g. /data
    data_dir: str = ""
    # Empty in local/dev. In production set to the CDN origin (CloudFront, R2, etc.)
    # so /media/uploads/... is rewritten to https://cdn.example.com/media/uploads/...
    media_cdn_base: str = ""
    db_pool_size: int = 10
    db_max_overflow: int = 20
    admin_name: str = "Admin"
    admin_phone: str = "0712345678"
    admin_password: str = "admin1234"
    # Set FRESH_START=1 once to wipe catalog/users and keep only admin + categories.
    fresh_start: bool = False
    # OTP: "dev" accepts any code. Switch to beem | africastalking | twilio when keys are set.
    otp_provider: str = "dev"
    otp_api_key: str = ""
    otp_api_secret: str = ""
    otp_sender_id: str = "Qisas"
    otp_expire_seconds: int = 300
    otp_resend_seconds: int = 45
    otp_dev_accept_any: bool = True
    # False = phone + password only. Set OTP_REQUIRED=1 when SMS is live.
    otp_required: bool = False

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
