from django.urls import path

from . import views

app_name = 'oficinas'

urlpatterns = [
    path('', views.OficinaListView.as_view(), name='lista'),
    path('nova/', views.OficinaCreateView.as_view(), name='criar'),
    path('<int:pk>/', views.OficinaDetailView.as_view(), name='detalhe'),
    path('<int:pk>/editar/', views.OficinaUpdateView.as_view(), name='editar'),
    path('tipos/', views.TipoOficinaListView.as_view(), name='tipos'),
    path('tipos/novo/', views.TipoOficinaCreateView.as_view(), name='tipo_criar'),
    path('tipos/<int:pk>/editar/', views.TipoOficinaUpdateView.as_view(), name='tipo_editar'),
    path('tipos/<int:pk>/excluir/', views.TipoOficinaDeleteView.as_view(), name='tipo_excluir'),
]
