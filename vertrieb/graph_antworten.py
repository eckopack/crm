"""Erkennung von Kundenantworten auf automatische Nachfass-Mails im Postfach
vertrieb@ecko-pack.de, über Microsoft Graph (25.10.2026, auf Wunsch von Björn -
"Graph-Antworten", siehe Chat-Verlauf 24./25.10.2026).

Hintergrund/Architektur:
- Die Nachfass-Mails selbst verlassen das System über Resend (SMTP), nicht über Exchange/
  Graph (siehe settings.EMAIL_BACKEND, nurture.py) - Exchange sieht den ausgehenden Versand
  also nie und kann dafür keine eigene conversationId vergeben. Die Zuordnung "diese
  eingehende Mail ist die Antwort auf jene ausgehende Mail" läuft deshalb NICHT über
  conversationId, sondern darüber, dass wir beim Versand selbst eine Message-ID setzen
  (siehe nurture.py, email.utils.make_msgid) und hier gegen die In-Reply-To-/References-
  Header der eingehenden Mail matchen - das ist Standard-E-Mail-Threading (RFC 5322) und
  funktioniert unabhängig davon, über welchen Weg die ursprüngliche Mail verschickt wurde.
- Die App-Registrierung "ECKO-PACK CRM Mail Reader" hat bewusst KEINE API-Berechtigung in
  Azure AD/Entra (siehe E-Mail-Austausch mit Andrej, IT, 25.10.2026) - der Zugriff läuft
  ausschließlich über eine auf vertrieb@/rechnung@ beschränkte RBAC-for-Applications-
  Rollenzuweisung (Application Mail.Read) in Exchange Online. Diese Datei greift deshalb nur
  auf vertrieb@ecko-pack.de zu; rechnung@ (Eingangsrechnungen) ist ein eigenständiges, noch
  nicht gebautes Stück (Phase 4 Materialwirtschaft).
- Björns ausdrückliche Entscheidung (25.10.2026, "bis wir eingreifen"): eine erkannte Antwort
  BEENDET NICHT automatisch die laufende Nachfasskette (AngebotNachfassStatus/
  MusterboxNachfassStatus) - sie legt nur eine interne Aktivität (typ="nachfass") für den
  zuständigen Mitarbeiter an. Die Kette läuft weiter, bis ein Mensch eingreift.

Bewusst ohne zusätzliche Abhängigkeit (kein "requests", kein "msal") - beide HTTP-Aufrufe
(Token holen, Postfach lesen) sind einfache JSON-REST-Calls, dafür reicht urllib aus der
Standardbibliothek; requirements.txt bleibt dadurch unverändert.
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.utils import timezone

from .models import Aktivitaet, EmailVersand

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
VERTRIEB_POSTFACH = "vertrieb@ecko-pack.de"

# Nachfassketten, für die beim Versand eine Message-ID gesetzt wird (siehe nurture.py) -
# nur für diese ist eine Antwort-Erkennung sinnvoll/möglich.
MAILTYPEN_MIT_ANTWORT_ERKENNUNG = ("musterbox_nachfass", "angebot_nachfass")

# Sicherheitsnetz gegen eine unbegrenzt wachsende Graph-Abfrage, falls ein EmailVersand aus
# irgendeinem Grund nie als beantwortet markiert wird (z.B. Bug, oder Kunde antwortet nie) -
# siehe HOECHSTENS_TAGE_RUECKBLICK-Doku in antworten_pruefen().
HOECHSTENS_TAGE_RUECKBLICK = 90


class GraphFehler(Exception):
    """Technischer Fehler beim Zugriff auf Microsoft Graph (Token oder Postfach-Abfrage)."""


def _env_oder_fehler(name):
    wert = os.environ.get(name, "")
    if not wert:
        raise GraphFehler(f"Umgebungsvariable {name} ist nicht gesetzt.")
    return wert


def _http_json(url, *, method="GET", data=None, headers=None, timeout=20):
    """Kleiner JSON-REST-Helfer über urllib - siehe Moduldoku, warum kein 'requests'."""
    body = None
    alle_header = dict(headers or {})
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8") if isinstance(data, dict) else data
        alle_header.setdefault("Content-Type", "application/x-www-form-urlencoded")
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
        raise GraphFehler(f"Keine gültige JSON-Antwort von {url}: {rohtext[:500]}") from exc


def _access_token():
    """Holt ein Access Token per Client-Credentials-Flow (App-only, kein Nutzerkontext).

    GRAPH_TENANT_ID/GRAPH_CLIENT_ID/GRAPH_CLIENT_SECRET werden von Björn selbst in Render
    als Umgebungsvariablen gesetzt (nie von Claude/im Code), siehe render.yaml."""
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


def _header_werte(nachricht, header_name):
    """Liefert alle Werte eines Internet-Mail-Headers (z.B. 'In-Reply-To') einer über Graph
    gelesenen Nachricht - Graph liefert internetMessageHeaders nur, wenn explizit per
    $select angefordert (siehe _postfach_nachrichten_seit)."""
    header_name = header_name.lower()
    return [
        h.get("value", "")
        for h in (nachricht.get("internetMessageHeaders") or [])
        if h.get("name", "").lower() == header_name
    ]


def _referenzierte_message_ids(nachricht):
    """Extrahiert alle '<...>'-Message-ID-Tokens aus In-Reply-To/References einer
    eingehenden Mail (RFC 5322 - References kann mehrere, leerzeichengetrennte IDs
    enthalten, In-Reply-To i.d.R. genau eine)."""
    gefunden = set()
    for header_name in ("In-Reply-To", "References"):
        for wert in _header_werte(nachricht, header_name):
            for token in wert.split():
                token = token.strip()
                if token.startswith("<") and token.endswith(">"):
                    gefunden.add(token)
    return gefunden


def _postfach_nachrichten_seit(token, postfach, seit_datetime):
    """Liest alle Nachrichten im Posteingang von `postfach` seit `seit_datetime` (inkl.
    internetMessageHeaders für den Antwort-Abgleich), über alle Seiten hinweg."""
    iso = seit_datetime.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    filter_ = urllib.parse.quote(f"receivedDateTime ge {iso}")
    select = "subject,receivedDateTime,internetMessageHeaders"
    url = (
        f"{GRAPH_BASE_URL}/users/{urllib.parse.quote(postfach)}/mailFolders/inbox/messages"
        f"?$filter={filter_}&$select={select}&$top=50"
    )
    header = {"Authorization": f"Bearer {token}"}
    nachrichten = []
    # Hartes Limit gegen eine Endlosschleife bei einer kaputten/unerwarteten @odata.nextLink -
    # 50 Seiten à 50 Nachrichten (2500) ist für ein einzelnes Postfach im Prüf-Takt von
    # Stunden weit mehr, als realistisch jemals anfallen sollte.
    for _ in range(50):
        antwort = _http_json(url, headers=header)
        nachrichten.extend(antwort.get("value", []))
        url = antwort.get("@odata.nextLink")
        if not url:
            break
    return nachrichten


def antworten_pruefen():
    """Hauptfunktion, vom Management-Command graph_antworten_pruefen aufgerufen (siehe dort,
    analog zu nachfass_pruefen.py).

    Gibt (anzahl_geprueft, anzahl_erkannt) zurück. Wirft GraphFehler bei technischen
    Problemen (Token, Netzwerk) - der Aufrufer loggt das und bricht den Lauf ab, statt
    halbe/inkonsistente Ergebnisse zu riskieren; einzelne Datenprobleme (z.B. eine Aktivität
    kann nicht angelegt werden) werden dagegen pro Treffer abgefangen, damit ein einzelner
    kaputter Datensatz nicht den ganzen Lauf verhindert."""
    offene = list(
        EmailVersand.objects.filter(
            mailtyp__in=MAILTYPEN_MIT_ANTWORT_ERKENNUNG,
            erfolg=True,
            antwort_erkannt_am__isnull=True,
        )
        .exclude(message_id="")
        .select_related("deal", "deal__zustaendiger", "angebot")
    )
    if not offene:
        return 0, 0

    seit = min(e.versendet_am for e in offene)
    aelteste_erlaubt = timezone.now() - timedelta(days=HOECHSTENS_TAGE_RUECKBLICK)
    seit = max(seit, aelteste_erlaubt)

    token = _access_token()
    nachrichten = _postfach_nachrichten_seit(token, VERTRIEB_POSTFACH, seit)

    nach_message_id = {e.message_id: e for e in offene}
    erkannt = 0
    jetzt = timezone.now()

    for nachricht in nachrichten:
        for referenz in _referenzierte_message_ids(nachricht):
            email_versand = nach_message_id.get(referenz)
            if email_versand is None:
                continue
            try:
                email_versand.antwort_erkannt_am = jetzt
                email_versand.save(update_fields=["antwort_erkannt_am"])
                deal = email_versand.deal
                Aktivitaet.objects.create(
                    typ="nachfass",
                    betreff=f"Kunde hat geantwortet: {email_versand.betreff or email_versand.mailtyp}",
                    beschreibung=(
                        f"Antwort im Postfach {VERTRIEB_POSTFACH} erkannt auf die automatische "
                        f"Mail \"{email_versand.betreff}\" vom {email_versand.versendet_am:%d.%m.%Y %H:%M} "
                        f"an {email_versand.empfaenger}. Betreff der Antwort: "
                        f"\"{nachricht.get('subject', '')}\". Die Nachfasskette läuft automatisch "
                        f"weiter - bitte manuell prüfen und bei Bedarf beenden."
                    ),
                    deal=deal,
                    firma=deal.firma if deal else None,
                    zustaendiger=deal.zustaendiger if deal else None,
                )
                erkannt += 1
            except Exception:
                logger.exception(
                    "Erkannte Antwort (EmailVersand %s) konnte nicht verarbeitet werden",
                    email_versand.pk,
                )
            # Jede Message-ID höchstens einmal verbrauchen, auch falls sie aus irgendeinem
            # Grund mehrfach vorkäme (z.B. zwei verschiedene eingehende Mails referenzieren
            # dieselbe Nachfassmail - selten, aber ohne pop() würden wir doppelt anlegen).
            nach_message_id.pop(referenz, None)

    return len(offene), erkannt
