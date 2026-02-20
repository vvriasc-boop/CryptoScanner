"""CryptoScanner — расчёт сигналов: E[return] по событиям и токенам."""

import logging
from collections import defaultdict

import config

logger = logging.getLogger("crypto_scanner.signal")


def _nn(val, fallback):
    """val if not None, else fallback."""
    return val if val is not None else fallback


def calculate_event_expected_return(outcomes: list[dict]) -> dict | None:
    """E[return] для одного события = Σ(P × impact). None при невалидных данных."""
    if not outcomes:
        return None
    for o in outcomes:
        p, imp = o.get("probability"), o.get("price_impact_pct")
        if p is None or imp is None or not (0.0 <= p <= 1.0):
            return None

    e_ret = sum(o["probability"] * o["price_impact_pct"] for o in outcomes)
    e_bull = sum(
        o["probability"] * _nn(o.get("price_impact_high"), o["price_impact_pct"])
        for o in outcomes)
    e_bear = sum(
        o["probability"] * _nn(o.get("price_impact_low"), o["price_impact_pct"])
        for o in outcomes)

    deltas = [(_nn(o.get("probability_high"), o["probability"])
               - _nn(o.get("probability_low"), o["probability"])) / 2
              for o in outcomes]
    conf_d = sum(deltas) / len(deltas) if deltas else 0

    return {
        "e_return": round(e_ret, 4),
        "e_return_bull": round(e_bull, 4),
        "e_return_bear": round(e_bear, 4),
        "confidence_delta": round(conf_d, 4),
        "outcomes_count": len(outcomes),
    }


def _clamp(val: float, limit: float) -> float:
    return max(-limit, min(limit, val))


def calculate_token_signal(token: str, events_data: list[dict]) -> dict:
    """Агрегация E[return] по всем событиям одного токена → сигнал."""
    total_er = sum(ed["e_return"]["e_return"] for ed in events_data)
    total_bull = sum(ed["e_return"]["e_return_bull"] for ed in events_data)
    total_bear = sum(ed["e_return"]["e_return_bear"] for ed in events_data)
    avg_conf = (sum(ed["e_return"]["confidence_delta"] for ed in events_data)
                / len(events_data)) if events_data else 0

    cap = config.MAX_TOKEN_E_RETURN
    capped = (abs(total_er) > cap or abs(total_bull) > cap
              or abs(total_bear) > cap)
    total_er = _clamp(total_er, cap)
    total_bull = _clamp(total_bull, cap)
    total_bear = _clamp(total_bear, cap)

    thr = config.SIGNAL_THRESHOLD
    if total_er > thr:
        signal, strength = "LONG", "strong" if total_er > thr * 2 else "moderate"
    elif total_er < -thr:
        signal, strength = "SHORT", "strong" if total_er < -thr * 2 else "moderate"
    else:
        signal, strength = "NEUTRAL", "none"

    return {
        "token": token, "signal": signal, "strength": strength,
        "total_e_return": round(total_er, 4),
        "total_bull": round(total_bull, 4),
        "total_bear": round(total_bear, 4),
        "avg_confidence_delta": round(avg_conf, 4),
        "events_count": len(events_data),
        "capped": capped,
        "events": [{"title": ed["event"].get("title", "?"),
                     "type": ed["event"].get("event_type", "?"),
                     "e_return": ed["e_return"]["e_return"]}
                    for ed in events_data],
    }


async def generate_all_signals(db, limit: int = 50) -> list[dict]:
    """Собрать все сигналы по всем токенам из БД."""
    from database.db import get_events_with_complete_data

    rows = await get_events_with_complete_data(db, limit=limit * 10)
    if not rows:
        return []

    events_map: dict = {}
    for row in rows:
        eid = row["id"]
        if eid not in events_map:
            events_map[eid] = {
                "event": {"id": eid, "coin_symbol": row["coin_symbol"],
                          "event_type": row["event_type"],
                          "title": row["title"],
                          "importance": row["importance"]},
                "outcomes": [],
            }
        events_map[eid]["outcomes"].append({
            "outcome_key": row["outcome_key"],
            "probability": row["probability"],
            "probability_low": row["probability_low"],
            "probability_high": row["probability_high"],
            "price_impact_pct": row["price_impact_pct"],
            "price_impact_low": row["price_impact_low"],
            "price_impact_high": row["price_impact_high"],
        })

    by_token: dict[str, list] = defaultdict(list)
    for em in events_map.values():
        er = calculate_event_expected_return(em["outcomes"])
        if er is None:
            logger.warning(f"Skip event {em['event'].get('title')}: incomplete")
            continue
        by_token[em["event"]["coin_symbol"]].append(
            {"event": em["event"], "e_return": er})

    signals = [calculate_token_signal(t, ed) for t, ed in by_token.items()]
    signals.sort(key=lambda s: abs(s["total_e_return"]), reverse=True)
    return signals[:limit]
