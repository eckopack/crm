from django.urls import path

from . import views

app_name = "vertrieb"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("pipeline/", views.pipeline_kanban, name="pipeline"),
    path("pipeline/<int:pk>/phase/", views.deal_phase_setzen, name="deal_phase_setzen"),

    path("firmen/", views.FirmaListView.as_view(), name="firma_list"),
    path("firmen/neu/", views.FirmaCreateView.as_view(), name="firma_create"),
    path("firmen/<int:pk>/", views.FirmaDetailView.as_view(), name="firma_detail"),
    path("firmen/<int:pk>/bearbeiten/", views.FirmaUpdateView.as_view(), name="firma_update"),
    path("firmen/<int:pk>/loeschen/", views.FirmaDeleteView.as_view(), name="firma_delete"),

    path("kontakte/", views.KontaktListView.as_view(), name="kontakt_list"),
    path("kontakte/neu/", views.KontaktCreateView.as_view(), name="kontakt_create"),
    path("kontakte/<int:pk>/", views.KontaktDetailView.as_view(), name="kontakt_detail"),
    path("kontakte/<int:pk>/bearbeiten/", views.KontaktUpdateView.as_view(), name="kontakt_update"),
    path("kontakte/<int:pk>/loeschen/", views.KontaktDeleteView.as_view(), name="kontakt_delete"),

    path("deals/", views.DealListView.as_view(), name="deal_list"),
    path("deals/neu/", views.DealCreateView.as_view(), name="deal_create"),
    path("deals/<int:pk>/", views.DealDetailView.as_view(), name="deal_detail"),
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
]
