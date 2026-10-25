"""Kleine, eigenständige Helfer-Datei (26.10.2026, Produktionsbericht-Freigabe-Workflow) -
bewusst NICHT in views.py oder models.py, weil sowohl views.py (Freigabe-Views) als auch
middleware.py (Zugriffsbeschränkung für die Gruppe "Produktion") denselben Check brauchen
und middleware.py aus Importreihenfolge-Gründen nicht aus views.py importieren soll."""

PRODUKTIONSLEITER_GRUPPE = "Produktionsleiter"
PRODUKTION_GRUPPE = "Produktion"


def ist_produktionsleiter(user):
    """True für Superuser oder Mitglieder der Gruppe "Produktionsleiter" (konkret Bizer/
    Gallenkamp, 25.10.2026 - siehe Produktionsbericht-Moduldoku in models.py). Diese beiden
    Konten müssen nach dem Deploy einmalig im Admin der Gruppe zugeordnet werden, da das
    hier aus dem Code heraus nicht automatisch geschehen kann (keine Kenntnis der genauen
    Produktions-Benutzerkonten zum Zeitpunkt der Migration)."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name=PRODUKTIONSLEITER_GRUPPE).exists()


def ist_nur_produktion(user):
    """True für Mitglieder der Gruppe "Produktion" (MA), die NICHT gleichzeitig
    Produktionsleiter oder Superuser sind - diese Nutzer werden von
    vertrieb.middleware.ProduktionszugriffMiddleware auf die Produktionsbericht-
    Eingabemaske/-liste beschränkt."""
    if not user.is_authenticated or user.is_superuser:
        return False
    if ist_produktionsleiter(user):
        return False
    return user.groups.filter(name=PRODUKTION_GRUPPE).exists()
