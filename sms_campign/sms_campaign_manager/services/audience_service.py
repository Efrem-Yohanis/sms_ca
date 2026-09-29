"""Audience ingestion service for manual, file, and database sources."""

import csv
import logging
import os
import sqlite3
import time
import uuid

from django.db import transaction
from django.utils import timezone

from ..models import AudienceBuildJob, AudienceMember, CustomerProfileConfig, AudienceConfig, Language
from ..utils import resolve_language, validate_msisdn
from .database_connector import DatabaseConnector

logger = logging.getLogger(__name__)


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
        self.chunk_size = 5000

    def _progress(self, phase=None, processed=None, total=None):
        update = {}
        if phase is not None:
            update['last_rebuild_phase'] = phase
        if processed is not None:
            update['last_rebuild_processed'] = processed
        if total is not None:
            update['last_rebuild_total'] = total
        current_processed = processed if processed is not None else self.config.last_rebuild_processed
        current_total = total if total is not None else self.config.last_rebuild_total
        if current_total:
            update['last_rebuild_percent'] = round(current_processed / current_total * 100, 2)
        elif total == 0:
            update['last_rebuild_percent'] = 0
        if update:
            AudienceConfig.objects.filter(pk=self.config.pk).update(**update, updated_at=timezone.now())
            for field, value in update.items():
                setattr(self.config, field, value)
            if phase is not None or (processed is not None and processed % 5000 == 0):
                logger.info(
                    'Audience build progress config_id=%s campaign_id=%s round=%s phase=%s processed=%s total=%s percent=%s',
                    self.config.pk,
                    self.campaign.pk,
                    getattr(self, 'build_round_number', self.config.round_number),
                    self.config.last_rebuild_phase,
                    self.config.last_rebuild_processed,
                    self.config.last_rebuild_total,
                    self.config.last_rebuild_percent,
                )

    def build(self, round_number=None, build_id=None):
        """Return a contract-safe build report and persist AudienceMember rows."""
        round_number = max(int(round_number or self.config.round_number or 1), 1)
        self.build_round_number = round_number
        build_id = build_id or uuid.uuid4().hex
        rows = []
        source_type = self.config.source_type
        logger.info(
            'Audience build started config_id=%s campaign_id=%s source_type=%s round=%s build_id=%s',
            self.config.pk,
            self.campaign.pk,
            source_type,
            round_number,
            build_id,
        )
        if source_type == 'manual':
            rows = iter(self._manual_rows())
        elif source_type == 'file_import':
            rows = self._file_rows()
        elif source_type == 'database':
            rows = self._database_rows()
        else:
            raise ValueError(f'Unsupported source type: {source_type}')

        self._progress(phase='fetching', processed=0, total=0)

        mapper_join = self._uses_database_mapper_join()
        mapper_lookup = self._mapper_rows() if self.config.mapper_enabled and not mapper_join else {}
        supported_languages = {
            language.code: language
            for language in Language.objects.filter(code__in=['en', 'am', 'ti', 'om', 'so'])
        }

        valid = 0
        invalid = 0
        language_from_source = 0
        language_from_mapper = 0
        language_from_default = 0

        audience_members = []
        built_pairs = []
        total_count = 0
        total_rows_fetched = 0
        sequence = 0
        seen_msisdns = set()
        duplicate_rows = 0
        first_chunk = True
        for row in rows:
            total_rows_fetched += 1
            if total_rows_fetched % 5000 == 0:
                self._progress(phase='validating', processed=total_rows_fetched)
            msisdn = row.get('msisdn')
            normalized_msisdn, ok, error = self._normalize_msisdn(msisdn)
            stored_msisdn = normalized_msisdn if ok else str(msisdn or '').strip()[:20]
            if stored_msisdn in seen_msisdns:
                duplicate_rows += 1
                continue
            seen_msisdns.add(stored_msisdn)
            sequence += 1

            source_language = str(row.get('language') or '').strip().lower()
            candidate_language = None
            language_source = 'default'

            if source_language and source_language in supported_languages:
                candidate_language = source_language
                language_source = 'source'
                language_from_source += 1
            elif row.get('mapper_language') or mapper_lookup.get(normalized_msisdn):
                mapped_language = row.get('mapper_language') or mapper_lookup[normalized_msisdn]
                candidate_language = str(mapped_language).strip().lower()
                if candidate_language not in supported_languages:
                    candidate_language = self.default_language.code
                    language_from_default += 1
                else:
                    language_source = 'mapper'
                    language_from_mapper += 1
            else:
                candidate_language = self.default_language.code
                language_source = 'default'
                language_from_default += 1

            if ok:
                valid += 1
            else:
                invalid += 1
            total_count += 1
            audience_members.append(AudienceMember(
                campaign=self.campaign,
                campaign_id=self.campaign.id,
                msisdn=stored_msisdn,
                language_id=supported_languages.get(candidate_language, self.default_language).id,
                language_source=language_source,
                source_type=source_type,
                is_valid=ok,
                validation_error=error,
                custom_fields={},
                sequence_number=sequence,
                round_number=round_number,
                build_id=build_id,
            ))
            if len(built_pairs) < 100:
                built_pairs.append({'audience_id': self.config.id, 'campaign_id': self.campaign.id, 'msisdn': stored_msisdn, 'language': candidate_language})

            if len(audience_members) >= self.chunk_size:
                if first_chunk:
                    AudienceMember.objects.filter(
                        campaign=self.campaign,
                        round_number=round_number,
                    ).delete()
                    first_chunk = False
                AudienceMember.objects.bulk_create(audience_members, batch_size=self.chunk_size)
                self._progress(phase='inserting', processed=total_rows_fetched)
                audience_members = []

        if first_chunk:
            AudienceMember.objects.filter(
                campaign=self.campaign,
                round_number=round_number,
            ).delete()
        self._progress(phase='inserting', processed=total_rows_fetched, total=total_rows_fetched)
        if audience_members:
            AudienceMember.objects.bulk_create(audience_members, batch_size=self.chunk_size)
        self._progress(phase='finalizing', processed=total_rows_fetched, total=total_rows_fetched)

        self.config.total_count = total_count
        self.config.total_rows_fetched = total_rows_fetched
        self.config.valid_count = valid
        self.config.invalid_count = invalid
        self.config.round_number = round_number
        self.config.language_from_source = language_from_source
        self.config.language_from_mapper = language_from_mapper
        self.config.language_from_default = language_from_default
        self.config.last_build_id = build_id
        self.config.is_round_active = True
        self.config.is_processed = True
        self.config.last_built_at = timezone.now()
        self.config.last_rebuild_processed = total_rows_fetched
        self.config.last_rebuild_total = total_rows_fetched
        self.config.last_rebuild_percent = 100
        self.config.save(update_fields=[
            'total_count', 'total_rows_fetched', 'valid_count', 'invalid_count',
            'language_from_source', 'language_from_mapper',
            'language_from_default', 'round_number', 'is_processed', 'last_built_at',
            'last_build_id', 'is_round_active',
            'last_rebuild_processed', 'last_rebuild_total', 'last_rebuild_percent', 'updated_at'
        ])
        self.campaign.refresh_readiness_flag()
        logger.info(
            'Audience build complete config_id=%s campaign_id=%s source_type=%s round=%s build_id=%s fetched=%s unique=%s valid=%s invalid=%s duplicates=%s language_source=%s language_mapper=%s language_default=%s',
            self.config.pk,
            self.campaign.pk,
            source_type,
            round_number,
            build_id,
            total_rows_fetched,
            total_count,
            valid,
            invalid,
            duplicate_rows,
            language_from_source,
            language_from_mapper,
            language_from_default,
        )

        return {
            'success': True,
            'message': 'Audience build completed.',
            'data': {
                'audience_id': self.config.id,
                'campaign_id': self.campaign.id,
                'source_type': source_type,
                'total_count': total_count,
                'total_rows_fetched': total_rows_fetched,
                'valid_count': valid,
                'invalid_count': invalid,
                'round_number': round_number,
                'build_id': build_id,
                'language_from_source': language_from_source,
                'language_from_mapper': language_from_mapper,
                'language_from_default': language_from_default,
                'is_processed': True,
                'rows': built_pairs,
            },
        }

    @classmethod
    def run_job(cls, job_id):
        job = AudienceBuildJob.objects.select_related('audience_config').get(pk=job_id)
        if job.status == 'SUCCEEDED':
            return job
        started_at = timezone.now()
        started_clock = time.monotonic()
        config = job.audience_config
        job.status = 'RUNNING'
        job.started_at = job.started_at or started_at
        job.heartbeat_at = started_at
        job.error_message = ''
        job.save(update_fields=['status', 'started_at', 'heartbeat_at', 'error_message', 'updated_at'])
        logger.info(
            'Audience build job started job_id=%s config_id=%s campaign_id=%s round=%s',
            job.pk,
            config.pk,
            config.campaign_id,
            job.round_number,
        )
        config.last_rebuild_started_at = started_at
        config.last_rebuild_status = 'running'
        config.last_rebuild_phase = 'starting'
        config.last_rebuild_processed = 0
        config.last_rebuild_total = 0
        config.last_rebuild_percent = 0
        config.last_rebuild_error = ''
        config.is_processed = False
        config.round_number = job.round_number
        build_id = (job.result or {}).get('build_id') or uuid.uuid4().hex
        config.last_build_id = build_id
        config.save(update_fields=[
            'last_rebuild_started_at', 'last_rebuild_status', 'last_rebuild_phase',
            'last_rebuild_processed', 'last_rebuild_total', 'last_rebuild_percent', 'last_rebuild_error',
            'is_processed', 'round_number', 'last_build_id', 'updated_at',
        ])
        try:
            result = cls(config).build(job.round_number, build_id=build_id)
            data = result.get('data', {})
            completed_at = timezone.now()
            duration = max(time.monotonic() - started_clock, 0)
            history = (config.rebuild_history_seconds or [])[-19:] + [duration]
            config.last_rebuild_completed_at = completed_at
            config.last_rebuild_status = 'success'
            config.last_rebuild_phase = 'done'
            config.last_rebuild_round = job.round_number
            config.is_round_active = True
            config.last_rebuild_error = ''
            config.last_rebuild_duration_seconds = duration
            config.avg_rebuild_duration_seconds = sum(history) / len(history)
            config.rebuild_history_seconds = history
            config.last_built_at = completed_at
            config.save(update_fields=[
                'last_rebuild_completed_at', 'last_rebuild_status', 'last_rebuild_phase', 'last_rebuild_error',
                'last_rebuild_duration_seconds', 'avg_rebuild_duration_seconds',
                'rebuild_history_seconds', 'last_built_at', 'last_rebuild_round', 'updated_at',
            ])
            schedule = getattr(config.campaign, 'schedule', None)
            if schedule and job.round_number > schedule.current_round:
                schedule.current_round = job.round_number
                schedule.save(update_fields=['current_round', 'updated_at'])
            job.status = 'SUCCEEDED'
            job.processed_rows = data.get('total_rows_fetched', 0)
            job.valid_rows = data.get('valid_count', 0)
            job.invalid_rows = data.get('invalid_count', 0)
            job.result = result
            job.completed_at = completed_at
            job.heartbeat_at = job.completed_at
            job.save(update_fields=[
                'status', 'processed_rows', 'valid_rows', 'invalid_rows',
                'result', 'completed_at', 'heartbeat_at', 'updated_at',
            ])
            logger.info(
                'Audience build job succeeded job_id=%s config_id=%s campaign_id=%s round=%s processed=%s valid=%s invalid=%s duration_seconds=%.3f',
                job.pk,
                config.pk,
                config.campaign_id,
                job.round_number,
                job.processed_rows,
                job.valid_rows,
                job.invalid_rows,
                duration,
            )
        except Exception as error:
            completed_at = timezone.now()
            duration = max(time.monotonic() - started_clock, 0)
            config.last_rebuild_completed_at = completed_at
            config.last_rebuild_status = 'failed'
            config.last_rebuild_phase = 'failed'
            config.last_rebuild_error = str(error)
            config.last_rebuild_duration_seconds = duration
            config.save(update_fields=[
                'last_rebuild_completed_at', 'last_rebuild_status', 'last_rebuild_phase', 'last_rebuild_error',
                'last_rebuild_duration_seconds', 'updated_at',
            ])
            job.status = 'FAILED'
            job.error_message = str(error)
            job.completed_at = completed_at
            job.heartbeat_at = job.completed_at
            job.save(update_fields=['status', 'error_message', 'completed_at', 'heartbeat_at', 'updated_at'])
            logger.exception(
                'Audience build job failed job_id=%s config_id=%s campaign_id=%s round=%s duration_seconds=%.3f',
                job.pk,
                config.pk,
                config.campaign_id,
                job.round_number,
                duration,
            )
        return job

    def _manual_rows(self):
        rows = []
        msisdns = list(self.config.manual_msisdns or [])
        languages = list(self.config.manual_languages or [])
        for idx, msisdn in enumerate(msisdns):
            language = languages[idx] if idx < len(languages) else ''
            rows.append({'msisdn': msisdn, 'language': language})
        return rows

    def _file_rows(self):
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
                    yield {'msisdn': msisdn, 'language': language}
        else:
            raise ValueError('File audience build currently supports CSV uploads.')

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

        mapper_join = self._uses_database_mapper_join()
        if mapper_join:
            mapper_table = self._quote_identifier(self.config.mapper_table, db_type)
            mapper_msisdn = self._quote_identifier(self.config.mapper_msisdn_column, db_type)
            mapper_language = self._quote_identifier(self.config.mapper_language_column, db_type)
            source_language = f'src.{quoted_language}' if quoted_language else 'NULL'
            join_type = 'INNER JOIN' if self.config.mapper_join_type == 'INNER' else 'LEFT JOIN'
            source_alias = f'{quoted_table} src' if db_type == 'oracle' else f'{quoted_table} AS src'
            sql = (
                f'SELECT src.{quoted_msisdn} AS msisdn, '
                f'{source_language} AS language, '
                f'ref.{mapper_language} AS mapper_language '
                f'FROM {source_alias} '
                f'{join_type} {mapper_table} ref '
                f'ON src.{quoted_msisdn} = ref.{mapper_msisdn}'
            )
            if self.config.source_filter_clause:
                clause = self.config.source_filter_clause.strip()
                if clause.lower().startswith('where '):
                    clause = clause[6:].strip()
                sql += f' WHERE {clause}'

        with connector._connect() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(sql)
                columns = [col[0] for col in cursor.description]
                while True:
                    records = cursor.fetchmany(self.chunk_size)
                    if not records:
                        break
                    for record in records:
                        values = dict(zip(columns, record))
                        yield {
                            'msisdn': values.get('msisdn'),
                            'language': values.get('language') or '',
                            'mapper_language': values.get('mapper_language') or '',
                        }
            finally:
                cursor.close()

    def _mapper_rows(self):
        """Return a simple msisdn -> language map for the mapper table."""
        if not self.config.mapper_enabled or not self.config.mapper_database:
            return {}
        connector = DatabaseConnector(self.config.mapper_database)
        db_type = (self.config.mapper_database.database_type or '').lower()
        quoted_table = self._quote_identifier(self.config.mapper_table, db_type)
        quoted_msisdn = self._quote_identifier(self.config.mapper_msisdn_column, db_type)
        quoted_language = self._quote_identifier(self.config.mapper_language_column, db_type)
        sql = f'SELECT {quoted_msisdn} AS msisdn, {quoted_language} AS language FROM {quoted_table}'
        with connector._connect() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(sql)
                result = {}
                while True:
                    rows = cursor.fetchmany(self.chunk_size)
                    if not rows:
                        break
                    for msisdn, language in rows:
                        normalized, valid, _ = self._normalize_msisdn(msisdn)
                        if valid and language:
                            result[normalized] = str(language).strip().lower()
            finally:
                cursor.close()
        return result

    def _uses_database_mapper_join(self):
        return bool(
            self.config.source_type == 'database'
            and self.config.mapper_enabled
            and self.config.mapper_database_id == self.config.source_database_id
            and self.config.mapper_table
        )

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

    def create_from_manual(self, msisdns, languages=None, source_type='manual'):
        languages = languages or []
        rows = [
            {'msisdn': number, 'source_language': languages[index] if index < len(languages) else '', 'custom_fields': {}}
            for index, number in enumerate(msisdns)
        ]
        return self._process(rows, source_type)

    def _process(self, rows, source_type):
        rows = list(rows)
        languages_by_code = {
            language.code: language
            for language in Language.objects.filter(code__in=['en', 'am', 'ti', 'om', 'so'])
        }
        default_language = languages_by_code[self.default_language]
        with transaction.atomic():
            AudienceMember.objects.filter(campaign=self.campaign).delete()
            members = []
            valid = invalid = matched = defaulted = 0
            for sequence, row in enumerate(rows, start=1):
                is_valid, normalized, error = validate_msisdn(row.get('msisdn'))
                language_code, source = resolve_language(row.get('source_language'), '', self.default_language)
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
                    language=languages_by_code[language_code],
                    language_source=source,
                    source_type=source_type,
                    is_valid=is_valid,
                    validation_error=error,
                    custom_fields=row.get('custom_fields') or {},
                    sequence_number=sequence,
                ))
            AudienceMember.objects.bulk_create(members, batch_size=10000)

            config, _ = AudienceConfig.objects.get_or_create(
                campaign=self.campaign,
                defaults={'default_language': default_language},
            )
            config.source_type = source_type
            config.manual_msisdns = [row['msisdn'] for row in rows]
            config.manual_languages = [row.get('source_language', '') for row in rows]
            config.source_file_path = ''
            config.default_language = default_language
            config.total_count = len(rows)
            config.valid_count = valid
            config.invalid_count = invalid
            config.language_from_source = matched
            config.language_from_mapper = 0
            config.language_from_default = defaulted
            config.is_processed = True
            config.last_built_at = timezone.now()
            config.save()

            self.campaign.refresh_readiness_flag()
        logger.info(
            'Manual audience creation complete campaign_id=%s source_type=%s fetched=%s valid=%s invalid=%s language_matched=%s language_default=%s',
            self.campaign.pk,
            source_type,
            len(rows),
            valid,
            invalid,
            matched,
            defaulted,
        )
        return self.campaign
