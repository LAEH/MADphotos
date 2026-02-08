/* pulse.js — Pulse: A living, breathing mosaic.
   Images ripple with sine waves emanating from the center or cursor.
   Category pills filter by theme. Mouse/touch moves the wave origin.
   Click any image to open lightbox. */

let pulsePhotos = [];
let pulseRunning = false;
let pulseCols = 0;
let pulseRows = 0;
let pulseCells = [];
let pulseOriginX = 0.5;
let pulseOriginY = 0.5;
let pulseActiveCategory = 0;

const PULSE_DESKTOP = 100; /* 10x10 */
const PULSE_TABLET = 64;   /* 8x8 */
const PULSE_PHONE = 36;    /* 6x6 */

/* Categories — reuse filter helpers from confetti.js */
const PULSE_CATEGORIES = [
    { emoji: '\u2B50', label: 'Best',      pool: p => (p.aesthetic || 0) >= 6.5 },
    { emoji: '\uD83C\uDF39', label: 'Rouge',    pool: p => hueRange(p, 355, 25) },
    { emoji: '\uD83C\uDF4A', label: 'Ambre',    pool: p => hueRange(p, 15, 50) },
    { emoji: '\uD83C\uDF40', label: 'Vert',     pool: p => hueRange(p, 80, 170) },
    { emoji: '\uD83E\uDD8B', label: 'Azur',     pool: p => hueRange(p, 190, 255) },
    { emoji: '\uD83D\uDD2E', label: 'Violet',   pool: p => hueRange(p, 260, 320) },
    { emoji: '\uD83C\uDF05', label: 'Dor\u00E9',      pool: p => p.time === 'golden hour' },
    { emoji: '\uD83C\uDF19', label: 'Nuit',     pool: p => p.time === 'night' },
    { emoji: '\uD83D\uDE0C', label: 'Serein',   pool: p => vibeHas(p, 'serene', 'calm', 'peaceful', 'tranquil') },
    { emoji: '\uD83D\uDD25', label: 'Intense',  pool: p => vibeHas(p, 'dramatic', 'intense', 'powerful', 'bold') },
    { emoji: '\uD83D\uDDA4', label: 'Sombre',   pool: p => vibeHas(p, 'dark', 'moody', 'somber', 'melancholic') },
    { emoji: '\uD83C\uDF3B', label: 'Nostalgique', pool: p => vibeHas(p, 'nostalgic', 'vintage', 'retro') },
];

function initPulse() {
    const container = document.getElementById('view-pulse');
    container.innerHTML = '';

    pulseRunning = false;
    pulseCells = [];
    pulseOriginX = 0.5;
    pulseOriginY = 0.5;
    pulseActiveCategory = 0;

    const w = window.innerWidth;
    if (w <= 480)     { pulseCols = 6; }
    else if (w <= 768) { pulseCols = 8; }
    else               { pulseCols = 10; }
    pulseRows = pulseCols; /* square grid */

    renderPulseShell(container);
    selectPulseCategory(0);
}

function renderPulseShell(container) {
    const shell = document.createElement('div');
    shell.className = 'pulse-shell';
    shell.id = 'pulse-shell';

    /* Grid */
    const grid = document.createElement('div');
    grid.className = 'pulse-grid';
    grid.id = 'pulse-grid';
    grid.style.setProperty('--pulse-cols', pulseCols);
    shell.appendChild(grid);

    /* Category pills at bottom */
    const rack = document.createElement('div');
    rack.className = 'pulse-rack';
    rack.id = 'pulse-rack';

    for (let i = 0; i < PULSE_CATEGORIES.length; i++) {
        const cat = PULSE_CATEGORIES[i];
        const pill = document.createElement('button');
        pill.className = 'pulse-pill';
        pill.dataset.idx = i;
        pill.textContent = cat.emoji + ' ' + cat.label;
        pill.addEventListener('click', () => selectPulseCategory(i));
        rack.appendChild(pill);
    }

    shell.appendChild(rack);

    /* Mouse tracking */
    shell.addEventListener('mousemove', e => {
        const grid = document.getElementById('pulse-grid');
        if (!grid) return;
        const rect = grid.getBoundingClientRect();
        pulseOriginX = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
        pulseOriginY = Math.max(0, Math.min(1, (e.clientY - rect.top) / rect.height));
    });
    shell.addEventListener('mouseleave', () => {
        pulseOriginX = 0.5;
        pulseOriginY = 0.5;
    });
    shell.addEventListener('touchmove', e => {
        const grid = document.getElementById('pulse-grid');
        if (!grid) return;
        const rect = grid.getBoundingClientRect();
        pulseOriginX = Math.max(0, Math.min(1, (e.touches[0].clientX - rect.left) / rect.width));
        pulseOriginY = Math.max(0, Math.min(1, (e.touches[0].clientY - rect.top) / rect.height));
    }, { passive: true });

    container.appendChild(shell);
}

