/* app.js — Core data loading, router, shared utilities */

const APP = {
    data: null,
    photoMap: {},
    currentView: 'launcher',
    faces: null,
    gameRounds: null,
    streamSequence: null,
    driftNeighbors: null,
};

/* Experience registry */
const EXPERIENCES = [
    { id: 'grille',      name: 'La Grille',       init: 'initGrille' },
    { id: 'bento',       name: 'Le Bento',        init: 'initBento' },
    { id: 'similarity',  name: 'La Similarit\u00e9', init: 'initSimilarity' },
    { id: 'derive',      name: 'La D\u00e9rive',  init: 'initDerive' },
    { id: 'couleurs',    name: 'Les Couleurs',    init: 'initCouleurs' },
    { id: 'game',        name: 'Le Jeu',          init: 'initGame' },
    { id: 'darkroom',    name: 'Chambre Noire',   init: 'initDarkroom' },
    { id: 'stream',      name: 'Le Flot',         init: 'initStream' },
    { id: 'faces',       name: 'Les Visages',     init: 'initFaces' },
    { id: 'compass',     name: 'La Boussole',     init: 'initCompass' },
    { id: 'observatory', name: 'L\'Observatoire', init: 'initObservatory' },
    { id: 'map',         name: 'La Carte',        init: 'initMap' },
    { id: 'typewriter',  name: 'Machine \u00c0 \u00c9crire', init: 'initTypewriter' },
    { id: 'pendulum',    name: 'Le Pendule',      init: 'initPendulum' },
];

/* ===== Data Loading ===== */
async function loadData() {
    const resp = await fetch('/data/photos.json');
    APP.data = await resp.json();

    for (const photo of APP.data.photos) {
        APP.photoMap[photo.id] = photo;
    }

    document.getElementById('photo-count').textContent = APP.data.count + ' photos';
    return APP.data;
}

async function loadFaces() {
    if (APP.faces) return APP.faces;
    try {
        const resp = await fetch('/data/faces.json');
        APP.faces = await resp.json();
    } catch (e) {
        APP.faces = {};
    }
    return APP.faces;
}

async function loadGameRounds() {
    if (APP.gameRounds) return APP.gameRounds;
    try {
        const resp = await fetch('/data/game_rounds.json');
        APP.gameRounds = await resp.json();
    } catch (e) {
        APP.gameRounds = [];
    }
    return APP.gameRounds;
}

async function loadStreamSequence() {
    if (APP.streamSequence) return APP.streamSequence;
    try {
        const resp = await fetch('/data/stream_sequence.json');
        APP.streamSequence = await resp.json();
    } catch (e) {
        APP.streamSequence = [];
    }
    return APP.streamSequence;
}

async function loadDriftNeighbors() {
    if (APP.driftNeighbors) return APP.driftNeighbors;
    try {
        const resp = await fetch('/data/drift_neighbors.json');
        APP.driftNeighbors = await resp.json();
    } catch (e) {
        APP.driftNeighbors = {};
    }
    return APP.driftNeighbors;
}

/* ===== Router ===== */
function initRouter() {
    // Logo goes home
    document.getElementById('logo-home').addEventListener('click', (e) => {
        e.preventDefault();
        switchView('launcher');
    });

    // Experience cards on launcher
    document.querySelectorAll('.exp-card').forEach(card => {
        card.addEventListener('click', () => {
            const view = card.dataset.view;
            if (view) switchView(view);
        });
    });

    // Hash routing
    const hash = location.hash.slice(1);
    const validViews = ['launcher', ...EXPERIENCES.map(e => e.id)];
    if (validViews.includes(hash)) {
        switchView(hash);
    }
}

function switchView(name) {
    APP.currentView = name;
    location.hash = name === 'launcher' ? '' : name;

    // Update tabs
    const tabsContainer = document.getElementById('tabs');
    if (name === 'launcher') {
        tabsContainer.innerHTML = '';
    } else {
        // Show a back button + current experience name
        const exp = EXPERIENCES.find(e => e.id === name);
        tabsContainer.innerHTML = '';

        const backBtn = document.createElement('button');
        backBtn.className = 'tab';
        backBtn.textContent = 'All';
        backBtn.addEventListener('click', () => switchView('launcher'));
        tabsContainer.appendChild(backBtn);

        if (exp) {
            const current = document.createElement('button');
            current.className = 'tab active';
            current.textContent = exp.name;
            tabsContainer.appendChild(current);
        }
    }

    // Toggle views
    document.querySelectorAll('.view').forEach(v => {
        v.classList.toggle('active', v.id === 'view-' + name);
    });

    // Trigger init
    const exp = EXPERIENCES.find(e => e.id === name);
    if (exp && typeof window[exp.init] === 'function') {
        window[exp.init]();
    }
}

