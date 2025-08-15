from flask import Flask, render_template, request, send_file
from pdf2image import convert_from_path
from PIL import Image, ImageDraw
import os
import tempfile

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()

# --- SETTINGS ---
dpi = 300  # Conversion DPI

# Crop coordinates
CROP_X, CROP_Y, CROP_W, CROP_H = 441, 393, 1271, 647

# Card size: 90mm x 55mm
CARD_W_MM, CARD_H_MM = 95, 55

# Grid: 5 rows × 2 columns = 10 cards/page
COLS, ROWS = 2, 5

# Helpers
def mm_to_px(mm, dpi=300):
    return int(round((mm / 25.4) * dpi))

CARD_W_PX = mm_to_px(CARD_W_MM, dpi)
CARD_H_PX = mm_to_px(CARD_H_MM, dpi)

A4_W_PX = mm_to_px(210, dpi)
A4_H_PX = mm_to_px(297, dpi)

def draw_dashed_rectangle(draw, xy, dash_length=10, gap_length=6, outline="black", width=2):
    x1, y1, x2, y2 = xy
    # Top
    x = x1
    while x < x2:
        draw.line([(x, y1), (min(x + dash_length, x2), y1)], fill=outline, width=width)
        x += dash_length + gap_length
    # Bottom
    x = x1
    while x < x2:
        draw.line([(x, y2), (min(x + dash_length, x2), y2)], fill=outline, width=width)
        x += dash_length + gap_length
    # Left
    y = y1
    while y < y2:
        draw.line([(x1, y), (x1, min(y + dash_length, y2))], fill=outline, width=width)
        y += dash_length + gap_length
    # Right
    y = y1
    while y < y2:
        draw.line([(x2, y), (x2, min(y + dash_length, y2))], fill=outline, width=width)
        y += dash_length + gap_length

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        files = request.files.getlist("pdf_files")
        if not files:
            return "Koi PDF upload nathi kari.", 400

        all_cards = []

        for f in files:
            if not f or f.filename.strip() == "":
                continue

            pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], f.filename)
            f.save(pdf_path)

            pages = convert_from_path(pdf_path, dpi=dpi)

            for pg in pages:
                pw, ph = pg.size

                # Crop safety
                x1 = max(0, min(CROP_X, pw - 1))
                y1 = max(0, min(CROP_Y, ph - 1))
                x2 = max(x1 + 1, min(CROP_X + CROP_W, pw))
                y2 = max(y1 + 1, min(CROP_Y + CROP_H, ph))

                card = pg.crop((x1, y1, x2, y2)).resize((CARD_W_PX, CARD_H_PX), Image.LANCZOS)

                # White canvas + dashed border
                canvas = Image.new("RGB", (CARD_W_PX, CARD_H_PX), "white")
                canvas.paste(card, (0, 0))
                d = ImageDraw.Draw(canvas)
                draw_dashed_rectangle(d, (0, 0, CARD_W_PX-1, CARD_H_PX-1), outline="black", width=2)
                all_cards.append(canvas)

        if not all_cards:
            return "Valid pages madya nathi.", 400

        # ── Centered grid on A4 ──
        cards_per_page = COLS * ROWS
        gap_x = (A4_W_PX - (COLS * CARD_W_PX)) // (COLS + 1)
        gap_y = (A4_H_PX - (ROWS * CARD_H_PX)) // (ROWS + 1)

        pages_out = []
        for i in range(0, len(all_cards), cards_per_page):
            page = Image.new("RGB", (A4_W_PX, A4_H_PX), "white")
            dp = ImageDraw.Draw(page)
            draw_dashed_rectangle(dp, (0, 0, A4_W_PX-1, A4_H_PX-1), outline="black", width=3)

            for idx, card in enumerate(all_cards[i:i+cards_per_page]):
                c = idx % COLS
                r = idx // COLS
                x = gap_x + c * (CARD_W_PX + gap_x)
                y = gap_y + r * (CARD_H_PX + gap_y)
                page.paste(card, (x, y))

            pages_out.append(page)

        out_path = os.path.join(app.config['UPLOAD_FOLDER'], "cards_layout_95x57.pdf")
        pages_out[0].save(out_path, save_all=True, append_images=pages_out[1:], resolution=dpi)
        return send_file(out_path, as_attachment=True)

    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
