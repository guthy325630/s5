#!/usr/bin/env python3
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, flash, redirect, render_template, request, session, url_for


APP_SECRET = os.environ.get("SOCKS5_ADMIN_SECRET", "change-me")
DB_PATH = os.environ.get("SOCKS5_ADMIN_DB", "/var/lib/socks5-admin/admin.db")
CONFIG_FILE = os.environ.get("SOCKS5_CONFIG_FILE", "/etc/sing-box/config.json")
CRED_FILE = os.environ.get("SOCKS5_ADMIN_CRED_FILE", "/var/lib/socks5-admin/admin.credentials")
COLLECT_INTERVAL = int(os.environ.get("SOCKS5_COLLECT_INTERVAL_SEC", "60"))

app = Flask(__name__)
app.secret_key = APP_SECRET


def utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def db_conn():
    ensure_parent_dir(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(db_conn()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                remark TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                total_up INTEGER NOT NULL DEFAULT 0,
                total_down INTEGER NOT NULL DEFAULT 0,
                total_duration INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                src_ip TEXT DEFAULT '',
                start_at TEXT NOT NULL,
                end_at TEXT,
                duration_sec INTEGER NOT NULL DEFAULT 0,
                bytes_up INTEGER NOT NULL DEFAULT 0,
                bytes_down INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS admin_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS login_guard (
                ip TEXT PRIMARY KEY,
                fail_count INTEGER NOT NULL DEFAULT 0,
                first_fail_at TEXT,
                locked_until TEXT
            );

            CREATE TABLE IF NOT EXISTS traffic_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                day TEXT NOT NULL,
                bytes_up INTEGER NOT NULL DEFAULT 0,
                bytes_down INTEGER NOT NULL DEFAULT 0,
                duration_sec INTEGER NOT NULL DEFAULT 0,
                conn_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, day),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            """
        )
        # 兼容旧表，补充 conn_key 字段用于更精确的连接会话识别
        cols = conn.execute("PRAGMA table_info(sessions)").fetchall()
        col_names = {c["name"] for c in cols}
        if "conn_key" not in col_names:
            conn.execute("ALTER TABLE sessions ADD COLUMN conn_key TEXT DEFAULT ''")
        conn.commit()


def log_action(action: str, detail: str):
    with closing(db_conn()) as conn:
        conn.execute(
            "INSERT INTO admin_logs(action, detail, created_at) VALUES (?, ?, ?)",
            (action, detail, utc_now()),
        )
        conn.commit()


def sync_users_to_singbox():
    if not os.path.exists(CONFIG_FILE):
        return "未找到 sing-box 配置文件"

    with closing(db_conn()) as conn:
        users = conn.execute(
            "SELECT username, password FROM users WHERE status='active' ORDER BY id ASC"
        ).fetchall()

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    inbounds = cfg.get("inbounds", [])
    socks_inbound = None
    for inbound in inbounds:
        if inbound.get("type") == "socks":
            socks_inbound = inbound
            break

    if socks_inbound is None:
        return "未找到 type=socks 的 inbound"

    socks_inbound["users"] = [{"username": u["username"], "password": u["password"]} for u in users]

    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    proc = subprocess.run(
        ["systemctl", "restart", "sing-box.service"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return f"已写入配置，但重启失败: {proc.stderr.strip()}"
    return "已同步并重启 sing-box"


def ensure_admin_cred_file():
    ensure_parent_dir(CRED_FILE)
    if os.path.exists(CRED_FILE):
        return
    admin_user = os.environ.get("SOCKS5_ADMIN_USER", "admin")
    admin_pass = os.environ.get("SOCKS5_ADMIN_PASS", "admin123")
    with open(CRED_FILE, "w", encoding="utf-8") as f:
        f.write(f"{admin_user}:{admin_pass}\n")
    os.chmod(CRED_FILE, 0o600)


def read_admin_cred():
    ensure_admin_cred_file()
    try:
        with open(CRED_FILE, "r", encoding="utf-8") as f:
            line = f.readline().strip()
        if ":" not in line:
            return "admin", "admin123"
        user, pwd = line.split(":", 1)
        user = user.strip() or "admin"
        pwd = pwd.strip() or "admin123"
        return user, pwd
    except Exception:
        return "admin", "admin123"


def write_admin_cred(user: str, pwd: str):
    ensure_parent_dir(CRED_FILE)
    with open(CRED_FILE, "w", encoding="utf-8") as f:
        f.write(f"{user}:{pwd}\n")
    os.chmod(CRED_FILE, 0o600)


def _get_meta(key: str):
    with closing(db_conn()) as conn:
        row = conn.execute("SELECT value FROM app_meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def _set_meta(key: str, value: str):
    with closing(db_conn()) as conn:
        conn.execute(
            """
            INSERT INTO app_meta(key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (key, value),
        )
        conn.commit()


def _fmt_day():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _upsert_daily(conn, user_id: int, day: str, add_up: int, add_down: int, add_dur: int, add_conn: int):
    now = utc_now()
    row = conn.execute(
        "SELECT id FROM traffic_daily WHERE user_id=? AND day=?",
        (user_id, day),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO traffic_daily(user_id, day, bytes_up, bytes_down, duration_sec, conn_count, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, day, max(add_up, 0), max(add_down, 0), max(add_dur, 0), max(add_conn, 0), now, now),
        )
    else:
        conn.execute(
            """
            UPDATE traffic_daily
            SET bytes_up=bytes_up+?, bytes_down=bytes_down+?, duration_sec=duration_sec+?, conn_count=conn_count+?, updated_at=?
            WHERE id=?
            """,
            (max(add_up, 0), max(add_down, 0), max(add_dur, 0), max(add_conn, 0), now, row["id"]),
        )


def _snapshot_daily_from_users():
    key = "daily_last_totals"
    raw = _get_meta(key) or "{}"
    try:
        old = json.loads(raw)
    except Exception:
        old = {}

    day = _fmt_day()
    with closing(db_conn()) as conn:
        users = conn.execute("SELECT id, total_up, total_down, total_duration FROM users").fetchall()
        new_cache = {}
        for u in users:
            uid = str(u["id"])
            prev = old.get(uid, {})
            last_up = int(prev.get("up", 0))
            last_down = int(prev.get("down", 0))
            last_dur = int(prev.get("dur", 0))
            add_up = int(u["total_up"]) - last_up
            add_down = int(u["total_down"]) - last_down
            add_dur = int(u["total_duration"]) - last_dur
            if add_up > 0 or add_down > 0 or add_dur > 0:
                _upsert_daily(conn, int(uid), day, add_up, add_down, add_dur, 0)
            new_cache[uid] = {
                "up": int(u["total_up"]),
                "down": int(u["total_down"]),
                "dur": int(u["total_duration"]),
            }
        conn.commit()

    _set_meta(key, json.dumps(new_cache, ensure_ascii=False))


def _parse_log_line(line: str):
    username = None
    src_ip = None
    up = 0
    down = 0
    close_event = False

    u_patterns = [
        r'username[=:" ]+([A-Za-z0-9._@-]+)',
        r'user[=:" ]+([A-Za-z0-9._@-]+)',
    ]
    for p in u_patterns:
        m = re.search(p, line, re.IGNORECASE)
        if m:
            username = m.group(1)
            break

    ip_patterns = [
        r'from[=:" ]+([0-9a-fA-F\.:]+)',
        r'src[=:" ]+([0-9a-fA-F\.:]+)',
        r'([0-9]{1,3}(?:\.[0-9]{1,3}){3})',
    ]
    for p in ip_patterns:
        m = re.search(p, line, re.IGNORECASE)
        if m:
            src_ip = m.group(1)
            break

    m_up = re.search(r'(?:up|upload|uplink)[=:" ]+([0-9]+)', line, re.IGNORECASE)
    m_down = re.search(r'(?:down|download|downlink)[=:" ]+([0-9]+)', line, re.IGNORECASE)
    if m_up:
        up = int(m_up.group(1))
    if m_down:
        down = int(m_down.group(1))

    if re.search(r'close|closed|disconnect|EOF', line, re.IGNORECASE):
        close_event = True

    open_event = bool(re.search(r"accept|accepted|open|new connection|inbound connection", line, re.IGNORECASE))
    conn_key = None
    m_conn = re.search(r'(?:conn|connection|id)[=:" ]+([A-Za-z0-9._:-]+)', line, re.IGNORECASE)
    if m_conn:
        conn_key = m_conn.group(1)
    return username, src_ip, up, down, close_event, open_event, conn_key


def collect_metrics_from_logs():
    last_cursor = _get_meta("journal_cursor")
    cmd = ["journalctl", "-u", "sing-box.service", "--no-pager", "-o", "json"]
    if last_cursor:
        cmd.extend(["--after-cursor", last_cursor])
    else:
        cmd.extend(["-n", "2000"])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return f"采集失败: {proc.stderr.strip() or 'journalctl 返回非0'}"

    lines = [x.strip() for x in proc.stdout.splitlines() if x.strip()]
    newest_cursor = last_cursor
    touched = 0
    now = utc_now()

    with closing(db_conn()) as conn:
        for line in lines:
            try:
                obj = json.loads(line)
            except Exception:
                continue
            msg = str(obj.get("MESSAGE", "")).strip()
            if not msg:
                continue
            if "__CURSOR" in obj:
                newest_cursor = obj["__CURSOR"]

            username, src_ip, up, down, close_event, open_event, conn_key = _parse_log_line(msg)
            if not username:
                continue
            user = conn.execute(
                "SELECT id, total_up, total_down, total_duration FROM users WHERE username=?",
                (username,),
            ).fetchone()
            if user is None:
                continue

            key = conn_key or f"{username}@{src_ip or 'unknown'}"

            if close_event:
                s = conn.execute(
                    """
                    SELECT id, start_at, bytes_up, bytes_down FROM sessions
                    WHERE user_id=? AND end_at IS NULL AND conn_key=?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (user["id"], key),
                ).fetchone()
                if s is None:
                    s = conn.execute(
                        """
                        SELECT id, start_at, bytes_up, bytes_down FROM sessions
                        WHERE user_id=? AND end_at IS NULL
                        ORDER BY id DESC LIMIT 1
                        """,
                        (user["id"],),
                    ).fetchone()
                if s is not None:
                    start_dt = datetime.strptime(s["start_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                    dur = int((datetime.now(timezone.utc) - start_dt).total_seconds())
                    conn.execute(
                        """
                        UPDATE sessions SET end_at=?, duration_sec=?, bytes_up=?, bytes_down=?
                        WHERE id=?
                        """,
                        (now, max(dur, 0), s["bytes_up"] + up, s["bytes_down"] + down, s["id"]),
                    )
                    conn.execute(
                        """
                        UPDATE users
                        SET total_up=total_up+?, total_down=total_down+?, total_duration=total_duration+?, updated_at=?
                        WHERE id=?
                        """,
                        (up, down, max(dur, 0), now, user["id"]),
                    )
                    _upsert_daily(conn, user["id"], _fmt_day(), up, down, max(dur, 0), 0)
                    touched += 1
            else:
                opened = conn.execute(
                    """
                    SELECT id FROM sessions
                    WHERE user_id=? AND end_at IS NULL AND conn_key=?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (user["id"], key),
                ).fetchone()
                if opened is None and open_event:
                    conn.execute(
                        "INSERT INTO sessions(user_id, src_ip, start_at, conn_key) VALUES (?, ?, ?, ?)",
                        (user["id"], src_ip or "", now, key),
                    )
                    _upsert_daily(conn, user["id"], _fmt_day(), 0, 0, 0, 1)
                    touched += 1
                elif opened is not None and (up > 0 or down > 0):
                    conn.execute(
                        """
                        UPDATE sessions SET bytes_up=bytes_up+?, bytes_down=bytes_down+?
                        WHERE id=?
                        """,
                        (up, down, opened["id"]),
                    )
                    conn.execute(
                        "UPDATE users SET total_up=total_up+?, total_down=total_down+?, updated_at=? WHERE id=?",
                        (up, down, now, user["id"]),
                    )
                    _upsert_daily(conn, user["id"], _fmt_day(), up, down, 0, 0)
                    touched += 1

        conn.commit()

    if newest_cursor and newest_cursor != last_cursor:
        _set_meta("journal_cursor", newest_cursor)
    _snapshot_daily_from_users()
    return f"采集完成，更新 {touched} 条记录"


def _parse_dt(raw: str):
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _is_locked(ip: str):
    with closing(db_conn()) as conn:
        row = conn.execute("SELECT locked_until FROM login_guard WHERE ip=?", (ip,)).fetchone()
    if row is None or not row["locked_until"]:
        return False
    lock_until = _parse_dt(row["locked_until"])
    return bool(lock_until and datetime.now(timezone.utc) < lock_until)


def _record_login_fail(ip: str):
    now = datetime.now(timezone.utc)
    now_s = now.strftime("%Y-%m-%d %H:%M:%S")
    with closing(db_conn()) as conn:
        row = conn.execute(
            "SELECT fail_count, first_fail_at FROM login_guard WHERE ip=?",
            (ip,),
        ).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO login_guard(ip, fail_count, first_fail_at, locked_until) VALUES (?, 1, ?, '')",
                (ip, now_s),
            )
            conn.commit()
            return
        first_fail = _parse_dt(row["first_fail_at"])
        fail_count = int(row["fail_count"])
        if first_fail is None or now - first_fail > timedelta(minutes=15):
            fail_count = 1
            first_fail = now
        else:
            fail_count += 1
        locked_until = ""
        if fail_count >= 5:
            locked_until = (now + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE login_guard SET fail_count=?, first_fail_at=?, locked_until=? WHERE ip=?",
            (fail_count, first_fail.strftime("%Y-%m-%d %H:%M:%S"), locked_until, ip),
        )
        conn.commit()


