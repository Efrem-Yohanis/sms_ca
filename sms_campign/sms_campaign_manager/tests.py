import json
import os
import sqlite3
import tempfile
from datetime import date, timedelta
from unittest.mock import Mock, patch

from django.utils import timezone
from django.contrib.auth import get_user_model

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
    AudienceMember,
    AudienceBuildJob,
    Language,
    CustomerProfileConfig,
    DeliveryRecord,
    Audience,
    EmailConfig,
    EmailReport,
    ReportDeliveryLog,
    ReportSubscription,
    MessageContent,
    MessageObject,
    Schedule,
    SMSCConfig,
    SentRecord,
    SuccessSent,
    FailedSent,
    SuccessDelivery,
    FailedDelivery,
)
from .serializers import (
    CampaignCreateUpdateSerializer,
    MessageContentApiInputSerializer,
    MessageContentCreateUpdateSerializer,
)
from .services.database_connector import DatabaseConnector
from .services.audience_service import AudienceBuildService
from .services.campaign_actions import CampaignActionsService
from .services.campaign_activation_email import send_campaign_activation_email
from .services.message_builder import MessageBuilder
from .services.smsc_sender import SmsSenderService
from sms_status_updater.app import process_delivery_batch, process_send_batch
from .views import CampaignDetailView


class AuthenticationContractTests(TestCase):
    def test_registration_creates_standard_user_that_can_log_in(self):
        registration_response = self.client.post(
            '/api/v1/auth/register/',
            {
                'username': 'new-campaign-user',
                'email': 'new-user@example.com',
                'password': '9$Prism-Copper-71-Cloud',
                'is_staff': True,
                'is_superuser': True,
            },
            format='json',
        )

        self.assertEqual(registration_response.status_code, 201, registration_response.content)
        self.assertNotIn('password', registration_response.json())

        user = get_user_model().objects.get(username='new-campaign-user')
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)

        login_response = self.client.post(
            '/api/v1/auth/login/',
            {'username': 'new-campaign-user', 'password': '9$Prism-Copper-71-Cloud'},
            format='json',
        )
        self.assertEqual(login_response.status_code, 200, login_response.content)
        self.assertTrue(login_response.json()['access'])

    def test_existing_django_user_can_obtain_and_refresh_jwt(self):
        user_model = get_user_model()
        user_model.objects.create_user(username='campaign-user', password='Strong-pass-123')

        login_response = self.client.post(
            '/api/v1/auth/login/',
            {'username': 'campaign-user', 'password': 'Strong-pass-123'},
            format='json',
        )

        self.assertEqual(login_response.status_code, 200, login_response.content)
        token_data = login_response.json()
        self.assertTrue(token_data['access'])
        self.assertTrue(token_data['refresh'])

        refresh_response = self.client.post(
            '/api/v1/auth/refresh/',
            {'refresh': token_data['refresh']},
            format='json',
        )
        self.assertEqual(refresh_response.status_code, 200, refresh_response.content)
        self.assertTrue(refresh_response.json()['access'])


