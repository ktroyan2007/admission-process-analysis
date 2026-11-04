-- Анализ процесса приёма заявлений (SQLite).
-- База: data/admission.db. Запуск всех запросов: python scripts/run_analysis.py

-- 1. Общая картина: сколько заявлений, сколько с ошибками, какая доля
SELECT
  COUNT(*)                                             AS applications,
  SUM(has_error)                                       AS with_errors,
  ROUND(100.0 * SUM(has_error) / COUNT(*), 1)          AS error_rate_pct
FROM (
  SELECT a.id,
         CASE WHEN EXISTS (SELECT 1 FROM errors e WHERE e.application_id = a.id) THEN 1 ELSE 0 END AS has_error
  FROM applications a
);

-- 2. Доля заявлений с ошибками по каналам подачи
-- COUNT(DISTINCT a.id), а не COUNT(*): после LEFT JOIN заявление с двумя ошибками даёт две строки
SELECT
  a.channel,
  COUNT(DISTINCT a.id)                                           AS applications,
  COUNT(DISTINCT e.application_id)                               AS with_errors,
  ROUND(100.0 * COUNT(DISTINCT e.application_id) / COUNT(DISTINCT a.id), 1) AS error_rate_pct
FROM applications a
LEFT JOIN errors e ON e.application_id = a.id
GROUP BY a.channel
ORDER BY error_rate_pct DESC;

-- 3. Самые частые типы ошибок и можно ли их поймать автопроверкой
SELECT
  e.error_type,
  COUNT(*)                                         AS errors,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS share_pct,
  CASE t.preventable WHEN 1 THEN 'да' ELSE 'нет' END AS auto_check
FROM errors e
JOIN error_types t ON t.name = e.error_type
GROUP BY e.error_type, t.preventable
ORDER BY errors DESC;

-- 4. Сколько времени занимает обработка заявления с ошибкой и без (в часах)
SELECT
  CASE WHEN e.application_id IS NULL THEN 'без ошибок' ELSE 'с ошибками' END AS group_name,
  COUNT(*)                                                                    AS applications,
  ROUND(AVG((julianday(a.processed_at) - julianday(a.submitted_at)) * 24), 1) AS avg_hours
FROM applications a
LEFT JOIN (SELECT DISTINCT application_id FROM errors) e ON e.application_id = a.id
GROUP BY group_name;

-- 5. Сколько ждёт абитуриент, пока исправят ошибку: от обнаружения до исправления (в часах)
SELECT
  ROUND(AVG((julianday(fixed_at) - julianday(found_at)) * 24), 1) AS avg_fix_hours,
  ROUND(MAX((julianday(fixed_at) - julianday(found_at)) * 24), 1) AS max_fix_hours
FROM errors;

-- 6. Нагрузка по дням: топ-5 самых загруженных дней и время обработки в эти дни
SELECT
  substr(submitted_at, 1, 10)                                                 AS day,
  COUNT(*)                                                                    AS applications,
  ROUND(AVG((julianday(processed_at) - julianday(submitted_at)) * 24), 1)     AS avg_hours
FROM applications
GROUP BY day
ORDER BY applications DESC
LIMIT 5;

-- 7. Сравнение пиковой недели (последние 5 дней приёма) с остальным периодом
SELECT
  CASE WHEN submitted_at >= '2025-07-21' THEN 'последние 5 дней' ELSE 'остальной период' END AS period,
  COUNT(*)                                                                    AS applications,
  ROUND(1.0 * COUNT(*) / COUNT(DISTINCT substr(submitted_at, 1, 10)), 1)      AS per_day,
  ROUND(AVG((julianday(processed_at) - julianday(submitted_at)) * 24), 1)     AS avg_hours
FROM applications
GROUP BY period;

-- 8. Нагрузка на операторов: число заявлений, найденных ошибок и рейтинг по скорости
--    Ошибки сначала считаются по каждому заявлению, чтобы JOIN не размножал строки
WITH per_app AS (
  SELECT a.id, a.operator_id,
         (julianday(a.processed_at) - julianday(a.submitted_at)) * 24 AS hours,
         (SELECT COUNT(*) FROM errors e WHERE e.application_id = a.id) AS n_errors
  FROM applications a
)
SELECT
  o.name                               AS operator,
  COUNT(*)                             AS applications,
  SUM(p.n_errors)                      AS errors_found,
  ROUND(AVG(p.hours), 1)               AS avg_hours,
  RANK() OVER (ORDER BY AVG(p.hours))  AS speed_rank
FROM operators o
JOIN per_app p ON p.operator_id = o.id
GROUP BY o.id, o.name
ORDER BY speed_rank;

-- 9. Дубли заявлений: сколько абитуриентов подали заявление повторно
SELECT
  COUNT(*)                                                  AS duplicates,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM applications), 1) AS duplicate_pct
FROM applications
WHERE is_duplicate = 1;

-- 10. Накопительный итог подачи по дням (для графика динамики)
SELECT
  day,
  applications,
  SUM(applications) OVER (ORDER BY day) AS cumulative
FROM (
  SELECT substr(submitted_at, 1, 10) AS day, COUNT(*) AS applications
  FROM applications
  GROUP BY day
)
ORDER BY day;

-- 11. Оценка эффекта to-be: доля заявлений с ошибками, если автопроверка отсечёт предотвратимые ошибки.
--     Заявление остаётся «с ошибкой», только если в нём есть хотя бы одна непредотвратимая ошибка.
WITH per_app AS (
  SELECT e.application_id,
         MAX(CASE WHEN t.preventable = 0 THEN 1 ELSE 0 END) AS has_unpreventable
  FROM errors e
  JOIN error_types t ON t.name = e.error_type
  GROUP BY e.application_id
)
SELECT
  (SELECT COUNT(*) FROM applications)                                                AS applications,
  COUNT(*)                                                                           AS with_errors_now,
  SUM(has_unpreventable)                                                             AS with_errors_after,
  ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM applications), 1)                   AS rate_now_pct,
  ROUND(100.0 * SUM(has_unpreventable) / (SELECT COUNT(*) FROM applications), 1)     AS rate_after_pct,
  ROUND(100.0 * (COUNT(*) - SUM(has_unpreventable)) / COUNT(*), 1)                   AS reduction_pct
FROM per_app;