def _clear_login_guard(ip: str):
    with closing(db_conn()) as conn:
        conn.execute("DELETE FROM login_guard WHERE ip=?", (ip,))
        conn.commit()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "admin" not in session:
            return redirect(url_for("login"))
        return fn(*args, **kwargs)

    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    ip = (request.headers.get("X-Forwarded-For", "") or request.remote_addr or "").split(",")[0].strip() or "unknown"
    if _is_locked(ip):
        flash("登录失败次数过多，请15分钟后重试")
        return render_template("login.html")

    if request.method == "POST":
        user = request.form.get("username", "").strip()
        pwd = request.form.get("password", "").strip()
        admin_user, admin_pass = read_admin_cred()
        if user == admin_user and pwd == admin_pass:
            session["admin"] = admin_user
            _clear_login_guard(ip)
            return redirect(url_for("dashboard"))
        _record_login_fail(ip)
        flash("账号或密码错误")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def dashboard():
    with closing(db_conn()) as conn:
        user_count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        banned_count = conn.execute("SELECT COUNT(*) c FROM users WHERE status='banned'").fetchone()["c"]
        active_session_count = conn.execute("SELECT COUNT(*) c FROM sessions WHERE end_at IS NULL").fetchone()["c"]
        traffic = conn.execute(
            "SELECT COALESCE(SUM(total_up + total_down), 0) t FROM users"
        ).fetchone()["t"]
        recent_logs = conn.execute(
            "SELECT action, detail, created_at FROM admin_logs ORDER BY id DESC LIMIT 20"
        ).fetchall()

    return render_template(
        "dashboard.html",
        user_count=user_count,
        banned_count=banned_count,
        active_session_count=active_session_count,
        traffic=traffic,
        recent_logs=recent_logs,
    )


