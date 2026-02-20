"""Тест сканера токенов: Parallel Search → Groq AI → events_v2."""

import asyncio, logging, os, sqlite3, sys, time  # noqa: E401
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import aiosqlite, httpx  # noqa: E401
import config
from database.db import ensure_outcome_tables
from services.binance_tokens import get_futures_tokens
from services.groq_client import GroqAPIError
from services.parallel_client import search_token_events
from services.token_scanner import _process_results

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
TEST_TOKENS = ["ARB", "OP", "PENDLE", "SUI", "ZK"]
SEP = "=" * 50


async def main():
    run_all = "--all" in sys.argv
    print(f"\n{SEP}\nTEST SCANNER TOKENS\nDB: {os.path.abspath(str(config.DB_PATH))}\n{SEP}")
    if not config.PARALLEL_API_KEY:
        print("\nPARALLEL_API_KEY not set in .env"); return
    t0 = time.time()
    async with httpx.AsyncClient() as http, \
               aiosqlite.connect(str(config.DB_PATH)) as db:
        db.row_factory = sqlite3.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await ensure_outcome_tables(db)
        tokens = await get_futures_tokens(http, exclude=config.TOP_EXCLUDE)
        if not tokens:
            print("\nFailed to get token list"); return
        print(f"\nTokens: {len(tokens)} (excluded: {', '.join(sorted(config.TOP_EXCLUDE))})")
        if run_all:
            scan_list = tokens
            print(f"Mode: full ({len(tokens)} tokens)\n")
        else:
            ts = set(tokens)
            scan_list = [t for t in TEST_TOKENS if t in ts]
            if len(scan_list) < 3: scan_list = tokens[:5]
            print(f"Mode: test ({len(scan_list)} tokens)\n")
        st = {"res": 0, "groq": 0, "found": 0, "new": 0, "dup": 0, "err": 0}
        seen: set[str] = set()
        for i, token in enumerate(scan_list, 1):
            print(f"[{i}/{len(scan_list)}] {token}")
            try:
                results = await search_token_events(
                    http, token, config.PARALLEL_API_KEY,
                    config.PARALLEL_MAX_RESULTS, config.PARALLEL_MAX_CHARS)
                print(f"  Parallel: {len(results)} results")
                if not results:
                    print("  -> skip\n"); await asyncio.sleep(config.PARALLEL_DELAY); continue
                st["res"] += 1; st["groq"] += 1
                events = await _process_results(token, results, db)
                print(f"  Groq: {len(events)} events")
                for j, ev in enumerate(events, 1):
                    t_ = ev.get("title", "")[:40]
                    print(f"    {j}. {t_} | {ev.get('event_type','?')} | "
                          f"{ev.get('date_event','?')} | {ev.get('importance','?')}")
                st["found"] += len(events)
                for ev in events:
                    k = f"{ev.get('coin_symbol','')}-{ev.get('event_type','')}-{ev.get('title','')}"
                    if k in seen: st["dup"] += 1
                    else: seen.add(k); st["new"] += 1
                if events: print(f"  Saved: {len(events)} new")
            except GroqAPIError as e:
                print(f"  Groq error: {e}"); st["err"] += 1
            except Exception as e:
                print(f"  Error: {e}"); st["err"] += 1
            print()
            await asyncio.sleep(config.PARALLEL_DELAY)
        cur = await db.execute("SELECT COUNT(*) as cnt FROM events_v2")
        row = await cur.fetchone()
        db_cnt = row["cnt"] if row else 0
        elapsed = time.time() - t0
        print(f"{SEP}\nRESULTS")
        for label, val in [("Tokens:", len(scan_list)), ("With results:", st["res"]),
                           ("Groq calls:", st["groq"]), ("Events found:", st["found"]),
                           ("New in DB:", st["new"]), ("Duplicates:", st["dup"]),
                           ("Errors:", st["err"]), ("DB events_v2:", f"{db_cnt} (total)"),
                           ("Time:", f"{elapsed:.0f} sec")]:
            print(f"  {label:20s} {val}")
        print(SEP)


if __name__ == "__main__":
    asyncio.run(main())
