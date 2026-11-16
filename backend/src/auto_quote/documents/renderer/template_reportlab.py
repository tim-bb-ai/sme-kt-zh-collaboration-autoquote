import json
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from auto_quote.documents.renderer.quote_renderer import QuoteRenderer
from auto_quote.models.quote import Quote, QuoteLine
from auto_quote.models.quote_template import QuoteTemplate, TemplateTextSizes


REGULAR_FONT = "QuoteTemplateRegular"
MEDIUM_FONT = "QuoteTemplateMedium"
PAGE_WIDTH, PAGE_HEIGHT = A4
POINTS_PER_INCH = 72
GERMAN_MONTHS = [
    "Januar",
    "Februar",
    "März",
    "April",
    "Mai",
    "Juni",
    "Juli",
    "August",
    "September",
    "Oktober",
    "November",
    "Dezember",
]


class _TextSetter:
    """Places the characters of one font the way Word does: advance widths plus kerning at the layout size."""

    def __init__(self, font_name: str, sizes: TemplateTextSizes, metrics: dict | None):
        self.font_name = font_name
        self.sizes = sizes
        self.metrics = metrics

    def offsets(self, text: str, large: bool) -> tuple[list[float], float]:
        layout_size = self.sizes.large_layout if large else self.sizes.small_layout
        grid = self.sizes.layout_grid_dpi
        offsets, x = [], 0.0
        for index, character in enumerate(text):
            offsets.append(x)
            next_character = text[index + 1] if index + 1 < len(text) else ""
            advance = self._advance(character, next_character, layout_size)
            x += round(advance * grid / POINTS_PER_INCH) / grid * POINTS_PER_INCH if grid else advance
        return offsets, x

    def width(self, text: str, large: bool = False) -> float:
        return self.offsets(text, large)[1]

    def wrap(self, text: str, width: float, large: bool = False) -> list[str]:
        lines = []
        for paragraph in text.split("\n"):
            line = ""
            for word in paragraph.split(" "):
                candidate = f"{line} {word}" if line else word
                if line and self.width(candidate, large) > width:
                    lines.append(line)
                    line = word
                else:
                    line = candidate
            lines.append(line)
        return lines

    def draw(self, canvas: Canvas, text: str, x: float, y: float, large: bool) -> None:
        offsets, _ = self.offsets(text, large)
        text_object = canvas.beginText()
        text_object.setFont(self.font_name, self.sizes.large if large else self.sizes.small)
        for character, offset in zip(text, offsets, strict=True):
            text_object.setTextOrigin(x + offset, y)
            text_object.textOut(character)
        canvas.drawText(text_object)

    # In points at the layout size.
    def _advance(self, character: str, next_character: str, layout_size: float) -> float:
        if self.metrics is None or character not in self.metrics["advances"]:
            return pdfmetrics.stringWidth(character, self.font_name, layout_size)
        units = self.metrics["advances"][character] + self.metrics["kerning"].get(character + next_character, 0)
        return units * layout_size / self.metrics["units_per_em"]


@dataclass
class _Text:
    text: str
    x: float
    y: float
    large: bool = False
    align: str = "left"
    medium: bool = False


@dataclass
class _Rule:
    y: float
    left: float
    right: float


@dataclass
class _Bar:
    top: float
    bottom: float


@dataclass
class _Page:
    texts: list[_Text] = field(default_factory=list)
    rules: list[_Rule] = field(default_factory=list)
    bars: list[_Bar] = field(default_factory=list)
    # Where the page number goes, filled in once the number of pages is known.
    page_number_y: float | None = None


