"""Nachfass-Automatik für Musterversand-Leads + Versand-Bestätigungsmail für echte Bestellungen.

Teil 1 (bestehend): Button 'Musterkarton anfordern' (views.musterkarton_anfordern) legt einen
Packschein mit ist_musterversand=True an. Sobald der im Lager auf 'versendet'
gesetzt wird (views.packschein_versand_bestaetigen), läuft hier:

1. Bestätigungsmail an den Lead (best effort – ein fehlender/kaputter E-Mail-Versand
   darf den Packvorgang nicht blockieren, deshalb try/except statt hartem Fehler).
2. Anlage der ersten wöchentlichen Nachfass-Aktivität (+7 Tage), die anschließend vom
   management command 'nachfass_pruefen' (wöchentlicher Cron, siehe render.yaml)
   verlängert wird, solange der Deal noch nicht tatsächlich versendet hat (siehe Teil 2).

Teil 2 (neu, 17.10.2026, auf Wunsch von Björn): Sobald ein echter Lieferschein (nicht nur
der Musterversand-Packschein) über views.lieferschein_versand_bestaetigen mit Trackingnummer
versehen wird, verschickt lieferschein_versand_abgeschlossen() eine eigene, als HTML gestaltete
Versand-Bestätigungsmail an den Kunden, der Lieferschein selbst wird dabei als PDF angehängt
(dieselbe Erzeugung wie beim Download-Button im CRM, siehe pdf.lieferschein_pdf_erzeugen).
Anders als bei Teil 1 wird hier KEINE neue Nachfass-Aktivität angelegt - der echte Versand ist
stattdessen das Ende der Nachfass-Kette (siehe nachfass_pruefen.py: eine bestehende Kette wird
nicht mehr verlängert, sobald irgendein Lieferschein des Deals eine Trackingnummer hat).

Teil 3 (18.10.2026, auf Wunsch von Björn, NOCHMAL GEÄNDERT am selben Tag): Die ursprüngliche
Teil-3-Version verschickte bei jeder Verlängerung der (für ALLE offenen Deals laufenden)
Nachfass-Kette eine einzige, immer gleiche Kundenmail (models.NachfassKundenmailVorlage,
inzwischen entfernt). Björn wollte das stattdessen nur für Musterversand-Leads und als
erzählerisch aufgebaute 8-Wochen-Reihe: musterbox_nachfass_senden() verschickt pro Woche
(1-8) einen eigenen Text aus models.MusterboxNachfassVorlage, gesteuert über
models.MusterboxNachfassStatus (ein Status-Datensatz pro Deal, angelegt in
musterversand_abgeschlossen() unten). Die Kette endet, sobald der Deal die Phase
lead/qualifiziert verlässt (Angebot o.ä. = Reaktion da) oder nach Woche 8 ohne Reaktion -
siehe management/commands/nachfass_pruefen.py für die genaue Ablaufsteuerung. Deals OHNE
Musterversand-Historie bekommen seitdem gar keine automatische Kundenmail mehr.

Teil 4 (18.10.2026, auf Wunsch von Björn): Bei der Musterkarton-Anforderung (views.
musterkarton_anfordern) wird die dort gewählte Sprache (de/en) jetzt auf Packschein.sprache
gespeichert und bei Versand auf MusterboxNachfassStatus.sprache übernommen - für die gesamte
Dauer der 8-Wochen-Kette fest. ALLE Musterbox-bezogenen Kundenmails (die sofortige
Versandbestätigung unten UND die 8 Wochen-Nachfassmails) werden entsprechend in der
jeweiligen Sprache verschickt, inkl. {{ artikel }}-Platzhalter. Die unabhängige
Lieferschein-Versandbestätigung (Teil 2, für echte Bestellungen) ist davon NICHT betroffen -
bleibt bewusst deutsch, bis Björn das separat beauftragt.

Teil 5 (20.10.2026, auf Wunsch von Björn): Die Musterversand-Bestätigungsmail aus Teil 1 war
seit ihrer ursprünglichen Einführung reiner Text (send_mail ohne HTML) - anders als die
HTML-gestaltete Lieferschein-Versandbestätigung aus Teil 2, die erst später (PR #7/#8)
dazukam. Björn ist aufgefallen, dass ausgerechnet die allererste Mail an einen neuen Lead
(der Musterkarton-Versand) ohne Logo/Branding ankommt. musterversand_abgeschlossen() nutzt
jetzt wie Teil 2 EmailMultiAlternatives mit einem eigenen HTML/Text-Template-Paar
(email/musterversand_bestaetigung.html/.txt) inkl. Logo-Header und "Sendung verfolgen"-Button
(dafür neu: Packschein.tracking_url, analog zu Lieferschein.tracking_url). Weiterhin KEIN
PDF-Anhang (Packschein hat kein Briefpapier/keine PDF-Erzeugung, siehe Packschein-Docstring
in models.py) und weiterhin zweisprachig wie seit Teil 4.

Teil 6 (20.10.2026, auf Wunsch von Björn): Die in Teil 4 bewusst ausgeklammerte
Lieferschein-Versandbestätigung (Teil 2) ignorierte lieferschein.sprache tatsächlich
komplett und verschickte IMMER Deutsch - aufgefallen bei einem englischsprachigen
Testversand (Lieferschein-PDF selbst korrekt Englisch, Mail drumherum aber Deutsch).
lieferschein_versand_abgeschlossen() ist jetzt wie musterversand_abgeschlossen()
zweisprachig (Betreff + Templates). Separat davon, bei derselben Gelegenheit entdeckt:
views.musterkarton_anfordern setzte die Bezeichnung der Musterkarton-Position IMMER aus
Artikel.bezeichnung (Deutsch) statt sprachabhaengig aus bezeichnung_en - anders als beim
Beileger (eigener Artikel pro Sprache, daher dort unbemerkt), siehe Fix dort.

Teil 7 (20.10.2026, auf Wunsch von Björn): Bei derselben Gelegenheit aufgefallen - zu einem
versendeten Lieferschein (egal ob Musterversand oder echte Bestellung) wurde nie
automatisch eine Rechnung erzeugt oder verschickt, nur ueber den manuellen Button
"Rechnung erstellen" (views.rechnung_erstellen), und selbst eine manuell erstellte Rechnung
wurde vom CRM nie per Mail verschickt (nur PDF-Download). Neu:

1. rechnung_automatisch_erstellen(lieferschein) wird von views.lieferschein_versand_
   bestaetigen direkt nach der Versand-Bestaetigungsmail aufgerufen (fuer Muster UND echte
   Bestellungen gleichermassen - beide landen hier) und legt eine Rechnung mit den
   Lieferschein-Positionen an. Preisermittlung bewusst vorsichtig: pro Position wird der
   Preis NUR gesetzt, wenn die Position einen Artikel verknuepft hat (Artikel.
   preis_fuer_menge(), inkl. Mengenstaffel, plus Artikel.ust_satz) - LieferscheinPosition
   traegt selbst keinen Preis (reines Lieferdokument), und beim Anlegen eines Lieferscheins
   aus einem Packschein (views.lieferschein_erstellen) wird die Artikel-Verknuepfung aus der
   Positions-Vorbefuellung aktuell NICHT uebernommen - ist sie bei einer Position nicht
   gesetzt, bleibt der Preis unbekannt.
2. rechnung_versand_senden(rechnung) verschickt die (HTML-gestaltete, zweisprachige)
   Rechnungs-Mail mit PDF-Anhang analog zu lieferschein_versand_abgeschlossen() und setzt
   bei Erfolg rechnung.status auf 'versendet' (damit greift automatisch die bestehende
   GoBD-Sperre, siehe Rechnung.ist_bearbeitbar).
3. rechnung_automatisch_erstellen() + views.lieferschein_versand_bestaetigen verschicken die
   Rechnung automatisch NUR, wenn ALLE Positionen einen Preis haben - sonst bleibt die
   Rechnung als Entwurf liegen (Preise manuell nachtragen), und der Nutzer sieht im UI genau,
   welche Positionen betroffen sind. Der manuelle "Jetzt versenden"-Button auf der
   Rechnungs-Detailseite (views.rechnung_versand_senden_view) ruft danach denselben
   rechnung_versand_senden() auf - KEIN Freitext-/Preis-Risiko: lieber eine Rechnung zu viel
   im Entwurf liegen lassen als automatisch eine mit 0,00 EUR oder falschem Steuersatz an
   einen Kunden verschicken.

Teil 8 (20.10.2026, auf Wunsch von Björn: "alle emailaktivitaeten sehen koennen, um einen
ueberblick zu haben, und um auch manuell einzugreifen"): JEDER Mailversand (die drei
bestehenden aus Teil 1/2/3 oben sowie die neue Rechnungs-Mail aus Teil 7) protokolliert sich
jetzt zusaetzlich als models.EmailVersand-Datensatz - erfolgreich oder fehlgeschlagen,
inkl. Fehlermeldung. Siehe views.EmailVersandListView fuer die Uebersichtsseite im CRM
sowie den Email-Verlauf-Abschnitt auf der Deal-Detailseite. Protokollierung ist selbst
best effort (siehe _mail_protokollieren) - ein Fehler beim Schreiben des Protokolls darf
niemals den eigentlichen Mailversand zum Scheitern bringen.
"""

