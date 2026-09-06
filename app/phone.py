import re


def normalize_phone(raw: str) -> str:
    clean = (raw or "").strip()
    digits = re.sub(r"\D", "", clean)
    if digits.startswith("255") and len(digits) == 12:
        return f"+{digits}"
    if digits.startswith("0") and len(digits) == 10:
        return f"+255{digits[1:]}"
    if len(digits) == 9:
        return f"+255{digits}"
    if clean.startswith("+"):
        return clean
    return clean


def phone_digits(raw: str) -> str:
    return re.sub(r"\D", "", raw or "")


def phones_match(stored: str | None, query: str | None) -> bool:
    if not stored or not query:
        return False
    s = phone_digits(stored)
    q = phone_digits(query)
    if not s or not q:
        return False
    if s == q:
        return True
    if len(s) >= 9 and len(q) >= 9:
        return s[-9:] == q[-9:]
    return False
