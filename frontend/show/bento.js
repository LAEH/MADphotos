/* bento.js — Le Bento: Algorithmic Mondrian mosaic */

let bentoPhotos = [];

function initBento() {
    const container = document.getElementById('view-bento');
    container.innerHTML = '';
    container.className = 'view active bento-view';

    const grid = document.createElement('div');
    grid.className = 'bento-grid';
    grid.id = 'bento-grid';
    container.appendChild(grid);

    /* Hint overlay */
    const hint = document.createElement('div');
    hint.className = 'bento-hint';
    hint.textContent = 'Space to reshuffle';
    container.appendChild(hint);
    setTimeout(() => hint.style.opacity = '0', 3000);

    generateBento();

    /* Crossfade one tile every 45s — registered for cleanup */
    registerTimer(setInterval(crossfadeOneTile, 45000));

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

    /* Sort by aesthetic score, take top tier */
    const sorted = [...photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    const pool = sorted.slice(0, 200);

    /* Pick 12 images for chromatic harmony */
    const seed = randomFrom(pool);
    const selected = [seed];
    const remaining = pool.filter(p => p.id !== seed.id);

    for (let i = 0; i < 11 && remaining.length > 0; i++) {
        let bestIdx = 0;
        let bestScore = -1;

        for (let j = 0; j < Math.min(remaining.length, 50); j++) {
            const candidate = remaining[j];
            let colorDist = 0;
            const pal1 = seed.palette || [];
            const pal2 = candidate.palette || [];
            if (pal1.length && pal2.length) {
                colorDist = Math.abs((seed.hue || 0) - (candidate.hue || 0));
                if (colorDist > 180) colorDist = 360 - colorDist;
            }
            const harmonyScore = colorDist < 60 ? 10 : (colorDist > 150 && colorDist < 210 ? 8 : 3);
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
    const grid = document.getElementById('bento-grid');
    grid.innerHTML = '';

    const vh = window.innerHeight - HEADER_HEIGHT;
    const vw = window.innerWidth;

    /* Mondrian-style layout: 3 rows */
    let idx = 0;
    const rowHeights = [0.35, 0.35, 0.30];

    for (let r = 0; r < 3 && idx < photos.length; r++) {
        const rowH = Math.floor(vh * rowHeights[r]);
        const tilesInRow = r === 1 ? Math.min(4, photos.length - idx) : Math.min(3, photos.length - idx);
        const rowPhotos = photos.slice(idx, idx + tilesInRow);
        idx += tilesInRow;

        const totalAspect = rowPhotos.reduce((s, p) => s + (p.aspect || 1.5), 0);

        for (const photo of rowPhotos) {
            const tileW = Math.floor(vw * ((photo.aspect || 1.5) / totalAspect));

            const tile = document.createElement('div');
            tile.className = 'bento-tile';
            tile.style.width = tileW + 'px';
            tile.style.height = rowH + 'px';
            tile.dataset.id = photo.id;

            const img = document.createElement('img');
            loadProgressive(img, photo, 'display');
            img.alt = photo.alt || photo.caption || '';
            tile.appendChild(img);

            const caption = document.createElement('div');
            caption.className = 'bento-caption';
            caption.textContent = photo.caption || photo.alt || '';
            tile.appendChild(caption);

            tile.addEventListener('click', () => openLightbox(photo));
            grid.appendChild(tile);
        }
    }
}

function crossfadeOneTile() {
    if (APP.currentView !== 'bento') return;

    const tiles = document.querySelectorAll('.bento-tile');
    if (tiles.length === 0) return;

    const tileIdx = Math.floor(Math.random() * tiles.length);
    const tile = tiles[tileIdx];
    const oldId = tile.dataset.id;

    /* Pick a new photo not already in the grid */
    const currentIds = new Set(bentoPhotos.map(p => p.id));
    const pool = APP.data.photos.filter(p => p.thumb && p.aesthetic && !currentIds.has(p.id));
    if (pool.length === 0) return;

    const newPhoto = randomFrom(pool);

    /* CSS transition crossfade: fade out, swap, fade in */
    tile.style.opacity = '0';

    /* Wait for CSS transition to complete, then swap content */
    const onFadeOut = () => {
        tile.removeEventListener('transitionend', onFadeOut);

        const img = tile.querySelector('img');
        const caption = tile.querySelector('.bento-caption');
        loadProgressive(img, newPhoto, 'display');
        img.alt = newPhoto.alt || newPhoto.caption || '';
        caption.textContent = newPhoto.caption || newPhoto.alt || '';
        tile.dataset.id = newPhoto.id;

        /* Update bentoPhotos */
        const bIdx = bentoPhotos.findIndex(p => p.id === oldId);
        if (bIdx >= 0) bentoPhotos[bIdx] = newPhoto;

        /* Rebind click */
        tile.onclick = () => openLightbox(newPhoto);

        /* Fade in */
        requestAnimationFrame(() => { tile.style.opacity = '1'; });
    };

    tile.addEventListener('transitionend', onFadeOut);

    /* Safety: if transition doesn't fire (e.g. reduced motion), run after timeout */
    setTimeout(() => {
        if (tile.style.opacity === '0') onFadeOut();
    }, 1000);
}
