"""
Management-Command zum Import des Artikelstamms (Blatt "Artikel") aus der
ECKO-PACK/LUAMO-Artikelstamm-Excel-Datei in das CRM.

Nutzung:
    python manage.py import_artikelstamm /pfad/zur/Datei.xlsx
    python manage.py import_artikelstamm /pfad/zur/Datei.xlsx --dry-run

Der Import ist idempotent: Artikel werden über das Feld "Artikelnummer" erkannt und bei
einem erneuten Import aktualisiert statt dupliziert (genau wie Firmen/Kontakte/Deals über
externe_id beim Leadlisten-Import). Preisstaffeln eines Artikels werden bei jedem Import
komplett neu aus der Datei geschrieben (alte Staffeln dieses Artikels werden vorher
gelöscht) - so bleibt die Datei eine lebende Masterdatei: Zeile ändern, neu importieren.

Annahmen (siehe Chat mit Björn vom 14.10.2026, Datei
"LUAMO_Masterartikelstamm_DE_EN_mit_Musterbeilegern.xlsx"):

- Das Blatt "Artikel" ist führend (Björns Entscheidung). Das Blatt "Stammdaten NEU"
  enthält dieselben Artikelnummern mit teils zusätzlichen Logistikfeldern (Umkarton-VE,
  Paletten), wird hier aber NICHT ausgelesen - falls diese Felder später gebraucht
  werden, müsste das Modell und dieser Import erweitert werden.

- Die Spalte "Geschäftsbereich *" in der Datei enthält KEINE der fünf ECKO-PACK-
  Unternehmensbereiche, sondern eine feinere Produktkategorie (hier: "Einweg-/
  Serviceprodukte" [Trinkhalme], "Großbesteck", "Kleinbesteck", "Muster"). Dieser Text
  wird deshalb in das neue Feld Artikel.warengruppe geschrieben; Artikel.geschaeftsbereich
  (der Unternehmensbereich) wird für ALLE importierten Zeilen fest auf
  "einweg_serviceprodukte" gesetzt, da alle vier Kategorien dort einsortiert sind.

- Mengenstaffelpreise (Spalten "VK 1: 300.000 Stk" ... "VK 9: 50 Stk"): Die Spalten-
  überschriften sind nur Richtwerte und gelten NICHT wörtlich für alle Warengruppen -
  laut den Blättern "VK-Staffeln" (Trinkhalme) und "Besteck-Staffeln" (Groß-/
  Kleinbesteck) haben Großbesteck und Kleinbesteck eigene, leicht abweichende
  Mindestmengen je Stufe (z. B. Großbesteck VK2 ab 200.100 Stk statt 200.000). Dieser
  Import nutzt deshalb pro Warengruppe eine eigene, hier hart hinterlegte Mindestmengen-
  Tabelle (siehe ABMENGE_JE_WARENGRUPPE) statt die Spaltenüberschriften zu interpretieren.
  Für eine unbekannte Warengruppe werden befüllte VK-Spalten NICHT importiert, sondern
  nur als Warnung gemeldet - das verhindert falsche Mindestmengen für künftige, anders
  strukturierte Produktlinien. Für "Muster" sind in der Datei ohnehin keine VK-Spalten
  befüllt (nur der Flatrate-Verkaufspreis).

- Achtung (an Björn kommuniziert, nicht Teil dieses Imports): Mehrere Preisstaffeln bei
  Großbesteck/Kleinbesteck sind laut dem Blatt "Besteck-Staffeln" noch "Vorschlag", nicht
  "bestätigt" (nur Großbesteck VK1 und Kleinbesteck-Pommespicker VK1 sind als bestätigt
  vermerkt). Dieser Import übernimmt trotzdem alle Werte unverändert - die fachliche
  Freigabe der Preise bleibt Björns Aufgabe, bevor ein Angebot mit diesen Preisen
  rausgeht.

- Artikel ohne jeden Preis (weder Flatrate-Verkaufspreis noch eine Preisstaffel) werden
  TROTZDEM angelegt (Stammdaten/Lagerbestand sind auch ohne Preis nützlich), aber mit
  einer Warnung gemeldet - entsprechend Björns Entscheidung, offene/unfertige Artikel
  nicht zu sperren, sondern nur sichtbar zu machen.

- Status (Spalte "Status", z. B. "In Vorbereitung", "Entwurf"): wird informativ in
  Artikel.status übernommen (keine Sperre für Angebote/Packscheine), unbekannte Texte
  fallen auf "in_vorbereitung" zurück.
"""
from decimal import Decimal, InvalidOperation

