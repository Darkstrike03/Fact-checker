"""Deterministic checks that keep live fact-check verdicts conservative."""

from __future__ import annotations

import re
from datetime import date
from urllib.parse import urlparse

import config

_MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

_MONTH_RE = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|"
    r"Nov(?:ember)?|Dec(?:ember)?"
)

_DATE_PATTERNS = (
    re.compile(
        rf"\b(?P<year>\d{{4}})-(?P<month>\d{{1,2}})-(?P<day>\d{{1,2}})\b"
    ),
    re.compile(
        rf"\b(?P<month>{_MONTH_RE})\.?\s+"
        r"(?P<day>\d{1,2})(?:st|nd|rd|th)?,?\s+(?P<year>\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\b(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+"
        rf"(?P<month>{_MONTH_RE})\.?\s*,?\s+(?P<year>\d{{4}})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<first>\d{1,2})[/-](?P<second>\d{1,2})[/-]"
        r"(?P<year>\d{4}|\d{2})\b"
    ),
)

_PAST_MARKERS = re.compile(
    r"\b(visited|went|was|were|won|released|launched|announced|signed|"
    r"died|happened|took place|became|started|ended|arrested|banned|"
    r"approved|confirmed|attended|met|said|did)\b",
    re.IGNORECASE,
)
_PLAN_MARKERS = re.compile(
    r"\b(will|would|is set to|are set to|scheduled to|plans? to|planned to|"
    r"expected to|due to|ahead of|to visit|to launch|to release|to be|"
    r"likely to|may visit|might visit)\b",
    re.IGNORECASE,
)

_TERM_STOPWORDS = {
    "the",
    "this",
    "that",
    "these",
    "those",
    "a",
    "an",
    "and",
    "or",
    "but",
    "if",
    "of",
    "to",
    "in",
    "on",
    "at",
    "by",
    "for",
    "from",
    "with",
    "about",
    "after",
    "before",
    "during",
    "into",
    "over",
    "under",
    "as",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "has",
    "have",
    "had",
    "will",
    "would",
    "can",
    "could",
    "may",
    "might",
    "should",
    "did",
    "does",
    "do",
    "done",
    "says",
    "said",
    "claim",
    "claims",
    "claimed",
    "viral",
    "social",
    "media",
    "post",
    "posted",
    "video",
    "photo",
    "image",
    "news",
    "report",
    "reports",
    "reported",
    "according",
    "today",
    "yesterday",
    "tomorrow",
    "government",
    "officials",
    "official",
    "people",
    "person",
    "country",
    "world",
    "day",
    "days",
    "year",
    "years",
    "time",
    "visit",
    "visited",
    "visiting",
    "went",
    "goes",
    "gone",
    "confirm",
    "confirms",
    "confirmed",
    "announce",
    "announces",
    "announced",
    "release",
    "released",
    "launch",
    "launched",
    "ban",
    "banned",
    "take",
    "took",
    "taken",
    "happen",
    "happened",
    "occur",
    "occurred",
    "experience",
    "experienced",
    "new",
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
    "jan",
    "feb",
    "mar",
    "apr",
    "jun",
    "jul",
    "aug",
    "sep",
    "sept",
    "oct",
    "nov",
    "dec",
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}

_SHORT_TERMS = {"us", "uk", "eu", "un", "ai", "who", "nasa", "isro"}

_MONTH_TYPOS = {
    "janurary": "January",
    "januray": "January",
    "janury": "January",
    "feburary": "February",
    "febuary": "February",
    "februrary": "February",
    "apirl": "April",
    "augest": "August",
    "septmber": "September",
    "setpember": "September",
    "octover": "October",
    "novmber": "November",
    "decmeber": "December",
}
_MONTH_TYPO_RE = re.compile(
    r"\b(" + "|".join(re.escape(key) for key in _MONTH_TYPOS) + r")\b",
    re.IGNORECASE,
)


def _normalize_months(text: str) -> str:
    return _MONTH_TYPO_RE.sub(
        lambda match: _MONTH_TYPOS[match.group(1).lower()],
        text or "",
    )


