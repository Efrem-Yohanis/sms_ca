"""Custom model fields for Campaign Manager.

EncryptedCharField transparently encrypts its value at rest using Fernet
(symmetric, authenticated encryption from the `cryptography` package) and
decrypts on load. Plaintext never touches the database.

Setup
-----
1. `pip install cryptography`
2. Generate a key once and store it OUTSIDE version control:

       from cryptography.fernet import Fernet
       Fernet.generate_key()

3. Add it to settings, e.g. via environment variable:

       FIELD_ENCRYPTION_KEY = os.environ["FIELD_ENCRYPTION_KEY"]

Rotating the key requires re-encrypting existing rows (decrypt with the old
key, re-save with the new one) — plan a migration/management command for
that rather than swapping the setting in place.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

from cryptography.fernet import Fernet, InvalidToken


def _get_fernet() -> Fernet:
    key = getattr(settings, 'FIELD_ENCRYPTION_KEY', None)
    if not key:
        raise ImproperlyConfigured(
            'FIELD_ENCRYPTION_KEY must be set in settings to use EncryptedCharField.'
        )
    if isinstance(key, str):
        key = key.encode()
    return Fernet(key)


class EncryptedCharField(models.CharField):
    """A CharField that is encrypted in the database and plaintext in Python."""

    def get_prep_value(self, value):
        if value is None or value == '':
            return value
        value = super().get_prep_value(value)
        token = _get_fernet().encrypt(value.encode()).decode()
        return token

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        try:
            return _get_fernet().decrypt(value.encode()).decode()
        except InvalidToken:
            # Value predates encryption being enabled, or the key rotated
            # without a re-encryption pass. Surface it plainly rather than
            # silently returning ciphertext as if it were a real password.
            raise ValueError(
                'Could not decrypt DatabaseConfig field value — '
                'check FIELD_ENCRYPTION_KEY or run the re-encryption migration.'
            )

    def to_python(self, value):
        return value