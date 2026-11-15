import sqlite3
from pathlib import Path

p = Path("data/raw/pireps.db").resolve()
c = sqlite3.connect("file:" + p.as_posix() + "?mode=ro", uri=True)
c.row_factory = sqlite3.Row
print("TRAINABLE COLS", [r["name"] for r in c.execute("PRAGMA table_info(trainable)")])
print("TRAINABLE SQL", c.execute("SELECT sql FROM sqlite_master WHERE name='trainable'").fetchone()["sql"])
print("REPORTS COLS", [r["name"] for r in c.execute("PRAGMA table_info(reports)")])
print("RUNS COLS", [r["name"] for r in c.execute("PRAGMA table_info(runs)")])
r = c.execute("SELECT * FROM trainable LIMIT 1").fetchone()
print("SAMPLE", dict(r) if r else None)
c.close()
