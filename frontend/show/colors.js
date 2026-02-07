/* colors.js — Les Couleurs: Chromatic bento — viewport-fixed color exploration.
   Click spectrum band to browse by dominant hue. Elevated card, no scroll. */

let colorBuckets = [];
let activeColorIdx = 0;

const NUM_BUCKETS = 24;
const _rs = getComputedStyle(document.documentElement);

function initCouleurs() {
    buildColorBuckets();

    /* Start with a random non-empty bucket */
    const nonEmpty = colorBuckets.map((b, i) => ({ b, i })).filter(x => x.b.photos.length > 0);
    activeColorIdx = nonEmpty.length > 0 ? randomFrom(nonEmpty).i : 0;

    const container = document.getElementById('view-couleurs');
    container.innerHTML = '';

    const wrap = document.createElement('div');
    wrap.className = 'couleurs-wrap';

    /* Spectrum bar */
    const spectrum = document.createElement('div');
    spectrum.className = 'couleurs-spectrum';
    spectrum.id = 'couleurs-spectrum';

    for (let i = 0; i < colorBuckets.length; i++) {
        const bucket = colorBuckets[i];
        const band = document.createElement('div');
        band.className = 'couleurs-band';
        if (i === activeColorIdx) band.classList.add('active');
        band.style.background = bucket.color;
        band.dataset.idx = i;
        band.addEventListener('click', () => selectCouleursBand(i));
        spectrum.appendChild(band);
    }

    wrap.appendChild(spectrum);

    /* Bento card */
    const card = document.createElement('div');
    card.className = 'couleurs-card';
    card.id = 'couleurs-card';
    wrap.appendChild(card);

    container.appendChild(wrap);
    renderCouleursBento();
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

    const grayPhotos = [];
    for (const photo of APP.data.photos) {
        if (!photo.thumb) continue;
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

function selectCouleursBand(idx) {
    activeColorIdx = idx;
    document.querySelectorAll('.couleurs-band').forEach((band, i) => {
        band.classList.toggle('active', i === idx);
    });
    renderCouleursBento();
}

function renderCouleursBento() {
    const card = document.getElementById('couleurs-card');
    if (!card) return;
    card.innerHTML = '';

    const bucket = colorBuckets[activeColorIdx];
    if (!bucket || bucket.photos.length === 0) {
        card.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--text-muted);font-size:14px">No photos in this range</div>';
        return;
    }

    /* Pick 8 from this bucket, highest aesthetic first */
    const sorted = [...bucket.photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
    let selected = sorted.slice(0, 8);

    /* Fill from adjacent buckets if needed */
    if (selected.length < 8) {
        const usedIds = new Set(selected.map(p => p.id));
        for (let offset = 1; offset <= 3 && selected.length < 8; offset++) {
            for (const dir of [-1, 1]) {
                const adjIdx = (activeColorIdx + dir * offset + colorBuckets.length) % colorBuckets.length;
                const adj = colorBuckets[adjIdx];
                if (!adj) continue;
                const adjSorted = [...adj.photos].sort((a, b) => (b.aesthetic || 0) - (a.aesthetic || 0));
                for (const p of adjSorted) {
                    if (selected.length >= 8) break;
                    if (!usedIds.has(p.id)) {
                        selected.push(p);
                        usedIds.add(p.id);
                    }
                }
            }
        }
    }

    selected = shuffleArray(selected);

    const mobile = window.matchMedia('(max-width: 768px)').matches;

    if (mobile) {
        /* 4 rows of 2 */
        const rows = [[0,1],[2,3],[4,5],[6,7]];
        for (const indices of rows) {
            const row = document.createElement('div');
            row.className = 'couleurs-row';
            for (const i of indices) {
                if (selected[i]) row.appendChild(makeCouleursTile(selected[i]));
            }
            card.appendChild(row);
        }
    } else {
        /* 2 rows of 4 */
        const rows = [[0,1,2,3],[4,5,6,7]];
        for (const indices of rows) {
            const row = document.createElement('div');
            row.className = 'couleurs-row';
            for (const i of indices) {
                if (selected[i]) row.appendChild(makeCouleursTile(selected[i]));
            }
            card.appendChild(row);
        }
    }
}

function makeCouleursTile(photo) {
    const tile = document.createElement('div');
    tile.className = 'couleurs-tile';

    const img = document.createElement('img');
    loadProgressive(img, photo, 'display');
    img.alt = '';
    tile.appendChild(img);

    tile.addEventListener('click', () => openLightbox(photo));
    return tile;
}
