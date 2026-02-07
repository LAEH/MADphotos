/* bento.js — Le Bento: Irregular mosaic of mixed portrait & landscape images.
   Multiple layout templates. Crossfade tiles. Desktop only. */

let bentoPhotos = [];
let bentoLayout = null;
let bentoLayoutIdx = -1;

const BENTO_LAYOUTS = [
    /* "Classic" — 8 images, 4x4 grid */
    {
        cols: 4, rows: 4, count: 8,
        cells: [
            { r: 1, c: 1, rs: 2, cs: 2, pref: 'landscape' },
            { r: 1, c: 3, rs: 2, cs: 1, pref: 'portrait' },
            { r: 1, c: 4, rs: 1, cs: 1 },
            { r: 2, c: 4, rs: 2, cs: 1, pref: 'portrait' },
            { r: 3, c: 1, rs: 2, cs: 1, pref: 'portrait' },
            { r: 3, c: 2, rs: 1, cs: 2, pref: 'landscape' },
            { r: 4, c: 2, rs: 1, cs: 2, pref: 'landscape' },
            { r: 4, c: 4, rs: 1, cs: 1 },
        ]
    },
    /* "Stagger" — 7 images, 4x3 grid */
    {
        cols: 4, rows: 3, count: 7,
        cells: [
            { r: 1, c: 1, rs: 1, cs: 2, pref: 'landscape' },
            { r: 1, c: 3, rs: 1, cs: 1 },
            { r: 1, c: 4, rs: 2, cs: 1, pref: 'portrait' },
            { r: 2, c: 1, rs: 2, cs: 1, pref: 'portrait' },
            { r: 2, c: 2, rs: 1, cs: 2, pref: 'landscape' },
            { r: 3, c: 2, rs: 1, cs: 1 },
            { r: 3, c: 3, rs: 1, cs: 2, pref: 'landscape' },
        ]
    },
    /* "Panoramic" — 7 images, 5x3 grid */
    {
        cols: 5, rows: 3, count: 7,
        cells: [
            { r: 1, c: 1, rs: 1, cs: 3, pref: 'landscape' },
            { r: 1, c: 4, rs: 1, cs: 2, pref: 'landscape' },
            { r: 2, c: 1, rs: 2, cs: 1, pref: 'portrait' },
            { r: 2, c: 2, rs: 1, cs: 2, pref: 'landscape' },
            { r: 2, c: 4, rs: 1, cs: 2, pref: 'landscape' },
            { r: 3, c: 2, rs: 1, cs: 2, pref: 'landscape' },
            { r: 3, c: 4, rs: 1, cs: 2, pref: 'landscape' },
        ]
    },
    /* "Tower" — 8 images, 3x4 grid */
    {
        cols: 3, rows: 4, count: 8,
        cells: [
            { r: 1, c: 1, rs: 2, cs: 1, pref: 'portrait' },
            { r: 1, c: 2, rs: 1, cs: 2, pref: 'landscape' },
            { r: 2, c: 2, rs: 1, cs: 1 },
            { r: 2, c: 3, rs: 2, cs: 1, pref: 'portrait' },
            { r: 3, c: 1, rs: 1, cs: 2, pref: 'landscape' },
            { r: 4, c: 1, rs: 1, cs: 1 },
            { r: 4, c: 2, rs: 1, cs: 1 },
            { r: 4, c: 3, rs: 1, cs: 1 },
        ]
    },
];

function initBento() {
    const container = document.getElementById('view-bento');
    container.innerHTML = '';
    container.className = 'view active bento-view';

    generateBento();

    registerTimer(setInterval(crossfadeOneTile, 20000));
    document.removeEventListener('keydown', bentoKeyHandler);
    document.addEventListener('keydown', bentoKeyHandler);
}

function bentoKeyHandler(e) {
    if (APP.currentView !== 'bento') return;
    if (e.code === 'Space') {
        e.preventDefault();
        generateBento();
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        bentoCycle(1);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        bentoCycle(-1);
    }
}

function bentoCycle(dir) {
    bentoLayoutIdx = (bentoLayoutIdx + dir + BENTO_LAYOUTS.length) % BENTO_LAYOUTS.length;
    generateBentoWithLayout(bentoLayoutIdx);
}

function generateBentoWithLayout(idx) {
    bentoLayoutIdx = idx;
    bentoLayout = BENTO_LAYOUTS[idx];
    _fillBento();
}

