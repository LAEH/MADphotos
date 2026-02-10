/* picks.js — Curated slideshow of accepted Tinder picks.
   Two-layer crossfade (opacity only — compositor), Ken Burns drift,
   palette background, auto-advance with progress bar.
   Mobile: portrait cover. Desktop: landscape cover / portrait contained. */

const PICKS_ADVANCE_MS = 6000;
const PICKS_PRELOAD_AHEAD = 3;
const PICKS_KB_COUNT = 6;

let picksState = {
    photos: [],
    index: 0,
    activeSlot: 'a',  /* alternate 'a' / 'b' */
    timer: null,
    progressRAF: null,
    progressStart: 0,
    paused: false,
    _keyHandler: null,
    _touchX: 0,
    _inited: false,
};

/* ===== Viewport lock (same pattern as Tinder) ===== */

function picksLockViewport() {
    document.documentElement.style.overflow = 'hidden';
    document.body.style.overflow = 'hidden';
    document.documentElement.style.position = 'fixed';
    document.documentElement.style.inset = '0';
    document.documentElement.style.width = '100%';
}

function picksUnlockViewport() {
    document.documentElement.style.overflow = '';
    document.body.style.overflow = '';
    document.documentElement.style.position = '';
    document.documentElement.style.inset = '';
    document.documentElement.style.width = '';
}

/* ===== Init ===== */

function initPicks() {
    const container = document.getElementById('view-picks');
    if (!container || !APP.data) return;

    picksLockViewport();

    /* If already built, just restart slideshow */
    if (picksState._inited && picksState.photos.length > 0) {
        picksStartAuto();
        return;
    }

    const mobile = isMobile();
    const picksData = APP.picksData || { portrait: [], landscape: [] };

    /* Resolve IDs to photo objects — strict: portrait on mobile, landscape on desktop */
    const orientation = mobile ? 'portrait' : 'landscape';
    const ids = picksData[orientation] || [];

    const photos = [];
    for (const id of ids) {
        const p = APP.photoMap[id];
        if (p) photos.push(p);
    }
    picksState.photos = shuffleArray(photos);
    picksState.index = 0;
    picksState.paused = false;
    picksState._inited = true;

    /* Build DOM */
    container.innerHTML = '';

    if (photos.length === 0) {
        container.innerHTML = '<div class="picks-empty">No picks yet \u2014 vote in Tinder to start curating.</div>';
        return;
    }

    const shell = document.createElement('div');
    shell.className = 'picks-shell';

    /* Background color layers */
    const bgA = document.createElement('div');
    bgA.className = 'picks-bg-layer';
    bgA.id = 'picks-bg-a';
    const bgB = document.createElement('div');
    bgB.className = 'picks-bg-layer';
    bgB.id = 'picks-bg-b';

    /* Image layers */
    const layerA = document.createElement('div');
    layerA.className = 'picks-layer';
    layerA.id = 'picks-layer-a';
    const imgA = document.createElement('img');
    imgA.className = 'picks-img';
    imgA.alt = '';
    layerA.appendChild(imgA);

    const layerB = document.createElement('div');
    layerB.className = 'picks-layer';
    layerB.id = 'picks-layer-b';
    const imgB = document.createElement('img');
    imgB.className = 'picks-img';
    imgB.alt = '';
    layerB.appendChild(imgB);

    /* Progress bar */
    const progress = document.createElement('div');
    progress.className = 'picks-progress';
    const progressFill = document.createElement('div');
    progressFill.className = 'picks-progress-fill';
    progressFill.id = 'picks-progress-fill';
    progress.appendChild(progressFill);

    /* Counter */
    const counter = document.createElement('div');
    counter.className = 'picks-counter';
    counter.id = 'picks-counter';

    shell.appendChild(bgA);
    shell.appendChild(bgB);
    shell.appendChild(layerA);
    shell.appendChild(layerB);
    shell.appendChild(progress);
    shell.appendChild(counter);
    container.appendChild(shell);

    /* Event: swipe (mobile) */
    shell.addEventListener('touchstart', (e) => {
        picksState._touchX = e.touches[0].clientX;
    }, { passive: true });

    shell.addEventListener('touchend', (e) => {
        const dx = e.changedTouches[0].clientX - picksState._touchX;
        if (Math.abs(dx) > 50) {
            picksGo(dx > 0 ? -1 : 1);
        } else {
            /* Tap center → lightbox */
            openLightbox(picksState.photos[picksState.index], picksState.photos);
        }
    }, { passive: true });

    /* Event: click (desktop) — left half = prev, right half / center = next */
    shell.addEventListener('click', (e) => {
        if (e.target.closest('.picks-progress') || e.target.closest('.picks-counter')) return;
        const rect = shell.getBoundingClientRect();
        const x = e.clientX - rect.left;
        if (x < rect.width / 3) {
            picksGo(-1);
        } else {
            picksGo(1);
        }
    });

    /* Event: keyboard */
    if (picksState._keyHandler) {
        document.removeEventListener('keydown', picksState._keyHandler);
    }
    picksState._keyHandler = (e) => {
        if (APP.currentView !== 'picks') return;
        if (!document.getElementById('lightbox').classList.contains('hidden')) return;
        if (e.key === 'ArrowRight') { picksGo(1); e.preventDefault(); }
        else if (e.key === 'ArrowLeft') { picksGo(-1); e.preventDefault(); }
        else if (e.key === ' ') { picksTogglePause(); e.preventDefault(); }
    };
    document.addEventListener('keydown', picksState._keyHandler);

    /* Show first slide */
    picksShowSlide(0, true);
    picksStartAuto();
}

