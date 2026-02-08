/* reveal.js — Reveal: Clip-path morphing image transitions.
   Full-screen photos revealed through geometric shapes — circles,
   diamonds, stars, hexagons, blobs. Each shape is paired with a
   themed set of images. Click to trigger the next shape-reveal.
   Inspired by MADvids Shape Reveal experiment. */

let revealPhotos = [];
let revealSets = [];
let revealIdx = 0;
let revealSetIdx = 0;
let revealAnimating = false;

const REVEAL_PER_SET = 14;
const REVEAL_DURATION = 1000;

/* Each shape paired with a themed image set */
const REVEAL_DEFS = [
    { name: 'Circle',  label: 'Serene',
      pool: p => vibeHas(p, 'serene', 'calm', 'peaceful', 'tranquil'),
      fn: (cx, cy, t) =>
        'circle(' + (t * 150).toFixed(1) + '% at ' + cx.toFixed(1) + '% ' + cy.toFixed(1) + '%)' },

    { name: 'Diamond', label: 'Intense',
      pool: p => vibeHas(p, 'dramatic', 'intense', 'powerful', 'bold'),
      fn: (cx, cy, t) => {
        const s = t * 110;
        return 'polygon(' + cx.toFixed(1) + '% ' + (cy - s).toFixed(1) + '%, ' +
            (cx + s).toFixed(1) + '% ' + cy.toFixed(1) + '%, ' +
            cx.toFixed(1) + '% ' + (cy + s).toFixed(1) + '%, ' +
            (cx - s).toFixed(1) + '% ' + cy.toFixed(1) + '%)';
    }},

    { name: 'Inset',   label: 'Golden Hour',
      pool: p => p.time === 'golden hour',
      fn: (cx, cy, t) => {
        const b = ((1 - t) * 50).toFixed(1);
        const r = ((1 - t) * 40).toFixed(1);
        return 'inset(' + b + '% ' + b + '% ' + b + '% ' + b + '% round ' + r + '%)';
    }},

    { name: 'Star',    label: 'Night',
      pool: p => p.time === 'night' || p.time === 'blue hour',
      fn: (cx, cy, t) => {
        const outer = t * 130;
        const inner = outer * 0.38;
        const pts = [];
        for (let i = 0; i < 6; i++) {
            const aO = ((i / 6) * 360 - 90) * Math.PI / 180;
            const aI = (((i + 0.5) / 6) * 360 - 90) * Math.PI / 180;
            pts.push((cx + outer * Math.cos(aO)).toFixed(1) + '% ' + (cy + outer * Math.sin(aO)).toFixed(1) + '%');
            pts.push((cx + inner * Math.cos(aI)).toFixed(1) + '% ' + (cy + inner * Math.sin(aI)).toFixed(1) + '%');
        }
        return 'polygon(' + pts.join(', ') + ')';
    }},

    { name: 'Split',   label: 'Nostalgic',
      pool: p => vibeHas(p, 'nostalgic', 'vintage', 'retro', 'timeless'),
      fn: (cx, cy, t) => {
        const gap = ((1 - t) * 50).toFixed(1);
        return 'inset(' + gap + '% 0%)';
    }},

    { name: 'Hexagon', label: 'Nature',
      pool: p => p.scene && /forest|garden|field|mountain|park|lake|beach/.test(p.scene),
      fn: (cx, cy, t) => {
        const r = t * 120;
        const pts = [];
        for (let i = 0; i < 6; i++) {
            const a = ((i / 6) * 360 - 90) * Math.PI / 180;
            pts.push((cx + r * Math.cos(a)).toFixed(1) + '% ' + (cy + r * Math.sin(a)).toFixed(1) + '%');
        }
        return 'polygon(' + pts.join(', ') + ')';
    }},

    { name: 'Blob',    label: 'Ethereal',
      pool: p => vibeHas(p, 'ethereal', 'dreamy', 'magical', 'mystical'),
      fn: (cx, cy, t, now) => {
        const r = t * 110;
        const pts = [];
        for (let i = 0; i < 12; i++) {
            const a = (i / 12) * Math.PI * 2;
            const wobble = 1 + Math.sin(a * 3 + (now || 0) * 0.004) * 0.18;
            pts.push((cx + r * wobble * Math.cos(a)).toFixed(1) + '% ' + (cy + r * wobble * Math.sin(a)).toFixed(1) + '%');
        }
        return 'polygon(' + pts.join(', ') + ')';
    }},
];