function generateBento() {
    bentoLayoutIdx = Math.floor(Math.random() * BENTO_LAYOUTS.length);
    bentoLayout = BENTO_LAYOUTS[bentoLayoutIdx];
    _fillBento();
}

function _fillBento() {
    const n = bentoLayout.count;

    const photos = APP.data.photos.filter(p => p.thumb && p.display && p.aesthetic);
    const sorted = [...photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    const pool = sorted.slice(0, 300);

    /* Pick n images with chromatic harmony */
    const seed = randomFrom(pool);
    const selected = [seed];
    const remaining = pool.filter(p => p.id !== seed.id);

    for (let i = 1; i < n && remaining.length > 0; i++) {
        let bestIdx = 0;
        let bestScore = -1;

        for (let j = 0; j < Math.min(remaining.length, 80); j++) {
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
    renderBentoGrid(bentoLayout, selected);
}

function matchPhotosToLayout(cells, photos) {
    const portraits = [];
    const landscapes = [];

    for (const p of photos) {
        const isPortrait = p.orientation === 'portrait' || p.style === 'portrait';
        if (isPortrait) portraits.push(p);
        else landscapes.push(p);
    }

    shuffleArray(portraits);
    shuffleArray(landscapes);

    const matched = [];

    for (const cell of cells) {
        let photo;
        if (cell.pref === 'portrait' && portraits.length > 0) {
            photo = portraits.shift();
        } else if (cell.pref === 'landscape' && landscapes.length > 0) {
            photo = landscapes.shift();
        } else {
            photo = (landscapes.length > 0 ? landscapes : portraits).shift();
        }
        matched.push(photo || null);
    }

    return matched;
}

function renderBentoGrid(layout, photos) {
    const container = document.getElementById('view-bento');
    container.innerHTML = '';

    const matched = matchPhotosToLayout(layout.cells, photos);

    const wrap = document.createElement('div');
    wrap.className = 'bento-wrap';

    /* Touch/swipe support for mobile */
    let touchStartX = 0, touchStartY = 0;
    wrap.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY; }, {passive: true});
    wrap.addEventListener('touchend', e => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
            if (dx > 0) bentoCycle(-1);
            else bentoCycle(1);
        }
    }, {passive: true});

    const grid = document.createElement('div');
    grid.className = 'bento-grid';
    grid.id = 'bento-grid';
    grid.style.setProperty('--bento-cols', layout.cols);
    grid.style.setProperty('--bento-rows', layout.rows);
    grid.style.aspectRatio = layout.cols / layout.rows;

    for (let i = 0; i < matched.length; i++) {
        const cell = layout.cells[i];
        const photo = matched[i];
        if (!photo) continue;

        const tile = document.createElement('div');
        tile.className = 'bento-tile';
        tile.dataset.id = photo.id;
        tile.style.gridRow = cell.r + ' / ' + (cell.r + cell.rs);
        tile.style.gridColumn = cell.c + ' / ' + (cell.c + cell.cs);

        const img = document.createElement('img');
        loadProgressive(img, photo, 'display');
        img.alt = '';
        tile.appendChild(img);

        tile.addEventListener('click', () => openLightbox(photo));
        grid.appendChild(tile);
    }

    wrap.appendChild(grid);

    /* Navigation arrows */
    const prevBtn = document.createElement('button');
    prevBtn.className = 'bento-nav bento-nav-prev';
    prevBtn.innerHTML = '&#8249;';
    prevBtn.addEventListener('click', () => bentoCycle(-1));
    wrap.appendChild(prevBtn);

    const nextBtn = document.createElement('button');
    nextBtn.className = 'bento-nav bento-nav-next';
    nextBtn.innerHTML = '&#8250;';
    nextBtn.addEventListener('click', () => bentoCycle(1));
    wrap.appendChild(nextBtn);

    /* Regen button */
    const btn = document.createElement('button');
    btn.className = 'bento-regen';
    btn.textContent = '\uD83C\uDFB2';
    btn.addEventListener('click', generateBento);
    wrap.appendChild(btn);

    container.appendChild(wrap);
}

function crossfadeOneTile() {
    if (APP.currentView !== 'bento') return;

    const tiles = document.querySelectorAll('.bento-tile');
    if (tiles.length === 0) return;

    const tileIdx = Math.floor(Math.random() * tiles.length);
    const tile = tiles[tileIdx];
    const oldId = tile.dataset.id;

    const currentIds = new Set(bentoPhotos.map(p => p.id));
    const pool = APP.data.photos.filter(p => p.thumb && p.display && p.aesthetic && !currentIds.has(p.id));
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
