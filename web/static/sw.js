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
var CACHE = 'books-shell-7aff36fde93b';   // shell-hash: 7aff36fde93b
/* R2348（R67-P1）：运行时缓存独立桶（随版本号自动换名，activate 阶段
 * 连旧 RT 一起清），上限 60 条在 fetch 回写处维护。 */
var RT = CACHE + '-rt';
/* R229x：manifest+图标进预缓存——「装上 PWA 即断网」场景下图标/manifest
 * 此前只靠运行时懒缓存兜不住。
 * R230d（R16-P2-1）：SHELL 补齐首屏依赖——web-lite.css、lxgw.css（字体
 * 声明本体）、zcool woff2、favicon、8 张功能卡图（lazy 藏在 details 里的
 * 两张此前离线断图）。lxgw 的 ~15 个 woff2 分片走运行时缓存（P0-1 修复后
 * put 真正落地）。 */
var SHELL = ['/', '/static/index.html', '/static/app.js', '/static/app_poster.js',
             '/static/app_research.js', '/static/app_wallpaper.js',
             '/static/qian_data.js',
             '/static/styles.css',
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
             /* R3341（审-中）：renge/oracle/moon-cat 三张功能卡图在首屏
              * 宫格上屏，此前漏收——RT 60 条桶被热图挤占后离线破图。
              * （R3338 曾把 moon-cat 挪去 RT，审复核它其实是首屏卡图，
              * 收回 SHELL。empty-xiaoman 有 onerror 自移除兕底，留 RT。） */
             '/static/cream/icon-renge.jpg',
             '/static/cream/cream-icon-oracle.jpg',
             /* R3396-P1-1：mochi/qian/ansb 三张新功能卡图同口径收
              * SHELL——装完即断网不破图，重烘自动换 CACHE 号。 */
             '/static/cream/cream-icon-mochi.jpg',
             '/static/cream/cream-icon-qian.jpg',
             '/static/cream/cream-icon-ansb.jpg',
             /* R3424：敲敲木鱼卡图+敲击面主图同一张——收 SHELL。 */
             '/static/cream/cream-icon-muyu.jpg',
             '/static/shared/icon-set-moon-cat.jpg',
             /* R233d（R42-#5）：首屏图 + 礼盒 + 吉凶字字体补进 SHELL——
              * 装完即断网不再破图/回落字体（gift 另有 onerror 双保险）。 */
             '/static/cream/cream-hero-v2.jpg',
             '/static/cream/avatar-xiaoman-cream.jpg',
             '/static/cream/icon-180.png',
             /* R2510（审-SW-P2）：manifest maskable 图标此前不在 SHELL——
              * 装完即离线时启动图标破图。 */
             '/static/cream/icon-512-maskable.png',
             '/static/shared/daily-box-gift.png',
             '/static/cream/daily-gift-bear.png',
             '/static/fonts/smiley-sans-subset.woff2',
             /* R3371（审-低-5）：qrcode 懒库收进 SHELL——否则首次进
              * 海报页前断网，回流二维码离线失效。21KB。 */
             '/static/libs/qrcode.min.js'];

