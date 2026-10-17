from decimal import Decimal

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone


GESCHAEFTSBEREICH_CHOICES = [
    ("maschinenbau", "Maschinenbau"),
    ("verpackungstechnik", "Verpackungstechnik"),
    ("service", "Service"),
    ("immobilien", "Immobilien"),
    ("nachhaltige_verpackung", "Nachhaltige Verpackungslösungen"),
    ("einweg_serviceprodukte", "Einweg-/Serviceprodukte"),
    ("sonstiges", "Sonstiges"),
]

FIRMA_STATUS_CHOICES = [
    ("lead", "Lead"),
    ("interessent", "Interessent"),
    ("kunde", "Kunde"),
    ("lieferant", "Lieferant"),
    ("inaktiv", "Inaktiv"),
]

DEAL_PHASE_CHOICES = [
    ("lead", "Lead"),
    ("qualifiziert", "Qualifiziert"),
    ("angebot", "Angebot erstellt"),
    ("verhandlung", "Verhandlung"),
    ("gewonnen", "Gewonnen"),
    ("verloren", "Verloren"),
]

# Standard-Wahrscheinlichkeit je Phase – wird beim Anlegen als Vorschlag genutzt,
# bleibt aber pro Deal frei editierbar.
PHASE_STANDARD_WAHRSCHEINLICHKEIT = {
    "lead": 10,
    "qualifiziert": 30,
    "angebot": 50,
    "verhandlung": 70,
    "gewonnen": 100,
    "verloren": 0,
}

AKTIVITAET_TYP_CHOICES = [
    ("anruf", "Anruf"),
    ("email", "E-Mail"),
    ("meeting", "Meeting"),
    ("aufgabe", "Aufgabe"),
    ("notiz", "Notiz"),
    ("nachfass", "Nachfass (automatisch)"),
]

ANGEBOT_STATUS_CHOICES = [
    ("entwurf", "Entwurf"),
    ("versendet", "Versendet"),
    ("angenommen", "Angenommen"),
    ("abgelehnt", "Abgelehnt"),
    ("abgelaufen", "Abgelaufen"),
]

EINHEIT_CHOICES = [
    ("stk", "Stück"),
    ("karton", "Karton"),
    ("std", "Stunde"),
    ("tag", "Tag"),
    ("monat", "Monat"),
    ("pauschal", "Pauschal"),
    ("kg", "kg"),
    ("m", "m"),
    ("m2", "m²"),
]

PACKSCHEIN_STATUS_CHOICES = [
    ("offen", "Offen"),
    ("in_arbeit", "In Bearbeitung"),
    ("fertig", "Fertig gepackt"),
    ("versendet", "Versendet"),
]

VERSANDDIENSTLEISTER_CHOICES = [
    ("dhl", "DHL"),
    ("dpd", "DPD"),
    ("gls", "GLS"),
    ("ups", "UPS"),
    ("post", "Deutsche Post"),
    ("abholung", "Selbstabholung"),
    ("sonstiges", "Sonstiges"),
]

# Tracking-Link-Vorlagen fuer die Versand-Bestaetigungsmail (siehe Lieferschein.tracking_url
# unten). STAND 17.10.2026: aus Trainingswissen uebernommen, NICHT live verifiziert (Websuche
# fuer diesen Account deaktiviert) - vor dem ersten echten Kundenversand bitte je einmal mit
# einer echten Sendungsnummer durchklicken und ggf. hier korrigieren.
TRACKING_URL_VORLAGEN = {
    "dhl": "https://www.dhl.de/de/privatkunden/pakete-empfangen/verfolgen.html?piececode={code}",
    "dpd": "https://tracking.dpd.de/status/de_DE/parcel/{code}",
    "ups": "https://www.ups.com/track?loc=de_DE&tracknum={code}",
    "gls": "https://gls-group.eu/DE/de/paket-verfolgen?match={code}",
    "post": "https://www.deutschepost.de/de/s/sendungsverfolgung.html?piececode={code}",
}

LIEFERSCHEIN_STATUS_CHOICES = [
    ("entwurf", "Entwurf"),
    ("versendet", "Versendet/Geliefert"),
]

RECHNUNG_STATUS_CHOICES = [
    ("entwurf", "Entwurf"),
    ("versendet", "Versendet"),
    ("bezahlt", "Bezahlt"),
    ("storniert", "Storniert"),
]

STEUERSATZ_CHOICES = [
    (Decimal("19.00"), "19 %"),
    (Decimal("7.00"), "7 %"),
    (Decimal("0.00"), "0 % (steuerfrei)"),
]

ARTIKEL_STATUS_CHOICES = [
    ("in_vorbereitung", "In Vorbereitung"),
    ("aktiv", "Aktiv"),
    ("auslaufend", "Auslaufend"),
    ("gesperrt", "Gesperrt"),
]


class Firma(models.Model):
    name = models.CharField("Name", max_length=200)
    geschaeftsbereich = models.CharField(
        "Geschäftsbereich (ECKO-PACK)", max_length=30, choices=GESCHAEFTSBEREICH_CHOICES, default="sonstiges"
    )
    status = models.CharField("Status", max_length=20, choices=FIRMA_STATUS_CHOICES, default="lead")
    branche_kunde = models.CharField("Branche des Kunden", max_length=150, blank=True)
    website = models.URLField("Webseite", blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    strasse = models.CharField("Straße/Nr.", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    land = models.CharField("Land", max_length=100, default="Deutschland", blank=True)
    zustaendiger = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Zuständiger Mitarbeiter",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="firmen"
    )
    notizen = models.TextField("Notizen", blank=True)
    externe_id = models.CharField(
        "Externe ID (z.B. aus Lead-Recherche-Liste)", max_length=30, blank=True, db_index=True,
        help_text="Für Abgleich beim wiederholten Import aus einer Excel-Liste, z.B. 'F001'.",
    )
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)
    aktualisiert_am = models.DateTimeField("Aktualisiert am", auto_now=True)

    class Meta:
        verbose_name = "Firma"
        verbose_name_plural = "Firmen"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("vertrieb:firma_detail", args=[self.pk])

    @property
    def adresse_einzeilig(self):
        teile = [t for t in [self.strasse, f"{self.plz} {self.ort}".strip(), self.land] if t and t.strip()]
        return ", ".join(teile)


