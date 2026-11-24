"""Automatischer Import von Lieferantenrechnungen aus dem Postfach rechnung@ecko-pack.de
per Microsoft Graph, inkl. Felderkennung aus der PDF per Anthropic-API (23.11.2026, auf
Wunsch von Björn - "Eingangsrechnungen automatisch einstellen").

Architektur/Hintergrund:
- Liest NICHT über die Gmail-Weiterleitung (eckopack.rechnungen@gmail.com), sondern direkt
  bei Microsoft 365, über dieselbe App-Registrierung "ECKO-PACK CRM Mail Reader", die seit
  25.10.2026 schon für vertrieb@ im Einsatz ist (siehe graph_antworten.py) - deren RBAC-for-
  Applications-Rollenzuweisung (Application Mail.Read) war laut dortigem Kommentar von
  Anfang an auch auf rechnung@ecko-pack.de gescoped, nur bisher ungenutzt. Dieselben
  Umgebungsvariablen GRAPH_TENANT_ID/GRAPH_CLIENT_ID/GRAPH_CLIENT_SECRET werden
  wiederverwendet, kein neuer Zugang nötig.
- _access_token()/_http_json()/GraphFehler sind bewusst eine zweite, unabhängige Kopie der
  gleichnamigen Helfer in graph_antworten.py statt eines gemeinsamen Imports - beide
  Mail-Pipelines bleiben dadurch unabhängig voneinander änderbar/testbar, analog zum
  bestehenden Nebeneinander von nachfass_pruefen.py und graph_antworten.py. Gleicher Grund,
  warum hier wie dort kein "requests" eingesetzt wird, nur urllib aus der Standardbibliothek.
- Sachkonto/Kostenstelle bleiben IMMER leer, auch bei automatischem Import - siehe
  Eingangsrechnung-Doku in models.py (19.11.2026, Björns ausdrückliche Vorgabe). Diese Datei
  befüllt beide Felder an keiner Stelle.
- Ein Anhang, der laut Anthropic-Erkennung gar keine Rechnung/Gutschrift ist (z.B.
  Lieferschein, AGB, Werbe-PDF), wird übersprungen, nicht angelegt. Eine Mail kann mehrere
  Eingangsrechnungen enthalten (ein PDF-Anhang je Beleg) - siehe email_message_id-Doku in
  models.py, war dort schon so vorgesehen.
- Unbekannter Lieferant (Absender-Adresse passt zu keiner bestehenden Firma): Björns
  Entscheidung (23.11.2026) ist, automatisch eine neue Firma mit Status "Lieferant"
  anzulegen, deutlich als Platzhalter markiert (siehe PLATZHALTER_HINWEIS) statt den Import
  zurückzustellen. Bewusstes Risiko von Dubletten/falsch benannten Lieferanten - siehe
  Chat-Diskussion 23.11.2026.
- Bereits importierte Mails werden über Eingangsrechnung.email_message_id erkannt (nicht
  eindeutig/unique, siehe Modell-Doku - eine Mail kann mehrere Treffer haben). Es gibt
  bewusst KEINEN separaten "zuletzt geprüft"-Zeitstempel, sondern einen festen
  Rückblick-Zeitraum (LOOKBACK_TAGE) bei jedem Lauf, analog zum HOECHSTENS_TAGE_RUECKBLICK-
  Muster in graph_antworten.py - robuster gegen einen einzelnen ausgefallenen Cron-Lauf.
"""

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import Decimal, InvalidOperation

from django.core.files.base import ContentFile
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import STEUERSATZ_CHOICES, Eingangsrechnung, Firma

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
RECHNUNG_POSTFACH = "rechnung@ecko-pack.de"

# Wie weit zurück bei jedem Lauf nach neuen Rechnungsmails gesucht wird - bewusst mehr als
# der Prüf-Takt (1x täglich, siehe render.yaml), damit ein einzelner ausgefallener Cron-Lauf
# keine Rechnung verloren gehen lässt.
LOOKBACK_TAGE = 4

