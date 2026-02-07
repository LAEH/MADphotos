/* app.js — Core data loading, router, shared utilities */

/* ===== Constants ===== */
const HEADER_HEIGHT = 52; /* px — sticky header */
const LAZY_MARGIN = '300px'; /* IntersectionObserver preload distance */

const APP = {
    data: null,
    photoMap: {},
    currentView: null,
    faces: null,
    gameRounds: null,
    streamSequence: null,
    driftNeighbors: null,
    _activeTimers: [], /* track intervals for cleanup */
    lightboxPhotos: [],
    lightboxIndex: -1,
};

/* Experience registry */
const EXPERIENCES = [
    { id: 'grille',      name: 'Sort By',         init: 'initGrille' },
    { id: 'couleurs',    name: 'Colors',           init: 'initCouleurs' },
    { id: 'faces',       name: 'Faces',            init: 'initFaces' },
    { id: 'compass',     name: 'Relations',        init: 'initCompass' },
    { id: 'bento',       name: 'Bento',            init: 'initBento' },
    { id: 'nyu',         name: 'NYU',              init: 'initNyu' },
    { id: 'game',        name: 'Couple',            init: 'initGame' },
    { id: 'confetti',    name: 'Boom',             init: 'initConfetti' },
];

/* ===== Device Detection & Gating ===== */
function isMobile() {
    return window.matchMedia('(max-width: 768px)').matches;
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
        /* photo count removed — header shows experiment name instead */
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
/* ===== Side Menu ===== */
function buildSideMenu() {
    const list = document.getElementById('side-menu-list');
    if (!list) return;
    list.innerHTML = '';

    /* About link — opens State dashboard in new tab */
    const aboutLi = document.createElement('li');
    aboutLi.className = 'side-menu-item side-menu-about';
    aboutLi.textContent = 'About';
    aboutLi.addEventListener('click', () => {
        window.open('https://laeh.github.io/MADphotos/state.html', '_blank');
        closeSideMenu();
    });
    list.appendChild(aboutLi);

    for (const exp of EXPERIENCES) {
        const li = document.createElement('li');
        li.className = 'side-menu-item';
        li.dataset.view = exp.id;
        li.textContent = exp.name;
        li.addEventListener('click', () => {
            switchView(exp.id);
            closeSideMenu();
        });
        list.appendChild(li);
    }
}

function toggleSideMenu() {
    const menu = document.getElementById('side-menu');
    const backdrop = document.getElementById('side-menu-backdrop');
    const open = menu.classList.toggle('open');
    backdrop.classList.toggle('open', open);
}

function closeSideMenu() {
    document.getElementById('side-menu').classList.remove('open');
    document.getElementById('side-menu-backdrop').classList.remove('open');
}

function updateSideMenuActive(viewId) {
    document.querySelectorAll('.side-menu-item').forEach(item => {
        item.classList.toggle('active', item.dataset.view === viewId);
    });
}

function initRouter() {
    buildSideMenu();

    document.getElementById('logo-home').addEventListener('click', (e) => {
        e.preventDefault();
        toggleSideMenu();
    });

    document.getElementById('menu-btn').addEventListener('click', () => {
        toggleSideMenu();
    });

    document.getElementById('side-menu-backdrop').addEventListener('click', closeSideMenu);

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeSideMenu();
    });

    window.addEventListener('hashchange', () => {
        const hash = location.hash.slice(1);
        if (hash && hash !== APP.currentView) {
            const validViews = EXPERIENCES.map(e => e.id);
            if (validViews.includes(hash)) {
                switchView(hash);
            }
        }
    });
}

