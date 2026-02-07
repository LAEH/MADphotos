/* compass.js — Relations: Four-axis signal compass with animated transitions.
   Grid layout: top/bottom wide bars, left/right narrow, center hero.
   Landscape images only. Desktop/iPad landscape only. */

let compassCurrentId = null;
let compassAnimating = false;

/* Landscape-only pool — built once per init */
let compassPool = [];

function initCompass() {
    const container = document.getElementById('view-compass');
    container.innerHTML = '';

    compassPool = APP.data.photos.filter(p =>
        p.thumb && p.style !== 'portrait' && p.orientation !== 'portrait'
    );

    const vibePool = compassPool.filter(p => (p.vibes || []).length > 0);
    const start = randomFrom(vibePool.length ? vibePool : compassPool);
    compassAnimating = false;
    renderCompass(start, null);
}

/* ===== Initial render (no animation) ===== */
function renderCompass(photo, fromDirection) {
    compassCurrentId = photo.id;
    const container = document.getElementById('view-compass');

    /* Build fresh grid */
    const grid = document.createElement('div');
    grid.className = 'compass-grid';
    grid.id = 'compass-grid';

    /* Touch/swipe support for mobile — swipe to random */
    let touchStartX = 0, touchStartY = 0;
    grid.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY; }, {passive: true});
    grid.addEventListener('touchend', e => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 50) {
            if (compassAnimating) return;
            compassAnimating = true;
            const vibePool = compassPool.filter(p => (p.vibes || []).length > 0);
            renderCompass(randomFrom(vibePool.length ? vibePool : compassPool), null);
            compassAnimating = false;
        }
    }, {passive: true});

    const axes = [
        { key: 'north', label: 'Composition', finder: findCompositionMatch },
        { key: 'east',  label: 'Color',       finder: findColorMatch },
        { key: 'south', label: 'Mood',        finder: findMoodMatch },
        { key: 'west',  label: 'Meaning',     finder: findMeaningMatch },
    ];

    const matches = {};
    for (const axis of axes) {
        matches[axis.key] = { photo: axis.finder(photo, compassPool), label: axis.label };
    }

    /* North */
    const north = buildCompassArm('north', matches.north);
    north.style.gridArea = 'north';
    grid.appendChild(north);

    /* West */
    const west = buildCompassArm('west', matches.west);
    west.style.gridArea = 'west';
    grid.appendChild(west);

    /* Center */
    const center = document.createElement('div');
    center.className = 'compass-center';
    center.id = 'compass-center';
    center.style.gridArea = 'center';
    const centerImg = document.createElement('img');
    centerImg.className = 'compass-center-img clickable-img';
    loadProgressive(centerImg, photo, 'display');
    centerImg.alt = photo.caption || photo.alt || '';
    centerImg.addEventListener('click', () => openLightbox(photo));
    center.appendChild(centerImg);
    grid.appendChild(center);

    /* East */
    const east = buildCompassArm('east', matches.east);
    east.style.gridArea = 'east';
    grid.appendChild(east);

    /* South */
    const south = buildCompassArm('south', matches.south);
    south.style.gridArea = 'south';
    grid.appendChild(south);

    /* If first render, just place it */
    if (!fromDirection) {
        container.innerHTML = '';
        container.appendChild(grid);
        appendRandomBtn(container);
        /* Fade in arms */
        requestAnimationFrame(() => {
            grid.querySelectorAll('.compass-arm').forEach(arm => {
                arm.classList.add('compass-arm-enter');
            });
        });
        return;
    }

    /* Animated transition from a direction */
    animateTransition(container, grid, fromDirection);
}

