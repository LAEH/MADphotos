/* nyu.js — NYU: 150 curated photographs, 5 ways to experience them.
   Reel · Grid · Deck · Canvas · Overview
   Inspired by art0-nyu. */

let nyuPhotos = [];
let nyuMode = 'reel';
let nyuDeckIdx = 0;
let nyuCanvasIdx = 0;
let nyuCanvasColorIdx = 0;
let nyuAnimating = false;

const NYU_MODES = [
    { id: 'reel',     icon: '\uD83C\uDFDE\uFE0F' },
    { id: 'grid',     icon: '\uD83C\uDF71' },
    { id: 'deck',     icon: '\uD83C\uDCCF' },
    { id: 'canvas',   icon: '\uD83C\uDFA8' },
    { id: 'overview', icon: '\uD83D\uDCA0' },
];

/* ===== Init ===== */
function initNyu() {
    const container = document.getElementById('view-nyu');
    container.innerHTML = '';

    nyuPhotos = selectBestImages(APP.data.photos, 150);
    nyuMode = 'reel';
    nyuDeckIdx = 0;
    nyuCanvasIdx = 0;
    nyuCanvasColorIdx = 0;
    nyuAnimating = false;

    /* Shell */
    const shell = document.createElement('div');
    shell.className = 'nyu-shell';

    const vp = document.createElement('div');
    vp.className = 'nyu-viewport';
    vp.id = 'nyu-viewport';
    shell.appendChild(vp);

    /* Navigation bar */
    const nav = document.createElement('nav');
    nav.className = 'nyu-nav';
    for (const m of NYU_MODES) {
        const btn = document.createElement('button');
        btn.className = 'nyu-nav-btn' + (m.id === nyuMode ? ' active' : '');
        btn.dataset.mode = m.id;
        btn.textContent = m.icon;
        btn.addEventListener('click', () => switchNyuMode(m.id));
        nav.appendChild(btn);
    }
    shell.appendChild(nav);

    container.appendChild(shell);

    document.removeEventListener('keydown', handleNyuKey);
    document.addEventListener('keydown', handleNyuKey);

    renderNyuMode();
}

function selectBestImages(photos, count) {
    const pool = photos.filter(p => p.thumb && p.display);
    const sorted = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    const selected = [];
    const sceneCounts = {};
    const maxPerScene = Math.ceil(count / 8);

    for (const photo of sorted) {
        if (selected.length >= count) break;
        const scene = photo.scene || 'unknown';
        sceneCounts[scene] = (sceneCounts[scene] || 0) + 1;
        if (sceneCounts[scene] <= maxPerScene) {
            selected.push(photo);
        }
    }
    return shuffleArray(selected);
}