@app.route("/reports")
@login_required
def reports():
    try:
        days = int(request.args.get("days", "7"))
    except ValueError:
        days = 7
    if days not in (7, 30):
        days = 7

    selected_user = request.args.get("user_id", "all").strip()
    where_sql = ""
    params = []
    if selected_user != "all" and selected_user.isdigit():
        where_sql = "WHERE td.user_id=?"
        params.append(int(selected_user))

    with closing(db_conn()) as conn:
        users = conn.execute("SELECT id, username FROM users ORDER BY username ASC").fetchall()
        daily_rows = conn.execute(
            f"""
            SELECT td.day, u.username, td.bytes_up, td.bytes_down, td.duration_sec, td.conn_count
            FROM traffic_daily td
            JOIN users u ON u.id = td.user_id
            {where_sql}
            ORDER BY td.day DESC, (td.bytes_up + td.bytes_down) DESC
            LIMIT ?
            """,
            (*params, 500),
        ).fetchall()

        trend_rows = conn.execute(
            f"""
            SELECT td.day, SUM(td.bytes_up + td.bytes_down) AS total_traffic
            FROM traffic_daily td
            {where_sql}
            GROUP BY td.day
            ORDER BY td.day DESC
            LIMIT ?
            """,
            (*params, days),
        ).fetchall()

    trend_rows = list(reversed(trend_rows))
    trend_days = [r["day"] for r in trend_rows]
    trend_values = [int(r["total_traffic"] or 0) for r in trend_rows]
    return render_template(
        "reports.html",
        users=users,
        selected_user=selected_user,
        days=days,
        daily_rows=daily_rows,
        trend_days_json=json.dumps(trend_days, ensure_ascii=False),
        trend_values_json=json.dumps(trend_values),
    )


