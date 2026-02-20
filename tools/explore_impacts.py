"""Тест оценки ценового влияния: события → 3x Groq → медиана → save."""

import asyncio, logging, os, sqlite3, sys, time, traceback  # noqa: E401
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import aiosqlite  # noqa: E402
from config import DB_PATH
from database.db import (ensure_impact_columns, get_events_without_impacts,
                         get_outcomes_for_event, update_outcome_impact)
from services.impact_estimator import estimate_event_impacts

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
SEP = "\u2550" * 50


async def main():
    print(f"\n{SEP}\nОЦЕНКА ЦЕНОВОГО ВЛИЯНИЯ (Шаг 4)"
          f"\nБД: {os.path.abspath(str(DB_PATH))}\n{SEP}")
    t0 = time.time()

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await ensure_impact_columns(db)

        events = await get_events_without_impacts(db, limit=10)
        if not events:
            print("\n\u26a0\ufe0f  Нет событий с вероятностями без ценовых оценок")
            return

        print(f"\nСобытий без ценовых оценок: {len(events)}\n")
        st = {"ok": 0, "err": 0, "groq": 0, "previews": []}

        for i, event in enumerate(events, 1):
            eid = event["id"]
            coin, etype = event["coin_symbol"], event["event_type"]
            imp = event.get("importance", "?")
            print(f"[{i}/{len(events)}] {coin} | {etype} | {imp}")

            try:
                rows = await get_outcomes_for_event(db, eid)
                if not rows:
                    print("  No outcomes, skip\n"); continue
                outcomes = [dict(r) for r in rows]
                st["groq"] += 3

                result = await estimate_event_impacts(event, outcomes)
                if not result:
                    print("  \u274c Не удалось оценить\n"); st["err"] += 1; continue

                e_ret = 0.0
                for o in outcomes:
                    key = o["outcome_key"]
                    r = result.get(key)
                    if not r: continue
                    val, lo, hi = r["impact"], r["low"], r["high"]
                    p = o.get("probability") or 0
                    e_ret += p * val
                    text = o["outcome_text"][:40]
                    print(f"  {key}) {text:42s} P={p:.2f}  "
                          f"impact={val:+.1f}% [{lo:+.1f} .. {hi:+.1f}]")
                    await update_outcome_impact(db, eid, key, val, lo, hi)

                print(f"  \U0001f4ca E[return] = {e_ret:+.2f}%")
                print(f"  \U0001f4be Сохранено\n")
                st["previews"].append((coin, etype, e_ret))
                st["ok"] += 1

            except Exception as e:
                print(f"  \u274c Error: {e}\n")
                traceback.print_exc()
                st["err"] += 1

        elapsed = time.time() - t0
        print(f"{SEP}\nИТОГ")
        for label, val in [("Событий:", len(events)), ("Оценено:", st["ok"]),
                           ("Ошибки:", st["err"]),
                           ("Groq вызовов:",
                            f"{st['groq']} (3 \u00d7 {st['ok']+st['err']})"),
                           ("Время:", f"{elapsed:.0f} сек")]:
            print(f"  {label:20s} {val}")

        if st["previews"]:
            print(f"\nPREVIEW Шаг 5 (E[return] по событиям):")
            for coin, etype, er in st["previews"]:
                print(f"  {coin:6s} {etype:12s} E[return] = {er:+.2f}%")
        print(SEP)


if __name__ == "__main__":
    asyncio.run(main())
