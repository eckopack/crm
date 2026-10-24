"""Erzeugt Angebots-, Lieferschein- und Rechnungs-PDFs auf dem ECKO-PACK-Briefpapier.

Nutzt reportlab (reine Python-Bibliothek, keine Systemabhängigkeiten wie Pango/Cairo)
statt WeasyPrint, damit es auf Render ohne zusätzliche Build-Pakete läuft.
"""
import io
import os
from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# vertragstexte: reines Text-/Klausel-Modul (keine Models), siehe Kommentar dort zum
# Entwurfscharakter der Klauseln. Separater Import statt Inline-Text hier, damit der
# komplette Vertragswortlaut an einer Stelle gepflegt wird (22.10.2026, Rahmenvertrag-PDF).
from . import vertragstexte

# Briefpapier als Vektor-Zeichenfunktion statt fixem Bild (18.10.2026, siehe
# _hintergrund_zeichnen unten): vorher wurde hier ein fertig gerendertes PNG
# (briefpapier.png, nur Deutsch) per drawImage() als Hintergrund eingeklebt. Björns
# Anforderung "Angebot/Lieferschein/Rechnung müssen komplett in der gewählten Sprache
# rausgehen, inkl. Briefpapier" ließ sich damit nicht erfüllen, ohne zwei Bilddateien zu
# pflegen UND jede künftige Adress-/Bankänderung doppelt nachzuziehen. Stattdessen wird das
# Briefpapier jetzt komplett aus Vektorelementen (Formen + Text) nachgebaut: eine einzige
# Quelle, die Angebot/Lieferschein/Rechnung-Hintergrund für beide Sprachen erzeugt. Die
# Positionen/Farben/Schriftgrößen unten sind per Pixelanalyse aus dem alten
# briefpapier.png (1654×2339px, 200dpi A4) hergeleitet - siehe PX2PT-Hilfsfunktion.
# briefpapier.png selbst bleibt unverändert im Repo (Referenz/Fallback), wird aber ab jetzt
# nirgends mehr geladen.
_PDF_ASSETS = os.path.join(settings.BASE_DIR, "vertrieb", "pdf_assets")
_FONT_REGULAR_PFAD = os.path.join(_PDF_ASSETS, "fonts", "Poppins-Regular.ttf")
_FONT_MEDIUM_PFAD = os.path.join(_PDF_ASSETS, "fonts", "Poppins-Medium.ttf")
LOGO_ICON_PFAD = os.path.join(_PDF_ASSETS, "logo_icon.png")

# Poppins ist KEINE der 14 reportlab-eingebauten Standardschriften (Helvetica/Times/
# Courier) - muss daher als TTF-Datei mitgeliefert und registriert werden, sonst würde ein
# Deploy auf Render (kein Google-Fonts-Paket im Container) mit fehlender Schrift fehlschlagen
# oder lautlos auf irgendeinen Fallback springen. Dateien liegen unter pdf_assets/fonts/
# (Google Fonts, SIL Open Font License - frei einsetzbar). Nur fürs Briefpapier (Logo/
# Fußzeile) verwendet; die eigentlichen Dokumentinhalte (Positionstabelle etc.) bleiben bei
# Helvetica, wie bisher.
if "Poppins" not in pdfmetrics.getRegisteredFontNames():
    pdfmetrics.registerFont(TTFont("Poppins", _FONT_REGULAR_PFAD))
    pdfmetrics.registerFont(TTFont("Poppins-Medium", _FONT_MEDIUM_PFAD))

SEITENBREITE, SEITENHOEHE = A4
_PX2PT = SEITENHOEHE / 2339.0  # Umrechnung Pixel (altes 200dpi-Referenzbild) -> PDF-Punkte


def _px(x, y):
    """Pixelkoordinate (Ursprung oben links, wie im alten briefpapier.png) -> reportlab-
    Punktkoordinate (Ursprung unten links)."""
    return x * _PX2PT, SEITENHOEHE - y * _PX2PT

# RAND_LINKS war bisher 56pt und damit ~15,5pt weiter links als die im Briefpapier-
# Hintergrundbild (briefpapier.png) fest eingebrannte Adresszeile ("ECKO-PACK GMBH ·
# Wasbeker Straße 324 · ..."), die bei ca. x=198px/200dpi = 71,5pt beginnt (per Pixel-
# analyse des Bilds gemessen, 16.10.2026, Björns Rückmeldung anhand eines PDF-Screenshots:
# Empfänger-Adresse/Titel/Tabelle saßen sichtbar links versetzt zur Kopfzeile). RAND_LINKS
# jetzt auf diesen Wert gesetzt, damit Empfängeradresse, Titel, Trennlinie und Tabelle auf
# allen vier Dokumenttypen (Angebot/Packschein/Lieferschein/Rechnung) exakt unter der
# Kopfzeile starten. Die Positionstabellen-Spaltenbreiten (Bezeichnung-Spalte je Dokument)
# wurden um das Delta (15,5pt) reduziert, damit die Tabelle bei schmalerem Inhaltsbereich
# nicht in den rechten Rand hineinragt.
RAND_LINKS = 71.5
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


def _artikelnummer_umbrechen(text, verfuegbare_breite, font_name, font_size):
    """Bricht eine Artikelnummer für die Anzeige in einer schmalen Tabellenspalte NUR an
    vorhandenen Bindestrichen um (21.10.2026, Björns Rückmeldung: "brich bitte bei allen
    Belegen die Artikel Nr. immer beim '-' so sieht das echt dämlich aus!"). Vorher
    überließen wir reportlab seinen Standard-Zeilenumbruch für zu lange "Wörter"
    (splitLongWords), der rein zeichenweise bricht - mitten in einer Zahl oder einem
    Silbenteil, siehe z.B. die Verschlechterung "ART-XYZ-999" / "9-LANGECODE" (bricht die
    Ziffernfolge "9999" mitten durch).

    Passt nichts an (gibt den - XML-escapten - Text unverändert zurück), wenn die
    Artikelnummer ohnehin in die Spalte passt; sonst wird vor jedem Bindestrich, an dem
    ein Umbruch nötig wird, ein <br/> eingefügt (reportlab-Paragraph-Markup), der
    Bindestrich bleibt dabei am Ende der jeweiligen Zeile stehen, statt zusätzlich
    verdoppelt oder durch ein unsichtbares Zeichen ersetzt zu werden (beides wurde
    ausprobiert: ein Soft-Hyphen direkt hinter dem vorhandenen Bindestrich ergab ein
    hässliches doppeltes "--", ein Zero-Width-Space wird von Helvetica/reportlabs
    Standard-14-Schriften gar nicht dargestellt und erzeugt ein kaputtes Glyphen-Kästchen)."""
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from xml.sax.saxutils import escape as _xml_escape

    text = str(text)
    if not text or stringWidth(text, font_name, font_size) <= verfuegbare_breite:
        return _xml_escape(text)

    segmente = []
    rest = text
    while "-" in rest:
        pos = rest.index("-") + 1
        segmente.append(rest[:pos])
        rest = rest[pos:]
    if rest:
        segmente.append(rest)

    zeilen = []
    aktuelle_zeile = ""
    for segment in segmente:
        kandidat = aktuelle_zeile + segment
        if aktuelle_zeile and stringWidth(kandidat, font_name, font_size) > verfuegbare_breite:
            zeilen.append(aktuelle_zeile)
            aktuelle_zeile = segment
        else:
            aktuelle_zeile = kandidat
    if aktuelle_zeile:
        zeilen.append(aktuelle_zeile)

    return "<br/>".join(_xml_escape(z) for z in zeilen)


_MONATE_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _eur(betrag, sprache="de"):
    """sprache="en" (18.10.2026, Angebot.sprache): englische Zahlenkonvention (Punkt als
    Dezimal-, Komma als Tausendertrennzeichen) statt der deutschen - sonst liest sich
    "1.234,56 €" für einen englischsprachigen Kunden leicht als "1,23456" oder "1234,56"."""
    if sprache == "en":
        return f"€{betrag:,.2f}"
    text = f"{betrag:,.2f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{text} €"