import logging
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import Context, Template
from django.template.loader import render_to_string
from django.utils import timezone

from . import pdf
from .models import (
    Aktivitaet, Artikel, EmailVersand, MUSTERKARTON_ARTIKEL, MusterboxNachfassStatus,
    MusterboxNachfassVorlage, Rechnung, RechnungPosition,
)

logger = logging.getLogger(__name__)


def _mail_protokollieren(*, deal, mailtyp, empfaenger, betreff, erfolg, fehlermeldung="",
                          packschein=None, lieferschein=None, rechnung=None):
    """Legt einen EmailVersand-Protokolleintrag an - siehe Teil 8 oben. Best effort: ein
    Fehler HIER (z.B. DB kurz nicht erreichbar) darf den bereits erfolgten/versuchten
    Mailversand nicht nachtraeglich als Fehlschlag erscheinen lassen, deshalb eigenes
    try/except statt den Aufrufer platzen zu lassen."""
    try:
        EmailVersand.objects.create(
            deal=deal, mailtyp=mailtyp, empfaenger=empfaenger or "", betreff=betreff or "",
            erfolg=erfolg, fehlermeldung=fehlermeldung or "",
            packschein=packschein, lieferschein=lieferschein, rechnung=rechnung,
        )
    except Exception:
        logger.exception(
            "E-Mail-Versand konnte nicht protokolliert werden (Mailtyp %s, Deal %s)",
            mailtyp, deal.pk if deal else None,
        )

