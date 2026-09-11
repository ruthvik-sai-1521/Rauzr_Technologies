"""
Centralized application configuration.

All values are sourced from environment variables so the same image can be
promoted from local -> staging -> Railway -> any other cloud without code
changes (12-factor config).
"""
from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "Rauzr Technologies API"
    ENV: str = "development"  # development | staging | production
    DEBUG: bool = True

    # --- Database ---
    # Railway injects DATABASE_URL automatically when a Postgres plugin is
    # attached. Locally this defaults to a throwaway SQLite file so the repo
    # is runnable with zero external services.
    #
    # PERSISTENCE NOTE (see README "Login persistence -- root cause & fix"):
    # A container's filesystem is ephemeral -- anything written inside it,
    # including this SQLite file, is wiped on every rebuild/redeploy/restart
    # unless it lives on a volume that is mounted from *outside* the
    # container. That was the actual cause of "registered users can't log
    # back in after restarting the project": the previous default pointed at
    # a relative path with no volume behind it, so every restart handed the
    # app a brand new, empty `rauzr.db` -- the login endpoint was correct
    # the whole time, it was just correctly rejecting logins against a
    # database that no longer had the user in it.
    #
    # Fix, in order of preference:
    #   1. Production / anything that must survive restarts: attach Railway's
    #      managed Postgres plugin (or any Postgres) and set DATABASE_URL to
    #      it. This is enforced below via `require_persistent_database()`.
    #   2. Local Docker without Postgres: DATA_DIR is mounted as a named
    #      volume (see docker-compose.yml) and DATABASE_URL points inside it,
    #      so the file survives `docker compose restart` / container rebuilds.
    #   3. Bare `uvicorn` on a laptop: the relative-path SQLite default is
    #      fine -- there's no container filesystem to lose.
    # Keep the legacy filename so existing local accounts survive the brand
    # rename. Change this only with an explicit database migration.
    DATABASE_URL: str = "sqlite:///./veritant.db"

    # Directory a persistent volume should be mounted at in containerized
    # environments. Only used by the Dockerfile's default DATABASE_URL and
    # by docker-compose; irrelevant for bare local runs.
    DATA_DIR: str = "/app/data"

    # --- Auth / JWT ---
    # Login is OPTIONAL for the product itself (landing + demo booking never
    # require it) but is used to gate the authenticated workspace demo and
    # the internal admin view of bookings.
    JWT_SECRET_KEY: str = "CHANGE_ME_DEV_ONLY_INSECURE_SECRET"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h, fine for a demo product

    # --- CORS ---
    # Comma separated list of allowed origins, e.g.
    # "https://your-rauzr-frontend.example,https://rauzr.example"
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Set this to the public frontend URL on Railway. Keeping it separate
    # makes the deployed auth flow work even when CORS_ORIGINS is unchanged.
    FRONTEND_URL: str = ""

    # --- Rate limiting ---
    RATE_LIMIT_PER_MINUTE: int = 30

    # --- Email (optional; demo booking confirmation) ---
    # Left unconfigured in the OSS scaffold -- bookings are always persisted
    # to the DB regardless of whether email sending is enabled.
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "no-reply@rauzr.local"

    @property
    def cors_origin_list(self) -> List[str]:
        origins = [o.strip().rstrip("/") for o in self.CORS_ORIGINS.split(",") if o.strip()]
        frontend_url = self.FRONTEND_URL.strip().rstrip("/")
        if frontend_url and frontend_url not in origins:
            origins.append(frontend_url)
        return origins

    @property
    def is_production(self) -> bool:
        return self.ENV == "production"

    @property
    def is_railway(self) -> bool:
        """
        True whenever this process is actually running on Railway,
        regardless of whether the ENV variable was ever set on the
        dashboard. Railway injects RAILWAY_ENVIRONMENT_NAME (and several
        other RAILWAY_* vars) into every deployment automatically -- this
        does NOT depend on the user configuring anything.

        This exists because of a real bug found in this codebase: the
        original persistence guard only enforced its check when
        ENV=production was explicitly set. Nothing on Railway sets ENV for
        you, so a service deployed without ever touching that variable
        silently ran with ENV=development, the guard never fired, and the
        backend booted happily against an ephemeral SQLite file. Every
        redeploy/restart then wiped every registered user -- which looks
        exactly like "signup and login don't work on Railway" even though
        both endpoints are implemented correctly.
        """
        import os

        return any(
            os.environ.get(key)
            for key in ("RAILWAY_ENVIRONMENT_NAME", "RAILWAY_ENVIRONMENT", "RAILWAY_PROJECT_ID")
        )

    @property
    def uses_ephemeral_sqlite(self) -> bool:
        """
        True when DATABASE_URL is SQLite and not pointed at the mounted
        DATA_DIR -- i.e. the exact configuration that caused the original
        login-persistence bug. Used to fail fast instead of silently losing
        data again.
        """
        return self.DATABASE_URL.startswith("sqlite") and self.DATA_DIR not in self.DATABASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()


def require_persistent_database(settings: "Settings") -> None:
    """
    Startup guard against the login-persistence bug regressing. Raises on
    Railway or in any explicit `ENV=production` -- both are contexts where a
    silent data-loss bug is unacceptable and a loud, obvious deploy failure
    (visible in Railway's build/deploy logs) is far preferable to a backend
    that boots "successfully" and then quietly forgets every user on the
    next restart. Warns everywhere else (e.g. a bare local `uvicorn` run).
    """
    if not settings.uses_ephemeral_sqlite:
        return

    message = (
        "DATABASE_URL is a SQLite file that is NOT on the persistent "
        f"{settings.DATA_DIR} volume. Every restart/redeploy will silently "
        "erase all registered users, bookings, and pipeline runs "
        "(this was the original login-persistence bug). Attach a Postgres "
        "database (recommended: add the Postgres plugin in Railway, which "
        "injects DATABASE_URL automatically) or point DATABASE_URL inside "
        "a mounted volume -- see README: 'Login persistence -- root cause "
        "& fix'."
    )
    if settings.is_production or settings.is_railway:
        raise RuntimeError(message)
    import logging

    logging.getLogger("rauzr").warning(message)
