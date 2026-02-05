import os
import re
import tempfile
from datetime import datetime, timedelta
from typing import Optional

from bson import ObjectId
from flask import Blueprint, render_template, request, jsonify, session, current_app

from app.models import (
    get_db,
    create_expense,
    list_expenses,
)
from app.nlp_parser import parse_expense_text
from app.asr import transcribe_with_whisper  # if ASR_BACKEND="whisper"

# ---------- UI ROUTES ----------
bp = Blueprint("main", __name__)


@bp.route("/", methods=["GET"])
def home():
    # Show the login page to unauthenticated users; logged-in users see the main app
    if session.get("user_id"):
        return render_template("index.html")
    return render_template("login.html")


@bp.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")


@bp.route("/signup", methods=["GET"])
def signup_page():
    return render_template("signup.html")


@bp.route("/dashboard", methods=["GET"])
def dashboard_page():
    return render_template("dashboard.html")


# ---------- Helpers ----------
def require_user_json():
    """Return (user_id, error_response_or_None). Never redirects to HTML."""
    uid = session.get("user_id")
    if not uid:
        return None, (jsonify({"error": "Unauthorized"}), 401)
    return uid, None


def as_oid(x):
    return x if isinstance(x, ObjectId) else ObjectId(str(x))


def goal_slug(name: str) -> str:
    """Normalize goal names to a case/space/char-insensitive key."""
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")


def serialize_goal(g):
    return {
        "_id": str(g["_id"]),
        "user_id": str(g["user_id"]),
        "goal_name": g.get("goal_name") or g.get("name"),
        "target_amount": float(g.get("target_amount", 0.0)),
        "saved_amount": float(g.get("saved_amount", 0.0)),
        "is_completed": bool(g.get("is_completed", False)),
        "slug": g.get("slug"),
        "created_at": g.get("created_at"),
        "updated_at": g.get("updated_at"),
    }


# ---------- CATEGORY / PAYMENT DETECTION ----------
CATEGORY_KEYWORDS = {
    "Food": [
        "pizza", "burger", "food", "meal", "restaurant", "coffee", "snack", "dinner",
        "lunch", "breakfast", "sandwich", "tea",
    ],
    "Shopping": [
        "dress", "clothes", "shopping", "furniture", "electronics", "jeans", "bag",
        "shoes", "watch", "mobile", "laptop", "accessory",
    ],
    "Transport": [
        "taxi", "uber", "ola", "bus", "train", "fuel", "petrol", "diesel", "cab", "bike",
        "metro", "auto", "rickshaw", "parking", "toll",
    ],
    "Bills": [
        "electric", "electricity", "bill", "wifi", "internet", "broadband", "recharge",
        "mobile recharge", "dth", "subscription", "netflix", "prime", "spotify",
    ],
    "Entertainment": [
        "movie", "cinema", "game", "music", "concert", "ott", "theatre", "theater",
    ],
    "Health": [
        "medicine", "hospital", "doctor", "gym", "health", "protein", "pharmacy", "clinic",
    ],
    "Education": [
        "book", "course", "exam", "college", "school", "tuition", "fees", "coaching",
    ],
    "Rent": [
        "rent", "flat", "room", "hostel", "pg",
    ],
    "Travel": [
        "flight", "hotel", "trip", "vacation", "travel", "tour", "airbnb",
    ],
}


def infer_category(text: str, given: Optional[str] = None) -> str:
    if given and given not in (None, "", "Unknown", "Others", "Other"):
        return given
    t = (text or "").lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        for kw in kws:
            if re.search(rf"\b{re.escape(kw)}\b", t):
                return cat
    return "Others"


def infer_payment_method(text: str, given: Optional[str] = None) -> str:
    if given and given not in (None, "", "Unknown"):
        return given
    t = (text or "").lower()
    if "google pay" in t or "gpay" in t:
        return "Google Pay"
    if "phonepe" in t:
        return "PhonePe"
    if "paytm" in t:
        return "Paytm"
    if "upi" in t:
        return "UPI"
    if "cash" in t:
        return "Cash"
    if "credit" in t or "debit" in t or "card" in t:
        return "Card"
    return "Unknown"


