from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.HomeView.as_view(), name='home'),
    path('favicon.ico', views.favicon, name='favicon'),
    path('service-worker.js', views.service_worker, name='service_worker'),
]
