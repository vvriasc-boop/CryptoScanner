"""Тест сигналов: E[return] + торговые сигналы по данным из БД."""

import asyncio, logging, os, sqlite3, sys, time  # noqa: E401
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import aiosqlite  # noqa: E402
from config import DB_PATH, SIGNAL_THRESHOLD
from services.signal_calculator import generate_all_signals

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
SEP = "\u2550" * 50


async def main():
    print(f"\n{SEP}\n\u0421\u0418\u0413\u041d\u0410\u041b\u042b (\u0428\u0430\u0433\u0438 5+6)"
          f"\n\u0411\u0414: {os.path.abspath(str(DB_PATH))}"
          f"\n\u041f\u043e\u0440\u043e\u0433: \u00b1{SIGNAL_THRESHOLD}%\n{SEP}")
    t0 = time.time()

    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        await db.execute("PRAGMA journal_mode=WAL")

        signals = await generate_all_signals(db, limit=50)
        if not signals:
            print("\n\u26a0\ufe0f  \u041d\u0435\u0442 \u0434\u0430\u043d\u043d\u044b\u0445 \u0441 \u043f\u043e\u043b\u043d\u044b\u043c\u0438 \u043e\u0446\u0435\u043d\u043a\u0430\u043c\u0438")
            return

        print()
        active = [s for s in signals if s["signal"] != "NEUTRAL"]
        neutral = [s for s in signals if s["signal"] == "NEUTRAL"]
        longs, shorts, abs_rets = 0, 0, []

        for s in active + neutral:
            er = s["total_e_return"]
            bull, bear = s["total_bull"], s["total_bear"]
            cd = s["avg_confidence_delta"]
            abs_rets.append(abs(er))
            conf = "\u0432\u044b\u0441\u043e\u043a\u0430\u044f" if cd < 0.03 else ("\u0441\u0440\u0435\u0434\u043d\u044f\u044f" if cd < 0.08 else "\u043d\u0438\u0437\u043a\u0430\u044f")

            if s["signal"] == "LONG":
                icon = "\U0001f7e2 LONG  "; longs += 1
            elif s["signal"] == "SHORT":
                icon = "\U0001f534 SHORT "; shorts += 1
            else:
                icon = "\u26aa NEUTRAL"

            cap_mark = "  \u26a0\ufe0f capped" if s.get("capped") else ""
            print(f"{icon} {s['token']:6s} E[return] = {er:+.2f}%  "
                  f"[bear: {bear:+.2f}% .. bull: {bull:+.2f}%]  "
                  f"\u0394={cd:.2f} ({conf}){cap_mark}")
            details = "  |  ".join(
                f"{e['type']}: E={e['e_return']:+.2f}%" for e in s["events"])
            print(f"  \u2192 {details}\n")

        elapsed = time.time() - t0
        avg_abs = sum(abs_rets) / len(abs_rets) if abs_rets else 0
        long_names = ", ".join(s["token"] for s in signals if s["signal"] == "LONG")
        short_names = ", ".join(s["token"] for s in signals if s["signal"] == "SHORT")

        print(f"{SEP}\n\u0418\u0422\u041e\u0413")
        for label, val in [
            ("\u0422\u043e\u043a\u0435\u043d\u043e\u0432 \u0441 \u0434\u0430\u043d\u043d\u044b\u043c\u0438:", len(signals)),
            ("\U0001f7e2 LONG \u0441\u0438\u0433\u043d\u0430\u043b\u044b:", f"{longs} ({long_names})" if longs else "0"),
            ("\U0001f534 SHORT \u0441\u0438\u0433\u043d\u0430\u043b\u044b:", f"{shorts} ({short_names})" if shorts else "0"),
            ("\u26aa NEUTRAL:", len(signals) - longs - shorts),
            ("\u0421\u0440\u0435\u0434\u043d\u0438\u0439 |E[return]|:", f"{avg_abs:.2f}%"),
            ("\u0412\u0440\u0435\u043c\u044f:", f"{elapsed:.1f} \u0441\u0435\u043a"),
        ]:
            print(f"  {str(label):25s} {val}")

        trade = [s for s in signals if s["signal"] != "NEUTRAL"]
        if trade:
            print(f"\n\u0421\u0418\u0413\u041d\u0410\u041b\u042b \u0414\u041b\u042f \u0422\u041e\u0420\u0413\u041e\u0412\u041b\u0418:")
            for s in trade:
                ic = "\U0001f7e2 LONG " if s["signal"] == "LONG" else "\U0001f534 SHORT"
                cd = s["avg_confidence_delta"]
                cf = "\u0432\u044b\u0441\u043e\u043a\u0430\u044f" if cd < 0.03 else ("\u0441\u0440\u0435\u0434\u043d\u044f\u044f" if cd < 0.08 else "\u043d\u0438\u0437\u043a\u0430\u044f")
                print(f"  {ic} {s['token']:6s} {s['total_e_return']:+.2f}%  "
                      f"({s['events_count']} \u0441\u043e\u0431\u044b\u0442\u0438\u0439, \u0443\u0432\u0435\u0440\u0435\u043d\u043d\u043e\u0441\u0442\u044c: {cf})")
        print(SEP)


if __name__ == "__main__":
    asyncio.run(main())
