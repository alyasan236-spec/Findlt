
from flask import Flask, request, jsonify, redirect, session
from flask_cors import CORS
import os
import uuid
from werkzeug.utils import secure_filename
import sqlite3
import re
from difflib import SequenceMatcher
from werkzeug.security import generate_password_hash

app = Flask(__name__)
app.secret_key = "findit_secret_key_2026"
CORS(app)
UPLOAD_FOLDER = "static/uploads"

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def init_db():
    conn = sqlite3.connect("findit.db")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            university_id TEXT UNIQUE,
            password TEXT NOT NULL
        )
    """)

    columns = [
        row[1] for row in conn.execute("PRAGMA table_info(users)")
    ]

    if "university_id" not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN university_id TEXT"
        )

    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        unique_university_id ON users(university_id)
    """)

        # Items table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT NOT NULL,
            location TEXT NOT NULL,
            date TEXT NOT NULL,
            phone TEXT NOT NULL,
            image_url TEXT
        )
    """)

    
    item_columns = [
        row[1] for row in conn.execute("PRAGMA table_info(items)")
    ]

    if "user_id" not in item_columns:
        conn.execute("""
            ALTER TABLE items ADD COLUMN user_id INTEGER
        """)

    # Claims table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS claims (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            claimant_name TEXT NOT NULL,
            university_id TEXT NOT NULL,
            contact TEXT NOT NULL,
            proof_details TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()



from flask import render_template
def calculate_similarity(item1, item2):
    def clean_text(text):
        return set(re.findall(r'\w+', str(text).lower()))

    text1 = clean_text(item1["name"] + " " + item1["description"])
    text2 = clean_text(item2["name"] + " " + item2["description"])

    if not text1 or not text2:
        text_score = 0
    else:
        text_score = len(text1 & text2) / len(text1 | text2)

    category_score = 1 if item1["category"].lower() == item2["category"].lower() else 0

    location_score = SequenceMatcher(
        None,
        item1["location"].lower(),
        item2["location"].lower()
    ).ratio()

    final_score = (
        text_score * 0.5 +
        category_score * 0.3 +
        location_score * 0.2
    )

    return round(final_score * 100, 2)

@app.route("/")
def home():
    return render_template("index.html")
@app.route("/register", methods=["GET"])
def register_page():
    return render_template("register.html")
@app.route("/login", methods=["GET"])
def login_page():
    return render_template("login.html")

@app.route("/items", methods=["GET", "POST"])
def manage_items():

    if request.method == "POST":

        if "user_id" not in session:
            return jsonify({"error": "Please login first"}), 401

        name = request.form.get("name")
        category = request.form.get("category")
        item_type = request.form.get("type")
        description = request.form.get("description")
        location = request.form.get("location")
        date = request.form.get("date")
        phone = request.form.get("phone")

        required_fields = {
            "Item Name": name,
            "Category": category,
            "Report Type": item_type,
            "Description": description,
            "Location": location,
            "Date": date,
            "Phone Number": phone
        }

        missing_fields = [
            field for field, value in required_fields.items()
            if not value or not value.strip()
        ]

        if missing_fields:
            return jsonify({
                "error": "Please fill in: " + ", ".join(missing_fields)
            }), 400

        if item_type not in ["Lost", "Found"]:
            return jsonify({"error": "Invalid report type"}), 400

        image = request.files.get("image")
        image_url = None

        if image and image.filename:
            filename = secure_filename(image.filename)
            extension = os.path.splitext(filename)[1].lower()

            if not filename or extension not in [
                ".jpg", ".jpeg", ".png", ".gif", ".webp"
            ]:
                return jsonify({"error": "Invalid image format"}), 400

            unique_name = str(uuid.uuid4()) + extension

            image.save(
                os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
            )

            image_url = "/static/uploads/" + unique_name

        conn = sqlite3.connect("findit.db")

        cursor = conn.execute("""
            INSERT INTO items
            (name, category, type, description, location, date, phone, image_url, user_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            name, category, item_type, description,
            location, date, phone, image_url,
            session["user_id"]
        ))

        item_id = cursor.lastrowid

        conn.commit()
        conn.close()

        return jsonify({
            "message": "Item added successfully",
            "item_id": item_id
        }), 201

    conn = sqlite3.connect("findit.db")
    conn.row_factory = sqlite3.Row

    rows = conn.execute("SELECT * FROM items ORDER BY id DESC").fetchall()

    saved_items = [dict(row) for row in rows]

    conn.close()

    return jsonify(saved_items)

