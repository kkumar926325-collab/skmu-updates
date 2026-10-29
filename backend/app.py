"""SKMU Updates - backend v2 (Flask + SQLite)

Sirf admin (aap) post kar sakte ho. Log post padh sakte hain aur sawal puchh sakte hain.

Run:  python app.py
"""
import glob
import os
import re
import secrets
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import Flask, abort, g, jsonify, request, send_file, send_from_directory

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("SKMU_DB", os.path.join(BASE, "skmu.db"))
KEY_FILE = os.path.join(BASE, "admin_key.txt")
UPLOAD_DIR = os.path.join(BASE, "uploads")
BACKUP_DIR = os.path.join(BASE, "backups")
STATIC_DIR = os.path.join(BASE, "static")
for _d in (UPLOAD_DIR, BACKUP_DIR):
    os.makedirs(_d, exist_ok=True)

# 0 = auto delete band. 7 = 7 din se purani (unpinned) posts apne aap hat jayengi.
AUTO_DELETE_DAYS = int(os.environ.get("SKMU_AUTO_DELETE_DAYS", "0"))

CATEGORIES = ["Admission", "Result", "Form", "Exam", "Notice", "Scholarship", "Other"]
COURSES = ["All", "BA", "BSc", "BCom", "BBA", "BCA", "B.Ed", "MA", "MSc", "MCom", "Other"]
SEMESTERS = ["All", "1", "2", "3", "4", "5", "6", "7", "8"]

