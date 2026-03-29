#!/usr/bin/env python3
"""Einfaches Rechnungs-Tool für 3D-Druck-Aufträge.

Funktionen:
- Liest Rechnungsdaten aus einer JSON-Datei
- Validiert Pflichtangaben nach deutschem UStG (vereinfachte, praxisnahe Prüfung)
- Erzeugt eine menschenlesbare HTML-Rechnung
- Erzeugt optional eine E-Rechnung im UBL-2.1-XML-Format (EN16931-nahe Struktur)

Hinweis: Für produktive Nutzung sollte die E-Rechnung gegen offizielle Schematron/XSD-Regeln
(z. B. XRechnung) validiert werden.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

TWOPLACES = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


@dataclass
class Party:
    name: str
    street: str
    zip_code: str
    city: str
    country: str
    email: str | None = None
    vat_id: str | None = None
    tax_number: str | None = None


@dataclass
class InvoiceLine:
    description: str
    quantity: Decimal
    unit: str
    unit_price_net: Decimal
    vat_rate: Decimal

    @property
    def line_net(self) -> Decimal:
        return money(self.quantity * self.unit_price_net)

    @property
    def line_vat(self) -> Decimal:
        return money(self.line_net * self.vat_rate / Decimal("100"))

    @property
    def line_gross(self) -> Decimal:
        return money(self.line_net + self.line_vat)


@dataclass
class Invoice:
    invoice_number: str
    issue_date: dt.date
    service_date: dt.date
    seller: Party
    buyer: Party
    lines: list[InvoiceLine]
    currency: str = "EUR"
    payment_terms: str = "Zahlbar innerhalb von 14 Tagen ohne Abzug."
    payment_iban: str | None = None
    payment_bic: str | None = None
    note: str | None = None
    is_kleinunternehmer: bool = False

    @property
    def total_net(self) -> Decimal:
        return money(sum((line.line_net for line in self.lines), Decimal("0.00")))

    @property
    def total_vat(self) -> Decimal:
        if self.is_kleinunternehmer:
            return Decimal("0.00")
        return money(sum((line.line_vat for line in self.lines), Decimal("0.00")))

    @property
    def total_gross(self) -> Decimal:
        return money(self.total_net + self.total_vat)


class ValidationError(Exception):
    pass


def parse_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as exc:  # noqa: BLE001
        raise ValidationError(f"Ungültiger Dezimalwert für {field_name}: {value}") from exc


def parse_date(value: str, field_name: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError(
            f"Ungültiges Datum für {field_name}: {value}. Erwartet wird YYYY-MM-DD."
        ) from exc


def load_invoice(path: Path) -> Invoice:
    data = json.loads(path.read_text(encoding="utf-8"))

    def read_party(raw: dict[str, Any], role: str) -> Party:
        required = ["name", "street", "zip_code", "city", "country"]
        for key in required:
            if not raw.get(key):
                raise ValidationError(f"{role}.{key} fehlt.")
        return Party(
            name=raw["name"],
            street=raw["street"],
            zip_code=raw["zip_code"],
            city=raw["city"],
            country=raw["country"],
            email=raw.get("email"),
            vat_id=raw.get("vat_id"),
            tax_number=raw.get("tax_number"),
        )

    lines: list[InvoiceLine] = []
    for idx, raw_line in enumerate(data.get("lines", []), start=1):
        lines.append(
            InvoiceLine(
                description=raw_line.get("description", ""),
                quantity=parse_decimal(raw_line.get("quantity", 0), f"lines[{idx}].quantity"),
                unit=raw_line.get("unit", "Stk"),
                unit_price_net=parse_decimal(
                    raw_line.get("unit_price_net", 0), f"lines[{idx}].unit_price_net"
                ),
                vat_rate=parse_decimal(raw_line.get("vat_rate", 0), f"lines[{idx}].vat_rate"),
            )
        )

    return Invoice(
        invoice_number=data.get("invoice_number", ""),
        issue_date=parse_date(data.get("issue_date", ""), "issue_date"),
        service_date=parse_date(data.get("service_date", ""), "service_date"),
        seller=read_party(data.get("seller", {}), "seller"),
        buyer=read_party(data.get("buyer", {}), "buyer"),
        lines=lines,
        currency=data.get("currency", "EUR"),
        payment_terms=data.get("payment_terms", "Zahlbar innerhalb von 14 Tagen ohne Abzug."),
        payment_iban=data.get("payment_iban"),
        payment_bic=data.get("payment_bic"),
        note=data.get("note"),
        is_kleinunternehmer=bool(data.get("is_kleinunternehmer", False)),
    )


def validate_invoice(invoice: Invoice) -> None:
    # Pflichtangaben nach deutschem Recht (vereinfachte technische Prüfung)
    if not invoice.invoice_number.strip():
        raise ValidationError("Fortlaufende Rechnungsnummer fehlt.")

    if not invoice.lines:
        raise ValidationError("Mindestens eine Rechnungsposition ist erforderlich.")

    if invoice.issue_date < dt.date(2000, 1, 1):
        raise ValidationError("Rechnungsdatum scheint unplausibel.")

    if invoice.service_date > invoice.issue_date + dt.timedelta(days=365):
        raise ValidationError("Leistungsdatum liegt unplausibel weit in der Zukunft.")

    if not invoice.seller.vat_id and not invoice.seller.tax_number:
        raise ValidationError(
            "Beim Verkäufer muss mindestens USt-IdNr. oder Steuernummer angegeben sein."
        )

    for idx, line in enumerate(invoice.lines, start=1):
        if not line.description.strip():
            raise ValidationError(f"Beschreibung in Position {idx} fehlt.")
        if line.quantity <= 0:
            raise ValidationError(f"Menge in Position {idx} muss > 0 sein.")
        if line.unit_price_net < 0:
            raise ValidationError(f"Einzelpreis in Position {idx} darf nicht negativ sein.")
        if not invoice.is_kleinunternehmer and line.vat_rate < 0:
            raise ValidationError(f"MwSt-Satz in Position {idx} darf nicht negativ sein.")


def render_html(invoice: Invoice) -> str:
    rows = []
    for line in invoice.lines:
        rows.append(
            "<tr>"
            f"<td>{line.description}</td>"
            f"<td>{line.quantity}</td>"
            f"<td>{line.unit}</td>"
            f"<td>{line.unit_price_net:.2f} {invoice.currency}</td>"
            f"<td>{line.vat_rate:.2f}%</td>"
            f"<td>{line.line_net:.2f} {invoice.currency}</td>"
            "</tr>"
        )

    vat_text = (
        "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet."
        if invoice.is_kleinunternehmer
        else f"{invoice.total_vat:.2f} {invoice.currency}"
    )

    return f"""<!DOCTYPE html>
