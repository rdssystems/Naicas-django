from django.urls import path

from . import views

app_name = 'escolas'

urlpatterns = [
    path('', views.EscolaListView.as_view(), name='lista'),
    path('nova/', views.EscolaCreateView.as_view(), name='criar'),
    path('<int:pk>/editar/', views.EscolaUpdateView.as_view(), name='editar'),
    path('foco/', views.SelecionarFocoView.as_view(), name='selecionar_foco'),
]
