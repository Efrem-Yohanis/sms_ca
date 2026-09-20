"""Audience ingestion service for manual, file, and database sources."""

import csv
import os
import sqlite3
from itertools import islice

from django.db import transaction
from django.utils import timezone

from ..models import AudienceMember, CustomerProfileConfig, AudienceConfig, Language
from ..utils import resolve_language, validate_msisdn
from .database_connector import DatabaseConnector


class AudienceBuildService:
    """Build the final msisdn/language audience rows from an AudienceConfig row.

    The source type is metadata-driven, so the service reads the stored
    source metadata (manual, file, or database) and then applies the mapper
    and default-language policy before bulk-writing AudienceMember rows.
    """

    def __init__(self, audience_config):
        self.config = audience_config
        self.campaign = audience_config.campaign
        self.default_language = audience_config.default_language

    def build(self):
        """Return a contract-safe build report and persist AudienceMember rows."""
        source_type = self.config.source_type
        if source_type == 'manual':
            rows = iter(self._manual_rows())
        elif source_type == 'file_import':
            rows = iter(self._file_rows())
        elif source_type == 'database':
            rows = self._database_rows()
        else:
            raise ValueError(f'Unsupported source type: {source_type}')

        valid = 0
        invalid = 0
        language_from_source = 0
        language_from_mapper = 0
        language_from_default = 0
        language_ids = {
            language.code: language.id
            for language in Language.objects.filter(
                code__in=['en', 'am', 'ti', 'om', 'so'],
                is_active=True,
            )
        }

        AudienceMember.objects.filter(campaign=self.campaign).delete()
        built_pairs = []
        sequence = 0
        for source_batch in iter(lambda: list(islice(rows, 5000)), []):
            mapper_lookup = self._mapper_rows(
                [row.get('msisdn') for row in source_batch]
            ) if self.config.mapper_enabled else {}
            audience_members = []
            for row in source_batch:
                sequence += 1
                msisdn = row.get('msisdn')
                normalized_msisdn, ok, error = self._normalize_msisdn(msisdn)
                if not ok:
                    invalid += 1
                    continue

                # Source language wins when present.
                source_language = str(row.get('language') or '').strip().lower()
                candidate_language = None
                language_source = 'default'

                if source_language and source_language in {'en', 'am', 'ti', 'om', 'so'}:
                    candidate_language = source_language
                    language_source = 'source'
                    language_from_source += 1
                elif mapper_lookup.get(normalized_msisdn):
                    candidate_language = str(mapper_lookup[normalized_msisdn]).strip().lower()
                    if candidate_language not in {'en', 'am', 'ti', 'om', 'so'}:
                        candidate_language = self.default_language.code
                    else:
                        language_source = 'reference'
                        language_from_mapper += 1
                else:
                    candidate_language = self.default_language.code
                    language_source = 'default'
                    language_from_default += 1

                valid += 1
                audience_members.append(AudienceMember(
                    campaign=self.campaign,
                    campaign_id=self.campaign.id,
                    msisdn=normalized_msisdn,
                    language_id=language_ids[candidate_language],
                    language_source=language_source,
                    is_valid=True,
                    validation_error='',
                    custom_fields={'source_type': source_type},
                    sequence_number=sequence,
                ))
                if len(built_pairs) < 1000:
                    built_pairs.append({'audience_id': self.config.id, 'campaign_id': self.campaign.id, 'msisdn': normalized_msisdn, 'language': candidate_language})

            AudienceMember.objects.bulk_create(audience_members, batch_size=5000)

        self.config.total_count = valid
        self.config.valid_count = valid
        self.config.invalid_count = invalid
        self.config.language_from_source = language_from_source
        self.config.language_from_mapper = language_from_mapper
        self.config.language_from_default = language_from_default
        self.config.is_processed = True
        self.config.last_built_at = timezone.now()
        self.config.save(update_fields=[
            'total_count', 'valid_count', 'invalid_count',
            'language_from_source', 'language_from_mapper',
            'language_from_default', 'is_processed', 'last_built_at', 'updated_at'
        ])

        return {
            'success': True,
            'message': 'Audience build completed.',
            'data': {
                'audience_id': self.config.id,
                'campaign_id': self.campaign.id,
                'source_type': source_type,
                'total_count': valid,
                'valid_count': valid,
                'invalid_count': invalid,
                'language_from_source': language_from_source,
                'language_from_mapper': language_from_mapper,
                'language_from_default': language_from_default,
                'is_processed': True,
                'rows': built_pairs,
            },
        }

    def _manual_rows(self):
        rows = []
        msisdns = list(self.config.manual_msisdns or [])
        languages = list(self.config.manual_languages or [])
        for idx, msisdn in enumerate(msisdns):
            language = languages[idx] if idx < len(languages) else ''
            rows.append({'msisdn': msisdn, 'language': language})
        return rows

    def _file_rows(self):
        rows = []
        file_path = self.config.source_file_path
        if file_path.startswith('/'):
            path = file_path
        else:
            path = os.path.abspath(os.path.join(os.getcwd(), file_path))

        if not os.path.exists(path):
            raise FileNotFoundError(f'Uploaded file not found at {path}')

        if path.lower().endswith('.csv'):
            with open(path, newline='', encoding='utf-8-sig') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    msisdn = row.get(self.config.source_file_msisdn_column, '')
                    language = row.get(self.config.source_file_language_column, '')
                    rows.append({'msisdn': msisdn, 'language': language})
        else:
            raise ValueError('File audience build currently supports CSV uploads.')
        return rows

    def _database_rows(self):
        connector = DatabaseConnector(self.config.source_database)
        db_type = (self.config.source_database.database_type or '').lower()
        quoted_table = self._quote_identifier(self.config.source_table, db_type)
        quoted_msisdn = self._quote_identifier(self.config.source_msisdn_column, db_type)
        quoted_language = self._quote_identifier(self.config.source_language_column, db_type) if self.config.source_language_column else None

        sql = f'SELECT {quoted_msisdn} AS msisdn'
        if quoted_language:
            sql += f', {quoted_language} AS language'
        else:
            sql += ', NULL AS language'
        sql += f' FROM {quoted_table}'
        if self.config.source_filter_clause:
            clause = self.config.source_filter_clause.strip()
            if clause.lower().startswith('where '):
                clause = clause[6:].strip()
            sql += f' WHERE {clause}'

        with connector._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql)
            columns = [col[0] for col in cursor.description]
            for record in iter(lambda: cursor.fetchmany(5000), []):
                for values in record:
                    values = dict(zip(columns, values))
                    yield {'msisdn': values.get('msisdn'), 'language': values.get('language') or ''}

    def _mapper_rows(self, msisdns=None):
        """Load mapper rows in bounded batches for the current source batch."""
        if not self.config.mapper_enabled or not self.config.mapper_database:
            return {}
        connector = DatabaseConnector(self.config.mapper_database)
        db_type = (self.config.mapper_database.database_type or '').lower()
        quoted_table = self._quote_identifier(self.config.mapper_table, db_type)
        quoted_msisdn = self._quote_identifier(self.config.mapper_msisdn_column, db_type)
        quoted_language = self._quote_identifier(self.config.mapper_language_column, db_type)
        sql = f'SELECT {quoted_msisdn} AS msisdn, {quoted_language} AS language FROM {quoted_table}'
        params = []
        if msisdns is not None:
            values = [value for value in msisdns if value is not None]
            if not values:
                return {}
            placeholder = '?' if db_type == 'sqlite' else '%s'
            sql += f" WHERE {quoted_msisdn} IN ({','.join([placeholder] * len(values))})"
            params = values
        with connector._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            rows = cursor.fetchall()
        return {str(msisdn): str(language).strip().lower() for msisdn, language in rows}

    @staticmethod
    def _normalize_msisdn(msisdn):
        from ..utils import normalize_msisdn
        normalized = normalize_msisdn(msisdn)
        if normalized:
            return normalized, True, ''
        return None, False, f'Invalid MSISDN format: {msisdn}'

    @staticmethod
    def _quote_identifier(name, db_type):
        db_type = (db_type or '').lower()
        if db_type == 'sqlite' or db_type == 'postgresql' or db_type == 'oracle':
            return f'"{name}"'
        if db_type == 'mysql':
            return f'`{name}`'
        if db_type == 'mssql':
            return f'[{name}]'
        return f'"{name}"'


