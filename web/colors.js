/* colors.js — Les Couleurs: Color space exploration */

let colorsInitialized = false;
let colorBuckets = [];
let activeColorIdx = -1;

const NUM_BUCKETS = 24;

function initCouleurs() {
    if (colorsInitialized) return;
    colorsInitialized = true;

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

function buildColorBuckets() {
    colorBuckets = [];
    const bucketSize = 360 / NUM_BUCKETS;

    for (let i = 0; i < NUM_BUCKETS; i++) {
        const hueStart = i * bucketSize;
        const hueMid = hueStart + bucketSize / 2;
        colorBuckets.push({
            hueStart: hueStart,
            hueEnd: hueStart + bucketSize,
            color: `hsl(${hueMid}, 65%, 50%)`,
            photos: [],
        });
    }

    // Sort photos into buckets by dominant hue
    for (const photo of APP.data.photos) {
        const hue = photo.hue || 0;
        // Also check if the photo has very low saturation (grayscale)
        const palette = photo.palette || [];
        const isGray = palette.every(hex => {
            const r = parseInt(hex.slice(1, 3), 16);
            const g = parseInt(hex.slice(3, 5), 16);
            const b = parseInt(hex.slice(5, 7), 16);
            const max = Math.max(r, g, b);
            const min = Math.min(r, g, b);
            return (max - min) < 30;
        });

        if (isGray) {
            // Put grays in a special bucket (add after the loop)
            continue;
        }

        const idx = Math.min(Math.floor(hue / (360 / NUM_BUCKETS)), NUM_BUCKETS - 1);
        colorBuckets[idx].photos.push(photo);
    }

    // Add grayscale bucket
    const grayPhotos = APP.data.photos.filter(photo => {
        const palette = photo.palette || [];
        return palette.length > 0 && palette.every(hex => {
            if (hex.length < 7) return true;
            const r = parseInt(hex.slice(1, 3), 16);
            const g = parseInt(hex.slice(3, 5), 16);
            const b = parseInt(hex.slice(5, 7), 16);
            const max = Math.max(r, g, b);
            const min = Math.min(r, g, b);
            return (max - min) < 30;
        });
    });

    if (grayPhotos.length > 0) {
        colorBuckets.push({
            hueStart: -1,
            hueEnd: -1,
            color: '#666666',
            photos: grayPhotos,
        });
    }

    // Remove empty buckets from spectrum (but keep indexes stable for click)
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
    grid.style.display = 'flex';
    grid.style.flexWrap = 'wrap';
    grid.style.gap = '4px';

    const targetHeight = 160;

    for (const photo of sorted) {
        const aspect = photo.aspect || 1.5;
        const width = Math.floor(aspect * targetHeight);

        const item = document.createElement('div');
        item.className = 'colors-grid-item';
        item.style.width = width + 'px';
        item.style.height = targetHeight + 'px';
        item.style.flexGrow = '1';

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
                    { color: colorNameToHex(pop.color) }
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
    swatch.style.display = 'inline-block';
    swatch.style.width = '10px';
    swatch.style.height = '10px';
    swatch.style.borderRadius = '50%';
    swatch.style.background = bucket.color;
    swatch.style.marginRight = '8px';
    swatch.style.verticalAlign = 'middle';
    title.appendChild(swatch);
    title.appendChild(document.createTextNode(
        photos.length + ' photos with this dominant color'
    ));
    wrap.appendChild(title);

    if (photos.length === 0) {
        const empty = document.createElement('div');
        empty.style.padding = '40px';
        empty.style.color = 'var(--text-muted)';
        empty.style.textAlign = 'center';
        empty.textContent = 'No photos in this color range.';
        wrap.appendChild(empty);
        return;
    }

    const grid = document.createElement('div');
    grid.className = 'colors-grid';
    grid.style.display = 'flex';
    grid.style.flexWrap = 'wrap';
    grid.style.gap = '6px';

    const targetHeight = 220;

    for (const photo of photos) {
        const aspect = photo.aspect || 1.5;
        const width = Math.floor(aspect * targetHeight);

        const item = document.createElement('div');
        item.className = 'colors-grid-item';
        item.style.width = width + 'px';
        item.style.height = targetHeight + 'px';
        item.style.flexGrow = '1';

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
                    { color: colorNameToHex(pop.color) }
                ));
            }
            item.appendChild(popWrap);
        }

        item.addEventListener('click', () => openLightbox(photo));
        grid.appendChild(item);
    }

    wrap.appendChild(grid);
}

function colorNameToHex(name) {
    const map = {
        'red': '#e74c3c',
        'orange': '#e67e22',
        'yellow': '#f1c40f',
        'green': '#2ecc71',
        'blue': '#3498db',
        'purple': '#9b59b6',
        'pink': '#e91e8b',
        'brown': '#8b6914',
        'black': '#2c3e50',
        'white': '#ecf0f1',
        'gray': '#95a5a6',
        'grey': '#95a5a6',
        'gold': '#f39c12',
        'silver': '#bdc3c7',
        'teal': '#1abc9c',
        'cyan': '#00bcd4',
        'magenta': '#e91e63',
        'cream': '#fffdd0',
        'beige': '#f5f5dc',
        'navy': '#2c3e6b',
    };
    return map[(name || '').toLowerCase()] || '#888888';
}
