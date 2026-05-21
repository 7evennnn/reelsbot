import os
import json
import secrets
from datetime import datetime, timedelta

TOKENS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "tokens.json")

def _load_tokens() -> dict:
    if not os.path.exists(TOKENS_FILE):
        return {}
    try:
        with open(TOKENS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def _save_tokens(tokens: dict):
    os.makedirs(os.path.dirname(TOKENS_FILE), exist_ok=True)
    with open(TOKENS_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

def generate_login_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    tokens = _load_tokens()
    
    # Expiration: 15 minutes from now
    expires_at = (datetime.utcnow() + timedelta(minutes=15)).isoformat()
    tokens[token] = {
        "user_id": user_id,
        "expires_at": expires_at
    }
    
    _save_tokens(tokens)
    return token

def verify_login_token(token: str) -> int | None:
    tokens = _load_tokens()
    if token not in tokens:
        return None
    
    info = tokens[token]
    expires_at = datetime.fromisoformat(info["expires_at"])
    
    # Delete token from the store (one-time use)
    del tokens[token]
    _save_tokens(tokens)
    
    if datetime.utcnow() > expires_at:
        return None
        
    return info["user_id"]
