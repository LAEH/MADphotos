/* compass.js — La Boussole: Four-axis signal compass.
   Viewport-fixed cross layout. Center image prominent,
   four directional suggestions dimmed around it. */

let compassCurrentId = null;

function initCompass() {
    const container = document.getElementById('view-compass');
    container.innerHTML = '';

    const photos = APP.data.photos.filter(p => p.thumb && (p.vibes || []).length > 0);
    const start = randomFrom(photos.length ? photos : APP.data.photos);
    renderCompass(start);
}

function renderCompass(photo) {
    compassCurrentId = photo.id;
    const container = document.getElementById('view-compass');
    container.innerHTML = '';

    const layout = document.createElement('div');
    layout.className = 'compass-cross';

    /* Find one neighbor per axis */
    const allPhotos = APP.data.photos;
    const axes = [
        { key: 'north', label: 'Composition', finder: findCompositionMatch },
        { key: 'east',  label: 'Color',       finder: findColorMatch },
        { key: 'south', label: 'Mood',        finder: findMoodMatch },
        { key: 'west',  label: 'Meaning',     finder: findMeaningMatch },
    ];

    const matches = {};
    for (const axis of axes) {
        matches[axis.key] = { photo: axis.finder(photo, allPhotos), label: axis.label };
    }

    /* North */
    const north = buildCompassArm('north', matches.north);
    layout.appendChild(north);

    /* Middle row: west — center — east */
    const mid = document.createElement('div');
    mid.className = 'compass-mid';

    mid.appendChild(buildCompassArm('west', matches.west));

    /* Center */
    const center = document.createElement('div');
    center.className = 'compass-center';
    const centerImg = document.createElement('img');
    centerImg.className = 'compass-center-img clickable-img';
    loadProgressive(centerImg, photo, 'display');
    centerImg.alt = photo.caption || photo.alt || '';
    centerImg.addEventListener('click', () => openLightbox(photo));
    center.appendChild(centerImg);
    mid.appendChild(center);

    mid.appendChild(buildCompassArm('east', matches.east));

    layout.appendChild(mid);

    /* South */
    const south = buildCompassArm('south', matches.south);
    layout.appendChild(south);

    container.appendChild(layout);

    /* Random button — floating */
    const randomBtn = document.createElement('button');
    randomBtn.className = 'compass-random';
    randomBtn.textContent = 'random';
    randomBtn.addEventListener('click', () => {
        const photos = APP.data.photos.filter(p => p.thumb && (p.vibes || []).length > 0);
        renderCompass(randomFrom(photos));
    });
    container.appendChild(randomBtn);
}

function buildCompassArm(direction, match) {
    const arm = document.createElement('div');
    arm.className = 'compass-arm compass-' + direction;

    if (!match.photo) {
        arm.classList.add('compass-arm-empty');
        return arm;
    }

    const img = document.createElement('img');
    img.className = 'compass-arm-img';
    loadProgressive(img, match.photo, 'mobile');
    img.alt = match.photo.caption || match.photo.alt || '';

    const overlay = document.createElement('div');
    overlay.className = 'compass-arm-overlay';

    const label = document.createElement('span');
    label.className = 'compass-arm-label';
    label.textContent = match.label;
    overlay.appendChild(label);

    /* Show the shared trait */
    const trait = getSharedTrait(direction, match.photo);
    if (trait) {
        const traitEl = document.createElement('span');
        traitEl.className = 'compass-arm-trait';
        traitEl.textContent = trait;
        overlay.appendChild(traitEl);
    }

    arm.appendChild(img);
    arm.appendChild(overlay);

    arm.addEventListener('click', () => renderCompass(match.photo));
    return arm;
}

function getSharedTrait(direction, photo) {
    if (!photo) return null;
    switch (direction) {
        case 'north': return photo.composition ? titleCase(photo.composition) : null;
        case 'east': return photo.palette ? photo.palette[0] : null;
        case 'south': return (photo.vibes || [])[0] ? titleCase(photo.vibes[0]) : null;
        case 'west': return (photo.objects || [])[0] ? titleCase(photo.objects[0]) : null;
        default: return null;
    }
}

function findCompositionMatch(photo, all) {
    if (!photo.composition) return randomFrom(all.filter(p => p.thumb && p.id !== photo.id));
    const matches = all.filter(p =>
        p.id !== photo.id && p.thumb && p.composition === photo.composition && p.scene !== photo.scene
    );
    return matches.length ? randomFrom(matches) : null;
}

function findColorMatch(photo, all) {
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
    const vibes = photo.vibes || [];
    if (!vibes.length) return randomFrom(all.filter(p => p.thumb && p.id !== photo.id));
    const v = vibes[0];
    const matches = all.filter(p =>
        p.id !== photo.id && p.thumb && (p.vibes || []).includes(v) && p.category !== photo.category
    );
    return matches.length ? randomFrom(matches) : null;
}

function findMeaningMatch(photo, all) {
    const objs = photo.objects || [];
    if (!objs.length) return randomFrom(all.filter(p => p.thumb && p.id !== photo.id));
    const matches = all.filter(p => {
        if (p.id === photo.id || !p.thumb) return false;
        return (p.objects || []).some(o => objs.includes(o)) && p.scene !== photo.scene;
    });
    return matches.length ? randomFrom(matches) : null;
}
