"""Backward-compatible names. The optional online integration lives in `foundry_client.py`."""
from .foundry_client import REQUIRED_ENV, SYSTEM_PROMPT, FoundryClient, online_generator_from_env

AzureChatGenerator = FoundryClient

__all__ = ["REQUIRED_ENV", "SYSTEM_PROMPT", "AzureChatGenerator", "FoundryClient", "online_generator_from_env"]
