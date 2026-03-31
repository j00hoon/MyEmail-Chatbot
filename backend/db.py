from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker


Base = declarative_base()


def create_session_factory(database_url: str):
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {
            "check_same_thread": False,
            "timeout": 30,
        }

    engine = create_engine(database_url, connect_args=connect_args)

    if database_url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA synchronous=NORMAL;")
            cursor.execute("PRAGMA busy_timeout=30000;")
            cursor.close()

    return engine, sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db(database_url: str):
    engine, _ = create_session_factory(database_url)
    from models import EmailRecord, SyncMeta  # noqa: F401

    Base.metadata.create_all(bind=engine)
    return engine