# Versanddienstleister-Anzeigetext fuer die englische Versandbestaetigung - die Choices in
# models.VERSANDDIENSTLEISTER_CHOICES sind deutsch beschriftet (zwei davon tatsaechlich
# uebersetzungsbeduerftig, der Rest sind Markennamen und bleiben gleich).
_VERSANDDIENSTLEISTER_TEXT_EN = {
    "post": "Deutsche Post",
    "abholung": "Pickup",
    "sonstiges": "Other carrier",
}

NACHFASS_INTERVALL_TAGE = 7
MUSTERBOX_NACHFASS_INTERVALL_TAGE = 7

# Hardcoded wie beim NACHFASS-Cron in render.yaml - fuer absolute Links (Logo, Tracking) in
# E-Mails, die ausserhalb eines Request-Kontexts (also ohne request.build_absolute_uri)
# zusammengebaut werden.
SITE_URL = "https://eckopack-crm.onrender.com"


def _empfaenger_email(deal):
    """Bevorzugt den im Deal hinterlegten Ansprechpartner, sonst den Hauptansprechpartner
    der Firma, sonst die allgemeine Firmen-E-Mail. Gibt None zurück, wenn nichts davon
    eine E-Mail-Adresse hat."""
    if deal.kontakt and deal.kontakt.email:
        return deal.kontakt.email
    hauptkontakt = deal.firma.kontakte.filter(ist_hauptansprechpartner=True).first()
    if hauptkontakt and hauptkontakt.email:
        return hauptkontakt.email
    if deal.firma.email:
        return deal.firma.email
    return None