@app.route("/collect", methods=["POST"])
@login_required
def collect():
    msg = collect_metrics_from_logs()
    flash(msg)
    log_action("collect_metrics", msg)
    return redirect(url_for("dashboard"))


@app.route("/admin/account", methods=["POST"])
@login_required
def update_admin_account():
    old_password = request.form.get("old_password", "").strip()
    new_user = request.form.get("new_username", "").strip()
    new_password = request.form.get("new_password", "").strip()
    confirm_password = request.form.get("confirm_password", "").strip()
    current_user, current_pass = read_admin_cred()

    if old_password != current_pass:
        flash("旧密码错误")
        return redirect(url_for("dashboard"))
    if not new_user or not new_password:
        flash("新账号和新密码不能为空")
        return redirect(url_for("dashboard"))
    if len(new_password) < 8:
        flash("新密码至少8位")
        return redirect(url_for("dashboard"))
    if new_password != confirm_password:
        flash("两次输入的新密码不一致")
        return redirect(url_for("dashboard"))

    write_admin_cred(new_user, new_password)
    session["admin"] = new_user
    log_action("update_admin_account", f"{current_user} -> {new_user}")
    flash("管理员账号密码已更新")
    return redirect(url_for("dashboard"))


@app.route("/users")
@login_required
def users():
    with closing(db_conn()) as conn:
        rows = conn.execute(
            """
            SELECT
              u.*,
              (SELECT COUNT(*) FROM sessions s WHERE s.user_id = u.id AND s.end_at IS NULL) AS online_count
            FROM users u
            ORDER BY u.id DESC
            """
        ).fetchall()
    return render_template("users.html", users=rows)