# Modell für die PDF-Felderkennung, per Umgebungsvariable überschreibbar, falls Anthropic ein
# neueres Modell veröffentlicht, ohne dass dafür ein Deploy nötig sein soll.
STANDARD_MODELL = "claude-sonnet-4-5-20250929"

PLATZHALTER_HINWEIS = (
    "Automatisch angelegt aus E-Mail-Rechnungsimport ({datum}). Lieferantendaten "
    "(Adresse, USt-IdNr., Zahlungsbedingungen) bitte pruefen/vervollstaendigen."
)

EXTRAKTIONS_PROMPT = """Du bekommst eine einzelne PDF-Datei aus dem E-Mail-Posteingang \
rechnung@ecko-pack.de einer Firma namens ECKO-PACK GmbH. Pruefe, ob es sich um eine an \
ECKO-PACK gerichtete Lieferantenrechnung oder Gutschrift handelt (nicht: Lieferschein, \
Auftragsbestaetigung, AGB, Werbung, o.ae.).

Antworte AUSSCHLIESSLICH mit einem einzigen JSON-Objekt, keinem Fliesstext davor/danach, \
keinen Markdown-Codeblock-Markierungen. Exaktes Schema:

{
  "typ": "rechnung" | "gutschrift" | "kein_beleg",
  "lieferant_name": string oder null,
  "lieferant_email": string oder null,
  "rechnungsnummer": string oder null,
  "bestellnummer": string oder null,
  "rechnungsdatum": "YYYY-MM-DD" oder null,
  "faelligkeitsdatum": "YYYY-MM-DD" oder null,
  "betrag_netto": Zahl oder null,
  "betrag_brutto": Zahl oder null,
  "mwst_betrag": Zahl oder null,
  "steuersatz_prozent": Zahl oder null (nur bei einheitlichem Satz, sonst null),
  "skonto_prozent": Zahl oder null,
  "skonto_tage": ganze Zahl oder null,
  "zahlungsbedingungen": string oder null,
  "unsicher": true oder false,
  "begruendung": kurzer string, nur falls unsicher=true, sonst null
}

"typ"="kein_beleg", wenn das PDF klar keine Rechnung/Gutschrift ist - dann duerfen alle \
anderen Felder null sein. Setze "unsicher"=true, wenn Betraege/Datum nicht eindeutig \
lesbar sind (z.B. schlecht gescannt) oder die Zuordnung unklar ist. Erfinde NIEMALS \
Werte, die nicht im Dokument stehen - im Zweifel null."""


class GraphFehler(Exception):
    """Technischer Fehler beim Zugriff auf Microsoft Graph (Token oder Postfach-Abfrage)."""


class ExtraktionsFehler(Exception):
    """Technischer Fehler beim Aufruf der Anthropic-API oder beim Parsen ihrer Antwort."""


def _env_oder_fehler(name, fehlerklasse=GraphFehler):
    wert = os.environ.get(name, "")
    if not wert:
        raise fehlerklasse(f"Umgebungsvariable {name} ist nicht gesetzt.")
    return wert


