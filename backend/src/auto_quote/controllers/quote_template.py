import csv
import json
import threading
from pathlib import Path

from loguru import logger

from auto_quote.models.quote import Quote
from auto_quote.models.quote_template import QuoteTemplate


class QuoteTemplateController:
    """Completes a quote with what the template layout needs and the model cannot know: the quote number, the customer's address and,
    for a contact in the customer file, the salutation (Herr/Frau cannot be told from a name)."""

    def __init__(self, template: QuoteTemplate, template_folder: Path):
        self.template = template
        self.template_folder = template_folder
        self._number_lock = threading.Lock()

    # A new quote gets the next number; an adjusted quote keeps the number of the quote it replaces.
    def complete_quote(self, quote: Quote, previous_quote: Quote | None) -> Quote:
        number = previous_quote.number if previous_quote is not None and previous_quote.number else self._next_number()
        rows = self._find_customer_rows(quote.company)
        contact_row = _find_contact_row(rows, quote.contact)
        contact, salutation = quote.contact, quote.salutation
        if contact_row is not None and contact_row.get("anrede", "").strip():
            contact = _format(self.template.contact_format, contact_row)
            salutation = _format(self.template.salutation_format, contact_row)
        address = [rows[0]["firma"] if rows else quote.company, contact]
        if rows:
            address += [rows[0].get("strasse", ""), rows[0].get("plz_ort", "")]
        else:
            logger.warning(f"Customer {quote.company!r} is not in the customer file; the quote address has no street and city")
        return quote.model_copy(
            update={
                "number": number,
                "contact": contact,
                "salutation": salutation,
                "address": [line.strip() for line in address if line and line.strip()],
            }
        )

    def _next_number(self) -> str:
        if self.template.test.number:
            return self.template.test.number
        counter_path = self.template_folder / self.template.numbering.counter_file
        with self._number_lock:
            counter = json.loads(counter_path.read_text(encoding="utf-8")) if counter_path.is_file() else {}
            number = int(counter.get("next", self.template.numbering.start))
            counter_path.write_text(json.dumps({"next": number + 1}), encoding="utf-8")
        return str(number)

    def _find_customer_rows(self, company: str) -> list[dict[str, str]]:
        if not self.template.customers_file or not company.strip():
            return []
        customers_path = self.template_folder / self.template.customers_file
        if not customers_path.is_file():
            return []
        with customers_path.open(encoding="utf-8-sig", newline="") as customers_file:
            return [row for row in csv.DictReader(customers_file, delimiter=";") if _normalize(row.get("firma", "")) == _normalize(company)]


# The contact matches when its first and last name both appear in the contact the model read from the request.
def _find_contact_row(rows: list[dict[str, str]], contact: str) -> dict[str, str] | None:
    words = set(_normalize(contact).split())
    return next(
        (
            row
            for row in rows
            if row.get("nachname", "").strip()
            and _normalize(row["nachname"]) in words
            and (not row.get("vorname", "").strip() or _normalize(row["vorname"]) in words)
        ),
        None,
    )


def _format(text_format: str, row: dict[str, str]) -> str:
    return " ".join(text_format.format(**{key: (value or "").strip() for key, value in row.items() if key}).split())


def _normalize(name: str) -> str:
    return " ".join(name.casefold().split())