/* ===== Glass Tag Component ===== */
function createGlassTag(text, opts = {}) {
    const tag = document.createElement('span');
    tag.className = 'glass-tag';
    if (opts.active) tag.classList.add('active');
    if (opts.category) tag.classList.add('tag-' + opts.category);

    if (opts.color) {
        const dot = document.createElement('span');
        dot.className = 'dot';
        dot.style.background = opts.color;
        tag.appendChild(dot);
    }

    // Capitalize first letter of each word
    const displayText = titleCase(text);
    tag.appendChild(document.createTextNode(displayText));

    if (opts.onClick) {
        tag.addEventListener('click', (e) => {
            e.stopPropagation();
            opts.onClick(text, tag);
        });
    }

    return tag;
}

function titleCase(str) {
    if (!str) return '';
    return str.replace(/\b\w/g, c => c.toUpperCase());
}

/* ===== Palette Dots ===== */
function createPaletteDots(palette, size) {
    const frag = document.createDocumentFragment();
    for (const hex of (palette || [])) {
        const dot = document.createElement('span');
        dot.className = 'palette-dot';
        dot.style.background = hex;
        if (size) {
            dot.style.width = size + 'px';
            dot.style.height = size + 'px';
        }
        frag.appendChild(dot);
    }
    return frag;
}

/* ===== Lightbox ===== */
function initLightbox() {
    const lb = document.getElementById('lightbox');
    const backdrop = lb.querySelector('.lightbox-backdrop');
    const closeBtn = lb.querySelector('.lightbox-close');

    function close() {
        lb.classList.add('hidden');
    }

    backdrop.addEventListener('click', close);
    closeBtn.addEventListener('click', close);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close();
    });
}

function openLightbox(photo) {
    const lb = document.getElementById('lightbox');
    const img = lb.querySelector('.lightbox-img');
    const alt = lb.querySelector('.lightbox-alt');
    const tags = lb.querySelector('.lightbox-tags');
    const palette = lb.querySelector('.lightbox-palette');

    img.src = photo.display || photo.mobile || photo.thumb;
    img.alt = photo.alt || photo.caption || '';
    alt.textContent = photo.caption || photo.alt || '';

    tags.innerHTML = '';
    for (const v of (photo.vibes || [])) {
        tags.appendChild(createGlassTag(v, { category: 'vibe' }));
    }
    if (photo.grading) tags.appendChild(createGlassTag(photo.grading, { category: 'grading' }));
    if (photo.time) tags.appendChild(createGlassTag(photo.time, { category: 'time' }));
    if (photo.scene) tags.appendChild(createGlassTag(photo.scene, { category: 'scene' }));
    if (photo.emotion) tags.appendChild(createGlassTag(photo.emotion, { category: 'emotion' }));
    if (photo.camera) tags.appendChild(createGlassTag(photo.camera, { category: 'camera' }));

    palette.innerHTML = '';
    palette.appendChild(createPaletteDots(photo.palette, 20));

    lb.classList.remove('hidden');
}

/* ===== Progressive Image Loading ===== */
function loadProgressive(img, photo, targetTier) {
    if (photo.micro) {
        img.src = photo.micro;
    }
    const target = photo[targetTier] || photo.thumb;
    if (target && target !== photo.micro) {
        const full = new Image();
        full.onload = () => { img.src = target; };
        full.src = target;
    }
}

/* ===== Lazy Loading with IntersectionObserver ===== */
function createLazyImg(photo, targetTier) {
    const img = document.createElement('img');
    img.alt = photo.alt || photo.caption || '';
    img.loading = 'lazy';
    if (photo.micro) {
        img.src = photo.micro;
    }
    img.dataset.src = photo[targetTier] || photo.thumb;
    img.dataset.id = photo.id;
    return img;
}

const lazyObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
        if (entry.isIntersecting) {
            const img = entry.target;
            const src = img.dataset.src;
            if (src && img.src !== src) {
                const full = new Image();
                full.onload = () => { img.src = src; };
                full.src = src;
            }
            lazyObserver.unobserve(img);
        }
    }
}, { rootMargin: '200px' });

/* ===== Utility: Random from Array ===== */
function randomFrom(arr) {
    return arr[Math.floor(Math.random() * arr.length)];
}

function shuffleArray(arr) {
    for (let i = arr.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [arr[i], arr[j]] = [arr[j], arr[i]];
    }
    return arr;
}

/* ===== Init ===== */
async function init() {
    document.getElementById('view-grille').innerHTML = '<div class="loading">Loading photographs</div>';
    await loadData();
    initRouter();
    initLightbox();

    // Start with hash or launcher
    const hash = location.hash.slice(1);
    const validViews = ['launcher', ...EXPERIENCES.map(e => e.id)];
    if (hash && validViews.includes(hash)) {
        switchView(hash);
    }
}

document.addEventListener('DOMContentLoaded', init);
