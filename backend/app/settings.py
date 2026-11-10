"""Settings for the ai-agents control plane (OIDC BFF + service keys)."""

from __future__ import annotations

import os
import ssl
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../docker/.env", "../docker/.env.secrets"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="ai-agents", alias="APP_NAME")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    backend_port: int = Field(default=8080, alias="BACKEND_PORT")
    public_url: str = Field(default="https://ai-agents-dev.example.com", alias="PUBLIC_URL")

    # PostgreSQL lives on the Docker host (not in Compose). Alembic creates the DB if missing.
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/ai_agents",
        alias="DATABASE_URL",
    )

    # One or more bootstrap service keys (comma/space/semicolon separated). Full access.
    service_api_keys: str = Field(default="", alias="SERVICE_API_KEYS")

    # Keycloak OIDC (BFF, cookie session).
    keycloak_issuer_override: str | None = Field(default=None, alias="KEYCLOAK_ISSUER")
    keycloak_realm: str = Field(default="ai-agents", alias="KEYCLOAK_REALM")
    keycloak_client_id: str = Field(default="ai-agents", alias="KEYCLOAK_CLIENT_ID")
    keycloak_client_secret: str = Field(default="", alias="KEYCLOAK_CLIENT_SECRET")
    keycloak_redirect_uri: str | None = Field(default=None, alias="KEYCLOAK_REDIRECT_URI")
    keycloak_ca_bundle: str | None = Field(default=None, alias="KEYCLOAK_CA_BUNDLE")
    keycloak_ssl_verify_override: bool | None = Field(default=None, alias="KEYCLOAK_SSL_VERIFY")
    keycloak_public_url_override: str | None = Field(
        default="https://keycloak.example.com", alias="KEYCLOAK_PUBLIC_URL"
    )
    admin_roles: str = Field(default="ai-agents-admin", alias="ADMIN_ROLES")
    # Отдельный клиент Keycloak с правом realm-management view-users (по умолчанию — основной).
    keycloak_admin_client_id: str = Field(default="", alias="DIRECTORY_ADMIN_CLIENT_ID")
    keycloak_admin_client_secret: str = Field(
        default="", alias="DIRECTORY_ADMIN_CLIENT_SECRET"
    )
    # Аккаунты, которые всегда суперадмины (bootstrap), независимо от realm-ролей.
    superadmin_emails: str = Field(
        default="admin@example.com", alias="SUPERADMIN_EMAILS"
    )

    # BFF session cookie (signed with itsdangerous).
    session_secret_key: str = Field(default="dev-only-change-me", alias="SESSION_SECRET_KEY")
    session_cookie_name: str = Field(default="ai_agents_session", alias="SESSION_COOKIE_NAME")
    session_cookie_secure: bool = Field(default=False, alias="SESSION_COOKIE_SECURE")
    session_ttl_hours: int = Field(default=8, alias="SESSION_TTL_HOURS")
    session_salt: str = "ai-agents-session"

    # Default OpenAI-compatible LLM; a run may override per request.
    default_llm_base_url: str = Field(
        default="http://host.docker.internal:1234/v1", alias="DEFAULT_LLM_BASE_URL"
    )
    default_llm_model: str = Field(default="local-model", alias="DEFAULT_LLM_MODEL")
    default_llm_api_key: str = Field(default="not-needed", alias="DEFAULT_LLM_API_KEY")

    # Tool/skill integrations.
    github_token: str = Field(default="", alias="GITHUB_TOKEN")
    skills_sh_token: str = Field(default="", alias="SKILLS_SH_TOKEN")
    # Local skill import: path must resolve under one of these roots (comma-separated).
    # Empty → STORAGE_PATH only. Entries upload (browser) ignores this.
    storage_path: str = Field(default="/data", alias="STORAGE_PATH")
    log_dir: str = Field(default="logs", alias="LOG_DIR")
    skills_import_roots: str = Field(default="", alias="SKILLS_IMPORT_ROOTS")

    # Langfuse tracing (optional).
    langfuse_host: str = Field(default="", alias="LANGFUSE_HOST")
    langfuse_public_key: str = Field(default="", alias="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", alias="LANGFUSE_SECRET_KEY")

    # Runtime limits.
    run_timeout_seconds: float = Field(default=120.0, alias="RUN_TIMEOUT_SECONDS")
    max_steps: int = Field(default=8, alias="MAX_STEPS")
    max_steps_cap: int = Field(default=32, alias="MAX_STEPS_CAP")
    run_timeout_cap_seconds: float = Field(default=600.0, alias="RUN_TIMEOUT_CAP_SECONDS")
    run_token_budget: int = Field(default=200_000, ge=1, alias="RUN_TOKEN_BUDGET")
    run_token_cap: int = Field(default=2_000_000, ge=1, alias="RUN_TOKEN_CAP")
    run_max_attempts: int = Field(default=2, ge=1, alias="RUN_MAX_ATTEMPTS")
    run_max_attempts_cap: int = Field(default=5, ge=1, alias="RUN_MAX_ATTEMPTS_CAP")
    run_retry_backoff_seconds: float = Field(
        default=1.0, ge=0, alias="RUN_RETRY_BACKOFF_SECONDS"
    )
    run_retry_backoff_max_seconds: float = Field(
        default=8.0, ge=0, alias="RUN_RETRY_BACKOFF_MAX_SECONDS"
    )
    run_fallback_model: str = Field(default="", alias="RUN_FALLBACK_MODEL")
    run_approval_mode: str = Field(default="mutating", alias="RUN_APPROVAL_MODE")
    run_approval_timeout_seconds: float = Field(
        default=60.0, ge=1, alias="RUN_APPROVAL_TIMEOUT_SECONDS"
    )
    run_context_max_tokens: int = Field(
        default=24_000, ge=1, alias="RUN_CONTEXT_MAX_TOKENS"
    )
    run_tool_output_max_chars: int = Field(
        default=8_000, ge=1, alias="RUN_TOOL_OUTPUT_MAX_CHARS"
    )
    run_schedule_poll_seconds: int = Field(
        default=30, ge=5, alias="RUN_SCHEDULE_POLL_SECONDS"
    )
    run_schedule_max_per_tick: int = Field(
        default=10, ge=1, alias="RUN_SCHEDULE_MAX_PER_TICK"
    )
    run_max_subrun_depth: int = Field(default=2, ge=0, alias="RUN_MAX_SUBRUN_DEPTH")
    run_max_subruns_per_run: int = Field(
        default=5, ge=1, alias="RUN_MAX_SUBRUNS_PER_RUN"
    )
    run_scheduler_enabled: bool = Field(
        default=True, alias="RUN_SCHEDULER_ENABLED"
    )
    run_delivery_max_attempts: int = Field(
        default=5, ge=1, alias="RUN_DELIVERY_MAX_ATTEMPTS"
    )
    run_delivery_poll_seconds: int = Field(
        default=10, ge=1, alias="RUN_DELIVERY_POLL_SECONDS"
    )
    run_delivery_enabled: bool = Field(
        default=True, alias="RUN_DELIVERY_ENABLED"
    )
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")

    # Bounded execution: in-process gate (single backend replica) + queued row cap.
    run_max_concurrency: int = Field(default=4, ge=1, alias="RUN_MAX_CONCURRENCY")
    run_max_concurrency_per_agent: int = Field(
        default=2, ge=1, alias="RUN_MAX_CONCURRENCY_PER_AGENT"
    )
    run_max_queued: int = Field(default=50, ge=1, alias="RUN_MAX_QUEUED")

    # Event retention: 0 disables pruning; digest/run rows are kept.
    run_events_retention_days: int = Field(
        default=30, ge=0, alias="RUN_EVENTS_RETENTION_DAYS"
    )
    run_retention_interval_seconds: int = Field(
        default=21600, ge=60, alias="RUN_RETENTION_INTERVAL_SECONDS"
    )

    # MCP Streamable HTTP DNS-rebinding allowlist extras (comma/space).
    # Always includes PUBLIC_URL host + localhost/127.0.0.1 + Docker Desktop aliases.
    mcp_allowed_hosts_extra: str = Field(default="", alias="MCP_ALLOWED_HOSTS")

    # MCP egress allowlist (comma/semicolon): host, *.suffix, IP/CIDR, which may be
    # private. Applies ONLY to MCP connections; custom tools stay public-only.
    mcp_egress_allowed_hosts: str = Field(default="", alias="MCP_EGRESS_ALLOWED_HOSTS")

    # Role "user": runs per UTC day (0 = unlimited). Per-user override lives in user_identities.
    user_daily_run_limit: int = Field(default=20, ge=0, alias="USER_DAILY_RUN_LIMIT")
    user_daily_token_limit: int = Field(default=0, ge=0, alias="USER_DAILY_TOKEN_LIMIT")

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.keycloak_client_id and self.keycloak_client_secret)

    @property
    def keycloak_issuer(self) -> str:
        if self.keycloak_issuer_override:
            return self.keycloak_issuer_override.rstrip("/")
        return f"{self.keycloak_public_url}/realms/{self.keycloak_realm}"

    @property
    def keycloak_public_url(self) -> str:
        return (self.keycloak_public_url_override or "").rstrip("/")

    @property
    def keycloak_redirect(self) -> str:
        return self.keycloak_redirect_uri or f"{self.public_url.rstrip('/')}/auth/callback"

    @property
    def keycloak_ssl_context(self) -> bool | ssl.SSLContext | str:
        """httpx verify=: KEYCLOAK_SSL_VERIFY=false wins, then CA path, then system default."""
        if self.keycloak_ssl_verify_override is False:
            return False
        bundle = (self.keycloak_ca_bundle or "").strip()
        if bundle:
            return bundle
        return True

    @property
    def superadmin_email_set(self) -> set[str]:
        raw = self.superadmin_emails.replace(";", ",").replace("\n", ",")
        parts = raw.replace(",", " ").split()
        return {part.strip().lower() for part in parts if part.strip()}

    @property
    def admin_role_set(self) -> set[str]:
        return {part for part in self.admin_roles.replace(",", " ").split() if part}

    @property
    def langfuse_enabled(self) -> bool:
        return bool(
            self.langfuse_host.strip()
            and self.langfuse_public_key.strip()
            and self.langfuse_secret_key.strip()
        )

    @property
    def service_key_set(self) -> set[str]:
        raw = self.service_api_keys.replace(";", ",").replace("\n", ",")
        keys: set[str] = set()
        for part in raw.split(","):
            for key in part.split():
                key = key.strip()
                if key:
                    keys.add(key)
        return keys

    @property
    def skills_import_root_list(self) -> list[str]:
        """Allowed roots for server-path skill import (absolute paths)."""
        raw = self.skills_import_roots.replace(";", ",").replace("\n", ",")
        roots = [part.strip() for part in raw.split(",") if part.strip()]
        if roots:
            return roots
        storage = (self.storage_path or "").strip()
        return [storage] if storage else []

    @property
    def mcp_allowed_hosts(self) -> list[str]:
        """Host values accepted by MCP transport security (no client Host forging)."""
        from urllib.parse import urlsplit

        host = (urlsplit(self.public_url).hostname or "localhost").strip().lower()
        hosts: list[str] = [
            host,
            f"{host}:*",
            "localhost",
            "localhost:*",
            "127.0.0.1",
            "127.0.0.1:*",
            # ai-agents lab Compose: peer containers call published :8096 via Docker DNS.
            "host.docker.internal",
            "host.docker.internal:*",
            "gateway.docker.internal",
            "gateway.docker.internal:*",
        ]
        raw = self.mcp_allowed_hosts_extra.replace(";", ",").replace("\n", ",")
        for part in raw.replace(",", " ").split():
            value = part.strip().lower()
            if value and value not in hosts:
                hosts.append(value)
        return hosts

    @property
    def mcp_egress_allowlist(self) -> tuple[str, ...]:
        """Private MCP targets explicitly allowed outbound (host, *.suffix, IP/CIDR)."""
        raw = self.mcp_egress_allowed_hosts.replace(";", ",").replace("\n", ",")
        return tuple(
            part.strip().lower() for part in raw.replace(",", " ").split() if part.strip()
        )


_WEAK_SESSION_SECRETS = frozenset({"", "dev-only-change-me", "change-me", "secret"})


def _assert_session_secret(settings: Settings) -> None:
    """Prod/staging must not boot with the lab placeholder session secret."""
    env = (settings.environment or "").strip().lower()
    if env in {"", "development", "dev", "test", "local", "lab"}:
        return
    secret = (settings.session_secret_key or "").strip()
    if secret.lower() in _WEAK_SESSION_SECRETS or len(secret) < 16:
        raise RuntimeError(
            "SESSION_SECRET_KEY is missing or weak for ENVIRONMENT="
            f"{settings.environment!r}; set a strong secret in .env.secrets / SOPS"
        )


@lru_cache
def get_settings() -> Settings:
    # SETTINGS_ENV_FILE="" отключает чтение .env-файлов (тесты не должны видеть
    # локальные docker/.env.secrets); путь в переменной переопределяет список.
    env_file = os.environ.get("SETTINGS_ENV_FILE")
    if env_file == "":
        settings = Settings(_env_file=None)
    elif env_file:
        settings = Settings(_env_file=env_file)
    else:
        settings = Settings()
    _assert_session_secret(settings)
    return settings
