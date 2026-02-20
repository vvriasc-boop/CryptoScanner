"""CryptoScanner — генератор отчёта с полной цепочкой рассуждений."""
import os, sqlite3, sys
from datetime import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from services.signal_calculator import calculate_event_expected_return, calculate_token_signal

def _nn(v, fb): return v if v is not None else fb

def main():
    today = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(str(config.REPORTS_DIR), exist_ok=True)
    path = config.REPORTS_DIR / f"signal_report_{today}.txt"
    db = sqlite3.connect(str(config.DB_PATH)); db.row_factory = sqlite3.Row
    try:
        rows = db.execute("""
            SELECT e.id eid, e.coin_symbol, e.event_type, e.title, e.importance,
                   e.date_event, e.source_name, eo.outcome_key, eo.outcome_text,
                   eo.probability, eo.probability_low, eo.probability_high,
                   eo.price_impact_pct, eo.price_impact_low, eo.price_impact_high
            FROM events_v2 e JOIN event_outcomes eo ON e.id = eo.event_id
            WHERE eo.probability IS NOT NULL AND eo.price_impact_pct IS NOT NULL
            ORDER BY e.coin_symbol, e.id, eo.outcome_key""").fetchall()
        if not rows:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"CRYPTOSCANNER — {today}\nНет данных с полными оценками.\n")
            print(f"⚠️  Нет данных. Отчёт: {path}"); return
        # --- Group by event ---
        evmap = {}
        for r in rows:
            eid = r["eid"]
            if eid not in evmap:
                evmap[eid] = {"coin_symbol": r["coin_symbol"], "event_type": r["event_type"],
                    "title": r["title"], "importance": r["importance"] or "?",
                    "date_event": r["date_event"], "source_name": r["source_name"] or "?",
                    "outcomes": []}
            evmap[eid]["outcomes"].append({k: r[k] for k in (
                "outcome_key", "outcome_text", "probability", "probability_low",
                "probability_high", "price_impact_pct", "price_impact_low", "price_impact_high")})
        # --- Calculate signals ---
        by_tok = {}
        for ev in evmap.values():
            er = calculate_event_expected_return(ev["outcomes"])
            if not er: continue
            by_tok.setdefault(ev["coin_symbol"], []).append({"event": ev, "e_return": er})
        sigs = [calculate_token_signal(t, ed) for t, ed in by_tok.items()]
        for s in sigs: s["detail"] = by_tok[s["token"]]
        sigs.sort(key=lambda s: abs(s["total_e_return"]), reverse=True)

        longs = sum(1 for s in sigs if s["signal"] == "LONG")
        shorts = sum(1 for s in sigs if s["signal"] == "SHORT")
        neut = len(sigs) - longs - shorts
        W = 64; L = []
        # --- Header ---
        L.append("╔" + "═" * W + "╗")
        for txt in [f"CRYPTOSCANNER — СИГНАЛЫ НА {today}",
                     f"Токенов: {len(sigs)} | LONG: {longs} | SHORT: {shorts} | NEUTRAL: {neut}",
                     f"Порог: ±{config.SIGNAL_THRESHOLD}% | Cap: ±{config.MAX_TOKEN_E_RETURN}%"]:
            L.append(f"║  {txt:<{W - 2}}║")
        L.append("╚" + "═" * W + "╝\n")
        # --- Each token ---
        for sig in sigs:
            ic = {"LONG": "🟢 LONG", "SHORT": "🔴 SHORT"}.get(sig["signal"], "⚪ NEUTRAL")
            cd = sig["avg_confidence_delta"]
            cf = "высокая" if cd < 0.03 else ("средняя" if cd < 0.08 else "низкая")
            cap = " ⚠️ capped" if sig.get("capped") else ""
            L += ["═" * W, f"{ic}  {sig['token']}  |  E[return] = {sig['total_e_return']:+.2f}%"
                  f"{cap}  |  {cf} (Δ={cd:.2f})", "═" * W, ""]
            for i, ed in enumerate(sig["detail"], 1):
                ev, outs = ed["event"], ed["event"]["outcomes"]
                L.append(f"  📌 Событие {i}: {ev['title']} ({ev['event_type']}, {ev['importance']})")
                L.append(f"     Дата: {ev['date_event'] or 'N/A'} | Источник: {ev['source_name']}\n")
                L += ["     ┌─────┬─────────────────────────────┬────────────────────┬─────────────────────┐",
                      "     │ Key │ Описание                    │ Вероятность        │ Влияние на цену     │",
                      "     ├─────┼─────────────────────────────┼────────────────────┼─────────────────────┤"]
                for o in outs:
                    p, imp = o["probability"], o["price_impact_pct"]
                    pl, ph = _nn(o["probability_low"], p), _nn(o["probability_high"], p)
                    il, ih = _nn(o["price_impact_low"], imp), _nn(o["price_impact_high"], imp)
                    d = (o["outcome_text"] or "?")[:27]
                    L.append(f"     │  {o['outcome_key']}  │ {d:27s} │ P={p:.2f} [{pl:.2f}-{ph:.2f}]│ "
                             f"{imp:+.1f}% [{il:+.1f}..{ih:+.1f}]│")
                L.append("     └─────┴─────────────────────────────┴────────────────────┴─────────────────────┘\n")
                parts = " + ".join(f"{o['probability']:.2f}×({o['price_impact_pct']:+.1f})" for o in outs)
                L.append(f"     E[return] = {parts} = {ed['e_return']['e_return']:+.2f}%\n")
            er_sum = " + ".join(f"{d['e_return']['e_return']:+.2f}%" for d in sig["detail"])
            L += [f"  📊 ИТОГ ПО {sig['token']}:", f"     E[return]: {er_sum} = "
                  f"{sig['total_e_return']:+.2f}%{cap}",
                  f"     Диапазон: [bear: {sig['total_bear']:+.2f}% .. bull: {sig['total_bull']:+.2f}%]\n"]
        # --- Trading summary ---
        L += ["═" * W, "СВОДКА СИГНАЛОВ ДЛЯ ТОРГОВЛИ", "═" * W]
        for s in sigs:
            if s["signal"] == "NEUTRAL": continue
            ic = "🟢 LONG " if s["signal"] == "LONG" else "🔴 SHORT"
            cd = s["avg_confidence_delta"]
            cf = "высокая" if cd < 0.03 else ("средняя" if cd < 0.08 else "низкая")
            cp = " ⚠️capped" if s.get("capped") else ""
            L.append(f"  {ic}  {s['token']:7s} {s['total_e_return']:+.2f}%{cp:12s}"
                     f"  ({s['events_count']} соб., {cf})")
        L += ["", "  ⚠️  Это НЕ финансовая рекомендация. Перепроверяйте данные.", ""]
        # --- Metadata ---
        from services.groq_client import _active_providers
        provs = ", ".join(p["name"] for p in _active_providers)
        n_ev = db.execute("SELECT COUNT(*) FROM events_v2").fetchone()[0]
        L += ["═" * W, "МЕТАДАННЫЕ"]
        for lbl, v in [("Дата:", datetime.now().strftime("%Y-%m-%d %H:%M")),
                        ("AI провайдеры:", provs), ("Горизонт:", f"{config.SCAN_HORIZON_DAYS} дн."),
                        ("Событий в БД:", n_ev), ("Исходов с данными:", len(rows))]:
            L.append(f"  {str(lbl):22s} {v}")
        L.append("═" * W)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(L) + "\n")
        print(f"✅ Отчёт: {path}")
        print(f"   {len(sigs)} токенов, {longs} LONG, {shorts} SHORT, {neut} NEUTRAL")
    finally:
        db.close()

if __name__ == "__main__":
    main()
