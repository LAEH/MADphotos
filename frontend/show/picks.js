/* picks.js — Re-curation pass on accepted Tinder picks.
   Tinder-style two-card stack. Swipe right = keep, swipe left = remove.
   Data source: picks.json. Votes stored in localStorage('picks-votes') + Firestore.
   Reuses .tinder-* CSS classes for the card stack UI. */

const PICKS_PRELOAD_AHEAD = 10;
const PICKS_SWIPE_THRESHOLD = 80;
const PICKS_ROTATION_FACTOR = 0.03;
const PICKS_GRAB_SCALE = 0.985;
const PICKS_MIN_EXIT_V = 0.8;

let picksState = {
    photos: [],
    index: 0,
    isMobile: false,     /* screen ≤ 768px — controls orientation + image tier */
    hasTouch: false,      /* touch device — controls swipe handlers */
    hasHover: false,      /* cursor/trackpad — controls hover zones */
    votes: {},
    animating: false,
    _keyHandler: null,
    _cache: {},
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
    document.body.classList.remove('picks-bg-reject', 'picks-bg-accept');
}

/* ===== Init ===== */

function initPicks() {
    const container = document.getElementById('view-picks');
    if (!container || !APP.data) return;

    picksState.isMobile = window.innerWidth <= 768;
    picksState.hasTouch = 'ontouchstart' in window;
    picksState.hasHover = window.matchMedia('(any-hover: hover)').matches;

    try {
        picksState.votes = JSON.parse(localStorage.getItem('picks-votes') || '{}');
    } catch { picksState.votes = {}; }

    const picksData = APP.picksData || { portrait: [], landscape: [] };
    const orientation = picksState.isMobile ? 'portrait' : 'landscape';
    const ids = picksData[orientation] || [];

    /* Resolve IDs, exclude photos already rejected in picks */
    const photos = [];
    for (const id of ids) {
        if (picksState.votes[id] === 'reject') continue;
        const p = APP.photoMap[id];
        if (p) photos.push(p);
    }
    picksState.photos = shuffleArray(photos);
    picksState.index = 0;
    picksState.animating = false;
    picksState._cache = {};
    picksState._inited = true;

    picksLockViewport();

    container.innerHTML = '';

    if (photos.length === 0) {
        container.innerHTML = '<div class="picks-empty">All reviewed \ud83c\udf89</div>';
        return;
    }

    const wrapper = document.createElement('div');
    wrapper.className = 'tinder-container';

    const stack = document.createElement('div');
    stack.className = 'tinder-stack';
    stack.id = 'picks-stack';

    const counter = document.createElement('div');
    counter.className = 'tinder-counter';
    counter.id = 'picks-counter';

    const minimap = document.createElement('div');
    minimap.className = 'tinder-minimap';
    minimap.id = 'picks-minimap';

    wrapper.appendChild(stack);
    wrapper.appendChild(counter);
    wrapper.appendChild(minimap);
    container.appendChild(wrapper);

    if (picksState._keyHandler) {
        document.removeEventListener('keydown', picksState._keyHandler);
    }
    const keyHandler = (e) => {
        if (APP.currentView !== 'picks') return;
        if (e.key === 'ArrowLeft') { e.preventDefault(); votePicks('reject'); }
        else if (e.key === 'ArrowRight') { e.preventDefault(); votePicks('accept'); }
    };
    document.addEventListener('keydown', keyHandler);
    picksState._keyHandler = keyHandler;

    picksPreloadBuffer();
    picksRenderStack();
    updatePicksCounter();
    renderPicksMinimap();
}

/* ===== Counter ===== */

function updatePicksCounter() {
    const el = document.getElementById('picks-counter');
    if (!el) return;
    const total = picksState.photos.length;
    const current = Math.min(picksState.index + 1, total);
    el.textContent = total === 0 ? 'All reviewed \ud83c\udf89' : current + ' / ' + total;
}

/* ===== Preload buffer ===== */

