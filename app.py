from flask import Flask, render_template, redirect, url_for, request, session, flash, jsonify
import sqlite3
import hashlib
from datetime import datetime, date
from collections import defaultdict

app = Flask(__name__)
import os
app.secret_key = os.environ.get("SECRET_KEY", "Ryonusuke12")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "database.db")

ADMIN_USERNAME = "admin@ucccs"
ADMIN_PASSWORD = "admin123"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id    TEXT UNIQUE NOT NULL,
            lastname      TEXT NOT NULL,
            firstname     TEXT NOT NULL,
            middlename    TEXT,
            address       TEXT,
            course        TEXT,
            level         TEXT,
            email         TEXT,
            password      TEXT NOT NULL,
            sessions_left INTEGER NOT NULL DEFAULT 30
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS announcements (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            title      TEXT,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sitin_sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            purpose    TEXT NOT NULL,
            lab_room   TEXT NOT NULL,
            time_in    TEXT NOT NULL,
            time_out   TEXT,
            status     TEXT NOT NULL DEFAULT 'active'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            lab_room   TEXT NOT NULL,
            message    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reservations (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id    TEXT NOT NULL,
            lab_room      TEXT NOT NULL,
            date          TEXT NOT NULL,
            time_slot     TEXT NOT NULL,
            purpose       TEXT NOT NULL,
            pc_number     TEXT,
            status        TEXT NOT NULL DEFAULT 'pending',
            admin_remarks TEXT,
            created_at    TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS unavailable_pcs (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_room  TEXT NOT NULL,
            pc_number INTEGER NOT NULL,
            UNIQUE(lab_room, pc_number)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reservation_settings (
            id              INTEGER PRIMARY KEY,
            is_open         INTEGER NOT NULL DEFAULT 1,
            disable_message TEXT
        )
    """)
    conn.execute("INSERT OR IGNORE INTO reservation_settings (id, is_open) VALUES (1, 1)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blocked_slots (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            lab_room  TEXT NOT NULL,
            date      TEXT NOT NULL,
            time_slot TEXT NOT NULL,
            UNIQUE(lab_room, date, time_slot)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reservation_logs (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            reservation_id INTEGER NOT NULL,
            student_id     TEXT NOT NULL,
            lab_room       TEXT NOT NULL,
            date           TEXT NOT NULL,
            time_slot      TEXT NOT NULL,
            pc_number      TEXT,
            action         TEXT NOT NULL,
            remarks        TEXT,
            processed_by   TEXT NOT NULL,
            action_at      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reservation_tips (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            icon       TEXT,
            message    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL,
            title      TEXT NOT NULL,
            message    TEXT NOT NULL,
            is_read    INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS student_ratings (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id    INTEGER NOT NULL,
            student_id    TEXT NOT NULL,
            behavior      INTEGER NOT NULL DEFAULT 0,
            pc_usage      INTEGER NOT NULL DEFAULT 0,
            cleanliness   INTEGER NOT NULL DEFAULT 0,
            arrangement   INTEGER NOT NULL DEFAULT 0,
            shutdown      INTEGER NOT NULL DEFAULT 0,
            raw_score     INTEGER NOT NULL DEFAULT 0,
            average       REAL    NOT NULL DEFAULT 0,
            remarks       TEXT,
            rated_by      TEXT NOT NULL,
            rated_at      TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS analytics_snapshots (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date    TEXT NOT NULL,
            total_sessions   INTEGER NOT NULL DEFAULT 0,
            unique_students  INTEGER NOT NULL DEFAULT 0,
            total_feedback   INTEGER NOT NULL DEFAULT 0,
            top_purpose      TEXT,
            top_lab          TEXT,
            created_at       TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lab_software (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            lab      TEXT NOT NULL,
            name     TEXT NOT NULL,
            version  TEXT,
            category TEXT NOT NULL DEFAULT 'TOOL'
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS lab_software_settings (
            id           INTEGER PRIMARY KEY,
            is_published INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("INSERT OR IGNORE INTO lab_software_settings (id, is_published) VALUES (1, 0)")
    conn.commit()

    def add_column_if_missing(table, column, col_type):
        existing = [row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if column not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            conn.commit()
            print(f"[migrate] Added '{column}' to '{table}'")

    add_column_if_missing("reservations",         "pc_number",       "TEXT")
    add_column_if_missing("reservations",         "admin_remarks",   "TEXT")
    add_column_if_missing("reservation_settings", "disable_message", "TEXT")
    add_column_if_missing("reservation_logs",     "pc_number",       "TEXT")
    add_column_if_missing("reservation_logs",     "remarks",         "TEXT")
    add_column_if_missing("reservation_logs",     "processed_by",    "TEXT NOT NULL DEFAULT ''")
    add_column_if_missing("reservation_logs",     "action_at",       "TEXT NOT NULL DEFAULT ''")
    add_column_if_missing("student_ratings",      "raw_score",       "INTEGER NOT NULL DEFAULT 0")
    add_column_if_missing("feedback", "rating",         "INTEGER NOT NULL DEFAULT 0")
    add_column_if_missing("feedback", "session_id_ref", "INTEGER")
    add_column_if_missing("sitin_sessions",       "pc_number",       "TEXT")

    conn.execute("""
        UPDATE student_ratings
        SET raw_score = behavior + arrangement + cleanliness
        WHERE raw_score = 0 AND (behavior + arrangement + cleanliness) > 0
    """)
    conn.commit()
    conn.close()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

init_db()

# ══════════════════════════════════════════════════════════════════════════════
#  LANDING / AUTH ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def landing():
    conn = get_db()
    leaderboard = conn.execute("""
        SELECT
            s.student_id, s.firstname, s.lastname, s.course, s.level,
            SUM(r.raw_score)                                 AS total_points,
            ROUND(AVG(CAST(r.raw_score AS REAL)), 1)         AS avg_score,
            COUNT(r.id)                                      AS total_ratings
        FROM students s
        JOIN student_ratings r ON s.student_id = r.student_id
        GROUP BY s.student_id
        ORDER BY total_points DESC, avg_score DESC
        LIMIT 10
    """).fetchall()
    conn.close()
    return render_template("LandingPage/landing.html", leaderboard=leaderboard)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        student_id = request.form.get("id", "").strip()
        lastname   = request.form.get("lastname", "").strip()
        firstname  = request.form.get("firstname", "").strip()
        middlename = request.form.get("middlename", "").strip()
        address    = request.form.get("address", "").strip()
        course     = request.form.get("course", "").strip()
        level      = request.form.get("level", "").strip()
        email      = request.form.get("email", "").strip()
        password   = request.form.get("password", "")
        confirm    = request.form.get("confirm_password", "")
        if not all([student_id, lastname, firstname, password]):
            flash("Please fill in all required fields.", "error")
            return render_template("LandingPage/registration.html")
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("LandingPage/registration.html")
        try:
            conn = get_db()
            conn.execute("""
                INSERT INTO students
                (student_id, lastname, firstname, middlename, address, course, level, email, password, sessions_left)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 30)
            """, (student_id, lastname, firstname, middlename, address, course, level,
                  email, hash_password(password)))
            conn.commit()
            conn.close()
        except sqlite3.IntegrityError:
            flash("That ID number is already registered.", "error")
            return render_template("LandingPage/registration.html")
        flash("Account created successfully! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("LandingPage/registration.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("id", "").strip()
        password = request.form.get("password", "")
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"]   = True
            session["admin_user"] = ADMIN_USERNAME
            return redirect(url_for("admin_home"))
        conn    = get_db()
        student = conn.execute(
            "SELECT * FROM students WHERE student_id = ? AND password = ?",
            (username, hash_password(password))
        ).fetchone()
        conn.close()
        if student:
            session["student_id"] = student["student_id"]
            session["firstname"]  = student["firstname"]
            session["lastname"]   = student["lastname"]
            session["middlename"] = student["middlename"]
            session["address"]    = student["address"]
            session["course"]     = student["course"]
            session["level"]      = student["level"]
            session["email"]      = student["email"]
            return redirect(url_for("dashboard"))
        flash("Invalid ID or password.", "error")
        return render_template("LandingPage/login.html")
    return render_template("LandingPage/login.html")

@app.route("/about")
def about():
    return render_template("LandingPage/about.html")

@app.route("/community")
def community():
    return render_template("LandingPage/community.html")

# ══════════════════════════════════════════════════════════════════════════════
#  STUDENT ROUTES
# ══════════════════════════════════════════════════════════════════════════════

def get_student_notifications(student_id):
    conn   = get_db()
    notifs = conn.execute(
        "SELECT * FROM notifications WHERE student_id=? ORDER BY id DESC LIMIT 20",
        (student_id,)
    ).fetchall()
    unread = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE student_id=? AND is_read=0",
        (student_id,)
    ).fetchone()[0]
    conn.close()
    return notifs, unread

@app.route("/dashboard")
def dashboard():
    if "student_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    announcements = conn.execute("SELECT * FROM announcements ORDER BY id DESC").fetchall()
    conn.close()
    return render_template("StudentPage/dashboard.html",
                           student=session, announcements=announcements)

@app.route("/edit_profile")
def edit_profile():
    if "student_id" not in session:
        return redirect(url_for("login"))
    return render_template("StudentPage/edit_profile.html", student=session)

@app.route("/update_profile", methods=["POST"])
def update_profile():
    if "student_id" not in session:
        return redirect(url_for("login"))
    firstname  = request.form.get("firstname", "").strip()
    lastname   = request.form.get("lastname", "").strip()
    middlename = request.form.get("middlename", "").strip()
    email      = request.form.get("email", "").strip()
    address    = request.form.get("address", "").strip()
    level      = request.form.get("level", "").strip()
    new_pass   = request.form.get("new_password", "")
    confirm    = request.form.get("confirm_password", "")
    if new_pass and new_pass != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("edit_profile"))
    conn = get_db()
    if new_pass:
        conn.execute("""
            UPDATE students SET firstname=?,lastname=?,middlename=?,email=?,address=?,level=?,password=?
            WHERE student_id=?
        """, (firstname, lastname, middlename, email, address, level,
              hash_password(new_pass), session["student_id"]))
    else:
        conn.execute("""
            UPDATE students SET firstname=?,lastname=?,middlename=?,email=?,address=?,level=?
            WHERE student_id=?
        """, (firstname, lastname, middlename, email, address, level, session["student_id"]))
    conn.commit()
    conn.close()
    session.update({"firstname": firstname, "lastname": lastname,
                    "middlename": middlename, "email": email,
                    "address": address, "level": level})
    flash("Profile updated successfully!", "success")
    return redirect(url_for("edit_profile"))

@app.route("/history")
def history():
    if "student_id" not in session:
        return redirect(url_for("login"))
    sid  = session["student_id"]
    conn = get_db()

    records = conn.execute(
        "SELECT * FROM sitin_sessions WHERE student_id=? ORDER BY id DESC",
        (sid,)
    ).fetchall()

    # Sessions remaining
    student_db    = conn.execute("SELECT sessions_left FROM students WHERE student_id=?", (sid,)).fetchone()
    sessions_left = student_db["sessions_left"] if student_db else 0

    # Compute per-session durations
    fmt          = "%Y-%m-%d %H:%M:%S"
    durations    = {}
    total_mins   = 0
    longest      = 0
    dur_list     = []
    for r in records:
        if r["time_in"] and r["time_out"] and r["status"] == "done":
            try:
                diff = int((datetime.strptime(r["time_out"], fmt) -
                            datetime.strptime(r["time_in"],  fmt)).total_seconds() / 60)
                if 0 < diff < 600:
                    durations[r["id"]] = diff
                    total_mins += diff
                    dur_list.append(diff)
                    if diff > longest:
                        longest = diff
            except:
                pass

    total_hours  = round(total_mins / 60, 1)
    avg_duration = round(sum(dur_list) / len(dur_list)) if dur_list else 0
    completed    = sum(1 for r in records if r["status"] == "done")
    active       = sum(1 for r in records if r["status"] == "active")

    # Admin ratings of student per session
    ratings = {}
    for row in conn.execute(
        "SELECT session_id, raw_score FROM student_ratings WHERE student_id=?", (sid,)
    ).fetchall():
        ratings[row["session_id"]] = row["raw_score"]

    # Student feedback already submitted (keyed by session_id)
    feedback_map = {}
    for row in conn.execute(
        "SELECT session_id_ref, rating FROM feedback WHERE student_id=? AND session_id_ref IS NOT NULL",
        (sid,)
    ).fetchall():
        feedback_map[row["session_id_ref"]] = row

    conn.close()

    stats = {
        "sessions_left" : sessions_left,
        "total_hours"   : total_hours,
        "total_minutes" : total_mins,
        "total_sessions": len(records),
        "completed"     : completed,
        "active"        : active,
        "avg_duration"  : avg_duration,
        "longest"       : longest,
    }

    return render_template("StudentPage/history.html",
                           student=session,
                           records=records,
                           stats=stats,
                           durations=durations,
                           ratings=ratings,
                           feedback_map=feedback_map)


# ── REPLACE YOUR EXISTING submit_feedback() ROUTE WITH THIS ──────────────────
@app.route("/submit_feedback", methods=["POST"])
def submit_feedback():
    if "student_id" not in session:
        return redirect(url_for("login"))
    lab_room   = request.form.get("lab_room",   "").strip()
    message    = request.form.get("message",    "").strip()
    session_id = request.form.get("session_id", "").strip()
    rating_raw = request.form.get("rating",     "0").strip()

    if not lab_room or not message:
        flash("Please fill in all feedback fields.", "error")
        return redirect(url_for("history"))

    try:
        rating = max(0, min(5, int(rating_raw)))
    except:
        rating = 0

    sid_ref = int(session_id) if session_id.isdigit() else None

    conn = get_db()
    conn.execute(
        "INSERT INTO feedback (student_id, lab_room, message, rating, session_id_ref, created_at) VALUES (?,?,?,?,?,?)",
        (session["student_id"], lab_room, message, rating, sid_ref,
         datetime.now().strftime("%Y-%m-%d"))
    )
    conn.commit()
    conn.close()
    flash("Thank you! Your feedback has been submitted.", "success")
    return redirect(url_for("history"))

# ── Student: Reservation ─────────────────────────────────────────────────────
@app.route("/reservation")
def reservation():
    if "student_id" not in session:
        return redirect(url_for("login"))
    sid  = session["student_id"]
    conn = get_db()

    reservations = conn.execute(
        "SELECT * FROM reservations WHERE student_id=? ORDER BY id DESC", (sid,)
    ).fetchall()

    has_pending = conn.execute(
        "SELECT id FROM reservations WHERE student_id=? AND status='pending'", (sid,)
    ).fetchone() is not None

    tips = conn.execute("SELECT * FROM reservation_tips ORDER BY id DESC").fetchall()

    blocked_rows  = conn.execute("SELECT lab_room, date, time_slot FROM blocked_slots").fetchall()
    blocked_slots = {}
    for row in blocked_rows:
        key = row["lab_room"] + "|" + row["date"]
        blocked_slots.setdefault(key, []).append(row["time_slot"])

    reserved_rows = conn.execute("""
        SELECT lab_room, date, time_slot, pc_number FROM reservations
        WHERE status IN ('pending','approved') AND pc_number IS NOT NULL
    """).fetchall()
    reserved_pcs = {}
    for row in reserved_rows:
        if row["pc_number"]:
            try:
                pc_num = int(row["pc_number"].replace("PC ", ""))
            except:
                continue
            key = row["lab_room"] + "|" + row["date"] + "|" + row["time_slot"]
            reserved_pcs.setdefault(key, []).append(pc_num)

    unavail_rows    = conn.execute("SELECT lab_room, pc_number FROM unavailable_pcs").fetchall()
    unavailable_pcs = {}
    for row in unavail_rows:
        unavailable_pcs.setdefault(row["lab_room"], []).append(row["pc_number"])

    settings                = conn.execute("SELECT * FROM reservation_settings WHERE id=1").fetchone()
    reservations_open       = settings["is_open"] if settings else 1
    reservations_closed_msg = settings["disable_message"] if settings else ""

    student_db            = conn.execute("SELECT sessions_left FROM students WHERE student_id=?", (sid,)).fetchone()
    student_sessions_left = student_db["sessions_left"] if student_db else 0

    notifications, unread_count = get_student_notifications(sid)
    conn.close()

    return render_template("StudentPage/reservation.html",
                           student=session,
                           reservations=reservations,
                           has_pending=has_pending,
                           tips=tips,
                           blocked_slots=blocked_slots,
                           reserved_pcs=reserved_pcs,
                           unavailable_pcs=unavailable_pcs,
                           reservations_open=reservations_open,
                           reservations_closed=not reservations_open,
                           reservations_closed_msg=reservations_closed_msg,
                           notifications=notifications,
                           unread_count=unread_count,
                           student_sessions_left=student_sessions_left,
                           today=date.today().isoformat())

@app.route("/submit_reservation", methods=["POST"])
def submit_reservation():
    if "student_id" not in session:
        return redirect(url_for("login"))
    sid       = session["student_id"]
    lab_room  = request.form.get("lab_room", "").strip()
    res_date  = request.form.get("date", "").strip()
    time_slot = request.form.get("time_slot", "").strip()
    purpose   = request.form.get("purpose", "").strip()

    if not all([lab_room, res_date, time_slot, purpose]):
        flash("Please fill in all fields and select a time slot.", "error")
        return redirect(url_for("reservation"))

    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM reservations WHERE student_id=? AND status='pending'", (sid,)
    ).fetchone()
    if existing:
        flash("You already have a pending reservation.", "error")
        conn.close()
        return redirect(url_for("reservation"))

    blocked = conn.execute(
        "SELECT id FROM blocked_slots WHERE lab_room=? AND date=? AND time_slot=?",
        (lab_room, res_date, time_slot)
    ).fetchone()
    if blocked:
        flash("That time slot is not available. Please choose another.", "error")
        conn.close()
        return redirect(url_for("reservation"))

    pc_number = request.form.get("pc_number", "").strip()
    conn.execute("""
        INSERT INTO reservations (student_id, lab_room, date, time_slot, purpose, pc_number, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (sid, lab_room, res_date, time_slot, purpose, pc_number or None,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    flash("Reservation submitted! Please wait for admin approval.", "success")
    return redirect(url_for("reservation"))

# ── Notifications ─────────────────────────────────────────────────────────────
@app.route("/notifications/mark_read/<int:notif_id>", methods=["POST"])
def mark_notification_read(notif_id):
    if "student_id" not in session:
        return jsonify({"ok": False}), 401
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE id=? AND student_id=?",
                 (notif_id, session["student_id"]))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})

@app.route("/notifications/mark_all_read", methods=["POST"])
def mark_all_notifications_read():
    if "student_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    conn.execute("UPDATE notifications SET is_read=1 WHERE student_id=?",
                 (session["student_id"],))
    conn.commit()
    conn.close()
    return redirect(url_for("reservation"))

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))

# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN HELPER
# ══════════════════════════════════════════════════════════════════════════════

def admin_required():
    return session.get("is_admin") is True

# ══════════════════════════════════════════════════════════════════════════════
#  ADMIN ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/admin")
def admin_home():
    if not admin_required():
        return redirect(url_for("login"))
    conn = get_db()
    total_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    current_sitin  = conn.execute("SELECT COUNT(*) FROM sitin_sessions WHERE status='active'").fetchone()[0]
    total_sitin    = conn.execute("SELECT COUNT(*) FROM sitin_sessions").fetchone()[0]
    announcements  = conn.execute("SELECT * FROM announcements ORDER BY id DESC").fetchall()
    conn.close()
    stats = {"total_students": total_students, "current_sitin": current_sitin, "total_sitin": total_sitin}
    return render_template("AdminPage/home.html", active="home", stats=stats, announcements=announcements)

@app.route("/admin/announcement/post", methods=["POST"])
def admin_post_announcement():
    if not admin_required(): return redirect(url_for("login"))
    title   = request.form.get("title", "").strip()
    content = request.form.get("content", "").strip()
    if not content:
        flash("Announcement content is required.", "error")
        return redirect(url_for("admin_home"))
    conn = get_db()
    conn.execute("INSERT INTO announcements (title,content,created_at) VALUES (?,?,?)",
                 (title or None, content, datetime.now().strftime("%Y-%m-%d")))
    conn.commit(); conn.close()
    flash("Announcement posted!", "success")
    return redirect(url_for("admin_home"))

