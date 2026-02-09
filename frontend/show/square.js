/* square.js — Square: Living contact sheet.
   Dense grid fills viewport. One photo at a time pulses — scales up
   with a glow, caption overlay. Auto-cycles every 2.5s. Click any for lightbox. */

let squarePhotos = [];
let squareActiveIdx = -1;
let squareCycleTimer = null;
let squarePaused = false;
let squareCategoryIdx = 0;

const SQUARE_CYCLE_MS = 2500;

const SQUARE_CATEGORIES = [
    { label: 'All',       pool: () => true },
    { label: 'Best',      pool: p => (p.aesthetic || 0) >= 7 },
    { label: 'Mono',      pool: p => p.mono },
    { label: 'Night',     pool: p => p.time === 'Night' },
    { label: 'Urban',     pool: p => p.setting === 'Urban' || p.environment === 'urban' },
    { label: 'Golden',    pool: p => p.time === 'Golden Hour' },
    { label: 'Serene',    pool: p => vibeHas(p, 'serene', 'calm', 'peaceful', 'tranquil') },
    { label: 'Intense',   pool: p => vibeHas(p, 'dramatic', 'intense', 'powerful', 'bold') },
];

function initSquare() {
    const container = document.getElementById('view-square');
    container.innerHTML = '';

    clearInterval(squareCycleTimer);
    squareCycleTimer = null;
    squarePaused = false;
    squareActiveIdx = -1;

    renderSquareShell(container);
    selectSquareCategory(0);
}

function renderSquareShell(container) {
    const shell = document.createElement('div');
    shell.className = 'sq-shell';

    /* Category tabs along top */
    const tabs = document.createElement('div');
    tabs.className = 'sq-tabs';
    tabs.id = 'sq-tabs';

    for (let i = 0; i < SQUARE_CATEGORIES.length; i++) {
        const cat = SQUARE_CATEGORIES[i];
        const btn = document.createElement('button');
        btn.className = 'sq-tab';
        btn.dataset.idx = i;
        btn.textContent = cat.label;
        btn.addEventListener('click', () => selectSquareCategory(i));
        tabs.appendChild(btn);
    }
    shell.appendChild(tabs);

    /* Grid area */
    const grid = document.createElement('div');
    grid.className = 'sq-grid';
    grid.id = 'sq-grid';
    shell.appendChild(grid);

    /* Info overlay — shows caption of active photo */
    const info = document.createElement('div');
    info.className = 'sq-info';
    info.id = 'sq-info';
    shell.appendChild(info);

    container.appendChild(shell);

    /* Keyboard */
    document.removeEventListener('keydown', squareKeyHandler);
    document.addEventListener('keydown', squareKeyHandler);
}

function squareKeyHandler(e) {
    if (APP.currentView !== 'square') return;
    if (e.code === 'Space') {
        e.preventDefault();
        squarePaused = !squarePaused;
    } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        squarePaused = true;
        spotlightSquare((squareActiveIdx + 1) % squarePhotos.length);
    } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        squarePaused = true;
        spotlightSquare((squareActiveIdx - 1 + squarePhotos.length) % squarePhotos.length);
    }
}

function selectSquareCategory(idx) {
    squareCategoryIdx = idx;

    document.querySelectorAll('.sq-tab').forEach((tab, i) => {
        tab.classList.toggle('active', i === idx);
    });

    const cat = SQUARE_CATEGORIES[idx];
    const pool = APP.data.photos.filter(p => p.thumb && cat.pool(p));

    /* Sort by aesthetic, take top batch */
    pool.sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));

    /* How many tiles fit in viewport? */
    const w = window.innerWidth;
    const cols = w <= 480 ? 4 : w <= 768 ? 6 : w <= 1200 ? 8 : 10;
    const headerH = 52;
    const tabsH = 44;
    const availH = window.innerHeight - headerH - tabsH;
    const tileSize = Math.floor((w - 2) / cols); /* 2px for minimal gap */
    const rows = Math.floor(availH / tileSize);
    const maxTiles = cols * rows;

    squarePhotos = shuffleArray(pool.slice(0, Math.min(pool.length, maxTiles)));
    squareActiveIdx = -1;

    populateSquareGrid(cols);
}

function populateSquareGrid(cols) {
    const grid = document.getElementById('sq-grid');
    if (!grid) return;
    grid.innerHTML = '';
    grid.style.setProperty('--sq-cols', cols);

    clearInterval(squareCycleTimer);

    for (let i = 0; i < squarePhotos.length; i++) {
        const photo = squarePhotos[i];
        const cell = document.createElement('div');
        cell.className = 'sq-cell';
        cell.dataset.idx = i;
        cell.style.setProperty('--sq-delay', (i * 15) + 'ms');

        const img = document.createElement('img');
        loadProgressive(img, photo, 'thumb');
        img.alt = '';
        cell.appendChild(img);

        cell.addEventListener('click', () => {
            if (squareActiveIdx === i) {
                openLightbox(photo, squarePhotos);
            } else {
                squarePaused = true;
                spotlightSquare(i);
            }
        });

        grid.appendChild(cell);
    }

    /* Stagger entrance */
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            grid.classList.add('sq-revealed');

            /* Start auto-cycle after entrance settles */
            setTimeout(() => {
                spotlightSquare(Math.floor(Math.random() * squarePhotos.length));
                squarePaused = false;
                squareCycleTimer = setInterval(() => {
                    if (squarePaused) return;
                    const next = Math.floor(Math.random() * squarePhotos.length);
                    spotlightSquare(next);
                }, SQUARE_CYCLE_MS);
                APP._activeTimers.push(squareCycleTimer);
            }, 600);
        });
    });
}

function spotlightSquare(idx) {
    if (idx < 0 || idx >= squarePhotos.length) return;
    squareActiveIdx = idx;
    const photo = squarePhotos[idx];

    /* Toggle active class */
    document.querySelectorAll('.sq-cell').forEach((cell, i) => {
        cell.classList.toggle('sq-active', i === idx);
    });

    /* Update info overlay */
    const info = document.getElementById('sq-info');
    if (info) {
        const caption = photo.florence || photo.caption || '';
        const camera = photo.camera || '';
        info.classList.remove('sq-info-visible');
        setTimeout(() => {
            info.innerHTML = '';
            if (caption) {
                const capEl = document.createElement('span');
                capEl.className = 'sq-info-caption';
                capEl.textContent = caption.endsWith('.') ? caption.slice(0, -1) : caption;
                info.appendChild(capEl);
            }
            if (camera) {
                const camEl = document.createElement('span');
                camEl.className = 'sq-info-camera';
                camEl.textContent = camera;
                info.appendChild(camEl);
            }
            info.classList.add('sq-info-visible');
        }, 100);
    }

    /* Scroll the active cell into view if needed */
    const activeCell = document.querySelector(`.sq-cell[data-idx="${idx}"]`);
    if (activeCell) {
        const grid = document.getElementById('sq-grid');
        const cellRect = activeCell.getBoundingClientRect();
        const gridRect = grid.getBoundingClientRect();
        if (cellRect.bottom > gridRect.bottom || cellRect.top < gridRect.top) {
            activeCell.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }
}
