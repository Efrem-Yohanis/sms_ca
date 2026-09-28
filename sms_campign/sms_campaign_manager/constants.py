"""
Constants used across the Campaign Manager app.
We start minimal - only what the Campaign model needs.
More will be added as we build other models.
"""

# Languages
SUPPORTED_LANGUAGES = [
    ('en', 'English'),
    ('am', 'Amharic'),
    ('ti', 'Tigrinya'),
    ('om', 'Oromo'),
    ('so', 'Somali'),
]

SUPPORTED_LANGUAGE_CODES = ['en', 'am', 'ti', 'om', 'so']
DEFAULT_LANGUAGE = 'en'

# Campaign status
CAMPAIGN_STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('active', 'Active'),
    ('in_progress', 'In Progress'),
    ('paused', 'Paused'),
    ('stopped', 'Stopped'),
    ('completed', 'Completed'),
    ('invalid_schedule', 'Invalid Schedule'),
    ('archived', 'Archived'),
]

# Execution status
EXECUTION_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('PROCESSING', 'Processing'),
    ('PAUSED', 'Paused'),
    ('STOPPED', 'Stopped'),
    ('COMPLETED', 'Completed'),
    ('FAILED', 'Failed'),
]

# Channels
CHANNEL_CHOICES = [
    ('sms', 'SMS'),
]

VALID_CHANNELS = ['sms']

DATABASE_TYPE_CHOICES = [
    ('postgresql', 'PostgreSQL'),
    ('mysql', 'MySQL'),
    ('mssql', 'Microsoft SQL Server'),
    ('oracle', 'Oracle'),
    ('sqlite', 'SQLite'),
]
DEFAULT_DB_PORTS = {
    'postgresql': 5432,
    'mysql': 3306,
    'mssql': 1433,
    'oracle': 1521,
    'sqlite': 1,
}
DB_CONNECTION_TIMEOUT = 10
DB_PREVIEW_ROW_LIMIT = 50

# Schedule
SCHEDULE_TYPE_CHOICES = [
    ('once', 'One Time'),
    ('daily', 'Daily'),
    ('weekly', 'Weekly'),
    ('monthly', 'Monthly'),
]

WINDOW_STATUS_CHOICES = [
    ('pending', 'Pending'),
    ('active', 'Active'),
    ('completed', 'Completed'),
    ('partial', 'Partial'),
    ('skipped', 'Skipped'),
]

# Sender ID rules
SENDER_ID_MIN_LENGTH = 3
SENDER_ID_MAX_LENGTH = 11

# Sent record status
SENT_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('SUBMITTED', 'Submitted'),
    ('ACCEPTED', 'Accepted'),
    ('REJECTED', 'Rejected'),
    ('FAILED', 'Failed'),
]

SENT_TERMINAL_STATUSES = ['ACCEPTED', 'REJECTED', 'FAILED']

# Delivery record status
DELIVERY_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('DELIVERED', 'Delivered'),
    ('UNDELIVERABLE', 'Undeliverable'),
    ('EXPIRED', 'Expired'),
    ('REJECTED', 'Rejected'),
    ('UNKNOWN', 'Unknown'),
]

DELIVERY_TERMINAL_STATUSES = [
    'DELIVERED', 'UNDELIVERABLE', 'EXPIRED', 'REJECTED',
]

# Campaign message status
CAMPAIGN_MESSAGE_STATUS_CHOICES = [
    ('PENDING', 'Pending'),
    ('QUEUED', 'Queued'),
    ('SENT', 'Sent'),
    ('DELIVERED', 'Delivered'),
    ('FAILED', 'Failed'),
    ('SKIPPED', 'Skipped'),
]
CAMPAIGN_MESSAGE_TERMINAL_STATUSES = ['DELIVERED', 'FAILED', 'SKIPPED']
MESSAGE_BUILD_CHUNK_SIZE = 5000

# Audience
SOURCE_TYPE_CHOICES = [
    ('manual', 'Manual Entry'),
    ('file_import', 'File Import'),
    ('database', 'Database Source'),
]
LANGUAGE_SOURCE_CHOICES = [
    ('source', 'From Source'),
    ('mapper', 'From Mapper'),
    ('default', 'Default Language'),
]
AUDIENCE_BULK_CHUNK_SIZE = 10000
AUDIENCE_MAX_SIZE = 10_000_000
AUDIENCE_DEFAULT_LANGUAGE = 'en'
