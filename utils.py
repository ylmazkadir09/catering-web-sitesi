
from __future__ import annotations
import io
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

def df_to_excel_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    out = io.BytesIO()
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for name, df in sheets.items():
            df.to_excel(writer, index=False, sheet_name=name[:31])
    return out.getvalue()

def require_cols(df: pd.DataFrame, required: list[str], sheet: str):
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{sheet} sayfasında eksik kolon(lar): {missing}")

def simple_table_pdf(title: str, lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    w, h = A4
    y = h - 50
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, title)
    y -= 25
    c.setFont("Helvetica", 10)
    for line in lines:
        if y < 50:
            c.showPage()
            y = h - 50
            c.setFont("Helvetica", 10)
        c.drawString(40, y, line[:120])
        y -= 14
    c.showPage()
    c.save()
    return buf.getvalue()
