# Erstellt von Hand am 26.10.2026 als DATENMIGRATION (kein Schema-Wechsel) - auf Wunsch von
# Björn (Produktionsbericht-Pilot Trinkhalm-L1): legt die beiden Benutzergruppen an, die der
# Freigabe-Workflow braucht (siehe Produktionsbericht-Moduldoku in models.py und
# vertrieb/middleware.py):
#
#   - "Produktion": MA-Konten, technisch auf die Produktionsbericht-Eingabemaske
#     beschränkt (siehe ProduktionszugriffMiddleware). Neue MA-Konten müssen im Admin
#     dieser Gruppe zugeordnet UND mit is_staff=False angelegt werden (damit /admin/
#     für sie ohnehin nicht erreichbar ist).
#   - "Produktionsleiter": darf Produktionsberichte freigeben/ablehnen (siehe
#     .produktionsleiter.ist_produktionsleiter). Björns Entscheidung (25.10.2026): konkret
#     Bizer und Gallenkamp. Diese Migration legt NUR die leere Gruppe an - die beiden
#     bestehenden Benutzerkonten müssen einmalig von Björn selbst im Admin
#     (/admin/auth/group/) zugeordnet werden, da diese Migration die genauen Benutzerkonten
#     im Live-System nicht kennt (keine Annahme über Benutzernamen/IDs).
from django.db import migrations


def vorwaerts(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.get_or_create(name="Produktion")
    Group.objects.get_or_create(name="Produktionsleiter")


def rueckwaerts(apps, schema_editor):
    # Bewusst kein Rückbau: würde ggf. inzwischen zugeordnete Benutzer aus der Gruppe
    # reißen. Eine übrig gebliebene leere Gruppe ist unschädlich.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("vertrieb", "0041_produktionsbericht"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(vorwaerts, rueckwaerts),
    ]