class CampaignAudienceInsertionTests(TestCase):
    def test_campaign_audience_post_persists_manual_recipients(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        sender = SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True, is_default=True)
        campaign = Campaign.objects.create(
            name='Audience insertion campaign',
            sender_id=sender.sender_id,
            channels_id=[channel.id],
            status='draft',
        )

        response = self.client.post(
            f'/api/v1/campaigns/{campaign.id}/audience/',
            {
                'msisdns': ['+251711234567'],
                'languages': ['am'],
                'default_language': 'en',
                'source_type': 'file_import',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        audience = AudienceMember.objects.get(campaign=campaign, msisdn='+251711234567')
        self.assertEqual(audience.language.code, 'am')
        self.assertEqual(AudienceConfig.objects.get(campaign=campaign).source_type, 'file_import')

        list_response = self.client.get('/api/v1/audiences/')
        self.assertEqual(list_response.status_code, 200, list_response.content)
        listed_audience = list_response.json()['results'][0]
        self.assertEqual(listed_audience['id'], campaign.id)
        self.assertEqual(listed_audience['campaign_info']['name'], campaign.name)
        self.assertEqual(listed_audience['total_count'], 1)

        summary_response = self.client.get('/api/v1/audiences/summary/')
        self.assertEqual(summary_response.status_code, 200, summary_response.content)
        self.assertEqual(summary_response.json()['total_audiences'], 1)
        self.assertEqual(summary_response.json()['total_recipients'], 1)

        detail_response = self.client.get(f'/api/v1/audiences/{campaign.id}/')
        self.assertEqual(detail_response.status_code, 200, detail_response.content)
        self.assertEqual(detail_response.json()['recipients_preview'][0]['msisdn'], '+251711234567')

        preview_response = self.client.get(f'/api/v1/audiences/{campaign.id}/recipients_preview/')
        self.assertEqual(preview_response.status_code, 200, preview_response.content)
        self.assertEqual(preview_response.json()['preview'][0]['lang'], 'am')

        statistics_response = self.client.get(f'/api/v1/audiences/{campaign.id}/statistics/')
        self.assertEqual(statistics_response.status_code, 200, statistics_response.content)
        self.assertEqual(statistics_response.json()['valid_count'], 1)

        campaign_detail_response = self.client.get(f'/api/v1/campaigns/{campaign.id}/')
        self.assertEqual(campaign_detail_response.status_code, 200, campaign_detail_response.content)
        linked_audience = campaign_detail_response.json()['data']['audience']
        self.assertEqual(linked_audience['total_count'], 1)
        self.assertEqual(linked_audience['valid_count'], 1)
        self.assertEqual(linked_audience['source_type'], 'file_import')


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

    def test_campaign_create_resolves_channel_codes_sent_by_wizard(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True)
        serializer = CampaignCreateUpdateSerializer(data={
            'name': 'Wizard channel code campaign',
            'sender_id': 'SMSINFO',
            'channels': ['sms'],
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        campaign = serializer.save()
        self.assertEqual(campaign.channels_id, [channel.id])

    def test_campaign_owner_emails_are_normalized_and_validated(self):
        Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True, is_default=True)

        serializer = CampaignCreateUpdateSerializer(data={
            'name': 'Owner notification campaign',
            'sender_id': 'SMSINFO',
            'channels': ['SMS'],
            'owner_emails': [' Owner@Example.com ', 'owner@example.com'],
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['owner_emails'], ['owner@example.com'])

        invalid = CampaignCreateUpdateSerializer(data={
            'name': 'Owner notification campaign',
            'sender_id': 'SMSINFO',
            'channels': ['SMS'],
            'owner_emails': ['not-an-email'],
        })
        self.assertFalse(invalid.is_valid())
        self.assertIn('owner_emails', invalid.errors)

    def test_campaign_create_and_draft_update_persist_owner_emails(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True)
        payload = {
            'name': 'Owner email persistence',
            'sender_id': 'SMSINFO',
            'channels': ['SMS'],
            'owner_emails': ['Owner@Example.com'],
        }

        create = CampaignCreateUpdateSerializer(data=payload)
        self.assertTrue(create.is_valid(), create.errors)
        campaign = create.save()
        self.assertEqual(campaign.owner_emails, ['owner@example.com'])

        update = CampaignCreateUpdateSerializer(
            campaign,
            data={'name': campaign.name, 'sender_id': campaign.sender_id,
                  'channels': ['SMS'], 'owner_emails': ['next@example.com']},
            partial=True,
        )
        self.assertTrue(update.is_valid(), update.errors)
        campaign = update.save()
        self.assertEqual(campaign.owner_emails, ['next@example.com'])

    def test_campaign_api_create_returns_persisted_owner_emails(self):
        Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True)

        create_response = self.client.post(
            '/api/v1/campaigns/',
            {
                'name': 'Campaign API owner email',
                'sender_id': 'SMSINFO',
                'channels': ['SMS'],
                'owner_emails': [' Owner@Example.com ', 'owner@example.com'],
            },
            format='json',
        )

        self.assertEqual(create_response.status_code, 201, create_response.content)
        campaign_id = create_response.json()['data']['id']
        self.assertEqual(create_response.json()['data']['owner_emails'], ['owner@example.com'])

        detail_response = self.client.get(f'/api/v1/campaigns/{campaign_id}/')

        self.assertEqual(detail_response.status_code, 200, detail_response.content)
        self.assertEqual(detail_response.json()['data']['owner_emails'], ['owner@example.com'])


class MessageContentApiContractTests(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True)
        self.language = Language.objects.filter(code='en').first() or Language.objects.create(
            code='en', name='English',
        )
        self.campaign = Campaign.objects.create(
            name='Message API campaign',
            sender_id='SMSINFO',
            channels_id=[self.channel.id],
            status='draft',
        )
        self.message = MessageContent.objects.create(
            campaign=self.campaign,
            en='Hello {name}',
            default_language=self.language,
        )

    def test_message_list_detail_languages_and_update_contract(self):
        list_response = self.client.get('/api/v1/message-content/')
        self.assertEqual(list_response.status_code, 200, list_response.content)
        self.assertEqual(list_response.json()['count'], 1)
        item = list_response.json()['results'][0]
        self.assertEqual(item['campaign'], self.campaign.id)
        self.assertEqual(item['content']['en'], 'Hello {name}')
        self.assertEqual(item['default_language'], 'en')

        detail_response = self.client.get(f'/api/v1/message-content/{self.message.id}/')
        self.assertEqual(detail_response.status_code, 200, detail_response.content)
        self.assertEqual(detail_response.json()['id'], self.message.id)

    def test_standalone_message_create_links_content_to_selected_campaign(self):
        campaign = Campaign.objects.create(
            name='Standalone message campaign',
            sender_id='SMSINFO',
            channels_id=[self.channel.id],
            status='draft',
        )
        input_serializer = MessageContentApiInputSerializer(data={
            'campaign': campaign.id,
            'content': {'en': 'Standalone hello'},
            'default_language': 'en',
        })
        self.assertTrue(input_serializer.is_valid(), input_serializer.errors)
        input_payload = input_serializer.validated_data
        model_serializer = MessageContentCreateUpdateSerializer(data={
            **input_payload['content'],
            'default_language': input_payload['default_language'].pk,
        })
        self.assertTrue(model_serializer.is_valid(), model_serializer.errors)

        with patch(
            'sms_campaign_manager.views.MessageContentCreateUpdateSerializer',
            side_effect=MessageContentCreateUpdateSerializer,
        ) as content_serializer_factory:
            response = self.client.post(
                '/api/v1/message-content/',
                {
                    'campaign': campaign.id,
                    'content': {'en': 'Standalone hello'},
                    'default_language': 'en',
                },
                format='json',
            )
        self.assertEqual(
            content_serializer_factory.call_args.kwargs['data'],
            {'en': 'Standalone hello', 'default_language': self.language.id},
        )

        self.assertEqual(response.status_code, 201, response.content)
        message = MessageContent.objects.get(campaign=campaign)
        self.assertEqual(response.json()['campaign'], campaign.id)

        campaign_detail = self.client.get(f'/api/v1/campaigns/{campaign.id}/')
        self.assertEqual(campaign_detail.status_code, 200, campaign_detail.content)
        linked_content = campaign_detail.json()['data']['message_content']
        self.assertEqual(linked_content['id'], message.id)
        self.assertEqual(linked_content['content']['en'], 'Standalone hello')

        languages_response = self.client.get('/api/v1/message-content/languages/')
        self.assertEqual(languages_response.status_code, 200, languages_response.content)
        self.assertIn('en', [item['code'] for item in languages_response.json()['data']])

        update_response = self.client.patch(
            f'/api/v1/message-content/{self.message.id}/',
            json.dumps({'content': {'en': 'Updated {name}'}, 'default_language': 'en'}),
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200, update_response.content)
        self.assertEqual(update_response.json()['content']['en'], 'Updated {name}')


class CampaignDeleteContractTests(TestCase):
    def test_soft_delete_is_available_for_non_draft_campaigns(self):
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

        self.assertEqual(response.status_code, 200)
        campaign.refresh_from_db()
        self.assertTrue(campaign.is_deleted)


class EmailConfigAndReportTests(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(code='sms', name='SMS')
        self.sender = SenderID.objects.create(
            sender_id='SMSINFO', name='SMS Info', is_active=True, is_default=True,
        )
        self.campaign = Campaign.objects.create(
            name='Report campaign',
            sender_id=self.sender.sender_id,
            owner_emails=['ops@example.com'],
            channels_id=[self.channel.id],
            status='draft',
        )

    @patch('sms_campaign_manager.services.email_reports.EmailMultiAlternatives.send', return_value=1)
    def test_email_config_can_be_created_and_campaign_report_is_sent(self, mock_send):
        config_response = self.client.post(
            '/api/v1/email-config/',
            {
                'name': 'Primary SMTP',
                'host': 'smtp.example.com',
                'port': 587,
                'username': 'no-reply@example.com',
                'password': 'secret',
                'use_tls': True,
                'default_from_email': 'no-reply@example.com',
                'is_default': True,
            },
            format='json',
        )

        self.assertEqual(config_response.status_code, 201, config_response.content)
        self.assertTrue(EmailConfig.objects.filter(name='Primary SMTP').exists())
        selected_config = EmailConfig.objects.create(
            name='Campaign SMTP',
            host='campaign-smtp.example.com',
            port=2525,
            default_from_email='campaigns@example.com',
        )

        report_response = self.client.post(
            f'/api/v1/campaigns/{self.campaign.id}/reports/email/',
            {
                'email_config_id': selected_config.id,
                'subject': 'Custom report subject',
            },
            format='json',
        )

        self.assertEqual(report_response.status_code, 201, report_response.content)
        self.assertTrue(report_response.json()['success'])
        delivery = ReportDeliveryLog.objects.get(campaign=self.campaign)
        self.assertEqual(delivery.recipients, ['ops@example.com'])
        self.assertEqual(delivery.email_config_id, selected_config.id)
        self.assertEqual(delivery.subject, 'Custom report subject')
        self.assertIn('<!doctype html>', delivery.content.lower())
        self.assertIn('Report overview', delivery.content)
        self.assertIn('Campaign details', delivery.content)
        self.assertIn('Successful deliveries', delivery.content)
        self.assertIn('Total success sent', delivery.content)
        self.assertIn('Total failed sent', delivery.content)
        self.assertIn('Total success delivery', delivery.content)
        self.assertIn('Total failed delivery', delivery.content)
        self.assertEqual(report_response.json()['data']['id'], delivery.id)
        self.assertEqual(report_response.json()['data']['email_config_id'], selected_config.id)
        self.assertEqual(delivery.status, 'sent')
        self.assertEqual(EmailReport.objects.filter(campaign=self.campaign).count(), 1)
        mock_send.assert_called_once()

    @patch('sms_campaign_manager.views.EmailMessage')
    def test_saved_email_config_test_sends_message_and_records_result(self, mock_email_message):
        config = EmailConfig.objects.create(
            name='Test SMTP',
            host='smtp.example.com',
            port=587,
            default_from_email='no-reply@example.com',
        )

        response = self.client.post(
            f'/api/v1/email-config/{config.id}/test/',
            {'test_email': 'verify@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()['success'])
        mock_email_message.assert_called_once()
        self.assertEqual(mock_email_message.call_args.kwargs['to'], ['verify@example.com'])
        mock_email_message.return_value.send.assert_called_once_with(fail_silently=False)
        config.refresh_from_db()
        self.assertEqual(config.last_test_status, 'success')
        self.assertIn('verify@example.com', config.last_test_message)

    def test_report_subscription_crud_accepts_selected_recipients(self):
        create_response = self.client.post(
            '/api/v1/report-subscriptions/',
            {
                'campaign': self.campaign.id,
                'recipients': [' Reports@Example.com ', 'reports@example.com'],
                'frequency': 'weekly',
                'format': 'csv',
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        subscription_id = create_response.json()['id']
        self.assertEqual(create_response.json()['recipients'], ['reports@example.com'])
        self.assertTrue(ReportSubscription.objects.filter(pk=subscription_id).exists())

        patch_response = self.client.patch(
            f'/api/v1/report-subscriptions/{subscription_id}/',
            json.dumps({'frequency': 'monthly', 'is_active': False}),
            content_type='application/json',
        )
        self.assertEqual(patch_response.status_code, 200, patch_response.content)
        self.assertEqual(patch_response.json()['frequency'], 'monthly')
        self.assertFalse(patch_response.json()['is_active'])

        delete_response = self.client.delete(f'/api/v1/report-subscriptions/{subscription_id}/')
        self.assertEqual(delete_response.status_code, 204)

    def test_campaign_progress_report_crud(self):
        create_response = self.client.post(
            '/api/v1/email-reports/',
            {
                'name': 'Operations progress',
                'campaigns': [self.campaign.id],
                'recipients': ['reports@example.com'],
                'include_campaign_owners': True,
                'frequency': '10_minutes',
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        report_id = create_response.json()['id']
        self.assertEqual(self.client.get('/api/v1/email-reports/').status_code, 200)

        update_response = self.client.patch(
            f'/api/v1/email-reports/{report_id}/',
            json.dumps({'frequency': 'hourly', 'is_active': False}),
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200, update_response.content)
        self.assertEqual(update_response.json()['frequency'], 'hourly')

        delete_response = self.client.delete(f'/api/v1/email-reports/{report_id}/')
        self.assertEqual(delete_response.status_code, 204)


class CampaignWorkflowStepTests(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(code='sms', name='SMS')
        self.sender = SenderID.objects.create(
            sender_id='SMSINFO', name='SMS Info', is_active=True, is_default=True,
        )
        self.language = Language.objects.get(code='en')

    def create_campaign(self):
        return Campaign.objects.create(
            name='Workflow campaign',
            sender_id=self.sender.sender_id,
            owner_emails=['owner@example.com'],
            channels_id=[self.channel.id],
            status='draft',
        )

    def test_step_1_create_campaign(self):
        campaign = self.create_campaign()

        self.assertEqual(campaign.status, 'draft')
        self.assertEqual(campaign.owner_emails, ['owner@example.com'])

    def test_campaign_list_returns_table_fields_and_message_progress(self):
        campaign = self.create_campaign()
        Schedule.objects.create(
            campaign=campaign,
            schedule_type='once',
            start_date=date.today() + timedelta(days=1),
            time_windows=[{'start': '09:00', 'end': '17:00'}],
        )
        MessageContent.objects.create(
            campaign=campaign,
            en='Hello customer',
            default_language=self.language,
        )
        Audience.objects.create(
            campaign=campaign,
            msisdn='+251700000001',
            language=self.language,
            sequence_number=1,
        )
        MessageObject.objects.create(
            campaign=campaign,
            message_id='campaign-list-message-1',
            recipient='+251700000001',
            sender_id=campaign.sender_id,
            message_content='Hello customer',
        )

        response = self.client.get('/api/v1/campaigns/?page=1&page_size=20')

        self.assertEqual(response.status_code, 200, response.content)
        listed = response.json()['results'][0]
        self.assertEqual(listed['channels'], ['SMS'])
        self.assertEqual(listed['execution_status'], 'PENDING')
        self.assertEqual(listed['execution_status_display'], 'Pending')
        self.assertEqual(listed['total_messages'], 1)
        self.assertEqual(listed['total_processed'], 0)
        self.assertEqual(listed['progress_percent'], 0)
        self.assertTrue(listed['has_schedule'])
        self.assertTrue(listed['has_audience'])
        self.assertTrue(listed['has_content'])

    def test_campaign_progress_and_batch_endpoints_aggregate_message_states(self):
        campaign = self.create_campaign()
        MessageObject.objects.create(
            campaign=campaign,
            message_id='progress-message-accepted',
            recipient='+251700000001',
            sender_id=campaign.sender_id,
            message_content='Accepted message',
            sent_status='ACCEPTED',
            delivery_status='DELIVERED',
            batch_id='progress-batch-1',
        )
        MessageObject.objects.create(
            campaign=campaign,
            message_id='progress-message-pending',
            recipient='+251700000002',
            sender_id=campaign.sender_id,
            message_content='Pending message',
            sent_status='PENDING',
            delivery_status='PENDING',
            batch_id='progress-batch-1',
        )

        progress_response = self.client.get(f'/api/v1/campaigns/{campaign.id}/progress/')
        batches_response = self.client.get(f'/api/v1/campaigns/{campaign.id}/messages/batches/')

        self.assertEqual(progress_response.status_code, 200, progress_response.content)
        self.assertEqual(batches_response.status_code, 200, batches_response.content)
        progress = progress_response.json()
        self.assertEqual(progress['progress']['total_messages'], 2)
        self.assertEqual(progress['progress']['sent_count'], 1)
        self.assertEqual(progress['progress']['delivered_count'], 1)
        self.assertEqual(progress['progress']['pending_count'], 1)
        self.assertEqual(progress['progress']['progress_percent'], 50)
        self.assertEqual(progress['batches']['total_batches'], 1)
        self.assertEqual(progress['batches']['in_progress_batches'], 1)
        batch = batches_response.json()['results'][0]
        self.assertEqual(batch['batch_id'], 'progress-batch-1')
        self.assertEqual(batch['total_messages'], 2)
        self.assertEqual(batch['status'], 'PROCESSING')

    def test_step_2_configure_database_audience(self):
        campaign = self.create_campaign()
        database = DatabaseConfig.objects.create(
            name='workflow-source', database_type='sqlite', database_name=':memory:',
            host='localhost', port=1, is_active=True,
        )

        response = self.client.post(
            f'/api/v1/campaigns/{campaign.id}/audience/database/',
            data={
                'source_database_id': database.id,
                'source_table': 'customers',
                'source_msisdn_column': 'msisdn',
                'source_language_column': 'language',
                'default_language_id': self.language.id,
                'rebuild_before_each_run': True,
                'rebuild_minutes_before': 10,
                'rebuild_timeout_minutes': 30,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        config = AudienceConfig.objects.get(campaign=campaign)
        self.assertTrue(config.rebuild_before_each_run)
        self.assertEqual(config.source_table, 'customers')

    def test_database_audience_joins_reference_language_without_source_language_column(self):
        campaign = self.create_campaign()
        language, _ = Language.objects.get_or_create(code='am', defaults={'name': 'Amharic'})
        database_file = tempfile.NamedTemporaryFile(suffix='.sqlite3', delete=False)
        database_file.close()
        self.addCleanup(lambda: os.unlink(database_file.name) if os.path.exists(database_file.name) else None)

        with sqlite3.connect(database_file.name) as connection:
            connection.execute('CREATE TABLE recipients (phone TEXT)')
            connection.executemany(
                'INSERT INTO recipients (phone) VALUES (?)',
                [('+251711234567',), ('+251722345678',)],
            )
            connection.execute('CREATE TABLE language_reference (phone TEXT, language TEXT)')
            connection.execute(
                'INSERT INTO language_reference (phone, language) VALUES (?, ?)',
                ('+251711234567', 'am'),
            )
        connection.close()

        database = DatabaseConfig.objects.create(
            name='audience-source-test',
            database_type='sqlite',
            database_name=database_file.name,
            host='localhost',
            port=1,
        )
        config = AudienceConfig.objects.create(
            campaign=campaign,
            source_type='database',
            source_database=database,
            source_table='recipients',
            source_msisdn_column='phone',
            mapper_enabled=True,
            mapper_database=database,
            mapper_table='language_reference',
            mapper_msisdn_column='phone',
            mapper_language_column='language',
            default_language=self.language,
        )

        result = AudienceBuildService(config).build()

        self.assertEqual(result['data']['total_count'], 2)
        self.assertEqual(result['data']['language_from_mapper'], 1)
        self.assertEqual(result['data']['language_from_default'], 1)
        members = {
            member.msisdn: member.language.code
            for member in AudienceMember.objects.filter(campaign=campaign).select_related('language')
        }
        self.assertEqual(members['+251711234567'], language.code)
        self.assertEqual(members['+251722345678'], self.language.code)
    def test_step_3_add_daily_schedule(self):
        campaign = self.create_campaign()

        schedule = Schedule.objects.create(
            campaign=campaign,
            schedule_type='daily',
            start_date=date.today(),
            time_windows=[{'start': '08:00', 'end': '20:00'}],
            schedule_status='active',
        )

        self.assertEqual(schedule.schedule_type, 'daily')
        self.assertEqual(schedule.time_windows[0]['start'], '08:00')

    def test_campaign_schedule_api_create_read_and_update(self):
        campaign = self.create_campaign()
        url = f'/api/v1/campaigns/{campaign.id}/schedule/'
        payload = {
            'schedule_type': 'weekly',
            'start_date': (date.today() + timedelta(days=1)).isoformat(),
            'run_days': [0, 2],
            'time_windows': [{'start': '09:00', 'end': '17:00'}],
            'timezone': 'Africa/Addis_Ababa',
            'auto_reset': False,
        }

        create_response = self.client.post(
            url,
            json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        self.assertEqual(create_response.json()['data']['campaign'], campaign.id)
        self.assertFalse(create_response.json()['data']['auto_reset'])
        schedule_id = create_response.json()['data']['id']

        campaign_detail_response = self.client.get(f'/api/v1/campaigns/{campaign.id}/')
        self.assertEqual(campaign_detail_response.status_code, 200, campaign_detail_response.content)
        campaign_detail = campaign_detail_response.json()['data']
        self.assertEqual(campaign_detail['schedule_id'], schedule_id)
        self.assertEqual(campaign_detail['schedule']['id'], schedule_id)
        self.assertEqual(campaign_detail['schedule']['schedule_type'], 'weekly')

        list_response = self.client.get('/api/v1/schedules/')
        summary_response = self.client.get('/api/v1/schedules/summary/')
        detail_response = self.client.get(f'/api/v1/schedules/{schedule_id}/')
        self.assertEqual(list_response.status_code, 200, list_response.content)
        self.assertEqual(list_response.json()['results'][0]['campaign'], campaign.id)
        self.assertEqual(summary_response.status_code, 200, summary_response.content)
        self.assertEqual(summary_response.json()['total_schedules'], 1)
        self.assertEqual(detail_response.status_code, 200, detail_response.content)
        self.assertEqual(detail_response.json()['data']['campaign_info']['id'], campaign.id)

        upcoming_response = self.client.get(f'/api/v1/schedules/{schedule_id}/upcoming_windows/')
        self.assertEqual(upcoming_response.status_code, 200, upcoming_response.content)

        manager_update_response = self.client.patch(
            f'/api/v1/schedules/{schedule_id}/',
            json.dumps({'auto_reset': True}),
            content_type='application/json',
        )
        self.assertEqual(manager_update_response.status_code, 200, manager_update_response.content)
        self.assertTrue(manager_update_response.json()['data']['auto_reset'])

        read_response = self.client.get(url)
        self.assertEqual(read_response.status_code, 200, read_response.content)
        self.assertEqual(read_response.json()['data']['run_days'], [0, 2])

        payload['auto_reset'] = True
        update_response = self.client.put(
            url,
            json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(update_response.status_code, 200, update_response.content)
        self.assertTrue(update_response.json()['data']['auto_reset'])

    def test_campaign_audience_summary_reads_audience_config(self):
        campaign = self.create_campaign()
        AudienceConfig.objects.create(
            campaign=campaign,
            default_language=self.language,
            source_type='database',
            total_count=4,
            valid_count=3,
            invalid_count=1,
            language_from_source=2,
            language_from_mapper=1,
            language_from_default=1,
            is_processed=True,
            round_number=1,
        )
        for sequence, language_source in enumerate(
            ['source', 'source', 'mapper', 'default'],
            start=1,
        ):
            Audience.objects.create(
                campaign=campaign,
                msisdn=f'+25170000000{sequence}',
                language=self.language,
                language_source=language_source,
                is_valid=sequence != 4,
                validation_error='Invalid MSISDN' if sequence == 4 else '',
                sequence_number=sequence,
                round_number=1,
            )

        response = self.client.get(f'/api/v1/campaigns/{campaign.id}/audience/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['default_language'], 'en')
        self.assertEqual(response.json()['data']['total_count'], 4)
        self.assertEqual(response.json()['data']['invalid_count'], 1)
        self.assertEqual(response.json()['data']['language_matched'], 3)

    def test_audience_collection_lists_campaign_with_built_members(self):
        campaign = self.create_campaign()
        AudienceConfig.objects.create(
            campaign=campaign,
            default_language=self.language,
            source_type='database',
        )
        Audience.objects.create(
            campaign=campaign,
            msisdn='+251700000001',
            language=self.language,
            sequence_number=1,
            round_number=1,
        )

        response = self.client.get('/api/v1/audiences/?page=1&page_size=10')

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['campaign'], campaign.id)
        self.assertEqual(payload['results'][0]['total_count'], 1)
        self.assertEqual(payload['results'][0]['valid_count'], 1)

    def test_step_4_add_content_and_build_message_objects(self):
        campaign = self.create_campaign()
        MessageContent.objects.create(
            campaign=campaign,
            en='Hello customer',
            default_language=self.language,
        )
        Audience.objects.create(
            campaign=campaign,
            msisdn='+251700000001',
            language=self.language,
            sequence_number=1,
        )

        result = MessageBuilder(campaign=campaign, round_number=1).build()

        self.assertEqual(result['built'], 1)
        self.assertEqual(MessageObject.objects.filter(campaign=campaign).count(), 1)
        self.assertEqual(MessageObject.objects.get(campaign=campaign).message_content, 'Hello customer')

    def test_message_build_progress_reports_committed_rows(self):
        campaign = self.create_campaign()
        MessageContent.objects.create(
            campaign=campaign,
            en='Hello customer',
            default_language=self.language,
        )
        Audience.objects.create(
            campaign=campaign,
            msisdn='+251700000001',
            language=self.language,
            sequence_number=1,
            round_number=1,
        )

        result = MessageBuilder(campaign=campaign, round_number=1).build()
        response = self.client.get(f'/api/v1/campaigns/{campaign.id}/messages/build-progress/')

        self.assertEqual(response.status_code, 200, response.content)
        progress = response.json()['data']
        self.assertEqual(progress['status'], 'SUCCEEDED')
        self.assertEqual(progress['phase'], 'complete')
        self.assertEqual(progress['processed'], 1)
        self.assertEqual(progress['total'], 1)
        self.assertEqual(progress['built'], 1)
        self.assertEqual(progress['percent'], 100)
        self.assertEqual(
            MessageObject.objects.filter(campaign=campaign, batch_id=result['batch_id']).count(),
            progress['built'],
        )

    def test_kafka_status_events_persist_once_and_archive_message_object(self):
        campaign = self.create_campaign()
        message = MessageObject.objects.create(
            campaign=campaign,
            message_id='kafka-event-message-1',
            recipient='+251700000001',
            sender_id=campaign.sender_id,
            message_content='Kafka test message',
            channel=self.channel,
            language=self.language,
            batch_id='send-batch-1',
        )
        send_event = {
            'event_type': 'SEND_RESPONSE',
            'message_id': message.message_id,
            'provider_message_id': 'smsc-provider-kafka-1',
            'campaign_id': campaign.id,
            'recipient': message.recipient,
            'sender_id': message.sender_id,
            'status': 'ACCEPTED',
            'segment_count': 1,
            'received_at': timezone.now().isoformat(),
        }

        self.assertEqual(process_send_batch([send_event]), 1)
        self.assertEqual(process_send_batch([send_event]), 0)
        self.assertEqual(SuccessSent.objects.filter(message_id=message.message_id).count(), 1)
        self.assertFalse(MessageObject.objects.filter(pk=message.pk).exists())

        delivery_event = {
            'event_type': 'DELIVERY_REPORT',
            'message_id': message.message_id,
            'provider_message_id': 'smsc-provider-kafka-1',
            'campaign_id': campaign.id,
            'recipient': message.recipient,
            'status': 'DELIVRD',
            'err_code': '000',
            'error_reason': 'Delivered',
            'segment_count': 1,
            'delivered_at': timezone.now().isoformat(),
        }

        self.assertEqual(process_delivery_batch([delivery_event]), 1)
        self.assertEqual(process_delivery_batch([delivery_event]), 0)
        self.assertEqual(SuccessDelivery.objects.filter(message_id=message.message_id).count(), 1)

    @patch('sms_campaign_manager.services.campaign_activation_email.EmailMultiAlternatives')
    def test_campaign_activation_builds_messages_and_emails_owner_snapshot(self, email_message):
        campaign = self.create_campaign()
        active_email_config = EmailConfig.objects.create(
            name='Activation default SMTP',
            host='smtp.example.com',
            port=587,
            default_from_email='campaigns@example.com',
            is_active=True,
            is_default=False,
        )
        email_message.return_value.send.side_effect = RuntimeError('SMTP unavailable')
        MessageContent.objects.create(
            campaign=campaign,
            en='Hello customer',
            am='Hello in Amharic',
            default_language=self.language,
        )
        Audience.objects.create(
            campaign=campaign,
            msisdn='+251700000001',
            language=self.language,
            sequence_number=1,
        )
        AudienceConfig.objects.create(
            campaign=campaign,
            default_language=self.language,
            source_type='manual',
            total_count=1,
            valid_count=1,
            invalid_count=0,
        )
        Schedule.objects.create(
            campaign=campaign,
            schedule_type='once',
            start_date=date.today() + timedelta(days=1),
            time_windows=[{'start': '09:00', 'end': '17:00'}],
        )

        response = self.client.post(
            f'/api/v1/campaigns/{campaign.id}/activate/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()['data']['messages_built'], 1)
        self.assertFalse(response.json()['data']['owner_notification_sent'])
        message = MessageObject.objects.get(campaign=campaign)
        self.assertEqual(message.message_content, 'Hello customer')
        self.assertEqual(message.recipient, '+251700000001')
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'active')
        self.assertTrue(campaign.is_ready_to_execute)
        email_message.assert_called_once()
        email_kwargs = email_message.call_args.kwargs
        self.assertEqual(email_kwargs['subject'], f'Campaign activated: {campaign.name}')
        self.assertEqual(email_kwargs['from_email'], active_email_config.default_from_email)
        self.assertEqual(email_kwargs['to'], ['owner@example.com'])
        self.assertIn('Hello owner@example.com,', email_kwargs['body'])
        self.assertIn('The following campaign is now active and ready to send.', email_kwargs['body'])
        self.assertIn('Owner Emails         owner@example.com', email_kwargs['body'])
        self.assertIn('Execution Status     Pending', email_kwargs['body'])
        self.assertIn(' 2. MESSAGE CONTENT', email_kwargs['body'])
        self.assertIn(' 3. SCHEDULE', email_kwargs['body'])
        self.assertIn(' 4. AUDIENCE', email_kwargs['body'])
        self.assertIn('═' * 67, email_kwargs['body'])
        self.assertIn('─' * 67, email_kwargs['body'])
        self.assertIn('Valid rate           100.0%', email_kwargs['body'])
        self.assertIn('Amharic              Hello in Amharic', email_kwargs['body'])
        self.assertLess(email_kwargs['body'].index(' 2. MESSAGE CONTENT'), email_kwargs['body'].index(' 3. SCHEDULE'))
        email_html, content_type = email_message.return_value.attach_alternative.call_args.args
        self.assertEqual(content_type, 'text/html')
        self.assertIn('Hello owner@example.com,', email_html)
        self.assertIn('Campaign info', email_html)
        self.assertIn('Message content', email_html)
        self.assertIn('Hello in Amharic', email_html)
        email_message.return_value.send.assert_called_once_with(fail_silently=False)

    @patch('sms_campaign_manager.services.campaign_activation_email.EmailMultiAlternatives')
    def test_campaign_activation_email_silently_skips_when_no_owners(self, email_message):
        campaign = self.create_campaign()
        campaign.owner_emails = []

        self.assertIsNone(send_campaign_activation_email(campaign))
        email_message.assert_not_called()

    @patch('sms_campaign_manager.services.campaign_activation_email.EmailMultiAlternatives')
    def test_campaign_activation_requires_schedule_and_sends_no_email(self, email_message):
        campaign = self.create_campaign()
        MessageContent.objects.create(
            campaign=campaign,
            en='Hello customer',
            default_language=self.language,
        )
        Audience.objects.create(
            campaign=campaign,
            msisdn='+251700000001',
            language=self.language,
            sequence_number=1,
        )

        response = self.client.post(
            f'/api/v1/campaigns/{campaign.id}/activate/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn('Schedule is missing.', response.json()['errors'])
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'draft')
        self.assertFalse(MessageObject.objects.filter(campaign=campaign).exists())
        email_message.assert_not_called()

    def test_campaign_pause_resume_stop_and_cancel_transitions(self):
        campaign = self.create_campaign()
        actions = CampaignActionsService(campaign)

        self.assertFalse(actions.start_campaign()['success'])
        self.assertFalse(actions.pause_campaign()['success'])
        campaign.status = 'active'
        campaign.is_ready_to_execute = True
        campaign.save(update_fields=['status', 'is_ready_to_execute', 'updated_at'])
        MessageObject.objects.create(
            campaign=campaign,
            message_id='msg_start_transition',
            recipient='+251700000001',
            sender_id=campaign.sender_id,
            message_content='Hello customer',
            channel=self.channel,
            language=self.language,
        )
        start_response = self.client.post(f'/api/v1/campaigns/{campaign.id}/start/', {}, format='json')
        self.assertEqual(start_response.status_code, 200, start_response.content)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, 'in_progress')
        self.assertTrue(actions.pause_campaign()['success'])
        self.assertTrue(actions.resume_campaign()['success'])
        self.assertTrue(actions.complete_campaign()['success'])
        self.assertFalse(actions.resume_campaign()['success'])

        cancelled = self.create_campaign()
        cancelled.status = 'active'
        cancelled.save(update_fields=['status', 'updated_at'])
        cancel_result = CampaignActionsService(cancelled).cancel_campaign()
        self.assertTrue(cancel_result['success'])
        self.assertEqual(cancel_result['data']['status'], 'stopped')

    def test_campaign_message_queue_endpoints_build_list_stats_and_clear(self):
        campaign = self.create_campaign()
        MessageContent.objects.create(
            campaign=campaign,
            en='Hello customer',
            default_language=self.language,
        )
        Audience.objects.create(
            campaign=campaign,
            msisdn='+251700000001',
            language=self.language,
            sequence_number=1,
        )

        build_response = self.client.post(
            f'/api/v1/campaigns/{campaign.id}/messages/build/',
            {'round_number': 1, 'batch_id': 'workflow-test'},
            format='json',
        )
        list_response = self.client.get(f'/api/v1/campaigns/{campaign.id}/messages/')
        stats_response = self.client.get(f'/api/v1/campaigns/{campaign.id}/messages/stats/')

        self.assertEqual(build_response.status_code, 201, build_response.content)
        self.assertEqual(build_response.json()['data']['built'], 1)
        self.assertEqual(list_response.status_code, 200, list_response.content)
        self.assertEqual(list_response.json()['results'][0]['recipient'], '+251700000001')
        self.assertEqual(stats_response.status_code, 200, stats_response.content)
        self.assertEqual(stats_response.json()['data']['total'], 1)

        clear_response = self.client.delete(f'/api/v1/campaigns/{campaign.id}/messages/clear/')

        self.assertEqual(clear_response.status_code, 200, clear_response.content)
        self.assertEqual(MessageObject.objects.filter(campaign=campaign).count(), 0)

    @patch('sms_campaign_manager.services.smsc_sender.requests.post')
    def test_step_5_sender_submits_pending_message(self, post):
        campaign = self.create_campaign()
        campaign.status = 'in_progress'
        campaign.save(update_fields=['status', 'updated_at'])
        message = MessageObject.objects.create(
            campaign=campaign,
            recipient='+251700000001',
            sender_id=campaign.sender_id,
            message_content='Hello customer',
            channel=self.channel,
            language=self.language,
            batch_id='workflow-batch',
            sent_status='PENDING',
        )
        config = SMSCConfig.objects.create(
            name='workflow-smsc', base_url='http://127.0.0.1:8090',
            send_endpoint='/api/send', auth_type='none',
            rate_limit_per_second=10, rate_limit_per_minute=600,
        )
        response = Mock(status_code=200, content=b'{}')
        response.json.return_value = {
            'status': 'ACCEPTED', 'provider_message_id': 'provider-workflow-1',
        }
        post.return_value = response

        result = SmsSenderService(config, workers=1).run_once()

        self.assertEqual(result['sent'], 1)
        self.assertTrue(MessageObject.objects.filter(pk=message.pk).exists())
        self.assertEqual(MessageObject.objects.get(pk=message.pk).sent_status, 'SENT')
        self.assertFalse(SentRecord.objects.filter(provider_message_id='provider-workflow-1').exists())

    def test_sender_claim_keeps_first_sending_started_at_across_retries(self):
        campaign = self.create_campaign()
        campaign.status = 'active'
        campaign.save(update_fields=['status', 'updated_at'])
        first_claim = timezone.now() - timedelta(minutes=5)
        message = MessageObject.objects.create(
            campaign=campaign,
            recipient='+251700000002',
            sender_id=campaign.sender_id,
            message_content='Retry test message',
            channel=self.channel,
            language=self.language,
            sent_status='FAILED',
            sending_started_at=first_claim,
            locked_until=first_claim + timedelta(minutes=5),
        )
        config = SMSCConfig.objects.create(
            name='retry-smsc', base_url='http://127.0.0.1:8090',
            send_endpoint='/api/send', auth_type='none',
            rate_limit_per_second=10, rate_limit_per_minute=600,
            request_timeout_seconds=30,
        )

        service = SmsSenderService(config, workers=1)
        service._claim_batch([message])
        message.refresh_from_db()

        self.assertEqual(message.sending_started_at, first_claim)
        self.assertTrue(message.locked_until is not None)
        self.assertTrue(message.locked_until > timezone.now())
        self.assertTrue(message.worker_id)
        self.assertTrue(message.batch_id)


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
    def test_draft_campaign_audience_config_persists_language_and_builds_linked_audience(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True)
        campaign = Campaign.objects.create(
            name='Wizard audience build',
            sender_id='SMSINFO',
            channels_id=[channel.id],
            status='draft',
        )
        language = Language.objects.get(code='en')

        response = self.client.post(
            f'/api/v1/campaigns/{campaign.id}/audience-config/',
            {
                'source_type': 'manual',
                'manual_msisdns': ['+251711111111', '+251722222222'],
                'manual_languages': ['en', ''],
                'default_language_id': language.id,
                'mapper_enabled': False,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        config = AudienceConfig.objects.get(campaign=campaign)
        self.assertEqual(config.default_language_id, language.id)
        build = AudienceBuildService(config).build()
        self.assertEqual(build['data']['valid_count'], 2)

        detail_response = self.client.get(f'/api/v1/campaigns/{campaign.id}/')
        self.assertEqual(detail_response.status_code, 200, detail_response.content)
        linked = detail_response.json()['data']['audience']
        self.assertEqual(detail_response.json()['data']['audience_id'], config.id)
        self.assertEqual(linked['id'], config.id)
        self.assertEqual(linked['total_count'], 2)
        self.assertEqual(linked['valid_count'], 2)

    def test_audience_config_write_rejects_non_draft_campaign(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True)
        campaign = Campaign.objects.create(
            name='Active campaign audience lock',
            sender_id='SMSINFO',
            channels_id=[channel.id],
            status='active',
        )
        language = Language.objects.get(code='en')

        response = self.client.post(
            f'/api/v1/campaigns/{campaign.id}/audience-config/',
            {'source_type': 'manual', 'manual_msisdns': ['+251711111111'], 'default_language_id': language.id},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(AudienceConfig.objects.filter(campaign=campaign).exists())

    def test_file_source_config_never_persists_manual_recipients(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True)
        campaign = Campaign.objects.create(
            name='File source recipe', sender_id='SMSINFO', channels_id=[channel.id],
        )
        language = Language.objects.get(code='en')

        response = self.client.post(
            f'/api/v1/campaigns/{campaign.id}/audience-config/',
            {
                'source_type': 'file_import',
                'source_file_path': 'audience/source.csv',
                'source_file_msisdn_column': 'phone',
                'default_language_id': language.id,
                'manual_msisdns': ['+251711111111'],
                'manual_languages': ['en'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        config = AudienceConfig.objects.get(campaign=campaign)
        self.assertEqual(config.manual_msisdns, [])
        self.assertEqual(config.manual_languages, [])

    def test_campaign_audience_summary_uses_current_audience_config(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True, is_default=True)
        campaign = Campaign.objects.create(
            name='Audience summary campaign',
            sender_id='SMSINFO',
            channels_id=[channel.id],
        )
        language = Language.objects.get(code='en')
        config = AudienceConfig.objects.create(
            campaign=campaign,
            default_language=language,
            source_type='manual',
            total_count=2,
            valid_count=2,
            language_from_source=1,
            language_from_mapper=1,
            language_from_default=0,
            is_processed=True,
            round_number=1,
        )
        Audience.objects.create(
            campaign=campaign, msisdn='+251711111111', language=language,
            language_source='source', sequence_number=1, round_number=1,
        )
        Audience.objects.create(
            campaign=campaign, msisdn='+251722222222', language=language,
            language_source='mapper', sequence_number=2, round_number=1,
        )

        response = self.client.get(f'/api/v1/campaigns/{campaign.id}/audience/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['default_language'], language.code)
        self.assertEqual(response.json()['data']['total_count'], config.total_count)
        self.assertEqual(response.json()['data']['language_matched'], 2)

    def test_audience_config_model_and_metadata_route_are_registered(self):
        self.assertIsNotNone(AudienceConfig)
        self.assertEqual(resolve('/api/v1/campaigns/1/audience-config/').url_name, 'campaign-audience-config')
        self.assertEqual(resolve('/api/v1/campaigns/1/audience-config/preview/').url_name, 'campaign-audience-config-preview')

    def test_audience_build_route_accepts_audience_id(self):
        self.assertEqual(resolve('/api/v1/audience-configs/1/build/').url_name, 'audience-build')

    def test_build_materializes_invalid_rows_and_replaces_only_target_round(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True)
        campaign = Campaign.objects.create(
            name='Round replacement campaign', sender_id='SMSINFO', channels_id=[channel.id],
        )
        language = Language.objects.get(code='en')
        config = AudienceConfig.objects.create(
            campaign=campaign,
            default_language=language,
            source_type='manual',
            manual_msisdns=['+251711111111', 'not-a-number'],
        )

        first_build = AudienceBuildService(config).build(round_number=1, build_id='round-one-first')

        self.assertEqual(first_build['data']['valid_count'], 1)
        self.assertEqual(first_build['data']['invalid_count'], 1)
        invalid_member = Audience.objects.get(campaign=campaign, round_number=1, is_valid=False)
        self.assertTrue(invalid_member.validation_error)
        self.assertEqual(invalid_member.build_id, 'round-one-first')
        self.assertEqual(invalid_member.source_type, 'manual')

        config.refresh_from_db()
        config.manual_msisdns = ['+251722222222']
        config.save(update_fields=['manual_msisdns', 'updated_at'])
        AudienceBuildService(config).build(round_number=2, build_id='round-two')
        AudienceBuildService(config).build(round_number=1, build_id='round-one-replacement')

        self.assertEqual(Audience.objects.filter(campaign=campaign, round_number=1).count(), 1)
        self.assertEqual(Audience.objects.filter(campaign=campaign, round_number=2).count(), 1)
        self.assertEqual(
            Audience.objects.get(campaign=campaign, round_number=1).build_id,
            'round-one-replacement',
        )

    def test_msisdn_normalization_matches_supported_local_and_numeric_formats(self):
        cases = [
            ('912345678', '+251912345678'),
            ('0912345678', '+251912345678'),
            ('251912345678', '+251912345678'),
            (912345678, '+251912345678'),
            ('2517012345678', '+251712345678'),
        ]

        for source, expected in cases:
            normalized, valid, error = AudienceBuildService._normalize_msisdn(source)
            self.assertTrue(valid, error)
            self.assertEqual(normalized, expected)

    def test_build_endpoint_allows_active_campaign_and_prevents_parallel_job(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True)
        campaign = Campaign.objects.create(
            name='Active audience rebuild', sender_id='SMSINFO',
            channels_id=[channel.id], status='active',
        )
        config = AudienceConfig.objects.create(
            campaign=campaign,
            default_language=Language.objects.get(code='en'),
            round_number=1,
        )

        response = self.client.post(
            f'/api/v1/audience-configs/{config.id}/build/',
            {'increment_round': True},
            format='json',
        )
        duplicate_response = self.client.post(
            f'/api/v1/audience-configs/{config.id}/build/', {}, format='json',
        )

        self.assertEqual(response.status_code, 202, response.content)
        self.assertEqual(response.json()['round_number'], 2)
        self.assertEqual(duplicate_response.status_code, 409)

    def test_audience_reads_are_scoped_to_current_or_requested_round(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True)
        campaign = Campaign.objects.create(
            name='Round scoped reads', sender_id='SMSINFO', channels_id=[channel.id],
        )
        language = Language.objects.get(code='en')
        AudienceConfig.objects.create(
            campaign=campaign, default_language=language, round_number=2,
        )
        Audience.objects.create(
            campaign=campaign, msisdn='+251711111111', language=language,
            sequence_number=1, round_number=1, build_id='build-one',
        )
        Audience.objects.create(
            campaign=campaign, msisdn='+251722222222', language=language,
            sequence_number=1, round_number=2, build_id='build-two',
        )

        summary = self.client.get(f'/api/v1/campaigns/{campaign.id}/audience/')
        current_members = self.client.get(f'/api/v1/campaigns/{campaign.id}/audience/members/')
        previous_members = self.client.get(
            f'/api/v1/campaigns/{campaign.id}/audience/members/?round_number=1',
        )
        rounds = self.client.get(f'/api/v1/campaigns/{campaign.id}/audience/rounds/')

        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()['data']['round_number'], 2)
        self.assertEqual(summary.json()['data']['total_count'], 1)
        self.assertEqual(current_members.json()['count'], 1)
        self.assertEqual(current_members.json()['results'][0]['round_number'], 2)
        self.assertEqual(previous_members.json()['results'][0]['round_number'], 1)
        self.assertEqual([row['round_number'] for row in rounds.json()], [2, 1])

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

    def test_campaign_message_content_accepts_language_code_from_wizard(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True, is_default=True)
        campaign = Campaign.objects.create(
            name='Wizard message campaign',
            sender_id='SMSINFO',
            channels_id=[channel.id],
            status='draft',
        )
        language = Language.objects.get(code='en')

        response = self.client.post(
            f'/api/v1/campaigns/{campaign.id}/content/',
            {
                'en': 'Hello {name}',
                'default_language': 'en',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()['data']['default_language'], language.id)
        campaign_detail = self.client.get(f'/api/v1/campaigns/{campaign.id}/')
        self.assertEqual(campaign_detail.status_code, 200, campaign_detail.content)
        linked_content = campaign_detail.json()['data']['message_content']
        self.assertEqual(linked_content['id'], response.json()['data']['id'])
        self.assertEqual(linked_content['content']['en'], 'Hello {name}')

    def test_audience_rebuild_returns_job_and_status_endpoint_reports_it(self):
        channel = Channel.objects.create(code='sms', name='SMS')
        sender = SenderID.objects.create(sender_id='SMSINFO', name='SMS Info', is_active=True, is_default=True)
        campaign = Campaign.objects.create(
            name='Async rebuild campaign', sender_id=sender.sender_id,
            channels_id=[channel.id], status='draft',
        )
        config = AudienceConfig.objects.create(
            campaign=campaign, default_language=Language.objects.get(code='en'),
        )

        response = self.client.post(f'/api/v1/audience-configs/{config.id}/build/', {}, format='json')

        self.assertEqual(response.status_code, 202)
        job = AudienceBuildJob.objects.get(pk=response.json()['job_id'])
        status_response = self.client.get(f'/api/v1/audience-build-jobs/{job.id}/')
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()['data']['status'], 'PENDING')


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
