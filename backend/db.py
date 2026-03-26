from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker


Base = declarative_base()


def create_session_factory(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args)
    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(database_url: str):
    engine, _ = create_session_factory(database_url)
    from models import EmailRecord  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return engine
