/* square.js — Square: Scrabble-board tile grid of square-cropped images.
   Category filtering via emoji pills, shake/shuffle, score badges. */

let squareTileCount = 25;
let squarePool = [];
let squareVisible = [];
let squareCategoryIdx = 0;

const SQUARE_CATEGORIES = [
    { emoji: '\u2B50', label: 'Best',     pool: p => (p.aesthetic || 0) >= 7 },
    { emoji: '\uD83C\uDF39', label: 'Rouge',    pool: p => hueRange(p, 355, 25) },
    { emoji: '\uD83C\uDF40', label: 'Vert',     pool: p => hueRange(p, 80, 165) },
    { emoji: '\uD83E\uDD8B', label: 'Bleu',     pool: p => hueRange(p, 195, 260) },
    { emoji: '\u26AB', label: 'Mono',     pool: p => p.mono },
    { emoji: '\uD83D\uDE0C', label: 'Serein',   pool: p => vibeHas(p, 'serene', 'calm', 'peaceful', 'tranquil') },
    { emoji: '\uD83D\uDD25', label: 'Intense',  pool: p => vibeHas(p, 'dramatic', 'intense', 'powerful', 'bold') },
    { emoji: '\uD83C\uDF05', label: 'Dor\u00E9',      pool: p => p.time === 'golden hour' },
    { emoji: '\uD83D\uDC31', label: 'Animaux',  pool: p => objHas(p, 'cat', 'dog', 'bird', 'horse') },
    { emoji: '\uD83C\uDF3F', label: 'Nature',   pool: p => vibeHas(p, 'natural', 'organic') || objHas(p, 'potted plant', 'tree', 'flower') },
    { emoji: '\uD83C\uDFD9\uFE0F', label: 'Urbain',  pool: p => p.setting === 'urban' || p.environment === 'urban' },
    { emoji: '\uD83C\uDF19', label: 'Nuit',     pool: p => p.time === 'night' },
];

function initSquare() {
    const container = document.getElementById('view-square');
    container.innerHTML = '';

    /* Compute tile count by viewport */
    const w = window.innerWidth;
    if (w <= 480) squareTileCount = 9;
    else if (w <= 768) squareTileCount = 16;
    else squareTileCount = 25;

    renderSquareShell(container);
    selectSquareCategory(0);
}

function renderSquareShell(container) {
    const wrap = document.createElement('div');
    wrap.className = 'square-wrap';

    /* Score display */
    const scoreEl = document.createElement('div');
    scoreEl.className = 'square-score';
    scoreEl.id = 'square-score';
    scoreEl.textContent = '0';
    wrap.appendChild(scoreEl);

    /* Board */
    const cols = Math.round(Math.sqrt(squareTileCount));
    const board = document.createElement('div');
    board.className = 'square-board';
    board.id = 'square-board';
    board.style.setProperty('--sq-cols', cols);
    wrap.appendChild(board);

    /* Shake button */
    const shakeBtn = document.createElement('button');
    shakeBtn.className = 'square-shake';
    shakeBtn.textContent = '\uD83C\uDFB2';
    shakeBtn.title = 'Shuffle';
    shakeBtn.addEventListener('click', shakeSquare);
    wrap.appendChild(shakeBtn);

    /* Category rack */
    const rack = document.createElement('div');
    rack.className = 'square-rack';
    rack.id = 'square-rack';

    for (let i = 0; i < SQUARE_CATEGORIES.length; i++) {
        const cat = SQUARE_CATEGORIES[i];
        const pill = document.createElement('button');
        pill.className = 'square-pill';
        pill.dataset.idx = i;
        pill.textContent = cat.emoji + ' ' + cat.label;
        pill.addEventListener('click', () => selectSquareCategory(i));
        rack.appendChild(pill);
    }

    wrap.appendChild(rack);
    container.appendChild(wrap);

    /* Keyboard handler */
    document.removeEventListener('keydown', squareKeyHandler);
    document.addEventListener('keydown', squareKeyHandler);
}

function squareKeyHandler(e) {
    if (APP.currentView !== 'square') return;
    if (e.code === 'Space' || e.key === 'Enter') {
        e.preventDefault();
        shakeSquare();
    } else if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        selectSquareCategory((squareCategoryIdx + 1) % SQUARE_CATEGORIES.length);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        selectSquareCategory((squareCategoryIdx - 1 + SQUARE_CATEGORIES.length) % SQUARE_CATEGORIES.length);
    }
}

function selectSquareCategory(idx) {
    squareCategoryIdx = idx;

    document.querySelectorAll('.square-pill').forEach(pill => {
        pill.classList.toggle('active', parseInt(pill.dataset.idx) === idx);
    });

    const cat = SQUARE_CATEGORIES[idx];
    squarePool = APP.data.photos.filter(p => p.thumb && cat.pool(p));

    populateBoard();
}

function populateBoard() {
    const board = document.getElementById('square-board');
    if (!board) return;
    board.innerHTML = '';

    const shuffled = shuffleArray([...squarePool]);
    const tiles = shuffled.slice(0, squareTileCount);
    squareVisible = tiles;

    const cols = Math.round(Math.sqrt(squareTileCount));
    const center = Math.floor(squareTileCount / 2);
    const corners = [0, cols - 1, squareTileCount - cols, squareTileCount - 1];

    let totalScore = 0;

    for (let i = 0; i < tiles.length; i++) {
        const photo = tiles[i];
        const tile = document.createElement('div');
        tile.className = 'square-tile';
        const isPremium = corners.includes(i) || i === center;
        if (isPremium) tile.classList.add('square-tile-premium');

        /* Stagger animation delay */
        tile.style.setProperty('--sq-delay', (i * 40) + 'ms');

        const img = document.createElement('img');
        loadProgressive(img, photo, 'thumb');
        img.alt = '';
        tile.appendChild(img);

        /* Score badge */
        const score = Math.round((photo.aesthetic || 5) * 10);
        totalScore += score;
        const badge = document.createElement('span');
        badge.className = 'square-badge';
        badge.textContent = score;
        tile.appendChild(badge);

        /* Click to lightbox */
        tile.addEventListener('click', () => openLightbox(photo, squareVisible));

        board.appendChild(tile);
    }

    /* Update score display */
    const scoreEl = document.getElementById('square-score');
    if (scoreEl) scoreEl.textContent = totalScore;

    /* Trigger assembly animation */
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            board.classList.add('assembled');
        });
    });
}

function shakeSquare() {
    const board = document.getElementById('square-board');
    if (!board) return;

    board.classList.add('shaking');

    /* Set random shake offsets per tile */
    board.querySelectorAll('.square-tile').forEach(tile => {
        tile.style.setProperty('--shake-x', (Math.random() - 0.5) * 12 + 'px');
        tile.style.setProperty('--shake-y', (Math.random() - 0.5) * 12 + 'px');
        tile.style.setProperty('--shake-r', (Math.random() - 0.5) * 8 + 'deg');
    });

    setTimeout(() => {
        board.classList.remove('shaking');
        board.classList.remove('assembled');
        populateBoard();
    }, 500);
}