class Kontakt(models.Model):
    firma = models.ForeignKey(Firma, verbose_name="Firma", on_delete=models.CASCADE, related_name="kontakte")
    vorname = models.CharField("Vorname", max_length=100)
    nachname = models.CharField("Nachname", max_length=100)
    position = models.CharField("Position", max_length=150, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    mobil = models.CharField("Mobil", max_length=50, blank=True)
    ist_hauptansprechpartner = models.BooleanField("Hauptansprechpartner", default=False)
    notizen = models.TextField("Notizen", blank=True)
    externe_id = models.CharField(
        "Externe ID (z.B. aus Lead-Recherche-Liste)", max_length=30, blank=True, db_index=True,
        help_text="Für Abgleich beim wiederholten Import aus einer Excel-Liste, z.B. 'K001'.",
    )
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Kontakt"
        verbose_name_plural = "Kontakte"
        ordering = ["nachname", "vorname"]

    def __str__(self):
        return f"{self.vorname} {self.nachname} ({self.firma.name})"

    def get_absolute_url(self):
        return reverse("vertrieb:kontakt_detail", args=[self.pk])


class Deal(models.Model):
    titel = models.CharField("Titel", max_length=200)
    firma = models.ForeignKey(Firma, verbose_name="Firma", on_delete=models.CASCADE, related_name="deals")
    kontakt = models.ForeignKey(
        Kontakt, verbose_name="Ansprechpartner", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="deals"
    )
    geschaeftsbereich = models.CharField(
        "Geschäftsbereich", max_length=30, choices=GESCHAEFTSBEREICH_CHOICES, default="sonstiges"
    )
    wert = models.DecimalField("Wert (EUR, netto)", max_digits=12, decimal_places=2, default=0)
    potenzial_tonnen = models.DecimalField(
        "Mengenpotenzial (Tonnen)", max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Geschätzte Jahres-/Bezugsmenge in Tonnen, unabhängig vom EUR-Wert (z.B. aus Lead-Recherche).",
    )
    phase = models.CharField("Phase", max_length=20, choices=DEAL_PHASE_CHOICES, default="lead")
    wahrscheinlichkeit = models.PositiveSmallIntegerField("Wahrscheinlichkeit (%)", default=10)
    erwartetes_abschlussdatum = models.DateField("Erwartetes Abschlussdatum", null=True, blank=True)
    zustaendiger = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Zuständiger Mitarbeiter",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="deals"
    )
    verloren_grund = models.CharField("Grund (bei Verloren)", max_length=300, blank=True)
    notizen = models.TextField("Notizen", blank=True)
    externe_id = models.CharField(
        "Externe ID (z.B. aus Lead-Recherche-Liste)", max_length=30, blank=True, db_index=True,
        help_text="Für Abgleich beim wiederholten Import aus einer Excel-Liste, z.B. 'L001'.",
    )
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)
    aktualisiert_am = models.DateTimeField("Aktualisiert am", auto_now=True)

    class Meta:
        verbose_name = "Deal"
        verbose_name_plural = "Deals"
        ordering = ["-erstellt_am"]

    def __str__(self):
        return f"{self.titel} – {self.firma.name}"

    def get_absolute_url(self):
        return reverse("vertrieb:deal_detail", args=[self.pk])

    @property
    def gewichteter_wert(self):
        return self.wert * self.wahrscheinlichkeit / 100

    @property
    def ist_offen(self):
        return self.phase not in ("gewonnen", "verloren")


class Aktivitaet(models.Model):
    typ = models.CharField("Typ", max_length=20, choices=AKTIVITAET_TYP_CHOICES, default="aufgabe")
    betreff = models.CharField("Betreff", max_length=200)
    beschreibung = models.TextField("Beschreibung", blank=True)
    datum = models.DateTimeField("Datum/Fällig", default=timezone.now)
    erledigt = models.BooleanField("Erledigt", default=False)
    firma = models.ForeignKey(
        Firma, verbose_name="Firma", null=True, blank=True, on_delete=models.CASCADE, related_name="aktivitaeten"
    )
    kontakt = models.ForeignKey(
        Kontakt, verbose_name="Kontakt", null=True, blank=True, on_delete=models.CASCADE, related_name="aktivitaeten"
    )
    deal = models.ForeignKey(
        Deal, verbose_name="Deal", null=True, blank=True, on_delete=models.CASCADE, related_name="aktivitaeten"
    )
    zustaendiger = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Zuständiger Mitarbeiter",
        null=True, blank=True, on_delete=models.SET_NULL, related_name="aktivitaeten"
    )
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Aktivität"
        verbose_name_plural = "Aktivitäten"
        ordering = ["datum"]

    def __str__(self):
        return self.betreff

    def get_absolute_url(self):
        return reverse("vertrieb:aktivitaet_detail", args=[self.pk])

    @property
    def ist_ueberfaellig(self):
        return (not self.erledigt) and self.datum < timezone.now()