def _normalize_date(year: int, month: int, day: int) -> str | None:
    if year < 100:
        year += 2000
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def extract_dates(text: str) -> list[str]:
    found: set[str] = set()
    normalized_text = _normalize_months(text)
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(normalized_text):
            groups = match.groupdict()
            if "first" in groups:
                first = int(groups["first"])
                second = int(groups["second"])
                year = int(groups["year"])
                if first > 12:
                    day, month = first, second
                elif second > 12:
                    month, day = first, second
                else:
                    day, month = first, second
            else:
                month_text = str(groups["month"]).lower().rstrip(".")
                month = (
                    int(month_text)
                    if month_text.isdigit()
                    else _MONTHS.get(month_text)
                )
                if not month:
                    continue
                day = int(groups["day"])
                year = int(groups["year"])
            normalized = _normalize_date(year, month, day)
            if normalized:
                found.add(normalized)
    return sorted(found)


def _content_terms(text: str) -> list[str]:
    terms: list[str] = []
    for token in re.findall(
        r"[A-Za-z0-9][A-Za-z0-9']*",
        _normalize_months(text),
    ):
        lowered = token.lower().strip("'")
        if not lowered or lowered in _TERM_STOPWORDS:
            continue
        if lowered.isdigit():
            if 1900 <= int(lowered) <= 2099:
                continue
            if len(lowered) < 2:
                continue
        elif len(lowered) < 3 and lowered not in _SHORT_TERMS:
            continue
        if lowered not in terms:
            terms.append(lowered)
    return terms


def _term_in_corpus(term: str, corpus: str) -> bool:
    if term.isdigit():
        if re.search(rf"\b{re.escape(term)}(?:st|nd|rd|th)?\b", corpus):
            return True
    elif re.search(rf"\b{re.escape(term)}\b", corpus):
        return True
    if len(term) >= 5:
        stem = re.escape(term[:4])
        return bool(re.search(rf"\b{stem}", corpus))
    return False


def _evidence_text(item: dict) -> str:
    return " ".join(
        str(item.get(key, "")) for key in ("title", "text", "snippet", "url")
    )


def evidence_quality(selected: list[dict]) -> dict:
    scores = []
    for item in selected:
        try:
            scores.append(float(item.get("score") or 0.0))
        except (TypeError, ValueError):
            scores.append(0.0)
    domains = {
        urlparse(str(item.get("url", ""))).netloc.lower()
        for item in selected
        if item.get("url")
    }
    domains.discard("")
    top = max(scores) if scores else 0.0
    mean = sum(scores) / len(scores) if scores else 0.0
    sufficient = bool(
        selected
        and top >= config.MIN_TOP_RELEVANCE
        and mean >= config.MIN_MEAN_RELEVANCE
        and len(domains) >= config.MIN_EVIDENCE_SOURCES
    )
    if sufficient and top >= 0.5 and len(domains) >= 3:
        label = "strong"
    elif sufficient:
        label = "moderate"
    else:
        label = "weak"
    return {
        "relevance_label": label,
        "top_relevance": round(top, 4),
        "mean_relevance": round(mean, 4),
        "source_count": len(domains),
        "sufficient": sufficient,
    }


def _pretty_date(value: str) -> str:
    try:
        return date.fromisoformat(value).strftime("%d %B %Y").lstrip("0")
    except (TypeError, ValueError):
        return str(value or "")


def _item_dates(item: dict) -> set[str]:
    dates = set(extract_dates(_evidence_text(item)))
    published = str(item.get("published_at", "")).strip()
    if published:
        dates.update(extract_dates(published))
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
            dates.add(published)
    return dates


def analyze(claim: str, selected: list[dict]) -> dict:
    claim_dates = extract_dates(claim)
    terms = _content_terms(claim)
    corpus = " ".join(_evidence_text(item) for item in selected).lower()
    missing = [term for term in terms if not _term_in_corpus(term, corpus)]

    evidence_dates: set[str] = set()
    supporting_items: list[dict] = []
    for item in selected:
        item_text = _evidence_text(item)
        item_dates = _item_dates(item)
        evidence_dates.update(item_dates)
        if claim_dates and (set(claim_dates) & item_dates):
            item_missing = [
                term
                for term in terms
                if not _term_in_corpus(term, item_text.lower())
            ]
            if not item_missing:
                supporting_items.append(item)

    date_match: bool | None = None
    if claim_dates:
        date_match = bool(supporting_items)

    texts = [_evidence_text(item) for item in selected[:3]]
    claim_has_past = bool(_PAST_MARKERS.search(claim))
    top_three_plan = bool(
        claim_has_past
        and texts
        and all(_PLAN_MARKERS.search(text) for text in texts)
    )
    supporting_plan = bool(
        claim_has_past
        and supporting_items
        and all(
            _PLAN_MARKERS.search(_evidence_text(item))
            for item in supporting_items
        )
    )
    plan_only = top_three_plan or supporting_plan

    quality = evidence_quality(selected)
    return {
        **quality,
        "claim_dates": claim_dates,
        "evidence_dates": sorted(evidence_dates),
        "date_match": date_match,
        "missing_terms": missing[:8],
        "plan_only": plan_only,
    }


