from pathlib import Path
p = Path("dashboard/adapters/sqlite_ro.py")
text = p.read_text(encoding="utf-8")
lines = []
for line in text.splitlines(keepends=True):
    if "sidecars: " in line and "detail +=" in line:
        line = '            detail += f" | sidecars: {\', \'.join(sidecars)}"\n'
    lines.append(line)
p.write_text("".join(lines), encoding="utf-8")