class Angebot(models.Model):
    nummer = models.CharField("Angebotsnummer", max_length=30, unique=True, blank=True)
    deal = models.ForeignKey(Deal, verbose_name="Deal", on_delete=models.CASCADE, related_name="angebote")
    datum = models.DateField("Datum", default=timezone.now)
    gueltig_bis = models.DateField("Gültig bis", null=True, blank=True)
    status = models.CharField("Status", max_length=20, choices=ANGEBOT_STATUS_CHOICES, default="entwurf")
    notizen = models.TextField("Notizen/Konditionen", blank=True)
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Angebot"
        verbose_name_plural = "Angebote"
        ordering = ["-datum", "-nummer"]

    def __str__(self):
        return self.nummer or f"Angebot (Entwurf) – {self.deal}"

    def get_absolute_url(self):
        return reverse("vertrieb:angebot_detail", args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.nummer:
            jahr = (self.datum or timezone.now().date()).year
            letzte = Angebot.objects.filter(nummer__startswith=f"ANG-{jahr}-").order_by("-nummer").first()
            if letzte and letzte.nummer.split("-")[-1].isdigit():
                naechste = int(letzte.nummer.split("-")[-1]) + 1
            else:
                naechste = 1
            self.nummer = f"ANG-{jahr}-{naechste:04d}"
        super().save(*args, **kwargs)

    @property
    def gesamtsumme(self):
        return sum((p.gesamtpreis for p in self.positionen.all()), start=0)


class AngebotPosition(models.Model):
    angebot = models.ForeignKey(Angebot, on_delete=models.CASCADE, related_name="positionen")
    artikel = models.ForeignKey(
        "Artikel", verbose_name="Artikel", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="angebotpositionen",
    )
    position = models.PositiveIntegerField("Pos.", default=1)
    bezeichnung = models.CharField("Bezeichnung", max_length=300)
    menge = models.DecimalField("Menge", max_digits=10, decimal_places=2, default=1)
    einheit = models.CharField("Einheit", max_length=10, choices=EINHEIT_CHOICES, default="stk")
    # decimal_places=5, nicht 2: bei Stückgut-Artikeln (z. B. Trinkhalme) liegt der
    # Nettopreis je Stück im Bruchteilscent-Bereich (z. B. 0,01298 EUR) - bei nur 2
    # Nachkommastellen würde der Gesamtpreis bei großen Mengen spürbar verfälscht
    # (300.000 Stk * gerundet 0,01 statt 0,01298 EUR = 3.000 statt 3.894 EUR).
    einzelpreis = models.DecimalField("Einzelpreis (EUR, netto)", max_digits=14, decimal_places=5, default=0)

    class Meta:
        verbose_name = "Angebotsposition"
        verbose_name_plural = "Angebotspositionen"
        ordering = ["position"]

    def __str__(self):
        return self.bezeichnung

    @property
    def gesamtpreis(self):
        return self.menge * self.einzelpreis


class Packschein(models.Model):
    """Internes Kommissionier-/Packdokument fürs Lagerpersonal.

    Kein Kunden-/Briefpapierbezug – dient der Vorbereitung im Lager, bevor der
    (kundenseitige) Lieferschein erstellt wird. Positionen lassen sich einzeln
    als „gepackt“ abhaken, sowohl in der CRM-Oberfläche als auch handschriftlich
    auf dem Ausdruck.
    """
    nummer = models.CharField("Packscheinnummer", max_length=30, unique=True, blank=True)
    deal = models.ForeignKey(Deal, verbose_name="Deal", on_delete=models.CASCADE, related_name="packscheine")
    angebot = models.ForeignKey(
        Angebot, verbose_name="Angebot", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="packscheine"
    )
    datum = models.DateField("Kommissionierdatum", default=timezone.now)
    kommissionierer = models.CharField("Kommissioniert von", max_length=150, blank=True)
    status = models.CharField("Status", max_length=20, choices=PACKSCHEIN_STATUS_CHOICES, default="offen")
    notizen = models.TextField("Notizen (z. B. Lagerplatz, Besonderheiten)", blank=True)
    ist_musterversand = models.BooleanField(
        "Musterversand", default=False,
        help_text=(
            "Markiert diesen Packschein als automatisierten Musterkarton-Versand an einen Lead "
            "(löst beim Versand die Bestätigungsmail und die wöchentliche Nachfass-Automatik aus)."
        ),
    )
    versanddienstleister = models.CharField(
        "Versanddienstleister", max_length=20, choices=VERSANDDIENSTLEISTER_CHOICES, blank=True
    )
    trackingnummer = models.CharField("Trackingnummer", max_length=50, blank=True)
    versendet_am = models.DateField("Versendet am", null=True, blank=True)
    bestaetigungsmail_gesendet_am = models.DateTimeField(
        "Bestätigungsmail gesendet am", null=True, blank=True
    )
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Packschein"
        verbose_name_plural = "Packscheine"
        ordering = ["-datum", "-nummer"]

    def __str__(self):
        return self.nummer or f"Packschein (Entwurf) – {self.deal}"

    def get_absolute_url(self):
        return reverse("vertrieb:packschein_detail", args=[self.pk])

    @property
    def vollstaendig_gepackt(self):
        positionen = list(self.positionen.all())
        return bool(positionen) and all(p.gepackt for p in positionen)

    def save(self, *args, **kwargs):
        if not self.nummer:
            jahr = (self.datum or timezone.now().date()).year
            letzter = Packschein.objects.filter(nummer__startswith=f"PACK-{jahr}-").order_by("-nummer").first()
            if letzter and letzter.nummer.split("-")[-1].isdigit():
                naechste = int(letzter.nummer.split("-")[-1]) + 1
            else:
                naechste = 1
            self.nummer = f"PACK-{jahr}-{naechste:04d}"
        super().save(*args, **kwargs)


class PackscheinPosition(models.Model):
    packschein = models.ForeignKey(Packschein, on_delete=models.CASCADE, related_name="positionen")
    artikel = models.ForeignKey(
        "Artikel", verbose_name="Artikel", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="packscheinpositionen",
    )
    position = models.PositiveIntegerField("Pos.", default=1)
    bezeichnung = models.CharField("Bezeichnung", max_length=300)
    menge = models.DecimalField("Menge", max_digits=10, decimal_places=2, default=1)
    einheit = models.CharField("Einheit", max_length=10, choices=EINHEIT_CHOICES, default="stk")
    gepackt = models.BooleanField("Gepackt", default=False)

    class Meta:
        verbose_name = "Packscheinposition"
        verbose_name_plural = "Packscheinpositionen"
        ordering = ["position"]

    def __str__(self):
        return self.bezeichnung


class Lieferschein(models.Model):
    nummer = models.CharField("Lieferscheinnummer", max_length=30, unique=True, blank=True)
    deal = models.ForeignKey(Deal, verbose_name="Deal", on_delete=models.CASCADE, related_name="lieferscheine")
    angebot = models.ForeignKey(
        Angebot, verbose_name="Angebot", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="lieferscheine"
    )
    packschein = models.ForeignKey(
        Packschein, verbose_name="Packschein", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="lieferscheine"
    )
    datum = models.DateField("Lieferdatum", default=timezone.now)
    status = models.CharField("Status", max_length=20, choices=LIEFERSCHEIN_STATUS_CHOICES, default="entwurf")
    # Versand-/Tracking-Erfassung (17.10.2026, auf Wunsch von Björn): bewusst dieselben
    # Feldnamen/Choices wie beim Packschein (siehe oben) statt neuer Begriffe, damit das CRM
    # durchgängig bleibt. Erst wenn trackingnummer gesetzt ist, gilt eine Rechnung zu diesem
    # Lieferschein als erzeugbar (siehe views.rechnung_erstellen) und die Nachfass-Kette des
    # zugehoerigen Deals als beendet (siehe management/commands/nachfass_pruefen.py) - die
    # Eingabe des Trackingcodes ist damit der maßgebliche "jetzt ist wirklich versendet"-Moment,
    # nicht das Status-Feld oben (das bleibt manuell/for Anzeige, kann aber durch die Eingabe
    # ueberschrieben werden, siehe save()).
    versanddienstleister = models.CharField(
        "Versanddienstleister", max_length=20, choices=VERSANDDIENSTLEISTER_CHOICES, blank=True
    )
    trackingnummer = models.CharField("Trackingnummer", max_length=50, blank=True)
    versendet_am = models.DateField("Versendet am", null=True, blank=True)
    versand_erfasst_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Versand erfasst von", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+", editable=False,
    )
    bestaetigungsmail_gesendet_am = models.DateTimeField(
        "Versand-Bestätigungsmail an Kunde gesendet am", null=True, blank=True, editable=False,
    )
    notizen = models.TextField("Notizen", blank=True)
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Lieferschein"
        verbose_name_plural = "Lieferscheine"
        ordering = ["-datum", "-nummer"]

    def __str__(self):
        return self.nummer or f"Lieferschein (Entwurf) – {self.deal}"

    def get_absolute_url(self):
        return reverse("vertrieb:lieferschein_detail", args=[self.pk])

    @property
    def tatsaechlich_versendet(self):
        """True, sobald ein Trackingcode hinterlegt ist - siehe Kommentar oben am Feld."""
        return bool(self.trackingnummer)

    @property
    def tracking_url(self):
        if not self.trackingnummer or not self.versanddienstleister:
            return ""
        vorlage = TRACKING_URL_VORLAGEN.get(self.versanddienstleister)
        if not vorlage:
            return ""
        from urllib.parse import quote
        return vorlage.format(code=quote(self.trackingnummer))

    def save(self, *args, **kwargs):
        if not self.nummer:
            jahr = (self.datum or timezone.now().date()).year
            letzter = Lieferschein.objects.filter(nummer__startswith=f"LS-{jahr}-").order_by("-nummer").first()
            if letzter and letzter.nummer.split("-")[-1].isdigit():
                naechste = int(letzter.nummer.split("-")[-1]) + 1
            else:
                naechste = 1
            self.nummer = f"LS-{jahr}-{naechste:04d}"
        super().save(*args, **kwargs)


