const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const { test } = require('node:test');
const vm = require('node:vm');

const script = readFileSync(resolve(__dirname, '../static/core/navegacao.js'), 'utf8');

function elemento() {
    const eventos = new Map();
    const classes = new Set();
    return {
        inert: false, dataset: {}, attrs: {}, focos: 0,
        classList: { contains: (nome) => classes.has(nome), add: (nome) => classes.add(nome), remove: (nome) => classes.delete(nome) },
        addEventListener: (nome, callback) => eventos.set(nome, callback),
        emitir: (nome, evento = {}) => eventos.get(nome)?.(evento),
        setAttribute(nome, valor) { this.attrs[nome] = valor; },
        focus() { this.focos += 1; },
    };
}

function tela({ anterior = 'https://naica.exemplo/alunos/?page=2', historico = true, tamanho = 3, desktop = false } = {}) {
    const pagina = elemento(), menu = elemento(), abrir = elemento(), voltar = elemento(), janela = elemento();
    const media = Object.assign(elemento(), { matches: desktop }), inicio = elemento();
    const chamadas = { voltar: 0, fechar: 0 };
    voltar.dataset.historico = String(historico);
    const nodes = { 'pagina-app': pagina, 'menu-principal': menu, 'abrir-menu': abrir };
    const window = Object.assign(janela, {
        location: { origin: 'https://naica.exemplo', href: 'https://naica.exemplo/alunos/1/' },
        history: { length: tamanho, back() { chamadas.voltar += 1; } },
        matchMedia: () => media,
        bootstrap: { Offcanvas: { getInstance() { return { hide() {
            chamadas.fechar += 1;
            menu.classList.remove('show');
            menu.emitir('hidden.bs.offcanvas');
        } }; } } },
    });
    vm.runInNewContext(script, { window, URL, document: {
        referrer: anterior, querySelector: (seletor) => seletor === '.navbar-brand' ? inicio : voltar,
        getElementById: (id) => nodes[id],
    } });
    return { pagina, menu, abrir, voltar, window, chamadas, media, inicio };
}

function clique(extra = {}) {
    return Object.assign({ button: 0, preventDefault() { this.impedido = true; } }, extra);
}

test('menu bloqueia a pagina e devolve o foco ao fechar', () => {
    const t = tela();
    t.menu.emitir('show.bs.offcanvas');
    assert.equal(t.pagina.inert, true);
    assert.equal(t.abrir.attrs['aria-expanded'], 'true');
    t.menu.emitir('hidden.bs.offcanvas');
    assert.equal(t.pagina.inert, false);
    assert.equal(t.abrir.attrs['aria-expanded'], 'false');
    assert.equal(t.abrir.focos, 1);
});

test('voltar recupera a entrada anterior do historico', () => {
    const t = tela(), evento = clique();
    t.voltar.emitir('click', evento);
    assert.equal(t.chamadas.voltar, 1);
    assert.equal(evento.impedido, true);
});

test('acesso direto e referencia externa usam o link local sem sair pelo historico', () => {
    for (const opcoes of [{ anterior: 'https://outro.exemplo/' }, { anterior: '' }, { tamanho: 1 }, { historico: false }]) {
        const t = tela(opcoes), evento = clique();
        t.voltar.emitir('click', evento);
        assert.equal(t.chamadas.voltar, 0);
        assert.equal(evento.impedido, undefined);
    }
});

test('atalho para abrir link em outra aba continua funcionando', () => {
    const t = tela(), evento = clique({ ctrlKey: true });
    t.voltar.emitir('click', evento);
    assert.equal(t.chamadas.voltar, 0);
    assert.equal(evento.impedido, undefined);
});

test('selecionar um destino fecha o menu sem alterar a navegacao do link', () => {
    const t = tela();
    t.menu.emitir('show.bs.offcanvas');
    t.menu.emitir('click', { target: { closest: () => ({ href: '/oficinas/' }) } });
    assert.equal(t.chamadas.fechar, 1);
    assert.equal(t.pagina.inert, false);
});

test('retorno pelo cache do navegador nao deixa a pagina bloqueada', () => {
    const t = tela();
    t.menu.classList.add('show');
    t.pagina.inert = true;
    t.window.emitir('pageshow', { persisted: true });
    assert.equal(t.chamadas.fechar, 1);
    assert.equal(t.pagina.inert, false);
});

test('ampliar a janela fecha o painel e devolve o foco a um controle visivel no desktop', () => {
    const t = tela();
    t.menu.classList.add('show');
    t.menu.emitir('show.bs.offcanvas');
    t.media.matches = true;
    t.media.emitir('change');
    assert.equal(t.chamadas.fechar, 1);
    assert.equal(t.menu.classList.contains('show'), false);
    assert.equal(t.pagina.inert, false);
    assert.equal(t.abrir.attrs['aria-expanded'], 'false');
    assert.equal(t.abrir.focos, 0);
    assert.equal(t.inicio.focos, 1);
});

test('desktop impede abertura modal e voltar ao modo tablet permite usar o painel', () => {
    const t = tela({ desktop: true }), evento = clique();
    t.menu.emitir('show.bs.offcanvas', evento);
    assert.equal(evento.impedido, true);
    assert.equal(t.pagina.inert, false);
    t.media.matches = false;
    t.media.emitir('change');
    const eventoTablet = clique();
    t.menu.emitir('show.bs.offcanvas', eventoTablet);
    assert.equal(eventoTablet.impedido, undefined);
    assert.equal(t.pagina.inert, true);
});
