/* sw.js — Service Worker for MADphotos Show.
   Vite-built assets use content-hash filenames (HTTP cache handles them).
   Images use a 3-tier runtime cache with LRU eviction. */

const CACHE_NAME = 'madphotos-v62';

/* 3-tier image caches */
const MICRO_CACHE = 'mp-micro-v1';
const THUMB_CACHE = 'mp-thumb-v1';
const IMAGE_CACHE = 'mp-image-v1';
const THUMB_CACHE_LIMIT = 2000;
const IMAGE_CACHE_LIMIT = 500;
const ALL_IMAGE_CACHES = [MICRO_CACHE, THUMB_CACHE, IMAGE_CACHE];

/* Install — skip waiting immediately (no static asset pre-caching with Vite) */
self.addEventListener('install', event => {
    event.waitUntil(self.skipWaiting());
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

/* Fetch — cache-first for GCS images, network-first for data files */
self.addEventListener('fetch', event => {
    const url = new URL(event.request.url);

    if (event.request.method !== 'GET') return;

    /* Let Firebase/Google API requests pass through */
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

    /* All other requests — let browser handle (Vite hashed assets are HTTP-cached) */
});

/* Micro precache — app sends micro URLs after data load */
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
