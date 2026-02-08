/* cinema.js — Cinema: Full-screen immersive slideshow with Ken Burns effect.
   Each photograph fills the entire viewport edge-to-edge. Slow zoom+pan drift.
   Cinematic crossfade between images. Auto-advances every 7 seconds.
   Themed chapters with smart diversity sampling — each chapter shows a
   curated set of 12 images with a brief title card between transitions.
   Click right = next, click left = prev, space = pause/play. */

let cinemaPhotos = [];
let cinemaChapters = [];
let cinemaIdx = 0;
let cinemaTimer = null;
let cinemaPaused = false;
let cinemaActiveLayer = 'a';

const CINEMA_INTERVAL = 7000;
const CINEMA_PER_CHAPTER = 12;
const KB_CLASSES = ['kb-1', 'kb-2', 'kb-3', 'kb-4', 'kb-5', 'kb-6'];

/* Chapter definitions — curated themes with filter predicates */
const CINEMA_CHAPTERS = [
    { label: 'Golden Hour',  pool: p => p.time === 'golden hour' },
    { label: 'Serene',       pool: p => vibeHas(p, 'serene', 'calm', 'peaceful', 'tranquil') },
    { label: 'Intense',      pool: p => vibeHas(p, 'dramatic', 'intense', 'powerful', 'bold') },
    { label: 'Night',        pool: p => p.time === 'night' || p.time === 'blue hour' },
    { label: 'Portraits',    pool: p => objHas(p, 'person') && p.style === 'portrait' },
    { label: 'Nature',       pool: p => p.scene && /forest|garden|field|mountain|park|lake|beach/.test(p.scene) },
    { label: 'Urban',        pool: p => p.scene && /street|city|urban|building|downtown|market/.test(p.scene) },
    { label: 'Nostalgic',    pool: p => vibeHas(p, 'nostalgic', 'vintage', 'retro', 'timeless') },
    { label: 'Ethereal',     pool: p => vibeHas(p, 'ethereal', 'dreamy', 'magical', 'mystical') },
    { label: 'Dark',         pool: p => vibeHas(p, 'dark', 'moody', 'somber', 'melancholic') },
    { label: 'Vibrant',      pool: p => vibeHas(p, 'vibrant', 'lively', 'energetic', 'joyful') },
];

function initCinema() {
    const container = document.getElementById('view-cinema');
    container.innerHTML = '';

    cinemaIdx = 0;
    cinemaPaused = false;
    cinemaActiveLayer = 'a';
    if (cinemaTimer) { clearInterval(cinemaTimer); cinemaTimer = null; }

    /* Build chapters with diversity sampling */
    buildCinemaChapters();

    if (cinemaPhotos.length === 0) {
        container.innerHTML = '<div class="loading">No photos</div>';
        return;
    }

    renderCinemaShell(container);
    showCinemaChapterLabel(0);
    loadCinemaSlide(cinemaPhotos[0], 'a', true);
    startCinemaAuto();
}

function buildCinemaChapters() {
    const all = APP.data.photos.filter(p => p.display);
    const usedIds = new Set();
    cinemaChapters = [];
    cinemaPhotos = [];

    for (const ch of CINEMA_CHAPTERS) {
        const matches = all.filter(p => !usedIds.has(p.id) && ch.pool(p));
        if (matches.length < 6) continue;

        /* Diversity sample: top by aesthetic, then shuffle */
        const sorted = [...matches].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
        const sampled = shuffleArray(sorted.slice(0, CINEMA_PER_CHAPTER * 3)).slice(0, CINEMA_PER_CHAPTER);

        const startIdx = cinemaPhotos.length;
        for (const p of sampled) {
            cinemaPhotos.push(p);
            usedIds.add(p.id);
        }

        cinemaChapters.push({
            label: ch.label,
            startIdx: startIdx,
            endIdx: startIdx + sampled.length - 1,
        });

        if (cinemaChapters.length >= 8) break;
    }

    /* If somehow too few, add top aesthetics as "Masterpieces" */
    if (cinemaPhotos.length < 20) {
        const sorted = [...all].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
        const remaining = sorted.filter(p => !usedIds.has(p.id)).slice(0, 24);
        if (remaining.length > 0) {
            const startIdx = cinemaPhotos.length;
            cinemaPhotos.push(...shuffleArray(remaining));
            cinemaChapters.push({
                label: 'Masterpieces',
                startIdx: startIdx,
                endIdx: cinemaPhotos.length - 1,
            });
        }
    }
}

