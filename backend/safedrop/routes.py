import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import bcrypt
from flask import Blueprint, current_app, jsonify, request, send_file
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import User, StoredFile, ShareLink, AuditEvent
from .security import clean_filename, new_share_token, hash_token, is_expired

api = Blueprint("api", __name__)


def error(message, status):
    return jsonify({"error": message}), status


def audit(event_type, user_id=None, file_id=None, detail=""):
    db.session.add(AuditEvent(user_id=user_id, file_id=file_id, event_type=event_type, detail=detail[:500]))


def current_user_id():
    try:
        return int(get_jwt_identity())
    except (TypeError, ValueError):
        return None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


@api.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    if len(email) > 254 or "@" not in email or email.startswith("@") or email.endswith("@"):
        return error("Enter a valid email address.", 400)
    if not isinstance(password, str) or len(password) < 10 or len(password) > 128:
        return error("Password must be 10–128 characters.", 400)
    user = User(email=email, password_hash=hash_password(password))
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error("An account with this email already exists.", 409)
    audit("register", user.id, detail="Account created")
    db.session.commit()
    return jsonify({"message": "Account created. Please log in."}), 201


@api.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip().lower()
    password = data.get("password", "")
    user = User.query.filter_by(email=email).first()
    if not user or not isinstance(password, str) or not verify_password(user.password_hash, password):
        return error("Invalid email or password.", 401)
    token = create_access_token(identity=str(user.id))
    audit("login", user.id, detail="Successful login")
    db.session.commit()
    return jsonify({"access_token": token, "user": {"id": user.id, "email": user.email}})


@api.get("/auth/me")
@jwt_required()
def current_user():
    uid = current_user_id()
    user = User.query.get(uid)
    if not user:
        return error("User not found.", 404)
    return jsonify({"user": {"id": user.id, "email": user.email}})


@api.post("/auth/logout")
@jwt_required()
def logout():
    uid = current_user_id()
    audit("logout", uid, detail="User logged out")
    db.session.commit()
    return jsonify({"message": "Logged out successfully."})


@api.get("/files")
@jwt_required()
def list_files():
    uid = current_user_id()
    files = StoredFile.query.filter_by(owner_id=uid).order_by(StoredFile.created_at.desc()).all()
    return jsonify({"files": [file_json(f) for f in files]})


@api.get("/files/<int:file_id>")
@jwt_required()
def get_file(file_id):
    uid = current_user_id()
    record = StoredFile.query.filter_by(id=file_id, owner_id=uid).first()
    if not record:
        return error("File not found.", 404)
    return jsonify({"file": file_json(record)})


@api.get("/files/<int:file_id>/download")
@jwt_required()
def download_file(file_id):
    uid = current_user_id()
    record = StoredFile.query.filter_by(id=file_id, owner_id=uid).first()
    if not record:
        return error("File not found.", 404)
    path = Path(current_app.config["UPLOAD_FOLDER"]) / record.storage_name
    if not path.is_file():
        return error("File is no longer available.", 404)
    audit("file_downloaded", uid, record.id, "Downloaded by owner")
    db.session.commit()
    return send_file(path, as_attachment=True, download_name=record.original_name, mimetype=record.mime_type or "application/octet-stream", max_age=0)


def file_json(f):
    return {"id": f.id, "name": f.original_name, "size_bytes": f.size_bytes, "mime_type": f.mime_type,
            "created_at": f.created_at.isoformat() if f.created_at else None}


@api.post("/files")
@jwt_required()
def upload_file():
    uid = current_user_id()
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return error("Choose a file to upload.", 400)
    safe_name = clean_filename(uploaded.filename)
    if not safe_name:
        audit("upload_rejected", uid, detail="Unsupported or unsafe filename")
        db.session.commit()
        return error("Unsupported file type or filename. Allowed: PDF, text, CSV, common images, Office files, ZIP.", 400)
    storage_name = __import__("secrets").token_hex(24)
    target = Path(current_app.config["UPLOAD_FOLDER"]) / storage_name
    try:
        uploaded.save(target)
        size = target.stat().st_size
        if size <= 0:
            target.unlink(missing_ok=True)
            return error("Empty files are not accepted.", 400)
        if size > current_app.config["MAX_CONTENT_LENGTH"]:
            target.unlink(missing_ok=True)
            return error("File is larger than the configured upload limit.", 413)
        record = StoredFile(owner_id=uid, original_name=safe_name, storage_name=storage_name,
                            size_bytes=size, mime_type=uploaded.mimetype or "application/octet-stream")
        db.session.add(record)
        db.session.flush()
        audit("file_uploaded", uid, record.id, f"Uploaded {safe_name} ({size} bytes)")
        db.session.commit()
        return jsonify({"file": file_json(record)}), 201
    except Exception:
        db.session.rollback()
        target.unlink(missing_ok=True)
        current_app.logger.exception("File upload failed")
        return error("Upload failed. Please try again.", 500)


