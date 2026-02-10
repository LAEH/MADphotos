/* faces.js — Les Visages: Face crops filling viewport, no scroll.
   Dynamic cell sizing fills the container. Different density per filter. */

const _rootStyle = getComputedStyle(document.documentElement);
function emoColor(emotion) {
    return _rootStyle.getPropertyValue('--emo-' + emotion).trim()
        || _rootStyle.getPropertyValue('--system-gray-2').trim()
        || 'rgb(99, 99, 102)';
}

let facesFilter = 'all';
let facesData = {};

function initFaces() {
    const container = document.getElementById('view-faces');
    container.innerHTML = '<div class="loading">Loading face data</div>';
    loadFaces().then(() => renderFacesView(container));
}

function renderFacesView(container) {
    container.innerHTML = '';

    facesData = {};
    for (const [uuid, faceList] of Object.entries(APP.faces)) {
        const photo = APP.photoMap[uuid];
        if (!photo || !photo.thumb) continue;
        for (const face of faceList) {
            /* Skip low-confidence or tiny faces (noise) */
            if ((face.conf || 0) < 0.75) continue;
            if ((face.w || 0) * (face.h || 0) < 0.005) continue;
            const emo = face.emo || 'neutral';
            if (!facesData[emo]) facesData[emo] = [];
            facesData[emo].push({ photo, face });
        }
    }

    const wrap = document.createElement('div');
    wrap.className = 'faces-container';

    /* Filter bar */
    const filterBar = document.createElement('div');
    filterBar.className = 'faces-filter-bar';
    filterBar.id = 'faces-filter-bar';

    const filters = [
        { id: 'all',      label: 'All' },
        { id: 'happy',    label: '\uD83D\uDE04' },
        { id: 'sad',      label: '\uD83D\uDE22' },
        { id: 'angry',    label: '\uD83D\uDE21' },
        { id: 'fear',     label: '\uD83D\uDE28' },
        { id: 'surprise', label: '\uD83D\uDE32' },
        { id: 'neutral',  label: '\uD83D\uDE10' },
    ];

    for (const f of filters) {
        const btn = document.createElement('button');
        btn.className = 'faces-filter-btn' + (f.id === 'all' ? ' active' : '');
        btn.dataset.emotion = f.id;
        btn.textContent = f.label;

        const count = f.id === 'all'
            ? Object.values(facesData).reduce((sum, arr) => sum + arr.length, 0)
            : (facesData[f.id] || []).length;
        if (count > 0) {
            const badge = document.createElement('span');
            badge.className = 'faces-filter-count';
            badge.textContent = count;
            btn.appendChild(badge);
        }

        btn.addEventListener('click', () => {
            facesFilter = f.id;
            document.querySelectorAll('.faces-filter-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.emotion === f.id);
            });
            renderFacesGrid();
        });
        filterBar.appendChild(btn);
    }

    wrap.appendChild(filterBar);

    /* Container for face cards — no scroll */
    const card = document.createElement('div');
    card.className = 'faces-card';
    card.id = 'faces-card';
    wrap.appendChild(card);

    container.appendChild(wrap);
    facesFilter = 'all';
    renderFacesGrid();
}

function renderFacesGrid() {
    const card = document.getElementById('faces-card');
    if (!card) return;
    card.innerHTML = '';

    let faces;
    if (facesFilter === 'all') {
        faces = [];
        for (const emo of Object.keys(facesData)) {
            faces.push(...facesData[emo]);
        }
    } else {
        faces = facesData[facesFilter] || [];
    }

    if (faces.length === 0) {
        card.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:14px">No faces found</div>';
        return;
    }

    /* Double rAF ensures layout has fully settled after view activation */
    requestAnimationFrame(() => requestAnimationFrame(() => {
        const shuffled = shuffleArray([...faces]);
        const gap = 2;
        const pad = 12;
        const rect = card.getBoundingClientRect();
        const w = rect.width - pad * 2;
        const h = rect.height - pad * 2;
        if (w <= 0 || h <= 0) return;

        const mobile = window.matchMedia('(max-width: 768px)').matches;
        const MIN_SIZE = mobile ? 40 : 8;
        const MAX_SIZE = mobile ? 64 : 96;
        const n = shuffled.length;

        /* Binary search for largest cell size that fits ALL n faces */
        let lo = MIN_SIZE, hi = MAX_SIZE;
        while (hi - lo > 0.5) {
            const mid = (lo + hi) / 2;
            const cols = Math.floor((w + gap) / (mid + gap));
            if (cols < 1) { hi = mid; continue; }
            const rows = Math.ceil(n / cols);
            const totalH = rows * (mid + gap) - gap;
            if (totalH <= h) lo = mid;
            else hi = mid;
        }

        const cellSize = Math.floor(lo);
        const cols = Math.floor((w + gap) / (cellSize + gap));
        const usableRows = Math.floor((h + gap) / (cellSize + gap));
        const show = Math.min(n, cols * usableRows);
        const toShow = shuffled.slice(0, show);

        card.style.setProperty('--face-size', cellSize + 'px');

        const canvasRes = Math.min(Math.round(cellSize * (window.devicePixelRatio || 1)), 200);

        for (const { photo, face } of toShow) {
            const faceEl = document.createElement('div');
            faceEl.className = 'face-card';
            const emo = face.emo || 'neutral';
            if (cellSize >= 20) {
                faceEl.style.borderColor = emoColor(emo);
            } else {
                faceEl.style.border = 'none';
            }

            const canvas = document.createElement('canvas');
            canvas.className = 'face-crop-canvas face-crop-loading';
            canvas.width = canvasRes;
            canvas.height = canvasRes;
            canvas.dataset.thumb = photo.thumb;
            canvas.dataset.fx = face.x || 0;
            canvas.dataset.fy = face.y || 0;
            canvas.dataset.fw = face.w || 0.1;
            canvas.dataset.fh = face.h || 0.1;
            canvas.dataset.photoId = photo.id;

            faceCropObserver.observe(canvas);
            faceEl.appendChild(canvas);

            faceEl.addEventListener('click', () => openLightbox(photo));
            card.appendChild(faceEl);
        }
    }));
}

