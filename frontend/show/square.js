/* square.js — Shuffleboard: Polaroid toss experience.
   Deck at bottom center, toss cards onto a scattered stage.
   Cards are draggable, clickable for lightbox. Auto-toss every ~2s. */

let sqPool = [];
let sqDeckIdx = 0;
let sqTossed = [];
let sqAutoPlay = true;
let sqAutoTimer = null;
let sqDragging = null;

const SQ_AUTO_MS = 2000;
const SQ_MAX_CARDS = 25;

function initSquare() {
    const container = document.getElementById('view-square');
    container.innerHTML = '';

    clearInterval(sqAutoTimer);
    sqAutoTimer = null;
    sqTossed = [];
    sqDeckIdx = 0;
    sqAutoPlay = true;
    sqDragging = null;

    /* Shuffle photo pool */
    sqPool = APP.data.photos.filter(p => p.thumb);
    shuffleArray(sqPool);

    /* Build shell */
    const stage = document.createElement('div');
    stage.className = 'sq-stage';
    stage.id = 'sq-stage';

    const deck = document.createElement('div');
    deck.className = 'sq-deck';
    deck.id = 'sq-deck';

    const deckStack = document.createElement('div');
    deckStack.className = 'sq-deck-stack';
    deckStack.addEventListener('click', () => tossSq());

    const deckCount = document.createElement('div');
    deckCount.className = 'sq-deck-count';
    deckCount.id = 'sq-deck-count';
    deckCount.textContent = sqPool.length;

    deck.appendChild(deckStack);
    deck.appendChild(deckCount);

    container.appendChild(stage);
    container.appendChild(deck);

    /* Keyboard */
    document.removeEventListener('keydown', sqKeyHandler);
    document.addEventListener('keydown', sqKeyHandler);

    /* Start auto-play */
    startSqAuto();
}

function startSqAuto() {
    clearInterval(sqAutoTimer);
    if (!sqAutoPlay) return;
    sqAutoTimer = setInterval(() => {
        if (!sqAutoPlay || APP.currentView !== 'square') return;
        tossSq();
    }, SQ_AUTO_MS);
    APP._activeTimers.push(sqAutoTimer);
}

