/* game.js — Le Jeu: Curated image pairs, viewport-fixed.
   Two images, same ratio, thumbs up/down on fixed glass bar.
   Rotating strategies produce diverse pair pools.
   👍 saves pair to favorites (localStorage). */

let jeuState = null;

const JEU_FAV_KEY = 'sq-couple-favs';
const JEU_FAV_MAX = 200;
const JEU_REJECT_KEY = 'sq-couple-rejects';

/* ===== Rejected Photos ===== */

function getJeuRejects() {
    try {
        return new Set(JSON.parse(localStorage.getItem(JEU_REJECT_KEY)) || []);
    } catch { return new Set(); }
}

function addJeuReject(photoId) {
    const rejects = getJeuRejects();
    rejects.add(photoId);
    localStorage.setItem(JEU_REJECT_KEY, JSON.stringify([...rejects]));

    /* Fire-and-forget Firestore write */
    try {
        if (typeof db !== 'undefined') {
            db.collection('couple-rejects').add({
                photo: photoId,
                ts: firebase.firestore.FieldValue.serverTimestamp()
            });
        }
    } catch (e) { /* silent */ }

    /* Remove all pairs containing this photo from current pool */
    if (jeuState && jeuState.pool) {
        jeuState.pool = jeuState.pool.filter(p => p.a.id !== photoId && p.b.id !== photoId);
        if (jeuState.index >= jeuState.pool.length) jeuState.index = 0;
    }
}

function addJeuApprove(photoId) {
    /* Fire-and-forget Firestore write — positive signal on individual photo */
    try {
        if (typeof db !== 'undefined') {
            db.collection('couple-approves').add({
                photo: photoId,
                ts: firebase.firestore.FieldValue.serverTimestamp()
            });
        }
    } catch (e) { /* silent */ }
}

/* ===== Strategy Registry ===== */

