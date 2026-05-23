"""
ClickUp configuration manager — stores/token management.
"""

import os
import json
from typing import Any

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CONFIG_PATH = os.path.join(CONFIG_DIR, "clickup_config.json")
TOKEN_PATH = os.path.join(CONFIG_DIR, "clickup_token.txt")

from services.logger import info


def load_token() -> str | None:
    """Load the ClickUp personal API token from disk."""
    for path in [TOKEN_PATH, CONFIG_PATH]:
        if os.path.exists(path):
            if path.endswith(".txt"):
                token = open(path).read().strip()
                if token:
                    return token
            elif path.endswith(".json"):
                data = json.load(open(path))
                token = data.get("token", "")
                if token:
                    return token
    return None


def save_token(token: str) -> None:
    """Save the ClickUp personal API token to disk."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(TOKEN_PATH, "w") as f:
        f.write(token.strip())
    info("ClickUp token saved")


def delete_token() -> None:
    """Remove stored ClickUp token."""
    for path in [TOKEN_PATH, CONFIG_PATH]:
        if os.path.exists(path):
            os.remove(path)
    info("ClickUp token deleted")


def is_configured() -> bool:
    return load_token() is not None
