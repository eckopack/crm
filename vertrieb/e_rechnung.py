# E-Rechnung (ZUGFeRD/Factur-X) fuer Ausgangsrechnungen - 24.11.2026, auf Wunsch von Björn
# im Zuge der Pflicht zur elektronischen Rechnung (Wachstumschancengesetz, § 14 Abs. 1 S. 3
# UStG): seit 1.1.2025 gilt ein PDF per E-Mail rechtlich nur noch als "sonstige Rechnung",
# nicht mehr als E-Rechnung. Björns Entscheidung (AskUserQuestion, 24.11.2026):
#   - Format: ZUGFeRD/Factur-X-Hybrid (bestehendes, menschenlesbares PDF bleibt wie bisher,
#     zusaetzlich eingebettete, maschinenlesbare XML nach EN 16931) - NICHT reine XRechnung.
#   - Geltungsbereich: einheitlich fuer ALLE Ausgangsrechnungen, keine Sonderbehandlung nach
#     Inland/Ausland (das ZUGFeRD-PDF bleibt fuer jeden Empfaenger optisch identisch lesbar,
#     daher kein Nachteil fuer Kunden, die nur das PDF ansehen).
#
# Technik: drafthorse erzeugt die CII-XML (Cross Industry Invoice, EN-16931-Profil) UND
# validiert sie beim serialize() gegen die mitgelieferte offizielle Factur-X-1.0.07-XSD
# (schema="FACTUR-X_EN16931") - ein struktureller Fehler wirft hier eine XMLSyntaxError,
# NICHT erst beim Empfaenger. drafthorse.pdf.attach_xml() bettet die XML in das bestehende
# reportlab-PDF (pdf.rechnung_pdf_erzeugen) ein und setzt die ZUGFeRD-XMP-Metadaten. Danach
# macht pikepdf.pdfa (Flavour "3b") aus dem Ergebnis ein echtes PDF/A-3b (fehlendes
# ICC-Output-Intent wird ergaenzt, Embedded-File-Metadaten werden auf PDF/A-3-Konformitaet
# nachgebessert) UND validiert das geschriebene Ergebnis gegen die PDF/A-3b-Spezifikation -
# schlaegt das fehl, wirft save() eine PdfaError, bevor irgendetwas verschickt wird.
#
# Bewusst NICHT geprueft: die vollen EN-16931-Geschaeftsregeln (Schematron/KoSIT-Validator,
# z. B. "bei Kategorie != S ist eine ExemptionReason patflichf") - das ist mit Bordmitteln
# dieser Sandbox (kein Java/KoSIT verfuegbar) nicht moeglich. Insbesondere der Fall
# Steuersatz 0% ("steuerfrei") ist im bestehenden Rechnung-Modell nicht weiter danach
# unterschieden, WARUM steuerfrei (Export, innergemeinschaftliche Lieferung, § 19 UStG...).
# Hier wird pragmatisch Kategorie "Z" (Zero rated) mit Freitext-Begruendung "Steuerfrei"
# gesetzt - das sollte vor dem produktiven Einsatz mit Eileen Paetzel (Steuerberatung
# GUTOM/ECKO-PACK) abgeglichen werden, siehe PR-Beschreibung.
from datetime import date
from decimal import Decimal
from io import BytesIO

from drafthorse.models.accounting import ApplicableTradeTax
from drafthorse.models.document import Document
from drafthorse.models.payment import PaymentMeans
from drafthorse.models.tradelines import LineItem
from drafthorse.pdf import attach_xml

from . import pdf as rechnung_pdf


# Land (Freitext in Firma.land) -> ISO-3166-1-alpha-2. EN 16931 verlangt zwingend einen
# gueltigen Laendercode (PostalTradeAddress.country_id, BT-40/BT-55) - bewusst KEIN stiller
# Fallback auf "DE" o.ae., ein unbekanntes Land soll die Generierung mit einer klaren
# Fehlermeldung stoppen statt eine falsche Rechnung zu erzeugen (siehe
# _land_iso_code unten).
LAND_ISO_CODES = {
    "deutschland": "DE",
    "österreich": "AT",
    "oesterreich": "AT",
    "schweiz": "CH",
    "niederlande": "NL",
    "belgien": "BE",
    "frankreich": "FR",
    "italien": "IT",
    "polen": "PL",
    "tschechien": "CZ",
    "dänemark": "DK",
    "daenemark": "DK",
    "schweden": "SE",
    "norwegen": "NO",
    "spanien": "ES",
    "portugal": "PT",
    "luxemburg": "LU",
    "ungarn": "HU",
    "slowakei": "SK",
    "slowenien": "SI",
    "kroatien": "HR",
    "rumänien": "RO",
    "rumaenien": "RO",
    "finnland": "FI",
    "irland": "IE",
    "vereinigtes königreich": "GB",
    "vereinigtes koenigreich": "GB",
    "großbritannien": "GB",
    "grossbritannien": "GB",
    "usa": "US",
    "vereinigte staaten": "US",
    "china": "CN",
}

