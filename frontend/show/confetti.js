/* confetti.js — Les Confettis: Curated sets assembled as mosaics.
   Choose a set. Watch it explode. Click to reshuffle.
   Viewport-fixed layout. No page scroll. */

let confettiSets = [];
let confettiActiveSet = null;
let confettiAnimating = false;

function initConfetti() {
    const container = document.getElementById('view-confetti');
    container.innerHTML = '';
    confettiActiveSet = null;
    confettiAnimating = false;
    confettiSets = buildConfettiSets();
    renderConfettiSelector(container);

    document.removeEventListener('keydown', handleConfettiKey);
    document.addEventListener('keydown', handleConfettiKey);
}

function handleConfettiKey(e) {
    if (APP.currentView !== 'confetti') return;
    if (e.key === ' ' || e.key === 'Enter') {
        if (confettiActiveSet) { e.preventDefault(); reshuffleConfetti(); }
    } else if (e.key === 'Escape' || e.key === 'Backspace') {
        if (confettiActiveSet) { e.preventDefault(); closeConfettiSet(); }
    }
}

/* ===== Build sets from photo data ===== */
function buildConfettiSets() {
    const pool = APP.data.photos.filter(p => p.thumb);
    const MIN = 25;
    const sets = [];

    /* Group by primary vibe */
    const vibeBuckets = {};
    for (const p of pool) {
        if (p.vibes && p.vibes[0]) {
            const v = p.vibes[0];
            if (!vibeBuckets[v]) vibeBuckets[v] = [];
            vibeBuckets[v].push(p);
        }
    }

    /* Take largest vibe groups, sort each by aesthetic, pick perfect-square count */
    const topVibes = Object.entries(vibeBuckets)
        .filter(([, arr]) => arr.length >= MIN)
        .sort((a, b) => b[1].length - a[1].length)
        .slice(0, 12);

    for (const [vibe, photos] of topVibes) {
        const sorted = [...photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
        const n = sorted.length >= 64 ? 64 : sorted.length >= 49 ? 49 : sorted.length >= 36 ? 36 : 25;
        sets.push({
            id: vibe.replace(/\s+/g, '-').toLowerCase(),
            label: vibe.charAt(0).toUpperCase() + vibe.slice(1),
            photos: sorted.slice(0, n),
            total: photos.length,
        });
    }

    return sets;
}

/* ===== Set selector — grid of mini-mosaic cards ===== */
function renderConfettiSelector(container) {
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'confetti-selector';

    for (const set of confettiSets) {
        const card = document.createElement('div');
        card.className = 'confetti-card';

        /* Mini-mosaic preview: 5×5 of set's best photos */
        const preview = document.createElement('div');
        preview.className = 'confetti-preview';
        const prevCount = Math.min(25, set.photos.length);
        const prevCols = Math.ceil(Math.sqrt(prevCount));
        preview.style.setProperty('--prev-cols', prevCols);

        for (let i = 0; i < prevCount; i++) {
            const img = createLazyImg(set.photos[i], 'thumb');
            img.alt = '';
            lazyObserver.observe(img);
            preview.appendChild(img);
        }

        card.appendChild(preview);

        /* Label bar at bottom */
        const label = document.createElement('div');
        label.className = 'confetti-card-label';

        const name = document.createElement('span');
        name.className = 'confetti-card-name';
        name.textContent = set.label;
        label.appendChild(name);

        const count = document.createElement('span');
        count.className = 'confetti-card-count';
        count.textContent = set.photos.length;
        label.appendChild(count);

        card.appendChild(label);

        card.addEventListener('click', () => openConfettiSet(set));
        wrap.appendChild(card);
    }

    container.appendChild(wrap);
}

/* ===== Open a set — confetti assembly ===== */
function openConfettiSet(set) {
    if (confettiAnimating) return;
    confettiAnimating = true;
    confettiActiveSet = set;

    const container = document.getElementById('view-confetti');
    container.innerHTML = '';

    const stage = document.createElement('div');
    stage.className = 'confetti-stage';

    /* Back button */
    const back = document.createElement('button');
    back.className = 'confetti-back';
    back.innerHTML = '&larr;';
    back.addEventListener('click', (e) => { e.stopPropagation(); closeConfettiSet(); });
    stage.appendChild(back);

    /* Title */
    const title = document.createElement('div');
    title.className = 'confetti-label';
    title.textContent = set.label;
    stage.appendChild(title);

    /* Build mosaic */
    const mosaic = buildConfettiMosaic(set.photos);
    stage.appendChild(mosaic);

    /* Hint */
    const hint = document.createElement('div');
    hint.className = 'confetti-hint';
    hint.textContent = 'Click to reshuffle';
    stage.appendChild(hint);

    container.appendChild(stage);

    /* Trigger assembly after paint */
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            mosaic.classList.add('assembled');
            confettiAnimating = false;
            /* Fade hint after first assembly */
            setTimeout(() => hint.classList.add('visible'), 1800);
        });
    });
}