def _eur_praezise(betrag, sprache="de"):
    """Wie _eur(), aber mit bis zu 5 statt 2 Nachkommastellen (mindestens 2).

    Für Einzelpreise von Stückgut-Artikeln mit Bruchteilscent-Preisen (z. B. 0,01298 €
    je Trinkhalm, siehe Artikel-/Preisstaffel-Import): die Positionssumme wird intern mit
    voller Präzision berechnet, aber bei der normalen 2-Nachkommastellen-Anzeige würde der
    Einzelpreis auf 0,01 € gerundet erscheinen - wer das von Hand nachrechnet, käme auf
    ein falsches Ergebnis, obwohl die gedruckte Summe stimmt."""
    if sprache == "en":
        text = f"{betrag:.5f}"
        ganzzahl, dezimal = text.split(".")
        dezimal = dezimal.rstrip("0")
        if len(dezimal) < 2:
            dezimal = dezimal.ljust(2, "0")
        return f"€{int(ganzzahl):,}.{dezimal}"
    text = f"{betrag:,.5f}"
    text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    ganzzahl, dezimal = text.split(",")
    dezimal = dezimal.rstrip("0")
    if len(dezimal) < 2:
        dezimal = dezimal.ljust(2, "0")
    return f"{ganzzahl},{dezimal} €"


def _menge(wert, sprache="de"):
    wert = Decimal(wert)
    if sprache == "en":
        if wert == wert.to_integral_value():
            return f"{int(wert):,}"
        return f"{wert:,.2f}"
    if wert == wert.to_integral_value():
        return f"{int(wert):,}".replace(",", ".")
    text = f"{wert:,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def _datum(d, sprache="de"):
    """sprache="en": "18 Oct 2026" statt "18.10.2026" - vermeidet die MM/DD- vs. TT.MM.-
    Verwechslungsgefahr des rein numerischen Formats bei englischsprachigen Kunden."""
    if d is None:
        return "–"
    if sprache == "en":
        return f"{d.day} {_MONATE_EN[d.month - 1]} {d.year}"
    return d.strftime("%d.%m.%Y")


def _satz_text(satz, sprache="de"):
    satz_normal = satz.normalize()
    text = f"{int(satz_normal)}" if satz_normal == satz_normal.to_integral() else f"{satz_normal}"
    return f"{text}%" if sprache == "en" else f"{text} %"


def _empfaenger_zeilen(firma, kontakt=None, sprache="de"):
    """sprache="en" (18.10.2026): "z. Hd." -> "Attn." - war in der ursprünglichen
    Angebot-Sprachfunktion (PR #13) übersehen worden, da kein Testfall einen Kontakt mit
    Empfänger-Adresse auf einem englischen Angebot geprüft hatte. Fällt hier auf, weil
    jetzt auch Lieferschein/Rechnung dieselbe Funktion sprachabhängig nutzen."""
    zeilen = [firma.name]
    if kontakt:
        anrede = "Attn." if sprache == "en" else "z. Hd."
        zeilen.append(f"{anrede} {kontakt.vorname} {kontakt.nachname}")
    if firma.strasse:
        zeilen.append(firma.strasse)
    plz_ort = f"{firma.plz} {firma.ort}".strip()
    if plz_ort:
        zeilen.append(plz_ort)
    if firma.land and firma.land.lower() != "deutschland":
        zeilen.append(firma.land)
    return zeilen


# ---------------------------------------------------------------------------
# Briefpapier-Hintergrund (Vektor-Nachbau, siehe Modul-Kommentar oben)
# ---------------------------------------------------------------------------
# Alle Koordinaten unten sind Pixel-Koordinaten aus dem alten briefpapier.png
# (1654x2339px @ 200dpi), per Konturerkennung (mint-farbige Flächen) bzw. Pixelanalyse
# (Text-Bounding-Boxes, Farben) exakt vermessen - siehe _px() oben für die Umrechnung.

MINT_ECKE = colors.HexColor("#00ffaa")  # Farbe der Eckgrafiken (gemessen) - bewusst eigene
# Konstante, nicht identisch mit MINT (#05db8e, die etwas gedämpftere Akzentfarbe für
# Trennlinien/Tabellenkopf im Dokumentinhalt, unverändert aus der bisherigen Gestaltung).

_BRIEFPAPIER_ECKE_OBEN_RECHTS = [
    (1274, 0), (1653, 500), (1653, 315), (1561, 195), (1653, 44),
    (1653, 0), (1549, 0), (1489, 98), (1414, 0),
]
_BRIEFPAPIER_ECKE_UNTEN_LINKS = [(0, 2026), (0, 2211), (96, 2338), (236, 2338)]
_BRIEFPAPIER_STRICHE = [(29, 69, 826.5), (29, 85, 1170), (29, 69, 1653)]  # (x0, x1, y_mitte)

_BRIEFPAPIER_FUSSZEILE_DE = [
    [("ECKO-PACK GmbH", True), ("Wasbeker Straße 324", False), ("D-24537 Neumünster", False),
     ("T. +49 (0) 4331 - 1348 - 101", False), ("info@ecko-pack.de", False), ("www.ecko-pack.de", False)],
    [("Geschäftsführung:", True), ("Björn Gallenkamp", False), ("Carmen Ungnade-Täuberecht", False),
     ("Amtsgericht Kiel · HRB 22209 KI", False), ("USt-IdNr.: DE334919463", False)],
    [("Bankverbindungen:", True), ("VR Bank zwischen den Meeren eG", False),
     ("IBAN: DE82 2139 0008 0004 3740 88", False), ("BIC: GENODEF1NSH", False),
     ("HypoVereinsbank", False), ("IBAN: DE16 2003 0000 0020 5419 12", False),
     ("BIC: HYVEDEMMXXX", False)],
]
# Englische Fußzeile (18.10.2026, auf Wunsch von Björn: "Amtsgericht Kiel · HRB 22209 KI"
# vollständig übersetzt, nicht nur die üblichen Label wie USt-IdNr./Geschäftsführung -
# Björns ausdrückliche Entscheidung, siehe Konversation). Adresse/IBAN/BIC/Namen bleiben
# unverändert (international ohnehin verständlich bzw. nicht übersetzbar).
_BRIEFPAPIER_FUSSZEILE_EN = [
    [("ECKO-PACK GmbH", True), ("Wasbeker Straße 324", False), ("D-24537 Neumünster", False),
     ("Germany", False), ("Phone: +49 (0) 4331 - 1348 - 101", False),
     ("info@ecko-pack.de", False), ("www.ecko-pack.de", False)],
    [("Management:", True), ("Björn Gallenkamp", False), ("Carmen Ungnade-Täuberecht", False),
     ("Local Court Kiel · HRB 22209 KI", False), ("VAT ID: DE334919463", False)],
    [("Bank details:", True), ("VR Bank zwischen den Meeren eG", False),
     ("IBAN: DE82 2139 0008 0004 3740 88", False), ("BIC: GENODEF1NSH", False),
     ("HypoVereinsbank", False), ("IBAN: DE16 2003 0000 0020 5419 12", False),
     ("BIC: HYVEDEMMXXX", False)],
]


def _briefpapier_text_getrackt(c, text, x, y, font, groesse, farbe, tracking):
    """Zeichnet Text mit zusätzlichem Buchstabenabstand (tracking) - reportlab kennt das
    nicht nativ; wird für Logo/Tagline gebraucht, die im Original deutlich gesperrt gesetzt
    sind (siehe Pixelanalyse)."""
    c.setFont(font, groesse)
    c.setFillColor(farbe)
    cx = x
    for ch in text:
        c.drawString(cx, y, ch)
        cx += c.stringWidth(ch, font, groesse) + tracking


