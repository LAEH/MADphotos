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
    const pool = sorted.slice(0, 800);

    /* Pick n images with chromatic harmony + vibe/scene diversity */
    const seed = randomFrom(pool);
    const selected = [seed];
    const remaining = pool.filter(p => p.id !== seed.id);
    const usedScenes = new Set(seed.scene ? [seed.scene] : []);
    const usedVibes = new Set(seed.vibes || []);

    for (let i = 1; i < n && remaining.length > 0; i++) {
        let bestIdx = 0;
        let bestScore = -1;
        const useDiversity = i % 2 === 1; /* odd picks: scene/vibe diversity */

        for (let j = 0; j < Math.min(remaining.length, 200); j++) {
            const candidate = remaining[j];
            let score = 0;

            /* Chromatic harmony (always contributes) */
            let colorDist = Math.abs((seed.hue || 0) - (candidate.hue || 0));
            if (colorDist > 180) colorDist = 360 - colorDist;
            const harmonyScore = colorDist < 60 ? 10 : (colorDist > 150 ? 8 : 3);
            score += harmonyScore;

            /* Aesthetic bonus */
            score += (candidate.aesthetic || 5) / 2;

            if (useDiversity) {
                /* Bonus for different scene */
                if (candidate.scene && !usedScenes.has(candidate.scene)) score += 8;
                /* Bonus for different vibes */
                if (candidate.vibes) {
                    let newVibes = 0;
                    for (const v of candidate.vibes) {
                        if (!usedVibes.has(v)) newVibes++;
                    }
                    score += newVibes * 3;
                }
            }

            if (score > bestScore) {
                bestScore = score;
                bestIdx = j;
            }
        }

        const pick = remaining[bestIdx];
        selected.push(pick);
        remaining.splice(bestIdx, 1);
        if (pick.scene) usedScenes.add(pick.scene);
        if (pick.vibes) { for (const v of pick.vibes) usedVibes.add(v); }
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

        /* Dominant color placeholder while image loads */
        const dominant = photo.palette && photo.palette[0];
        if (dominant) tile.style.backgroundColor = dominant + '99';

        const img = document.createElement('img');
        loadProgressive(img, photo, 'display');
        img.alt = '';
        tile.appendChild(img);

        /* Fullscreen icon — visible on hover */
        const fsBtn = document.createElement('button');
        fsBtn.className = 'bento-tile-fs';
        fsBtn.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 3H5a2 2 0 00-2 2v3m18 0V5a2 2 0 00-2-2h-3m0 18h3a2 2 0 002-2v-3M3 16v3a2 2 0 002 2h3"/></svg>';
        fsBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const p = bentoPhotos.find(ph => ph.id === tile.dataset.id);
            if (p) openLightbox(p, bentoPhotos);
        });
        tile.appendChild(fsBtn);

        /* Click tile → swap for new image */
        tile.addEventListener('click', () => swapBentoTile(tile));
        grid.appendChild(tile);
    }

    wrap.appendChild(grid);
    container.appendChild(wrap);

    /* Dice button in nav bar (next to experience label) */
    let diceBtn = document.getElementById('bento-dice-nav');
    if (!diceBtn) {
        diceBtn = document.createElement('button');
        diceBtn.id = 'bento-dice-nav';
        diceBtn.className = 'bento-dice-nav';
        diceBtn.textContent = '\uD83C\uDFB2';
        diceBtn.addEventListener('click', generateBento);
        document.getElementById('floating-nav').appendChild(diceBtn);
    }
    diceBtn.style.display = '';
}

function swapBentoTile(tile) {
    const oldId = tile.dataset.id;
    const currentIds = new Set(bentoPhotos.map(p => p.id));
    const pool = APP.data.photos.filter(p => p.thumb && p.display && p.aesthetic && !currentIds.has(p.id));
    if (pool.length === 0) return;

    const newPhoto = randomFrom(pool);
    tile.style.opacity = '0';

    const finish = () => {
        tile.removeEventListener('transitionend', finish);
        const img = tile.querySelector('img');
        const target = newPhoto.display || newPhoto.thumb;
        const preload = new Image();
        preload.decoding = 'async';
        preload.onload = () => {
            img.src = target;
            img.classList.remove('img-loading', 'img-loaded');
            tile.dataset.id = newPhoto.id;
            const dominant = newPhoto.palette && newPhoto.palette[0];
            if (dominant) tile.style.backgroundColor = dominant + '99';
            const bIdx = bentoPhotos.findIndex(p => p.id === oldId);
            if (bIdx >= 0) bentoPhotos[bIdx] = newPhoto;
            requestAnimationFrame(() => { tile.style.opacity = '1'; });
        };
        preload.onerror = () => { requestAnimationFrame(() => { tile.style.opacity = '1'; }); };
        preload.src = target;
    };

    tile.addEventListener('transitionend', finish);
    setTimeout(() => { if (tile.style.opacity === '0') finish(); }, 1000);
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
            const dominant = newPhoto.palette && newPhoto.palette[0];
            if (dominant) tile.style.backgroundColor = dominant + '99';

            const bIdx = bentoPhotos.findIndex(p => p.id === oldId);
            if (bIdx >= 0) bentoPhotos[bIdx] = newPhoto;

            tile.onclick = () => swapBentoTile(tile);
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
