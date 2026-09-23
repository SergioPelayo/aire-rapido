/* Aire Rápido · sw.js · v1.0.0
   Service worker: permite instalar la app y verla sin conexión con los últimos datos descargados.
   Red primero para la web y los datos (siempre lo más reciente); caché como respaldo. */
const CACHE = 'aire-rapido-1.7.0';
const BASE = ['./', './index.html', './manifest.webmanifest', './stations.json',
  './icon-192.png', './icon-512.png', './icon-maskable-512.png', './apple-touch-icon.png', './favicon.svg'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(BASE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(caches.keys()
    .then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  const propio = url.origin === self.location.origin;
  const libreria = url.hostname === 'cdnjs.cloudflare.com' || url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com';
  if (!propio && !libreria) return;            // teselas del mapa, IGN, Ministerio: directo a la red
  if (libreria) {                              // librerías y fuentes: caché primero
    e.respondWith(caches.match(req).then((r) => r || fetch(req).then((res) => {
      const copia = res.clone(); caches.open(CACHE).then((c) => c.put(req, copia)); return res;
    })));
    return;
  }
  e.respondWith(fetch(req).then((res) => {      // web y datos: red primero
    if (res.ok) { const copia = res.clone(); caches.open(CACHE).then((c) => c.put(req, copia)); }
    return res;
  }).catch(() => caches.match(req).then((r) => r || (req.mode === 'navigate' ? caches.match('./index.html') : Response.error()))));
});