def _hintergrund_zeichnen(canvas_obj, doc, sprache="de"):
    c = canvas_obj
    c.saveState()

    # Eckgrafiken (mint, sprachunabhängig)
    c.setFillColor(MINT_ECKE)
    for form in (_BRIEFPAPIER_ECKE_OBEN_RECHTS, _BRIEFPAPIER_ECKE_UNTEN_LINKS):
        pfad = c.beginPath()
        punkte = [_px(x, y) for x, y in form]
        pfad.moveTo(*punkte[0])
        for punkt in punkte[1:]:
            pfad.lineTo(*punkt)
        pfad.close()
        c.drawPath(pfad, fill=1, stroke=0)

    # Strich-Akzente am linken Rand (sprachunabhängig)
    c.setStrokeColor(GRAU)
    c.setLineWidth(1.4)
    for x0, x1, y_mitte in _BRIEFPAPIER_STRICHE:
        xx0, yy = _px(x0, y_mitte)
        xx1, _ = _px(x1, y_mitte)
        c.line(xx0, yy, xx1, yy)

    # Logo "ECKO [Icon] PACK" (sprachunabhängig - Wortmarke bleibt immer Englisch/neutral)
    logo_groesse, logo_tracking = 27.5, 1.6
    ecko_x, ecko_y = _px(575, 186)
    _briefpapier_text_getrackt(c, "ECKO", ecko_x, ecko_y, "Poppins", logo_groesse, DUNKEL, logo_tracking)
    pack_x, pack_y = _px(880, 186)
    _briefpapier_text_getrackt(c, "PACK", pack_x, pack_y, "Poppins", logo_groesse, DUNKEL, logo_tracking)
    if os.path.exists(LOGO_ICON_PFAD):
        icon_x, icon_y = _px(797, 185)
        icon_breite = (869 - 797) * _PX2PT
        icon_hoehe = (185 - 131) * _PX2PT
        c.drawImage(LOGO_ICON_PFAD, icon_x, icon_y, width=icon_breite, height=icon_hoehe, mask="auto")

    # Tagline (sprachunabhängig - im Original bereits Englisch)
    tagline = "[ INTELLIGENT FOOD PACKAGING ]"
    tag_groesse, tag_tracking = 12.8, 1.4
    c.setFont("Poppins", tag_groesse)
    tag_breite = sum(c.stringWidth(ch, "Poppins", tag_groesse) + tag_tracking for ch in tagline) - tag_tracking
    tag_start_x = (618 + 1019) / 2 * _PX2PT - tag_breite / 2
    _, tag_y = _px(0, 228)
    _briefpapier_text_getrackt(c, tagline, tag_start_x, tag_y, "Poppins", tag_groesse, DUNKEL, tag_tracking)

    # Adresszeile unter dem Logo (18.10.2026, Björns Korrektur: diese Zeile sitzt an der
    # Stelle, an der später die Kundenadresse im Fensterumschlag erscheint - darf deshalb
    # höchstens bis zur Papierhälfte reichen, nicht darüber hinaus. Statt einer fest
    # kalibrierten Schriftgröße (die bei der englischen Variante mit ", Germany" sowie durch
    # die Schriftersatz-Breite von Poppins bereits über die Hälfte hinausragte) wird die
    # Größe hier aus der tatsächlichen Textbreite berechnet - bleibt automatisch korrekt,
    # auch wenn sich Adresse oder Übersetzung später mal ändern.
    if sprache == "en":
        adresszeile = "ECKO-PACK GMBH · Wasbeker Straße 324 · D-24537 Neumünster, Germany"
    else:
        adresszeile = "ECKO-PACK GMBH · Wasbeker Straße 324 · D-24537 Neumünster"
    addr_x, addr_y = _px(198, 368)
    addr_max_breite = (SEITENBREITE / 2) - addr_x
    addr_basis_groesse = 10.3
    addr_breite = pdfmetrics.stringWidth(adresszeile, "Poppins", addr_basis_groesse)
    # 0.96 Sicherheitsabstand, damit die Zeile nicht exakt auf der Papierhälfte endet
    addr_groesse = addr_basis_groesse if addr_breite <= addr_max_breite else (
        addr_basis_groesse * addr_max_breite / addr_breite * 0.96
    )
    c.setFont("Poppins", addr_groesse)
    c.setFillColor(GRAU)
    c.drawString(addr_x, addr_y, adresszeile)

    # Fußzeile, drei Spalten (sprachabhängig)
    fuss_groesse, fuss_zeilenabstand = 6.9, 9.72
    spalten_x = [_px(309, 0)[0], _px(685, 0)[0], _px(1116, 0)[0]]
    _, fuss_start_y = _px(0, 2098 + 16)
    fusszeile = _BRIEFPAPIER_FUSSZEILE_EN if sprache == "en" else _BRIEFPAPIER_FUSSZEILE_DE
    for spalte_x, zeilen in zip(spalten_x, fusszeile):
        y = fuss_start_y
        for text, fett in zeilen:
            c.setFont("Poppins-Medium" if fett else "Poppins", fuss_groesse)
            c.setFillColor(GRAU)
            c.drawString(spalte_x, y, text)
            y -= fuss_zeilenabstand

    c.restoreState()


def _kopf_erste_seite(empfaenger_zeilen, meta_zeilen, titel, sprache="de"):
    def zeichnen(canvas_obj, doc):
        _hintergrund_zeichnen(canvas_obj, doc, sprache)
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


def _kopf_folgeseite(titel, nummer, sprache="de"):
    def zeichnen(canvas_obj, doc):
        _hintergrund_zeichnen(canvas_obj, doc, sprache)
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.setFillColor(GRAU)
        fortsetzung = "continued" if sprache == "en" else "Fortsetzung"
        canvas_obj.drawString(RAND_LINKS, HEADER_START_Y + 30, f"{titel} {nummer} – {fortsetzung}")
        canvas_obj.restoreState()
    return zeichnen


def _kopf_folgeseite_artikelliste(titel, nummer, sprache, empfaenger_name):
    """Wie _kopf_folgeseite (Fortsetzungszeile auf Seite 2+), aber zusätzlich mit dem
    Empfängernamen (erste Zeile von empfaenger_zeilen) rechtsbündig in der gleichen Zeile -
    nur für die Artikelliste (21.10.2026, Bjoerns Nachtrag: "warum ist die adresse nicht
    auf allen erzeugten seiten zu sehen?"). Grund: die Artikelliste kann über mehrere
    Seiten laufen und Seiten könnten getrennt werden, dann fehlt sonst jeder Hinweis, für
    wen Seite 2 gedacht ist. Bewusst NICHT in der geteilten _kopf_folgeseite ergänzt,
    damit Angebot/Lieferschein/Rechnung (die dieselbe Funktion verwenden) unverändert
    bleiben. empfaenger_name: None/leer lässt die rechte Seite frei (z.B. interne Vorschau
    ohne Empfänger)."""
    def zeichnen(canvas_obj, doc):
        _hintergrund_zeichnen(canvas_obj, doc, sprache)
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica", 9)
        canvas_obj.setFillColor(GRAU)
        fortsetzung = "continued" if sprache == "en" else "Fortsetzung"
        canvas_obj.drawString(RAND_LINKS, HEADER_START_Y + 30, f"{titel} {nummer} – {fortsetzung}")
        if empfaenger_name:
            canvas_obj.drawRightString(SEITENBREITE - RAND_RECHTS, HEADER_START_Y + 30, empfaenger_name)
        canvas_obj.restoreState()
    return zeichnen


def _positionstabelle(spalten, zeilen, artikelnummer_spalte=1):
    """spalten: Liste von (Kopfzeile, Breite, Ausrichtung ('l'|'r')).
    zeilen: Liste von Zeilen, jede Zeile eine Liste von Werten passend zu spalten.

    artikelnummer_spalte (21.10.2026, siehe _artikelnummer_umbrechen): Index der
    Artikel-Nr.-Spalte - bei allen vier Aufrufern (Angebot/Lieferschein/Rechnung/
    Packschein) konsistent Spalte 1 (0 = Pos.). Diese eine Spalte bricht bei Bedarf
    gezielt an vorhandenen Bindestrichen um statt reportlabs Standardumbruch mitten im
    Zeichen; None deaktiviert das (z.B. falls eine Tabelle mal keine Artikelnummer zeigt)."""
    kopf = []
    for label, _, ausrichtung in spalten:
        stil = STIL_TEXT_RECHTS if ausrichtung == "r" else STIL_TEXT
        kopf.append(Paragraph(f"<b>{label}</b>", stil))

    breiten = [b for _, b, _ in spalten]
    artikelnummer_breite = None
    if artikelnummer_spalte is not None and artikelnummer_spalte < len(breiten):
        artikelnummer_breite = breiten[artikelnummer_spalte] - 6  # LEFTPADDING+RIGHTPADDING unten

    daten = [kopf]
    for zeile in zeilen:
        formatiert = []
        for i, (wert, (_, _, ausrichtung)) in enumerate(zip(zeile, spalten)):
            stil = STIL_TEXT_RECHTS if ausrichtung == "r" else STIL_TEXT
            if i == artikelnummer_spalte and artikelnummer_breite is not None:
                text = _artikelnummer_umbrechen(wert, artikelnummer_breite, stil.fontName, stil.fontSize)
            else:
                text = str(wert)
            formatiert.append(Paragraph(text, stil))
        daten.append(formatiert)

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


