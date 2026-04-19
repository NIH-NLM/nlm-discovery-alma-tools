"""Shared constants for OCLC and Azure AD."""

OCLC_API_BASE_URL = "https://metadata.api.oclc.org/worldcat"
OCLC_OAUTH_URL = "https://oauth.oclc.org/token"
OCLC_OAUTH_SCOPE = "WorldCatMetadataAPI"
BATCH_SIZE = 100

AZURE_AD_ISSUER_BASE = "https://login.microsoftonline.com"
AZURE_AD_DISCOVERY_PATH = "/.well-known/openid-configuration"

SEARCH_FIELD_MAPPING = {
    "ti": "ti",
    "au": "au",
    "se": "se",
    "pu": "pu",
    "pb": "pb",
    "yr": "yr",
    "su": "su",
    "is": "is",
    "bn": "bn",
    "kw": "kw",
}

DEFAULT_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}

ERROR_MESSAGES = {
    "missing_auth": "Authorization header is missing or invalid.",
}