class LieferscheinPosition(models.Model):
    lieferschein = models.ForeignKey(Lieferschein, on_delete=models.CASCADE, related_name="positionen")
    artikel = models.ForeignKey(
        "Artikel", verbose_name="Artikel", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="lieferscheinpositionen",
    )
    position = models.PositiveIntegerField("Pos.", default=1)
    bezeichnung = models.CharField("Bezeichnung", max_length=300)
    menge = models.DecimalField("Menge", max_digits=10, decimal_places=2, default=1)
    einheit = models.CharField("Einheit", max_length=10, choices=EINHEIT_CHOICES, default="stk")

    class Meta:
        verbose_name = "Lieferscheinposition"
        verbose_name_plural = "Lieferscheinpositionen"
        ordering = ["position"]

    def __str__(self):
        return self.bezeichnung


class Rechnung(models.Model):
    nummer = models.CharField("Rechnungsnummer", max_length=30, unique=True, blank=True)
    deal = models.ForeignKey(Deal, verbose_name="Deal", on_delete=models.CASCADE, related_name="rechnungen")
    angebot = models.ForeignKey(
        Angebot, verbose_name="Angebot", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="rechnungen"
    )
    lieferschein = models.ForeignKey(
        Lieferschein, verbose_name="Lieferschein", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="rechnungen"
    )
    rechnungsdatum = models.DateField("Rechnungsdatum", default=timezone.now)
    leistungsdatum = models.DateField(
        "Liefer-/Leistungsdatum", null=True, blank=True,
        help_text="Falls abweichend vom Rechnungsdatum; Pflichtangabe nach §14 UStG.",
    )
    zahlungsziel_tage = models.PositiveSmallIntegerField("Zahlungsziel (Tage, netto)", default=7)
    status = models.CharField("Status", max_length=20, choices=RECHNUNG_STATUS_CHOICES, default="entwurf")
    notizen = models.TextField("Notizen/Zahlungshinweis", blank=True)
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Rechnung"
        verbose_name_plural = "Rechnungen"
        ordering = ["-rechnungsdatum", "-nummer"]

    def __str__(self):
        return self.nummer or f"Rechnung (Entwurf) – {self.deal}"

    def get_absolute_url(self):
        return reverse("vertrieb:rechnung_detail", args=[self.pk])

    def save(self, *args, **kwargs):
        if not self.nummer:
            jahr = (self.rechnungsdatum or timezone.now().date()).year
            letzte = Rechnung.objects.filter(nummer__startswith=f"RE-{jahr}-").order_by("-nummer").first()
            if letzte and letzte.nummer.split("-")[-1].isdigit():
                naechste = int(letzte.nummer.split("-")[-1]) + 1
            else:
                naechste = 1
            self.nummer = f"RE-{jahr}-{naechste:04d}"
        super().save(*args, **kwargs)

    @property
    def faelligkeitsdatum(self):
        from datetime import timedelta
        basis = self.rechnungsdatum or timezone.now().date()
        return basis + timedelta(days=self.zahlungsziel_tage)

    @property
    def ist_bearbeitbar(self):
        return self.status == "entwurf"

    @property
    def nettosumme(self):
        return sum((p.nettobetrag for p in self.positionen.all()), start=Decimal("0"))

    @property
    def steuerbetrag(self):
        return sum((p.steuerbetrag for p in self.positionen.all()), start=Decimal("0"))

    @property
    def bruttosumme(self):
        return self.nettosumme + self.steuerbetrag

    @property
    def steuer_aufschluesselung(self):
        """Liste von (Steuersatz, Netto-Bemessungsgrundlage, Steuerbetrag) je verwendetem Satz –
        so wie §14 UStG den Steuerausweis auf der Rechnung verlangt."""
        gruppen = {}
        for p in self.positionen.all():
            netto, steuer = gruppen.get(p.steuersatz, (Decimal("0"), Decimal("0")))
            gruppen[p.steuersatz] = (netto + p.nettobetrag, steuer + p.steuerbetrag)
        return [(satz, *werte) for satz, werte in sorted(gruppen.items())]