/* ===== Animated transition ===== */
function animateTransition(container, newGrid, fromDirection) {
    const oldGrid = document.getElementById('compass-grid');
    if (!oldGrid) {
        container.innerHTML = '';
        container.appendChild(newGrid);
        appendRandomBtn(container);
        compassAnimating = false;
        return;
    }

    /* Phase 1: fade out old arms, keep the clicked arm visible */
    const oldArms = oldGrid.querySelectorAll('.compass-arm');
    const oldCenter = oldGrid.querySelector('.compass-center');

    /* Fade out all old arms except the one that was clicked */
    oldArms.forEach(arm => {
        const dir = arm.classList.contains('compass-north') ? 'north'
                  : arm.classList.contains('compass-east') ? 'east'
                  : arm.classList.contains('compass-south') ? 'south'
                  : 'west';
        if (dir !== fromDirection) {
            arm.style.transition = 'opacity 300ms var(--ease-out-quart)';
            arm.style.opacity = '0';
        }
    });

    /* Fade out old center */
    if (oldCenter) {
        oldCenter.style.transition = 'opacity 300ms var(--ease-out-quart)';
        oldCenter.style.opacity = '0';
    }

    /* Phase 2: after fade out, swap grids */
    setTimeout(() => {
        /* Start new grid hidden */
        newGrid.style.opacity = '0';
        container.innerHTML = '';
        container.appendChild(newGrid);
        appendRandomBtn(container);

        /* New center starts visible, arms start hidden */
        const newCenter = newGrid.querySelector('.compass-center');
        if (newCenter) {
            newCenter.style.opacity = '1';
        }

        const newArms = newGrid.querySelectorAll('.compass-arm');
        newArms.forEach(arm => {
            arm.style.opacity = '0';
            arm.style.transition = 'none';
        });

        /* Show the grid */
        requestAnimationFrame(() => {
            newGrid.style.transition = 'opacity 200ms var(--ease-out-quart)';
            newGrid.style.opacity = '1';

            /* Stagger arms appearing */
            requestAnimationFrame(() => {
                const delays = { north: 100, east: 180, south: 260, west: 340 };
                newArms.forEach(arm => {
                    const dir = arm.classList.contains('compass-north') ? 'north'
                              : arm.classList.contains('compass-east') ? 'east'
                              : arm.classList.contains('compass-south') ? 'south'
                              : 'west';
                    const delay = delays[dir] || 200;
                    setTimeout(() => {
                        arm.style.transition = 'opacity 400ms var(--ease-out-quart), transform 400ms var(--ease-out-expo)';
                        arm.style.opacity = '1';
                        arm.classList.add('compass-arm-enter');
                    }, delay);
                });

                /* Done animating */
                setTimeout(() => {
                    compassAnimating = false;
                }, 500);
            });
        });
    }, 320);
}

function appendRandomBtn(container) {
    /* Remove existing */
    const existing = container.querySelector('.compass-random');
    if (existing) existing.remove();

    const randomBtn = document.createElement('button');
    randomBtn.className = 'compass-random';
    randomBtn.textContent = 'random';
    randomBtn.addEventListener('click', () => {
        if (compassAnimating) return;
        compassAnimating = true;
        const vibePool = compassPool.filter(p => (p.vibes || []).length > 0);
        renderCompass(randomFrom(vibePool.length ? vibePool : compassPool), null);
        compassAnimating = false;
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
    loadProgressive(img, match.photo, 'thumb');
    img.alt = match.photo.caption || match.photo.alt || '';

    const overlay = document.createElement('div');
    overlay.className = 'compass-arm-overlay';

    const label = document.createElement('span');
    label.className = 'compass-arm-label';
    label.textContent = match.label;
    overlay.appendChild(label);

    const trait = getSharedTrait(direction, match.photo);
    if (trait) {
        const traitEl = document.createElement('span');
        traitEl.className = 'compass-arm-trait';
        traitEl.textContent = trait;
        overlay.appendChild(traitEl);
    }

    arm.appendChild(img);
    arm.appendChild(overlay);

    arm.addEventListener('click', () => {
        if (compassAnimating) return;
        compassAnimating = true;
        renderCompass(match.photo, direction);
    });
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
    if (!photo.composition) return randomFrom(all.filter(p => p.id !== photo.id));
    const matches = all.filter(p =>
        p.id !== photo.id && p.composition === photo.composition && p.scene !== photo.scene
    );
    return matches.length ? randomFrom(matches) : null;
}

function findColorMatch(photo, all) {
    const hue = photo.hue || 0;
    let best = null, bestDist = 999;
    const step = Math.max(1, Math.floor(all.length / 500));
    for (let i = 0; i < all.length; i += step) {
        const p = all[i];
        if (p.id === photo.id) continue;
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
    if (!vibes.length) return randomFrom(all.filter(p => p.id !== photo.id));
    const v = vibes[0];
    const matches = all.filter(p =>
        p.id !== photo.id && (p.vibes || []).includes(v) && p.category !== photo.category
    );
    return matches.length ? randomFrom(matches) : null;
}

function findMeaningMatch(photo, all) {
    const objs = photo.objects || [];
    if (!objs.length) return randomFrom(all.filter(p => p.id !== photo.id));
    const matches = all.filter(p => {
        if (p.id === photo.id) return false;
        return (p.objects || []).some(o => objs.includes(o)) && p.scene !== photo.scene;
    });
    return matches.length ? randomFrom(matches) : null;
}
