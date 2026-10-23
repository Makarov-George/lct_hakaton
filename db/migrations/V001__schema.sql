-- V001. Схема БД системы мониторинга строительных площадок.

CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TABLE site_type (
    id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name  text NOT NULL UNIQUE CHECK (btrim(name) <> '')
);


CREATE TABLE work_type (
    id          uuid     PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text     UNIQUE CHECK (code ~ '^[0-9]+(\.[0-9]+)*$'),
    parent_id   uuid     REFERENCES work_type (id) ON DELETE CASCADE,
    name        text     NOT NULL CHECK (btrim(name) <> ''),
    level       integer  NOT NULL CHECK (level >= 1),
    observable  boolean  NOT NULL DEFAULT false,

    CONSTRAINT work_type_root CHECK ((parent_id IS NULL) = (level = 1)),
    CONSTRAINT work_type_root_has_code CHECK (parent_id IS NOT NULL OR code IS NOT NULL)
);

CREATE INDEX work_type_parent_idx ON work_type (parent_id);

COMMENT ON COLUMN work_type.code IS 'Иерархический код. NULL у дочерних записей без кода: такая запись определяется родителем';

CREATE FUNCTION check_work_type_hierarchy() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_parent work_type%ROWTYPE;
BEGIN
    IF NEW.parent_id IS NULL THEN
        IF NEW.code IS NOT NULL AND position('.' IN NEW.code) > 0 THEN
            RAISE EXCEPTION 'work_type %: root code must have one segment', NEW.code
                USING ERRCODE = 'check_violation';
        END IF;
        RETURN NEW;
    END IF;

    SELECT * INTO v_parent FROM work_type WHERE id = NEW.parent_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'work_type %: parent % not found', NEW.id, NEW.parent_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    IF NEW.level <> v_parent.level + 1 THEN
        RAISE EXCEPTION 'work_type %: level must be parent level + 1', NEW.id
            USING ERRCODE = 'check_violation';
    END IF;

    IF NEW.code IS NOT NULL AND (
           v_parent.code IS NULL
        OR NEW.code NOT LIKE v_parent.code || '.%'
        OR cardinality(string_to_array(NEW.code, '.'))
           <> cardinality(string_to_array(v_parent.code, '.')) + 1
    ) THEN
        RAISE EXCEPTION 'work_type %: code is inconsistent with parent code %', NEW.code, v_parent.code
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER work_type_check_hierarchy
    BEFORE INSERT OR UPDATE OF code, parent_id, level ON work_type
    FOR EACH ROW EXECUTE FUNCTION check_work_type_hierarchy();


CREATE TABLE work_type_applicability (
    work_type_id  uuid NOT NULL REFERENCES work_type (id) ON DELETE CASCADE,
    site_type_id  uuid NOT NULL REFERENCES site_type (id) ON DELETE CASCADE,
    PRIMARY KEY (work_type_id, site_type_id)
);

CREATE INDEX work_type_applicability_site_type_idx ON work_type_applicability (site_type_id);


CREATE TABLE equipment_class (
    id    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code  text NOT NULL UNIQUE CHECK (code ~ '^[a-z][a-z0-9_]*$'),
    name  text NOT NULL UNIQUE CHECK (btrim(name) <> '')
);