def musterversand_abgeschlossen(packschein):
    deal = packschein.deal
    empfaenger = _empfaenger_email(deal)
    sprache = packschein.sprache

    if empfaenger:
        # Bis 20.10.2026 verschickte diese Mail reinen Text ohne Logo/Header - anders als
        # die HTML-gestaltete Versandbestaetigung fuer echte Bestellungen weiter unten
        # (lieferschein_versand_abgeschlossen). Björn ist das beim Musterversand an einen
        # Lead aufgefallen (gerade DER erste Eindruck zaehlt da). Jetzt auf dasselbe
        # EmailMultiAlternatives-Muster umgestellt, inkl. "Sendung verfolgen"-Button
        # (Packschein.tracking_url, neu). Dabei auch der Mailtext leicht neu strukturiert:
        # Trackingdaten stehen jetzt wie bei der Lieferschein-Mail in einer eigenen Zeile
        # statt im Fliesstext eingebettet - lesbarer, konsistent mit der anderen Mail.
        if sprache == "en":
            betreff = "Your sample box is on its way – ECKO-PACK"
            versanddienstleister_anzeige = (
                _VERSANDDIENSTLEISTER_TEXT_EN.get(packschein.versanddienstleister)
                or packschein.get_versanddienstleister_display()
            )
        else:
            betreff = "Ihr Musterkarton ist unterwegs – ECKO-PACK"
            versanddienstleister_anzeige = packschein.get_versanddienstleister_display()

        kontext = {
            "packschein": packschein,
            "deal": deal,
            "firma": deal.firma,
            "ansprechpartner": deal.kontakt,
            "sprache": sprache,
            "versanddienstleister_anzeige": versanddienstleister_anzeige,
            "site_url": SITE_URL,
            "logo_url": f"{SITE_URL}/static/img/eckopack-logo.png",
        }
        text_body = render_to_string("vertrieb/email/musterversand_bestaetigung.txt", kontext)
        html_body = render_to_string("vertrieb/email/musterversand_bestaetigung.html", kontext)

        try:
            mail = EmailMultiAlternatives(betreff, text_body, settings.DEFAULT_FROM_EMAIL, [empfaenger])
            mail.attach_alternative(html_body, "text/html")
            mail.send(fail_silently=False)
        except Exception as exc:
            logger.exception(
                "Musterversand-Bestaetigungsmail konnte nicht gesendet werden (Packschein %s)",
                packschein.nummer,
            )
            _mail_protokollieren(
                deal=deal, mailtyp="musterversand_bestaetigung", empfaenger=empfaenger, betreff=betreff,
                erfolg=False, fehlermeldung=str(exc), packschein=packschein,
            )
        else:
            packschein.bestaetigungsmail_gesendet_am = timezone.now()
            packschein.save(update_fields=["bestaetigungsmail_gesendet_am"])
            _mail_protokollieren(
                deal=deal, mailtyp="musterversand_bestaetigung", empfaenger=empfaenger, betreff=betreff,
                erfolg=True, packschein=packschein,
            )
    else:
        logger.warning(
            "Kein Empfaenger (E-Mail) fuer Musterversand-Bestaetigungsmail gefunden (Packschein %s, Deal %s)",
            packschein.nummer, deal.pk,
        )
        _mail_protokollieren(
            deal=deal, mailtyp="musterversand_bestaetigung", empfaenger="", betreff="",
            erfolg=False, fehlermeldung="keine E-Mail-Adresse für Firma/Ansprechpartner hinterlegt",
            packschein=packschein,
        )

    Aktivitaet.objects.create(
        typ="nachfass",
        betreff=f"Nachfass Musterversand: {deal.firma.name}",
        beschreibung=(
            f"Musterkarton wurde am {packschein.versendet_am or timezone.now().date()} versendet "
            f"(Packschein {packschein.nummer}). Bitte nach einer Woche nachfassen. Wird automatisch "
            f"wöchentlich verlängert, bis der Deal verloren ist oder die eigentliche Bestellung "
            f"tatsächlich versendet wurde (Lieferschein mit Trackingnummer)."
        ),
        datum=timezone.now() + timedelta(days=NACHFASS_INTERVALL_TAGE),
        firma=deal.firma,
        kontakt=deal.kontakt,
        deal=deal,
        zustaendiger=deal.zustaendiger,
    )

    # 8-wöchige Musterbox-Nachfasskette an den KUNDEN (siehe Teil 3 oben) - eigener,
    # von der internen Aktivitaet oben unabhängiger Status pro Deal. get_or_create, falls
    # musterversand_abgeschlossen() fuer denselben Deal ausnahmsweise ein zweites Mal
    # laufen sollte (z.B. zweiter Musterversand-Packschein) - die laufende Kette wird dann
    # NICHT neu gestartet/verlaengert.
    MusterboxNachfassStatus.objects.get_or_create(
        deal=deal,
        defaults={
            "sprache": sprache,
            "naechste_woche": 1,
            "naechster_versand_am": timezone.now() + timedelta(days=MUSTERBOX_NACHFASS_INTERVALL_TAGE),
        },
    )


