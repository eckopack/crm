"""Prüft rechnung@ecko-pack.de per Microsoft Graph auf neue Lieferantenrechnungen und legt
sie automatisch als Eingangsrechnung an (23.11.2026, auf Wunsch von Björn).

Wird wie nachfass_pruefen/graph_antworten_pruefen nicht direkt per Cron gegen die SQLite-
Datei aufgerufen (die liegt nur auf der Disk des Web-Service), sondern ueber den internen
HTTP-Endpoint vertrieb.views.interner_eingangsrechnungen_cron, den ein separater Render-
Cron-Job per HTTPS anstoesst (siehe render.yaml). Die eigentliche Logik (Graph-Zugriff,
PDF-Felderkennung per Anthropic, Lieferanten-Zuordnung, Eingangsrechnung anlegen) steckt in
vertrieb/graph_eingangsrechnungen.py - dieser Befehl ist nur der duenne Cron-Einstiegspunkt.
"""

from django.core.management.base import BaseCommand

from vertrieb.graph_eingangsrechnungen import GraphFehler, rechnungen_importieren


class Command(BaseCommand):
    help = "Prüft rechnung@ecko-pack.de per Microsoft Graph auf neue Lieferantenrechnungen."

    def handle(self, *args, **options):
        try:
            geprueft, importiert, uebersprungen, fehlgeschlagen = rechnungen_importieren()
        except GraphFehler as exc:
            # Kein Crash des Cron-Laufs nach aussen (siehe interner_eingangsrechnungen_cron) -
            # ein temporaeres Graph-/Netzwerkproblem soll beim naechsten Lauf (1x taeglich,
            # siehe render.yaml) einfach erneut versucht werden, nicht den ganzen Request mit
            # HTTP 500 beantworten.
            self.stderr.write(self.style.ERROR(f"Eingangsrechnungen-Import fehlgeschlagen: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Eingangsrechnungen-Import abgeschlossen: {geprueft} neue Mail(s) geprüft, "
            f"{importiert} Eingangsrechnung(en) angelegt, {uebersprungen} übersprungen "
            f"(kein Beleg/schon vorhanden), {fehlgeschlagen} fehlgeschlagen (siehe Log)."
        ))