CREATE TABLE site (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text        NOT NULL CHECK (btrim(name) <> ''),
    address       text,
    site_type_id  uuid        NOT NULL REFERENCES site_type (id) ON DELETE CASCADE,
    closed_at     timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX site_site_type_idx ON site (site_type_id);

CREATE TRIGGER site_set_updated_at
    BEFORE UPDATE ON site
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE camera (
    id                 uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id            uuid        NOT NULL REFERENCES site (id) ON DELETE CASCADE,
    name               text        NOT NULL CHECK (btrim(name) <> ''),
    no_data_after_min  integer     CHECK (no_data_after_min > 0),
    closed_at          timestamptz,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT camera_name_unique UNIQUE (site_id, name),
    CONSTRAINT camera_id_site_unique UNIQUE (id, site_id)
);

CREATE TRIGGER camera_set_updated_at
    BEFORE UPDATE ON camera
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


CREATE TABLE plan_task (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id       uuid        NOT NULL REFERENCES site (id) ON DELETE CASCADE,
    work_type_id  uuid        NOT NULL REFERENCES work_type (id) ON DELETE CASCADE,
    start_date    date        NOT NULL,
    end_date      date        NOT NULL,
    closed_at     timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT plan_task_dates CHECK (end_date >= start_date),
    CONSTRAINT plan_task_id_site_unique UNIQUE (id, site_id)
);

CREATE UNIQUE INDEX plan_task_unique_open
    ON plan_task (site_id, work_type_id, start_date)
    WHERE closed_at IS NULL;

CREATE INDEX plan_task_open_by_date_idx
    ON plan_task (site_id, start_date, end_date)
    WHERE closed_at IS NULL;

CREATE INDEX plan_task_work_type_idx ON plan_task (work_type_id);

CREATE TRIGGER plan_task_set_updated_at
    BEFORE UPDATE ON plan_task
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- Вид работ этапа применим к типу участка.
CREATE FUNCTION check_plan_task_applicability() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM site s
        JOIN work_type_applicability a ON a.site_type_id = s.site_type_id
        WHERE s.id = NEW.site_id
          AND a.work_type_id = NEW.work_type_id
    ) THEN
        RAISE EXCEPTION 'work type % is not applicable to site %', NEW.work_type_id, NEW.site_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER plan_task_check_applicability
    BEFORE INSERT OR UPDATE OF site_id, work_type_id ON plan_task
    FOR EACH ROW EXECUTE FUNCTION check_plan_task_applicability();


CREATE TABLE rule (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    work_type_id        uuid        NOT NULL REFERENCES work_type (id) ON DELETE CASCADE,
    equipment_class_id  uuid        NOT NULL REFERENCES equipment_class (id) ON DELETE CASCADE,
    kind                text        NOT NULL CHECK (kind IN ('required', 'allowed', 'unexpected')),
    min_count           integer     CHECK (min_count >= 1),
    severity            text        NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    inherit             boolean     NOT NULL DEFAULT true,
    closed_at           timestamptz,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT rule_min_count CHECK ((kind = 'required') = (min_count IS NOT NULL))
);

-- Одно действующее правило на пару «вид работ + класс техники».
CREATE UNIQUE INDEX rule_unique_open
    ON rule (work_type_id, equipment_class_id)
    WHERE closed_at IS NULL;

CREATE INDEX rule_equipment_class_idx ON rule (equipment_class_id);

CREATE TRIGGER rule_set_updated_at
    BEFORE UPDATE ON rule
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- =====================================================================
-- Снимки и отчёты
-- =====================================================================

CREATE TABLE frame (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id       uuid        NOT NULL REFERENCES site (id) ON DELETE CASCADE,
    camera_id     uuid        NOT NULL,
    storage_key   text        NOT NULL UNIQUE CHECK (btrim(storage_key) <> ''),
    content_type  text        NOT NULL CHECK (content_type IN ('image/jpeg', 'image/png')),
    captured_at   timestamptz NOT NULL,
    received_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT frame_camera_fk
        FOREIGN KEY (camera_id, site_id) REFERENCES camera (id, site_id) ON DELETE CASCADE
);

CREATE INDEX frame_site_captured_idx   ON frame (site_id, captured_at);
CREATE INDEX frame_camera_received_idx ON frame (camera_id, received_at);


CREATE TABLE detection_report (
    id             uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    frame_id       uuid        NOT NULL UNIQUE REFERENCES frame (id) ON DELETE CASCADE,
    status         text        NOT NULL CHECK (status IN ('ok', 'failed')),
    error_message  text,
    created_at     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT detection_report_error CHECK ((status = 'failed') = (error_message IS NOT NULL))
);


CREATE TABLE detection (
    id                    uuid         PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id             uuid         NOT NULL REFERENCES detection_report (id) ON DELETE CASCADE,
    equipment_class_code  text         NOT NULL CHECK (btrim(equipment_class_code) <> ''),
    confidence            numeric(3,2) NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    x_min                 integer      NOT NULL CHECK (x_min >= 0),
    y_min                 integer      NOT NULL CHECK (y_min >= 0),
    x_max                 integer      NOT NULL,
    y_max                 integer      NOT NULL,

    CONSTRAINT detection_bbox CHECK (x_max > x_min AND y_max > y_min)
);

