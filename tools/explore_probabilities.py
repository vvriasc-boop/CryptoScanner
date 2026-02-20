"""Тест оценки вероятностей: события с исходами → 3x Groq → медиана → save."""

import asyncio, logging, os, sqlite3, sys, time, traceback  # noqa: E401
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import aiosqlite  # noqa: E402
from config import DB_PATH
from database.db import (ensure_probability_columns, get_events_with_outcomes,
                         get_outcomes_for_event, update_outcome_probability)
from services.probability_estimator import estimate_event_probabilities

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
SEP = "=" * 50


async def main():
    print(f"\n{SEP}\nPROBABILITY ESTIMATION (Step 3)\nDB: {os.path.abspath(str(DB_PATH))}\n{SEP}")
    t0 = time.time()

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await ensure_probability_columns(db)

        events = await get_events_with_outcomes(db, limit=10)
        if not events:
            print("\nNo events with outcomes missing probabilities")
            return

        print(f"\nEvents without probabilities: {len(events)}\n")
        st = {"ok": 0, "err": 0, "groq": 0, "deltas": []}

        for i, event in enumerate(events, 1):
            eid = event["id"]
            coin = event["coin_symbol"]
            etype = event["event_type"]
            imp = event.get("importance", "?")
            print(f"[{i}/{len(events)}] {coin} | {etype} | {imp}")

            try:
                rows = await get_outcomes_for_event(db, eid)
                if not rows:
                    print("  No outcomes, skip\n"); continue
                outcomes = [dict(r) for r in rows]
                st["groq"] += 3

                result = await estimate_event_probabilities(event, outcomes)
                if not result:
                    print("  Failed to estimate\n"); st["err"] += 1; continue

                prob_sum = 0.0
                deltas = []
                for o in outcomes:
                    key = o["outcome_key"]
                    r = result.get(key)
                    if not r:
                        continue
                    p, lo, hi = r["probability"], r["low"], r["high"]
                    delta = (hi - lo) / 2
                    deltas.append(delta)
                    prob_sum += p
                    text = o["outcome_text"][:45]
                    print(f"    {key}) P={p:.2f} [{lo:.2f} - {hi:.2f}] "
                          f"+/-{delta:.2f}  {text}")
                    await update_outcome_probability(db, eid, key, p, lo, hi)

                delta_avg = sum(deltas) / len(deltas) if deltas else 0
                st["deltas"].append(delta_avg)
                if delta_avg < 0.03: conf = "high"
                elif delta_avg < 0.08: conf = "medium"
                else: conf = "low"
                check = "ok" if abs(prob_sum - 1.0) < 0.02 else f"sum={prob_sum:.2f}"
                print(f"    Sum={prob_sum:.2f} {check}  D_avg={delta_avg:.3f} "
                      f"(confidence: {conf})")
                print(f"  Saved\n")
                st["ok"] += 1

            except Exception as e:
                print(f"  Error: {e}\n")
                traceback.print_exc()
                st["err"] += 1

        elapsed = time.time() - t0
        avg_d = sum(st["deltas"]) / len(st["deltas"]) if st["deltas"] else 0
        print(f"{SEP}\nRESULTS")
        for label, val in [("Events:", len(events)), ("Estimated:", st["ok"]),
                           ("Errors:", st["err"]),
                           ("Groq calls:", f"{st['groq']} (3 x {st['ok']+st['err']})"),
                           ("Avg delta:", f"{avg_d:.3f}"),
                           ("Time:", f"{elapsed:.0f} sec")]:
            print(f"  {label:20s} {val}")
        print(SEP)


if __name__ == "__main__":
    asyncio.run(main())