const JEU_STRATEGIES = [
    /* ─── Harmony ─── */
    {
        id: 'twins', name: 'Twins', subtitle: 'Uncanny resemblance',
        icon: '\uD83E\uDEDE', type: 'harmony', needsDrift: true,
        build(photos, photoMap, drift) {
            /* DINOv2+CLIP visual similarity — best performer, keep tight threshold */
            const pairs = [], seen = new Set();
            if (!drift) return pairs;
            for (const [id, neighbors] of Object.entries(drift)) {
                const a = photoMap[id];
                if (!a || !a.thumb || (a.aesthetic || 0) < 9.5) continue;
                /* Use top 3 neighbors instead of just top 1 */
                for (const nb of neighbors.slice(0, 3)) {
                    if (!nb || nb.score < 0.60) continue;
                    const b = photoMap[nb.id];
                    if (!b || !b.thumb || (b.aesthetic || 0) < 9.5) continue;
                    const key = canonKey(a.id, b.id);
                    if (seen.has(key)) continue;
                    seen.add(key);
                    pairs.push({ a, b, reason: `drift ${nb.score.toFixed(2)}` });
                }
            }
            return pairs;
        }
    },
    {
        id: 'chromatic', name: 'Chromatic', subtitle: 'Same palette, different subject',
        icon: '\uD83C\uDFA8', type: 'harmony',
        build(photos, photoMap) {
            /* Match on hue + similar brightness + similar contrast = visually cohesive color pairs */
            const buckets = {};
            for (const p of photos) {
                if (p.mono || p.hue == null || (p.aesthetic || 0) < 9.5) continue;
                const bucket = Math.floor(p.hue / 15) % 24;
                (buckets[bucket] = buckets[bucket] || []).push(p);
            }
            const pairs = [], seen = new Set();
            for (const group of Object.values(buckets)) {
                if (group.length < 2) continue;
                const shuffled = shuffleArray([...group]);
                for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
                    const a = shuffled[i];
                    for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
                        const b = shuffled[j];
                        if (a.scene === b.scene) continue;
                        /* Require similar brightness (within 20) AND similar contrast (within 15) */
                        if (Math.abs((a.brightness || 50) - (b.brightness || 50)) > 20) continue;
                        if (Math.abs((a.contrast || 50) - (b.contrast || 50)) > 15) continue;
                        const key = canonKey(a.id, b.id);
                        if (seen.has(key)) continue;
                        seen.add(key);
                        pairs.push({ a, b, reason: `${hueLabel(a.hue)} ~${Math.round(a.hue)}\u00B0` });
                        break;
                    }
                }
            }
            return pairs;
        }
    },
    {
        id: 'texture', name: 'Texture', subtitle: 'Same feel, same gaze',
        icon: '\uD83E\uDDF5', type: 'harmony',
        build(photos, photoMap) {
            /* depth + composition + similar depth_complexity + same style = real texture match */
            const buckets = {};
            for (const p of photos) {
                if (!p.depth || !p.composition || !p.style || (p.aesthetic || 0) < 9.5) continue;
                const key = p.depth + '|' + p.composition + '|' + p.style;
                (buckets[key] = buckets[key] || []).push(p);
            }
            const pairs = [], seen = new Set();
            for (const group of Object.values(buckets)) {
                if (group.length < 2) continue;
                const shuffled = shuffleArray([...group]);
                for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
                    const a = shuffled[i];
                    for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
                        const b = shuffled[j];
                        if (Math.abs((a.depth_complexity || 0) - (b.depth_complexity || 0)) > 0.3) continue;
                        if (a.scene === b.scene) continue; /* different subjects */
                        const key = canonKey(a.id, b.id);
                        if (seen.has(key)) continue;
                        seen.add(key);
                        pairs.push({ a, b, reason: `${a.style} \u2014 ${a.depth}, ${a.composition}` });
                        break;
                    }
                }
            }
            return pairs;
        }
    },
    {
        id: 'timewarp', name: 'Time Warp', subtitle: 'Years apart, same spirit',
        icon: '\u23F3', type: 'harmony',
        build(photos, photoMap) {
            /* Same scene + same style + 3+ years apart = real time warp */
            const buckets = {};
            for (const p of photos) {
                if (!p.date || !p.scene || !p.style || (p.aesthetic || 0) < 9.5) continue;
                const key = p.scene + '|' + p.style;
                (buckets[key] = buckets[key] || []).push(p);
            }
            const pairs = [], seen = new Set();
            for (const group of Object.values(buckets)) {
                if (group.length < 2) continue;
                const sorted = [...group].sort((a, b) => a.date.localeCompare(b.date));
                for (let i = 0; i < sorted.length - 1 && pairs.length < 500; i++) {
                    const a = sorted[i];
                    for (let j = sorted.length - 1; j > i && pairs.length < 500; j--) {
                        const b = sorted[j];
                        const ya = new Date(a.date).getFullYear();
                        const yb = new Date(b.date).getFullYear();
                        if (Math.abs(yb - ya) < 3) continue;
                        /* Require similar brightness for visual cohesion */
                        if (Math.abs((a.brightness || 50) - (b.brightness || 50)) > 25) continue;
                        const key = canonKey(a.id, b.id);
                        if (seen.has(key)) continue;
                        seen.add(key);
                        pairs.push({ a, b, reason: `${a.scene}, ${a.style} \u2014 ${ya} \u2194 ${yb}` });
                        break;
                    }
                }
            }
            return pairs;
        }
    },
    {
        id: 'solitude', name: 'Solitude', subtitle: 'Quiet frames, same world',
        icon: '\uD83C\uDF2C\uFE0F', type: 'harmony',
        build(photos, photoMap) {
            /* Empty frames that share scene + similar brightness + similar saliency position */
            const lonely = photos.filter(p =>
                (p.aesthetic || 0) >= 9.5 &&
                (p.face_count || 0) === 0 &&
                !(p.objects || []).includes('person') &&
                p.saliency && p.saliency.spread < 16 &&
                p.scene && p.depth
            );
            /* Bucket by scene for thematic coherence */
            const buckets = {};
            for (const p of lonely) {
                (buckets[p.scene] = buckets[p.scene] || []).push(p);
            }
            const pairs = [], seen = new Set();
            for (const group of Object.values(buckets)) {
                if (group.length < 2) continue;
                const shuffled = shuffleArray([...group]);
                for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
                    const a = shuffled[i];
                    for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
                        const b = shuffled[j];
                        if (Math.abs((a.brightness || 50) - (b.brightness || 50)) > 20) continue;
                        /* Require same depth for visual consistency */
                        if (a.depth !== b.depth) continue;
                        const key = canonKey(a.id, b.id);
                        if (seen.has(key)) continue;
                        seen.add(key);
                        pairs.push({ a, b, reason: `${a.scene} \u2014 quiet, ${a.depth}` });
                        break;
                    }
                }
            }
            return pairs;
        }
    },
    {
        id: 'moodring', name: 'Mood Ring', subtitle: 'Same emotion, same place, different eye',
        icon: '\uD83D\uDE36\u200D\uD83C\uDF2B\uFE0F', type: 'harmony',
        build(photos, photoMap) {
            /* emotion + scene + different style/camera = meaningful emotional pairing */
            const buckets = {};
            for (const p of photos) {
                if (!p.emotion || !p.scene || (p.aesthetic || 0) < 9.5) continue;
                const key = p.emotion + '|' + p.scene;
                (buckets[key] = buckets[key] || []).push(p);
            }
            const pairs = [], seen = new Set();
            for (const [bucket, group] of Object.entries(buckets)) {
                if (group.length < 2) continue;
                const shuffled = shuffleArray([...group]);
                for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
                    const a = shuffled[i];
                    for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
                        const b = shuffled[j];
                        /* Must differ in camera OR style */
                        if (a.camera === b.camera && a.style === b.style) continue;
                        const key = canonKey(a.id, b.id);
                        if (seen.has(key)) continue;
                        seen.add(key);
                        const [emotion, scene] = bucket.split('|');
                        pairs.push({ a, b, reason: `${emotion} \u2014 ${scene}` });
                        break;
                    }
                }
            }
            return pairs;
        }
    },

    /* ─── Tension ─── */
    {
        id: 'complement', name: 'Complement', subtitle: 'Opposite colors, shared soul',
        icon: '\uD83C\uDF08', type: 'tension',
        build(photos, photoMap) {
            /* Opposite hues (150-210 apart) + shared vibe = color tension with thematic link */
            const colored = photos.filter(p => !p.mono && p.hue != null && (p.aesthetic || 0) >= 9.5);
            const pairs = [], seen = new Set();
            const shuffled = shuffleArray([...colored]);
            for (let i = 0; i < shuffled.length && pairs.length < 500; i++) {
                const a = shuffled[i];
                for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
                    const b = shuffled[j];
                    const diff = hueDiff(a.hue, b.hue);
                    if (diff < 150 || diff > 210) continue;
                    /* Require shared vibe for thematic connection */
                    const sharedVibe = (a.vibes || []).find(v => (b.vibes || []).includes(v));
                    if (!sharedVibe) continue;
                    const key = canonKey(a.id, b.id);
                    if (seen.has(key)) continue;
                    seen.add(key);
                    pairs.push({ a, b, reason: `${hueLabel(a.hue)} \u2194 ${hueLabel(b.hue)} \u2014 ${sharedVibe}` });
                    break;
                }
            }
            return pairs;
        }
    },
    {
        id: 'strangers', name: 'Strangers', subtitle: 'Same place, different world',
        icon: '\uD83D\uDC65', type: 'tension',
        build(photos, photoMap) {
            /* Same scene + different style + different time + similar composition = same spot, different photographer */
            const buckets = {};
            for (const p of photos) {
                if (!p.scene || !p.style || !p.composition || (p.aesthetic || 0) < 9.5) continue;
                (buckets[p.scene] = buckets[p.scene] || []).push(p);
            }
            const pairs = [], seen = new Set();
            for (const group of Object.values(buckets)) {
                if (group.length < 2) continue;
                const shuffled = shuffleArray([...group]);
                for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
                    const a = shuffled[i];
                    for (let j = i + 1; j < shuffled.length; j++) {
                        const b = shuffled[j];
                        /* Must differ in at least 2 of: time, style, grading */
                        let diffs = 0;
                        if (a.time !== b.time) diffs++;
                        if (a.style !== b.style) diffs++;
                        if (a.grading !== b.grading) diffs++;
                        if (diffs < 2) continue;
                        /* Same composition anchors the visual connection */
                        if (a.composition !== b.composition) continue;
                        const key = canonKey(a.id, b.id);
                        if (seen.has(key)) continue;
                        seen.add(key);
                        pairs.push({ a, b, reason: `${a.scene} \u2014 ${a.style} vs ${b.style}` });
                        break;
                    }
                }
            }
            return pairs;
        }
    },
    {
        id: 'lightdark', name: 'Light & Dark', subtitle: 'Brightness extremes',
        icon: '\u25D1', type: 'tension',
        build(photos, photoMap) {
            /* Top/bottom 15% brightness + shared scene or object = keep (already works well) */
            const quality = photos.filter(p => p.brightness != null && (p.aesthetic || 0) >= 9.5);
            const sorted = [...quality].sort((a, b) => a.brightness - b.brightness);
            const cut = Math.floor(sorted.length * 0.15);
            const darks = sorted.slice(0, cut);
            const lights = sorted.slice(-cut);
            const pairs = [], seen = new Set();
            const shuffledD = shuffleArray([...darks]);
            const shuffledL = shuffleArray([...lights]);
            for (let i = 0; i < shuffledD.length && pairs.length < 500; i++) {
                const a = shuffledD[i];
                for (let j = 0; j < shuffledL.length && pairs.length < 500; j++) {
                    const b = shuffledL[j];
                    /* Prefer scene match, fallback to shared vibe+object */
                    const sharedScene = a.scene && a.scene === b.scene;
                    const sharedVibe = (a.vibes || []).some(v => (b.vibes || []).includes(v));
                    const sharedObj = (a.objects || []).some(o => (b.objects || []).includes(o));
                    if (!sharedScene && !(sharedVibe && sharedObj)) continue;
                    const key = canonKey(a.id, b.id);
                    if (seen.has(key)) continue;
                    seen.add(key);
                    const link = sharedScene ? a.scene : '';
                    pairs.push({ a, b, reason: `${Math.round(a.brightness)} vs ${Math.round(b.brightness)}${link ? ' \u2014 ' + link : ''}` });
                    break;
                }
            }
            return pairs;
        }
    },
    {
        id: 'doppelganger', name: 'Doppelganger', subtitle: 'Same object, different world',
        icon: '\uD83E\uDE9E', type: 'tension',
        build(photos, photoMap) {
            /* Shared specific object + different scene + similar depth = object in two worlds */
            const skip = new Set([
                'person', 'car', 'tree', 'building', 'sky', 'wall', 'floor', 'window',
                'traffic light', 'truck', 'couch', 'chair', 'tv', 'bus', 'bed'
            ]);
            const buckets = {};
            for (const p of photos) {
                if ((p.aesthetic || 0) < 9.5 || !p.depth) continue;
                for (const obj of (p.objects || [])) {
                    if (skip.has(obj)) continue;
                    (buckets[obj] = buckets[obj] || []).push(p);
                }
            }
            const pairs = [], seen = new Set();
            for (const [obj, group] of Object.entries(buckets)) {
                if (group.length < 2 || group.length > 200) continue; /* skip overly common objects */
                const shuffled = shuffleArray([...group]);
                for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
                    const a = shuffled[i];
                    for (let j = i + 1; j < shuffled.length; j++) {
                        const b = shuffled[j];
                        if (a.scene === b.scene) continue;
                        /* Same depth type for visual consistency */
                        if (a.depth !== b.depth) continue;
                        const key = canonKey(a.id, b.id);
                        if (seen.has(key)) continue;
                        seen.add(key);
                        pairs.push({ a, b, reason: `${obj} \u2014 ${a.scene} vs ${b.scene}` });
                        break;
                    }
                }
            }
            return pairs;
        }
    },
    {
        id: 'monochrome', name: 'Monochrome', subtitle: 'Color meets its shadow',
        icon: '\u25AB\u25AA', type: 'tension',
        build(photos, photoMap) {
            /* B&W + color sharing SAME SCENE + similar composition = strong mono/color tension */
            const monos = photos.filter(p => p.mono && p.scene && p.composition && (p.aesthetic || 0) >= 9.5);
            const colorByScene = {};
            for (const p of photos) {
                if (p.mono || !p.scene || !p.composition || (p.aesthetic || 0) < 9.5) continue;
                (colorByScene[p.scene] = colorByScene[p.scene] || []).push(p);
            }
            const pairs = [], seen = new Set();
            const shuffledM = shuffleArray([...monos]);
            for (const a of shuffledM) {
                const candidates = colorByScene[a.scene];
                if (!candidates) continue;
                for (const b of shuffleArray([...candidates])) {
                    /* Same composition anchors the pairing visually */
                    if (a.composition !== b.composition) continue;
                    const key = canonKey(a.id, b.id);
                    if (seen.has(key)) continue;
                    seen.add(key);
                    pairs.push({ a, b, reason: `mono \u00D7 color \u2014 ${a.scene}, ${a.composition}` });
                    break;
                }
                if (pairs.length >= 500) break;
            }
            return pairs;
        }
    },

    /* ─── Format ─── */
    {
        id: 'bento', name: 'Bento', subtitle: 'Portrait meets landscape',
        icon: '\uD83C\uDFDE\uFE0F', type: 'tension',
        build(photos, photoMap) {
            /* Portrait + landscape sharing scene + style = strong format contrast with thematic unity */
            const portraits = photos.filter(p => p.orientation === 'portrait' && p.scene && p.style && (p.aesthetic || 0) >= 9.5);
            const lsBySceneStyle = {};
            for (const p of photos) {
                if (p.orientation !== 'landscape' || !p.scene || !p.style || (p.aesthetic || 0) < 9.5) continue;
                const key = p.scene + '|' + p.style;
                (lsBySceneStyle[key] = lsBySceneStyle[key] || []).push(p);
            }
            const pairs = [], seen = new Set();
            const shuffledP = shuffleArray([...portraits]);
            for (const a of shuffledP) {
                const k = a.scene + '|' + a.style;
                const candidates = lsBySceneStyle[k];
                if (!candidates) continue;
                for (const b of shuffleArray([...candidates])) {
                    const key = canonKey(a.id, b.id);
                    if (seen.has(key)) continue;
                    seen.add(key);
                    pairs.push({ a, b, reason: `portrait \u00D7 landscape \u2014 ${a.scene}, ${a.style}` });
                    break;
                }
                if (pairs.length >= 500) break;
            }
            return pairs;
        }
    },

    /* ─── Special ─── */
    {
        id: 'focal', name: 'Focal Point', subtitle: 'Same gaze, different frame',
        icon: '\uD83C\uDFAF', type: 'special',
        build(photos, photoMap) {
            /* Same saliency position quadrant + same depth + different scene = eyes land in the same spot */
            const withSaliency = photos.filter(p =>
                (p.aesthetic || 0) >= 9.5 && p.saliency && p.depth && p.scene
            );
            /* Bucket by saliency quadrant + depth */
            const buckets = {};
            for (const p of withSaliency) {
                const qx = p.saliency.px < 0.5 ? 'L' : 'R';
                const qy = p.saliency.py < 0.5 ? 'T' : 'B';
                const key = qx + qy + '|' + p.depth;
                (buckets[key] = buckets[key] || []).push(p);
            }
            const pairs = [], seen = new Set();
            for (const group of Object.values(buckets)) {
                if (group.length < 2) continue;
                const shuffled = shuffleArray([...group]);
                for (let i = 0; i < shuffled.length - 1 && pairs.length < 500; i++) {
                    const a = shuffled[i];
                    for (let j = i + 1; j < shuffled.length && pairs.length < 500; j++) {
                        const b = shuffled[j];
                        if (a.scene === b.scene) continue;
                        /* Tight saliency position match */
                        const spDist = Math.hypot(
                            (a.saliency.px - b.saliency.px),
                            (a.saliency.py - b.saliency.py)
                        );
                        if (spDist > 0.2) continue;
                        /* Similar brightness for visual harmony */
                        if (Math.abs((a.brightness || 50) - (b.brightness || 50)) > 20) continue;
                        const key = canonKey(a.id, b.id);
                        if (seen.has(key)) continue;
                        seen.add(key);
                        pairs.push({ a, b, reason: `focal match \u2014 ${a.depth}` });
                        break;
                    }
                }
            }
            return pairs;
        }
    },
];

