"""Übersetzungen für die MA-Oberfläche des Produktionsbericht-Piloten (27.10.2026, auf
Wunsch von Björn: zwei MA sprechen Tschechisch bzw. Ukrainisch und sollen die
Eingabemaske/Navigation in ihrer Sprache sehen und ausfüllen können).

Bewusst KEIN Django-i18n-Framework (gettext/.po-Dateien, LocaleMiddleware, makemessages/
compilemessages im Deploy) eingeführt, sondern dasselbe leichtgewichtige Muster wie bei den
bereits bestehenden zweisprachigen Kundendokumenten (siehe pdf.py, Angebot.sprache: ein
Sprachfeld + eine kleine Übersetzungstabelle/ein paar if-Zweige) - die MA-Oberfläche ist
technisch auf eine Handvoll Templates begrenzt (ProduktionszugriffMiddleware sperrt MA
ohnehin von jedem anderen Teil des CRM ab, siehe middleware.py), für zwei Mitarbeiter und
zwei Sprachen wäre eine vollständige i18n-Infrastruktur unverhältnismäßig.

Abgrenzung (Björns Entscheidung 27.10.2026, siehe Chat):
- Übersetzt werden NUR die festen Formular-/Navigationstexte (Beschriftungen, Buttons,
  Dropdown-Werte wie Schicht/Ausschussgrund, Fehlermeldungen) - siehe UEBERSETZUNGEN unten.
- Freitextfelder (Bemerkungen, Stillstandsgrund, Werkzeug-Bezeichnung, Reinigungsperson)
  werden NICHT automatisch übersetzt - der MA tippt sie in der Sprache seiner Wahl, der
  Produktionsleiter sieht sie unverändert. Bewusst keine maschinelle Übersetzung (Kosten,
  Fehleranfälligkeit, und Mitarbeitertext an einen externen Übersetzungsdienst zu schicken
  wäre ein eigenständig zu entscheidender Datenschutz-Punkt).
- Das PDF (produktionsbericht_pdf_erzeugen in pdf.py) und die Benachrichtigungsmail an den
  Produktionsleiter (nurture.produktionsbericht_eingereicht_benachrichtigen) bleiben IMMER
  Deutsch, unabhängig von der Sprache des einreichenden MA - ohne jeden Zusatzaufwand: beide
  lesen get_schicht_display()/get_status_display()/etc. direkt vom Modell, dessen
  choices-Tupel (PRODUKTIONSBERICHT_SCHICHT_CHOICES & Co. in models.py) unverändert Deutsch
  sind. Nur ProduktionsberichtForm überschreibt die choices auf FORMULAR-Ebene für die
  aktive Sprache (siehe forms.py) - das betrifft ausschließlich die Eingabemaske, nicht das
  Modell selbst, und PDF/Mail erzeugen nie ein Formular.

WICHTIG [Sicher]: Die Tschechisch-/Ukrainisch-Texte unten sind maschinell erstellte
Übersetzungen (von Claude), KEINE geprüfte professionelle Übersetzung. Vor dem produktiven
Einsatz durch die betroffenen Mitarbeiter sollten sie von einem Muttersprachler (idealerweise
den beiden MA selbst) gegengelesen werden - eine Fehlübersetzung auf einem
Schichtbericht-Formular kann zu falschen Eingaben führen."""

PRODUKTION_SPRACHE_CHOICES = [
    ("de", "Deutsch"),
    ("cs", "Čeština"),
    ("uk", "Українська"),
]

STANDARDSPRACHE = "de"

# Session-Schlüssel, unter dem die aktive Oberflächensprache abgelegt wird (siehe
# signals.sprache_bei_login_aktivieren und context_processors.ma_sprache) - bewusst die
# Session und nicht ein Cookie, siehe MitarbeiterSprache-Moduldoku in models.py
# (gemeinsam genutzter Büro-PC, Sprache muss am Konto hängen, nicht am Gerät).
SESSION_SCHLUESSEL = "ma_sprache"

