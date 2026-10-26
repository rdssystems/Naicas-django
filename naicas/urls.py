"""URLs raiz do Naicas: só inclui as URLs de cada app, cada um com namespace próprio."""

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
    path('escalas/', include('escalas.urls')),
    path('', include('core.urls')),
]

# /media/ NÃO é servido (nem em dev): os anexos têm dados pessoais e só saem
# pela view autenticada anexos:arquivo, que checa a visibilidade do aluno.

handler403 = 'core.views.erro_403'
