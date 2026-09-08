from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .security import utcnow


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, default="")
    phone: Mapped[str] = mapped_column(String, unique=True, index=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="USER")
    language: Mapped[str] = mapped_column(String, default="sw")
    avatar: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    data_saver_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    preferred_quality: Mapped[str] = mapped_column(String, default="auto")
    subscription_status: Mapped[str] = mapped_column(String, default="FREE_TIER")
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_visit_date: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    badges: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    name: Mapped[str] = mapped_column(String)
    name_sw: Mapped[str] = mapped_column(String)
    order: Mapped[int] = mapped_column(Integer, default=0)
    image: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    icon_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)


class Series(Base):
    __tablename__ = "series"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    slug: Mapped[str] = mapped_column(String, unique=True, index=True)
    title: Mapped[str] = mapped_column(String)
    title_sw: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default="")
    description_sw: Mapped[str] = mapped_column(Text, default="")
    category_id: Mapped[str] = mapped_column(ForeignKey("categories.id"))
    cover_gradient: Mapped[str] = mapped_column(String, default="teal")
    image: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    backdrop_image: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    featured: Mapped[bool] = mapped_column(Boolean, default=False)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    seasons_count: Mapped[int] = mapped_column(Integer, default=1)
    rating: Mapped[float] = mapped_column(Float, default=4.8)
    tags: Mapped[str] = mapped_column(Text, default="[]")
    unlock_price_tzs: Mapped[int] = mapped_column(Integer, default=1000)
    is_story_of_week: Mapped[bool] = mapped_column(Boolean, default=False)
    sponsored_plays: Mapped[int] = mapped_column(Integer, default=0)
    sponsor_pool: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"), index=True)
    season_number: Mapped[int] = mapped_column(Integer, default=1)
    order: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String)
    title_sw: Mapped[str] = mapped_column(String)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description_sw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration_sec: Mapped[int] = mapped_column(Integer, default=120)
    media_url: Mapped[str] = mapped_column(String, default="")
    media_type: Mapped[str] = mapped_column(String, default="AUDIO")
    poster_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_free: Mapped[bool] = mapped_column(Boolean, default=False)
    views: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    share_count: Mapped[int] = mapped_column(Integer, default=0)
    published: Mapped[bool] = mapped_column(Boolean, default=True)
    author_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    author_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    from_video_job: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user_name: Mapped[str] = mapped_column(String, default="")
    user_phone: Mapped[str] = mapped_column(String, default="")
    plan: Mapped[str] = mapped_column(String)
    plan_name_sw: Mapped[str] = mapped_column(String, default="")
    amount_tzs: Mapped[int] = mapped_column(Integer, default=0)
    payment_method: Mapped[str] = mapped_column(String, default="M-Pesa")
    reference_code: Mapped[str] = mapped_column(String, unique=True)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"), index=True)
    episode_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    user_name: Mapped[str] = mapped_column(String)
    user_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_avatar: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    parent_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SeriesLike(Base):
    __tablename__ = "series_likes"
    __table_args__ = (UniqueConstraint("user_id", "series_id", name="uq_series_like"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class EpisodeLike(Base):
    __tablename__ = "episode_likes"
    __table_args__ = (UniqueConstraint("user_id", "episode_id", name="uq_episode_like"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommentLike(Base):
    __tablename__ = "comment_likes"
    __table_args__ = (UniqueConstraint("user_id", "comment_id", name="uq_comment_like"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    comment_id: Mapped[str] = mapped_column(ForeignKey("comments.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ShareEvent(Base):
    __tablename__ = "share_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    series_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    episode_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    channel: Mapped[str] = mapped_column(String, default="copy")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (UniqueConstraint("user_id", "series_id", name="uq_favorite"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (UniqueConstraint("user_id", "episode_id", name="uq_progress"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    episode_id: Mapped[str] = mapped_column(ForeignKey("episodes.id"), index=True)
    position_sec: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    target_user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    target_audience: Mapped[str] = mapped_column(String, default="ALL")
    title: Mapped[str] = mapped_column(String)
    title_sw: Mapped[str] = mapped_column(String)
    message: Mapped[str] = mapped_column(Text, default="")
    message_sw: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String, default="SYSTEM")
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    action_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CommunityUpload(Base):
    __tablename__ = "community_uploads"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    uploader_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    uploader_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    author_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    author_phone: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    verified_speaker: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str] = mapped_column(String)
    title_sw: Mapped[str] = mapped_column(String)
    category: Mapped[str] = mapped_column(String, default="")
    description: Mapped[str] = mapped_column(Text, default="")
    description_sw: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    media_url: Mapped[str] = mapped_column(String, default="")
    media_type: Mapped[str] = mapped_column(String, default="AUDIO")
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    references: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    views: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String, default="PENDING")
    moderation_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    series_id: Mapped[str] = mapped_column(String, default="")
    episode_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    episode_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    format: Mapped[str] = mapped_column(String, default="VERTICAL_9_16")
    engine: Mapped[str] = mapped_column(String, default="qisas-ai")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str] = mapped_column(String, default="Draft")
    status: Mapped[str] = mapped_column(String, default="DRAFT")
    brief: Mapped[str] = mapped_column(Text, default="")
    title_sw: Mapped[str] = mapped_column(String, default="")
    title_en: Mapped[str] = mapped_column(String, default="")
    storyboard: Mapped[str] = mapped_column(Text, default="[]")
    script_provider: Mapped[str] = mapped_column(String, default="gemini-flash")
    tts_provider: Mapped[str] = mapped_column(String, default="elevenlabs")
    voice: Mapped[str] = mapped_column(String, default="sw-TZ-standard")
    output_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    poster_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    duration_sec: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    logs: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SeriesUnlock(Base):
    __tablename__ = "series_unlocks"
    __table_args__ = (UniqueConstraint("user_id", "series_id", name="uq_series_unlock"),)

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"), index=True)
    kind: Mapped[str] = mapped_column(String, default="PURCHASE")
    amount_tzs: Mapped[int] = mapped_column(Integer, default=0)
    payment_method: Mapped[str] = mapped_column(String, default="M-Pesa")
    reference_code: Mapped[str] = mapped_column(String, default="")
    status: Mapped[str] = mapped_column(String, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Sponsorship(Base):
    __tablename__ = "sponsorships"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    donor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    series_id: Mapped[str] = mapped_column(ForeignKey("series.id"), index=True)
    amount_tzs: Mapped[int] = mapped_column(Integer, default=0)
    payment_method: Mapped[str] = mapped_column(String, default="M-Pesa")
    reference_code: Mapped[str] = mapped_column(String, default="")
    anonymous: Mapped[bool] = mapped_column(Boolean, default=True)
    target_label: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConversionEvent(Base):
    __tablename__ = "conversion_events"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, index=True)
    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    series_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    meta: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    phone: Mapped[str] = mapped_column(String, index=True)
    code_hash: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String, default="dev")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
