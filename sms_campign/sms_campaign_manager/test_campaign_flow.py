import os
import json
import sqlite3
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from .models import (
    AudienceMember,
    Channel,
    DatabaseConfig,
    DeliveryRecord,
    Language,
    MessageObject,
    Schedule,
    SenderID,
    SentRecord,
    SMSCConfig,
)
from .services.smsc_sender import SmsSenderService


class CampaignDeliveryFlowTests(TestCase):
    """Exercise a bounded version of the campaign-13 configuration end to end."""

    def setUp(self):
        self.source_file = tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False)
        self.source_file.close()
        self.addCleanup(lambda: os.unlink(self.source_file.name) if os.path.exists(self.source_file.name) else None)

        connection = sqlite3.connect(self.source_file.name)
        connection.executescript(
            '''
            CREATE TABLE audience_source (
                phone_number TEXT,
                preferred_lang TEXT,
                active INTEGER
            );
            CREATE TABLE language_reference (
                msisdn TEXT,
                language TEXT
            );
            '''
        )
        connection.executemany(
            'INSERT INTO audience_source VALUES (?, ?, ?)',
            [
                ('+251700000001', 'en', 1),
                ('+251700000002', '', 1),
                ('+251700000003', 'am', 1),
                ('+251700000004', '', 0),
            ],
        )
        connection.executemany(
            'INSERT INTO language_reference VALUES (?, ?)',
            [
                ('+251700000002', 'ti'),
                ('+251700000004', 'om'),
            ],
        )
        connection.commit()
        connection.close()

        self.channel = Channel.objects.create(code='sms', name='SMS', is_active=True)
        self.sender = SenderID.objects.create(
            sender_id='SMSINFO',
            name='SMS Info',
            is_active=True,
            is_default=True,
        )
        self.database = DatabaseConfig.objects.create(
            name='campaign-13-test-source',
            database_type='sqlite',
            database_name=self.source_file.name,
            is_active=True,
        )
        self.default_language = Language.objects.get(code='en')

    @unittest.skipUnless(
        os.getenv('RUN_SMS_SCALE_TEST') == '1',
        'Set RUN_SMS_SCALE_TEST=1 to run the large audience stress test.',
    )
    def test_rebuild_large_audience_recreate_messages_and_send_window(self):
        """Run with SMS_SCALE_COUNT=500000 to exercise the production scale."""
        count = int(os.getenv('SMS_SCALE_COUNT', '500000'))
        connection = sqlite3.connect(self.source_file.name)
        connection.execute('DELETE FROM audience_source')
        connection.execute('DELETE FROM language_reference')
        connection.executemany(
            'INSERT INTO audience_source VALUES (?, ?, ?)',
            (
                (f'+2517{index:08d}', '', 1)
                for index in range(count)
            ),
        )
        connection.commit()
        connection.close()

        campaign_response = self.client.post(
            '/api/v1/campaigns/',
            {
                'name': 'Large audience rebuild test',
                'sender_id': self.sender.sender_id,
                'channels': [self.channel.name],
            },
            format='json',
        )
        self.assertEqual(campaign_response.status_code, 201)
        campaign_id = campaign_response.json()['data']['id']

        audience_response = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/audience/database/',
            {
                'source_database_id': self.database.id,
                'source_table': 'audience_source',
                'source_msisdn_column': 'phone_number',
                'source_language_column': 'preferred_lang',
                'source_filter_clause': 'active = 1',
                'mapper_enabled': False,
                'default_language_id': self.default_language.id,
            },
            format='json',
        )
        self.assertEqual(audience_response.status_code, 201)
        audience_id = audience_response.json()['data']['id']

        build_response = self.client.post(f'/api/v1/audience-configs/{audience_id}/build/')
        self.assertEqual(build_response.status_code, 201)
        self.assertEqual(build_response.json()['data']['valid_count'], count)
        self.assertEqual(AudienceMember.objects.filter(campaign_id=campaign_id).count(), count)

        content_response = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/content/',
            {
                'en': 'Large audience rebuild test.',
                'am': '',
                'ti': '',
                'om': '',
                'so': '',
                'default_language': self.default_language.id,
            },
            format='json',
        )
        self.assertEqual(content_response.status_code, 201)

        schedule_response = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/schedule/',
            data=json.dumps({
                'schedule_type': 'once',
                'start_date': date.today().isoformat(),
                'run_days': [],
                'time_windows': [{'start': '00:00', 'end': '23:59'}],
                'timezone': 'UTC',
            }),
            content_type='application/json',
        )
        self.assertEqual(schedule_response.status_code, 201)

        activate_response = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/activate/',
            {'build_messages': False},
            format='json',
        )
        self.assertEqual(activate_response.status_code, 200)

        first_message_build = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/messages/build/',
            {'round_number': 1},
            format='json',
        )
        self.assertEqual(first_message_build.status_code, 201)
        self.assertEqual(MessageObject.objects.filter(campaign_id=campaign_id).count(), count)

        second_message_build = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/messages/build/',
            {'round_number': 2},
            format='json',
        )
        self.assertEqual(second_message_build.status_code, 201)
        self.assertEqual(second_message_build.json()['data']['cleared'], count)
        self.assertEqual(MessageObject.objects.filter(campaign_id=campaign_id).count(), count)

        smsc = SMSCConfig.objects.create(
            name='large-audience-test-smsc',
            base_url='http://smsc.test',
            send_endpoint='/api/send',
            auth_type='none',
            rate_limit_per_second=100,
            max_retries=1,
        )

        def accepted_response(url, **kwargs):
            payload = kwargs['json']
            response = type('SMSCResponse', (), {})()
            response.status_code = 200
            response.content = b'{"status":"ACCEPTED"}'
            response.json = lambda: {
                'status': 'ACCEPTED',
                'provider_message_id': f"provider-{payload['message_id']}",
            }
            return response

        with patch(
            'sms_campaign_manager.services.smsc_sender.requests.post',
            side_effect=accepted_response,
        ):
            send_report = SmsSenderService(smsc).run_once()

        send_window = min(count, 100)
        self.assertEqual(send_report['sent'], send_window)
        sent_records = list(SentRecord.objects.filter(campaign_id=campaign_id))
        self.assertEqual(len(sent_records), send_window)

        for sent_record in sent_records:
            callback_response = self.client.post(
                '/api/v1/delivery-reports/callback/',
                {
                    'provider_message_id': sent_record.provider_message_id,
                    'receiver': sent_record.msisdn,
                    'status': 'DELIVRD',
                    'delivered_at': timezone.now().isoformat(),
                },
                format='json',
            )
            self.assertEqual(callback_response.status_code, 200)

        self.assertEqual(
            DeliveryRecord.objects.filter(
                campaign_id=campaign_id,
                delivery_status='DELIVERED',
            ).count(),
            send_window,
        )

    def test_campaign_setup_build_send_and_delivery_callback(self):
        campaign_response = self.client.post(
            '/api/v1/campaigns/',
            {
                'name': 'Campaign 13 flow test',
                'sender_id': self.sender.sender_id,
                'channels': [self.channel.name],
            },
            format='json',
        )
        self.assertEqual(campaign_response.status_code, 201)
        campaign_id = campaign_response.json()['data']['id']

        audience_response = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/audience/database/',
            {
                'source_database_id': self.database.id,
                'source_table': 'audience_source',
                'source_msisdn_column': 'phone_number',
                'source_language_column': 'preferred_lang',
                'source_filter_clause': 'active = 1',
                'mapper_enabled': True,
                'mapper_database_id': self.database.id,
                'mapper_table': 'language_reference',
                'mapper_msisdn_column': 'msisdn',
                'mapper_language_column': 'language',
                'mapper_join_type': 'LEFT',
                'default_language_id': self.default_language.id,
            },
            format='json',
        )
        self.assertEqual(audience_response.status_code, 201)
        audience_id = audience_response.json()['data']['id']

        build_response = self.client.post(f'/api/v1/audience-configs/{audience_id}/build/')
        self.assertEqual(build_response.status_code, 201)
        self.assertEqual(build_response.json()['data']['valid_count'], 3)
        self.assertEqual(AudienceMember.objects.filter(campaign_id=campaign_id).count(), 3)

        content_response = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/content/',
            {
                'en': 'Hello from the campaign flow test.',
                'am': 'የዘመቻ ፈተና ሰላምታ።',
                'ti': 'ሰላም ካብ ፈተና ወፍሪ።',
                'om': '',
                'so': '',
                'default_language': self.default_language.id,
            },
            format='json',
        )
        self.assertEqual(content_response.status_code, 201)

        schedule_payload = {
            'schedule_type': 'once',
            'start_date': date.today().isoformat(),
            'run_days': [],
            'time_windows': [{'start': '00:00', 'end': '23:59'}],
            'timezone': 'UTC',
        }
        schedule_response = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/schedule/',
            data=json.dumps(schedule_payload),
            content_type='application/json',
        )
        self.assertEqual(schedule_response.status_code, 201, schedule_response.json())
        self.assertTrue(
            Schedule.objects.filter(
                campaign_id=campaign_id,
                start_date=date.today(),
                is_active=True,
            ).exists()
        )

        readiness_response = self.client.post(f'/api/v1/campaigns/{campaign_id}/validate/')
        self.assertEqual(readiness_response.status_code, 200)
        self.assertTrue(readiness_response.json()['data']['is_ready'])

        activate_response = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/activate/',
            {'build_messages': False},
            format='json',
        )
        self.assertEqual(activate_response.status_code, 200)

        message_build_response = self.client.post(
            f'/api/v1/campaigns/{campaign_id}/messages/build/',
            {'round_number': 1},
            format='json',
        )
        self.assertEqual(message_build_response.status_code, 201, message_build_response.json())
        self.assertEqual(message_build_response.json()['data']['built'], 3)
        self.assertEqual(MessageObject.objects.filter(campaign_id=campaign_id).count(), 3)

        smsc = SMSCConfig.objects.create(
            name='campaign-flow-test-smsc',
            base_url='http://smsc.test',
            send_endpoint='/api/send',
            auth_type='none',
            rate_limit_per_second=10,
            max_retries=1,
        )

        def accepted_response(url, **kwargs):
            payload = kwargs['json']
            response = type('SMSCResponse', (), {})()
            response.status_code = 200
            response.content = b'{"status":"ACCEPTED"}'
            response.json = lambda: {
                'status': 'ACCEPTED',
                'provider_message_id': f"provider-{payload['message_id']}",
            }
            return response

        with patch(
            'sms_campaign_manager.services.smsc_sender.requests.post',
            side_effect=accepted_response,
        ):
            send_report = SmsSenderService(smsc).run_once()

        self.assertEqual(send_report['sent'], 3)
        self.assertEqual(SentRecord.objects.filter(campaign_id=campaign_id).count(), 3)
        self.assertEqual(MessageObject.objects.filter(campaign_id=campaign_id).count(), 0)

        sent_records = list(SentRecord.objects.filter(campaign_id=campaign_id))
        for sent_record in sent_records:
            callback_response = self.client.post(
                '/api/v1/delivery-reports/callback/',
                {
                    'provider_message_id': sent_record.provider_message_id,
                    'receiver': sent_record.msisdn,
                    'status': 'DELIVRD',
                    'delivered_at': timezone.now().isoformat(),
                },
                format='json',
            )
            self.assertEqual(callback_response.status_code, 200)

        self.assertEqual(
            DeliveryRecord.objects.filter(
                campaign_id=campaign_id,
                delivery_status='DELIVERED',
            ).count(),
            3,
        )
