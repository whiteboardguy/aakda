import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

from .utils.print_utils import printStat


if not os.getenv("LLM_API_KEY"):
    printStat("o", "Environment variables are not loaded. Loading from the env file.")
    try:
        load_dotenv()
        printStat("o", "Successfully loading environment variables from the env file.")
    except Exception as e:
        printStat("c", "Problem loading environment variables from the env file.")
        printStat("c", str(e))


class Settings(BaseSettings):
    # AI
    llm_base_url: str = str(os.getenv("LLM_BASE_URL"))
    llm_api_key: str = str(os.getenv("LLM_API_KEY"))
    llm_model_id: str = str(os.getenv("LLM_MODEL"))

    # TOOLS
    tools_jina_api: str = str(os.getenv("JINA_API_KEY"))
    tools_iteration_count: int = int(str((os.getenv("ITERATIONS"))))

    # DATABASE
    database_hostname: str = str(os.getenv("DATABASE_HOSTNAME"))
    database_port: int = int(str(os.getenv("DATABASE_PORT")))
    database_password: str = str(os.getenv("DATABASE_PASSWORD"))
    database_name: str = str(os.getenv("DATABASE_NAME"))
    database_username: str = str(os.getenv("DATABASE_USERNAME"))

    # SECURITY
    security_session_secret: str = str(os.getenv("SECURITY_SESSION_SECRET"))

    # MISC
    aakda_url: str = str(os.getenv("INSTANCE_URL"))
    aakda_host: str = str(os.getenv("INSTANCE_HOST"))
    aakda_port: int = int(str(os.getenv("INSTANCE_PORT", 5000)))
    aakda_version: str = str(os.getenv("INSTANCE_VER"))

    # OPTS
    opts_autoverify: bool = bool(os.getenv("OPTIONS_AUTOVERIFY", False))

    # --- #

    # DEV
    DEBUG: bool = bool(os.getenv("DEBUG", False))


try:
    settings = Settings()
except Exception as e:
    printStat("c", "Error initialising the configuration settings.")
    printStat("c", str(e))
