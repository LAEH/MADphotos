/* drift.js — Drift: Visual similarity explorer.
   Navigate through 9,011 images by visual similarity. Click any neighbor
   to drift to it — each hop reveals new connections. The center image
   is surrounded by its 8 nearest neighbors (by DINOv2+CLIP vectors).
   A breadcrumb trail tracks your journey through the collection. */

let driftData = null;
let driftHistory = [];
let driftCurrentId = null;

const DRIFT_NEIGHBORS = 8;

async function initDrift() {
    const container = document.getElementById('view-drift');
    container.innerHTML = '<div class="loading">Loading similarity map\u2026</div>';

    driftHistory = [];
    driftCurrentId = null;

    /* Load precomputed neighbors */
    driftData = await loadDriftNeighbors();

    if (!driftData || Object.keys(driftData).length === 0) {
        container.innerHTML = '<div class="loading">No similarity data available</div>';
        return;
    }

    /* Start with a random high-aesthetic photo */
    const all = APP.data.photos.filter(p => p.display && driftData[p.id]);
    const top = [...all].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    const pool = top.slice(0, 200);
    const start = pool[Math.floor(Math.random() * pool.length)];

    container.innerHTML = '';
    renderDriftShell(container);
    navigateDrift(start.id);
}

function renderDriftShell(container) {
    const shell = document.createElement('div');
    shell.className = 'drift-shell';
    shell.id = 'drift-shell';

    /* Center — the hero image */
    const center = document.createElement('div');
    center.className = 'drift-center-wrap';
    center.id = 'drift-center';
    shell.appendChild(center);

    /* Neighbors ring */
    const ring = document.createElement('div');
    ring.className = 'drift-ring';
    ring.id = 'drift-ring';
    shell.appendChild(ring);

    /* Breadcrumb trail */
    const trail = document.createElement('div');
    trail.className = 'drift-trail';
    trail.id = 'drift-trail';
    shell.appendChild(trail);

    /* Random button */
    const random = document.createElement('button');
    random.className = 'drift-random';
    random.textContent = '\uD83C\uDFB2';
    random.title = 'Random starting point';
    random.addEventListener('click', () => {
        const all = APP.data.photos.filter(p => p.display && driftData[p.id]);
        const pick = all[Math.floor(Math.random() * all.length)];
        driftHistory = [];
        navigateDrift(pick.id);
    });
    shell.appendChild(random);

    /* Similarity score label */
    const label = document.createElement('div');
    label.className = 'drift-score-label';
    label.id = 'drift-score-label';
    shell.appendChild(label);

    /* Keyboard */
    document.removeEventListener('keydown', driftKeyHandler);
    document.addEventListener('keydown', driftKeyHandler);

    container.appendChild(shell);
}

function driftKeyHandler(e) {
    if (APP.currentView !== 'drift') return;
    if (e.key === 'Backspace' || e.key === 'Escape') {
        e.preventDefault();
        driftBack();
    }
    if (e.key >= '1' && e.key <= '8') {
        e.preventDefault();
        const ring = document.getElementById('drift-ring');
        if (!ring) return;
        const cards = ring.querySelectorAll('.drift-card');
        const idx = parseInt(e.key) - 1;
        if (idx < cards.length) cards[idx].click();
    }
}

function navigateDrift(photoId) {
    if (driftCurrentId && driftCurrentId !== photoId) {
        driftHistory.push(driftCurrentId);
        if (driftHistory.length > 30) driftHistory.shift();
    }
    driftCurrentId = photoId;

    const photo = APP.photoMap[photoId];
    if (!photo) return;

    const neighbors = (driftData[photoId] || []).slice(0, DRIFT_NEIGHBORS);

    renderDriftCenter(photo);
    renderDriftNeighbors(neighbors);
    renderDriftTrail();
    updateDriftLabel(photo);
}

function renderDriftCenter(photo) {
    const center = document.getElementById('drift-center');
    if (!center) return;

    /* Crossfade: create new img on top, remove old after transition */
    const existing = center.querySelector('.drift-hero');
    const img = document.createElement('img');
    img.className = 'drift-hero drift-hero-entering';
    img.alt = photo.caption || '';
    loadProgressive(img, photo, 'display');

    img.addEventListener('click', () => openLightbox(photo, [photo]));

    center.appendChild(img);

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            img.classList.remove('drift-hero-entering');
            if (existing) {
                existing.classList.add('drift-hero-exiting');
                setTimeout(() => existing.remove(), 500);
            }
        });
    });
}

function renderDriftNeighbors(neighbors) {
    const ring = document.getElementById('drift-ring');
    if (!ring) return;

    /* Fade out old cards */
    const oldCards = ring.querySelectorAll('.drift-card');
    oldCards.forEach(c => {
        c.classList.add('drift-card-exit');
        setTimeout(() => c.remove(), 300);
    });

    /* Create new cards with stagger */
    neighbors.forEach((n, i) => {
        const photo = APP.photoMap[n.id];
        if (!photo) return;

        const card = document.createElement('div');
        card.className = 'drift-card';
        card.style.setProperty('--drift-delay', (i * 60) + 'ms');

        const img = document.createElement('img');
        img.alt = '';
        loadProgressive(img, photo, 'thumb');
        card.appendChild(img);

        /* Score badge */
        const score = document.createElement('span');
        score.className = 'drift-card-score';
        score.textContent = (n.score * 100).toFixed(0) + '%';
        card.appendChild(score);

        card.addEventListener('click', () => navigateDrift(n.id));

        ring.appendChild(card);
    });
}

function renderDriftTrail() {
    const trail = document.getElementById('drift-trail');
    if (!trail) return;
    trail.innerHTML = '';

    const visible = driftHistory.slice(-12);
    for (const id of visible) {
        const photo = APP.photoMap[id];
        if (!photo) continue;

        const dot = document.createElement('div');
        dot.className = 'drift-trail-dot';

        const img = document.createElement('img');
        img.alt = '';
        loadProgressive(img, photo, 'thumb');
        dot.appendChild(img);

        dot.addEventListener('click', () => {
            /* Navigate back to this point, trim history */
            const idx = driftHistory.indexOf(id);
            if (idx >= 0) driftHistory = driftHistory.slice(0, idx);
            driftCurrentId = null;
            navigateDrift(id);
        });

        trail.appendChild(dot);
    }

    /* Current indicator */
    if (driftCurrentId) {
        const cur = document.createElement('div');
        cur.className = 'drift-trail-dot drift-trail-current';
        const curPhoto = APP.photoMap[driftCurrentId];
        if (curPhoto) {
            const img = document.createElement('img');
            img.alt = '';
            loadProgressive(img, curPhoto, 'thumb');
            cur.appendChild(img);
        }
        trail.appendChild(cur);
    }
}

function updateDriftLabel(photo) {
    const el = document.getElementById('drift-score-label');
    if (!el) return;

    const parts = [];
    if (photo.scene) parts.push(photo.scene);
    if (photo.vibes && photo.vibes[0]) parts.push(photo.vibes[0]);
    if (photo.camera) parts.push(photo.camera);

    el.textContent = parts.join(' \u00B7 ');
    el.classList.remove('flash');
    void el.offsetWidth;
    el.classList.add('flash');
}

function driftBack() {
    if (driftHistory.length === 0) return;
    const prev = driftHistory.pop();
    driftCurrentId = null;
    navigateDrift(prev);
    /* Remove the duplicate we just re-pushed */
    if (driftHistory.length > 0 && driftHistory[driftHistory.length - 1] === prev) {
        driftHistory.pop();
    }
}
