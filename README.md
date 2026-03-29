# invoice-generator

Ein Rechnungstool für 3D-Druck-Kunden mit zwei Wegen:

- **CLI** (`invoice_tool.py`) für JSON → HTML (+ optional XML E-Rechnung)
- **Web-App** (`web/`) mit **Live-Vorschau rechts**, während links Felder bearbeitet werden

## Voraussetzungen

- Python 3.11+ (nur Standardbibliothek)

## 1) CLI nutzen

```bash
python3 invoice_tool.py --input example_invoice.json --out ./output --e-invoice
```

Erzeugt im Ausgabeordner z. B.:

- `invoice_2026-0001.html`
- `invoice_2026-0001.xml` (bei `--e-invoice`)

## 2) Web-App lokal starten

```bash
python3 web_server.py
```

Dann im Browser öffnen:

- `http://127.0.0.1:8080`

Features der Web-App:

- Formular links, **Live-Rechnung rechts**
- Positionen hinzufügen/entfernen
- Download von JSON, HTML und XML-E-Rechnung

## 3) GitHub Pages Deployment

Das Projekt ist so vorbereitet, dass die Web-App aus `web/` direkt über **GitHub Pages** deployed werden kann.

### Einmalig im Repository

1. **Settings → Pages** öffnen.
2. Bei **Build and deployment** als Source **GitHub Actions** auswählen.
3. Workflow `.github/workflows/deploy-pages.yml` ist bereits enthalten.

### Danach bei jedem Push auf `main`

- GitHub Actions baut die statische Web-App aus `web/`.
- Die Seite wird automatisch auf GitHub Pages veröffentlicht.

Deine URL ist dann typischerweise:

- `https://<dein-user>.github.io/<repo-name>/`

## Eingabeformat (CLI)

Siehe `example_invoice.json`.

Wichtige Felder:

- `invoice_number`: Rechnungsnummer
- `issue_date`: Rechnungsdatum (YYYY-MM-DD)
- `service_date`: Liefer-/Leistungsdatum
- `seller`: Ausstellerdaten (inkl. Steuernummer oder USt-IdNr.)
- `buyer`: Kundendaten
- `lines`: Positionen mit Menge, Einheit, Nettopreis, MwSt-Satz
- `is_kleinunternehmer`: `true/false`

## Pflichtangaben (DE, praxisnah)

Das Tool prüft u. a.:

- fortlaufende Rechnungsnummer
- vollständige Adressdaten von Verkäufer/Käufer
- Rechnungs- und Leistungsdatum
- Leistungsbeschreibung
- Menge/Einheit/Einzelpreis
- Steuernummer oder USt-IdNr. des Ausstellers
- Netto-/Steuer-/Bruttosummen
- Hinweis für Kleinunternehmerregelung (§ 19 UStG)

> Hinweis: Die rechtliche Beurteilung kann je nach Fall (B2C, B2B EU, Reverse Charge etc.) abweichen. Für produktiven Einsatz sollte ein Steuerberater eingebunden werden.

## E-Rechnungs-Hinweis

Die XML-Ausgabe ist UBL-2.1-basiert und orientiert sich an EN16931/XRechnung-Strukturen.
Für verbindlichen Versand (z. B. öffentliche Auftraggeber) sollte eine formale XRechnung-Validierung (XSD/Schematron) erfolgen.
