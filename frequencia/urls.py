from django.urls import path

from . import views

app_name = 'frequencia'

urlpatterns = [
    path('oficina/<int:pk>/', views.FrequenciaOficinaView.as_view(), name='oficina'),
    path('oficina/<int:pk>/chamada/', views.ChamadaView.as_view(), name='chamada'),
    path('oficina/<int:pk>/aulas/<int:aula_pk>/excluir/', views.ExcluirAulaView.as_view(), name='excluir_aula'),
]
