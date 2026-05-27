import re
"""
ai_engine.py — Privacy-first AI orchestrator
- No public feeds or recommendations
- Matches are private sessions between exactly two users
- Rewards only on confirmed recovery
- Messages scoped to match sessions
"""
import os
from model       import hybrid_score, preprocess
from image_model import image_similarity
from database    import (get_db, log_activity, push_notification,
                         update_user_level, is_session_participant)

UPLOAD_FOLDER   = os.path.join(os.path.dirname(__file__), "uploads")
MATCH_THRESHOLD = 0.22   # min combined score to create a private session

# ── Internals ────────────────────────────────────────────────────────────────

def _img_score(fn_a, fn_b):
    if not fn_a or not fn_b:
        return 0.0
    return image_similarity(
        os.path.join(UPLOAD_FOLDER, fn_a),
        os.path.join(UPLOAD_FOLDER, fn_b)
    )

def _text(r):
    return f"{r['item']} {r['description'] or ''} {r['place'] or ''}"

def _combined_score(r_lost, r_found):
    t = hybrid_score(_text(r_lost), _text(r_found))
    i = _img_score(r_lost["image"], r_found["image"])
    return round(t * 0.65 + i * 0.35, 4), round(t * 100, 1), round(i * 100, 1)

# ── Match-session engine ──────────────────────────────────────────────────────

def run_matching_for_report(new_report_id):
    """
    Called after every new report submission.
    Scans for private matches and creates match_sessions.
    Notifies ONLY the two matched users — no public exposure.
    """
    conn = get_db()
    new_r = conn.execute("SELECT * FROM reports WHERE id=?", (new_report_id,)).fetchone()
    if not new_r:
        conn.close()
        return

    opposite_type = "found" if new_r["type"] == "lost" else "lost"

    candidates = conn.execute(
        "SELECT * FROM reports WHERE type=? AND status='active' AND username!=? "
        "ORDER BY created_at DESC",
        (opposite_type, new_r["username"])
    ).fetchall()
    conn.close()

    for cand in candidates:
        # Don't create duplicate sessions
        conn = get_db()
        r_lost  = new_r  if new_r["type"]  == "lost"  else cand
        r_found = new_r  if new_r["type"]  == "found" else cand
        existing = conn.execute(
            "SELECT id FROM match_sessions WHERE report_lost=? AND report_found=?",
            (r_lost["id"], r_found["id"])
        ).fetchone()

        if existing:
            conn.close()
            continue

        score, t_score, i_score = _combined_score(r_lost, r_found)
        if score < MATCH_THRESHOLD:
            conn.close()
            continue

        # Create private session
        conn.execute(
            "INSERT INTO match_sessions "
            "(report_lost, report_found, user_lost, user_found, score) "
            "VALUES (?,?,?,?,?)",
            (r_lost["id"], r_found["id"],
             r_lost["username"], r_found["username"], score)
        )
        conn.commit()

        # Notify both users privately — no details exposed in notification
        pct = round(score * 100, 1)
        push_notification(
            r_lost["username"],
            f"🎯 AI found a {pct}% match for your lost '{r_lost['item']}'! "
            f"Check your private matches.",
            "/dashboard"
        )
        push_notification(
            r_found["username"],
            f"🎯 Someone may be looking for the item you found ('{r_found['item']}'). "
            f"Check your private matches.",
            "/dashboard"
        )
        log_activity("system", "match_created",
                     f"session: {r_lost['username']} ↔ {r_found['username']} score={pct}%")
        conn.close()


