/* app.js — Core data loading, router, shared utilities */

/* ===== Performance Tier Detection ===== */
/* Tier A: full fidelity (Safari, high-end Chrome).
   Tier B: no backdrop-filter (Chrome Android, mid-range).
   Tier C: minimal effects (very low-end, ≤2 cores, or save-data). */
(function detectTier() {
    const ua = navigator.userAgent;
    const isWebKit = /AppleWebKit/.test(ua) && !/Chrome/.test(ua); /* Safari */
    const cores = navigator.hardwareConcurrency || 2;
    const dpr = devicePixelRatio || 1;
    const mem = navigator.deviceMemory || 4; /* GB, Chrome-only */
    const saveData = navigator.connection && navigator.connection.saveData;
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let tier;
    if (saveData || cores <= 2 || mem <= 2) {
        tier = 'tier-c';
    } else if (isWebKit || (cores >= 4 && dpr <= 3 && mem >= 4)) {
        tier = 'tier-a';
    } else {
        tier = 'tier-b';
    }

    document.documentElement.classList.add(tier);
})();

/* ===== Constants ===== */
const HEADER_HEIGHT = 0; /* px — no header, floating pill */
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
    { id: 'picks',       route: 'tinder',  name: 'Tinder',           init: 'initPicks' },
    { id: 'couleurs',    route: 'couleurs', name: 'Colors',          init: 'initCouleurs' },

    { id: 'compass',     route: 'compass',  name: 'Relation',        init: 'initCompass' },
    { id: 'bento',       route: 'bento',    name: 'Bento',           init: 'initBento' },
    { id: 'nyu',         route: 'nyu',      name: 'NYU',             init: 'initNyu' },
    { id: 'game',        route: 'game',     name: 'Couple',          init: 'initGame' },
    { id: 'confetti',    route: 'confetti', name: 'Boom',            init: 'initConfetti' },
    { id: 'caption',     route: 'caption',  name: 'Caption',         init: 'initCaption' },
    { id: 'isit',        route: 'isit',     name: 'ISIT',            init: 'initIsit' },
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
        const errEl = document.getElementById('view-grille') || document.getElementById('view-couleurs');
        if (errEl) errEl.innerHTML = '<div class="loading error">Failed to load photos. Check data/photos.json.</div>';
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

async function loadPicks() {
    if (APP.picksData) return APP.picksData;
    try { APP.picksData = await fetchJSON('/data/picks.json'); }
    catch { APP.picksData = { portrait: [], landscape: [] }; }
    return APP.picksData;
}

async function loadVoted() {
    if (APP.votedData) return APP.votedData;
    try { APP.votedData = await fetchJSON('/data/voted.json'); }
    catch { APP.votedData = {}; }
    return APP.votedData;
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

    /* System button — in the footer, above Theme */
    const footer = document.querySelector('.side-menu-footer');
    if (footer) {
        const sysBtn = document.createElement('button');
        sysBtn.className = 'side-menu-action';
        sysBtn.setAttribute('aria-label', 'System');
        sysBtn.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="3"/><path d="M13.4 10a1.2 1.2 0 0 0 .2 1.3l.1.1a1.5 1.5 0 1 1-2.1 2.1l-.1-.1a1.2 1.2 0 0 0-1.3-.2 1.2 1.2 0 0 0-.7 1.1v.2a1.5 1.5 0 0 1-3 0v-.1a1.2 1.2 0 0 0-.8-1.1 1.2 1.2 0 0 0-1.3.2l-.1.1a1.5 1.5 0 1 1-2.1-2.1l.1-.1a1.2 1.2 0 0 0 .2-1.3 1.2 1.2 0 0 0-1.1-.7h-.2a1.5 1.5 0 0 1 0-3h.1a1.2 1.2 0 0 0 1.1-.8 1.2 1.2 0 0 0-.2-1.3l-.1-.1a1.5 1.5 0 1 1 2.1-2.1l.1.1a1.2 1.2 0 0 0 1.3.2h.1a1.2 1.2 0 0 0 .7-1.1v-.2a1.5 1.5 0 0 1 3 0v.1a1.2 1.2 0 0 0 .7 1.1 1.2 1.2 0 0 0 1.3-.2l.1-.1a1.5 1.5 0 1 1 2.1 2.1l-.1.1a1.2 1.2 0 0 0-.2 1.3v.1a1.2 1.2 0 0 0 1.1.7h.2a1.5 1.5 0 0 1 0 3h-.1a1.2 1.2 0 0 0-1.1.7z"/></svg><span>System</span>';
        sysBtn.addEventListener('click', () => {
            window.open('/system/', '_blank');
            closeSideMenu();
        });
        footer.insertBefore(sysBtn, footer.firstChild);
    }
}

