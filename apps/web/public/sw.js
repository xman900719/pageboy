/* Conservative offline shell only; NEVER cache authenticated /api responses or exam documents. */
const CACHE='shutong-static-v3';
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(['/','/icons/favicon-32.png','/icons/favicon-48.png','/icons/apple-touch-icon.png','/icons/icon-192.png','/icons/icon-512.png','/manifest.webmanifest'])));self.skipWaiting()});
self.addEventListener('activate',event=>{event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));self.clients.claim()});
self.addEventListener('fetch',event=>{const u=new URL(event.request.url);if(event.request.method!=='GET'||u.pathname.startsWith('/api')||u.pathname.startsWith('/health')||u.origin!==self.location.origin)return;if(event.request.mode==='navigate'){event.respondWith(fetch(event.request).catch(()=>caches.match('/')));return} event.respondWith(fetch(event.request).catch(()=>caches.match(event.request)))});