@api.delete("/files/<int:file_id>")
@jwt_required()
def delete_file(file_id):
    uid = current_user_id()
    record = StoredFile.query.filter_by(id=file_id, owner_id=uid).first()
    if not record:
        audit("file_delete_denied", uid, file_id, "Missing file or not owner")
        db.session.commit()
        return error("File not found.", 404)
    target = Path(current_app.config["UPLOAD_FOLDER"]) / record.storage_name
    audit("file_deleted", uid, record.id, f"Deleted {record.original_name}")
    ShareLink.query.filter_by(file_id=record.id).delete()
    db.session.delete(record)
    db.session.commit()
    target.unlink(missing_ok=True)
    return jsonify({"message": "File deleted."})


@api.post("/files/<int:file_id>/shares")
@jwt_required()
def create_share(file_id):
    uid = current_user_id()
    record = StoredFile.query.filter_by(id=file_id, owner_id=uid).first()
    if not record:
        return error("File not found.", 404)
    data = request.get_json(silent=True) or {}
    try:
        hours = int(data.get("expires_in_hours", 24))
    except (TypeError, ValueError):
        return error("expires_in_hours must be a number between 1 and 168.", 400)
    if not 1 <= hours <= 168:
        return error("Share links can expire in 1–168 hours.", 400)
    token, token_digest = new_share_token()
    expiry = datetime.now(timezone.utc) + timedelta(hours=hours)
    share = ShareLink(file_id=record.id, owner_id=uid, token_hash=token_digest, expires_at=expiry)
    db.session.add(share)
    audit("share_created", uid, record.id, f"Share expires in {hours} hours")
    db.session.commit()
    return jsonify({"share_id": share.id, "url": f"{request.host_url.rstrip('/')}/api/share/{token}",
                    "expires_at": expiry.isoformat(), "expires_in_hours": hours}), 201


@api.delete("/shares/<int:share_id>")
@jwt_required()
def revoke_share(share_id):
    uid = current_user_id()
    share = ShareLink.query.filter_by(id=share_id, owner_id=uid).first()
    if not share:
        return error("Share link not found.", 404)
    share.revoked = True
    audit("share_revoked", uid, share.file_id, f"Revoked share {share_id}")
    db.session.commit()
    return jsonify({"message": "Share link revoked."})


@api.get("/share/<token>")
def download_shared(token):
    digest = hash_token(token)
    share = ShareLink.query.filter_by(token_hash=digest).first()
    if not share or share.revoked or is_expired(share.expires_at):
        audit("share_access_denied", detail="Invalid, revoked, or expired link")
        db.session.commit()
        return error("This share link is invalid or has expired.", 404)
    record = db.session.get(StoredFile, share.file_id)
    if not record:
        return error("File not found.", 404)
    path = Path(current_app.config["UPLOAD_FOLDER"]) / record.storage_name
    if not path.is_file():
        return error("File is no longer available.", 404)
    audit("file_downloaded", share.owner_id, record.id, "Downloaded through share link")
    db.session.commit()
    return send_file(path, as_attachment=True, download_name=record.original_name, mimetype="application/octet-stream", max_age=0)


@api.get("/audit")
@jwt_required()
def audit_log():
    uid = current_user_id()
    events = AuditEvent.query.filter_by(user_id=uid).order_by(AuditEvent.created_at.desc()).limit(100).all()
    return jsonify({"events": [{"id": e.id, "event_type": e.event_type, "file_id": e.file_id,
        "detail": e.detail, "created_at": e.created_at.isoformat() if e.created_at else None} for e in events]})
