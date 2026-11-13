(() => {
    'use strict';

    const voltar = document.querySelector('[data-voltar]');
    if (voltar) {
        voltar.addEventListener('click', (event) => {
            if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
            if (voltar.dataset.historico !== 'true' || window.history.length < 2) return;
            let anterior;
            try {
                anterior = new URL(document.referrer);
            } catch {
                return;
            }
            if (anterior.origin !== window.location.origin || anterior.href === window.location.href) return;
            event.preventDefault();
            window.history.back();
        });
    }

    const menu = document.getElementById('menu-principal');
    const pagina = document.getElementById('pagina-app');
    const abrir = document.getElementById('abrir-menu');
    if (!menu || !pagina || !abrir) return;

    // Mesma condição do menu horizontal em naicas.css.
    const desktop = window.matchMedia('(min-width: 992px)');
    const liberarPagina = () => {
        pagina.inert = false;
        abrir.setAttribute('aria-expanded', 'false');
    };
    const fecharMenu = () => window.bootstrap?.Offcanvas.getInstance(menu)?.hide();

    menu.addEventListener('show.bs.offcanvas', (event) => {
        if (desktop.matches) {
            event.preventDefault();
            return;
        }
        pagina.inert = true;
        abrir.setAttribute('aria-expanded', 'true');
    });
    menu.addEventListener('hidden.bs.offcanvas', () => {
        liberarPagina();
        const destino = desktop.matches ? document.querySelector('.navbar-brand') : abrir;
        destino?.focus({ preventScroll: true });
    });
    menu.addEventListener('click', (event) => {
        const link = event.target.closest('a[href]');
        if (link && !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) {
            fecharMenu();
        }
    });
    desktop.addEventListener('change', () => {
        if (!desktop.matches) return;
        fecharMenu();
        liberarPagina();
    });
    window.addEventListener('pageshow', (event) => {
        if (!event.persisted) return;
        const aberto = menu.classList.contains('show') || menu.classList.contains('showing');
        if (aberto) {
            fecharMenu();
        } else {
            liberarPagina();
        }
    });
})();