def lieferschein_versand_abgeschlossen(lieferschein):
    """Verschickt die (HTML-gestaltete) Versand-Bestätigungsmail an den Kunden, sobald ein
    echter Lieferschein (views.lieferschein_versand_bestaetigen) eine Trackingnummer erhält.

    Der Lieferschein wird als PDF angehängt (gleiche Erzeugung wie der Download-Button im CRM).
    Schlägt die PDF-Erzeugung fehl, zählt das als Fehlschlag der gesamten Mail - eine
    Versandbestätigung ohne den eigentlichen Lieferschein waere unvollstaendig.

    Gibt (erfolg: bool, fehlermeldung: str|None) zurück, damit der aufrufende View dem
    Nutzer sofort sichtbar machen kann, wenn der Versand zwar erfasst, die Mail aber NICHT
    rausgegangen ist (anders als bei musterversand_abgeschlossen() oben oder beim woechentlichen
    Nachfass-Cron wird hier bewusst NICHT fail-silent geloggt - das ist eine kundenseitige
    Benachrichtigung, Björn soll das direkt im UI sehen, nicht erst im Render-Log suchen).

    Sprache (20.10.2026, auf Wunsch von Björn): Diese Mail ignorierte lieferschein.sprache
    bisher komplett und ging IMMER deutsch raus, obwohl das Feld seit PR #14 existiert und
    der Lieferschein selbst (inkl. angehaengter PDF) laengst zweisprachig ist - Björn ist das
    bei einem englischsprachigen Testversand aufgefallen. Templates und Betreff sind jetzt
    nach demselben {% if sprache == "en" %}-Muster wie musterversand_bestaetigung.html/.txt
    zweisprachig."""
    deal = lieferschein.deal
    empfaenger = _empfaenger_email(deal)

    if not empfaenger:
        meldung = "keine E-Mail-Adresse für Firma/Ansprechpartner hinterlegt"
        logger.warning(
            "Kein Empfaenger (E-Mail) fuer Versand-Bestaetigungsmail gefunden (Lieferschein %s, Deal %s)",
            lieferschein.nummer, deal.pk,
        )
        _mail_protokollieren(
            deal=deal, mailtyp="lieferschein_bestaetigung", empfaenger="", betreff="",
            erfolg=False, fehlermeldung=meldung, lieferschein=lieferschein,
        )
        return False, meldung

    sprache = lieferschein.sprache
    if sprache == "en":
        betreff = f"Your order is on its way – ECKO-PACK ({lieferschein.nummer})"
        versanddienstleister_anzeige = (
            _VERSANDDIENSTLEISTER_TEXT_EN.get(lieferschein.versanddienstleister)
            or lieferschein.get_versanddienstleister_display()
        )
    else:
        betreff = f"Ihre Bestellung ist unterwegs – ECKO-PACK ({lieferschein.nummer})"
        versanddienstleister_anzeige = lieferschein.get_versanddienstleister_display()

    kontext = {
        "lieferschein": lieferschein,
        "deal": deal,
        "firma": deal.firma,
        "ansprechpartner": deal.kontakt,
        "sprache": sprache,
        "versanddienstleister_anzeige": versanddienstleister_anzeige,
        "site_url": SITE_URL,
        "logo_url": f"{SITE_URL}/static/img/eckopack-logo.png",
    }
    text_body = render_to_string("vertrieb/email/versand_bestaetigung.txt", kontext)
    html_body = render_to_string("vertrieb/email/versand_bestaetigung.html", kontext)

    try:
        lieferschein_pdf_bytes = pdf.lieferschein_pdf_erzeugen(lieferschein)
        mail = EmailMultiAlternatives(betreff, text_body, settings.DEFAULT_FROM_EMAIL, [empfaenger])
        mail.attach_alternative(html_body, "text/html")
        mail.attach(f"{lieferschein.nummer}.pdf", lieferschein_pdf_bytes, "application/pdf")
        mail.send(fail_silently=False)
    except Exception as exc:
        logger.exception(
            "Versand-Bestaetigungsmail (inkl. Lieferschein-PDF) konnte nicht gesendet werden (Lieferschein %s)",
            lieferschein.nummer,
        )
        _mail_protokollieren(
            deal=deal, mailtyp="lieferschein_bestaetigung", empfaenger=empfaenger, betreff=betreff,
            erfolg=False, fehlermeldung=str(exc), lieferschein=lieferschein,
        )
        return False, str(exc)

    lieferschein.bestaetigungsmail_gesendet_am = timezone.now()
    lieferschein.save(update_fields=["bestaetigungsmail_gesendet_am"])
    _mail_protokollieren(
        deal=deal, mailtyp="lieferschein_bestaetigung", empfaenger=empfaenger, betreff=betreff,
        erfolg=True, lieferschein=lieferschein,
    )
    return True, None


def _musterversand_artikel_text(deal, sprache="de"):
    """Leitet eine kurze, menschenlesbare Bezeichnung der beim Musterversand bestellten
    Artikelart ab (für den {{ artikel }}-Platzhalter der Musterbox-Nachfasskette) - aus den
    Positionen des (letzten) Musterversand-Packscheins des Deals.

    Korrektur (18.10.2026, im Zuge der Sprachumstellung entdeckt): filtert jetzt explizit auf
    musterkarton_einzelart (nur von views.musterkarton_anfordern auf der eigentlichen
    Musterkarton-Position gesetzt, NICHT auf dem Beileger/Flyer) statt wie vorher auf alle
    Positions-Bezeichnungen - vorher stand im Platzhalter faelschlich auch der Beileger-Text
    mit drin (z.B. "Besteck-Muster und Flyer Besteck DE" statt "Besteck").

    Fallback auf einen neutralen Text, falls sich nichts ableiten lässt (z.B. Packschein ohne
    Positionen, oder ein manuell ohne den Schnellaktions-Button angelegter Musterversand ohne
    gesetztes musterkarton_einzelart)."""
    neutral = {"de": "unsere Produkte", "en": "our products"}[sprache]
    packschein = deal.packscheine.filter(ist_musterversand=True).order_by("-datum", "-pk").first()
    if not packschein:
        return neutral
    einzelarten = []
    for einzelart in packschein.positionen.exclude(musterkarton_einzelart="").values_list(
        "musterkarton_einzelart", flat=True
    ):
        if einzelart not in einzelarten:
            einzelarten.append(einzelart)
    if not einzelarten:
        return neutral
    verbindungswort = {"de": " und ", "en": " and "}[sprache]
    return verbindungswort.join(MUSTERKARTON_ARTIKEL[einzelart]["text"][sprache] for einzelart in einzelarten)


