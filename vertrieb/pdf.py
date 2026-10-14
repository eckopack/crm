"""Erzeugt Angebots-, Lieferschein- und Rechnungs-PDFs auf dem ECKO-PACK-Briefpapier.

Nutzt reportlab (reine Python-Bibliothek, keine Systemabhängigkeiten wie Pango/Cairo)
statt WeasyPrint, damit es auf Render ohne zusätzliche Build-Pakete läuft.
"""
import io
import os
from decimal import Decimal

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

BRIEFPAPIER_PFAD = os.path.join(settings.BASE_DIR, "vertrieb", "pdf_assets", "briefpapier.png")

SEITENBREITE, SEITENHOEHE = A4

RAND_LINKS = 56
RAND_RECHTS = 56
INHALT_BREITE = SEITENBREITE - RAND_LINKS - RAND_RECHTS

HEADER_START_Y = 690   # erste Zeile der Adresse/Meta-Box (von unten gemessen)
ZEILENHOEHE = 13
TITEL_ABSTAND = 24
DIVIDER_ABSTAND = 8

TOP_MARGIN = SEITENHOEHE - 575   # reserviert Platz fuer Adresse/Meta/Titel oberhalb der Frame
BOTTOM_MARGIN = 150              # reserviert Platz fuer die Fusszeile des Briefpapiers

MINT = colors.HexColor("#05db8e")
DUNKEL = colors.HexColor("#3c3c3b")
GRAU = colors.HexColor("#6c6c6c")

STIL_TEXT = ParagraphStyle("Text", fontName="Helvetica", fontSize=9.5, leading=12.5, textColor=DUNKEL)
STIL_TEXT_RECHTS = ParagraphStyle("TextRechts", parent=STIL_TEXT, alignment=TA_RIGHT)
STIL_NOTIZEN = ParagraphStyle("Notizen", fontName="Helvetica", fontSize=9.5, leading=13, textColor=DUNKEL, spaceBefore=4)


def _eur(betrag):
    text = f"{betrag:,.2f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def _eur_praezise(betrag):
    """Wie _eur(), aber mit bis zu 5 statt 2 Nachkommastellen (mindestens 2).

    Für Einzelpreise von Stückgut-Artikeln mit Bruchteilscent-Preisen (z. B. 0,01298 €
    je Trinkhalm, siehe Artikel-/Preisstaffel-Import): die Positionssumme wird intern mit
    voller Präzision berechnet, aber bei der normalen 2-Nachkommastellen-Anzeige würde der
    Einzelpreis auf 0,01 € gerundet erscheinen - wer das von Hand nachrechnet, käme auf
    ein falsches Ergebnis, obwohl die gedruckte Summe stimmt."""
    text = f"{betrag:,.5f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    ganzzahl, dezimal = text.split(",")
    dezimal = dezimal.rstrip("0")
    if len(dezimal) < 2:
        dezimal = dezimal.ljust(2, "0")
    return f"{ganzzahl},{dezimal} €"


def _menge(wert):
    wert = Decimal(wert)
    if wert == wert.to_integral_value():
        return f"{int(wert):,}".replace(",", ".")
    text = f"{wert:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _datum(d):
    if d is None:
        return "–"
    return d.strftime("%d.%m.%Y")


def _satz_text(satz):
    satz_normal = satz.normalize()
    if satz_normal == satz_normal.to_integral():
        return f"{int(satz_normal)} %"
    return f"{satz_normal} %"


def _empfaenger_zeilen(firma, kontakt=None):
    zeilen = [firma.name]
    if kontakt:
        zeilen.append(f"z. Hd. {kontakt.vorname} {kontakt.nachname}")
    if firma.strasse:
        zeilen.append(firma.strasse)
    plz_ort = f"{firma.plz} {firma.ort}".strip()
    if plz_ort:
        zeilen.append(plz_ort)
    if firma.land and firma.land.lower() != "deutschland":
        zeilen.append(firma.land)
    return zeilen