MAX_IMG = 2_500_000
IMG_RE = re.compile(r"^[a-f0-9]{16}\.(jpg|png|webp)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
IST = timezone(timedelta(hours=5, minutes=30))

DEFAULT_SETTINGS = {
    "result_url": "",
    "contact": "",
    "about": (
        "SKMU Updates ek student-run (unofficial) app hai jahan SKMU Dumka se jude "
        "admission, result, form, exam aur notice ki jaankari ek jagah milti hai.\n\n"
        "Yahan di gayi jaankari official source se dekhkar daali jaati hai, phir bhi "
        "final confirm university ki official website se zaroor karein."
    ),
    "guide": (
        "ADMISSION KE LIYE AAM STEPS\n\n"
        "1. University ki official website par admission notification dekhein.\n"
        "2. Online form bharne ki last date note kar lein.\n"
        "3. Zaroori documents ready rakhein: marksheet, certificate, photo, signature, "
        "Aadhaar/ID, category certificate (agar ho).\n"
        "4. Form bharkar fees online jama karein aur receipt save rakhein.\n"
        "5. Form ka print ya PDF apne paas rakhein.\n\n"
        "Kisi bhi sawal ke liye kisi post me neeche sawal puchh sakte hain."
    ),
}

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 4 * 1024 * 1024


# ---------------------------------------------------------------- admin key
def load_admin_key():
    key = os.environ.get("SKMU_ADMIN_KEY")
    if key:
        return key.strip()
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            return f.read().strip()
    key = secrets.token_urlsafe(12)
    with open(KEY_FILE, "w", encoding="utf-8") as f:
        f.write(key)
    return key


ADMIN_KEY = load_admin_key()


def is_admin():
    k = request.headers.get("X-Admin-Key", "")
    return bool(k) and secrets.compare_digest(k.encode("utf-8"), ADMIN_KEY.encode("utf-8"))


def admin_only(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not is_admin():
            return jsonify(error="Admin key galat hai"), 401
        return fn(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------- database
SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'Other',
    link TEXT NOT NULL DEFAULT '',
    pinned INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    text TEXT NOT NULL,
    reply TEXT NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    replied_at INTEGER
);
CREATE INDEX IF NOT EXISTS idx_comments_post ON comments(post_id);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    first_seen INTEGER NOT NULL,
    last_seen INTEGER NOT NULL
);
"""

POST_COLS = [
    ("course", "TEXT NOT NULL DEFAULT 'All'"),
    ("semester", "TEXT NOT NULL DEFAULT 'All'"),
    ("due_date", "TEXT NOT NULL DEFAULT ''"),
    ("image", "TEXT NOT NULL DEFAULT ''"),
    ("edited_at", "INTEGER"),
]


def init_db():
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    have = {r[1] for r in con.execute("PRAGMA table_info(posts)")}
    for name, ddl in POST_COLS:
        if name not in have:
            con.execute("ALTER TABLE posts ADD COLUMN %s %s" % (name, ddl))
    have_c = {r[1] for r in con.execute("PRAGMA table_info(comments)")}
    if "reports" not in have_c:
        con.execute("ALTER TABLE comments ADD COLUMN reports INTEGER NOT NULL DEFAULT 0")
    con.commit()
    con.close()


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    d = g.pop("db", None)
    if d is not None:
        d.close()


POST_SELECT = (
    "SELECT p.*, (SELECT COUNT(*) FROM comments c WHERE c.post_id = p.id) AS comment_count "
    "FROM posts p"
)


def post_dict(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "body": row["body"],
        "category": row["category"],
        "course": row["course"],
        "semester": row["semester"],
        "due_date": row["due_date"],
        "image": row["image"],
        "link": row["link"],
        "pinned": bool(row["pinned"]),
        "created_at": int(row["created_at"]),
        "edited_at": row["edited_at"],
        "comment_count": row["comment_count"],
    }


def comment_dict(row):
    return {
        "id": row["id"],
        "name": row["name"],
        "text": row["text"],
        "reply": row["reply"],
        "created_at": int(row["created_at"]),
        "replied_at": row["replied_at"],
        "reports": row["reports"],
    }


def get_settings():
    s = dict(DEFAULT_SETTINGS)
    for r in db().execute("SELECT key, value FROM settings"):
        if r["key"] in s:
            s[r["key"]] = r["value"]
    return s


# ---------------------------------------------------------------- helpers
_hits = {}
_last_maint = 0


def client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() if fwd else (request.remote_addr or "?")


def too_many(key, limit=8, window=60):
    now = time.time()
    recent = [t for t in _hits.get(key, []) if now - t < window]
    if len(recent) >= limit:
        _hits[key] = recent
        return True
    recent.append(now)
    _hits[key] = recent
    return False


def today_ist():
    return datetime.now(IST).date()


def clean_link(value):
    value = (value or "").strip()
    if not value:
        return ""
    if not (value.startswith("http://") or value.startswith("https://")):
        return None
    return value[:500]


def clean_due(value):
    value = (value or "").strip()
    if not value:
        return ""
    if not DATE_RE.match(value):
        return None
    try:
        date.fromisoformat(value)
    except ValueError:
        return None
    return value


def sniff_image(data):
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return None


def remove_image(name):
    if name and IMG_RE.match(name):
        try:
            os.remove(os.path.join(UPLOAD_DIR, name))
        except OSError:
            pass


def make_backup():
    dest = os.path.join(BACKUP_DIR, "skmu-%s.db" % time.strftime("%Y%m%d-%H%M%S"))
    src = sqlite3.connect(DB_PATH)
    dst = sqlite3.connect(dest)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    for old in sorted(glob.glob(os.path.join(BACKUP_DIR, "skmu-*.db")))[:-7]:
        try:
            os.remove(old)
        except OSError:
            pass
    return dest


def purge_old(now):
    cutoff = int(now - AUTO_DELETE_DAYS * 86400)
    rows = db().execute("SELECT id, image FROM posts WHERE pinned = 0 AND created_at < ?", (cutoff,)).fetchall()
    for r in rows:
        remove_image(r["image"])
    db().execute("DELETE FROM posts WHERE pinned = 0 AND created_at < ?", (cutoff,))
    db().commit()


def clean_orphans(now):
    used = {r["image"] for r in db().execute("SELECT image FROM posts WHERE image != ''")}
    for name in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, name)
        if name not in used and now - os.path.getmtime(path) > 86400:
            remove_image(name)


@app.before_request
def maintenance():
    """Har ghante: purani posts hatao (agar on ho), roz backup, bekar images saaf."""
    global _last_maint
    now = time.time()
    if now - _last_maint < 3600:
        return
    _last_maint = now
    try:
        if AUTO_DELETE_DAYS > 0:
            purge_old(now)
        clean_orphans(now)
        files = sorted(glob.glob(os.path.join(BACKUP_DIR, "skmu-*.db")))
        if not files or now - os.path.getmtime(files[-1]) > 86400:
            make_backup()
    except Exception as exc:  # maintenance se request kabhi fail nahi honi chahiye
        print("maintenance error:", exc)


@app.after_request
def headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    if request.path in ("/", "/sw.js", "/manifest.json", "/privacy"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# ---------------------------------------------------------------- pages
@app.get("/")
def root():
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/sw.js")
def sw():
    resp = send_from_directory(STATIC_DIR, "sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.get("/manifest.json")
def manifest():
    return send_from_directory(STATIC_DIR, "manifest.json")


@app.get("/privacy")
def privacy():
    return send_from_directory(STATIC_DIR, "privacy.html")


@app.get("/uploads/<name>")
def uploads(name):
    if not IMG_RE.match(name):
        abort(404)
    return send_from_directory(UPLOAD_DIR, name, max_age=31536000)


# ---------------------------------------------------------------- public api
@app.get("/api/status")
def status():
    return jsonify(app="SKMU Updates", status="ok")


@app.get("/api/config")
def config():
    return jsonify(
        categories=CATEGORIES, courses=COURSES, semesters=SEMESTERS, settings=get_settings()
    )


@app.post("/api/ping")
def ping():
    if too_many("ping:" + client_ip(), limit=30):
        return jsonify(ok=True)
    did = str((request.get_json(silent=True) or {}).get("id", ""))
    if re.fullmatch(r"[A-Za-z0-9_-]{8,64}", did):
        now = int(time.time())
        db().execute(
            "INSERT INTO devices (id, first_seen, last_seen) VALUES (?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET last_seen = excluded.last_seen",
            (did, now, now),
        )
        db().commit()
    return jsonify(ok=True)


@app.get("/api/latest")
def latest():
    row = db().execute("SELECT id, title, category FROM posts ORDER BY id DESC LIMIT 1").fetchone()
    if row is None:
        return jsonify(id=0, title="", category="")
    return jsonify(id=row["id"], title=row["title"], category=row["category"])


@app.get("/api/posts")
def list_posts():
    cat = request.args.get("category", "").strip()
    course = request.args.get("course", "").strip()
    sem = request.args.get("semester", "").strip()
    q = request.args.get("q", "").strip()
    try:
        offset = max(0, int(request.args.get("offset", 0)))
    except ValueError:
        offset = 0

    sql = POST_SELECT + " WHERE 1=1"
    args = []
    if cat and cat != "All":
        sql += " AND p.category = ?"
        args.append(cat)
    if course and course != "All":
        sql += " AND (p.course = ? OR p.course = 'All')"
        args.append(course)
    if sem and sem != "All":
        sql += " AND (p.semester = ? OR p.semester = 'All')"
        args.append(sem)
    if q:
        sql += " AND (p.title LIKE ? OR p.body LIKE ?)"
        like = "%" + q + "%"
        args += [like, like]
    sql += " ORDER BY p.pinned DESC, p.created_at DESC LIMIT 50 OFFSET ?"
    args.append(offset)

    rows = db().execute(sql, args).fetchall()
    return jsonify(posts=[post_dict(r) for r in rows])


@app.get("/api/dates")
def upcoming_dates():
    today = today_ist().isoformat()
    rows = db().execute(
        POST_SELECT + " WHERE p.due_date != '' AND p.due_date >= ? ORDER BY p.due_date ASC LIMIT 100",
        (today,),
    ).fetchall()
    return jsonify(posts=[post_dict(r) for r in rows])


@app.get("/api/posts/<int:post_id>")
def get_post(post_id):
    row = db().execute(POST_SELECT + " WHERE p.id = ?", (post_id,)).fetchone()
    if row is None:
        return jsonify(error="Post nahi mili"), 404
    comments = db().execute(
        "SELECT * FROM comments WHERE post_id = ? ORDER BY created_at ASC", (post_id,)
    ).fetchall()
    return jsonify(post=post_dict(row), comments=[comment_dict(c) for c in comments])


@app.post("/api/posts/<int:post_id>/comments")
def add_comment(post_id):
    if too_many(client_ip()):
        return jsonify(error="Bahut jaldi jaldi sawal bhej rahe ho, thoda ruko"), 429
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    text = str(data.get("text", "")).strip()

    if not (1 <= len(name) <= 40):
        return jsonify(error="Naam 1 se 40 akshar ka likhein"), 400
    if not (3 <= len(text) <= 500):
        return jsonify(error="Sawal 3 se 500 akshar ka likhein"), 400
    if db().execute("SELECT 1 FROM posts WHERE id = ?", (post_id,)).fetchone() is None:
        return jsonify(error="Post nahi mili"), 404

    cur = db().execute(
        "INSERT INTO comments (post_id, name, text, created_at) VALUES (?,?,?,?)",
        (post_id, name, text, int(time.time())),
    )
    db().commit()
    return jsonify(ok=True, id=cur.lastrowid), 201


@app.post("/api/comments/<int:comment_id>/report")
def report_comment(comment_id):
    if too_many("report:" + client_ip(), limit=5):
        return jsonify(error="Thoda ruko"), 429
    db().execute("UPDATE comments SET reports = reports + 1 WHERE id = ?", (comment_id,))
    db().commit()
    return jsonify(ok=True)


# ---------------------------------------------------------------- admin api
@app.post("/api/admin/check")
@admin_only
def admin_check():
    return jsonify(ok=True)


def read_post_payload(data):
    """Post ka data check karke (dict, error) lautata hai."""
    title = str(data.get("title", "")).strip()
    body = str(data.get("body", "")).strip()
    category = str(data.get("category", "Other")).strip()
    course = str(data.get("course", "All")).strip()
    semester = str(data.get("semester", "All")).strip()
    image = str(data.get("image", "")).strip()
    link = clean_link(data.get("link"))
    due = clean_due(data.get("due_date"))

    if not (3 <= len(title) <= 200):
        return None, "Title 3 se 200 akshar ka hona chahiye"
    if not (1 <= len(body) <= 10000):
        return None, "Details likhna zaroori hai (max 10000 akshar)"
    if link is None:
        return None, "Link http:// ya https:// se shuru hona chahiye"
    if due is None:
        return None, "Last date sahi format me nahi hai"
    if image and not (IMG_RE.match(image) and os.path.exists(os.path.join(UPLOAD_DIR, image))):
        return None, "Photo sahi nahi hai, dobara upload karein"
    if category not in CATEGORIES:
        category = "Other"
    if course not in COURSES:
        course = "All"
    if semester not in SEMESTERS:
        semester = "All"
    return {
        "title": title, "body": body, "category": category, "course": course,
        "semester": semester, "link": link, "due_date": due, "image": image,
        "pinned": 1 if data.get("pinned") else 0,
    }, None


@app.post("/api/posts")
@admin_only
def create_post():
    p, err = read_post_payload(request.get_json(silent=True) or {})
    if err:
        return jsonify(error=err), 400
    cur = db().execute(
        "INSERT INTO posts (title, body, category, course, semester, due_date, image, link, pinned, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (p["title"], p["body"], p["category"], p["course"], p["semester"], p["due_date"],
         p["image"], p["link"], p["pinned"], int(time.time())),
    )
    db().commit()
    return jsonify(ok=True, id=cur.lastrowid), 201


@app.put("/api/posts/<int:post_id>")
@admin_only
def update_post(post_id):
    old = db().execute("SELECT image FROM posts WHERE id = ?", (post_id,)).fetchone()
    if old is None:
        return jsonify(error="Post nahi mili"), 404
    p, err = read_post_payload(request.get_json(silent=True) or {})
    if err:
        return jsonify(error=err), 400
    db().execute(
        "UPDATE posts SET title=?, body=?, category=?, course=?, semester=?, due_date=?, "
        "image=?, link=?, pinned=?, edited_at=? WHERE id=?",
        (p["title"], p["body"], p["category"], p["course"], p["semester"], p["due_date"],
         p["image"], p["link"], p["pinned"], int(time.time()), post_id),
    )
    db().commit()
    if old["image"] and old["image"] != p["image"]:
        remove_image(old["image"])
    return jsonify(ok=True)


@app.delete("/api/posts/<int:post_id>")
@admin_only
def delete_post(post_id):
    row = db().execute("SELECT image FROM posts WHERE id = ?", (post_id,)).fetchone()
    db().execute("DELETE FROM posts WHERE id = ?", (post_id,))
    db().commit()
    if row:
        remove_image(row["image"])
    return jsonify(ok=True)


@app.post("/api/upload")
@admin_only
def upload():
    f = request.files.get("image")
    if f is None:
        return jsonify(error="Photo nahi mili"), 400
    data = f.read(MAX_IMG + 1)
    if len(data) > MAX_IMG:
        return jsonify(error="Photo bahut badi hai (max 2.5 MB)"), 413
    ext = sniff_image(data)
    if ext is None:
        return jsonify(error="Sirf JPG, PNG ya WEBP photo chalegi"), 400
    name = secrets.token_hex(8) + ext
    with open(os.path.join(UPLOAD_DIR, name), "wb") as out:
        out.write(data)
    return jsonify(ok=True, image=name)


@app.post("/api/comments/<int:comment_id>/reply")
@admin_only
def reply_comment(comment_id):
    data = request.get_json(silent=True) or {}
    reply = str(data.get("reply", "")).strip()
    if not (1 <= len(reply) <= 1000):
        return jsonify(error="Jawab 1 se 1000 akshar ka likhein"), 400
    db().execute(
        "UPDATE comments SET reply = ?, replied_at = ? WHERE id = ?",
        (reply, int(time.time()), comment_id),
    )
    db().commit()
    return jsonify(ok=True)


@app.delete("/api/comments/<int:comment_id>")
@admin_only
def delete_comment(comment_id):
    db().execute("DELETE FROM comments WHERE id = ?", (comment_id,))
    db().commit()
    return jsonify(ok=True)


@app.put("/api/settings")
@admin_only
def update_settings():
    data = request.get_json(silent=True) or {}
    limits = {"result_url": 500, "contact": 200, "about": 3000, "guide": 6000}
    for key, maxlen in limits.items():
        if key not in data:
            continue
        val = str(data[key]).strip()
        if len(val) > maxlen:
            return jsonify(error="%s bahut lamba hai" % key), 400
        if key == "result_url" and val and not val.startswith(("http://", "https://")):
            return jsonify(error="Result link http:// ya https:// se shuru hona chahiye"), 400
        db().execute(
            "INSERT INTO settings (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, val),
        )
    db().commit()
    return jsonify(ok=True, settings=get_settings())


@app.get("/api/admin/stats")
@admin_only
def stats():
    d = db()
    week = int(time.time()) - 7 * 86400
    one = lambda sql, a=(): d.execute(sql, a).fetchone()[0]  # noqa: E731
    return jsonify(
        devices=one("SELECT COUNT(*) FROM devices"),
        active7=one("SELECT COUNT(*) FROM devices WHERE last_seen >= ?", (week,)),
        posts=one("SELECT COUNT(*) FROM posts"),
        comments=one("SELECT COUNT(*) FROM comments"),
        reported=one("SELECT COUNT(*) FROM comments WHERE reports > 0"),
    )


@app.get("/api/admin/backup")
@admin_only
def backup_download():
    path = make_backup()
    return send_file(path, as_attachment=True, download_name=os.path.basename(path))


init_db()

if __name__ == "__main__":
    print("=" * 50)
    print(" SKMU Updates server v2")
    print(" ADMIN KEY:", ADMIN_KEY)
    print(" (yahi key app me login ke liye use karni hai)")
    print("=" * 50)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
