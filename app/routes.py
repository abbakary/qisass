from __future__ import annotations

from datetime import timedelta
import json
import secrets
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import models
from .database import DATA_DIR, SessionLocal, get_db
from .deps import (
    can_play_episode,
    get_admin,
    get_current_user,
    get_current_user_optional,
    refresh_subscription_status,
    user_has_vip,
)
from .phone import normalize_phone, phones_match
from .security import create_access_token, hash_password, utcnow, verify_password
from .serialize import (
    PLANS,
    category_out,
    comment_out,
    community_out,
    episode_out,
    favorite_out,
    notification_out,
    progress_out,
    series_out,
    session_out,
    sponsorship_out,
    subscription_out,
    unlock_out,
    unlocks_out,
    sponsorships_out,
    user_out,
    video_job_out,
)
from .services.ai_engine import generate_story, generate_storyboard
from .services.otp import send_challenge, verify_challenge
from .seed import seed_all
from .video_poster import extract_video_poster, persist_poster_url, write_fallback_poster
from .monetize import (
    STARTER_BUNDLE_COUNT,
    STARTER_BUNDLE_TZS,
    bump_streak,
    analytics_report,
    monetize_kpis,
    FREE_EPISODE_COUNT,
    series_price,
    story_of_week,
    track_event,
    user_owns_series,
)

router = APIRouter()
UPLOADS = DATA_DIR / "uploads"


def nid(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


VIDEO_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".m4v", ".avi"}
AUDIO_SUFFIXES = {".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac", ".opus"}


def _suffix(name: str | None) -> str:
    return Path(name or "").suffix.lower()


def _looks_like_video(file: Optional[UploadFile], media_type: str, url: str) -> bool:
    if (media_type or "").upper() == "VIDEO":
        return True
    if file and file.content_type and file.content_type.startswith("video"):
        return True
    return _suffix(file.filename if file else url) in VIDEO_SUFFIXES


def _looks_like_audio(file: Optional[UploadFile], media_type: str) -> bool:
    if (media_type or "").upper() == "AUDIO":
        return True
    if file and file.content_type and file.content_type.startswith("audio"):
        return True
    return _suffix(file.filename if file else "") in AUDIO_SUFFIXES


async def save_upload(file: UploadFile, prefix: str) -> str:
    UPLOADS.mkdir(parents=True, exist_ok=True)
    suffix = _suffix(file.filename) or ".bin"
    name = f"{prefix}_{uuid4().hex[:10]}{suffix}"
    dest = UPLOADS / name
    with dest.open("wb") as out:
        while True:
            chunk = await file.read(256 * 1024)
            if not chunk:
                break
            out.write(chunk)
    await file.close()
    return f"/media/uploads/{name}"


def _fill_missing_poster(episode_id: str, media_url: str) -> None:
    poster = extract_video_poster(media_url)
    if not poster:
        return
    db = SessionLocal()
    try:
        row = db.get(models.Episode, episode_id)
        if row:
            row.poster_url = poster
            db.commit()
    finally:
        db.close()


class PhoneIn(BaseModel):
    phone: str


class LoginIn(BaseModel):
    phone: Optional[str] = None
    identifier: Optional[str] = None
    password: str
    otpTicket: Optional[str] = None


class RegisterIn(BaseModel):
    name: str
    phone: str
    password: str
    language: str = "sw"
    otpTicket: Optional[str] = None


class OtpSendIn(BaseModel):
    phone: str


class OtpVerifyIn(BaseModel):
    phone: str
    code: str
    challengeId: Optional[str] = None


class CommentIn(BaseModel):
    id: Optional[str] = None
    seriesId: str
    episodeId: Optional[str] = None
    text: str
    parentId: Optional[str] = None


class ShareIn(BaseModel):
    seriesId: Optional[str] = None
    episodeId: Optional[str] = None
    channel: str = "copy"


class ProgressIn(BaseModel):
    episodeId: str
    positionSec: int = 0
    completed: bool = False


class SubscribeIn(BaseModel):
    plan: str
    paymentMethod: str = "M-Pesa"


class GrantIn(BaseModel):
    userId: str
    plan: str


class StatusIn(BaseModel):
    status: str


class CategoryIn(BaseModel):
    id: Optional[str] = None
    slug: str
    name: str
    nameSw: str
    order: int = 0
    image: Optional[str] = None
    iconName: Optional[str] = None


class SeriesIn(BaseModel):
    id: Optional[str] = None
    slug: str
    title: str
    titleSw: str
    description: str = ""
    descriptionSw: str = ""
    categoryId: str
    coverGradient: str = "teal"
    image: Optional[str] = None
    backdropImage: Optional[str] = None
    featured: bool = False
    published: bool = True
    tags: Optional[list[str]] = None
    unlockPriceTzs: Optional[int] = None
    isStoryOfWeek: bool = False


class EpisodeIn(BaseModel):
    id: Optional[str] = None
    seriesId: str
    seasonNumber: int = 1
    order: int = 1
    title: str
    titleSw: str
    description: Optional[str] = None
    descriptionSw: Optional[str] = None
    durationSec: int = 120
    mediaUrl: str = ""
    mediaType: str = "AUDIO"
    posterUrl: Optional[str] = None
    isFree: bool = True
    published: bool = True
    authorName: Optional[str] = None
    authorPhone: Optional[str] = None
    fromVideoJob: bool = False