def _http_json(url, *, method="GET", data=None, headers=None, timeout=30, json_body=False):
    """JSON-REST-Helfer über urllib - siehe Moduldoku, warum kein 'requests'. json_body=True
    sendet `data` als JSON statt als urlencodierte Formulardaten (für die Anthropic-API)."""
    body = None
    alle_header = dict(headers or {})
    if data is not None:
        if json_body:
            body = json.dumps(data).encode("utf-8")
            alle_header.setdefault("Content-Type", "application/json")
        elif isinstance(data, dict):
            body = urllib.parse.urlencode(data).encode("utf-8")
            alle_header.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            body = data
    request = urllib.request.Request(url, data=body, headers=alle_header, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as antwort:
            rohtext = antwort.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        rohtext = exc.read().decode("utf-8", errors="replace")
        raise GraphFehler(f"HTTP {exc.code} von {url}: {rohtext[:500]}") from exc
    except urllib.error.URLError as exc:
        raise GraphFehler(f"Netzwerkfehler bei {url}: {exc}") from exc
    try:
        return json.loads(rohtext) if rohtext else {}
    except json.JSONDecodeError as exc:
        raise GraphFehler(f"Keine gueltige JSON-Antwort von {url}: {rohtext[:500]}") from exc


def _access_token():
    """Holt ein Access Token per Client-Credentials-Flow (App-only, kein Nutzerkontext) -
    identische GRAPH_*-Umgebungsvariablen wie graph_antworten.py, siehe Moduldoku."""
    tenant_id = _env_oder_fehler("GRAPH_TENANT_ID")
    client_id = _env_oder_fehler("GRAPH_CLIENT_ID")
    client_secret = _env_oder_fehler("GRAPH_CLIENT_SECRET")
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    antwort = _http_json(url, method="POST", data={
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
    })
    token = antwort.get("access_token")
    if not token:
        raise GraphFehler(f"Token-Antwort ohne access_token: {antwort}")
    return token


def _postfach_rechnungen_seit(token, postfach, seit_datetime):
    """Liest alle Nachrichten MIT Anhang im Posteingang von `postfach` seit `seit_datetime`,
    über alle Seiten hinweg. hasAttachments-Filter reduziert die Trefferzahl spuerbar, da
    ohne Anhang ohnehin keine Rechnung vorliegen kann."""
    iso = seit_datetime.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    filter_ = urllib.parse.quote(f"receivedDateTime ge {iso} and hasAttachments eq true")
    select = "subject,receivedDateTime,from,hasAttachments"
    url = (
        f"{GRAPH_BASE_URL}/users/{urllib.parse.quote(postfach)}/mailFolders/inbox/messages"
        f"?$filter={filter_}&$select={select}&$top=50"
    )
    header = {"Authorization": f"Bearer {token}"}
    nachrichten = []
    # Hartes Limit gegen Endlosschleife bei kaputter @odata.nextLink - siehe Begruendung in
    # graph_antworten.py._postfach_nachrichten_seit, hier bei taeglichem Takt erst recht mehr
    # als genug.
    for _ in range(50):
        antwort = _http_json(url, headers=header)
        nachrichten.extend(antwort.get("value", []))
        url = antwort.get("@odata.nextLink")
        if not url:
            break
    return nachrichten


def _pdf_anhaenge(token, postfach, message_id):
    """Liefert alle PDF-Dateianhaenge (Name + Base64-Inhalt) einer Nachricht. Nicht-Datei-
    anhaenge (z.B. eingebettete Outlook-Items) und Nicht-PDF-Anhaenge werden ignoriert."""
    # Kein $select hier: Graph lehnt "contentBytes" im $select auf der polymorphen
    # attachments-Collection ab ("Could not find a property named 'contentBytes' on
    # type 'microsoft.graph.attachment'") - contentBytes existiert nur auf der
    # Unterklasse fileAttachment. Ohne $select liefert Graph trotzdem alle Felder
    # (inkl. contentBytes) zurueck, nur eben ungefiltert. Live mit echten Mails
    # verifiziert (24.11.2026, siehe Chat).
    url = (
        f"{GRAPH_BASE_URL}/users/{urllib.parse.quote(postfach)}/messages/{message_id}"
        f"/attachments"
    )
    header = {"Authorization": f"Bearer {token}"}
    antwort = _http_json(url, headers=header)
    ergebnis = []
    for anhang in antwort.get("value", []):
        ist_datei = anhang.get("@odata.type") == "#microsoft.graph.fileAttachment"
        content_type = (anhang.get("contentType") or "").lower()
        name = anhang.get("name") or "anhang.pdf"
        if ist_datei and ("pdf" in content_type or name.lower().endswith(".pdf")):
            if anhang.get("contentBytes"):
                ergebnis.append({"name": name, "contentBytes": anhang["contentBytes"]})
    return ergebnis


def _anthropic_erkennung(pdf_base64):
    """Ruft die Anthropic Messages API mit der PDF als Dokument-Content-Block auf (native
    PDF-Unterstuetzung, kein separates OCR/Text-Extraktions-Paket noetig - funktioniert auch
    bei gescannten/Bild-Rechnungen). Gibt das geparste JSON-Objekt zurueck oder wirft
    ExtraktionsFehler."""
    api_key = _env_oder_fehler("ANTHROPIC_API_KEY", fehlerklasse=ExtraktionsFehler)
    modell = os.environ.get("ANTHROPIC_INVOICE_MODEL", STANDARD_MODELL)
    payload = {
        "model": modell,
        # War 1024: bei einer realen Rechnung (SPORTFIVE/HSV, 24.11.2026) brach die
        # Antwort ohne schliessende "}" ab - re.search unten fand daher gar keine
        # JSON-Struktur. Ursache noch nicht abschliessend bestaetigt (kein Zugriff auf
        # den echten stop_reason jenes Laufs), aber stop_reason wird jetzt mitgeloggt,
        # falls es erneut passiert. 4096 kostet nichts, wenn ungenutzt - Anthropic
        # berechnet nur tatsaechlich erzeugte Tokens.
        "max_tokens": 4096,
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "document",
                    "source": {
                        "type": "base64",
                        "media_type": "application/pdf",
                        "data": pdf_base64,
                    },
                },
                {"type": "text", "text": EXTRAKTIONS_PROMPT},
            ],
        }],
    }
    header = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    try:
        antwort = _http_json(ANTHROPIC_URL, method="POST", data=payload, headers=header,
                              json_body=True, timeout=60)
    except GraphFehler as exc:
        # _http_json wirft bewusst generisch GraphFehler (siehe oben) - hier in die fuer
        # diesen Aufrufer passende Fehlerklasse uebersetzen.
        raise ExtraktionsFehler(str(exc)) from exc
    bloecke = antwort.get("content") or []
    text = "".join(b.get("text", "") for b in bloecke if b.get("type") == "text").strip()
    if not text:
        raise ExtraktionsFehler(f"Anthropic-Antwort ohne Text-Block: {antwort}")
    # Robust gegen ```json ... ``` -Einfassung, falls das Modell sich trotz Anweisung nicht
    # an "nur JSON" haelt.
    treffer = re.search(r"\{.*\}", text, re.DOTALL)
    if not treffer:
        # stop_reason mitloggen: "max_tokens" belegt, dass die Antwort vor der
        # schliessenden "}" abgeschnitten wurde (siehe max_tokens-Kommentar oben) -
        # jeder andere Wert deutet auf eine andere Ursache hin.
        stop_reason = antwort.get("stop_reason")
        raise ExtraktionsFehler(
            f"Keine JSON-Struktur in Anthropic-Antwort (stop_reason={stop_reason}, "
            f"Laenge={len(text)}): {text[:500]}"
        )
    try:
        return json.loads(treffer.group(0))
    except json.JSONDecodeError as exc:
        raise ExtraktionsFehler(f"Anthropic-JSON nicht parsbar: {text[:500]}") from exc


