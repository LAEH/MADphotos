/* drift.js — La Dérive: Abstract visual drift through DINOv2 embeddings.
   Two completely different images that share something you can't name —
   a shape, a rhythm, a structure. A bridge matches a ribcage.
   A shoe matches a skateboard ramp. Same geometry, different worlds. */

let deriveHistory = [];
let deriveCurrentId = null;

async function initDerive() {
    await loadDriftNeighbors();

    const container = document.getElementById('view-derive');
    container.innerHTML = '';

    const inner = document.createElement('div');
    inner.className = 'drift-container';
    inner.id = 'derive-inner';
    container.appendChild(inner);

    // Pick a random starting photo that has drift neighbors
    const photos = APP.data.photos.filter(p => p.thumb && APP.driftNeighbors[p.id]);
    if (photos.length === 0) return;
    const start = randomFrom(photos);
    navigateDerive(start.id);
}

function navigateDerive(photoId) {
    const photo = APP.photoMap[photoId];
    if (!photo) return;

    if (deriveCurrentId && deriveCurrentId !== photoId) {
        const existingIdx = deriveHistory.indexOf(photoId);
        if (existingIdx >= 0) {
            deriveHistory = deriveHistory.slice(0, existingIdx);
        }
        deriveHistory.push(deriveCurrentId);
    }
    deriveCurrentId = photoId;
    renderDerive(photo);
}

function renderDerive(photo) {
    const container = document.getElementById('derive-inner');
    container.innerHTML = '';

    // Controls bar
    const controls = document.createElement('div');
    controls.className = 'drift-controls';

    const randomBtn = document.createElement('button');
    randomBtn.className = 'drift-btn';
    randomBtn.textContent = 'random';
    randomBtn.addEventListener('click', () => {
        const photos = APP.data.photos.filter(p => p.thumb && APP.driftNeighbors[p.id]);
        navigateDerive(randomFrom(photos).id);
    });
    controls.appendChild(randomBtn);

    if (deriveHistory.length > 0) {
        const backBtn = document.createElement('button');
        backBtn.className = 'drift-btn';
        backBtn.textContent = 'back';
        backBtn.addEventListener('click', () => {
            const prevId = deriveHistory.pop();
            if (prevId) {
                deriveCurrentId = prevId;
                renderDerive(APP.photoMap[prevId]);
            }
        });
        controls.appendChild(backBtn);
    }

    // Breadcrumb trail
    if (deriveHistory.length > 0) {
        const breadcrumb = document.createElement('div');
        breadcrumb.className = 'drift-breadcrumb';
        const trail = deriveHistory.slice(-8);

        for (let i = 0; i < trail.length; i++) {
            const bPhoto = APP.photoMap[trail[i]];
            if (!bPhoto) continue;
            const crumb = document.createElement('div');
            crumb.className = 'drift-breadcrumb-item';
            const cImg = document.createElement('img');
            cImg.src = bPhoto.micro || bPhoto.thumb;
            cImg.alt = '';
            crumb.appendChild(cImg);
            crumb.addEventListener('click', () => {
                const idx = deriveHistory.indexOf(trail[i]);
                if (idx >= 0) {
                    deriveHistory = deriveHistory.slice(0, idx);
                    deriveCurrentId = trail[i];
                    renderDerive(APP.photoMap[trail[i]]);
                }
            });
            breadcrumb.appendChild(crumb);
            if (i < trail.length - 1) {
                const arrow = document.createElement('span');
                arrow.className = 'drift-breadcrumb-arrow';
                arrow.textContent = '\u203a';
                breadcrumb.appendChild(arrow);
            }
        }
        const arrow = document.createElement('span');
        arrow.className = 'drift-breadcrumb-arrow';
        arrow.textContent = '\u203a';
        breadcrumb.appendChild(arrow);
        const cur = document.createElement('div');
        cur.className = 'drift-breadcrumb-item current';
        const curImg = document.createElement('img');
        curImg.src = photo.micro || photo.thumb;
        curImg.alt = '';
        cur.appendChild(curImg);
        breadcrumb.appendChild(cur);
        controls.appendChild(breadcrumb);
    }

    container.appendChild(controls);

    // Center image — large and dramatic, structure speaks
    const center = document.createElement('div');
    center.className = 'drift-center';

    const img = document.createElement('img');
    loadProgressive(img, photo, 'display');
    img.alt = photo.alt || photo.caption || '';
    img.addEventListener('click', () => openLightbox(photo));
    img.className = 'clickable-img';
    center.appendChild(img);

    // Minimal metadata — just a whisper of context
    if (photo.caption || photo.alt) {
        const cap = document.createElement('p');
        cap.className = 'drift-center-alt';
        cap.textContent = photo.caption || photo.alt;
        center.appendChild(cap);
    }

    container.appendChild(center);

    // DINOv2 structural neighbors — the magic
    const neighborData = APP.driftNeighbors[photo.id] || [];
    const neighbors = [];
    for (const n of neighborData) {
        const nPhoto = APP.photoMap[n.uuid];
        if (nPhoto && nPhoto.thumb) {
            neighbors.push({ photo: nPhoto, score: n.score });
        }
        if (neighbors.length >= 6) break;
    }

    if (neighbors.length > 0) {
        const neighborsGrid = document.createElement('div');
        neighborsGrid.className = 'drift-neighbors';

        for (const { photo: nPhoto, score } of neighbors) {
            const card = document.createElement('div');
            card.className = 'drift-neighbor';

            const nImg = createLazyImg(nPhoto, 'thumb');
            lazyObserver.observe(nImg);
            card.appendChild(nImg);

            // Subtle similarity score indicator
            const scoreBar = document.createElement('div');
            scoreBar.className = 'drift-score';
            scoreBar.style.width = Math.round(score * 100) + '%';
            card.appendChild(scoreBar);

            card.addEventListener('click', () => navigateDerive(nPhoto.id));
            neighborsGrid.appendChild(card);
        }

        container.appendChild(neighborsGrid);
    }

    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
