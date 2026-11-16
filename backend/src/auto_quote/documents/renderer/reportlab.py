from datetime import date
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from auto_quote.documents.renderer.quote_renderer import QuoteRenderer
from auto_quote.models.branding import Branding
from auto_quote.models.quote import CURRENCY, Quote, QuoteLanguage, QuoteLine


PAGE_MARGIN = 18 * mm
LOGO_MAX_WIDTH = 70 * mm
DEFAULT_FONT = "Helvetica"
DEFAULT_BOLD_FONT = "Helvetica-Bold"
REGULAR_WEIGHT = 400
BOLD_WEIGHT = 700
COLUMN_WIDTHS = [12 * mm, 78 * mm, 16 * mm, 20 * mm, 24 * mm, 24 * mm]
GREY = colors.HexColor("#6b6b6b")
LINE_COLOR = colors.HexColor("#d0d0d0")


class QuoteLabels(BaseModel):
    date: str
    customer: str
    scope_of_work: str
    position: str
    description: str
    quantity: str
    unit: str
    price: str
    total: str


QUOTE_LABELS: dict[QuoteLanguage, QuoteLabels] = {
    QuoteLanguage.ENGLISH: QuoteLabels(
        date="Date",
        customer="Customer",
        scope_of_work="Scope of work",
        position="Pos.",
        description="Description",
        quantity="Qty",
        unit="Unit",
        price="Price",
        total="Total",
    ),
    QuoteLanguage.FRENCH: QuoteLabels(
        date="Date",
        customer="Client",
        scope_of_work="Prestations",
        position="Pos.",
        description="Description",
        quantity="Qté",
        unit="Unité",
        price="Prix",
        total="Total",
    ),
    QuoteLanguage.GERMAN: QuoteLabels(
        date="Datum",
        customer="Kunde",
        scope_of_work="Leistungsumfang",
        position="Pos.",
        description="Beschreibung",
        quantity="Menge",
        unit="Einheit",
        price="Preis",
        total="Total",
    ),
    QuoteLanguage.ITALIAN: QuoteLabels(
        date="Data",
        customer="Cliente",
        scope_of_work="Prestazioni",
        position="Pos.",
        description="Descrizione",
        quantity="Qtà",
        unit="Unità",
        price="Prezzo",
        total="Totale",
    ),
}