# Schlüssel -> {sprachcode: text}. "de" ist zugleich der im restlichen Code/den Templates
# tatsächlich verwendete deutsche Text (siehe jeweilige Verwendungsstelle) - bei einer
# späteren Textänderung dort muss der Eintrag hier mitgepflegt werden, das wird nicht
# automatisch geprüft.
UEBERSETZUNGEN = {
    # Navigation (base.html, MA-Ansicht)
    "nav.neuer_bericht": {
        "de": "Neuer Produktionsbericht",
        "cs": "Nový výrobní hlášení",
        "uk": "Новий виробничий звіт",
    },
    "nav.meine_berichte": {
        "de": "Meine Produktionsberichte",
        "cs": "Moje výrobní hlášení",
        "uk": "Мої виробничі звіти",
    },
    "nav.abmelden": {
        "de": "Abmelden",
        "cs": "Odhlásit se",
        "uk": "Вийти",
    },

    # produktionsbericht_form.html
    "formular.titel_neu": {
        "de": "Produktionsbericht: Trinkhalm-Produktion L1",
        "cs": "Výrobní hlášení: Výroba brček L1",
        "uk": "Виробничий звіт: Виробництво трубочок L1",
    },
    "formular.hinweis_neu": {
        "de": "Bitte den Bericht für die abgeschlossene Schicht ausfüllen und einreichen. "
              "Der Bericht fließt erst nach Freigabe durch den Produktionsleiter in den "
              "Lagerbestand ein.",
        "cs": "Vyplňte prosím hlášení za ukončenou směnu a odešlete je. Hlášení se do "
              "skladové evidence započítá až po schválení vedoucím výroby.",
        "uk": "Будь ласка, заповніть звіт за завершену зміну та надішліть його. Звіт "
              "враховується на складі лише після затвердження керівником виробництва.",
    },
    "formular.titel_korrektur": {
        "de": "korrigieren: Trinkhalm-Produktion L1",
        "cs": "oprava: Výroba brček L1",
        "uk": "виправлення: Виробництво трубочок L1",
    },
    "formular.hinweis_korrektur": {
        "de": "Bitte die Angaben korrigieren und erneut einreichen. Der Bericht wartet "
              "danach wieder auf Freigabe durch den Produktionsleiter.",
        "cs": "Opravte prosím údaje a odešlete hlášení znovu. Hlášení poté opět čeká na "
              "schválení vedoucím výroby.",
        "uk": "Будь ласка, виправте дані та надішліть звіт повторно. Після цього звіт знову "
              "очікує на затвердження керівником виробництва.",
    },
    "formular.abgelehnt_praefix": {
        "de": "Abgelehnt",
        "cs": "Zamítnuto",
        "uk": "Відхилено",
    },
    "formular.von": {
        "de": "von",
        "cs": "od",
        "uk": "від",
    },
    "formular.am": {
        "de": "am",
        "cs": "dne",
        "uk": "дата",
    },
    "formular.schicht_karte": {
        "de": "Schicht",
        "cs": "Směna",
        "uk": "Зміна",
    },
    "formular.werkzeug_karte": {
        "de": "Werkzeug & Schuss",
        "cs": "Nástroj a vstřik",
        "uk": "Форма і впорскування",
    },
    "formular.menge_karte": {
        "de": "Produzierte Menge (Stück)",
        "cs": "Vyrobené množství (kusy)",
        "uk": "Виготовлена кількість (шт.)",
    },
    "formular.ruesten_karte": {
        "de": "Rüsten & Stillstand",
        "cs": "Seřízení a prostoje",
        "uk": "Налагодження та простої",
    },
    "formular.sonstiges_karte": {
        "de": "Sonstiges",
        "cs": "Ostatní",
        "uk": "Інше",
    },
    "formular.feld.fertigprodukt": {
        "de": "Trinkhalm-Artikel",
        "cs": "Artikl brčka",
        "uk": "Артикул трубочки",
    },
    "formular.feld.datum": {
        "de": "Datum",
        "cs": "Datum",
        "uk": "Дата",
    },
    "formular.feld.schicht": {
        "de": "Schicht",
        "cs": "Směna",
        "uk": "Зміна",
    },
    "formular.feld.bediener_1": {
        "de": "Bediener 1",
        "cs": "Obsluha 1",
        "uk": "Оператор 1",
    },
    "formular.feld.bediener_2": {
        "de": "Bediener 2",
        "cs": "Obsluha 2",
        "uk": "Оператор 2",
    },
    "formular.feld.produktionszeit_von": {
        "de": "Produktionszeit von",
        "cs": "Doba výroby od",
        "uk": "Час виробництва від",
    },
    "formular.feld.produktionszeit_bis": {
        "de": "Produktionszeit bis",
        "cs": "Doba výroby do",
        "uk": "Час виробництва до",
    },
    "formular.feld.werkzeug_bezeichnung": {
        "de": "Werkzeug/Form",
        "cs": "Nástroj/forma",
        "uk": "Форма/оснащення",
    },
    "formular.feld.schussanzahl": {
        "de": "Schussanzahl",
        "cs": "Počet vstřiků",
        "uk": "Кількість впорскувань",
    },
    "formular.feld.menge_gut_stueck": {
        "de": "Gutmenge (Stück)",
        "cs": "Dobré kusy (ks)",
        "uk": "Придатна кількість (шт.)",
    },
    "formular.feld.menge_ausschuss_stueck": {
        "de": "Ausschuss (Stück)",
        "cs": "Zmetky (ks)",
        "uk": "Брак (шт.)",
    },
    "formular.feld.ausschussgrund": {
        "de": "Ausschussgrund",
        "cs": "Důvod zmetkovitosti",
        "uk": "Причина браку",
    },
    "formular.feld.ruestzeit_minuten": {
        "de": "Rüstzeit (Minuten)",
        "cs": "Doba seřízení (minuty)",
        "uk": "Час налагодження (хв)",
    },
    "formular.feld.stillstandszeit_minuten": {
        "de": "Stillstandszeit (Minuten)",
        "cs": "Doba prostoje (minuty)",
        "uk": "Час простою (хв)",
    },
    "formular.feld.stillstandsgrund": {
        "de": "Stillstandsgrund",
        "cs": "Důvod prostoje",
        "uk": "Причина простою",
    },
    "formular.feld.stromverbrauch_kwh": {
        "de": "Stromverbrauch (kWh)",
        "cs": "Spotřeba elektřiny (kWh)",
        "uk": "Споживання електроенергії (кВт·год)",
    },
    "formular.feld.reinigung_durchgefuehrt_von": {
        "de": "Reinigung durchgeführt von",
        "cs": "Čištění provedl(a)",
        "uk": "Очищення виконав(ла)",
    },
    "formular.feld.bemerkungen": {
        "de": "Bemerkungen",
        "cs": "Poznámky",
        "uk": "Примітки",
    },
    "formular.einreichen": {
        "de": "Bericht einreichen",
        "cs": "Odeslat hlášení",
        "uk": "Надіслати звіт",
    },
    "formular.korrigiert_einreichen": {
        "de": "Korrigiert erneut einreichen",
        "cs": "Odeslat opravené hlášení",
        "uk": "Надіслати виправлений звіт",
    },
    "formular.abbrechen": {
        "de": "Abbrechen",
        "cs": "Zrušit",
        "uk": "Скасувати",
    },

    # produktionsbericht_list.html
    "liste.titel": {
        "de": "Meine Produktionsberichte",
        "cs": "Moje výrobní hlášení",
        "uk": "Мої виробничі звіти",
    },
    "liste.neuer_button": {
        "de": "+ Neuer Produktionsbericht",
        "cs": "+ Nové výrobní hlášení",
        "uk": "+ Новий виробничий звіт",
    },
    "liste.spalte.datum": {"de": "Datum", "cs": "Datum", "uk": "Дата"},
    "liste.spalte.linie": {"de": "Linie", "cs": "Linka", "uk": "Лінія"},
    "liste.spalte.schicht": {"de": "Schicht", "cs": "Směna", "uk": "Зміна"},
    "liste.spalte.fertigprodukt": {"de": "Fertigprodukt", "cs": "Výrobek", "uk": "Виріб"},
    "liste.spalte.gutmenge": {
        "de": "Gutmenge (Stück)", "cs": "Dobré kusy (ks)", "uk": "Придатна кількість (шт.)",
    },
    "liste.spalte.bediener": {"de": "Bediener", "cs": "Obsluha", "uk": "Оператор"},
    "liste.spalte.status": {"de": "Status", "cs": "Stav", "uk": "Статус"},
    "liste.leer": {
        "de": "Noch kein Produktionsbericht erfasst.",
        "cs": "Zatím nebylo zaznamenáno žádné výrobní hlášení.",
        "uk": "Виробничих звітів ще немає.",
    },

    # produktionsbericht_detail.html
    "detail.pdf_button": {
        "de": "PDF / Drucken", "cs": "PDF / Tisk", "uk": "PDF / Друк",
    },
    "detail.korrigieren_button": {
        "de": "Korrigieren und erneut einreichen",
        "cs": "Opravit a odeslat znovu",
        "uk": "Виправити та надіслати повторно",
    },
    "detail.karte.schicht": {"de": "Schicht", "cs": "Směna", "uk": "Зміна"},
    "detail.karte.menge": {
        "de": "Produzierte Menge", "cs": "Vyrobené množství", "uk": "Виготовлена кількість",
    },
    "detail.karte.ruesten": {
        "de": "Rüsten & Stillstand", "cs": "Seřízení a prostoje", "uk": "Налагодження та простої",
    },
    "detail.karte.sonstiges": {"de": "Sonstiges", "cs": "Ostatní", "uk": "Інше"},
    "detail.karte.workflow": {"de": "Workflow", "cs": "Průběh", "uk": "Процес"},
    "detail.fertigprodukt": {"de": "Fertigprodukt:", "cs": "Výrobek:", "uk": "Виріб:"},
    "detail.produktionszeit": {
        "de": "Produktionszeit:", "cs": "Doba výroby:", "uk": "Час виробництва:",
    },
    "detail.bediener": {"de": "Bediener:", "cs": "Obsluha:", "uk": "Оператор:"},
    "detail.werkzeug": {"de": "Werkzeug/Form:", "cs": "Nástroj/forma:", "uk": "Форма/оснащення:"},
    "detail.schussanzahl": {
        "de": "Schussanzahl:", "cs": "Počet vstřiků:", "uk": "Кількість впорскувань:",
    },
    "detail.gutmenge": {"de": "Gutmenge:", "cs": "Dobré kusy:", "uk": "Придатна кількість:"},
    "detail.ausschuss": {"de": "Ausschuss:", "cs": "Zmetky:", "uk": "Брак:"},
    "detail.ruestzeit": {"de": "Rüstzeit:", "cs": "Doba seřízení:", "uk": "Час налагодження:"},
    "detail.stillstandszeit": {
        "de": "Stillstandszeit:", "cs": "Doba prostoje:", "uk": "Час простою:",
    },
    "detail.stromverbrauch": {
        "de": "Stromverbrauch:", "cs": "Spotřeba elektřiny:", "uk": "Споживання електроенергії:",
    },
    "detail.reinigung": {
        "de": "Reinigung durchgeführt von:", "cs": "Čištění provedl(a):",
        "uk": "Очищення виконав(ла):",
    },
    "detail.eingereicht_von": {
        "de": "Eingereicht von:", "cs": "Odesláno:", "uk": "Подано:",
    },
    "detail.wartet_auf_freigabe": {
        "de": "Wartet auf Freigabe durch den Produktionsleiter.",
        "cs": "Čeká na schválení vedoucím výroby.",
        "uk": "Очікує на затвердження керівником виробництва.",
    },

    # Linie-Auswahl (Werte aus models.PRODUKTIONSBERICHT_LINIE_CHOICES) - Besteck L1-L3 sind
    # für MA aktuell technisch nicht erreichbar (nur Trinkhalm-L1-Pilot, siehe
    # produktionsbericht_erfassen in views.py), hier trotzdem vollständig für den Fall, dass
    # get_linie_display() einmal auch dafür über {% t_feld %} angezeigt wird.
    "linie.trinkhalm_l1": {
        "de": "Trinkhalm-Produktion L1",
        "cs": "Výroba brček L1",
        "uk": "Виробництво трубочок L1",
    },
    "linie.besteck_l1": {
        "de": "Besteck-Produktion L1",
        "cs": "Výroba příborů L1",
        "uk": "Виробництво столових приборів L1",
    },
    "linie.besteck_l2": {
        "de": "Besteck-Produktion L2",
        "cs": "Výroba příborů L2",
        "uk": "Виробництво столових приборів L2",
    },
    "linie.besteck_l3": {
        "de": "Besteck-Produktion L3",
        "cs": "Výroba příborů L3",
        "uk": "Виробництво столових приборів L3",
    },

    # Schicht-Auswahl (Werte aus models.PRODUKTIONSBERICHT_SCHICHT_CHOICES)
    "schicht.frueh": {"de": "Frühschicht", "cs": "Ranní směna", "uk": "Ранкова зміна"},
    "schicht.spaet": {"de": "Spätschicht", "cs": "Odpolední směna", "uk": "Вечірня зміна"},
    "schicht.nacht": {"de": "Nachtschicht", "cs": "Noční směna", "uk": "Нічна зміна"},
    "schicht.sonder": {"de": "Sonderschicht", "cs": "Mimořádná směna", "uk": "Позачергова зміна"},

    # Ausschussgrund-Auswahl (Werte aus models.PRODUKTIONSBERICHT_AUSSCHUSSGRUND_CHOICES)
    "ausschussgrund.leer": {
        "de": "– nicht angegeben –", "cs": "– neuvedeno –", "uk": "– не вказано –",
    },
    "ausschussgrund.kaltfliessnase": {
        "de": "Kaltfließnase", "cs": "Studený spoj", "uk": "Холодний спай",
    },
    "ausschussgrund.grat": {"de": "Grat", "cs": "Otřep", "uk": "Задирка"},
    "ausschussgrund.verzug": {"de": "Verzug", "cs": "Deformace", "uk": "Деформація"},
    "ausschussgrund.lufteinschluss": {
        "de": "Lufteinschluss/Blase", "cs": "Vzduchová bublina", "uk": "Повітряна бульбашка",
    },
    "ausschussgrund.kurzschuss": {
        "de": "Kurzschuss (Teil nicht vollständig gefüllt)",
        "cs": "Nedostřik (díl není zcela zaplněný)",
        "uk": "Недолив (деталь заповнена не повністю)",
    },
    "ausschussgrund.anfahrverlust": {
        "de": "Anfahrverlust (Rüsten/Anlaufphase)",
        "cs": "Ztráta při najíždění (seřízení/rozběh)",
        "uk": "Втрати під час запуску (налагодження/пуск)",
    },
    "ausschussgrund.sonstiges": {
        "de": "Sonstiges (siehe Bemerkungen)",
        "cs": "Jiné (viz poznámky)",
        "uk": "Інше (див. примітки)",
    },

    # Flash-Meldungen (django.contrib.messages) nach dem Einreichen/Korrigieren - siehe
    # views.produktionsbericht_erfassen/produktionsbericht_korrigieren.
    "meldung.eingereicht": {
        "de": "Produktionsbericht eingereicht - wartet jetzt auf Freigabe durch den "
              "Produktionsleiter.",
        "cs": "Výrobní hlášení odesláno - nyní čeká na schválení vedoucím výroby.",
        "uk": "Виробничий звіт надіслано - тепер очікує на затвердження керівником "
              "виробництва.",
    },
    "meldung.korrigiert_eingereicht": {
        "de": "Korrigierter Produktionsbericht eingereicht - wartet jetzt erneut auf "
              "Freigabe durch den Produktionsleiter.",
        "cs": "Opravené výrobní hlášení odesláno - nyní opět čeká na schválení vedoucím "
              "výroby.",
        "uk": "Виправлений виробничий звіт надіслано - тепер знову очікує на затвердження "
              "керівником виробництва.",
    },
    "meldung.nur_abgelehnte_korrigierbar": {
        "de": "Nur abgelehnte Produktionsberichte können korrigiert werden.",
        "cs": "Opravit lze pouze zamítnutá výrobní hlášení.",
        "uk": "Виправляти можна лише відхилені виробничі звіти.",
    },

    # Fehlermeldungen in forms.ProduktionsberichtForm.clean() - mit Platzhaltern für die
    # eingesetzten Werte (siehe dortiger str.format()-Aufruf). Die Platzhalternamen müssen
    # in allen drei Sprachen identisch bleiben.
    "fehler.zeit_reihenfolge": {
        "de": "Muss nach der Produktionszeit \"von\" liegen.",
        "cs": "Musí být později než čas výroby \"od\".",
        "uk": "Має бути пізніше, ніж час виробництва \"від\".",
    },
    "fehler.plausibilitaet": {
        "de": "Rüstzeit ({ruestzeit} Min.) + Stillstandszeit ({stillstand} Min.) sind "
              "zusammen länger als die angegebene Produktionszeit ({dauer} Min.) - bitte "
              "Zeiten prüfen.",
        "cs": "Doba seřízení ({ruestzeit} min) + doba prostoje ({stillstand} min) jsou "
              "dohromady delší než uvedená doba výroby ({dauer} min) - zkontrolujte prosím "
              "časy.",
        "uk": "Час налагодження ({ruestzeit} хв) + час простою ({stillstand} хв) разом "
              "перевищують зазначений час виробництва ({dauer} хв) - перевірте, будь ласка, "
              "час.",
    },
    "fehler.duplikat": {
        "de": "Für den {datum} ({schicht}, Trinkhalm L1) liegt bereits ein "
              "Produktionsbericht vor. Bei einer Korrektur bitte den Produktionsleiter "
              "informieren, statt ein zweites Mal einzureichen.",
        "cs": "Pro {datum} ({schicht}, Trinkhalm L1) již výrobní hlášení existuje. V "
              "případě opravy prosím informujte vedoucího výroby, místo opětovného "
              "odeslání.",
        "uk": "На {datum} ({schicht}, Trinkhalm L1) звіт вже існує. У разі виправлення, "
              "будь ласка, повідомте керівника виробництва, а не надсилайте повторно.",
    },

    # Status-Anzeige (Werte aus models.PRODUKTIONSBERICHT_STATUS_CHOICES)
    "status.eingereicht": {
        "de": "Eingereicht – wartet auf Freigabe",
        "cs": "Odesláno – čeká na schválení",
        "uk": "Подано – очікує затвердження",
    },
    "status.freigegeben": {"de": "Freigegeben", "cs": "Schváleno", "uk": "Затверджено"},
    "status.abgelehnt": {"de": "Abgelehnt", "cs": "Zamítnuto", "uk": "Відхилено"},
}