function picksPreloadBuffer() {
    const tier = cardImageTier();
    const end = Math.min(picksState.index + 1 + PICKS_PRELOAD_AHEAD, picksState.photos.length);
    for (let i = picksState.index + 1; i < end; i++) {
        const photo = picksState.photos[i];
        if (picksState._cache[photo.id]) continue;
        const src = photo[tier] || photo.mobile || photo.thumb;
        if (!src) continue;
        const img = new Image();
        img.decoding = 'async';
        img.src = src;
        if (typeof DECODE_QUEUE !== 'undefined') {
            DECODE_QUEUE.enqueue(img).then(() => {
                if (picksState._cache[photo.id]) picksState._cache[photo.id].decoded = true;
            });
        } else if (typeof img.decode === 'function') {
            img.decode().then(() => {
                if (picksState._cache[photo.id]) picksState._cache[photo.id].decoded = true;
            }).catch(() => {});
        }
        picksState._cache[photo.id] = { src, img, decoded: false };
    }
}

/* ===== Two-card stack ===== */

function picksBuildCard(photo, isFront) {
    const card = document.createElement('div');
    card.className = 'tinder-card' + (isFront ? ' tinder-card-front' : ' tinder-card-back');
    card.dataset.photoId = photo.id;

    const overlayAccept = document.createElement('div');
    overlayAccept.className = 'tinder-overlay tinder-overlay-accept';
    const overlayReject = document.createElement('div');
    overlayReject.className = 'tinder-overlay tinder-overlay-reject';
    card.appendChild(overlayAccept);
    card.appendChild(overlayReject);
    if (photo.palette && photo.palette[0]) card.style.backgroundColor = photo.palette[0] + '55';

    const img = document.createElement('img');
    img.alt = photo.alt || photo.caption || '';
    img.draggable = false;
    if (photo.focus) img.style.objectPosition = photo.focus[0] + '% ' + photo.focus[1] + '%';

    /* Thumb-first: show thumb immediately (visible), upgrade to full-res when decoded.
       No opacity:0 / img-loading — the thumb IS the instant placeholder. */
    const cached = picksState._cache[photo.id];
    if (cached && cached.decoded) {
        /* Full-res already decoded in preload buffer — use it directly */
        img.src = cached.src;
    } else {
        /* Show thumb immediately */
        if (photo.thumb) img.src = photo.thumb;

        /* Upgrade to full-res in background */
        const tier = cardImageTier();
        const fullSrc = cached ? cached.src : (photo[tier] || photo.mobile || photo.thumb);
        if (fullSrc && fullSrc !== photo.thumb) {
            const pre = cached ? cached.img : new Image();
            if (!cached) { pre.decoding = 'async'; pre.src = fullSrc; }
            const doUpgrade = () => {
                if (img.isConnected !== false) img.src = fullSrc;
            };
            if (cached && cached.img && typeof cached.img.decode === 'function') {
                cached.img.decode().then(doUpgrade).catch(doUpgrade);
            } else if (typeof pre.decode === 'function') {
                pre.decode().then(doUpgrade).catch(doUpgrade);
            } else {
                pre.onload = doUpgrade;
            }
        }
    }
    /* Priority hint: front card loads first */
    if (isFront) img.fetchPriority = 'high';

    card.appendChild(img);

    /* Hover zones on front card for any device with cursor/trackpad */
    if (isFront && picksState.hasHover) {
        setupPicksHoverZones(card);
    }

    return card;
}

/* ===== Desktop hover zones ===== */

function setupPicksHoverZones(card) {
    const zoneReject = document.createElement('div');
    zoneReject.className = 'tinder-hover-zone tinder-hover-left';
    const iconReject = document.createElement('div');
    iconReject.className = 'tinder-hover-icon tinder-hover-icon-reject';
    iconReject.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M18 6L6 18M6 6l12 12"/></svg>';
    zoneReject.appendChild(iconReject);

    const zoneAccept = document.createElement('div');
    zoneAccept.className = 'tinder-hover-zone tinder-hover-right';
    const iconAccept = document.createElement('div');
    iconAccept.className = 'tinder-hover-icon tinder-hover-icon-accept';
    iconAccept.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg>';
    zoneAccept.appendChild(iconAccept);

    const body = document.body;
    function clearBgTint() {
        body.classList.remove('picks-bg-reject', 'picks-bg-accept');
    }

    zoneReject.addEventListener('pointerenter', () => {
        zoneReject.classList.add('hovered');
        clearBgTint();
        body.classList.add('picks-bg-reject');
    });
    zoneReject.addEventListener('pointerleave', () => {
        zoneReject.classList.remove('hovered');
        clearBgTint();
    });
    zoneReject.addEventListener('click', (e) => {
        e.stopPropagation();
        zoneReject.classList.remove('hovered');
        clearBgTint();
        votePicks('reject');
    });

    zoneAccept.addEventListener('pointerenter', () => {
        zoneAccept.classList.add('hovered');
        clearBgTint();
        body.classList.add('picks-bg-accept');
    });
    zoneAccept.addEventListener('pointerleave', () => {
        zoneAccept.classList.remove('hovered');
        clearBgTint();
    });
    zoneAccept.addEventListener('click', (e) => {
        e.stopPropagation();
        zoneAccept.classList.remove('hovered');
        clearBgTint();
        votePicks('accept');
    });

    card.appendChild(zoneReject);
    card.appendChild(zoneAccept);
}