# ---------- EXPENSES ----------
@bp.route("/api/expenses", methods=["GET"])
def api_expenses_get():
    uid, err = require_user_json()
    if err:
        return err

    limit = int(request.args.get("limit", 50))
    docs = list_expenses(uid)[:limit]

    out = []
    for d in docs:
        d["_id"] = str(d["_id"])
        d["user_id"] = str(d["user_id"])
        if isinstance(d.get("timestamp"), datetime):
            d["timestamp"] = d["timestamp"].isoformat()
        out.append(d)
    return jsonify({"expenses": out}), 200


@bp.route("/api/expenses", methods=["POST"])
def api_expenses_post():
    uid, err = require_user_json()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    text = (data.get("description") or "").strip()
    if not text:
        return jsonify({"error": "description is required"}), 400

    parsed = parse_expense_text(text) or {}
    if not parsed.get("amount"):
        parsed["amount"] = 0.0
        parsed["meta"] = {"status": "pending_amount"}

    parsed.setdefault("description", text)
    parsed.setdefault("timestamp", datetime.utcnow())
    parsed["user_id"] = uid

    parsed["category"] = infer_category(parsed.get("description", ""), parsed.get("category"))
    parsed["payment_method"] = infer_payment_method(parsed.get("description", ""), parsed.get("payment_method"))

    created = create_expense(uid, parsed)
    if not created:
        db = get_db()
        created = db.expenses.find_one({"user_id": as_oid(uid)}, sort=[("_id", -1)])

    created["_id"] = str(created["_id"])
    created["user_id"] = str(created["user_id"])
    if isinstance(created.get("timestamp"), datetime):
        created["timestamp"] = created["timestamp"].isoformat()

    return jsonify({"message": "Expense created", "expense": created}), 201


@bp.route("/api/expenses/<expense_id>", methods=["DELETE"])
def api_expenses_delete(expense_id):
    uid, err = require_user_json()
    if err:
        return err

    db = get_db()
    res = db.expenses.delete_one({"_id": as_oid(expense_id), "user_id": as_oid(uid)})
    if res.deleted_count:
        return jsonify({"message": "Expense deleted"}), 200
    return jsonify({"error": "Not found"}), 404


