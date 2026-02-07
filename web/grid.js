/* grid.js — La Grille: Semantic grid with justified rows, glass tags, filtering */

let gridFilters = new Set();
let gridLastVisible = null; /* cached filtered results */

const debouncedRenderGrid = debounce(renderGrid, 80);

function initGrille() {
    const container = document.getElementById('view-grille');
    container.innerHTML = '';

    /* Filter bar */
    const filterBar = document.createElement('div');
    filterBar.className = 'filter-bar';
    filterBar.id = 'grid-filter-bar';
    container.appendChild(filterBar);

    /* Grid container */
    const gridWrap = document.createElement('div');
    gridWrap.className = 'grid-container';
    gridWrap.id = 'grid-container';
    container.appendChild(gridWrap);

    gridLastVisible = null;
    renderGrid();
    updateFilterBar();
}

function renderGrid() {
    const wrap = document.getElementById('grid-container');
    if (!wrap) return;
    wrap.innerHTML = '';

    const photos = APP.data.photos;
    const targetRowHeight = 220;
    const gap = 4;
    const containerWidth = wrap.clientWidth - 24;

    /* Filter photos — cache result */
    const visible = gridFilters.size === 0
        ? photos
        : photos.filter(p => matchesFilters(p));
    gridLastVisible = visible;

    /* Build justified rows */
    let row = [];
    let rowAspect = 0;

    for (const photo of visible) {
        const aspect = photo.aspect || (photo.w / photo.h) || 1.5;
        row.push({ photo, aspect });
        rowAspect += aspect;

        const rowWidth = rowAspect * targetRowHeight + (row.length - 1) * gap;

        if (rowWidth >= containerWidth && row.length >= 2) {
            const availableWidth = containerWidth - (row.length - 1) * gap;
            const rowHeight = availableWidth / rowAspect;
            renderRow(wrap, row, rowHeight, gap);
            row = [];
            rowAspect = 0;
        }
    }

    /* Render leftover row */
    if (row.length > 0) {
        const height = Math.min(targetRowHeight, (containerWidth - (row.length - 1) * gap) / rowAspect);
        renderRow(wrap, row, height, gap);
    }
}

function renderRow(container, items, height, gap) {
    const rowEl = document.createElement('div');
    rowEl.className = 'grid-row';
    rowEl.style.marginBottom = gap + 'px';

    for (const { photo, aspect } of items) {
        const width = Math.floor(aspect * height);
        const item = document.createElement('div');
        item.className = 'grid-item';
        item.style.width = width + 'px';
        item.style.height = Math.floor(height) + 'px';

        const img = createLazyImg(photo, 'thumb');
        lazyObserver.observe(img);
        item.appendChild(img);

        /* Overlay with tags */
        const overlay = document.createElement('div');
        overlay.className = 'grid-overlay';

        const tagRow = document.createElement('div');
        tagRow.className = 'grid-overlay-tags';

        for (const vibe of (photo.vibes || []).slice(0, 3)) {
            tagRow.appendChild(createGlassTag(vibe, {
                category: 'vibe',
                active: gridFilters.has('vibe:' + vibe),
                onClick: () => toggleFilter('vibe', vibe),
            }));
        }
        if (photo.grading) {
            tagRow.appendChild(createGlassTag(photo.grading, {
                category: 'grading',
                active: gridFilters.has('grading:' + photo.grading),
                onClick: () => toggleFilter('grading', photo.grading),
            }));
        }

        overlay.appendChild(tagRow);
        item.appendChild(overlay);

        item.addEventListener('click', () => openLightbox(photo));
        rowEl.appendChild(item);
    }

    container.appendChild(rowEl);
}

function matchesFilters(photo) {
    for (const f of gridFilters) {
        const [dim, val] = f.split(':');
        if (dim === 'vibe') {
            if (!(photo.vibes || []).some(v => v === val)) return false;
        } else if (dim === 'grading') {
            if (photo.grading !== val) return false;
        } else if (dim === 'time') {
            if (photo.time !== val) return false;
        } else if (dim === 'setting') {
            if (photo.setting !== val) return false;
        } else if (dim === 'category') {
            if (photo.category !== val) return false;
        } else if (dim === 'composition') {
            if (photo.composition !== val) return false;
        } else if (dim === 'exposure') {
            if (photo.exposure !== val) return false;
        } else if (dim === 'depth') {
            if (photo.depth !== val) return false;
        }
    }
    return true;
}

function toggleFilter(dimension, value) {
    const key = dimension + ':' + value;
    if (gridFilters.has(key)) {
        gridFilters.delete(key);
    } else {
        gridFilters.add(key);
    }
    debouncedRenderGrid();
    updateFilterBar();
}

function updateFilterBar() {
    const bar = document.getElementById('grid-filter-bar');
    if (!bar) return;
    bar.innerHTML = '';

    /* Quick filter groups */
    const groups = [
        { label: 'vibe', values: APP.data.vibes.slice(0, 12) },
        { label: 'grading', values: APP.data.gradings },
        { label: 'time', values: APP.data.times },
        { label: 'setting', values: APP.data.settings },
    ];

    /* If filters are active, show active pills + count */
    if (gridFilters.size > 0) {
        const activeSection = document.createElement('div');
        activeSection.className = 'filter-active-section';

        for (const f of gridFilters) {
            const [dim, val] = f.split(':');
            activeSection.appendChild(createGlassTag(val, {
                category: dim,
                active: true,
                onClick: () => toggleFilter(dim, val),
            }));
        }

        const clear = document.createElement('button');
        clear.className = 'clear-btn';
        clear.textContent = 'clear';
        clear.addEventListener('click', () => {
            gridFilters.clear();
            renderGrid();
            updateFilterBar();
        });
        activeSection.appendChild(clear);

        /* Use cached count from last render */
        const matchCount = gridLastVisible ? gridLastVisible.length : 0;
        const count = document.createElement('span');
        count.className = 'filter-count';
        count.textContent = matchCount + ' / ' + APP.data.count;
        activeSection.appendChild(count);

        bar.appendChild(activeSection);
        return;
    }

    /* Show quick filter groups as compact rows */
    for (const group of groups) {
        const label = document.createElement('span');
        label.className = 'filter-label';
        label.textContent = group.label;
        bar.appendChild(label);

        for (const val of group.values) {
            bar.appendChild(createGlassTag(val, {
                category: group.label,
                onClick: () => toggleFilter(group.label, val),
            }));
        }
    }
}
