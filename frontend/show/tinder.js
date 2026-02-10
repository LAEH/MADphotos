/* tinder.js — Mobile validation: swipe portrait (mobile) / landscape (desktop)
   Two-card stack: next card always rendered underneath so swipe reveals instantly.
   rAF-throttled touch, compositor-only animations, 10-image preload buffer.
   v2: velocity-aware exit, spring-back, grab micro-interaction, eased overlays. */

const TINDER_PRELOAD_AHEAD = 10;
const TINDER_SWIPE_THRESHOLD = 80;
const TINDER_ROTATION_FACTOR = 0.03;   /* subtler than 0.04 — less mechanical */
const TINDER_GRAB_SCALE = 0.985;       /* micro scale-down on touch */
const TINDER_MIN_EXIT_V = 0.8;         /* px/ms — minimum exit velocity */

let tinderState = {
    photos: [],
    index: 0,
    isMobile: false,
    votes: {},
    animating: false,
    _keyHandler: null,
    _cache: {}
};

/* ===== Viewport lock ===== */

function tinderLockViewport() {
    document.documentElement.style.overflow = 'hidden';
    document.body.style.overflow = 'hidden';
    document.documentElement.style.position = 'fixed';
    document.documentElement.style.inset = '0';
    document.documentElement.style.width = '100%';
}

function tinderUnlockViewport() {
    document.documentElement.style.overflow = '';
    document.body.style.overflow = '';
    document.documentElement.style.position = '';
    document.documentElement.style.inset = '';
    document.documentElement.style.width = '';
}

/* ===== Fullscreen ===== */

function tinderEnterFullscreen() {
    const el = document.documentElement;
    if (el.requestFullscreen) el.requestFullscreen().catch(() => {});
    else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
}

/* ===== Init ===== */

function initTinder() {
    const container = document.getElementById('view-tinder');
    if (!container || !APP.data) return;

    tinderState.isMobile = !window.matchMedia('(hover: hover)').matches;

    try {
        tinderState.votes = JSON.parse(localStorage.getItem('tinder-votes') || '{}');
    } catch { tinderState.votes = {}; }

    const orientation = tinderState.isMobile ? 'portrait' : 'landscape';
    tinderState.photos = shuffleArray(
        APP.data.photos.filter(p =>
            p.orientation === orientation && !tinderState.votes[p.id]
        )
    );
    tinderState.index = 0;
    tinderState.animating = false;
    tinderState._cache = {};

    tinderLockViewport();
    if (tinderState.isMobile) tinderEnterFullscreen();

    container.innerHTML = '';

    const wrapper = document.createElement('div');
    wrapper.className = 'tinder-container';

    const stack = document.createElement('div');
    stack.className = 'tinder-stack';
    stack.id = 'tinder-stack';

    const actions = document.createElement('div');
    actions.className = 'tinder-actions';
    actions.id = 'tinder-actions';

    if (!tinderState.isMobile) {
        const rejectBtn = document.createElement('button');
        rejectBtn.className = 'tinder-btn tinder-btn-reject';
        rejectBtn.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>';
        rejectBtn.addEventListener('click', () => voteTinder('reject'));

        const acceptBtn = document.createElement('button');
        acceptBtn.className = 'tinder-btn tinder-btn-accept';
        acceptBtn.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>';
        acceptBtn.addEventListener('click', () => voteTinder('accept'));

        actions.appendChild(rejectBtn);
        actions.appendChild(acceptBtn);
    }

    const counter = document.createElement('div');
    counter.className = 'tinder-counter';
    counter.id = 'tinder-counter';

    const minimap = document.createElement('div');
    minimap.className = 'tinder-minimap';
    minimap.id = 'tinder-minimap';

    wrapper.appendChild(stack);
    wrapper.appendChild(actions);
    wrapper.appendChild(counter);
    wrapper.appendChild(minimap);
    container.appendChild(wrapper);

    if (tinderState._keyHandler) {
        document.removeEventListener('keydown', tinderState._keyHandler);
    }
    const keyHandler = (e) => {
        if (APP.currentView !== 'tinder') return;
        if (e.key === 'ArrowLeft') { e.preventDefault(); voteTinder('reject'); }
        else if (e.key === 'ArrowRight') { e.preventDefault(); voteTinder('accept'); }
    };
    document.addEventListener('keydown', keyHandler);
    tinderState._keyHandler = keyHandler;

    tinderPreloadBuffer();
    tinderRenderStack();
    updateTinderCounter();
    renderTinderMinimap();
}