class TemplateQuoteRenderer(QuoteRenderer):
    """Renders a quote in a company's own layout, as described by a QuoteTemplate. Rows that do not fit continue on further pages."""

    def __init__(self, template: QuoteTemplate, template_folder: Path):
        self.template = template
        self.layout = template.layout
        self.emphasis = template.emphasis
        fonts = template.fonts
        pdfmetrics.registerFont(TTFont(REGULAR_FONT, template_folder / fonts.regular))
        self.regular = _TextSetter(REGULAR_FONT, template.sizes, _read_metrics(template_folder, fonts.metrics))
        if fonts.medium:
            pdfmetrics.registerFont(TTFont(MEDIUM_FONT, template_folder / fonts.medium))
            self.medium = _TextSetter(MEDIUM_FONT, template.sizes, _read_metrics(template_folder, fonts.medium_metrics))
        else:
            self.medium = self.regular
        self.header_image = ImageReader(template_folder / template.header_image) if template.header_image else None
        self.footer_image = ImageReader(template_folder / template.footer_image) if template.footer_image else None

    def render(self, quote: Quote, issue_date: date) -> bytes:
        pages = self._lay_out(quote=quote, issue_date=self.template.test.issue_date or issue_date)
        buffer = BytesIO()
        canvas = Canvas(buffer, pagesize=A4)
        canvas.setTitle(self._title(quote))
        for page_number, page in enumerate(pages, start=1):
            self._draw_images(canvas)
            self._draw_shapes(canvas, page)
            texts = list(page.texts)
            if page.page_number_y is not None:
                page_text = self.template.page_format.format(page=page_number, pages=len(pages))
                page_number_y = page.page_number_y + self.layout.page_number_offset
                texts += [
                    _Text(self.template.page_label, self.layout.page_label_left, page_number_y),
                    _Text(page_text, self.layout.page_number_left, page_number_y),
                ]
            for text in texts:
                self._draw_text(canvas, text)
            canvas.showPage()
        canvas.save()
        return buffer.getvalue()

    def _lay_out(self, quote: Quote, issue_date: date) -> list[_Page]:
        layout = self.layout
        page = _Page()
        pages = [page]

        address = quote.address or [line for line in (quote.company or quote.customer, quote.contact) if line]
        for index, line in enumerate(address):
            page.texts.append(_Text(line, layout.left, layout.address_top + index * layout.large_line_height, large=True))
        date_text = f"{self.template.place}, {issue_date.day}. {GERMAN_MONTHS[issue_date.month - 1]} {issue_date.year}"
        page.texts.append(_Text(date_text, layout.left, layout.date_top))
        self._add_title(page, quote, layout.title_top)
        page.texts += self._info_block()
        if layout.info_rule_top is not None:
            page.rules.append(_Rule(layout.info_rule_top, layout.rule_left, layout.rule_right))
        if quote.salutation:
            page.texts.append(_Text(quote.salutation, layout.left, layout.salutation_top))
        for index, line in enumerate(self.template.intro):
            page.texts.append(_Text(line, layout.left, layout.intro_top + index * layout.intro_line_height))
        self._add_table_header(page, layout.table_header_top)

        y = layout.table_header_top + layout.first_row_gap
        last_y = layout.table_header_top
        for quote_line in quote.lines:
            row = self._row(quote_line)
            row_height = max(text.y for text in row)
            if y + row_height > layout.content_bottom:
                page = self._next_page(quote, with_table_header=True)
                pages.append(page)
                y = layout.next_page_table_header_top + layout.first_row_gap
            for text in row:
                page.texts.append(_Text(text.text, text.x, y + text.y, align=text.align))
            last_y = y + row_height
            y = last_y + layout.row_gap + (layout.details_row_extra_gap if quote_line.details else 0)

        for block, gap, is_tail in ((self._notice(), layout.notice_gap, False), (self._tail(), layout.conditions_gap, True)):
            if not block:
                continue
            block_height = max(text.y for text in block)
            rule_space = layout.conditions_rule_offset if is_tail and layout.conditions_rule_offset is not None else 0
            top = last_y + gap
            if top + block_height > layout.content_bottom:
                page = self._next_page(quote, with_table_header=False)
                pages.append(page)
                top = layout.next_page_table_header_top + rule_space
            if is_tail and layout.conditions_rule_offset is not None:
                page.rules.append(_Rule(top - layout.conditions_rule_offset, layout.rule_left, layout.conditions_rule_right))
            page.texts += [_Text(text.text, text.x, top + text.y, align=text.align, medium=text.medium) for text in block]
            last_y = top + block_height
        return pages

    def _title(self, quote: Quote) -> str:
        return self.template.title_format.format(number=quote.number, title=quote.title)

    def _add_title(self, page: _Page, quote: Quote, y: float) -> None:
        page.texts.append(_Text(self._title(quote), self.layout.left, y, large=True, medium=self.emphasis.title))
        page.page_number_y = y
        if self.layout.title_rule_offset is not None:
            page.rules.append(_Rule(y + self.layout.title_rule_offset, self.layout.rule_left, self.layout.rule_right))

    def _next_page(self, quote: Quote, with_table_header: bool) -> _Page:
        page = _Page()
        self._add_title(page, quote, self.layout.next_page_title_top)
        if with_table_header:
            self._add_table_header(page, self.layout.next_page_table_header_top)
        return page

    # Left: label at the margin and its lines right-aligned; right: label, and its lines right-aligned at the page margin.
    def _info_block(self) -> list[_Text]:
        layout = self.layout
        line_count = max(
            sum(len(block.lines) for block in self.template.info_left),
            len(self.template.info_right.lines) if self.template.info_right else 0,
        )
        heights = layout.info_line_heights or [layout.line_height]
        line_ys = [layout.info_top]
        for index in range(1, line_count):
            line_ys.append(line_ys[-1] + heights[min(index - 1, len(heights) - 1)])

        texts = []
        line_index = 0
        for block in self.template.info_left:
            texts.append(_Text(block.label, layout.left, line_ys[line_index]))
            for line in block.lines:
                texts.append(_Text(line, layout.info_value_right, line_ys[line_index], align="right"))
                line_index += 1
        if self.template.info_right:
            texts.append(_Text(self.template.info_right.label, layout.info_right_label_left, line_ys[0]))
            for index, line in enumerate(self.template.info_right.lines):
                texts.append(_Text(line, layout.info_right_value_right, line_ys[index], align="right"))
        return texts

    def _add_table_header(self, page: _Page, y: float) -> None:
        layout, columns, medium = self.layout, self.template.columns, self.emphasis.table_header
        if layout.table_header_bar_color is not None:
            page.bars.append(_Bar(y - layout.table_header_bar_above, y + layout.table_header_bar_below))
        page.texts += [
            _Text(columns.reference, layout.left, y, medium=medium),
            _Text(columns.description, layout.description_left, y, medium=medium),
            _Text(columns.quantity, layout.quantity_header_right, y, align="right", medium=medium),
            _Text(columns.price, layout.price_header_right, y, align="right", medium=medium),
            _Text(columns.total, layout.total_header_right, y, align="right", medium=medium),
        ]

    # Texts of one row; y is relative to the row's first baseline.
    def _row(self, quote_line: QuoteLine) -> list[_Text]:
        layout = self.layout
        width = layout.description_width * mm
        description_lines = self.regular.wrap(quote_line.description, width)
        if quote_line.details:
            description_lines += self.regular.wrap(quote_line.details, width)
        texts = [
            _Text(line, layout.description_left, layout.description_offset + index * layout.line_height)
            for index, line in enumerate(description_lines)
        ]
        texts.append(_Text(quote_line.product_reference or "", layout.left, 0))
        texts.append(_Text(_format_quantity(quote_line.quantity), layout.quantity_right, 0, align="right"))
        if not (self.template.blank_zero_prices and quote_line.unit_price == 0 and quote_line.total == 0):
            texts.append(_Text(_format_amount(quote_line.unit_price), layout.price_right, 0, align="right"))
            texts.append(_Text(_format_amount(quote_line.total), layout.total_right, 0, align="right"))
        return texts

    def _notice(self) -> list[_Text]:
        if not self.template.notice:
            return []
        layout, medium = self.layout, self.emphasis.notice
        setter = self.medium if medium else self.regular
        lines = setter.wrap(self.template.notice, (layout.right - layout.left) * mm)
        return [
            _Text(line, layout.notice_centre, index * layout.notice_line_height, align="centre", medium=medium)
            for index, line in enumerate(lines)
        ]

    # Conditions, closing sentence, greeting and signature stay together on one page.
    def _tail(self) -> list[_Text]:
        layout = self.layout
        texts: list[_Text] = []
        y = 0.0
        for index, condition in enumerate(self.template.conditions):
            if index:
                y += layout.conditions_line_height
            label, _, text = condition.partition("\t")
            if text:
                texts.append(_Text(label, layout.left, y))
                texts.append(_Text(text, layout.conditions_tab, y))
            else:
                texts.append(_Text(condition, layout.left, y))
        if self.template.closing:
            y = y + layout.closing_gap if texts else y
            texts.append(_Text(self.template.closing, layout.left, y))
        for index, line in enumerate(self.template.greeting):
            y += layout.greeting_gap if index == 0 and texts else (layout.greeting_line_height if index else 0)
            texts.append(_Text(line, layout.left, y, medium=index in self.emphasis.greeting_lines))
        if self.template.signature:
            y = y + layout.signature_gap if texts else y
            texts.append(_Text(self.template.signature, layout.left, y))
        return texts

    def _draw_images(self, canvas: Canvas) -> None:
        if self.header_image is not None:
            width, height = self.header_image.getSize()
            image_height = PAGE_WIDTH * height / width
            canvas.drawImage(self.header_image, 0, PAGE_HEIGHT - image_height, width=PAGE_WIDTH, height=image_height, mask="auto")
        if self.footer_image is not None:
            width, height = self.footer_image.getSize()
            canvas.drawImage(self.footer_image, 0, 0, width=PAGE_WIDTH, height=PAGE_WIDTH * height / width, mask="auto")

    def _draw_shapes(self, canvas: Canvas, page: _Page) -> None:
        layout = self.layout
        if page.bars and layout.table_header_bar_color is not None:
            canvas.setFillColor(colors.HexColor(layout.table_header_bar_color))
            for bar in page.bars:
                height = (bar.bottom - bar.top) * mm
                canvas.rect(layout.left * mm, PAGE_HEIGHT - bar.bottom * mm, (layout.right - layout.left) * mm, height, stroke=0, fill=1)
        canvas.setFillColor(colors.black)
        canvas.setStrokeColor(colors.black)
        canvas.setLineWidth(layout.rule_thickness)
        for rule in page.rules:
            canvas.line(rule.left * mm, PAGE_HEIGHT - rule.y * mm, rule.right * mm, PAGE_HEIGHT - rule.y * mm)

    def _draw_text(self, canvas: Canvas, text: _Text) -> None:
        setter = self.medium if text.medium else self.regular
        x = text.x * mm
        if text.align != "left":
            width = setter.width(text.text, text.large)
            x -= width if text.align == "right" else width / 2
        setter.draw(canvas, text.text, x, PAGE_HEIGHT - text.y * mm, text.large)


def _read_metrics(template_folder: Path, metrics_file: str | None) -> dict | None:
    return json.loads((template_folder / metrics_file).read_text(encoding="utf-8")) if metrics_file else None


def _format_quantity(quantity: float) -> str:
    return str(int(quantity)) if quantity == int(quantity) else f"{quantity:g}"


# Swiss format: 2'390.00
def _format_amount(amount: float) -> str:
    return f"{amount:,.2f}".replace(",", "'")