# Ex-Works-Klausel (21.10.2026, auf Wunsch von Björn: "Bitte erstelle alle Preislisten und
# Angebote, die wir verschicken, so, dass da im Fußtext steht, Preise gelten Ex-Works, also
# ab Lager, zuzüglich Verpackung und Fracht. Das muss da bitte unterstehen.") - erscheint
# auf Angebot (angebot_pdf_erzeugen) und Artikel-/Preisliste (artikelliste_pdf_erzeugen) als
# eigene Zeile unterhalb des jeweils schon vorhandenen Fußhinweises. Bewusst NICHT auf
# Lieferschein (zeigt ohnehin keine Preise) oder Rechnung (dort wären die tatsächlich
# vereinbarten Lieferbedingungen maßgeblich, nicht diese allgemeine Standardklausel) -
# siehe Rückfrage an Björn dazu.
_FUSSHINWEIS_EXWORKS_DE = "Alle Preise verstehen sich Ex-Works (ab Lager), zuzüglich Verpackung und Fracht."
_FUSSHINWEIS_EXWORKS_EN = "All prices are Ex Works (ex warehouse), plus packaging and freight."


def _dokument_pdf_bytes(*, titel, nummer, empfaenger_zeilen, meta_zeilen, spalten, zeilen,
                         summenzeilen=None, notizen_titel=None, notizen_text=None, fusshinweis=None,
                         sprache="de"):
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
        onFirstPage=_kopf_erste_seite(empfaenger_zeilen, meta_zeilen, titel, sprache),
        onLaterPages=_kopf_folgeseite(titel, nummer, sprache),
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
        ("Pos.", 32, "l"), ("Artikel-Nr.", 75, "l"), ("Bezeichnung", 174.5, "l"), ("Menge", 70, "r"),
        ("Einheit", 70, "r"), ("Gepackt", 46, "r"),
    ]
    zeilen = []
    for p in packschein.positionen.all():
        # Unicode-Kästchen (☐/☑) werden von reportlabs Standard-Helvetica nicht
        # unterstützt (kaputtes Glyph im PDF) - daher ASCII-Darstellung.
        haken = "[X]" if p.gepackt else "[  ]"
        artikelnummer = p.artikel.artikelnummer if p.artikel_id else "–"
        zeilen.append([p.position, artikelnummer, p.bezeichnung, _menge(p.menge), p.get_einheit_display(), haken])

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


# Einheit-Anzeigetexte für das englische Angebots-PDF (18.10.2026) - EINHEIT_CHOICES in
# models.py ist fest Deutsch (get_einheit_display()), da dieselben Einheiten auch auf
# internen Dokumenten (Packschein) und in der CRM-Oberfläche selbst verwendet werden, die
# nicht übersetzt werden. Nur hier fürs Kunden-PDF übersetzt; fehlt ein Schlüssel (sollte
# bei den neun festen EINHEIT_CHOICES nicht vorkommen), wird die deutsche Anzeige genutzt.
_EINHEIT_LABEL_EN = {
    "stk": "pcs", "karton": "carton", "std": "hour", "tag": "day", "monat": "month",
    "pauschal": "flat rate", "kg": "kg", "m": "m", "m2": "m²",
}


def angebot_pdf_erzeugen(angebot):
    """sprache="en" (angebot.sprache, 18.10.2026): übersetzt nur Überschriften/Spalten-
    köpfe/Zahlenformat des PDFs - die Positions-Bezeichnung selbst kommt unverändert aus
    AngebotPosition.bezeichnung (beim Anlegen ggf. aus Artikel.bezeichnung_en vorbefüllt,
    siehe views.artikel_daten_json), die Kalkulation (Preis/Menge/Summe) ist in jeder
    Sprache exakt dieselbe."""
    sprache = angebot.sprache
    deal = angebot.deal
    firma = deal.firma
    empfaenger_zeilen = _empfaenger_zeilen(firma, deal.kontakt, sprache)
    if sprache == "en":
        titel = "QUOTATION"
        meta_zeilen = [
            ("Quotation No.", angebot.nummer),
            ("Date", _datum(angebot.datum, sprache)),
            ("Valid until", _datum(angebot.gueltig_bis, sprache)),
        ]
        spalten = [
            ("No.", 32, "l"), ("Art. No.", 65, "l"), ("Description", 122.5, "l"), ("Qty", 55, "r"),
            ("Unit", 55, "r"), ("Unit Price", 70, "r"), ("Total", 68, "r"),
        ]
        summen_label = "Total (net, plus applicable VAT)"
        notizen_titel = "Terms" if angebot.notizen else None
    else:
        titel = "ANGEBOT"
        meta_zeilen = [
            ("Angebotsnummer", angebot.nummer),
            ("Datum", _datum(angebot.datum)),
            ("Gültig bis", _datum(angebot.gueltig_bis)),
        ]
        spalten = [
            ("Pos.", 32, "l"), ("Artikel-Nr.", 65, "l"), ("Bezeichnung", 122.5, "l"), ("Menge", 55, "r"),
            ("Einheit", 55, "r"), ("Einzelpreis", 70, "r"), ("Gesamt", 68, "r"),
        ]
        summen_label = "Gesamtsumme (netto, zzgl. gesetzl. USt.)"
        notizen_titel = "Konditionen" if angebot.notizen else None

    fusshinweis = _FUSSHINWEIS_EXWORKS_EN if sprache == "en" else _FUSSHINWEIS_EXWORKS_DE

    zeilen = []
    for p in angebot.positionen.all():
        einheit_text = _EINHEIT_LABEL_EN.get(p.einheit, p.get_einheit_display()) if sprache == "en" else p.get_einheit_display()
        artikelnummer = p.artikel.artikelnummer if p.artikel_id else "–"
        zeilen.append([p.position, artikelnummer, p.bezeichnung, _menge(p.menge, sprache), einheit_text,
                        _eur_praezise(p.einzelpreis, sprache), _eur(p.gesamtpreis, sprache)])
    summenzeilen = [(summen_label, _eur(angebot.gesamtsumme, sprache))]
    return _dokument_pdf_bytes(
        titel=titel, nummer=angebot.nummer, empfaenger_zeilen=empfaenger_zeilen,
        meta_zeilen=meta_zeilen, spalten=spalten, zeilen=zeilen, summenzeilen=summenzeilen,
        notizen_titel=notizen_titel, notizen_text=angebot.notizen,
        fusshinweis=fusshinweis, sprache=sprache,
    )


