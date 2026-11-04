"""Генерация учебных (синтетических) данных приёмной кампании.

Реальных персональных данных абитуриентов в проекте нет: все записи созданы этим скриптом.
Запуск:  python scripts/generate_data.py   → data/admission.db и CSV-файлы в data/
"""
import csv
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

SEED = 2025
rnd = random.Random(SEED)
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)

START = datetime(2025, 6, 20)        # начало приёма документов
DEADLINE = datetime(2025, 7, 25)     # последний день приёма
N_APPS = 1500

PROGRAMS = [
    (1, "Бизнес-информатика", 120), (2, "Системный анализ и управление", 90),
    (3, "Прикладная математика", 100), (4, "Информационная безопасность", 80),
    (5, "Экономика", 110), (6, "Программная инженерия", 100),
]
OPERATORS = [(i, f"Оператор {i}") for i in range(1, 9)]  # команда из 8 человек

CHANNELS = ["Госуслуги", "Личный кабинет", "Лично"]
CHANNEL_W = [55, 30, 15]
# вероятность ошибки зависит от канала: при личной подаче данные вводятся вручную
ERR_P = {"Госуслуги": 0.05, "Личный кабинет": 0.12, "Лично": 0.27}

# типы ошибок: (название, предотвращается автопроверкой?, веса по каналам)
ERROR_TYPES = [
    ("Неверный формат СНИЛС или паспорта", True,  {"Госуслуги": 1, "Личный кабинет": 4, "Лично": 7}),
    ("Нет согласия на зачисление",          True,  {"Госуслуги": 3, "Личный кабинет": 4, "Лично": 3}),
    ("Не приложен документ об образовании", True,  {"Госуслуги": 2, "Личный кабинет": 3, "Лично": 1}),
    ("Баллы ЕГЭ не совпадают с ФИС",        True,  {"Госуслуги": 1, "Личный кабинет": 2, "Лично": 4}),
    ("Опечатка в ФИО или дате рождения",    False, {"Госуслуги": 1, "Личный кабинет": 2, "Лично": 4}),
    ("Неверно указан приоритет программ",   False, {"Госуслуги": 2, "Личный кабинет": 2, "Лично": 2}),
]


def day_weight(d: datetime) -> float:
    """Подача растёт к дедлайну: последние 5 дней — пик."""
    days_left = (DEADLINE - d).days
    if days_left <= 2:
        return 4.0
    if days_left <= 5:
        return 2.6
    if (d - START).days <= 2:
        return 1.8           # всплеск в первые дни
    return 1.0


days = [START + timedelta(days=i) for i in range((DEADLINE - START).days + 1)]
weights = [day_weight(d) for d in days]

applications, errors = [], []
applicant_id = 1000
err_id = 1
load_by_day = {}

# сначала распределяем подачу по дням, чтобы знать нагрузку
submissions = []
for app_id in range(1, N_APPS + 1):
    day = rnd.choices(days, weights)[0]
    ts = day + timedelta(hours=rnd.randint(8, 22), minutes=rnd.randint(0, 59))
    submissions.append((app_id, ts))
    load_by_day[day.date()] = load_by_day.get(day.date(), 0) + 1
peak = max(load_by_day.values())

