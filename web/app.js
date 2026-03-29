const form = document.getElementById('invoice-form');
const preview = document.getElementById('preview-container');
const lineItemsContainer = document.getElementById('line-items');
const lineTemplate = document.getElementById('line-template');

function euro(value) {
  return Number(value || 0).toFixed(2);
}

function createLine(initial = {}) {
  const node = lineTemplate.content.firstElementChild.cloneNode(true);
  node.querySelectorAll('input[data-key]').forEach((input) => {
    const key = input.dataset.key;
    if (initial[key] !== undefined) {
      input.value = initial[key];
    }
    input.addEventListener('input', render);
  });

  node.querySelector('.remove-line').addEventListener('click', () => {
    node.remove();
    render();
  });

  lineItemsContainer.appendChild(node);
}

function getLines() {
  return [...lineItemsContainer.querySelectorAll('.line-item')].map((item) => {
    const data = {};
    item.querySelectorAll('input[data-key]').forEach((input) => {
      data[input.dataset.key] = input.value;
    });
    return {
      description: data.description || '',
      quantity: Number(data.quantity || 0),
      unit: data.unit || 'C62',
      unit_price_net: Number(data.unit_price_net || 0),
      vat_rate: Number(data.vat_rate || 0)
    };
  });
}

function getInvoice() {
  const fd = new FormData(form);
  return {
    invoice_number: fd.get('invoice_number'),
    issue_date: fd.get('issue_date'),
    service_date: fd.get('service_date'),
    currency: fd.get('currency') || 'EUR',
    is_kleinunternehmer: fd.get('is_kleinunternehmer') === 'on',
    seller: {
      name: fd.get('seller_name'),
      street: fd.get('seller_street'),
      zip_code: fd.get('seller_zip'),
      city: fd.get('seller_city'),
      country: fd.get('seller_country'),
      vat_id: fd.get('seller_vat_id') || null,
      tax_number: fd.get('seller_tax_number') || null
    },
    buyer: {
      name: fd.get('buyer_name'),
      street: fd.get('buyer_street'),
      zip_code: fd.get('buyer_zip'),
      city: fd.get('buyer_city'),
      country: fd.get('buyer_country')
    },
    lines: getLines(),
    payment_terms: fd.get('payment_terms'),
    payment_iban: fd.get('payment_iban'),
    payment_bic: fd.get('payment_bic'),
    note: fd.get('note')
  };
}

function computeTotals(invoice) {
  const lines = invoice.lines.map((line) => {
    const line_net = Number((line.quantity * line.unit_price_net).toFixed(2));
    const line_vat = invoice.is_kleinunternehmer
      ? 0
      : Number((line_net * (line.vat_rate / 100)).toFixed(2));
    return { ...line, line_net, line_vat, line_gross: Number((line_net + line_vat).toFixed(2)) };
  });
  const total_net = Number(lines.reduce((acc, line) => acc + line.line_net, 0).toFixed(2));
  const total_vat = Number(lines.reduce((acc, line) => acc + line.line_vat, 0).toFixed(2));
  const total_gross = Number((total_net + total_vat).toFixed(2));
  return { lines, total_net, total_vat, total_gross };
}

function renderPreviewHTML(invoice, totals) {
  const rows = totals.lines.map((line) => `
    <tr>
      <td>${line.description}</td>
      <td>${line.quantity}</td>
      <td>${line.unit}</td>
      <td>${euro(line.unit_price_net)} ${invoice.currency}</td>
      <td>${euro(line.vat_rate)}%</td>
      <td>${euro(line.line_net)} ${invoice.currency}</td>
    </tr>
  `).join('');

  const vatText = invoice.is_kleinunternehmer
    ? 'Gemäß § 19 UStG wird keine Umsatzsteuer berechnet.'
    : `${euro(totals.total_vat)} ${invoice.currency}`;

  return `
    <h2>Rechnung ${invoice.invoice_number}</h2>
    <p><strong>Rechnungsdatum:</strong> ${invoice.issue_date} | <strong>Leistungsdatum:</strong> ${invoice.service_date}</p>

    <div style="display:flex; gap:2rem; flex-wrap: wrap;">
      <div>
        <h3>Verkäufer</h3>
        <div>${invoice.seller.name}</div>
        <div>${invoice.seller.street}</div>
        <div>${invoice.seller.zip_code} ${invoice.seller.city}</div>
        <div>${invoice.seller.country}</div>
        <div>USt-IdNr.: ${invoice.seller.vat_id || '-'}</div>
        <div>Steuernummer: ${invoice.seller.tax_number || '-'}</div>
      </div>
      <div>
        <h3>Kunde</h3>
        <div>${invoice.buyer.name}</div>
        <div>${invoice.buyer.street}</div>
        <div>${invoice.buyer.zip_code} ${invoice.buyer.city}</div>
        <div>${invoice.buyer.country}</div>
      </div>
    </div>

    <table class="invoice-table">
      <thead>
        <tr>
          <th>Beschreibung</th><th>Menge</th><th>Einheit</th><th>Einzelpreis (netto)</th><th>MwSt.</th><th>Gesamt (netto)</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>

    <div class="totals">
      <div>Nettobetrag: ${euro(totals.total_net)} ${invoice.currency}</div>
      <div>Umsatzsteuer: ${vatText}</div>
      <div><strong>Gesamtbetrag: ${euro(totals.total_gross)} ${invoice.currency}</strong></div>
    </div>

    <p><strong>Zahlungsbedingungen:</strong> ${invoice.payment_terms || '-'}</p>
    <p><strong>IBAN:</strong> ${invoice.payment_iban || '-'} | <strong>BIC:</strong> ${invoice.payment_bic || '-'}</p>
    <p>${invoice.note || ''}</p>
  `;
}