/* ===== Slide Transition ===== */

function picksShowSlide(index, immediate) {
    const photos = picksState.photos;
    if (photos.length === 0) return;

    /* Wrap around */
    if (index < 0) index = photos.length - 1;
    if (index >= photos.length) index = 0;
    picksState.index = index;

    const photo = photos[index];
    const mobile = isMobile();
    const tier = mobile ? 'mobile' : 'display';
    const src = photo[tier] || photo.thumb;

    /* Determine active/inactive slots */
    const slot = picksState.activeSlot;
    const nextSlot = slot === 'a' ? 'b' : 'a';

    const nextLayer = document.getElementById('picks-layer-' + nextSlot);
    const prevLayer = document.getElementById('picks-layer-' + slot);
    const nextBg = document.getElementById('picks-bg-' + nextSlot);
    const prevBg = document.getElementById('picks-bg-' + slot);
    const img = nextLayer.querySelector('.picks-img');

    /* Set image */
    img.src = src;
    img.alt = photo.alt || photo.caption || '';
    if (photo.focus) {
        img.style.objectPosition = photo.focus[0] + '% ' + photo.focus[1] + '%';
    } else {
        img.style.objectPosition = '';
    }

    /* Ken Burns — random class */
    const kbClass = 'kb-' + (Math.floor(Math.random() * PICKS_KB_COUNT) + 1);
    nextLayer.className = 'picks-layer active ' + kbClass;
    if (prevLayer) {
        prevLayer.classList.remove('active');
        /* Remove KB class after transition so animation doesn't replay */
    }

    /* Background palette color */
    const bgColor = (photo.palette && photo.palette[0]) || '#000';
    if (nextBg) nextBg.style.background = bgColor;
    if (nextBg) nextBg.classList.add('active');
    if (prevBg) prevBg.classList.remove('active');

    picksState.activeSlot = nextSlot;

    /* Counter */
    const counter = document.getElementById('picks-counter');
    if (counter) counter.textContent = (index + 1) + ' / ' + photos.length;

    /* Preload ahead */
    for (let i = 1; i <= PICKS_PRELOAD_AHEAD; i++) {
        const ni = (index + i) % photos.length;
        const np = photos[ni];
        const nsrc = np[tier] || np.thumb;
        if (nsrc) {
            const pre = new Image();
            pre.src = nsrc;
        }
    }
}

/* ===== Auto-advance ===== */

function picksStartAuto() {
    picksStopAuto();
    picksState.paused = false;
    picksState.progressStart = performance.now();

    picksState.timer = registerTimer(setInterval(() => {
        if (!picksState.paused) {
            picksGo(1);
        }
    }, PICKS_ADVANCE_MS));

    picksAnimateProgress();
}

function picksStopAuto() {
    if (picksState.timer) {
        clearInterval(picksState.timer);
        picksState.timer = null;
    }
    if (picksState.progressRAF) {
        cancelAnimationFrame(picksState.progressRAF);
        picksState.progressRAF = null;
    }
}

function picksAnimateProgress() {
    const fill = document.getElementById('picks-progress-fill');
    if (!fill) return;

    function tick(now) {
        if (picksState.paused) {
            picksState.progressRAF = requestAnimationFrame(tick);
            return;
        }
        const elapsed = now - picksState.progressStart;
        const pct = Math.min(elapsed / PICKS_ADVANCE_MS, 1);
        fill.style.transform = 'scaleX(' + pct + ')';
        if (pct < 1) {
            picksState.progressRAF = requestAnimationFrame(tick);
        }
    }
    picksState.progressRAF = requestAnimationFrame(tick);
}

/* ===== Navigation ===== */

function picksGo(dir) {
    picksShowSlide(picksState.index + dir);
    /* Reset auto-advance timer */
    picksState.progressStart = performance.now();
    if (picksState.timer) {
        clearInterval(picksState.timer);
        picksState.timer = registerTimer(setInterval(() => {
            if (!picksState.paused) {
                picksGo(1);
            }
        }, PICKS_ADVANCE_MS));
    }
}

function picksTogglePause() {
    picksState.paused = !picksState.paused;
    if (!picksState.paused) {
        /* Reset progress start to now so bar fills from current position */
        picksState.progressStart = performance.now();
    }
}
