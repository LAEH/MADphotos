/* confetti.js — Les Confettis: Themed sets with diversity-sampled mosaics.
   Vertical emoji nav on left, mosaic center, click to reshuffle.
   Viewport-fixed layout. No page scroll. */

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

    /* Object sets — COCO detection labels */
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
function hexToHue(hex) {
    if (!hex || hex.length < 7) return -1;
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const d = max - min;
    if (d < 0.08) return -1; /* achromatic */
    const l = (max + min) / 2;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (s < 0.12) return -1; /* too desaturated */
    let h;
    if (max === r) h = ((g - b) / d + 6) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    return h * 60;
}

function hueRange(photo, lo, hi) {
    if (!photo.palette || !photo.palette[0]) return false;
    const h = hexToHue(photo.palette[0]);
    if (h < 0) return false;
    if (lo <= hi) return h >= lo && h <= hi;
    return h >= lo || h <= hi; /* wraps around 360 */
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

/* ===== Diversity sampling — avoid similar images ===== */
function diverseSample(pool, count) {
    if (pool.length <= count) return shuffleArray([...pool]);

    /* Sort by aesthetic, take generous candidate pool */
    const sorted = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    const candidates = sorted.slice(0, Math.min(pool.length, count * 5));
    const neighbors = APP.driftNeighbors || {};

    /* Pre-build neighbor ID sets for O(1) lookup */
    const neighborIds = {};
    for (const c of candidates) {
        const nList = neighbors[c.id];
        if (nList) {
            neighborIds[c.id] = new Set(nList.map(n => n.uuid || n.id || n));
        } else {
            neighborIds[c.id] = new Set();
        }
    }

    /* Track selected features for diversity scoring */
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

    /* Seed with highest aesthetic */
    addToSelected(candidates[0]);

    while (selected.length < count) {
        let bestIdx = -1;
        let bestScore = -Infinity;

        for (let i = 0; i < candidates.length; i++) {
            const c = candidates[i];
            if (selIds.has(c.id)) continue;

            let score = 0;

            /* Neighbor penalty: how many selected photos are visual neighbors? */
            const cNeighbors = neighborIds[c.id];
            let neighborOverlap = 0;
            if (cNeighbors && cNeighbors.size > 0) {
                for (const s of selected) {
                    if (cNeighbors.has(s.id)) neighborOverlap++;
                    /* Check reverse too */
                    if (neighborIds[s.id] && neighborIds[s.id].has(c.id)) neighborOverlap++;
                }
            }
            score -= neighborOverlap * 50;

            /* Scene diversity: penalize repeated scenes */
            const cScene = c.scene || '';
            score -= (selScenes[cScene] || 0) * 8;

            /* Vibe diversity */
            if (c.vibes) {
                let vibeOverlap = 0;
                for (const v of c.vibes) vibeOverlap += (selVibes[v] || 0);
                score -= vibeOverlap * 3;
            }

            /* Palette hue diversity: reward unique hues */
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

            /* Aesthetic bonus (small, as tiebreaker) */
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

    /* Load neighbor data for diversity, then build */
    loadDriftNeighbors().then(() => {
        confettiSets = buildConfettiSets();
        renderConfettiShell(container);
        /* Auto-select first set */
        if (confettiSets.length > 0) selectConfettiSet(0);
    });
}

function buildConfettiSets() {
    const pool = APP.data.photos.filter(p => p.thumb);
    const sets = [];

    for (const def of CONFETTI_DEFS) {
        const matches = pool.filter(def.pool);
        if (matches.length < CONFETTI_MIN) continue;

        /* Pick perfect-square target */
        const n = matches.length >= 80 ? 64
                : matches.length >= 55 ? 49
                : matches.length >= 40 ? 36 : 25;

        const selected = diverseSample(matches, n);

        sets.push({
            emoji: def.emoji,
            label: def.label,
            photos: selected,
        });

        if (sets.length >= 14) break;
    }

    return sets;
}

/* ===== Shell — vertical nav + viewport ===== */
function renderConfettiShell(container) {
    container.innerHTML = '';

    const shell = document.createElement('div');
    shell.className = 'confetti-shell';

    /* Vertical nav */
    const nav = document.createElement('nav');
    nav.className = 'confetti-nav';
    nav.id = 'confetti-nav';

    for (let i = 0; i < confettiSets.length; i++) {
        const set = confettiSets[i];
        const btn = document.createElement('button');
        btn.className = 'confetti-nav-btn';
        btn.dataset.idx = i;
        btn.textContent = set.emoji;
        btn.title = set.label;
        btn.addEventListener('click', () => selectConfettiSet(i));
        nav.appendChild(btn);
    }

    shell.appendChild(nav);

    /* Viewport */
    const vp = document.createElement('div');
    vp.className = 'confetti-viewport';
    vp.id = 'confetti-viewport';
    shell.appendChild(vp);

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
        reshuffleConfetti();
    }
}

/* ===== Select a set ===== */
function selectConfettiSet(idx) {
    if (confettiAnimating || idx === confettiActiveIdx) return;
    confettiAnimating = true;
    confettiActiveIdx = idx;

    /* Update nav */
    document.querySelectorAll('.confetti-nav-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.idx) === idx);
    });

    const vp = document.getElementById('confetti-viewport');
    if (!vp) { confettiAnimating = false; return; }

    const existing = document.getElementById('confetti-mosaic');

    if (existing) {
        /* Scatter out current, then build new */
        existing.classList.remove('assembled');
        existing.classList.add('scattering');
        setTimeout(() => assembleSet(vp, confettiSets[idx]), 450);
    } else {
        assembleSet(vp, confettiSets[idx]);
    }
}

function assembleSet(vp, set) {
    vp.innerHTML = '';

    const mosaic = buildConfettiMosaic(set.photos);
    vp.appendChild(mosaic);

    /* Label */
    const label = document.createElement('div');
    label.className = 'confetti-label';
    label.textContent = set.label;
    vp.appendChild(label);

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            mosaic.classList.add('assembled');
            confettiAnimating = false;
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

        const img = document.createElement('img');
        loadProgressive(img, photo, 'thumb');
        img.alt = '';
        cell.appendChild(img);

        const col = i % cols;
        const row = Math.floor(i / cols);
        const dist = Math.sqrt((col - cx) ** 2 + (row - cy) ** 2);

        /* Scatter: random ring */
        const angle = Math.random() * Math.PI * 2;
        const scatter = 300 + Math.random() * 500;
        cell.style.setProperty('--sx', (Math.cos(angle) * scatter).toFixed(0) + 'px');
        cell.style.setProperty('--sy', (Math.sin(angle) * scatter).toFixed(0) + 'px');
        cell.style.setProperty('--sr', ((Math.random() - 0.5) * 540).toFixed(0) + 'deg');

        /* Assembly: center first */
        const delay = (dist / maxDist) * 700 + Math.random() * 150;
        cell.style.setProperty('--d', delay.toFixed(0) + 'ms');

        /* Scatter-out: fast random burst */
        cell.style.setProperty('--d-out', (Math.random() * 250).toFixed(0) + 'ms');

        mosaic.appendChild(cell);
    }

    mosaic.addEventListener('click', reshuffleConfetti);
    return mosaic;
}

/* ===== Reshuffle — scatter, rebuild, reassemble ===== */
function reshuffleConfetti() {
    if (confettiAnimating || confettiActiveIdx < 0) return;
    confettiAnimating = true;

    const mosaic = document.getElementById('confetti-mosaic');
    if (!mosaic) { confettiAnimating = false; return; }

    mosaic.classList.remove('assembled');
    mosaic.classList.add('scattering');

    setTimeout(() => {
        const vp = document.getElementById('confetti-viewport');
        if (!vp) { confettiAnimating = false; return; }
        assembleSet(vp, confettiSets[confettiActiveIdx]);
    }, 500);
}