function tossSq() {
    if (sqDeckIdx >= sqPool.length) {
        /* Reshuffle when deck exhausted */
        shuffleArray(sqPool);
        sqDeckIdx = 0;
    }

    const photo = sqPool[sqDeckIdx++];
    const stage = document.getElementById('sq-stage');
    if (!stage) return;

    /* Random landing position & rotation */
    const stageRect = stage.getBoundingClientRect();
    const cardW = window.innerWidth <= 480 ? 110 : window.innerWidth <= 768 ? 140 : 180;
    const padX = cardW / 2 + 10;
    const padY = cardW * 1.25 / 2 + 10;
    const endX = padX + Math.random() * (stageRect.width - padX * 2);
    const endY = padY + Math.random() * (stageRect.height - padY * 2 - 80);
    const endRot = (Math.random() - 0.5) * 30; /* -15 to 15 degrees */

    /* Build card */
    const card = document.createElement('div');
    card.className = 'sq-card';
    card.style.setProperty('--sq-end-x', endX + 'px');
    card.style.setProperty('--sq-end-y', endY + 'px');
    card.style.setProperty('--sq-end-rot', endRot + 'deg');
    card.dataset.photoId = photo.id;

    const img = document.createElement('img');
    loadProgressive(img, photo, 'thumb');
    img.alt = '';
    img.draggable = false;
    card.appendChild(img);

    const caption = photo.florence || photo.caption || '';
    if (caption) {
        const capEl = document.createElement('div');
        capEl.className = 'sq-card-caption';
        capEl.textContent = caption.length > 60 ? caption.slice(0, 57) + '...' : caption;
        card.appendChild(capEl);
    }

    /* Toss animation */
    card.classList.add('sq-tossing');
    card.addEventListener('animationend', () => {
        card.classList.remove('sq-tossing');
        card.style.transform = `translate(${endX}px, ${endY}px) rotate(${endRot}deg)`;
    }, { once: true });

    /* Click → lightbox (only if not dragging) */
    let didDrag = false;
    card.addEventListener('click', (e) => {
        if (didDrag) { didDrag = false; return; }
        openLightbox(photo, sqPool);
    });

    /* Drag via pointer events — rAF-throttled for 120Hz */
    card.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        card.setPointerCapture(e.pointerId);
        didDrag = false;

        const rect = card.getBoundingClientRect();
        const stageR = stage.getBoundingClientRect();
        const offsetX = e.clientX - rect.left;
        const offsetY = e.clientY - rect.top;

        /* Lift to top + promote layer for drag */
        card.style.zIndex = Date.now() % 100000;
        card.style.transition = 'none';
        card.style.willChange = 'transform';
        card.classList.add('sq-dragging');

        let rafId = 0;
        let lastX = 0, lastY = 0;

        const onMove = (ev) => {
            didDrag = true;
            lastX = ev.clientX - stageR.left - offsetX;
            lastY = ev.clientY - stageR.top - offsetY;
            if (!rafId) {
                rafId = requestAnimationFrame(() => {
                    card.style.transform = `translate(${lastX}px, ${lastY}px) rotate(${endRot}deg)`;
                    rafId = 0;
                });
            }
        };

        const onUp = (ev) => {
            card.removeEventListener('pointermove', onMove);
            card.removeEventListener('pointerup', onUp);
            if (rafId) { cancelAnimationFrame(rafId); rafId = 0; }
            card.style.transition = '';
            card.style.willChange = 'auto';
            card.classList.remove('sq-dragging');
            /* Update end position for future reference */
            const finalRect = card.getBoundingClientRect();
            const finalX = finalRect.left - stageR.left;
            const finalY = finalRect.top - stageR.top;
            card.style.setProperty('--sq-end-x', finalX + 'px');
            card.style.setProperty('--sq-end-y', finalY + 'px');
        };

        card.addEventListener('pointermove', onMove);
        card.addEventListener('pointerup', onUp);
    });

    stage.appendChild(card);
    sqTossed.push({ card, photo });

    /* Enforce max cards on stage */
    while (sqTossed.length > SQ_MAX_CARDS) {
        const oldest = sqTossed.shift();
        oldest.card.classList.add('sq-scatter');
        oldest.card.addEventListener('animationend', () => {
            oldest.card.remove();
        }, { once: true });
    }

    /* Update deck count */
    updateSqDeckCount();
}

function undoToss() {
    if (sqTossed.length === 0) return;
    const last = sqTossed.pop();
    last.card.classList.add('sq-scatter');
    last.card.addEventListener('animationend', () => {
        last.card.remove();
    }, { once: true });
    sqDeckIdx = Math.max(0, sqDeckIdx - 1);
    updateSqDeckCount();
}

function clearSqStage() {
    for (const item of sqTossed) {
        item.card.classList.add('sq-scatter');
        item.card.addEventListener('animationend', () => {
            item.card.remove();
        }, { once: true });
    }
    sqTossed = [];
    updateSqDeckCount();
}

function updateSqDeckCount() {
    const el = document.getElementById('sq-deck-count');
    if (el) el.textContent = sqTossed.length + ' on stage';
}

function sqKeyHandler(e) {
    if (APP.currentView !== 'square') return;
    if (e.code === 'Space') {
        e.preventDefault();
        sqAutoPlay = !sqAutoPlay;
        if (sqAutoPlay) startSqAuto();
        else clearInterval(sqAutoTimer);
    } else if (e.key === 'ArrowRight') {
        e.preventDefault();
        tossSq();
    } else if (e.key === 'ArrowLeft') {
        e.preventDefault();
        undoToss();
    } else if (e.key === 'Escape') {
        e.preventDefault();
        clearSqStage();
    }
}