CREATE INDEX detection_report_idx ON detection (report_id);

COMMENT ON COLUMN detection.equipment_class_code IS 'Код класса от детектора. Без FK: неизвестные коды не участвуют в правилах';


-- =====================================================================
-- Отклонения
-- =====================================================================

CREATE TABLE deviation (
    id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id             uuid        NOT NULL REFERENCES site (id) ON DELETE CASCADE,
    type                text        NOT NULL CHECK (type IN (
                                        'missing_required', 'unexpected_equipment',
                                        'unplanned_activity', 'not_observable', 'no_data')),
    plan_task_id        uuid,
    work_type_id        uuid        REFERENCES work_type (id) ON DELETE CASCADE,
    rule_id             uuid        REFERENCES rule (id) ON DELETE CASCADE,
    equipment_class_id  uuid        REFERENCES equipment_class (id) ON DELETE CASCADE,
    camera_id           uuid,
    severity            text        NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    status              text        NOT NULL DEFAULT 'open'
                                    CHECK (status IN ('open', 'acknowledged', 'resolved', 'false_positive')),
    message             text        NOT NULL CHECK (btrim(message) <> ''),
    hits                integer     NOT NULL DEFAULT 1 CHECK (hits >= 1),
    first_seen_at       timestamptz NOT NULL,
    last_seen_at        timestamptz NOT NULL,
    acknowledged_at     timestamptz,
    closed_at           timestamptz,
    closed_by           text        CHECK (closed_by IN ('user', 'system')),
    close_reason        text        CHECK (close_reason IN (
                                        'condition_cleared', 'stage_finished', 'plan_changed',
                                        'rule_disabled', 'camera_disabled',
                                        'user_resolved', 'user_false_positive')),
    comment             text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT deviation_plan_task_fk
        FOREIGN KEY (plan_task_id, site_id) REFERENCES plan_task (id, site_id) ON DELETE CASCADE,
    CONSTRAINT deviation_camera_fk
        FOREIGN KEY (camera_id, site_id) REFERENCES camera (id, site_id) ON DELETE CASCADE,

    CONSTRAINT deviation_seen CHECK (last_seen_at >= first_seen_at),

    -- Закрытое отклонение: все три поля закрытия заполнены; открытое: все пусты.
    CONSTRAINT deviation_closed CHECK (
        CASE WHEN status IN ('resolved', 'false_positive')
             THEN closed_at IS NOT NULL AND closed_by IS NOT NULL AND close_reason IS NOT NULL
             ELSE closed_at IS NULL AND closed_by IS NULL AND close_reason IS NULL
        END),
    CONSTRAINT deviation_acknowledged CHECK (status <> 'acknowledged' OR acknowledged_at IS NOT NULL),

    -- Ссылки по типу.
    CONSTRAINT deviation_work_type_with_task CHECK ((work_type_id IS NULL) = (plan_task_id IS NULL)),
    CONSTRAINT deviation_refs CHECK (
        CASE type
            WHEN 'missing_required'     THEN plan_task_id IS NOT NULL AND rule_id IS NOT NULL
                                             AND equipment_class_id IS NOT NULL AND camera_id IS NULL
            WHEN 'unexpected_equipment' THEN plan_task_id IS NOT NULL AND rule_id IS NOT NULL
                                             AND equipment_class_id IS NOT NULL AND camera_id IS NULL
            WHEN 'not_observable'       THEN plan_task_id IS NOT NULL AND rule_id IS NULL
                                             AND equipment_class_id IS NULL AND camera_id IS NULL
            WHEN 'unplanned_activity'   THEN plan_task_id IS NULL AND rule_id IS NULL
                                             AND camera_id IS NULL
            WHEN 'no_data'              THEN plan_task_id IS NULL AND rule_id IS NULL
                                             AND equipment_class_id IS NULL AND camera_id IS NOT NULL
        END)
);

