"""Send report subscriptions that Django reports as due."""

from datetime import timedelta
import logging
import os

import pendulum
import requests
from airflow import DAG
from airflow.operators.python import PythonOperator


log = logging.getLogger(__name__)
DJANGO_API = os.getenv('AIRFLOW_DJANGO_API', 'http://camaping-manager-backend-app:8000/api/v1').rstrip('/')


def dispatch(**context):
    response = requests.get(f'{DJANGO_API}/report-subscriptions/due-now/', timeout=30)
    response.raise_for_status()
    body = response.json()
    if body.get('success') is False:
        raise RuntimeError(body.get('error') or body.get('detail') or 'Report due-now request failed')

    sent = []
    skipped = []
    failed = []
    for subscription in body.get('data') or []:
        subscription_id = subscription['id']
        try:
            response = requests.post(
                f'{DJANGO_API}/report-subscriptions/{subscription_id}/send-now/',
                json={'scheduled': True},
                timeout=180,
            )
            result = response.json()
            if response.status_code == 200 and result.get('success') and result.get('skipped'):
                skipped.append({
                    'subscription_id': subscription_id,
                    'name': subscription.get('name'),
                    'reason': result.get('message'),
                    'next_run_at': result.get('next_run_at'),
                })
            elif response.status_code == 200 and result.get('success'):
                sent.append({
                    'subscription_id': subscription_id,
                    'name': subscription.get('name'),
                    'log_id': result.get('log_id'),
                })
            else:
                failure = {
                    'subscription_id': subscription_id,
                    'status': response.status_code,
                    'error': result.get('error') or response.text[:300],
                }
                failed.append(failure)
                log.error('Scheduled report failed: %s', failure)
        except Exception as exc:
            failure = {'subscription_id': subscription_id, 'error': str(exc)}
            failed.append(failure)
            log.exception('Scheduled report request failed subscription_id=%s', subscription_id)

    result = {'sent': sent, 'skipped': skipped, 'failed': failed}
    log.info('Report dispatch result: %s', result)
    if context.get('ti'):
        context['ti'].xcom_push(key='sent', value=sent)
        context['ti'].xcom_push(key='skipped', value=skipped)
        context['ti'].xcom_push(key='failed', value=failed)
    return result


with DAG(
    dag_id='dispatch_reports',
    description='Send scheduled email reports through Django',
    schedule='* * * * *',
    start_date=pendulum.datetime(2026, 1, 1, tz='Africa/Addis_Ababa'),
    catchup=False,
    max_active_runs=1,
    default_args={'retries': 1, 'retry_delay': timedelta(seconds=30)},
    tags=['sms', 'reports'],
) as dag:
    PythonOperator(task_id='dispatch_reports', python_callable=dispatch)
