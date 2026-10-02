from django.urls import path

from . import views

app_name = 'anexos'

urlpatterns = [
    path('aluno/<int:pk>/', views.AnexosAlunoView.as_view(), name='aluno'),
    path('<int:anexo_pk>/arquivo/', views.AnexoArquivoView.as_view(), name='arquivo'),
    path('<int:anexo_pk>/excluir/', views.AnexoExcluirView.as_view(), name='excluir'),
    path('tipos/', views.TipoDocumentoListView.as_view(), name='tipos'),
    path('tipos/novo/', views.TipoDocumentoCreateView.as_view(), name='tipo_criar'),
    path('tipos/<int:pk>/editar/', views.TipoDocumentoUpdateView.as_view(), name='tipo_editar'),
    path('tipos/<int:pk>/excluir/', views.TipoDocumentoExcluirView.as_view(), name='tipo_excluir'),
]
