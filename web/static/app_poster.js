/* ── 海报/分享图生成族（R2400，R122-P1-1：自 app.js 拆出，懒加载组件）──
 * 加载方式：app.js 的 downloadPoster stub 首次被点才注入本脚本；
 * 加载后本文件的同名函数接管 stub。模态管理（showPosterModal 等）
 * 与通用导出弹层留在 app.js——它们还被文本导出等非海报链共用。 */

var POSTER_FULL_W = 1080, POSTER_FULL_H = 1440;   /* 判据 7 固定 3:4 */
var POSTER_LOW_W = 750, POSTER_LOW_H = 1000;      /* T3.3 低端降级尺寸 */
var POSTER_LONGTASK_MS = 50;                      /* 长任务阈值 */

function drawPoster(j, opts) {
  var o = opts || {};
  var perf = (window.performance && performance.now) ?
    function () { return performance.now(); } : function () { return 0; };
  var W = o.low ? POSTER_LOW_W : POSTER_FULL_W;
  var H = o.low ? POSTER_LOW_H : POSTER_FULL_H;
  if (o.auto === false || o.low) {     /* 验收口径 / 强制低配：固定尺寸直绘 */
    var __cv = _paintPoster(j, W, H);
    return __cv ? { canvas: __cv, w: W, h: H } : null;
  }
  var __t1 = perf();
  var cv = _paintPoster(j, POSTER_FULL_W, POSTER_FULL_H);
  var __dt = perf() - __t1;
  if (!cv) return null;
  if (__dt > POSTER_LONGTASK_MS) {     /* T3.3：长任务 → 低端降级重画 */
    /* R230r（R29-#13）：二次降级仍失败时如实返回 null——原来包一层
     * {canvas:null, w,h} 外壳，下游字段全非空像成功。 */
    var _cv2 = _paintPoster(j, POSTER_LOW_W, POSTER_LOW_H);
    return _cv2 ? { canvas: _cv2, w: POSTER_LOW_W, h: POSTER_LOW_H } : null;
  }
  return { canvas: cv, w: POSTER_FULL_W, h: POSTER_FULL_H };
}

/** 海报绘制本体：逻辑坐标恒 1080×1440，经 ctx.scale 缩放到目标画布。
 *  所有几何/字号写死逻辑值——同一输入在任何目标尺寸下版式逐点一致。
 *  R198b（US5）：新增通用形状 j.share —— {title, subtitle, big, bigSub,
 *  lines:[{k,v}], cards:[{name,sub,img?}]}，由 buildShareData(view,j)
 *  从各端点响应提取；j.share 存在时走统一模板（七端点一套版式族），
 *  不存在时保持 bazi 专属旧版式（check_poster 判据 12 口径不变）。 */
function _paintPoster(j, W, H) {
  var S = W / 1080;
  if (j && j.share) {
    /* R218a-巡3 修复（N-02+N-04 副作用兜底）：buildShareData 各 case 把 j 的
     * 关键字段（warm/full_names/peach_zhi/day_wx_a/_b/_sheng）压到 s.lines/
     * s.cards 供海报内容用，但**没**保留 j.warm/j.full_names/j.peach_zhi 到
     * s 自身；金句 hook（_posterHookForView）会读这些字段做数据驱动金句
     * （N-09）。为不丢这个能力，把 j 整体挂到 s._src（additive：纯新增键
     * 不影响 share schema），让 hook 仍能拿到完整父数据，share 静态字段
     * 走 s 自身，重复也不冲突。 */
    return _paintSharePoster(Object.assign({}, j.share, { _src: j }), W, H);
  }
  var warm = (j && j.warm) || {};
  var paipan = (j && j.paipan) || {};
  var ec = warm.energy_card || {};
  var cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  var ctx = cv.getContext('2d');
  if (!ctx) return null;
  ctx.setTransform(S, 0, 0, S, 0, 0);

  // 底色：暖米白渐变（固定值，不读 CSS 变量——版式不受主题影响）
  var bg = ctx.createLinearGradient(0, 0, 0, 1440);
  bg.addColorStop(0, '#FDF8F0');
  bg.addColorStop(1, '#F6EDE0');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, 1080, 1440);

  // 标题
  ctx.fillStyle = '#7A5C2E';
  /* R2345（R62-P1-7）：海报标题换品牌快乐体（站点标题同款声口） */
  ctx.font = '64px "ZCOOL KuaiLe","LXGW WenKai","Noto Serif TC",serif';
  ctx.textAlign = 'center';
  /* R230r（R29-#3）：legacy 版式混用 W 与 1080 逻辑坐标——750 档下标题/
   * pills/能量卡/水印集体左移、首 pill 被裁。几何值全部钉回 1080 逻辑系。 */
  ctx.fillText('🔮 今日命盘', 540, 130);

  // 四柱 pills
  /* R3235：时辰未知盘第 4 柱是默认午时——海报同卡面换「时辰未知」，
   * _pillarsHonest 在 app.js（本 chunk 懒加载在其后）。 */
  var pillars = String(_pillarsHonest(paipan.render, j && j.hour_known) || '').split(/\s+/).filter(function (p) { return p.length >= 2; });
  ctx.font = '500 44px "LXGW WenKai","Noto Serif TC",serif';
  pillars.slice(0, 4).forEach(function (p, i) {
    var pw = 220, gap = 24;
    var x0 = (1080 - pillars.slice(0, 4).length * pw - (pillars.slice(0, 4).length - 1) * gap) / 2;
    ctx.fillStyle = i % 2 ? '#EFE3CE' : '#F3E6CF';
    roundRect(ctx, x0 + i * (pw + gap), 190, pw, 78, 39);
    ctx.fill();
    ctx.fillStyle = '#5B4620';
    ctx.fillText(p, x0 + i * (pw + gap) + pw / 2, 243);
  });

  // 一句话结论（L0）
  ctx.fillStyle = '#3E3428';
  ctx.font = '600 56px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  var l0 = wrapText(ctx, _pStr(warm.one_liner), 880);
  l0.forEach(function (ln, i) { ctx.fillText(ln, 540, 380 + i * 76); });

  // 能量卡区块
  /* R216b 续（U-014）：卡高 430→560（信息行与出处行原本叠印，见下）。 */
  var cardY = 480;
  ctx.fillStyle = '#FFFFFF';
  roundRect(ctx, 90, cardY, 900, 560, 28);
  ctx.fill();
  ctx.strokeStyle = '#E8D9BC'; ctx.lineWidth = 2;
  roundRect(ctx, 90, cardY, 900, 560, 28);
  ctx.stroke();

  ctx.textAlign = 'left';
  ctx.fillStyle = '#7A5C2E'; ctx.font = '600 40px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  ctx.fillText('本命 ' + _pStr(ec.element) + '（' + _pStr(ec.element_warm) + '）', 140, cardY + 80);

  var rows = [];
  var _elc = _pArr(ec.lucky_colors), _eln = _pArr(ec.lucky_numbers),
      _elh = _pArr(ec.lucky_hours);
  if (_elc.length) rows.push(['幸运色', _elc.map(_pStr).join(' · ')]);
  if (_eln.length) rows.push(['幸运数字', _eln.map(_pStr).join(' · ')]);
  if (_elh.length) {
    /* R216b 续（U-014 附带）：lucky_hours 全量 join 可达 ~60 字，38px 下
     * 远超卡宽（940px 内约 24 字）——审查轨截图里「黄运棕」实为「黄 · 棕」
     * 与下一行叠印的误读，但时段行确实溢出。只取前三个时段并压缩区间写法。 */
    var hs = _elh.slice(0, 3).map(function (h) {
      return String(h).replace(/（/g, '(').replace(/）/g, ')').replace(/–/g, '-');
    });
    rows.push(['幸运时段', hs.join('、')]);
  }
  ctx.font = '400 38px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  rows.slice(0, 3).forEach(function (r, i) {
    var y = cardY + 160 + i * 84;
    // 幸运色色块
    if (i === 0) {
      var colors = ['红#C0392B', '紫#8E44AD', '黄#D4AC0D', '棕#8D6E63',
                    '黑#2C3E50', '蓝#2874A6', '青#148F77', '绿#27AE60',
                    '白#F2F3F4', '金#B7950B'];
      var cx = 620;
      String(r[1]).split(' · ').forEach(function (cname) {
        for (var k = 0; k < colors.length; k++) {
          if (colors[k].indexOf(cname) === 0) {
            ctx.fillStyle = colors[k].split('#')[1];
            circle(ctx, cx, y - 12, 22); ctx.fill();
            cx += 60;
            break;
          }
        }
      });
      /* 色块只是辅助——文字本身也要画出（原版文字被值叠印吞掉）。 */
    }
    ctx.fillStyle = '#9A8A6C';
    ctx.fillText(r[0], 140, y);
    /* R216b 续（UX 队列 U-014）：原代码 fillText(r[1], 140, y+0) 与标签
     * 同 x 同 y 叠印——「幸运数字」与「5 · 0」重叠成不可读模糊块。
     * 值右移到标签之后（x=460，标签「幸运时段」4 字 @38px ≈152px 宽，
     * 460 留足间距且色块 cx=420 起排不冲突）。 */
    ctx.fillStyle = '#3E3428';
    if (r[0] === '幸运时段' && r[1].length > 15) {
      /* U-014 续：值区从 x=460 起只有约 570px（38px 下约 15 字），
       * 三时段一行放不下——拆两行画。 */
      var segs = r[1].split('、');
      var l1 = segs.slice(0, 2).join('、');
      var l2 = segs.slice(2).join('、');
      ctx.fillText(l1, 460, y);
      if (l2) ctx.fillText(l2, 460, y + 50);
    } else {
      ctx.fillText(r[1], 460, y);
    }
  });

  // 出处三条（判据 10 可追溯）
  ctx.fillStyle = '#9A8A6C'; ctx.font = '400 30px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  _pArr(ec.basis).slice(0, 3).forEach(function (b, i) {
    var t = '· ' + _basisCn(b);   /* R2362：海报不再画裸字段路径 */
    if (Array.from(t).length > 26) {
      /* V-004：截断点避开英文键名中间——优先回退到最近的非字母数字字符。 */
      var cut = 25;
      for (var k2 = cut; k2 > 12; k2--) {
        if (!/[A-Za-z0-9_]/.test(t.charAt(k2)) && !/[A-Za-z0-9_]/.test(t.charAt(k2 - 1))) {
          cut = k2; break;
        }
      }
      t = _gSlice(t, cut) + '…';
    }
    ctx.fillText(t, 140, cardY + 480 + i * 44);
  });

  // 免责水印（判据 2：仅供娱乐标识，常显不折叠）
  ctx.textAlign = 'center';
  /* R218a-11：品牌水印 + 金句 hook——「@小满的解忧铺」+ 副标
   * 写在「知命 · 仅供娱乐」上方（保留底标过 check_poster 判据 12）。 */
  ctx.fillStyle = '#7A5C2E';
  ctx.font = '600 36px "LXGW WenKai","Noto Serif TC",serif';
  ctx.fillText('@小满的解忧铺', 540, 1440 - 150);
  /* R2351（R107-P2-页脚）：两句口号并一行——4 行 150px 太挤，
   * 品牌+口号+免责三行拉开行距反而更清爽。 */
  ctx.fillStyle = '#815934';
  ctx.font = '500 25px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  ctx.fillText('知命知趣知自己 · 为了更好地活', 540, 1440 - 104);
  ctx.fillStyle = '#B7A98A';
  ctx.font = '400 32px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  /* R3259（N5）：有引文的判词在分享图底标带上「可核验」——
   * 全网唯一性卖点跟着每张流出的图走。 */
  var _vc0 = false;
  try { _vc0 = !!(j && j.interpretation &&
    (j.interpretation.citations || []).length); } catch (eVC0) {}
  ctx.fillText(_vc0 ? '判词引自古籍 可核验 · 仅供娱乐'
                    : '知命 · 仅供娱乐', 540, 1440 - 50);

  return cv;
}

/* ── R198b（US5）：通用分享海报模板族──────────────────────────────
 * 七端点一套版式：标题区 / 大字结论 / 键值行 / 可选卡片区（塔罗画真图）。
 * 同源图片 drawImage 直绘（不污染外链判据）。 */
