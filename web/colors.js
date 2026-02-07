/* colors.js — Les Couleurs: Color space exploration */

let colorBuckets = [];
let activeColorIdx = -1;

const NUM_BUCKETS = 24;

function initCouleurs() {

    buildColorBuckets();

    const container = document.getElementById('view-couleurs');
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'colors-container';

    // Spectrum bar
    const spectrum = document.createElement('div');
    spectrum.className = 'color-spectrum';
    spectrum.id = 'color-spectrum';

    for (let i = 0; i < colorBuckets.length; i++) {
        const bucket = colorBuckets[i];
        const band = document.createElement('div');
        band.className = 'color-band';
        band.style.background = bucket.color;
        band.dataset.idx = i;

        const count = document.createElement('span');
        count.className = 'color-band-count';
        count.textContent = bucket.photos.length;
        band.appendChild(count);

        band.addEventListener('click', () => selectColorBand(i));
        spectrum.appendChild(band);
    }

    wrap.appendChild(spectrum);

    // Grid area
    const gridWrap = document.createElement('div');
    gridWrap.className = 'colors-grid-wrapper';
    gridWrap.id = 'colors-grid-wrapper';
    wrap.appendChild(gridWrap);

    container.appendChild(wrap);

    // Show all photos sorted by hue initially
    renderAllByColor();
}

function isGrayPalette(palette) {
    if (!palette || palette.length === 0) return false;
    return palette.every(hex => {
        if (!hex || hex.length < 7) return true;
        const r = parseInt(hex.slice(1, 3), 16);
        const g = parseInt(hex.slice(3, 5), 16);
        const b = parseInt(hex.slice(5, 7), 16);
        return (Math.max(r, g, b) - Math.min(r, g, b)) < 30;
    });
}

function buildColorBuckets() {
    colorBuckets = [];
    const bucketSize = 360 / NUM_BUCKETS;

    for (let i = 0; i < NUM_BUCKETS; i++) {
        const hueStart = i * bucketSize;
        const hueMid = hueStart + bucketSize / 2;
        colorBuckets.push({
            hueStart,
            hueEnd: hueStart + bucketSize,
            color: `hsl(${hueMid}, 65%, 50%)`,
            photos: [],
        });
    }

    /* Sort photos into buckets — single pass, gray detection shared */
    const grayPhotos = [];
    for (const photo of APP.data.photos) {
        if (isGrayPalette(photo.palette)) {
            grayPhotos.push(photo);
            continue;
        }
        const hue = photo.hue || 0;
        const idx = Math.min(Math.floor(hue / bucketSize), NUM_BUCKETS - 1);
        colorBuckets[idx].photos.push(photo);
    }

    if (grayPhotos.length > 0) {
        colorBuckets.push({
            hueStart: -1,
            hueEnd: -1,
            color: _rs.getPropertyValue('--system-gray').trim() || '#8e8e93',
            photos: grayPhotos,
        });
    }
}

function selectColorBand(idx) {
    if (activeColorIdx === idx) {
        activeColorIdx = -1;
        renderAllByColor();
    } else {
        activeColorIdx = idx;
        renderColorBucket(idx);
    }

    // Update band active states
    document.querySelectorAll('.color-band').forEach((band, i) => {
        band.classList.toggle('active', i === activeColorIdx);
    });
}