# RechnungPosition.einheit -> UN/ECE-Rec.-20-Einheitencode (von XRechnung/ZUGFeRD
# vorgeschriebenes Codesystem fuer BilledQuantity/unitCode). "karton" und "pauschal" sind
# keine physikalischen Rec.-20-Maßeinheiten - hier bewusst vereinfacht auf "Stück"/"Eins"
# gemappt, die eigentliche Einheit bleibt im Freitext der Positionsbezeichnung erhalten.
EINHEIT_UNECE_CODES = {
    "stk": "H87",      # piece
    "karton": "H87",   # piece (Vereinfachung, siehe Kommentar oben)
    "std": "HUR",      # hour
    "tag": "DAY",       # day
    "monat": "MON",     # month
    "pauschal": "C62",  # "one" (Zähleinheit ohne spezifische Maßeinheit)
    "kg": "KGM",        # kilogram
    "m": "MTR",         # metre
    "m2": "MTK",        # square metre
}

# ECKO-PACK-Stammdaten (Verkäufer-Partei der XML) - bewusst dieselben Werte wie das
# Briefpapier in pdf.py (_BRIEFPAPIER_FUSSZEILE_DE), dort aber als Layout-Text eingebettet
# und nicht als strukturierte Daten wiederverwendbar. Bei einer Aenderung der Firmendaten
# (Adresse, IBAN, USt-IdNr.) MUSS das hier mitgepflegt werden - siehe Kommentar dort.
ECKO_PACK_NAME = "ECKO-PACK GmbH"
ECKO_PACK_STRASSE = "Wasbeker Straße 324"
ECKO_PACK_PLZ = "24537"
ECKO_PACK_ORT = "Neumünster"
ECKO_PACK_LAND_ISO = "DE"
ECKO_PACK_USTIDNR = "DE334919463"
ECKO_PACK_EMAIL = "info@ecko-pack.de"
ECKO_PACK_IBAN = "DE82213900080004374088"
ECKO_PACK_BIC = "GENODEF1NSH"
ECKO_PACK_BANKNAME = "VR Bank zwischen den Meeren eG"


def _land_iso_code(firma):
    text = (firma.land or "").strip().lower()
    if not text:
        return ECKO_PACK_LAND_ISO  # leeres Land-Feld: wie pdf.py, Annahme Inland
    code = LAND_ISO_CODES.get(text)
    if code is None:
        raise ValueError(
            f"E-Rechnung: Land \"{firma.land}\" von Firma \"{firma}\" ist keinem "
            f"ISO-3166-Code zugeordnet (vertrieb/e_rechnung.py, LAND_ISO_CODES). Bitte "
            f"dort ergänzen oder das Land-Feld bei der Firma korrigieren."
        )
    return code


def _einheit_unece_code(einheit):
    code = EINHEIT_UNECE_CODES.get(einheit)
    if code is None:
        raise ValueError(
            f"E-Rechnung: Einheit \"{einheit}\" ist keinem UN/ECE-Rec.20-Code zugeordnet "
            f"(vertrieb/e_rechnung.py, EINHEIT_UNECE_CODES)."
        )
    return code


def _adresse_setzen(party, name, strasse, plz, ort, land_iso, ust_idnr=None):
    party.name = name
    party.address.line_one = strasse
    party.address.postcode = plz
    party.address.city_name = ort
    party.address.country_id = land_iso
    if ust_idnr:
        reg = party.tax_registrations.empty_element()
        reg.id = ("VA", ust_idnr)  # Schema "VA" = USt-IdNr. (EN 16931, BT-31/BT-48)
        party.tax_registrations.add(reg)


