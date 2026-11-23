"""Tests für den automatischen Eingangsrechnungen-Import per Graph/Anthropic (23.11.2026).

Graph- und Anthropic-Zugriff werden durchgehend gemockt - diese Tests laufen ohne Netzwerk
und ohne echte Zugangsdaten. Was hier NICHT getestet wird (bewusst, da nicht lokal prüfbar):
ob die echte RBAC-Rollenzuweisung in Exchange Online rechnung@ tatsächlich freigibt - das
zeigt erst ein echter Lauf gegen Render (siehe Chat 23.11.2026)."""

from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings

from .graph_eingangsrechnungen import (
    ExtraktionsFehler, GraphFehler, rechnungen_importieren,
)
from .models import Eingangsrechnung, Firma

NACHRICHT_BASIS = {
    "id": "msg-1",
    "subject": "Rechnung 12345",
    "receivedDateTime": "2026-11-22T10:00:00Z",
    "from": {"emailAddress": {"address": "buchhaltung@beispiel-lieferant.de", "name": "Beispiel Lieferant"}},
    "hasAttachments": True,
}

ANHANG_BASIS = {"name": "rechnung.pdf", "contentBytes": "ZmFrZS1wZGY="}

EXTRAKTION_BASIS = {
    "typ": "rechnung",
    "lieferant_name": "Beispiel Lieferant GmbH",
    "lieferant_email": "buchhaltung@beispiel-lieferant.de",
    "rechnungsnummer": "RE-2026-001",
    "bestellnummer": None,
    "rechnungsdatum": "2026-11-20",
    "faelligkeitsdatum": "2026-12-04",
    "betrag_netto": 100.00,
    "betrag_brutto": 119.00,
    "mwst_betrag": 19.00,
    "steuersatz_prozent": 19.00,
    "skonto_prozent": 2.0,
    "skonto_tage": 10,
    "zahlungsbedingungen": "14 Tage netto",
    "unsicher": False,
    "begruendung": None,
}


def _patch_graph(nachrichten, anhaenge):
    """Patcht Access-Token/Postfach-Abfrage/Anhang-Abruf; `anhaenge` ist die Anhangsliste für
    JEDE Nachricht (im Testfall reicht eine gemeinsame Liste)."""
    return (
        patch("vertrieb.graph_eingangsrechnungen._access_token", return_value="fake-token"),
        patch("vertrieb.graph_eingangsrechnungen._postfach_rechnungen_seit", return_value=nachrichten),
        patch("vertrieb.graph_eingangsrechnungen._pdf_anhaenge", return_value=anhaenge),
    )