function initReveal() {
    const container = document.getElementById('view-reveal');
    container.innerHTML = '';

    revealIdx = 0;
    revealSetIdx = 0;
    revealAnimating = false;

    buildRevealSets();

    if (revealPhotos.length === 0) {
        container.innerHTML = '<div class="loading">No photos</div>';
        return;
    }

    renderRevealShell(container);
}

function buildRevealSets() {
    const all = APP.data.photos.filter(p => p.display);
    const usedIds = new Set();
    revealSets = [];
    revealPhotos = [];

    for (const def of REVEAL_DEFS) {
        const matches = all.filter(p => !usedIds.has(p.id) && def.pool(p));
        if (matches.length < 6) continue;

        const sorted = [...matches].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
        const sampled = shuffleArray(sorted.slice(0, REVEAL_PER_SET * 3)).slice(0, REVEAL_PER_SET);

        const startIdx = revealPhotos.length;
        for (const p of sampled) {
            revealPhotos.push(p);
            usedIds.add(p.id);
        }

        revealSets.push({
            name: def.name,
            label: def.label,
            fn: def.fn,
            startIdx: startIdx,
            endIdx: startIdx + sampled.length - 1,
        });
    }

    /* Fallback: add top aesthetics if too few */
    if (revealPhotos.length < 30) {
        const sorted = [...all].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
        const remaining = sorted.filter(p => !usedIds.has(p.id)).slice(0, 20);
        if (remaining.length > 0) {
            const startIdx = revealPhotos.length;
            revealPhotos.push(...shuffleArray(remaining));
            revealSets.push({
                name: 'Circle',
                label: 'Best',
                fn: REVEAL_DEFS[0].fn,
                startIdx: startIdx,
                endIdx: revealPhotos.length - 1,
            });
        }
    }
}

function renderRevealShell(container) {
    const shell = document.createElement('div');
    shell.className = 'reveal-shell';
    shell.id = 'reveal-shell';

    /* Current layer — always fully visible (z-index: 1) */
    const current = document.createElement('div');
    current.className = 'reveal-layer reveal-current';
    current.id = 'reveal-current';
    const imgCur = document.createElement('img');
    imgCur.className = 'reveal-img';
    imgCur.alt = '';
    loadProgressive(imgCur, revealPhotos[0], 'display');
    current.appendChild(imgCur);
    shell.appendChild(current);

    /* Incoming layer — on top (z-index: 2), hidden via clip-path */
    const incoming = document.createElement('div');
    incoming.className = 'reveal-layer reveal-incoming';
    incoming.id = 'reveal-incoming';
    incoming.style.clipPath = 'circle(0% at 50% 50%)';
    const imgInc = document.createElement('img');
    imgInc.className = 'reveal-img';
    imgInc.alt = '';
    incoming.appendChild(imgInc);
    shell.appendChild(incoming);

    /* Set label — top center, shows shape + theme */
    const label = document.createElement('div');
    label.className = 'reveal-label';
    label.id = 'reveal-label';
    shell.appendChild(label);

    /* Counter */
    const ctr = document.createElement('div');
    ctr.className = 'reveal-counter';
    ctr.id = 'reveal-counter';
    ctr.textContent = '1\u2009/\u2009' + revealPhotos.length;
    shell.appendChild(ctr);

    /* Hint */
    const hint = document.createElement('div');
    hint.className = 'reveal-hint';
    hint.id = 'reveal-hint';
    hint.textContent = 'Click anywhere';
    shell.appendChild(hint);

    /* Show initial set label */
    showRevealSetLabel();

    /* Click */
    shell.addEventListener('click', e => {
        const rect = shell.getBoundingClientRect();
        const cx = ((e.clientX - rect.left) / rect.width * 100);
        const cy = ((e.clientY - rect.top) / rect.height * 100);
        const dir = (e.clientX / window.innerWidth) < 0.3 ? -1 : 1;
        triggerReveal(dir, cx, cy);
    });

    /* Swipe */
    let tx = 0;
    shell.addEventListener('touchstart', e => { tx = e.touches[0].clientX; }, { passive: true });
    shell.addEventListener('touchend', e => {
        if (revealAnimating) return;
        const dx = e.changedTouches[0].clientX - tx;
        if (Math.abs(dx) > 50) triggerReveal(dx > 0 ? -1 : 1, 50, 50);
    }, { passive: true });

    /* Keyboard */
    document.removeEventListener('keydown', revealKeyHandler);
    document.addEventListener('keydown', revealKeyHandler);

    container.appendChild(shell);

    setTimeout(() => {
        const h = document.getElementById('reveal-hint');
        if (h) h.classList.add('faded');
    }, 3500);
}