def lieferschein_pdf_erzeugen(lieferschein):
    """sprache=lieferschein.sprache (18.10.2026, wie Angebot.sprache): übersetzt Briefpapier,
    Überschriften/Spaltenköpfe, Zahlen-/Datumsformat und den Fußhinweis. Die Vorbefüllung des
    Felds beim Anlegen (aus dem verknüpften Angebot/Packschein) sorgt dafür, dass ein Deal in
    der Regel durchgängig in einer Sprache läuft (siehe views.lieferschein_erstellen) - hier
    wird aber bewusst immer lieferschein.sprache selbst gelesen, nicht nochmal das Angebot,
    falls jemand die Sprache am Lieferschein bewusst abweichend gesetzt hat."""
    sprache = lieferschein.sprache
    deal = lieferschein.deal
    firma = deal.firma
    empfaenger_zeilen = _empfaenger_zeilen(firma, deal.kontakt, sprache)
    if sprache == "en":
        titel = "DELIVERY NOTE"
        meta_zeilen = [
            ("Delivery Note No.", lieferschein.nummer),
            ("Delivery Date", _datum(lieferschein.datum, sprache)),
            ("Ref. Quotation", lieferschein.angebot.nummer if lieferschein.angebot_id else "–"),
        ]
        spalten = [
            ("No.", 36, "l"), ("Art. No.", 80, "l"), ("Description", 201.5, "l"), ("Qty", 75, "r"), ("Unit", 75, "r"),
        ]
        notizen_titel = "Notes" if lieferschein.notizen else None
        fusshinweis = "The items listed above have been delivered."
    else:
        titel = "LIEFERSCHEIN"
        meta_zeilen = [
            ("Lieferscheinnummer", lieferschein.nummer),
            ("Lieferdatum", _datum(lieferschein.datum)),
            ("Bezug Angebot", lieferschein.angebot.nummer if lieferschein.angebot_id else "–"),
        ]
        spalten = [
            ("Pos.", 36, "l"), ("Artikel-Nr.", 80, "l"), ("Bezeichnung", 201.5, "l"), ("Menge", 75, "r"), ("Einheit", 75, "r"),
        ]
        notizen_titel = "Hinweise" if lieferschein.notizen else None
        fusshinweis = "Die oben genannten Positionen wurden geliefert."

    zeilen = []
    for p in lieferschein.positionen.all():
        einheit_text = _EINHEIT_LABEL_EN.get(p.einheit, p.get_einheit_display()) if sprache == "en" else p.get_einheit_display()
        artikelnummer = p.artikel.artikelnummer if p.artikel_id else "–"
        zeilen.append([p.position, artikelnummer, p.bezeichnung, _menge(p.menge, sprache), einheit_text])

    return _dokument_pdf_bytes(
        titel=titel, nummer=lieferschein.nummer, empfaenger_zeilen=empfaenger_zeilen,
        meta_zeilen=meta_zeilen, spalten=spalten, zeilen=zeilen,
        notizen_titel=notizen_titel, notizen_text=lieferschein.notizen,
        fusshinweis=fusshinweis, sprache=sprache,
    )


def rechnung_pdf_erzeugen(rechnung):
    """sprache=rechnung.sprache (18.10.2026, wie Angebot/Lieferschein) - siehe Kommentar bei
    lieferschein_pdf_erzeugen, gilt hier analog.

    storno_zu (24.10.2026, auf Wunsch von Björn, Stornorechnung-/Rechnungskorrektur-Feature):
    ist rechnung.storno_zu_id gesetzt, handelt es sich um eine Korrektur zu einer anderen
    Rechnung - Titel, Meta-Zeile (Bezug auf das Original) und Zahlungshinweistext weichen dann
    vom Normalfall ab. Bewusst NICHT "GUTSCHRIFT"/"CREDIT NOTE" als Titel verwenden - siehe
    RechnungKorrekturForm-Kommentar zur Terminologie (§14 UStG "Gutschrift" meint rechtlich
    eine vom Kaeufer ausgestellte Abrechnung, nicht diese vom Verkaeufer ausgestellte
    Korrektur)."""
    sprache = rechnung.sprache
    deal = rechnung.deal
    firma = deal.firma
    empfaenger_zeilen = _empfaenger_zeilen(firma, deal.kontakt, sprache)
    ist_korrektur = bool(rechnung.storno_zu_id)
    erstattung = ist_korrektur and rechnung.bruttosumme < 0
    if sprache == "en":
        titel = "INVOICE CORRECTION" if ist_korrektur else "INVOICE"
        meta_zeilen = [
            ("Invoice No.", rechnung.nummer),
            ("Invoice Date", _datum(rechnung.rechnungsdatum, sprache)),
            ("Delivery Date", _datum(rechnung.leistungsdatum or rechnung.rechnungsdatum, sprache)),
        ]
        if ist_korrektur:
            meta_zeilen.append((
                "Correction to Invoice",
                f"{rechnung.storno_zu.nummer} ({_datum(rechnung.storno_zu.rechnungsdatum, sprache)})",
            ))
        else:
            meta_zeilen += [
                ("Payment Terms", f"{rechnung.zahlungsziel_tage} days net"),
                ("Due Date", _datum(rechnung.faelligkeitsdatum, sprache)),
            ]
        spalten = [
            ("No.", 30, "l"), ("Art. No.", 55, "l"), ("Description", 112.5, "l"), ("Qty", 45, "r"), ("Unit", 45, "r"),
            ("Unit Price", 60, "r"), ("VAT", 40, "r"), ("Total (net)", 80, "r"),
        ]
        netto_label = "Net total"
        brutto_label = "Amount to be refunded" if erstattung else "Total (gross)"
        zuschlag_label = "plus VAT {satz} on {netto}"
        notizen_titel = "Payment Terms"
        if not ist_korrektur:
            zahlungstext = (
                f"Please transfer the invoice amount by {_datum(rechnung.faelligkeitsdatum, sprache)} "
                f"without deduction to the account below."
            )
        elif erstattung:
            zahlungstext = (
                f"This document corrects invoice {rechnung.storno_zu.nummer}. The amount shown "
                f"will be refunded to you; no payment is required on your part."
            )
        else:
            zahlungstext = (
                f"This document corrects invoice {rechnung.storno_zu.nummer}. Please transfer the "
                f"amount shown above without deduction to the account below."
            )
    else:
        titel = "RECHNUNGSKORREKTUR" if ist_korrektur else "RECHNUNG"
        meta_zeilen = [
            ("Rechnungsnummer", rechnung.nummer),
            ("Rechnungsdatum", _datum(rechnung.rechnungsdatum)),
            ("Leistungsdatum", _datum(rechnung.leistungsdatum or rechnung.rechnungsdatum)),
        ]
        if ist_korrektur:
            meta_zeilen.append((
                "Korrektur zu Rechnung",
                f"{rechnung.storno_zu.nummer} ({_datum(rechnung.storno_zu.rechnungsdatum)})",
            ))
        else:
            meta_zeilen += [
                ("Zahlungsziel", f"{rechnung.zahlungsziel_tage} Tage netto"),
                ("Fällig am", _datum(rechnung.faelligkeitsdatum)),
            ]
        spalten = [
            ("Pos.", 30, "l"), ("Artikel-Nr.", 55, "l"), ("Bezeichnung", 112.5, "l"), ("Menge", 45, "r"), ("Einheit", 45, "r"),
            ("Einzelpreis", 60, "r"), ("USt.", 40, "r"), ("Gesamt (netto)", 80, "r"),
        ]
        netto_label = "Nettosumme"
        brutto_label = "Erstattungsbetrag" if erstattung else "Gesamtbetrag (brutto)"
        zuschlag_label = "zzgl. USt {satz} auf {netto}"
        notizen_titel = "Zahlungshinweis"
        if not ist_korrektur:
            zahlungstext = (
                f"Bitte überweisen Sie den Rechnungsbetrag bis zum {_datum(rechnung.faelligkeitsdatum)} "
                f"ohne Abzug auf unten genanntes Konto."
            )
        elif erstattung:
            zahlungstext = (
                f"Dieses Dokument korrigiert Rechnung {rechnung.storno_zu.nummer}. Der ausgewiesene "
                f"Betrag wird Ihnen erstattet, eine Zahlung ist Ihrerseits nicht erforderlich."
            )
        else:
            zahlungstext = (
                f"Dieses Dokument korrigiert Rechnung {rechnung.storno_zu.nummer}. Bitte überweisen "
                f"Sie den oben genannten Betrag ohne Abzug auf unten genanntes Konto."
            )

    zeilen = []
    for p in rechnung.positionen.all():
        einheit_text = _EINHEIT_LABEL_EN.get(p.einheit, p.get_einheit_display()) if sprache == "en" else p.get_einheit_display()
        artikelnummer = p.artikel.artikelnummer if p.artikel_id else "–"
        zeilen.append([
            p.position, artikelnummer, p.bezeichnung, _menge(p.menge, sprache), einheit_text,
            _eur_praezise(p.einzelpreis, sprache), _satz_text(p.steuersatz, sprache), _eur(p.nettobetrag, sprache),
        ])

    summenzeilen = [(netto_label, _eur(rechnung.nettosumme, sprache))]
    for satz, netto, steuer in rechnung.steuer_aufschluesselung:
        label = zuschlag_label.format(satz=_satz_text(satz, sprache), netto=_eur(netto, sprache))
        summenzeilen.append((label, _eur(steuer, sprache)))
    summenzeilen.append((brutto_label, _eur(rechnung.bruttosumme, sprache)))

    notizen_text = zahlungstext
    if rechnung.notizen:
        notizen_text = f"{zahlungstext}\n{rechnung.notizen}"

    return _dokument_pdf_bytes(
        titel=titel, nummer=rechnung.nummer, empfaenger_zeilen=empfaenger_zeilen,
        meta_zeilen=meta_zeilen, spalten=spalten, zeilen=zeilen, summenzeilen=summenzeilen,
        notizen_titel=notizen_titel, notizen_text=notizen_text, sprache=sprache,
    )


