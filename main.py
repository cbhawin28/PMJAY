import os
import io
import uuid
import random
import fitz  # PyMuPDF
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash, jsonify
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from flask_dance.contrib.google import make_google_blueprint, google

# ----------------- APP + CONFIG -----------------
app = Flask(__name__)
app.secret_key = "super_secret_key"

google_bp = make_google_blueprint(
    client_id="YOUR_GOOGLE_CLIENT_ID",
    client_secret="YOUR_GOOGLE_CLIENT_SECRET",
    redirect_url="/google/authorized",
    scope=["profile", "email"]
)
app.register_blueprint(google_bp, url_prefix="/google")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_IMG = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
ALLOWED_PDF = {".pdf"}

# ----------------- USERS (demo, replace with DB) -----------------
USERS = {}

# ----------------- CARD CONFIG -----------------
DPI = 300
MM_TO_INCH = 25.4
CARD_W_MM, CARD_H_MM = 90, 55
CARD_W_PT = CARD_W_MM * 72 / MM_TO_INCH
CARD_H_PT = CARD_H_MM * 72 / MM_TO_INCH

BORDER_COLOR = colors.grey
BORDER_DASH = (1, 2)

# Crop coordinates in pixels @DPI
CROP_COORDS = [
    (441, 393, 1271, 647),  # Front (x, y, w, h)
    (441, 1040, 1271, 647)  # Back (y + h for next card)
]

