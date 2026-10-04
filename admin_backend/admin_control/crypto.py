from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


def get_fernet():
    key = settings.FIELD_ENCRYPTION_KEY
    if not key:
        raise ImproperlyConfigured(
            "FIELD_ENCRYPTION_KEY must match the campaign backend key to encrypt credentials."
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


class SharedEncryptedCharField(models.CharField):
    """Use the shared Fernet key for credential fields stored by either backend."""

    def get_prep_value(self, value):
        if value in (None, ""):
            return value
        return get_fernet().encrypt(str(value).encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        try:
            return get_fernet().decrypt(value.encode()).decode()
        except InvalidToken as error:
            raise ValueError(
                "Could not decrypt SMSC credentials; check FIELD_ENCRYPTION_KEY."
            ) from error
