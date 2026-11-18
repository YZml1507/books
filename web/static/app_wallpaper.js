/* R3317 每日开运壁纸 chunk——懒加载（与 app_poster.js 同款 stub 接管：
 * app.js 的 downloadWallpaper stub 先接住点击，本文件落地后同名
 * 接管。底图是离线烘的 10 张竖幅（scripts/gen_wallpapers.py），
 * 按日轮换；canvas 叠字合成成品（日期锚/判词/开运色签/日签）。
 * 模态与落盘复用 app.js 的 showPosterModal + 海报的 a.download 流。 */
'use strict';

/* R3328+：_LC_HEX 收敛——读 app.js 顶层全局唯一真源；懒加载顺序
 * 保证到时已定义，异常缺失走调用点 #d9c9a8 兜底。 */
var _WAP_LC_HEX = window.LC_HEX || {};
/* 判词星级色：吉=暖金、小吉=蜜桃、平=雾蓝、凶=暖灰（治愈向不用冷色） */
/* R3318（审-P1-3）：personal.mine.verdict 九个判值原全部落到米白
 * fallback——浅底图上判词低对比。按「合=暖金 / 轻绊=雾蓝 / 凶挫=灰褐」
 * 三档补全，与日卡 _verdictTone 同语义。 */
var _WAP_LV_TINT = { '吉': '#F5C06A', '小吉': '#F5A88C', '大吉': '#F5C06A',
                     '平': '#9DB8D8', '凶': '#C9B8A8', '注意': '#C9B8A8',
                     '合缘': '#F5C06A', '岁合': '#F5C06A', '半合': '#F5C06A',
                     '轻冲': '#9DB8D8', '小绊': '#9DB8D8', '岁吟': '#9DB8D8',
                     '小凶': '#E8A08A', '小挫': '#E8A08A', '伏吟': '#C9B8A8' };

function _wapSeed(dstr) {
  /* 同日全站同图（确定性）：日期串散列取模。 */
  var h = 0, s = String(dstr || '');
  for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h % _WAP_COUNT;
}

function _wapImg(url) {
  return new Promise(function (res, rej) {
    var im = new Image();
    im.onload = function () { res(im); };
    im.onerror = function () { rej(new Error('壁纸底图没加载上')); };
    im.src = url;
  });
}

function _wapWrap(ctx, text, maxW, maxLines) {
  var lines = [], cur = '';
  String(text || '').split('').forEach(function (ch) {
    /* 与 wrapText3 同款避头尾 */
    if ('，。：；、！？）》」'.indexOf(ch) !== -1) { cur += ch; return; }
    if (ctx.measureText(cur + ch).width > maxW) { lines.push(cur); cur = ch; }
    else cur += ch;
  });
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    lines = lines.slice(0, maxLines);
    var last = lines[maxLines - 1];
    lines[maxLines - 1] = last.slice(0, -1) + '…';
  }
  return lines;
}

/* R3479 灵魂色谱壁纸：全幅星云（与 soulart 海报底同一画家算法、
 * 同一 seed/ bands 口径）+ 色谱名 + 气质行——无日期无烘焙底图，
 * 720×1280 锁屏比例。 */
