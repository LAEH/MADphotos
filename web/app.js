/* app.js — Core data loading, router, shared utilities */

const APP = {
    data: null,
    photoMap: {},
    currentView: 'grille',
    activeFilters: [],
};

/* ===== Data Loading ===== */
async function loadData() {
    const resp = await fetch('/data/photos.json');
    APP.data = await resp.json();

    // Build lookup map
    for (const photo of APP.data.photos) {
        APP.photoMap[photo.id] = photo;
    }

    document.getElementById('photo-count').textContent = APP.data.count + ' photos';
    return APP.data;
}

/* ===== Router ===== */
function initRouter() {
    const tabs = document.querySelectorAll('.tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const view = tab.dataset.view;
            switchView(view);
        });
    });

    // Hash routing
    const hash = location.hash.slice(1);
    if (['grille', 'derive', 'couleurs'].includes(hash)) {
        switchView(hash);
    }
}

function switchView(name) {
    APP.currentView = name;
    location.hash = name;

    document.querySelectorAll('.tab').forEach(t => {
        t.classList.toggle('active', t.dataset.view === name);
    });
    document.querySelectorAll('.view').forEach(v => {
        v.classList.toggle('active', v.id === 'view-' + name);
    });

    // Trigger view activation
    if (name === 'grille' && typeof initGrille === 'function') initGrille();
    if (name === 'derive' && typeof initDerive === 'function') initDerive();
    if (name === 'couleurs' && typeof initCouleurs === 'function') initCouleurs();
}

/* ===== Glass Tag Component ===== */
function createGlassTag(text, opts = {}) {
    const tag = document.createElement('span');
    tag.className = 'glass-tag';
    if (opts.active) tag.classList.add('active');

    if (opts.color) {
        const dot = document.createElement('span');
        dot.className = 'dot';
        dot.style.background = opts.color;
        tag.appendChild(dot);
    }

    tag.appendChild(document.createTextNode(text));

    if (opts.onClick) {
        tag.addEventListener('click', (e) => {
            e.stopPropagation();
            opts.onClick(text, tag);
        });
    }

    return tag;
}

/* ===== Palette Dots ===== */
function createPaletteDots(palette, size) {
    const frag = document.createDocumentFragment();
    for (const hex of (palette || [])) {
        const dot = document.createElement('span');
        dot.className = 'palette-dot';
        dot.style.background = hex;
        if (size) {
            dot.style.width = size + 'px';
            dot.style.height = size + 'px';
        }
        frag.appendChild(dot);
    }
    return frag;
}

/* ===== Lightbox ===== */
function initLightbox() {
    const lb = document.getElementById('lightbox');
    const backdrop = lb.querySelector('.lightbox-backdrop');
    const closeBtn = lb.querySelector('.lightbox-close');

    function close() {
        lb.classList.add('hidden');
    }

    backdrop.addEventListener('click', close);
    closeBtn.addEventListener('click', close);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') close();
    });
}

function openLightbox(photo) {
    const lb = document.getElementById('lightbox');
    const img = lb.querySelector('.lightbox-img');
    const alt = lb.querySelector('.lightbox-alt');
    const tags = lb.querySelector('.lightbox-tags');
    const palette = lb.querySelector('.lightbox-palette');

    img.src = photo.display || photo.mobile || photo.thumb;
    img.alt = photo.alt;
    alt.textContent = photo.alt;

    tags.innerHTML = '';
    for (const v of (photo.vibes || [])) {
        tags.appendChild(createGlassTag(v));
    }
    if (photo.grading) tags.appendChild(createGlassTag(photo.grading));
    if (photo.time) tags.appendChild(createGlassTag(photo.time));

    palette.innerHTML = '';
    palette.appendChild(createPaletteDots(photo.palette, 20));

    lb.classList.remove('hidden');
}

/* ===== Progressive Image Loading ===== */
function loadProgressive(img, photo, targetTier) {
    // Start with micro (tiny, instant), then load target
    if (photo.micro) {
        img.src = photo.micro;
    }

    const target = photo[targetTier] || photo.thumb;
    if (target && target !== photo.micro) {
        const full = new Image();
        full.onload = () => {
            img.src = target;
        };
        full.src = target;
    }
}

/* ===== Lazy Loading with IntersectionObserver ===== */
function createLazyImg(photo, targetTier) {
    const img = document.createElement('img');
    img.alt = photo.alt || '';
    img.loading = 'lazy';
    // Set micro as immediate placeholder
    if (photo.micro) {
        img.src = photo.micro;
    }
    img.dataset.src = photo[targetTier] || photo.thumb;
    img.dataset.id = photo.id;
    return img;
}

const lazyObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
        if (entry.isIntersecting) {
            const img = entry.target;
            const src = img.dataset.src;
            if (src && img.src !== src) {
                const full = new Image();
                full.onload = () => { img.src = src; };
                full.src = src;
            }
            lazyObserver.unobserve(img);
        }
    }
}, { rootMargin: '200px' });

/* ===== Init ===== */
async function init() {
    // Show loading
    document.getElementById('view-grille').innerHTML = '<div class="loading">Loading photographs</div>';

    await loadData();
    initRouter();
    initLightbox();

    // Start with the active view
    switchView(APP.currentView);
}

document.addEventListener('DOMContentLoaded', init);
