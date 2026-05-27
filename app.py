"""
app.py — Privacy-First Lost & Found AI Platform
- No public feeds
- All match data gated to session participants
- Rewards only on confirmed recovery
"""
import os, uuid
from flask import (Flask, request, jsonify, render_template,
                   session, redirect, send_from_directory)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils    import secure_filename

from database  import (get_db, init_db, log_activity, push_notification,
                        update_user_level, is_session_participant)
from ai_engine import (run_matching_for_report, get_my_match_sessions,
                        confirm_recovery, get_session_messages,
                        send_session_message, get_bot_response, get_chat_history)

app = Flask(__name__)
app.secret_key     = os.environ.get("SECRET_KEY", "lf_private_2024_change_me")
UPLOAD_FOLDER      = os.path.join(os.path.dirname(__file__), "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
init_db()

# ── Helpers ───────────────────────────────────────────────────────────────────
def allowed_file(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def cu():
    return session.get("user")

def auth_required(fn):
    """Decorator: return 401 JSON if not logged in."""
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not cu():
            return jsonify({"message": "Unauthorized"}), 401
        return fn(*args, **kwargs)
    return wrapper

def is_admin():
    if not cu(): return False
    conn = get_db()
    row  = conn.execute("SELECT role FROM users WHERE username=?", (cu(),)).fetchone()
    conn.close()
    return row and row["role"] == "admin"

# ── Uploads — auth-gated ──────────────────────────────────────────────────────
@app.route("/uploads/<filename>")
def uploaded_file(filename):
    """
    Only serve upload to users who are participants of a confirmed session
    involving this file — or to admins.
    """
    if not cu():
        return jsonify({"message": "Unauthorized"}), 401

    if is_admin():
        return send_from_directory(UPLOAD_FOLDER, filename)

    # Check user is participant of a session involving this image
    conn = get_db()
    row = conn.execute(
        """SELECT ms.id FROM match_sessions ms
           JOIN reports r ON (r.id = ms.report_lost OR r.id = ms.report_found)
           WHERE r.image=? AND (ms.user_lost=? OR ms.user_found=?)""",
        (filename, cu(), cu())
    ).fetchone()
    # Also allow viewing your own report image
    own = conn.execute(
        "SELECT id FROM reports WHERE image=? AND username=?", (filename, cu())
    ).fetchone()
    conn.close()

    if not row and not own:
        return jsonify({"message": "Forbidden"}), 403

    return send_from_directory(UPLOAD_FOLDER, filename)

# ── Pages ─────────────────────────────────────────────────────────────────────
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login")
def login_page():
    if cu(): return redirect("/dashboard")
    return render_template("login.html")

@app.route("/register")
def register_page():
    if cu(): return redirect("/dashboard")
    return render_template("register.html")

@app.route("/dashboard")
def dashboard():
    if not cu(): return redirect("/login")
    return render_template("dashboard.html")

@app.route("/report")
def report_page():
    if not cu(): return redirect("/login")
    return render_template("report.html")

@app.route("/match/<int:session_id>")
def match_page(session_id):
    if not cu(): return redirect("/login")
    if not is_session_participant(session_id, cu()):
        return redirect("/dashboard")
    return render_template("match.html", session_id=session_id)

@app.route("/admin")
def admin_page():
    if not is_admin(): return redirect("/dashboard")
    return render_template("admin.html")

# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route("/api/register", methods=["POST"])
def register():
    d = request.get_json(silent=True) or {}
    username = d.get("username", "").strip()
    password = d.get("password", "").strip()
    if not username or not password:
        return jsonify({"message": "Missing fields"}), 400
    if len(username) < 3:
        return jsonify({"message": "Username must be ≥ 3 characters"}), 400
    if len(password) < 4:
        return jsonify({"message": "Password must be ≥ 4 characters"}), 400
    conn = get_db()
    try:
        conn.execute("INSERT INTO users (username,password) VALUES (?,?)",
                     (username, generate_password_hash(password)))
        conn.commit()
        log_activity(username, "register")
        return jsonify({"message": "Registered successfully"}), 200
    except Exception:
        return jsonify({"message": "Username already exists"}), 409
    finally:
        conn.close()

@app.route("/api/login", methods=["POST"])
def login():
    d = request.get_json(silent=True) or {}
    username = d.get("username", "").strip()
    password = d.get("password", "").strip()
    if not username or not password:
        return jsonify({"message": "Missing fields"}), 400
    conn = get_db()
    row  = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    conn.close()
    if not row or not check_password_hash(row["password"], password):
        return jsonify({"message": "Invalid credentials"}), 401
    if row["banned"]:
        return jsonify({"message": "Account suspended. Contact admin."}), 403
    session["user"] = username
    log_activity(username, "login")
    return jsonify({"message": "Login successful", "role": row["role"]}), 200

@app.route("/api/logout")
def logout():
    session.clear()
    return redirect("/login")

# ── User ──────────────────────────────────────────────────────────────────────
@app.route("/api/user")
@auth_required
def get_user():
    conn = get_db()
    row  = conn.execute(
        "SELECT username,stars,credits,level,badge,role,recoveries FROM users WHERE username=?",
        (cu(),)
    ).fetchone()
    notif_count = conn.execute(
        "SELECT COUNT(*) FROM notifications WHERE username=? AND read=0", (cu(),)
    ).fetchone()[0]
    unread_msgs = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE receiver=? AND read=0", (cu(),)
    ).fetchone()[0]
    conn.close()
    if not row: return jsonify({"message": "Not found"}), 404
    return jsonify({
        "username":          row["username"],
        "stars":             row["stars"] or 0,
        "credits":           row["credits"] or 0,
        "level":             row["level"],
        "badge":             row["badge"],
        "role":              row["role"],
        "recoveries":        row["recoveries"] or 0,
        "notifications":     notif_count,
        "unread_messages":   unread_msgs,
    }), 200

# ── Reports ───────────────────────────────────────────────────────────────────
@app.route("/api/report", methods=["POST"])
@auth_required
def report_item():
    try:
        d = request.form
        for f in ["type", "item", "description", "place", "date", "contact"]:
            if not d.get(f, "").strip():
                return jsonify({"message": f"Field '{f}' is required"}), 400
        if d.get("type") not in ("lost", "found"):
            return jsonify({"message": "Type must be lost or found"}), 400

        filename = None
        if "image" in request.files:
            img = request.files["image"]
            if img and img.filename and allowed_file(img.filename):
                safe     = secure_filename(img.filename)
                filename = f"{uuid.uuid4().hex}_{safe}"
                img.save(os.path.join(UPLOAD_FOLDER, filename))

        conn = get_db()
        cursor = conn.execute(
            "INSERT INTO reports (username,type,item,description,place,date,contact,image) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (cu(), d["type"].strip(), d["item"].strip(), d["description"].strip(),
             d["place"].strip(), d["date"].strip(), d["contact"].strip(), filename)
        )
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()

        log_activity(cu(), "report", f"{d['type']} {d['item']}")

        # Trigger private AI matching in-process (fast enough for sync)
        try:
            run_matching_for_report(new_id)
        except Exception as e:
            print(f"[matching] non-fatal error: {e}")

        return jsonify({"message": "Item reported successfully"}), 200

    except Exception as e:
        print("REPORT ERROR:", e)
        return jsonify({"message": "Server error"}), 500

