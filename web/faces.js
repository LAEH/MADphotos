/* faces.js — Les Visages: Face crops + emotions */

let facesInitialized = false;

const EMOTION_COLORS = {
    happy: '#34C759',
    sad: '#5AC8FA',
    angry: '#FF3B30',
    surprise: '#FF9500',
    fear: '#AF52DE',
    disgust: '#8E8E93',
    neutral: '#636366',
    contempt: '#FF2D55',
};

function initFaces() {
    if (facesInitialized) return;
    facesInitialized = true;

    const container = document.getElementById('view-faces');
    container.innerHTML = '<div class="loading">Loading face data</div>';

    loadFaces().then(() => {
        renderFaces(container);
    });
}

function renderFaces(container) {
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'faces-container';

    // Mood meter
    const moodBar = document.createElement('div');
    moodBar.className = 'faces-mood-bar';

    const emotionCounts = {};
    let totalFaces = 0;

    for (const [uuid, faceList] of Object.entries(APP.faces)) {
        for (const face of faceList) {
            totalFaces++;
            const emo = face.emo || 'neutral';
            emotionCounts[emo] = (emotionCounts[emo] || 0) + 1;
        }
    }

    const sorted = Object.entries(emotionCounts).sort((a, b) => b[1] - a[1]);
    for (const [emo, count] of sorted) {
        const pct = (count / totalFaces * 100).toFixed(1);
        const seg = document.createElement('div');
        seg.className = 'faces-mood-segment';
        seg.style.flex = count;
        seg.style.background = EMOTION_COLORS[emo] || '#636366';
        seg.title = `${titleCase(emo)}: ${count} (${pct}%)`;

        const label = document.createElement('span');
        label.className = 'faces-mood-label';
        label.textContent = titleCase(emo);
        seg.appendChild(label);

        moodBar.appendChild(seg);
    }
    wrap.appendChild(moodBar);

    // Filter buttons
    const filters = document.createElement('div');
    filters.className = 'faces-filters';

    const allBtn = document.createElement('button');
    allBtn.className = 'glass-tag active';
    allBtn.textContent = `All (${totalFaces})`;
    allBtn.addEventListener('click', () => {
        filters.querySelectorAll('.glass-tag').forEach(b => b.classList.remove('active'));
        allBtn.classList.add('active');
        renderFaceGrid(grid, null);
    });
    filters.appendChild(allBtn);

    for (const [emo, count] of sorted) {
        const btn = document.createElement('button');
        btn.className = 'glass-tag';
        btn.style.borderLeft = '3px solid ' + (EMOTION_COLORS[emo] || '#636366');
        btn.textContent = `${titleCase(emo)} (${count})`;
        btn.addEventListener('click', () => {
            filters.querySelectorAll('.glass-tag').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderFaceGrid(grid, emo);
        });
        filters.appendChild(btn);
    }
    wrap.appendChild(filters);

    // Face grid
    const grid = document.createElement('div');
    grid.className = 'faces-grid';
    grid.id = 'faces-grid';
    wrap.appendChild(grid);

    container.appendChild(wrap);
    renderFaceGrid(grid, null);
}

function renderFaceGrid(grid, emotionFilter) {
    grid.innerHTML = '';

    for (const [uuid, faceList] of Object.entries(APP.faces)) {
        const photo = APP.photoMap[uuid];
        if (!photo || !photo.thumb) continue;

        for (const face of faceList) {
            const emo = face.emo || 'neutral';
            if (emotionFilter && emo !== emotionFilter) continue;

            const card = document.createElement('div');
            card.className = 'face-card';
            card.style.borderColor = EMOTION_COLORS[emo] || '#636366';

            // Use the full thumbnail but crop to face area via CSS
            const imgWrap = document.createElement('div');
            imgWrap.className = 'face-crop';

            const img = document.createElement('img');
            img.src = photo.thumb;
            img.alt = '';

            // Position image to show face region
            // face.x, face.y are normalized (0-1) positions of face box
            const fx = face.x || 0, fy = face.y || 0;
            const fw = face.w || 0.1, fh = face.h || 0.1;
            const cx = (fx + fw / 2) * 100;
            const cy = (fy + fh / 2) * 100;
            img.style.objectPosition = `${cx}% ${cy}%`;

            imgWrap.appendChild(img);
            card.appendChild(imgWrap);

            const label = document.createElement('div');
            label.className = 'face-label';
            label.textContent = titleCase(emo);
            label.style.color = EMOTION_COLORS[emo] || '#636366';
            card.appendChild(label);

            card.addEventListener('click', () => openLightbox(photo));
            grid.appendChild(card);
        }
    }
}