def get_my_match_sessions(username):
    """
    Returns match sessions for this user ONLY.
    Counterpart's contact/image only revealed if both sides are confirmed.
    Privacy: caller only gets full detail for their own reports.
    """
    conn = get_db()
    sessions = conn.execute(
        "SELECT * FROM match_sessions "
        "WHERE (user_lost=? OR user_found=?) AND status != 'cancelled' "
        "ORDER BY created_at DESC",
        (username, username)
    ).fetchall()

    results = []
    for s in sessions:
        s = dict(s)
        i_am_lost  = (s["user_lost"]  == username)
        i_am_found = (s["user_found"] == username)

        my_report_id    = s["report_lost"]  if i_am_lost  else s["report_found"]
        their_report_id = s["report_found"] if i_am_lost  else s["report_lost"]

        my_r    = conn.execute("SELECT * FROM reports WHERE id=?", (my_report_id,)).fetchone()
        their_r = conn.execute("SELECT * FROM reports WHERE id=?", (their_report_id,)).fetchone()

        if not my_r or not their_r:
            continue

        both_confirmed = s["confirmed_by_lost"] and s["confirmed_by_found"]

        entry = {
            "session_id"       : s["id"],
            "status"           : s["status"],
            "score"            : round(s["score"] * 100, 1),
            "my_report_id"     : my_r["id"],
            "my_item"          : my_r["item"],
            "my_type"          : my_r["type"],
            "i_confirmed"      : s["confirmed_by_lost"] if i_am_lost else s["confirmed_by_found"],
            "they_confirmed"   : s["confirmed_by_found"] if i_am_lost else s["confirmed_by_lost"],
            "both_confirmed"   : both_confirmed,
            "created_at"       : s["created_at"],
            # Their info — only full detail after both confirm
            "their_item"       : their_r["item"],
            "their_type"       : their_r["type"],
            "their_description": their_r["description"] if both_confirmed else "🔒 Confirm recovery to reveal",
            "their_place"      : their_r["place"]       if both_confirmed else "🔒 Hidden",
            "their_date"       : their_r["date"]        if both_confirmed else "🔒 Hidden",
            "their_contact"    : their_r["contact"]     if both_confirmed else "🔒 Confirm to reveal",
            "their_image"      : (f"/uploads/{their_r['image']}" if their_r["image"] else "")
                                 if both_confirmed else "",
            "their_username"   : their_r["username"],
        }
        results.append(entry)

    conn.close()
    return results


def confirm_recovery(session_id, username):
    """
    User confirms item was recovered.
    Stars/credits awarded ONLY after both sides confirm.
    """
    conn = get_db()
    s = conn.execute("SELECT * FROM match_sessions WHERE id=?", (session_id,)).fetchone()
    if not s:
        conn.close()
        return False, "Session not found"

    if s["user_lost"] != username and s["user_found"] != username:
        conn.close()
        return False, "Unauthorized"

    if s["status"] == "confirmed":
        conn.close()
        return False, "Already confirmed"

    i_am_lost = (s["user_lost"] == username)

    if i_am_lost:
        conn.execute(
            "UPDATE match_sessions SET confirmed_by_lost=1 WHERE id=?", (session_id,)
        )
    else:
        conn.execute(
            "UPDATE match_sessions SET confirmed_by_found=1 WHERE id=?", (session_id,)
        )
    conn.commit()

    # Re-fetch to check both
    s = conn.execute("SELECT * FROM match_sessions WHERE id=?", (session_id,)).fetchone()
    both = s["confirmed_by_lost"] and s["confirmed_by_found"]

    if both:
        # Resolve both reports
        conn.execute(
            "UPDATE reports SET status='resolved', resolved_by=? WHERE id IN (?,?)",
            (username, s["report_lost"], s["report_found"])
        )
        conn.execute(
            "UPDATE match_sessions SET status='confirmed' WHERE id=?", (session_id,)
        )
        # Award stars/credits ONLY to finder (found-item reporter)
        finder = s["user_found"]
        conn.execute(
            "UPDATE users SET stars=stars+2, credits=credits+50, recoveries=recoveries+1 "
            "WHERE username=?", (finder,)
        )
        conn.commit()
        conn.close()

        update_user_level(finder)
        push_notification(
            finder,
            "🎉 Recovery confirmed! You earned +2 ⭐ stars & +50 💎 credits.",
            "/dashboard"
        )
        push_notification(
            s["user_lost"],
            "✅ Item successfully recovered! Thank you for using Lost & Found AI.",
            "/dashboard"
        )
        log_activity("system", "recovery_confirmed",
                     f"session {session_id}: {s['user_lost']} ↔ {finder}")
        return True, "fully_confirmed"
    else:
        conn.close()
        other = s["user_found"] if i_am_lost else s["user_lost"]
        push_notification(
            other,
            f"⏳ The other party confirmed recovery. Please confirm on your end.",
            "/dashboard"
        )
        return True, "waiting_other"


