/* sw.js — Service Worker for MADphotos Show.
   Caches static assets (JS, CSS, HTML) for offline use.
   Images use a 3-tier runtime cache with LRU eviction. */

const CACHE_NAME = 'madphotos-v40';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/style.css?v=73',
    '/app.js?v=73',
    '/theme.js?v=73',
    '/colors.js?v=73',
    '/bento.js?v=73',
    '/game.js?v=73',
    '/faces.js?v=73',
    '/compass.js?v=73',
    '/nyu.js?v=73',
    '/confetti.js?v=73',
    '/caption.js?v=73',
    '/tinder.js?v=73',
    '/picks.js?v=73',
    '/isit.js?v=73',
];

/* 3-tier image caches */
const MICRO_CACHE = 'mp-micro-v1';    /* 64px placeholders (~600B each) — never evict */
const THUMB_CACHE = 'mp-thumb-v1';    /* 480px previews (~15KB each) — LRU 2000 */
const IMAGE_CACHE = 'mp-image-v1';    /* mobile+display tiers — LRU 500 */
const THUMB_CACHE_LIMIT = 2000;
const IMAGE_CACHE_LIMIT = 500;
const ALL_IMAGE_CACHES = [MICRO_CACHE, THUMB_CACHE, IMAGE_CACHE];

/* Install — pre-cache static assets */
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => cache.addAll(STATIC_ASSETS))
            .then(() => self.skipWaiting())
    );
});

/* Activate — clean old caches */
self.addEventListener('activate', event => {
    const keepCaches = new Set([CACHE_NAME, ...ALL_IMAGE_CACHES]);
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => !keepCaches.has(k))
                    .map(k => caches.delete(k))
            )
        ).then(() => self.clients.claim())
    );
});

/* Determine which image cache tier a GCS URL belongs to */
function imageCacheTier(pathname) {
    if (pathname.includes('/micro/'))   return { name: MICRO_CACHE, limit: 0 };
    if (pathname.includes('/thumb/'))   return { name: THUMB_CACHE, limit: THUMB_CACHE_LIMIT };
    return { name: IMAGE_CACHE, limit: IMAGE_CACHE_LIMIT };
}

/* Fetch — network first for HTML/JS/CSS, cache first for images */
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    /* Skip non-GET (let Firestore POSTs pass through to network) */
    if (event.request.method !== 'GET') return;

    /* Let Firebase/Google API requests go straight to network
       — but NOT storage.googleapis.com (that's our image CDN) */
    if (url.hostname.includes('firebaseio.com') ||
        url.hostname.includes('gstatic.com') ||
        (url.hostname.includes('googleapis.com') &&
         !url.hostname.startsWith('storage.'))) return;

    /* Data files — network first, cache fallback */
    if (url.pathname.startsWith('/data/')) {
        event.respondWith(
            fetch(event.request)
                .then(resp => {
                    const clone = resp.clone();
                    caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
                    return resp;
                })
                .catch(() => caches.match(event.request))
        );
        return;
    }

    /* GCS images — cache first, network fallback, tiered caches */
    if (url.hostname === 'storage.googleapis.com') {
        const tier = imageCacheTier(url.pathname);
        event.respondWith(
            caches.match(event.request).then(cached => {
                if (cached) return cached;
                return fetch(event.request).then(resp => {
                    if (resp.ok) {
                        const clone = resp.clone();
                        caches.open(tier.name).then(async cache => {
                            await cache.put(event.request, clone);
                            /* LRU eviction (skip for micro — never evict) */
                            if (tier.limit > 0) {
                                const keys = await cache.keys();
                                if (keys.length > tier.limit) {
                                    await cache.delete(keys[0]);
                                }
                            }
                        });
                    }
                    return resp;
                });
            })
        );
        return;
    }

    /* Static assets — network first, cache fallback (ensures fresh deploys land immediately) */
    event.respondWith(
        fetch(event.request)
            .then(resp => {
                const clone = resp.clone();
                caches.open(CACHE_NAME).then(c => c.put(event.request, clone));
                return resp;
            })
            .catch(() => caches.match(event.request))
    );
});

/* Micro precache — app.js sends micro URLs after data load */
self.addEventListener('message', event => {
    if (event.data && event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
        return;
    }
    if (event.data && event.data.type === 'precache-micros') {
        const urls = event.data.urls;
        if (!urls || !urls.length) return;
        caches.open(MICRO_CACHE).then(cache => {
            let i = 0;
            function next() {
                const batch = urls.slice(i, i + 20);
                if (!batch.length) return;
                i += 20;
                Promise.all(batch.map(u =>
                    cache.match(u).then(hit => hit ? null : cache.add(u).catch(() => {}))
                )).then(() => setTimeout(next, 100));
            }
            next();
        });
    }
});