function updateTinderCounter() {
    const el = document.getElementById('tinder-counter');
    if (!el) return;
    const total = tinderState.photos.length;
    const current = Math.min(tinderState.index + 1, total);
    el.textContent = total === 0 ? 'All done' : current + ' / ' + total;
}

/* ===== Preload buffer ===== */

function tinderPreloadBuffer() {
    const tier = tinderState.isMobile ? 'mobile' : 'display';
    const end = Math.min(tinderState.index + 1 + TINDER_PRELOAD_AHEAD, tinderState.photos.length);
    for (let i = tinderState.index + 1; i < end; i++) {
        const photo = tinderState.photos[i];
        if (tinderState._cache[photo.id]) continue;
        const src = photo[tier] || photo.thumb;
        if (!src) continue;
        const img = new Image();
        img.decoding = 'async';
        img.src = src;
        if (typeof img.decode === 'function') {
            img.decode().then(() => {
                if (tinderState._cache[photo.id]) tinderState._cache[photo.id].decoded = true;
            }).catch(() => {});
        }
        tinderState._cache[photo.id] = { src, img, decoded: false };
    }
}

function tinderCachedSrc(photo) {
    const entry = tinderState._cache[photo.id];
    return entry ? entry.src : null;
}

/* ===== Two-card stack ===== */
/* The stack always has two cards: back (next) underneath, front (current) on top.
   On swipe, the front flies away revealing the back instantly.
   Then we promote back→front and build a new back card. */

function tinderBuildCard(photo, isFront) {
    const card = document.createElement('div');
    card.className = 'tinder-card' + (isFront ? ' tinder-card-front' : ' tinder-card-back');
    card.dataset.photoId = photo.id;

    const overlayAccept = document.createElement('div');
    overlayAccept.className = 'tinder-overlay tinder-overlay-accept';
    const overlayReject = document.createElement('div');
    overlayReject.className = 'tinder-overlay tinder-overlay-reject';
    card.appendChild(overlayAccept);
    card.appendChild(overlayReject);

    const img = document.createElement('img');
    img.alt = photo.alt || photo.caption || '';
    img.draggable = false;

    const cachedSrc = tinderCachedSrc(photo);
    if (cachedSrc) {
        img.src = cachedSrc;
        if (photo.focus) img.style.objectPosition = photo.focus[0] + '% ' + photo.focus[1] + '%';
        img.classList.add('img-loading');
        if (typeof img.decode === 'function') {
            img.decode().then(() => revealImg(img)).catch(() => revealImg(img));
        } else {
            revealImg(img);
        }
    } else {
        const tier = tinderState.isMobile ? 'mobile' : 'display';
        loadProgressive(img, photo, tier);
    }
    card.appendChild(img);
    return card;
}

function tinderRenderStack() {
    const stack = document.getElementById('tinder-stack');
    if (!stack) return;

    const idx = tinderState.index;
    const photos = tinderState.photos;

    if (idx >= photos.length) {
        stack.innerHTML = '<div class="tinder-empty">No more photos to review</div>';
        const actions = document.getElementById('tinder-actions');
        if (actions) actions.style.display = 'none';
        updateTinderCounter();
        return;
    }

    stack.innerHTML = '';

    /* Back card (next photo) — rendered first, sits behind */
    if (idx + 1 < photos.length) {
        stack.appendChild(tinderBuildCard(photos[idx + 1], false));
    }

    /* Front card (current photo) — on top */
    const front = tinderBuildCard(photos[idx], true);
    stack.appendChild(front);

    if (tinderState.isMobile) {
        const oa = front.querySelector('.tinder-overlay-accept');
        const or = front.querySelector('.tinder-overlay-reject');
        setupTinderSwipe(front, oa, or);
    }

    tinderPreloadBuffer();
}

