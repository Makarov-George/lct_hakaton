# База данных

## Таблицы

### `site_type`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `name` | text | UK | Название типа участка |

### `work_type`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `code` | text | UK, nullable | Иерархический код вида работ |
| `parent_id` | uuid | FK → `work_type` | Родительский узел |
| `name` | text | | Название вида работ |
| `level` | integer | | Глубина узла в дереве |
| `observable` | boolean | | Контролируется по снимкам |

### `work_type_applicability`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `work_type_id` | uuid | PK, FK → `work_type` | Вид работ |
| `site_type_id` | uuid | PK, FK → `site_type` | Тип участка |

### `equipment_class`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `code` | text | UK | Код класса техники |
| `name` | text | UK | Название класса техники |

### `site`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `name` | text | | Название участка |
| `address` | text | | Адрес участка |
| `site_type_id` | uuid | FK → `site_type` | Тип участка |
| `closed_at` | timestamptz | | Дата закрытия |
| `created_at` | timestamptz | | Дата создания |
| `updated_at` | timestamptz | | Дата обновления |

### `camera`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `site_id` | uuid | FK → `site` | Участок |
| `name` | text | | Название камеры |
| `no_data_after_min` | integer | | Порог отсутствия данных, мин |
| `closed_at` | timestamptz | | Дата закрытия |
| `created_at` | timestamptz | | Дата создания |
| `updated_at` | timestamptz | | Дата обновления |

- UK (`site_id`, `name`), UK (`id`, `site_id`)

### `plan_task`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `site_id` | uuid | FK → `site` | Участок |
| `work_type_id` | uuid | FK → `work_type` | Вид работ |
| `start_date` | date | | Дата начала этапа |
| `end_date` | date | | Дата окончания этапа |
| `closed_at` | timestamptz | | Дата закрытия |
| `created_at` | timestamptz | | Дата создания |
| `updated_at` | timestamptz | | Дата обновления |

- UK (`site_id`, `work_type_id`, `start_date`) среди незакрытых, UK (`id`, `site_id`)

### `rule`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `work_type_id` | uuid | FK → `work_type` | Вид работ |
| `equipment_class_id` | uuid | FK → `equipment_class` | Класс техники |
| `kind` | text (`required` \| `allowed` \| `unexpected`) | | Тип правила |
| `min_count` | integer | | Минимальное количество техники |
| `severity` | text (`info` \| `warning` \| `critical`) | | Уровень серьёзности |
| `inherit` | boolean | | Наследуется дочерними видами работ |
| `closed_at` | timestamptz | | Дата закрытия |
| `created_at` | timestamptz | | Дата создания |
| `updated_at` | timestamptz | | Дата обновления |

- UK (`work_type_id`, `equipment_class_id`) среди незакрытых

### `frame`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `site_id` | uuid | FK → `site` | Участок |
| `camera_id` | uuid | FK → `camera` (вместе с `site_id`) | Камера |
| `storage_key` | text | UK | Ключ объекта в MinIO |
| `content_type` | text (`image/jpeg` \| `image/png`) | | MIME-тип снимка |
| `captured_at` | timestamptz | | Время съёмки |
| `received_at` | timestamptz | | Время получения |

- Индексы: (`site_id`, `captured_at`), (`camera_id`, `received_at`)

### `detection_report`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `frame_id` | uuid | FK → `frame`, UK | Снимок |
| `status` | text (`ok` \| `failed`) | | Результат обработки |
| `error_message` | text | | Текст ошибки |
| `created_at` | timestamptz | | Дата создания |

### `detection`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `report_id` | uuid | FK → `detection_report` | Отчёт |
| `equipment_class_code` | text | | Код класса найденного объекта |
| `confidence` | numeric(3,2) | | Уверенность модели |
| `x_min`, `y_min`, `x_max`, `y_max` | integer | | Координаты рамки объекта, px |

### `deviation`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `site_id` | uuid | FK → `site` | Участок |
| `type` | text (`missing_required` \| `unexpected_equipment` \| `unplanned_activity` \| `not_observable` \| `no_data`) | | Тип отклонения |
| `plan_task_id` | uuid | FK → `plan_task` (вместе с `site_id`) | Этап |
| `work_type_id` | uuid | FK → `work_type` | Вид работ |
| `rule_id` | uuid | FK → `rule` | Правило |
| `equipment_class_id` | uuid | FK → `equipment_class` | Класс техники |
| `camera_id` | uuid | FK → `camera` (вместе с `site_id`) | Камера |
| `severity` | text (`info` \| `warning` \| `critical`) | | Уровень серьёзности |
| `status` | text (`open` \| `acknowledged` \| `resolved` \| `false_positive`) | | Статус отклонения |
| `message` | text | | Текст сообщения |
| `hits` | integer | | Количество срабатываний |
| `first_seen_at` | timestamptz | | Время первого обнаружения |
| `last_seen_at` | timestamptz | | Время последнего обнаружения |
| `acknowledged_at` | timestamptz | | Время подтверждения |
| `closed_at` | timestamptz | | Время закрытия |
| `closed_by` | text (`user` \| `system`) | | Кто закрыл |
| `close_reason` | text (`condition_cleared` \| `stage_finished` \| `plan_changed` \| `rule_disabled` \| `camera_disabled` \| `user_resolved` \| `user_false_positive`) | | Причина закрытия |
| `comment` | text | | Комментарий |
| `created_at` | timestamptz | | Дата создания |
| `updated_at` | timestamptz | | Дата обновления |

- UK `NULLS NOT DISTINCT` (`site_id`, `type`, `plan_task_id`, `rule_id`, `equipment_class_id`, `camera_id`) при `status IN (open, acknowledged)`

### `deviation_evidence`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `deviation_id` | uuid | PK, FK → `deviation` | Отклонение |
| `frame_id` | uuid | PK, FK → `frame` | Снимок |
| `role` | text (`violation` \| `resolution`) | | Роль снимка |
| `added_at` | timestamptz | | Время добавления |

### `deviation_history`

| Поле | Тип | Ключ | Описание |
|---|---|---|---|
| `id` | uuid | PK | Идентификатор |
| `deviation_id` | uuid | FK → `deviation` | Отклонение |
| `change` | text (`opened` \| `updated` \| `acknowledged` \| `resolved` \| `false_positive`) | | Тип события |
| `status` | text | | Статус после изменения |
| `severity` | text | | Серьёзность после изменения |
| `hits` | integer | | Счётчик после изменения |
| `actor` | text | | Кто внёс изменение |
| `comment` | text | | Комментарий |
| `created_at` | timestamptz | | Дата создания |

## Функции

| Функция | Результат |
|---|---|
| `effective_rules(work_type_id)` | `rule_id`, `source_work_type_id`, `distance`, `equipment_class_id`, `kind`, `min_count`, `severity` |
| `active_plan_tasks(site_id, date)` | Незакрытые этапы участка, активные на дату |
| `stage_status(plan_task_id, as_of)` | `planned` \| `completed` \| `not_observable` \| `violation` \| `ok` |
| `site_status(site_id, as_of)` | `critical` \| `warning` \| `no_data` \| `idle` \| `ok` |