@app.route("/api/my_reports")
@auth_required
def my_reports():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM reports WHERE username=? ORDER BY created_at DESC", (cu(),)
    ).fetchall()
    conn.close()
    return jsonify([{
        "id":          r["id"],
        "type":        r["type"],
        "item":        r["item"],
        "description": r["description"],
        "place":       r["place"],
        "date":        r["date"],
        "contact":     r["contact"],
        "image":       f"/uploads/{r['image']}" if r["image"] else "",
        "status":      r["status"],
        "created_at":  r["created_at"],
    } for r in rows]), 200

@app.route("/api/delete_report/<int:rid>", methods=["DELETE"])
@auth_required
def delete_report(rid):
    conn = get_db()
    row  = conn.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
    if not row:
        conn.close()
        return jsonify({"message": "Not found"}), 404
    if row["username"] != cu() and not is_admin():
        conn.close()
        return jsonify({"message": "Forbidden"}), 403
    conn.execute("DELETE FROM reports WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Deleted"}), 200

# ── Private Match Sessions ────────────────────────────────────────────────────
@app.route("/api/my_matches")
@auth_required
def my_matches():
    sessions = get_my_match_sessions(cu())
    return jsonify(sessions), 200

@app.route("/api/confirm_recovery", methods=["POST"])
@auth_required
def api_confirm_recovery():
    d          = request.get_json(silent=True) or {}
    session_id = d.get("session_id")
    if not session_id:
        return jsonify({"message": "Missing session_id"}), 400
    ok, status = confirm_recovery(session_id, cu())
    if not ok:
        return jsonify({"message": status}), 400
    return jsonify({"success": True, "status": status}), 200

# ── Session-scoped Messaging ──────────────────────────────────────────────────
@app.route("/api/session_messages/<int:session_id>")
@auth_required
def session_messages(session_id):
    msgs = get_session_messages(session_id, cu())
    if msgs is None:
        return jsonify({"message": "Forbidden"}), 403
    return jsonify(msgs), 200

@app.route("/api/send_session_message", methods=["POST"])
@auth_required
def api_send_session_message():
    d          = request.get_json(silent=True) or {}
    session_id = d.get("session_id")
    body       = d.get("body", "").strip()
    if not session_id or not body:
        return jsonify({"message": "Missing fields"}), 400
    ok, msg = send_session_message(session_id, cu(), body)
    if not ok:
        return jsonify({"message": msg}), 403
    return jsonify({"message": "Sent"}), 200

