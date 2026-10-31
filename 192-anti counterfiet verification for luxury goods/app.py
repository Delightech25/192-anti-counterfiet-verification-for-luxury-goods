from flask import Flask, render_template, request, redirect, session, url_for
import sqlite3
import hashlib
import hmac
import os
import qrcode
from datetime import datetime

app = Flask(__name__)
app.secret_key = "super_secret_session_key"  # change in production

DATABASE = "database.db"
SECRET_KEY = "very_secure_product_key"


# ==========================
# Database Initialization
# ==========================
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()

    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT
                )''')

    # Products table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    serial TEXT,
                    token TEXT UNIQUE,
                    scan_count INTEGER DEFAULT 0,
                    created_at TEXT
                )''')

    conn.commit()
    conn.close()


# ==========================
# Utility Functions
# ==========================

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token(product_id):
    return hmac.new(
        SECRET_KEY.encode(),
        str(product_id).encode(),
        hashlib.sha256
    ).hexdigest()


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


# ==========================
# Routes
# ==========================

@app.route('/')
def index():
    return render_template("index.html")


# -------- Register --------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])

        conn = get_db_connection()
        try:
            conn.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                         (username, password))
            conn.commit()
            conn.close()
            return redirect('/login')
        except:
            conn.close()
            return "Username already exists!"

    return render_template("register.html")


# -------- Login --------
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?",
                            (username, password)).fetchone()
        conn.close()

        if user:
            session['admin'] = username
            return redirect('/dashboard')
        else:
            return "Invalid credentials!"

    return render_template("login.html")


# -------- Logout --------
@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# -------- Dashboard --------
@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'admin' not in session:
        return redirect('/login')

    conn = get_db_connection()

    if request.method == 'POST':
        name = request.form['name']
        serial = request.form['serial']

        # Insert temporary product
        cursor = conn.cursor()
        cursor.execute("INSERT INTO products (name, serial, token, created_at) VALUES (?, ?, ?, ?)",
                       (name, serial, "temp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        product_id = cursor.lastrowid

        # Generate secure token
        token = generate_token(product_id)

        # Update token
        cursor.execute("UPDATE products SET token=? WHERE id=?",
                       (token, product_id))
        conn.commit()

        # Generate QR Code
        if not os.path.exists("static/qr_codes"):
            os.makedirs("static/qr_codes")

        verify_url = f"http://127.0.0.1:5000/verify/{token}"
        img = qrcode.make(verify_url)
        img.save(f"static/qr_codes/{product_id}.png")

    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()

    return render_template("dashboard.html", products=products)


# -------- Verify Product --------
@app.route('/verify')
def verify():
    token = request.args.get('token')

    if not token:
        return "Invalid Request"

    conn = get_db_connection()
    product = conn.execute(
        "SELECT * FROM products WHERE token=?",
        (token,)
    ).fetchone()

    if product:
        scan_count = product['scan_count'] + 1
        conn.execute(
            "UPDATE products SET scan_count=? WHERE token=?",
            (scan_count, token)
        )
        conn.commit()

        if scan_count > 5:
            status = "⚠ Suspicious - Multiple scans detected"
        else:
            status = "✅ Genuine Product"

        product_name = product['name']
        serial = product['serial']
    else:
        status = "❌ Invalid / Fake Product"
        product_name = None
        serial = None

    conn.close()

    return render_template(
        "result.html",
        status=status,
        product_name=product_name,
        serial=serial
    )

# ==========================
# Main
# ==========================
if __name__ == '__main__':
    init_db()
    app.run(host="127.0.0.1", port=5055, debug=True, use_reloader=False)