def get_session_messages(session_id, username):
    """Return messages for a session — only accessible to participants."""
    if not is_session_participant(session_id, username):
        return None  # forbidden

    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC",
        (session_id,)
    ).fetchall()
    conn.execute(
        "UPDATE messages SET read=1 WHERE session_id=? AND receiver=?",
        (session_id, username)
    )
    conn.commit()
    conn.close()
    return [dict(r) for r in rows]


def send_session_message(session_id, sender, body):
    """Send a message within a private match session."""
    if not is_session_participant(session_id, sender):
        return False, "Unauthorized"

    conn = get_db()
    s = conn.execute(
        "SELECT user_lost, user_found FROM match_sessions WHERE id=?", (session_id,)
    ).fetchone()
    if not s:
        conn.close()
        return False, "Session not found"

    receiver = s["user_found"] if s["user_lost"] == sender else s["user_lost"]
    conn.execute(
        "INSERT INTO messages (session_id, sender, receiver, body) VALUES (?,?,?,?)",
        (session_id, sender, receiver, body)
    )
    conn.commit()
    conn.close()
    push_notification(receiver, f"💬 New message in your private match chat.", "/dashboard")
    return True, "sent"


# ── Chatbot ───────────────────────────────────────────────────────────────────

INTENTS = {
    "greet"       : ["hi","hello","hey","good morning","good evening","howdy","sup"],
    "thanks"      : ["thank","thanks","thank you","thx","cheers","appreciate"],
    "report_lost" : ["i lost","i've lost","lost my","missing my","can't find","cannot find","dropped my"],
    "report_found": ["i found","i've found","found a","picked up","someone left","discovered"],
    "confirm"     : ["how to confirm","how do i confirm","confirm recovery","confirm match",
                     "confirmed","recovery confirmed","got back","item recovered","mark as found"],
    "check_match" : ["my matches","find my match","check match","search match","look for","match results","match session"],
    "privacy"     : ["private","privacy","safe","secure","who can see","hidden","data","personal"],
    "leaderboard" : ["leaderboard","ranking","top users","credits","stars","points","level badge"],
    "how_it_works": ["how does","explain","what is","tell me","guide me","how it works","help me understand"],
}

