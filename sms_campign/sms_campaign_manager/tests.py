import json
import sqlite3
import tempfile

import yaml

from django.test import TestCase
from django.conf import settings
from django.urls import resolve
from rest_framework.test import APIRequestFactory

from .models import (
    Campaign,
    Channel,
    SenderID,
    DatabaseConfig,
    AudienceConfig,
    Language,
    CustomerProfileConfig,
    DeliveryRecord,
    SentRecord,
)
from .serializers import CampaignCreateUpdateSerializer, MessageContentCreateUpdateSerializer
from .services.database_connector import DatabaseConnector
from .views import CampaignDetailView


class CampaignCreateContractTests(TestCase):
    def test_campaign_create_serializer_requires_clean_sender_and_channel_reference(self):
        Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True, is_default=True)

        valid_payload = {
            'name': 'Launch campaign',
            'sender_id': 'SMSINFO',
            'channels': ['SMS'],
        }
        serializer = CampaignCreateUpdateSerializer(data=valid_payload)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        invalid_payload = {
            'name': 'Launch campaign',
            'sender_id': 'UNKNOWN',
            'channels': ['NoSuchChannel'],
        }
        serializer = CampaignCreateUpdateSerializer(data=invalid_payload)
        self.assertFalse(serializer.is_valid())
        self.assertIn('sender_id', serializer.errors)
        self.assertIn('channels', serializer.errors)


class CampaignDeleteContractTests(TestCase):
    def test_soft_delete_requires_draft_campaign_only(self):
        Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True, is_default=True)

        campaign = Campaign.objects.create(
            name='Launch campaign',
            sender_id='SMSINFO',
            channels_id=[1],
            status='paused',
            is_ready_to_execute=False,
        )

        request = APIRequestFactory().delete(f'/api/v1/campaigns/{campaign.id}/')
        view = CampaignDetailView()
        view.request = request
        view.kwargs = {'campaign_id': campaign.id}

        response = view.destroy(request, campaign_id=campaign.id)

        self.assertEqual(response.status_code, 400)
        campaign.refresh_from_db()
        self.assertFalse(campaign.is_deleted)


