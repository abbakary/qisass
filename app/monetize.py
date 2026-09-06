from __future__ import annotations

from datetime import date, datetime, timedelta
import json
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from . import models
from .security import utcnow

STARTER_BUNDLE_COUNT = 3
STARTER_BUNDLE_TZS = 2000
FREE_EPISODE_COUNT = 3


def is_free_episode(episode: models.Episode) -> bool:
    return episode.order <= FREE_EPISODE_COUNT or bool(episode.is_free)


def price_for_episode_count(count: int) -> int:
    if count <= 6:
        return 500
    if count <= 14:
        return 1000
    return 1500


def series_price(db: Session, series: models.Series) -> int:
    if series.unlock_price_tzs and series.unlock_price_tzs > 0:
        return int(series.unlock_price_tzs)
    n = db.query(models.Episode).filter(models.Episode.series_id == series.id).count()
    return price_for_episode_count(n)


def user_owns_series(db: Session, user: Optional[models.User], series_id: str) -> bool:
    if not user:
        return False
    if user.role == "ADMIN" or user.subscription_status == "ACTIVE":
        return True
    row = (
        db.query(models.SeriesUnlock)
        .filter(
            models.SeriesUnlock.user_id == user.id,
            models.SeriesUnlock.series_id == series_id,
            models.SeriesUnlock.status == "ACTIVE",
        )
        .first()
    )
    return bool(row)


def story_of_week(db: Session) -> Optional[models.Series]:
    flagged = (
        db.query(models.Series)
        .filter(models.Series.is_story_of_week.is_(True), models.Series.published.is_(True))
        .first()
    )
    if flagged:
        return flagged
    published = (
        db.query(models.Series)
        .filter(models.Series.published.is_(True))
        .order_by(models.Series.views.desc())
        .all()
    )
    if not published:
        return None
    return published[date.today().isocalendar().week % len(published)]


def consume_sponsor_grant(db: Session, user: models.User, series: models.Series) -> bool:
    if series.sponsor_pool <= 0:
        return False
    if user_owns_series(db, user, series.id):
        return True
    series.sponsor_pool = max(0, series.sponsor_pool - 1)
    db.add(
        models.SeriesUnlock(
            id=f"ul_{uuid4().hex[:12]}",
            user_id=user.id,
            series_id=series.id,
            kind="SPONSORED_GRANT",
            amount_tzs=0,
            payment_method="Sadaqah",
            reference_code=f"SADAQA-{series.id[-6:].upper()}",
            status="ACTIVE",
        )
    )
    track_event(db, "sponsored_grant", user.id, series.id)
    return True


def can_play_episode(db: Session, episode: models.Episode, user: Optional[models.User]) -> bool:
    if is_free_episode(episode):
        return True
    series = db.get(models.Series, episode.series_id)
    if not series:
        return False
    sow = story_of_week(db)
    if sow and sow.id == series.id:
        return True
    if user and user.role == "ADMIN":
        return True
    if user and user.subscription_status == "ACTIVE":
        return True
    if user_owns_series(db, user, series.id):
        return True
    if user and consume_sponsor_grant(db, user, series):
        db.commit()
        return True
    return False


def track_event(db: Session, typ: str, user_id: Optional[str], series_id: Optional[str] = None, meta: Optional[dict] = None) -> None:
    db.add(
        models.ConversionEvent(
            id=f"ev_{uuid4().hex[:12]}",
            type=typ,
            user_id=user_id,
            series_id=series_id,
            meta=json.dumps(meta or {}),
        )
    )


def bump_streak(db: Session, user: models.User) -> models.User:
    today = date.today().isoformat()
    if user.last_visit_date == today:
        return user
    yesterday = date.fromordinal(date.today().toordinal() - 1).isoformat()
    if user.last_visit_date == yesterday:
        user.streak_days = (user.streak_days or 0) + 1
    else:
        user.streak_days = 1
    user.last_visit_date = today
    badges = []
    try:
        badges = json.loads(user.badges or "[]")
    except json.JSONDecodeError:
        badges = []
    if user.streak_days >= 3 and "streak-3" not in badges:
        badges.append("streak-3")
    if user.streak_days >= 7 and "streak-7" not in badges:
        badges.append("streak-7")
    user.badges = json.dumps(badges)
    return user