function _wapNebula(j) {
  var cv = document.createElement('canvas');
  cv.width = 720; cv.height = 1280;
  var ctx = cv.getContext('2d');
  /* R3484-P2（审）：空 bands 硬编木带会让判词印错行——回落
   * 带不带 wx 标记，判词行借此静默缺席。 */
  var _bands = (j && j.art && Array.isArray(j.art.bands)
    && j.art.bands.length) ? j.art.bands
    : [{ c: '#B8A5E8', frac: 0.6, wx: '' }];
  var _seed = (+((j && j.art && j.art.seed) || 0)) >>> 0;
  var g = ctx.createLinearGradient(0, 0, 0, 1280);
  g.addColorStop(0, '#1A1430'); g.addColorStop(1, '#0E0B1F');
  ctx.fillStyle = g; ctx.fillRect(0, 0, 720, 1280);
  var _rnd = function () {
    _seed = (_seed * 1664525 + 1013904223) >>> 0;
    return _seed / 4294967296;
  };
  _bands.forEach(function (b) {
    var _cx = 120 + _rnd() * 480, _cy = 200 + _rnd() * 880;
    var _r = 170 + b.frac * 380;
    var _g = ctx.createRadialGradient(_cx, _cy, 0, _cx, _cy, _r);
    _g.addColorStop(0, b.c + 'CC');
    _g.addColorStop(0.55, b.c + '55');
    _g.addColorStop(1, b.c + '00');
    ctx.fillStyle = _g; ctx.fillRect(0, 0, 720, 1280);
  });
  ctx.fillStyle = 'rgba(255,246,232,0.7)';
  for (var _sp = 0; _sp < 70; _sp++) {
    var _sx = _rnd() * 720, _sy = _rnd() * 1280,
        _sr = _rnd() * 1.6 + 0.4;
    ctx.beginPath(); ctx.arc(_sx, _sy, _sr, 0, 6.3); ctx.fill();
  }
  /* 文字区：店招 + 色谱名 + 最浓气 + 色带图例。 */
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(255,246,232,0.92)';
  ctx.font = '600 28px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillText('小 满 的 解 忧 铺', 360, 96);
  ctx.fillStyle = '#FFF6E8';
  ctx.font = '700 54px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillText(_pStr(j && j._saName) || '我的五行色谱', 360, 1160);
  var _top = _bands.slice().sort(function (a, b2) {
    return b2.frac - a.frac; })[0];
  ctx.font = '400 26px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = 'rgba(255,246,232,0.85)';
  /* 「土气」在目标语境=老土——五行行名直拼会读成自贬，
   * 用「土行」避开歧义。空 bands（回落带 wx=''）不印判词，
   * 改中性「一人一幅」（与卡内无 top 静默缺席同口径）。 */
  ctx.fillText(_top && _top.wx
               ? '你盘里最浓的是' + _top.wx + '行'
               : '一人一幅，按五行权重画',
               360, 1212);
  /* 色带图例：小圆点排排。 */
  var _lw = _bands.length * 34, _lx = 360 - _lw / 2 + 17;
  _bands.forEach(function (b, i) {
    ctx.beginPath(); ctx.arc(_lx + i * 34, 1060, 9, 0, 6.3);
    ctx.fillStyle = b.c; ctx.fill();
  });
  return cv;
}
/* R3491 灵魂纹样原图：720×720 方形（可当头像）+竖放中央，
 * 夜底 + 大徽章 + 店招 + 纹名 + 纹意 + 落款。纹样本体交给
 * app.js 全局 _emblemDraw（本文件惰载时它一定在场）。 */