@app.route("/admin/announcement/delete/<int:ann_id>", methods=["POST"])
def admin_delete_announcement(ann_id):
    if not admin_required(): return redirect(url_for("login"))
    conn = get_db()
    conn.execute("DELETE FROM announcements WHERE id=?", (ann_id,))
    conn.commit(); conn.close()
    flash("Announcement deleted.", "success")
    return redirect(url_for("admin_home"))

@app.route("/admin/search", methods=["GET", "POST"])
def admin_search():
    if not admin_required(): return redirect(url_for("login"))
    student = None; query = None; searched = False
    if request.method == "POST":
        query    = request.form.get("query", "").strip()
        searched = True
        conn     = get_db()
        student  = conn.execute("""
            SELECT * FROM students WHERE student_id=? OR (firstname||' '||lastname) LIKE ?
        """, (query, f"%{query}%")).fetchone()
        conn.close()
    return render_template("AdminPage/search.html", active="search",
                           student=student, query=query, searched=searched)

@app.route("/admin/sitin/submit", methods=["POST"])
def admin_sitin_submit():
    if not admin_required(): return redirect(url_for("login"))
    student_id = request.form.get("student_id", "").strip()
    purpose    = request.form.get("purpose", "").strip()
    lab_room   = request.form.get("lab_room", "").strip()
    conn       = get_db()
    student    = conn.execute("SELECT * FROM students WHERE student_id=?", (student_id,)).fetchone()
    if not student or student["sessions_left"] <= 0:
        flash("Cannot sit in: student not found or no sessions remaining.", "error")
        conn.close(); return redirect(url_for("admin_search"))
    active = conn.execute(
        "SELECT id FROM sitin_sessions WHERE student_id=? AND status='active'", (student_id,)
    ).fetchone()
    if active:
        flash("This student is already sitting in.", "error")
        conn.close(); return redirect(url_for("admin_search"))
    pc_number = request.form.get("pc_number", "").strip()
    conn.execute("""
        INSERT INTO sitin_sessions (student_id,purpose,lab_room,pc_number,time_in,status)
        VALUES (?,?,?,?,?,'active')
    """, (student_id, purpose, lab_room, pc_number or None, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); conn.close()
    flash(f"Student {student_id} has been logged in successfully!", "success")
    return redirect(url_for("admin_current_sitin"))

# ── Sit-In from Approved Reservation ─────────────────────────────────────────
@app.route("/admin/reservation/<int:res_id>/sitin", methods=["POST"])
def admin_reservation_sitin(res_id):
    if not admin_required(): return redirect(url_for("login"))
    conn = get_db()
    res  = conn.execute("""
        SELECT r.*, s.firstname, s.lastname, s.sessions_left
        FROM reservations r JOIN students s ON r.student_id = s.student_id
        WHERE r.id = ? AND r.status = 'approved'
    """, (res_id,)).fetchone()

    if not res:
        flash("Reservation not found or not approved.", "error")
        conn.close()
        return redirect(url_for("admin_reservation") + "#requests")

    if res["sessions_left"] <= 0:
        flash("Student has no sessions remaining.", "error")
        conn.close()
        return redirect(url_for("admin_reservation") + "#requests")

    active = conn.execute(
        "SELECT id FROM sitin_sessions WHERE student_id=? AND status='active'",
        (res["student_id"],)
    ).fetchone()
    if active:
        flash("This student is already sitting in.", "error")
        conn.close()
        return redirect(url_for("admin_reservation") + "#requests")

    conn.execute("""
        INSERT INTO sitin_sessions (student_id, purpose, lab_room, pc_number, time_in, status)
        VALUES (?, ?, ?, ?, ?, 'active')
    """, (res["student_id"], res["purpose"], res["lab_room"], res["pc_number"],
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.execute("UPDATE reservations SET status='used' WHERE id=?", (res_id,))
    conn.commit(); conn.close()

    flash(f"{res['firstname']} {res['lastname']} has been sat in successfully!", "success")
    return redirect(url_for("admin_current_sitin"))

# ── Timeout → Rating Page ─────────────────────────────────────────────────────
@app.route("/admin/sitin/timeout/<int:session_id>", methods=["POST"])
def admin_timeout(session_id):
    if not admin_required(): return redirect(url_for("login"))
    conn  = get_db()
    sitin = conn.execute("SELECT student_id FROM sitin_sessions WHERE id=?", (session_id,)).fetchone()
    if sitin:
        conn.execute("UPDATE sitin_sessions SET status='done', time_out=? WHERE id=?",
                     (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), session_id))
        conn.execute(
            "UPDATE students SET sessions_left=sessions_left-1 WHERE student_id=? AND sessions_left>0",
            (sitin["student_id"],))
        conn.commit()
    conn.close()
    return redirect(url_for("admin_rate_student", session_id=session_id))

# ── Rating Page (GET) ─────────────────────────────────────────────────────────
@app.route("/admin/sitin/rate/<int:session_id>", methods=["GET"])
def admin_rate_student(session_id):
    if not admin_required(): return redirect(url_for("login"))
    conn  = get_db()
    sitin = conn.execute("""
        SELECT ss.*, s.firstname, s.lastname, s.course, s.level,
               s.student_id as sid, ss.purpose
        FROM sitin_sessions ss
        JOIN students s ON ss.student_id = s.student_id
        WHERE ss.id = ?
    """, (session_id,)).fetchone()

    if not sitin:
        flash("Session not found.", "error")
        conn.close()
        return redirect(url_for("admin_current_sitin"))

    score_summary = conn.execute("""
        SELECT
            COALESCE(SUM(raw_score), 0)                           AS total_points,
            COALESCE(ROUND(AVG(CAST(raw_score AS REAL)), 1), 0.0) AS avg_score,
            COUNT(id)                                             AS total_ratings
        FROM student_ratings
        WHERE student_id = ?
    """, (sitin["sid"],)).fetchone()

    conn.close()
    return render_template("AdminPage/rate_student.html",
                           active="sitin",
                           sitin=sitin,
                           score_summary=score_summary)

# ── Rating Submit (POST) ──────────────────────────────────────────────────────
@app.route("/admin/sitin/rate/<int:session_id>/submit", methods=["POST"])
def admin_rate_student_submit(session_id):
    if not admin_required(): return redirect(url_for("login"))
    conn  = get_db()
    sitin = conn.execute(
        "SELECT student_id FROM sitin_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if not sitin:
        flash("Session not found.", "error")
        conn.close(); return redirect(url_for("admin_current_sitin"))

    behavior    = int(request.form.get("behavior",    0))
    arrangement = int(request.form.get("arrangement", 0))
    cleanliness = int(request.form.get("cleanliness", 0))
    pc_usage    = int(request.form.get("pc_usage",    0))
    shutdown    = int(request.form.get("shutdown",    0))
    remarks     = request.form.get("remarks", "").strip()

    raw_score = behavior + arrangement + cleanliness
    average   = round(raw_score / 3, 4)

    conn.execute("""
        INSERT INTO student_ratings
        (session_id, student_id, behavior, pc_usage, cleanliness, arrangement, shutdown,
         raw_score, average, remarks, rated_by, rated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (session_id, sitin["student_id"], behavior, pc_usage, cleanliness,
          arrangement, shutdown, raw_score, average, remarks or None,
          ADMIN_USERNAME, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); conn.close()

    flash("Student rated successfully!", "success")
    return redirect(url_for("admin_current_sitin"))

@app.route("/admin/sitin/current")
def admin_current_sitin():
    if not admin_required(): return redirect(url_for("login"))
    conn     = get_db()
    sessions = conn.execute("""
        SELECT ss.id, ss.student_id, ss.purpose, ss.lab_room, ss.pc_number, ss.time_in,
               s.firstname, s.lastname, s.course
        FROM sitin_sessions ss JOIN students s ON ss.student_id=s.student_id
        WHERE ss.status='active' ORDER BY ss.time_in DESC
    """).fetchall()
    conn.close()
    return render_template("AdminPage/current_sitin.html", active="sitin", sessions=sessions)

@app.route("/admin/sitin/records")
def admin_sitin_records():
    if not admin_required(): return redirect(url_for("login"))
    conn    = get_db()
    records = conn.execute("""
        SELECT ss.id,ss.student_id,ss.purpose,ss.lab_room,ss.pc_number,ss.time_in,ss.time_out,
               s.firstname,s.lastname,s.course
        FROM sitin_sessions ss JOIN students s ON ss.student_id=s.student_id
        WHERE ss.status='done' ORDER BY ss.id DESC
    """).fetchall()
    purpose_data = {}; lab_data = {}; course_data = {}; student_ids = set()
    for r in records:
        purpose_data[r["purpose"]] = purpose_data.get(r["purpose"], 0) + 1
        lab_data[r["lab_room"]]    = lab_data.get(r["lab_room"], 0) + 1
        course_data[r["course"]]   = course_data.get(r["course"], 0) + 1
        student_ids.add(r["student_id"])
    top_purpose = max(purpose_data, key=purpose_data.get) if purpose_data else "—"
    conn.close()
    return render_template("AdminPage/view_sitin_records.html", active="records",
                           records=records, purpose_data=purpose_data, lab_data=lab_data,
                           course_data=course_data, unique_students=len(student_ids),
                           top_purpose=top_purpose)

@app.route("/admin/sitin/reports")
def admin_sitin_reports():
    if not admin_required(): return redirect(url_for("login"))
    date_from  = request.args.get("date_from", "").strip()
    date_to    = request.args.get("date_to", "").strip()
    lab_filter = request.args.get("lab_filter", "").strip()
    query = """
        SELECT ss.id,ss.student_id,ss.purpose,ss.lab_room,ss.pc_number,ss.time_in,ss.time_out,
               s.firstname,s.lastname,s.course
        FROM sitin_sessions ss JOIN students s ON ss.student_id=s.student_id
        WHERE ss.status='done'
    """
    params = []
    if date_from:  query += " AND DATE(ss.time_in)>=?"; params.append(date_from)
    if date_to:    query += " AND DATE(ss.time_in)<=?"; params.append(date_to)
    if lab_filter: query += " AND ss.lab_room=?";       params.append(lab_filter)
    query += " ORDER BY ss.time_in DESC"
    conn    = get_db()
    records = conn.execute(query, params).fetchall()
    conn.close()
    return render_template("AdminPage/sitin_reports.html", active="reports",
                           records=records, date_from=date_from,
                           date_to=date_to, lab_filter=lab_filter)

@app.route("/admin/feedback")
def admin_feedback_reports():
    if not admin_required(): return redirect(url_for("login"))
    conn      = get_db()
    feedbacks = conn.execute("""
        SELECT f.id,f.student_id,f.lab_room,f.message,f.created_at,
               s.firstname,s.lastname
        FROM feedback f LEFT JOIN students s ON f.student_id=s.student_id
        ORDER BY f.id DESC
    """).fetchall()
    conn.close()
    return render_template("AdminPage/feedback_reports.html", active="feedback", feedbacks=feedbacks)

@app.route("/admin/feedback/delete/<int:feedback_id>", methods=["POST"])
def admin_delete_feedback(feedback_id):
    if not admin_required(): return redirect(url_for("login"))
    conn = get_db()
    conn.execute("DELETE FROM feedback WHERE id=?", (feedback_id,))
    conn.commit(); conn.close()
    flash("Feedback deleted.", "success")
    return redirect(url_for("admin_feedback_reports"))

@app.route("/admin/students")
def admin_students():
    if not admin_required(): return redirect(url_for("login"))
    conn     = get_db()
    students = conn.execute("SELECT * FROM students ORDER BY lastname ASC").fetchall()
    conn.close()
    return render_template("AdminPage/students.html", active="students", students=students)

@app.route("/admin/students/edit/<student_id>", methods=["GET", "POST"])
def admin_edit_student(student_id):
    if not admin_required(): return redirect(url_for("login"))
    conn = get_db()
    if request.method == "POST":
        conn.execute("""
            UPDATE students SET firstname=?,lastname=?,middlename=?,email=?,
            course=?,level=?,address=?,sessions_left=? WHERE student_id=?
        """, (request.form.get("firstname","").strip(), request.form.get("lastname","").strip(),
              request.form.get("middlename","").strip(), request.form.get("email","").strip(),
              request.form.get("course","").strip(),     request.form.get("level","").strip(),
              request.form.get("address","").strip(),    request.form.get("sessions_left", 30),
              student_id))
        conn.commit(); conn.close()
        flash("Student updated successfully!", "success")
        return redirect(url_for("admin_students"))
    student = conn.execute("SELECT * FROM students WHERE student_id=?", (student_id,)).fetchone()
    conn.close()
    if not student:
        flash("Student not found.", "error"); return redirect(url_for("admin_students"))
    return render_template("AdminPage/edit_student.html", active="students", student=student)

@app.route("/admin/students/delete/<student_id>", methods=["POST"])
def admin_delete_student(student_id):
    if not admin_required(): return redirect(url_for("login"))
    conn = get_db()
    conn.execute("DELETE FROM students WHERE student_id=?", (student_id,))
    conn.commit(); conn.close()
    flash("Student deleted.", "success")
    return redirect(url_for("admin_students"))

@app.route("/admin/students/add", methods=["POST"])
def admin_add_student():
    if not admin_required(): return redirect(url_for("login"))
    student_id = request.form.get("id","").strip()
    lastname   = request.form.get("lastname","").strip()
    firstname  = request.form.get("firstname","").strip()
    password   = request.form.get("password","")
    confirm    = request.form.get("confirm_password","")
    if not all([student_id, lastname, firstname, password]):
        flash("Please fill in all required fields.", "error")
        return redirect(url_for("admin_students"))
    if password != confirm:
        flash("Passwords do not match.", "error")
        return redirect(url_for("admin_students"))
    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO students
            (student_id,lastname,firstname,middlename,address,course,level,email,password,sessions_left)
            VALUES (?,?,?,?,?,?,?,?,?,30)
        """, (student_id, lastname, firstname,
              request.form.get("middlename","").strip(),
              request.form.get("address","").strip(),
              request.form.get("course","").strip(),
              request.form.get("level","").strip(),
              request.form.get("email","").strip(),
              hash_password(password)))
        conn.commit(); conn.close()
        flash(f"Student {firstname} {lastname} registered successfully!", "success")
    except sqlite3.IntegrityError:
        flash("That ID number is already registered.", "error")
    return redirect(url_for("admin_students"))

@app.route("/admin/students/reset-sessions", methods=["POST"])
def admin_reset_all_sessions():
    if not admin_required(): return redirect(url_for("login"))
    conn = get_db()

    # ── Save analytics snapshot before resetting ──────────────────────────
    top_p = conn.execute("""
        SELECT purpose, COUNT(*) c FROM sitin_sessions
        WHERE status='done' GROUP BY purpose ORDER BY c DESC LIMIT 1
    """).fetchone()
    top_l = conn.execute("""
        SELECT lab_room, COUNT(*) c FROM sitin_sessions
        WHERE status='done' GROUP BY lab_room ORDER BY c DESC LIMIT 1
    """).fetchone()
    tot  = conn.execute("SELECT COUNT(*) FROM sitin_sessions WHERE status='done'").fetchone()[0]
    uniq = conn.execute("SELECT COUNT(DISTINCT student_id) FROM sitin_sessions WHERE status='done'").fetchone()[0]
    fb   = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    conn.execute("""
        INSERT INTO analytics_snapshots
        (snapshot_date, total_sessions, unique_students, total_feedback, top_purpose, top_lab, created_at)
        VALUES (?,?,?,?,?,?,?)
    """, (date.today().isoformat(), tot, uniq, fb,
          top_p["purpose"] if top_p else None,
          top_l["lab_room"] if top_l else None,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    # ─────────────────────────────────────────────────────────────────────

    conn.execute("UPDATE students SET sessions_left=30")
    conn.commit(); conn.close()
    flash("All student sessions have been reset to 30.", "success")
    return redirect(url_for("admin_students"))

# ── Admin: Reservation ────────────────────────────────────────────────────────
@app.route("/admin/reservation")
def admin_reservation():
    if not admin_required(): return redirect(url_for("login"))
    conn = get_db()

    pending_reservations = conn.execute("""
        SELECT r.*, s.firstname, s.lastname, s.course
        FROM reservations r JOIN students s ON r.student_id=s.student_id
        WHERE r.status='pending' ORDER BY r.created_at ASC
    """).fetchall()

    all_reservations = conn.execute("""
        SELECT r.*, s.firstname, s.lastname, s.course
        FROM reservations r JOIN students s ON r.student_id=s.student_id
        ORDER BY r.id DESC
    """).fetchall()

    logs = conn.execute("""
        SELECT rl.*, s.firstname, s.lastname
        FROM reservation_logs rl LEFT JOIN students s ON rl.student_id=s.student_id
        ORDER BY rl.id DESC
    """).fetchall()

    tips = conn.execute("SELECT * FROM reservation_tips ORDER BY id DESC").fetchall()

    blocked_rows  = conn.execute("SELECT lab_room,date,time_slot FROM blocked_slots").fetchall()
    blocked_slots = {}
    for row in blocked_rows:
        key = row["lab_room"] + "|" + row["date"]
        blocked_slots.setdefault(key, []).append(row["time_slot"])

    unavail_rows    = conn.execute("SELECT lab_room, pc_number FROM unavailable_pcs").fetchall()
    unavailable_pcs = {}
    for row in unavail_rows:
        unavailable_pcs.setdefault(row["lab_room"], []).append(row["pc_number"])

    settings                = conn.execute("SELECT * FROM reservation_settings WHERE id=1").fetchone()
    reservations_open       = settings["is_open"] if settings else 1
    reservations_closed_msg = settings["disable_message"] if settings else ""

    pending_count = len(pending_reservations)
    conn.close()

    return render_template("AdminPage/reservation.html",
                           active="reservation",
                           pending_reservations=pending_reservations,
                           all_reservations=all_reservations,
                           logs=logs, tips=tips,
                           blocked_slots=blocked_slots,
                           unavailable_pcs=unavailable_pcs,
                           reservations_open=reservations_open,
                           reservations_closed_msg=reservations_closed_msg,
                           pending_count=pending_count,
                           today=date.today().isoformat())


# ── Admin: Reservation Action ─────────────────────────────────────────────────
@app.route("/admin/reservation/<int:res_id>/action", methods=["POST"])
def admin_reservation_action(res_id):
    if not admin_required():
        return jsonify({"ok": False, "error": "Unauthorized"}), 401

    action  = request.form.get("action", "").strip()
    remarks = request.form.get("remarks", "").strip() or \
              ("Reservation approved." if action == "approve" else "")

    conn = get_db()
    res  = conn.execute("SELECT * FROM reservations WHERE id=?", (res_id,)).fetchone()
    if not res:
        conn.close()
        return jsonify({"ok": False, "error": "Reservation not found."}), 404

    new_status = "approved" if action == "approve" else "rejected"

    conn.execute("UPDATE reservations SET status=?, admin_remarks=? WHERE id=?",
                 (new_status, remarks, res_id))

    conn.execute("""
        INSERT INTO reservation_logs
        (reservation_id, student_id, lab_room, date, time_slot, pc_number,
         action, remarks, processed_by, action_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (res_id, res["student_id"], res["lab_room"], res["date"], res["time_slot"],
          res["pc_number"], new_status, remarks, ADMIN_USERNAME,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    if new_status == "approved":
        notif_title = "✅ Reservation Approved!"
        notif_msg   = (f"Your reservation for {res['lab_room']} on {res['date']} "
                       f"at {res['time_slot']} has been approved.")
    else:
        notif_title = "❌ Reservation Rejected"
        notif_msg   = (f"Your reservation for {res['lab_room']} on {res['date']} "
                       f"was rejected. Reason: {remarks}")

    conn.execute("""
        INSERT INTO notifications (student_id, title, message, is_read, created_at)
        VALUES (?, ?, ?, 0, ?)
    """, (res["student_id"], notif_title, notif_msg,
          datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()

    pending_count = conn.execute(
        "SELECT COUNT(*) FROM reservations WHERE status='pending'"
    ).fetchone()[0]

    conn.close()

    return jsonify({
        "ok":            True,
        "new_status":    new_status,
        "res_id":        res_id,
        "pending_count": pending_count,
    })


@app.route("/admin/schedule/toggle", methods=["POST"])
def admin_schedule_toggle():
    if not admin_required(): return redirect(url_for("login"))
    lab_room  = request.form.get("lab_room", "").strip()
    date_val  = request.form.get("date", "").strip()
    time_slot = request.form.get("time_slot", "").strip()
    action    = request.form.get("action", "block")
    conn      = get_db()
    if action == "block":
        try:
            conn.execute(
                "INSERT INTO blocked_slots (lab_room,date,time_slot) VALUES (?,?,?)",
                (lab_room, date_val, time_slot))
        except sqlite3.IntegrityError:
            pass
    else:
        conn.execute(
            "DELETE FROM blocked_slots WHERE lab_room=? AND date=? AND time_slot=?",
            (lab_room, date_val, time_slot))
    conn.commit(); conn.close()
    flash(f"Slot {'blocked' if action == 'block' else 'unblocked'} successfully.", "success")
    return redirect(url_for("admin_reservation") + "#schedule")

@app.route("/admin/tips/post", methods=["POST"])
def admin_post_tip():
    if not admin_required(): return redirect(url_for("login"))
    icon    = request.form.get("icon", "💡").strip()
    message = request.form.get("message", "").strip()
    if not message:
        flash("Tip message is required.", "error")
        return redirect(url_for("admin_reservation"))
    conn = get_db()
    conn.execute("INSERT INTO reservation_tips (icon,message,created_at) VALUES (?,?,?)",
                 (icon, message, datetime.now().strftime("%Y-%m-%d")))
    conn.commit(); conn.close()
    flash("Tip posted successfully!", "success")
    return redirect(url_for("admin_reservation"))

@app.route("/admin/tips/delete/<int:tip_id>", methods=["POST"])
def admin_delete_tip(tip_id):
    if not admin_required(): return redirect(url_for("login"))
    conn = get_db()
    conn.execute("DELETE FROM reservation_tips WHERE id=?", (tip_id,))
    conn.commit(); conn.close()
    flash("Tip deleted.", "success")
    return redirect(url_for("admin_reservation"))

@app.route("/admin/pc/toggle", methods=["POST"])
def admin_pc_toggle():
    if not admin_required(): return redirect(url_for("login"))
    lab_room  = request.form.get("lab_room", "").strip()
    pc_number = int(request.form.get("pc_number", 0))
    action    = request.form.get("action", "block")
    conn      = get_db()
    if action == "block":
        try:
            conn.execute(
                "INSERT INTO unavailable_pcs (lab_room, pc_number) VALUES (?,?)",
                (lab_room, pc_number))
        except sqlite3.IntegrityError:
            pass
    else:
        conn.execute(
            "DELETE FROM unavailable_pcs WHERE lab_room=? AND pc_number=?",
            (lab_room, pc_number))
    conn.commit(); conn.close()
    flash(f"PC {pc_number} in {lab_room} "
          f"{'blocked' if action == 'block' else 'unblocked'}.", "success")
    return redirect(url_for("admin_reservation"))

@app.route("/admin/reservation/toggle", methods=["POST"])
def admin_reservation_toggle():
    if not admin_required(): return redirect(url_for("login"))
    action  = request.form.get("action", "enable")
    message = request.form.get("disable_message", "").strip()
    is_open = 1 if action == "enable" else 0
    conn    = get_db()
    conn.execute(
        "UPDATE reservation_settings SET is_open=?, disable_message=? WHERE id=1",
        (is_open, message if not is_open else None))
    conn.commit(); conn.close()
    flash(f"Reservations {'enabled' if is_open else 'disabled'}.", "success")
    return redirect(url_for("admin_reservation"))

# ── Admin: Analytics ──────────────────────────────────────────────────────────
@app.route("/admin/analytics")
def admin_analytics():
    if not admin_required(): return redirect(url_for("login"))

    date_from  = request.args.get("date_from", "").strip()
    date_to    = request.args.get("date_to", "").strip()
    lab_filter = request.args.get("lab_filter", "").strip()

    conn = get_db()

    where  = "WHERE ss.status='done'"
    params = []
    if date_from:  where += " AND DATE(ss.time_in)>=?"; params.append(date_from)
    if date_to:    where += " AND DATE(ss.time_in)<=?"; params.append(date_to)
    if lab_filter: where += " AND ss.lab_room=?";       params.append(lab_filter)

    records = conn.execute(f"""
        SELECT ss.*, s.firstname, s.lastname, s.course
        FROM sitin_sessions ss JOIN students s ON ss.student_id=s.student_id
        {where} ORDER BY ss.time_in
    """, params).fetchall()

    total_sessions  = len(records)
    unique_students = len(set(r["student_id"] for r in records))

    durations = []
    for r in records:
        if r["time_in"] and r["time_out"]:
            try:
                fmt  = "%Y-%m-%d %H:%M:%S"
                diff = (datetime.strptime(r["time_out"], fmt) -
                        datetime.strptime(r["time_in"],  fmt)).total_seconds() / 60
                if 0 < diff < 600:
                    durations.append(diff)
            except: pass
    avg_duration = round(sum(durations) / len(durations)) if durations else 0

    total_reservations    = conn.execute("SELECT COUNT(*) FROM reservations").fetchone()[0]
    approved_reservations = conn.execute(
        "SELECT COUNT(*) FROM reservations WHERE status IN ('approved','used')"
    ).fetchone()[0]
    total_feedback = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]

    trend_raw = defaultdict(int)
    for r in records:
        day = r["time_in"][:10] if r["time_in"] else None
        if day: trend_raw[day] += 1
    trend_labels = sorted(trend_raw.keys())[-30:]
    trend_values = [trend_raw[d] for d in trend_labels]

    purpose_data = defaultdict(int)
    lab_data     = defaultdict(int)
    course_data  = defaultdict(int)
    for r in records:
        purpose_data[r["purpose"]]            += 1
        lab_data[r["lab_room"]]               += 1
        course_data[r["course"] or "Unknown"] += 1

    hour_data = defaultdict(int)
    for r in records:
        if r["time_in"]:
            try: hour_data[int(r["time_in"][11:13])] += 1
            except: pass

    DAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    weekday_data = defaultdict(int)
    for r in records:
        if r["time_in"]:
            try:
                dt = datetime.strptime(r["time_in"][:10], "%Y-%m-%d")
                weekday_data[DAYS[dt.weekday()]] += 1
            except: pass

    DAY_SHORT = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]
    heatmap_data = {d: {} for d in DAY_SHORT}
    for r in records:
        if r["time_in"]:
            try:
                dt  = datetime.strptime(r["time_in"][:10], "%Y-%m-%d")
                day = DAY_SHORT[dt.weekday()]
                hr  = int(r["time_in"][11:13])
                heatmap_data[day][hr] = heatmap_data[day].get(hr, 0) + 1
            except: pass

    res_rows   = conn.execute(
        "SELECT status, COUNT(*) as cnt FROM reservations GROUP BY status"
    ).fetchall()
    res_status = {row["status"]: row["cnt"] for row in res_rows}

    top_rows = conn.execute(f"""
        SELECT ss.student_id, s.firstname, s.lastname, s.course,
               COUNT(ss.id) AS session_count
        FROM sitin_sessions ss JOIN students s ON ss.student_id=s.student_id
        {where}
        GROUP BY ss.student_id ORDER BY session_count DESC LIMIT 8
    """, params).fetchall()
    top_students = [dict(r) for r in top_rows]

    snapshots = conn.execute(
        "SELECT * FROM analytics_snapshots ORDER BY id DESC LIMIT 20"
    ).fetchall()

    conn.close()

    return render_template("AdminPage/analytics.html",
        active="analytics",
        date_from=date_from, date_to=date_to, lab_filter=lab_filter,
        total_sessions=total_sessions,
        unique_students=unique_students,
        avg_duration=avg_duration,
        total_reservations=total_reservations,
        approved_reservations=approved_reservations,
        total_feedback=total_feedback,
        trend_labels=trend_labels,
        trend_values=trend_values,
        purpose_data=dict(purpose_data),
        lab_data=dict(lab_data),
        course_data=dict(course_data),
        hour_data=dict(hour_data),
        weekday_data=dict(weekday_data),
        heatmap_data=heatmap_data,
        res_status=res_status,
        top_students=top_students,
        snapshots=snapshots,
    )

ALL_LABS = ['Lab 524', 'Lab 526', 'Lab 528', 'Lab 530', 'Lab 542', 'Lab 544']


@app.route("/admin/lab-software")
def admin_lab_software():
    if not admin_required():
        return redirect(url_for("login"))

    conn         = get_db()
    settings     = conn.execute("SELECT is_published FROM lab_software_settings WHERE id=1").fetchone()
    is_published = settings["is_published"] if settings else 0
    software     = conn.execute("SELECT * FROM lab_software ORDER BY lab, category, name").fetchall()
    conn.close()

    labs_data = {lab: [] for lab in ALL_LABS}
    for sw in software:
        if sw["lab"] in labs_data:
            labs_data[sw["lab"]].append(sw)

    return render_template(
        "AdminPage/lab_software_admin_tab.html",
        active       = "lab_software",
        is_published = is_published,
        ALL_LABS     = ALL_LABS,
        labs_data    = labs_data
    )


@app.route("/student/lab-software")
def student_lab_software():
    if "student_id" not in session:
        return redirect(url_for("login"))

    conn         = get_db()
    settings     = conn.execute("SELECT is_published FROM lab_software_settings WHERE id=1").fetchone()
    is_published = settings["is_published"] if settings else 0
    grouped      = {lab: [] for lab in ALL_LABS}

    if is_published:
        for sw in conn.execute("SELECT * FROM lab_software ORDER BY lab, name").fetchall():
            if sw["lab"] in grouped:
                grouped[sw["lab"]].append(sw)
    conn.close()

    return render_template(
        "StudentPage/lab_software_student.html",
        student          = session,
        ALL_LABS         = ALL_LABS,
        grouped_software = grouped,
        is_published     = is_published
    )

@app.route("/admin/lab-software/publish", methods=["POST"])
def admin_lab_software_publish():
    if not admin_required():
        return redirect(url_for("login"))
    conn     = get_db()
    current  = conn.execute("SELECT is_published FROM lab_software_settings WHERE id=1").fetchone()
    new_state = 0 if (current and current["is_published"]) else 1
    conn.execute("UPDATE lab_software_settings SET is_published=? WHERE id=1", (new_state,))
    conn.commit(); conn.close()
    flash(f"Lab software {'published to' if new_state else 'hidden from'} students.", "success")
    return redirect(url_for("admin_lab_software"))


@app.route("/admin/lab-software/delete/<int:sw_id>", methods=["POST"])
def admin_lab_software_delete(sw_id):
    if not admin_required():
        return redirect(url_for("login"))
    conn = get_db()
    sw   = conn.execute("SELECT name, lab FROM lab_software WHERE id=?", (sw_id,)).fetchone()
    if sw:
        conn.execute("DELETE FROM lab_software WHERE id=?", (sw_id,))
        conn.commit()
        flash(f'"{sw["name"]}" removed from {sw["lab"]}.', "success")
    conn.close()
    return redirect(url_for("admin_lab_software"))

@app.route("/admin/lab-software/add", methods=["POST"])
def admin_lab_software_add():
    if not admin_required():
        return redirect(url_for("login"))
    lab      = request.form.get("lab", "").strip()
    name     = request.form.get("name", "").strip()
    version  = request.form.get("version", "").strip()
    category = request.form.get("category", "TOOL").strip()
    if not lab or not name:
        flash("Lab and name are required.", "error")
        return redirect(url_for("admin_lab_software"))
    conn = get_db()
    conn.execute("INSERT INTO lab_software (lab, name, version, category) VALUES (?,?,?,?)",
                 (lab, name, version or None, category))
    conn.commit(); conn.close()
    flash(f'"{name}" added to {lab}.', "success")
    return redirect(url_for("admin_lab_software"))

# ── Admin: Logout ─────────────────────────────────────────────────────────────
@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("login"))

# ══════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    app.run(debug=True)
