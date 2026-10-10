# ECKO-PACK CRM (MVP)

Internes Vertriebs-CRM für ECKO-PACK GmbH. Verwaltet Firmen, Kontakte,
Vertriebs-Pipeline (Deals), Aktivitäten und Angebote – zugeschnitten auf die
Geschäftsbereiche Maschinenbau, Verpackungstechnik, Service, Immobilien und
nachhaltige Verpackungslösungen.

**Status:** MVP für den internen Einsatz bei ECKO-PACK. Kein Mandanten-/SaaS-Betrieb,
kein Fertigungs-/ERP-Modul (siehe „Roadmap" unten – bewusst stufenweises Vorgehen).

## 1. Lokale Installation (zum Testen)

```bash
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py beispieldaten    # legt Admin admin/admin123 + Testdaten an
python manage.py runserver
```

Dann im Browser: http://127.0.0.1:8000/ (Login: admin / admin123 – **danach sofort
Passwort ändern**, unter /admin/ → Benutzer → admin → Passwort).

## 2. Funktionsumfang (MVP)

- **Firmen**: Stammdaten, Geschäftsbereich, Status (Lead/Interessent/Kunde/Lieferant/Inaktiv)
- **Kontakte**: pro Firma, mit Kennzeichnung Hauptansprechpartner
- **Deals (Pipeline)**: Kanban-Board nach Phase, Wert, Wahrscheinlichkeit,
  gewichtete Umsatzprognose
- **Aktivitäten**: Anrufe, E-Mails, Meetings, Aufgaben – mit Fälligkeit und
  Überfällig-Kennzeichnung
- **Angebote**: Nummernkreis ANG-JAHR-NNNN, Positionen mit Menge/Einheit/Preis,
  Druckansicht
- **Dashboard**: offene Pipeline, gewichtete Prognose, anstehende/überfällige Aktivitäten
- Admin-Oberfläche unter `/admin/` für Benutzerverwaltung und Rohdatenzugriff

## 3. Bekannte Grenzen und offene Punkte (bitte vor Produktivnutzung beachten)

- **Single-Tenant**: Das System ist für den internen Einsatz bei ECKO-PACK gebaut,
  nicht für mehrere getrennte Kunden auf einer Installation. Sollte daraus ein
  verkaufbares Produkt werden, ist ein Umbau auf Mandantenfähigkeit (Datenisolation,
  Rechteverwaltung je Mandant) nötig – das ist kein kleiner Nachtrag, sondern
  Architekturarbeit.
- **Keine automatisierten Tests (Unit-/Integrationstests)**: Bisher nur manuelle
  Smoke-Tests (CRUD, Formulare, Login, Kanban-Phasenwechsel). Vor echtem Einsatz mit
  echten Kundendaten sollten zumindest Tests für die Geschäftslogik (Angebotssummen,
  Wahrscheinlichkeiten, Nummernkreis) ergänzt werden.
- **Keine Datensicherung konfiguriert**: SQLite-Datei bzw. Postgres-Datenbank müssen
  regelmäßig gesichert werden (siehe Abschnitt 5). Ohne Backup-Routine ist Datenverlust
  bei Festplattenausfall vollständig.
- **DSGVO**: Kontaktdaten (Namen, E-Mails, Telefonnummern) sind personenbezogene Daten.
  Für den internen Gebrauch reicht in der Regel die übliche Sorgfaltspflicht
  (Zugriffsschutz, Backups, Löschkonzept), bei Erweiterung zu einem Produkt mit
  externen Kunden wird eine Auftragsverarbeitungsvereinbarung und ein
  Datenschutzkonzept nötig – dazu empfiehlt sich anwaltliche/datenschutzrechtliche
  Prüfung, das kann ich nicht ersetzen.
- **Keine E-Mail-Integration**: Aktivitäten werden manuell erfasst, kein automatisches
  Mitschneiden von E-Mail-Verkehr.

## 4. Roadmap (bewusst gestuft, siehe Begründung im Chat)

1. **Phase 1 (dieses MVP)**: CRM intern bei ECKO-PACK im echten Vertriebsalltag testen,
   mindestens 4–6 Wochen, bevor investiert wird in Phase 2.
2. **Phase 2**: Je nach Erfahrung aus Phase 1 – Lagerverwaltung (Artikelstamm,
   Bestände, Wareneingang/-ausgang), Verknüpfung Angebot → Auftrag → Rechnung.
3. **Phase 3**: Fertigungsmodul (Stücklisten, Arbeitspläne, Kapazitätsplanung) – mit
   Abstand der aufwendigste Teil. Hier empfiehlt sich eine erneute Build-vs-Buy-Prüfung,
   da ausgereifte Lösungen (z.B. Odoo Manufacturing) ggf. wirtschaftlicher sind als
   Eigenentwicklung.
4. **Erst bei konkretem Verkaufsvorhaben an Dritte**: Umbau auf Mandantenfähigkeit,
   Abo-Abrechnung, Support-Prozesse, rechtliche Prüfung (AGB, DSGVO/AVV, Haftung).

## 5. Deployment auf einem VPS (Produktivbetrieb)

Empfohlener Stack: Ubuntu-Server + PostgreSQL + Gunicorn + Nginx + systemd.

```bash
# Auf dem Server:
sudo apt install python3-venv postgresql nginx
sudo -u postgres createuser eckopack_crm
sudo -u postgres createdb -O eckopack_crm eckopack_crm

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt psycopg[binary] gunicorn

# Umgebungsvariablen setzen (z.B. in /etc/eckopack_crm.env):
export DJANGO_SECRET_KEY="<zufälliger, langer String>"
export DJANGO_DEBUG=False
export DJANGO_ALLOWED_HOSTS="crm.ecko-pack.de"
export DJANGO_CSRF_TRUSTED_ORIGINS="https://crm.ecko-pack.de"
export DJANGO_HTTPS=True
export DJANGO_DB_ENGINE=postgres
export DJANGO_DB_NAME=eckopack_crm
export DJANGO_DB_USER=eckopack_crm
export DJANGO_DB_PASSWORD="<sicheres Passwort>"
export DJANGO_DB_HOST=localhost

python manage.py migrate
python manage.py collectstatic
python manage.py createsuperuser

gunicorn eckopack_crm.wsgi:application --bind 127.0.0.1:8000
```

Nginx als Reverse-Proxy mit TLS (z.B. via Let's Encrypt/certbot) davorschalten,
Gunicorn über systemd als Service betreiben (nicht manuell im Terminal laufen lassen).

**Backups**: täglicher `pg_dump` auf separaten Speicher (nicht nur auf demselben
Server!), mindestens 7 Tage Historie. Ohne das ist jeder Datenverlust endgültig.

## 6. Projektstruktur

```
eckopack_crm/        Projekt-Settings, URLs
vertrieb/             App: Models, Views, Forms, Templates, Admin
  management/commands/beispieldaten.py   Demo-Daten-Generator
  migrations/          Datenbankschema-Historie
  templates/vertrieb/  HTML-Templates (Bootstrap 5)
requirements.txt
```
