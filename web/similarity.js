/* similarity.js — La Similarit\u00e9: Navigate semantically connected photographs */

let similarityHistory = [];
let similarityCurrentId = null;

function initSimilarity() {

    const container = document.getElementById('view-similarity');
    container.innerHTML = '';

    const el = document.createElement('div');
    el.className = 'drift-container';
    el.id = 'similarity-inner';
    container.appendChild(el);

    const photos = APP.data.photos;
    const startIdx = Math.floor(Math.random() * photos.length);
    navigateSimilarity(photos[startIdx].id);
}

function navigateSimilarity(photoId) {
    const photo = APP.photoMap[photoId];
    if (!photo) return;

    if (similarityCurrentId && similarityCurrentId !== photoId) {
        const existingIdx = similarityHistory.indexOf(photoId);
        if (existingIdx >= 0) {
            similarityHistory = similarityHistory.slice(0, existingIdx);
        }
        similarityHistory.push(similarityCurrentId);
    }
    similarityCurrentId = photoId;
    renderSimilarity(photo);
}

function renderSimilarity(photo) {
    const container = document.getElementById('similarity-inner');
    container.innerHTML = '';

    // Controls
    const controls = document.createElement('div');
    controls.className = 'drift-controls';

    const randomBtn = document.createElement('button');
    randomBtn.className = 'drift-btn';
    randomBtn.textContent = 'random';
    randomBtn.addEventListener('click', () => {
        const photos = APP.data.photos;
        const idx = Math.floor(Math.random() * photos.length);
        navigateSimilarity(photos[idx].id);
    });
    controls.appendChild(randomBtn);

    if (similarityHistory.length > 0) {
        const backBtn = document.createElement('button');
        backBtn.className = 'drift-btn';
        backBtn.textContent = 'back';
        backBtn.addEventListener('click', () => {
            const prevId = similarityHistory.pop();
            if (prevId) {
                similarityCurrentId = prevId;
                renderSimilarity(APP.photoMap[prevId]);
            }
        });
        controls.appendChild(backBtn);
    }

    // Breadcrumb trail
    if (similarityHistory.length > 0) {
        const breadcrumb = document.createElement('div');
        breadcrumb.className = 'drift-breadcrumb';
        const trail = similarityHistory.slice(-8);

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
                const idx = similarityHistory.indexOf(trail[i]);
                if (idx >= 0) {
                    similarityHistory = similarityHistory.slice(0, idx);
                    similarityCurrentId = trail[i];
                    renderSimilarity(APP.photoMap[trail[i]]);
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

        const currentCrumb = document.createElement('div');
        currentCrumb.className = 'drift-breadcrumb-item current';
        const curImg = document.createElement('img');
        curImg.src = photo.micro || photo.thumb;
        curImg.alt = '';
        currentCrumb.appendChild(curImg);
        breadcrumb.appendChild(currentCrumb);

        controls.appendChild(breadcrumb);
    }

    container.appendChild(controls);

    // Center photo
    const center = document.createElement('div');
    center.className = 'drift-center';

    const img = document.createElement('img');
    loadProgressive(img, photo, 'display');
    img.alt = photo.alt || photo.caption || '';
    img.addEventListener('click', () => openLightbox(photo));
    img.className = 'clickable-img';
    center.appendChild(img);

    // Meta
    const meta = document.createElement('div');
    meta.className = 'drift-center-meta';

    const alt = document.createElement('p');
    alt.className = 'drift-center-alt';
    alt.textContent = photo.caption || photo.alt || '';
    meta.appendChild(alt);

    const tags = document.createElement('div');
    tags.className = 'drift-center-tags';
    for (const v of (photo.vibes || [])) {
        tags.appendChild(createGlassTag(v, { category: 'vibe' }));
    }
    if (photo.grading) tags.appendChild(createGlassTag(photo.grading, { category: 'grading' }));
    if (photo.time) tags.appendChild(createGlassTag(photo.time, { category: 'time' }));
    if (photo.setting) tags.appendChild(createGlassTag(photo.setting, { category: 'setting' }));
    meta.appendChild(tags);

    const palette = document.createElement('div');
    palette.className = 'drift-center-palette';
    palette.appendChild(createPaletteDots(photo.palette, 16));
    meta.appendChild(palette);

    center.appendChild(meta);
    container.appendChild(center);

    // Neighbors — use "similarity" key (was "drift")
    const neighbors = (APP.data.similarity[photo.id] || []).slice(0, 6);
    if (neighbors.length > 0) {
        const neighborsGrid = document.createElement('div');
        neighborsGrid.className = 'drift-neighbors';

        for (const neighbor of neighbors) {
            const nPhoto = APP.photoMap[neighbor.id];
            if (!nPhoto) continue;

            const card = document.createElement('div');
            card.className = 'drift-neighbor';

            const nImg = createLazyImg(nPhoto, 'thumb');
            lazyObserver.observe(nImg);
            card.appendChild(nImg);

            const label = document.createElement('div');
            label.className = 'drift-neighbor-label';
            label.appendChild(document.createTextNode(titleCase(neighbor.reason)));
            card.appendChild(label);

            card.addEventListener('click', () => navigateSimilarity(neighbor.id));
            neighborsGrid.appendChild(card);
        }

        container.appendChild(neighborsGrid);
    }

    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
