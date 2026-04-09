import json

from sqlalchemy import create_engine, event, inspect, text
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
    from models import EmailRecord, GmailAccount, SyncMeta  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _run_post_create_migrations(engine, database_url)
    return engine


def _run_post_create_migrations(engine, database_url: str):
    if not database_url.startswith("sqlite"):
        return

    inspector = inspect(engine)
    email_columns = {column["name"] for column in inspector.get_columns("emails")}
    sync_meta_columns = {column["name"] for column in inspector.get_columns("sync_meta")}

    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS gmail_accounts (
                id INTEGER PRIMARY KEY,
                account_id TEXT NOT NULL UNIQUE,
                email_address TEXT,
                display_name TEXT,
                token_path TEXT NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT 0,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_gmail_accounts_email_address ON gmail_accounts (email_address)"
        )

        if "account_id" not in email_columns:
            connection.exec_driver_sql("DROP TABLE IF EXISTS emails_legacy_backup")
            connection.exec_driver_sql("ALTER TABLE emails RENAME TO emails_legacy_backup")
            connection.exec_driver_sql(
                """
                CREATE TABLE emails (
                    id INTEGER PRIMARY KEY,
                    account_id TEXT NOT NULL DEFAULT 'local_default',
                    gmail_message_id TEXT NOT NULL,
                    thread_id TEXT,
                    subject TEXT NOT NULL DEFAULT '',
                    sender TEXT,
                    recipients TEXT,
                    sent_at TEXT,
                    gmail_category TEXT,
                    snippet TEXT,
                    body_text TEXT,
                    attachment_names TEXT,
                    raw_payload TEXT,
                    indexed_at DATETIME,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO emails (
                    id, account_id, gmail_message_id, thread_id, subject, sender, recipients, sent_at,
                    gmail_category, snippet, body_text, attachment_names, raw_payload, indexed_at, created_at, updated_at
                )
                SELECT
                    id, 'local_default', gmail_message_id, thread_id, subject, sender, recipients, sent_at,
                    gmail_category, snippet, body_text, attachment_names, raw_payload, indexed_at, created_at, updated_at
                FROM emails_legacy_backup
                """
            )
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_emails_account_id ON emails (account_id)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_emails_gmail_message_id ON emails (gmail_message_id)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_emails_gmail_category ON emails (gmail_category)")
            connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_emails_account_message ON emails (account_id, gmail_message_id)")
        else:
            if "gmail_category" not in email_columns:
                connection.execute(text("ALTER TABLE emails ADD COLUMN gmail_category TEXT"))
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_emails_account_id ON emails (account_id)")
            connection.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_emails_gmail_category ON emails (gmail_category)")
            connection.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_emails_account_message ON emails (account_id, gmail_message_id)")

        if "id" not in sync_meta_columns:
            connection.exec_driver_sql("DROP TABLE IF EXISTS sync_meta_legacy_backup")
            connection.exec_driver_sql("ALTER TABLE sync_meta RENAME TO sync_meta_legacy_backup")
            connection.exec_driver_sql(
                """
                CREATE TABLE sync_meta (
                    id INTEGER PRIMARY KEY,
                    account_id TEXT NOT NULL DEFAULT 'local_default',
                    key TEXT NOT NULL,
                    value TEXT,
                    last_synced_at DATETIME,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.exec_driver_sql(
                """
                INSERT INTO sync_meta (account_id, key, value, last_synced_at, updated_at)
                SELECT 'local_default', key, value, last_synced_at, updated_at
                FROM sync_meta_legacy_backup
                """
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_meta_account_key ON sync_meta (account_id, key)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_sync_meta_account_id ON sync_meta (account_id)"
            )
        else:
            if "account_id" not in sync_meta_columns:
                connection.execute(
                    text("ALTER TABLE sync_meta ADD COLUMN account_id TEXT NOT NULL DEFAULT 'local_default'")
                )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_sync_meta_account_key ON sync_meta (account_id, key)"
            )
            connection.exec_driver_sql(
                "CREATE INDEX IF NOT EXISTS ix_sync_meta_account_id ON sync_meta (account_id)"
            )

        connection.exec_driver_sql(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts
            USING fts5(
                subject,
                sender,
                recipients,
                snippet,
                body_text,
                attachment_names,
                content='emails',
                content_rowid='id',
                tokenize='porter unicode61'
            )
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS emails_ai AFTER INSERT ON emails BEGIN
              INSERT INTO emails_fts(rowid, subject, sender, recipients, snippet, body_text, attachment_names)
              VALUES (new.id, new.subject, new.sender, new.recipients, new.snippet, new.body_text, new.attachment_names);
            END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS emails_ad AFTER DELETE ON emails BEGIN
              INSERT INTO emails_fts(emails_fts, rowid, subject, sender, recipients, snippet, body_text, attachment_names)
              VALUES ('delete', old.id, old.subject, old.sender, old.recipients, old.snippet, old.body_text, old.attachment_names);
            END
            """
        )
        connection.exec_driver_sql(
            """
            CREATE TRIGGER IF NOT EXISTS emails_au AFTER UPDATE ON emails BEGIN
              INSERT INTO emails_fts(emails_fts, rowid, subject, sender, recipients, snippet, body_text, attachment_names)
              VALUES ('delete', old.id, old.subject, old.sender, old.recipients, old.snippet, old.body_text, old.attachment_names);
              INSERT INTO emails_fts(rowid, subject, sender, recipients, snippet, body_text, attachment_names)
              VALUES (new.id, new.subject, new.sender, new.recipients, new.snippet, new.body_text, new.attachment_names);
            END
            """
        )
        connection.exec_driver_sql("INSERT INTO emails_fts(emails_fts) VALUES ('rebuild')")

        connection.exec_driver_sql(
            "INSERT OR IGNORE INTO gmail_accounts (account_id, token_path, is_active) VALUES ('local_default', 'token.json', 1)"
        )

        rows = connection.execute(
            text(
                "SELECT id, raw_payload FROM emails "
                "WHERE (gmail_category IS NULL OR gmail_category = '') "
                "AND raw_payload IS NOT NULL AND raw_payload != ''"
            )
        ).fetchall()

        for row in rows:
            gmail_category = _category_from_raw_payload(row.raw_payload)
            if gmail_category is None:
                continue
            connection.execute(
                text("UPDATE emails SET gmail_category = :gmail_category WHERE id = :email_id"),
                {"gmail_category": gmail_category, "email_id": row.id},
            )


def _category_from_raw_payload(raw_payload: str):
    try:
        payload = json.loads(raw_payload)
    except json.JSONDecodeError:
        return None

    label_ids = payload.get("labelIds", [])
    if not isinstance(label_ids, list):
        return None

    label_map = {
        "CATEGORY_PERSONAL": "primary",
        "CATEGORY_PROMOTIONS": "promotions",
        "CATEGORY_SOCIAL": "social",
        "CATEGORY_UPDATES": "updates",
        "CATEGORY_FORUMS": "forums",
    }
    for label_id in label_ids:
        mapped = label_map.get(str(label_id))
        if mapped:
            return mapped
    return "uncategorized"