def musterbox_nachfass_senden(deal, status):
    """Verschickt die Mail der aktuell fälligen Woche (status.naechste_woche) der
    8-wöchigen Musterbox-Nachfasskette an den Kunden (siehe MusterboxNachfassVorlage /
    MusterboxNachfassStatus in models.py sowie management/commands/nachfass_pruefen.py, das
    diese Funktion pro fälligem Status-Datensatz aufruft).

    Best effort, wie zuvor bei der generischen Kundenmail: ein Fehler hier (z.B. keine
    E-Mail-Adresse hinterlegt, kaputte Vorlage) wird nur geloggt und blockiert nicht den
    Fortschritt der Kette - der wöchentliche Cron läuft unbeaufsichtigt, niemand ist da, um
    eine UI-Fehlermeldung zu sehen. Das heißt auch: schlägt der Versand einer Woche fehl,
    rückt die Kette trotzdem auf die nächste Woche vor (siehe nachfass_pruefen.py) statt
    hängen zu bleiben - sonst würde ein einziger kaputter Platzhalter die komplette Kette
    für den betroffenen Deal dauerhaft blockieren.

    Gibt (erfolg: bool, fehlermeldung: str|None) zurück, damit der aufrufende Cron-Befehl
    zählen kann, wie viele Kundenmails pro Lauf tatsächlich rausgegangen sind."""
    empfaenger = _empfaenger_email(deal)

    if not empfaenger:
        meldung = "keine E-Mail-Adresse für Firma/Ansprechpartner hinterlegt"
        logger.warning(
            "Kein Empfaenger (E-Mail) fuer Musterbox-Nachfassmail gefunden (Deal %s, Woche %s)",
            deal.pk, status.naechste_woche,
        )
        _mail_protokollieren(
            deal=deal, mailtyp="musterbox_nachfass", empfaenger="", betreff="",
            erfolg=False, fehlermeldung=meldung,
        )
        return False, meldung

    vorlage = MusterboxNachfassVorlage.fuer_woche(status.naechste_woche, status.sprache)
    if vorlage is None:
        meldung = f"keine Vorlage für Woche {status.naechste_woche}/{status.sprache} hinterlegt"
        logger.error(
            "Musterbox-Nachfassmail: keine Vorlage fuer Woche %s/%s (Deal %s) - bitte im Admin anlegen",
            status.naechste_woche, status.sprache, deal.pk,
        )
        _mail_protokollieren(
            deal=deal, mailtyp="musterbox_nachfass", empfaenger=empfaenger, betreff="",
            erfolg=False, fehlermeldung=meldung,
        )
        return False, meldung

    ansprechpartner = deal.kontakt
    platzhalter = Context({
        "vorname": ansprechpartner.vorname if ansprechpartner else "",
        "nachname": ansprechpartner.nachname if ansprechpartner else "",
        "firma": deal.firma.name,
        "deal_titel": deal.titel,
        "artikel": _musterversand_artikel_text(deal, status.sprache),
    })
    try:
        betreff = Template(vorlage.betreff).render(platzhalter)
        nachricht_text = Template(vorlage.text).render(platzhalter)
    except Exception as exc:
        logger.exception(
            "Musterbox-Nachfassmail-Vorlage (Woche %s/%s) konnte nicht gerendert werden (Deal %s) - "
            "vermutlich ein Tippfehler in einem {{ Platzhalter }} im Admin",
            status.naechste_woche, status.sprache, deal.pk,
        )
        _mail_protokollieren(
            deal=deal, mailtyp="musterbox_nachfass", empfaenger=empfaenger, betreff="",
            erfolg=False, fehlermeldung=str(exc),
        )
        return False, str(exc)

    kontext = {
        "ansprechpartner": ansprechpartner,
        "nachricht_text": nachricht_text,
        "sprache": status.sprache,
        "site_url": SITE_URL,
        "logo_url": f"{SITE_URL}/static/img/eckopack-logo.png",
    }
    text_body = render_to_string("vertrieb/email/musterbox_nachfass.txt", kontext)
    html_body = render_to_string("vertrieb/email/musterbox_nachfass.html", kontext)

    try:
        mail = EmailMultiAlternatives(betreff, text_body, settings.DEFAULT_FROM_EMAIL, [empfaenger])
        mail.attach_alternative(html_body, "text/html")
        mail.send(fail_silently=False)
    except Exception as exc:
        logger.exception(
            "Musterbox-Nachfassmail (Woche %s) konnte nicht gesendet werden (Deal %s)",
            status.naechste_woche, deal.pk,
        )
        _mail_protokollieren(
            deal=deal, mailtyp="musterbox_nachfass", empfaenger=empfaenger, betreff=betreff,
            erfolg=False, fehlermeldung=str(exc),
        )
        return False, str(exc)

    _mail_protokollieren(
        deal=deal, mailtyp="musterbox_nachfass", empfaenger=empfaenger, betreff=betreff, erfolg=True,
    )
    return True, None