function switchNyuMode(mode) {
    nyuMode = mode;
    document.querySelectorAll('.nyu-nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    renderNyuMode();
}

function renderNyuMode() {
    const vp = document.getElementById('nyu-viewport');
    if (!vp) return;
    vp.innerHTML = '';
    vp.className = 'nyu-viewport nyu-vp-' + nyuMode;

    switch (nyuMode) {
        case 'reel':     renderNyuReel(vp); break;
        case 'grid':     renderNyuGrid(vp); break;
        case 'deck':     renderNyuDeckView(vp); break;
        case 'canvas':   renderNyuCanvas(vp); break;
        case 'overview': renderNyuOverview(vp); break;
    }
}

function handleNyuKey(e) {
    if (APP.currentView !== 'nyu') return;

    if (nyuMode === 'reel') {
        if (e.key === 'ArrowRight') { e.preventDefault(); scrollNyuReel(1); }
        else if (e.key === 'ArrowLeft') { e.preventDefault(); scrollNyuReel(-1); }
    } else if (nyuMode === 'deck') {
        if (e.key === 'ArrowRight' || e.key === ' ') { e.preventDefault(); cycleNyuDeck(1); }
        else if (e.key === 'ArrowLeft') { e.preventDefault(); cycleNyuDeck(-1); }
    } else if (nyuMode === 'canvas') {
        if (e.key === 'ArrowRight') { e.preventDefault(); stepNyuCanvas(1); }
        else if (e.key === 'ArrowLeft') { e.preventDefault(); stepNyuCanvas(-1); }
    }
}

/* ===== REEL — Horizontal scroll carousel with nav arrows ===== */
let nyuReelIdx = 0;

function renderNyuReel(vp) {
    nyuReelIdx = 0;
    _reelPositions = null; /* reset position cache */

    const reel = document.createElement('div');
    reel.className = 'nyu-reel';
    reel.id = 'nyu-reel';

    for (const photo of nyuPhotos) {
        const item = document.createElement('div');
        item.className = 'nyu-reel-item';
        if (photo.palette && photo.palette[0]) {
            item.style.background = photo.palette[0] + '15';
        }

        const img = document.createElement('img');
        loadProgressive(img, photo, 'display');
        img.alt = photo.alt || photo.caption || '';
        item.appendChild(img);

        item.addEventListener('click', () => openLightbox(photo, nyuPhotos));
        reel.appendChild(item);
    }

    vp.appendChild(reel);

    /* Nav arrows */
    const prevBtn = document.createElement('button');
    prevBtn.className = 'nyu-reel-nav nyu-reel-prev';
    prevBtn.innerHTML = '&#8249;';
    prevBtn.addEventListener('click', () => scrollNyuReel(-1));
    vp.appendChild(prevBtn);

    const nextBtn = document.createElement('button');
    nextBtn.className = 'nyu-reel-nav nyu-reel-next';
    nextBtn.innerHTML = '&#8250;';
    nextBtn.addEventListener('click', () => scrollNyuReel(1));
    vp.appendChild(nextBtn);

    /* Counter */
    const counter = document.createElement('div');
    counter.className = 'nyu-counter nyu-reel-counter';
    counter.id = 'nyu-reel-counter';
    counter.textContent = '1 / ' + nyuPhotos.length;
    vp.appendChild(counter);

    /* Track scroll position to update counter */
    reel.addEventListener('scrollend', updateReelCounter);
    reel.addEventListener('scroll', debounce(updateReelCounter, 150));
}

function scrollNyuReel(dir) {
    const reel = document.getElementById('nyu-reel');
    if (!reel) return;
    const items = reel.querySelectorAll('.nyu-reel-item');
    nyuReelIdx = Math.max(0, Math.min(nyuReelIdx + dir, items.length - 1));
    items[nyuReelIdx].scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    updateReelCounter();
}

/* Cached item positions — avoids reading 150 offsets on every scroll */
let _reelPositions = null;
function cacheReelPositions() {
    const reel = document.getElementById('nyu-reel');
    if (!reel) return;
    const items = reel.querySelectorAll('.nyu-reel-item');
    _reelPositions = [];
    items.forEach(item => {
        _reelPositions.push(item.offsetLeft + item.offsetWidth / 2);
    });
}

function updateReelCounter() {
    const reel = document.getElementById('nyu-reel');
    const counter = document.getElementById('nyu-reel-counter');
    if (!reel || !counter) return;
    if (!_reelPositions || _reelPositions.length === 0) cacheReelPositions();
    if (!_reelPositions) return;
    const center = reel.scrollLeft + reel.clientWidth / 2;
    let closest = 0, minDist = Infinity;
    for (let i = 0; i < _reelPositions.length; i++) {
        const d = Math.abs(_reelPositions[i] - center);
        if (d < minDist) { minDist = d; closest = i; }
    }
    nyuReelIdx = closest;
    counter.textContent = (closest + 1) + ' / ' + nyuPhotos.length;
}

/* ===== GRID — Masonry rows ===== */
function renderNyuGrid(vp) {
    const grid = document.createElement('div');
    grid.className = 'nyu-grid';

    let i = 0;
    const patterns = ['pair', 'triplet', 'hero', 'pair', 'triplet'];
    let patIdx = 0;

    while (i < nyuPhotos.length) {
        const remaining = nyuPhotos.length - i;
        let count;
        const pattern = patterns[patIdx % patterns.length];
        patIdx++;

        if (pattern === 'hero') count = 1;
        else if (pattern === 'pair') count = 2;
        else count = 3;

        if (remaining < count) count = remaining;

        const row = document.createElement('div');
        row.className = 'nyu-grid-row';
        row.dataset.type = count === 1 ? 'hero' : count === 2 ? 'pair' : 'triplet';

        for (let j = 0; j < count && i < nyuPhotos.length; j++, i++) {
            const photo = nyuPhotos[i];
            const cell = document.createElement('div');
            cell.className = 'nyu-grid-cell';
            if (photo.palette && photo.palette[0]) cell.style.backgroundColor = photo.palette[0] + '33';

            const img = createLazyImg(photo, 'display');
            cell.appendChild(img);
            lazyObserver.observe(img);

            cell.addEventListener('click', () => openLightbox(photo, nyuPhotos));
            row.appendChild(cell);
        }

        grid.appendChild(row);
    }

    vp.appendChild(grid);
}

/* ===== DECK — Stacked cards ===== */
function renderNyuDeckView(vp) {
    const accent = document.createElement('div');
    accent.className = 'nyu-accent';
    accent.id = 'nyu-accent';
    /* Two layers for opacity crossfade (avoids full-viewport background repaint) */
    const layer0 = document.createElement('div');
    layer0.className = 'nyu-accent-layer';
    layer0.id = 'nyu-accent-layer-0';
    const layer1 = document.createElement('div');
    layer1.className = 'nyu-accent-layer';
    layer1.id = 'nyu-accent-layer-1';
    layer1.style.opacity = '0';
    accent.appendChild(layer0);
    accent.appendChild(layer1);
    vp.appendChild(accent);

    const stack = document.createElement('div');
    stack.className = 'nyu-stack';
    stack.id = 'nyu-stack';

    /* Touch/swipe support for mobile — swipe to navigate deck */
    let touchStartX = 0, touchStartY = 0;
    stack.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY; }, {passive: true});
    stack.addEventListener('touchend', e => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
            if (dx > 0) cycleNyuDeck(-1);
            else cycleNyuDeck(1);
        }
    }, {passive: true});

    vp.appendChild(stack);

    const counter = document.createElement('div');
    counter.className = 'nyu-counter';
    counter.id = 'nyu-counter';
    vp.appendChild(counter);

    nyuDeckIdx = 0;
    nyuAnimating = false;
    updateNyuDeckCards();
}