function renderAllByColor() {
    const wrap = document.getElementById('colors-grid-wrapper');
    wrap.innerHTML = '';

    // Show all photos sorted by hue in a single grid
    const sorted = [...APP.data.photos].sort((a, b) => (a.hue || 0) - (b.hue || 0));

    const title = document.createElement('div');
    title.className = 'colors-section-title';
    title.textContent = 'all ' + sorted.length + ' photos by dominant hue — click a color band to filter';
    wrap.appendChild(title);

    const grid = document.createElement('div');
    grid.className = 'colors-grid';

    const targetHeight = 160;

    for (const photo of sorted) {
        const aspect = photo.aspect || 1.5;
        const width = Math.floor(aspect * targetHeight);

        const item = document.createElement('div');
        item.className = 'colors-grid-item';
        item.style.width = width + 'px';
        item.style.height = targetHeight + 'px';

        const img = createLazyImg(photo, 'thumb');
        lazyObserver.observe(img);
        item.appendChild(img);

        // Semantic pop labels on hover
        if (photo.pops && photo.pops.length > 0) {
            const popWrap = document.createElement('div');
            popWrap.className = 'colors-pop-label';
            for (const pop of photo.pops.slice(0, 2)) {
                popWrap.appendChild(createGlassTag(
                    pop.color + ' ' + pop.object,
                    { color: colorNameToCSS(pop.color) }
                ));
            }
            item.appendChild(popWrap);
        }

        item.addEventListener('click', () => openLightbox(photo));
        grid.appendChild(item);
    }

    wrap.appendChild(grid);
}

function renderColorBucket(idx) {
    const bucket = colorBuckets[idx];
    if (!bucket) return;

    const wrap = document.getElementById('colors-grid-wrapper');
    wrap.innerHTML = '';

    const photos = bucket.photos;

    const title = document.createElement('div');
    title.className = 'colors-section-title';

    const swatch = document.createElement('span');
    swatch.className = 'color-swatch-sm';
    swatch.style.background = bucket.color;
    title.appendChild(swatch);
    title.appendChild(document.createTextNode(
        photos.length + ' photos with this dominant color'
    ));
    wrap.appendChild(title);

    if (photos.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'No photos in this color range.';
        wrap.appendChild(empty);
        return;
    }

    const grid = document.createElement('div');
    grid.className = 'colors-grid colors-grid-bucket';

    const targetHeight = 220;

    for (const photo of photos) {
        const aspect = photo.aspect || 1.5;
        const width = Math.floor(aspect * targetHeight);

        const item = document.createElement('div');
        item.className = 'colors-grid-item';
        item.style.width = width + 'px';
        item.style.height = targetHeight + 'px';

        const img = createLazyImg(photo, 'thumb');
        lazyObserver.observe(img);
        item.appendChild(img);

        // Show semantic pops
        if (photo.pops && photo.pops.length > 0) {
            const popWrap = document.createElement('div');
            popWrap.className = 'colors-pop-label';
            for (const pop of photo.pops) {
                popWrap.appendChild(createGlassTag(
                    pop.color + ' ' + pop.object,
                    { color: colorNameToCSS(pop.color) }
                ));
            }
            item.appendChild(popWrap);
        }

        item.addEventListener('click', () => openLightbox(photo));
        grid.appendChild(item);
    }

    wrap.appendChild(grid);
}

/* Resolve Apple system color from CSS variable */
const _rs = getComputedStyle(document.documentElement);
function colorNameToCSS(name) {
    const map = {
        'red': '--system-red',
        'orange': '--system-orange',
        'yellow': '--system-yellow',
        'green': '--system-green',
        'blue': '--system-blue',
        'purple': '--system-purple',
        'pink': '--system-pink',
        'brown': '--system-brown',
        'teal': '--system-teal',
        'cyan': '--system-cyan',
        'mint': '--system-mint',
        'indigo': '--system-indigo',
        'gray': '--system-gray',
        'grey': '--system-gray',
        'gold': '--system-yellow',
        'magenta': '--system-pink',
    };
    const varName = map[(name || '').toLowerCase()];
    if (varName) return _rs.getPropertyValue(varName).trim();
    /* Fallback for non-system colors */
    const fallbacks = {
        'black': '#1c1c1e', 'white': '#f2f2f7', 'silver': '#aeaeb2',
        'navy': '#2c3e6b', 'cream': '#fffdd0', 'beige': '#f5f5dc',
    };
    return fallbacks[(name || '').toLowerCase()] || _rs.getPropertyValue('--system-gray').trim();
}