/* ===== Build the mosaic grid ===== */
function buildConfettiMosaic(photos) {
    const shuffled = shuffleArray([...photos]);
    const n = shuffled.length;
    const cols = Math.ceil(Math.sqrt(n));
    const rows = Math.ceil(n / cols);

    const mosaic = document.createElement('div');
    mosaic.className = 'confetti-mosaic';
    mosaic.id = 'confetti-mosaic';
    mosaic.style.setProperty('--m-cols', cols);
    mosaic.style.setProperty('--m-rows', rows);

    const cx = (cols - 1) / 2;
    const cy = (rows - 1) / 2;
    const maxDist = Math.sqrt(cx * cx + cy * cy) || 1;

    for (let i = 0; i < n; i++) {
        const photo = shuffled[i];
        const cell = document.createElement('div');
        cell.className = 'confetti-cell';

        const img = document.createElement('img');
        loadProgressive(img, photo, 'thumb');
        img.alt = '';
        cell.appendChild(img);

        /* Grid position for stagger */
        const col = i % cols;
        const row = Math.floor(i / cols);
        const dist = Math.sqrt((col - cx) ** 2 + (row - cy) ** 2);

        /* Scatter origin: random point on ring */
        const angle = Math.random() * Math.PI * 2;
        const scatter = 300 + Math.random() * 500;
        cell.style.setProperty('--sx', (Math.cos(angle) * scatter).toFixed(0) + 'px');
        cell.style.setProperty('--sy', (Math.sin(angle) * scatter).toFixed(0) + 'px');
        cell.style.setProperty('--sr', ((Math.random() - 0.5) * 540).toFixed(0) + 'deg');

        /* Assembly stagger: center first, edges last */
        const delay = (dist / maxDist) * 700 + Math.random() * 150;
        cell.style.setProperty('--d', delay.toFixed(0) + 'ms');

        /* Scatter-out stagger: fast random burst */
        cell.style.setProperty('--d-out', (Math.random() * 250).toFixed(0) + 'ms');

        mosaic.appendChild(cell);
    }

    /* Click mosaic to reshuffle */
    mosaic.addEventListener('click', reshuffleConfetti);

    return mosaic;
}

/* ===== Reshuffle — scatter out, rebuild, reassemble ===== */
function reshuffleConfetti() {
    if (confettiAnimating || !confettiActiveSet) return;
    confettiAnimating = true;

    const mosaic = document.getElementById('confetti-mosaic');
    if (!mosaic) { confettiAnimating = false; return; }

    /* Phase 1: scatter out */
    mosaic.classList.remove('assembled');
    mosaic.classList.add('scattering');

    /* Phase 2: rebuild after scatter completes */
    setTimeout(() => {
        const parent = mosaic.parentElement;
        const newMosaic = buildConfettiMosaic(confettiActiveSet.photos);
        parent.replaceChild(newMosaic, mosaic);

        /* Phase 3: assemble new composition */
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                newMosaic.classList.add('assembled');
                confettiAnimating = false;
            });
        });
    }, 550);
}

/* ===== Close — scatter out, return to selector ===== */
function closeConfettiSet() {
    if (confettiAnimating) return;
    confettiAnimating = true;

    const mosaic = document.getElementById('confetti-mosaic');
    if (mosaic) {
        mosaic.classList.remove('assembled');
        mosaic.classList.add('scattering');
    }

    setTimeout(() => {
        confettiActiveSet = null;
        const container = document.getElementById('view-confetti');
        renderConfettiSelector(container);
        confettiAnimating = false;
    }, 550);
}