def rechnung_cii_xml_erzeugen(rechnung):
    """Erzeugt die CII-XML (ZUGFeRD/Factur-X, Profil EN 16931) fuer eine Rechnung als
    bytes. Wirft ValueError bei fehlenden/nicht zuordenbaren Stammdaten (Land, Einheit) und
    lxml.etree.XMLSyntaxError, wenn das Ergebnis nicht der offiziellen Factur-X-1.0.07-XSD
    entspricht - beides bewusst VOR dem Versand, nicht erst beim Empfaenger."""
    firma = rechnung.deal.firma
    doc = Document()

    # EN-16931-Kennung (siehe drafthorse.pdf._extract_xml_info: erwartet, dass das
    # vorletzte ":"-Segment "en16931" ist, damit das Profil beim PDF-Einbetten automatisch
    # korrekt erkannt wird).
    doc.context.guideline_parameter.id = "urn:cen.eu:en16931:2017"

    doc.header.id = rechnung.nummer
    doc.header.type_code = "381" if rechnung.storno_zu_id else "380"  # 380=Rechnung, 381=Gutschrift/Storno
    # Kein doc.header.name: das EN-16931-Profil der Factur-X-XSD kennt fuer
    # ExchangedDocument/Header gar kein "Name"-Element (nur ID, TypeCode, IssueDateTime,
    # IncludedNote*) - anders als drafthorse's generisches (BASIC/EXTENDED-taugliches)
    # Python-Modell, das das Feld vorhaelt. Gesetzt wuerde es bei der Validierung gegen
    # FACTUR-X_EN16931 zu einem XSD-Fehler fuehren (per Testlauf verifiziert, 24.11.2026).
    doc.header.issue_date_time = rechnung.rechnungsdatum

    _adresse_setzen(
        doc.trade.agreement.seller, ECKO_PACK_NAME, ECKO_PACK_STRASSE,
        ECKO_PACK_PLZ, ECKO_PACK_ORT, ECKO_PACK_LAND_ISO, ECKO_PACK_USTIDNR,
    )
    doc.trade.agreement.seller.electronic_address.uri_ID = ("EM", ECKO_PACK_EMAIL)

    _adresse_setzen(
        doc.trade.agreement.buyer, firma.name,
        firma.strasse or "", firma.plz or "", firma.ort or "",
        _land_iso_code(firma), firma.ust_idnr or None,
    )
    if firma.email:
        doc.trade.agreement.buyer.electronic_address.uri_ID = ("EM", firma.email)

    # Lieferdatum (BT-72): Leistungsdatum, falls erfasst, sonst Rechnungsdatum (wie im
    # bestehenden PDF, siehe Rechnung.leistungsdatum).
    doc.trade.delivery.event.occurrence = rechnung.leistungsdatum or rechnung.rechnungsdatum

    doc.trade.settlement.currency_code = "EUR"
    doc.trade.settlement.payment_reference = rechnung.nummer
    terms = doc.trade.settlement.terms.empty_element()
    terms.description = f"Zahlbar innerhalb {rechnung.zahlungsziel_tage} Tagen ohne Abzug."
    terms.due = rechnung.faelligkeitsdatum
    doc.trade.settlement.terms.add(terms)

    means = PaymentMeans()
    means.type_code = "58"  # SEPA-Überweisung
    means.payee_account.iban = ECKO_PACK_IBAN
    means.payee_institution.bic = ECKO_PACK_BIC
    doc.trade.settlement.payment_means.add(means)

    for i, position in enumerate(rechnung.positionen.all(), start=1):
        item = LineItem()
        item.document.line_id = str(i)
        item.product.name = position.bezeichnung
        item.agreement.net.amount = position.einzelpreis
        item.delivery.billed_quantity = (position.menge, _einheit_unece_code(position.einheit))

        # item.settlement.trade_tax ist ein einzelnes (nicht Multi-)Field - der von
        # __get__ automatisch angelegte ApplicableTradeTax darf nur IN-PLACE befuellt
        # werden (Element-Felder sind read-only gegenueber Ersetzen, siehe
        # drafthorse.models.fields.Field.__set__).
        steuer = item.settlement.trade_tax
        steuer.calculated_amount = position.steuerbetrag
        steuer.basis_amount = position.nettobetrag
        steuer.rate_applicable_percent = position.steuersatz
        steuer.type_code = "VAT"
        if position.steuersatz == 0:
            steuer.category_code = "Z"
            steuer.exemption_reason = (
                "Steuerfrei - Grund vor Versand mit der Buchhaltung/Steuerberatung "
                "abzugleichen (Export/innergemeinschaftlich/§19 UStG o.ä.)"
            )
        else:
            steuer.category_code = "S"
        item.settlement.monetary_summation.total_amount = position.nettobetrag

        doc.trade.items.add(item)

    netto = rechnung.nettosumme
    steuer_gesamt = rechnung.steuerbetrag
    brutto = rechnung.bruttosumme

    for satz, netto_je_satz, steuer_je_satz in rechnung.steuer_aufschluesselung:
        kopf_steuer = ApplicableTradeTax()
        kopf_steuer.calculated_amount = steuer_je_satz
        kopf_steuer.basis_amount = netto_je_satz
        kopf_steuer.rate_applicable_percent = satz
        kopf_steuer.type_code = "VAT"
        if satz == 0:
            kopf_steuer.category_code = "Z"
            kopf_steuer.exemption_reason = (
                "Steuerfrei - Grund vor Versand mit der Buchhaltung/Steuerberatung "
                "abzugleichen (Export/innergemeinschaftlich/§19 UStG o.ä.)"
            )
        else:
            kopf_steuer.category_code = "S"
        doc.trade.settlement.trade_tax.add(kopf_steuer)

    # Auch hier: in-place befuellen statt ersetzen (siehe Kommentar oben bei trade_tax).
    summe = doc.trade.settlement.monetary_summation
    summe.line_total = netto
    summe.charge_total = Decimal("0")
    summe.allowance_total = Decimal("0")
    summe.tax_basis_total = netto
    summe.tax_total = steuer_gesamt
    summe.grand_total = brutto
    summe.due_amount = rechnung.offener_betrag

    return doc.serialize(schema="FACTUR-X_EN16931")