RESPONSES = {
    "greet": [
        "Hey! 👋 I'm your private Lost & Found AI assistant. How can I help?",
        "Hello! All your reports and matches are completely private. What do you need?",
    ],
    "report_lost": (
        "Sorry to hear that! 😟 Here's the secure process:\n\n"
        "1. Click **Report Item** → select **Lost**\n"
        "2. Describe your item (color, brand, size)\n"
        "3. Add the location and date\n"
        "4. Upload a photo — improves match accuracy by 35%\n\n"
        "🔒 **Privacy:** Only you and the person who found it will ever see match details.\n"
        "The AI privately scans all found reports and notifies you both if there's a match."
    ),
    "report_found": (
        "Great that you want to help! 🌟 Secure process:\n\n"
        "1. Click **Report Item** → select **Found**\n"
        "2. Describe what you found (without revealing too much publicly)\n"
        "3. The AI privately matches you with the owner\n\n"
        "🏆 **Reward:** You earn ⭐ +2 stars & 💎 +50 credits when the owner confirms recovery."
    ),
    "check_match": (
        "To see your private matches:\n\n"
        "1. Go to **Dashboard** → **My Private Matches**\n"
        "2. Each match shows a confidence % score\n"
        "3. Use the **private chat** to verify with the other person\n"
        "4. Both parties must **Confirm Recovery** to release full contact details\n\n"
        "🔒 Contact info is hidden until both sides confirm — preventing fraud."
    ),
    "privacy": (
        "🔒 **Privacy Architecture:**\n\n"
        "• **No public feed** — nobody can browse all reports\n"
        "• **Match sessions are private** — only two matched users see each other\n"
        "• **Contact details hidden** until both parties confirm recovery\n"
        "• **Images hidden** until confirmation\n"
        "• **Session-scoped chat** — messages only visible to matched pair\n\n"
        "This prevents fraudulent ownership claims."
    ),
    "leaderboard": (
        "🏆 The leaderboard shows recovery heroes — anonymised stats only.\n\n"
        "**How to earn:**\n"
        "• Report a found item → AI matches you → owner confirms → **+2 ⭐ +50 💎**\n"
        "• NO stars for logging in or registering\n"
        "• NO stars unless recovery is confirmed by the lost-item owner\n\n"
        "Levels: 🌱 Newcomer → 🤝 Helper → ⭐ Trusted → 🏆 Champion → 🌟 Legend → 👑 Guardian"
    ),
    "confirm": (
        "To confirm a recovery:\n\n"
        "1. Go to **Dashboard** → **My Private Matches**\n"
        "2. Find the session with status **Pending Confirmation**\n"
        "3. Click **Confirm Recovery**\n"
        "4. Once BOTH parties confirm:\n"
        "   • Full contact details are revealed\n"
        "   • Finder earns stars & credits\n"
        "   • Reports are marked resolved\n\n"
        "⚠️ Only confirm when you have actually received/returned the item."
    ),
    "how_it_works": (
        "**Lost & Found AI — How It Works:**\n\n"
        "1️⃣ Report your lost or found item privately\n"
        "2️⃣ AI matches using text (65%) + image (35%) similarity\n"
        "3️⃣ Both users notified privately — no public exposure\n"
        "4️⃣ Private session chat opens between matched pair\n"
        "5️⃣ Both confirm recovery → rewards released\n\n"
        "🔒 Nobody else can see your reports, images, or contact details."
    ),
    "thanks": [
        "You're welcome! 😊 Stay safe and I hope you recover your item soon.",
        "Happy to help! 🍀 Remember — all your data stays completely private.",
    ],
    "default": (
        "I can help with:\n\n"
        "• **'I lost my wallet'** — how to report\n"
        "• **'I found a phone'** — how to report a found item\n"
        "• **'Show my matches'** — checking your private matches\n"
        "• **'How does this work'** — platform explanation\n"
        "• **'Is my data private'** — privacy architecture\n"
        "• **'How to confirm recovery'** — confirmation steps"
    )
}

def detect_intent(text):
    t = " " + text.lower() + " "          # pad so whole-word check works
    for intent, kws in INTENTS.items():
        for kw in kws:
            # multi-word phrases: substring match; single words: whole-word match
            if " " in kw:
                if kw in t:
                    return intent
            else:
                if re.search(r"\b" + re.escape(kw) + r"\b", t):
                    return intent
    return "default"

def get_bot_response(message, username=None):
    import random
    intent = detect_intent(message)
    resp   = RESPONSES.get(intent, RESPONSES["default"])
    if isinstance(resp, list):
        resp = random.choice(resp)
    if username:
        conn = get_db()
        conn.execute(
            "INSERT INTO chat_history (username,role,message) VALUES (?,?,?)",
            (username, "user", message)
        )
        conn.execute(
            "INSERT INTO chat_history (username,role,message) VALUES (?,?,?)",
            (username, "bot", resp)
        )
        conn.commit()
        conn.close()
    return resp

def get_chat_history(username, limit=30):
    conn = get_db()
    rows = conn.execute(
        "SELECT role,message,created_at FROM chat_history "
        "WHERE username=? ORDER BY created_at DESC LIMIT ?",
        (username, limit)
    ).fetchall()
    conn.close()
    return list(reversed([dict(r) for r in rows]))
