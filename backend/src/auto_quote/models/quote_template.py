from datetime import date

from pydantic import BaseModel


# A quote template reproduces a company's own quote layout: fixed texts, header and footer images, fonts, lines and positions.
# It lives in data/quote_template/template.json (with its files next to it); without it the default layout is used.
# Positions are in mm from the top left corner of an A4 page; y values are text baselines. The defaults were measured on bb's quote
# as its ERP prints it (F01, 16.11.2026).


class TemplateFonts(BaseModel):
    # TrueType files relative to the template folder: the regular weight and, for emphasised texts, a medium or bold weight.
    regular: str
    medium: str | None = None
    # Advance widths and kerning pairs (scripts/build_font_metrics.py), so text runs as wide as in Word. Without them there is no kerning.
    metrics: str | None = None
    medium_metrics: str | None = None


class TemplateTextSizes(BaseModel):
    # Size the glyphs are drawn at, and the size Word laid them out at (the character positions follow the layout size).
    small: float = 7.56
    small_layout: float = 7.5
    large: float = 9.48
    large_layout: float = 9.5
    # Rounds each character position to this grid (dots per inch); none fitted bb's quote better than exact positions.
    layout_grid_dpi: int | None = None


class TemplateEmphasis(BaseModel):
    # Texts set in the medium weight.
    title: bool = True
    table_header: bool = True
    notice: bool = True
    # Indices of the greeting lines, e.g. [1] for the company name below "Freundliche Grüsse".
    greeting_lines: list[int] = [1]


class TemplateInfoBlock(BaseModel):
    label: str
    lines: list[str]


class TemplateColumns(BaseModel):
    reference: str
    description: str
    quantity: str
    price: str
    total: str


class TemplateTest(BaseModel):
    # Fixed values while comparing the tool's quote with a reference quote; leave empty in normal use.
    issue_date: date | None = None
    number: str | None = None


class TemplateNumbering(BaseModel):
    # The next quote number is kept in this file, relative to the template folder; it starts at start.
    counter_file: str = "quote_numbers.json"
    start: int = 1


class TemplateLayout(BaseModel):
    left: float = 21.04
    right: float = 201.7
    # Last baseline above the footer image; the images themselves span the page width and keep their aspect ratio.
    content_bottom: float = 272.0
    line_height: float = 3.793
    large_line_height: float = 4.798

    # Horizontal lines (thickness in pt, from rule_left to rule_right); a line set to None is not drawn.
    rule_thickness: float = 0.14
    rule_left: float = 21.04
    rule_right: float = 201.65
    # Below the title, measured from the title's baseline (also on following pages).
    title_rule_offset: float | None = 1.65
    # Below the payment / delivery / contact block.
    info_rule_top: float | None = 139.52
    # Above the conditions (MWST, Muster), measured up from their first baseline; this line reaches a little further right.
    conditions_rule_offset: float | None = 5.14
    conditions_rule_right: float = 202.07
    # Grey bar behind the table header, from above to below its baseline; colour as hex, None for no bar.
    table_header_bar_color: str | None = "#c0c0c0"
    table_header_bar_above: float = 4.72
    table_header_bar_below: float = 1.93

    address_top: float = 58.0
    date_top: float = 115.29
    title_top: float = 126.3
    page_label_left: float = 186.64
    page_number_left: float = 193.78
    # The page number sits slightly higher than the larger title on the same line.
    page_number_offset: float = -0.04
    info_top: float = 131.38
    info_line_heights: list[float] = [3.43, 3.51]
    info_value_right: float = 102.14
    info_right_label_left: float = 122.37
    info_right_value_right: float = 201.6
    salutation_top: float = 146.15
    intro_top: float = 153.73
    intro_line_height: float = 3.85
    table_header_top: float = 165.34

    description_left: float = 51.1
    description_width: float = 90.6
    # Right edges of the column headers and of the values below them.
    quantity_header_right: float = 159.26
    price_header_right: float = 179.32
    total_header_right: float = 201.66
    quantity_right: float = 159.4
    price_right: float = 179.41
    total_right: float = 201.42
    description_offset: float = 0.0
    first_row_gap: float = 6.65
    row_gap: float = 6.27
    # Added after a row that has details (the finishing line), as measured on the reference quote.
    details_row_extra_gap: float = 0.88

    notice_gap: float = 10.03
    notice_line_height: float = 3.81
    notice_centre: float = 111.33
    conditions_gap: float = 14.19
    conditions_tab: float = 31.21
    conditions_line_height: float = 3.81
    closing_gap: float = 7.58
    greeting_gap: float = 7.58
    greeting_line_height: float = 3.77
    signature_gap: float = 11.39

    # Following pages: title line with the page number, then the table header and the remaining rows.
    next_page_title_top: float = 50.0
    next_page_table_header_top: float = 59.2


class QuoteTemplate(BaseModel):
    fonts: TemplateFonts
    sizes: TemplateTextSizes = TemplateTextSizes()
    layout: TemplateLayout = TemplateLayout()
    emphasis: TemplateEmphasis = TemplateEmphasis()
    header_image: str | None = None
    footer_image: str | None = None
    place: str
    # Fields: {number}, {title}
    title_format: str = "{title}"
    page_label: str = "Seite"
    # Fields: {page}, {pages}
    page_format: str = "{page} von {pages}"
    info_left: list[TemplateInfoBlock] = []
    info_right: TemplateInfoBlock | None = None
    intro: list[str] = []
    columns: TemplateColumns
    # Centred below the positions; line breaks are kept and long lines wrap.
    notice: str = ""
    # A tab moves the text to layout.conditions_tab.
    conditions: list[str] = []
    closing: str = ""
    greeting: list[str] = []
    signature: str = ""
    # Lines without a price (e.g. "Drucknebenkosten inklusive") show no price and no amount instead of 0.00.
    blank_zero_prices: bool = True
    numbering: TemplateNumbering = TemplateNumbering()
    # CSV (semicolon separated, UTF-8), one row per contact person, relative to the template folder. Columns: firma, strasse,
    # plz_ort, and for the contact anrede, vorname, nachname. The address and, for a known contact, the salutation come from it.
    customers_file: str | None = None
    # Fields: the columns of the customer file. Used when the contact of the request is found in the customer file.
    contact_format: str = "{anrede} {vorname} {nachname}"
    salutation_format: str = "Guten Tag {anrede} {nachname}"
    test: TemplateTest = TemplateTest()