class UserCreateIn(BaseModel):
    name: str
    phone: str
    email: str
    password: str
    role: str = "USER"
    language: str = "sw"


class UserPatchIn(BaseModel):
    name: Optional[str] = None
    language: Optional[str] = None
    role: Optional[str] = None
    subscriptionStatus: Optional[str] = None


class NotificationIn(BaseModel):
    title: str
    titleSw: str
    message: str
    messageSw: str
    type: str = "ANNOUNCEMENT"
    targetUserId: Optional[str] = "ALL"
    targetPhone: Optional[str] = None
    targetAudience: str = "ALL"
    actionUrl: Optional[str] = None


class VideoJobIn(BaseModel):
    id: Optional[str] = None
    seriesId: str = ""
    episodeId: Optional[str] = None
    episodeTitle: Optional[str] = None
    format: str = "VERTICAL_9_16"
    engine: str = "qisas-ai"
    brief: str = ""
    titleSw: str = ""
    titleEn: str = ""
    storyboard: list[dict[str, Any]] = Field(default_factory=list)
    voice: str = "sw-TZ-standard"
    durationSec: Optional[int] = 120
    status: Optional[str] = None
    progress: Optional[int] = None
    currentStep: Optional[str] = None
    outputUrl: Optional[str] = None
    posterUrl: Optional[str] = None
    logs: Optional[str] = None


class AIStoryIn(BaseModel):
    prompt: str
    categorySlug: str = "manabii"
    targetDurationSec: int = 120
    tone: str = "inspiring"


class AIStoryboardIn(BaseModel):
    brief: str
    targetDurationSec: int = 120


class AIPublishIn(BaseModel):
    story: dict[str, Any]
    mediaUrl: Optional[str] = None
    isFree: bool = True


def liked_series_ids(db: Session, user: Optional[models.User]) -> set[str]:
    if not user:
        return set()
    rows = db.query(models.SeriesLike.series_id).filter(models.SeriesLike.user_id == user.id).all()
    return {r[0] for r in rows}


def liked_episode_ids(db: Session, user: Optional[models.User]) -> set[str]:
    if not user:
        return set()
    rows = db.query(models.EpisodeLike.episode_id).filter(models.EpisodeLike.user_id == user.id).all()
    return {r[0] for r in rows}


def liked_comment_ids(db: Session, user: Optional[models.User]) -> set[str]:
    if not user:
        return set()
    rows = db.query(models.CommentLike.comment_id).filter(models.CommentLike.user_id == user.id).all()
    return {r[0] for r in rows}


def find_user_by_phone(db: Session, phone: str) -> Optional[models.User]:
    users = db.query(models.User).all()
    return next((u for u in users if phones_match(u.phone, phone)), None)


def active_sub(db: Session, user: models.User) -> Optional[models.Subscription]:
    refresh_subscription_status(db, user)
    return (
        db.query(models.Subscription)
        .filter(models.Subscription.user_id == user.id, models.Subscription.status == "ACTIVE")
        .order_by(models.Subscription.end_date.desc())
        .first()
    )


@router.post("/auth/otp/send")
def auth_otp_send(body: OtpSendIn, db: Session = Depends(get_db)):
    return send_challenge(db, body.phone)


@router.post("/auth/otp/verify")
def auth_otp_verify(body: OtpVerifyIn, db: Session = Depends(get_db)):
    return verify_challenge(db, body.phone, body.code, body.challengeId)


@router.post("/auth/check-phone")
def check_phone(body: PhoneIn, db: Session = Depends(get_db)):
    user = find_user_by_phone(db, body.phone)
    if not user:
        return {"exists": False}
    return {
        "exists": True,
        "user": {"id": user.id, "name": user.name, "phone": user.phone, "role": user.role},
    }