/* ===== Pair Helpers ===== */

function canonKey(idA, idB) {
    return idA < idB ? idA + '|' + idB : idB + '|' + idA;
}

function hueDiff(h1, h2) {
    const d = Math.abs(h1 - h2);
    return d > 180 ? 360 - d : d;
}

function hueLabel(h) {
    if (h < 15 || h >= 345) return 'red';
    if (h < 45) return 'orange';
    if (h < 75) return 'yellow';
    if (h < 150) return 'green';
    if (h < 210) return 'cyan';
    if (h < 270) return 'blue';
    if (h < 330) return 'purple';
    return 'pink';
}

/* ===== Favorites ===== */

function getJeuFavs() {
    try {
        return JSON.parse(localStorage.getItem(JEU_FAV_KEY)) || [];
    } catch { return []; }
}

function setJeuFavs(favs) {
    localStorage.setItem(JEU_FAV_KEY, JSON.stringify(favs.slice(-JEU_FAV_MAX)));
}

function saveFavPair(pair) {
    const favs = getJeuFavs();
    /* Avoid duplicates */
    const exists = favs.some(f => (f.a === pair.a.id && f.b === pair.b.id) || (f.a === pair.b.id && f.b === pair.a.id));
    if (!exists) {
        favs.push({ a: pair.a.id, b: pair.b.id });
        setJeuFavs(favs);
    }
    updateJeuFavBadge();

    /* Fire-and-forget Firestore write for anonymous aggregation */
    try {
        if (typeof db !== 'undefined') {
            db.collection('couple-likes').add({
                a: pair.a.id,
                b: pair.b.id,
                strategy: pair.strategy || 'unknown',
                ts: firebase.firestore.FieldValue.serverTimestamp()
            });
        }
    } catch (e) { /* silent — localStorage is the primary store */ }

    /* Pulse feedback on 👍 button */
    const upBtn = document.getElementById('jeu-up-btn');
    if (upBtn) {
        upBtn.classList.add('jeu-btn-pulse');
        upBtn.addEventListener('animationend', () => upBtn.classList.remove('jeu-btn-pulse'), { once: true });
    }
}