class RechnungPosition(models.Model):
    rechnung = models.ForeignKey(Rechnung, on_delete=models.CASCADE, related_name="positionen")
    artikel = models.ForeignKey(
        "Artikel", verbose_name="Artikel", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="rechnungpositionen",
    )
    position = models.PositiveIntegerField("Pos.", default=1)
    bezeichnung = models.CharField("Bezeichnung", max_length=300)
    menge = models.DecimalField("Menge", max_digits=10, decimal_places=2, default=1)
    einheit = models.CharField("Einheit", max_length=10, choices=EINHEIT_CHOICES, default="stk")
    # decimal_places=5: siehe Kommentar bei AngebotPosition.einzelpreis.
    einzelpreis = models.DecimalField("Einzelpreis (EUR, netto)", max_digits=14, decimal_places=5, default=0)
    steuersatz = models.DecimalField(
        "USt-Satz (%)", max_digits=4, decimal_places=2, choices=STEUERSATZ_CHOICES, default=Decimal("19.00")
    )

    class Meta:
        verbose_name = "Rechnungsposition"
        verbose_name_plural = "Rechnungspositionen"
        ordering = ["position"]

    def __str__(self):
        return self.bezeichnung

    @property
    def nettobetrag(self):
        return self.menge * self.einzelpreis

    @property
    def steuerbetrag(self):
        return (self.nettobetrag * self.steuersatz / Decimal("100")).quantize(Decimal("0.01"))

    @property
    def bruttobetrag(self):
        return self.nettobetrag + self.steuerbetrag


MATERIALTYP_CHOICES = [
    ("handelsware", "Handelsware (zugekauft, keine eigene Produktion)"),
    ("rohmaterial", "Rohmaterial"),
    ("fertigware", "Fertigware (Eigenproduktion)"),
]


class Artikel(models.Model):
    """Artikelstamm: ein Eintrag je verkauftem/gelagertem Artikel.

    Wird bei Angeboten, Packscheinen, Lieferscheinen und Rechnungen als Positionsquelle
    genutzt (Bezeichnung/Einheit/Preis werden beim Auswählen übernommen, bleiben aber je
    Position frei überschreibbar) und zeigt den Lagerbestand im CRM an.

    Materialwirtschaft (16.10.2026, Phase A - reines Datenmodell, siehe Rezeptur/Charge/
    Lagerbewegung unten): materialtyp unterscheidet, ob ein Artikel eine zugekaufte
    Handelsware ist (Default - trifft heute auf praktisch alle importierten LUAMO-Artikel
    zu, die über einen Lieferanten bezogen werden), ein Rohmaterial, oder eine im eigenen
    Betrieb aus Rohmaterial gefertigte Fertigware. lagerbestand_aktuell bleibt in dieser
    Phase bewusst unverändert (weiterhin frei editierbar / aus dem Excel-Import gesetzt) -
    die Umstellung auf eine aus Lagerbewegungen berechnete Zahl ist ein späterer,
    eigenständiger Schritt, sobald Bewegungen für die betroffenen Artikel tatsächlich
    produktiv erfasst werden.

    Mengenstaffelpreise (z. B. "ab 10.000 Stück günstigerer Preis je Stück") werden NICHT
    hier auf dem Artikel selbst gepflegt, sondern als separate Preisstaffel-Einträge
    (siehe unten) - ein Artikel kann 0 bis n Staffeln haben. Gibt es keine Staffel für die
    bestellte Menge, gilt der Flatrate-Preis in `verkaufspreis`.
    """
    artikelnummer = models.CharField("Artikelnummer", max_length=50, unique=True)
    bezeichnung = models.CharField("Bezeichnung", max_length=300)
    beschreibung = models.TextField("Beschreibung", blank=True)
    geschaeftsbereich = models.CharField(
        "Geschäftsbereich (ECKO-PACK)", max_length=30, choices=GESCHAEFTSBEREICH_CHOICES,
        default="einweg_serviceprodukte",
    )
    warengruppe = models.CharField(
        "Warengruppe/Serie", max_length=100, blank=True,
        help_text="Feinere Produktkategorie innerhalb des Geschäftsbereichs, z. B. "
                   "\"Trinkhalme\", \"Großbesteck\", \"Kleinbesteck\", \"Muster\".",
    )
    materialtyp = models.CharField(
        "Materialtyp", max_length=20, choices=MATERIALTYP_CHOICES, default="handelsware",
        help_text="Für Rezeptur und Lagerbewegungen (Materialwirtschaft) relevant bei "
                   "Rohmaterial/Fertigware; Handelsware wird weiterhin nur über den "
                   "Lagerbestand-Wert geführt.",
    )
    einheit = models.CharField("Einheit", max_length=10, choices=EINHEIT_CHOICES, default="stk")
    verkaufspreis = models.DecimalField(
        "Verkaufspreis (EUR, netto)", max_digits=14, decimal_places=5, null=True, blank=True,
        help_text="Flatrate-Preis je Einheit. Pflicht, falls keine Preisstaffeln hinterlegt sind.",
    )
    ust_satz = models.DecimalField(
        "USt-Satz (%)", max_digits=4, decimal_places=2, choices=STEUERSATZ_CHOICES, default=Decimal("19.00")
    )
    einkaufspreis = models.DecimalField(
        "Einkaufspreis (EUR, netto)", max_digits=14, decimal_places=5, null=True, blank=True,
        help_text="Optional, aber Voraussetzung für Rohertrag/Deckungsbeitrag je Artikel.",
    )
    lagerbestand_aktuell = models.DecimalField(
        "Lagerbestand aktuell", max_digits=12, decimal_places=2, null=True, blank=True
    )
    mindestbestand = models.DecimalField(
        "Mindestbestand (Meldebestand)", max_digits=12, decimal_places=2, null=True, blank=True
    )
    verpackungseinheit_stk = models.PositiveIntegerField(
        "Verpackungseinheit (Stück je Gebinde)", null=True, blank=True,
        help_text="Z. B. 500 bei einem 500er-Schlauchbeutel oder 150 bei einem 150er-Karton.",
    )
    lagerort = models.CharField("Lagerort", max_length=100, blank=True)
    lieferant = models.CharField("Lieferant", max_length=200, blank=True)
    status = models.CharField(
        "Status", max_length=30, choices=ARTIKEL_STATUS_CHOICES, default="in_vorbereitung", blank=True,
        help_text="Rein informativ - verhindert aktuell NICHT die Verwendung in Angeboten/Packscheinen.",
    )
    notizen = models.TextField("Notizen", blank=True)
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)
    aktualisiert_am = models.DateTimeField("Zuletzt aktualisiert", auto_now=True)

    class Meta:
        verbose_name = "Artikel"
        verbose_name_plural = "Artikel"
        ordering = ["artikelnummer"]

    def __str__(self):
        return f"{self.artikelnummer} – {self.bezeichnung}"

    def get_absolute_url(self):
        return reverse("vertrieb:artikel_detail", args=[self.pk])

    @property
    def unter_mindestbestand(self):
        if self.lagerbestand_aktuell is None or self.mindestbestand is None:
            return False
        return self.lagerbestand_aktuell < self.mindestbestand

    def preis_fuer_menge(self, menge):
        """Liefert den Nettopreis je Einheit für eine bestellte Menge: die höchste
        Preisstaffel, deren Mindestmenge die bestellte Menge nicht übersteigt - sonst
        der Flatrate-Verkaufspreis."""
        if menge is not None:
            staffel = self.preisstaffeln.filter(ab_menge__lte=menge).order_by("-ab_menge").first()
            if staffel is not None:
                return staffel.preis_netto
        return self.verkaufspreis