/* After a vote animation completes, advance and rebuild the stack */
function tinderAdvance() {
    tinderState.index++;
    tinderState.animating = false;

    const stack = document.getElementById('tinder-stack');
    if (!stack) return;

    const idx = tinderState.index;
    const photos = tinderState.photos;

    if (idx >= photos.length) {
        stack.innerHTML = '<div class="tinder-empty">No more photos to review</div>';
        const actions = document.getElementById('tinder-actions');
        if (actions) actions.style.display = 'none';
        updateTinderCounter();
        renderTinderMinimap();
        return;
    }

    /* Remove the old front card (already animated off-screen) */
    const oldFront = stack.querySelector('.tinder-card-front');
    if (oldFront) oldFront.remove();

    /* Promote back card to front with smooth scale-up */
    const backCard = stack.querySelector('.tinder-card-back');
    if (backCard) {
        /* Enable transition for the promotion scale-up (0.97 → 1.0) */
        backCard.classList.add('tinder-card-promoting');
        backCard.classList.remove('tinder-card-back');
        backCard.classList.add('tinder-card-front');
        /* Remove promotion class after transition completes (280ms + margin) */
        setTimeout(() => backCard.classList.remove('tinder-card-promoting'), 320);
        if (tinderState.isMobile) {
            const oa = backCard.querySelector('.tinder-overlay-accept');
            const or = backCard.querySelector('.tinder-overlay-reject');
            setupTinderSwipe(backCard, oa, or);
        }
    }

    /* Build new back card for the one after */
    if (idx + 1 < photos.length) {
        const newBack = tinderBuildCard(photos[idx + 1], false);
        /* Insert before the front card so it renders behind */
        if (backCard) {
            stack.insertBefore(newBack, backCard);
        } else {
            stack.appendChild(newBack);
        }
    }

    tinderPreloadBuffer();
    updateTinderCounter();
    renderTinderMinimap();
}

/* ===== Swipe ===== */

function setupTinderSwipe(card, overlayAccept, overlayReject) {
    let startX = 0, startY = 0, deltaX = 0;
    let tracking = false, rafId = 0;
    let dirLocked = false, swipeDir = null;
    /* Velocity tracking: last 3 move samples */
    let vSamples = [];

    function resetSwipe() {
        tracking = false;
        if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    }

    card.addEventListener('touchstart', (e) => {
        if (tinderState.animating) return;
        startX = e.touches[0].clientX;
        startY = e.touches[0].clientY;
        deltaX = 0;
        tracking = true;
        dirLocked = false;
        swipeDir = null;
        vSamples = [{ x: startX, t: performance.now() }];
        card.style.transition = 'none';
        overlayAccept.style.transition = 'none';
        overlayReject.style.transition = 'none';
        /* Micro grab feedback — tiny scale-down */
        card.style.transform = 'translate3d(0,0,0) scale(' + TINDER_GRAB_SCALE + ')';
    }, { passive: false });

    card.addEventListener('touchmove', (e) => {
        if (!tracking) return;
        const cx = e.touches[0].clientX;
        const dx = cx - startX;
        const dy = e.touches[0].clientY - startY;

        if (!dirLocked && (Math.abs(dx) > 8 || Math.abs(dy) > 8)) {
            dirLocked = true;
            swipeDir = Math.abs(dx) >= Math.abs(dy) ? 'h' : 'v';
        }
        if (swipeDir === 'v') return;
        e.preventDefault();
        deltaX = dx;

        /* Keep last 3 samples for velocity calc */
        const now = performance.now();
        vSamples.push({ x: cx, t: now });
        if (vSamples.length > 3) vSamples.shift();

        if (!rafId) {
            rafId = requestAnimationFrame(() => {
                rafId = 0;
                const rot = deltaX * TINDER_ROTATION_FACTOR;
                card.style.transform = 'translate3d(' + deltaX + 'px,0,0) rotate(' + rot + 'deg)';
                /* Eased overlay: quadratic ramp — feels more intentional */
                const t = Math.min(Math.abs(deltaX) / 160, 1);
                const intensity = t * t * 0.5;
                if (deltaX > 0) {
                    overlayAccept.style.opacity = intensity;
                    overlayReject.style.opacity = '0';
                } else {
                    overlayReject.style.opacity = intensity;
                    overlayAccept.style.opacity = '0';
                }
            });
        }
    }, { passive: false });

    function endTouch() {
        if (!tracking) return;
        resetSwipe();

        if (swipeDir === 'h' && Math.abs(deltaX) > TINDER_SWIPE_THRESHOLD) {
            /* Calculate exit velocity from last samples */
            let vel = 0;
            if (vSamples.length >= 2) {
                const a = vSamples[0], b = vSamples[vSamples.length - 1];
                const dt = b.t - a.t;
                if (dt > 0) vel = Math.abs(b.x - a.x) / dt; /* px/ms */
            }
            voteTinder(deltaX > 0 ? 'accept' : 'reject', vel);
        } else {
            /* Spring back — custom spring curve */
            card.style.transition = 'transform .35s cubic-bezier(.175,.885,.32,1.1)';
            overlayAccept.style.transition = 'opacity .25s ease-out';
            overlayReject.style.transition = 'opacity .25s ease-out';
            card.style.transform = '';
            overlayAccept.style.opacity = '0';
            overlayReject.style.opacity = '0';
        }
    }

    card.addEventListener('touchend', endTouch, { passive: true });
    card.addEventListener('touchcancel', endTouch, { passive: true });
}

