/* confetti.js — Les Confettis: Themed sets with diversity-sampled mosaics.
   Vertical emoji nav on left, bomb to blow, mosaic center.
   Click image → glass overlay. Viewport-fixed layout. */

let confettiSets = [];
let confettiActiveIdx = -1;
let confettiAnimating = false;

/* ===== Set definitions — emoji + filter + label ===== */
const CONFETTI_DEFS = [
    /* Color sets — dominant palette hue */
    { emoji: '\uD83C\uDF39', label: 'Rouge',     pool: p => hueRange(p, 355, 25) },
    { emoji: '\uD83C\uDF4A', label: 'Ambre',     pool: p => hueRange(p, 20, 40) },
    { emoji: '\uD83C\uDF4B', label: 'Or',        pool: p => hueRange(p, 42, 62) },
    { emoji: '\uD83C\uDF40', label: '\u00C9meraude', pool: p => hueRange(p, 100, 165) },
    { emoji: '\uD83E\uDD8B', label: 'Azur',      pool: p => hueRange(p, 195, 250) },
    { emoji: '\uD83D\uDD2E', label: 'Am\u00E9thyste', pool: p => hueRange(p, 260, 315) },

    /* Time sets */
    { emoji: '\uD83C\uDF05', label: 'Dor\u00E9',       pool: p => p.time === 'golden hour' },
    { emoji: '\uD83C\uDF19', label: 'Nuit',       pool: p => p.time === 'night' },
    { emoji: '\uD83C\uDF0A', label: 'Cr\u00E9puscule',  pool: p => p.time === 'blue hour' },

    /* Object sets */
    { emoji: '\uD83D\uDC31', label: 'Chats',     pool: p => objHas(p, 'cat') },
    { emoji: '\uD83D\uDC15', label: 'Chiens',    pool: p => objHas(p, 'dog') },
    { emoji: '\uD83D\uDE97', label: 'Routes',    pool: p => objHas(p, 'car', 'truck', 'bus', 'motorcycle') },
    { emoji: '\uD83C\uDF3F', label: 'Flore',     pool: p => objHas(p, 'potted plant', 'vase') },
    { emoji: '\uD83C\uDF7D\uFE0F', label: 'Table',    pool: p => objHas(p, 'dining table', 'bowl', 'cup', 'wine glass') },
    { emoji: '\uD83D\uDCDA', label: 'Int\u00E9rieur', pool: p => objHas(p, 'book', 'chair', 'couch', 'bed') },
    { emoji: '\u2602\uFE0F', label: 'Pluie',     pool: p => objHas(p, 'umbrella') },
    { emoji: '\uD83D\uDC64', label: 'Portraits', pool: p => objHas(p, 'person') && (p.style === 'portrait' || p.orientation === 'portrait') },

    /* Vibe sets */
    { emoji: '\uD83D\uDE0C', label: 'Serein',    pool: p => vibeHas(p, 'serene', 'calm', 'peaceful', 'tranquil') },
    { emoji: '\uD83D\uDD25', label: 'Intense',   pool: p => vibeHas(p, 'dramatic', 'intense', 'powerful', 'bold') },
    { emoji: '\u2728',       label: 'Onirique',  pool: p => vibeHas(p, 'ethereal', 'dreamy', 'magical', 'mystical') },
    { emoji: '\uD83D\uDDA4', label: 'Sombre',    pool: p => vibeHas(p, 'dark', 'moody', 'somber', 'melancholic') },
    { emoji: '\uD83C\uDF89', label: 'Vivace',    pool: p => vibeHas(p, 'vibrant', 'lively', 'energetic', 'joyful') },
    { emoji: '\uD83C\uDF3B', label: 'Nostalgique', pool: p => vibeHas(p, 'nostalgic', 'vintage', 'retro', 'timeless') },
];

const CONFETTI_MIN = 25;

/* ===== Filter helpers ===== */
/* hexToHue defined in app.js */

function hueRange(photo, lo, hi) {
    if (!photo.palette || !photo.palette[0]) return false;
    const h = hexToHue(photo.palette[0]);
    if (h < 0) return false;
    if (lo <= hi) return h >= lo && h <= hi;
    return h >= lo || h <= hi;
}

function objHas(photo, ...labels) {
    if (!photo.objects) return false;
    return photo.objects.some(o => {
        const lower = o.toLowerCase();
        return labels.some(l => lower === l || lower.includes(l));
    });
}

function vibeHas(photo, ...vibes) {
    if (!photo.vibes) return false;
    return photo.vibes.some(v => {
        const lower = v.toLowerCase();
        return vibes.some(t => lower.includes(t));
    });
}

