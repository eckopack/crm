# Sicherheits-TODO: Zugangsdaten rotieren

Sammelt Zugangsdaten, die im Chat mit Claude per Screenshot sichtbar wurden und
deshalb vorsichtshalber rotiert (alten Wert löschen, neuen erzeugen, überall
ersetzen) werden sollten. Bewusst gebündelt statt einzeln sofort – Absprache vom
12.10.2026: wird gesammelt, bis Björn Zeit für alle auf einmal hat.

## Offen

(aktuell nichts offen)

## Erledigt

- [x] **GitHub Personal Access Token** (`~/Documents/eckopack-token.txt`, genutzt
  für den Push-Zugriff aufs `eckopack/crm`-Repo). Sichtbar geworden in einem
  Terminal-Screenshot (`cat ~/Documents/eckopack-token.txt`) am 11.10.2026.
  Rotiert am 18.10.2026: alter Fine-grained-Token `eckopack-crm-deploy` gelöscht,
  neuer Token erzeugt und in `~/Documents/eckopack-token.txt` ersetzt (von Björn
  bestätigt).

- [x] **Resend API-Key** (fürs CRM, SMTP-Versand über `DJANGO_EMAIL_HOST_PASSWORD`
  in Render). Sichtbar geworden in einem Resend-Dashboard-Screenshot am 12.10.2026.
  Rotiert am 18.10.2026: alter Key gelöscht, neuer Key erzeugt und in Render beim
  Service `eckopack-crm` als `DJANGO_EMAIL_HOST_PASSWORD` neu eingetragen. Redeploy
  mit neuer Umgebungsvariable über den Render-Deploy-Log bestätigt; ein echter
  Testmailversand zur endgültigen Funktionsbestätigung steht noch aus.