class Preisstaffel(models.Model):
    """Eine Mengenstaffel-Preisstufe eines Artikels (z. B. "ab 10.000 Stück: 0,045 EUR/Stk")."""
    artikel = models.ForeignKey(Artikel, on_delete=models.CASCADE, related_name="preisstaffeln")
    ab_menge = models.PositiveIntegerField("Ab Menge (Stück/Einheit)")
    preis_netto = models.DecimalField("Preis je Einheit (EUR, netto)", max_digits=14, decimal_places=5)

    class Meta:
        verbose_name = "Preisstaffel"
        verbose_name_plural = "Preisstaffeln"
        ordering = ["-ab_menge"]
        unique_together = [("artikel", "ab_menge")]

    def __str__(self):
        return f"{self.artikel.artikelnummer}: ab {self.ab_menge} → {self.preis_netto} €"


# ---------------------------------------------------------------------------
# Materialwirtschaft (16.10.2026, Phase A)
#
# Umfang laut Björns Vorgaben vom 16.10.2026: Rohmaterial/Fertigprodukt-Beziehung ist
# überwiegend einfach (1:1 oder nah dran) - Rezeptur bildet trotzdem mehrere Zeilen pro
# Fertigprodukt ab, falls doch mal mehr als ein Rohmaterial hineinfließt. Ein zentrales
# Lager (keine Mehrstandort-Bestände nötig). Chargen-/MHD-Pflicht JA, deshalb eigenes
# Charge-Modell statt einer reinen Mengenbuchung. Lagerbewegung ist ein Journal: wird nie
# editiert oder gelöscht (dieselbe Überlegung wie bei Rechnungen/GoBD, siehe Chat-Verlauf
# 16.10.2026) - Korrekturen entstehen durch eine neue, gegenläufige Buchung, nicht durch
# Ändern einer bestehenden Zeile. Phase A legt nur das Datenmodell + Admin an, ohne eigene
# Bedienoberfläche - Wareneingang-Erfassung (Phase B), Produktionsbuchung (Phase C) und
# automatische Buchung beim Lieferschein-Versand (Phase D) folgen als eigene Schritte.
# ---------------------------------------------------------------------------

class Rezeptur(models.Model):
    """Verknüpft ein Fertigprodukt mit dem/den Rohmaterial(ien), aus dem es entsteht,
    plus Umrechnungsfaktor (z. B. "1 Stück Fertigprodukt verbraucht 0,05 kg Rohmaterial
    X"). Bewusst als Zeilen-Tabelle (nicht ein einzelnes FK-Feld am Artikel), damit auch
    ein Fertigprodukt mit mehr als einem Rohmaterial abbildbar ist, auch wenn das laut
    Björn aktuell der Ausnahmefall ist."""
    fertigprodukt = models.ForeignKey(
        Artikel, verbose_name="Fertigprodukt", on_delete=models.CASCADE,
        related_name="rezeptur_zeilen", limit_choices_to={"materialtyp": "fertigware"},
    )
    rohmaterial = models.ForeignKey(
        Artikel, verbose_name="Rohmaterial", on_delete=models.PROTECT,
        related_name="verwendet_in_rezepturen", limit_choices_to={"materialtyp": "rohmaterial"},
    )
    menge_je_einheit = models.DecimalField(
        "Menge Rohmaterial je Einheit Fertigprodukt", max_digits=12, decimal_places=5,
        help_text="In der Einheit des Rohmaterials, je einer Einheit des Fertigprodukts.",
    )
    notizen = models.CharField("Notizen", max_length=300, blank=True)

    class Meta:
        verbose_name = "Rezeptur-Zeile"
        verbose_name_plural = "Rezeptur-Zeilen"
        ordering = ["fertigprodukt__artikelnummer", "rohmaterial__artikelnummer"]
        unique_together = [("fertigprodukt", "rohmaterial")]

    def __str__(self):
        return (f"{self.fertigprodukt.artikelnummer}: {self.menge_je_einheit} × "
                f"{self.rohmaterial.artikelnummer}")

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.fertigprodukt_id and self.rohmaterial_id and self.fertigprodukt_id == self.rohmaterial_id:
            raise ValidationError("Ein Artikel kann nicht sein eigenes Rohmaterial sein.")


