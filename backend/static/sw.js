const V = "skmu-v2";
const SHELL = ["/", "/manifest.json", "/static/icon-192.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(V).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys()
      .then((ks) => Promise.all(ks.filter((k) => k !== V).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const r = e.request;
  if (r.method !== "GET") return;
  const u = new URL(r.url);
  if (u.origin !== location.origin) return;
  if (u.pathname.startsWith("/api/")) return;

  if (u.pathname.startsWith("/uploads/")) {
    e.respondWith(
      caches.open(V).then(async (c) => {
        const hit = await c.match(r);
        if (hit) return hit;
        const res = await fetch(r);
        if (res.ok) c.put(r, res.clone());
        return res;
      })
    );
    return;
  }

  e.respondWith(
    fetch(r)
      .then((res) => {
        if (res.ok) {
          const cp = res.clone();
          caches.open(V).then((c) => c.put(r, cp));
        }
        return res;
      })
      .catch(() => caches.match(r).then((h) => h || caches.match("/")))
  );
});