@bp.route("/api/expenses/upload-audio", methods=["POST"])
def api_expenses_upload_audio():
    uid, err = require_user_json()
    if err:
        return err

    if "audio" not in request.files:
        return jsonify({"error": "audio file missing"}), 400

    f = request.files["audio"]
    ext = os.path.splitext(f.filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name

    try:
        backend = current_app.config.get("ASR_BACKEND", "whisper")
        if backend == "whisper":
            transcript = transcribe_with_whisper(tmp_path)
        else:
            transcript = request.form.get("transcript")
    except Exception as e:
        os.remove(tmp_path)
        return jsonify({"error": "ASR failed", "details": str(e)}), 500
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    parsed = parse_expense_text(transcript) or {}
    if not parsed.get("amount"):
        parsed["amount"] = 0.0
        parsed["meta"] = {"status": "pending_amount"}

    parsed.setdefault("description", transcript)
    parsed.setdefault("timestamp", datetime.utcnow())
    parsed["user_id"] = uid

    parsed["category"] = infer_category(parsed.get("description", ""), parsed.get("category"))
    parsed["payment_method"] = infer_payment_method(parsed.get("description", ""), parsed.get("payment_method"))

    created = create_expense(uid, parsed)
    if not created:
        db = get_db()
        created = db.expenses.find_one({"user_id": as_oid(uid)}, sort=[("_id", -1)])

    created["_id"] = str(created["_id"])
    created["user_id"] = str(created["user_id"])
    if isinstance(created.get("timestamp"), datetime):
        created["timestamp"] = created["timestamp"].isoformat()

    return jsonify({"message": "Expense saved", "transcript": transcript, "expense": created}), 201


# ---------- GOALS ----------
@bp.route("/api/goals", methods=["GET"])
def api_goals_get():
    uid, err = require_user_json()
    if err:
        return err

    db = get_db()
    goals = list(
        db.goals.find({"user_id": as_oid(uid)}).sort([("created_at", -1), ("_id", -1)])
    )
    return jsonify({"goals": [serialize_goal(g) for g in goals]}), 200


@bp.route("/api/goals", methods=["POST"])
def api_goals_post():
    """
    Create a goal, or update target if the goal (by slug) already exists.
    Body: { goal_name, target_amount }
    """
    uid, err = require_user_json()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    name = (data.get("goal_name") or data.get("name") or "").strip()
    try:
        target = float(data.get("target_amount") or data.get("target") or 0.0)
    except Exception:
        target = 0.0

    if not name or target <= 0:
        return jsonify({"error": "goal_name and target_amount are required"}), 400

    db = get_db()
    slug = goal_slug(name)
    existing = db.goals.find_one({"user_id": as_oid(uid), "slug": slug})

    if existing:
        update = {"updated_at": datetime.utcnow()}
        update["target_amount"] = target
        saved = float(existing.get("saved_amount", 0.0))
        update["is_completed"] = saved >= target
        db.goals.update_one({"_id": existing["_id"]}, {"$set": update})
        updated = db.goals.find_one({"_id": existing["_id"]})
        return jsonify(
            {
                "message": "Goal already existed; updated target",
                "goal": serialize_goal(updated),
            }
        ), 200

    new_goal = {
        "user_id": as_oid(uid),
        "goal_name": name,
        "slug": slug,
        "target_amount": target,
        "saved_amount": 0.0,
        "currency": "INR",
        "is_completed": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }
    res = db.goals.insert_one(new_goal)
    created = db.goals.find_one({"_id": res.inserted_id})
    return jsonify({"message": "Goal created", "goal": serialize_goal(created)}), 201


@bp.route("/api/goals/<goal_id>", methods=["DELETE"])
def api_goals_delete(goal_id):
    uid, err = require_user_json()
    if err:
        return err

    db = get_db()
    res = db.goals.delete_one({"_id": as_oid(goal_id), "user_id": as_oid(uid)})
    if res.deleted_count:
        return jsonify({"message": "Goal deleted"}), 200
    return jsonify({"error": "Not found"}), 404


@bp.route("/api/goals/voice-update", methods=["POST"])
def api_goals_voice_update():
    """
    Voice updates for existing goals.
    Examples: "add 500 to my watch", "save 1,200 for laptop", "deposit 250 into vacation goal"
    - Matches goal by normalized slug; does NOT auto-create (returns 404 if not found).
    - Returns flags: goal_completed, exceeded, over_by.
    """
    uid, err = require_user_json()
    if err:
        return err

    fpath = None
    transcript = None
    try:
        if "audio" in request.files:
            f = request.files["audio"]
            ext = os.path.splitext(f.filename)[1] or ".webm"
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                f.save(tmp.name)
                fpath = tmp.name

        backend = current_app.config.get("ASR_BACKEND", "whisper")
        if backend == "whisper" and fpath:
            transcript = transcribe_with_whisper(fpath)
        else:
            transcript = request.form.get("transcript")
    except Exception as e:
        if fpath and os.path.exists(fpath):
            os.remove(fpath)
        return jsonify({"error": "ASR failed", "details": str(e)}), 500
    finally:
        if fpath and os.path.exists(fpath):
            os.remove(fpath)

    if not transcript:
        return jsonify({"error": "audio file or transcript required"}), 400

    raw_transcript = transcript.strip()
    t = raw_transcript.lower()

    # ---- amount: first numeric token ----
    amt_m = re.search(r'(\d+(?:\.\d{1,2})?)', t)
    if not amt_m:
        return jsonify({
            "error": "Could not parse amount from voice",
            "transcript": raw_transcript
        }), 400
    amount = float(amt_m.group(1).replace(',', ''))

    # ---- goal name: try several flexible patterns ----
    goal_name = None
    goal_patterns = [
        r'(?:to|into|for|towards)\s+(?:my\s+)?([a-z][a-z0-9 ]+?)(?:\s+goal)?\b',
        r'\bmy\s+([a-z][a-z0-9 ]+?)(?:\s+goal)?\b',
        r'\b([a-z][a-z0-9 ]+?)\s+goal\b',
    ]

    for pat in goal_patterns:
        m = re.search(pat, t, re.I)
        if m:
            goal_name = m.group(1).strip()
            break

    # Fallback: last few non-noise tokens
    if not goal_name:
        noise = {
            'add', 'put', 'save', 'deposit', 'set', 'aside', 'transfer', 'move',
            'to', 'into', 'for', 'towards', 'my', 'goal', 'rs', 'rupees', '₹'
        }
        tokens = [w for w in re.findall(r'[a-z0-9]+', t) if w not in noise and not w.isdigit()]
        if tokens:
            goal_name = ' '.join(tokens[-3:]).strip()

    if not goal_name:
        return jsonify({"error": "Could not parse goal update", "transcript": raw_transcript}), 400

    slug = goal_slug(goal_name)

    db = get_db()
    goal = db.goals.find_one({"user_id": as_oid(uid), "slug": slug})
    if not goal:
        return jsonify(
            {"error": f"Goal '{goal_name}' not found. Create it first.", "transcript": raw_transcript}
        ), 404

    saved = float(goal.get("saved_amount", 0.0)) + amount
    target = float(goal.get("target_amount", 0.0))
    is_completed = target > 0 and saved >= target
    exceeded = target > 0 and saved > target

    db.goals.update_one(
        {"_id": goal["_id"]},
        {"$set": {"saved_amount": saved, "is_completed": is_completed, "updated_at": datetime.utcnow()}},
    )
    updated = db.goals.find_one({"_id": goal["_id"]})

    return jsonify(
        {
            "message": "Goal updated",
            "goal": serialize_goal(updated),
            "saved_amount": saved,
            "target_amount": target,
            "goal_completed": is_completed,
            "exceeded": exceeded,
            "over_by": max(saved - target, 0.0) if exceeded else 0.0,
            "transcript": raw_transcript,
        }
    ), 200


# ---------- ANALYTICS (dashboard + charts) ----------
@bp.route("/api/analytics/summary", methods=["GET"])
def api_analytics_summary():
    uid, err = require_user_json()
    if err:
        return err

    db = get_db()
    since = datetime.utcnow() - timedelta(days=30)

    # total spent / count / avg in last 30 days
    match = {"user_id": as_oid(uid), "timestamp": {"$gte": since}}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
    ]
    agg = list(db.expenses.aggregate(pipeline))
    total_spent = float(agg[0]["total"]) if agg else 0.0
    total_expenses = int(agg[0]["count"]) if agg else 0
    avg_expense = (total_spent / total_expenses) if total_expenses else 0.0

    # total saved across all goals
    goals = list(db.goals.find({"user_id": as_oid(uid)}, {"saved_amount": 1}))
    total_saved = float(sum(g.get("saved_amount", 0.0) for g in goals))

    return jsonify(
        {
            "total_spent": total_spent,
            "avg_expense": avg_expense,
            "total_expenses": total_expenses,
            "total_saved": total_saved,
        }
    ), 200