function _wapEmblem(j) {
  var cv = document.createElement('canvas');
  cv.width = 720; cv.height = 1280;
  var ctx = cv.getContext('2d');
  var _em = (j && j.emblem) || {};
  var _wx = _pStr(_em.wx) || '木';
  var _seed = (+_em.seed) >>> 0;
  var g = ctx.createLinearGradient(0, 0, 0, 1280);
  g.addColorStop(0, '#1E1834'); g.addColorStop(1, '#0E0B1F');
  ctx.fillStyle = g; ctx.fillRect(0, 0, 720, 1280);
  /* 星点散斑（与星云同款 LCG 种子推进——同纹同点）。 */
  var _rnds = function () {
    _seed = (_seed * 1664525 + 1013904223) >>> 0;
    return _seed / 4294967296;
  };
  ctx.fillStyle = 'rgba(255,246,232,0.55)';
  for (var _sp = 0; _sp < 80; _sp++) {
    var _sx = _rnds() * 720, _sy = _rnds() * 1280,
        _sr = _rnds() * 1.6 + 0.4;
    ctx.beginPath(); ctx.arc(_sx, _sy, _sr, 0, 6.3); ctx.fill();
  }
  /* 大徽章居中。种子单独推流：散斑消耗掉一段，徽章吃后段。 */
  if (typeof _emblemDraw === 'function') {
    _emblemDraw(ctx, 360, 560, 250, _wx,
                (+((j && j.emblem && j.emblem.seed) || 0)) >>> 0);
  }
  ctx.textAlign = 'center';
  ctx.fillStyle = 'rgba(255,246,232,0.92)';
  ctx.font = '600 28px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillText('小 满 的 解 忧 铺', 360, 96);
  ctx.fillStyle = '#FFF6E8';
  ctx.font = '700 54px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillText(_pStr(_em.name) || '灵魂纹样', 360, 940);
  ctx.font = '400 28px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = 'rgba(255,246,232,0.85)';
  var _vb = _pStr(_em.vibe);
  ctx.fillText(_vb ? _vb.slice(0, 20) : '一人一纹，按五行生',
               360, 996);
  ctx.font = '400 24px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = 'rgba(255,246,232,0.72)';
  ctx.fillText('@小满的解忧铺 · 仅供娱乐', 360, 1242);
  return cv;
}
function _wapComposite(j, bg, variant) {
  /* R3325-B：variant.square → 1:1 开运头像（720×720，底图中裁，
   * 版心下移适配圆裁展示）。 */
  var _sq = !!(variant && variant.square);
  var cv = document.createElement('canvas');
  cv.width = 720; cv.height = _sq ? 720 : 1280;
  var ctx = cv.getContext('2d');
  /* 底图 cover（方形从 1280 高中裁 720） */
  if (_sq) ctx.drawImage(bg, 0, 280, 720, 720, 0, 0, 720, 720);
  else ctx.drawImage(bg, 0, 0, 720, 1280);
  /* 方形版重定描点 */
  /* R3327-P0-3：圆裁实测裁掉两端文字——方形版按 ~560px 安全宽
   * 重排版：日期/开运色行缩字号、品牌短落款上移。 */
  var A = _sq ? { shop: 64, date: 116, dateFs: 26, verdict: 330,
                  lucky: 430, luckyFs: 26, sign: 560, signGap: 46,
                  brand: 640, signW: 520,
                  scrimT: 300, scrimB0: 440, scrimB1: 720 }
              : { shop: 96, date: 158, dateFs: 34, verdict: 300,
                  lucky: 380, luckyFs: 32, sign: 1120, signGap: 52,
                  brand: 1242, signW: 560,
                  /* R3337（审-中）：竖版底 scrim 起点 1000、签句区
                   * 1120-1172 只吃 ~0.3 暗——熊脚底图签句实测压字。
                   * 起点抬到 940、终值 0.68→0.74。 */
                  scrimT: 470, scrimB0: 940, scrimB1: 1280 };
  /* 上下暗角——叠字可读的 scrim（烘焙图上半本来就留净空，这里
   * 只是再压一层保证任何图的日期锚都可读）。 */
  /* R3318（审-P1-3）：渐隐原止于 y=430，开运色签行（y≈368-380）
   * 正落在尾巴上——浅底图洗到近不可读。强掩到 400 再缓出到 470。 */
  var g1 = ctx.createLinearGradient(0, 0, 0, A.scrimT);
  g1.addColorStop(0, 'rgba(38,30,22,0.62)');
  g1.addColorStop(0.78, 'rgba(38,30,22,0.42)');
  g1.addColorStop(1, 'rgba(38,30,22,0)');
  ctx.fillStyle = g1; ctx.fillRect(0, 0, 720, A.scrimT);
  var g2 = ctx.createLinearGradient(0, A.scrimB0, 0, A.scrimB1);
  g2.addColorStop(0, 'rgba(38,30,22,0)');
  g2.addColorStop(1, _sq ? 'rgba(38,30,22,0.68)'
                         : 'rgba(38,30,22,0.74)');
  ctx.fillStyle = g2;
  ctx.fillRect(0, A.scrimB0, 720, A.scrimB1 - A.scrimB0);

  var _mine = (j && j.personal && j.personal.mine) || {};
  var _lv = _mine.verdict && _mine.verdict !== '无冲无合'
    ? _mine.verdict : ((j && j.level) || '今日签');
  var _tint = _WAP_LV_TINT[_lv] || _WAP_LV_TINT[(_lv || '').slice(0, 1)] ||
              '#F5E3C0';

  ctx.textAlign = 'center';
  /* 顶区：「小满的解忧铺」店招 + 日期锚（月日周+农历） */
  ctx.fillStyle = 'rgba(255,246,232,0.92)';
  ctx.font = '600 30px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillText('小 满 的 解 忧 铺', 360, A.shop);
  var _wd = '', _ln2 = '';
  try {
    var _dd = new Date(String(j.date || '') + 'T00:00:00');
    var _wds = '日一二三四五六';
    if (!isNaN(_dd)) {
      _wd = '周' + _wds[_dd.getDay()];
      _wd = (_dd.getMonth() + 1) + '月' + _dd.getDate() + '日 · ' + _wd;
    }
  } catch (eD) {}
  _ln2 = (j && j.lunar) || '';
  ctx.font = '400 ' + A.dateFs +
    'px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = 'rgba(255,246,232,0.95)';
  ctx.fillText((_wd || String(j.date || '')) + (_ln2 ? ' · ' + _ln2 : ''),
               360, A.date);

  /* 判词大字 */
  /* R3326（审-P1）：方图裁切后判词行压在熊脸深色块上——
   * 方形版先铺一条半透明暗衬带保可读。
   * R3353（审-P1/P2）：两版判词实测均压奶油熊毛弱读——方图
   * 衬带加深（0.38→0.5、加宽），竖图同补暗衬。 */
  ctx.fillStyle = _sq ? 'rgba(38,30,22,0.5)'
                      : 'rgba(38,30,22,0.42)';
  ctx.beginPath();
  ctx.ellipse(360, _sq ? A.verdict - 34 : A.verdict - 40,
              _sq ? 190 : 235, _sq ? 88 : 100, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.font = '600 ' + (_sq ? 96 : 108) +
    'px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = _tint;
  ctx.shadowColor = 'rgba(0,0,0,0.35)';
  ctx.shadowBlur = 18; ctx.shadowOffsetY = 4;
  ctx.fillText(String(_lv).slice(0, 6), 360, A.verdict);
  ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;

  /* 开运色签：色圆点 + 色名 + 意象词 + 幸运数 */
  /* R3337（审-中）：方图 lucky 行 y=430 落在顶 scrim 尾外、底 scrim
   * 头前——正中熊脸区压字。方图在行后垫椭圆暗衬（同判词做法）。 */
  var _lc = (j.lucky && j.lucky.color) || '';
  var _lcw = (j.lucky && j.lucky.color_word) || '';
  var _lnum = (j.lucky && j.lucky.num) || '';
  if (_lc) {
    var _hex = _WAP_LC_HEX[_lc] || '#d9c9a8';
    ctx.font = '400 ' + A.luckyFs +
      'px "LXGW WenKai","PingFang SC",sans-serif';
    var _lcTxt = '今日开运色 · ' + _lc +
      (_lcw ? '（' + _lcw + '）' : '') + (_lnum ? ' · ' + _lnum : '');
    var _tw = ctx.measureText(_lcTxt).width;
    if (_sq) {
      /* R3353（审-P1）：深色椭圆压熊脸像污渍——换奶油色胶囊
       * +深棕字（卡面同款配色），色点保持彩色。 */
      ctx.fillStyle = 'rgba(255,246,232,0.88)';
      ctx.beginPath();
      ctx.ellipse(360, A.lucky - 26, _tw / 2 + 56, 36,
                  0, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = 'rgba(62,52,40,0.18)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.ellipse(360, A.lucky - 26, _tw / 2 + 56, 36,
                  0, 0, Math.PI * 2);
      ctx.stroke();
    }
    var _cx = 360 - _tw / 2 - 26;
    ctx.beginPath();
    ctx.arc(_cx, A.lucky - Math.round(A.luckyFs * 0.7), 16, 0, Math.PI * 2);
    ctx.fillStyle = _hex;
    ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.lineWidth = 2; ctx.stroke();
    ctx.textAlign = 'left';
    ctx.fillStyle = _sq ? '#5A4633' : 'rgba(255,246,232,0.95)';
    ctx.fillText(_lcTxt, _cx + 26, A.lucky);
    ctx.textAlign = 'center';
  }

  /* 底区：日签句（summary 首句或个人判词行）+ 品牌行 */
  var _sign = '';
  try {
    _sign = ((j.summary || '').split('；')[0] ||
             (j.warm && j.warm.one_liner) || '').slice(0, 44);
  } catch (eS) {}
  ctx.font = '400 36px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = 'rgba(255,246,232,0.96)';
  var _sl = _wapWrap(ctx, _sign, A.signW, 2);
  _sl.forEach(function (ln, i) {
    ctx.fillText(ln, 360, A.sign + i * A.signGap); });
  ctx.font = '400 24px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = 'rgba(255,246,232,0.72)';
  /* R3319（规划C）：连签里程碑限定壁纸——落款带纪念标，
   * 仪式感奖励物可直发晒图。 */
  /* R3353（审-P1）：方图头像缺合规标——可直发物料须与全站
   * 同口径（变体 tag 是里程碑纪念标，豁免）。 */
  ctx.fillText((variant && variant.tag) ||
               (_sq ? '@小满的解忧铺 · 仅供娱乐'
                    : '@小满的解忧铺 · 知命·仅供娱乐'), 360, A.brand);
  return cv;
}

/* R3486：守护图腾锁屏画家——烘焙灵兽底图（gd-<wx>.jpg）+ 店招 +
 * 灵兽名 + 守护语。与 _wapNebula 同款独立合成器路径：
 * 底图是 Agnes 离线烘焙资产，无日期锚（图腾不按日换）。 */
function _wapBeast(j) {
  return new Promise(function (res, rej) {
    var _b = (j && j.beast) || {};
    var _img = new Image();
    _img.onload = function () {
      var cv = document.createElement('canvas');
      cv.width = 720; cv.height = 1280;
      var ctx = cv.getContext('2d');
      /* cover：1536×1024→720×1280 中裁 */
      var _iw = _img.width, _ih = _img.height;
      var _sc = Math.max(720 / _iw, 1280 / _ih);
      var _dw = _iw * _sc, _dh = _ih * _sc;
      ctx.drawImage(_img, (720 - _dw) / 2, (1280 - _dh) / 2, _dw, _dh);
      /* 上下暗角保文字可读（与 _wapComposite 同口径 scrim）。 */
      var g1 = ctx.createLinearGradient(0, 0, 0, 400);
      g1.addColorStop(0, 'rgba(38,30,22,0.60)');
      g1.addColorStop(1, 'rgba(38,30,22,0)');
      ctx.fillStyle = g1; ctx.fillRect(0, 0, 720, 400);
      var g2 = ctx.createLinearGradient(0, 940, 0, 1280);
      g2.addColorStop(0, 'rgba(38,30,22,0)');
      g2.addColorStop(1, 'rgba(38,30,22,0.74)');
      ctx.fillStyle = g2; ctx.fillRect(0, 940, 720, 340);
      ctx.textAlign = 'center';
      ctx.fillStyle = 'rgba(255,246,232,0.92)';
      ctx.font = '600 28px "LXGW WenKai","PingFang SC",sans-serif';
      ctx.fillText('小 满 的 解 忧 铺', 360, 96);
      /* 灵兽名大字（带暗衬椭圆） */
      ctx.fillStyle = 'rgba(38,30,22,0.42)';
      ctx.beginPath();
      ctx.ellipse(360, 1060, 235, 100, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.font = '700 96px "LXGW WenKai","PingFang SC",sans-serif';
      ctx.fillStyle = '#FFF6E8';
      ctx.shadowColor = 'rgba(0,0,0,0.35)';
      ctx.shadowBlur = 18; ctx.shadowOffsetY = 4;
      ctx.fillText(_pStr(_b.name) || '守护图腾', 360, 1088);
      ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
      /* 守护语小字 */
      ctx.font = '400 30px "LXGW WenKai","PingFang SC",sans-serif';
      ctx.fillStyle = 'rgba(255,246,232,0.95)';
      var _gl = _wapWrap(ctx, _pStr(_b.guard) || '', 560, 2);
      _gl.forEach(function (ln, i) {
        ctx.fillText(ln, 360, 1150 + i * 44); });
      ctx.font = '400 24px "LXGW WenKai","PingFang SC",sans-serif';
      ctx.fillStyle = 'rgba(255,246,232,0.72)';
      ctx.fillText('@小满的解忧铺 · 知命·仅供娱乐', 360, 1242);
      res(cv);
    };
    _img.onerror = function () { rej(new Error('beast img')); };
    _img.src = _pStr(j && j.beast && j.beast.img) ||
      '/static/wallpapers/gd-earth.jpg';
  });
}

/* R80：灵魂角色锁屏画家——从「角色图铺暖渐变」改成「烘焙场景底图 +
 * 店招/名号/写照」三段式，与 _wapBeast（守护图腾）同一条管线。
 * 用户实测本轮：「那个洛神怎么是个很丑的东西……他的『做我的壁纸』
 * 也是很难看」。原来这里是拿透明底角色图（icons/ic-*.png）自己铺暖
 * 渐变 + 一团径向柔光当底——没有环境没有氛围，角色像贴在色块上，所以
 * 「很难看」。R80 由 scripts/gen_soul_assets.py 烘焙了 5 张整幅场景
 * 壁纸（wallpapers/ic-wap-<wx>.jpg，720×1280：角色在上半、下半压暗
 * 留字位），这里改为 cover 铺底 + 上下暗角 + 浅色字。
 * 底图取不到（旧壳/网络断）时回落原渐变 + 角色抠图兜底，不空手。 */
function _wapSoulIcon(j) {
  return new Promise(function (res, rej) {
    var _bg = new Image();
    _bg.onload = function () { _souliconPaint(res, _bg, null, j); };
    _bg.onerror = function () {
      var _ch = new Image();
      _ch.onload = function () { _souliconPaint(res, null, _ch, j); };
      _ch.onerror = function () { rej(new Error('soulicon img')); };
      _ch.src = _pStr(j && j._icImgUrl) || '/static/icons/ic-wood.png';
    };
    _bg.src = _pStr(j && j._icWap) || '/static/wallpapers/ic-wap-wood.jpg';
  });
}
/* R81（用户直报 2026-11-19 第 2 条「灵魂角色『做我的锁屏』时有第二张截
 * 屏那样的报错」）：R80 把画家从 _wapSoulIcon 里抽成独立函数时，签名写成
 * (res, bg, ch) 却没把 j 传进去——而函数体下半段的角色名/本命依据/写照
 * 三处 ctx.fillText 都在读 j._icName / j._icWhy / j._icVibe。合成器每次走
 * 到这里就抛 ReferenceError: j is not defined，冒到 window error 处理器弹
 * 「⚠️ 页面出了点小状况，刷新一下试～」——所以不是底图 404，是签名漏参。
 * 加回第 4 个形参 j，两处调用点一起补。 */
function _souliconPaint(res, bg, ch, j) {
  var cv = document.createElement('canvas');
  cv.width = 720; cv.height = 1280;
  var ctx = cv.getContext('2d');
  if (bg) {
    /* cover：底图本就 720×1280，等比铺满零裁切 */
    var _iw = bg.width, _ih = bg.height;
    var _sc = Math.max(720 / _iw, 1280 / _ih);
    ctx.drawImage(bg, (720 - _iw * _sc) / 2, (1280 - _ih * _sc) / 2,
                  _iw * _sc, _ih * _sc);
  } else {
    /* 兜底：原 R78 的暖渐变（与 --bg/#FFF8E7 同族） */
    var g = ctx.createLinearGradient(0, 0, 0, 1280);
    g.addColorStop(0, '#F7E9D2');
    g.addColorStop(0.42, '#F1DCB8');
    g.addColorStop(1, '#E4C9A0');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 720, 1280);
    var rg = ctx.createRadialGradient(360, 560, 40, 360, 560, 620);
    rg.addColorStop(0, 'rgba(255,252,244,0.55)');
    rg.addColorStop(1, 'rgba(255,252,244,0)');
    ctx.fillStyle = rg;
    ctx.fillRect(0, 0, 720, 1280);
    /* 角色：contain 适配，居中偏上（下半留名字与台词） */
    var _cw = ch.width, _chh = ch.height;
    var _cs = Math.min(620 / _cw, 820 / _chh);
    var _dw = _cw * _cs, _dh = _chh * _cs;
    ctx.drawImage(ch, (720 - _dw) / 2, 170, _dw, _dh);
    var sg = ctx.createRadialGradient(360, 170 + _dh, 10,
                                      360, 170 + _dh, _dw * 0.55);
    sg.addColorStop(0, 'rgba(74,63,53,0.20)');
    sg.addColorStop(1, 'rgba(74,63,53,0)');
    ctx.fillStyle = sg;
    ctx.fillRect(0, 170 + _dh - 90, 720, 180);
  }
  /* 上下暗角保文字可读（与 _wapBeast 同口径 scrim） */
  var g1 = ctx.createLinearGradient(0, 0, 0, 400);
  g1.addColorStop(0, 'rgba(38,30,22,0.58)');
  g1.addColorStop(1, 'rgba(38,30,22,0)');
  ctx.fillStyle = g1; ctx.fillRect(0, 0, 720, 400);
  var g2 = ctx.createLinearGradient(0, 880, 0, 1280);
  g2.addColorStop(0, 'rgba(38,30,22,0)');
  g2.addColorStop(1, 'rgba(38,30,22,0.80)');
  ctx.fillStyle = g2; ctx.fillRect(0, 880, 720, 400);
  ctx.textAlign = 'center';
  /* 店招 */
  ctx.fillStyle = 'rgba(255,246,232,0.92)';
  ctx.font = '600 28px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillText('小 满 的 解 忧 铺', 360, 96);
  /* 角色名大字（带暗衬椭圆） */
  ctx.fillStyle = 'rgba(38,30,22,0.42)';
  ctx.beginPath();
  ctx.ellipse(360, 1036, 225, 84, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.font = '700 84px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = '#FFF6E8';
  ctx.shadowColor = 'rgba(0,0,0,0.35)';
  ctx.shadowBlur = 18; ctx.shadowOffsetY = 4;
  ctx.fillText(_pStr(j && j._icName) || '灵魂角色', 360, 1068);
  ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
  /* 凭什么是他 + 一句角色写照——逐行往下排，行距按字号走，
   * 末行与落款之间留 18px 气（1280 底，别贴边）。 */
  ctx.font = '400 28px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = 'rgba(255,246,232,0.96)';
  var _gl = _wapWrap(ctx, _pStr(j && j._icWhy) || '', 620, 2);
  _gl.forEach(function (ln, i) {
    ctx.fillText(ln, 360, 1124 + i * 32); });
  ctx.font = '400 25px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = 'rgba(255,246,232,0.88)';
  var _vib = _wapWrap(ctx, _pStr(j && j._icVibe) || '', 620, 2);
  _vib.forEach(function (ln, i) {
    ctx.fillText(ln, 360, 1192 + i * 28); });
  ctx.font = '400 22px "LXGW WenKai","PingFang SC",sans-serif';
  ctx.fillStyle = 'rgba(255,246,232,0.72)';
  ctx.fillText('@小满的解忧铺 · 知命·仅供娱乐', 360, 1260);
  res(cv);
}

/* R76：开运图落盘——从 showPosterModal 的比例切换里抽出来共用。
 * square=头像 1:1，否则壁纸 9:16。触屏端弹层长按即可存，不必静默
 * 落盘（R3326：iOS/微信 a[download] 多半落空）。 */
function _wapSave(cv, j, square, fname) {
  var _ymd = String((j && j.date) || '').replace(/-/g, '');
  try {
    cv.toBlob(function (blob) {
      if (!blob) return;
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = square
        ? '小满-开运头像-' + _ymd + '.png'
        : '小满-开运壁纸-' + _ymd + (fname ? '-' + fname : '') + '.png';
      document.body.appendChild(a);
      try { a.click(); } finally {
        setTimeout(function () {
          URL.revokeObjectURL(a.href); a.remove(); }, 800);
      }
    }, 'image/png');
  } catch (eWS) {}
}

function downloadWallpaper(j, variant) {
  /* R3491：灵魂纹样原图变体——方形大图独立合成器（可当头像）。 */
  if (variant && variant.emblem) {
    try {
      var _cvE = _wapEmblem(j);
      var _tE = (typeof navigator !== 'undefined' &&
        (navigator.maxTouchPoints > 0 || 'ontouchstart' in window));
      if (_tE && !/MicroMessenger/i.test(navigator.userAgent || '')) {
        showPosterModal(_cvE, 'emblem-wap', j);
        return Promise.resolve();
      }
      _cvE.toBlob(function (blob) {
        if (!blob) return;
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = '小满-灵魂纹样.png';
        document.body.appendChild(a);
        try { a.click(); } finally {
          setTimeout(function () {
            URL.revokeObjectURL(a.href); a.remove(); }, 800);
        }
      }, 'image/png');
      showPosterModal(_cvE, 'emblem-wap', j);
      return Promise.resolve();
    } catch (eEM) {
      showToast('纹样没画好，再点一次', 'warn');
      return null;
    }
  }
  /* R3486：守护图腾壁纸变体——烘焙灵兽底图独立画家。 */
  if (variant && variant.beast) {
    return _wapBeast(j).then(function (cv) {
      var _tB = (typeof navigator !== 'undefined' &&
        (navigator.maxTouchPoints > 0 || 'ontouchstart' in window));
      if (_tB && !/MicroMessenger/i.test(navigator.userAgent || '')) {
        showPosterModal(cv, 'guardian-wap', j);
        return;
      }
      cv.toBlob(function (blob) {
        if (!blob) return;
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = '小满-守护图腾壁纸.png';
        document.body.appendChild(a);
        try { a.click(); } finally {
          setTimeout(function () {
            URL.revokeObjectURL(a.href); a.remove(); }, 800);
        }
      }, 'image/png');
      showPosterModal(cv, 'guardian-wap', j);
    }).catch(function () {
      showToast('壁纸没做好，再点一次', 'warn');
    });
  }
  /* R78（用户实测：灵魂角色卡没锁屏钮）：灵魂角色壁纸变体。
   * R80：底从「透明 PNG 自己铺暖渐变」换成烘焙好的整幅场景 JPEG
   * （wallpapers/ic-wap-<wx>.jpg）——用户实测本轮「洛神……他的『做我的
   * 壁纸』也是很难看」，渐变底没有环境没有氛围。见 _wapSoulIcon 注释。 */
  if (variant && variant.soulicon) {
    return _wapSoulIcon(j).then(function (cv) {
      var _tS = (typeof navigator !== 'undefined' &&
        (navigator.maxTouchPoints > 0 || 'ontouchstart' in window));
      if (_tS && !/MicroMessenger/i.test(navigator.userAgent || '')) {
        showPosterModal(cv, 'soul-wap', j);
        return;
      }
      cv.toBlob(function (blob) {
        if (!blob) return;
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = '小满-灵魂角色壁纸.png';
        document.body.appendChild(a);
        try { a.click(); } finally {
          setTimeout(function () {
            URL.revokeObjectURL(a.href); a.remove(); }, 800);
        }
      }, 'image/png');
      showPosterModal(cv, 'soul-wap', j);
    }).catch(function () {
      showToast('壁纸没做好，再点一次', 'warn');
    });
  }
  /* R3479：灵魂色谱壁纸变体——无日期/无烘焙底图，走独立合成器。 */
  if (variant && variant.nebula) {
    try {
      var _cvN = _wapNebula(j);
      var _tN = (typeof navigator !== 'undefined' &&
        (navigator.maxTouchPoints > 0 || 'ontouchstart' in window));
      if (_tN && !/MicroMessenger/i.test(navigator.userAgent || '')) {
        showPosterModal(_cvN, 'soulart-wap', j);
        return Promise.resolve();
      }
      _cvN.toBlob(function (blob) {
        if (!blob) return;
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = '小满-灵魂色谱壁纸.png';
        document.body.appendChild(a);
        try { a.click(); } finally {
          setTimeout(function () {
            URL.revokeObjectURL(a.href); a.remove(); }, 800);
        }
      }, 'image/png');
      showPosterModal(_cvN, 'soulart-wap', j);
      return Promise.resolve();
    } catch (eNB) {
      showToast('壁纸没做好，再点一次', 'warn');
      return null;
    }
  }
  if (!j || !j.date) {
    showToast('今日运势还没出来，等它算好再做壁纸～', 'warn');
    return null;
  }
  /* R3319（规划C）：里程碑变体——种子混入 tag 拿异图、
   * 落款/文件名带纪念标。
   * R3362：节日/节气日限定主题底图优先（当日最独特的仪式
   * 感）；非节点日才回退种子轮换。 */
  /* R76（#15）：横幅「换一张」挑中的底图优先——用户明确选过就听他的，
   * 没选过才走主题图 → 日期轮换。带 tag 的变体（ beast / nebula /
   * soulart ）要的是异图，不吃这个覆写。 */
  var _nm = (!variant || !variant.tag)
    ? (window._wapPickNm || _wapTheme(j)) : null;
  if (!_nm) {
    var _n = _wapSeed(j.date + ((variant && variant.tag) || ''));
    _nm = 'wap-' + ('0' + _n).slice(-2);
  }
  return _wapImg('/static/wallpapers/' + _nm + '.jpg')
    .then(function (bg) {
      var _sq = !!(variant && variant.square);
      var cv = _wapComposite(j, bg, variant);
      /* 落盘（与海报同款 a.download；移动端走浮层长按）
       * R3326（审-P2）：触屏与海报统一——静默 a[download] 在 iOS/
       * 微信里多半落空，只留浮层长按；桌面照常落盘。 */
      var _touch = (typeof navigator !== 'undefined' &&
        (navigator.maxTouchPoints > 0 || 'ontouchstart' in window));
      /* R76（用户裁决·开运图合并入口）：无 variant = 「今日开运图」。
       * 头像与壁纸本是同一次构图，_sq 只决定裁不裁方——合成时就把
       * 两种比例都备好，弹层里切「存壁纸 9:16 / 存头像 1:1」。
       * 调研（BulkPicTools 中文平台尺寸速查）：微信头像必须 1:1、
       * 锁屏要 9:16，两个比例都是平台硬需求，删哪个都是砍分享出口；
       * 所以合并不删，删的是那枚让人以为是两张图的第二个按钮。 */
      var _ratioOpts = null;
      if (!variant) {
        _ratioOpts = {
          onRatio: function (sq) {
            try { return _wapComposite(j, bg, { square: !!sq }); }
            catch (eRC) { return null; }
          },
          onRatioSave: function (cv2, sq) {
            if (_touch &&
                !/MicroMessenger/i.test(navigator.userAgent || '')) return;
            _wapSave(cv2, j, !!sq, '');
          }
        };
      }
      try {
        if (_touch &&
            !/MicroMessenger/i.test(navigator.userAgent || '')) {
          showPosterModal(cv, _sq ? 'daily-ava' : 'daily-wap', j, _ratioOpts);
          return;
        }
        _wapSave(cv, j, _sq, (variant && variant.fname) || '');
      } catch (eB) {}
      showPosterModal(cv, _sq ? 'daily-ava' : 'daily-wap', j, _ratioOpts);
    })
    .catch(function (e) {
      showToast((e && e.message) || '壁纸没做好，网好了再点一次', 'warn');
    });
}
