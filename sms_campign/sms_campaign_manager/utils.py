"""Audience validation and language mapping helpers."""

import re


def normalize_msisdn(msisdn):
    if not msisdn:
        return None
    value = re.sub(r'[\s\-\(\)]', '', str(msisdn).strip())
    if re.match(r'^\+2517\d{8}$', value):
        return value
    if re.match(r'^2517\d{8}$', value):
        return '+' + value
    if re.match(r'^07\d{8}$', value):
        return '+251' + value[1:]
    if re.match(r'^7\d{8}$', value):
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