@router.post("/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    ident = (body.phone or body.identifier or "").strip()
    user = find_user_by_phone(db, ident)
    if not user:
        user = db.query(models.User).filter(models.User.email == ident.lower()).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid phone or password")
    refresh_subscription_status(db, user)
    token = create_access_token(user.id, {"role": user.role})
    return {"token": token, "user": session_out(user, active_sub(db, user))}


@router.post("/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    phone = normalize_phone(body.phone)
    if find_user_by_phone(db, phone):
        raise HTTPException(status_code=409, detail="Phone already registered")
    digits = "".join(ch for ch in phone if ch.isdigit()) or "user"
    email = f"{digits}@qisas.local"
    if db.query(models.User).filter(models.User.email == email).first():
        email = f"{digits}-{nid('u')}@qisas.local"
    user = models.User(
        id=nid("user"),
        name=body.name.strip(),
        phone=phone,
        email=email,
        password_hash=hash_password(body.password),
        role="USER",
        language=body.language or "sw",
        subscription_status="FREE_TIER",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    token = create_access_token(user.id, {"role": user.role})
    return {"token": token, "user": session_out(user)}


@router.get("/auth/me")
def me(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    refresh_subscription_status(db, user)
    return session_out(user, active_sub(db, user))


@router.patch("/auth/me")
def patch_me(body: UserPatchIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.name is not None:
        user.name = body.name
    if body.language is not None:
        user.language = body.language
    db.commit()
    return session_out(user, active_sub(db, user))


@router.get("/bootstrap")
def bootstrap(
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_current_user_optional),
):
    if user:
        refresh_subscription_status(db, user)
    s_liked = liked_series_ids(db, user)
    e_liked = liked_episode_ids(db, user)
    is_admin = bool(user and user.role == "ADMIN")
    series_rows = db.query(models.Series).all() if is_admin else (
        db.query(models.Series).filter(models.Series.published.is_(True)).all()
    )
    published_ids = {s.id for s in series_rows}
    if is_admin:
        episode_rows = db.query(models.Episode).all()
    elif published_ids:
        episode_rows = (
            db.query(models.Episode)
            .filter(models.Episode.published.is_(True), models.Episode.series_id.in_(published_ids))
            .all()
        )
    else:
        episode_rows = []
    payload: dict[str, Any] = {
        "categories": [category_out(c) for c in db.query(models.Category).order_by(models.Category.order).all()],
        "series": [series_out(s, s.id in s_liked) for s in series_rows],
        "episodes": [episode_out(e, e.id in e_liked) for e in episode_rows],
        "plans": [{"id": k, **v} for k, v in PLANS.items()],
        "starterBundle": {
            "id": "STARTER_BUNDLE",
            "seriesCount": STARTER_BUNDLE_COUNT,
            "amountTzs": STARTER_BUNDLE_TZS,
            "name": "Starter bundle",
            "planNameSw": "Kifurushi cha kuanza — 3 hadithi kwa bei ya 2",
        },
    }
    sow = story_of_week(db)
    payload["storyOfWeekId"] = sow.id if sow else None
    for item in payload["series"]:
        item["isStoryOfWeek"] = bool(sow and item.get("id") == sow.id)
    if user:
        bump_streak(db, user)
        db.commit()
        payload["me"] = session_out(user, active_sub(db, user))
        payload["favorites"] = [favorite_out(f) for f in db.query(models.Favorite).filter(models.Favorite.user_id == user.id).all()]
        payload["progress"] = [progress_out(p) for p in db.query(models.Progress).filter(models.Progress.user_id == user.id).all()]
        payload["mySubscriptions"] = [
            subscription_out(s) for s in db.query(models.Subscription).filter(models.Subscription.user_id == user.id).all()
        ]
        payload["unlocks"] = unlocks_out(
            db, db.query(models.SeriesUnlock).filter(models.SeriesUnlock.user_id == user.id).all()
        )
        payload["notifications"] = [
            notification_out(n)
            for n in db.query(models.Notification).all()
            if n.target_user_id in (None, "ALL", user.id) or n.target_phone == user.phone
        ]
        if user.role == "ADMIN":
            c_liked = liked_comment_ids(db, user)
            payload["comments"] = [comment_out(c, c.id in c_liked) for c in db.query(models.Comment).all()]
            payload["users"] = [user_out(u) for u in db.query(models.User).all()]
            payload["subscriptions"] = [subscription_out(s) for s in db.query(models.Subscription).all()]
            payload["communityUploads"] = [community_out(c) for c in db.query(models.CommunityUpload).all()]
            payload["videoJobs"] = [video_job_out(j) for j in db.query(models.VideoJob).all()]
            payload["allNotifications"] = [notification_out(n) for n in db.query(models.Notification).all()]
            payload["sponsorships"] = sponsorships_out(db, db.query(models.Sponsorship).all())
            payload["allUnlocks"] = unlocks_out(
                db,
                db.query(models.SeriesUnlock).order_by(models.SeriesUnlock.created_at.desc()).all(),
            )
    return payload


@router.post("/categories", dependencies=[Depends(get_admin)])
def create_category(body: CategoryIn, db: Session = Depends(get_db)):
    if db.query(models.Category).filter(models.Category.slug == body.slug).first():
        raise HTTPException(status_code=409, detail="Slug exists")
    row = models.Category(
        id=body.id or nid("cat"),
        slug=body.slug,
        name=body.name,
        name_sw=body.nameSw,
        order=body.order,
        image=body.image,
        icon_name=body.iconName,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return category_out(row)


@router.patch("/categories/{item_id}", dependencies=[Depends(get_admin)])
def patch_category(item_id: str, body: dict[str, Any], db: Session = Depends(get_db)):
    row = db.get(models.Category, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    mapping = {"nameSw": "name_sw", "iconName": "icon_name"}
    for k, v in body.items():
        setattr(row, mapping.get(k, k), v)
    db.commit()
    return category_out(row)


@router.delete("/categories/{item_id}", dependencies=[Depends(get_admin)])
def delete_category(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Category, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/series", dependencies=[Depends(get_admin)])
def create_series(body: SeriesIn, db: Session = Depends(get_db)):
    if db.query(models.Series).filter(models.Series.slug == body.slug).first():
        raise HTTPException(status_code=409, detail="Slug exists")
    row = models.Series(
        id=body.id or nid("ser"),
        slug=body.slug,
        title=body.title,
        title_sw=body.titleSw,
        description=body.description,
        description_sw=body.descriptionSw,
        category_id=body.categoryId,
        cover_gradient=body.coverGradient,
        image=body.image,
        backdrop_image=body.backdropImage or body.image,
        featured=body.featured,
        published=body.published,
        tags=json.dumps(body.tags or []),
        unlock_price_tzs=body.unlockPriceTzs or 1000,
        is_story_of_week=body.isStoryOfWeek,
    )
    if body.isStoryOfWeek:
        for other in db.query(models.Series).all():
            other.is_story_of_week = False
    db.add(row)
    db.commit()
    db.refresh(row)
    return series_out(row)


@router.patch("/series/{item_id}", dependencies=[Depends(get_admin)])
def patch_series(item_id: str, body: dict[str, Any], db: Session = Depends(get_db)):
    row = db.get(models.Series, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    mapping = {
        "titleSw": "title_sw",
        "descriptionSw": "description_sw",
        "categoryId": "category_id",
        "coverGradient": "cover_gradient",
        "backdropImage": "backdrop_image",
        "seasonsCount": "seasons_count",
        "shareCount": "share_count",
        "unlockPriceTzs": "unlock_price_tzs",
        "isStoryOfWeek": "is_story_of_week",
        "sponsoredPlays": "sponsored_plays",
        "sponsorPool": "sponsor_pool",
    }
    if body.get("isStoryOfWeek"):
        for other in db.query(models.Series).filter(models.Series.id != item_id).all():
            other.is_story_of_week = False
    for k, v in body.items():
        if k == "tags":
            row.tags = json.dumps(v)
        else:
            setattr(row, mapping.get(k, k), v)
    db.commit()
    return series_out(row)


@router.delete("/series/{item_id}", dependencies=[Depends(get_admin)])
def delete_series(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Series, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.query(models.Episode).filter(models.Episode.series_id == item_id).delete()
    db.query(models.Comment).filter(models.Comment.series_id == item_id).delete()
    db.query(models.Favorite).filter(models.Favorite.series_id == item_id).delete()
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/series/{item_id}/toggle-featured", dependencies=[Depends(get_admin)])
def toggle_featured(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Series, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.featured = not row.featured
    db.commit()
    return {"featured": row.featured}


@router.post("/series/{item_id}/toggle-published", dependencies=[Depends(get_admin)])
def toggle_series_published(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Series, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.published = not row.published
    db.commit()
    return {"published": row.published}


@router.post("/series/{item_id}/like")
def like_series(item_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = db.get(models.Series, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    existing = (
        db.query(models.SeriesLike)
        .filter(models.SeriesLike.user_id == user.id, models.SeriesLike.series_id == item_id)
        .first()
    )
    if existing:
        db.delete(existing)
        row.likes = max(0, (row.likes or 0) - 1)
        liked = False
    else:
        db.add(models.SeriesLike(id=nid("slike"), user_id=user.id, series_id=item_id))
        row.likes = (row.likes or 0) + 1
        liked = True
    db.commit()
    return {"liked": liked, "likes": row.likes}


@router.post("/series/{item_id}/view")
def view_series(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Series, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.views = (row.views or 0) + 1
    db.commit()
    return {"views": row.views}


@router.post("/episodes", dependencies=[Depends(get_admin)])
def create_episode(body: EpisodeIn, db: Session = Depends(get_db)):
    if not body.mediaUrl:
        raise HTTPException(status_code=400, detail="mediaUrl or file upload is required")
    row = models.Episode(
        id=body.id or nid("ep"),
        series_id=body.seriesId,
        season_number=body.seasonNumber,
        order=body.order,
        title=body.title,
        title_sw=body.titleSw,
        description=body.description,
        description_sw=body.descriptionSw,
        duration_sec=body.durationSec,
        media_url=body.mediaUrl,
        media_type=body.mediaType,
        poster_url=body.posterUrl,
        is_free=True if body.order <= FREE_EPISODE_COUNT else body.isFree,
        published=body.published,
        author_name=body.authorName,
        author_phone=body.authorPhone,
        from_video_job=body.fromVideoJob,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return episode_out(row)


@router.post("/episodes/upload", dependencies=[Depends(get_admin)])
async def upload_episode(
    background_tasks: BackgroundTasks,
    seriesId: str = Form(...),
    title: str = Form(...),
    titleSw: str = Form(...),
    order: int = Form(1),
    mediaType: str = Form("AUDIO"),
    durationSec: int = Form(120),
    isFree: str = Form("true"),
    published: str = Form("true"),
    description: str = Form(""),
    descriptionSw: str = Form(""),
    mediaUrl: str = Form(""),
    file: Optional[UploadFile] = File(None),
    poster: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    url = mediaUrl.strip()
    uploaded = file if file and file.filename else None
    if uploaded:
        url = await save_upload(uploaded, "ep")
        if _looks_like_video(uploaded, mediaType, url):
            mediaType = "VIDEO"
        elif _looks_like_audio(uploaded, mediaType):
            mediaType = "AUDIO"
    if not url:
        raise HTTPException(status_code=400, detail="Provide a file upload or a media URL")
    poster_url = None
    if poster and poster.filename:
        poster_url = persist_poster_url(await save_upload(poster, "poster"))
    row = models.Episode(
        id=nid("ep"),
        series_id=seriesId,
        order=order,
        title=title,
        title_sw=titleSw,
        description=description or None,
        description_sw=descriptionSw or None,
        duration_sec=durationSec,
        media_url=url,
        media_type=mediaType,
        poster_url=poster_url or write_fallback_poster(int(order) if order else 1),
        is_free=True if int(order) <= FREE_EPISODE_COUNT else str(isFree).lower() in {"1", "true", "yes", "on"},
        published=str(published).lower() in {"1", "true", "yes", "on"},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    if not poster_url and _looks_like_video(uploaded, mediaType, url):
        background_tasks.add_task(_fill_missing_poster, row.id, url)
    return episode_out(row)


@router.get("/episodes/{item_id}/access")
def episode_access(
    item_id: str,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_current_user_optional),
):
    row = db.get(models.Episode, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    allowed = can_play_episode(db, row, user)
    return {
        "allowed": allowed,
        "isFree": row.is_free,
        "vip": user_has_vip(db, user) if user else False,
        "reason": None if allowed else "UNLOCK_REQUIRED",
    }


@router.patch("/episodes/{item_id}", dependencies=[Depends(get_admin)])
def patch_episode(item_id: str, body: dict[str, Any], db: Session = Depends(get_db)):
    row = db.get(models.Episode, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    mapping = {
        "seriesId": "series_id",
        "seasonNumber": "season_number",
        "titleSw": "title_sw",
        "descriptionSw": "description_sw",
        "durationSec": "duration_sec",
        "mediaUrl": "media_url",
        "mediaType": "media_type",
        "posterUrl": "poster_url",
        "isFree": "is_free",
        "authorName": "author_name",
        "authorPhone": "author_phone",
        "fromVideoJob": "from_video_job",
        "shareCount": "share_count",
    }
    for k, v in body.items():
        setattr(row, mapping.get(k, k), v)
    db.commit()
    return episode_out(row)


@router.delete("/episodes/{item_id}", dependencies=[Depends(get_admin)])
def delete_episode(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Episode, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/episodes/{item_id}/toggle-free", dependencies=[Depends(get_admin)])
def toggle_free(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Episode, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.is_free = not row.is_free
    db.commit()
    return {"isFree": row.is_free}


@router.post("/episodes/{item_id}/toggle-published", dependencies=[Depends(get_admin)])
def toggle_ep_published(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Episode, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.published = not row.published
    db.commit()
    return {"published": row.published}


@router.post("/episodes/{item_id}/like")
def like_episode(item_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = db.get(models.Episode, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    existing = (
        db.query(models.EpisodeLike)
        .filter(models.EpisodeLike.user_id == user.id, models.EpisodeLike.episode_id == item_id)
        .first()
    )
    if existing:
        db.delete(existing)
        row.likes = max(0, (row.likes or 0) - 1)
        liked = False
    else:
        db.add(models.EpisodeLike(id=nid("elike"), user_id=user.id, episode_id=item_id))
        row.likes = (row.likes or 0) + 1
        liked = True
    db.commit()
    return {"liked": liked, "likes": row.likes}


@router.post("/episodes/{item_id}/view")
def view_episode(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Episode, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.views = (row.views or 0) + 1
    db.commit()
    return {"views": row.views}


@router.get("/comments")
def list_comments(
    seriesId: Optional[str] = None,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_current_user_optional),
):
    q = db.query(models.Comment)
    if seriesId:
        q = q.filter(models.Comment.series_id == seriesId)
    liked = liked_comment_ids(db, user)
    rows = q.order_by(models.Comment.created_at.desc()).limit(200).all()
    return [comment_out(c, c.id in liked) for c in rows if not c.hidden or (user and user.role == "ADMIN")]


@router.post("/comments")
def create_comment(body: CommentIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = models.Comment(
        id=body.id or nid("cmt"),
        series_id=body.seriesId,
        episode_id=body.episodeId,
        user_id=user.id,
        user_name=user.name,
        user_phone=user.phone,
        text=body.text.strip(),
        parent_id=body.parentId,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return comment_out(row)


@router.post("/comments/{item_id}/like")
def like_comment(item_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = db.get(models.Comment, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    existing = (
        db.query(models.CommentLike)
        .filter(models.CommentLike.user_id == user.id, models.CommentLike.comment_id == item_id)
        .first()
    )
    if existing:
        db.delete(existing)
        row.likes = max(0, (row.likes or 0) - 1)
        liked = False
    else:
        db.add(models.CommentLike(id=nid("clike"), user_id=user.id, comment_id=item_id))
        row.likes = (row.likes or 0) + 1
        liked = True
    db.commit()
    return {"liked": liked, "likes": row.likes}


@router.post("/comments/{item_id}/hide", dependencies=[Depends(get_admin)])
def hide_comment(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Comment, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.hidden = not row.hidden
    db.commit()
    return {"hidden": row.hidden}


@router.delete("/comments/{item_id}", dependencies=[Depends(get_admin)])
def delete_comment(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Comment, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.query(models.CommentLike).filter(models.CommentLike.comment_id == item_id).delete()
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/shares")
def create_share(
    body: ShareIn,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_current_user_optional),
):
    db.add(
        models.ShareEvent(
            id=nid("share"),
            user_id=user.id if user else None,
            series_id=body.seriesId,
            episode_id=body.episodeId,
            channel=body.channel,
        )
    )
    count = 0
    if body.seriesId:
        s = db.get(models.Series, body.seriesId)
        if s:
            s.share_count = (s.share_count or 0) + 1
            count = s.share_count
    if body.episodeId:
        e = db.get(models.Episode, body.episodeId)
        if e:
            e.share_count = (e.share_count or 0) + 1
            count = e.share_count
    db.commit()
    return {"ok": True, "shareCount": count}


@router.post("/favorites/{series_id}/toggle")
def toggle_favorite(series_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    existing = (
        db.query(models.Favorite)
        .filter(models.Favorite.user_id == user.id, models.Favorite.series_id == series_id)
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()
        return {"saved": False}
    db.add(models.Favorite(id=nid("fav"), user_id=user.id, series_id=series_id))
    db.commit()
    return {"saved": True}


@router.post("/progress")
def upsert_progress(body: ProgressIn, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = (
        db.query(models.Progress)
        .filter(models.Progress.user_id == user.id, models.Progress.episode_id == body.episodeId)
        .first()
    )
    if row:
        row.position_sec = body.positionSec
        row.completed = body.completed
        row.updated_at = utcnow()
    else:
        row = models.Progress(
            id=nid("prog"),
            user_id=user.id,
            episode_id=body.episodeId,
            position_sec=body.positionSec,
            completed=body.completed,
        )
        db.add(row)
    db.commit()
    return progress_out(row)


@router.get("/subscriptions/plans")
def list_plans():
    return [{"id": k, **v} for k, v in PLANS.items()]


@router.get("/subscriptions/me")
def my_subscriptions(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    refresh_subscription_status(db, user)
    rows = db.query(models.Subscription).filter(models.Subscription.user_id == user.id).all()
    return {
        "subscriptionStatus": user.subscription_status,
        "vip": user_has_vip(db, user),
        "items": [subscription_out(s) for s in rows],
        "active": subscription_out(active_sub(db, user)) if active_sub(db, user) else None,
    }


def _create_subscription(db: Session, user: models.User, plan: str, method: str, status: str) -> models.Subscription:
    cfg = PLANS.get(plan)
    if not cfg:
        raise HTTPException(status_code=400, detail="Unknown plan")
    start = utcnow()
    end = start + timedelta(days=cfg["days"])
    sub = models.Subscription(
        id=nid("sub"),
        user_id=user.id,
        user_name=user.name,
        user_phone=user.phone,
        plan=plan,
        plan_name_sw=cfg["planNameSw"],
        amount_tzs=cfg["amountTzs"],
        payment_method=method,
        reference_code=f"{'GRANT' if method == 'Admin Grant' else 'PAY'}-{secrets.token_hex(4).upper()}",
        status=status,
        start_date=start,
        end_date=end,
    )
    db.add(sub)
    if status == "ACTIVE":
        user.subscription_status = "ACTIVE"
    db.commit()
    db.refresh(sub)
    return sub


@router.post("/subscriptions/me")
def request_subscription(body: SubscribeIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role == "ADMIN":
        sub = _create_subscription(db, user, body.plan, body.paymentMethod, "ACTIVE")
        return subscription_out(sub)
    sub = _create_subscription(db, user, body.plan, body.paymentMethod, "PENDING")
    return subscription_out(sub)


@router.post("/subscriptions/grant", dependencies=[Depends(get_admin)])
def grant_subscription(body: GrantIn, db: Session = Depends(get_db)):
    user = db.get(models.User, body.userId)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    sub = _create_subscription(db, user, body.plan, "Admin Grant", "ACTIVE")
    return subscription_out(sub)


@router.patch("/subscriptions/{item_id}", dependencies=[Depends(get_admin)])
def patch_subscription(item_id: str, body: StatusIn, db: Session = Depends(get_db)):
    sub = db.get(models.Subscription, item_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Not found")
    sub.status = body.status
    user = db.get(models.User, sub.user_id)
    if user:
        if body.status == "ACTIVE":
            user.subscription_status = "ACTIVE"
        elif body.status in {"CANCELLED", "EXPIRED"}:
            other = (
                db.query(models.Subscription)
                .filter(
                    models.Subscription.user_id == user.id,
                    models.Subscription.id != item_id,
                    models.Subscription.status == "ACTIVE",
                )
                .first()
            )
            if not other:
                user.subscription_status = "EXPIRED" if body.status == "EXPIRED" else "FREE_TIER"
    db.commit()
    return subscription_out(sub)


@router.delete("/subscriptions/{item_id}", dependencies=[Depends(get_admin)])
def delete_subscription(item_id: str, db: Session = Depends(get_db)):
    sub = db.get(models.Subscription, item_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(sub)
    db.commit()
    return {"ok": True}


@router.post("/users", dependencies=[Depends(get_admin)])
def create_user(body: UserCreateIn, db: Session = Depends(get_db)):
    phone = normalize_phone(body.phone)
    if find_user_by_phone(db, phone):
        raise HTTPException(status_code=409, detail="Phone exists")
    user = models.User(
        id=nid("user"),
        name=body.name,
        phone=phone,
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        role=body.role if body.role in {"USER", "ADMIN"} else "USER",
        language=body.language,
        subscription_status="FREE_TIER",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user_out(user)


@router.patch("/users/{item_id}", dependencies=[Depends(get_admin)])
def patch_user(item_id: str, body: UserPatchIn, db: Session = Depends(get_db)):
    user = db.get(models.User, item_id)
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    if body.name is not None:
        user.name = body.name
    if body.language is not None:
        user.language = body.language
    if body.role in {"USER", "ADMIN"}:
        user.role = body.role
    if body.subscriptionStatus:
        user.subscription_status = body.subscriptionStatus
    db.commit()
    return user_out(user)


@router.delete("/users/{item_id}", dependencies=[Depends(get_admin)])
def delete_user(item_id: str, db: Session = Depends(get_db)):
    user = db.get(models.User, item_id)
    if not user:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(user)
    db.commit()
    return {"ok": True}


@router.post("/notifications", dependencies=[Depends(get_admin)])
def create_notification(body: NotificationIn, db: Session = Depends(get_db)):
    row = models.Notification(
        id=nid("notif"),
        target_user_id=body.targetUserId,
        target_phone=body.targetPhone,
        target_audience=body.targetAudience,
        title=body.title,
        title_sw=body.titleSw,
        message=body.message,
        message_sw=body.messageSw,
        type=body.type,
        action_url=body.actionUrl,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return notification_out(row)


@router.post("/notifications/{item_id}/read")
def read_notification(item_id: str, db: Session = Depends(get_db), user: models.User = Depends(get_current_user)):
    row = db.get(models.Notification, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    row.read = True
    db.commit()
    return notification_out(row)


@router.delete("/notifications/{item_id}", dependencies=[Depends(get_admin)])
def delete_notification(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.Notification, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.patch("/community/{item_id}", dependencies=[Depends(get_admin)])
def patch_community(item_id: str, body: dict[str, Any], db: Session = Depends(get_db)):
    row = db.get(models.CommunityUpload, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if "status" in body:
        row.status = body["status"]
    if "moderationNotes" in body:
        row.moderation_notes = body["moderationNotes"]
    db.commit()
    return community_out(row)


@router.delete("/community/{item_id}", dependencies=[Depends(get_admin)])
def delete_community(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.CommunityUpload, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/video-jobs", dependencies=[Depends(get_admin)])
def create_video_job(body: VideoJobIn, db: Session = Depends(get_db), admin: models.User = Depends(get_admin)):
    row = models.VideoJob(
        id=body.id or nid("job"),
        series_id=body.seriesId,
        episode_id=body.episodeId,
        episode_title=body.episodeTitle,
        format=body.format,
        engine=body.engine,
        brief=body.brief,
        title_sw=body.titleSw,
        title_en=body.titleEn,
        storyboard=json.dumps(body.storyboard),
        voice=body.voice,
        duration_sec=body.durationSec,
        created_by_id=admin.id,
        status=body.status or "DRAFT",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return video_job_out(row)


@router.patch("/video-jobs/{item_id}", dependencies=[Depends(get_admin)])
def patch_video_job(item_id: str, body: dict[str, Any], db: Session = Depends(get_db)):
    row = db.get(models.VideoJob, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    mapping = {
        "seriesId": "series_id",
        "episodeId": "episode_id",
        "episodeTitle": "episode_title",
        "currentStep": "current_step",
        "titleSw": "title_sw",
        "titleEn": "title_en",
        "outputUrl": "output_url",
        "posterUrl": "poster_url",
        "durationSec": "duration_sec",
        "createdById": "created_by_id",
    }
    for k, v in body.items():
        if k == "storyboard":
            row.storyboard = json.dumps(v)
        else:
            setattr(row, mapping.get(k, k), v)
    row.updated_at = utcnow()
    db.commit()
    return video_job_out(row)


@router.delete("/video-jobs/{item_id}", dependencies=[Depends(get_admin)])
def delete_video_job(item_id: str, db: Session = Depends(get_db)):
    row = db.get(models.VideoJob, item_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/ai/generate-story", dependencies=[Depends(get_admin)])
async def ai_story(body: AIStoryIn):
    return await generate_story(body.prompt, body.categorySlug, body.targetDurationSec, body.tone)


@router.post("/ai/generate-storyboard", dependencies=[Depends(get_admin)])
async def ai_board(body: AIStoryboardIn):
    return await generate_storyboard(body.brief, body.targetDurationSec)


@router.post("/ai/publish-story", dependencies=[Depends(get_admin)])
def publish_story(body: AIPublishIn, db: Session = Depends(get_db)):
    story = body.story
    cat = db.query(models.Category).filter(models.Category.slug == story.get("categorySlug")).first()
    if not cat:
        cat = db.query(models.Category).first()
    slug_base = "".join(ch.lower() if ch.isalnum() else "-" for ch in (story.get("titleSw") or "story"))
    slug = f"{slug_base.strip('-')}-{uuid4().hex[:4]}"
    series = models.Series(
        id=nid("ser"),
        slug=slug,
        title=story.get("titleEn") or "Untitled",
        title_sw=story.get("titleSw") or "Bila kichwa",
        description=story.get("descriptionEn") or "",
        description_sw=story.get("descriptionSw") or "",
        category_id=cat.id if cat else "",
        cover_gradient=story.get("coverGradient") or "teal",
        featured=True,
        published=True,
    )
    db.add(series)
    db.flush()
    media = body.mediaUrl or db.query(models.Episode).first()
    media_url = body.mediaUrl or (media.media_url if isinstance(media, models.Episode) else "/media/seed/placeholder.wav")
    ep = models.Episode(
        id=nid("ep"),
        series_id=series.id,
        order=1,
        title=f"{series.title} - Part 1",
        title_sw=f"{series.title_sw} - Sehemu ya 1",
        duration_sec=int(story.get("targetDurationSec") or 120),
        media_url=media_url,
        media_type="AUDIO",
        is_free=body.isFree,
        published=True,
        author_name="Qisas Studio",
    )
    db.add(ep)
    db.commit()
    db.refresh(series)
    db.refresh(ep)
    return {"series": series_out(series), "episode": episode_out(ep)}


class UnlockIn(BaseModel):
    seriesId: Optional[str] = None
    kind: str = "PURCHASE"
    paymentMethod: str = "M-Pesa"
    phone: Optional[str] = None
    anonymous: bool = True
    targetLabel: Optional[str] = None


def _grant_unlock(db: Session, user: models.User, series: models.Series, kind: str, amount: int, method: str) -> models.SeriesUnlock:
    existing = (
        db.query(models.SeriesUnlock)
        .filter(models.SeriesUnlock.user_id == user.id, models.SeriesUnlock.series_id == series.id)
        .first()
    )
    if existing:
        existing.status = "ACTIVE"
        existing.kind = existing.kind or kind
        return existing
    row = models.SeriesUnlock(
        id=nid("ul"),
        user_id=user.id,
        series_id=series.id,
        kind=kind,
        amount_tzs=amount,
        payment_method=method,
        reference_code=f"PAY-{secrets.token_hex(3).upper()}",
        status="ACTIVE",
    )
    db.add(row)
    return row


@router.post("/unlocks")
def create_unlock(body: UnlockIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    method = body.paymentMethod if body.paymentMethod != "Card" else "Card"
    if body.kind == "BUNDLE":
        owned = {
            u.series_id
            for u in db.query(models.SeriesUnlock).filter(models.SeriesUnlock.user_id == user.id).all()
        }
        picks = (
            db.query(models.Series)
            .filter(models.Series.published.is_(True))
            .order_by(models.Series.views.desc())
            .all()
        )
        chosen = [s for s in picks if s.id not in owned][:STARTER_BUNDLE_COUNT]
        if not chosen:
            raise HTTPException(status_code=400, detail="No series left to unlock")
        created = []
        share = max(1, STARTER_BUNDLE_TZS // max(1, len(chosen)))
        for s in chosen:
            created.append(_grant_unlock(db, user, s, "BUNDLE", share, method))
        track_event(db, "unlock_bundle", user.id, chosen[0].id, {"count": len(chosen)})
        db.commit()
        return {"unlocks": unlocks_out(db, created), "amountTzs": STARTER_BUNDLE_TZS}
    if not body.seriesId:
        raise HTTPException(status_code=400, detail="seriesId required")
    series = db.get(models.Series, body.seriesId)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    amount = series_price(db, series)
    row = _grant_unlock(db, user, series, "PURCHASE", amount, method)
    track_event(db, "unlock_series", user.id, series.id, {"amount": amount})
    db.commit()
    db.refresh(row)
    return {"unlocks": unlocks_out(db, [row]), "amountTzs": amount}


@router.get("/unlocks")
def list_unlocks(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(models.SeriesUnlock).order_by(models.SeriesUnlock.created_at.desc())
    if user.role != "ADMIN":
        q = q.filter(models.SeriesUnlock.user_id == user.id)
    return unlocks_out(db, q.all())


@router.post("/sponsorships")
def create_sponsorship(body: UnlockIn, user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not body.seriesId:
        raise HTTPException(status_code=400, detail="seriesId required")
    series = db.get(models.Series, body.seriesId)
    if not series:
        raise HTTPException(status_code=404, detail="Series not found")
    amount = series_price(db, series)
    gift = models.Sponsorship(
        id=nid("sadaqa"),
        donor_id=user.id,
        series_id=series.id,
        amount_tzs=amount,
        payment_method=body.paymentMethod,
        reference_code=f"SADAQA-{secrets.token_hex(3).upper()}",
        anonymous=body.anonymous,
        target_label=body.targetLabel or "Watoto na wasikilizaji wa bure",
    )
    db.add(gift)
    series.sponsored_plays = (series.sponsored_plays or 0) + 1
    series.sponsor_pool = (series.sponsor_pool or 0) + 1
    track_event(db, "sponsor_series", user.id, series.id, {"anonymous": body.anonymous})
    db.commit()
    db.refresh(gift)
    return sponsorships_out(db, [gift])[0]


@router.get("/sponsorships")
def list_sponsorships(user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin only")
    rows = db.query(models.Sponsorship).order_by(models.Sponsorship.created_at.desc()).all()
    return sponsorships_out(db, rows)


class EventIn(BaseModel):
    type: str
    seriesId: Optional[str] = None
    meta: Optional[dict[str, Any]] = None


@router.post("/events")
def create_event(
    body: EventIn,
    db: Session = Depends(get_db),
    user: Optional[models.User] = Depends(get_current_user_optional),
):
    if body.type not in {
        "series_view",
        "unlock_prompt",
        "unlock_start",
        "sponsor_prompt",
        "bundle_view",
    }:
        raise HTTPException(status_code=400, detail="Unknown event")
    track_event(db, body.type, user.id if user else None, body.seriesId, body.meta)
    db.commit()
    return {"ok": True}


@router.get("/monetize/kpis", dependencies=[Depends(get_admin)])
def get_monetize_kpis(db: Session = Depends(get_db)):
    return monetize_kpis(db)


@router.get("/monetize/analytics", dependencies=[Depends(get_admin)])
def get_monetize_analytics(db: Session = Depends(get_db)):
    return analytics_report(db)


@router.post("/system/reset", dependencies=[Depends(get_admin)])
def reset_system(db: Session = Depends(get_db)):
    seed_all(db)
    return {"ok": True}
