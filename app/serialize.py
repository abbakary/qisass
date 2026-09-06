from datetime import datetime
import json
from typing import Any, Optional

from . import models
from .config import settings


def public_url(url: Optional[str]) -> Optional[str]:
    """Point media at a CDN origin when MEDIA_CDN_BASE is set — YouTube-style edge URLs."""
    if not url:
        return url
    base = (settings.media_cdn_base or "").rstrip("/")
    if base and url.startswith("/media/"):
        return f"{base}{url}"
    return url

PLANS = {
    "WEEKLY": {"days": 7, "amountTzs": 1000, "planNameSw": "Kifurushi cha Wiki", "name": "Weekly VIP"},
    "MONTHLY": {"days": 30, "amountTzs": 3500, "planNameSw": "Kifurushi cha Mwezi", "name": "Monthly VIP"},
    "ANNUAL": {"days": 365, "amountTzs": 25000, "planNameSw": "Kifurushi cha Mwaka", "name": "Annual VIP"},
    "VIP_LIFETIME": {"days": 3650, "amountTzs": 100000, "planNameSw": "VIP wa Maisha", "name": "Lifetime VIP"},
}


def iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        return dt.isoformat() + "Z"
    return dt.isoformat()


def user_out(u: models.User) -> dict[str, Any]:
    return {
        "id": u.id,
        "name": u.name,
        "phone": u.phone,
        "email": u.email,
        "password": "",
        "role": u.role,
        "language": u.language,
        "avatar": u.avatar,
        "dataSaverEnabled": u.data_saver_enabled,
        "preferredQuality": u.preferred_quality,
        "subscriptionStatus": u.subscription_status,
        "streakDays": getattr(u, "streak_days", 0) or 0,
        "badges": json.loads(getattr(u, "badges", None) or "[]"),
        "createdAt": iso(u.created_at),
    }


def session_out(u: models.User, sub: models.Subscription | None = None) -> dict[str, Any]:
    data = {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "phone": u.phone,
        "role": u.role,
        "language": u.language,
        "subscriptionStatus": u.subscription_status,
        "streakDays": getattr(u, "streak_days", 0) or 0,
        "badges": json.loads(getattr(u, "badges", None) or "[]"),
    }
    if sub:
        data["plan"] = sub.plan
        data["subscriptionEndDate"] = iso(sub.end_date)
        data["subscriptionPlanNameSw"] = sub.plan_name_sw
    return data


def category_out(c: models.Category) -> dict[str, Any]:
    return {
        "id": c.id,
        "slug": c.slug,
        "name": c.name,
        "nameSw": c.name_sw,
        "order": c.order,
        "image": public_url(c.image),
        "iconName": c.icon_name,
    }


def series_out(s: models.Series, liked: bool = False) -> dict[str, Any]:
    try:
        tags = json.loads(s.tags or "[]")
    except json.JSONDecodeError:
        tags = []
    return {
        "id": s.id,
        "slug": s.slug,
        "title": s.title,
        "titleSw": s.title_sw,
        "description": s.description,
        "descriptionSw": s.description_sw,
        "categoryId": s.category_id,
        "coverGradient": s.cover_gradient,
        "image": public_url(s.image),
        "backdropImage": public_url(s.backdrop_image),
        "featured": s.featured,
        "published": s.published,
        "views": s.views,
        "likes": s.likes,
        "likedByMe": liked,
        "shareCount": s.share_count,
        "seasonsCount": s.seasons_count,
        "rating": s.rating,
        "tags": tags,
        "unlockPriceTzs": getattr(s, "unlock_price_tzs", None) or 1000,
        "isStoryOfWeek": bool(getattr(s, "is_story_of_week", False)),
        "sponsoredPlays": getattr(s, "sponsored_plays", 0) or 0,
        "sponsorPool": getattr(s, "sponsor_pool", 0) or 0,
        "createdAt": iso(s.created_at),
    }


def episode_out(e: models.Episode, liked: bool = False) -> dict[str, Any]:
    return {
        "id": e.id,
        "seriesId": e.series_id,
        "seasonNumber": e.season_number,
        "order": e.order,
        "title": e.title,
        "titleSw": e.title_sw,
        "description": e.description,
        "descriptionSw": e.description_sw,
        "durationSec": e.duration_sec,
        "mediaUrl": public_url(e.media_url),
        "mediaType": e.media_type,
        "posterUrl": public_url(e.poster_url),
        "isFree": e.is_free,
        "views": e.views,
        "likes": e.likes,
        "likedByMe": liked,
        "shareCount": e.share_count,
        "published": e.published,
        "authorName": e.author_name,
        "authorPhone": e.author_phone,
        "createdAt": iso(e.created_at),
        "fromVideoJob": e.from_video_job,
    }


def comment_out(c: models.Comment, liked: bool = False) -> dict[str, Any]:
    return {
        "id": c.id,
        "seriesId": c.series_id,
        "episodeId": c.episode_id,
        "userId": c.user_id,
        "userName": c.user_name,
        "userPhone": c.user_phone,
        "userAvatar": c.user_avatar,
        "text": c.text,
        "likes": c.likes,
        "likedByMe": liked,
        "createdAt": iso(c.created_at),
        "hidden": c.hidden,
        "parentId": c.parent_id,
    }


