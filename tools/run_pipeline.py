"""CryptoScanner — полный пайплайн: 6 шагов от поиска до сигналов."""
import asyncio, logging, os, sqlite3, sys, time, traceback  # noqa: E401
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import aiosqlite, httpx  # noqa: E402
import config
from database.db import (ensure_outcome_tables, ensure_probability_columns,
    ensure_impact_columns, get_unprocessed_events, get_events_with_outcomes,
    get_events_without_impacts, get_outcomes_for_event, save_outcomes,
    update_outcome_probability, update_outcome_impact)
from services.binance_tokens import get_futures_tokens
from services.token_scanner import scan_single_token
from services.outcome_generator import generate_outcomes, validate_outcomes
from services.probability_estimator import estimate_event_probabilities
from services.impact_estimator import estimate_event_impacts
from services.signal_calculator import generate_all_signals

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
TEST_TOKENS = ["ARB", "OP", "PENDLE", "SUI", "ZK"]
SEP = "\u2550" * 50
def _ft(s: float) -> str:
    return f"{int(s)//60}m {int(s)%60}s" if s >= 60 else f"{s:.0f}s"

async def _run_estimate(db, events, est_fn, upd_fn, val_key):
    """Шаги 3/4: estimate → update. Returns groq_calls."""
    groq = 0
    for ev in events:
        try:
            rows = await get_outcomes_for_event(db, ev["id"])
            if not rows: continue
            outs = [dict(r) for r in rows]
            res = await est_fn(ev, outs); groq += 3
            if not res: continue
            for o in outs:
                r = res.get(o["outcome_key"])
                if r:
                    await upd_fn(db, ev["id"], o["outcome_key"],
                                 r[val_key], r["low"], r["high"])
        except Exception as e:
            logging.warning(f"Estimate {ev.get('coin_symbol')}: {e}")
    return groq
async def main():
    full = "--full" in sys.argv
    mode = f"full (50 токенов)" if full else f"test ({len(TEST_TOKENS)} токенов)"
    print(f"\n{SEP}\nCRYPTOSCANNER PIPELINE"
          f"\nРежим: {mode} | Порог: \u00b1{config.SIGNAL_THRESHOLD}%\n{SEP}\n")
    if not config.PARALLEL_API_KEY:
        print("\u274c PARALLEL_API_KEY не задан"); return
    if not config.GROQ_API_KEY:
        print("\u274c GROQ_API_KEY не задан"); return

    t_all, groq_all, n_tok = time.time(), 0, 0
    async with httpx.AsyncClient() as http, \
               aiosqlite.connect(str(config.DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await ensure_outcome_tables(db)
        await ensure_probability_columns(db)
        await ensure_impact_columns(db)

        t1, ev_new = time.time(), 0  # Step 1: scan tokens
        try:
            toks = await get_futures_tokens(http, exclude=config.TOP_EXCLUDE)
            if not toks:
                print("\u274c Не удалось получить список токенов"); return
            toks = toks[:50] if full else [t for t in TEST_TOKENS if t in toks]
            n_tok = len(toks)
            for tok in toks:
                try:
                    ev_new += len(await scan_single_token(tok, db, http))
                except Exception as e:
                    logging.warning(f"Step1 {tok}: {e}")
                await asyncio.sleep(config.GROQ_DELAY)
        except Exception as e:
            print(f"  Шаг 1 ошибка: {e}"); traceback.print_exc()
        print(f"Шаг 1: Сбор событий .............. {n_tok} токенов, "
              f"{ev_new} новых событий    [{_ft(time.time()-t1)}]")

        t2, n_out, n2 = time.time(), 0, 0  # Step 2: generate outcomes
        try:
            evts = await get_unprocessed_events(db, limit=100)
            n2 = len(evts)
            for ev in evts:
                try:
                    outs = await generate_outcomes(ev)
                    if validate_outcomes(outs):
                        await save_outcomes(db, ev["id"], outs); n_out += len(outs)
                except Exception as e:
                    logging.warning(f"Step2 {ev.get('coin_symbol')}: {e}")
        except Exception as e:
            print(f"  Шаг 2 ошибка: {e}"); traceback.print_exc()
        print(f"Шаг 2: Генерация исходов ......... {n2} событий \u2192 "
              f"{n_out} исходов          [{_ft(time.time()-t2)}]")

        t3 = time.time()  # Step 3: estimate probabilities
        try:
            evts3 = await get_events_with_outcomes(db, limit=100)
        except Exception as e:
            evts3 = []; print(f"  Шаг 3 ошибка: {e}")
        g3 = await _run_estimate(db, evts3, estimate_event_probabilities,
                                 update_outcome_probability, "probability")
        groq_all += g3
        print(f"Шаг 3: Оценка вероятностей ....... {len(evts3)} событий, "
              f"{g3} Groq вызовов      [{_ft(time.time()-t3)}]")

        t4 = time.time()  # Step 4: estimate impacts
        try:
            evts4 = await get_events_without_impacts(db, limit=100)
        except Exception as e:
            evts4 = []; print(f"  Шаг 4 ошибка: {e}")
        g4 = await _run_estimate(db, evts4, estimate_event_impacts,
                                 update_outcome_impact, "impact")
        groq_all += g4
        print(f"Шаг 4: Оценка ценового влияния ... {len(evts4)} событий, "
              f"{g4} Groq вызовов      [{_ft(time.time()-t4)}]")

        t5, signals = time.time(), []  # Steps 5-6: signals
        try:
            signals = await generate_all_signals(db, limit=50)
        except Exception as e:
            print(f"  Шаг 5-6 ошибка: {e}")
        print(f"Шаг 5-6: Расчёт сигналов ......... {len(signals)} токенов "
              f"с данными              [{_ft(time.time()-t5)}]")

        print(f"\n{SEP}\nСИГНАЛЫ\n{SEP}\n")
        active = [s for s in signals if s["signal"] != "NEUTRAL"]
        neutral = [s for s in signals if s["signal"] == "NEUTRAL"]
        for s in active:
            ic = "\U0001f7e2 LONG " if s["signal"] == "LONG" else "\U0001f534 SHORT"
            cd = s["avg_confidence_delta"]
            cf = "высокая" if cd < 0.03 else ("средняя" if cd < 0.08 else "низкая")
            cap = " \u26a0\ufe0f capped" if s.get("capped") else ""
            print(f"{ic} {s['token']:6s} E[return] = {s['total_e_return']:+.2f}%{cap}  "
                  f"({s['events_count']} событий, уверенность: {cf})")
        if neutral:
            parts = [f"{s['token']} ({s['total_e_return']:+.2f}%)" for s in neutral]
            print(f"\nБез сигнала (NEUTRAL): {', '.join(parts)}")
        if not signals:
            print("Нет данных для формирования сигналов.")
        longs = sum(1 for s in signals if s["signal"] == "LONG")
        shorts = sum(1 for s in signals if s["signal"] == "SHORT")
        print(f"\n{SEP}\nИТОГО")
        for lbl, v in [("Всего токенов:", n_tok), ("С событиями:", len(signals)),
                        ("\U0001f7e2 LONG:", longs), ("\U0001f534 SHORT:", shorts),
                        ("\u26aa NEUTRAL:", len(neutral)),
                        ("Groq вызовов:", groq_all),
                        ("Время:", _ft(time.time() - t_all))]:
            print(f"  {str(lbl):20s} {v}")
        print(SEP)
if __name__ == "__main__":
    asyncio.run(main())
