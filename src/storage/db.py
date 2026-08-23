import hashlib
from pathlib import Path
from typing import Union

import duckdb

DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "data" / "thesis-ledger.duckdb"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def get_connection(db_path: Union[Path, str] = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def migrate(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR PRIMARY KEY,
            checksum VARCHAR NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = sql_file.read_text()
        checksum = hashlib.sha256(sql.encode()).hexdigest()
        existing = con.execute(
            "SELECT checksum FROM schema_migrations WHERE version = ?",
            [sql_file.name],
        ).fetchone()
        if existing:
            if existing[0] != checksum:
                raise RuntimeError(
                    f"applied migration {sql_file.name} was modified; add a new migration instead"
                )
            continue
        con.execute("BEGIN TRANSACTION")
        try:
            con.execute(sql)
            con.execute(
                "INSERT INTO schema_migrations (version, checksum) VALUES (?, ?)",
                [sql_file.name, checksum],
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
