from django.urls import path
from . import views

app_name = "customer_activity"
urlpatterns = [path("", views.customer_activity, name="list")]
