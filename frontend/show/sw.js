/* sw.js — Service Worker for MADphotos Show.
   Caches static assets (JS, CSS, HTML) for offline use.
   Images use a runtime cache with LRU eviction. */

const CACHE_NAME = 'madphotos-v1';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/style.css?v=12',
    '/app.js?v=12',
    '/theme.js?v=12',
    '/grid.js?v=12',
    '/colors.js?v=12',
    '/bento.js?v=12',
    '/game.js?v=12',
    '/faces.js?v=12',
    '/compass.js?v=12',
    '/nyu.js?v=12',
    '/confetti.js?v=12',
    '/square.js?v=12',
    '/caption.js?v=12',
    '/cinema.js?v=12',
    '/reveal.js?v=12',
    '/pulse.js?v=12',
    '/drift.js?v=12',
];

const IMAGE_CACHE = 'madphotos-images-v1';
const IMAGE_CACHE_LIMIT = 500;

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
    event.waitUntil(
        caches.keys().then(keys =>
            Promise.all(
                keys.filter(k => k !== CACHE_NAME && k !== IMAGE_CACHE)
                    .map(k => caches.delete(k))
            )
        ).then(() => self.clients.claim())
    );
});

/* Fetch — network first for HTML/JS/CSS, cache first for images */
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    /* Skip non-GET */
    if (event.request.method !== 'GET') return;

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

    /* GCS images — cache first, network fallback */
    if (url.hostname === 'storage.googleapis.com') {
        event.respondWith(
            caches.match(event.request).then(cached => {
                if (cached) return cached;
                return fetch(event.request).then(resp => {
                    if (resp.ok) {
                        const clone = resp.clone();
                        caches.open(IMAGE_CACHE).then(async cache => {
                            await cache.put(event.request, clone);
                            /* LRU eviction */
                            const keys = await cache.keys();
                            if (keys.length > IMAGE_CACHE_LIMIT) {
                                await cache.delete(keys[0]);
                            }
                        });
                    }
                    return resp;
                });
            })
        );
        return;
    }

    /* Static assets — cache first, network fallback */
    event.respondWith(
        caches.match(event.request).then(cached => cached || fetch(event.request))
    );
});