function picksRenderStack() {
    const stack = document.getElementById('picks-stack');
    if (!stack) return;

    const idx = picksState.index;
    const photos = picksState.photos;

    if (idx >= photos.length) {
        stack.innerHTML = '<div class="tinder-empty">All reviewed \ud83c\udf89</div>';

        updatePicksCounter();
        return;
    }

    stack.innerHTML = '';

    /* Back card (next photo) — rendered first, sits behind */
    if (idx + 1 < photos.length) {
        stack.appendChild(picksBuildCard(photos[idx + 1], false));
    }

    /* Front card (current photo) — on top */
    const front = picksBuildCard(photos[idx], true);
    stack.appendChild(front);

    if (picksState.hasTouch) {
        const oa = front.querySelector('.tinder-overlay-accept');
        const or = front.querySelector('.tinder-overlay-reject');
        setupPicksSwipe(front, oa, or);
    }

    picksPreloadBuffer();
}

/* After a vote animation completes, advance and rebuild the stack */
function picksAdvance() {
    picksState.index++;
    picksState.animating = false;

    const stack = document.getElementById('picks-stack');
    if (!stack) return;

    const idx = picksState.index;
    const photos = picksState.photos;

    if (idx >= photos.length) {
        stack.innerHTML = '<div class="tinder-empty">All reviewed \ud83c\udf89</div>';

        updatePicksCounter();
        renderPicksMinimap();
        return;
    }

    /* Remove the old front card */
    const oldFront = stack.querySelector('.tinder-card-front');
    if (oldFront) oldFront.remove();

    /* Promote back card to front */
    const backCard = stack.querySelector('.tinder-card-back');
    if (backCard) {
        backCard.classList.add('tinder-card-promoting');
        backCard.classList.remove('tinder-card-back');
        backCard.classList.add('tinder-card-front');
        setTimeout(() => backCard.classList.remove('tinder-card-promoting'), 320);
        const oa = backCard.querySelector('.tinder-overlay-accept');
        const or = backCard.querySelector('.tinder-overlay-reject');
        if (picksState.hasTouch) setupPicksSwipe(backCard, oa, or);
        if (picksState.hasHover) setupPicksHoverZones(backCard);
    }

    /* Build new back card */
    if (idx + 1 < photos.length) {
        const newBack = picksBuildCard(photos[idx + 1], false);
        if (backCard) {
            stack.insertBefore(newBack, backCard);
        } else {
            stack.appendChild(newBack);
        }
    }

    picksPreloadBuffer();
    updatePicksCounter();
    renderPicksMinimap();
}

/* ===== Swipe ===== */