def _unverified_answer(checks: dict, evidence_count: int) -> str:
    pieces = ["The available evidence is not strong enough to confirm this claim."]
    missing = checks.get("missing_terms") or []
    if missing:
        pieces.append("The evidence does not cover: " + ", ".join(missing) + ".")
    if checks.get("date_match") is False and checks.get("claim_dates"):
        dates = ", ".join(_pretty_date(day) for day in checks["claim_dates"])
        pieces.append(
            f"No source matching the claim's key details is dated {dates}."
        )
    if checks.get("plan_only"):
        pieces.append("The sources describe plans or expectations, not confirmation that the event happened.")
    if evidence_count == 0:
        pieces.append("No usable evidence was retrieved.")
    elif not checks.get("sufficient"):
        pieces.append("The retrieved sources are too few, weakly related, or from too few independent domains.")
    return " ".join(pieces)


def _unverified_reason(checks: dict, evidence_count: int) -> str:
    reasons = []
    if evidence_count == 0:
        reasons.append("No usable evidence was retrieved.")
    if not checks.get("sufficient"):
        reasons.append("Evidence relevance or source diversity is below the safety threshold.")
    if checks.get("missing_terms"):
        reasons.append("Key claim terms are absent from the evidence.")
    if checks.get("date_match") is False:
        reasons.append(
            "The claimed date is not confirmed by a source that matches the claim's key details."
        )
    if checks.get("plan_only"):
        reasons.append("The evidence only describes plans or expectations.")
    return " ".join(dict.fromkeys(reasons)) or "The evidence is insufficient."


def apply_guard(
    parsed: dict,
    checks: dict,
    evidence_count: int,
) -> dict:
    label = parsed.get("label")
    confidence = parsed.get("confidence") or "MEDIUM"
    citations = [
        number
        for number in parsed.get("citations", [])
        if 1 <= number <= max(evidence_count, 0)
    ]
    answer = str(parsed.get("answer", "")).strip()
    reason = str(parsed.get("reason", "")).strip()

    if label not in config.LIVE_LABELS:
        label = "UNVERIFIED"
        answer = _unverified_answer(checks, evidence_count)
        reason = "The model did not return a usable label. " + _unverified_reason(
            checks, evidence_count
        )
    elif label == "UNVERIFIED":
        confidence = "LOW" if not checks.get("sufficient") else confidence
        if not answer:
            answer = _unverified_answer(checks, evidence_count)
        if not reason:
            reason = _unverified_reason(checks, evidence_count)
    else:
        issues = []
        if evidence_count == 0:
            issues.append("No usable evidence was retrieved.")
        if not citations:
            issues.append("The answer did not cite the evidence.")
        if not checks.get("sufficient"):
            issues.append("Evidence relevance or source diversity is too low.")
        if checks.get("missing_terms"):
            issues.append("Key claim terms are missing from the evidence.")
        if checks.get("date_match") is False:
            issues.append("The claimed date is not supported by the evidence.")
        if checks.get("plan_only"):
            issues.append("The evidence describes plans, not a completed event.")
        if confidence == "LOW":
            issues.append("The model reported low confidence.")
        if issues:
            label = "UNVERIFIED"
            confidence = "LOW"
            citations = []
            answer = _unverified_answer(checks, evidence_count)
            reason = " ".join(issues)

    return {
        "label": label,
        "confidence": confidence,
        "answer": answer,
        "reason": reason,
        "citations": citations,
    }


def no_evidence_result() -> dict:
    checks = {
        "relevance_label": "weak",
        "top_relevance": 0.0,
        "mean_relevance": 0.0,
        "source_count": 0,
        "sufficient": False,
        "claim_dates": [],
        "evidence_dates": [],
        "date_match": None,
        "missing_terms": [],
        "plan_only": False,
    }
    return {
        "label": "UNVERIFIED",
        "confidence": "LOW",
        "answer": _unverified_answer(checks, 0),
        "reason": _unverified_reason(checks, 0),
        "citations": [],
        "checks": checks,
    }
