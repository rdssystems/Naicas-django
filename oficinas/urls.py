from django.urls import path
from . import views

app_name = 'oficinas'
urlpatterns = [
    path('', views.OficinaListView.as_view(), name='lista'),
    path('nova/', views.OficinaCreateView.as_view(), name='criar'),
    path('<int:pk>/', views.OficinaDetailView.as_view(), name='detalhe'),
    path('<int:pk>/editar/', views.OficinaUpdateView.as_view(), name='editar'),
    path('<int:pk>/arquivar/', views.ArquivarOficinaView.as_view(), name='arquivar'),
    path('<int:pk>/excluir/', views.ExcluirOficinaView.as_view(), name='excluir'),
    path('tipos/', views.CatalogoAntigoView.as_view(), name='tipos'),
    path('tipos/novo/', views.CatalogoAntigoView.as_view(), name='tipo_criar'),
    path('tipos/<int:pk>/editar/', views.CatalogoAntigoView.as_view(), name='tipo_editar'),
    path('tipos/<int:pk>/excluir/', views.CatalogoAntigoView.as_view(), name='tipo_excluir'),
]
