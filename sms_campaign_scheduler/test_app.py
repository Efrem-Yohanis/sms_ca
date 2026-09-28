from datetime import date, datetime, time, timezone
import asyncio
import unittest
from unittest.mock import patch

from sms_campaign_scheduler.app import CampaignScheduler


class CampaignSchedulerStepTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            'status': 'draft',
            'audience_rebuild': {
                'id': 1,
                'enabled': True,
                'minutes_before': 10,
                'timeout_minutes': 30,
            },
            'schedule': {
                'schedule_type': 'daily',
                'start_date': str(date.today()),
                'end_date': None,
                'run_days': [],
                'time_windows': [{'start': '08:00', 'end': '20:00'}],
                'schedule_status': 'active',
                'is_active': True,
            },
        }

    def test_schedule_is_running_inside_window(self):
        current = datetime.combine(date.today(), time(12), tzinfo=timezone.utc)
        self.assertTrue(CampaignScheduler.is_running_now(self.row, current))

    def test_schedule_is_not_running_outside_window(self):
        current = datetime.combine(date.today(), time(21), tzinfo=timezone.utc)
        self.assertFalse(CampaignScheduler.is_running_now(self.row, current))

    def test_audience_rebuild_starts_ten_minutes_before_window(self):
        current = datetime.combine(date.today(), time(7, 50), tzinfo=timezone.utc)
        self.assertTrue(CampaignScheduler.is_prepare_window(self.row, current))

    def test_active_campaign_is_not_stopped_outside_its_delivery_window(self):
        scheduler = CampaignScheduler()
        campaign = {**self.row, 'id': 41, 'status': 'active'}

        with (
            patch.object(scheduler, 'campaigns', return_value=[campaign]),
            patch.object(CampaignScheduler, 'is_running_now', return_value=False),
            patch.object(scheduler, 'call_campaign_api') as call_api,
        ):
            report = asyncio.run(scheduler.run_once())

        call_api.assert_not_called()
        self.assertEqual(report['stopped'], [])

    def test_in_progress_campaign_pauses_between_windows_and_resumes_in_window(self):
        scheduler = CampaignScheduler()
        in_progress = {**self.row, 'id': 41, 'status': 'in_progress'}

        with (
            patch.object(scheduler, 'campaigns', return_value=[in_progress]),
            patch.object(CampaignScheduler, 'is_running_now', return_value=False),
            patch.object(scheduler, 'call_campaign_api') as call_api,
        ):
            report = asyncio.run(scheduler.run_once())

        self.assertEqual(report['paused'], [41])
        call_api.assert_called_once_with(41, 'pause')

        self.row['schedule']['time_windows'] = [{'start': '00:00', 'end': '23:59'}]
        paused = {**self.row, 'id': 42, 'status': 'paused'}
        with (
            patch.object(scheduler, 'campaigns', return_value=[paused]),
            patch.object(CampaignScheduler, 'is_running_now', return_value=True),
            patch.object(scheduler, 'call_campaign_api') as call_api,
        ):
            report = asyncio.run(scheduler.run_once())

        self.assertEqual(report['resumed'], [42])
        call_api.assert_called_once_with(42, 'resume')

    def test_automatic_rebuild_advances_round_and_builds_messages_for_that_round(self):
        class FakeResponse:
            def __init__(self, body):
                self.body = body

            def raise_for_status(self):
                pass

            def json(self):
                return self.body

        with (
            patch('sms_campaign_scheduler.app.DJANGO_API_BASE_URL', 'http://django/api/v1'),
            patch('sms_campaign_scheduler.app.requests.post') as post,
            patch('sms_campaign_scheduler.app.requests.get') as get,
        ):
            post.side_effect = [
                FakeResponse({'job_id': 7, 'round_number': 5}),
                FakeResponse({'success': True}),
            ]
            get.return_value = FakeResponse({'data': {'status': 'SUCCEEDED'}})

            CampaignScheduler.prepare_campaign({
                'id': 12,
                'audience_rebuild': {'id': 3, 'timeout_minutes': 1},
            })

        self.assertEqual(post.call_args_list[0].args[0], 'http://django/api/v1/audience-configs/3/build/')
        self.assertEqual(post.call_args_list[0].kwargs['json'], {'increment_round': True})
        self.assertEqual(post.call_args_list[1].args[0], 'http://django/api/v1/campaigns/12/messages/build/')
        self.assertEqual(post.call_args_list[1].kwargs['json'], {'round_number': 5})