/* ===== Diversity sampling ===== */
function diverseSample(pool, count) {
    if (pool.length <= count) return shuffleArray([...pool]);

    const sorted = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    const candidates = sorted.slice(0, Math.min(pool.length, count * 5));
    const neighbors = APP.driftNeighbors || {};

    const neighborIds = {};
    for (const c of candidates) {
        const nList = neighbors[c.id];
        neighborIds[c.id] = nList ? new Set(nList.map(n => n.uuid || n.id || n)) : new Set();
    }

    const selected = [];
    const selIds = new Set();
    const selScenes = {};
    const selVibes = {};
    const selHues = [];

    function addToSelected(photo) {
        selected.push(photo);
        selIds.add(photo.id);
        const sc = photo.scene || '';
        selScenes[sc] = (selScenes[sc] || 0) + 1;
        if (photo.vibes) {
            for (const v of photo.vibes) selVibes[v] = (selVibes[v] || 0) + 1;
        }
        if (photo.palette && photo.palette[0]) {
            const h = hexToHue(photo.palette[0]);
            if (h >= 0) selHues.push(h);
        }
    }

    addToSelected(candidates[0]);

    while (selected.length < count) {
        let bestIdx = -1;
        let bestScore = -Infinity;

        for (let i = 0; i < candidates.length; i++) {
            const c = candidates[i];
            if (selIds.has(c.id)) continue;

            let score = 0;
            const cNeighbors = neighborIds[c.id];
            let neighborOverlap = 0;
            if (cNeighbors && cNeighbors.size > 0) {
                for (const s of selected) {
                    if (cNeighbors.has(s.id)) neighborOverlap++;
                    if (neighborIds[s.id] && neighborIds[s.id].has(c.id)) neighborOverlap++;
                }
            }
            score -= neighborOverlap * 50;

            const cScene = c.scene || '';
            score -= (selScenes[cScene] || 0) * 8;

            if (c.vibes) {
                let vibeOverlap = 0;
                for (const v of c.vibes) vibeOverlap += (selVibes[v] || 0);
                score -= vibeOverlap * 3;
            }

            if (c.palette && c.palette[0]) {
                const h = hexToHue(c.palette[0]);
                if (h >= 0 && selHues.length > 0) {
                    let minDiff = 360;
                    for (const sh of selHues) {
                        const diff = Math.abs(h - sh);
                        minDiff = Math.min(minDiff, diff, 360 - diff);
                    }
                    score += Math.min(minDiff / 10, 5);
                }
            }

            score += (c.aesthetic || 0) * 2;

            if (score > bestScore) {
                bestScore = score;
                bestIdx = i;
            }
        }

        if (bestIdx < 0) break;
        addToSelected(candidates[bestIdx]);
    }

    return selected;
}

/* ===== Init ===== */
function initConfetti() {
    const container = document.getElementById('view-confetti');
    container.innerHTML = '<div class="loading">Building sets\u2026</div>';

    confettiActiveIdx = -1;
    confettiAnimating = false;

    loadDriftNeighbors().then(() => {
        confettiSets = buildConfettiSets();
        renderConfettiShell(container);
        if (confettiSets.length > 0) selectConfettiSet(0);
    });
}

function buildConfettiSets() {
    const pool = APP.data.photos.filter(p => p.thumb);
    const sets = [];

    for (const def of CONFETTI_DEFS) {
        const matches = pool.filter(def.pool);
        if (matches.length < CONFETTI_MIN) continue;

        const n = matches.length >= 80 ? 64
                : matches.length >= 55 ? 49
                : matches.length >= 40 ? 36 : 25;

        sets.push({
            emoji: def.emoji,
            label: def.label,
            photos: diverseSample(matches, n),
        });

        if (sets.length >= 14) break;
    }

    return sets;
}