def _decimal_oder_none(wert):
    if wert is None or wert == "":
        return None
    try:
        return Decimal(str(wert)).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _datum_oder_none(wert):
    if not wert:
        return None
    try:
        return datetime.strptime(wert, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _passender_steuersatz(wert):
    """Nur einen der drei festen Sachkonto-Steuersaetze (19/7/0 %) uebernehmen - alles
    andere (z.B. Rundungsungenauigkeit der Erkennung, gemischte Saetze) bleibt leer statt
    einen ungueltigen choices-Wert zu erzwingen."""
    betrag = _decimal_oder_none(wert)
    if betrag is None:
        return None
    gueltige = {code for code, _ in STEUERSATZ_CHOICES}
    return betrag if betrag in gueltige else None


def _lieferant_ermitteln(absender_email, lieferant_name, heute):
    """Sucht eine bestehende, nicht archivierte Firma per exakter E-Mail, dann per exaktem
    Namen (case-insensitiv) - sonst wird eine neue Platzhalter-Firma mit Status "Lieferant"
    angelegt (Björns Entscheidung 23.11.2026, siehe Moduldoku)."""
    kandidaten = Firma.objects.filter(archiviert=False)
    if absender_email:
        treffer = kandidaten.filter(email__iexact=absender_email).first()
        if treffer:
            return treffer, False
    if lieferant_name:
        treffer = kandidaten.filter(name__iexact=lieferant_name.strip()).first()
        if treffer:
            return treffer, False
    name = (lieferant_name or "").strip() or absender_email or "Unbekannter Lieferant (E-Mail-Import)"
    neue_firma = Firma.objects.create(
        name=name,
        status="lieferant",
        email=absender_email or "",
        notizen=PLATZHALTER_HINWEIS.format(datum=heute.isoformat()),
    )
    return neue_firma, True


@transaction.atomic
def _eingangsrechnung_anlegen(extraktion, anhang, message_id, absender_email):
    heute = timezone.localdate()
    lieferant, neu_angelegt = _lieferant_ermitteln(
        absender_email, extraktion.get("lieferant_name"), heute,
    )
    rechnungsnummer = (extraktion.get("rechnungsnummer") or "").strip()
    if not rechnungsnummer:
        # Ohne Rechnungsnummer greift der UniqueConstraint (lieferant, rechnungsnummer)
        # nicht sinnvoll und Dubletten waeren nicht erkennbar - lieber ueberspringen als
        # raten.
        raise ValueError("Keine Rechnungsnummer erkannt.")
    betrag_netto = _decimal_oder_none(extraktion.get("betrag_netto"))
    betrag_brutto = _decimal_oder_none(extraktion.get("betrag_brutto"))
    if betrag_brutto is None:
        raise ValueError("Kein Brutto-Betrag erkannt.")
    rechnungsdatum = _datum_oder_none(extraktion.get("rechnungsdatum")) or heute
    notiz_teile = ["Automatisch per E-Mail-Import erkannt - Felder bitte gegenpruefen."]
    if extraktion.get("unsicher"):
        notiz_teile.append(f"KI-Erkennung unsicher: {extraktion.get('begruendung') or 'kein Grund angegeben'}.")
    if neu_angelegt:
        notiz_teile.append("Lieferant wurde dabei automatisch neu angelegt (Platzhalter).")
    if betrag_netto is None:
        notiz_teile.append("Netto-Betrag nicht erkannt, hilfsweise = Brutto-Betrag gesetzt - bitte korrigieren.")

    eingangsrechnung = Eingangsrechnung(
        lieferant=lieferant,
        rechnungsnummer=rechnungsnummer,
        typ="gutschrift" if extraktion.get("typ") == "gutschrift" else "rechnung",
        rechnungsdatum=rechnungsdatum,
        faelligkeitsdatum=_datum_oder_none(extraktion.get("faelligkeitsdatum")),
        bestellnummer=(extraktion.get("bestellnummer") or "")[:100],
        betrag_netto=betrag_netto if betrag_netto is not None else betrag_brutto,
        betrag_brutto=betrag_brutto,
        mwst_betrag=_decimal_oder_none(extraktion.get("mwst_betrag")) or Decimal("0"),
        steuersatz=_passender_steuersatz(extraktion.get("steuersatz_prozent")),
        skonto_prozent=_decimal_oder_none(extraktion.get("skonto_prozent")),
        skonto_tage=extraktion.get("skonto_tage") or None,
        zahlungsbedingungen=(extraktion.get("zahlungsbedingungen") or "")[:200],
        status="zu_pruefen",
        quelle="email_import",
        email_message_id=message_id,
        notizen=" ".join(notiz_teile),
    )
    # Erst den Datensatz speichern (das ist der Punkt, an dem der UniqueConstraint
    # lieferant+rechnungsnummer greift und IntegrityError wirft) - DANACH erst die Datei
    # tatsaechlich auf die Platte schreiben. Storage-Schreibzugriffe sind NICHT Teil der
    # DB-Transaktion, ein IntegrityError hier wuerde die Datei sonst als Leiche auf der
    # Platte zuruecklassen, obwohl kein Datensatz dafuer existiert (so im ersten Anlauf
    # tatsaechlich passiert, siehe Verifikations-Szenario "doppelte Rechnungsnummer").
    eingangsrechnung.save()
    eingangsrechnung.rechnung_datei.save(
        anhang["name"], ContentFile(base64.b64decode(anhang["contentBytes"])), save=True,
    )
    return eingangsrechnung


def rechnungen_importieren():
    """Hauptfunktion, vom Management-Command eingangsrechnungen_importieren aufgerufen.

    Gibt (geprueft, importiert, uebersprungen, fehlgeschlagen) zurueck. Wirft GraphFehler bei
    technischen Problemen beim Postfach-Zugriff selbst (Token, Netzwerk) - der Aufrufer
    bricht dann den ganzen Lauf ab, analog zu graph_antworten.antworten_pruefen(). Fehler bei
    einzelnen Nachrichten/Anhaengen (kaputtes PDF, Anthropic-Fehler, fehlende Pflichtfelder)
    werden dagegen pro Anhang abgefangen, damit ein einzelner kaputter Beleg nicht den
    gesamten Lauf verhindert."""
    token = _access_token()
    seit = timezone.now() - timedelta(days=LOOKBACK_TAGE)
    nachrichten = _postfach_rechnungen_seit(token, RECHNUNG_POSTFACH, seit)

    geprueft = importiert = uebersprungen = fehlgeschlagen = 0
    for nachricht in nachrichten:
        message_id = nachricht.get("id")
        if not message_id or Eingangsrechnung.objects.filter(email_message_id=message_id).exists():
            continue
        geprueft += 1
        absender = ((nachricht.get("from") or {}).get("emailAddress")) or {}
        absender_email = absender.get("address", "")

        try:
            anhaenge = _pdf_anhaenge(token, RECHNUNG_POSTFACH, message_id)
        except GraphFehler as exc:
            logger.error("Eingangsrechnungen-Import: Anhaenge von Nachricht %s nicht lesbar: %s",
                         message_id, exc)
            fehlgeschlagen += 1
            continue

        if not anhaenge:
            uebersprungen += 1
            continue

        for anhang in anhaenge:
            try:
                extraktion = _anthropic_erkennung(anhang["contentBytes"])
            except ExtraktionsFehler as exc:
                logger.error("Eingangsrechnungen-Import: Felderkennung fuer '%s' (Nachricht %s) "
                             "fehlgeschlagen: %s", anhang["name"], message_id, exc)
                fehlgeschlagen += 1
                continue

            if extraktion.get("typ") not in ("rechnung", "gutschrift"):
                uebersprungen += 1
                continue

            try:
                _eingangsrechnung_anlegen(extraktion, anhang, message_id, absender_email)
                importiert += 1
            except IntegrityError:
                # Vermutlich doppelt erkannte Rechnungsnummer desselben Lieferanten (siehe
                # UniqueConstraint in models.py) - kein technischer Fehler, einfach schon da.
                uebersprungen += 1
            except (ValueError, InvalidOperation) as exc:
                logger.error("Eingangsrechnungen-Import: '%s' (Nachricht %s) konnte nicht "
                             "angelegt werden: %s", anhang["name"], message_id, exc)
                fehlgeschlagen += 1

    return geprueft, importiert, uebersprungen, fehlgeschlagen