# ── Leaderboard (public — shows only username/stars/level, no reports) ────────
@app.route("/api/leaderboard")
def leaderboard():
    conn = get_db()
    rows = conn.execute(
        "SELECT username, stars, credits, level, badge, recoveries "
        "FROM users WHERE banned=0 ORDER BY stars DESC, recoveries DESC LIMIT 10"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200

# ── Notifications ─────────────────────────────────────────────────────────────
@app.route("/api/notifications")
@auth_required
def notifications():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM notifications WHERE username=? ORDER BY created_at DESC LIMIT 20",
        (cu(),)
    ).fetchall()
    conn.execute("UPDATE notifications SET read=1 WHERE username=?", (cu(),))
    conn.commit()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200

# ── Chatbot ───────────────────────────────────────────────────────────────────
@app.route("/api/chat", methods=["POST"])
@auth_required
def chat():
    d   = request.get_json(silent=True) or {}
    msg = d.get("message", "").strip()
    if not msg:
        return jsonify({"message": "Empty message"}), 400
    return jsonify({"response": get_bot_response(msg, cu())}), 200

@app.route("/api/chat_history")
@auth_required
def chat_history():
    return jsonify(get_chat_history(cu())), 200

# ── Admin ─────────────────────────────────────────────────────────────────────
@app.route("/api/admin/stats")
def admin_stats():
    if not is_admin(): return jsonify({"message": "Forbidden"}), 403
    conn  = get_db()
    stats = {
        "total_users":      conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "total_reports":    conn.execute("SELECT COUNT(*) FROM reports").fetchone()[0],
        "active_reports":   conn.execute("SELECT COUNT(*) FROM reports WHERE status='active'").fetchone()[0],
        "resolved":         conn.execute("SELECT COUNT(*) FROM reports WHERE status='resolved'").fetchone()[0],
        "match_sessions":   conn.execute("SELECT COUNT(*) FROM match_sessions").fetchone()[0],
        "confirmed_matches":conn.execute("SELECT COUNT(*) FROM match_sessions WHERE status='confirmed'").fetchone()[0],
        "messages":         conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
    }
    conn.close()
    return jsonify(stats), 200

@app.route("/api/admin/users")
def admin_users():
    if not is_admin(): return jsonify({"message": "Forbidden"}), 403
    conn = get_db()
    rows = conn.execute(
        "SELECT id,username,role,stars,credits,level,badge,recoveries,banned,created_at "
        "FROM users ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200

@app.route("/api/admin/reports")
def admin_reports():
    if not is_admin(): return jsonify({"message": "Forbidden"}), 403
    conn = get_db()
    rows = conn.execute("SELECT * FROM reports ORDER BY created_at DESC LIMIT 100").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200

@app.route("/api/admin/sessions")
def admin_sessions():
    if not is_admin(): return jsonify({"message": "Forbidden"}), 403
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM match_sessions ORDER BY created_at DESC LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200

@app.route("/api/admin/ban/<username>", methods=["POST"])
def admin_ban(username):
    if not is_admin(): return jsonify({"message": "Forbidden"}), 403
    conn = get_db()
    conn.execute("UPDATE users SET banned=1 WHERE username=?", (username,))
    conn.commit()
    conn.close()
    log_activity(cu(), "ban_user", username)
    return jsonify({"message": f"{username} banned"}), 200

@app.route("/api/admin/unban/<username>", methods=["POST"])
def admin_unban(username):
    if not is_admin(): return jsonify({"message": "Forbidden"}), 403
    conn = get_db()
    conn.execute("UPDATE users SET banned=0 WHERE username=?", (username,))
    conn.commit()
    conn.close()
    return jsonify({"message": f"{username} unbanned"}), 200

@app.route("/api/admin/delete_report/<int:rid>", methods=["DELETE"])
def admin_delete_report(rid):
    if not is_admin(): return jsonify({"message": "Forbidden"}), 403
    conn = get_db()
    conn.execute("DELETE FROM reports WHERE id=?", (rid,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Deleted"}), 200

@app.route("/api/admin/activity")
def admin_activity():
    if not is_admin(): return jsonify({"message": "Forbidden"}), 403
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM activity_log ORDER BY created_at DESC LIMIT 200"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows]), 200

@app.route("/api/admin/make_admin/<username>", methods=["POST"])
def make_admin(username):
    if not is_admin(): return jsonify({"message": "Forbidden"}), 403
    conn = get_db()
    conn.execute("UPDATE users SET role='admin' WHERE username=?", (username,))
    conn.commit()
    conn.close()
    return jsonify({"message": f"{username} is now admin"}), 200

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
