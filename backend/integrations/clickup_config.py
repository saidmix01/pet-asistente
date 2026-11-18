"""
ClickUp configuration manager — stores/token management.
"""

import os
import sys
import json
from typing import Any

from services.logger import info


from db.database import get_data_dir


CONFIG_DIR = get_data_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "clickup_config.json")
TOKEN_PATH = os.path.join(CONFIG_DIR, "clickup_token.txt")


def load_token() -> str | None:
    """Load the ClickUp personal API token. Checks SQLite config first, then file."""
    # Try SQLite config store first
    try:
        from services.config_store import get_clickup_token
        token = get_clickup_token()
        if token:
            return token
    except Exception:
        pass

    # Fallback to file
    for path in [TOKEN_PATH, CONFIG_PATH]:
        if os.path.exists(path):
            if path.endswith(".txt"):
                with open(path, encoding="utf-8") as f:
                    token = f.read().strip()
                if token:
                    return token
            elif path.endswith(".json"):
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                token = data.get("token", "")
                if token:
                    return token
    return None


def save_token(token: str) -> None:
    """Save the ClickUp personal API token to SQLite + file backup."""
    # Save to SQLite config store
    try:
        from services.config_store import set_clickup_token
        set_clickup_token(token.strip())
    except Exception:
        pass
    # Also save to file as backup
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(TOKEN_PATH, "w", encoding="utf-8") as f:
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
