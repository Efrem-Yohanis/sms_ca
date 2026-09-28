"""Generate audience_source and language_reference data for local testing."""

import argparse
import os
import sqlite3
from pathlib import Path


LANGUAGES = ("en", "am", "ti", "om", "so")


def generate_rows(start_number, count):
    for offset in range(count):
        msisdn = f"+251{start_number + offset:09d}"
        language = LANGUAGES[offset % len(LANGUAGES)]
        yield msisdn, language


def generate_data(
    connection,
    backend,
    count,
    batch_size,
    start_number,
    replace,
    source_table,
    source_msisdn_column,
    source_language_column,
    reference_table,
    reference_msisdn_column,
    reference_language_column,
):
    placeholder = "%s" if backend == "postgres" else "?"

    with connection:
        cursor = connection.cursor()
        if backend == "sqlite":
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS audience_source (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    msisdn TEXT NOT NULL UNIQUE
                );

                CREATE TABLE IF NOT EXISTS language_reference (
                    msisdn TEXT PRIMARY KEY,
                    language TEXT NOT NULL
                );
                """
            )

        if replace:
            cursor.execute(f'DELETE FROM "{source_table}"')
            cursor.execute(f'DELETE FROM "{reference_table}"')

        rows_written = 0
        rows = generate_rows(start_number, count)
        while True:
            batch = list(next_batch(rows, batch_size))
            if not batch:
                break

            cursor.executemany(
                f'INSERT INTO "{source_table}" ("{source_msisdn_column}"'
                f', "{source_language_column}") VALUES ({placeholder}, {placeholder})',
                batch,
            )
            cursor.executemany(
                f'INSERT INTO "{reference_table}" '
                f'("{reference_msisdn_column}", "{reference_language_column}") '
                f"VALUES ({placeholder}, {placeholder}) "
                f'ON CONFLICT ("{reference_msisdn_column}") DO UPDATE '
                f'SET "{reference_language_column}" = EXCLUDED."{reference_language_column}"',
                batch,
            )
            rows_written += len(batch)
            print(f"Inserted {rows_written:,}/{count:,} rows", flush=True)

        cursor.close()

    return rows_written


def next_batch(rows, batch_size):
    for _ in range(batch_size):
        try:
            yield next(rows)
        except StopIteration:
            return


def open_connection(args):
    if args.backend == "sqlite":
        database_path = Path(args.db)
        database_path.parent.mkdir(parents=True, exist_ok=True)
        return sqlite3.connect(database_path), str(database_path)

    try:
        import psycopg2
    except ImportError as error:
        raise SystemExit(
            "PostgreSQL support requires psycopg2-binary. "
            "Install it with: pip install psycopg2-binary"
        ) from error

    connection = psycopg2.connect(
        host=args.host,
        port=args.port,
        dbname=args.database,
        user=args.user,
        password=args.password,
    )
    return connection, f"{args.host}:{args.port}/{args.database}"


def print_postgres_schema(connection):
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name, column_name, data_type
                , is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position
            """
        )
        for table_name, column_name, data_type, is_nullable, column_default in cursor.fetchall():
            print(
                f"{table_name}.{column_name} ({data_type}, "
                f"nullable={is_nullable}, default={column_default})"
            )
        cursor.execute(
            """
            SELECT tc.table_name, kcu.column_name, tc.constraint_type
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.table_name IN ('audience_source', 'language_reference')
              AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
            ORDER BY tc.table_name, kcu.column_name
            """
        )
        for table_name, column_name, constraint_type in cursor.fetchall():
            print(f"constraint: {table_name}.{column_name} ({constraint_type})")


def add_database_arguments(parser):
    parser.add_argument(
        "--backend",
        choices=("sqlite", "postgres"),
        default="sqlite",
        help="Database backend (default: sqlite)",
    )
    parser.add_argument(
        "--db",
        default="audience_source.sqlite3",
        help="SQLite database path (default: audience_source.sqlite3)",
    )
    parser.add_argument("--host", default=os.getenv("PGHOST", "localhost"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PGPORT", "5432")))
    parser.add_argument("--database", default=os.getenv("PGDATABASE", "postgres"))
    parser.add_argument("--user", default=os.getenv("PGUSER", "postgres"))
    parser.add_argument("--password", default=os.getenv("PGPASSWORD"))
    parser.add_argument("--source-table", default="audience_source")
    parser.add_argument("--source-msisdn-column", default="phone_number")
    parser.add_argument("--source-language-column", default="preferred_lang")
    parser.add_argument("--reference-table", default="language_reference")
    parser.add_argument("--reference-msisdn-column", default="msisdn")
    parser.add_argument("--reference-language-column", default="language")
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Print PostgreSQL public tables and columns, then exit",
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate matching audience_source and language_reference rows."
    )
    add_database_arguments(parser)
    parser.add_argument(
        "--count",
        type=int,
        default=10_000_000,
        help="Number of records to generate (default: 10,000,000)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
        help="Rows inserted per batch (default: 10,000)",
    )
    parser.add_argument(
        "--start-number",
        type=int,
        default=700_000_000,
        help="First nine-digit subscriber number (default: 700000000)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Delete existing rows before inserting generated data",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.backend == "postgres" and not all((args.database, args.user, args.password)):
        raise SystemExit(
            "PostgreSQL requires --database, --user, and --password "
            "or PGDATABASE, PGUSER, and PGPASSWORD."
        )
    if args.count < 1:
        raise SystemExit("--count must be greater than zero")
    if args.batch_size < 1:
        raise SystemExit("--batch-size must be greater than zero")
    if not 0 <= args.start_number <= 999_999_999:
        raise SystemExit("--start-number must fit in nine digits")
    if args.start_number + args.count - 1 > 999_999_999:
        raise SystemExit("count exceeds the available nine-digit number range")

    connection, database_label = open_connection(args)
    try:
        if args.inspect:
            print_postgres_schema(connection)
            return
        rows_written = generate_data(
            connection=connection,
            backend=args.backend,
            count=args.count,
            batch_size=args.batch_size,
            start_number=args.start_number,
            replace=args.replace,
            source_table=args.source_table,
            source_msisdn_column=args.source_msisdn_column,
            source_language_column=args.source_language_column,
            reference_table=args.reference_table,
            reference_msisdn_column=args.reference_msisdn_column,
            reference_language_column=args.reference_language_column,
        )
    finally:
        connection.close()
    print(f"Done. Wrote {rows_written:,} rows to {database_label}")


if __name__ == "__main__":
    main()