function _roundRectPath(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}
function _paintSharePoster(s, W, H) {
  /* R228r：畸形载荷防御——cards/lines 非数组、卡片缺 name 时静默纠正，
   * 不让分享海报把整段渲染抛死（历史 share 数据/schema 漂移可复现）。 */
  s = s || {};
  if (!Array.isArray(s.cards)) s.cards = [];
  if (!Array.isArray(s.lines)) s.lines = [];
  /* R230r（R29-#14）：元素级类型防御——数组对了但 name=42 照样崩
   * （slice is not a function）；统一字符串化。 */
  s.cards = s.cards.filter(function (c) { return c && c.name != null; })
    .map(function (c) {
      c.name = _pStr(c.name); c.sub = _pStr(c.sub); return c;
    });
  s.lines = s.lines.map(function (r) {
    /* R3398-P2-5：dot 是 daily-outfit 五行色点——归一化剥字段
     * 让 :534 的 r.dot 永假。保留并做 hex 白名单，脏值落 null。 */
    var _dot = _pStr(r && r.dot);
    return { k: _pStr(r && r.k), v: _pStr(r && r.v),
             dot: /^#[0-9a-fA-F]{3,8}$/.test(_dot) ? _dot : null };
  });
  var cv = document.createElement('canvas');
  cv.width = W; cv.height = H;
  var ctx = cv.getContext('2d');
  if (!ctx) return null;
  var S = W / 1080;
  ctx.setTransform(S, 0, 0, S, 0, 0);
  /* R209b：已批准的候选背景图（同步绘制需预加载——downloadPoster 前
   * warmPoster 已预热；未加载完成时回落渐变）。 */
  /* R230w：视图底图——s.view 由 buildShareData 注入；老海报/未加载
   * 完成时先回落 warm 再回落渐变（确定性口径不变）。 */
  /* R3422-P2-5（审）：墨色系按「意图底图」选、不按「实画底图」
   * 选——lilac 未加载回落奶油/渐变后，夜紫浅墨 #FFF6E8 印奶底
   * 隐形（tarot.png 慢网实态可复现）。_bgKey 随实际落底走。 */
  var _bgKey = _POSTER_BG_BY_VIEW[s && s.view] || 'warm';
  var bgImg = _posterBgFor(s && s.view);
  /* R3462 灵魂色谱：s.art 在场时底图不贴图——画家现场生成
   * 星云。深空渐变底 + 每个色带一团径向光晕（位置由 seed 定
   * 点、半径与透明度随占比），同盘同画确定性口径。 */
  var _saArt = (s && s.art && Array.isArray(s.art.bands)
    && s.art.bands.length) ? s.art : null;
  if (_saArt) {
    var _neb = ctx.createLinearGradient(0, 0, 0, 1440);
    _neb.addColorStop(0, '#1A1430'); _neb.addColorStop(1, '#0E0B1F');
    ctx.fillStyle = _neb; ctx.fillRect(0, 0, 1080, 1440);
    var _seed = (+_saArt.seed) >>> 0;
    var _rnd = function () {
      _seed = (_seed * 1664525 + 1013904223) >>> 0;
      return _seed / 4294967296;
    };
    _saArt.bands.forEach(function (b) {
      var _cx = 180 + _rnd() * 720, _cy = 260 + _rnd() * 920;
      var _r = 240 + b.frac * 560;
      var _g = ctx.createRadialGradient(_cx, _cy, 0, _cx, _cy, _r);
      _g.addColorStop(0, b.c + 'CC');
      _g.addColorStop(0.55, b.c + '55');
      _g.addColorStop(1, b.c + '00');
      ctx.fillStyle = _g;
      ctx.fillRect(0, 0, 1080, 1440);
    });
    /* 星点散斑：种子继续推进，与色带数无关的画质点缀。 */
    ctx.fillStyle = 'rgba(255,246,232,0.7)';
    for (var _sp = 0; _sp < 90; _sp++) {
      var _sx = _rnd() * 1080, _sy = _rnd() * 1440,
          _sr = _rnd() * 1.8 + 0.4;
      ctx.beginPath(); ctx.arc(_sx, _sy, _sr, 0, 6.3); ctx.fill();
    }
    _bgKey = 'lilac';   /* 深底→浅墨盘 */
    bgImg = null;
  } else if (!(bgImg && bgImg.complete && bgImg.naturalWidth)) {
    bgImg = POSTER_BG.warm;
    _bgKey = 'warm';
  }
  if (bgImg && bgImg.complete && bgImg.naturalWidth) {
    ctx.drawImage(bgImg, 0, 0, 1080, 1440);
  } else if (!_saArt) {
    var bg = ctx.createLinearGradient(0, 0, 0, 1440);
    bg.addColorStop(0, '#FDF8F0'); bg.addColorStop(1, '#F6EDE0');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, 1080, 1440);
    _bgKey = 'warm';
  }
  ctx.textAlign = 'center';

  /* R2349m（R75-P1-1/P2-3）：lilac 夜紫底上深色文字整体偏暗、
   * 副题被月亮面冲刷——深底换浅字调色板+深色晕影。 */
  var _ink = (_bgKey === 'lilac')
    ? { title: '#F5E3C0', sub: '#EADFC8', big: '#FFF6E8',
        halo: 'rgba(40,28,60,0.85)' }
    : { title: '#7A5C2E', sub: '#B7A98A', big: '#3E3428',
        halo: 'rgba(253,248,240,0.95)' };

  /* 标题 + 副题 */
  /* R2345（R62-P1-7）：标题换品牌快乐体——衬线粗体与全站声口不一致 */
  ctx.fillStyle = _ink.title;
  /* R2349p（R79-P0-1）：合婚双昵称 16 字上限 ×2 能到 35 字——60px 下
   * ~2010px 冲出画布。照抄 hook 行的 measureText 缩字号循环，兜底截断。 */
  var _title = _pStr(s.title) || '小满的签';
  var _ts = 60;
  ctx.font = _ts + 'px "ZCOOL KuaiLe","LXGW WenKai","Noto Serif TC",serif';
  while (_ts > 34 && ctx.measureText(_title).width > 960) {
    _ts -= 4;
    ctx.font = _ts + 'px "ZCOOL KuaiLe","LXGW WenKai","Noto Serif TC",serif';
  }
  if (ctx.measureText(_title).width > 960) {
    _title = _gSliceB(_title, 30) + '…';
  }
  ctx.fillText(_title, 540, 128);
  /* R2349t（R88-15b）：节日徽章——中秋🌕/春节🧧/冬至🥟/节气🌾，
   * 右上角一枚大 emoji，海报一眼时令（现有资产内调参，零新图）。 */
  if (s.badge) {
    ctx.font = '64px "Noto Sans Emoji","Apple Color Emoji",serif';
    ctx.textAlign = 'right';
    /* R2504（A-2）：setTransform 后坐标全是 1080 逻辑系，这里误用
     * 像素宽 W——低配 750 画布下徽章漂到 64% 画面宽处。 */
    ctx.fillText(s.badge, 1080 - 56, 128);
    ctx.textAlign = 'center';
  }
  if (s.subtitle) {
    ctx.fillStyle = _ink.sub; ctx.font = '400 32px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
    /* R2349（R65-P2-7）：底图星芒装饰会压副题行——给文字一圈
     * 奶白晕影（shadowBlur 沿字形外扩），字浮在星上仍可读。
     * R2349m：深底晕影换深色（白晕在夜紫上反而更糊）。 */
    ctx.save();
    ctx.shadowColor = _ink.halo;
    ctx.shadowBlur = _bgKey === 'lilac' ? 14 : 10;
    ctx.fillText(_gSliceB(s.subtitle, 24), 540, 182);
    ctx.restore();
  }

  /* 大字结论（最多两行，自动缩字号防溢出） */
  var big = _pStr(s.big);
  ctx.fillStyle = _ink.big;
  var bigSize = big.length > 14 ? 62 : (big.length > 9 ? 76 : 92);
  /* R3462s-3（审）：大字可能含灵兽/晶石 emoji——补彩色表情字
   * 体回落链，桌面机无 PingFang/YaHei emoji 时不再豆腐。 */
  ctx.font = '600 ' + bigSize + 'px "LXGW WenKai","PingFang SC","Microsoft YaHei","Noto Sans Emoji","Apple Color Emoji","Segoe UI Emoji",sans-serif';
  /* R212：三行上限（原两行导致「宜稳不」截断感），行距随字号自适应 */
  var words = wrapText3(ctx, big, 900);
  var bigGap = Math.round(bigSize * 1.35);
  words.forEach(function (ln, i) { ctx.fillText(ln, 540, 300 + i * bigGap); });

  /* 键值行卡片 */
  /* R233t（R51-P0-2）：原来一律 slice(0,4)——daily 的「忌」、
   * checkin-week 的第 5-7 天、taohua 强度等被静默切掉。按 view 给
   * 上限；行高按剩余空间自适应，不越进页脚水印区。 */
  var _lineCap = { daily: 7, 'checkin-week': 7, 'checkin-month': 6,
                   hehun: 6, 'daily-outfit': 5,
                   huangli: 6, birth: 5, bazi: 5,
                   /* R3398：daily 构建 6-7 行（吉签插签运）cap=5
                    * 把「先缓缓」天天切没——注释口径兑现到 7；
                    * dream/soulmate 的免责尾行、qiming 的出处行
                    * 同理被默认 cap4 静默切，提帽收口。 */
                   dream: 5, soulmate: 6, qiming: 5,
                   /* R3398-P3-11：taohua 全字段齐 6 行——旺期预告
                    * 末行被切，提帽 6。 */
                   taohua: 6,
                   moodweek: 5,
                   /* R3469：soulart 四元素行+最浓+口径共 6 行——
                    * 默认 cap4 把「最浓/口径」尾两行静默切没。 */
                   soulart: 6,
                   /* R3474：fortune_dir 加旺城行后共 6 行——默认 cap4
                    * 会把「小满说/口径」尾两行静默切没，提帽 6。 */
                   fortune_dir: 6,
                   /* R3477c-P1（亲审）：guardian/crystal 全字段齐 5 行
                    * ——cap4 把「口径」免责行静默切掉，提帽 6。 */
                   guardian: 6, crystal: 6,
                   'year-wrap': 6, mochi: 6 }[s.view] || 4;
  var lines = (s.lines || []).slice(0, _lineCap);
  /* R212：随大字行数下移卡片，避免重叠 */
  var cardY = (s.cards && s.cards.length ? 500 : 520) + Math.max(0, words.length - 2) * 60;
  /* R2350h（R107-合婚海报）：s.chip——大字与明细卡之间的亮分胶囊
   * （合拍指数此前只是 40px 普通行，晒点不够）。 */
  if (s.chip) {
    var _cT = _pStr(s.chip);
    ctx.font = '600 46px "LXGW WenKai","PingFang SC",sans-serif';
    var _cW = ctx.measureText(_cT).width + 96;
    var _cY = 300 + (words.length - 1) * bigGap + 66;
    ctx.fillStyle = '#E8668A';
    _roundRectPath(ctx, 540 - _cW / 2, _cY - 42, _cW, 84, 42); ctx.fill();
    ctx.fillStyle = '#FFFFFF';
    ctx.fillText(_cT, 540, _cY + 14);
    cardY += 96;
  }
  if (lines.length) {
    /* R233t：底部水印 y≈1330，卡片区 y≈880——明细区硬顶 1260，
     * 行数多时收行高（最低 64px 可容 7 行）。
     * R2349p（R79-P2-1）：lh 封顶 120 + cardY 固定 → 少行视图卡下
     * 留 300-700px 死白——行高上限放 150，且行块在剩余区间里
     * 垂直居中（下移量封顶 120px，给页脚留呼吸）。
     * R2504（A-1）：有卡片区（塔罗前三张）时硬顶收到 860——
     * 原 1260 让 ≥5 张牌阵的补位明细行整片落进卡座（880 起）
     * 被白卡盖住，「还有·共N张」永远不可见。 */
    var _linesTop = (s.cards || []).length ? 860 : 1260;
    /* 心情周记色点阵——7 色点横排收进明细卡首行（与 liuyao 条阵同
     * 一先例：view 专属元素挤进既有卡区，不另起版式）。点阵占高
     * _MDOT_H，行块按剩余高度自适应，几何与无点阵视图同口径。 */
    var _mdL = (s.view === 'moodweek') ? _pArr(s.moodDots) : [];
    var _MDOT_H = _mdL.length ? 130 : 0;
    /* R3393：流年K线柱带——与心情点阵同款「view 专属元素挤进卡区首行」
     * 先例。带占高 _KL_H，行块在其下排。 */
    var _klD = (s.view === 'bazi-kline') ? s.kline : null;
    var _KL_H = (_klD && _pArr(_klD.candles).length) ? 310 : 0;
    /* R3397：开运日历格带——与 K线柱带同款先例：月历格收进卡区
     * 顶部，行块在其下排。 */
    var _calD = (s.view === 'hlcal') ? s.cal : null;
    var _CAL_H = (_calD && _pArr(_calD.days).length) ? 380 : 0;
    var lh = Math.min(150, Math.max(64,
      (_linesTop - cardY - _MDOT_H - _KL_H - _CAL_H) / lines.length));
    /* R3260（实拍抓到的溢出）：每行是「小标签+大值」双行排版，
     * 末行值基线 = cardY+(n-1)·lh+62，框底旧口径 +40 只到
     * cardY+n·lh-20——lh 贴 64 下限时末行戳出框 18px。
     * 底 padding 40→76，框底 = 末行基线 +14 下沉量，不再溢出。 */
    var _LH_PAD = 76;
    var _cardH = lines.length * lh + _LH_PAD + _MDOT_H + _KL_H + _CAL_H;
    var _slack = _linesTop - (cardY - 60) - _cardH;
    if (_slack > 0) cardY += Math.min(120, Math.round(_slack / 2));
    /* R2504（A-1 兜底）：lh 贴 64 下限仍超硬顶时整块上提，
     * 保证行块底缘不越 _linesTop。 */
    if (cardY - 60 + _cardH > _linesTop) {
      cardY -= (cardY - 60 + _cardH) - _linesTop;
    }
    /* R3398-P3-16：上提没设下限——big 折 3 行 + 卡座 + ≥4 行明细
     * 时白卡可顶进大字第三行下沿。地板 = 大字末行基线 + 16。 */
    var _bigFloor = 300 + (words.length - 1) * bigGap + 60 + 16;
    if (cardY - 60 < _bigFloor) cardY = _bigFloor + 60;
    /* R3406-P2：地板下压可能顶破 _linesTop 硬顶——daily 卡座
     * 880 起，白卡底 >860 时末行值线（如「先缓缓」）被浮贴卡
     * 盖住。补救：先把行高压到 52 下限，仍超则从尾丢行到
     * 放得下为止（丢一行比糊一行强）。 */
    if (cardY - 60 + _cardH > _linesTop) {
      lh = Math.max(52, Math.min(lh,
        (_linesTop - cardY - _MDOT_H - _KL_H - _CAL_H - _LH_PAD) /
        lines.length));
      while (lines.length > 1 &&
             cardY - 60 + lines.length * lh + _LH_PAD + _MDOT_H +
             _KL_H + _CAL_H > _linesTop) {
        lines.pop();
      }
      _cardH = lines.length * lh + _LH_PAD + _MDOT_H + _KL_H + _CAL_H;
    }
    ctx.fillStyle = '#FFFFFF';
    _roundRectPath(ctx, 90, cardY - 60, 900, _cardH, 28); ctx.fill();
    ctx.strokeStyle = '#E8D9BC'; ctx.lineWidth = 2;
    _roundRectPath(ctx, 90, cardY - 60, 900, _cardH, 28); ctx.stroke();
    ctx.textAlign = 'left';
    /* 点阵：周X在上、色点居中、日期在下；未记的日子画空心环
     * （与页面 .mood-dot-empty 同语义）。 */
    if (_mdL.length) {
      var _dTop = cardY - 60 + 26;
      var _cellW = 900 / _mdL.length;
      ctx.textAlign = 'center';
      _mdL.forEach(function (d, i) {
        var _dx = 90 + _cellW * i + _cellW / 2;
        ctx.fillStyle = '#B7A98A';
        ctx.font = '400 22px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
        ctx.fillText(_pStr(d.wd), _dx, _dTop);
        ctx.beginPath();
        ctx.arc(_dx, _dTop + 40, 24, 0, Math.PI * 2);
        if (d.c) {
          ctx.fillStyle = d.c; ctx.fill();
          ctx.strokeStyle = 'rgba(62,52,40,.25)'; ctx.lineWidth = 2;
          ctx.stroke();
        } else {
          ctx.strokeStyle = '#C9BCA6'; ctx.lineWidth = 2.5; ctx.stroke();
        }
        ctx.fillStyle = '#B7A98A';
        ctx.fillText(_pStr(d.d), _dx, _dTop + 92);
      });
      ctx.textAlign = 'left';
    }
    /* R3393：流年柱带——卡区顶部 _MDOT 位之下再画 90 柱。 */
    if (_klD) {
      var _kcs = _pArr(_klD.candles);
      var _kx0 = 130, _kw = 820, _ky0 = cardY - 60 + 30;
      var _kh = _KL_H - 56;
      var _kmid = _ky0 + _kh * 0.62;
      var _kstep = _kw / _kcs.length;
      var _kbw = Math.max(3, Math.floor(_kstep) - 1);
      _kcs.forEach(function (c, i) {
        var x = _kx0 + i * _kstep;
        var hh = (Math.abs(c.score) / 4) * (_kh * 0.56);
        ctx.fillStyle = c.score > 0 ? '#C4624E'
          : (c.score < 0 ? '#8FA98A' : '#C9BCA6');
        ctx.fillRect(x, c.score >= 0 ? _kmid - hh : _kmid,
                     _kbw, Math.max(3, hh));
        if (c.age === _klD.this_age) {
          ctx.strokeStyle = '#7A5C2E'; ctx.lineWidth = 3;
          ctx.strokeRect(x - 3, _ky0 - 6, _kbw + 6, _kh + 12);
        }
        if ((c.flags || []).indexOf('换运') >= 0) {
          ctx.strokeStyle = '#D9CBAE'; ctx.lineWidth = 2;
          ctx.beginPath();
          ctx.moveTo(x, _ky0 - 4); ctx.lineTo(x, _ky0 + _kh + 4);
          ctx.stroke();
        }
        var _kfy = _ky0 + _kh + 26;
        if ((c.flags || []).indexOf('本命年') >= 0) {
          ctx.strokeStyle = '#C4624E'; ctx.lineWidth = 3;
          ctx.beginPath();
          ctx.arc(x + _kbw / 2, _kfy, 6, 0, Math.PI * 2); ctx.stroke();
        } else if ((c.flags || []).indexOf('冲太岁') >= 0 ||
                   (c.flags || []).indexOf('犯太岁') >= 0) {
          ctx.fillStyle = '#8A4A3C';
          ctx.beginPath();
          ctx.arc(x + _kbw / 2, _kfy, 5, 0, Math.PI * 2); ctx.fill();
        }
        if (c.age % 10 === 0) {
          ctx.fillStyle = '#B7A98A';
          ctx.font = '400 20px "LXGW WenKai","PingFang SC",sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(c.age + '岁', x + _kbw / 2, _ky0 + _kh + 58);
        }
      });
      ctx.strokeStyle = '#E0D4C0'; ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(_kx0 - 8, _kmid); ctx.lineTo(_kx0 + _kw + 8, _kmid);
      ctx.stroke();
      /* 今年标记 */
      var _kth = _kcs[_klD.this_age];
      if (_kth) {
        ctx.fillStyle = '#7A5C2E';
        ctx.font = '600 24px "LXGW WenKai","PingFang SC",sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('今年 ' + _pStr(_kth.ganzhi),
                     _kx0 + _klD.this_age * _kstep + _kbw / 2, _ky0 - 14);
      }
      ctx.textAlign = 'left';
    }
    /* R3397：开运月历格带——卡区顶部 weekday 头+日期格，
     * 吉日红圈（TOP3 加星标）、避让日灰叉、今天粗框。 */
    if (_calD) {
      var _cym = _pStr(_calD.ym) || '';           /* '2026-10' */
      var _cyy = +_cym.slice(0, 4), _cmm = +_cym.slice(5, 7);
      var _cdim = new Date(_cyy, _cmm, 0).getDate();
      var _cFirst = (new Date(_cyy, _cmm - 1, 1).getDay() + 6) % 7; /* 周一起 */
      var _cdays = {};
      _pArr(_calD.days).forEach(function (_c) {
        _cdays[+_c.d] = _c; });
      var _cToday = +_pStr(_calD.today_day);
      var _gx0 = 150, _gw = 780, _gcw = _gw / 7, _gch = 46;
      var _gy0 = cardY - 60 + 18;
      var _wds = ['一','二','三','四','五','六','日'];
      ctx.font = '500 20px "LXGW WenKai","PingFang SC",sans-serif';
      ctx.fillStyle = '#B7A98A'; ctx.textAlign = 'center';
      _wds.forEach(function (_w, _i) {
        ctx.fillText(_w, _gx0 + _i * _gcw + _gcw / 2, _gy0 + 24);
      });
      var _rows = Math.ceil((_cFirst + _cdim) / 7);
      for (var _cd = 1; _cd <= _cdim; _cd++) {
        var _cp = _cFirst + _cd - 1;
        var _cx = _gx0 + (_cp % 7) * _gcw + _gcw / 2;
        var _cy = _gy0 + 44 + Math.floor(_cp / 7) * _gch + _gch / 2;
        var _g = _cdays[_cd];
        if (_calD.mode === 'ji') {
          /* 避让图：忌它的日子灰叉+圈底提示。 */
          if (_g) {
            ctx.strokeStyle = '#B0A48E'; ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.moveTo(_cx - 9, _cy - 2); ctx.lineTo(_cx + 9, _cy + 14);
            ctx.moveTo(_cx + 9, _cy - 2); ctx.lineTo(_cx - 9, _cy + 14);
            ctx.stroke();
          }
        } else if (_g) {
          ctx.fillStyle = '#C4624E';
          ctx.beginPath();
          ctx.arc(_cx, _cy + 6, 19, 0, Math.PI * 2); ctx.fill();
          ctx.fillStyle = '#FFF8EE';
          ctx.font = '700 22px "LXGW WenKai","PingFang SC",sans-serif';
          ctx.fillText(String(_cd), _cx, _cy + 14);
          if (_g.rank && _g.rank <= 3) {
            ctx.fillStyle = '#7A5C2E';
            ctx.font = '600 15px "LXGW WenKai","PingFang SC",sans-serif';
            ctx.fillText('★', _cx + 26, _cy - 6);
          }
        } else {
          ctx.fillStyle = '#9A8B74';
          ctx.font = '400 21px "LXGW WenKai","PingFang SC",sans-serif';
          ctx.fillText(String(_cd), _cx, _cy + 13);
        }
        if (_cd === _cToday) {
          ctx.strokeStyle = '#7A5C2E'; ctx.lineWidth = 3;
          ctx.strokeRect(_cx - _gcw / 2 + 8, _cy - _gch / 2 + 2,
                       _gcw - 16, _gch - 4);
        }
      }
      ctx.textAlign = 'left';
    }
    /* R3260：行高 <95 时双行排版（标签上值下，62px 内距）会和下一行
     * 标签挤叠（daily 5 行 + 卡座时 lh=72 实测叠加）。行高不够就
     * 切单行「标签：值」——行高 ≥56 即呼吸充足。 */
    var _rowInline = lh < 95;
    lines.forEach(function (r, i) {
      /* R3469：带色点的行恒走单行——两行排版下点落在行纵中
       * 心，标签顶置/值底置，点孤零零悬在中间（灵魂色谱海报
       * 实测）。色点行=图例行，「dot 木：13%」单行才读得顺。 */
      var _ri = _rowInline || !!r.dot;
      var y = cardY + _MDOT_H + _KL_H + _CAL_H + i * lh + 10;
      /* R3327-P2-9：r.dot（hex）行前色点——穿搭档行的五行色
       * 上得了图；点在标签左侧固定位。 */
      var _dotY = cardY + _MDOT_H + _KL_H + _CAL_H + i * lh + Math.round(lh / 2);
      if (r.dot) {
        ctx.fillStyle = r.dot;
        ctx.beginPath(); ctx.arc(118, _dotY, 13, 0, Math.PI * 2); ctx.fill();
        ctx.strokeStyle = 'rgba(62,52,40,.25)'; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(118, _dotY, 13, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.fillStyle = '#B7A98A'; ctx.font = '400 34px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
      var _kx = 150;
      if (_ri) {
        y = cardY + _MDOT_H + _KL_H + _CAL_H + i * lh + Math.round(lh / 2) + 14;
        ctx.fillText(r.k + '：', 150, y);
        _kx = 150 + ctx.measureText(r.k + '：').width + 8;
      } else {
        ctx.fillText(r.k, 150, y);
      }
      ctx.fillStyle = '#3E3428'; ctx.font = '500 40px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
      var v = _pStr(r.v);
      /* R233t（R51-P1-4）：截断 15→22——四柱「戊寅·己未·辛酉·甲…」
       * 残字一眼假，命盘图的可信度就在四柱齐全。
       * R2349m（R75-P1-2）：「…、在生气 等 3 项」这类尾巴被拦腰
       * 截成「等 3…」——遇到「等N项」收尾时保住尾巴完整。 */
      var _vv = v;
      if (Array.from(v).length > 22) {
        /* R3337（审-中）：顿号/中点清单从词中截断（「动土」劈成
         * 「动」）像渲染出错——先词边截断凑整项，不足 1 项再退回
         * 原硬切。「等N项」尾巴照旧保留。 */
        var _mEq = v.match(/等\s*\d+\s*[项件条]?$/);
        var _keep = _mEq ? _mEq[0] : '';
        var _hasSep = v.indexOf('、') !== -1 || v.indexOf('·') !== -1;
        if (_hasSep) {
          var _items = v.split(/、|·/);
          var _cut = 21 - Array.from(_keep).length - 4;
          var _acc = '', _nLeft = 0;
          for (var _ii = 0; _ii < _items.length; _ii++) {
            var _cand = _acc + (_acc ? '、' : '') + _items[_ii];
            if (Array.from(_cand).length > _cut) {
              _nLeft = _items.length - _ii; break;
            }
            _acc = _cand;
          }
          if (_acc && _nLeft > 0) {
            /* R3353（审-P1）：_keep 自带「等N件」尾时再拼「等N项」
             * 出双计数器乱码（「…等1项等 4 件」）——_keep 非空用它的
             * 计数，不再自算。 */
            _vv = _acc + (_keep ? '…' + _keep
                                : '…等' + _nLeft + '项');
          } else {
            _vv = _gSlice(v, Math.max(6, 21 - Array.from(_keep).length)) +
              '…' + _keep;
          }
        } else {
          _vv = _gSlice(v, Math.max(6, 21 - Array.from(_keep).length)) +
            '…' + _keep;
        }
      }
      /* R2351（R109-P1-2）：按字数截断不测宽——22 字 × 40px ≈ 880px
       * 会冲出卡右缘。逐 2px 缩字号到放得下（最低 30px 再截）。 */
      var _vMax = 990 - _kx - 20;
      for (var _fz = 40; _fz > 30 &&
           ctx.measureText(_vv).width > _vMax; _fz -= 2) {
        ctx.font = '500 ' + _fz +
          'px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
      }
      ctx.fillText(_vv, _kx, _ri ? y : y + 52);
      /* R2349p（R79-P2-5）：幸运色行补色块圆点——legacy 版式有、
       * share 模板只印字。文字照画，色块排在值右侧。 */
      /* R3314（R3312-P2-6）：护身符海报行键是「开运色」——原只认
       * 「幸运色」，色点永不画。放宽两键。 */
      if (r.k === '幸运色' || r.k === '开运色') {
        var _cmap = { 红: '#C0392B', 紫: '#8E44AD', 黄: '#D4AC0D',
          棕: '#8D6E63', 黑: '#2C3E50', 蓝: '#2874A6', 青: '#148F77',
          绿: '#27AE60', 白: '#F2F3F4', 金: '#B7950B', 粉: '#FF8FAB',
          橙: '#E67E22', 灰: '#95A5A6' };
        var _scx = _kx + ctx.measureText(_vv).width + 40;
        var _scy = _rowInline ? y - 14 : y + 40;
        String(v).split(/\s*·\s*|\s*、\s*/).forEach(function (cn) {
          var hex = _cmap[cn.trim().charAt(0)];
          if (hex && _scx < 940) {
            ctx.fillStyle = hex;
            ctx.beginPath(); ctx.arc(_scx, _scy, 18, 0, Math.PI * 2); ctx.fill();
            ctx.strokeStyle = 'rgba(62,52,40,.25)'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(_scx, _scy, 18, 0, Math.PI * 2); ctx.stroke();
            _scx += 50;
          }
        });
      }
    });
    ctx.textAlign = 'center';
  }

  /* R2350d（R100-P2-7）：六爻海报中腰偏空——卦象数据就在响应里
   * （ben.lines：阳/阴/动爻），画六爻条形阵让卦「长」在图上：
   * 阳=整根实条，阴=两段断条，动爻尾缀红点。挤不下时跳过不画。 */
  var _lyL = (s.view === 'liuyao') &&
    _pArr((((s._src || {}).ben) || {}).lines);
  if (_lyL && _lyL.length === 6) {
    /* R2351（R109-P2）：原预算 `_gy+180<=1280` 在有任何明细行时
     * 恒不成立（条阵=死代码）。改挂「标题区底→明细卡顶」空档带：
     * 带高 ≥212px 才画且垂直居中，不够就跳过（密版式不硬塞）。 */
    var _bandTop = 560, _bandBot = lines.length ? (cardY - 60) : 1100;
    var _need = 6 * 26 + 36 + 20;
    if (_bandBot - _bandTop >= _need) {
      var _gy = _bandTop + Math.round((_bandBot - _bandTop - _need + 20) / 2);
      ctx.fillStyle = '#FFFFFF';
      _roundRectPath(ctx, 330, _gy - 18, 420, 6 * 26 + 36, 20); ctx.fill();
      ctx.strokeStyle = '#E8D9BC'; ctx.lineWidth = 2;
      _roundRectPath(ctx, 330, _gy - 18, 420, 6 * 26 + 36, 20); ctx.stroke();
      _lyL.forEach(function (L, i) {
        var _by = _gy + i * 26;
        ctx.fillStyle = '#5A4633';
        if (L && L.yang) {
          _roundRectPath(ctx, 390, _by, 300, 16, 8); ctx.fill();
        } else {
          _roundRectPath(ctx, 390, _by, 136, 16, 8); ctx.fill();
          _roundRectPath(ctx, 554, _by, 136, 16, 8); ctx.fill();
        }
        if (L && L.moving) {
          ctx.fillStyle = '#C43E3E';
          ctx.beginPath(); ctx.arc(712, _by + 8, 7, 0, Math.PI * 2); ctx.fill();
        }
      });
    }
  }

  /* 卡片区（塔罗：RWS 真图直绘；其他：文字卡） */
  var cards = (s.cards || []).slice(0, 3);
  if (cards.length) {
    /* R2504（A-1b）：ch 420→400——有明细行时卡座 880 起、底缘
     * 1300 会盖住品牌水印行（y≈1288）；收到 400 后底缘 1280，
     * 与水印留 8px 缝。 */
    var cw = 250, gap = (1080 - cards.length * cw) / (cards.length + 1);
    /* R2341（R57-P1-3）：无明细行时 cards 上提到 560——
     * 原来固定 880，大字(≤440)到卡片之间留 ~500px 空洞。
     * R3337（审-中）：有明细行时卡座底 1280 压进品牌水印行（基线
     * 1276、字形上沿 ~1240）——卡高收 40px，底缘退到 1240 以上。 */
    var ch = lines.length ? 360 : 400;
    var cy = lines.length ? 880 : 560;
    cards.forEach(function (c, i) {
      var cx = gap + i * (cw + gap);
      ctx.fillStyle = '#FFFFFF';
      _roundRectPath(ctx, cx, cy, cw, ch, 20); ctx.fill();
      ctx.strokeStyle = '#D8C6A4'; ctx.lineWidth = 3;
      _roundRectPath(ctx, cx, cy, cw, ch, 20); ctx.stroke();
      var iy = cy;
      if (c.img) {
        try {
          /* R3260：drawImage 硬拉伸→contain 适配——RWS 竖牌被
           * 226×270 横向拉胖 ~47%、日签横幅会被拉变形。保比例居中
           * 铺满上限，米白衬底让留白不突兀。
           * R3316（审-P1）：图区缩到 ch-160、文字区整体上抬——
           * 原 sub 基线 1250 的 28px 字形下沿叠进页脚品牌行
           * （36px 上沿 ~1240），五张海报底区糊字。 */
          var _tw = cw - 24, _th = ch - 160;
          var _iw = c.img.naturalWidth || c.img.width || 1;
          var _ih = c.img.naturalHeight || c.img.height || 1;
          var _sc = Math.min(_tw / _iw, _th / _ih);
          var _dw = Math.round(_iw * _sc), _dh = Math.round(_ih * _sc);
          ctx.save();
          _roundRectPath(ctx, cx + 12, cy + 12, _tw, _th, 14); ctx.clip();
          ctx.fillStyle = '#F6EFE2';
          ctx.fillRect(cx + 12, cy + 12, _tw, _th);
          ctx.drawImage(c.img,
            cx + 12 + Math.round((_tw - _dw) / 2),
            cy + 12 + Math.round((_th - _dh) / 2), _dw, _dh);
          ctx.restore();
        } catch (e) { /* 图未就绪则跳过，文字兜底 */ }
        iy = cy + ch - 148;
      } else {
        /* R3422-P2-7（审）：牌图/清单未加载时卡座画白底空框——
         * 米白图区+居中牌背纹，别像加载失败的残图。 */
        var _tw0 = cw - 24, _th0 = ch - 160;
        ctx.save();
        _roundRectPath(ctx, cx + 12, cy + 12, _tw0, _th0, 14); ctx.clip();
        ctx.fillStyle = '#F6EFE2';
        ctx.fillRect(cx + 12, cy + 12, _tw0, _th0);
        ctx.fillStyle = '#C9B283';
        ctx.font = '400 96px "LXGW WenKai","PingFang SC",sans-serif';
        ctx.fillText('✦', cx + 12 + _tw0 / 2, cy + 12 + _th0 / 2 + 34);
        ctx.restore();
        iy = cy + ch - 148;
      }
      /* R3254h（用户实测「鬼/可怕的东西」末字消失）：两重修正——
       * ①此前 textAlign 残留为 left，cx+cw/2 起点右偏、长名冲出
       *   卡缘；②_gSlice 硬切 6 字把「西」劈掉。改：绘制前显式
       *   center + 长名缩字号到 30px、截断放宽到 9 字。 */
      var _nm = _pStr(c.name);
      var _nmFs = _nm.length > 6 ? 30 : 38;
      ctx.textAlign = 'center';
      /* R3398-P3-17：9 字 ×30px ≈270px > 卡宽 250px 两侧出血——
       * 按卡宽实测量身缩字号，再截断兜底。 */
      ctx.font = '600 ' + _nmFs + 'px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
      while (_nmFs > 22 && ctx.measureText(_gSlice(_nm, 9)).width > cw - 24) {
        _nmFs -= 2;
        ctx.font = '600 ' + _nmFs + 'px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
      }
      var _nmDraw = _gSlice(_nm, 9);
      while (_nmDraw.length > 3 &&
             ctx.measureText(_nmDraw + '…').width > cw - 24) {
        _nmDraw = _nmDraw.slice(0, -1);
      }
      if (_nmDraw.length < _nm.length) _nmDraw += '…';
      ctx.fillStyle = '#3E3428';
      ctx.fillText(_nmDraw, cx + cw / 2, iy + 44);
      ctx.fillStyle = '#815934'; ctx.font = '400 28px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
      ctx.fillText(_gSlice(c.sub, 8), cx + cw / 2, iy + 88);
    });
  }

  /* R218a-11：品牌水印 + 金句 hook——海报底部分两行：
   * 1) 品牌水印「@小满的解忧铺 · 知命知趣知自己」（替原「知命 · 仅供娱乐」）
   * 2) 金句 hook（按 view 给不同内容，无 view 时通用）。 */
  ctx.textAlign = 'center';
  /* 水印行 */
  ctx.fillStyle = '#7A5C2E'; ctx.font = '600 36px "LXGW WenKai","Noto Serif TC",serif';
  /* R2350d（R100-P2-5）：底部 CTA 区距画布底缘 6px 贴边——整张带
   * 上移 32px，底缘留白 ~50px，长图在相册里不顶脚。
   * R3304（审-P3）：品牌行基线 1288 vs 免责 pill 顶 1298 只差 10px，
   * 字形下沿压在 pill 上——品牌行上移 12px 拉开。 */
  ctx.fillText('@小满的解忧铺', 540, 1276);
  /* R230r（R29-#11）：免责声明是合规件——花纹底图上浅棕字几乎不可读，
   * 给文字垫一条半透明米白衬底，任何背景下都可读。 */
  ctx.fillStyle = 'rgba(253,248,240,0.78)';
  _roundRectPath(ctx, 540 - 340, 1298, 680, 42, 21); ctx.fill();
  ctx.fillStyle = '#8A7A56'; ctx.font = '400 26px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  /* R229z续23（R11-#3）：分享图会离站传播，免责必须跟着走 */
  /* R3259（N5）：有引文时底标换成「可核验」口径——分享图是最大
   * 离站传播面，信任标签该跟着图走。 */
  var _vc1 = false, _src1 = s && (s._src || s);
  try { _vc1 = !!(_src1 && _src1.interpretation &&
    (_src1.interpretation.citations || []).length); } catch (eVC1) {}
  ctx.fillText(_vc1 ? '· 判词引自古籍 可核验 · 仅供娱乐 ·'
                    : '· 知命知趣知自己 · 仅供娱乐 ·', 540, 1324);
  /* 金句 hook（按 view 动态 + 数据驱动） */
  /* R218a-巡3 修复（N-02+N-04 同根因）：原 `j` 是父函数 _paintPoster 的形参，
   * 本函数 _paintSharePoster(s, W, H) 形参只有 s；j 在 share 分支闭包不可见，
   * 会抛 `j is not defined` → 海报浮层 + 差异化全失效。改用 s。
   * N-09 数据驱动金句需要父 j 的 warm/full_names/peach_zhi 等字段，_paintPoster
   * 已把 j 挂到 s._src（line 992 附近），这里优先用 s._src，无则回退 s。 */
  var hook = _posterHookForView(s && s.view, s._src || s);
  if (hook) {
    /* R230r（R29-#5）：hook 行不测宽会左右出画布（hehun 双方五行灌长串
     * 实测宽 1372px>1080）——先缩字号再截断兜底。 */
    hook = _pStr(hook);
    var _hs = 28;
    ctx.font = '500 ' + _hs + 'px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
    while (_hs > 16 && ctx.measureText(hook).width > 980) {
      _hs -= 2; ctx.font = '500 ' + _hs + 'px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
    }
    if (ctx.measureText(hook).width > 980) hook = _gSlice(hook, 34) + '…';
    /* R2341（R57-P1-1）：hook/CTA 在紫/樱底上对比度不足且两行
     * 字形互碰——两行合并垫同一块米白衬底（照抄免责 pill 做法）。 */
    /* R2345（R62-P1-7）：CTA 是海报转化位却最挤——pill 加宽到 88%，
     * hook/CTA 两行都在 pill 内（原 680px 宽，CTA 贴着 pill 底缘）。 */
    /* R2500（R144-P3-6）：hook 基线 1364×CTA 基线 1390 字形几乎相触
     * ——pill 下移加高，两行各让开一档。 */
    ctx.fillStyle = 'rgba(253,248,240,0.78)';
    _roundRectPath(ctx, 65, 1346, 950, 84, 22); ctx.fill();
    ctx.fillStyle = '#815934';
    ctx.fillText(hook, 540, 1374);
  }
  /* R231d（R37-F1/F10）：回流 CTA——海报底部一行邀请语，收到图的人
   * 知道去哪儿玩同款（部署域名未定时只引品牌名，不画裸 URL）。 */
  /* R2341：hook 缺席时 CTA 也要有衬底（P1-1 同根因） */
  if (!hook) {
    ctx.fillStyle = 'rgba(253,248,240,0.78)';
    _roundRectPath(ctx, 65, 1346, 950, 62, 22); ctx.fill();
  }
  ctx.fillStyle = '#7A5C2E';
  ctx.font = '400 26px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  /* R2350b（R99-P2）：CTA 换接收方口吻——只看图的人想测，教她
   * 去搜品牌名；「链接甩给 TA 就行」是对分享者说的话。
   * R2350f（R102-P1-2）：部署在真实域名时把 host 画进 CTA——图单飞
   * 也有回站路径；本地/内网自动不画。 */
  var _host = '';
  try {
    _host = (location.hostname || '').toLowerCase();
    if (!/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(_host) ||
        /(^|\.)(localhost|local|internal|lan)$/.test(_host) ||
        /^\d+\.\d+\.\d+\.\d+$/.test(_host)) _host = '';
  } catch (eH) { _host = ''; }
  ctx.fillText(_host ? ('→ ' + _host + ' 测你的同款 ✨')
                     : '搜「小满的解忧铺」· 测你的同款 ✨',
               540, hook ? 1414 : 1382);
  /* R3317-F：回流二维码——真实域名时画进 CTA pill 左端，
   * 扫码即回站（window.qrcode 由 app.js 懒加载，缺席静默跳过）。 */
  if (_host && typeof qrcode === 'function') {
    try {
      /* QR 边长顶到 pill 内高的上限——转发压缩后仍可扫
       * （WeChat 长按识别对 <60px 的码失败率明显升）。 */
      var _qh = hook ? 72 : 52;
      var _qy = 1346 + ((hook ? 84 : 62) - _qh) / 2;
      /* R3477a：扫码落到同款——QR 与复制链同口径携带 view 别名
       * 与小惊喜 sa 锚，扫守护兽海报不再只到首页。 */
      var _sv0 = (s && s.view) || '';
      var _qu = (location.origin || '') + '/?view=' +
        encodeURIComponent(
          (typeof _SHARE_VIEW_ALIAS === 'object' &&
            _SHARE_VIEW_ALIAS[_sv0]) || _sv0 || 'home') +
        '&from=poster';
      var _saQ = (typeof _SA_SHARE_KEY === 'object' &&
        _SA_SHARE_KEY[_sv0]) || '';
      if (_saQ) _qu += '&sa=' + _saQ;
      var _qr = qrcode(0, 'M'); _qr.addData(_qu); _qr.make();
      var _qn = _qr.getModuleCount();
      var _qc = Math.floor(_qh / (_qn + 6));
      var _qo = Math.floor((_qh - _qc * _qn) / 2);
      ctx.fillStyle = 'rgba(255,255,255,.95)';
      _roundRectPath(ctx, 84, _qy - 6, _qh + 12, _qh + 12, 10); ctx.fill();
      ctx.fillStyle = '#4A3620';
      for (var _rr = 0; _rr < _qn; _rr++) {
        for (var _cc = 0; _cc < _qn; _cc++) {
          if (_qr.isDark(_rr, _cc)) {
            ctx.fillRect(90 + _qo + _cc * _qc,
                         _qy + _qo + _rr * _qc, _qc, _qc);
          }
        }
      }
    } catch (eQR) { /* 画不出码就当没这功能 */ }
  }
  /* R230x（P2-8）：右下角小满吉祥物贴纸——圆形裁切+奶油色衬底，
   * 与底图区隔成「贴纸」观感；图未加载则跳过不画。 */
  if (POSTER_MASCOT.complete && POSTER_MASCOT.naturalWidth) {
    try {
      /* R2341（R57-P1-3）：tarot 卡片区 (880-1300) 与右下贴纸
       * (1216-1340) 重叠压第三张牌——有卡片时挪右上角。
       * R3398-P3-12：右上角又正好盖节日徽章（badge 画在
       * 1080-56,128）——两枚同位置时贴纸让到左上。 */
      var _mx = 974, _my = cards.length ? 76 : 1238;
      if (cards.length && s.badge) _mx = 106;
      ctx.save();
      ctx.beginPath(); ctx.arc(_mx, _my, 62, 0, Math.PI * 2); ctx.clip();
      ctx.drawImage(POSTER_MASCOT, _mx - 62, _my - 62, 124, 124);
      ctx.restore();
      ctx.strokeStyle = 'rgba(255,255,255,.85)'; ctx.lineWidth = 5;
      ctx.beginPath(); ctx.arc(_mx, _my, 62, 0, Math.PI * 2); ctx.stroke();
    } catch (e) { /* 画不出就跳过 */ }
  }
  return cv;
}

/* R218a-巡2：按海报 view 给一句金句 hook——N-09 数据化钩子：bazi/qiming/
 * taohua/hehun 端点用 warm 字段里的真实数据，daily/tarot/liuyao 走文案。
 * 视觉给 3 秒抓眼球的扎心金句，数据可空时回退到文案版。 */
function _posterHookForView(view, j) {
  var w = (j && j.warm) || {};
  /* bazi: 用日主 + 偏财运（warm 里有 elements 偏财运/事业指数时可读出） */
  if (view === 'bazi') {
    var ec = w.energy_card || {};
    var c = _pStr(ec.element);
    /* R233g（R44-P1-5）：「命格/一字真言」术语 → 用 warm 的白话名。 */
    var cw = _pStr(ec.element_warm);
    if (c || cw) return '你的能量底色是「' + (cw || c) + '」';
  }
  /* qiming: 用 TOP 1 名 + 评分（j 必有 full_names）；v2 用新评分口径 */
  var _fn = _pArr(j && j.full_names);
  if (view === 'qiming' && _fn[0] && _fn[0].full_name) {
    var top = _fn[0];
    var _fe1 = j.five_elements || {};
    /* R3319-P3：「参考分」工具腔出戏——海报钩子只说挑了哪个。 */
    return '古籍给你挑了「' + _pStr(top.full_name) + '」';
  }
  /* taohua: 用桃花支 + 强度 */
  if (view === 'taohua' && j) {
    var zhi = _pStr(j.peach_zhi);
    var stg = _pStr(j.strength);
    /* R233g（R44-P1-5）：海报 hook 去术语——「落在X支·强度待时」
     * 改人话。 */
    var _za = {'子':'鼠','丑':'牛','寅':'虎','卯':'兔','辰':'龙','巳':'蛇',
      '午':'马','未':'羊','申':'猴','酉':'鸡','戌':'狗','亥':'猪'}[zhi];
    if (zhi) return '桃花信号' +
      ({strong: '最近正旺', mid: '在慢慢升温', weak: '还在酝酿'}[stg] || '待时而动') +
      '，留意「' + zhi + (_za ? '（' + _za + '）' : '') + '」这个方向';
  }
  /* hehun: 用双方日主五行（R230r：畸形字段先过 _pStr，不画 [object Object]） */
  var _ha = _pStr(j && j.day_wx_a), _hb = _pStr(j && j.day_wx_b);
  if (view === 'hehun' && _ha && _hb) {
    return '你们是「' + _ha + ' 遇 ' + _hb + '」的路子 · ' +
      (j.day_wx_sheng ? '越处越热' : (j.day_wx_same ? '同气相属' : '互补也甜'));
  }
  /* R3319-P2：7 个此前落万能胶水的视图补数据驱动钩子。 */
  if (view === 'xzm' && j) {
    var _xa = _pStr(j.a), _xb = _pStr(j.b), _xsc2 = _pStr(j.score);
    if (_xa && _xb) {
      return (_xa + '座 × ' + _xb + '座') +
        (_xsc2 ? ' 的合拍指数在这' : ' 搭不搭？测出来了');
    }
  }
  if (view === 'bazi-yearly' && j) {
    var _yr2 = (j.calc && j.calc.yearly) || {};
    if (_yr2.ganzhi) return _pStr(_yr2.ganzhi) + '年的节奏替你排好了';
  }
  if (view === 'dream' && j) {
    var _ds2 = _pArr(j.symbols);
    if (_ds2.length && _ds2[0].name) {
      return '梦见「' + _pStr(_ds2[0].name) + '」——册子有话说';
    }
  }
  /* R3373：正缘画像——数据驱动金句（相遇信号做钩子）。 */
  if (view === 'soulmate' && j) {
    var _smt = _pStr(j._smTiming);
    if (_smt) return 'TA 在路上——' + _smt;
    return '盘里推出的 TA，气质长这样';
  }
  /* R3379：周记信——「用你真实记录拼的」是卖点本身。 */
  if (view === 'weekletter') return '用你上周真实记录拼的一封信';
  /* R3381：默契挑战——挑战感是钩子。 */
  if (view === 'mochi') {
    /* R3387 榜海报 vs 成绩条海报分开钩——榜的钩是排名引诱。 */
    if (j && j._mcb) return '你来了能排第几？';
    return '敢不敢测你们有多懂对方';
  }
  /* R3388：每日一签——签是求来的，「你也来求一支」是钩。 */
  if (view === 'qian') return '今天你的签是什么？';
  if (view === 'ansb') return '心里有个问题？来翻一页';
  /* R3417：还愿/跨年启封——一个是正反馈钩，一个是仪式感钩。 */
  if (view === 'wishecho') {
    if (j && j._wishecho && j._wishecho.ny) return '来写下你的新年愿望';
    return '来许个愿——等它成了回来还愿';
  }
  /* R3398-P3-7：避让日历配「好日子」钩是反着的——按 mode 分叉。 */
  if (view === 'hlcal') {
    var _hc2 = (j && j._hlcal) || {};
    return _hc2.mode === 'ji' ? '这个月哪几天别安排它？' : '你的好日子是哪天？';
  }
  if (view === 'bazi-kline') return '你的流年走势长什么样？';
  if (view === 'bandaid') return '睡不着的时候，这张贴管用';
  if (view === 'lucky' && j) {
    var _lc3 = _pStr(j.lucky && j.lucky.color);
    if (_lc3) return '今日开运色是「' + _lc3 + '」';
  }
  if (view === 'weekly' && j) {
    var _vd = _pStr(j.visitDays);
    if (_vd && _vd !== '0') return '这周小满陪了你 ' + _vd + ' 天';
  }
  /* 心情周记钩——记下几天就说几天的话，没记录就说点阵本身。 */
  if (view === 'moodweek' && j) {
    var _mwN = _pStr(j.recorded);
    if (_mwN && _mwN !== '0') {
      return '这周记下 ' + _mwN + ' 天心情——给自己鼓鼓掌';
    }
    return '把一周心情画成点点，翻翻也挺有意思';
  }
  if (view === 'renge' && j) {
    var _rn2 = _pStr(j._nick), _re2 = _pStr(j._elCn);
    if (_re2) {
      return (_rn2 ? '「' + _rn2 + '」是' : '测出来了——你是') +
        _re2 + '型人格';
    }
  }
  /* 默认文案版（R218a-11 原版）；
   * R233t（R51-P2-17）：5 个 view 共用同一句万能胶水——每 view 一句
   * 贴语境的。 */
  var hooks = {
    'liuyao': '卦不骗人，帮你读',
    'daily':  '今日签 · 小满给你划重点',
    'tarot':  '牌已经替你说了',
    'xingzuo': '星星今天这么安排',
    'checkin': '新的一天，小满还在等你',
    'checkin-week': '一周七天，天天有签', 'checkin-month': '一个月的好运战报',
    'huangli': null,  /* R2350a（R94-P1-3）：写死「今天」是错话——下方按日词给 */
    'birth':  '这张小卡是你的底色',
    /* R3318（审-P3-1）：开运壁纸此前落通用兜底——给一句壁纸语境钩。 */
    'daily-wap': '今日开运壁纸，换上就有好心情',
    /* R3327-P1-2：hook 与 _os.big 同句→底 pill 与 y300 大字双印。
     * 换差异钩。 */
    'daily-outfit': '跟着五行穿，顺到不像话 →',
    /* R3342：年报钩——晒语境（「打包带走」=下载语义双关）。 */
    'year-wrap': '这一年攒下的，都在这张卡里'
  };
  if (view === 'huangli' && hooks[view] == null) {
    /* 黄历页脚跟卡面日：今天→「今天」；其他→日词 */
    var _dw2 = '今天';
    try {
      var _jd = (j && j.date) || '';
      if (_jd) {
        var _tt = new Date(); _tt.setHours(0, 0, 0, 0);
        _dw2 = _hlDayWord(Math.round(
          (new Date(_jd + 'T00:00:00') - _tt) / 864e5));
      }
    } catch (eDW) {}
    return '老黄历' + _dw2 + '这么说';
  }
  return hooks[view] || '今天，明天，每一天，都值得被认真对待';
}

/** R193b（T3.3）：空闲时预热海报字体/栅格管线——首跑冷启动实测 51.7ms
 *  （≥50ms 长任务阈值）、稳态约 25ms；预热把冷启动成本移到页面加载期，
 *  用户点击「分享图」时走的就是热路径。产物即弃，零副作用。 */
/** R198b（US5）：从各端点响应提取统一海报形状 j.share。
 *  数据只取自 warm/确定性字段（不新增事实，宪法第三条口径）；
 *  塔罗卡图用已加载的 <img> 元素（同源，drawImage 直绘）。 */
function buildShareData(view, j) {
  var w = (j && j.warm) || {};
  var l0 = w.one_liner || '';
  /* R3353（审-P3）：海报日期统一取记录日（台账复看分享不标成
   * 今天）。提到函数顶层——base 外的 qiming/moodweek/信卡等分支
   * 也用它（原只在 base 内声明，外层引用 ReferenceError）。 */
  var _pd = _pStr(j && j._posterDate) || todayIso();
  function base(title, subtitle) {
    /* R218a-11：注入 view 字段供 _paintSharePoster 取金句 hook。 */
    /* R230y（R36-P3-2）：subtitle 空兜当天日期——海报带「今天的签」时效感 */
    /* R233t（R51-P2-15）：裸 ISO 日期「2026-09-20」默认副标
     * 全部视图统一「M月D日 · 周X」。 */
    /* R2349p（R79-P2-2）：默认副标与 _cnDateSub 口径统一（去月前导零）。 */
    var _defSub = _cnDateSub(_pd);
    return { title: title, subtitle: subtitle || _defSub, big: l0 || title,
             lines: [], cards: [], view: view };
  }
  switch (view) {
    /* R230r（R29-#1/#2）：入图字段一律过 _pArr/_pStr——后端 schema 漂移
     * 把 yi 传成字符串、clash 传成对象时不再崩分享链或画出 [object Object]。 */
    case 'daily': {
      /* R233n（R47-Top5-3）：日签副题 = 周X·农历·第N签——小红书
       * 「每日一签」形态，签号按日确定性哈希（同一天同一张签）。 */
      var _dd = _pStr(j && j.date);
      /* R3337（审-低）：j.lunar 有两路 schema——daily 响应里是
       * 「八月初八」字符串，黄历端点是 {month_cn,day_cn} 对象。
       * 原一律按对象取，字符串路径农历行静默丢失。 */
      var _dl = (j && j.lunar) || {};
      var _lunarSub = (typeof _dl === 'string' && _dl)
        ? ' · ' + _dl
        : ((_dl.month_cn || _dl.day_cn)
          ? ' · 农历' + (_dl.month_cn || '') + (_dl.day_cn || '') : '');
      var _dsub = _weekdayCn(_dd) + _lunarSub +
        ' · 第' + _signNo(_dd) + '签';
      /* R2349g（R68-P2）：签诗池 10→20——60 天首撞日从第 11 天推到第
       * 21 天后；「每日一签」感的关键在诗文不重复。 */
      /* R2349l（R73-P1-1）：签诗换真源——签号对应的卦名+白话签意
       * （与卡面解签同一签），不再是与签号无关的 20 条鸡汤池。 */
      var _dpoem = _signText(_dd) || '今天适合许愿';
      var _ds = { title: '今日签', subtitle: _dsub,
        /* R212：原 slice(0,18) 会把 summary 拦腰截断（「…宜稳不」）——
         * 改取第一个分号前的完整短句。 */
        big: (j && j.summary)
          ? (String(j.summary).split(/[；;]/)[0] || '今日份小确幸')
          : '今日份小确幸',
        /* R229z续23（R11-#8）：海报与卡面同口径——凶→缓 */
        lines: [{ k: '今日评分',
                  v: (function () {
                    /* R2350h（R107-共1）：等级值是真实计算结果——配星
                     * 级视觉，单字「平」收据感太弱。 */
                    var _lv = _pStr((j && j.level)) || '';
                    var _st = ({ '吉': '★★★★★', '小吉': '★★★★☆',
                                 '平': '★★★☆☆', '凶': '★★☆☆☆' })[_lv] || '';
                    return ((_lv === '凶' ? '缓' : _lv) || '—') +
                      (_st ? ' ' + _st : '');
                  })() },
                /* R233t（R51-P2-14）：地支原文「丑/未」上天书——转生肖。 */
                { k: '贵人属相', v: _pStr(j && j.noble) ?
                  _zhiToAnimal(j.noble) : '—' },
                /* R3261（R13）：财神方位上明细行——搞钱人群
                 * 晒图时自带的每日落点。 */
                { k: '财神方位', v: _pStr(j && j.money_dir) || '—' },
                { k: '宜试试', v: _clauseCut(_pStr(j && j.do) || '—', 20) },
                /* R2349p（R79-P2-3）：忌行与子句口径一致——顿号清单
                 * 在子句边界截，不拦腰断词。 */
                { k: '先缓缓', v: _clauseCut(_pStr(j && j.dont) || '—', 20) }],
        cards: [], view: view };
      _ds.lines.unshift({ k: '签诗', v: _dpoem });
      /* R2349t（R88-4c）：吉签海报也庆祝——「上上签」是可晒素材。 */
      if (j && j.level === '吉') {
        _ds.lines.splice(1, 0, { k: '签运', v: '上上签' });
      }
      /* R2349t（R88-2a/15b）：节日/节气上海报副题+右上徽章——
       * 中秋当天发出去的图自带时令由头（字段已在 daily 响应下发）。 */
      var _dfest = _pArr(j && j.festival)[0] ||
        _pStr(j && j.term && j.term.name);
      if (_dfest) {
        _ds.subtitle += ' · ' + _dfest;
        _ds.badge = { '中秋节': '🌕', '春节': '🧧', '冬至': '🥟',
                      '七夕': '💘', '元宵': '🏮', '端午': '🐉' }[_dfest] ||
          (j.term && j.term.name === _dfest ? '🌾' : '🎐');
      }
      /* R3260（N5 晒图升级）：判词档位场景横幅上海报——日签卡里
       * 已加载的 bear-scene-* 同源 <img> 直绘成卡座（与塔罗牌面/
       * 签面插画同管线）。图没加载到时静默缺省，海报照常出。 */
      try {
        var _lvArt = document.querySelector('#dailyLevel img.lv-b');
        if (_lvArt && _lvArt.complete && _lvArt.naturalWidth > 0) {
          /* R3316（审-P1）：卡内再写一遍店名=与页脚品牌行双落款，
           * 换成暖句（店名页脚已有）。 */
          _ds.cards = [{ img: _lvArt, name: '今日小天气',
            sub: '把好天气装进口袋' }];
        }
      } catch (eLA) {}
      /* R3319-G：今日牌缩略也上海报——与卡面同一张烘图；
       * 位向与塔罗海报同口径写进 sub（缩略图不旋转，与
       * 塔罗牌阵海报「逆位」只标注不翻图的先例一致）。 */
      try {
        var _dcEl2 = document.querySelector('#dailyTarot img.dc-thumb');
        if (_dcEl2 && _dcEl2.complete && _dcEl2.naturalWidth > 0 &&
            j.daily_card && j.daily_card.name) {
          _ds.cards.push({ img: _dcEl2,
            name: '今日牌 ' + _pStr(j.daily_card.name),
            sub: j.daily_card.upright ? '正位' : '逆位' });
        }
      } catch (eDC) {}
      return _ds;
    }
    case 'daily-outfit': {
      /* R3325：五行穿搭五档——色圆点用 lines 的 v 内联不了图，
       * tier 色落成「tag：colors」行，大吉行加 ★。 */
      var _of = (j && j.outfit) || {};
      var _oTiers = _pArr(_of.tiers);
      var _os = base('今日穿搭',
        _cnDateSub(_pStr(j && j.date)) +
          (_of.wx ? ' · ' + _of.wx + '日' : ''));
      _os.big = '穿对颜色，今天顺一半';
      _os.lines = _oTiers.map(function (t, i) {
        return { k: _pStr(t.tag) + (i === 0 ? ' ★' : ''),
                 dot: _pStr(t.hex) || null,
                 v: _pStr(t.colors) + ' · ' + _pStr(t.tip) };
      });
      if (!_os.lines.length) {
        _os.lines = [{ k: '大吉', v: '穿件亮色，提提气' }];
      }
      return _os;
    }
    case 'tarot': {
      var draws = _pArr(j && j.draws);
      /* R233t（R51-P1-7）：卡图不再按 DOM 顺序抓——复看/重渲后 DOM
       * 序与 draws 可能错位；改用 draws[].img/src 数据键（若有）。 */
      /* R3337（审-中）：大众占卜分享图——牌面图是晒点核心，
       * j._cardImgs 显式供图优先（堆卡 DOM 选择器与主阵不同源）。 */
      var imgs = (j && j._cardImgs) ||
        document.querySelectorAll('.tarot-card-front img');
      /* R3021（真修#18）：问题文本烤进可分享图=披露足迹外泄——危机/
       * 敏感问句不上副题（复用 app.js 全局镜像判定，同源口径）。 */
      var _tq = _pStr(j && j.question);
      var _tqSafe = _tq &&
        !(typeof feCrisis === 'function' && feCrisis(_tq)) &&
        !(typeof feSensitive === 'function' && feSensitive(_tq));
      /* R3353（审-P2）：问句缺席时副题尾悬「·」——两段拼法
       * 改 join，不留孤分隔符。 */
      var _sub = (_pStr(j && j.spread)
        ? '「' + _pStr(j.spread) + '」牌阵' : '');
      if (_tqSafe) _sub += (_sub ? ' · ' : '') +
        '你问的：「' + _gSlice(_tq, 16) + '」';
      var s = base('塔罗指引', _sub);
      /* R219b（P1-4）：海报兜底句去掉「牌面是象征，不是结论」免责套话 */
      /* R2349s（R86-P2-7）：「节制·正：调和，少硬刚」的「·正：」
       * 是内部编码格式漏到画上——转成顺读「节制（正位）：…」。 */
      var _tb = _pStr(l0).replace(/·\s*([正逆])\s*：/, '（$1位）：');
      /* R3353（审-P2）：单张物料说「这几张牌」量词穿帮——
       * 按实际牌数选量词。 */
      s.big = _tb || (draws.length <= 1
        ? '这张牌，值得你看一眼' : '今天这几张牌，值得你看一眼');
      s.cards = draws.slice(0, 3).map(function (d, i) {
        var el = imgs[i] && imgs[i].complete && imgs[i].naturalWidth > 0 ? imgs[i] : null;
        /* R2350h（R107-塔罗海报）：位置名（过去/现在/未来…）此前算出来
         * 却不上图——牌阵叙事丢光。拼进副标位。 */
        var _pos = _pStr(d && d.position);
        return { name: _pStr(d && d.name),
          sub: (_pos ? _pos + ' · ' : '') + ((d && d.upright) ? '正位' : '逆位'),
          img: el };
      });
      /* R2354（R112-P3-7）：>3 张的阵（celtic 10 张）海报只带前三位，
       * 「结果」位永远不上图——明细行续上第 4-6 位+总数收口。 */
      if (draws.length > 3) {
        s.lines = draws.slice(3, 6).map(function (d, i2) {
          return { k: _pStr(d && d.position) || ('第 ' + (i2 + 4) + ' 张'),
            v: _pStr(d && d.name) +
              (((d || {}).upright) ? '（正位）' : '（逆位）') };
        });
        s.lines.push({ k: '还有', v: '共 ' + draws.length + ' 张牌' });
      }
      /* R3447：万圣聊斋当值签——限定抽的判词上晒图（读 draw 侧
       * window 旗，j 是接口响应体不私挂键）。 */
      var _lzP = (typeof window !== 'undefined' && window.__trLiao) || null;
      if (_lzP && _lzP.c) {
        s.lines = s.lines || [];
        /* R3447：海报专用短判 t2——行值渲染 22 字硬截断且「·」
         * 触发清单折叠，名号去中点+短句整句放得下。 */
        var _lzV = _pStr(_lzP.c).replace(/·/g, '') + '：' +
          _pStr(_lzP.t2 || _lzP.t);
        s.lines.push({ k: '今夜当值', v: _clauseCut(_lzV, 22) });
      }
      return s;
    }
    /* R230d（R16-P2-2）：星座日运分享图——值宫 + 三维度摘要。 */
    case 'xingzuo': {
      /* R233t（R51-P1-6）：大字只印俩字星座名太孤——判词当大字，
       * 星座名挪副标。 */
      var _xzTd0 = _pArr(j && j.signs).filter(function (s) { return s && s.is_today; })[0];
      /* R2349s（R86-P1-6）：缺星座数据时「今日座」是病句——兜底
       * 换「今日星运」。 */
      var _xzSign = _pStr(j && j.today_sign);
      var sxz = base('星座日运',
        (_xzSign ? _xzSign + '座' : '今日星运') + ' · ' + _cnDateSub(j && j.date));
      var _xzTd = _xzTd0;
      sxz.big = _clauseCut(_pStr((j && j.today_note) || (_xzTd0 && _xzTd0.note) || l0) || '星星今天值班', 22);
      var _xzl = [];
      if (_xzTd && _xzTd.love) _xzl.push({ k: '爱情', v: _gSlice(_xzTd.love, 24) });
      if (_xzTd && _xzTd.career) _xzl.push({ k: '事业', v: _gSlice(_xzTd.career, 24) });
      if (_xzTd && _xzTd.wealth) _xzl.push({ k: '财运', v: _gSlice(_xzTd.wealth, 24) });
      /* R3304（审-P3）：白卡稀疏补丁——星座日运补一条「今日方向」
       * 次级行（sign_direction 确定性派生，非凑数字段）。 */
      var _xzDir = (_xzTd && _xzTd.direction) || '';
      var _xzDirTxt = { forward: '宜主动一点', hold: '宜稳住节奏',
                        observe: '宜先看看风向' }[_xzDir];
      if (_xzDirTxt) _xzl.push({ k: '今日方向', v: _xzDirTxt });
      sxz.lines = _xzl.slice(0, 4);
      return sxz;
    }
    case 'liuyao': {
      var sly = base('六爻占卜', '');
      /* R2349s（R86-P1-3）：古籍侧卦名是繁体（賁/復/臨/觀/兌/離…）
       * ——简体海报直出混排生僻繁体，先过映射表。
       * R2351（R109-P1）：大字标题（warm.one_liner 直出）同样要过——
       * 此前只罩明细行，标题「賁卦」对卡内「贲」打架。 */
      var _gs = {'賁':'贲','復':'复','臨':'临','觀':'观','兌':'兑',
        '離':'离','夬':'夬','姤':'姤','遯':'遁','蹇':'蹇','謙':'谦',
        '師':'师','比':'比','畜':'畜','隨':'随','蠱':'蛊','剝':'剥',
        '頤':'颐','過':'过','鹹':'咸','恆':'恒','壯':'壮','晉':'晋',
        '夷':'夷','睽':'睽','解':'解','損':'损','升':'升','困':'困',
        '井':'井','革':'革','鼎':'鼎','震':'震','艮':'艮','漸':'渐',
        '妹':'妹','豐':'丰','旅':'旅','巽':'巽','渙':'涣','節':'节',
        '孚':'孚','濟':'济','訟':'讼','蒙':'蒙','需':'需','履':'履',
        '泰':'泰','否':'否','乾':'乾','坤':'坤','屯':'屯','坎':'坎'};
      var _gsS = function (g) {
        g = _pStr(g);
        return g ? g.split('').map(function (c) {
          return _gs[c] || c; }).join('') : g;
      };
      /* R233t（R51-P2-13）：4 行全叫「依据」分不清——位置化标签。 */
      var _lyLbl = ['卦象', '提示', '走势', '小满捎话'];
      /* R2349m（R75-P2-1）：明细行与 hook 大字逐字重复时剔掉——不当复读机 */
      sly.lines = _pArr(w.details && w.details.basis)
        .filter(function (b) { return _pStr(b) !== l0; }).slice(0, 4)
        .map(function (b, i) { return { k: _lyLbl[i] || '看点', v: _basisCn(b) }; });
      /* R2341（R57-P2-2）：basis 空时退化行复读大字——改画卦名/
       * 动爻这些已有字段，明细区不当复读机。 */
      if (!sly.lines.length) {
        /* R2349p（R79-P1-2）：旧字段名（j.gua/j.moving…）与真实响应
         * 对不上（j.ben.gua_name/j.ben.moving_lines），fallback 恒走
         * 「结论」空壳——读真字段；变卦不同名时给出方向行。 */
        var _ben = (j && j.ben) || {}, _bian = (j && j.bian) || {};
        var _lg = _gsS(_ben.gua_name);
        var _lml = _pArr(_ben.moving_lines);
        var _lmn = ['初', '二', '三', '四', '五', '上'];
        var _lm = _lml.map(function (i) {
          return (_lmn[i - 1] || i) + '爻';
        }).join('、');
        if (_lg) {
          sly.lines = [{ k: '起到的卦', v: _lg }];
          if (_lm) sly.lines.push({ k: '动的那一爻', v: _lm });
          else sly.lines.push({ k: '动的那一爻', v: '静卦 · 格局稳住' });
          var _lgb = _gsS(_bian.gua_name);
          if (_lgb && _lgb !== _lg) {
            sly.lines.push({ k: '走向', v: _lg + ' → ' + _lgb });
          }
        } else {
          sly.lines = [{ k: '结论', v: _clauseCut(l0, 18) }];
        }
      }
      sly.big = _gsS(sly.big);   /* R2351：大字标题同样过简体映射 */
      return sly;
    }
    case 'qiming':
      /* R2349m（R75-P2-6）：副题补日期——其余视图副题都带时效。 */
      /* R2349m（R75-P2-7）：海报补五行行——「五行起名」主题缺席；
       * 真实缺行/偏弱兜底分开说（与后端口径一致不谎报）。 */
      var _qfe = (j && j.five_elements) || {};
      var _qmiss = _pArr(_qfe.missing), _qweak = _pArr(_qfe.weak);
      var _qfeLine = _qmiss.length ? ('缺 ' + _qmiss.join('、') + ' · 专补它')
        : (_qweak.length ? ('五行偏弱，宜补：' + _qweak.join('、'))
           : '五行俱全');
      /* R3304（审-P3）：备选连出两个同名标签 + 白卡稀——备选①②
       * 编号 + 首选补「出处」次级行（origin 字段确定性派生）。 */
      var _qAlt = ['', '①', '②'];
      var _qOrigin = _pStr((_pArr(j && j.full_names)[0] || {}).origin);
      return { title: '五行起名',
        subtitle: '按五行补缺 · ' + _cnDateSub(_pd),
        big: _gSlice((_pArr(j && j.full_names)[0] || {}).full_name || l0, 12),
        lines: [{ k: '五行', v: _qfeLine }].concat(
          _pArr(j && j.full_names).slice(0, 3).map(function (n, i) {
            /* R2349s（R86-P2-6）：「推荐 N」编号腔——首选/备选。 */
            return { k: (i === 0 ? '首选' : ('备选' + (_qAlt[i] || ''))),
                     v: _pStr(n && n.full_name) }; })).concat(
          _qOrigin ? [{ k: '名字出处', v: _gSlice(_qOrigin, 16) }] : []),
        cards: [], view: view };
    /* R218a-巡2（N-04）：补 3 case——之前 buildShareData 没有 bazi/taohua/hehun，
     * 直接走 default 返回 null，downloadPoster 拿不到 j.share，回落旧 bazi 专属
     * 版式，桃花/合婚海报只有 4 行键值（liuyao 模板错位套用）。三 case 用各自
     * 端点的真实字段画差异化海报：
     *   bazi   → 四柱 + 日主 + 能量卡字段
     *   taohua → 桃花支 + 红鸾/天喜 + 应期
     *   hehun  → 双方日主 + 冲/合/日主相生 + 桃相同
     * 同时把 shareBazi/shareTaohua/shareHehun 改为传正确的 view（之前 bazi 不
     * 传、taohua/hehun 错传 'liuyao'，导致海报内容错位/空白）。 */
    case 'birth': {
      /* R231d（R37-F14）：本命盘卡是全站最强「我也想测」素材——
       * 复用 bazi 字段画「你是 X 座」海报。 */
      /* R233t（R51-P1-5）：太阳星座是陌生人一秒能接的信息——调用处
       * 把 sunSign 结果挂 j._birth_sign 透传进来当大字。 */
      var _bsign = _pStr(j && j._birth_sign);
      /* R2349m（R75-P2-4）：副题「你是X座」与大字逐字重复——
       * 副题只留日期，星座交给大字。 */
      /* R2349s（R86-P2-12）：本命盘副标挂「生于」生日——「我的本命盘
       * · 9月21日周一」念着像分享当天是生日，日期数据是错的。
       * R2349t（R87-P2-5）：上游从未真传 year/month/day（死分支）——
       * 且印明文生日本就是隐私面倒退，直接收成日期兜底。 */
      var _birSub = _cnDateSub(_pd);
      var _bir = base('我的本命盘', _birSub);
      var _bp = String(_pillarsHonest(((j && j.paipan) || {}).render, (j || {}).hour_known) || '').split(/\s+/).filter(function (p) { return p.length >= 2; }).slice(0, 4);
      var _bec = (w && w.energy_card) || {};
      _bir.big = _bsign ? ('你是 ' + _bsign + '座') : (l0 || '本命已就位');
      _bir.lines = [];
      if (_bp.length) _bir.lines.push({ k: '生辰四柱', v: _bp.join(' · ') });
      var _bfe = (((j && j.calc) || {}).five_elements || {}).counts || {};
      /* R2349m（R75-P2-4）：「木 0.3·火 2·土 1.3」小数口径机器味——
       * 海报只留偏旺行（取整 ≥1），弱的本来就不该当卖点。 */
      var _bfx = Object.keys(_bfe)
        .map(function (k) { return [k, Math.round(_bfe[k])]; })
        .filter(function (p) { return p[1] >= 1; })
        .map(function (p) { return p[0] + ' ' + p[1]; }).join(' · ');
      if (_bfx) _bir.lines.push({ k: '五行偏旺', v: _clauseCut(_bfx, 20) });
      if (_bec.element) _bir.lines.push({ k: '本命', v: _pStr(_bec.element) });
      /* R2350d（R100-P2-7 续）：本命盘海报中腰偏空——warm 里现成的
       * one_liner 短评补一行，三行撑不满时不再留大片死白。 */
      var _bol = _pStr(w && w.one_liner);
      if (_bol) _bir.lines.push({ k: '小满短评', v: _clauseCut(_bol, 20) });
      if (!_bir.lines.length) _bir.lines = [{ k: '结论', v: '知己知命' }];
      /* R3252：五行人格分享图——doRenge 传入已加载的拟人熊
       * <img>，直绘成卡座；晒出去的「我是哪一型」是形象不是字。 */
      if (j && j._art) {
        _bir.cards = [{ img: j._art, name: '我的五行人格',
          sub: _pStr(j._artCap) || '日主定盘' }];
      }
      return _bir;
    }
    case 'checkin': {
      /* R233n（R47-Top5-2）：首日也走这张海报——连签 ≥3 标题挂天数，
       * 否则挂「今天的签」，big 主打抽中的签面（晒点更足）。 */
      var _stk = Number(j && j.streak) || 0;
      /* R233q（R47-P2 续）：满月款标记——连签 ≥30 的海报挂限定标，
       * 给「晒出去」再加一层稀缺感。 */
      var _ck = base(_stk >= 100 ?
          '🏮 百日传说款 · 连续 ' + _pStr(j && j.streak) + ' 天来小满打卡' :
          _stk >= 30 ?
          '🌕 满月款 · 连续 ' + _pStr(j && j.streak) + ' 天来小满打卡' :
          _stk >= 3 ?
          '我连续 ' + _pStr(j && j.streak) + ' 天来小满打卡' : '今天的好运签',
        _weekdayCn('') + ' · ' + _cnDateSub(_pd).split(' · ')[0]);
      _ck.big = '今天抽到「' + (_pStr(j && j.pick) || '好运签') + '」';
      /* R233t（R51-P2-12）：「打卡姿势」字段名错位（值是签面文案），
       * 口号恒同一句——连晒 7 天口号全同稀释新鲜感，上轮换池。 */
      _ck.lines = [
        { k: '今日签面', v: _pStr(j && j.pick) || '—' },
        { k: '连签', v: _stk ? (_stk + ' 天') : '第 1 天' },
        { k: '小满碎碎念', v: _dayPick([
            '今天也要好好生活呀', '把小日子过成想要的样子',
            '运气在排队，别急', '你比签上写的还好一点',
            '今天也是值得收藏的一天', '慢慢来，好戏在后头',
            '先把今天过好，明天有新签', '心里有光，日子就亮'], 'ckslogan') }];
      /* R3252：签面插画上海报——app.js 预载的奶油熊签面图直绘成
       * 卡座（与塔罗牌面同管线），抽到的那张签晒出去是「图」不是
       * 「字」。有插画卡时「今日签面」行与卡名重复，摘掉。 */
      if (j && j.art) {
        _ck.cards = [{ img: j.art,
          name: '「' + (_pStr(j && j.pick) || '好运签') + '」',
          sub: '今日签面' }];
        _ck.lines = _ck.lines.filter(function (r) {
          return r.k !== '今日签面';
        });
      }
      return _ck;
    }
    /* R233q：周报海报——近 7 天每行 M/D·周X·签面，big 挂打卡率。 */
    case 'checkin-week': {
      var _wd = (j && j.days) || [];
      var _hit = _wd.filter(function (d) { return d && d.opt; }).length;
      var _wk = base('我的本周签运',
        ((_wd[0] ? _cnDateSub(_wd[0].date).split(' · ')[0] : '') + ' ~ ' +
         (_wd[6] ? _cnDateSub(_wd[6].date).split(' · ')[0] : '')));
      _wk.big = '本周打卡 ' + _hit + '/7 天' +
        (j && j.streak >= 3 ? ' · 连签 ' + j.streak + ' 天' : '');
      /* R2350h（R107-周报）：高光签标 ✦——抽中稀有签面的日子一眼
       * 能看出，流水账变晒点。 */
      var _hi = { '开运蛋': 1, '暴富签': 1, '生日签': 1, '甜甜运': 1 };
      _wk.lines = _wd.map(function (d) {
        var dd = String(d.date || '');
        var _op = d.opt || '歇了一天';
        return { k: _weekdayCn(dd) + ' ' + dd.slice(5).replace('-', '/'),
                 v: _op + (_hi[d.opt] ? ' ✦' : '') };
      });
      return _wk;
    }
    case 'checkin-month': {
      /* R2352（R107-月报）：整月聚合——不走 31 行流水账，
       * 给「打卡天数/连签峰值/稀有签/最常翻牌/签运词」5 行战报。 */
      var _md = (j && j.days) || [];
      var _mm0 = (_md[0] && _md[0].date || '').slice(0, 7);
      var _hit = _md.filter(function (d) { return d && d.opt; }).length;
      var _mspec = base('我的本月签运',
        _mm0 ? (Number(_mm0.slice(5)) + ' 月 · 已攒 ' + _hit + ' 张签') : '');
      var _hi2 = { '开运蛋': 1, '暴富签': 1, '生日签': 1, '甜甜运': 1 };
      var _rare = _md.filter(function (d) { return _hi2[d.opt]; });
      /* 连签峰值（月内最长连续打卡段） */
      var _peak = 0, _run = 0;
      _md.forEach(function (d) {
        _run = d.opt ? _run + 1 : 0;
        if (_run > _peak) _peak = _run;
      });
      /* 最常翻的签 top2 */
      var _cnt = {};
      _md.forEach(function (d) {
        if (d.opt) _cnt[d.opt] = (_cnt[d.opt] || 0) + 1;
      });
      var _top = Object.keys(_cnt).sort(function (a, b) {
        return _cnt[b] - _cnt[a]; }).slice(0, 2);
      _mspec.big = '本月打卡 ' + _hit + ' 天' +
        (_rare.length ? ' · 稀有签 ' + _rare.length + ' 张' : '');
      _mspec.lines = [
        { k: '打卡天数', v: _hit + '/' + _md.length + ' 天' },
        { k: '连签峰值', v: _peak >= 2 ? (_peak + ' 天连签') : '还没连起来' }];
      if (_top.length) _mspec.lines.push(
        { k: '最常翻牌', v: _top.map(function (o) {
          return o + '×' + _cnt[o]; }).join(' · ') });
      if (_rare.length) {
        /* R2354（R112-P3-8）：「日期+签名 等」超 22 字被 _gSlice
         * 腰斩成裸「…暴…」——改按签名计数缩写，一行必进。 */
        var _rc = {};
        _rare.forEach(function (d) {
          _rc[d.opt] = (_rc[d.opt] || 0) + 1;
        });
        _mspec.lines.push({ k: '稀有签 ✦', v:
          Object.keys(_rc).map(function (o) {
            return o + '×' + _rc[o]; }).join(' · ') +
          '（共 ' + _rare.length + ' 张）' });
      }
      _mspec.lines.push({ k: '本月签运词', v:
        _hit >= 20 ? '全勤选手，锦鲤本鲤' :
        (_hit >= 10 ? '稳稳在线，好运常来' :
         (_hit >= 5 ? '隔三差五，运气在攒' : '初来乍到，签运开张')) });
      return _mspec;
    }
    case 'bazi': {
      var sb = base('今日命盘', '');
      var pillars = String(_pillarsHonest(((j && j.paipan) || {}).render, (j || {}).hour_known) || '').split(/\s+/).filter(function (p) { return p.length >= 2; }).slice(0, 4);
      var ec = (w && w.energy_card) || {};
      sb.big = l0 || '本命已就位';
      sb.lines = [];
      if (pillars.length) sb.lines.push({ k: '生辰四柱', v: pillars.join(' · ') });
      if (ec.element) sb.lines.push({ k: '本命', v: _pStr(ec.element) + (ec.element_warm ? '（' + _pStr(ec.element_warm) + '）' : '') });
      var _lc = _pArr(ec.lucky_colors), _ln = _pArr(ec.lucky_numbers);
      if (_lc.length) sb.lines.push({ k: '幸运色', v: _lc.slice(0, 3).map(_pStr).join(' · ') });
      if (_ln.length) sb.lines.push({ k: '幸运数字', v: _ln.map(_pStr).join(' · ') });
      if (!sb.lines.length) sb.lines = [{ k: '结论', v: _gSlice(l0, 15) || '知己知命' }];
      return sb;
    }
    /* R3304（审-P2）：五行人格海报此前套 'bazi' 模板——大标题
     * 「今日命盘」与人格物口径脱节。人格名当主标，五行+判词当明细。 */
    case 'renge': {
      var _rgs = base('五行人格', '');
      var _rn = _pStr(j && j._nick);
      var _re = _pStr(j && j._elCn);
      _rgs.big = _rn ? ('「' + _rn + '」') : (l0 || '测测你的五行人格');
      _rgs.lines = [];
      if (_re) _rgs.lines.push({ k: '五行人格', v: _re + '型' });
      var _rgF = (((j || {}).calc || {}).five_elements || {}).counts || {};
      var _rgTop = Object.keys(_rgF).sort(function (a, b) {
        return (parseFloat(_rgF[b]) || 0) - (parseFloat(_rgF[a]) || 0);
      }).slice(0, 2).join(' · ');
      if (_rgTop) _rgs.lines.push({ k: '料比较足的是', v: _rgTop });
      if (l0) _rgs.lines.push({ k: '一句话', v: _gSlice(l0, 18) });
      if (!_rgs.lines.length) {
        _rgs.lines = [{ k: '结论', v: '你是你这一型' }];
      }
      /* 人格形象卡同源直绘（与 birth/dream 同管线）。 */
      if (j && j._art) {
        _rgs.cards = [{ img: j._art, name: '我的五行人格',
          sub: _pStr(j._artCap) || _rn || '日主定盘' }];
      }
      return _rgs;
    }
    /* R3165：年度运势图——年底/生日季晒图格式（年度干支十神+顺劲/
     * 使劲月榜），数据源 calc.yearly.easy/hard（与 warm 行同口径）。
     * 月份只放「X月」——十神明细在卡面逐月条上，海报要一眼扫完。 */
    case 'bazi-yearly': {
      var sy = base('年度运势图', '');
      var _yr = (j && j.calc && j.calc.yearly) || {};
      var _TGL = { 比肩: '同伴力', 劫财: '分享力', 食神: '表达力',
                   伤官: '创造力', 偏财: '流动财', 正财: '稳定财',
                   七杀: '压力位', 正官: '规矩位', 偏印: '直觉力',
                   正印: '庇护力' };
      var _yrRel = _pStr(_yr.gan_rel);
      if (_yr.year && _yr.ganzhi) {
        sy.subtitle = _yr.year + ' · ' + _pStr(_yr.ganzhi) + '年';
      }
      sy.big = _yrRel
        ? ((_TGL[_yrRel] || _yrRel) + '之年')
        : (l0 || '一年有一年的节奏');
      sy.lines = [];
      if (_yr.ganzhi && _yrRel) {
        /* R3319-P2：十神原文（「丙午 · 正财」）同人话译名（「稳定财」）
         * 并挂——明细行也过 _TGL，不然一图两语。 */
        sy.lines.push({ k: '本年干支', v: _pStr(_yr.ganzhi) + ' · ' +
          (_TGL[_yrRel] || _yrRel) });
      }
      var _ezM = _pArr(_yr.easy).map(function (s) {
        return _pStr(s).split('（')[0]; }).filter(Boolean);
      var _hdM = _pArr(_yr.hard).map(function (s) {
        return _pStr(s).split('（')[0]; }).filter(Boolean);
      if (_ezM.length) sy.lines.push({ k: '顺劲月份', v: _ezM.join('·') });
      if (_hdM.length) sy.lines.push({ k: '使劲月份', v: _hdM.join('·') });
      if (!sy.lines.length) {
        sy.lines = [{ k: '结论', v: _gSlice(l0, 15) || '知己知命' }];
      }
      return sy;
    }
    case 'dream': {
      /* R3178：解梦海报——象征名上主位（「掉牙」比长句有记忆点），
       * 老话口径进明细行；免责句压尾防被当预言转发。 */
      var sd = base('解梦', '');
      var _dsyms = _pArr(j && j.symbols);
      var _dn = _dsyms.length ? _pStr(_dsyms[0].name) : '';
      sd.big = _dn ? ('梦见「' + _dn + '」') : (l0 || '梦是情绪的回声');
      sd.lines = [];
      _dsyms.slice(0, 2).forEach(function (s) {
        sd.lines.push({ k: _pStr(s.name) || '画面',
                        v: _clauseCut(_pStr(s.trad), 20) });
        sd.lines.push({ k: '回声', v: _clauseCut(_pStr(s.echo), 20) });
      });
      if (!_dsyms.length) {
        sd.lines.push({ k: '这梦', v: '不在常用册子里——是心事' });
      }
      sd.lines.push({ k: '口径', v: '梦是回声，不是预言' });
      /* R3254g：梦符熊直绘卡座（同 bazi 人格熊/checkin 签面模式）。 */
      if (j && j._art) {
        sd.cards = [{ img: j._art, name: _pStr(j._artCap) || '梦是回声',
          sub: '梦不是预言' }];
        /* 有图时明细留 1 组象征足够——版位让给卡座。 */
        sd.lines = sd.lines.slice(0, 2);
        sd.lines.push({ k: '口径', v: '梦是回声，不是预言' });
      }
      return sd;
    }
    case 'taohua': {
      var st = base('桃花运势', '');
      st.big = l0 || '桃花今日份';
      st.lines = [];
      /* R2349m（R75-P2-2）：地支黑话映生肖——「卯」陌生人看不懂，「兔」一秒接住 */
      var _zhiAn = {'子':'鼠','丑':'牛','寅':'虎','卯':'兔','辰':'龙','巳':'蛇',
        '午':'马','未':'羊','申':'猴','酉':'鸡','戌':'狗','亥':'猪'};
      var _zhiCn = function (z) {
        z = _pStr(z);
        return z && _zhiAn[z] ? (z + '（' + _zhiAn[z] + '）') : z;
      };
      if (_pStr(j && j.peach_zhi)) st.lines.push({ k: '桃花位置', v: _zhiCn(j.peach_zhi) });
      var _hp = _pArr(j && j.hit_pillars);
      if (_hp.length) st.lines.push({ k: '落在哪柱', v: _hp.map(function (p) { return ({ year: '年柱', month: '月柱', day: '日柱', hour: '时柱' })[p] || _pStr(p); }).join(' · ') });
      if (_pStr(j && j.hongluan)) st.lines.push({ k: '红鸾星', v: _zhiCn(j.hongluan) });
      if (_pStr(j && j.tianxi)) st.lines.push({ k: '天喜星', v: _zhiCn(j.tianxi) });
      /* R233t（R51-P1-9）：裸枚举 strong 上图社死——映射人话。 */
      var _stg = _pStr(j && j.strength);
      if (_stg) st.lines.push({ k: '桃花信号', v:
        ({ strong: '最近正旺', mid: '在慢慢升温', weak: '还在酝酿' })[_stg] || _stg });
      /* R3304（审-P3）：白卡稀疏补丁——大运应期（dayun_hits 确定性
       * 派生）补一条「旺期预告」。 */
      var _dyh = _pArr(j && j.dayun_hits);
      /* R3353（审-P3）：应期按公历年过滤——已过运（2003 起那种）
       * 不再当「旺期预告」挂图：先挑眼下在走的运，否则下一个将到的；
       * 全已过才报「上一回」。每运约十年。 */
      var _ny = new Date().getFullYear();
      var _dCur = null, _dNext = null, _dPast = null;
      _dyh.forEach(function (d) {
        var _ys = +(d && d.year_start || 0);
        if (!_ys) return;
        if (_ys <= _ny && _ny < _ys + 10) { if (!_dCur) _dCur = d; }
        else if (_ys > _ny) { if (!_dNext) _dNext = d; }
        else { _dPast = d; }
      });
      var _dy0 = _dCur || _dNext || _dPast;
      if (_dy0 && _dy0.pillar) {
        var _dyT = _dCur ? '（眼下就在这运里）'
          : _dNext ? '（' + _dNext.year_start + ' 起）'
          : '（' + _dPast.year_start + ' 起 · 上一回）';
        st.lines.push({ k: '旺期预告', v: _pStr(_dy0.pillar) + '运' + _dyT });
      }
      if (!st.lines.length) st.lines = [{ k: '结论', v: _gSlice(l0, 15) || '桃花待时而动' }];
      return st;
    }
    case 'soulmate': {
      /* R3373 正缘画像海报：气质型名上主位，traits 胶囊行入
       * lines，时机信号压一条，免责小字守恒——「样子是想象，
       * 信号是真的」。 */
      var _sm = base('正缘画像', '');
      _sm.big = _pStr(j && j._artCap) || 'TA 的气质画像';
      _sm.lines = [];
      (_pArr(j && j._smTraits)).slice(0, 3).forEach(function (t) {
        _sm.lines.push({ k: '气质', v: _pStr(t) || '' });
      });
      if (_pStr(j && j._smTiming)) {
        _sm.lines.push({ k: '相遇信号', v: _clauseCut(_pStr(j._smTiming), 20) });
      }
      if (_pStr(j && j._smTip)) {
        _sm.lines.push({ k: '小满说', v: _clauseCut(_pStr(j._smTip), 20) });
      }
      _sm.lines.push({ k: '口径', v: '样子是想象，信号是真的' });
      if (j && j._art) {
        _sm.cards = [{ img: j._art,
          name: _pStr(j._artCap) || '正缘画像',
          sub: '样子是想象，信号是真的' }];
        /* 有图时明细留白——但 traits 不在画里（画是氛围想象图），
         * 三条并一行留住；相遇信号有底部 hook 顶着，不再占行。 */
        _sm.lines = [{
          k: '气质',
          v: _pArr(j && j._smTraits).slice(0, 3).join(' · ')
        }].concat(_sm.lines.slice(-2));
      }
      if (!_sm.lines.length) _sm.lines =
        [{ k: '结论', v: 'TA 在路上' }];
      return _sm;
    }
    case 'fortune_dir': {
      /* R3456 旺你的方位海报：方位上主位大字，喜用依据/城市气质/
       * 贴士进 lines，小注守恒——「图个顺劲儿」免责口径。 */
      var _fd = base('旺你的方位', '');
      _fd.big = _pStr(j && j._fdDir) || '旺方';
      _fd.lines = [];
      if (_pStr(j && j._fdWx)) {
        _fd.lines.push({ k: '喜用', v: _pStr(j._fdWx) + ' 的方向' });
      }
      if (_pStr(j && j._fdWhy)) {
        _fd.lines.push({ k: '依据', v: _clauseCut(_pStr(j._fdWhy), 20) });
      }
      if (_pStr(j && j._fdVibe)) {
        _fd.lines.push({ k: '城市气质', v: _clauseCut(_pStr(j._fdVibe), 20) });
      }
      /* R3474：幸运城市点名上海报——晒点真城比气质描述更有传播钩。 */
      if (_pStr(j && j._fdCities)) {
        _fd.lines.push({ k: '你的旺城', v: _clauseCut(_pStr(j._fdCities), 20) });
      }
      if (_pStr(j && j._fdTip)) {
        _fd.lines.push({ k: '小满说', v: _clauseCut(_pStr(j._fdTip), 20) });
      }
      _fd.lines.push({ k: '口径', v: '图个顺劲儿，真搬家还看工作在哪' });
      if (!_fd.lines.length) _fd.lines =
        [{ k: '结论', v: '顺着自己的喜用走' }];
      return _fd;
    }
    case 'guardian': {
      /* R3457 守护图腾海报：灵兽上主位大字，喜用依据/气质/守护语
       * 进 lines，小注守恒——「图个念想」免责口径。 */
      var _gd = base('守护图腾', '');
      var _gdBig = _pStr(j && j._gdName) || '守护兽';
      var _gdGl = _pStr(j && j._gdGlyph);
      _gd.big = (_gdGl ? _gdGl + ' ' : '') + _gdBig;
      _gd.lines = [];
      if (_pStr(j && j._gdWx)) {
        _gd.lines.push({ k: '喜用', v: _pStr(j._gdWx) + ' 的灵兽' });
      }
      if (_pStr(j && j._gdWhy)) {
        _gd.lines.push({ k: '依据', v: _clauseCut(_pStr(j._gdWhy), 20) });
      }
      if (_pStr(j && j._gdVibe)) {
        _gd.lines.push({ k: '气质', v: _clauseCut(_pStr(j._gdVibe), 20) });
      }
      if (_pStr(j && j._gdGuard)) {
        _gd.lines.push({ k: '小满说', v: _clauseCut(_pStr(j._gdGuard), 20) });
      }
      _gd.lines.push({ k: '口径', v: '图个念想，真养宠物看缘分' });
      if (!_gd.lines.length) _gd.lines =
        [{ k: '结论', v: '灵兽替你守着' }];
      return _gd;
    }
    case 'crystal': {
      /* R3461 守护水晶海报：晶石上主位大字，喜用依据/气质/
       * 佩戴进 lines，小注守恒——「图个念想」免责口径。 */
      var _cr = base('守护水晶', '');
      var _crBig = _pStr(j && j._crName) || '守护晶';
      var _crGl = _pStr(j && j._crGlyph);
      _cr.big = (_crGl ? _crGl + ' ' : '') + _crBig;
      _cr.lines = [];
      if (_pStr(j && j._crWx)) {
        _cr.lines.push({ k: '喜用', v: _pStr(j._crWx) + ' 的晶石' });
      }
      if (_pStr(j && j._crWhy)) {
        _cr.lines.push({ k: '依据', v: _clauseCut(_pStr(j._crWhy), 20) });
      }
      if (_pStr(j && j._crVibe)) {
        _cr.lines.push({ k: '气质', v: _clauseCut(_pStr(j._crVibe), 20) });
      }
      if (_pStr(j && j._crWear)) {
        _cr.lines.push({ k: '小满说', v: _clauseCut(_pStr(j._crWear), 20) });
      }
      _cr.lines.push({ k: '口径', v: '图个念想，真买先量预算' });
      if (!_cr.lines.length) _cr.lines =
        [{ k: '结论', v: '晶石替你补着' }];
      return _cr;
    }
    case 'soulart': {
      /* R3462 灵魂色谱海报：底图交给画家生成式星云（s.art 携带
       * bands+seed，与卡内色条同一组数据），大字=色谱名，lines
       * =各色占比+最浓气+口径行。 */
      var _sa = base('灵魂色谱', '');
      _sa.big = '我的五行色谱';
      _sa.lines = [];
      var _saBd = (j && Array.isArray(j._saBands)) ? j._saBands : [];
      _saBd.forEach(function (b) {
        if (b && _pStr(b.wx) && _pStr(b.c) && +b.frac > 0) {
          _sa.lines.push({ k: _pStr(b.wx),
            v: Math.round(+b.frac * 100) + '%', dot: _pStr(b.c) });
        }
      });
      if (_saBd.length) {
        var _saTop = _saBd.slice().sort(function (a, b2) {
          return (+b2.frac || 0) - (+a.frac || 0); })[0];
        _sa.lines.push({ k: '最浓',
          /* R3480：「土气」=老土歧义，行名改「行」。 */
          v: _pStr(_saTop.wx) + '行占最大一片' });
      }
      _sa.lines.push({ k: '口径', v: '一人一幅，按五行权重画' });
      if (!_sa.lines.length) _sa.lines =
        [{ k: '结论', v: '色谱替你开着' }];
      /* 画家分支的 payload：seed 防脏值（非数回落 0）。 */
      _sa.art = { seed: (+_pStr(j && j._saSeed) || 0),
        bands: _saBd.map(function (b) {
          return { wx: _pStr(b.wx), c: _pStr(b.c),
                   frac: +b.frac || 0 };
        }).filter(function (b) {
          return b.wx && /^#[0-9a-fA-F]{6}$/.test(b.c) &&
            b.frac > 0; }) };
      return _sa;
    }
    case 'weekletter': {
      /* R3379 周记信海报：小记原文拆句入 lines（每行一条），
       * 周报感靠 hook 顶行。 */
      var _wl = base('小满的上周小记', '');
      _wl.big = '上周小记';
      _wl.lines = [];
      var _wTxt = _pStr(j && j._wlBody) || '';
      /* 按句号/换行拆句，最多 4 条，每条约 20 字截断。 */
      _wTxt.split(/[。\n]/).map(function (x) { return x.trim(); })
        .filter(Boolean).slice(0, 4).forEach(function (_seg) {
          _wl.lines.push({ k: '小记', v: _clauseCut(_seg, 22) });
        });
      if (!_wl.lines.length) {
        _wl.lines = [{ k: '小记', v: '新的一周，慢慢来就好' }];
      }
      return _wl;
    }
    case 'mochi': {
      /* R3381 默契挑战海报：分数是大字，名字对+判词+对上的题
       * 进 lines（对不上的题反成钩子「去测测你们差在哪」）。 */
      var _mc = (j && j._mc) || {};
      var _ms = base('默契挑战',
        _cnDateSub(_pStr(j && j.date)));
      /* R3387 默契榜海报：出题人晒「谁最懂我」排行——榜本身是
       * 邀请函（「你来了能排第几」），朋友扫榜心痒又来应战。 */
      var _mcb = (j && j._mcb) || null;
      if (_mcb) {
        _ms.big = '谁最懂我 · 默契榜';
        _ms.lines = [
          { k: '出题人', v: _pStr(_mcb.hn) || '我' },
          { k: '应战', v: _pStr(_mcb.n) || '0 位' }
        ];
        /* 奖牌 emoji 画布字库是豆腐块——用「第N名」文字位；
         * mochi 行 cap=6：出题人+应战+前三+「还有」恰好满。 */
        _pArr(_mcb.rows).slice(0, 3).forEach(function (r, i) {
          _ms.lines.push({ k: '第' + (i + 1) + '名',
            v: _clauseCut(_pStr(r.n) || 'TA', 8) + ' · ' +
               _pStr(r.s) + ' 分' });
        });
        if ((_mcb.n || 0) > 3) {
          _ms.lines.push({ k: '还有', v: (_mcb.n - 3) + ' 位' });
        }
        return _ms;
      }
      /* R3437 默契证书化：鼻祖小程序的收藏感来自「证书」框——
       * 题改成默契证书、选手改持证人、补「特发此证」落款，
       * 晒出去是纪念件不是分数截图。 */
      _ms = base('默契证书', _cnDateSub(_pStr(j && j.date)));
      _ms.big = '默契 ' + (_pStr(_mc.pct) || '0') + ' 分';
      _ms.lines = [
        { k: '持证人', v: (_pStr(_mc.hn) || '我') + ' × ' +
                          (_pStr(_mc.gn) || 'TA') },
        { k: '默契等级', v: _pStr(_mc.tier) || '测测才知道' },
        { k: '判语', v: _clauseCut(_pStr(_mc.line), 24) }
      ];
      /* R3433-P1-2（审）：自写题干直通晒图——敏感题面（身体/收入/
       * 前任比较）随成绩海报外流。进 lines 前过闸回落占位，
       * 与答案之书问句/还愿愿望同口径。 */
      var _mHit = _pArr(_mc.matched).filter(function (_mq) {
        return !(typeof feCrisis === 'function' && feCrisis(_mq)) &&
               !(typeof feSensitive === 'function' && feSensitive(_mq));
      });
      if (_mHit.length) {
        _ms.lines.push({ k: '想到一块儿',
          v: _clauseCut(_mHit.slice(0, 2).join(' · '), 20) });
      } else if (_pArr(_mc.matched).length) {
        _ms.lines.push({ k: '想到一块儿', v: '（心里那题）' });
      } else {
        _ms.lines.push({ k: '想到一块儿', v: '一道都没对上——正好处处有得聊' });
      }
      _ms.lines.push({ k: '落款', v: '小满的解忧铺 · 特发此证' });
      return _ms;
    }
    case 'qian': {
      /* R3388 每日一签海报：签号+吉凶是大字，签诗/小满说进
       * lines——签是「求来的答案」，晒语境足。 */
      var _qn = (j && j._qian) || {};
      var _qs = base('每日一签', _cnDateSub(_pStr(j && j.date)));
      _qs.big = '第' + (_pStr(_qn.n) || '?') + '签 · ' +
                (_pStr(_qn.luck) || '');
      var _qpoem = _pArr(_qn.poem);
      _qs.lines = [
        { k: '签题',
          v: (_pStr(_qn.topic) ? '问' + _pStr(_qn.topic) + ' · ' : '') +
             (_pStr(_qn.name) || '') },
        { k: '签诗', v: _clauseCut(_qpoem.slice(0, 2).join('，'), 20) },
        { k: '小满说', v: _clauseCut(_pStr(_qn.say), 24) }
      ];
      if (_qpoem.length > 2) {
        _qs.lines.push({ k: '下联',
          v: _clauseCut(_qpoem.slice(2, 4).join('，'), 20) });
      }
      return _qs;
    }
    case 'wishecho': {
      /* R3417 还愿海报：「愿望成了」是大字——许的愿/等了几天/
       * 回音进 lines。还愿笔记是小红书原生爆款文体，晒语境最足。 */
      var _we = (j && j._wishecho) || {};
      /* R3417：跨年启封海报（ny=1）——「新年愿望」大字，愿望/
       * 写于去年底/给N年进 lines。 */
      /* R3422-P2-4（审）：愿望原文是自由输入——不过闸直接烤进
       * 可晒图，敏感问句（离婚/堕胎/轻生类）会随海报外流。
       * 与 ansb:1762 同口径：命中危机/敏感闸回落占位。 */
      var _wt = _pStr(_we.t);
      var _wtSafe = _wt &&
        !(typeof feCrisis === 'function' && feCrisis(_wt)) &&
        !(typeof feSensitive === 'function' && feSensitive(_wt));
      var _wtShow = _wtSafe ? (_clauseCut(_wt, 18) || '（心里那个）')
        : '（心里那个）';
      if (_we.ny) {
        var _wy = base('跨年许愿', _cnDateSub(_pStr(j && j.date)));
        _wy.big = '新年愿望';
        _wy.lines = [
          { k: '写给明年', v: _wtShow },
          { k: '封于', v: '去年 12 月' },
          { k: '小满说', v: '启封了——' + (+_we.year || '') + ' 年慢慢让它长' }
        ];
        return _wy;
      }
      var _ws = base('愿望成真', _cnDateSub(_pStr(j && j.date)));
      _ws.big = '愿望成了';
      _ws.lines = [
        { k: '许的愿', v: _wtShow },
        { k: '等了', v: (+_we.days || 0) + ' 天' },
        { k: '小满说', v: _clauseCut(_pStr(_we.echo), 20) ||
          '许愿→成真，这条链走通了' }
      ];
      return _ws;
    }
    case 'ansb': {
      /* R3394 答案之书海报：翻到的那句话是大字，问题/书里还说/
       * 小动作进 lines——「书替我答了」的晒语境。 */
      var _ab = (j && j._ansb) || {};
      var _as = base('答案之书', _cnDateSub(_pStr(j && j.date)));
      _as.big = _clauseCut(_pStr(_ab.a) || '去吧', 12);
      /* R3398-P1：问句原文烤进可晒图前过危机/敏感闸——塔罗
       * :1114 同口径先例，命中回落默念位（隐私足迹不外泄）。 */
      var _aq = _pStr(_ab.q);
      var _aqSafe = _aq &&
        !(typeof feCrisis === 'function' && feCrisis(_aq)) &&
        !(typeof feSensitive === 'function' && feSensitive(_aq));
      _as.lines = [
        { k: '她问的是', v: _aqSafe ? _clauseCut(_aq, 14) : '（心里默念的）' },
        { k: '书里还说', v: _clauseCut(_pStr(_ab.h), 22) },
        { k: '可以试', v: _clauseCut(_pStr(_ab.d), 20) }
      ];
      return _as;
    }
    case 'cpdaily': {
      /* R3425 今日合拍指数海报：当日分是主体——「今天你们 N 分」
       * 的日更晒件，名字行/日支信号进 lines。 */
      var _cds = base('今日合拍指数', _pStr(j && j.date) + ' · ' +
        _pStr(j && j.ganzhi) + '日');
      _cds.big = (+_pStr(j && j.score) || 0) + ' 分';
      _cds.lines = [
        { k: '你们', v: _pStr(j && j.title) || '—' },
        { k: '小满说', v: _pStr(j && j.line) || '—' },
        { k: '提示', v: _pStr(j && j.tag) || '没什么大信号——平常过就好' }
      ];
      return _cds;
    }
    case 'muyu': {
      /* R3424 敲敲木鱼海报：攒数是主体——「攒了 N 点心安」晒语境，
       * 今天敲数/连敲进 lines。 */
      var _my = (j && j._muyu) || {};
      var _mys = base('敲敲木鱼', _cnDateSub(_pStr(j && j.date)));
      _mys.big = '攒了 ' + (+_my.total || 0) + ' 点心安';
      _mys.lines = [
        { k: '今天敲了', v: (+_my.today || 0) + ' 下' },
        { k: '连敲', v: (+_my.streak || 0) + ' 天' },
        { k: '小满说', v: '烦心事敲薄一层是一层' }
      ];
      return _mys;
    }
    case 'hlcal': {
      /* R3397 开运日历海报：月历格是主体（卡内格带），名次进
       * lines——「本月宜X的日子我圈好了」的晒语境。 */
      var _hc = (j && j._hlcal) || {};
      var _hcm = +_pStr(_hc.ym).slice(5, 7);
      var _hs = base((_hc.mode === 'ji' ? '避让日历' : '吉日日历'),
        _hcm ? (_hcm + '月 · ' + (_hc.mode === 'ji' ? '忌' : '宜') +
                _pStr(_hc.scene)) : '');
      _hs.view = 'hlcal';
      _hs.cal = _hc;
      var _hd = _pArr(_hc.days);
      /* R3398-P3-8：days 空时「0 天是好日子」+裸「 日」悬残——
       * 换兜底句/占位符。 */
      _hs.big = _hd.length
        ? (_hcm + '月共 ' + _hd.length + ' 天' +
           (_hc.mode === 'ji' ? '要绕开' : '是好日子'))
        : (_hcm + '月没有圈出' + (_hc.mode === 'ji' ? '要绕开' : '特别好') + '的日子');
      var _ht1 = _hd.filter(function (_x) { return _x.rank === 1; })[0];
      _hs.lines = [
        { k: '头名', v: _ht1 ? (_hcm + '月' + _ht1.d + '日') : '—' },
        { k: '事由', v: _pStr(_hc.scene) || '—' },
        { k: '圈里', v: _hd.slice(0, 5).map(function (_x) {
            return _x.d; }).join('、') + ' 日' }
      ];
      return _hs;
    }
    case 'bazi-kline': {
      /* R3393 人生K线海报：走势图是主体（卡内柱带），今年干支
       * 与顺/缓段进 lines。payload 直接吃 j.calc.kline。 */
      var _kk = (j && j.calc && j.calc.kline) || {};
      var _ks = base('人生K线',
        _pStr(_kk.birth_year) ? (_pStr(_kk.birth_year) + '年生 · 流年走势') : '');
      _ks.view = 'bazi-kline';
      _ks.kline = _kk;
      var _kt = _pArr(_kk.candles)[_kk.this_age];
      _ks.big = _kt
        ? (_kt.ganzhi + '年 · ' + (_kt.score > 0 ? '顺' : ( _kt.score < 0 ? '缓' : '平')))
        : '一年有一年的节奏';
      _ks.lines = [];
      if (_kt) {
        /* R3411-P2-13（终审）：海报「偏财（大运庚寅）」十神裸术语
         * 上可晒件——走 _TEN_GOD_TAG 白话口径（同伴/活水财/担当）。 */
        var _tg = (window._TEN_GOD_TAG || {})[_kt.gan_rel] ||
          _pStr(_kt.gan_rel);
        _ks.lines.push({ k: '今年', v: _pStr(_kt.ganzhi) + ' · ' +
          _tg + (_kt.dayun ? '（大运' + _pStr(_kt.dayun) + '）' : '') });
      }
      var _ke = _pArr(_kk.easy_segs).map(function (s) {
        return s.a + '–' + s.b + '岁'; });
      var _kh = _pArr(_kk.hard_segs).map(function (s) {
        return s.a + '–' + s.b + '岁'; });
      if (_ke.length) _ks.lines.push({ k: '顺段', v: _ke.join('、') });
      if (_kh.length) _ks.lines.push({ k: '缓段', v: _kh.join('、') });
      var _kf = _pArr(_kk.candles).filter(function (c) {
        return c.age >= _kk.this_age &&
               (c.flags || []).indexOf('冲太岁') >= 0; })[0];
      if (_kf) {
        _ks.lines.push({ k: '提个醒',
          v: _pStr(_kf.year) + '年（' + _kf.age + '岁）冲太岁，宜守' });
      }
      return _ks;
    }
    case 'hehun': {
      /* R230z（R36-P1-2）：海报标题用昵称对——「小鱼 × 阿哲」比
       * 「合婚配对」更有分享欲 */
      var _hhT = (j && (j.a_name || j.b_name)) ?
        ((j.a_name || '我') + ' × ' + (j.b_name || 'TA')) : '合婚配对';
      var sh = base(_hhT, '');
      sh.big = l0 || '甜度超标组合';
      sh.lines = [];
      /* R2349s（R86-P0-1）：海报分与卡面同源——此前前端另起一套
       * 打分（60+15combine+10gan_he…），同一对盘卡面 68/99、海报 70
       * 无分母，转发出去两个数对不上。直接读服务端 match_score。 */
      var _ms = (j && j.match_score != null) ? j.match_score : null;
      /* R3398-P3-19：_ms!=null 但为 NaN/非数时 chip 出「NaN /99」
       * ——后端恒发 int，此处只收防御层缝。 */
      if (_ms != null && !Number.isFinite(+_ms)) _ms = null;
      /* R2350h（R107-合婚海报）：分数上胶囊主位。
       * R2351（R109-P2）：chip 已写一遍「合拍指数 X/99」，明细行
       * 再写同数是双写——有分时删明细行，没分时留占位「—」。 */
      if (_ms != null) sh.chip = '合拍指数 ' + _ms + ' / 99';
      if (_ms == null) sh.lines.push({ k: '合拍指数', v: '—' });
      var _wa = _pStr(j && j.day_wx_a), _wb = _pStr(j && j.day_wx_b);
      if (_wa && _wb) {
        var sheng = j.day_wx_sheng ? ' · 越处越合拍'
          : (j.day_wx_same ? ' · 同气相属' : '');
        sh.lines.push({ k: '五行底子', v: _wa + ' 和 ' + _wb + sheng });
      }
      /* R233t（R51-P2-14）：「六冲/六合」行话不上图——人话映射。 */
      if (j && j.clash === true) sh.lines.push({ k: '需要磨合', v: '冲合有磕绊' });
      if (j && j.combine === true) sh.lines.push({ k: '天作之合', v: '本命相合' });
      if (j && typeof j.peach_same === 'boolean') sh.lines.push({ k: '桃花位置', v: j.peach_same ? '同支共振' : '各有桃花' });
      if (j && j.gan_he === true) sh.lines.push({ k: '天干相合', v: '有' });
      if (!sh.lines.length) sh.lines = [{ k: '结论', v: _gSlice(l0, 15) || '天作之合' }];
      return sh;
    }
    /* R229z续25：黄历分享图——唯一没海报的核心视图补齐（宜/忌/建除/值宿/
     * 冲煞/相冲提示全取自确定性字段，离站海报同样带仅供娱乐页脚）。 */
    case 'huangli': {
      var jh = j || {};
      var lun = jh.lunar || {};
      /* R2350a（R94-P1-3）：标题/大字/文件名原写死「今日」——翻别的天
       * 分享出去全是错话。日词跟卡面日走。 */
      var _pdw = '今天';
      if (jh.date) {
        var _t0 = new Date(); _t0.setHours(0, 0, 0, 0);
        var _off = Math.round(
          (new Date(jh.date + 'T00:00:00') - _t0) / 864e5);
        _pdw = _hlDayWord(_off);
      }
      var _pdwS = (_pdw === '今天') ? '今日' : _pdw;
      var shl = base(_pdwS + '宜忌',
        _cnDateSub(jh.date) +
        ((lun.month_cn || lun.day_cn) ? ' · 农历' + (lun.month_cn || '') + (lun.day_cn || '') : ''));
      var yiL = _pArr(jh.yi), jiL = _pArr(jh.ji);
      /* R230y（R36-P2-4）：海报上印白话——「宜 上任·谒贵」发出去没人懂，
       * 过映射表转人话，未命中词保留原味。 */
      var _yiP = yiL.map(function (x) { return _HL_YI_MAP[x] || _pStr(x); });
      var _jiP = jiL.map(function (x) { return _HL_JI_MAP[x] || _pStr(x); });
      /* R233t（R51-P1-8）：大字只放最有梗的一条宜——原三词拼接
       * wrapText 切出孤行「 · 许愿」悬在半空。 */
      shl.big = _yiP.length ? (_pdwS + '宜' + _yiP[0]) : (_pdwS + '平稳');
      shl.lines = [];
      /* R233t（R51-P1-8）：「前 2 条全量 + 等 N 件」不再拦腰截词。 */
      var _yiT = _yiP.slice(0, 2).join(' · ') +
        (_yiP.length > 2 ? '　等 ' + _yiP.length + ' 件' : '');
      var _jiT = _jiP.slice(0, 2).join(' · ') +
        (_jiP.length > 2 ? '　等 ' + _jiP.length + ' 件' : '');
      if (_yiP.length) shl.lines.push({ k: '宜', v: _yiT });
      if (_jiP.length) shl.lines.push({ k: '忌', v: _jiT });
      /* R2341（R57-P2-5）：单字行合并「建除·X / 值宿·Y」省一行 */
      /* R2349p（R79-P2-6）：「建除·除」单字撞上标签字读着叠音——
       * 值日用正式名「X日」（建日/除日/满日…）。 */
      if (jh.jianchu || jh.xiu) shl.lines.push({ k: '今日值日',
        v: (jh.jianchu ? _pStr(jh.jianchu) + '日' : '') +
           ((jh.jianchu && jh.xiu) ? ' · ' : '') +
           (jh.xiu ? _pStr(jh.xiu) + '宿' : '') });
      if (jh.chongsha) {
        /* R2349s（R86-P2-9）：「冲X煞Y」对非玩家是天书——属相+方位
         * 分开说人话。 */
        var _csAn = _pStr(jh.chongsha.chong_animal || jh.chongsha.chong);
        var _csDir = _pStr(jh.chongsha.sha_fang);
        var _cs = '';
        if (typeof jh.chongsha === 'object' && jh.chongsha) {
          _cs = _csAn ? ('属' + _csAn + '的朋友注意' +
            (_csDir ? ' · 朝' + _csDir + '先缓缓' : '')) : '';
        } else if (typeof jh.chongsha === 'string') {
          /* 字符串形态「冲龙煞北」同转人话 */
          var _cm = /冲(.{1})煞?(.{1})?/.exec(jh.chongsha);
          _cs = _cm ? ('属' + _cm[1] + '的朋友注意' +
            (_cm[2] ? ' · 朝' + _cm[2] + '先缓缓' : '')) : jh.chongsha;
        }
        if (_cs) shl.lines.push({ k: '提醒', v: _cs });
      }
      var _cf = _pArr(jh.conflict);
      if (_cf.length) {
        shl.lines.push({ k: '小满提一句', v: _cf.slice(0, 3).map(_pStr).join('·') + ' 宜忌两边都见，自己拿捏' });
      }
      return shl;
    }
    /* R2350d（R100-P1-4）：星座速配——全站填表成本最低的晒点此前
     * 没有分享图，只能手截一张无品牌小卡。 */
    /* R3260（UX-PLAN-R6 R9）：深夜创可贴——23-05 点聊天空态的
     * 出口卡。调研口径：深夜用户要的不是功能是一件小物——
     * 一句能存图带走的话 + 夜灯场景卡。 */
    case 'bandaid': {
      var _bd = base('深夜创可贴', _cnDateSub(_pd) + ' · 🌙');
      _bd.big = _dayPick([
        '你不是不够好，只是光还在路上找你',
        '今晚先把没处理完的事放一放——它们在原地等你，你先睡',
        '能撑到这么晚还在想办法的你，已经很努力了',
        '心下雨的时候，小满的灯一直给你留着'],
        'bandaid');
      _bd.lines = [
        { k: '小满说', v: '夜里的情绪不用急着解决，放一放天就亮了' },
        { k: '今晚试试', v: '把手机扣过去，喝口温水，先躺下' }];
      if (j && j._art) {
        _bd.cards = [{ img: j._art, name: '今夜小夜灯',
          sub: '今晚也要好好睡' }];
      }
      return _bd;
    }
    case 'xzm': {
      var _xm = base('星座速配', _cnDateSub(_pd));
      /* R3260：闺蜜/同事视角进副标——「巨蟹座×天蝎座」晒到群里
       * 时一句话说清测的是什么关系；恋人默认不加（感情腔即默认）。 */
      if (j && (j._rel === '闺蜜' || j._rel === '同事')) {
        _xm.subtitle += ' · ' + j._rel + '视角';
      }
      _xm.big = _pStr(j && j.a) + '座 × ' + _pStr(j && j.b) + '座';
      /* R3337（审-低）：判词「同款/同象/互补/相磨」是圈内速记——
       * 晒出去的卡加一句白话注释，外人一眼懂。 */
      var _xLb = _pStr(j && j.label);
      var _xGloss = { '同款': '同一个模子', '同象': '同象一家人',
                      '互补': '互补型组合', '相磨': '要多花心思' }[_xLb];
      _xm.lines = [
        /* R3398-P3-9：score 缺席时「/99」裸斜杠——占位符回落。 */
        { k: '合拍指数',
          v: _pStr(j && j.score) ? (_pStr(j.score) + '/99') : '—' },
        { k: '判词', v: _xLb + (_xGloss ? '（' + _xGloss + '）' : '') },
        { k: '小满说', v: _clauseCut(_pStr(j && j.line), 20) }];
      /* R3138：lines 面在场时分享图补一行「画风」摘要——晒出去
       * 的卡带场景句比单行判词更有记忆点。 */
      var _xsc = ((j && j.lines) || []).filter(function (l) {
        return String(l).indexOf('日常画风') === 0;
      })[0];
      if (_xsc) {
        _xm.lines.push({ k: '画风',
          v: _clauseCut(String(_xsc).replace('日常画风：', ''), 22) });
      }
      return _xm;
    }
    case 'lucky': {
      /* R3264（R29）：今日护身符——开运色/幸运数/财神/贵人属相。 */
      var _lu = base('今日护身符', _cnDateSub(_pd));
      _lu.big = _pStr(j && j.summary)
        ? (String(j.summary).split(/[；;]/)[0] || '今日份小确幸')
        : '今日份小确幸';
      _lu.lines = [
        { k: '开运色', v: _pStr((j && j.lucky && j.lucky.color) || '—') },
        { k: '幸运数', v: _pStr((j && j.lucky && j.lucky.num) || '—') },
        { k: '财神方位', v: _pStr(j && j.money_dir) || '—' },
        { k: '贵人属相', v: _pStr(j && j.noble) ? _zhiToAnimal(j.noble) : '—' }];
      try {
        var _lvArt2 = document.querySelector('#dailyLevel img.lv-b');
        if (_lvArt2 && _lvArt2.complete && _lvArt2.naturalWidth > 0) {
          _lu.cards = [{ img: _lvArt2, name: '今日小天气',
            sub: '把好天气装进口袋' }];
        }
      } catch (eL) {}
      return _lu;
    }
    case 'year-wrap': {
      /* R3342：年度小满报告——Wrapped 式全年足迹回顾。 */
      var _yr = base('小满年报',
        _pStr(j && j.year) + ' 年 · 小满陪你过的一年');
      /* R3353（审-P3）：顶部天数与明细「打卡 N 天」同口径——
       * 两值取大（visit 口径本应 ≥ checkin，镜像清盘后可能倒挂）。 */
      _yr.big = '这一年小满陪了你 ' +
        Math.max(+(j && j.visitDays) || 0, +(j && j.checkinDays) || 0) + ' 天';
      _yr.chip = '最长连打 ' +
        (_pStr(j && j.streakBest) || '0') + ' 天';
      _yr.lines = [
        { k: '打卡', v: (_pStr(j && j.checkinDays) || '0') + ' 天' },
        { k: '主心情', v: _pStr(j && j.moodMain) || '还没记过心情' },
        { k: '最常翻', v: _pStr(j && j.topView) || '还没怎么聊' },
        { k: '写小记', v: (_pStr(j && j.journalCount) || '0') + ' 篇' },
        { k: '完成仪式', v: (_pStr(j && j.ritualCount) || '0') + ' 天' },
        { k: '愿望成真', v: (_pStr(j && j.fulfilledCount) || '0') + ' 个' }];
      return _yr;
    }
    case 'weekly': {
      /* R3264（R39）：小满周报分享卡——近 7 天心情/常问/仪式数。 */
      var _wk = base('小满周报', _cnDateSub(_pd));
      /* R3314：usage:d:* 按天计数，海报同口径改「天」。 */
      _wk.big = '这周小满陪了你 ' + (_pStr(j && j.visitDays) || '0') + ' 天';
      /* R3304（审-P3）：「—」裸破折号挂白卡太冷——换兜底文案。 */
      _wk.lines = [
        { k: '主心情', v: _pStr(j && j.moodMain) || '这周心情还没记' },
        { k: '常问', v: _pStr(j && j.topView) || '还没怎么聊' },
        /* R3314（R3314-journal）：小记篇数上卡——写下的事该被看见。 */
        { k: '写小记', v: (_pStr(j && j.journalCount) || '0') + ' 篇' },
        { k: '完成仪式', v: (_pStr(j && j.ritualCount) || '0') + ' 天' }];
      return _wk;
    }
    case 'moodweek': {
      /* 心情周记卡——日期区间副题 + 主情绪大字 + 7 色点阵（moodDots
       * 收进明细卡首行，见 _paintSharePoster）+ 判词/连记/上周对比。
       * j 来自 _moodWeekData()，全本机数据不上线。 */
      var _mwD = _pArr(j && j.days);
      var _mws = base('这周的你',
        (_mwD[0] ? _cnDateSub(_mwD[0].date).split(' · ')[0] : '') + ' ~ ' +
        (_mwD[6] ? _cnDateSub(_mwD[6].date).split(' · ')[0] : ''));
      var _mwMain = (j && j.main >= 0 && typeof _MOOD_META !== 'undefined' &&
        _MOOD_META[j.main]) ? _MOOD_META[j.main] : null;
      _mws.big = _mwMain ? ('这周多是「' + _mwMain.t + '」')
                         : '这周还没攒下心情点';
      _mws.moodDots = _mwD.map(function (d) {
        var _mm = (d && d.m !== null && d.m !== undefined &&
                   _MOOD_META[d.m]) ? _MOOD_META[d.m] : null;
        return { wd: _weekdayCn(d.date), d: (d.date || '').slice(5).replace('-', '/'),
                 c: _mm ? _mm.c : '', e: _mm ? _mm.e : '', t: _mm ? _mm.t : '' };
      });
      _mws.lines = [];
      /* R3353（审-P1）：硬切把判词斩在词中（「…趁热用，惦」）——
       * 换子句截断带省略号。 */
      _mws.lines.push({ k: '小满说', v: _clauseCut(_pStr(j && j.verdict), 20) });
      _mws.lines.push({ k: '这周记下', v: _pStr(j && j.recorded) + '/7 天' });
      if ((j && j.streak) >= 2) {
        _mws.lines.push({ k: '连续记录', v: _pStr(j.streak) + ' 天' });
      }
      if (j && j.prevN > 0) {
        /* 卡面行 ≤20 字才不撞右缘截断——用紧凑口径，页面长句版
         * 留在视图 prevText。 */
        var _pv = '上周 ' + _pStr(j.prevN) + ' 天 · 这周 ' +
          _pStr(j.recorded) + ' 天';
        if (j.recorded > j.prevN) _pv += '，越记越顺手';
        else if (j.recorded < j.prevN) _pv += '，想记就记';
        _mws.lines.push({ k: '和上周比', v: _pv });
      }
      /* 小满插画：主情绪场景图（_shareMoodWeek 预载进 j._art）。 */
      if (j && j._art) {
        _mws.cards = [{ img: j._art, name: '小满这周陪你',
          sub: '慢慢过' }];
      }
      return _mws;
    }
    default:
      return null;
  }
}

var _POSTER_LAST = {};   /* view → ts：同视图 4s 内连点只弹浮层不再下载 */
var _POSTER_INFLIGHT = false;   /* R2513（审-P1）：生成管线在途锁——
 * on() 处理器不 return 时 guardedCall 微秒级放锁；裸 addEventListener
 * 入口在各平台 activeElement 也不一定落在按钮上。模块级旗标单点
 * 全覆盖：在途再点静默吞掉，绝不并行第二条管线/第二张同名 PNG。 */
async function downloadPoster(j, view) {
  if (_POSTER_INFLIGHT) return null;
  _POSTER_INFLIGHT = true;
  /* R3477b-P0：idle 预热后本函数直接接管入口（app.js stub 被
   * 覆盖），qrcode 懒载链被绕过——QR 在实际使用中永远不画。
   * 这里补一次懒载保证（已加载则瞬时 resolve）。 */
  try {
    if (typeof _loadQrJs === 'function' &&
        typeof qrcode !== 'function') await _loadQrJs();
  } catch (eQL) {}
  /* R233k（R45-§2）：按下到浮层弹出要 ~1.5-4s（底图 decode+字体
   * load），原零反馈。触发按钮立即转忙态直到流程结束。 */
  var _pbtn = document.activeElement;
  if (_pbtn && _pbtn.tagName === 'BUTTON' && !_pbtn.disabled) {
    _pbtn.classList.add('is-working');
    _pbtn.setAttribute('aria-busy', 'true');
    _pbtn.disabled = true;
  } else { _pbtn = null; }
  try {
    return await _downloadPoster(j, view);
  } finally {
    _POSTER_INFLIGHT = false;
    if (_pbtn) {
      _pbtn.disabled = false;
      _pbtn.classList.remove('is-working');
      _pbtn.removeAttribute('aria-busy');
    }
  }
}
/* R2341（R57-P0-1）：收集海报将绘制的全部文案——LXGW 子集按
 * unicode-range 懒加载，canvas fillText 命中未加载子集会回落系统
 * 字体（豆腐块）。fonts.load(spec, text) 会按 text 的码位拉起
 * 对应子集，所以这里把 title/subtitle/big/lines/cards/hook/页脚
 * 常量全拼上。 */
function _posterTextCollect(s) {
  var t = '';
  try {
    if (s) {
      t += _pStr(s.title) + _pStr(s.subtitle) + _pStr(s.big);
      /* R2513（审-P2）：chip（hehun「合拍指数 X / 99」胶囊）漏收——
       * 命中未加载 unicode-range 子集时胶囊文字回落系统字体。 */
      t += _pStr(s.chip);
      (s.lines || []).forEach(function (r) {
        t += _pStr(r && r.k) + _pStr(r && r.v); });
      (s.cards || []).forEach(function (c) {
        t += _pStr(c && c.name) + _pStr(c && c.sub); });
      /* 心情周记点阵的周X/日期标签——入预载集，不然点阵下小字
       * 命中未加载子集回落系统字体（同 P1-1 根因）。 */
      (s.moodDots || []).forEach(function (d) {
        t += _pStr(d && d.wd) + _pStr(d && d.d) + _pStr(d && d.t); });
      var _h = _posterHookForView(s.view, s._src || s);
      t += _pStr(_h);
      /* 旧版式（无 j.share）走 bazi 专属模板：四柱 pills + one_liner +
       * 能量卡行——巳/壬/酉这些支干字最容易踩豆腐块。 */
      var _w = s.warm || {}, _pp = s.paipan || {}, _e = _w.energy_card || {};
      /* R3235：字体预载文案与画面同源——时辰未知不预载默认午时的支干字。 */
      t += _pStr(_pillarsHonest(_pp.render, (s._src || s).hour_known)) + _pStr(_w.one_liner);
      t += _pStr(_e.element) + _pStr(_e.element_warm);
      ['lucky_colors', 'lucky_numbers', 'lucky_hours', 'basis'].forEach(function (f) {
        (_pArr(_e[f])).forEach(function (x) { t += _pStr(x); });
      });
      /* 键值行标签常量 */
      t += '今日命盘幸运色数字时段本命';
      /* R3398-P3-14：K线柱带/月历格带/免责行漏收集——无 CJK 全集
       * 字体的机器上这些字会画豆腐块。 */
      var _kl = s.kline;
      if (_kl && _pArr(_kl.candles).length) {
        _kl.candles.forEach(function (c) {
          t += _pStr(c && c.ganzhi) + _pStr(c && c.age);
        });
        t += '岁今年本命冲太犯';
      }
      var _cl = s.cal;
      if (_cl && _pArr(_cl.days).length) {
        t += '一二三四五六日★' + _pStr(_cl.ym) +
             _pStr(_cl.scene) + (_cl.mode === 'ji' ? '忌' : '宜');
        _pArr(_cl.days).forEach(function (d) {
          t += _pStr(d && d.d); });
      }
      t += '判词引自古籍可核验';
    }
  } catch (e) {}
  /* 页脚常量 + 旧版式 drawPoster 的固定串 + 各视图兜底文案也要覆盖 */
  /* R2350b（R99-P2）：预热集与现役 CTA 对齐（「铺/的」等字原不在
   * 集里，命中未加载子集时回落系统字体）。 */
  return t + '知命，是为了更好地活@小满的解忧铺·知命知趣知自己' +
    '仅供娱乐测你的同款→搜「」✨' +
    '小满说这周记下和上周比连续记录天慢慢过陪你';
}

async function _downloadPoster(j, view) {
  /* R230q（R28-P3-13）：连点分享每次都真下载——下载目录堆 N 张同名图
   * 还触发浏览器「多次下载」权限弹窗。4s 内同视图只给预览浮层。 */
  var _vkey = view || 'default';
  /* R2349（R65-P1-1）：键不存在时 (now - 0) < 4000 恒真——落地 4s 内
   * 首点被误吞「刚保存过」。必须先验键在表。 */
  var _dup = (_vkey in _POSTER_LAST) &&
    (performance.now() - _POSTER_LAST[_vkey]) < 4000;
  /* R193b：外壳返回 {canvas,w,h}；auto 模式 >50ms 自动降级 750×1000。
   * R198b（US5）：view 传入时先 buildShareData 注入 j.share（通用模板）；
   * 不传则保持 bazi 专属旧版式。
   * R218a-巡2（N-02 虚标重做）：画完海报后**弹浮层**给用户看——之前
   * `canvas.toBlob()` 静默触发下载，用户在小红书场景下完全不知道图
   * 在哪、怎么用。本轮补 modal：海报图 + 关闭按钮（点遮罩/ESC 都关）
   * + 长按图片保存到相册的提示文案。下载仍走 toBlob（兼容 desktop）
   * 浮层只是补一层视觉反馈。 */
  /* R2349m（R75-P1-3）：_idlePrefetch 只在进功能视图时触发——首页
   * 日卡直接点分享图时底图/吉祥物 src 为空，产出无底图素版海报。
   * 分享动作本身就是「这张海报我要了」的信号，先补预拉再等解码。 */
  try { _idlePrefetch(); } catch (eP0) {}
  if (view) {
    /* R233n：daily 海报要农历——daily 响应不含 lunar，懒取一次
     * 当日黄历补齐（失败则海报退化为无农历副题）。 */
    if (view === 'daily' && j && !j.lunar && typeof api === 'function') {
      try {
        var _hlj = await api('/api/huangli?date=' +
          encodeURIComponent(j.date || todayIso()), { silent: true });
        if (_hlj && _hlj.lunar) j = Object.assign({}, j, { lunar: _hlj.lunar });
      } catch (e0) {}
    }
    var s = buildShareData(view, j);
    /* R3398-P3-15：未知 view → buildShareData null → 回落画近乎
     * 空白的旧版命盘——张冠李戴还当正常出图。直接拒出 + 回音。 */
    if (s) {
      j = Object.assign({}, j, { share: s });
    } else {
      showToast('这张图的版式还没做好，换个分享入口试试', 'warn');
      return null;
    }
  }
  /* R230r（R29-#6）：背景图 requestIdleCallback 异步加载——点就画会拿到
   * 渐变底、过会再点拿到真图，同一输入两种产出。绘制前等它加载
   * （1.5s 超时/失败都回落渐变，保证确定性口径「同一时点同一产出」）。 */
  /* R230w：预热的是本视图的底图而非固定 warm。 */
  var _bg = _posterBgFor(view);
  if (_bg && _bg.src && !(_bg.complete && _bg.naturalWidth)) {
    try {
      await Promise.race([
        (_bg.decode ? _bg.decode() : new Promise(function (res, rej) {
          _bg.onload = res; _bg.onerror = rej;
        })),
        new Promise(function (res) { setTimeout(res, 1500); })]);
    } catch (e) { /* 加载失败走渐变兜底 */ }
  }
  /* R230x：吉祥物同款等待（同一超时时窗内一起等）。 */
  if (POSTER_MASCOT.src && !(POSTER_MASCOT.complete && POSTER_MASCOT.naturalWidth)) {
    try {
      await Promise.race([
        (POSTER_MASCOT.decode ? POSTER_MASCOT.decode() : Promise.resolve()),
        new Promise(function (res) { setTimeout(res, 800); })]);
    } catch (e) { /* 没加载上就不画贴纸 */ }
  }
  /* R230x（V-6）：海报字体换 LXGW 文楷链——canvas 不阻塞排版，
   * 绘制前必须显式 load，否则首画仍回落系统 serif。加载失败
   * 静默回落（老设备无此字体也能出图）。
   * R2341（R57-P0-1）：fonts.load 不带 text 只拉 unicode-range
   * 探测串覆盖的子集——巳/壬/酉等字画到未加载子集当场回落系统
   * 字体（无 CJK 的机器出豆腐块）。把海报全部待画文案拼起来
   * 喂给 fonts.load，浏览器按 unicode-range 拉起全部命中子集。 */
  try {
    if (document.fonts && document.fonts.load) {
      /* R3422-P2-8（审）：lxgw.css 是 window load+800ms 才注入的
       * 懒链——窗内点分享时 @font-face 根本没注册，fonts.load
       * 拉无可拉，非 CJK 机出豆腐海报。分享即立刻补注入。 */
      try {
        if (!document.getElementById('lxgwCss')) {
          var _lx = document.createElement('link');
          _lx.id = 'lxgwCss'; _lx.rel = 'stylesheet';
          _lx.href = '/static/fonts/lxgw.css';
          document.head.appendChild(_lx);
        }
      } catch (eLX) {}
      var _ptext = _posterTextCollect(j && j.share ?
        Object.assign({}, j.share, { _src: j }) : j);
      /* R3406-P2：原只拉 '400 32px' 一档且不等栅格——unicode-range
       * 子集 fonts.load resolve 时机早于实际可画，非 CJK 机首画
       * 仍出豆腐。改成：用到的全部字重×字号规格按 _ptext 拉起 +
       * fonts.ready + fonts.check 逐字核验，没过就短睡重试，
       * 外层照旧 2.5s 总帽。 */
      var _fspecs = ['400 34px "LXGW WenKai"', '500 40px "LXGW WenKai"',
        '400 28px "LXGW WenKai"', '600 64px "LXGW WenKai"',
        '400 22px "LXGW WenKai"', '500 30px "LXGW WenKai"'];
      await Promise.race([(async function () {
        for (var _ft = 0; _ft < 6; _ft++) {
          try {
            await Promise.all(_fspecs.map(function (sp) {
              return document.fonts.load(sp, _ptext);
            }));
            await document.fonts.ready;
            if (_fspecs.every(function (sp) {
                  return document.fonts.check(sp, _ptext);
                })) break;
          } catch (e2) { break; }
          await new Promise(function (r2) { setTimeout(r2, 120); });
        }
      })(), new Promise(function (res) { setTimeout(res, 2500); })]);
    }
  } catch (e) { /* 字体没加载上也能画——fallback 链兜底 */ }
  var r = drawPoster(j);
  /* R230r（R29-#12）：画不出来要有回音——原来静默 return 像没点到。 */
  if (!r || !r.canvas) {
    showToast('这张图没画出来，再点一次试试', 'warn');
    return;
  }
  /* 同时触发下载（兼容 desktop「图去哪了」老习惯）+ 弹浮层。
   * R2349m（R76-P2-7）：触屏机上 a[download] 路径是错的——iOS
   * Safari 弹「下载到文件」不是相册、微信 webview 多半静默无效；
   * 浮层里「长按保存」才是对的路。移动端跳过自动下载。 */
  var _isTouch = (typeof navigator !== 'undefined' &&
    (navigator.maxTouchPoints > 0 || 'ontouchstart' in window));
  try {
    if (_dup) {
      showToast('这张图刚保存过了，长按/右键可直接再存', 'info');
    } else if (_isTouch && !/MicroMessenger/i.test(navigator.userAgent || '')) {
      /* 触屏端不触发 a[download]——弹层长按保存即可。
       * R2350b（R99-P2）：微信 webview（尤其 Android）对 data: 图
       * 长按多半不弹「保存图片」——容器内恢复走下载兜底。 */
      _POSTER_LAST[_vkey] = performance.now();
    } else {
      _POSTER_LAST[_vkey] = performance.now();
      r.canvas.toBlob(function (blob) {
        /* R230v（R34-#13）：canvas 编码失败此前静默——浮层照弹但文件
         * 没落盘，用户找不到图。给一句说明。 */
        if (!blob) {
          showToast('图保存没成功，浮层里的预览长按也能存～', 'warn');
          return;
        }
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        /* R230r（R29-#9）：文件名带视图+日期——连存多张不再全是同名。 */
        var _d = new Date();
        var _ymd = _d.getFullYear() +
          ('0' + (_d.getMonth() + 1)).slice(-2) + ('0' + _d.getDate()).slice(-2);
        /* R2350a（R94-P1-3）：黄历海报文件名跟卡面日——翻到 9/22
         * 分享出的文件之前写 0921。 */
        if (_vkey === 'huangli' && j && j.date &&
            /^\d{4}-\d{2}-\d{2}$/.test(j.date)) {
          _ymd = j.date.replace(/-/g, '');
        }
        /* R230y（R36-P3-2）：文件名对齐品牌「小满」
         * R231c：中文文件名「小满-今日命盘-0920」——小红书链路里
         * 辨识度高于 xiaoman-bazi（保存到相册一眼可认）。 */
        var _pt = _POSTER_TITLES[_vkey] || '分享图';
        /* R3437：默契双海报分名——成绩单=默契证书、榜=默契榜。 */
        if (_vkey === 'mochi') _pt = (j && j._mcb) ? '默契榜' : '默契证书';
        a.download = '小满-' + _pt + '-' + _ymd.slice(4) + '.png';
        document.body.appendChild(a);
        /* R2513（审-次）：click() 抛错时 revoke/remove 漏跑——
         * blob URL + DOM 节点双泄漏。包 try/finally。 */
        try { a.click(); } finally {
          setTimeout(function () {
            URL.revokeObjectURL(a.href); a.remove(); }, 800);
        }
      }, 'image/png');
    }
  } catch (e) { /* 低端降级：静默，不打断主流程 */ }
  /* 弹浮层——海报预览 + 移动端长按保存提示 */
  showPosterModal(r.canvas, view, j);
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function circle(ctx, x, y, r) {
  ctx.beginPath();
  ctx.arc(x, y, r, 0, Math.PI * 2);
  ctx.closePath();
}

/* R212：海报大字用——先按宽度断行，超 3 行则缩字号重排，杜绝截断。 */
function wrapText3(ctx, text, maxWidth) {
  /* parseInt(ctx.font) 会把 '600 92px …' 解析成 600（字重前缀）——
   * 必须取 px 前的数字。 */
  var mpx = /(\d+)px/.exec(ctx.font);
  var size = mpx ? parseInt(mpx[1], 10) : 60;
  for (var trial = 0; trial < 4; trial++) {
    ctx.font = ctx.font.replace(/\d+px/, (size - trial * 8) + 'px');
    var lines = [], cur = '';
    String(text || '').split('').forEach(function (ch) {
      /* R2349s（R86-P1-3）：「——」是成对破折号，折行不许劈开——
       * 「说—/—贲卦」的断法视觉上是两根孤杠。 */
      if (ch === '—' && cur.slice(-1) === '—') { cur += ch; return; }
      /* R3316（审-P2）：避头尾——「，。：；、！？）》」等禁做行首，
       * 宁可本行微溢也不让标点悬头（六爻「慢慢看 / ：艮卦」事故）。 */
      if ('，。：；、！？）》」』%‰'.indexOf(ch) !== -1) {
        cur += ch; return;
      }
      if (ctx.measureText(cur + ch).width > maxWidth) { lines.push(cur); cur = ch; }
      else cur += ch;
    });
    if (cur) lines.push(cur);
    /* R2349s（R86-P1-4）：末行只剩 1 个字是排版事故（孤字悬行）——
     * 从上一行尾巴匀一个字过来。
     * R2350d（R100-P2-6）：末行 2 字同样悬空（实测「主角」孤行）——
     * 门槛提到 <3 字，按需逐字回借。 */
    while (lines.length > 1 &&
           Array.from(lines[lines.length - 1]).length < 3 &&
           Array.from(lines[lines.length - 2]).length > 3) {
      var _pa = Array.from(lines[lines.length - 2]);
      lines[lines.length - 1] = _pa.pop() + lines[lines.length - 1];
      lines[lines.length - 2] = _pa.join('');
    }
    if (lines.length <= 3) return lines;
  }
  /* R230r（R29-#4）：超 3 行截断带省略号——静默丢尾巴看不出有下文。 */
  var _t3 = lines.slice(0, 3); _t3[2] += '…';
  return _t3;
}

function wrapText(ctx, text, maxWidth) {
  var lines = [], cur = '';
  String(text || '').split('').forEach(function (ch) {
    /* R2341（R57-P1-4）：避头尾——同 wrapText3 */
    var _noStart = '，。；：、！？）】」』…—·'.indexOf(ch) >= 0;
    if (!_noStart && ctx.measureText(cur + ch).width > maxWidth) {
      lines.push(cur); cur = ch;
    } else cur += ch;
  });
  if (cur) lines.push(cur);
  /* R230r（R29-#4）：同 wrapText3——截断显式收尾。 */
  var _out = lines.slice(0, 3);
  if (lines.length > 3) _out[_out.length - 1] += '…';
  return _out;
}

/* R230r（R29-#1/#2/#8）：海报入图安全工具——
 * _pArr  数组防御（schema 漂移把数组传成字符串/对象时不崩链）
 * _pStr  标量化（对象/数组入图前吃掉，杜绝 [object Object] 画上海报）
 * _gSlice 码点截断（slice() 按 UTF-16 码元切会撕裂 emoji 代理对） */
/* R2341（R57-P1-4）：海报大字按子句截断——定长切会把
 * 「回头看一眼，答案多半在」断在半句。先取 n 码点，若被截则
 * 回退到最近子句边界（，。；！？——）；无边界才硬切。 */
function _clauseCut(v, n) {
  var t = _pStr(v);
  if (Array.from(t).length <= n) return t;
  var cut = _gSliceB(t, n);
  var seps = ['。','！','？','；','，','——','·'];
  var pos = -1;
  seps.forEach(function (sep) {
    var p = cut.lastIndexOf(sep);
    if (p >= 0) pos = Math.max(pos, p + sep.length);
  });
  var out;
  if (pos >= 6) {
    /* R2349s（R86-P1-1）：子句边界截完尾巴不许留孤分隔符——
     * 「…喝咖啡·」的悬点比拦腰截还难看。 */
    out = _gSlice(cut, pos).replace(/[·，；、——]+$/u, '');
  } else {
    out = cut;
  }
  /* R3353（审-P1）：被截就要有截的样子——_gSliceB 遇未闭合引号
   * 回退后只剩半截无截断符（「老话里猫进梦是」悬空），统一补 …。 */
  if (Array.from(out).length < Array.from(t).length &&
      !/[…。！？]$/.test(out)) out += '…';
  return out;
}
function _gSliceB(v, n) {
  var t = _gSlice(v, n);
  var pairs = [['（', '）'], ['「', '」'], ['【', '】'], ['(', ')'],
               ['《', '》']];
  for (var i = 0; i < pairs.length; i++) {
    var o = t.lastIndexOf(pairs[i][0]), c = t.lastIndexOf(pairs[i][1]);
    if (o > c) {           /* 有开无合 */
      /* 开括号前至少留 4 字才不回退（「（节气）」整段当尾巴弃掉
       * 不值得，前面只剩「秋分」又太空——折中：回退到开括号，
       * 但前面 ≥4 字才执行）。 */
      if (o >= 4) { t = _gSlice(t, o); }
      break;
    }
  }
  return t;
}

/* 上一次响应缓存：切换口吻时就地重画，不重发请求。
 * 键 = 结果容器 id，值 = {json, proTitle, render}。render 是"用这份 json
 * 重画整个结果区"的闭包——切换只影响解读段，但结果区是一次性拼出来的
 * 字符串，所以整块重画最简单也最不容易漏。 */