<html lang=\"de\">
<head>
  <meta charset=\"utf-8\" />
  <title>Rechnung {invoice.invoice_number}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; }}
    .meta, .parties {{ display: flex; gap: 3rem; margin-bottom: 1rem; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
    th, td {{ border: 1px solid #ccc; padding: 0.4rem; text-align: left; }}
    th {{ background: #f4f4f4; }}
    .totals {{ margin-top: 1rem; text-align: right; }}
  </style>
</head>
<body>
  <h1>Rechnung {invoice.invoice_number}</h1>

  <div class=\"meta\">
    <div><strong>Rechnungsdatum:</strong> {invoice.issue_date.isoformat()}</div>
    <div><strong>Leistungsdatum:</strong> {invoice.service_date.isoformat()}</div>
  </div>

  <div class=\"parties\">
    <div>
      <h3>Verkäufer</h3>
      <div>{invoice.seller.name}</div>
      <div>{invoice.seller.street}</div>
      <div>{invoice.seller.zip_code} {invoice.seller.city}</div>
      <div>{invoice.seller.country}</div>
      <div>USt-IdNr.: {invoice.seller.vat_id or '-'}</div>
      <div>Steuernummer: {invoice.seller.tax_number or '-'}</div>
    </div>

    <div>
      <h3>Kunde</h3>
      <div>{invoice.buyer.name}</div>
      <div>{invoice.buyer.street}</div>
      <div>{invoice.buyer.zip_code} {invoice.buyer.city}</div>
      <div>{invoice.buyer.country}</div>
    </div>
  </div>

  <table>
    <thead>
      <tr>
        <th>Beschreibung</th>
        <th>Menge</th>
        <th>Einheit</th>
        <th>Einzelpreis (netto)</th>
        <th>MwSt.</th>
        <th>Gesamt (netto)</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <div class=\"totals\">
    <div>Nettobetrag: {invoice.total_net:.2f} {invoice.currency}</div>
    <div>Umsatzsteuer: {vat_text}</div>
    <div><strong>Gesamtbetrag: {invoice.total_gross:.2f} {invoice.currency}</strong></div>
  </div>

  <p><strong>Zahlungsbedingungen:</strong> {invoice.payment_terms}</p>
  <p><strong>IBAN:</strong> {invoice.payment_iban or '-'} | <strong>BIC:</strong> {invoice.payment_bic or '-'}</p>
  <p>{invoice.note or ''}</p>
</body>
</html>
"""


def render_ubl_xml(invoice: Invoice) -> str:
    # Vereinfachte UBL-Invoice-Struktur. Für produktive E-Rechnungs-Prozesse
    # sollte zusätzlich XRechnung-Validierung erfolgen.
    nsmap = {
        "": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    }

    for prefix, uri in nsmap.items():
        ET.register_namespace(prefix, uri)

    def n(tag: str, prefix: str = "") -> str:
        uri = nsmap[prefix]
        return f"{{{uri}}}{tag}"

    root = ET.Element(n("Invoice"))
    ET.SubElement(root, n("CustomizationID", "cbc")).text = (
        "urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0"
    )
    ET.SubElement(root, n("ProfileID", "cbc")).text = "urn:fdc:peppol.eu:2017:poacc:billing:01:1.0"
    ET.SubElement(root, n("ID", "cbc")).text = invoice.invoice_number
    ET.SubElement(root, n("IssueDate", "cbc")).text = invoice.issue_date.isoformat()
    ET.SubElement(root, n("DueDate", "cbc")).text = (
        invoice.issue_date + dt.timedelta(days=14)
    ).isoformat()
    ET.SubElement(root, n("InvoiceTypeCode", "cbc")).text = "380"
    ET.SubElement(root, n("DocumentCurrencyCode", "cbc")).text = invoice.currency
    if invoice.note:
        ET.SubElement(root, n("Note", "cbc")).text = invoice.note

    supplier_party = ET.SubElement(root, n("AccountingSupplierParty", "cac"))
    supplier = ET.SubElement(supplier_party, n("Party", "cac"))
    ET.SubElement(ET.SubElement(supplier, n("PartyName", "cac")), n("Name", "cbc")).text = invoice.seller.name
    supplier_address = ET.SubElement(supplier, n("PostalAddress", "cac"))
    ET.SubElement(supplier_address, n("StreetName", "cbc")).text = invoice.seller.street
    ET.SubElement(supplier_address, n("CityName", "cbc")).text = invoice.seller.city
    ET.SubElement(supplier_address, n("PostalZone", "cbc")).text = invoice.seller.zip_code
    ET.SubElement(supplier_address, n("CountrySubentity", "cbc")).text = invoice.seller.country
    ET.SubElement(ET.SubElement(supplier_address, n("Country", "cac")), n("IdentificationCode", "cbc")).text = "DE"

    supplier_tax = ET.SubElement(supplier, n("PartyTaxScheme", "cac"))
    ET.SubElement(supplier_tax, n("CompanyID", "cbc")).text = invoice.seller.vat_id or invoice.seller.tax_number
    ET.SubElement(ET.SubElement(supplier_tax, n("TaxScheme", "cac")), n("ID", "cbc")).text = "VAT"

    customer_party = ET.SubElement(root, n("AccountingCustomerParty", "cac"))
    customer = ET.SubElement(customer_party, n("Party", "cac"))
    ET.SubElement(ET.SubElement(customer, n("PartyName", "cac")), n("Name", "cbc")).text = invoice.buyer.name
    customer_address = ET.SubElement(customer, n("PostalAddress", "cac"))
    ET.SubElement(customer_address, n("StreetName", "cbc")).text = invoice.buyer.street
    ET.SubElement(customer_address, n("CityName", "cbc")).text = invoice.buyer.city
    ET.SubElement(customer_address, n("PostalZone", "cbc")).text = invoice.buyer.zip_code
    ET.SubElement(customer_address, n("CountrySubentity", "cbc")).text = invoice.buyer.country
    ET.SubElement(ET.SubElement(customer_address, n("Country", "cac")), n("IdentificationCode", "cbc")).text = "DE"

    payment_means = ET.SubElement(root, n("PaymentMeans", "cac"))
    ET.SubElement(payment_means, n("PaymentMeansCode", "cbc")).text = "58"
    account = ET.SubElement(payment_means, n("PayeeFinancialAccount", "cac"))
    if invoice.payment_iban:
        ET.SubElement(account, n("ID", "cbc")).text = invoice.payment_iban
    if invoice.payment_bic:
        inst = ET.SubElement(account, n("FinancialInstitutionBranch", "cac"))
        ET.SubElement(inst, n("ID", "cbc")).text = invoice.payment_bic

    tax_total = ET.SubElement(root, n("TaxTotal", "cac"))
    ET.SubElement(tax_total, n("TaxAmount", "cbc"), attrib={"currencyID": invoice.currency}).text = f"{invoice.total_vat:.2f}"

    tax_subtotal = ET.SubElement(tax_total, n("TaxSubtotal", "cac"))
    ET.SubElement(tax_subtotal, n("TaxableAmount", "cbc"), attrib={"currencyID": invoice.currency}).text = f"{invoice.total_net:.2f}"
    ET.SubElement(tax_subtotal, n("TaxAmount", "cbc"), attrib={"currencyID": invoice.currency}).text = f"{invoice.total_vat:.2f}"

    category = ET.SubElement(tax_subtotal, n("TaxCategory", "cac"))
    ET.SubElement(category, n("ID", "cbc")).text = "E" if invoice.is_kleinunternehmer else "S"
    ET.SubElement(category, n("Percent", "cbc")).text = "0.00" if invoice.is_kleinunternehmer else "19.00"
    ET.SubElement(ET.SubElement(category, n("TaxScheme", "cac")), n("ID", "cbc")).text = "VAT"

    legal_total = ET.SubElement(root, n("LegalMonetaryTotal", "cac"))
    ET.SubElement(legal_total, n("LineExtensionAmount", "cbc"), attrib={"currencyID": invoice.currency}).text = f"{invoice.total_net:.2f}"
    ET.SubElement(legal_total, n("TaxExclusiveAmount", "cbc"), attrib={"currencyID": invoice.currency}).text = f"{invoice.total_net:.2f}"
    ET.SubElement(legal_total, n("TaxInclusiveAmount", "cbc"), attrib={"currencyID": invoice.currency}).text = f"{invoice.total_gross:.2f}"
    ET.SubElement(legal_total, n("PayableAmount", "cbc"), attrib={"currencyID": invoice.currency}).text = f"{invoice.total_gross:.2f}"

    for idx, line in enumerate(invoice.lines, start=1):
        invoice_line = ET.SubElement(root, n("InvoiceLine", "cac"))
        ET.SubElement(invoice_line, n("ID", "cbc")).text = str(idx)
        ET.SubElement(invoice_line, n("InvoicedQuantity", "cbc"), attrib={"unitCode": line.unit}).text = str(line.quantity)
        ET.SubElement(invoice_line, n("LineExtensionAmount", "cbc"), attrib={"currencyID": invoice.currency}).text = f"{line.line_net:.2f}"

        item = ET.SubElement(invoice_line, n("Item", "cac"))
        ET.SubElement(item, n("Name", "cbc")).text = line.description
        tax_cat = ET.SubElement(item, n("ClassifiedTaxCategory", "cac"))
        ET.SubElement(tax_cat, n("ID", "cbc")).text = "E" if invoice.is_kleinunternehmer else "S"
        ET.SubElement(tax_cat, n("Percent", "cbc")).text = f"{0 if invoice.is_kleinunternehmer else line.vat_rate:.2f}"
        ET.SubElement(ET.SubElement(tax_cat, n("TaxScheme", "cac")), n("ID", "cbc")).text = "VAT"

        price = ET.SubElement(invoice_line, n("Price", "cac"))
        ET.SubElement(price, n("PriceAmount", "cbc"), attrib={"currencyID": invoice.currency}).text = f"{line.unit_price_net:.2f}"

    return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")


def write_output(invoice: Invoice, out_dir: Path, create_einvoice: bool) -> tuple[Path, Path | None]:
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / f"invoice_{invoice.invoice_number}.html"
    html_path.write_text(render_html(invoice), encoding="utf-8")

    xml_path = None
    if create_einvoice:
        xml_path = out_dir / f"invoice_{invoice.invoice_number}.xml"
        xml_path.write_text(render_ubl_xml(invoice), encoding="utf-8")

    return html_path, xml_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Rechnungen für 3D-Druck-Kunden erstellen")
    parser.add_argument("--input", required=True, type=Path, help="Pfad zur JSON-Eingabedatei")
    parser.add_argument("--out", type=Path, default=Path("./output"), help="Ausgabeordner")
    parser.add_argument(
        "--e-invoice",
        action="store_true",
        help="Zusätzlich XML-E-Rechnung (UBL/XRechnung-nahe Struktur) erzeugen",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        invoice = load_invoice(args.input)
        validate_invoice(invoice)
        html_path, xml_path = write_output(invoice, args.out, create_einvoice=args.e_invoice)
    except ValidationError as exc:
        print(f"Fehler: {exc}")
        return 1

    print(f"HTML-Rechnung erstellt: {html_path}")
    if xml_path:
        print(f"E-Rechnung XML erstellt: {xml_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
