const cacheVersion = "v2.10";

self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open(cacheVersion).then(function (cache) {
      return cache.addAll([
        "/static/css/style.css?" + cacheVersion,
        "/static/css/vendor.css?" + cacheVersion,
        "/static/js/app.js?" + cacheVersion,
        "/static/reconnecting-websocket.min.js",
        "/static/img/icon.svg",
        "/static/img/icon192.png",
        "/static/img/icon512-maskable.png",
      ]);
    })
  );
});

self.addEventListener("activate", function (e) {
  e.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (key) {
            return key !== cacheVersion;
          })
          .map(function (key) {
            return caches.delete(key);
          })
      );
    })
  ).then(function () {
    return clients.claim();
  });
});

self.addEventListener("fetch", function (e) {
  e.respondWith(
    caches.match(e.request).then(function (response) {
      return response || fetch(e.request);
    })
  );
});