def _hintergrund_zeichnen(canvas_obj, doc):
    canvas_obj.saveState()
    if os.path.exists(BRIEFPAPIER_PFAD):
        canvas_obj.drawImage(
            BRIEFPAPIER_PFAD, 0, 0, width=SEITENBREITE, height=SEITENHOEHE,
            preserveAspectRatio=False, mask="auto",
        )
    canvas_obj.restoreState()


def _kopf_erste_seite(empfaenger_zeilen, meta_zeilen, titel):
    def zeichnen(canvas_obj, doc):
        _hintergrund_zeichnen(canvas_obj, doc)
        canvas_obj.saveState()

        y = HEADER_START_Y
        canvas_obj.setFont("Helvetica", 10)
        canvas_obj.setFillColor(DUNKEL)
        for zeile in empfaenger_zeilen:
            canvas_obj.drawString(RAND_LINKS, y, zeile)
            y -= ZEILENHOEHE

        y_meta = HEADER_START_Y
        meta_x = SEITENBREITE - RAND_RECHTS
        for label, wert in meta_zeilen:
            canvas_obj.setFont("Helvetica", 10)
            wert_breite = canvas_obj.stringWidth(wert, "Helvetica", 10)
            canvas_obj.drawRightString(meta_x, y_meta, wert)
            canvas_obj.setFont("Helvetica-Bold", 10)
            canvas_obj.drawRightString(meta_x - wert_breite, y_meta, f"{label}: ")
            y_meta -= ZEILENHOEHE + 3

        y_titel = min(y, y_meta) - TITEL_ABSTAND
        canvas_obj.setFont("Helvetica-Bold", 16)
        canvas_obj.setFillColor(DUNKEL)
        canvas_obj.drawString(RAND_LINKS, y_titel, titel)
        canvas_obj.setStrokeColor(MINT)
        canvas_obj.setLineWidth(1.6)
        canvas_obj.line(RAND_LINKS, y_titel - DIVIDER_ABSTAND, SEITENBREITE - RAND_RECHTS, y_titel - DIVIDER_ABSTAND)
        canvas_obj.restoreState()
    return zeichnen


def _kopf_folgeseite(titel, nummer):
    def zeichnen(canvas_obj, doc):
        _hintergrund_zeichnen(canvas_obj, doc)
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.setFillColor(GRAU)
        canvas_obj.drawString(RAND_LINKS, HEADER_START_Y + 30, f"{titel} {nummer} – Fortsetzung")
        canvas_obj.restoreState()
    return zeichnen


def _positionstabelle(spalten, zeilen):
    """spalten: Liste von (Kopfzeile, Breite, Ausrichtung ('l'|'r')).
    zeilen: Liste von Zeilen, jede Zeile eine Liste von Werten passend zu spalten."""
    kopf = []
    for label, _, ausrichtung in spalten:
        stil = STIL_TEXT_RECHTS if ausrichtung == "r" else STIL_TEXT
        kopf.append(Paragraph(f"<b>{label}</b>", stil))

    daten = [kopf]
    for zeile in zeilen:
        formatiert = []
        for wert, (_, _, ausrichtung) in zip(zeile, spalten):
            stil = STIL_TEXT_RECHTS if ausrichtung == "r" else STIL_TEXT
            formatiert.append(Paragraph(str(wert), stil))
        daten.append(formatiert)

    breiten = [b for _, b, _ in spalten]
    tabelle = Table(daten, colWidths=breiten, repeatRows=1)
    tabelle.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, MINT),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#dddddd")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return tabelle


def _summentabelle(zeilen, fett_letzte=True):
    daten = []
    for i, (label, wert) in enumerate(zeilen):
        stil_label = STIL_TEXT_RECHTS
        stil_wert = STIL_TEXT_RECHTS
        if fett_letzte and i == len(zeilen) - 1:
            stil_label = ParagraphStyle("SummeLabel", parent=STIL_TEXT_RECHTS, fontName="Helvetica-Bold")
            stil_wert = ParagraphStyle("SummeWert", parent=STIL_TEXT_RECHTS, fontName="Helvetica-Bold")
        daten.append([Paragraph(label, stil_label), Paragraph(wert, stil_wert)])

    tabelle = Table(daten, colWidths=[INHALT_BREITE - 110, 110])
    stil = [
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]
    if fett_letzte:
        stil.append(("LINEABOVE", (0, -1), (-1, -1), 1.0, DUNKEL))
        stil.append(("TOPPADDING", (0, -1), (-1, -1), 6))
    tabelle.setStyle(TableStyle(stil))
    return tabelle