def _zu_pdfa3b(pdf_bytes):
    """Wandelt pdf_bytes zu PDF/A-3b (ICC-OutputIntent, Metadaten-/Schriftkorrekturen) und
    gibt (bytes, Report) zurueck. Wirft pikepdf.pdfa.PdfaError NUR bei echten Verstoessen
    (Finding.kind == "violation"). "unsupported"-Befunde (Konstrukte, die pikepdfs eigener
    Validator gar nicht pruefen kann - siehe Modul-Docstring: "may be valid PDF/A but the
    validator does not check it") werden toleriert und nur im zurueckgegebenen Report
    sichtbar gemacht, statt die Erzeugung grundlos abzubrechen. Bewusst NICHT
    pikepdf.pdfa.save() direkt verwendet, da dessen interne Pruefung JEDEN Befund (auch
    "unsupported") als Fehlschlag behandelt (per Testlauf 24.11.2026 so vorgefunden, siehe
    PR-Beschreibung)."""
    import pikepdf

    with pikepdf.open(BytesIO(pdf_bytes)) as pdf:
        pikepdf.pdfa.prepare(pdf, "3b", output_intent="sRGB")
        ausgabe = BytesIO()
        pdf.save(ausgabe)
        ausgabe.seek(0)
        ergebnis = ausgabe.read()
    with pikepdf.open(BytesIO(ergebnis)) as pruef_pdf:
        bericht = pikepdf.pdfa.check(pruef_pdf, "3b")
    verstoesse = [f for f in bericht.findings if f.kind == "violation"]
    if verstoesse:
        raise pikepdf.pdfa.PdfaError(bericht)
    return ergebnis, bericht


def rechnung_zugferd_pdf_erzeugen(rechnung):
    """Erzeugt das vollstaendige, versandfertige ZUGFeRD/Factur-X-PDF (PDF/A-3b mit
    eingebetteter EN-16931-XML) als bytes: bestehendes reportlab-Layout (unveraendert) +
    eingebettete, validierte CII-XML + PDF/A-3b-Konformitaet (siehe _zu_pdfa3b fuer die
    genauen Garantien/Grenzen). Wirft PdfaError bei einem echten PDF/A-Verstoss oder
    lxml.etree.XMLSyntaxError bei ungueltiger XML - in beiden Faellen wird NICHTS
    zurueckgegeben, der Aufrufer darf das Ergebnis dann nicht versenden.

    Reihenfolge bewusst: erst das reine reportlab-PDF (ohne Anhang) zu PDF/A-3b wandeln,
    danach erst die XML einbetten - ein frisch eingebetteter Dateianhang ist der eine
    Baustein, den pikepdfs Validator strukturell nicht pruefen kann (siehe _zu_pdfa3b), die
    Basis-PDF/A-3b-Konformitaet (Schriften, Farbraum, Metadaten) soll davon unabhaengig
    sauber durchlaufen."""
    import pikepdf

    basis_pdf = rechnung_pdf.rechnung_pdf_erzeugen(rechnung)
    xml_bytes = rechnung_cii_xml_erzeugen(rechnung)

    pdfa_ohne_anhang, _ = _zu_pdfa3b(basis_pdf)
    mit_xml = attach_xml(pdfa_ohne_anhang, xml_bytes, level="EN 16931")

    # drafthorse setzt beim Einbetten PageMode="/UseAttachments" (oeffnet im Viewer
    # automatisch das Anhang-Panel) - das verletzt PDF/A (Catalog/PageMode darf laut
    # Spezifikation nur UseNone/UseOutlines/UseThumbs/FullScreen sein; per Testlauf
    # 24.11.2026 als echter "violation"-Befund gefunden). Rein kosmetisch, daher fuer
    # PDF/A-3-Konformitaet entfernt statt die Konformitaet aufzuweichen.
    with pikepdf.open(BytesIO(mit_xml)) as endgueltig:
        if "/PageMode" in endgueltig.Root:
            del endgueltig.Root["/PageMode"]
        zwischenablage = BytesIO()
        endgueltig.save(zwischenablage)
        zwischenablage.seek(0)
        mit_xml = zwischenablage.read()

    fertiges_pdf, _ = _zu_pdfa3b(mit_xml)
    return fertiges_pdf
