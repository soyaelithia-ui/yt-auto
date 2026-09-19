"""src/scrapers/scp/constants.py - Endpoints, licenses, and defaults for SCP scraping."""

from __future__ import annotations

DEFAULT_LICENSE = "CC BY-SA 3.0"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) YoutubeAutomation/1.0 (SCP Scraper; CC BY-SA 3.0 Compliant)"
)
CROM_GRAPHQL_ENDPOINT = "https://api.crom.avn.sh/graphql"
SCP_WIKI_BASE_URL = "https://scp-wiki.wikidot.com"
SCP_WIKI_ES_BASE_URL = "http://lafundacionscp.wikidot.com"

__all__ = [
    "DEFAULT_LICENSE",
    "DEFAULT_USER_AGENT",
    "CROM_GRAPHQL_ENDPOINT",
    "SCP_WIKI_BASE_URL",
    "SCP_WIKI_ES_BASE_URL",
]
