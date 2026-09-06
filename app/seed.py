from sqlalchemy.orm import Session

from . import models
from .config import settings
from .phone import normalize_phone
from .security import hash_password, utcnow

CATEGORIES = [
    {"slug": "manabii", "name": "Prophets", "nameSw": "Manabii", "order": 1},
    {"slug": "maswahaba", "name": "Companions", "nameSw": "Maswahaba", "order": 2},
    {"slug": "wanazuoni", "name": "Scholars", "nameSw": "Wanazuoni", "order": 3},
    {"slug": "sira", "name": "Seerah", "nameSw": "Sira", "order": 4},
    {"slug": "dua-na-adabu", "name": "Dua & Manners", "nameSw": "Dua na Adabu", "order": 5},
    {"slug": "watoto", "name": "Kids", "nameSw": "Watoto", "order": 6},
]


def seed_if_empty(db: Session) -> None:
    if settings.fresh_start:
        seed_all(db)
        return
    if not db.query(models.User).first():
        _ensure_admin(db)
    if not db.query(models.Category).first():
        _ensure_categories(db)
    demo = (
        db.query(models.User)
        .filter(models.User.phone.in_(["+255754987654", "0754987654"]))
        .first()
    )
    if demo:
        db.delete(demo)
    db.commit()


def seed_all(db: Session) -> None:
    """Wipe catalog/users and leave only the admin + category dropdowns."""
    for model in (
        models.CommentLike,
        models.SeriesLike,
        models.EpisodeLike,
        models.ShareEvent,
        models.Favorite,
        models.Progress,
        models.Comment,
        models.SeriesUnlock,
        models.Sponsorship,
        models.OtpChallenge,
        models.ConversionEvent,
        models.Subscription,
        models.Notification,
        models.CommunityUpload,
        models.VideoJob,
        models.Episode,
        models.Series,
        models.Category,
        models.User,
    ):
        db.query(model).delete()
    db.flush()
    _ensure_admin(db)
    _ensure_categories(db)
    db.commit()


def _ensure_admin(db: Session) -> models.User:
    phone = normalize_phone(settings.admin_phone)
    existing = db.query(models.User).filter(models.User.phone == phone).first()
    if existing:
        existing.role = "ADMIN"
        existing.subscription_status = "ACTIVE"
        return existing
    admin = models.User(
        id="user-admin",
        name=settings.admin_name,
        phone=phone,
        email="admin@qisas.local",
        password_hash=hash_password(settings.admin_password),
        role="ADMIN",
        language="sw",
        subscription_status="ACTIVE",
        created_at=utcnow(),
    )
    db.add(admin)
    return admin


def _ensure_categories(db: Session) -> None:
    for c in CATEGORIES:
        if db.query(models.Category).filter(models.Category.slug == c["slug"]).first():
            continue
        db.add(
            models.Category(
                id=f"cat-{c['slug']}",
                slug=c["slug"],
                name=c["name"],
                name_sw=c["nameSw"],
                order=c["order"],
                image=None,
                icon_name=c["slug"],
            )
        )
