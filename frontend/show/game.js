/* game.js — Le Jeu: Curated image pairs, viewport-fixed.
   Two images, same ratio, thumbs up/down on fixed glass bar. */

let jeuState = null;

function initGame() {
    const container = document.getElementById('view-game');
    container.innerHTML = '';

    const sim = APP.data.similarity || {};
    const pool = [];

    for (const [id, neighbors] of Object.entries(sim)) {
        const photo = APP.photoMap[id];
        if (!photo || !photo.thumb) continue;
        for (const n of neighbors.slice(0, 2)) {
            const other = APP.photoMap[n.id];
            if (!other || !other.thumb) continue;
            pool.push({ a: photo, b: other });
        }
    }

    if (pool.length === 0) {
        container.innerHTML = '<div class="loading">No pairs available.</div>';
        return;
    }

    jeuState = { pool: shuffleArray(pool), index: 0 };

    /* Build persistent structure: pair area + fixed glass bar */
    const wrap = document.createElement('div');
    wrap.className = 'jeu-container';

    const pairEl = document.createElement('div');
    pairEl.className = 'jeu-pair';
    pairEl.id = 'jeu-pair';
    wrap.appendChild(pairEl);

    const bar = document.createElement('div');
    bar.className = 'jeu-bar';

    const downBtn = document.createElement('button');
    downBtn.className = 'jeu-btn';
    downBtn.textContent = '\uD83D\uDC4E';
    downBtn.addEventListener('click', nextJeuPair);
    bar.appendChild(downBtn);

    const upBtn = document.createElement('button');
    upBtn.className = 'jeu-btn';
    upBtn.textContent = '\uD83D\uDC4D';
    upBtn.addEventListener('click', nextJeuPair);
    bar.appendChild(upBtn);

    wrap.appendChild(bar);
    container.appendChild(wrap);

    renderJeuPair();
}

function nextJeuPair() {
    const pairEl = document.getElementById('jeu-pair');
    if (!pairEl) return;

    /* Fade out current pair */
    pairEl.classList.add('jeu-pair-exit');

    setTimeout(() => {
        jeuState.index++;
        renderJeuPair();
    }, 300);
}

function renderJeuPair() {
    const pairEl = document.getElementById('jeu-pair');
    if (!pairEl) return;

    const js = jeuState;
    if (js.index >= js.pool.length) {
        js.index = 0;
        js.pool = shuffleArray(js.pool);
    }

    const pair = js.pool[js.index];

    pairEl.innerHTML = '';
    pairEl.classList.remove('jeu-pair-exit');
    pairEl.classList.add('jeu-pair-enter');

    for (const photo of [pair.a, pair.b]) {
        const card = document.createElement('div');
        card.className = 'jeu-card';
        const img = document.createElement('img');
        img.className = 'jeu-img clickable-img';
        loadProgressive(img, photo, 'display');
        img.alt = '';
        img.addEventListener('click', () => openLightbox(photo));
        card.appendChild(img);
        pairEl.appendChild(card);
    }

    /* Remove enter class after animation */
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            pairEl.classList.remove('jeu-pair-enter');
        });
    });
}
