self.addEventListener("install", function (e) {
  e.waitUntil(
    caches.open("v2.8").then(function (cache) {
      return cache.addAll([
        "/",
        "/static/css/style.css?v2.8",
        "/static/css/vendor.css?v2.8",
        "/static/js/app.js?v=2.8",
        "/static/reconnecting-websocket.min.js",
        "/static/img/icon.svg",
        "/static/img/icon192.png",
        "/static/img/icon512-maskable.png",
      ]);
    })
  );
});

self.addEventListener("fetch", function (e) {
  e.respondWith(
    caches.match(e.request).then(function (response) {
      return response || fetch(e.request);
    })
  );
});