function switchView(name) {
    /* Clean up previous view's timers and queues */
    clearAllTimers();
    if (typeof _faceBatchQueue !== 'undefined') {
        _faceBatchQueue.length = 0;
        _faceBatchRunning = false;
    }

    APP.currentView = name;
    location.hash = name;

    /* Update header — show experiment name */
    const expNameEl = document.getElementById('header-exp-name');
    const exp = EXPERIENCES.find(e => e.id === name);
    if (expNameEl) {
        expNameEl.textContent = exp ? '\u201C' + exp.name + '\u201D' : '';
    }

    /* Update side menu active state */
    updateSideMenuActive(name);

    /* Toggle views */
    document.querySelectorAll('.view').forEach(v => {
        v.classList.toggle('active', v.id === 'view-' + name);
    });

    /* Trigger experience init */
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
    const prevBtn = lb.querySelector('.lightbox-prev');
    const nextBtn = lb.querySelector('.lightbox-next');

    function close() {
        lb.classList.add('hidden');
        APP.lightboxPhotos = [];
        APP.lightboxIndex = -1;
    }

    backdrop.addEventListener('click', close);
    closeBtn.addEventListener('click', close);
    prevBtn.addEventListener('click', (e) => { e.stopPropagation(); navigateLightbox(-1); });
    nextBtn.addEventListener('click', (e) => { e.stopPropagation(); navigateLightbox(1); });

    /* Capture phase so lightbox keys take priority over experience handlers */
    document.addEventListener('keydown', (e) => {
        if (lb.classList.contains('hidden')) return;
        if (e.key === 'Escape') { close(); e.stopPropagation(); e.preventDefault(); }
        else if (e.key === 'ArrowRight') { navigateLightbox(1); e.stopPropagation(); e.preventDefault(); }
        else if (e.key === 'ArrowLeft') { navigateLightbox(-1); e.stopPropagation(); e.preventDefault(); }
    }, true);

    /* Touch swipe on lightbox content for mobile navigation */
    let lbTouchX = 0;
    const content = lb.querySelector('.lightbox-content');
    content.addEventListener('touchstart', (e) => { lbTouchX = e.touches[0].clientX; }, { passive: true });
    content.addEventListener('touchend', (e) => {
        const dx = e.changedTouches[0].clientX - lbTouchX;
        if (Math.abs(dx) > 50) navigateLightbox(dx > 0 ? -1 : 1);
    }, { passive: true });
}

function navigateLightbox(dir) {
    if (APP.lightboxPhotos.length === 0 || APP.lightboxIndex < 0) return;
    const newIdx = APP.lightboxIndex + dir;
    if (newIdx < 0 || newIdx >= APP.lightboxPhotos.length) return;
    APP.lightboxIndex = newIdx;
    showLightboxPhoto(APP.lightboxPhotos[newIdx]);
}

function showLightboxPhoto(photo) {
    const lb = document.getElementById('lightbox');
    const img = lb.querySelector('.lightbox-img');
    const alt = lb.querySelector('.lightbox-alt');
    const tags = lb.querySelector('.lightbox-tags');
    const palette = lb.querySelector('.lightbox-palette');
    const prevBtn = lb.querySelector('.lightbox-prev');
    const nextBtn = lb.querySelector('.lightbox-next');

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

    /* Show/hide nav based on list context */
    const hasList = APP.lightboxPhotos.length > 1;
    prevBtn.hidden = !hasList || APP.lightboxIndex <= 0;
    nextBtn.hidden = !hasList || APP.lightboxIndex >= APP.lightboxPhotos.length - 1;
}

function openLightbox(photo, photoList) {
    if (photoList && photoList.length > 0) {
        APP.lightboxPhotos = photoList;
        APP.lightboxIndex = photoList.findIndex(p => p.id === photo.id);
        if (APP.lightboxIndex < 0) APP.lightboxIndex = 0;
    } else {
        APP.lightboxPhotos = [];
        APP.lightboxIndex = -1;
    }

    showLightboxPhoto(photo);
    document.getElementById('lightbox').classList.remove('hidden');
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

/* ===== Color Utilities ===== */
function hexToHue(hex) {
    if (!hex || hex.length < 7) return -1;
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    const d = max - min;
    if (d < 0.08) return -1;
    const l = (max + min) / 2;
    const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (s < 0.12) return -1;
    let h;
    if (max === r) h = ((g - b) / d + 6) % 6;
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    return h * 60;
}

function hexToLightness(hex) {
    if (!hex || hex.length < 7) return 50;
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;
    return (Math.max(r, g, b) + Math.min(r, g, b)) / 2 * 100;
}

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

    /* Navigate to hash or default to first experience */
    const hash = location.hash.slice(1);
    const validViews = EXPERIENCES.map(e => e.id);
    if (hash && validViews.includes(hash)) {
        switchView(hash);
    } else {
        switchView('confetti');
    }
}

document.addEventListener('DOMContentLoaded', init);