/* ===== Vote ===== */

function voteTinder(vote, swipeVelocity) {
    if (tinderState.animating) return;
    if (tinderState.index >= tinderState.photos.length) return;

    tinderState.animating = true;
    const photo = tinderState.photos[tinderState.index];
    const card = document.querySelector('.tinder-card-front');

    tinderState.votes[photo.id] = vote;
    try {
        localStorage.setItem('tinder-votes', JSON.stringify(tinderState.votes));
    } catch {}

    try {
        if (typeof db !== 'undefined') {
            db.collection('tinder-votes').add({
                photo: photo.id,
                vote: vote,
                device: tinderState.isMobile ? 'mobile' : 'desktop',
                ts: firebase.firestore.FieldValue.serverTimestamp()
            });
        }
    } catch (e) {}

    if (card) {
        const dir = vote === 'accept' ? 1 : -1;
        const ov = card.querySelector(vote === 'accept' ? '.tinder-overlay-accept' : '.tinder-overlay-reject');
        if (ov) { ov.style.transition = 'none'; ov.style.opacity = '0.4'; }

        /* Velocity-aware exit: faster swipes fly farther and faster */
        const vel = Math.max(swipeVelocity || 0, TINDER_MIN_EXIT_V);
        const dist = Math.min(180 + vel * 250, 500);
        const dur = Math.max(0.15, Math.min(0.32, 180 / (vel * 1000)));
        const rot = dir * Math.min(8 + vel * 6, 18);

        card.style.transition = 'transform ' + dur + 's cubic-bezier(.2,.6,.3,1), opacity ' + dur + 's ease-out';
        card.style.transform = 'translate3d(' + (dir * dist) + 'px,0,0) rotate(' + rot + 'deg)';
        card.style.opacity = '0';
        card.style.pointerEvents = 'none';

        /* Use transitionend for precise timing instead of setTimeout */
        let advanced = false;
        const onEnd = () => {
            if (advanced) return;
            advanced = true;
            card.removeEventListener('transitionend', onEnd);
            tinderAdvance();
        };
        card.addEventListener('transitionend', onEnd);
        /* Safety fallback in case transitionend doesn't fire (iOS edge case) */
        setTimeout(onEnd, dur * 1000 + 50);
    } else {
        tinderAdvance();
    }
}

/* ===== Minimap ===== */

function renderTinderMinimap() {
    const el = document.getElementById('tinder-minimap');
    if (!el) return;
    el.innerHTML = '';

    const idx = tinderState.index;
    const photos = tinderState.photos;
    const total = photos.length;
    if (total === 0) return;

    for (let i = idx - 3; i <= idx + 3; i++) {
        const slot = document.createElement('div');
        slot.className = 'tinder-mini-slot';

        if (i < 0 || i >= total) {
            slot.classList.add('tinder-mini-empty');
            el.appendChild(slot);
            continue;
        }

        const photo = photos[i];
        const img = document.createElement('img');
        img.draggable = false;
        const src = photo.thumb || photo.mobile || '';
        if (src) img.src = src;
        if (photo.focus) img.style.objectPosition = photo.focus[0] + '% ' + photo.focus[1] + '%';
        slot.appendChild(img);

        if (i === idx) {
            slot.classList.add('tinder-mini-current');
        } else if (i < idx) {
            const vote = tinderState.votes[photo.id];
            const tint = document.createElement('div');
            tint.className = 'tinder-mini-tint';
            tint.classList.add(vote === 'accept' ? 'tinder-mini-accept' : 'tinder-mini-reject');
            slot.appendChild(tint);
            slot.style.cursor = 'pointer';
            slot.addEventListener('click', () => {
                if (tinderState.animating) return;
                tinderGoBack(i);
            });
        } else {
            slot.classList.add('tinder-mini-future');
        }

        el.appendChild(slot);
    }
}

function tinderGoBack(targetIndex) {
    const photo = tinderState.photos[targetIndex];
    if (!photo) return;

    delete tinderState.votes[photo.id];
    try {
        localStorage.setItem('tinder-votes', JSON.stringify(tinderState.votes));
    } catch {}

    tinderState.index = targetIndex;
    tinderState.animating = false;
    tinderRenderStack();
    updateTinderCounter();
    renderTinderMinimap();
}
