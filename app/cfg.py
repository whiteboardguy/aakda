import os
import sys

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from .utils.print_utils import printStat


if not os.getenv("LLM_API_KEY"):
    printStat("o", "Environment variables are not loaded. Loading from the env file.")
    try:
        load_dotenv()
        printStat("o", "Successfully loaded environment variables from the env file.")
    except Exception as e:
        printStat("c", "Problem loading environment variables from the env file.")
        printStat("c", str(e))
        sys.exit(1)


def _req(key: str) -> str:
    """Return env var value, or print a CRITICAL error and exit if not set."""
    val = os.getenv(key)
    if val is None:
        printStat(
            "c", f"Required environment variable '{key}' is not set. Cannot start."
        )
        sys.exit(1)
    return val


def _req_int(key: str, default: int | None = None) -> int:
    """Return int env var value, use default if absent, or exit on bad value."""
    val = os.getenv(key)
    if val is None:
        if default is not None:
            return default
        printStat(
            "c", f"Required environment variable '{key}' is not set. Cannot start."
        )
        sys.exit(1)
    try:
        return int(val)
    except ValueError:
        printStat(
            "c",
            f"Environment variable '{key}' must be an integer, got {val!r}. Cannot start.",
        )
        sys.exit(1)


class Settings(BaseSettings):
    # AI
    llm_base_url: str = _req("LLM_BASE_URL")
    llm_api_key: str = _req("LLM_API_KEY")
    llm_model_id: str = _req("LLM_MODEL")

    # TOOLS
    tools_jina_api: str = _req("JINA_API_KEY")
    tools_iteration_count: int = _req_int("ITERATIONS", default=8)

    # DATABASE
    database_hostname: str = _req("DATABASE_HOSTNAME")
    database_port: int = _req_int("DATABASE_PORT")
    database_password: str = _req("DATABASE_PASSWORD")
    database_name: str = _req("DATABASE_NAME")
    database_username: str = _req("DATABASE_USERNAME")

    # SECURITY
    security_session_secret: str = _req("SECURITY_SESSION_SECRET")

    # MISC
    aakda_url: str = _req("INSTANCE_URL")
    aakda_host: str = _req("INSTANCE_HOST")
    aakda_port: int = _req_int("INSTANCE_PORT", default=5000)
    # OPTS
    opts_autoverify: bool = os.getenv("OPTIONS_AUTOVERIFY", "").lower() in (
        "1",
        "true",
        "yes",
    )
    opts_delete_after: int = _req_int("OPTIONS_PERMADELETE_WAIT_DAYS", default=-1)
    opts_workers: int = max(1, _req_int("OPTIONS_WORKERS", default=1))

    # DEV
    DEBUG: bool = os.getenv("DEBUG", "").lower() in ("1", "true", "yes")


try:
    settings = Settings()
except Exception as e:
    printStat("c", "Error initialising the configuration settings.")
    printStat("c", str(e))
    sys.exit(1)