def uebersetzen(schluessel, sprache):
    """Liefert den übersetzten Text für schluessel in sprache, fällt auf Deutsch zurück,
    wenn die Sprache nicht hinterlegt ist, und auf den Schlüssel selbst, wenn der Schlüssel
    komplett fehlt (bewusst kein KeyError/Exception - ein fehlender Übersetzungseintrag soll
    beim Lesen auffallen, nicht die Seite für den MA kaputt machen)."""
    eintrag = UEBERSETZUNGEN.get(schluessel)
    if eintrag is None:
        return schluessel
    return eintrag.get(sprache) or eintrag.get(STANDARDSPRACHE, schluessel)


def sprache_fuer_konto(user):
    """Liest die hinterlegte Oberflächensprache für user (siehe MitarbeiterSprache in
    models.py), Standard "de" falls keine gesetzt oder der Benutzer nicht angemeldet ist.
    Lokaler Import von models, um einen Zirkelimport beim App-Start zu vermeiden (gleiches
    Muster wie in produktion_extras.py)."""
    if not getattr(user, "is_authenticated", False):
        return STANDARDSPRACHE
    from .models import MitarbeiterSprache

    try:
        return user.mitarbeitersprache.oberflaechen_sprache
    except MitarbeiterSprache.DoesNotExist:
        return STANDARDSPRACHE
