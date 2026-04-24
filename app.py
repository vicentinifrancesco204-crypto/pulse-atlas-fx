from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta, timezone
from math import ceil, floor
from pathlib import Path
from time import monotonic
from typing import Any, Callable
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import json
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
try:
    ROME_TZ = ZoneInfo("Europe/Rome")
except Exception:
    ROME_TZ = datetime.now().astimezone().tzinfo or timezone.utc
UTC = timezone.utc
YAHOO_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
FOREX_FACTORY_WEEK = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FOREX_FACTORY_WEEK_XML = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
CACHE_DIR = BASE_DIR / "cache"
CALENDAR_CACHE_FILE = CACHE_DIR / "calendar.json"

SUPPORTED_PAIRS: dict[str, dict[str, Any]] = {
    "EURUSD": {"label": "EUR/USD", "pip_size": 0.0001},
    "GBPUSD": {"label": "GBP/USD", "pip_size": 0.0001},
}

IMPACT_FACTOR = {"High": 1.5, "Medium": 1.22, "Low": 1.05}

KEYWORD_BOOSTS = {
    "non-farm": 0.34,
    "nfp": 0.34,
    "interest rate": 0.34,
    "rate statement": 0.32,
    "fomc": 0.34,
    "powell": 0.26,
    "cpi": 0.25,
    "inflation": 0.25,
    "gdp": 0.22,
    "pmi": 0.18,
    "employment": 0.2,
    "jobless": 0.16,
    "claims": 0.14,
    "retail sales": 0.17,
    "speech": 0.12,
}

_session = requests.Session()
_cache: dict[str, tuple[float, Any]] = {}

