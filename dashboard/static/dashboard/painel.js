(() => {
    const caixa = document.querySelector('[data-grafico]');
    if (!caixa) return;
    const svg = caixa.querySelector('svg');
    const dica = caixa.querySelector('.grafico-dica');
    const mira = caixa.querySelector('.mira');
    const largura = svg.viewBox.baseVal.width;
    const esconder = () => {
        dica.hidden = true;
        mira.setAttribute('visibility', 'hidden');
    };

    caixa.querySelectorAll('.alvo').forEach(alvo => {
        const x = Number(alvo.dataset.x);
        const meia = Number(alvo.dataset.meia);
        const esquerda = Math.max(0, x - meia);
        alvo.setAttribute('x', esquerda);
        alvo.setAttribute('width', Math.min(largura, x + meia) - esquerda);

        const mostrar = () => {
            dica.textContent = alvo.dataset.texto;
            dica.hidden = false;
            const meiaDica = dica.offsetWidth / 2;
            const centro = caixa.clientWidth * x / largura;
            dica.style.left = Math.min(caixa.clientWidth - meiaDica - 8, Math.max(meiaDica + 8, centro)) + 'px';
            mira.setAttribute('x1', x);
            mira.setAttribute('x2', x);
            mira.setAttribute('visibility', 'visible');
        };
        alvo.addEventListener('pointerenter', mostrar);
        alvo.addEventListener('focus', mostrar);
        alvo.addEventListener('click', mostrar);
        alvo.addEventListener('pointerleave', esconder);
        alvo.addEventListener('blur', esconder);
        alvo.addEventListener('keydown', evento => {
            if (evento.key === 'Escape') esconder();
        });
    });
    document.addEventListener('pointerdown', evento => {
        if (!caixa.contains(evento.target)) esconder();
    });
})();