# ---------------------------------------------------------------------------
# Artikel-/Preisliste (21.10.2026, auf Wunsch von Björn: "eine funktion ... in dem ich
# unsere artikelliste samt preisstaffel mit eckopack briefpapier erzeugen und versenden
# kann" - zweisprachig, auf dem normalen Kunden-Briefpapier wie Angebot/Lieferschein/
# Rechnung, aber KEIN Bezug zu einem einzelnen Deal/einer Firma (anders als die anderen
# Dokumente hier) - wird global über alle Großhandels-Artikel erzeugt und per freier
# E-Mail-Eingabe versendet (siehe views.artikelliste_versenden). pdf.py bleibt bewusst
# frei von Model-Importen (siehe übrige Funktionen oben) - der Aufrufer liefert bereits
# die gefilterte/sortierte Artikel-Liste (vertriebskanal="standard", siehe Artikel-Model-
# Doku zu den Amazon-Zweitlistungen) als Parameter.
# ---------------------------------------------------------------------------

STIL_ARTIKEL_NR = ParagraphStyle("ArtikelNr", parent=STIL_TEXT, fontSize=8.5, leading=11)
STIL_ARTIKEL_BEZEICHNUNG = ParagraphStyle(
    "ArtikelBezeichnung", parent=STIL_TEXT, fontName="Helvetica-Bold", fontSize=9.5,
)
STIL_ARTIKEL_HINWEIS = ParagraphStyle(
    "ArtikelHinweis", parent=STIL_TEXT, fontSize=8.5, textColor=GRAU,
)

# Spaltenbreiten der Artikelliste-Tabelle, muessen INHALT_BREITE (467.5pt) ergeben -
# siehe Modul-Kommentar zu den uebrigen Dokumenten. Fuenfte Spalte "1.000er Stückpreis"
# (21.10.2026, auf Wunsch von Björn) ergaenzt neben dem Preis je Einheit - in der
# Verpackungsbranche die uebliche zweite Preisangabe fuer Mengenkalkulationen.
_ARTIKELLISTE_SPALTENBREITEN = [90, 125, 85, 85, 82.5]
_ARTIKELLISTE_GRUPPE_TRENNLINIE = colors.HexColor("#cfd2d1")
_ARTIKELLISTE_ZEBRA = colors.HexColor("#f6f8f8")
_ARTIKELLISTE_SUBZEILE_LINIE = colors.HexColor("#eeeeee")


def _artikelliste_tabelle(label_ab_menge, label_preis, label_preis_1000, gruppen):
    """Eine EINZIGE durchlaufende Tabelle (statt eines separaten Mini-Blocks je Artikel) -
    21.10.2026, auf Wunsch von Björn: "mehr tabellarisch, aber gut lesbar". Artikelnummer/
    Bezeichnung werden je Artikel über alle seine Preisstaffel-Zeilen hinweg vertikal
    verbunden (SPAN) statt wiederholt - so liest sich die Liste wie eine echte Preistabelle
    (Excel-artig gruppiert), nicht wie eine Kette einzelner kleiner Tabellen. repeatRows=1
    sorgt zugleich dafür, dass die Spaltenköpfe bei einer längeren Liste auf jeder
    Folgeseite automatisch wiederkehren (vorher gab es dort nur "Fortsetzung" ohne Köpfe).
    Ein dezenter Zebra-Hintergrund je ZWEITEM Artikel (nicht je Zeile) macht die
    Artikel-Gruppen zusätzlich zur SPAN-Klammer auf einen Blick unterscheidbar, ohne bei
    Artikeln mit mehreren Preisstaffel-Zeilen unruhig zu wirken."""
    kopf = [
        Paragraph(f"<b>{label}</b>", STIL_TEXT_RECHTS if ausrichtung == "r" else STIL_TEXT)
        for label, ausrichtung in (
            ("Artikel-Nr." if label_ab_menge == "Ab Menge" else "Art. No.", "l"),
            ("Bezeichnung" if label_ab_menge == "Ab Menge" else "Description", "l"),
            (label_ab_menge, "l"),
            (label_preis, "r"),
            (label_preis_1000, "r"),
        )
    ]
    daten = [kopf]
    stil = [
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, MINT),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]

    zeile = 1
    for gruppen_index, (artikelnummer, bezeichnung, unterzeilen) in enumerate(gruppen):
        start = zeile
        # Artikel-Nr. bricht gezielt an Bindestrichen um (siehe _artikelnummer_umbrechen),
        # Breite abzgl. Standard-Zellpadding (hier keine LEFTPADDING/RIGHTPADDING-Overrides
        # in `stil` oben, also reportlabs Default 6+6pt).
        artikelnummer_text = _artikelnummer_umbrechen(
            artikelnummer, _ARTIKELLISTE_SPALTENBREITEN[0] - 12, STIL_ARTIKEL_NR.fontName, STIL_ARTIKEL_NR.fontSize,
        )
        for menge_text, preis_text, preis_1000_text in unterzeilen:
            daten.append([
                Paragraph(artikelnummer_text, STIL_ARTIKEL_NR),
                Paragraph(bezeichnung, STIL_ARTIKEL_BEZEICHNUNG),
                Paragraph(menge_text, STIL_TEXT),
                Paragraph(preis_text, STIL_TEXT_RECHTS),
                Paragraph(preis_1000_text, STIL_TEXT_RECHTS),
            ])
            zeile += 1
        ende = zeile - 1

        if ende > start:
            stil.append(("SPAN", (0, start), (0, ende)))
            stil.append(("SPAN", (1, start), (1, ende)))
            for r in range(start, ende):
                stil.append(("LINEBELOW", (2, r), (4, r), 0.3, _ARTIKELLISTE_SUBZEILE_LINIE))
        if gruppen_index > 0:
            stil.append(("LINEABOVE", (0, start), (-1, start), 0.6, _ARTIKELLISTE_GRUPPE_TRENNLINIE))
        if gruppen_index % 2 == 1:
            stil.append(("BACKGROUND", (0, start), (-1, ende), _ARTIKELLISTE_ZEBRA))

        zeile = ende + 1

    tabelle = Table(daten, colWidths=_ARTIKELLISTE_SPALTENBREITEN, repeatRows=1)
    tabelle.setStyle(TableStyle(stil))
    return tabelle


