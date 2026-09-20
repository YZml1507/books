/* R218a-巡4（E-c）：离线兜底——SPA 无 SW 时断网 reload 直接白屏
 * （ERR_INTERNET_DISCONNECTED）。本 SW 只做两件事：
 *  1. app shell（/、index.html、app.js、styles.css）stale-while-revalidate：
 *     断网时用缓存兜住壳，页面可渲染 + 提示「当前离线」；
 *  2. /api/* 永不缓存（命理数据必须新鲜，离线时让请求自然失败，
 *     前端既有 toast/内联错误文案接管）。
 * 版本号递增即失效旧缓存。 */
/* R229z续14++：CACHE 名直接派生自 app.js 内容哈希（scripts/bump_sw.py
 * 重写下一行）。selftest 闸「sw.shell_hash」比对标记与文件现状——
 * 改了 app.js 忘跑 bump_sw.py 会直接红，杜绝老客粘旧壳。 */
var CACHE = 'books-shell-4c74c7025786';   // shell-hash: 4c74c7025786
/* R229x：manifest+图标进预缓存——「装上 PWA 即断网」场景下图标/manifest
 * 此前只靠运行时懒缓存兜不住。
 * R230d（R16-P2-1）：SHELL 补齐首屏依赖——web-lite.css、lxgw.css（字体
 * 声明本体）、zcool woff2、favicon、8 张功能卡图（lazy 藏在 details 里的
 * 两张此前离线断图）。lxgw 的 ~15 个 woff2 分片走运行时缓存（P0-1 修复后
 * put 真正落地）。 */
var SHELL = ['/', '/static/index.html', '/static/app.js', '/static/styles.css',
             '/static/manifest.json', '/static/cream/icon-192.png',
             '/static/cream/icon-512.png',
             '/static/animotion/web-lite.css', '/static/fonts/lxgw.css',
             '/static/fonts/zcool-kuaile-subset.woff2',
             '/static/cream/favicon-cream-64.png',
             '/static/cream/cream-icon-bazi.jpg',
             '/static/cream/cream-icon-liuyao.jpg',
             '/static/cream/cream-icon-huangli.jpg',
             '/static/cream/cream-icon-tarot.jpg',
             '/static/cream/cream-icon-qiming.jpg',
             '/static/cream/cream-icon-hehun.jpg',
             '/static/cream/cream-icon-taohua.jpg',
             '/static/cream/cream-icon-xingzuo.jpg',
             '/static/cream/cream-icon-history.jpg'];

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return c.addAll(SHELL).catch(function () { /* 单文件失败不阻断安装 */ });
  }));
  self.skipWaiting();
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }));
  self.clients.claim();
});

self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;          // POST 全直连
  if (url.origin !== self.location.origin) return; // 跨源不接管（未来外链保险）
  if (url.pathname.indexOf('/api/') === 0) return; // API 永不缓存

  /* 导航请求（刷新）：SWR——先给缓存壳保住白屏，后台再更新 */
  if (e.request.mode === 'navigate') {
    e.respondWith(
      caches.match('/').then(function (hit) {
        var net = fetch(e.request).then(function (resp) {
          /* R228k：瞬时 500/断线 HTML 不许当壳缓存——否则坏页会粘住 */
          if (resp.ok) {
            /* R230d（R16-P0-1）：put 挂 waitUntil——游离 Promise 会在
             * respondWith resolve 后随 SW 回收而丢，运行时缓存恒写不进。 */
            e.waitUntil(caches.open(CACHE).then(function (c) {
              return c.put('/', resp.clone());
            }));
          }
          return resp;
        }).catch(function () { return hit; });
        return hit || net;
      })
    );
    return;
  }

  /* 同源静态资源：cache-first，命中即回，后台静默更新 */
  e.respondWith(
    caches.match(e.request).then(function (hit) {
      var net = fetch(e.request).then(function (resp) {
        if (resp.ok) {
          /* R230d（R16-P0-1）：同上，运行时缓存回写必须挂 waitUntil。 */
          e.waitUntil(caches.open(CACHE).then(function (c) {
            return c.put(e.request, resp.clone());
          }));
        }
        return resp;
      }).catch(function () { return hit; });
      return hit || net;
    })
  );
});