function selectPulseCategory(idx) {
    pulseActiveCategory = idx;

    /* Update pill states */
    document.querySelectorAll('.pulse-pill').forEach(pill => {
        pill.classList.toggle('active', parseInt(pill.dataset.idx) === idx);
    });

    /* Stop existing animation */
    pulseRunning = false;

    const cat = PULSE_CATEGORIES[idx];
    const count = pulseCols * pulseRows;

    /* Filter and sample */
    const all = APP.data.photos.filter(p => p.thumb);
    const matches = all.filter(cat.pool);

    /* Smart sampling: sort by aesthetic, take top pool, shuffle */
    const sorted = [...matches].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    const pool = sorted.slice(0, count * 3);
    pulsePhotos = shuffleArray([...pool]).slice(0, count);

    /* Fallback: if not enough, pad with random top aesthetics */
    if (pulsePhotos.length < count) {
        const topAll = [...all].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
        const existing = new Set(pulsePhotos.map(p => p.id));
        for (const p of topAll) {
            if (pulsePhotos.length >= count) break;
            if (!existing.has(p.id)) {
                pulsePhotos.push(p);
                existing.add(p.id);
            }
        }
    }

    populatePulseGrid();
}

function populatePulseGrid() {
    const grid = document.getElementById('pulse-grid');
    if (!grid) return;
    grid.innerHTML = '';
    pulseCells = [];

    const count = pulseCols * pulseRows;
    const maxDist = Math.sqrt((pulseCols / 2) ** 2 + (pulseRows / 2) ** 2);

    for (let i = 0; i < Math.min(pulsePhotos.length, count); i++) {
        const photo = pulsePhotos[i];
        const cell = document.createElement('div');
        cell.className = 'pulse-cell';

        const img = document.createElement('img');
        img.alt = '';
        loadProgressive(img, photo, 'thumb');
        cell.appendChild(img);

        cell.addEventListener('click', () => openLightbox(photo, pulsePhotos));

        /* Stagger reveal delay from center outward */
        const col = i % pulseCols;
        const row = Math.floor(i / pulseCols);
        const dist = Math.sqrt((col - pulseCols / 2) ** 2 + (row - pulseRows / 2) ** 2);
        const delay = (dist / maxDist) * 600 + Math.random() * 150;
        cell.style.setProperty('--pulse-delay', delay.toFixed(0) + 'ms');

        grid.appendChild(cell);
        pulseCells.push(cell);
    }

    /* Trigger reveal */
    requestAnimationFrame(() => {
        grid.classList.remove('revealed');
        void grid.offsetWidth;
        grid.classList.add('revealed');
    });

    /* Start pulse animation after reveal completes */
    setTimeout(() => {
        /* Remove transition so rAF inline styles take over */
        pulseCells.forEach(cell => {
            cell.style.transition = 'none';
        });
        startPulseWave();
    }, 1200);
}

function startPulseWave() {
    pulseRunning = true;

    function animate(now) {
        if (!pulseRunning || APP.currentView !== 'pulse') {
            pulseRunning = false;
            return;
        }

        const cx = pulseOriginX * pulseCols;
        const cy = pulseOriginY * pulseRows;

        for (let i = 0; i < pulseCells.length; i++) {
            const col = i % pulseCols;
            const row = Math.floor(i / pulseCols);
            const dist = Math.sqrt((col - cx) ** 2 + (row - cy) ** 2);

            /* Sine wave: distance creates phase offset, time creates motion */
            const wave = Math.sin(dist * 1.0 - now * 0.0018) * 0.5 + 0.5;
            const scale = 0.84 + wave * 0.16;
            const opacity = 0.4 + wave * 0.6;

            pulseCells[i].style.transform = 'scale(' + scale.toFixed(3) + ')';
            pulseCells[i].style.opacity = opacity.toFixed(2);
        }

        requestAnimationFrame(animate);
    }

    requestAnimationFrame(animate);
}
