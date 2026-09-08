from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    admin_ids: str = ""
    timezone: str = "Europe/Moscow"

    database_url: str

    yookassa_provider_token: str = ""
    yookassa_shop_id: str = ""
    yookassa_secret_key: str = ""
    yookassa_return_url: str = ""

    payment_server_host: str = "0.0.0.0"
    payment_server_port: int = 8080

    selection_15_duration: int = 15  # always free - see services/selection_15.py

    # Platform's cut of a paid booking, as a whole percent (0-100). The rest
    # is what's owed to the psychologist - see services/payouts.py. Never
    # applied to free bookings (they never generate a Payout row at all).
    #
    # IMPORTANT: 30 here is a PLACEHOLDER, not a confirmed business figure -
    # nothing in the project's requirements has stated an agreed commission
    # percentage. Override it via the PLATFORM_COMMISSION_PERCENT env var
    # (see .env.example) once the business owner decides the real number;
    # do not treat this default as authoritative. Each Payout row stores
    # the percent that was actually used at the time it was created, so
    # changing this later never rewrites historical payouts.
    platform_commission_percent: int = 30

    # Reminder windows: minutes-before-start during which each reminder is
    # allowed to fire (a 1-minute cron tick can otherwise miss the exact
    # minute, or double-fire near a boundary - see services/reminders.py).
    reminder_1h_min: int = 55
    reminder_1h_max: int = 65
    reminder_10m_min: int = 7
    reminder_10m_max: int = 12

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def admin_id_list(self) -> list[int]:
        if not self.admin_ids:
            return []
        return [int(admin_id.strip()) for admin_id in self.admin_ids.split(",") if admin_id.strip()]


settings = Settings()