function updateJeuFavBadge() {
    const badge = document.getElementById('jeu-fav-badge');
    if (!badge) return;
    const count = getJeuFavs().length;
    badge.textContent = count;
    badge.style.display = count > 0 ? '' : 'none';
}

/* ===== Build All Strategies ===== */

async function buildAllPairs() {
    const rejects = getJeuRejects();
    const allPhotos = APP.data.photos.filter(p => p.thumb && !rejects.has(p.id));

    /* Camera-diverse sampling: cap each camera at 1200 photos max.
       This prevents DJI Osmo Pro (32%) and Leica M8 (41%) from dominating. */
    const CAM_CAP = 1200;
    const byCam = {};
    for (const p of allPhotos) {
        const cam = p.camera || 'unknown';
        (byCam[cam] = byCam[cam] || []).push(p);
    }
    const photos = [];
    for (const [cam, group] of Object.entries(byCam)) {
        if (group.length <= CAM_CAP) {
            photos.push(...group);
        } else {
            photos.push(...shuffleArray([...group]).slice(0, CAM_CAP));
        }
    }
    console.log(`[Couple] Diverse pool: ${photos.length} photos (from ${allPhotos.length}, ${rejects.size} rejected, ${Object.keys(byCam).length} cameras capped at ${CAM_CAP})`);

    const photoMap = APP.photoMap;
    const drift = await loadDriftNeighbors();
    const all = [];

    /* Yield between strategies to avoid blocking the main thread.
       Each strategy can take 20-80ms; running 13 back-to-back blocks for 200-800ms. */
    for (const strat of JEU_STRATEGIES) {
        await new Promise(r => setTimeout(r, 0)); /* yield to paint/input */
        const t0 = performance.now();
        const pool = strat.build(photos, photoMap, strat.needsDrift ? drift : null);
        const ms = (performance.now() - t0).toFixed(1);
        for (const pair of pool) pair.strategy = strat.id;
        console.log(`[Couple] ${strat.id}: ${pool.length} pairs (${ms}ms)`);
        all.push(...pool);
    }

    /* Global dedup: cap each photo to max 3 appearances across all pairs.
       This ensures wide sampling — no single photo dominates the feed. */
    const appearances = {};
    const MAX_APPEARANCES = 3;
    const deduped = shuffleArray(all).filter(pair => {
        const cA = appearances[pair.a.id] = (appearances[pair.a.id] || 0) + 1;
        const cB = appearances[pair.b.id] = (appearances[pair.b.id] || 0) + 1;
        return cA <= MAX_APPEARANCES && cB <= MAX_APPEARANCES;
    });

    console.log(`[Couple] Total: ${deduped.length} pairs (from ${all.length} raw) across ${JEU_STRATEGIES.length} strategies`);
    return deduped;
}

