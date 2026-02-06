/* drift.js — La Dérive: Semantic drift through connected photographs */

let driftInitialized = false;
let driftHistory = [];
let driftCurrentId = null;

function initDerive() {
    if (driftInitialized) {
        return;
    }
    driftInitialized = true;

    const container = document.getElementById('view-derive');
    container.innerHTML = '';

    const driftEl = document.createElement('div');
    driftEl.className = 'drift-container';
    driftEl.id = 'drift-inner';
    container.appendChild(driftEl);

    // Pick a random starting photo
    const photos = APP.data.photos;
    const startIdx = Math.floor(Math.random() * photos.length);
    navigateDrift(photos[startIdx].id);
}

function navigateDrift(photoId) {
    const photo = APP.photoMap[photoId];
    if (!photo) return;

    // Update history
    if (driftCurrentId && driftCurrentId !== photoId) {
        // Remove forward history if we went back
        const existingIdx = driftHistory.indexOf(photoId);
        if (existingIdx >= 0) {
            driftHistory = driftHistory.slice(0, existingIdx);
        }
        driftHistory.push(driftCurrentId);
    }
    driftCurrentId = photoId;

    renderDrift(photo);
}

function renderDrift(photo) {
    const container = document.getElementById('drift-inner');
    container.innerHTML = '';

    // Controls bar
    const controls = document.createElement('div');
    controls.className = 'drift-controls';

    // Random button
    const randomBtn = document.createElement('button');
    randomBtn.className = 'drift-btn';
    randomBtn.textContent = 'random';
    randomBtn.addEventListener('click', () => {
        const photos = APP.data.photos;
        const idx = Math.floor(Math.random() * photos.length);
        navigateDrift(photos[idx].id);
    });
    controls.appendChild(randomBtn);

    // Back button
    if (driftHistory.length > 0) {
        const backBtn = document.createElement('button');
        backBtn.className = 'drift-btn';
        backBtn.textContent = 'back';
        backBtn.addEventListener('click', () => {
            const prevId = driftHistory.pop();
            if (prevId) {
                driftCurrentId = prevId;
                renderDrift(APP.photoMap[prevId]);
            }
        });
        controls.appendChild(backBtn);
    }

    // Breadcrumb trail
    if (driftHistory.length > 0) {
        const breadcrumb = document.createElement('div');
        breadcrumb.className = 'drift-breadcrumb';

        const trail = driftHistory.slice(-8);
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
                // Navigate back to this point
                const idx = driftHistory.indexOf(trail[i]);
                if (idx >= 0) {
                    driftHistory = driftHistory.slice(0, idx);
                    driftCurrentId = trail[i];
                    renderDrift(APP.photoMap[trail[i]]);
                }
            });
            breadcrumb.appendChild(crumb);

            if (i < trail.length - 1) {
                const arrow = document.createElement('span');
                arrow.className = 'drift-breadcrumb-arrow';
                arrow.textContent = '›';
                breadcrumb.appendChild(arrow);
            }
        }

        // Current dot
        const arrow = document.createElement('span');
        arrow.className = 'drift-breadcrumb-arrow';
        arrow.textContent = '›';
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
    img.alt = photo.alt || '';
    img.addEventListener('click', () => openLightbox(photo));
    img.style.cursor = 'pointer';
    center.appendChild(img);

    // Meta
    const meta = document.createElement('div');
    meta.className = 'drift-center-meta';

    const alt = document.createElement('p');
    alt.className = 'drift-center-alt';
    alt.textContent = photo.alt || '';
    meta.appendChild(alt);

    const tags = document.createElement('div');
    tags.className = 'drift-center-tags';
    for (const v of (photo.vibes || [])) {
        tags.appendChild(createGlassTag(v));
    }
    if (photo.grading) tags.appendChild(createGlassTag(photo.grading));
    if (photo.time) tags.appendChild(createGlassTag(photo.time));
    if (photo.setting) tags.appendChild(createGlassTag(photo.setting));
    if (photo.composition) tags.appendChild(createGlassTag(photo.composition));
    meta.appendChild(tags);

    const palette = document.createElement('div');
    palette.className = 'drift-center-palette';
    palette.appendChild(createPaletteDots(photo.palette, 16));
    meta.appendChild(palette);

    center.appendChild(meta);
    container.appendChild(center);

    // Neighbors
    const neighbors = (APP.data.drift[photo.id] || []).slice(0, 6);
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

            const dot = document.createElement('span');
            dot.className = 'connection-dot';
            label.appendChild(dot);

            label.appendChild(document.createTextNode(neighbor.reason));
            card.appendChild(label);

            card.addEventListener('click', () => navigateDrift(neighbor.id));
            neighborsGrid.appendChild(card);
        }

        container.appendChild(neighborsGrid);
    }

    // Smooth scroll to top
    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