function updateNyuDeckCards() {
    const stack = document.getElementById('nyu-stack');
    const counter = document.getElementById('nyu-counter');
    const accent = document.getElementById('nyu-accent');
    if (!stack) return;

    stack.innerHTML = '';
    const visible = 4;

    for (let i = visible - 1; i >= 0; i--) {
        const idx = (nyuDeckIdx + i) % nyuPhotos.length;
        const photo = nyuPhotos[idx];

        const card = document.createElement('div');
        card.className = 'nyu-card';
        card.style.setProperty('--card-index', i);
        if (photo.palette && photo.palette[0]) card.style.backgroundColor = photo.palette[0] + '33';

        const img = document.createElement('img');
        loadProgressive(img, photo, 'display');
        img.alt = photo.alt || photo.caption || '';
        card.appendChild(img);

        if (i === 0) {
            card.addEventListener('click', () => cycleNyuDeck(1));
        }

        stack.appendChild(card);
    }

    if (counter) counter.textContent = (nyuDeckIdx + 1) + ' / ' + nyuPhotos.length;

    /* Crossfade accent layers (compositor-only opacity, no background repaint) */
    const topPhoto = nyuPhotos[nyuDeckIdx % nyuPhotos.length];
    if (accent) {
        const l0 = document.getElementById('nyu-accent-layer-0');
        const l1 = document.getElementById('nyu-accent-layer-1');
        if (l0 && l1) {
            /* Determine which layer is currently visible */
            const incoming = parseFloat(l0.style.opacity) === 0 ? l0 : l1;
            const outgoing = incoming === l0 ? l1 : l0;
            if (topPhoto.palette && topPhoto.palette[0]) {
                incoming.style.background =
                    `radial-gradient(ellipse at center, ${topPhoto.palette[0]}18 0%, transparent 70%)`;
            } else {
                incoming.style.background = 'none';
            }
            incoming.style.opacity = '1';
            outgoing.style.opacity = '0';
        }
    }
}