import openpyxl
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from vertrieb.models import Artikel, EINHEIT_CHOICES, Preisstaffel

GESCHAEFTSBEREICH_IMPORT = "einweg_serviceprodukte"

# Spaltenreihenfolge der neun VK-Staffel-Spalten im Blatt "Artikel", in dieser Reihenfolge.
VK_SPALTEN = [
    "VK 1: 300.000 Stk", "VK 2: 200.000 Stk", "VK 3: 100.000 Stk", "VK 4: 50.000 Stk",
    "VK 5: 10.000 Stk", "VK 6: 3.000 Stk", "VK 7: 1.000 Stk", "VK 8: 100 / 150 / 500 Stk",
    "VK 9: 50 Stk",
]

# Echte Mindestmengen je Warengruppe (siehe Blätter "VK-Staffeln" / "Besteck-Staffeln"),
# NICHT identisch mit den generischen Spaltenüberschriften oben - siehe Docstring.
ABMENGE_JE_WARENGRUPPE = {
    "Einweg-/Serviceprodukte": [300000, 200000, 100000, 50000, 10000, 3000, 1000, 100, 50],
    "Großbesteck": [300000, 200100, 100050, 50100, 10050, 3000, 1050, 150],
    "Kleinbesteck": [300000, 200000, 100000, 50000, 10000, 3000, 1000, 500],
}

STATUS_MAPPING = {
    "in vorbereitung": "in_vorbereitung",
    "entwurf": "in_vorbereitung",
    "aktiv": "aktiv",
    "auslaufend": "auslaufend",
    "gesperrt": "gesperrt",
}

_EINHEIT_LABEL_ZU_KEY = {label.lower(): key for key, label in EINHEIT_CHOICES}


def _s(value):
    if value is None:
        return ""
    return str(value).strip()


