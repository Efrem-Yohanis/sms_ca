# Email Configuration and Email Reports

## Current status

The application currently supports campaign owner email notifications and API-based sent/delivery reports. It does not yet provide a dedicated SMTP configuration API or scheduled email reports.

| Feature | Status |
| --- | --- |
| Store campaign owner email addresses | Implemented |
| Validate owner email addresses | Implemented |
| Send campaign-created notification | Implemented |
| SMTP configuration through Django settings | Not configured |
| Email configuration API | Not implemented |
| Email sent/delivery reports | Not implemented |
| Scheduled email reports | Not implemented |
| Email report history/logs | Not implemented |
| PDF/CSV email attachments | Not implemented |

## Campaign owner email addresses

Campaigns store notification recipients in the `owner_emails` JSON field:

- Model: `sms_campign/sms_campaign_manager/models.py`
- Migration: `sms_campign/sms_campaign_manager/migrations/0009_campaign_owner_emails.py`
- Serializer: `sms_campign/sms_campaign_manager/serializers.py`

Example campaign request:

```http
POST /api/v1/campaigns/
Content-Type: application/json
```

```json
{
  "name": "September Promotion",
  "sender_id": "SMSINFO",
  "owner_emails": [
    "manager@example.com",
    "marketing@example.com"
  ],
  "channels": ["SMS"]
}
```

Email addresses are:

- Validated with DRF `EmailField`
- Trimmed and lowercased
- Deduplicated
- Limited to 50 recipients

## Campaign-created notification

The notification helper is `notify_campaign_owners()` in:

```text
sms_campign/sms_campaign_manager/views.py
```

It is called after campaign creation. If `owner_emails` is empty, no message is sent.

The current message is:

```text
Subject: Campaign created: September Promotion

Campaign "September Promotion" was created with ID 13.
Current status: draft.
```

The helper uses Django:

```python
send_mail(
    subject=f'Campaign created: {campaign.name}',
    message=message,
    from_email=None,
    recipient_list=campaign.owner_emails,
    fail_silently=False,
)
```

If delivery fails, the exception is logged by Django and the campaign creation response is not replaced with an email-specific error.

## SMTP configuration

The current settings file does not define SMTP settings:

```text
sms_campign/sms_campign/settings.py
```

For a real SMTP server, add settings using environment variables:

```python
import os

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.example.com')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '587'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'true').lower() == 'true'
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'false').lower() == 'true'
DEFAULT_FROM_EMAIL = os.environ.get(
    'DEFAULT_FROM_EMAIL',
    'no-reply@example.com',
)
```

Recommended environment variables:

```text
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=no-reply@example.com
EMAIL_HOST_PASSWORD=your-password
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
DEFAULT_FROM_EMAIL=no-reply@example.com
```

Do not commit SMTP passwords or other credentials to source control.

## Existing API reports

### Sent/submission reports

```http
GET /api/v1/campaigns/{campaign_id}/sent-records/
GET /api/v1/campaigns/{campaign_id}/sent-stats/
```

The records endpoint supports filters such as:

```text
?sent_status=ACCEPTED
?batch_id=batch-001
```

These endpoints return API responses only. They do not send email.

### Delivery reports

```http
GET /api/v1/campaigns/{campaign_id}/delivery-records/
GET /api/v1/campaigns/{campaign_id}/delivery-stats/
POST /api/v1/delivery-reports/callback/
```

The records endpoint supports filters such as:

```text
?delivery_status=DELIVERED
?batch_id=batch-001
```

The callback accepts provider delivery updates and stores them as delivery records. It does not currently trigger an email.

### Campaign message statistics

```http
GET /api/v1/campaigns/{campaign_id}/messages/stats/
```

This is also an API response and is not emailed.

## Email reports not yet implemented

The following endpoints do not currently exist:

```text
GET  /api/v1/email-config/
POST /api/v1/email-config/
PATCH /api/v1/email-config/{id}/
POST /api/v1/campaigns/{id}/reports/email/
GET  /api/v1/campaigns/{id}/report-history/
```

There are no models yet for SMTP provider configuration, report subscriptions, scheduled reports, report delivery logs, or generated attachments.

## Expected future email-report flow

1. Calculate sent, delivery, and message statistics.
2. Render a text or HTML report.
3. Optionally generate a CSV or PDF attachment.
4. Send the report through the configured SMTP provider.
5. Store success or failure in an email report log.
6. Expose report history through an API.

