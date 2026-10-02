from django.urls import path

from . import views

app_name = 'matriculas'

urlpatterns = [
    path('oficina/<int:pk>/', views.MatriculadosOficinaView.as_view(), name='oficina'),
    path('oficina/<int:pk>/nova/', views.MatricularNaOficinaView.as_view(), name='matricular_na_oficina'),
    path('aluno/<int:pk>/', views.EtapaMatriculaView.as_view(), name='aluno'),
    path('<int:pk>/concluir/', views.AlterarSituacaoView.as_view(acao='concluir'), name='concluir'),
    path('<int:pk>/desistir/', views.AlterarSituacaoView.as_view(acao='desistir'), name='desistir'),
]