def rechnung_automatisch_erstellen(lieferschein):
    """Legt zu einem soeben versendeten Lieferschein automatisch eine Rechnung an (siehe
    Teil 7 oben) - fuer Muster UND echte Bestellungen gleichermassen, aufgerufen von
    views.lieferschein_versand_bestaetigen.

    Gibt (rechnung, ungepreiste_positionen) zurueck. ungepreiste_positionen ist eine Liste
    von Klartexten ("Position 1 (LUAMO Musterkarton Besteck)") fuer jede Position, deren
    Preis NICHT ermittelt werden konnte (keine Artikel-Verknuepfung auf der
    Lieferschein-Position, oder Artikel ohne Verkaufspreis/Preisstaffel) - ist diese Liste
    nicht leer, bleibt rechnung.status='entwurf' und der Aufrufer darf NICHT automatisch
    versenden (siehe rechnung_versand_senden unten).

    Idempotent: existiert zu diesem Lieferschein bereits eine Rechnung (egal welcher
    Status), wird NICHTS angelegt - gibt dann (bestehende Rechnung, []) zurueck, damit ein
    versehentliches Doppel-Auftreten (z.B. erneuter POST) keine zweite Rechnung erzeugt.
    """
    bestehende = lieferschein.rechnungen.first()
    if bestehende is not None:
        return bestehende, []

    deal = lieferschein.deal
    rechnung = Rechnung.objects.create(
        deal=deal, angebot=lieferschein.angebot, lieferschein=lieferschein,
        sprache=lieferschein.sprache,
        notizen=(
            "Automatisch erzeugt beim Versand (siehe Lieferschein "
            f"{lieferschein.nummer})." if lieferschein.sprache != "en" else
            f"Automatically created on shipment (see delivery note {lieferschein.nummer})."
        ),
    )

    ungepreiste_positionen = []
    for p in lieferschein.positionen.all():
        einzelpreis = None
        steuersatz = Decimal("19.00")
        if p.artikel is not None:
            preis = p.artikel.preis_fuer_menge(p.menge)
            if preis is not None:
                einzelpreis = preis
                steuersatz = p.artikel.ust_satz
        if einzelpreis is None:
            ungepreiste_positionen.append(f"Position {p.position} ({p.bezeichnung})")
            einzelpreis = Decimal("0")
        RechnungPosition.objects.create(
            rechnung=rechnung, artikel=p.artikel, position=p.position, bezeichnung=p.bezeichnung,
            menge=p.menge, einheit=p.einheit, einzelpreis=einzelpreis, steuersatz=steuersatz,
        )

    return rechnung, ungepreiste_positionen


