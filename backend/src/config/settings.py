"""集中配置：全部来自环境变量，默认值与 .env.example 保持一致。"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "jobmerge"
    app_title: str = "多渠道招聘岗位归并与薪资口径归一"
    # 发布口径规则版本：调高即让所有旧发布版本立即失效，待复核簇重新排队。
    review_rule_version: str = ""

    db_kind: str = "postgres"  # postgres | mysql
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "jobmerge"
    db_user: str = "jobmerge"
    db_password: str = "jobmerge_pw_2026"

    jwt_secret: str = "jobmerge-jwt-secret-change-me-2026"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 480

    redis_url: str = "redis://localhost:6379/0"
    seed_demo: bool = True
    rate_limit_per_minute: int = 300
    rate_limit_write_per_minute: int = 60
    app_timezone_offset_minutes: int = 480

    @property
    def database_url(self) -> str:
        if self.db_kind == "mysql":
            return (
                f"mysql+pymysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
            )
        return (
            f"postgresql+psycopg2://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