def artikelliste_pdf_erzeugen(artikel_liste, sprache="de", empfaenger_zeilen=None, aufschlag_prozent=None):
    """Erzeugt die zweisprachige Artikel-/Preisliste als EINE durchlaufende Tabelle
    (Artikelnummer/Bezeichnung je Artikel über seine Preisstaffel-Zeilen hinweg vertikal
    verbunden, siehe _artikelliste_tabelle) - aufsteigend nach Ab-Menge sortiert, bewusst
    umgekehrt zur Preisstaffel.Meta.ordering (absteigend), die fürs interne
    preis_fuer_menge()-Lookup praktisch ist, für einen Kunden beim Lesen aber unnatürlich
    wäre. Artikel ganz ohne Preisstaffel zeigen stattdessen den Flatrate-Verkaufspreis;
    fehlt auch der (verkaufspreis=None, z.B. unvollständig gepflegter Artikel), wird das
    ausdrücklich als "Preis auf Anfrage"/"Price on request" ausgewiesen statt eine falsche
    Zahl zu erfinden oder die Zeile stillschweigend wegzulassen.

    empfaenger_zeilen (21.10.2026, auf Wunsch von Björn: "ich möchte aber auch die adresse
    auf der preisliste eingeben können"): optionale Liste von Textzeilen fürs
    Anschriftenfeld oben links (gleiche Position/Optik wie bei Angebot/Lieferschein/
    Rechnung, siehe _kopf_erste_seite) - anders als dort aber KEIN Firma/Kontakt-Objekt,
    sondern freier Text, weil die Preisliste (anders als die übrigen Dokumente) keinen
    Deal-/Firmenbezug hat (siehe Modul-Kommentar oben). Leer/None lässt das Feld frei,
    z.B. für eine reine interne Vorschau ohne Empfänger.

    aufschlag_prozent (21.10.2026, auf Wunsch von Björn: Preisliste mit Agenten-Provision
    "ich muss in der Lage sein, die Preisliste so rauszugeben, dass ich ... 5% Provision
    aufschlage"): optionaler Decimal/Zahl, z.B. Decimal("5") für +5% auf JEDEN gezeigten
    Preis (Preis je Stück UND den daraus abgeleiteten 1.000er-Stückpreis, sowohl bei
    Preisstaffeln als auch beim Flatrate-Verkaufspreis). None oder 0 lässt die Preise
    unverändert - das PDF sieht dann exakt wie die normale Preisliste aus, es gibt bewusst
    KEINEN Hinweis auf dem Dokument, dass ein Aufschlag enthalten ist (die Liste soll 1:1
    an den Agenten bzw. dessen Kunden weitergereicht werden können). "Preis auf Anfrage"-
    Zeilen (kein verkaufspreis gepflegt) bleiben unverändert, da dort keine Zahl existiert,
    auf die ein Aufschlag angewendet werden könnte."""
    aufschlag_faktor = None
    if aufschlag_prozent:
        aufschlag_faktor = (Decimal("100") + Decimal(aufschlag_prozent)) / Decimal("100")

    def _mit_aufschlag(preis):
        return preis * aufschlag_faktor if aufschlag_faktor is not None else preis
    heute = timezone.localdate()
    if sprache == "en":
        titel = "PRICE LIST"
        meta_zeilen = [("As of", _datum(heute, sprache))]
        label_ab_menge, label_preis = "From qty.", "Price per piece (net)"
        label_preis_1000 = "Price per 1,000 pcs (net)"
        preis_auf_anfrage = "on request"
        fusshinweis = (
            "All prices are net in EUR, plus statutory VAT. Subject to errors and price "
            "changes. Please contact us for current availability and shipping costs."
            f"<br/>{_FUSSHINWEIS_EXWORKS_EN}"
        )
        keine_artikel = "No articles available."
    else:
        titel = "ARTIKEL- UND PREISLISTE"
        meta_zeilen = [("Stand", _datum(heute))]
        label_ab_menge, label_preis = "Ab Menge", "Preis je Stück (netto)"
        label_preis_1000 = "1.000er Stückpreis (netto)"
        preis_auf_anfrage = "auf Anfrage"
        fusshinweis = (
            "Alle Preise netto in EUR, zzgl. der gesetzlichen Umsatzsteuer. Irrtümer und "
            "Preisänderungen vorbehalten. Aktuelle Verfügbarkeit und Versandkosten bitte "
            "bei uns erfragen."
            f"<br/>{_FUSSHINWEIS_EXWORKS_DE}"
        )
        keine_artikel = "Keine Artikel vorhanden."

    gruppen = []
    for artikel in artikel_liste:
        bezeichnung = artikel.bezeichnung
        if sprache == "en" and artikel.bezeichnung_en:
            bezeichnung = artikel.bezeichnung_en
        einheit_text = _EINHEIT_LABEL_EN.get(artikel.einheit, artikel.get_einheit_display()) if sprache == "en" else artikel.get_einheit_display()

        staffeln = list(artikel.preisstaffeln.order_by("ab_menge"))
        if staffeln:
            unterzeilen = [
                (
                    f"{_menge(s.ab_menge, sprache)} {einheit_text}",
                    _eur_praezise(_mit_aufschlag(s.preis_netto), sprache),
                    _eur(_mit_aufschlag(s.preis_netto) * 1000, sprache),
                )
                for s in staffeln
            ]
        elif artikel.verkaufspreis is not None:
            preis_mit_aufschlag = _mit_aufschlag(artikel.verkaufspreis)
            unterzeilen = [(
                "–", _eur_praezise(preis_mit_aufschlag, sprache), _eur(preis_mit_aufschlag * 1000, sprache),
            )]
        else:
            unterzeilen = [("–", preis_auf_anfrage, "–")]
        gruppen.append((artikel.artikelnummer, bezeichnung, unterzeilen))

    story = []
    if gruppen:
        story.append(_artikelliste_tabelle(label_ab_menge, label_preis, label_preis_1000, gruppen))
    else:
        story.append(Paragraph(keine_artikel, STIL_TEXT))

    story.append(Spacer(1, 16))
    story.append(Paragraph(fusshinweis, STIL_NOTIZEN))

    empfaenger_name = (empfaenger_zeilen or [None])[0]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
        leftMargin=RAND_LINKS, rightMargin=RAND_RECHTS,
    )
    doc.build(
        story,
        onFirstPage=_kopf_erste_seite(empfaenger_zeilen or [], meta_zeilen, titel, sprache),
        onLaterPages=_kopf_folgeseite_artikelliste(titel, _datum(heute, sprache), sprache, empfaenger_name),
    )
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Rahmenvertrag-PDF (22.10.2026, auf Wunsch von Björn: "ich will auch, dass das Angebot
# bzw. Rahmenvertrag in einen ordentlichen Rahmen eingebracht wird mit Paragraphen ...
# damit wir einen professionellen Eindruck bei so großen Kunden machen.") - anders als
# die übrigen Dokumente oben KEIN reiner Daten-/Preisausdruck, sondern ein echtes
# Vertragswerk mit §-Klauseln (siehe vertragstexte.py). WICHTIG, siehe Modul-Kommentar
# in vertragstexte.py: die Klauseln sind ein technischer ENTWURF, keine anwaltlich
# geprüfte Vorlage - deshalb der deutlich sichtbare Entwurfs-Hinweis (Banner) ganz oben
# auf Seite 1, der nicht kommentarlos entfernt werden darf.
# ---------------------------------------------------------------------------

_ENTWURFSHINWEIS_HINTERGRUND = colors.HexColor("#fff3cd")
_ENTWURFSHINWEIS_RAND = colors.HexColor("#ffe69c")
_ENTWURFSHINWEIS_TEXTFARBE = colors.HexColor("#664d03")

STIL_ENTWURFSHINWEIS = ParagraphStyle(
    "Entwurfshinweis", fontName="Helvetica-Bold", fontSize=9, leading=12.5,
    textColor=_ENTWURFSHINWEIS_TEXTFARBE,
)
STIL_VERTRAGSTEXT = ParagraphStyle("Vertragstext", parent=STIL_TEXT, spaceAfter=4)
STIL_PARAGRAPH_UEBERSCHRIFT = ParagraphStyle(
    "ParagraphUeberschrift", fontName="Helvetica-Bold", fontSize=10.5, leading=14,
    textColor=DUNKEL, spaceBefore=10, spaceAfter=3,
)


def _unterschriftenzeile_vertrag(name_links, name_rechts, sprache="de"):
    """Unterschriftenblock für zwei benannte Vertragsparteien (Lieferant/Kunde) - anders
    als die generische, Packschein-spezifische _unterschriftenzeile() oben (feste Labels
    "Kommissioniert von"/"Kontrolliert von"), zeigt dieser Block den jeweiligen Firmennamen
    fett über der Unterschriftenlinie, mit Platz dazwischen für die tatsächliche
    Unterschrift."""
    stil_name = ParagraphStyle("UnterschriftName", parent=STIL_TEXT, fontName="Helvetica-Bold")
    fuer = "For" if sprache == "en" else "Für"
    label = "Place, Date, Signature" if sprache == "en" else "Ort, Datum, Unterschrift"
    daten = [
        [Paragraph(f"{fuer} {name_links}", stil_name), Paragraph(f"{fuer} {name_rechts}", stil_name)],
        ["", ""],
        [Paragraph(label, STIL_TEXT), Paragraph(label, STIL_TEXT)],
    ]
    tabelle = Table(daten, colWidths=[INHALT_BREITE / 2, INHALT_BREITE / 2], rowHeights=[16, 40, 16])
    tabelle.setStyle(TableStyle([
        ("LINEABOVE", (0, 2), (0, 2), 0.6, GRAU),
        ("LINEABOVE", (1, 2), (1, 2), 0.6, GRAU),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (1, 0), (1, 0), 0),
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
    ]))
    return tabelle


