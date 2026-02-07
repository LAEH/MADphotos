/* grid.js — Sort: Top 1,000 photographs with glass sort bar.
   Sort by aesthetic, vibe, scene, color, light.
   Adjustable grid density (S/M/L). */

let sortMethod = 'aesthetic';
let sortedPhotos = [];
let gridSize = 'M';

const GRID_SIZES = { S: 140, M: 220, L: 320 };

function initGrille() {
    const container = document.getElementById('view-grille');
    container.innerHTML = '';

    const pool = APP.data.photos.filter(p => p.thumb);
    sortedPhotos = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0)).slice(0, 1000);
    sortMethod = 'aesthetic';

    /* Glass sort bar */
    const sortBar = document.createElement('div');
    sortBar.className = 'sort-bar';
    sortBar.id = 'sort-bar';

    const inner = document.createElement('div');
    inner.className = 'sort-bar-inner';

    const methods = [
        { id: 'aesthetic', label: 'Aesthetic' },
        { id: 'vibe',     label: 'Vibe' },
        { id: 'scene',    label: 'Scene' },
        { id: 'color',    label: 'Color' },
        { id: 'light',    label: 'Light' },
    ];

    for (const m of methods) {
        const btn = document.createElement('button');
        btn.className = 'sort-btn' + (m.id === sortMethod ? ' active' : '');
        btn.dataset.sort = m.id;
        btn.textContent = m.label;
        btn.addEventListener('click', () => applySortMethod(m.id));
        inner.appendChild(btn);
    }

    /* Separator */
    const sep = document.createElement('div');
    sep.className = 'sort-sep';
    inner.appendChild(sep);

    /* Grid size toggle */
    for (const size of ['S', 'M', 'L']) {
        const btn = document.createElement('button');
        btn.className = 'sort-size-btn' + (size === gridSize ? ' active' : '');
        btn.dataset.size = size;
        btn.textContent = size;
        btn.addEventListener('click', () => {
            gridSize = size;
            document.querySelectorAll('.sort-size-btn').forEach(b => {
                b.classList.toggle('active', b.dataset.size === size);
            });
            renderSortGrid();
        });
        inner.appendChild(btn);
    }

    sortBar.appendChild(inner);
    container.appendChild(sortBar);

    /* Grid wrap */
    const gridWrap = document.createElement('div');
    gridWrap.className = 'sort-grid-wrap';
    gridWrap.id = 'sort-grid-wrap';
    container.appendChild(gridWrap);

    renderSortGrid();
}

function applySortMethod(method) {
    sortMethod = method;

    document.querySelectorAll('.sort-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.sort === method);
    });

    const pool = APP.data.photos.filter(p => p.thumb);
    const top1000 = [...pool].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0)).slice(0, 1000);

    switch (method) {
        case 'aesthetic':
            sortedPhotos = top1000;
            break;
        case 'vibe':
            sortedPhotos = [...top1000].sort((a, b) => {
                const va = (a.vibes && a.vibes[0]) || '\uffff';
                const vb = (b.vibes && b.vibes[0]) || '\uffff';
                return va.localeCompare(vb);
            });
            break;
        case 'scene':
            sortedPhotos = [...top1000].sort((a, b) => {
                return (a.scene || '\uffff').localeCompare(b.scene || '\uffff');
            });
            break;
        case 'color':
            sortedPhotos = [...top1000].sort((a, b) => {
                /* Use precomputed hue from most-saturated palette color */
                const ha = (a.hue != null && a.hue > 0) ? a.hue : 999;
                const hb = (b.hue != null && b.hue > 0) ? b.hue : 999;
                return ha - hb;
            });
            break;
        case 'light':
            sortedPhotos = [...top1000].sort((a, b) => {
                const la = a.palette && a.palette[0] ? hexToLightness(a.palette[0]) : 50;
                const lb = b.palette && b.palette[0] ? hexToLightness(b.palette[0]) : 50;
                return la - lb;
            });
            break;
    }

    renderSortGrid();
    document.getElementById('view-grille').scrollTo({ top: 0, behavior: 'smooth' });
}

function renderSortGrid() {
    const wrap = document.getElementById('sort-grid-wrap');
    if (!wrap) return;
    wrap.innerHTML = '';

    const targetRowHeight = GRID_SIZES[gridSize] || 220;
    const gap = 4;
    const containerWidth = Math.min(wrap.clientWidth || 1100, 1100);

    let row = [];
    let rowAspect = 0;

    for (const photo of sortedPhotos) {
        const aspect = photo.aspect || (photo.w / photo.h) || 1.5;
        row.push({ photo, aspect });
        rowAspect += aspect;

        const rowWidth = rowAspect * targetRowHeight + (row.length - 1) * gap;

        if (rowWidth >= containerWidth && row.length >= 2) {
            const availableWidth = containerWidth - (row.length - 1) * gap;
            const rowHeight = availableWidth / rowAspect;
            renderSortRow(wrap, row, rowHeight, gap);
            row = [];
            rowAspect = 0;
        }
    }

    if (row.length > 0) {
        const height = Math.min(targetRowHeight, (containerWidth - (row.length - 1) * gap) / rowAspect);
        renderSortRow(wrap, row, height, gap);
    }
}

function renderSortRow(container, items, height, gap) {
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

        /* Tap-to-toggle overlay on mobile (hover doesn't work on touch) */
        item.addEventListener('click', (e) => {
            if ('ontouchstart' in window) {
                if (!item.classList.contains('tapped')) {
                    document.querySelectorAll('.grid-item.tapped').forEach(el => el.classList.remove('tapped'));
                    item.classList.add('tapped');
                    e.stopPropagation();
                    return;
                }
            }
            openLightbox(photo, sortedPhotos);
        });
        rowEl.appendChild(item);
    }

    container.appendChild(rowEl);
}