function renderCinemaShell(container) {
    const shell = document.createElement('div');
    shell.className = 'cinema-shell';
    shell.id = 'cinema-shell';

    /* Two full-screen layers for crossfade */
    for (const id of ['a', 'b']) {
        const layer = document.createElement('div');
        layer.className = 'cinema-layer';
        layer.id = 'cinema-layer-' + id;
        const img = document.createElement('img');
        img.className = 'cinema-img';
        img.alt = '';
        layer.appendChild(img);
        shell.appendChild(layer);
    }

    /* Chapter title overlay */
    const chapter = document.createElement('div');
    chapter.className = 'cinema-chapter';
    chapter.id = 'cinema-chapter';
    shell.appendChild(chapter);

    /* Progress bar — thin line at bottom */
    const prog = document.createElement('div');
    prog.className = 'cinema-progress';
    const fill = document.createElement('div');
    fill.className = 'cinema-progress-fill';
    fill.id = 'cinema-progress-fill';
    prog.appendChild(fill);
    shell.appendChild(prog);

    /* Counter — bottom right */
    const ctr = document.createElement('div');
    ctr.className = 'cinema-counter';
    ctr.id = 'cinema-counter';
    shell.appendChild(ctr);

    /* Pause flash indicator */
    const pause = document.createElement('div');
    pause.className = 'cinema-pause';
    pause.id = 'cinema-pause';
    shell.appendChild(pause);

    /* Click: left 30% = prev, right 70% = next */
    shell.addEventListener('click', e => {
        const x = e.clientX / window.innerWidth;
        if (x < 0.3) cinemaPrev(); else cinemaNext();
    });

    /* Touch swipe */
    let tx = 0;
    shell.addEventListener('touchstart', e => { tx = e.touches[0].clientX; }, { passive: true });
    shell.addEventListener('touchend', e => {
        const dx = e.changedTouches[0].clientX - tx;
        if (Math.abs(dx) > 50) { dx > 0 ? cinemaPrev() : cinemaNext(); }
    }, { passive: true });

    /* Keyboard */
    document.removeEventListener('keydown', cinemaKeyHandler);
    document.addEventListener('keydown', cinemaKeyHandler);

    container.appendChild(shell);
}

function cinemaKeyHandler(e) {
    if (APP.currentView !== 'cinema') return;
    if (e.key === 'ArrowRight') { e.preventDefault(); cinemaNext(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); cinemaPrev(); }
    else if (e.key === ' ') { e.preventDefault(); toggleCinemaPause(); }
}

function showCinemaChapterLabel(photoIdx) {
    const chapter = cinemaChapters.find(c => photoIdx >= c.startIdx && photoIdx <= c.endIdx);
    if (!chapter) return;
    if (photoIdx !== chapter.startIdx) return; /* only on first photo of chapter */

    const el = document.getElementById('cinema-chapter');
    if (!el) return;
    el.textContent = chapter.label;
    el.classList.remove('visible');
    void el.offsetWidth;
    el.classList.add('visible');

    /* Fade out after 2.5s */
    setTimeout(() => {
        if (el) el.classList.remove('visible');
    }, 2500);
}