@app.route("/users/create", methods=["POST"])
@login_required
def create_user():
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    remark = request.form.get("remark", "").strip()
    if not username or not password:
        flash("用户名和密码不能为空")
        return redirect(url_for("users"))

    now = utc_now()
    try:
        with closing(db_conn()) as conn:
            conn.execute(
                """
                INSERT INTO users(username, password, remark, status, created_at, updated_at)
                VALUES (?, ?, ?, 'active', ?, ?)
                """,
                (username, password, remark, now, now),
            )
            conn.commit()
        msg = sync_users_to_singbox()
        log_action("create_user", f"{username} ({msg})")
    except sqlite3.IntegrityError:
        flash("用户名已存在")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/remark", methods=["POST"])
@login_required
def update_remark(user_id: int):
    remark = request.form.get("remark", "").strip()
    with closing(db_conn()) as conn:
        row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            flash("用户不存在")
            return redirect(url_for("users"))
        conn.execute(
            "UPDATE users SET remark=?, updated_at=? WHERE id=?",
            (remark, utc_now(), user_id),
        )
        conn.commit()
    log_action("update_remark", f"{row['username']} -> {remark}")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/ban", methods=["POST"])
@login_required
def ban_user(user_id: int):
    with closing(db_conn()) as conn:
        row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            flash("用户不存在")
            return redirect(url_for("users"))
        conn.execute(
            "UPDATE users SET status='banned', updated_at=? WHERE id=?",
            (utc_now(), user_id),
        )
        conn.commit()
    msg = sync_users_to_singbox()
    log_action("ban_user", f"{row['username']} ({msg})")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/unban", methods=["POST"])
