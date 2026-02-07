/* domino.js — Le Domino: Connected image exploration.
   Center image with 4 dimmed connected images along different dimensions.
   Labels on edges show the shared trait. Click a connected image to chain. */

const DOMINO_DIMS = [
    { key: 'vibes',   label: 'Vibe',    extract: p => p.vibes || [] },
    { key: 'scene',   label: 'Scene',   extract: p => p.scene ? [p.scene] : [] },
    { key: 'time',    label: 'Time',    extract: p => p.time ? [p.time] : [] },
    { key: 'setting', label: 'Setting', extract: p => p.setting ? [p.setting] : [] },
    { key: 'grading', label: 'Look',    extract: p => p.grading ? [p.grading] : [] },
    { key: 'objects', label: 'Object',  extract: p => (p.objects || []).slice(0, 5) },
];

let dominoCurrentId = null;

function initDomino() {
    const container = document.getElementById('view-domino');
    container.innerHTML = '';

    const pool = APP.data.photos.filter(p => p.thumb);
    if (pool.length === 0) {
        container.innerHTML = '<div class="loading">No photos available.</div>';
        return;
    }

    /* Start from a random high-aesthetic photo */
    const sorted = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    const seed = sorted[Math.floor(Math.random() * Math.min(sorted.length, 100))];
    dominoCurrentId = null;
    navigateDomino(seed.id);
}

function findConnected(center, dim, excludeIds) {
    const centerLabels = new Set(dim.extract(center));
    if (centerLabels.size === 0) return null;

    const candidates = [];
    for (const p of APP.data.photos) {
        if (p.id === center.id || excludeIds.has(p.id) || !p.thumb) continue;
        const pLabels = dim.extract(p);
        const shared = pLabels.find(l => centerLabels.has(l));
        if (shared) {
            candidates.push({ photo: p, shared });
        }
    }

    if (candidates.length === 0) return null;

    /* Pick from top aesthetic candidates with some randomness */
    candidates.sort((a, b) => (b.photo.aesthetic || 0) - (a.photo.aesthetic || 0));
    const pick = candidates[Math.floor(Math.random() * Math.min(candidates.length, 15))];
    return { photo: pick.photo, dimLabel: dim.label, sharedLabel: pick.shared };
}

function navigateDomino(id) {
    const photo = APP.photoMap[id];
    if (!photo) return;
    dominoCurrentId = id;
    renderDominoBento(photo);
}

function renderDominoBento(center) {
    const container = document.getElementById('view-domino');
    container.innerHTML = '';

    /* Find 4 connected images along different dimensions */
    const connected = [];
    const usedIds = new Set([center.id]);
    const shuffledDims = shuffleArray([...DOMINO_DIMS]);

    for (const dim of shuffledDims) {
        if (connected.length >= 4) break;
        const result = findConnected(center, dim, usedIds);
        if (result) {
            connected.push(result);
            usedIds.add(result.photo.id);
        }
    }

    /* Second pass if we couldn't fill 4 */
    if (connected.length < 4) {
        for (const dim of DOMINO_DIMS) {
            if (connected.length >= 4) break;
            const result = findConnected(center, dim, usedIds);
            if (result) {
                connected.push(result);
                usedIds.add(result.photo.id);
            }
        }
    }

    /* Build bento grid */
    const grid = document.createElement('div');
    grid.className = 'domino-bento';

    const positions = ['top-left', 'top-right', 'bot-left', 'bot-right'];

    /* Top row: 2 connected images */
    for (let i = 0; i < 2; i++) {
        grid.appendChild(makeDominoConn(connected[i], positions[i]));
    }

    /* Center image — prominent */
    const main = document.createElement('div');
    main.className = 'domino-main';
    const mainImg = document.createElement('img');
    loadProgressive(mainImg, center, 'display');
    mainImg.alt = center.alt || center.caption || '';
    main.appendChild(mainImg);
    main.addEventListener('click', () => openLightbox(center));
    grid.appendChild(main);

    /* Bottom row: 2 connected images */
    for (let i = 2; i < 4; i++) {
        grid.appendChild(makeDominoConn(connected[i], positions[i]));
    }

    container.appendChild(grid);

    /* Random button */
    const rndBtn = document.createElement('button');
    rndBtn.className = 'domino-random';
    rndBtn.textContent = '\uD83C\uDFB2';
    rndBtn.addEventListener('click', () => {
        const pool = APP.data.photos.filter(p => p.thumb);
        const sorted = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
        const pick = sorted[Math.floor(Math.random() * Math.min(sorted.length, 100))];
        navigateDomino(pick.id);
    });
    container.appendChild(rndBtn);
}

function makeDominoConn(conn, pos) {
    const slot = document.createElement('div');
    slot.className = 'domino-conn';
    slot.dataset.pos = pos;

    if (conn) {
        const img = document.createElement('img');
        loadProgressive(img, conn.photo, 'display');
        img.alt = '';
        slot.appendChild(img);

        /* Label overlay showing the shared dimension */
        const label = document.createElement('div');
        label.className = 'domino-conn-label';

        const dimSpan = document.createElement('span');
        dimSpan.className = 'domino-conn-dim';
        dimSpan.textContent = conn.dimLabel;
        label.appendChild(dimSpan);

        const valSpan = document.createElement('span');
        valSpan.className = 'domino-conn-value';
        valSpan.textContent = titleCase(conn.sharedLabel);
        label.appendChild(valSpan);

        slot.appendChild(label);
        slot.addEventListener('click', () => navigateDomino(conn.photo.id));
    } else {
        slot.style.background = 'var(--bg-elevated)';
    }

    return slot;
}