app = FastAPI(title="Pulse Atlas FX", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def disable_cache(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path.startswith("/static/") or path in {"/sw.js", "/manifest.webmanifest"}:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    if path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


def cache_get(key: str, ttl_seconds: int, builder: Callable[[], Any]) -> Any:
    now = monotonic()
    cached = _cache.get(key)
    if cached and now - cached[0] < ttl_seconds:
        return cached[1]
    value = builder()
    _cache[key] = (now, value)
    return value


def normalize_symbol(symbol: str) -> str:
    clean = symbol.upper().replace("/", "").replace("=", "").replace("X", "")
    if clean.endswith("X"):
        clean = clean[:-1]
    if clean not in SUPPORTED_PAIRS:
        raise HTTPException(status_code=400, detail=f"Pair non supportato: {symbol}")
    return clean


def pair_info(pair: str) -> dict[str, Any]:
    info = dict(SUPPORTED_PAIRS[pair])
    info["code"] = pair
    info["base"] = pair[:3]
    info["quote"] = pair[3:]
    info["yahoo_symbol"] = f"{pair}=X"
    return info


def to_local_time(unix_ts: int) -> datetime:
    return datetime.fromtimestamp(unix_ts, tz=UTC).astimezone(ROME_TZ)


def parse_calendar_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(ROME_TZ)


def parse_calendar_xml_time(date_text: str, time_text: str) -> datetime | None:
    date_text = (date_text or "").strip()
    time_text = (time_text or "").strip()
    if not date_text:
        return None
    normalized_time = time_text.lower().replace(" ", "")
    if not normalized_time or normalized_time in {"all", "allday", "tentative"}:
        normalized_time = "12:00am"
    try:
        parsed = datetime.strptime(f"{date_text} {normalized_time}", "%m-%d-%Y %I:%M%p")
    except ValueError:
        return None
    return parsed.replace(tzinfo=ROME_TZ)


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * ratio
    lower = floor(idx)
    upper = ceil(idx)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - idx) + ordered[upper] * (idx - lower)


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def ema(values: list[float], period: int) -> float:
    if not values:
        return 0.0
    multiplier = 2 / (period + 1)
    result = values[0]
    for value in values[1:]:
        result = (value - result) * multiplier + result
    return result


def direction_label(score: int) -> str:
    if score >= 4:
        return "Forte rialzista"
    if score >= 2:
        return "Rialzista"
    if score <= -4:
        return "Forte ribassista"
    if score <= -2:
        return "Ribassista"
    return "Neutrale"


def direction_tone(score: int) -> str:
    if score > 1:
        return "bullish"
    if score < -1:
        return "bearish"
    return "neutral"


def format_price(value: float, pair: str) -> str:
    decimals = 3 if pair.endswith("JPY") else 5
    return f"{value:.{decimals}f}"


def pip_value(move: float, pip_size: float) -> float:
    return abs(move) / pip_size if pip_size else 0.0


def minute_jump_pips(bars: list[dict[str, Any]], index: int, pip_size: float) -> float:
    if not bars:
        return 0.0
    if index <= 0:
        return pip_value(bars[index]["close"] - bars[index]["open"], pip_size)
    return pip_value(bars[index]["close"] - bars[index - 1]["close"], pip_size)


def minute_jump_signed(bars: list[dict[str, Any]], index: int, pip_size: float) -> float:
    if not bars or not pip_size:
        return 0.0
    if index <= 0:
        return (bars[index]["close"] - bars[index]["open"]) / pip_size
    return (bars[index]["close"] - bars[index - 1]["close"]) / pip_size


def signed_pips(move: float, pip_size: float) -> float:
    return move / pip_size if pip_size else 0.0


def bars_between(
    bars: list[dict[str, Any]],
    day_value: date,
    start_time: dt_time,
    end_time: dt_time,
) -> list[dict[str, Any]]:
    return [
        bar
        for bar in bars
        if bar["time"].date() == day_value and start_time <= bar["time"].time().replace(tzinfo=None) < end_time
    ]


def previous_trading_day(days: list[date], current_day: date) -> date | None:
    previous = [day for day in days if day < current_day]
    return previous[-1] if previous else None


def next_london_window(now: datetime) -> datetime:
    candidate = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now < candidate and candidate.weekday() < 5:
        return candidate
    candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate


def floor_to_five(ts: datetime) -> datetime:
    minute = ts.minute - (ts.minute % 5)
    return ts.replace(minute=minute, second=0, microsecond=0)


def floor_to_half_hour(ts: datetime) -> datetime:
    minute = 30 if ts.minute >= 30 else 0
    return ts.replace(minute=minute, second=0, microsecond=0)


def floor_to_interval(ts: datetime, minutes: int) -> datetime:
    total_minutes = ts.hour * 60 + ts.minute
    floored = total_minutes - (total_minutes % minutes)
    return ts.replace(hour=floored // 60, minute=floored % 60, second=0, microsecond=0)


def aggregate_bars(bars: list[dict[str, Any]], bucket_minutes: int, source_minutes: int) -> list[dict[str, Any]]:
    expected_points = max(1, bucket_minutes // source_minutes)
    grouped: list[list[dict[str, Any]]] = []

    for bar in bars:
        bucket_start = floor_to_interval(bar["time"], bucket_minutes)
        if not grouped or floor_to_interval(grouped[-1][0]["time"], bucket_minutes) != bucket_start:
            grouped.append([bar])
        else:
            grouped[-1].append(bar)

    aggregated: list[dict[str, Any]] = []
    for chunk in grouped:
        if len(chunk) < expected_points:
            continue
        bucket_start = floor_to_interval(chunk[-1]["time"], bucket_minutes)
        aggregated.append(
            {
                "time": bucket_start,
                "open": chunk[0]["open"],
                "high": max(item["high"] for item in chunk),
                "low": min(item["low"] for item in chunk),
                "close": chunk[-1]["close"],
            }
        )
    return aggregated


def session_label(ts: datetime) -> str:
    minutes = ts.hour * 60 + ts.minute
    if 8 * 60 <= minutes < 10 * 60 + 30:
        return "Europe open"
    if 14 * 60 <= minutes < 17 * 60 + 30:
        return "London/New York overlap"
    if 0 <= minutes < 2 * 60:
        return "Asia open"
    if 20 * 60 <= minutes < 21 * 60 + 30:
        return "US fixing"
    return "Technical flow"


def bucket_label(start: datetime, end: datetime) -> str:
    named = session_label(start)
    if named != "Technical flow":
        return named
    return f"Window {start.strftime('%H:%M')} - {end.strftime('%H:%M')}"


def keyword_factor(title: str) -> float:
    lower_title = title.lower()
    return 1.0 + sum(boost for key, boost in KEYWORD_BOOSTS.items() if key in lower_title)


def fetch_chart(pair: str, interval: str, range_value: str) -> dict[str, Any]:
    symbol = pair_info(pair)["yahoo_symbol"]
    cache_key = f"chart:{symbol}:{interval}:{range_value}"

    def builder() -> dict[str, Any]:
        response = _session.get(
            YAHOO_ENDPOINT.format(symbol=symbol),
            params={"interval": interval, "range": range_value, "includePrePost": "true"},
            headers=HEADERS,
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        result = (payload.get("chart", {}).get("result") or [None])[0]
        if not result:
            raise HTTPException(status_code=503, detail="Feed Yahoo non disponibile")
        timestamps = result.get("timestamp") or []
        quote = (result.get("indicators", {}).get("quote") or [{}])[0]
        bars: list[dict[str, Any]] = []
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        for index, raw_ts in enumerate(timestamps):
            close_value = closes[index] if index < len(closes) else None
            if close_value is None:
                continue
            open_value = opens[index] if index < len(opens) and opens[index] is not None else close_value
            high_value = highs[index] if index < len(highs) and highs[index] is not None else max(open_value, close_value)
            low_value = lows[index] if index < len(lows) and lows[index] is not None else min(open_value, close_value)
            bars.append(
                {
                    "time": to_local_time(raw_ts),
                    "open": float(open_value),
                    "high": float(high_value),
                    "low": float(low_value),
                    "close": float(close_value),
                }
            )
        return {"bars": bars, "meta": result.get("meta", {})}

    return cache_get(cache_key, 40, builder)


def fetch_calendar() -> list[dict[str, Any]]:
    def persist(events: list[dict[str, Any]]) -> None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = []
        for event in events:
            payload.append({**event, "time": event["time"].isoformat()})
        CALENDAR_CACHE_FILE.write_text(json.dumps(payload), encoding="utf-8")

    def from_cache() -> list[dict[str, Any]]:
        if not CALENDAR_CACHE_FILE.exists():
            return []
        try:
            payload = json.loads(CALENDAR_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
        restored: list[dict[str, Any]] = []
        for event in payload:
            try:
                restored.append({**event, "time": parse_calendar_time(event["time"])})
            except Exception:
                continue
        restored.sort(key=lambda item: item["time"])
        return restored

    def normalize_json(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for event in events:
            try:
                event_time = parse_calendar_time(event["date"])
            except Exception:
                continue
            normalized.append(
                {
                    "title": event.get("title", "").strip(),
                    "country": event.get("country", "").strip().upper(),
                    "impact": event.get("impact", "Low").title(),
                    "forecast": (event.get("forecast") or "").strip(),
                    "previous": (event.get("previous") or "").strip(),
                    "url": event.get("url", ""),
                    "time": event_time,
                }
            )
        normalized.sort(key=lambda item: item["time"])
        return normalized

    def normalize_xml(text: str) -> list[dict[str, Any]]:
        root = ElementTree.fromstring(text)
        normalized: list[dict[str, Any]] = []
        for node in root.findall(".//event"):
            event_time = parse_calendar_xml_time(node.findtext("date", ""), node.findtext("time", ""))
            if not event_time:
                continue
            normalized.append(
                {
                    "title": (node.findtext("title", "") or "").strip(),
                    "country": (node.findtext("country", "") or "").strip().upper(),
                    "impact": (node.findtext("impact", "Low") or "Low").strip().title(),
                    "forecast": (node.findtext("forecast", "") or "").strip(),
                    "previous": (node.findtext("previous", "") or "").strip(),
                    "url": (node.findtext("url", "") or "").strip(),
                    "time": event_time,
                }
            )
        normalized.sort(key=lambda item: item["time"])
        return normalized

    def builder() -> list[dict[str, Any]]:
        try:
            response = _session.get(FOREX_FACTORY_WEEK, headers=HEADERS, timeout=20)
            response.raise_for_status()
            normalized = normalize_json(response.json())
            if normalized:
                persist(normalized)
                return normalized
        except Exception:
            pass

        try:
            response = _session.get(FOREX_FACTORY_WEEK_XML, headers=HEADERS, timeout=20)
            response.raise_for_status()
            normalized = normalize_xml(response.text)
            if normalized:
                persist(normalized)
                return normalized
        except Exception:
            pass

        cached = from_cache()
        if cached:
            return cached
        raise HTTPException(status_code=503, detail="Calendario macro non disponibile")

    return cache_get("calendar:ff:thisweek", 120, builder)


def build_general_bias(pair: str, daily_bars: list[dict[str, Any]], hourly_bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [bar["close"] for bar in daily_bars]
    current = closes[-1]
    ema20 = ema(closes[-40:], 20)
    ema50 = ema(closes[-90:], 50)
    ten_day_return = current - closes[-11] if len(closes) > 10 else current - closes[0]
    twenty_day_window = closes[-20:] if len(closes) >= 20 else closes
    twenty_day_high = max(twenty_day_window)
    twenty_day_low = min(twenty_day_window)
    location = 0.5
    if twenty_day_high > twenty_day_low:
        location = (current - twenty_day_low) / (twenty_day_high - twenty_day_low)

    hourly_closes = [bar["close"] for bar in hourly_bars]
    day_trend = current - hourly_closes[-25] if len(hourly_closes) > 24 else current - hourly_closes[0]

    score = 0
    drivers: list[str] = []
    if current > ema20 > ema50:
        score += 2
        drivers.append("Prezzo sopra daily EMA 20 e EMA 50")
    elif current < ema20 < ema50:
        score -= 2
        drivers.append("Prezzo sotto daily EMA 20 e EMA 50")

    if ten_day_return > 0:
        score += 1
        drivers.append("Ultimi 10 giorni con progression positiva")
    elif ten_day_return < 0:
        score -= 1
        drivers.append("Ultimi 10 giorni con pressure negativa")

    if location > 0.65:
        score += 1
        drivers.append("Prezzo vicino alla parte alta del 20-day range")
    elif location < 0.35:
        score -= 1
        drivers.append("Prezzo vicino alla parte bassa del 20-day range")

    if day_trend > 0:
        score += 1
        drivers.append("Hourly confirmation coerente con il trend principale")
    elif day_trend < 0:
        score -= 1
        drivers.append("Hourly structure in contrasto o in scarico")

    label = direction_label(score)
    return {
        "label": label,
        "tone": direction_tone(score),
        "score": score,
        "confidence": int(clamp(55 + abs(score) * 8, 55, 92)),
        "summary": f"General bias {label.lower()} basato su trend daily e conferma hourly live.",
        "drivers": drivers[:4],
        "metrics": {
            "ema20": ema20,
            "ema50": ema50,
            "ten_day_return_pips": pip_value(ten_day_return, SUPPORTED_PAIRS[pair]["pip_size"]),
            "range_location": location,
        },
    }


def build_intraday_bias(pair: str, five_minute: list[dict[str, Any]]) -> dict[str, Any]:
    pip_size = SUPPORTED_PAIRS[pair]["pip_size"]
    fifteen_minute = aggregate_bars(five_minute, 15, 5)
    closes_15m = [bar["close"] for bar in fifteen_minute]
    current = closes_15m[-1]
    ema9 = ema(closes_15m[-30:], 9)
    ema21 = ema(closes_15m[-70:], 21)
    ema55 = ema(closes_15m[-170:], 55)
    recent_return = current - closes_15m[-5] if len(closes_15m) > 4 else current - closes_15m[0]
    now = datetime.now(ROME_TZ)
    today_bars = [bar for bar in fifteen_minute if bar["time"].date() == now.date()]
    if not today_bars:
        today_bars = fifteen_minute[-32:]
    session_open = today_bars[0]["open"]
    day_high = max(bar["high"] for bar in today_bars)
    day_low = min(bar["low"] for bar in today_bars)
    day_mid = (day_high + day_low) / 2
    lookback_4h = fifteen_minute[-17:-1] if len(fifteen_minute) > 17 else fifteen_minute[:-1]
    previous_4h_high = max((bar["high"] for bar in lookback_4h), default=current)
    previous_4h_low = min((bar["low"] for bar in lookback_4h), default=current)
    median_15m_range = percentile(
        [pip_value(bar["high"] - bar["low"], pip_size) for bar in fifteen_minute[-180:] if bar["high"] >= bar["low"]],
        0.5,
    )

    score = 0
    drivers: list[str] = []
    if current > ema9 > ema21 > ema55:
        score += 3
        drivers.append("Bullish M15 alignment sopra EMA 9/21/55")
    elif current < ema9 < ema21 < ema55:
        score -= 3
        drivers.append("Bearish M15 alignment sotto EMA 9/21/55")

    if recent_return > 0:
        score += 1
        drivers.append("Ultima ora M15 in acceleration positiva")
    elif recent_return < 0:
        score -= 1
        drivers.append("Ultima ora M15 in acceleration negativa")

    if current > session_open:
        score += 1
        drivers.append("Prezzo M15 sopra session open")
    elif current < session_open:
        score -= 1
        drivers.append("Prezzo M15 sotto session open")

    if current > day_mid:
        score += 1
        drivers.append("Struttura M15 appoggiata sulla meta alta del day range")
    elif current < day_mid:
        score -= 1
        drivers.append("Struttura M15 nella meta bassa del day range")

    if current > previous_4h_high:
        score += 1
        drivers.append("Breakout M15 sopra il 4h high")
    elif current < previous_4h_low:
        score -= 1
        drivers.append("Breakout M15 sotto il 4h low")

    return {
        "label": direction_label(score),
        "tone": direction_tone(score),
        "score": score,
        "confidence": int(clamp(52 + abs(score) * 7, 52, 93)),
        "summary": "Intraday bias aggiornato live solo su struttura M15, senza simulazione.",
        "drivers": drivers[:5],
        "levels": {
            "session_open": session_open,
            "day_high": day_high,
            "day_low": day_low,
            "day_mid": day_mid,
            "four_hour_high": previous_4h_high,
            "four_hour_low": previous_4h_low,
            "median_15m_range_pips": median_15m_range,
            "median_5m_range_pips": median_15m_range,
            "recent_return_pips": recent_return / pip_size if pip_size else 0.0,
        },
    }


def nearest_event(events: list[dict[str, Any]], ts: datetime, currencies: set[str], threshold_minutes: int = 20) -> dict[str, Any] | None:
    candidates = [
        event
        for event in events
        if event["country"] in currencies and abs((event["time"] - ts).total_seconds()) <= threshold_minutes * 60
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: abs((item["time"] - ts).total_seconds()))[0]


def spike_reason(
    ts: datetime,
    event: dict[str, Any] | None,
    direction: str,
    prev_high: float,
    prev_low: float,
    bar: dict[str, Any],
    compressed: bool,
) -> tuple[str, str]:
    if event:
        title = event["title"]
        body = (
            f"Impulso {direction} in concomitanza con {title} su {event['country']}: "
            "il mercato ha repriced rapidamente aspettative macro e liquidity."
        )
        return ("Macro event", body)
    if bar["high"] > prev_high and compressed:
        return (
            "Compression breakout",
            f"Rottura {direction} dopo una fase di compression: il prezzo ha superato l'area dell'ultima ora in una fascia di liquidity sensibile.",
        )
    if bar["low"] < prev_low and compressed:
        return (
            "Compression breakout",
            f"Rottura {direction} dopo compression: scarico veloce sotto i minimi dell'ultima ora con espansione immediata del range.",
        )
    named_session = session_label(ts)
    if named_session != "Technical flow":
        return (
            named_session,
            f"Acceleration {direction} durante {named_session.lower()}, una finestra che tende a concentrare ordini e riallineamenti di flow.",
        )
    if bar["high"] > prev_high or bar["low"] < prev_low:
        return (
            "Technical breakout",
            f"Il prezzo ha rotto i livelli dell'ora precedente con estensione {direction} e assorbimento rapido della liquidity vicina.",
        )
    return (
        "Momentum burst",
        "Espansione improvvisa del range senza news macro vicine: probabile sbilanciamento di ordini o prosecuzione di uno squeeze intraday.",
    )


def detect_spikes(
    pair: str,
    one_minute: list[dict[str, Any]],
    five_minute: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    pip_size = SUPPORTED_PAIRS[pair]["pip_size"]
    minute_jumps = [minute_jump_pips(one_minute, index, pip_size) for index, _ in enumerate(one_minute)]
    threshold = max(percentile(minute_jumps, 0.965), 1.4 if pair.endswith("JPY") else 2.0)
    currencies = {pair[:3], pair[3:]}
    five_lookup = {floor_to_five(bar["time"]): bar for bar in five_minute}
    baseline_median = percentile(minute_jumps, 0.5)
    candidates: list[dict[str, Any]] = []
    last_selected: datetime | None = None

    for index in range(60, len(one_minute)):
        bar = one_minute[index]
        range_pips = minute_jump_pips(one_minute, index, pip_size)
        if range_pips < threshold:
            continue
        if last_selected and (bar["time"] - last_selected).total_seconds() < 20 * 60:
            continue
        previous_bars = one_minute[index - 60 : index]
        previous_ranges = [
            minute_jump_pips(one_minute, back_index, pip_size) for back_index in range(max(1, index - 15), index)
        ]
        compressed = average(previous_ranges) < baseline_median * 0.75 if baseline_median else False
        prev_high = max(item["high"] for item in previous_bars)
        prev_low = min(item["low"] for item in previous_bars)
        matched_event = nearest_event(events, bar["time"], currencies)
        direction = "rialzista" if minute_jump_signed(one_minute, index, pip_size) >= 0 else "ribassista"
        reason_title, reason_body = spike_reason(bar["time"], matched_event, direction, prev_high, prev_low, bar, compressed)
        five_bar = five_lookup.get(floor_to_five(bar["time"]))
        five_range = pip_value((five_bar["high"] - five_bar["low"]) if five_bar else 0.0, pip_size)
        five_move = pip_value((five_bar["close"] - five_bar["open"]) if five_bar else 0.0, pip_size)
        liquidity_taken: list[str] = []
        if bar["high"] > prev_high:
            liquidity_taken.append("Ha preso il previous 1h high e la buy-side liquidity vicina.")
        if bar["low"] < prev_low:
            liquidity_taken.append("Ha preso il previous 1h low e la sell-side liquidity vicina.")
        if not liquidity_taken:
            liquidity_taken.append("Lo spike ha lavorato soprattutto come expansion interna, senza sweep netto dei livelli 1h.")
        candidates.append(
            {
                "time": bar["time"].isoformat(),
                "direction": direction,
                "session": session_label(bar["time"]),
                "one_minute_pips": round(range_pips, 1),
                "one_minute_body_pips": round(abs(minute_jump_signed(one_minute, index, pip_size)), 1),
                "five_minute_pips": round(five_range, 1),
                "five_minute_body_pips": round(five_move, 1),
                "reason_title": reason_title,
                "reason_body": reason_body,
                "event_title": matched_event["title"] if matched_event else None,
                "impact": matched_event["impact"] if matched_event else None,
                "detail_summary": (
                    f"Spike {direction} con jump 1m di {round(range_pips, 1)} pips e range 5m di {round(five_range, 1)} pips."
                ),
                "liquidity_taken": liquidity_taken,
                "reference_levels": {
                    "previous_1h_high": prev_high,
                    "previous_1h_low": prev_low,
                    "spike_open": bar["open"],
                    "spike_close": bar["close"],
                    "spike_high": bar["high"],
                    "spike_low": bar["low"],
                },
                "score": range_pips + five_range * 0.45,
            }
        )
        last_selected = bar["time"]

    ranked = sorted(candidates, key=lambda item: item["score"], reverse=True)[:18]
    ranked.sort(key=lambda item: item["time"], reverse=True)
    return ranked


def build_bucket_maps(
    pair: str,
    one_minute: list[dict[str, Any]],
    five_minute: list[dict[str, Any]],
) -> tuple[dict[int, dict[str, float]], dict[int, dict[str, float]], dict[int, float]]:
    pip_size = SUPPORTED_PAIRS[pair]["pip_size"]
    one_buckets: dict[int, list[float]] = {}
    five_buckets: dict[int, list[float]] = {}

    for index, bar in enumerate(one_minute):
        bucket = bar["time"].hour * 2 + (1 if bar["time"].minute >= 30 else 0)
        one_buckets.setdefault(bucket, []).append(minute_jump_pips(one_minute, index, pip_size))

    for bar in five_minute:
        bucket = bar["time"].hour * 2 + (1 if bar["time"].minute >= 30 else 0)
        five_buckets.setdefault(bucket, []).append(pip_value(bar["high"] - bar["low"], pip_size))

    one_stats: dict[int, dict[str, float]] = {}
    five_stats: dict[int, dict[str, float]] = {}
    bucket_scores: dict[int, float] = {}
    for bucket in range(48):
        one_values = one_buckets.get(bucket, [])
        five_values = five_buckets.get(bucket, [])
        one_stats[bucket] = {
            "mean": average(one_values),
            "p90": percentile(one_values, 0.9),
            "count": float(len(one_values)),
        }
        five_stats[bucket] = {
            "mean": average(five_values),
            "p90": percentile(five_values, 0.9),
            "count": float(len(five_values)),
        }
        bucket_scores[bucket] = five_stats[bucket]["mean"] * 0.55 + five_stats[bucket]["p90"] * 0.45
    return one_stats, five_stats, bucket_scores


def bucket_percentile(bucket_scores: dict[int, float], bucket: int) -> float:
    values = list(bucket_scores.values())
    score = bucket_scores.get(bucket, 0.0)
    lower_or_equal = len([value for value in values if value <= score])
    return lower_or_equal / len(values) if values else 0.0


def build_future_macro(
    pair: str,
    events: list[dict[str, Any]],
    bucket_scores: dict[int, float],
    one_stats: dict[int, dict[str, float]],
    five_stats: dict[int, dict[str, float]],
    base_spike_1m: float,
    base_spike_5m: float,
) -> list[dict[str, Any]]:
    now = datetime.now(ROME_TZ)
    currencies = {pair[:3], pair[3:]}
    relevant = [
        event
        for event in events
        if event["country"] in currencies and event["time"] > now and event["impact"] in {"High", "Medium", "Low"}
    ]
    primary = [event for event in relevant if event["impact"] in {"High", "Medium"}]
    fallback = [event for event in relevant if event["impact"] == "Low"]
    candidates = (primary[:6] + fallback[: max(0, 4 - len(primary))])[:6]
    items: list[dict[str, Any]] = []
    for event in candidates:
        bucket = event["time"].hour * 2 + (1 if event["time"].minute >= 30 else 0)
        bucket_rank = bucket_percentile(bucket_scores, bucket)
        impact_multiplier = IMPACT_FACTOR.get(event["impact"], 1.0)
        news_multiplier = keyword_factor(event["title"])
        timing_multiplier = 0.92 + bucket_rank * 0.4
        predicted_1m = max(one_stats[bucket]["p90"], base_spike_1m * impact_multiplier * news_multiplier * timing_multiplier)
        predicted_5m = max(five_stats[bucket]["p90"], base_spike_5m * impact_multiplier * news_multiplier * timing_multiplier)
        probability = int(
            clamp(
                40 + {"High": 26, "Medium": 15, "Low": 8}[event["impact"]] + bucket_rank * 18 + (news_multiplier - 1.0) * 30,
                42,
                97,
            )
        )
        items.append(
            {
                "kind": "macro",
                "title": f"{event['title']} ({event['country']})",
                "time": event["time"].isoformat(),
                "window_label": bucket_label(floor_to_half_hour(event["time"]), floor_to_half_hour(event["time"]) + timedelta(minutes=30)),
                "impact": event["impact"],
                "probability": probability,
                "expected_one_minute_pips": round(predicted_1m, 1),
                "expected_five_minute_pips": round(predicted_5m, 1),
                "reason": (
                    f"Evento {event['impact'].lower()} su {event['country']} in una fascia che per {SUPPORTED_PAIRS[pair]['label']} "
                    "ha già prodotto re-pricing rapidi: previsione basata su baseline live e stagionalità intraday recente."
                ),
                "forecast": event["forecast"],
                "previous": event["previous"],
                "url": event["url"],
            }
        )
    return items


def build_future_sessions(
    pair: str,
    one_stats: dict[int, dict[str, float]],
    five_stats: dict[int, dict[str, float]],
    bucket_scores: dict[int, float],
) -> list[dict[str, Any]]:
    now = datetime.now(ROME_TZ)
    start = floor_to_half_hour(now)
    candidates: list[dict[str, Any]] = []
    for step in range(1, 49):
        bucket_start = start + timedelta(minutes=30 * step)
        bucket_end = bucket_start + timedelta(minutes=30)
        bucket = bucket_start.hour * 2 + (1 if bucket_start.minute >= 30 else 0)
        five_snapshot = five_stats[bucket]
        if five_snapshot["count"] < 3:
            continue
        rank = bucket_percentile(bucket_scores, bucket)
        probability = int(clamp(38 + rank * 44, 40, 89))
        candidates.append(
            {
                "kind": "session",
                "title": bucket_label(bucket_start, bucket_end),
                "time": bucket_start.isoformat(),
                "window_label": f"{bucket_start.strftime('%H:%M')} - {bucket_end.strftime('%H:%M')}",
                "impact": "Statistico",
                "probability": probability,
                "expected_one_minute_pips": round(max(one_stats[bucket]["mean"], one_stats[bucket]["p90"]), 1),
                "expected_five_minute_pips": round(max(five_snapshot["mean"], five_snapshot["p90"]), 1),
                "reason": (
                    f"Negli ultimi campioni live questa finestra è nel percentile {int(rank * 100)} "
                    f"per range medio 5m su {SUPPORTED_PAIRS[pair]['label']}, quindi resta una candidata naturale a nuovi scatti."
                ),
                "forecast": "",
                "previous": "",
                "url": "",
            }
        )

    selected = sorted(candidates, key=lambda item: (-item["probability"], item["time"]))[:4]
    selected.sort(key=lambda item: item["time"])
    return selected


def zone_snapshot(
    pair: str,
    label: str,
    side: str,
    level: float,
    before_london: list[dict[str, Any]],
    london_window: list[dict[str, Any]],
    after_london: list[dict[str, Any]],
    current_price: float,
) -> dict[str, Any]:
    pip_size = SUPPORTED_PAIRS[pair]["pip_size"]
    if side == "buy-side":
        before_taken = any(bar["high"] >= level for bar in before_london)
        london_taken = any(bar["high"] >= level for bar in london_window)
        after_taken = any(bar["high"] >= level for bar in after_london)
    else:
        before_taken = any(bar["low"] <= level for bar in before_london)
        london_taken = any(bar["low"] <= level for bar in london_window)
        after_taken = any(bar["low"] <= level for bar in after_london)

    if london_taken:
        status = "taken in London"
        status_key = "taken"
    elif before_taken:
        status = "taken before London"
        status_key = "taken-before"
    elif after_taken:
        status = "taken after London"
        status_key = "taken-after"
    else:
        status = "open"
        status_key = "open"

    distance = signed_pips(level - current_price, pip_size)
    return {
        "label": label,
        "side": side,
        "price": level,
        "status": status,
        "status_key": status_key,
        "distance_pips": round(distance, 1),
    }


def build_london_playbook(
    pair: str,
    five_minute_60d: list[dict[str, Any]],
    current_price: float,
    general_bias: dict[str, Any],
    intraday_bias: dict[str, Any],
) -> dict[str, Any]:
    pip_size = SUPPORTED_PAIRS[pair]["pip_size"]
    grouped_days = sorted({bar["time"].date() for bar in five_minute_60d})
    london_sessions: list[dict[str, Any]] = []
    for day_value in grouped_days:
        london_bars = bars_between(five_minute_60d, day_value, dt_time(9, 0), dt_time(10, 0))
        if len(london_bars) < 6:
            continue
        london_range = pip_value(max(bar["high"] for bar in london_bars) - min(bar["low"] for bar in london_bars), pip_size)
        london_sessions.append(
            {
                "date": day_value,
                "range_pips": london_range,
                "open": london_bars[0]["open"],
                "close": london_bars[-1]["close"],
            }
        )

    last_30_sessions = london_sessions[-30:]
    avg_range = average([item["range_pips"] for item in last_30_sessions])
    median_range = percentile([item["range_pips"] for item in last_30_sessions], 0.5)
    bullish_closes = len([item for item in last_30_sessions if item["close"] > item["open"]])
    bearish_closes = len([item for item in last_30_sessions if item["close"] < item["open"]])

    today = five_minute_60d[-1]["time"].date()
    today_bars = [bar for bar in five_minute_60d if bar["time"].date() == today]
    before_london = bars_between(five_minute_60d, today, dt_time(0, 0), dt_time(9, 0))
    london_window = bars_between(five_minute_60d, today, dt_time(9, 0), dt_time(10, 0))
    after_london = [bar for bar in today_bars if bar["time"].time().replace(tzinfo=None) >= dt_time(10, 0)]
    previous_day_value = previous_trading_day(grouped_days, today)
    previous_day_bars = [bar for bar in five_minute_60d if bar["time"].date() == previous_day_value] if previous_day_value else []

    asia_high = max((bar["high"] for bar in before_london), default=current_price)
    asia_low = min((bar["low"] for bar in before_london), default=current_price)
    previous_day_high = max((bar["high"] for bar in previous_day_bars), default=current_price)
    previous_day_low = min((bar["low"] for bar in previous_day_bars), default=current_price)

    zones = [
        zone_snapshot(pair, "Asia high", "buy-side", asia_high, [], london_window, after_london, current_price),
        zone_snapshot(pair, "Previous day high", "buy-side", previous_day_high, before_london, london_window, after_london, current_price),
        zone_snapshot(pair, "Asia low", "sell-side", asia_low, [], london_window, after_london, current_price),
        zone_snapshot(pair, "Previous day low", "sell-side", previous_day_low, before_london, london_window, after_london, current_price),
    ]

    open_above = sorted(
        [zone for zone in zones if zone["status_key"] == "open" and zone["distance_pips"] > 0],
        key=lambda item: item["distance_pips"],
    )
    open_below = sorted(
        [zone for zone in zones if zone["status_key"] == "open" and zone["distance_pips"] < 0],
        key=lambda item: abs(item["distance_pips"]),
    )
    taken_zones = [zone["label"] for zone in zones if zone["status_key"] != "open"]
    open_zones = [zone["label"] for zone in zones if zone["status_key"] == "open"]

    alignment_score = general_bias["score"] + intraday_bias["score"]
    if alignment_score >= 3:
        title = "London setup bullish"
        primary = open_above[0] if open_above else None
        hedge = open_below[0] if open_below else None
        scenario = (
            f"General bias e Intraday bias sono allineati long. Londra tende a lavorare in continuation finche il pair non perde il session structure."
        )
        if primary:
            scenario += (
                f" La buy-side liquidity piu vicina resta {primary['label']} a {format_price(primary['price'], pair)} "
                f"({abs(primary['distance_pips']):.1f} pips), quindi e un target realistico se resta dentro il London average range."
            )
        if hedge:
            scenario += (
                f" Il rischio contrario e un first sweep sotto {hedge['label']} a {format_price(hedge['price'], pair)} "
                "prima di una eventuale continuation."
            )
    elif alignment_score <= -3:
        title = "London setup bearish"
        primary = open_below[0] if open_below else None
        hedge = open_above[0] if open_above else None
        scenario = (
            "General bias e Intraday bias sono allineati short. Londra ha spazio per cercare sell-side liquidity se il prezzo resta debole in apertura."
        )
        if primary:
            scenario += (
                f" Il target piu vicino e {primary['label']} a {format_price(primary['price'], pair)} "
                f"({abs(primary['distance_pips']):.1f} pips), raggiungibile se il move entra nel London average range."
            )
        if hedge:
            scenario += (
                f" Se invece arriva un counter move, la prima area sensibile resta {hedge['label']} a {format_price(hedge['price'], pair)}."
            )
    else:
        title = "London setup mixed"
        nearest_open = sorted(
            [zone for zone in zones if zone["status_key"] == "open"],
            key=lambda item: abs(item["distance_pips"]),
        )
        scenario = (
            "Bias generale e intraday non sono perfettamente allineati, quindi Londra potrebbe lavorare in two-sided sweep prima di scegliere direzione."
        )
        if nearest_open:
            first_zone = nearest_open[0]
            scenario += (
                f" La liquidity piu vicina resta {first_zone['label']} a {format_price(first_zone['price'], pair)} "
                f"({abs(first_zone['distance_pips']):.1f} pips), quindi e la prima candidata ad essere presa."
            )

    taken_line = ", ".join(taken_zones) if taken_zones else "nessuna zona presa"
    open_line = ", ".join(open_zones) if open_zones else "nessuna zona aperta"
    next_window = next_london_window(datetime.now(ROME_TZ))
    now = datetime.now(ROME_TZ)
    if now < now.replace(hour=9, minute=0, second=0, microsecond=0):
        window_state = "pre-London"
    elif now < now.replace(hour=10, minute=0, second=0, microsecond=0):
        window_state = "in London"
    else:
        window_state = "post-London"

    return {
        "title": title,
        "window_state": window_state,
        "next_window": next_window.isoformat(),
        "average_range_pips": round(avg_range, 1),
        "median_range_pips": round(median_range, 1),
        "sample_size": len(last_30_sessions),
        "bullish_closes": bullish_closes,
        "bearish_closes": bearish_closes,
        "zones": zones,
        "summary": (
            f"Negli ultimi {len(last_30_sessions)} London opens utili, la finestra 09:00-10:00 Rome ha sviluppato in media "
            f"{round(avg_range, 1)} pips con mediana {round(median_range, 1)} pips."
        ),
        "ai_analysis": (
            f"{scenario} Zone gia prese: {taken_line}. Zone ancora da prendere: {open_line}."
        ),
    }


def build_intraday_chart_analysis(
    pair: str,
    five_minute_60d: list[dict[str, Any]],
    hourly: list[dict[str, Any]],
    daily: list[dict[str, Any]],
    current_price: float,
    general_bias: dict[str, Any],
    intraday_bias: dict[str, Any],
) -> dict[str, Any]:
    pip_size = SUPPORTED_PAIRS[pair]["pip_size"]
    today = five_minute_60d[-1]["time"].date()
    today_bars = [bar for bar in five_minute_60d if bar["time"].date() == today]
    grouped_days = sorted({bar["time"].date() for bar in five_minute_60d})
    previous_day_value = previous_trading_day(grouped_days, today)
    previous_day_bars = [bar for bar in five_minute_60d if bar["time"].date() == previous_day_value] if previous_day_value else []
    asia_bars = bars_between(five_minute_60d, today, dt_time(0, 0), dt_time(9, 0))

    session_open = today_bars[0]["open"] if today_bars else current_price
    day_high = max((bar["high"] for bar in today_bars), default=current_price)
    day_low = min((bar["low"] for bar in today_bars), default=current_price)
    asia_high = max((bar["high"] for bar in asia_bars), default=current_price)
    asia_low = min((bar["low"] for bar in asia_bars), default=current_price)
    previous_day_high = max((bar["high"] for bar in previous_day_bars), default=current_price)
    previous_day_low = min((bar["low"] for bar in previous_day_bars), default=current_price)

    last_week_daily = daily[-6:-1] if len(daily) >= 6 else daily[:-1]
    weekly_high = max((bar["high"] for bar in last_week_daily), default=current_price)
    weekly_low = min((bar["low"] for bar in last_week_daily), default=current_price)
    four_hour_window = hourly[-5:-1] if len(hourly) >= 5 else hourly[:-1]
    four_hour_high = max((bar["high"] for bar in four_hour_window), default=current_price)
    four_hour_low = min((bar["low"] for bar in four_hour_window), default=current_price)

    today_high_taken = lambda level: any(bar["high"] >= level for bar in today_bars)
    today_low_taken = lambda level: any(bar["low"] <= level for bar in today_bars)

    zones = [
        {"label": "Asia high", "side": "buy-side", "price": asia_high, "taken_today": today_high_taken(asia_high), "why": "liquidity sopra il range asiatico"},
        {"label": "Previous day high", "side": "buy-side", "price": previous_day_high, "taken_today": today_high_taken(previous_day_high), "why": "liquidity sul massimo del giorno precedente"},
        {"label": "Week high", "side": "buy-side", "price": weekly_high, "taken_today": today_high_taken(weekly_high), "why": "magnete di liquidity della settimana"},
        {"label": "4h high", "side": "buy-side", "price": four_hour_high, "taken_today": today_high_taken(four_hour_high), "why": "breakout level della struttura 4h"},
        {"label": "Asia low", "side": "sell-side", "price": asia_low, "taken_today": today_low_taken(asia_low), "why": "liquidity sotto il range asiatico"},
        {"label": "Previous day low", "side": "sell-side", "price": previous_day_low, "taken_today": today_low_taken(previous_day_low), "why": "liquidity sul minimo del giorno precedente"},
        {"label": "Week low", "side": "sell-side", "price": weekly_low, "taken_today": today_low_taken(weekly_low), "why": "magnete di liquidity della settimana"},
        {"label": "4h low", "side": "sell-side", "price": four_hour_low, "taken_today": today_low_taken(four_hour_low), "why": "breakout level della struttura 4h"},
    ]

    enriched_zones = []
    for zone in zones:
        distance_pips = signed_pips(zone["price"] - current_price, pip_size)
        status = "taken" if zone["taken_today"] else "open"
        enriched_zones.append(
            {
                **zone,
                "status": status,
                "distance_pips": round(distance_pips, 1),
            }
        )

    open_above = sorted(
        [zone for zone in enriched_zones if zone["status"] == "open" and zone["distance_pips"] > 0],
        key=lambda item: item["distance_pips"],
    )
    open_below = sorted(
        [zone for zone in enriched_zones if zone["status"] == "open" and zone["distance_pips"] < 0],
        key=lambda item: abs(item["distance_pips"]),
    )
    all_above = sorted(
        [zone for zone in enriched_zones if zone["distance_pips"] > 0],
        key=lambda item: abs(item["distance_pips"]),
    )
    all_below = sorted(
        [zone for zone in enriched_zones if zone["distance_pips"] < 0],
        key=lambda item: abs(item["distance_pips"]),
    )
    nearest_any = sorted(enriched_zones, key=lambda item: abs(item["distance_pips"]))

    alignment = general_bias["score"] + intraday_bias["score"]
    structure_above_open = current_price > session_open
    structure_near_high = pip_value(day_high - current_price, pip_size) < pip_value(current_price - day_low, pip_size)
    structure_hint = "sopra session open" if structure_above_open else "sotto session open"

    if alignment >= 3:
        primary_targets = open_above[:3] if open_above else (all_above[:3] if all_above else nearest_any[:3])
        hedge_target = open_below[0] if open_below else None
        headline = "Intraday AI outlook bullish"
        scenario = (
            f"Il chart live mostra una struttura {structure_hint} con bias combinata positiva. "
            "Il mercato ha piu probabilita di continuare a cercare buy-side liquidity se non perde il ritmo intraday."
        )
        if structure_near_high:
            scenario += " Il prezzo e gia nella meta alta del day range, quindi i target sopra possono essere attaccati senza bisogno di un reset profondo."
        if primary_targets:
            zone_line = ", ".join(
                f"{item['label']} {format_price(item['price'], pair)} ({abs(item['distance_pips']):.1f} pips)"
                for item in primary_targets
            )
            scenario += f" Le prime liquidity zones sopra prezzo sono: {zone_line}."
        if hedge_target:
            scenario += (
                f" L'invalidation area piu credibile resta {hedge_target['label']} a {format_price(hedge_target['price'], pair)} "
                f"({abs(hedge_target['distance_pips']):.1f} pips) se arriva un first sweep contrario."
            )
    elif alignment <= -3:
        primary_targets = open_below[:3] if open_below else (all_below[:3] if all_below else nearest_any[:3])
        hedge_target = open_above[0] if open_above else None
        headline = "Intraday AI outlook bearish"
        scenario = (
            f"Il chart live mostra una struttura {structure_hint} con bias combinata negativa. "
            "Il mercato ha piu probabilita di spingere verso sell-side liquidity finche non recupera con decisione il blocco intraday superiore."
        )
        if not structure_near_high:
            scenario += " Il prezzo e gia nella meta bassa del day range, quindi la continuation short resta coerente con il contesto."
        if primary_targets:
            zone_line = ", ".join(
                f"{item['label']} {format_price(item['price'], pair)} ({abs(item['distance_pips']):.1f} pips)"
                for item in primary_targets
            )
            scenario += f" Le prime liquidity zones sotto prezzo sono: {zone_line}."
        if hedge_target:
            scenario += (
                f" La prima invalidation area utile resta {hedge_target['label']} a {format_price(hedge_target['price'], pair)} "
                f"({abs(hedge_target['distance_pips']):.1f} pips) in caso di squeeze contrario."
            )
    else:
        primary_targets = sorted(
            [zone for zone in enriched_zones if zone["status"] == "open"],
            key=lambda item: abs(item["distance_pips"]),
        )[:4]
        hedge_target = None
        headline = "Intraday AI outlook mixed"
        scenario = (
            "Il chart live non mostra ancora un allineamento totale tra general bias e intraday bias. "
            "Per oggi il rischio piu realistico resta un two-sided sweep: il mercato puo prendere liquidity da un lato e girarsi subito sull'altro."
        )
        if primary_targets:
            zone_line = ", ".join(
                f"{item['label']} {format_price(item['price'], pair)} ({abs(item['distance_pips']):.1f} pips)"
                for item in primary_targets
            )
            scenario += f" Le liquidity zones piu vicine al prezzo sono: {zone_line}."

    if len(primary_targets) < 3:
        existing = {zone["label"] for zone in primary_targets}
        for zone in nearest_any:
            if zone["label"] in existing:
                continue
            primary_targets.append(zone)
            existing.add(zone["label"])
            if len(primary_targets) >= 3:
                break

    target_cards = []
    for zone in primary_targets:
        target_cards.append(
            {
                "label": zone["label"],
                "price": zone["price"],
                "distance_pips": abs(zone["distance_pips"]),
                "side": zone["side"],
                "status": zone["status"],
                "why": zone["why"],
            }
        )

    open_zone_names = [zone["label"] for zone in enriched_zones if zone["status"] == "open"]
    taken_zone_names = [zone["label"] for zone in enriched_zones if zone["status"] == "taken"]
    chart_context = (
        f"Lettura AI intraday live allineata al chart TradingView {pair_info(pair)['label']}: "
        f"current price {format_price(current_price, pair)}, day high {format_price(day_high, pair)}, day low {format_price(day_low, pair)}, session open {format_price(session_open, pair)}."
    )
    return {
        "headline": headline,
        "summary": chart_context,
        "analysis": (
            f"{scenario} Zone gia toccate oggi: {', '.join(taken_zone_names) if taken_zone_names else 'nessuna'}. "
            f"Zone ancora aperte: {', '.join(open_zone_names) if open_zone_names else 'nessuna'}."
        ),
        "targets": target_cards,
        "all_zones": enriched_zones,
        "current_price": current_price,
        "tradingview_symbol": f"FX:{pair}",
    }


def build_dashboard(pair: str) -> dict[str, Any]:
    pair = normalize_symbol(pair)
    charts_1m = fetch_chart(pair, "1m", "7d")
    charts_5m = fetch_chart(pair, "5m", "1mo")
    charts_5m_60d = fetch_chart(pair, "5m", "60d")
    charts_60m = fetch_chart(pair, "60m", "1mo")
    charts_1d = fetch_chart(pair, "1d", "6mo")
    calendar = fetch_calendar()

    one_minute = charts_1m["bars"]
    five_minute = charts_5m["bars"]
    five_minute_60d = charts_5m_60d["bars"]
    hourly = charts_60m["bars"]
    daily = charts_1d["bars"]
    if not one_minute or not five_minute or not five_minute_60d or not hourly or not daily:
        raise HTTPException(status_code=503, detail="Feed dati incompleto")

    info = pair_info(pair)
    latest = one_minute[-1]
    now = datetime.now(ROME_TZ)
    age_minutes = max(0, int((now - latest["time"]).total_seconds() // 60))
    previous_close = daily[-2]["close"] if len(daily) > 1 else daily[-1]["close"]
    daily_change_pct = ((latest["close"] / previous_close) - 1) * 100 if previous_close else 0.0

    one_ranges = [minute_jump_pips(one_minute, index, info["pip_size"]) for index, _ in enumerate(one_minute)]
    five_ranges = [pip_value(bar["high"] - bar["low"], info["pip_size"]) for bar in five_minute]
    base_spike_1m = percentile(one_ranges, 0.95)
    base_spike_5m = percentile(five_ranges, 0.95)

    today_five = [bar for bar in five_minute if bar["time"].date() == latest["time"].date()]
    if not today_five:
        today_five = five_minute[-48:]

    general_bias = build_general_bias(pair, daily, hourly)
    intraday_bias = build_intraday_bias(pair, five_minute)
    historical_spikes = detect_spikes(pair, one_minute, five_minute, calendar)
    one_stats, five_stats, bucket_scores = build_bucket_maps(pair, one_minute, five_minute)
    future_macro = build_future_macro(pair, calendar, bucket_scores, one_stats, five_stats, base_spike_1m, base_spike_5m)
    future_sessions = build_future_sessions(pair, one_stats, five_stats, bucket_scores)
    london_playbook = build_london_playbook(pair, five_minute_60d, latest["close"], general_bias, intraday_bias)
    intraday_ai = build_intraday_chart_analysis(pair, five_minute_60d, hourly, daily, latest["close"], general_bias, intraday_bias)

    live_state = "live" if age_minutes <= 15 and now.weekday() < 5 else "slow"
    return {
        "pair": info,
        "meta": {
            "generated_at": now.isoformat(),
            "price_updated_at": latest["time"].isoformat(),
            "calendar_source": "Forex Factory weekly JSON",
            "price_source": "Yahoo Finance chart feed",
            "live_state": live_state,
            "age_minutes": age_minutes,
        },
        "snapshot": {
            "price": latest["close"],
            "price_label": format_price(latest["close"], pair),
            "daily_change_pct": round(daily_change_pct, 3),
            "day_high": max(bar["high"] for bar in today_five),
            "day_low": min(bar["low"] for bar in today_five),
            "last_minute_range_pips": round(one_ranges[-1], 1),
            "last_five_minute_range_pips": round(five_ranges[-1], 1),
            "market_note": "Bias live, nessuna simulazione: i punteggi nascono dai feed correnti e dal calendario macro in arrivo.",
        },
        "bias_general": general_bias,
        "bias_intraday": intraday_bias,
        "intraday_ai": intraday_ai,
        "london_playbook": london_playbook,
        "historical_spikes": historical_spikes,
        "future_catalog": {
            "macro": future_macro,
            "sessions": future_sessions,
        },
        "notes": [
            "Questa risposta mantiene compatibilita anche con la UI precedente, cosi il feed non si rompe mentre il browser aggiorna la cache.",
            "Bias generale e intraday restano live sui feed correnti del pair scelto.",
            "Il London playbook aggiunge range medio 30d e lettura AI delle liquidity zones nella finestra 09:00-10:00 Rome.",
        ],
    }


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/manifest.webmanifest")
def manifest() -> FileResponse:
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(STATIC_DIR / "sw.js", media_type="text/javascript")


@app.get("/robots.txt")
def robots() -> FileResponse:
    return FileResponse(STATIC_DIR / "robots.txt", media_type="text/plain")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/pairs")
def pairs() -> dict[str, Any]:
    items = []
    for code in SUPPORTED_PAIRS:
        info = pair_info(code)
        items.append({"code": code, "label": info["label"], "base": info["base"], "quote": info["quote"]})
    return {"pairs": items}


@app.get("/api/dashboard")
def dashboard(symbol: str = Query("EURUSD")) -> dict[str, Any]:
    pair = normalize_symbol(symbol)
    return cache_get(f"dashboard:{pair}", 25, lambda: build_dashboard(pair))
