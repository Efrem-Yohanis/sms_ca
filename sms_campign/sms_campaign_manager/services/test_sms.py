import time

import requests

from ..models import SMSCConfig


def send_test_to_smsc(sender_id, recipient, channel_code, message_content, test_campaign_id):
    """Send one isolated test message and return its request and outcome details."""
    config = SMSCConfig.objects.filter(is_active=True).order_by('-is_default', 'id').first()
    if config is None:
        return {'config_missing': True}

    normalized_channel = channel_code.strip().lower()
    service_type = {'sms': 'normal', 'flash': 'flash'}.get(normalized_channel, normalized_channel)
    payload = {
        'shortMessage': message_content,
        'messageType': 'TEXT',
        'destAddr': [{'id': recipient}],
        'sourceAddr': {'name': sender_id},
        'servicetag': {'name': f'camp-{test_campaign_id}'},
        'servicetype': {'name': service_type},
    }
    url = config.get_full_send_url()
    method = (config.http_method or 'POST').upper()
    started = time.monotonic()
    http_status = 0
    response_payload = {}
    provider_message_id = ''
    provider_status = ''
    error_message = ''
    accepted = False

    try:
        response = requests.request(
            method,
            url,
            json=payload,
            headers=config.get_headers(),
            timeout=(config.connect_timeout_seconds, config.request_timeout_seconds),
        )
        http_status = response.status_code
        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {'raw_text': response.text[:2000]}

        if http_status != 200:
            error_message = f'SMSC returned HTTP {http_status}: {response.text[:500]}'
            provider_status = 'failed'
        elif isinstance(response_payload, list) and response_payload and isinstance(response_payload[0], dict):
            first_result = response_payload[0]
            provider_message_id = str(first_result.get('messageId') or '')
            provider_status = str(first_result.get('status') or '')
            accepted = provider_status.lower() == 'submitted' and bool(provider_message_id)
            if not accepted:
                error_message = f'SMSC rejected: status={provider_status or "unknown"}'
        else:
            provider_status = 'failed'
            error_message = 'SMSC returned an invalid response payload.'
    except requests.RequestException as exc:
        error_message = str(exc)
    finally:
        duration_ms = max(0, int((time.monotonic() - started) * 1000))

    return {
        'config_missing': False,
        'request_url': url,
        'request_method': method,
        'request_payload': payload,
        'response_payload': response_payload,
        'http_status': http_status,
        'duration_ms': duration_ms,
        'accepted': accepted,
        'provider_message_id': provider_message_id,
        'provider_status': provider_status,
        'error_message': error_message,
    }
