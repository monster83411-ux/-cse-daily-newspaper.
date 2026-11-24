"""newspaper.py - turns finished stories into a 2-column newspaper PDF (ReportLab)."""

import os
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
)

W, H = A4
M, GAP, MAST = 14 * mm, 8 * mm, 40 * mm
COL = (W - 2 * M - GAP) / 2
INK, ACCENT, GREY = (
    colors.HexColor("#111827"),
    colors.HexColor("#b91c1c"),
    colors.HexColor("#6b7280"),
)

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_FOLDERS = [os.path.join(HERE, "fonts"), "/usr/share/fonts/truetype/dejavu"]
FONT_FILES = {
    "CSE-Sans": "DejaVuSans.ttf",
    "CSE-Bold": "DejaVuSans-Bold.ttf",
    "CSE-Italic": "DejaVuSans-Oblique.ttf",
    "CSE-Serif": "DejaVuSerif-Bold.ttf",
}
PLAIN = {
    "sans": "Helvetica",
    "bold": "Helvetica-Bold",
    "italic": "Helvetica-Oblique",
    "serif": "Times-Bold",
}
FONTS = dict(PLAIN)  # filled in by load_fonts()
GLYPHS = None  # set of characters the font can draw (None = plain mode)


def load_fonts():
    """Use DejaVu (draws the rupee sign, curly quotes, accents). Falls back to plain Helvetica."""
    global FONTS, GLYPHS
    for folder in FONT_FOLDERS:
        paths = {n: os.path.join(folder, f) for n, f in FONT_FILES.items()}
        if all(os.path.exists(p) for p in paths.values()):
            try:
                for name, path in paths.items():
                    pdfmetrics.registerFont(TTFont(name, path))
                FONTS = {
                    "sans": "CSE-Sans",
                    "bold": "CSE-Bold",
                    "italic": "CSE-Italic",
                    "serif": "CSE-Serif",
                }
                GLYPHS = set(
                    chr(c) for c in pdfmetrics.getFont("CSE-Sans").face.charToGlyph
                )
                return "unicode fonts from " + folder
            except Exception:  # noqa: BLE001 - a bad font file must not stop the paper
                pass
    FONTS, GLYPHS = dict(PLAIN), None
    return "plain Helvetica (rupee sign and some symbols will be dropped)"


def safe(text):
    """Drop characters the font cannot draw (they would print as black boxes), then escape &, <, >."""
    text = (text or "").replace("\u00a0", " ")
    if GLYPHS is None:
        text = text.encode("cp1252", errors="ignore").decode("cp1252")
    else:
        text = "".join(ch for ch in text if ch in GLYPHS or ch == " ")
    return escape("".join(ch for ch in text if ch >= " "))


def styles():
    f = FONTS
    return {
        "section": ParagraphStyle(
            "sec",
            fontName=f["bold"],
            fontSize=8.6,
            leading=12,
            textColor=colors.white,
            backColor=INK,
            borderPadding=(3, 4, 3, 4),
            spaceBefore=10,
            spaceAfter=7,
            keepWithNext=1,
        ),
        "head": ParagraphStyle(
            "head",
            fontName=f["serif"],
            fontSize=11.2,
            leading=14,
            textColor=INK,
            spaceBefore=4,
        ),
        "body": ParagraphStyle(
            "body",
            fontName=f["sans"],
            fontSize=8.5,
            leading=12.2,
            alignment=TA_LEFT,
            spaceBefore=2,
        ),
        "src": ParagraphStyle(
            "src",
            fontName=f["italic"],
            fontSize=7.2,
            leading=10,
            textColor=GREY,
            spaceBefore=2,
            spaceAfter=9,
        ),
        "note": ParagraphStyle(
            "note", fontName=f["italic"], fontSize=8.5, leading=12.2, textColor=GREY
        ),
    }


def source_line(story):
    host = urlparse(story["link"]).netloc.replace("www.", "")
    where = "" if (not host or "news.google.com" in host) else f" ({host})"
    url = escape(story["link"], {'"': "&quot;"})
    tag = "" if story["ai"] else " | shown without AI summary"
    return (
        f'Source: <font name="{FONTS["bold"]}">{safe(story["source"])}</font>{safe(where)} | '
        f'<link href="{url}" color="#1d4ed8"><u>Read original</u></link>{safe(tag)}'
    )


def draw_first(c, doc):
    c.saveState()
    c.setFillColor(INK)
    c.setFont(FONTS["serif"], 42)
    c.drawCentredString(W / 2, H - M - 14 * mm, "CSE DAILY")
    c.setFont(FONTS["sans"], 8)
    c.setFillColor(GREY)
    c.drawCentredString(
        W / 2, H - M - 20 * mm, "ENGINEERING & COMPUTER SCIENCE NEWS  |  MORNING EDITION"
    )
    c.setStrokeColor(ACCENT)
    c.setLineWidth(2)
    c.line(M, H - M - 23 * mm, W - M, H - M - 23 * mm)
    c.setFillColor(INK)
    c.setFont(FONTS["bold"], 8.5)
    c.drawString(M, H - M - 29 * mm, doc.edition_date)
    c.drawRightString(W - M, H - M - 29 * mm, doc.edition_info)
    c.setStrokeColor(INK)
    c.setLineWidth(0.6)
    c.line(M, H - M - 32 * mm, W - M, H - M - 32 * mm)
    c.restoreState()
    draw_footer(c, doc)


def draw_footer(c, doc):
    c.saveState()
    c.setFont(FONTS["sans"], 6.8)
    c.setFillColor(GREY)
    c.drawString(
        M,
        9 * mm,
        "Auto-generated from public sources. AI writes the summaries - always check the original link.",
    )
    c.drawRightString(W - M, 9 * mm, f"Page {doc.page}")
    c.restoreState()


def build_pdf(path, stories_by_section, edition_date, notes=()):
    mode = load_fonts()
    print("  fonts:", mode)
    S = styles()
    total = sum(len(v) for v in stories_by_section.values())
    doc = BaseDocTemplate(
        path, pagesize=A4, title=f"CSE Daily - {edition_date}", author="CSE Daily Bot"
    )
    doc.edition_date, doc.edition_info = edition_date, f"{total} stories"
    bottom = 14 * mm

    def frames(top):
        kw = dict(leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        return [
            Frame(M, bottom, COL, top - bottom, id="a", **kw),
            Frame(M + COL + GAP, bottom, COL, top - bottom, id="b", **kw),
        ]

    doc.addPageTemplates(
        [
            PageTemplate(id="first", frames=frames(H - M - MAST), onPage=draw_first),
            PageTemplate(id="later", frames=frames(H - M), onPage=draw_footer),
        ]
    )

    flow = [NextPageTemplate("later")]
    for note in notes:
        flow.append(Paragraph(safe(note), S["note"]))
    for section, stories in stories_by_section.items():
        flow.append(Paragraph(safe(section.upper()), S["section"]))
        if not stories:
            flow.append(Paragraph("No new stories in this section today.", S["note"]))
            continue
        for s in stories:
            flow.append(
                KeepTogether(
                    [
                        Paragraph(safe(s["headline"]), S["head"]),
                        Paragraph(safe(s["body"]), S["body"]),
                        Paragraph(source_line(s), S["src"]),
                    ]
                )
            )
    flow.append(Spacer(1, 1))
    doc.build(flow)
    return path
