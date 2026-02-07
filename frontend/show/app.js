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
    { id: 'grille',      name: 'Sort',            init: 'initGrille' },
    { id: 'bento',       name: 'Le Bento',        init: 'initBento' },
    { id: 'similarity',  name: 'La Similarit\u00e9', init: 'initSimilarity' },
    { id: 'couleurs',    name: 'Les Couleurs',    init: 'initCouleurs' },
    { id: 'game',        name: 'Le Jeu',          init: 'initGame' },
    { id: 'domino',      name: 'Le Domino',       init: 'initDomino' },
    { id: 'stream',      name: 'Le Flot',         init: 'initStream' },
    { id: 'faces',       name: 'Les Visages',     init: 'initFaces' },
    { id: 'compass',     name: 'La Boussole',     init: 'initCompass' },
    { id: 'nyu',         name: 'NYU',             init: 'initNyu' },
    { id: 'confetti',    name: 'Les Confettis',   init: 'initConfetti' },
];

/* ===== Device Detection & Gating ===== */
function isMobile() {
    return window.matchMedia('(max-width: 768px)').matches;
}

function updateDeviceGating() {
    const mobile = isMobile();
    document.querySelectorAll('.exp-card[data-device]').forEach(card => {
        const device = card.dataset.device;
        const disabled = (mobile && device === 'desktop') || (!mobile && device === 'mobile');
        card.classList.toggle('exp-card-disabled', disabled);
        if (disabled) {
            card.dataset.disabledMsg = mobile ? 'Desktop only' : 'Mobile only';
        } else {
            card.dataset.disabledMsg = '';
        }
    });
}

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
            if (card.classList.contains('exp-card-disabled')) return;
            const view = card.dataset.view;
            if (view) switchView(view);
        });
    });

    window.addEventListener('hashchange', () => {
        const hash = location.hash.slice(1);
        if (hash && hash !== APP.currentView) {
            const validViews = EXPERIENCES.map(e => e.id);
            if (validViews.includes(hash)) {
                const card = document.querySelector(`.exp-card[data-view="${hash}"]`);
                if (card && card.classList.contains('exp-card-disabled')) {
                    switchView('launcher');
                    return;
                }
                switchView(hash);
            }
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

    /* Progressive load: use shared loadProgressive for consistent fade-in */
    loadProgressive(img, photo, 'display');
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

/* ===== Image Reveal Helper ===== */
/**
 * Swap an img from .img-loading (opacity:0) to .img-loaded (opacity:1
 * with transition). After the opacity transition ends, remove the
 * .img-loaded class so the element's natural CSS transitions (e.g.
 * transform on hover) are no longer overridden.
 *
 * This is the single codepath for "make this image visible with a fade."
 */
function revealImg(img) {
    img.classList.remove('img-loading');
    img.classList.add('img-loaded');

    /* Clean up .img-loaded after fade completes so it doesn't
       permanently override other transition properties on this element. */
    function onEnd(e) {
        if (e.propertyName === 'opacity') {
            img.removeEventListener('transitionend', onEnd);
            img.classList.remove('img-loaded');
            /* opacity:1 is now the default (no class needed) */
        }
    }
    img.addEventListener('transitionend', onEnd);

    /* Safety: if transition doesn't fire (reduced-motion, not in DOM,
       or duration rounds to 0), clean up after a generous timeout. */
    setTimeout(() => {
        img.classList.remove('img-loaded');
        img.classList.remove('img-loading');
    }, 600);
}

/* ===== Progressive Image Loading ===== */
/**
 * Load an image progressively: start invisible, preload the target tier
 * off-screen, then set src and fade in once fully decoded.
 *
 * Compositing note: only opacity is transitioned (compositor-only).
 * The .img-loading class starts at opacity:0; .img-loaded transitions
 * to opacity:1 via CSS. No layout or paint properties are animated.
 */
function loadProgressive(img, photo, targetTier) {
    const target = photo[targetTier] || photo.thumb;
    if (!target) return;

    /* Start invisible — will fade in once target is fully decoded */
    img.classList.add('img-loading');
    img.classList.remove('img-loaded');

    const preload = new Image();
    preload.decoding = 'async';
    preload.onload = () => {
        img.src = target;
        /* Use decode() where available so the frame that adds .img-loaded
           is guaranteed to have the pixels ready — no flash of blank. */
        if (typeof img.decode === 'function') {
            img.decode().then(() => {
                revealImg(img);
            }).catch(() => {
                /* decode() can reject if img is detached from DOM */
                revealImg(img);
            });
        } else {
            revealImg(img);
        }
    };
    preload.onerror = () => {
        /* Fallback: if target fails, try showing micro at least */
        if (photo.micro && target !== photo.micro) {
            img.src = photo.micro;
        }
        revealImg(img);
    };
    preload.src = target;
}

/* ===== Lazy Loading with IntersectionObserver ===== */
/**
 * Create an img element that starts invisible and defers loading
 * until it enters the viewport (via lazyObserver). Once the target
 * tier is fully decoded, the image fades in via .img-loaded.
 *
 * Container must set explicit width/height or aspect-ratio to
 * prevent CLS — the img itself is opacity:0 until loaded.
 */
function createLazyImg(photo, targetTier) {
    const img = document.createElement('img');
    img.alt = photo.alt || photo.caption || '';
    img.decoding = 'async';
    img.dataset.src = photo[targetTier] || photo.thumb;
    img.dataset.id = photo.id;

    /* Start invisible — no src set yet, nothing to paint */
    img.classList.add('img-loading');

    return img;
}

const lazyObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
        if (entry.isIntersecting) {
            const img = entry.target;
            const src = img.dataset.src;
            lazyObserver.unobserve(img);

            if (!src) return;

            const preload = new Image();
            preload.decoding = 'async';
            preload.onload = () => {
                img.src = src;
                img.removeAttribute('data-src');
                if (typeof img.decode === 'function') {
                    img.decode().then(() => {
                        revealImg(img);
                    }).catch(() => {
                        revealImg(img);
                    });
                } else {
                    revealImg(img);
                }
            };
            preload.onerror = () => {
                /* Show whatever we have — don't leave invisible */
                revealImg(img);
            };
            preload.src = src;
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
    updateDeviceGating();
    window.addEventListener('resize', debounce(updateDeviceGating, 250));

    const hash = location.hash.slice(1);
    const validViews = EXPERIENCES.map(e => e.id);
    if (hash && validViews.includes(hash)) {
        switchView(hash);
    }
}

document.addEventListener('DOMContentLoaded', init);