/* Image cache — avoids re-loading the same thumbnail for multiple faces */
const _faceImgCache = {};
const _FACE_CACHE_MAX = 200;
const _faceImgCacheKeys = [];

function cropFaceToCanvas(canvas, img) {
    const fx = parseFloat(canvas.dataset.fx);
    const fy = parseFloat(canvas.dataset.fy);
    const fw = parseFloat(canvas.dataset.fw);
    const fh = parseFloat(canvas.dataset.fh);

    const iw = img.naturalWidth;
    const ih = img.naturalHeight;

    let cx = fx * iw;
    let cy = fy * ih;
    let cw = fw * iw;
    let ch = fh * ih;

    /* Padding around face (40%) */
    const padX = cw * 0.4;
    const padY = ch * 0.4;
    cx = Math.max(0, cx - padX);
    cy = Math.max(0, cy - padY);
    cw = Math.min(iw - cx, cw + padX * 2);
    ch = Math.min(ih - cy, ch + padY * 2);

    /* Make square — clamp position so the crop stays fully inside the image */
    let size = Math.max(cw, ch);
    size = Math.min(size, iw, ih); /* can't exceed image dimensions */
    const centerX = cx + cw / 2;
    const centerY = cy + ch / 2;
    cx = Math.max(0, Math.min(centerX - size / 2, iw - size));
    cy = Math.max(0, Math.min(centerY - size / 2, ih - size));

    const drawSize = canvas.width;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, cx, cy, size, size, 0, 0, drawSize, drawSize);

    canvas.classList.remove('face-crop-loading');
    canvas.classList.add('face-crop-loaded');
}

/* Batch queue for staggered loading — prevents browser overload with 3000+ faces */
let _faceBatchQueue = [];
let _faceBatchRunning = false;

function enqueueFaceCrop(canvas) {
    _faceBatchQueue.push(canvas);
    if (!_faceBatchRunning) processFaceBatch();
}

function processFaceBatch() {
    _faceBatchRunning = true;
    const BATCH = 30;
    const batch = _faceBatchQueue.splice(0, BATCH);
    if (batch.length === 0) { _faceBatchRunning = false; return; }

    for (const canvas of batch) {
        const src = canvas.dataset.thumb;
        if (!src) continue;

        if (_faceImgCache[src]) {
            const cached = _faceImgCache[src];
            if (cached.complete && cached.naturalWidth > 0) {
                cropFaceToCanvas(canvas, cached);
            } else {
                cached.addEventListener('load', () => cropFaceToCanvas(canvas, cached), { once: true });
            }
            continue;
        }

        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.decoding = 'async';
        _faceImgCache[src] = img;
        _faceImgCacheKeys.push(src);
        if (_faceImgCacheKeys.length > _FACE_CACHE_MAX) {
            const old = _faceImgCacheKeys.shift();
            delete _faceImgCache[old];
        }
        img.onload = () => cropFaceToCanvas(canvas, img);
        img.onerror = () => {
            canvas.classList.remove('face-crop-loading');
            canvas.classList.add('face-crop-loaded');
        };
        img.src = src;
    }

    /* Next batch after a frame to avoid blocking paint */
    requestAnimationFrame(() => {
        if (_faceBatchQueue.length > 0) processFaceBatch();
        else _faceBatchRunning = false;
    });
}

/* Lazy observer for face crop canvases */
const faceCropObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const canvas = entry.target;
        faceCropObserver.unobserve(canvas);
        enqueueFaceCrop(canvas);
    }
}, { rootMargin: '400px' });