class DatabaseConnectorGuidanceTests(TestCase):
    def test_non_sqlite_connection_failure_reaches_driver_connection_branch(self):
        config = DatabaseConfig(
            name='postgres-example',
            database_type='postgresql',
            host='localhost',
            port=5432,
            database_name='demo',
            username='postgres',
            ssl_required=False,
        )

        result = DatabaseConnector(config).test_connection()

        self.assertFalse(result['success'])
        self.assertIn('Connection failed:', result['message'])
        self.assertNotIn('driver package', result['message'].lower())

    def test_database_tables_endpoint_returns_clean_api_error_for_connection_failure(self):
        config = DatabaseConfig.objects.create(
            name='postgres-example',
            database_type='postgresql',
            host='localhost',
            port=5432,
            database_name='demo',
            username='postgres',
            password='',
            ssl_required=False,
            is_active=True,
            created_by=None,
        )

        response = self.client.get(f'/api/v1/databases/{config.pk}/tables/')

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['success'], False)
        self.assertIn('Connection failed:', response.json()['message'])

    def test_supported_language_catalogue_is_seeded_for_profile_defaults(self):
        seeded = sorted(Language.objects.filter(code__in=['en', 'am', 'ti', 'om', 'so']).values_list('code', flat=True))
        self.assertEqual(seeded, ['am', 'en', 'om', 'so', 'ti'])

    def test_customer_profile_preview_returns_top_rows_and_schema(self):
        lang = Language.objects.filter(code='en').first()
        if lang is None:
            lang = Language.objects.create(code='en', name='English', is_active=True)
        db_file = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite3')
        db_file.close()
        conn = sqlite3.connect(db_file.name)
        conn.execute('CREATE TABLE language_reference (msisdn TEXT, language TEXT)')
        conn.execute('INSERT INTO language_reference VALUES (?, ?)', ('+25170000001', 'en'))
        conn.execute('INSERT INTO language_reference VALUES (?, ?)', ('+25170000002', 'am'))
        conn.commit()
        conn.close()

        db = DatabaseConfig.objects.create(
            name='sqlite-profile-db',
            database_type='sqlite',
            host='localhost',
            port=1,
            database_name=db_file.name,
            username='',
            password='',
            ssl_required=False,
            is_active=True,
            created_by=None,
        )
        profile = CustomerProfileConfig.objects.create(
            name='profile_sqlite_preview',
            description='preview',
            database_config=db,
            table_name='language_reference',
            msisdn_column='msisdn',
            language_column='language',
            default_language=lang,
            is_active=True,
            created_by=None,
        )

        response = self.client.post(
            f'/api/v1/databases/customer-profiles/{profile.id}/preview/',
            data=json.dumps({'msisdns': ['+25170000001', '+25170000002']}),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('data', payload)
        self.assertIn('schema', payload['data'])
        self.assertIn('top_rows', payload['data'])
        self.assertLessEqual(len(payload['data']['top_rows']['rows']), 10)
        self.assertIn('name', payload['data']['schema'][0])


class AudienceConfigContractTests(TestCase):
    def test_audience_config_model_and_metadata_route_are_registered(self):
        self.assertIsNotNone(AudienceConfig)
        self.assertEqual(resolve('/api/v1/campaigns/1/audience-config/').url_name, 'campaign-audience-config')
        self.assertEqual(resolve('/api/v1/campaigns/1/audience-config/preview/').url_name, 'campaign-audience-config-preview')

    def test_audience_build_route_accepts_audience_id(self):
        self.assertEqual(resolve('/api/v1/audience-configs/1/build/').url_name, 'audience-build')

    def test_message_content_default_language_accepts_language_id_only(self):
        lang = Language.objects.filter(code='en', is_active=True).first()
        self.assertIsNotNone(lang)
        serializer = MessageContentCreateUpdateSerializer(data={
            'en': 'Hello',
            'am': '',
            'ti': '',
            'om': '',
            'so': '',
            'default_language': lang.id,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)


class DeliveryReportCallbackTests(TestCase):
    def test_provider_delivery_report_is_mapped_and_idempotent(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True, is_default=True)
        campaign = Campaign.objects.create(
            name='Delivery callback campaign',
            sender_id='SMSINFO',
            channels_id=[channel.id],
            status='active',
            is_ready_to_execute=True,
        )
        sent_record = SentRecord.objects.create(
            campaign=campaign,
            channel=channel,
            msisdn='+251700000001',
            batch_id='batch-1',
            sent_status='ACCEPTED',
            provider_message_id='smsc-provider-1',
            provider_status='ACCEPTED',
        )
        payload = {
            'provider_message_id': 'smsc-provider-1',
            'receiver': '+251700000001',
            'status': 'DELIVRD',
            'delivered_at': '2026-09-16T10:15:32.123456+00:00',
        }

        first = self.client.post('/api/v1/delivery-reports/callback/', payload, format='json')
        second = self.client.post('/api/v1/delivery-reports/callback/', payload, format='json')

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(DeliveryRecord.objects.filter(sent_record=sent_record).count(), 1)
        record = DeliveryRecord.objects.get(sent_record=sent_record)
        self.assertEqual(record.delivery_status, 'DELIVERED')
        self.assertIsNotNone(record.delivered_at)



class SchemaRegistryTests(TestCase):
    def test_openapi_tags_include_database_section_only(self):
        tags = settings.SPECTACULAR_SETTINGS.get('TAGS', [])
        tag_names = {tag.get('name') for tag in tags}

        self.assertIn('Databases', tag_names)
        self.assertNotIn('Customer Profiles', tag_names)
        self.assertNotIn('Campaign Messages', tag_names)

    def test_database_and_customer_profile_preview_routes_are_registered(self):
        self.assertEqual(resolve('/api/v1/databases/test-params/').url_name, 'database-test-params')
        self.assertEqual(resolve('/api/v1/databases/customer-profiles/1/preview/').url_name, 'customer-profile-preview')

    def test_missing_reference_endpoints_have_canonical_route_names(self):
        self.assertEqual(resolve('/api/v1/sender-ids/').url_name, 'sender-id-list-create')
        self.assertEqual(resolve('/api/v1/smsc-configs/').url_name, 'smsc-config-list-create')

    def test_campaign_message_routes_are_registered(self):
        self.assertEqual(resolve('/api/v1/campaigns/1/messages/build/').url_name, 'campaign-messages-build')
        self.assertEqual(resolve('/api/v1/campaigns/1/messages/').url_name, 'campaign-messages-list')
        self.assertEqual(resolve('/api/v1/campaigns/1/messages/stats/').url_name, 'campaign-messages-stats')
        self.assertEqual(resolve('/api/v1/campaigns/1/messages/clear/').url_name, 'campaign-messages-clear')

    def test_openapi_schema_never_emits_lowercase_database_tag_for_customer_profile_detail(self):
        response = self.client.get('/api/v1/schema/')
        self.assertEqual(response.status_code, 200)
        schema = yaml.safe_load(response.content)
        lowercase_tag_ops = []
        for path, operations in schema.get('paths', {}).items():
            for method, op in operations.items():
                if isinstance(op, dict) and 'databases' in op.get('tags', []):
                    lowercase_tag_ops.append((path, method, op.get('tags')))
        self.assertEqual(lowercase_tag_ops, [])