def _dokument_pdf_bytes(*, titel, nummer, empfaenger_zeilen, meta_zeilen, spalten, zeilen,
                         summenzeilen=None, notizen_titel=None, notizen_text=None, fusshinweis=None):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
        leftMargin=RAND_LINKS, rightMargin=RAND_RECHTS,
    )

    story = [_positionstabelle(spalten, zeilen)]

    if summenzeilen:
        story.append(Spacer(1, 10))
        story.append(_summentabelle(summenzeilen))

    if notizen_text:
        story.append(Spacer(1, 18))
        if notizen_titel:
            story.append(Paragraph(f"<b>{notizen_titel}</b>", STIL_NOTIZEN))
        for absatz in str(notizen_text).split("\n"):
            if absatz.strip():
                story.append(Paragraph(absatz, STIL_NOTIZEN))

    if fusshinweis:
        story.append(Spacer(1, 16))
        story.append(Paragraph(fusshinweis, STIL_NOTIZEN))

    doc.build(
        story,
        onFirstPage=_kopf_erste_seite(empfaenger_zeilen, meta_zeilen, titel),
        onLaterPages=_kopf_folgeseite(titel, nummer),
    )
    return buffer.getvalue()


def _kopf_intern_erste_seite(info_zeilen, meta_zeilen, titel):
    """Kopf für interne Lagerdokumente (Packschein): kein Briefpapier-Hintergrund,
    stattdessen ein schlichter Hinweis-Header statt Kunden-/Firmenadresse."""
    def zeichnen(canvas_obj, doc):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 8.5)
        canvas_obj.setFillColor(GRAU)
        canvas_obj.drawString(RAND_LINKS, SEITENHOEHE - 40, "ECKO-PACK GmbH – Internes Dokument, nicht für den Kundenversand")

        y = HEADER_START_Y
        canvas_obj.setFont("Helvetica", 10)
        canvas_obj.setFillColor(DUNKEL)
        for zeile in info_zeilen:
            canvas_obj.drawString(RAND_LINKS, y, zeile)
            y -= ZEILENHOEHE

        y_meta = HEADER_START_Y
        meta_x = SEITENBREITE - RAND_RECHTS
        for label, wert in meta_zeilen:
            canvas_obj.setFont("Helvetica", 10)
            wert_breite = canvas_obj.stringWidth(wert, "Helvetica", 10)
            canvas_obj.drawRightString(meta_x, y_meta, wert)
            canvas_obj.setFont("Helvetica-Bold", 10)
            canvas_obj.drawRightString(meta_x - wert_breite, y_meta, f"{label}: ")
            y_meta -= ZEILENHOEHE + 3

        y_titel = min(y, y_meta) - TITEL_ABSTAND
        canvas_obj.setFont("Helvetica-Bold", 16)
        canvas_obj.setFillColor(DUNKEL)
        canvas_obj.drawString(RAND_LINKS, y_titel, titel)
        canvas_obj.setStrokeColor(MINT)
        canvas_obj.setLineWidth(1.6)
        canvas_obj.line(RAND_LINKS, y_titel - DIVIDER_ABSTAND, SEITENBREITE - RAND_RECHTS, y_titel - DIVIDER_ABSTAND)
        canvas_obj.restoreState()
    return zeichnen


def _kopf_intern_folgeseite(titel, nummer):
    def zeichnen(canvas_obj, doc):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.setFillColor(GRAU)
        canvas_obj.drawString(RAND_LINKS, SEITENHOEHE - 40, f"{titel} {nummer} – Fortsetzung (internes Dokument)")
        canvas_obj.restoreState()
    return zeichnen