self.addEventListener('install', function (e) {
  /* R230v（R34-#9）：addAll 全有或全无 + catch 吞错 = 单文件 404 时
   * 安装「成功」但 CACHE 是空的，首次离线导航 respondWith(undefined)
   * 白屏——「断网不白屏」静默失效。改为逐件 allSettled：壳核心件
   * （/、index.html、app.js、styles.css）缺一不可装；装饰件（图标/
   * 字体/卡图）失败容忍，下次安装补齐。 */
  var CORE = ['/', '/static/index.html', '/static/app.js',
              '/static/styles.css'];
  e.waitUntil(caches.open(CACHE).then(function (c) {
    /* R2353（R110-P2-8）：allSettled 在 Chromium<76/iOS<13 未实现——
     * install 抛异常 SW 装不上，离线壳静默缺失（老 X5 命中）。
     * 手动等值包装，兼容到最早 SW 实现。 */
    var _settle = function (p) {
      return p.then(
        function (v) { return { status: 'fulfilled', value: v }; },
        function (r) { return { status: 'rejected', reason: r }; });
    };
    /* R3371（审-P1-2）：版本化资产按 ?v=hash 装壳——URL 自带内容
     * 指纹，页面刚下载过的同 URL 可吃 HTTP 缓存命中，install 不再
     * 全量重下（首访省 ~0.5MB、每版老客省 ~0.5MB）。裸 URL 仍走
     * reload 防 3600s 陈旧字节装进新 CACHE（R63-P2-3 语义保留）。 */
    var _vh = CACHE.slice('books-shell-'.length);
    /* R3405-F6：_VMAP 扩到全部「页面按 ?v= 请」的壳件——
     * 懒 chunk（poster/research/wallpaper/qian_data）此前走
     * cache:reload 全量重下 ~335KB，版本化请求可吃 HTTP 命中。 */
    var _VMAP = {
      '/static/app.js': '/static/app.js?v=' + _vh,
      '/static/styles.css': '/static/styles.css?v=' + _vh,
      '/static/app_poster.js': '/static/app_poster.js?v=' + _vh,
      '/static/app_research.js': '/static/app_research.js?v=' + _vh,
      '/static/app_wallpaper.js': '/static/app_wallpaper.js?v=' + _vh,
      '/static/qian_data.js': '/static/qian_data.js?v=' + _vh };
    return Promise.all(SHELL.map(function (u) {
      var _req = _VMAP[u] ? new Request(_VMAP[u])
                          : new Request(u, {cache: 'reload'});
      return _settle(c.add(_req));
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
  }).then(function () {
    /* R3341（审-低）：skipWaiting 收进 waitUntil——写在事件外，
     * SW 可能在收编前被回收，新壳装了不接管。 */
    return self.skipWaiting();
  }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    /* R2500（R143-SW-P3）：自己的 RT 桶不删——此前 activate 把
     * CACHE+'-rt' 也清了（无害但白删一轮）。 */
    return Promise.all(keys.filter(function (k) { return k !== CACHE && k !== RT; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () {
    /* R3341（审-低）：claim 收进 waitUntil——同上。 */
    return self.clients.claim();
  }));
});

self.addEventListener('fetch', function (e) {
  var url = new URL(e.request.url);
  if (e.request.method !== 'GET') return;          // POST 全直连
  /* R3355：blob: 请求（海报预览图/a[download] 对象 URL）会被
   * SW 接管——url.origin 解析出内层源判定同源，落到 cache-first
   * 分支后 SW 内 fetch(e.request) 对 blob: 恒失败（预览图裂）。
   * 不 respondWith 即默认放行，由 blob store 直接应答。 */
  if (e.request.url.indexOf('blob:') === 0) return;
  if (url.origin !== self.location.origin) return; // 跨源不接管（未来外链保险）
  if (url.pathname.indexOf('/api/') === 0) return; // API 永不缓存

  /* 导航请求（刷新）：SWR——先给缓存壳保住白屏，后台再更新。
   * R2345（R63-P1-1）：/static/* 直链导航此前一律回壳 HTML——直开
   * 静态图拿到首页。静态路径放行落到下面的 cache-first 分支。 */
  if (e.request.mode === 'navigate'
      && url.pathname.indexOf('/static/') !== 0) {
    /* R2510（审-SW-P2）：match('/') 与 fetch 此前串行——每次导航
     * 白等一个 CacheStorage 往返才发网络请求。并行起，离线兜底时
     * 再用壳查询结果；catch 兜底防 match 自身 reject 变游离拒绝。 */
    var _hitP = caches.match('/').catch(function () { return undefined; });
    /* R3364（审-P2）：导航 network-first 无超时——后端挂起时每次
     * 导航白屏吃满挂起时长（Render 冷启/卡死窗口）。8s 竞速回落
     * 壳位；5xx 同样回落（裸 502 上屏不如离线壳）。403 门页不在
     * 此列——必须原样上屏。 */
    var _navTo = new Promise(function (_r, _rj) {
      setTimeout(function () { _rj(new Error('nav-timeout')); }, 8000);
    });
    var _navF = fetch(e.request);
    /* R3405-F10：8s 竞速超时后飞行中的响应被丢弃——Render 慢冷启
     * 首访拿旧壳还得再刷一次才是新内容。飞行 promise 也挂补写链：
     * 晚到的成功正壳导航顺手更新 '/' 壳位（竞速胜出的正常路径
     * 已有 put，此处 clone 会抛——try/catch 吞掉即可，不双写）。 */
    e.waitUntil(_navF.then(function (resp) {
      try {
        if (resp.ok && url.pathname === '/' && !url.search) {
          return caches.open(CACHE).then(function (c) {
            return c.put('/', resp.clone()).catch(function () {});
          });
        }
      } catch (xBF) {}
      return undefined;
    }).catch(function () {}));
    e.respondWith(
        /* R2400（R130-P2-2）：network-first——旧版「先给缓存壳」让
         * 门页对解锁过的设备永久失效（cookie 过期/换口令都赶不走）。
         * 在线时以服务端响应为准（403 门页照实上屏），缓存壳只留作
         * 离线兜底。 */
        Promise.race([_navF, _navTo]).then(function (resp) {
          if (resp.status >= 500) {
            throw new Error('nav-' + resp.status);
          }
          /* R228k：瞬时 500/断线 HTML 不许当壳缓存——否则坏页会粘住 */
          /* R2349u（R91-P1-3）：FastAPI 默认开 /docs /openapi.json，
           * 那些导航的响应此前被写进 '/' 壳位——壳污染后首页变 Swagger。
           * 只有真 '/' 导航才允许回写壳位。 */
          /* R2510（审-SW-P2）：?view= 等带参导航返回的是 og 变体文档
           * （分享链接/PWA 捷径专用）——此前 pathname==='/' 就放它进
           * 壳位，离线打开 '/' 看到变体页。空 search 才算正壳。 */
          if (resp.ok && url.pathname === '/' && !url.search) {
            /* R230d（R16-P0-1）：put 挂 waitUntil——游离 Promise 会在
             * respondWith resolve 后随 SW 回收而丢，运行时缓存恒写不进。 */
            e.waitUntil(caches.open(CACHE).then(function (c) {
              /* R2345（R63-P3-7）：配额满 put 会 reject——挂 catch
               * 不让 waitUntil 变 rejected 拖到 SW 回收。 */
              return c.put('/', resp.clone()).catch(function () {});
            }));
          }
          return resp;
        }).catch(function () {
          /* R2502：CacheStorage 在存储压力下可整体逐出——hit 此时是
           * undefined，respondWith 收到非 Response 等价白屏。离线
           * 且壳也丢了时给一句人话页兜底。 */
          return _hitP.then(function (hit) {
            return hit || new Response(
            '<!doctype html><meta charset="utf-8"><meta name="viewport" ' +
            'content="width=device-width,initial-scale=1"><body ' +
            'style="font-family:sans-serif;display:flex;min-height:100vh;' +
            'align-items:center;justify-content:center;text-align:center;' +
            'background:#FFF8E7;color:#4A3F35;margin:0;padding:16px">' +
            '<div style="max-width:320px;background:#fff;border-radius:18px;' +
            'padding:28px 24px;box-shadow:0 4px 20px rgba(0,0,0,.08)"> ' +
            '<div style="font-size:42px;margin-bottom:12px">🌾</div>' +
            '<h1 style="margin:0 0 10px;font-size:20px">小满 offline 卡</h1>' +
            '<p style="margin:0 0 18px;line-height:1.6;font-size:15px">' +
            '网没连上，缓存也刚好空了。<br>联网后按下面刷新，小满在这儿等你。' +
            '</p><button onclick="location.reload()" ' +
            'style="font-size:15px;padding:10px 22px;border-radius:999px;' +
            'border:0;background:#4A3F35;color:#FFF8E7;cursor:pointer">' +
            '刷新试试</button></div></body>',
            { status: 503,
              headers: { 'Content-Type': 'text/html; charset=utf-8' } });
        });
      })
    );
    return;
  }

  /* 同源静态资源：cache-first。
   * R2349u（R91-P0-1/P1-1）：此前 caches.match 按桶创建序命中——
   * precache 桶恒先于 RT 命中，「后台静默更新」写进的是永远读不到的
   * 死字节，同版本内 app.js 不可自愈合；且命中也照发 refetch——
   * 每页加载对 ~30 壳件+长尾各 revalidate 一次纯属浪费。
   * 现改为：RT 桶先查（运行资产自愈用），再查 precache
   * （ignoreSearch 让 ?v= 版本化 URL 命中版本钉死的壳件）；
   * precache 命中直接回（桶名即内容哈希，字节不可能变，零 refetch）；
   * RT 命中才后台 revalidate。 */
  /* R3364（审-低）：?v 检查前置到 RT 查询之前——此前 RT 桶命中
   * 的请求跳过版本检查，哪天 app.js?v=新 被写进 RT，该 URL 就
   * 永久免检查（哑弹）。 ?v 不符：JS 回限频刷新脚本，非 JS 网
   * 络直通（版本化 URL 本就不该占 RT 位）。 */
  var _reqV = url.searchParams.get('v');
  if (_reqV && _reqV !== CACHE.slice('books-shell-'.length)) {
    if (url.pathname.slice(-3) === '.js') {
      /* R3364（审-P0）：刷新脚本自带刹车——30s 窗内最多 5 次
       * reload，超出即停手。此前裸 location.reload()：一旦
       * 环成（老 SW+新 HTML），任何年代的 SW 都没有自救
       * 手段、风暴饿死软更新检查。刹车写进响应体本身，不
       * 依赖页面新旧。sessionStorage 不可用时退回裸 reload
       * （无痕下 SW 本不持久）。 */
      e.respondWith(new Response(
        'try{var _k="__swrl",_v=(sessionStorage.getItem(_k)' +
        '||"0:0").split(":"),_t=+_v[0],_c=+_v[1],_n=Date.now();' +
        'if(_n-_t>30000){_t=_n;_c=0}' +
        'sessionStorage.setItem(_k,_t+":"+(_c+1));' +
        'if(_c<5){location.reload()}}catch(x){location.reload()}',
        { headers: { 'Content-Type':
          'text/javascript; charset=utf-8' } }));
    } else {
      e.respondWith(fetch(e.request)
        .catch(function () { return undefined; }));
    }
    return;
  }
  e.respondWith(
    caches.open(RT).then(function (rtc) {
      return rtc.match(e.request).then(function (rtHit) {
        var _net = function () {
          return fetch(e.request).then(function (resp) {
            if (resp.ok) {
              /* R230d（R16-P0-1）：运行时缓存回写必须挂 waitUntil。 */
              e.waitUntil(rtc.put(e.request, resp.clone()).then(function () {
                /* 超帽逐出最老条（keys() 顺序即写入序）。
                 * R3371（审-P2-4）：60→180——tarot 80 图+lxgw 50 分片+
                 * 壁纸 21≈151 条候选，60 桶会把早期牌面/字体挤出
                 * 导致离线破图；180 全收仍只 ~5-8MB。 */
                return rtc.keys().then(function (ks) {
                  /* R3405-F3：180 帽 < EXTRA_GLOBS 实收 260 件
                   * （tarot 80+lxgw 分片+壁纸 21+签/合盘/图标等，
                   * ~8.5MB）——重度用户全触后最早条目被逐出，
                   * 离线回看早期牌面/字体分片破图。帽提到 300。 */
                  if (ks.length <= 300) return;
                  return Promise.all(ks.slice(0, ks.length - 300)
                    .map(function (k) { return rtc.delete(k); }));
                });
              }).catch(function () {}));
            }
            return resp;
          });
        };
        if (rtHit) {
          /* RT 命中：serve + 后台 revalidate（牌面/字体等运行资产
           * 跨版本更换桶名，自愈只在同版本内需要）。 */
          e.waitUntil(_net().catch(function () {}));
          return rtHit;
        }
        return caches.match(e.request, { ignoreSearch: true })
          .then(function (hit) {
            /* precache 命中：版本钉死内容，不再 revalidate（R91-P1-1）。 */
            if (hit) return hit;
            return _net().catch(function () { return undefined; });
          });
      });
    })
  );
});