function toggleSideMenu() {
    const menu = document.getElementById('side-menu');
    const backdrop = document.getElementById('side-menu-backdrop');
    const menuBtn = document.getElementById('menu-btn');
    const floatingNav = document.getElementById('floating-nav');
    const open = menu.classList.toggle('open');
    backdrop.classList.toggle('open', open);
    menuBtn.classList.toggle('menu-open', open);
    floatingNav.classList.toggle('menu-expanded', open);
    /* Sync menu width to nav width so they visually connect */
    if (open) menu.style.width = floatingNav.offsetWidth + 'px';
    else menu.style.width = '';
}

function closeSideMenu() {
    const menu = document.getElementById('side-menu');
    menu.classList.remove('open');
    menu.style.width = '';
    document.getElementById('side-menu-backdrop').classList.remove('open');
    document.getElementById('menu-btn').classList.remove('menu-open');
    document.getElementById('floating-nav').classList.remove('menu-expanded');
}

function updateSideMenuActive(viewId) {
    document.querySelectorAll('.side-menu-item').forEach(item => {
        item.classList.toggle('active', item.dataset.view === viewId);
    });
}

function initRouter() {
    buildSideMenu();

    document.getElementById('menu-btn').addEventListener('click', (e) => {
        e.preventDefault();
        toggleSideMenu();
    });

    /* Desktop: click to toggle collapse (no hover behavior) */

    document.getElementById('side-menu-backdrop').addEventListener('click', closeSideMenu);

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeSideMenu();
    });

    window.addEventListener('hashchange', () => {
        const hash = location.hash.slice(1);
        const exp = EXPERIENCES.find(e => e.route === hash);
        if (exp && exp.id !== APP.currentView) {
            switchView(exp.id);
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

    /* Release decoded image memory from inactive views */
    document.querySelectorAll('.view:not(.active) img[src]').forEach(img => {
        if (img.closest('#lightbox')) return; /* don't touch lightbox */
        img.removeAttribute('src');
    });

    /* Viewport lock cleanup (ISIT, Tinder & Picks all lock) */
    if (APP.currentView === 'isit' && name !== 'isit') {
        if (typeof isitUnlockViewport === 'function') isitUnlockViewport();
    }
    if (APP.currentView === 'tinder' && name !== 'tinder') {
        if (typeof tinderUnlockViewport === 'function') tinderUnlockViewport();
    }
    if (APP.currentView === 'picks' && name !== 'picks') {
        if (typeof picksUnlockViewport === 'function') picksUnlockViewport();
    }

    APP.currentView = name;
    const expForHash = EXPERIENCES.find(e => e.id === name);
    location.hash = expForHash ? expForHash.route : name;

    /* Hide bento dice when leaving bento */
    const bentoDice = document.getElementById('bento-dice-nav');
    if (bentoDice) bentoDice.style.display = name === 'bento' ? '' : 'none';

    const exp = EXPERIENCES.find(e => e.id === name);

    /* Update side menu active state + mobile button label */
    updateSideMenuActive(name);
    const btnLabel = document.getElementById('menu-btn-label');
    if (btnLabel && exp) btnLabel.textContent = exp.name;
    /* Desktop: show experience name next to logo */
    const navExpLabel = document.getElementById('nav-exp-label');
    if (navExpLabel && exp) navExpLabel.textContent = exp.name;

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

/* ===== Border Crop ===== */
/**
 * Apply border crop to an img element. For object-fit:cover contexts,
 * scaling up hides borders (parent overflow:hidden clips them).
 * For the lightbox (natural size), clip-path trims precisely.
 */
function applyBorderCrop(img, crop) {
    const t = crop.top || 0, r = crop.right || 0;
    const b = crop.bottom || 0, l = crop.left || 0;
    /* Scale factor: enough to push all borders outside the container */
    const scaleX = 100 / (100 - l - r);
    const scaleY = 100 / (100 - t - b);
    const scale = Math.max(scaleX, scaleY);
    img.style.transform = 'scale(' + scale.toFixed(4) + ')';
}

/**
 * Apply clip-path for lightbox (full image, no object-fit:cover).
 */
function applyBorderClip(img, crop) {
    if (!crop) { img.style.clipPath = ''; return; }
    const t = crop.top || 0, r = crop.right || 0;
    const b = crop.bottom || 0, l = crop.left || 0;
    img.style.clipPath = 'inset(' + t + '% ' + r + '% ' + b + '% ' + l + '%)';
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

    /* Reset border scale from card views, use clip-path for lightbox */
    img.style.transform = '';
    loadProgressive(img, photo, 'display');
    applyBorderClip(img, photo.border_crop);
    img.alt = photo.alt || photo.caption || '';
    alt.textContent = photo.best_caption || photo.caption || photo.alt || '';

    tags.innerHTML = '';
    /* Consensus tags first (visually distinct — agreed by 2+ models) */
    const consensusSet = new Set(photo.consensus || []);
    for (const c of (photo.consensus || [])) {
        tags.appendChild(createGlassTag(c, { category: 'consensus' }));
    }
    /* Then vibes (skip any already shown as consensus) */
    for (const v of (photo.vibes || [])) {
        if (!consensusSet.has(v.toLowerCase())) {
            tags.appendChild(createGlassTag(v, { category: 'vibe' }));
        }
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
    }, 800);
}

/* ===== Image Tier Selection ===== */
/**
 * DPR + connection-aware tier selection.
 * role: 'card' (tinder/picks card) or 'full' (bento, game, caption fullscreen).
 */
function optimalTier(role) {
    const w = window.innerWidth;
    const dpr = Math.min(devicePixelRatio || 1, 3);
    const cssW = role === 'card' ? Math.min(w, 600) : w;
    const needed = cssW * dpr;
    const slow = navigator.connection &&
        (navigator.connection.saveData ||
         navigator.connection.effectiveType === '2g' ||
         navigator.connection.effectiveType === 'slow-2g');

    if (slow) return needed <= 600 ? 'thumb' : 'mobile';
    if (needed <= 540)  return 'thumb';   /* 480px tier */
    if (needed <= 1400) return 'mobile';  /* 1280px tier */
    return 'display';                      /* 2048px tier */
}

/* Back-compat alias — callers in other files use this */
function cardImageTier() {
    return optimalTier('card');
}

/* ===== Decode Queue (browser-aware concurrency) ===== */
const DECODE_QUEUE = {
    max: /AppleWebKit.*Mobile/.test(navigator.userAgent) ? 2 :
         /AppleWebKit/.test(navigator.userAgent) ? 3 :
         /Android/.test(navigator.userAgent) ? 3 : 6,
    active: 0,
    pending: [],
    enqueue(img) {
        return new Promise(resolve => {
            this.pending.push({ img, resolve });
            this._drain();
        });
    },
    _drain() {
        while (this.active < this.max && this.pending.length) {
            this.active++;
            const { img, resolve } = this.pending.shift();
            (typeof img.decode === 'function' ? img.decode() : Promise.resolve())
                .then(resolve).catch(resolve)
                .finally(() => { this.active--; this._drain(); });
        }
    }
};

/* ===== Progressive Image Loading ===== */
/**
 * Load an image with blur-up: show micro immediately as blurred placeholder,
 * then crossfade to the target tier once fully decoded.
 * Falls back to invisible→reveal if no micro is available.
 */
function loadProgressive(img, photo, targetTier) {
    const target = photo[targetTier] || photo.thumb;
    if (!target) return;

    /* Dominant color placeholder on parent — fallback only (per-view code
       may already have set a custom color/opacity). */
    if (photo.palette && photo.palette[0] && img.parentElement
        && !img.parentElement.style.backgroundColor) {
        img.parentElement.style.backgroundColor = photo.palette[0] + '55';
    }

    /* Content-aware focal point — prevents cropping faces/animals */
    if (photo.focus) {
        img.style.objectPosition = photo.focus[0] + '% ' + photo.focus[1] + '%';
    }

    /* Border crop — scale up slightly to hide film scan borders */
    if (photo.border_crop) {
        applyBorderCrop(img, photo.border_crop);
    }

    /* Phase 1: Show micro immediately as blurred placeholder */
    if (photo.micro) {
        img.src = photo.micro;
        img.classList.add('img-blur-up');
        img.classList.remove('img-loading', 'img-loaded');
    } else {
        /* No micro — fall back to invisible until target loads */
        img.classList.add('img-loading');
        img.classList.remove('img-loaded', 'img-blur-up');
    }

    /* Phase 2: Preload target, crossfade when ready */
    const pre = new Image();
    pre.decoding = 'async';
    pre.src = target;
    const swap = () => {
        img.src = target;
        img.classList.remove('img-blur-up');
        img.style.filter = '';
        img.style.transform = '';
        /* Re-apply border crop if needed (blur-up used scale(1.05)) */
        if (photo.border_crop) applyBorderCrop(img, photo.border_crop);
        revealImg(img);
    };
    const doLoad = () => {
        DECODE_QUEUE.enqueue(pre).then(swap).catch(swap);
    };
    pre.onload = doLoad;
    pre.onerror = () => {
        /* Fallback: if target fails, at least show micro */
        if (photo.micro && target !== photo.micro) {
            img.src = photo.micro;
        }
        img.classList.remove('img-blur-up');
        revealImg(img);
    };
    /* If already cached, onload may have fired synchronously */
    if (pre.complete && pre.naturalWidth) doLoad();
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

    /* Content-aware focal point — prevents cropping faces/animals */
    if (photo.focus) {
        img.style.objectPosition = photo.focus[0] + '% ' + photo.focus[1] + '%';
    }

    /* Border crop — scale up slightly to hide film scan borders */
    if (photo.border_crop) {
        applyBorderCrop(img, photo.border_crop);
    }

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
                DECODE_QUEUE.enqueue(img).then(() => {
                    revealImg(img);
                });
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

/* ===== Fullscreen Toggle ===== */
function toggleFullscreen() {
    if (!document.fullscreenElement && !document.webkitFullscreenElement) {
        const el = document.documentElement;
        if (el.requestFullscreen) el.requestFullscreen();
        else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
    } else {
        if (document.exitFullscreen) document.exitFullscreen();
        else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
    }
}

function updateFullscreenIcon() {
    const isFs = !!(document.fullscreenElement || document.webkitFullscreenElement);
    document.documentElement.classList.toggle('is-fullscreen', isFs);
}

function initFullscreen() {
    const btn = document.getElementById('fullscreen-toggle');
    if (!btn) return;

    /* Hide on iOS Safari — Fullscreen API not supported */
    const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
    if (isIOS || (!document.documentElement.requestFullscreen && !document.documentElement.webkitRequestFullscreen)) {
        btn.style.display = 'none';
        return;
    }

    btn.addEventListener('click', toggleFullscreen);
    document.addEventListener('fullscreenchange', updateFullscreenIcon);
    document.addEventListener('webkitfullscreenchange', updateFullscreenIcon);
}

/* ===== Init ===== */
async function init() {
    const grille = document.getElementById('view-grille');
    if (grille) grille.innerHTML = '<div class="loading">Curating your photographs</div>';

    try {
        await loadData();
    } catch {
        return; /* loadData already shows error UI */
    }

    /* Load picks data (non-blocking — OK if missing) */
    await loadPicks();

    /* Load server-side vote history for cross-device dedup */
    await loadVoted();

    /* Stash full collection for Tinder (needs all photos for curation) */
    APP.allPhotos = APP.data.photos;
    APP.allPhotoMap = { ...APP.photoMap };

    /* Filter to picks only for all other experiences */
    const picksSet = new Set([
        ...(APP.picksData.portrait || []),
        ...(APP.picksData.landscape || [])
    ]);
    APP.data.photos = APP.allPhotos.filter(p => picksSet.has(p.id));
    APP.photoMap = {};
    for (const photo of APP.data.photos) {
        APP.photoMap[photo.id] = photo;
    }

    /* Precache micro images via service worker */
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
        const micros = APP.data.photos.filter(p => p.micro).map(p => p.micro);
        if (micros.length) {
            navigator.serviceWorker.controller.postMessage({ type: 'precache-micros', urls: micros });
        }
    }

    initRouter();
    initLightbox();
    initFullscreen();

    /* Navigate to hash or default view */
    const hash = location.hash.slice(1);
    const matchedExp = EXPERIENCES.find(e => e.route === hash);
    if (matchedExp) {
        switchView(matchedExp.id);
    } else {
        switchView('picks');
    }
}

document.addEventListener('DOMContentLoaded', init);