function setupPicksSwipe(card, overlayAccept, overlayReject) {
    let startX = 0, startY = 0, deltaX = 0;
    let tracking = false, rafId = 0;
    let dirLocked = false, swipeDir = null;
    let vSamples = [];

    function resetSwipe() {
        tracking = false;
        if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
    }

    card.addEventListener('touchstart', (e) => {
        if (picksState.animating) return;
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
        card.style.transform = 'translate3d(0,0,0) scale(' + PICKS_GRAB_SCALE + ')';
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

        const now = performance.now();
        vSamples.push({ x: cx, t: now });
        if (vSamples.length > 3) vSamples.shift();

        if (!rafId) {
            rafId = requestAnimationFrame(() => {
                rafId = 0;
                const rot = deltaX * PICKS_ROTATION_FACTOR;
                card.style.transform = 'translate3d(' + deltaX + 'px,0,0) rotate(' + rot + 'deg)';
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

        if (swipeDir === 'h' && Math.abs(deltaX) > PICKS_SWIPE_THRESHOLD) {
            let vel = 0;
            if (vSamples.length >= 2) {
                const a = vSamples[0], b = vSamples[vSamples.length - 1];
                const dt = b.t - a.t;
                if (dt > 0) vel = Math.abs(b.x - a.x) / dt;
            }
            votePicks(deltaX > 0 ? 'accept' : 'reject', vel);
        } else {
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

function votePicks(vote, swipeVelocity) {
    if (picksState.animating) return;
    if (picksState.index >= picksState.photos.length) return;

    picksState.animating = true;
    const photo = picksState.photos[picksState.index];
    const card = document.querySelector('#picks-stack .tinder-card-front');

    picksState.votes[photo.id] = vote;
    try {
        localStorage.setItem('picks-votes', JSON.stringify(picksState.votes));
    } catch {}

    try {
        if (typeof db !== 'undefined') {
            db.collection('picks-votes').add({
                photo: photo.id,
                vote: vote,
                device: picksState.isMobile ? 'mobile' : 'desktop',
                ts: firebase.firestore.FieldValue.serverTimestamp()
            });
        }
    } catch (e) {}

    if (card) {
        const dir = vote === 'accept' ? 1 : -1;
        const ov = card.querySelector(vote === 'accept' ? '.tinder-overlay-accept' : '.tinder-overlay-reject');
        if (ov) { ov.style.transition = 'none'; ov.style.opacity = '0.4'; }

        const vel = Math.max(swipeVelocity || 0, PICKS_MIN_EXIT_V);
        const dist = Math.min(180 + vel * 250, 500);
        const dur = Math.max(0.15, Math.min(0.32, 180 / (vel * 1000)));
        const rot = dir * Math.min(8 + vel * 6, 18);

        card.style.transition = 'transform ' + dur + 's cubic-bezier(.2,.6,.3,1), opacity ' + dur + 's ease-out';
        card.style.transform = 'translate3d(' + (dir * dist) + 'px,0,0) rotate(' + rot + 'deg)';
        card.style.opacity = '0';
        card.style.pointerEvents = 'none';

        let advanced = false;
        const onEnd = () => {
            if (advanced) return;
            advanced = true;
            card.removeEventListener('transitionend', onEnd);
            picksAdvance();
        };
        card.addEventListener('transitionend', onEnd);
        setTimeout(onEnd, dur * 1000 + 50);
    } else {
        picksAdvance();
    }
}

/* ===== Minimap ===== */

function renderPicksMinimap() {
    const el = document.getElementById('picks-minimap');
    if (!el) return;
    el.innerHTML = '';

    const idx = picksState.index;
    const photos = picksState.photos;
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
        const src = photo.micro || photo.thumb || '';
        if (src) img.src = src;
        if (photo.focus) img.style.objectPosition = photo.focus[0] + '% ' + photo.focus[1] + '%';
        slot.appendChild(img);

        if (i === idx) {
            slot.classList.add('tinder-mini-current');
        } else if (i < idx) {
            const v = picksState.votes[photo.id];
            const tint = document.createElement('div');
            tint.className = 'tinder-mini-tint';
            tint.classList.add(v === 'accept' ? 'tinder-mini-accept' : 'tinder-mini-reject');
            slot.appendChild(tint);
            slot.style.cursor = 'pointer';
            slot.addEventListener('click', () => {
                if (picksState.animating) return;
                picksGoBack(i);
            });
        } else {
            slot.classList.add('tinder-mini-future');
        }

        el.appendChild(slot);
    }
}

function picksGoBack(targetIndex) {
    const photo = picksState.photos[targetIndex];
    if (!photo) return;

    delete picksState.votes[photo.id];
    try {
        localStorage.setItem('picks-votes', JSON.stringify(picksState.votes));
    } catch {}

    picksState.index = targetIndex;
    picksState.animating = false;
    picksRenderStack();
    updatePicksCounter();
    renderPicksMinimap();
}
