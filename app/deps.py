from datetime import timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .security import decode_access_token, utcnow

bearer = HTTPBearer(auto_error=False)


def get_current_user_optional(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> Optional[models.User]:
    if not creds:
        return None
    try:
        payload = decode_access_token(creds.credentials)
        user_id = payload.get("sub")
    except InvalidTokenError:
        return None
    if not user_id:
        return None
    return db.get(models.User, user_id)


def get_current_user(user: Optional[models.User] = Depends(get_current_user_optional)) -> models.User:
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


def get_admin(user: models.User = Depends(get_current_user)) -> models.User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def refresh_subscription_status(db: Session, user: models.User) -> models.User:
    now = utcnow()
    active = (
        db.query(models.Subscription)
        .filter(
            models.Subscription.user_id == user.id,
            models.Subscription.status == "ACTIVE",
        )
        .all()
    )
    still_active = False
    for sub in active:
        if sub.end_date and sub.end_date < now:
            sub.status = "EXPIRED"
        else:
            still_active = True
    if user.role == "ADMIN":
        user.subscription_status = "ACTIVE"
    elif still_active:
        user.subscription_status = "ACTIVE"
    elif user.subscription_status == "ACTIVE":
        user.subscription_status = "EXPIRED"
    db.commit()
    db.refresh(user)
    return user


def user_has_vip(db: Session, user: Optional[models.User]) -> bool:
    if not user:
        return False
    user = refresh_subscription_status(db, user)
    return user.role == "ADMIN" or user.subscription_status == "ACTIVE"


from .monetize import bump_streak, can_play_episode as monetize_can_play


def can_play_episode(db: Session, episode: models.Episode, user: Optional[models.User]) -> bool:
    return monetize_can_play(db, episode, user)
