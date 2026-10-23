from flask import Flask, render_template, request, redirect, url_for, abort, jsonify, flash
from . import db

app = Flask(__name__)
app.secret_key = "change-me"

from datetime import datetime, date

# изменение формата даты
def _finalize(value):
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d.%m.%Y")
    return value

app.jinja_env.finalize = _finalize

# изменение формата выводы информации
STATUS_LABELS = {
    # deviation.type
    "not_observable":        "нет информации с камер",
    "no_data":               "нет данных с камер",
    "missing_required":      "отсутствует обязательная техника",
    "unexpected_equipment":  "непредвиденная техника",
    "unplanned_activity":    "незапланированные работы",

    # deviation.status
    "open":                  "найдено отклонение",
    "acknowledged":          "подтверждено отклонение оператором",
    "resolved":              "устранено отклонение",
    "false_positive":        "ложное срабатывание, отклонений нет",

    # deviation.severity
    "info":                  "инфо",
    "warning":               "предупреждение",
    "critical":              "критично",

    "opened":                "начато",
    "updated":               "изменено",
    "closed":                "завершено",

    # stage_status
    "not_started":           "не начат",
    "in_progress":           "идёт",
    "finished":              "завершён",
    "planned":               "запланирован",
}

@app.template_filter("defined")
def defined(value):
    if value is None:
        return "—"
    return STATUS_LABELS.get(str(value), str(value))


# Все участки + тип + сводка по отклонениям
@app.route("/")
def index():
    sites = db.fetch_all("""
        SELECT
            s.id, s.name, s.address, s.closed_at,
            st.name AS site_type_name,
            (SELECT count(*) FROM deviation d
              WHERE d.site_id = s.id
                AND d.status IN ('open','acknowledged')) AS open_deviations,
            (SELECT max(
                CASE d.severity
                  WHEN 'critical' THEN 3
                  WHEN 'warning'  THEN 2
                  ELSE 1
                END)
              FROM deviation d
              WHERE d.site_id = s.id
                AND d.status IN ('open','acknowledged')) AS worst_severity
        FROM site s
        LEFT JOIN site_type st ON st.id = s.site_type_id
        WHERE s.closed_at IS NULL
        ORDER BY s.name
    """)

    # Активный этап на каждый участок
    for s in sites:
        tasks = db.fetch_all("""
            SELECT
                t.id,
                t.start_date,
                t.end_date,
                wt.name       AS work_type_name,
                wt.observable AS work_type_observable
            FROM active_plan_tasks(%s, CURRENT_DATE) AS t
            JOIN work_type wt ON wt.id = t.work_type_id
            ORDER BY t.start_date
        """, (s["id"],))
        s["active_tasks"] = tasks

    return render_template("index.html", sites=sites)


# создание нового объекта
@app.route("/sites/new", methods=["GET", "POST"])
def site_new():
    site_types = db.fetch_all("SELECT id, name FROM site_type ORDER BY name")
    work_types = db.fetch_all(
        "SELECT id, name FROM work_type WHERE observable = true ORDER BY name"
    )

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        address = request.form.get("address", "").strip()
        site_type_id = request.form.get("site_type_id") or None

        if not name:
            flash("Название обязательно", "error")
            return render_template("site_new.html",
                                   site_types=site_types,
                                   work_types=work_types)

        site = db.execute(
            """INSERT INTO site (name, address, site_type_id)
               VALUES (%s, %s, %s) RETURNING id""",
            (name, address, site_type_id),
        )
        site_id = site["id"]

        # Камеры
        cam_names = request.form.getlist("camera_name[]")
        cam_thresholds = request.form.getlist("camera_no_data_after_min[]")
        for cname, thr in zip(cam_names, cam_thresholds):
            cname = cname.strip()
            if not cname:
                continue
            db.execute(
                """INSERT INTO camera (site_id, name, no_data_after_min)
                   VALUES (%s, %s, %s)""",
                (site_id, cname, int(thr) if thr else None),
            )

        # План-задачи
        wt_ids = request.form.getlist("plan_work_type_id[]")
        starts = request.form.getlist("plan_start_date[]")
        ends = request.form.getlist("plan_end_date[]")
        for wt, s_date, e_date in zip(wt_ids, starts, ends):
            if not wt or not s_date or not e_date:
                continue
            db.execute(
                """INSERT INTO plan_task (site_id, work_type_id, start_date, end_date)
                   VALUES (%s, %s, %s, %s)""",
                (site_id, wt, s_date, e_date),
            )

        flash("Объект создан", "ok")
        return redirect(url_for("site_detail", site_id=site_id))

    return render_template("site_new.html",
                           site_types=site_types,
                           work_types=work_types)


