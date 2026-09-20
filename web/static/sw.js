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
var CACHE = 'books-shell-08bfd9e2e4e5';   // shell-hash: 08bfd9e2e4e5
/* R2348（R67-P1）：运行时缓存独立桶（随版本号自动换名，activate 阶段
 * 连旧 RT 一起清），上限 60 条在 fetch 回写处维护。 */
var RT = CACHE + '-rt';
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
             '/static/cream/cream-icon-history.jpg',
             /* R233d（R42-#5）：首屏图 + 礼盒 + 吉凶字字体补进 SHELL——
              * 装完即断网不再破图/回落字体（gift 另有 onerror 双保险）。 */
             '/static/cream/cream-hero-v2.jpg',
             '/static/cream/avatar-xiaoman-cream.jpg',
             '/static/cream/empty-xiaoman.png',
             '/static/cream/icon-180.png',
             '/static/shared/daily-box-gift.png',
             '/static/cream/daily-gift-bear.png',
             '/static/shared/icon-set-moon-cat.jpg',
             '/static/fonts/smiley-sans-subset.woff2'];

self.addEventListener('install', function (e) {
  /* R230v（R34-#9）：addAll 全有或全无 + catch 吞错 = 单文件 404 时
   * 安装「成功」但 CACHE 是空的，首次离线导航 respondWith(undefined)
   * 白屏——「断网不白屏」静默失效。改为逐件 allSettled：壳核心件
   * （/、index.html、app.js、styles.css）缺一不可装；装饰件（图标/
   * 字体/卡图）失败容忍，下次安装补齐。 */
  var CORE = ['/', '/static/index.html', '/static/app.js',
              '/static/styles.css'];
  e.waitUntil(caches.open(CACHE).then(function (c) {
    return Promise.allSettled(SHELL.map(function (u) {
      /* R2345（R63-P2-3）：c.add 默认走 HTTP 缓存——js/css 有
       * max-age=3600，部署后 1h 内安装可能把旧字节装进新 CACHE 名。
       * reload 模式绕开 HTTP 缓存直取网络。 */
      return c.add(new Request(u, {cache: 'reload'}));
    })).then(function (rs) {
      var coreMiss = [];
      rs.forEach(function (r, i) {
        if (r.status === 'rejected' && CORE.indexOf(SHELL[i]) !== -1) {
          coreMiss.push(SHELL[i]);
        }
      });
      if (coreMiss.length) {
        /* 核心件缺失 → 安装失败让浏览器下次重试，不留「装了但没壳」。 */
        throw new Error('shell core missing: ' + coreMiss.join(','));
      }
    });
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

  /* 导航请求（刷新）：SWR——先给缓存壳保住白屏，后台再更新。
   * R2345（R63-P1-1）：/static/* 直链导航此前一律回壳 HTML——直开
   * 静态图拿到首页。静态路径放行落到下面的 cache-first 分支。 */
  if (e.request.mode === 'navigate'
      && url.pathname.indexOf('/static/') !== 0) {
    e.respondWith(
      caches.match('/').then(function (hit) {
        var net = fetch(e.request).then(function (resp) {
          /* R228k：瞬时 500/断线 HTML 不许当壳缓存——否则坏页会粘住 */
          if (resp.ok) {
            /* R230d（R16-P0-1）：put 挂 waitUntil——游离 Promise 会在
             * respondWith resolve 后随 SW 回收而丢，运行时缓存恒写不进。 */
            e.waitUntil(caches.open(CACHE).then(function (c) {
              /* R2345（R63-P3-7）：配额满 put 会 reject——挂 catch
               * 不让 waitUntil 变 rejected 拖到 SW 回收。 */
              return c.put('/', resp.clone()).catch(function () {});
            }));
          }
          return resp;
        }).catch(function () { return hit; });
        return hit || net;
      })
    );
    return;
  }

  /* 同源静态资源：cache-first，命中即回，后台静默更新。
   * R2348（R67-P1）：运行时写进独立 books-rt 桶并 LRU 封顶 60 条——
   * 原先全部塞进 SHELL 桶且无上限，tarot 3MB+lxgw 长尾随浏览单调涨，
   * 只能靠版本 bump 整库清。 */
  e.respondWith(
    caches.match(e.request).then(function (hit) {
      var net = fetch(e.request).then(function (resp) {
        if (resp.ok) {
          /* R230d（R16-P0-1）：同上，运行时缓存回写必须挂 waitUntil。 */
          e.waitUntil(caches.open(RT).then(function (c) {
            return c.put(e.request, resp.clone()).then(function () {
              /* 超帽逐出最老条（keys() 顺序即写入序）。60 条≈几 MB，
               * 删掉自己刚写入的边界情形用 '!==e.request' 排除不掉——
               * 先 put 后 trim，刚写的在最尾不会被删。 */
              return c.keys().then(function (ks) {
                if (ks.length <= 60) return;
                return Promise.all(ks.slice(0, ks.length - 60)
                  .map(function (k) { return c.delete(k); }));
              });
            }).catch(function () {});
          }));
        }
        return resp;
      }).catch(function () { return hit; });
      return hit || net;
    })
  );
});