class RechnungenImportierenTests(TestCase):
    def setUp(self):
        self.lieferant = Firma.objects.create(
            name="Beispiel Lieferant GmbH", status="lieferant",
            email="buchhaltung@beispiel-lieferant.de",
        )

    def _lauf(self, nachrichten, anhaenge, extraktion_oder_fehler):
        p_token, p_nachrichten, p_anhaenge = _patch_graph(nachrichten, anhaenge)
        with p_token, p_nachrichten, p_anhaenge:
            if isinstance(extraktion_oder_fehler, Exception):
                with patch("vertrieb.graph_eingangsrechnungen._anthropic_erkennung",
                           side_effect=extraktion_oder_fehler):
                    return rechnungen_importieren()
            with patch("vertrieb.graph_eingangsrechnungen._anthropic_erkennung",
                       return_value=extraktion_oder_fehler):
                return rechnungen_importieren()

    def test_rechnung_wird_mit_bestehendem_lieferanten_angelegt(self):
        geprueft, importiert, uebersprungen, fehlgeschlagen = self._lauf(
            [NACHRICHT_BASIS], [ANHANG_BASIS], EXTRAKTION_BASIS,
        )
        self.assertEqual((geprueft, importiert, uebersprungen, fehlgeschlagen), (1, 1, 0, 0))

        er = Eingangsrechnung.objects.get()
        self.assertEqual(er.lieferant, self.lieferant)
        self.assertEqual(er.rechnungsnummer, "RE-2026-001")
        self.assertEqual(er.status, "zu_pruefen")
        self.assertEqual(er.quelle, "email_import")
        self.assertEqual(er.email_message_id, "msg-1")
        self.assertEqual(er.betrag_brutto, Decimal("119.00"))
        self.assertEqual(er.betrag_netto, Decimal("100.00"))
        self.assertEqual(er.steuersatz, Decimal("19.00"))
        # Kernregel: Sachkonto/Kostenstelle werden NIE automatisch befuellt.
        self.assertEqual(er.sachkonto, "")
        self.assertEqual(er.kostenstelle, "")
        self.assertTrue(er.rechnung_datei.name.endswith(".pdf"))

    def test_unbekannter_lieferant_wird_als_platzhalter_angelegt(self):
        self.lieferant.delete()
        geprueft, importiert, uebersprungen, fehlgeschlagen = self._lauf(
            [NACHRICHT_BASIS], [ANHANG_BASIS], EXTRAKTION_BASIS,
        )
        self.assertEqual(importiert, 1)
        neue_firma = Firma.objects.get()
        self.assertEqual(neue_firma.status, "lieferant")
        self.assertEqual(neue_firma.name, "Beispiel Lieferant GmbH")
        self.assertIn("Automatisch angelegt", neue_firma.notizen)
        er = Eingangsrechnung.objects.get()
        self.assertIn("automatisch neu angelegt", er.notizen)

    def test_kein_beleg_wird_uebersprungen_ohne_datensatz(self):
        extraktion = {**EXTRAKTION_BASIS, "typ": "kein_beleg"}
        geprueft, importiert, uebersprungen, fehlgeschlagen = self._lauf(
            [NACHRICHT_BASIS], [ANHANG_BASIS], extraktion,
        )
        self.assertEqual((importiert, uebersprungen, fehlgeschlagen), (0, 1, 0))
        self.assertFalse(Eingangsrechnung.objects.exists())

    def test_bereits_importierte_mail_wird_nicht_erneut_geprueft(self):
        Eingangsrechnung.objects.create(
            lieferant=self.lieferant, rechnungsnummer="ALT-1",
            rechnungsdatum="2026-11-01", betrag_netto=Decimal("1"), betrag_brutto=Decimal("1"),
            email_message_id="msg-1", quelle="email_import",
        )
        geprueft, importiert, uebersprungen, fehlgeschlagen = self._lauf(
            [NACHRICHT_BASIS], [ANHANG_BASIS], EXTRAKTION_BASIS,
        )
        self.assertEqual((geprueft, importiert, uebersprungen, fehlgeschlagen), (0, 0, 0, 0))
        self.assertEqual(Eingangsrechnung.objects.count(), 1)

    def test_doppelte_rechnungsnummer_wird_als_uebersprungen_gezaehlt(self):
        Eingangsrechnung.objects.create(
            lieferant=self.lieferant, rechnungsnummer="RE-2026-001",
            rechnungsdatum="2026-11-01", betrag_netto=Decimal("1"), betrag_brutto=Decimal("1"),
            email_message_id="irgendeine-andere-nachricht", quelle="manuell",
        )
        geprueft, importiert, uebersprungen, fehlgeschlagen = self._lauf(
            [NACHRICHT_BASIS], [ANHANG_BASIS], EXTRAKTION_BASIS,
        )
        self.assertEqual((geprueft, importiert, uebersprungen, fehlgeschlagen), (1, 0, 1, 0))

    def test_fehlende_rechnungsnummer_zaehlt_als_fehlgeschlagen(self):
        extraktion = {**EXTRAKTION_BASIS, "rechnungsnummer": None}
        geprueft, importiert, uebersprungen, fehlgeschlagen = self._lauf(
            [NACHRICHT_BASIS], [ANHANG_BASIS], extraktion,
        )
        self.assertEqual((importiert, uebersprungen, fehlgeschlagen), (0, 0, 1))
        self.assertFalse(Eingangsrechnung.objects.exists())

    def test_anthropic_fehler_zaehlt_als_fehlgeschlagen_statt_crash(self):
        geprueft, importiert, uebersprungen, fehlgeschlagen = self._lauf(
            [NACHRICHT_BASIS], [ANHANG_BASIS], ExtraktionsFehler("API down"),
        )
        self.assertEqual((importiert, uebersprungen, fehlgeschlagen), (0, 0, 1))

    def test_nachricht_ohne_pdf_anhang_wird_uebersprungen(self):
        geprueft, importiert, uebersprungen, fehlgeschlagen = self._lauf(
            [NACHRICHT_BASIS], [], EXTRAKTION_BASIS,
        )
        self.assertEqual((importiert, uebersprungen, fehlgeschlagen), (0, 1, 0))

    def test_graph_fehler_beim_token_wird_durchgereicht(self):
        with patch("vertrieb.graph_eingangsrechnungen._access_token", side_effect=GraphFehler("kein Zugriff")):
            with self.assertRaises(GraphFehler):
                rechnungen_importieren()


@override_settings(ALLOWED_HOSTS=["testserver"])
class CronEndpointTests(TestCase):
    def test_ohne_secret_verboten(self):
        response = Client().post("/interna/eingangsrechnungen-cron/")
        self.assertEqual(response.status_code, 403)

    @patch.dict("os.environ", {"NACHFASS_CRON_SECRET": "testsecret"})
    def test_falsches_secret_verboten(self):
        response = Client().post(
            "/interna/eingangsrechnungen-cron/", HTTP_X_CRON_SECRET="falsch",
        )
        self.assertEqual(response.status_code, 403)

    @patch.dict("os.environ", {"NACHFASS_CRON_SECRET": "testsecret"})
    @patch("vertrieb.views.call_command")
    def test_richtiges_secret_ruft_command_auf(self, mock_call_command):
        response = Client().post(
            "/interna/eingangsrechnungen-cron/", HTTP_X_CRON_SECRET="testsecret",
        )
        self.assertEqual(response.status_code, 200)
        mock_call_command.assert_called_once_with("eingangsrechnungen_importieren")