/* ===== Init ===== */

function initGame() {
    const container = document.getElementById('view-game');
    container.innerHTML = '';

    jeuState = { pool: [], index: 0 };

    /* Build persistent structure */
    const wrap = document.createElement('div');
    wrap.className = 'jeu-container';

    /* Pair area */
    const pairEl = document.createElement('div');
    pairEl.className = 'jeu-pair';
    pairEl.id = 'jeu-pair';
    wrap.appendChild(pairEl);

    /* Touch/swipe support for mobile */
    let touchStartX = 0, touchStartY = 0;
    wrap.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; touchStartY = e.touches[0].clientY; }, {passive: true});
    wrap.addEventListener('touchend', e => {
        const dx = e.changedTouches[0].clientX - touchStartX;
        const dy = e.changedTouches[0].clientY - touchStartY;
        if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 50) {
            nextJeuPair();
        }
    }, {passive: true});

    /* Fixed glass bar */
    const bar = document.createElement('div');
    bar.className = 'jeu-bar';

    /* 👎 Skip */
    const downBtn = document.createElement('button');
    downBtn.className = 'jeu-btn';
    downBtn.textContent = '\uD83D\uDC4E';
    downBtn.addEventListener('click', () => nextJeuPair());
    bar.appendChild(downBtn);

    /* ❤️ Saved — center button with badge */
    const favBtn = document.createElement('button');
    favBtn.className = 'jeu-btn jeu-fav-btn';
    favBtn.innerHTML = '\u2764\uFE0F';
    favBtn.addEventListener('click', () => openJeuFavsOverlay());

    const badge = document.createElement('span');
    badge.className = 'jeu-fav-badge';
    badge.id = 'jeu-fav-badge';
    badge.style.display = 'none';
    favBtn.appendChild(badge);
    bar.appendChild(favBtn);

    /* 👍 Like */
    const upBtn = document.createElement('button');
    upBtn.className = 'jeu-btn';
    upBtn.id = 'jeu-up-btn';
    upBtn.textContent = '\uD83D\uDC4D';
    upBtn.addEventListener('click', () => {
        const pair = jeuState.pool[jeuState.index];
        if (pair) saveFavPair(pair);
        nextJeuPair();
    });
    bar.appendChild(upBtn);

    wrap.appendChild(bar);
    container.appendChild(wrap);

    updateJeuFavBadge();

    /* Build all strategy pairs, shuffle, render */
    buildAllPairs().then(pool => {
        jeuState.pool = pool;
        renderJeuPair();
    });
}

