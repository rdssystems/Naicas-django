from django.urls import path

from . import views

app_name = 'alunos'

urlpatterns = [
    path('', views.AlunoListView.as_view(), name='lista'),
    path('novo/', views.EtapaDadosView.as_view(), name='criar'),
    path('<int:pk>/', views.AlunoDetailView.as_view(), name='detalhe'),
    path('<int:pk>/dados/', views.EtapaDadosView.as_view(), name='etapa_dados'),
    path('<int:pk>/responsaveis/', views.EtapaResponsaveisView.as_view(), name='etapa_responsaveis'),
    path('<int:pk>/familia/', views.EtapaFamiliaView.as_view(), name='etapa_familia'),
    path(
        '<int:pk>/responsaveis/<int:vinculo_pk>/editar/',
        views.ResponsavelEditarView.as_view(), name='responsavel_editar',
    ),
    path(
        '<int:pk>/responsaveis/<int:vinculo_pk>/remover/',
        views.ResponsavelRemoverView.as_view(), name='responsavel_remover',
    ),
    path('responsaveis/buscar/', views.BuscarResponsavelView.as_view(), name='buscar_responsavel'),
]
