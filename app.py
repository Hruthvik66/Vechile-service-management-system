from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
import sqlite3
from datetime import date
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "vehicle-service-secret"
DB = "database.db"
UPLOAD_FOLDER = "uploads"
ALLOWED_EXTENSIONS = {"pdf", "jpg", "jpeg", "png", "webp"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024


def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS services (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            phone TEXT NOT NULL,
            vehicle TEXT NOT NULL,
            reg_no TEXT NOT NULL,
            service_type TEXT NOT NULL,
            service_date TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            amount REAL DEFAULT 0,
            bill_file TEXT
        )
    """)
    # Add bill_file to existing databases without changing existing records.
    columns = [row["name"] for row in conn.execute("PRAGMA table_info(services)").fetchall()]
    if "bill_file" not in columns:
        conn.execute("ALTER TABLE services ADD COLUMN bill_file TEXT")
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    conn.commit()
    conn.close()


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.errorhandler(413)
def file_too_large(error):
    flash("Bill file is too large. Maximum size is 10 MB.")
    return redirect(url_for("services"))


@app.route("/")
def index():
    conn = get_db()
    services = conn.execute(
        "SELECT * FROM services ORDER BY id DESC"
    ).fetchall()
    total = len(services)
    pending = sum(s["status"] == "Pending" for s in services)
    completed = sum(s["status"] == "Completed" for s in services)
    revenue = sum(s["amount"] for s in services if s["status"] == "Completed")
    conn.close()
    return render_template("index.html", services=services, total=total,
                           pending=pending, completed=completed, revenue=revenue)


@app.route("/add", methods=["GET", "POST"])
def add_service():
    if request.method == "POST":
        fields = ["customer", "phone", "vehicle", "reg_no",
                  "service_type", "service_date"]
        values = [request.form.get(field, "").strip() for field in fields]
        if not all(values):
            flash("Please fill in all required fields.")
            return redirect(url_for("add_service"))

        conn = get_db()
        conn.execute("""
            INSERT INTO services
            (customer, phone, vehicle, reg_no, service_type, service_date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, values)
        conn.commit()
        conn.close()
        flash("Service booking added successfully!")
        return redirect(url_for("services"))
    return render_template("add_service.html", today=date.today().isoformat())


@app.route("/services")
def services():
    search = request.args.get("search", "").strip()
    conn = get_db()
    records = conn.execute("""
        SELECT * FROM services
        WHERE customer LIKE ? OR reg_no LIKE ? OR phone LIKE ?
        ORDER BY id DESC
    """, (f"%{search}%", f"%{search}%", f"%{search}%")).fetchall()
    conn.close()
    return render_template("services.html", services=records, search=search)


@app.route("/update/<int:id>", methods=["POST"])
def update_service(id):
    status = request.form.get("status")
    amount_text = request.form.get("amount", "0")
    if status not in ["Pending", "In Progress", "Completed"]:
        flash("Invalid service status.")
        return redirect(url_for("services"))
    try:
        amount = float(amount_text)
        if amount < 0:
            raise ValueError
    except ValueError:
        flash("Enter a valid, non-negative amount.")
        return redirect(url_for("services"))

    conn = get_db()
    conn.execute("UPDATE services SET status = ?, amount = ? WHERE id = ?",
                 (status, amount, id))
    conn.commit()
    conn.close()
    flash("Service updated successfully!")
    return redirect(url_for("services"))


@app.route("/upload_bill/<int:id>", methods=["POST"])
def upload_bill(id):
    bill = request.files.get("bill_file")

    if not bill or bill.filename == "":
        flash("Please select a bill to upload.")
        return redirect(url_for("services"))

    if not allowed_file(bill.filename):
        flash("Invalid bill file. Use PDF, JPG, JPEG, PNG or WEBP.")
        return redirect(url_for("services"))

    conn = get_db()
    service = conn.execute(
        "SELECT status, bill_file FROM services WHERE id = ?", (id,)
    ).fetchone()

    if not service:
        conn.close()
        flash("Service record not found.")
        return redirect(url_for("services"))

    # Bills can only be uploaded after the service is completed.
    if service["status"] != "Completed":
        conn.close()
        flash("Bill can only be uploaded after the service is completed.")
        return redirect(url_for("services"))

    filename = secure_filename(bill.filename)
    extension = filename.rsplit(".", 1)[1].lower()
    final_name = f"service_{id}_{date.today().isoformat()}_{os.urandom(4).hex()}.{extension}"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    bill.save(os.path.join(UPLOAD_FOLDER, final_name))

    # Remove the previous bill if one was uploaded.
    old_file = service["bill_file"]
    if old_file:
        old_path = os.path.join(UPLOAD_FOLDER, old_file)
        if os.path.exists(old_path):
            os.remove(old_path)

    conn.execute("UPDATE services SET bill_file = ? WHERE id = ?", (final_name, id))
    conn.commit()
    conn.close()
    flash("Bill uploaded successfully!")
    return redirect(url_for("services"))


@app.route("/bill/<int:id>")
def view_bill(id):
    conn = get_db()
    service = conn.execute(
        "SELECT bill_file FROM services WHERE id = ?", (id,)
    ).fetchone()
    conn.close()

    if not service or not service["bill_file"]:
        flash("No bill uploaded for this service.")
        return redirect(url_for("services"))

    return send_from_directory(
        app.config["UPLOAD_FOLDER"], service["bill_file"]
    )


@app.route("/delete/<int:id>", methods=["POST"])
def delete_service(id):
    conn = get_db()
    service = conn.execute(
        "SELECT bill_file FROM services WHERE id = ?", (id,)
    ).fetchone()

    conn.execute("DELETE FROM services WHERE id = ?", (id,))
    conn.commit()
    conn.close()

    if service and service["bill_file"]:
        bill_path = os.path.join(UPLOAD_FOLDER, service["bill_file"])
        if os.path.exists(bill_path):
            os.remove(bill_path)

    flash("Service record deleted.")
    return redirect(url_for("services"))


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