function cycleNyuDeck(dir) {
    if (nyuAnimating) return;
    nyuAnimating = true;

    const stack = document.getElementById('nyu-stack');
    if (!stack) { nyuAnimating = false; return; }

    const topCard = stack.lastElementChild;
    if (!topCard) { nyuAnimating = false; return; }

    topCard.classList.add(dir > 0 ? 'nyu-card-exit' : 'nyu-card-exit-left');

    setTimeout(() => {
        nyuDeckIdx = (nyuDeckIdx + dir + nyuPhotos.length) % nyuPhotos.length;
        updateNyuDeckCards();
        nyuAnimating = false;
    }, 350);
}

/* ===== CANVAS — Full-screen image with palette background ===== */
function renderNyuCanvas(vp) {
    nyuCanvasIdx = 0;
    nyuCanvasColorIdx = 0;

    const canvas = document.createElement('div');
    canvas.className = 'nyu-canvas';
    canvas.id = 'nyu-canvas';

    /* Touch/swipe support for mobile — swipe to navigate canvas */
    let canvasTouchStartX = 0, canvasTouchStartY = 0;
    canvas.addEventListener('touchstart', e => { canvasTouchStartX = e.touches[0].clientX; canvasTouchStartY = e.touches[0].clientY; }, {passive: true});
    canvas.addEventListener('touchend', e => {
        const dx = e.changedTouches[0].clientX - canvasTouchStartX;
        const dy = e.changedTouches[0].clientY - canvasTouchStartY;
        if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
            if (dx > 0) stepNyuCanvas(-1);
            else stepNyuCanvas(1);
        }
    }, {passive: true});

    /* Background layers for opacity crossfade (avoids full-viewport repaint) */
    const bg0 = document.createElement('div');
    bg0.className = 'nyu-canvas-bg';
    bg0.id = 'nyu-canvas-bg-0';
    const bg1 = document.createElement('div');
    bg1.className = 'nyu-canvas-bg';
    bg1.id = 'nyu-canvas-bg-1';
    bg1.style.opacity = '0';
    canvas.appendChild(bg0);
    canvas.appendChild(bg1);

    const imgWrap = document.createElement('div');
    imgWrap.className = 'nyu-canvas-img-wrap';
    imgWrap.id = 'nyu-canvas-img-wrap';
    canvas.appendChild(imgWrap);

    const counter = document.createElement('div');
    counter.className = 'nyu-counter nyu-canvas-counter';
    counter.id = 'nyu-canvas-counter';
    canvas.appendChild(counter);

    vp.appendChild(canvas);
    updateNyuCanvas();
}

function stepNyuCanvas(dir) {
    nyuCanvasIdx = (nyuCanvasIdx + dir + nyuPhotos.length) % nyuPhotos.length;
    nyuCanvasColorIdx = 0;
    updateNyuCanvas();
}

