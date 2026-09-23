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
  var pillars = String(paipan.render || '').split(/\s+/).filter(function (p) { return p.length >= 2; });
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
  ctx.fillText('知命 · 仅供娱乐', 540, 1440 - 50);

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
    return { k: _pStr(r && r.k), v: _pStr(r && r.v) };
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
  var bgImg = _posterBgFor(s && s.view);
  if (!(bgImg && bgImg.complete && bgImg.naturalWidth)) {
    bgImg = POSTER_BG.warm;
  }
  if (bgImg && bgImg.complete && bgImg.naturalWidth) {
    ctx.drawImage(bgImg, 0, 0, 1080, 1440);
  } else {
    var bg = ctx.createLinearGradient(0, 0, 0, 1440);
    bg.addColorStop(0, '#FDF8F0'); bg.addColorStop(1, '#F6EDE0');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, 1080, 1440);
  }
  ctx.textAlign = 'center';

  /* R2349m（R75-P1-1/P2-3）：lilac 夜紫底上深色文字整体偏暗、
   * 副题被月亮面冲刷——深底换浅字调色板+深色晕影。 */
  var _bgKey = _POSTER_BG_BY_VIEW[s && s.view] || 'warm';
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
    ctx.fillText(s.badge, W - 56, 128);
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
  ctx.font = '600 ' + bigSize + 'px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  /* R212：三行上限（原两行导致「宜稳不」截断感），行距随字号自适应 */
  var words = wrapText3(ctx, big, 900);
  var bigGap = Math.round(bigSize * 1.35);
  words.forEach(function (ln, i) { ctx.fillText(ln, 540, 300 + i * bigGap); });

  /* 键值行卡片 */
  /* R233t（R51-P0-2）：原来一律 slice(0,4)——daily 的「忌」、
   * checkin-week 的第 5-7 天、taohua 强度等被静默切掉。按 view 给
   * 上限；行高按剩余空间自适应，不越进页脚水印区。 */
  var _lineCap = { daily: 5, 'checkin-week': 7, 'checkin-month': 6,
                   taohua: 5, hehun: 6,
                   huangli: 6, birth: 5, bazi: 5 }[s.view] || 4;
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
     * 垂直居中（下移量封顶 120px，给页脚留呼吸）。 */
    var lh = Math.min(150, Math.max(64, (1260 - cardY) / lines.length));
    var _slack = 1260 - (cardY - 60) - (lines.length * lh + 40);
    if (_slack > 0) cardY += Math.min(120, Math.round(_slack / 2));
    ctx.fillStyle = '#FFFFFF';
    _roundRectPath(ctx, 90, cardY - 60, 900, lines.length * lh + 40, 28); ctx.fill();
    ctx.strokeStyle = '#E8D9BC'; ctx.lineWidth = 2;
    _roundRectPath(ctx, 90, cardY - 60, 900, lines.length * lh + 40, 28); ctx.stroke();
    ctx.textAlign = 'left';
    lines.forEach(function (r, i) {
      var y = cardY + i * lh + 10;
      ctx.fillStyle = '#B7A98A'; ctx.font = '400 34px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
      ctx.fillText(r.k, 150, y);
      ctx.fillStyle = '#3E3428'; ctx.font = '500 40px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
      var v = _pStr(r.v);
      /* R233t（R51-P1-4）：截断 15→22——四柱「戊寅·己未·辛酉·甲…」
       * 残字一眼假，命盘图的可信度就在四柱齐全。
       * R2349m（R75-P1-2）：「…、在生气 等 3 项」这类尾巴被拦腰
       * 截成「等 3…」——遇到「等N项」收尾时保住尾巴完整。 */
      var _vv = v;
      if (Array.from(v).length > 22) {
        /* R2349p（R79-P1-3）：黄历忌行产「等 3 件」——正则只认「项」
         * 把「件」拦腰截掉；量词放宽。 */
        var _mEq = v.match(/等\s*\d+\s*[项件条]?$/);
        var _keep = _mEq ? _mEq[0] : '';
        _vv = _gSlice(v, Math.max(6, 21 - Array.from(_keep).length)) +
          '…' + _keep;
      }
      /* R2351（R109-P1-2）：按字数截断不测宽——22 字 × 40px ≈ 880px
       * 会冲出卡右缘。逐 2px 缩字号到放得下（最低 30px 再截）。 */
      var _vMax = 990 - 150 - 20;
      for (var _fz = 40; _fz > 30 &&
           ctx.measureText(_vv).width > _vMax; _fz -= 2) {
        ctx.font = '500 ' + _fz +
          'px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
      }
      ctx.fillText(_vv, 150, y + 52);
      /* R2349p（R79-P2-5）：幸运色行补色块圆点——legacy 版式有、
       * share 模板只印字。文字照画，色块排在值右侧。 */
      if (r.k === '幸运色') {
        var _cmap = { 红: '#C0392B', 紫: '#8E44AD', 黄: '#D4AC0D',
          棕: '#8D6E63', 黑: '#2C3E50', 蓝: '#2874A6', 青: '#148F77',
          绿: '#27AE60', 白: '#F2F3F4', 金: '#B7950B', 粉: '#FF8FAB',
          橙: '#E67E22', 灰: '#95A5A6' };
        var _scx = 150 + ctx.measureText(_vv).width + 40;
        String(v).split(/\s*·\s*|\s*、\s*/).forEach(function (cn) {
          var hex = _cmap[cn.trim().charAt(0)];
          if (hex && _scx < 940) {
            ctx.fillStyle = hex;
            ctx.beginPath(); ctx.arc(_scx, y + 40, 18, 0, Math.PI * 2); ctx.fill();
            ctx.strokeStyle = 'rgba(62,52,40,.25)'; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(_scx, y + 40, 18, 0, Math.PI * 2); ctx.stroke();
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
    var cw = 250, ch = 420, gap = (1080 - cards.length * cw) / (cards.length + 1);
    /* R2341（R57-P1-3）：无明细行时 cards 上提到 560——
     * 原来固定 880，大字(≤440)到卡片之间留 ~500px 空洞。 */
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
          ctx.save();
          _roundRectPath(ctx, cx + 12, cy + 12, cw - 24, ch - 130, 14); ctx.clip();
          ctx.drawImage(c.img, cx + 12, cy + 12, cw - 24, ch - 130);
          ctx.restore();
        } catch (e) { /* 图未就绪则跳过，文字兜底 */ }
        iy = cy + ch - 118;
      }
      ctx.fillStyle = '#3E3428'; ctx.font = '600 38px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
      ctx.fillText(_gSlice(c.name, 6), cx + cw / 2, iy + 44);
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
   * 上移 32px，底缘留白 ~50px，长图在相册里不顶脚。 */
  ctx.fillText('@小满的解忧铺', 540, 1288);
  /* R230r（R29-#11）：免责声明是合规件——花纹底图上浅棕字几乎不可读，
   * 给文字垫一条半透明米白衬底，任何背景下都可读。 */
  ctx.fillStyle = 'rgba(253,248,240,0.78)';
  _roundRectPath(ctx, 540 - 340, 1298, 680, 42, 21); ctx.fill();
  ctx.fillStyle = '#8A7A56'; ctx.font = '400 26px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  /* R229z续23（R11-#3）：分享图会离站传播，免责必须跟着走 */
  ctx.fillText('· 知命知趣知自己 · 仅供娱乐 ·', 540, 1324);
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
  /* R230x（P2-8）：右下角小满吉祥物贴纸——圆形裁切+奶油色衬底，
   * 与底图区隔成「贴纸」观感；图未加载则跳过不画。 */
  if (POSTER_MASCOT.complete && POSTER_MASCOT.naturalWidth) {
    try {
      /* R2341（R57-P1-3）：tarot 卡片区 (880-1300) 与右下贴纸
       * (1216-1340) 重叠压第三张牌——有卡片时挪右上角。 */
      var _mx = 974, _my = cards.length ? 76 : 1238;
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
    var _ts = _qmScore(top, (_fe1.missing && _fe1.missing.length) ? _fe1.missing : (_fe1.weak || []));
    return '首选「' + _pStr(top.full_name) + '」· 参考分 ' + (_ts.total || 0) + ' / 100';
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
    'birth':  '这张小卡是你的底色'
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
  function base(title, subtitle) {
    /* R218a-11：注入 view 字段供 _paintSharePoster 取金句 hook。 */
    /* R230y（R36-P3-2）：subtitle 空兜当天日期——海报带「今天的签」时效感 */
    /* R233t（R51-P2-15）：裸 ISO 日期「2026-09-20」默认副标
     * 全部视图统一「M月D日 · 周X」。 */
    /* R2349p（R79-P2-2）：默认副标与 _cnDateSub 口径统一（去月前导零）。 */
    var _defSub = _cnDateSub(todayIso());
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
      var _dl = (j && j.lunar) || {};
      var _dsub = _weekdayCn(_dd) +
        ((_dl.month_cn || _dl.day_cn) ?
          ' · 农历' + (_dl.month_cn || '') + (_dl.day_cn || '') : '') +
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
      return _ds;
    }
    case 'tarot': {
      var draws = _pArr(j && j.draws);
      /* R233t（R51-P1-7）：卡图不再按 DOM 顺序抓——复看/重渲后 DOM
       * 序与 draws 可能错位；改用 draws[].img/src 数据键（若有）。 */
      var imgs = document.querySelectorAll('.tarot-card-front img');
      var s = base('塔罗指引',
        (_pStr(j && j.spread) ? '「' + _pStr(j.spread) + '」牌阵 · ' : '') +
        (_pStr(j && j.question) ? '你问的：「' + _gSlice(_pStr(j.question), 16) + '」' : ''));
      /* R219b（P1-4）：海报兜底句去掉「牌面是象征，不是结论」免责套话 */
      /* R2349s（R86-P2-7）：「节制·正：调和，少硬刚」的「·正：」
       * 是内部编码格式漏到画上——转成顺读「节制（正位）：…」。 */
      var _tb = _pStr(l0).replace(/·\s*([正逆])\s*：/, '（$1位）：');
      s.big = _tb || '今天这几张牌，值得你看一眼';
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
      sxz.lines = _xzl.slice(0, 3);
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
          if (_lm) sly.lines.push({ k: '动爻', v: _lm });
          else sly.lines.push({ k: '动爻', v: '静卦 · 格局稳住' });
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
      return { title: '五行起名',
        subtitle: '按五行补缺 · ' + _cnDateSub(todayIso()),
        big: _gSlice((_pArr(j && j.full_names)[0] || {}).full_name || l0, 12),
        lines: [{ k: '五行', v: _qfeLine }].concat(
          _pArr(j && j.full_names).slice(0, 3).map(function (n, i) {
            /* R2349s（R86-P2-6）：「推荐 N」编号腔——首选/备选。 */
            return { k: (i === 0 ? '首选' : '备选'), v: _pStr(n && n.full_name) }; })),
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
      var _birSub = _cnDateSub(todayIso());
      var _bir = base('我的本命盘', _birSub);
      var _bp = String(((j && j.paipan) || {}).render || '').split(/\s+/).filter(function (p) { return p.length >= 2; }).slice(0, 4);
      var _bec = (w && w.energy_card) || {};
      _bir.big = _bsign ? ('你是 ' + _bsign + '座') : (l0 || '本命已就位');
      _bir.lines = [];
      if (_bp.length) _bir.lines.push({ k: '四柱', v: _bp.join(' · ') });
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
        _weekdayCn('') + ' · ' + _cnDateSub(todayIso()).split(' · ')[0]);
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
      var pillars = String(((j && j.paipan) || {}).render || '').split(/\s+/).filter(function (p) { return p.length >= 2; }).slice(0, 4);
      var ec = (w && w.energy_card) || {};
      sb.big = l0 || '本命已就位';
      sb.lines = [];
      if (pillars.length) sb.lines.push({ k: '四柱', v: pillars.join(' · ') });
      if (ec.element) sb.lines.push({ k: '本命', v: _pStr(ec.element) + (ec.element_warm ? '（' + _pStr(ec.element_warm) + '）' : '') });
      var _lc = _pArr(ec.lucky_colors), _ln = _pArr(ec.lucky_numbers);
      if (_lc.length) sb.lines.push({ k: '幸运色', v: _lc.slice(0, 3).map(_pStr).join(' · ') });
      if (_ln.length) sb.lines.push({ k: '幸运数字', v: _ln.map(_pStr).join(' · ') });
      if (!sb.lines.length) sb.lines = [{ k: '结论', v: _gSlice(l0, 15) || '知己知命' }];
      return sb;
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
      if (_pStr(j && j.peach_zhi)) st.lines.push({ k: '桃花支', v: _zhiCn(j.peach_zhi) });
      var _hp = _pArr(j && j.hit_pillars);
      if (_hp.length) st.lines.push({ k: '命中柱', v: _hp.map(function (p) { return ({ year: '年柱', month: '月柱', day: '日柱', hour: '时柱' })[p] || _pStr(p); }).join(' · ') });
      if (_pStr(j && j.hongluan)) st.lines.push({ k: '红鸾星', v: _zhiCn(j.hongluan) });
      if (_pStr(j && j.tianxi)) st.lines.push({ k: '天喜星', v: _zhiCn(j.tianxi) });
      /* R233t（R51-P1-9）：裸枚举 strong 上图社死——映射人话。 */
      var _stg = _pStr(j && j.strength);
      if (_stg) st.lines.push({ k: '桃花信号', v:
        ({ strong: '最近正旺', mid: '在慢慢升温', weak: '还在酝酿' })[_stg] || _stg });
      if (!st.lines.length) st.lines = [{ k: '结论', v: _gSlice(l0, 15) || '桃花待时而动' }];
      return st;
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
      if (j && j.combine === true) sh.lines.push({ k: '天作之合', v: '日主相合' });
      if (j && typeof j.peach_same === 'boolean') sh.lines.push({ k: '桃花支', v: j.peach_same ? '同支共振' : '各有桃花' });
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
    case 'xzm': {
      var _xm = base('星座速配', _cnDateSub(todayIso()));
      _xm.big = _pStr(j && j.a) + '座 × ' + _pStr(j && j.b) + '座';
      _xm.lines = [
        { k: '合拍指数', v: _pStr(j && j.score) + '/99' },
        { k: '判词', v: _pStr(j && j.label) },
        { k: '小满说', v: _clauseCut(_pStr(j && j.line), 20) }];
      return _xm;
    }
    default:
      return null;
  }
}

var _POSTER_LAST = {};   /* view → ts：同视图 4s 内连点只弹浮层不再下载 */
async function downloadPoster(j, view) {
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
      (s.lines || []).forEach(function (r) {
        t += _pStr(r && r.k) + _pStr(r && r.v); });
      (s.cards || []).forEach(function (c) {
        t += _pStr(c && c.name) + _pStr(c && c.sub); });
      var _h = _posterHookForView(s.view, s._src || s);
      t += _pStr(_h);
      /* 旧版式（无 j.share）走 bazi 专属模板：四柱 pills + one_liner +
       * 能量卡行——巳/壬/酉这些支干字最容易踩豆腐块。 */
      var _w = s.warm || {}, _pp = s.paipan || {}, _e = _w.energy_card || {};
      t += _pStr(_pp.render) + _pStr(_w.one_liner);
      t += _pStr(_e.element) + _pStr(_e.element_warm);
      ['lucky_colors', 'lucky_numbers', 'lucky_hours', 'basis'].forEach(function (f) {
        (_pArr(_e[f])).forEach(function (x) { t += _pStr(x); });
      });
      /* 键值行标签常量 */
      t += '今日命盘幸运色数字时段本命';
    }
  } catch (e) {}
  /* 页脚常量 + 旧版式 drawPoster 的固定串 + 各视图兜底文案也要覆盖 */
  /* R2350b（R99-P2）：预热集与现役 CTA 对齐（「铺/的」等字原不在
   * 集里，命中未加载子集时回落系统字体）。 */
  return t + '知命，是为了更好地活@小满的解忧铺·知命知趣知自己' +
    '仅供娱乐测你的同款→搜「」✨' ;
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
    if (s) j = Object.assign({}, j, { share: s });
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
      var _ptext = _posterTextCollect(j && j.share ?
        Object.assign({}, j.share, { _src: j }) : j);
      await Promise.race([
        document.fonts.load('400 32px "LXGW WenKai"', _ptext),
        new Promise(function (res) { setTimeout(res, 2500); })]);
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
        a.download = '小满-' + (_POSTER_TITLES[_vkey] || '分享图') +
          '-' + _ymd.slice(4) + '.png';
        document.body.appendChild(a);
        a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 800);
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
  if (pos >= 6) {
    /* R2349s（R86-P1-1）：子句边界截完尾巴不许留孤分隔符——
     * 「…喝咖啡·」的悬点比拦腰截还难看。 */
    return _gSlice(cut, pos).replace(/[·，；、——]+$/u, '');
  }
  return cut;
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