function revealKeyHandler(e) {
    if (APP.currentView !== 'reveal') return;
    if (revealAnimating) return;
    if (e.key === 'ArrowRight') { e.preventDefault(); triggerReveal(1, 50, 50); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); triggerReveal(-1, 50, 50); }
}

function getCurrentRevealSet() {
    return revealSets.find(s => revealIdx >= s.startIdx && revealIdx <= s.endIdx) || revealSets[0];
}

function showRevealSetLabel() {
    const set = getCurrentRevealSet();
    if (!set) return;
    const el = document.getElementById('reveal-label');
    if (!el) return;
    el.innerHTML = '<span class="reveal-label-shape">' + set.name + '</span>' +
                   '<span class="reveal-label-sep">\u2009\u00B7\u2009</span>' +
                   '<span class="reveal-label-theme">' + set.label + '</span>';
    el.classList.remove('flash');
    void el.offsetWidth;
    el.classList.add('flash');
}

function triggerReveal(dir, cx, cy) {
    if (revealAnimating) return;
    revealAnimating = true;

    const hint = document.getElementById('reveal-hint');
    if (hint) hint.classList.add('faded');

    const nextIdx = (revealIdx + dir + revealPhotos.length) % revealPhotos.length;
    const nextPhoto = revealPhotos[nextIdx];

    /* Determine which shape to use based on which set the NEXT photo is in */
    const oldSet = getCurrentRevealSet();
    revealIdx = nextIdx;
    const newSet = getCurrentRevealSet();
    const shapeFn = (newSet || oldSet).fn;

    /* Show set label if entering new set */
    if (newSet !== oldSet) {
        showRevealSetLabel();
    }

    const incoming = document.getElementById('reveal-incoming');
    const current = document.getElementById('reveal-current');
    const incomingImg = incoming.querySelector('img');
    const currentImg = current.querySelector('img');

    const preload = new Image();
    preload.onload = () => {
        incomingImg.src = nextPhoto.display || nextPhoto.thumb;

        animateRevealClip(incoming, shapeFn, cx, cy, () => {
            currentImg.src = incomingImg.src;
            incoming.style.clipPath = 'circle(0% at 50% 50%)';
            revealAnimating = false;

            const ctr = document.getElementById('reveal-counter');
            if (ctr) {
                const set = getCurrentRevealSet();
                if (set) {
                    const within = revealIdx - set.startIdx + 1;
                    const total = set.endIdx - set.startIdx + 1;
                    ctr.textContent = within + '\u2009/\u2009' + total;
                }
            }
        });
    };
    preload.onerror = () => { revealAnimating = false; };
    preload.src = nextPhoto.display || nextPhoto.thumb;
}

function animateRevealClip(layer, shapeFn, cx, cy, onComplete) {
    const start = performance.now();

    function frame(now) {
        if (APP.currentView !== 'reveal') { revealAnimating = false; return; }

        const elapsed = now - start;
        const t = Math.min(elapsed / REVEAL_DURATION, 1);
        const e = 1 - Math.pow(1 - t, 3);

        layer.style.clipPath = shapeFn(cx, cy, e, now);

        if (t < 1) {
            requestAnimationFrame(frame);
        } else {
            layer.style.clipPath = 'none';
            if (onComplete) onComplete();
        }
    }

    requestAnimationFrame(frame);
}
