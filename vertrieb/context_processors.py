"""27.10.2026, auf Wunsch von Björn (zwei MA im Produktionsbericht-Pilot sprechen
Tschechisch/Ukrainisch): stellt die aktive Produktionsbericht-Oberflächensprache alle
Templates als "ma_sprache" zur Verfügung, inkl. base.html (dort erscheint die vereinfachte
MA-Navigation). Liest NUR aus der Session (gesetzt beim Login, siehe
signals.sprache_bei_login_aktivieren) statt die Datenbank bei jedem Request erneut
abzufragen - bewusst kein DB-Zugriff hier, um diesen auf jeder einzelnen Seite zu
vermeiden, nicht nur auf den Produktionsbericht-Seiten."""
from .produktion_sprachen import SESSION_SCHLUESSEL, STANDARDSPRACHE


def ma_sprache(request):
    return {"ma_sprache": request.session.get(SESSION_SCHLUESSEL, STANDARDSPRACHE)}
