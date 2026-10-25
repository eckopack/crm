from django.urls import path

from . import views

app_name = "vertrieb"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("pipeline/", views.pipeline_kanban, name="pipeline"),
    path("pipeline/<int:pk>/phase/", views.deal_phase_setzen, name="deal_phase_setzen"),
    path("interna/nachfass-cron/", views.interner_nachfass_cron, name="interner_nachfass_cron"),

    path("firmen/", views.FirmaListView.as_view(), name="firma_list"),
    path("firmen/neu/", views.FirmaCreateView.as_view(), name="firma_create"),
    path("firmen/<int:pk>/", views.FirmaDetailView.as_view(), name="firma_detail"),
    path("firmen/<int:pk>/bearbeiten/", views.FirmaUpdateView.as_view(), name="firma_update"),
    path("firmen/<int:pk>/archivieren/", views.firma_archivieren, name="firma_archivieren"),
    path("firmen/<int:pk>/reaktivieren/", views.firma_reaktivieren, name="firma_reaktivieren"),

    path("kontakte/", views.KontaktListView.as_view(), name="kontakt_list"),
    path("kontakte/neu/", views.KontaktCreateView.as_view(), name="kontakt_create"),
    path("kontakte/<int:pk>/", views.KontaktDetailView.as_view(), name="kontakt_detail"),
    path("kontakte/<int:pk>/bearbeiten/", views.KontaktUpdateView.as_view(), name="kontakt_update"),
    path("kontakte/<int:pk>/archivieren/", views.kontakt_archivieren, name="kontakt_archivieren"),
    path("kontakte/<int:pk>/reaktivieren/", views.kontakt_reaktivieren, name="kontakt_reaktivieren"),

    path("deals/", views.DealListView.as_view(), name="deal_list"),
    path("deals/export/", views.deal_liste_export, name="deal_liste_export"),
    path("deals/neu/", views.DealCreateView.as_view(), name="deal_create"),
    path("deals/<int:pk>/", views.DealDetailView.as_view(), name="deal_detail"),
    path("deals/<int:pk>/musterkarton/", views.musterkarton_anfordern, name="musterkarton_anfordern"),
    path("deals/<int:pk>/nachfass-abbrechen/", views.musterbox_nachfass_abbrechen, name="musterbox_nachfass_abbrechen"),
    path("deals/<int:pk>/bearbeiten/", views.DealUpdateView.as_view(), name="deal_update"),
    path("deals/<int:pk>/loeschen/", views.DealDeleteView.as_view(), name="deal_delete"),

    path("aktivitaeten/", views.AktivitaetListView.as_view(), name="aktivitaet_list"),
    path("aktivitaeten/neu/", views.AktivitaetCreateView.as_view(), name="aktivitaet_create"),
    path("aktivitaeten/<int:pk>/", views.AktivitaetDetailView.as_view(), name="aktivitaet_detail"),
    path("aktivitaeten/<int:pk>/bearbeiten/", views.AktivitaetUpdateView.as_view(), name="aktivitaet_update"),
    path("aktivitaeten/<int:pk>/loeschen/", views.AktivitaetDeleteView.as_view(), name="aktivitaet_delete"),
    path("aktivitaeten/<int:pk>/erledigt/", views.aktivitaet_erledigt_umschalten, name="aktivitaet_erledigt"),

    path("angebote/", views.AngebotListView.as_view(), name="angebot_list"),
    path("angebote/neu/", views.angebot_erstellen, name="angebot_create"),
    path("angebote/<int:pk>/", views.AngebotDetailView.as_view(), name="angebot_detail"),
    path("angebote/<int:pk>/bearbeiten/", views.angebot_bearbeiten, name="angebot_update"),
    path("angebote/<int:pk>/loeschen/", views.AngebotDeleteView.as_view(), name="angebot_delete"),
    path("angebote/<int:pk>/pdf/", views.angebot_pdf_download, name="angebot_pdf"),
    path("angebote/<int:pk>/versenden/", views.angebot_versand_senden_view, name="angebot_versand"),
    path("angebote/<int:pk>/ablehnen/", views.angebot_ablehnen, name="angebot_ablehnen"),

    path("rahmenvereinbarungen/", views.RahmenvereinbarungListView.as_view(), name="rahmenvereinbarung_list"),
    path("rahmenvereinbarungen/neu/", views.rahmenvereinbarung_erstellen, name="rahmenvereinbarung_create"),
    path("rahmenvereinbarungen/<int:pk>/", views.RahmenvereinbarungDetailView.as_view(), name="rahmenvereinbarung_detail"),
    path("rahmenvereinbarungen/<int:pk>/bearbeiten/", views.rahmenvereinbarung_bearbeiten, name="rahmenvereinbarung_update"),
    path("rahmenvereinbarungen/<int:pk>/loeschen/", views.RahmenvereinbarungDeleteView.as_view(), name="rahmenvereinbarung_delete"),
    path("rahmenvereinbarungen/<int:pk>/vertrag-pdf/", views.rahmenvereinbarung_pdf_download, name="rahmenvereinbarung_pdf"),

    path("packscheine/", views.PackscheinListView.as_view(), name="packschein_list"),
    path("packscheine/neu/", views.packschein_erstellen, name="packschein_create"),
    path("packscheine/<int:pk>/", views.PackscheinDetailView.as_view(), name="packschein_detail"),
    path("packscheine/<int:pk>/bearbeiten/", views.packschein_bearbeiten, name="packschein_update"),
    path("packscheine/<int:pk>/versand/", views.packschein_versand_bestaetigen, name="packschein_versand"),
    path("packscheine/<int:pk>/loeschen/", views.PackscheinDeleteView.as_view(), name="packschein_delete"),
    path("packscheine/<int:pk>/pdf/", views.packschein_pdf_download, name="packschein_pdf"),

    path("lieferscheine/", views.LieferscheinListView.as_view(), name="lieferschein_list"),
    path("lieferscheine/neu/", views.lieferschein_erstellen, name="lieferschein_create"),
    path("lieferscheine/<int:pk>/", views.LieferscheinDetailView.as_view(), name="lieferschein_detail"),
    path("lieferscheine/<int:pk>/bearbeiten/", views.lieferschein_bearbeiten, name="lieferschein_update"),
    path("lieferscheine/<int:pk>/versand/", views.lieferschein_versand_bestaetigen, name="lieferschein_versand"),
    path("lieferscheine/<int:pk>/loeschen/", views.LieferscheinDeleteView.as_view(), name="lieferschein_delete"),
    path("lieferscheine/<int:pk>/pdf/", views.lieferschein_pdf_download, name="lieferschein_pdf"),

    path("rechnungen/", views.RechnungListView.as_view(), name="rechnung_list"),
    path("rechnungen/neu/", views.rechnung_erstellen, name="rechnung_create"),
    path("rechnungen/<int:pk>/", views.RechnungDetailView.as_view(), name="rechnung_detail"),
    path("rechnungen/<int:pk>/bearbeiten/", views.rechnung_bearbeiten, name="rechnung_update"),
    path("rechnungen/<int:pk>/loeschen/", views.RechnungDeleteView.as_view(), name="rechnung_delete"),
    path("rechnungen/<int:pk>/pdf/", views.rechnung_pdf_download, name="rechnung_pdf"),
    path("rechnungen/<int:pk>/versand/", views.rechnung_versand_senden_view, name="rechnung_versand"),
    path("rechnungen/<int:pk>/zahlung/", views.rechnung_zahlung_erfassen, name="rechnung_zahlung_erfassen"),
    path(
        "rechnungen/<int:pk>/zahlung/<int:zahlung_pk>/loeschen/",
        views.rechnung_zahlung_loeschen, name="rechnung_zahlung_loeschen",
    ),
    path("rechnungen/<int:pk>/korrektur/", views.rechnung_korrektur_erstellen, name="rechnung_korrektur_erstellen"),

    path("offene-posten/", views.offene_posten_liste, name="offene_posten_list"),

    path("emails/", views.EmailVersandListView.as_view(), name="email_versand_list"),
    path("nachfass/", views.MusterboxNachfassStatusListView.as_view(), name="musterbox_nachfass_list"),

    path("artikel/", views.ArtikelListView.as_view(), name="artikel_list"),
    path("artikel/neu/", views.ArtikelCreateView.as_view(), name="artikel_create"),
    path("artikel/<int:pk>/", views.ArtikelDetailView.as_view(), name="artikel_detail"),
    path("artikel/<int:pk>/bearbeiten/", views.ArtikelUpdateView.as_view(), name="artikel_update"),
    path("artikel/<int:pk>/loeschen/", views.ArtikelDeleteView.as_view(), name="artikel_delete"),
    path("artikel/<int:pk>/daten.json", views.artikel_daten_json, name="artikel_daten_json"),
    path("artikel/preisliste/", views.artikelliste_versenden, name="artikelliste_versenden"),
    path("artikel/preisliste/pdf/", views.artikelliste_pdf_download, name="artikelliste_pdf"),

    path("lagerwirtschaft/wareneingang/", views.wareneingang_erfassen, name="wareneingang_erfassen"),
    path("lagerwirtschaft/bestandsuebersicht/", views.bestandsuebersicht, name="bestandsuebersicht"),
    path("lagerwirtschaft/bewegungen/", views.LagerbewegungListView.as_view(), name="lagerbewegung_list"),
    path("lagerwirtschaft/produktion/", views.produktionsbuchung_erfassen, name="produktionsbuchung_erfassen"),
    path("lagerwirtschaft/produktion/liste/", views.ProduktionsbuchungListView.as_view(), name="produktionsbuchung_list"),
    path(
        "lagerwirtschaft/produktion/<int:pk>/", views.ProduktionsbuchungDetailView.as_view(),
        name="produktionsbuchung_detail",
    ),

    path("produktionsberichte/", views.ProduktionsberichtListView.as_view(), name="produktionsbericht_list"),
    path("produktionsberichte/neu/", views.produktionsbericht_erfassen, name="produktionsbericht_erfassen"),
    path(
        "produktionsberichte/<int:pk>/", views.ProduktionsberichtDetailView.as_view(),
        name="produktionsbericht_detail",
    ),
    path(
        "produktionsberichte/<int:pk>/freigeben/", views.produktionsbericht_freigeben,
        name="produktionsbericht_freigeben",
    ),
    path(
        "produktionsberichte/<int:pk>/ablehnen/", views.produktionsbericht_ablehnen,
        name="produktionsbericht_ablehnen",
    ),
    path(
        "produktionsberichte/<int:pk>/pdf/", views.produktionsbericht_pdf_download,
        name="produktionsbericht_pdf",
    ),
]