def _unterschriftenzeile():
    tabelle = Table(
        [[
            Paragraph("Kommissioniert von (Name, Datum, Unterschrift)", STIL_TEXT),
            Paragraph("Kontrolliert von (Name, Datum, Unterschrift)", STIL_TEXT),
        ]],
        colWidths=[INHALT_BREITE / 2, INHALT_BREITE / 2],
    )
    tabelle.setStyle(TableStyle([
        ("LINEABOVE", (0, 0), (0, 0), 0.6, GRAU),
        ("LINEABOVE", (1, 0), (1, 0), 0.6, GRAU),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
    ]))
    return tabelle


def packschein_pdf_erzeugen(packschein):
    """Internes Kommissionier-/Packdokument fürs Lager – schlicht, ohne Briefpapier
    und ohne Preisangaben; mit Ankreuzspalte je Position zum händischen Abhaken."""
    deal = packschein.deal
    firma = deal.firma
    info_zeilen = [f"Firma: {firma.name}", f"Deal: {deal.titel}"]

    meta_zeilen = [
        ("Packscheinnummer", packschein.nummer),
        ("Kommissionierdatum", _datum(packschein.datum)),
        ("Kommissioniert von", packschein.kommissionierer or "–"),
        ("Status", packschein.get_status_display()),
        ("Bezug Angebot", packschein.angebot.nummer if packschein.angebot_id else "–"),
    ]
    spalten = [
        ("Pos.", 32, "l"), ("Bezeichnung", 265, "l"), ("Menge", 70, "r"),
        ("Einheit", 70, "r"), ("Gepackt", 46, "r"),
    ]
    zeilen = []
    for p in packschein.positionen.all():
        # Unicode-Kästchen (☐/☑) werden von reportlabs Standard-Helvetica nicht
        # unterstützt (kaputtes Glyph im PDF) - daher ASCII-Darstellung.
        haken = "[X]" if p.gepackt else "[  ]"
        zeilen.append([p.position, p.bezeichnung, _menge(p.menge), p.get_einheit_display(), haken])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
        leftMargin=RAND_LINKS, rightMargin=RAND_RECHTS,
    )
    story = [_positionstabelle(spalten, zeilen)]

    if packschein.notizen:
        story.append(Spacer(1, 18))
        story.append(Paragraph("<b>Notizen (z. B. Lagerplatz, Besonderheiten)</b>", STIL_NOTIZEN))
        for absatz in str(packschein.notizen).split("\n"):
            if absatz.strip():
                story.append(Paragraph(absatz, STIL_NOTIZEN))

    story.append(Spacer(1, 36))
    story.append(_unterschriftenzeile())

    doc.build(
        story,
        onFirstPage=_kopf_intern_erste_seite(info_zeilen, meta_zeilen, "PACKSCHEIN"),
        onLaterPages=_kopf_intern_folgeseite("PACKSCHEIN", packschein.nummer),
    )
    return buffer.getvalue()


def angebot_pdf_erzeugen(angebot):
    deal = angebot.deal
    firma = deal.firma
    empfaenger_zeilen = _empfaenger_zeilen(firma, deal.kontakt)
    meta_zeilen = [
        ("Angebotsnummer", angebot.nummer),
        ("Datum", _datum(angebot.datum)),
        ("Gültig bis", _datum(angebot.gueltig_bis)),
    ]
    spalten = [
        ("Pos.", 32, "l"), ("Bezeichnung", 203, "l"), ("Menge", 55, "r"),
        ("Einheit", 55, "r"), ("Einzelpreis", 70, "r"), ("Gesamt", 68, "r"),
    ]
    zeilen = []
    for p in angebot.positionen.all():
        zeilen.append([p.position, p.bezeichnung, _menge(p.menge), p.get_einheit_display(),
                        _eur_praezise(p.einzelpreis), _eur(p.gesamtpreis)])
    summenzeilen = [("Gesamtsumme (netto, zzgl. gesetzl. USt.)", _eur(angebot.gesamtsumme))]
    return _dokument_pdf_bytes(
        titel="ANGEBOT", nummer=angebot.nummer, empfaenger_zeilen=empfaenger_zeilen,
        meta_zeilen=meta_zeilen, spalten=spalten, zeilen=zeilen, summenzeilen=summenzeilen,
        notizen_titel="Konditionen" if angebot.notizen else None, notizen_text=angebot.notizen,
    )