def monetize_kpis(db: Session) -> dict:
    unlocks = db.query(models.SeriesUnlock).filter(models.SeriesUnlock.status == "ACTIVE").all()
    purchases = [u for u in unlocks if u.kind in {"PURCHASE", "BUNDLE"}]
    sponsors = db.query(models.Sponsorship).all()
    users = db.query(models.User).filter(models.User.role != "ADMIN").all()
    free_users = [u for u in users if u.subscription_status != "ACTIVE"]
    buyers = {u.user_id for u in purchases}
    sponsor_donors = {s.donor_id for s in sponsors if s.donor_id}
    by_series: dict[str, int] = {}
    for u in purchases:
        by_series[u.series_id] = by_series.get(u.series_id, 0) + 1
    return {
        "weeklyActiveHint": len(users),
        "freeUsers": len(free_users),
        "unlocks": len(purchases),
        "sponsorships": len(sponsors),
        "sponsoredPlays": sum(s.sponsored_plays or 0 for s in db.query(models.Series).all()),
        "sponsorPool": sum(s.sponsor_pool or 0 for s in db.query(models.Series).all()),
        "freeToUnlockRate": round((len(buyers) / max(1, len(free_users))) * 100, 1),
        "unlockToSponsorRate": round((len(sponsor_donors) / max(1, len(buyers))) * 100, 1),
        "revenueTzs": sum(u.amount_tzs for u in purchases) + sum(s.amount_tzs for s in sponsors),
        "topConvertingSeries": sorted(by_series.items(), key=lambda x: -x[1])[:8],
    }


def _as_date(value) -> Optional[date]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _day_key(value) -> Optional[str]:
    d = _as_date(value)
    return d.isoformat() if d else None


