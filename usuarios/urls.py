from django.urls import path

from . import views

app_name = 'usuarios'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', views.LogoutView.as_view(), name='logout'),
    path('', views.UsuarioListView.as_view(), name='lista'),
    path('novo/', views.UsuarioCreateView.as_view(), name='criar'),
    path('<int:pk>/editar/', views.UsuarioUpdateView.as_view(), name='editar'),
    path('<int:pk>/ativo/', views.UsuarioToggleAtivoView.as_view(), name='alternar_ativo'),
]