class Charge(models.Model):
    """Eine konkrete Wareneingangs-Charge eines Artikels (Rohmaterial oder Fertigware) mit
    eigenem Mindesthaltbarkeitsdatum und eigenem Restbestand. Lagerbewegungen verbrauchen
    Chargen in der Reihenfolge der Meta.ordering (älteste zuerst = FIFO)."""
    artikel = models.ForeignKey(Artikel, verbose_name="Artikel", on_delete=models.PROTECT, related_name="chargen")
    chargennummer = models.CharField("Chargennummer", max_length=100, blank=True)
    wareneingang_datum = models.DateField("Wareneingangsdatum", default=timezone.now)
    mindesthaltbarkeitsdatum = models.DateField("Mindesthaltbarkeitsdatum (MHD)", null=True, blank=True)
    lieferant = models.CharField("Lieferant", max_length=200, blank=True)
    menge_eingang = models.DecimalField(
        "Menge bei Wareneingang", max_digits=14, decimal_places=3,
        help_text="Historischer Wert, ändert sich nie - nur zur Dokumentation der Ursprungsmenge.",
    )
    bestand_aktuell = models.DecimalField(
        "Restbestand dieser Charge", max_digits=14, decimal_places=3, default=Decimal("0"),
        help_text="Startet bei 0 und wird ausschließlich durch Lagerbewegungen fortgeschrieben "
                   "(siehe Lagerbewegung.save()) - nicht von Hand pflegen. Die erste Buchung auf "
                   "eine neue Charge ist üblicherweise eine 'wareneingang'-Bewegung in Höhe von "
                   "menge_eingang; Charge und Bewegung getrennt zu halten verhindert Doppelzählung.",
    )
    notizen = models.TextField("Notizen", blank=True)
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Charge"
        verbose_name_plural = "Chargen"
        ordering = ["wareneingang_datum", "erstellt_am"]

    def __str__(self):
        bezeichnung = self.chargennummer or f"Charge #{self.pk}"
        return f"{self.artikel.artikelnummer} – {bezeichnung}"

    @property
    def abgelaufen(self):
        if not self.mindesthaltbarkeitsdatum:
            return False
        return self.mindesthaltbarkeitsdatum < timezone.now().date()


BEWEGUNGSTYP_CHOICES = [
    ("wareneingang", "Wareneingang"),
    ("produktion_verbrauch", "Materialverbrauch (Produktion)"),
    ("produktion_zugang", "Fertigwarenzugang (Produktion)"),
    ("warenausgang", "Warenausgang (Versand)"),
    ("ruecklieferung", "Rücklieferung/Retoure"),
    ("korrektur", "Korrektur/Inventur"),
]


class Lagerbewegung(models.Model):
    """Unveränderliches Bewegungsjournal für Materialwirtschaft. Wird NIE nachträglich
    editiert oder gelöscht (siehe Moduldoku oben) - im Admin deshalb nur lesbar/anlegbar,
    keine Änderung/Löschung bestehender Zeilen. Jede Bewegung aktualisiert beim Anlegen
    (siehe save()) den Restbestand der zugehörigen Charge, falls eine angegeben ist."""
    artikel = models.ForeignKey(Artikel, verbose_name="Artikel", on_delete=models.PROTECT, related_name="bewegungen")
    charge = models.ForeignKey(
        Charge, verbose_name="Charge", on_delete=models.PROTECT, null=True, blank=True,
        related_name="bewegungen", help_text="Optional - z. B. für Korrekturen ohne Chargenbezug leer lassen.",
    )
    bewegungstyp = models.CharField("Bewegungstyp", max_length=30, choices=BEWEGUNGSTYP_CHOICES)
    menge = models.DecimalField(
        "Menge", max_digits=14, decimal_places=3,
        help_text="Positiv = Zugang, negativ = Abgang.",
    )
    lieferschein = models.ForeignKey(
        Lieferschein, verbose_name="Lieferschein (bei Warenausgang)", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="lagerbewegungen",
    )
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Erfasst von", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    datum = models.DateTimeField("Datum/Zeit", auto_now_add=True)
    notizen = models.TextField("Notizen", blank=True)

    class Meta:
        verbose_name = "Lagerbewegung"
        verbose_name_plural = "Lagerbewegungen"
        ordering = ["-datum", "-pk"]

    def __str__(self):
        vorzeichen = "+" if self.menge >= 0 else ""
        return f"{self.artikel.artikelnummer}: {vorzeichen}{self.menge} ({self.get_bewegungstyp_display()})"

    def save(self, *args, **kwargs):
        ist_neu = self._state.adding
        super().save(*args, **kwargs)
        if ist_neu and self.charge_id:
            Charge.objects.filter(pk=self.charge_id).update(
                bestand_aktuell=models.F("bestand_aktuell") + self.menge
            )

    def delete(self, *args, **kwargs):
        raise NotImplementedError(
            "Lagerbewegungen werden nie gelöscht - für Korrekturen eine neue, "
            "gegenläufige Lagerbewegung anlegen."
        )


MUSTERBOX_NACHFASS_WOCHEN = 8