# информация о конкретном объекте
@app.route("/sites/<site_id>")
def site_detail(site_id):
    site = db.fetch_one("""
        SELECT s.*, st.name AS site_type_name
        FROM site s
        LEFT JOIN site_type st ON st.id = s.site_type_id
        WHERE s.id = %s
    """, (site_id,))
    if not site:
        abort(404)

    # Все планы-задачи участка (план)
    plan_tasks = db.fetch_all("""
        SELECT pt.*, wt.name AS work_type_name,
               stage_status(pt.id, now()) AS status
        FROM plan_task pt
        JOIN work_type wt ON wt.id = pt.work_type_id
        WHERE pt.site_id = %s
        ORDER BY pt.start_date
    """, (site_id,))

    # Камеры
    cameras = db.fetch_all(
        "SELECT * FROM camera WHERE site_id = %s ORDER BY name",
        (site_id,),
    )

    # Последние фотографии (по участку)
    frames = db.fetch_all("""
        SELECT f.id, f.storage_key, f.captured_at, f.received_at,
               f.content_type, c.name AS camera_name
        FROM frame f
        LEFT JOIN camera c ON c.id = f.camera_id
        WHERE f.site_id = %s
        ORDER BY f.captured_at DESC
        LIMIT 12
    """, (site_id,))

    # История изменений отклонений этого участка
    history = db.fetch_all("""
        SELECT dh.*, d.type AS deviation_type, d.severity
        FROM deviation_history dh
        JOIN deviation d ON d.id = dh.deviation_id
        WHERE d.site_id = %s
        ORDER BY dh.created_at DESC
        LIMIT 50
    """, (site_id,))

    # Текущие отклонения
    deviations = db.fetch_all("""
        SELECT d.*, wt.name AS work_type_name,
               ec.name AS equipment_class_name,
               c.name  AS camera_name
        FROM deviation d
        LEFT JOIN work_type wt       ON wt.id = d.work_type_id
        LEFT JOIN equipment_class ec ON ec.id = d.equipment_class_id
        LEFT JOIN camera c           ON c.id  = d.camera_id
        WHERE d.site_id = %s
          AND d.status IN ('open','acknowledged')
        ORDER BY d.last_seen_at DESC
    """, (site_id,))

    return render_template(
        "site_detail.html",
        site=site,
        plan_tasks=plan_tasks,
        cameras=cameras,
        frames=frames,
        history=history,
        deviations=deviations,
    )