def subscription_out(s: models.Subscription) -> dict[str, Any]:
    return {
        "id": s.id,
        "userId": s.user_id,
        "userName": s.user_name,
        "userPhone": s.user_phone,
        "plan": s.plan,
        "planNameSw": s.plan_name_sw,
        "amountTzs": s.amount_tzs,
        "paymentMethod": s.payment_method,
        "referenceCode": s.reference_code,
        "status": s.status,
        "startDate": iso(s.start_date),
        "endDate": iso(s.end_date),
        "createdAt": iso(s.created_at),
    }


def favorite_out(f: models.Favorite) -> dict[str, Any]:
    return {
        "id": f.id,
        "userId": f.user_id,
        "seriesId": f.series_id,
        "createdAt": iso(f.created_at),
    }


def progress_out(p: models.Progress) -> dict[str, Any]:
    return {
        "id": p.id,
        "userId": p.user_id,
        "episodeId": p.episode_id,
        "positionSec": p.position_sec,
        "completed": p.completed,
        "updatedAt": iso(p.updated_at),
    }


def notification_out(n: models.Notification) -> dict[str, Any]:
    return {
        "id": n.id,
        "targetUserId": n.target_user_id,
        "targetPhone": n.target_phone,
        "targetAudience": n.target_audience,
        "title": n.title,
        "titleSw": n.title_sw,
        "message": n.message,
        "messageSw": n.message_sw,
        "type": n.type,
        "read": n.read,
        "actionUrl": n.action_url,
        "createdAt": iso(n.created_at),
    }


def community_out(c: models.CommunityUpload) -> dict[str, Any]:
    return {
        "id": c.id,
        "userId": c.user_id,
        "userName": c.user_name,
        "userPhone": c.user_phone,
        "uploaderName": c.uploader_name,
        "uploaderPhone": c.uploader_phone,
        "authorName": c.author_name,
        "authorPhone": c.author_phone,
        "verifiedSpeaker": c.verified_speaker,
        "title": c.title,
        "titleSw": c.title_sw,
        "category": c.category,
        "description": c.description,
        "descriptionSw": c.description_sw,
        "mediaUrl": c.media_url,
        "mediaType": c.media_type,
        "thumbnailUrl": c.thumbnail_url,
        "durationSec": c.duration_sec,
        "references": c.references,
        "likes": c.likes,
        "views": c.views,
        "status": c.status,
        "moderationNotes": c.moderation_notes,
        "createdAt": iso(c.created_at),
    }


def video_job_out(j: models.VideoJob) -> dict[str, Any]:
    try:
        storyboard = json.loads(j.storyboard or "[]")
    except json.JSONDecodeError:
        storyboard = []
    return {
        "id": j.id,
        "seriesId": j.series_id,
        "episodeId": j.episode_id,
        "episodeTitle": j.episode_title,
        "format": j.format,
        "engine": j.engine,
        "progress": j.progress,
        "currentStep": j.current_step,
        "status": j.status,
        "brief": j.brief,
        "titleSw": j.title_sw,
        "titleEn": j.title_en,
        "storyboard": storyboard,
        "scriptProvider": j.script_provider,
        "ttsProvider": j.tts_provider,
        "voice": j.voice,
        "outputUrl": j.output_url,
        "posterUrl": j.poster_url,
        "durationSec": j.duration_sec,
        "logs": j.logs,
        "error": j.error,
        "createdById": j.created_by_id,
        "createdAt": iso(j.created_at),
        "updatedAt": iso(j.updated_at),
    }


def _user_map(db) -> dict[str, models.User]:
    return {u.id: u for u in db.query(models.User).all()}


def _series_map(db) -> dict[str, models.Series]:
    return {s.id: s for s in db.query(models.Series).all()}


def unlocks_out(db, rows: list[models.SeriesUnlock]) -> list[dict[str, Any]]:
    users = _user_map(db)
    series = _series_map(db)
    return [unlock_out(u, users.get(u.user_id), series.get(u.series_id)) for u in rows]


def sponsorships_out(db, rows: list[models.Sponsorship]) -> list[dict[str, Any]]:
    users = _user_map(db)
    series = _series_map(db)
    return [sponsorship_out(s, users.get(s.donor_id) if s.donor_id else None, series.get(s.series_id)) for s in rows]


def unlock_out(
    u: models.SeriesUnlock,
    user: models.User | None = None,
    series: models.Series | None = None,
) -> dict[str, Any]:
    return {
        "id": u.id,
        "userId": u.user_id,
        "userName": user.name if user else "",
        "userPhone": user.phone if user else "",
        "seriesId": u.series_id,
        "seriesTitle": series.title if series else "",
        "seriesTitleSw": series.title_sw if series else "",
        "kind": u.kind,
        "amountTzs": u.amount_tzs,
        "paymentMethod": u.payment_method,
        "referenceCode": u.reference_code,
        "status": u.status,
        "createdAt": iso(u.created_at),
    }


def sponsorship_out(
    s: models.Sponsorship,
    donor: models.User | None = None,
    series: models.Series | None = None,
) -> dict[str, Any]:
    return {
        "id": s.id,
        "donorId": s.donor_id,
        "donorName": None if s.anonymous else (donor.name if donor else None),
        "seriesId": s.series_id,
        "seriesTitleSw": series.title_sw if series else "",
        "amountTzs": s.amount_tzs,
        "paymentMethod": s.payment_method,
        "referenceCode": s.reference_code,
        "anonymous": s.anonymous,
        "targetLabel": s.target_label,
        "createdAt": iso(s.created_at),
    }