function updateNyuCanvas() {
    const canvas = document.getElementById('nyu-canvas');
    const imgWrap = document.getElementById('nyu-canvas-img-wrap');
    const counter = document.getElementById('nyu-canvas-counter');
    if (!canvas || !imgWrap) return;

    const photo = nyuPhotos[nyuCanvasIdx];
    imgWrap.innerHTML = '';

    const img = document.createElement('img');
    img.className = 'nyu-canvas-img';
    loadProgressive(img, photo, 'display');
    img.alt = photo.alt || photo.caption || '';
    imgWrap.appendChild(img);

    /* Crossfade background layers (compositor-only opacity) */
    function setCanvasBg(color) {
        const b0 = document.getElementById('nyu-canvas-bg-0');
        const b1 = document.getElementById('nyu-canvas-bg-1');
        if (!b0 || !b1) return;
        const incoming = parseFloat(b0.style.opacity) === 0 ? b0 : b1;
        const outgoing = incoming === b0 ? b1 : b0;
        incoming.style.background = color;
        incoming.style.opacity = '1';
        outgoing.style.opacity = '0';
    }

    /* Click image to cycle palette colors */
    img.addEventListener('click', (e) => {
        e.stopPropagation();
        if (photo.palette && photo.palette.length > 1) {
            nyuCanvasColorIdx = (nyuCanvasColorIdx + 1) % photo.palette.length;
            setCanvasBg(photo.palette[nyuCanvasColorIdx]);
        }
    });

    /* Set background from palette */
    const bgColor = (photo.palette && photo.palette[nyuCanvasColorIdx])
        ? photo.palette[nyuCanvasColorIdx]
        : 'var(--bg-elevated)';
    setCanvasBg(bgColor);

    if (counter) counter.textContent = (nyuCanvasIdx + 1) + ' / ' + nyuPhotos.length;
}

/* ===== OVERVIEW — Centered square mosaic with assembly animation ===== */
function renderNyuOverview(vp) {
    const n = nyuPhotos.length;
    const cols = Math.ceil(Math.sqrt(n));
    const rows = Math.ceil(n / cols);

    const mosaic = document.createElement('div');
    mosaic.className = 'nyu-mosaic';
    mosaic.style.setProperty('--m-cols', cols);
    mosaic.style.setProperty('--m-rows', rows);

    const cx = (cols - 1) / 2;
    const cy = (rows - 1) / 2;
    const maxDist = Math.sqrt(cx * cx + cy * cy);

    for (let i = 0; i < n; i++) {
        const photo = nyuPhotos[i];
        const cell = document.createElement('div');
        cell.className = 'nyu-mosaic-cell';
        if (photo.palette && photo.palette[0]) cell.style.backgroundColor = photo.palette[0] + '33';

        const img = document.createElement('img');
        loadProgressive(img, photo, 'thumb');
        img.alt = '';
        cell.appendChild(img);

        /* Grid position → radial distance from center */
        const col = i % cols;
        const row = Math.floor(i / cols);
        const dist = Math.sqrt((col - cx) ** 2 + (row - cy) ** 2);

        /* Scatter origin: random point on ring around center */
        const angle = Math.random() * Math.PI * 2;
        const scatter = 200 + Math.random() * 400;
        cell.style.setProperty('--sx', (Math.cos(angle) * scatter).toFixed(0) + 'px');
        cell.style.setProperty('--sy', (Math.sin(angle) * scatter).toFixed(0) + 'px');
        cell.style.setProperty('--sr', ((Math.random() - 0.5) * 360).toFixed(0) + 'deg');

        /* Stagger: center tiles arrive first, edges last */
        const delay = (dist / maxDist) * 600 + Math.random() * 150;
        cell.style.setProperty('--d', delay.toFixed(0) + 'ms');

        cell.addEventListener('click', () => openLightbox(photo, nyuPhotos));
        mosaic.appendChild(cell);
    }

    vp.appendChild(mosaic);

    /* Trigger assembly after paint */
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            mosaic.classList.add('assembled');
            /* Free GPU memory after assembly animation completes */
            setTimeout(() => {
                mosaic.querySelectorAll('.nyu-mosaic-cell').forEach(c => { c.style.willChange = 'auto'; });
            }, 3000);
        });
    });
}
