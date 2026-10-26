from django.urls import path

from . import views

app_name = 'escalas'

urlpatterns = [
    path('', views.GradeView.as_view(), name='grade'),
    path('monitor/<int:pk>/', views.EscalaMonitorView.as_view(), name='monitor'),
    path('minha-semana/', views.MinhaSemanaView.as_view(), name='minha_semana'),
]
