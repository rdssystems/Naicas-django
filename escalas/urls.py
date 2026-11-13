from django.urls import path
from . import views

app_name = 'escalas'
urlpatterns = [
    path('', views.GradeView.as_view(), name='grade'),
    path('novo/', views.AtividadeCreateView.as_view(), name='criar'),
    path('atividades/<int:pk>/', views.AtividadeDetailView.as_view(), name='detalhe'),
    path('atividades/<int:pk>/editar/', views.AtividadeUpdateView.as_view(), name='editar'),
    path('atividades/<int:pk>/excluir/', views.AtividadeDeleteView.as_view(), name='excluir'),
    path('monitor/<int:pk>/', views.EscalaMonitorView.as_view(), name='monitor'),
    path('minha-semana/', views.MinhaSemanaView.as_view(), name='minha_semana'),
]
