"""
Management-Command zum Anlegen von Beispieldaten für ECKO-PACK CRM.

Nutzung: python manage.py beispieldaten
Legt einen Admin-Benutzer (admin/admin123 – bitte nach dem ersten Login ändern!)
sowie ein paar realistische Beispiel-Firmen/Deals für die Geschäftsbereiche von
ECKO-PACK an, damit das System sofort nachvollziehbar getestet werden kann.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from vertrieb.models import Aktivitaet, Angebot, AngebotPosition, Deal, Firma, Kontakt

User = get_user_model()


class Command(BaseCommand):
    help = "Legt einen Admin-Benutzer und Beispieldaten für ECKO-PACK CRM an."

    def handle(self, *args, **options):
        if not User.objects.filter(username="admin").exists():
            User.objects.create_superuser("admin", "admin@ecko-pack.de", "admin123")
            self.stdout.write(self.style.WARNING(
                "Admin-Benutzer angelegt: admin / admin123 — bitte Passwort nach dem ersten Login ändern!"
            ))
        admin = User.objects.get(username="admin")

        if Firma.objects.exists():
            self.stdout.write("Beispieldaten bereits vorhanden – überspringe.")
            return

        f1 = Firma.objects.create(
            name="Müller Maschinenbau GmbH", geschaeftsbereich="maschinenbau", status="kunde",
            branche_kunde="Automobilzulieferer", ort="Stuttgart", land="Deutschland",
            telefon="0711 1234560", email="einkauf@mueller-maschinenbau.example",
            zustaendiger=admin, notizen="Bestandskunde seit 2022, Wartungsvertrag läuft.",
        )
        f2 = Firma.objects.create(
            name="GrünPack Lebensmittel AG", geschaeftsbereich="nachhaltige_verpackung", status="interessent",
            branche_kunde="Lebensmittelproduktion", ort="Köln", land="Deutschland",
            telefon="0221 9988770", email="projekte@gruenpack.example",
            zustaendiger=admin, notizen="Sucht Alternative zu Plastikverpackungen, erste Gespräche Q3.",
        )
        f3 = Firma.objects.create(
            name="Nordlicht Immobilien Verwaltung", geschaeftsbereich="immobilien", status="lead",
            branche_kunde="Gewerbeimmobilien", ort="Hamburg", land="Deutschland",
            zustaendiger=admin, notizen="Interesse an Serviceverträgen für mehrere Standorte.",
        )

        k1 = Kontakt.objects.create(
            firma=f1, vorname="Sabine", nachname="Keller", position="Leiterin Einkauf",
            email="s.keller@mueller-maschinenbau.example", telefon="0711 1234561",
            ist_hauptansprechpartner=True,
        )
        k2 = Kontakt.objects.create(
            firma=f2, vorname="Jonas", nachname="Reimers", position="Head of Procurement",
            email="j.reimers@gruenpack.example", telefon="0221 9988771",
            ist_hauptansprechpartner=True,
        )
        Kontakt.objects.create(
            firma=f3, vorname="Petra", nachname="Lohmann", position="Objektleitung",
            email="p.lohmann@nordlicht-immobilien.example",
            ist_hauptansprechpartner=True,
        )

        jetzt = timezone.now()

        d1 = Deal.objects.create(
            titel="Wartungsvertrag Fertigungslinie 3", firma=f1, kontakt=k1,
            geschaeftsbereich="service", wert=Decimal("18500.00"), phase="verhandlung",
            wahrscheinlichkeit=70, erwartetes_abschlussdatum=(jetzt + timedelta(days=14)).date(),
            zustaendiger=admin, notizen="Letztes Angebot wird aktuell geprüft.",
        )
        d2 = Deal.objects.create(
            titel="Umstellung auf nachhaltige Verpackung – Pilotlinie", firma=f2, kontakt=k2,
            geschaeftsbereich="nachhaltige_verpackung", wert=Decimal("64000.00"), phase="angebot",
            wahrscheinlichkeit=50, erwartetes_abschlussdatum=(jetzt + timedelta(days=30)).date(),
            zustaendiger=admin, notizen="Muster wurden verschickt, Rückmeldung steht aus.",
        )
        Deal.objects.create(
            titel="Serviceverträge 4 Standorte", firma=f3,
            geschaeftsbereich="immobilien", wert=Decimal("9600.00"), phase="lead",
            wahrscheinlichkeit=10, erwartetes_abschlussdatum=(jetzt + timedelta(days=60)).date(),
            zustaendiger=admin,
        )

        Aktivitaet.objects.create(
            typ="anruf", betreff="Rückruf wegen Vertragskonditionen", datum=jetzt + timedelta(days=1),
            firma=f1, kontakt=k1, deal=d1, zustaendiger=admin,
        )
        Aktivitaet.objects.create(
            typ="meeting", betreff="Präsentation Musterergebnisse", datum=jetzt + timedelta(days=3),
            firma=f2, kontakt=k2, deal=d2, zustaendiger=admin,
        )
        Aktivitaet.objects.create(
            typ="aufgabe", betreff="Angebot nachfassen", datum=jetzt - timedelta(days=2),
            firma=f1, deal=d1, zustaendiger=admin, erledigt=False,
        )

        angebot = Angebot.objects.create(deal=d1, status="versendet", notizen="Zahlbar innerhalb 14 Tagen netto.")
        AngebotPosition.objects.create(
            angebot=angebot, position=1, bezeichnung="Wartung Fertigungslinie 3 – Jahresvertrag",
            menge=1, einheit="pauschal", einzelpreis=Decimal("15000.00"),
        )
        AngebotPosition.objects.create(
            angebot=angebot, position=2, bezeichnung="Ersatzteilpauschale",
            menge=1, einheit="pauschal", einzelpreis=Decimal("3500.00"),
        )

        self.stdout.write(self.style.SUCCESS("Beispieldaten erfolgreich angelegt."))