@login_required
def unban_user(user_id: int):
    with closing(db_conn()) as conn:
        row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            flash("用户不存在")
            return redirect(url_for("users"))
        conn.execute(
            "UPDATE users SET status='active', updated_at=? WHERE id=?",
            (utc_now(), user_id),
        )
        conn.commit()
    msg = sync_users_to_singbox()
    log_action("unban_user", f"{row['username']} ({msg})")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id: int):
    with closing(db_conn()) as conn:
        row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        if row is None:
            flash("用户不存在")
            return redirect(url_for("users"))
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        conn.commit()
    msg = sync_users_to_singbox()
    log_action("delete_user", f"{row['username']} ({msg})")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/sessions")
@login_required
def user_sessions(user_id: int):
    with closing(db_conn()) as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if user is None:
            flash("用户不存在")
            return redirect(url_for("users"))
        rows = conn.execute(
            "SELECT * FROM sessions WHERE user_id=? ORDER BY id DESC LIMIT 200",
            (user_id,),
        ).fetchall()
    return render_template("sessions.html", user=user, sessions=rows)


def bootstrap_users_from_singbox():
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return

    socks_inbound = None
    for inbound in cfg.get("inbounds", []):
        if inbound.get("type") == "socks":
            socks_inbound = inbound
            break

    if not socks_inbound:
        return

    now = utc_now()
    with closing(db_conn()) as conn:
        for item in socks_inbound.get("users", []):
            uname = str(item.get("username", "")).strip()
            pwd = str(item.get("password", "")).strip()
            if not uname or not pwd:
                continue
            exists = conn.execute("SELECT id FROM users WHERE username=?", (uname,)).fetchone()
            if exists is None:
                conn.execute(
                    """
                    INSERT INTO users(username, password, remark, status, created_at, updated_at)
                    VALUES (?, ?, '', 'active', ?, ?)
                    """,
                    (uname, pwd, now, now),
                )
        conn.commit()


def create_app():
    init_db()
    ensure_admin_cred_file()
    bootstrap_users_from_singbox()
    _snapshot_daily_from_users()

    def _collector_loop():
        while True:
            try:
                collect_metrics_from_logs()
            except Exception:
                pass
            time.sleep(max(15, COLLECT_INTERVAL))

    t = threading.Thread(target=_collector_loop, daemon=True)
    t.start()
    return app


if __name__ == "__main__":
    create_app()
    host = os.environ.get("SOCKS5_ADMIN_HOST", "0.0.0.0")
    port = int(os.environ.get("SOCKS5_ADMIN_PORT", "9580"))
    app.run(host=host, port=port)