# ----------------- HELPERS -----------------
def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            flash("Please login first.", "warning")
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def pil_from_pdf_page(page, dpi=DPI):
    mat = fitz.Matrix(dpi/72, dpi/72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    return Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

def try_crop(img, coords):
    x, y, w, h = coords
    if x + w <= img.width and y + h <= img.height:
        return img.crop((x, y, x + w, y + h))
    return img

def resize_card(img):
    w_px = int(CARD_W_MM / MM_TO_INCH * DPI)
    h_px = int(CARD_H_MM / MM_TO_INCH * DPI)
    return img.resize((w_px, h_px), Image.LANCZOS)

def dotted_rect(c, x, y, w, h):
    c.setStrokeColor(BORDER_COLOR)
    c.setDash(*BORDER_DASH)
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.setDash()

def center_grid_positions(page_w, page_h, cols=2, rows=5, gap_pt=10):
    total_w = cols*CARD_W_PT + (cols-1)*gap_pt
    total_h = rows*CARD_H_PT + (rows-1)*gap_pt
    start_x = (page_w - total_w)/2
    start_y = (page_h - total_h)/2
    pos = []
    for r in range(rows):
        for c in range(cols):
            x = start_x + c*(CARD_W_PT + gap_pt)
            y = page_h - (start_y + (r+1)*CARD_H_PT + r*gap_pt)
            pos.append((x,y))
    return pos

def serialize_pil(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", dpi=(DPI,DPI))
    buf.seek(0)
    return buf

def collect_normal(files):
    fronts = []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext in ALLOWED_PDF:
            doc = fitz.open(stream=f.read(), filetype="pdf")
            f.stream.seek(0)
            for page in doc:
                img = pil_from_pdf_page(page)
                # Crop using your coordinates
                front = try_crop(img, (441, 393, 1271, 647))  # (CROP_X, CROP_Y, CROP_W, CROP_H)
                front = resize_card(front)
                fronts.append(front)
        elif ext in ALLOWED_IMG:
            img = Image.open(f.stream).convert("RGB")
            fronts.append(resize_card(img))
            f.stream.seek(0)
    return fronts

def collect_duplex(files):
    pairs = []
    for f in files:
        ext = os.path.splitext(f.filename)[1].lower()
        if ext in ALLOWED_PDF:
            doc = fitz.open(stream=f.read(), filetype="pdf")
            f.stream.seek(0)
            for page in doc:
                img = pil_from_pdf_page(page)
                front = try_crop(img, CROP_COORDS[0])
                back = try_crop(img, CROP_COORDS[1])
                front = resize_card(front)
                back = resize_card(back)
                pairs.append((front, back))
        elif ext in ALLOWED_IMG:
            img = Image.open(f.stream).convert("RGB")
            rimg = resize_card(img)
            pairs.append((rimg, rimg.copy()))
            f.stream.seek(0)
    return pairs

def build_pdf(files, duplex=False):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4
    positions = center_grid_positions(page_w, page_h)

    if not duplex:
        fronts = collect_normal(files)
        for start in range(0, len(fronts), 10):
            batch = fronts[start:start+10]
            for img, (x, y) in zip(batch, positions):
                c.drawImage(ImageReader(serialize_pil(img)), x, y, CARD_W_PT, CARD_H_PT)
                dotted_rect(c, x, y, CARD_W_PT, CARD_H_PT)
            c.showPage()
    else:
        pairs = collect_duplex(files)
        for start in range(0, len(pairs), 10):
            batch = pairs[start:start+10]
            # Front page
            for (f,_), (x,y) in zip(batch, positions):
                c.drawImage(ImageReader(serialize_pil(f)), x, y, CARD_W_PT, CARD_H_PT)
                dotted_rect(c, x, y, CARD_W_PT, CARD_H_PT)
            c.showPage()
            # Back page mirrored
            for (_,b), (x,y) in zip(batch, positions):
                mx = page_w - x - CARD_W_PT
                c.drawImage(ImageReader(serialize_pil(b)), mx, y, CARD_W_PT, CARD_H_PT)
                dotted_rect(c, mx, y, CARD_W_PT, CARD_H_PT)
            c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()

# ----------------- ROUTES -----------------
@app.route("/")
def home():
    return redirect(url_for("dashboard"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email").lower()
        mobile = request.form.get("mobile")
        otp = request.form.get("otp")
        password = request.form.get("password")
        if not (name and email and mobile and otp and password):
            flash("All fields are required.", "error")
            return render_template("signup.html")
        if email in USERS:
            flash("User already exists.", "error")
            return render_template("signup.html")
        # OTP check
        if "otp" not in session or "otp_mobile" not in session or session["otp_mobile"] != mobile or session["otp"] != otp:
            flash("Invalid or expired OTP.", "error")
            return render_template("signup.html")
        USERS[email] = {"username": name, "email": email, "mobile": mobile, "password": password}
        session.pop("otp", None)
        session.pop("otp_mobile", None)
        flash("Signup successful! Please login.", "success")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        email = request.form.get("email").lower()
        password = request.form.get("password")
        u = USERS.get(email)
        if u and u["password"]==password:
            session["user"] = u["username"]
            flash("Login success", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html", user=session.get("user"))

@app.route('/generate_card', methods=['POST'])
def generate_card():
    files = request.files.getlist("files")
    files = [f for f in files if f and f.filename]
    if not files:
        flash("Select files", "warning")
        return redirect(url_for("dashboard"))
    pdf_bytes = build_pdf(files, duplex=False)

    # Find next available number for filename
    static_dir = os.path.join(BASE_DIR, "static")
    existing = [f for f in os.listdir(static_dir) if f.startswith("PRINTPERFECT_A4_") and f.endswith(".pdf")]
    numbers = []
    for fname in existing:
        try:
            num = int(fname.replace("PRINTPERFECT_A4_", "").replace(".pdf", ""))
            numbers.append(num)
        except:
            pass
    next_num = max(numbers) + 1 if numbers else 1
    out_name = f"PRINTPERFECT_A4_{next_num}.pdf"
    out_path = os.path.join(static_dir, out_name)
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    pdf_url = url_for('static', filename=out_name)
    flash("PDF created successfully!", "success")
    return render_template("dashboard.html", user=session.get("user"), pdf_url=pdf_url)

@app.route("/generate_duplex_card", methods=["POST"])
def generate_duplex_card():
    files = request.files.getlist("files")
    files = [f for f in files if f and f.filename]
    if not files:
        flash("Select files", "warning")
        return redirect(url_for("dashboard"))
    pdf_bytes = build_pdf(files, duplex=True)
    out_name = "output_duplex.pdf"
    out_path = os.path.join(BASE_DIR, "static", out_name)
    with open(out_path, "wb") as f:
        f.write(pdf_bytes)
    pdf_url = url_for('static', filename=out_name)
    flash("Duplex PDF created successfully!", "success")
    return render_template("dashboard.html", user=session.get("user"), pdf_url=pdf_url)

@app.route("/send_otp", methods=["POST"])
def send_otp():
    data = request.get_json()
    mobile = data.get("mobile")
    if not mobile or len(mobile) != 10 or not mobile.isdigit():
        return jsonify({"status": "error", "message": "Invalid mobile number"})
    otp = str(random.randint(100000, 999999))
    session["otp"] = otp
    session["otp_mobile"] = mobile
    # In real app, send OTP via SMS API here
    print(f"OTP for {mobile}: {otp}")  # For demo, print in console
    return jsonify({"status": "sent"})

@app.route("/google-login")
def google_login():
    if not google.authorized:
        return redirect(url_for("google.login"))
    resp = google.get("/oauth2/v2/userinfo")
    if resp.ok:
        user_info = resp.json()
        email = user_info["email"]
        name = user_info.get("name", "")
        # User ko USERS dict me add karein (agar nahi hai)
        if email not in USERS:
            USERS[email] = {"username": name, "email": email, "password": None}
        session["user"] = email
        flash("Google से लॉगिन सफल!", "success")
        return redirect(url_for("dashboard"))
    flash("Google लॉगिन में समस्या है.", "error")
    return redirect(url_for("login"))

# ----------------- RUN APP -----------------
if __name__=="__main__":
    app.run(debug=True)