-- Одно незакрытое отклонение на ключ.
CREATE UNIQUE INDEX deviation_open_unique
    ON deviation (site_id, type, plan_task_id, rule_id, equipment_class_id, camera_id)
    NULLS NOT DISTINCT
    WHERE status IN ('open', 'acknowledged');

CREATE INDEX deviation_site_status_idx ON deviation (site_id, status);
CREATE INDEX deviation_plan_task_idx   ON deviation (plan_task_id) WHERE plan_task_id IS NOT NULL;
CREATE INDEX deviation_rule_idx        ON deviation (rule_id)      WHERE rule_id IS NOT NULL;
CREATE INDEX deviation_camera_idx      ON deviation (camera_id)    WHERE camera_id IS NOT NULL;

CREATE TRIGGER deviation_set_updated_at
    BEFORE UPDATE ON deviation
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();


-- Переходы статуса:
--   open         -> acknowledged | resolved | false_positive
--   acknowledged -> resolved | false_positive
--   resolved, false_positive — конечные.
-- Поля ключа не изменяются.
CREATE FUNCTION check_deviation_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status <> OLD.status AND NOT (
           (OLD.status = 'open'         AND NEW.status IN ('acknowledged', 'resolved', 'false_positive'))
        OR (OLD.status = 'acknowledged' AND NEW.status IN ('resolved', 'false_positive'))
    ) THEN
        RAISE EXCEPTION 'deviation %: invalid status transition % -> %', OLD.id, OLD.status, NEW.status
            USING ERRCODE = 'check_violation';
    END IF;

    IF (NEW.site_id, NEW.type, NEW.plan_task_id, NEW.rule_id, NEW.equipment_class_id, NEW.camera_id)
       IS DISTINCT FROM
       (OLD.site_id, OLD.type, OLD.plan_task_id, OLD.rule_id, OLD.equipment_class_id, OLD.camera_id)
    THEN
        RAISE EXCEPTION 'deviation %: key fields are immutable', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER deviation_check_update
    BEFORE UPDATE ON deviation
    FOR EACH ROW EXECUTE FUNCTION check_deviation_update();


CREATE TABLE deviation_evidence (
    deviation_id  uuid        NOT NULL REFERENCES deviation (id) ON DELETE CASCADE,
    frame_id      uuid        NOT NULL REFERENCES frame (id) ON DELETE CASCADE,
    role          text        NOT NULL CHECK (role IN ('violation', 'resolution')),
    added_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (deviation_id, frame_id)
);

CREATE INDEX deviation_evidence_frame_idx ON deviation_evidence (frame_id);


-- Снимок и отклонение принадлежат одному участку.
CREATE FUNCTION check_evidence_site() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM deviation d
        JOIN frame f ON f.site_id = d.site_id
        WHERE d.id = NEW.deviation_id
          AND f.id = NEW.frame_id
    ) THEN
        RAISE EXCEPTION 'evidence: frame % and deviation % belong to different sites',
            NEW.frame_id, NEW.deviation_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER deviation_evidence_check_site
    BEFORE INSERT OR UPDATE ON deviation_evidence
    FOR EACH ROW EXECUTE FUNCTION check_evidence_site();