MUSTERBOX_NACHFASS_ENDE_CHOICES = [
    ("angebot", "Deal erreichte die Angebotsphase (oder weiter)"),
    ("abgelaufen", "8 Wochen ohne Reaktion"),
    ("verloren", "Deal als verloren markiert"),
]


class MusterboxNachfassVorlage(models.Model):
    """Fester Satz von genau 8 Vorlagen (eine je Woche) für die Musterbox-Nachfasskette an
    den Kunden (siehe nurture.musterbox_nachfass_senden und
    management/commands/nachfass_pruefen.py). Ersetzt die frühere, einzelne, immer gleiche
    NachfassKundenmailVorlage (bis 18.10.2026) - auf Wunsch von Björn (18.10.2026) gibt es
    jetzt acht unterschiedliche, aufeinander aufbauende Inhalte statt eines einzigen,
    wiederholten Texts. Diese Mail geht AUSSCHLIESSLICH an Deals, die tatsächlich einen
    Musterversand erhalten haben (siehe MusterboxNachfassStatus unten) - für alle anderen
    Deals gibt es seit diesem Wechsel keinen automatischen Kunden-Mailkontakt mehr.

    Anrede, Logo-Kopfzeile, Unterschrift (Björn persönlich) und Fußzeile sind fest in der
    E-Mail-Vorlage vorgegeben (templates/vertrieb/email/musterbox_nachfass.html/.txt). Hier
    wird nur der eigentliche Nachrichtentext der jeweiligen Woche gepflegt. Platzhalter im
    Text werden als Django-Template ausgewertet, verfügbar sind: {{ vorname }}, {{ nachname }},
    {{ firma }}, {{ deal_titel }}, {{ artikel }} (die beim Musterversand bestellte Artikelart,
    z.B. "Besteck" bzw. "Trinkhalme" - aus den Packschein-Positionen abgeleitet, da es dafür
    kein eigenes Feld gibt; siehe nurture._musterversand_artikel_text)."""

    woche = models.PositiveSmallIntegerField("Woche", unique=True)
    betreff = models.CharField(
        "Betreff", max_length=200,
        help_text="Platzhalter möglich: {{ firma }}, {{ deal_titel }}, {{ artikel }}.",
    )
    text = models.TextField(
        "Nachrichtentext",
        help_text=(
            "Nur der Nachrichtentext - Anrede ('Guten Tag ...') und Grußformel/Unterschrift "
            "stehen fest im Vorlagen-Rahmen und müssen hier nicht wiederholt werden. "
            "Platzhalter: {{ vorname }}, {{ nachname }}, {{ firma }}, {{ deal_titel }}, "
            "{{ artikel }}. Leerzeilen werden als eigene Absätze dargestellt."
        ),
    )
    aktualisiert_am = models.DateTimeField("Zuletzt geändert am", auto_now=True)
    aktualisiert_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="Zuletzt geändert von", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        verbose_name = "Musterbox-Nachfassmail (Vorlage je Woche)"
        verbose_name_plural = "Musterbox-Nachfassmails (Vorlagen je Woche)"
        ordering = ["woche"]

    def __str__(self):
        return f"Woche {self.woche}: {self.betreff}"

    @classmethod
    def fuer_woche(cls, woche):
        return cls.objects.filter(woche=woche).first()


class MusterboxNachfassStatus(models.Model):
    """Führt pro Deal Buch darüber, in welcher Woche der 8-wöchigen Musterbox-Nachfasskette
    an den Kunden (siehe MusterboxNachfassVorlage oben) sich der Deal gerade befindet. Wird
    einmalig angelegt, sobald der zugehörige Musterversand-Packschein als versendet markiert
    wird (siehe nurture.musterversand_abgeschlossen) - bewusst GETRENNT von der bestehenden,
    länger laufenden internen Nachfass-Aktivität (Aktivitaet, typ='nachfass'), die weiterhin
    unverändert bis zum echten Versand oder 'verloren' läuft (siehe nachfass_pruefen.py) und
    NICHT Teil dieser Kette ist - das ist weiterhin die interne Erinnerung an den
    zuständigen Mitarbeiter, unabhängig vom Deal-Fortschritt.

    Pro Lauf des wöchentlichen Crons (siehe management/commands/nachfass_pruefen.py) wird
    höchstens EINE Mail verschickt (Woche naechste_woche), danach entweder naechste_woche um
    1 erhöht, oder - nach Woche 8 - die Kette beendet und eine interne Aktivität für den
    zuständigen Mitarbeiter angelegt ("Lead ausgelaufen nach 8 Wochen, bitte manuell
    prüfen"). Die Kette endet vorher, OHNE weitere Mail, sobald der Deal die Phase
    'lead'/'qualifiziert' verlässt (auf Wunsch von Björn, 18.10.2026: eine Reaktion -
    Angebot, Verhandlung, Gewonnen - beendet die automatische Werbung sofort) oder als
    'verloren' markiert wird."""

    deal = models.OneToOneField(
        Deal, verbose_name="Deal", on_delete=models.CASCADE, related_name="musterbox_nachfass_status",
    )
    naechste_woche = models.PositiveSmallIntegerField("Nächste Woche", default=1)
    naechster_versand_am = models.DateTimeField("Nächster Versand fällig am", default=timezone.now)
    aktiv = models.BooleanField("Aktiv", default=True)
    beendet_am = models.DateTimeField("Beendet am", null=True, blank=True)
    beendet_grund = models.CharField(
        "Beendet, weil", max_length=20, choices=MUSTERBOX_NACHFASS_ENDE_CHOICES, blank=True,
    )
    erstellt_am = models.DateTimeField("Erstellt am", auto_now_add=True)

    class Meta:
        verbose_name = "Musterbox-Nachfass-Status"
        verbose_name_plural = "Musterbox-Nachfass-Status"
        ordering = ["-aktiv", "naechster_versand_am"]

    def __str__(self):
        if self.aktiv:
            return f"{self.deal}: Woche {self.naechste_woche} fällig {self.naechster_versand_am:%d.%m.%Y}"
        return f"{self.deal}: beendet ({self.get_beendet_grund_display()})"