function toUblXml(invoice, totals) {
  const taxPercent = invoice.is_kleinunternehmer ? '0.00' : '19.00';
  const category = invoice.is_kleinunternehmer ? 'E' : 'S';

  const linesXml = totals.lines.map((line, i) => `
    <cac:InvoiceLine>
      <cbc:ID>${i + 1}</cbc:ID>
      <cbc:InvoicedQuantity unitCode="${line.unit}">${line.quantity}</cbc:InvoicedQuantity>
      <cbc:LineExtensionAmount currencyID="${invoice.currency}">${euro(line.line_net)}</cbc:LineExtensionAmount>
      <cac:Item>
        <cbc:Name>${line.description}</cbc:Name>
        <cac:ClassifiedTaxCategory>
          <cbc:ID>${category}</cbc:ID>
          <cbc:Percent>${invoice.is_kleinunternehmer ? '0.00' : euro(line.vat_rate)}</cbc:Percent>
          <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
        </cac:ClassifiedTaxCategory>
      </cac:Item>
      <cac:Price><cbc:PriceAmount currencyID="${invoice.currency}">${euro(line.unit_price_net)}</cbc:PriceAmount></cac:Price>
    </cac:InvoiceLine>
  `).join('');

  return `<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2">
  <cbc:CustomizationID>urn:cen.eu:en16931:2017#compliant#urn:xeinkauf.de:kosit:xrechnung_3.0</cbc:CustomizationID>
  <cbc:ProfileID>urn:fdc:peppol.eu:2017:poacc:billing:01:1.0</cbc:ProfileID>
  <cbc:ID>${invoice.invoice_number}</cbc:ID>
  <cbc:IssueDate>${invoice.issue_date}</cbc:IssueDate>
  <cbc:InvoiceTypeCode>380</cbc:InvoiceTypeCode>
  <cbc:DocumentCurrencyCode>${invoice.currency}</cbc:DocumentCurrencyCode>
  <cac:AccountingSupplierParty><cac:Party><cac:PartyName><cbc:Name>${invoice.seller.name}</cbc:Name></cac:PartyName></cac:Party></cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty><cac:Party><cac:PartyName><cbc:Name>${invoice.buyer.name}</cbc:Name></cac:PartyName></cac:Party></cac:AccountingCustomerParty>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="${invoice.currency}">${euro(totals.total_vat)}</cbc:TaxAmount>
    <cac:TaxSubtotal>
      <cbc:TaxableAmount currencyID="${invoice.currency}">${euro(totals.total_net)}</cbc:TaxableAmount>
      <cbc:TaxAmount currencyID="${invoice.currency}">${euro(totals.total_vat)}</cbc:TaxAmount>
      <cac:TaxCategory>
        <cbc:ID>${category}</cbc:ID>
        <cbc:Percent>${taxPercent}</cbc:Percent>
        <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
      </cac:TaxCategory>
    </cac:TaxSubtotal>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="${invoice.currency}">${euro(totals.total_net)}</cbc:LineExtensionAmount>
    <cbc:TaxExclusiveAmount currencyID="${invoice.currency}">${euro(totals.total_net)}</cbc:TaxExclusiveAmount>
    <cbc:TaxInclusiveAmount currencyID="${invoice.currency}">${euro(totals.total_gross)}</cbc:TaxInclusiveAmount>
    <cbc:PayableAmount currencyID="${invoice.currency}">${euro(totals.total_gross)}</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  ${linesXml}
</Invoice>`;
}

function download(filename, content, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function render() {
  const invoice = getInvoice();
  const totals = computeTotals(invoice);
  preview.innerHTML = renderPreviewHTML(invoice, totals);
}

form.addEventListener('input', render);
document.getElementById('add-line').addEventListener('click', () => {
  createLine({
    description: 'Neue Position',
    quantity: 1,
    unit: 'C62',
    unit_price_net: 0,
    vat_rate: 19
  });
  render();
});

document.getElementById('download-json').addEventListener('click', () => {
  const invoice = getInvoice();
  download(`invoice_${invoice.invoice_number}.json`, JSON.stringify(invoice, null, 2), 'application/json');
});

document.getElementById('download-html').addEventListener('click', () => {
  const invoice = getInvoice();
  const totals = computeTotals(invoice);
  const html = `<!doctype html><html lang="de"><meta charset="utf-8"><title>Rechnung ${invoice.invoice_number}</title><body>${renderPreviewHTML(invoice, totals)}</body></html>`;
  download(`invoice_${invoice.invoice_number}.html`, html, 'text/html');
});

document.getElementById('download-xml').addEventListener('click', () => {
  const invoice = getInvoice();
  const totals = computeTotals(invoice);
  const xml = toUblXml(invoice, totals);
  download(`invoice_${invoice.invoice_number}.xml`, xml, 'application/xml');
});

createLine({ description: '3D-Druck Gehäuse PLA (schwarz)', quantity: 10, unit: 'C62', unit_price_net: 12.5, vat_rate: 19 });
createLine({ description: 'Konstruktionsanpassung CAD', quantity: 1, unit: 'HUR', unit_price_net: 65, vat_rate: 19 });
render();