# изменение плана объекта
@app.route("/sites/<site_id>/plan", methods=["GET", "POST"])
def site_plan_edit(site_id):
    site = db.fetch_one("""
        SELECT s.*, st.name AS site_type_name
        FROM site s
        LEFT JOIN site_type st ON st.id = s.site_type_id
        WHERE s.id = %s
    """, (site_id,))
    if not site:
        abort(404)

    # Список доступных видов работ (все, что observable)
    work_types = db.fetch_all("""
        SELECT id, name FROM work_type
        WHERE observable = true
        ORDER BY name
    """)

    if request.method == "POST":
        # удаление этапа
        delete_ids = request.form.getlist("delete_ids[]")
        for tid in delete_ids:
            if tid:
                db.execute("DELETE FROM plan_task WHERE id = %s AND site_id = %s",
                           (tid, site_id))

        # обновление данных по объекту
        ids = request.form.getlist("pt_id[]")
        wt_ids = request.form.getlist("pt_work_type_id[]")
        starts = request.form.getlist("pt_start_date[]")
        ends = request.form.getlist("pt_end_date[]")

        for tid, wt, s_date, e_date in zip(ids, wt_ids, starts, ends):
            tid = (tid or "").strip()
            if not tid:
                continue
            if not wt or not s_date or not e_date:
                continue    # пропускаем пустые
            db.execute("""
                UPDATE plan_task
                SET work_type_id = %s,
                    start_date   = %s,
                    end_date     = %s
                WHERE id = %s AND site_id = %s
            """, (wt, s_date, e_date, tid, site_id))

        # новые данные
        new_wt_ids = request.form.getlist("new_work_type_id[]")
        new_starts = request.form.getlist("new_start_date[]")
        new_ends = request.form.getlist("new_end_date[]")

        for wt, s_date, e_date in zip(new_wt_ids, new_starts, new_ends):
            if not wt or not s_date or not e_date:
                continue
            db.execute("""
                INSERT INTO plan_task (site_id, work_type_id, start_date, end_date)
                VALUES (%s, %s, %s, %s)
            """, (site_id, wt, s_date, e_date))

        flash("План обновлён", "ok")
        return redirect(url_for("site_plan_edit", site_id=site_id))

    # GET — показать редактор
    plan_tasks = db.fetch_all("""
        SELECT pt.id, pt.work_type_id, pt.start_date, pt.end_date,
               wt.name AS work_type_name
        FROM plan_task pt
        JOIN work_type wt ON wt.id = pt.work_type_id
        WHERE pt.site_id = %s
        ORDER BY pt.start_date
    """, (site_id,))

    return render_template(
        "site_plan_edit.html",
        site=site,
        plan_tasks=plan_tasks,
        work_types=work_types,
    )


# перемещение объектов в архив
@app.post("/sites/<site_id>/archive")
def site_archive(site_id):
    site = db.fetch_one("SELECT id, name, closed_at FROM site WHERE id = %s", (site_id,))
    if not site:
        abort(404)

    db.execute(
        "UPDATE site SET closed_at = now(), updated_at = now() WHERE id = %s",
        (site_id,),
    )
    flash(f"Объект «{site['name']}» перемещён в архив", "ok")
    return redirect(url_for("index"))


# достаем объекты из архива
@app.post("/sites/<site_id>/unarchive")
def site_unarchive(site_id):
    site = db.fetch_one("SELECT id, name FROM site WHERE id = %s", (site_id,))
    if not site:
        abort(404)

    db.execute(
        "UPDATE site SET closed_at = NULL, updated_at = now() WHERE id = %s",
        (site_id,),
    )
    flash(f"Объект «{site['name']}» возвращён из архива", "ok")
    return redirect(url_for("site_detail", site_id=site_id))

# страница с архивными объектами
@app.route("/archive")
def archive():
    sites = db.fetch_all("""
        SELECT
            s.id, s.name, s.address, s.closed_at,
            st.name AS site_type_name
        FROM site s
        LEFT JOIN site_type st ON st.id = s.site_type_id
        WHERE s.closed_at IS NOT NULL
        ORDER BY s.closed_at DESC
    """)
    return render_template("archive.html", sites=sites)


# блоки для проверки (потом нужно будет удалить)

# список всех таблиц
@app.route("/main")
def main():
    tables = db.list_tables()
    return render_template("main.html", tables=tables)


@app.route("/table/<name>")
def table_view(name: str):
    if not name.replace("_", "").isalnum():
        abort(400, "invalid table name")

    known = {t["table_name"] for t in db.list_tables()}
    if name not in known:
        abort(404, f"table '{name}' not found")

    limit = min(int(request.args.get("limit", 100)), 1000)
    rows = db.fetch_all(f'SELECT * FROM "{name}" LIMIT %s', (limit,))
    columns = list(rows[0].keys()) if rows else []
    return render_template(
        "table.html",
        name=name,
        columns=columns,
        rows=rows,
        limit=limit,
    )


@app.errorhandler(400)
@app.errorhandler(404)
def handle_error(e):
    return render_template("error.html", error=e), e.code