def lieferschein_pdf_erzeugen(lieferschein):
    deal = lieferschein.deal
    firma = deal.firma
    empfaenger_zeilen = _empfaenger_zeilen(firma, deal.kontakt)
    meta_zeilen = [
        ("Lieferscheinnummer", lieferschein.nummer),
        ("Lieferdatum", _datum(lieferschein.datum)),
        ("Bezug Angebot", lieferschein.angebot.nummer if lieferschein.angebot_id else "–"),
    ]
    spalten = [
        ("Pos.", 36, "l"), ("Bezeichnung", 297, "l"), ("Menge", 75, "r"), ("Einheit", 75, "r"),
    ]
    zeilen = []
    for p in lieferschein.positionen.all():
        zeilen.append([p.position, p.bezeichnung, _menge(p.menge), p.get_einheit_display()])

    pdf_bytes = _dokument_pdf_bytes(
        titel="LIEFERSCHEIN", nummer=lieferschein.nummer, empfaenger_zeilen=empfaenger_zeilen,
        meta_zeilen=meta_zeilen, spalten=spalten, zeilen=zeilen,
        notizen_titel="Hinweise" if lieferschein.notizen else None, notizen_text=lieferschein.notizen,
        fusshinweis="Die oben genannten Positionen wurden geliefert.",
    )
    return pdf_bytes


def rechnung_pdf_erzeugen(rechnung):
    deal = rechnung.deal
    firma = deal.firma
    empfaenger_zeilen = _empfaenger_zeilen(firma, deal.kontakt)
    meta_zeilen = [
        ("Rechnungsnummer", rechnung.nummer),
        ("Rechnungsdatum", _datum(rechnung.rechnungsdatum)),
        ("Leistungsdatum", _datum(rechnung.leistungsdatum or rechnung.rechnungsdatum)),
        ("Zahlungsziel", f"{rechnung.zahlungsziel_tage} Tage netto"),
        ("Fällig am", _datum(rechnung.faelligkeitsdatum)),
    ]
    spalten = [
        ("Pos.", 30, "l"), ("Bezeichnung", 168, "l"), ("Menge", 45, "r"), ("Einheit", 45, "r"),
        ("Einzelpreis", 60, "r"), ("USt.", 40, "r"), ("Gesamt (netto)", 95, "r"),
    ]
    zeilen = []
    for p in rechnung.positionen.all():
        zeilen.append([
            p.position, p.bezeichnung, _menge(p.menge), p.get_einheit_display(),
            _eur_praezise(p.einzelpreis), _satz_text(p.steuersatz), _eur(p.nettobetrag),
        ])

    summenzeilen = [("Nettosumme", _eur(rechnung.nettosumme))]
    for satz, netto, steuer in rechnung.steuer_aufschluesselung:
        summenzeilen.append((f"zzgl. USt {_satz_text(satz)} auf {_eur(netto)}", _eur(steuer)))
    summenzeilen.append(("Gesamtbetrag (brutto)", _eur(rechnung.bruttosumme)))

    zahlungstext = (
        f"Bitte überweisen Sie den Rechnungsbetrag bis zum {_datum(rechnung.faelligkeitsdatum)} "
        f"ohne Abzug auf unten genanntes Konto."
    )
    notizen_text = zahlungstext
    if rechnung.notizen:
        notizen_text = f"{zahlungstext}\n{rechnung.notizen}"

    return _dokument_pdf_bytes(
        titel="RECHNUNG", nummer=rechnung.nummer, empfaenger_zeilen=empfaenger_zeilen,
        meta_zeilen=meta_zeilen, spalten=spalten, zeilen=zeilen, summenzeilen=summenzeilen,
        notizen_titel="Zahlungshinweis", notizen_text=notizen_text,
    )
