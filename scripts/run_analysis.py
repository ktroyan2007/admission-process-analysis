"""Выполняет все запросы из sql/analysis.sql, пишет результаты в results/query_results.md
и строит графики в results/charts/.  Запуск: python scripts/run_analysis.py"""
import re
import sqlite3
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"
CH = RES / "charts"
CH.mkdir(parents=True, exist_ok=True)

con = sqlite3.connect(ROOT / "data" / "admission.db")
text = (ROOT / "sql" / "analysis.sql").read_text(encoding="utf-8")

# делим файл на запросы по заголовкам вида "-- N. ..."
blocks = re.split(r"\n(?=-- \d+\. )", text)
queries = []
for b in blocks:
    m = re.match(r"-- (\d+)\. (.+)", b)
    if not m:
        continue
    sql = "\n".join(l for l in b.splitlines() if not l.strip().startswith("--")).strip()
    queries.append((int(m.group(1)), m.group(2).strip(), sql))

out = ["# Результаты запросов", "", "Получены скриптом `scripts/run_analysis.py` на данных `data/admission.db`.", ""]
results = {}
for num, title, sql in queries:
    cur = con.execute(sql)
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    results[num] = (cols, rows)
    out += [f"## {num}. {title}", "", "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    shown = rows if num != 10 else rows[:5] + [("…",) * len(cols)] + rows[-3:]
    out += ["| " + " | ".join(str(v) for v in r) + " |" for r in shown]
    out.append("")
(RES / "query_results.md").write_text("\n".join(out), encoding="utf-8")

# ---------- графики ----------
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.alpha": 0.25, "grid.linestyle": "-"})
ACC, MUTED, OK = "#3553d1", "#9aa3b2", "#23814f"

def save(fig, name):
    fig.tight_layout(); fig.savefig(CH / name, dpi=150); plt.close(fig)

# 1) ошибки по каналам
cols, rows = results[2]
fig, ax = plt.subplots(figsize=(6.4, 3.4))
names = [r[0] for r in rows]; vals = [r[3] for r in rows]
bars = ax.barh(names[::-1], vals[::-1], color=[ACC if v == max(vals) else MUTED for v in vals[::-1]])
for b, v in zip(bars, vals[::-1]):
    ax.text(b.get_width() + 0.5, b.get_y() + b.get_height() / 2, f"{v}%", va="center")
ax.set_xlabel("Доля заявлений с ошибками, %"); ax.set_title("Ошибки по каналам подачи", loc="left", fontweight="bold")
ax.grid(axis="y", visible=False); ax.set_xlim(0, max(vals) * 1.2)
save(fig, "errors_by_channel.png")

# 2) типы ошибок
cols, rows = results[3]
fig, ax = plt.subplots(figsize=(7.2, 3.8))
labels = [r[0] for r in rows][::-1]; vals = [r[1] for r in rows][::-1]; prev = [r[3] for r in rows][::-1]
bars = ax.barh(labels, vals, color=[ACC if p == "да" else MUTED for p in prev])
for b, v in zip(bars, vals):
    ax.text(b.get_width() + 0.6, b.get_y() + b.get_height() / 2, str(v), va="center")
from matplotlib.patches import Patch
ax.set_xlabel("Количество ошибок"); ax.set_title("Типы ошибок", loc="left", fontweight="bold")
ax.legend(handles=[Patch(color=ACC, label="ловится автопроверкой"), Patch(color=MUTED, label="не ловится")],
          loc="lower right", frameon=False)
ax.grid(axis="y", visible=False); ax.set_xlim(0, max(vals) * 1.18)
save(fig, "error_types.png")

# 3) нагрузка по дням и время обработки
cur = con.execute("""SELECT substr(submitted_at,1,10) d, COUNT(*),
  AVG((julianday(processed_at)-julianday(submitted_at))*24) FROM applications GROUP BY d ORDER BY d""")
rows = cur.fetchall()
fig, ax = plt.subplots(figsize=(8, 3.6))
x = range(len(rows))
ax.bar(x, [r[1] for r in rows], color=MUTED, label="Заявлений за день")
ax2 = ax.twinx()
ax2.plot(x, [r[2] for r in rows], color=ACC, lw=2, label="Среднее время обработки, ч")
ax2.spines["top"].set_visible(False); ax2.grid(False)
ax.set_xticks(list(x)[::5]); ax.set_xticklabels([rows[i][0][5:] for i in list(x)[::5]])
ax.set_ylabel("Заявлений"); ax2.set_ylabel("Часов")
ax.set_title("Нагрузка растёт к дедлайну, вместе с ней — время обработки", loc="left", fontweight="bold")
h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
ax.legend(h1 + h2, l1 + l2, loc="upper left", frameon=False)
save(fig, "load_by_day.png")

# 4) эффект to-be
cols, rows = results[11]
now, after = rows[0][3], rows[0][4]
fig, ax = plt.subplots(figsize=(5.2, 3.2))
bars = ax.bar(["Сейчас (as-is)", "С автопроверкой (to-be)"], [now, after], color=[MUTED, OK], width=0.55)
for b, v in zip(bars, [now, after]):
    ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.2, f"{v}%", ha="center", fontweight="bold")
ax.set_ylabel("Доля заявлений с ошибками, %"); ax.set_ylim(0, now * 1.3)
ax.set_title("Оценка эффекта изменений", loc="left", fontweight="bold"); ax.grid(axis="x", visible=False)
save(fig, "to_be_effect.png")

print("ok:", len(queries), "queries")
for n in (1, 2, 4, 5, 7, 9, 11):
    print(n, results[n][0], results[n][1])
