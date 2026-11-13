from django.urls import path

from . import views

app_name = 'frequencia'

urlpatterns = [
    path('naica/chamada/', views.ChamadaNaicaView.as_view(), name='chamada_naica'),
    path('oficina/<int:pk>/', views.FrequenciaOficinaLegadaView.as_view(), name='oficina'),
    path('oficina/<int:pk>/chamada/', views.FrequenciaOficinaLegadaView.as_view(), name='chamada'),
    path('oficina/<int:pk>/aulas/<int:aula_pk>/excluir/', views.FrequenciaOficinaLegadaView.as_view(), name='excluir_aula'),
]
