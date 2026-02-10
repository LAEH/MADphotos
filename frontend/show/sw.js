/* sw.js — Service Worker for MADphotos Show.
   Caches static assets (JS, CSS, HTML) for offline use.
   Images use a runtime cache with LRU eviction. */

const CACHE_NAME = 'madphotos-v24';
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/style.css?v=38',
    '/app.js?v=38',
    '/theme.js?v=38',
    '/colors.js?v=38',
    '/bento.js?v=38',
    '/game.js?v=38',
    '/faces.js?v=38',
    '/compass.js?v=38',
    '/nyu.js?v=38',
    '/confetti.js?v=38',
    '/caption.js?v=38',
    '/tinder.js?v=38',
    '/picks.js?v=38',
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

    /* Skip non-GET (let Firestore POSTs pass through to network) */
    if (event.request.method !== 'GET') return;

    /* Let Firebase/Google API requests go straight to network */
    if (url.hostname.includes('googleapis.com') || url.hostname.includes('gstatic.com') || url.hostname.includes('firebaseio.com')) return;

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
