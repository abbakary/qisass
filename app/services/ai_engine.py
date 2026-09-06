from __future__ import annotations

import json
import re
from typing import Any

import httpx

from ..config import settings

STORY_SCHEMA_HINT = """Return ONLY valid JSON with keys:
titleSw, titleEn, descriptionSw, descriptionEn, categorySlug, coverGradient,
targetDurationSec, moralSw, beats (array of {timestamp, narrativeSw, visualPrompt}).
coverGradient must be one of: teal, forest, gold, deep, olive, emerald.
Write respectful Islamic educational content in Kiswahili and English. No images of prophets."""


def _local_story(prompt: str, category_slug: str, duration: int, tone: str) -> dict[str, Any]:
    is_prophet = category_slug == "manabii"
    is_companion = category_slug == "maswahaba"
    is_kid = category_slug == "watoto"
    snippet = prompt.strip()[:80] or "kisa cha imani"
    title_sw = (
        f"Kisa cha {snippet.split(' ')[0]}"
        if is_prophet
        else f"Hadithi Tamu ya Watoto: {snippet[:28]}"
        if is_kid
        else f"Uaminifu wa Maswahaba: {snippet[:30]}"
        if is_companion
        else f"Hazina ya Hikma: {snippet[:32]}"
    )
    title_en = (
        "The Life and Virtues of the Prophet"
        if is_prophet
        else "Virtues and Manners for Young Hearts"
        if is_kid
        else "Companions of Truth and Valor"
        if is_companion
        else "Gems of Wisdom and Islamic History"
    )
    beats = [
        {
            "timestamp": "00:00 - 00:25",
            "narrativeSw": f"Bismillahir Rahmanir Rahim. {snippet}. Katika zama za mwangaza wa imani, kulikuwa na mfano mzuri wa mtu aliyeshikamana na haki bila hofu.",
            "visualPrompt": "Golden morning light over an ancient oasis with stylized Arabic calligraphy.",
        },
        {
            "timestamp": "00:26 - 00:55",
            "narrativeSw": "Majaribu yalipozidi, ulimi wake haukuacha kutaja jina la Mola wake. Imani yake ilikuwa pana kuliko mbingu na ardhi.",
            "visualPrompt": "Warm wind sweeping golden desert sands under deep starry twilight.",
        },
        {
            "timestamp": "00:56 - 01:25",
            "narrativeSw": "Na Mwenyezi Mungu huwalipa wanaosubiri. Kila machozi ya subira yalibadilika kuwa mti wenye matunda ya heri.",
            "visualPrompt": "Minaret silhouette against a tranquil sunset with emerald and gold aura.",
        },
        {
            "timestamp": "01:26 - 02:00",
            "narrativeSw": "Tujifunze kutokana na kisa hiki: kuwa na moyo thabiti, kuwajali walio dhaifu, na kutambua kwamba baada ya kila dhiki kuna faraja.",
            "visualPrompt": "Soft lantern glow reflecting off water in an authentic Islamic courtyard.",
        },
    ]
    return {
        "titleSw": title_sw,
        "titleEn": title_en,
        "descriptionSw": f"Msururu mfupi unaosimulia {prompt}. Imeandaliwa kwa Kiswahili na adabu.",
        "descriptionEn": "A structured micro-narrative of moral lessons from authentic Islamic history.",
        "categorySlug": category_slug,
        "coverGradient": "gold" if is_prophet else "forest" if is_companion else "emerald" if is_kid else "teal",
        "targetDurationSec": duration,
        "moralSw": "Uvumilivu katika subira na kumtegemea Mwenyezi Mungu huleta ushindi.",
        "beats": beats,
        "tone": tone,
        "provider": "local",
    }


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        raise ValueError("No JSON object in model response")
    return json.loads(match.group(0))


async def _gemini(prompt: str) -> dict[str, Any]:
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"
    async with httpx.AsyncClient(timeout=45) as client:
        res = await client.post(
            url,
            params={"key": settings.gemini_api_key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        res.raise_for_status()
        data = res.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _extract_json(text)


async def _openai(prompt: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=45) as client:
        res = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openai_api_key}"},
            json={
                "model": "gpt-4o-mini",
                "temperature": 0.7,
                "messages": [
                    {"role": "system", "content": "You generate Islamic educational story JSON."},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        res.raise_for_status()
        data = res.json()
        text = data["choices"][0]["message"]["content"]
        return _extract_json(text)


def _provider() -> str:
    mode = (settings.ai_provider or "auto").lower()
    if mode in {"gemini", "openai", "local"}:
        return mode
    if settings.gemini_api_key:
        return "gemini"
    if settings.openai_api_key:
        return "openai"
    return "local"


async def generate_story(prompt: str, category_slug: str, duration: int, tone: str) -> dict[str, Any]:
    provider = _provider()
    user_prompt = (
        f"{STORY_SCHEMA_HINT}\nCategory slug: {category_slug}\nTone: {tone}\n"
        f"Target duration seconds: {duration}\nStory brief:\n{prompt}"
    )
    if provider == "local":
        data = _local_story(prompt, category_slug, duration, tone)
        data["provider"] = "local"
        return data
    try:
        if provider == "gemini":
            data = await _gemini(user_prompt)
        else:
            data = await _openai(user_prompt)
        data.setdefault("categorySlug", category_slug)
        data.setdefault("targetDurationSec", duration)
        data["provider"] = provider
        return data
    except Exception as exc:
        fallback = _local_story(prompt, category_slug, duration, tone)
        fallback["provider"] = f"local-fallback:{provider}"
        fallback["warning"] = str(exc)
        return fallback


async def generate_storyboard(brief: str, duration: int) -> dict[str, Any]:
    story = await generate_story(brief, "manabii", duration, "inspiring")
    scenes = []
    beats = story.get("beats") or []
    per = max(15, duration // max(1, len(beats)))
    motifs = ["desert", "stars", "light", "water", "geometric", "dusk"]
    for i, beat in enumerate(beats):
        scenes.append(
            {
                "id": f"scene-{i + 1}",
                "narrationSw": beat.get("narrativeSw", ""),
                "narrationEn": beat.get("visualPrompt", ""),
                "motif": motifs[i % len(motifs)],
                "headline": story.get("titleSw", ""),
                "seconds": per,
            }
        )
    return {
        "titleSw": story.get("titleSw"),
        "titleEn": story.get("titleEn"),
        "storyboard": scenes,
        "provider": story.get("provider"),
    }
