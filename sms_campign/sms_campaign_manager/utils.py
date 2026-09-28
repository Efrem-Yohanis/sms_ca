"""Audience validation and language mapping helpers."""

import re
from decimal import Decimal, InvalidOperation


def normalize_msisdn(msisdn):
    if not msisdn:
        return None
    if not isinstance(msisdn, str):
        try:
            numeric_value = Decimal(str(msisdn))
            if numeric_value.is_finite() and numeric_value == numeric_value.to_integral_value():
                msisdn = format(numeric_value, 'f').split('.')[0]
        except (InvalidOperation, ValueError):
            pass
    value = re.sub(r'[\s\-\(\)]', '', str(msisdn).strip())
    if re.match(r'^25170\d{8}$', value):
        return '+2517' + value[5:]
    if re.match(r'^\+251[79]\d{8}$', value):
        return value
    if re.match(r'^251[79]\d{8}$', value):
        return '+' + value
    if re.match(r'^0[79]\d{8}$', value):
        return '+251' + value[1:]
    if re.match(r'^[79]\d{8}$', value):
        return '+251' + value
    return None


def validate_msisdn(msisdn):
    normalized = normalize_msisdn(msisdn)
    if normalized:
        return True, normalized, ''
    return False, None, f'Invalid MSISDN format: {msisdn}'


def resolve_language(source_lang, profile_lang, default_lang):
    valid = {'en', 'am', 'ti', 'om', 'so'}
    source = (source_lang or '').strip().lower()
    profile = (profile_lang or '').strip().lower()
    default = (default_lang or 'en').strip().lower()
    if source in valid:
        return source, 'source'
    if profile in valid:
        return profile, 'reference'
    return (default if default in valid else 'en'), 'default'