class ReportLabQuoteRenderer(QuoteRenderer):
    # font_files: the brand font's files by weight, only those that exist (licensed fonts may be missing from a checkout).
    def __init__(self, branding: Branding, logo: bytes, font_files: dict[int, Path] | None = None):
        self.branding = branding
        self.logo = logo
        self.ink_color = colors.HexColor(branding.colors.ink)
        self.font, self.bold_font = _register_brand_font(branding=branding, font_files=font_files or {})
        styles = getSampleStyleSheet()
        self.body_style = ParagraphStyle("QuoteBody", parent=styles["BodyText"], fontName=self.font, fontSize=9.5, leading=13)
        self.small_style = ParagraphStyle("QuoteSmall", parent=self.body_style, fontSize=8, leading=10.5, textColor=GREY)
        self.brand_name_style = ParagraphStyle(
            "QuoteBrandName", parent=self.body_style, fontName=self.bold_font, fontSize=13, leading=16, textColor=self.ink_color
        )
        self.title_style = ParagraphStyle(
            "QuoteTitle", parent=self.body_style, fontName=self.bold_font, fontSize=16, leading=20, spaceAfter=4, textColor=self.ink_color
        )
        self.heading_style = ParagraphStyle(
            "QuoteHeading", parent=self.body_style, fontName=self.bold_font, fontSize=11, spaceBefore=8, textColor=self.ink_color
        )

    def render(self, quote: Quote, issue_date: date) -> bytes:
        buffer = BytesIO()
        document = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=PAGE_MARGIN,
            rightMargin=PAGE_MARGIN,
            topMargin=PAGE_MARGIN,
            bottomMargin=PAGE_MARGIN,
            title=quote.title,
        )
        labels = QUOTE_LABELS[quote.language]
        story = [
            *self._build_header(),
            Spacer(1, 10 * mm),
            Paragraph(_to_markup(quote.title), self.title_style),
            Paragraph(f"{labels.date}: {issue_date.isoformat()}<br/>{labels.customer}: {_to_markup(quote.customer)}", self.body_style),
            Paragraph(labels.scope_of_work, self.heading_style),
            Paragraph(_to_markup(quote.scope_of_work), self.body_style),
            Spacer(1, 5 * mm),
            self._build_lines_table(quote=quote, labels=labels),
            Spacer(1, 6 * mm),
            Paragraph(_to_markup(quote.terms), self.body_style),
        ]
        document.build(story)
        return buffer.getvalue()

    def _build_header(self) -> list:
        image_width, image_height = ImageReader(BytesIO(self.logo)).getSize()
        # Square logos are limited by the height, wide wordmarks by the width.
        scale = min(self.branding.logo_height_mm * mm / image_height, LOGO_MAX_WIDTH / image_width)
        header = [
            Image(BytesIO(self.logo), width=image_width * scale, height=image_height * scale, hAlign="LEFT"),
            Spacer(1, 3 * mm),
            Paragraph(_to_markup(self.branding.name), self.brand_name_style),
        ]
        if self.branding.details.strip():
            header.append(Paragraph(_to_markup(self.branding.details), self.small_style))
        return header

    def _build_lines_table(self, quote: Quote, labels: QuoteLabels) -> Table:
        rows = [
            [labels.position, labels.description, labels.quantity, labels.unit, f"{labels.price} {CURRENCY}", f"{labels.total} {CURRENCY}"]
        ]
        rows += [self._build_line_row(position=position, line=line) for position, line in enumerate(quote.lines, start=1)]
        rows.append(["", Paragraph(f"<b>{labels.total}</b>", self.body_style), "", "", "", _format_amount(quote.total)])
        table = Table(rows, colWidths=COLUMN_WIDTHS, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), self.font),
                    ("FONTNAME", (0, 0), (-1, 0), self.bold_font),
                    ("FONTNAME", (-1, -1), (-1, -1), self.bold_font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("ALIGN", (2, 0), (2, -1), "RIGHT"),
                    ("ALIGN", (4, 0), (5, -1), "RIGHT"),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.8, self.ink_color),
                    ("LINEBELOW", (0, 1), (-1, -2), 0.3, LINE_COLOR),
                    ("LINEABOVE", (0, -1), (-1, -1), 0.8, self.ink_color),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return table

    def _build_line_row(self, position: int, line: QuoteLine) -> list:
        reference = f"<br/><font size=7.5 color='#6b6b6b'>{_to_markup(line.product_reference)}</font>" if line.product_reference else ""
        return [
            str(position),
            Paragraph(f"{_to_markup(line.description)}{reference}", self.body_style),
            f"{line.quantity:g}",
            line.unit,
            _format_amount(line.unit_price),
            _format_amount(line.total),
        ]


# Registers the brand font with the PDF library and returns the regular and bold font names, or Helvetica without a regular weight.
def _register_brand_font(branding: Branding, font_files: dict[int, Path]) -> tuple[str, str]:
    if branding.font is None or REGULAR_WEIGHT not in font_files:
        return DEFAULT_FONT, DEFAULT_BOLD_FONT
    font_names = {}
    for weight in (REGULAR_WEIGHT, BOLD_WEIGHT):
        if weight in font_files:
            font_names[weight] = f"{branding.font.family}-{weight}"
            pdfmetrics.registerFont(TTFont(font_names[weight], str(font_files[weight])))
    regular, bold = font_names[REGULAR_WEIGHT], font_names.get(BOLD_WEIGHT, font_names[REGULAR_WEIGHT])
    # Lets <b> in paragraphs switch to the bold file.
    pdfmetrics.registerFontFamily(regular, normal=regular, bold=bold, italic=regular, boldItalic=bold)
    return regular, bold


def _to_markup(text: str) -> str:
    return escape(text).replace("\n", "<br/>")


# Swiss formatting: apostrophe as thousands separator.
def _format_amount(amount: float) -> str:
    return f"{amount:,.2f}".replace(",", "'")
