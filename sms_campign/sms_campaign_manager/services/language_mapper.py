"""Language lookups for customer profile-based audience enrichment."""

import re

from .database_connector import DatabaseConnector, ConnectionError


class LanguageMapper:
    """Resolve MSISDN language values from a configured customer profile table."""

    def __init__(self, profile):
        self.profile = profile
        self.connector = DatabaseConnector(profile.database_config)

    def lookup_batch(self, msisdns):
        """Return a dict of msisdn -> language for a batch of numbers.

        Priority and behavior mirrors the intended profile mapping flow:
        fetch from the source table using the configured profile columns and
        fall back to None when no language row is found.
        """
        msisdns = [str(value).strip() for value in msisdns if str(value).strip()]
        if not msisdns:
            return {}

        db_type = (self.profile.database_config.database_type or '').lower()
        safe_msisdn_column = self._safe_identifier(self.profile.msisdn_column)
        safe_language_column = self._safe_identifier(self.profile.language_column)
        safe_table = self._safe_identifier(self.profile.table_name)

        msisdn_col = self._quote_identifier(safe_msisdn_column, db_type)
        language_col = self._quote_identifier(safe_language_column, db_type)
        table_ident = self._quote_identifier(safe_table, db_type)
        values_sql = ', '.join(self._quote_literal(msisdn, db_type) for msisdn in msisdns)

        sql = (
            f'SELECT {msisdn_col} AS msisdn, {language_col} AS language '
            f'FROM {table_ident} '
            f'WHERE {msisdn_col} IN ({values_sql})'
        )

        with self.connector._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()

        mapping = {}
        for msisdn, language in rows:
            key = str(msisdn)
            mapping[key] = str(language) if language is not None else None

        return mapping

    @staticmethod
    def _safe_identifier(name):
        if not re.match(r'^[A-Za-z0-9_]+$', name):
            raise ConnectionError(f'Invalid database identifier: {name}')
        return name

    @staticmethod
    def _quote_identifier(name, db_type):
        db_type = (db_type or '').lower()
        if db_type == 'sqlite':
            return f'"{name}"'
        if db_type == 'postgresql':
            return f'"{name}"'
        if db_type == 'mysql':
            return f'`{name}`'
        if db_type == 'mssql':
            return f'[{name}]'
        if db_type == 'oracle':
            return f'"{name}"'
        raise ConnectionError(f'Unsupported database type: {db_type}')

    @staticmethod
    def _quote_literal(value, db_type):
        db_type = (db_type or '').lower()
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"