@bp.route("/api/analytics/category-wise", methods=["GET"])
def api_analytics_category_wise():
    uid, err = require_user_json()
    if err:
        return err

    db = get_db()
    since = datetime.utcnow() - timedelta(days=30)
    pipeline = [
        {"$match": {"user_id": as_oid(uid), "timestamp": {"$gte": since}}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
        {"$sort": {"total": -1}},
    ]
    data = list(db.expenses.aggregate(pipeline))
    for d in data:
        d["total"] = float(d.get("total", 0))
        if d.get("_id") in (None, "", "Unknown"):
            d["_id"] = "Others"
    return jsonify({"data": data}), 200


@bp.route("/api/analytics/month-wise", methods=["GET"])
def api_analytics_month_wise():
    uid, err = require_user_json()
    if err:
        return err

    db = get_db()
    since = datetime.utcnow() - timedelta(days=180)  # ~6 months
    pipeline = [
        {"$match": {"user_id": as_oid(uid), "timestamp": {"$gte": since}}},
        {
            "$group": {
                "_id": {"$dateToString": {"format": "%Y-%m", "date": "$timestamp"}},
                "total": {"$sum": "$amount"},
            }
        },
        {"$sort": {"_id": 1}},
    ]
    data = list(db.expenses.aggregate(pipeline))
    for d in data:
        d["total"] = float(d.get("total", 0))
    return jsonify({"data": data}), 200

# ---------- Q&A (natural question handlers) ----------
@bp.route("/api/qa", methods=["POST"])
def api_qa():
    uid, err = require_user_json()
    if err:
        return err

    data = request.get_json(silent=True) or {}
    qid = data.get("question_id")
    qtext = (data.get("q") or "").strip()

    db = get_db()
    now = datetime.utcnow()
    today_start = datetime(now.year, now.month, now.day)
    today_end = today_start + timedelta(days=1) - timedelta(microseconds=1)
    week_start = today_start - timedelta(days=today_start.weekday())
    month_start = datetime(now.year, now.month, 1)
    year_start = datetime(now.year, 1, 1)

    def sum_amount(match):
        pipeline = [{"$match": match}, {"$group": {"_id": None, "total": {"$sum": "$amount"}}}]
        agg = list(db.expenses.aggregate(pipeline))
        return float(agg[0]["total"]) if agg else 0.0

    def count_docs(match):
        return db.expenses.count_documents(match)

    def top_category(match, ascending=False):
        s = -1 if not ascending else 1
        pipeline = [
            {"$match": match},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
            {"$sort": {"total": s}},
            {"$limit": 1},
        ]
        res = list(db.expenses.aggregate(pipeline))
        return res[0] if res else None

    def top_date(match):
        pipeline = [
            {"$match": match},
            {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}}, "total": {"$sum": "$amount"}}},
            {"$sort": {"total": -1}},
            {"$limit": 1},
        ]
        res = list(db.expenses.aggregate(pipeline))
        return res[0] if res else None

    # Helper: active (first incomplete) goal
    goal = db.goals.find_one({"user_id": as_oid(uid), "is_completed": False}, sort=[("created_at", -1)])
    if not goal:
        # fallback to latest goal
        goal = db.goals.find_one({"user_id": as_oid(uid)}, sort=[("created_at", -1)])

    q = int(qid) if qid is not None else None

    if q == 1:
        val = sum_amount({"user_id": as_oid(uid), "timestamp": {"$gte": today_start, "$lte": today_end}})
        return jsonify({"question_id": 1, "answer": f"You spent ₹{val:.2f} today."}), 200
    if q == 2:
        val = sum_amount({"user_id": as_oid(uid), "timestamp": {"$gte": week_start, "$lte": now}})
        return jsonify({"question_id": 2, "answer": f"You spent ₹{val:.2f} this week."}), 200
    if q == 3:
        val = sum_amount({"user_id": as_oid(uid), "timestamp": {"$gte": month_start, "$lte": now}})
        return jsonify({"question_id": 3, "answer": f"You spent ₹{val:.2f} this month."}), 200
    if q == 4:
        val = sum_amount({"user_id": as_oid(uid), "category": "Food"})
        return jsonify({"question_id": 4, "answer": f"You spent ₹{val:.2f} on Food."}), 200
    if q == 5:
        val = sum_amount({"user_id": as_oid(uid), "category": "Food", "timestamp": {"$gte": month_start, "$lte": now}})
        return jsonify({"question_id": 5, "answer": f"You spent ₹{val:.2f} on Food this month."}), 200
    if q == 6:
        top = top_category({"user_id": as_oid(uid)})
        if top:
            return jsonify({"question_id": 6, "answer": f"Your highest spending category is {top['_id']} (₹{float(top['total']):.2f})."}), 200
        return jsonify({"error": "No expenses found"}), 200
    if q == 7:
        top = top_category({"user_id": as_oid(uid)}, ascending=True)
        if top:
            return jsonify({"question_id": 7, "answer": f"Your lowest spending category is {top['_id']} (₹{float(top['total']):.2f})."}), 200
        return jsonify({"error": "No expenses found"}), 200
    if q == 8:
        val = sum_amount({"user_id": as_oid(uid), "payment_method": "UPI"})
        return jsonify({"question_id": 8, "answer": f"You spent ₹{val:.2f} using UPI."}), 200
    if q == 9:
        val = sum_amount({"user_id": as_oid(uid), "payment_method": "Cash"})
        return jsonify({"question_id": 9, "answer": f"You spent ₹{val:.2f} using Cash."}), 200
    if q == 10:
        doc = db.expenses.find_one({"user_id": as_oid(uid)}, sort=[("amount", -1)])
        if doc:
            return jsonify({"question_id": 10, "answer": f"Your biggest expense was ₹{float(doc['amount']):.2f} ({doc.get('description','')})."}), 200
        return jsonify({"error": "No expenses found"}), 200
    if q == 11:
        doc = db.expenses.find_one({"user_id": as_oid(uid)}, sort=[("amount", 1)])
        if doc:
            return jsonify({"question_id": 11, "answer": f"Your smallest expense was ₹{float(doc['amount']):.2f} ({doc.get('description','')})."}), 200
        return jsonify({"error": "No expenses found"}), 200
    if q == 12:
        cnt = count_docs({"user_id": as_oid(uid), "timestamp": {"$gte": month_start, "$lte": now}})
        return jsonify({"question_id": 12, "answer": f"You logged {cnt} expenses this month."}), 200
    if q == 13:
        top = top_date({"user_id": as_oid(uid)})
        if top:
            return jsonify({"question_id": 13, "answer": f"You spent the most on {top['_id']} (₹{float(top['total']):.2f})."}), 200
        return jsonify({"error": "No expenses found"}), 200
    if q == 14:
        month_total = sum_amount({"user_id": as_oid(uid), "timestamp": {"$gte": month_start, "$lte": now}})
        days_passed = now.day or 1
        avg = month_total / days_passed
        return jsonify({"question_id": 14, "answer": f"Your average daily spending this month is ₹{avg:.2f}."}), 200
    if q == 15:
        if goal:
            saved = float(goal.get("saved_amount", 0.0))
            return jsonify({"question_id": 15, "answer": f"You have saved ₹{saved:.2f} towards your goal '{goal.get('goal_name')}'."}), 200
        return jsonify({"error": "No goal found"}), 200
    if q == 16:
        if goal:
            target = float(goal.get("target_amount", 0.0))
            saved = float(goal.get("saved_amount", 0.0))
            left = max(target - saved, 0.0)
            return jsonify({"question_id": 16, "answer": f"₹{left:.2f} left to achieve your goal '{goal.get('goal_name')}'."}), 200
        return jsonify({"error": "No goal found"}), 200
    if q == 17:
        if goal:
            return jsonify({"question_id": 17, "answer": f"Your current goal is '{goal.get('goal_name')}'."}), 200
        return jsonify({"question_id": 17, "answer": "You have no active goals."}), 200
    if q == 18:
        if goal:
            return jsonify({"question_id": 18, "answer": f"Goal completed: {bool(goal.get('is_completed', False))}."}), 200
        return jsonify({"question_id": 18, "answer": "You have no goals."}), 200
    if q == 19:
        # Return a sentence only; data not included per user preference
        return jsonify({"question_id": 19, "answer": "Here are your recent 5 expenses."}), 200
    if q == 20:
        val = sum_amount({"user_id": as_oid(uid), "timestamp": {"$gte": year_start, "$lte": now}})
        return jsonify({"question_id": 20, "answer": f"You spent ₹{val:.2f} this year."}), 200

    return jsonify({"error": "Unknown question id or missing parameters"}), 400