CREATE TABLE deviation_history (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    deviation_id  uuid        NOT NULL REFERENCES deviation (id) ON DELETE CASCADE,
    change        text        NOT NULL CHECK (change IN (
                                  'opened', 'updated', 'acknowledged', 'resolved', 'false_positive')),
    status        text        NOT NULL,
    severity      text        NOT NULL,
    hits          integer     NOT NULL,
    actor         text        NOT NULL,
    comment       text,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX deviation_history_deviation_idx ON deviation_history (deviation_id, created_at);


-- Журнал изменений отклонения.
-- Автор: SET LOCAL app.actor = '...'; по умолчанию 'system'.
CREATE FUNCTION on_deviation_change() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    v_change text;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_change := 'opened';
    ELSIF NEW.status <> OLD.status THEN
        v_change := NEW.status;
    ELSIF NEW.hits <> OLD.hits
       OR NEW.last_seen_at <> OLD.last_seen_at
       OR NEW.severity <> OLD.severity
       OR NEW.message <> OLD.message
       OR NEW.comment IS DISTINCT FROM OLD.comment THEN
        v_change := 'updated';
    ELSE
        RETURN NULL;
    END IF;

    INSERT INTO deviation_history (deviation_id, change, status, severity, hits, actor, comment)
    VALUES (NEW.id, v_change, NEW.status, NEW.severity, NEW.hits,
            coalesce(nullif(current_setting('app.actor', true), ''), 'system'),
            NEW.comment);

    RETURN NULL;
END;
$$;

CREATE TRIGGER deviation_on_change
    AFTER INSERT OR UPDATE ON deviation
    FOR EACH ROW EXECUTE FUNCTION on_deviation_change();

-- Действующие правила вида работ с учётом наследования:
-- по каждому классу техники — правило ближайшего уровня дерева;
-- правила предков учитываются только при inherit = true.
CREATE FUNCTION effective_rules(p_work_type_id uuid)
RETURNS TABLE (
    rule_id             uuid,
    source_work_type_id uuid,
    distance            integer,
    equipment_class_id  uuid,
    kind                text,
    min_count           integer,
    severity            text
)
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE chain AS (
        SELECT w.id, w.parent_id, 0 AS depth
        FROM work_type w
        WHERE w.id = p_work_type_id
        UNION ALL
        SELECT w.id, w.parent_id, c.depth + 1
        FROM work_type w
        JOIN chain c ON w.id = c.parent_id
    )
    SELECT DISTINCT ON (r.equipment_class_id)
           r.id, r.work_type_id, c.depth, r.equipment_class_id, r.kind, r.min_count, r.severity
    FROM chain c
    JOIN rule r ON r.work_type_id = c.id
    WHERE r.closed_at IS NULL
      AND (c.depth = 0 OR r.inherit)
    ORDER BY r.equipment_class_id, c.depth;
$$;


-- Незакрытые этапы участка, активные на дату.
CREATE FUNCTION active_plan_tasks(p_site_id uuid, p_on_date date)
RETURNS SETOF plan_task
LANGUAGE sql STABLE AS $$
    SELECT t.*
    FROM plan_task t
    WHERE t.site_id = p_site_id
      AND t.closed_at IS NULL
      AND p_on_date BETWEEN t.start_date AND t.end_date;
$$;


-- Статус этапа на момент p_as_of:
-- planned | completed | not_observable | violation | ok. NULL для закрытого этапа.
CREATE FUNCTION stage_status(p_plan_task_id uuid, p_as_of timestamptz)
RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN p_as_of::date < t.start_date THEN 'planned'
        WHEN p_as_of::date > t.end_date   THEN 'completed'
        WHEN NOT w.observable
          OR NOT EXISTS (SELECT 1 FROM effective_rules(t.work_type_id)) THEN 'not_observable'
        WHEN EXISTS (SELECT 1 FROM deviation d
                     WHERE d.plan_task_id = t.id
                       AND d.status IN ('open', 'acknowledged')) THEN 'violation'
        ELSE 'ok'
    END
    FROM plan_task t
    JOIN work_type w ON w.id = t.work_type_id
    WHERE t.id = p_plan_task_id
      AND t.closed_at IS NULL;
$$;


-- Статус участка на момент p_as_of:
-- critical | warning | no_data | idle | ok.
CREATE FUNCTION site_status(p_site_id uuid, p_as_of timestamptz)
RETURNS text
LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN EXISTS (SELECT 1 FROM deviation d
                     WHERE d.site_id = p_site_id AND d.status IN ('open', 'acknowledged')
                       AND d.type <> 'no_data' AND d.severity = 'critical') THEN 'critical'
        WHEN EXISTS (SELECT 1 FROM deviation d
                     WHERE d.site_id = p_site_id AND d.status IN ('open', 'acknowledged')
                       AND d.type <> 'no_data' AND d.severity = 'warning') THEN 'warning'
        WHEN EXISTS (SELECT 1 FROM deviation d
                     WHERE d.site_id = p_site_id AND d.status IN ('open', 'acknowledged')
                       AND d.type = 'no_data') THEN 'no_data'
        WHEN NOT EXISTS (SELECT 1 FROM active_plan_tasks(p_site_id, p_as_of::date)) THEN 'idle'
        ELSE 'ok'
    END;
$$;
