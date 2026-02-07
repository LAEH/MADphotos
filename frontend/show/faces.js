/* faces.js — Les Visages: Face crops in elevated container with emotion filters.
   Viewport-fixed layout. No page scroll. */

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

    /* Build faces data grouped by emotion */
    facesData = {};
    for (const [uuid, faceList] of Object.entries(APP.faces)) {
        const photo = APP.photoMap[uuid];
        if (!photo || !photo.thumb) continue;
        for (const face of faceList) {
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
        { id: 'happy',    label: 'Happy' },
        { id: 'sad',      label: 'Sad' },
        { id: 'angry',    label: 'Angry' },
        { id: 'fear',     label: 'Fear' },
        { id: 'surprise', label: 'Surprise' },
        { id: 'neutral',  label: 'Neutral' },
    ];

    for (const f of filters) {
        const btn = document.createElement('button');
        btn.className = 'faces-filter-btn' + (f.id === 'all' ? ' active' : '');
        btn.dataset.emotion = f.id;
        btn.textContent = f.label;

        /* Count badge */
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

    /* Elevated card container */
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

    const shuffled = shuffleArray([...faces]);

    for (const { photo, face } of shuffled) {
        const faceEl = document.createElement('div');
        faceEl.className = 'face-card';
        const emo = face.emo || 'neutral';
        faceEl.style.borderColor = emoColor(emo);

        const canvas = document.createElement('canvas');
        canvas.className = 'face-crop-canvas face-crop-loading';
        canvas.width = 120;
        canvas.height = 120;
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
}

/* Lazy observer for face crop canvases */
const faceCropObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const canvas = entry.target;
        faceCropObserver.unobserve(canvas);

        const img = new Image();
        img.crossOrigin = 'anonymous';
        img.decoding = 'async';
        img.onload = () => {
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

            /* Make square */
            const size = Math.max(cw, ch);
            const centerX = cx + cw / 2;
            const centerY = cy + ch / 2;
            cx = Math.max(0, centerX - size / 2);
            cy = Math.max(0, centerY - size / 2);
            cw = Math.min(iw - cx, size);
            ch = Math.min(ih - cy, size);

            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, cx, cy, cw, ch, 0, 0, 120, 120);

            canvas.classList.remove('face-crop-loading');
            canvas.classList.add('face-crop-loaded');
        };
        img.onerror = () => {
            canvas.classList.remove('face-crop-loading');
            canvas.classList.add('face-crop-loaded');
        };
        img.src = canvas.dataset.thumb;
    }
}, { rootMargin: '400px' });
