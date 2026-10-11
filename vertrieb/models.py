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
    ("std", "Stunde"),
    ("tag", "Tag"),
    ("monat", "Monat"),
    ("pauschal", "Pauschal"),
    ("kg", "kg"),
    ("m", "m"),
    ("m2", "m²"),
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
    position = models.PositiveIntegerField("Pos.", default=1)
    bezeichnung = models.CharField("Bezeichnung", max_length=300)
    menge = models.DecimalField("Menge", max_digits=10, decimal_places=2, default=1)
    einheit = models.CharField("Einheit", max_length=10, choices=EINHEIT_CHOICES, default="stk")
    einzelpreis = models.DecimalField("Einzelpreis (EUR)", max_digits=12, decimal_places=2, default=0)

    class Meta:
        verbose_name = "Angebotsposition"
        verbose_name_plural = "Angebotspositionen"
        ordering = ["position"]

    def __str__(self):
        return self.bezeichnung

    @property
    def gesamtpreis(self):
        return self.menge * self.einzelpreis


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


class Lieferschein(models.Model):
    nummer = models.CharField("Lieferscheinnummer", max_length=30, unique=True, blank=True)
    deal = models.ForeignKey(Deal, verbose_name="Deal", on_delete=models.CASCADE, related_name="lieferscheine")
    angebot = models.ForeignKey(
        Angebot, verbose_name="Angebot", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="lieferscheine"
    )
    datum = models.DateField("Lieferdatum", default=timezone.now)
    status = models.CharField("Status", max_length=20, choices=LIEFERSCHEIN_STATUS_CHOICES, default="entwurf")
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
    position = models.PositiveIntegerField("Pos.", default=1)
    bezeichnung = models.CharField("Bezeichnung", max_length=300)
    menge = models.DecimalField("Menge", max_digits=10, decimal_places=2, default=1)
    einheit = models.CharField("Einheit", max_length=10, choices=EINHEIT_CHOICES, default="stk")
    einzelpreis = models.DecimalField("Einzelpreis (EUR, netto)", max_digits=12, decimal_places=2, default=0)
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
