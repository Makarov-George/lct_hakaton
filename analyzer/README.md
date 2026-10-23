# Analyzer

Фоновый сервис системы мониторинга стройплощадок.
По расписанию обходит активные участки, собирает детекции техники за окно,
сверяет с активными этапами плана и правилами, ведёт отклонения.

## Что делает

1. Берёт активные участки (`site.closed_at IS NULL`).
2. Для каждого участка:
   - загружает активные этапы (`active_plan_tasks`);
   - собирает детекции техники за окно (`frame ⋈ detection_report ⋈ detection`);
   - агрегирует: для каждого класса — максимум одновременного присутствия;
   - проверяет правила (`required` / `unexpected`);
   - проверяет молчащие камеры (`no_data`);
   - учитывает grace-периоды на перегонку техники;
   - upsert/close отклонений.
3. Пишет результат в `deviation` (журнал — триггер `deviation_on_change`).

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `CM_DATABASE_URL` | `postgresql://cm_admin:admin_password@localhost:54321/construction_monitoring` | DSN БД |
| `CM_LOG_LEVEL` | `INFO` | Уровень логирования |
| `CM_ANALYZER__INTERVAL_SECONDS` | `3600` | Период обхода участков |
| `CM_ANALYZER__ANALYSIS_WINDOW_MINUTES` | `60` | Окно сбора детекций |
| `CM_ANALYZER__MIN_CONFIDENCE` | `0.5` | Порог уверенности детектора |
| `CM_ANALYZER__MIN_HITS` | `2` | Минимум срабатываний до warning |
| `CM_ANALYZER__GRACE__ARRIVAL_MINUTES` | `60` | Поблажка на въезд техники |
| `CM_ANALYZER__GRACE__DEPARTURE_MINUTES` | `60` | Поблажка на выезд техники |

## Запуск

```bash
docker compose up -d --build
```

## Тесты

```bash
pip install -e ".[dev]"
pytest
```