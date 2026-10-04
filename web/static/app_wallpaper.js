/* R3317 每日开运壁纸 chunk——懒加载（与 app_poster.js 同款 stub 接管：
 * app.js 的 downloadWallpaper stub 先接住点击，本文件落地后同名
 * 接管。底图是离线烘的 10 张竖幅（scripts/gen_wallpapers.py），
 * 按日轮换；canvas 叠字合成成品（日期锚/判词/开运色签/日签）。
 * 模态与落盘复用 app.js 的 showPosterModal + 海报的 a.download 流。 */
'use strict';

var _WAP_COUNT = 10;   /* /static/wallpapers/wap-00.jpg .. wap-09.jpg */
/* R3362 主题系列：节日/节气日换限定底图（wap-t-*.jpg），对不上
 * 的平凡日子仍走日轮换。节日名对 _FEST_SOLAR/_FEST_LUNAR 产物，
 * 节气名对 j.term.name（后端真节气时刻表，含近似日）。 */
var _WAP_THEME_FEST = {
  '万圣夜': 'halloween', '万圣节': 'halloween',
  '平安夜': 'xmas', '圣诞节': 'xmas',
  '跨年夜': 'nye', '元旦': 'nye',
  '除夕': 'cny', '春节': 'cny', '破五': 'cny', '人日': 'cny',
  '元宵节': 'cny', '填仓节': 'cny', '小年': 'cny', '腊八节': 'cny',
  '情人节': 'valentine', '白色情人节': 'valentine',
  '网络情人节': 'valentine', '521': 'valentine', '七夕': 'valentine',
};
var _WAP_THEME_TERM = {
  '霜降': 'frost', '立冬': 'winterstart',
  '小雪': 'snow', '大雪': 'snow',
  '冬至': 'solstice', '小寒': 'deepcold', '大寒': 'deepcold',
  '立春': 'spring', '雨水': 'spring', '惊蛰': 'spring',
};

function _wapTheme(j) {
  /* 当日限定主题文件名（无 → null）。节日列表逐名对表取首个命中。 */
  try {
    var _f = (j && j.festival) || [];
    for (var i = 0; i < _f.length; i++) {
      var t = _WAP_THEME_FEST[_f[i]];
      if (t) return 'wap-t-' + t;
    }
    var _tm = j && j.term && j.term.name;
    if (_tm && _WAP_THEME_TERM[_tm]) return 'wap-t-' + _WAP_THEME_TERM[_tm];
  } catch (e) {}
  return null;
}
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

function downloadWallpaper(j, variant) {
  if (!j || !j.date) {
    showToast('今日运势还没出来，等它算好再做壁纸～', 'warn');
    return null;
  }
  /* R3319（规划C）：里程碑变体——种子混入 tag 拿异图、
   * 落款/文件名带纪念标。
   * R3362：节日/节气日限定主题底图优先（当日最独特的仪式
   * 感）；非节点日才回退种子轮换。 */
  var _nm = _wapTheme(j);
  if (!_nm) {
    var _n = _wapSeed(j.date + ((variant && variant.tag) || ''));
    _nm = 'wap-' + ('0' + _n).slice(-2);
  }
  return _wapImg('/static/wallpapers/' + _nm + '.jpg')
    .then(function (bg) {
      /* R3328（审-高）：showPosterModal 在此层引用 _wapComposite
       * 局部 _sq——每次点击 ReferenceError，浮层永不开。本层自算。 */
      var _sq = !!(variant && variant.square);
      var cv = _wapComposite(j, bg, variant);
      /* 落盘（与海报同款 a.download；移动端走浮层长按）
       * R3326（审-P2）：触屏与海报统一——静默 a[download] 在 iOS/
       * 微信里多半落空，只留浮层长按；桌面照常落盘。 */
      var _touch = (typeof navigator !== 'undefined' &&
        (navigator.maxTouchPoints > 0 || 'ontouchstart' in window));
      try {
        if (_touch &&
            !/MicroMessenger/i.test(navigator.userAgent || '')) {
          showPosterModal(cv, _sq ? 'daily-ava' : 'daily-wap', j);
          return;
        }
        cv.toBlob(function (blob) {
          if (!blob) return;
          var a = document.createElement('a');
          a.href = URL.createObjectURL(blob);
          var _ymd = String(j.date || '').replace(/-/g, '');
          a.download = (variant && variant.square)
            ? '小满-开运头像-' + _ymd + '.png'
            : '小满-开运壁纸-' + _ymd +
              ((variant && variant.fname) ? '-' + variant.fname : '') + '.png';
          document.body.appendChild(a);
          try { a.click(); } finally {
            setTimeout(function () {
              URL.revokeObjectURL(a.href); a.remove(); }, 800);
          }
        }, 'image/png');
      } catch (eB) {}
      showPosterModal(cv, _sq ? 'daily-ava' : 'daily-wap', j);
    })
    .catch(function (e) {
      showToast((e && e.message) || '壁纸没做好，网好了再点一次', 'warn');
    });
}