/* ===== Shell — radial dial + viewport ===== */
function renderConfettiShell(container) {
    container.innerHTML = '';

    const shell = document.createElement('div');
    shell.className = 'confetti-shell';

    /* Viewport */
    const vp = document.createElement('div');
    vp.className = 'confetti-viewport';
    vp.id = 'confetti-viewport';

    /* Touch/swipe support for mobile — swipe to navigate vibes */
    let touchStartX = 0, touchStartY = 0;
    vp.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY; }, {passive: true});
    vp.addEventListener('touchend', e => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
            if (dx > 0) selectConfettiSet((confettiActiveIdx - 1 + confettiSets.length) % confettiSets.length);
            else selectConfettiSet((confettiActiveIdx + 1) % confettiSets.length);
        }
    }, {passive: true});

    shell.appendChild(vp);

    /* Radial dial — bomb center + orbiting emoji buttons */
    const dial = document.createElement('div');
    dial.className = 'confetti-dial';
    dial.id = 'confetti-dial';

    const bomb = document.createElement('button');
    bomb.className = 'confetti-bomb';
    bomb.textContent = '\uD83D\uDCA3';
    bomb.title = 'Blow';
    bomb.addEventListener('click', blowConfetti);
    dial.appendChild(bomb);

    const count = confettiSets.length;
    for (let i = 0; i < count; i++) {
        const set = confettiSets[i];
        const btn = document.createElement('button');
        btn.className = 'confetti-dial-btn';
        btn.dataset.idx = i;
        btn.textContent = set.emoji;
        btn.title = set.label;
        const angle = (i / count) * 360 - 90; /* start from top */
        btn.style.setProperty('--dial-angle', angle + 'deg');
        btn.addEventListener('click', () => selectConfettiSet(i));
        dial.appendChild(btn);
    }

    shell.appendChild(dial);
    container.appendChild(shell);

    document.removeEventListener('keydown', handleConfettiKey);
    document.addEventListener('keydown', handleConfettiKey);
}

function handleConfettiKey(e) {
    if (APP.currentView !== 'confetti') return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
        e.preventDefault();
        selectConfettiSet((confettiActiveIdx + 1) % confettiSets.length);
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
        e.preventDefault();
        selectConfettiSet((confettiActiveIdx - 1 + confettiSets.length) % confettiSets.length);
    } else if (e.key === ' ' || e.key === 'Enter') {
        e.preventDefault();
        blowConfetti();
    }
}

/* ===== Select a set ===== */
function selectConfettiSet(idx) {
    if (confettiAnimating || idx === confettiActiveIdx) return;
    confettiAnimating = true;
    confettiActiveIdx = idx;

    document.querySelectorAll('.confetti-dial-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.idx) === idx);
    });

    const vp = document.getElementById('confetti-viewport');
    if (!vp) { confettiAnimating = false; return; }

    const existing = document.getElementById('confetti-mosaic');

    if (existing) {
        existing.classList.remove('assembled');
        existing.classList.add('scattering');
        setTimeout(() => assembleSet(vp, confettiSets[idx]), 450);
    } else {
        assembleSet(vp, confettiSets[idx]);
    }
}

function assembleSet(vp, set) {
    vp.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'confetti-mosaic-wrap';

    const mosaic = buildConfettiMosaic(set.photos);
    wrap.appendChild(mosaic);

    vp.appendChild(wrap);

    const label = document.createElement('div');
    label.className = 'confetti-label';
    label.textContent = set.label;
    vp.appendChild(label);

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            mosaic.classList.add('assembled');
            confettiAnimating = false;
            /* Free GPU memory after assembly animation completes */
            setTimeout(() => {
                mosaic.querySelectorAll('.confetti-cell').forEach(c => { c.style.willChange = 'auto'; });
            }, 2500);
        });
    });
}

/* ===== Build mosaic grid ===== */
function buildConfettiMosaic(photos) {
    const shuffled = shuffleArray([...photos]);
    const n = shuffled.length;
    const cols = Math.ceil(Math.sqrt(n));
    const rows = Math.ceil(n / cols);

    const mosaic = document.createElement('div');
    mosaic.className = 'confetti-mosaic';
    mosaic.id = 'confetti-mosaic';
    mosaic.style.setProperty('--m-cols', cols);
    mosaic.style.setProperty('--m-rows', rows);

    const cx = (cols - 1) / 2;
    const cy = (rows - 1) / 2;
    const maxDist = Math.sqrt(cx * cx + cy * cy) || 1;

    for (let i = 0; i < n; i++) {
        const photo = shuffled[i];
        const cell = document.createElement('div');
        cell.className = 'confetti-cell';
        if (photo.palette && photo.palette[0]) cell.style.backgroundColor = photo.palette[0] + '80';

        const img = document.createElement('img');
        loadProgressive(img, photo, 'thumb');
        img.alt = '';
        cell.appendChild(img);

        /* Click cell → open glass preview */
        cell.addEventListener('click', (e) => {
            e.stopPropagation();
            openConfettiPreview(photo);
        });

        const col = i % cols;
        const row = Math.floor(i / cols);
        const dist = Math.sqrt((col - cx) ** 2 + (row - cy) ** 2);

        /* Scatter vars */
        const angle = Math.random() * Math.PI * 2;
        const scatter = 300 + Math.random() * 500;
        cell.style.setProperty('--sx', (Math.cos(angle) * scatter).toFixed(0) + 'px');
        cell.style.setProperty('--sy', (Math.sin(angle) * scatter).toFixed(0) + 'px');
        cell.style.setProperty('--sr', ((Math.random() - 0.5) * 540).toFixed(0) + 'deg');

        /* Assembly delay: center first */
        const delay = (dist / maxDist) * 700 + Math.random() * 150;
        cell.style.setProperty('--d', delay.toFixed(0) + 'ms');

        /* Scatter-out delay */
        cell.style.setProperty('--d-out', (Math.random() * 250).toFixed(0) + 'ms');

        mosaic.appendChild(cell);
    }

    return mosaic;
}

