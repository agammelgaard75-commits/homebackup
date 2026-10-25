from django.urls import path
from . import views, service_views

app_name = "search"
urlpatterns = [
    path("", views.search, name="index"),
    path("by-service/", service_views.service_contact_search, name="services"),
    path("by-service/emails/", service_views.service_contact_emails, name="service_emails"),
]
