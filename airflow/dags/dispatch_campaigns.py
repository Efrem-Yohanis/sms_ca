"""Poll Django schedules and start or stop campaign senders."""

from datetime import timedelta
import logging
import os
import time

import pendulum
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator


log = logging.getLogger(__name__)
DJANGO_API = os.getenv('AIRFLOW_DJANGO_API', 'http://camaping-manager-backend-app:8000/api/v1').rstrip('/')
SENDER_API = os.getenv('AIRFLOW_SENDER_API', 'http://sms_sender_app:8001').rstrip('/')
AUDIENCE_BUILD_TIMEOUT_SECONDS = int(os.getenv('AIRFLOW_AUDIENCE_BUILD_TIMEOUT', '1800'))
AUDIENCE_POLL_INTERVAL_SECONDS = int(os.getenv('AIRFLOW_AUDIENCE_POLL_INTERVAL', '5'))


def _get_json(url, *, timeout=30):
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    body = response.json()
    if isinstance(body, dict) and body.get('success') is False:
        raise RuntimeError(body.get('error') or body.get('detail') or f'Request failed: {url}')
    return body


def _post_json(url, payload, *, timeout=60):
    response = requests.post(url, json=payload, timeout=timeout)
    try:
        body = response.json()
    except ValueError:
        body = {'raw': response.text[:500]}
    return response.status_code, body, response.text


def _wait_for_audience_build(config_id):
    deadline = time.monotonic() + AUDIENCE_BUILD_TIMEOUT_SECONDS
    progress_url = f'{DJANGO_API}/audience-configs/{config_id}/progress/'
    while time.monotonic() < deadline:
        progress = _get_json(progress_url, timeout=30).get('data') or {}
        build_status = str(progress.get('status') or '').lower()
        if build_status in {'success', 'succeeded'}:
            log.info(
                'Audience build succeeded config_id=%s round=%s build_id=%s',
                config_id,
                progress.get('round_number'),
                progress.get('build_id'),
            )
            return progress
        if build_status == 'failed':
            raise RuntimeError(progress.get('error') or f'Audience build failed for config {config_id}')
        log.info(
            'Audience build running config_id=%s phase=%s percent=%s',
            config_id,
            progress.get('phase'),
            progress.get('percent'),
        )
        time.sleep(AUDIENCE_POLL_INTERVAL_SECONDS)
    raise TimeoutError(f'Audience build timed out for config {config_id}')


def _start_campaign(campaign):
    campaign_id = campaign['campaign_id']
    round_number = campaign['round_number']
    audience_rebuilt = False
    if campaign.get('audience_needs_rebuild'):
        config_id = campaign.get('audience_config_id')
        if not config_id:
            raise RuntimeError('Audience rebuild requested but audience_config_id is missing')
        status_code, body, response_text = _post_json(
            f'{DJANGO_API}/audience-configs/{config_id}/build/',
            {'round_number': round_number},
            timeout=60,
        )
        if status_code != 202:
            raise RuntimeError(f'Audience build trigger failed HTTP {status_code}: {response_text[:300]}')
        _wait_for_audience_build(config_id)
        audience_rebuilt = True

    if campaign.get('messages_need_build') or audience_rebuilt:
        status_code, body, response_text = _post_json(
            f'{DJANGO_API}/campaigns/{campaign_id}/messages/build/',
            {
                'round_number': round_number,
                'batch_id': f'campaign-{campaign_id}-round-{round_number}',
            },
            timeout=300,
        )
        if status_code not in (200, 201) or body.get('success') is False:
            raise RuntimeError(f'Message build failed HTTP {status_code}: {response_text[:300]}')

    status_code, body, response_text = _post_json(
        f'{DJANGO_API}/campaigns/{campaign_id}/activate/',
        {'build_messages': False},
        timeout=60,
    )
    if status_code not in (200, 201) or body.get('success') is False:
        raise RuntimeError(f'Campaign activation failed HTTP {status_code}: {response_text[:300]}')

    status_code, body, response_text = _post_json(
        f'{DJANGO_API}/campaigns/{campaign_id}/send-now/',
        {'round_number': round_number},
        timeout=60,
    )
    if status_code not in (200, 202) or body.get('success') is False:
        raise RuntimeError(f'Sender start failed HTTP {status_code}: {response_text[:300]}')
    result_status = 'already_running' if 'already running' in str(body.get('message', '')).lower() else 'started'
    return {
        'campaign_id': campaign_id,
        'round_number': round_number,
        'status': result_status,
        'owner_notification_sent': body.get('owner_notification_sent'),
    }


def dispatch(**context):
    due_body = _get_json(f'{DJANGO_API}/schedules/due-now/')
    due = due_body.get('data') or []
    status_body = _get_json(f'{SENDER_API}/sender/status', timeout=30)
    running = status_body.get('data', {}).get('active_campaigns') or []
    running_by_id = {int(row['campaign_id']): row for row in running}

    should_run = {
        int(row['campaign_id']): row
        for row in due
        if row.get('should_run')
    }
    started = []
    stopped = []
    errors = []

    for campaign_id, campaign in should_run.items():
        running_campaign = running_by_id.get(campaign_id)
        if running_campaign:
            running_round = int(running_campaign.get('round_number') or 1)
            if running_round == int(campaign['round_number']):
                continue
            stop_status, stop_body, stop_text = _post_json(
                f'{SENDER_API}/sender/stop',
                {'campaign_id': campaign_id, 'round_number': running_round},
                timeout=30,
            )
            if stop_status not in (200, 404):
                errors.append({
                    'campaign_id': campaign_id,
                    'stage': 'stop_previous_round',
                    'status': stop_status,
                    'body': stop_body,
                })
                log.error('Could not stop previous round campaign_id=%s body=%s', campaign_id, stop_text[:300])
                continue
            stopped.append({'campaign_id': campaign_id, 'round_number': running_round})
        try:
            started.append(_start_campaign(campaign))
        except Exception as exc:
            log.exception('Campaign dispatch failed campaign_id=%s', campaign_id)
            errors.append({'campaign_id': campaign_id, 'stage': 'start', 'error': str(exc)})

    for campaign_id, running_campaign in running_by_id.items():
        if campaign_id in should_run:
            continue
        round_number = int(running_campaign.get('round_number') or 1)
        status_code, body, response_text = _post_json(
            f'{SENDER_API}/sender/stop',
            {'campaign_id': campaign_id, 'round_number': round_number},
            timeout=30,
        )
        if status_code in (200, 404):
            stopped.append({'campaign_id': campaign_id, 'round_number': round_number})
        else:
            log.error('Sender stop failed campaign_id=%s status=%s body=%s', campaign_id, status_code, response_text[:300])
            errors.append({'campaign_id': campaign_id, 'stage': 'stop', 'status': status_code, 'body': body})

    result = {'started': started, 'stopped': stopped, 'errors': errors}
    log.info('Campaign dispatch result: %s', result)
    if context.get('ti'):
        context['ti'].xcom_push(key='started', value=started)
        context['ti'].xcom_push(key='stopped', value=stopped)
        context['ti'].xcom_push(key='errors', value=errors)
    return result


with DAG(
    dag_id='dispatch_campaigns',
    description='Start and stop campaign senders using Django schedules',
    schedule='* * * * *',
    start_date=pendulum.datetime(2026, 1, 1, tz='Africa/Addis_Ababa'),
    catchup=False,
    max_active_runs=1,
    default_args={'retries': 1, 'retry_delay': timedelta(seconds=30)},
    tags=['sms', 'dispatch'],
) as dag:
    PythonOperator(task_id='dispatch_campaigns', python_callable=dispatch)
