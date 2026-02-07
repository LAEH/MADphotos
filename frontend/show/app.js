/* app.js — Core data loading, router, shared utilities */

/* ===== Constants ===== */
const HEADER_HEIGHT = 52; /* px — sticky header */
const LAZY_MARGIN = '300px'; /* IntersectionObserver preload distance */

const APP = {
    data: null,
    photoMap: {},
    currentView: 'launcher',
    faces: null,
    gameRounds: null,
    streamSequence: null,
    driftNeighbors: null,
    _activeTimers: [], /* track intervals for cleanup */
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

/* ===== Data Loading (with error handling) ===== */
async function fetchJSON(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`${resp.status} ${resp.statusText}: ${url}`);
    return resp.json();
}

async function loadData() {
    try {
        APP.data = await fetchJSON('/data/photos.json');
        for (const photo of APP.data.photos) {
            APP.photoMap[photo.id] = photo;
        }
        document.getElementById('photo-count').textContent = APP.data.count + ' photos';
        return APP.data;
    } catch (err) {
        document.getElementById('view-grille').innerHTML =
            '<div class="loading error">Failed to load photos. Check data/photos.json.</div>';
        console.error('loadData failed:', err);
        throw err;
    }
}

async function loadFaces() {
    if (APP.faces) return APP.faces;
    try { APP.faces = await fetchJSON('/data/faces.json'); }
    catch { APP.faces = {}; }
    return APP.faces;
}

async function loadGameRounds() {
    if (APP.gameRounds) return APP.gameRounds;
    try { APP.gameRounds = await fetchJSON('/data/game_rounds.json'); }
    catch { APP.gameRounds = []; }
    return APP.gameRounds;
}

async function loadStreamSequence() {
    if (APP.streamSequence) return APP.streamSequence;
    try { APP.streamSequence = await fetchJSON('/data/stream_sequence.json'); }
    catch { APP.streamSequence = []; }
    return APP.streamSequence;
}

async function loadDriftNeighbors() {
    if (APP.driftNeighbors) return APP.driftNeighbors;
    try { APP.driftNeighbors = await fetchJSON('/data/drift_neighbors.json'); }
    catch { APP.driftNeighbors = {}; }
    return APP.driftNeighbors;
}

/* ===== Timer Management (prevent leaks) ===== */
function registerTimer(id) {
    APP._activeTimers.push(id);
    return id;
}

function clearAllTimers() {
    for (const id of APP._activeTimers) {
        clearInterval(id);
        cancelAnimationFrame(id);
    }
    APP._activeTimers = [];
}

/* ===== Router ===== */
function initRouter() {
    document.getElementById('logo-home').addEventListener('click', (e) => {
        e.preventDefault();
        switchView('launcher');
    });

    document.querySelectorAll('.exp-card').forEach(card => {
        card.addEventListener('click', () => {
            const view = card.dataset.view;
            if (view) switchView(view);
        });
    });

    window.addEventListener('hashchange', () => {
        const hash = location.hash.slice(1);
        if (hash && hash !== APP.currentView) {
            const validViews = EXPERIENCES.map(e => e.id);
            if (validViews.includes(hash)) switchView(hash);
        }
    });
}

function switchView(name) {
    /* Clean up previous view's timers */
    clearAllTimers();

    APP.currentView = name;
    location.hash = name === 'launcher' ? '' : name;

    /* Update tabs */
    const tabsContainer = document.getElementById('tabs');
    tabsContainer.innerHTML = '';

    if (name !== 'launcher') {
        const exp = EXPERIENCES.find(e => e.id === name);

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

    /* Toggle views */
    document.querySelectorAll('.view').forEach(v => {
        v.classList.toggle('active', v.id === 'view-' + name);
    });

    /* Trigger experience init */
    const exp = EXPERIENCES.find(e => e.id === name);
    if (exp && typeof window[exp.init] === 'function') {
        try {
            window[exp.init]();
        } catch (err) {
            console.error(`Failed to init ${exp.name}:`, err);
            const view = document.getElementById('view-' + name);
            if (view) view.innerHTML = '<div class="loading error">Experience failed to load.</div>';
        }
    }

    /* Scroll to top on view switch */
    window.scrollTo({ top: 0 });
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

    tag.appendChild(document.createTextNode(titleCase(text)));

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
        if (e.key === 'Escape' && !lb.classList.contains('hidden')) close();
    });
}

function openLightbox(photo) {
    const lb = document.getElementById('lightbox');
    const img = lb.querySelector('.lightbox-img');
    const alt = lb.querySelector('.lightbox-alt');
    const tags = lb.querySelector('.lightbox-tags');
    const palette = lb.querySelector('.lightbox-palette');

    /* Progressive load: micro → display */
    if (photo.micro) img.src = photo.micro;
    const targetSrc = photo.display || photo.mobile || photo.thumb;
    if (targetSrc && targetSrc !== photo.micro) {
        const preload = new Image();
        preload.onload = () => { img.src = targetSrc; };
        preload.src = targetSrc;
    }
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
    if (photo.micro) img.src = photo.micro;
    const target = photo[targetTier] || photo.thumb;
    if (target && target !== photo.micro) {
        const preload = new Image();
        preload.onload = () => { img.src = target; };
        preload.src = target;
    }
}

/* ===== Lazy Loading with IntersectionObserver ===== */
function createLazyImg(photo, targetTier) {
    const img = document.createElement('img');
    img.alt = photo.alt || photo.caption || '';
    img.loading = 'lazy';
    if (photo.micro) img.src = photo.micro;
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
                const preload = new Image();
                preload.onload = () => {
                    img.src = src;
                    img.removeAttribute('data-src');
                };
                preload.src = src;
            }
            lazyObserver.unobserve(img);
        }
    }
}, { rootMargin: LAZY_MARGIN });

/* ===== Utilities ===== */
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

/** Debounce: delay fn execution until pause in calls */
function debounce(fn, ms) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}

/* ===== Init ===== */
async function init() {
    document.getElementById('view-grille').innerHTML = '<div class="loading">Curating your photographs</div>';

    try {
        await loadData();
    } catch {
        return; /* loadData already shows error UI */
    }

    initRouter();
    initLightbox();

    const hash = location.hash.slice(1);
    const validViews = EXPERIENCES.map(e => e.id);
    if (hash && validViews.includes(hash)) {
        switchView(hash);
    }
}

document.addEventListener('DOMContentLoaded', init);
