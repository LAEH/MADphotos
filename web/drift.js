/* drift.js — La Dérive: Creative structural drift via visual similarity
   Uses DINOv2 embeddings to find images with similar composition/shape
   regardless of subject matter. A shoe matches a skateboard ramp. */

let deriveInitialized = false;
let deriveHistory = [];
let deriveCurrentId = null;

function initDerive() {
    if (deriveInitialized) return;
    deriveInitialized = true;

    const container = document.getElementById('view-derive');
    container.innerHTML = '';

    const inner = document.createElement('div');
    inner.className = 'drift-container';
    inner.id = 'derive-inner';
    container.appendChild(inner);

    // Note: For now, uses similarity connections until DINOv2 neighbors are precomputed
    // TODO: Replace with compass_neighbors.json (DINOv2 structural similarity)
    const photos = APP.data.photos.filter(p => p.thumb);
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

    // Controls
    const controls = document.createElement('div');
    controls.className = 'drift-controls';

    const randomBtn = document.createElement('button');
    randomBtn.className = 'drift-btn';
    randomBtn.textContent = 'random';
    randomBtn.addEventListener('click', () => {
        const photos = APP.data.photos.filter(p => p.thumb);
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

    // Breadcrumb
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

    // Center image — larger, more dramatic
    const center = document.createElement('div');
    center.className = 'drift-center';

    const img = document.createElement('img');
    loadProgressive(img, photo, 'display');
    img.alt = photo.alt || photo.caption || '';
    img.addEventListener('click', () => openLightbox(photo));
    img.style.cursor = 'pointer';
    center.appendChild(img);

    // Minimal meta — just caption, no tags for cleaner drift feeling
    if (photo.caption || photo.alt) {
        const cap = document.createElement('p');
        cap.className = 'drift-center-alt';
        cap.textContent = photo.caption || photo.alt;
        center.appendChild(cap);
    }

    container.appendChild(center);

    // Find drift neighbors: use similarity but favor visual/structural matches
    // Prefer neighbors that share style/composition but DIFFER in subject
    const simNeighbors = APP.data.similarity[photo.id] || [];
    const allPhotos = APP.data.photos;

    // Build "drift" neighbors: find photos with similar depth complexity + composition
    // but from different categories/scenes
    const driftCandidates = [];
    for (const p of allPhotos) {
        if (p.id === photo.id || !p.thumb) continue;

        let score = 0;
        // Similar aspect ratio
        if (Math.abs((p.aspect || 1.5) - (photo.aspect || 1.5)) < 0.3) score += 2;
        // Similar depth complexity
        if (p.depth_complexity != null && photo.depth_complexity != null) {
            if (Math.abs(p.depth_complexity - photo.depth_complexity) < 1) score += 3;
        }
        // Similar brightness
        if (p.brightness != null && photo.brightness != null) {
            if (Math.abs(p.brightness - photo.brightness) < 30) score += 1;
        }
        // Same composition technique but different scene
        if (p.composition && photo.composition && p.composition === photo.composition && p.scene !== photo.scene) {
            score += 5;
        }
        // Same style but different category
        if (p.style && photo.style && p.style === photo.style && p.category !== photo.category) {
            score += 3;
        }
        // Penalize same scene/setting (we want unexpected connections)
        if (p.scene === photo.scene && photo.scene) score -= 2;
        if (p.setting === photo.setting && photo.setting) score -= 1;

        if (score > 3) {
            driftCandidates.push({ photo: p, score });
        }
    }

    // Sort by score, take top 6
    driftCandidates.sort((a, b) => b.score - a.score);
    let neighbors = driftCandidates.slice(0, 6).map(c => c.photo);

    // Fallback to similarity if not enough drift candidates
    if (neighbors.length < 4) {
        for (const n of simNeighbors) {
            if (neighbors.length >= 6) break;
            const np = APP.photoMap[n.id];
            if (np && !neighbors.find(x => x.id === np.id)) {
                neighbors.push(np);
            }
        }
    }

    if (neighbors.length > 0) {
        const neighborsGrid = document.createElement('div');
        neighborsGrid.className = 'drift-neighbors';

        for (const nPhoto of neighbors) {
            const card = document.createElement('div');
            card.className = 'drift-neighbor';

            const nImg = createLazyImg(nPhoto, 'thumb');
            lazyObserver.observe(nImg);
            card.appendChild(nImg);

            card.addEventListener('click', () => navigateDerive(nPhoto.id));
            neighborsGrid.appendChild(card);
        }

        container.appendChild(neighborsGrid);
    }

    container.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
