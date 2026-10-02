"""URLs raiz do Naicas: só inclui as URLs de cada app, cada um com namespace próprio."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('usuarios/', include('usuarios.urls')),
    path('escolas/', include('escolas.urls')),
    path('oficinas/', include('oficinas.urls')),
    path('alunos/', include('alunos.urls')),
    path('anexos/', include('anexos.urls')),
    path('matriculas/', include('matriculas.urls')),
    path('frequencia/', include('frequencia.urls')),
    path('', include('core.urls')),
]

if settings.DEBUG:
    # Só em dev. Em produção, anexos (dados pessoais) são servidos por view autenticada.
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
