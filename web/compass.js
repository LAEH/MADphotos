/* compass.js — La Boussole: Four-axis signal compass */

let compassCurrentId = null;

function initCompass() {

    const container = document.getElementById('view-compass');
    container.innerHTML = '';

    const inner = document.createElement('div');
    inner.className = 'compass-container';
    inner.id = 'compass-inner';
    container.appendChild(inner);

    const photos = APP.data.photos.filter(p => p.thumb && p.vibes.length > 0);
    const start = randomFrom(photos.length ? photos : APP.data.photos);
    renderCompass(start);
}

function renderCompass(photo) {
    compassCurrentId = photo.id;
    const container = document.getElementById('compass-inner');
    container.innerHTML = '';

    // Center image
    const center = document.createElement('div');
    center.className = 'compass-center';

    const img = document.createElement('img');
    loadProgressive(img, photo, 'display');
    img.alt = photo.caption || photo.alt || '';
    img.addEventListener('click', () => openLightbox(photo));
    center.appendChild(img);

    // Caption
    if (photo.caption || photo.alt) {
        const cap = document.createElement('p');
        cap.className = 'compass-caption';
        cap.textContent = photo.caption || photo.alt;
        center.appendChild(cap);
    }

    container.appendChild(center);

    // Four axes: composition (N), color (E), mood (S), meaning (W)
    const axes = document.createElement('div');
    axes.className = 'compass-axes';

    const neighbors = APP.data.similarity[photo.id] || [];
    const allPhotos = APP.data.photos;

    // Find one neighbor per axis
    const axisConfigs = [
        { label: 'Composition', dir: 'north', finder: findCompositionMatch },
        { label: 'Color', dir: 'east', finder: findColorMatch },
        { label: 'Mood', dir: 'south', finder: findMoodMatch },
        { label: 'Meaning', dir: 'west', finder: findMeaningMatch },
    ];

    for (const axis of axisConfigs) {
        const match = axis.finder(photo, allPhotos);
        if (!match) continue;

        const card = document.createElement('div');
        card.className = 'compass-card compass-' + axis.dir;

        const label = document.createElement('div');
        label.className = 'compass-label';
        label.textContent = axis.label;
        card.appendChild(label);

        const nImg = createLazyImg(match, 'thumb');
        lazyObserver.observe(nImg);
        card.appendChild(nImg);

        card.addEventListener('click', () => renderCompass(match));
        axes.appendChild(card);
    }

    container.appendChild(axes);
}

function findCompositionMatch(photo, all) {
    // Same composition technique, different scene
    if (!photo.composition) return randomFrom(all.filter(p => p.thumb && p.id !== photo.id));
    const matches = all.filter(p =>
        p.id !== photo.id && p.thumb && p.composition === photo.composition && p.scene !== photo.scene
    );
    return matches.length ? randomFrom(matches) : null;
}

function findColorMatch(photo, all) {
    /* Closest hue — sample 500 without copying entire array */
    const hue = photo.hue || 0;
    let best = null, bestDist = 999;
    const step = Math.max(1, Math.floor(all.length / 500));
    for (let i = 0; i < all.length; i += step) {
        const p = all[i];
        if (p.id === photo.id || !p.thumb) continue;
        let d = Math.abs((p.hue || 0) - hue);
        if (d > 180) d = 360 - d;
        if (d < bestDist && d > 5) {
            bestDist = d;
            best = p;
        }
    }
    return best;
}

function findMoodMatch(photo, all) {
    // Same dominant vibe, different visual
    const vibes = photo.vibes || [];
    if (!vibes.length) return randomFrom(all.filter(p => p.thumb && p.id !== photo.id));
    const v = vibes[0];
    const matches = all.filter(p =>
        p.id !== photo.id && p.thumb && (p.vibes || []).includes(v) && p.category !== photo.category
    );
    return matches.length ? randomFrom(matches) : null;
}

function findMeaningMatch(photo, all) {
    // Same detected objects, different everything else
    const objs = photo.objects || [];
    if (!objs.length) return randomFrom(all.filter(p => p.thumb && p.id !== photo.id));
    const matches = all.filter(p => {
        if (p.id === photo.id || !p.thumb) return false;
        return (p.objects || []).some(o => objs.includes(o)) && p.scene !== photo.scene;
    });
    return matches.length ? randomFrom(matches) : null;
}
