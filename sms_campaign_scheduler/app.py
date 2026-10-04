"""Standalone campaign scheduler service."""

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, time as clock_time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import requests
from fastapi import FastAPI, HTTPException

logger = logging.getLogger('sms_campaign_scheduler')

DJANGO_API_BASE_URL = os.getenv(
    'SMSC_SCHEDULER_DJANGO_API',
    'http://127.0.0.1:8000/api/v1',
).rstrip('/')
SCHEDULER_INTERVAL_SECONDS = int(os.getenv('SMSC_SCHEDULER_INTERVAL', '60'))
RUN_WORKER = os.getenv('SMSC_SCHEDULER_RUN_WORKER', 'false').lower() in {'1', 'true', 'yes'}


class CampaignScheduler:
    """Poll campaign schedules and apply activate/cancel decisions."""

    def __init__(self):
        self.lock = asyncio.Lock()
        self.worker_task: asyncio.Task | None = None
        self.last_report: dict[str, Any] = {}

    def campaigns(self) -> list[dict[str, Any]]:
        campaigns: list[dict[str, Any]] = []
        page = 1
        while True:
            response = requests.get(
                f'{DJANGO_API_BASE_URL}/campaigns/',
                params={'page': page, 'page_size': 200},
                timeout=10,
            )
            response.raise_for_status()
            body = response.json()
            if isinstance(body, list):
                campaigns.extend(body)
                break
            campaigns.extend(body.get('results', []))
            if not body.get('next'):
                break
            page += 1
        return campaigns

    @staticmethod
    def _local_current(schedule: dict[str, Any], current: datetime) -> datetime:
        try:
            schedule_timezone = ZoneInfo(schedule.get('timezone') or 'UTC')
        except ZoneInfoNotFoundError:
            schedule_timezone = timezone.utc
        return current.astimezone(schedule_timezone)

    @staticmethod
    def _occurs_on(schedule: dict[str, Any], current_date: date) -> bool:
        start = date.fromisoformat(str(schedule['start_date']))
        end = date.fromisoformat(str(schedule['end_date'])) if schedule.get('end_date') else None
        if current_date < start or (end and current_date > end):
            return False
        schedule_type = schedule.get('schedule_type')
        if schedule_type == 'once':
            return current_date == start
        if schedule_type == 'daily':
            return True
        if schedule_type == 'weekly':
            return current_date.weekday() in schedule.get('run_days', [])
        if schedule_type == 'monthly':
            return current_date.day == start.day
        return False

    @classmethod
    def current_window_start(cls, row: dict[str, Any], current: datetime) -> datetime | None:
        schedule = row.get('schedule')
        if not schedule or not schedule.get('is_active') or schedule.get('schedule_status') != 'active':
            return None
        local_current = cls._local_current(schedule, current)
        if not cls._occurs_on(schedule, local_current.date()):
            return None
        current_time = local_current.time().replace(tzinfo=None)
        for window in schedule.get('time_windows') or []:
            start_time = clock_time.fromisoformat(window['start'])
            end_time = clock_time.fromisoformat(window['end'])
            if start_time <= current_time < end_time:
                return datetime.combine(local_current.date(), start_time, tzinfo=local_current.tzinfo)
        return None

    @classmethod
    def is_running_now(cls, row: dict[str, Any], current: datetime) -> bool:
        return cls.current_window_start(row, current) is not None

    @classmethod
    def prepare_window_start(cls, row: dict[str, Any], current: datetime) -> datetime | None:
        policy = row.get('audience_rebuild')
        schedule = row.get('schedule')
        if not policy or not policy.get('enabled') or not schedule:
            return None
        local_current = cls._local_current(schedule, current)
        if schedule.get('schedule_status') != 'active' or not cls._occurs_on(schedule, local_current.date()):
            return None
        minutes_before = int(policy.get('minutes_before', 10))
        for window in schedule.get('time_windows') or []:
            window_start = datetime.combine(
                local_current.date(),
                clock_time.fromisoformat(window['start']),
                tzinfo=local_current.tzinfo,
            )
            prepare_start = window_start - timedelta(minutes=minutes_before)
            if prepare_start <= local_current < window_start:
                return window_start
        return None

    @classmethod
    def is_prepare_window(cls, row: dict[str, Any], current: datetime) -> bool:
        return cls.prepare_window_start(row, current) is not None

    @staticmethod
    def _was_built_for_window(policy: dict[str, Any], window_start: datetime, current: datetime) -> bool:
        last_built_value = policy.get('last_built_at')
        if not last_built_value:
            return False
        try:
            last_built = datetime.fromisoformat(str(last_built_value).replace('Z', '+00:00'))
        except ValueError:
            return False
        if last_built.tzinfo is None:
            last_built = last_built.replace(tzinfo=timezone.utc)
        local_last_built = last_built.astimezone(window_start.tzinfo)
        local_current = current.astimezone(window_start.tzinfo)
        prepare_start = window_start - timedelta(minutes=int(policy.get('minutes_before', 10)))
        return prepare_start <= local_last_built <= local_current

    @staticmethod
    def call_campaign_api(campaign_id: int, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = requests.post(
            f'{DJANGO_API_BASE_URL}/campaigns/{campaign_id}/{action}/',
            json=payload or {},
            timeout=10,
        )
        try:
            body = response.json()
        except ValueError:
            body = {'raw': response.text[:500]}
        if response.status_code not in (200, 201):
            raise RuntimeError(
                f'{action} campaign {campaign_id} failed: '
                f'HTTP {response.status_code}: {body}'
            )
        return body

    @staticmethod
    def prepare_campaign(campaign: dict[str, Any]) -> dict[str, Any]:
        policy = campaign['audience_rebuild']
        timeout = max(60, int(policy.get('timeout_minutes', 30)) * 60)
        response = requests.post(
            f"{DJANGO_API_BASE_URL}/audience-configs/{policy['id']}/build/",
            json={'increment_round': True},
            timeout=timeout,
        )
        response.raise_for_status()
        job = response.json()
        job_id = job.get('job_id')
        if job_id:
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                status_response = requests.get(
                    f'{DJANGO_API_BASE_URL}/audience-build-jobs/{job_id}/',
                    timeout=10,
                )
                status_response.raise_for_status()
                status = status_response.json().get('data', {})
                if status.get('status') == 'SUCCEEDED':
                    break
                if status.get('status') == 'FAILED':
                    raise RuntimeError(status.get('error_message') or f'Audience build job {job_id} failed')
                time.sleep(1)
            else:
                raise RuntimeError(f'Audience build job {job_id} timed out')
        response = requests.post(
            f"{DJANGO_API_BASE_URL}/campaigns/{campaign['id']}/messages/build/",
            json={'round_number': job.get('round_number', 1)},
            timeout=timeout,
        )
        response.raise_for_status()
        return response.json()

    async def run_once(self) -> dict[str, Any]:
        async with self.lock:
            now = datetime.now(timezone.utc)
            started: list[int] = []
            paused: list[int] = []
            resumed: list[int] = []
            prepared: list[int] = []
            errors: list[str] = []
            campaigns = await asyncio.to_thread(self.campaigns)
            for campaign in campaigns:
                running = self.is_running_now(campaign, now)
                policy = campaign.get('audience_rebuild') or {}

                async def prepare_window(window_start: datetime) -> None:
                    await asyncio.to_thread(self.prepare_campaign, campaign)
                    policy['last_built_at'] = datetime.now(timezone.utc).isoformat()
                    if campaign['id'] not in prepared:
                        prepared.append(campaign['id'])

                try:
                    preparation_start = self.prepare_window_start(campaign, now)
                    if (
                        preparation_start
                        and not self._was_built_for_window(policy, preparation_start, now)
                    ):
                        await prepare_window(preparation_start)

                    if running and campaign['status'] == 'draft':
                        running_window = self.current_window_start(campaign, now)
                        if (
                            policy.get('enabled')
                            and running_window
                            and not self._was_built_for_window(policy, running_window, now)
                        ):
                            await prepare_window(running_window)
                        await asyncio.to_thread(
                            self.call_campaign_api,
                            campaign['id'],
                            'activate',
                            {'build_messages': not bool(policy.get('enabled'))},
                        )
                        await asyncio.to_thread(self.call_campaign_api, campaign['id'], 'start')
                        started.append(campaign['id'])
                    elif running and campaign['status'] == 'active':
                        await asyncio.to_thread(self.call_campaign_api, campaign['id'], 'start')
                        started.append(campaign['id'])
                    elif running and campaign['status'] == 'paused':
                        await asyncio.to_thread(self.call_campaign_api, campaign['id'], 'resume')
                        resumed.append(campaign['id'])
                    elif not running and campaign['status'] == 'in_progress':
                        await asyncio.to_thread(self.call_campaign_api, campaign['id'], 'pause')
                        paused.append(campaign['id'])
                except (requests.RequestException, RuntimeError, ValueError, TypeError, KeyError) as exc:
                    errors.append(str(exc))
                    logger.exception(
                        'Schedule processing failed campaign_id=%s',
                        campaign.get('id'),
                    )

            self.last_report = {
                'success': not errors,
                'checked': len(campaigns),
                'prepared': prepared,
                'started': started,
                'stopped': [],
                'paused': paused,
                'resumed': resumed,
                'errors': errors,
            }
            logger.info(
                'Schedule check complete checked=%s prepared=%s started=%s paused=%s resumed=%s errors=%s',
                len(campaigns),
                len(prepared),
                len(started),
                len(paused),
                len(resumed),
                len(errors),
            )
            return self.last_report

    async def worker(self) -> None:
        while True:
            started_at = asyncio.get_running_loop().time()
            try:
                await self.run_once()
            except Exception as exc:
                self.last_report = {'success': False, 'errors': [str(exc)]}
                logger.exception('Scheduled worker cycle failed')
            delay = max(
                0.0,
                SCHEDULER_INTERVAL_SECONDS - (asyncio.get_running_loop().time() - started_at),
            )
            await asyncio.sleep(delay or 0.01)


scheduler = CampaignScheduler()


@asynccontextmanager
async def lifespan(_: FastAPI):
    if RUN_WORKER:
        logger.info(
            'Starting scheduler worker interval_seconds=%s',
            SCHEDULER_INTERVAL_SECONDS,
        )
        scheduler.worker_task = asyncio.create_task(scheduler.worker())
    yield
    if scheduler.worker_task:
        logger.info('Stopping scheduler worker')
        scheduler.worker_task.cancel()
        try:
            await scheduler.worker_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title='SMS Campaign Scheduler',
    version='1.0.0',
    description='Standalone schedule checker for campaign activation and stopping.',
    lifespan=lifespan,
)


@app.get('/health')
async def health() -> dict[str, Any]:
    return {
        'success': True,
        'django_api': DJANGO_API_BASE_URL,
        'interval_seconds': SCHEDULER_INTERVAL_SECONDS,
        'worker_running': scheduler.worker_task is not None and not scheduler.worker_task.done(),
        'last_report': scheduler.last_report,
    }


@app.post('/run-once')
async def run_once() -> dict[str, Any]:
    try:
        return await scheduler.run_once()
    except (requests.RequestException, RuntimeError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post('/worker/start')
async def start_worker() -> dict[str, Any]:
    if scheduler.worker_task is None or scheduler.worker_task.done():
        scheduler.worker_task = asyncio.create_task(scheduler.worker())
    return {'success': True, 'worker_running': True}


@app.post('/worker/stop')
async def stop_worker() -> dict[str, Any]:
    if scheduler.worker_task:
        scheduler.worker_task.cancel()
        scheduler.worker_task = None
    return {'success': True, 'worker_running': False}