function loadCinemaSlide(photo, layerId, immediate) {
    const layer = document.getElementById('cinema-layer-' + layerId);
    if (!layer) return;
    const img = layer.querySelector('.cinema-img');

    /* Remove old KB class */
    KB_CLASSES.forEach(c => layer.classList.remove(c));

    const pre = new Image();
    pre.onload = () => {
        img.src = photo.display || photo.thumb;

        /* Assign random Ken Burns drift */
        const kb = KB_CLASSES[Math.floor(Math.random() * KB_CLASSES.length)];
        layer.classList.add(kb);

        if (immediate) {
            layer.classList.add('active');
        } else {
            requestAnimationFrame(() => {
                layer.classList.add('active');
                const other = layerId === 'a' ? 'b' : 'a';
                document.getElementById('cinema-layer-' + other).classList.remove('active');
            });
        }
    };
    pre.src = photo.display || photo.thumb;

    /* Update counter — show chapter context */
    const ctr = document.getElementById('cinema-counter');
    if (ctr) {
        const chapter = cinemaChapters.find(c => cinemaIdx >= c.startIdx && cinemaIdx <= c.endIdx);
        if (chapter) {
            const withinChapter = cinemaIdx - chapter.startIdx + 1;
            const chapterSize = chapter.endIdx - chapter.startIdx + 1;
            ctr.textContent = withinChapter + '\u2009/\u2009' + chapterSize;
        } else {
            ctr.textContent = (cinemaIdx + 1) + '\u2009/\u2009' + cinemaPhotos.length;
        }
    }

    /* Reset progress bar */
    const fill = document.getElementById('cinema-progress-fill');
    if (fill) {
        fill.style.transition = 'none';
        fill.style.width = '0%';
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                fill.style.transition = 'width ' + CINEMA_INTERVAL + 'ms linear';
                fill.style.width = '100%';
            });
        });
    }
}

function cinemaAdvance(dir) {
    cinemaIdx = (cinemaIdx + dir + cinemaPhotos.length) % cinemaPhotos.length;
    cinemaActiveLayer = cinemaActiveLayer === 'a' ? 'b' : 'a';

    /* Show chapter label if entering a new chapter */
    showCinemaChapterLabel(cinemaIdx);

    loadCinemaSlide(cinemaPhotos[cinemaIdx], cinemaActiveLayer, false);
}

function cinemaNext() {
    clearCinemaAuto();
    cinemaAdvance(1);
    if (!cinemaPaused) startCinemaAuto();
}

function cinemaPrev() {
    clearCinemaAuto();
    cinemaAdvance(-1);
    if (!cinemaPaused) startCinemaAuto();
}

function toggleCinemaPause() {
    cinemaPaused = !cinemaPaused;
    const el = document.getElementById('cinema-pause');
    if (el) {
        el.textContent = cinemaPaused ? '\u25B6' : '\u275A\u275A';
        el.classList.remove('flash');
        void el.offsetWidth;
        el.classList.add('flash');
    }

    if (cinemaPaused) {
        clearCinemaAuto();
        const fill = document.getElementById('cinema-progress-fill');
        if (fill) {
            const w = fill.getBoundingClientRect().width;
            const pw = fill.parentElement.getBoundingClientRect().width;
            fill.style.transition = 'none';
            fill.style.width = (pw > 0 ? (w / pw * 100) : 0) + '%';
        }
    } else {
        const fill = document.getElementById('cinema-progress-fill');
        if (fill) {
            const cur = parseFloat(fill.style.width) || 0;
            const rem = CINEMA_INTERVAL * (1 - cur / 100);
            fill.style.transition = 'width ' + rem + 'ms linear';
            fill.style.width = '100%';
        }
        startCinemaAuto();
    }
}

function startCinemaAuto() {
    clearCinemaAuto();
    cinemaTimer = registerTimer(setInterval(() => {
        if (!cinemaPaused && APP.currentView === 'cinema') cinemaAdvance(1);
    }, CINEMA_INTERVAL));
}

function clearCinemaAuto() {
    if (cinemaTimer) { clearInterval(cinemaTimer); cinemaTimer = null; }
}