def rechnung_versand_senden(rechnung):
    """Verschickt die (HTML-gestaltete, zweisprachige) Rechnungs-Mail mit PDF-Anhang an den
    Kunden - analog zu lieferschein_versand_abgeschlossen() oben (siehe Teil 7). Wird sowohl
    automatisch direkt nach rechnung_automatisch_erstellen() aufgerufen (wenn alle
    Positionen einen Preis haben) als auch ueber den manuellen "Jetzt versenden"-Button auf
    der Rechnungs-Detailseite (views.rechnung_versand_senden_view) - z.B. nachdem Björn
    fehlende Preise nachgetragen hat.

    Setzt bei Erfolg rechnung.status='versendet' (damit greift automatisch die bestehende
    GoBD-Sperre, siehe Rechnung.ist_bearbeitbar) und rechnung.bestaetigungsmail_gesendet_am.

    Gibt (erfolg: bool, fehlermeldung: str|None) zurueck - wie lieferschein_versand_
    abgeschlossen() bewusst NICHT fail-silent, der aufrufende View soll das sofort im UI
    zeigen koennen."""
    deal = rechnung.deal
    empfaenger = _empfaenger_email(deal)

    if not empfaenger:
        meldung = "keine E-Mail-Adresse für Firma/Ansprechpartner hinterlegt"
        logger.warning(
            "Kein Empfaenger (E-Mail) fuer Rechnungs-Mail gefunden (Rechnung %s, Deal %s)",
            rechnung.nummer, deal.pk,
        )
        _mail_protokollieren(
            deal=deal, mailtyp="rechnung_bestaetigung", empfaenger="", betreff="",
            erfolg=False, fehlermeldung=meldung, rechnung=rechnung,
        )
        return False, meldung

    sprache = rechnung.sprache
    if sprache == "en":
        betreff = f"Your invoice is ready – ECKO-PACK ({rechnung.nummer})"
    else:
        betreff = f"Ihre Rechnung – ECKO-PACK ({rechnung.nummer})"

    kontext = {
        "rechnung": rechnung,
        "deal": deal,
        "firma": deal.firma,
        "ansprechpartner": deal.kontakt,
        "sprache": sprache,
        "site_url": SITE_URL,
        "logo_url": f"{SITE_URL}/static/img/eckopack-logo.png",
    }
    text_body = render_to_string("vertrieb/email/rechnung_bestaetigung.txt", kontext)
    html_body = render_to_string("vertrieb/email/rechnung_bestaetigung.html", kontext)

    try:
        rechnung_pdf_bytes = pdf.rechnung_pdf_erzeugen(rechnung)
        mail = EmailMultiAlternatives(betreff, text_body, settings.DEFAULT_FROM_EMAIL, [empfaenger])
        mail.attach_alternative(html_body, "text/html")
        mail.attach(f"{rechnung.nummer}.pdf", rechnung_pdf_bytes, "application/pdf")
        mail.send(fail_silently=False)
    except Exception as exc:
        logger.exception(
            "Rechnungs-Mail (inkl. PDF) konnte nicht gesendet werden (Rechnung %s)", rechnung.nummer,
        )
        _mail_protokollieren(
            deal=deal, mailtyp="rechnung_bestaetigung", empfaenger=empfaenger, betreff=betreff,
            erfolg=False, fehlermeldung=str(exc), rechnung=rechnung,
        )
        return False, str(exc)

    rechnung.status = "versendet"
    rechnung.bestaetigungsmail_gesendet_am = timezone.now()
    rechnung.save(update_fields=["status", "bestaetigungsmail_gesendet_am"])
    _mail_protokollieren(
        deal=deal, mailtyp="rechnung_bestaetigung", empfaenger=empfaenger, betreff=betreff,
        erfolg=True, rechnung=rechnung,
    )
    return True, None


def artikelliste_versenden(empfaenger_email, sprache="de", empfaenger_zeilen=None):
    """Verschickt die Artikel-/Preisliste (siehe pdf.artikelliste_pdf_erzeugen) als PDF-
    Anhang an eine frei eingegebene E-Mail-Adresse (21.10.2026, auf Wunsch von Björn) -
    bewusst OHNE Deal-/Firmenbezug, anders als alle übrigen Mailfunktionen in diesem Modul:
    EmailVersand.deal ist nullable (siehe Model-Doku "Teil 8"), ein Protokolleintrag mit
    deal=None ist also ausdrücklich vorgesehen. empfaenger_zeilen (optional): Textzeilen
    fürs Anschriftenfeld auf dem PDF-Briefpapier, siehe pdf.artikelliste_pdf_erzeugen.
    Gibt (erfolg: bool, fehlermeldung: str|None) zurück, analog zu
    rechnung_versand_senden() oben."""
    betreff = "ECKO-PACK price list" if sprache == "en" else "ECKO-PACK Artikel- und Preisliste"

    kontext = {
        "sprache": sprache,
        "site_url": SITE_URL,
        "logo_url": f"{SITE_URL}/static/img/eckopack-logo.png",
    }
    text_body = render_to_string("vertrieb/email/artikelliste_versand.txt", kontext)
    html_body = render_to_string("vertrieb/email/artikelliste_versand.html", kontext)

    artikel_liste = Artikel.objects.filter(vertriebskanal="standard").order_by("artikelnummer").prefetch_related("preisstaffeln")

    try:
        pdf_bytes = pdf.artikelliste_pdf_erzeugen(artikel_liste, sprache=sprache, empfaenger_zeilen=empfaenger_zeilen)
        mail = EmailMultiAlternatives(betreff, text_body, settings.DEFAULT_FROM_EMAIL, [empfaenger_email])
        mail.attach_alternative(html_body, "text/html")
        dateiname = "ECKO-PACK_Price_List.pdf" if sprache == "en" else "ECKO-PACK_Artikel-Preisliste.pdf"
        mail.attach(dateiname, pdf_bytes, "application/pdf")
        mail.send(fail_silently=False)
    except Exception as exc:
        logger.exception(
            "Artikelliste-Mail (inkl. PDF) konnte nicht gesendet werden (Empfaenger %s)", empfaenger_email,
        )
        _mail_protokollieren(
            deal=None, mailtyp="artikelliste", empfaenger=empfaenger_email, betreff=betreff,
            erfolg=False, fehlermeldung=str(exc),
        )
        return False, str(exc)

    _mail_protokollieren(
        deal=None, mailtyp="artikelliste", empfaenger=empfaenger_email, betreff=betreff, erfolg=True,
    )
    return True, None