for app_id, submitted in sorted(submissions, key=lambda x: x[1]):
    channel = rnd.choices(CHANNELS, CHANNEL_W)[0]
    applicant_id += 1 if rnd.random() > 0.04 else 0     # ~4% — дубли от того же абитуриента
    is_duplicate = 1 if applications and applications[-1][1] == applicant_id else 0
    program = rnd.choice(PROGRAMS)[0]
    operator = rnd.choice(OPERATORS)[0]
    # время обработки: базовое + рост при пиковой нагрузке
    load = load_by_day[submitted.date()] / peak
    base_hours = rnd.uniform(3, 10) + 30 * load ** 2
    n_err = 0
    if rnd.random() < ERR_P[channel]:
        n_err = 1 if rnd.random() < 0.8 else 2
    app_errors = []
    found = submitted + timedelta(hours=base_hours * rnd.uniform(0.4, 0.8))
    chosen = set()
    while len(chosen) < n_err:
        names = [e[0] for e in ERROR_TYPES]
        ws = [e[2][channel] for e in ERROR_TYPES]
        chosen.add(rnd.choices(names, ws)[0])
    extra = 0.0
    for etype in chosen:
        fix_delay = rnd.uniform(12, 72)           # абитуриента нужно найти и дождаться исправления
        fixed = found + timedelta(hours=fix_delay)
        app_errors.append((err_id, app_id, etype, found.strftime("%Y-%m-%d %H:%M"), fixed.strftime("%Y-%m-%d %H:%M")))
        err_id += 1
        extra = max(extra, fix_delay + rnd.uniform(1, 6))
    processed = submitted + timedelta(hours=base_hours + extra)
    if is_duplicate:
        status = "отклонено"
    elif rnd.random() < 0.03:
        status = "отозвано"
    else:
        status = "принято"
    applications.append((app_id, applicant_id, program, channel, submitted.strftime("%Y-%m-%d %H:%M"),
                         processed.strftime("%Y-%m-%d %H:%M"), status, operator, is_duplicate))
    errors.extend(app_errors)

SCHEMA = """
CREATE TABLE programs (id INTEGER PRIMARY KEY, name TEXT NOT NULL, budget_places INTEGER);
CREATE TABLE operators (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE applications (
  id INTEGER PRIMARY KEY,
  applicant_id INTEGER NOT NULL,
  program_id INTEGER REFERENCES programs(id),
  channel TEXT NOT NULL,              -- Госуслуги / Личный кабинет / Лично
  submitted_at TEXT NOT NULL,         -- когда подано
  processed_at TEXT NOT NULL,         -- когда обработка завершена
  status TEXT NOT NULL,               -- принято / отклонено / отозвано
  operator_id INTEGER REFERENCES operators(id),
  is_duplicate INTEGER NOT NULL       -- 1, если это повторное заявление того же абитуриента
);
CREATE TABLE errors (
  id INTEGER PRIMARY KEY,
  application_id INTEGER REFERENCES applications(id),
  error_type TEXT NOT NULL,
  found_at TEXT NOT NULL,             -- когда сотрудник нашёл ошибку
  fixed_at TEXT NOT NULL              -- когда абитуриент её исправил
);
CREATE TABLE error_types (name TEXT PRIMARY KEY, preventable INTEGER NOT NULL);  -- 1 = ловится автопроверкой
"""

db_path = DATA / "admission.db"
if db_path.exists():
    db_path.unlink()
con = sqlite3.connect(db_path)
con.executescript(SCHEMA)
con.executemany("INSERT INTO programs VALUES (?,?,?)", PROGRAMS)
con.executemany("INSERT INTO operators VALUES (?,?)", OPERATORS)
con.executemany("INSERT INTO applications VALUES (?,?,?,?,?,?,?,?,?)", applications)
con.executemany("INSERT INTO errors VALUES (?,?,?,?,?)", errors)
con.executemany("INSERT INTO error_types VALUES (?,?)", [(e[0], int(e[1])) for e in ERROR_TYPES])
con.commit()

for table in ["programs", "operators", "applications", "errors", "error_types"]:
    cur = con.execute(f"SELECT * FROM {table}")
    with open(DATA / f"{table}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([c[0] for c in cur.description])
        w.writerows(cur.fetchall())

# SQL-дамп, чтобы базу можно было поднять в любой СУБД или DB Fiddle
with open(DATA / "admission_dump.sql", "w", encoding="utf-8") as f:
    for line in con.iterdump():
        f.write(line + "\n")
con.close()
print(f"applications={len(applications)} errors={len(errors)} -> {db_path}")
