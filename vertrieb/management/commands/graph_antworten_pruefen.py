"""Prüft das Postfach vertrieb@ecko-pack.de per Microsoft Graph auf Kundenantworten zu
automatischen Nachfass-Mails (25.10.2026, auf Wunsch von Björn - "Graph-Antworten").

Wird wie nachfass_pruefen nicht direkt per Cron gegen die SQLite-Datei aufgerufen (die liegt
nur auf der Disk des Web-Service), sondern ueber den internen HTTP-Endpoint
vertrieb.views.interner_graph_antworten_cron, den ein separater Render-Cron-Job per HTTPS
anstoesst (siehe render.yaml). Die eigentliche Logik (Graph-Zugriff, Matching, Aktivität
anlegen) steckt in vertrieb/graph_antworten.py - dieser Befehl ist nur der duenne
Cron-Einstiegspunkt, analog zu nachfass_pruefen.py.
"""

from django.core.management.base import BaseCommand

from vertrieb.graph_antworten import GraphFehler, antworten_pruefen


class Command(BaseCommand):
    help = "Prüft vertrieb@ecko-pack.de per Microsoft Graph auf Antworten zu Nachfass-Mails."

    def handle(self, *args, **options):
        try:
            geprueft, erkannt = antworten_pruefen()
        except GraphFehler as exc:
            # Kein Crash des Cron-Laufs nach aussen (siehe interner_graph_antworten_cron) -
            # ein temporaeres Graph-/Netzwerkproblem soll beim naechsten Lauf (Prüf-Takt,
            # siehe render.yaml) einfach erneut versucht werden, nicht den ganzen Request
            # mit HTTP 500 beantworten.
            self.stderr.write(self.style.ERROR(f"Graph-Antworten-Prüfung fehlgeschlagen: {exc}"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"Graph-Antworten-Prüfung abgeschlossen: {geprueft} offene Nachfassmail(s) "
            f"geprüft, {erkannt} Antwort(en) erkannt."
        ))
