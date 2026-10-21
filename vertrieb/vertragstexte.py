"""Vertragstext-Bausteine für den Rahmenvertrag (pdf.rahmenvertrag_pdf_erzeugen).

WICHTIG (22.10.2026, Björns Anfrage nach einem "ordentlichen Vertragswerk mit
Paragraphen" für Rahmenvereinbarungen mit Großkunden): die hier hinterlegten
Klauseln sind ein TECHNISCHER ENTWURF, keine rechtlich geprüfte Vorlage. Claude
ist kein Anwalt und darf keine verbindlichen Vertragsinhalte erfinden - die
Formulierungen unten sind bewusst konservativ/üblich gehalten (Standard-
Haftungsbeschränkung, salvatorische Klausel, etc.), ersetzen aber ausdrücklich
KEINE anwaltliche Prüfung vor dem ersten Versand an einen Kunden. Das PDF trägt
deshalb oben auf Seite 1 einen deutlich sichtbaren Entwurfs-Hinweis (siehe
pdf.rahmenvertrag_pdf_erzeugen) - dieser Hinweis darf beim Versand an echte
Kunden nicht kommentarlos entfernt werden, ohne dass eine anwaltliche Prüfung
stattgefunden hat.

Geschäftliche Eckpunkte, auf Björns ausdrücklicher Entscheidung vom 22.10.2026
beruhend (siehe Konversation) - nicht von Claude erfunden:
- Die Jahresmenge je Position ist eine UNVERBINDLICHE Zielmenge (Grundlage für
  Preis und Bonusstaffel), KEINE verbindliche Abnahmeverpflichtung des Kunden.
  Es gibt daher keine Vertragsstrafe bei Nichterreichen.
- Keine Exklusivität/kein Gebietsschutz für den Kunden.
- Laufzeit: 12 Monate ab Gültig-ab-Datum, automatische Verlängerung um jeweils
  weitere 12 Monate, sofern nicht mit einer Frist von 3 Monaten zum Ende der
  jeweiligen Laufzeit gekündigt wird.
"""
from decimal import Decimal


LIEFERANT_NAME = "ECKO-PACK GmbH"
LIEFERANT_ANSCHRIFT_DE = "Wasbeker Straße 324, D-24537 Neumünster"
LIEFERANT_ANSCHRIFT_EN = "Wasbeker Straße 324, D-24537 Neumünster, Germany"

ENTWURFSHINWEIS_DE = (
    "ENTWURF – NICHT RECHTSGEPRÜFT. Diese Vorlage wurde automatisiert aus den im CRM "
    "hinterlegten Jahresmengen/Preisen/Bonusstaffeln erzeugt. Sie ersetzt keine anwaltliche "
    "Prüfung und darf in dieser Form nicht ohne vorherige rechtliche Prüfung final an einen "
    "Kunden versendet werden."
)
ENTWURFSHINWEIS_EN = (
    "DRAFT – NOT LEGALLY REVIEWED. This document was generated automatically from the annual "
    "quantities/prices/bonus tiers stored in the CRM. It does not replace legal review and "
    "must not be sent to a customer in final form without prior legal review."
)


def _format_menge(menge, sprache):
    menge = Decimal(menge)
    if menge == menge.to_integral_value():
        text = f"{int(menge):,}"
    else:
        text = f"{menge:,.2f}"
    if sprache != "en":
        text = text.replace(",", "X").replace(".", ",").replace("X", ".")
    return text


def praeambel(kunde_name, sprache="de"):
    if sprache == "en":
        return (
            f"This Framework Supply Agreement (“Agreement”) is entered into between "
            f"{LIEFERANT_NAME}, {LIEFERANT_ANSCHRIFT_EN} (“Supplier”) and {kunde_name} "
            f"(“Customer”). It sets out the annual quantity targets, frozen prices and "
            f"bonus tiers agreed between the parties for the articles listed below."
        )
    return (
        f"Dieser Rahmenvertrag (“Vertrag”) wird geschlossen zwischen der {LIEFERANT_NAME}, "
        f"{LIEFERANT_ANSCHRIFT_DE} (“Lieferant”) und {kunde_name} (“Kunde”). Er "
        f"regelt die zwischen den Parteien vereinbarten Jahresmengen-Zielwerte, die dafür "
        f"eingefrorenen Preise sowie die Bonusstaffel für die nachfolgend aufgeführten Artikel."
    )


