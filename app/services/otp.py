"""Phone OTP — swap OTP_PROVIDER when a real SMS API is ready."""

from __future__ import annotations

from datetime import timedelta
import hashlib
import logging
import secrets
from typing import Protocol

import httpx
from fastapi import HTTPException
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from .. import models
from ..config import settings
from ..phone import normalize_phone
from ..security import create_access_token, decode_access_token, utcnow

log = logging.getLogger("qisas.otp")


class OtpSender(Protocol):
    name: str

    def send(self, phone: str, code: str) -> None: ...


class DevOtpSender:
    name = "dev"

    def send(self, phone: str, code: str) -> None:
        log.info("OTP (dev, not sent) phone=%s code=%s", phone, code)


class HttpOtpSender:
    """Skeleton for Beem / Africa's Talking / Twilio. Fill URL + payload when keys exist."""

    name: str

    def __init__(self, name: str) -> None:
        self.name = name

    def send(self, phone: str, code: str) -> None:
        if not settings.otp_api_key:
            raise HTTPException(status_code=503, detail="OTP provider is not configured")
        url = {
            "beem": "https://api.beem.africa/v1/send",
            "africastalking": "https://api.africastalking.com/version1/messaging",
            "twilio": "https://api.twilio.com/2010-04-01/Accounts.json",
        }.get(self.name)
        if not url:
            raise HTTPException(status_code=503, detail=f"Unknown OTP provider: {self.name}")
        # Real integration: map each vendor's JSON here. Dev mode never reaches this.
        try:
            httpx.post(
                url,
                json={
                    "to": phone,
                    "from": settings.otp_sender_id,
                    "message": f"Qisas code: {code}",
                    "code": code,
                },
                headers={"Authorization": f"Bearer {settings.otp_api_key}"},
                timeout=12,
            ).raise_for_status()
        except httpx.HTTPError as exc:
            log.exception("OTP send failed")
            raise HTTPException(status_code=502, detail="Could not send verification SMS") from exc


def get_sender() -> OtpSender:
    name = (settings.otp_provider or "dev").strip().lower()
    if name in ("", "dev", "stub", "mock"):
        return DevOtpSender()
    return HttpOtpSender(name)


def _hash_code(code: str) -> str:
    return hashlib.sha256(f"{settings.secret_key}:{code.strip()}".encode("utf-8")).hexdigest()


def _nid() -> str:
    return f"otp_{secrets.token_hex(8)}"


def send_challenge(db: Session, raw_phone: str) -> dict:
    phone = normalize_phone(raw_phone)
    if len("".join(ch for ch in phone if ch.isdigit())) < 9:
        raise HTTPException(status_code=400, detail="Enter a valid phone number")

    now = utcnow()
    latest = (
        db.query(models.OtpChallenge)
        .filter(models.OtpChallenge.phone == phone)
        .order_by(models.OtpChallenge.created_at.desc())
        .first()
    )
    wait = settings.otp_resend_seconds
    if latest and (now - latest.created_at).total_seconds() < wait:
        left = int(wait - (now - latest.created_at).total_seconds())
        raise HTTPException(status_code=429, detail=f"Wait {left}s before requesting another code")

    code = f"{secrets.randbelow(1_000_000):06d}"
    sender = get_sender()
    sender.send(phone, code)
    row = models.OtpChallenge(
        id=_nid(),
        phone=phone,
        code_hash=_hash_code(code),
        provider=sender.name,
        expires_at=now + timedelta(seconds=settings.otp_expire_seconds),
    )
    db.add(row)
    db.commit()
    return {
        "ok": True,
        "challengeId": row.id,
        "phone": phone,
        "expiresIn": settings.otp_expire_seconds,
        "resendIn": settings.otp_resend_seconds,
        "provider": sender.name,
        "devAcceptAny": sender.name == "dev" and settings.otp_dev_accept_any,
    }


def verify_challenge(db: Session, raw_phone: str, code: str, challenge_id: str | None = None) -> dict:
    phone = normalize_phone(raw_phone)
    entered = (code or "").strip()
    if not entered:
        raise HTTPException(status_code=400, detail="Enter the code sent to your phone")

    q = db.query(models.OtpChallenge).filter(models.OtpChallenge.phone == phone)
    if challenge_id:
        q = q.filter(models.OtpChallenge.id == challenge_id)
    row = q.order_by(models.OtpChallenge.created_at.desc()).first()
    if not row:
        raise HTTPException(status_code=400, detail="Request a new code")
    if row.verified_at:
        raise HTTPException(status_code=400, detail="This code was already used")
    if row.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Code expired. Request a new one")

    accept_any = row.provider == "dev" and settings.otp_dev_accept_any
    if not accept_any and not secrets.compare_digest(row.code_hash, _hash_code(entered)):
        raise HTTPException(status_code=400, detail="Incorrect code")

    row.verified_at = utcnow()
    db.commit()
    ticket = create_access_token(
        phone,
        {
            "typ": "otp",
            "phone": phone,
            "cid": row.id,
            "exp": utcnow() + timedelta(minutes=20),
        },
    )
    return {"ok": True, "otpTicket": ticket, "phone": phone}


def require_otp_ticket(ticket: str | None, raw_phone: str) -> str:
    phone = normalize_phone(raw_phone)
    if not settings.otp_required:
        return phone
    if not ticket:
        raise HTTPException(status_code=403, detail="Verify your phone number first")
    try:
        payload = decode_access_token(ticket)
    except InvalidTokenError:
        raise HTTPException(status_code=403, detail="Phone verification expired. Try again") from None
    if payload.get("typ") != "otp":
        raise HTTPException(status_code=403, detail="Verify your phone number first")
    ticket_phone = normalize_phone(str(payload.get("phone") or payload.get("sub") or ""))
    if ticket_phone != phone:
        raise HTTPException(status_code=403, detail="Phone does not match verification")
    return phone