def rahmenvertrag_pdf_erzeugen(rahmenvereinbarung):
    """Erzeugt das Rahmenvertrags-PDF: Entwurfs-Banner, Präambel, §1-§11 (Standard-
    klauseln aus vertragstexte.paragraphen(), inhaltlich auf Björns vier Entscheidungen
    vom 22.10.2026 festgelegt: unverbindliche Zielmenge, keine Exklusivität, 1 Jahr
    Laufzeit mit automatischer Verlängerung/3 Monate Kündigungsfrist), die Jahresmengen-/
    Preistabelle (eingefügt nach §3), die Bonusstaffel-Tabelle (eingefügt nach §4), optional
    "Besondere Vereinbarungen" aus rahmenvereinbarung.notizen, und ein Unterschriftenblock
    für Lieferant und Kunde.

    WICHTIG: trägt oben auf Seite 1 einen deutlich sichtbaren "ENTWURF – NICHT
    RECHTSGEPRÜFT"-Hinweis (vertragstexte.ENTWURFSHINWEIS_DE/_EN). Dieser Hinweis darf
    nicht entfernt werden, ohne dass tatsächlich eine anwaltliche Prüfung stattgefunden
    hat - siehe Modul-Kommentar in vertragstexte.py."""
    sprache = rahmenvereinbarung.sprache
    deal = rahmenvereinbarung.deal
    firma = deal.firma
    kunde_name = firma.name
    empfaenger_zeilen = _empfaenger_zeilen(firma, deal.kontakt, sprache)

    gueltig_bis_text = _datum(rahmenvereinbarung.gueltig_bis, sprache) if rahmenvereinbarung.gueltig_bis else None

    if sprache == "en":
        titel = "FRAMEWORK SUPPLY AGREEMENT"
        meta_zeilen = [
            ("Agreement No.", rahmenvereinbarung.nummer),
            ("Valid from", _datum(rahmenvereinbarung.gueltig_ab, sprache)),
            ("Valid until", gueltig_bis_text or "open-ended (auto-renewal)"),
        ]
        spalten = [
            ("No.", 32, "l"), ("Art. No.", 65, "l"), ("Description", 125.5, "l"), ("Annual Qty.", 80, "r"),
            ("Unit", 55, "r"), ("Frozen Price", 110, "r"),
        ]
        bonus_spalten = [("From cumulative qty.", 300, "l"), ("Bonus", 167.5, "r")]
        positionen_titel = "§3 Annual Quantities and Prices – Detail"
        bonus_titel = "§4 Bonus Tiers – Detail"
        besondere_titel = "Special Agreements"
        keine_positionen = "No positions on file."
        keine_bonusstaffel = "No bonus tiers on file."
    else:
        titel = "RAHMENVERTRAG"
        meta_zeilen = [
            ("Vertragsnummer", rahmenvereinbarung.nummer),
            ("Gültig ab", _datum(rahmenvereinbarung.gueltig_ab)),
            ("Gültig bis", gueltig_bis_text or "unbefristet (automat. Verlängerung)"),
        ]
        spalten = [
            ("Pos.", 32, "l"), ("Artikel-Nr.", 65, "l"), ("Bezeichnung", 125.5, "l"), ("Jahresmenge", 80, "r"),
            ("Einheit", 55, "r"), ("Eingefrorener Preis", 110, "r"),
        ]
        bonus_spalten = [("Ab Gesamtmenge", 300, "l"), ("Bonus", 167.5, "r")]
        positionen_titel = "§3 Jahresmengen und Preise – Detail"
        bonus_titel = "§4 Bonusstaffel – Detail"
        besondere_titel = "Besondere Vereinbarungen"
        keine_positionen = "Keine Positionen hinterlegt."
        keine_bonusstaffel = "Keine Bonusstaffel hinterlegt."

    entwurfshinweis_text = vertragstexte.ENTWURFSHINWEIS_EN if sprache == "en" else vertragstexte.ENTWURFSHINWEIS_DE
    banner = Table([[Paragraph(entwurfshinweis_text, STIL_ENTWURFSHINWEIS)]], colWidths=[INHALT_BREITE])
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _ENTWURFSHINWEIS_HINTERGRUND),
        ("BOX", (0, 0), (-1, -1), 0.75, _ENTWURFSHINWEIS_RAND),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))

    positionen_zeilen = []
    for p in rahmenvereinbarung.positionen.all():
        einheit_text = _EINHEIT_LABEL_EN.get(p.einheit, p.get_einheit_display()) if sprache == "en" else p.get_einheit_display()
        artikelnummer = p.artikel.artikelnummer if p.artikel_id else "–"
        positionen_zeilen.append([
            p.position, artikelnummer, p.bezeichnung, _menge(p.jahresmenge, sprache), einheit_text,
            _eur_praezise(p.einzelpreis, sprache),
        ])

    bonus_zeilen = [
        [_menge(b.ab_menge, sprache), _satz_text(b.bonus_prozent, sprache)]
        for b in rahmenvereinbarung.bonusstaffeln.order_by("ab_menge")
    ]

    paragraphen_liste = vertragstexte.paragraphen(
        kunde_name=kunde_name,
        gueltig_ab=_datum(rahmenvereinbarung.gueltig_ab, sprache),
        gueltig_bis=gueltig_bis_text,
        zahlungsziel_tage=7,
        sprache=sprache,
    )

    story = [
        banner, Spacer(1, 14),
        Paragraph(vertragstexte.praeambel(kunde_name, sprache), STIL_VERTRAGSTEXT),
        Spacer(1, 8),
    ]

    for index, (ueberschrift, text) in enumerate(paragraphen_liste):
        story.append(Paragraph(f"<b>{ueberschrift}</b>", STIL_PARAGRAPH_UEBERSCHRIFT))
        story.append(Paragraph(text, STIL_VERTRAGSTEXT))
        if index == 2:  # direkt nach §3 (Preise): Jahresmengen-/Preistabelle je Artikel
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"<b>{positionen_titel}</b>", STIL_PARAGRAPH_UEBERSCHRIFT))
            if positionen_zeilen:
                story.append(_positionstabelle(spalten, positionen_zeilen))
            else:
                story.append(Paragraph(keine_positionen, STIL_VERTRAGSTEXT))
            story.append(Spacer(1, 4))
        elif index == 3:  # direkt nach §4 (Bonusstaffel): die konkreten Stufen
            story.append(Spacer(1, 4))
            story.append(Paragraph(f"<b>{bonus_titel}</b>", STIL_PARAGRAPH_UEBERSCHRIFT))
            if bonus_zeilen:
                story.append(_positionstabelle(bonus_spalten, bonus_zeilen, artikelnummer_spalte=None))
            else:
                story.append(Paragraph(keine_bonusstaffel, STIL_VERTRAGSTEXT))
            story.append(Spacer(1, 4))

    if rahmenvereinbarung.notizen:
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"<b>{besondere_titel}</b>", STIL_PARAGRAPH_UEBERSCHRIFT))
        for absatz in str(rahmenvereinbarung.notizen).split("\n"):
            if absatz.strip():
                story.append(Paragraph(absatz, STIL_VERTRAGSTEXT))

    story.append(Spacer(1, 36))
    story.append(_unterschriftenzeile_vertrag(vertragstexte.LIEFERANT_NAME, kunde_name, sprache))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
        leftMargin=RAND_LINKS, rightMargin=RAND_RECHTS,
    )
    doc.build(
        story,
        onFirstPage=_kopf_erste_seite(empfaenger_zeilen, meta_zeilen, titel, sprache),
        onLaterPages=_kopf_folgeseite(titel, rahmenvereinbarung.nummer, sprache),
    )
    return buffer.getvalue()
