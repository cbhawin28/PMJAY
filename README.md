# PDF → 90×60 mm Card Layout (Gujarati)

- Crop coordinates: **x=441, y=393, w=1271, h=647**
- Card size (resize): **90mm × 60mm** @ 300 DPI
- A4 layout: **5 rows × 2 columns = 10 per page**
- Multiple PDFs supported

## Install
1) Python 3.9+
2) Poppler install (Windows):
   - https://github.com/oschwartz10612/poppler-windows/releases/
   - `bin` folder no path `PATH` ma add karo
3) Dependencies:
```bash
pip install -r requirements.txt
```

## Run
```bash
python app.py
```
Open: http://127.0.0.1:5000/

## Notes
- Layout auto-center thay che: page par equal gap calculate kari ne.
- Jo A4 ma space ochhu hoy to gap 0 thai jashe (cards overlap nahi thay).
- Jo crop shift dekhae to original PDF na DPI/size alag hoy sake. A case ma tame page ne same DPI (300) par convert thai che—pan crop coords fixed che.