class AudienceService:
    def __init__(self, campaign, default_language='en', customer_profile=None):
        self.campaign = campaign
        self.default_language = default_language
        self.customer_profile = customer_profile

    def create_from_manual(self, msisdns, languages=None):
        languages = languages or []
        rows = [
            {'msisdn': number, 'source_language': languages[index] if index < len(languages) else '', 'custom_fields': {}}
            for index, number in enumerate(msisdns)
        ]
        return self._process(rows, 'manual', {'manual_entries': len(rows)})

    def _process(self, rows, source_type, source_config):
        with transaction.atomic():
            self.campaign.default_language = self.default_language
            self.campaign.source_type = source_type
            self.campaign.source_config = source_config
            self.campaign.customer_profile = self.customer_profile
            self.campaign.processing_started_at = timezone.now()
            self.campaign.processing_completed_at = None
            self.campaign.is_processed = False
            self.campaign.total_count = 0
            self.campaign.valid_count = 0
            self.campaign.invalid_count = 0
            self.campaign.language_matched = 0
            self.campaign.language_defaulted = 0
            self.campaign.save(update_fields=[
                'default_language', 'source_type', 'source_config', 'customer_profile',
                'processing_started_at', 'processing_completed_at', 'is_processed',
                'total_count', 'valid_count', 'invalid_count', 'language_matched',
                'language_defaulted', 'updated_at'
            ])

            AudienceMember.objects.filter(campaign=self.campaign).delete()
            members = []
            valid = invalid = matched = defaulted = 0
            for sequence, row in enumerate(rows, start=1):
                is_valid, normalized, error = validate_msisdn(row.get('msisdn'))
                language, source = resolve_language(row.get('source_language'), '', self.default_language)
                if is_valid:
                    valid += 1
                    if source == 'source':
                        matched += 1
                    else:
                        defaulted += 1
                else:
                    invalid += 1
                members.append(AudienceMember(
                    campaign=self.campaign,
                    campaign_id=self.campaign.id,
                    msisdn=normalized or str(row.get('msisdn', ''))[:20],
                    language=language,
                    language_source=source,
                    is_valid=is_valid,
                    validation_error=error,
                    custom_fields=row.get('custom_fields') or {},
                    sequence_number=sequence,
                ))
            AudienceMember.objects.bulk_create(members, batch_size=10000)

            self.campaign.total_count = len(rows)
            self.campaign.valid_count = valid
            self.campaign.invalid_count = invalid
            self.campaign.language_matched = matched
            self.campaign.language_defaulted = defaulted
            self.campaign.is_processed = True
            self.campaign.processing_completed_at = timezone.now()
            self.campaign.save(update_fields=[
                'total_count', 'valid_count', 'invalid_count', 'language_matched',
                'language_defaulted', 'is_processed', 'processing_completed_at', 'updated_at'
            ])
        return self.campaign
