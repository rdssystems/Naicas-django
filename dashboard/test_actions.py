from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

from django.contrib.staticfiles import finders
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from alunos.models import Aluno
from escolas.foco import CHAVE_SESSAO

from .tests import BaseDashboardTestCase


class ControlesPainel(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.ids = []
        self.forms = []
        self.form = None
        self.link = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if tag == 'a':
            attrs['_texto'] = ''
            self.link = attrs
            self.links.append(attrs)
        elif tag == 'form':
            self.form = {'attrs': attrs, 'inputs': {}}
            self.forms.append(self.form)
        elif tag == 'input' and self.form is not None and attrs.get('name'):
            self.form['inputs'][attrs['name']] = attrs.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'a':
            self.link = None
        if tag == 'form':
            self.form = None

    def handle_data(self, data):
        if self.link is not None:
            self.link['_texto'] += data


class AcoesPainelTests(BaseDashboardTestCase):
    def abrir(self, user=None, params=None):
        self.client.force_login(user or self.diretor)
        resposta = self.client.get(reverse('dashboard:painel'), params or {})
        self.assertEqual(resposta.status_code, 200)
        return resposta, ControlesPainel(resposta.content.decode())

    def verificar_destinos(self, controles):
        self.assertEqual(len(controles.ids), len(set(controles.ids)), 'IDs duplicados no painel')
        destinos = set()
        for link in controles.links:
            href = link.get('href', '')
            if href == '#' and link.get('data-bs-toggle'):
                continue  # Menus Bootstrap da navegação comum.
            self.assertTrue(href, 'Link sem destino')
            if href.startswith('#'):
                self.assertIn(href[1:], controles.ids)
            elif href.startswith('/'):
                destinos.add(href)
            else:
                self.fail(f'Destino inesperado: {href}')
        for destino in destinos:
            with self.subTest(destino=destino):
                self.assertEqual(self.client.get(destino).status_code, 200)

    def test_tema_compartilhado_dados_reais_e_arquivos_existentes(self):
        resposta, _ = self.abrir()
        self.assertTemplateUsed(resposta, 'core/base.html')
        self.assertContains(resposta, 'Olá, diretor')
        self.assertContains(resposta, 'navbar-naicas')
        self.assertContains(resposta, 'dashboard/painel.css')
        self.assertContains(resposta, 'dashboard/painel.js')
        self.assertTrue(finders.find('dashboard/painel.css'))
        self.assertTrue(finders.find('dashboard/painel.js'))
        for texto in ('SkillPath', 'ui-avatars.com', 'Enrolled Courses', 'Teacher Dashboard',
                      'UI Widgets', 'Training Hours', 'Certificates Earned'):
            self.assertNotContains(resposta, texto)

    def test_todos_os_links_e_ancoras_do_diretor_tem_destino(self):
        from datetime import timedelta
        for dias in (1, 8, 15):
            self.lancar(self.danca, timezone.localdate() - timedelta(days=dias), {self.ana: 'P', self.bia: 'F'})
        Aluno.objects.filter(pk=self.caio.pk).update(turno=None)
        resposta, controles = self.abrir()
        self.assertContains(resposta, 'Ver dados por semana')
        self.assertContains(resposta, 'Classificar atendidos')
        self.assertContains(resposta, 'Vincular oficina')
        self.verificar_destinos(controles)

    def test_coordenador_tem_apenas_acoes_e_dados_do_seu_escopo(self):
        resposta, controles = self.abrir(self.coord_alfa)
        self.assertNotIn('unidades', controles.ids)
        self.assertNotContains(resposta, 'Naica Beta')
        self.assertNotContains(resposta, f'href="{reverse("usuarios:lista")}"')
        self.assertNotContains(resposta, reverse('escolas:selecionar_foco'))
        self.verificar_destinos(controles)

    def test_chamada_rapida_recebe_unidade_e_data_selecionadas(self):
        _, controles = self.abrir(params={'escola': self.beta.pk})
        chamadas = [urlsplit(link['href']) for link in controles.links
                    if link['_texto'].strip() == 'Fazer chamada geral']
        self.assertEqual(len(chamadas), 1)
        for chamada in chamadas:
            params = parse_qs(chamada.query)
            self.assertEqual(params['escola'], [str(self.beta.pk)])
            self.assertEqual(params['data'], [timezone.localdate().isoformat()])

    def test_classificar_alunos_abre_lista_correta_inclusive_campos_vazios(self):
        Aluno.objects.filter(pk=self.caio.pk).update(turno='', turma='')
        Aluno.objects.filter(pk=self.bruno.pk).update(turno=None)
        resposta, _ = self.abrir(params={'escola': self.alfa.pk})
        destino = resposta.context['url_alunos_pendentes']
        self.assertEqual(parse_qs(urlsplit(destino).query),
                         {'classificacao': ['pendente'], 'escola': [str(self.alfa.pk)]})
        alunos = self.client.get(destino).context['alunos']
        self.assertEqual(list(alunos), [self.caio])

    def test_entrar_na_unidade_envia_post_com_csrf_e_preserva_filtros(self):
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.diretor)
        resposta = cliente.get(reverse('dashboard:painel'), {'sexo': 'F'})
        controles = ControlesPainel(resposta.content.decode())
        formulario = next(form for form in controles.forms
                          if form['attrs'].get('action') == reverse('escolas:selecionar_foco')
                          and form['inputs'].get('escola') == str(self.alfa.pk)
                          and form['inputs'].get('next'))
        self.assertEqual(formulario['attrs']['method'].lower(), 'post')
        self.assertTrue(formulario['inputs']['csrfmiddlewaretoken'])
        resposta = cliente.post(formulario['attrs']['action'], formulario['inputs'], follow=True)
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(cliente.session[CHAVE_SESSAO], self.alfa.pk)
        self.assertEqual(resposta.context['unidade_painel'], self.alfa)
        self.assertEqual(resposta.context['filtros'].cleaned_data['sexo'], 'F')

    def test_filtros_invalidos_nao_criam_ancoras_sem_secao(self):
        resposta, controles = self.abrir(params={'idade': 'abc'})
        self.assertContains(resposta, 'Revise os filtros indicados')
        self.assertNotContains(resposta, 'data-grafico')
        self.verificar_destinos(controles)
