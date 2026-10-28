import hashlib
import secrets
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"pdf", "txt", "csv", "png", "jpg", "jpeg", "gif", "webp", "docx", "xlsx", "pptx", "zip"}


def clean_filename(name):
    # Remove path components before sanitizing; never trust client-supplied paths.
    name = (name or "").replace("\\", "/").split("/")[-1]
    safe = secure_filename(name)[:180]
    if not safe or "." not in safe:
        return None
    ext = safe.rsplit(".", 1)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return None
    return safe


def new_share_token():
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest()


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def is_expired(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt <= datetime.now(timezone.utc)
