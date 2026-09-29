import requests
from django.test import TestCase
from django.urls import resolve
from unittest.mock import patch

from .models import (
    Channel,
    MessageObject,
    SenderID,
    SMSCConfig,
    TestMessage,
)


class FakeSMSCResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self.payload = payload
        self.text = text

    def json(self):
        return self.payload


class TestSmsApiTests(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(code='sms', name='SMS')
        self.sender_id = SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_default=True)
        self.url = '/api/v1/test-sms/'
        self.payload = {
            'sender_id': 'SMSINFO',
            'recipient': '251799120001',
            'channel_code': 'sms',
            'message_content': 'Standalone test message.',
        }

    def create_smsc_config(self):
        return SMSCConfig.objects.create(
            name='Test SMSC',
            base_url='https://smsc.example.com',
            send_endpoint='/onion/swift/duos',
            auth_type='none',
            is_default=True,
        )

    @patch('sms_campaign_manager.services.test_sms.requests.request')
    def test_create_sends_to_smsc_and_persists_only_test_record(self, request):
        self.create_smsc_config()
        request.return_value = FakeSMSCResponse(payload=[{
            'messageId': 'provider-42',
            'msisdn': '251799120001',
            'status': 'submitted',
        }])

        response = self.client.post(self.url, self.payload, format='json')

        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()['data']
        self.assertTrue(body['accepted'])
        self.assertEqual(body['provider_message_id'], 'provider-42')
        self.assertEqual(body['request_url'], 'https://smsc.example.com/onion/swift/duos')
        self.assertEqual(body['request_method'], 'POST')
        self.assertEqual(body['request_payload']['destAddr'], [{'id': '251799120001'}])
        self.assertEqual(body['request_payload']['servicetag'], {'name': 'camp-9999'})
        self.assertEqual(body['request_payload']['servicetype'], {'name': 'normal'})
        self.assertEqual(TestMessage.objects.count(), 1)
        self.assertEqual(MessageObject.objects.count(), 0)
        request.assert_called_once()

    @patch('sms_campaign_manager.services.test_sms.requests.request')
    def test_smsc_rejection_is_recorded_with_created_response(self, request):
        self.create_smsc_config()
        request.return_value = FakeSMSCResponse(payload=[{
            'messageId': '',
            'msisdn': '251799120001',
            'status': 'failed',
        }])

        response = self.client.post(self.url, self.payload, format='json')

        self.assertEqual(response.status_code, 201, response.content)
        self.assertTrue(response.json()['success'])
        self.assertFalse(response.json()['data']['accepted'])
        self.assertEqual(response.json()['data']['provider_status'], 'failed')
        self.assertIn('SMSC rejected', response.json()['data']['error_message'])
        self.assertEqual(TestMessage.objects.count(), 1)

    @patch('sms_campaign_manager.services.test_sms.requests.request', side_effect=requests.Timeout('timed out'))
    def test_network_failure_is_saved_as_a_test_result(self, request):
        self.create_smsc_config()

        response = self.client.post(self.url, self.payload, format='json')

        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(response.json()['data']['accepted'])
        self.assertEqual(response.json()['data']['http_status'], 0)
        self.assertEqual(response.json()['data']['response_payload'], {})
        self.assertIn('timed out', response.json()['data']['error_message'])
        self.assertEqual(TestMessage.objects.count(), 1)

    def test_missing_smsc_config_returns_502_without_creating_a_row(self):
        response = self.client.post(self.url, self.payload, format='json')
        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.json()['success'])
        self.assertIn('smsc_config', response.json()['errors'])
        self.assertEqual(TestMessage.objects.count(), 0)

    def test_validation_checks_active_references_and_digits_only_recipient(self):
        invalid_recipient = {**self.payload, 'recipient': '+251799120001'}
        response = self.client.post(self.url, invalid_recipient, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('recipient', response.json()['errors'])

        inactive_sender = SenderID.objects.create(sender_id='OLDINFO', name='Old Info', is_active=False)
        invalid_sender = {**self.payload, 'sender_id': inactive_sender.sender_id}
        response = self.client.post(self.url, invalid_sender, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('active Sender ID', response.json()['errors']['sender_id'][0])

        inactive_channel = Channel.objects.create(code='flash', name='Flash SMS', is_active=False)
        invalid_channel = {**self.payload, 'channel_code': inactive_channel.code}
        response = self.client.post(self.url, invalid_channel, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('channel_code', response.json()['errors'])

    @patch('sms_campaign_manager.services.test_sms.requests.request')
    def test_resend_creates_a_new_test_message_without_modifying_original(self, request):
        self.create_smsc_config()
        original = TestMessage.objects.create(
            sender_id='SMSINFO',
            recipient='251799120001',
            channel_code='sms',
            message_content='Original message',
            provider_message_id='old-provider-id',
            provider_status='submitted',
            accepted=True,
            request_payload={'shortMessage': 'Original message'},
        )
        request.return_value = FakeSMSCResponse(payload=[{
            'messageId': 'new-provider-id',
            'msisdn': '251799120001',
            'status': 'submitted',
        }])

        response = self.client.post(f'{self.url}{original.id}/resend/', {}, format='json')

        self.assertEqual(response.status_code, 201, response.content)
        self.assertNotEqual(response.json()['data']['id'], original.id)
        self.assertEqual(response.json()['data']['provider_message_id'], 'new-provider-id')
        original.refresh_from_db()
        self.assertEqual(original.provider_message_id, 'old-provider-id')
        self.assertEqual(TestMessage.objects.count(), 2)

    def test_list_search_limit_detail_delete_and_route_names(self):
        rows = [
            TestMessage.objects.create(
                sender_id='SMSINFO',
                recipient=f'2517991200{index:02d}',
                channel_code='sms',
                message_content=f'Test phrase {index}',
            )
            for index in range(12)
        ]
        list_response = self.client.get(f'{self.url}?limit=10&offset=0&search=phrase&accepted=false')
        self.assertEqual(list_response.status_code, 200, list_response.content)
        self.assertEqual(list_response.json()['count'], 12)
        self.assertEqual(len(list_response.json()['results']), 10)
        self.assertNotIn('request_payload', list_response.json()['results'][0])

        detail_response = self.client.get(f'{self.url}{rows[-1].id}/')
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn('request_payload', detail_response.json()['data'])

        delete_response = self.client.delete(f'{self.url}{rows[-1].id}/')
        self.assertEqual(delete_response.status_code, 204)
        self.assertFalse(TestMessage.objects.filter(pk=rows[-1].id).exists())
        self.assertEqual(resolve(self.url).url_name, 'test-sms-list-create')
        self.assertEqual(resolve(f'{self.url}1/').url_name, 'test-sms-detail')
        self.assertEqual(resolve(f'{self.url}1/resend/').url_name, 'test-sms-resend')

    def test_sender_and_channel_lists_support_active_filter(self):
        Channel.objects.create(code='flash', name='Flash SMS', is_active=False)
        SenderID.objects.create(sender_id='OLDINFO', name='Old Info', is_active=False)

        channels = self.client.get('/api/v1/channels/?is_active=true')
        sender_ids = self.client.get('/api/v1/sender-ids/?is_active=true')

        self.assertEqual(channels.status_code, 200)
        self.assertEqual(sender_ids.status_code, 200)
        channel_body = channels.json()
        sender_body = sender_ids.json()
        channel_rows = channel_body if isinstance(channel_body, list) else channel_body['results']
        sender_rows = sender_body if isinstance(sender_body, list) else sender_body['results']
        self.assertTrue(all(row['is_active'] for row in channel_rows))
        self.assertTrue(all(row['is_active'] for row in sender_rows))