def analytics_report(db: Session) -> dict:
    today = date.today()
    users = db.query(models.User).filter(models.User.role != "ADMIN").all()
    unlocks = db.query(models.SeriesUnlock).filter(models.SeriesUnlock.status == "ACTIVE").all()
    purchases = [u for u in unlocks if u.kind in {"PURCHASE", "BUNDLE"}]
    grants = [u for u in unlocks if u.kind == "SPONSORED_GRANT"]
    sponsors = db.query(models.Sponsorship).all()
    progress = db.query(models.Progress).all()
    episodes = db.query(models.Episode).all()
    series_rows = db.query(models.Series).filter(models.Series.published.is_(True)).all()
    events = db.query(models.ConversionEvent).all()

    buyers = {u.user_id for u in purchases}
    donors = {s.donor_id for s in sponsors if s.donor_id}
    starters = {p.user_id for p in progress}
    ep_by_id = {e.id: e for e in episodes}
    eps_by_series: dict[str, list] = {}
    for e in episodes:
        if e.published:
            eps_by_series.setdefault(e.series_id, []).append(e)
    for lst in eps_by_series.values():
        lst.sort(key=lambda e: e.order)

    last_active: dict[str, date] = {}
    for u in users:
        d = _as_date(u.last_visit_date)
        if d:
            last_active[u.id] = d
    for p in progress:
        d = _as_date(p.updated_at)
        if not d:
            continue
        prev = last_active.get(p.user_id)
        if not prev or d > prev:
            last_active[p.user_id] = d

    wau = sum(1 for u in users if last_active.get(u.id) and (today - last_active[u.id]).days <= 6)
    free_users = [u for u in users if u.subscription_status != "ACTIVE"]

    def retention(min_age: int, window: int) -> tuple[Optional[float], int]:
        cohort = []
        for u in users:
            created = _as_date(u.created_at)
            if not created:
                continue
            age = (today - created).days
            if min_age <= age < min_age + window:
                cohort.append(u)
        if not cohort:
            return None, 0
        kept = 0
        for u in cohort:
            created = _as_date(u.created_at)
            active = last_active.get(u.id)
            if created and active and (active - created).days >= min_age - 1:
                kept += 1
        return round(kept / len(cohort) * 100, 1), len(cohort)

    d7, d7n = retention(7, 14)
    d30, d30n = retention(30, 30)

    days = 14
    daily = []
    for i in range(days - 1, -1, -1):
        day = today - timedelta(days=i)
        key = day.isoformat()
        day_purchases = [u for u in purchases if _day_key(u.created_at) == key]
        day_gifts = [s for s in sponsors if _day_key(s.created_at) == key]
        day_done = [p for p in progress if p.completed and _day_key(p.updated_at) == key]
        day_users = [u for u in users if _day_key(u.created_at) == key]
        daily.append(
            {
                "date": key,
                "label": day.strftime("%d %b"),
                "unlocks": len(day_purchases),
                "sadaqah": len(day_gifts),
                "revenueTzs": sum(u.amount_tzs for u in day_purchases) + sum(s.amount_tzs for s in day_gifts),
                "completions": len(day_done),
                "newUsers": len(day_users),
            }
        )

    rails: dict[str, dict] = {}
    for u in purchases:
        name = u.payment_method or "Other"
        row = rails.setdefault(name, {"name": name, "count": 0, "revenueTzs": 0})
        row["count"] += 1
        row["revenueTzs"] += u.amount_tzs
    for s in sponsors:
        name = s.payment_method or "Other"
        row = rails.setdefault(name, {"name": name, "count": 0, "revenueTzs": 0})
        row["count"] += 1
        row["revenueTzs"] += s.amount_tzs

    bands = {"500": {"band": "500 TZS", "unlocks": 0, "revenueTzs": 0}, "1000": {"band": "1,000 TZS", "unlocks": 0, "revenueTzs": 0}, "1500": {"band": "1,500 TZS", "unlocks": 0, "revenueTzs": 0}}
    for u in purchases:
        key = "500" if u.amount_tzs <= 600 else "1000" if u.amount_tzs <= 1200 else "1500"
        bands[key]["unlocks"] += 1
        bands[key]["revenueTzs"] += u.amount_tzs

    completed_by_user_series: dict[tuple[str, str], int] = {}
    started_by_series: dict[str, set[str]] = {}
    for p in progress:
        ep = ep_by_id.get(p.episode_id)
        if not ep:
            continue
        started_by_series.setdefault(ep.series_id, set()).add(p.user_id)
        if p.completed:
            completed_by_user_series[(p.user_id, ep.series_id)] = completed_by_user_series.get((p.user_id, ep.series_id), 0) + 1

    series_out = []
    completion_rates = []
    for s in series_rows:
        eps = eps_by_series.get(s.id, [])
        need = max(1, len(eps))
        last_id = eps[-1].id if eps else None
        starters_n = len(started_by_series.get(s.id, set()))
        last_completers = {
            p.user_id
            for p in progress
            if p.completed and p.episode_id == last_id
        } if last_id else set()
        deep = {
            uid
            for uid in started_by_series.get(s.id, set())
            if completed_by_user_series.get((uid, s.id), 0) >= max(1, int(need * 0.7))
        }
        completers = last_completers | deep
        rate = round(len(completers) / max(1, starters_n) * 100, 1) if starters_n else 0
        if starters_n:
            completion_rates.append(rate)
        buys = [u for u in purchases if u.series_id == s.id]
        series_out.append(
            {
                "id": s.id,
                "slug": s.slug,
                "titleSw": s.title_sw,
                "title": s.title,
                "views": s.views or 0,
                "likes": s.likes or 0,
                "priceTzs": s.unlock_price_tzs or 0,
                "unlocks": len(buys),
                "revenueTzs": sum(u.amount_tzs for u in buys),
                "starters": starters_n,
                "completers": len(completers),
                "completionRate": rate,
                "convertHint": round(len(buys) / max(1, s.views or starters_n or 1) * 100, 2),
                "sponsoredPlays": s.sponsored_plays or 0,
            }
        )
    series_out.sort(key=lambda r: (-r["unlocks"], -r["views"]))

    unlock_rev = sum(u.amount_tzs for u in purchases)
    sadaqah_rev = sum(s.amount_tzs for s in sponsors)
    avg_completion = round(sum(completion_rates) / max(1, len(completion_rates)), 1)
    streaks = [u.streak_days or 0 for u in users if (u.streak_days or 0) > 0]

    insights = []
    if purchases:
        top = series_out[0] if series_out and series_out[0]["unlocks"] else None
        if top:
            insights.append(
                {
                    "tone": "good",
                    "title": f"Produce more like “{top['titleSw']}”",
                    "detail": f"{top['unlocks']} paid unlocks · {top['revenueTzs']:,} TZS. Conversion beats surveys.",
                }
            )
    hooked = [r for r in series_out if r["views"] >= 200 and r["unlocks"] == 0]
    if hooked:
        h = hooked[0]
        insights.append(
            {
                "tone": "watch",
                "title": f"“{h['titleSw']}” hooks but does not convert",
                "detail": f"{h['views']:,} plays and 0 unlocks at {h['priceTzs']:,} TZS. Check the paywall copy or drop the price band.",
            }
        )
    paid_drop = [r for r in series_out if r["unlocks"] > 0 and r["starters"] > 0 and r["completionRate"] < 25]
    if paid_drop:
        d = paid_drop[0]
        insights.append(
            {
                "tone": "watch",
                "title": f"People unlock “{d['titleSw']}” then leave",
                "detail": f"{d['completionRate']}% finish after paying. Shorten later episodes or add a recap.",
            }
        )
    rail_list = sorted(rails.values(), key=lambda r: -r["revenueTzs"])
    if rail_list:
        lead = rail_list[0]
        share = round(lead["count"] / max(1, sum(r["count"] for r in rail_list)) * 100)
        insights.append(
            {
                "tone": "go",
                "title": f"{lead['name']} is {share}% of payments",
                "detail": "Keep STK push first. Card stays a fallback only.",
            }
        )
    if d7 is not None:
        insights.append(
            {
                "tone": "good" if d7 >= 20 else "watch",
                "title": f"D7 retention {d7}% ({d7n} in cohort)",
                "detail": "Kids streaks stay free — they are the cheapest way to lift this number.",
            }
        )
    if not purchases:
        insights.append(
            {
                "tone": "go",
                "title": "No paid unlocks in the ledger yet",
                "detail": "Watch free→unlock after the first STK. Bundle (3 for 2) should be the first-purchase prompt.",
            }
        )

    return {
        "kpis": {
            "wauHint": wau,
            "registered": len(users),
            "freeUsers": len(free_users),
            "buyers": len(buyers),
            "starters": len(starters),
            "freeToUnlockRate": round((len(buyers) / max(1, len(free_users))) * 100, 1),
            "unlockToSponsorRate": round((len(donors) / max(1, len(buyers))) * 100, 1),
            "unlocks": len(purchases),
            "sponsoredGrants": len(grants),
            "sponsorships": len(sponsors),
            "revenueTzs": unlock_rev + sadaqah_rev,
            "unlockRevenueTzs": unlock_rev,
            "sadaqahRevenueTzs": sadaqah_rev,
            "d7Retention": d7,
            "d30Retention": d30,
            "d7Cohort": d7n,
            "d30Cohort": d30n,
            "completionRate": avg_completion,
            "avgStreak": round(sum(streaks) / max(1, len(streaks)), 1) if streaks else 0,
            "events": len(events),
        },
        "funnel": [
            {"step": "Registered", "stepSw": "Waliojisajili", "value": len(users)},
            {"step": "Started a story", "stepSw": "Walianza hadithi", "value": len(starters)},
            {"step": "Unlocked", "stepSw": "Walifungua", "value": len(buyers)},
            {"step": "Sponsored", "stepSw": "Walidhamini", "value": len(donors)},
        ],
        "daily": daily,
        "rails": rail_list,
        "priceBands": list(bands.values()),
        "series": series_out,
        "insights": insights[:5],
    }