/* ===== Blow — magical rearrange in the air ===== */
function blowConfetti() {
    if (confettiAnimating || confettiActiveIdx < 0) return;
    confettiAnimating = true;

    const mosaic = document.getElementById('confetti-mosaic');
    if (!mosaic) { confettiAnimating = false; return; }

    const cells = [...mosaic.querySelectorAll('.confetti-cell')];
    if (cells.length === 0) { confettiAnimating = false; return; }

    const n = cells.length;
    const cols = parseInt(mosaic.style.getPropertyValue('--m-cols'));
    const cx = (cols - 1) / 2;
    const cy = ((Math.ceil(n / cols)) - 1) / 2;
    const maxDist = Math.sqrt(cx * cx + cy * cy) || 1;

    /* Re-promote layers for animation */
    cells.forEach(c => { c.style.willChange = 'transform, opacity'; });

    /* Phase 1: lift — each cell floats to a nearby random spot */
    mosaic.classList.remove('assembled');
    mosaic.classList.add('floating');

    cells.forEach((cell, i) => {
        const angle = Math.random() * Math.PI * 2;
        const dist = 60 + Math.random() * 120;
        const rot = (Math.random() - 0.5) * 40;
        cell.style.setProperty('--fx', (Math.cos(angle) * dist).toFixed(0) + 'px');
        cell.style.setProperty('--fy', (Math.sin(angle) * dist).toFixed(0) + 'px');
        cell.style.setProperty('--fr', rot.toFixed(0) + 'deg');
        cell.style.setProperty('--fd', (i * 8).toFixed(0) + 'ms');
    });

    /* Phase 2: after floating, shuffle images and settle back */
    setTimeout(() => {
        /* Collect current photos from cells */
        const imgs = cells.map(c => c.querySelector('img'));
        const srcs = imgs.map(img => img.src);

        /* Shuffle sources */
        for (let i = srcs.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            [srcs[i], srcs[j]] = [srcs[j], srcs[i]];
        }

        /* Assign shuffled images */
        imgs.forEach((img, i) => {
            img.src = srcs[i];
        });

        /* Phase 3: settle back to grid */
        mosaic.classList.remove('floating');
        mosaic.classList.add('assembled');

        /* Re-set assembly delays from center outward */
        cells.forEach((cell, i) => {
            const col = i % cols;
            const row = Math.floor(i / cols);
            const d = Math.sqrt((col - cx) ** 2 + (row - cy) ** 2);
            const delay = (d / maxDist) * 400 + Math.random() * 100;
            cell.style.setProperty('--d', delay.toFixed(0) + 'ms');
        });

        setTimeout(() => {
            confettiAnimating = false;
            /* Free GPU memory after settle */
            setTimeout(() => {
                cells.forEach(c => { c.style.willChange = 'auto'; });
            }, 2000);
        }, 600);
    }, 600);
}

/* ===== Glass preview overlay ===== */
function openConfettiPreview(photo) {
    /* Remove existing */
    let overlay = document.getElementById('confetti-preview');
    if (overlay) overlay.remove();

    overlay = document.createElement('div');
    overlay.className = 'confetti-preview';
    overlay.id = 'confetti-preview';

    const backdrop = document.createElement('div');
    backdrop.className = 'confetti-preview-backdrop';
    overlay.appendChild(backdrop);

    const img = document.createElement('img');
    img.className = 'confetti-preview-img';
    loadProgressive(img, photo, 'display');
    img.alt = photo.caption || photo.alt || '';
    overlay.appendChild(img);

    /* Click outside image to close */
    backdrop.addEventListener('click', () => closeConfettiPreview());
    document.addEventListener('keydown', confettiPreviewKeyHandler);

    document.body.appendChild(overlay);

    requestAnimationFrame(() => {
        overlay.classList.add('open');
    });
}

function confettiPreviewKeyHandler(e) {
    if (e.key === 'Escape') {
        closeConfettiPreview();
    }
}

function closeConfettiPreview() {
    const overlay = document.getElementById('confetti-preview');
    if (!overlay) return;
    document.removeEventListener('keydown', confettiPreviewKeyHandler);

    overlay.classList.remove('open');
    setTimeout(() => overlay.remove(), 300);
}
