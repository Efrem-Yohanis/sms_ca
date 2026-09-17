"""Connect to configured external databases and inspect their schema/data."""

import importlib
import re
import sqlite3
from contextlib import contextmanager


class ConnectionError(Exception):
    """Raised when a configured database cannot be accessed."""


class DatabaseConnector:
    DRIVER_REQUIREMENTS = {
        'postgresql': {'package': 'psycopg2-binary', 'module': 'psycopg2'},
        'mysql': {'package': 'mysqlclient', 'module': 'MySQLdb'},
        'mssql': {'package': 'pyodbc', 'module': 'pyodbc'},
        'oracle': {'package': 'oracledb', 'module': 'oracledb'},
    }

    def __init__(self, database_config):
        self.config = database_config

    def test_connection(self):
        try:
            with self._connect() as connection:
                cursor = connection.cursor()
                if self.config.database_type == 'sqlite':
                    cursor.execute('SELECT sqlite_version()')
                    version = cursor.fetchone()[0]
                else:
                    version = 'connected'
            return {'success': True, 'message': 'Connection successful.', 'details': {'server_version': version}}
        except Exception as error:
            return {'success': False, 'message': f'Connection failed: {error}', 'details': {}}

    def list_tables(self):
        db_type = (self.config.database_type or '').lower()
        if db_type == 'sqlite':
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
                return [row[0] for row in cursor.fetchall()]

        with self._connect() as connection:
            cursor = connection.cursor()
            if db_type == 'postgresql':
                cursor.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                    ORDER BY table_name
                """)
            elif db_type == 'mysql':
                cursor.execute('SHOW TABLES')
            elif db_type == 'mssql':
                cursor.execute("""
                    SELECT TABLE_NAME
                    FROM INFORMATION_SCHEMA.TABLES
                    WHERE TABLE_TYPE = 'BASE TABLE'
                    ORDER BY TABLE_NAME
                """)
            elif db_type == 'oracle':
                cursor.execute('SELECT table_name FROM user_tables ORDER BY table_name')
            else:
                raise ConnectionError(f'Unsupported database type: {db_type}')
            return [str(row[0]) for row in cursor.fetchall()]

    def list_columns(self, table_name):
        db_type = (self.config.database_type or '').lower()
        safe_table = self._sanitize_identifier(table_name) if db_type == 'sqlite' else table_name

        if db_type == 'sqlite':
            if safe_table not in self.list_tables():
                raise ConnectionError(f'Table not found: {table_name}')
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(f'PRAGMA table_info("{safe_table}")')
                return [
                    {'name': row[1], 'type': row[2] or 'unknown', 'nullable': not bool(row[3])}
                    for row in cursor.fetchall()
                ]

        if db_type == 'postgresql':
            query = """
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position
            """
        elif db_type == 'mysql':
            query = f'SHOW COLUMNS FROM `{table_name}`'
        elif db_type == 'mssql':
            query = """
                SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_NAME = ?
                ORDER BY ORDINAL_POSITION
            """
        elif db_type == 'oracle':
            query = """
                SELECT column_name, data_type, nullable
                FROM all_tab_columns
                WHERE table_name = UPPER(:table_name)
                ORDER BY column_id
            """
        else:
            raise ConnectionError(f'Unsupported database type: {db_type}')

        with self._connect() as connection:
            cursor = connection.cursor()
            if db_type == 'postgresql':
                cursor.execute(query, (table_name,))
                return [
                    {'name': row[0], 'type': row[1], 'nullable': row[2].lower() == 'yes'}
                    for row in cursor.fetchall()
                ]
            elif db_type == 'mysql':
                cursor.execute(query)
                return [
                    {'name': row[0], 'type': row[1], 'nullable': row[2].lower() == 'yes'}
                    for row in cursor.fetchall()
                ]
            elif db_type == 'mssql':
                cursor.execute(query, (table_name,))
                return [
                    {'name': row[0], 'type': row[1], 'nullable': row[2].lower() == 'yes'}
                    for row in cursor.fetchall()
                ]
            elif db_type == 'oracle':
                cursor.execute(query, {'table_name': table_name.upper()})
                return [
                    {'name': row[0], 'type': row[1], 'nullable': row[2].lower() == 'y'}
                    for row in cursor.fetchall()
                ]

    def preview_rows(self, table_name, limit=50):
        db_type = (self.config.database_type or '').lower()
        if db_type == 'sqlite':
            safe_table = self._sanitize_identifier(table_name)
            if safe_table not in self.list_tables():
                raise ConnectionError(f'Table not found: {table_name}')
            limit = max(1, min(int(limit), 50))
            with self._connect() as connection:
                cursor = connection.cursor()
                cursor.execute(f'SELECT * FROM "{safe_table}" LIMIT {limit}')
                columns = [description[0] for description in cursor.description]
                rows = [[self._serialize(value) for value in row] for row in cursor.fetchall()]
            return {'columns': columns, 'rows': rows, 'row_count': len(rows)}

        limit = max(1, min(int(limit), 50))
        if db_type == 'postgresql':
            sql = f'SELECT * FROM "{table_name}" LIMIT {limit}'
        elif db_type == 'mysql':
            sql = f'SELECT * FROM `{table_name}` LIMIT {limit}'
        elif db_type == 'mssql':
            sql = f'SELECT TOP {limit} * FROM [{table_name}]'
        elif db_type == 'oracle':
            sql = f'SELECT * FROM "{table_name}" FETCH FIRST {limit} ROWS ONLY'
        else:
            raise ConnectionError(f'Unsupported database type: {db_type}')

        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            columns = [description[0] for description in cursor.description]
            rows = [[self._serialize(value) for value in row] for row in cursor.fetchall()]
        return {'columns': columns, 'rows': rows, 'row_count': len(rows)}

    def _missing_driver_message(self, database_type):
        requirement = self.DRIVER_REQUIREMENTS.get(database_type)
        driver = requirement['package'] if requirement else 'sqlite3'
        return (
            f"'{database_type}' inspection requires the '{driver}' driver package "
            f"to be installed in this environment. Install it with `pip install {driver}` "
            f"or add it to the project requirements. SQLite is supported by the standard library."
        )

    @contextmanager
    def _connect(self):
        db_type = (self.config.database_type or '').lower()
        if db_type == 'sqlite':
            connection = sqlite3.connect(self.config.database_name, timeout=10)
            try:
                yield connection
            finally:
                connection.close()
            return

        requirement = self.DRIVER_REQUIREMENTS.get(db_type)
        if not requirement:
            raise ConnectionError(f"Unsupported database type: {db_type}")

        try:
            module = importlib.import_module(requirement['module'])
        except Exception:
            raise ConnectionError(self._missing_driver_message(db_type)) from None

        try:
            if db_type == 'postgresql':
                connection = module.connect(
                    host=self.config.host,
                    port=self.config.port,
                    dbname=self.config.database_name,
                    user=self.config.username,
                    password=self.config.password,
                )
            elif db_type == 'mysql':
                connection = module.connect(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.database_name,
                    user=self.config.username,
                    passwd=self.config.password,
                )
            elif db_type == 'mssql':
                pyodbc_dsn = (
                    f'DRIVER={{ODBC Driver 18 for SQL Server}};'
                    f'SERVER={self.config.host};'
                    f'PORT={self.config.port};'
                    f'DATABASE={self.config.database_name};'
                    f'UID={self.config.username};'
                    f'PWD={self.config.password}'
                )
                connection = module.connect(pyodbc_dsn)
            elif db_type == 'oracle':
                connection = module.connect(
                    user=self.config.username,
                    password=self.config.password,
                    host=self.config.host,
                    port=self.config.port,
                    service_name=self.config.database_name,
                )
            else:
                raise ConnectionError(f"Unsupported database type: {db_type}")
        except Exception as exc:
            raise ConnectionError(f'Connection failed: {exc}') from exc

        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _sanitize_identifier(name):
        if not re.match(r'^[A-Za-z0-9_]+$', name):
            raise ConnectionError(f'Invalid table name: {name}')
        return name

    @staticmethod
    def _serialize(value):
        return value if value is None or isinstance(value, (str, int, float, bool)) else str(value)