def _dec(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int(value):
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class Command(BaseCommand):
    help = "Importiert den Artikelstamm (Blatt 'Artikel') aus der Artikelstamm-Excel-Datei."

    def add_arguments(self, parser):
        parser.add_argument("pfad", type=str, help="Pfad zur .xlsx-Datei")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Nur anzeigen, was passieren würde - ohne etwas zu speichern.",
        )

    def handle(self, *args, **options):
        pfad = options["pfad"]
        dry_run = options["dry_run"]

        try:
            wb = openpyxl.load_workbook(pfad, data_only=True)
        except FileNotFoundError:
            raise CommandError(f"Datei nicht gefunden: {pfad}")

        if "Artikel" not in wb.sheetnames:
            raise CommandError("Blatt 'Artikel' fehlt in der Datei - Import abgebrochen.")

        ws = wb["Artikel"]
        header = [_s(c.value) for c in ws[1]]
        spalte = {name: idx for idx, name in enumerate(header) if name}

        pflicht = ["Artikelnummer *", "Bezeichnung *", "Geschäftsbereich *", "Einheit *", "USt-Satz (%) *"]
        fehlend = [p for p in pflicht if p not in spalte]
        if fehlend:
            raise CommandError(f"Pflichtspalte(n) fehlen im Blatt 'Artikel': {', '.join(fehlend)}")

        def wert(row, name):
            idx = spalte.get(name)
            return row[idx] if idx is not None else None

        stats = {"neu": 0, "aktualisiert": 0, "uebersprungen": 0, "warnungen": []}

        with transaction.atomic():
            for row in ws.iter_rows(min_row=2, values_only=True):
                artikelnummer = _s(wert(row, "Artikelnummer *"))
                if not artikelnummer:
                    continue

                bezeichnung = _s(wert(row, "Bezeichnung *"))
                if not bezeichnung:
                    stats["warnungen"].append(f"{artikelnummer}: keine Bezeichnung - übersprungen.")
                    stats["uebersprungen"] += 1
                    continue

                warengruppe = _s(wert(row, "Geschäftsbereich *"))
                if not warengruppe:
                    stats["warnungen"].append(f"{artikelnummer}: kein Geschäftsbereich/Warengruppe - übersprungen.")
                    stats["uebersprungen"] += 1
                    continue

                einheit_text = _s(wert(row, "Einheit *")).lower()
                einheit = _EINHEIT_LABEL_ZU_KEY.get(einheit_text)
                if einheit is None:
                    einheit = "stk"
                    stats["warnungen"].append(
                        f"{artikelnummer}: Einheit '{_s(wert(row, 'Einheit *'))}' unbekannt - 'Stück' angenommen."
                    )

                ust_satz = _dec(wert(row, "USt-Satz (%) *"))
                if ust_satz is None:
                    ust_satz = Decimal("19.00")
                    stats["warnungen"].append(f"{artikelnummer}: kein USt-Satz - 19% angenommen.")

                status_text = _s(wert(row, "Status")).lower()
                status = STATUS_MAPPING.get(status_text, "in_vorbereitung")

                defaults = {
                    "bezeichnung": bezeichnung,
                    "beschreibung": _s(wert(row, "Beschreibung")),
                    "geschaeftsbereich": GESCHAEFTSBEREICH_IMPORT,
                    "warengruppe": warengruppe,
                    "einheit": einheit,
                    "verkaufspreis": _dec(wert(row, "Verkaufspreis (EUR, netto) *")),
                    "ust_satz": ust_satz,
                    "einkaufspreis": _dec(wert(row, "Einkaufspreis (EUR, netto)")),
                    "lagerbestand_aktuell": _dec(wert(row, "Lagerbestand aktuell")),
                    "mindestbestand": _dec(wert(row, "Mindestbestand")),
                    "verpackungseinheit_stk": _int(wert(row, "Verpackung Stk")),
                    "lagerort": _s(wert(row, "Lagerort"))[:100],
                    "lieferant": _s(wert(row, "Lieferant"))[:200],
                    "status": status,
                    "notizen": _s(wert(row, "Notizen")),
                }

                obj, created = Artikel.objects.get_or_create(artikelnummer=artikelnummer, defaults=defaults)
                if created:
                    stats["neu"] += 1
                else:
                    for k, v in defaults.items():
                        setattr(obj, k, v)
                    obj.save()
                    stats["aktualisiert"] += 1

                # Preisstaffeln: je Import komplett neu schreiben (siehe Docstring).
                abmengen = ABMENGE_JE_WARENGRUPPE.get(warengruppe)
                neue_staffeln = []
                if abmengen is not None:
                    for spalten_name, ab_menge in zip(VK_SPALTEN, abmengen):
                        preis = _dec(wert(row, spalten_name))
                        if preis is not None:
                            neue_staffeln.append(Preisstaffel(artikel=obj, ab_menge=ab_menge, preis_netto=preis))
                else:
                    for spalten_name in VK_SPALTEN:
                        if wert(row, spalten_name) not in (None, ""):
                            stats["warnungen"].append(
                                f"{artikelnummer}: Warengruppe '{warengruppe}' hat keine hinterlegte "
                                f"Mindestmengen-Tabelle - Spalte '{spalten_name}' NICHT importiert."
                            )
                            break

                if not dry_run:
                    obj.preisstaffeln.all().delete()
                    if neue_staffeln:
                        Preisstaffel.objects.bulk_create(neue_staffeln)

                if defaults["verkaufspreis"] is None and not neue_staffeln:
                    stats["warnungen"].append(f"{artikelnummer}: kein Preis hinterlegt (weder Flatrate noch Staffel).")

            if dry_run:
                transaction.set_rollback(True)
                self.stdout.write(self.style.WARNING("--dry-run: Es wurde NICHTS gespeichert."))

        self.stdout.write(self.style.SUCCESS(
            f"Artikel: {stats['neu']} neu, {stats['aktualisiert']} aktualisiert, "
            f"{stats['uebersprungen']} übersprungen"
        ))
        if stats["warnungen"]:
            self.stdout.write(self.style.WARNING(f"\n{len(stats['warnungen'])} Warnung(en):"))
            for w in stats["warnungen"]:
                self.stdout.write(self.style.WARNING(f"  - {w}"))
