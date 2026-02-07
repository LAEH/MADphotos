/* bento.js — Le Bento: Elevated mosaic card.
   A single beautiful composition of ~8 images in a centered card
   with generous space around it. Horizontal on desktop, vertical
   on mobile. Crossfades individual tiles. */

let bentoPhotos = [];

function initBento() {
    const container = document.getElementById('view-bento');
    container.innerHTML = '';
    container.className = 'view active bento-view';

    generateBento();

    /* Crossfade one tile every 20s */
    registerTimer(setInterval(crossfadeOneTile, 20000));

    /* Space reshuffles */
    document.addEventListener('keydown', bentoKeyHandler);
}

function bentoKeyHandler(e) {
    if (APP.currentView !== 'bento') return;
    if (e.code === 'Space') {
        e.preventDefault();
        generateBento();
    }
}

function generateBento() {
    const photos = APP.data.photos.filter(p => p.thumb && p.aesthetic);
    const sorted = [...photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    const pool = sorted.slice(0, 200);

    /* Pick 8 images with chromatic harmony */
    const seed = randomFrom(pool);
    const selected = [seed];
    const remaining = pool.filter(p => p.id !== seed.id);

    for (let i = 0; i < 7 && remaining.length > 0; i++) {
        let bestIdx = 0;
        let bestScore = -1;

        for (let j = 0; j < Math.min(remaining.length, 50); j++) {
            const candidate = remaining[j];
            let colorDist = Math.abs((seed.hue || 0) - (candidate.hue || 0));
            if (colorDist > 180) colorDist = 360 - colorDist;
            const harmonyScore = colorDist < 60 ? 10 : (colorDist > 150 ? 8 : 3);
            const aestheticBonus = (candidate.aesthetic || 5) / 2;
            const score = harmonyScore + aestheticBonus;

            if (score > bestScore) {
                bestScore = score;
                bestIdx = j;
            }
        }

        selected.push(remaining[bestIdx]);
        remaining.splice(bestIdx, 1);
    }

    bentoPhotos = selected;
    renderBentoGrid(selected);
}

function renderBentoGrid(photos) {
    const container = document.getElementById('view-bento');
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'bento-wrap';

    const card = document.createElement('div');
    card.className = 'bento-card';
    card.id = 'bento-grid';

    const mobile = window.matchMedia('(max-width: 768px)').matches;

    if (mobile) {
        /* Vertical: 4 rows of 2 */
        const rows = [[0,1],[2,3],[4,5],[6,7]];
        for (const [a, b] of rows) {
            const row = document.createElement('div');
            row.className = 'bento-row';
            if (photos[a]) row.appendChild(makeBentoTile(photos[a]));
            if (photos[b]) row.appendChild(makeBentoTile(photos[b]));
            card.appendChild(row);
        }
    } else {
        /* Horizontal: 2 rows of 4 */
        const rows = [[0,1,2,3],[4,5,6,7]];
        for (const indices of rows) {
            const row = document.createElement('div');
            row.className = 'bento-row';
            for (const i of indices) {
                if (photos[i]) row.appendChild(makeBentoTile(photos[i]));
            }
            card.appendChild(row);
        }
    }

    wrap.appendChild(card);

    /* Regenerate button */
    const btn = document.createElement('button');
    btn.className = 'bento-regen';
    btn.textContent = '\uD83C\uDFB2';
    btn.addEventListener('click', generateBento);
    wrap.appendChild(btn);

    container.appendChild(wrap);
}

function makeBentoTile(photo) {
    const tile = document.createElement('div');
    tile.className = 'bento-tile';
    tile.dataset.id = photo.id;

    const img = document.createElement('img');
    loadProgressive(img, photo, 'display');
    img.alt = '';
    tile.appendChild(img);

    tile.addEventListener('click', () => openLightbox(photo));
    return tile;
}

function crossfadeOneTile() {
    if (APP.currentView !== 'bento') return;

    const tiles = document.querySelectorAll('.bento-tile');
    if (tiles.length === 0) return;

    const tileIdx = Math.floor(Math.random() * tiles.length);
    const tile = tiles[tileIdx];
    const oldId = tile.dataset.id;

    const currentIds = new Set(bentoPhotos.map(p => p.id));
    const pool = APP.data.photos.filter(p => p.thumb && p.aesthetic && !currentIds.has(p.id));
    if (pool.length === 0) return;

    const newPhoto = randomFrom(pool);

    tile.style.opacity = '0';

    const onFadeOut = () => {
        tile.removeEventListener('transitionend', onFadeOut);

        const img = tile.querySelector('img');
        const target = newPhoto.display || newPhoto.thumb;
        const preload = new Image();
        preload.decoding = 'async';
        preload.onload = () => {
            img.src = target;
            img.classList.remove('img-loading');
            img.classList.remove('img-loaded');
            img.alt = '';
            tile.dataset.id = newPhoto.id;

            const bIdx = bentoPhotos.findIndex(p => p.id === oldId);
            if (bIdx >= 0) bentoPhotos[bIdx] = newPhoto;

            tile.onclick = () => openLightbox(newPhoto);
            requestAnimationFrame(() => { tile.style.opacity = '1'; });
        };
        preload.onerror = () => {
            requestAnimationFrame(() => { tile.style.opacity = '1'; });
        };
        preload.src = target;
    };

    tile.addEventListener('transitionend', onFadeOut);
    setTimeout(() => {
        if (tile.style.opacity === '0') onFadeOut();
    }, 1000);
}
