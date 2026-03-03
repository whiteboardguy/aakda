from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from ..cfg import settings
from .print_utils import printStat


try:
    DB_URL: str = f"postgresql+psycopg2://{settings.database_username}:{settings.database_password}@{settings.database_hostname}:{settings.database_port}/{settings.database_name}"
    DB_URL_SAFE: str = f"postgresql+psycopg2://***:***@{settings.database_hostname}:{settings.database_port}/{settings.database_name}"
except Exception as e:
    printStat("c", "Database URL is invalid or doesn't exist.")
    printStat("c", str(e))
    DB_URL = ""
    DB_URL_SAFE = ""


printStat("o", f"Database URL ==> {DB_URL_SAFE}")
printStat("o", "Attempting to create database engine.")

try:
    engine = create_engine(DB_URL)
    printStat("o", f"Successfully created database engine for ==> {DB_URL_SAFE}")
    printStat("o", f"Database engine ==> {engine}")
except Exception as e:
    printStat("c", "Failed to create the database engine.")
    printStat("c", str(e))
    engine = None


class Base(DeclarativeBase):
    pass


def get_db():
    with Session(engine) as db_session:
        yield db_session
