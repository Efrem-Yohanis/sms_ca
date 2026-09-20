from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase

from .models import (
    Campaign, Channel, DeliveryRecord, EmailCampaignReport,
    EmailCampaignReportRecipient, EmailServerConfig, SentRecord,
    SenderID,
)
from .services.email_report_service import aggregate_campaigns, send_report


class EmailCampaignReportTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('owner', email='owner@example.com')
        self.report_owner = User.objects.create_user('reporter', email='reporter@example.com')
        self.channel = Channel.objects.create(code='sms', name='SMS')
        SenderID.objects.create(sender_id='TEST', name='Test')
        self.campaign = Campaign.objects.create(
            name='Test', sender_id='TEST', channels_id=[self.channel.id], created_by=self.user,
        )
        self.server = EmailServerConfig.objects.create(
            name='local', host='localhost', from_email='reports@example.com',
        )
        self.report = EmailCampaignReport.objects.create(
            name='Daily', owner=self.report_owner, email_server=self.server,
        )
        self.report.campaigns.add(self.campaign)
        EmailCampaignReportRecipient.objects.create(report=self.report, email='recipient@example.com')

    def test_aggregates_campaign_sent_and_delivery_failures(self):
        SentRecord.objects.create(campaign=self.campaign, channel=self.channel, msisdn='1', sent_status='FAILED')
        DeliveryRecord.objects.create(
            campaign=self.campaign, channel=self.channel, msisdn='1', delivery_status='DELIVERED',
        )
        DeliveryRecord.objects.create(
            campaign=self.campaign, channel=self.channel, msisdn='2', delivery_status='REJECTED',
        )
        self.assertEqual(aggregate_campaigns(self.report.campaigns.all())['sent_count'], 1)
        self.assertEqual(aggregate_campaigns(self.report.campaigns.all())['failed_sent'], 1)
        self.assertEqual(aggregate_campaigns(self.report.campaigns.all())['delivered_count'], 1)
        self.assertEqual(aggregate_campaigns(self.report.campaigns.all())['failed_delivery'], 1)

    @patch('sms_campaign_manager.services.email_report_service.smtplib.SMTP')
    def test_send_report_includes_owner_and_recipient(self, smtp_cls):
        smtp = smtp_cls.return_value.__enter__.return_value
        send_report(self.report)
        message = smtp.send_message.call_args.args[0]
        self.assertIn('owner@example.com', message['To'])
        self.assertIn('recipient@example.com', message['To'])
        self.assertNotIn('reporter@example.com', message['To'])
        self.assertIn('text/html', message.get_body('html').get_content_type())
        self.assertIn('Campaign progress report', message.get_body('html').get_content())
        self.assertIsNotNone(self.report.__class__.objects.get(pk=self.report.pk).last_sent_at)