/* ===== Navigation ===== */

function nextJeuPair() {
    const pairEl = document.getElementById('jeu-pair');
    if (!pairEl) return;

    pairEl.classList.add('jeu-pair-exit');

    setTimeout(() => {
        jeuState.index++;
        renderJeuPair();
    }, 300);
}

/* ===== Render ===== */

function renderJeuPair() {
    const pairEl = document.getElementById('jeu-pair');
    if (!pairEl) return;

    const js = jeuState;
    if (js.index >= js.pool.length) {
        js.index = 0;
        js.pool = shuffleArray(js.pool);
    }

    const pair = js.pool[js.index];
    if (!pair) return;

    pairEl.innerHTML = '';
    pairEl.classList.remove('jeu-pair-exit', 'jeu-pair-bento', 'jeu-pair-bento-flip');
    pairEl.classList.add('jeu-pair-enter');

    /* Detect mixed orientations for bento layout */
    const oA = pair.a.orientation, oB = pair.b.orientation;
    const mixed = oA && oB && oA !== oB;
    let ordered = [pair.a, pair.b];
    if (mixed) {
        /* Randomize which side the portrait lands on */
        const portraitFirst = Math.random() < 0.5;
        const portrait = oA === 'portrait' ? pair.a : pair.b;
        const landscape = oA === 'portrait' ? pair.b : pair.a;
        ordered = portraitFirst ? [portrait, landscape] : [landscape, portrait];
        pairEl.classList.add('jeu-pair-bento');
        if (!portraitFirst) pairEl.classList.add('jeu-pair-bento-flip');
    }

    for (const photo of ordered) {
        const card = document.createElement('div');
        card.className = 'jeu-card';
        const img = document.createElement('img');
        const orient = photo.orientation === 'portrait' ? 'jeu-img-portrait' : 'jeu-img-landscape';
        img.className = `jeu-img clickable-img${mixed ? ' ' + orient : ''}`;
        loadProgressive(img, photo, 'display');
        img.alt = '';
        img.addEventListener('click', () => openLightbox(photo));
        card.appendChild(img);

        /* Hover approve/reject buttons (desktop only) */
        const actions = document.createElement('div');
        actions.className = 'jeu-card-actions';

        const rejectBtn = document.createElement('button');
        rejectBtn.className = 'jeu-card-btn jeu-card-reject';
        rejectBtn.innerHTML = '\u2715';
        rejectBtn.title = 'Reject this photo';
        rejectBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            card.classList.add('jeu-card-rejected');
            addJeuReject(photo.id);
            setTimeout(() => nextJeuPair(), 400);
        });

        const approveBtn = document.createElement('button');
        approveBtn.className = 'jeu-card-btn jeu-card-approve';
        approveBtn.innerHTML = '\u2713';
        approveBtn.title = 'Good photo';
        approveBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            card.classList.add('jeu-card-approved');
            addJeuApprove(photo.id);
            setTimeout(() => card.classList.remove('jeu-card-approved'), 600);
        });

        actions.appendChild(rejectBtn);
        actions.appendChild(approveBtn);
        card.appendChild(actions);

        pairEl.appendChild(card);
    }

    /* Remove enter class after animation */
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            pairEl.classList.remove('jeu-pair-enter');
        });
    });
}

