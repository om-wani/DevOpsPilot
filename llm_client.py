"""Shared Azure OpenAI client.

The resource is on the OpenAI v1 endpoint, so this uses the plain `OpenAI`
client with `base_url` and an API key. Do not switch to `AzureOpenAI` and do
not pass `api_version`: this resource rejects both.
"""

import os
from functools import lru_cache

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class ConfigError(RuntimeError):
    """Required Azure OpenAI configuration is missing."""


@lru_cache(maxsize=1)
def get_client():
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    key = os.getenv("AZURE_OPENAI_KEY")
    if not endpoint or not key:
        raise ConfigError("AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_KEY must be set")
    return OpenAI(base_url=endpoint, api_key=key)


def chat_deployment():
    name = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT")
    if not name:
        raise ConfigError("AZURE_OPENAI_CHAT_DEPLOYMENT must be set")
    return name


def embed_deployment():
    name = os.getenv("AZURE_OPENAI_EMBED_DEPLOYMENT")
    if not name:
        raise ConfigError("AZURE_OPENAI_EMBED_DEPLOYMENT must be set")
    return name
