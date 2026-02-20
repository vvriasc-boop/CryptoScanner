"""Очистка БД от тестовых и мусорных данных. Запуск: python3 tools/cleanup_db.py"""
import os, sqlite3, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config

JUNK = ["price prediction", "forecast", "2027", "2028", "2029", "2030",
        "top 10", "best crypto", "what is", "guide to",
        "charts and quotes", "live price chart", "historical price",
        "candlestick chart", "price today"]

def main():
    db = sqlite3.connect(str(config.DB_PATH)); db.row_factory = sqlite3.Row
    excl = tuple(config.TOP_EXCLUDE)
    # 1. TOP_EXCLUDE events
    for tbl in ["events_v2", "events"]:
        ids = [r[0] for r in db.execute(
            f"SELECT id FROM {tbl} WHERE coin_symbol IN ({','.join('?'*len(excl))})", excl)]
        if not ids:
            print(f"  {tbl}: 0 событий TOP_EXCLUDE"); continue
        ph = ",".join("?" * len(ids))
        oc_tbl = "event_outcomes" if tbl == "events_v2" else None
        if oc_tbl:
            db.execute(f"DELETE FROM {oc_tbl} WHERE event_id IN ({ph})", ids)
        db.execute(f"DELETE FROM {tbl} WHERE id IN ({ph})", ids)
        db.commit()
        print(f"  {tbl}: удалено {len(ids)} событий TOP_EXCLUDE")

    # 2. Junk events (interactive)
    cands = []
    for tbl in ["events_v2", "events"]:
        col = "title" if tbl == "events_v2" else "caption"
        for r in db.execute(f"SELECT id, coin_symbol, {col} AS t FROM {tbl}"):
            low = (r["t"] or "").lower()
            if any(j in low for j in JUNK):
                cands.append((tbl, r["id"], r["coin_symbol"], r["t"]))
    if cands:
        print(f"\nКандидаты на удаление ({len(cands)}):")
        for i, (tbl, eid, sym, t) in enumerate(cands, 1):
            print(f"  {i}. [{tbl}] {sym} — {t[:80]}")
        if input("Удалить? [y/N]: ").strip().lower() == "y":
            for tbl, eid, _, _ in cands:
                if tbl == "events_v2":
                    db.execute("DELETE FROM event_outcomes WHERE event_id=?", (eid,))
                db.execute(f"DELETE FROM {tbl} WHERE id=?", (eid,))
            db.commit()
            print(f"Удалено {len(cands)} мусорных событий")
    else:
        print("\nМусорных событий не найдено")

    # 3. Summary
    ev2 = db.execute("SELECT COUNT(*) FROM events_v2").fetchone()[0]
    eo = db.execute("SELECT COUNT(*) FROM event_outcomes").fetchone()[0]
    ev1 = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    print(f"\nВ БД осталось: events_v2={ev2}, event_outcomes={eo}, events={ev1}")
    db.close()

if __name__ == "__main__":
    main()