/* ===== Favorites overlay ===== */

function openJeuFavsOverlay() {
    /* Remove existing */
    const existing = document.getElementById('jeu-favs-overlay');
    if (existing) { existing.remove(); return; }

    const favs = getJeuFavs();

    const overlay = document.createElement('div');
    overlay.className = 'jeu-favs-overlay';
    overlay.id = 'jeu-favs-overlay';

    const inner = document.createElement('div');
    inner.className = 'jeu-favs-inner';

    /* Header */
    const header = document.createElement('div');
    header.className = 'jeu-favs-header';

    const title = document.createElement('span');
    title.textContent = 'Saved Pairs (' + favs.length + ')';
    header.appendChild(title);

    const closeBtn = document.createElement('button');
    closeBtn.className = 'jeu-favs-close';
    closeBtn.textContent = '\u2715';
    closeBtn.addEventListener('click', () => overlay.remove());
    header.appendChild(closeBtn);

    inner.appendChild(header);

    /* List of saved pairs */
    if (favs.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'jeu-favs-empty';
        empty.textContent = 'No saved pairs yet. Tap \uD83D\uDC4D to save pairs you like!';
        inner.appendChild(empty);
    } else {
        const list = document.createElement('div');
        list.className = 'jeu-favs-list';

        for (let i = favs.length - 1; i >= 0; i--) {
            const fav = favs[i];
            const photoA = APP.photoMap[fav.a];
            const photoB = APP.photoMap[fav.b];
            if (!photoA || !photoB) continue;

            const row = document.createElement('div');
            row.className = 'jeu-fav-row';

            for (const photo of [photoA, photoB]) {
                const thumb = document.createElement('img');
                thumb.className = 'jeu-fav-thumb';
                loadProgressive(thumb, photo, 'thumb');
                thumb.alt = '';
                thumb.addEventListener('click', () => openLightbox(photo));
                row.appendChild(thumb);
            }

            const removeBtn = document.createElement('button');
            removeBtn.className = 'jeu-fav-remove';
            removeBtn.textContent = '\u2715';
            removeBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                const updated = getJeuFavs().filter(f => !(f.a === fav.a && f.b === fav.b));
                setJeuFavs(updated);
                row.remove();
                updateJeuFavBadge();
                title.textContent = 'Saved Pairs (' + updated.length + ')';
                if (updated.length === 0) {
                    list.remove();
                    const empty = document.createElement('div');
                    empty.className = 'jeu-favs-empty';
                    empty.textContent = 'No saved pairs yet. Tap \uD83D\uDC4D to save pairs you like!';
                    inner.appendChild(empty);
                }
            });
            row.appendChild(removeBtn);

            list.appendChild(row);
        }
        inner.appendChild(list);
    }

    /* Clear all button */
    if (favs.length > 0) {
        const clearBtn = document.createElement('button');
        clearBtn.className = 'jeu-favs-clear';
        clearBtn.textContent = 'Clear All';
        clearBtn.addEventListener('click', () => {
            setJeuFavs([]);
            updateJeuFavBadge();
            overlay.remove();
        });
        inner.appendChild(clearBtn);
    }

    overlay.appendChild(inner);

    /* Close on backdrop click */
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) overlay.remove();
    });

    document.getElementById('view-game').appendChild(overlay);
}