def paragraphen(*, kunde_name, gueltig_ab, gueltig_bis, zahlungsziel_tage=7, sprache="de"):
    """Gibt eine Liste von (Überschrift, Text)-Tupeln zurück. gueltig_ab/gueltig_bis sind
    bereits als Anzeige-Strings übergeben (siehe pdf._datum), damit dieses Modul keine
    eigene Datumsformatierung pflegen muss."""
    laufzeit_bis_hinweis_de = (
        f" Die Vereinbarung ist bis zum {gueltig_bis} befristet." if gueltig_bis else
        " Es ist zunächst keine feste Befristung über die automatische Verlängerung hinaus hinterlegt."
    )
    laufzeit_bis_hinweis_en = (
        f" The agreement is limited until {gueltig_bis}." if gueltig_bis else
        " No fixed end date beyond the automatic renewal is currently on file."
    )

    if sprache == "en":
        return [
            ("§1 Parties and Subject Matter", (
                f"The Supplier and the Customer agree on annual quantity targets and frozen "
                f"unit prices for the articles listed in §3, for deliveries called off by the "
                f"Customer in partial shipments over the term of this Agreement."
            )),
            ("§2 Annual Quantities (Non-Binding Targets)", (
                "The annual quantities stated for each article in §3 are non-binding target "
                "volumes that form the basis for the agreed unit price and the bonus tiers in "
                "§4. They do not constitute a binding minimum purchase obligation of the "
                "Customer. The Customer is not obliged to call off the full annual quantity, "
                "and no penalty or additional charge applies if the actual call-off volume "
                "remains below the stated target. Call-offs exceeding the target quantity are "
                "accepted at the Supplier's discretion and continue to be invoiced at the same "
                "frozen unit price."
            )),
            ("§3 Prices", (
                "For the term of this Agreement, the Supplier grants the Customer the unit "
                "prices listed in the table below, irrespective of the quantity of any "
                "individual partial delivery. All prices are net prices Ex Works (ex "
                "warehouse), plus statutory VAT, packaging and freight."
            )),
            ("§4 Bonus Tiers", (
                "In addition to the prices in §3, the Customer receives a percentage rebate on "
                "the cumulative turnover actually called off under this Agreement, in "
                "accordance with the bonus tiers listed in the table below. The rebate is "
                "calculated on the total call-off volume across all articles under this "
                "Agreement and is settled between the parties by mutual agreement (e.g. by "
                "credit note or offsetting against future invoices)."
            )),
            ("§5 Call-Offs and Delivery", (
                "Individual call-offs are placed by the Customer and confirmed by the Supplier "
                "by way of a delivery note referencing this Agreement. Delivery terms are Ex "
                "Works (ex warehouse) unless otherwise agreed in writing for an individual "
                "call-off. Delivery dates are agreed between the parties on a case-by-case "
                "basis."
            )),
            ("§6 Payment Terms", (
                f"Unless otherwise agreed for an individual invoice, payment is due net within "
                f"{zahlungsziel_tage} days of the invoice date. Invoices are issued per "
                f"delivery note/call-off."
            )),
            ("§7 Term and Termination", (
                f"This Agreement enters into force on {gueltig_ab} and runs for an initial "
                f"term of twelve (12) months. It is automatically renewed for further periods "
                f"of twelve (12) months each unless terminated in writing by either party with "
                f"three (3) months' notice to the end of the then-current term."
                + laufzeit_bis_hinweis_en
            )),
            ("§8 Warranty and Liability", (
                "Statutory warranty provisions apply. The Supplier's liability for damages, "
                "irrespective of the legal grounds, is limited to intent and gross negligence. "
                "In cases of slight negligence, the Supplier is liable only for breach of a "
                "material contractual obligation (cardinal obligation), and in that case "
                "limited to the foreseeable damage typical for this type of contract. The "
                "foregoing limitations do not apply to liability under mandatory product "
                "liability law or for injury to life, body or health."
            )),
            ("§9 Confidentiality", (
                "Both parties shall treat the commercial terms of this Agreement, in "
                "particular the prices and bonus tiers, as confidential and shall not disclose "
                "them to third parties without the other party's prior written consent, unless "
                "required by law."
            )),
            ("§10 No Exclusivity", (
                "This Agreement does not grant the Customer any exclusivity or territorial "
                "protection. Both parties remain free to enter into comparable agreements with "
                "third parties."
            )),
            ("§11 Final Provisions", (
                "Amendments and supplements to this Agreement require written form; this also "
                "applies to any waiver of this written-form requirement. This Agreement is "
                "governed by the laws of the Federal Republic of Germany, excluding the UN "
                "Convention on Contracts for the International Sale of Goods (CISG). The place "
                "of jurisdiction is, to the extent legally permissible, the registered seat of "
                "the Supplier. Should any provision of this Agreement be or become invalid, the "
                "validity of the remaining provisions shall remain unaffected."
            )),
        ]

    return [
        ("§1 Vertragsparteien und Vertragsgegenstand", (
            f"Lieferant und Kunde vereinbaren Jahresmengen-Zielwerte sowie eingefrorene "
            f"Einzelpreise für die in §3 genannten Artikel, die der Kunde über die Laufzeit "
            f"dieses Vertrages in Teillieferungen abrufen kann."
        )),
        ("§2 Jahresmengen (unverbindliche Zielwerte)", (
            "Die in §3 je Artikel genannten Jahresmengen sind unverbindliche Zielmengen, die "
            "dem vereinbarten Einzelpreis und der Bonusstaffel in §4 zugrunde liegen. Sie "
            "begründen keine verbindliche Mindestabnahmeverpflichtung des Kunden. Der Kunde "
            "ist nicht verpflichtet, die volle Jahresmenge abzurufen; bei Unterschreitung "
            "entstehen keine Vertragsstrafe und keine Nachbelastung. Abrufe über die "
            "Zielmenge hinaus werden nach freiem Ermessen des Lieferanten angenommen und "
            "weiterhin zum selben eingefrorenen Einzelpreis abgerechnet."
        )),
        ("§3 Preise", (
            "Für die Laufzeit dieses Vertrages gewährt der Lieferant dem Kunden die in der "
            "nachfolgenden Tabelle genannten Einzelpreise, unabhängig von der Menge der "
            "jeweiligen einzelnen Teillieferung. Alle Preise verstehen sich netto, Ex-Works "
            "(ab Lager), zuzüglich gesetzlicher Umsatzsteuer, Verpackung und Fracht."
        )),
        ("§4 Bonusstaffel", (
            "Zusätzlich zu den Preisen aus §3 erhält der Kunde eine prozentuale "
            "Rückvergütung auf den im Rahmen dieses Vertrages kumulierten tatsächlich "
            "abgerufenen Umsatz gemäß der nachfolgenden Bonusstaffel. Die Staffel bezieht "
            "sich auf die Gesamtmenge über alle Artikel dieses Vertrages hinweg und wird "
            "zwischen den Parteien einvernehmlich verrechnet (z. B. per Gutschrift oder "
            "Anrechnung auf künftige Rechnungen)."
        )),
        ("§5 Abruf und Lieferung", (
            "Einzelabrufe erfolgen durch den Kunden und werden vom Lieferanten jeweils über "
            "einen Lieferschein mit Bezug auf diesen Vertrag bestätigt. Die Lieferbedingungen "
            "sind Ex-Works (ab Lager), sofern für einen einzelnen Abruf nicht schriftlich "
            "etwas anderes vereinbart wird. Liefertermine werden zwischen den Parteien im "
            "Einzelfall abgestimmt."
        )),
        ("§6 Zahlungsbedingungen", (
            f"Sofern für eine einzelne Rechnung nichts anderes vereinbart wird, ist der "
            f"Rechnungsbetrag innerhalb von {zahlungsziel_tage} Tagen netto nach "
            f"Rechnungsdatum fällig. Die Rechnungsstellung erfolgt je Lieferschein/Abruf."
        )),
        ("§7 Vertragslaufzeit und Kündigung", (
            f"Dieser Vertrag tritt am {gueltig_ab} in Kraft und wird zunächst für eine "
            f"Laufzeit von zwölf (12) Monaten geschlossen. Er verlängert sich automatisch um "
            f"jeweils weitere zwölf (12) Monate, sofern er nicht von einer der Parteien mit "
            f"einer Frist von drei (3) Monaten zum Ende der jeweiligen Laufzeit schriftlich "
            f"gekündigt wird." + laufzeit_bis_hinweis_de
        )),
        ("§8 Gewährleistung und Haftung", (
            "Es gelten die gesetzlichen Gewährleistungsregelungen. Die Haftung des "
            "Lieferanten für Schadensersatz ist, gleich aus welchem Rechtsgrund, auf Vorsatz "
            "und grobe Fahrlässigkeit beschränkt. Bei einfacher Fahrlässigkeit haftet der "
            "Lieferant nur bei Verletzung einer wesentlichen Vertragspflicht "
            "(Kardinalpflicht), und in diesem Fall begrenzt auf den vorhersehbaren, "
            "vertragstypischen Schaden. Die vorstehenden Haftungsbeschränkungen gelten nicht "
            "für die zwingende Haftung nach dem Produkthaftungsgesetz sowie für Schäden aus "
            "der Verletzung des Lebens, des Körpers oder der Gesundheit."
        )),
        ("§9 Geheimhaltung", (
            "Beide Parteien behandeln die kaufmännischen Konditionen dieses Vertrages, "
            "insbesondere Preise und Bonusstaffel, vertraulich und geben sie ohne vorherige "
            "schriftliche Zustimmung der anderen Partei nicht an Dritte weiter, soweit keine "
            "gesetzliche Pflicht zur Offenlegung besteht."
        )),
        ("§10 Keine Exklusivität", (
            "Dieser Vertrag begründet keine Exklusivität und keinen Gebietsschutz zugunsten "
            "des Kunden. Beide Parteien bleiben frei, mit Dritten vergleichbare "
            "Vereinbarungen zu schließen."
        )),
        ("§11 Schlussbestimmungen", (
            "Änderungen und Ergänzungen dieses Vertrages bedürfen der Schriftform; dies gilt "
            "auch für einen Verzicht auf dieses Schriftformerfordernis. Es gilt das Recht der "
            "Bundesrepublik Deutschland unter Ausschluss des UN-Kaufrechts (CISG). "
            "Gerichtsstand ist, soweit gesetzlich zulässig, der Sitz des Lieferanten. Sollten "
            "einzelne Bestimmungen dieses Vertrages unwirksam sein oder werden, bleibt die "
            "Wirksamkeit der übrigen Bestimmungen davon unberührt."
        )),
    ]
