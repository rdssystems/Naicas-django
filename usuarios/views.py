from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.models import User
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from core.acesso import NivelAcesso
from core.mixins import DiretorRequiredMixin
from escolas.models import EscolaNaica

from .forms import UsuarioForm


class LoginView(auth_views.LoginView):
    template_name = 'usuarios/login.html'
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    pass


class UsuarioListView(DiretorRequiredMixin, ListView):
    template_name = 'usuarios/usuario_list.html'
    context_object_name = 'usuarios'
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.select_related('profile', 'profile__escola').order_by(
            'first_name', 'username'
        )
        params = self.request.GET
        if busca := params.get('q', '').strip():
            qs = qs.filter(
                Q(username__icontains=busca)
                | Q(first_name__icontains=busca)
                | Q(last_name__icontains=busca)
            )
        if nivel := params.get('nivel'):
            qs = qs.filter(profile__nivel_acesso=nivel)
        if escola := params.get('escola'):
            qs = qs.filter(profile__escola_id=escola)
        if params.get('status') == 'inativos':
            qs = qs.filter(is_active=False)
        elif params.get('status') != 'todos':
            qs = qs.filter(is_active=True)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['niveis'] = NivelAcesso.choices
        context['escolas'] = EscolaNaica.objects.all()
        filtros = self.request.GET.copy()
        filtros.pop('page', None)
        context['filtros_querystring'] = filtros.urlencode()
        return context


class UsuarioFormMixin:
    model = User
    form_class = UsuarioForm
    template_name = 'usuarios/usuario_form.html'
    success_url = reverse_lazy('usuarios:lista')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['usuario_logado'] = self.request.user
        return kwargs


class UsuarioCreateView(DiretorRequiredMixin, UsuarioFormMixin, CreateView):
    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Usuário "{self.object.username}" criado.')
        return response


class UsuarioUpdateView(DiretorRequiredMixin, UsuarioFormMixin, UpdateView):
    context_object_name = 'usuario'

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, f'Usuário "{self.object.username}" atualizado.')
        return response


class UsuarioToggleAtivoView(DiretorRequiredMixin, View):
    """Desativar em vez de excluir: preserva o histórico (ex.: quem lançou chamadas)."""

    http_method_names = ['post']

    def post(self, request, pk):
        usuario = get_object_or_404(User, pk=pk)
        if usuario.pk == request.user.pk:
            messages.error(request, 'Você não pode desativar a sua própria conta.')
        else:
            usuario.is_active = not usuario.is_active
            usuario.save(update_fields=['is_active'])
            estado = 'reativado' if usuario.is_active else 'desativado'
            messages.success(request, f'Usuário "{usuario.username}" {estado}.')
        return redirect('usuarios:lista')
