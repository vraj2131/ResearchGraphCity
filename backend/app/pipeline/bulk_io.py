from __future__ import annotations

from collections.abc import Iterable

from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy import text
from sqlalchemy.engine import Connection


PAPER_COLUMNS = (
    "openalex_id",
    "doi",
    "title",
    "abstract",
    "publication_year",
    "venue",
    "publisher",
    "citation_count",
    "open_access",
    "code_available",
    "data_available",
    "authors",
    "author_ids",
    "institutions",
    "institution_ids",
    "topics",
    "keywords",
    "methods",
    "datasets",
    "metadata",
)
JSON_COLUMNS = {
    "authors",
    "author_ids",
    "institutions",
    "institution_ids",
    "topics",
    "keywords",
    "methods",
    "datasets",
    "metadata",
}
PAPER_DEFAULTS = {
    "abstract": "",
    "venue": "",
    "publisher": "",
    "citation_count": 0,
    "open_access": False,
    "code_available": False,
    "data_available": False,
    "authors": [],
    "author_ids": [],
    "institutions": [],
    "institution_ids": [],
    "topics": [],
    "keywords": [],
    "methods": [],
    "datasets": [],
    "metadata": {},
}


def copy_rows(
    connection: Connection,
    table: str,
    columns: tuple[str, ...],
    rows: Iterable[tuple],
) -> int:
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table),
        sql.SQL(", ").join(sql.Identifier(column) for column in columns),
    )
    copied = 0
    driver_connection = connection.connection.driver_connection
    with driver_connection.cursor() as cursor:
        with cursor.copy(statement) as copy:
            for row in rows:
                copy.write_row(row)
                copied += 1
    return copied


def upsert_paper_rows(connection: Connection, rows: Iterable[dict]) -> int:
    prepared = []
    for row in rows:
        values = []
        for column in PAPER_COLUMNS:
            value = row.get(column)
            if value is None and column in PAPER_DEFAULTS:
                value = PAPER_DEFAULTS[column]
            values.append(Jsonb(value) if column in JSON_COLUMNS else value)
        prepared.append(tuple(values))
    if not prepared:
        return 0
    connection.execute(text("CREATE TEMP TABLE paper_stage (LIKE papers INCLUDING DEFAULTS) ON COMMIT DROP"))
    copy_rows(connection, "paper_stage", PAPER_COLUMNS, prepared)
    assignments = ", ".join(
        f'{column} = EXCLUDED.{column}'
        for column in PAPER_COLUMNS
        if column not in {"openalex_id"}
    )
    columns = ", ".join(PAPER_COLUMNS)
    connection.execute(
        text(
            f"""
            INSERT INTO papers ({columns})
            SELECT {columns} FROM paper_stage
            ON CONFLICT (openalex_id) DO UPDATE SET {assignments}
            """
        )
    )
    return len(prepared)