@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}

    name = data.get("name")
    email = data.get("email")
    university_id = data.get("university_id")
    password = data.get("password")

    if not all([name, email, university_id, password]):
        return jsonify({
            "error": "Name, email, University ID and password are required"
        }), 400

    if len(password) < 8:
        return jsonify({
            "error": "Password must be at least 8 characters"
        }), 400

    hashed_password = generate_password_hash(password)

    try:
        conn = sqlite3.connect("findit.db")
        conn.execute(
            """INSERT INTO users
            (name, email, university_id, password)
            VALUES (?, ?, ?, ?)""",
            (name, email, university_id, hashed_password)
        )
        conn.commit()
        conn.close()

        return jsonify({
            "message": "Account created successfully"
        }), 201

    except sqlite3.IntegrityError:
        return jsonify({
            "error": "This email or University ID is already registered"
        }), 409

from werkzeug.security import check_password_hash

@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}

    university_id = data.get("university_id")
    password = data.get("password")

    if not university_id or not password:
        return jsonify({
            "error": "University ID and password are required"
        }), 400

    conn = sqlite3.connect("findit.db")
    conn.row_factory = sqlite3.Row

    user = conn.execute(
        "SELECT * FROM users WHERE university_id = ?",
        (university_id,)
    ).fetchone()

    conn.close()

    if user is None or not check_password_hash(user["password"], password):
        return jsonify({
            "error": "Invalid University ID or password"
        }), 401
    if user is None or not check_password_hash(user["password"], password):
            return jsonify({
                "error": "Invalid University ID or password"
            }), 401
    session["user_id"] = user["id"]

    return jsonify({
        "message": "Login successful",
        "user": {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "university_id": user["university_id"]
        }
    }), 200
@app.route("/browse")
def browse_items():
    conn = sqlite3.connect("findit.db")
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        "SELECT * FROM items ORDER BY id DESC"
    ).fetchall()

    saved_items = [dict(row) for row in rows]

    conn.close()

    for item in saved_items:
        item["matches"] = []

        for other in saved_items:
            if item["id"] == other["id"]:
                continue

            if item["type"].lower() == other["type"].lower():
                continue

            score = calculate_similarity(item, other)

            if score >= 20:
                item["matches"].append({
                    "name": other["name"],
                    "type": other["type"],
                    "location": other["location"],
                    "score": score
                })

        item["matches"].sort(
            key=lambda match: match["score"],
            reverse=True
        )

    return render_template("items.html", items=saved_items)
@app.route("/add-item")
def add_item():
    return render_template("add_item.html")
@app.route("/claim/<int:item_id>", methods=["GET", "POST"])
def claim_item(item_id):

    conn = sqlite3.connect("findit.db")
    conn.row_factory = sqlite3.Row

    item = conn.execute(
        "SELECT * FROM items WHERE id = ? AND type = 'Found'",
        (item_id,)
    ).fetchone()

    if item is None:
        conn.close()
        return "Found item not found", 404

    if request.method == "POST":
        claimant_name = request.form.get("claimant_name", "").strip()
        university_id = request.form.get("university_id", "").strip()
        contact = request.form.get("contact", "").strip()
        proof_details = request.form.get("proof_details", "").strip()

        if not all([claimant_name, university_id, contact, proof_details]):
            conn.close()
            return "Please fill in all fields", 400

        conn.execute("""
            INSERT INTO claims
            (item_id, claimant_name, university_id, contact, proof_details)
            VALUES (?, ?, ?, ?, ?)
        """, (item_id, claimant_name, university_id, contact, proof_details))

        conn.commit()
        conn.close()

        return "Claim request submitted successfully! Your request is pending review."

    conn.close()
    return render_template("claim.html", item=dict(item))
@app.route("/claims")
def view_claims():

    if "user_id" not in session:
        return redirect("/login")

    conn = sqlite3.connect("findit.db")
    conn.row_factory = sqlite3.Row

    claims = conn.execute("""
        SELECT claims.*, items.name AS item_name
        FROM claims
        JOIN items ON claims.item_id = items.id
        WHERE items.user_id = ?
        ORDER BY claims.created_at DESC
    """, (session["user_id"],)).fetchall()

    conn.close()

    return render_template("claims.html", claims=claims)


@app.route("/claims/update/<int:claim_id>", methods=["POST"])
def update_claim(claim_id):

    if "user_id" not in session:
        return redirect("/login")

    status = request.form.get("status")

    if status not in ["Approved", "Rejected"]:
        return "Invalid status", 400

    conn = sqlite3.connect("findit.db")

    claim = conn.execute("""
        SELECT claims.id
        FROM claims
        JOIN items ON claims.item_id = items.id
        WHERE claims.id = ? AND items.user_id = ?
    """, (claim_id, session["user_id"])).fetchone()

    if claim is None:
        conn.close()
        return "Unauthorized", 403

    conn.execute(
        "UPDATE claims SET status = ? WHERE id = ?",
        (status, claim_id)
    )

    conn.commit()
    conn.close()

    return redirect("/claims")
if __name__ == "__main__":
    app.run(debug=True)