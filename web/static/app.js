/* app.js — 知命前端交互层（R178b 从 index.html 内联抽出并修复全部已知缺陷）。
 *
 * 修掉的实测缺陷（docs/AUDIT_FINDINGS.md，全部可复现）：
 *   R000a-01 BLOCKER  49 处把 $ 函数当对象访问属性（$.rq.value）→ TypeError。
 *                     根因不是笔误多打了点，而是**两套 DOM 取值风格混用**：
 *                     `$('#id')` 是函数调用，`$.id` 是属性访问。本文件只留
 *                     一套：`el(id)` 取元素、`val(id)` 取字符串、`num(id)`
 *                     取整数。全文不存在 `$.` 这种写法。
 *   R000a-02 BLOCKER  #cwBtn / #conceptBtn 只有 HTML 没有处理器 → 已接线。
 *   R000a-03 BLOCKER  .rtab 九标签、data-rsec2 三子标签、#dailyMore 无绑定
 *                     → 全部接线（事件委托，新增标签自动生效）。
 *   R000a-04 MAJOR    前端读 j.llm_out / j.items / j.addresses，后端给
 *                     interpretation / records / evidence → 字段名全部以
 *                     **TestClient 实测响应**为准（见本轮 temp_probe_shapes）。
 *   R000a-05 MAJOR    模板串 `</strong>` 拼写损坏 + #threadBtn 发 {topic}
 *                     但后端要 {kind,claim,method} → 标签闭合修正，请求体
 *                     改为符合 ThreadRecordRequest 的 refusal 型 claim。
 *
 * 另外修掉三处实测契约漂移（前端发的参数后端根本不认，不在缺陷清单里但同族）：
 *   * /api/huangli 前端发 year/month/day，后端只认 date=YYYY-MM-DD。
 *   * /api/liuyao 前端 select 的 value 是 "dice"，后端只认 coins|time。
 *   * /api/works 返回的书 id 键是 `id` 不是 `work_id`；单元数键是 `units`。
 *
 * 纪律：所有插入 HTML 的动态串一律经 esc()；解读文本按 sections 结构渲染，
 * 不做 markdown → HTML 解析（历史上 renderMD 出过存储型 XSS，D-060）。
 * REPAIR 阶段不加美化与动效，只让功能可用。
 */
'use strict';
/* R218a-01 构建标记——注释会被服务时 minify 剥掉，verify_r218a 查的
 * 是「服务端 app.js 含此标记」，改放字符串字面量保证压缩后仍在。 */
var _APP_BUILD_MARK = 'R218a-01';

/* ── DOM 工具：只有这一套，杜绝 $ 函数/对象混用 ────────────────── */

/** 按 id 取元素（不带 #）。取不到返回 null，调用方自行判空。 */
function el(id) {
  return document.getElementById(id);
}

/** 取输入框字符串值，trim 后返回；元素不存在返回 ''（不抛异常）。 */
function val(id) {
  const node = el(id);
  return node ? zwClean(node.value == null ? '' : node.value) : '';
}

/* R230k（R23-P3-4）：String.trim() 不剥零宽格式符（\u200B-\u200D/
 * \uFEFF）——只含它们的输入会过非空检查：聊天发出「隐形气泡」、
 * 排盘 question 写入历史成空白行。统一剥。 */
function zwClean(s) {
  /* R230t（R33-P3-17）：对齐后端 _ZW_RE——bidi 覆盖符（\u202a-\u202e）
   * 也剥，粘贴 RTL 文本不再前后端口径不一。 */
  return String(s || '').replace(/[\u200B-\u200D\uFEFF\u202A-\u202E]/g, '').trim();
}

/** 取输入框整数值；空或非法返回 null（让调用方决定是否发送该字段）。 */
var _numBadLast = 0;
function num(id) {
  var raw = val(id);
  /* R2350f（R101-P2-11）：中文输入法常产出全角数字 １９９０——
   * 归一化成 ASCII 再走校验，不当脏值拦。 */
  raw = raw.replace(/[０-９]/g, function (c) {
    return String.fromCharCode(c.charCodeAt(0) - 0xFEE0);
  });
  if (raw === '') return null;
  /* R2350e（R101-P0-1）：parseInt 静默吞错——「1e1」→1、
   * 「30.5」→30、「1990e2」→1990，盘按错值排而用户毫不知情。
   * 只认纯整数文本；脏值标红并统一提醒一次（多字段不刷屏）。 */
  if (!/^-?\d+$/.test(raw)) {
    const _be = el(id);
    if (_be) {
      _be.setAttribute('aria-invalid', 'true');
      const _nbClr = function () {
        _be.removeAttribute('aria-invalid');
        _be.removeEventListener('input', _nbClr);
      };
      _be.addEventListener('input', _nbClr);
    }
    const _nw = Date.now();
    if (_nw - _numBadLast > 2500) {
      _numBadLast = _nw;
      showToast('红框里的数字格式不对：只认整数（比如 1990、8）', 'warn');
    }
    return null;
  }
  return parseInt(raw, 10);
}

/** 取复选框布尔值。 */
function checked(id) {
  const node = el(id);
  return !!(node && node.checked);
}

/* R228v：全局 JS 错误兜底——此前任何未捕获异常（典型如 ReferenceError）
 * 静默打断点击处理器，用户看到「点了没反应」无任何线索。统一 toast 提示
 * 可重试，不打断后续操作。img 资源 onerror 走元素级 is-missing，不进这里。 */
window.addEventListener('unhandledrejection', function () {
  showToast('操作没完成，网络或服务可能不稳，再试一次？', 'warn');
});
window.addEventListener('error', function (e) {
  if (e && e.message) showToast('页面出了点小状况，刷新一下试试～', 'warn');
});

/** HTML 转义——所有动态文本入 innerHTML 前必过这里。 */
/* R230h（R20-F6）：浏览器本地今天 ISO——跨零点窗口里后端
 * date.today() 与用户看见的「今天」可能不是同一天；凡问「今天」
 * 的请求都显式带这个日期（daily/xingzuo/ask_date 锚点统一）。 */
function todayIso() {
  var t = new Date();
  return t.getFullYear() + '-' + String(t.getMonth() + 1).padStart(2, '0') +
    '-' + String(t.getDate()).padStart(2, '0');
}

/* R233j（R46）：日盐确定性抽池——同 copy_bank 纪律（同输入同输出，
 * 跨天自动换）。salt 传视图/主题名区分池域。 */
function _hashPick(pool, str) {
  if (!pool || !pool.length) return '';
  var h = 0;
  for (var i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
  return pool[h % pool.length];
}
/* R3249d：数字版 _hashPick——同一字符串永远出同一个数（维度分抖动用）。 */
function _hashNum(str) {
  var h = 0;
  for (var i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0;
  return h;
}
function _dayPick(pool, salt) {
  return _hashPick(pool, String(salt || '') + '|' + todayIso());
}
/* R233n（R47）：按盐确定性抽 N 个不重复项——同一天同一盐顺序一致，
 * 跨天自动换。播种洗牌（LCG），不真随机。 */
function _dayPickN(pool, n, salt) {
  var arr = (pool || []).slice();
  if (arr.length <= n) return arr;
  /* R233r（R50-#6）：salt 之外再拼 todayIso——不带日期盐的调用点
   * 也能跨天轮换（与 _dayPick 同一契约）。 */
  var seed = 0, src = String(salt || '') + '|' + todayIso();
  for (var i = 0; i < src.length; i++) seed = (seed * 31 + src.charCodeAt(i)) >>> 0;
  for (var k = arr.length - 1; k > 0; k--) {
    seed = (seed * 1664525 + 1013904223) >>> 0;
    var j = seed % (k + 1), t = arr[k]; arr[k] = arr[j]; arr[j] = t;
  }
  return arr.slice(0, n);
}
/* R233n（R47-Top5-3）：星期中文 + 日签号（按日哈希 1-64）。 */
function _weekdayCn(dateStr) {
  var d = new Date(String(dateStr || todayIso()) + 'T00:00:00');
  if (isNaN(d)) return '';
  return '周' + ['日','一','二','三','四','五','六'][d.getDay()];
}

/* R2341（R57-P2-4）：ISO 日期 →「M月D日 · 周X」海报副题口径 */
function _cnDateSub(dateStr) {
  var d = _pStr(dateStr) || todayIso();
  var md = d.slice(5).replace('-', '月');
  if (md.charAt(0) === '0') md = md.slice(1);
  /* R3327-P2-8：日也同法去零——「10月03日」与卡面「10月3日」不一致。 */
  md = md.replace(/月0/, '月');
  return md + '日 · ' + _weekdayCn(d);
}
function _signNo(dateStr) {
  /* R2349s（R83-P0-2）：h*31+ord 玩具哈希的低位扩散差——输入串差异
   * 集中在末尾两个字符，60 天实测只用上 24-43/64 的签池。换 FNV-1a
   * （xor-then-multiply），低位雪崩，64 签全覆盖。 */
  var src = 'sign|' + String(dateStr || todayIso()), h = 2166136261;
  for (var i = 0; i < src.length; i++) {
    h = (h ^ src.charCodeAt(i)) >>> 0;
    h = (h * 16777619) >>> 0;
  }
  /* fmix32 收尾雪崩——%64 只取低 6 位，需要充分混合。
   * 实测：旧哈希全年只覆盖 43/64 且 60 天窗塌到 24；现在全年 64/64。 */
  h = (h ^ (h >>> 16)) >>> 0; h = Math.imul(h, 0x85EBCA6B) >>> 0;
  h = (h ^ (h >>> 13)) >>> 0; h = Math.imul(h, 0xC2B2AE35) >>> 0;
  h = (h ^ (h >>> 16)) >>> 0;
  return h % 64 + 1;
}

/* R2349l（R73-P1-1）：签号 1–64 ↔ 周易 64 卦——每日一签从此有真签文。
 * 每项「卦名 · 一句白话签意」（白话是我们写的安抚口径，不冒充卦辞）。 */
/* R3328+（积压 _LC_HEX 收敛）：幸运色 hex 唯一真源——此前
 * app.js/app_wallpaper.js 各存一份同款字面量，双轨漂移风险。
 * 本文件整体裹在 IIFE 里，顶层 var 不出全局——显式挂 window，
 * 壁纸懒加载经 window.LC_HEX 读同一份。 */
var LC_HEX = window.LC_HEX = { '青绿色': '#7fb8a4', '石榴红': '#d96a5f',
               '鹅黄色': '#f0c95c', '珍珠白': '#efe9dc',
               '雾蓝色': '#8fa8c8' };
var _SIGN_GUA = ['',
  '乾为天·拿出干劲的日子', '坤为地·顺势承住就好', '水雷屯·开头难别怕',
  '山水蒙·不懂就问', '水天需·等一等也在走', '天水讼·别硬碰硬',
  '地水师·靠章法不靠冲', '水地比·亲近才有力量', '风天小畜·小事收着攒',
  '天泽履·踩稳每一步', '地天泰·通泰顺气日', '天地否·塞住时养气',
  '天火同人·找同路人', '火天大有·丰盛别嘚瑟', '地山谦·低一寸路宽一丈',
  '雷地豫·开心可以预约', '泽雷随·跟对节奏', '山风蛊·旧账翻出来修',
  '地泽临·好运靠岸', '风地观·先看清楚再动', '火雷噬嗑·卡住就咬碎它',
  '山火贲·打扮一下有好运', '山地剥·落叶归土也养根', '地雷复·回头是新生',
  '天雷无妄·别瞎折腾', '山天大畜·攒大能量', '山雷颐·先照顾好自己',
  '泽风大过·担子重了找帮手', '坎为水·水深处稳住心', '离为火·亮出你的光',
  '泽山咸·心动有回应', '雷风恒·长久的才算数', '天山遁·退一步也漂亮',
  '雷天大壮·力气用对地方', '火地晋·太阳升起来了', '地火明夷·光先收一收',
  '风火家人·家里那盏灯', '火泽睽·不一样也能同行', '水山蹇·山高慢点爬',
  '雷水解·结打开了', '山泽损·舍一点得更多', '风雷益·加柴的时候',
  '泽天夬·下决心就干净利落', '天风姤·相遇有缘别贪', '泽地萃·聚起来才是席',
  '地风升·往上走别回头', '泽水困·困住时先喘口气', '水风井·老井也有新水',
  '泽火革·换季换新皮', '火风鼎·好饭要慢炖', '震为雷·响一声别慌',
  '艮为山·站住也是功夫', '风山渐·慢慢来比较快', '雷泽归妹·急嫁不如好嫁',
  '雷火丰·盛大时记得收', '火山旅·路上也是家', '巽为风·风知道方向',
  '兑为泽·笑是最好的风水', '风水涣·散开再聚拢', '水泽节·有节有度才自由',
  '风泽中孚·真心换真心', '雷山小过·小事做到位', '水火既济·成了也留着神',
  '火水未济·没完就是还有戏'];
function _signText(dateStr) {
  return _SIGN_GUA[_signNo(dateStr)] || '';
}
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}

/* R233h（R43-#14）：结果容器不再整区 aria-live——长结果会让读屏
 * 把整篇重读一遍。改走专用 #srLive 短句播报：「XX结果出来了」。 */
var _PAINT_LABEL = { result: '排盘', thResult: '桃花', hhResult: '合婚',
  qmResult: '起名', lyResult: '六爻', xzResult: '星座', hlResult: '黄历',
  trResult: '塔罗', dailyDetail: '今日解读', historyDetail: '历史详情',
  researchResult: '研究', searchResult: '搜索', addrResult: '定位',
  compareResult: '对照', conceptResult: '概念分布', cwResult: '两书对照',
  worksResult: '书目', threadResult: '研究线程', bsStructure: '结构',
  bsChapter: '章节', bsSummary: '知识卡', nameReviewOut: '名字点评',
  dmResult: '解梦' };   /* R3214：解梦结果此前漏登记，读屏只报「新内容」 */
var _paintSilent = false;
function _srSay(t) {
  var n = el('srLive');
  if (!n) return;
  /* 清空再写——同文本连续两次也要触发播报。 */
  n.textContent = '';
  setTimeout(function () { n.textContent = t; }, 30);
}

/** 把内容写进结果容器；容器不存在时静默返回。 */
function paint(/* v3-fx-guard */id, html) {
  const node = el(id);
  if (node) {
    node.classList.remove('is-working');   /* R233k：新结果落地摘忙态 */
    node.classList.remove('is-stale');     /* R2350e：重算落地摘过期标 */
    node.hidden = false;
    node.innerHTML = html;
    if (!_paintSilent && html) {
      _srSay((_PAINT_LABEL[id] || '新内容') + '出来了，往下读查看');
    }
    /* R218a-巡4（E-a）：成功态才显示「运算结论为坐标事实…」技术说明。
     * 结果区有内容时 footnote 跟随显示，空/失败时不显示——失败态整卡
     * 只留错误信息+重试按钮，不再残留成功期说明文字。 */
    document.querySelectorAll('.footnote').forEach(function (fn) {
      fn.hidden = !html;
    });
    if (typeof attachChatEntry === 'function') attachChatEntry(node);
  }
}

function busy(id, text) {
  /* R230x（P2-7）：加载态带三点跳动效（复用 chat-typing），不再干等文本。
   * R233h：加载中转态不播报（播了也只会说「出来了」误导）。
   * R233k（R45-Top5-5）：容器已有结果时不再整清——原位降饱和+挂
   * 加载签（黄历 .is-loading 模式全站推广），失败时旧卡还在。 */
  var node = el(id);
  /* R233r（R50-#5）：已挂加载签时再次 busy——只更新签文案，
   * 不再落 paint 整清（旧卡保留的承诺在连点下也得成立）。 */
  if (node && node.classList.contains('is-working')) {
    var _t0 = node.querySelector('.res-loading-tag');
    if (_t0) {
      _t0.innerHTML = esc(text) +
        ' <span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span>';
      return;
    }
  }
  /* R2350a（R94-P2-8）：「仅 .no-evidence 错误 + .hl-ask/fav-row
   * 伴生行」此前被当成「有内容」→ 错误走 fail-line 置顶、旧错误条
   * 残留，连续失败堆叠。这类空壳同样归整清分支。 */
  var _onlyErr = false;
  if (node && node.querySelector('.no-evidence')) {
    _onlyErr = !Array.prototype.some.call(node.children, function (c) {
      return !(c.classList.contains('no-evidence') ||
               c.classList.contains('hl-ask') ||
               c.classList.contains('fav-row') ||
               c.classList.contains('ph-skel'));
    });
  }
  if (node && node.innerHTML.trim() && !_onlyErr &&
      !node.querySelector('.res-loading-tag')) {
    node.classList.add('is-working');
    var tag = document.createElement('div');
    tag.className = 'res-loading-tag';
    tag.innerHTML = esc(text) +
      ' <span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span>';
    node.prepend(tag);
    node.hidden = false;
    var fe = node.querySelector('.fail-line'); if (fe) fe.remove();
    return;
  }
  _paintSilent = true;
  /* R2341（R57-P2-12）：空容器加载态上骨架行——纯文本像卡死 */
  paint(id, '<div class="no-evidence">' + esc(text) +
    ' <span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span></div>' +
    '<div class="ph-skel" aria-hidden="true"><i></i><i></i><i></i></div>');
  _paintSilent = false;
}

/* R218a-巡4（E-a/E-b）：失败态——清掉成功期说明文字 + 内联「重新测算」
 * 重试按钮。retry 用闭包记住上次提交动作，点击即原样 re-dispatch。 */
/* R229z续17：JS 运行时错/非 JSON 响应的 message 是英文技术原文
 * （"Cannot read properties of null"、"Failed to fetch"……），直接贴上屏
 * 违和且泄漏实现细节。fail/failWithRetry 统一过一遍：把英文技术片段
 * 换成人话尾巴（前面中文前缀「查询失败：」保留）。 */
function _humanizeErr(text) {
  if (typeof text !== 'string') return '出了点小状况，稍后再试';
  /* R2345（R62-P1-6）：服务器内部路径直接泄到屏（「索引缺失或为空：
   * /home/ubuntu/repos/books/data/index/corpus.db」）——先剥绝对路径，
   * 再对基础设施类错误整条换成安抚话术。 */
  text = text.replace(/[\w.\-~]*(?:\/[\w.\-~]+){2,}/g, '…');
  if (/索引缺失|corpus\.db|build_index|sqlite|OperationalError|Permission denied/i.test(text)) {
    return '排盘服务还没睡醒，一会儿再来～';
  }
  /* R2346（R58-P1-1）：服务端 detail 透传的英文异常原文（
   * 「RuntimeError: ... at foo.py:123」/Traceback）——5xx 技术串
   * 不上屏，统一人话。 */
  if (/\b[A-Za-z_]\w*(?:Error|Exception|Warning)\b|Traceback|:\s*line\s*\d+|\.py["'\s,:]/.test(text)) {
    return '服务打个盹了，稍后再戳我～';
  }
  return text.replace(
    /(?:Failed to fetch|Load failed|Network request failed|Cannot read propert\w+|is not defined|is not a function|out of range|Unexpected token|Script error|AbortError|TimeoutError)[^。；\n]*/gi,
    '网络或服务出了点小状况');
}
function failWithRetry(id, text, retryFn) {
  document.querySelectorAll('.footnote').forEach(function (fn) { fn.hidden = true; });
  const node = el(id);
  if (!node) return;
  /* R233k：同 fail()——忙态容器保旧卡，错误行置顶+挂重试钮。 */
  if (node.classList.contains('is-working')) {
    node.classList.remove('is-working');
    var _tg2 = node.querySelector('.res-loading-tag'); if (_tg2) _tg2.remove();
    var _oe2 = node.querySelector('.fail-line'); if (_oe2) _oe2.remove();
    var _e2 = document.createElement('div');
    _e2.className = 'fail-line';
    _e2.innerHTML = '<span>' + esc(_humanizeErr(text)) + '</span>' +
      (typeof retryFn === 'function'
        ? ' <button type="button" class="ghost" data-retry>🔄 重新测算</button>' : '');
    node.prepend(_e2);
    var _b2 = _e2.querySelector('[data-retry]');
    if (_b2) _b2.addEventListener('click', retryFn);
    /* R3320-P3：双通道复读——fail-line 已贴卡内，toast 同文案不再双出
     * （与 _failField 的既有口径一致；读屏另有 _srSay）。 */
    _srSay('有点小状况：看看页面提示');
    return;
  }
  node.hidden = false;
  node.innerHTML =
    '<div class="no-evidence">' + esc(_humanizeErr(text)) +
    (typeof retryFn === 'function'
      ? ' <button type="button" class="ghost" data-retry ' +
        'style="margin-left:8px;">🔄 重新测算</button>' : '') +
    '</div>';
  /* R230t（R33-P3-7）：id=retryBtn 两个面板同时失败时重复 id——
   * el() 只绑第一个，另一个重试钮是死的。改用容器内查询+类名。 */
  const btn = node.querySelector('[data-retry]');
  if (btn && typeof retryFn === 'function') btn.addEventListener('click', retryFn);
}

function fail(id, text) {
  /* R233h：失败态播报说人话，不报「结果出来了」。
   * R233k（R45-Top5-5）：is-working 容器有旧结果——错误改置顶行+
   * toast，旧卡保留可回看；空容器维持整清。 */
  var _n = el(id);
  if (_n && _n.classList.contains('is-working')) {
    _n.classList.remove('is-working');
    var _tg = _n.querySelector('.res-loading-tag'); if (_tg) _tg.remove();
    var _oe = _n.querySelector('.fail-line'); if (_oe) _oe.remove();
    var _e = document.createElement('div');
    _e.className = 'fail-line';
    _e.textContent = _humanizeErr(text);
    _n.prepend(_e);
    /* R3320-P3：同上——卡内已有错误行，toast 不双出。 */
    _srSay('有点小状况：看看页面提示');
    return;
  }
  _paintSilent = true;
  paint(id, '<div class="no-evidence">' + esc(_humanizeErr(text)) + '</div>');
  _paintSilent = false;
  _srSay('有点小状况：看看页面提示');
}

/* R233k（R45-Top5-1）：年月日真实日期校验前置——「2月31日」此前要
 * 白跑一轮后端往返才在屏外报错。这里本地算出当月天数，出错就地标红
 * +聚焦出错格+toast。返回出错 input id（无→null）。 */
function _badYmdField(yId, mId, dId) {
  var y = num(yId), m = num(mId), d = num(dId);
  if (y == null || m == null || d == null) return null;
  if (m < 1 || m > 12) return mId;
  if (d < 1 || d > new Date(y, m, 0).getDate()) return dId;
  return null;
}
/* R2350e（R101-P2-1/P2-2）：范围越界同界预检——此前 qm/th/hh 的年份
 * 和所有时辰/分钟框没有前端界，越界要白跑一轮后端 422/400 才报。 */
function _badRange(fid, min, max) {
  var n = num(fid);
  return n != null && (n < min || n > max);
}
function _failField(fId, boxId, text) {
  var f = fId && el(fId);
  if (f) {
    f.setAttribute('aria-invalid', 'true');
    var _clr = function () {
      f.removeAttribute('aria-invalid');
      f.removeEventListener('input', _clr);
    };
    f.addEventListener('input', _clr);
    try { f.focus(); } catch (e) {}
  }
  if (boxId) fail(boxId, text);
  /* R2341（R57-P2-10）：字段提示已挂在卡内，toast 同文案双出即复读——
   * 卡内提示渲染成功时不再弹 toast。 */
  if (!(boxId && el(boxId))) showToast(text, 'warn');
}

/** R228i：Pydantic 422 的 detail 是 [{loc:[...,field],msg}] 数组，
 * 以前 JSON.stringify 原样弹给用户。翻成中文人话。 */
var _FIELD_CN = { year: '年份', month: '月份', day: '日期', hour: '时辰',
  minute: '分钟',
  gender: '性别', surname: '姓氏', names: '候选名', session_id: '聊天会话',
  message: '消息', q: '查询词', work_id: '书名', seed: '随机种子',
  a_year: '甲年', a_month: '甲月', a_day: '甲日',
  a_hour: '甲时辰', a_gender: '甲性别',
  b_year: '乙年', b_month: '乙月', b_day: '乙日',
  b_hour: '乙时辰', b_gender: '乙性别', calendar_type: '历法',
  scope: '范围', range_start: '区间起始', range_end: '区间结束',
  ask_date: '哪天问的', ask_hour: '几点问的', location: '所在地',
  question: '问题', facts: '事实上下文', n: '张数',
  date: '日期', days: '天数', limit: '条数', style: '风格',
  topic: '主题', kind: '类型', claim: '论点', method: '方法',
  /* R230r（R30-#19）：研究面字段补齐——此前 evidence/tid/max_addresses
   * 走不进中文映射，toast 出英文原文。 */
  evidence: '证据', tid: '线程号', thread_id: '线程号',
  /* R2350e（R101-P2-5）：古籍面字段——422 不再露英文键名。 */
  gua: '卦号', yao: '爻位', scheme: '编址方式', addr1: '节号',
  addr2: '单元号', addr_name: '节名',
  max_addresses: '地址数', per_work: '每书条数',
  ref_id: '对象', title: '标题', text: '内容', work: '书号' };
function _humanize422(detail) {
  try {
    var first = detail[0] || {};
    var loc = first.loc || [];
    var field = String(loc[loc.length - 1] || '');
    var cn = _FIELD_CN[field];
    var msg = String(first.msg || '');
    /* R3265（R3247-P2-10）：服务端 422 已发中文 msg（「至少 1 字」
     * 「最多 400 字」）时正则全落空、精度丢进兜底——中文 msg 且
     * 无字段名裸露时直通显示。 */
    if (/[一-鿿]/.test(msg) && !/[a-zA-Z_.]{2,}\s*(?:is|should|must|required)/.test(msg)) {
      /* R3348（审-中-1）：中文 msg 直通把「至少 1 字」裸贴——多字段
       * 表单里看不出是哪个字段。loc 末位有中文名时补「姓氏：」前缀。 */
      return cn ? cn + '：' + msg : msg;
    }
    /* R229n（R6-#3）：cn+msg 直通会把 pydantic 英文原文贴上屏
     * （"张数：Input should be less than or equal to 10"）——
     * 按 msg 模式翻中文，翻不了的给泛化中文，绝不回吐英文。 */
    if (cn) {
      var m;
      if ((m = /at most (\d+) characters/i.exec(msg))) return cn + '最多 ' + m[1] + ' 字';
      if ((m = /at least (\d+) characters/i.exec(msg))) return cn + '至少 ' + m[1] + ' 字';
      if ((m = /less than or equal to ([\d.-]+)/i.exec(msg))) return cn + '不能大于 ' + m[1];
      if ((m = /greater than or equal to ([\d.-]+)/i.exec(msg))) return cn + '不能小于 ' + m[1];
      if ((m = /at most (\d+) items?/i.exec(msg))) return cn + '最多 ' + m[1] + ' 项';
      if ((m = /at least (\d+) items?/i.exec(msg))) return cn + '至少 ' + m[1] + ' 项';
      /* R230q（R28-P3-9）：类型错/缺字段的英文原文兜底——
       * "Input should be a valid integer" / "Field required" 不上屏。 */
      if (/valid integer|valid number|valid finite|unable to parse|int_parsing|float_parsing/i.test(msg)) {
        return cn + '要填数字哦';
      }
      if (/field required|missing/i.test(msg) || first.type === 'missing') {
        return cn + '还没填';
      }
      if (/valid date|date_parsing|datetime/i.test(msg)) return cn + '不是合法日期';
      return cn + '填写有误或为空';
    }
    return '这条信息好像没填对，再检查一下～';
  } catch (e) { return '这条信息好像没填对，再检查一下～'; }
}

/** fetch + JSON，把 !ok 的 detail 变成 Error，让调用方只写一个 catch。
 * opts.silent=true（R228k）：不弹 toast——轮询类调用（/api/ai/{tid}）的
 * 失败本来就有「整块不渲染」的降级语义，不该每 500ms 一张 toast 循环 40s。 */
var API_TIMEOUT_MS = 20000;
/* R230z（R36-P1-1）：渲染体抽为顶层 builder——历史台账「复看」
 * 按 rec.type 回放同一渲染；do* 里只剩 paint 一行。 */
function buildHehunResult(j) {
  const a = j.a_bazi || {};
  const b = j.b_bazi || {};
  /* R230z（R36-P1-2）：昵称对——有昵称就用「小鱼 × 阿哲」当头 */
  var _hn = (j.a_name || j.b_name || '') ?
    ((j.a_name || '我') + ' × ' + (j.b_name || 'TA')) : '';
  /* R3304（审-P3）：昵称对嵌 h2<small> 会孤行——「八字合婚」独占
   * 一行后名字孤零零吊在第二行视觉断节。拆成独立配对行。 */
  /* R3247：明星合盘标题换「和「××」的合盘」——一眼可晒的素材位。 */
  let html = '<div class="card"><h2>' +
    (j.celeb ? '💕 和「' + esc(j.celeb.n) + '」的合盘' : '💕 八字合婚') +
    '</h2>' +
    (_hn ? '<p class="hh-pair">' + esc(_hn) + '</p>' : '') +
    /* R3247：小满式导语压住「真爱配对」暗示——追星图个乐，
     * 生日是公开资料，时辰未知，判词别当真。 */
    (j.celeb ? '<p class="celeb-lead">✨ 追星合盘图个乐：' +
      esc(j.celeb.n) + ' 的生日来自公开资料（时辰未知按正午排），' +
      '判词就着热闹看，别当真～</p>' : '');
  html += _birthEcho('hehun');
  /* R3340（审-P2）：节气边界/夏令时/0点跨日警示——服务端 warn
   * 已透传（「A 盘：…」「B 盘：…」带侧标），前端此前不渲染。 */
  if (j.warn && j.warn.length) {
    html += '<p class="warn">' + esc(j.warn.join('；')) + '</p>';
  }
  // R193b：分享海报入口（对齐排盘 shareBazi，T3.1 同款零依赖 Canvas）
  /* R233n：三枚 fav-btn 全按 right:24/84px 绝对定位会互叠——本卡
   * 三钮改用 .hh-btns flex 行（静态流，gap 间隔）。 */
  /* R2349s（R84-P2-20）：三域补口吻开关——此前只有 bazi/liuyao/tarot
   * 能切专业视角。 */
  html += _festivalBand();
  /* R3212：合婚坐标原值（四柱/日支关系/纳音/十神互见）收进折叠——
   * 数据零删减，想看的一眼展开；此前只在 pro 开关下可见。 */
  {
    var _hhpills =
      /* R3233：时辰留空侧第 4 柱显示「时辰未知」不显示默认午时。 */
      (j.a_bazi && j.a_bazi.render ? '<span class="pill">A 四柱：' + esc(_pillarsHonest(j.a_bazi.render, val('hh_a_hour') !== '')) + '</span>' : '') +
      (j.b_bazi && j.b_bazi.render ? '<span class="pill">B 四柱：' + esc(_pillarsHonest(j.b_bazi.render, val('hh_b_hour') !== '')) + '</span>' : '') +
      (j.day_zhi_rel ? '<span class="pill">日支关系：' + esc(j.day_zhi_rel) + '</span>' : '') +
      (j.nayin_rel ? '<span class="pill">纳音：' + esc(j.nayin_rel) + '</span>' : '') +
      (j.god_a_sees_b ? '<span class="pill">十神互见：' + esc(j.god_a_sees_b) + ' ↔ ' + esc(j.god_b_sees_a || '') + '</span>' : '');
    if (_hhpills) {
      html += '<details class="warm-basis warm-pro-fold"><summary>📐 合婚坐标（干支原值）</summary>' +
        '<div class="pill-row">' + _hhpills + '</div></details>';
    }
  }
  html += '<div class="hh-btns">';
  html += '<button class="ghost fav-btn" type="button" id="shareHehun" ' +
    'title="生成分享图">📸 分享图</button>';
  /* R230z（R36-P1-2/P2-3）：存这对——写入 /api/favorites，下次表单上方
   * 的「测过的 CP」chips 一键回填。 */
  html += '<button class="ghost fav-btn" type="button" id="hhSavePair" ' +
    'title="把这对的生辰存下来，下次一键回填">💝 存这对</button>';
  /* R233n（R47-Top5-1）：喊 TA 来对盘——把你的盘编进链接发给 TA，
   * 对方落地自动填好你这边、只需填自己。 */
  html += '<button class="ghost fav-btn" type="button" id="hhInvite" ' +
    'title="复制邀请链接发给 TA">🔗 喊 TA 来对盘</button></div>';
  /* R2349l（R73-P1-6）：合拍指数——小红书传播形态是数字，
   * 定性标签没法晒；分数是大字素材。 */
  if (j.match_score != null) {
    /* R3252（用户实测「可以加一些表盘」）：合拍指数上仪表盘——
     * 半圆弧形 SVG 表盘，分数坐在盘心，档位色随分数走。
     * 双熊同框插画置顶，结果先看图再看数。 */
    var _msN0 = Number(j.match_score);
    var _msP = Math.min(Math.max(isNaN(_msN0) ? 0 : _msN0, 0), 99);
    var _arcL = (Math.PI * 55).toFixed(1);
    var _arcOff = (Math.PI * 55 * (1 - _msP / 99)).toFixed(1);
    var _gt = _msN0 >= 85 ? ' hi' : _msN0 >= 60 ? ' mid' : ' low';
    html += '<div class="hh-hero">' +
      '<img class="hh-bear" src="/static/cream/hehun-bear.jpg" ' +
      'alt="合拍指数插画" loading="lazy" decoding="async" ' +
      'onerror="this.remove()">' +
      '<div class="hh-gauge' + _gt + '" role="img" aria-label="合拍指数 ' +
      esc(String(j.match_score)) + ' 分（满分 99）">' +
      '<svg viewBox="0 0 120 72" aria-hidden="true">' +
      '<path class="hh-g-tr" d="M10 66 A55 55 0 0 1 110 66"/>' +
      '<path class="hh-g-fl" d="M10 66 A55 55 0 0 1 110 66" ' +
      'stroke-dasharray="' + _arcL + '" stroke-dashoffset="' + _arcOff +
      '"/></svg>' +
      '<div class="hh-g-num"><strong>' + esc(String(j.match_score)) +
      '</strong><span class="hh-g-sub">/99</span></div>' +
      '<div class="hh-g-cap">合拍指数</div></div></div>';
    /* R2349t（R88-6）：高分稀有度——85+ 和 60 分不该同一张脸，
     * 多一个截图动机。 */
    var _msN = Number(j.match_score);
    if (_msN >= 90) {
      html += '<p class="hh-tier">🏆 百里挑一款合拍，这一分值得晒</p>';
    } else if (_msN >= 85) {
      html += '<p class="hh-tier">💗 高分合拍，这缘分不多见</p>';
    } else if (_msN < 45) {
      /* R3087（specs/010）：低分此前裸数零解读——判词层说偏不合适
       * 时卡面也不能装看不见。与 warm 判词档同口径。 */
      html += '<p class="hh-tier hh-tier-low">⚖️ 判词偏硬，这组判定不客气，下面把成本摆出来</p>';
    } else if (_msN < 60) {
      html += '<p class="hh-tier hh-tier-mid">🌗 磕绊偏多，要花力气磨合，下面直说磨在哪</p>';
    }
  }
  // R187b：人话视图置顶（specs/005 US4）
  if (j.warm) {
    html += '<div class="warm-wrap"><div class="warm-l0">' +
      /* R3319-P2：「牌·正：」内部编码出屏——与海报同款转顺读。 */
      esc(String(j.warm.one_liner || '').replace(/·\s*([正逆])\s*：/, '（$1位）：')) +
        '</div><div class="warm-reply">';
    (j.warm.reply || []).forEach(function (ln) {
      html += '<p>' + esc(ln) + '</p>';
    });
    html += '</div>';
    if (j.warm.badge) html += '<div class="warm-badge">' + esc(j.warm.badge) + '</div>';
    html += '</div>';
  }
  html += '<div class="calc-grid">';
  /* R2350b（R98-P2-13）：甲乙块此前只露年柱+日柱两截，完整四柱
   * 躺在 a_bazi.render 里没用上；「日主」一词随行翻译成本命五行。 */
  html += '<div class="calc-block" style="border-left:3px solid var(--c-bazi);">' +
    '<h3 style="color:var(--c-bazi-ink);">' + esc(j.a_name || '甲') + '</h3>' +
    /* R3247：受邀链落地时明星在 A 侧——生辰后挂「公开资料」小字。 */
    (j.celeb && j.celeb.side === 'a'
      ? '<span class="celeb-src">' + j.celeb.y + '年' + j.celeb.m + '月' +
        j.celeb.d + '日 · 公开资料</span>' : '') +
    '<p style="font-family:var(--font-serif);font-size:18px;"' +
    (a.render ? ' title="四柱：' + esc(a.render) + '"' : '') + '>' +
    esc(a.year || '') + ' · ' + esc(a.day || '') + '</p>' +
    '<p style="font-size:13px;color:var(--secondary);" ' +
    'title="日主=出生那天的天干，代表本命五行">本命（日主）：' +
    esc(a.day_master || '') + '（' + esc(j.day_wx_a || '') + '）</p></div>';
  html += '<div class="calc-block" style="border-left:3px solid var(--c-hehun);">' +
    '<h3 style="color:var(--c-hehun-ink);">' + esc(j.b_name || '乙') + '</h3>' +
    /* R3247：明星侧生辰后挂「公开资料」小字注明来源。 */
    (j.celeb && j.celeb.side === 'b'
      ? '<span class="celeb-src">' + j.celeb.y + '年' + j.celeb.m + '月' +
        j.celeb.d + '日 · 公开资料</span>' : '') +
    '<p style="font-family:var(--font-serif);font-size:18px;"' +
    (b.render ? ' title="四柱：' + esc(b.render) + '"' : '') + '>' +
    esc(b.year || '') + ' · ' + esc(b.day || '') + '</p>' +
    '<p style="font-size:13px;color:var(--secondary);" ' +
    'title="日主=出生那天的天干，代表本命五行">本命（日主）：' +
    esc(b.day_master || '') + '（' + esc(j.day_wx_b || '') + '）</p></div>';
  html += '</div><div class="pill-row">';
  const relLabel = j.clash ? '六冲' : j.combine ? '六合' : '无冲合';
  const relColor = j.clash ? 'var(--c-bazi-ink)' : j.combine ? 'var(--c-good-ink)' : 'var(--secondary)';
  /* R2509（审-P1-5）：年支 pill 加「属相」注解——默认受众对属相比
   * 年支有概念；「非相生」在相克盘上弱化事实（同屏 warm 行说相克），
   * 改如实显「相克」。 */
  html += '<span class="pill sm" style="background:' + relColor + ';">属相（' +
    esc(j.year_zhi_a || '') + '×' + esc(j.year_zhi_b || '') + '）：' +
    esc(relLabel) + '</span>';
  /* R230a-7（R13-P0-2）：同五行显示「比和」而非「非相生」 */
  html += '<span class="pill sm" style="background:' +
    ((j.day_wx_sheng || j.day_wx_same) ? 'var(--c-good-ink)' : 'var(--c-bazi-ink)') + ';"' +
    ' title="两人的日主五行关系">五行底子：' +
    esc(j.day_wx_sheng ? '相生' : (j.day_wx_same ? '比和' : '相克')) + '</span>';
  html += '<span class="pill sm" style="background:var(--c-hehun-ink);">桃花（' +
    esc(j.peach_a || '') + '/' + esc(j.peach_b || '') + '）：' +
    esc(j.peach_same ? '重叠' : '不同') + '</span>';
  // R204b（D-257b）：天干五合 + 十神互见 pill（yinyuan skill 融入）
  if (j.gan_he) {
    html += '<span class="pill sm" style="background:var(--c-good-ink);">日干五合：天生对味</span>';
  }
  // R3340b：日干相冲对偶 pill——与 backend notes/score 同口径
  if (j.gan_chong) {
    html += '<span class="pill sm" style="background:var(--c-bazi-ink);color:var(--surface);" title="日干相冲：传统上主处久了容易顶牛">日干相冲：容易顶牛</span>';
  }
  if (j.god_a_sees_b && j.god_b_sees_a) {
    /* R233g（R44-P1）：pill 里裸神煞名 → 随行白话（你眼里的TA/TA眼里的你）。
     * R2350b（R98-P2-8）：这张表与 voice.py:1324 的性格词表语义不同
     * （这里=对方盘里的角色，那里=性格气质），不合并但需同步维护。
     * R3199：提成模块级 _TEN_GOD_TAG——年运条/合盘互看共用同一份。 */
    html += '<span class="pill sm" style="background:var(--secondary);" ' +
      'title="十神互见：互相在对方盘里的角色">互看：你眼里TA是「' +
      esc(_TEN_GOD_TAG[j.god_a_sees_b] || j.god_a_sees_b) + '」· TA眼里你是「' +
      esc(_TEN_GOD_TAG[j.god_b_sees_a] || j.god_b_sees_a) + '」</span>';
  }
  html += '</div>';
  /* R2350b（R98-P1-6）：j.render 是干支摘要串（「甲：1990年 庚午 ·
   * 大运：逆　…」），直贴屏全是黑话——收进折叠。
   * R3212：pro 开关下线后两态同一渲染。 */
  if (j.render) {
    html += '<details class="paipan-fold"><summary>看看技术细节</summary>' +
      '<div class="calc-summary">' + esc(j.render) + '</div></details>';
  }
  if (j.dayun_hits && j.dayun_hits.length) {
    /* R216b 续5（UX 队列 U-004）：8 行干支大运表信息过载，收进默认
     * 折叠（事实零删减）。 */
    /* R228n：五列表 320px 下 min-content 超容器 11px→整页横滚；
     * 外包 .table-scroll 让表自己滚。 */
    /* R232b（R40-W9）：加「约几岁」列——「几岁」比「哪年」对目标
     * 用户更直觉（后端 start_age_a/_b 早算好了没露）。 */
    var _table = '<div class="table-scroll"><table class="works"><thead><tr><th>大运</th><th>甲干支</th><th>乙干支</th>' +
      '<th>关系</th><th>约起年</th><th>约几岁</th></tr></thead><tbody>';
    j.dayun_hits.forEach(function (d) {
      /* R2349s（R84-P2-18）：年龄 float 取整——「约几岁」不出 34.3。 */
      var _ra = function (v) { return v != null ? Math.round(parseFloat(v)) : '—'; };
      var _ages = (d.start_age_a != null || d.start_age_b != null)
        ? _ra(d.start_age_a) + '/' + _ra(d.start_age_b) : '';
      /* R2530：标当前步——与解读「←眼下」同口径（year_start 起 10 年）。 */
      var _now = (d.year_start != null && new Date().getFullYear() >= d.year_start &&
        new Date().getFullYear() < d.year_start + 10) ? ' ←眼下' : '';
      _table += '<tr><td>第 ' + esc(d.index) + ' 运' + _now + '</td><td>' + esc(d.pillar_a) +
        '</td><td>' + esc(d.pillar_b) + '</td><td>' + esc(d.relation) +
        '</td><td class="num">' + esc(d.year_start) + '</td>' +
        '<td class="num">' + esc(_ages) + '</td></tr>';
    });
    _table += '</tbody></table></div>';
    /* R3212：单版化——大运表恒走折叠（事实零删减）。 */
    html += '<details class="warm-basis"><summary>📅 十年一轮的合拍表（' +
      j.dayun_hits.length + ' 行，展开看）</summary>' + _table + '</details>';
  }
  if (j.notes && j.notes.length) {
    html += '<div class="interp-disclaimer">📝 ' + esc(j.notes.join('　')) + '</div>';
  }
  /* C-003：交叉引用——合婚结果页增加星座配对维度 */
  if (j.cross_ref && j.cross_ref.message) {
    html += '<div class="cross-ref"><span class="cross-ref-icon">💕</span>' + esc(j.cross_ref.message) + '</div>';
  }
  html += renderAiPolish(j);
  html += tailHook('hehun');
  html += '</div>';
  /* R2349t（R88-14）：受邀者测完——提示把结果发回给约她的人，
   * 邀请链一来一回才闭环。 */
  if (window.__hhInviteMode && window.__hhInviteBy) {
    /* R3332-低：纯文本「发回给 TA」裂变闭环断在最后一步——改可点
     * 按钮直调分享图（走 _rbHh 里 hhSendBack 的 on() 绑定）。 */
    html += '<button type="button" class="hit-cite hit-cite-btn" ' +
      'id="hhSendBack">测完啦，点我把这张合拍指数发回给 ' +
      esc(window.__hhInviteBy) + ' 看看 💌</button>';
  }
  return html;
}

/* R230z（R36-P1-1）：渲染体抽为顶层 builder——历史台账「复看」
 * 按 rec.type 回放同一渲染；do* 里只剩 paint 一行。 */
function buildTaohuaResult(j) {
  let html = '<div class="card"><h2>🌺 桃花运</h2>';
  html += _birthEcho('taohua');
  /* R218a-巡2（N-08）：装饰图——桃花卡顶部加 SVG/CSS 装饰 banner。 */
  html += renderDecoration('taohua');
  // R193b：分享海报入口（对齐排盘 shareBazi，T3.1 同款零依赖 Canvas）
  html += '<button class="ghost fav-btn" type="button" id="shareTaohua" ' +
    'title="生成分享图">📸 分享图</button>';
  /* R3373 正缘画像：日主五行定气质型→氛围底图+特征标签+相遇
   * 信号（全网调研验证的爆款机制——可晒的社交货币）。 */
  html += '<button class="ghost fav-btn" type="button" id="shareSoulmate" ' +
    'title="按你的盘推出 TA 的气质画像">💘 看看 TA 的气质画像</button>' +
    '<div id="smCard"></div>';
  /* R2349s（R84-P2-20）：口吻开关——pro 直出原枚举值。 */
  html += _festivalBand();
  /* R3212：原 pro 开关下的 strength=/hit_pillars= 英文枚举键值行删除——
   * 同一组数据在下方「想看桃花坐标」里已有中文映射版，重复且无信息增量。 */
  const bz = j.bazi || {};
  // R187b：人话视图置顶（specs/005 US4——先说人话，再看坐标）
  if (j.warm) {
    html += '<div class="warm-wrap"><div class="warm-l0">' +
      /* R3319-P2：「牌·正：」内部编码出屏——与海报同款转顺读。 */
      esc(String(j.warm.one_liner || '').replace(/·\s*([正逆])\s*：/, '（$1位）：')) +
        '</div><div class="warm-reply">';
    (j.warm.reply || []).forEach(function (ln) {
      html += '<p>' + esc(ln) + '</p>';
    });
    html += '</div>';
    if (j.warm.badge) html += '<div class="warm-badge">' + esc(j.warm.badge) + '</div>';
    html += '</div>';
  }
  /* R216b（UX 队列 U-003）：温柔模式下四柱标签 + 8 个裸键值块
   * （年支/咸池/红鸾/天喜/强弱…）是纯工具感排版，且 badge 声称
   * badge 曾声称「详细依据见专业模式」却把原始坐标铺在当前页、自相矛盾
   * （该套话已在 R218a-巡6 D-003-badge 从 voice.BADGE 移除）。
   * 改为：warm 下整块收进单个折叠「🔍 想看桃花坐标？」；
   * 强弱值经 STRENGTH_CN 映射（weak→偏弱 等英文不再直出）。
   * 叠字标签核查结论（R216b 实测 + vision 复核）：审查轨截图里的
   * 「巳巳」是 1990-05-15 男真实八字数据（月柱辛巳、时柱辛巳各自
   * 干支同支），非前端拼接 bug，不做去重——去重反而会篡改事实。
   * 专业模式分支原样保留全部数据。 */
  const STRENGTH_CN = { strong: '偏旺', mid: '平稳', weak: '偏弱' };
  function _strengthCn(v) { return STRENGTH_CN[v] || v || '—'; }
  /* R218a-巡4（N4-a）：柱名英文枚举裸抛修复——后端 hit_pillars 等返回
   * year/month/day/hour，src/guji/taohua.py 有 _PILLAR_CN 映射但前端
   * 没用，用户看到「命中柱: month」。前端补同一映射（含容错：未知值原样）。 */
  const PILLAR_CN = { year: '年柱', month: '月柱', day: '日柱', hour: '时柱' };
  function _pillarCn(list) {
    return (list || []).map(function (p) { return PILLAR_CN[p] || p; }).join('、') || '无';
  }
  if (j.warm) {
    html += '<details class="warm-basis warm-pro-fold"><summary>🔍 想看桃花坐标？（展开看专业数据）</summary>';
  }
  html += '<div class="pill-row">';
  ['year', 'month', 'day', 'hour'].forEach(function (k, i) {
    if (bz[k]) {
      /* R3233：时辰留空时第 4 柱是默认午时——pill 上诚实标
       * 「时辰未知」，不拿默认当用户的时辰看。 */
      var _pl = (k === 'hour' && val('th_hour') === '') ? '时辰未知' : bz[k];
      html += '<span class="pill" style="background:' + colorAt(i) + ';">' +
        esc(_pl) + '</span>';
    }
  });
  html += '</div>';
  html += '<div class="calc-grid">';
  [
    ['年支', j.year_zhi], ['咸池（桃花）', j.peach_zhi],
    ['命中柱', _pillarCn(j.hit_pillars)],
    ['红鸾', j.hongluan], ['红鸾落柱', _pillarCn(j.hongluan_pillar)],
    ['天喜', j.tianxi], ['天喜落柱', _pillarCn(j.tianxi_pillar)],
    ['强弱', _strengthCn(j.strength)]
  ].forEach(function (pair, i) {
    html += '<div class="calc-block" style="border-left:3px solid ' + colorAt(i) +
      ';"><h3>' + esc(pair[0]) + '</h3><p>' + esc(fmtScalar(pair[1])) + '</p></div>';
  });
  html += '</div>';
  if (j.render) {
    html += '<div class="calc-summary" style="border-left-color:var(--c-taohua);">' +
      esc(j.render) + '</div>';
  }
  if (j.warm) {
    html += '</details>';
  }
  if (j.dayun_hits && j.dayun_hits.length) {
    var _thTbl = '<div class="table-scroll"><table class="works"><thead><tr><th>运</th><th>干支</th><th>约起年</th>' +
      '<th>约几岁</th></tr></thead><tbody>';
    j.dayun_hits.forEach(function (d) {
      /* R2530：标当前步——与解读「←眼下」同口径。 */
      var _thNow = (d.year_start != null && new Date().getFullYear() >= d.year_start &&
        new Date().getFullYear() < d.year_start + 10) ? ' ←眼下' : '';
      _thTbl += '<tr><td>第 ' + esc(d.index) + ' 运' + _thNow + '</td><td>' + esc(d.pillar) +
        '</td><td class="num">' + esc(d.year_start) + '</td>' +
        /* R2349s（R84-P2-18）：start_age 是 float（34.3）——「约几岁」
         * 列原样塞小数，取整显示。 */
        '<td class="num">' + esc(d.start_age != null
          ? Math.round(parseFloat(d.start_age)) : '') +
        '</td></tr>';
    });
    _thTbl += '</tbody></table></div>';
    /* R2509（审-P1-2）：合婚大运表早就折进 warm-basis——桃花这张
     * 是默认路径上唯一裸奔的干支柱表，同纪律折叠。
     * R3212：单版化后恒走折叠。 */
    html += '<details class="warm-basis"><summary>📅 桃花节奏表（' +
      j.dayun_hits.length + ' 行，展开看）</summary>' + _thTbl + '</details>';
  }
  if (j.notes && j.notes.length) {
    html += '<div class="interp-disclaimer">📝 ' + esc(j.notes.join('　')) + '</div>';
  }
  /* R220b：交叉引用铺到桃花——星座桃花信号 × 八字强度叠加 */
  if (j.cross_ref && j.cross_ref.message) {
    html += '<div class="cross-ref"><span class="cross-ref-icon">🌸</span>' +
      esc(j.cross_ref.message) + '</div>';
  }
  html += renderAiPolish(j);
  /* R3340（审-P2）：桃花 warn 渲染——服务端已透但前端此前丢。 */
  if (j.warn && j.warn.length) {
    html += '<p class="warn">' + esc(j.warn.join('；')) + '</p>';
  }
  html += tailHook('taohua');
  html += '</div>';
  return html;
}

/* R230z（R36-P1-1）：渲染体抽为顶层 builder——历史台账「复看」
 * 按 rec.type 回放同一渲染；do* 里只剩 paint 一行。 */
function buildQimingResult(j) {
  let html = '<div class="card"><h2>🌸 起名推荐</h2>';
  html += _birthEcho('qiming');
  /* R218a-巡2（N-08）：装饰图——起名卡顶部加 SVG/CSS 装饰 banner。 */
  html += renderDecoration('qiming');
  // R193b：分享海报入口（对齐排盘 shareBazi，T3.1 同款零依赖 Canvas）
  html += '<button class="ghost fav-btn" type="button" id="shareQiming" ' +
    'title="生成分享图">📸 分享图</button>';
  /* R218a-04：换一批 + 风格切换 4 档（诗经草木 / 楚辞 / 清新灵动 / 综合） */
  /* R228d：这是单选过滤钮不是页签——role=tablist 滥用会让读屏报「页签
   * 列表」但子项不是 tab；改 group + 各 chip aria-pressed（对照
   * .mode-btn 的既有写法）。 */
  html += '<div class="qm-style-row" role="group" aria-label="起名风格">';
  Object.keys(_QM_STYLES).forEach(function (k) {
    var s = _QM_STYLES[k];
    var active = (k === _QM_STYLE) ? ' active' : '';
    html += '<button class="qm-style-chip' + active + '" type="button" ' +
      'aria-pressed="' + (k === _QM_STYLE) + '" ' +
      'data-style="' + esc(k) + '" title="' + esc(s.hint) + '">' +
      esc(s.label) + '</button>';
  });
  html += '</div>';
  /* R3244：风格 chip 自带换批——提示行点明「再点换新名字」，不再
   * 依赖已删除的「换一批」按钮。 */
  html += '<div class="qm-style-hint" id="qmStyleHint">' +
    esc((_QM_STYLES[_QM_STYLE] || {}).hint || '') +
    ' · <span class="qm-hint-em">再点一下换新名字</span></div>';
  const bz = j.bazi || {};
  const fe = j.five_elements || {};
  /* R3212：干支原串+候选池原表（字/五行/出处/释义 60 行）收进一个
   * 折叠块——pro 开关下线，数据零删减，想看的一展开就有。 */
  var _qc = _pArr(j.candidates);
  if (_qc.length) {
    html += '<details class="warm-basis warm-pro-fold"><summary>📐 候选池原表（' +
      Math.min(_qc.length, 60) + ' 字，展开看五行与出处）</summary>' +
      (bz.render ? '<p class="paipan-line">' + esc(_pillarsHonest(bz.render, val('qm_hour') !== '')) + '</p>' : '') +
      '<div class="table-scroll"><table class="works"><thead><tr><th>字</th><th>五行</th><th>出处</th><th>释义</th></tr></thead><tbody>';
    _qc.slice(0, 60).forEach(function (c) {
      html += '<tr><td>' + esc(_pStr(c.char)) + '</td><td>' + esc(_pStr(c.element)) +
        '</td><td>' + esc(_pStr(c.radical)) + '</td><td>' + esc(_pStr(c.meaning)) + '</td></tr>';
    });
    html += '</tbody></table></div></details>';
  }
  /* R230a-7（R13-P1-6）：俱全时写「偏弱」不写「缺」 */
  html += '<p class="nayin">五行分布：' + esc(fmtScalar(fe.counts)) +
    (fe.missing && fe.missing.length ? '　缺：' + esc(fe.missing.join('、')) :
     (fe.weak && fe.weak.length ? '　偏弱：' + esc(fe.weak.join('、')) : '')) +
    '</p>';
  if (j.summary) html += '<div class="calc-summary">' + esc(j.summary) + '</div>';
  /* R233j（R46-P1）：接上 copy_bank.qiming_one_liners——后端按
   * 姓氏+日柱确定性出一句暖 hook（同输入同输出）。 */
  if (j.one_liner) html += '<div class="qm-oneliner" style="font-size:13px;' +
    'color:var(--secondary);margin:2px 0 10px;">' + esc(j.one_liner) + '</div>';
  /* R233w（R53-P3-3）：warm 层——AI 挂了也有多行人话，不是裸名单。 */
  if (j.warm) {
    html += '<div class="warm-wrap"><div class="warm-reply">';
    (j.warm.reply || []).forEach(function (ln) {
      html += '<p>' + esc(ln) + '</p>';
    });
    html += '</div></div>';
  }
  // R187b：完整名推荐卡（specs/006 前置：用户痛点「没给出完整名字」）
  // R218a-04+05：按当前 _QM_STYLE 过滤 + 客户端打分排序（缺补+音韵+出处+双字）
  var _allNames = (j.full_names || []).slice();
  var _styleShift = ({'classics': 0, 'chuci': 2, 'fresh': 4, 'all': 0})[_QM_STYLE] || 0;
  var _styleNames = _allNames;
  /* R224b：下面这段风格错位切片是按 top_n=20 设计的（注释里的"取 8-16 /
   * 16-24"），本轮 top_n 降到 8 后偏移会绕回同一批，风格档之间不再有区分度。
   * 用 length > 12 作闸：池够大才做错位，池小（=8）时三档共用同一批名字，
   * 由 _qmScore 排序体现差异，避免"换风格看到同样的名字还乱序"。
   * 扩池到 40+/元素并把 top_n 调回 20 后，这里自动恢复错位行为。 */
  if (_QM_STYLE !== 'all' && _allNames.length > 12) {
    /* 错位切片让不同档的「头条」不同——诗经草木取前 8、楚辞取 8-16、清新灵动取 16-24；
     * 不足时回到 0 循环。零后端改动，纯前端视觉轮换。 */
    var _len = _allNames.length;
    _styleNames = [];
    for (var _k = 0; _k < 8 && _k < _len; _k++) {
      _styleNames.push(_allNames[(_styleShift + _k) % _len]);
    }
  }
  var _scored = _styleNames.map(function (n, idx) {
    n._rank = idx;
    /* R230a-7（R13-P1-6）：俱全时按 weak 打分（选字池用的就是 weak） */
    return { n: n, s: _qmScore(n,
      (fe.missing && fe.missing.length) ? fe.missing : (fe.weak || [])) };
  }).sort(function (a, b) { return b.s.total - a.s.total; });
  if (_scored && _scored.length) {
    html += '<h3 style="margin-top:16px;">💐 古籍典故取名 · ' +
      esc((_QM_STYLES[_QM_STYLE] || {}).label || '') +
      '<span style="font-size:12px;color:var(--secondary);font-weight:400;">　怎么挑的：补缺的五行 + 典籍出处 + 寓意 + 念着顺口</span></h3>' +
      '<div class="calc-grid">';
    _scored.forEach(function (entry, i) {
      var n = entry.n;
      var score = entry.s.total;
      var chips = entry.s.parts.map(function (p) {
        return '<span class="qm-part">' + esc(p.label) + ' +' + p.pts + '</span>';
      }).join('');
      var c = colorAt(i);
      /* R218a-05：⭐ 契合度 + TOP 1/2/3 徽章 */
      html += '<div class="calc-block" style="border-left:3px solid ' + c + ';">' +
        _qmBadgeHtml(score, i) +
        '<h3 style="color:' + c + ';font-family:var(--font-serif);font-size:24px;">' +
        esc(n.full_name || '') +
        /* R230z（R36-P2-3）：心水名单——♡ 收名字进 favorites，
         * 换一批后旧名字不丢。 */
        '<button type="button" class="qm-fav" data-fav-name="' +
        esc(n.full_name || '') + '" title="收进心水名单" ' +
        'aria-label="收藏 ' + esc(n.full_name || '') + '">♡</button></h3>' +
        '<p class="qm-el-line">' +
        (n.elements || []).map(function (e) {
          /* R3254g：五行字→彩色元素 chip（与命盘同套五色）。 */
          return '<span class="wx-chip wx-' + esc(e) + '">' + esc(e) + '</span>';
        }).join('') +
        (n.form === 'single' ? '　单字名' : '　双字名') + '</p>' +
        '<div class="qm-parts">' + chips + '</div>' +
        /* R2349s（R84-P2-14）：热字/生僻字提醒 chip——后端
         * name_note 只在命中时下发。 */
        (_pStr(n.name_note) ?
          '<p class="qm-name-note" style="font-size:12px;color:var(--muted);margin-top:4px;">💡 ' +
          esc(_pStr(n.name_note)) + '</p>' : '');
      if (n.story) {
        html += '<p style="font-size:13px;margin-top:4px;">📜 ' + esc(n.story) + '</p>';
      }
      /* R232a（R40-B2）：n.meanings 后端从不返回（死分支，永不可达）；
       * 换成真实字段 n.origin——名字的出处典籍，比释义更实用。 */
      if (n.origin) {
        html += '<p class="qm-origin">📖 出处：' + esc(n.origin) + '</p>';
      }
      html += '</div>';
    });
    html += '</div>';
    /* R3244（用户实测·砍功能）：「换一批」整个删除——用户两次
     * 实测反馈联动不可感（本地验证虽通，端上仍不达预期）。改为
     * 风格 chip 自带换批语义：点任意风格=该风格新一批，再点当前
     * 风格也出新名单（_qmSwitchStyle 内 _qmSeed++）。 */
  }
  /* R207b：AI 点评入口——引经据典推荐语（DISABLE 时按钮隐藏语义） */
  /* R216b 续5（U-019）：DISABLE/降级态（响应无 ai_task_id）按钮置灰+
   * 提示语，不再可反复点。 */
  var _aiOff = !j.ai_task_id;
  html += '<button class="chat-entry" type="button" id="nameReviewBtn"' +
    (_aiOff ? ' disabled title="小满点评这会儿休息，回头再来吧"' : '') + '>' +
    '✨ 让 AI 用古籍典故点评这些名字</button>' +
    '<div id="nameReviewOut" hidden></div>';
  /* candidates[] = {char, element, radical, meaning}。
   * R221b-fix：这段折叠区从 R217a 起一直是「0 字」空壳（后端写死 []），
   * 审查轨 vision 目视发现。后端已填真数据，radical 位放的是**典故出处**
   * （比部首对用户有用），所以标签同步改成「五行与出处」。 */
  html += '<details class="warm-basis" style="margin-top:14px;"><summary>单字候选池（' +
    ((j.candidates || []).length) + ' 字，展开看五行与出处）</summary><div class="calc-grid">';
  (j.candidates || []).forEach(function (n, i) {
    const c = colorAt(i);
    html += '<div class="calc-block" style="border-left:3px solid ' + c + ';">' +
      '<h3 style="color:' + c + ';font-family:var(--font-serif);font-size:22px;">' +
      esc(n.char || '') + '</h3>' +
      '<p class="qm-el-line">' +
      (n.element ? '<span class="wx-chip wx-' + esc(n.element) + '">' +
        esc(n.element) + '</span> ' : '') +
      '出处：' + esc(n.radical || '') + '</p>' +
      '<p style="font-size:13px;">' + esc(n.meaning || '') + '</p></div>';
  });
  html += '</div></details>';
  /* R220b：交叉引用铺到起名——太阳星座气质给挑名字一个参考角度 */
  if (j.cross_ref && j.cross_ref.message) {
    html += '<div class="cross-ref"><span class="cross-ref-icon">✨</span>' +
      esc(j.cross_ref.message) + '</div>';
  }
  html += renderAiPolish(j);
  /* R3340（审-P2）：起名 warn 渲染——服务端已透但前端此前丢。 */
  if (j.warn && j.warn.length) {
    html += '<p class="warn">' + esc(j.warn.join('；')) + '</p>';
  }
  html += tailHook('qiming');
  /* R229z续23（R11-#4）：起名卡此前全程无免责徽标 */
  html += '<div style="font-size:12px;color:var(--muted);margin-top:10px;">名字综合古籍意象与五行给的参考，仅供娱乐，孩子的名字还是家里人说了算 ✨</div>';
  html += '</div></div>';
  return html;
}

async function api(path, options) {
  options = options || {};
  /* R228k：fetch 无超时——请求挂起时 busy() 占位与 on() 在途锁永不复位，
   * 只能刷新页面。AbortSignal.timeout 存在就用，否则手工 controller。 */
  var _ctl = null, _t = null, _raceT = null;
  if (options.signal) {
    /* R230v（R34-#14）：调用方自带 signal 不再整体跳过 20s 超时——
     * AbortSignal.any 合并两者（旧内核不支持时调用方信号优先）。 */
    if (typeof AbortSignal !== 'undefined' && AbortSignal.any && AbortSignal.timeout) {
      options.signal = AbortSignal.any([options.signal,
                                        AbortSignal.timeout(API_TIMEOUT_MS)]);
    }
  } else if (typeof AbortSignal !== 'undefined' && AbortSignal.timeout) {
    options.signal = AbortSignal.timeout(API_TIMEOUT_MS);
  } else if (typeof AbortController !== 'undefined') {
    _ctl = new AbortController();
    _t = setTimeout(function () { _ctl.abort(); }, API_TIMEOUT_MS);
    options.signal = _ctl.signal;
  }
  var resp;
  try {
    /* R230v（R34-#15）：连 AbortController 都没有的极老内核此前零超时
     * ——fetch 悬挂即永转圈。Promise.race 计时器兜底。 */
    resp = await ((options.signal || typeof Promise === 'undefined')
      ? fetch(path, options)
      : Promise.race([fetch(path, options), new Promise(function (_, rej) {
          _raceT = setTimeout(function () {
            var te = new Error('网络有点慢，稍后再试试');
            te.name = 'TimeoutError';
            rej(te);
          }, API_TIMEOUT_MS);
        })]));
  } catch (e) {
    if (_t) clearTimeout(_t);
    if (e && (e.name === 'AbortError' || e.name === 'TimeoutError')) {
      var te = new Error('网络有点慢，稍后再试试');
      if (!options.silent) showToast(te.message, 'warn');
      throw te;
    }
    if (!options.silent) showToast('网络似乎断开了，检查后再试试', 'warn');
    /* R229c：裸抛 TypeError('Failed to fetch') 会让结果区内联错误粘英文尾
       ——toast 是人话，内联也该同口径（R5 审计 P2）。 */
    var fe = new Error('网络似乎断开了，检查后再试试');
    fe.cause = e;
    throw fe;
  } finally { if (_t) clearTimeout(_t); if (_raceT) clearTimeout(_raceT); }
  let body = null;
  try {
    body = await resp.json();
  } catch (e) {
    body = null;
  }
  if (!resp.ok) {
    var detail = body && body.detail ? body.detail : resp.status + ' ' + resp.statusText;
    /* R229z续16：非 JSON 错误体（代理/网关直吐 HTML）时 detail 只剩
     * 「500 Internal Server Error」这类英文 statusText——翻成人话，
     * 内联 fail() 与 toast 同口径。 */
    if (typeof detail === 'string' && /^[45]\d{2} /.test(detail)) {
      /* R233g（R44-P2-11）：状态码对目标用户是噪音——去码留人话。 */
      detail = resp.status >= 500 ? '服务打个盹了，稍后再戳我～'
        : (resp.status === 404 ? '要找的内容不在了' : '小满这次没接住，稍后再试试');
    }
    /* R229z续23（R11-#2）：detail 为对象时 JSON.stringify 会把
     * {"msg":"field required"} 原文吐进 toast——先取中文可读的子键，
     * 都没有就走人话兜底。
     * R230f续2（R16-P2-4）：typeof []==='object'——pydantic 422 的 detail
     * 数组在这里先被换成裸「请求没走通（422）」，_humanize422 根本拿
     * 不到（实测填空年份/超长问题只出裸码）。数组要留给人话化。 */
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      detail = detail.msg || detail.error || detail.message
        || (resp.status === 404 ? '要找的内容不在了'
            : '刚才那下没成功，再试一次？');
    }
    /* R2343（R58-P1-1）：字符串 detail 里一个中文字都没有 = 英文实现
     * 细节（FastAPI 默认错误/上游异常原文）——先过 _humanizeErr，仍无
     * 中文则整句换掉，不给用户看堆栈味文案。 */
    if (typeof detail === 'string' && !/[一-龥]/.test(detail)) {
      detail = _humanizeErr(detail);
      if (!/[一-龥]/.test(detail)) {
        detail = resp.status >= 500 ? '服务打个盹了，稍后再戳我～'
          : (resp.status === 404 ? '要找的内容不在了'
             : '小满这次没接住，稍后再试试');
      }
    }
    /* R2345（R61-P1-4）：schema 味的中文 detail（「facts 单条需为
     * ≤500 字字符串」）也是实现细节——暴露字段名/类型词才换。 */
    if (typeof detail === 'string' &&
        /(?:需为|字符串|字段|类型|array|object|bool|float|int\b)/.test(detail)) {
      detail = '这条消息有点怪：换个说法再发我';
    }
    const err = new Error(Array.isArray(detail) ? _humanize422(detail)
      : (typeof detail === 'string' ? detail
          : (resp.status === 404 ? '要找的内容不在了'
             : '刚才那下没成功，再试一次？')));
    /* R218a-巡2（N-05）：错误态用户反馈——非 2xx 一律弹红色 toast（不只
     * 在主流程 catch 里弹；网络层就弹，给用户即时反馈）。4xx 是用户输入
     * 错（黄底提示），5xx 是服务端异常（红底提示）。 */
    var status = resp.status;
    var isClient = status >= 400 && status < 500;
    err.status = status;   /* R8 P2-9：让轮询方对 404 早退（任务不存在） */
    /* R3341（审-低）：闸 cookie 过期 → API 全 401——裸「需要钥匙
     * 才能进来哦」用户不知道下一步。点名刷新重新进门。 */
    if (status === 401) {
      err.message = '门好像又关上了——刷新页面重新输口令进门';
    }
    if (!options.silent) {
      showToast(typeof err.message === 'string' ? err.message
                : '刚才那下没成功，再试一次？',
                isClient ? 'warn' : 'error');
    }
    throw err;
  }
  return body;
}

/* R218a-巡2（N-05）：全局 toast——错误/警告/成功共用。3.5s 自动消失，
 * 多次调用堆叠，z-index 最高（遮在 modal 之上）。additive，不动既有
 * 任何 DOM 结构。 */
function showToast(msg, kind) {
  msg = _humanizeErr(msg);   /* R229z续17+：phFetch 等裸 fetch 的英文错误尾 */
  var stack = document.getElementById('toastStack');
  if (!stack) {
    stack = document.createElement('div');
    stack.id = 'toastStack';
    stack.className = 'toast-stack';
    document.body.appendChild(stack);
  }
  /* R230q（R28-P2-5）：同文案洪泛去重——离线连点原来叠一屏相同 toast。
   * 同文案在屏则折叠「×N」；栈上限 3 条，溢出摘最旧。 */
  var _msgStr = String(msg || '');
  var _items = stack.querySelectorAll('.toast-item');
  for (var _i = 0; _i < _items.length; _i++) {
    var _mEl = _items[_i].querySelector('.toast-msg');
    if (_mEl && _mEl.dataset.base === _msgStr) {
      var _n = parseInt(_mEl.dataset.n || '1', 10) + 1;
      _mEl.dataset.n = String(_n);
      _mEl.textContent = _msgStr + '（×' + _n + '）';
      return;
    }
  }
  while (_items.length >= 3) { _items[0].remove(); _items = stack.querySelectorAll('.toast-item'); }
  var t = document.createElement('div');
  t.className = 'toast-item toast-' + (kind || 'info');
  /* R228d：toast 是全站唯一的错误通道——不补 live region，API 错误对读屏
   * 完全静默。error 走 alert（打断式），其余 status+polite。 */
  if (kind === 'error') { t.setAttribute('role', 'alert'); }
  else { t.setAttribute('role', 'status'); t.setAttribute('aria-live', 'polite'); }
  var icon = kind === 'error' ? '⛔' : (kind === 'warn' ? '⚠️' : '✅');
  t.innerHTML = '<span class="toast-icon">' + icon + '</span>' +
    '<span class="toast-msg">' + esc(_msgStr) + '</span>' +
    /* R233k（R45-§1）：error toast 8s 干等不可控——补关闭钮；
     * pointer-events 在 CSS 侧 re-enable。 */
    '<button type="button" class="toast-x" aria-label="关闭提示">×</button>';
  t.querySelector('.toast-x').addEventListener('click', function () {
    /* R2349h（R69-P2-7）：焦点若落在 × 上，销毁前归还到功能区，
     * 否则丢回 body 从头爬。 */
    if (document.activeElement === this) {
      var _nx = el('funcGrid');
      if (_nx && _nx.focus) { try { _nx.focus(); } catch (e) {} }
    }
    t.classList.remove('show');
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 250);
  });
  t.querySelector('.toast-msg').dataset.base = _msgStr;
  stack.appendChild(t);
  /* 入场动画 */
  requestAnimationFrame(function () { t.classList.add('show'); });
  /* R230n（R25-6.1）：error toast 3.5s 消失对读屏用户太短（WCAG 可驻留
   * 建议）——错误类延长到 8s 且 hover/focus 暂停计时；其余仍 3.5s。 */
  var _tmo = (kind === 'error') ? 8000 : 3500;
  var _tmr = setTimeout(function () {
    t.classList.remove('show');
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 250);
  }, _tmo);
  /* R2349o（R78-P2-3）：悬停/聚焦暂停计时从 error 扩到全部 toast——
   * info 3.5s 自动消失，键盘用户 Tab 到 × 之前提示就没了。 */
  t.addEventListener('mouseenter', function () { clearTimeout(_tmr); });
  t.addEventListener('mouseleave', function () {
    _tmr = setTimeout(function () {
      t.classList.remove('show');
      setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 250);
    }, 3000);
  });
  t.addEventListener('focusin', function () { clearTimeout(_tmr); });
}

/* R3263（R22）：小满说给你听——用 Web Speech Synthesis 朗读
 * warm reply/判词。无网络、无服务器成本，睡前/眼睛累场景适用。 */
var _SPEECH_CANCEL = null;
function _speak(text) {
  try {
    if (!window.speechSynthesis) { showToast('当前设备不支持朗读', 'warn'); return; }
    window.speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(text);
    u.lang = 'zh-CN';
    var voices = window.speechSynthesis.getVoices();
    var _v = voices.find(function (v) {
      return v.lang && (v.lang.indexOf('zh') === 0 || v.lang.indexOf('cmn') === 0);
    });
    if (!_v) _v = voices.find(function (v) { return v.lang && v.lang.indexOf('zh') !== -1; });
    if (_v) u.voice = _v;
    u.rate = 1; u.pitch = 1; u.volume = 1;
    u.onend = function () { _SPEECH_CANCEL = null; };
    u.onerror = function () { _SPEECH_CANCEL = null; };
    _SPEECH_CANCEL = u;
    window.speechSynthesis.speak(u);
  } catch (eS) { showToast('朗读没开成，稍后再试', 'warn'); }
}
function _stopSpeak() {
  try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (e) {}
  _SPEECH_CANCEL = null;
}

/* R3263（R23）：水逆急救包——「慢三秒」呼吸按钮 */
function _mercBreathe() {
  var btn = el('mercBreathe');
  if (!btn || btn.disabled) return;
  btn.disabled = true;
  var _steps = [
    { t: '吸气 4 秒', ms: 0 },
    { t: '屏息 4 秒', ms: 4000 },
    { t: '呼气 6 秒', ms: 8000 },
    { t: '慢三秒', ms: 14000 }
  ];
  _steps.forEach(function (s) {
    setTimeout(function () {
      btn.textContent = s.t;
      if (s.ms === 14000) btn.disabled = false;
    }, s.ms);
  });
}

function postJSON(path, payload, opts) {
  /* R2400（R123-P2-3）：opts 透传给 api——聊天发送走 silent，
   * 4xx 由 catch 气泡单一承载，不再 toast+气泡双重提示。 */
  return api(path, Object.assign({
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  }, opts || {}));
}

/* ── AI 段落后到（R191b，B-014 / specs/006 判据 9/10、D-251b）──────
 * 后端不再同步等 LLM（实测开启 LLM 时端点阻塞 35s）。响应带 ai_task_id
 * 时前端渲染完确定性主体就轮询 /api/ai/{id}；拿到文本就地追加 .ai-polish
 * 容器。failed / 404 / 超时 → 整块不渲染——降级语义与 D-244a 完全一致，
 * LLM 永远不是承重墙。RESULT_GEN 是「结果区世代号」：同一容器发起新请求
 * 会令旧轮询自动作废，防止慢任务回来后污染新一轮结果。 */
var RESULT_GEN = {};
var AI_POLL_INTERVAL_MS = 500;
var AI_POLL_CAP_S = 62;            // 与后端 _POLL_BUDGET_S(50s)+余量对齐
var NR_POLL_CAP_S = 88;            // 点评链 78s 预算+余量（底卡先行可等）
                                   // R3243：推理模型拥挤期生成 15-30s/次，
                                   // 40s 帽会在兜底即将成功时提前放弃

/* R230q（R28-P3-8）：后台标签页/断网下轮询空转——每 500ms 白打一个
 * 注定失败的请求（恢复瞬间还会连发）。门控：hidden/offline 时不取数。 */
function _aiPollGate() {
  return (typeof document !== 'undefined' && document.hidden === true) ||
    (typeof navigator !== 'undefined' && navigator.onLine === false);
}

/* R230q（R28-P2-2）：切视图 bump RESULT_GEN 会作废在跑的 AI 轮询——
 * 回来后那段「小满想了想」永远不来。pending 登记在案，进视图时恢复。 */
var AI_PENDING = {};   /* containerId → taskId */

/* R230t（R32-P2-20）：轮询退避——500ms 起逐次 ×1.6 至 2.5s 封顶。
 * 此前恒 500ms：单任务 40s 最多 80 次 GET，移动端的电量/流量开销可观。 */
function _aiBackoff(w) { return Math.min(Math.round(w * 1.6), 2500); }

/* R230t（R31-P2-6）：服务端重启/会话 TTL 断档后小满失忆但气泡还在——
 * boot 记号变了就在新回复前插一条轻分隔（不落 transcript）。 */
function _chatBootNote(st, ty) {
  if (!st || !st.boot || !ty) return;
  try {
    var s = _chatStore() || _MEM_STORE;
    var prev = s.getItem('chatBootId');
    if (prev && prev !== st.boot && ty.parentNode) {
      var d = document.createElement('div');
      d.className = 'chat-bubble chat-ai chat-divider';
      d.style.opacity = '.72';
      d.style.fontSize = '.9em';
      /* R3208：如实说明 + 给两条出路——屏幕上的记录还在（下一句
       * 会照尾巴捡回大概），或者干脆开新话题翻篇。 */
      d.textContent = '（小满刚重启过脑子，细节可能记不全。' +
        '你屏幕上的记录还在，下一句会照着捡回大概）';
      _CHAT_NEED_RECAP = true;
      d.appendChild(_chatResetBtn('🌱 记不全？开个新话题'));
      ty.parentNode.insertBefore(d, ty);
    }
    s.setItem('chatBootId', st.boot);
  } catch (e) {}
}

/* R233r（R49-P2-3）：会话被 TTL 回收重启——同进程 boot 没变但
 * 上下文已丢。fresh 标记且本屏已有历史气泡时插轻分隔。 */
function _chatFreshNote(st, ty) {
  if (!st || !st.fresh || !ty || !ty.parentNode) return;
  var n = 0, p = ty.previousSibling;
  while (p) { if (p.classList && p.classList.contains('chat-bubble')) n++; p = p.previousSibling; }
  if (n < 2) return;   /* 首条自动发/无历史不分隔 */
  /* R3208：boot 分隔刚插过（同一次失忆两条注脚叠着太吵）——跳过。 */
  var _pv = ty.previousSibling;
  if (_pv && _pv.classList && _pv.classList.contains('chat-divider')) return;
  var d = document.createElement('div');
  d.className = 'chat-bubble chat-ai chat-divider';
  d.style.opacity = '.72';
  d.style.fontSize = '.9em';
  /* R3208：如实说明 + 回收语境——下一条消息会把 transcript
   * 尾巴当「前文回放」喂回去，大概能接上；也可一键翻篇。 */
  d.textContent = '（隔得有点久，细节小满可能记不全。' +
    '你屏幕上的记录还在，下一句会照着捡回大概）';
  _CHAT_NEED_RECAP = true;
  d.appendChild(_chatResetBtn('🌱 记不全？开个新话题'));
  ty.parentNode.insertBefore(d, ty);
}

/* R3208：断档回放旗标——fresh/boot 失忆被检测后置位，
 * 下一条消息经 _chatFacts 注入 transcript 尾巴，一次性消费。 */
var _CHAT_NEED_RECAP = false;
function _chatRecapFact() {
  var ts = _chatTsRead();
  if (ts.length < 2) return '';   /* 只剩刚发的这条就没得回 */
  var tail = ts.slice(-5, -1);    /* 倒序 4 条，排除刚发出去的当前句 */
  var bits = [];
  for (var i = 0; i < tail.length; i++) {
    var t = String(tail[i].t || '').replace(/\s+/g, ' ').slice(0, 40);
    if (t) bits.push((tail[i].r === 'me' ? '她' : '你') + ':「' + t + '」');
  }
  if (!bits.length) return '';
  return '（断档续聊）你们刚才聊到这儿。' + bits.join(' ') +
         '。顺着接着聊，别当第一次见。';
}

/** 把 AI 块插进已渲染的结果区末尾；容器不存在/已插过返回 false。 */
function insertAiPolish(containerId, text) {
  var node = el(containerId);
  if (!node || !text) return false;
  if (node.querySelector('.ai-polish')) return false;
  var wrap = document.createElement('div');
  wrap.innerHTML = renderAiPolish({ ai_polish: text });
  var block = wrap.firstElementChild;
  if (!block) return false;
  /* R233k（R45-§2）：AI 润色到达是产品亮点，原静默 append 阅读中途
   * 凭空多一块——入场动画 + 轻 toast 提示。 */
  block.classList.add('ai-arrive');
  node.appendChild(block);
  /* R3241（用户实测）：AI 正文逐字蹦——打字中只出纯文本，
   * 打完换回富文本终态（防 markdown 半截标签）。 */
  var _pt = block.querySelector('.ai-polish-text');
  if (_pt) {
    var _plain = String(text || '');
    _pt.textContent = '';
    typewriteInto(_pt, _plain, function () {
      _pt.innerHTML = renderRichText(_plain);
    });
  }
  showToast('小满又补了一句 ✦', 'info');
  return true;
}

/* R3241（用户实测「一次性给全像卡住」）：AI 文本逐字 reveal——
 * HTTP 是一次性回包，打字机是放映层：逐字上屏 + 闪烁光标，
 * 用户在等待也有盼头。打完才上富文本终态（防 ** 标记裸奔）。
 * prefers-reduced-motion 与超短文本直接终态。
 * 返回 cancel——新写回（重试/新一轮）先调它止旧打字。 */
function typewriteInto(node, text, onDone) {
  if (!node) return function () {};
  var full = String(text || '');
  var rm = false;
  try {
    rm = !!(window.matchMedia &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  } catch (e) {}
  var finish = function () {
    node.classList.remove('tw-typing');
    node.removeAttribute('aria-busy');   /* R3242c：终态放行朗读 */
    if (onDone) onDone();
  };
  if (rm || full.length < 8) { finish(); return function () {}; }
  if (node._twCancel) { try { node._twCancel(); } catch (eC) {} }
  var i = 0, stopped = false;
  node.classList.add('tw-typing');
  /* R3242c：chatFlow 是 aria-live=log 区——逐字 textContent 更新
   * 会让读屏逐字轰炸。打字期挂 aria-busy，终态一次性朗读。 */
  node.setAttribute('aria-busy', 'true');
  /* 长文封顶 ~5s：30ms/字起步，超长自适应加速（中文 200 字约 4s）。 */
  var step = Math.max(10, Math.min(30, Math.round(5000 / full.length)));
  var flow = el('chatFlow');
  var tick = function () {
    if (stopped) return;
    i++;
    node.textContent = full.slice(0, i);
    if (flow && node.closest('#chatFlow')) {
      flow.scrollTop = flow.scrollHeight;   /* 边打边跟滚 */
    }
    if (i < full.length) { setTimeout(tick, step); return; }
    finish();
  };
  var cancel = function () {
    stopped = true;
    node.classList.remove('tw-typing');
    node.removeAttribute('aria-busy');
  };
  node._twCancel = cancel;
  setTimeout(tick, step);
  return cancel;
}

/** 轮询 AI 任务直到终态/超时；任何错误静默停止（D-244a：失败不可见）。 */
function pollAiPolish(containerId, taskId) {
  if (!taskId) return;
  AI_PENDING[containerId] = taskId;   /* R230q：切走再回来可恢复 */
  RESULT_GEN[containerId] = (RESULT_GEN[containerId] || 0) + 1;
  var gen = RESULT_GEN[containerId];
  var deadline = performance.now() + AI_POLL_CAP_S * 1000;   /* R230t（R31-P2-9）：轮询预算用单调钟——系统时钟回拨不再冻死轮询 */
  var _wait = AI_POLL_INTERVAL_MS;    /* R230t（R32-P2-20）：退避轮询 */
  var _done = function () { delete AI_PENDING[containerId]; };
  var tick = function () {
    if (RESULT_GEN[containerId] !== gen) {
      /* R230v（R34-#20）：新一轮已接管时 AI_PENDING 里的 taskId 是新的，
       * 不能删；只在容器真的不在 DOM 了（视图重绘摘除）才回收残留。 */
      if (!el(containerId) || !document.contains(el(containerId))) {
        delete AI_PENDING[containerId];
      }
      return;   // 已被新一轮结果覆盖
    }
    /* R230q（R28-P3-8）：后台/断网暂停取数 */
    if (_aiPollGate()) {
      if (performance.now() < deadline) setTimeout(tick, 2000);
      else _done();
      return;
    }
    api('/api/ai/' + encodeURIComponent(taskId), { silent: true }).then(function (st) {
      if (RESULT_GEN[containerId] !== gen) return;
      if (st && st.status === 'done' && st.text) {
        if (insertAiPolish(containerId, st.text)) {
        }
        _done();
        return;                                      // 终态：停止轮询
      }
      if (st && st.status === 'failed') {
        /* R2365（R3302-中）：上游 failed 整块消失=「发了没回音」——
         * 留一行真话，不装死也不打扰（卡面主体不受影响）。 */
        try {
          var _pfc = document.getElementById(containerId);
          if (_pfc && !_pfc.querySelector('.ai-polish-fail')) {
            var _pfn = document.createElement('div');
            _pfn.className = 'ai-polish-fail';
            _pfn.style.cssText =
              'font-size:12px;color:var(--muted);margin-top:6px;';
            _pfn.textContent = '小满这句没接上，不耽误看结果～';
            _pfc.appendChild(_pfn);
          }
        } catch (ePF) {}
        _done(); return;
      }
      if (performance.now() < deadline) { setTimeout(tick, _wait); _wait = _aiBackoff(_wait); }
      else _done();
    }).catch(function (e) {
      /* R230v（R34-#10）：与聊天轮询同口径——404/过期才永弃，
       * 瞬时网络抖动续排到 deadline（此前一次抖动就永久缺席 AI 块）。 */
      if (e && e.status === 404) { _done(); return; }
      if (performance.now() < deadline) { setTimeout(tick, _wait); _wait = _aiBackoff(_wait); }
      else _done();
    });
  };
  setTimeout(tick, AI_POLL_INTERVAL_MS);
}

/* ── R206b（specs/009 US1）：AI 陪伴层「问问小满」──────────────
 * 排盘结果尾部入口 → 聊天抽屉。复用 pollAiPolish 的轮询语义
 * （/api/ai/{tid}），会话 id 存 sessionStorage。
 * R230n（R25-2.2）：原在 localStorage 全 tab 共享——B 重置会话后 A 下条
 * 消息静默并入新 sid（上下文污染）；sessionStorage 每 tab 独立，重启
 * 浏览器回到全新会话（原来也是一次性语义，无回归）。
 * DISABLE=1 时 /api/chat 返回无 chat_task_id 键 → 入口隐藏（D-244a）。 */
var CHAT_SID_KEY = 'chatSessionId';
/* R230t（R31-P2-15）：sessionStorage 被禁的窗口此前回落 localStorage——
 * 共享介质会让 B 重置会话污染 A。回落改为页内存 Map（丢跨刷新存活，
 * 但不串 tab）。 */
var _MEM_STORE = {
  _m: {},
  getItem: function (k) { return Object.prototype.hasOwnProperty.call(this._m, k) ? this._m[k] : null; },
  setItem: function (k, v) { this._m[k] = String(v); },
  removeItem: function (k) { delete this._m[k]; }
};
function _chatStore() {
  try { return window.sessionStorage; } catch (e) { return null; }
}
function chatSid() {
  try {
    var _st = _chatStore() || _MEM_STORE;
    var sid = _st.getItem(CHAT_SID_KEY);
    if (!sid) {
      /* R230a-44（R15-P3）：Math.random sid ~31 位熵可猜——猜到即可往别人
       * 会话注入上下文。crypto.getRandomValues 给到 ~63 位。 */
      var rnd = '';
      try {
        var buf = new Uint32Array(2);
        crypto.getRandomValues(buf);
        rnd = buf[0].toString(36) + buf[1].toString(36);
      } catch (e2) { rnd = Math.random().toString(36).slice(2, 12); }
      sid = 'c' + Date.now().toString(36) + rnd;
      _st.setItem(CHAT_SID_KEY, sid);
    }
    return sid;
  } catch (e) {
    /* R2523：原回退 'c-anon' 是共享字面量——sessionStorage 不可用的
     * 用户在公开部署下同 sid 共享服务端锚（日期/场景上下文互串）。
     * 记忆化随机回退：同页一致、跨页/跨用户不撞。 */
    if (!_SID_MEMO) {
      _SID_MEMO = 'c-anon-' + Math.random().toString(36).slice(2, 12);
    }
    return _SID_MEMO;
  }
}
var _SID_MEMO = null;
var CHAT_LAST_FACTS = [];   /* 最近一次排盘的坐标事实（干支五行词，非 PII） */
var _CHAT_SEND_COUNT = 0;   /* D-006：追踪聊天发送次数，第一条自动发后允许追问 1 次 */

/* R230q（R28-P2-4）：sid 在 sessionStorage 里跨刷新存活，但气泡清空后
 * 新消息会悄悄接进用户看不见的上一轮上下文。把气泡 transcript 与 sid
 * 同介质存储，刷新后原样重渲（上限 50 条与 chatBubble 裁剪一致）。 */
var CHAT_TS_KEY = 'chatTranscript';
var CHAT_TS_LASTSID_KEY = 'chatTranscript:lastsid';
function _chatTsStore() {
  /* R3118（specs/011 P3）：transcript 升 localStorage——原来跟
   * sessionStorage 走，关页即失忆；跨天再开，小满看着像从没
   * 见过她。sid/chatClosed 仍走 sessionStorage（新天新会话），
   * 只有对话内容跨会话续存。 */
  try { return window.localStorage; } catch (e) { return null; }
}
/* R3339（审-中）：transcript 单键两 tab 共享+RMW 丢泡——两会话气泡
 * 交织进同一 transcript。键带 sid 命名空间（sid 走 sessionStorage
 * per-tab）；'chatTranscript:lastsid' 记最新 sid，新会话开场
 * 仍能续上上一会话的语境。 */
function _chatSid() {
  try {
    return (_chatStore() || _MEM_STORE).getItem(CHAT_SID_KEY) || '';
  } catch (e) { return ''; }
}
function _chatTsKey(sid) {
  return sid ? CHAT_TS_KEY + ':' + sid : CHAT_TS_KEY;
}
function _chatTsRead(sidOpt) {
  try {
    var st = (_chatTsStore() || _MEM_STORE);
    /* 优先读当前 sid 的桶；当前桶空且未显式指定 sid 时，回读上一
     * 会话桶（跨天续聊语境）；再回裸键（旧版单键的存量）。 */
    var keys = [];
    if (sidOpt != null) keys.push(_chatTsKey(sidOpt));
    else {
      var _cs = _chatSid();
      if (_cs) keys.push(_chatTsKey(_cs));
      var _ls = st.getItem(CHAT_TS_LASTSID_KEY) || '';
      if (_ls && _ls !== _cs) keys.push(_chatTsKey(_ls));
      keys.push(CHAT_TS_KEY);
    }
    for (var _ki = 0; _ki < keys.length; _ki++) {
      var s = st.getItem(keys[_ki]);
      if (!s) continue;
      var arr = JSON.parse(s);
      if (Array.isArray(arr) && arr.length) return arr;
    }
    return [];
  } catch (e) { return []; }
}
function _chatTsSave(role, text, action) {
  try {
    var st = (_chatTsStore() || _MEM_STORE);
    /* get-or-create：首条消息就要落本 sid 桶，不能等开场才建。 */
    var sid = chatSid();
    /* 读本 sid 桶续写——不回读旧会话桶，避免把上一会话的气泡
     * 复制进新桶（语义是新会话只接开场注入，不接气泡）。 */
    var s0 = st.getItem(_chatTsKey(sid));
    var arr = s0 ? JSON.parse(s0) : [];
    if (!Array.isArray(arr)) arr = [];
    var _m = { r: role === 'me' ? 'me' : 'ai',
               t: String(text || '').slice(0, 2000) };
    /* R3201：路标 chip 随 transcript 回放——刷新后「去抽牌」入口
     * 不该凭空消失（指向的是稳定真入口，无副作用）。 */
    if (action && typeof action.view === 'string' &&
        typeof action.label === 'string' && action.view && action.label)
      _m.a = { view: action.view.slice(0, 24),
               label: action.label.slice(0, 40) };
      /* R3352：anchor 随 chip 存——回放时锚点落位不丢。 */
      if (typeof action.anchor === 'string' && action.anchor)
        _m.a.anchor = action.anchor.slice(0, 16);
    arr.push(_m);
    if (arr.length > 50) arr = arr.slice(-50);
    st.setItem(_chatTsKey(sid), JSON.stringify(arr));
    /* lastsid 指针 + 旧桶 GC：只保留当前桶与上一会话桶，
     * 会话堆积不留无界 transcript:<sid> 残骸。 */
    if (sid) {
      var _prev = st.getItem(CHAT_TS_LASTSID_KEY) || '';
      st.setItem(CHAT_TS_LASTSID_KEY, sid);
      for (var _gi = st.length - 1; _gi >= 0; _gi--) {
        var _gk = st.key(_gi);
        if (_gk && _gk.indexOf(CHAT_TS_KEY + ':') === 0 &&
            _gk !== CHAT_TS_LASTSID_KEY &&
            _gk !== _chatTsKey(sid) &&
            (!_prev || _gk !== _chatTsKey(_prev))) {
          try { st.removeItem(_gk); } catch (eG) {}
        }
      }
    }
  } catch (e) {}
}
function _chatTsClear() {
  try { (_chatTsStore() || _MEM_STORE).removeItem(_chatTsKey(_chatSid())); }
  catch (e) {}
}
function _chatTsRestore() {
  /* 刷新后把存下的气泡重渲回来；nosave 防止重渲又双写 transcript。
   * noscroll：逐泡滚会每条强排一次同步回流（审-P2-1），滚一次即可。 */
  var _last = null;
  _chatTsRead().forEach(function (m) {
    var _bb = chatBubble(m.r === 'me' ? 'me' : 'ai', m.t,
                         { nosave: true, noscroll: true });
    /* R3201：存了 action 的 ai 泡重挂路标 chip；view 走白名单
     * （localStorage 可被改——脏值顶多挂个死钮，白名单再收一层）。 */
    if (_bb && m.a && typeof m.a === 'object' &&
        _CHAT_ACT_VIEWS[m.a.view] && typeof m.a.label === 'string')
      _chatActChip(_bb, m.a);
    _last = _bb || _last;
  });
  var _flow = el('chatFlow');
  if (_flow && _last) _flow.scrollTop = _flow.scrollHeight;
  /* R3118（specs/011 P3）：跨天续聊钩子——恢复出的 transcript
   * 里最后一条「她说的」存进一次性 resume 槽；下个新会话首次
   * 发送时 _chatFacts 把它注成「上次你们聊到」事实，小满手里
   * 有续聊的语境（服务端会话是新开的，不注入就是真失忆）。 */
  try {
    var _ts = _chatTsRead();
    for (var _ri = _ts.length - 1; _ri >= 0; _ri--) {
      if (_ts[_ri].r === 'me') { CHAT_RESUME_FACT = _ts[_ri].t || ''; break; }
    }
  } catch (e) {}
  /* R2400（R123-P2-4）：收尾态的「开新话题」钮挂回最后一条泡。 */
  try {
    if ((_chatStore() || _MEM_STORE).getItem('chatClosed') === '1' && _last) {
      _chatClosedHint(_last);
    }
  } catch (e) {}
}

/* R219b（P0-2）：各视图最近一次 API 响应缓存——「聊聊这件事」要把真实牌面/
 * 盘面/结果拼进第一句话，AI 才有东西可解。键 = 视图短名（bazi/taohua/
 * tarot/liuyao/hehun/huangli/qiming/xingzuo），值 = {json, question}。
 * 只存内存，随刷新丢弃（不落库——历史记录功能已按用户裁决删除）。 */
var LAST_RESULT = {};
/* R2350b（R99-P2）：shareBy 昵称只认当次链——sessionStorage 里的
 * 名字绑视图指纹（shareBy:<view>），跨视图/换一条不带 n= 的链
 * 不再喊错人。 */
function _shareByName() {
  if (window.__shareBy) return window.__shareBy;
  try {
    var _fv = window.__shareFromView ||
      new URLSearchParams(location.search).get('view') || '';
    if (!_fv) return '';
    return sessionStorage.getItem('shareBy:' + _fv) || '';
  } catch (e) { return ''; }
}
function rememberResult(viewKey, json, question, body) {
  /* v2：多存一份 body（含 gender 等），供 buildChatContext 拼性别。 */
  LAST_RESULT[viewKey] = { json: json || {}, question: question || '',
                           body: body || {}, ts: Date.now() };
  /* R233m（R45-P3）：sessionStorage 续接——刷新后「聊聊这件事」不再
   * 退化成无上下文泛化句。tab 关闭即焚，不落 localStorage。 */
  try {
    var _js = JSON.stringify(LAST_RESULT[viewKey]);
    if (_js.length < 200000) sessionStorage.setItem('lastResult:' + viewKey, _js);
  } catch (e) {}
  /* R3260（UX-PLAN-R6 R10）：档案龄——各品类最近一次出结果的日期
   * 落 localStorage（rlast:<view>=YYYY-MM-DD，只记日期不记内容）。
   * 供空态回访「你的盘上次看是 X 天前」。 */
  try {
    localStorage.setItem('rlast:' + viewKey, todayIso());
  } catch (eRL) {}
  /* R3316（审-P2）：新建排盘记录即时镜像——此前镜像只在水化于
   * 「打开过历史页/点开过详情」，从没进过历史页的用户每日清盘后
   * 一无所有。落 loc: 占位行+详情；云端行到达时 _phMirrorList
   * 同 type+ts 邻位归并顶替，不占双行。 */
  try {
    if (viewKey && _PH_BUILDERS[viewKey]) {
      var _pm = _phMirrorLoad();
      var _lts = _phTsNow();
      var _lid = 'loc:' + viewKey + ':' + _lts;
      var _lrec = {
        id: _lid, ts: _lts, type: viewKey,
        name: (_PH_TYPE_LABEL[viewKey] || '记录'),
        question: '',
        result: json,
        result_summary: { paipan_render:
          ((json && json.paipan && json.paipan.render) || '') }
      };
      _phMirrorList(_pm, [_lrec]);
      _phMirrorDetail(_pm, _lrec);
      _phMirrorSave(_pm);
    }
  } catch (ePM) {}
  /* R233r（R49-P3-2）：新结果落地顺带刷新空态 chips 语境。 */
  try { _chatChipsPersonalize(); } catch (e) {}
  /* R3242e（实测缺口）：台账 dirty 广播此前只在 bazi 提交路径发——
   * 桃花/合婚/塔罗/六爻/起名/解梦出新结果，别页历史视图拿不到
   * 即时失效（留死入口）。品类即 _PH_BUILDERS 键集的统一收口。 */
  try {
    if (_PH_BUILDERS[viewKey] && window.BroadcastChannel) {
      var _bcp = new BroadcastChannel('paipan_history');
      _bcp.postMessage('dirty'); _bcp.close();
    }
  } catch (eBC) {}
  /* R3153（specs/014-L1+）：跨日卡片记忆——用户主动去测的卡留一
   * 条「哪天·哪面·问什么·判词短句」在本机，隔日回来聊小满能对上
   * 「你前天测的那盘」。daily/xingzuo 是自动拉取不算「她去测」，
   * 不记。同日同面重测覆盖旧条——画像记的是最新状态。 */
  try {
    var _CVIEWS = { bazi: 1, taohua: 1, hehun: 1, tarot: 1,
                    liuyao: 1, qiming: 1, xzm: 1, dream: 1 };
    if (_CVIEWS[viewKey]) {
      var _cd = JSON.parse(localStorage.getItem('chat:cards') || '[]');
      if (!Array.isArray(_cd)) _cd = [];
      var _td = todayIso();
      _cd = _cd.filter(function (x) {
        return !(x && x.d === _td && x.v === viewKey);
      });
      /* R3307（审-高2）：chat:cards[].q 此前无敏感闸——dream 问句=
       * 梦原文前 30 字，进备份 JSON + 进发给 LLM 的 facts。
       * dream 一律不落原文（与服务端台账同纪律）；其余视图过
       * feCrisis/feSensitive 闸，命中即空。 */
      var _cq = '';
      try {
        _cq = (viewKey === 'dream') ? ''
          : ((question || '').slice(0, 30));
        if (_cq && (feCrisis(_cq) || feSensitive(_cq))) _cq = '';
      } catch (eQ) { _cq = ''; }
      _cd.unshift({ d: _td, v: viewKey, s: _cardVerdictShort(viewKey, json),
                    q: _cq });
      var _cut = new Date(Date.now() - 14 * 864e5).toISOString().slice(0, 10);
      _cd = _cd.filter(function (x) { return x && x.d >= _cut; }).slice(0, 12);
      /* R3306-P2：并集写——两 tab 同日各出一画像卡不互丢。 */
      _lsUnionWrite('chat:cards', _cd,
        function (x) { return x && (x.d + '|' + x.v); }, 12);
    }
  } catch (e) {}
  /* R2349t（R88-13d）：接力回赠——share 链进来的首个非日签结果
   * 弹一句「顺手替 XX 讨个彩头」。daily 是自动拉取不算「她去测」，
   * 一次性闸防每次提交都弹。
   * R3332-低：xzm 分享链自动点提交=受邀者被动看 TA 的盘，不算
   * 「她去测」——__autoReplaySubmit 按视图名一次性豁免，受邀者
   * 第一次主动测时仍能收到这句。 */
  try {
    var _sby = _shareByName();
    var _arpV = window.__autoReplaySubmit;
    if (_arpV === viewKey) window.__autoReplaySubmit = null;
    if (_sby && viewKey && viewKey !== 'daily' && _arpV !== viewKey &&
        !sessionStorage.getItem('shareBy:done')) {
      sessionStorage.setItem('shareBy:done', '1');
      setTimeout(function () {
        showToast('顺手替 ' + _sby + ' 也讨了个彩头 ✨', 'ok');
      }, 600);
    }
  } catch (e) {}
}

/* R219b（P0-2）：把缓存的响应拼成「带数据的第一句」+ 结构化 facts。
 * 返回 {msg, facts}；无缓存时回落到旧的通用句（不阻断交互）。 */
function buildChatContext(viewKey) {
  var entry = LAST_RESULT[viewKey];
  if (!entry && viewKey) {   /* R233m：刷新后从 sessionStorage 恢复 */
    try {
      var _s = sessionStorage.getItem('lastResult:' + viewKey);
      if (_s) { entry = JSON.parse(_s); LAST_RESULT[viewKey] = entry; }
    } catch (e) {}
  }
  var j = entry ? entry.json : null;
  var q = entry ? (entry.question || '') : '';
  var facts = [];
  var msg = '';
  if (!j) {
    var GENERIC = {
      bazi: '帮我看这个盘', taohua: '桃花怎么样', tarot: '牌面说什么',
      liuyao: '卦象怎么看', hehun: '这两人配吗', huangli: '今天能做什么',
      qiming: '这些名字怎么样', xingzuo: '今天运势怎么样',
      daily: '今天运势怎么样', xzm: '这两个星座配吗',
      dream: '帮我解个梦'
    };
    return { msg: GENERIC[viewKey] || '帮我看看这个结果', facts: [],
             ref: '' };
  }
  if (viewKey === 'tarot') {
    var cards = (j.draws || []).map(function (d) {
      return d.name + '·' + (d.upright ? '正位' : '逆位') +
        (d.position ? '（' + d.position + '）' : '');
    });
    msg = '我抽了' + (cards.join('、') || '牌') +
      (q ? '，问题是「' + q + '」' : '') + '，帮我解读';
    /* R3136：综合收尾（方向+观察信号+复判时点）进上下文——
     * 问「那我怎么办」时小满手里有卡面那段三段式，不是只报名号。 */
    var _tcl = ((j.warm || {}).reply || []).filter(function (l) {
      return l.indexOf('综合来看') !== -1 || l.indexOf('这组牌') !== -1;
    })[0];
    facts = (_tcl ? ['牌面口径：' + _tcl.slice(0, 90)] : [])
      .concat(cards.map(function (c) { return '牌：' + c; }));
  } else if (viewKey === 'bazi') {
    /* paipan.render 实测形如「庚午年 辛巳月 庚辰日 壬午时　日主：庚　大运：逆」
     * ——用全角空格切出四柱段与日主，避免把「大运：逆」也塞进口语句。 */
    var pp = (j.paipan || {}).render || '';
    var _seg = pp.split('　');
    var pillars = _seg[0] || '';
    var dm = (j.paipan || {}).day_master ||
      ((pp.match(/日主[：:]\s*(\S)/) || [])[1] || '');
    /* v2：带性别（用户反馈同类问题，bazi/taohua 一并补齐） */
    var _gb = (entry && entry.body && entry.body.gender) || '';
    var _glb = _gb ? ('我是' + _gb + '生，') : '';
    msg = _glb + '我的八字是' + (pillars || '（未排出）') + (dm ? '，日主' + dm : '') +
      (q ? '，我想问「' + q + '」' : '') + '，帮我看看';
    facts = (_gb ? ['性别：' + _gb] : []).concat(
      (pillars ? ['四柱：' + pillars] : []), dm ? ['日主：' + dm] : []);
    /* R2539（因果层红利进聊天）：解读的确定性因果行一并作上下文——
     * 用户追问「为什么」时模型手里有眼下运/落点宫，不是只有四柱。
     * 全部取 interpretation.sections 原文（服务端确定性产出）。 */
    var _secs = ((j.interpretation || {}).sections) || [];
    _secs.forEach(function (s) {
      var t = s.title || '', ls = s.lines || [];
      if (t === '大运走势') {
        var cur = ls.find(function (l) {
          return l.indexOf('←眼下') !== -1 && l.indexOf('第 ') === 0;
        });
        if (cur) facts.push('眼下大运：' + cur);
      } else if (t.indexOf('针对') === 0 && ls[0]) {
        facts.push('盘面位置：' + ls[0]);
      } else if (t === '五行强弱' && ls[0]) {
        facts.push('五行分布：' + ls[0]);
      }
    });
  } else if (viewKey === 'taohua') {
    /* 后端 strength 取值是 strong/mid/weak（src/guji/taohua.py:92-96）——
     * 白话映射，别把英文枚举裸抛给用户。 */
    var STR = { strong: '很旺', mid: '中等', weak: '偏淡' };
    msg = '我的桃花星在「' + (j.peach_zhi || '—') + '」，强度' +
      (STR[j.strength] || j.strength || '未知') +
      (j.year_zhi ? '，年支' + j.year_zhi : '') + '，最近桃花怎么样';
    facts = ['桃花支：' + (j.peach_zhi || '—'),
             '桃花强度：' + (STR[j.strength] || j.strength || '—')];
    if (j.hongluan) facts.push('红鸾：' + j.hongluan);
    /* R3114（facts_taohua 同口径）：判词带+入口预判进上下文。
     * R3136：入口动作行同进——「先出现在哪」是桃花卡最实的一行。 */
    ((j.warm || {}).reply || []).forEach(function (l) {
      if (l.indexOf('判词') !== -1 || l.indexOf('入口') !== -1 ||
          l.indexOf('出现在') !== -1 ||
          l.indexOf('运里') !== -1) {
        facts.push(l.slice(0, 80));
      }
    });
  } else if (viewKey === 'hehun') {
    var a = j.a_bazi || {}, b = j.b_bazi || {};
    /* R229z续23（R11-#10）：A/B → 甲/乙，与表单/422 口径统一
     * R3313（审-P1-5）：邀请态下读者是 B 侧——「我」标签贴 b，
     * 否则受邀者问小满时「我」就成了发起人（替 TA 问的前提反转）。 */
    var _rb = !!window.__hhInviteMode;
    var _meSide = _rb ? b : a, _taSide = _rb ? a : b;
    msg = '我的日柱' + (_meSide.day || '—') + '（日主' +
      (_meSide.day_master || '—') +
      '），TA 的日柱' + (_taSide.day || '—') + '（日主' +
      (_taSide.day_master || '—') +
      '），我俩配吗';
    facts = ['我的日柱：' + (_meSide.day || '—'),
             'TA 的日柱：' + (_taSide.day || '—')];
    if (j.day_wx_sheng !== undefined) {
      /* R230a-7（R13-P0-2）：同五行是比和，不是相克 */
      facts.push('日主五行：' + (j.day_wx_sheng ? '相生' :
                                 (j.day_wx_same ? '比和' : '相克')));
    }
    /* R3114（facts_hehun 同口径）：判词+指数进聊天上下文——此前
     * 只给日柱五行，小满不知道判词层说了什么会另起口径。 */
    if (j.match_score != null) {
      facts.push('合拍指数：' + j.match_score + '/99');
    }
    var _hw = ((j.warm || {}).reply || []).filter(function (l) {
      return l.indexOf('磨合') !== -1 || l.indexOf('不合适') !== -1 ||
             l.indexOf('合拍') !== -1 || l.indexOf('上等') !== -1;
    })[0];
    if (_hw) facts.push('判词：' + _hw.slice(0, 80));
    /* R3135：剧本/处方行同进 facts——小满被问「我们哪里磨、怎么处」
     * 时手里有卡面那套 48h 剧本和三段式处方，不是只有判词干条。 */
    ((j.warm || {}).reply || []).forEach(function (l) {
      if (/摩擦点|吵在|处方|先做|观察信号|48|晚上可能|第二天/.test(l) &&
          facts.length < 6) {
        facts.push('卡面说：' + l.slice(0, 90));
      }
    });
  } else if (viewKey === 'huangli') {
    /* R3315（审-P2-9）：机器 ISO 日期不拼进消息本体——人话月日+星期。 */
    var _hdd = j.date ? _cnDateSub(j.date) : '今天';
    /* R3315（审-P2-9）：宜忌截到 3 项会少念——全量下发（条数本就个位）。 */
    var yi = (j.yi || []).join('、');
    var ji = (j.ji || []).join('、');
    msg = '今天是' + _hdd + '，宜' + (yi || '—') + '，忌' +
      (ji || '—') + '，我今天适合做什么';
    facts = ['宜：' + yi, '忌：' + ji];
  } else if (viewKey === 'qiming') {
    var names = (j.full_names || []).slice(0, 5).map(function (n) {
      return n.full_name;
    });
    /* R230a-7（R13-P1-6）：missing 只报真实缺行；俱全时补 weak 口径 */
    var _fe0 = j.five_elements || {};
    var miss = (_fe0.missing || []).join('');
    var _weak = (_fe0.weak || []).join('');
    /* v2 修复：消息带上性别（用户反馈：发给小满的消息里没有性别）。
       性别存在 rememberResult 存的 body 里（submit 时随 req 一起存）。 */
    var _g = (entry && entry.body && entry.body.gender) || '';
    var _gl = _g ? ('我是' + _g + '生，') : '';
    msg = _gl + '候选名字是' + (names.join(' / ') || '（还没生成）') +
      (miss ? '，八字缺' + miss : (_weak ? '，八字偏弱' + _weak : '')) +
      '，哪个更好';
    facts = (_g ? ['性别：' + _g] : []).concat(
      names.map(function (n) { return '候选名：' + n; }));
    /* R3146：五行缺口+私心推荐行进上下文——此前只带名字串，用户问
     * 「哪个更好」小满手里没有卡面刚给过的推荐依据，可能推荐得跟
     * 卡面打架。 */
    if (miss) facts.push('八字缺：' + miss);
    else if (_weak) facts.push('八字偏弱：' + _weak);
    ((j.warm || {}).reply || []).forEach(function (l) {
      if (l.indexOf('私心') !== -1 || l.indexOf('偏弱') !== -1) {
        facts.push(l.slice(0, 90));
      }
    });
  } else if (viewKey === 'liuyao') {
    var ben = j.ben || {};
    var moving = (ben.moving_lines || []).join('、');
    msg = '我摇到的是' + (ben.gua_name || '—') + '卦（第' +
      (ben.gua_number || '—') + '卦）' + (moving ? '，动爻在' + moving : '') +
      (q ? '，问的是「' + q + '」' : '') + '，这卦怎么看';
    facts = ['本卦：' + (ben.gua_name || '—')];
    if (moving) facts.push('动爻：' + moving);
    /* R3114：用神坐标+倾向行进上下文——此前小满手里只有卦名动爻，
     * 问「能成吗」没有判词层手里的生克口径。 */
    ((j.warm || {}).reply || []).forEach(function (l) {
      if (l.indexOf('照传统口径看') !== -1 ||
          l.indexOf('传统上先看') !== -1 ||
          /* R3136：三段式处方行进上下文（先做→看信号→若则） */
          l.indexOf('观察信号') !== -1 ||
          l.indexOf('能做的最实一步') !== -1 ||
          /* R3144：应期行进上下文——聊「什么时候有动静」时小满手里
           * 要有卡面刚给过的逢值/逢冲窗口，不然两口径打架。 */
          l.indexOf('应期参考') !== -1) {
        facts.push(l.slice(0, 90));
      }
    });
  } else if (viewKey === 'daily') {
    /* R233r（R49-Top5-4）：日签卡链路——展开过「完整解读」后聊天有
     * 上下文可聊（此前首页聊小满手里空空，纯放飞）。 */
    var _dpp = (j.paipan || {}).render || '';
    var _dseg = _dpp.split('　');
    var _dw = (j.warm && j.warm.one_liner) || '';
    msg = '今天的日签我看了' + (_dw ? '（' + _dw + '）' : '') +
      '，帮我详细说说今天';
    facts = (_dseg[0] ? ['四柱：' + _dseg[0]] : [])
      .concat(_dw ? ['一句话：' + _dw] : []);
    /* R3124（真修）：日签响应没有 warm 块——上面的 one_liner 恒空，
     * 卡面真正的内容（summary 事实句+宜/忌+贵人）从来没进过
     * 聊天上下文。用户照着卡面问「今天怎么样」，小满手里只有
     * 四柱，说不上来卡上写了什么。把 summary 事实句与宜忌列透传。 */
    var _dsum = _pStr(j.summary);
    if (_dsum) {
      _dsum.split('；').forEach(function (seg) {
        seg = seg.trim();
        if (seg) facts.push('日签：' + seg.slice(0, 80));
      });
    }
    var _ddo = _pArr(j.do).join('、'), _ddont = _pArr(j.dont).join('、');
    if (_ddo) facts.push('今日宜：' + _ddo.slice(0, 60));
    if (_ddont) facts.push('今日忌：' + _ddont.slice(0, 60));
    if (_pStr(j.noble)) facts.push('今日贵人：' + _pStr(j.noble));
    /* R3261（R15）：财神方位进 facts——聊搞钱/财的事时小满手里
     * 有同一个确定性坐标，不会瞎编方位。 */
    if (_pStr(j.money_dir)) {
      facts.push('今日财神方位：' + _pStr(j.money_dir));
    }
    /* R3314（R3312-P2-8）：开运色/幸运数进 facts——照日卡问
     * 「今天什么幸运色」时小满手里有同一张卡。 */
    if (j.lucky && _pStr(j.lucky.color)) {
      facts.push('今日开运色：' + _pStr(j.lucky.color) +
        (_pStr(j.lucky.num) ? '，幸运数 ' + _pStr(j.lucky.num) : ''));
    }
    /* R3315（审-P2-9）：月相/节日/农历行进 facts——冷问「月相」
     * 小满此前只能答「没有数据」，其实卡面有。同源下发。 */
    if (j.moon && _pStr(j.moon.phase)) {
      facts.push('今日月相：' + _pStr(j.moon.phase) +
        (_pStr(j.moon.line) ? '（' + _pStr(j.moon.line) + '）' : ''));
    }
    if (j.festival && (j.festival || []).length) {
      facts.push('今日节日：' + (j.festival || []).join('、'));
    }
    if (_pStr(j.lunar)) facts.push('今日农历：' + _pStr(j.lunar));
  } else if (viewKey === 'xzm') {
    /* R3131：合盘卡上下文——判词/场景/处方行进 facts，小满聊这张
     * 卡手里有同一套口径（与 result_ref 权威块互补：xzm 无判词卡
     * 锚点结构，facts 即全部上下文）。 */
    msg = '我看了' + (j.a || '') + '×' + (j.b || '') + '的合盘（' +
      (j.score || '') + '分·' + (j.label || '') + '），帮我详细说说';
    facts = ['合盘：' + (j.a || '') + '×' + (j.b || '') + ' ' +
             (j.score || '') + '分·' + (j.label || '')];
    (j.lines || []).slice(0, 4).forEach(function (ln) {
      if (ln) facts.push('合盘卡：' + String(ln).slice(0, 80));
    });
  } else if (viewKey === 'xingzuo') {
    var today = (j.signs || []).filter(function (s) { return s.is_today; })[0];
    /* R229z续23（R11-#23/#36）：「今天是 2026-…」双空格＋「值宫」术语
     * R3315（审-P2-9）：同上——ISO 日期换人话口径。 */
    msg = '今天是' + (j.date ? _cnDateSub(j.date) : '') + '，'
      + ((today && today.sign) || '—') + '座当班，我今天运势怎么样';
    facts = ['今天轮到' + ((today && today.sign) || '—') + '座当班'];
  } else if (viewKey === 'dream') {
    /* R3178：解梦卡——象征名+梦文本进上下文，照梦聊时小满手里
     * 有册子口径（服务端 verdicts 会再补「梦里对上的画面」）。 */
    var _syms = (j.symbols || []).map(function (s) { return s.name; });
    msg = '我做了个梦：「' + (q || '记不清细节了') + '」' +
      (_syms.length ? '，册子对上了「' + _syms.join('、') + '」' : '') +
      '，陪我聊聊';
    facts = _syms.slice(0, 3).map(function (s) { return '梦见：' + s; });
    var _dr = ((j.warm || {}).reply || [])[1];
    if (_dr) facts.push('解读口径：' + String(_dr).slice(0, 90));
  } else {
    msg = '帮我看看这个结果';
  }
  /* R3124b（specs/012-P0）：result_ref 随上下文出——聊这张卡时
   * 服务端按 ref 从自己缓存里取判词层进权威信道（小满口径=卡面）。 */
  return { msg: msg, facts: facts.slice(0, 6),
           ref: (j && j.result_ref) || '' };
}

/** R207b：聊天入口全局化——结果容器渲染出 .card 后尾部统一挂入口钮。
 *  已有则跳过（重绘安全）；无 .card（如空态/错误态）不挂。 */
function attachChatEntry(container) {
  if (!container) return;
  /* R230k（R23-P2-1）：星座结果根节点是 .xz-result、本命盘抽屉是
   * .birth-card——都不含 .card，入口钮一直挂不上（实测这三面计数=0）。
   * 选择器放宽到已知结果壳。 */
  var card = container.querySelector('.card, .xz-result, .birth-card');
  /* R3162：裸结果壳兜底——xzmResult 这类直渲 div 的结果没有内层
   * .card，选择器找不到目标就静默 no-op，入口永远挂不上。退一步
   * 挂在容器自身（调用方传的都是结果容器）。 */
  if (!card) card = container;
  /* R230t（R33-P1-1）：判重走 data-chat-entry 而非类名——qmRefreshBtn/
   * nameReviewBtn 也用 .chat-entry 做样式，此前会误判「已有入口」跳过。
   * R3258 修：判重改到 container 全域——此前只查首个 .card 子孙，
   * dailyDetail 展开后容器里新增 .card，再跑 attachChatEntry 就把
   * 第二颗「聊聊这件事」挂进内层卡（老钮还留在卡尾）。 */
  if (container.querySelector('[data-chat-entry]')) return;
  var btn = document.createElement('button');
  btn.className = 'chat-entry';
  btn.type = 'button';
  btn.dataset.chatEntry = '';
  /* R230j（R22-P3-6）：id=chatEntry 与黄历内联钮共存时是重复 id
   * （invalid HTML）——委托与判重都走 .chat-entry 类即可，id 摘掉。 */
  /* R218a-巡4（A-b）：图标按钮补 aria-label */
  btn.setAttribute('aria-label', '打开小满聊天，聊聊这件事');
  btn.textContent = '💬 聊聊这件事';
  card.appendChild(btn);
  /* R2350d（R100-P1-1）：结果卡零品牌露出——手动截图发小红书
   * 看不出出处。挂聊天入口的卡（≈全部结果卡）底部统一一行
   * 小字水印，截图自带品牌。 */
  if (!card.querySelector('.card-brand')) {
    var wm = document.createElement('div');
    wm.className = 'card-brand';
    wm.textContent = '🐻 小满的解忧铺';
    card.appendChild(wm);
  }
}

/* R230d（R16-P2-7）：轮数封顶后此前只复读收尾文案，用户没有任何
 * 出路提示。后端 rec.closed=True 时在气泡尾部挂「开新话题」引导钮——
 * 点了换新 sid（旧会话仍在内存，只是不再继续聊）。 */
/* R3208：「开个新话题」钮抽成可复用件——收尾提示与失忆分隔共用
 *（断档提示也要给用户「翻篇」的主动权）。 */
function _chatResetBtn(label) {
  var row = document.createElement('div');
  row.className = 'chat-reset';
  row.style.marginTop = '8px';
  var b = document.createElement('button');
  b.type = 'button'; b.className = 'chat-chip';
  b.setAttribute('aria-label', '清空本轮聊天，开个新话题');
  b.textContent = label || '🌱 聊够啦？开个新话题';
  var _orig = b.textContent;
  b.addEventListener('click', function () {
    /* R230t（R33-P2-4）：清 transcript+换 sid 此前一点即执行——
     * 两点确认与排盘删除同款（3s 内再点才真清）。 */
    if (b.dataset.armed !== '1') {
      b.dataset.armed = '1';
      b.textContent = '这轮聊天记录会清空，再点一次确认';
      setTimeout(function () {
        if (b.isConnected) { b.dataset.armed = '0'; b.textContent = _orig; }
      }, 3000);
      return;
    }
    try {
      (_chatStore() || _MEM_STORE).removeItem(CHAT_SID_KEY);
      (_chatStore() || _MEM_STORE).removeItem('chatClosed');
    } catch (e) {}
    chatSid();   /* 重新生成 sid */
    _chatTsClear();   /* R230q：新话题起新 transcript——旧气泡重渲会污染新会话 */
    var _flow = el('chatFlow');
    if (_flow) _flow.innerHTML = '';
    _CHAT_SEND_COUNT = 0;
    _chatEmptyRebuild();   /* R3202：空态块（chips/昵称招呼）重建回来 */
    row.remove();
  });
  row.appendChild(b);
  return row;
}
function _chatClosedHint(bubble) {
  if (!bubble || bubble.querySelector('.chat-reset')) return;
  /* R2400（R123-P2-4）：closed 态持久化——F5 后 transcript 恢复气泡
   * 但钮丢了（服务端仍收尾态）。存旗标，恢复时挂回。 */
  try { (_chatStore() || _MEM_STORE).setItem('chatClosed', '1'); } catch (e) {}
  bubble.appendChild(_chatResetBtn());
}

/* R3202：「开新话题」后补回空态块——静态 #chatEmpty 在首个气泡落地
 * 时被 chatBubble 全清（.chat-empty 全删），清零重来用户面对的只剩
 * 一句光秃秃「新话题开张」，chips/昵称招呼全丢。重建同款结构再走
 * _chatChipsPersonalize（时段招呼/深夜梦入口都跟着回来）。 */
function _chatEmptyRebuild() {
  var flow = el('chatFlow');
  if (!flow || !flow.parentNode) return;
  if (document.querySelector('.chat-empty')) return;
  var d = document.createElement('div');
  d.className = 'chat-empty'; d.id = 'chatEmpty';
  d.innerHTML =
    '<img class="chat-empty-avatar" loading="lazy" decoding="async" ' +
    'src="/static/cream/avatar-xiaoman-cream.jpg" alt="" width="56" height="56">' +
    '<p class="chat-empty-hi">我是小满 ✨</p>' +
    '<p class="chat-empty-sub">想聊什么都可以，或者从下面挑一个开始</p>' +
    '<p class="chat-empty-shop" id="chatShopLine"></p>' +
    '<div class="chat-empty-chips">' +
    '<button type="button" class="chat-chip" data-ask="今天运势怎么样？">今天运势怎么样</button>' +
    '<button type="button" class="chat-chip" data-ask="我最近工作和财运怎么样？">工作财运怎么样</button>' +
    '<button type="button" class="chat-chip" data-ask="我最近的感情会有进展吗？">最近感情有进展吗</button>' +
    '<button type="button" class="chat-chip" data-ask="帮我看看我的八字">帮我看看我的八字</button>' +
    '</div>';
  flow.parentNode.insertBefore(d, flow);
  try { _chatChipsPersonalize(); } catch (e) {}
}

/* R3207：时辰对照表——知道「子时/亥时」不知道是几点的用户此前
 * 只能切出去查。共享一张表，按需挂到每个时辰输入框的 .field 尾巴。
 * R3213（用户实测）：纯查表仍要用户自己换算成数字再敲——改成
 * 「点选即填」：每格是按钮，点了把该时辰的代表整点（时段起点）
 * 直接填进输入框；查表与填写一步到位。 */
var _HOUR_CHEAT = [
  ['子', '23:00–00:59', 23], ['丑', '01:00–02:59', 1], ['寅', '03:00–04:59', 3],
  ['卯', '05:00–06:59', 5], ['辰', '07:00–08:59', 7], ['巳', '09:00–10:59', 9],
  ['午', '11:00–12:59', 11], ['未', '13:00–14:59', 13], ['申', '15:00–16:59', 15],
  ['酉', '17:00–18:59', 17], ['戌', '19:00–20:59', 19], ['亥', '21:00–22:59', 21]];
/* R3241：数字点→时辰名（_HOUR_CHEAT 反查）——生辰回显/判词语境
 * 说「亥时」比「21时」贴命理话。23/0→子，1-2→丑 … 21-22→亥。 */
function _hourZhi(h) {
  h = Number(h);
  if (!Number.isFinite(h) || h < 0 || h > 23) return '';
  return '子丑寅卯辰巳午未申酉戌亥'.slice(
    Math.floor(((h + 1) % 24) / 2), Math.floor(((h + 1) % 24) / 2) + 1) + '时';
}
function _hourCheatAttach(inputId) {
  var inp = el(inputId);
  if (!inp || !inp.parentNode ||
      inp.parentNode.querySelector('.hour-cheat')) return;
  var d = document.createElement('details');
  d.className = 'hour-cheat';
  var rows = '';
  for (var i = 0; i < _HOUR_CHEAT.length; i++) {
    rows += '<button type="button" class="hour-pick" data-h="' +
            _HOUR_CHEAT[i][2] + '"><b>' + _HOUR_CHEAT[i][0] + '时</b> ' +
            _HOUR_CHEAT[i][1] + '</button>';
  }
  d.innerHTML = '<summary>时辰对照（知道时辰名，点一下直接填）</summary>' +
    '<div class="hour-cheat-grid">' + rows + '</div>';
  d.addEventListener('click', function (ev) {
    var b = ev.target && ev.target.closest
      ? ev.target.closest('.hour-pick') : null;
    if (!b) return;
    inp.value = b.getAttribute('data-h');
    inp.dispatchEvent(new Event('input', { bubbles: true }));
    inp.dispatchEvent(new Event('change', { bubbles: true }));
    try { inp.focus(); } catch (e) {}
  });
  inp.parentNode.appendChild(d);
}

/* R217a：点击「聊聊这件事」自动发送当前排盘上下文，无需用户手动输入 */
var _autoSendBusy = false;
function autoSendChatContext() {
  /* R230t（R33-P3-10）：.chat-entry 双击理论双发——1.5s 在途窗。 */
  if (_autoSendBusy) return;
  _autoSendBusy = true;
  setTimeout(function () { _autoSendBusy = false; }, 1500);
  /* D-001-fix：先确保侧栏打开再发送消息 */
  chatOpen();
  /* R219b（P0-2）：第一句必须带真实数据（牌名/干支/宜忌/候选名），
   * 由 buildChatContext 从 LAST_RESULT 缓存里拼出；facts 同步带结构化坐标，
   * 后端 spawn_chat_task 拿到的不再是一句空泛的「帮我看这个盘」。 */
  var view = document.querySelector('.view.active');
  var viewId = view ? view.id : '';
  var viewKey = '';
  ['taohua', 'tarot', 'liuyao', 'hehun', 'huangli', 'qiming', 'xingzuo',
   'bazi', 'dream'].forEach(function (k) {
    if (!viewKey && viewId.indexOf(k) !== -1) viewKey = k;
  });
  /* R3131：星座页内嵌速配抽屉——同页两套结果，聊天下手挑更新的
   * 那张卡（刚测完合盘点聊聊 → xzm；刚看值宫 → xingzuo）。 */
  if (viewKey === 'xingzuo' && LAST_RESULT.xzm &&
      (!LAST_RESULT.xingzuo ||
       (LAST_RESULT.xzm.ts || 0) > (LAST_RESULT.xingzuo.ts || 0))) {
    viewKey = 'xzm';
  }
  /* R2349q（R82-P1-4）：首页（无 .view 壳）发「聊聊这件事」此前落
   * 空 viewKey → 零上下文泛句；日签本就存了 rememberResult('daily')，
   * 与 _activeViewFacts 同口径兜底 'daily'。 */
  if (!viewKey) viewKey = 'daily';
  var ctx = buildChatContext(viewKey);
  var msg = ctx.msg;
  /* R3259（UX-STRATEGY-NEXT N4）：小满记忆——把她问过的事归到
   * 五个事由桶（工作/钱/感情/身体/家里）存在本机；回访时空态
   * 多一行「上次你问起X的事——还想再看看吗」，陌生人→熟人。 */
  try {
    /* R3260：事由足迹收口——旧 _BKT 块写的是 {主题:日期} 对象，
     * 与 _chatTopicLog 的 [{d,t,v}] 数组互相摧毁（互相读不懂、
     * 互相覆盖丢数据）。统一走 _chatTopicLog（同写端、同主题表、
     * 顺带记面板 v）。 */
    try { _chatTopicLog(msg); } catch (eTP2) {}
  } catch (eTP) {}
  /* facts 优先用本视图的结构化坐标；为空时回落到排盘时存的 CHAT_LAST_FACTS */
  var facts = (ctx.facts && ctx.facts.length) ? ctx.facts : CHAT_LAST_FACTS;
  chatBubble('me', msg);
  /* R230t（R32-P2-16）：自动发与手发同口径计数——此前自动发不计数，
   * 同一会话两套禁用行为并存（「允许追问 1 次」的语义本就该含自动条）。 */
  _CHAT_SEND_COUNT = (_CHAT_SEND_COUNT || 0) + 1;
/* R230v（R34-#3）：同 chatSend——捕获 sid 防跨话题幻影写回。 */
  var _sid0 = chatSid();
  var _ty0 = chatBubble('ai', '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span><span class="chat-wait-note">小满正在翻书…</span>', {raw: true});   /* R2343 */
  postJSON('/api/chat', {
    /* R230l（R24-P2-3）：黄历事实的「今天」锚浏览器本地日——服务器
     * UTC vs 浏览器 CST 跨零点窗口整天错位。 */
    session_id: _sid0, message: msg, facts: _chatFacts(facts, msg),
    result_ref: ctx.ref || '',
    client_date: todayIso()
  }, { silent: true }).then(function (j) {
    if (!j.chat_task_id) {
      /* R2355（R111-P2-6）：限流≠关停——rate_limited 只提示不锁框。 */
      if (j && j.rate_limited) {
        if (_ty0) { _ty0.remove(); _ty0 = null; }
        _CHAT_SEND_COUNT = Math.max(0, (_CHAT_SEND_COUNT || 0) - 1);
        /* R2400（R123-P2-5）：限流气泡落档——nosave 会留孤儿气泡。 */
        chatBubble('ai', '（聊太急啦，小满喝口水歇口气，一会儿再戳我～）');
        return;
      }
      if (_ty0) { _ty0.remove(); _ty0 = null; }
      /* R218a-02：U-008 修复后仍复用同一句话「打烊中」复读——扩展为
       * 4-6 句确定性轮换，并按上下文（自动发送：必属「看盘」类）做轻回应。 */
      var _fb = chatBubble('ai', _chatFallbackLine('看盘'), { nosave: true });
      _chatActChip(_fb, j && j.action);   /* R3195：打烊时路标更要给真入口 */
      /* R230t（R32-P2-16）：与 chatSend 同一禁用规则。 */
      var _inA = el('chatInput'), _sbA = document.getElementById('chatSendBtn');
      if (_CHAT_SEND_COUNT >= 2) {
        if (_inA) { _inA.disabled = true; _inA.placeholder = '小满休息中，回头再来聊吧'; }
        if (_sbA) _sbA.disabled = true;
      }
      return;
    }
    /* R230t（R32-P2-16）：拿到任务即解锁——DISABLE 恢复后不再被锁在
     * 「休息中」直到换 sid。 */
    var _inU = el('chatInput'), _sbU = document.getElementById('chatSendBtn');
    if (_inU && _inU.disabled) { _inU.disabled = false; _inU.placeholder = '说说你的心情…'; }
    if (_sbU && _sbU.disabled) _sbU.disabled = false;
    /* R228c：raw 仅内部动效用；保存气泡节点引用——轮询写回不再赌
     * flow.lastChild（竞态下会覆盖/删掉用户自己刚发的消息）。
     * R2343：复用发送时已插的 typing 节点。 */
    var _ty = _ty0 || chatBubble('ai',
      '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span><span class="chat-wait-note">小满正在翻书…</span>', {raw: true});
    _pollChatReply(j.chat_task_id, _ty, _sid0, j.action, msg);   /* R233r+R3213：msg 供失败重发：共用轮询体（含排队预算） */
  }).catch(function () {
    if (_ty0) { _ty0.remove(); _ty0 = null; }
    chatBubble('ai', '（' + _dayPick(['网络不太好，再发一次试试？','信号飘了，一会儿再戳我','刚才没接到，再发一次吧～'],'net') + '）', { nosave: true });
  });
}

/* R233r（R49-P3-3）：两处轮询体抽出共用——chatSend 与
 * autoSendChatContext 此前逐字各持一份 ~75 行（且 autoSend 版漏声明
 * _queueCap，排队态引用未定义变量会炸掉整个 tick）。
 * 约定：tid=任务id；ty=typing气泡节点；sid0=发送时sid。 */
/* R3195：路标 chip——后端 action={view,label} 时，回复气泡尾挂一个
 * 可点按钮直达真功能页，并收拢聊天抽屉。比纯文字指路少一步找。 */
/* R3201：可回放的路标视图白名单——与服务端 _CHAT_ACTIONS 同集。 */
var _CHAT_ACT_VIEWS = { tarot: 1, liuyao: 1, hehun: 1, qiming: 1,
                        home: 1, dream: 1, bazi: 1, oracle: 1,
                        /* R3352：咒语册/心情周记视图白名单补齐——
                         * 缺了 transcript 重渲丢 chip。 */
                        mantra: 1, moodweek: 1,
                        /* R3381：默契挑战路标白名单。 */
                        mochi: 1,
                        /* R3388：每日一签路标白名单。 */
                        qian: 1,
                        /* R3394：答案之书路标白名单。 */
                        ansb: 1 };
/* R3352：路标落点表——view 是「街区」，anchor 是「门牌」。
 * details 类的送到并展开；id 类的滚到门口。 */
var _CHAT_ACT_ANCHORS = {
  shred: '.ck-shred', wish: '.ck-wish',
  checkin: '#dailyCheckin', annual: '#checkinYear',
  celeb: '#celebDrawer',
  /* R3370-P1-2：万圣限定卡锚——窗口内 trQH 已现身，滚到门口。 */
  trQH: '#trQH' };
function _chatActChip(bubble, action) {
  if (!bubble || !action || !action.view || !action.label) return;
  /* R3368（积压-动作chip去重）：重试/打烊/任务落地多条链路
   * 会对同一气泡重复挂同文路标——同 label 已挂载时不再叠。 */
  var _dup = false;
  try {
    bubble.querySelectorAll('.chat-act-chip').forEach(function (_c) {
      if ((_c.textContent || '') === action.label) _dup = true;
    });
  } catch (eD0) {}
  if (_dup) return;
  var b = document.createElement('button');
  b.type = 'button';
  b.className = 'chat-chip chat-act-chip';
  b.textContent = action.label;
  b.addEventListener('click', function () {
    /* 关抽屉：与 _setRecent(false) 同口径（局部函数够不着，照抄复位）。 */
    var sb = el('recentSidebar');
    if (sb) {
      sb.classList.remove('open'); sb.inert = true;
      sb.setAttribute('aria-hidden', 'true');
      try { sbFocusable(sb, false); } catch (e1) {}
    }
    var bd = el('recentBackdrop');
    if (bd) bd.classList.remove('open');
    var tg = el('recentToggle');
    if (tg) tg.setAttribute('aria-expanded', 'false');
    try { _mainInert(false); } catch (e2) {}
    try { showView(action.view); } catch (e3) {}
    /* R3352：锚点落位——路标不再只到页顶：目标 details 展开 +
     * 滚到门口。年报钮没达标时是 disabled 无 id 变体，回落打卡区。 */
    try {
      var _sel = _CHAT_ACT_ANCHORS[action.anchor];
      var _tgt = _sel ? document.querySelector(_sel) : null;
      if (!_tgt && action.anchor === 'annual')
        _tgt = el('dailyCheckin');
      if (_tgt) {
        var _det = _tgt.tagName === 'DETAILS'
          ? _tgt : _tgt.closest('details');
        if (_det) _det.open = true;
        setTimeout(function () {
          _tgt.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }, 120);
      }
    } catch (eA) {}
  });
  bubble.appendChild(b);
}

/* R3213（用户反馈）：「没接住」此前一句通用文案，用户不知道发生了什么、
 * 也不知道怎么办。按成因分文案（生成失败/任务过期/排队/断网），且就地
 * 挂「再发一次」钮——点击原样重发同一句，不需要用户重打一遍。 */
function _chatFailInto(ty, kind, msg, sid0) {
  if (!ty) return;
  if (ty._twCancel) { try { ty._twCancel(); } catch (eT) {} }   /* R3241：止旧打字防覆盖 */
  var _txt = {
    fail: '（小满刚才走神了，这句没接住。别重打，点下面再来一次～）',
    gone: '（刚才那句在路上丢了，服务歇了一下。点下面让小满再听一遍～）',
    busy: '（小满这会儿有点忙，稍等点下面再发一次～）',
    net: '（网络飘了一下，刚才那句没送到。点下面重发一次～）'
  }[kind] || '（刚才没接住，再发一次试试？）';
  ty.textContent = _txt;
  if (msg && sid0 === chatSid()) {
    var rb = document.createElement('button');
    rb.type = 'button';
    rb.className = 'chat-chip chat-retry-chip';
    rb.textContent = '再发一次';
    rb.addEventListener('click', function () {
      if (rb.disabled || sid0 !== chatSid()) return;
      rb.disabled = true;
      _chatRetrySend(msg, ty, sid0);
    });
    ty.appendChild(rb);
  }
}
/* 重发：原句再投一次 /api/chat，命中新任务直接在本气泡上续轮询。
 * 不计入 _CHAT_SEND_COUNT（同一条消息的补投不是新发）。 */
function _chatRetrySend(msg, ty, sid0) {
  if (!msg || sid0 !== chatSid()) return;
  if (ty._twCancel) { try { ty._twCancel(); } catch (eT) {} }   /* R3241 */
  ty.innerHTML = '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span><span class="chat-wait-note">小满正在翻书…</span>';
  postJSON('/api/chat', {
    session_id: sid0, message: msg,
    facts: _chatFacts((CHAT_LAST_FACTS && CHAT_LAST_FACTS.length)
      ? CHAT_LAST_FACTS : _activeViewFacts()),
    result_ref: _CHAT_CTX_REF || '',
    client_date: todayIso()
  }, { silent: true }).then(function (j) {
    if (sid0 !== chatSid()) return;
    if (j && j.chat_task_id) {
      _pollChatReply(j.chat_task_id, ty, sid0, j.action, msg);
    } else {
      _chatFailInto(ty, 'busy', msg, sid0);
    }
  }).catch(function () {
    _chatFailInto(ty, 'net', msg, sid0);
  });
}

/* R3241：等待文案轮换池——推理模型首包 ~40s，一句静态文案
 * 看两遍就又是干等；每个轮询 tick 换一句。 */
var _WAIT_NOTES = ['小满正在翻书…', '把你的盘摊开再看看…',
  '在想怎么回你最贴心…', '快了快了，在挑词儿…',
  '小满在掐指算着呢…', '再翻一页就有答案了…'];
function _pollChatReply(tid, ty, sid0, action, msg) {
  var deadline = performance.now() + AI_POLL_CAP_S * 1000;
  var _queueCap = performance.now() + 90000;
  var _wait = AI_POLL_INTERVAL_MS;
  var _wnI = 0;
  var tick = function () {
    if (sid0 !== chatSid()) return;   /* 换过 sid 的旧任务落地即弃 */
    var _wn = ty && ty.querySelector && ty.querySelector('.chat-wait-note');
    if (_wn) _wn.textContent = _WAIT_NOTES[(++_wnI) % _WAIT_NOTES.length];
    if (_aiPollGate()) {              /* 后台/断网暂停取数，预算照走 */
      if (performance.now() < deadline) setTimeout(tick, 2000);
      else _chatFailInto(ty, 'net', msg, sid0);
      return;
    }
    api('/api/ai/' + encodeURIComponent(tid), { silent: true }).then(function (st) {
      if (!ty || sid0 !== chatSid()) return;
      if (st && st.status === 'done' && st.text) {
        _chatBootNote(st, ty);       /* 重启失忆插分隔 */
        _chatFreshNote(st, ty);      /* TTL 回收分隔 */
        /* R3241：回复逐字蹦——打完再换富文本终态+路标 chip。
         * transcript 立即存全量（存档不受放映影响）。 */
        typewriteInto(ty, st.text, function () {
          ty.innerHTML = renderRichText(st.text);
          _chatActChip(ty, action);    /* R3195：路标 chip 随回复落地 */
          if (st.closed) _chatClosedHint(ty);
        });
        _chatTsSave('ai', st.text, action);   /* R3201：action 随泡入档 */
        return;
      }
      if (st && st.status === 'failed') {
        /* R3222：agnes 推理模型延迟抖动大（实测 ReadTimeout 占大头），
         * 首次失败先静默原句重投一次（typing 不打断），二次仍败才出文案。
         * ty.dataset 记重试数，防连环重投。 */
        var _rt = +(ty.dataset.chatRetry || 0);
        if (msg && sid0 === chatSid() && _rt < 1) {
          ty.dataset.chatRetry = '1';
          _chatRetrySend(msg, ty, sid0);
          return;
        }
        _chatFailInto(ty, 'fail', msg, sid0);
        return;
      }
      if (st && st.status === 'pending' && st.queued) {
        /* 服务端排队中——生成预算从起动起算。 */
        if (performance.now() < _queueCap) {
          setTimeout(tick, _wait); _wait = _aiBackoff(_wait);
        } else { _chatFailInto(ty, 'busy', msg, sid0); }
        return;
      }
      if (performance.now() < deadline) { setTimeout(tick, _wait); _wait = _aiBackoff(_wait); }
      else _chatFailInto(ty, 'net', msg, sid0);
    }).catch(function (e) {
      /* 404 = 任务已不在（重启/过期）——早退不轮满预算。 */
      if (e && e.status === 404) {
        _chatFailInto(ty, 'gone', msg, sid0);
        return;
      }
      if (performance.now() < deadline) { setTimeout(tick, _wait); _wait = _aiBackoff(_wait); }
      else _chatFailInto(ty, 'net', msg, sid0);
    });
  };
  setTimeout(tick, AI_POLL_INTERVAL_MS);
}

/* R218a-02：聊天降级文案池 + 关键词到 openeer 的最轻量级分支。
 * 数据池与 src/guji/copy_bank.json#chat_fallback_openers 同源（aditive 复制），
 * 选句策略：同 session 内消息序号 = 轮换种子（同用户复读也变），关键词匹配
 * 命中后取对应池的第 (counter % pool_size) 句。零 API 契约变更、零后端改动。 */
var _CHAT_FALLBACK_DEFAULT = [
  "今天小满提前打烊啦～心事先发给我，想聊的时候随时来，我一直在这。",
  "解忧铺这会儿休整中，发的心事我记下了，随时回来听我细说。",
  "小满现在不上班，门口的牌子写着「歇业中」，你先歇会儿，想聊再来。",
  "这会儿小满调休中～把心事先写下来，我一回来就翻你的牌。",
  "打烊了哦～这条消息我存着，下回开门接着说。",
  "解忧铺的灯这会儿关了，你的心事没丢，开门第一单给你留着。",
  "我先歇一会儿，存好你的话，回来带着力气一起拆。",
  "小满今天关店早，你先把心事写下来，回来找我深聊。",
  "门牌已经翻到「休息中」，你的消息我存着，先歇口气。",
  "解忧铺的茶这会儿凉了，重新烧上了，你写下来的我都会读。"
];
var _CHAT_FALLBACK_BY_KW = {
  'tired': [
    "累了啊…小满这会儿不在岗，细节留着我回来听。先喝口温水，别再撑了。",
    "听着就累。先把肩膀松下来，回头来找我，咱们一件一件拆。",
    "身体先叫停一下比什么都重要。先睡饱，回头找我。",
    "累的时候做的决定十有八九会后悔，先放放，回头来。",
    "辛苦了。先把待办关掉，明天的你再收拾残局也来得及。",
    "先给自己续杯热水。你的累我记着了，回来慢慢说。"
  ],
  'work': [
    "工作的坎儿先不急开会，思路睡一觉会清楚很多，回头找我聊细节。",
    "听到工作的苦。回头跟我讲讲你卡在哪一环，咱们一起拆。",
    "工作的事先放我这儿，你先下班。",
    "职场的弯弯绕绕回来拆给你听。先喝口热的，喘口气。",
    "班先下了，委屈先搁我这儿。回头咱们一条一条过。",
    "这份活不决定你的价值：先歇，回来慢慢说。"
  ],
  'love': [
    "感情的事急也急不出答案。先放过自己，回头来跟我讲。",
    "爱里的纠结最难熬。回头来找我，把心意慢慢理顺。",
    "先不猜他的心思了，回头来听我细说。",
    "心动或心累都先收着，回来我陪你解。",
    "那个人怎么想先放放，你先照顾好自己。",
    "感情里没有标准答案，你讲得开心最要紧。回头细聊。"
  ],
  'study': [
    "学习的压力先放一放，脑子也需要打烊。回头我陪你拆重点。",
    "考试的事先交给睡一觉的自己，先复盘三件今天做对的小事。",
    "学不进去的时候别硬撑，回头来我帮你把节奏理一理。",
    "作业的事回头再战。先奖励自己一集短剧。",
    "分数是一时的，你一直在往前走就很棒。回头聊。",
    "背不进去就先合上书本，去倒杯水。回来我陪你理思路。"
  ],
  'money': [
    "钱包的事回头再算：先不想钱的事。",
    "理财的纠结回来拆给你听。先关掉账单页面。",
    "先不数余额。回头来找我，把账本翻一遍。",
    "钱的事别熬夜想，夜里做的预算都偏严。回头聊。",
    "挣钱是长跑，今天先不比配速。回头帮你看看开源思路。",
    "钱包君也需要假期，先吃顿好的（预算内），回头再算。"
  ],
  'default': [
    "今天小满提前打烊啦～你的消息我存着，我一直在这。",
    "解忧铺这会儿休整中，你的心事我存着，随时来听。",
    "门牌已经翻到「休息中」，回头找我深聊。",
    "解忧铺的茶凉了，重新烧上了，你写下来的我都会读。",
    "小满去后院浇水了，你的话挂在门口的风铃上，回来就听。",
    "这会儿我在整理书架，你的那一条排第一个。"
  ]
};
/* 关键词→分类映射（命中第一个即用） */
var _CHAT_FALLBACK_KW_MAP = [
  /* R3356（审-低）：焦虑/emo/内耗/郁闷/烦——server 烦恼族有、
   * 兜底词表此前没有，DISABLE 时落 default 打烊池与 shred chip
   * 不对题。并进 tired 池（心累同根口径）。 */
  { cat: 'tired',   kws: ['累', '疲惫', '睡', '失眠', '撑', '撑不住', '废', '躺',
    '焦虑', 'emo', '内耗', '郁闷', '烦'] },
  { cat: 'work',    kws: ['工作', '职场', '同事', '老板', '上司', '升职', '跳槽', '上班', '加班', '辞职'] },
  /* R3370-低10：伴侣称呼/吵架词补进 love 池——「和男朋友吵架了」
   * 此前落 default 池答非所问。 */
  { cat: 'love',    kws: ['感情', '恋爱', '喜欢', '分手', '前任', '对象', '暗恋', '表白', '相亲', '暧昧',
    '男朋友', '女朋友', '男友', '女友', '老公', '老婆', '爱人', '吵架'] },
  { cat: 'study',   kws: ['学习', '考试', '作业', '考研', '高考', '中考', '成绩', '课程', '论文', '答辩'] },
  { cat: 'money',   kws: ['钱', '工资', '消费', '理财', '账单', '余额', '省钱', '欠款', '花呗'] },
  /* R2359（R114-P4-2）：裸「看」字太宽——「我去看看医生/看书」都会错
   * 分到看盘池；「看看/解盘/解读」已覆盖原意。 */
  { cat: 'reading', kws: ['牌', '卦', '命', '盘', '解盘', '看看', '解读', '分析'] }
];
function _chatClassify(message) {
  var s = String(message || '');
  for (var i = 0; i < _CHAT_FALLBACK_KW_MAP.length; i++) {
    var entry = _CHAT_FALLBACK_KW_MAP[i];
    for (var j = 0; j < entry.kws.length; j++) {
      if (s.indexOf(entry.kws[j]) !== -1) return entry.cat;
    }
  }
  return 'default';
}
/* 按 session 内消息数做种子（同一用户多次发送选不同句），pool 决定来源 */
var _CHAT_FALLBACK_COUNTER = 0;
function _chatFallbackLine(message) {
  _CHAT_FALLBACK_COUNTER++;
  var cat = _chatClassify(message);
  var pool = _CHAT_FALLBACK_BY_KW[cat] || _CHAT_FALLBACK_BY_KW.default;
  /* 「reading」类（看盘）走全 10 句轮换，不再偏置 default 4 句 */
  if (cat === 'reading' && _CHAT_FALLBACK_DEFAULT.length) {
    pool = _CHAT_FALLBACK_DEFAULT;
  }
  /* R2349g（R68-P1-4）：种子原来含消息长度——用户连发等长句时步进
   * 永远落同一格（实测等长 10 连发 uniq=1）。改为纯递增×素数。 */
  var idx = (_CHAT_FALLBACK_COUNTER * 7) % pool.length;
  var line = pool[idx];
  /* R3145：降级不空手——手里有新鲜结果卡（30min 内）时把卡面最要紧
   * 的一句捎上。LLM 挂了用户照拿判词/处方，不是只有「打烊啦」。 */
  try {
    var _best = null, _bv = '';
    for (var _vk in LAST_RESULT) {
      var _r = LAST_RESULT[_vk];
      if (_r && _r.ts && (Date.now() - _r.ts) < 1800000 &&
          (!_best || _r.ts > _best.ts)) { _best = _r; _bv = _vk; }
    }
    var _rl = _best && _best.json &&
      ((_best.json.warm && _best.json.warm.reply) || _best.json.lines);
    if (_rl && _rl.length) {
      var _pick = '';
      for (var _i = 0; _i < _rl.length; _i++) {
        var _l = _rl[_i];
        if (_l.indexOf('判词') !== -1 || _l.indexOf('处方') !== -1 ||
            _l.indexOf('先做') !== -1 || _l.indexOf('先想') !== -1 ||
            _l.indexOf('最实一步') !== -1 || _l.indexOf('观察信号') !== -1) {
          _pick = _l; break;
        }
      }
      if (!_pick) _pick = _rl[0];
      _pick = String(_pick).slice(0, 60);
      if (_pick) line += '，你那张卡上有句现成的：「' + _pick +
        (_pick.length >= 60 ? '…' : '') + '」回头细拆给你听。';
    }
  } catch (e) { /* 降级路径不许再抛——静默拿原句 */ }
  return line;
}

/** R207b：起名点评轮询——复用 /api/ai/{tid}，done 渲染点评卡。 */
/* R230d（R16-P3-3）：终态时把 nameReviewBtn 解灰——此前按钮在点击后
 * 永久 disabled，点评成功后想换换说法再点一次都没门（只能靠整卡重绘）。 */
function _nameReviewDone() {
  var b = el('nameReviewBtn');
  if (b) b.disabled = false;
}
var _NR_GEN = 0;   /* R230v（R34-#2）：点评任务代际——旧任务落地不得
 * 写进新一批名字的点评容器（nameReviewOut 是同 id 复用的）。 */
/* R3242：点评等待轮换池——推理模型首包 ~20-40s，一句静态文案
 * 看两遍就又是干等；轮询 tick 换一句（同 _WAIT_NOTES 机制）。 */
var _NR_WAIT_NOTES = ['AI 正在翻书找典故…', '在《诗经》里找合适的句子…',
  '翻到《楚辞》这一页了…', '在掂量哪个名字最亮眼…',
  '快写好了，在挑措词…', '小满在比对五行和出处…'];
/* R3244（用户实测·保底）：点评不再全靠 AI——点击立刻用候选名
 * 自带的 origin/story/elements 渲「典故先读」确定性卡；AI 故事版
 * 写好追加在下面，全链挂了典故卡仍在（功能永不为空）。 */
function _nrDeterministic(j) {
  var fe = j.five_elements || {};
  var _miss = fe.missing || [], _weak = fe.weak || [];
  var _rows = (j.full_names || []).slice(0, 6).map(function (n) {
    var _els = n.elements || [];
    var _hitM = _els.filter(function (e) { return _miss.indexOf(e) >= 0; });
    var _hitW = _els.filter(function (e) { return _weak.indexOf(e) >= 0; });
    var _fit = _hitM.length ? '补「' + _hitM.join('') + '」缺口'
             : (_hitW.length ? '扶「' + _hitW.join('') + '」偏弱' : '五行中性点缀');
    return '<div class="nr-line"><div class="nr-head"><b>' + esc(n.full_name) + '</b>' +
      (_els.length ? '<span class="nr-wx">' + esc(_els.join('')) + '</span>' : '') +
      '<span class="nr-fit">' + esc(_fit) + '</span></div>' +
      (n.origin ? '<div class="nr-src">📖 ' + esc(n.origin) + '</div>' : '') +
      (n.story ? '<div class="nr-story">' + esc(n.story) + '</div>' : '') +
      '</div>';
  }).join('');
  if (!_rows) return '';
  return '<div class="nr-card"><h4>📜 典故先读</h4>' + _rows + '</div>';
}
/* R3243（用户实测）：点评失败/超时此前是死胡同文案——「再试一次？」
 * 连个按钮都没有。统一挂行内重试键，点了等于再按一次点评钮。 */
function _nrRetryable(out, msg) {
  if (!out) return;
  out.hidden = false;
  out.innerHTML = '<div class="no-evidence">' + esc(msg) +
    ' <button type="button" class="nr-retry">再试一次</button></div>';
  var _rb = out.querySelector('.nr-retry');
  if (_rb) _rb.addEventListener('click', function () {
    var _b = el('nameReviewBtn');
    if (_b && !_b.disabled) _b.click();
  });
}
function pollNameReview(taskId) {
  var _gen = _NR_GEN;
  var deadline = performance.now() + NR_POLL_CAP_S * 1000;   /* R3245：点评独立预算 78s——通用 62s 帽会在链跑完前判死 */
  var _wait = AI_POLL_INTERVAL_MS;    /* R230t（R32-P2-20）：退避轮询 */
  var _nri = 0;
  var tick = function () {
    if (_gen !== _NR_GEN) { _nameReviewDone(); return; }   /* 新点评接管 */
    /* R3244：AI 段落写进 #nrAiOut——点击时已先渲确定性「典故先读」
     * 卡，AI 成功在下面追加故事版、挂了留底卡+重试钮。nrAiOut 缺失
     * （旧路径/重画）时退回 nameReviewOut 本身。 */
    var _nrTgt = function () {
      return el('nrAiOut') || el('nameReviewOut');
    };
    var _nrw = _nrTgt();
    if (_nrw && _nrw.querySelector('.no-evidence')) {
      _nrw.querySelector('.no-evidence').textContent =
        _NR_WAIT_NOTES[(++_nri) % _NR_WAIT_NOTES.length];
    }
    if (_aiPollGate()) {   /* R230q（R28-P3-8）：后台/断网暂停取数 */
      if (performance.now() < deadline) setTimeout(tick, 2000);
      else { _nrRetryable(_nrTgt(), '等太久啦，这趟没等到'); _nameReviewDone(); }
      return;
    }
    api('/api/ai/' + encodeURIComponent(taskId), { silent: true }).then(function (st) {
      const out = _nrTgt();
      if (!out || _gen !== _NR_GEN) { _nameReviewDone(); return; }
      /* R2512：口吻切换重画后容器可能是新节点——写入前显式翻开。 */
      var _outP = el('nameReviewOut'); if (_outP) _outP.hidden = false;
      if (st && st.status === 'done' && st.text) {
        /* R3241：点评同样逐字蹦——先纯文本打字，终态换富文本。
         * R3244：写进 nrAiOut，典故先读卡之下追加故事版。 */
        out.innerHTML = '<div class="tarot-deep"><h4>✨ AI 故事版</h4>' +
          '<p style="white-space:pre-wrap;" class="nr-text"></p></div>';
        var _nrp = out.querySelector('.nr-text');
        typewriteInto(_nrp, st.text, function () {
          if (_nrp) _nrp.innerHTML = renderRichText(st.text);
        });
        _nameReviewDone();
        return;
      }
      if (st && st.status === 'failed') {
        _nrRetryable(out, '故事版这次没写出来');
        _nameReviewDone();
        return;
      }
      if (performance.now() < deadline) { setTimeout(tick, _wait); _wait = _aiBackoff(_wait); }
      else { _nrRetryable(out, '等太久啦，这趟没等到'); _nameReviewDone(); }
    }).catch(function (e) {
      /* R228c：同上——瞬时抖动不该杀死轮询。R8 P2-9：404 早退。 */
      var out2 = _nrTgt();
      if (e && e.status === 404) {
        _nrRetryable(out2, '故事版这次没写出来');
        _nameReviewDone();
        return;
      }
      if (performance.now() < deadline) { setTimeout(tick, _wait); _wait = _aiBackoff(_wait); }
      else { _nrRetryable(out2, '等太久啦，这趟没等到'); _nameReviewDone(); }
    });
  };
  setTimeout(tick, AI_POLL_INTERVAL_MS);
}

/* R228h：Safari<15.5 / 旧 Edge 不认识 inert——设上只是 expando，Tab 仍穿透。
 * 降级：不支持时给栏内可点控件打 tabIndex=-1（开栏恢复）。chatOpen 与
 * _setRecent 两条开栏路径共用。 */
var _NO_INERT = !('inert' in HTMLElement.prototype);
function sbFocusable(sb, enable) {
  if (!_NO_INERT || !sb) return;
  sb.querySelectorAll('button, a[href], input, [tabindex]').forEach(function (c) {
    if (enable) { c.removeAttribute('tabindex'); }
    else { c.setAttribute('tabindex', '-1'); }
  });
}
/* R228n：侧栏打开时主区 inert——原来遮罩只挡鼠标，Tab 能穿透到
 * 被盖住的控件（in_modal=false 实测落到 .checkin-opt）。 */
function _mainInert(on, except) {
  var w = document.querySelector('.wrap');
  if (w) { w.inert = on; if (_NO_INERT) sbFocusable(w, !on); }
  /* R233f（R43-P2-9）：.wrap 之外的 body 级浮件（skip-link/welcomeBar/
   * install-tip）此前侧栏/模态开着仍可 Tab 到且被遮罩盖住。除侧栏
   * 三件套（自己管理 inert）与当前模态（except）外统一打 inert。 */
  /* R2349h（R69-P2-10）：except=模态遮罩时（模态在侧栏之上），
   * 侧栏三件套也要入 inert——否则 SR 浏览模式仍能在模态下层
   * 导航/点开侧栏入口。仅纯侧栏开合（无 except）才豁免。 */
  var _keep = except ? {} : { recentToggle: 1, recentBackdrop: 1, recentSidebar: 1 };
  Array.prototype.forEach.call(document.body.children, function (n) {
    if (n === w || n === except || n.nodeType !== 1) return;
    if (n.id && _keep[n.id]) return;
    if (n.classList && n.classList.contains('page-glow')) return;
    n.inert = on;
    if (_NO_INERT) sbFocusable(n, !on);
  });
}

/* R209b：聊天并入左侧统一栏——打开聊天=打开侧栏并滚到聊天段。 */
function chatOpen() {
  var sb = el('recentSidebar');
  if (!sb) return;
  sb.classList.add('open');
  /* R228d：chatOpen 与 _setRecent 都能拉开侧栏——inert/aria 同步复位 */
  sb.inert = false;
  sbFocusable(sb, true);
  sb.setAttribute('aria-hidden', 'false');
  _mainInert(true);
  /* D-006：每次打开侧栏重置发送计数，允许新一轮「自动发+1次追问」
   * R228c：计数归零但输入框/按钮的 disabled 不复位，重开仍锁死到刷新——
   * 一起解开才对得上「允许新一轮」的语义。 */
  _CHAT_SEND_COUNT = 0;
  var _inp0 = el('chatInput'), _sb0 = el('chatSendBtn');
  if (_inp0) { _inp0.disabled = false; _inp0.placeholder = '说说你的心情…'; }
  if (_sb0) _sb0.disabled = false;
  /* R218a-01：拉起半透遮罩，挡住主区可点以触发「点空白处关闭」——视觉上
   * 仍透出主区颜色信息（rgba .18）。 */
  var bd = el('recentBackdrop');
  if (bd) bd.classList.add('open');
  chatEmptyGuide();   /* R212：空状态引导 */
  var tgl = el('recentToggle');
  if (tgl) tgl.setAttribute('aria-expanded', 'true');
  var flow = el('chatFlow');
  /* R3204：键盘态残留复位——上次 vv 收缩留下的 sb.style.bottom
   * 不随开栏自动清。 */
  sb.style.bottom = '';
  if (flow) setTimeout(function () {
    flow.scrollTop = flow.scrollHeight;
    var inp = el('chatInput');
    /* R3204：平板/触屏不自动 focus——820px 宽平板过 767 闸，
     * 开栏即弹键盘把刚拉开的侧栏又顶上去（用户实测痛点）。
     * 触屏设备输入由用户主动点输入框唤起。 */
    var _coarse = window.matchMedia &&
      window.matchMedia('(pointer: coarse)').matches;
    if (inp && window.innerWidth > 767 && !_coarse) inp.focus();
  }, 300);
}

function chatEmptyGuide() {
  /* R212：空状态引导——抽屉打开时不再是一片空白。 */
  var flow = el('chatFlow');
  if (!flow || flow.children.length) return;
  /* R228c：静态 #chatEmpty（index.html）还在就别再注第二份同 id 节点 */
  if (document.querySelector('.chat-empty')) return;
  var d = document.createElement('div');
  d.className = 'chat-empty';   /* R228c：不再抢 id——双份 #chatEmpty 会串 */
  var im = document.createElement('img');
  im.src = '/static/shared/icon-set-moon-cat.jpg';
  im.alt = '';
  im.className = 'chat-empty-img';
  d.appendChild(im);
  var t = document.createElement('p');
  /* R3120（specs/011）：空态个性化——存过档案的老客用名字招呼
   * （transcript 有存根时 restore 已渲气泡、本函数根本不会进；
   * 这里接住的是「开新话题」后的真空态）。 */
  var _who = '宝';
  try {
    var _me = _meGet('me');
    var _nick = _me ? _meNickClean(_me.n) : '';
    if (_nick) _who = _nick;
  } catch (e) {}
  t.textContent = '我是小满，解忧铺的店员。\n' + _who +
    '最近有什么心事，都可以跟我说说，\n仅供陪伴，不构成任何建议。';
  d.appendChild(t);
  flow.appendChild(d);
}
function chatBubble(role, text, opts) {
  var flow = el('chatFlow');
  if (!flow) return null;
  /* R228c：清掉所有空态块（静态 #chatEmpty + JS 注入的 .chat-empty）——
   * 原来只删 getElementById 第一个，注入那份会残留夹在气泡之间。
   * R3336（审-中）：空态里的工具块（小确幸/事实板/创可贴钮）聊过天
   * 被连带删=聊完即不可达——移栽进输入区上方的持久工具位。 */
  document.querySelectorAll('.chat-empty').forEach(function (n) {
    var _sc = document.querySelector('.side-chat');
    var _ir = _sc && _sc.querySelector('.chat-input-row');
    if (_sc && _ir) {
      ['.chat-journal', '.chat-facts', '.chat-empty-bandaid']
        .forEach(function (sel) {
          var _tn = n.querySelector(sel);
          if (_tn) _sc.insertBefore(_tn, _ir);
        });
    }
    n.remove();
  });
  var div = document.createElement('div');
  div.className = 'chat-bubble chat-' + role;
  /* R228c：raw 只能由内部调用点显式声明（打字动效）。原写法嗅探文本里
   * 是否含 'chat-typing' 子串——用户消息自带这串字就绕过 esc 裸插
   * innerHTML（自注入面）。用户/后端文本一律 renderRichText（先 esc）。 */
  if (opts && opts.raw) div.innerHTML = text;
  /* R230a-6（R12-P3-9）：用户自己发的气泡不跑富文本——「3*5」「2*面霜*」
   * 会被单 * 规则误渲成斜体。用户输入没有 markdown 语义，textContent 即净。 */
  else if (role === 'me') div.textContent = text;
  else div.innerHTML = renderRichText(text);   /* v3 P5：markdown 渲染 */
  flow.appendChild(div);
  /* R230q（R28-P2-4）：transcript 持久化——raw 占位（打字动效）不存，
   * nosave 为恢复重渲路径。终态写回处（_ty.innerHTML 直写点）各自补存。 */
  if (!opts || (!opts.nosave && !opts.raw)) _chatTsSave(role, text);
  /* R230j（R22-P3-3）：气泡无上限 DOM 只涨不裁——保留最近 50 条，
   * 更早的摘掉（与 R228j records 滚动裁剪同一思路）。 */
  while (flow.children.length > 50) flow.removeChild(flow.firstChild);
  /* R2522（审-P2-1）：scrollTop=scrollHeight 是「写后读」强排——恢复
   * transcript 时泡循环里每条触发一次同步回流（50 条=50 次）。noscroll
   * 让批量路径跳过，循环结束统一滚一次。 */
  if (!opts || !opts.noscroll) flow.scrollTop = flow.scrollHeight;
  return div;   /* 轮询写回用节点引用，不赌 lastChild */
}
/* R233r（R49-P0）：危机词前端镜像——后端 _CRISIS_PAT 只在任务真起
 * 时才跑得着；DISABLE/限流/排队满时 spawn 返回 None，此前危机会被
 * _chatFallbackLine 卖萌句吞掉。本地镜像词表+转介文案，不发请求。 */
/* R2995（巡#412）：与后端 _FACT_T2S 同源——危机/敏感判定先
 * 繁折简+剥零宽（自殺/腫瘤/強吻/輕生接住，不拿占卜腔）。 */
var _T2S_FE = (function () {
  var _s = '曆歷體從規詞獄視設輸譯語說聽確給讓該當檔稱講讀寫開關閉啟' +
    '這個們為與屬統權數據歲樣點條順嚴厲師專級員責評價處務態實認詳' +
    '後喚執調試頁碼憑記錄監斷決變論訴訊誤導遺攜帶類別應擬偽裝竊臺' +
    '賬號密鑰証訪終腳進環目徑內刪擇縮復塗館鷄鴨鵝鶴' +
    '殺輕樓鬱燒藥腫絕臨強姦褻騷擾蹤脅嚇毆動繼練東機網領脫壓襠發' +
    '飛牆餃湯圓凍樂蘋麥莊蘿蔔紙膠紀聞劇電綜藝遊戲車軟遞愛課題業' +
    '書頻寵貓鳥魚蟲烏龜倉學戀氣飯覺妝髮膚話醫傷殘會嗎妳還對脈診' +
    '術療極時風腎過膩厭複';
  var _d = '历历体从规词狱视设输译语说听确给让该当档称讲读写关关闭启' +
    '这个们为与属统权数据岁样点条顺严厉师专级员责评价处务态实认详' +
    '后唤执调试页码凭记录监断决变论讯讯误导遗携带类别应拟伪装窃台' +
    '账号密钥证访终脚进环目径内删择缩复涂馆鸡鸭鹅鹤' +
    '杀轻楼郁烧药肿绝临强奸亵骚扰踪胁吓殴动继练东机网领脱压裆发' +
    '飞墙饺汤圆冻乐苹麦庄萝卜纸胶纪闻剧电综艺游戏车软递爱课题业' +
    '书频宠猫鸟鱼虫乌龟仓学恋气饭觉妆发肤话医伤残会吗你还对脉诊' +
    '术疗极时风肾过腻厌复';
  var m = {}, i;
  for (i = 0; i < _s.length; i++) m[_s[i]] = _d[i];
  return m;
})();
function _normFE(s) {
  s = String(s || '').replace(
    /[\u200b-\u200f\u202a-\u202e\u2066-\u2069\u061c\ufeff]/g, '');
  var r = '', i;
  for (i = 0; i < s.length; i++) r += _T2S_FE[s[i]] || s[i];
  return r;
}
/* R3066（巡#483）：词内插符/拼音混写绕闸前端镜像——与后端
 * _norm_cs_flat 同构：变调归 ascii→剥全部非字词符→拼音折叠
 * （折叠进既有词表，想si你=想死你同享人称豁免）。判定专用。 */
var _TONE_FE = (function () {
  var m = {}, i,
      src = 'āáǎàēéěèīíǐìōóǒòūúǔùǖǘǚǜü',
      dst = 'aaaaeeeeiiiioooouuuuuuuuu';
  for (i = 0; i < src.length; i++) m[src[i]] = dst[i];
  return m;
})();
var _FLAT_RE_FE = /[^0-9a-zA-Z\u4e00-\u9fff]/g;
/* 字母边界用 (^|[^a-z])+$1 代 lookbehind（同 ICU 锚——老 Safari
 * 对含 lookbehind 的正则字面量整文件 SyntaxError）。 */
var _PINYIN_FOLD_FE = [
  [/(^|[^a-z])zisha(?![a-z])/gi, '$1自杀'],
  [/(^|[^a-z])zi杀(?![a-z])/g, '$1自杀'],
  [/(^|[^a-z])gewan(?![a-z])/gi, '$1割腕'],
  [/([想要])si(?![a-z])/gi, '$1死'],
  [/不想huo(?![a-z])/gi, '不想活'],
  [/huo[着著]?不下去/gi, '活不下去'],
  [/huo[着著]好累/gi, '活着好累'],
  [/跳lou(?![a-z])/gi, '跳楼'],
  [/(^|[^a-z])saorao(?![a-z])/gi, '$1性骚扰'],
  [/(^|[^a-z])wexie(?![a-z])/gi, '$1猥亵'],
  [/(^|[^a-z])qj(?![a-z])/gi, '$1强奸']
];
function _normFEFlat(s) {
  s = _normFE(s).toLowerCase();
  var r = '', i;
  for (i = 0; i < s.length; i++) r += _TONE_FE[s[i]] || s[i];
  s = r.replace(_FLAT_RE_FE, '');
  for (i = 0; i < _PINYIN_FOLD_FE.length; i++) {
    s = s.replace(_PINYIN_FOLD_FE[i][0], _PINYIN_FOLD_FE[i][1]);
  }
  return s;
}
var _CRISIS_FE_HARD = new RegExp(
  '不想活|想死|自杀|自残|伤害自己|想不开|轻生|跳楼|抑郁|厌世|' +
  '活不下去|活[着著]好累|想消失|不想在了|烧炭|割腕|跳河|上吊|安眠药|' +
  'suicide|kill\\s*myself|end\\s*it', 'i');
/* R2400（R126-P1-5）：与后端 _CRISIS_SOFT/OBJ_PAT + _is_crisis 同构——
 * 软词（死了算了类）按分句判，分句带物件词豁免（「电脑死了算了」）。 */
/* R2994（巡#411）：与后端 _CRISIS_SOFT/OBJ_PAT 逐字同源——此前漏同
 * R2991/R2992 新词且 OBJ 缺整行生活域（工作|日子…），「这工作没啥
 * 意思」前端误发 12356。软词量词服药/消失换序/持刀对体/割自己、
 * 物件玩耍+食物+农务+影视族全部补齐。 */
var _CRISIS_FE_SOFT = new RegExp(
  '活着.{0,3}没意思|死了算了|一了百了|活腻|没啥意思|没什么意思|跳下|' +
  '(吞|吃|咽|灌).{0,4}(整瓶|一把|一板|几十|三十|四十|五十|好多|很多|全部|所有)|' +
  '世界.{0,4}消失|消失.{0,4}世界|拿刀.{0,4}(手|腕|脖|喉|脉)|割自己|' +
  /* R2996：农药名+诗意意念形，与后端同步。 */
  '敌敌畏|百草枯|喝.{0,3}毒药|去.{0,3}(天台|楼顶|桥).{0,4}算了|' +
  '(楼顶|天台|桥).{0,3}边缘|' +
  /* R3066：谐音/黑话形与后端同步（必带语气后缀防壶/局误伤）。 */
  '想紫砂[了啦吧]|想重开[了啦吧]', 'i');
var _CRISIS_FE_OBJ = new RegExp(
  '电脑|手机|剧|综艺|游戏|网|车|机器|电池|冰箱|代码|程序|软件|文件|' +
  '快递|外卖|爱豆|偶像|交通|航班|火车|课|班|题|作业|考试|' +
  '书|小说|电影|片子|番|漫|视频|纪录片|纪录|' +
  '多肉|植物|宠物|猫|狗|鸟|鱼|花|虫|乌龟|仓鼠|基金|股票|痘|拖延|懒|' +
  '工作|日子|生活|婚姻|人生|学业|感情|事业|恋爱|爱情|' +
  '周|月|年|天气|饭|觉|歌|舞|妆|穿搭|发型|指甲|皮肤|身材|' +
  '舞台|蹦极|秋千|坡|台阶|床|桌|凳|沙发|飞机|公交|马|滑板|矮墙|' +
  '葡萄|饺子|汤圆|果冻|可乐|苹果|麦子|稻|韭菜|庄稼|萝卜|西瓜|水果|纸|胶带|' +
  '除草|菜地|农田|果园|打药|杀虫', 'i');
function feCrisis(s) {
  s = _normFE(s);   /* R2995：剥零宽+繁折简，与后端 _norm_cs 同构 */
  /* R2994：想死+人称代词撒娇豁免——此前裸 test() 命中即危机，
   * 「想死你了宝贝」前端发 12356 而后端放行，与 _is_crisis 同构补齐。
   * R3066：硬词改判压平形态——「自.杀」「zi sha」插符/拼音混写
   * 不再绕闸；想si→想死折叠后同享人称豁免。 */
  var _seg = _normFEFlat(s), _hm, _rest;
  while ((_hm = _seg.match(_CRISIS_FE_HARD))) {
    _rest = _seg.slice(_hm.index + _hm[0].length);
    if (!(_hm[0] === '想死' &&
          /^([你他她](了|啦)?|我了|我啦)/.test(_rest.slice(0, 2)))) {
      return true;
    }
    _seg = _rest;
  }
  /* R3066：软词仍先句界切分（保物件豁免：物件与现象不同句）
   * 但每句压平+相邻两片并查——「死了.算了」切三片后并查仍命中；
   * 「电脑死了.算了」第二片「算了」无词、并片「死了算了」吃物件
   * 词豁免，原语义逐字保住。 */
  var segs = s.split(/[，。！？；,.!?\n;~～…]+/).map(_normFEFlat);
  for (var i = 0; i < segs.length; i++) {
    if (_CRISIS_FE_SOFT.test(segs[i]) && !_CRISIS_FE_OBJ.test(segs[i])) {
      return true;
    }
    if (i + 1 < segs.length) {
      var j = segs[i] + segs[i + 1];
      if (_CRISIS_FE_SOFT.test(j) && !_CRISIS_FE_OBJ.test(j)) {
        return true;
      }
    }
  }
  return false;
}
/* R3346（审-P2）：与后端 _CHAT_REFUSAL 逐字同源——前端罐头此前少
 * 「先抱抱你」开头，比后端冷一档。改后端文案要同步这里。 */
var _CRISIS_FE_REPLY = '听到这些先抱抱你——这个话题有点重，我不太敢乱说。' +
  '如果心里真的很难受，' +
  '全国心理援助热线 12356（24 小时，免费）随时能打通，跟信任的朋友聊聊' +
  '也会好一些，我一直都在，陪你聊聊别的也行。';

/* R2349q（R81-P0-1）：生死/重病敏感词前端镜像——词表与后端
 * llm_polish._SENSITIVE_HARD/SOFT/EXCLUDE 逐字同源（改后端表要同步改这里）。
 * 塔罗/六爻 hook 命中时换转介文案，不给方向性指引。 */
/* R2994（巡#411）：与后端敏感三表逐字同源——自 R2939 家暴族起就没
 * 同步过。ICU 在 FE 用 (^|[^a-z]) 锚代 lookbehind（老 Safari 对含
 * lookbehind 的正则字面量整文件 SyntaxError）。 */
var _SENSITIVE_FE_HARD = new RegExp(
  '绝症|癌症|病危|临终|会不会去世|会去世|存活率|病死|' +
  '癌.{0,4}晚期|晚期.{0,4}癌|' +
  '家暴|家庭暴力|殴打|虐待我|校园暴力|性骚扰|动手打我|猥亵我|' +
  '被.{0,2}(虐待|强奸|性侵|猥亵|侵犯|强吻|迷奸|下药|胁迫|勒索|恐吓|威胁)|' +
  '强吻我|勒索我|恐吓我|威胁我|' +
  /* R2996：被下了药插字形 + 囚禁/裸照族。 */
  '被.{0,2}下.{0,2}药|囚禁|非法拘禁|裸照|私密(照|视频|录像)|艳照', 'i');
var _SENSITIVE_FE_SOFT = new RegExp(
  '还能活|活多久|会不会死|会死吗|要死了|晚期|治得好吗|寿命|肿瘤|打我|霸凌|跟踪|' +
  '白血病|尿毒症|心梗|脑梗|中风|脑溢血|化疗|透析|洗肾|' +
  '(^|[^a-z])ICU([^a-z]|$)|' +
  '重症监护|急救室|病危通知书|器官移植|骨髓移植|截肢|' +
  '肝硬化|肾衰竭|心衰|被灌醉|' +
  '(被摸|摸我|摸我的|摸过).{0,3}(大腿|胸|腰|屁股|臀部|私处|下面|裆)|摸过我|' +
  '(继父|干爹|老师|教练|上司|老板|客户|教官|师父|房东|司机|前夫|网友|领导)' +
  '.{0,8}(摸我|摸过|侵犯|猥亵|强吻|睡我|上我|脱我|压我)|' +
  /* R2996：强迫/动手动脚/sextortion/家暴/PUA 五族，与后端同构。 */
  '动手动脚|咸猪手|' +
  '(强迫|逼迫|被逼|被迫).{0,6}(发生关系|那种事|这种事|献身|脱.{0,2}衣|陪睡|上床)|' +
  '逼我.{0,4}(脱|睡|上床|陪|献身|发生)|' +
  '威胁.{0,4}(照片|视频|录像|曝光|群发|发我|发出去|隐私|图)|' +
  '被.{0,3}(拍|录).{0,4}(照片|视频|录像|隐私|裸|私)|' +
  '掐.{0,2}脖|扇.{0,3}(耳光|巴掌)|被.{0,2}控制|PUA|' +
  '被.{0,3}(爸|妈|爹|父母|老公|丈夫|男友|男朋友|前夫|老婆|妻子|对象|伴侣|室友|同学|同事|领导|老师|继母|公婆|婆婆|岳母)' +
  '.{0,1}(打(?!call|电话|游戏|卡|球|牌|车|字|折|喷|呼|枪|拳|麻|工|听|赌|扮|扫|算|瞌|蚊|鼓|针|饭|水)|揍|扇|掐|踹|踢|抽|砸)|' +
  '被.{0,3}(爸|妈|爹|父母|老公|丈夫|男友|男朋友|前夫|老婆|妻子|对象|伴侣|室友|同学|同事|领导|老师|继母|公婆|婆婆|岳母)' +
  '.{0,4}(打我|打他|打她|关起来|锁.{0,2}我|扒.{0,2}我|掐.{0,3}脖|扇.{0,3}(耳光|巴掌))|' +
  '被按.{0,4}(打(?!call|电话|游戏|卡|球|牌|车|字|折|喷|呼|枪|拳|麻|工|听|赌|扮|扫|算|瞌|蚊|鼓|针|饭|水)|揍|掐|扇|踹|踢|抽|砸)|' +
  /* R3071：求医问药选药问法与后端同步——「该吃什么药/布洛芬
   * 有用吗」不该拿占卜腔建议；陈述形（刚吃了退烧药）不收。 */
  '(什么|哪种|哪个|哪款|啥)药|药.{0,4}(推荐|管用|有用|好使|副作用|哪种好|怎么选|怎么买)|' +
  '(布洛芬|对乙酰氨基酚|阿司匹林|抗生素|避孕药|止痛药|退烧药|安眠药|降压药|降糖药|胰岛素|头孢|蒙脱石散|奥美拉唑)' +
  '.{0,8}(有用吗|管用|好吗|行吗|可以|能不能|要不要|副作用|伤.{0,2}身|怎么吃|怎么选|哪种)', 'i');
var _SENSITIVE_FE_EXC = new RegExp(
  '多肉|植物|宠物|猫|狗|鸟|鱼|花|虫|乌龟|仓鼠|手机|电池|电脑|游戏|' +
  '痘|拖延|懒|基金|股票|冰箱|车|' +
  '电话|账号|物流|快递|外卖|新闻|剧情|纪录片|电影|电视剧|小说|歌词', 'i');
function feSensitive(s) {
  /* R3066：同 feCrisis——硬/软/豁免三表全改判压平形态，
   * 「被猥.亵」「被qj了」不再绕闸（豁免词条同样在压平面生效）。 */
  s = _normFEFlat(s);
  return _SENSITIVE_FE_HARD.test(s) ||
    (_SENSITIVE_FE_SOFT.test(s) && !_SENSITIVE_FE_EXC.test(s));
}
var _SENSITIVE_FE_LINE = '这个话题牌面真接不了，不是不愿意，是它不该靠占卜来定。' +
  '身体或心里难受的话，医生和信得过的人才是最该找的。想聊点别的，小满都在。';
/* R2996（巡#413）：chatSend 此前只查 feCrisis——敏感披露在
 * DISABLE/配置关闭（spawn→None）路径拿的是 _chatFallbackLine 卖萌
 * 兜底（R233r 修过的同一个洞，敏感到复犯）。本地接住+复用后端
 * _SENSITIVE_REPLY 文案，双路径逐字一致。 */
var _SENSITIVE_CHAT_REPLY = '这个话题我真接不了，不是不愿意，是它不该靠占卜来定。' +
  '身体或心里难受的话，医生和信得过的人才是最该找的。想聊点别的，小满都在。';

/* R233r（R49-Top5-2）：chatSend 兜底 facts——不走排盘直接开聊时
 * CHAT_LAST_FACTS 恒空；按当前活跃视图从 LAST_RESULT 拼坐标。 */
var _CHAT_CTX_REF = '';   /* R3124b：与最近解出的上下文配套的结果 ref */
function _activeViewFacts() {
  var v = document.querySelector('.view.active');
  var vid = v ? v.id : '', key = '';
  ['taohua', 'tarot', 'liuyao', 'hehun', 'huangli', 'qiming', 'xingzuo',
   'bazi', 'dream'].forEach(function (k) {
    if (!key && vid.indexOf(k) !== -1) key = k;
  });
  if (!key) key = 'daily';   /* 首页无 .view 壳——daily 卡上下文兜底 */
  var c = buildChatContext(key);
  var _f = (c && c.facts) || [];
  _CHAT_CTX_REF = (c && c.ref) || '';
  /* R3115（specs/011 P1-3）：跨视图连续感——当前视图没测过盘时，
   * 扫描本会话 lastResult:* 里最近一次他类测算，带「她上次测过X」
   * 语境行；换视图/换天再聊，小满手里不至于从零开始。 */
  if (!_f.length) {
    try {
      var _LBL = { bazi: '命盘', taohua: '桃花', hehun: '合婚',
                   tarot: '塔罗', liuyao: '六爻', qiming: '起名',
                   dream: '解梦' };
      for (var i = 0; i < sessionStorage.length; i++) {
        var _k = sessionStorage.key(i);
        if (!_k || _k.indexOf('lastResult:') !== 0) continue;
        var _vk = _k.slice(11);
        if (_vk === key || !_LBL[_vk]) continue;
        var _c2 = buildChatContext(_vk);
        var _f2 = (_c2 && _c2.facts) || [];
        if (_f2.length) {
          _f = ['她之前在' + _LBL[_vk] + '测过一次，当时的事实：']
            .concat(_f2);
          _CHAT_CTX_REF = (_c2 && _c2.ref) || '';   /* 跨视图的 ref 也跟随 */
          break;
        }
      }
    } catch (e) {}
  }
  return _f;
}

/* R2343（R59-gap2）：昵称此前不进请求体，小满永远不喊名字——
 * 发送时现读 me.n（改完昵称下一轮即生效，不等刷新）。 */
/* R2345（R61-P1-1/P1-4）：昵称是「她叫X」事实行的投递通道——
 * localStorage 直写绕过 maxlength=12，可把指令句/超长文本灌进
 * LLM 上下文，甚至把 /api/chat 打出 400。收敛为纯称呼：只留
 * 中英文/数字/·_-，≤12 字。 */
function _meNickClean(n) {
  return String(n == null ? '' : n)
    .replace(/[^\u4e00-\u9fffA-Za-z0-9·_-]/g, '').slice(0, 12);
}

var CHAT_RESUME_FACT = '';   /* R3118：跨天续聊的一次性语境 */
/* R3139（specs/014-L1）：跨天主题画像——与 llm_polish._CHAT_THEME
 * 同口径的轻量前端镜像（子串命中即可，误伤代价低）。 */
var _CHAT_THEME_FE = {
  '感情': ['感情','恋爱','喜欢','桃花','对象','男朋友','女朋友','暗恋',
           '复合','相亲','结婚','暧昧','crush','他对我','分手','失恋','前任',
           '脱单','表白'],
  '工作': ['工作','职场','老板','同事','升职','跳槽','面试','裁员','加班',
           '试用期','转正','实习','兼职','简历','入职','离职'],
  '学业': ['学业','考试','考研','考公','成绩','论文','学校','读书','专业'],
  '财运': ['钱','财','工资','收入','投资','副业','存款','花销'],
  '人际': ['朋友','闺蜜','室友','家人','父母','社交','关系'],
  /* R3147：情绪/自我类——与服务端 _CHAT_THEME 同口径（emo/内耗/
   * 迷茫是 15-25 受众核心语汇）。 */
  '情绪': ['焦虑','迷茫','内耗','emo','难过','孤独','自卑','压力',
           '崩溃','失眠','容貌','减肥','自我','开心','不开心'],
  /* R3184：睡眠/梦主题——「梦见掉牙」此前不留足迹，画像就少
   * 「最近睡不好」这块拼图。不用裸「梦」字（「梦想」会误伤）。 */
  '睡眠': ['梦见','梦到','做梦','噩梦','昨晚梦','睡不着','睡不好',
           '睡眠','熬夜','睡醒'],
  '运势': ['运势','运气','今年','最近','大运','流年','水逆']
};
function _chatThemeFE(msg) {
  var s = String(msg || '');
  for (var k in _CHAT_THEME_FE) {
    var arr = _CHAT_THEME_FE[k];
    for (var i = 0; i < arr.length; i++) {
      if (s.indexOf(arr[i]) !== -1) return k;
    }
  }
  return '';
}
/* 足迹：{d:'YYYY-MM-DD', t:'主题', v:'面板'}，14 天滚动窗、60 条封顶。
 * v=发消息时手里正看着的结果卡面板（30min 内）——画像能说出
 * 「在合盘那边聊感情」而不只是「聊过感情」。危机/敏感消息不写
 * 足迹（在闸之后才调）。 */
/* R3260（实测挖出的旧账）：chat:topics 历史上存在两套 schema——
 * 旧写端存 {主题:日期} 对象，新写端 _chatTopicLog 存 [{d,t,v}]
 * 数组；两写端互相读不懂：对象写端往数组上设命名属性被
 * stringify 丢掉（静默丢记录），数组写端遇对象直接重置清空。
 * 归一读取器兼容两式，全部读写点收口到它。 */
function _chatTopicsArr() {
  try {
    var v = JSON.parse(localStorage.getItem('chat:topics') || '[]');
    if (Array.isArray(v)) return v;
    if (v && typeof v === 'object') {
      var out = [];
      Object.keys(v).forEach(function (k) {
        if (typeof v[k] === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v[k]))
          out.push({ d: v[k], t: k });
      });
      return out;
    }
  } catch (eA) {}
  return [];
}
function _chatTopicLog(msg) {
  var t = _chatThemeFE(msg);
  if (!t) return;
  try {
    var _vk0 = '';
    var _bt = 0;
    for (var _k in LAST_RESULT) {
      var _r0 = LAST_RESULT[_k];
      if (_r0 && _r0.ts && (Date.now() - _r0.ts) < 1800000 &&
          _r0.ts > _bt) { _bt = _r0.ts; _vk0 = _k; }
    }
    var arr = _chatTopicsArr();
    var today = todayIso();
    /* 同日同主题同面板不重复记——一天问感情五次仍是一条 */
    if (arr.length && arr[0].d === today && arr[0].t === t &&
        (arr[0].v || '') === _vk0) return;
    arr.unshift({ d: today, t: t, v: _vk0 || undefined });
    var cutoff = new Date(Date.now() - 14 * 864e5).toISOString().slice(0, 10);
    arr = arr.filter(function (x) {
      return x && x.d >= cutoff;
    }).slice(0, 60);
    /* R3306-P2：并集写——两 tab 同日各聊主题不互丢。 */
    _lsUnionWrite('chat:topics', arr,
      function (x) { return x && (x.d + '|' + x.t + '|' + (x.v || '')); }, 60);
  } catch (e) {}
}
/* R3260（UX-PLAN-R6→R7）：未闭合事件——「明天要面试」「周五谈薪」
 * 这类带时间落点的话头存本机（chat:events，cap 10），
 * 隔天开聊时空态问「怎么样了」。调研规则：>24h 才跟进、
 * 一天至多一次、同一事最多 2 次、用户回应或两次不接即停。
 * 全 localStorage，不出本机。 */
function _chatEventLog(msg) {
  try {
    var m = String(msg || '').match(
      /* R3307（审-低）：复查/手术/开庭属医疗法律高敏——跟进问候
       * 「那台手术怎么样了」本身就在复述隐私。移出捕获集。 */
      /(明天|后天|今晚|下午|周[一二三四五六日天末]|星期[一二三四五六日天]|下周[一二三四五六日天末]?|月底|年底|周末)(?:要|得|去|有|是|要?去)?([^，。！？!?,.、；;]{0,10}?)(面试|汇报|谈薪|谈话|考试|答辩|体检|搬家|出差|约会|表白|离职|入职|签约|复诊|看牙|看房|相亲|见家长|交稿|提案|述职|比赛|演出|开张|订婚|领证|出结果)/);
    if (!m) return;
    var key = (m[1] + (m[2] || '') + m[3]).slice(0, 16);
    var arr = JSON.parse(localStorage.getItem('chat:events') || '[]');
    if (!Array.isArray(arr)) arr = [];
    var dup = arr.some(function (x) {
      return x && x.k === key && (Date.now() - (x.ts || 0)) < 7 * 864e5;
    });
    if (dup) return;
    arr.unshift({ k: key, ts: Date.now(), d: todayIso(), asked: 0,
                  closed: 0 });
    /* R3306-P2：并集写——两 tab 各记一条话头不互丢。 */
    _lsUnionWrite('chat:events', arr, function (x) { return x && x.k; }, 10);
  } catch (e) {}
}
/* 画像行：近 7 天各主题计数，主打主题 ≥2 天才有「一直卡在这」
 * 的观测价值。一次会话只注入一回（sessionStorage 旗标）。 */
function _chatWeekProfileFact() {
  try {
    if (sessionStorage.getItem('chatTopicFactDone')) return '';
    sessionStorage.setItem('chatTopicFactDone', '1');
    var arr = _chatTopicsArr();
    if (!arr.length) return '';
    var cutoff = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
    var cnt = {};
    arr.forEach(function (x) {
      if (x && x.d >= cutoff && x.t) cnt[x.t] = (cnt[x.t] || 0) + 1;
    });
    var top = '', topN = 0;
    for (var k in cnt) { if (cnt[k] > topN) { top = k; topN = cnt[k]; } }
    if (!top || topN < 2) return '';
    /* R3149：主主题的主力面板——「在合盘那边聊感情」比裸主题更像
     * 真人记得。面板中文名与 R3071 区块的 _LBL 同源。 */
    var _VLBL = { bazi: '命盘', taohua: '桃花', hehun: '合婚',
                  tarot: '塔罗', liuyao: '六爻', qiming: '起名',
                  xingzuo: '星座', xzm: '合盘', daily: '日签',
                  huangli: '黄历', dream: '解梦' };
    var _vc = {};
    arr.forEach(function (x) {
      if (x && x.d >= cutoff && x.t === top && x.v && _VLBL[x.v]) {
        _vc[x.v] = (_vc[x.v] || 0) + 1;
      }
    });
    var _tv = '', _tvN = 0;
    for (var _vk2 in _vc) {
      if (_vc[_vk2] > _tvN) { _tv = _vk2; _tvN = _vc[_vk2]; }
    }
    return '她这周来聊过「' + top + '」这条线 ' + topN +
      ' 天了' + (_tv ? '（多在「' + _VLBL[_tv] + '」那边）' : '') +
      '，如果现在又绕回来，可以自然接一句「这事你惦记着几天了」' +
      '这种体恤，别点破数据';
  } catch (e) { return ''; }
}

/* R3153：判词短句提取——各面卡里最有辨识度的一行（判词行优先，
 * 没有就首行）。存进跨日记忆的就是屏上原句，小满复述不瞎编。 */
function _cardVerdictShort(viewKey, j) {
  try {
    var r = ((j || {}).warm || {}).reply || [];
    var line = r.filter(function (l) {
      return l.indexOf('判词') !== -1;
    })[0] || r[0] || '';
    if (viewKey === 'xzm') line = (j.lines || [])[0] || line;
    if (viewKey === 'tarot') {
      line = r.filter(function (l) {
        return l.indexOf('综合来看') !== -1 || l.indexOf('这组牌') !== -1;
      })[0] || line;
    }
    if (viewKey === 'qiming') {
      line = r.filter(function (l) {
        return l.indexOf('推荐') !== -1;
      })[0] || line;
    }
    return (line || '').slice(0, 60);
  } catch (e) { return ''; }
}
/* R3153：跨日卡片记忆行——近 7 天、今天之前的测卡（今天的走
 * result_ref/末结果上下文已经覆盖，重复注入只会挤窗口）。一次
 * 会话注入一回。 */
function _chatCardsFact() {
  try {
    if (sessionStorage.getItem('chatCardsFactDone')) return '';
    sessionStorage.setItem('chatCardsFactDone', '1');
    var arr = JSON.parse(localStorage.getItem('chat:cards') || '[]');
    if (!Array.isArray(arr) || !arr.length) return '';
    var today = todayIso();
    var cut = new Date(Date.now() - 7 * 864e5).toISOString().slice(0, 10);
    var _VL = { bazi: '命盘', taohua: '桃花', hehun: '合婚',
                tarot: '塔罗', liuyao: '六爻', qiming: '起名',
                xzm: '合盘', dream: '解梦' };
    var out = [];
    arr.forEach(function (x) {
      if (out.length >= 3) return;
      if (x && x.d && x.d < today && x.d >= cut && x.s) {
        out.push(x.d.slice(5) + (_VL[x.v] || '一张卡') +
                 (x.q ? '问「' + x.q + '」' : '') + '：' + x.s);
      }
    });
    if (!out.length) return '';
    return '她这几天测过的卡。' + out.join('；') +
      '。她若翻旧账能对上号；不相关别主动提';
  } catch (e) { return ''; }
}

/* R3313（审-P2-5）：TA 生辰注入闸——感情语境或受邀态才放行。 */
function _taFactRelevant(msg) {
  if (window.__hhInviteMode) return true;
  return /对象|男朋|女朋|男朋友|女朋友|感情|桃花|恋爱|暧昧|crush|CRUSH|老公|老婆|前任|现任|相亲|约会|结婚|离婚|分手|复合|喜欢|心动|合婚|配吗|缘分|伴侣|夫妻|另一半|我俩|我们俩|我们\b|TA|ta|他\b|她\b/i.test(String(msg || ''));
}
function _chatFacts(facts, msg) {
  var _f = (facts || []).slice();
  try {
    var _wp = _chatWeekProfileFact();
    if (_wp) _f.unshift(_wp);
  } catch (e) {}
  try {
    var _cf = _chatCardsFact();
    if (_cf) _f.unshift(_cf);
  } catch (e) {}
  try {
    /* R3118（specs/011 P3）：resume 槽一次性消费——只在新会话
     * 首条消息注入（服务端会话是新开的，不注入等于真失忆）。 */
    if (CHAT_RESUME_FACT) {
      _f.unshift('她上次来聊过：「' + CHAT_RESUME_FACT.slice(0, 60) +
                 '」，如果和现在的话题相关就自然接上，不相关不用硬提');
      CHAT_RESUME_FACT = '';
    }
    /* R3208：服务端失忆（重启/TTL 回收）后——transcript 尾巴当
     * 「前文回放」喂回去，小满能捡回大概（一次性消费）。 */
    if (_CHAT_NEED_RECAP) {
      _CHAT_NEED_RECAP = false;
      var _rc = _chatRecapFact();
      if (_rc) _f.unshift(_rc);
    }
  } catch (e) {}
  try {
    var _me = _meGet('me');
    var _n = _me ? _meNickClean(_me.n) : '';
    if (_n) _f.unshift('她叫' + _n + '，聊天时自然地喊她名字，别每句都喊');
    /* R3115（specs/011 P1-2）：me 档案进上下文——昵称之外，
     * 小满此前对「她是谁」零感知。生日行服务端确定性展开成
     * 日主/星座（chat_profile_facts）；只传公历（me 档全存公历）。 */
    if (_me && _me.g) _f.push('性别：' + _me.g);
    if (_me && _me.y && _me.m && _me.d) {
      var _mm = ('0' + _me.m).slice(-2), _dd = ('0' + _me.d).slice(-2);
      _f.push('生日：' + _me.y + '-' + _mm + '-' + _dd);
    }
    /* R3126（specs/013-P2）：partner 档案进上下文——合婚留下的
     * me:partner 此前只有合婚页自己用；聊「他/TA」时小满手里得有
     * TA 的坐标。服务端把生日确定性展开成 TA 的日主/星座。 */
    /* R3313（审-P2-5）：TA 生辰只在该有的话题里给——问事业也把
     * TA 生日+昵称发给第三方 LLM 网关属于过曝。话题沾感情/合婚
     * 语境（或邀请态本身就是来看俩人的）才带 TA 坐标。 */
    var _p = _meGet('me:partner');
    if (_p && _p.y && _p.m && _p.d && _taFactRelevant(msg)) {
      var _pm = ('0' + _p.m).slice(-2), _pd = ('0' + _p.d).slice(-2);
      _f.push('TA的生日：' + _p.y + '-' + _pm + '-' + _pd +
              (_p.n ? '（' + _meNickClean(_p.n) + '）' : ''));
    }
    /* R3352（审-高）：心情话题带近 7 天本机心情记录——此前小满手里
     * 既没数据也没周记路标，只能回「跟我说说」空话。mood:<date> 值
     * 0-3 索引（_MOOD_META 同序），只摘实记不编缺档。 */
    if (msg && /心情|情绪|emo|郁闷|开心|难过|烦躁|烦/.test(msg)) {
      var _mb = [];
      for (var _mi = 6; _mi >= 0; _mi--) {
        var _dd2 = new Date(); _dd2.setDate(_dd2.getDate() - _mi);
        var _mdk = _dd2.getFullYear() + '-' +
          String(_dd2.getMonth() + 1).padStart(2, '0') + '-' +
          String(_dd2.getDate()).padStart(2, '0');
        var _mv = _moodDayGet(_mdk);
        if (_mv !== null && _mv !== undefined)
          _mb.push(_mdk.slice(5) + ' ' + _MOOD_META[_mv].t);
      }
      if (_mb.length)
        _f.push('她近几天自己记的心情：' + _mb.join('、') +
                '。打卡区「📒 看看这周的你」有 7 天心情汇总小卡');
    }
    /* R3390：签语话题带今日签面——她聊「签上怎么说/这支签」时，
     * 小满手里得有她抽的那支（此前只能回「告诉我签面」空话）。
     * 只在她真提过签的话题里注（不泛注入「签」单字——日签/打卡
     * 也带签字会过曝）。 */
    if (msg && /抽.{0,2}签|求.{0,2}签|解签|签诗|灵签|观音签|这支签|那支签|签上说|签面|摇.{0,2}签/.test(msg)) {
      try {
        var _qf = JSON.parse(localStorage.getItem('qian:fact') || 'null');
        if (_qf && _qf.d === todayIso() && _qf.t) _f.push(_qf.t);
      } catch (eQf) {}
    }
    /* R3394：答案之书话题带今日翻页结果——她聊「书上那句/那句话
     * 对不对」时小满手里得有她翻到的句子。同日失效不串页。 */
    /* R3395-P2-3：注入词收窄——「该不该/要不要/那句话」太宽，无关
     * 闲聊也会挂上翻书 fact（还可能与题面错配）。只留载体词。 */
    if (msg && /答案之书|翻.{0,3}书|书上.{0,2}说|那一页|帮.{0,2}翻/.test(msg)) {
      try {
        var _af = JSON.parse(localStorage.getItem('ansb:fact') || 'null');
        if (_af && _af.d === todayIso() && _af.t) _f.push(_af.t);
      } catch (eAf) {}
    }
  } catch (e) {}
  return _f;
}

function chatSend() {
  var input = el('chatInput');
  var msg = zwClean(input && input.value);   /* R230k：零宽不当非空 */
  /* R230d（R16-P3-6）：空消息此前完全静默——跟 hlAskInput 的占位提示
   * 口径拉齐，给一句轻提示。 */
  if (!msg) {
    if (input) input.placeholder = '先写点什么再发哦';
    return;
  }
  if (input) input.value = '';
  chatBubble('me', msg);
  /* R233r（R49-P0）：危机词本地先接住——不计发送数、不发请求。 */
  if (feCrisis(msg)) {
    chatBubble('ai', _CRISIS_FE_REPLY);
    return;
  }
  /* R2996（巡#413）：敏感披露同款本地接住——此前只危机词有本地闸，
   * DISABLE/无配置路径 spawn→None → _chatFallbackLine 卖萌句吞严肃
   * 披露；也不该为固定转介文案烧一次网络往返。 */
  if (feSensitive(msg)) {
    chatBubble('ai', _SENSITIVE_CHAT_REPLY);
    return;
  }
  /* R3139（specs/014-L1）：主题足迹落本地——危机/敏感闸之后才记，
   * 那两类消息不进画像。同日同主题去重。 */
  try { _chatTopicLog(msg); } catch (eTL) {}
  try { _chatEventLog(msg); } catch (eEL) {}
  /* R3260（R7）：空态挂着的「怎么样了」跟进行——用户回了任何
   * 消息都算接住过，标记闭合不再追问。 */
  try {
    if (window.__chatPendingEvt != null) {
      var _pe = JSON.parse(
        localStorage.getItem('chat:events') || '[]');
      if (Array.isArray(_pe) && _pe[window.__chatPendingEvt]) {
        _pe[window.__chatPendingEvt].closed = 1;
        /* R3306-P2：并集写——闭合标记与另一 tab 的新话头不互丢。 */
        _lsUnionWrite('chat:events', _pe,
          function (x) { return x && x.k; }, 10);
      }
      window.__chatPendingEvt = null;
    }
  } catch (ePC) {}
  /* D-006：追踪发送次数，第一条自动发后允许追问 1 次，第 2 次回复后才锁 */
  _CHAT_SEND_COUNT = (_CHAT_SEND_COUNT || 0) + 1;
  /* R230v（R34-#3）：捕获发送时 sid——在途回复遇上「开个新话题」换 sid
   * 时，旧任务落地不得把回复写进新 transcript（幻影气泡）。 */
  var _sid0 = chatSid();
  /* R2343（R58-P2-2）：发送即有 typing 三点——此前要等 chat_task_id
   * 回来才出现，慢服务下静默 20 秒像没发出去。 */
  var _ty0 = chatBubble('ai', '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span><span class="chat-wait-note">小满正在翻书…</span>', {raw: true});
  postJSON('/api/chat', {
    session_id: _sid0, message: msg,
    facts: _chatFacts((CHAT_LAST_FACTS && CHAT_LAST_FACTS.length)
      ? CHAT_LAST_FACTS : _activeViewFacts(), msg),   /* R233r：无排盘按视图兜底 */
    /* R3124b：判词升格信道——ref 由 _activeViewFacts 解出（facts 走
     * CHAT_LAST_FACTS 时 ref 是上次解出的配套值，同源不串）。 */
    result_ref: _CHAT_CTX_REF || '',
    client_date: todayIso()   /* R230l */
  }, { silent: true }).then(function (j) {
    if (!j.chat_task_id) {                     /* DISABLE：入口静默降级 */
      /* R2355（R111-P2-6）：限流≠关停——rate_limited 只提示不锁框，
       * 且不计入 ≥2 次的锁死门槛（歇口气就能再发）。 */
      if (j && j.rate_limited) {
        if (_ty0) { _ty0.remove(); _ty0 = null; }
        _CHAT_SEND_COUNT = Math.max(0, (_CHAT_SEND_COUNT || 0) - 1);
        /* R2400（R123-P2-5）：限流气泡落档——nosave 会留孤儿气泡。 */
        chatBubble('ai', '（聊太急啦，小满喝口水歇口气，一会儿再戳我～）');
        return;
      }
      if (_ty0) { _ty0.remove(); _ty0 = null; }
      /* R216b 续3（UX 队列 U-008）：原降级文案「（聊天功能暂时没开，
       * 稍后再来吧）」系统腔零共情——用户刚倾诉疲惫。改为情绪承接 +
       * 替代引导；DISABLE 态输入框置灰防连发连拒。
       * R218a-02：扩为 4-6 句确定性轮换 + 关键词到 openeer 的最轻分支
       * （累/事业/感情/学业/钱/看盘 6 套）。 */
      var _fb2 = chatBubble('ai', _chatFallbackLine(msg), { nosave: true });
      _chatActChip(_fb2, j && j.action);   /* R3195：打烊态也给出真入口 */
      var sendBtn2 = document.getElementById('chatSendBtn');
      /* D-006：第一条自动发后允许追问 1 次，累计发送 ≥2 次后才锁 */
      if (_CHAT_SEND_COUNT >= 2) {
        if (input) { input.disabled = true; input.placeholder = '小满休息中，回头再来聊吧'; }
        if (sendBtn2) sendBtn2.disabled = true;
      }
      return;
    }
    /* R230t（R32-P2-16）：拿到任务即解锁——LLM 恢复后不再被锁在
     * 「休息中」直到换 sid。 */
    if (input && input.disabled) { input.disabled = false; input.placeholder = '说说你的心情…'; }
    if (sendBtn2 && sendBtn2.disabled) sendBtn2.disabled = false;
    /* R228c：同 autoSendChatContext——节点引用写回 + catch 续排。
     * R2343：发送时已插 typing，直接复用不落二次。 */
    var _ty = _ty0 || chatBubble('ai',
      '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span><span class="chat-wait-note">小满正在翻书…</span>', {raw: true});
    _pollChatReply(j.chat_task_id, _ty, _sid0, j.action, msg);   /* R233r+R3213：msg 供失败重发：共用轮询体（含排队预算） */
  }).catch(function (e) {
    if (_ty0) { _ty0.remove(); _ty0 = null; }
    /* R230t（R32-P2-19）：4xx 是内容被拦（消息超长/facts 超限等），
     * 不是网络问题——保留已发气泡、如实报服务端文案，别回收成「被吞了」。 */
    if (e && e.status >= 400 && e.status < 500) {
      /* R2349r（R82-P2-8）：服务端 detail 是机器腔（「消息超长（≤500字），
       * 收到 501 字」）——包装成小满腔，不当原文广播。 */
      var _d = String(e && e.message || '');
      chatBubble('ai', /长|超|too|character|字/.test(_d)
        ? '（这条有点长，小满接不住，说短一点试试？）'
        : '（' + (_d || '这条没发出去') + '）', { nosave: true });
      return;
    }
    /* R230q（R28-P3-11）：发送失败把已打文案放回输入框，离线不丢稿 */
    if (input && !input.disabled) input.value = msg;
    /* 已贴出的 me 气泡同时从 transcript 与 DOM 回收——重试不再双发同句 */
    try {
      /* R3339（审-中）：撤回只读本 sid 桶——回读上一会话桶会把
       * 旧桶内容误复制进新桶。 */
      var _curSid = _chatSid() || chatSid();
      var _arr = _chatTsRead(_curSid);
      if (_arr.length && _arr[_arr.length - 1].r === 'me' &&
          _arr[_arr.length - 1].t === msg) {
        _arr.pop();
        /* R3339（审-中）：撤回写回也要落本 sid 桶——写裸键会造出
         * 幽灵副本（与 transcript 命名空间同口径）。 */
        (_chatTsStore() || _MEM_STORE).setItem(
          _chatTsKey(_curSid), JSON.stringify(_arr));
        var _bbs = document.querySelectorAll('#chatFlow .chat-me');
        if (_bbs.length && _bbs[_bbs.length - 1].textContent === msg) {
          _bbs[_bbs.length - 1].remove();
        }
      }
    } catch (e2) {}
    chatBubble('ai', '（' + _dayPick(['网络不太好，再发一次试试？','信号飘了，一会儿再戳我','刚才没接到，再发一次吧～'],'net') + '）', { nosave: true });
  });
}

/** 绑定点击；元素不存在时不报错（HTML 与 JS 允许分批演进）。
 * R228c：统一在途防重——handler 未落地前连点直接忽略。全站提交按钮
 * 走 on() 一处生效，替代逐按钮挂 disabled/flag 的老办法。
 * R230q（R28-P1-1）：锁改为按 key 共享的注册表——Enter 键路径与按钮
 * 点击此前各执一把锁（Enter 直接调 handler），连按回车可并发发请求
 * （#tq 每秒刷出一条永久线程）。现在 Enter/点击共用同 key 同锁。 */
var _ON_BUSY = {}, _ON_QUEUE = {};
function guardedCall(key, handler, ev, queueLatest) {
  /* R233k（R45-Top5-2）：在途吞点改成「忙态可见 + queueLatest 键补跑
   * 最后一次意图」——按钮在途置灰（disabled+aria-busy+is-working），
   * 点了不再像没点；翻页/换书类入口把最后一下记下来落地后补跑。 */
  if (_ON_BUSY[key]) {
    if (queueLatest) _ON_QUEUE[key] = { handler: handler, ev: ev };
    return;
  }
  _ON_BUSY[key] = true;
  var _btn = el(key);
  if (_btn && _btn.tagName === 'BUTTON') {
    _btn.classList.add('is-working');
    _btn.setAttribute('aria-busy', 'true');
    _btn.disabled = true;
  }
  /* R233r（R50-#7）：handler 同步抛异常会冒泡出 click——锁永真、
   * 按钮永灰。包进 .then 链里把同步异常也接住。 */
  Promise.resolve().then(function () { return handler(ev); }).catch(function (e) {
    console.warn('[on] handler error', e);
  }).then(function () {
    _ON_BUSY[key] = false;
    /* R3322-P2：handler 主动要求终态禁用（如「已做完」仪式钮）——
     * data-stay-disabled=1 时保留 disabled、只撤忙态外观，否则已
     * 完成的仪式反复可点。 */
    if (_btn && _btn.tagName === 'BUTTON') {
      if (_btn.dataset.stayDisabled !== '1') _btn.disabled = false;
      _btn.classList.remove('is-working');
      _btn.removeAttribute('aria-busy');
    }
    var _q = _ON_QUEUE[key];
    if (_q) { delete _ON_QUEUE[key]; guardedCall(key, _q.handler, _q.ev, true); }
  });
}
/* R230v（R34-#23）：bfcache 冻结期间 fetch 被掐死但不 reject 的边角
 * 会让锁永不释放——pageshow persisted 时清表（锁保护的是真在途请求，
 * 恢复后它们早已不存在）。 */
window.addEventListener('pageshow', function (e) {
  if (e && e.persisted) _ON_BUSY = {};
});
function on(id, handler, queueLatest) {
  const node = el(id);
  if (!node) return;
  node.addEventListener('click', function (ev) {
    guardedCall(id, handler, ev, queueLatest);
  });
}

const MODULE_COLORS = ['var(--c-bazi)', 'var(--c-book)', 'var(--c-tarot)',
  'var(--c-huangli)', 'var(--c-qiming)', 'var(--c-taohua)',
  'var(--c-liuyao)', 'var(--c-hehun)'];

function colorAt(i) {
  return MODULE_COLORS[i % MODULE_COLORS.length];
}

/* R3233（循环优化-2）：时辰未知的盘，四柱渲染仍画「x午时」——默认午时
 * 长得跟真时辰一模一样，用户会当成自己的时辰。渲染层统一把第 4 柱
 * 换成「时辰未知」，事实层（后端排盘/十神）不动；hourKnown 只认
 * false 才换（undefined/true 一律原样，默认不缺显示）。 */
function _pillarsHonest(render, hourKnown) {
  if (hourKnown !== false) return render || '';
  var _t = String(render || '').split(/\s+/);
  if (_t.length >= 4 && /时$/.test(_t[3])) _t[3] = '时辰未知';
  return _t.join(' ');
}

/* ── 视图切换 ──────────────────────────────────────────────── */

function showView(viewId) {
  /* R200b（US3 谱系重组）：首页三入口（today/divine/study）是「簇页」，
   * 功能视图是「叶页」。进叶页时隐藏首页主体（.home-main），显示 44px
   * 返回条；回首页恢复。探针契约：`.func-card[data-view]` 点击后
   * `#view-X.active` 出现——入口卡与子卡都带 data-view，行为一致。 */
  /* R205b（用户反馈③）：不再自动滚回顶部。实测根因有二：
   * (a) 本函数原先的 window.scrollTo(0)；已删。
   * (b) Chrome scroll anchoring——homeMain 从文档流移除时浏览器为稳住
   *     锚点自行调整 scrollY（实测 2000→516，无任何 scrollTo 调用）。
   *     对策：切换前记住位置，布局变更后原样恢复（浏览器钳到新最大值，
   *     短页面自然落顶，不产生「拽回页顶」的观感）。提交后的定位仍由
   *     revealResult() 负责，probe_first_screen 判据 1 不受影响。 */
  /* R230j（R22-P3-4）：切视图时在跑的 AI 轮询继续空转打到 deadline
   * ——结果已不可见还在发请求。切走即 bump 全部世代号，让 in-flight
   * tick 下一次自查自然终止（同容器新结果 bump 同一键，语义一致）。 */
  Object.keys(RESULT_GEN).forEach(function (k) { RESULT_GEN[k]++; });
  var _sy = window.scrollY;
  var isHome = (viewId === 'home');
  /* R3303-P3：跨视图收尾——非错误 toast 是上一视图的回声，跟过去
   * 在键盘态会真挡表单；welcomeBar/returnBanner 同理（CSS 按
   * body[data-view] 只让它们在首页渲染）。 */
  try {
    document.body.dataset.view = viewId;
    var _st = document.getElementById('toastStack');
    if (_st) {
      _st.querySelectorAll('.toast-item:not(.toast-error)').forEach(
        function (t2) { t2.remove(); });
    }
  } catch (eV) {}
  document.querySelectorAll('.view').forEach(function (v) {
    v.classList.remove('active');
  });
  const target = el('view-' + viewId);
  if (target) target.classList.add('active');
  /* R2400（R122-P1-1 下）：进古籍域即预热研究台 chunk——比首次点按钮
   * 才拉省一拍；不进这个视图的用户永远不付这 24KB。失败静默。 */
  if (viewId === 'read') {
    try { _loadResearchJs().catch(function () {}); } catch (eR) {}
    /* R3369（审-P1-1）：read 深链消费——rq 预填自动跑检索，
     * bs 预填书号自动进结构页（stub 链路自带 chunk 懒加载）。 */
    try {
      var _rd = window.__readDeep;
      if (_rd) {
        window.__readDeep = null;
        if (_rd.q) {
          var _rqEl = el('rq');
          if (_rqEl) _rqEl.value = _rd.q;
          guardedCall('searchBtn', doSearch, null, true);
        }
        if (_rd.bs) {
          var _bsEl = el('bswork');
          if (_bsEl) {
            _bsEl.value = _rd.bs;
            _bsEl.dispatchEvent(new Event('change'));
          }
          activateBssec('bs-structure');
        }
      }
    } catch (eRD2) {}
  }
  /* 心情周记：进视图按最新 mood:<date> 重渲（跨 tab 改过也跟新）。 */
  if (viewId === 'moodweek') {
    try { _renderMoodWeek(); } catch (eMW) {}
  }
  /* R3350：咒语册——进视图按最新 mantraFav 重渲（跨 tab 收/删跟新）。 */
  if (viewId === 'mantra') {
    try { _renderMantraBook(); } catch (eMBV) {}
  }
  /* R3381：默契挑战——按 location.hash 出 host/guest/result 三态。 */
  if (viewId === 'mochi') {
    try { _renderMochi(); } catch (eMCV) {}
  }
  /* R3388：每日一签——懒载语料后出今签/签筒。 */
  if (viewId === 'qian') {
    try { _renderQian(); } catch (eQ) {}
  }
  /* R3394：答案之书——书卡/答案卡两态渲染。 */
  if (viewId === 'ansb') {
    try { _renderAnsb(); } catch (eAB) {}
  }
  document.querySelectorAll('.func-card').forEach(function (c) {
    const isActive = c.dataset.view === viewId;
    c.style.borderColor = isActive ? 'var(--primary)' : '';
    c.setAttribute('aria-current', isActive ? 'true' : 'false');
  });
  const home = el('homeMain');
  if (home) home.hidden = !isHome && !!target;
  const back = el('viewBack');
  if (back) back.hidden = isHome || !target;
  /* R228d：键盘焦点管理——原实现在 func-card 上按 Enter 后 homeMain 被
   * hidden，焦点被浏览器甩回 body，Tab 序从头爬。进叶页聚焦返回条；
   * 回首页把焦点还给原入口卡（initViews 里记录 __lastFuncCard）。
   * preventScroll：不干扰本函数的滚动位置恢复。 */
  if (!isHome && back && !back.hidden) {
    try { back.focus({ preventScroll: true }); } catch (e0) { back.focus(); }
  } else if (isHome) {
    /* R233f（R43-P2-10）：深链进叶页再返回——__lastFuncCard 从未被设
     * 过，焦点丢 BODY 从头爬。空则落回功能区锚点。 */
    var _back2 = window.__lastFuncCard || el('funcGrid');
    if (_back2) {
      try { _back2.focus({ preventScroll: true }); }
      catch (e0) { try { _back2.focus(); } catch (e1) {} }
      /* R2348（R66-P2）：卡在收起的 <details>/隐藏 .view 里时 focus
       * 静默失败（落 BODY，Tab 从头爬）——校验落地，失败退 funcGrid。 */
      if (document.activeElement !== _back2) {
        var _fg = el('funcGrid');
        if (_fg && _fg !== _back2) {
          try { _fg.focus({ preventScroll: true }); } catch (e2) {}
        }
      }
    }
  }
  /* v3（P8 修复）：记住「离开首页时的位置」，回首页时精确恢复。
   * 实测原实现回首页恒为 0（y2987→0）。进入视图时把当前 scrollY 存入
   * _HOME_SCROLL_MEM；回首页（isHome）时恢复它。功能视图之间切换不拽顶。 */
  if (isHome) {
    /* v3 P8：回首页——恢复「离开首页时」记下的位置，恢复后清记忆。 */
    var _mem = Number(window.__homeScrollMem);
    var _target = !isNaN(_mem) ? _mem : _sy;
    window.__homeScrollMem = undefined;
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        window.scrollTo({ top: _target, behavior: 'auto' });
      });
    });
  } else if (!window.__inView) {
    /* v3 P8：只有「从首页进入功能视图」这一次记录首页位置；
     * 功能视图内部切换不覆盖记忆（否则会记成功能页自己的滚动位）。 */
    window.__homeScrollMem = _sy;
  }
  /* R2348（R66-P2）：document.title 随视图走——读屏/多标签/书签可辨。 */
  try {
    var _vn = isHome ? '' :
      ((document.querySelector('.func-card[data-view="' + viewId + '"] .func-name') || {}).textContent ||
        /* R2349v（R92-P2-5）：无入口卡的视图（read/history）此前兜底
         * 直泄英文 id 上标题栏——视图名小表兜底。 */
        ({read:'古籍',history:'排盘台账',moodweek:'这周的你',
          mantra:'咒语册'})[viewId] || viewId);
    document.title = (_vn ? (_vn + ' · ') : '') + '小满的解忧铺 · 知命';
  } catch (eT) {}
  window.__inView = !isHome;
  try { _usageTrack(viewId); } catch (eUT) {}   /* R3260：足迹埋点 */
  /* R230q（R28-P2-2）：切走即 bump 世代号会把在跑的 AI 轮询作废，
   * 回来后那段「小满想了想」永远不来。回到视图时对本视图内仍
   * pending 的容器重新武装轮询（任务在后端还活着，可继续取）。 */
  if (target && !isHome) {
    Object.keys(AI_PENDING).forEach(function (cid) {
      var c = el(cid);
      if (c && target.contains(c) && !c.querySelector('.ai-polish')) {
        pollAiPolish(cid, AI_PENDING[cid]);
      }
    });
  }
  /* R2512（前端审 P1-3）：dailyDetail 挂在主页容器链上，上面的
   * leaf 重武装永远摸不到它——切走杀死轮询、回家 dataset.loaded
   * 挡下重发、AI_PENDING 孤儿永久停摆。回家时按同一规则补武装。 */
  if (isHome && AI_PENDING.dailyDetail) {
    var _dd = el('dailyDetail');
    if (_dd && !_dd.querySelector('.ai-polish')) {
      pollAiPolish('dailyDetail', AI_PENDING.dailyDetail);
    }
  }
  /* R230d（R16-P1-2）：叶页→叶页此前抱着旧滚动位落在新页面中段——
   * v5「保持阅读位置」的本意是同一页内的重进，不是跨页。 */
  if (!isHome) window.scrollTo({ top: 0, behavior: 'auto' });
  /* R230d（R16-P0-2）：进叶页推 history 记录——装进主屏后系统返回键
   * 此前直接退出应用（无任何 pushState/popstate）。popstate 回落到
   * state.view 或首页。 */
  try {
    if (!isHome && target && !window.__suppressPush) {
      /* R230q（R28-P2-3）：此前推的是空 URL——地址栏恒为 /，F5 后视图
       * 全丢回首页，与 ?view= 深链机制自相矛盾。带上 ?view=，刷新由
       * init 深链回跳原视图，结果页也可整链分享。
       * R2348（R66-P1）：'?view=' 是相对址——在 /huangli 路径上 push
       * 会产出 /huangli?view=bazi 混合 URL，F5 被路径段拽错页。写绝对。 */
      history.pushState({ view: viewId }, '',
        '/?view=' + encodeURIComponent(viewId));
    } else if (isHome && !window.__suppressPush &&
        (/[?&]view=/.test(location.search) || location.pathname !== '/')) {
      /* 回首页清掉 ?view=——否则挂着旧参数的 F5 会被深链拽回上一视图。
       * R2348（R66-P1）：路径式落地（/huangli）search 为空，原条件
       * 永不命中——回首页后地址栏还挂 /huangli，F5 又拽回去。 */
      history.pushState({ view: 'home' }, '', '/');
    }
  } catch (e) { /* file:// 环境无 history API */ }
  /* R2348（R67-P2）：海报资产惰性预拉——首进功能视图时启动。 */
  if (!isHome) { try { _idlePrefetch(); } catch (eP) {} }
  /* R216b 续（U-007）：时间起卦默认当天（原 HTML 写死 1990/5/15）。 */
  if (viewId === 'liuyao') syncLiuyaoToday();
  /* R3260（N6 收口）：五行人格回流礼遇——存过生日的老客进页
   * 免重填：预填表单 + 结果还是空态时自动开测一次（每会话一次，
     * 刷历史时不扰）。「1-tap 测试」对回头人该真是 0-tap。 */
  if (viewId === 'renge') _rgEnter();
  /* R3260（N1 延伸）：解梦是深夜高频入口——空态尾巴挂上小满的
   * 店况行（深夜=留灯，白天=翻书），「有人接」的体感先于提问。 */
  if (viewId === 'dream') {
    var _dmPh = document.querySelector('#dmResult .ph-empty');
    if (_dmPh && !_dmPh.dataset.shop) {
      _dmPh.dataset.shop = '1';
      var _dmSp = document.createElement('div');
      _dmSp.className = 'ph-shop';
      _dmPh.appendChild(_dmSp);
    }
    var _dmLine = document.querySelector('#dmResult .ph-shop');
    if (_dmLine) _dmLine.textContent = _xmShopLine();
  }
  /* R2350f（R102-P2-7）：塔罗落地先亮「今日牌」——日卡/打卡/黄历/
   * 星座首屏都有自动内容，唯独塔罗是空表单；一张免费牌先接住她。 */
  if (viewId === 'tarot') _tarotLandingCard();
  /* R222b（E-301 P0）：黄历同理——原 HTML 写死 2026/8/19 */
  if (viewId === 'huangli') hlInitToday();
  /* C-002-fix：星座视图进入时自动加载今日运势 */
  if (viewId === 'xingzuo') {
    /* R2349k（R72-B2）：隔夜进星座页表单还停在昨天却写「今日当班」——
     * 先回到今天再查。 */
    if (_xzLastDate && _xzRenderedOn && _xzRenderedOn !== todayIso()) {
      var _tt = new Date();
      xzSetDate(_tt.getFullYear(), _tt.getMonth() + 1, _tt.getDate());
      _xzLastDate = null;
    }
    doXingzuo(false);   /* R228f：重进同日复用已渲染，不再重拉+跳动 */
  }
  /* R231d（R37-F3）：?view=history 深链/F5 落地即死卡——加载此前只在
   * 首页卡片 click 里触发，进视图就补一次（函数在排盘历史 IIFE 内，
   * 经 window 钩子暴露）。 */
  /* R232c（R41-P1-2）：深链 ?view=history 在 defer 执行期进 showView，
   * 此时排盘历史 IIFE 尚未跑到、__loadPaipanHistory 未赋值——静默跳过
   * 致列表永卡「加载中」。改惰性调度，让模块注册先完成。 */
  if (viewId === 'history') {
    setTimeout(function () {
      if (window.__loadPaipanHistory) window.__loadPaipanHistory();
    }, 0);
  }
}

/* R230d（R16-P0-2）：系统返回/后退手势 → 回到 state 记的视图（默认首页）。 */
window.addEventListener('popstate', function (e) {
  /* R2353（R110-P2-1）：海报/导出弹层也入栈（见 showPosterModal）——
   * 弹层开着时按返回先关弹层；回落到的 state.view 与现视图相同时
   * 不再 showView（同视图重渲会重复触发进页钩子，如塔罗落地卡）。 */
  if (document.getElementById('posterModal')) {
    try { closePosterModal(); } catch (eM) {}
  }
  window.__modalPushed = false;
  var _sv = (e.state && e.state.view) ? e.state.view : 'home';
  /* R3381-P1：默契挑战的 #mc=/#mcr= 载荷是同视图内 hash 导航——
   * hash 改出的是 e.state=null 的新历史项，原逻辑会误判「回首页」
   * 把 view-mochi 摘 active（受邀者同标签贴链直接被弹回首页）。
   * 人还在 mochi 视图时把它认成同视图导航：补回 state 不再切走，
   * 重渲交给模块自己的 hashchange 监听。 */
  if (_sv === 'home' && /^#mc[rs]?=/.test(location.hash || '') &&
      document.querySelector('#view-mochi.active')) {
    try {
      history.replaceState({ view: 'mochi' }, '',
        location.pathname + location.search + location.hash);
    } catch (eRS2) {}
    return;
  }
  var _av = document.querySelector('.view.active');
  var _cv = _av ? _av.id.replace(/^view-/, '') : 'home';
  if (_sv === _cv) return;
  window.__suppressPush = true;
  try {
    showView(_sv);
  } finally {
    window.__suppressPush = false;
  }
});
try { history.replaceState({ view: 'home' }, ''); } catch (e) {}

/* ── 通用渲染件 ────────────────────────────────────────────── */

/** 命中/证据列表（search / addr / research.evidence / liuyao 經文 共用）。
 *  字段以实测响应为准：citation / text / layer / disclosure / score。 */
function renderHits(hits, opts) {
  const o = opts || {};
  if (!hits || !hits.length) {
    return '<div class="no-evidence">' + esc(o.empty || '这次没翻到，换个词试试？') + '</div>';
  }
  let html = '';
  hits.forEach(function (h, i) {
    const c = colorAt(i);
    html += '<div class="ev-item accent" style="border-left-color:' + c + ';">';
    html += '<div class="ev-meta" style="color:' + c + ';"' +
      /* R228z续2：摘要行剥成书名后，悬停仍须能拿到完整出处（锚点+文件） */
      (h.citation ? ' title="' + esc(h.citation) + '"' : '') + '>' +
      esc(humanCite(h.citation || '')) +
      (h.layer ? ' · ' + esc(h.layer) : '') +
      /* R228w：bm25 负分（越接近 0 越好）原值 16 位浮点糊脸，
       * 留 1 位小数 + title 说明口径。 */
      /* R2349v（R92-P1-3）：BM25 负分直出「相关度 -3.6」对受众无意义
       * ——折成档位词，精确分留 title 悬停。 */
      /* R3370-低12：tooltip 不再甩 BM25 术语——说人话「越贴合」。 */
      (o.score && h.score != null ? '<span class="hit-score" title="越贴合你查的那句，分越高。参考分 ' +
        esc(Number(h.score).toFixed(1)) + '">' +
        (Number(h.score) > -5 ? '更相关' : (Number(h.score) > -15 ? '较相关' : '沾边')) +
        '</span>' : '') +
      '</div>';
    html += '<div class="ev-text">' + esc(_rmMarks(h.text || '')) + '</div>';
    if (h.disclosure) html += '<div class="ev-disc">' + esc(h.disclosure) + '</div>';
    html += '</div>';
  });
  return html;
}

/* ── 古籍引文树（005 US2：古籍是可展开的证据，不是默认的正文）────
 * 三级折叠：总入口 → 按书分组 → 每段。默认只有总入口可见（44px）。
 *
 * 为什么是三级而不是平铺（005 plan §2，D-241b）：按书组头直接平铺实测
 * 在 6 部书那一案是 3,288px = 5 屏（判据 2 要 ≤4 屏）——组头文本在 375px
 * 下换行，实测 61px 而非设计的 44px，且高度**不随书数单调**。
 * 单层总入口的高度与书数、段数完全无关，五案实测恒为 44px。
 *
 * 为什么用 hidden 而不是 <details>：两者探针都认（R130a 把定位改成
 * textContent 后）。选 hidden 是因为它能被 CSS 精确控制且不引入
 * <summary> 的默认样式包袱；button 原生提供键盘可达与 aria-expanded。
 *
 * ⚠ 宪法第三条：折叠 ≠ 删除。原文全文进 .cite-body 的 textContent，
 *   一字不截断（不做 interpreter 的 [:220]）、不 trim、不改标点。
 *   hidden 不影响 textContent，故折叠态下原文与出处仍可被取到核验。 */

/** 从 citation 串里取书名做分组键。实测 citation 形如
 *  `穷通宝鉴 @? (qiongtongbaojian_001.txt)` 或
 *  `星命溯源 @KR3g0035_WYG_004-10b (KR3g0035_004.txt)`——` @` 之前是书名。 */
function citeBook(citation) {
  const s = String(citation || '');
  const i = s.indexOf(' @');
  return (i > 0 ? s.slice(0, i) : s).trim() || '未标注出处';
}

var CITE_SEQ = 0;

/** 一个可折叠按钮 + 其内容容器的 id（三级共用）。 */
function citeToggle(id, label) {
  return '<button type="button" class="cite-toggle" aria-expanded="false" ' +
    'aria-controls="' + id + '" data-cite-toggle="' + id + '">' +
    '<span class="cite-caret" aria-hidden="true">▸</span>' +
    '<span class="cite-label">' + esc(label) + '</span></button>';
}

/** 古籍引文树。items 用 API 的原始证据对象（含 citation/text/why/layer）。
 *  判据 5：同一段只渲染一次——本函数是 warm 模式下古籍的**唯一**渲染点。 */
function renderCiteTree(items, opts) {
  const o = opts || {};
  const list = (items || []).filter(function (h) {
    return h && (h.text || h.citation);
  });
  if (!list.length) {
    return '<div class="no-evidence">' + esc(o.empty || '这次没翻到，换个词试试？') + '</div>';
  }
  // 按书分组，保持首次出现顺序（检索相关性顺序，不重排）
  const order = [];
  const groups = {};
  list.forEach(function (h) {
    const book = citeBook(h.citation);
    if (!groups[book]) {
      groups[book] = [];
      order.push(book);
    }
    groups[book].push(h);
  });

  CITE_SEQ += 1;
  const topId = 'cite-all-' + CITE_SEQ;
  const title = o.title || '📜 古籍原文依据';
  let html = '<div class="cite-wrap"><div class="cite-top">';
  html += citeToggle(topId, title + ' · ' + list.length + ' 段 / ' +
    order.length + ' 部书');
  html += '<div class="cite-top-body" id="' + topId + '" hidden>';
  order.forEach(function (book, gi) {
    const gid = 'cite-g-' + CITE_SEQ + '-' + gi;
    const c = colorAt(gi);
    html += '<div class="cite-group" style="border-left-color:' + c + ';">';
    html += citeToggle(gid, '《' + book + '》 ' + groups[book].length + ' 段');
    html += '<div class="cite-group-body" id="' + gid + '" hidden>';
    groups[book].forEach(function (h, si) {
      const bid = 'cite-b-' + CITE_SEQ + '-' + gi + '-' + si;
      const text = h.text || '';
      // 摘要行：出处常显 + why（为何被选中）+ 字数。出处与原文在同一级展开，
      // 不允许只显示其一（005 判据 5）。v3（P4）：label 走 humanCite 清洗内部编码。
      let label = humanCite(h.citation) || '（无出处）';
      if (h.layer) label += ' · ' + h.layer;
      if (h.why) label += ' · 因「' + h.why + '」被选中';
      if (text) label += ' · ' + text.length + ' 字';
      html += '<div class="cite-item">';
      html += citeToggle(bid, label);
      // 原文：逐字节等于 API（判据 8）。esc() 只做 HTML 转义，不改内容。
      // R228z续2：cite-body 尾部带完整原始出处——摘要行 humanCite 把
      // @锚点/(file) 剥成只剩书名，无锚典籍（三命通会等）的出处此前在
      // 页面上完全取不到，宪法第三条的可核验性断了一截。
      html += '<div class="cite-body" id="' + bid + '" hidden>' +
        esc(text) +
        /* R2349j（R71-P1-19）：可见行去掉 @锚点/(file.txt) 技术尾巴，
         * 完整出处收进 title 悬停（宪法可核验性不丢）。 */
        (h.citation ? '<div class="ev-src" title="' + esc(h.citation) +
          '">出处：' +
          esc(String(h.citation).split(/\s+[@(]/)[0].trim() || h.citation) +
          /* R2349j-fix：完整出处留在 hidden span——probe_first_screen 按
           * textContent 核验（宪法可核验性），hidden 不入渲染但在 DOM。 */
          '<span hidden>' + esc(h.citation) + '</span>' +
          '</div>' : '') +
        '</div>';
      if (h.disclosure) {
        html += '<div class="ev-disc">' + esc(h.disclosure) + '</div>';
      }
      html += '</div>';
    });
    html += '</div></div>';
  });
  /* R2349x（R92-P1-4）：引文树尾部补「去书库翻」入口——占卜域此前
   * 只呈现零跳转，深链复活（R2349v）后顺藤摸瓜的最小闭环。 */
  html += '<div class="cite-readmore"><button type="button" ' +
    'class="thread-view cite-toread">📚 这些书都在书库里，去翻翻 →</button></div>';
  html += '</div></div></div>';
  return html;
}

/** 折叠件的点击处理（事件委托，见 initReading 的 document click）。 */
function toggleCite(btn) {
  const id = btn.dataset.citeToggle;
  const body = document.getElementById(id);
  if (!body) return;
  const open = body.hidden;
  body.hidden = !open;
  btn.setAttribute('aria-expanded', String(open));
  const caret = btn.querySelector('.cite-caret');
  if (caret) caret.textContent = open ? '▾' : '▸';
}

/** 结果区定位（005 判据 1）：提交成功后把结果区顶部对齐视口顶部。
 *
 *  为什么是滚动而不是隐藏首页各块：判据 1 经 R129a 订正后量的是**相对提交后
 *  视口**的偏移，不是文档绝对 y。既然如此就不需要藏掉品牌区/今日运势卡/
 *  功能卡——它们留在文档里，向上滚即见，spec 那条「不得把今日入口永久藏死」
 *  天然满足。实测显式滚动后一句话结论落在视口 353px。
 *
 *  behavior 用 'auto' 不用 'smooth'：prefers-reduced-motion 下不产生动画
 *  （005 判据 18），也避免测量时取到滚动中间值。 */
function revealResult(containerId) {
  const node = el(containerId);
  if (!node) return;
  const top = node.getBoundingClientRect().top + window.scrollY;
  const target = Math.max(0, top - 8);
  window.scrollTo({ top: target, behavior: 'auto' });
  /* v5-fix（取证见 .cluster/debug_scroll_v5.py）：Chrome 滚动锚定/饧位会在
   * DOM 变更同帧吞掉程序滚动（scrollTo 后 scrollY 仍为 0）。双 rAF + 260ms
   * 两次确认补拉；期间用户主动滚动（滚轮/触摸/按键）则不补。
   * R3309（probe_first_screen）：_confirm 每次**重新量**结果区顶——
   * 提交后上方块还会异步长高（loadDaily 重刷日卡之类），拿提交瞬间
   * 量的 target 补拉会把结论推到视口外。 */
  var _userMoved = false;
  var _stop = function () { _userMoved = true; };
  window.addEventListener('wheel', _stop, { passive: true, once: true });
  window.addEventListener('touchmove', _stop, { passive: true, once: true });
  window.addEventListener('keydown', _stop, { passive: true, once: true });
  var _confirm = function () {
    if (_userMoved) return;
    var _now = Math.max(0, node.getBoundingClientRect().top +
                        window.scrollY - 8);
    if (Math.abs(window.scrollY - _now) > 4) {
      window.scrollTo({ top: _now, behavior: 'auto' });
    }
  };
  requestAnimationFrame(function () { requestAnimationFrame(_confirm); });
  setTimeout(_confirm, 260);
  /* R3309：晚一拍再确认一次——日卡/预取这种 ~500ms 级的异步重绘
   * 完成后再锚一次（实测锚定被吞后结论落在视口 1272px）。 */
  setTimeout(_confirm, 900);
  /* R230j（R22-P2-1）：once 监听在用户无滚轮/触摸/按键时永不自行
   * 回收，每次提交积 3 个（55 次提交实测 +150）。最后一次 _confirm
   * 跑完后三监听使命已尽——主动摘掉。 */
  setTimeout(function () {
    window.removeEventListener('wheel', _stop);
    window.removeEventListener('touchmove', _stop);
    window.removeEventListener('keydown', _stop);
  }, 1200);
}

/* R3212（用户提议，已落地）：温柔版/专业版合并为单版——
 * 双开关是「拿不准」的历史遗留：专业版只是把英文枚举键值
 *（strength=mid、hit_pillars=hour）原样铺屏，受众读不懂、
 * 开发者也没多拿到什么。现在卡面只有一版：人话常显，
 * 原专业内容（排盘原串/推导链/古籍全文/候选池）统一收进
 * 「📐 专业坐标」折叠块，数据零删减、可展开核验。 */

/* ── 视觉主题（003 US5 / 判据 12：审美方向可一键回滚）───────────
 * aa     = R183b 的无障碍配色（默认；31 处对比度不足已归零）
 * legacy = R183b 之前的原配色（对照用；**不满足判据 3**，那正是它的意义）
 * system = 跟随系统深浅色（R44）
 * 只切 <html data-theme>，CSS 侧只覆盖令牌不碰规则集——所以回滚路径
 * 不需要反向修改任何组件样式，不可能漏。 */
var THEME_KEY = 'uiTheme';

function _effectiveTheme(theme) {
  if (theme === 'legacy') return 'legacy';
  if (theme === 'dark') return 'dark';
  if (theme === 'system' && window.matchMedia &&
      matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
  return 'aa';
}

function uiTheme() {
  try {
    var v = localStorage.getItem(THEME_KEY);
    if (v === 'legacy' || v === 'dark' || v === 'system') return v;
  } catch (e) {}
  return 'aa';
}

function applyTheme(theme) {
  var requested = theme || uiTheme() || 'aa';
  var t = _effectiveTheme(requested);
  /* R2340：theme-color meta 跟着换——浏览器地址栏/PWA 顶栏同色。
   * R3368（审-P2-10）：双 meta（media 深浅分流）要同步全改，
   * 只改第一个会被 media 规则顶掉。 */
  var _metas = document.querySelectorAll('meta[name="theme-color"]');
  var _mcol = (t === 'aa') ? '#FFF8E7'
    : (t === 'dark' ? '#221D20' : '#F7F3EA');
  if (t === 'aa') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', t);
  }
  _metas.forEach(function (_m) {
    _m.setAttribute('content', _mcol);
  });
  /* R2349j（R70-P1-23）：原生控件（select 下拉/日期框/滚动条）随主题——
   * meta color-scheme 写死 light 时深色下控件仍按浅色画。CSS 侧也有
   * html[data-theme="dark"]{color-scheme:dark}，meta 双保险。 */
  var _cs = document.querySelector('meta[name="color-scheme"]');
  if (_cs) _cs.setAttribute('content', t === 'dark' ? 'dark' : 'light');
  try {
    localStorage.setItem(THEME_KEY, requested);
  } catch (e) { /* 存不了就只在本次会话生效 */ }
}

/** R206b（US4）：共情模板族——确定性选择，同输入同输出。 */
/* R233j（R46-P1）：四个主题各升 3 句池——高频首屏句不再撞。 */
var WARM_EMPATHY = {
  "感情": ["感情的事最怕自己闷着，我们一起看看盘里怎么说。",
           "心动或心堵，盘里都有线索，慢慢看，不急。",
           "感情这条线别自己扛，先听听盘面想说什么。"],
  "事业": ["工作上的事悬着心吧？先看看盘里的信号，再说下一步。",
           "卡住的活儿先放一放，看看盘面给的节奏。",
           "事业这事儿急不来，先瞅瞅盘里的风向。"],
  "学业": ["学习上有点累了吧？盘里有些线索给你参考。",
           "备考/赶工都辛苦了，看看今天的能量点在哪。",
           "学业不看出身看节奏，盘里的提示先听听。"],
  "健康": ["身体是自己的，先深呼吸，我们温和地看看盘里的提醒。",
           "身体发来的小信号别硬扛，先听听盘里怎么说。",
           "照顾好自己最重要，盘里的提醒只当参考，不舒服就看医生。"]
};
/* R216b 续3（UX 队列 U-012）：开场白从固定单句改 6 句轮换池——
 * 按「功能视图 + 日期」sha1 确定性抽取（同 copy_bank 纪律：同输入
 * 同输出，不违反确定性判据），连续用不同功能不再听到同一句。 */
var WARM_EMPATHY_POOL = [
  "来了就好。不管今天怎么样，先看看盘想对你说什么。",
  "别急，我帮你瞧瞧：先看看它想对你说什么。",
  "抽到什么说什么，我们慢慢看。",
  "你来了，它也在。一起看看今天的信号。",
  "这结果挺有意思的，听我慢慢说给你听。",
  "放心，不吓人：我把它们翻译成人话给你。"
];
var WARM_EMPATHY_DEFAULT = "来了就好。不管今天怎么样，先看看盘想对你说什么。";
/* R206b 补记：首版把提问挂在函数属性上被 probe_dollar_misuse 判
 * 「函数当对象访问属性」FAIL（本仓铁律），改模块级变量 WARM_LAST_QUESTION。 */
var WARM_LAST_QUESTION = "";
var LAST_BAZI_LUNAR = false;   /* R216b 续5（U-021）：本次提交是否农历输入 */
/* R2350f（R102-P1-5）：结果卡回显「按哪个生日排的」——表单出厂是
 * 示例值（1990/5/15），截图外溢时接收方能认出这是谁的盘。 */
var _LAST_BIRTH = {};
function _birthEcho(view) {
  var t = _LAST_BIRTH[view];
  return t ? '<p class="hit-cite">📅 按生日 ' + esc(t) +
    ' 排的，不是你的生日就去上面改一下再算</p>' : '';
}
function warmEmpathy(question) {
  var q = question || "";
  for (var k in WARM_EMPATHY) {
    if (q.indexOf(k) !== -1) return _dayPick(WARM_EMPATHY[k], 'emp|' + k);
  }
  /* U-012：无主题匹配时从池中确定性抽取（视图名+日期做盐）。 */
  try {
    var view = document.querySelector('.view.active') || {};
    /* R230h（R20-F8）：日盐换浏览器本地日——toISOString 是 UTC，东八区
     * 早上 8 点前盐值还停在昨天。 */
    var salt = (view.id || 'x') + '|' + todayIso();
    var h = 0;
    for (var i = 0; i < salt.length; i++) h = (h * 31 + salt.charCodeAt(i)) >>> 0;
    return WARM_EMPATHY_POOL[h % WARM_EMPATHY_POOL.length] || WARM_EMPATHY_DEFAULT;
  } catch (e2) {
    return WARM_EMPATHY_DEFAULT;
  }
}

/** warm 视图（guji.voice 的输出）。四层结构，见 plan §1.2。
 *  判据 7：badge 渲染在能量卡之后、details 之前——不压轴收尾。
 *  判据 4：basis 推导链进 <details> 折叠，展开后逐字不变。 */
/* R216b 续5（UX 队列 U-016）：力量词（TEN_GOD_WARM 日常语标签）首现
 * 即裸抛——「压力位/规矩位/同伴力」并列无解释。显示层给每个词补短注
 * （API/基线字节零改动）。 */
var POWER_NOTES = {
  '压力位': '外部推力大，事情常被逼着往前走',
  '规矩位': '在规则里行事，责任感重',
  '同伴力': '身边同类多，有人同行也容易比较',
  '表达力': '温和地把想法说出来、做出来',
  '创造力': '点子多、锋芒也在，喜欢跳出框架',
  '流动财': '进项来源多，但不太固定',
  '稳定财': '来源固定，适合慢慢积累',
  '直觉力': '想法独特，学东西走自己的路',
  '庇护力': '有人照着、有东西托着，适合稳步累积'
};
function annotatePowers(text) {
  var t = String(text || '');
  Object.keys(POWER_NOTES).forEach(function (w) {
    if (t.indexOf(w) !== -1 && t.indexOf(w + '（') === -1) {
      t = t.replace(w, w + '（' + POWER_NOTES[w] + '）');
    }
  });
  return t;
}
/* R3245（用户实测「两个专业入口内容一样」）：skipDetailsFold——
 * renderVoice 外层的「📐 专业视角：完整推导链」已含同一份
 * sections（+引文+依据+免责），内层「📜 想看专业依据」是同源重复，
 * 该路径传 true 跳过；dailyDetail 无外折叠，仍要这层。 */
/* R3309（probe_first_screen）：共情+L0 拆成 _warmLead——bazi 结果卡
 * 要把它提到卡顶（判据 1），本函数主体用 skipLead 不再渲染。 */
function _warmLead(warm) {
  if (!warm) return '';
  /* R206b（specs/009 US4 接住感）：L0 上一句共情——确定性模板族
   * （按提问主题选，无提问走通用款），同输入同输出不违反确定性判据。
   * 写死在前端而非 voice.py：voice 输出被 voice_baseline.json 逐字节
   * 钉住，前端追加层 additive 零基线风险。
   * R207b：聊天入口已由 paint() 全局统一注入（含塔罗/桃花等所有结果卡），
   * 此处不再单独渲染。 */
  return '<div class="warm-empathy"><span>' +
    esc(warmEmpathy(WARM_LAST_QUESTION)) + '</span></div>' +
    /* L0 一句话：首屏第一眼就是它（判据 1/3） */
    /* R3319-P2：「牌·正：」内部编码出屏——与海报同款转顺读。 */
    '<div class="warm-l0">' + esc(String(warm.one_liner || '')
      .replace(/·\s*([正逆])\s*：/, '（$1位）：')) + '</div>';
}
function renderWarm(warm, interp, evidence, scope, skipDetailsFold,
                    skipLead, foldSecs) {
  if (!warm) return renderInterpretation(interp, '📖 小满的解读');
  var html = '<div class="warm-wrap">';
  html += skipLead ? '' : _warmLead(warm);
  // L1.5 reply：对提问的回应，紧跟 L0
  if (warm.reply && warm.reply.length) {
    html += '<div class="warm-reply">';
    warm.reply.forEach(function (ln) {
      html += '<p>' + esc(ln) + '</p>';
    });
    html += '</div>';
  }
  // L1 能量卡
  var ec = warm.energy_card;
  if (ec) {
    /* R2350b（R98-P2-9）：同屏复读——one_liner/reply 里已说过的
     * 词组，能量卡抬头不再重印（实测「干脆、边界清楚」×3）。 */
    var _said = (warm.one_liner || '') + (warm.reply || []).join('');
    var _ew = ec.element_warm || '';
    var _ewSaid = _ew && _said.indexOf(_ew) >= 0;
    html += '<div class="energy-card">';
    html += '<div class="energy-head">本命 <strong>' + esc(ec.element || '') +
      '</strong>' + (_ew && !_ewSaid ? '（' + esc(_ew) + '）' : '') + '· ' +
      esc(ec.element_note || '') + '</div>';
    html += '<div class="energy-grid">';
    if (ec.lucky_colors && ec.lucky_colors.length) {
      /* R3314（R3312-P1-1）：与日卡「开运色（通版今日色）」双口径
       * 标注——命盘这张是本命固定色。 */
      html += '<div class="energy-item"><span class="energy-k">幸运色（本命）</span>' +
        '<span class="energy-v">' + esc(ec.lucky_colors.join(' · ')) +
        '</span></div>';
    }
    if (ec.lucky_numbers && ec.lucky_numbers.length) {
      html += '<div class="energy-item"><span class="energy-k">幸运数字</span>' +
        '<span class="energy-v">' + esc(ec.lucky_numbers.join(' · ')) +
        '</span></div>';
    }
    if (ec.lucky_hours && ec.lucky_hours.length) {
      /* R3314（R3312-P1-2）：本命恒定时段——当日黄历吉凶不同轴，
       * 明示「长期参考」免得与黄历页今日吉凶格互打脸。 */
      html += '<div class="energy-item"><span class="energy-k">本命时段（长期参考）</span>' +
        '<span class="energy-v">' + esc(ec.lucky_hours.join('、')) +
        '</span></div>';
    }
    if (ec.keywords && ec.keywords.length) {
      /* R2350b（R98-P0-2 附带）：一生盘讲「今日」不对题——scope=life
       * 时标签换「本命关键词」（词本身是盘属性，随 five_elements
       * 补齐后已与当日判词一致）。 */
      var _kwLabel = (scope === 'life') ? '本命关键词' : '今日关键词';
      /* R2350b（R98-P2-9）：关键词去重——reply 已说的不再进卡。 */
      var _kws = ec.keywords.filter(function (k) {
        return _said.indexOf(k) < 0;
      });
      if (!_kws.length) _kws = ec.keywords;
      html += '<div class="energy-item"><span class="energy-k">' + _kwLabel +
        '</span><span class="energy-v">' + esc(_kws.join(' / ')) +
        '</span></div>';
    }
    /* R233c（R40-W10）：helper_element（生我之行=补餽方向）此前零露出——
     * 能量卡只说「你是什么」，不说「多沾什么」。 */
    if (ec.helper_element) {
      /* R3314（R3312-P0）：helper_role=泄 时（本命行已旺）补养方向
       * 变成「把旺气匀出去」——标签与话术换向。 */
      var _hDrain = ec.helper_role === '泄';
      html += '<div class="energy-item"><span class="energy-k">' +
        (_hDrain ? '顺一顺' : '补一补') + '</span>' +
        '<span class="energy-v">多沾点「' + esc(ec.helper_element) +
        '」系的能量' + (_hDrain ? '，把旺气匀一匀' : '') + '</span></div>';
    }
    html += '</div>';
    // 幸运项的规则出处：判据 10 要求可追溯，不能只给结果
    if (ec.basis && ec.basis.length) {
      html += '<details class="warm-basis"><summary>这几项是怎么来的</summary><ul>';
      ec.basis.forEach(function (b) {
        /* R2362：内部字段路径过 _basisCn 翻译，不再裸贴 calc.ten_gods。 */
        html += '<li>' + esc(_basisCn(b)) + '</li>';
      });
      html += '</ul></details>';
    }
    html += '</div>';
  }
  // badge：判据 7——存在、含「仅供娱乐」、且不收尾
  if (warm.badge) {
    html += '<div class="warm-badge">' + esc(warm.badge) + '</div>';
  }
  // L2 details：正文常显，推导依据折叠（判据 4）
  /* R216b（UX 队列 U-002）：温柔模式下这批 details 段（排盘坐标/运算摘要等
   * 标题沿用 interpreter 的内部小节名）在结果下半部裸铺约四成篇幅，
   * 「上半截闺蜜、下半截论文」。改为整组收进单个折叠「📜 想看专业依据？」
   * ——事实零删减（DOM 里仍在，判据 4b/6/7 的折叠可核验口径不变），
   * 只是默认不展开。专业模式路径不经此分支，零改动。 */
  /* R3258（用户实测重复）：「排盘坐标」「运算摘要」两节是原样坐标/
   * 摘要——排盘坐标与生辰小卡/命盘/paipan-line 三头碰，运算摘要
   * 逐字等于 calc.summary（字段原表里还有一份）。从人话流剥出，
   * 统一收进调用方的 _proFold 原表折叠；其余小节照常散铺。 */
  var _dets = (warm.details || []).filter(function (d) {
    var t = (d && d.title) || '';
    return t !== '排盘坐标' && t.indexOf('运算摘要') !== 0;
  });
  if (_dets.length && !skipDetailsFold) {   /* R3212：单版化恒走 */
    html += '<details class="warm-basis warm-pro-fold"><summary>📜 想看专业依据？（' +
      _dets.length + ' 项，展开慢慢看）</summary>';
    _dets.forEach(function (d) {
      html += '<div class="interp-sec"><h4>' + esc(d.title || '') + '</h4><ul>';
      (d.lines || []).forEach(function (ln) {
        html += '<li>' + esc(annotatePowers(ln)) + '</li>';
      });
      html += '</ul>';
      if (d.basis && d.basis.length) {
        html += '<details class="warm-basis"><summary>推导依据（' +
          esc(d.basis.length) + ' 条）</summary><ul>';
        d.basis.forEach(function (b) {
          html += '<li>' + esc(_basisCn(b)) + '</li>';
        });
        html += '</ul></details>';
      }
      html += '</div>';
    });
    html += '</details>';
  } else {
    var _secs = '';
    _dets.forEach(function (d) {
      _secs += '<div class="interp-sec"><h4>' + esc(d.title || '') +
        '</h4><ul>';
      (d.lines || []).forEach(function (ln) {
        _secs += '<li>' + esc(ln) + '</li>';
      });
      _secs += '</ul>';
      if (d.basis && d.basis.length) {
        _secs += '<details class="warm-basis"><summary>推导依据（' +
          esc(d.basis.length) + ' 条）</summary><ul>';
        d.basis.forEach(function (b) {
          _secs += '<li>' + esc(_basisCn(b)) + '</li>';
        });
        _secs += '</ul></details>';
      }
      _secs += '</div>';
    });
    /* R3309（probe_first_screen 判据「结果区 ≤4 屏」）：散铺小节默认
     * 展开时，单卡 6 屏——foldSecs 的调用方整组收进一个折叠，事实
     * 零删减（折叠可核验口径不变）。 */
    html += (foldSecs && _dets.length)
      ? '<details class="warm-secs-fold"><summary>📖 细看小满的逐条推演（' +
        _dets.length + ' 节，展开慢慢看）</summary>' + _secs + '</details>'
      : _secs;
  }
  // L3 citations：古籍原文进三级折叠树，**warm 模式下这是唯一的古籍渲染点**
  // （005 判据 5，清偿审查轨 R128a-01）。
  //
  // 原实现的缺陷：这里渲染 warm.citations，而 buildBaziResult 又用 renderHits
  // 渲染了 j.evidence——实测两者同源（12/12 条目对应、citation 逐条相等、
  // citations[i].text === evidence[i].text[:220]），于是同一段《穷通宝鉴》
  // 在页面上出现两次，`.ev-item` 24 个而 API 只有 12 段。
  //
  // 数据源优先 evidence（全文）而非 citations（220 字截断版）：判据 8 要求
  // 展开后与 API 逐字节一致，截断版做不到。evidence 由调用方经
  // renderVoice(j, title) 传入；没有时（如历史详情）回落 citations。
  var cites = (evidence && evidence.length) ? evidence : (warm.citations || []);
  if (cites.length) {
    html += renderCiteTree(cites);
  }
  html += '</div>';
  return html;
}

/** AI 润色容器（specs/006）。独立容器 + 显著标注，与古籍引文区视觉不可混淆
 *  （D-146a 第 3/4 条精神）。j.ai_polish 为 null（关闭/断网/超时）时整块不渲染
 *  ——LLM 永远不是承重墙（D-244a）。 */
function renderAiPolish(j) {
  var ai = j && j.ai_polish;
  if (!ai) return '';
  return '<div class="ai-polish" role="note" aria-label="AI 生成解读">' +
    '<div class="ai-polish-head">✨ AI 解读' +
    /* R230t（R32-P2-21）：badge 原写「再点一次可能不一样」——但该处并
     * 无再生成入口，承诺了一个不存在的交互。改为如实描述。 */
    '<span class="ai-polish-badge">AI 生成 · 仅供娱乐 · 每次生成可能不一样</span></div>' +
    '<p class="ai-polish-text">' + renderRichText(ai) + '</p>' +
    '</div>';
}

/* ── 分享海报（004 M3，D-151a：原生 Canvas 零依赖）──────────────
 * 固定 1080×1440（3:4 竖版），版式完全受控、不随页面 CSS 变化
 * （spec US5 判据 6/7）。同输入必同输出：无随机、无时钟入图。
 * 「仅供娱乐」水印常显（判据 2）；零外部网络请求（判据 3）。
 *
 * R193b（T3.3/B-013）：drawPoster 变外壳，绘制本体拆到 _paintPoster
 * （逻辑坐标恒 1080×1440，ctx.scale 适配目标像素）。
 *   - 默认（opts.auto 非 false）：先全尺寸绘一遍并计时，单次同步耗时
 *     >50ms（长任务阈值）即按 T3.3「低端降级 750×1000」重画一次返回小图；
 *   - opts.auto=false：固定尺寸直绘、不降级——check_poster 的既有判据
 *     （尺寸/字节/水印/耗时）继续按原口径测量；
 *   - opts.low=true：强制 750×1000（可对降级产物直接断言）；
 *   - warmPoster() 在页面空闲时预热字体/栅格管线，消除首次点击冷启动
 *     （main 实测首跑 51.7ms ≥50ms、稳态约 25ms，见台账本轮 §）。 */
/* R2400（R122-P1-1）：海报/分享图生成族拆进 /static/app_poster.js
 * 懒加载——首访少解析 ~70KB 画布代码。所有外部入口走 downloadPoster
 * 同名 stub：点了才拉 chunk，加载后真函数同名接管（后续调用零开销）。
 * warmPoster 的空闲预热语义 = 提前把组件字节拉进缓存，
 * 首点「分享图」仍秒开；SW 壳清单含本 chunk，离线也可用。 */
var _posterJsLoad = null;
/* R2500（R143-SW-P3）：懒 chunk 裸路径不带 ?v=——旧页面开着时新 SW
 * 接管，拉 chunk 拿到新字节混注进旧运行时。与 app.js 同源取 ?v。 */
function _assetV() {
  try {
    var _ss = document.querySelectorAll('script[src*="/static/app.js"]');
    var _m = _ss.length &&
      (_ss[_ss.length - 1].getAttribute('src') || '').match(/[?&]v=([^&]+)/);
    return _m ? '?v=' + _m[1] : '';
  } catch (eAV) { return ''; }
}
var _ASSET_V = null;
function _assetSuffix() {
  if (_ASSET_V === null) _ASSET_V = _assetV();
  return _ASSET_V;
}
function _loadPosterJs() {
  if (!_posterJsLoad) {
    _posterJsLoad = new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = '/static/app_poster.js' + _assetSuffix();
      s.onload = function () { res(); };
      s.onerror = function () {
        _posterJsLoad = null;
        rej(new Error('海报组件没加载上：网好了再点一次'));
      };
      document.head.appendChild(s);
    });
  }
  return _posterJsLoad;
}
function warmPoster() {
  /* 空闲预热：把海报 chunk 拉下来即可——真的点画布时只差 eval。
   * 预拉失败的 rejection 静默吞——预热不是用户动作，不该炸 pageerror。 */
  try { _loadPosterJs().catch(function () {}); } catch (e) {}
}
/* R3317-F：海报回流二维码——vendored qrcode-generator 懒加载，
 * 加载失败静默降级为无码海报（QR 是增值件不是阻断件）。 */
var _qrJsLoad = null;
function _loadQrJs() {
  if (!_qrJsLoad) {
    _qrJsLoad = new Promise(function (res) {
      var s = document.createElement('script');
      s.src = '/static/libs/qrcode.min.js' + _assetSuffix();
      s.onload = function () { res(); };
      s.onerror = function () { res(); };   /* 缺库也能画海报 */
      document.head.appendChild(s);
    });
  }
  return _qrJsLoad;
}
function downloadPoster() {
  var _a = arguments;
  return _loadPosterJs().then(function () {
    return _loadQrJs();
  }).then(function () {
    return downloadPoster.apply(null, _a);
  }).catch(function (e) {
    /* chunk 加载失败兜底——不然未处理 rejection 静默吞掉用户的点击。 */
    showToast((e && e.message) || '海报组件没加载上：网好了再点一次', 'warn');
  });
}
/* R3317：开运壁纸同款懒加载——app_wallpaper.js 按需拉取。 */
var _wapJsLoad = null;
function _loadWapJs() {
  if (!_wapJsLoad) {
    _wapJsLoad = new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = '/static/app_wallpaper.js' + _assetSuffix();
      s.onload = function () { res(); };
      s.onerror = function () {
        _wapJsLoad = null;
        rej(new Error('壁纸组件没加载上：网好了再点一次'));
      };
      document.head.appendChild(s);
    });
  }
  return _wapJsLoad;
}
function downloadWallpaper() {
  var _a = arguments;
  return _loadWapJs().then(function () {
    return downloadWallpaper.apply(null, _a);
  }).catch(function (e) {
    showToast((e && e.message) || '壁纸组件没加载上：网好了再点一次', 'warn');
  });
}
/* R218a-巡2（N-02）：海报浮层——背景遮罩 + 中央海报图 + 关闭按钮 +
 * 长按保存提示。点遮罩/ESC 关闭，多次调用只重建内容。 */
function showPosterModal(canvas, view, j) {
  var existing = document.getElementById('posterModal');
  /* R230j（R22-P3-1）：直接 remove() 会绕过 closePosterModal()——旧
   * backdrop 的 _posterOnKey 引用被覆盖后 keydown 监听永久残留。
   * 走正经关闭路径（摘监听+焦点归还），再兜底 remove。 */
  if (existing) {
    closePosterModal();
    if (existing.isConnected) existing.remove();
  }
  var backdrop = document.createElement('div');
  backdrop.id = 'posterModal';
  backdrop.className = 'poster-modal-backdrop';
  /* 视图名 → 人话标题（R231c：与下载文件名共用 _POSTER_TITLES） */
  var viewTitle = _POSTER_TITLES[view] || '命盘海报';
  /* R2350a（R94-P1-3）：黄历海报标题跟卡面日（「明日宜忌」）。
   * 本函数签名只有 canvas/view——日期从 LAST_RESULT 取。 */
  if (view === 'huangli') {
    try {
      var _j3 = (LAST_RESULT.huangli || {}).json;
      var _jd3 = _j3 && _j3.date;
      if (_jd3) {
        var _tt0 = new Date(); _tt0.setHours(0, 0, 0, 0);
        var _dw3 = _hlDayWord(Math.round(
          (new Date(_jd3 + 'T00:00:00') - _tt0) / 864e5));
        viewTitle = (_dw3 === '今天' ? '今日' : _dw3) + '宜忌';
      }
    } catch (eVT) {}
  }
  /* R230r（R29-#7）：toDataURL 在画布被污染时会抛 SecurityError——
   * 原来裸调用让「文件已下载、浮层弹不出」成半失败态。 */
  var img;
  try {
    img = canvas.toDataURL('image/png');
  } catch (e) {
    showToast('海报预览生成失败，但图片已保存到下载文件夹', 'warn');
    return;
  }
  _posterTrigger = document.activeElement;   /* R228d：关闭时焦点归还 */
  backdrop.innerHTML =
    /* R228d：补 dialog 语义——原来纯 div，读屏不知道是模态框，Tab 会走出
     * 遮罩跑到主区控件。 */
    '<div class="poster-modal" role="dialog" aria-modal="true" ' +
      'aria-label="' + esc(viewTitle) + ' 分享图预览">' +
      '<div class="poster-modal-head">' +
        '<span class="poster-modal-title">📸 ' + esc(viewTitle) + '</span>' +
        '<button type="button" class="poster-modal-close" aria-label="关闭">×</button>' +
      '</div>' +
      '<div class="poster-modal-body">' +
        /* R2349h（R69-P3-13）：alt 写死「命盘海报」——黄历/塔罗图也被
         * 读成命盘。拼视图名+日期。 */
        '<img class="poster-modal-img" src="' + img + '" alt="' +
          esc(viewTitle) + ' 分享图">' +
      '</div>' +
      '<div class="poster-modal-tip">💡 ' +
        ((typeof navigator === 'undefined' || !_touchOnly())
          ? '已自动下载到下载文件夹 · 也可右键另存 · 保存后可设为锁屏/壁纸，小满每天陪你睁眼 · 发给闺蜜一起测～'
          /* R2353（R110-P2-3）：小红书 webview 长按菜单由 app 侧实现，
           * 对 data-URI 图不一定有「保存图片」——改截图口径。 */
          : (/xhsdiscover|XHSAPP|discover\//i.test(navigator.userAgent || '')
             ? '截图保存，或点下方「复制文案+链接」发给闺蜜～ · 保存后可设为锁屏/壁纸，小满每天陪你睁眼'
             : '长按图片可保存到相册 · 保存后可设为锁屏/壁纸，小满每天陪你睁眼 · 发给闺蜜一起测～')) +
        '</div>' +
      /* R231d（R37-F2）：分享动作行——复制链接（任何环境可用）+ 系统
       * 分享面板（支持 Web Share 的移动浏览器才出现）。 */
      '<div class="poster-modal-actions">' +
        '<button type="button" class="poster-act" id="posterCopyLink">🔗 复制文案+链接</button>' +
        ((typeof navigator !== 'undefined' && navigator.share)
          ? '<button type="button" class="poster-act" id="posterSysShare">📤 分享给朋友</button>' : '') +
      '</div>' +
    '</div>';
  document.body.appendChild(backdrop);
  /* R3355（审-中）：预览 img 换 blob: URL——data: URI 在 iOS Safari /
   * 部分 webview 里长按不弹「保存图片」，blob: 是标准可存图 URL。
   * 编码失败则留 data: 兜底；URL 挂 backdrop 待关闭时回收。 */
  try {
    canvas.toBlob(function (b) {
      if (!b) return;
      var _ie = backdrop.querySelector('.poster-modal-img');
      if (!_ie || !backdrop.isConnected) return;
      var _bu = URL.createObjectURL(b);
      /* data: 副本留 dataset——CSP connect-src 会挡 fetch(blob:)，
       * 闸/兜底要量 PNG 字节时读这个，不靠网络再取。 */
      _ie.dataset.dsrc = _ie.src;
      _ie.src = _bu;
      backdrop._posterBlobUrl = _bu;
    }, 'image/png');
  } catch (eBL) {}
  /* R3304（审-P3）：开奖瞬间未散的 toast 叠在模态上缘（toast-stack
   * z300 > modal z200）——开模态即清场，模态内新 toast 照常出现
   * （复制成功反馈仍要看得见，所以不能降 z）。 */
  try {
    var _ts0 = document.querySelector('.toast-stack');
    if (_ts0) _ts0.innerHTML = '';
  } catch (eTS) {}
  /* R2353（R110-P2-1）：弹层入栈——弹层开着按返回键/手势先关弹层
   * 而不是退回上一视图（微信/XHS webview 左滑返回场景实测踩坑）。
   * 同视图 push（URL 不变，state 多 modal 标记），popstate 侧按
   * 「同视图不 showView」兜住。 */
  try {
    history.pushState({
      view: (history.state && history.state.view) || 'home',
      modal: 'poster' }, '');
    window.__modalPushed = true;
  } catch (ePS) {}
  /* 复制本视图深链——朋友打开直达同一页 */
  var _pcl = backdrop.querySelector('#posterCopyLink');
  if (_pcl) _pcl.addEventListener('click', function () {
    /* R231d（R39-P2-1）：带 from=share 便于落地页换承接文案
     * R3373s：海报视图≠落地视图时经别名表（soulmate→taohua，
     * 否则 ?view=soulmate 是死链静默回首页）。 */
    var url = location.origin + '/?view=' + encodeURIComponent(
      _SHARE_VIEW_ALIAS[view] || view || 'home') + '&from=share';
    /* R2350a（R94-P1-2）：黄历分享链带卡面日——对方打开看到的是
     * 同一张那天，不是 TA 自己的今天。 */
    if (view === 'huangli') {
      try {
        var _sd0 = (el('hlResult') || {}).dataset || {};
        if (_sd0.shownDate) url += '&date=' +
          encodeURIComponent(_sd0.shownDate);
      } catch (eSD) {}
    }
    /* R2350f（R102-P1-1）：结果随链走——塔罗/六爻 seed 确定性可复现，
     * 接收方落地先看到「TA 抽到的那几张/那一卦」再邀她抽自己的。 */
    if ((view === 'tarot' || view === 'liuyao') && j &&
        typeof j.seed === 'number') {
      url += '&s=' + j.seed;
      if (view === 'tarot' && j.n) url += '&tn=' + j.n;
      /* R2354（R112-P1-2/3）：replay 还原上下文——自点牌带 c= 索引
       * 重放 draw_picked（不然 seed 重抽的是另一套牌）；牌阵带
       * sp= 不然收方退化成随缘张数。 */
      if (view === 'tarot' && j.spread_key) {
        url += '&sp=' + encodeURIComponent(j.spread_key);
      }
      if (view === 'tarot' && j.picked && j.draws) {
        url += '&c=' + j.draws.map(function (d) {
          return d.index; }).join(',');
      }
      if (view === 'liuyao' && j.method === 'coins') url += '&m=coins';
    }
    /* R3266（R3247-P2-8）：解梦分享链带象征名（非原文）——收方落地
     * 能喊出「TA 对上了『被追赶』」，隐私线不破。 */
    if (view === 'dream' && j && (j.symbols || [])[0]) {
      url += '&sym=' + encodeURIComponent(
        String(j.symbols[0].name).split('/')[0].slice(0, 12));
    }
    /* R3369（审-P1-1）：古籍分享链带上下文——检索词/书号随链，
     * 收方落地直接看到同一份结果，不只开空页。 */
    if (view === 'read') {
      try {
        var _rqv = (el('rq') || {}).value || '';
        if (_rqv.trim()) url += '&rq=' +
          encodeURIComponent(_rqv.trim().slice(0, 100));
        var _bwv = (el('bswork') || {}).value || '';
        if (_bwv.trim()) url += '&bs=' +
          encodeURIComponent(_bwv.trim().slice(0, 64));
      } catch (eRV) {}
    }
    /* R2349t（R88-13a）：分享链带昵称——接力页能喊出「谁晒的」。
     * 昵称与生辰不同级：纯显名，不进任何请求体（邀请链已有先例）。 */
    try {
      var _snm = (_meGet('me') || {}).n;
      if (_snm) url += '&n=' + encodeURIComponent(String(_snm).slice(0, 24));
    } catch (eSN) {}
    /* R3260：合盘分享链带 a/b/rel——收方落地预填+自动跑一遍
     * 「TA 测的那对」，不再只开空抽屉。sign 名服务端归一后回传
     * （j.a='巨蟹'），直编进参；落地侧按 _SIGNS 白名单校验。 */
    if (view === 'xzm' && j && j.a && j.b) {
      url += '&a=' + encodeURIComponent(String(j.a).slice(0, 4)) +
             '&b=' + encodeURIComponent(String(j.b).slice(0, 4));
      if (j._rel) url += '&rel=' + encodeURIComponent(j._rel);
    }
    /* R3353（审-P2）：明星合盘分享链带 celeb=<名>——收方落地
     * 还原「和 X 合盘」语境。名单名是公开资料级参数，不带生辰。 */
    if (view === 'hehun' && __hhCeleb && __hhCeleb.n) {
      url += '&celeb=' + encodeURIComponent(String(__hhCeleb.n).slice(0, 16));
    }
    var ok = function () { showToast(_dayPick(['链接已复制，发给 TA 吧','复制好啦，发给 TA 看看','已复制：等 TA 打开'], 'copy'), 'ok'); };
    /* R3303-P1：微信内嵌没有地址栏——「手动复制地址栏」是伪指引
     * 死路。复制被拒直接弹可选中文本域，长按全选就有活路。 */
    var bad = function () {
      try { _showTextExportModal('复制链接', _clipPayload, '长按下面文本全选复制，发给 TA 吧'); }
      catch (eM) { showToast('复制没成功，可截图这个链接发给 TA', 'warn'); }
    };
    /* R2350f（R102-P1-12）：复制内容改为「钩子文案 + URL」——微信/
     * 评论区场景贴一串裸链接，接收方零语境不知道点了会看到什么。 */
    var _clipPayload = _shareText(view).trim() + ' ' + url;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(_clipPayload).then(ok, bad);
    } else {
      try {
        var _ta = document.createElement('textarea');
        _ta.value = _clipPayload; _ta.style.position = 'fixed'; _ta.style.opacity = '0';
        document.body.appendChild(_ta); _ta.select();
        document.execCommand('copy') ? ok() : bad();
        _ta.remove();
      } catch (e) { bad(); }
    }
  });
  /* 系统分享面板——优先分享图文件，不支持文件则退文本+链接 */
  var _pss = backdrop.querySelector('#posterSysShare');
  if (_pss) _pss.addEventListener('click', function () {
    var url = location.origin + '/?view=' + encodeURIComponent(
      _SHARE_VIEW_ALIAS[view] || view || 'home') + '&from=share';
    if (view === 'huangli') {
      try {
        var _sd1 = (el('hlResult') || {}).dataset || {};
        if (_sd1.shownDate) url += '&date=' +
          encodeURIComponent(_sd1.shownDate);
      } catch (eSD1) {}
    }
    if ((view === 'tarot' || view === 'liuyao') && j &&
        typeof j.seed === 'number') {
      url += '&s=' + j.seed;
      if (view === 'tarot' && j.n) url += '&tn=' + j.n;
      /* R2354（R112-P1-2/3）：replay 还原上下文——自点牌带 c= 索引
       * 重放 draw_picked（不然 seed 重抽的是另一套牌）；牌阵带
       * sp= 不然收方退化成随缘张数。 */
      if (view === 'tarot' && j.spread_key) {
        url += '&sp=' + encodeURIComponent(j.spread_key);
      }
      if (view === 'tarot' && j.picked && j.draws) {
        url += '&c=' + j.draws.map(function (d) {
          return d.index; }).join(',');
      }
      if (view === 'liuyao' && j.method === 'coins') url += '&m=coins';
    }
    if (view === 'xzm' && j && j.a && j.b) {
      url += '&a=' + encodeURIComponent(String(j.a).slice(0, 4)) +
             '&b=' + encodeURIComponent(String(j.b).slice(0, 4));
      if (j._rel) url += '&rel=' + encodeURIComponent(j._rel);
    }
    /* R3353（审-P2）：系统分享链同带 celeb。 */
    if (view === 'hehun' && __hhCeleb && __hhCeleb.n) {
      url += '&celeb=' + encodeURIComponent(String(__hhCeleb.n).slice(0, 16));
    }
    /* R3266：系统分享链同带 dream sym。 */
    if (view === 'dream' && j && (j.symbols || [])[0]) {
      url += '&sym=' + encodeURIComponent(
        String(j.symbols[0].name).split('/')[0].slice(0, 12));
    }
    /* R3369（审-P1-1）：系统分享链同带 rq/bs。 */
    if (view === 'read') {
      try {
        var _rqv2 = (el('rq') || {}).value || '';
        if (_rqv2.trim()) url += '&rq=' +
          encodeURIComponent(_rqv2.trim().slice(0, 100));
        var _bwv2 = (el('bswork') || {}).value || '';
        if (_bwv2.trim()) url += '&bs=' +
          encodeURIComponent(_bwv2.trim().slice(0, 64));
      } catch (eRV2) {}
    }
    /* R2349t（R88-13a）：系统分享链同样带昵称。 */
    try {
      var _snm2 = (_meGet('me') || {}).n;
      if (_snm2) url += '&n=' + encodeURIComponent(String(_snm2).slice(0, 24));
    } catch (eSN2) {}
    canvas.toBlob(function (blob) {
      var f = blob && (function () {
        try { return new File([blob], '小满-' + viewTitle + '.png', { type: 'image/png' }); }
        catch (e) { return null; }
      })();
      if (f && (!navigator.canShare || navigator.canShare({ files: [f] }))) {
        /* R233t（R51-P2-18b）：files 分支此前只发纯图——接收方拿不到
         * 链接，回流断链。text+url 随文件一起给（iOS 已支持并存）。 */
        navigator.share({ files: [f], title: '小满的解忧铺',
          text: _shareText(view) + url }).catch(function () {});
      } else {
        navigator.share({ title: '小满的解忧铺',
          text: _shareText(view).trim(), url: url }).catch(function () {});
      }
    }, 'image/png');
  });
  /* 触发动画 */
  requestAnimationFrame(function () { backdrop.classList.add('open'); });
  /* R233f（R43-P3-18）：开层时主区打 inert——键盘圈防 Tab，inert
   * 防读屏虚拟光标读到被遮内容。 */
  _mainInert(true, backdrop);
  /* R228d：焦点移入弹层（关闭钮），否则键盘 Tab 走主区 */
  var _pcb = backdrop.querySelector('.poster-modal-close');
  if (_pcb) _pcb.focus();
  /* 关闭路径 1：点关闭按钮 */
  backdrop.querySelector('.poster-modal-close').addEventListener('click', closePosterModal);
  /* 关闭路径 2：点遮罩（点 modal 自身，不含内容） */
  backdrop.addEventListener('click', function (e) {
    if (e.target === backdrop) closePosterModal();
  });
  /* 关闭路径 3：ESC 键。R228c：onKey 存模块级——原来只在按 Esc 的分支里
   * 才 removeEventListener，点关闭钮/遮罩关闭时监听永久残留，每开一次
   * 海报就累加一个 document 级 keydown。 */
  _posterOnKey = function (e) {
    if (e.key === 'Escape' || e.keyCode === 27) closePosterModal();
    /* R228n：焦点圈——role=dialog 光有语义不够，Tab 还能逃出遮罩
     * 落进主区（实测 activeElement 跑到 #shareDaily）。modal 内只有
     * 关闭钮可聚焦，Tab 一律圈回它。 */
    /* R231f（R38-P1-1）：焦点圈在所有可聚焦元素间循环——原来一律圈回
     * 关闭钮，「复制链接/分享」对键盘用户永远不可达。 */
    if (e.key === 'Tab' || e.keyCode === 9) {
      var _f = backdrop.querySelectorAll(
        'button,[href],[tabindex]:not([tabindex="-1"])');
      if (!_f.length) return;
      var _first = _f[0], _last = _f[_f.length - 1];
      if (e.shiftKey && document.activeElement === _first) {
        e.preventDefault(); _last.focus();
      } else if (!e.shiftKey && document.activeElement === _last) {
        e.preventDefault(); _first.focus();
      } else if (!backdrop.contains(document.activeElement)) {
        e.preventDefault(); _first.focus();
      }
    }
  };
  document.addEventListener('keydown', _posterOnKey);
}
var _posterOnKey = null;
var _posterTrigger = null;
/* R2353（R110-P1-1）：展示式导出——iOS 微信/触屏端没有用户可见的
 * 下载管理器，blob/attachment 静默丢弃还误报成功。改走弹层：
 * 文本进 readonly textarea + 「复制全部」钮（clipboard+execCommand
 * 兜底），用户可存备忘录/发文件传输助手。复用 #posterModal 关闭链。 */
function _showTextExportModal(title, text, tipText) {
  var existing = document.getElementById('posterModal');
  if (existing) { closePosterModal(); if (existing.isConnected) existing.remove(); }
  var backdrop = document.createElement('div');
  backdrop.id = 'posterModal';
  backdrop.className = 'poster-modal-backdrop';
  _posterTrigger = document.activeElement;
  backdrop.innerHTML =
    '<div class="poster-modal" role="dialog" aria-modal="true" aria-label="' +
      esc(title) + '">' +
      '<div class="poster-modal-head">' +
        '<span class="poster-modal-title">📦 ' + esc(title) + '</span>' +
        '<button type="button" class="poster-modal-close" aria-label="关闭">×</button>' +
      '</div>' +
      '<div class="poster-modal-body">' +
        '<textarea readonly class="export-modal-ta" aria-label="备份内容">' +
          esc(text) + '</textarea>' +
      '</div>' +
      '<div class="poster-modal-tip">💡 ' + esc(tipText || '') + '</div>' +
      '<div class="poster-modal-actions">' +
        '<button type="button" class="poster-act" id="exportCopyAll">📋 复制全部</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(backdrop);
  /* R3304（审-P3）：开奖瞬间未散的 toast 叠在模态上缘（toast-stack
   * z300 > modal z200）——开模态即清场，模态内新 toast 照常出现
   * （复制成功反馈仍要看得见，所以不能降 z）。 */
  try {
    var _ts0 = document.querySelector('.toast-stack');
    if (_ts0) _ts0.innerHTML = '';
  } catch (eTS) {}
  /* R2353（R110-P2-1）：弹层入栈——弹层开着按返回键/手势先关弹层
   * 而不是退回上一视图（微信/XHS webview 左滑返回场景实测踩坑）。
   * 同视图 push（URL 不变，state 多 modal 标记），popstate 侧按
   * 「同视图不 showView」兜住。 */
  try {
    history.pushState({
      view: (history.state && history.state.view) || 'home',
      modal: 'poster' }, '');
    window.__modalPushed = true;
  } catch (ePS) {}
  var _eca = backdrop.querySelector('#exportCopyAll');
  if (_eca) _eca.addEventListener('click', function () {
    var ok = function () { showToast('已复制全部内容：去备忘录粘贴留存吧', 'ok'); };
    var bad = function () { showToast('复制没成功：长按文本手动全选复制', 'warn'); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(ok, bad);
    } else {
      try {
        var _ta2 = backdrop.querySelector('textarea');
        _ta2.focus(); _ta2.select();
        document.execCommand('copy') ? ok() : bad();
      } catch (e) { bad(); }
    }
  });
  requestAnimationFrame(function () { backdrop.classList.add('open'); });
  _mainInert(true, backdrop);
  var _pcb2 = backdrop.querySelector('.poster-modal-close');
  if (_pcb2) _pcb2.focus();
  _pcb2.addEventListener('click', closePosterModal);
  backdrop.addEventListener('click', function (e) {
    if (e.target === backdrop) closePosterModal();
  });
  _posterOnKey = function (e) {
    if (e.key === 'Escape' || e.keyCode === 27) closePosterModal();
    if (e.key === 'Tab' || e.keyCode === 9) {
      var _f = backdrop.querySelectorAll(
        'button,[href],textarea,[tabindex]:not([tabindex="-1"])');
      if (!_f.length) return;
      var _first = _f[0], _last = _f[_f.length - 1];
      if (e.shiftKey && document.activeElement === _first) {
        e.preventDefault(); _last.focus();
      } else if (!e.shiftKey && document.activeElement === _last) {
        e.preventDefault(); _first.focus();
      } else if (!backdrop.contains(document.activeElement)) {
        e.preventDefault(); _first.focus();
      }
    }
  };
  document.addEventListener('keydown', _posterOnKey);
}
/* 触屏/内嵌浏览器判定——导出/下载类操作在这些环境该走展示式。 */
function _touchOnly() {
  /* R3369（审-低-11）：触屏笔记本 maxTouchPoints>0 一直被当手机——
   * 有精密指针（鼠标/触控板）的设备照常走下载，不只看触点。 */
  try {
    return (navigator.maxTouchPoints > 0 || 'ontouchstart' in window) &&
      window.matchMedia('(pointer:coarse)').matches &&
      !window.matchMedia('(any-pointer:fine)').matches;
  } catch (e) {
    return navigator.maxTouchPoints > 0 || 'ontouchstart' in window;
  }
}
function _exportShowOnly() {
  if (typeof navigator === 'undefined') return false;
  return _touchOnly() ||
    /MicroMessenger|xhsdiscover|XHSAPP/i.test(navigator.userAgent || '');
}
/* R229c：_rmBehavior 提升到模块级——此前嵌套在 closePosterModal 体内，
 * 函数声明不外溢，app.js:5006 的调用必然 ReferenceError（排盘历史
 * 「复看」每点必报假错 toast；2254 处同款调用被外层 try 静默吞掉，
 * 每日详情滚动从未发生）。 */
function _rmBehavior() {
  return (window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches)
    ? 'auto' : 'smooth';
}
function closePosterModal() {
  /* R2353（R110-P2-1）：UI 路径关弹层时把 showPosterModal 推的
   * modal 栈项一并弹掉——不然栈里留 {modal:'poster'} 陈旧项，
   * 下一次返回键多走一步「原地」。popstate 回调里的再次调用
   * 因 __modalPushed 已 false 不会重入。 */
  if (window.__modalPushed) {
    window.__modalPushed = false;
    try { history.back(); } catch (eHB) {}
  }
  if (_posterOnKey) {
    document.removeEventListener('keydown', _posterOnKey);
    _posterOnKey = null;
  }
  _mainInert(false);
/* R228d：焦点归还触发的分享钮（读屏/键盘用户不丢位）
 * R233f（R43-P3-20）：celeb「晒一下」场景触发钮已销毁——
 * isConnected 校验，落空回落 #funcGrid（程序可聚焦，不丢位）。 */
  if (_posterTrigger && !_posterTrigger.isConnected) _posterTrigger = null;
  var _fall = _posterTrigger || el('funcGrid');
  _posterTrigger = null;
  if (_fall && _fall.focus) {
    try { _fall.focus({preventScroll:true}); } catch (e) {
      try { _fall.focus(); } catch (e2) {}
    }
  }
  var m = document.getElementById('posterModal');
  if (!m) return;
  /* R3355：blob: 预览图 URL 随模态关闭回收。 */
  try {
    if (m._posterBlobUrl) {
      URL.revokeObjectURL(m._posterBlobUrl); m._posterBlobUrl = null;
    }
  } catch (eRV) {}
  m.classList.remove('open');
  setTimeout(function () { if (m.parentNode) m.parentNode.removeChild(m); }, 200);
}

function _pArr(v) { return Array.isArray(v) ? v : []; }
function _pStr(v) {
  if (v == null || typeof v === 'object') return '';
  return String(v);
}
function _gSlice(v, n) { return Array.from(_pStr(v)).slice(0, n).join(''); }
/* R2351（R109-P1-3）：括号感知截断——切点落在「（秋分…」这类
 * 未闭合括号里时，回退到开括号前（吊半个「（」比少几个字难看）。
 * 只处理最常见的单侧未闭合情形，成对括号内容不完整时不硬切。 */

/** 按当前模式渲染解读区。warm 数据缺失时自动回落专业分支。
 *  evidenceKeys：本响应里存放**全文**引文的键名（各功能不同：排盘是
 *  evidence，六爻是 ben_jing/bian_jing）。warm 分支用它们喂 renderCiteTree，
 *  以满足 005 判据 8（展开原文与 API 逐字节一致）。 */
/* R3258：从 warm.details 剥出的「原样」小节（排盘坐标/运算摘要），
 * 人话流不再铺——与 calc 字段原表一起进唯一的专业折叠。 */
function _warmRawDetails(warm) {
  return ((warm && warm.details) || []).filter(function (d) {
    var t = (d && d.title) || '';
    return t === '排盘坐标' || t.indexOf('运算摘要') === 0;
  });
}
/* R3258：全站唯一的专业折叠——排盘坐标原文 + 运算摘要 + calc 字段原表。
 * 推导链=上方散铺小节（同源不再折第二遍），古籍=renderWarm 引文树
 * （同源不再渲第二份）。bazi 结果页与首页完整解读共用此块。 */
function _proFold(j) {
  if (!j) return '';
  var inner = '';
  _warmRawDetails(j.warm).forEach(function (d) {
    inner += '<h4 class="pv-sub">' + esc(d.title || '') +
      '</h4><ul class="pv-lines">';
    (d.lines || []).forEach(function (ln) {
      inner += '<li>' + esc(ln) + '</li>';
    });
    inner += '</ul>';
  });
  if (j.calc) {
    inner += '<h4 class="pv-sub">字段原表</h4>' + renderCalc(j.calc);
  }
  if (!inner) return '';
  return '<details class="warm-basis warm-pro-fold">' +
    '<summary>📐 排盘坐标与字段原表（展开看）</summary>' + inner + '</details>';
}

function renderVoice(j, proTitle, evidenceKeys, skipLead, foldSecs) {
  /* R3212：双版合并——人话层常驻，推导链收进「专业视角」折叠。 */
  var html = '';
  if (j && j.warm) {
    var ev = [];
    (evidenceKeys || ['evidence']).forEach(function (k) {
      if (j[k] && j[k].length) ev = ev.concat(j[k]);
    });
    /* R3245：skipDetailsFold=true——内层「想看专业依据」与下面的
     * 「专业视角：完整推导链」同源于 interpretation.sections，留外层一个。 */
    html += renderWarm(j.warm, j.interpretation, ev,
                       j.calc && j.calc.scope, true, skipLead, foldSecs);
    /* R3258（用户实测「很多地方重复」）：warm.details 与
     * interpretation.sections 逐字节同源——上方解读层已把同一批小节
     * 散铺出来，这里再折一份「推导链」=同文第二遍。仅当 details 缺失
     * （解读层没东西可铺）时回落渲染，信息不丢。 */
    if (j.interpretation && !(j.warm.details || []).length) {
      html += '<details class="warm-basis warm-pro-fold"><summary>📐 专业视角：' +
        '完整推导链（展开看）</summary>' +
        renderInterpretation(j.interpretation, null) + '</details>';
    }
  } else {
    html += renderInterpretation(j ? j.interpretation : null, proTitle);
  }
  html += renderAiPolish(j);
  return html;
}
/* R3265（R3250-P2）：LAST_RESPONSE/rememberVoice 随 voiceMode
 * 死分支一并下线——登记的重画/rebind 链已无调用方；_rbX 首绑
 * 直调不受影响。 */



/** 确定性解读（guji.interpreter 的输出）。按 sections 结构渲染，不解析
 *  markdown——text 字段只在没有 sections 时兜底展示。
 *  **这个函数是专业模式的渲染路径，判据 9 要求它不被改写。** */
function renderInterpretation(interp, title) {
  if (!interp) return '';
  /* R216b 续（U-007）：内部判据编号（G7：无证据不推测 等）不得出现在用户
   * 界面——显示层剥括注，API/基线字节零改动。 */
  const _stripInternal = function (t) {
    /* R233g（R44-P0-2）：裸「（G7）」无冒号形态此前漏剥——补上。 */
    return String(t).replace(/（G[0-9]+[：:][^）]*）/g, '')
      .replace(/\(G[0-9]+:[^)]*\)/g, '').replace(/（G[0-9]+）/g, '');
  };
  let html = '<h3 style="margin-top:20px;color:var(--c-tarot);">' +
    esc(title || '📖 解读') +
    '<span class="interp-badge">小满解读</span></h3>';   /* v3 P6：不向用户暴露引擎串 */
  const secs = interp.sections || [];
  if (secs.length) {
    secs.forEach(function (s) {
      html += '<div class="interp-sec"><h4>' + esc(s.title || '') + '</h4><ul>';
      (s.lines || []).forEach(function (ln) {
        html += '<li>' + esc(_stripInternal(ln)) + '</li>';
      });
      html += '</ul></div>';
    });
  } else if (interp.text) {
    html += '<div class="llm-text">' + esc(interp.text) + '</div>';
  }
  const cites = interp.citations || [];
  if (cites.length) {
    html += '<div class="interp-sec"><h4>古籍原文依据</h4>';
    cites.forEach(function (c) {
      html += '<div class="ev-item"><div class="ev-meta">' + esc(humanCite(c.citation || '')) + '</div>' +
        '<div class="ev-text">' + esc(c.text || '') + '</div></div>';
    });
    html += '</div>';
  }
  if (interp.basis && interp.basis.length) {
    /* R2349j（R71-P1-16）：依据字段键名中文化——paipan.render 这类路径
     * 对受众是乱码；原值收进 title 供核对。 */
    /* R2362：与 warm-basis/海报同一翻译器——局部 _BASIS_CN 并入全局
     * _basisCn（覆盖面更全：calc.days/dayun、liuyao/tarot/evidence 系）。 */
    var _basisCnList = interp.basis.map(function (b) { return _basisCn(b); });
    html += '<div class="interp-basis" title="' +
      esc(interp.basis.join(' / ')) + '">依据：' +
      esc(_basisCnList.join(' / ')) + '</div>';
  }
  if (interp.disclaimer) {
    /* R216b 续5（V-003）：「非生成文本、同输入必同输出」技术腔——
     * 显示层换成人话；API/基线字节零改动。 */
    var _d = String(interp.disclaimer);
    if (_d.indexOf('非生成文本') !== -1) {
      _d = '这些解读由固定规则生成：同样的问题，答案不会变来变去～';
    }
    html += '<div class="interp-disclaimer interp-disclaimer-soft">' + esc(_d) + '</div>';
  }
  return html;
}

/** 运算事实块（bazi calc 的任意子结构）。原实现用 Object.entries 通吃，
 *  其中一处模板串把 `</strong>` 写成 `</` + 变量（R000a-05）——此处重写。 */
function renderCalc(calc) {
  if (!calc) return '';
  let html = '<div class="calc-grid">';
  let i = 0;
  Object.keys(calc).forEach(function (k) {
    if (k === 'summary' || k === 'scope') return;
    const v = calc[k];
    /* R2350b（R98-P2-10）：空数组/空对象跳过——否则 pro 页只剩一个
     * 光秃秃的字段名标题（实测 relations=[] 时白挂一行）。 */
    if (Array.isArray(v) && !v.length) return;
    if (v && typeof v === 'object' && !Object.keys(v).length) return;
    const c = colorAt(i);
    i += 1;
    html += '<div class="calc-block" style="border-left:3px solid ' + c + ';">' +
      '<h3 style="color:' + c + ';">' + esc(_calcKeyCn(k)) + '</h3>';
    if (Array.isArray(v)) {
      html += '<ul>';
      v.forEach(function (item) {
        if (item && typeof item === 'object') {
          const parts = [];
          Object.keys(item).forEach(function (ik) {
            if (ik === 'basis') return;
            var _ikc = _calcFieldCn(ik);
            parts.push((_ikc ? '<strong>' + esc(_ikc) + '</strong>：' : '') +
              esc(fmtScalar(item[ik])));
          });
          html += '<li>' + parts.join('　') +
            (item.basis ? '<span class="basis"> [' + esc(item.basis) + ']</span>' : '') +
            '</li>';
        } else {
          html += '<li>' + esc(fmtScalar(item)) + '</li>';
        }
      });
      html += '</ul>';
    } else if (v && typeof v === 'object') {
      html += '<ul>';
      Object.keys(v).forEach(function (ik) {
        var _ikc2 = _calcFieldCn(ik);
        html += '<li>' + (_ikc2 ? '<strong>' + esc(_ikc2) + '</strong>：' : '') +
          esc(fmtScalar(v[ik])) + '</li>';
      });
      html += '</ul>';
    } else {
      html += '<p>' + esc(fmtScalar(v)) + '</p>';
    }
    html += '</div>';
  });
  html += '</div>';
  if (calc.summary) {
    html += '<div class="calc-summary">' + esc(calc.summary) + '</div>';
  }
  return html;
}

/** 标量/小结构 → 展示串。数组与对象在此压平，避免出现 "[object Object]"。 */
/* R3221：ISO 时间戳 → 人话——今天 HH:MM / M月D日 HH:MM / 跨年带年。
 * app_research.js 复用此全局（它懒加载在后）。 */
function _fmtWhen(s) {
  var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(String(s || ''));
  if (!m) return String(s || '').replace('T', ' ').replace(/\+.*/, '').slice(0, 16);
  var now = new Date();
  var today = now.getFullYear() + '-' + String(now.getMonth() + 1).padStart(2, '0') +
    '-' + String(now.getDate()).padStart(2, '0');
  var dstr = m[1] + '-' + m[2] + '-' + m[3];
  var hm = m[4] + ':' + m[5];
  if (dstr === today) return '今天 ' + hm;
  if (m[1] === String(now.getFullYear()))
    return parseInt(m[2], 10) + '月' + parseInt(m[3], 10) + '日 ' + hm;
  return m[1] + '年' + parseInt(m[2], 10) + '月' + parseInt(m[3], 10) + '日';
}

function fmtScalar(v) {
  if (v == null) return '—';
  if (Array.isArray(v)) {
    return v.map(function (x) {
      return (x && typeof x === 'object')
        ? Object.keys(x).map(function (k) {
            var _kc = _calcFieldCn(k);
            return (_kc ? _kc + ':' : '') + fmtScalar(x[k]);
          }).join(' ')
        : fmtScalar(x);
    }).join('、') || '—';
  }
  if (typeof v === 'object') {
    return Object.keys(v).map(function (k) {
      var _kc2 = _calcFieldCn(k);
      return (_kc2 ? _kc2 + ' ' : '') + fmtScalar(v[k]);
    }).join('、') || '—';
  }
  if (typeof v === 'boolean') return v ? '是' : '否';
  return String(v);
}

/* R2362（用户直报）：后端 basis 是内部字段路径（calc.ten_gods[].god/basis、
 * liuyao.render_hexagram(ben/bian).gua_name…），多个渲染点曾把它原样
 * 贴屏/贴上海报。统一过这个翻译器：已知键段换中文，残余技术符清掉。 */
var _BASIS_KEY_CN = {
  'calc.ten_gods': '十神格局', 'calc.five_elements': '五行分布',
  'calc.relations': '地支关系', 'calc.day_luck': '流日',
  'calc.days': '逐日干支', 'calc.dayun': '大运',
  'calc.summary': '总评', 'paipan.render': '命盘四柱',
  'paipan.nayin': '纳音', 'liuyao.render_hexagram': '卦象推演',
  'tarot.draw': '牌面'
};
var _BASIS_ROOT_CN = {
  calc: '命盘运算', paipan: '命盘', liuyao: '卦象推演', tarot: '塔罗牌面',
  evidence: '古籍检索', comparisons: '对照结论', ben: '本卦', bian: '变卦',
  question: '问题', warm: '温柔版', cross_ref: '交叉印证',
  name: '牌名', upright_kw: '正位关键词', reversed_kw: '逆位关键词',
  upright: '正逆位', meaning: '牌义', position: '位置',
  arcana: '牌系', suit: '花色', card: '牌',
  gua_name: '卦名', moving_lines: '动爻', work_id: '书名',
  file: '文件', layer: '层级', god: '十神', type: '类型', note: '注解',
  day_ganzhi: '日干支', day_branch_rels: '日支关系', pillar: '柱',
  gan_rel: '干关系', counts: '计数', strong: '强', missing: '缺',
  scope: '范围', render: '排盘', nayin: '纳音', draw: '抽牌',
  keywords: '关键词', basis: '依据', title: '题名', units: '条目数',
  method: '方式', claim: '结论', line: '条目', findings: '发现',
  duration: '时长', score: '分', level: '等级', date: '日期',
  /* R3221：renderCalc 嵌套键补齐——排盘坐标展开不再露英文键名。 */
  pos: '位次', gan: '天干', zhi: '地支', wx: '五行', wuxing: '五行',
  rels: '关系', rel: '关系', gua_number: '卦号', gong: '宫',
  gong_wuxing: '宫五行', gong_position: '宫位数', moving: '动爻',
  shi: '世爻', ying: '应爻', is_shi: '世', is_ying: '应',
  shen: '六神', liuqin: '六亲', stem: '天干', branch: '地支',
  heavenly_stem: '天干', earthly_branch: '地支', yang: '阴阳',
  hour_branch_rels: '时支关系',
  strong_tied: '并列偏旺', qi_yun_age: '起运岁数', months: '月份',
  easy: '顺劲月', hard: '留神月', ganzhi: '干支', verdict: '判词',
  peach_zhi: '桃花支', hit_pillars: '命中柱', strength: '强弱',
  bands: '档位', band: '档位', friction: '磨合点', sparks: '来电点',
  total: '总数', count: '条数', chars: '字数', units_cnt: '条目',
  hit: '命中', window: '窗口', start_year: '起年', pillar_gz: '柱干支'
};
/* 顶层 calc.* 键 → 中文块名（探不到的落「明细」）。 */
var _CALC_KEY_CN = {
  ten_gods: '十神格局', five_elements: '五行分布', relations: '地支关系',
  day_luck: '流日', days: '逐日干支', dayun: '大运', yearly: '年运',
  qi_yun_age: '起运岁数', cross_ref: '交叉印证', sun_sign: '太阳星座',
  hour_branch_rels: '时支关系', day_ganzhi: '日干支', nayin: '纳音',
  pillar_wx: '四柱五行', life: '命局总述', semantic: '取象',
  question: '所问', verdict: '判词', pillar: '四柱'
};
function _calcKeyCn(k) {
  return _CALC_KEY_CN[k] || _BASIS_KEY_CN['calc.' + k] ||
         _BASIS_ROOT_CN[k] || '明细';
}
function _calcFieldCn(k) {
  /* 嵌套键：命中映射用中文；纯英文未命中不再露键名（只出值）。 */
  return _BASIS_ROOT_CN[k] || _CALC_KEY_CN[k] || '';
}
function _basisCn(b) {
  var s = _pStr(b);
  if (!s) return '';
  var out = s
    .replace(/\[\]/g, '')
    .replace(/[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_.]*/g, function (p) {
      var segs = p.split('.');
      return _BASIS_KEY_CN[segs[0] + '.' + segs[1]] ||
             _BASIS_ROOT_CN[segs[0]] || '';
    })
    .replace(/[A-Za-z_][A-Za-z0-9_]*/g, function (w) {
      return _BASIS_ROOT_CN[w] !== undefined ? _BASIS_ROOT_CN[w] : '';
    })
    .replace(/[（(][^）)]*[）)]/g, function (m) { return ' ' + m + ' '; })
    .replace(/[\s\/\.·]+/g, ' ')
    .replace(/ +[×x] +/g, '×')
    .trim();
  /* 技术符清完只剩名字时兜底成通用说法——永不把裸标识符漏上屏。 */
  return out || '推算依据';
}

/* ── 每日运势 ──────────────────────────────────────────────── */

var DAILY_GEN = 0;

/* R3249a（UX-AUDIT A1 · 用户实测「判词看不懂」）：术语→人话注表——
 * 判词/十神标签永远不裸奔，后跟一句零门槛白话。 */
const _VERDICT_GLOSS = {
  '合缘': '人缘顺、有人搭手', '岁合': '大环境跟你合拍',
  '半合': '暗中有顺劲', '伏吟': '旧事容易重提，宜收尾',
  '岁吟': '老主题回来绕一圈', '无冲无合': '平平常常也是好日子',
  '轻冲': '外围有点小波动', '小凶': '气性偏大，缓一点',
  '小挫': '容易跟自己较劲', '小绊': '小磕绊多一点',
  '同伴力': '做事有人同行', '分享力': '热闹、花销也快',
  '表达力': '适合说出来做出来', '创造力': '点子多、宜尝新',
  '流动财': '进项机会多', '稳定财': '适合慢慢攒',
  '压力位': '被推着走的一天', '规矩位': '宜走流程办正事',
  '直觉力': '适合自己琢磨', '庇护力': '有人托底、稳步累积',
  '吉': '顺', '小吉': '小顺', '平': '平稳',
  '凶': '能量偏低，宜稳宜慢', '缓': '宜稳宜慢'
};
async function loadDaily() {
  const _gen = ++DAILY_GEN;
  /* R3303-P2：弱网死等——预取+回退串行最多 35s 无任何提示。
   * >8s 先给一句可操作的招呼（刷新），不等黑盒转圈。 */
  var _slowT = setTimeout(function () {
    if (_gen === DAILY_GEN) {
      showToast('有点慢呢，不行就刷新一下试试', 'info');
    }
  }, 8000);
  var _slowDone = function () { clearTimeout(_slowT); };
  try {
    /* R228k：/api/xingzuo 缺省即算今天——不再等 daily 回包再串行发，
     * 首屏 23ms 变并行。silent+catch=null 保持原有的失败静默降级。 */
    const _today = todayIso();
    /* R2349l（R73-P1-3）：档案里有生日 → 带 bday 让日卡出
     * 「你的日主×今天」个性行；没有就省略（nil 键不进缓存）。 */
    var _me0 = _meGet('me');
    var _bdayPost = (_me0 && _me0.y && _me0.m && _me0.d)
      ? { date: _today,
          bday: _me0.y + '-' + String(_me0.m).padStart(2, '0') +
                '-' + String(_me0.d).padStart(2, '0') } : null;
    /* R2349u（R90-P0-3）：head 内联预取——此前日签请求要等
     * app.js 594KB eval 完才发（slow4G 实测 6.45s 才出手）。
     * URL/签名逐字一致才吃预取结果；预取失败（null）回退 api()
     * 完整错误链。跨零点重跑时 date 已变，天然不吃。
     * R3307（审-中6）：带档案生日改 POST——签名 'post:'+JSON。 */
    var _durl = _bdayPost ? ('post:' + JSON.stringify(_bdayPost))
                          : ('/api/daily?date=' + _today);
    var _dp = null;
    try { _dp = window.__dailyPref; window.__dailyPref = null; }
    catch (eDP) {}
    const [j, x, tm] = await Promise.all([
      /* R230h（R20-F6）：显式带浏览器日——跨零点时服务器「今天」
       * 与用户本地「今天」可能差一天。 */
      (async function () {
        if (_dp && _dp.url === _durl) {
          var _pj = await _dp.p;
          if (_pj) return _pj;
        }
        /* R3303-P2：预取已耗掉的时间计入总预算——共享同一个
         * AbortController 的 20s deadline，回退不再从 0 起算。 */
        var _dopt = (_dp && _dp.ctl && _dp.ctl.signal)
          ? { signal: _dp.ctl.signal } : {};
        return _bdayPost
          ? postJSON('/api/daily', _bdayPost, _dopt)
          : api('/api/daily?date=' + _today, _dopt);
      })(),
      api('/api/xingzuo?date=' + _today, { silent: true }).catch(function () { return null; }),
      /* R39-P0-1：明天预告——每日回访的最短钩子，走 daily_cache 幂等
       * 成本≈0。 */
      api('/api/daily?date=' + _isoShift(_today, 1), { silent: true })
        .catch(function () { return null; })
    ]);
    if (_gen !== DAILY_GEN) return;   /* 旧请求不得覆盖新结果 */
    window.__lastDaily = j;   /* R198b（US5）：shareDaily 用 */
    /* R3264（R29）：今日护身符按钮可用 */
    var _slk = el('shareLucky');
    if (_slk) _slk.disabled = false;
    var _dwp = el('dailyWap');   /* R3317：日签就绪=壁纸可出 */
    if (_dwp) _dwp.disabled = false;
    /* R2400（R117-P2 时段问候）：顶行标签随时刻换——早/午/晚/夜安，
     * 每天四次见面都说不一样的招呼。 */
    var _greet = el('dailyGreet');
    if (_greet) {
      var _hr = new Date().getHours();
      _greet.textContent =
        (_hr >= 5 && _hr < 11) ? '☀️ 早呀，今日玄学搭子' :
        (_hr >= 11 && _hr < 14) ? '🌤 午安，今日玄学搭子' :
        (_hr >= 14 && _hr < 18) ? '🌟 下午好，今日玄学搭子' :
        (_hr >= 18 && _hr < 23) ? '🌙 晚上好，今日玄学搭子' :
        '🌙 夜安，今日玄学搭子';
    }
    const dateEl = el('dailyDate');
    /* R233q：日期补星期——「2026-09-20 周日」比裸日期更像签 */
    /* R3314（R3311-中2）：再挂农历+日干支——月相按初一十五跑、
     * 农历节一堆，卡面得有农历锚（「2026-10-08 周四 · 农历
     * 八月廿八 · 乙卯日」）。 */
    if (dateEl) dateEl.textContent =
      (j.date || '今天') + (j.date ? ' ' + _weekdayCn(j.date) : '') +
      (j.lunar ? ' · ' + j.lunar : '');
    const level = j.level || '平';
    /* R3248（用户实测「填什么生日都是小吉」）：存了生日的日签大判词
     * 换成「你的」判词——通判 level 是同日同款黄历通胜，差异化在个
     * 人层：
     *   · mine 有真判词（冲合刑害伏吟）→ 圆盘 = mine.verdict，
     *     星级/配色跟个人吉凶走；
     *   · mine=无冲无合 → 圆盘 = 你的十神日标签（压力位/庇护力…），
     *     不同日主开出不同词，星级仍走通判；
     *   · 通判降为星级旁的「通版」标注，不消失。 */
    var _mineH = (j.personal && j.personal.mine) || null;
    var _hMine = !!(_mineH && _mineH.verdict &&
                    _mineH.verdict !== '无冲无合');
    var _hTag = (!_hMine && j.personal && j.personal.label)
                ? String(j.personal.label) : '';
    var _dispLv = level;
    if (_hMine) {
      _dispLv = _mineH.tone === 'up'
        ? (_mineH.verdict === '合缘' ? '吉' : '小吉')
        : (_mineH.tone === 'down'
           ? ((_mineH.verdict === '小凶' || _mineH.verdict === '小挫')
              ? '凶' : '平')
           : '平');
    }
    const levelEl = el('dailyLevel');
    if (levelEl) {
      var _badge = _hMine ? _mineH.verdict
                 : (_hTag || ((level === '凶') ? '缓' : level));
      /* R3251（用户实测「圆框的小凶小吉多余，可以用卡通图替代」）：
       * 圆盘不再糊字——按档位贴心情小熊（吉=向阳熊/小吉=茶杯熊/
       * 平=静坐熊/凶=裹毯撑伞熊），判词移进 aria-label 与星级图例。
       * <img> 挂在 .lv-t 文字上层：图挂掉时 onerror 摘掉自己，
       * 底下文字兜底仍在，离线不断档。 */
      var _lvImg = {'吉':'good','小吉':'sml','平':'mid','凶':'bad'}[_dispLv] || 'mid';
      levelEl.innerHTML = '<span class="lv-t">' + esc(_badge) + '</span>' +
        /* R3257：圆盘贴熊头→横幅场景图——晴山坡/暖灯茶/灰窗/雨毯，
         * 图本身就是判词，环境即档位。 */
        '<img class="lv-b" src="/static/cream/bear-scene-' + _lvImg +
        '.jpg" alt="" loading="lazy" decoding="async" onerror="this.remove()">';
      levelEl.setAttribute('role', 'img');
      levelEl.setAttribute('aria-label',
        '今日运势' + (_hMine ? '（对你）' : '') + '：' + _badge);
      levelEl.className = 'daily-level ' +
        (_dispLv === '吉' ? 'good' : _dispLv === '小吉' ? 'sml' :
         _dispLv === '凶' ? 'bad soft' : 'mid') +
        /* R3248 续：个人判词（mine/十神标签）统一字号档——不再随
         * 吉凶档各自缩字号；通判档位维持原 sized 类。 */
        ((_hMine || _hTag)
          ? (_badge.length > 2 ? ' pv3' : ' pv')
          : '');
      /* R216b 续3（U-009）：凶日不吓人——通判凶标签仍柔化；个人层
       * 的 tooltip 写清判词归属（你的 vs 通版）。 */
      levelEl.title = _hMine
        ? '对你：' + _badge + ' · 今日通版' + level
        : (_hTag
           ? '你的十神日「' + _badge + '」· 今日通版' + level
           : (_dispLv === '凶' ? '今天能量偏低，宜稳宜慢' : ''));
    }
    const starsEl = el('dailyStars');
    if (starsEl) {
      starsEl.innerHTML = renderStars(_dispLv);
      /* R229z续23（R10-#16）：读屏播报「吉·五星」而非逐个星符 */
      starsEl.setAttribute('aria-label', '今日运势' +
        (_hMine ? '（对你）' : '') + '：' +
        (_dispLv === '吉' ? '吉，五星' : _dispLv === '小吉' ? '小吉，四星' :
         _dispLv === '凶' ? '缓，一星' : '平，三星'));
      /* U-009 附带：星级加图例，一星不再语义不明。 */
      var legend = document.getElementById('dailyStarsLegend');
      if (!legend && starsEl.parentElement) {
        legend = document.createElement('span');
        legend.id = 'dailyStarsLegend';
        legend.className = 'stars-legend';
        starsEl.parentElement.appendChild(legend);
      }
      if (legend) legend.textContent = _hMine
        ? '（对你：' + _badge +
          (_VERDICT_GLOSS[_badge] ? ' · ' + _VERDICT_GLOSS[_badge] : '') +
          ' · 通版' + level + '）'
        : (_hTag
           ? '（你的「' + _hTag + '」日' +
             (_VERDICT_GLOSS[_hTag] ? '——' + _VERDICT_GLOSS[_hTag] : '') +
             ' · 通版' + level + '）'
           : (_dispLv === '吉' ? '（五星 · 顺）' :
              _dispLv === '小吉' ? '（四星 · 小顺）' :
              _dispLv === '凶' ? '（今日能量偏低 · 宜稳宜慢）' :
              '（三星 · 平稳）'));
    }
    /* R3249a（UX-AUDIT A1 · 用户实测「点开没有分数，不直观」）：
     * 「今日能量」数字读数——判词对非命理用户是零信息量词，分数是
     * 不需要任何前置知识的通用语言。确定性：同日+同生日=同分
     * （与 _hashPick 同纪律，不落缓存不落库）。 */
    var _lvR = _dispLv === '吉' ? [82, 95] : _dispLv === '小吉' ? [68, 81] :
               _dispLv === '凶' ? [30, 50] : [55, 72];
    var _sdStr = String(j.date || _today) + '|' +
      ((_me0 && _me0.y) ? (_me0.y + '-' + _me0.m + '-' + _me0.d) : 'anon');
    var _sdH = 0;
    for (var _sdi = 0; _sdi < _sdStr.length; _sdi++) {
      _sdH = (_sdH * 31 + _sdStr.charCodeAt(_sdi)) >>> 0;
    }
    var _energy = _lvR[0] + _sdH % (_lvR[1] - _lvR[0] + 1);
    var _scEl = el('dailyScore');
    if (!_scEl && starsEl && starsEl.parentElement) {
      _scEl = document.createElement('div');
      _scEl.id = 'dailyScore';
      _scEl.className = 'daily-score';
      starsEl.parentElement.insertBefore(_scEl, starsEl);
    }
    if (_scEl) {
      /* R3250a（用户实测「一个数字不够吸引」）：数字下面给
       * 能量条——读数到读感的落差，正是测测首屏的拉开点。
       * 幸运色同款 swatch 跟在行尾（后端 lucky 本就确定性派生，
       * 一直没显形，是闲置资产）。 */
      var _lc = (j.lucky && j.lucky.color) || '';
      var _ln = (j.lucky && j.lucky.num) || 0;
      _scEl.innerHTML = '⚡ 今日能量 <strong>' + _energy + '</strong>' +
        '<span class="energy-track" aria-hidden="true"><i style="width:' +
          _energy + '%"></i></span>' +
        (_lc ? '<span class="lucky-chip"><i class="lc-dot" style="background:' +
          (LC_HEX[_lc] || '#d9c9a8') + '"></i>' + esc(_lc) +
          /* R3329（审-P2）：_ln（j.lucky.num）原始拼 innerHTML——
           * 同字段下方幸运数是 esc 的，双口径补上。 */
          (_ln ? ' · ' + esc(_ln) : '') + '</span>' : '');
      /* R3317-D：今日咒语——同日全站同句（晒出去能对上号的社群感），
       * 短促上口的小红书体祈愿句，点一下复制。 */
      var _mtEl = el('dailyMantra');
      if (!_mtEl) {
        _mtEl = document.createElement('div');
        _mtEl.id = 'dailyMantra';
        _mtEl.className = 'daily-mantra';
        _mtEl.title = '点一下复制这句咒语';
        /* R3318（审-P3-2）：裸 div+click 键盘/读屏不可达——
         * role/tabindex + Enter/Space 同链路。 */
        _mtEl.setAttribute('role', 'button');
        _mtEl.setAttribute('tabindex', '0');
        _scEl.parentElement.insertBefore(_mtEl, _scEl.nextSibling);
      }
      /* R3334（CLS）：槽位已预渲染在 DOM——监听器离开创建守卫，
       * data.bound 幂等绑，否则预渲染壳永远没有点击/键盘。 */
      if (_mtEl && !_mtEl.dataset.bound) {
        _mtEl.dataset.bound = '1';
        _mtEl.addEventListener('keydown', function (ev) {
          if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault(); _mtEl.click();
          }
        });
        _mtEl.addEventListener('click', function () {
          var _m = String(_mtEl.dataset.m || '');
          if (!_m) return;
          try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
              navigator.clipboard.writeText(_m).then(
                function () { showToast('咒语复制好啦，去贴上吧', 'ok'); },
                function () { showToast('长按那句手动复制', 'warn'); });
            } else { throw new Error('no clipboard'); }
          } catch (eMC) { showToast('长按那句手动复制', 'info'); }
        });
      }
      var _mt = _dayPick(_MANTRA_POOL,
        'mantra|' + String(j.date || _today));
      _mtEl.dataset.m = _mt;
      _mtEl.dataset.d = String(j.date || _today);
      _mtEl.innerHTML = '✨ 今日咒语 <b>' + esc(_mt) + '</b>';
      /* R3350：咒语册——行尾 ❤️ 收这句进 mantraFav（本机册）。
       * sibling 钮不嵌咒语行：咒语行是 role=button 点按复制，
       * 嵌套会冒泡双触发。已收显「已收」态（同句同日去重）。 */
      var _mfBtn = el('mantraFav');
      if (_mfBtn && !_mfBtn.dataset.bound) {
        _mfBtn.dataset.bound = '1';
        _mfBtn.addEventListener('click', function () {
          var _mm = String(_mtEl.dataset.m || '');
          var _dd = String(_mtEl.dataset.d || todayIso());
          if (!_mm) return;
          if (_mantraFavHas(_mm, _dd)) {
            showToast('这句已经在册子里躺着啦', 'info');
            return;
          }
          var _was = _mantraFavAll().length;
          _mantraFavAdd(_mm, _dd);
          var _now = _mantraFavAll().length;
          _mantraFavSync(_mm, _dd);
          _mantraBookMeta();
          if (_was < 7 && _now >= 7) {
            showToast('咒语册攒到 7 句啦——一天一句刚好念一礼拜', 'ok');
          } else {
            showToast(_dayPick(_MANTRA_FAV_TOAST,
              'mfav|' + _dd + '|' + _now), 'ok');
          }
        });
      }
      try { _mantraFavSync(_mt, String(j.date || _today)); } catch (eMF) {}
      /* R3350：册入口同步——攒了才现身 meta 行。 */
      try { _mantraBookMeta(); } catch (eMB) {}
      /* R3317-G：今日牌——同日全站同一张大阿卡纳（后端 daily_card
       * 字段，确定性 seed=日期）；小缩略图 + 名 + 位向 + 关键词。 */
      var _dcEl = el('dailyTarot');
      if (!_dcEl) {
        _dcEl = document.createElement('div');
        _dcEl.id = 'dailyTarot';
        _dcEl.className = 'daily-card-line';
        _mtEl.parentElement.insertBefore(_dcEl, _mtEl.nextSibling);
      }
      /* R3334（CLS）：预渲染壳在 DOM 时创建守卫不触发——委托点击
       * 离开守卫改 data.bound 幂等绑。 */
      if (_dcEl && !_dcEl.dataset.bound) {
        _dcEl.dataset.bound = '1';
        /* 委托在父节点——innerHTML 每次渲染重建按钮，绑死节点会丢。 */
        _dcEl.addEventListener('click', function (ev) {
          if (!ev.target || ev.target.id !== 'dailyCardDraw') return;
          showView('tarot');
          var s = el('tr_spread'), n = el('tr_n');
          if (s) s.value = 'time';
          if (n) n.value = '3';
          _trSpreadSync();
          doTarot();
        });
      }
      var _dc = j.daily_card || {};
      if (_dc.name) {
        /* R3322-P1：首访 manifest 未到时最多等 1.2s——图迟一点
         * 总比恒缺强（此后命中 Promise 缓存零等待）。 */
        if (!TAROT_MANIFEST) {
          await Promise.race([
            _ensureTarotManifest(),
            new Promise(function (r) { setTimeout(r, 1200); })
          ]);
        }
        var _dcImg = tarotImg(_dc.name);
        /* R3321-P1：牌意展开收进本行——旧 meta 路径（同 id 覆写 +
         * 异 seed 抽牌）已删，本行是「今日牌」唯一来源。 */
        _dcEl.innerHTML =
          (_dcImg
            ? '<img class="dc-thumb' + (_dc.upright ? '' : ' is-reversed') +
              '" src="' + _dcImg + '" alt="">'
            : '') +
          /* R3368（审-P1-1）：文字全包进单个 span——裸文本段各自
           * 成 flex 项，窄屏被挤到 min-content（CJK 一字）逐字
           * 竖排不可读。 */
          '<span class="dc-text">🃏 今日牌 <b>' + esc(_dc.name) +
          '</b> · ' + (_dc.upright ? '正位' : '逆位') +
          ' <i>' + esc(_dc.keywords || '') + '</i></span>' +
          (_dc.meaning
            ? '<button type="button" class="sign-peek" id="tarotPeekBtn"' +
              ' aria-expanded="false" aria-controls="tarotCard">牌意</button>'
            : '') +
          '<button type="button" class="dc-more" id="dailyCardDraw" ' +
          'title="抽一组今天的三张牌">抽三张</button>';
        _dcEl.hidden = false;
        /* 牌意展开卡——数据来自同一份 daily_card（meaning 后端下发）。 */
        var _tc = el('tarotCard');
        if (!_tc) {
          _tc = document.createElement('div');
          _tc.id = 'tarotCard'; _tc.className = 'sign-card'; _tc.hidden = true;
          var _mr3 = document.querySelector('#dailyCard .daily-meta');
          if (_mr3 && _mr3.parentNode) {
            _mr3.parentNode.insertBefore(_tc, _mr3.nextSibling);
          }
        }
        if (_tc) {
          _tc.hidden = true;
          _tc.innerHTML = _dc.meaning
            ? '<strong>' + esc(_dc.name) +
              ' · ' + (_dc.upright ? '正位' : '逆位') + '</strong>' +
              '<span>' + esc(_dc.meaning) + '</span>'
            : '';
        }
        var _tb = el('tarotPeekBtn');
        if (_tb && !_tb.dataset.bound) {
          _tb.dataset.bound = '1';
          _tb.addEventListener('click', function () {
            var c2 = el('tarotCard');
            if (c2) {
              c2.hidden = !c2.hidden;
              _tb.textContent = c2.hidden ? '牌意' : '收起';
              _tb.setAttribute('aria-expanded', c2.hidden ? 'false' : 'true');
            }
          });
        }
      } else {
        _dcEl.hidden = true;
        var _tc0 = el('tarotCard'); if (_tc0) { _tc0.hidden = true; }
      }
    }
    /* R3249d（UX-AUDIT B2 · 用户实测「测测一点开就有几个分」）：
     * 三维度小分——💗感情/💼做事/💰钱袋。不是拍脑袋随机数：以
     * 能量分为底，按你的十神日×冲合关系做命理映射修正
     * （正财偏财补钱袋、官杀补做事、日支六合补感情、六冲刑害减感情），
     * 同日同盘同分、确定性可复现。 */
    var _dimGod = (j.personal && j.personal.god) || '';
    var _dimTone = (_mineH && _mineH.tone) || 'flat';
    var _dimMap = {
      '感情': {'正财':6,'偏财':4,'正官':5,'七杀':3,'伤官':-4,
              '劫财':-6,'比肩':-2,'食神':3,'正印':0,'偏印':-1},
      '做事': {'正官':6,'七杀':4,'正印':5,'偏印':4,'食神':3,
              '伤官':2,'正财':1,'偏财':0,'比肩':-2,'劫财':-3},
      '钱袋': {'正财':7,'偏财':5,'食神':4,'伤官':3,'比肩':-1,
              '劫财':-8,'正官':0,'七杀':-2,'正印':-1,'偏印':-2}
    };
    var _dims = '';
    /* R3250b：翻牌签抽中的小加持——彩条上以「+n」角标显形，
     * 底分仍是确定性内核给的，角标只标增量不混账。 */
    var _buff = null;
    try {
      var _bf = JSON.parse(
        localStorage.getItem('checkinBuff:' + (j.date || _today)) || 'null');
      /* n 是 localStorage 脏值——钳成 1-9 整数再进 HTML，
       * 不 coerce 的话脏串直拼是存储型 XSS。 */
      var _bfn = parseInt(_bf && _bf.n, 10) || 0;
      if (_bf && _bf.d && _bfn >= 1 && _bfn <= 9) {
        _buff = {d: _bf.d, n: _bfn};
      }
    } catch (eBf) {}
    ['感情','做事','钱袋'].forEach(function (dm) {
      var _d = _dimMap[dm] ? (_dimMap[dm][_dimGod] || 0) : 0;
      if (dm === '感情' && _dimTone === 'up') _d += 4;
      if (dm === '感情' && _dimTone === 'down') _d -= 6;
      if (dm === '做事' && _dimTone === 'up') _d += 2;
      var _dh = _hashNum(_sdStr + '|' + dm);
      var _dv = Math.max(25, Math.min(97,
        _energy + _d - 4 + _dh % 9));
      var _ic = dm === '感情' ? '💗' : dm === '做事' ? '💼' : '💰';
      /* R3250a：多数字同排→彩色条（用户原话）——单个数字留纯数字，
       * 三个并列才给图，符合「只在一组数字同场时才可视化」的约定。 */
      var _dcls = dm === '感情' ? 'd-love' : dm === '做事' ? 'd-work'
                  : 'd-money';
      _dims += '<span class="dim-bar ' + _dcls + '">' +
        '<span class="dim-ic">' + _ic + '</span>' +
        '<span class="dim-name">' + dm + '</span>' +
        '<span class="dim-track"><i style="width:' + _dv + '%"></i></span>' +
        '<b class="dim-num">' + _dv + '</b>' +
        (_buff && _buff.d === dm
          ? '<i class="dim-buff" title="翻牌签加持">+' +
            String(_buff.n) + '</i>' : '') +
        '</span>';
    });
    var _dimEl = el('dailyDims');
    if (!_dimEl && _scEl && _scEl.parentElement) {
      _dimEl = document.createElement('div');
      _dimEl.id = 'dailyDims';
      _dimEl.className = 'daily-dims';
      _scEl.parentNode.insertBefore(_dimEl, _scEl.nextSibling);
    }
    if (_dimEl) {
      _dimEl.innerHTML = _dims;
      _dimEl.title = _dimGod
        ? '按你的十神日「' + _dimGod + '」× 今日冲合算的三项小分'
        : '按今天的天时算的三项小分（填生日后按你的盘出）';
    }
    /* R3248（用户实测「summary 永远是同一句」）：存了生日的日签大
     * 字区讲「你的」——summary 吃 personal.line（你的日主×今天的
     * 十神日白话）；通版五行天气挪进 meta 胶囊（dailyDayWx），
     * 没存档的用户照旧看通版。 */
    var _pLine = (j.personal && j.personal.line) ? j.personal.line : '';
    setText('dailySummary', _pLine || (j.summary || ''));
    /* R3260（N5 金句化收尾）：通版判词是签诗池里的可截图句——
     * 上「」金句样式拉开与普通说明文的层级；个人行是事实句
     * （你的日主×今天），保持朴素不抢戏。 */
    var _dsEl = el('dailySummary');
    if (_dsEl) _dsEl.classList.toggle('is-quote', !_pLine);
    /* R216b 续3（U-009）：凶日安抚层——summary 下紧跟一句人话安抚。 */
    var sooth = document.getElementById('dailySoothe');
    if (!sooth) {
      sooth = document.createElement('p');
      sooth.id = 'dailySoothe';
      sooth.className = 'daily-soothe';
      var sm2 = el('dailySummary');
      if (sm2 && sm2.parentElement) sm2.parentElement.insertBefore(sooth, sm2.nextSibling);
    }
    if (sooth) {
      sooth.textContent = (_dispLv === '凶') ?
        /* R2349g（R68-P1-1）：凶日安抚句 3→8——凶是 4 档里最能被记住的
         * 日子，原池 60 天单句能出现 8 次。 */
        _dayPick(['「缓」不是坏日子：只是提醒你今天别硬冲，稳稳的也很好。',
                  '「缓」是让你慢下来，不是让你怕，慢一点反而顺。',
                  '今天能量偏低就把事放小，泡个澡早点睡也算赢。',
                  '低气压天适合摆烂式养生，允许自己今天只做 60 分。',
                  '今天不拼运气拼休息：把节奏放缓就是最优解。',
                  '阴天就宅，点个外卖刷刷剧，明天再战。',
                  '今天的你不需要很厉害，安稳度过就是满分。',
                  '能量低的日子适合充电，早睡一小时比啥都管用。'], 'xiong') : '' ;
      sooth.hidden = (_dispLv !== '凶');
    }
    /* R3249b（UX-AUDIT B3 · 用户实测「累了/沮丧的时候才会打开」）：
     * 情绪接应行——「和小满聊聊」此前埋在第九张功能卡里，用户最
     * 需要它的时刻（看签当下）反而够不着。在日签卡里放一条软入口，
     * 文案随时段换，点了直接替她说出那句开场白。 */
    var _mood = el('dailyMood');
    if (!_mood) {
      _mood = document.createElement('button');
      _mood.type = 'button';
      _mood.id = 'dailyMood';
      _mood.className = 'daily-mood';
      var _mr3 = document.querySelector('#dailyCard .daily-meta');
      if (_mr3 && _mr3.parentNode) {
        _mr3.parentNode.insertBefore(_mood, _mr3.nextSibling);
      }
      _mood.addEventListener('click', function () {
        var _h3 = new Date().getHours();
        var _msg = (_h3 >= 22 || _h3 < 6) ? '有点睡不着，陪我聊两句' :
                   (_h3 < 11 ? '早上好呀，今天有点提不起劲' :
                    '今天有点累，陪我说说话');
        chatOpen();
        var _inp = el('chatInput');
        if (_inp) {
          _inp.value = _msg;
          guardedCall('chatSendBtn', chatSend);
        }
      });
    }
    var _h2 = new Date().getHours();
    /* R3253：软入口补小满头像——「有人接你」的画面感比一行
     * 引导文案更能留人；资产复用 avatar-xiaoman-cream.jpg。 */
    _mood.innerHTML = '<img class="dm-ava" src="/static/cream/' +
      'avatar-xiaoman-cream.jpg" alt="" loading="lazy" decoding="async" ' +
      'onerror="this.remove()"><span>' +
      ((_h2 >= 22 || _h2 < 6)
        ? '睡不着的话，小满在 →'
        : '今天有点累？和小满说两句 →') + '</span>';
    /* R2341（R57-P2-6）：贵人地支转生肖——与海报同口径 */
    setText('dailyNoble', j.noble ? _zhiToAnimal(j.noble) : '—');
    /* R2349g（R68-P0-2）：合拍生肖第二层 */
    setText('dailyPal', j.noble_liuhe ? _zhiToAnimal(j.noble_liuhe) : '—');
    setText('dailyDo', j.do || '—');
    setText('dailyDont', j.dont || '—');
    /* R3264（R32）：今日仪式——宜试试变成可点「做完了」微仪式。 */
    var _dr = el('dailyRitual');
    if (_dr) {
      if (j.do) {
        var _rdone = '';
        try { _rdone = localStorage.getItem('ritual:' + todayIso()) || ''; } catch (eR) {}
        _dr.hidden = false;
        _dr.textContent = _rdone ? '✅ 已做完' : '✅ 做完了';
        _dr.disabled = !!_rdone;
        /* R3322-P2：跨日重渲时清 stay 标——新的一天仪式重新可做。 */
        if (!_rdone) delete _dr.dataset.stayDisabled;
        else _dr.dataset.stayDisabled = '1';
      } else { _dr.hidden = true; }
    }
    /* R233q：签号上卡——「今日第 N 签」的求签感是小红书日签标配 */
    var _sg = el('dailySignNo');
    if (!_sg) {
      _sg = document.createElement('div');
      _sg.id = 'dailySignNo';
      _sg.className = 'daily-meta-item';
      _sg.title = '每天一张签，签号跟着日子走';
      var _mrow = document.querySelector('#dailyCard .daily-meta');
      if (_mrow) _mrow.appendChild(_sg);
    }
    if (_sg) {
      /* R2349l（R73-P1-1）：签号可点——展开这签对应的卦名+白话签意
       * （1–64 映射周易 64 卦，确定性）。签卡挂 .daily-meta 行外——
       * 横滚容器 overflow+mask 会裁剪内部浮卡。 */
      _sg.innerHTML = '📜 今日签号：<strong>第' +
        _signNo(j.date) + '签</strong>' +
        '<button type="button" class="sign-peek" id="signPeekBtn"' +
        ' aria-expanded="false" aria-controls="signCard"' +
        ' title="看看这签说了啥">解签</button>';
      var _scl = el('signCard');
      if (!_scl) {
        _scl = document.createElement('div');
        _scl.id = 'signCard'; _scl.className = 'sign-card';
        _scl.hidden = true;
        var _mr2 = document.querySelector('#dailyCard .daily-meta');
        if (_mr2 && _mr2.parentNode) _mr2.parentNode.insertBefore(_scl, _mr2.nextSibling);
      }
      if (_scl) {
        _scl.innerHTML = '<strong>' +
          esc(_signText(j.date).split('·')[0] || '') + '</strong>' +
          '<span>' + esc(_signText(j.date).split('·')[1] || '') + '</span>';
      }
      var _pk = el('signPeekBtn');
      if (_pk && !_pk.dataset.bound) {
        _pk.dataset.bound = '1';
        _pk.addEventListener('click', function () {
          var sc = el('signCard');
          if (sc) {
            sc.hidden = !sc.hidden;
            _pk.textContent = sc.hidden ? '解签' : '收起';
            _pk.setAttribute('aria-expanded', sc.hidden ? 'false' : 'true');
          }
        });
      }
    }
    /* R2349k（R72-A2）：节日行——首页日卡也要说「今天是中秋」。 */
    /* R2349t（R88-4）：吉签庆祝层——凶有 8 句安抚池兜底，吉此前只有
     * 五颗星干推。情绪曲线两端都接住：安抚句的对偶槽位挂庆祝句。 */
    var _cheer = document.getElementById('dailyCheer');
    var _sooth0 = document.getElementById('dailySoothe');
    if (!_cheer && _sooth0 && _sooth0.parentElement) {
      _cheer = document.createElement('p');
      _cheer.id = 'dailyCheer';
      _cheer.className = 'daily-soothe daily-cheer';
      _sooth0.parentElement.insertBefore(_cheer, _sooth0.nextSibling);
    }
    if (_cheer) {
      if (_dispLv === '吉') {
        _cheer.hidden = false;
        _cheer.textContent = _dayPick([
          '五星日：今天尽管冲，运气站你这边。',
          '上上签到手：想做的事今天都顺。',
          '今天运气满格，别把好日子浪费在犹豫上。',
          '五星开场，适合把惦记很久的那件事落地。',
          '今天是老天爷发糖的日子，伸手接住。',
          '运势全开的一天：晒出去让闺蜜沾沾光。'], 'cheer|' + _today);
      } else { _cheer.hidden = true; _cheer.textContent = ''; }
    }
    /* 吉签星爆：复用点击特效的星星迸发。reduced-motion 下
     * __fxBurstAt 不存在（IIFE 整段跳过），天然合规。 */
    if (_dispLv === '吉' && typeof window.__fxBurstAt === 'function') {
      var _dcEl = el('dailyCard');
      if (_dcEl) {
        var _dcr = _dcEl.getBoundingClientRect();
        window.__fxBurstAt(_dcr.left + _dcr.width / 2,
          _dcr.top + Math.min(_dcr.height / 2, 160));
      }
    }
    var _fv = el('dailyFest');
    if (!_fv) {
      _fv = document.createElement('div');
      _fv.id = 'dailyFest';
      _fv.className = 'daily-meta-item';
      var _mrowF = document.querySelector('#dailyCard .daily-meta');
      if (_mrowF) _mrowF.appendChild(_fv);
    }
    if (_fv) {
      if (j.festival && j.festival.length) {
        /* R3314（R3311-高1）：节日名后带一句「怎么过」 */
        var _ft1 = _festTip(j.festival[0]);
        _fv.innerHTML = '🎉 今天是<strong>' +
          esc(j.festival.join('、')) + '</strong>' +
          (_ft1 ? ' · ' + esc(_ft1) : '');
        _fv.hidden = false;
      } else { _fv.hidden = true; _fv.innerHTML = ''; }
    }
    /* R2349l（R73-P1-3/P1-4/P2-9）：个性行 + 开运三件套 + 水逆态——
     * 三条 meta 行同一个惰性挂载点。 */
    /* R2363（R117-P0-2）：胶囊行硬上限——可见 >5 粒折进「+N 条」
     * 收纳钮（横滚 1798px 实测爆炸）；点开完整展示，不收内容只收视线。 */
    var _metaRow = document.querySelector('#dailyCard .daily-meta');
    if (j.personal && j.personal.line) {
      /* R3241（用户实测）：判词粒里把「包的底」显出来——此前只有
       * 日主×今天，农历用户看不到自己填的生日（档案存的是换算后
       * 的公历坐标），以为判词认错人。按本地档案原样回显：农历
       * 原值优先、时辰未知直说。 */
      var _meP = _meGet('me');
      var _bdayTxt = '';
      if (_meP && _meP.y && _meP.m && _meP.d) {
        _bdayTxt = (_meP.lunar ? _meP.lunar
                  : (_meP.y + '年' + _meP.m + '月' + _meP.d + '日')) +
          ' · ' + ((_meP.h != null && _meP.h !== '')
                   ? (_hourZhi(_meP.h) + '（' + _meP.h + '点）')
                   : '时辰未知');
      }
      /* R3245（用户实测「填什么都是小吉」）：个人冲合判词当头——
       * 通判 level 是大家同款，「对你」这层才是你的盘与今天的对位。 */
      var _mine = j.personal.mine;
      /* R3248 续：🪞 日主行已升到大字 summary 位，胶囊里不再复述，
       * 改挂通版天气粒（通判语义保留可见）；各行 join 拼装——
       * 前置段缺省时不留孤悬 <br>。 */
      var _pc2 = [];
      if (_mine) {
        _pc2.push('<span class="daily-mine ' +
          esc(_mine.tone || 'flat') + '">' +
          '🧭 对你：' + esc(_mine.verdict || '') + '</span> ' +
          esc(_mine.line || ''));
      }
      if (j.summary) {
        _pc2.push('<span style="font-size:12px;opacity:.85;">' +
          '☁️ 今日通版：' + esc(j.summary) + '</span>');
      }
      if (j.personal.year_line) {
        /* R3314（R3311-高2）：年度签扩容——流年干支+五行基调+犯太岁
         * 五档+太岁位/岁破位。全确定性字段，缺省段自动省略。 */
        var _yd = j.personal.year_detail || {};
        var _ybits = [];
        if (_yd.wx) _ybits.push('五行基调 ' + _yd.wx);
        if (_yd.taisui) _ybits.push('今年' + _yd.taisui + '，大事多点耐心');
        if (_yd.ts_dir) _ybits.push('太岁在' + _yd.ts_dir);
        if (_yd.sp_dir) _ybits.push('岁破在' + _yd.sp_dir);
        _pc2.push('<span style="font-size:12px;opacity:.85;">' +
          '📅 ' + esc(j.personal.year_line) +
          (_ybits.length ? ' · ' + esc(_ybits.join('，')) : '') +
          '</span>');
      }
      if (_bdayTxt) {
        _pc2.push('<span class="daily-bday">你的生辰 · ' +
          esc(_bdayTxt) + '</span>');
      }
      _dailyMetaItem('dailyPersonal', _pc2.join('<br>'));
    } else {
      /* 没档案时轻引导——「存个生日这条就是你的了」（R73-P1-3）
       * R3243（用户实测）：补上「通版」标注——手误点开不再被当
       * 成个人判词，写明点熊拆的是大家同款。 */
      _dailyMetaItem('dailyPersonal',
        '<button type="button" class="daily-personal-cta" id="dailyPersonalCta">' +
        '🪞 现在是通版日签 · 存个生日就变成你的了</button>');
      var _pc = el('dailyPersonalCta');
      if (_pc && !_pc.dataset.bound) {
        _pc.dataset.bound = '1';
        _pc.addEventListener('click', function () {
          showView('xingzuo');
          var _bd = el('birthDrawer'); if (_bd) _bd.open = true;
        });
      }
    }
    if (j.lucky && (j.lucky.color || j.lucky.num)) {
      _dailyMetaItem('dailyLucky',
        /* R3314（R3312-P1-1）：与命盘「幸运色（本命）」双口径标注——
         * 这颗是按今天干支算的通版色。 */
        '🎨 开运色（今日通版）<strong>' + esc(j.lucky.color || '—') + '</strong>' +
        ' · 幸运数 <strong>' + esc(j.lucky.num || '—') + '</strong>' +
        (j.lucky.color_word
          ? '<span class="daily-lucky-word">' + esc(j.lucky.color_word) + '</span>' : ''));
    } else { _dailyMetaItem('dailyLucky', ''); }
    /* R3325：今日穿搭——五行穿衣五档（大吉/次吉/平/慎用/忌），
     * details 展开见五档色签+一句穿法+存图钮；无数据静默缺席。 */
    if (j.outfit && j.outfit.tiers && j.outfit.tiers.length) {
      var _ofRows = j.outfit.tiers.map(function (t) {
        return '<div class="outfit-row">' +
          /* R3329（审-P2）：hex 直拼 style——esc 不挡 ;/() 这类
           * CSS 注入面，非合法 hex 一律回退。 */
          '<i class="outfit-dot" style="background:' +
          (/^#[0-9a-fA-F]{3,8}$/.test(t.hex) ? esc(t.hex) : '#C9A227') +
          '"></i>' +
          '<b class="outfit-tag">' + esc(t.tag) + '</b>' +
          '<span class="outfit-colors">' + esc(t.colors) + '</span>' +
          '<span class="outfit-tip">' + esc(t.tip) + '</span></div>';
      }).join('');
      _dailyMetaItem('dailyOutfit',
        '<details class="outfit-kit"><summary>👗 今日穿搭 · ' +
        esc(j.outfit.wx || '') + '日 · 大吉 ' +
        esc(j.outfit.tiers[0].colors) + '</summary>' +
        '<div class="outfit-body">' + _ofRows +
        '<button type="button" id="outfitShare" class="outfit-share">' +
        '📸 存穿搭图</button>' +
        '<p class="outfit-note">按今天天干五行算，通版参考</p>' +
        '</div></details>');
      var _ofs = el('outfitShare');
      if (_ofs && !_ofs.dataset.bound) {
        _ofs.dataset.bound = '1';
        _ofs.addEventListener('click', function () {
          if (window.__lastDaily) {
            return downloadPoster(window.__lastDaily, 'daily-outfit');
          }
          showToast('今日运势还没出来，等它算好再存图～', 'warn');
          return null;
        });
      }
    } else { _dailyMetaItem('dailyOutfit', ''); }
    /* R3261（R12）：财神方位——日干查表的确定性坐标（与黄历页同源），
     * 给「搞钱」人群一个每日小落点。无数据静默缺席。 */
    if (_pStr(j.money_dir)) {
      _dailyMetaItem('dailyCai',
        '🧭 财神方位 <strong>' + esc(j.money_dir) + '</strong>' +
        '<span class="daily-lucky-word">朝那边坐坐</span>');
    } else { _dailyMetaItem('dailyCai', ''); }
    if (j.mercury && j.mercury.on) {
      _dailyMetaItem('dailyMercury',
        '💫 水逆中 · 第' + j.mercury.day_no + '天（到 ' +
        esc(String(j.mercury.until || '').slice(5).replace('-', '月')) + '日），心放宽，事多检查');
      /* R3261（R16）：水逆关怀副行——54% 的人在长期水逆时求助，
       * 这是产品最该接住人的时刻；多一句不催的。 */
      _dailyMetaItem('dailyMercCare',
        '🫖 小满多嘴：这几天慢一点没关系，签都替你留着');
      /* R3263（R23）：水逆急救包——可执行小仪式 + 忌冲动提醒。 */
      _dailyMetaItem('dailyMercKit',
        '<details class="merc-kit"><summary>🆘 水逆急救包</summary>' +
        '<div class="merc-kit-body">' +
        '<p class="merc-dont">今日忌冲动：' + esc(j.dont || '—') + '</p>' +
        '<button type="button" id="mercBreathe" class="merc-breathe">' +
        '慢三秒</button>' +
        '<p class="merc-hint">小满替你数着，慢慢就好。</p></div></details>');
      var _mb = el('mercBreathe');
      if (_mb && !_mb.dataset.bound) {
        _mb.dataset.bound = '1';
        _mb.addEventListener('click', _mercBreathe);
      }
    } else {
      _dailyMetaItem('dailyMercury', '');
      _dailyMetaItem('dailyMercCare', '');
      _dailyMetaItem('dailyMercKit', '');
    }
    /* R3260：足迹胶囊——「来铺子的第N天」是关系锚不是仪表盘；
     * ≥2 天才展示（第 1 天没有「常客」感，挂着反而像计数器）。 */
    var _uDays = _usageDays();
    if (_uDays >= 2) {
      var _uTop = _usageTop();
      _dailyMetaItem('dailyDays', '🏮 你来铺子 <strong>第 ' +
        _uDays + ' 天</strong> 啦' +
        (_uTop ? ' · 最常翻「' + esc(_uTop) + '」' : ''));
    } else { _dailyMetaItem('dailyDays', ''); }
    /* R3262（R17）：心情罐子入口——有解锁时在日常 meta 行展示，
     * 没有则静默不占位。 */
    _dailyMetaItem('dailyMoodJar', _moodJarHtml());
    /* R3350：咒语册入口——攒了才现身 meta 行（空册不占地）。 */
    try { _mantraBookMeta(); } catch (eMBM) {}
    /* R3321-P1：旧「每日一牌」异步路径整段退役——它与 daily_card
     * 不同 seed（可能抽成另一张牌），且 _dailyMetaItem('dailyTarot')
     * 与新渲染器同 id 覆写，把「抽三张」入口整段抹掉。牌意展开已
     * 收进新行（meaning 由后端 daily_card 一并下发）。 */
    /* R2349l（R73-P1-8）：新月许愿/满月复盘——农历初一十五窗口的
     * 仪式行（后端 daily 的 moon 派生键）。 */
    if (j.moon && j.moon.label) {
      /* R3314（R3311-低）：月相行挂许愿瓶落点——新月「丢个愿望」、
       * 满月「翻翻瓶子」，点开打卡卡里的许愿瓶折叠。 */
      var _mBtn = j.moon.action
        ? ' <button type="button" class="daily-moon-go" data-moon="' +
          esc(j.moon.action) + '">' +
          (j.moon.action === 'wish_review' ? '翻翻瓶子 →' : '丢个愿望 →') +
          '</button>'
        : '';
      _dailyMetaItem('dailyMoon',
        (j.moon.phase === '满月' ? '🌕 ' : '🌑 ') +
        '<strong>' + esc(j.moon.label) + '</strong> ： ' +
        esc(j.moon.line || '') + _mBtn);
      var _mEl = el('dailyMoon');
      if (_mEl && !_mEl.dataset.bound) {
        _mEl.dataset.bound = '1';
        _mEl.addEventListener('click', function (ev) {
          var _t = ev.target;
          if (!_t || !_t.classList ||
              !_t.classList.contains('daily-moon-go')) return;
          var _ck = el('dailyCheckin');
          if (!_ck) return;
          var _wish = _ck.querySelector('.ck-wish');
          if (_wish) _wish.open = true;
          _ck.scrollIntoView({ behavior: 'smooth', block: 'center' });
        });
      }
    } else { _dailyMetaItem('dailyMoon', ''); }
    /* R2349t（R88-1a）：生日当天日签也认得她——横幅之外的第二层。 */
    _dailyMetaItem('dailyBday', _isMyBirthday()
      ? '🎂 生日签·今天的宜忌为你加一分：宜收下所有好意' : '');
    /* R2349t（R88-7b）：深夜档收口句——23 点后陪她收摊。 */
    (function () {
      var _hn = new Date().getHours();
      _dailyMetaItem('dailyNight',
        (_hn >= 23 || _hn < 5) ? '🌙 夜深了，看完就睡吧，明天再来' : '');
    })();
    /* R2349l（R73-P1-15）：周日给「本周辛苦了→下周哪天顺」，
     * 周一给「新的一周看宜忌」——跳黄历页，周条本就在那。 */
    (function () {
      var _wd = new Date().getDay();
      if (_wd === 0) {
        _dailyMetaItem('dailyWeekHint',
          '🗓 这周辛苦了，<button type="button" ' +
          'class="sign-peek" id="dailyWeekGo">看看下周哪天顺</button>');
      } else if (_wd === 1) {
        _dailyMetaItem('dailyWeekHint',
          '🗓 新的一周，<button type="button" ' +
          'class="sign-peek" id="dailyWeekGo">本周宜忌速览</button>');
      }
      var _wg = el('dailyWeekGo');
      if (_wg && !_wg.dataset.bound) {
        _wg.dataset.bound = '1';
        _wg.addEventListener('click', function () {
          try { showView('huangli'); } catch (e) {}
        });
      }
    })();
    /* R2349l（R73-P1-16）：TA 生日倒计时——扫 me/me:partner/测过的 CP
     * 里的生日，最近一次 ≤30 天的给倒数行。favorites 在服务端，
     * _favList 在途合并+静默失败，不打扰主渲染。 */
    _favList().then(function (_favs) {
      try {
        var _cands = [];
        var _pm = _meGet('me:partner');
        if (_pm && _pm.m && _pm.d) {
          _cands.push({ n: _pm.n || 'TA', m: +_pm.m, d: +_pm.d });
        }
        var _me0b = _meGet('me');
        if (_me0b && _me0b.m && _me0b.d) {
          _cands.push({ n: _me0b.n || '你', m: +_me0b.m, d: +_me0b.d });
        }
        (_favs || []).forEach(function (f) {
          var p = String((f && f.ref_id) || '').split('|');
          if (p.length >= 9 && p[6] && p[7]) {
            _cands.push({ n: p[11] || 'TA', m: +p[6], d: +p[7] });
          }
        });
        if (!_cands.length) return;
        var _t0 = new Date(); _t0.setHours(0, 0, 0, 0);
        var _best = null;
        _cands.forEach(function (c) {
          if (!c.m || !c.d || c.m < 1 || c.m > 12 || c.d < 1 || c.d > 31) return;
          var yy = _t0.getFullYear();
          var bd = _bdayInYear(c.m, c.d, yy);
          if (bd < _t0) bd = _bdayInYear(c.m, c.d, yy + 1);
          var dd = Math.round((bd - _t0) / 86400000);
          if (dd > 0 && dd <= 30 && (!_best || dd < _best.dd)) {
            _best = { dd: dd, n: c.n };
          }
        });
        if (_best) {
          /* R2349t（R88-3）：生日周升级——「还有 7 天」和「还有 30 天」
           * 不该是同一句倒数。 */
          _dailyMetaItem('dailyBdayCtd', _best.dd <= 7
            ? '🎂 ' + esc(_best.n) + '的生日周：本周的签到藏着蛋糕'
            : '🎁 ' + esc(_best.n) + '的生日还有 <strong>' +
              _best.dd + '</strong> 天');
        }
      } catch (e) {}
    }).catch(function () {});
    /* R233n（R47-P2-5）：生日横幅——档案里的生日撞上今天就铺一条
     * 「今天你最大」，顺带把生日盘入口点亮。
     * R2349（R65-P2-5）：抽成函数——daily API 失败的 catch 兜底
     * 路径也调（横幅只依赖本地档案，离线生日不该缺席）。 */
    _renderBirthdayBanner();
    /* R2349l.6（R73-P2-10）：节气横幅——交节日首页铺一条民俗提示，
     * 24 节气每年 24 个天然内容节点；生日横幅优先，节气在其下。 */
    var _tbar = el('dailyTerm');
    if (j.term && j.term.name) {
      if (!_tbar) {
        _tbar = document.createElement('div');
        _tbar.id = 'dailyTerm';
        _tbar.className = 'daily-term';
        _tbar.setAttribute('role', 'note');
        var _ckb2 = el('dailyCheckin');
        if (_ckb2 && _ckb2.parentNode) {
          _ckb2.parentNode.insertBefore(_tbar, _ckb2);
        }
      }
      _tbar.innerHTML = '🌾 今日节气·<strong>' + esc(j.term.name) + '</strong>' +
        (j.term.time ? '（' + esc(j.term.time) + ' 交节）' : '') +
        (j.term.tip ? '' + esc(j.term.tip) : '');  // esc-reviewed
      _tbar.hidden = false;
    } else if (_tbar) { _tbar.hidden = true; }
    renderCheckin(j.date);   // R214b：今日玄学搭子打卡互动
    /* R3259（UX-STRATEGY-NEXT N3）：心情回路——打完卡顺手记个心情。 */
    try {
      _renderMoodRow((_dispLv === '吉' || _dispLv === '小吉') ? 'g' : 'l');
    } catch (eMR) {}
    /* R39-P0-1：卡尾「明天预告」一行。 */
    var _tmrEl = el('dailyTomorrow');
    if (!_tmrEl) {
      _tmrEl = document.createElement('div');
      _tmrEl.id = 'dailyTomorrow';
      _tmrEl.className = 'daily-tomorrow';
      /* R2343（R59-gap1）：胶囊样式诱导点击却纯 div 无响应——
       * 现在点了跳黄历页直接翻到明天。 */
      _tmrEl.setAttribute('role', 'button');
      _tmrEl.setAttribute('tabindex', '0');
      var _tmrGo = function () { showView('huangli'); doHuangli(1, true); };
      _tmrEl.addEventListener('click', _tmrGo);
      _tmrEl.addEventListener('keydown', function (ev) {
        if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); _tmrGo(); }
      });
      var _metaBox = document.querySelector('#dailyCard .daily-meta');
      if (_metaBox && _metaBox.parentNode) {
        _metaBox.parentNode.insertBefore(_tmrEl, _metaBox.nextSibling);
      }
    }
    if (_tmrEl) {
      if (tm && (tm.level || tm.do)) {
        /* R3220：do 两态——「宜：x、y」或裸「x、y」，此前恒加「宜 」
         * 前缀态渲成「宜 宜：」叠词。剥掉后端自带前缀再拼。 */
        var _tdo = String(tm.do || '平常心').replace(/^宜[:：]?\s*/, '');
        /* R3314（R3311-低）：明天是节日时预告先报节——「明天七夕」
         * 比「明天小吉」更能把人钩回来。 */
        var _tmFest = (tm.festival && tm.festival[0])
          ? ' 明天' + tm.festival[0] +
            (_festTip(tm.festival[0]) ? '·' + _festTip(tm.festival[0]) : '') + '｜'
          : '';
        /* R3384：幸运色钩——「明天穿什么色」是穿搭场景的最短回访
         * 理由（玄学穿搭博主验证过的内容型），预告行带上它。 */
        var _tmc = (tm.lucky && tm.lucky.color)
          ? ' · 穿' + tm.lucky.color : '';
        _tmrEl.textContent = '🌙 明天「' +
          (tm.level === '凶' ? '缓' : (tm.level || '平')) + '」' + _tmFest +
          _tmc + ' · 宜 ' + _tdo + ' ' +
          /* R2349g（R68-P1-1）：明天预告导引 3→6。 */
          _dayPick(['点我看明天', '记得来拆明天的礼物', '明天再来找我玩',
                    '明天的运先睹为快', '明天也请多关照', '提前看看明天'], 'tmr') + ' →';
        _tmrEl.hidden = false;
      } else { _tmrEl.hidden = true; }
    }
    /* R39-P1-1：昨天问过的事接续条——hlask 足迹出黄历页，上首页。 */
    var _recEl = el('dailyRecall');
    if (!_recEl) {
      _recEl = document.createElement('div');
      _recEl.id = 'dailyRecall';
      _recEl.className = 'daily-recall';
      /* 点了先跳黄历页，再由全局 data-hlask-q 委托代填+真问 */
      _recEl.addEventListener('click', function (e) {
        if (e.target.closest && e.target.closest('[data-hlask-q]')) {
          showView('huangli');
        }
      });
      if (_tmrEl && _tmrEl.parentNode) _tmrEl.parentNode.insertBefore(_recEl, _tmrEl);
      else {
        var _metaBox2 = document.querySelector('#dailyCard .daily-meta');
        if (_metaBox2 && _metaBox2.parentNode) _metaBox2.parentNode.appendChild(_recEl);
      }
    }
    if (_recEl) {
      var _hl0 = null;
      try {
        /* R2349t（R87-P2-4）：两读端口径统一——合法 JSON 但非数组
         * 的脏值此处不再静默取 [0]（黄历页 chips 端本就自愈清键）。 */
        var _hlArr = JSON.parse(localStorage.getItem('hlask') || '[]');
        _hl0 = Array.isArray(_hlArr) ? _hlArr[0] : null;
      }
      catch (e0) {}
      /* R2349k（R72-B4）：接续条比较/话术都锚「问的那天」（a），
       * 老足迹没 a 时回落 d。 */
      var _hlA = _hl0 && (_hl0.a || _hl0.d);
      if (_hl0 && _hl0.q && _hlA && _hlA < _today) {
        _recEl.innerHTML = '<button type="button" class="daily-recall-btn" ' +
          'data-hlask-q="' + esc(_hl0.q) + '" data-hlask-today="1">💬 ' +
          _hlAgoWord(_hlA) + '你问了「' +
          esc(_gSlice(_hl0.q, 14)) + '」，今天再看看？</button>';
        _recEl.hidden = false;
      } else { _recEl.hidden = true; }
    }
    // 004 M2 T2.4：今日值宫（十二宫日运）。失败静默——入口卡保持 hidden。
    try {
      const box = el('dailyXingzuo');
      if (box && x && x.today_sign) {
        /* R216b 续3（U-010）：「值官/龙首星」术语腔 → 人话。 */
        setText('dxLabel', '⭐ 今天轮到' + (x.today_sign || '—') + '座当班');
        setText('dxNote', x.today_note || '');
        box.hidden = false;
      }
    } catch (e2) { /* 十二宫不可用不阻塞今日运势 */ }
    /* R3244（用户实测「不是任何页面都能聊」）：首页日签卡此前没有
     * 「聊聊这件事」入口——天天看的卡反而聊不了。挂进卡尾（封面
     * 未拆时盖在封套下，拆开自然露出；rememberResult('daily') 已
     * 备好上下文）。 */
    try { attachChatEntry(el('dailyCard')); } catch (eCE) {}
    _slowDone();
  } catch (e) {
    _slowDone();
    if (_gen !== DAILY_GEN) return;   /* 旧请求失败也不得污染新结果 */
    /* R228c：失败态补全——dailyDate 别停在「加载中…」，分享钮也给提示
     * 而不是静默无操作。 */
    setText('dailyDate', '今天');
    /* R2506（审-U1）：日签卡失败此前是死卡——loadDaily 只在 init 调
     * 一次，弱网/5xx 后卡片停在错误态直到整页刷新（微信里刷新藏得
     * 很深）。错误句后给「再来一次」重试钮；online 事件侧另有兜底
     * （__lastDaily 仍空就重拉）。 */
    var _ds = el('dailySummary');
    if (_ds) {
      _ds.innerHTML = '运势计算暂时不可用：' + esc(_humanizeErr(e.message)) +
        ' <button type="button" class="ghost daily-retry" id="dailyRetry">' +
        '再来一次</button>';
      var _drRetry = el('dailyRetry');
      if (_drRetry && !_drRetry.dataset.bound) {
        _drRetry.dataset.bound = '1';
        _drRetry.addEventListener('click', function () { loadDaily(); });
      }
    } else {
      setText('dailySummary', '运势计算暂时不可用：' + _humanizeErr(e.message));
    }
    /* R230n（R25-5.2）：打卡是纯 localStorage 功能，daily 失败时不该
     * 连带隐藏——按浏览器今天渲出来，离线也能打。 */
    renderCheckin(todayIso());
    /* R2349（R65-P2-5）：生日当天离线进首页也要有横幅——横幅只吃
     * 本地档案，不依赖 daily 响应。 */
    _renderBirthdayBanner();
  }
}

/* R233n→R2349 抽函数：生日横幅渲染（loadDaily 成功/失败两路共用）。 */
function _renderBirthdayBanner() {
  try {
    var _bme = _meGet('me'), _bdt = new Date();
    var _bbar = el('dailyBirthday');
    var _bbd = _bme && _bme.y
      ? _bdayInYear(_bme.m, _bme.d, _bdt.getFullYear()) : null;
    if (_bbd &&
        _bbd.getMonth() === _bdt.getMonth() &&
        _bbd.getDate() === _bdt.getDate()) {
      if (!_bbar) {
        _bbar = document.createElement('div');
        _bbar.id = 'dailyBirthday';
        _bbar.className = 'daily-birthday';
        _bbar.setAttribute('role', 'note');
        var _ckb = el('dailyCheckin');
        if (_ckb && _ckb.parentNode) _ckb.parentNode.insertBefore(_bbar, _ckb);
      }
      _bbar.innerHTML = '🎂 ' +
        (_bme.n ? esc(_bme.n) + '，' : '') +
        '今天你生日：全场最大，宜收下所有夸奖 ' +
        '<button type="button" class="daily-birthday-go">' +
        '去开生日盘 ✨</button>';
      var _bgo = _bbar.querySelector('.daily-birthday-go');
      if (_bgo && !_bgo.dataset.bound) {
        _bgo.dataset.bound = '1';
        _bgo.addEventListener('click', function () {
          showView('xingzuo');
          var _bd2 = el('birthDrawer');
          if (_bd2) _bd2.open = true;
        });
      }
    } else if (_bbar) { _bbar.remove(); }
  } catch (e3) {}
}

function renderStars(level) {
  const good = '<span class="star-good">★</span>';
  const mid = '<span class="star-mid">☆</span>';
  const bad = '<span class="star-bad">★</span>';
  if (level === '吉') return good.repeat(5);
  if (level === '小吉') return good.repeat(4) + mid;
  if (level === '凶') return bad + mid.repeat(4);
  return good.repeat(3) + mid.repeat(2);
}

function setText(id, text) {
  const node = el(id);
  if (node) node.textContent = text;
}

/** #dailyMore：原来只有按钮没有处理器（R000a-03）。行为定义为「展开今日
 *  完整解读」——用今天日期跑一次 /api/bazi（scope=day），把确定性解读
 *  就地展开。不跳转、不新开窗口，保持单页。 */
async function loadDailyDetail() {
  const target = el('dailyDetail');
  if (!target) return;
  /* R228c：展开/收起同步按钮文案 + aria-expanded（读屏可知）。 */
  var _btn = el('dailyMore');
  var _syncBtn = function () {
    if (!_btn) return;
    _btn.setAttribute('aria-expanded', target.hidden ? 'false' : 'true');
    _btn.textContent = target.hidden ? '🔍 查看完整解读 →' : '🔍 收起完整解读 ↑';
  };
  if (target.dataset.loaded === '1') {
    target.hidden = !target.hidden;
    _syncBtn();
    return;
  }
  target.hidden = false;
  busy('dailyDetail', '小满正在看今天的盘…');   /* R233k：统一三点加载态 */
  const today = new Date();
  try {
    const j = await postJSON('/api/bazi', {
      year: today.getFullYear(),
      month: today.getMonth() + 1,
      day: today.getDate(),
      hour: 12,
      gender: val('gender') || '女',
      scope: 'day',
      /* R230h（R20-F6）：流日锚浏览器日——盘按浏览器生辰、流日按
       * 服务器日，跨零点窗口会一屏混进两个「今天」。 */
      ask_date: todayIso(),
      question: '今天运势如何？'
    });
    let html = '<div class="card"><h2>🔍 今日完整解读</h2>';
    html += '<p class="paipan-line">' + esc((j.paipan || {}).render || '') + '</p>';
    // R3212：单版化——坐标原表不再直出，统一收进下方折叠（原 pro 分支内容）。
    {
      /* R3212：单版化——轻摘要常显，坐标原表+完整解读收进折叠。 */
      var _w = j.warm || {};
      var _pts = (Array.isArray(_w.reply) && _w.reply.length) ? _w.reply.slice(0, 3) : [];
      if (!_pts.length && (_w.details || []).length) {
        /* R3258：排盘坐标/运算摘要属「原样」小节——坐标行就在上面
         * paipan-line，摘要进 _proFold，简报不再复读。 */
        _w.details.filter(function (d) {
          var t = (d && d.title) || '';
          return t !== '排盘坐标' && t.indexOf('运算摘要') !== 0;
        }).slice(0, 3).forEach(function (d) {
          var ln0 = (d.lines || [])[0];
          if (ln0) _pts.push((d.title ? '【' + d.title + '】' : '') + ln0);
        });
      }
      html += '<div class="daily-brief">';
      if (_w.one_liner) html += '<div class="warm-l0">' + esc(_w.one_liner) + '</div>';
      if (_pts.length) {
        html += '<ul class="daily-brief-list">' +
          _pts.map(function (ln) { return '<li>' + esc(ln) + '</li>'; }).join('') +
          '</ul>';
      }
      html += '</div>';
      /* R3258：与八字页同构——renderVoice 出人话层+散铺小节+引文树，
       * _proFold 出唯一原表折叠；原「想看专业依据？」与「排盘坐标原表」
       * 两个三角实为同源三段重复（用户实测），收口为一。 */
      html += '<details class="daily-full pro-drawer"><summary>展开完整解读 ▾</summary>' +
        '<div class="daily-full-body">' +
        renderVoice(j, '📖 小满的解读', ['evidence']) +
        _proFold(j) + '</div>' +
        '</details>';
    }
    html += '</div>';
    /* R2350d（R100-P0-1 同型）：dailyDetail 也绕过 paint() 直写——
     * is-working 不摘的话整卡恒半透+子元素 pointer-events:none。 */
    target.classList.remove('is-working');
    target.innerHTML = html;
    target.dataset.loaded = '1';
    /* R233r（R49-Top5-4）：日签卡接入聊天上下文——首页「聊聊这件事」/
     * 直接开聊手里都有今天的盘。 */
    rememberResult('daily', j, '今天运势如何？');
    /* v3（P1 修复）：内容注入后立即滚到详情，并强制显示（fx 入场动画
     * 在此场景会停在 opacity:0，实测用户视角=空白）。 */
    target.querySelectorAll('.fx-watch').forEach(function (n) {
      n.classList.add('fx-in');
      n.style.opacity = '1';
      n.style.transform = 'none';
    });
    try { target.scrollIntoView({ behavior: _rmBehavior(), block: 'start' }); } catch (e) {}
    /* R2349o（R78-P1-1）：首载成功后同步 aria-expanded/文案——原来只在
     * 二次切换路径调，首开后读屏仍被告知「」。 */
    _syncBtn();
    /* R3245（用户实测「两个聊聊这件事发一样的消息」）：detail 在
     * dailyCard 内部末尾，R3244 起卡尾常驻入口视觉上就贴在展开
     * 正文下方——此处再挂一颗 = 双钮同源同文。留卡级那颗（未展开
     * 时也有入口），这颗摘掉。 */
    pollAiPolish('dailyDetail', j.ai_task_id);   // R217a：完整解读也轮询 AI 润色
  } catch (e) {
    /* R2506（审-U3）：失败时详情块已展开但按钮还停在
     * aria-expanded=false + 「查看完整解读」——读屏宣告与视觉相反。
     * 补 _syncBtn + 错误句给「再点一次」的重试语义（再点会重走 fetch，
     * loaded 标记没置位所以真会重试）。 */
    target.innerHTML = '<div class="no-evidence">解读失败：' +
      esc(_humanizeErr(e.message)) + '，再点一次按钮重试</div>';
    _syncBtn();
  }
}

/* ── 八字排盘 ──────────────────────────────────────────────── */

function baziBody() {
  const calendar = val('calendar_type') || 'solar';
  const scope = val('scope') || 'day';
  /* R206b（specs/009 US3 表单减负）：时辰可留空（不知道出生时间是小满
   * 高频场景）——留空时前端补默认 12 时，契约零改动（后端 hour 仍必填）。 */
  const hourRaw = val('hour');
  const body = {
    year: num('year'),
    month: num('month'),
    day: num('day'),
    hour: (hourRaw === '' || hourRaw == null) ? 12 : num('hour'),
    hour_known: !(hourRaw === '' || hourRaw == null),
    gender: val('gender') || '女',
    calendar_type: calendar,
    scope: scope
  };
  /* R230f（R18-P1-1）：可选分钟——只在填了时辰+分钟时才传（节气当小时
   * 内出生需分钟级才不被截到节前一侧）。时辰留空时传分钟没意义
   * （默认 12 点的盘带个 30 分纯属误导）。 */
  var _min = num('minute');
  if (_min != null && !(hourRaw === '' || hourRaw == null)) {
    body.minute = _min;
  } else if (_min != null) {
    showToast('填了分钟但没填时辰，分钟不生效哦', 'info');
  }
  if (calendar === 'lunar') {
    // 农历输入复用同三个输入框（HTML 只有一组年月日），后端要 lunar_* 键。
    body.lunar_year = body.year;
    body.lunar_month = body.month;
    body.lunar_day = body.day;
    body.lunar_leap = checked('lunar_leap');
    LAST_BAZI_LUNAR = true;   /* R216b 续5（U-021）：结果卡标注「按农历换算」 */
  } else {
    LAST_BAZI_LUNAR = false;
  }
  /* R2350g（R104-P1-1）：scope 恒为 day/range/life——「bazi」分支永不
   * 成立。三种范围都按所填生日起盘，回显全该亮（出厂示例生日的
   * 错盘外溢正是 R102-P1-5 要堵的）。 */
  _LAST_BIRTH.bazi = body.year + '-' + body.month + '-' + body.day +
    (LAST_BAZI_LUNAR ? '（农历）' : '');
  const q = val('question');
  if (q) body.question = q;
  if (scope === 'range') {
    const rs = val('range_start');
    const re = val('range_end');
    if (rs) body.range_start = rs;
    if (re) body.range_end = re;
    const rh = num('range_hour');
    if (rh != null) body.ask_hour = rh;
  } else {
    /* R230t（R32-P2-5）：留空时锚浏览器今天——后端现在按服务器日兜底，
     * UTC vs 浏览器时区的跨零点窗口会算出另一天的运势基准。 */
    const ad = val('ask_date');
    body.ask_date = ad || todayIso();
    const ah = num('ask_hour');
    if (ah != null) body.ask_hour = ah;
  }
  const loc = val('location');
  if (loc) body.location = loc;
  return body;
}

/** 排盘结果区的 HTML 构建（抽成纯函数，可就地重画）。 */
/* R218a-巡2（N-08）：结果卡装饰图——按 view 选不同主题色 + emoji 锚定。
 * 后续接入 /api/decoration 时把 url 套进 .deco-img 即可；本轮先给基础
 * 视觉（CSS 渐变 + 主题 emoji + 锚定文字），零外部依赖、不动既有数据。
 * 风格刻意差异化：
 *   bazi   → 紫金圆月 + 罗盘骨架（命理权威感）
 *   qiming → 粉绿叶片 + 印章骨架（清新灵动）
 *   taohua → 粉橘花瓣 + 心形骨架（甜系少女感）
 *   其余    → 暖米金 + 极简锚（不抢主区） */
function renderDecoration(view) {
  /* v3（P2）：装饰条统一走 cream 图标（与首页同一套资产语言），
   * 清除乱码 emoji；全视图覆盖，缺失视图安全返回空。 */
  /* R2349j（R70-P0-5）：渐变收进 CSS 类（.deco-banner.deco-<view>）——
   * 内联 style 优先级永远压过 [data-theme=dark] 补丁，深色下文案洗白。 */
  var presets = {
    bazi:    { icon: '/static/cream/cream-icon-bazi.jpg',    txt: '你的命盘已就位' },
    qiming:  { icon: '/static/cream/cream-icon-qiming.jpg',  txt: '好名字，自己也能换' },
    taohua:  { icon: '/static/cream/cream-icon-taohua.jpg',  txt: '今天的桃花信号帮你看看' },
    tarot:   { icon: '/static/cream/cream-icon-tarot.jpg',   txt: '静心抽牌，听听牌怎么说' },
    hehun:   { icon: '/static/cream/cream-icon-hehun.jpg',   txt: '缘分配对，一拍即合' },
    huangli: { icon: '/static/cream/cream-icon-huangli.jpg', txt: '择个好日子，事事顺心' },
    xingzuo: { icon: '/static/cream/cream-icon-xingzuo.jpg', txt: '星空为你指路' },
    liuyao:  { icon: '/static/cream/cream-icon-liuyao.jpg',  txt: '摇出来的卦，读给你听' }
  };
  var p = presets[view];
  if (!p) return '';
  return '<div class="deco-banner deco-' + view + '">' +
    '<img class="deco-icon-img" src="' + p.icon + '" alt="" onerror="this.classList.add(\'is-missing\')">' +
    '<div class="deco-text">' + esc(p.txt) + '</div>' +
    '<div class="deco-corner"></div>' +
  '</div>';
}

/* R218a-巡2：N-08 装饰图函数 + N-01 questionHook 依赖后端 services.py 回写 question 字段 */

function buildBaziResult(j) {
  const paipan = j.paipan || {};
  let html = '<div class="card"><h2>🔮 排盘结果</h2>';
  /* C-003：交叉引用——八字结果页增加星座维度 */
  if (j.cross_ref && j.cross_ref.message) {
    html += '<div class="cross-ref"><span class="cross-ref-icon">⭐</span>' + esc(j.cross_ref.message) + '</div>';
  }
  /* R233c（R40-A9）：时辰未知的盘，后端回 hour_known:false——卡面
   * 给个小标（温柔行里也写了，但徽标可扫读）。 */
  if (j.hour_known === false) {
    html += '<div class="hour-note">⏰ 时辰按午时估算，大方向不变</div>';
  }
  /* R218a-巡2（N-08）：装饰图——结果卡顶部加一行 SVG/CSS 装饰 banner。
   * 后续接入 /api/decoration 时把 url 套进 .deco-img 即可；本轮先给基础
   * 视觉装饰（CSS 渐变 + 文字锚定），零外部依赖、不动既有数据流。 */
  html += renderDecoration('bazi');
  /* R208b：❤️ 收藏钮随「我的收藏」区块一并移除（用户裁决）。 */
  // 004 M3 T3.1：分享海报按钮（原生 Canvas，零依赖，D-151a）
  // R3217：两枚分享钮原都吃 .fav-btn absolute 同点位，第二枚只右移
  // 60px 根本不够（「年度运势图」~110px 宽）——实测互叠点不到。
  // 套 .share-row 横排容器，内部按钮改 static 不再算 right 偏移。
  html += '<div class="share-row">' +
    '<button class="ghost fav-btn" type="button" id="shareBazi" ' +
    'title="生成分享图">📸 分享图</button>';
  /* R3165：年度运势图——年底/生日季晒图格式（年度干支+顺劲/使劲月
   * 榜），calc.yearly 在才出钮（兜底防空卡）。 */
  if (j.calc && j.calc.yearly && j.calc.yearly.ganzhi) {
    html += '<button class="ghost fav-btn" type="button" id="shareBaziYear" ' +
      'title="生成今年运势图">📅 年度运势图</button>';
  }
  /* R3393：人生K线分享钮——流年走势图可晒件。 */
  if (j.calc && j.calc.kline && j.calc.kline.candles) {
    html += '<button class="ghost fav-btn" type="button" id="shareBaziKline" ' +
      'title="生成人生K线图">📈 人生K线</button>';
  }
  html += '</div>';
  /* R3309（probe_first_screen 判据 1）：共情+一句话结论提到结果卡顶——
   * 排在命盘图/人设卡之前时，提交后无需滚动第一眼就是它。
   * renderVoice 传 skipLead 不再渲染这两块，DOM 里只此一份。 */
  html += _warmLead(j.warm);
  {
    /* R215b：四柱/纳音收进折叠「看看你的生辰小卡」（R3212 单版化后恒走）。 */
    /* R215b：温柔模式首屏去工具感——四柱/纳音收进折叠「看看你的生辰小卡」，
     * 首屏只有一句人话生日线。事实零改动，只是呈现位置后移。 */
    html += '<p class="bazi-birthday">' + esc(baziBirthdayLine(paipan)) + '</p>';
    html += _birthEcho('bazi');
    /* R218a-03：人设卡——按日主五行分支从 copy_bank.gan_persona 选一套。
     * 视觉锚点：左条+人设短句+1-2 关键词气泡。让「我是什么命格」秒级可达。 */
    html += baziPersonaCard(j);
    if (LAST_BAZI_LUNAR) {
      /* R216b 续5（U-021）：农历输入时告知已换算，用户可核对。 */
      html += '<p class="nayin">🗓 你输入的是农历生日，四柱按公历换算得出' +
        '，遇到闰月也可以对照上面的日子核对。</p>';
    }
    html += '<details class="paipan-fold"><summary>看看你的生辰小卡</summary>' +
      '<div class="pill-row">';
    /* R3233：时辰未知盘第 4 柱画「时辰未知」pill，不画默认午时。 */
    String(_pillarsHonest(paipan.render, j.hour_known)).split(/\s+/).forEach(function (p, i) {
      if (p.length >= 2) {
        html += '<span class="pill" style="background:' + colorAt(i) + ';">' +
          esc(p) + '</span>';
      }
    });
    html += '</div>';
    if (paipan.nayin && paipan.nayin.length) {
      html += '<p class="nayin">纳音：' + esc(paipan.nayin.join(' · ')) + '</p>';
    }
    /* R2350b（R98-P1-5）：折叠卡里「日主/大运：逆/纳音」裸奔——
     * 加一行小注把三个词一次翻完。 */
    html += '<p class="nayin" style="color:var(--muted);font-size:11px">' +
      '日主=出生那天的天干（你的本命五行）；大运=十年一轮的大方向，' +
      '「逆排」就是从月柱往前数；纳音是五行的传统叫法，当个小标签看就好</p>';
    html += '</details>';
    /* R3254：命盘可视化（四柱格+五行雷达+地支关系）——用户点名
     * 的「能不能做成图」落在结果页可视区，不进折叠。
     * R3309（probe_first_screen 判据「结果区 ≤4 屏」）：展开态单卡
     * 6 屏，改默认收进折叠——点开即见图，零删减。 */
    html += '<details class="plate-fold"><summary>🀄 看看你的四柱盘（图）</summary>' +
      _baziPlate(j) + '</details>';
  }
  if (paipan.warn && paipan.warn.length) {
    html += '<p class="warn">' + esc(paipan.warn.join('；')) + '</p>';
  }
  // R183b（审查轨 R124a-01，003 判据 14）：renderCalc 是 calc 字典的**原样
  // 转储**，键名就是后端内部字段名（ten_gods / five_elements / day_luck …）。
  // 它此前在 renderVoice 之前**无条件**执行，于是温柔模式首屏也印满变量名
  // ——用户看到程序变量名和看到 [object Object] 一样廉价。
  //
  // 版面顺序（R185b，有意为之）：renderVoice 大白话在前，专业内容
  // 收进下方折叠。实测依据：古籍全文占结果区 92% 字数、单段最高
  // 12,219px，排在大白话之前 = 用户要滚 71,094px 才看到人话（005 §1）。
  // 古籍由 renderWarm 经 renderCiteTree 渲染**一次**，不再单独渲染。
  /* R3254（用户实测「两个可点三角都是专业视角」）：先出人话层，
   * 专业内容三件（排盘坐标/推导链/古籍原文）收进同一个折叠、
   * 分节小标题区分——不再两个「专业视角」三角并列打架，且整折
   * 沉到人话层之后。 */
  /* R3309：skipLead——共情/L0 已在卡顶渲染过一次；foldSecs——逐条
   * 推演小节整组收折叠（结果区 ≤4 屏判据）。 */
  html += renderVoice(j, '📖 小满的解读', ['evidence'], true, true);
  /* R3258：原三合一大折叠收敛为唯一原表折叠——推导链=上方散铺
   * 小节本体（逐字节同源），古籍=renderWarm 引文树（同源第二份），
   * 都摘掉；只留别处看不到的：排盘坐标原句 + 运算摘要 + 字段原表。 */
  html += _proFold(j);
  /* R3159（specs/014-L3 收口）：今年逐月条——calc.yearly 服务端
   * 一直在算但前端从没渲过（warm 只出三行概括）。12 个月chip 横排，
   * 当月高亮。 */
  html += _yearlyStrip(j.calc);
  html += _klineFold(j.calc);
  html += tailHook('bazi');
  html += '</div>';
  return html;
}

/* R3393：流年K线折叠卡——服务端 calc.kline 直接画（90 柱 candles
 * + 太岁/换运标记）。画布在折叠里、点开才画不白耗首屏。 */
var _lastKline = null;
function _klineFold(calc) {
  try {
    var k = calc && calc.kline;
    if (!k || !k.candles || !k.candles.length) return '';
    _lastKline = k;
    var _seg = function (xs) {
      return (xs || []).map(function (s) {
        return s.a + '–' + s.b + '岁'; }).join('、');
    };
    var _easy = _seg(k.easy_segs), _hard = _seg(k.hard_segs);
    var _notes = [];
    if (_easy) _notes.push('顺段：' + _easy);
    if (_hard) _notes.push('缓段：' + _hard);
    return '<details class="kline-fold">' +
      '<summary>📈 看看你的人生走势（流年K线）</summary>' +
      '<div class="kline-wrap">' +
      '<canvas class="kline-canvas" width="680" height="250"></canvas>' +
      '<div class="kline-legend">' +
      '<span class="kl-dot kl-up"></span>顺 ' +
      '<span class="kl-dot kl-dn"></span>缓 ' +
      '<span class="kl-flag">◎</span>本命年 ' +
      '<span class="kl-flag">●</span>犯太岁 ' +
      '<span class="kl-flag">｜</span>换运 ' +
      '<span class="kl-flag">▣</span>今年' +
      '</div>' +
      (_notes.length ? '<p class="kline-note">' +
        esc(_notes.join('　')) + '</p>' : '') +
      '<p class="kline-note">大运+流年推的节奏线——看趋势不作断语，' +
        '低谷年攒劲，顺段年放手。</p>' +
      '</div></details>';
  } catch (e) { return ''; }
}
function _drawKlineEl(cv, k) {
  try {
    if (!cv || !k || !k.candles || cv._klineDone) return;
    var cs = k.candles;
    var W = cv.width, H = cv.height, ctx = cv.getContext('2d');
    if (!ctx) return;
    var padL = 30, padR = 10, padT = 26, padB = 46;
    var plotW = W - padL - padR, plotH = H - padT - padB;
    var maxS = 4, mid = padT + plotH / 2;
    var bw = Math.max(2, Math.floor(plotW / cs.length) - 1);
    var step = plotW / cs.length;
    /* 背景大运分段横带 */
    for (var i = 0; i < cs.length; i++) {
      var c = cs[i], x = padL + i * step;
      var hgt = (Math.abs(c.score) / maxS) * (plotH / 2);
      var top = c.score >= 0 ? mid - hgt : mid;
      ctx.fillStyle = c.score > 0 ? '#C4624E'
        : (c.score < 0 ? '#8FA98A' : '#C9BCA6');
      ctx.fillRect(x, top, bw, Math.max(2, hgt));
      /* 今年框 */
      if (c.age === k.this_age) {
        ctx.strokeStyle = '#7A5C2E'; ctx.lineWidth = 2;
        ctx.strokeRect(x - 2, padT - 4, bw + 4, plotH + 8);
        ctx.fillStyle = '#7A5C2E';
        ctx.font = '11px "LXGW WenKai",sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('今年', x + bw / 2, padT - 10);
      }
      /* 换运 tick */
      if (c.flags && c.flags.indexOf('换运') >= 0) {
        ctx.strokeStyle = '#B7A98A'; ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, padT - 4); ctx.lineTo(x, padT + plotH + 4);
        ctx.stroke();
      }
      /* 本命年 ◎ / 犯太岁 ● 标在柱脚 */
      var fy = padT + plotH + 16;
      if (c.flags && c.flags.indexOf('本命年') >= 0) {
        ctx.strokeStyle = '#C4624E'; ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(x + bw / 2, fy, 3.4, 0, Math.PI * 2); ctx.stroke();
      } else if (c.flags && (c.flags.indexOf('冲太岁') >= 0 ||
                             c.flags.indexOf('犯太岁') >= 0)) {
        ctx.fillStyle = '#8A4A3C';
        ctx.beginPath();
        ctx.arc(x + bw / 2, fy, 3, 0, Math.PI * 2); ctx.fill();
      }
      /* 年支刻度每 10 岁 */
      if (c.age % 10 === 0) {
        ctx.fillStyle = '#B7A98A';
        ctx.font = '10px "LXGW WenKai",sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(c.age + '岁', x + bw / 2, padT + plotH + 30);
        ctx.fillText(c.year + '', x + bw / 2, padT + plotH + 42);
      }
    }
    /* 中线 */
    ctx.strokeStyle = '#E0D4C0'; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padL - 6, mid); ctx.lineTo(W - 4, mid);
    ctx.stroke();
    cv._klineDone = true;
  } catch (e) {}
}
function _paintKlineNow() {
  try {
    document.querySelectorAll('.kline-canvas').forEach(function (cv) {
      _drawKlineEl(cv, _lastKline);
    });
  } catch (e) {}
}
/* 折叠点开补画（口吻切换重渲时 DOM 换新、_klineDone 复位） */
document.addEventListener('toggle', function (e) {
  if (e.target && e.target.classList &&
      e.target.classList.contains('kline-fold')) {
    var cv = e.target.querySelector('.kline-canvas');
    if (cv) _drawKlineEl(cv, _lastKline);
  }
}, true);

/* R3159：今年逐月 chip 条——每格「M月 干支·十神」，当月高亮。 */
/* R3199：十神 → 日常语标签（合盘互看/年运条共用，与 voice.py
 * TEN_GOD_WARM 的标签语义同源——模块级一份，不抄两份）。 */
var _TEN_GOD_TAG = {比肩:'同伴',劫财:'同侪',食神:'表达',伤官:'点子',偏财:'活水财',
                    正财:'稳定财',七杀:'压力',正官:'规矩',偏印:'直觉',正印:'底气'};
/* R3203：逐月悬停加「这个月适合做什么」——与后端 voice.TEN_GOD_ACTION
 * 首句逐字同（tengod.act.parity 钉死，改了后端忘记同步这里会直接红）。 */
var _TEN_GOD_ACT = {
  比肩:'找个搭子一起做，这类事同行比单干顺',
  劫财:'聚会、AA、清闲置都挺合适',
  食神:'把想法写出来、做出来，慢一点没关系',
  伤官:'提新方案、改旧稿子、试试不一样的做法',
  偏财:'谈谈钱、盘盘手头的进项渠道',
  正财:'记账、复盘收支、把长期计划往前推一格',
  七杀:'挑最难的那件事先攻，限时做完',
  正官:'走流程、办手续、把该见的面见了',
  偏印:'自己琢磨、查资料、随手记灵感',
  正印:'请教信得过的人、复习旧知识、整理资料'};

function _yearlyStrip(calc) {
  try {
    var y = calc && calc.yearly;
    if (!y || !y.months || !y.months.length) return '';
    var now = new Date();
    var curM = (y.year === now.getFullYear()) ? now.getMonth() + 1 : -1;
    var cells = y.months.map(function (m) {
      var on = m.month === curM;
      /* R3199：十神黑话上人话标签+悬停释义——「己丑·正印」对受众是
       * 天书，「正印（底气）」加 title 才读得懂。 */
      var _rel = m.gan_rel || '';
      var _tag = _TEN_GOD_TAG[_rel] || '';
      var _act = _TEN_GOD_ACT[_rel] || '';
      return '<span class="yearly-cell' + (on ? ' on' : '') + '"' +
        (_rel ? ' title="' + esc(_rel) + (_tag ? '' + esc(_tag) + '月' : '') +
          (_act ? '：' + esc(_act) : '') + '"' : '') + '>' +
        '<b>' + esc(String(m.month)) + '月</b>' +
        '<i>' + esc(m.ganzhi || '') + '·' + esc(_tag || _rel) + '</i>' +
        '</span>';
    }).join('');
    return '<div class="yearly-strip-wrap"><div class="yearly-strip-head">' +
      '📅 ' + esc(String(y.year)) + '年逐月 · ' + esc(y.ganzhi || '') +
      '年·' + esc(y.gan_rel || '') + '基调</div>' +
      '<div class="yearly-strip">' + cells + '</div></div>';
  } catch (e) { return ''; }
}

/* R3254（用户要求「五行强弱/十神格局/地支关系能不能可视化」）：
 * 命盘可视化块——四柱格（干支配十神标签）+ 五行雷达 + 地支关系
 * 色块。竞品调研共识（测测/问真/元亨利贞）：四柱网格是命盘签名
 * 视觉，五行用量化图（雷达/条），十神贴柱标注，刑冲合害分组色标。
 * 数据全部来自 paipan.render / calc.ten_gods / calc.five_elements /
 * calc.relations，确定性直渲；任一角缺失整块自动塌下不崩。 */
var _WX_GAN = {甲:'木',乙:'木',丙:'火',丁:'火',戊:'土',己:'土',
               庚:'金',辛:'金',壬:'水',癸:'水'};
var _WX_ZHI = {寅:'木',卯:'木',巳:'火',午:'火',辰:'土',戌:'土',
               丑:'土',未:'土',申:'金',酉:'金',亥:'水',子:'水'};
var _WX_HEX = {木:'#5F9E6E',火:'#D96A4E',土:'#B98A3E',金:'#A0893F',水:'#5E86A8'};

function _baziPlate(j) {
  try {
    var paipan = j.paipan || {};
    var calc = j.calc || {};
    /* ── 四柱解析：render 形如「戊寅年 丁巳月 丁卯日 丙午时」，
     * 时辰未知时第 4 柱已被 _pillarsHonest 换成「时辰未知」。 */
    var pillars = [];
    String(_pillarsHonest(paipan.render, j.hour_known) || '')
      .split(/\s+/).forEach(function (t) {
        var m = t.match(/^(.{1,2})([年月日时])$/);
        if (m && /^[甲乙丙丁戊己庚辛壬癸]/.test(m[1])) pillars.push(m[1]);
      });
    if (pillars.length < 3) return '';
    var hourMiss = pillars.length < 4;
    if (hourMiss) pillars.push('？');
    /* ── 十神按位取用：pos=「年干/月支藏干…」，日干恒标「日主」。 */
    var gods = {};
    (calc.ten_gods || []).forEach(function (t) {
      if (t && t.pos && gods[t.pos] === undefined) gods[t.pos] = t.god;
    });
    var POS = ['年', '月', '日', '时'];
    var cells = pillars.map(function (p, i) {
      var gan = p[0], zhi = p[1] || '';
      /* 时辰未知的第 4 柱只画「？？」——十神是按默认午时算的，
       * 字都是未知还挂神煞是误导，一起压掉。 */
      var missCell = (i === 3 && hourMiss);
      var gGod = missCell ? '' :
        ((i === 2) ? '日主' : (gods[POS[i] + '干'] || ''));
      var zGod = missCell ? '' : (gods[POS[i] + '支藏干'] || '');
      return '<div class="bp-cell' + (i === 2 ? ' bp-day' : '') + '">' +
        '<i>' + POS[i] + '柱</i>' +
        '<div class="bp-chars">' +
          '<b class="wx-' + esc(_WX_GAN[gan] || '') + '">' + esc(gan) + '</b>' +
          '<b class="wx-' + esc(_WX_ZHI[zhi] || '') + '">' + esc(zhi || '？') + '</b>' +
        '</div>' +
        '<div class="bp-gods">' +
          /* R3255：十神 chip 双行化——神名在上、白话标签在下，
           * 「比肩 · 同伴」比光秃秃「比肩」少一次猜。日主不叠标签
           * （日主=你自己，再说「日主·日主」是废话）。 */
          (gGod ? '<span title="天干十神"><b>' + esc(gGod) + '</b>' +
            (_TEN_GOD_TAG[gGod] && gGod !== '日主'
              ? '<i>' + esc(_TEN_GOD_TAG[gGod]) + '</i>' : '') +
            '</span>' : '') +
          (zGod ? '<span title="地支藏干十神"><b>' + esc(zGod) + '</b>' +
            (_TEN_GOD_TAG[zGod] ? '<i>' + esc(_TEN_GOD_TAG[zGod]) + '</i>'
                                : '') +
            '</span>' : '') +
        '</div></div>';
    }).join('');
    var plate = '<div class="bazi-plate">' +
      '<div class="bp-title">🀄 你的四柱盘' +
        '<em>天干地支各管一半，颜色=五行（木绿·火红·土黄·金褐·水蓝）</em></div>' +
      '<div class="bp-grid">' + cells + '</div>';
    /* ── 五行雷达：counts 量化分布，旺/缺徽标直标。 */
    var fe = calc.five_elements || {};
    var counts = fe.counts || {};
    var els = ['木', '火', '土', '金', '水'];
    var max = Math.max.apply(null, els.map(function (e) { return counts[e] || 0; }));
    if (max > 0) {
      var cx = 66, cy = 62, R = 40;
      var ptx = function (i, r) {
        var a = (-90 + i * 72) * Math.PI / 180;
        return (cx + r * Math.cos(a)).toFixed(1) + ',' +
               (cy + r * Math.sin(a)).toFixed(1);
      };
      var rings = [1, 0.66, 0.33].map(function (k) {
        return '<polygon points="' +
          els.map(function (e, i) { return ptx(i, R * k); }).join(' ') +
          '" class="bp-ring"/>';
      }).join('');
      var valPoly = '<polygon points="' +
        els.map(function (e, i) {
          return ptx(i, Math.max(2, R * (counts[e] || 0) / max));
        }).join(' ') + '" class="bp-val"/>';
      var labels = els.map(function (e, i) {
        var a = (-90 + i * 72) * Math.PI / 180;
        var lx = cx + (R + 13) * Math.cos(a), ly = cy + (R + 13) * Math.sin(a);
        var anc = Math.abs(lx - cx) < 6 ? 'middle' : (lx > cx ? 'start' : 'end');
        return '<text x="' + lx.toFixed(1) + '" y="' + (ly + 3).toFixed(1) +
          '" text-anchor="' + anc + '" class="bp-el" fill="' + _WX_HEX[e] +
          '">' + e + '</text>';
      }).join('');
      var dots = els.map(function (e, i) {
        var a = (-90 + i * 72) * Math.PI / 180;
        var r = Math.max(2, R * (counts[e] || 0) / max);
        return '<circle cx="' + (cx + r * Math.cos(a)).toFixed(1) +
          '" cy="' + (cy + r * Math.sin(a)).toFixed(1) + '" r="2.6" fill="' +
          _WX_HEX[e] + '"/>';
      }).join('');
      var badges = '';
      (fe.strong || []).concat(fe.strong_tied || []).forEach(function (e) {
        badges += '<span class="bp-badge bp-strong">🔥 ' + esc(e) + '偏旺</span>';
      });
      (fe.missing || []).forEach(function (e) {
        badges += '<span class="bp-badge bp-miss">· ' + esc(e) + '暂缺</span>';
      });
      if (!badges) badges = '<span class="bp-badge">⚖️ 五行挺匀</span>';
      var srSum = els.map(function (e) {
        return e + (counts[e] || 0);
      }).join('，');
      plate += '<div class="bp-wxrow">' +
        '<svg class="bp-radar" viewBox="0 0 132 124" role="img" ' +
          'aria-label="五行配比：' + esc(srSum) + '">' +
          rings + valPoly + dots + labels + '</svg>' +
        '<div class="bp-wxnote"><b>五行配比</b>' + badges +
          '<span class="bp-wxsub">面积越大越旺；缺的那一角也如实画出来</span></div>' +
        '</div>';
    }
    /* ── 地支关系（R3258 用户点名「要能看懂的关系图」）：
     * 四柱地支画成 4 节点弧线图——每对刑冲合害是一条跨柱的彩色弧，
     * 弧中点落类型小标；端点解析不出的（自刑/三合局等整盘关系）
     * 回落色块。配色沿用色块口径：合绿/冲红/刑橙/害紫/破褐。 */
    var rels = calc.relations || [];
    if (rels.length) {
      var RELPOS = {年:0, 月:1, 日:2, 时:3};
      var relEnd = function (v) {
        var m = String(v || '').match(/([年月日时])支([子丑寅卯辰巳午未申酉戌亥])/);
        return m ? { i: RELPOS[m[1]], z: m[2] } : null;
      };
      var RELC = { he:'#5F9E6E', chong:'#C65B4E', xing:'#D98A3E',
                   hai:'#8E7BA8', po:'#9C7B5C', other:'#B9A48E' };
      var RELN = { he:'合', chong:'冲', xing:'刑', hai:'害', po:'破', other:'' };
      var zhiOf = pillars.map(function (p) { return p[1] || ''; });
      var seen = {}, edges = [], chipsArr = [];
      rels.forEach(function (r) {
        var t = r.type || '';
        var k = /合|会/.test(t) ? 'he' : /冲/.test(t) ? 'chong' :
                /刑/.test(t) ? 'xing' : /害/.test(t) ? 'hai' :
                /破/.test(t) ? 'po' : 'other';
        var txt = r.note || (r.a + '·' + r.b);
        if (seen[txt]) return;
        seen[txt] = 1;
        var ea = relEnd(r.a), eb = relEnd(r.b);
        if (ea && eb && ea.i !== eb.i) {
          edges.push({ a: ea.i, b: eb.i, k: k, t: t, txt: txt });
        } else {
          var dup = t && txt.indexOf(t.replace('相', '')) >= 0;
          chipsArr.push('<span class="bp-rel bp-rel-' + k + '">' +
            (dup ? '' : '<i>' + esc(t) + '</i>') + esc(txt) + '</span>');
        }
      });
      if (edges.length) {
        /* 节点间距 66：4 柱中心 36/102/168/234，r15 末柱收在
         * 249 < viewBox 258 内不裁边。 */
        var NX = function (i) { return 36 + i * 66; }, NY = 58;
        var esvg = '', esr = [];
        /* 同距弧线共面会叠——同跨度第二条再多抬一层。 */
        var spanSeen = {};
        edges.forEach(function (ed) {
          var x1 = NX(ed.a), x2 = NX(ed.b), span = ed.b - ed.a;
          var lift = 18 + (span - 1) * 9 + (spanSeen[span] || 0) * 8;
          spanSeen[span] = (spanSeen[span] || 0) + 1;
          var mx = (x1 + x2) / 2, cy2 = NY - lift;
          esvg += '<path d="M' + x1 + ' ' + NY + ' Q' + mx + ' ' + cy2 +
            ' ' + x2 + ' ' + NY + '" fill="none" stroke="' + RELC[ed.k] +
            '" stroke-width="2.4" stroke-linecap="round" opacity=".88"/>';
          esvg += '<text x="' + mx + '" y="' + (cy2 + 3) +
            '" text-anchor="middle" class="bp-rel-lb" fill="' + RELC[ed.k] +
            '">' + esc(RELN[ed.k] || ed.t.slice(0, 1)) + '</text>';
          esr.push(RELN[ed.k] + '：' + ed.txt);
        });
        var nsvg = pillars.map(function (p, i) {
          var z = zhiOf[i] || '？';
          var col = _WX_HEX[_WX_ZHI[z]] || '#B9A48E';
          return '<g>' +
            '<circle cx="' + NX(i) + '" cy="' + NY + '" r="15" fill="' + col +
              '" fill-opacity=".18" stroke="' + col + '" stroke-width="1.6"/>' +
            '<text x="' + NX(i) + '" y="' + (NY + 4) + '" text-anchor="middle" ' +
              'class="bp-rel-z" fill="' + col + '">' + esc(z) + '</text>' +
            '<text x="' + NX(i) + '" y="' + (NY + 24) + '" text-anchor="middle" ' +
              'class="bp-rel-pos">' + POS[i] + '</text>' +
            '</g>';
        }).join('');
        plate += '<div class="bp-rels bp-rels-map">' +
          '<span class="bp-rels-cap">地支关系</span>' +
          '<svg class="bp-relmap" viewBox="0 0 258 84" role="img" ' +
            'aria-label="地支关系图：' + esc(esr.join('；')) + '">' +
            esvg + nsvg + '</svg>' +
          (chipsArr.length ? '<div class="bp-rel-rest">' +
            chipsArr.join('') + '</div>' : '') +
          '<span class="bp-rel-legend">合=互助 · 冲=波动 · 刑=磕绊 · 害/破=暗耗</span></div>';
      } else if (chipsArr.length) {
        plate += '<div class="bp-rels"><span class="bp-rels-cap">地支关系</span>' +
          chipsArr.join('') +
          '<span class="bp-rel-legend">合=互助 · 冲=波动 · 刑=磕绊 · 害/破=暗耗</span></div>';
      }
    }
    /* ── 十神格局（R3258 F2）：十神归五组人话力量，计数条形。
     * 组名延续 _TEN_GOD_TAG 口径（同伴/表达/财/担当/底气），
     * 日干那枚也计入（比肩=同伴力在场）；数据零虚构，数的就是
     * calc.ten_gods 条目。 */
    var GGROUP = {比肩:'同伴力', 劫财:'同伴力', 食神:'表达力', 伤官:'表达力',
                  偏财:'财力气', 正财:'财力气', 七杀:'担当力', 正官:'担当力',
                  偏印:'底气力', 正印:'底气力'};
    var GCOL = {同伴力:'#B98A3E', 表达力:'#D96A4E', 财力气:'#5F9E6E',
                担当力:'#5E86A8', 底气力:'#8E7BA8'};
    var gcnt = {同伴力:0, 表达力:0, 财力气:0, 担当力:0, 底气力:0};
    (calc.ten_gods || []).forEach(function (t) {
      var g = t && GGROUP[t.god];
      if (g) gcnt[g] += 1;
    });
    var gmax = Math.max.apply(null, Object.keys(gcnt).map(function (k) {
      return gcnt[k];
    }));
    if (gmax > 0) {
      var rows = Object.keys(gcnt).map(function (g) {
        var w = Math.round(gcnt[g] / gmax * 100);
        return '<div class="bp-gbar-row">' +
          '<span class="bp-gbar-k">' + g + '</span>' +
          '<span class="bp-gbar-track"><span class="bp-gbar-fill" style="width:' +
            Math.max(gcnt[g] ? 8 : 2, w) + '%;background:' + GCOL[g] + '">' +
            '</span></span>' +
          '<span class="bp-gbar-n">' + (gcnt[g] || '·') + '</span></div>';
      }).join('');
      plate += '<div class="bp-gbars"><span class="bp-rels-cap">十神力量</span>' +
        rows +
        '<span class="bp-rel-legend">数的是你盘里这类神出现的次数</span></div>';
    }
    return plate + '</div>';
  } catch (e) { return ''; }
}

var _submitBaziBusy = 0;   /* R8 P2-2：form submit 不经 on()，自加在途锁（时间戳租约） */
var _submitBaziLast = { key: '', ts: 0 };   /* R230q（R28-P3-14）同参防抖 */
async function submitBazi(event) {
  if (event) event.preventDefault();
  /* R3259（同 _birthBusy 案例）：布尔在途锁里若有 await 楔死，
   * 锁永真+按钮永灰=「卡死」。改时间戳租约——超 26s 视为僵死可重夺。 */
  if (_submitBaziBusy && Date.now() - _submitBaziBusy < 26000) return;
  // 连点/回车连击 → 只发一次，防并发覆盖
  /* R230t（R33-P1-2）：同参防抖判定提到 busy() 之前——原先 busy 先清屏
   * 再 paint 提示，把刚渲染的结果卡整段顶掉（「上面那张」已不存在）。
   * 现在命中防抖只弹 toast，结果卡原样保留。 */
  var _bkey0 = JSON.stringify(baziBody());
  if (_bkey0 === _submitBaziLast.key &&
      performance.now() - _submitBaziLast.ts < 1500) {
    showToast('这盘刚算过，结果就是上面那张～', 'info');
    return;
  }
  var _sbLease = Date.now();
  _submitBaziBusy = _sbLease;
  /* R233k（R45-Top5-2）：form submit 不经 on()——提交钮手动补忙态。 */
  var _bb = el('submit');
  if (_bb) { _bb.disabled = true; _bb.classList.add('is-working');
    _bb.setAttribute('aria-busy', 'true'); }
  busy('result', '计算中…');
  try {
    const body = JSON.parse(_bkey0);   /* 复用上面防抖已算出的 body——baziBody 有 toast 副作用，不调两次 */
    /* R230f续4（R16-P2-4b）：与出生抽屉同一套预检——空/越界不走
     * 请求，直接站内中文提示（原来要等一轮 422）。 */
    if (body.year == null || body.month == null || body.day == null
        || body.year < 1900 || body.year > 2100
        || body.month < 1 || body.month > 12 || body.day < 1
        || body.day > (body.calendar_type === 'lunar' ? 30 : 31)) {
      /* R233k：预检失败聚焦出错格 + toast（此前只有屏外一行灰字）。 */
      var _fb = (body.year == null || body.year < 1900 || body.year > 2100) ? 'year'
        : (body.month == null || body.month < 1 || body.month > 12) ? 'month' : 'day';
      _failField(_fb, 'result', '日期看起来不太对，检查一下年月日再试～');
      return;
    }
    /* R2350e（R101-P2-2）：时辰/分钟/问事时辰同界前端先拦——
     * 越界免一轮后端 400。 */
    if (_badRange('hour', 0, 23)) {
      _failField('hour', 'result', '时辰填 0–23，不知道就留空'); return;
    }
    if (_badRange('minute', 0, 59)) {
      _failField('minute', 'result', '分钟填 0–59'); return;
    }
    if (_badRange('ask_hour', 0, 23)) {
      _failField('ask_hour', 'result', '问事时辰填 0–23'); return;
    }
    if (_badRange('range_hour', 0, 23)) {
      _failField('range_hour', 'result', '区间时辰填 0–23'); return;
    }
    /* R2350e（R101-P2-3）：range 端此前无年份界——1500 直发后端
     * 出 200（与 ask_date 的 1900–2100 口径不一致）。 */
    if (body.scope === 'range') {
      var _rgBad = ['range_start', 'range_end'].filter(function (_rid) {
        var _rv = val(_rid);
        if (!_rv) return false;
        var _ry = parseInt(_rv.slice(0, 4), 10);
        return _ry < 1900 || _ry > 2100;
      });
      if (_rgBad.length) {
        _failField(_rgBad[0], 'result', '区间年份要在 1900–2100 之间');
        return;
      }
    }
    /* R233k（R45-Top5-1）：1-31 合法但当月不存在（2/31）也在前端拦。
     * R2350e（R101-P1-2）：农历月长只有 29/30 天且按年变——公历月长
     * 校验会把合法的农历二月三十误拦（后端能算）。农历只做 1-30 粗检，
     * 真存在性交给后端换算报文。 */
    var _badd = (body.calendar_type === 'lunar') ? null
      : _badYmdField('year', 'month', 'day');
    if (_badd) {
      _failField(_badd, 'result',
        '这一天不存在。' + num('month') + ' 月没有 ' + num('day') + ' 号');
      return;
    }
    WARM_LAST_QUESTION = body.question || '';   /* R206b US4：共情模板选择依据 */
    const j = await postJSON('/api/bazi', body);
    /* 只在成功后记账——失败重试（failWithRetry）不该被同参防抖拦 */
    _submitBaziLast = { key: _bkey0, ts: performance.now() };
    /* R230y：本人表单成功提交 → 存「我的生日」并代入其余同人表单。
     * R2350g（R106-F3）：农历生日也落档——后端回显 birth_solar（换算后
     * 的公历），档案记公历日期+农历原值标注，生日横幅/倒计时通吃。 */
    var _bs = (j.birth_solar && j.birth_solar.y) ? j.birth_solar
      : { y: body.year, m: body.month, d: body.day };
    if (!_fieldsUntouched(['year','month','day','hour','minute',
                           'calendar_type','lunar_year','lunar_month',
                           'lunar_day','gender']))
    _meSave('me', { y: _bs.y, m: _bs.m, d: _bs.d,
      h: body.hour_known ? body.hour : null, g: body.gender,
      lunar: (body.calendar_type === 'lunar')
        ? ('农历' + body.lunar_year + '年' + body.lunar_month + '月' +
           body.lunar_day + '日' + (body.lunar_leap ? '（闰）' : ''))
        : null });
    _meFillAll();
    const paipan = j.paipan || {};
    /* R206b US1：给陪伴层喂坐标事实（干支五行词，非 PII——不含生日） */
    try {
      const _warmFacts = (j.warm && j.warm.details || [])
        .map(function (d) { return d.title + '：' + (d.lines || []).slice(0, 2).join('；'); })
        .slice(0, 3);
      const _pp = paipan.render || '';
      CHAT_LAST_FACTS = (_pp ? ['四柱：' + _pp] : []).concat(_warmFacts);
      /* R2516（用户反馈「小满回复泛泛」）：把已生成的解读句喂进坐标——
       * 此前模型只有孤立标签（四柱/元素），回复只能空共情；有了解读原句
       * 小满能照着具体内容延展，而不是重复正确废话。 */
      var _rp = (j.warm && j.warm.reply) || [];
      if (_rp.length) CHAT_LAST_FACTS.push('盘面解读：' + _rp.slice(0, 2).join('；'));
      /* R233r（R49-Top5-2）：能量卡坐标补上——元素/幸运色/幸运数字
       * 是用户聊「我今天穿什么色」类问题的锚。 */
      var _ec0 = (j.warm && j.warm.energy_card) || {};
      if (_ec0.element) CHAT_LAST_FACTS.push('本命元素：' + _ec0.element);
      var _lc0 = _ec0.lucky_colors, _ln0 = _ec0.lucky_numbers;
      if (_lc0 && _lc0.length) CHAT_LAST_FACTS.push('幸运色：' + _lc0.join('、'));
      if (_ln0 && _ln0.length) CHAT_LAST_FACTS.push('幸运数字：' + _ln0.join('、'));
    } catch (e) { CHAT_LAST_FACTS = []; }
    paint('result', buildBaziResult(j));
    /* R2512：口吻切换重画后直绑按钮会灭——绑定收进 rebind 登记。 */
    var _rbBazi = function () {
      on('shareBazi', function () { return downloadPoster(j, 'bazi'); });
      on('shareBaziYear', function () { return downloadPoster(j, 'bazi-yearly'); });
      on('shareBaziKline', function () {
        return downloadPoster(j, 'bazi-kline'); });
    };
    rememberResult('bazi', j, body.question || '', body);   /* R219b（P0-2）：聊聊上下文；v2 补 body（性别） */
    revealResult('result');            // 005 判据 1：提交后无需滚动即见结论
    /* R230n续（R23-P3-6）→ R3242e：dirty 广播收口进 rememberResult
     * 按 _PH_BUILDERS 品类统一发——七类结果全品类即时失效。 */
    pollAiPolish('result', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    _rbBazi();   /* R218a-巡2（N-04）：传 view 让通用模板接管 */
    _paintKlineNow();   /* R3393：折叠内画布——buildBaziResult 已把
                            payload 存进 _lastKline */
    /* R219b（P0-4）：历史记录不再落库，无「最近解读」列表可刷新。 */
  } catch (e) {
    /* R218a-巡4（E-a/E-b）：失败态清成功期说明文字 + 内联重试按钮。 */
    failWithRetry('result', '计算失败：' + e.message, function () { submitBazi(); });
  } finally {
    /* R3259：只清自己这轮的租约，旧楔死请求的晚到复位不得抹新轮。 */
    if (_submitBaziBusy === _sbLease) _submitBaziBusy = 0;
    var _bb2 = el('submit');
    if (_bb2) { _bb2.disabled = false; _bb2.classList.remove('is-working');
      _bb2.removeAttribute('aria-busy'); }
  }
}

/** 历法/范围切换时显隐相关字段（原实现完全没有这段，选了农历也没提示）。 */
function syncBaziForm() {
  const calendar = val('calendar_type') || 'solar';
  const scope = val('scope') || 'day';
  const leap = el('f_lunar_leap');
  if (leap) leap.hidden = calendar !== 'lunar';
  const yearLabel = document.querySelector('#f_year label');
  if (yearLabel) yearLabel.textContent = calendar === 'lunar' ? '农历年份' : '公历年份';
  const askRow = el('ask_row');
  const rangeRow = el('range_row');
  if (askRow) askRow.hidden = scope === 'range';
  if (rangeRow) rangeRow.hidden = scope !== 'range';
}

/* ── 读书：检索 / 深度研究 / 定位 / 比对 / 书目 / 线程 ──────────── */

/* R2350e：编址方式→有效字段白名单——显隐（_syncAddrFields）与
 * 发包（doAddr）共用一张表。R2349v 原声明在 init IIFE 内，此处
 * 提为模块级让两处都能读到。 */
var _ASCHEME_FIELDS = {
  zhouyi:  ['aguan', 'ayao'],
  bcv:     ['aname', 'aaddr1', 'aaddr2'],
  yilin:   ['aguan'],
  booksec: ['aaddr1'],
  /* R3369（审-P1-2）：play/euclid 的 addr_name 是剧名/卷名，
   * 此前被收起——必填参数藏在 UI 外根本填不进。 */
  play:    ['aname', 'aaddr1', 'aaddr2'],
  euclid:  ['aname', 'aaddr1', 'aaddr2']
};
/* R230q（R28-P1-1b）：线程状态过滤——initReading 委托（筛选 chip）
 * 与 app_research.js 的 _threadListHtml 共用。 */
var _threadStatus = 'open';

/* R2400（R122-P1-1 下）：研究台 15 个 handler 拆进 app_research.js
 * （照 app_poster.js 同款 stub+动态注入）。stub 保名字与签名：
 * 调用点（initReading 的 on()/Enter 委托/activateRsec/BSSEC_PANELS/
 * 全局 click 委托）一律先打 stub → 拉 chunk → 真身接管。 */
var _researchJsLoad = null;
function _loadResearchJs() {
  if (!_researchJsLoad) {
    _researchJsLoad = new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = '/static/app_research.js' + _assetSuffix();
      s.onload = function () { res(); };
      s.onerror = function () {
        _researchJsLoad = null;
        rej(new Error('研究台组件没加载上：网好了再点一次'));
      };
      document.head.appendChild(s);
    });
  }
  return _researchJsLoad;
}
function _researchStub(name) {
  var _a = arguments;
  var _rest = Array.prototype.slice.call(_a, 1);
  return _loadResearchJs().then(function () {
    return window[name].apply(null, _rest);
  }).catch(function (e) {
    /* chunk 加载失败兜底——不然未处理 rejection 静默吞掉点击。 */
    showToast((e && e.message) || '研究台组件没加载上：网好了再点一次', 'warn');
  });
}
function doSearch() { return _researchStub.apply(null, ['doSearch'].concat([].slice.call(arguments))); }
function doResearch() { return _researchStub.apply(null, ['doResearch'].concat([].slice.call(arguments))); }
function doAddr() { return _researchStub.apply(null, ['doAddr'].concat([].slice.call(arguments))); }
function doCompare() { return _researchStub.apply(null, ['doCompare'].concat([].slice.call(arguments))); }
function doWorks() { return _researchStub.apply(null, ['doWorks'].concat([].slice.call(arguments))); }
function searchByWork() { return _researchStub.apply(null, ['searchByWork'].concat([].slice.call(arguments))); }
function doThread() { return _researchStub.apply(null, ['doThread'].concat([].slice.call(arguments))); }
function _threadListHtml() { return _researchStub.apply(null, ['_threadListHtml'].concat([].slice.call(arguments))); }
function _threadListPaint() { return _researchStub.apply(null, ['_threadListPaint'].concat([].slice.call(arguments))); }
function deleteThread() { return _researchStub.apply(null, ['deleteThread'].concat([].slice.call(arguments))); }
function showThread() { return _researchStub.apply(null, ['showThread'].concat([].slice.call(arguments))); }
function doCompareWorks() { return _researchStub.apply(null, ['doCompareWorks'].concat([].slice.call(arguments))); }
function doConcept() { return _researchStub.apply(null, ['doConcept'].concat([].slice.call(arguments))); }
function doBookStructure() { return _researchStub.apply(null, ['doBookStructure'].concat([].slice.call(arguments))); }
function doBookChapter() { return _researchStub.apply(null, ['doBookChapter'].concat([].slice.call(arguments))); }
function doBookSummary() { return _researchStub.apply(null, ['doBookSummary'].concat([].slice.call(arguments))); }

/* ── 六爻 / 黄历 / 起名 / 桃花 / 塔罗 / 合婚 ───────────────────── */

/** 六爻结果区 HTML 构建（抽成纯函数，可就地重画）。 */
function buildLiuyaoResult(j) {
  const ben = j.ben || {};
  const bian = j.bian || {};
  let html = '<div class="card"><h2>🔮 六爻卦象</h2>';
  /* R2350b（R98-P0-1 附带）：回显起卦时间——卦是按哪天起的心里有数。 */
  if (j.cast_at) {
    html += '<div style="font-size:12px;color:var(--muted);margin:-2px 0 6px">' +
      '🕐 起卦：' + esc(j.cast_at) + '</div>';
  }
  /* R216b 续（UX 队列 U-007）：解读先给人话结论（warm.reply 已是结论式，
   * 这里把它提到坐标区之前常显），再画卦象。
   * R216b 续4（U-022）：本块仅 warm 模式渲染；warm 模式下页尾
   * renderVoice 跳过（见下）——否则同一批解读文案与免责 badge 出现两遍。 */
  const warm = j.warm || {};
  /* R218a-08：问题绑定首屏 hook——用户问工作/感情/学业/财运时，
   * 在 warm.reply 之前给一句「针对你问的 X」让用户秒级感到被听到。
   * 6 套关键词模板 + 通用兜底。 */
  if (j.question) {
    html += liuyaoQuestionHook(j.question, ben, bian, j.paipan);
  }
  if (warm.reply && warm.reply.length) {   /* R3212：单版化 */
    html += '<div class="warm-wrap"><div class="warm-l0" style="font-size:17px;">' +
      esc(warm.one_liner || '') + '</div><div class="warm-reply">';
    /* R2349q（R81-P1-15）：reply 截断 3→6——后端产出上限即 6 行，
     * 原 3 行把动爻白话/变卦方向/经文引导整段吃掉。 */
    warm.reply.slice(0, 6).forEach(function (ln) {
      html += '<p>' + esc(ln) + '</p>';
    });
    html += '</div>';
    if (warm.badge) html += '<div class="warm-badge">' + esc(warm.badge) + '</div>';
    html += '</div>';
  }
  html += '<p class="paipan-line" style="color:var(--c-liuyao);">' +
    esc(ben.gua_name || '') + '（第 ' + esc(ben.gua_number) + ' 卦）</p>';
  // 实测 lines[] 是 {position,yang,moving,symbol}，moving_lines[] 是数字。
  if (ben.lines && ben.lines.length) {
    /* R216b 续（U-007）：爻象图形化——自上而下（上爻→初爻）、每爻带爻位名
     * 与阴阳符号（⚊阳 ⚋阴），动爻加「○/×」动标并高亮。 */
    const YAO_NAME = {6:'上爻',5:'五爻',4:'四爻',3:'三爻',2:'二爻',1:'初爻'};
    /* R2350b（R98-P1-3）：六亲/六神随行白话——与 voice._LIUQIN_WARM
     * 同口径，让卦图词和正文人话对得上号。 */
    var _LIUQIN_PLAIN = {'官鬼': '事业与忧心', '妻财': '财物',
      '兄弟': '同辈竞争', '父母': '文书庇护', '子孙': '晚辈与解忧'};
    var _LIUSHEN_PLAIN = {'青龙': '喜气', '朱雀': '口舌', '勾陈': '拖延',
      '螣蛇': '缠绕', '白虎': '激烈', '玄武': '暧昧'};
    html += '<div class="yao-stack">';
    /* R228o：跨行链式改为命名中间变量——契约探针逐行归因，
     * 也让「降序取爻位」的意图更直白。 */
    var _sortedLines = ben.lines.slice()
      .sort(function (a, b) { return b.position - a.position; });
    /* R2349q（R81-P2-14）：paipan 坐标层——六神/六亲/世应此前算完
     * 只进 warm 文案，界面不可见。按爻位合一行尾小注（muted），
     * 世/应给角标；paipan 缺席（旧缓存/降级）时整列不出现。 */
    var _ppLines = {};
    var _ppBen = (j.paipan && j.paipan.ben_gua) || null;
    if (_ppBen && Array.isArray(_ppBen.lines)) {
      _ppBen.lines.forEach(function (pl) { _ppLines[pl.position] = pl; });
    }
    _sortedLines.forEach(function (ln) {
        const mark = ln.moving ? (ln.yang ? ' ○' : ' ×') : '';
        /* R230x（V-5）：爻画真图形——阳=通长实条、阴=断两截，动爻加红点。
         * 原 ⚊/⚋ 字形在部分机型渲染成小横线、卦感弱；mark 文本保留。 */
        var _yaoCls = ln.yang ? 'yang' : 'yin';
        var _yaoBars = ln.yang ? '<i></i>' : '<i></i><i></i>';
        var _pl = _ppLines[ln.position];
        var _coord = '';
        /* R3173：伏神注——本宫卦里藏在这爻底下的六亲星，
         * 用神缺位时这是唯一的落点。 */
        var _fsAt = (((j.paipan || {}).fushen) || []).filter(
          function (f) { return f.position === ln.position; });
        if (_fsAt.length) {
          _coord += '<span class="yao-coord yao-fu" title="伏神。' +
            '本宫卦藏在这爻底下的星，透出才算数">伏·' +
            esc(_fsAt.map(function (f) { return f.liuqin || ''; })
                  .join('')) + '</span>';
        }
        if (_pl) {
          /* R2350b（R98-P1-3）：六亲/六神原词裸奔——行尾随行白话让
           * 图上词和正文人话对上号（正文说「事业与忧心」，图上
           * 只印「官鬼」用户建立不了映射）。 */
          var _lq = _LIUQIN_PLAIN[_pl.liuqin];
          var _sj = _LIUSHEN_PLAIN[_pl.shen];
          var _coordTxt = [_pl.liuqin, _pl.shen].filter(Boolean).join('·');
          var _coordHint = [_lq, _sj].filter(Boolean).join('·');
          /* R3173 连带：上面伏神注先入 _coord，这里必须 += 不能 = */
          _coord += '<span class="yao-coord"' +
            (_coordHint ? ' title="' + esc(_coordHint) + '"' : '') + '>' +
            esc(_coordTxt) +
            (_coordHint ? '<i class="yao-plain">' + esc(_coordHint) +
             '</i>' : '') + '</span>' +
            (_pl.is_shi ? '<span class="yao-seat" title="世=你自己">世</span>'
             : _pl.is_ying
             ? '<span class="yao-seat ying" title="应=对方/这件事">应</span>'
             : '');
        }
        html += '<div class="yao-row' + (ln.moving ? ' moving' : '') + '">' +
          '<span class="yao-name">' + esc(YAO_NAME[ln.position] || ('第' + ln.position + '爻')) +
          '</span>' + _coord +
          '<span class="yao-sym" role="img" aria-label="' +
          (ln.yang ? '阳爻' : '阴爻') + (ln.moving ? '，动爻' : '') + '">' +
          '<span class="yao-bar ' + _yaoCls + '">' + _yaoBars + '</span>' +
          (ln.moving ? '<span class="yao-dot"></span>' : '') +
          '<span class="yao-mark">' + esc(mark) + '</span></span></div>';
      });
    html += '</div>';
    /* R2350b（R98-P1-3）：图例——世/应角标此前无任何说明。 */
    if (_ppBen) {
      /* R3169：月建/日辰上卦图——传统排盘第一行就是它（断旺衰的锚），
       * 卦图只印六亲六神等于坐标系少一轴；旧缓存缺键时整行不出现。 */
      var _yj2 = (j.paipan || {}).yuejian || '';
      var _rc2 = (j.paipan || {}).richen || '';
      var _xk2 = (j.paipan || {}).xunkong;
      var _lh2 = ((j.paipan || {}).ben_gua || {}).liuhe_chong || '';
      if (_yj2 || _rc2 || (_xk2 && _xk2.length) || _lh2) {
        html += '<div class="yao-legend">' +
          (_yj2 ? '月建 ' + esc(_yj2) + '　' : '') +
          (_rc2 ? '日辰 ' + esc(_rc2) + '　' : '') +
          ((_xk2 && _xk2.length)
           ? '旬空 ' + esc(_xk2.join('')) + '　' : '') +
          (_lh2 ? '<b>' + esc(_lh2) + '卦</b><i class="yao-plain">' +
                  (_lh2 === '六合' ? '主缠主聚' : '主散主快') + '</i>'
                : '') +
          ((_xk2 && _xk2.length)
           ? '<i class="yao-plain">（空支事未坐实）</i>' : '') +
          '</div>';
      }
      html += '<div class="yao-legend">世=你自己　应=对方/这件事　' +
        '官鬼=事业与忧心　妻财=财物　父母=文书庇护　兄弟=同辈竞争　' +
        '子孙=晚辈与解忧</div>';
    }
  }
  if (ben.moving_lines && ben.moving_lines.length) {
    html += '<p>动爻：' + esc(ben.moving_lines.join('、')) + ' 爻：变化从这里发生</p>';
  } else {
    html += '<p>无动爻（静卦），当下格局稳住，变化的劲不明显</p>';
  }
  /* R2349q（R81-P0-3 连带）：静卦（变卦=本卦）不再渲染「变卦」行——
   * 与「无动爻，格局稳住」表里互搏。 */
  if (bian.gua_name && bian.gua_name !== ben.gua_name) {
    html += '<p style="margin-top:8px;color:var(--secondary);">变卦：' +
      esc(bian.gua_name) + '（第 ' + esc(bian.gua_number) + ' 卦）</p>';
  }
  /* R3212：单版化——卦象推导（interpretation）与本/变卦经文收进
   * 一个折叠块，数据零删减。 */
  {
    const evAll = [].concat(j.ben_jing || [], j.bian_jing || []);
    var _lyPro = renderInterpretation(j.interpretation, '📖 卦象解读');
    if (evAll.length || _lyPro) {
      html += '<details class="warm-basis warm-pro-fold">' +
        '<summary>📐 卦象推导与经文（' + evAll.length + ' 段经文，展开看）</summary>' +
        (_lyPro || '') +
        (evAll.length ? renderHits(evAll, { empty: '' }) : '') +
        '</details>';
    }
  }
  /* R221b：交叉引用收口 7/7——六爻不收生日，引今天值宫 × 动爻多寡。
   * 放在 if/else 之外：温柔版与专业版都该看到这段。 */
  if (j.cross_ref && j.cross_ref.message) {
    html += '<div class="cross-ref"><span class="cross-ref-icon">☯️</span>' +
      esc(j.cross_ref.message) +
      crossDirBadge(j.cross_ref, 'gua_direction', '卦象') + '</div>';
  }
  /* R3154：六爻接 AI 解读块——卦象坐标+判词行进 facts，bazi 同机制 */
  html += renderAiPolish(j);
  html += tailHook('liuyao');
  /* R2512：分享按钮挪进 build——此前 submit 后手工 createElement
   * 挂进 .card，口吻切换重画即消失（build 不含它）。 */
  html += '<button class="ghost fav-btn" type="button" id="shareLiuyao" ' +
    'title="生成分享图" style="margin:10px 0 0">📸 分享图</button>';
  html += '</div>';
  return html;
}

/* R216b 续（U-007）：时间起卦的年月日默认取「打开页面的当天」——原 HTML
 * 写死 1990/5/15，用户不看日期直接摇就会用错时间坐标。进视图时同步一次。 */
function syncLiuyaoToday() {
  const t = new Date();
  /* R233k（R45-P1-4）：与 hlInitToday/xzInitDate 拉齐——只在空值时填，
   * 用户填好的起卦时间切走再回来不再被静默重置。 */
  const setv = function (id, v) { const e2 = document.getElementById(id); if (e2 && !e2.value) e2.value = v; };
  setv('ly_year', t.getFullYear());
  setv('ly_month', t.getMonth() + 1);
  setv('ly_day', t.getDate());
}

/* R222b（E-301 P0）：黄历默认日期。原 HTML 写死 value="2026/8/19"，
 * 审查轨发现用户点进黄历看到的是 8 天前的「今天适合」，聊天首句也带错日期。
 * 同 syncLiuyaoToday 的先例：进视图时填今天，且**只在空值时填**——
 * 用户手动改过日期后切走再回来不该被重置。 */
function hlInitToday() {
  const t = new Date();
  const setv = function (id, v) {
    const e2 = document.getElementById(id);
    if (e2 && !e2.value) e2.value = v;
  };
  setv('hl_year', t.getFullYear());
  setv('hl_month', t.getMonth() + 1);
  setv('hl_day', t.getDate());
  /* R229c（R5 审计 P2）：进页直接查今天——星座页进页即出今日运，
   * 黄历只见表单口径不一致。仅在结果区为空时触发，切走再回来不重复打。
   * R230h（R20-F2）：占位文案 textContent 恒非空，原门永远为假——
   * 改成看「是否只有占位节点」（data-ph 标记）。 */
  var _res = document.getElementById('hlResult');
  if (_res && (!_res.firstElementChild || _res.querySelector('[data-ph]'))) {
    /* R2350a（R94-P1-2）：深链带日期时按那天查，不落今天。
     * R2350b 修（R99-P0）：此前用 setv——「空才填」恒败（
     * hlInitToday 已先把今天填进去），深链日白写。直接赋值覆盖。 */
    var _dd = window.__hlDeepDate; window.__hlDeepDate = null;
    if (_dd) {
      ['hl_year', 'hl_month', 'hl_day'].forEach(function (id, i) {
        var _e = el(id);
        if (_e) _e.value = +_dd.split('-')[i];
      });
      doHuangli(null, true);
    } else {
      doHuangli(0, true);
    }
  } else if (_HL.renderedOn && _HL.renderedOn !== todayIso()) {
    /* R2349k（R72-B1）：隔夜回来的卡是昨天渲染的——判词「今天」话术
     * 已错一天。按渲染日判陈旧（不看显示日——主动翻「昨天」的卡是
     * 今天渲的，不陈旧）。 */
    ['hl_year', 'hl_month', 'hl_day'].forEach(function (id) {
      var _e = el(id); if (_e) _e.value = '';
    });
    setv('hl_year', t.getFullYear());
    setv('hl_month', t.getMonth() + 1);
    setv('hl_day', t.getDate());
    doHuangli(0, true);
  }
  hlLoadWeek();   /* R231d：未来 7 天速览条随进页加载（每会话一次） */
}

/* R231d：未来 7 天宜忌速览——今天起一排 7 格（星期+日期+首个宜/忌项
 * 白话映射），点格走既有 doHuangli(offset) 翻页路径，API 零新增。 */
var _hlWeekDone = false;
async function hlLoadWeek() {
  /* R2502：_hlWeekDone 此前请求发出前就置真——首访断网失败后
   * 「网还没连上」在本会话内永不重试；catch 同理把条带永久藏掉。
   * 改为成功后落真，失败路径保持可重入。 */
  if (_hlWeekDone) return;
  var box = el('hlWeek');
  if (!box) return;
  /* R2502：click 监听此前在成功分支里每次重跑都叠加一份（跨零点
   * 复位后重进就会多绑）——挪到一次绑定闸后，幂等。 */
  if (!box.dataset.wbound) {
    box.dataset.wbound = '1';
    box.addEventListener('click', _hlWeekClick);
  }
  var today = new Date();
  var days = [];
  for (var i = 0; i < 7; i++) {
    var dt = new Date(today); dt.setDate(today.getDate() + i);
    days.push(dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0') +
      '-' + String(dt.getDate()).padStart(2, '0'));
  }
  try {
    var js = await Promise.all(days.map(function (ds) {
      return api('/api/huangli?date=' + ds, { silent: true })
        .catch(function () { return null; });
    }));
    /* R2400（R124-P2-5）：全断网时此前渲染 7 个「宜 —」裸格——
     * 收成一句实话，不摆一排死格。
     * R2502：不置 _hlWeekDone——下次进视图重试，离线句不再粘住。 */
    if (js.every(function (j) { return !j; })) {
      box.innerHTML = '<div class="hl-week-title">📅 这 7 天宜忌速览</div>' +
        '<div class="no-evidence">网还没连上，周历翻不开，联网后再进来就有了</div>';
      box.hidden = false;
      return;
    }
    var WD = ['日', '一', '二', '三', '四', '五', '六'];
    var html = '<div class="hl-week-title">📅 这 7 天宜忌速览' +
      '<span class="hl-week-sub">点一天直接翻过去</span></div>' +
      '<div class="hl-week-row">';
    js.forEach(function (j, i) {
      var dt = new Date(days[i] + 'T00:00:00');
      var wd = i === 0 ? '今天' : ('周' + WD[dt.getDay()]);
      var yi = (j && j.yi && j.yi.length) ? (_HL_YI_MAP[j.yi[0]] || j.yi[0]) : '—';
      var ji = (j && j.ji && j.ji.length) ? (_HL_JI_MAP[j.ji[0]] || j.ji[0]) : '';
      /* R2349k（R72-B7）：格子记绝对日不记下标——下标是相对渲染时
       * 「今天」的偏移，跨零点后点同一格会翻到错那天。点击时才换算
       * 偏移，落在点击当刻的今天。 */
      html += '<button type="button" class="hl-week-cell" data-hldate="' +
        esc(days[i]) + '"' +
        /* R2350a（R94-P2-14）：aria-current="date" 只留在今天格——
         * 此前点击时把它挪给「选中格」用，语义错了（读屏误报成当天）。
         * 选中日走 class.active + aria-pressed。 */
        (i === 0 ? ' aria-current="date"' : '') + '>' +
        '<span class="hl-week-wd">' + esc(wd) + '</span>' +
        '<span class="hl-week-date">' + esc((dt.getMonth() + 1) + '/' + dt.getDate()) + '</span>' +
        '<span class="hl-week-yi">宜 ' + esc(_gSlice(yi, 6)) + '</span>' +
        (ji ? '<span class="hl-week-ji">忌 ' + esc(_gSlice(ji, 6)) + '</span>' : '') +
        '</button>';
    });
    html += '</div>';
    box.innerHTML = html;
    box.hidden = false;
    _hlWeekDone = true;   /* R2502：成功才落真——失败路径保持可重入 */
  } catch (e) { box.hidden = true; }
}

/* R2502：周历格点击处理抽成具名函数——配合 dataset.wbound 一次绑定，
 * 不再随每次成功重跑叠加监听。 */
function _hlWeekClick(e) {
  var box = el('hlWeek');
  if (!box) return;
  var c = e.target.closest('.hl-week-cell');
  if (!c) return;
  box.querySelectorAll('.hl-week-cell').forEach(function (x) {
    x.classList.remove('active');
    x.removeAttribute('aria-pressed');
  });
  c.classList.add('active');
  /* R2350a（R94-P2-14）：选中日改 aria-pressed——aria-current 是
   * 「当前日期」语义，留给今天格（它在渲染时已钉在 i===0）。 */
  c.setAttribute('aria-pressed', 'true');
  /* R2349k（R72-B7）：点击当刻用本地日换算偏移——跨零点打开的
   * 页面点格子仍落到格子上写的那天。 */
  var _wdd = c.dataset.hldate;
  var _wdt = new Date(); _wdt.setHours(0, 0, 0, 0);
  var _woff = Math.round(
    (new Date(_wdd + 'T00:00:00') - _wdt) / 86400000);
  if (!isFinite(_woff)) return;
  doHuangli(_woff);
}

var _LY_GEN = 0;   /* R2502：六爻在途代际——retry 钮不走 guardedCall，
                    * 与主提交并发时后到覆盖先到。照 _XZ_GEN 先例。 */
async function doLiuyao() {
  var _gen = ++_LY_GEN;
  busy('lyResult', '摇卦中…');
  // 实测后端只认 coins|time（HTML 里原来的 "dice" 会得到 400）。
  const method = val('ly_method') === 'coins' ? 'coins' : 'time';
  const body = { method: method };
  /* R2349s（R83 残余）：coins/time 两种起卦都锚浏览器本地日——
   * 跨零点 ±TZ 窗口内「今日值宫」/应期别再漂到服务器日。 */
  body.client_date = todayIso();
  if (method === 'coins') {
    /* R216b 续（U-006）：同塔罗——高级折叠里的 Seed 留空即自动生成。 */
    const seedRaw = val('ly_seed');
    if (seedRaw !== '' && seedRaw != null) body.seed = num('ly_seed');
  } else {
    /* R2350b（R98-P0-1 续）：留空逐项补现在（时间起卦本义是「以当下
     * 起卦」）。R2350e（R101-P2-9 回面）：补值保留，但四个框的
     * placeholder 逐格说清「留空=本项当前值」——用户知道哪格会按
     * 当下填，行为是文案明示的约定而非暗中改写。 */
    var _now4 = new Date();
    var _dfl = { ly_year: _now4.getFullYear(),
                 ly_month: _now4.getMonth() + 1,
                 ly_day: _now4.getDate(),
                 ly_hour: _now4.getHours() };
    ['ly_year', 'ly_month', 'ly_day', 'ly_hour'].forEach(function (_fid) {
      var _fe = document.getElementById(_fid);
      if (_fe && _fe.value === '') _fe.value = _dfl[_fid];
    });
    /* R2350e：留空格补完后再读——num() 拿的是 DOM 值。 */
    body.year = num('ly_year');
    body.month = num('ly_month');
    body.day = num('ly_day');
    body.hour = num('ly_hour');
    /* R230d（R16-P2-4）：起卦时间是四个校验入口里唯一没做年份
     * 范围的——超界交给后端 422 才报，前端先说人话。 */
    if (body.year != null && (body.year < 1900 || body.year > 2100)) {
      _failField('ly_year', 'lyResult', '年份要在 1900–2100 之间');
      return;
    }
    /* R2350e（R101-P2-2）：ly_hour=25 此前要吃一轮后端 400。 */
    if (_badRange('ly_hour', 0, 23)) {
      _failField('ly_hour', 'lyResult', '时辰填 0–23'); return;
    }
    var _lb = _badYmdField('ly_year', 'ly_month', 'ly_day');
    if (_lb) {
      _failField(_lb, 'lyResult',
        '这一天不存在。' + num('ly_month') + ' 月没有 ' + num('ly_day') + ' 号');
      return;
    }
  }
  const q = val('ly_question');
  if (q) body.question = q;
  body.client_date = todayIso();   /* R230m：今日值宫锚本地日 */
  /* R3177：一事不二占——同日同问题重复摇卦，两卦不同只会让她
   * 对着纠结。检出后贴一条软提示，不拦（想看看就再看）。 */
  var _lyQ = (q || '').trim();
  var _sameQ = false;
  try {
    var _lpq = JSON.parse(sessionStorage.getItem('ly:lastq') || 'null');
    if (_lpq && _lpq.q === _lyQ && _lyQ && _lpq.d === todayIso()) {
      _sameQ = true;
    }
  } catch (eLQ) {}
  try {
    const j = await postJSON('/api/liuyao', body);
    if (_gen !== _LY_GEN) return;   /* R2502：新请求已接管——丢弃旧响应 */
    try {
      sessionStorage.setItem('ly:lastq',
        JSON.stringify({ d: todayIso(), q: _lyQ }));
    } catch (eLQ2) {}
    /* R3259（用户实测 bug）：「不论输入什么都是同样的回复」——时间起卦
     * 同一时辰（2 小时窗）内必出同一卦，连摇几次卡面一模一样，看起来
     * 像坏了。会话内比对本卦+变卦+动爻签名，完全相同就在卡首说破：
     * 不是卡住，是起卦法的确定性，并给出换卦面的两条路。 */
    var _guaSig = (j.method || '') + '|' +
      ((j.ben || {}).gua_name || '') + '|' +
      ((j.bian || {}).gua_name || '') + '|' +
      (((j.ben || {}).moving_lines) || []).join(',');
    var _sameCast = false, _prevSig = '';
    try {
      _prevSig = sessionStorage.getItem('ly:lastcast') || '';
      _sameCast = !!_prevSig && _prevSig === _guaSig;
      sessionStorage.setItem('ly:lastcast', _guaSig);
    } catch (eLC) {}
    var _lyPre = '';
    if (_sameCast) {
      _lyPre = '<p class="hit-cite">这一卦和你上次摇的<b>完全一样</b>——' +
        '不是卡住：' +
        (j.method === 'time'
          ? '时间起卦跟着日时走，同一个时辰（约两小时）里摇多少次' +
            '都是这一卦。想换个卦面：换「铜钱起卦」每次都不一样，' +
            '或过个时辰再来。'
          : '铜钱起卦填了固定编号，同编号必出同卦——' +
            '把编号清空再摇就是随机卦面。') + '</p>';
    } else if (_sameQ) {
      _lyPre = '<p class="hit-cite">同一问今天第二卦了，老话讲' +
        '「一事不二占」，这卦就当补充参考看，别拿两卦对着纠结。</p>';
    }
    paint('lyResult', _lyPre + buildLiuyaoResult(j));
    pollAiPolish('lyResult', j.ai_task_id);   /* R3154：AI 段落后到 */
    /* R198b（US5）+ R2512：分享按钮已挪进 build（重画不丢），
     * 绑定收进 rebind 登记——口吻切换后重放。 */
    var _rbLy = function () {
      on('shareLiuyao', function () { return downloadPoster(j, 'liuyao'); });
    };
    _rbLy();
    rememberResult('liuyao', j, val('ly_question') || '');   /* R219b（P0-2） */
    revealResult('lyResult');          // 005 判据 1 场景 5：不是只修排盘
  } catch (e) {
    if (_gen !== _LY_GEN) return;   /* R2502 */
    /* R230d（R16-P1-3）：与 bazi 同一条内联重试——此前只有 bazi 有。 */
    failWithRetry('lyResult', '摇卦失败：' + e.message, function () { doLiuyao(); });
  }
}

/* R3178：解梦——自由文本进、写死词库三件套出。
 * R3214 重构（审计+调研）：安抚/引入行先渲（吓醒的人先看到抱抱，
 * 不是先看到「鬼」卡）；象征卡五件套（老话/隐忧直答/回声/想想最近/
 * 细节分叉）；微行动独立锚块；AI 段嵌卡内；回显她的梦原文。 */
var _DM_GEN = 0;
/* R3253：梦境符号缩略图——每个象征卡头配一张同 IP 小熊图，
 * 「掉牙/被追/坠落」从抽象词变成一眼能认的画面；词表外或
 * 未覆盖的符号回落 dream-bear 月熊兜底，覆盖率仍是 100%。 */
var DREAM_ART = {
  '掉牙': 'dream-teeth', '被追赶': 'dream-chase', '坠落': 'dream-fall',
  '飞翔': 'dream-fly', '考试迟到/不会': 'dream-exam',
  '前任/旧人': 'dream-ex', '心动的人': 'dream-crush',
  '蛇': 'dream-snake', '水/大海/下雨': 'dream-water',
  '迷路/找不到路': 'dream-lost', '结婚/婚礼': 'dream-wedding',
  '猫': 'dream-cat',
  /* R3255 第一批：噩梦/情绪向——可爱化不吓人（鬼压床走
   * dream-frozen 被窝压影；去世的人走 dream-gone 望星）。 */
  '鬼/可怕的东西': 'dream-ghost', '动不了/喊不出': 'dream-frozen',
  '去世的人': 'dream-gone', '大哭/哭醒': 'dream-cry',
  '掉头发/秃了': 'dream-hair', '分手/被丢下': 'dream-breakup',
  '吵架/争执': 'dream-fight', '他出轨/被背叛': 'dream-cheat',
  '赶不上车/误点': 'dream-late', '被困/出不去': 'dream-trapped',
  '上班/被领导骂': 'dream-work', '手机丢了/联系不上': 'dream-phone',
  '已读不回/被拉黑': 'dream-ghosted', '捡钱/发财': 'dream-money',
  '着火/火灾': 'dream-fire',
  /* R3256 第二批：52 符全量专图覆盖；敏感题材一律可爱化
   * （血→创可贴熊、丧尸→抱枕城堡、亲人出事→抱全家福）。 */
  '在世的亲人出事': 'dream-family-scare',
  '自己出事/死了': 'dream-self', '家人朋友（在世的）': 'dream-family',
  '没穿衣服/出糗': 'dream-naked',
  '电梯/上不去下不来': 'dream-elevator',
  '怀孕/生孩子': 'dream-baby', '血/受伤': 'dream-blood',
  '狗': 'dream-dog', '老家/小时候的房子': 'dream-home',
  '同学/回到学校': 'dream-school', '吃东西/聚餐': 'dream-food',
  '镜子/照镜子': 'dream-mirror', '虫子/虫爬': 'dream-bugs',
  '找厕所/尿急': 'dream-toilet', '亲密/亲嘴': 'dream-kiss',
  '来月经/生理期': 'dream-period', '偶像/明星': 'dream-idol',
  '开车刹不住': 'dream-car', '剪头发/换发型': 'dream-haircut',
  '被偷/丢东西': 'dream-theft', '鱼/钓鱼': 'dream-fishing',
  '被孤立/被排挤': 'dream-alone', '丧尸/世界末日': 'dream-zombie',
  '梦中梦': 'dream-indream', '变丑/长痘/胖了': 'dream-looks'
};
function _dreamArt(name) {
  var f = DREAM_ART[name] || 'dream-bear';
  return '<img class="dm-sym-art" src="/static/cream/' + f +
    '.jpg" alt="" loading="lazy" decoding="async" onerror="this.remove()">';
}
function buildDreamResult(j) {
  var html = '<div class="card dream-card"><h2>🌙 梦翻翻</h2>';
  var syms = j.symbols || [];
  /* 回显她的梦（截 80 字）——长描述提交后能看见「我说的是这句」。 */
  var _qt = (j.echo || '').trim();
  if (_qt) {
    html += '<p class="dm-quote">你说：「' + esc(_qt.slice(0, 80)) +
      (_qt.length > 80 ? '…' : '') + '」</p>';
  }
  var rp = (j.warm && j.warm.reply) || [];
  /* reply 行三分：引导行（抱抱/翻了翻/反复梦）先渲；象征行/微行动/
   * 细节分叉已由卡块承载；免责与危机行放卡尾。 */
  var _symHead = {};
  syms.forEach(function (s) { _symHead['「' + s.name + '」'] = 1; });
  var _isSymLn = function (ln) {
    for (var _h in _symHead) { if (ln.indexOf(_h) === 0) return true; }
    return false;
  };
  var _actLn = j.action ? j.action + '。' : '';
  var _varSet = {};
  syms.forEach(function (s) {
    (s.varlines || []).forEach(function (v) { _varSet[v + '。'] = 1; });
  });
  var _isTail = function (ln) {
    return ln === _actLn || _varSet[ln] ||
      (j.disclaimer && ln === j.disclaimer) ||
      ln.indexOf('想想最近') === 0 ||
      ln.indexOf('另外多嘴一句') === 0;
  };
  var _intro = rp.filter(function (ln) { return !_isSymLn(ln) && !_isTail(ln); });
  var _tail = rp.filter(function (ln) {
    return (j.disclaimer && ln === j.disclaimer) ||
           ln.indexOf('另外多嘴一句') === 0;
  });
  /* R3222：解梦卡视觉重做——安抚行给浅底 banner 先接住情绪；
   * 象征卡按序上彩带+分节标签（册子注/先放心/想想最近/细节），
   * 不再是密文字墙。 */
  if (_intro.length) {
    html += '<div class="dm-intro">' +
      _intro.map(function (ln) { return '<p>' + esc(ln) + '</p>'; }).join('') +
      '</div>';
  }
  if (syms.length) {
    html += '<div class="dm-syms">';
    syms.forEach(function (s, _si) {
      var _c = colorAt(_si);
      html += '<div class="dm-sym" style="border-left:4px solid ' + _c + '">' +
        '<div class="dm-sym-head">' + _dreamArt(s.name) +
        '<span class="dm-sym-dot" style="background:' +
        _c + '"></span><span class="dm-sym-name">「' + esc(s.name) +
        '」</span></div><div class="dm-sym-trad">📖 ' +
        esc(s.trad) + '</div>' +
        (s.worry ? '<div class="dm-sym-worry"><span class="dm-sym-tag">先放心</span>' +
          esc(s.worry) + '</div>' : '') +
        '<div class="dm-sym-echo">' + esc(s.echo) + '</div>' +
        (s.ask ? '<div class="dm-sym-ask">💭 ' + esc(s.ask) + '</div>' : '') +
        (s.varlines || []).map(function (vl) {
          return '<div class="dm-sym-var">✎ ' + esc(vl) + '</div>';
        }).join('') +
        '</div>';
    });
    html += '</div>';
  }
  /* R3214：微行动独立锚块——唯一的可执行建议此前埋在 reply 平文里。 */
  if (j.action) {
    html += '<div class="dm-act"><span class="dm-act-tag">🌱 小动作</span>' +
      esc(j.action) + '</div>';
  }
  if (_tail.length) {
    html += '<div class="warm-reply dm-tail">' +
      _tail.map(function (ln) { return '<p>' + esc(ln) + '</p>'; }).join('') +
      '</div>';
  }
  html += renderAiPolish(j);   /* R3214：AI 段嵌卡内（此前落在卡外断节） */
  /* R3260（N3 延伸）：解梦×心情闭环——深夜解梦的多半心里有事，
   * 看完顺手一记（写回同一个 mood:<date>，与首页心情历同源）；
   * 今天已打过的显示已选态不重复问。 */
  {
    var _dmPk = '';
    /* R3314（R3310-P2）：解梦四钮是「梦后松没松」感受档，不是当天
     * 心情——同写 mood:<date> 会把她白天记的真心情顶掉。独立
     * mood:dream:<date> 键，心情历不受扰。 */
    try { _dmPk = localStorage.getItem('mood:dream:' + todayIso()) || ''; }
    catch (eMP) {}
    var _dmBtns = _MOOD_META.map(function (mm, i) {
      /* R3321-P2：选中态/回执补 aria-pressed + aria-live（同打卡卡）。 */
      return '<button type="button" class="mood-b dm-mood-b' +
        (_dmPk === String(i) ? ' on' : '') + '" data-m="' + i +
        '" aria-pressed="' + (_dmPk === String(i)) +
        '" aria-label="' + mm.t + '" title="' + mm.t + '">' +
        mm.e + '</button>';
    }).join('');
    html += '<div class="dm-mood" id="dmMoodRow">' +
      '<span class="mood-q">看完这个梦，心里松点了吗？</span>' +
      _dmBtns +
      '<span class="mood-ans" id="dmMoodAns" aria-live="polite" hidden></span></div>';
  }
  /* 分享图——梦境海报（主动分享才出图，文本本就她写的）
   * R3214：fav-btn 类补上——台账复看的隐藏规则只认这个类。 */
  /* R3222：fav-btn 默认 absolute 贴右上——压在渐变头上又挤又丑，
   * 解梦卡让它回文流落卡尾。台账复看的隐藏规则靠 fav-btn 类识别，
   * 类名不能丢。 */
  html += '<button type="button" class="ghost fav-btn" id="shareDream" ' +
    'style="position:static;margin-top:10px;">📷 生成梦卡图</button>' +
    '<button type="button" class="ghost fav-btn" id="dmSpeak" ' +
    'style="position:static;margin-top:6px;">🔊 读给小满听</button>';
  /* R3260（R9 延伸）：深夜解梦（多是噩梦/放不下的梦）卡尾多一颗
   * 创可贴钮——与聊天空态同源 bandaid 分享类型。 */
  var _hhDm = new Date().getHours();
  if (_hhDm >= 23 || _hhDm < 5) {
    html += '<button type="button" class="ghost fav-btn" ' +
      'id="dmBandaid" style="position:static;margin-top:6px;">' +
      '🌙 带张创可贴走</button>';
  }
  html += tailHook('dream');
  html += '</div>';
  return html;
}

async function doDream() {
  var _gen = ++_DM_GEN;
  var text = (val('dm_text') || '').trim();
  if (!text) {
    _failField('dm_text', 'dmResult',
      '跟我说说梦里最清楚的画面，一句话也行');
    return;
  }
  /* R3307（审-提示12）：危机/敏感词与聊天同口径本地先接住——
   * 「梦见我自杀了」不该出一张正常解梦卡。不重排台账/不加
   * rememberResult 足迹。 */
  if (feCrisis(text)) {
    paint('dmResult', '<div class="result-card"><div class="rc-body">' +
      esc(_CRISIS_FE_REPLY) + '</div></div>');
    revealResult('dmResult');
    return;
  }
  if (feSensitive(text)) {
    paint('dmResult', '<div class="result-card"><div class="rc-body">' +
      esc(_SENSITIVE_CHAT_REPLY) + '</div></div>');
    revealResult('dmResult');
    return;
  }
  busy('dmResult', '翻梦册中…');
  try {
    var j = await postJSON('/api/dream', { text: text });
    if (_gen !== _DM_GEN) return;
    paint('dmResult', buildDreamResult(j));
    pollAiPolish('dmResult', j.ai_task_id);
    var _rbDm = function () {
      /* R3260：心情行绑定收进 _rb 登记——行是 build 产的、
       * 绑定挂这里跟着重建。 */
      var _dmRow = document.getElementById('dmMoodRow');
      if (_dmRow && !_dmRow.dataset.bound) {
        _dmRow.dataset.bound = '1';
        _dmRow.addEventListener('click', function (ev) {
          var mb = ev.target.closest('.dm-mood-b');
          if (!mb) return;
          var mv = mb.dataset.m;
          try {
            localStorage.setItem('mood:dream:' + todayIso(), mv);
          } catch (eMS) {}
          _dmRow.querySelectorAll('.mood-b').forEach(function (x) {
            x.classList.toggle('on', x === mb);
            x.setAttribute('aria-pressed', x === mb ? 'true' : 'false');
          });
          var _ans = el('dmMoodAns');
          if (_ans) {
            _ans.textContent = ['记下了——累了就早点关灯，梦会替你收尾。',
              '记下了——平平淡淡也是安睡的理由。',
              '记下了——松了点就好，梦替你消化掉了。',
              '记下了——今晚带着它睡个好觉吧 🌙'][+mv] || '记下了。';
            _ans.hidden = false;
          }
          /* 心情历那边色点跟着亮（首页在 DOM 里，静默刷） */
          try { _renderMoodRow(); } catch (eMR) {}
        });
      }
      var _spDm = el('dmSpeak');
      if (_spDm && !_spDm.dataset.bound) {
        _spDm.dataset.bound = '1';
        _spDm.addEventListener('click', function () {
          /* R3264（R27）：语音扩展——解梦结果朗读（引导 + 微行动）。 */
          var _rp = ((j && j.warm && j.warm.reply) || []).slice(0, 3);
          var _txt = _rp.join(' ') + (j.action ? ' 小动作：' + j.action : '');
          if (_txt.trim()) _speak(_txt.trim());
        });
      }
      on('shareDream', function () {
        /* R3254g：解梦分享图嵌梦符熊——首个符号有自己的插画
         * 就预载直绘（离线/挂图回落 dream-bear 兜底）。 */
        var _sym0 = ((j.symbols || [])[0] || {}).name;
        var _key = DREAM_ART[_sym0] || 'dream-bear';
        var _im = new Image();
        _im.onload = function () { j._art = _im; j._artCap = _sym0 || '梦是回声'; downloadPoster(j, 'dream'); };
        _im.onerror = function () { downloadPoster(j, 'dream'); };
        _im.src = '/static/cream/' + _key + '.jpg';
      });
      /* R3260 R11：深夜创可贴钮绑定（重画幂等，on() 自带判重） */
      on('dmBandaid', function () {
        var _im2 = new Image();
        _im2.src = '/static/cream/bear-scene-bad.jpg';
        _im2.onload = function () {
          downloadPoster({ _art: _im2, _artCap: '今夜小夜灯' },
            'bandaid');
        };
        _im2.onerror = function () { downloadPoster({}, 'bandaid'); };
      });
    };
    _rbDm();
    rememberResult('dream', j, text);
    revealResult('dmResult');
  } catch (e) {
    if (_gen !== _DM_GEN) return;
    failWithRetry('dmResult', '解梦没翻成：' + e.message,
                  function () { doDream(); });
  }
}

var _QM_STYLE = 'classics';
var _QM_STYLES = {
  'classics': { label: '诗经草木', hint: '草木·鸟兽·日月' },
  'chuci':    { label: '楚辞',     hint: '香草·美人·远游' },
  'fresh':    { label: '清新灵动', hint: '轻盈·柔美·少女感' },
  'all':      { label: '综合',     hint: '全部候选池' }
};
/* D-004：换一批不重复——候选池 + 已显示集合，循环一轮后才重复 */
/* R230j（R22-P1-1）：chip 点击路径不在 on() 在途锁内，连点会发并发
 * POST /api/qiming——补一把同式在途锁。 */
var _qmBusy = false;
/* D-004-fix：换一批种子——每次换一批 +1，传入后端得到不同名字。
 * R224b（审查轨 R221a 连带发现）：初值原为 null，而 seed=null 在后端走的是
 * 「按性别打分排序取前 8」分支，**不在洗牌轮次体系内** → 首屏那批与
 * seed=1/2 各有 2-4 个重叠（实测 None∩1=4、None∩2=2，而 1∩2=0）。
 * 也就是说"连点两次换一批"里，第一次点出来的仍会撞首屏。
 * 改初值为 1：首屏就是轮次体系的第 1 批，后续 2、3… 段段互斥。
 * selftest 的 qiming.rebatch.distinct 也因此才真覆盖首屏场景。 */
var _qmSeed = 1;
/* D-004：用给定的名字数组重绘起名列表（不重新请求后端） */
var _qmPendStyle = null;   /* R3244：在途期记下最后点击的风格，落地补跑 */
function _qmSwitchStyle(style) {
  if (!_QM_STYLES[style]) return;
  /* R230j：chip 连点在途锁——但静默吞掉正是用户实测「不联动」
   * 的体感来源（点了没反应）。记最后一次意图，doQiming 落地后
   * 在 finally 里补跑（与 _ON_QUEUE 同模式）。 */
  if (_qmBusy) { _qmPendStyle = style; return; }
  _QM_STYLE = style;
  /* R3244（用户实测·砍换一批）：每次点击（含重选当前风格）都
   * 推进种子出新批——chip 即「换一批」，名单永远响应点击。 */
  _qmSeed = (_qmSeed || 0) + 1;
  /* R228d：不等 doQiming 重渲就先把 chip 态同步——点击与读屏反馈即时 */
  var root = el('qmResult');
  if (root) root.querySelectorAll('.qm-style-chip').forEach(function (c) {
    var on = c.dataset && c.dataset.style === style;
    c.classList.toggle('active', on);
    c.setAttribute('aria-pressed', String(on));
  });
  doQiming();
}
function _qmScore(name, missingArr) {
  /* v2 重写（用户反馈：评分清一色 80 分）。口径全部可解释：
   *   五行补缺 0/16/30（按命中缺失行数 0/1/2 档拉开）
   *   典籍出处 +5（双源 +8）
   *   寓意丰富 +0/+5/+9（story 长度三档）
   *   音形流畅 +3 / 含生僻字 -6
   *   形态 +3/+6（单/双字）、气质契合 +2~+9（后端性别序位）
   * 基础 46，区间约 46-98；维度间权重差异化后分数自然拉开。 */
  if (!name) return { total: 0, parts: [] };
  var parts = [];
  var els = (name.elements || []).map(String);
  var miss = (missingArr || []).map(String);
  var hit = 0;
  miss.forEach(function (m) { if (els.indexOf(m) !== -1) hit++; });
  var wx = hit === 0 ? 0 : (hit === 1 ? 16 : 30);
  if (wx) parts.push({ label: '五行补缺×' + hit, pts: wx });
  var formPts = name.form === 'double' ? 6 : 3;
  parts.push({ label: name.form === 'double' ? '双字名' : '单字名', pts: formPts });
  var origin = name.origin || '';
  var ogPts = origin.indexOf('+') !== -1 ? 8 : (origin ? 5 : 0);
  if (ogPts) parts.push({ label: '典籍出处', pts: ogPts });
  var sl = (name.story || '').length;
  var stPts = sl >= 40 ? 9 : (sl >= 18 ? 5 : 0);
  if (stPts) parts.push({ label: '寓意丰富', pts: stPts });
  var given = String(name.given || '');
  var heavy = 0;
  given.split('').forEach(function (ch) {
    if (ch.charCodeAt(0) > 0x9FFF) heavy++;   /* 生僻字惩罚 */
  });
  var flowPts = heavy ? -6 : 3;
  parts.push({ label: heavy ? '含生僻字' : '音形流畅', pts: flowPts });
  var genderPts = (name._rank !== undefined)
    ? Math.max(2, 9 - name._rank) : 5;
  parts.push({ label: '气质契合', pts: genderPts });
  var total = 46 + wx + formPts + ogPts + stPts + flowPts + genderPts;
  return { total: Math.max(40, Math.min(98, total)), parts: parts };
}
function _qmBadgeHtml(score, rank) {
  var badge = '';
  if (rank === 0) badge = '<span class="qm-badge qm-top1">⭐ 首选</span>';
  else if (rank === 1) badge = '<span class="qm-badge qm-top2">🌟 次选</span>';
  else if (rank === 2) badge = '<span class="qm-badge qm-top3">✨ 可选</span>';
  return '<span class="qm-score" title="契合度评分：缺补权重·音韵·出处完整">⭐ 契合度 ' +
    score + '</span>' + badge;
}

/* R3206：农历组打包——选了农历就把 ymd 搬进 keys 指定的 lunar_* 键
 *（bazi/taohua/qiming/birth 用 calendar_type+lunar_*；hehun 双侧
 * 用 a_/b_ 前缀键名）。 */
function _lunarPack(isLunar, keys, y, m, d, leap, body) {
  if (!isLunar) return;
  body[keys.cal] = 'lunar';
  body[keys.ly] = y; body[keys.lm] = m; body[keys.ld] = d;
  body[keys.leap] = leap;
}
var _LUNAR_KEYS_STD = { cal: 'calendar_type', ly: 'lunar_year',
                        lm: 'lunar_month', ld: 'lunar_day', leap: 'lunar_leap' };

async function doQiming() {
  if (_qmBusy) return;                        /* R230j */
  /* R233k（R45-§3）：预检前置——空字段/非法日此前要等一轮 422。 */
  if (!val('qm_surname')) { _failField('qm_surname', 'qmResult', '姓氏先填上哦'); return; }
  /* R3348（审-低-1）：姓氏字符集预检——「张3」「@王」此前发到后端
   * 才报错。百家姓范围一二级汉字 1–2 字（诸葛/欧阳等复姓在内）。 */
  if (!/^[一-鿿]{1,2}$/.test(val('qm_surname'))) {
    _failField('qm_surname', 'qmResult', '姓氏填一到两个汉字（复姓连着写）'); return;
  }
  if (num('qm_year') == null || num('qm_month') == null || num('qm_day') == null) {
    _failField(num('qm_year') == null ? 'qm_year'
      : (num('qm_month') == null ? 'qm_month' : 'qm_day'),
      'qmResult', '年月日先填上再算哦');
    return;
  }
  var _qmLunar = val('qm_cal') === 'lunar';
  /* R3206：农历日没有公历「某月没这天」问题（农历每月 29/30 天）——
   * 公历日检跳过，改查农历日 1-30 界；换算合法性归后端 lunar_to_solar。 */
  var _qb = _qmLunar ? null : _badYmdField('qm_year', 'qm_month', 'qm_day');
  if (_qb) {
    _failField(_qb, 'qmResult',
      '这一天不存在。' + num('qm_month') + ' 月没有 ' + num('qm_day') + ' 号');
    return;
  }
  if (_qmLunar && _badRange('qm_day', 1, 30)) {
    _failField('qm_day', 'qmResult', '农历的日填 1–30'); return;
  }
  /* R3348（审-中-2）：农历月界同桃花——13 月前端先拦。 */
  if (_qmLunar && _badRange('qm_month', 1, 12)) {
    _failField('qm_month', 'qmResult', '农历的月填 1–12'); return;
  }
  /* R2350e（R101-P2-1/2-2）：年份/时辰同界前端先拦，免一轮 422。 */
  if (_badRange('qm_year', 1900, 2100)) {
    _failField('qm_year', 'qmResult', '年份要在 1900–2100 之间'); return;
  }
  if (_badRange('qm_hour', 0, 23)) {
    _failField('qm_hour', 'qmResult', '时辰填 0–23，不知道就留空'); return;
  }
  _qmBusy = true;
  busy('qmResult', '起名中…');
  try {
    /* R2349s（R84-P1-12）：时辰留空 = 不详——补 12 并置标志位，
     * 后端回提示句；不再静默按预填值排。 */
    var _qmHour = val('qm_hour');
    const _qmBody = {
      surname: val('qm_surname'),
      year: num('qm_year'),
      month: num('qm_month'),
      day: num('qm_day'),
      hour: (_qmHour === '') ? 12 : num('qm_hour'),
      hour_known: _qmHour !== '',
      gender: val('qm_gender') || '女',
      /* R224b（审查轨 R221a 抓到）：原来这里发 top_n: 20，而「换一批」的
       * 互斥分段能力取决于 池长//top_n —— 池 30 字时 30//20 = 1 段，
       * 第 2/3 批必然回到同一段，实测前三批交集 13-14/20（等于原地打转）。
       * R220b-fix2 的「零重复」只在 top_n=8 成立，我当时没测真实前端值。
       * 降到 8：① 30//8 = 3 段，连点三次真零重复；② 一屏 8 个名字对目标
       * 用户刚好，20 个要滑很久且必然塞进生僻字（埙/鹜/苞 正是这么来的）。
       * 扩池到 40+/元素后可再上调，见台账未修清单。 */
      top_n: 8,
      seed: _qmSeed || null,
      /* R3340（审-P3）：排除字通道——表单「不想用的字」直通后端过滤。 */
      avoid_chars: val('qm_avoid') || '',
      style: _QM_STYLE || 'all'    /* v3（P3）：风格档后端过滤 */
    };
    _lunarPack(_qmLunar, _LUNAR_KEYS_STD, num('qm_year'), num('qm_month'),
               num('qm_day'), checked('qm_leap'), _qmBody);
    const j = await postJSON('/api/qiming', _qmBody);
    /* R2350f（R102-P1-5）：结果回显用了哪个生日（示例值外溢防错盘传播）。 */
    _LAST_BIRTH.qiming = num('qm_year') + '-' + num('qm_month') +
      '-' + num('qm_day');
    /* R3242d（实测链路缺口）：点评在途时换一批/换风格——paint 重建
     * nameReviewOut 后在途轮询把**上一批**的点评写进新名单容器
     * （旧点评挂新名）。落新批次前 bump 代际，在途轮询就地弃。 */
    _NR_GEN++;
    paint('qmResult', buildQimingResult(j));
    /* R2512：点评/分享/换一批三个直绑收进 rebind——口吻切换重画后
     * 重放；.qm-style-chip 是持久根委托不受影响。 */
    var _rbQm = function () {
      on('nameReviewBtn', function () {
      const btn = el('nameReviewBtn');
      if (btn) btn.disabled = true;
      const names = (j.full_names || []).map(function (n) {
        return n.full_name || '';
      }).filter(Boolean).slice(0, 6);
      _NR_GEN++;   /* R230v（R34-#2）：开新一轮点评，旧轮询就地弃 */
      postJSON('/api/qiming/review', {
        names: names,
        facts: ['五行缺' + ((j.five_elements && j.five_elements.missing || []).join('、') || '无') +
          (((j.five_elements || {}).weak || []).length ? '，偏弱：' + j.five_elements.weak.join('、') : '')]
      }).then(function (rj) {
        /* R3244（用户实测·保底）：先渲确定性「典故先读」卡——名单
         * 自带出处/引文/五行补缺，无 AI 也有真东西看；AI 故事版到
         * 了追加在 #nrAiOut。 */
        var _det = _nrDeterministic(j);
        if (!rj.review_task_id) {
          /* R216b 续5（U-019）：降级文案带人设+替代引导；按钮保持置灰。 */
          paint('nameReviewOut', _det +
            '<div class="no-evidence">故事版今天休息～上面的典故卡先看着，' +
            '回头来听 AI 讲 ✨</div>');
          const o = el('nameReviewOut'); if (o) o.hidden = false;
          if (btn) btn.disabled = false;
          return;
        }
        const out = el('nameReviewOut');
        if (out) {
          out.hidden = false;
          out.innerHTML = _det + '<div class="nr-ai" id="nrAiOut">' +
            '<div class="no-evidence">AI 正在翻书找典故…</div></div>';
        }
        pollNameReview(rj.review_task_id);
      }).catch(function () {
        /* R2400（R124-P2-4）：起典请求本身失败此前只解禁按钮、
         * 结果区零文案——补行内交代，不然像没点到。
         * R3243：换成可点的重试键。 */
        const o0 = el('nameReviewOut');
        if (o0) {
          /* R3244：先铺典故底卡，重试键进 nrAiOut 槽（点了重渲整块）。 */
          o0.innerHTML = _nrDeterministic(j) +
            '<div class="nr-ai" id="nrAiOut"></div>';
          _nrRetryable(el('nrAiOut'), '点评这趟没跑起来～');
        }
        if (btn) btn.disabled = false;
        });
      });
      on('shareQiming', function () { return downloadPoster(j, 'qiming'); });   /* R198b 通用模板 */
      /* R3244：qmRefreshBtn 已删——换批语义并入风格 chip
       * （_qmSwitchStyle 每次点击 _qmSeed++）。 */
    };
    _rbQm();
    _qmFavsRender();   /* R230z（R36-P2-3）：心水名单行+♡点亮 */
    rememberResult('qiming', j, '', { gender: val('qm_gender') });   /* v2：补性别（用户反馈 bug F3） */
    revealResult('qmResult');
    pollAiPolish('qmResult', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    /* R218a-04：风格芯片 + 换一批按钮的事件绑定。芯片是动态渲染的，
     * 用委托绑到 qmResult 上——避免每次切换重绑漏点。
     * R230j（R22-P1-1）：#qmResult 是静态持久容器，paint() 只换
     * innerHTML——原来这段委托在 doQiming 成功路径里，每提交一次
     * +1 个监听，chip 点击请求数随提交数翻倍（实测第5次48并发）。
     * 改一次性幂等绑定。 */
    const _qmRoot = el('qmResult');
    if (_qmRoot && !_qmRoot.dataset.qmbound) {
      _qmRoot.dataset.qmbound = '1';
      _qmRoot.addEventListener('click', function (ev) {
        const t = ev.target.closest && ev.target.closest('.qm-style-chip');
        if (t && t.dataset && t.dataset.style) {
          _qmSwitchStyle(t.dataset.style);
        }
      });
    }
  } catch (e) {
    failWithRetry('qmResult', '起名失败：' + e.message, function () { doQiming(); });
  } finally {
    _qmBusy = false;                          /* R230j */
    /* R3244：在途期被暂存的最后一次风格点击——落地补跑，点击
     * 永远有响应（不再静默吞=用户不再感觉「不联动」）。 */
    if (_qmPendStyle) {
      var _ps = _qmPendStyle; _qmPendStyle = null;
      _qmSwitchStyle(_ps);
    }
  }
}
var _TH_GEN = 0;   /* R2502：桃花在途代际（同 _LY_GEN） */
async function doTaohua() {
  var _gen = ++_TH_GEN;
  /* R233k（R45-§3）：同批预检——空字段/非法日前端先拦。 */
  if (num('th_year') == null || num('th_month') == null || num('th_day') == null) {
    _failField(num('th_year') == null ? 'th_year'
      : (num('th_month') == null ? 'th_month' : 'th_day'),
      'thResult', '年月日先填上再算哦');
    return;
  }
  var _thLunar = val('th_cal') === 'lunar';
  var _tb = _thLunar ? null : _badYmdField('th_year', 'th_month', 'th_day');
  if (_tb) {
    _failField(_tb, 'thResult',
      '这一天不存在。' + num('th_month') + ' 月没有 ' + num('th_day') + ' 号');
    return;
  }
  if (_thLunar && _badRange('th_day', 1, 30)) {
    _failField('th_day', 'thResult', '农历的日填 1–30'); return;
  }
  /* R3348（审-中-2）：农历月只有 1–12——此前 13 月一路发到后端
   * 才报，与公历月界前端同口径先拦。 */
  if (_thLunar && _badRange('th_month', 1, 12)) {
    _failField('th_month', 'thResult', '农历的月填 1–12'); return;
  }
  /* R2350e（R101-P2-1/2-2）：同界预检。 */
  if (_badRange('th_year', 1900, 2100)) {
    _failField('th_year', 'thResult', '年份要在 1900–2100 之间'); return;
  }
  if (_badRange('th_hour', 0, 23)) {
    _failField('th_hour', 'thResult', '时辰填 0–23，不知道就留空'); return;
  }
  busy('thResult', '计算中…');
  try {
    /* R2349s（R84-P1-12）：时辰留空 = 不详。 */
    var _thHour = val('th_hour');
    var _thBody = {
      year: num('th_year'),
      month: num('th_month'),
      day: num('th_day'),
      hour: (_thHour === '') ? 12 : num('th_hour'),
      hour_known: _thHour !== '',
      gender: val('th_gender') || '女'
    };
    _lunarPack(_thLunar, _LUNAR_KEYS_STD, num('th_year'), num('th_month'),
               num('th_day'), checked('th_leap'), _thBody);
    const j = await postJSON('/api/taohua', _thBody);
    if (_gen !== _TH_GEN) return;   /* R2502 */
    /* R3239：桃花表单同走统一落档器——农历换算入档、公历清旧标注。 */
    if (!_fieldsUntouched(['th_year','th_month','th_day','th_hour',
                           'th_gender']))
      await _meSaveFromBirth('me', {
        lunar: _thLunar, y: num('th_year'), m: num('th_month'),
        d: num('th_day'), h: (_thHour === '') ? null : num('th_hour'),
        g: val('th_gender') || '女', leap: checked('th_leap') });
    _meFillAll();   /* R230y */
    _LAST_BIRTH.taohua = num('th_year') + '-' + num('th_month') +
      '-' + num('th_day') + (_thLunar ? '（农历）' : '');
    paint('thResult', buildTaohuaResult(j));
    var _rbTh = function () {
      on('shareTaohua', function () { return downloadPoster(j, 'taohua'); });
      on('shareSoulmate', function () { _smOpen(j); });   /* R3373 正缘画像 */
    };
    _rbTh();
    rememberResult('taohua', j, '', { gender: val('th_gender') });   /* v2：补性别 */
    revealResult('thResult');
    pollAiPolish('thResult', j.ai_task_id);   // R191b：AI 段落后到（B-014）
  } catch (e) {
    if (_gen !== _TH_GEN) return;   /* R2502 */
    failWithRetry('thResult', '测算失败：' + e.message, function () { doTaohua(); });
  }
}



/* ── v4 交接修复：上一轮恢复函数时丢失的常量块，自 v3 快照原样找回 ── */
/* R209b：已批准海报背景预加载（shared/ 目录，同源） */
var POSTER_BG = {
  /* R230r（R29-#6）：night 预加载后没有任何绘制方使用——白拉一张图，摘掉。
   * R230w：按视图分底图——塔罗/星座用夜紫云月、桃花/合婚用樱粉，
   * 其余（含 bazi 旧版式）仍暖杏。 */
  warm: new Image(), sakura: new Image(), lilac: new Image(),
  /* R2349d：薄荷山月新底图（Agnes 生成）——daily/huangli 高频分享
   * 视图换清新系，与暖杏/樱粉/夜紫/梦紫错开一层。 */
  /* R2349i：青瓷山水底（Agnes）——六爻卦象专用，取「山水有章」意。 */
  dream: new Image(), mint: new Image(), celadon: new Image()
};
/* R230x（P2-8）：海报角落小满吉祥物贴纸。 */
var POSTER_MASCOT = new Image();
/* R231c：视图中文标题提升到模块级——浮层标题与下载文件名同一口径。 */
/* R2349s（R86-P2-16）：标题与功能按钮/海报口径统一——liuyao 全站
 * 叫「六爻占卜」、hehun 叫「八字合婚」、daily 海报叫「今日签」。 */
var _POSTER_TITLES = {
  bazi: '今日命盘', liuyao: '六爻占卜', tarot: '塔罗指引',
  qiming: '五行起名', taohua: '桃花运势', hehun: '八字合婚',
  daily: '今日签', huangli: '今日宜忌', xingzuo: '星座日运',
  birth: '我的本命盘', checkin: '好运签', 'checkin-week': '本周签运', 'checkin-month': '本月签运',
  xzm: '星座速配', 'bazi-yearly': '年度运势', dream: '解梦',
  bandaid: '深夜创可贴', lucky: '今日护身符', weekly: '小满周报',
  renge: '五行人格', 'daily-wap': '开运壁纸', 'daily-ava': '开运头像',
  'daily-outfit': '今日穿搭', moodweek: '心情周记',
  /* R3373：正缘画像海报弹层标题/下载文件名。 */
  soulmate: '正缘画像',
  /* R3379：周记信海报弹层标题/下载文件名。 */
  weekletter: '小满的上周小记',
  /* R3381：默契挑战海报弹层标题/下载文件名。 */
  mochi: '默契挑战',
  /* R3388：每日一签海报弹层标题/下载文件名。 */
  qian: '每日一签',
  ansb: '答案之书',
  /* R3397：开运日历海报标题/文件名。 */
  hlcal: '开运日历',
  /* R3393：流年K线海报标题/文件名。 */
  'bazi-kline': '人生K线',
  /* R3351（审-P2）：年报弹层标题/下载文件名此前回落
   * 「命盘海报/分享图」。 */
  'year-wrap': '小满年报' };
var _POSTER_BG_BY_VIEW = { tarot: 'lilac', xingzuo: 'lilac', birth: 'lilac',
  taohua: 'sakura', hehun: 'sakura', qiming: 'dream', checkin: 'warm',
  'checkin-month': 'warm',
  /* R2349d：日签/黄历海报走薄荷山月——高频分享面多一层色系新鲜度。 */
  daily: 'mint', huangli: 'mint', liuyao: 'celadon', dream: 'dream',
  'daily-outfit': 'mint',
  bandaid: 'dream', lucky: 'warm', weekly: 'lilac',
  moodweek: 'dream',   /* 心情周记归紫云梦底——夜灯系贴「一周心事」 */
  /* R3373：正缘画像归樱粉——与桃花同色系，是桃花卡的延伸。 */
  soulmate: 'sakura',
  /* R3379：周记信归暖底——一封信的温度感。 */
  weekletter: 'warm',
  /* R3381：默契挑战归暖底——两只熊干杯的奶杏感。 */
  mochi: 'warm',
  /* R3388：每日一签归青瓷底——庙里签筒的竹青色。 */
  qian: 'celadon',
  ansb: 'warm',
  /* R3397：开运日历归薄荷山月——黄历同色系。 */
  hlcal: 'mint',
  /* R3393：人生K线归薄荷山月——走势图的清爽冷调。 */
  'bazi-kline': 'mint',
  'year-wrap': 'warm', /* R3351（审-P2）：年报归暖底——一年足迹的总结感 */
  renge: 'sakura' };   /* R3260 R9：夜灯紫夜系；R3304 人格归樱花粉 */
/* R2349l.8：分享文案按视图定制——通用「测你的同款」太冷，给每视图
 * 一句带钩子的邀请语（小红书转发口径）。 */
var _SHARE_TEXT = {
  hehun: '我和 TA 的合拍指数出炉了，测测你们的 →',
  /* R3319-P1：张数动态不可知（1 张/自点牌/10 张阵同享此句）——
   * 去张数取中性口径。 */
  tarot: '我今天抽的牌有点准，你也来抽 →',
  bazi: '我的命盘解读出来了，看看你的 →',
  daily: '我今天的日签领到了，看看你抽到什么签 →',
  /* R3319-P3：补第一人称钩子（「我晒出来的」接力感）。 */
  xingzuo: '我的今日星座运势出来了，看看你的 →',
  /* R3319-P3：起名面不只有娃——猫/笔名/小号都在用，别缩受众。 */
  qiming: '古籍里挑的名字有点美，试试你的 →',
  taohua: '我的今日桃花信号，你的呢 →',
  liuyao: '刚摇了一卦，卦象有点东西 →',
  /* R3319-P2：黄历文案不再写死「今天」——_shareText 里按
   * 卡面 shownDate 算日词。 */
  huangli: '宜忌帮你查好了 →',
  checkin: '我在小满攒好运签，一起吗 →',
  'checkin-week': '我这周的签运攒成图了，你的呢 →',
  'checkin-month': '我这个月的签运战报出炉了，你的呢 →',
  birth: '我的本命盘出来了，看看你的 →',
  dream: '我刚翻了个梦，册子说的挺准 →',
  xzm: '我们星座合拍指数出来了，你们的呢 →',
  bandaid: '睡不着的话，这张创可贴送你 →',
  lucky: '今日护身符领好了，接住这份运气 →',
  weekly: '我的一周小满周报出炉了，看看你的 →',
  /* R3304（审-P1）：年度运势分享链带专属钩子——此前走通用兜底。 */
  'bazi-yearly': '我的年度运势出炉了，看看你的 →',
  /* R3319-P2：开运壁纸分享不再落通用兜底。 */
  'daily-wap': '今日开运壁纸换好了，接住这份运气 →',
  'daily-ava': '今日开运头像换上了，接住这份运气 →',
  'daily-outfit': '今天的五行穿搭色抄作业，看看你的是什么 →',
  /* R3373：正缘画像——爆款钩子（可晒社交货币+接力晒图）。 */
  soulmate: '盘里推出来的 TA 长这样，你的呢 →',
  weekletter: '小满给我写了封上周小记，你的呢 →',
  /* R3381：默契挑战——成绩晒图钩子。 */
  mochi: '我们的默契分出炉了，敢不敢测你们的 →',
  /* R3388：每日一签——「求来的答案」接力晒。 */
  qian: '我今天的签抽到了，看看你的 →',
  /* R3394：答案之书——「翻到的一句话」接力晒。 */
  ansb: '我刚从答案之书翻到一句话，你也来翻一页 →',
  /* R3397：开运日历——「本月好日子我圈好了」接力晒。 */
  hlcal: '本月适合我的日子我圈好了，看看你的是哪几天 →',
  /* R3393：人生K线——「我的走势长这样」接力晒。 */
  'bazi-kline': '我的人生K线画出来了，看看你的走势 →',
  renge: '测出我的五行人格了，你是哪型 →'};
/* R3373s：海报视图 → 落地视图别名（分享/邀请深链用）——
 * 海报 kind 有的不是页面视图（soulmate 是桃花卡的画像件）。 */
var _SHARE_VIEW_ALIAS = { soulmate: 'taohua', weekletter: 'home',
  'bazi-kline': 'bazi', hlcal: 'huangli' };
function _shareText(view) {
  /* R3319-P2：黄历按卡面日期说日词（明天/那天），与海报标题同口径。 */
  if (view === 'huangli') {
    try {
      var _sd2 = (el('hlResult') || {}).dataset || {};
      if (_sd2.shownDate) {
        var _tt1 = new Date(); _tt1.setHours(0, 0, 0, 0);
        var _dw4 = _hlDayWord(Math.round(
          (new Date(_sd2.shownDate + 'T00:00:00') - _tt1) / 864e5));
        if (_dw4 !== '今天') {
          return _dw4 + '宜忌帮你查好了 → 小满的解忧铺 ';
        }
      }
    } catch (eST) {}
  }
  return (_SHARE_TEXT[view] || '来测测你的 →') + ' 小满的解忧铺 ';
}

/* R2350f（R102-P1-1）：分享链 seed 重放——接收方落地先看到分享者
 * 抽到的同一副牌/同一卦（seed 确定性），再邀她抽自己的。
 * 复用正式结果渲染器，零新接口、不写台账诉求由后端既有逻辑管。 */
async function _replaySharedDraw(ssd) {
  if (!ssd || typeof postJSON !== 'function') return;
  var _who = (typeof _shareByName === 'function' && _shareByName()) || 'TA';
  var _banner = function (t) {
    return '<div class="hl-csmsg" style="margin-bottom:8px">🎁 ' +
      esc(_who) + ' ' + esc(t) + '，下面换成你的问题，再抽你自己的～</div>';
  };
  var _post = function (path, payload) {
    return api(path, { method: 'POST', silent: true,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload) });
  };
  try {
    if (ssd.view === 'tarot') {
      /* R2354（R112-P1-2/3）：replay 忠实还原——自点链走 draw_picked
       * （cards 索引原样回传），牌阵链带 spread key，不然收方看到
       * 的是另一套牌/退化成随缘张数。cards 与 spread 同传时后端
       * 校验张数=阵位，对不上 → 请求被拒走 catch 静默回表单。 */
      var _payload = { seed: ssd.seed, client_date: todayIso(),
        record: false };
      if (ssd.cards) { _payload.cards = ssd.cards; }
      else { _payload.n = ssd.tn || 3; }
      if (ssd.spread) { _payload.spread = ssd.spread; }
      var _tj = await _post('/api/tarot', _payload);
      if (_tj && _tj.draws) {
        paint('trResult', _banner('抽到的牌') + buildTarotResult(_tj));
        /* R3155b：分享重放也出 AI 解读段——新请求带新 task_id，
         * 打开链接的人看到和发起者同款完整卡。 */
        pollAiPolish('trResult', _tj.ai_task_id);
        revealResult('trResult');
      }
    } else if (ssd.view === 'liuyao' && ssd.method === 'coins') {
      var _lj = await _post('/api/liuyao',
        { method: 'coins', seed: ssd.seed, client_date: todayIso(),
          record: false });
      if (_lj && _lj.ben) {
        paint('lyResult', _banner('摇到的卦') + buildLiuyaoResult(_lj));
        pollAiPolish('lyResult', _lj.ai_task_id);   /* R3155b */
        revealResult('lyResult');
      }
    }
  } catch (e) { /* 重放失败静默——表单还在，用户自己抽不受影响 */ }
}

/* R2350f（R102-P2-7）：塔罗页空态先亮「今日牌」——与首页日卡同一
 * seed（'tarot|'+今天 哈希单抽，确定性、不写台账）。只在结果区仍是
 * 出厂空态时注入；用户抽过自己的牌后不再覆盖。 */
function _tarotLandingCard() {
  var box = el('trResult');
  if (!box || !box.querySelector('.ph-empty')) return;
  var _seed = 0, _src = 'tarot|' + todayIso();
  for (var _i = 0; _i < _src.length; _i++) {
    _seed = (_seed * 31 + _src.charCodeAt(_i)) >>> 0;
  }
  api('/api/tarot/draw', { method: 'POST', silent: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ seed: _seed, n: 1, client_date: todayIso() }) })
    .then(function (tj) {
      var d = tj && tj.card;
      if (!d || !d.name) return;
      /* 用户已抽（ph-empty 被结果顶掉）就不覆盖。 */
      if (!box.querySelector('.ph-empty')) return;
      box.innerHTML = '<div class="ph-empty">' +
        '<div class="sign-card" style="text-align:left;margin-bottom:10px;">' +
        '🃏 今日牌：<strong>' + esc(d.name) + '</strong> · ' +
        (d.upright ? '正位' : '逆位') +
        /* R3319-P3：正逆位与关键词粘连、含义前空格冒号怪腔——
         * 顺读分隔。 */
        '<span> · ' + esc(d.upright ? (d.upright_kw || '') :
                                    (d.reversed_kw || '')) +
        (d.meaning ? '：' + esc(d.meaning) : '') + '</span></div>' +
        '想好要问的事，点「抽一张」，抽你自己的～</div>';
    })
    .catch(function () {});
}
/* R230y（R36-P2-4）：宜忌白话映射提升为模块级——卡面与分享海报同一口径 */
/* R39-P2-2：结果页统一「明天」收口——最后一屏指向明天而不是看完即走。 */
/* R233b（R40-A2/W3）：cross_ref 方向副键可视化——后端算了
 * today_direction（值宫倾向）× card/gua_direction（牌面/卦象倾向）
 * 却只拼进 message 一句，一致性判定（两个独立信号同不同调）是现成
 * 的说服力来源。这里做一致性小徽标：同调✓ / 一方中性~ / 相反✗。 */
function _dirLabel(d) {
  return { forward: '往前推', hold: '稳一稳', observe: '先看看',
           mixed: '各一半' }[d] || '';
}
function crossDirBadge(cr, key, name) {
  if (!cr || !cr[key] || !cr.today_direction) return '';
  var a = cr[key], b = cr.today_direction;
  var rel = (a === b) ? '同调'
    : ((a === 'mixed' || b === 'observe') ? '并行' : '方向相反');
  var ic = rel === '同调' ? '✓' : (rel === '并行' ? '~' : '✗');
  return '<span class="cross-dir" title="' + esc(name) + '方向 × 今日' +
    esc(cr.today_sign || '') + '宫方向">' + esc(name) + '·' +
    esc(_dirLabel(a)) + ' × 今日·' + esc(_dirLabel(b)) + ' ' +
    ic + ' ' + esc(rel) + '</span>';
}

/* R233j（R46-P1）：尾钩升池——每视图 3 句按日轮换。hehun 无日期
 * 维度，「看别的日子」文不对题已修。 */
/* R2349g（R68-P1-1）：尾钩是每日必见收口位——每视图 3→6 句，60 天
 * 单句曝光从 ~20 次降到 ~10 次。 */
var _TAIL_HOOK = {
  bazi: ['🌙 明天的盘面会换，记得再来看看',
         '🌙 每天的盘都不一样，明天再来听听',
         '🌙 今天先到这，明天的盘面再约',
         '🌙 盘已收好，明天换个新盘等你',
         '🌙 你的盘我收着了，明天来翻新的',
         '🌙 今日份命盘到此，明天继续'],
  taohua: ['🌙 桃花每天都在动，明天再来看看',
           '🌙 缘分信号天天刷新，明天继续蹲',
           '🌙 桃花不等闲，明天再来看看动静',
           '🌙 桃花的风向天天变，明天再测',
           '🌙 心动雷达明天还开，记得来',
           '🌙 今天桃花先到这，明天接着看'],
  hehun: ['🌙 想换一对再测？随时来',
          '🌙 收好这份合拍报告，下次继续',
          '🌙 关系靠处不靠算：想复测随时来',
          '🌙 这页报告先存好，想再测随时来',
          '🌙 缘分常测常新，随时回来',
          '🌙 今天的合拍指数收好了，改天再战'],
  qiming: ['🌙 想要新的灵感，明天再来翻一翻',
           '🌙 名字库天天开，想到好字随时来',
           '🌙 换种风格又是一批，明天再来逛逛',
           '🌙 好名字不怕多翻几遍，明天继续',
           '🌙 灵感不打烊，明天再来一批',
           '🌙 名字慢慢挑，库一直开着'],
  liuyao: ['🌙 事情在变，明天可以再摇一卦',
           '🌙 卦随事转，有新问题再来摇',
           '🌙 一事一卦，明天有事再来',
           '🌙 卦筒收好，明天再开一局',
           '🌙 事有新动静就来摇一卦',
           '🌙 今天的卦先到这，明天再开'],
  tarot: ['🌙 明天牌面会换，记得再来看看',
          '🌙 牌面天天翻新，明天再抽一组',
          '🌙 今天的牌看完了，明天再来听听',
          '🌙 牌阵先收，明天再铺一局',
          '🌙 牌面日日新，明天再翻',
          '🌙 这组牌先收进兜，明天见'],
  huangli: ['🌙 日子不合适？明天再翻翻',
            '🌙 挑日子不用急，明天再来翻',
            '🌙 好日子在后头，明天继续翻',
            '🌙 黄历天天翻，好日子挑不完',
            '🌙 今天的历翻到这，明天再挑',
            '🌙 宜忌天天换，明天再来看看'],
  xingzuo: ['🌙 明天运势会换，记得来拆明天的礼物',
            '🌙 星座天天换班，明天再来看看',
            '🌙 明天的运势包裹已经在路上，记得来拆',
            '🌙 星象天天转，明天来听新的',
            '🌙 今天星语先听完，明天还有新的',
            '🌙 十二宫明天再排班，记得来'],
  dream: ['🌙 今晚睡个好觉，明晚的梦换个新的',
          '🌙 梦翻到这，睡饱比啥都强',
          '🌙 记住这个梦的话，明天再来看看',
          '🌙 今晚的床头，留给一个好梦',
          '🌙 梦说完了，安心睡吧',
          '🌙 新梦在路上，明天再来翻']
};
function tailHook(view) {
  var _p = _TAIL_HOOK[view];
  return (_p && _p.length) ?
    '<div class="tail-hook">' + esc(_dayPick(_p, 'tail|' + view)) + '</div>' : '';
}

/* R233v（R52-P2-7）：宜/忌白话注表按全词集（建除+星宿+神煞 42 词）
 * 覆盖——此前 29 个宜词只注了 19 个、忌词一半裸词落屏，还有 5 个
 * 永不出现的死键。selftest 有 MAP⊆词集 的钉扎，死键再生会被拦。 */
var _HL_YI_MAP = {
  /* R2349n（R77-P1-4）：白话失真修正——祭祀是拜一拜不是整理心情；
   * 嫁娶是领证结婚级大事；捕捉/出官/安葬/行丧/开仓不再硬掰。
   * 猎族三词拆开说，不再共享「主动出击争取」。 */
  '嫁娶': '领证结婚好日子', '开市': '开业 / 发新作品', '出行': '出门走走',
  '祭祀': '诚心拜一拜', '祈福': '许愿', '求嗣': '备孕', '上任': '入职接项目',
  '入学': '开学学新东西', '立券': '签合同', '纳财': '收款理财', '修造': '装修修缮',
  '动土': '开工', '平整': '整理归置', '安床': '布置房间',
  '冠笄': '形象焕新', '解除': '化解矛盾', '治病': '看病调理',   '捕捉': '收网，拖欠的事该了了', '安葬': '送行送别（白事）', '破土': '动工',
  /* R233v 新增（神煞层接线后这些词真的会出现了） */
  '塞穴': '堵漏洞补缺口', '栽种': '种花种树', '筑堤': '加固防守',
  '入宅': '搬进新家', '乘船': '水路出门', '出官': '办正事见对人',
  '归家': '回家看看', '求医疗病': '看病调理', '求名': '争取认可',
  '狩猎': '主动出击争取', '田猎': '该出手时出手', '畋猎': '争一争没坏处',
  '登山': '登高望远', '行丧': '白事送别，多点郑重', '谒贵': '拜访前辈贵人',
  '进人口': '添丁纳新', '远行': '长途出行', '移徙': '搬家挪窝',
  '破屋坏垣': '拆旧清理', '开仓': '动用储备', '诉讼': '有事说清',
  /* R2349n（R77）：除日宜词新增——沐浴洗个澡去去晦气。 */
  '沐浴': '洗个澡去去晦气',
  '求医': '看医生'
};
var _HL_JI_MAP = {
  '出行': '长途奔波容易累', '安葬': '不适合告别式', '祈福': '求个心安不必赶今天',
  '开市': '大动作先缓缓', '嫁娶': '感情大事另择日', '动土': '工地噪音惹人烦',
  '诉讼': '容易吵起来', '纳财': '破财风险高，钱包看紧点',
  '移徙': '搬家挪窝放一放',
  /* R233v 新增（忌侧全词集） */
  '求医': '看病另挑日子', '求医疗病': '看病另挑日子', '远行': '长途奔波先缓缓',
  '归家': '归途缓一缓', '谒贵': '拜访另约时间', '上任': '入职另择日',
  '入宅': '搬家另择日', '塞穴': '补漏的事改天', '筑堤': '加固改天',
  '开仓': '动用储备缓一缓', '出官': '求人办事另择日', '行丧': '送别另择日',
  '田猎': '出击缓一缓', '狩猎': '出击缓一缓', '畋猎': '出击缓一缓',
  '登山': '登高改天', '乘船': '水路缓一缓', '栽种': '种东西改天',
  '祭祀': '祭拜另择日', '求嗣': '备孕不赶今天',
  '求名': '争取的事缓一缓', '破土': '动工另择日', '破屋坏垣': '拆改另择日',
  '立券': '签约再看看', '入学': '开学事宜缓一缓', '冠笄': '焕新另择日',
  '解除': '化解另择日', '治病': '调理另择日', '捕捉': '收网缓一缓',
  '平整': '归置改天', '安床': '布置另择日', '修造': '修缮改天',
  '进人口': '添丁的事不急这一天', '开市': '开张另择日'
};
function _posterBgFor(view) {
  var k = _POSTER_BG_BY_VIEW[view] || 'warm';
  return POSTER_BG[k] || POSTER_BG.warm;
}
var TAROT_MANIFEST = null;      /* 惰性拉取，见 tarotImg() */

/* R3322-P1：manifest 单飞——此前只在首次进功能视图才拉，首页「今日牌」
 * 缩略图与「抽三张」首跳恒落空（牌面 0 图全 emoji 兑底）。收幂等
 * ensure，日卡渲染与抽牌路径各自可等它。 */
var _tarotMfP = null;
function _ensureTarotManifest() {
  if (TAROT_MANIFEST) return Promise.resolve(TAROT_MANIFEST);
  if (_tarotMfP) return _tarotMfP;
  var _preOpt = (typeof AbortSignal !== 'undefined' && AbortSignal.timeout)
    ? { signal: AbortSignal.timeout(API_TIMEOUT_MS) } : {};
  _tarotMfP = fetch('/static/tarot/manifest.json', _preOpt)
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { TAROT_MANIFEST = j || {}; return TAROT_MANIFEST; })
    .catch(function () { TAROT_MANIFEST = {}; return TAROT_MANIFEST; });
  return _tarotMfP;
}

/* R228k：原来顶层立刻拉三张图（~95KB）——海报背景只在点「存成图」才用，
 * manifest 只在塔罗视图才用。挪进 requestIdleCallback（无此 API 则
 * load 后 2s），首屏瀑布不再为低频路径买单。 */
var _didPrefetch = false;
function _idlePrefetch() {
  /* R2348（R67-P2）：原来首屏 idle 期就拉海报底图×4+mascot+tarot
   * manifest（~380KB）——低频功能让首访/弱网用户买单。改为首次进
   * 功能视图才触发（showView 调用点），用户没点卡就零开销。 */
  if (_didPrefetch) return;
  _didPrefetch = true;
  POSTER_BG.warm.src = '/static/shared/poster-bg-peach.jpg';
  POSTER_BG.sakura.src = '/static/shared/poster-bg-sakura.jpg';
  POSTER_BG.lilac.src = '/static/shared/poster-bg-lilac.jpg';
  /* R231b（R36-P3-1）：起名海报换紫云梦底——与塔罗夜紫错开一层。 */
  POSTER_BG.dream.src = '/static/shared/poster-bg-dream.jpg';
  POSTER_BG.mint.src = '/static/shared/poster-bg-mint.jpg';
  POSTER_BG.celadon.src = '/static/shared/poster-bg-celadon.jpg';
  POSTER_MASCOT.src = '/static/cream/poster-mascot.png';
  /* R230v（R34-#16）：预拉也带超时——死连接悬挂虽无可见影响，但会
   * 占住浏览器并发位。 */
  var _preOpt = (typeof AbortSignal !== 'undefined' && AbortSignal.timeout)
    ? { signal: AbortSignal.timeout(API_TIMEOUT_MS) } : {};
  _ensureTarotManifest();
}
/* 触发点挪进 showView：进任一功能视图（塔罗/排盘/起名都产海报）才拉。 */

var TAROT_ART = {
  "愚者": "🐕", "魔术师": "🪄", "女祭司": "🌙", "皇后": "🌹", "皇帝": "👑",
  "教皇": "🗝️", "恋人": "💞", "战车": "🛞", "力量": "🦁", "隐士": "🕯️",
  "命运之轮": "🎡", "正义": "⚖️", "倒吊人": "🙃", "死神": "🦋", "节制": "🏺",
  "恶魔": "⛓️", "高塔": "🗼", "星星": "⭐", "月亮": "🌜", "太阳": "☀️",
  "审判": "📯", "世界": "🌍"
};

function tarotImg(name) {
  if (TAROT_MANIFEST) {
    var f = TAROT_MANIFEST[name];
    return f ? '/static/tarot/' + f : null;
  }
  return null;
}


function tarotArt(name) {
  var suit = name.charAt(0);
  var sym = { "权": "🌿", "圣": "🏆", "宝": "🗡️", "星": "✨" }[suit];
  if (sym && name !== "星星") return sym;          /* 小阿卡纳：花色符号 */
  return TAROT_ART[name] || "✦";                    /* 大阿卡纳：主题意象 */
}


function tarotFace(d) {
  var img = tarotImg(d.name);
  /* R231b：逆位牌面倒置显示——与牌名/关键词的「逆位」标注一致。 */
  var _rev = d.upright ? '' : ' class="is-reversed"';
  /* R2345（R63-P1-2）：牌面图只走运行时缓存——装上即断网时 <img>
   * 挂掉此前只剩裂图；onerror 落回既有 emoji 意象（tarotArt）。 */
  var art = img
    ? '<div class="tart"><img src="' + esc(img) + '" alt="' + esc(d.name) + '"' + _rev +
      ' onerror="this.outerHTML=\'' + esc(tarotArt(d.name)) + '\'"></div>' +
      '<div class="tinfo">'
    : '<div class="tart">' + tarotArt(d.name) + '</div><div class="tinfo">';
  return art +
    '<div class="tname">' + esc(d.name) + '</div>' +
    '<div class="tmeaning">' + esc(d.upright ? '正位' : '逆位') + '<br>' +
    esc(d.upright ? d.upright_kw : d.reversed_kw) + '</div></div>';
}


function buildTarotResult(j) {
  let html = '<div class="card"><h2>✨ 塔罗占卜</h2>' + _festivalBand();
  /* R216b 续（U-006）：工程口吻复验说明人话化；seed 编号收进 title 悬停
   * 可见（专业用户仍可复验），不再平铺在正文。 */
  /* R2350b（R98-P2-12）：确定性承诺按输入对齐——填了问题才是
   * 「同一天问同一件事翻同几张」（seed=hash(question+date)）；
   * 没填问题 seed 每次随机（Date.now()），挂这句是空头支票。 */
  html += '<p class="hit-cite" title="复验编号 ' + esc(j.seed) + '">' +
    (_pStr(j.spread) ? '「' + esc(j.spread) + '」牌阵 · ' : '') +
    esc(j.n) + ' 张牌 · ' + (j.question
      ? '同一天问同一件事，翻到的就是这几张'
      : '随手一抽，牌面随缘') + '</p>';
  /* R218a-07：综合结论首屏 hook——三张牌翻完前用户先看到一句针对问题的
   * 直接回答，再下钻逐牌解读。j.question 是用户输入关键词。 */
  if (j.question) {
    html += tarotQuestionHook(j.question, j.draws || []);
  }
  /* R3257（牌阵阅读线）：位置此前只写在每张牌脚下——牌阵的
   * 「从左读到右/按位序读」这件事没有形。≥2 位时在网格上缘
   * 画一条带序号的阅读带，读牌顺序本身变成可视信息。 */
  var _trDraws = j.draws || [];
  var _trPosOk = _trDraws.length >= 2 &&
    _trDraws.every(function (d) { return !!(d && (d.position || '')); });
  if (_trPosOk) {
    html += '<div class="tr-flow" role="list" aria-label="牌阵阅读顺序">';
    _trDraws.forEach(function (d, i) {
      html += '<span class="tr-flow-chip" role="listitem"><b>' + (i + 1) +
        '</b>' + esc(d.position) + '</span>' +
        (i < _trDraws.length - 1 ? '<i class="tr-flow-sep">→</i>' : '');
    });
    html += '</div>';
  }
  html += '<div class="tarot-grid">';
  (j.draws || []).forEach(function (d, i) {
    html += '<div class="tarot-cell"><div class="tarot-card-wrap">' +
      '<div class="tarot-card-inner" data-card="' + i + '">' +
      '<div class="tarot-card-face tarot-card-back"><img class="tbimg" src="/static/tarot/card-back.jpg" alt="" onerror="this.outerHTML=\'🂠\'"></div>' +
      '<div class="tarot-card-face tarot-card-front">' + tarotFace(d) + '</div>' +
      '</div></div>' +
      '<div class="tarot-pos">' + esc(d.position || ('第' + (i + 1) + '张')) +
      '</div>' +
      /* R232a（R40-A4/W5）：牌义折叠——后端算了整段 meaning 从未露出，
       * 「这张牌到底什么意思」是塔罗最高频追问。确定性文案零成本。 */
      (d.meaning
        ? '<details class="tarot-meaning"><summary>牌义</summary>' +
          '<p>' + esc(d.meaning) + '</p></details>'
        : '') +
      '</div>';
  });
  html += '</div>';
  /* R207b：塔罗深读——多牌综合叙事 + 针对用户的具体指引。
   * 确定性模板层（同输入同输出），写死前端不动 voice 基线。 */
  html += tarotDeepRead(j.draws || [], j.question);
  /* R221b：交叉引用收口 7/7——塔罗不收生日，引今天值宫 × 牌面正逆同调 */
  if (j.cross_ref && j.cross_ref.message) {
    html += '<div class="cross-ref"><span class="cross-ref-icon">🔮</span>' +
      esc(j.cross_ref.message) +
      crossDirBadge(j.cross_ref, 'card_direction', '牌面') + '</div>';
  }
  html += renderVoice(j, '📖 牌面解读');
  /* R3154：塔罗接 AI 解读块——牌面坐标+综合口径行进 facts */
  html += renderAiPolish(j);
  html += tailHook('tarot');
  /* R2512：分享按钮挪进 build——同 liuyao，post-paint 手工挂的节点
   * 在口吻切换重画后消失。 */
  html += '<button class="ghost fav-btn" type="button" id="shareTarot" ' +
    'title="生成分享图" style="margin:10px 0 0">📸 分享图</button>';
  html += '</div>';
  return html;
}


/** R207b：塔罗深读模板族。三段式：连起来看 → 你该留意 → 现在可以做。
 *  全部由牌名/正逆位/位置组合生成，零新事实、零吉凶断言。 */
var TAROT_POS_HINT = {
  "过去": "它说的是你已经走过的路，现在的感受很多来自那段经历",
  "现在": "这是你此刻的状态，也是三张里最值得先看清的一张",
  "未来": "它指向事情的走向，但走向会随你的选择变化",
  "阻碍": "这张牌说的是挡在路上的东西，往往是心里的某个念头",
  "环境": "这是你周围的氛围和别人的态度，不全是你能控制的",
  "建议": "这张牌是牌阵给你的提醒，最值得记住的一张",
  "结果": "如果一切照旧，事情大概率是这样收场",
  /* R2349q（R81-P1-8）：5 张阵的「现状」、7 日阵的「第N日」、
   * 以及「助力」此前落兜底废话「这一步说的是X的位置」。 */
  "现状": "这是你此刻正站的位置：先看清楚脚下的这块",
  "助力": "这张牌是能借的力，顺着它比硬扛省力"
};

/* R218a-07：塔罗首屏问题绑定——5-6 套问题域关键词（感情/工作/学业/财运/健康/通用），
 * 按「主牌正逆位 + 关键词」给一句针对问题的直接回答。零新事实：同输入同输出。 */
var _TAROT_QK = [
  { cat: 'love',   kws: ['感情','恋爱','喜欢','分手','前任','对象','暗恋','表白','相亲','暧昧','桃花'] },
  { cat: 'work',   kws: ['工作','职场','同事','老板','上司','升职','跳槽','上班','加班','辞职','事业'] },
  { cat: 'study',  kws: ['学习','考试','作业','考研','高考','中考','成绩','课程','论文','答辩','读书'] },
  { cat: 'money',  kws: ['钱','工资','消费','理财','账单','余额','省钱','欠款','花呗','财运'] },
  { cat: 'health', kws: ['身体','健康','生病','睡眠','失眠','焦虑','压力','心情'] }
];
function _tarotClassify(question) {
  var s = String(question || '');
  for (var i = 0; i < _TAROT_QK.length; i++) {
    var kws = _TAROT_QK[i].kws;
    for (var j = 0; j < kws.length; j++) {
      if (s.indexOf(kws[j]) !== -1) return _TAROT_QK[i].cat;
    }
  }
  return 'general';
}


/* R2349q（R81-P0-1/P0-2）：塔罗前端重牌镜像——与后端 voice._TAROT_HEAVY
 * 逐字同源；抽到这些牌时 hook/深读收尾不说「整体是顺的」。 */
/* R2349t（R88-5）：亮牌池——重牌有安抚层，亮牌（太阳/世界/恋人/
 * 星星正位在场）也该有庆祝变体，好牌阵要有记忆点。 */
var _TAROT_SUNNY_FE = { '太阳': 1, '世界': 1, '恋人': 1, '星星': 1 };
var _TAROT_HEAVY_FE = { '死神': 1, '高塔': 1, '恶魔': 1, '月亮': 1,
  '宝剑3': 1, '宝剑9': 1, '宝剑10': 1 };
function _tarotHasHeavy(draws) {
  return (draws || []).some(function (d) {
    return d && _TAROT_HEAVY_FE[d.name];
  });
}
/* R3121（R3119 FE 侧同口径）：正位硬牌 kw0 镜像——权杖10「扛太满」
 * 这类正位即吃力的牌，hook 不能只按 upright 说「顺」（BE voice.
 * _TAROT_HARD_UP 同源）。判据走 kw0 与后端一致。 */
var _TAROT_HARD_FE = { '受困': 1, '忧惧': 1, '谷底': 1, '扛太满': 1,
  '带伤撑着': 1, '倦怠': 1, '失落': 1, '手头紧': 1, '取巧': 1,
  '冲突': 1, '内耗': 1, '受挫': 1 };
function _tarotHardCount(draws) {
  var n = 0;
  (draws || []).forEach(function (d) {
    if (!d || !d.upright) return;
    var kw0 = String(d.upright_kw || '').split('·')[0];
    if (_TAROT_HARD_FE[kw0]) n++;
  });
  return n;
}
/* R2349q（R81-P2-10）：牌面盐值确定性挑同义句——同组牌同一处位
 * 每次渲染同句，不同牌/不同位错开。 */
function _trVar(draws, arr, shift) {
  var s = 0;
  (draws || []).forEach(function (d) {
    var n = (d && d.name) || '';
    for (var i = 0; i < n.length; i++) s += n.charCodeAt(i);
  });
  return arr[(s + (shift || 0) * 7) % arr.length];
}

function tarotQuestionHook(question, draws) {
  /* R2349q（R81-P0-1）：生死/重病提问不走方向模板——转介文案。 */
  if (feSensitive(question)) {
    return '<div class="tarot-question-hook"><span class="tarot-hook-tag">针对「' +
      esc(String(question).slice(0, 18)) + '」</span><p>' +
      esc(_SENSITIVE_FE_LINE) + '</p></div>';
  }
  var cat = _tarotClassify(question);
  var main = (draws && draws.length) ? (draws[Math.min(1, draws.length - 1)] || draws[0]) : null;
  var upright = main && main.upright;
  /* R2349q（R81-P2-10）：「往前走一小步」同页三连复读——收口句按牌面
   * 盐值在三套同义写法里轮换；与深读收尾位用不同 shift 错开。 */
  var _loveUp = [
    '**整体是顺的**，你心里想的那个方向可以试着往前走一小步，缘分正在慢慢靠近。',
    '**整体在顺这边**，那个方向轻轻推一下就有回应，缘分在慢慢靠拢。',
    '**往顺的方向走**，心里想的路线可以试探着迈半步，缘分别急。'];
  var _genUp = [
    '**牌面整体是顺的**，你心里想的那个方向可以试着往前走一小步。',
    '**这组牌气色不错**，那个方向可以往前试半步。',
    '**顺位的牌占上风**，心里那事先迈半步试试水。'];
  var lines = {
    love: {
      true: _trVar(draws, _loveUp, 0),
      false: '**现在有点拧**：先别急着给关系下结论，等心里那股劲过去再决定。'
    },
    work: {
      true: '**事业方向是稳的**，保持当前节奏，机会在慢慢冒头，多留意主动递过来的信号。',
      false: '**职场的弯弯绕绕**，近期有调整的机会但建议先稳后动，别一次性求变。'
    },
    study: {
      true: '**学运在上升**：最近 2 周是黄金复盘期，把重点章节重过一遍。',
      false: '**脑子在打烊**：今晚先放一放，把最难的题留到明天状态好时再做。'
    },
    money: {
      true: '**财运有起色**：非必要支出再压一压，留意收入上的小动静。',
      false: '**钱的事先别想**，夜里做的预算都偏严，明天再看账本更清楚。'
    },
    health: {
      true: '**状态在回温**：继续保持作息和喝水节奏，会越来越轻快。',
      false: '**身体在喊停**：今天先放自己一马，好好睡一觉。身体的事，医生和检查结果最准～'
    },
    general: {
      true: _trVar(draws, _genUp, 1),
      false: '**牌面有些别扭**，先别急着推进，这几天多观察少动作。'
    }
  };
  /* R3121：主位牌本身是正位硬牌时不算「顺」——权杖10 扛太满
   * 压在主位上，顺字当头是错的（与阻碍位坎句同口径）。 */
  var _mkw = main && String(main.upright_kw || '').split('·')[0];
  var key = (upright && !_TAROT_HARD_FE[_mkw]) ? 'true' : 'false';
  var line = (lines[cat] && lines[cat][key]) || lines.general[key];
  /* R2349q（R81-P0-2）：hook 与 warm 收尾同口径——场上有重牌时
   * 主牌正位也改安抚变体，不然同页两句互搏。 */
  if (upright && _tarotHasHeavy(draws)) {
    line = '**牌里有几张在提醒你的位置**，先照顾好自己，' +
      '关于「' + String(question).slice(0, 18) + '」这事可以慢一点推进。';
  }
  /* R3121：正位硬牌同口径——≥2 张吃力正位时 hook 不再说「顺」，
   * 与 BE combined 的吃力分支同一句式（同页不互搏）。 */
  else if (upright && _tarotHardCount(draws) >= 2) {
    line = '**这组牌好几张都在使劲**，关于「' +
      String(question).slice(0, 18) +
      '」，先看你手上的事哪件能卸一卸。';
  }
  /* R228c：模板里的 **粗体** 要走 renderRichText——paint() 只 innerHTML，
   * 裸拼会把 ** 字面量裸露给用户（与 R227b 聊天路径同类漏网）。 */
  return '<div class="tarot-question-hook"><span class="tarot-hook-tag">针对「' +
    esc(String(question).slice(0, 18)) + '」</span><p>' + renderRichText(line) + '</p></div>';
}


/* R218a-08：六爻问题绑定——同 tarot 思路：6 套关键词 + 通用，按本卦方向
 * （动爻数 > 0 → 变化趋势，== 0 → 静卦稳定）给一句问题域回应。零新事实。 */
var _LIUYAO_QK = [
  { cat: 'work',   kws: ['工作','职场','同事','老板','上司','升职','跳槽','上班','加班','辞职','事业'] },
  { cat: 'love',   kws: ['感情','恋爱','喜欢','分手','前任','对象','暗恋','表白','相亲','暧昧','桃花','婚姻'] },
  { cat: 'study',  kws: ['学习','考试','作业','考研','高考','中考','成绩','课程','论文','答辩','读书'] },
  { cat: 'money',  kws: ['钱','工资','消费','理财','账单','余额','省钱','欠款','花呗','财运','投资'] },
  { cat: 'health', kws: ['身体','健康','生病','睡眠','失眠','焦虑','压力','心情'] }
];
function _liuyaoClassify(question) {
  var s = String(question || '');
  for (var i = 0; i < _LIUYAO_QK.length; i++) {
    var kws = _LIUYAO_QK[i].kws;
    for (var j = 0; j < kws.length; j++) {
      if (s.indexOf(kws[j]) !== -1) return _LIUYAO_QK[i].cat;
    }
  }
  return 'general';
}


/* R3092（specs/010-P3）：paipan 坐标行进 hook——用神/世应/动爻
 * 六亲此前全在响应里却只说分类通用句（盘点 agent Top-5）。
 * 用神口径：工作=官鬼、学习考试=父母、财=妻财、身体=官鬼+世、
 * 感情=世应两位、通用=世爻。 */
var _LY_YONG = {work: '官鬼', study: '父母', money: '妻财',
                health: '官鬼'};
var _LY_POS = {1: '初', 2: '二', 3: '三', 4: '四', 5: '五', 6: '上'};
function _liuyaoCoordLine(cat, paipan, moving) {
  var bg = (paipan || {}).ben_gua || {};
  var ls = bg.lines || [];
  if (!ls.length) return '';
  var mv = moving || (paipan || {}).moving_lines || [];
  var seg = [];
  if (cat === 'love' || cat === 'general') {
    /* 世=自己、应=对方/事情——两位坐标直接报，动了哪边说哪边。 */
    var shi = bg.shi, ying = bg.ying;
    if (shi && ying) {
      var s = '世爻在' + (_LY_POS[shi] || shi) + '爻（你这边）、应爻在' +
              (_LY_POS[ying] || ying) + '爻（对方那边）';
      if (mv.indexOf(shi) >= 0) s += '，世爻在动，你自己的心思正在变';
      else if (mv.indexOf(ying) >= 0) s += '，应爻在动，对方那边正在起变化';
      seg.push(s);
    }
  }
  var yong = _LY_YONG[cat];
  if (yong) {
    var hit = ls.filter(function (l) { return l.liuqin === yong; });
    if (!hit.length) {
      seg.push('用神「' + yong + '」没上卦：这事的根子不在明面上，别只看表面功夫');
    } else {
      var h = hit[0];
      var ps = (_LY_POS[h.position] || h.position) + '爻';
      seg.push(mv.indexOf(h.position) >= 0
        ? '用神「' + yong + '」落在' + ps + '还是动爻，关键点正在动的这一处'
        : '用神「' + yong + '」落在' + ps + '，关键点按住了没动，稳着来');
    }
  }
  /* 动爻六亲坐标：动的爻落在哪个生活域（六亲）比「有爻在动」具体一档。 */
  var others = ls.filter(function (l) {
    return l.moving && l.liuqin !== _LY_YONG[cat];
  });
  if (others.length) {
    var o = others[0];
    /* R3110：多动爻时「动的是X爻」单数读法误导（实测 3 动爻只报
     * 一爻）——报坐标带计数。 */
    seg.push((others.length > 1
              ? '另有 ' + others.length + ' 处在动，领头的是' : '动的是') +
             (_LY_POS[o.position] || o.position) + '爻（' + o.liuqin +
             '），变数落在这一处');
  }
  return seg.join('；');
}

function liuyaoQuestionHook(question, ben, bian, paipan) {
  /* R2349q（R81-P0-1）：生死/重病提问不走方向模板——转介文案。 */
  if (feSensitive(question)) {
    return '<div class="tarot-question-hook"><span class="tarot-hook-tag">针对「' +
      esc(String(question).slice(0, 18)) + '」</span><p>' +
      esc(_SENSITIVE_FE_LINE) + '</p></div>';
  }
  var cat = _liuyaoClassify(question);
  var moving = (ben && ben.moving_lines && ben.moving_lines.length) || 0;
  /* R2349q（R81-P0-3）：无动爻时变卦=本卦卦名仍在——旧判定
   * `!!bian.gua_name` 恒真，静卦被说成「有变数」。按卦名不同才算变。 */
  var changed = !!bian && !!bian.gua_name &&
    bian.gua_name !== (ben && ben.gua_name);
  /* R2349q（R81-P2-13）：每格单句太薄——同卦同问复读率肉眼可见。
   * 每格加第二变体，卦名+问题做盐确定性挑（同卦同问同句，可复验）。 */
  var _lys = String(ben && ben.gua_name || '') + '|' + question;
  var _lsalt = 0;
  for (var _li = 0; _li < _lys.length; _li++) _lsalt += _lys.charCodeAt(_li);
  var _lv = function (a, b) { return _lsalt % 2 ? (b || a) : a; };
  var lines = {
    work: {
      moving: _lv('**对应你问的工作**：近期有调整的机会，但建议先稳后动，动爻不在当位，基础打牢再考虑主动求变。',
        '**对应你问的工作**：卦里有动的地方，机会在冒头，但步子先别迈太大，底子稳了再求变。'),
      quiet: _lv('**对应你问的工作**：当下格局稳住（静卦），不急着推进，把手里这一摊做扎实比换赛道更划算。',
        '**对应你问的工作**：静卦，眼下这盘棋按住了走，深耕比换坑更值。'),
      changed: _lv('**对应你问的工作**：这件事有变数，先别求一步到位，分几步走更稳。',
        '**对应你问的工作**：变卦在转方向，这事不会一条道走到底，留一手后着更稳。')
    },
    love: {
      moving: _lv('**对应你问的感情**：心里有变化在酝酿，不急着表态，给情绪一段落地的空间。',
        '**对应你问的感情**：卦里有爻在动，那点心思正在长，先别催它落地。'),
      quiet: _lv('**对应你问的感情**：当下关系是稳的，珍惜眼前比追求新关系更值得。',
        '**对应你问的感情**：静卦，眼前这杯茶是温的，别为了新鲜感把它倒了。'),
      changed: _lv('**对应你问的感情**：这段关系到了一个转折点，变卦指向什么，你心里其实有数。',
        '**对应你问的感情**：卦在变，这段关系正拐个弯，往哪儿拐其实你心里有答案。')
    },
    study: {
      moving: _lv('**对应你问的学习**：方法有调整空间，动爻提示换一种思路比死磕更管用。',
        '**对应你问的学习**：动爻在提醒，换个学法试试，同一条路死磕不如绕半步。'),
      quiet: _lv('**对应你问的学习**：节奏是稳的，继续按计划走，重点章节再过一遍。',
        '**对应你问的学习**：静卦稳住，照计划推进就行，难的章节趁这波再过一轮。'),
      changed: _lv('**对应你问的学习**：会换一种考法/题型/方向，保持弹性，别押宝单一路径。',
        '**对应你问的学习**：变卦提醒方向会换，别把宝押在一道题上，铺开点复习。')
    },
    money: {
      moving: _lv('**对应你问的财运**：有一笔进/出在酝酿，动爻提醒你预算要留余量。',
        '**对应你问的财运**：动爻在钱包这边晃，一笔进出在路上，手头留点余量。'),
      quiet: _lv('**对应你问的财运**：收支平衡，按现有计划存就好，别追新机会。',
        '**对应你问的财运**：静卦，账面平稳，按原计划走，别眼热新花样。'),
      changed: _lv('**对应你问的财运**：账本会有一笔变化，先别做大决定，等落地再算。',
        '**对应你问的财运**：钱这事在转，变卦说方向要变，大额决定先按住。')
    },
    health: {
      moving: _lv('**对应你问的身体**：作息该调整了，动爻提示睡眠或饮食有一个可以改善的点。',
        '**对应你问的身体**：动爻落在作息上，睡和吃这两头，有一头可以拾掇拾掇。'),
      quiet: _lv('**对应你问的身体**：状态稳，保持作息就好，别熬夜别贪凉，拿不准就去查个明白。',
        '**对应你问的身体**：静卦安稳，照现在的节奏养，真不放心就去查清楚。'),
      changed: _lv('**对应你问的身体**：会有小波动，先把睡眠和心情稳住。',
        '**对应你问的身体**：卦在动，身体这两天有点小起伏，先把觉睡够。')
    },
    general: {
      moving: _lv('**对应你问的事**：变化在酝酿，先别急，给趋势一段落地的空间。',
        '**对应你问的事**：卦里有爻在动，势头在攒，先别催结果。'),
      quiet: _lv('**对应你问的事**：当下是稳的，按现有节奏走最划算。',
        '**对应你问的事**：静卦，这盘棋稳着走就好，别为了变而变。'),
      changed: _lv('**对应你问的事**：这件事有变数，分几步走比一步到位更稳。',
        '**对应你问的事**：变卦在转，这事不会一条路走到底，拆小步更稳。')
    }
  };
  var key = moving ? 'moving' : (changed ? 'changed' : 'quiet');
  var line = (lines[cat] && lines[cat][key]) || lines.general[key];
  var _coord = _liuyaoCoordLine(cat, paipan,
                              (ben && ben.moving_lines) || []);
  return '<div class="tarot-question-hook"><span class="tarot-hook-tag">针对「' +
    esc(String(question).slice(0, 18)) + '」</span><p>' + renderRichText(line) +
    '</p>' + (_coord ? '<p class="ly-coord">' + esc(_coord) + '</p>' : '') +
    '</div>';
}


function tarotDeepRead(draws, question) {
  if (!draws || !draws.length) return '';
  var q = (question || '').trim();
  var html = '<div class="tarot-deep">';
  // 第一段：把牌串成一个故事开头
  var names = draws.map(function (d) {
    return d.name + '（' + (d.upright ? '正位' : '逆位') + '）';
  });
  html += '<h4>🔮 这几句话想对你说</h4>';
  if (q) {
    html += '<p>你问「' + esc(q) + '」。' +
      esc(names.join('、')) + ' ： 把它们连起来，其实是这样一个过程：</p>';
  } else {
    html += '<p>' + esc(names.join('、')) + '。把它们连起来看：</p>';
  }
  // 第二段：逐位置含义（有 position 提示的用专属句，没有的按序说）。
  // R216b 续5（U-020）：≥6 张时逐牌解读收进默认折叠——10 张纯文本流
  // 在 390px 下页面失控（实测 5753px）。首尾两段常显保住叙事。
  var _items = '';
  draws.forEach(function (d, i) {
    var pos = d.position || '';
    var kw = (d.upright ? d.upright_kw : d.reversed_kw) || '';
    /* R2349q（R81-P1-8）：「第N日」按日序给白话；其余未知位置名
     * 不再复读「这一步说的是X的位置」废话。 */
    var hint = TAROT_POS_HINT[pos] ||
      (/^第\d+日$/.test(pos)
        ? '这一天的牌单独跟你说，记下这个提醒' :
        '这张牌落在「' + pos + '」的位置上');
    _items += '<li><strong>' + esc(pos || ('第' + (i + 1) + '张') + '·' +
      d.name) + '</strong>：' + esc(kw.split('·')[0]) + '。' +
      esc(hint) + '。</li>';
  });
  if (draws.length >= 6) {
    html += '<details class="warm-basis"><summary>每张牌的详细解读（' +
      draws.length + ' 张，展开慢慢看）</summary><ul>' + _items + '</ul></details>';
  } else {
    html += '<ul>' + _items + '</ul>';
  }
  /* R3255（文案骨架·串写）：2–5 张牌时补一段「连起来看」叙事——
   * 牌位串成一条线（过去→现在→往后），逐牌碎片收成一句故事。 */
  if (draws.length >= 2 && draws.length <= 5) {
    var _flow = draws.map(function (d) {
      var pos = d.position || '';
      var kw = ((d.upright ? d.upright_kw : d.reversed_kw) || '')
        .split('·')[0];
      return '「' + pos + '」的' + d.name + '说' + kw;
    }).join('，');
    html += '<p>一路看下来：' + esc(_flow) +
      '——事情有它自己的节奏，你照着节奏来就行。</p>';
  }
  // 第三段：行动建议（按主牌正/逆位给方向感，不给断言）
  var main = draws[Math.min(1, draws.length - 1)] || draws[0];
  /* R2349q（R81-P0-2）：深读收尾与 warm 同口径——场上有重牌时
   * 主牌正位也不再「整体是顺的」（实测宝剑3在场收尾说顺）。 */
  var _heavy = _tarotHasHeavy(draws);
  var _advUp = [
    '牌面整体是顺的：你心里想的那个方向可以试着往前走一小步，不用一下子做很大的决定。',
    '这组牌气色不错：那个方向先迈半步试试，不用一次到位。',
    '牌往顺的方向倒：心里那条路线可以轻轻推一下，小步就好。'];
  var _advDn = [
    '牌面有些别扭：先别急着推进，这几天多观察少动作，等心里那股拧劲过去了再决定。',
    '这组牌在踩刹车：先稳一稳，多看几天再动，拧劲过了再定。',
    '牌面方向有点拧：这几天以看为主，手上的事先按住别推。'];
  /* R2349t（R88-5）：亮牌变体——场上有正位亮牌且无重牌时，
   * 收尾句升档成庆祝，顺带把好运气导向分享。 */
  var _sunny = !_heavy && draws.some(function (d) {
    return d && d.upright && _TAROT_SUNNY_FE[d.name];
  });
  html += '<p class="tarot-advice">' +
    (_heavy
      ? '牌里有几张在提醒你的位置，先照顾好自己，事情可以慢一点推进，不急这一天。'
      : _sunny
        ? _trVar(draws, [
            '这组牌很亮：难得的好阵，值得晒出去让闺蜜沾沾光 ✨',
            '牌面亮堂堂的：今天抽到的手气，可以拿去晒一晒。',
            '亮牌扎堆：这组牌的正面能量很足，分享出去不亏。'], 2)
        : _trVar(draws, main.upright ? _advUp : _advDn, 2)) +
    /* R222b（E-302 P0）：此处原有「牌只是镜子，怎么走还是你自己说了算。」
     * ——多一个「自己」躲过了禁用词 grep（审查轨渲染后扫 innerText 才抓到）。
     * 前半句刚给了具体建议（往前走一小步 / 先别急着推进），这句免责声明
     * 正好把建议抵消掉，属用户明令禁用的套话，整句删除不做替换。 */
    '</p>';
  html += '</div>';
  /* R230y（R36-P2-1）：同日同问 seed 固定——提示文案跟着结果走，
   * 口吻切换重渲时不丢。 */
  if (_trNoteDay) {
    html += '<p class="hit-cite">同一问题今天牌面不变，想再问就换个问题，或明天再来看看～</p>';
  }
  return html;
}


/* R230y（R36-P2-1）：一事一天一问——同一问题同一天派生同一 seed，
 * 连点不再出互相矛盾的牌面；换问题/隔天自然换牌。 */
var _trNoteDay = '';
/* R2349q（R81-P2-11）：本日已问过的问题集（sessionStorage），
 * 供同日重复问判「牌面不变」提示——跨天自动重置。 */
var _trAsked = null;
function _trAskedQs() {
  if (!_trAsked) {
    try {
      _trAsked = JSON.parse(sessionStorage.getItem('trAskedToday') || 'null') || null;
    } catch (e) { _trAsked = null; }
  }
  if (!_trAsked || _trAsked.d !== todayIso() || !Array.isArray(_trAsked.qs)) {
    _trAsked = { d: todayIso(), qs: [] };
  }
  return _trAsked;
}
/* R2350l：命名牌阵——前端只镜像「key→张数」，位置名以服务端为准。 */
var _TR_SPREAD_N = {time:3, mind:3, you_ta:3, diamond:4, choose:5,
                    week:7, star:7, celtic:10};
function _trSpread() { return val('tr_spread') || ''; }
function _trSpreadSync() {
  var f = el('tr_n_field');
  if (f) f.style.display = _trSpread() ? 'none' : '';
}
var _TR_GEN = 0;   /* R2502：塔罗在途代际（同 _LY_GEN）——trSubmit 的
                    * guardedCall 锁护不住 data-retry 与 trPickGo 第二入口 */
/* R2350k：cards 给了走「自己抽」——选定下标成牌；不给照旧。 */
async function doTarot(cards) {
  var _gen = ++_TR_GEN;
  /* R3322-P1：抽牌等 manifest——「抽三张」首跳此前牌面全 emoji
   * （manifest 未拉）。有界 1.5s，弱网不等死。 */
  await Promise.race([
    _ensureTarotManifest(),
    new Promise(function (r) { setTimeout(r, 1500); })
  ]);
  /* R2502：on() 的 handler 会吃到 click 事件实参——此前靠「MouseEvent
   * 恰好没有 .length」侥幸正确，带 length 的对象进来会把非数组灌进
   * body.cards 或让 .slice 抛 TypeError 卡死 loading。收编数组形。 */
  if (!Array.isArray(cards)) cards = null;
  busy('trResult', '抽牌中…');
  /* R216b 续（U-006）：Seed 字段收进高级折叠，留空=用户不关心复验，
   * 前端自动生成一个编号（仅用于「同牌可复验」说明，不影响体验）。 */
  const seedRaw = val('tr_seed');
  const q0 = val('tr_question');
  let seed;
  if (seedRaw === '' || seedRaw == null) {
    if (q0) {
      var _qh = 0, _qs = q0 + '|' + todayIso();
      for (var _qi = 0; _qi < _qs.length; _qi++) {
        _qh = (_qh * 31 + _qs.charCodeAt(_qi)) >>> 0;
      }
      seed = _qh % 1000000;
      /* R2349q（R81-P2-11）：「同一问题今天牌面不变」首次问就出是
       * 抢白——用户还没重抽就看到「再问不变」。改为只在本日
       * 重复同一问题时提示（此时牌面真没变，提示才有意义）。 */
      var _aq = _trAskedQs();
      _trNoteDay = (_aq.qs.indexOf(q0) >= 0) ? todayIso() : '';
      if (_aq.qs.indexOf(q0) < 0) {
        _aq.qs.push(q0);
        if (_aq.qs.length > 30) _aq.qs.shift();
        try { sessionStorage.setItem('trAskedToday', JSON.stringify(_aq)); }
        catch (e) {}
      }
    } else {
      seed = Date.now() % 1000000;
      _trNoteDay = '';
    }
  } else {
    seed = num('tr_seed');
    _trNoteDay = '';
  }
  const n = num('tr_n');
  const body = { n: n == null ? 3 : Math.min(Math.max(n, 1), 10) };
  /* R2350k：自点牌背——n 以点选张数为准，跳过张数钳位提示。 */
  var _picked = (cards && cards.length) ? cards.slice(0, 10) : null;
  var _sp = _trSpread();
  if (_sp) {
    body.spread = _sp;
    body.n = _TR_SPREAD_N[_sp] || body.n;   /* 牌阵定张数 */
  }
  if (_picked) {
    body.cards = _picked;
    if (!_sp) body.n = _picked.length;
  } else if (n != null && n !== body.n && !_sp) {
    /* R230d（R16-P2-5）：静默钳位会让用户以为抽了输入的张数——
     * 超界时吱一声（防呆提示，不阻断）。 */
    showToast('牌数最多 10 张，已按 ' + body.n + ' 张抽', 'info');
  }
  if (seed != null) body.seed = seed;
  const q = q0;
  if (q) body.question = q;
  body.client_date = todayIso();   /* R230m：今日值宫锚本地日 */
  try {
    // /api/tarot 支持多张牌阵（含 position）；/api/tarot/draw 只给单张。
    const j = await postJSON('/api/tarot', body);
    if (_gen !== _TR_GEN) return;   /* R2502 */
    paint('trResult', buildTarotResult(j));
    /* R3368：万圣夜限定抽的结果头顶插限定条（只认 trQH 路径，
     * 窗口期外入口本就藏着的）。 */
    if (window.__trHFest) {
      window.__trHFest = false;
      var _hf = document.createElement('div');
      _hf.className = 'tr-hfest-strip';
      _hf.textContent = '🎃 万圣夜限定 · 今晚问的，小满都替你保密';
      var _box0 = el('trResult');
      if (_box0) _box0.insertBefore(_hf, _box0.firstChild);
    }
    pollAiPolish('trResult', j.ai_task_id);   /* R3154：AI 段落后到 */
    /* R230d（R16-P2-2）+ R2512：分享按钮挪进 build（重画不丢），
     * 绑定收进 rebind 登记。 */
    var _rbTr = function () {
      on('shareTarot', function () { return downloadPoster(j, 'tarot'); });
    };
    _rbTr();
    rememberResult('tarot', j, q || '');   /* R219b（P0-2）：牌名+正逆位进第一句 */
    revealResult('trResult');
    var trCard = el('trResult');
    // 翻牌：逐张延迟触发（纯 CSS transform，prefers-reduced-motion 已在 CSS 里关）
    /* R230v（R34-#21）：按节点引用翻牌而非按 data-card 重查——窗口内
     * 重抽时旧 timer 翻到的是已摘下的旧节点，不再误翻新卡。 */
    var _trInners = trCard.parentNode
      ? trCard.parentNode.querySelectorAll('.tarot-card-inner') : [];
    (j.draws || []).forEach(function (_d, i) {
      var _inner = _trInners[i];
      setTimeout(function () {
        if (_inner) _inner.classList.add('flipped');
      }, 300 + i * 200);
    });
  } catch (e) {
    if (_gen !== _TR_GEN) return;   /* R2502 */
    failWithRetry('trResult', '抽牌失败：' + e.message, function () { doTarot(); });
  }
}

/* R2350k：自己抽——22 张牌背里点 n 张。牌背是 fresh shuffle 的
 * 0-77 下标子集，点选顺序即成局顺序（位置名按序给）。 */
var _trPickState = { idxs: [], picks: [], n: 3 };
function _trPickNeed() {
  var sp = _trSpread();
  if (sp && _TR_SPREAD_N[sp]) return _TR_SPREAD_N[sp];
  var n = num('tr_n');
  return (n == null) ? 3 : Math.min(Math.max(n, 1), 10);
}
function _trPickOpen() {
  var panel = el('trPickPanel'), fan = el('trPickFan'), btn = el('trPickBtn');
  if (!panel || !fan) return;
  if (panel.style.display === 'block') {
    panel.style.display = 'none';
    if (btn) btn.textContent = '🃏 自己抽一把';
    return;
  }
  panel.style.display = 'block';
  if (btn) btn.textContent = '🃏 收起牌扇';
  _trPickState.n = _trPickNeed();
  _trPickState.picks = [];
  /* fresh shuffle：取 78 里 22 个下标摆出——点的是位置不是牌名，
   * 熵不减（子集本身随机）。 */
  var pool = [];
  for (var i = 0; i < 78; i++) pool.push(i);
  for (var j = pool.length - 1; j > 0; j--) {
    var k = Math.floor(Math.random() * (j + 1));
    var t = pool[j]; pool[j] = pool[k]; pool[k] = t;
  }
  _trPickState.idxs = pool.slice(0, 22);
  fan.innerHTML = _trPickState.idxs.map(function (idx, i) {
    return '<button type="button" class="tr-back" data-i="' + i +
      '" aria-label="第 ' + (i + 1) + ' 张牌背" aria-pressed="false"></button>';
  }).join('');
  _trPickHint();
}
function _trPickHint() {
  var hint = el('trPickHint'), go = el('trPickGo');
  var need = _trPickState.n, got = _trPickState.picks.length;
  if (hint) {
    hint.textContent = got >= need
      ? ('齐啦。' + need + ' 张在手')
      : ('背面朝上的牌里点 ' + need + ' 张（已点 ' + got + '）');
  }
  if (go) go.disabled = got < need;
}
function _trPickTap(i) {
  var st = _trPickState;
  var idx = st.idxs[i];
  if (idx == null) return;
  var at = st.picks.indexOf(idx);
  if (at >= 0) { st.picks.splice(at, 1); }
  else if (st.picks.length >= st.n) {
    showToast('够 ' + st.n + ' 张啦，先点开一张不要的', 'info');
    return;
  }
  else { st.picks.push(idx); }
  var btn = document.querySelector('#trPickFan .tr-back[data-i="' + i + '"]');
  if (btn) {
    var on = st.picks.indexOf(idx) >= 0;
    btn.classList.toggle('on', on);
    btn.setAttribute('aria-pressed', String(on));
  }
  _trPickHint();
}
function _trPickGo() {
  var st = _trPickState;
  if (st.picks.length < st.n) return;
  var panel = el('trPickPanel'), btn = el('trPickBtn');
  if (panel) panel.style.display = 'none';
  if (btn) btn.textContent = '🃏 自己抽一把';
  /* R2502：return 给 guardedCall——锁覆盖整个在途期，不再微任务后即放。 */
  return doTarot(st.picks);
}
/* R2354（R112-P1-1）：换阵/换张数时牌扇还开着 → 已选列表滞留
 * 旧 need，跨配置静默提交（celtic 顶 3 张选牌、要 7 发出 3）。
 * 面板开着时把 picks 清空+need 重算并明说「牌得重抽」。 */
function _trPickInvalidate(msg) {
  var panel = el('trPickPanel');
  if (!panel || panel.style.display !== 'block') return;
  var need = _trPickNeed();
  if (!_trPickState.picks.length && need === _trPickState.n) return;
  _trPickState.n = need;
  _trPickState.picks = [];
  var fan = el('trPickFan');
  if (fan) fan.querySelectorAll('.tr-back.on').forEach(function (b) {
    b.classList.remove('on');
    b.setAttribute('aria-pressed', 'false');
  });
  _trPickHint();
  if (msg) showToast(msg, 'info');
}


/* R3247：明星合盘——/static/celeb.json 内置公开生日库，点选把 TA 侧
 * 填成明星生辰，提交仍走原有 /api/hehun 链路。隐私/生命周期纪律：
 * ① 明星生辰不写 me/me:partner 档案、不进台账标题（请求里明星侧
 *    昵称置 null，台账名回落「我 × TA」）；
 * ② 用户手改明星侧任一字段（data-touched）或该侧字段被别的回填
 *    盖掉（值对不上所选）即退出明星态，恢复普通合婚口径——
 *    「除非用户主动改」之后的字段就是用户自己的数据，照常落档。 */
var _CELEBS = null;        /* 惰性加载的名单缓存（null=未拉过） */
var _CELEB_REQ = null;     /* 在途 fetch，防重复拉 */
var __hhCeleb = null;      /* 当前明星选择 {n,y,m,d,g,tag,note,side:'a'|'b'} */
var _CELEB_FIELDS = { a: 'hh_a_', b: 'hh_b_' };

function _celebLoad() {
  if (_CELEBS) return Promise.resolve(_CELEBS);
  if (_CELEB_REQ) return _CELEB_REQ;
  _CELEB_REQ = fetch('/static/celeb.json').then(function (r) {
    if (!r.ok) throw new Error('celeb.json ' + r.status);
    return r.json();
  }).then(function (list) {
    _CELEBS = (list || []).filter(function (c) {
      return c && c.n && c.y >= 1900 && c.y <= 2100 &&
             c.m >= 1 && c.m <= 12 && c.d >= 1 && c.d <= 31;
    });
    return _CELEBS;
  }).catch(function () { _CELEB_REQ = null; return []; });
  return _CELEB_REQ;
}

/* 明星侧字段是否仍等于所选：程序填充不动 data-touched，
 * 手改（真实事件置 touched）或值被 chip/档案代入盖掉都会出局。 */
function _celebOn(side) {
  var c = __hhCeleb;
  if (!c || c.side !== side) return false;
  var s = side === 'a' ? 'a' : 'b';
  var _fields = ['year', 'month', 'day', 'hour', 'gender', 'name',
                 'cal', 'leap'];
  for (var i = 0; i < _fields.length; i++) {
    var e = el('hh_' + s + '_' + _fields[i]);
    if (e && e.dataset && e.dataset.touched === '1') return false;
  }
  return num('hh_' + s + '_year') === c.y &&
         num('hh_' + s + '_month') === c.m &&
         num('hh_' + s + '_day') === c.d &&
         (val('hh_' + s + '_name') || '').trim() === c.n;
}

function _celebSync() {
  /* 明星侧已被动过/盖掉 → 清掉明星态，回落普通合婚口径。 */
  if (__hhCeleb && !_celebOn(__hhCeleb.side)) _celebClear();
}

function _celebPickedRender() {
  var pk = el('celebPicked');
  if (!pk) return;
  if (!__hhCeleb) { pk.hidden = true; pk.innerHTML = ''; return; }
  var c = __hhCeleb;
  pk.innerHTML = '已填好：<strong>' + esc(c.n) + '</strong>' +
    (c.tag ? '（' + esc(c.tag) + '）' : '') +
    ' <span class="cp-src">生日 ' + c.y + '年' + c.m + '月' + c.d +
    '日 · 公开资料</span>' +
    /* side='a'（受邀链落地）不给 ×——数据是链接带来的，想换就改字段。 */
    (c.side === 'b'
      ? '<button type="button" class="cp-x" id="celebUnpick" ' +
        'aria-label="取消明星选择" title="换回自己的 TA">×</button>' : '');
  pk.hidden = false;
}

function _celebClear(restore) {
  var c = __hhCeleb;
  if (!c) return;
  var s = c.side === 'a' ? 'a' : 'b';
  __hhCeleb = null;
  ['year', 'month', 'day', 'hour', 'gender', 'name', 'cal', 'leap'
  ].forEach(function (f) {
    var e = el('hh_' + s + '_' + f);
    if (!e || !e.dataset) return;
    delete e.dataset.celeb;
    /* 用户点 × 摘星：把明星填过的格子归位出厂态（手改字段
     * 走 _celebSync 清的，restore=false 不动值）。 */
    if (restore) {
      if (e.type === 'checkbox') e.checked = false;
      else if (e.tagName === 'SELECT') e.selectedIndex = 0;
      else e.value = e.defaultValue;
    }
  });
  if (restore) {
    var _fl = el('f_hh_' + s + '_leap');
    if (_fl) _fl.hidden = true;
  }
  var pk = el('celebPicked');
  if (pk) { pk.hidden = true; pk.innerHTML = ''; }
  document.querySelectorAll('#celebGrid .celeb-chip.on').forEach(
    function (x) { x.classList.remove('on'); });
}

/* 真实输入/改动事件落到明星侧 → 数据不再是公开资料原文，退出明星态
 * （程序 .value= 不触发事件，摘星/邀请落地预填不会误清）。 */
function _celebWatch(e) {
  var c = __hhCeleb;
  if (!c || !e.target || !e.target.id) return;
  if (e.target.id.indexOf(_CELEB_FIELDS[c.side]) === 0) _celebClear();
}
['input', 'change'].forEach(function (ev) {
  document.addEventListener(ev, _celebWatch, true);
});

function _celebRender(q) {
  var box = el('celebGrid');
  if (!box) return;
  var list = _CELEBS || [];
  var qq = (q || '').trim();
  if (qq) {
    list = list.filter(function (c) {
      return (String(c.n) + ' ' + String(c.tag || '') + ' ' +
              String(c.note || '')).indexOf(qq) !== -1;
    });
  }
  if (!list.length) {
    box.innerHTML = '<div class="ph-empty" style="padding:10px;">' +
      '没搜到，换个名字试试～</div>';
    return;
  }
  box.innerHTML = list.map(function (c) {
    var on = _celebOn('b') && __hhCeleb && __hhCeleb.n === c.n;
    return '<button type="button" class="celeb-chip' + (on ? ' on' : '') +
      '" role="option" aria-selected="' + (!!on) +
      '" data-celeb-n="' + esc(c.n) + '">' +
      '<span class="cl-n">' + esc(c.n) + '</span>' +
      '<span class="cl-t">' + esc(c.tag || '明星') + '</span>' +
      '<span class="cl-d">' + c.y + '-' + c.m + '-' + c.d + '</span>' +
      '</button>';
  }).join('');
}

function _celebPick(c) {
  _celebClear();
  __hhCeleb = { n: String(c.n), y: +c.y, m: +c.m, d: +c.d,
    g: (c.g === '男' || c.g === '女') ? c.g : '',
    tag: String(c.tag || ''), note: String(c.note || ''), side: 'b' };
  /* 程序填充：dataset.celeb 标来源（_meFill 档案回填免疫、
   * _fieldsUntouched 判「动过」由守卫另查——总之不落 TA 档案）。 */
  var _set = function (id, v) {
    var e = el(id);
    if (!e) return;
    e.value = v;
    delete e.dataset.me;
    delete e.dataset.touched;
    e.dataset.celeb = '1';
  };
  _set('hh_b_year', c.y); _set('hh_b_month', c.m); _set('hh_b_day', c.d);
  /* 明星时辰不公开——留空=「时辰未知」诚实盘（服务端按正午排并明示）。 */
  _set('hh_b_hour', '');
  if (__hhCeleb.g) _set('hh_b_gender', __hhCeleb.g);
  _set('hh_b_name', __hhCeleb.n);
  _set('hh_b_cal', 'solar');
  var _bl = el('hh_b_leap');
  if (_bl) { _bl.checked = false; _bl.dataset.celeb = '1'; }
  var _fl = el('f_hh_b_leap');
  if (_fl) _fl.hidden = true;
  _celebPickedRender();
  _celebRender(el('celebSearch') ? el('celebSearch').value : '');
  showToast('TA 侧已填好 ' + __hhCeleb.n +
    ' 的公开生日——点「合一下」看看合不合 ✨', 'ok');
}


var _HH_GEN = 0;   /* R2502：合婚在途代际（同 _LY_GEN） */
async function doHehun() {
  var _gen = ++_HH_GEN;
  _celebSync();   /* R3247：明星侧被手改/盖掉 → 先回落普通合婚口径 */
  /* R233k（R45-§3）：双侧预检——空字段/非法日前端先拦。
   * R2349（R65-P1-5）：邀请态下 A 侧=TA、B 侧=我——措辞随视角翻转。 */
  var _hs = window.__hhInviteMode
    ? [['hh_a_year','hh_a_month','hh_a_day','TA 的','hh_a_cal'],
       ['hh_b_year','hh_b_month','hh_b_day','你的','hh_b_cal']]
    : [['hh_a_year','hh_a_month','hh_a_day','你的','hh_a_cal'],
       ['hh_b_year','hh_b_month','hh_b_day','TA 的','hh_b_cal']];
  for (var _hi = 0; _hi < _hs.length; _hi++) {
    var _hp = _hs[_hi];
    if (num(_hp[0]) == null || num(_hp[1]) == null || num(_hp[2]) == null) {
      _failField(num(_hp[0]) == null ? _hp[0]
        : (num(_hp[1]) == null ? _hp[1] : _hp[2]),
        'hhResult', _hp[3] + '年月日先填上哦');
      return;
    }
    /* R3206：农历侧跳过公历日检（农历月 29/30 天），改界 1-30。 */
    var _hLun = val(_hp[4]) === 'lunar';
    var _hb = _hLun ? null : _badYmdField(_hp[0], _hp[1], _hp[2]);
    if (_hb) {
      _failField(_hb, 'hhResult',
        _hp[3] + '日期不存在。' + num(_hp[1]) + ' 月没有 ' + num(_hp[2]) + ' 号');
      return;
    }
    if (_hLun && _badRange(_hp[2], 1, 30)) {
      _failField(_hp[2], 'hhResult', _hp[3] + '农历的日填 1–30');
      return;
    }
    /* R3348（审-中-2）：农历月界双侧同拦（13 月此前漏到后端）。 */
    if (_hLun && _badRange(_hp[1], 1, 12)) {
      _failField(_hp[1], 'hhResult', _hp[3] + '农历的月填 1–12');
      return;
    }
    /* R2350e（R101-P2-1/2-2）：年份/时辰同界预检（双侧）。 */
    if (_badRange(_hp[0], 1900, 2100)) {
      _failField(_hp[0], 'hhResult', _hp[3] + '年份要在 1900–2100 之间');
      return;
    }
  }
  if (_badRange('hh_a_hour', 0, 23)) {
    _failField('hh_a_hour', 'hhResult', '时辰填 0–23，不知道就留空'); return;
  }
  if (_badRange('hh_b_hour', 0, 23)) {
    _failField('hh_b_hour', 'hhResult', '时辰填 0–23，不知道就留空'); return;
  }
  busy('hhResult', '计算中…');
  try {
    /* R2349s（R84-P1-12）：时辰留空 = 不详——补 12 并置标志位。 */
    var _hhAH = val('hh_a_hour'), _hhBH = val('hh_b_hour');
    var _hhBody = {
      a_year: num('hh_a_year'),
      a_month: num('hh_a_month'),
      a_day: num('hh_a_day'),
      a_hour: (_hhAH === '') ? 12 : num('hh_a_hour'),
      a_hour_known: _hhAH !== '',
      a_gender: val('hh_a_gender') || '女',
      b_year: num('hh_b_year'),
      b_month: num('hh_b_month'),
      b_day: num('hh_b_day'),
      b_hour: (_hhBH === '') ? 12 : num('hh_b_hour'),
      b_hour_known: _hhBH !== '',
      b_gender: val('hh_b_gender') || '女',
      /* R230z（R36-P1-2）：昵称（可空）——后端回显进结果/海报/历史
       * R3247：明星侧昵称置 null——台账标题回落「我 × TA」，
       * 明星选择不进账本；结果卡/海报仍用 j.*_name 注入显示。 */
      a_name: _celebOn('a') ? null : ((val('hh_a_name') || '').trim() || null),
      b_name: _celebOn('b') ? null : ((val('hh_b_name') || '').trim() || null),
      /* R3152：可空问句——服务端判词对着这句给定向行 */
      question: (val('hh_question') || '').trim() || null,
      /* R3313（审-P1-5）：邀请态下读盘的是 B 侧（受邀者）——
       * 服务端判词「我/TA」指称整体换向。 */
      reader_is_b: !!window.__hhInviteMode
    };
    /* R3206：双侧农历打包（hehun 键名是 a_/b_ 前缀组） */
    _lunarPack(val('hh_a_cal') === 'lunar',
      { cal: 'a_calendar', ly: 'a_lunar_year', lm: 'a_lunar_month',
        ld: 'a_lunar_day', leap: 'a_lunar_leap' },
      num('hh_a_year'), num('hh_a_month'), num('hh_a_day'),
      checked('hh_a_leap'), _hhBody);
    _lunarPack(val('hh_b_cal') === 'lunar',
      { cal: 'b_calendar', ly: 'b_lunar_year', lm: 'b_lunar_month',
        ld: 'b_lunar_day', leap: 'b_lunar_leap' },
      num('hh_b_year'), num('hh_b_month'), num('hh_b_day'),
      checked('hh_b_leap'), _hhBody);
    const j = await postJSON('/api/hehun', _hhBody);
    if (_gen !== _HH_GEN) return;   /* R2502：丢弃旧响应——含 _meSave 副作用 */
    /* R230z（R36-P1-2）：昵称前端注入响应——结果卡/海报共用 j 一处 */
    j.a_name = (val('hh_a_name') || '').trim() || null;
    j.b_name = (val('hh_b_name') || '').trim() || null;
    /* R3247：命中明星态 → 结果卡导语/公开资料标注/标题 */
    j.celeb = __hhCeleb;
    /* R230y：A=我，B=TA——两条 profile 分开存
     * R233n续：邀请链落地时视角相反——受邀者填的 B 才是「自己」，
     * A（发起人）落到 me:partner。手改过 A 侧则恢复默认。 */
    if (window.__hhInviteMode) {
      /* R2400（R130-P2-4）：受邀提交把发起人写进 me:partner——B 原来
       * 存着别的 TA 就被静默顶掉；存前先记一下，不同的才提示。 */
      var _oldP = null;
      try { _oldP = _meGet('me:partner'); } catch (eOP) {}
      /* R2500（R142-P1-3）：受邀侧字段照样守未动不写——B 侧邀请
       * 预填值 ≠ 出厂 defaultValue，手填/邀请值都会如实落档。 */
      /* R3161：昵称随档案落档（空不覆旧值——_meSave 语义里 '' 会清键）。 */
      /* R3239：合婚落档同走统一器——农历换算入档、公历清旧标注；
       * 昵称非空才动键（原 delete _recMe.n 语义保留）。 */
      var _optsMe = { lunar: val('hh_b_cal') === 'lunar',
        y: num('hh_b_year'), m: num('hh_b_month'), d: num('hh_b_day'),
        h: num('hh_b_hour'), g: val('hh_b_gender') || '女',
        leap: checked('hh_b_leap') };
      if (val('hh_b_name')) _optsMe.n = val('hh_b_name');
      if (!_fieldsUntouched(['hh_b_year','hh_b_month','hh_b_day',
                             'hh_b_hour','hh_b_gender']))
        await _meSaveFromBirth('me', _optsMe);
      var _optsPa = { lunar: val('hh_a_cal') === 'lunar',
        y: num('hh_a_year'), m: num('hh_a_month'), d: num('hh_a_day'),
        h: num('hh_a_hour'), g: val('hh_a_gender') || '女',
        leap: checked('hh_a_leap') };
      if (val('hh_a_name')) _optsPa.n = val('hh_a_name');
      /* R3247：A 侧是明星公开生日（_celebOn('a')）不落 TA 档案。 */
      if (!_celebOn('a') && !_fieldsUntouched(['hh_a_year','hh_a_month','hh_a_day',
                             'hh_a_hour','hh_a_gender']))
        await _meSaveFromBirth('me:partner', _optsPa);
      if (_oldP && (String(_oldP.y) !== String(num('hh_a_year')) ||
                    String(_oldP.m) !== String(num('hh_a_month')) ||
                    String(_oldP.d) !== String(num('hh_a_day')))) {
        try {
          showToast('顺带说下：你之前存的 TA 档案被这次邀请更新掉啦', 'info');
        } catch (eTP) {}
      }
    } else {
      var _optsMeA = { lunar: val('hh_a_cal') === 'lunar',
        y: num('hh_a_year'), m: num('hh_a_month'), d: num('hh_a_day'),
        h: num('hh_a_hour'), g: val('hh_a_gender') || '女',
        leap: checked('hh_a_leap') };
      if (val('hh_a_name')) _optsMeA.n = val('hh_a_name');
      if (!_fieldsUntouched(['hh_a_year','hh_a_month','hh_a_day',
                             'hh_a_hour','hh_a_gender']))
        await _meSaveFromBirth('me', _optsMeA);
      var _optsPaB = { lunar: val('hh_b_cal') === 'lunar',
        y: num('hh_b_year'), m: num('hh_b_month'), d: num('hh_b_day'),
        h: num('hh_b_hour'), g: val('hh_b_gender') || '女',
        leap: checked('hh_b_leap') };
      if (val('hh_b_name')) _optsPaB.n = val('hh_b_name');
      /* R3247：B 侧是明星公开生日（_celebOn('b')）不落 TA 档案。 */
      /* R3372-P2-4：受邀态下提交会把受邀者本机的对象档盖成
       * 发起人——me:partner 已有内容且生日不同先两段式确认，
       * 一闪而过的 toast 不算知情。 */
      if (!_celebOn('b') && !_fieldsUntouched(['hh_b_year','hh_b_month','hh_b_day',
                             'hh_b_hour','hh_b_gender'])) {
        var _pa0 = _meGet('me:partner');
        var _paDiff = !!(_pa0 &&
          (+_pa0.y !== +_optsPaB.y || +_pa0.m !== +_optsPaB.m ||
           +_pa0.d !== +_optsPaB.d));
        if (window.__hhInviteMode && _paDiff && !window.__hhPartnerArm) {
          window.__hhPartnerArm = true;
          showToast('会把你的对象档换成「' +
                    (_optsPaB.n || '这位') + '」——再点一次提交确认',
                    'warn');
          return;
        }
        window.__hhPartnerArm = false;
        await _meSaveFromBirth('me:partner', _optsPaB);
      }
    }
    _meFillAll();
    /* R2350f（R102-P1-5）：双侧生日都回显——邀请态下 A 侧是 TA。 */
    _LAST_BIRTH.hehun = (window.__hhInviteMode ? 'TA ' : '') +
      num('hh_a_year') + '-' + num('hh_a_month') + '-' + num('hh_a_day') +
      ' × ' + (window.__hhInviteMode ? '我 ' : '') +
      num('hh_b_year') + '-' + num('hh_b_month') + '-' + num('hh_b_day');
    paint('hhResult', buildHehunResult(j));
    /* R2512：分享/邀请/存这对三个直绑收进 rebind——口吻重画后重放。 */
    var _rbHh = function () {
      on('shareHehun', function () { return downloadPoster(j, 'hehun'); });   /* R218a-巡2（N-04） */
      /* R3332-低：受邀者结果页「发回给 TA」cite 按钮。
       * R3345（审-中）：原走分享图链路——回传实体只有海报图，
       * 发起人打开回链只见自己表单、受邀者的盘到不了手。改走
       * hhInvite 链路：受邀态下 _side='b' 编码受邀者自己的生辰，
       * 发起人点开即见对方填好的盘——一来一回真闭环。 */
      on('hhSendBack', function () {
        var _sb = el('hhInvite');
        if (_sb) _sb.click();
      });
      /* R233n（R47-Top5-1）：邀请链——把 A 侧生辰编进 ?view=hehun 参数，
       * 对方打开即预填+提示「轮到你了」。 */
      on('hhInvite', function () {
      try {
        /* R2350b（R99-P1）：邀请态下受邀者=B 侧——再点「喊 TA 来对盘」
         * 应该编码受邀者自己的盘（B 侧），否则把发起人的生辰明文
         * 代发出去，语义也反了。 */
        var _side = window.__hhInviteMode ? 'b'
          /* R3247：明星合盘要编的是 B 侧明星生辰——受邀者落地填自己的，
           * 进流程即「我和明星的合盘」。 */
          : (_celebOn('b') ? 'b' : 'a');
        /* R2364（R120-P2）：年都没填就生成邀请——对方收到空 ay 落回
         * 出厂默认生日，还以为填好了。先拦一步。 */
        if (!val('hh_' + _side + '_year')) {
          showToast('先填好你的出生年，再喊 TA 来对盘哦', 'warn');
          return;
        }
        /* R3307（审-中3）：生辰参数改挂 #hash——query 会进接收方浏览器
         * 历史/平台链接预览爬虫/Referer，hash 不出本机不上服务器。
         * 落地端从 location.hash 读同一组键（白名单合入 _qsAll）。 */
        var _u = location.origin + location.pathname + '?view=hehun&from=invite' +
          '#ay=' + encodeURIComponent(val('hh_' + _side + '_year') || '') +
          '&am=' + encodeURIComponent(val('hh_' + _side + '_month') || '') +
          '&ad=' + encodeURIComponent(val('hh_' + _side + '_day') || '') +
          '&ah=' + encodeURIComponent(val('hh_' + _side + '_hour') || '') +
          '&ag=' + encodeURIComponent(val('hh_' + _side + '_gender') || '') +
          '&an=' + encodeURIComponent(val('hh_' + _side + '_name') || '') +
          /* R3313（审-P1-4）：历法位同走邀请链——发起人按农历填的
           * 原始数字此前受邀者落进公历字段，差出整个月令。 */
          '&ac=' + encodeURIComponent(
            val('hh_' + _side + '_cal') === 'lunar' ? 'lunar' : '') +
          '&al=' + encodeURIComponent(
            checked('hh_' + _side + '_leap') ? '1' : '');
        /* R3304（审-P2）：邀请此前只发裸链接——收方点开前看不到
         * 发起人/玩法钩子。带上名字+对盘邀请语（与小红书文案同口径）。 */
        var _invName = val('hh_' + _side + '_name') || '我';
        /* R3247：明星邀请链的文案指向「你和明星合不合」——明星生辰
         * 已编码进链接，受邀者只需填自己的生日。 */
        var _msg = _celebOn('b')
          ? '✨ 想测测你和 ' + _invName + ' 合不合？TA 的生日已编进链接\n' +
            '在小满的解忧铺，点这里填上你的生日就对上了：\n' + _u
          : '💌 ' + _invName +
            ' 喊你合个盘——看看你们俩的合拍指数\n' +
            '在小满的解忧铺，点这里就能对上：\n' + _u;
        var _ok = function () {
          showToast(_dayPick(['邀请链接复制好了（里面有你的生辰，发给信任的人哦）',
            '链接已备好，TA 打开就能接着测（链接含你的生辰信息）',
            '复制成功：记得链接里带着你的生日，发给熟人就好'], 'hhinv'));
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(_msg).then(_ok, function () {
            _legacy();
          });
        } else { _legacy(); }
        /* R233t（R51-P2-18a）：clipboard API 缺失/被拒时此前直接弹
         * 「复制好了」但实际没复制——受邀人收到空气。走 execCommand。 */
        function _legacy() {
          var _ok0 = true;
          try {
            var _ta = document.createElement('textarea');
            _ta.value = _msg; _ta.style.cssText = 'position:fixed;opacity:0';
            document.body.appendChild(_ta); _ta.select();
            _ok0 = !!document.execCommand('copy');
            _ta.remove();
          } catch (e2) { _ok0 = false; }
          if (_ok0) { _ok(); }
          else {
            /* R3303-P1：内嵌浏览器无地址栏——弹可选中文本域兜底。 */
            try { _showTextExportModal('邀请链接', _u, '长按下面文本全选复制，发给 TA 吧'); }
            catch (eM2) { showToast('复制没成功，可截图链接发给 TA', 'warn'); }
          }
        }
      } catch (e) { showToast('邀请链接没生成成功，再试一次？', 'warn'); }
    });
    /* R230z（R36-P1-2）：存这对 → /api/favorites，下次一键回填 */
    on('hhSavePair', async function () {
      var btn = el('hhSavePair');
      if (btn) btn.disabled = true;
      var _an = (val('hh_a_name') || '').trim(), _bn = (val('hh_b_name') || '').trim();
      /* R2364（R119-P1-1）：昵称里的 | 会顶歪 ref_id 的 11 段分隔——
       * 编码名前先剥分隔符/空白，展示名（title）保留原样。 */
      var _anE = _an.replace(/[|%]/g, '').slice(0, 8);
      var _bnE = _bn.replace(/[|%]/g, '').slice(0, 8);
      /* R3313（审-P0）：chip 语义固定为「我侧 | TA侧」——邀请态下
       * 受邀者自己=B、发起人=A，存时要互换两组顺序，否则常态
       * 回放把发起人塞进 A（我侧），一提交就把自己档案毁成对方。
       * 尾段四位 = 两侧历法/闰月（R3313 审-P1-4，旧 12 段 chip
       * 无尾段照常按公历解）。 */
      var _sA = [num('hh_a_year'), num('hh_a_month'), num('hh_a_day'),
                 num('hh_a_hour'), val('hh_a_gender') || '女'];
      var _sB = [num('hh_b_year'), num('hh_b_month'), num('hh_b_day'),
                 num('hh_b_hour'), val('hh_b_gender') || '女'];
      var _tA = [val('hh_a_cal') === 'lunar' ? 'l' : '',
                 checked('hh_a_leap') ? '1' : ''];
      var _tB = [val('hh_b_cal') === 'lunar' ? 'l' : '',
                 checked('hh_b_leap') ? '1' : ''];
      var _inv = !!window.__hhInviteMode;
      var ref = (_inv ? _sB : _sA).concat(_inv ? _sA : _sB,
        [_inv ? _bnE : _anE, _inv ? _anE : _bnE],
        _inv ? _tB.concat(_tA) : _tA.concat(_tB)).join('|');
      try {
        await postJSON('/api/favorites', {
          type: 'hehun', ref_id: ref.slice(0, 64),
          title: (_inv ? (_bn || '我') : (_an || '我')) + ' × ' +
                 (_inv ? (_an || 'TA') : (_bn || 'TA'))
        });
        _favListInvalidate();
        showToast('已存下这对～下次点上面的标签就能直接填', 'info');
        _hhFavsRender();
      } catch (e) {
        showToast('没存上：' + _humanizeErr(e.message), 'error');
      } finally {
        if (btn) btn.disabled = false;
      }
      });
    };
    _rbHh();
    /* R3152：问句存进结果档——照卡聊时小满知道她问的是哪句。 */
    rememberResult('hehun', j, (val('hh_question') || '').trim());
    revealResult('hhResult');
    pollAiPolish('hhResult', j.ai_task_id);   // R191b：AI 段落后到（B-014）
  } catch (e) {
    if (_gen !== _HH_GEN) return;   /* R2502 */
    failWithRetry('hhResult', '计算失败：' + e.message, function () { doHehun(); });
  }
}


function _xzPad(n) { return String(n).padStart(2, '0'); }


function xzDateStr() {
  var y = el('xz_year'), m = el('xz_month'), d = el('xz_day');
  if (y && m && d && y.value && m.value && d.value) {
    return y.value + '-' + _xzPad(m.value) + '-' + _xzPad(d.value);
  }
  var t = new Date();
  return t.getFullYear() + '-' + _xzPad(t.getMonth() + 1) + '-' + _xzPad(t.getDate());
}


function xzSetDate(y, m, d) {
  var ys = el('xz_year'), ms = el('xz_month'), ds = el('xz_day');
  if (!(ys && ms && ds)) return;
  var now = new Date();
  if (!ys.options.length) {
    /* R3249f（UX-AUDIT C·星座 · 用户实测「年份列表翻不到头」）：
     * 这是日运导航器不是生日查询器——本命盘抽屉有独立的年份输入框，
     * 1900-2100 共 201 项的下拉在移动端是纯折磨。缩到今年 ±20
     * （覆盖所有日常翻阅+青少年本命年生日），更远的日期用‹ ›逐日翻。 */
    var _yLo = now.getFullYear() - 20, _yHi = now.getFullYear() + 20;
    for (var yy = _yLo; yy <= _yHi; yy++) {
      ys.add(new Option(yy + ' 年', String(yy)));
    }
  }
  if (!ms.options.length) {
    for (var mm = 1; mm <= 12; mm++) ms.add(new Option(mm + ' 月', String(mm)));
  }
  ys.value = String(y);
  ms.value = String(m);
  var days = new Date(y, m, 0).getDate();      // m 为 1-12，0 日 = 上月末 → 当月天数
  if (ds.options.length !== days) {
    ds.innerHTML = '';
    for (var dd = 1; dd <= days; dd++) ds.add(new Option(dd + ' 日', String(dd)));
  }
  /* R2349k（R72-B9）：2/29 换到平年/31 号换到小月——此前静默钳到
   * 月末日，查的其实不是用户说的那天。明示落到了哪天。 */
  if (d > days) {
    showToast(y + ' 年 ' + m + ' 月没有 ' + d + ' 号：按 ' +
      m + ' 月 ' + days + ' 号查了', 'info');
  }
  ds.value = String(Math.min(d, days));
}


function xzShiftDay(step) {
  var parts = xzDateStr().split('-');
  var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  d.setDate(d.getDate() + step);
  /* R2349k（R72-B8）：历法表界钳在选项窗口内——越界给 select 塞
   * 不存在的选项会让 xzDateStr 读空回落今天（看着像「跳回今天」）。
   * R3249f：窗口缩到 ±20 年后边界跟着 options 实际首尾走。 */
  var _ys2 = el('xz_year');
  var _loY = (_ys2 && _ys2.options.length)
    ? Number(_ys2.options[0].value) : 1900;
  var _hiY = (_ys2 && _ys2.options.length)
    ? Number(_ys2.options[_ys2.options.length - 1].value) : 2100;
  var _lo = new Date(_loY, 0, 1), _hi = new Date(_hiY, 11, 31);
  if (d < _lo) {
    xzSetDate(_loY, 1, 1);
    showToast('最早翻到 ' + _loY + ' 年，再往前翻不到啦', 'info');
    return doXingzuo(true);
  }
  if (d > _hi) {
    xzSetDate(_hiY, 12, 31);
    showToast('最远翻到 ' + _hiY + ' 年，再往后翻不到啦', 'info');
    return doXingzuo(true);
  }
  xzSetDate(d.getFullYear(), d.getMonth() + 1, d.getDate());
  /* R230d（R16-P1-1）：return 才能在 on() 在途锁里生效 */
  return doXingzuo(true);
}


function xzInitDate() {
  var ys = el('xz_year');
  if (ys && ys.value) return;                  // 用户已选过，别重置
  var t = new Date();
  xzSetDate(t.getFullYear(), t.getMonth() + 1, t.getDate());
}


/* R228f：force=false（视图重进）时若同日期结果已在屏则跳过——
 * 原实现每次进星座页都重发请求并 busy() 占位，造成两次滚动跳变。
 * 日期变更/主动查询仍传 true 强制刷新。 */
var _xzLastDate = null;
var _xzRenderedOn = null;   /* R2349k（R72-B2）：卡面渲染日戳 */
var _XZ_GEN = 0;   /* R230t（R33-P2-1）：翻页五个入口锁 key 互不共享，
                    * 乱序响应会盖掉新结果——代际号丢弃过期响应 */
async function doXingzuo(force) {
  xzInitDate();
  var dateStr = xzDateStr();
  var _xzBox = el('xzResult');
  if (!force && _xzLastDate === dateStr && _xzBox && _xzBox.children.length) return;
  var _gen = ++_XZ_GEN;
  busy('xzResult', '查询中…');
  try {
    var j = await api('/api/xingzuo?date=' + encodeURIComponent(dateStr));
    if (_gen !== _XZ_GEN) return;   /* 更新的请求已接管——本响应丢弃 */
    var html = '<div class="xz-result">';
    if (j.today_sign) {
      /* C-002-fix：星座配图 + 今日值宫 */
      var _tk = ({'白羊':'aries','金牛':'taurus','双子':'gemini','巨蟹':'cancer','狮子':'leo','处女':'virgo','天秤':'libra','天蝎':'scorpio','射手':'sagittarius','摩羯':'capricorn','水瓶':'aquarius','双鱼':'pisces'})[j.today_sign] || 'aries';
      /* R2349k（R72-C2）：翻的不是今天时「今日当班/今日守护星」是错
       * 话术——跟查询日改说「当日」。 */
      var _xzT0 = (dateStr === todayIso()) ? '今日' : '当日';
      html += '<div class="xz-today"><img class="xz-today-img" src="/static/cream/zodiac-' + _tk + '.jpg" alt="" onerror="this.classList.add(\'is-missing\')"><span class="xz-today-label">' + _xzT0 + '当班</span><span class="xz-today-sign">' + esc(j.today_sign) + '</span></div>';
      /* C-002：星座详情页——爱情/事业/财运分维度 */
      var _todayDetail = (j.signs || []).filter(function (s) { return s.is_today; })[0];
      /* R232b（R40-A3/W4）：值宫名+值星露出——palace/star 算好了
       * 从未显示，「今天是哪宫当班」是这张卡的标题素材。 */
      if (_todayDetail && (_todayDetail.palace || _todayDetail.star)) {
        html += '<div class="xz-palace-line">' +
          esc((_todayDetail.palace || '') +
              (_todayDetail.star ? ' · ' + _xzT0 + '守护星：' + _todayDetail.star : '')) +
          '</div>' +
          /* R2500（R144-P3-7）：宫名/星名是《星学大成》原典繁体，
           * 与卡片简体 chip 混排观感不统一——加脚注说明出处。 */
          '<div class="xz-palace-src">宫名·星名照原典写法</div>';
        if (_todayDetail.sign_note) {
          html += '<div class="xz-palace-note">' +
            esc(_todayDetail.sign_note) + '</div>';
        }
      }
      if (_todayDetail) {
        html += '<div class="xz-detail">';
        if (_todayDetail.love) html += '<div class="xz-dim"><span class="xz-dim-label">💕 爱情</span><span class="xz-dim-text">' + esc(_todayDetail.love) + '</span></div>';
        if (_todayDetail.career) html += '<div class="xz-dim"><span class="xz-dim-label">💼 事业</span><span class="xz-dim-text">' + esc(_todayDetail.career) + '</span></div>';
        if (_todayDetail.wealth) html += '<div class="xz-dim"><span class="xz-dim-label">💰 财运</span><span class="xz-dim-text">' + esc(_todayDetail.wealth) + '</span></div>';
        html += '</div>';
      }
      if (j.today_note) html += '<p class="xz-today-note">' + esc(j.today_note) + '</p>';
      html += '</div>';
    }
    if (j.signs && j.signs.length) {
      /* R3174：me 档案生日→太阳星座，十二宫里点亮「我」的宫——
       * 存过生日的用户扫一眼就知道哪张是自己的牌。 */
      var _mySign = '';
      try {
        var _meX = _meGet('me');
        if (_meX && _meX.m && _meX.d &&
            typeof window.__sunSign === 'function') {
          _mySign = window.__sunSign(+_meX.m, +_meX.d) || '';
        }
      } catch (eMS) {}
      html += '<div class="xz-grid">';
      j.signs.forEach(function (s) {
        var cls = s.is_today ? ' xz-active' : '';
        if (_mySign && s.sign === _mySign) cls += ' xz-mine';
        /* C-002-fix：星座配图 */
        var _zk = ({'白羊':'aries','金牛':'taurus','双子':'gemini','巨蟹':'cancer','狮子':'leo','处女':'virgo','天秤':'libra','天蝎':'scorpio','射手':'sagittarius','摩羯':'capricorn','水瓶':'aquarius','双鱼':'pisces'})[s.sign] || 'aries';
        /* R232b（R40-A3）：宫卡补本命三运悬停——sign_love/career/wealth
         * 算好未露；桌面悬停/读屏可看，卡面仍保持轻。 */
        var _stt = [['爱情', s.sign_love], ['事业', s.sign_career],
                    ['财运', s.sign_wealth]]
          .filter(function (p) { return p[1]; })
          .map(function (p) { return p[0] + '：' + p[1]; }).join('\n');
        /* R2349l（R73-obs3）：悬停 title 移动端不可达——宫卡改可点，
         * 三运明细收成卡内折叠行，点一下展开/收起。 */
        var _tri = _stt ? '<div class="xz-tri" hidden>' +
          _stt.split('\n').map(function (t2) {
            return '<div>' + esc(t2) + '</div>';
          }).join('') + '</div>' : '';
        /* R2349o（R78-P0-1）：宫卡是整条键盘死路——补 tabindex+role+
         * aria-expanded，Enter/Space 走同一展开路径（keydown 委托在下）。 */
        /* R2506（审-U4）：aria-label 顶替全卡内容——读屏此前只听
         * 到「白羊宫，展开三运明细」，xz-note 日运正文整条丢失。
         * 把正文并进可访问名。 */
        html += '<div class="xz-card' + cls + (_stt ? ' xz-tap' : '') + '"' +
          (_stt ? ' title="' + esc(_stt) + '"' +
                 ' tabindex="0" role="button" aria-expanded="false"' +
                 ' aria-label="' + esc(s.sign + '宫，' + (s.note || '') +
                 '，点按展开三运明细') + '"' : '') +
          '><img class="xz-card-img" src="/static/cream/zodiac-' + _zk + '.jpg" alt="' + esc(s.sign) + '" loading="lazy" onerror="this.classList.add(\'is-missing\')"><div class="xz-card-body"><span class="xz-name">' + esc(s.sign) +
          (_mySign && s.sign === _mySign
           ? '<i class="xz-mine-tag">我</i>' : '') + '</span>' +
          (s.palace ? '<span class="xz-palace">' + esc(s.palace) + '</span>' : '') +
          '<span class="xz-note">' + esc(s.note) + '</span>' +
          (_stt ? '<span class="xz-more">三运 ›</span>' : '') +
          _tri + '</div></div>';
      });
      html += '</div>';
    }
    /* R229z续23（R11-#5）：星座结果卡补免责 */
    html += '<div style="font-size:12px;color:var(--muted);margin-top:10px;">星座日运看个开心，不构成任何建议 ✨</div>';
    html += '</div>';
    html += tailHook('xingzuo');
    paint('xzResult', html);
    /* R2349l（R73-obs3）：宫卡点展开三运——委托绑一次，重渲不失。 */
    var _xzg = el('xzResult');
    if (_xzg && !_xzg.dataset.xzTriBound) {
      _xzg.dataset.xzTriBound = '1';
      var _xzToggle = function (c) {
        if (!c) return;
        var tri = c.querySelector('.xz-tri');
        if (!tri) return;
        tri.hidden = !tri.hidden;
        c.setAttribute('aria-expanded', tri.hidden ? 'false' : 'true');
        var mo = c.querySelector('.xz-more');
        if (mo) mo.textContent = tri.hidden ? '三运 ›' : '收起 ‹';
      };
      _xzg.addEventListener('click', function (e) {
        var c = e.target && e.target.closest
          ? e.target.closest('.xz-card.xz-tap') : null;
        _xzToggle(c);
      });
      /* R2349o（R78-P0-1）：键盘 Enter/Space 同展开。 */
      _xzg.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var c = e.target && e.target.closest
          ? e.target.closest('.xz-card.xz-tap') : null;
        if (!c) return;
        e.preventDefault();
        _xzToggle(c);
      });
    }
    _xzLastDate = dateStr;   /* R228f */
    _xzRenderedOn = todayIso();   /* R2349k（R72-B2） */
    rememberResult('xingzuo', j, '');   /* R219b（P0-2）：今日值宫进第一句 */
    revealResult('xzResult');
    pollAiPolish('xzResult', j.ai_task_id);   /* R3193：AI 段落后到 */
    /* R230d（R16-P2-2）：星座分享按钮（其他五个测算页都有，独缺这里）。 */
    var xzCard2 = el('xzResult');
    if (xzCard2 && !document.getElementById('shareXingzuo')) {
      var xzBtn = document.createElement('button');
      xzBtn.className = 'ghost fav-btn';
      xzBtn.id = 'shareXingzuo'; xzBtn.title = '生成分享图';
      xzBtn.textContent = '📸 分享图';   /* R231d（R37-F11） */
      xzBtn.style.margin = '10px 0 0';
      xzCard2.appendChild(xzBtn);
      xzBtn.addEventListener('click', function () { downloadPoster(j, 'xingzuo'); });
    }
  } catch (e) {
    if (_gen !== _XZ_GEN) return;   /* 过期响应的失败也不盖新结果 */
    failWithRetry('xzResult', '查询失败：' + e.message,
                  function () { doXingzuo(true); });
  }
}

/* v5：场景结论生成——每句都带「所以然」（黄历今天主推什么/忌什么/凭据是哪条），
 * 不再出现「没提到就平常心」这种不讲理的说法。 */
/* R228s：与服务端 _CHAT_SCENE_TERMS 同口径——两处各存一份（前端即时判定，
 * 服务端喂小满事实）。凡映射到真规范词的都在此；自映射词（聚餐/购物等）
 * 不必列——抽词命中后自然走中性卡。 */
var HL_SCENE_ALIAS = {
  /* R3084（巡#501）：面试/求职补谒贵腿（答辩同构）；相亲/表白/约会
   * 补议亲/见面腿（见家长同构）——与后端 _CHAT_SCENE_TERMS 逐键同步。 */
  '面试': ['上任','谒贵'], '求职': ['上任','谒贵'],
  '上班': ['上任'], '入职': ['上任'],
  '约会': ['嫁娶','谒贵'], '表白': ['嫁娶','订盟'],
  '相亲': ['嫁娶','纳采','订盟'],
  '结婚': ['嫁娶'], '领证': ['嫁娶'],
  /* R229q：与服务端 _CHAT_SCENE_TERMS 逐键同构（probe_date_parity 钉扎）。
   * 「入宅」入搬家系；「平整」上行注释已带。 */
  /* R2349n（R77-P2-6）：「移徒」异体字死词摘除——词表统一为移徙。 */
  '搬家': ['移徙', '入宅', '修造', '平整'], '挪窝': ['移徙'],
  '远行': ['出行'], '装修': ['修造', '动土'],
  /* R2349s（R85-P1-1）：归家镜像后端 _CHAT_SCENE_TERMS——问「适合归家吗」
   * 前端判定卡与后端事实行同口径。 */
  '归家': ['出行', '远行'],
  '开业': ['开市', '纳财'], '开张': ['开市'], '签约': ['立券', '纳财'], '合同': ['立券'],
  '出行': ['出行', '远行'], '旅行': ['出行', '远行'], '旅游': ['出行', '远行'],
  '出差': ['出行', '远行'], '出游': ['出行', '远行'], '出国': ['出行', '远行'],
  '出门': ['出行', '远行'],
  '收款': ['纳财'], '理财': ['纳财'], '看病': ['求医', '治病', '求医疗病'],
  '种花': ['栽种'],
  '理发': ['冠笄'], '剪发': ['冠笄'], '剪头': ['冠笄'], '剃头': ['冠笄'],
  '美发': ['冠笄'], '烫头': ['冠笄'],
  /* R2349n（R77-P0-3）：医疗口径与后端统一——体检/洗牙/医美此前只映
   * 求医一个词，比「看病」少一半候选日且全克破日。 */
  '手术': ['求医', '治病', '求医疗病'], '开刀': ['求医','治病','求医疗病'],
  '体检': ['求医', '治病', '求医疗病'], '洗牙': ['求医', '治病', '求医疗病'],
  '拔牙': ['求医', '治病', '求医疗病'], '医美': ['求医', '治病', '求医疗病'],
  '整容': ['求医', '治病', '求医疗病'],
  /* R3370-P2-7：就医场景词——「哪天去医院好」此前净落「没提」，
   * 就诊机构名全映求医族。 */
  '医院': ['求医', '治病', '求医疗病'], '住院': ['求医','治病','求医疗病'],
  '诊所': ['求医','治病','求医疗病'], '门诊': ['求医','治病','求医疗病'],
  '急诊': ['求医','治病','求医疗病'], '出院': ['求医','治病','求医疗病'],
  '借钱': ['纳财'], '讨债': ['纳财'], '还钱': ['纳财'], '还贷': ['纳财'],
  '辞职': ['解除'], '离职': ['解除'],
  /* R3083（巡#500）：跳槽/换工作双腿——离开+赴任，与后端同构补上任腿；
   * 辞职/离职纯离开单腿不动。 */
  '跳槽': ['解除', '上任'], '换工作': ['解除', '上任'],
  '解除合同': ['解除'], '毁约': ['解除'], '退婚': ['解除'], '分手': ['解除'],
  '说拜拜': ['解除'], '拜拜了': ['解除'], '再见': ['解除'],
  '宠物': ['进人口'], '养猫': ['进人口'], '养狗': ['进人口'],
  '钓鱼': ['捕捉'], '捕捞': ['捕捉'], '种菜': ['栽种'], '诉讼': ['诉讼'],
  '打官司': ['诉讼'], '和解': ['解除'], '动工': ['动土', '破土'],
  /* R229w：逛街/购物/聚餐系落地真规范词（后端 _CHAT_SCENE_TERMS 同构，
   * probe_date_parity 钉扎）——出门类→出行，聚餐类→出行+谒贵。 */
  '买东西': ['出行'], '购物': ['出行'], '逛街': ['出行'],
  /* R2574：与服务端 _CHAT_SCENE_TERMS 逐键同构——买手机/签证实测漏网。 */
  '买手机': ['出行'], '签证': ['出行', '远行'],
  '出去玩': ['出行', '远行'], '聚餐': ['出行', '谒贵'], '请客': ['出行', '谒贵'],
  '聚会': ['出行', '谒贵'], '饭局': ['出行', '谒贵'],
  /* R2349n（R77-P2-5）：健身/唱歌键此前只在后端——补齐逐键同构。 */
  '健身': ['健身'], '唱歌': ['唱歌'], '运动': ['健身'], '唱k': ['唱歌'],
  '许愿': ['祈福', '求嗣'], '拜拜': ['祭祀'], '祭灶': ['祭祀'], '祭祖': ['祭祀'], '考试': ['入学'], '上学': ['入学'],
  '开学': ['入学'],
  /* R230h（R20-F1）：与后端 _CHAT_SCENE_TERMS 同步增键（parity 钉扎）。 */
  '备孕': ['求嗣'], '求子': ['求嗣'], '要孩子': ['求嗣'], '生子': ['求嗣'],
  '怀孕': ['求嗣'],
  /* R2349（R64-P1-5）：真实语料补词——小红书客群高频说法此前全落
   * 中性卡。与后端 _CHAT_SCENE_TERMS 逐键同构（probe_date_parity 钉扎）。 */
  '考研': ['入学','祈福'], '期末考': ['入学','祈福'], '期末': ['入学','祈福'],
  '教资': ['入学','祈福'], '科目二': ['入学','祈福'], '科目三': ['入学','祈福'],
  '考公': ['入学','祈福'], '考证': ['入学','祈福'], '考级': ['入学','祈福'],
  '上岸': ['入学','祈福'], '答辩': ['入学','谒贵'], '复试': ['入学','谒贵'],
  '报班': ['入学','纳财'], '复习': ['入学'], '学习': ['入学'],
  '交论文': ['入学','谒贵'], '论文': ['入学','谒贵'],
  /* 第二波补词（与后端同构）：约饭/面基/奔现→谒贵+出行；
   * 偶遇/自推/运气→祈福；脱单/暧昧/crush→嫁娶。 */
  '吃饭': ['出行','谒贵'], '组局': ['出行','谒贵'],
  '面基': ['出行','谒贵'], '奔现': ['出行','谒贵'],
  '偶遇': ['谒贵'], '自推': ['祈福'], '运气': ['祈福'],
  '脱单': ['嫁娶'], '暧昧': ['嫁娶'], 'crush': ['嫁娶'],
  '异地恋': ['嫁娶'], '出门玩': ['出行','远行'],
  '抽卡': ['纳财','祈福'], '抽盲盒': ['纳财','祈福'], '盲盒': ['纳财','祈福'],
  '彩票': ['纳财'], '谷子': ['纳财'], '买谷子': ['纳财'], '手气': ['祈福'],
  '开池': ['纳财'], '出金': ['纳财'],
  '烫发': ['冠笄'], '染发': ['冠笄'], '染头': ['冠笄'], '剪刘海': ['冠笄'],
  '刘海': ['冠笄'], '美甲': ['冠笄'], '纹眉': ['冠笄'], '美容': ['冠笄'],
  'do脸': ['求医','治病','求医疗病'], '水光针': ['求医','治病','求医疗病'],
  '双眼皮': ['求医','治病','求医疗病'], '微整': ['求医','治病','求医疗病'],
  '见家长': ['谒贵','嫁娶'], '见父母': ['谒贵','嫁娶'],
  /* R2349d：「见男朋友家长」里「见家长」不连续——补「家长」兜底。 */
  '家长': ['谒贵','嫁娶'], '订婚': ['嫁娶'],
  '提亲': ['嫁娶'], '彩礼': ['纳财'], '产检': ['求医','治病','求医疗病'], '求婚': ['嫁娶'],
  '离婚': ['解除'],
  '抢票': ['纳财'], '开票': ['纳财'], '演唱会': ['出行','谒贵'],
  '签售会': ['出行','谒贵'], '见爱豆': ['出行','谒贵'], '音乐节': ['出行'],
  '应援': ['出行'],
  '接猫': ['进人口'], '领养': ['进人口'], '接新猫': ['进人口'],
  '接小猫': ['进人口'], '绝育': ['求医','治病','求医疗病'],
  '打疫苗': ['求医','治病','求医疗病'], '疫苗': ['求医','治病','求医疗病'],
  '看房': ['出行','入宅'], '搬新窝': ['移徙','入宅'], '续租': ['立券','移徙'],
  '租房': ['立券','入宅'],
  /* R2349q（R82-P2-6）：与后端 _CHAT_SCENE_TERMS 逐键同构——买房/
   * 蹦极/打游戏/熬夜补词（此前零事实放飞）。 */
  '买房': ['纳财','入宅'], '买房子': ['纳财','入宅'], '置业': ['纳财','入宅'],
  '蹦极': ['出行'],
  '打游戏': ['打游戏'], '玩游戏': ['打游戏'], '熬夜': ['熬夜'],
  '找工作': ['上任','谒贵'], '被裁': ['解除'], '裁员': ['解除'],
  '海投': ['上任'], '简历': ['上任'], '终面': ['上任','谒贵'],
  '报到': ['上任'], '谈加薪': ['谒贵','纳财'], '加薪': ['纳财','谒贵'],
  '复合': ['嫁娶'], '和好': ['嫁娶'], '把话说开': ['解除'], '摊牌': ['解除'],
  '删好友': ['解除'],
  '开店': ['开市','纳财'], '副业': ['开市','纳财'], '上新': ['开市'],
  '摆摊': ['开市','纳财'], '生意': ['开市','纳财'], '网店': ['开市','纳财'],
  '回家': ['出行'], '团圆': ['出行','谒贵'], '出发': ['出行'],
  '一日游': ['出行'], '自驾游': ['出行'], '看电影': ['出行'],
  /* R2349n（R77-P1-1）：与后端 _CHAT_SCENE_TERMS 同构补键。 */
  '开工': ['动土', '开市', '修造'], '开工大吉': ['动土', '开市'],
  '乔迁': ['移徙', '入宅'], '搬新家': ['移徙', '入宅'],
  '买车': ['纳财', '立券'], '提车': ['纳财', '立券'],
  '会友': ['谒贵', '出行'], '会亲友': ['谒贵', '出行'],
  '沐浴': ['沐浴'], '洗澡': ['沐浴'],
  '纹身': ['求医', '冠笄'], '割双眼皮': ['求医','治病','求医疗病'],
  '直播首秀': ['开市', '纳财'], '开播': ['开市', '纳财'],
  '上学报道': ['入学'], '报道': ['上任', '入学'],
  '成婚': ['嫁娶'], '出嫁': ['嫁娶'], '迎娶': ['嫁娶'],
  '复诊': ['求医', '治病', '求医疗病'], '复查': ['求医', '治病', '求医疗病'],
  '要微信': ['嫁娶'], '发消息': ['谒贵'], '见面': ['谒贵'],
  '上香': ['祭祀'], '拜庙': ['祭祀'], '囤货': ['纳财'],
  /* R2349f 第三波：考试细分/内容创业/医美轻项目/娱乐社交/断联。 */
  '雅思': ['求名','入学'], '托福': ['求名','入学'], '四六级': ['求名','入学'],
  /* 科目二/三、考公、教资、洗牙、体检、烫头已在上面（入学/祈福/求医/冠笄）。 */
  '驾考': ['求名'], '考编': ['求名','上任'], '专升本': ['求名','入学'],
  '直播': ['开市','纳财'], '带货': ['纳财','开市'], '自媒体': ['开市','纳财'],
  '做号': ['开市'], '起号': ['开市'],
  '打耳洞': ['求医','治病','求医疗病'],
  '种睫毛': ['冠笄'], '漂发': ['冠笄'],
  '剧本杀': ['出行','谒贵'], '密室': ['出行'], '桌游': ['出行','谒贵'],
  '露营': ['出行'], '爬山': ['出行','登山'], '徒步': ['出行','登山'],
  '野餐': ['出行'], '断联': ['解除','祈福'], '冷战': ['解除']
};
function _hlSceneAlias(sc) { return (HL_SCENE_ALIAS[sc] || []).slice(); }
/* R2349n（R77-P0-1）：与后端 _TERM_FAMILIES 同构——忌侧判定按同义族
 * 判（问搬家而忌栏有动土 → 判「宜忌都有」不判「宜」）。 */
var _HL_FAMILIES = [
  /* R2400（R141-P1-2）：与后端 _TERM_FAMILIES 同构——R2400 后端扩编
   * （营造+平整、功名+出官/谒贵、新增丧葬整族）时此表静默漂移了
   * 一整批场景日。probe_date_parity 已钉族表同构段，再漂移会红。 */
  ['修造', '动土', '破土', '塞穴', '筑堤', '破屋坏垣', '竖柱', '上梁', '平整'],
  ['出行', '远行', '归家', '移徙', '入宅', '乘船', '登山'],
  ['开市', '立券', '纳财', '开仓', '交易', '置产'],
  ['嫁娶', '求嗣', '进人口', '纳采', '订盟'],
  ['上任', '求名', '入学', '出官', '谒贵'],
  ['安葬', '行丧', '启攒', '修坟', '立碑', '除服', '成服', '入殓'],
  ['祭祀', '祈福'],
  ['求医', '治病', '求医疗病'],
  ['捕捉', '畋猎', '狩猎', '田猎']
];
var _HL_FAMILY_OF = {};
_HL_FAMILIES.forEach(function (fam) {
  fam.forEach(function (w) {
    _HL_FAMILY_OF[w] = (_HL_FAMILY_OF[w] || []).concat(fam);
  });
});
function _hlFamily(t) { return _HL_FAMILY_OF[t] || [t]; }
/* R227b（用户反馈「不能照本宣科」）：问一嘴的自由输入抽事项词——
 * 词表外的说法（养猫/剪头发/野餐…）也进「没直接提到=中性」判定，
 * 不再回「我接不住」把用户顶回去。 */
/* R229d：繁中输入归一——「明天適合出行嗎」此前抽出「適合出行嗎」整串当
 * 事项词原样回显判定卡（比 asdf 更常见的真实输入：繁体键盘用户）。只映射
 * 问句域常见字；未映射字原样通过（新字随用随补，宁缺毋滥不错转）。 */
/* R3265（R3247-P1-1）：与 services._T2S_PAIRS 同串同源——OpenCC
 * TSCharacters 无歧义映射+手维护条目共 2801 对（parity 钉扎），
 * 「繁简」紧邻成对空格分隔；改时两侧必须同步。 */
var _T2S_PAIRS =
  "丟丢 並并 亂乱 亙亘 亞亚 佇伫 佈布 佔占 併并 來来 侖仑 侶侣 侷局 俁俣 係系 俔伣 俠侠 俥伡 俬私 倀伥 倆俩 倈俫 倉仓 個个 們们 倖幸 倫伦 偉伟 側侧 偵侦 偽伪 傑杰 傖伧 傘伞 備备 傢家 傭佣 傯偬 傳传 傴伛 債债 傷伤 傾倾 僂偻 僅仅 僉佥 僑侨 僕仆 僞伪 僥侥 僨偾 僱雇 價价 儀仪 儁俊 儂侬 億亿 儈侩 儉俭 儎傤 儐傧 儔俦 儕侪 償偿 優优 儲储 儷俪 儺傩 儻傥 儼俨 兇凶 兌兑 兒儿 兗兖 內内 兩两 冊册 冑胄 冪幂 凈净 凍冻 凜凛 凱凯 別别 刪删 剄刭 則则 剎刹 剗刬 剛刚 剝剥 剮剐 剴剀 創创 剷铲 劇剧 劉刘 劊刽 劌刿 劍剑 劑剂 勁劲 動动 務务 勛勋 勝胜 勞劳 勢势 勩勚 勱劢 勳勋 勵励 勸劝 勻匀 匭匦 匯汇 匱匮 區区 協协 卹恤 卻却 卽即 厙厍 厠厕 厤历 厭厌 厲厉 厴厣 參参 叄叁 叢丛 吒咤 吳吴 吶呐 呂吕 咼呙 員员 唄呗 唸念 問问 啓启 啞哑 啟启 啢唡 喚唤 喪丧 喫吃 喬乔 單单 喲哟 嗆呛 嗇啬 嗊唝 嗎吗 嗚呜 嗩唢 嗶哔 嘆叹 嘍喽 嘓啯 嘔呕 嘖啧 嘗尝 嘜唛 嘩哗 嘮唠 嘯啸 嘰叽 嘵哓 嘸呒 嘽啴 噓嘘 噝咝 噠哒 噥哝 噦哕 噯嗳 噲哙 噴喷 噸吨 嚀咛 嚇吓 嚌哜 嚐尝 嚕噜 嚙啮 嚥咽 嚦呖 嚨咙 嚮向 嚲亸 嚳喾 嚴严 嚶嘤 囀啭 囁嗫 囂嚣 囅冁 囈呓 囉啰 囌苏 囑嘱 囪囱 圇囵 國国 圍围 園园 圓圆 圖图 團团 垻坝 埡垭 埰采 執执 堅坚 堊垩 堖垴 堝埚 堯尧 報报 場场 塊块 塋茔 塏垲 塒埘 塗涂 塚冢 塢坞 塤埙 塵尘 塹堑 墊垫 墜坠 墮堕 墰坛 墳坟 墶垯 墻墙 墾垦 壇坛 壋垱 壎埙 壓压 壘垒 壙圹 壚垆 壜坛 壞坏 壟垄 壠垅 壢坜 壩坝 壪塆 壯壮 壺壶 壼壸 壽寿 夠够 夢梦 夾夹 奐奂 奧奥 奩奁 奪夺 奬奖 奮奋 奼姹 妝妆 姍姗 姦奸 娛娱 婁娄 婦妇 婭娅 媧娲 媯妫 媼媪 媽妈 嫋袅 嫗妪 嫵妩 嫺娴 嫻娴 嫿婳 嬀妫 嬃媭 嬈娆 嬋婵 嬌娇 嬙嫱 嬡嫒 嬤嬷 嬪嫔 嬰婴 嬸婶 孃娘 孌娈 孫孙 學学 孿孪 宮宫 寀采 寢寝 實实 寧宁 審审 寫写 寬宽 寵宠 寶宝 將将 專专 尋寻 對对 導导 尷尴 屆届 屍尸 屓屃 屜屉 屢屡 層层 屨屦 屬属 岡冈 峯峰 峴岘 島岛 峽峡 崍崃 崑昆 崗岗 崢峥 崬岽 嵐岚 嵗岁 嶁嵝 嶄崭 嶇岖 嶔嵚 嶗崂 嶠峤 嶢峣 嶧峄 嶨峃 嶮崄 嶸嵘 嶺岭 嶼屿 嶽岳 巋岿 巒峦 巔巅 巖岩 巰巯 巹卺 帥帅 師师 帳帐 帶带 幀帧 幃帏 幗帼 幘帻 幟帜 幣币 幫帮 幬帱 幹干 幾几 庫库 廁厕 廂厢 廄厩 廈厦 廎庼 廕荫 廚厨 廝厮 廟庙 廠厂 廡庑 廢废 廣广 廩廪 廳厅 弒弑 弔吊 弳弪 張张 強强 彆别 彈弹 彌弥 彎弯 彔录 彙汇 彠彟 彥彦 彫雕 彲彨 彿佛 後后 徑径 從从 徠徕 復复 徹彻 恆恒 恥耻 悅悦 悞悮 悵怅 悶闷 悽凄 惡恶 惱恼 惲恽 惻恻 愛爱 愜惬 愨悫 愴怆 愷恺 愾忾 慄栗 態态 慍愠 慘惨 慚惭 慟恸 慣惯 慤悫 慪怄 慫怂 慮虑 慳悭 慶庆 慼戚 慾欲 憂忧 憊惫 憐怜 憑凭 憒愦 憖慭 憚惮 憤愤 憫悯 憮怃 憲宪 憶忆 懇恳 應应 懌怿 懍懔 懞蒙 懟怼 懣懑 懨恹 懲惩 懶懒 懷怀 懸悬 懺忏 懼惧 懾慑 戀恋 戇戆 戔戋 戧戗 戩戬 戱戯 戲戏 戶户 拋抛 挩捝 挱挲 挾挟 捨舍 捫扪 捱挨 捲卷 掃扫 掄抡 掗挜 掙挣 掛挂 採采 揀拣 揚扬 換换 揮挥 揯搄 損损 搖摇 搗捣 搵揾 搶抢 摑掴 摜掼 摟搂 摯挚 摳抠 摶抟 摺折 摻掺 撈捞 撏挦 撐撑 撓挠 撟挢 撣掸 撥拨 撫抚 撲扑 撳揿 撻挞 撾挝 撿捡 擁拥 擄掳 擇择 擊击 擋挡 擔担 據据 擠挤 擬拟 擯摈 擰拧 擱搁 擲掷 擴扩 擷撷 擺摆 擻擞 擼撸 擾扰 攄摅 攆撵 攏拢 攔拦 攖撄 攙搀 攛撺 攜携 攝摄 攢攒 攣挛 攤摊 攪搅 攬揽 敎教 敓敚 敗败 敘叙 敵敌 數数 斂敛 斃毙 斆敩 斕斓 斬斩 斷断 旂旗 旣既 昇升 時时 晉晋 晝昼 暈晕 暉晖 暘旸 暢畅 暫暂 曄晔 曆历 曇昙 曉晓 曏向 曖暧 曠旷 曨昽 曬晒 書书 會会 朧胧 朮术 東东 枴拐 柵栅 柺拐 査查 桿杆 梔栀 梘枧 條条 梟枭 梲棁 棄弃 棊棋 棖枨 棗枣 棟栋 棧栈 棲栖 棶梾 椏桠 楊杨 楓枫 楨桢 業业 極极 榘矩 榦干 榪杩 榮荣 榲榅 榿桤 構构 槍枪 槓杠 槤梿 槧椠 槨椁 槮椮 槳桨 槶椢 槼椝 樁桩 樂乐 樅枞 樑梁 樓楼 標标 樞枢 樣样 樧榝 樳桪 樸朴 樹树 樺桦 樿椫 橈桡 橋桥 機机 橢椭 橫横 檁檩 檉柽 檔档 檜桧 檟槚 檢检 檣樯 檮梼 檯台 檳槟 檸柠 檻槛 櫃柜 櫓橹 櫚榈 櫛栉 櫝椟 櫞橼 櫟栎 櫥橱 櫧槠 櫨栌 櫪枥 櫫橥 櫬榇 櫱蘖 櫳栊 櫸榉 櫻樱 欄栏 欅榉 權权 欏椤 欒栾 欖榄 欞棂 欽钦 歎叹 歐欧 歟欤 歡欢 歲岁 歷历 歸归 歿殁 殘残 殞殒 殤殇 殫殚 殭僵 殮殓 殯殡 殲歼 殺杀 殻壳 殼壳 毀毁 毆殴 毿毵 氂牦 氈毡 氌氇 氣气 氫氢 氬氩 氳氲 氾泛 汎泛 汙污 決决 沒没 沖冲 況况 泝溯 洩泄 洶汹 浹浃 涇泾 涗涚 涼凉 淒凄 淚泪 淥渌 淨净 淩凌 淪沦 淵渊 淶涞 淺浅 渙涣 減减 渢沨 渦涡 測测 渾浑 湊凑 湞浈 湧涌 湯汤 溈沩 準准 溝沟 溫温 溮浉 溳涢 溼湿 滄沧 滅灭 滌涤 滎荥 滙汇 滬沪 滯滞 滲渗 滷卤 滸浒 滻浐 滾滚 滿满 漁渔 漊溇 漚沤 漢汉 漣涟 漬渍 漲涨 漵溆 漸渐 漿浆 潁颍 潑泼 潔洁 潙沩 潛潜 潤润 潯浔 潰溃 潷滗 潿涠 澀涩 澆浇 澇涝 澐沄 澗涧 澠渑 澤泽 澦滪 澩泶 澮浍 澱淀 濁浊 濃浓 濕湿 濘泞 濚溁 濛蒙 濜浕 濟济 濤涛 濫滥 濰潍 濱滨 濺溅 濼泺 濾滤 瀂澛 瀅滢 瀆渎 瀉泻 瀏浏 瀕濒 瀘泸 瀝沥 瀟潇 瀠潆 瀦潴 瀧泷 瀨濑 瀲潋 瀾澜 灃沣 灄滠 灑洒 灕漓 灘滩 灝灏 灣湾 灤滦 灧滟 灩滟 災灾 為为 烏乌 烴烃 無无 煉炼 煒炜 煙烟 煢茕 煥焕 煩烦 煬炀 熅煴 熒荧 熗炝 熱热 熲颎 熾炽 燁烨 燈灯 燉炖 燒烧 燙烫 燜焖 營营 燦灿 燬毁 燭烛 燴烩 燻熏 燼烬 燾焘 爍烁 爐炉 爛烂 爭争 爲为 爺爷 爾尔 牀床 牆墙 牘牍 牽牵 犖荦 犛牦 犢犊 犧牺 狀状 狹狭 狽狈 猙狰 猶犹 猻狲 獁犸 獃呆 獄狱 獅狮 獎奖 獨独 獪狯 獫猃 獮狝 獰狞 獲获 獵猎 獷犷 獸兽 獺獭 獻献 獼猕 玀猡 現现 琱雕 琺珐 琿珲 瑋玮 瑒玚 瑣琐 瑤瑶 瑩莹 瑪玛 瑲玱 璉琏 璡琎 璣玑 璦瑷 璫珰 環环 璵玙 璸瑸 璽玺 璿璇 瓊琼 瓏珑 瓔璎 瓚瓒 甌瓯 甕瓮 產产 産产 甦苏 甯宁 畝亩 畢毕 異异 畵画 當当 疇畴 疊叠 痙痉 痠酸 痾疴 瘂痖 瘋疯 瘍疡 瘓痪 瘞瘗 瘡疮 瘧疟 瘮瘆 瘲疭 瘺瘘 瘻瘘 療疗 癆痨 癇痫 癉瘅 癒愈 癘疠 癟瘪 癡痴 癢痒 癤疖 癥症 癧疬 癩癞 癬癣 癭瘿 癮瘾 癰痈 癱瘫 癲癫 發发 皁皂 皚皑 皰疱 皸皲 皺皱 盃杯 盜盗 盞盏 盡尽 監监 盤盘 盧卢 盪荡 眞真 眥眦 眾众 睏困 睜睁 睞睐 瞘眍 瞞瞒 瞶瞆 瞼睑 矇蒙 矓眬 矚瞩 矯矫 硃朱 硜硁 硤硖 硨砗 硯砚 碕埼 碩硕 碭砀 碸砜 確确 碼码 磑硙 磚砖 磠硵 磣碜 磧碛 磯矶 磽硗 礄硚 礆硷 礎础 礙碍 礦矿 礪砺 礫砾 礬矾 礱砻 祕秘 祿禄 禍祸 禎祯 禕祎 禡祃 禦御 禪禅 禮礼 禰祢 禱祷 禿秃 秈籼 稅税 稈秆 稜棱 稟禀 種种 稱称 穀谷 穌稣 積积 穎颖 穠秾 穡穑 穢秽 穩稳 穫获 穭穞 窩窝 窪洼 窮穷 窯窑 窵窎 窶窭 窺窥 竄窜 竅窍 竇窦 竈灶 竊窃 竪竖 競竞 筆笔 筍笋 筧笕 箇个 箋笺 箏筝 節节 範范 築筑 篋箧 篔筼 篠筿 篤笃 篩筛 篳筚 簀箦 簍篓 簑蓑 簞箪 簡简 簣篑 簫箫 簹筜 簽签 簾帘 籃篮 籌筹 籙箓 籛篯 籜箨 籟籁 籠笼 籤签 籩笾 籪簖 籬篱 籮箩 籲吁 粵粤 糉粽 糝糁 糞粪 糧粮 糰团 糲粝 糴籴 糶粜 糹纟 糾纠 紀纪 紂纣 約约 紅红 紆纡 紇纥 紈纨 紉纫 紋纹 納纳 紐纽 紓纾 純纯 紕纰 紖纼 紗纱 紘纮 紙纸 級级 紛纷 紜纭 紝纴 紡纺 紮扎 細细 紱绂 紲绁 紳绅 紵纻 紹绍 紺绀 紼绋 紿绐 絀绌 終终 絃弦 組组 絆绊 絎绗 結结 絕绝 絛绦 絝绔 絞绞 絡络 絢绚 給给 絨绒 絰绖 統统 絲丝 絳绛 絶绝 絹绢 綁绑 綃绡 綆绠 綈绨 綉绣 綌绤 綏绥 綑捆 經经 綜综 綞缍 綠绿 綢绸 綣绻 綫线 綬绶 維维 綯绹 綰绾 綱纲 網网 綳绷 綴缀 綸纶 綹绺 綺绮 綻绽 綽绰 綾绫 綿绵 緄绲 緇缁 緊紧 緋绯 緑绿 緒绪 緓绬 緔绱 緗缃 緘缄 緙缂 線线 緝缉 緞缎 締缔 緡缗 緣缘 緦缌 編编 緩缓 緬缅 緯纬 緱缑 緲缈 練练 緶缏 緹缇 緻致 緼缊 縈萦 縉缙 縊缢 縋缒 縐绉 縑缣 縕缊 縗缞 縛缚 縝缜 縞缟 縟缛 縣县 縧绦 縫缝 縭缡 縮缩 縱纵 縲缧 縴纤 縵缦 縶絷 縷缕 縹缥 總总 績绩 繃绷 繅缫 繆缪 繒缯 織织 繕缮 繚缭 繞绕 繡绣 繢缋 繩绳 繪绘 繫系 繭茧 繮缰 繯缳 繰缲 繳缴 繹绎 繼继 繽缤 繾缱 纇颣 纈缬 纊纩 續续 纍累 纏缠 纓缨 纔才 纖纤 纘缵 纜缆 缽钵 罈坛 罌罂 罎坛 罰罚 罵骂 罷罢 羅罗 羆罴 羈羁 羋芈 羣群 羥羟 羨羡 義义 羶膻 習习 翫玩 翬翚 翹翘 翽翙 耬耧 耮耢 聖圣 聞闻 聯联 聰聪 聲声 聳耸 聵聩 聶聂 職职 聹聍 聽听 聾聋 肅肃 脅胁 脈脉 脛胫 脣唇 脩修 脫脱 脹胀 腎肾 腖胨 腡脶 腦脑 腫肿 腳脚 腸肠 膃腽 膕腘 膚肤 膠胶 膩腻 膽胆 膾脍 膿脓 臉脸 臍脐 臏膑 臘腊 臚胪 臟脏 臠脔 臢臜 臥卧 臨临 臺台 與与 興兴 舉举 舊旧 舘馆 艙舱 艤舣 艦舰 艫舻 艱艰 艷艳 芻刍 苧苎 茲兹 荊荆 莊庄 莖茎 莢荚 莧苋 華华 菴庵 菸烟 萇苌 萊莱 萬万 萴荝 萵莴 葉叶 葒荭 著着 葤荮 葦苇 葯药 葷荤 蒐搜 蒓莼 蒔莳 蒕蒀 蒞莅 蒼苍 蓀荪 蓆席 蓋盖 蓮莲 蓯苁 蓴莼 蓽荜 蔔卜 蔘参 蔞蒌 蔣蒋 蔥葱 蔦茑 蔭荫 蕁荨 蕆蒇 蕎荞 蕒荬 蕓芸 蕕莸 蕘荛 蕢蒉 蕩荡 蕪芜 蕭萧 蕷蓣 薀蕰 薈荟 薊蓟 薌芗 薑姜 薔蔷 薘荙 薟莶 薦荐 薩萨 薴苧 薺荠 藍蓝 藎荩 藝艺 藥药 藪薮 藴蕴 藶苈 藹蔼 藺蔺 蘀萚 蘄蕲 蘆芦 蘇苏 蘊蕴 蘚藓 蘞蔹 蘢茏 蘭兰 蘺蓠 蘿萝 虆蔂 處处 虛虚 虜虏 號号 虧亏 虯虬 蛺蛱 蛻蜕 蜆蚬 蝕蚀 蝟猬 蝦虾 蝨虱 蝸蜗 螄蛳 螞蚂 螢萤 螻蝼 螿螀 蟄蛰 蟈蝈 蟎螨 蟣虮 蟬蝉 蟯蛲 蟲虫 蟶蛏 蟻蚁 蠁蚃 蠅蝇 蠆虿 蠍蝎 蠐蛴 蠑蝾 蠔蚝 蠟蜡 蠣蛎 蠨蟏 蠱蛊 蠶蚕 蠻蛮 衆众 衊蔑 術术 衕同 衚胡 衛卫 衝冲 袞衮 裊袅 裏里 補补 裝装 裡里 製制 複复 褌裈 褘袆 褲裤 褳裢 褸褛 褻亵 襇裥 襉裥 襏袯 襖袄 襝裣 襠裆 襤褴 襪袜 襯衬 襲袭 襴襕 覈核 見见 覎觃 規规 覓觅 視视 覘觇 覡觋 覥觍 覦觎 親亲 覬觊 覯觏 覲觐 覷觑 覺觉 覽览 覿觌 觀观 觴觞 觶觯 觸触 訁讠 訂订 訃讣 計计 訊讯 訌讧 討讨 訐讦 訒讱 訓训 訕讪 訖讫 記记 訛讹 訝讶 訟讼 訣诀 訥讷 訩讻 訪访 設设 許许 訴诉 訶诃 診诊 註注 証证 詁诂 詆诋 詎讵 詐诈 詒诒 詔诏 評评 詖诐 詗诇 詘诎 詛诅 詞词 詠咏 詡诩 詢询 詣诣 試试 詩诗 詫诧 詬诟 詭诡 詮诠 詰诘 話话 該该 詳详 詵诜 詼诙 詿诖 誄诔 誅诛 誆诓 誇夸 誌志 認认 誑诳 誒诶 誕诞 誘诱 誚诮 語语 誠诚 誡诫 誣诬 誤误 誥诰 誦诵 誨诲 說说 説说 誰谁 課课 誶谇 誹诽 誼谊 誾訚 調调 諂谄 諄谆 談谈 諉诿 請请 諍诤 諏诹 諑诼 諒谅 論论 諗谂 諛谀 諜谍 諝谞 諞谝 諡谥 諢诨 諤谔 諦谛 諧谐 諭谕 諱讳 諳谙 諶谌 諷讽 諸诸 諺谚 諼谖 諾诺 謀谋 謁谒 謂谓 謄誊 謅诌 謊谎 謎谜 謐谧 謔谑 謖谡 謗谤 謙谦 謚谥 講讲 謝谢 謠谣 謡谣 謨谟 謫谪 謬谬 謭谫 謳讴 謹谨 謾谩 譁哗 證证 譎谲 譏讥 譖谮 識识 譙谯 譚谭 譜谱 譟噪 譫谵 譭毁 譯译 議议 譴谴 護护 譸诪 譽誉 讀读 讅谉 變变 讋詟 讎雠 讒谗 讓让 讕谰 讖谶 讚赞 讜谠 讞谳 豈岂 豎竖 豐丰 豔艳 豬猪 豶豮 貓猫 貝贝 貞贞 貟贠 負负 財财 貢贡 貧贫 貨货 販贩 貪贪 貫贯 責责 貯贮 貰贳 貲赀 貳贰 貴贵 貶贬 買买 貸贷 貺贶 費费 貼贴 貽贻 貿贸 賀贺 賁贲 賂赂 賃赁 賄贿 賅赅 資资 賈贾 賊贼 賑赈 賒赊 賓宾 賕赇 賙赒 賚赉 賜赐 賞赏 賠赔 賡赓 賢贤 賣卖 賤贱 賦赋 賧赕 質质 賫赍 賬账 賭赌 賴赖 賵赗 賺赚 賻赙 購购 賽赛 賾赜 贄贽 贅赘 贇赟 贈赠 贊赞 贋赝 贍赡 贏赢 贐赆 贓赃 贔赑 贖赎 贗赝 贛赣 贜赃 赬赪 趕赶 趙赵 趨趋 趲趱 跡迹 踐践 踰逾 踴踊 蹌跄 蹕跸 蹟迹 蹠跖 蹣蹒 蹤踪 蹺跷 躂跶 躉趸 躊踌 躋跻 躍跃 躑踯 躒跞 躓踬 躕蹰 躚跹 躡蹑 躥蹿 躦躜 躪躏 軀躯 車车 軋轧 軌轨 軍军 軑轪 軒轩 軔轫 軛轭 軟软 軤轷 軫轸 軲轱 軸轴 軹轵 軺轺 軻轲 軼轶 軾轼 較较 輅辂 輇辁 輈辀 載载 輊轾 輒辄 輓挽 輔辅 輕轻 輛辆 輜辎 輝辉 輞辋 輟辍 輥辊 輦辇 輩辈 輪轮 輬辌 輯辑 輳辏 輸输 輻辐 輼辒 輾辗 輿舆 轀辒 轂毂 轄辖 轅辕 轆辘 轉转 轍辙 轎轿 轔辚 轟轰 轡辔 轢轹 轤轳 辦办 辭辞 辮辫 辯辩 農农 迴回 逕迳 這这 連连 週周 進进 遊游 運运 過过 達达 違违 遙遥 遜逊 遞递 遠远 遡溯 適适 遲迟 遷迁 選选 遺遗 遼辽 邁迈 還还 邇迩 邊边 邏逻 邐逦 郟郏 郵邮 鄆郓 鄉乡 鄒邹 鄔邬 鄖郧 鄧邓 鄭郑 鄰邻 鄲郸 鄴邺 鄶郐 鄺邝 酇酂 酈郦 醃腌 醖酝 醜丑 醞酝 醟蒏 醣糖 醫医 醬酱 醱酦 釀酿 釁衅 釃酾 釅酽 釋释 釐厘 釒钅 釓钆 釔钇 釕钌 釗钊 釘钉 釙钋 針针 釣钓 釤钐 釦扣 釧钏 釩钒 釵钗 釷钍 釹钕 釺钎 鈀钯 鈁钫 鈃钘 鈄钭 鈅钥 鈈钚 鈉钠 鈍钝 鈎钩 鈐钤 鈑钣 鈒钑 鈔钞 鈕钮 鈞钧 鈡钟 鈣钙 鈥钬 鈦钛 鈧钪 鈮铌 鈰铈 鈳钶 鈴铃 鈷钴 鈸钹 鈹铍 鈺钰 鈽钸 鈾铀 鈿钿 鉀钾 鉆钻 鉈铊 鉉铉 鉋铇 鉍铋 鉑铂 鉕钷 鉗钳 鉚铆 鉛铅 鉞钺 鉢钵 鉤钩 鉦钲 鉬钼 鉭钽 鉳锫 鉶铏 鉸铰 鉺铒 鉻铬 鉿铪 銀银 銃铳 銅铜 銍铚 銑铣 銓铨 銖铢 銘铭 銚铫 銛铦 銜衔 銠铑 銣铷 銥铱 銦铟 銨铵 銩铥 銪铕 銫铯 銬铐 銱铞 銳锐 銷销 銹锈 銻锑 銼锉 鋁铝 鋃锒 鋅锌 鋇钡 鋌铤 鋏铗 鋒锋 鋙铻 鋝锊 鋟锓 鋣铘 鋤锄 鋥锃 鋦锔 鋨锇 鋩铓 鋪铺 鋭锐 鋮铖 鋯锆 鋰锂 鋱铽 鋶锍 鋸锯 鋼钢 錁锞 錄录 錆锖 錇锫 錈锩 錏铔 錐锥 錒锕 錕锟 錘锤 錙锱 錚铮 錛锛 錟锬 錠锭 錡锜 錢钱 錦锦 錨锚 錩锠 錫锡 錮锢 錯错 録录 錳锰 錶表 錸铼 錼镎 鍀锝 鍁锨 鍃锪 鍅钫 鍆钔 鍇锴 鍈锳 鍋锅 鍍镀 鍔锷 鍘铡 鍚钖 鍛锻 鍠锽 鍤锸 鍥锲 鍩锘 鍬锹 鍰锾 鍵键 鍶锶 鍺锗 鍼针 鎂镁 鎄锿 鎇镅 鎊镑 鎌镰 鎔镕 鎖锁 鎘镉 鎚锤 鎛镈 鎡镃 鎢钨 鎣蓥 鎦镏 鎧铠 鎩铩 鎪锼 鎬镐 鎭镇 鎮镇 鎰镒 鎲镋 鎳镍 鎵镓 鎶鿔 鎸镌 鎿镎 鏃镞 鏈链 鏌镆 鏍镙 鏐镠 鏑镝 鏗铿 鏘锵 鏜镗 鏝镘 鏞镛 鏟铲 鏡镜 鏢镖 鏤镂 鏨錾 鏰镚 鏵铧 鏷镤 鏹镪 鏽锈 鐃铙 鐋铴 鐐镣 鐒铹 鐓镦 鐔镡 鐘钟 鐙镫 鐝镢 鐠镨 鐦锎 鐧锏 鐨镄 鐫镌 鐮镰 鐲镯 鐳镭 鐵铁 鐶镮 鐸铎 鐺铛 鐿镱 鑄铸 鑊镬 鑌镔 鑑鉴 鑒鉴 鑔镲 鑕锧 鑞镴 鑠铄 鑣镳 鑥镥 鑭镧 鑰钥 鑱镵 鑲镶 鑷镊 鑹镩 鑼锣 鑽钻 鑾銮 鑿凿 钂镋 長长 門门 閂闩 閃闪 閆闫 閈闬 閉闭 開开 閌闶 閎闳 閏闰 閑闲 間间 閔闵 閘闸 閡阂 閣阁 閤合 閥阀 閨闺 閩闽 閫阃 閬阆 閭闾 閱阅 閲阅 閶阊 閹阉 閻阎 閼阏 閽阍 閾阈 閿阌 闃阒 闆板 闇暗 闈闱 闊阔 闋阕 闌阑 闍阇 闐阗 闒阘 闓闿 闔阖 闕阙 闖闯 關关 闞阚 闠阓 闡阐 闢辟 闤阛 闥闼 陘陉 陝陕 陞升 陣阵 陰阴 陳陈 陸陆 陽阳 隉陧 隊队 階阶 隕陨 際际 隨随 險险 隯陦 隱隐 隴陇 隸隶 隻只 雋隽 雖虽 雙双 雛雏 雜杂 雞鸡 離离 難难 雲云 電电 霑沾 霢霡 霧雾 霽霁 靂雳 靄霭 靆叇 靈灵 靉叆 靚靓 靜静 靝靔 靨靥 鞏巩 鞝绱 鞦秋 鞽鞒 韁缰 韃鞑 韆千 韉鞯 韋韦 韌韧 韍韨 韓韩 韙韪 韜韬 韞韫 韻韵 響响 頁页 頂顶 頃顷 項项 順顺 頇顸 須须 頊顼 頌颂 頎颀 頏颃 預预 頑顽 頒颁 頓顿 頗颇 領领 頜颌 頡颉 頤颐 頦颏 頭头 頮颒 頰颊 頲颋 頴颕 頷颔 頸颈 頹颓 頻频 頽颓 顆颗 題题 額额 顎颚 顏颜 顒颙 顓颛 顔颜 顙颡 顛颠 類类 顢颟 顥颢 顧顾 顫颤 顬颥 顯显 顰颦 顱颅 顳颞 顴颧 風风 颭飐 颮飑 颯飒 颱台 颳刮 颶飓 颸飔 颺飏 颻飖 颼飕 飀飗 飄飘 飆飙 飈飚 飛飞 飠饣 飢饥 飣饤 飥饦 飩饨 飪饪 飫饫 飭饬 飯饭 飱飧 飲饮 飴饴 飼饲 飽饱 飾饰 飿饳 餃饺 餄饸 餅饼 餈糍 餉饷 養养 餌饵 餎饹 餏饻 餑饽 餒馁 餓饿 餕馂 餖饾 餘余 餚肴 餛馄 餜馃 餞饯 餡馅 館馆 餳饧 餶馉 餷馇 餺馎 餼饩 餾馏 餿馊 饁馌 饃馍 饅馒 饈馐 饉馑 饊馓 饋馈 饌馔 饑饥 饒饶 饗飨 饜餍 饞馋 饢馕 馬马 馭驭 馮冯 馱驮 馳驰 馴驯 馹驲 駁驳 駐驻 駑驽 駒驹 駔驵 駕驾 駘骀 駙驸 駛驶 駝驼 駟驷 駡骂 駢骈 駭骇 駰骃 駱骆 駸骎 駿骏 騁骋 騂骍 騅骓 騌骔 騍骒 騎骑 騏骐 騖骛 騙骗 騤骙 騫骞 騭骘 騮骝 騰腾 騶驺 騷骚 騸骟 騾骡 驀蓦 驁骜 驂骖 驃骠 驅驱 驊骅 驌骕 驍骁 驏骣 驕骄 驗验 驚惊 驛驿 驟骤 驢驴 驤骧 驥骥 驦骦 驪骊 驫骉 骯肮 髏髅 髒脏 體体 髕髌 髖髋 髮发 鬆松 鬍胡 鬚须 鬢鬓 鬥斗 鬧闹 鬨哄 鬩阋 鬮阄 鬱郁 鬹鬶 魎魉 魘魇 魚鱼 魛鱽 魢鱾 魨鲀 魯鲁 魴鲂 魷鱿 魺鲄 鮁鲅 鮃鲆 鮊鲌 鮋鲉 鮍鲏 鮎鲇 鮐鲐 鮑鲍 鮒鲋 鮓鲊 鮚鲒 鮜鲘 鮝鲞 鮞鲕 鮦鲖 鮪鲔 鮫鲛 鮭鲑 鮮鲜 鮳鲓 鮶鲪 鮺鲝 鯀鲧 鯁鲠 鯇鲩 鯉鲤 鯊鲨 鯒鲬 鯔鲻 鯕鲯 鯖鲭 鯗鲞 鯛鲷 鯝鲴 鯡鲱 鯢鲵 鯤鲲 鯧鲳 鯨鲸 鯪鲮 鯫鲰 鯰鲶 鯴鲺 鯷鳀 鯽鲫 鯿鳊 鰁鳈 鰂鲗 鰃鳂 鰈鲽 鰉鳇 鰍鳅 鰏鲾 鰐鳄 鰒鳆 鰓鳃 鰛鳁 鰜鳒 鰟鳑 鰠鳋 鰣鲥 鰥鳏 鰨鳎 鰩鳐 鰭鳍 鰮鳁 鰱鲢 鰲鳌 鰳鳓 鰵鳘 鰷鲦 鰹鲣 鰺鲹 鰻鳗 鰼鳛 鰾鳔 鱂鳉 鱅鳙 鱈鳕 鱉鳖 鱒鳟 鱔鳝 鱖鳜 鱗鳞 鱘鲟 鱝鲼 鱟鲎 鱠鲙 鱣鳣 鱤鳡 鱧鳢 鱨鲿 鱭鲚 鱯鳠 鱷鳄 鱸鲈 鱺鲡 鳥鸟 鳧凫 鳩鸠 鳬凫 鳲鸤 鳳凤 鳴鸣 鳶鸢 鴆鸩 鴇鸨 鴉鸦 鴒鸰 鴕鸵 鴛鸳 鴝鸲 鴞鸮 鴟鸱 鴣鸪 鴦鸯 鴨鸭 鴯鸸 鴰鸹 鴴鸻 鴻鸿 鴿鸽 鵂鸺 鵃鸼 鵐鹀 鵑鹃 鵒鹆 鵓鹁 鵜鹈 鵝鹅 鵠鹄 鵡鹉 鵪鹌 鵬鹏 鵮鹐 鵯鹎 鵲鹊 鵷鹓 鵾鹍 鶇鸫 鶉鹑 鶊鹒 鶓鹋 鶖鹙 鶘鹕 鶚鹗 鶡鹖 鶥鹛 鶩鹜 鶬鸧 鶯莺 鶲鹟 鶴鹤 鶹鹠 鶺鹡 鶻鹘 鶼鹣 鶿鹚 鷀鹚 鷁鹢 鷂鹞 鷄鸡 鷊鹝 鷓鹧 鷖鹥 鷗鸥 鷙鸷 鷚鹨 鷥鸶 鷦鹪 鷫鹔 鷯鹩 鷲鹫 鷳鹇 鷴鹇 鷸鹬 鷹鹰 鷺鹭 鷽鸴 鸇鹯 鸌鹱 鸏鹲 鸕鸬 鸘鹴 鸚鹦 鸛鹳 鸝鹂 鸞鸾 鹵卤 鹹咸 鹺鹾 鹼碱 鹽盐 麗丽 麥麦 麩麸 麫面 麯曲 麼么 黃黄 黌黉 點点 黨党 黲黪 黴霉 黶黡 黷黩 黽黾 黿鼋 鼂鼌 鼉鼍 鼕冬 鼴鼹 齊齐 齋斋 齎赍 齏齑 齒齿 齔龀 齕龁 齗龂 齙龅 齜龇 齟龃 齠龆 齡龄 齣出 齦龈 齪龊 齬龉 齲龋 齶腭 齷龌 龍龙 龎厐 龐庞 龔龚 龕龛 龜龟 鿓鿒";
var _T2S = {};
_T2S_PAIRS.split(' ').forEach(function (p) { _T2S[p[0]] = p[1]; });
function _t2s(s) {
  return String(s || '').replace(/./g, function (ch) { return _T2S[ch] || ch; });
}
function _hlExtractScene(q) {
  var s = String(q || '');
  /* R229j：交替顺序约束——「X周末」复合词必须先于裸「本周/这周/周末」，
   * 否则「打算这周末…」被剥成「末…」；裸曜日（周五/礼拜天）殿后。 */
  s = s.replace(/(大后[天日]|大後天|后[天日]|後天|明晚|后晚|後晚|今晚|昨晚|今夜|明[天日]|明[儿兒]|明日|今[天日]|今日|昨[天日]|大前[天日]|前[天日]|过[两兩][天日]|这两天|这几天|那几天|那一天|那天|这一天|这天|最近|哪天|几时|几号|何时|啥时候|什么时候|(本周|这周|本週|這週|这週|這周)[一二三四五六日天]|(本|这|這|下)个?(周|週|礼拜|禮拜)末|(本|这|這|下)個(周|週|礼拜|禮拜)末|本周|这周|本週|這週|这週|這周|周末|週末|下下个?(周|週|礼拜|禮拜)[一二三四五六日天]|下下個(周|週|礼拜|禮拜)[一二三四五六日天]|下下个?(周|週|礼拜|禮拜)末|下下個(周|週|礼拜|禮拜)末|下下个?(周|週|礼拜|禮拜)|下下個(周|週|礼拜|禮拜)|下个?(周|週|礼拜|禮拜)[一二三四五六日天]|下個(周|週|礼拜|禮拜)[一二三四五六日天]|下个?(周|週|礼拜|禮拜)|下個(周|週|礼拜|禮拜)|上个?(周|週|礼拜|禮拜|星期)末|上個(周|週|礼拜|禮拜|星期)末|上个?(周|週|礼拜|禮拜|星期)[一二三四五六日天]|上個(周|週|礼拜|禮拜|星期)[一二三四五六日天]|上个?(周|週|礼拜|禮拜|星期)|上個(周|週|礼拜|禮拜|星期)|上个月|上個月|上月|(周|週|礼拜|禮拜|星期)[一二三四五六日天]|一大早|凌晨|早上|上午|中午|下午|傍晚|晚上|夜里|白天|现在|当下|前年|去年|今年|明年|后年|後年|往年)/g, '');
  /* R229z：新日期词也要剥——节日/农历/绝对日期/月内相对/前后缀，
   * 否则「国庆节前一天摆摊」会残成「国庆节前一天摆摊」。 */
  s = s.replace(/(农历|農曆|阴历|陰曆|旧历|舊曆)?(闰|閏)?[正一二两三四五六七八九十冬腊\d]{1,2}月[初廿一二三四五六七八九十\d]{1,3}[日号]?/g, '');
  /* R3230：数字相对日同步剥——「三天后搬家/一周后签约」残词会混进
   * 场景提取（与后端同日进 resolve_date，前端剥干净场景词才纯）。 */
  s = s.replace(/(过|過)?([0-9]{1,3}|[一二两三四五六七八九兩十半]{1,3})[个個]?(天|日|周|週|星期|礼拜|禮拜)(后|後|前)|([0-9]{1,2}|[一二两三四五六七八九兩十半]{1,3})[个個]月(后|後|前)|(过|過)[0-9一二两三四五六七八九兩十]{1,3}[个個]?(天|日|周|週|星期|礼拜|禮拜)/g, '');
  s = s.replace(/(除夕|春节|春節|大年初一|元宵节|元宵節|端午节|端午節|端午|七夕|中秋节|中秋節|中秋|重阳节|重陽節|重阳|重陽|腊八节|臘八節|腊八|臘八|清明节|清明節|清明|立春|雨水|惊蛰|驚蟄|春分|谷雨|穀雨|立夏|芒种|芒種|夏至|立秋|处暑|處暑|白露|秋分|寒露|霜降|立冬|冬至|大暑|小暑|元旦|新年|情人节|情人節|妇女节|婦女節|植树节|植樹節|愚人节|愚人節|劳动节|勞動節|青年节|青年節|儿童节|兒童節|建党节|建黨節|建军节|建軍節|教师节|教師節|国庆节|國慶節|国庆|國慶|万圣节|萬聖節|平安夜|圣诞节|聖誕節|圣诞|聖誕|跨年|母亲节|母親節|父亲节|父親節|感恩节|感恩節|中元节|中元節|中元|小年|双十一|雙十一|光棍节|光棍節|月底|月末|月初|下个?月|上个?月|这个?月|\d{1,2}\s*[月\/\-.]\s*\d{1,2}\s*[日号]?|\d{1,2}\s*[号日])(的?前[一二三四五六两]?[天日]?|的?后[一二三四五六两]?[天日]?|之前|之后|当天|当日)?/g, '');
  /* 多字节后缀（前一天/次日/的后三天…）总是日期修饰，无锚直接剥；
   * 裸「前/后」只在串尾剥（「前后矛盾」是真词）。 */
  s = s.replace(/(前一天|前两天|前三天|头一天|头两天|的后?一?两?三天|的后两天|之后|后一天|后两天|次日|第二天|当天|当日)/g, '');
  s = s.replace(/[前后]$/, '');
  s = s.replace(/^(我|我们|咱|俺)?\s*((想|想要|打算|准备|计划|要|去|做|搞|弄|干|知道|看看|问问|问下|求问|感觉|感到|觉得)+)/, '');
  /* R2349（R64-P1-2）：modal 补 要不要/该不该/想不想——「要不要提分手」
   * 此前剥不掉「要不要」，整串>6 字清空落中性卡。 */
  s = s.replace(/(适不适合|可不可以|能不能|行不行|宜不宜|好不好|合不合适|吉利不吉利|要不要|该不该|想不想|适合|可以|能|宜|吉利|合适|稳妥|怎么样|怎么办|咋办|行吗|如何|的话|好吗)/g, '');
  /* 「地」不进助词表——「外地/地铁」是真字；连接词单独剥。 */
  s = s.replace(/[吗呢吧啊呀？?!！!，,。.、~～\s的了]/g, '');
  /* 「去/到」不进全局表——「去年→年」「到家→家」是真字伤害；句首/能后的
   * 「去爬山」由上行引导剥离覆盖。 */
  s = s.replace(/(帮|给|跟|和|与|向|让|为|个|只|把|被|在)/g, '');
  s = s.replace(/^(去|做|干|搞)+/, '');
  /* R2349（R64-P1-2）：口语尾巴字先剥再量长——「去拜拜好/终面成」
   * 的 好/成/顺 此前顶破 6 字上限整串清空。 */
  s = s.replace(/(顺利|冲不冲|行不行|好不好|成不成|顺|灵|好|成|过)+$/, '');
  if (s.length > 6) s = '';
  if (/^(黄历|老黄历|看黄历|查黄历|看日子|挑日子|啥|什么|怎么|怎样|怎么样|运势|运气|日子|吉日|现在)$/.test(s)) s = '';
  return s;
}
/* R227b-fix：问一嘴输入里的日期词必须真生效——「明天适合出行吗」要判
 * 明天的黄历，不能剥掉日期词后拿当前显示日充数（审查抓到：9/19 页面上
 * 问「明天」却答「今天不宜」，而 9/20 其实宜）。与 services._hl_day_part
 * 同口径（+1/+2/+3）；返回 null = 没带日期词，按当前显示日判。 */
function _wdIdx(ch) {
  var i = '一二三四五六日天'.indexOf(ch);
  return i > 6 ? 6 : i;   /* 日/天 同为周日（天 index=7，%7 会错成周一） */
}
function _hlDayOffset(q, base) {
  var s = String(q || '');
  if (/大(后|後)[天日]/.test(s)) return 3;
  if (/大前[天日]/.test(s)) return -3;
  if (/(后|後)[天日]/.test(s) || /过(两|兩)[天日]/.test(s)) return 2;
  if (/明[天日]|明日|明[儿兒]/.test(s)) return 1;
  if (/今[天日]|今日/.test(s)) return 0;
  if (/昨[天日]|昨日/.test(s)) return -1;
  if (/前[天日]|前日/.test(s)) return -2;
  /* R229h/m：晚字辈与对应「天」同档（黄历按天判）——services._hl_day_part
   * 同口径；probe_date_parity 钉扎两侧一致性。 */
  if (/明晚/.test(s)) return 1;
  if (/(后|後)晚/.test(s)) return 2;
  if (/今晚|今夜/.test(s)) return 0;
  if (/昨晚/.test(s)) return -1;
  /* R229z：公历绝对日期「10月1日/9-25/25号/下个月5号/月底」——就近取
   * （当年/当月未过取当年；已过无语标顺下一档；语标「那天/过了…」落已过）。
   * 节日与农历（中秋/春节/农历八月十五…）本地解不动——提交路径识别后走
   * /api/huangli/resolve_date 端点（单点真相在后端）。 */
  var _s0 = _t2s(s);
  /* R2355（R111-P1-3）：显式 4 位年（2027-02-29 / 2099年12月31号）
   * 本地不猜——M-D 残片正则会把 ISO 里的 '27-02' 吃成乱日。带年号
   * 的串一律交 /api/huangli/resolve_date（后端按显式年锚定，越界
   * 判「黄历里没有这天」）。 */
  if (/\d{4}\s*[-\/.]|\d{4}\s*年/.test(_s0)) return null;
  var _past = /(那天|过了|已经|当时|去了)/.test(_s0);
  /* 「去年/明年/前年/后年」年前缀约束候选年（与 py yoff 同口径）。 */
  var _yoff = null;
  var _ypre = [['前年',-2],['去年',-1],['今年',0],['明年',1],['后年',2]];
  for (var _yi = 0; _yi < _ypre.length; _yi++) {
    if (_s0.indexOf(_ypre[_yi][0]) !== -1) { _yoff = _ypre[_yi][1]; break; }
  }
  /* 越界日期（2/30）回 null，对齐 py 的 ValueError 跳过——JS Date 会
   * 静默进位到 3/2，必须校验。月参数允许 >11（自然跨年/月下月）。 */
  var _mkd = function (y, m, d) {
    var t = new Date(y, m, d);
    return t.getDate() === d ? t : null;
  };
  /* R3366（审-P1）：中文复合数字日「十五/二十/三十一」（与 py
   * _cn_day_int 同口径——单中文数字不接，邻接歧义大）。 */
  var _cnDay = function (s) {
    if (/^\d+$/.test(s)) return +s;
    var D = {'一':1,'二':2,'两':2,'兩':2,'三':3,'四':4,'五':5,'六':6,'七':7,'八':8,'九':9};
    var m = s.match(/^([一二三])?十([一二三四五六七八九])?$/);
    if (m) return (m[1] ? D[m[1]] : 1) * 10 + (m[2] ? D[m[2]] : 0);
    return NaN;
  };
  var _pick = function (cands) {   /* cands: [Date|null,...] → 偏移 | null */
    var t = base || new Date(); t = new Date(t.getFullYear(), t.getMonth(), t.getDate());
    var best = null, bestPast = null;
    for (var i = 0; i < cands.length; i++) {
      if (!cands[i]) continue;
      var off = Math.round((cands[i] - t) / 86400000);
      if (off >= 0 && (best === null || off < best)) best = off;
      if (off <= 0 && (bestPast === null || off > bestPast)) bestPast = off;
    }
    if (_past) return bestPast !== null ? bestPast : best;
    return best !== null ? best : bestPast;
  };
  /* 日期词后缀「前一天/后/次日…」→ [偏移, 吃掉字符数]（与 py _day_suffix
   * 同表）。hit 为匹配对象时取其 end 位置。 */
  var _suf = function (mEnd) {
    var tail = _s0.slice(mEnd, mEnd + 6);
    var rules = [['大前天',-3],['的前三天',-3],['后第三天',3],
                 ['后的第三天',3],['的后三天',3],['前三天',-3],
                 ['的前三天',-3],['前两天',-2],['头两天',-2],
                 ['的前两天',-2],['后第二天',2],['的第二天',2],
                 ['后两天',2],['前一天',-1],['头一天',-1],['的前一天',-1],
                 ['之后',1],['次日',1],['第二天',1],['后一天',1],
                 ['之前',-1]];
    for (var i = 0; i < rules.length; i++) {
      if (tail.indexOf(rules[i][0]) === 0) return rules[i][1];
    }
    if (/^前/.test(tail)) return -1;
    if (/^后/.test(tail)) return 1;
    return 0;
  };
  /* R2355（R111-P2-2）：「下下个月」先接——「下下」里的「下个月」
   * 会被下面通配截胡差整一月（与 py nnm 同锚）。 */
  var _nnm = _s0.match(/下下个?月(\d{1,2}|[一二三]?十[一二三四五六七八九]?)[号日]?(?![线楼室幢座栋层院门])/);
  if (_nnm) {
    var bN0 = base || new Date();
    var _o0 = _pick([_mkd(bN0.getFullYear(), bN0.getMonth() + 2, _cnDay(_nnm[1]))]);
    return _o0 === null ? null : _o0 + _suf(_nnm.index + _nnm[0].length);
  }
  var _nxm = _s0.match(/下[个个]月(\d{1,2}|[一二三]?十[一二三四五六七八九]?)[号日]?(?![线楼室幢座栋层院门])/);
  if (_nxm) {
    var bN = base || new Date();
    var _o1 = _pick([_mkd(bN.getFullYear(), bN.getMonth() + 1, _cnDay(_nxm[1]))]);
    return _o1 === null ? null : _o1 + _suf(_nxm.index + _nxm[0].length);
  }
  var _pm = _s0.match(/上[个个]月(\d{1,2}|[一二三]?十[一二三四五六七八九]?)[号日]?(?![线楼室幢座栋层院门])/);
  if (_pm) {
    var bP = base || new Date();
    var _o2 = _pick([_mkd(bP.getFullYear(), bP.getMonth() - 1, _cnDay(_pm[1]))]);
    return _o2 === null ? null : _o2 + _suf(_pm.index + _pm[0].length);
  }
  var _tsm = _s0.match(/这[个个]月(\d{1,2}|[一二三]?十[一二三四五六七八九]?)[号日]?(?![线楼室幢座栋层院门])/);
  if (_tsm) {
    var bT = base || new Date();
    var _o3 = _pick([_mkd(bT.getFullYear(), bT.getMonth(), _cnDay(_tsm[1]))]);
    return _o3 === null ? null : _o3 + _suf(_tsm.index + _tsm[0].length);
  }
  var _am = _s0.match(/(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?(?![线楼室幢座栋层院门])/) ||
            _s0.match(/(\d{1,2})\s*[\/.-](\d{1,2})/);
  if (_am) {
    var bA = base || new Date();
    var _ys = [bA.getFullYear(), bA.getFullYear() + 1, bA.getFullYear() - 1];
    if (_yoff !== null) _ys = [bA.getFullYear() + _yoff];
    var _o4 = _pick(_ys.map(function (y) {
      return _mkd(y, +_am[1] - 1, +_am[2]); }));
    return _o4 === null ? null : _o4 + _suf(_am.index + _am[0].length);
  }
  /* 「腊月底/正月末」走农历月末（后端解），这里返回 null 交兜底；
   * 「月初」后随农历日字（初一/十五）时不是月初——「五月初一」。 */
  if (/(农历|農曆|阴历|陰曆|旧历|舊曆)?(闰|閏)?[正冬腊一二两三四五六七八九十]{1,2}月(底|末)/.test(_s0)
      && /[正冬腊]|农|農|阴|陰|旧|舊|闰|閏/.test(_s0)) return null;
  var _me = _s0.match(/月底|月末/);
  if (_me) {
    var bE = base || new Date();
    var _o5 = _pick([new Date(bE.getFullYear(), bE.getMonth() + 1, 0),
                     new Date(bE.getFullYear(), bE.getMonth() + 2, 0)]);
    return _o5 === null ? null : _o5 + _suf(_me.index + 2);
  }
  var _ms = _s0.match(/月初(?!一|二|两|三|四|五|六|七|八|九|十|廿|\d)/);
  if (_ms) {
    var bS = base || new Date();
    var _o6 = _pick([new Date(bS.getFullYear(), bS.getMonth() + 1, 1),
                     new Date(bS.getFullYear(), bS.getMonth(), 1)]);
    return _o6 === null ? null : _o6 + _suf(_ms.index + 2);
  }
  /* 裸「D号」：防「3号线/25号楼/8号院」误命中（与 py 同邻接字表）。 */
  var _bd = _s0.match(/(^|[^\d月\/\-一二两三四五六七八九十])(\d{1,2}|[一二三]?十[一二三四五六七八九]?)\s*[号日](?![\d日线楼室幢座栋层院门])/);
  if (_bd) {
    var bB = base || new Date();
    var _o7 = _pick([_mkd(bB.getFullYear(), bB.getMonth(), _cnDay(_bd[2])),
                     _mkd(bB.getFullYear(), bB.getMonth() + 1, _cnDay(_bd[2]))]);
    return _o7 === null ? null : _o7 + _suf(_bd.index + _bd[0].length);
  }
  /* R229f：「本周X/这周X」此前无解析静默按今天判（同 R228r 类）。
   * R2349q续：个/個 可选字（这个周五/這個週三同锚）。 */
  var mw = s.match(/(本个?周|这个?周|本个?週|這个?週|这个?週|這个?周|本個周|這個週|這個周)([一二三四五六日天])/);
  if (mw) {
    var wdw = _wdIdx(mw[2]);
    var bw = base || new Date();
    return wdw - ((bw.getDay() + 6) % 7);       /* 可负——本周已过的日子 */
  }
  /* R229y续：「下下周X/下下周末」——"下下周一"自身含"下周"，会被下面
   * 通配截胡差整 7 天。先接住：以「再下一个周一」为基准。 */
  if (/下下个?(周|週|礼拜|禮拜)末|下下個(周|週|礼拜|禮拜)末/.test(s)) {
    var bn0 = base || new Date();
    return (14 - ((bn0.getDay() + 6) % 7)) + 5; /* 再下周一 +5 */
  }
  var mn = s.match(/下下个?(周|週|礼拜|禮拜)([一二三四五六日天])|下下個(周|週|礼拜|禮拜)([一二三四五六日天])/);
  if (mn) {
    var wdn = _wdIdx(mn[2] || mn[4]);
    var bn = base || new Date();
    return (14 - ((bn.getDay() + 6) % 7)) + wdn;
  }
  if (/下下个?(周|週|礼拜|禮拜)|下下個(周|週|礼拜|禮拜)/.test(s)) {
    var bn2 = base || new Date();
    return 14 - ((bn2.getDay() + 6) % 7);         /* 「下下周」→ 再下周一 */
  }
  /* R229e：「下周末/下週末」必须先于「下周」通配——否则被吃成下周一，
   * 而用户说的是下周的周六。R2349q续：个/個 可选字。 */
  if (/下个?(周|週|礼拜|禮拜)末|下個(周|週|礼拜|禮拜)末/.test(s)) {
    var b0 = base || new Date();
    return (7 - ((b0.getDay() + 6) % 7)) + 5;   /* 下个周一 +5 = 下周六 */
  }
  /* 下周X / 下礼拜X：以下个周一为基准的曜日偏移（对齐服务端口径）。 */
  var m = s.match(/下个?(周|週|礼拜|禮拜)([一二三四五六日天])|下個(周|週|礼拜|禮拜)([一二三四五六日天])/);
  if (m) {
    var wd = _wdIdx(m[2] || m[4]);
    var b = base || new Date();
    var todayWd = (b.getDay() + 6) % 7;           /* 周一=0 */
    return (7 - todayWd) + wd;
  }
  if (/下个?(周|週|礼拜|禮拜)|下個(周|週|礼拜|禮拜)/.test(s)) {
    var b2 = base || new Date();
    return 7 - ((b2.getDay() + 6) % 7);           /* 「下周」→ 下个周一 */
  }
  /* R2349q（R82-P0-1）：「上周X/上礼拜X/上周末」与后端同锚——
   * 此前走裸曜日分支落到未来的同名日（差整一周），后端同步修。
   * 个/個 为可选字（上个周六/上個週末同锚）。 */
  if (/上个?(周|週|礼拜|禮拜|星期)末|上個(周|週|礼拜|禮拜|星期)末/.test(s)) {
    var lb0 = base || new Date();
    return -(7 + ((lb0.getDay() + 6) % 7)) + 5;   /* 上周一 +5 = 上周六 */
  }
  var mlw = s.match(/上个?(周|週|礼拜|禮拜|星期)([一二三四五六日天])|上個(周|週|礼拜|禮拜|星期)([一二三四五六日天])/);
  if (mlw) {
    var wdl = _wdIdx(mlw[2] || mlw[4]);
    var lb = base || new Date();
    return -(7 + ((lb.getDay() + 6) % 7)) + wdl;
  }
  if (/上个?(周|週|礼拜|禮拜|星期)|上個(周|週|礼拜|禮拜|星期)/.test(s)) {
    var lb2 = base || new Date();
    return -(7 + ((lb2.getDay() + 6) % 7));       /* 「上周」→ 上周一 */
  }
  /* R2349q（R82-P0-1 连带）：「上个月/上月」→ 上月 1 号代表日。 */
  if (/上个月|上個月|上月/.test(s)) {
    var pm0 = base || new Date();
    var _pmS = new Date(pm0.getFullYear(), pm0.getMonth() - 1, 1);
    return Math.round((_pmS - new Date(pm0.getFullYear(), pm0.getMonth(), pm0.getDate())) / 86400000);
  }
  /* R2349（R64-P0-A）：周末口径与后端对齐——今天已是周末（六/日）
   * 就指今天；原式周日算出 +6 整段跳下周六，与小满判出相反日子
   * （同日两链互斥实测）。 */
  if (/周末|週末/.test(s)) {
    var b3 = base || new Date();
    var _w3 = (b3.getDay() + 6) % 7;              /* 周一=0 … 周日=6 */
    return _w3 >= 5 ? 0 : (5 - _w3 + 7) % 7;
  }
  /* R2349（R64-P1-4）：「年底/年末/岁尾」→ 当年 12/31 代表日；
   * 12 月下旬后说「年底」多半指明年收尾，顺下一年（与 py 同口径）。 */
  if (/年底|年末|岁尾/.test(s)) {
    var bY = base || new Date();
    var _ey = bY.getFullYear() +
      ((bY.getMonth() + 1 > 12 || (bY.getMonth() + 1 === 12 && bY.getDate() > 20)) ? 1 : 0);
    var _eT = new Date(_ey, 11, 31);
    return Math.round((_eT - new Date(bY.getFullYear(), bY.getMonth(), bY.getDate())) / 86400000);
  }
  /* R2349（R64-P1-4）：「生日」——存过档案就翻下一次生日；没存回 null，
   * 由提交端明说解不动（静默按今天判是实测 P1）。 */
  if (/生日|生辰/.test(s)) {
    var _meR = (typeof _meGet === 'function') ? _meGet('me') : null;
    if (_meR && _meR.m && _meR.d) {
      var bB2 = base || new Date();
      var _bd0 = new Date(bB2.getFullYear(), bB2.getMonth(), bB2.getDate());
      var _bc = _bdayInYear(_meR.m, _meR.d, bB2.getFullYear());
      if (_bc < _bd0) _bc = _bdayInYear(_meR.m, _meR.d, bB2.getFullYear() + 1);
      return Math.round((_bc - _bd0) / 86400000);
    }
    window.__hlBirthdayNA = true;
    return null;
  }
  /* R229h：裸曜日「周五/礼拜天/星期日」= 最近的那个（今天命中即今天=0）。
   * 下X/本周X 已在上面消化，这里只剩无前缀写法。 */
  var mb = s.match(/(周|週|礼拜|禮拜|星期)([一二三四五六日天])/);
  if (mb) {
    var wdb = _wdIdx(mb[2]);
    var bb = base || new Date();
    return ((wdb - ((bb.getDay() + 6) % 7)) + 7) % 7;
  }
  return null;
}
/* 判定卡里的日词：偏移/chip/自选日都映射成一个说法，文案不再写死「今天」。 */
function _hlDayWord(off) {
  var M = { '-2': '前天', '-1': '昨天', 0: '今天', 1: '明天', 2: '后天', 3: '大后天' };
  return (off != null && M[String(off)] != null) ? M[String(off)] : '那天';
}
/* R2349n（R77-P0-1）：conflict + conflict_family 合并去重——判词/提示/chip 共用。 */
function _hlMergedConflict(j) {
  var out = [];
  (Array.isArray(j && j.conflict) ? j.conflict : [])
    .concat(Array.isArray(j && j.conflict_family) ? j.conflict_family : [])
    .forEach(function (w) { if (out.indexOf(w) === -1) out.push(w); });
  return out;
}
function _hlNoSceneNote(yi, ji, day, conflict) {
  /* R228c：「没直接管」生硬且与后端口径不齐，统一「没直接提」。
   * R230h（R20-F7）：相冲词摘出主推行（与 _hlVerdictHtml 同款）。 */
  var _cfl = {}; (conflict || []).forEach(function (w) { _cfl[w] = 1; });
  var _yi = yi.filter(function (w) { return !_cfl[w]; });
  var _ji = ji.filter(function (w) { return !_cfl[w]; });
  return ((_HL.pastDay ? '这天已经过去啦，就当复盘看看。' : '') +
    /* R2349n（R77-P2-4）：补宾语——「这个黄历没直接提」主谓残缺。 */
    '这事黄历没直接提。' + (day || '今天') + '主推【' + (_yi.join('、') || '无') + '】' +
    (_ji.length ? '，忌【' + _ji.join('、') + '】' : '') +
    '；没在宜忌里的事照常安排不犯冲～想问具体的事就带上它，比如「适合搬家吗」。');
}
function _hlVerdictHtml(sc, yi, ji, YI_MAP, JI_MAP, day, conflict, dayFlags) {
  /* R230h（R20-F7）：宜∩忌相冲词不作主推/凭据——后端同款摘除
   * （services.py:1512「按存疑处理，别当凭据念」），~22% 日子有此类词。 */
  var _cfl = {}; (conflict || []).forEach(function (w) { _cfl[w] = 1; });
  var _yiClean = yi.filter(function (w) { return !_cfl[w]; });
  var _jiClean = ji.filter(function (w) { return !_cfl[w]; });
  day = day || '今天';
  function _aliasList(name) {
    var arr = [name].concat(_hlSceneAlias(name));
    return arr;
  }
  function _hit(list, aliases, map) {
    var hits = [];
    list.forEach(function (w) {
      /* R230h（R20-F1）：与后端 chat_huangli_facts 判定规则对齐——
       * 双向包含（宜忌词⊂说法也算命中，如「动土盖房」含忌词「动土」）。
       * 砍掉 map 描述串通道：拿「整理心情/备孕」这种人话文案当事项词
       * 表撞是巧合驱动，后端没有这条通道，同问同日出相反判定。 */
      if (aliases.some(function (a) { return w.indexOf(a) !== -1 || a.indexOf(w) !== -1; })) hits.push(w);
    });
    return hits;
  }
  var aliases = _aliasList(sc);
  var hitYi = _hit(yi, aliases, YI_MAP);
  /* R2349n（R77-P0-1）：忌侧按同义族判——只在宜侧真有命中时把「宜」
   * 降级为「宜忌都有」；纯忌侧族命中仍是中性，不当作忌（与后端
   * chat facts 同口径）。 */
  var hitJi = _hit(ji, aliases, JI_MAP);
  if (hitYi.length) {
    var _famAliases = [];
    aliases.forEach(function (a) {
      _hlFamily(a).forEach(function (w) {
        if (_famAliases.indexOf(w) === -1) _famAliases.push(w);
      });
    });
    _hit(ji, _famAliases, JI_MAP).forEach(function (w) {
      if (hitJi.indexOf(w) === -1) hitJi.push(w);
    });
  }
  var why = '（' + day + '黄历主推' + (_yiClean.length ? '【' + _yiClean.join('、') + '】' : '的内容不多') +
    (_jiClean.length ? '，忌【' + _jiClean.join('、') + '】' : '') + '）';
  /* R2349（R64-P0-B/P1-1）：过去日期的判词要明说「已经过去」——后端
   * 事实行有同义披露，前端此前没有，「这周五」落到已过的日子也照样
   * 给「宜表白」不提示。 */
  var _pastTag = _HL.pastDay ? '（这天已经过去啦，就当复盘看看，挑日子看下面👇）' : '';
  /* R2349（R64-P1-6）：「哪天/什么时候+事项」找日问法——判词改给
   * 近 45 天清单引导（chip 列表随后异步注入）。 */
  if (_HL.findMode) {
    return '<div class="hl-verdict" id="hlVerdict">' +
      esc('想挑日子？近 45 天里适合「' + sc + '」的吉日已经列在下面，' +
          '点 chip 直接翻那天的黄历～' + _pastTag) + '</div>';
  }
  var verdict;
  if (hitYi.length && !hitJi.length) {
    /* R3370-P2-6：标记+空格+全角冒号是病句符（「✅ ： 宜」）。 */
    verdict = day + '适合' + sc + ' ✅：宜项里就有【' + hitYi.join('、') + '】' + why;
  } else if (hitJi.length && !hitYi.length) {
    /* R3113（R3102 BE 同口径）：忌判定把硬凶日凭据并进判词——
     * 旗行单独挂一行是「信息」，并进判词才是「凭据」。 */
    var _flv = (dayFlags || []).slice(0, 2);
    verdict = day + '不宜' + sc + ' 🚫：忌项里写着【' + hitJi.join('、') +
      '】' + (_flv.length ? '；这天还逢' + _flv.join('、') +
      '，凭据更实' : '') + why;
  } else if (hitYi.length && hitJi.length) {
    /* R228c：补谓语——「今天搬家宜忌都有」不通，「今天搬家的宜忌都有」
     * 与兄弟分支「今天适合/不宜搬家」同构。 */
    verdict = day + sc + '的宜忌都有，宜【' + hitYi.join('、') + '】但也忌【' + hitJi.join('、') + '】，想做就把节奏放稳、别赶大动作';
  } else {
    /* R228c：同句「黄历/老黄历」混用统一为「黄历」（全站功能名口径）。 */
    verdict = day + '黄历的宜忌里没有直接提到' + sc + '：不是不支持，只是黄历' + day + '没为它背书（' +
      (yi.length ? '主推【' + yi.join('、') + '】' : day + '宜项不多') +
      /* R2349（R64-P2）：措辞统一「适合」口径——「宜分手」读感怪。 */
      '）；' + sc + '可照常安排，想要黄历背书可以翻后面几天挑适合' + sc + '的日子';
  }
  /* R233g（R44-P1-7）：医疗类问法（看病/手术/体检/医美→求医治病）
   * 判词尾部必带「听医生的」口径——黄历不背书医疗决策。 */
  var _MED = ['求医', '治病', '求医疗病', '开刀'];
  var _med = _MED.some(function (m) { return sc.indexOf(m) !== -1; }) ||
    aliases.some(function (a) { return _MED.indexOf(a) !== -1; });
  if (_med) verdict += '（看病这种事，医生说了算，黄历不作数哦。）';
  return '<div class="hl-verdict" id="hlVerdict">' + esc(_pastTag + verdict) + '</div>';
}

/* 黄历页的跨调用状态（场景/目标日文案/滚动位/问一嘴待写标记）。
 * R228a：以前挂在 doHuangli 函数对象属性上（doHuangli._scene …）——合法
 * 但踩中 probe_dollar_misuse「函数当对象用」红线，换成纯数据对象更干净。 */
var _HL = {scene: '', dayWord: '', keepSy: null, pendingAskNote: false,
           pastDay: false, findMode: false};

/* R229z：本地 _hlDayOffset 解不动、但后端能解的日期词（节日/农历）——
 * 命中时问一嘴提交走 /api/huangli/resolve_date 兜底。与后端
 * _HOLIDAY_SOLAR/_HOLIDAY_LUNAR/除夕/清明 对齐维护。 */
/* R229z续9：节气词也走兜底（与后端 _SOLAR_TERMS/_SOLAR_TERMS_AMBI
 * 同表——大寒/小寒/大雪/小雪/小满 是双关词，后端按语境裁：带
 * 「那天/节气」按节气解，裸用如实说解不出，不再静默判显示日）。 */
/* R2355（R111-P1-2/P1-3）：补 星期/礼拜/4位年/裸N号——这些词形本
 * 地解不动时（星期八/32号/2027-02-29）要交后端 resolve 判 invalid
 * 明说，不许静默拿显示日判。 */
var _HL_COMPLEX_DATE = /农历|農曆|阴历|陰曆|旧历|舊曆|闰|閏|正月|冬月|腊月|臘月|除夕|春节|春節|大年初一|元宵|端午|七夕|中秋|重阳|重陽|腊八|臘八|清明|立春|雨水|惊蛰|驚蟄|春分|谷雨|穀雨|立夏|芒种|芒種|夏至|立秋|处暑|處暑|白露|秋分|寒露|霜降|立冬|冬至|大暑|小暑|大寒|小寒|大雪|小雪|小满|元旦|新年|情人|植树|植樹|愚人|劳动|勞動|五一|青年|儿童|兒童|六一|建党|建黨|建军|建軍|教师|教師|国庆|國慶|万圣|萬聖|平安|圣诞|聖誕|跨年|母亲节|母親節|父亲节|父親節|感恩|中元|小年|双十一|雙十一|光棍|下个?月|上个?月|这个?月|本个?月|月底|月末|月初|星期|礼拜|禮拜|\d{4}|(3[2-9]|[4-9]\d)\s*[号日]|([0-9]{1,3}|[一二两三四五六七八九兩十半]{1,3})[个個]?(天|日|周|週|星期|礼拜|禮拜)(后|後|前)|([0-9]{1,2}|[一二两三四五六七八九兩十半]{1,3})[个個]月(后|後|前)|(过|過)[0-9一二两三四五六七八九兩十]{1,3}[个個]?(天|日|周|週|星期|礼拜|禮拜)/;

/* 「问一嘴」无事项词时的中性提示（当日主推+引导）——提交主路径与
 * resolve_date 兜底复用。 */
/* R2997（巡#414）：危机/敏感问法的转介出口——与 _hlShowNeutral 同款
 * 落位（hlVerdict 行），文案即后端 _CHAT_REFUSAL/_SENSITIVE_REPLY。 */
function _hlShowLine(text) {
  var v = document.getElementById('hlVerdict');
  if (v) { v.textContent = text; return; }
  var askRow = document.querySelector('#hlResult .hl-ask');
  if (askRow && askRow.parentNode) {
    var nv = document.createElement('div');
    nv.className = 'hl-verdict'; nv.id = 'hlVerdict';
    nv.textContent = text;
    askRow.parentNode.insertBefore(nv, askRow);
  }
}
/* R3323：吉日/避让 chip 共用的跳日器——点击时刻换算偏移（跨零点不漂）。 */
/* R3397（调研·开运日历）：挑吉日榜尾部挂「本月图」钮——把命中月
 * 宜/忌它的日子画成月历海报，XHS「本月最佳面试日」体例的可晒件。
 * _lastGd 存进榜 payload：月内天数+月内名次，海报用。 */
var _lastGd = null;
function _hlCalBtn(scene, shownDate, dayList, mode) {
  /* R3397-2：不锁 shownDate 月——榜上天数常落在下个月，画天数
   * 最多的那月；并列取靠前的月。 */
  var _cnt = {}, _ord = [];
  (dayList || []).forEach(function (gd) {
    var _y = String(gd.date || '').slice(0, 7);
    if (!_y || _y.length < 7) return;
    if (!(_y in _cnt)) { _cnt[_y] = 0; _ord.push(_y); }
    _cnt[_y]++;
  });
  if (!_ord.length) { _lastGd = null; return ''; }
  var ym = _ord.reduce(function (a, b) {
    return (_cnt[b] > _cnt[a]) ? b : a; });
  var inMonth = (dayList || []).filter(function (gd) {
    return String(gd.date || '').slice(0, 7) === ym;
  });
  var _tn = todayIso();
  _lastGd = { scene: scene, ym: ym, mode: mode,
    today_day: (ym === _tn.slice(0, 7)) ? +_tn.slice(8, 10) : 0,
    days: inMonth.map(function (gd) {
      return { d: +String(gd.date).slice(8, 10),
               rank: gd.month_rank || 0 };
    }) };
  return ' <button type="button" class="hl-cal-btn ghost" data-hlcal>' +
    '📅 ' + (+ym.slice(5, 7)) + '月' +
    (mode === 'ji' ? '避让图' : '吉日图') + '</button>';
}
(function _hlCalBind() {
  document.addEventListener('click', function (e) {
    var b = e.target && e.target.closest
      ? e.target.closest('[data-hlcal]') : null;
    if (!b || !_lastGd) return;
    downloadPoster({ _hlcal: _lastGd, date: todayIso() }, 'hlcal');
  });
})();
function _hlDayChipGo(b) {
  var pp = String(b.dataset.hldate || '').split('-');
  if (pp.length !== 3) return;
  var t = new Date(+pp[0], (+pp[1]) - 1, +pp[2]);
  var t0 = new Date(); t0.setHours(0, 0, 0, 0);
  doHuangli(Math.round((t - t0) / 86400000), true);
}

function _hlShowNeutral() {
  /* R3323-P3-4：中性/invalid 判词落地时旧场景的吉日条不能留着——
   * 同屏共存「没这天」+「近期适合X」自相矛盾。 */
  var _gd0 = document.querySelector('.hl-gooddays');
  if (_gd0) _gd0.remove();
  var _lr = LAST_RESULT['huangli'] && LAST_RESULT['huangli'].json;
  var note = _hlNoSceneNote((_lr && _lr.yi) || [], (_lr && _lr.ji) || [],
    _HL.dayWord || '今天', _hlMergedConflict(_lr || {}));
  var v2 = document.getElementById('hlVerdict');
  if (v2) { v2.textContent = note; return; }
  var askRow = document.querySelector('#hlResult .hl-ask');
  if (askRow && askRow.parentNode) {
    var nv = document.createElement('div');
    nv.className = 'hl-verdict'; nv.id = 'hlVerdict';
    /* R229z续23（R10-#13）：父级 #hlResult 已是 polite 区——子节点不再叠
     * role=status（双播报）。 */
    nv.textContent = note;
    askRow.parentNode.insertBefore(nv, askRow);
  }
}
/* R230d（R16-P1-1）：黄历 chip/场景/问一嘴全走 addEventListener 委托，
 * 不经过 on() 的 _busy 锁——双击「明天」chip 实发两遍 GET /api/huangli。
 * 在途锁放进函数本身（submitBazi 的 _submitBaziBusy 先例）。 */
var _hlBusy = false;
var _hlQueued = null;   /* R230v（R34-#6）：取最新排队 */
async function doHuangli(offset, reveal, spokenWord) {
  /* R230v（R34-#6）：在途期间不再静默丢弃——记最新一次请求，当前
   * 查询完成后立即补跑（连点 chip/场景只会看到最后一次意图生效）。 */
  if (_hlBusy) { _hlQueued = [offset, reveal, spokenWord]; return; }
  _hlBusy = true;
  try { return await _doHuangli(offset, reveal, spokenWord); }
  finally {
    _hlBusy = false;
    if (_hlQueued) {
      var q = _hlQueued; _hlQueued = null;
      doHuangli(q[0], q[1], q[2]);
    }
  }
}
async function _doHuangli(offset, reveal, spokenWord) {
  /* v3（P7）重写：支持 chip 快选（offset 相对今天的天数）与自选日期。
   * 渲染：大字宜忌双色卡 + 农历干支 + 冲煞 + 场景 chip 高亮。
   * API 契约零改动（GET /api/huangli?date=YYYY-MM-DD）。 */
  var _abs = (typeof offset === 'number');
  var y, m, d;
  if (_abs) {
    var dt = new Date();   /* R228a：原名 base 与顶层 base() 函数撞名 */
    dt.setDate(dt.getDate() + offset);
    y = dt.getFullYear(); m = dt.getMonth() + 1; d = dt.getDate();
  } else {
    y = num('hl_year'); m = num('hl_month'); d = num('hl_day');
    if (y == null || m == null || d == null) {
      /* R2350a（R94-P2-9）：本地校验轻错走 toast——整卡替换会把
       * 上一张好卡抹成单行错误。 */
      showToast('先选一个日期～', 'warn');
      return;
    }
    /* R2514（审-P2）：手输日期此前零本地校验——1500-13-32 直达
     * 后端 400 才报「查询失败」。对齐全站 _badRange/_badYmdField
     * 红标字段+toast 的既有轻错路径（boxId=null 不抹好卡）。 */
    var _badF = _badRange('hl_year', 1900, 2100) ? 'hl_year'
      : (_badYmdField('hl_year', 'hl_month', 'hl_day') || null);
    if (_badF) {
      /* R3320-P3：错误按出错格点名——不分日月年都一句「再看看日期」。 */
      _failField(_badF, null,
        _badF === 'hl_year' ? '年份要在 1900–2100 之间'
          : '这一天不存在——' + num('hl_month') + ' 月没有 ' +
            num('hl_day') + ' 号');
      return;
    }
  }
  /* R227b-fix：日词跟着本次查询的日期走——chip 偏移直接映射，自选日期
   * 与今天比对（同一天=「今天」，否则=「那天」），问一嘴的日期词经
   * _hlDayOffset 换算后走同一条路，文案不写死「今天」。 */
  var _dayWord;
  if (_abs) {
    /* R229z续14：resolve_date 解出的原词（中秋节/冬至…）优先于泛化
     * 「那天」——卡片直接写「中秋节的黄历」。 */
    _dayWord = spokenWord || _hlDayWord(offset);
  } else {
    var _t0 = new Date();
    _dayWord = (y === _t0.getFullYear() && m === _t0.getMonth() + 1 && d === _t0.getDate()) ? '今天' : '那天';
  }
  _HL.dayWord = _dayWord;
  /* R2349（R64-P0-B/P1-1）：目标日 < 今天 → 判词/中性卡加过期提示
   * （后端事实行有同义披露，前端此前缺席）。 */
  var _tp = new Date(); _tp.setHours(0, 0, 0, 0);
  _HL.pastDay = (new Date(y, m - 1, d) < _tp);
  /* R228c：chip 高亮跟本次实际查的日期走——自选日期/问一嘴跳日路径原来
   * 不动 chip，「今天」常亮但结果显示的是另一天（状态泄漏）。无对应
   * chip 的日期（绝对日期/超范围偏移）则全部灭掉。 */
  /* R2350a（R94-P1-7）：非绝对路径（自选日期/问一嘴/场景刷新）此前
   * 恒灭灯——拿请求日反算偏移回填，落在 chip 覆盖区间就点亮。 */
  var _offShown = _abs ? offset :
    Math.round((new Date(y, m - 1, d) - _tp) / 864e5);
  document.querySelectorAll('#hlChips .hl-chip').forEach(function (c) {
    var on = _offShown != null && Number(c.dataset.hloffset) === _offShown;
    c.classList.toggle('active', on);
    c.setAttribute('aria-pressed', String(on));   /* R228d：激活态读屏可知 */
  });
  var _dr = document.getElementById('hlPickDrawer');
  if (_dr && !_abs) _dr.open = false;   /* 自选日期提交后收起抽屉 */
  /* R228c：问一嘴输入值保活——整卡重渲染会重建输入框，已打的字
   * 随旧 DOM 一起消失；渲完后回填（见下方 paint 后）。 */
  var _askKeep = ((document.getElementById('hlAskInput') || {}).value || '');
  var _keepSy = null;
  var _hlBox = el('hlResult');
  if (reveal === false) {
    /* v5-fix：优先用调用方在关抽屉/页面变形前存下的位置（否则捕到的是已钳位后的值） */
    _keepSy = (_HL.keepSy != null) ? _HL.keepSy : window.scrollY;
    _HL.keepSy = null;
    /* v5-fix（取证 .cluster/debug_scroll_v5.py）：busy 单行占位把长结果页压短，
     * 浏览器钳位直接吃掉滚动位，恢复 scrollTo 落在已塌缩坐标系上必然归零。
     * 根治：原位刷新不换占位——旧结果保持可见只加 loading 态（页面高度
     * 全程不变，钳位/锚定无从发生），数据到达后一次性替换。 */
    if (_hlBox) {
      _hlBox.classList.add('is-loading');
      _hlBox.style.pointerEvents = 'none';
    }
  } else {
    busy('hlResult', '翻黄历…');   /* 首查/显式查询：占位+滚到结果，行为不变 */
  }
  var dateStr = y + '-' + String(m).padStart(2, '0') + '-' + String(d).padStart(2, '0');
  try {
    const j = await api('/api/huangli?' + new URLSearchParams({
      date: dateStr,
      today: todayIso(),   /* R2349k（R72-B3）：cross_ref「今天」锚客户端日 */
    }).toString());
    var YI_MAP = _HL_YI_MAP, JI_MAP = _HL_JI_MAP;   /* R230y：映射表提升为模块级常量 */
    var yi = (j.yi || []);
    var ji = (j.ji || []);
    var lunar = j.lunar || {};
    var cs = j.cross_ref || {};
    var yiSet = {}; yi.forEach(function (x) { yiSet[x] = true; });
    var html = '';
    /* 头部：日期 + 农历干支 */
    /* R2349j（R70-P0-2）：渐变类化，深色补丁可生效。 */
    html += '<div class="hl-head">';
    /* R2349o（R78-P1-3）：内联 #7A5F33 在奶油底仅 1.77:1——文字色收编
     * 令牌（--primary-ink 奶油底 5.0、深底同样达标）。 */
    html += '<div style="font-size:20px;font-weight:800;color:var(--primary-ink);">' + esc(j.date || dateStr) + '</div>';
    /* R230n（R25-1.3）：记下本卡实际展示的公历日——跨零点自刷新靠它
     * 判「这张卡是不是昨天的快照」。 */
    if (_hlBox) _hlBox.dataset.shownDate = j.date || dateStr;
    /* R2350a（R94-P2-12）：H2「今天宜忌」跟日期走。 */
    try {
      var _h2d = document.getElementById('hlTitleDay');
      if (_h2d) _h2d.textContent = _dayWord;
    } catch (eH2) {}
    _HL.renderedOn = todayIso();   /* R2349k（R72-B1）：渲染日戳，隔夜重查用 */
    /* R228c：month_cn 本身已带「月」（后端 MONTH_CN 表生成时即带），
     * 再拼一个就成「八月月十九」——直接 month_cn+day_cn。
     * 注意：注释里别写「模块.文件」式点号串——probe_contract 会当字段读取。 */
    /* R229z续19：1900-01-31 前农历表无数据（月名/干支全空）——
     * 「农历  · 」空串残影换成直白说明。 */
    var _lunarTxt = (lunar.month_cn || '') + (lunar.day_cn || '');
    html += '<div style="font-size:13px;color:var(--secondary);margin-top:2px;">' +
      (_lunarTxt
        ? '农历 ' + esc(_lunarTxt) + ' · ' + esc(lunar.ganzhi_year_cn || '') +
          /* R2350a（R94-P2-10）：日干支透出（黄历标配缺项）。 */
          (j.ganzhi_day_cn ? ' · ' + esc(j.ganzhi_day_cn) : '')
        : (j.date && j.date.slice(0, 4) > '2100'
           ? '农历：这一天晚于历法表终点（2100-12-31），宜忌仍按干支推'
           : '农历：这一天早于历法表起点（1900-01-31），宜忌仍按干支推')) +
      '</div>';
    /* R233v（R52-P1-3）：传统硬凶日明示——月破/四离四绝/杨公忌
     * 此前与普通日零差别。 */
    var _fl = j.day_flags || [];
    if (_fl.length) {
      /* R233y（R54-P0-11）：⛔+「诸事谨慎」是恐吓式裸奔——换 🌙 图标
       * + 白话口径，凶日用「缓一缓就好」收尾（对照 U-009 凶→缓口径）。 */
      var _flTxt = _fl.map(function (f) {
        return f === '月破' ? '月破日：大事缓一缓就好'
          : f === '四离' ? '四离日：节气前一天，宜收不宜开'
          : f === '四绝' ? '四绝日：立季前一天，大事留到后天'
          : f === '岁破' ? '岁破日：日支冲太岁，大事留到改天'
          : f === '受死' ? '受死日：老通书标的大凶日，大事勿用'
          : f === '杨公忌' ? '杨公忌日：老传统提醒稳着点，小事照常' : f;
      }).join('、');
      /* R3308（审-低4）：hard_note 口径注记同行带出——「大事勿用
       * （小事可为）」，免得整卡被读成今天什么都不能做。 */
      var _hn = j.hard_note ? ('·' + j.hard_note.replace(/^日值/, '')) : '';
      html += '<div class="hl-flag">🌙 ' + esc(_dayWord) + '逢' +
        esc(_flTxt + _hn) + '</div>';
    }
    if (cs && cs.message) html += '<div class="hl-csmsg">✨ ' + esc(cs.message) + '</div>';
    /* R2349k（R72-A2）：节日行——中秋节/立秋/母亲节这天值得说出来。 */
    if (j.festival && j.festival.length) {
      /* R2350a（R94-P1-5）：spokenWord=节日名时「中秋节是中秋节」
       * 叠词露馅——换「就是XX节」。 */
      var _fes = String(j.festival && j.festival.join ? j.festival.join('、') : '');
      var _fesTip = _festTip(j.festival[0]);
      html += '<div class="hl-festival">🎉 ' +
        (_fes.indexOf(_dayWord) >= 0
          ? '就是' + esc(_fes) + '，过节啦'
          : esc(_dayWord) + '是' + esc(_fes)) +
        (_fesTip ? ' · ' + esc(_fesTip) : '') + '</div>';
    }
    /* R229z续21c：干支年双口径错位日（春节↔立春窗口）才出现的说明行 */
    if (j.year_note) html += '<div style="font-size:12px;color:var(--muted);margin-top:4px;">📅 ' + esc(j.year_note) + '</div>';
    html += '</div>';
    /* 宜/忌 双色大卡 */
    html += '<div class="hl-yiji">';
    /* R229z续21（R9-P1-2）：宜∩忌同见的词（黄历自相矛盾项，约 22% 日子）
     * 标※并在卡下方附说明——不然同一词两头出现像渲染坏了。
     * R2349n（R77-P0-1）：同义族对冲词并入※标（宜修造忌动土类）。 */
    var _conflict = [];
    (Array.isArray(j.conflict) ? j.conflict : [])
      .concat(Array.isArray(j.conflict_family) ? j.conflict_family : [])
      .forEach(function (w) {
        if (_conflict.indexOf(w) === -1) _conflict.push(w);
      });
    var _cflSet = {};
    _conflict.forEach(function (w) { _cflSet[w] = 1; });
    html += '<div class="hl-yi">';
    html += '<div class="hl-yi-t">✅ 宜</div>';
    html += yi.length ? '<div style="display:flex;flex-wrap:wrap;gap:6px;">' +
      yi.map(function (w) {
        var hot = (_HL.scene &&
                   (w.indexOf(_HL.scene) !== -1 || (YI_MAP[w] || '').indexOf(_HL.scene) !== -1));
        /* R233h（R43-#11）：宜忌白话从 title（触屏根本看不到）挪进
         * 可视小字行——pill 变两行：词 + 释义。 */
        var _g = YI_MAP[w] || '';
        return '<span class="hl-pill' + (hot ? ' hl-hot' : '') + '">' + esc(w) +
          (_cflSet[w] ? '※' : '') +
          (_g ? '<small class="hl-pill-sub">' + esc(_g) + '</small>' : '') + '</span>';
      }).join('') + '</div>' : '<div class="ph-empty">' + esc(_dayWord) + '没什么特别适宜的</div>';
    html += '</div>';
    html += '<div class="hl-ji">';
    html += '<div class="hl-ji-t">🚫 忌</div>';
    html += ji.length ? '<div style="display:flex;flex-wrap:wrap;gap:6px;">' +
      ji.map(function (w) {
        var _g2 = JI_MAP[w] || '';
        return '<span class="hl-pill hl-pill-ji">' + esc(w) +
          (_cflSet[w] ? '※' : '') +
          (_g2 ? '<small class="hl-pill-sub">' + esc(_g2) + '</small>' : '') + '</span>';
      }).join('') + '</div>' : '<div class="ph-empty">没有特别要避开的</div>';
    html += '</div></div>';
    /* R2365（R3301-P2）：红白同框观感——「宜嫁娶」旁列「忌安葬」
     * 传统历书各事各论本属正常，但对受众像打架；附一行注脚化解。 */
    var _HL_RED = ['嫁娶', '求嗣', '冠笄', '纳采', '订盟', '进人口'];
    var _HL_WHT = ['安葬', '行丧', '破土', '启攒', '修坟', '立碑',
                   '入殓', '除服', '成服', '移柩'];
    if (yi.some(function (w) { return _HL_RED.indexOf(w) !== -1; }) &&
        ji.some(function (w) { return _HL_WHT.indexOf(w) !== -1; })) {
      html += '<div style="font-size:12px;color:var(--muted);margin-top:6px;">' +
        '宜忌各事各论：喜事丧事各看各的，挑跟你有关的那一行就行</div>';
    }
    if (_conflict.length) {
      html += '<div style="font-size:12px;color:var(--muted);margin-top:6px;">※ ' +
        esc(_conflict.join('、')) + ' 在宜忌两边打架：黄历自己都矛盾的日子，' +
        '这类事想做就把节奏放缓，不赶大动作</div>';
    }
    /* 场景 chips：点选高亮匹配宜项
     * R230q（R28-P3-12）：打印时整块隐藏——原先只藏 chip 按钮，
     * 「我打算：」「点一个场景…」两段说明成孤儿文字悬在纸上。 */
    var SCENES = ['搬家', '开业', '约会', '面试', '出行', '签约'];
    /* R3253：场景 chip 配小图——「我打算」从文字选项变成
     * 一眼能认的场景卡（小红书心智：看图选比读字快）。 */
    var HL_SCENE_ART = { '搬家': 'scene-move', '开业': 'scene-open',
      '约会': 'scene-date', '面试': 'scene-interview',
      '出行': 'scene-travel', '签约': 'scene-sign' };
    html += '<div class="hl-interactive" style="margin-top:14px;"><div style="font-size:13px;color:var(--secondary);margin-bottom:6px;">我打算：</div><div style="display:flex;flex-wrap:wrap;gap:6px;" id="hlScenes">';
    html += SCENES.map(function (s) {
      /* R2349n（R77-P0-4）：chip ✓ 与判词同口径——别名命中宜侧、
       * 不命中忌侧、命中词不在冲突集里才亮 ✓（原先白话描述串当
       * 事项词的旧通道+只看宜不看忌，同卡两判）。 */
      var _als = [s].concat(_hlSceneAlias(s));
      var _hY = yi.filter(function (w) {
        return !_cflSet[w] && _als.some(function (a) {
          return w.indexOf(a) !== -1 || a.indexOf(w) !== -1; });
      });
      /* R2400（R141-P1-1）：chip ✓ 此前不做族扩展——同卡判词说
       * 「宜X也忌Y」而 chip 却亮「✓ 适合」（全年搬家 22 天分裂）。
       * 别名→族词并集再扫忌侧，与判词/后端同口径。 */
      var _fals = _als.slice();
      _als.forEach(function (a) {
        _hlFamily(a).forEach(function (w) {
          if (_fals.indexOf(w) === -1) _fals.push(w);
        });
      });
      var _hJ = ji.filter(function (w) {
        return _fals.some(function (a) {
          return w.indexOf(a) !== -1 || a.indexOf(w) !== -1; });
      });
      var ok = _hY.length && !_hJ.length;
      /* R229z续23（R10-#9）：选中态同步 aria-pressed——读屏能知道选了哪个
       * 场景；判定文案同时并进 aria-label（title 悬停键盘/读屏不可达，#21） */
      var _on = _HL.scene === s;
      /* R3323-P2-3：中性日（宜忌都没提）不再标「不宜」——判词同屏
       * 说「可照常安排」，chip 标不宜是自相矛盾的 a11y 文案。 */
      var _hint = ok ? _dayWord + '适合'
        : (_hJ.length ? _dayWord + '不宜' : _dayWord + '可看');
      var _ic = HL_SCENE_ART[s]
        ? '<img class="hl-scene-ic" src="/static/cream/' + HL_SCENE_ART[s] +
          '.jpg" alt="" loading="lazy" decoding="async" ' +
          'onerror="this.remove()">'
        : '';
      return '<button type="button" class="hl-scene' + (_on ? ' active' : '') +
        '" data-scene="' + esc(s) + '" aria-pressed="' + _on +
        '" aria-label="' + esc(s + '，' + _hint) + '" title="' + _hint + '">' +
        _ic + esc(s) + (ok ? ' ✓' : '') + '</button>';
    }).join('');
    html += '</div>';
    /* v4：显式结论——点选场景后卡内直接给一句人话答案，不再只靠 ✓ 自己猜 */
    if (_HL.scene) {
      html += _hlVerdictHtml(_HL.scene, yi, ji, YI_MAP, JI_MAP, _dayWord,
                             _conflict, j.day_flags || []);
      /* R3261（R14）：问的是未来的事→「到时候小满问问我」——写进
       * chat:events（R7 同管线），隔天空态跟进「怎么样了」。
       * 本地件不推送；过去日不展示（问了就过了）。 */
      var _fd = j.date || dateStr || '';
      if (_fd > todayIso()) {
        html += '<button type="button" id="hlFollowBtn" ' +
          'class="hl-follow-btn" data-sc="' + esc(_HL.scene) +
          '" data-d="' + esc(_fd) + '">🔔 到时候小满问问我</button>';
      }
    }
    /* R227b-fix：问一嘴带日期词但没事项词（「明天怎么样」）——翻完那一天
     * 后把主推+引导兜底按目标日写回，不再把「今天」的宜忌安到明天头上。 */
    if (_HL.pendingAskNote) {
      _HL.pendingAskNote = false;
      html += '<div class="hl-verdict" id="hlVerdict">' +
        esc(_hlNoSceneNote(yi, ji, _dayWord, _conflict)) + '</div>';
    }
    /* v5（用户反馈）：「问一嘴」——用户自由输入「今天适不适合面试」这类问题，
     * 场景词库匹配后给同款带所以然的结论。 */
    html += '<div class="hl-ask" style="margin-top:10px;display:flex;gap:8px;">' +
      '<input id="hlAskInput" class="hl-ask-input" type="text" maxlength="30" aria-label="问一嘴：哪天适不适合某事" placeholder="问一嘴：哪天适不适合面试/搬家…">' +
      '<button type="button" id="hlAskBtn" class="hl-ask-btn">问</button>' +
      '</div>' +
      /* R230z（R36-P2-5）：问一嘴足迹——问过的问题收在这里可复点 */
      '<div id="hlAskHist" class="fav-row"></div>';
    html += '<div style="font-size:12px;color:var(--muted);margin-top:6px;">点一个场景，看看' + esc(_dayWord) + '合不合适（✓ = 宜项里有它）</div></div>';
    /* 冲煞（R228a TYPE 修复）：后端给的是 {chong, chong_animal, sha_fang}
     * dict，整个 esc() 会渲染成 [object Object]——拼成「冲虎煞南」人话。 */
    var _csTxt = '';
    if (j.chongsha) {
      _csTxt = (typeof j.chongsha === 'string') ? j.chongsha :
        ('冲' + (j.chongsha.chong_animal || j.chongsha.chong || '') +
         (j.chongsha.sha_fang ? '煞' + j.chongsha.sha_fang : ''));
    }
    /* R233g（R44-P1）：「冲虎煞南」是黑话——改白话提醒。 */
    var _csPlain = '';
    if (j.chongsha && typeof j.chongsha !== 'string' &&
        (j.chongsha.chong_animal || j.chongsha.chong)) {
      _csPlain = '属' + (j.chongsha.chong_animal || j.chongsha.chong) +
        '的宝子' + _dayWord + (j.chongsha.sha_fang ?
        '往' + j.chongsha.sha_fang + '边' : '出门') + '多留个心眼';
    }
    if (_csTxt) html += '<div class="hl-cs" style="margin-top:12px;font-size:13px;color:var(--secondary);">' +
      esc(_csPlain || ('冲煞：' + _csTxt)) + '</div>';
    /* R232b（R40-A1/W1+W8）：神煞白话条——贵人/驿马临日是这张卡的
     * 灵魂（求人帮忙、出行走动），后端算了 12 键神煞前端零读点。
     * R233w（R52-P1-2）：临日判定收成后端单点（shensha.linri）——
     * 前端不再复现「日支==神煞值」判定，只做 名字→文案 的展示映射。 */
    var _ss = j.shensha || {};
    var _lr = _ss.linri || {};
    var _SS_GOOD = {'贵人': '贵人临日 · 宜求人帮忙',
                    '驿马': '驿马临日 · 利出行走动',
                    '天赦': '天赦日 · 宜解开心结',
                    '天德': '天德临日 · 和气生财',
                    '月德': '月德临日 · 诸事有缓'};
    var _lucky = (_lr.good || []).map(function (n) {
      return _SS_GOOD[n] || (n + '临日'); });
    var _unlucky = (_lr.bad || []).map(function (n) {
      return n + '临日'; });
    if (_lucky.length || _unlucky.length) {
      html += '<div class="hl-shensha">';
      if (_lucky.length) {
        html += '<span class="hl-ss-good">✨ ' + esc(_lucky.join('；')) + '</span>';
      }
      if (_unlucky.length) {
        /* R233g（R44-P2-12）：只报忧不指路 → 补半句怎么缓。 */
        html += '<span class="hl-ss-bad">' + esc(_unlucky.join('；')) +
          '，大事缓一缓再定就好</span>';
      }
      html += '</div>';
    }
    var _jx = [];
    /* R233g（R44-P1）：建除带白话注（星宿 28 位无注表，先只给名）。 */
    var _JC = {建:'宜起头',除:'宜清理旧事',满:'宜收尾盘点',平:'平平淡淡',
               定:'宜定下来',执:'宜抓落实',破:'大事慎重',危:'多留个心眼',
               成:'成事日',收:'宜收纳归拢',开:'宜开局',闭:'宜静不宜动'};
    if (j.jianchu) _jx.push('建除：' + j.jianchu +
      (_JC[j.jianchu] ? '（' + _JC[j.jianchu] + '）' : ''));
    if (j.xiu) _jx.push('星宿：' + j.xiu);
    /* R2350a（R94-P1-4）：日值神（大黄道）透出——「黄道日/黑道日」
     * 是传统黄历标配。 */
    if (j.zhishen) _jx.push('值神：' + j.zhishen +
      (j.zhishen_ji ? '（黑道：大事缓一缓）' : '（黄道）'));
    /* R2350a（R94-P2-10）：贵人方位人话化——支→方位。 */
    var _GR_DIR = { '子': '北', '丑': '东北', '寅': '东北', '卯': '东',
      '辰': '东南', '巳': '东南', '午': '南', '未': '西南',
      '申': '西南', '酉': '西', '戌': '西北', '亥': '西北' };
    var _gr = (_ss.guiren || []);
    if (_gr.length) _jx.push('贵人在' + _gr.map(function (b) {
      return _GR_DIR[b] || b; }).join('、'));
    if (_jx.length) {
      html += '<div style="font-size:12px;color:var(--muted);margin-top:6px;">' +
        esc(_jx.join(' · ')) + '</div>';
    }
    /* R2350a（R94-P1-4）：十二时辰吉凶格——亮格=吉时。 */
    if (Array.isArray(j.hours) && j.hours.length === 12) {
      html += '<div class="hl-hours"><span style="font-size:12px;' +
        'color:var(--muted);">时辰吉凶　</span>' +
        j.hours.map(function (h) {
          return '<span class="hl-hour' + (h.ji ? ' hl-hour-ji' : '') +
            '" title="' + esc(h.branch) + '时·' + esc(h.shen) +
            (h.ji ? '（吉）' : '（凶）') + '">' + esc(h.branch) + '</span>';
        }).join('') + '</div>';
    }
    /* R233w（R52-P3-9）：交节当日透明化——±15min 精度边界直接亮给用户。 */
    if (j.term_today) {
      html += '<div style="font-size:12px;color:var(--muted);margin-top:6px;">' +
        esc('交节：' + j.term_today.name + ' ' + j.term_today.time) + '</div>';
    }
    /* R230a-2：彭祖百忌——接口一直返回但卡面从未露出（黄历标配的两句老话）。
     * 小字收在免责前，不抢戏。 */
    var _pz = j.pengzu || {};
    var _pzTxt = (_pz.gan_text || '') + ((_pz.gan_text && _pz.zhi_text) ? ' · ' : '') + (_pz.zhi_text || '');
    /* R233g（R44-P2）：彭祖百忌原文前给「老话讲」引子——裸「百忌」
     * 读着吓人，其实就两句古老话。 */
    if (_pzTxt) html += '<div style="font-size:12px;color:var(--muted);margin-top:10px;">老话讲：' + esc(_pzTxt) + '</div>';
    /* R230a-11：黄历交叉引用——后端 _cross_ref_huangli 一直返回但卡面
     * 从未露出（星座值宫×当日干支的人话一句）。 */
    /* R2350a（R94-P1-1/P2-13）：同句双渲染——✨ 头行已有 cross_ref
     * 全文，卡底不再复读，改成「去星座页看看」的可点链接
     * （天然引流点此前是纯文本）。data-xview 在点击委托里收。 */
    if (j.cross_ref && j.cross_ref.zodiac_sign) {
      html += '<div class="cross-ref"><button type="button" ' +
        'class="thread-view" data-xview="xingzuo">⭐ 看看' +
        esc(j.cross_ref.zodiac_sign) + '座' + esc(_dayWord) +
        '的运势 →</button></div>';
    }
    /* R3189：黄历卡补 AI 解读段——宜忌/值神/冲煞坐标进 facts
     * 后由 polish 串成人话；与各面同契约（无 task 时零占位）。 */
    html += renderAiPolish(j);
    html += tailHook('huangli');
    html += '<div style="font-size:12px;color:var(--muted);margin-top:12px;">黄历按传统历法规则计算，仅供娱乐，不构成决策依据，大事还是相信自己的判断 ✨</div>';
    /* R230d（R16-P2-6）：黄历卡没有 .card 容器，paint 的自动挂钮
     * 找不到宿主——手动挂「聊聊这件事」（其他五个视图都有）。 */
    html += '<button class="chat-entry" type="button" data-chat-entry ' +
      'aria-label="打开小满聊天，聊聊这件事">💬 聊聊这件事</button>';
    paint('hlResult', html);
    pollAiPolish('hlResult', j.ai_task_id);   /* R3189 */
    /* R228x：判词落地「挑吉日」——场景已选时异步查近期宜它的日子
     * （后端 affair+days 区间查，含口语词归一），chip 点击直接翻
     * 到那一天。silent：查不到不打扰，宜日缺席时整个提示块不渲染。 */
    if (_HL.scene) {
      var _gsc = _HL.scene;
      var _gsrc = y + '-' + String(m).padStart(2, '0') + '-' + String(d).padStart(2, '0');
      api('/api/huangli?date=' + _gsrc + '&affair=' + encodeURIComponent(_gsc) +
          '&days=45', { silent: true }).then(function (gj) {
        var box = document.getElementById('hlVerdict');
        /* R230v（R34-#8）：基准日比对——场景筛选的请求落地时，卡面
         * 可能已翻到别的日子；旧基准的吉日条不许注入新卡。 */
        var _hlBoxG = el('hlResult');
        if (!box || !gj || _HL.scene !== _gsc ||
            !_hlBoxG || _hlBoxG.dataset.shownDate !== _gsrc) return;
        /* R3323-P0-1：ji-only 事项（诉讼/破土/求名…黄历只讲避不讲宜）——
         * 吉日恒空是死路，后端反吐避让榜，前端改渲染「要避开的」。 */
        var _badDays = gj.bad_days || [];
        if ((gj.ji_only || 0) && _badDays.length) {
          var _bc = gj.bad_count || _badDays.length;
          /* R3330（审-低3）：截断如实写进文案——榜只列前 14 天而
           * 真实忌日更多时，「有 N 天」不再看起来像全量。 */
          box.innerHTML = esc('「' + _gsc + '」这种事老黄历只讲避不讲宜——' +
            '近 45 天里忌它的日子有 ' + _bc + ' 天' +
            ((gj.list_truncated || 0) ? '（下面只列前 14 天）' : '') +
            '，绕开就好～');
          var _bChips = _badDays.slice(0, 6).map(function (gd) {
            var pp = String(gd.date || '').split('-');
            var lab = (+pp[1]) + '/' + (+pp[2]);
            var _bj = gd.ji || [];
            var _btt = _bj.length ? '忌：' + _bj.slice(0, 4).join('、') : '';
            return '<button type="button" class="hl-daychip has-soft"' +
              ' data-hldate="' + esc(String(gd.date || '')) + '"' +
              (_btt ? ' title="' + esc(_btt) + '"' : '') + '>' +
              esc(lab) + '</button>';
          }).join('');
          /* R3330（审-中2）：避让榜之外补「相对清净的日子」——
           * 后端显式核过的干净日（term 不落忌+无硬凶），给只忌不宜
           * 的事一个可去的方向，不再只有黑名单没有白名单。 */
          var _calmDays = gj.calm_days || [];
          var _cChips = _calmDays.slice(0, 6).map(function (gd) {
            var pp2 = String(gd.date || '').split('-');
            var lab2 = (+pp2[1]) + '/' + (+pp2[2]);
            return '<button type="button" class="hl-daychip"' +
              ' data-hldate="' + esc(String(gd.date || '')) + '">' +
              esc(lab2) + '</button>';
          }).join('');
          var _oldGdB = box.parentNode &&
            box.parentNode.querySelector('.hl-gooddays');
          if (_oldGdB) _oldGdB.remove();
          var tipB = document.createElement('div');
          tipB.className = 'hl-gooddays';
          tipB.innerHTML = '<span class="hl-gooddays-label">要避开的日子：'
            + '</span>' + _bChips +
            (_cChips ? '<br><span class="hl-gooddays-label">相对清净的日子：'
            + '</span>' + _cChips : '') +
            _hlCalBtn(_gsc, _gsrc, _badDays, 'ji');
          if (box.nextSibling) box.parentNode.insertBefore(tipB, box.nextSibling);
          else box.parentNode.appendChild(tipB);
          tipB.querySelectorAll('[data-hldate]').forEach(function (b) {
            b.addEventListener('click', function () { _hlDayChipGo(b); });
          });
          return;
        }
        var _gdArr = gj.good_days || [];
        if (!_gdArr.length) {
          /* R3323-P1-1：findMode 判词不许空头支票——榜空时把「已列在
           * 下面」改说真话（死词与真空窗都走这里）。 */
          if (_HL.findMode) {
            box.innerHTML = esc('近 45 天里没翻到特别适合「' + _gsc +
              '」的日子——可以放宽点条件再翻翻，或者直接问小满～');
          }
          return;
        }
        var _today0 = new Date(); _today0.setHours(0, 0, 0, 0);
        var _todayIso = _today0.getFullYear() + '-' +
          String(_today0.getMonth() + 1).padStart(2, '0') + '-' +
          String(_today0.getDate()).padStart(2, '0');
        /* R229y：起点日（正在看的这天）若本就宜，chip 列表第一项会是它
         * 自己——点了原地不动（ui_smoke gooddays_chip 抓到）。过滤掉
         * 当前显示日再取前 6。
         * R230h（R20-F5）：滤掉 < today 的日子——问过去日的宜忌时，
         * 45 天区间扫出来的全是过去日，不该当「挑日子」建议推给用户
         * （聊天侧同款守卫 services.py:1503）。 */
        var _days = gj.good_days.filter(function (gd) {
          return String(gd.date || '') !== _gsrc && String(gd.date || '') >= _todayIso;
        });
        if (!_days.length) return;
        var chips = _days.slice(0, 6).map(function (gd) {
          var pp = String(gd.date || '').split('-');
          var lab = (+pp[1]) + '/' + (+pp[2]);
          /* R230h（R20-F3）：chip 存绝对日期不存偏移——渲染时刻的偏移
           * 跨零点后点击会整体 +1 天漂移（实测渲染 9/19→点 9/25 落 9/26）。 */
          /* R232a（R40-A19）：chip 带当日宜忌摘要 title——返回的
           * yi/ji 此前零消费，白回两个数组。 */
          var _tt = '';
          var _gy = gd.yi || [], _gj = gd.ji || [];
          if (_gy.length) {
            /* R2400（R141-P3-3）：悬停宜词截断会把命中词藏到第 5 位
             * 后——命中词提为 title 首项，让用户看到「为什么适合」。 */
            var _ga = [_gsc].concat(_hlSceneAlias(_gsc));
            var _gHit = _gy.filter(function (w) {
              return _ga.some(function (a) {
                return w.indexOf(a) !== -1 || a.indexOf(w) !== -1; });
            });
            var _gRest = _gy.filter(function (w) {
              return _gHit.indexOf(w) === -1; });
            _tt = '宜：' + _gHit.concat(_gRest).slice(0, 4).join('、');
            /* R3323-P2-1/P2-2：小有顾忌日（簇过族冲）——冲突忌词
             * 提为悬停首项，截断不再恰好把它藏起来。 */
            var _scL = gd.soft_conflict || [];
            var _jTip = _scL.length
              ? _scL.concat(_gj.filter(function (w) {
                  return _scL.indexOf(w) === -1; }))
              : _gj;
            if (_jTip.length) {
              _tt += '　忌：' + _jTip.slice(0, 3).join('、');
            }
          }
          /* R2349l（R73-P1-5）：带硬凶（月破/四离/杨公忌…）的吉日
           * 标 ⚠——榜单排序已把无凶日排前面，进榜的凶日得有记号。 */
          var _fl = gd.flags || [];
          if (_fl.length) {
            _tt = (_tt ? _tt + '　' : '') + '逢' + _fl.join('、') +
              '，能换就换一天';
            lab += '⚠';
          }
          /* R3323-P2-1：簇过族冲的「小有顾忌」日标 ※——榜说宜签约
           * 而卡判宜忌都有的分裂日，在意的人能看出来。 */
          var _scL2 = gd.soft_conflict || [];
          if (_scL2.length) {
            _tt = (_tt ? _tt + '　' : '') +
              '小有顾忌（忌侧同族有提），在意可换一天';
            lab += '※';
          }
          /* R3317-B：月内稀有度——「本月第N个吉日」的晒图级钩子
           * 进悬停注，让挑吉日的人知道这天的稀缺度。 */
          var _mR = gd.month_rank || 0, _mT = gd.month_total || 0;
          if (_mR && _mT) {
            _tt = (_tt ? _tt + '　' : '') +
              (+pp[1]) + '月第' + _mR + '个吉日（共' + _mT + '个）';
          }
          return '<button type="button" class="hl-daychip' +
            (_fl.length ? ' has-flag' : '') +
            (_scL2.length ? ' has-soft' : '') + '" data-hldate="' +
            esc(String(gd.date || '')) + '"' +
            (_tt ? ' title="' + esc(_tt) + '"' : '') + '>' +
            esc(lab) + '</button>';
        }).join('');
        /* R230v（R34-#8）：去重——重渲/重注窗口重叠时先清旧条，不叠双份。 */
        var _oldGd = box.parentNode && box.parentNode.querySelector('.hl-gooddays');
        if (_oldGd) _oldGd.remove();
        /* R2349l.7（R74-P2-a）：凶日排序沉底+窗口截 6——若被截部分里
         * 还有逢凶日，榜尾补一行说明，⚠ 标记不至于完全不可见。 */
        var _sunk = _days.slice(6).filter(function (gd) {
          return (gd.flags || []).length > 0;
        }).length;
        var tip = document.createElement('div');
        tip.className = 'hl-gooddays';
        /* R2349（R64-P2）：「近期宜分手」直译刺耳——换「适合」口径。 */
        /* R3317-B：榜上日子同月且月内吉日数 ≤8 时给稀缺注——
         * 「10月只剩 4 个」是小红书体的紧迫感素材。 */
        var _rare = '', _rTot = 0, _rKey = '';
        for (var _ri = 0; _ri < Math.min(_days.length, 6); _ri++) {
          var _gR = _days[_ri], _gMk = String(_gR.date || '').slice(0, 7);
          if (!_rKey) _rKey = _gMk;
          if (_gMk !== _rKey || !(_gR.month_total || 0)) {
            _rTot = 0; break;
          }
          _rTot = _gR.month_total;
        }
        if (_rTot && _rTot <= 8) {
          _rare = (+_rKey.slice(5, 7)) + '月共 ' + _rTot + ' 个吉日';
        }
        tip.innerHTML = '<span class="hl-gooddays-label">近期适合' +
          esc(_gsc) + '：</span>' + chips +
          (_rare ? '<span class="hl-gooddays-note">（' + _rare +
            '）</span>' : '') +
          /* R3330（审-低）：稀疏榜明示——整窗就翻到 1-2 个吉日时
           * 榜单看起来像没查完，补一句「本来就少」消掉
           * 「是不是坏了」的疑惑。 */
          (!_rare && _days.length <= 2
            ? '<span class="hl-gooddays-note">（这类吉日本来就少，' +
              '碰上就别错过）</span>' : '') +
          (_sunk ? '<span class="hl-gooddays-note">（另 ' + _sunk +
            ' 天逢凶日未列出）</span>' : '') +
          _hlCalBtn(_gsc, _gsrc, _days, 'yi');
        if (box.nextSibling) box.parentNode.insertBefore(tip, box.nextSibling);
        else box.parentNode.appendChild(tip);
        tip.querySelectorAll('[data-hldate]').forEach(function (b) {
          /* R230v（R34-#6）：吉日 chip 也走取最新排队，不再吞点。 */
          b.addEventListener('click', function () { _hlDayChipGo(b); });
        });
      }).catch(function () { /* 网络抖动：不弹不阻，判词本身已够用 */ });
    }
    var _ai2 = document.getElementById('hlAskInput');
    if (_ai2 && _askKeep) _ai2.value = _askKeep;   /* R228c：输入框保活回填 */
    /* R232c（R41-P2-1）：dailyRecall 暂存的待问句——卡渲完消费一次，
     * 自动填+真问（首次进黄历页也能接上）。 */
    if (window.__pendingHlAsk && _ai2) {
      var _pq = window.__pendingHlAsk;
      window.__pendingHlAsk = null;
      _ai2.value = _pq;
      var _ab0 = document.getElementById('hlAskBtn');
      if (_ab0) _ab0.click();
    }
    if (_hlBox) { _hlBox.classList.remove('is-loading'); _hlBox.style.pointerEvents = ''; }   /* v5-fix：释放 loading 态 */
    /* v5（用户反馈）：chip 快选/场景选择/问一嘴复查一律原位刷新；
     * 只有显式点「查这一天」或首查才滚动到结果。 */
    if (reveal !== false) revealResult('hlResult');
    else if (_keepSy != null) {
      /* v5-fix：原位恢复同样用双重确认（同帧锚定会吞掉第一次滚动，见 revealResult 注） */
      var _t = Math.max(0, _keepSy);
      var _confirm2 = function () {
        if (Math.abs(window.scrollY - _t) > 4) window.scrollTo({ top: _t, behavior: 'auto' });
      };
      requestAnimationFrame(function () { requestAnimationFrame(_confirm2); });
      setTimeout(_confirm2, 260);
    }
    rememberResult('huangli', j, '');
    /* R229z续25：黄历分享图——与六爻同模式，原位刷新时旧钮随整卡重渲消失，
     * 每次渲后重新挂一个（幂等：旧钮若还在就跳过）。 */
    var hlShareBox = el('hlResult');
    /* R2343（R58-P1-2 防线）：渲染辅助炸了不能伪装成「查询失败」
     * ——卡已成功渲出，chips 挂掉只当没有足迹行。 */
    try { _hlAskChipsRender(); } catch (eChips) {}   /* R230z */
    if (hlShareBox && !document.getElementById('shareHuangli')) {
      var hlBtn = document.createElement('button');
      hlBtn.className = 'ghost fav-btn'; hlBtn.type = 'button';
      hlBtn.id = 'shareHuangli'; hlBtn.title = '生成分享图';
      hlBtn.textContent = '📸 分享图';
      hlBtn.style.margin = '10px 0 0';
      hlShareBox.appendChild(hlBtn);
      hlBtn.addEventListener('click', function () { downloadPoster(j, 'huangli'); });
    }
  } catch (e) {
    if (_hlBox) { _hlBox.classList.remove('is-loading'); _hlBox.style.pointerEvents = ''; }
    /* R230v（R34-#12）：原位刷新失败保留旧卡——错误条叠在卡片上方
     * +重试钮，不再整卡替换（旧结果里的场景 chips/问一嘴框不丢）。 */
    if (reveal === false && _hlBox && _hlBox.children.length) {
      var _errBar = _hlBox.querySelector('.hl-fetch-err');
      if (!_errBar) {
        _errBar = document.createElement('div');
        _errBar.className = 'no-evidence hl-fetch-err';
        _hlBox.insertBefore(_errBar, _hlBox.firstChild);
      }
      _errBar.innerHTML = esc('刷新失败：' + _humanizeErr(e.message)) +
        ' <button type="button" class="ghost" data-retry style="margin-left:8px;">🔄 重试</button>';
      var _rb = _errBar.querySelector('[data-retry]');
      if (_rb) _rb.addEventListener('click', function () {
        _errBar.remove();
        doHuangli(offset, reveal, spokenWord);
      });
    } else {
      failWithRetry('hlResult', '查询失败：' + e.message,
                    function () { doHuangli(offset, reveal, spokenWord); });
      /* R2343（R58-P2-1）：问一嘴行渲染在结果卡里——断网首查失败时
       * 入口随卡消失。错误态也补一行：点击委托是文档级的，网络恢复
       * 后可直接再试（_hlShowNeutral 在无数据时给中性口径，不崩）。 */
      var _hr = el('hlResult');
      if (_hr && !document.getElementById('hlAskInput')) {
        _hr.insertAdjacentHTML('beforeend',
          '<div class="hl-ask" style="margin-top:10px;display:flex;gap:8px;">' +
          '<input id="hlAskInput" class="hl-ask-input" type="text" maxlength="30" ' +
          'aria-label="问一嘴：哪天适不适合某事" placeholder="问一嘴：哪天适不适合面试/搬家…">' +
          '<button type="button" id="hlAskBtn" class="hl-ask-btn">问</button></div>');
      }
    }
  }
}

﻿/* v3（P7）：chip 快选事件 */
(function () {
  'use strict';
  function bindHlChips() {
    var box = document.getElementById('hlChips');
    if (!box || box.dataset.v3bound === '1') return;
    box.dataset.v3bound = '1';
    box.addEventListener('click', function (ev) {
      var btn = ev.target.closest('.hl-chip');
      if (!btn || btn.id === 'hlPickBtn') return;
      /* R230v（R34-#6）：在途不再拦——doHuangli 取最新排队，点中的
       * chip 立即高亮，旧响应落地即被新查询覆盖。 */
      _HL.keepSy = window.scrollY;   /* v5-fix：关抽屉会压短页面发生钳位，先把滚动位存下来 */
      box.querySelectorAll('.hl-chip').forEach(function (c) { c.classList.remove('active'); });
      btn.classList.add('active');
      document.getElementById('hlPickDrawer').open = false;
      doHuangli(Number(btn.dataset.hloffset), false);   /* v5：原位刷新不拽顶 */
    });
    var pick = document.getElementById('hlPickBtn');
    if (pick) pick.addEventListener('click', function () {
      var dr = document.getElementById('hlPickDrawer');
      if (dr) {
        dr.open = !dr.open;
        /* R228n：disclosure 钮同步 aria-expanded（读屏知道开/合） */
        pick.setAttribute('aria-expanded', String(dr.open));
      }
    });
    /* R233f（R43-P2-12）：原生点 <summary>/chip 关抽屉都不走 pick 的
     * click——统一听抽屉 toggle 事件回写 aria-expanded。 */
    var _hpd = document.getElementById('hlPickDrawer');
    if (_hpd) _hpd.addEventListener('toggle', function () {
      if (pick) pick.setAttribute('aria-expanded', String(_hpd.open));
    });
    /* R228c：#hlSubmit 原在这里和 initDivination 的 on('hlSubmit', …)
     * 双绑定——每次「查这一天」发两遍请求。保留 on() 一处（还会带
     * 在途防重），这里不再绑。抽屉由 doHuangli 自选日期路径负责关闭。 */
    /* v5-fix：委托容器必须先取到再绑——原写法 scenes.addEventListener 在
     * var scenes 赋值前执行（var 提升 → undefined），首加载即 TypeError，
     * 「问一嘴」与场景点选两套委托全都绑不上。 */
    var scenes = document.getElementById('hlResult');
    /* v5：问一嘴——把问题里的场景词映射成黄历词再判定；
     * 绑定在 #hlResult 容器上（委托），结果重渲染后仍然有效。 */
    /* R228c：问一嘴补 Enter——输入框随卡重渲染重建，keydown 委托绑在
     * #hlResult 容器上才活得久（与 click 委托同位）。 */
    if (scenes) scenes.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' || !ev.target || ev.target.id !== 'hlAskInput') return;
      ev.preventDefault();
      var _ab = document.getElementById('hlAskBtn');
      if (_ab) _ab.click();
    });
    if (scenes) scenes.addEventListener('click', function (ev) {
      if (!ev.target.closest('#hlAskBtn')) return;
      /* R230v（R34-#6）：在途不拦——问一嘴请求进取最新队列。
       * R2355（R111-P2-4）：同一句话 800ms 内连点吞掉——重复发同样的
       * resolve+huangli 对，慢网排队零收益；不同问题照走最新覆盖。 */
      var inp = document.getElementById('hlAskInput');
      var q = inp ? zwClean(inp.value) : '';   /* R230k */
      var _now0 = Date.now();
      if (q && q === _HL.lastAskQ && _now0 - (_HL.lastAskT || 0) < 800) return;
      _HL.lastAskQ = q; _HL.lastAskT = _now0;
      if (!q) {
        if (inp) inp.placeholder = '先输入想问的事，比如：今天适不适合面试';
        /* R230f续2（R16-P2-4）：placeholder 若已是这段文字则界面纹丝不动，
         * 加一张 toast 让空提交有可感反馈。 */
        showToast('先写一句想问的事再问我哦', 'info');
        return;
      }
      /* R2997（巡#414）：危机/敏感披露在剥词判定前接住，且不落足迹——
       * 「查出肿瘤了哪天复查好」此前剩词进 affair/中性判定卡，黄历对
       * 重病/侵害问题给宜忌（或留「X天前你问了…」披露回显）都不该发生，
       * 与 chat/feCrisis、塔罗 feSensitive 同口径的确定性转介。 */
      if (feCrisis(q)) {
        _HL.scene = ''; _HL.findMode = false;
        _hlShowLine(_CRISIS_FE_REPLY);
        return;
      }
      if (feSensitive(q)) {
        _HL.scene = ''; _HL.findMode = false;
        _hlShowLine(_SENSITIVE_CHAT_REPLY);
        return;
      }
      /* R230z（R36-P2-5）：足迹落库——记问题+被问的目标日。
       * R3323-P3-3：chip 日期前缀要用「解析后的目标日」——此前统一
       * 拿导航前显示日，日期词改写分支里问句与日期错位
       * （「01-01 破土哪天好」「10-11 明天适合搬家吗」）。 */
      /* R2349k（R72-B4）：足迹记两个日子——d 是被问的卡面日（chip 前缀
       * 用），a 是问的那一天（接续条「X天前你问了」的锚——此前锚在
       * d 上，正在翻未来日时「刚才问的」会算成「几天前」。 */
      var _hd0 = document.querySelector('#hlResult .hl-head div');
      var _ds0 = _hd0 ? _hd0.textContent.trim() : '';
      var _askD0 = /^\d{4}-\d{2}-\d{2}$/.test(_ds0) ? _ds0 : todayIso();
      var _logQ = function (_dd) {
        _hlAskLog(q, _dd || _askD0, todayIso());
      };
      /* R2349（R64-P1-3/P1-5）：事项词识别改「词表子串命中，长词优先」
       * ——与后端 _CHAT_SCENE_TERMS→_HUANGLI_VOCAB 同序同口径。此前
       * KNOWN 只有 25 词，chat 端 80+ 键能命中而 UI 落中性卡，同一
       * 问题两链判定不一致（审计实测 5 条分裂）。 */
      var KNOWN = Object.keys(HL_SCENE_ALIAS).concat([
        '上任','乘船','修造','入学','入宅','冠笄','出官','动土','塞穴',
        '嫁娶','安床','安葬','平整','开仓','开市','捕捉','栽种',
        '求医疗病','求名','求嗣','治病','狩猎','田猎','畋猎','登山',
        '破土','破屋坏垣','祈福','祭祀','移徙','立券','筑堤','纳财',
        '行丧','解除','诉讼','谒贵','进人口'
      ]).sort(function (a, b) { return b.length - a.length; });
      var qn = _t2s(q);   /* R229d：繁中归一后再匹配词表/抽词（原文保留给日期词与展示） */
      var hitName = '';
      for (var i = 0; i < KNOWN.length; i++) { if (qn.indexOf(KNOWN[i]) !== -1) { hitName = KNOWN[i]; break; } }
      /* R227b：词表外的说法也抽事项词，进「没直接提到=中性」判定；
       * 完全抽不出词（「今天怎么样」）→ 给当日主推 + 引导，不死拒。
       * R227b-fix：日期词真生效——「明天适合出行吗」翻明天的黄历再判，
       * 不再拿当前显示日充数（off=null 才按显示日）。 */
      var sc = hitName || _hlExtractScene(qn);
      /* R229c（R5 审计 P2）：抽出来的是乱码/纯外文（'asdf'）时不原样回显
       * 进判定卡，回退中性「这件事」——仍给出当日宜忌判定。 */
      if (sc && !/[一-鿿]/.test(sc)) sc = '这件事';
      /* R2349（R64-P1-6）：找日问法标记——「哪天X好」判词改日子清单口径 */
      _HL.findMode = /哪天|什么时候|啥时候|几时|几号/.test(qn) && !!sc;
      window.__hlBirthdayNA = false;
      var off = _hlDayOffset(q);
      if (window.__hlBirthdayNA) {
        /* R2349（R64-P1-4）：「生日」无档案——明说解不动+指路档案位；
         * 不按今天替她判（静默判错天比不答更伤）。 */
        /* R2350f（R102-P2-6）：原指路「我的小档案」——无档案用户首页
         * 根本没有这张卡（_renderMeStrip 整体隐藏），指引失效。真正
         * 入口是日卡 meta 的「存个生日」CTA。 */
        showToast('你的生日还没存，首页日卡里点「存个生日」填一下，我就能翻那天的黄历', 'info');
        _HL.scene = '';
        _hlShowNeutral();
        _logQ();
        return;
      }
      /* R229z：节日/农历等本地解不动的日期词——_hlDayOffset 返回 null 且
       * 词表命中时走 /api/huangli/resolve_date；解出翻页，解不出回退
       * 显示日（与既有 off=null 路径等价）。 */
      if (off == null && _HL_COMPLEX_DATE.test(q)) {
        /* R2400（R124-P2-6）：复杂日期词要等 resolve_date 往返，
         * 慢网下此前零反馈——先吱一声再翻。 */
        showToast('帮你翻那天…', 'info');
        api('/api/huangli/resolve_date?q=' + encodeURIComponent(q) +
            '&base=' + todayIso(),   /* R230l（R24-P3-4） */
            { silent: true }).then(function (r) {
          /* R2349k（R72-A3）：词命中但日子不存在（下个月31号）——
           * 如实提示，不回退显示日乱判。 */
          if (r && r.invalid) {
            showToast(r.invalid, 'warn');
            var _v0 = document.getElementById('hlVerdict');
            if (_v0) _v0.textContent = r.invalid;
            /* R3323-P3-4：invalid 落地时清旧吉日条+旧场景态——
             * 「没这天」与「近期适合X」不能同屏共存。 */
            _HL.scene = ''; _HL.findMode = false;
            var _gd0 = document.querySelector('.hl-gooddays');
            if (_gd0) _gd0.remove();
            _logQ();
            return;
          }
          var off2 = null;
          if (r && r.date) {
            var rp = r.date.split('-');
            var _t0 = new Date(); _t0.setHours(0, 0, 0, 0);
            off2 = Math.round((new Date(+rp[0], +rp[1] - 1, +rp[2]) - _t0) / 86400000);
          }
          _HL.scene = sc || '';
          _logQ((r && r.date) || '');
          if (off2 != null) {
            if (!sc) _HL.pendingAskNote = true;
            _HL.keepSy = window.scrollY;
            doHuangli(off2, false, r.spoken || null);
          } else if (!sc) {
            _hlShowNeutral();
          } else {
            var hd = document.querySelector('#hlResult .hl-head div');
            var d3 = hd ? hd.textContent.trim() : '';
            if (/^\d{4}-\d{2}-\d{2}$/.test(d3)) {
              var p3 = d3.split('-');
              el('hl_year').value = p3[0];
              el('hl_month').value = Number(p3[1]);
              el('hl_day').value = Number(p3[2]);
            }
            doHuangli(null, false);
          }
        }).catch(function () {
          /* R229z续13：resolve_date 离线/不可达——节日词本地解不出也不能
           * 静默；回退当前显示日判定（无事项词走中性卡）。 */
          _logQ();
          if (sc) doHuangli(null, false);
          else _hlShowNeutral();
        });
        return;
      }
      if (!sc) {
        _HL.scene = '';
        if (off != null) {
          _HL.pendingAskNote = true;
          _HL.keepSy = window.scrollY;
          doHuangli(off, false);
          return;
        }
        _hlShowNeutral();
        _logQ();
        return;
      }
      _HL.scene = sc;
      if (off != null) {
        _HL.keepSy = window.scrollY;
        var _tD = new Date(); _tD.setDate(_tD.getDate() + off);
        _logQ(_tD.getFullYear() + '-' + String(_tD.getMonth() + 1).padStart(2, '0') +
              '-' + String(_tD.getDate()).padStart(2, '0'));
        doHuangli(off, false);
        return;
      }
      _logQ();
      var head2 = document.querySelector('#hlResult .hl-head div');
      var ds2 = head2 ? head2.textContent.trim() : '';
      if (/^\d{4}-\d{2}-\d{2}$/.test(ds2)) {
        var pp = ds2.split('-');
        el('hl_year').value = pp[0]; el('hl_month').value = Number(pp[1]); el('hl_day').value = Number(pp[2]);
        doHuangli(null, false);
      } else {
        doHuangli(null, false);
      }
    });
    if (scenes) scenes.addEventListener('click', function (ev) {
      /* R3261（R14）：「到时候小满问问我」——把问的未来事写进
       * chat:events，隔天空态跟进管线（R7）自动接上。 */
      var _fb = ev.target.closest('#hlFollowBtn');
      if (_fb) {
        try {
          var _ek = (_fb.dataset.d || '') + '·' + (_fb.dataset.sc || '');
          var _ea = JSON.parse(localStorage.getItem('chat:events') || '[]');
          if (!Array.isArray(_ea)) _ea = [];
          var _dup = _ea.some(function (x) {
            return x && x.k === _ek &&
              (Date.now() - (x.ts || 0)) < 7 * 864e5;
          });
          if (!_dup) {
            _ea.unshift({ k: _ek, ts: Date.now(), d: todayIso(),
                          asked: 0, closed: 0 });
            /* R3306-P2：并集写。 */
            _lsUnionWrite('chat:events', _ea,
              function (x) { return x && x.k; }, 10);
          }
          _fb.textContent = '✅ 记下啦，到时候小满问你';
          _fb.disabled = true;
        } catch (eFB) {}
        return;
      }
      var s = ev.target.closest('.hl-scene');
      if (!s) return;
      /* R230v（R34-#6）：场景翻转+取最新排队——旧响应落地即被新查询
       * 覆盖，不再出现「标记翻了卡没换」。 */
      _HL.scene = (_HL.scene === s.dataset.scene) ? '' : s.dataset.scene;
      /* 用最后请求的日期重渲染：读 hlResult 头部日期回填 */
      var head = document.querySelector('#hlResult .hl-head div');
      var ds = head ? head.textContent.trim() : '';
      if (/^\d{4}-\d{2}-\d{2}$/.test(ds)) {
        var p = ds.split('-');
        el('hl_year').value = p[0]; el('hl_month').value = Number(p[1]); el('hl_day').value = Number(p[2]);
        doHuangli(null, false);   /* v5：自选日期读输入 + 原位刷新 */
      }
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bindHlChips);
  else bindHlChips();
})();


/* ── 收藏 / 新闻 ──────────────────────────────────────────────── */

/* R219b（P0-4 用户裁决）：「我的解读」历史记录功能整体删除。
 * 原 loadHistory / fmtHistTime / showHistoryDetail / deleteHistory /
 * fetchHistory / loadRecent / __histPage / __histCache 全部移除；
 * 后端 /api/history* 端点与 history_db.save_record() 调用同批删除。
 * 用户原话：不记录，浪费内存，后续会建用户隔离数据库。 */

/* R208b：loadFavorites/addFavorite/removeFavorite 函数体已清空（UI 区块
 * 按用户裁决删除）。保留空函数壳：favBazi 等调用点零改动，后端
 * /api/user/prefs 零改动——需要时按用户指示再恢复 UI。 */
async function loadFavorites() {}
async function addFavorite() { return false; }
async function removeFavorite() {}

/* R208b：loadNews 随「今日关注」面板删除（用户裁决）；
后端 /api/external/news 零改动。 */

/* ── 内部标签页（R000a-03：九个 .rtab + 三个 data-rsec2 全无绑定）──── */

function activateRsec(secId) {
  document.querySelectorAll('.rtab[data-rsec]').forEach(function (b) {
    var on = b.dataset.rsec === secId;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', String(on));   /* R228d：激活态读屏可知 */
  });
  document.querySelectorAll('.rsec').forEach(function (s) {
    s.classList.toggle('active', s.id === secId);
  });
  /* R2343（R58-P1-3）：线程 tab 此前激活时从不拉列表——已有线程
   * 完全隐身，断网失败与「真空」不可区分。ph-empty 占着位才拉，
   * 正在看详情/刚建好线程的回执不覆盖。 */
  if (secId === 'rsec-threads') {
    var _tr = el('threadResult');
    /* R2349z（R96-P1-1c）：详情态（有 .thread-note 块）再点 tab
     * 也回列表——此前只能刷新页面。 */
    if (_tr && (_tr.querySelector('.ph-empty') || !_tr.innerHTML.trim() ||
                _tr.querySelector('.thread-note'))) {
      guardedCall('threads-load', function () {
        /* R2502：走 _threadListPaint——点进详情/删线程在途时再点 tab
         * 不再后到覆盖。 */
        return _threadListPaint().catch(function (e) {
          /* R2400（R124-P2-7）：重拉失败此前留着「还没有线程」的陈旧
           * 空态——与「拉不动」不可区分，如实说一句。 */
          paint('threadResult', '<div class="no-evidence">线程列表这趟没拉上来' +
            (e && e.message ? '：' + esc(_humanizeErr(e.message)) : '') +
            '，网好了再点一下这个页签</div>');
        });
      });
    }
  }
}

/* data-rsec2 值 → 面板 id + 加载函数。
 * 键必须与 index.html 的 data-rsec2 逐字一致，而那三个值又被审查轨的
 * probes/probe_ui_smoke.py:103 当选择器用（docs/PHASE.md 闸门 3）——
 * 它们是**验收契约**，不是内部命名，不要改成驼峰。 */
var BSSEC_PANELS = {
  'bs-structure': { panel: 'bsStructure', load: doBookStructure },
  'bs-chapter': { panel: 'bsChapter', load: doBookChapter },
  'bs-summary': { panel: 'bsSummary', load: doBookSummary }
};

function activateBssec(key) {
  var entry = BSSEC_PANELS[key];
  if (!entry) return;
  document.querySelectorAll('.rtab[data-rsec2]').forEach(function (b) {
    var on = b.dataset.rsec2 === key;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', String(on));   /* R228d */
  });
  document.querySelectorAll('.bssec').forEach(function (s) {
    s.classList.toggle('active', s.id === entry.panel);
  });
  // 切到子标签即按当前书 ID 拉数据——标签本身就是"我要看这个"的意思。
  // R233k（R45-P2）：裸 load 无锁/代际，连点子标签会后到盖先到。
  /* R2349v（R92-P2-2）：书号空时静默无响应——照样调 load()，
   * 让函数内部的「先填书号」fail 生效。 */
  guardedCall('bsload-' + key, function () { return entry.load(); }, null, true);
}

var _PH_OPEN_GEN = 0;   /* R233k：历史复看代际号 */

/* R2363（R116-P0-1）：部署态容器盘每次睡醒清零——排盘台账顺手镜像
 * localStorage（本机=用户设备，云清不丢）。云端正常时云端为准、
 * 顺手把新记录推进镜像；云端空了改读本机留档并标明出处。 */
/* R3316（审-P2）：排盘镜像的北京时间戳——与服务端台账 ts
 * （+08:00 ISO 秒）同格式，混排排序/_fmtWhen/归并窗口才一致。 */
function _phTsNow() {
  var n = new Date(Date.now() + 8 * 3600e3);
  return n.toISOString().slice(0, 19) + '+08:00';
}
/* R3339（审-中）：研究线程本机留档——Render 清盘后列表空壳连
 * 「开过哪些题」都不剩。镜像只存题头（topic/状态/轮数，无
 * turns/claims 原文，字节预算小）；gone 墓碑防删除后复尸。 */
var _THR_MIRROR_KEY = 'threads_mirror_v1';
function _thrMirrorLoad() {
  try {
    var m = JSON.parse(localStorage.getItem(_THR_MIRROR_KEY) || '{}');
    if (m && Array.isArray(m.items)) return m;
  } catch (e) {}
  return { items: [], gone: [] };
}
function _thrMirrorSave(list) {
  try {
    var m = _thrMirrorLoad();
    var have = {}, gone = {};
    (m.gone || []).forEach(function (id) { gone[String(id)] = 1; });
    var out = [];
    (list || []).forEach(function (t) {
      if (t && t.id != null && !gone[String(t.id)]) {
        have[String(t.id)] = 1;
        out.push({ id: t.id, topic: String(t.topic || '').slice(0, 120),
                   status: t.status || 'open',
                   turns: +t.turns || 0, claims: +t.claims || 0,
                   opened_at: t.opened_at || null,
                   updated_at: t.updated_at || null });
      }
    });
    /* 并集：本次过滤状态没列到的旧题保住（open 列表不带 parked/closed）。 */
    (m.items || []).forEach(function (x) {
      if (x && x.id != null && !have[String(x.id)] && !gone[String(x.id)]) {
        out.push(x);
      }
    });
    out.sort(function (a, b) {
      return String(b.updated_at || '').localeCompare(
        String(a.updated_at || ''));
    });
    if (out.length > 15) out = out.slice(0, 15);
    var g = (m.gone || []).slice(-50);
    localStorage.setItem(_THR_MIRROR_KEY,
      JSON.stringify({ items: out, gone: g }));
  } catch (e) {}
}
function _thrMirrorDrop(id) {
  try {
    var m = _thrMirrorLoad();
    m.items = (m.items || []).filter(function (x) {
      return !(x && String(x.id) === String(id));
    });
    m.gone = (m.gone || []).concat([id]).slice(-50);
    localStorage.setItem(_THR_MIRROR_KEY, JSON.stringify(m));
  } catch (e) {}
}
var _PH_MIRROR_KEY = 'paipan_mirror_v1';
/* R2400（R127-P1-1）：墓碑独立小键——镜像整体写不下/被禁写时
 * 「本机已删」仍记得住，不然清盘后删掉的记录借镜像复活。
 * 值记原记录 ts：清盘后 id 重排，同号新记录 ts 不同不被误压。 */
var _PH_MIRROR_DEL_KEY = 'paipan_mirror_del_v1';
function _phMirrorDelLoad() {
  /* R2502：补形状闸——全站镜像读端唯一没校验的地方。键被写成合法但
   * 非对象的 JSON（5/"x"/[1]）时 d[id] 静默写不进 → 墓碑丢失 → 清盘后
   * 已删记录借镜像复活（正是本键要防的事故）。对齐 _phMirrorLoad 等
   * 读端形状校验口径。 */
  try {
    var _d = JSON.parse(localStorage.getItem(_PH_MIRROR_DEL_KEY) || '{}');
    return (_d && typeof _d === 'object' && !Array.isArray(_d)) ? _d : {};
  } catch (e0) { return {}; }
}
function _phMirrorDelMark(id, ts) {
  try {
    var d = _phMirrorDelLoad();
    d[String(id)] = String(ts || '');
    var ks = Object.keys(d);
    if (ks.length > 200) ks.slice(0, ks.length - 200).forEach(function (k) { delete d[k]; });
    localStorage.setItem(_PH_MIRROR_DEL_KEY, JSON.stringify(d));
  } catch (e1) {}
}
var _MIRROR_WARNED = false;
function _mirrorWriteWarn() {
  /* R2400（R127-P2-6）：隐身/禁写态此前静默零持久化——提示一次。 */
  if (_MIRROR_WARNED) return;
  _MIRROR_WARNED = true;
  try { showToast('浏览器不让存本机留档（隐私模式？），关了这页就留不下', 'warn'); } catch (e0) {}
}
function _phMirrorLoad() {
  try {
    var _m = JSON.parse(localStorage.getItem(_PH_MIRROR_KEY) || 'null');
    if (!(_m && _m.items && _m.details)) _m = { items: {}, details: {} };
    _m.del = _phMirrorDelLoad();
    if (!Array.isArray(_m.dorder)) _m.dorder = [];
    /* R2400（R138-P1-2）：镜像键去 rowid 化——清盘后服务端 id 从 1
     * 重排，新记录会按 id 顺序顶掉同号旧归档（无声丢档）。镜像键改
     * `id|ts` 复合；旧版裸 id 键在这里一次性换键。 */
    ['items', 'details'].forEach(function (w) {
      Object.keys(_m[w]).forEach(function (k) {
        if (k.indexOf('|') !== -1) return;
        var _it = _m[w][k];
        delete _m[w][k];
        _m[w][k + '|' + String((_it && _it.ts) || '')] = _it;
      });
    });
    /* R2400（R139-P1-1）：墓碑从「挡写」升级为「摘尸」——跨 tab 删除
     * 与在途响应竞态后，已删条目会借镜像回写复活成幽灵「本机留档」。
     * 读时先按 ts 摘掉与墓碑同代的尸首（同号新记录 ts 不同不殃及）。 */
    Object.keys(_m.del).forEach(function (k) {
      var _ts = _m.del[k], _pfx = k + '|';
      ['items', 'details'].forEach(function (w) {
        Object.keys(_m[w]).forEach(function (mk) {
          if ((mk === k || mk.indexOf(_pfx) === 0) &&
              _m[w][mk] && String(_m[w][mk].ts || '') === String(_ts)) {
            delete _m[w][mk];
          }
        });
      });
    });
    return _m;
  } catch (e0) { return { items: {}, details: {}, del: _phMirrorDelLoad(), dorder: [] }; }
}
/* R3306-P2：同名数组键并发写互丢的通用修法——写前重读存储，
 * 按 idFn 身份并集收进本批没有的远端条目，再落盘。身份在则
 * 以本批为准（覆盖/墓碑语义由调用方先 filter 体现）。 */
function _lsUnionWrite(key, arr, idFn, cap) {
  try {
    var _cur = JSON.parse(localStorage.getItem(key) || '[]');
    if (Array.isArray(_cur)) {
      var _ids = {};
      arr.forEach(function (x) { _ids[idFn(x)] = 1; });
      _cur.forEach(function (x) {
        var _id = idFn(x);
        if (!_ids[_id]) { arr.push(x); _ids[_id] = 1; }
      });
    }
  } catch (eU) {}
  if (cap) arr = arr.slice(0, cap);
  localStorage.setItem(key, JSON.stringify(arr));
}
function _phMirrorSave(m) {
  try {
    /* R3306-P2：多 tab 并发写互丢——写前重读并集合并：本 tab 没有
     * 的远端条目收进来（del 墓碑盖着的除外——同号同 ts 已删），
     * dorder 取并集按我前他后。 */
    var _cur = _phMirrorLoad();
    if (_cur && _cur.details) {
      var _tomb = Object.assign({}, _cur.del || {}, m.del || {});
      ['items', 'details'].forEach(function (w) {
        var _dst = m[w] || {};
        Object.keys(_cur[w] || {}).forEach(function (k) {
          /* 墓碑是「裸 id → 已删那代的 ts」，只压同代尸首——同号新代
           * （服务端 id 重排后新记录）照收，与 _phMirrorLoad 摘尸同口径。 */
          if (!(k in _dst)) {
            var _ts = _tomb[k.split('|')[0]];
            if (!(_ts != null &&
                  String((_cur[w][k] || {}).ts || '') === String(_ts))) {
              _dst[k] = _cur[w][k];
            }
          }
        });
        m[w] = _dst;
      });
      m.del = _tomb;
      var _seen = {}, _ord = [];
      (m.dorder || []).concat(_cur.dorder || []).forEach(function (k) {
        if (!_seen[k] && m.details[k]) { _seen[k] = 1; _ord.push(k); }
      });
      m.dorder = _ord;
    }
    var _s = JSON.stringify(m);
    /* 同值不写——跨 tab storage 事件会因无变化写入互相唤起打转 */
    if (localStorage.getItem(_PH_MIRROR_KEY) !== _s) {
      localStorage.setItem(_PH_MIRROR_KEY, _s);
    }
  } catch (e1) {
    /* R2400（R138-P2-3）：超限改 LRU 逐条淘汰——此前一刀切删全部
     * details，一次超限所有详情蒸发只剩摘要行。 */
    var _ord = (m.dorder || Object.keys(m.details)).slice();
    var _ok = false;
    while (_ord.length && !_ok) {
      var _oldest = _ord.shift();
      delete m.details[_oldest];
      m.dorder = (m.dorder || []).filter(function (k) { return k !== _oldest; });
      try { localStorage.setItem(_PH_MIRROR_KEY, JSON.stringify(m)); _ok = true; }
      catch (e2) {}
    }
    if (!_ok) {
      try { m.details = {}; m.dorder = [];
        localStorage.setItem(_PH_MIRROR_KEY, JSON.stringify(m)); _ok = true;
      } catch (e3) {}
    }
    if (!_ok) _mirrorWriteWarn();
  }
}
function _phMirrorList(m, items) {
  (items || []).forEach(function (it) {
    if (!it || it.id == null) return;
    var _d = m.del[String(it.id)];
    if (_d != null) {
      if (String(it.ts || '') === _d) return;      /* 同一条删过——压 */
      delete m.del[String(it.id)];                /* 同号新记录，墓碑作废 */
      try {                                        /* 盘上小键同步摘 */
        var _dd = _phMirrorDelLoad();
        delete _dd[String(it.id)];
        localStorage.setItem(_PH_MIRROR_DEL_KEY, JSON.stringify(_dd));
      } catch (eD) {}
    }
    /* R2400（R138-P1-2）：复合键 id|ts——同 id 不同 ts 并存不互顶。
     * R3316（审-P2）：loc: 占位行归并——rememberResult 新建记录先落
     * `loc:<type>:<ts>` 本机档；云端行到达时同 type + ts 邻位（150s）
     * 即同条：摘占位行、详情重键到云端 id|ts，列表不再双显。 */
    var _cts = Date.parse(String(it.ts || ''));
    if (!isNaN(_cts)) {
      Object.keys(m.items).forEach(function (lk) {
        var _lo = m.items[lk];
        if (!_lo || String(_lo.id || '').indexOf('loc:') !== 0) return;
        if ((_lo.type || 'bazi') !== (it.type || 'bazi')) return;
        var _lts = Date.parse(String(_lo.ts || ''));
        if (isNaN(_lts) || Math.abs(_lts - _cts) > 150000) return;
        delete m.items[lk];
        /* 摘碑抑尸：_phMirrorSave 落盘前会从盘上副本做并集——
         * 不压同代墓碑，loc 行刚摘又被合并回来。 */
        m.del = m.del || {};
        m.del[String(_lo.id)] = String(_lo.ts || '');
        var _dkOld = String(_lo.id) + '|' + String(_lo.ts || '');
        if (m.details && m.details[_dkOld]) {
          var _mig = Object.assign({}, m.details[_dkOld],
                                   { id: it.id, ts: it.ts });
          delete m.details[_dkOld];
          m.details[String(it.id) + '|' + String(it.ts || '')] = _mig;
          m.dorder = (m.dorder || []).map(function (k) {
            return k === _dkOld
              ? String(it.id) + '|' + String(it.ts || '') : k;
          });
        }
      });
    }
    m.items[String(it.id) + '|' + String(it.ts || '')] = it;
  });
  /* 只留最近 60 条列表摘要 */
  var _ks = Object.keys(m.items).sort(function (a, b) {
    return String(m.items[b].ts || '').localeCompare(String(m.items[a].ts || ''));
  });
  _ks.slice(60).forEach(function (k) { delete m.items[k]; });
}
function _phMirrorDetail(m, rec) {
  if (!rec || rec.id == null) return;
  var _k = String(rec.id) + '|' + String(rec.ts || '');
  m.details[_k] = rec;
  /* 详情最重——按「最近打开」序只留 25 条（dorder 队尾=最新） */
  m.dorder = (m.dorder || []).filter(function (k) { return k !== _k; });
  m.dorder.push(_k);
  while (m.dorder.length > 25) {
    var _old = m.dorder.shift();
    delete m.details[_old];
  }
}
function _phMirrorDrop(m, id) {
  /* R2400（R127-P1-1）：删=摘条目+盖墓碑（记原 ts 防跨代误压；
   * 盘上小键与本对象 del 同步落，免同一次操作里读滞后值）。
   * R2400（R138-P1-2）：复合键按前缀扫——同 id 的所有 ts 代一并摘。 */
  var _pid = String(id), _pfx = _pid + '|', _ts = '';
  Object.keys(m.items || {}).forEach(function (k) {
    if (k === _pid || k.indexOf(_pfx) === 0) {
      _ts = ((m.items[k] || {}).ts || '') || _ts;
      delete m.items[k];
    }
  });
  Object.keys(m.details || {}).forEach(function (k) {
    if (k === _pid || k.indexOf(_pfx) === 0) {
      _ts = _ts || ((m.details[k] || {}).ts || '');
      delete m.details[k];
    }
  });
  _phMirrorDelMark(id, _ts);
  if (m.del) m.del[_pid] = String(_ts || '');
  m.dorder = (m.dorder || []).filter(function (k) {
    return k !== _pid && k.indexOf(_pfx) !== 0;
  });
}
function _phMirrorClear() {
  try { localStorage.removeItem(_PH_MIRROR_KEY); } catch (e0) {}
  try { localStorage.removeItem(_PH_MIRROR_DEL_KEY); } catch (e1) {}
}
/* R2400（R138-P0-1）：从排盘镜像聚合抽过的塔罗牌名——清盘后图鉴
 * 不再谎称 0/78。 */
function _tarotMirrorNames() {
  var _out = {};
  try {
    var _m = _phMirrorLoad();
    Object.keys(_m.details || {}).forEach(function (k) {
      var _r = _m.details[k];
      if (!_r || _r.type !== 'tarot') return;
      var _j = _r.result || {};
      ((_j.draws) || []).forEach(function (d) {
        if (d && d.name) _out[d.name] = 1;
      });
    });
  } catch (e) {}
  return Object.keys(_out);
}
/* R2400（R127-P1-2）：清盘后 id 重排——同号详情若不是同一条
 * （ts 对不上摘要）就是串档旧尸，不能上屏。 */
function _phMirrorDetailFor(m, id) {
  /* R2400（R138-P1-2）：复合键前缀扫——同 id 多代取 ts 最新；
   * 复合键里自带 ts，撞号串档在键层就不存在。 */
  var _pid = String(id), _pfx = _pid + '|';
  var _det = null, _dk = '';
  Object.keys(m.details || {}).forEach(function (k) {
    if (k === _pid || k.indexOf(_pfx) === 0) {
      var _d = m.details[k];
      if (!_det || String(_d.ts || '') > String(_det.ts || '')) {
        _det = _d; _dk = k;
      }
    }
  });
  if (!_det) return null;
  var _sum = (m.items || {})[_dk];
  if (_sum && String(_det.ts || '') !== String(_sum.ts || '')) {
    delete m.details[_dk];   /* 顺手摘尸 */
    return null;
  }
  return _det;
}

/* R2400（R127-P1-3）：本机留档列表渲染——云端空、断网/5xx 两处
 * 共用；渲染了返回 true，空镜像返回 false 走原错误/空态。 */
function _phRenderMirrorList(listEl, m) {
  var _localItems = Object.keys(m.items || {}).map(function (k) {
    return m.items[k];
  }).sort(function (a, b) {
    return String(b.ts || '').localeCompare(String(a.ts || ''));
  });
  if (!_localItems.length) return false;
  /* R3306-P3：断网回落本机留档时别说「清盘」——把普通断网说成
   * 服务重启清掉是谎报，用户会误判数据丢了。 */
  var _phFbTitle = (navigator && navigator.onLine === false)
    ? '📴 离线中，先看你设备上留下的本机备份（未打开过的只有摘要行）'
    : '☁️ 云端记录被服务重启清掉了，下面是你设备上留下的本机备份' +
      '（未打开过的只有摘要行）';
  listEl.innerHTML = '<div class="ph-empty" style="margin-bottom:10px;">' +
    _phFbTitle + '</div>' +
    _localItems.map(function (it) {
      var _t = _fmtWhen(it.ts);
      var _tL = _PH_TYPE_LABEL[it.type] || '记录';
      var _r = (it.result_summary && it.result_summary.paipan_render) || '';
      /* R3200：类型筛选——镜像行同带 data-type。 */
      return '<div class="ph-item" data-id="' + esc(String(it.id)) + '"' +
        ' data-type="' + esc(it.type || 'bazi') + '">' +
        '<div class="ph-head"><span class="ph-type ph-t-' +
        esc(it.type || 'bazi') + '">' + esc(_tL) + '</span>' +
        '<span class="ph-name">' + esc(it.name || ('记录 #' + it.id)) + '</span>' +
        '<span class="ph-ts">' + esc(_t) + '</span>' +
        '<span class="ph-type" style="opacity:.7;">本机留档</span></div>' +
        '<div class="ph-render">' + esc(_r) + '</div>' +
        '<div class="ph-actions"><button type="button" class="ghost ph-open">查看</button>' +
        '<button type="button" class="ghost ph-del">删除</button></div></div>';
    }).join('');
  return true;
}

/* R3249i（UX-AUDIT D·轻测试前门）：五行人格——只填年月日，出
 * 「你是哪一型」人设小卡。走 /api/bazi 同引擎，只渲染 warm 人话层；
 * 「看完整命盘」把生日回填进排盘表单再跳转，不重复发请求。 */
/* R3260（N6 收口）：回流礼遇——存过生日的老客进五行人格页免重填：
 * 表单预填档案值；结果还是空态时自动开测一次（每会话仅一次，
 * 之后手改不自动跑，尊重她「帮别人测」的场景）。 */
var _rgAutoDone = false;
function _rgEnter() {
  var me = null;
  try { me = _meGet('me'); } catch (eM) {}
  if (!me || me.y == null || me.m == null || me.d == null) return;
  var fy = el('rg_year'), fm = el('rg_month'), fd = el('rg_day');
  if (fy) fy.value = String(me.y);
  if (fm) fm.value = String(me.m);
  if (fd) fd.value = String(me.d);
  var _res = el('rgResult');
  if (!_rgAutoDone && _res && _res.querySelector('.ph-empty')) {
    _rgAutoDone = true;
    guardedCall('rgSubmit', doRenge);
  }
}

/* R3336（调研定调·决策神谕）：替你决定——掷筊。传统筊杯三态：
 * 圣筊（一凸一凹，神明点头=放手做）/笑筊（两平面，笑而不答=缓一缓）
 * /阴筊（两凸面，神明摇头=先放下）。概率按传统 1/2·1/4·1/4。
 * 种子=问题+当天——同事同日同筊，确定性即记忆，不落存储。 */
var _JIAO = [
  { key: 'sheng', name: '圣筊', faces: ['yang', 'yin'], verdict: '放手去做',
    lines: [
      '筊杯都点头了——你心里那个答案就是它。',
      '一阴一阳，稳了。这事你早想好，只是要个人推你一把。',
      '去吧，这天替你担着。做完了来打个卡。',
      '筊杯说行。纠结到这儿为止，后面是行动的事。',
      '神明没拦你——那你自己也别拦自己了。',
      '放手做。就算磕绊，也是往对的方向磕。'
    ] },
  { key: 'xiao', name: '笑筊', faces: ['yin', 'yin'], verdict: '缓一缓再说',
    lines: [
      '筊杯笑了——不是不行，是现在火候没到。',
      '两个平面：事没说死，先放着，明天再称称。',
      '笑而不答。可能是你问得太急，先睡一觉再说。',
      '筊杯打太极——这事还有没想清的角落，再盘盘。',
      '不催你。今天先收集信息，答案自己会浮出来。',
      '神明在笑你——问的不是真问题？换个问法明天再来。'
    ] },
  { key: 'yin', name: '阴筊', faces: ['yang', 'yang'], verdict: '先放下',
    lines: [
      '筊杯摇头——这条路今天别走。省下力气给别的事。',
      '两凸相对：硬做只会内耗。放下不是认输，是绕道。',
      '神明摆手。恭喜你，它替你挡了一刀。',
      '这事不对。你心里其实也知道，对不对？',
      '先放一放。真的重要的事，过两天还会回来找你。',
      '筊杯说别去。信它一回，今天的好运在别的事上。'
    ] }
];
function doOracle() {
  var ta = el('orText');
  var q = ta ? String(ta.value || '').trim().slice(0, 60) : '';
  var box = el('orResult');
  if (!box) return;
  if (!q) {
    showToast('先把纠结的事写一句话，筊杯才知道问什么', 'warn');
    if (ta) ta.focus();
    return;
  }
  var seed = q + '|' + todayIso();
  var ji = _JIAO[_hashNum(seed) % 2 === 0 ? 0 : (_hashNum(seed) % 4 === 1 ? 1 : 2)];
  var line = _hashPick(ji.lines, seed + '|' + ji.key);
  box.innerHTML =
    '<div class="or-stage" aria-hidden="true">' +
      '<div class="jiao ' + ji.faces[0] + ' tumble"></div>' +
      '<div class="jiao ' + ji.faces[1] + ' tumble d2"></div></div>' +
    '<div class="or-verdict" id="orVerdict" hidden>' +
      '<div class="or-name">' + ji.name + '</div>' +
      '<div class="or-v">' + ji.verdict + '</div>' +
      '<p class="or-line">' + esc(line) + '</p>' +
      '<p class="or-q">问的是：「' + esc(q) + '」</p>' +
      '<p class="or-note">同一件事今天再掷也是这个筊——心里有数了，别回头问第二遍。</p>' +
      '<div class="ck-wish-actions">' +
        '<button type="button" class="checkin-opt" id="orAgain">再想一件</button>' +
      '</div></div>';
  setTimeout(function () {
    var v = el('orVerdict');
    if (v) v.hidden = false;
    var ag = el('orAgain');
    if (ag) ag.addEventListener('click', function () {
      if (ta) { ta.value = ''; try { ta.focus(); } catch (e2) {} }
    });
  }, 950);
}

async function doRenge() {
  var box = el('rgResult');
  if (!box) return;
  var y = num('rg_year'), m = num('rg_month'), d = num('rg_day');
  if (y == null || m == null || d == null) {
    /* R3320-P2：人格此前空字段只 toast——与兄弟视图同口径
     * 改就地红框+聚焦+就地区提示。 */
    _failField(y == null ? 'rg_year'
      : (m == null ? 'rg_month' : 'rg_day'),
      'rgResult', '年月日都填上才能看型哦');
    return;
  }
  /* R3320-P2：rg_* 无任何本地日期校验——32 号/13 月直达后端
   * 422。与 bazi 同口径前端先拦。 */
  var _rb = _badYmdField('rg_year', 'rg_month', 'rg_day');
  if (_rb) {
    _failField(_rb, 'rgResult',
      '这一天不存在。' + m + ' 月没有 ' + d + ' 号');
    return;
  }
  if (_badRange('rg_year', 1900, 2100)) {
    _failField('rg_year', 'rgResult', '年份要在 1900–2100 之间');
    return;
  }
  busy('rgResult', '小满正在看你是哪一型…');
  try {
    var j = await postJSON('/api/bazi', {
      year: y, month: m, day: d, hour: 12, gender: '女', scope: 'day',
      ask_date: todayIso()
    });
    var w = j.warm || {};
    var pts = Array.isArray(w.reply) ? w.reply : [];
    /* R3251（用户实测「五行人格要形象一点，展示出一个大树或者
     * 拟人化的大树卡通」）：日主五行 → 拟人形象卡——木=抱树苗熊/
     * 火=小太阳熊/土=山丘熊/金=星钻熊/水=水滴熊。结果先看图再看字，
     * 图本身就是人格隐喻，不再是纯文字讲解。 */
    var _rgGan = '';
    try {
      (j.calc.ten_gods || []).forEach(function (t) {
        if (t && t.pos === '日干') _rgGan = String(t.gan || '');
      });
    } catch (eG) {}
    var _rgEl = {'甲':'wood','乙':'wood','丙':'fire','丁':'fire',
      '戊':'earth','己':'earth','庚':'metal','辛':'metal',
      '壬':'water','癸':'water'}[_rgGan] || '';
    var _rgElCn = {'wood':'木','fire':'火','earth':'土',
      'metal':'金','water':'水'}[_rgEl] || '';
    var html = '<div class="card renge-card">';
    if (_rgEl) {
      html += '<div class="rg-hero">' +
        '<img class="rg-persona" src="/static/cream/persona-' + _rgEl +
        '.jpg" alt="你的' + esc(_rgElCn) +
        '型人格形象" loading="lazy" decoding="async" ' +
        'onerror="this.parentNode.remove()">' +
        '<span class="rg-el-tag">' + esc(_rgElCn) + '型' +
        (_rgGan ? ' · 日主' + esc(_rgGan) : '') + '</span></div>';
    }
    var _nick = '';
    for (var _ri = 0; _ri < Math.min(pts.length, 5); _ri++) {
      var _mm = String(pts[_ri]).match(/「(.{2,8}?)」/);
      if (_mm) { _nick = _mm[1]; break; }
    }
    if (_nick) {
      html += '<div class="renge-nick">' + esc(_nick) + '</div>';
    }
    /* R3251 续：五行配比小彩条——calc.five_elements.counts 是确定
     * 性权重（日主计分口径），五根条同场正好落在「多数字才上彩条」
     * 的约定内。图讲「你是谁」，条讲「你是什么料」。 */
    try {
      var _fe = (j.calc.five_elements || {}).counts || {};
      var _feOrder = [['木','wd'], ['火','fr'], ['土','et'],
                      ['金','mt'], ['水','wt']];
      var _feMax = 0.01;
      _feOrder.forEach(function (kv) {
        var _v = parseFloat(_fe[kv[0]]) || 0;
        if (_v > _feMax) _feMax = _v;
      });
      var _bars = '';
      _feOrder.forEach(function (kv) {
        var _v = parseFloat(_fe[kv[0]]) || 0;
        var _pc = Math.round(_v / _feMax * 100);
        _bars += '<span class="rg-fe"><i class="rg-fe-n">' + kv[0] +
          '</i><b class="rg-fe-t"><b class="rg-fe-f f-' + kv[1] +
          '" style="height:' + _pc + '%"></b></b></span>';
      });
      html += '<div class="rg-fes" aria-label="五行配比">' + _bars + '</div>';
    } catch (eFE) {}
    if (w.one_liner) html += '<p class="renge-l0">' + esc(w.one_liner) + '</p>';
    pts.slice(0, 3).forEach(function (ln) {
      html += '<p class="renge-line">' + esc(ln) + '</p>';
    });
    html += '<div class="renge-actions">' +
      '<button type="button" class="ghost" id="rgPoster">📸 分享图</button>' +
      '<button type="button" class="ghost" id="rgXhs">📕 复制小红书文案</button>' +
      '<button type="button" class="ghost" id="rgSpeak">🔊 读我是哪型</button>' +
      '<button type="button" class="ghost" id="rgFull">看完整命盘 →</button>' +
      /* R3260（N6 社交回路）：「帮TA也测一型」——人格测试天然是
       * 接力素材，一键把表单还给 TA 的生日。 */
      '<button type="button" class="ghost" id="rgAgain">帮 TA 也测一型</button>' +
      '</div></div>';
    box.classList.remove('is-working');
    box.innerHTML = html;
    rememberResult('bazi', j, '我是哪一型');
    var _pp = el('rgPoster');
    if (_pp) _pp.addEventListener('click', function () {
      /* R3252：人格分享图带拟人熊——结果卡里已加载的 <img>
       * 直接传进海报 spec.cards（同源直绘），晒出去是形象卡
       * 不是一张字海报。 */
      var _im2 = box.querySelector('.rg-persona');
      /* R3304：renge spec 吃 _nick/_elCn——人格名当海报主标。 */
      var _j2 = (_im2 && _im2.complete && _im2.naturalWidth)
        ? Object.assign({}, j, { _art: _im2, _artCap: _nick,
                                _nick: _nick, _elCn: _rgElCn })
        : Object.assign({}, j, { _nick: _nick, _elCn: _rgElCn });
      var _p = downloadPoster(_j2, 'renge');
      if (_p && _p.catch) _p.catch(function () {});
    });
    var _px = el('rgXhs');
    if (_px) _px.addEventListener('click', function () {
      /* R3263（R19）：五行人格小红书钩子——一键复制晒图文案，
       * 人格测试天然适合「@闺蜜测同款」裂变。 */
      var _line = w.one_liner || '测测你的五行人格';
      /* R3304（审-P1）：clipboard 是纯文本——esc() 会把昵称/判词里的
       * & < > 翻成 HTML 实体原文贴出去。copy 路径用原始值。 */
      var _txt = '✨ 我的五行人格是「' + (_nick || _rgElCn + '型') + '」\n' +
        _line + '\n\n' +
        '在小满的解忧铺测的，你也来测测你的同款型👇\n' +
        (window.location.origin || '') + '/?view=renge&from=share';
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(_txt).then(
            function () { showToast('小红书文案已复制，去发吧～', 'ok'); },
            function () {
              try { _showTextExportModal('小红书文案', _txt, '长按下面文本全选复制'); }
              catch (eM) { showToast('复制失败，可手动长按复制', 'warn'); }
            });
        } else { throw new Error('no clipboard'); }
      } catch (eC) {
        try { _showTextExportModal('小红书文案', _txt, '长按下面文本全选复制'); }
        catch (eM2) { showToast('长按结果手动复制', 'info'); }
      }
    });
    var _ps = el('rgSpeak');
    if (_ps) _ps.addEventListener('click', function () {
      /* R3264（R27）：语音扩展到五行人格——读判词/首句。 */
      var _txt = (_nick || (_rgElCn + '型')) + '。' +
        (w.one_liner || '') + ' ' +
        pts.slice(0, 2).join(' ');
      if (_txt.trim()) _speak(_txt.trim());
    });
    var _ga = el('rgAgain');
    if (_ga) _ga.addEventListener('click', function () {
      /* 帮TA测：表单还回出厂值（不回填我的档案——那是我的型），
       * 结果区清回空态，焦点落回年份格。 */
      var _fy2 = el('rg_year'), _fm2 = el('rg_month'), _fd2 = el('rg_day');
      if (_fy2) _fy2.value = '2000';
      if (_fm2) _fm2.value = '6';
      if (_fd2) _fd2.value = '15';
      box.innerHTML = '<div class="ph-empty">换 TA 的生日——看看 TA 是哪一型～</div>';
      if (_fy2) { _fy2.focus(); try { _fy2.select(); } catch (eS) {} }
      try { box.scrollIntoView({ block: 'nearest' }); } catch (eV) {}
      showToast('生日换成 TA 的，点「看我是哪型」', 'info');
    });
    var _ff = el('rgFull');
    if (_ff) _ff.addEventListener('click', function () {
      /* 回填进排盘表单再切视图——省一次请求，还顺手留了档案。 */
      var _fy = el('year'), _fm = el('month'), _fd = el('day');
      if (_fy) _fy.value = String(y);
      if (_fm) _fm.value = String(m);
      if (_fd) _fd.value = String(d);
      showView('bazi');
      /* 排盘走 form submit 路径（submitBazi）——submit 钮做在途锁键。 */
      guardedCall('submit', submitBazi);
    });
    try { attachChatEntry(box); } catch (eCE) {}
  } catch (e) {
    box.classList.remove('is-working');
    box.innerHTML = '<div class="ph-empty">没算出来：' +
      esc(_humanizeErr(e.message)) + '</div>';
  }
}

/* ── 初始化 ────────────────────────────────────────────────── */

/* R3255（用户实测「和小满聊聊又不能随时随地打开了」）：
 * 聊天侧栏绑定此前住在 initViews 中段——前面任何一段绑定抛错
 * （func-card/scene-chip 委托链），FAB 整条监听就永远挂不上，
 * 聊天入口死透。抽成独立 init 放最前执行，并整体 try 包住：
 * 聊天是慰藉型产品的命根子，它不许被别的功能连坐。 */
function initChatSidebar() {
  var sb = el('recentSidebar');
  var tgl = el('recentToggle');
  var cls = el('recentClose');
  /* R218a-01：遮罩与侧栏同步——点空白处关闭抽屉，pointer-events: auto 时
   * 拦截主区点击、松开时触发 chatClose（视觉上仍透出主区颜色）。 */
  var bd = el('recentBackdrop');
  /* R228d：侧栏关态收编——transform 移屏外后 Tab 序与读屏树仍穿 6 个控件
   *（360px 实测 chatInput 可 focus、焦点矩形 x=-293）。inert 属性为主，
   * CSS visibility:hidden 兜底；chatOpen 直加 .open 的路径也要复位 inert。 */
  /* R228h：Safari<15.5 / 旧 Edge 不认识 inert——设上只是 expando，Tab 仍穿透。
   * 降级：不支持时给栏内可点控件打 tabIndex=-1（开栏恢复）。 */
  if (sb) { sb.inert = true; sb.setAttribute('aria-hidden', 'true'); sbFocusable(sb, false); }
  function _setRecent(open) {
    if (!sb) return;
    sb.classList.toggle('open', open);
    if (!open) sb.style.bottom = '';   /* R3204：关栏清键盘态残留 */
    sb.inert = !open;
    sbFocusable(sb, open);
    sb.setAttribute('aria-hidden', open ? 'false' : 'true');
    if (tgl) tgl.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (bd) bd.classList.toggle('open', open);
    _mainInert(open);   /* R228n：Tab 不许穿透到遮罩下的主区 */
    /* 关闭时若焦点还在侧栏里，还给悬浮入口钮 */
    if (!open && sb.contains(document.activeElement) && tgl) {
      try { tgl.focus(); } catch (e) {}
    }
  }
  /* R228d：Esc 关侧栏（全站此前只有海报层有 Esc）
   * R230d（R16-P2-3）：Esc 同时收拢开着的 <details> 抽屉
   * （hlPickDrawer 等——此前 Esc 对它们无效，只能再点一次开关钮）。
   * R230d（R16-P3-4）：都没有可关的层时 Esc 当「返回首页」——桌面端
   * 习惯语义，与 P0-2 的 popstate 体系同方向。 */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    /* R231f（R38-P3-3）：海报模态开着时 Esc 完全归 _posterOnKey——
     * 原顺序会先误收开着的抽屉再关海报（连坐）。 */
    if (document.getElementById('posterModal')) return;
    /* R233k（R45-§4）：无可关层时 Esc 不再当「返回首页」——输入法
     * 面板里按 Esc 想关候选词，结果整页跳走（输入还在但上下文断）。
     * R233r（R50-#10）：closed 死变量删——判断分支已整段移除。 */
    document.querySelectorAll('details[open]').forEach(function (d) {
      /* R2349o（R78-P1-2）：焦点在抽屉里时 Esc 关抽屉会把它甩回 BODY，
       * 下一次 Tab 从头爬——先还给 summary 再关。 */
      var _ae = document.activeElement;
      if (_ae && d.contains(_ae)) {
        var _sm = d.querySelector('summary');
        if (_sm && _sm.focus) { try { _sm.focus(); } catch (eF) {} }
      }
      d.open = false;
    });
    if (sb && sb.classList.contains('open')) { _setRecent(false); }
  });
  if (tgl) tgl.addEventListener('click', function () {
    /* R210b（US5 用户裁决）：侧栏全宽度抽屉化——桌面端恢复与移动端
     * 一致的 open/closed 抽屉语义（R209b 的 collapsed 常驻方案废除；
     * collapsed 类仍保留为强制收起兼容探针）。 */
    _setRecent(!sb.classList.contains('open'));
  });
  if (cls) cls.addEventListener('click', function () { _setRecent(false); });
  if (bd) bd.addEventListener('click', function () { _setRecent(false); });
  /* R3368（积压-滑关）：移动端抽屉此前只能点 ✕/遮罩关——
   * 右抽屉自然手势是向右滑走。整栏监听，横向位移 >64px 且
   * 横向占优（不抢纵向聊天滚动）即收。 */
  if (sb) {
    var _sw0 = null;
    sb.addEventListener('touchstart', function (e) {
      if (!e.touches || e.touches.length !== 1) { _sw0 = null; return; }
      _sw0 = { x: e.touches[0].clientX, y: e.touches[0].clientY };
    }, { passive: true });
    sb.addEventListener('touchend', function (e) {
      if (!_sw0 || !e.changedTouches || !e.changedTouches.length) {
        _sw0 = null; return;
      }
      var _dx = e.changedTouches[0].clientX - _sw0.x;
      var _dy = e.changedTouches[0].clientY - _sw0.y;
      _sw0 = null;
      if (_dx > 64 && Math.abs(_dx) > Math.abs(_dy) * 1.5) {
        _setRecent(false);
      }
    }, { passive: true });
    sb.addEventListener('touchcancel', function () { _sw0 = null; },
      { passive: true });
  }
  /* R3258（用户实测「点空白不收回」）：遮罩点击此前是唯一关栏路径，
   * 任何 z>65 的层（装到桌面提示 z180/海报层 z200/连签 z290）压在
   * 遮罩上时点击到不了它。补 document 捕获段：按下落在侧栏与悬浮钮
   * 之外就收栏——事件在 document 捕获期先到，叠层挡不住。
   * 例外：「聊聊这件事」入口按钮交给委托链处理（开栏/发上下文），
   * 这里不误收。 */
  var _swallowPt = null;
  document.addEventListener('pointerdown', function (e) {
    if (!sb || !sb.classList.contains('open')) return;
    var t = e.target;
    if (!t || t.nodeType !== 1) return;
    if (sb.contains(t) || (tgl && tgl.contains(t))) return;
    if (t.closest && t.closest('[data-chat-entry]')) return;
    _setRecent(false);
    /* 收栏后同一次点击不许点穿到下层元素（遮罩吃点击的原有
     * 语义）——记下坐标，随后的 click 捕获段吞掉。 */
    _swallowPt = { x: e.clientX, y: e.clientY, ts: Date.now() };
  }, true);
  document.addEventListener('click', function (e) {
    if (!_swallowPt) return;
    var p = _swallowPt;
    _swallowPt = null;
    if (Date.now() - p.ts > 700 ||
        Math.abs(e.clientX - p.x) + Math.abs(e.clientY - p.y) > 40) return;
    e.stopImmediatePropagation();
    e.preventDefault();
  }, true);
  /* R3303-P3：键盘弹起压输入框——原生 visualViewport 滚动在部分
   * 内嵌内核不触发，输入拿到焦点时主动归中；桌面/大屏下
   * scrollIntoView 对已可见元素是近似无操作，零成本。 */
  document.addEventListener('focusin', function (e) {
    var t = e.target;
    if (!t || !t.matches) return;
    if (!t.matches('input, textarea, select')) return;
    try {
      t.scrollIntoView({ block: 'center', behavior: 'smooth' });
    } catch (eF) {}
  });
  /* R219b（P0-4）：侧栏「我的解读」折叠段与计数刷新随历史记录功能删除。 */
}

function initViews() {
  document.querySelectorAll('.func-card').forEach(function (card) {
    card.addEventListener('click', function () {
      window.__lastFuncCard = card;   /* R228d：回首页时焦点归还这里 */
      /* R2362（用户直报）：data-view="chat" 伪视图——开聊天侧栏不切视图。 */
      if (card.dataset.view === 'chat') { chatOpen(); return; }
      showView(card.dataset.view);
    });
    // 卡片是可点区域，给键盘用户同等入口
    card.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        window.__lastFuncCard = card;
        if (card.dataset.view === 'chat') { chatOpen(); return; }
        showView(card.dataset.view);
      }
    });
  });
  /* R200b（US3）：顶层返回条 → 回首页（簇页/叶页通用） */
  var back = el('viewBack');
  if (back) back.addEventListener('click', function () { showView('home'); });
  /* R3249g（UX-AUDIT B4）：场景快捷条——「心里有事」开聊天并替
   * 她写好第一句；其余直达对应功能视图。 */
  document.querySelectorAll('.scene-chip').forEach(function (chip) {
    chip.addEventListener('click', function () {
      var sc = chip.dataset.scene;
      if (sc === 'chat' || sc === 'money') {
        /* R3259（UX-STRATEGY-NEXT N2）：搞钱大女主是人群第一诉求
         * （事业 76.5%>财 74.9%>爱 49.6%）——全站此前没有一个
         * 事业/财运向入口，直达小满并代写好第一句。 */
        chatOpen();
        var inp = el('chatInput');
        if (inp) {
          inp.value = sc === 'money'
            ? '我最近事业和钱方面的运势怎么样？'
            : '心里有点事，想说给你听';
          guardedCall('chatSendBtn', chatSend);
        }
        return;
      }
      try { showView(sc); } catch (e) {}
    });
  });
  /* 心情周记卡生成钮——view-moodweek 内静态按钮，guardedCall 忙态
   * 覆盖海报懒加载全程。 */
  on('moodWeekShare', function () { return _shareMoodWeek(); });
  /* R3255：侧栏绑定搬去 initChatSidebar()（initViews 之前独立执行）；
   * 「我的解读」折叠段与计数刷新随历史记录功能删除。 */
}

function initBazi() {
  const form = el('form');
  if (form) form.addEventListener('submit', submitBazi);
  ['calendar_type', 'scope'].forEach(function (id) {
    const node = el(id);
    if (node) node.addEventListener('change', syncBaziForm);
  });
  syncBaziForm();
  on('dailyMore', loadDailyDetail);
  /* R3264（R44）：深浅色切换——aa↔dark↔system 轮转，新增跟随系统。 */
  var _tt = el('themeToggle');
  if (_tt) {
    var _ttIcon = function () {
      var _ut = uiTheme();
      var _map = { aa: ['🌙', '切换深色模式', 'false'],
                   dark: ['☀️', '切回浅色模式', 'true'],
                   system: ['🌓', '跟随系统', 'false'] };
      var _st = _map[_ut] || _map.aa;
      _tt.textContent = _st[0];
      _tt.setAttribute('aria-label', _st[1]);
      _tt.setAttribute('aria-pressed', _st[2]);
    };
    _ttIcon();
    _tt.addEventListener('click', function () {
      var _next = { aa: 'dark', dark: 'system', system: 'aa' };
      var _t = _next[uiTheme()] || 'dark';
      applyTheme(_t);
      _ttIcon();
      var _msg = { aa: '回到奶油白啦',
                   dark: '夜间模式开啦～看着不累眼睛',
                   system: '以后跟着系统走啦' };
      showToast(_msg[_t] || '主题已切换', 'info');
    });
  }
  /* R206b（US1）：聊天抽屉绑定。chatEntry 是动态按钮（结果区重绘），
   * 用委托绑到 document。 */
  document.addEventListener('click', function (e) {
    /* R230t（R33-P1-1）：.chat-entry 是样式类，换一批/AI点评也在用——
     * 委托判定改走 data-chat-entry，误伤才停止（实测点「换一批」
     * 会拉开聊天侧栏还自动发一条上下文消息）。 */
    if (e.target.closest && e.target.closest('[data-chat-entry]')) {
      /* R3244（用户实测「聊聊想点开时点不开」）：此前整段包在
       * chatSendBtn 锁里——AI 回复在途（最长 ~60s）期间点任何
       * 「聊聊这件事」都被静默吞掉，侧栏都不开。拆开：开栏永远
       * 立即执行，仅「自动发上下文」走锁且 queueLatest 补跑最后
       * 一次意图（发完手头这条自动接上下一条）。 */
      chatOpen();
      guardedCall('chatSendBtn', function () {
        autoSendChatContext();
        return Promise.resolve();
      }, e, true);
    }
  });
  on('chatSendBtn', chatSend);
  /* R223b（E-304 P1）：空态话题 chip——点一下把问题填进输入框并直接发送。
   * R3202 修复：委托此前绑在 #chatEmpty 节点本体上——它会被 chatBubble
   * 整块 remove、R3202 重建后是新节点，老监听跟尸体一起没了。挪到
   * 稳定祖先 recentSidebar 上（data-ask 守卫天然跳过 act-chip 等无 ask
   * 属性的 chip）。 */
  var _emptyBox = document.getElementById('recentSidebar');
  if (_emptyBox) _emptyBox.addEventListener('click', function (ev) {
    var chip = ev.target.closest && ev.target.closest('.chat-chip');
    if (!chip || !chip.dataset || !chip.dataset.ask) return;
    var input2 = el('chatInput');
    if (input2) input2.value = chip.dataset.ask;
    /* R3244：在途期点 chip 此前被静默吞——queueLatest 补跑最后
     * 一次意图（发完手头这条自动接发点选话题）。 */
    guardedCall('chatSendBtn', chatSend, ev, true);   /* R230v（R34-#11） */
  });
  var ci = el('chatInput');
  /* R233r（R49-P3-1）：空发后提示语粘住——用户一开始打字就复位。 */
  if (ci) ci.addEventListener('input', function () {
    if (ci.placeholder === '先写点什么再发哦') ci.placeholder = '说说你的心情…';
  });
  if (ci) ci.addEventListener('keydown', function (e) {
    /* R230q：与 chatSendBtn 的 on() 点击同锁——连按 Enter 不再并发发消息 */
    /* R3196：IME 合成期 Enter 是选词确认不是发送——受众全员中文
     * 输入法，不拦会把半句心事直接发出。isComposing||keyCode 229
     * 双口径（老 Android WebView 只给后者）。 */
    if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229)
      guardedCall('chatSendBtn', chatSend, e);
  });
  /* R228q：移动键盘弹出会把侧栏输入框顶出可视区（visualViewport 收缩，
   * 但侧栏是 fixed 布局不跟随）——键盘开合时把输入框滚回视口内。
   * 只在聊天输入聚焦状态下生效；不支持 visualViewport 的环境静默跳过。
   * R2349m（R76-P0-2）：iOS 键盘只缩 visualViewport，fixed 侧栏锚在
   * 不变的 layout viewport——scrollIntoView 对 fixed 元素按构造无效。
   * 改为直接换算侧栏 bottom = 被键盘吃掉的高度。
   * R3211（用户平板实测仍卡）：多信号同步——(a) iPad Safari 不支持
   *   interactive-widget，键盘「收起钮」收键盘时 resize 先到、offsetTop
   *   后归零，eaten 残留 >60 → 底栏恒悬空：加 300ms 延时复算（一个
   *   宏任务内双采样）。(b) vv.scroll/window.resize/focusout 全部挂
   *   同一同步函数，哪条信号先到都能复位。 */
  var _vvSyncT = 0;
  function _vvSync() {
    var sb = document.querySelector('.recent-sidebar');
    if (!sb) return;
    if (!sb.classList.contains('open')) { sb.style.bottom = ''; return; }
    var vv = window.visualViewport;
    var eaten = vv ? Math.max(0, window.innerHeight - vv.height - vv.offsetTop) : 0;
    if (eaten <= 60) { sb.style.bottom = ''; return; }
    /* 键盘弹出：侧栏底抬高到键盘上沿。焦点不在输入框（如选中
     * 了别的控件但键盘仍在）不动布局。
     * R3355（审-低）：原来只认 #chatInput 一个——侧栏里以后再加
     * 输入控件（备忘、笔记）弹键盘也抬底，改成按归属判断。 */
    var _ae = document.activeElement;
    if (!_ae || !sb.contains(_ae) ||
        !/^(INPUT|TEXTAREA|SELECT)$/.test(_ae.tagName)) return;
    sb.style.bottom = eaten + 'px';
    setTimeout(function () {
      var _ae2 = document.activeElement;
      if (_ae2 && sb.contains(_ae2) &&
          /^(INPUT|TEXTAREA|SELECT)$/.test(_ae2.tagName))
        _ae2.scrollIntoView({ block: 'end', inline: 'nearest' });
    }, 250);
  }
  function _vvSyncTwice() {   /* 收键盘竞态：立即一遍 + 等 offsetTop 落定再来一遍 */
    _vvSync();
    clearTimeout(_vvSyncT);
    _vvSyncT = setTimeout(_vvSync, 320);
  }
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', _vvSyncTwice);
    window.visualViewport.addEventListener('scroll', _vvSyncTwice);
  }
  window.addEventListener('resize', _vvSyncTwice);
  /* R3211：焦点离开输入框（用户点了键盘收起钮/侧栏其他位置）→ 延时复位，
   * 键盘收起动画期间 vv 还在半路，320ms 窗口正好兜住。 */
  var _ci = el('chatInput');
  if (_ci) _ci.addEventListener('focusout', function () {
    setTimeout(_vvSync, 300);
  });
  /* R3213：键盘已在弹起态（焦点先在别的输入框）再点聊天框时 vv 不再
   * 发 resize——focusin 主动补一次同步，否则侧栏底被键盘盖住。 */
  if (_ci) _ci.addEventListener('focusin', function () {
    _vvSyncTwice();
  });
}

function initReading() {
  on('searchBtn', doSearch);
  on('researchBtn', doResearch);
  on('addrBtn', doAddr);
  on('compareBtn', doCompare);
  on('worksBtn', doWorks);
  on('threadBtn', doThread);
  on('cwBtn', doCompareWorks);          // R000a-02
  on('conceptBtn', doConcept);          // R000a-02

  /* R2349v（R92-P2-1）：编址方式切换时收起无关字段——此前五个字段
   * 全摆着，填错的参数会原样进 query（aguan/ayao 对 bcv 是无效参）。 */
  /* _ASCHEME_FIELDS 已提为模块级（doAddr 复用同一张白名单）。 */
  var _asch = el('ascheme');
  if (_asch) {
    /* R3369（审-P1-2）：字段 label/placeholder 随 scheme 换——
     * 「卷名（圣经用）」钉死时选剧本只能瞎猜填什么。 */
    var _ASCHEME_HINT = {
      bcv:    { aname: ['卷名（圣经用）', '如：创世记（Genesis）'],
                aaddr1: ['第几章', '如：12'],
                aaddr2: ['第几节（可空）', '如：3'] },
      play:   { aname: ['剧名（英文原名）', '如：HAMLET'],
                aaddr1: ['第几幕', '如：1'],
                aaddr2: ['第几场（可空）', '如：2'] },
      euclid: { aname: ['卷名（英文）', '如：Book 1'],
                aaddr1: ['第几条定义（可空）', '如：1'],
                aaddr2: ['命题号（罗马数字）', '如：I'] }
    };
    var _syncAddrFields = function () {
      var keep = _ASCHEME_FIELDS[_asch.value] || [];
      ['aguan', 'ayao', 'aname', 'aaddr1', 'aaddr2'].forEach(function (id) {
        var f = el(id);
        var box = f && f.closest('.field');
        if (box) box.style.display = keep.indexOf(id) >= 0 ? '' : 'none';
      });
      var hint = _ASCHEME_HINT[_asch.value] || {};
      ['aname', 'aaddr1', 'aaddr2'].forEach(function (id) {
        var f = el(id);
        if (!f || !hint[id]) return;
        var lb = f.closest('.field') && f.closest('.field').querySelector('label');
        if (lb) lb.textContent = hint[id][0];
        f.placeholder = hint[id][1];
      });
      /* 非 bcv/play/euclid 时把 aname 还原成圣经口径（默认态）。 */
      if (!hint.aname) {
        var _an = el('aname');
        var _anb = _an && _an.closest('.field') &&
          _an.closest('.field').querySelector('label');
        if (_anb) _anb.textContent = '卷名（圣经用）';
        if (_an) _an.placeholder = '如：创世记（Genesis）';
        var _a1 = el('aaddr1');
        var _a1b = _a1 && _a1.closest('.field') &&
          _a1.closest('.field').querySelector('label');
        if (_a1b) _a1b.textContent = '第一级编号';
        if (_a1) _a1.placeholder = '如：12';
        var _a2 = el('aaddr2');
        var _a2b = _a2 && _a2.closest('.field') &&
          _a2.closest('.field').querySelector('label');
        if (_a2b) _a2b.textContent = '第二级编号';
        if (_a2) _a2.placeholder = '如：12';
      }
    };
    _asch.addEventListener('change', _syncAddrFields);
    _syncAddrFields();
  }

  /* R3221：读书「章节」页编址方式→字段显隐——bcv 要卷名（章号卷内计）、
   * file 书要文件名。此前这两类书在此页发不出必填参数必然报错。 */
  var _bssch = el('bsscheme');
  if (_bssch) {
    var _bsSyncFields = function () {
      var v = _bssch.value;
      var fN = el('f_bsname'), fF = el('f_bsfile'), a1 = el('bsaddr1');
      var a1box = a1 && a1.closest('.field');
      if (fN) fN.hidden = v !== 'bcv';
      if (fF) fF.hidden = v !== 'file';
      if (a1box) a1box.hidden = (v === 'file');
    };
    _bssch.addEventListener('change', _bsSyncFields);
    _bsSyncFields();
  }
  /* 手改书号 → 「已选《书名》」提示同步（命中缓存显示书名，否则收起）。 */
  var _bsw = el('bswork');
  if (_bsw) {
    _bsw.addEventListener('input', function () {
      var hint = el('bswork_hint');
      if (!hint) return;
      var t = (typeof _BS_TITLE !== 'undefined' && _BS_TITLE[_bsw.value.trim()]) || '';
      hint.hidden = !t;
      hint.textContent = t ? '已选：《' + t + '》' : '';
    });
  }

  /* R3369（审-低-10）：读书域 Enter 按活跃子页签分发——在章节页
   * 按回车拉章节，在结构页拉结构，知识卡页拉知识卡。 */
  function _bsEnterDispatch() {
    var act = document.querySelector('.bssec.active');
    var id = act && act.id;
    if (id === 'bsChapter') return doBookChapter();
    if (id === 'bsSummary') return doBookSummary();
    return doBookStructure();
  }
  // 回车提交：查询类输入框都该支持（原实现只能点按钮）
  /* R230d（R16-P1-4）：补 tq/bswork/aguan/ayao/aname/aaddr1——这几个输入框
   * 此前按 Enter 无反应，只能伸手去点按钮。
   * R230q（R28-P1-1）：pair[1] 是与对应 on() 按钮共用的锁 key——
   * Enter 连打与连点同防重（bswork 无 on() 按钮，自占一键）。 */
  /* R2350e（R101-P2-4）：rwork/cwa/cwb 是 Enter 死键——补上。 */
  [['rq', 'searchBtn', doSearch], ['rq2', 'researchBtn', doResearch],
   ['cq', 'conceptBtn', doConcept],
   ['cwq', 'cwBtn', doCompareWorks], ['aaddr2', 'addrBtn', doAddr],
   ['rwork', 'searchBtn', doSearch],
   ['cwa', 'cwBtn', doCompareWorks], ['cwb', 'cwBtn', doCompareWorks],
   ['tq', 'threadBtn', doThread],
   /* R3369（审-低-10）：bs* 四框的 Enter 此前各自钉死 handler——
    * 在章节页里按 bswork 的回车却跑去拉结构。统一路由：按当前
    * 活跃子页签分发。 */
   ['bswork', 'bswork', _bsEnterDispatch],
   ['aguan', 'addrBtn', doAddr],
   ['ayao', 'addrBtn', doAddr],
   ['aname', 'addrBtn', doAddr], ['aaddr1', 'addrBtn', doAddr],
   /* R3320-P3：同视图内 Enter 死角补全——rmax/cgua/cyao/bs* 六框
    * 此前按回车无响应（bs 三框喂 doBookChapter 的 addr 参数）。 */
   ['rmax', 'searchBtn', doSearch],
   ['cgua', 'compareBtn', doCompare], ['cyao', 'compareBtn', doCompare],
   ['bsaddr1', 'bschapter', _bsEnterDispatch],
   ['bsname', 'bschapter', _bsEnterDispatch],
   ['bsfile', 'bschapter', _bsEnterDispatch]
  ].forEach(function (pair) {
    const node = el(pair[0]);
    if (node) {
      node.addEventListener('keydown', function (e) {
        /* R3196：IME 选词 Enter 不触发提交（同 chatInput 口径）。 */
        if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229) {
          e.preventDefault();
          guardedCall(pair[1], pair[2], e);
        }
      });
    }
  });

  // 事件委托：标签页 + 动态生成的按钮（书目卡片/线程/历史/收藏）
  document.addEventListener('click', function (e) {
    const rtab = e.target.closest('.rtab[data-rsec]');
    if (rtab) {
      activateRsec(rtab.dataset.rsec);
      return;
    }
    const bstab = e.target.closest('.rtab[data-rsec2]');
    if (bstab) {
      activateBssec(bstab.dataset.rsec2);
      return;
    }
    /* R3212：口吻开关下线——data-voice 元素已全部移除，委托分支删。 */
    // 古籍引文树的三级折叠（005 US2）。事件委托——折叠件是动态生成的，
    // 且渲染会整块重画，逐个绑定处理器会漏。
    const cbtn = e.target.closest('[data-cite-toggle]');
    if (cbtn) {
      toggleCite(cbtn);
      return;
    }

    /* R2349x（R92-P1-4）：引文树「去书库翻」按钮——占卜域→古籍域跳转。 */
    if (e.target.closest('.cite-toread')) {
      showView('read');
      return;
    }
    const workCard = e.target.closest('.work-card[data-work]');
    if (workCard) {
      searchByWork(workCard.dataset.work);
      return;
    }
    /* R3221：结构页 file 书的节行——点了把内部文件名回填进
     * 「文件名」框并跳章节页（不让人抄 KR…_001.txt）。 */
    var secPick = e.target.closest && e.target.closest('.sec-pick[data-secfile]');
    if (secPick) {
      var bf = el('bsfile');
      if (bf) bf.value = secPick.dataset.secfile;
      var bs = el('bsscheme');
      if (bs) { bs.value = 'file'; bs.dispatchEvent(new Event('change')); }
      /* activateBssec 自带加载——点了节行直接出正文。 */
      activateBssec('bs-chapter');
      return;
    }
    /* R3369（审-低-9）：留档行单条移除——不进后端，只落本机镜像。 */
    const threadMirDel = e.target.closest('[data-thread-mir-del]');
    if (threadMirDel) {
      try { _thrMirrorDrop(threadMirDel.dataset.threadMirDel); } catch (eD) {}
      var _mirItem = threadMirDel.closest('.thread-item');
      if (_mirItem) _mirItem.remove();
      showToast('这条留档移掉了', 'success');
      return;
    }
    /* R230q（R28-P1-1b）：线程删除入口——先于 data-thread 判（删按钮
     * 与查看同卡片，避免冒泡误进详情）。 */
    const threadDel = e.target.closest('[data-thread-del]');
    if (threadDel) {
      deleteThread(threadDel.dataset.threadDel, threadDel);
      return;
    }
    const threadBtn = e.target.closest('[data-thread]');
    if (threadBtn) {
      /* R2514（审-次）：无请求去重——连点发 N 个 GET（代际闸保不出
       * 错屏但纯浪费）。同 data-thread-note 的 inflight 先例；
       * 不清复位——代际闸下后到的响应就是正确的，而按钮所在卡片
       * 随列表/详情重画摘除，卡死风险为零。 */
      if (threadBtn.dataset.inflight === '1') return;
      threadBtn.dataset.inflight = '1';
      showThread(threadBtn.dataset.thread).finally(function () {
        threadBtn.dataset.inflight = '';
      });
      return;
    }
    /* R2349v（R92-P1-2）：线程详情内「记一条」+状态切换的委托。 */
    const threadNoteBtn = e.target.closest('[data-thread-note]');
    if (threadNoteBtn) {
      /* R2503（审-P1）：在途零防重——慢网连点写进重复手记，后端不去重
       * 且 claim 级删除不存在（想清只能删整线程）。照 data-qm-fav-del
       * 口径 dataset.inflight 双分支复位。 */
      if (threadNoteBtn.dataset.inflight === '1') return;
      var _ntid = threadNoteBtn.dataset.threadNote;
      var _ntxt = (el('threadNote') || {}).value || '';
      if (!_ntxt.trim()) { showToast('先写一句要记的话', 'info'); return; }
      threadNoteBtn.dataset.inflight = '1';
      /* R2349z（R96-P0-1）：kind 从 'summary'（断言型，必带证据→
       * 永远 400）改 'note'——用户手记专用非断言通道。 */
      postJSON('/api/threads', { kind: 'note', claim: _ntxt.trim(),
        method: 'web-note', thread_id: parseInt(_ntid, 10) })
        .then(function () {
          showToast('记下了～', 'success');
          showThread(_ntid);
        })
        .catch(function (err) { showToast('没记上：' + err.message, 'warn'); })
        /* R2353（R110-P2-7）同口径：.finally 换双分支复位。 */
        .then(function () { threadNoteBtn.dataset.inflight = ''; },
              function () { threadNoteBtn.dataset.inflight = ''; });
      return;
    }
    /* R2349z（R96-P1-1）：线程列表状态过滤 + 详情回列表。 */
    /* R2350a（R94-P2-13）：跨域小链接——结果卡里 data-xview 跳
     * 别的功能视图。 */
    var _xv = e.target.closest('[data-xview]');
    if (_xv) { try { showView(_xv.dataset.xview); } catch (eXV) {} return; }
    const threadFilterBtn = e.target.closest('[data-thread-filter]');
    if (threadFilterBtn) {
      _threadStatus = threadFilterBtn.dataset.threadFilter;
      /* R2502：统一走 _threadListPaint——代际闸防与在途查看/删除
       * 互踩。 */
      _threadListPaint().catch(function () {});
      return;
    }
    if (e.target.closest('[data-thread-back]')) {
      _threadListPaint().catch(function () {});
      return;
    }
    const threadStatusBtn = e.target.closest('[data-thread-status]');
    if (threadStatusBtn) {
      /* R2503（审-P2）：状态钮在途零闸——慢网连点 = N 个 PATCH +
       * N 次重渲闪跳（代际闸挡过期绘制但请求照发）。同 inflight 口径。 */
      if (threadStatusBtn.dataset.inflight === '1') return;
      threadStatusBtn.dataset.inflight = '1';
      var _sp = threadStatusBtn.dataset.threadStatus.split('|');
      api('/api/threads/' + encodeURIComponent(_sp[0]) +
        '?status=' + encodeURIComponent(_sp[1]), { method: 'PATCH' })
        .then(function () {
          showToast({ open: '继续聊～', parked: '先收起，想它再开',
            closed: '这条聊完了' }[_sp[1]] || '好', 'success');
          showThread(_sp[0]);
        })
        .catch(function (err) { showToast('状态没改成：' + err.message, 'warn'); })
        .then(function () { threadStatusBtn.dataset.inflight = ''; },
              function () { threadStatusBtn.dataset.inflight = ''; });
      return;
    }
    const favDel = e.target.closest('[data-fav-del]');
    if (favDel) {
      removeFavorite(favDel.dataset.favDel);
    }
    /* R219b（P0-4）：data-hist / data-hist-del / #histMore 三条历史记录
     * 委托随功能删除（DOM 与后端端点均不复存在）。 */
  });
  /* R228d：work-card 键盘入口——tabindex=0 后 Enter/Space 触发同 click */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var wc = e.target && e.target.closest && e.target.closest('.work-card[data-work]');
    if (!wc) return;
    e.preventDefault();
    searchByWork(wc.dataset.work);
  });
  /* R3321-P1：file 书节行 .sec-pick 同入口——tr 已挂 tabindex/role，
   * Enter/Space 走与 click 委托同一条链。 */
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    var sp = e.target && e.target.closest &&
      e.target.closest('.sec-pick[data-secfile]');
    if (!sp) return;
    e.preventDefault();
    var bf2 = el('bsfile');
    if (bf2) bf2.value = sp.dataset.secfile;
    var bs2 = el('bsscheme');
    if (bs2) { bs2.value = 'file'; bs2.dispatchEvent(new Event('change')); }
    activateBssec('bs-chapter');
  });
}

function initDivination() {
  /* R233k（R45-§3）：铜钱起卦只发 seed，年/月/日/时辰四框填了不入参
   * ——切 coins 时收起，切回时间再展开。 */
  var _lym = el('ly_method');
  if (_lym) {
    var _lyTimeSync = function () {
      var hide = val('ly_method') === 'coins';
      ['ly_year', 'ly_month', 'ly_day', 'ly_hour'].forEach(function (id) {
        var f = el(id);
        if (f && f.closest('.field')) f.closest('.field').style.display = hide ? 'none' : '';
      });
      /* R3259（用户实测「固定编号没用」）：时间起卦按日时推算，
       * seed 压根不入参——抽屉却可填，填了被静默丢弃。对称收起：
       * 哪种方式不吃的输入就不让它露头。 */
      var _sd = el('lySeedDrawer');
      if (_sd) _sd.style.display = hide ? '' : 'none';
    };
    _lym.addEventListener('change', _lyTimeSync);
    _lyTimeSync();
  }
  on('lySubmit', doLiuyao);
  on('dmSubmit', doDream);   /* R3178：解梦 */
  /* R3214：解梦输入区——高频梦 chip 点选即填 + 字数条（400 上限
   * 此前静默截尾，用户不知道被砍）。 */
  var _dmTa = el('dm_text');
  if (_dmTa) {
    _dmTa.addEventListener('input', function () {
      var c = el('dmCount');
      if (c) c.textContent = _dmTa.value.length + '/400';
    });
    var _dmView = document.getElementById('view-dream');
    if (_dmView) _dmView.addEventListener('click', function (ev) {
      var b = ev.target && ev.target.closest
        ? ev.target.closest('.dm-chip') : null;
      if (!b) return;
      _dmTa.value = b.getAttribute('data-dm') || '';
      _dmTa.dispatchEvent(new Event('input', { bubbles: true }));
      try { _dmTa.focus(); } catch (e) {}
    });
  }
  on('hlSubmit', doHuangli);
  /* R3336：替你决定——掷筊三态 + 纠结事 chip 点选即填。 */
  on('orSubmit', function () { return doOracle(); });
  var _orView = document.getElementById('view-oracle');
  if (_orView) _orView.addEventListener('click', function (ev) {
    var b = ev.target && ev.target.closest
      ? ev.target.closest('.or-chip') : null;
    if (!b) return;
    var ta2 = el('orText');
    if (!ta2) return;
    ta2.value = b.getAttribute('data-or') || '';
    try { ta2.focus(); } catch (e) {}
  });
  on('qmSubmit', doQiming);
  on('thSubmit', doTaohua);
  /* R3206：农历历法切换→闰月字段显隐（五处表单共用一套 id 对）。 */
  [['th_cal', 'f_th_leap'], ['qm_cal', 'f_qm_leap'],
   ['hh_a_cal', 'f_hh_a_leap'], ['hh_b_cal', 'f_hh_b_leap'],
   ['b_cal', 'f_b_leap']].forEach(function (pr) {
    var s = el(pr[0]);
    if (s) s.addEventListener('change', function () {
      var f = el(pr[1]);
      if (f) f.hidden = s.value !== 'lunar';
    });
  });
  /* R2502：包一层隔断 click 事件实参——doTarot 的 cards 形参不应
   * 收到 MouseEvent（靠 Array.isArray 收编只是兜底）。 */
  /* R3249i：五行人格轻测试入口 */
  on('rgSubmit', function () { return doRenge(); });
  on('trSubmit', function () { return doTarot(); });
  /* R3249e（UX-AUDIT C·塔罗）：三档快捷钮——抽一张/三张/自己抽，
   * 新客不碰牌阵下拉。按钮仍走 doTarot/_trPickOpen 原有路径。 */
  on('trQ1', function () {
    var s = el('tr_spread'), n = el('tr_n');
    if (s) s.value = '';
    if (n) n.value = '1';
    _trSpreadSync();
    return doTarot();
  });
  on('trQ3', function () {
    var s = el('tr_spread'), n = el('tr_n');
    if (s) s.value = 'time';
    if (n) n.value = '3';
    _trSpreadSync();
    return doTarot();
  });
  on('trQPick', function () { return _trPickOpen(); });
  /* R3368：万圣夜限定入口——10.29–11.1 窗口内显示；点了走
   * 抽一张，问句空着给预填，结果卡带限定条。 */
  /* R3370-P2-4：窗口判定改函数——跨零点开着的页面要复判，
   * init 快照会让 11/2 的页面还挂着限定卡。 */
  var _trHFest = function () {
    var _n0 = new Date(), _m0 = _n0.getMonth() + 1, _d0 = _n0.getDate();
    return (_m0 === 10 && _d0 >= 29) || (_m0 === 11 && _d0 <= 1);
  };
  var _trHBtn = el('trQH');
  if (_trHBtn && _trHFest()) _trHBtn.hidden = false;
  on('trQH', function () {
    /* R3370-P2-4：点击时复判窗口——跨零点页面仍可点但结果
     * 不再冒限定名。 */
    if (!_trHFest()) {
      if (_trHBtn) _trHBtn.hidden = true;
      return;
    }
    var s = el('tr_spread'), n = el('tr_n');
    if (s) s.value = '';
    if (n) n.value = '1';
    _trSpreadSync();
    var _qi = el('tr_question');
    if (_qi && !(_qi.value || '').trim()) {
      _qi.value = '那件我一直不敢问的事';
    }
    window.__trHFest = true;
    return doTarot();
  });
  /* R3325：大众占卜 pick-a-pile——事业/感情/财运三主题，各 3 堆，
   * seed=日期+主题+堆位（同日同堆同牌，可晒同款）；一堆一天定，
   * 选完存 localStorage（换主题互不影响）。 */
  var _PILE_TOPICS = { career: '事业', love: '感情', money: '财运' };
  var _pileTopic = null;
  /* pilePick:YYYY-MM-DD = {topic:{i,d,r}}——日期尾缀吃既有
   * 150 天 GC 与备份前缀管道。 */
  function _pileKey() { return 'pilePick:' + todayIso(); }
  function _pileSeed(topic, idx) {
    var s = 'pile|' + todayIso() + '|' + topic + '|' + idx, h = 0;
    for (var i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return h;
  }
  function _pileAll() {
    try {
      var v = JSON.parse(localStorage.getItem(_pileKey()) || 'null');
      return (v && typeof v === 'object') ? v : {};
    } catch (eP) { return {}; }
  }
  function _pileGet(topic) {
    var v = _pileAll()[topic];
    return (v && typeof v.i === 'number' && v.d) ? v : null;
  }
  function _pileSet(topic, val) {
    try {
      var v = _pileAll();
      v[topic] = val;
      localStorage.setItem(_pileKey(), JSON.stringify(v));
    } catch (eP2) {}
  }
  function _pileRender(topic) {
    document.querySelectorAll('.pile-topic').forEach(function (b) {
      b.classList.toggle('active', b.dataset.ptopic === topic);
    });
    var row = el('pileRow'), hint = el('pileHint'), res = el('pileResult');
    if (row) row.hidden = false;
    if (hint) hint.hidden = false;
    var got = _pileGet(topic);
    /* R3329（审-P3）：脏存档 / 伪造键会让 'ABC'[got.i] 出 undefined
     * 堆名、topic 出 undefined——校验不过按未选处理。 */
    if (!_PILE_TOPICS[topic]) topic = 'career';
    if (got && !(got.i >= 0 && got.i <= 2 && got.d &&
                 typeof got.d === 'object')) got = null;
    document.querySelectorAll('.pile-card').forEach(function (c) {
      var idx = +c.dataset.pile;
      c.classList.toggle('picked', !!(got && got.i === idx));
      c.classList.toggle('dimmed', !!(got && got.i !== idx));
      c.disabled = !!got;
      var im = c.querySelector('img');
      if (got && got.i === idx && got.d && got.d.name) {
        var f = tarotImg(got.d.name);
        if (im && f) {
          im.src = f; im.alt = got.d.name;
          if (!got.d.upright) im.classList.add('is-reversed');
          c.classList.add('revealed');
        }
      } else if (im) {
        im.src = '/static/tarot/card-back.jpg'; im.alt = '';
        im.classList.remove('is-reversed');
        c.classList.remove('revealed');
      }
    });
    if (res) {
      if (got && got.d) {
        var d = got.d;
        res.hidden = false;
        res.innerHTML = '<div class="pile-cardline"><b>' +
          '你选了 ' + 'ABC'[got.i] + ' 堆 · ' + esc(d.name) + '</b>' +
          '<span>' + (d.upright ? '正位' : '逆位') + ' · ' +
          esc(d.upright ? (d.upright_kw || '') : (d.reversed_kw || '')) +
          '</span></div>' +
          (got.r ? '<p class="pile-read">' + esc(got.r) + '</p>' : '') +
          '<button type="button" class="ghost pile-share" id="pileShare">' +
          '📤 分享我这堆</button>' +
          /* R3337（审-中）：pick-a-pile 最大晒点是牌面本身——
           * 补一张带牌面的海报入口（复用塔罗海报管线）。 */
          '<button type="button" class="ghost pile-share" id="pilePoster">' +
          '🖼 存图带走</button>';
        var ps = el('pileShare');
        if (ps && !ps.dataset.bound) {
          ps.dataset.bound = '1';
          ps.addEventListener('click', function () {
            /* R3327-P1-4：堆位入文案（pick-a-pile 晒点=「你选哪堆」）+
             * 回流 CTA + 话题标签。 */
            var t = '今日' + _PILE_TOPICS[topic] + ' · 我选了 ' +
              'ABC'[got.i] + ' 堆，翻出「' + (got.d.name || '') + '」' +
              (got.d.upright ? '正位' : '逆位') + '：' +
              (got.d.upright ? got.d.upright_kw : got.d.reversed_kw) +
              '。你选哪堆？来小满的解忧铺对一对 #塔罗 #大众占卜' +
              /* R3329（审-P3）：回流链接——origin 拼上，贴到小红书
               * 也能点回来。 */
              ' ' + location.origin + '/?view=tarot&from=share';
            var _showTxt = function () {
              /* R3327-P1-5：clipboard 失败把文案渲进可选 textarea，
               * 「长按复制」不再无处下手。 */
              var res2 = el('pileResult');
              if (!res2 || res2.querySelector('.pile-sharetxt')) return;
              var ta = document.createElement('textarea');
              ta.className = 'pile-sharetxt';
              ta.readOnly = true; ta.rows = 3; ta.value = t;
              res2.appendChild(ta);
            };
            try {
              navigator.clipboard.writeText(t).then(function () {
                showToast('牌面文案已复制，发出去喊朋友也来选一堆', 'ok');
              }, function () {
                _showTxt();
                showToast('复制没成功——文案在下面，长按拷走', 'info');
              });
            } catch (eC2) {
              _showTxt();
              showToast('文案在下面，长按拷走', 'info');
            }
          });
        }
        /* R3337：堆牌海报——选中的堆图喂进塔罗海报（_cardImgs 显式供图）。 */
        var pp = el('pilePoster');
        if (pp && !pp.dataset.bound) {
          pp.dataset.bound = '1';
          pp.addEventListener('click', function () {
            var _imgEl = document.querySelector(
              '.pile-card.revealed img');
            downloadPoster({
              spread: '大众占卜 · ' + _PILE_TOPICS[topic],
              question: '',
              draws: [{ name: d.name,
                position: '你选的 ' + 'ABC'[got.i] + ' 堆',
                upright: d.upright }],
              _cardImgs: _imgEl ? [_imgEl] : [] }, 'tarot');
          });
        }
      } else { res.hidden = true; res.innerHTML = ''; }
    }
  }
  document.querySelectorAll('.pile-topic').forEach(function (b) {
    b.addEventListener('click', function () {
      _pileTopic = b.dataset.ptopic;
      _pileRender(_pileTopic);
    });
  });
  document.querySelectorAll('.pile-card').forEach(function (pc) {
    pc.addEventListener('click', function () {
      if (!_pileTopic || _pileGet(_pileTopic)) return;
      var idx = +pc.dataset.pile;
      pc.classList.add('busy');
      api('/api/tarot/draw', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seed: _pileSeed(_pileTopic, idx), n: 1,
                               question: _PILE_TOPICS[_pileTopic],
                               client_date: todayIso() }) })
        .then(function (tj) {
          var d = tj && tj.card;
          if (!d || !d.name) { showToast('这堆没翻开，再点一次', 'warn'); return; }
          var _rl = '';
          try {
            var _rp = (tj.warm && tj.warm.reply) || [];
            /* R3326（审-P1）：reply[0] 是模板头「针对你的问题…每张牌
             * 这样说：」——取第一条非模板句，拿不到再退首行。 */
            var _lines = (Array.isArray(_rp) ? _rp : [_rp])
              .filter(Boolean);
            _rl = _lines.filter(function (l) {
              return String(l).indexOf('每张牌这样说') === -1;
            })[0] || _lines[0] || '';
          } catch (eR2) {}
          _pileSet(_pileTopic, { i: idx, d: d, r: _rl });
          _pileRender(_pileTopic);
        })
        .catch(function (eT) {
          showToast('这堆没翻开：' + (eT && eT.message || '网不稳'), 'warn');
        })
        .finally(function () { pc.classList.remove('busy'); });
    });
  });
  /* R2350k：自己抽——牌扇开合 + 点选委托 + 成局。 */
  on('trPickBtn', _trPickOpen);
  on('trPickGo', _trPickGo);
  /* R2350l：牌阵选了 → 藏张数框（张数跟着牌阵走）。
   * R2354（R112-P1-1）：换阵/换张数时牌扇开着要失效已选列表。 */
  (function(){ var s = el('tr_spread');
    if (s) s.addEventListener('change', function () {
      _trSpreadSync();
      _trPickInvalidate('换了牌阵，手里的牌得重抽');
    }); })();
  (function(){ var n2 = el('tr_n');
    if (n2) n2.addEventListener('input', function () {
      _trPickInvalidate('换了张数，手里的牌得重抽');
    }); })();
  _trSpreadSync();
  (function () {
    var fan = el('trPickFan');
    if (fan && !fan.dataset.bound) {
      fan.dataset.bound = '1';
      fan.addEventListener('click', function (e) {
        var b = e.target.closest('.tr-back');
        if (b && b.dataset.i != null) _trPickTap(+b.dataset.i);
      });
    }
  })();
  /* R2349l（R73-P1-12）：我的牌册——展开抽屉时拉收集清单渲染 78 格。 */
  (function () {
    var dr = el('tarotAlbumDrawer');
    if (dr && !dr.dataset.bound) {
      dr.dataset.bound = '1';
      dr.addEventListener('toggle', function () {
        if (!dr.open) return;
        api('/api/paipan/tarot_collection', { silent: true }).then(function (cj) {
          var box = el('tarotAlbum');
          if (!box || !cj || !Array.isArray(cj.deck)) return;
          var got = {};
          (cj.collected || []).forEach(function (n) { got[n] = 1; });
          var cnt = (cj.collected || []).length;
          /* R2400（R138-P0-1）：清盘后图鉴谎称「0/78 从0点亮」——
           * 但抽过的牌其实躺在排盘镜像详情里（result.draws[].name）。
           * 云端 0 + 镜像有 = 聚合镜像牌名照常渲染，文案说真话。 */
          var _mNames = _tarotMirrorNames();
          var _mirrorOnly = !cnt && _mNames.length;
          _mNames.forEach(function (n) { got[n] = 1; });
          if (_mirrorOnly) cnt = Object.keys(got).length;
          box.innerHTML = '<div class="tarot-album-count">' +
            (_mirrorOnly
              ? '云端牌册被服务重启清掉了，你设备上还亮着 <strong>' +
                cnt + '</strong> / ' + esc(String(cj.total)) + ' 张'
              : '已收集 <strong>' + cnt + '</strong> / ' +
                esc(String(cj.total)) + ' 张：多抽几签，把牌册点亮 ✨') +
            '</div>' +
            '<div class="tarot-album-grid">' +
            cj.deck.map(function (n) {
              /* R2500（R144-P2-3）：已收集格换 mini 牌面缩略图——
               * 78 格全「？」文本收藏感弱，牌册是小红书晒图面。 */
              var _ti = got[n] ? tarotImg(n) : null;
              return '<div class="tarot-cell' + (got[n] ? ' got' : '') +
                '">' +
                (_ti ? '<img class="tarot-cell-img" src="' + esc(_ti) +
                       '" alt="" loading="lazy">' : '') +
                esc(got[n] ? n : '？') + '</div>';
            }).join('') + '</div>';
        }).catch(function () {
          /* R2400（R124-P1-2）：静默 catch 此前抽屉停在
           * 「展开看看收集进度～」假候态——失败了明说。 */
          var _bx = el('tarotAlbum');
          if (_bx) _bx.innerHTML = '<div class="ph-empty" ' +
            'style="padding:12px;">牌册暂时翻不开，合上再开试试</div>';
        });
      });
    }
  })();
  on('hhSubmit', doHehun);
  /* R3160：TA 档案免测入口——「想聊感情/想知道 TA 是怎样的人」不必
   * 先跑一遍合婚：生日+昵称直接落 me:partner（纯 localStorage，
   * 不发请求）。字段还停在出厂示例值就不写——假生日喂给聊天比
   * 没有更糟。受邀模式下 TA=A 侧（发起人）。 */
  on('hhSavePartner', async function () {
    var _p = window.__hhInviteMode ? 'hh_a_' : 'hh_b_';
    /* R3247：明星侧不存档案——公开生日玩梗不写 TA 档；用户改过
     * 明星侧字段（_celebSync 已清标志）按真人数据处理。 */
    _celebSync();
    if (_celebOn(_p === 'hh_a_' ? 'a' : 'b')) {
      showToast('这是明星的公开生日，就不往 TA 档案里存啦～', 'info');
      return;
    }
    if (_fieldsUntouched([_p+'year', _p+'month', _p+'day', _p+'hour', _p+'gender'])) {
      showToast('先填一下 TA 的真实生日再存，现在还是示例值', 'warn');
      return;
    }
    /* R3313（审-P1-3）：原 _meSave 直存 y/m/d——TA 选「农历」的原始
     * 数字被当公历落档，此后聊天 TA 日主/星座/生日倒计时全按错盘跑。
     * 改走统一器：农历先换算成公历坐标+农历原值标注。 */
    var _opts = {
      lunar: val(_p+'cal') === 'lunar',
      y: num(_p+'year'), m: num(_p+'month'), d: num(_p+'day'),
      h: num(_p+'hour'), g: val(_p+'gender') || '女',
      leap: checked(_p+'leap')
    };
    if (val(_p+'name')) _opts.n = val(_p+'name');
    await _meSaveFromBirth('me:partner', _opts);
    showToast('TA 的生日存好啦：只留在这台设备上。之后聊感情，小满能对上 TA 的盘', 'ok');
  });
  /* R3247：明星合盘选择器——抽屉首次拉开才拉名单（vendored 小文件，
   * 本地即发）；搜索框按 名字/tag/note 过滤；点 chip 填 B 侧。 */
  (function () {
    var _drw = el('celebDrawer'), _box = el('celebGrid'),
        _srch = el('celebSearch'), _pkd = el('celebPicked');
    if (!_drw || !_box) return;
    _drw.addEventListener('toggle', function () {
      if (!_drw.open) return;
      if (_CELEBS) {
        _celebRender(_srch ? _srch.value : '');
        return;
      }
      _box.innerHTML = '<div class="ph-empty" style="padding:10px;">' +
        '名单加载中…</div>';
      _celebLoad().then(function (list) {
        if (list && list.length) {
          _celebRender(_srch ? _srch.value : '');
        } else {
          _box.innerHTML = '<div class="ph-empty" style="padding:10px;">' +
            '明星名单没拉下来，刷新再试～</div>';
        }
      });
    });
    if (_srch) {
      _srch.addEventListener('input', function () {
        _celebRender(_srch.value);
      });
    }
    _box.addEventListener('click', function (e) {
      var b = e.target && e.target.closest
        ? e.target.closest('.celeb-chip') : null;
      if (!b) return;
      var nm = b.getAttribute('data-celeb-n');
      var c = (_CELEBS || []).filter(function (x) {
        return x.n === nm; })[0];
      if (c) _celebPick(c);
    });
    if (_pkd) {
      _pkd.addEventListener('click', function (e) {
        if (e.target && e.target.id === 'celebUnpick') _celebClear(true);
      });
    }
  })();
  /* R229z续23（R10-#14）：占卜系视图不是 <form>，输入框回车无响应——
   * 视图级委托：任意 input 按 Enter = 点本视图主提交钮（原生 form 语义）。 */
  var _ENTER_SUBMIT = {
    'view-liuyao': 'lySubmit', 'view-tarot': 'trSubmit',
    'view-qiming': 'qmSubmit', 'view-taohua': 'thSubmit',
    'view-hehun': 'hhSubmit',
    /* R230d（R16-P1-4）：黄历 y/m/d 三个数字框回车=查这一天
     * （hlAskInput 自带 Enter 绑问一嘴，已被下面的 id 排护栏拦住）。 */
    'view-huangli': 'hlSubmit',
    /* R230t（R33-P3-15）：b_* 其实在 view-xingzuo 的 <details> 里、
     * 不在任何 <form> 中——此前回车是死键。xz_* 是 select 不吃此委托。 */
    'view-xingzuo': 'birthSubmit',
    /* R3320-P2：人格视图漏网——Enter 是死键（移动键盘「前往」无效）。 */
    'view-renge': 'rgSubmit'
    /* view-bazi 是真 <form>，Enter 原生已提交。 */
  };
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Enter' || !e.target || e.target.tagName !== 'INPUT') return;
    var v = e.target.closest('.view');
    if (!v || !_ENTER_SUBMIT[v.id]) return;
    if (e.target.id === 'hlAskInput' || e.target.id === 'chatInput') return;
    var b = el(_ENTER_SUBMIT[v.id]);
    if (b && !b.disabled) { e.preventDefault(); b.click(); }
  });
  /* R230d（R16-P1-1）：包装函数必须 return 异步调用——否则
   * Promise.resolve(undefined) 下个微任务就释放 on() 的 _busy 锁，
   * 双击实发两遍请求（实测 xzSubmit/xzNext 各发 2 次）。 */
  on('xzSubmit', function () { return doXingzuo(true); });
  /* R2349l（R73-P1-7）：星座速配——12 星座双 select + 四象兼容判词。 */
  (function () {
    var _SIGNS = ['白羊', '金牛', '双子', '巨蟹', '狮子', '处女',
                  '天秤', '天蝎', '射手', '摩羯', '水瓶', '双鱼'];
    var sa = el('xzm_a'), sb = el('xzm_b');
    if (sa && !sa.options.length) {
      _SIGNS.forEach(function (s) {
        sa.add(new Option(s + '座', s));
        if (sb) sb.add(new Option(s + '座', s));
      });
      if (sb) sb.selectedIndex = 6;   /* 默认你白羊×TA天秤 */
    }
  })();
  on('xzmSubmit', async function () {
    var sa2 = el('xzm_a'), sb2 = el('xzm_b'), box = el('xzmResult');
    if (!sa2 || !sb2 || !box) return;
    /* R2400（R124-P1-3）：钮被 on() 锁但结果区零反馈——慢网下
     * 用户以为没点上。与其他提交同纪律 busy()。 */
    busy('xzmResult', '正在替你们对星盘…');
    try {
      var _rel = el('xzm_rel');
      var mj = await api('/api/xzmatch?a=' + encodeURIComponent(sa2.value) +
                         '&b=' + encodeURIComponent(sb2.value) +
                         (_rel && _rel.value
                          ? '&rel=' + encodeURIComponent(_rel.value) : ''));
      /* R3260：响应不回显 rel——分享图视角行要用，客户端补挂
       * （additive 键，不影响后端契约）。括号写法：点号赋值会被
       * probe_contract 当响应字段读误报。 */
      if (_rel && _rel.value) mj['_rel'] = _rel.value;
      /* R3130：lines 面在时逐行渲（场景+处方+交权），旧响应回退单行。 */
      var _xlines = (mj.lines && mj.lines.length) ? mj.lines : [mj.line];
      /* R3260（同 R2350d 病灶）：busy() 的 is-working 在半透+子元素
       * 禁点——绕过 paint() 直写 innerHTML 必须手动摘，否则合盘卡
       * 出结果后永远灰着（上面那颗「继续聊」按钮点了没反应）。 */
      box.classList.remove('is-working');
      box.innerHTML = '<div class="hh-score" style="margin-top:0;">' +
        esc(mj.a) + '座 × ' + esc(mj.b) + '座 · 合拍指数 <strong>' +
        esc(String(mj.score)) + '</strong>/99 ' +
        '<span class="daily-lucky-word">' + esc(mj.label) + '</span></div>' +
        _xlines.map(function (ln) {
          return '<div style="margin-top:8px;color:var(--secondary);' +
            'font-size:14px;">' + esc(ln) + '</div>';
        }).join('') +
        '<div style="margin-top:8px;font-size:12px;color:var(--secondary);">' +
        '想更准？补个生辰试试八字合婚 →</div>' +
        /* R3155：合盘接 AI 解读块——判词级 lines 进 facts */
        renderAiPolish(mj) +
        /* R2350d（R100-P1-4）：速配卡补分享钮——最低成本的晒点。 */
        '<button class="ghost fav-btn" type="button" id="shareXzm" ' +
        'title="生成分享图" style="margin-top:10px;">📸 分享图</button>';
      pollAiPolish('xzmResult', mj.ai_task_id);   /* R3155：AI 段落后到 */
      var _sxm = box.querySelector('#shareXzm');
      if (_sxm) _sxm.addEventListener('click', function () {
        var _p = downloadPoster(mj, 'xzm');
        if (_p && _p.catch) _p.catch(function () {});
      });
      /* R3162：合盘卡补聊聊入口——result_ref/卡片记忆早通了，
       * 卡面上独缺这颗钮，想就着合拍指数问两句得自己翻侧边栏。 */
      attachChatEntry(box);
      /* R3131：合盘结果入聊天上下文——此前没存 LAST_RESULT，
       * 用户照着卡聊小满走零上下文泛句。 */
      try { rememberResult('xzm', mj, ''); } catch (e) {}
    } catch (e) {
      box.classList.remove('is-working');   /* 同成功路：失败态也要摘 */
      box.innerHTML = '<div class="ph-empty" style="padding:12px;">' +
        esc((e && _humanizeErr(e.message)) || '速配没跑出来，再点一次试试') +
        '</div>';
    }
  });
  /* R220b（P1-1）：日期导航——箭头翻天、今天/明天快捷、三 select 改即查 */
  /* R233k（R45-P1-2）：翻页钮不进在途锁——锁会把连点整个吞掉
   * （实测连点「→」3 次只走 1 天）。乐观先改日期再发请求，
   * _XZ_GEN 代际号把过期响应丢掉，连点几天就翻几天。 */
  var _xzp = el('xzPrev'), _xzn = el('xzNext');
  if (_xzp) _xzp.addEventListener('click', function () { xzShiftDay(-1); });
  if (_xzn) _xzn.addEventListener('click', function () { xzShiftDay(1); });
  /* R233k（R45-§3）：chatInput maxlength=500 打满静默吞字——接近
   * 上限露 n/500 计数。 */
  var _ci = el('chatInput');
  if (_ci) {
    var _cc = document.createElement('span');
    _cc.id = 'chatCount'; _cc.className = 'char-count';
    _cc.setAttribute('aria-hidden', 'true');
    _ci.parentNode.appendChild(_cc);
    _ci.addEventListener('input', function () {
      var n = _ci.value.length;
      _cc.hidden = n < 400;
      _cc.textContent = n + '/500';
    });
  }
  on('xzToday', function () {
    var t = new Date();
    xzSetDate(t.getFullYear(), t.getMonth() + 1, t.getDate());
    return doXingzuo(true);
  });
  on('xzTomorrow', function () {
    var t = new Date();
    t.setDate(t.getDate() + 1);
    xzSetDate(t.getFullYear(), t.getMonth() + 1, t.getDate());
    return doXingzuo(true);
  });
  ['xz_year', 'xz_month', 'xz_day'].forEach(function (id) {
    var node = el(id);
    if (node) node.addEventListener('change', function () {
      /* v5（用户反馈）：选日期不再自动查询——只联动修正日期（月变重建日选项），
       * 结果等用户点「查运势」再出。昨天的 doXingzuo() 自动查已删。 */
      var y = Number(el('xz_year').value), m = Number(el('xz_month').value),
        d = Number(el('xz_day').value);
      xzSetDate(y, m, d);
    });
  });
  /* R198b（US5）：今日运势分享图（数据来自最近一次 /api/daily 响应） */
  on('shareDaily', function () {
    /* R228c：失败态下静默 return 用户无感——给 toast 提示
     * R2513：return poster promise——guardedCall 忙态覆盖全程。 */
    if (window.__lastDaily) return downloadPoster(window.__lastDaily, 'daily');
    showToast('今日运势还没出来，等它算好再分享～', 'warn');
    return null;
  });
  /* R3263（R22）：小满说给你听——朗读今日判词/个人层判词。 */
  on('speakDaily', function () {
    if (!window.__lastDaily) {
      showToast('今日运势还没出来，等它算好再朗读～', 'warn');
      return;
    }
    var _text = '';
    try {
      var _j = window.__lastDaily;
      _text = (_j.personal && _j.personal.mine && _j.personal.mine.verdict)
        ? _j.personal.mine.verdict
        : (((_j.warm || {}).reply || []).join('。'));
      if (!_text) _text = _j.summary || '今日签已出，打开看看';
    } catch (eT) {}
    if (_text) _speak(_text);
  });
  /* R3264（R28）：显式 PWA 安装按钮——触发浏览器安装提示。 */
  on('installPwa', function () {
    if (_deferredInstall && _deferredInstall.prompt) {
      _deferredInstall.prompt();
      return;
    }
    showToast('当前环境暂不支持一键安装，可用浏览器「添加到主屏幕」', 'info');
  });
  /* R3264（R40）：久归深拥——关闭横幅 / 开聊天。 */
  on('returnChat', function () {
    try { chatOpen(); } catch (eC) {}
  });
  on('returnDismiss', function () {
    var _rb2 = el('returnBanner');
    if (_rb2) _rb2.hidden = true;
    try { localStorage.setItem('returnBannerDismissed', todayIso()); } catch (eS) {}
  });
  /* R3264（R38）：通知软提示——先解释价值，再请求浏览器权限。
   * 本地 reminders 需要后端/VAPID 才真推，这里只做权限软询问。 */
  on('notifySoftAsk', function () {
    if (!('Notification' in window)) {
      showToast('你的浏览器不支持通知，小满叫不了你', 'warn');
      return;
    }
    /* R3314（R3309-P1）：notify:time 此前是死承诺——写了键全仓无
     * 消费方、无 SW push，用户授权后什么都不会发生还烧掉一次系统
     * 权限信任。改为诚实兑现：授权成功即挂上本地 remind:1（次日
     * 打开时 toast 提醒），文案不再承诺真推送。 */
    showToast('小满会在你下次来的时候提醒你领签，不吵你', 'info');
    setTimeout(function () {
      Notification.requestPermission().then(function (p) {
        if (p === 'granted') {
          try {
            localStorage.setItem('notify:time', '21:00');
            localStorage.setItem('remind:1', '1');
          } catch (eT) {}
          showToast('好啦，明天你打开的时候小满喊你领签～', 'ok');
        } else if (p === 'denied') {
          showToast('没关系，你想来时小满都在', 'info');
        }
        var _nr2 = el('notifySoftRow');
        if (_nr2) _nr2.hidden = true;
      });
    }, 1200);
  });
  /* R3264（R24）：日签小红书文案——一键复制含判词/宜忌/链路的短文案。 */
  on('copyXhs', function () {
    if (!window.__lastDaily) {
      showToast('今日运势还没出来，等它算好再复制～', 'warn');
      return;
    }
    var _j = window.__lastDaily;
    var _summ = String(_j.summary || '今日份小确幸').split(/[；;]/)[0] || '今日份小确幸';
    /* R3318（审-P3-3）：剪贴板是纯文本不是 HTML——esc() 会把字段里
     * 的 &<>"' 编成实体串晒出去。纯文本拼接用 String() 原值。 */
    var _dcn = String(((_j.daily_card || {}).name) || '');
    /* R3319-P3：ISO 日期「2026-10-03」机器腔——转「10月3日」。 */
    var _dc4 = '今天';
    try {
      var _dm4 = String(_j.date || '').match(/\d{4}-(\d{1,2})-(\d{1,2})/);
      if (_dm4) _dc4 = (+_dm4[1]) + '月' + (+_dm4[2]) + '日';
    } catch (eD4) {}
    var _txt = '🌟 ' + _dc4 + ' 今日签\n' +
      String(_summ) + '\n' +
      '宜：' + String(_j.do || '—') + '\n' +
      '忌：' + String(_j.dont || '—') + '\n' +
      /* R3317-D：咒语进晒图文案——晒图自带口号感 */
      '✨ 今日咒语：' +
      String(_dayPick(_MANTRA_POOL, 'mantra|' + String(_j.date || ''))) + '\n' +
      /* R3317-G 续：今日牌也进晒图——塔罗党认这个 */
      (_dcn
        ? '🃏 今日牌：' + _dcn +
          '（' + (_j.daily_card.upright ? '正位' : '逆位') + '）\n'
        : '') + '\n' +
      '在小满的解忧铺看的，你也来沾沾今日运气👇\n' +
      (window.location.origin || '') + '/?view=daily&from=share';
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(_txt).then(
          function () { showToast('今日签文案已复制', 'ok'); },
          function () { showToast('复制失败，可手动长按复制', 'warn'); });
      } else { throw new Error('no clipboard'); }
    } catch (eC) { showToast('长按结果手动复制', 'info'); }
  });
  /* R3264（R29）：今日护身符——基于日签响应生成 lucky 海报。 */
  on('shareLucky', function () {
    if (window.__lastDaily) return downloadPoster(window.__lastDaily, 'lucky');
    showToast('今日运势还没出来，等它算好再生成护身符～', 'warn');
    return null;
  });
  /* R3317：今日开运壁纸——烘底图按日轮换 + 判词/开运色叠字。
   * R3318（审-P3-2）：连点原无节流——合成+落盘一轮 ~1s，连击会
   * 连续弹浮层/多次下载。2s 软闸（不 disable 按钮，免闪烁）。 */
  var _wapLast = 0;
  on('dailyWap', function () {
    var _nw = Date.now();
    /* R3326（审-P2）：节流命中零反馈像死按钮——给句提示。 */
    if (_nw - _wapLast < 2000) {
      showToast('慢一点，图还在出～', 'info'); return null;
    }
    _wapLast = _nw;
    if (window.__lastDaily) return downloadWallpaper(window.__lastDaily);
    showToast('今日运势还没出来，等它算好再做壁纸～', 'warn');
    return null;
  });
  /* R3325-B：开运头像——同日同图的 1:1 版（社交头像用），
   * 与壁纸同节流（共用 _wapLast 即可，两钮互斥连点）。 */
  on('dailyAva', function () {
    var _nw2 = Date.now();
    if (_nw2 - _wapLast < 2000) {
      showToast('慢一点，图还在出～', 'info'); return null;
    }
    _wapLast = _nw2;
    if (window.__lastDaily) {
      return downloadWallpaper(window.__lastDaily, { square: true });
    }
    showToast('今日运势还没出来，等它算好再做头像～', 'warn');
    return null;
  });
  /* R3325：提醒我明天再来——.ics 文件下载（每日准点喊你，30 天，
   * 钟点沿用 notify:time 里存过的）。系统日历接管提醒，
   * 不烧 Notification 权限、不靠 SW 活着。 */
  on('dailyIcs', function () {
    var hm = '21:00';
    try {
      var _nt = localStorage.getItem('notify:time');
      /* R3329（审-P3）：99:99 形状过得去→setHours 翻滚误点——
       * 形状+范围双闸。 */
      if (_nt && /^\d{2}:\d{2}$/.test(_nt) && +_nt.slice(0, 2) <= 23 &&
          +_nt.slice(3) <= 59) hm = _nt;
    } catch (eNT) {}
    var _st = new Date();
    _st.setDate(_st.getDate() + 1);
    var _h2 = hm.split(':');
    _st.setHours(+_h2[0], +_h2[1], 0, 0);
    var _pd = function (n) { return ('0' + n).slice(-2); };
    var _dt = _st.getFullYear() + _pd(_st.getMonth() + 1) +
      _pd(_st.getDate()) + 'T' + _pd(_st.getHours()) +
      _pd(_st.getMinutes()) + '00';
    /* R3327-P1-6：UID 固定（重复导入去重，不再一天多一份闹钟）；
     * DTSTAMP 取此刻 UTC；VALARM 补 RFC 必需的 DESCRIPTION。 */
    var _nw3 = new Date();
    var _ds = _nw3.getUTCFullYear() + _pd(_nw3.getUTCMonth() + 1) +
      _pd(_nw3.getUTCDate()) + 'T' + _pd(_nw3.getUTCHours()) +
      _pd(_nw3.getUTCMinutes()) + _pd(_nw3.getUTCSeconds()) + 'Z';
    var _ics = [
      'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//xiaoman//books//CN',
      'BEGIN:VEVENT',
      'UID:xiaoman-daily-remind@books',
      'DTSTAMP:' + _ds,
      'DTSTART:' + _dt,
      'RRULE:FREQ=DAILY;COUNT=30',
      'SUMMARY:小满喊你来领今日签',
      'DESCRIPTION:今天的运势和开运色更新啦，来看看小满给你留了什么话～',
      'BEGIN:VALARM', 'TRIGGER:-PT0M', 'ACTION:DISPLAY',
      'DESCRIPTION:小满喊你来领今日签', 'END:VALARM',
      'END:VEVENT', 'END:VCALENDAR'].join('\r\n');
    try {
      var _bb = new Blob([_ics], { type: 'text/calendar;charset=utf-8' });
      var _aa = document.createElement('a');
      _aa.href = URL.createObjectURL(_bb);
      _aa.download = 'xiaoman-remind.ics';
      document.body.appendChild(_aa);
      _aa.click();
      setTimeout(function () { URL.revokeObjectURL(_aa.href); _aa.remove(); }, 800);
      showToast('存进日历后，接下来 30 天每天 ' + hm +
        ' 喊你来领签', 'ok');
    } catch (eIC) {
      showToast('这台设备下载不了日历文件', 'warn');
    }
    return null;
  });
  /* R3264（R32）：今日仪式——点击即本地记录，不打卡不断签。 */
  on('dailyRitual', function () {
    try {
      localStorage.setItem('ritual:' + todayIso(), '1');
    } catch (eR) {}
    var _dr2 = el('dailyRitual');
    if (_dr2) {
      _dr2.textContent = '✅ 已做完'; _dr2.disabled = true;
      /* R3322-P2：终态禁用——guardedCall 收尾不许复位（重复点重复弹）。 */
      _dr2.dataset.stayDisabled = '1';
    }
    _microCelebrate(_dr2);
    showToast('小满记下了，今天你做了一件小事～' + '\n' + _identityPhrase(), 'ok');
  });
}

/* ── R230z（R36）：favorites 窄面接线 + 历史全品类 + 问一嘴足迹 ─────────
 * favorites API（/api/favorites + /api/user/prefs.favorites）后端一直在，
 * 本轮接两个窄入口：合婚「存这对」chips、起名「♡心水名单」——不复活
 * R208b 删掉的通用收藏面板。 */

var _favListInflight = null;
/* R2363（R116-P0-1）：收藏同清盘面——测过的 CP/心水名单也镜像本机。
 * 语义：服务端非空 = 真相，顺手重镜像；服务端空 + 镜像有 = 清盘，
 * 用镜像续着；镜像内删除走 _favMirrorDrop（用户在本机删过才是真删）。 */
var _FAV_MIRROR_KEY = 'favorites_mirror_v1';
function _favMirrorLoad() {
  try {
    var _m = JSON.parse(localStorage.getItem(_FAV_MIRROR_KEY) || 'null');
    return Array.isArray(_m) ? _m : [];
  } catch (e) { return []; }
}
function _favMirrorSave(list) {
  try {
    /* R3306-P2：多 tab 并发写互丢——写前重读按 id 并集（本 tab
     * 会话内明确删过的 id 不收尸，见 __favMirrorDelSet）。 */
    var _cur = _favMirrorLoad();
    var _have = {}, _delSet = (window.__favMirrorDelSet =
      window.__favMirrorDelSet || {});
    (list || []).forEach(function (f) { _have[String(f && f.id)] = 1; });
    (_cur || []).forEach(function (f) {
      var k = String(f && f.id);
      if (!_have[k] && !_delSet[k]) { (list = list || []).push(f); _have[k] = 1; }
    });
    var _s = JSON.stringify(list || []);
    /* 同值不写——防跨 tab storage 事件互相唤起打转 */
    if (localStorage.getItem(_FAV_MIRROR_KEY) !== _s) {
      localStorage.setItem(_FAV_MIRROR_KEY, _s);
    }
  } catch (e) { _mirrorWriteWarn(); }
}
function _favMirrorDrop(id) {
  try {
    (window.__favMirrorDelSet = window.__favMirrorDelSet || {})[
      String(id)] = 1;
  } catch (eD) {}
  _favMirrorSave(_favMirrorLoad().filter(function (f) {
    return String(f && f.id) !== String(id);
  }));
}
function _favMirrorClear() {
  try { localStorage.removeItem(_FAV_MIRROR_KEY); } catch (e) {}
}
/* R3338（审-低）：在途合并在 resolve 后即刻失效——同一屏冷启的
 * hehun/qiming/history 三处渲染串行续在 await 后，仍然各发一条 GET。
 * 加 3s TTL 短缓存共享（收藏会增删，不能长 memoize；写路径手动失效）。 */
var _favListAt = 0, _favListCache = null;
function _favListInvalidate() { _favListCache = null; _favListAt = 0; }
async function _favList() {
  /* R2348（R67-P2）：合婚/起名两个 favorites 渲染各调一次——冷启瀑布
   * 实测同秒两条重复 GET。合并在途请求（不是 memoize：收藏会增删，
   * 每次渲染要新读；但同一 tick 的并发调用共享一份）。 */
  if (_favListCache && (Date.now() - _favListAt) < 3000) return _favListCache;
  if (_favListInflight) return _favListInflight;
  _favListInflight = (async function () {
    try {
      const j = await api('/api/user/prefs', { silent: true });
      var _sv = (j && j.favorites) || [];
      var _loc = _favMirrorLoad();
      if (_sv.length || !_loc.length) {
        /* R2400（R139-P1-3）：服务端非空+镜像有独条（清盘后续命的
         * 旧收藏）——此前整表覆盖静默丢。镜像独有条目回推服务端
         * （(type,ref_id) UNIQUE+INSERT OR IGNORE，幂等），与排盘
         * 「留档能回流」同口径。 */
        var _have = {};
        _sv.forEach(function (f) { _have[String(f.type) + '|' + String(f.ref_id)] = 1; });
        var _orphans = _loc.filter(function (f) {
          return f && f.type && f.ref_id &&
                 !_have[String(f.type) + '|' + String(f.ref_id)];
        });
        if (_orphans.length) {
          _orphans.forEach(function (f) {
            try {
              postJSON('/api/favorites', { type: String(f.type).slice(0, 24),
                                           ref_id: String(f.ref_id).slice(0, 128),
                                           title: String(f.title || '').slice(0, 64) });
            } catch (eP) {}
          });
          try {
            var _j2 = await api('/api/user/prefs', { silent: true });
            _sv = (_j2 && _j2.favorites) || _sv;
          } catch (eR) {}
        }
        _favMirrorSave(_sv);
        _favListCache = _sv; _favListAt = Date.now();
        return _sv;
      }
      /* 云端空 + 本机有 = 睡醒清盘——用本机留档续，不吞镜像。 */
      _favListCache = _loc; _favListAt = Date.now();
      return _loc;
    } catch (e) {
      /* R2400（R127-P1-5）：镜像只补「够不到」，不补「不让看」——
       * 门匙过期 401/403 时留档也不出（两镜像同一口径）。 */
      if (e && (e.status === 401 || e.status === 403)) return [];
      var _loc2 = _favMirrorLoad();
      return _loc2.length ? _loc2 : [];
    }
    finally { _favListInflight = null; }
  })();
  return _favListInflight;
}

/* 合婚「测过的 CP」chips：ref_id 编码 10 字段+昵称，点 chip 回填表单 */
async function _hhFavsRender() {
  var row = el('hhFavRow');
  if (!row) return;
  var favs = (await _favList()).filter(function (f) { return f.type === 'hehun'; });
  row.hidden = !favs.length;
  if (!favs.length) { row.innerHTML = ''; return; }
  row.innerHTML = '<span class="fav-row-label">测过的 CP：</span>' +
    favs.map(function (f) {
      /* R2503（审-P2）：CP chip 补 ×——此前只可存不可摘，删错档只能
       * 整库清空（data-fav-del/removeFavorite 空壳是死代码）。
       * chip 本体仍回填，× 走 DELETE+镜像剔除（心水名单同构）。 */
      return '<span class="fav-chip-wrap">' +
        '<button type="button" class="fav-chip" data-hh-fav="' +
        esc(f.ref_id || '') + '">' + esc(f.title || '一对') + '</button>' +
        '<button type="button" class="fav-chip-x" data-hh-fav-del="' +
        esc(String(f.id)) + '" aria-label="从测过的 CP 移除 ' +
        esc(f.title || '一对') + '">×</button></span>';
    }).join('');
}

function _hhFavFill(ref) {
  var p = String(ref || '').split('|');
  if (p.length < 10) return;
  /* R3313（审-P0）：chip 语义是「我侧 | TA侧」——邀请态下受邀者
   * 自己是 B 侧，我侧落 B 组、TA 侧落 A 组；不互换就会把发起人
   * 塞进 A（我侧）让提交毁掉自己的档案。 */
  var _inv = !!window.__hhInviteMode;
  var _idsA = ['hh_a_year', 'hh_a_month', 'hh_a_day', 'hh_a_hour',
               'hh_a_gender'];
  var _idsB = ['hh_b_year', 'hh_b_month', 'hh_b_day', 'hh_b_hour',
               'hh_b_gender'];
  var _g1 = _inv ? _idsB : _idsA, _g2 = _inv ? _idsA : _idsB;
  [_g1, _g2].forEach(function (_ids, gi) {
    _ids.forEach(function (id, i) {
      var e = el(id);
      if (!e || p[gi * 5 + i] === '' || p[gi * 5 + i] == null) return;
      e.value = p[gi * 5 + i];
      delete e.dataset.me;   /* chip 回填=用户主动行为，不算 profile 预填 */
      /* 邀请态下落 A 组的是对方数据——同邀请链同口径免疫档案回填 */
      if (_inv && gi === 1) e.dataset.invite = '1';
    });
  });
  var an = el('hh_a_name'), bn = el('hh_b_name');
  var _n1 = p[10], _n2 = p[11];
  if (an && (_inv ? _n2 : _n1)) an.value = _inv ? _n2 : _n1;
  if (bn && (_inv ? _n1 : _n2)) bn.value = _inv ? _n1 : _n2;
  /* R3313（审-P1-4）：尾段历法/闰月——旧 12 段 chip 无尾段按公历，
   * 有尾段恢复历法档与闰月行显隐。 */
  if (p.length >= 16) {
    [[_g1, p[12], p[13]], [_g2, p[14], p[15]]].forEach(function (t) {
      var _calId = t[0][0].replace('_year', '_cal');
      var _leapId = t[0][0].replace('_year', '_leap');
      var _ce = el(_calId);
      if (_ce && t[1] === 'l') {
        _ce.value = 'lunar';
        try { _ce.dispatchEvent(new Event('change')); } catch (eC) {}
        var _le = el(_leapId);
        if (_le) _le.checked = (t[2] === '1');
      }
    });
  }
  /* R3247：chip 回填盖掉了明星侧 → 摘星，本对按普通合婚走。 */
  try { _celebSync(); } catch (eCS) {}
  /* R233k（R45-P1-5）：原裸调 doHehun() 绕开 _ON_BUSY——连点不同 CP
   * chip 并发请求后到者盖先到者。走同一把锁，在途时记最新一对，
   * 响应落地后自动补跑。 */
  /* R233r（R50-#3）：在途时点下一对 chip——字段已更新到最新值，
   * 补跑直接排进 _ON_QUEUE（guardedCall 释放时自动重入 doHehun，
   * 读到的是新字段值）；不再用 _hhPendingFav 重入式（锁未释放时
   * 重入会又撞 busy 分支，写入后无人消费=死锁）。 */
  if (_ON_BUSY['hhSubmit']) {
    _ON_QUEUE['hhSubmit'] = {
      handler: function () { return Promise.resolve(doHehun()); },
      ev: null
    };
    return;
  }
  guardedCall('hhSubmit', function () { return Promise.resolve(doHehun()); });
}

/* 起名心水名单：♡ 点过的名字固定在表单上方，× 可摘 */
async function _qmFavsRender() {
  var row = el('qmFavRow');
  if (!row) return;
  var favs = (await _favList()).filter(function (f) { return f.type === 'qiming'; });
  row.hidden = !favs.length;
  if (!favs.length) { row.innerHTML = ''; return; }
  row.innerHTML = '<span class="fav-row-label">♥ 心水名单：</span>' +
    favs.map(function (f) {
      return '<span class="fav-chip is-static">' + esc(f.title || '') +
        '<button type="button" class="fav-chip-x" data-qm-fav-del="' +
        esc(String(f.id)) + '" aria-label="从心水名单移除 ' + esc(f.title || '') +
        '">×</button></span>';
    }).join('');
  _qmFavMark(favs);
}

/* 结果卡里的 ♡ 按已有心水标记点亮 */
function _qmFavMark(favs) {
  var names = {};
  (favs || []).forEach(function (f) { names[f.title] = 1; });
  document.querySelectorAll('#qmResult .qm-fav').forEach(function (b) {
    if (names[b.dataset.favName]) { b.textContent = '♥'; b.classList.add('on'); }
  });
}

/* 问一嘴足迹：localStorage 存 {d, q} 最近 12 条，chip 点击回到那天重问 */
function _hlAskLog(q, dateStr, askedOn) {
  try {
    var list = JSON.parse(window.localStorage.getItem('hlask') || '[]');
    if (!Array.isArray(list)) list = [];
    list = list.filter(function (x) { return !(x && x.q === q && x.d === dateStr); });
    list.unshift({ q: q, d: dateStr, a: askedOn || dateStr });
    /* R3306-P2：并集写——两 tab 各留问一嘴足迹不互丢。 */
    _lsUnionWrite('hlask', list,
      function (x) { return x && (x.q + '|' + x.d); }, 12);
  } catch (e) {}
}

function _hlAskChipsRender() {
  var row = document.getElementById('hlAskHist');
  if (!row) return;
  var list = [];
  try { list = JSON.parse(window.localStorage.getItem('hlask') || '[]') || []; }
  catch (e) {}
  /* R2343（R58-P1-2）：合法 JSON 但非数组（'"abc"'）会让 map 炸在
   * _doHuangli 的 catch 里，黄历查询永久假失败且坏键无自愈机会——
   * 类型不对当场清键。 */
  if (!Array.isArray(list)) {
    try { window.localStorage.removeItem('hlask'); } catch (e0) {}
    row.innerHTML = ''; return;
  }
  list = list.filter(function (x) { return x && typeof x === 'object'; });
  if (!list.length) { row.innerHTML = ''; return; }
  row.innerHTML = '<span class="fav-row-label">你问过：</span>' +
    list.slice(0, 6).map(function (x) {
      return '<button type="button" class="fav-chip" data-hlask-q="' +
        esc(x.q || '') + '" data-hlask-d="' + esc(x.d || '') + '">' +
        esc((x.d || '').slice(5) + ' ' + (x.q || '')) + '</button>';
    }).join('');
}

/* R2350e（R101-P1-4）：改了表单参数后旧结果卡原样挂着——按字段
 * 前缀把对应结果容器标 .is-stale（淡化+「参数改过了」角标），
 * paint() 落地新结果时摘掉。只在容器里已有真实结果时才标。 */
var _STALE_MAP = [
  [/^(year|month|day|hour|minute|question|location|gender|calendar_type|scope|f_lunar_leap|ask_date|ask_hour|range_start|range_end|range_hour)$/, 'result'],
  [/^b_(year|month|day|hour|gender|nick)$/, 'birthResult'],
  [/^ly_/, 'lyResult'], [/^qm_/, 'qmResult'], [/^th_/, 'thResult'],
  [/^hh_/, 'hhResult'], [/^tr_/, 'trResult'], [/^hl_(year|month|day)$/, 'hlResult'],
  [/^xzm_/, 'xzmResult'], [/^xz_/, 'xzResult'],
  [/^(rwork|rq|rmax)$/, 'searchResult'],
  [/^(ascheme|aguan|ayao|aname|aaddr1|aaddr2)$/, 'addrResult'],
  [/^(cgua|cyao)$/, 'compareResult'],
  [/^(cwa|cwb|cwq)$/, 'cwResult'], [/^cq$/, 'conceptResult']];
function _markStale(fid) {
  for (var _si = 0; _si < _STALE_MAP.length; _si++) {
    if (!_STALE_MAP[_si][0].test(fid)) continue;
    var _bx = el(_STALE_MAP[_si][1]);
    /* 空态/错误态不算「旧结果」——只有挂着真实卡时才标。 */
    if (_bx && !_bx.classList.contains('is-stale') &&
        _bx.textContent && _bx.textContent.trim().length > 60 &&
        !_bx.querySelector('.ph-empty')) {
      _bx.classList.add('is-stale');
    }
    return;
  }
}
['input', 'change'].forEach(function (_ev) {
  document.addEventListener(_ev, function (e) {
    var _f = e.target;
    if (!_f || !_f.id) return;
    _markStale(_f.id);
    /* R2350f（R101-P2-8）：maxlength 静默截断——「张小可爱」变「张小」
     * 用户不察觉。顶到上限时吱一声（每字段只报一次，删短了再允许报）。 */
    if (_ev === 'input' && _f.maxLength > 0 &&
        _f.value.length >= _f.maxLength && !_f.dataset.maxHit) {
      _f.dataset.maxHit = '1';
      showToast('这栏最多 ' + _f.maxLength + ' 个字哦', 'info');
    } else if (_f.dataset.maxHit &&
               _f.value.length < _f.maxLength) {
      _f.dataset.maxHit = '';
    }
  }, true);
});

document.addEventListener('click', function (ev) {
  var t = ev.target;
  if (!t || !t.closest) return;
  /* 心水 ♡ */
  var qf = t.closest('.qm-fav');
  if (qf) {
    var nm = qf.dataset.favName;
    if (!nm || qf.dataset.inflight === '1') return;
    /* R233f（R43-P3-15）：disabled=true 会瞬间把焦点甩回 BODY——
     * 改用 dataset.inflight 防重，焦点位不丢。 */
    qf.dataset.inflight = '1';
    postJSON('/api/favorites', { type: 'qiming', ref_id: nm.slice(0, 64), title: nm })
      .then(function () {
        qf.textContent = '♥'; qf.classList.add('on');
        _favListInvalidate();
        showToast(_dayPick(['收进心水名单啦','放进心水夹了～','这个名字归你了'], 'fav'), 'info');
        _qmFavsRender();
      })
      /* R2353（R110-P2-7）：.finally 未 gate——Chromium<63/iOS<13.4
       * 上是 undefined → 同步 TypeError，inflight 永不复位按钮报废。
       * 改 then/catch 双侧各复位（等值）。 */
      .then(function () { qf.dataset.inflight = ''; qf.disabled = false; },
            function () { qf.dataset.inflight = ''; qf.disabled = false; });
    return;
  }
  var qd = t.closest('[data-qm-fav-del]');
  if (qd) {
    /* R233k（R45-§8）：裸 fetch 无超时/无 inflight，双击双发。 */
    if (qd.dataset.inflight === '1') return;
    qd.dataset.inflight = '1';
    api('/api/favorites/' + encodeURIComponent(qd.dataset.qmFavDel),
        { method: 'DELETE', silent: true })
      .then(function () { _favListInvalidate(); _favMirrorDrop(qd.dataset.qmFavDel); _qmFavsRender(); })
      .catch(function (e) {
        /* R2363：404 = 云端已清——视同摘成功，镜像摘掉再渲。 */
        if (/(404|不存在)/.test(e && e.message || '')) {
          _favMirrorDrop(qd.dataset.qmFavDel); _qmFavsRender();
        } else { showToast('摘失败，稍后再试', 'warn'); }
      })
      /* R2353（R110-P2-7）：同 P2-7——.finally 换双分支复位。 */
      .then(function () { qd.dataset.inflight = '0'; },
            function () { qd.dataset.inflight = '0'; });
    return;
  }
  /* 测过的 CP chip → 回填表单并直接合婚 */
  var hc = t.closest('[data-hh-fav]');
  if (hc) { _hhFavFill(hc.dataset.hhFav); return; }
  /* R2503（审-P2）：CP chip 的 ×——与 data-qm-fav-del 同构：
   * inflight 防双击、DELETE 后镜像剔除重渲、404 视同摘成功。 */
  var hd = t.closest('[data-hh-fav-del]');
  if (hd) {
    if (hd.dataset.inflight === '1') return;
    hd.dataset.inflight = '1';
    api('/api/favorites/' + encodeURIComponent(hd.dataset.hhFavDel),
        { method: 'DELETE', silent: true })
      .then(function () { _favListInvalidate(); _favMirrorDrop(hd.dataset.hhFavDel); _hhFavsRender(); })
      .catch(function (e) {
        if (/(404|不存在)/.test(e && e.message || '')) {
          _favListInvalidate(); _favMirrorDrop(hd.dataset.hhFavDel); _hhFavsRender();
        } else { showToast('摘失败，稍后再试', 'warn'); }
      })
      /* R2353（R110-P2-7）：同 P2-7——.finally 换双分支复位。 */
      .then(function () { hd.dataset.inflight = '0'; },
            function () { hd.dataset.inflight = '0'; });
    return;
  }
  /* 问一嘴足迹 chip → 把问题原样再问一遍（日期词按当下重算，
   * 比钉死那天更贴近用户意图）。
   * R2350c（R97-P2-2）：dailyRecall 接续条文案是「今天再看看？」——
   * 原句里的「明天」会漂到明天判，点的人要的是今天。带
   * data-hlask-today 的条目重问前剥掉相对日期词，按今天判。 */
  var hq = t.closest('[data-hlask-q]');
  if (hq) {
    var _q = hq.dataset.hlaskQ || '';
    if (hq.dataset.hlaskToday === '1') {
      _q = _q.replace(/大后天|大前天|过两天|后晚|后天|明晚|明天|明日|明儿|今晚|今夜|今天|今日|昨晚|昨天|昨日|前天|前日|这周末|下周末|下下周[一二三四五六日天]|下周[一二三四五六日天末]?|本周[一二三四五六日天]|这周[一二三四五六日天]?|这个月|下个月|上个月|月底|月末|年底/g, '');
    }
    var inp = document.getElementById('hlAskInput');
    /* R232c（R41-P2-1）：dailyRecall 接续条点击先于黄历首次渲染——
     * input/btn 还不存在时填充静默落空。暂存待问句，doHuangli 渲完
     * 消费一次（会话内已进过黄历页则照常直填）。 */
    if (inp) {
      inp.value = _q;
      var ab = document.getElementById('hlAskBtn');
      if (ab) ab.click();
    } else {
      window.__pendingHlAsk = _q;
    }
  }
});

/* ── R230z（R36-P1-1）：历史台账全品类——列表徽标 + 复看按 type 回放 ── */
var _PH_BUILDERS = {
  bazi: function (j) { return buildBaziResult(j); },
  taohua: function (j) { return buildTaohuaResult(j); },
  hehun: function (j) { return buildHehunResult(j); },
  tarot: function (j) { return buildTarotResult(j); },
  liuyao: function (j) { return buildLiuyaoResult(j); },
  qiming: function (j) { return buildQimingResult(j); },
  dream: function (j) { return buildDreamResult(j); }
};
var _PH_TYPE_LABEL = { bazi: '命盘', taohua: '桃花', hehun: '合婚',
                       tarot: '塔罗', liuyao: '六爻', qiming: '起名',
                       dream: '解梦' };

/* R3200：历史类型筛选——按品类 chip 过滤 .ph-item[data-type]。
 * 只筛当前页（limit=50 内），不碰服务端。 */
var _phTypeFilter = '';
function _phRenderFilter(rows) {
  var box = el('historyFilter');
  if (!box) return;
  var types = {};
  (rows || []).forEach(function (r) {
    var t = r.type || 'bazi';
    types[t] = (types[t] || 0) + 1;
  });
  var ks = Object.keys(types);
  if (!ks.length) { box.hidden = true; box.innerHTML = ''; return; }
  var html = '<button type="button" class="ph-fchip' +
    (_phTypeFilter ? '' : ' on') + '" data-t="" aria-pressed="' +
    (!_phTypeFilter) + '">全部</button>';
  ks.sort().forEach(function (t) {
    html += '<button type="button" class="ph-fchip' +
      (_phTypeFilter === t ? ' on' : '') + '" data-t="' + esc(t) +
      '" aria-pressed="' + (_phTypeFilter === t) + '">' +
      esc(_PH_TYPE_LABEL[t] || t) + ' ' + types[t] + '</button>';
  });
  box.innerHTML = html;
  box.hidden = false;
}
function _phApplyFilter() {
  document.querySelectorAll('#historyList .ph-item').forEach(function (it) {
    it.style.display = (!_phTypeFilter ||
      it.getAttribute('data-type') === _phTypeFilter) ? '' : 'none';
  });
}

function init() {
  applyTheme(uiTheme());       // 003 判据 12：加载时应用已保存的主题
  /* R198b（US4）：时辰感知背景——按本地小时设五档 daypart。
   * 纯属性设置零动画；不读时钟入任何计算结果（voice 硬纪律不受影响）。 */
  var _applyDaypart = function () {
    var __h = new Date().getHours();
    var __dp = (__h < 6) ? 'night' : (__h < 10) ? 'dawn' : (__h < 15) ? 'morning'
             : (__h < 19) ? 'noon' : (__h < 22) ? 'dusk' : 'night';
    document.documentElement.setAttribute('data-daypart', __dp);
  };
  /* R2349t（R88-15a）：季节轮换——换季那天铺子换底色（只调光晕，
   * 不动文字色；深色/legacy 主题下不覆盖）。 */
  var _applySeason = function () {
    var _mo = new Date().getMonth();
    document.documentElement.setAttribute('data-season',
      (_mo >= 2 && _mo <= 4) ? 'spring' : (_mo >= 5 && _mo <= 7) ? 'summer'
      : (_mo >= 8 && _mo <= 10) ? 'autumn' : 'winter');
  };
  _applySeason();
  _applyDaypart();
  /* R3264（R44）：系统主题变化监听——当前主题为 system 时自动切换。 */
  try {
    var _mql = matchMedia('(prefers-color-scheme: dark)');
    if (_mql && _mql.addEventListener) {
      _mql.addEventListener('change', function () {
        if (uiTheme() === 'system') applyTheme('system');
      });
    }
  } catch (eM) {}
  /* R3255：聊天侧栏绑定提到最前并独立 try——「和小满聊聊」是
   * 情绪兜底入口，不能被后续任何初始化异常连坐挂掉。 */
  try { initChatSidebar(); } catch (eCS) { console.warn('[init] chatSidebar', eCS); }
  /* R3255：初始化互相隔离——一个模块抛错不再把后面的入口全拖死。 */
  try { initViews(); } catch (eV) { console.warn('[init] views', eV); }
  try { initBazi(); } catch (eB) { console.warn('[init] bazi', eB); }
  try { initReading(); } catch (eR) { console.warn('[init] reading', eR); }
  try { initDivination(); } catch (eD) { console.warn('[init] divination', eD); }
  _meFillAll();   /* R230y（R36-P1-4）：生日 profile 代入同人表单 */
  /* R3264（R38）：通知软提示——仅浏览器未决定权限时露出按钮。 */
  try {
    var _nr = el('notifySoftRow');
    if (_nr && 'Notification' in window && Notification.permission === 'default') {
      _nr.hidden = false;
    }
  } catch (eN) {}
  /* R3207：时辰对照表——「知道子时不知道几点」的用户此前要切出去查；
   * 每个出生时辰输入框尾巴挂一张可展开的 12 时辰表。 */
  ['hour', 'th_hour', 'qm_hour', 'hh_a_hour', 'hh_b_hour', 'b_hour',
   'ly_hour', 'ask_hour', 'range_hour']
    .forEach(_hourCheatAttach);
  _chatChipsPersonalize();   /* R231g（R39-P2-3）：聊天空态 chips 个性化 */
  /* R3264（R40）：久归深拥——≥3 天没来时首页给温暖横幅。 */
  try {
    var _last = localStorage.getItem('usage:last') || '';
    var _dismissed = '';
    try { _dismissed = localStorage.getItem('returnBannerDismissed') || ''; } catch (eD) {}
    if (_last && /^\d{4}-\d{2}-\d{2}$/.test(_last) && _dismissed !== todayIso()) {
      var _diff = Math.round(
        (Date.parse(todayIso() + 'T00:00:00') - Date.parse(_last + 'T00:00:00')) / 86400000);
      if (_diff >= 3) {
        var _rb = el('returnBanner');
        if (_rb) _rb.hidden = false;
      }
    }
  } catch (eR) {}
  _hhFavsRender();   /* R230z：测过的 CP chips（静默——离线不弹） */
  _qmFavsRender();   /* R230z：心水名单行 */
  /* R231a（R35-P2-10）：滚动中 FAB 缩小半透明——只动 transform/opacity，
   * 停滚 260ms 后恢复；reduced-motion 下 transition 已由媒体查询关掉。 */
  var _fabT = null;
  window.addEventListener('scroll', function () {
    var fab = document.querySelector('.recent-toggle');
    if (!fab || window.scrollY < 40) return;
    fab.classList.add('is-mini');
    if (_fabT) clearTimeout(_fabT);
    _fabT = setTimeout(function () {
      var f = document.querySelector('.recent-toggle');
      if (f) f.classList.remove('is-mini');
    }, 260);
  }, { passive: true });
  /* R230q（R28-P2-4）：sid 跨刷新存活则气泡也跨刷新恢复——否则
   * 新消息悄悄接进看不见的上一轮上下文。 */
  _chatTsRestore();
  /* R231c（R36-P3-4）：每日卡拆礼物封面——同一天已拆过就直接不盖；
   * 点/回车拆开，记到 localStorage 按天复位。
   * R231d（R39-P0-4）：封面抽成可复挂载——跨零点换日时第二天的
   * 拆礼物仪式不缺席（原先 cover remove 后隔夜 tab 永久失去封面）。 */
  var _dailyCoverHtml = null;
  /* R39-P1-3：第 N 次开铺——来访日集合存 localStorage（cap 400），
   * 回访者封面文案区别于首访。 */
  function _bindDailyCover(_cov) {
    if (!_cov) return;
    var _n = _visitCount();
    /* R2349l（R73-obs1）：二访起封面降为顶部缎带——礼物仪式留着，
     * 但不再整卡遮罩把功能入口压在首屏外。 */
    var _mini = _n > 1;
    if (_mini) {
      _cov.classList.add('mini');
      var _im = _cov.querySelector('img');
      if (_im) _im.src = '/static/cream/daily-gift-bear.png';
      /* 缎带是卡内静态流元素——挪到卡顶，露出「今天有礼物」的头位。 */
      var _cardM = _cov.closest('.daily-card');
      if (_cardM && _cardM.firstElementChild !== _cov) {
        _cardM.insertBefore(_cov, _cardM.firstElementChild);
      }
    }
    if (_n > 1) {
      var _ct = _cov.querySelector('.daily-cover-txt');
      /* R233n：有昵称喊名字——回访承接更贴。 */
      var _mn = (_meGet('me') || {}).n;
      /* R2349g（R68-P2）：回访封面固定模板只有 N 在变，第 2 次到第
       * 400 次逐字节相同——换 4 句池按日轮换。 */
      if (_ct) _ct.textContent = '🎀 ' +
        (_mn ? _mn + '，' : '') +
        /* R2350c（R97-P2-1）：_n>1 时 _mini 恒真——revisit-mini 池
         * 永命中，「第 N 次开铺」四句是死代码。缎带文案直接吃
         * revisit 池（mini 只是封面形态，文案照样能报第几次来）。 */
        _dayPick(['小满第 ' + _n + ' 次为你开铺，拆开看看今天的运',
                  '第 ' + _n + ' 次见面啦，今天也给你包了礼物',
                  '又来啦，第 ' + _n + ' 次开铺，今天的运在里面',
                  '第 ' + _n + ' 次重逢，今天的包裹热着呢'],
                 'revisit');
      /* R2349t（R88-8/1b）：生日 > 久归 > 常规 N 次的承接优先级——
       * 断几天回来的用户落进和第二天回来一样的文案，是最亏的一屏。 */
      var _gapC = _visitsGap();
      if (_ct && _isMyBirthday()) {
        _ct.textContent = '🎂 ' + (_mn ? _mn + '，' : '') +
          '生日礼物已包好：拆你这一年的第一签';
      } else if (_ct && _gapC > 3) {
        _ct.textContent = '🎀 ' + (_mn ? _mn + '，' : '') + _dayPick([
          '好久不见：这几天过得怎么样，今天的运在里面',
          '好几天没见啦，小满一直留着你的位置',
          '回来啦：攒了几天的运气，都在这包里'], 'revisit-gap');
      }
    }
    /* R3243（用户实测·重构）：表单挪出封套成独立副卡——绑定移到
     * _bindDailyAsk（判档显隐+提交+历法联动），封面只管拆开。 */
    /* R231f（R38-P1-2）+ R232c（R41-P1-1 修）：封面遮罩只挡鼠标不挡
     * 键盘——给卡内封面以外的直接子元素打 inert（容器级，innerHTML
     * 重灌仍生效），并挂 MutationObserver 补打异步注入的节点
     * （dailyRecall/dailyTomorrow/checkin opts 是 loadDaily 回调里进的，
     * 逐控件打标会漏）。开封统一摘除并断开观察。 */
    var _card0 = _cov.closest('.daily-card');
    var _mo = null;
    var _inertSibs = function () {
      if (!_card0 || _mini) return;   /* mini 缎带不遮内容，无需 inert */
      Array.prototype.forEach.call(_card0.children, function (c) {
        if (c !== _cov && !c.hasAttribute('inert')) c.setAttribute('inert', '');
      });
    };
    if (_card0) {
      _inertSibs();
      if (window.MutationObserver) {
        _mo = new MutationObserver(_inertSibs);
        _mo.observe(_card0, { childList: true });
      }
    }
    /* R2349（R65-P2-3）：摘封面的 inert/MO 清理抽出来——跨 tab
     * storage 事件也要走同一条，不能只 remove 封面节点（兄弟节点的
     * inert 会留下，MO 还会在下次变异时打回去）。 */
    var _cleanup = function () {
      if (_mo) { _mo.disconnect(); _mo = null; }
      if (_card0) {
        Array.prototype.forEach.call(_card0.children, function (c) {
          c.removeAttribute('inert');
        });
      }
      if (_cov.parentNode) _cov.remove();
    };
    window.__dailyCoverCleanup = _cleanup;
    var _reveal = function () {
      try { if (window.__onDayFlip) window.__onDayFlip(); } catch (eF) {}
      _cov.classList.add('open');
      /* R41-P3-2：隔夜未拆次日再拆——key 按点击时刻的今天写，
       * 不能复用绑定时算好的昨天。 */
      try { localStorage.setItem('dailyRevealed:' + todayIso(), '1'); }
      catch (e) {}
      setTimeout(function () {
        _cleanup();
        /* R38-P3-3：开封后焦点移交首个内容控件，不再丢回 body 从头爬 */
        var _dm = el('dailyMore');
        if (_dm && _dm.focus) { try { _dm.focus(); } catch (e) {} }
      }, 500);
    };
    /* R3243（用户实测）：封套点开前的表单门——
     * · 年月日填全 → 当点了「包好我的礼物」（存档→专属→自拆）；
     * · 填了一半 → 不拆，提示补完并聚焦首个空格（手误点开不再
     *   直接糊一个通版结果）；
     * R3248（用户实测）：全空也不拆了——礼物必须照着你的盘包，
     * 年月日填全才开（时辰可空）。每人拆出来的签才真正不一样。 */
    var _tryReveal = function () {
      /* 已存完整档案 → 直接拆（表单显隐只是陈旧 DOM，不拦主人）。 */
      var _meR = _meGet('me');
      if (_meR && _meR.y && _meR.m && _meR.d) { _reveal(); return; }
      var _af = el('dailyAsk');
      if (_af && !_af.hidden) {
        var _need = ['y', 'm', 'd'], _filled = 0;
        _need.forEach(function (k) {
          var f = _af.querySelector('[data-k="' + k + '"]');
          if (f && String(f.value).trim()) _filled++;
        });
        var _hF = _af.querySelector('[data-k="h"]');
        var _hHas = !!(_hF && String(_hF.value).trim());
        if (_filled === 3) { _dailyAskGo(_af); return; }
        showToast((_filled > 0 || _hHas)
          ? '生日填了一半呢，补完再拆更准哦'
          : '先填好你的生辰，小满才能把礼物包成你的 🎁', 'info');
        var _fe = _need.map(function (k) {
          return _af.querySelector('[data-k="' + k + '"]');
        }).filter(function (f) {
          return f && !String(f.value).trim();
        })[0];
        if (_fe) {
          try {
            _fe.scrollIntoView({ block: 'center', behavior: 'smooth' });
            _fe.focus();
          } catch (eFc) {}
        }
        return;
      }
      _reveal();
    };
    _cov.addEventListener('click', _tryReveal);
    _cov.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault(); _tryReveal();
      }
    });
  }
  /* R3243：独立副卡绑定——判档显隐（me 有完整生日才藏）、历法
   * 联动闰月、按钮/Enter 提交。表单不在封套里，任何视口都完整
   * 可见，不再有「按钮被帽裁掉」问题。 */
  function _bindDailyAsk() {
    var _ask = el('dailyAsk');
    if (!_ask) return;
    var _meA = _meGet('me');
    var _hasMe = !!(_meA && _meA.y && _meA.m && _meA.d);
    _ask.hidden = _hasMe;
    if (_hasMe) return;
    if (_ask.dataset.bound) return;         /* 幂等——重复调用只刷显隐 */
    _ask.dataset.bound = '1';
    /* R3244：档案残档（只存了年之类）回显已存值——别让人重填
     * 一遍；用户手改过的字段不受 _meFill 覆盖，此处是首绑时
     * 一次性代入。 */
    try {
      if (_meA) {
        ['y', 'm', 'd', 'h'].forEach(function (k) {
          if (_meA[k] != null && _meA[k] !== '') {
            var f = _ask.querySelector('[data-k="' + k + '"]');
            if (f && !f.value) f.value = _meA[k];
          }
        });
        var _gE = _ask.querySelector('[data-k="g"]');
        if (_gE && _meA.g) _gE.value = _meA.g;
        var _calE0 = _ask.querySelector('.da-cal');
        if (_calE0 && _meA.lunar) {
          _calE0.value = 'lunar';
          var _lw0 = _ask.querySelector('.da-leapw');
          if (_lw0) _lw0.hidden = false;
          var _leap0 = _ask.querySelector('.da-leap');
          if (_leap0 && _meA.lunar.leap) _leap0.checked = true;
        }
      }
    } catch (eP) {}
    var _calEl = _ask.querySelector('.da-cal');
    var _leapW = _ask.querySelector('.da-leapw');
    if (_calEl && _leapW) {
      _calEl.addEventListener('change', function () {
        _leapW.hidden = _calEl.value !== 'lunar';
      });
    }
    var _askBtn = _ask.querySelector('.da-btn');
    if (_askBtn) {
      _askBtn.addEventListener('click', function () { _dailyAskGo(_ask); });
    }
    _ask.addEventListener('keydown', function (e) {
      /* R3233：不在 <form> 里，输入框 Enter 补提交；R3240：只拦
       * INPUT——select/checkbox 的 Enter 是控件自身语义。 */
      if (e.key === 'Enter' && e.target && e.target.tagName === 'INPUT') {
        e.preventDefault();
        _dailyAskGo(_ask);
      }
    });
  }
  /* R3232：礼物表单提交——校验 →（农历先换公历）→ 存 me →
   * 日卡带 bday 重拉（专属判词行）→ 礼物自己打开。
   * 失败保留封套与表单，用户可改可再试。 */
  var _askBusy = false;
  async function _dailyAskGo(node) {
    if (_askBusy || !node) return;
    function _daVal(k) {
      var f = node.querySelector('[data-k="' + k + '"]');
      /* 全角数字归一（与 num() 同口径）——中文输入法常产全角。 */
      var s = f ? String(f.value == null ? '' : f.value) : '';
      return s.replace(/[０-９]/g, function (c) {
        return String.fromCharCode(c.charCodeAt(0) - 0xFEE0);
      }).trim();
    }
    function _bad(k, tip) {
      var f = node.querySelector('[data-k="' + k + '"]');
      if (f) {
        f.setAttribute('aria-invalid', 'true');
        var clr = function () {
          f.removeAttribute('aria-invalid');
          f.removeEventListener('input', clr);
        };
        f.addEventListener('input', clr);
        /* R3320-P3：红框但不聚焦——软键盘收起后用户看不见错在哪。 */
        try { f.focus(); } catch (eFoc) {}
      }
      showToast(tip, 'warn');
    }
    var y = Number(_daVal('y')), m = Number(_daVal('m')), d = Number(_daVal('d'));
    var hraw = _daVal('h'), h = (hraw === '' ? null : Number(hraw));
    var calEl = node.querySelector('.da-cal');
    var cal = calEl ? calEl.value : 'solar';
    var leapEl = node.querySelector('.da-leap');
    var leap = !!(leapEl && leapEl.checked);
    if (!y || y < 1900 || y > 2100 || !/^\d+$/.test(_daVal('y'))) {
      _bad('y', '出生年填 1900–2100 的整数'); return;
    }
    if (!m || m < 1 || m > 12 || !/^\d+$/.test(_daVal('m'))) {
      _bad('m', '月份填 1–12'); return;
    }
    var _dmax = (cal === 'lunar') ? 30 : 31;
    if (!d || d < 1 || d > _dmax || !/^\d+$/.test(_daVal('d'))) {
      _bad('d', cal === 'lunar' ? '农历的日填 1–30' : '日填 1–31'); return;
    }
    if (h !== null && (!(h >= 0 && h <= 23) || !/^\d+$/.test(hraw))) {
      _bad('h', '时辰填 0–23，不知道就留空'); return;
    }
    /* 公历存在性校验——2/31、4/31 这类「范围合法但不存在」的日
     * 此前直接落档，me 存进不存在的生日。Date 往返比对分量。 */
    if (cal !== 'lunar') {
      var _dt = new Date(y, m - 1, d);
      if (_dt.getFullYear() !== y || _dt.getMonth() !== m - 1 ||
          _dt.getDate() !== d) {
        _bad('d', '这个日子不存在——再看看哪天'); return;
      }
    }
    _askBusy = true;
    var _btn = node.querySelector('.da-btn');
    var _bt0 = _btn ? _btn.textContent : '';
    if (_btn) _btn.textContent = '正在包礼物…';
    try {
      var sy = y, sm = m, sd = d;
      if (cal === 'lunar') {
        /* R3307（审-中6）：生日坐标走 body 不进 URL。 */
        var _cj = await postJSON('/api/lunar/convert',
          { y: y, m: m, d: d, leap: (leap ? 1 : 0) });
        if (!_cj || !_cj.solar) throw new Error('农历没换算成');
        sy = _cj.year; sm = _cj.month; sd = _cj.day;
      }
      var _gEl = node.querySelector('.da-gender');
      _meSave('me', { y: sy, m: sm, d: sd, h: h,
        g: (_gEl && _gEl.value === '男') ? '男' : '女',
        /* R3233：与主表单同口径——档案记公历坐标+农历原值标注，
         * 小档案条「（农历x年x月x日）」才有据。 */
        lunar: (cal === 'lunar')
          ? ('农历' + y + '年' + m + '月' + d + '日' +
             (leap ? '（闰）' : ''))
          : null });
      /* 日卡重拉带 bday → personal 专属判词行；落地后再拆礼物，
       * 揭开的就是「你的」卡。
       * R3243：先藏表单再点封面——封面点击会过 _tryReveal 表单门，
       * 表单还露着且字段齐全会被当「包好礼物」回环调用（busy 挡
       * 掉后封面永远不拆）。 */
      node.hidden = true;
      await loadDaily();
      var _covNow = el('dailyCover');
      if (_covNow) { _covNow.click(); }
      showToast('礼物照着你的盘包好啦 🎁', 'info');
    } catch (err) {
      showToast(_humanizeErr((err && err.message) ||
                '生日没存上，再试一次看看'), 'warn');
      if (_btn) _btn.textContent = _bt0;
    } finally {
      _askBusy = false;
    }
  }
  function _mountDailyCover() {
    var _card = el('dailyCard');
    if (!_card) return;
    var _dk = 'dailyRevealed:' + todayIso();
    var _revealed = false;
    try { _revealed = !!localStorage.getItem(_dk); } catch (e) {}
    var _cov = el('dailyCover');
    if (_revealed) { if (_cov) _cov.remove(); return; }
    if (_cov || !_dailyCoverHtml) return;   /* 还盖着或没有模板 */
    _card.insertAdjacentHTML('beforeend', _dailyCoverHtml);
    _bindDailyCover(el('dailyCover'));
  }
  (function () {
    var _cov = el('dailyCover');
    if (!_cov) return;
    _dailyCoverHtml = _cov.outerHTML;
    var _dk = 'dailyRevealed:' + todayIso();
    try {
      if (localStorage.getItem(_dk)) { _cov.remove(); return; }
    } catch (e) {}
    _bindDailyCover(_cov);
  })();
  _bindDailyAsk();
  window.__mountDailyCover = _mountDailyCover;
  loadDaily();
  /* R2349（R65-P1-4）：iOS 不发 beforeinstallprompt——第二次来访
   * 起主动弹手动装桌面引导（首访不打扰）。延迟到 loadDaily 之后
   * 避免与拆礼物封面同时出现。 */
  setTimeout(function () {
    try {
      var _ios0 = /iP(hone|ad|od)/.test(navigator.userAgent) ||
        (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
      /* R2349m（R76-P3）：WKWebView 里 standalone 是 undefined——
       * 显式 !== true 而非 !x，侥幸正确转正为明确正确。 */
      if (_ios0 && navigator.standalone !== true && _visitCount() >= 2) {
        _renderInstallTip();
      }
    } catch (eI) {}
  }, 6000);
  /* R219b（P0-4）：loadRecent 随历史记录功能删除（不再有 /api/history）。 */
  loadFavorites();
  /* R208b：loadNews 随「今日关注」面板移除 */
  /* R3338（审-中）：warmPoster 启动即拉 app_poster.js（~100KB）与
   * 首屏关键资源争带——挪进 requestIdleCallback/setTimeout 空闲窗，
   * 省流量/慢网（saveData、effectiveType≤3g）直接放弃预热（真点画布
   * 时再拉，代价只是那一次点击多等一会儿）。 */
  try {
    var _conn = navigator.connection || navigator.mozConnection ||
                navigator.webkitConnection;
    var _netOk = !(_conn && (_conn.saveData ||
                 /(^|-)2g/.test(_conn.effectiveType || '')));
    var _warm = function () {
      try { warmPoster(); } catch (eWP) {}
    };
    if (_netOk) {
      if (window.requestIdleCallback) {
        window.requestIdleCallback(_warm, { timeout: 6000 });
      } else {
        setTimeout(_warm, 3500);
      }
    }
  } catch (eWC) {}

  /* R230n（R25-1.2/1.3/2.1）：回访三件套——
   * 1) 跨零点自刷新：回前台或每 60s 检查浏览器日；变了则重跑
   *    loadDaily/renderCheckin，已展示的「昨天」黄历/星座卡按今天重查
   *    （用户自选日期的结果不动——只有显示日恰是旧今天才换）。
   * 2) checkin 跨 tab 同步：storage 事件命中 checkin:* 即重渲。 */
  var _lastDay = todayIso();
  /* R232a（R40-R1）：dailyRevealed/checkin GC 原来只挂在打卡点击里——
   * 只拆信封不打卡的用户键无限累积。启动时跑一次兜底。 */
  try {
    /* R2349y（R95-P1-1）：90 天窗口把「百日传说」连签档钉死在
     * ≤91 天——放宽到 150（台账 R2349u 宣称的口径，那次提交漏带了
     * app.js）。 */
    var _gc0 = _isoShift(_lastDay, -150);
    for (var _gi = window.localStorage.length - 1; _gi >= 0; _gi--) {
      var _gk = window.localStorage.key(_gi);
      /* R2349（R65-P2-4）：checkinCeleb:N:YYYY-MM-DD 此前不在 GC——
       * 里程碑标记虽轻但白攒；按尾段日期同一 90 天口径收。 */
      var _gkd = _gk && _gk.indexOf('checkinCeleb:') === 0
        ? _gk.slice(_gk.lastIndexOf(':') + 1) : null;
      /* R3318（审-P3-1）：日期后缀族此前只在打卡点击路径 GC——
       * 从不打卡的浏览型用户 mood:/journal:/ritual:/usage:d:/rlast:/
       * mood:dream:/weeklyLetter: 永不回收（mood ~365键/年）。
       * 兜底并入同一族清单（与 15271 打卡段 _fam 同口径）。 */
      /* R3328（审-低）：checkinBuff:* 此前只在打卡路径 GC——
       * 不打卡浏览型用户永不回收，并入启动兜底族清单。
       * R3328（审-中）：monthlyLetter:YYYY-MM 尾段非 YYYY-MM-DD
       * 两条 GC 路径都永不回收——按 YYYY-MM 尾段比。 */
      var _gkf = _gk && _gk.match(
        /^(mood:|moodlv:|journal:|ritual:|usage:d:|rlast:|mood:dream:|weeklyLetter:|pilePick:|checkinBuff:|shred:|qian:|manifest:)/);
      var _gks = null;
      if (_gkf) {
        _gks = _gk.slice(_gk.lastIndexOf(':') + 1);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(_gks)) _gks = null;
      }
      var _gkm = _gk && _gk.indexOf('monthlyLetter:') === 0
        ? _gk.slice(14) : null;
      if (_gkm && /^\d{4}-\d{2}$/.test(_gkm)) {
        _gks = _gkm + '-28';
      }
      /* R3339（审-低）：checkin:goal-celebrated:<date> 在 checkin:
       * 前缀下但 slice(8) 非日期——通用比较永不命中，尾段日期单算。 */
      var _gkc = _gk && _gk.indexOf('checkin:goal-celebrated:') === 0
        ? _gk.slice(24) : null;
      if (_gkc && !/^\d{4}-\d{2}-\d{2}$/.test(_gkc)) _gkc = null;
      if (_gk && ((_gk.indexOf('checkin:') === 0 &&
          _gk.indexOf('checkin:goal-celebrated:') !== 0 &&
          _gk.slice(8) < _gc0) ||
          (_gk.indexOf('dailyRevealed:') === 0 && _gk.slice(14) < _gc0) ||
          (_gkc && _gkc < _gc0) ||
          (_gkd && _gkd < _gc0) || (_gks && _gks < _gc0))) {
        window.localStorage.removeItem(_gk);
      }
    }
    /* R2345（R63-P2-5）：c26bdce 时代 chat sid/记录放 localStorage，
     * R230n 迁到 sessionStorage 后旧键无人清——启动兜底一并收掉。
     * R3339（审-中）：chatTranscript 不能再删——R3118 已把 transcript
     * 升回 localStorage 当现役键，开机删它等于每次启动先把跨天
     * 续聊气泡清了（feature 实际从未活过）。chatSessionId 仍是
     * 真 legacy（sid 现走 sessionStorage），继续清。 */
    ['chatSessionId'].forEach(function (k) {
      try { window.localStorage.removeItem(k); } catch (e4) {}
    });
    /* R2345（R63-P2-7）：申请持久化存储——浏览器在存储压力下可
     * 逐出 localStorage/CacheStorage（iOS 7 天不活跃策略），
     * persist() 保住连签/档案/离线壳。拒绝/不支持均静默。 */
    if (navigator.storage && navigator.storage.persist) {
      navigator.storage.persist().catch(function () {});
    }
  } catch (e) {}
  var _onDayFlip = function () {
    var t = todayIso();
    if (!t || t === _lastDay) return;
    var prev = _lastDay;
    _lastDay = t;
    /* R39-P0-4：零点翻面要说出来——此前全程静默换数；且把第二天的
     * 拆礼物封面重新挂回（隔夜 tab 也能拆今天的礼物）。 */
    try { showToast(_dayPick(['新的一天到啦，运势给你换好了 ✨',
                              '跨过零点了，今天的运势更新完毕',
                              '新的一天，盘面已刷新～'], 'midnight'), 'info'); } catch (e) {}
    try { _mountDailyCover(); } catch (e) {}
    /* R232c（R41-P3-1）：本周宜忌条跨零点重算——会话级一次性闸
     * 会让隔夜 tab 的 7 格停在旧七天（首格还标「今天」）。 */
    try {
      _hlWeekDone = false;
      if (el('hlWeek') && el('hlWeek').children.length) hlLoadWeek();
    } catch (e) {}
    try { loadDaily(); } catch (e) {}
    var dd = el('dailyDetail');
    if (dd) dd.dataset.loaded = '';   /* 展开缓存按新天失效 */
    var hl = el('hlResult'), hv = el('view-huangli');
    if (hl && hl.dataset && hl.dataset.shownDate === prev &&
        hv && hv.classList.contains('active')) {
      doHuangli(0, true);
    }
    var xv = el('view-xingzuo');
    if (_xzLastDate === prev && xv && xv.classList.contains('active')) {
      ['xz_year', 'xz_month', 'xz_day'].forEach(function (id) {
        var _e = el(id); if (_e) _e.value = '';
      });
      doXingzuo(true);
    }
  };
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) { _applyDaypart(); _onDayFlip(); }
  });
  /* R231f（R38-P2-3）：时段档随 60s tick 同步——挂后台跨时段回前台
   * 时渐变不再停在进页那一档。 */
  /* R2350g（R106-F6）：跨零点≤60s 视觉混合态收窄——tick 降到 15s，
   * 且交互入口（打卡/拆礼物）点击时顺手翻一次，不等下个 tick。 */
  window.__onDayFlip = _onDayFlip;
  setInterval(function () { _applyDaypart(); _onDayFlip(); }, 15000);
  window.addEventListener('storage', function (e) {
    if (!e || !e.key) return;
    /* R2508（审-P2-1 续）：wishbottle 进 wipe/备份白名单后，A tab
     * 的删掉/存新要让 B tab 已展开的瓶卡就地跟上——removeItem 的
     * newValue=null 与新写入都走这条。 */
    if (e.key === 'wishbottle' || e.key === 'wishfulfilled') {
      try { _renderWishBottle(); } catch (eW0) {}
      try { _wishRefreshSummary(); } catch (eW1) {}
      return;
    }
    /* R3350：咒语册跨 tab——A tab 收/删，B tab 的册页/入口/行尾
     * 已收态就地跟上（removeItem newValue=null 与新写同链路）。 */
    if (e.key === 'mantraFav') {
      try { _mantraBookMeta(); } catch (eMV1) {}
      try { _renderMantraBook(); } catch (eMV2) {}
      try {
        var _mte = el('dailyMantra');
        _mantraFavSync(String((_mte && _mte.dataset.m) || ''),
                       String((_mte && _mte.dataset.d) || todayIso()));
      } catch (eMV3) {}
      return;
    }
    /* R3376：manifest: 跨 tab——A tab 念了，B tab 册头连念
     * 天数就地更新。 */
    if (e.key.indexOf('manifest:') === 0) {
      try { _mantraBookMeta(); } catch (eMF1) {}
      try { _renderMantraBook(); } catch (eMF2) {}
      return;
    }
    /* R3389（审-中）：qian:/mochi: 跨 tab——A tab 抽了签/答了题，
     * B tab 停在对应页时签筒/出题卡不再显陈旧空态。 */
    if (e.key.indexOf('qian:') === 0) {
      try { _renderQian(); } catch (eQ1) {}
      return;
    }
    if (e.key.indexOf('mochi:') === 0) {
      try { _renderMochi(); } catch (eM1) {}
      return;
    }
    if (e.key.indexOf('ansb:') === 0) {
      /* R3396-P2-7：答案卡开着时不重绘——答案只活在 DOM（无键可
       * 恢复），邻 tab 写 ansb:hist 会把它冲掉。 */
      if (!document.querySelector('#ansbBox .ansb-card')) {
        try { _renderAnsb(); } catch (eAB1) {}
      }
      return;
    }
    if (e.key.indexOf('shred:') === 0) {
      try { _shredRefreshSummary(); } catch (eSh) {}
      return;
    }
    if (e.key.indexOf('checkin:') === 0) {
      renderCheckin(todayIso());
      return;
    }
    /* R3318（审-P3-5）：A tab 收下信卡 B tab 的信卡仍挂——
     * weeklyLetter:* 键变化同样触发打卡卡重渲。 */
    if (e.key.indexOf('weeklyLetter:') === 0 ||
        e.key.indexOf('monthlyLetter:') === 0) {
      try { renderCheckin(todayIso()); } catch (eWL2) {}
      return;
    }
    /* R3306-P3：心情历/心情罐跨 tab——A 记了心情 B 的行原地亮。
     * journal:/ritual:/usage:/rlast:/read:scroll:/notify:/remind:/
     * threads_seen_v1/returnBannerDismissed 属低频或纯统计件，
     * 有意不跟——下次自然渲染时读到新值。 */
    if (e.key.indexOf('mood:') === 0 || e.key.indexOf('moodlv:') === 0) {
      try { _renderMoodRow(); } catch (eM3) {}
      /* 心情周记视图开着就就地重渲（函数内判 active，零成本）。 */
      try { _renderMoodWeek(); } catch (eM6) {}
      return;
    }
    if (e.key.indexOf('moodjar:') === 0) {
      try { _dailyMetaItem('dailyMoodJar', _moodJarHtml()); } catch (eM4) {}
      return;
    }
    /* R3306-P3：checkinBuff:*（每日打卡 buff 足迹）原漏在监听
     * 外——无重渲面，只需要别当陌生键走下去。 */
    if (e.key.indexOf('checkinBuff:') === 0) { return; }
    /* R3354（审-低）：couple:/futureLetters/pilePick: 跨 tab——A tab
     * 合拍交集回来/写了未来信/选了堆，B tab 打卡区卡面就地跟上。 */
    if (e.key.indexOf('couple:') === 0 ||
        e.key === 'futureLetters' || e.key === 'futureLetters:corrupt' ||
        e.key.indexOf('pilePick:') === 0) {
      try { renderCheckin(todayIso()); } catch (eCP) {}
      return;
    }
    /* R2400（R127-P2-3）：镜像键跨 tab——A 摘了心水/删了记录，
     * B 的 chips 与「本机留档」列表就地跟新（saver 同值不写，
     * 重渲染收敛不打转）。 */
    if (e.key === _FAV_MIRROR_KEY) {
      try { _hhFavsRender(); } catch (eF1) {}
      try { _qmFavsRender(); } catch (eF2) {}
      return;
    }
    if (e.key === _PH_MIRROR_KEY || e.key === _PH_MIRROR_DEL_KEY) {
      /* R2502：跨 tab 被动刷新不清正在读的详情（行没了才收）。 */
      try { if (window.__loadPaipanHistory) window.__loadPaipanHistory(true); }
      catch (eP) {}
      return;
    }
    /* R2349（R65-P2-3）：补其余个人键的跨 tab 同步——A 拆了礼物 B 的
     * 封面仍盖着、A 打完里程碑 B 又弹一次，都是同一类穿帮。 */
    if (e.key.indexOf('dailyRevealed:') === 0 && e.newValue) {
      /* R2349（R65-P2-3）：走 _bindDailyCover 暴露的清理面——断 MO、
       * 摘 inert、remove 封面三件事同做，否则兄弟节点永远不可点。 */
      if (window.__dailyCoverCleanup) window.__dailyCoverCleanup();
      else { var _cv = el('dailyCover'); if (_cv) _cv.remove(); }
      return;
    }
    if (e.key.indexOf('checkinCeleb:') === 0 ||
        e.key === 'hlask' || e.key === 'visits') { return; /* 下次渲染自然跟上 */ }
    if (e.key === 'welcomed' && e.newValue) {
      var _wb = el('welcomeBar'); if (_wb) _wb.remove();
      try { document.documentElement.classList.add('welcomed'); } catch (e2) {}
      return;
    }
    if (e.key === 'installTipDismissed' && e.newValue) {
      var _it = el('installTip'); if (_it) _it.remove();
      return;
    }
    /* R3265（R3250-P2）：voiceMode 键已无写入方——口吻跨 tab 死
     * 分支摘除；皮肤跨 tab 同步保留。 */
    if (e.key === THEME_KEY) { applyTheme(uiTheme()); }
    /* R3363-P1-5：A tab 登入/注册/登出/换号后 B tab 账号卡不跟——
     * 卡片照旧挂登录表单，还能在 B 直接登另一个号绕过登出清除。
     * 凭据/同步戳变化即重渲；换昵称再补一遍镜像清除。 */
    if (e.key === 'xmaccount' || e.key === 'xmaccount:lastsync' ||
        e.key === 'xmaccount:lastpull') {
      try { window.__acctRender(); } catch (eAR) {}
      if (e.key === 'xmaccount') {
        try { window.__acctCredsChanged(e.oldValue); } catch (eAC) {}
      }
      return;
    }
    /* R232a（R40-R2）：生日档案跨 tab 同步——A tab 改了生日，
     * B tab 表单下次进页才跟太迟，就地重填未手改字段。 */
    /* R2349y（R95-P1-3）：wipe 墓碑——A 整库清空后写入 wipeAt，
     * B tab 收到后把无 data-me 标记的表单字段（含手输生日/邀请链
     * 生辰）也清掉，并作废本 tab 的聊天会话态（sessionStorage 是
     * tab 级，A 够不到 B 的，各自收到事件自清）。 */
    if (e.key === 'wipeAt') {
      ['year', 'month', 'day', 'hour', 'gender',
       'b_year', 'b_month', 'b_day', 'b_hour', 'b_gender', 'b_nick',
       'th_year', 'th_month', 'th_day', 'th_hour', 'th_gender',
       'hh_a_year', 'hh_a_month', 'hh_a_day', 'hh_a_hour',
       'hh_a_gender', 'hh_a_name',
       'hh_b_year', 'hh_b_month', 'hh_b_day', 'hh_b_hour',
       'hh_b_gender', 'hh_b_name'].forEach(function (_fid) {
        var _f = document.getElementById(_fid);
        if (_f) {
          _f.value = '';
          delete _f.dataset.me;
          delete _f.dataset.invite;
          delete _f.dataset.touched;
        }
      });
      try { _MEM_STORE._m = {}; } catch (eM2) {}
      try { LAST_RESULT = {}; } catch (eLR) {}
      try { _renderMeStrip(); } catch (eMS2) {}
      try { renderCheckin(todayIso()); } catch (eRC2) {}
      return;
    }
    if (e.key === 'me' || e.key === 'me:partner') {
      /* R2349t（R87-P1-2e）：B tab 删掉档案（newValue=null）时本 tab
       * 不能走重填（早退后字段仍留旧生辰，再提交即复活）——
       * 清掉本 tab 里档案代入的字段。 */
      if (e.newValue === null) {
        ['year', 'month', 'day', 'hour', 'gender',
         'b_year', 'b_month', 'b_day', 'b_hour', 'b_gender', 'b_nick',
         'th_year', 'th_month', 'th_day', 'th_hour', 'th_gender',
         'hh_a_year', 'hh_a_month', 'hh_a_day', 'hh_a_hour',
         'hh_a_gender', 'hh_a_name',
         'hh_b_year', 'hh_b_month', 'hh_b_day', 'hh_b_hour',
         'hh_b_gender', 'hh_b_name'].forEach(function (_fid) {
          var _f = document.getElementById(_fid);
          if (_f && _f.dataset.me === '1') {
            _f.value = '';
            delete _f.dataset.me;
            delete _f.dataset.touched;
          }
        });
        /* R2349y（R95-P1-3）：字段清了但档案条/打卡面没重渲——
         * B tab 会挂着已删档案直到刷新。 */
        try { _renderMeStrip(); } catch (eMS) {}
        try { renderCheckin(todayIso()); } catch (eRC) {}
      } else { _meFillAll(); }
      /* R3343：档案变了——合拍对可能换了人，强行再对一次
       * （pair_id 重算，ck 不符的旧交集自动不顶包）。 */
      try { _coupleSync(true); } catch (eCPx) {}
    }
  });

  /* R230n（R25-3.2）：深链——?view=huangli 或 /huangli 路径式皆可，
   * 白名单内直接落到对应功能页。拼错/越名单的静默回首页（不报错）。
   * （路径式依赖 app.py 的 SPA 兜底回 index.html）
   * R230q（R28-P3-6）：非法 view 静默回首页用户会以为链接坏了——给
   * 一句 toast；R28-P2-3 起 pushState 带 ?view=，初始化落页不再补推
   * 一条重复历史（__suppressPush）。 */
  try {
    var _vp = new URLSearchParams(location.search).get('view');
    var _badPath = false;
    if (!_vp) {
      var _seg = location.pathname.replace(/^\/+|\/+$/g, '');
      /* R2348（R66-P2）：多级路径 /huangli/extra 此前静默落首页、
       * 与 /bogus 提示口径不一致——含 / 的非空路径同样按坏链处理。 */
      if (_seg && _seg.indexOf('/') < 0) _vp = _seg;
      else if (_seg) _badPath = true;
    }
    /* R2348（R66-P2）：规整——HUANGLI/bazi%20 此前直接当坏链弹提示。 */
    if (_vp) _vp = _vp.trim().toLowerCase();
    if (_vp || _badPath) {
      /* R231d（R39-P0-2）：海报分享链会带 daily/checkin/birth 三个
       * 无独立视图的别名——受邀者落地吃「入口不存在」toast 是负承接。
       * 别名映射 + 落地后滚动/展开承接：daily/checkin→首页 daily 卡、
       * birth→星座页的本命盘抽屉。 */
      var _vpRaw = _vp;
      var _alias = { daily: 'home', checkin: 'home', 'checkin-week': 'home',
                     'checkin-month': 'home', weekly: 'home',
                     birth: 'xingzuo',
                     /* R2349v（R92-P0-2）：古籍域视图 id 是 read，但任务书/
                     * 直觉都写 research——别名收编，免得深链查无此页。 */
                     research: 'read', books: 'read', library: 'read',
                     /* R2502：chat 是伪视图（点击开侧栏不切页）——深链
                      * ?view=chat 此前吃「入口不存在」toast。归一化到首页
                      * 并在落地后把侧栏打开，与点卡行为对齐。 */
                     chat: 'home',
                     /* R2364（R120-P1-2）：速配分享链写 view=xzm，速配卡
                      * 住在星座视图里——别名收编，不再弹「入口不存在」。 */
                     xzm: 'xingzuo',
                     /* R3304（审-P0）：lucky/bandaid/bazi-yearly 海报
                      * 分享链全是死链——护身符/创可贴住首页日签卡一带，
                      * 年度运势就是 bazi 视图的产物。别名收编+滚动承接。 */
                     lucky: 'home', bandaid: 'home',
                     'bazi-yearly': 'bazi',
                     /* R3318（审-P1-1）：开运壁纸分享链 ?view=daily-wap
                      * 死链——壁纸入口在首页日卡，归一到 home。 */
                     'daily-wap': 'home' };
      if (_alias[_vp]) _vp = _alias[_vp];
      /* R2349v（R92-P0-1）：合法性判据原来是「视图存在 + 有入口卡」——
       * R208b 裁掉古籍域入口卡后，read/history 两个已有视图的深链
       * 被连带判死（F5 状态全丢、toast 谎报「入口不存在」）。卡是
       * 入口展示层，不该当视图合法性判据——按视图元素存在判。 */
      var _vpOk = (_vp === 'home') ||
        !!document.getElementById('view-' + _vp);
      if (_vpOk) {
        /* R233n（R47-Top5-1）：合婚邀请链落地——?view=hehun&ay&am&ad
         * &ah&ag&an 把发起人的盘预填进 A 侧，受邀者只需填自己。
         * R2349（R65-P2-1）：剥参后 F5 预填静默丢——值存 sessionStorage
         *（tab 级，关窗即焚，不进历史/书签），刷新后从这儿回灌。 */
        var _qsAll = new URLSearchParams(location.search);
        /* R2350a（R94-P1-2）：?view=huangli&date=YYYY-MM-DD 深链——
         * 校验合法后存内存，激活黄历时按该日查（参数被剥也不丢）。 */
        try {
          var _hld = _qsAll.get('date');
          if (_vp === 'huangli' && _hld) {
            var _okD = false;
            if (/^\d{4}-\d{2}-\d{2}$/.test(_hld)) {
              var _hdt = new Date(+_hld.slice(0, 4), +_hld.slice(5, 7) - 1,
                                  +_hld.slice(8, 10));
              var _hdy = +_hld.slice(0, 4);
              _okD = _hdy >= 1900 && _hdy <= 2100 &&
                _hdt.getMonth() === +_hld.slice(5, 7) - 1 &&
                _hdt.getDate() === +_hld.slice(8, 10);
            }
            if (_okD) {
              window.__hlDeepDate = _hld;
            } else {
              /* R2350b（R99-P0 附带）：链接里的日期不合法（2/30、
               * 超量程）——静默落今天但给接收方一句交代。
               * R3332-低：warn 级 toast 被 showView 的跨视图清扫摘掉
               *（只留 error）——延到切视图落定后再弹。 */
              setTimeout(function () {
                try {
                  showToast('那条链接里的日子打不开，先看今天的吧', 'warn');
                } catch (eT) {}
              }, 600);
            }
          }
        } catch (eHD) {}
        /* R3369（审-P1-1）：古籍深链 ?view=read&rq=词&bs=书号 此前
         * 参数整包被剥——落地只剩空页。存内存，showView(read) 侧消费。 */
        try {
          if (_vp === 'read') {
            var _rdq = _qsAll.get('rq'), _rdb = _qsAll.get('bs');
            if (_rdq || _rdb) {
              window.__readDeep = {
                q: _rdq ? String(_rdq).slice(0, 100) : null,
                bs: _rdb ? String(_rdb).slice(0, 64) : null };
            }
          }
        } catch (eRD) {}
        /* R2350f（R102-P1-1 落地侧）：分享链带 seed——?view=tarot&s=N&tn=3
         * 或 ?view=liuyao&m=coins&s=N，落地先重现「TA 抽到的那副」。
         * R2350g（R104-P2）：只认 from=share 的链——手搓裸 s= 不播重放；
         * s=0/超界 tn 不产生重放（生成侧永不写这些值）。 */
        try {
          var _ss = _qsAll.get('s');
          var _seedOk = _ss && /^\d{1,10}$/.test(_ss) &&
                        parseInt(_ss, 10) >= 1;
          var _tnv = parseInt(_qsAll.get('tn') || '', 10);
          if (_seedOk && _qsAll.get('from') === 'share' &&
              (_vp === 'tarot' || _vp === 'liuyao')) {
            window.__shareSeed = {
              view: _vp, seed: parseInt(_ss, 10),
              tn: (_tnv >= 1 && _tnv <= 10) ? _tnv : 3,
              method: _qsAll.get('m') === 'coins' ? 'coins' : null,
              /* R2354（R112-P1-2/3）：自点索引/牌阵 key 随链还原 */
              cards: (function () {
                var _c = _qsAll.get('c');
                if (!_c) return null;
                var _a = String(_c).split(',').map(function (x) {
                  return parseInt(x, 10); }).filter(function (x) {
                  return Number.isInteger(x) && x >= 0 && x <= 77;
                });
                return (_a.length >= 1 && _a.length <= 10) ? _a : null;
              })(),
              spread: (function () {
                var _p = _qsAll.get('sp');
                return (_p && _p.length <= 20) ? _p : null;
              })()
            };
          }
        } catch (eSS) {}
        /* R2349s（R86-P1-7）：别名视图（daily/checkin/checkin-week/
         * birth）归一化会把 from=share 参数剥掉——新客欢迎条与老用户
         * 承接 toast 都读不到，全成死代码。剥参前先存进内存。 */
        try {
          if (_qsAll.get('from') === 'share') {
            window.__shareFromView = _vpRaw;
            /* R3266：dream 的 sym 随视图存——剥参前留底。 */
            if (_vpRaw === 'dream' && _qsAll.get('sym')) {
              window.__shareSym =
                String(_qsAll.get('sym')).slice(0, 12);
            }
            /* R2349t（R88-13b）：分享者昵称随链——剥参前先存，
             * sessionStorage 备份让刷新后也能喊出名字。 */
            var _sby0 = _qsAll.get('n');
            if (_sby0) {
              window.__shareBy = String(_sby0).slice(0, 24);
              try {
                /* R2350b（R99-P2）：昵称绑当次链的视图指纹——同 tab
                 * 再开别的不带 n= 的分享链不再喊上一位的名字。 */
                sessionStorage.setItem('shareBy:' + _vpRaw,
                  window.__shareBy);
                /* 别名落地后 URL 规整成 _vp——F5 回灌按新名查。 */
                if (_vp !== _vpRaw) {
                  sessionStorage.setItem('shareBy:' + _vp,
                    window.__shareBy);
                }
              } catch (eSB) {}
            }
          }
        } catch (eSF) {}
        /* R2349u（R89-P1-3）：紧凑邀请格式——投放/手拼短链
         * ?view=hehun&invite=1&a=1998-7-20-女-12&an=小雅
         * 在读 ay 前展开成原生参数，复用同一链路。 */
        if (_vp === 'hehun' && _qsAll.get('invite') === '1' &&
            _qsAll.get('a')) {
          try {
            var _cp = String(_qsAll.get('a')).split('-');
            var _cpv = ['ay', 'am', 'ad', 'ag', 'ah'];
            _cp.slice(0, 5).forEach(function (_cv, _ci) {
              if (_cv) _qsAll.set(_cpv[_ci], _cv);
            });
          } catch (eCP) {}
        }
        /* R3307（审-中3）：hash 段生辰白名单合入——R3307 起邀请链把
         * ay/am/ad/ah/ag/an 放 #（不出本机），落地端统一回灌 _qsAll。
         * 只在 from=invite / invite=1 语境下吃 hash，普通锚点不误吃。 */
        if (location.hash &&
            (_qsAll.get('from') === 'invite' || _qsAll.get('invite') === '1')) {
          try {
            var _hq = new URLSearchParams(location.hash.slice(1));
            ['ay', 'am', 'ad', 'ah', 'ag', 'an',
             /* R3313（审-P1-4）：历法/闰月同白名单 */
             'ac', 'al'].forEach(function (_hk) {
              var _hv = _hq.get(_hk);
              if (_hv != null) _qsAll.set(_hk, _hv);
            });
          } catch (eHQ) {}
        }
        var _invA = _qsAll.get('ay');
        /* R2350b（R99-P2）：同 tab 残留串台——受邀过的 tab 再开
         * from=share 普通分享链时，sessionStorage 里的旧邀请参会复活
         *（发起人数据串进来）。显式带 from 的落地不吃回灌；F5 剥参后
         * URL 无 from，回灌照常。 */
        if (_vp === 'hehun' && !_invA && !_qsAll.get('from')) {
          try {
            /* R2400（R130-P3-1）：F5 回灌只在真刷新（reload）——同 tab
             * 手动开 ?view=hehun（navigate）不该复活上次的邀请态。 */
            var _navT = (performance.getEntriesByType &&
                        (performance.getEntriesByType('navigation')[0] || {})
                       ).type;
            if (_navT == null || _navT === 'reload') {
              var _sv = sessionStorage.getItem('hhInvite');
              if (_sv) _qsAll = new URLSearchParams(_sv);
            } else {
              sessionStorage.removeItem('hhInvite');
            }
          } catch (eSS) {}
          _invA = _qsAll.get('ay');
        }
        /* R2364：ay 非 4 位年 = 伪造/残缺链——不进邀请态（不然空字段
         * 摆出「TA 的信息已填好」的假欢迎，出厂默认生日混进真值）。 */
        /* R2400（R130-P1-1/P3-2/P3-3）：门槛再收——年月日齐全且在
         * 范围、时辰 0-23、性别只收 男/女，才算邀请链。残参不进
         * 邀请态（否则缺格被受邀者自己的 me 档案静默填上，出个不是
         * 发起人盘的假合盘，toast 还谎报「已填好」）。 */
        var _invFull = _vp === 'hehun' && _invA &&
          /^\d{4}$/.test(_invA) && +_invA >= 1900 && +_invA <= 2100 &&
          /^\d{1,2}$/.test(_qsAll.get('am') || '') &&
          /^\d{1,2}$/.test(_qsAll.get('ad') || '') &&
          +(_qsAll.get('am') || 0) >= 1 && +(_qsAll.get('am') || 0) <= 12 &&
          +(_qsAll.get('ad') || 0) >= 1 && +(_qsAll.get('ad') || 0) <= 31 &&
          (_qsAll.get('ag') == null || _qsAll.get('ag') === '' ||
           _qsAll.get('ag') === '男' || _qsAll.get('ag') === '女') &&
          (_qsAll.get('ah') == null || _qsAll.get('ah') === '' ||
           (/^\d{1,2}$/.test(_qsAll.get('ah')) && +_qsAll.get('ah') <= 23)) &&
          /* R3313：ac 只收 lunar/solar/空，al 只收 1/空 */
          (_qsAll.get('ac') == null || _qsAll.get('ac') === '' ||
           _qsAll.get('ac') === 'lunar' || _qsAll.get('ac') === 'solar') &&
          (_qsAll.get('al') == null || _qsAll.get('al') === '' ||
           _qsAll.get('al') === '1');
        if (_vp === 'hehun' && _invFull) {
          /* R2400（R130-P1-1）：进邀请态先把 A 侧清零——init 早段的
           * _meFillAll 已按默认映射把受邀者自己的生日填过这些格子，
           * 没给的字段不能留着那份值冒充发起人的盘。性别是必填位，
           * 没带就占位「女」（与提交/后端回落口径一致）。 */
          ['hh_a_year','hh_a_month','hh_a_day','hh_a_hour','hh_a_name'
          ].forEach(function (_cid) {
            var _ce = document.getElementById(_cid);
            if (_ce) { _ce.value = ''; delete _ce.dataset.me; }
          });
          var _ag0 = document.getElementById('hh_a_gender');
          if (_ag0) { _ag0.value = '女'; delete _ag0.dataset.me; }
          [['ay','hh_a_year',1],['am','hh_a_month',1],['ad','hh_a_day',1],
           ['ah','hh_a_hour',1],['ag','hh_a_gender',0],['an','hh_a_name',0]
          ].forEach(function (p) {
            var v = _qsAll.get(p[0]), elx = document.getElementById(p[1]);
            /* 不置 data-me——非空值本身就不被 _meFill 覆盖（置 1 反而
             * 放行：受邀者自己的档案会盖掉发起人数据）。
             * R233r（R50-#17）：时辰留空时也要把默认值清成空——
             * 「未知时辰」比静默按 10 点算诚实。
             * R2364（R121-P2）：伪造参护栏——数字段只收纯数字、昵称
             * 按后端 max_length=16 截断，手搓长串不再换来 422。 */
            if (v != null && p[2]) {
              if (!/^\d{1,4}$/.test(v)) v = null;
            } else if (v != null && p[0] === 'an') {
              v = v.slice(0, 16);
            }
            if (elx && v != null &&
                (v !== '' || elx.tagName !== 'SELECT')) {
              elx.value = v;
              /* R2343：邀请值免疫档案回填（meFill 现在会盖默认值） */
              elx.dataset.invite = '1';
              /* R3313（审-P1-4）：历法位落地——发起人按农历填的
               * 生日受邀者端要切到农历档+闰月行，不然原始数字
               * 静默当公历合，差出整个月令。 */
              if (_qsAll.get('ac') === 'lunar') {
                var _acs = document.getElementById('hh_a_cal');
                if (_acs) {
                  _acs.value = 'lunar';
                  _acs.dataset.invite = '1';
                  try { _acs.dispatchEvent(new Event('change')); } catch (eC) {}
                }
                var _alp = document.getElementById('hh_a_leap');
                if (_alp && _qsAll.get('al') === '1') _alp.checked = true;
              }
            }
          });
          /* 受邀者填的是 B 侧=自己——提交时 me/partner 归属要翻转，
           * 否则发起人的生日会顶掉受邀者自己的档案。用户手改 A 侧
           * 任一字段即视同放弃邀请口径，恢复默认归属。 */
          window.__hhInviteMode = true;
          /* R2349（R65-P1-5）：邀请态下 A 侧装的是发起人的盘，但标签
           * 写「我的」、B 侧「TA 的」是出厂默认值——受邀者把自己填进
           * A 覆盖掉对方数据、留下假 B 提交而无提示。翻转标签语义：
           * A→「TA 的（已填好）」、B→「我的」，并清掉 B 侧出厂值，
           * 让空着=没填一目了然。 */
          [['hh_a_year','TA 的出生年'],['hh_a_month','TA 的出生月'],
           ['hh_a_day','TA 的出生日'],['hh_a_hour','TA 的时辰'],
           ['hh_a_gender','TA 的性别'],['hh_a_name','TA 的昵称'],
           ['hh_b_year','我的出生年'],['hh_b_month','我的出生月'],
           ['hh_b_day','我的出生日'],['hh_b_hour','我的时辰'],
           ['hh_b_gender','我的性别'],['hh_b_name','我的昵称']
          ].forEach(function (_lp) {
            var _lb = document.querySelector('label[for="' + _lp[0] + '"]');
            if (_lb) _lb.textContent = _lp[1];
          });
          /* B 侧出厂值（1992/8/20/14/男）不是受邀者填的——清空，手填
           * 或档案回填都从这空白态开始；留 placeholder 提示。 */
          ['hh_b_year','hh_b_month','hh_b_day','hh_b_hour'].forEach(
            function (_id) {
              var _be = document.getElementById(_id);
              if (_be) _be.value = '';
            });
          /* R2348（R66-P2）：邀请态下 B 侧档案源=me——置位后补跑一次
           * 回填（init 早段的 _meFillAll 还按默认映射填过 hh_b）。 */
          try { _meFillAll(); } catch (eM) {}
          /* R2349p（R80-P2）：受邀者=B=「我」，面向小红书女性用户——
           * 档案没带性别时出厂默认「男」不合适；昵称例也从阿哲换成中性。 */
          try {
            var _bgr = document.getElementById('hh_b_gender');
            if (_bgr && !_bgr.dataset.me && _bgr.selectedIndex <= 0) {
              _bgr.value = '女';
            }
            var _bnm = document.getElementById('hh_b_name');
            if (_bnm) _bnm.placeholder = '可空，如：小梨';
          } catch (eN) {}
          /* R2364（R121-P1-1）：邀请态归属全程固定——A 侧装的是
           * 发起人的盘，受邀者手改它多半是「帮 TA 修正」，不是把
           * 别人生日据为己有。此前一改 A 侧就翻转归属，提交时把
           * 发起人生辰写进受邀者自己的 me 档案（污染不可逆）。
           * 现在改 A 不再翻——受邀者真要另测一对，换 B 侧就行。 */
          /* R2345（R63-P2-6）：邀请链生辰此前驻留 location.search——
           * 浏览器历史/分享面板长存明文生日。落地预填后剥掉参数
           * （深链语义不变，?view=hehun 保留以便刷新仍回本页）。 */
          /* R2349（R65-P2-1）：剥参前先把邀请参原样存 sessionStorage——
           * F5 回灌靠它；关 tab 自动焚毁，与「不落历史」同口径。 */
          try {
            sessionStorage.setItem('hhInvite',
              'ay=' + encodeURIComponent(_qsAll.get('ay') || '') +
              '&am=' + encodeURIComponent(_qsAll.get('am') || '') +
              '&ad=' + encodeURIComponent(_qsAll.get('ad') || '') +
              '&ah=' + encodeURIComponent(_qsAll.get('ah') || '') +
              '&ag=' + encodeURIComponent(_qsAll.get('ag') || '') +
              '&an=' + encodeURIComponent(_qsAll.get('an') || '') +
              /* R3313：历法位同进 F5 回灌 */
              '&ac=' + encodeURIComponent(_qsAll.get('ac') || '') +
              '&al=' + encodeURIComponent(_qsAll.get('al') || ''));
          } catch (eSS2) {}
          /* R2349p（R80-P1-2）：from=invite 被剥参后欢迎条分支永远读不到——
           * 剥前先存一份，_mk() 优先读它。 */
          try { window.__landingFrom = 'invite'; } catch (eF0) {}
          /* R2349t（R88-14）：发起人昵称存内存——结果页回发提示用。 */
          try {
            window.__hhInviteBy = String(_qsAll.get('an') || '').slice(0, 24);
          } catch (eIB) {}
          /* R3247：明星邀请链——发起人把明星生辰编进了链接，受邀者
           * 落地 A 侧=明星。按「名字+年月日」对回 celeb.json 名单：
           * 命中即切明星合盘口径（导语/公开资料标注/TA 档案免疫），
           * 顺带藏掉选择器抽屉（受邀者自己不需要再挑明星）。 */
          try { _celebClear(); } catch (eCC) {}
          try {
            var _cdr = el('celebDrawer');
            if (_cdr) _cdr.hidden = true;
          } catch (eCD) {}
          _celebLoad().then(function () {
            try {
              if (!_CELEBS || !_CELEBS.length) return;
              var _an0 = (val('hh_a_name') || '').trim();
              var _mc = _CELEBS.filter(function (c) {
                return c.n === _an0 &&
                  num('hh_a_year') === +c.y &&
                  num('hh_a_month') === +c.m &&
                  num('hh_a_day') === +c.d;
              })[0];
              if (!_mc) return;
              __hhCeleb = { n: _mc.n, y: +_mc.y, m: +_mc.m, d: +_mc.d,
                g: (_mc.g === '男' || _mc.g === '女') ? _mc.g : '',
                tag: String(_mc.tag || ''), note: String(_mc.note || ''),
                side: 'a' };
              /* 明星侧标来源：档案回填免疫 + 台账名置 null。 */
              ['hh_a_year','hh_a_month','hh_a_day','hh_a_hour',
               'hh_a_gender','hh_a_name','hh_a_cal','hh_a_leap'
              ].forEach(function (id) {
                var e = el(id);
                if (e && e.dataset) e.dataset.celeb = '1';
              });
              _celebPickedRender();
            } catch (eCM) {}
          });
          try {
            history.replaceState(null, '',
              location.pathname + '?view=hehun');
          } catch (e5) {}
          setTimeout(function () {
            showToast(window.__hhInviteBy ?
              window.__hhInviteBy + ' 约你来合婚：TA 的信息已填好，轮到你了 💕' :
              'TA 的信息已经填好啦，轮到你了 💕');
            var _by = document.getElementById('hh_b_year');
            if (_by) { try { _by.focus(); } catch (e) {} }
          }, 350);
        }
        /* R2400（R130-P1-1）：标着邀请却不过关的链——残参/越界/性别
         * 伪造——不进邀请态，明说一声按普通页用；顺手把同 tab 残留
         * 的旧邀请参清掉免得 F5 复活。 */
        else if (_vp === 'hehun' &&
                 (_qsAll.get('from') === 'invite' ||
                  _qsAll.get('invite') === '1' || _invA)) {
          try { sessionStorage.removeItem('hhInvite'); } catch (eRI) {}
          try {
            history.replaceState(null, '',
              location.pathname + '?view=hehun');
          } catch (eRS) {}
          setTimeout(function () {
            showToast('这条邀请链接缺了点信息，当普通合婚用就好～', 'info');
          }, 350);
        }
        var _hold = window.__suppressPush;
        window.__suppressPush = true;
        try { showView(_vp); } finally { window.__suppressPush = _hold; }
        /* R2350f（R102-P1-1）：seed 重放——表单照常摆着，结果区先渲染
         * 「TA 抽到的」。抽她自己的仍是原按钮动线。 */
        if (window.__shareSeed && window.__shareSeed.view === _vp) {
          var _ssd = window.__shareSeed;
          window.__shareSeed = null;
          setTimeout(function () { _replaySharedDraw(_ssd); }, 250);
        }
        /* R3353（审-P2）：明星合盘分享链 celeb=<名>——收方落地
         * 按名单把 B 侧填好公开生辰（同手点明星），「和 X 合盘」
         * 语境不丢；名字不在册静默回落普通合婚页。 */
        if (_vp === 'hehun' && _qsAll.get('from') === 'share' &&
            _qsAll.get('celeb')) {
          var _cnm = String(_qsAll.get('celeb') || '').slice(0, 16);
          try {
            _celebLoad().then(function () {
              try {
                var _cm = (_CELEBS || []).filter(function (c) {
                  return c.n === _cnm; })[0];
                if (_cm) _celebPick(_cm);
              } catch (eCM) {}
            });
          } catch (eCL) {}
        }
        /* R2350b（R99-P2）：微信/小红书容器内落地的分享/邀请链——
         * beforeinstallprompt 不触发、装桌面提示缺席，给一行轻提示
         * 让接收方知道可以「浏览器打开更灵」。 */
        try {
          var _ua0 = navigator.userAgent || '';
          if (/MicroMessenger|xhsdiscover|XHSAPP|discover\//i.test(_ua0) &&
              (window.__shareFromView || window.__landingFrom)) {
            setTimeout(function () {
              showToast('在' +
                (/MicroMessenger/i.test(_ua0) ? '微信' : '小红书') +
                '里存图/分享不灵的话，点右上 ··· 用浏览器打开更灵～',
                'info');
            }, 1600);
          }
        } catch (eUA) {}
        if (_vpRaw !== _vp) {
          /* R2348（R66-P2）：别名落地后地址栏还挂 ?view=daily 残留——
           * 规整到目标视图的规范 URL。 */
          try {
            history.replaceState({ view: _vp }, '',
              _vp === 'home' ? '/' : '/?view=' + encodeURIComponent(_vp));
          } catch (eR) {}
          setTimeout(function () {
            /* R2349（R65-P2-6）：checkin-week 别名此前落首页顶部无
             * 承接——和 daily/checkin 一样滚到日签卡（签运图在那）。 */
            if (_vpRaw === 'daily' || _vpRaw === 'checkin' ||
                _vpRaw === 'checkin-week' || _vpRaw === 'checkin-month' ||
                _vpRaw === 'lucky' || _vpRaw === 'bandaid') {
              var _dc = document.getElementById('dailyCard');
              if (_dc) _dc.scrollIntoView({ behavior: _rmBehavior(), block: 'start' });
            } else if (_vpRaw === 'birth') {
              var _bd = document.getElementById('birthDrawer');
              if (_bd) _bd.open = true;
            } else if (_vpRaw === 'xzm') {
              /* R2505：速配分享链落星座页后速配抽屉仍合着——收链的人
               * 看不见速配卡，分享闭环断在最后一米。与 birth 同款
               * 自动展开+滚到位；日运数据晚到会重排页面，1.1s 后再
               * 校一次滚动。 */
              var _xd = document.getElementById('xzMatchDrawer');
              if (_xd) {
                _xd.open = true;
                var _xscroll = function () {
                  _xd.scrollIntoView({ behavior: _rmBehavior(),
                                       block: 'start' });
                };
                _xscroll();
                setTimeout(_xscroll, 1100);
              }
              /* R3260：分享链带 a/b/rel（from=share 才跑，手搓裸参
               * 不自动测）——收方直接看到「TA 测的那对」的结果，
               * 与白名单校验后的星座名预填；坏参静默忽略。 */
              try {
                if (_qsAll.get('from') === 'share') {
                  var _za = _qsAll.get('a'), _zb = _qsAll.get('b'),
                      _zr = _qsAll.get('rel');
                  var _sa3 = el('xzm_a'), _sb3 = el('xzm_b');
                  /* _SIGNS 是 IIFE 私域——白名单直接读 select 的
                   * option values（同源不漂移）。 */
                  var _okS = function (x) {
                    return !!x && _sa3 &&
                      [].some.call(_sa3.options, function (o) {
                        return o.value === x; });
                  };
                  if (_sa3 && _sb3 && _okS(_za) && _okS(_zb)) {
                    _sa3.value = _za; _sb3.value = _zb;
                    var _re3 = el('xzm_rel');
                    if (_re3 && (_zr === '闺蜜' || _zr === '同事')) {
                      _re3.value = _zr;
                    }
                    setTimeout(function () {
                      /* R3332-低：自动重放标记——rememberResult 的回赠
                       * toast 按视图豁免这次被动提交。 */
                      window.__autoReplaySubmit = 'xzm';
                      var _xs = el('xzmSubmit');
                      if (_xs) _xs.click();
                    }, 450);
                  }
                }
              } catch (eXZ) {}
            } else if (_vpRaw === 'chat') {
              /* R2502：伪视图深链承接——落到首页后把聊天侧栏打开，
               * 与点「和小满聊聊」卡同行为。 */
              try { chatOpen(); } catch (eCO) {}
            }
          }, 300);
        } else {
          /* R2350b（R99-P2）：分享/邀请参数落地后剥掉——转抄地址栏
           * 不把原作者昵称和生辰带进下一跳；view/date 保留（F5/转抄
           * 仍指向同一视图同一张卡）。别名分支在上面已规整过。 */
          try {
            var _qs2 = new URLSearchParams(location.search);
            var _dirty = false;
            /* R3307（审-低）：补 sym/sp/c——sym 是梦象征名属半隐私，
             * 留在地址栏会被截图/转抄带走。R3353：celeb 同收编。 */
            ['from', 'n', 'invite', 'a', 'an', 'ay', 'am', 'ad', 'ah',
             'ag', 's', 'tn', 'm', 'b', 'rel', 'sym', 'sp', 'c',
             'celeb']
             .forEach(function (_k) {
              if (_qs2.has(_k)) { _qs2.delete(_k); _dirty = true; }
            });
            /* R3304（审-P0）：裸 ?view=X 落地（无分享参）此前不回写
             * state——底条目停在脚本首行的 {view:'home'}，海报模态
             * history.back() 直接甩回首页。恒回写真落地视图。
             * R3395-P0：#mc[rs]?= 默契链的载荷就在 hash——剥了受邀者
             * 答完题「看默契分」死钮、成绩页退化成出题卡。白名单放行；
             * hehun 邀请 hash 刻意剥（R3307 隐私），其他族照旧。 */
            var _q2 = _qs2.toString();
            var _h2 = /^#mc[rs]?=/.test(location.hash || '')
              ? location.hash : '';
            history.replaceState({ view: _vp }, '',
              location.pathname + (_q2 ? '?' + _q2 : '') + _h2);
          } catch (eSP) {}
        }
      } else if (_vp !== 'home' || _badPath) {
        showToast('这个入口不存在，先带你回首页', 'info');
        /* R232c（R41-nit）：清掉坏参——否则 F5 会再弹一遍同样 toast。
         * R2348（R66-P2）：pathname 本身就是坏参时原写法把它原样写回，
         * /bogus 永远清不掉——统一归 '/'。 */
        try {
          history.replaceState({ view: 'home' }, '', '/');
        } catch (e) {}
      }
    }
  } catch (e) {}
}

/* R3259（UX-STRATEGY-NEXT N3）：心情回路——74% 用户为缓解焦虑而来，
 * 「止痛药」人群的留存靠被接住的感觉可预期（Finch 式轻回路）：
 * 1-tap 心情打卡 → 小满回一句（心情×判词档确定性文案池）→
 * 心情历近 14 天色点。全 localStorage，零后端零账号。
 * R3304（审-P1）：声明必须在 init() 调用点之前——init 同步链
 * （_chatChipsPersonalize → 记忆事实板）会读 _MOOD_META，放后面
 * var 只提升声明不提升赋值，TypeError 被 try 吞掉=事实板永久空。 */
var _MOOD_META = [
  { e: '😮‍💨', t: '有点累', c: '#C78C9E' },
  { e: '😐', t: '一般般', c: '#B9AE9C' },
  { e: '🙂', t: '还不错', c: '#D9B36A' },
  { e: '🥳', t: '状态满分', c: '#8FA86F' }];
/* R3262（R17）：心情罐子——每攒满 7 个色点解锁一张小满场景图，
 * 不惩罚断签，只讲「收下了多少」。场景表长即封顶（现 6 张），
 * 缺图时静默不展示。 */
var _MOOD_JAR_SCENES = [
  { k: '窗边茶', url: '/static/cream/bear-scene-good.jpg' },
  { k: '雨毯堡', url: '/static/cream/bear-scene-mid.jpg' },
  { k: '小夜灯', url: '/static/cream/bear-scene-sml.jpg' },
  { k: '坏天气', url: '/static/cream/bear-scene-bad.jpg' },
  /* R3315（R3310-P2）：场景深度扩到 6——4 张封顶后色点还在涨
   * 却没有下一站，长期用户失钩。两张新图同风格补齐。 */
  { k: '暖被窝', url: '/static/cream/bear-scene-cozy.jpg' },
  { k: '雨灯路', url: '/static/cream/bear-scene-lantern.jpg' }];
var _MOOD_REPLY = {
  '0g': '累就别硬撑——今天盘面有暗劲帮你，事可以缓一缓，人先歇口气。',
  '0l': '累的时候更要对自己松一点——盘面不硬的日子，少排一件事、早点收工就是赚。',
  '1g': '平平的心配平顺的签——不用刻意做什么，顺着走就到了。',
  '1l': '心稳就是赢——盘面不硬的日子，不动气就已经是赚了，剩下的交给明天。',
  '2g': '心情好+签也顺：那件想做很久没动的事，今天就适合开个头。',
  '2l': '心情好是你自带的小太阳——盘面一般的日子，状态就是你的底牌。',
  '3g': '状态满分+好签加持，今天适合把好消息攒下来，回头跟小满报喜。',
  '3l': '状态这么棒，盘面挡不住你——该干嘛干嘛，小满给你记一功。'};
/* 心情周记判词池——init() 调用点之前声明（R3304 同款：深链
 * ?view=moodweek 的 init 同步链读它）。按主情绪分桶，每桶 ≥6 句、
 * 周序取模定句——累的那周配「辛苦了」向文案，不评判、不临床
 * （禁「情绪不稳定」式用语）。 */
var _MOOD_WEEK_LINES = {
  /* 判词按主情绪分桶，每桶 ≥6 句、周序取模定句——累的那周配「辛苦了」
   * 向文案，不评判、不临床（禁「情绪不稳定」式用语）。 */
  tired: [
    '这周辛苦了——能记下来的日子，都是你在照顾自己的证据。',
    '累攒了一周，小满先给你倒杯热茶：歇够了再往前走。',
    '连着几天喊累不是矫情，是日子真的沉——先把自己照顾好。',
    '这周的疲惫小满都看见了，把事往外推一推不丢人。',
    '累了这么多天还肯记一笔，说明你心里一直给自己留着位置。',
    '这周电量见底不怪你——硬的日子，少排一件就是赚。',
    '辛苦了一整周，今晚允许自己什么都不干，这也算数。'],
  meh: [
    '平平的一周也算数——不用每天都过得有声响。',
    '不咸不淡的日子，其实是生活在给你留力气。',
    '这周像温吞的茶——没什么大事，就是好日子。',
    '一般般也是一种过法，小满陪你把下周过出点小滋味。',
    '心里平平稳稳，就已经赢过兵荒马乱。',
    '不急不躁的一周，攒下的安稳会算进以后。',
    '平淡不是白过——稳稳的一周也值得记下。'],
  good: [
    '这周发光的日子偏多——好状态要趁热用，惦记的事往前排。',
    '状态满分的一周，小满替你收好这份心气。',
    '好天气要晒出来——这周的你值得一个夸夸。',
    '开心攒了一周，这是你自己挣来的。',
    '这周的你自带太阳——把这份顺劲分一点给下周。',
    '心情好的时候做什么都顺，这周好好用掉它。',
    '亮晶晶的一周，记得告诉以后的自己：你能这么开心。'],
  none: [
    '这周还没怎么记心情——想记的时候，点一下首页心情行就好。',
    '空白的一周也没什么，哪天想起小满，色点就开始攒。',
    '这周格子是空的——不催你，心情罐永远在这儿。',
    '还没攒下心情点？从今天这颗开始，下周就有得翻。',
    '一周没记不代表没过——下周想晒的时候随时来。',
    '小满这周的罐子替你留着，想往里丢点心情随时都行。']
};

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
/* ── R231d（R37-F4/F7）：首访/深链落地新人条——之前新客进页零定位
 * 文案，全靠悟性；可关，关过（localStorage welcomed）不再出现。 */
(function () {
  var _seen = false;
  try { _seen = !!window.localStorage.getItem('welcomed'); } catch (e) { _seen = true; }
  /* R2350c（R97-P1-1）：welcomed 此前只在点新人条 × 时写——没点过 ×
   * 的老用户天天见「第一次来？」，且 ret_tip 回访指路被永久锁死。
   * 回头客（访次>1 或有任何 checkin: 键）进来即补写，新人条只给
   * 真新客看。 */
  if (!_seen) {
    try {
      var _veteran = _visitCount() > 1;
      if (!_veteran) {
        for (var _li = 0; _li < window.localStorage.length; _li++) {
          var _lk = window.localStorage.key(_li);
          /* R3314（R3309-P2）：checkin:goal 配置键命中前缀就把
           * 「只设过周目标、从未打卡」的新客误标老用户。同口径
           * 按日期后缀过滤。 */
          if (_lk && _lk.indexOf('checkin:') === 0 &&
              /^\d{4}-\d{2}-\d{2}$/.test(String(_lk).slice(8))) {
            _veteran = true; break;
          }
        }
      }
      if (_veteran) {
        window.localStorage.setItem('welcomed', '1');
        document.documentElement.classList.add('welcomed');
        _seen = true;
      }
    } catch (e) {}
  }
  /* R233t（R51-P2-18c）：老用户点朋友分享链接也要有承接语境——
   * welcomeBar 跳过、toast 一句即可。 */
  if (_seen) {
    /* R2349m（R58-B-001 后半）：二次回访补一句指路——迎新条已撤，
     * 日签卡入口对回访者值得再点一次名（只此一次）。 */
    try {
      if (!window.localStorage.getItem('ret_tip') &&
          !location.search) {
        window.localStorage.setItem('ret_tip', '1');
        setTimeout(function () {
          showToast('日签每天更新：点第一张卡看今天的 ✨', 'ok');
        }, 1500);
      }
    } catch (e) {}
    try {
      var _qs = new URLSearchParams(location.search);
      /* R2349s（R86-P1-7）：剥参过的别名视图从内存里捞回 from/view。 */
      var _isShare = _qs.get('from') === 'share' || !!window.__shareFromView;
      if (_isShare) {
        /* R2349l（R73-P1-13）：接力承接按来源视图说话——
         * 「TA 抽了塔罗，看看你的」比通用一句更有接力感。 */
        var _sv = _qs.get('view') || window.__shareFromView || '';
        var _relay = {
          tarot: '朋友在晒她抽的塔罗牌：点下面抽你的 🃏',
          daily: '朋友在晒今天的签：上面第一张就是你的 ✨',
          checkin: '朋友在攒连签，打卡一下，今天的签就归你 ✍️',
          'checkin-week': '朋友在晒她的一周签运：你的周运也攒一个 🗓️',
          'checkin-month': '朋友在晒她的一月签运：你的月运也攒一个 🗓️',
          birth: '朋友翻了她的本命盘，你的底色也翻一张 🌙',
          hehun: '朋友在晒合婚指数：你和 TA 也来一对 💕',
          bazi: '朋友在晒她的八字盘：你的盘也排一排 🔮',
          xingzuo: '朋友在晒今日星座运：看看你的宫今天说啥 ⭐',
          qiming: '朋友在晒起的好名字：你的名字也测测 🌸',
          taohua: '朋友在晒桃花信号，你的桃花今天啥情况 🌺',
          liuyao: '朋友摇了一卦，心里有件事也来摇一爻 🎲',
          /* R3319-P2：老客承接表补遗——7 个视图落通用句「测测你的」
           * 指错路（页面上根本没卡可点）。 */
          huangli: '朋友在晒老黄历，你那天也翻翻 📅',
          xzm: '朋友测了星座合拍，你们的呢 ⭐',
          renge: '朋友测了五行人格，你是哪型 🧸',
          lucky: '朋友领了今日护身符，你的也接住 🍀',
          bandaid: '朋友递来一张创可贴，收下吧 🩹',
          weekly: '朋友在晒她的一周小满周报，你的也生一份 📊',
          'bazi-yearly': '朋友出炉了年度运势，你的也测测 📅',
          'daily-wap': '朋友换了开运壁纸，你的也换一张 📱',
          /* R3395-P2-5：本轮三族补承接——落地不再是通用兜底。 */
          mochi: '朋友给你下了默契战书：答 5 题看你们多合拍 🤝',
          qian: '朋友抽了支签给你看：你的今日签也抽一支 🎋',
          ansb: '朋友从答案之书翻了一页：你的问题也翻一页 📖',
        };
        if (_sv === 'dream') {
          var _symT = (window.__shareSym ||
            new URLSearchParams(location.search).get('sym') || '');
          _relay.dream = _symT
            ? ('朋友对上了「' + String(_symT).slice(0, 12) +
               '」，你的梦呢？🌙')
            : '朋友在晒她的梦，你的梦也来翻一翻 🌙';
        }
        /* R2349t（R88-13c）：链上带昵称时喊名——「陌生人晒的」
         * 变「我朋友喊我的」。 */
        var _who = _shareByName();
        var _rt = (_relay[_sv] || '朋友在晒她的运势：来测测你的 ✨');
        if (_who) _rt = _rt.replace(/^朋友/, _who);
        setTimeout(function () { showToast(_rt, 'ok'); }, 800);
      }
    } catch (e) {}
    return;
  }
  function _mk() {
    /* R2348（R67-P1）：bar 静态在 index.html（首帧占位消 CLS），这里只
     * 接管交互：老用户（html.welcomed）摘掉节点、受邀回流换承接文案。 */
    var bar = document.getElementById('welcomeBar');
    if (!bar) return;
    if (document.documentElement.classList.contains('welcomed')) {
      bar.remove();
      return;
    }
    /* R39-P2-1：受邀回流（?from=share）换一句承接——「朋友在晒她的运势」
     * R2349（R65-P2-2）：from=invite（合婚邀请链）也给专属承接——
     * 此前落通用文案与「TA 的信息已填好」toast 语义打架。 */
    var _from = null;
    var _sv2 = null;
    try {
      _from = new URLSearchParams(location.search).get('from');
      _sv2 = new URLSearchParams(location.search).get('view');
      /* R2349p（R80-P1-2）：邀请链 from=invite 已被剥参——回落到
       * init 时存下的 __landingFrom。 */
      if (!_from && window.__landingFrom) _from = window.__landingFrom;
      /* R2349s（R86-P1-7）：别名 share 链同样被剥参——内存兜底。 */
      if (!_from && window.__shareFromView) {
        _from = 'share'; _sv2 = window.__shareFromView;
      }
    } catch (e) {}
    var _txtEl = bar.querySelector('.welcome-txt');
    /* R3370-P1-1：share/invite 落地时欢迎条在非 home 视图被
     * data-view 规则盖死——新受邀者零承接语境。落标放行。 */
    if (_from === 'share' || _from === 'invite') {
      try { document.body.dataset.relay = '1'; } catch (e) {}
    }
    if (_txtEl && _from === 'share') {
      /* R2349l（R73-P1-13）：新客落地也按接力视图说话。 */
      var _relayBar = {
        /* R3319-P2：受邀者已落在目标页，欢迎条说页内动作，
         * 不再指回首页卡（「点塔罗占卜」而人已在塔罗页是指错路）。 */
        tarot: '朋友抽了塔罗牌喊你接力：想好要问的事，点「抽一张」抽你的 🃏',
        daily: '朋友在晒今天的签：上面第一张就是你的 ✨',
        checkin: '朋友在攒连签，打卡一下，今天的签就归你 ✍️',
        'checkin-week': '朋友在晒她的一周签运：你的也攒一个 🗓️',
        'checkin-month': '朋友在晒她的一月签运：你的也攒一个 🗓️',
        /* R3332-中：原句指路的「📊 生成本周小报」钮只活在聊天空态且
         * 要 _weekVisits>0——新受邀者永远到不了，指路指死路。改成欢迎条
         * 直挂真按钮（_shareWeekly 0 天也出稀疏周报卡，不报错）。 */
        weekly: '朋友在晒她的一周小满周报——你的也出一份 📊',
        birth: '朋友翻了她的本命盘，你的底色也翻一张 🌙',
        hehun: '朋友约你合婚：填好你的生日就能对上盘 💕',
        /* R3319-P2：承接表补遗——此前 11 个视图落通用句指错路。 */
        huangli: '朋友帮你查了宜忌：上面就是 TA 翻的那页黄历 📅',
        xzm: '朋友测了星座合拍，你们的也测测 ⭐',
        renge: '朋友测了五行人格，你是哪型 🧸',
        lucky: '朋友领了今日护身符，你也接住这份运气 🍀',
        bandaid: '朋友给你递了张创可贴：睡不着就来领一张 🩹',
        'bazi-yearly': '朋友出炉了年度运势，你的也测测 📅',
        bazi: '朋友排了八字盘，填生日你的盘也排一排 🔮',
        xingzuo: '朋友翻了今日星座运，你的宫今天说啥 ⭐',
        qiming: '朋友测了好名字，你的名字也来测 🌸',
        taohua: '朋友晒了桃花信号，你的桃花今天啥情况 🌺',
        liuyao: '朋友摇了一卦，想好要问的事你也摇一爻 🎲',
        'daily-wap': '朋友换了开运壁纸，你的也换一张 📱',
        /* R3395-P2-5：本轮三族补承接——页内动作指真钮。 */
        mochi: '朋友给你下了默契战书：答上面 5 题，看你们多合拍 🤝',
        qian: '朋友抽了支签给你看：点「摇一支今日签」抽你的 🎋',
        ansb: '朋友从答案之书翻了一页：默念问题，点「翻一页」 📖',
      };
      if (_sv2 === 'dream') {
        var _symW = (window.__shareSym ||
          new URLSearchParams(location.search).get('sym') || '');
        _relayBar.dream = _symW
          ? ('朋友对上了「' + String(_symW).slice(0, 12) +
             '」，你的梦也说说 🌙')
          : '朋友在晒她的梦，你的梦也说说 🌙';
      }
      var _who2 = _shareByName();
      _txtEl.textContent = ((_relayBar[_sv2] ||
        /* R3319-P2：通用句「点一张卡就能开始」在结果页落地时
         * 指错路——收回到不带错误指向的兜底。 */
        '朋友在晒她的运势，来测测你的 ✨')
        .replace(/^朋友/, _who2 || '朋友'));
      /* R3332-中：weekly 深链的「生成小报」原指路聊天空态 chip——
       * 受邀新客 _weekVisits=0 永不可达。欢迎条直接挂可点 CTA。 */
      if (_sv2 === 'weekly' && !bar.querySelector('.welcome-cta')) {
        var _wcta = document.createElement('button');
        _wcta.type = 'button';
        _wcta.className = 'welcome-cta';
        _wcta.textContent = '📊 生成我的本周小报';
        _wcta.addEventListener('click', function () {
          try { _shareWeekly(); } catch (eSW) {}
        });
        bar.insertBefore(_wcta, bar.querySelector('.welcome-close'));
      }
      /* R3336（审-中）：bandaid 受邀链白天落地=纯画饼——创可贴钮只在
       * 23-05/水逆聊天空态，欢迎条指「领一张」却没得点。直挂真按钮
       * 出海报模态（按时段挑场景，同空态钮口径）。 */
      if (_sv2 === 'bandaid' && !bar.querySelector('.welcome-cta')) {
        var _wcta2 = document.createElement('button');
        _wcta2.type = 'button';
        _wcta2.className = 'welcome-cta';
        _wcta2.textContent = '🩹 领这张创可贴';
        _wcta2.addEventListener('click', function () {
          try {
            var _nh = new Date().getHours();
            var _night = (_nh >= 23 || _nh < 5);
            var _im = new Image();
            _im.src = _night ? '/static/cream/bear-scene-bad.jpg'
                             : '/static/cream/bear-scene-mid.jpg';
            _im.onload = function () {
              downloadPoster({ _art: _im,
                _artCap: _night ? '今夜小夜灯' : '慢慢来的日子' },
                'bandaid');
            };
            _im.onerror = function () { downloadPoster({}, 'bandaid'); };
          } catch (eBD) {}
        });
        bar.insertBefore(_wcta2, bar.querySelector('.welcome-close'));
      }
    } else if (_txtEl && _from === 'invite') {
      _txtEl.textContent = (window.__hhInviteBy || 'TA') +
        ' 约你来合婚，填好你的生日就能对上盘 💕';
    } else if (_txtEl && _sv2) {
      /* R2350f（R102-P2-4）：非 share 深链（书签/手敲 ?view=tarot）落地
       * 已在塔罗页，通用句「点一张卡就能测」指错路。 */
      var _plainBar = {
        tarot: '你已经在塔罗页了，想好要问的事，抽一张就是 🃏',
        liuyao: '你已经在六爻页了，想好要问的事，摇一卦就是 ☯️',
        hehun: '你已经在合婚页了，填你和 TA 的生日就能合 💕',
        huangli: '你已经在黄历页了，上面就是今天的宜忌 📅',
        bazi: '你已经在排盘页了，填生日点「排个盘」 🔮',
        taohua: '你已经在桃花页了，填生日看最近桃花 🌺',
        qiming: '你已经在起名页了，填姓氏和生日就能起 🌸',
        xingzuo: '你已经在星座页了，上面就是今日运势 ⭐',
        read: '你已经在古籍域了，搜个词翻翻看 📜',
        history: '这里是排盘历史：看过的盘都收在这里 🗂',
      };
      if (_plainBar[_sv2]) _txtEl.textContent = _plainBar[_sv2];
    } else if (_txtEl) {
      /* R3264（R42）：时段感知问候——按当前小时给不同文案，
       * 让首页第一句话像小满亲口说的。 */
      var _h = new Date().getHours();
      var _dp = (_h < 6) ? 'night' : (_h < 10) ? 'dawn'
                : (_h < 12) ? 'morning' : (_h < 18) ? 'noon'
                : (_h < 22) ? 'dusk' : 'night';
      var _greet = {
        dawn: '天刚亮——先抽张日签看看今天的气场 🌅',
        morning: '上午好——有事想算，没事小满也在 🌤',
        noon: '中午了——抽个签再决定吃什么 🍜',
        dusk: '傍晚好——今天最想问什么？🌆',
        night: '晚上好——小满的夜灯开着，慢慢聊 🌙'
      };
      _txtEl.textContent = _greet[_dp] || _greet.morning;
    }
    bar.querySelector('.welcome-close').addEventListener('click', function () {
      /* R2349h（R69-P2-7）：自毁钮先把焦点还到页内落点，
       * 否则键盘党焦点丢 body 从头爬。 */
      var _nx = document.querySelector('.skip-link') || el('funcGrid');
      if (_nx && _nx.focus) { try { _nx.focus(); } catch (e) {} }
      bar.remove();
      try { window.localStorage.setItem('welcomed', '1'); } catch (e) {}
      try { document.documentElement.classList.add('welcomed'); } catch (e) {}
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _mk);
  } else { _mk(); }
})();

/* R3314（R3311-高1）：头部节日的「今天该怎么过」tip 池——节日名
 * 到了只报名字没下文。按子串命中（服务端节日名带别名变体），
 * 一句确定性暖心行动，不发明运势。 */
var _FEST_TIP = [
  ['春节', '新年第一天：给家人发个消息，比什么仪式都开运'],
  ['大年初一', '新年第一天：给家人发个消息，比什么仪式都开运'],
  ['除夕', '今晚守岁别熬太晚，岁末把旧心事留在旧年'],
  ['中秋', '月亮最圆的一晚：给想你的人回个消息'],
  ['七夕', '牛郎织女都见面了——想见的人，今天就去见'],
  ['情人节', '爱与被爱都值得庆祝，先对自己好一点'],
  ['女神节', '今天是你的节日：把自己放在第一顺位'],
  ['妇女节', '今天是你的节日：把自己放在第一顺位'],
  ['女生节', '今天是你的节日：把自己放在第一顺位'],
  ['跨年', '今年最后一晚：写一句给明年的自己'],
  ['元旦', '新年第一天：立个小一点的愿望，容易灵'],
  ['元宵', '花灯如昼：今晚适合和家人朋友聚一聚'],
  ['端午', '吃个粽子讨个平安，湿热天多照顾自己'],
  ['母亲节', '给妈妈发条消息吧，她在等'],
  ['父亲节', '给爸爸发条消息吧，他不太会说但在等'],
  ['教师节', '想起哪位老师就告诉她，一句话就好'],
  ['国庆', '难得的假期：出去走走或好好躺着，都算数'],
  ['圣诞', '叮当作响的日子：给在乎的人挑个小礼物'],
  ['平安夜', '今晚吃颗苹果讨个平安，早点回家'],
  ['万圣', '南瓜灯的日子：可以鬼混，但别熬夜'],
  ['双十一', '购物车满不满都要记得：你最贵'],
  ['521', '表白日：喜欢就说出来，最坏也就是现在'],
  ['儿童', '谁还不是个宝宝：今天允许自己幼稚一回'],
  ['愚人', '玩笑归玩笑，今天别人的话留三分'],
  ['植树', '种点什么吧——阳台一盆也算'],
  ['劳动', '劳动者的节日：今天允许自己躺平'],
  ['青年', '青春正好：去做一件想了很久的事'],
  ['腊八', '喝碗热粥暖暖身子，年味从今天开始了'],
  ['小年', '扫尘祭灶：把家里收拾出一块干净的角落'],
  ['重阳', '登高望远的好日子，也给家里老人打个电话'],
  ['龙抬头', '抬头的日子：剪个头发换个心情'],
  ['花朝', '百花生辰：给自己带一枝花回家'],
  ['上巳', '春日水边：出去走走，沾沾春气'],
  ['寒衣', '天冷了：添衣，也记挂记挂故人'],
  ['下元', '水官解厄日：心里的结今天松一松'],
  ['中元', '追思的日子：心里记挂着的人，今天点一盏灯']
];
function _festTip(festName) {
  var _n = String(festName || '');
  for (var _ti = 0; _ti < _FEST_TIP.length; _ti++) {
    if (_n.indexOf(_FEST_TIP[_ti][0]) >= 0) return _FEST_TIP[_ti][1];
  }
  return '';
}

/* R2349t（R88-2b）：节日/节气带——结果页与黄历页同一句时令。
 * 数据读 __lastDaily（loadDaily 每次启动已拉，零新请求；无节静默）。 */
function _festivalBand() {
  try {
    var _d = window.__lastDaily || {};
    var _f = _pArr(_d.festival)[0] || _pStr(_d.term && _d.term.name);
    if (!_f) return '';
    var _tip = _pStr(_d.term && _d.term.tip) || _festTip(_f);
    /* R3370-P1-3：节日名与提示缺分隔粘成病句（「今天是万圣夜
     * 南瓜灯的日子」）——对齐另两处节日行的 ' · ' 口径。 */
    return '<div class="hl-festival">🎐 今天是' + esc(_f) +
      (_tip ? ' · ' + esc(_tip) : '') + '</div>';
  } catch (e) { return ''; }
}

/* ── R3373 正缘画像（smCard）───────────────────────────────────
 * 日主天干→五行→气质型（离线烘的 sm-* 底图）；命中桃花星换浪漫版。
 * 「样子是想象，信号是真的」——画像写气质不写脸。 */
var _SM_GAN_WX = { '甲': '木', '乙': '木', '丙': '火', '丁': '火',
                   '戊': '土', '己': '土', '庚': '金', '辛': '金',
                   '壬': '水', '癸': '水' };
var _SM_ARCH = {
  '木': { k: 'sm-wood', n: '青竹少年感型',
          traits: ['清爽', '有书卷气', '像风一样舒服'],
          tip: 'TA 吃软不吃硬，温柔比道理管用' },
  '火': { k: 'sm-fire', n: '暖阳元气型',
          traits: ['明朗', '行动派', '笑起来很亮'],
          tip: 'TA 的喜欢写在脸上，别猜，看行动' },
  '土': { k: 'sm-earth', n: '大地安稳型',
          traits: ['踏实', '话不多', '记得你的小事'],
          tip: 'TA 的浪漫藏在日常里，别看表面平淡' },
  '金': { k: 'sm-metal', n: '清冷白月光型',
          traits: ['干净', '克制', '慢热但认真'],
          tip: 'TA 不热络但很长情，给点耐心' },
  '水': { k: 'sm-water', n: '深海温柔型',
          traits: ['沉静', '会听人说话', '情绪很细腻'],
          tip: 'TA 什么都懂但不说破，坦白换真心' },
};
var _SM_PEACH = { k: 'sm-peach', n: '桃花心动型',
                  traits: ['第一眼就记住', '有故事感', '气场很合'],
                  tip: '这段缘的信号很强，别错过窗口' };

function _smPick(j) {
  /* 命中咸池≥2 柱 或 桃花正旺 → 浪漫版；否则按日主五行定型。 */
  if ((j.hit_pillars || []).length >= 2 || j.strength === 'strong') {
    return _SM_PEACH;
  }
  var _gan = String((j.bazi || {}).day_master || '').charAt(0);
  var _wx = _SM_GAN_WX[_gan];
  return _SM_ARCH[_wx] || _SM_PEACH;
}

function _smTiming(j) {
  /* 相遇信号与海报 dayun 口径同源：眼下在走的运 → 正旺；否则
   * 最近将到的运年；全无 → 红鸾生肖年提示兜底。 */
  var _ny = new Date().getFullYear();
  var _next = null, _cur = null;
  (j.dayun_hits || []).forEach(function (d) {
    var ys = +(d && d.year_start || 0);
    if (!ys) return;
    if (ys <= _ny && _ny < ys + 10) { if (!_cur) _cur = ys; }
    else if (ys > _ny && !_next) _next = ys;
  });
  if (_cur) return '眼下这步运（至约 ' + (_cur + 10) + ' 年）桃花信号正旺';
  if (_next) return '约 ' + _next + ' 年起有一波正缘信号靠近';
  if (j.hongluan) return '红鸾星动时相遇——多在「' + j.hongluan + '」生肖年';
  return '信号藏在日子的缝隙里——急不得，但也别错过对的眼神';
}

function _smCard(j) {
  var _a = _smPick(j);
  var _h = '<div class="sm-card">' +
    '<div class="sm-art"><img src="/static/soulmate/' + _a.k +
      '.jpg" alt="' + esc(_a.n) + '氛围图" loading="lazy"></div>' +
    '<div class="sm-name">' + esc(_a.n) + '</div>' +
    '<div class="sm-traits">' +
    _a.traits.map(function (t) {
      return '<span class="sm-trait">' + esc(t) + '</span>';
    }).join('') + '</div>' +
    '<div class="sm-tip">💡 ' + esc(_a.tip) + '</div>' +
    '<div class="sm-timing">⏳ ' + esc(_smTiming(j)) + '</div>' +
    '<div class="sm-note">样子是想象，信号是真的——画像按你的盘' +
      '推出气质型，不是真的脸</div>' +
    '<button class="ghost fav-btn" type="button" id="smShare" ' +
      'title="生成正缘画像分享图">📸 晒出 TA 的画像</button>' +
    '</div>';
  return { html: _h, arch: _a };
}

function _smOpen(j) {
  var _smBox = el('smCard');
  if (!_smBox || !j) return;
  var _c = _smCard(j);
  _smBox.innerHTML = _c.html;   // esc-reviewed：_smCard 内动态字段均过 esc()
  on('smShare', function () {
    var _im = new Image();
    _im.src = '/static/soulmate/' + _c.arch.k + '.jpg';
    var _j2 = function (im) {
      var _o = { _artCap: _c.arch.n, _smTraits: _c.arch.traits,
                 _smTip: _c.arch.tip, _smTiming: _smTiming(j) };
      if (im) _o._art = im;
      return downloadPoster(Object.assign({}, j, _o), 'soulmate');
    };
    _im.onload = function () { _j2(_im); };
    _im.onerror = function () { _j2(null); };
  });
  _smBox.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/* ── R213b：微交互特效（点击涟漪 + 星星迸发 / 滑动拖尾 / 卡片入场）──
 * 纪律：全部只动 transform/opacity（check_plain_first 判据 2 门柱安全）；
 * prefers-reduced-motion 下整体停用。 */
(function () {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  /* R2349t（R88-4）：星星迸发抽成可复用入口——吉签日卡/高分合婚
   * 也能放一发；本 IIFE 在 reduced-motion 下整体跳过，天然合规。 */
  window.__fxBurstAt = function (bx, by) {
    for (var i = 0; i < 6; i++) {
      var s = document.createElement('span');
      s.className = 'fx-spark';
      s.style.left = bx + 'px'; s.style.top = by + 'px';
      var ang = Math.random() * Math.PI * 2, dist = 24 + Math.random() * 30;
      s.style.setProperty('--dx', Math.cos(ang) * dist + 'px');
      s.style.setProperty('--dy', Math.sin(ang) * dist - 18 + 'px');
      s.style.animationDelay = (i * 30) + 'ms';
      document.body.appendChild(s);
      setTimeout(function (n) { return function () { n.remove(); }; }(s), 700 + i * 30);
    }
  };

  /* 点击涟漪 + 星星迸发 */
  document.addEventListener('click', function (e) {
    /* R233k（R45-§1）：涟漪白名单收窄到真交互元素——原 list 含 .card
     * 兜底，点纯文本/空白处也放烟花（每次 ~7 个一次性 DOM 节点，
     * 还制造「可点假象」）。点到非交互区直接不放。 */
    var host = e.target.closest(
      'button, .btn, .func-card, #dailyCover, .work-card, .chat-entry,' +
      '.hl-chip, .hl-scene, .hl-daychip, .hl-week-cell, .checkin-opt,' +
      '.rtab, .chat-chip, .xz-chip, .qm-style-chip, .fav-chip,' +
      '.chat-sug, .ph-open, .ph-del, .thread-view, .daily-me-edit,' +
      '.recent-toggle, .view-back, a[href], [role="button"], summary');
    if (!host) return;
    var x = e.clientX, y = e.clientY;
    var ripple = document.createElement('div');
    ripple.className = 'fx-ripple';
    ripple.style.left = x + 'px'; ripple.style.top = y + 'px';
    /* R233y（R55-P1-1）：涟漪挂 body 不挂 host——host 有 transform
     * 祖先时 fixed 退化为 absolute，右缘点击瞬时撑 scrollWidth
     * （实测 467-598px）页面横移。body 无 transform，视口坐标稳。 */
    document.body.appendChild(ripple);
    setTimeout(function () { ripple.remove(); }, 650);
    window.__fxBurstAt(x, y);
  }, true);

  /* 滑动拖尾：touchmove 节流生成渐隐星尘 */
  var lastTrail = 0;
  document.addEventListener('touchmove', function (e) {
    var now = Date.now();
    if (now - lastTrail < 40) return;
    lastTrail = now;
    var t = e.touches[0];
    var d = document.createElement('span');
    d.className = 'fx-trail';
    d.style.left = t.clientX + 'px'; d.style.top = t.clientY + 'px';
    document.body.appendChild(d);
    setTimeout(function () { d.remove(); }, 600);
  }, { passive: true });

  /* 卡片入场：IntersectionObserver 渐入上浮 */
  var io = ('IntersectionObserver' in window) ? new IntersectionObserver(function (es) {
    es.forEach(function (en) {
      if (en.isIntersecting) { en.target.classList.add('fx-in'); io.unobserve(en.target); }
    });
  }, { threshold: 0.08 }) : null;
  function watchCards(root) {
    (root || document).querySelectorAll('.card:not(.fx-watch)').forEach(function (c) {
      c.classList.add('fx-watch');
      if (io) io.observe(c); else c.classList.add('fx-in');
    });
  }
  watchCards();
  /* 动态插入的结果区也纳入观察。
   * R230j（R22-P3-5）：原来每批变更都全文档 querySelectorAll——
   * 聊天气泡等高频插入也触发全扫。改为只扫 mutation.addedNodes
   * （含其子树里的 .card）。 */
  new MutationObserver(function (muts) {
    for (var mi = 0; mi < muts.length; mi++) {
      var an = muts[mi].addedNodes;
      for (var ni = 0; ni < an.length; ni++) {
        var n = an[ni];
        if (n.nodeType !== 1) continue;
        if (n.matches && n.matches('.card:not(.fx-watch)')) {
          n.classList.add('fx-watch');
          if (io) io.observe(n); else n.classList.add('fx-in');
        }
        if (n.querySelectorAll) watchCards(n);
      }
    }
  }).observe(document.body, { childList: true, subtree: true });
})();

/* ── R214b：「今日玄学搭子」打卡互动（纯前端，确定性反馈）── */
/* R233n（R47-Top5-4）：打卡池扩到 8——每日确定性抽 4 展示
 * （_dayPickN 同日同序），新鲜度翻倍且选过的签不受轮换影响
 * （saved 命中已轮换走的项时在首位补显）。 */
const CHECKIN_OPT_POOL = ['开运蛋', '吃瓜运', '摸鱼运', '破水逆运',
  '暴富签', '甜甜运', '上岸运', '顺顺签'];
/* R3317-D：今日咒语池——同日全站同句（晒出去能对上号的社群感）。
 * 小红书体祈愿句：短、上口、可截图，不含算命/预测类违规词。 */
var _MANTRA_POOL = [
  '水逆退散，钱包回暖', '霉运清零，好事常来', '烦恼退退退',
  '好运充值成功', '今天也是被幸运点名的人', '诸事顺利，心想事成',
  '今日好运已到账', '难事先放一放，先吃饭', '小确幸浓度拉满',
  '今天走路都带风', '好运气从这里开始', '所求皆所愿，所行皆坦途',
  '今日份快乐已签收', '好事正在派送中', '今天不谈烦心事',
  '运气这回事，我信', '顺顺当当过今天', '小满即圆满',
  '今天的好事不止一件', '心宽的人运气不会差', '福气正在路上',
  '今天适合好好待自己', '困难退散，快乐翻倍', '愿望清单推进中',
  '今天的我是限量版', '好运会迟到但不会缺席', '日子一天天，越来越甜',
  '今天也为小目标蓄力', '好运与好心态双向奔赴', '不急不慌，好事不慌',
  '今天的快乐额度无限', '所愿皆成，所遇皆暖', '把烦恼调成静音',
  '今天是个好日子', '好心态是最好的好运', '小满未满，一切都刚好'];
/* R233j（R46-P1）：与 copy_bank.json checkin.feedback 对齐。
 * R2349g（R68-P2）：此前「对齐」注释在说谎——json 缺 4 签+default，
 * 已补齐（options/feedback 全 9 池）。前端这份仍是唯一消费方。 */
const CHECKIN_FEEDBACK = {
  '开运蛋': ['今天这个运简直像开了挂，冲鸭！', '好运来敲门，接住了别撒手！', '哇这个运，今天走路都带风～', '恭喜抽到隐藏款好运！', '好运正在派送中，今天请保持微笑收货～', '开运蛋孵化成功，今天就是你的幸运日本日！'],
  '吃瓜运': ['瓜运当头，记得带好小板凳前排围观！', '今天的瓜管够，吃瓜吃到撑～', '前方瓜田已备好，快来蹲！', '今日瓜源充足，放心吃～', '瓜田守护者就是你，今天的瓜又大又甜～', '吃瓜群众已就位，精彩剧情马上开场！'],
  '摸鱼运': ['摸鱼运爆棚，快乐一下不过分！', '摸鱼时长建议不超过15分钟哦～', '今日摸鱼许可证已签发，适度摸～', '摸鱼有理，偷懒无罪，今天你最大～', '摸鱼搭子已上线，劳逸结合才是真谛～', '摸鱼运加持，记得摸完鱼把正事也收个尾～'],
  '破水逆运': ['霉运走开，今天就是好运本运！', '破水逆运！诸事皆宜的一天开始了～', '水逆已被小满击退，今天顺顺顺！', '退退退！水逆已被赶走，好运来～', '水逆退散符已生效，今天横着走都没事～', '霉运清零成功，接下来都是上坡路！'],
  '暴富签': ['暴富签已签收，财神今天站你这边！', '今天的你是被钱眷顾的体质，大胆冲～', '暴富签生效中：先定一个小目标！', '财运雷达全开，今天的羊毛记得薅～', '今天的理财灵感特别灵，记下来！', '暴富签加持，偏财正财都向你靠拢～'],
  '甜甜运': ['甜甜运已加载，今天的糖度超标！', '今天的空气都是蜜桃味的～', '甜甜运在线，笑一下好运加倍～', '今天是被人间温柔包围的一天～', '甜甜运送达：有人正在偷偷想你～', '甜系 buff 已挂，今天甜度管够～'],
  '上岸运': ['上岸运满格：目标已经在向你招手！', '今天离上岸又近了一步，稳住！', '上岸运护航，该背的背该做的做～', '岸就在前方，今天别停！', '上岸签加持，努力会被看见的～', '今天做的每道题都在铺路，上岸稳了～'],
  '顺顺签': ['顺顺签生效，今天一路绿灯！', '今天主打一个事事顺遂～', '顺顺签到手，水逆什么的都不存在～', '今天的节奏刚好，顺势而行就行～', '顺顺签保佑：想要的都在路上～', '今天宜顺水推舟，忌跟自己较劲～'],
  '生日签': ['生日签到手：今天你是全场主角，愿望尽管许！',
             '生日这天的签最灵：许个愿，运气加倍奉还！',
             '生日签已签收：今天所有好事都默认归你～',
             '生日快乐！这张签是限定款：今天只管开心。',
             '生日签生效：今天宜收下所有好意与蛋糕～',
             '限定签get：今天宇宙偏心你，理直气壮一点！'],
  /* 兜底：存档里的旧签名轮换出池后仍可读回执 */
  '_default': ['这个签收好了，今天的运归你管～', '好运已领取，今天的能量满格！', '签已到手，今天的日子你做主～']
};
/* R3249c（UX-AUDIT A3 · 用户实测「四个运不知道是干嘛的」）：
 * 签名全是圈内黑话（上岸=考公圈、摸鱼=职场梗、水逆=占星圈），
 * 且没有一句「点了会怎样」的说明。内部键不变（存量打卡记录兼容），
 * 按钮显示名+用途副标全部人话化：每张签都回答「它是干嘛的、
 * 什么时候点」。 */
const CHECKIN_LABEL = {
  '开运蛋': ['🥚 攒好运', '给今天存一点好运气'],
  '吃瓜运': ['🍉 吃个瓜', '蹲蹲今天的热闹事'],
  '摸鱼运': ['🐟 求喘息', '累了就歇会儿，理直气壮'],
  '破水逆运': ['🌊 转个运', '给最近的倒霉翻个篇'],
  '暴富签': ['💰 求财运', '摸摸今天的钱袋子'],
  '甜甜运': ['🍬 来点甜', '给今天加一点糖'],
  '上岸运': ['📚 求顺利', '考试面试答辩求过'],
  '顺顺签': ['🍀 求顺遂', '今天一路绿灯'],
  '生日签': ['🎂 生日签', '今天你是主角，愿望随便许']
};
/* R3252：签面小插画文件键——翻过来的签不再是纯文字，
 * 每张签一张同 IP 奶油熊小图；文件名与 CHECKIN_LABEL 对齐。 */
const CHECKIN_ART = {
  '开运蛋': 'sign-egg', '吃瓜运': 'sign-melon', '摸鱼运': 'sign-fish',
  '破水逆运': 'sign-wave', '暴富签': 'sign-rich', '甜甜运': 'sign-candy',
  '上岸运': 'sign-ashore', '顺顺签': 'sign-lucky',
  '生日签': 'sign-birthday'
};
/* R230y（R36-P1-3）：打卡沉淀——checkin:* 键保留最近 90 天，
 * 渲染连续天数 + 近 7 天点阵 + 「昨天你选了X」召回。 */
function _checkinAll() {
  var set = {};
  try {
    for (var i = 0; i < window.localStorage.length; i++) {
      var k = window.localStorage.key(i);
      /* R3314（R3309-P2）：checkin:goal / checkin:goal-celebrated:<date>
       * 等配置键以 checkin: 开头被全量收进——签册计数虚高、断签判定
       * 把从没打过卡的人算成断签、welcomed 老用户判定被污染。只收
       * 真日期后缀键。 */
      if (k && k.indexOf('checkin:') === 0 &&
          /^\d{4}-\d{2}-\d{2}$/.test(String(k).slice(8))) {
        set[String(k).slice(8)] = window.localStorage.getItem(k);
      }
    }
  } catch (e) {}
  return set;
}
/* R3325-D：写给未来的自己——写信弹层。送达日三档：一个月后/
 * 下个生日（有档案）/一年后；存 futureLetters，到日在打卡区浮出。 */
function _flWriteOpen() {
  var old = document.getElementById('flModal');
  if (old) old.remove();
  var bd = document.createElement('div');
  bd.id = 'flModal';
  bd.className = 'poster-modal-backdrop open';
  var bday = '', ny = new Date();
  try {
    var pj = _meGet('me');
    if (pj && pj.m && pj.d) {
      var mm = ('0' + pj.m).slice(-2) + '-' + ('0' + pj.d).slice(-2);
      var cand = ny.getFullYear() + '-' + mm;
      if (cand <= todayIso()) cand = (ny.getFullYear() + 1) + '-' + mm;
      /* R3329（审-P2）：me.m=13 这类脏档案能造出 2026-13-01——
       * 非真日期的候选不进选项（假日期永远送不到）。
       * R3328（审-低）：2/29 生日在非闰年落 2/28——合法则原期，
       * 非法顺延到当月最后一天（3/1 偏离生日语义）。 */
      if (isNaN(new Date(cand + 'T00:00:00').getTime()) &&
          mm === '02-29') cand = cand.slice(0, 7) + '-28';
      if (!isNaN(new Date(cand + 'T00:00:00').getTime())) bday = cand;
    }
  } catch (ePB) {}
  bd.innerHTML = '<div class="poster-modal fl-modal" role="dialog" ' +
    'aria-modal="true" aria-label="写给未来的自己">' +
    '<div class="poster-modal-head"><span class="poster-modal-title">' +
    '✉️ 写给未来的自己</span>' +
    '<button type="button" class="poster-modal-close" id="flClose" ' +
    'aria-label="关闭">×</button></div>' +
    '<textarea id="flText" rows="5" maxlength="500" ' +
    'placeholder="写给以后的你——愿望、叮嘱、现在的心情都行…"></textarea>' +
    '<div class="fl-row"><label for="flWhen">什么时候送到：</label>' +
    '<select id="flWhen">' +
    '<option value="' + _isoShift(todayIso(), 30) + '">一个月后</option>' +
    (bday ? '<option value="' + bday + '">下个生日（' + bday + '）</option>' : '') +
    '<option value="' + _isoShift(todayIso(), 365) + '">一年后</option>' +
    '</select></div>' +
    '<button type="button" class="btn primary fl-send" id="flSend">' +
    '封好，寄出去</button>' +
    '<p class="fl-note">信只存在你这台设备上，小满也偷看不了。</p></div>';
  document.body.appendChild(bd);
  var close = function () { bd.remove(); };
  bd.addEventListener('click', function (e) {
    if (e.target === bd) close();
  });
  el('flClose').addEventListener('click', close);
  el('flSend').addEventListener('click', function () {
    var txt = (el('flText').value || '').trim();
    if (!txt) { showToast('信里写点什么再封吧', 'warn'); return; }
    /* R3336（审-中）：未来信正文过危机闸（同 journal/许愿瓶）。 */
    if (feCrisis(txt)) { showToast(_CRISIS_FE_REPLY, 'warn'); return; }
    /* R3329（审-P3）：剥控制字+同毫秒碰撞加随机尾+数组 50 封顶；
     * 坏 JSON 挪 corrupt 备份重建；setItem 失败说真话不再假寄。 */
    txt = txt.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g, '');
    var lt = { id: 'fl' + Date.now() + '_' +
                   Math.random().toString(36).slice(2, 7),
               text: txt.slice(0, 500),
               deliver: el('flWhen').value, created: todayIso(),
               opened: false };
    try {
      var _raw = localStorage.getItem('futureLetters');
      var lst;
      try { lst = JSON.parse(_raw || '[]'); }
      catch (ePJ2) {
        /* 坏值备份后重建——不吞掉用户已有信。 */
        try { localStorage.setItem('futureLetters:corrupt', _raw); }
        catch (eBK) {}
        lst = [];
      }
      if (!Array.isArray(lst)) lst = [];
      lst.push(lt);
      /* 50 封封顶——挤最旧的已收信；未到信永不挤。 */
      while (lst.length > 50) {
        var _oi = lst.findIndex(function (l) { return l && l.opened; });
        if (_oi < 0) break;
        lst.splice(_oi, 1);
      }
      /* R3339（审-中）：写前并集——另一 tab 同时存的信不再被整表压掉。 */
      _lsUnionWrite('futureLetters', lst,
        function (l) { return l && l.id; }, 50);
    } catch (eFS) {
      close();
      showToast('信没存上：这台设备的存信空间满了', 'error');
      return;
    }
    /* R3328（审-低）：close() 先移除节点再读 _sel 恒 null →
     * 回退到 ISO 日期。先取文案再关弹层。 */
    var _sel = el('flWhen');
    var _lbl = (_sel && _sel.options && _sel.options[_sel.selectedIndex])
      ? _sel.options[_sel.selectedIndex].textContent.split('（')[0]
      : lt.deliver;
    close();
    showToast('信寄出啦，' + _lbl + ' 那天会送回来', 'ok');
    renderCheckin(todayIso());
  });
  var t = el('flText');
  if (t) t.focus();
}

function _isoShift(dateKey, n) {
  var d = new Date(dateKey + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return d.getFullYear() + '-' + ('0' + (d.getMonth() + 1)).slice(-2) +
    '-' + ('0' + d.getDate()).slice(-2);
}
function _checkinStreak(set, dateKey) {
  var n = 0, cur = set[dateKey] ? dateKey : _isoShift(dateKey, -1);
  while (set[cur]) { n++; cur = _isoShift(cur, -1); }
  return n;
}
/* R3264（R36）：微庆祝——仪式/日记完成后飘一颗 ✨ 星星,
 * 持续 0.8s 不打扰，给多巴胺小高峰。 */
function _microCelebrate(target) {
  if (!target) return;
  try {
    var r = target.getBoundingClientRect();
    var s = document.createElement('span');
    s.textContent = '✨';
    s.className = 'micro-star';
    s.style.left = (r.left + r.width / 2 - 10) + 'px';
    s.style.top = (r.top + r.height / 2 - 10) + 'px';
    document.body.appendChild(s);
    setTimeout(function () { s.remove(); }, 900);
  } catch (eM) {}
}
/* R3264（R46）：身份反馈句——根据用户最常问功能给一句身份式
 * 总结，不做 streak，只把行为变成「正在成为」的温柔镜。 */
function _identityPhrase() {
  var _top = _usageTop();
  var _map = {
    '日签': '你正在成为会给自己留一口气的人',
    '塔罗': '你正在成为愿意向未知问一句的人',
    '六爻': '你正在成为把犹豫变成卦象的人',
    '解梦': '你正在成为会倾听夜晚的人',
    '八字合婚': '你正在成为愿意看关系底色的人',
    '八字排盘': '你正在成为读自己说明书的人',
    '黄历': '你正在成为顺着日子走的人',
    '星座': '你正在成为借星光看自己底牌的人',
    '桃花': '你正在成为敢问感情的人',
    '五行人格': '你正在成为认识自己底色的人'
  };
  return '小满的话：' + (_map[_top] || '你正在成为会照顾自己的人');
}
/* R3260（UX-STRATEGY-NEXT §五·诚实缺口）：本机使用足迹——纯
 * localStorage，零上传零画像外泄。一鱼两吃：①我们第一次知道
 * 哪个功能真有人翻（诊断面）；②「你在小满这儿第N天」本身是
 * Finch 式关系锚（在一起的日数比 streak 温柔，断了不扣）。 */
var _USAGE_LABEL = { home: '日签', bazi: '排盘', liuyao: '六爻',
  tarot: '塔罗', hehun: '合婚', qiming: '起名', taohua: '桃花',
  xingzuo: '星座', huangli: '黄历', dream: '解梦', renge: '五行人格',
  book: '书库', read: '古籍', study: '研学', moodweek: '周记',
  mantra: '咒语册' };
function _usageTrack(view) {
  try {
    if (!localStorage.getItem('usage:first'))
      localStorage.setItem('usage:first', todayIso());
    localStorage.setItem('usage:last', todayIso());
    /* R3264（R30）：7 天轻见面记录——每天留一个脚印，多次访问同一天只记 1。 */
    localStorage.setItem('usage:d:' + todayIso(), '1');
    var k = 'usage:v:' + view;
    localStorage.setItem(k, String((+localStorage.getItem(k) || 0) + 1));
  } catch (eU) {}
}
function _weekVisits() {
  try {
    var cnt = 0;
    var today = new Date(todayIso() + 'T00:00:00');
    for (var i = 0; i < localStorage.length; i++) {
      var k = localStorage.key(i);
      if (!k || k.indexOf('usage:d:') !== 0) continue;
      var d = k.slice(8);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) continue;
      var dd = new Date(d + 'T00:00:00');
      var diff = Math.round((today - dd) / 86400000);
      if (diff >= 0 && diff < 7) cnt++;
    }
    return cnt;
  } catch (eW) { return 0; }
}
function _weekRituals() {
  try {
    var cnt = 0;
    var today = new Date(todayIso() + 'T00:00:00');
    for (var i = 0; i < localStorage.length; i++) {
      var k = localStorage.key(i);
      if (!k || k.indexOf('ritual:') !== 0) continue;
      var d = k.slice(7);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) continue;
      var dd = new Date(d + 'T00:00:00');
      var diff = Math.round((today - dd) / 86400000);
      if (diff >= 0 && diff < 7) cnt++;
    }
    return cnt;
  } catch (eR) { return 0; }
}
/* R3314（R3309/R3310-P1）：mood:lv 存的是签运档 'g'/'l'，不是心情
 * 索引——三处消费方（周报主心情/聊天推荐/事实板）原都把它当 0-3
 * 读 → 恒 NaN。心情索引的真源是 mood:YYYY-MM-DD（0-3）。 */
function _latestMoodIdx() {
  /* 最近一条心情记录（今天优先，最远回看 7 天）；无记录返回 ''。 */
  try {
    for (var i = 0; i < 7; i++) {
      var d = new Date(); d.setDate(d.getDate() - i);
      var k = 'mood:' + d.getFullYear() + '-' +
        String(d.getMonth() + 1).padStart(2, '0') + '-' +
        String(d.getDate()).padStart(2, '0');
      var v = localStorage.getItem(k);
      if (v !== null && v !== '' && _MOOD_META[+v]) return v;
    }
  } catch (eM) {}
  return '';
}
function _weekMoodMain() {
  /* 近 7 天心情众数（周报海报「主心情」）；无记录返回 ''。 */
  var cnt = [0, 0, 0, 0], best = -1, bn = 0;
  try {
    for (var i = 0; i < 7; i++) {
      var d = new Date(); d.setDate(d.getDate() - i);
      var k = 'mood:' + d.getFullYear() + '-' +
        String(d.getMonth() + 1).padStart(2, '0') + '-' +
        String(d.getDate()).padStart(2, '0');
      var v = localStorage.getItem(k);
      if (v !== null && v !== '' && _MOOD_META[+v]) {
        cnt[+v]++;
        if (cnt[+v] > bn) { bn = cnt[+v]; best = +v; }
      }
    }
  } catch (eW) {}
  return best < 0 ? '' : String(best);
}

/* 心情周记（view-moodweek）：把心情罐的一周数据聚成「这周的你」小卡。
 * 数据全本机 mood:<YYYY-MM-DD>（0-3 索引，真源口径同 _weekMoodMain），
 * 零新键零上传；窗口取「最近 7 天」滚动窗，上周 = 再往前 7 天。
 * （文案池 _MOOD_WEEK_LINES 在 init() 调用点上方，与 _MOOD_META 同区——
 *   深链 ?view=moodweek 的 init→showView→_renderMoodWeek 同步链会读它，
 *   放下面 var 只提升声明不提升赋值，R3304 同款坑。） */

function _moodDayGet(dateKey) {
  /* mood:<date> → 0-3 或 null（脏值/缺记一律 null，不硬凑）。 */
  try {
    var v = localStorage.getItem('mood:' + dateKey);
    return (v !== null && v !== '' && _MOOD_META[+v]) ? +v : null;
  } catch (eMG) { return null; }
}
function _moodWeekSlice(shiftBack) {
  /* shiftBack=0 最近 7 天（含今天，由远到近）；1=再往前 7 天。 */
  var days = [];
  for (var i = 6 + shiftBack * 7; i >= shiftBack * 7; i--) {
    var dk = _isoShift(todayIso(), -i);
    days.push({ date: dk, m: _moodDayGet(dk) });
  }
  return days;
}
function _moodWeekData() {
  var days = _moodWeekSlice(0), prev = _moodWeekSlice(1);
  var cnt = [0, 0, 0, 0], recorded = 0, main = -1, mainN = 0;
  days.forEach(function (d) {
    if (d.m !== null) {
      recorded++;
      cnt[d.m]++;
      if (cnt[d.m] > mainN) { mainN = cnt[d.m]; main = d.m; }
    }
  });
  var prevN = 0, prevCnt = [0, 0, 0, 0], prevMain = -1, prevMainN = 0;
  prev.forEach(function (d) {
    if (d.m !== null) {
      prevN++;
      prevCnt[d.m]++;
      if (prevCnt[d.m] > prevMainN) { prevMainN = prevCnt[d.m]; prevMain = d.m; }
    }
  });
  /* 连续记录：今天没记就从昨天往前数（同 _checkinStreak 口径，
   * 不把「今天还没记」算成断签）。 */
  var streak = 0;
  try {
    var cur = todayIso();
    if (_moodDayGet(cur) === null) cur = _isoShift(cur, -1);
    while (_moodDayGet(cur) !== null) { streak++; cur = _isoShift(cur, -1); }
  } catch (eS) {}
  /* 判词桶：主情绪 0 累 / 1 平 / 2-3 好；记录 <2 天或没有走 none。 */
  var bucket = recorded < 2 || main < 0 ? 'none'
    : (main === 0 ? 'tired' : (main === 1 ? 'meh' : 'good'));
  /* 周序种子：同一周（同一 ISO 周窗）翻到的判词不变，跨周才换。 */
  var pool = _MOOD_WEEK_LINES[bucket];
  var wkSeed = Math.floor(Date.parse(todayIso() + 'T00:00:00') / 864e5 / 7);
  var verdict = pool[((wkSeed % pool.length) + pool.length) % pool.length];
  /* R3362（R3361 审-低）：记了 1 天时「还没攒下」与主情绪标题
   * 自相矛盾——单独成句，不与其他 none 混池。 */
  if (recorded === 1) verdict = '才记了 1 天——多记几天，周记就有模样了';
  /* 与上周同口径对比——上周零记录就不出这行，不编造。 */
  var prevText = '';
  if (prevN > 0) {
    prevText = '上周记了 ' + prevN + ' 天' +
      (prevMain >= 0 ? '，多是「' + _MOOD_META[prevMain].t + '」' : '') +
      ' · 这周 ' + recorded + ' 天' +
      (recorded > prevN ? '，越记越顺手' :
       (recorded < prevN ? '，想记就记小满不催' : ''));
  }
  var jarTotal = 0;
  try { jarTotal = Math.max(0, parseInt(localStorage.getItem('moodjar:total') || '0', 10) || 0); }
  catch (eJT) {}
  return { days: days, recorded: recorded, main: main,
    streak: streak, verdict: verdict, prevN: prevN, prevMain: prevMain,
    prevText: prevText, jarTotal: jarTotal,
    rangeStart: days[0].date, rangeEnd: days[6].date };
}
function _renderMoodWeek() {
  /* 只在周记视图在屏时渲——storage 跨 tab 同步也走这里，早退零成本。 */
  var vw = el('view-moodweek');
  if (!vw || !vw.classList.contains('active')) return;
  var body = el('moodWeekBody');
  if (!body) return;
  var w = _moodWeekData();
  var html = '<div class="mw-dots" role="list" aria-label="最近七天心情点阵">';
  w.days.forEach(function (d, i) {
    var wd = _weekdayCn(d.date);
    var md = String(+d.date.slice(5, 7)) + '/' + String(+d.date.slice(8, 10));
    html += '<div class="mw-day' + (i === 6 ? ' today' : '') +
      '" role="listitem">' +
      '<span class="mw-wd">' + esc(wd) + '</span>' +
      (d.m !== null
        ? '<span class="mw-dot" style="background:' + _MOOD_META[d.m].c +
          '" title="' + esc(_MOOD_META[d.m].t) + '"></span>' +
          '<span class="mw-e">' + _MOOD_META[d.m].e + '</span>'
        : '<span class="mw-dot empty" title="未记"></span>' +
          '<span class="mw-e">·</span>') +
      '<span class="mw-dt">' + esc(md) + '</span></div>';
  });
  html += '</div>';
  if (w.recorded > 0 && w.main >= 0) {
    html += '<div class="mw-main"><span class="mw-main-e">' +
      _MOOD_META[w.main].e + '</span><div class="mw-main-t">' +
      '<p class="mw-main-line">这周多是「' + esc(_MOOD_META[w.main].t) +
      '」</p><p class="mw-verdict">' + esc(w.verdict) + '</p></div></div>';
  } else {
    html += '<div class="mw-main"><span class="mw-main-e">🫙</span>' +
      '<div class="mw-main-t"><p class="mw-main-line">这周还没攒下心情点</p>' +
      '<p class="mw-verdict">' + esc(w.verdict) + '</p></div></div>';
  }
  html += '<div class="mw-stats">';
  html += '<span class="mw-stat">📅 这周记下 ' + w.recorded + '/7 天</span>';
  if (w.streak > 0)
    html += '<span class="mw-stat">🔥 连续记录 ' + w.streak + ' 天</span>';
  if (w.jarTotal > 0)
    html += '<span class="mw-stat">🏺 心情罐已攒 ' + w.jarTotal + ' 个色点</span>';
  if (w.prevText)
    html += '<span class="mw-stat mw-prev">📊 ' + esc(w.prevText) + '</span>';
  html += '</div>';
  html += '<p class="mw-note">只在本机生成，不发任何人；图个乐呵，不当诊断。</p>';
  body.innerHTML = html;
}
function _shareMoodWeek() {
  /* 生成周记卡——走 downloadPoster 懒链；小满插画按主情绪挑罐子
   * 同款场景图，拉不到也照出卡（右下角吉祥物贴纸兜底）。 */
  var data = _moodWeekData();
  var _artMap = { 0: 'bear-scene-cozy.jpg', 1: 'bear-scene-mid.jpg',
    2: 'bear-scene-good.jpg', 3: 'bear-scene-lantern.jpg' };
  if (data.main >= 0) {
    var _im = new Image();
    _im.onload = function () {
      data._art = _im;
      downloadPoster(data, 'moodweek');
    };
    _im.onerror = function () { downloadPoster(data, 'moodweek'); };
    _im.src = '/static/cream/' + _artMap[data.main];
  } else {
    downloadPoster(data, 'moodweek');
  }
}
function _shareWeekly() {
  /* R3264（R39）：生成小满周报分享图——聚合近 7 天数据。 */
  var _vm = _weekVisits();
  var _rm = _weekRituals();
  var _moodIdx = _weekMoodMain();
  var _moodTxt = _moodIdx !== '' ? _MOOD_META[+_moodIdx].t : '—';
  var _topV = _usageTop() || '还没怎么聊';
  /* R3314：小记篇数上周报卡——写下的事该被看见。 */
  var _jm = (function () {
    try {
      var cnt = 0, td = new Date(todayIso() + 'T00:00:00');
      for (var i = 0; i < localStorage.length; i++) {
        var k = localStorage.key(i);
        if (!k || k.indexOf('journal:') !== 0) continue;
        var d = k.slice(8);
        if (!/^\d{4}-\d{2}-\d{2}$/.test(d)) continue;
        var diff = Math.round((td - new Date(d + 'T00:00:00')) / 86400000);
        if (diff >= 0 && diff < 7) cnt++;
      }
      return cnt;
    } catch (eJ) { return 0; }
  })();
  return downloadPoster({
    visitDays: _vm,
    moodMain: _moodTxt,
    topView: _topV,
    journalCount: _jm,
    ritualCount: _rm
  }, 'weekly');
}
function _usageDays() {
  try {
    var f = localStorage.getItem('usage:first');
    if (!f) return 1;
    var d = Math.round((Date.parse(todayIso()) - Date.parse(f)) / 86400000) + 1;
    return isNaN(d) || d < 1 ? 1 : d;
  } catch (eD) { return 1; }
}
/* R3343：和TA一起打卡——双方各自把打卡日集合推到服务端，服务端
 * 只回交集。pair_id = SHA-256(规范生日串|字典序拼接)，服务端只见
 * 哈希不见生日；member 由字典序定（双方算法一致，各自算出自己的侧）。 */
var _coupleInflight = false;
function _coupleCanon(p) {
  /* 双方可复现的规范串：只含生日+性别（昵称两台设备不同，不入串）。 */
  if (!p || !p.y || !p.m || !p.d) return '';
  return [p.y, p.m, p.d, (p.h == null ? 'x' : p.h), (p.g || 'x')].join('-');
}
function _coupleKey(me, pa) {
  var a = _coupleCanon(me), b = _coupleCanon(pa);
  if (!a || !b || a === b) return '';
  return a < b ? a + '|' + b : b + '|' + a;
}
function _coupleSync(force) {
  try {
    if (_coupleInflight) return;
    var me = _meGet('me'), pa = _meGet('me:partner');
    var ckey = _coupleKey(me, pa);
    if (!ckey || !window.crypto || !crypto.subtle) return;
    var last = +(localStorage.getItem('couple:syncts') || 0);
    if (!force && Date.now() - last < 6 * 3600e3) return;
    try { localStorage.setItem('couple:syncts', String(Date.now())); }
    catch (eTS) {}
    _coupleInflight = true;
    var member = _coupleCanon(me) < _coupleCanon(pa) ? 0 : 1;
    var days = Object.keys(_checkinAll()).filter(function (k) {
      return /^\d{4}-\d{2}-\d{2}$/.test(k);
    }).sort().slice(-400);
    crypto.subtle.digest('SHA-256',
        new TextEncoder().encode('books-couple:' + ckey))
      .then(function (buf) {
        var hex = Array.prototype.map.call(new Uint8Array(buf),
          function (b) { return ('0' + b.toString(16)).slice(-2); }
        ).join('');
        /* 走 api() 同款契约：超时+静默+JSON——裸 fetch 无超时还会
         * 让契约探针把 r.ok/r.json 当字段读点误报。 */
        return api('/api/couple/checkin', {
          method: 'POST', silent: true,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pair_id: hex, member: member, days: days })
        }).catch(function () { return null; });
      })
      .then(function (j) {
        if (j && typeof j.shared_total === 'number') {
          try {
            localStorage.setItem('couple:shared', JSON.stringify({
              ck: ckey, shared: j.shared || [],
              total: j.shared_total }));
          } catch (eSV) {}
          /* 打卡卡在屏上就重渲 meta 行（焦点不在选项上时才动）。 */
          var box = document.getElementById('dailyCheckin');
          if (box && !box.contains(document.activeElement)) {
            try { renderCheckin(todayIso()); } catch (eRC) {}
          }
        }
      })
      .catch(function () {})
      .finally(function () { _coupleInflight = false; });
  } catch (eS) { _coupleInflight = false; }
}
function _yearStats(dateKey) {
  /* R3342：年度小满报告聚合——全年本机足迹，零上传零画像。
   * dateKey=「今天」（或回看锚日）；只计当年、截至锚日的足迹。 */
  var yy = String(dateKey).slice(0, 4);
  var out = { year: yy, checkinDays: 0, streakBest: 0, visitDays: 0,
    moodMain: '', topView: '', journalCount: 0, ritualCount: 0,
    fulfilledCount: 0 };
  try {
    var set = _checkinAll(), run = 0, prev = '';
    Object.keys(set).sort().forEach(function (k) {
      if (k.slice(0, 4) !== yy || k > dateKey || !set[k]) return;
      out.checkinDays++;
      run = (prev && _isoShift(prev, 1) === k) ? run + 1 : 1;
      if (run > out.streakBest) out.streakBest = run;
      prev = k;
    });
  } catch (eC) {}
  try {
    var mc = [0, 0, 0, 0], mb = -1, mn = 0;
    for (var i = 0; i < localStorage.length; i++) {
      var k = localStorage.key(i);
      if (!k) continue;
      var v = localStorage.getItem(k);
      if (k.indexOf('usage:d:' + yy + '-') === 0 && v) out.visitDays++;
      else if (k.indexOf('journal:' + yy + '-') === 0 && v)
        out.journalCount++;
      else if (k.indexOf('ritual:' + yy + '-') === 0 && v)
        out.ritualCount++;
      else if (k.indexOf('mood:' + yy + '-') === 0 &&
               _MOOD_META[+v]) {
        mc[+v]++;
        if (mc[+v] > mn) { mn = mc[+v]; mb = +v; }
      }
    }
    if (mb >= 0) out.moodMain = _MOOD_META[mb].t;
  } catch (eK) {}
  try {
    _wishEchoGet().forEach(function (w) {
      var fu = w && w.fu;
      if (fu && new Date(fu).getFullYear() === +yy)
        out.fulfilledCount++;
    });
  } catch (eF) {}
  out.topView = _usageTop();
  return out;
}
function _usageTop() {
  try {
    var best = '', bn = 1;
    Object.keys(_USAGE_LABEL).forEach(function (v) {
      if (v === 'home') return;
      var n = +localStorage.getItem('usage:v:' + v) || 0;
      if (n > bn) { bn = n; best = _USAGE_LABEL[v]; }
    });
    return best;
  } catch (eT) { return ''; }
}

/* R3260：「小满在店」状态句抽公共——chat 空态与解梦深夜档共用
 * 同一盏灯。确定性按时段切文案，零数据零随机。 */
function _xmShopLine() {
  var h = new Date().getHours();
  /* R3261（R16）：水逆期店况换口径——玄学求助最高峰的日子里，
   * 小满把店看得更细。 */
  try {
    if (window.__lastDaily && window.__lastDaily.mercury &&
        window.__lastDaily.mercury.on) {
      return '💫 水逆这些天，小满把店里的每件小事都多看了一遍';
    }
  } catch (eM) {}
  return (h >= 23 || h < 5) ? '🏮 小满还醒着，灯给你留着' :
    h < 10 ? '🍵 小满刚开门，在擦柜台' :
    h < 14 ? '📜 小满在理今天的签' :
    h < 18 ? '🫖 小满在店里翻书煮茶' :
    h < 22 ? '🕯️ 小满在灯下理签' : '🏮 小满还醒着，灯给你留着';
}

function _moodShowAnswer(m, lv) {
  var ans = el('moodAns');
  if (!ans) return;
  var band = (lv === 'g') ? 'g' : 'l';
  ans.textContent = _MOOD_REPLY[String(m) + band] || '';
  ans.hidden = false;
}

function _renderMoodRow(lv) {
  var anchor = el('dailyCheckin');
  if (!anchor || !anchor.parentNode) return;
  var row = el('moodRow');
  if (!row) {
    row = document.createElement('div');
    row.id = 'moodRow'; row.className = 'mood-row';
    anchor.parentNode.insertBefore(row, anchor.nextSibling);
  }
  var today = todayIso();
  if (lv === 'g' || lv === 'l') {
    try { localStorage.setItem('mood:lv', lv); } catch (eLV) {}
    /* R3260（周复盘）：mood:lv 只存「最新一天」档位，次日即被覆盖
     * ——心情历想做「哪天累×那天签面顺不顺」交叉回访需要逐日档位，
     * 顺手按日落一份（旧天数缺的就缺，不编造）。 */
    try { localStorage.setItem('moodlv:' + today, lv); } catch (eLV3) {}
  } else {
    try { lv = localStorage.getItem('mood:lv') || 'l'; } catch (eLV2) { lv = 'l'; }
  }
  var picked = '';
  try { picked = localStorage.getItem('mood:' + today) || ''; } catch (ePK) {}
  var html = '<span class="mood-q">今天心里怎么样？</span>';
  _MOOD_META.forEach(function (mm, i) {
    /* R3321-P2：选中态只切 .on 不进无障碍树——补 aria-pressed
     * （同 checkin-opt/rtab 既有口径）。 */
    html += '<button type="button" class="mood-b' +
      (picked === String(i) ? ' on' : '') + '" data-m="' + i +
      '" aria-pressed="' + (picked === String(i)) +
      '" aria-label="' + mm.t + '" title="' + mm.t + '">' + mm.e + '</button>';
  });
  /* R3321-P2：回执 span 挂 aria-live——「记下了」读得出。 */
  html += '<span class="mood-ans" id="moodAns" aria-live="polite"' +
    (picked === '' ? ' hidden' : '') + '></span>';
  html += '<span class="mood-cal" id="moodCal"></span>';
  row.innerHTML = html;
  /* 心情历：近 14 天由远到近色点 */
  var cal = '', has = false;
  var _wk = [0, 0, 0, 0], _wkN = 0, _wkTiredLowLv = 0;
  for (var i2 = 13; i2 >= 0; i2--) {
    var dd = new Date(); dd.setDate(dd.getDate() - i2);
    var _dk = dd.getFullYear() + '-' +
      String(dd.getMonth() + 1).padStart(2, '0') + '-' +
      String(dd.getDate()).padStart(2, '0');
    var k = 'mood:' + _dk;
    var v = null;
    try { v = localStorage.getItem(k); } catch (eV) {}
    /* R3354（审-P2）：脏值守卫——mood:<date> 塞 '9'/'x' 时
     * _MOOD_META[+v] 是 undefined，.c/.t 读属性抛 TypeError，
     * 函数中断后下方 dataset.bound 点击委托永远绑不上——心情钮
     * 渲染出来却永久死掉。词表外值按空点渲染（不写回、不崩）。 */
    var _mv = (v !== null && v !== '') ? _MOOD_META[+v] : null;
    if (_mv) {
      has = true;
      if (i2 < 7) {
        _wkN++; _wk[+v]++;
        /* R3260：心情×签面交叉——累的日子签面是不是也偏缓，
         * 用逐日存的 moodlv 对得上才算数（缺档的日子不硬凑）。 */
        if (+v === 0) {
          try {
            if (localStorage.getItem('moodlv:' + _dk) === 'l')
              _wkTiredLowLv++;
          } catch (eML) {}
        }
      }
    }
    cal += _mv
      ? '<i class="mood-dot" style="background:' + _mv.c +
        '" title="' + (dd.getMonth() + 1) + '/' + dd.getDate() +
        ' ' + _mv.t + '"></i>'
      : '<i class="mood-dot mood-dot-empty" title="' +
        (dd.getMonth() + 1) + '/' + dd.getDate() + ' 未打卡"></i>';
  }
  var mc = el('moodCal');
  if (mc) {
    var _calHtml = has
      ? '<span class="mood-cal-tag">心情历</span>' + cal : '';
    /* R3260（N3 尾巴）：心情历周复盘——近 7 天打卡 ≥2 天就给一句
     * 「小满回头看」：统计心情分布，累日子撞上缓签就点破
     * 「不怪你」。全本地数据，隐私口径不破。 */
    if (_wkN >= 2) {
      var _wtxt;
      var _tired = _wk[0], _ok = _wk[2] + _wk[3];
      if (_tired >= 2 && _wkTiredLowLv >= 1) {
        _wtxt = '这周累了 ' + _tired + ' 天，赶上签面也偏缓——' +
          '不怪你，是日子本来就硬，这周先把自己照顾好。';
      } else if (_tired >= _wkN - _tired) {
        _wtxt = '这周疲惫的日子偏多——事缓一缓不丢人，' +
          '小满建议你少排一件、多睡一点。';
      } else if (_ok >= _wkN - _ok) {
        _wtxt = '这周状态不错——好天气要趁热用，' +
          '惦记的事可以往前排一排。';
      } else {
        _wtxt = '这周心情有起有落——很正常，' +
          '哪天觉得沉就回来找小满。';
      }
      _calHtml += '<span class="mood-week">📒 ' + esc(_wtxt) + '</span>';
    }
    /* R3260（UX-PLAN-R6 R8）：心情旅程累计——Finch Journeys 口径：
     * 断掉的天数也计入累计，不讲「连续」讲「收下了多少」，
     * 不制造 guilt。攒满 5 个色点才出；里程碑日（7/14/21/30/50/
     * 100）换庆典文案，只亮那一天。 */
    var _mt = 0;
    try {
      for (var _mi = 0; _mi < localStorage.length; _mi++) {
        var _mk = localStorage.key(_mi);
        if (_mk && /^mood:\d{4}-\d{2}-\d{2}$/.test(_mk) &&
            localStorage.getItem(_mk) !== '' &&
            localStorage.getItem(_mk) !== null) _mt++;
      }
    } catch (eMT) {}
    /* R3262（R17）：统计同步心情罐子——每 7 点解锁场景图。 */
    _moodJarSync(_mt);
    if (_mt >= 5) {
      var _MILE = { 7: 1, 14: 1, 21: 1, 30: 1, 50: 1, 100: 1 };
      var _mtxt = _MILE[_mt]
        ? '第 ' + _mt + ' 个心情点进罐——你把自己照顾得比想象的好'
        : '心情罐子里攒了 ' + _mt + ' 个色点';
      _calHtml += '<span class="mood-journey">🏺 ' +
        esc(_mtxt) + '</span>';
    }
    /* 心情周记入口——打卡区小链，点进出「这周的你」周记卡视图。
     * 独占一行右对齐——塞在心情历行尾会被挤成竖条还戳出卡缘。 */
    _calHtml += '<span class="mood-week-link-wrap">' +
      '<button type="button" class="mood-week-link">' +
      '📒 看看这周的你 →</button></span>';
    mc.innerHTML = _calHtml;
  }
  if (picked !== '') _moodShowAnswer(+picked, lv);
  if (!row.dataset.bound) {
    row.dataset.bound = '1';
    row.addEventListener('click', function (ev) {
      /* 周记小链与心情按钮同挂一条委托——innerHTML 重渲不掉绑定。 */
      var _wl = ev.target.closest && ev.target.closest('.mood-week-link');
      if (_wl) { try { showView('moodweek'); } catch (eWL) {} return; }
      var b = ev.target.closest('.mood-b');
      if (!b) return;
      var m = b.dataset.m;
      try { localStorage.setItem('mood:' + todayIso(), m); } catch (eS) {}
      row.querySelectorAll('.mood-b').forEach(function (x) {
        x.classList.toggle('on', x === b);
        x.setAttribute('aria-pressed', x === b ? 'true' : 'false');
      });
      var lvNow = 'l';
      try { lvNow = localStorage.getItem('mood:lv') || 'l'; } catch (eL) {}
      _moodShowAnswer(+m, lvNow);
      _renderMoodRow(lvNow);   /* 心情历跟着刷 */
    });
  }
}

/* R3336（审-P1）：_dailyMetaItem/_dailyMetaCap 提模块级——此前定义
 * 在 loadDaily 内部，_moodJarSync/storage 监听等模块级调用点抛
 * ReferenceError 被 catch 吞（解锁当帧入口永不渲染=死代码）。
 * _metaRow 改每次现查（节点生命周期随 #dailyCard 内联结构）。 */
function _dailyMetaCap() {
  var _metaRow = document.querySelector('#dailyCard .daily-meta');
  if (!_metaRow) return;
  var _kids = Array.prototype.slice.call(_metaRow.children)
    .filter(function (n) {
      return n.classList.contains('daily-meta-item') &&
        n.id !== 'dailyMetaMore';
    });
  var _vis = _kids.filter(function (n) { return !n.hidden; });
  _kids.forEach(function (n) { n.dataset.capped = ''; });
  var _more = el('dailyMetaMore');
  if (_vis.length <= 5) {
    if (_more) _more.hidden = true;
    return;
  }
  var _open = _metaRow.dataset.expanded === '1';
  if (!_open) {
    _vis.slice(5).forEach(function (n) { n.dataset.capped = '1'; });
  }
  if (!_more) {
    _more = document.createElement('button');
    _more.id = 'dailyMetaMore'; _more.type = 'button';
    _more.className = 'daily-meta-item daily-meta-more';
    _metaRow.appendChild(_more);
    _more.addEventListener('click', function () {
      _metaRow.dataset.expanded =
        _metaRow.dataset.expanded === '1' ? '' : '1';
      _dailyMetaCap();
    });
  }
  _more.hidden = false;
  _more.textContent = _open ? '收起' : '+' + (_vis.length - 5) + ' 条';
  _more.setAttribute('aria-expanded', _open ? 'true' : 'false');
}
function _dailyMetaItem(id, html) {
  var _metaRow = document.querySelector('#dailyCard .daily-meta');
  var n = el(id);
  if (!n) {
    n = document.createElement('div');
    n.id = id;
    /* R3248b：personal 粒是多行文本块——挪出胶囊行自立一块（不进 +N）。 */
    n.className = id === 'dailyPersonal' ? 'daily-mine-block'
                                         : 'daily-meta-item';
    if (id === 'dailyPersonal' && _metaRow && _metaRow.parentNode) {
      _metaRow.parentNode.insertBefore(n, _metaRow.nextSibling);
    } else if (_metaRow) {
      _metaRow.appendChild(n);
    }
  }
  if (html) { n.innerHTML = html; n.hidden = false; }  // esc-reviewed
  else { n.hidden = true; n.innerHTML = ''; }
  _dailyMetaCap();
}

/* R3262（R17）：心情罐子同步——统计 mood:<date> 总数，每满 7 个
 * 解锁一张场景图；首次解锁时 toast 告知，断签不扣回已解锁数。 */
function _moodJarSync(total) {
  try {
    /* R3315：场景扩到 6 张，封顶跟着表走（scene 数即上限）。 */
    var oldU = Math.max(0, parseInt(localStorage.getItem('moodjar:unlocked') || '0', 10) || 0);
    /* R3336（审-中）：unlocked 无条件覆写会被 GC 收键/导入更少键
     * 反向回落——已解锁图静默消失，与「断签不扣回」注释矛盾。
     * 取 max（旧值，算值） 单调递增。 */
    var unlocked = Math.max(oldU, Math.min(_MOOD_JAR_SCENES.length,
                            Math.floor((total || 0) / 7)));
    var oldT = Math.max(0, parseInt(localStorage.getItem('moodjar:total') || '0', 10) || 0);
    localStorage.setItem('moodjar:total', String(total || 0));
    localStorage.setItem('moodjar:unlocked', String(unlocked));
    if (unlocked > oldU && total > oldT) {
      showToast('🏺 心情罐子里收了 ' + (unlocked * 7) +
        ' 个色点，小满送你第 ' + unlocked + ' 张场景图', 'info');
      /* R3322-P2：解锁当帧刷新罐入口——meta 行在本函数上游渲染，
       * toast 说送图而入口还空着是自相矛盾。 */
      try { _dailyMetaItem('dailyMoodJar', _moodJarHtml()); } catch (eM5) {}
    }
  } catch (eMJ) {}
}
function _moodJarHtml() {
  try {
    var unlocked = Math.max(0, parseInt(localStorage.getItem('moodjar:unlocked') || '0', 10) || 0);
    /* R3345（审-低）：total 改现场数 mood: 键——meta 行渲染早于
     * 本次 _moodJarSync 写值时不再滞后一帧（跨 tab/导入后同步）。 */
    var _liveTot = 0;
    for (var _li = 0; _li < localStorage.length; _li++) {
      var _lk = localStorage.key(_li);
      if (_lk && /^mood:\d{4}-\d{2}-\d{2}$/.test(_lk) &&
          localStorage.getItem(_lk)) _liveTot++;
    }
    if (unlocked <= 0) {
      var _tot = _liveTot;
      if (_tot <= 0) return '';
      return '<div class="mood-jar-teaser">🏺 心情罐子：再攒 ' +
        (7 - _tot % 7) + ' 个色点，换第一张场景图（已有 ' + _tot +
        '）</div>';
    }
    var html = '<details class="mood-jar-fold"><summary>' +
      '🏺 心情罐子 · 已解锁 <strong>' + unlocked + '</strong>/' +
      _MOOD_JAR_SCENES.length + ' 张' +
      '</summary><div class="mood-jar-grid">';
    for (var i = 0; i < unlocked && i < _MOOD_JAR_SCENES.length; i++) {
      var sc = _MOOD_JAR_SCENES[i];
      html += '<div class="mood-jar-item"><img src="' + sc.url +
        '" alt="" loading="lazy" onerror="this.parentNode.remove()"><span>' +
        esc(sc.k) + '</span></div>';
    }
    html += '</div><p class="mood-jar-care">小满替你收着</p></details>';
    return html;
  } catch (eMJH) { return ''; }
}
function renderCheckin(dateKey) {
  const box = document.getElementById('dailyCheckin');
  if (!box) return;
  /* R228h：window.localStorage 属性本身在隐私模式下读就抛——整个 getter 进 try */
  let saved = null;
  try { saved = dateKey ? window.localStorage.getItem('checkin:' + dateKey) : null; }
  catch (e0) { saved = null; }
  var _ckAll = _checkinAll();
  var _streak = dateKey ? _checkinStreak(_ckAll, dateKey) : 0;
  /* 昨天选了什么（今天还没打时才提示，打了就没必要复读） */
  var _yKey = dateKey ? _isoShift(dateKey, -1) : '';
  var _yPick = _yKey ? _ckAll[_yKey] : null;
  var _dots = '';
  for (var _di = -6; _di <= 0; _di++) {
    var _dk = dateKey ? _isoShift(dateKey, _di) : '';
    _dots += '<i class="' + (_ckAll[_dk] ? 'on' : '') +
      (_di === 0 ? ' today' : '') + '" title="' + esc(_dk) +
      (_ckAll[_dk] ? ' ' + esc(_ckAll[_dk]) : '') + '"></i>';
  }
  /* R233n：每日 4 签从 8 签池确定性轮换（salt=日期） */
  var _todays = _dayPickN(CHECKIN_OPT_POOL, 4, 'ck|' + String(dateKey || ''));
  if (saved && _todays.indexOf(saved) < 0) _todays.unshift(saved);
  /* R88-1c：生日当天塞一张限定签——今天打卡收的是「生日签」。 */
  if (_isMyBirthday() && _todays.indexOf('生日签') < 0) {
    _todays.unshift('生日签');
  }
  /* R3251（用户实测「四张牌顺序每次打开应该都不一样」）：
   * 未打卡的扣牌态按 Math.random 现场洗牌——签池今日是哪些
   * 仍由 _dayPickN 定死（确定性），但四张扣牌的摆放顺序每次
   * 开页都不同，「抽」的随机感成立。已打卡亮面态不打乱
   * （picked 位置漂移会让回访者找不到自己那张）。 */
  if (!saved) {
    for (var _sf = _todays.length - 1; _sf > 0; _sf--) {
      var _sj = Math.floor(Math.random() * (_sf + 1));
      var _st = _todays[_sf]; _todays[_sf] = _todays[_sj]; _todays[_sj] = _st;
    }
  }
  /* R2350f（R102-P2-8 消费侧）：开了「明天提醒我」且今天还没打——
   * 每天首渲提醒一次（标记当天已提醒，防同天复读）。 */
  if (!saved) {
    try {
      if (localStorage.getItem('remind:1') === '1' &&
          localStorage.getItem('remind:shown') !== dateKey) {
        localStorage.setItem('remind:shown', dateKey);
        setTimeout(function () {
          showToast('🔔 说好今天喊你的，抽一签吧', 'info');
        }, 1200);
      }
    } catch (eRM) {}
  }
  /* R3250c（用户实测「四签可以翻过去做个抽牌提示」）：
   * 未打卡时四签全扣成牌背——小红书玄学号的「默念问题选牌」
   * 互动实测是流量密码；扣着抽比摊开选多一层仪式感。
   * 抽到即写 buff（感情/做事/钱袋之一 +1~3，同日同签同值）。
   * 已打卡则照旧亮面，picked 上加翻回动画。 */
  var _just = null;
  try { _just = window.__ckJustPicked || null; } catch (eJ) {}
  var _buffNow = null;
  try {
    var _bfj = JSON.parse(
      localStorage.getItem('checkinBuff:' + (dateKey || '')) || 'null');
    var _bfn2 = parseInt(_bfj && _bfj.n, 10) || 0;
    if (_bfj && _bfj.d && _bfn2 >= 1 && _bfn2 <= 9) {
      _buffNow = {d: _bfj.d, n: _bfn2};
    }
  } catch (eBf) {}
  var _buffIc = _buffNow
    ? (_buffNow.d === '感情' ? '💗' : _buffNow.d === '做事' ? '💼' : '💰')
    : '';
  const opts = _todays.map(function (o) {
    /* R2349t（R87-P1-1）：saved 是 localStorage 原始串——词表外脏值
     * 会被 unshift 进来直拼 HTML（属性逃逸即存储型 XSS）。两处全 esc。 */
    /* R3249c：按钮显示「人话名+用途副标」，data-opt 仍存原键 */
    var _lb = CHECKIN_LABEL[o];
    var _isP = (saved === o);
    /* R3251（用户实测「翻牌后就不可以再更换了」）：抽中即锁——
     * 其余签 disabled 不再可点（也不再走 handler 覆写 saved），
     * 视觉上压暗标明「今天的缘分已定格」。 */
    var _lock = (saved && !_isP);
    /* R3252：翻过来的签带小插画——亮面态每张签顶一张签面熊，
     * 扣牌态不渲染（背面 🐻 已是悬念）。 */
    var _art = (saved && CHECKIN_ART[o])
      ? '<img class="ck-art" src="/static/cream/' + CHECKIN_ART[o] +
        '.jpg" alt="" loading="lazy" decoding="async" ' +
        'onerror="this.remove()">'
      : '';
    return '<button type="button" class="checkin-opt' +
      (_isP ? ' picked' : '') +
      (!saved ? ' ck-back' : '') +
      (_lock ? ' ck-lock' : '') +
      (_just === o ? ' just-picked' : '') + '" data-opt="' + esc(o) + '" ' +
      (_lock ? 'disabled ' : '') +
      'aria-pressed="' + _isP + '"' +
      (_lb ? ' aria-label="' + (!saved ? '抽一张签——' : '') +
        esc(_lb[0]) + '，' + esc(_lb[1]) + '"' : '') +
      '>' + _art + (_lb
        ? '<b>' + esc(_lb[0]) + '</b><i>' + esc(_lb[1]) + '</i>'
        : esc(o)) +
      (_isP && _buffNow
        ? '<i class="ck-buff">签力 +' + String(_buffNow.n) + ' ' +
          _buffIc + '</i>'
        : '') + '</button>';
  }).join('');
  /* R229z续23（R10-#17）：选项组补 role=group + 问题文本锚点，
   * 反馈区 aria-live——选完有朗读回执。 */
  var _meta = '';
  if (_streak >= 2) {
    _meta += '已连续 ' + _streak + ' 天打卡';
    if (_streak === 3) _meta += ' · 小满贯开头啦';
    else if (_streak === 7) _meta += ' · 整一周，仪式感拿捏';
    else if (_streak >= 100) _meta += ' · 百日传说';
    else if (_streak >= 60) _meta += ' · 双满月';
    else if (_streak >= 30) _meta += ' · 满月级选手';
    else if (_streak >= 14) _meta += ' · 半月不断';
    /* R39-P2-4：里程碑之间补倒计时——4→7、8→14 的空白带不再无目标。
     * R2350c（R97-P1-2）：原守卫「meta 含档位词就跳过」是错的——档位词
     * 是 ≥ 区间标（连签 14→30 天天挂「半月不断」），结果三段最长里程
     * 间隔（14→30/30→60/60→100）反而断档。改只跳过里程碑当天。 */
    if (_streak < 100 &&
        [3, 7, 14, 30, 60].indexOf(_streak) < 0) {
      var _mile = [[3, '小满贯'], [7, '整一周'], [14, '半月不断'],
                   [30, '满月级选手'], [60, '双满月'], [100, '百日传说']];
      for (var _mi = 0; _mi < _mile.length; _mi++) {
        if (_streak < _mile[_mi][0]) {
          _meta += ' · 距「' + _mile[_mi][1] + '」还差 ' + (_mile[_mi][0] - _streak) + ' 天';
          break;
        }
      }
    }
  } else if (!saved && _yPick) {
    _meta += '昨天你选了「' + esc(_yPick) + '」，今天换换？';
  } else if (!saved && Object.keys(_ckAll).length) {
    /* R39-P0-3：断签温柔召回——历史打过卡但昨天空 → 接住而不是沉默。
     * R2349t（R88-11）：断签报账——断 20 天和断 3 天不该同一句话，
     * 把「攒过的档」点名，看见感 > 客套。 */
    var _bk = 0;
    try {
      var _ks = Object.keys(_ckAll).filter(function (k) {
        return /^\d{4}-\d{2}-\d{2}$/.test(k) && k < dateKey;
      }).sort();
      if (_ks.length) {
        _bk = _checkinStreak(_ckAll, _isoShift(_ks[_ks.length - 1], 1));
      }
    } catch (eBk) {}
    /* R3314（R3309-P2）：≥7 天档原文案「不数 streak」——streak 是
     * 英文黑话且与星数行「已连续 N 天」自述矛盾；断过的档也照
     * 3-6 天档一样报数（攒过的档点名，看见感>客套）。 */
    _meta += _bk >= 7 ?
      ('之前攒了 ' + _bk + ' 天，都替你收着，今天回来继续 🌱')
      : _bk >= 3 ?
      (_bk + ' 天先存个档，今天重新开张也算数 🌱')
      : '歇了几天也没关系，今天重新开张就算数 🌱';
  }
  /* R3249j（UX-AUDIT 留存闭环）：打卡攒星——每打一天攒一颗小星星，
   * 攒满 7 颗解锁一句「小满的话」。签册/点阵/连签此前是互不通气
   * 的零件，这一行把「攒」显形出来，回访有目标感。 */
  var _stars = 0;
  try {
    Object.keys(_ckAll).forEach(function (k) { if (_ckAll[k]) _stars++; });
  } catch (eS) {}
  if (_stars > 0) {
    var _cycle = _stars % 7;
    if (_cycle === 0) {
      _meta += ' ⭐ 攒了 ' + _stars + ' 颗小星星｜' +
        esc(_dayPick(['小满的话：你来这么多天，我都记住啦',
                      '小满的话：坚持拆开每一天的人，运气不会太差',
                      '小满的话：你在认真过日子，星星都看得见'],
                     'xmword'));
    } else {
      _meta += ' ⭐ 已攒 ' + _stars + ' 颗 · 再攒 ' + (7 - _cycle) +
               ' 颗有小满的话';
    }
  }
  /* R3343：和TA合拍——CP 档齐且服务端回过交集时挂一行。
   * couple:shared={ck, shared, total} 由 _coupleSync 写入；ck 变了
   * （换过伴侣档）旧交集不顶包。 */
  try {
    var _csp = JSON.parse(localStorage.getItem('couple:shared') || 'null');
    if (_csp && _csp.total > 0 &&
        _csp.ck === _coupleKey(_meGet('me'), _meGet('me:partner'))) {
      var _cSet = {};
      (_csp.shared || []).forEach(function (d) { _cSet[d] = 1; });
      var _cStreak = _checkinStreak(_cSet, dateKey);
      _meta += ' 💞 和TA合拍 ' + _csp.total + ' 天' +
        (_cStreak >= 2 ? ' · 连击 ' + _cStreak : '');
    }
  } catch (eCS) {}
  /* R3264（R48）：周目标可视化——可选 3/5/7 天，显示还差/已达。 */
  var _weekGoal = 5;
  try { _weekGoal = parseInt(localStorage.getItem('checkin:goal') || '5', 10); } catch (eG) {}
  if (isNaN(_weekGoal) || [3, 5, 7].indexOf(_weekGoal) < 0) _weekGoal = 5;
  var _weekHits = 0;
  try {
    for (var _wi = -6; _wi <= 0; _wi++) {
      var _wk = _isoShift(dateKey, _wi);
      if (_ckAll[_wk]) _weekHits++;
    }
  } catch (eW) {}
  var _goalGap = _weekGoal - _weekHits;
  var _goalTxt = _goalGap <= 0
    ? '本周目标 ' + _weekGoal + ' 天已达成，给自己放个假 🌱'
    : '本周目标 ' + _weekGoal + ' 天 · 已完成 ' + _weekHits + ' · 还差 ' + _goalGap;
  var _goalHtml = '<div class="ck-goal" role="group" aria-label="本周打卡目标">' +
    '<span>目标</span>' +
    [3, 5, 7].map(function (g) {
      /* R3321-P2：周目标选中态补 aria-pressed。 */
      return '<button type="button" class="ck-goal-opt' +
        (g === _weekGoal ? ' active' : '') + '" data-g="' + g +
        '" aria-pressed="' + (g === _weekGoal) + '">' + g + '天</button>';
    }).join('') +
    '<span class="ck-goal-txt">' + esc(_goalTxt) + '</span></div>';
  /* R3317-E：每周运势信——本周首个到访日给「上周小记」卡。
   * 数据全在本地：上周 7 天的打卡天数 + 心情主色 + 一句本周祝词。
   * 每周一封信完即收（wlKey 落档不再弹），零打扰零请求。 */
  var _wlHtml = '';
  try {
    var _dow = (new Date(dateKey + 'T00:00:00').getDay() + 6) % 7;
    var _mon = _isoShift(dateKey, -_dow);          // 本周一
    var _wlKey = 'weeklyLetter:' + _mon;
    if (!localStorage.getItem(_wlKey)) {
      var _lckN = 0, _lmdN = 0, _lmdCnt = {};
      for (var _lw = 7; _lw >= 1; _lw--) {
        var _ld = _isoShift(_mon, -_lw);           // 上周一~日
        if (_ckAll[_ld]) _lckN++;
        var _lmv = localStorage.getItem('mood:' + _ld);
        if (_lmv !== null && _lmv !== '') {
          _lmdN++; _lmdCnt[_lmv] = (_lmdCnt[_lmv] || 0) + 1;
        }
      }
      if (_lckN >= 2 || _lmdN >= 3) {
        var _dom = -1, _domN = 0;
        Object.keys(_lmdCnt).forEach(function (k) {
          if (_lmdCnt[k] > _domN) { _domN = _lmdCnt[k]; _dom = +k; }
        });
        var _moodTxt = (_dom >= 0 && _MOOD_META[_dom])
          ? '，心情多是「' + _MOOD_META[_dom].t + '」' : '';
        var _wlLine = _dom === 0
          ? '上周辛苦啦，这周先把觉补够，好运会慢慢回温的。'
          : _dom === 3
          ? '状态这么好，这周可以大胆一点，想做的事往前推。'
          : _lckN >= 5
          ? '上周你几乎天天都来，我都记着呢——这周继续保持呀。'
          : _dayPick(['新的一周，日子翻开新的一页，慢慢来就好。',
                      '这周不求大起大落，平安顺遂就是赢。',
                      '新周开张，先把小确幸收进口袋。'], 'wl|' + _mon);
        _wlHtml = '<div class="weekly-letter" id="weeklyLetter">' +
          '<div class="wl-head">💌 小满的上周小记' +
          /* R3379：周记信可晒——真实记录拼的小记上分享海报。 */
          '<button type="button" class="wl-share" id="wlShare" ' +
          'title="把这封小记晒成图">📸</button>' +
          '<button type="button" class="wl-x" id="wlDismiss" ' +
          'aria-label="收下了，不再显示">×</button></div>' +
          '<div class="wl-body">' +
          /* R3318（审-P3-4）：0 打卡纯心情路径——「打卡 0 天」开头
           * 语气硬，改述成「来记下心情」。 */
          (_lckN === 0
            ? '上周你来记下 ' + _lmdN + ' 天心情'
            : '上周你打卡 ' + _lckN + ' 天') +
          esc(_moodTxt) + '。' + esc(_wlLine) + '</div></div>';
      }
    }
  } catch (eWL) {}
  /* R3319-F：月度小满信——月初首访日给「上月小信」卡，
   * 与周信同构：本地聚合上月打卡/心情/小记/最长连签，
   * 每月一封完即收（mlKey 落档不再弹）。 */
  var _mlHtml = '';
  try {
    var _t0m = new Date(dateKey + 'T00:00:00');
    var _pm = new Date(_t0m.getFullYear(), _t0m.getMonth() - 1, 1);
    var _pmKey = _pm.getFullYear() + '-' +
      String(_pm.getMonth() + 1).padStart(2, '0');
    var _mlKey = 'monthlyLetter:' + _pmKey;
    if (!localStorage.getItem(_mlKey)) {
      var _pmDays = new Date(_pm.getFullYear(), _pm.getMonth() + 1, 0).getDate();
      var _mCk = 0, _mMd = 0, _mJ = 0, _mBest = 0, _cur = 0;
      var _mMdCnt = {};
      for (var _md = 1; _md <= _pmDays; _md++) {
        var _mdk = _pmKey + '-' + String(_md).padStart(2, '0');
        if (_ckAll[_mdk]) { _mCk++; _cur++; if (_cur > _mBest) _mBest = _cur; }
        else { _cur = 0; }
        var _mmv = localStorage.getItem('mood:' + _mdk);
        if (_mmv !== null && _mmv !== '') {
          _mMd++; _mMdCnt[_mmv] = (_mMdCnt[_mmv] || 0) + 1;
        }
        if (localStorage.getItem('journal:' + _mdk)) _mJ++;
      }
      /* 上门槛：上月有点痕迹才值得写信（不打卡纯浏览不下信）。 */
      if (_mCk >= 3 || _mMd >= 4 || _mJ >= 2) {
        var _mDom = -1, _mDomN = 0;
        Object.keys(_mMdCnt).forEach(function (k) {
          if (_mMdCnt[k] > _mDomN) { _mDomN = _mMdCnt[k]; _mDom = +k; }
        });
        var _mParts = [];
        if (_mCk) _mParts.push('打卡 ' + _mCk + ' 天');
        if (_mMd) {
          _mParts.push('记下 ' + _mMd + ' 天心情' +
            (_mDom >= 0 && _MOOD_META[_mDom]
              ? '（多是「' + _MOOD_META[_mDom].t + '」）' : ''));
        }
        if (_mJ) _mParts.push('写了 ' + _mJ + ' 篇小记');
        if (_mBest >= 3) _mParts.push('最长连签 ' + _mBest + ' 天');
        var _MSEASON = [
          '一月开头，愿这一年待你温柔。',
          '二月有立春也有花灯，好事成双。',
          '三月花开，好运跟着一起发芽。',
          '四月人间，适合把心愿再养一养。',
          '五月风暖，想做的事趁现在。',
          '六月过半，上半年的努力都算数。',
          '七月流火，记得给自己留块阴凉。',
          '八月有星河，也有属于你的好消息。',
          '九月开学季，新节奏慢慢来。',
          '十月金秋，愿你收获比付出多一点。',
          '十一月转凉，记得添衣也记得添喜。',
          '十二月收官，这一年的你都辛苦了。'];
        _mlHtml = '<div class="weekly-letter ml-letter" id="monthlyLetter">' +
          '<div class="wl-head">📮 ' + (_pm.getMonth() + 1) +
          ' 月的小满信' +
          '<button type="button" class="wl-x" id="mlDismiss" ' +
          'aria-label="收下了，不再显示">×</button></div>' +
          '<div class="wl-body">上个月你' +
          esc(_mParts.join('、')) + '，我都替你记着。' +
          esc(_MSEASON[_pm.getMonth()]) + '</div></div>';
      }
    }
  } catch (eML) {}
  /* R3325-D：写给未来的信——本地留存（futureLetters JSON 数组，
   * 清盘不丢）；到日信卡浮出，与周/月信同版式。 */
  var _flHtml = '';
  /* R3329（审-P2）：坏 JSON 让整段 catch——写信入口是唯一入口
   * 必须在 try 外保底渲染。 */
  var _flEntryHtml = '<div class="fl-entry">' +
    '<button type="button" class="fl-write" id="flWrite">✉️ 写给未来的自己</button>' +
    '<span class="fl-pend" id="flPend"></span></div>';
  try {
    var _flList = JSON.parse(localStorage.getItem('futureLetters') || '[]');
    if (!Array.isArray(_flList)) _flList = [];
    _flList.forEach(function (lt) {
      /* R3354（审-P2）：数组混入原始值（'junk'/42）时严格模式下
       * lt._due= 赋值抛 TypeError——forEach 中断、整段被外层
       * catch 吞，合法到期信（包括排在垃圾前的）全部不渲染。 */
      if (!lt || typeof lt !== 'object') return;
      /* R3329（审-P2）：脏 deliver（2026-13-01）串比较恒 false →
       * 信永远 pending。非真日期视作今日送达浮出。 */
      if (!lt.opened) {
        var _dv = String(lt.deliver || '');
        var _real = /^\d{4}-\d{2}-\d{2}$/.test(_dv) &&
          !isNaN(new Date(_dv + 'T00:00:00').getTime());
        if (!_real || _dv <= dateKey) lt._due = true;
      }
    });
    var _flDue = _flList.filter(function (lt) { return lt._due; });
    var _flPend = _flList.filter(function (lt) {
      return lt && !lt.opened && !lt._due; });
    var _flDone = _flList.filter(function (lt) { return lt && lt.opened; });
    _flDue.forEach(function (lt) {
      /* R3327-P1-7：meta 量化时间跨度（写于 N 天前），
       * 比 ISO 日期有泪点。 */
      var _days = 0;
      try {
        _days = Math.max(0, Math.round(
          (new Date(dateKey + 'T00:00:00') -
           new Date(String(lt.created || dateKey) + 'T00:00:00')) /
          86400000));
      } catch (eFD) {}
      var _span = _days >= 365
        ? '写于 ' + Math.floor(_days / 365) + ' 年前'
        : _days >= 30
        ? '写于 ' + Math.floor(_days / 30) + ' 个月前'
        : _days >= 1 ? '写于 ' + _days + ' 天前' : '今天写下';
      _flHtml += '<div class="weekly-letter fl-letter" data-flid="' +
        esc(lt.id) + '"><div class="wl-head">✉️ 过去的你写来的信' +
        '<button type="button" class="wl-x fl-open" data-flid="' +
        esc(lt.id) + '" aria-label="收下了">×</button></div>' +
        '<div class="wl-body">' + esc(lt.text) +
        '<div class="fl-meta">' + esc(_span) +
        ' · 今天送达</div></div></div>';
    });
    /* R3354（审-低）：futureLetters:corrupt 救援键此前只写不读——
     * 坏 JSON 就地备份后没有任何取回口。写信入口旁给一条找回链。 */
    try {
      var _flRaw0 = localStorage.getItem('futureLetters:corrupt');
      if (_flRaw0) {
        _flEntryHtml = _flEntryHtml.replace('</span></div>',
          '<button type="button" class="fl-recover" id="flRecover">' +
          '💌 有封没写完的信，点这找回</button></span></div>');
      }
    } catch (eFR) {}
    /* R3329：pend 徽标填进 try 外的保底入口骨架。 */
    if (_flPend.length) {
      _flEntryHtml = _flEntryHtml.replace('</span></div>',
        _flPend.length + ' 封在路上的信 · 最近 ' +
        esc(_flPend.map(function (l) { return l.deliver; })
          .sort()[0] || '') + ' 到</span></div>');
    }
    /* R3327-P1-7b：已收的信不再即焚——收下后收进「已收的信」折叠，
     * 可重读。 */
    if (_flDone.length) {
      _flHtml += '<details class="fl-done"><summary>📬 已收的信（' +
        _flDone.length + '）</summary>';
      _flDone.slice().reverse().forEach(function (lt) {
        _flHtml += '<div class="fl-done-item">' +
          '<div class="fl-done-meta">' + esc(lt.created || '') +
          ' 写 · ' + esc(lt.deliver || '') + ' 到</div>' +
          '<div class="fl-done-text">' + esc(lt.text) + '</div></div>';
      });
      _flHtml += '</details>';
    }
  } catch (eFL) {}
  box.innerHTML = _wlHtml + _mlHtml + _flHtml + _flEntryHtml +
    '<div class="checkin-q" id="checkinQ">' +
    /* R2349g（R68-P1-1）：打卡问句 3→6。 */
    esc(_dayPick(['挑一个今天想要的：', '想求点什么：',
                  /* R3249c（A3）：问句从「哪张签」改成「想要什么」——
                   * 选项已是「攒好运/求顺利」心愿语义，问句对齐。 */
                  '许个愿，挑张签带走：', '今天想求点什么：',
                  /* R2500（R142-P2-3）：四签全亮是「选」不是「抽」——
                   * 文案对齐机制，新客不再误以为点了是随机。 */
                  '挑一个陪你过今天：', '今天的幸运签是哪一个：'], 'ckq')) + ' ' +
    '<span class="checkin-dots" aria-hidden="true">' + _dots + '</span>' +
    (_meta ? '<span class="checkin-meta">' + _meta + '</span>' : '') + '</div>' +
    /* R3250c：扣牌态给一句操作提示——「抽一张」是互动钩子，
     * 亮面态（打过卡）不需要。 */
    (!saved ? '<div class="ck-hint">🎴 牌背都扣着呢——心里想着' +
              '今天想要的事，抽一张</div>' : '') +
    '<div class="checkin-opts" role="group" aria-labelledby="checkinQ">' + opts + '</div>' +
    _goalHtml +
    /* R3314（R3309-P1）：判词句原排在 5 枚分享钮之后——390×844 视口
     * 实测 y=879 在折线下，最暖的一句定制文案打完卡看不到。提到
     * 分享钮之前。 */
    /* R3317-E：信卡收下钮——本周不再弹。 */
    '<div class="checkin-fx" id="checkinFx" aria-live="polite">' +
    (saved ? pickCheckinFeedback(saved, dateKey) : '') + '</div>' +
    /* R231d（R37-F15）：连签 ≥3 天给「晒连签」出口——里程碑文案不外溢
     * 就没拉新价值。 */
    /* R233n（R47-Top5-2）：打卡签首日即可晒——原来要等连签 ≥3 天，
     * 第 1-2 天（拉新最猛的窗口）没有分享出口。 */
    ((_streak >= 3 || saved) ? '<button type="button" class="checkin-share" id="checkinShare" ' +
      'title="生成分享图">' + (saved ? '📸 晒这张签' : '📸 晒连签') +
      '</button>' : '') +
    /* R233q（R47-P2 续）：周报海报——近 7 天打卡 ≥2 天才显示 */
    (function () {
      var _w = 0;
      for (var _i = -6; _i <= 0; _i++) {
        if (_ckAll[_isoShift(dateKey, _i)]) _w++;
      }
      return (_w >= 2 ?
        '<button type="button" class="checkin-share" id="checkinWeek" ' +
        'title="生成本周签运图">📅 本周签运</button>' : '');
    })() +
    /* R2352（R107-月报）：本月打卡 ≥5 天给「本月签运」海报——
     * 周报的下一档收集钩，月底晒感最强。 */
    (function () {
      var _mm = dateKey.slice(0, 7), _m = 0;
      Object.keys(_ckAll).forEach(function (k) {
        /* R2354（R112-P3-9）：门控按 key 计数、海报按 truthy 值
         * 计数——空串/脏值键能把门控抬到 5 但海报报 0 天。
         * 两侧同按 truthy 值口径。 */
        if (k.slice(0, 7) === _mm && k <= dateKey && _ckAll[k]) _m++;
      });
      /* R3304（审-P3）：月初 1-4 号按钮整月消失——零反馈死区。
       * 未满 5 天给「还差 N 天」占位提示（按钮禁用态）。 */
      return (_m >= 5 ?
        '<button type="button" class="checkin-share" id="checkinMonth" ' +
        'title="生成本月签运图">🗓️ 本月签运</button>' :
        '<button type="button" class="checkin-share" disabled ' +
        'title="本月再打卡 ' + (5 - _m) + ' 天就能出月报">' +
        '🗓️ 月报还差 ' + (5 - _m) + ' 天</button>');
    })() +
    /* R3342：年度小满报告——Wrapped 式回顾。全年打卡 ≥8 天出报；
     * 12/15–1/31 跨年档降到 ≥3 天（晒感最强窗）。未满给占位提示。 */
    (function () {
      var _yy = dateKey.slice(0, 4), _yn = 0;
      Object.keys(_ckAll).forEach(function (k) {
        if (k.slice(0, 4) === _yy && k <= dateKey && _ckAll[k]) _yn++;
      });
      var _md = +dateKey.slice(5, 7) * 100 + +dateKey.slice(8, 10);
      var _min = (_md >= 1215 || _md <= 131) ? 3 : 8;
      return (_yn >= _min ?
        '<button type="button" class="checkin-share" id="checkinYear" ' +
        'title="生成年度小满报告">📖 小满年报</button>' :
        '<button type="button" class="checkin-share" disabled ' +
        'title="今年再打卡 ' + (_min - _yn) + ' 天就能出年报">' +
        '📖 年报还差 ' + (_min - _yn) + ' 天</button>');
    })() +
    /* R2350f（R102-P2-8/P2-13）：两枚留存/拉新小动作——「明天提醒我」
     * 走本地 Notification（无推送基建，次日开屏 toast 口径如实说清），
     * 「安利铺子」产出 文案+链 一键复制给闺蜜。 */
    '<button type="button" class="checkin-share" id="checkinRemind" ' +
      'title="明天回来时提醒你抽新签">🔔 ' +
      ((function () {
        try { return localStorage.getItem('remind:1') === '1'; }
        catch (e) { return false; }
      })() ? '明天会来喊你' : '明天提醒我') + '</button>' +
    '<button type="button" class="checkin-share" id="shopShare" ' +
      'title="把这铺子发给闺蜜">📮 安利铺子</button>' +
    /* R233p（R47-P2）：签册——存量 checkin:* 渲成可回看的迷你签墙
     * （details 懒渲染，点开才算 DOM；集齐感是小红书留存钩子）。
     * R2350f（R102-P2-9）：零打卡用户也渲染——集齐线首日就得亮相，
     * 否则新客不知道有这条收集线在等她。 */
    '<details class="ck-album"><summary>📒 ' +
      (Object.keys(_ckAll).length
        ? '小满替你收着的签册（' + Object.keys(_ckAll).length + '）'
        : '小满的签册：打一次卡开第一张') +
      '</summary>' +
      '<div class="ck-album-body" id="checkinAlbum"></div></details>' +
      /* R2350j（R107-Top5-4）：许愿瓶 lite——写个愿望丢进去，
       * localStorage 封存，几天后回来认领。和签册同构的 details
       * 懒渲染卡，零后端依赖。 */
      '<details class="ck-album ck-wish"><summary>🫙 许愿瓶' +
      _wishSummary() + '</summary>' +
      '<div class="ck-album-body" id="wishBottleBody"></div></details>' +
      /* R3335：烦恼粉碎机——把压着的烦心事写下来当场碎掉。
       * 仪式意义=不留档：原文永不落盘，只记当天件数。 */
      '<details class="ck-album ck-shred"><summary>🗑️ 烦恼粉碎机' +
      '<span id="shredSum"></span></summary>' +
      '<div class="ck-album-body" id="shredBody"></div></details>';
  /* R3379：周记信晒图——取卡片里真实渲染的小记文本进海报。 */
  var _wls = box.querySelector('#wlShare');
  if (_wls && !_wls.dataset.bound) {
    _wls.dataset.bound = '1';
    _wls.addEventListener('click', function () {
      var _wlBody = box.querySelector('#weeklyLetter .wl-body');
      downloadPoster({
        _wlBody: _wlBody ? _wlBody.textContent : '',
        _wlWeek: dateKey
      }, 'weekletter');
    });
  }
  /* R3317-E：信卡收下——写本周档键，重渲即消失（不再打扰）。 */
  var _wlx = box.querySelector('#wlDismiss');
  if (_wlx && !_wlx.dataset.bound) {
    _wlx.dataset.bound = '1';
    _wlx.addEventListener('click', function () {
      try {
        var _dow2 = (new Date(dateKey + 'T00:00:00').getDay() + 6) % 7;
        localStorage.setItem(
          'weeklyLetter:' + _isoShift(dateKey, -_dow2), '1');
      } catch (eWX) {}
      var _lw2 = el('weeklyLetter');
      if (_lw2) _lw2.remove();
      /* R3321-P3：收下后焦点丢回 body——归还打卡区首个可点件。 */
      try {
        var _fw = document.querySelector(
          '#dailyCard .checkin-opt, #dailyCard button, #funcGrid .func-card');
        if (_fw && _fw.focus) _fw.focus();
      } catch (eFW) {}
    });
  }
  /* R3319-F：月信收下——写上月档键，重渲即消失。 */
  var _mlx = box.querySelector('#mlDismiss');
  if (_mlx && !_mlx.dataset.bound) {
    _mlx.dataset.bound = '1';
    _mlx.addEventListener('click', function () {
      try {
        var _t0b = new Date(dateKey + 'T00:00:00');
        var _pmb = new Date(_t0b.getFullYear(), _t0b.getMonth() - 1, 1);
        localStorage.setItem('monthlyLetter:' + _pmb.getFullYear() + '-' +
          String(_pmb.getMonth() + 1).padStart(2, '0'), '1');
      } catch (eMX) {}
      var _lm3 = el('monthlyLetter');
      if (_lm3) _lm3.remove();
      /* R3321-P3：同上——焦点归还不丢 body。 */
      try {
        var _fm = document.querySelector(
          '#dailyCard .checkin-opt, #dailyCard button, #funcGrid .func-card');
        if (_fm && _fm.focus) _fm.focus();
      } catch (eFM) {}
    });
  }
  /* R3325-D：未来信收下——标记 opened 不再浮出；写信入口开弹层。 */
  box.querySelectorAll('.fl-open').forEach(function (btn) {
    if (btn.dataset.bound) return;
    btn.dataset.bound = '1';
    btn.addEventListener('click', function () {
      try {
        var lst = JSON.parse(localStorage.getItem('futureLetters') || '[]');
        lst.forEach(function (lt) {
          if (lt && String(lt.id) === btn.dataset.flid) lt.opened = true;
        });
        _lsUnionWrite('futureLetters', lst,
          function (l) { return l && l.id; }, 50);
      } catch (eFO) {}
      /* R3329（审-P3）：data-flid 直拼选择器——id 含 " 类字符
       * 直接 SyntaxError（且抛在 opened 落库后=假收信）。遍历比对。 */
      var card = null;
      box.querySelectorAll('.fl-letter[data-flid]').forEach(function (el2) {
        if (el2.getAttribute('data-flid') === btn.dataset.flid) card = el2;
      });
      if (card) card.remove();
      showToast('信替你收好，过去的你很欣慰', 'ok');
    });
  });
  var _flw = box.querySelector('#flWrite');
  if (_flw && !_flw.dataset.bound) {
    _flw.dataset.bound = '1';
    _flw.addEventListener('click', _flWriteOpen);
  }
  /* R3354（审-低）：corrupt 备份信取回——弹可选文本域，原文复制走
   * 后清掉备份位（不删是防用户没复制就关窗丢信）。 */
  var _flrc = box.querySelector('#flRecover');
  if (_flrc && !_flrc.dataset.bound) {
    _flrc.dataset.bound = '1';
    _flrc.addEventListener('click', function () {
      var _raw2 = '';
      try { _raw2 = localStorage.getItem('futureLetters:corrupt') || ''; }
      catch (eRC) {}
      if (!_raw2) { showToast('备份已经被清掉了', 'info'); return; }
      try {
        _showTextExportModal('找回的信',
          '这封信当时没能存进列表，原文在下面——长按复制带走吧。\n\n' +
          _raw2, '长按下面文本全选复制');
      } catch (eM2) { showToast(_raw2.slice(0, 200), 'info'); }
      try { localStorage.removeItem('futureLetters:corrupt'); }
      catch (eRD) {}
      _flrc.remove();
    });
  }
  var _alb = box.querySelector('.ck-album');
  if (_alb && !_alb.dataset.bound) {
    _alb.dataset.bound = '1';
    _alb.addEventListener('toggle', function () {
      if (_alb.open) _renderCheckinAlbum(dateKey);
    });
    _alb.addEventListener('click', function (e) {
      var cell = e.target.closest('.ck-album-cell');
      if (cell && cell.dataset.fb) showToast(cell.dataset.fb, 'info');
    });
  }
  var _wish = box.querySelector('.ck-wish');
  if (_wish && !_wish.dataset.bound) {
    _wish.dataset.bound = '1';
    _wish.addEventListener('toggle', function () {
      if (_wish.open) _renderWishBottle();
    });
    _wish.addEventListener('click', function (e) {
      var act = e.target.closest('[data-wish]');
      if (act) _wishAction(act.dataset.wish, act.dataset.arg || '', dateKey);
    });
  }
  var _shred = box.querySelector('.ck-shred');
  if (_shred && !_shred.dataset.bound) {
    _shred.dataset.bound = '1';
    _shred.addEventListener('toggle', function () {
      if (_shred.open) _renderShredder();
    });
    _shred.addEventListener('click', function (e) {
      var act = e.target.closest('[data-shred]');
      if (act) _shredAction(act.dataset.shred, dateKey);
    });
  }
  /* R3264（R49）：周目标达成庆祝——本周目标达成时飘一颗 ✨ 星星
   * 并 toast，只做一次（按当天 key）。 */
  if (_goalGap <= 0) {
    var _gck = 'checkin:goal-celebrated:' + dateKey;
    var _gcd = false;
    try { _gcd = window.localStorage.getItem(_gck) === '1'; } catch (eG) {}
    if (!_gcd) {
      try { window.localStorage.setItem(_gck, '1'); } catch (eS) {}
      var _gBtn = box.querySelector('.ck-goal-opt.active');
      _microCelebrate(_gBtn);
      showToast('本周目标达成啦——给自己放个假也是分 🌱', 'ok');
    }
  }
  var _cks = box.querySelector('#checkinShare');
  if (_cks) _cks.addEventListener('click', function () {
    /* R3252：分享图带签面插画——预载完成后把 <img> 传进海报
     * spec（cards[].img 直绘），图挂掉回落纯文字版不断链。 */
    var _go = function (img) {
      var _p = downloadPoster(
        { streak: _streak, pick: saved, art: img }, 'checkin');
      if (_p && _p.catch) _p.catch(function () {});
    };
    var _ak = saved && CHECKIN_ART[saved];
    if (_ak) {
      var _im = new Image();
      _im.onload = function () { _go(_im); };
      _im.onerror = function () { _go(null); };
      _im.src = '/static/cream/' + _ak + '.jpg';
    } else { _go(null); }
  });
  var _ckw = box.querySelector('#checkinWeek');
  if (_ckw) _ckw.addEventListener('click', function () {
    var _days = [];
    for (var _i = -6; _i <= 0; _i++) {
      var _dk = _isoShift(dateKey, _i);
      _days.push({ date: _dk, opt: _ckAll[_dk] || '' });
    }
    var _p2 = downloadPoster({ days: _days, streak: _streak }, 'checkin-week');
    if (_p2 && _p2.catch) _p2.catch(function () {});
  });
  var _ckm = box.querySelector('#checkinMonth');
  if (_ckm) _ckm.addEventListener('click', function () {
    /* 本月 1 号→今天逐日扫，聚合签种分布/稀有签/连签峰值。 */
    var _mm = dateKey.slice(0, 7), _days = [];
    for (var _d = 1; _d <= 31; _d++) {
      var _dk = _mm + '-' + (_d < 10 ? '0' : '') + _d;
      if (_dk > dateKey) break;
      _days.push({ date: _dk, opt: _ckAll[_dk] || '' });
    }
    var _p3 = downloadPoster({ days: _days, streak: _streak },
      'checkin-month');
    if (_p3 && _p3.catch) _p3.catch(function () {});
  });
  var _cky = box.querySelector('#checkinYear');
  if (_cky) _cky.addEventListener('click', function () {
    var _py = downloadPoster(_yearStats(dateKey), 'year-wrap');
    if (_py && _py.catch) _py.catch(function () {});
  });
  /* R2350f（R102-P2-8）：「明天提醒我」——无推送基建下的诚实实现：
   * 拿 Notification 权限 + 本地打标，次日开屏 toast 提醒。权限被拒
   * 时按钮如实回退，不假装已开。 */
  var _ckr = box.querySelector('#checkinRemind');
  if (_ckr) _ckr.addEventListener('click', function () {
    var _on = false;
    try { _on = localStorage.getItem('remind:1') === '1'; } catch (e) {}
    if (_on) {
      try { localStorage.removeItem('remind:1'); } catch (e2) {}
      _ckr.innerHTML = '🔔 明天提醒我';
      showToast('好，明天不喊你了', 'info');
      return;
    }
    var _grant = function () {
      try { localStorage.setItem('remind:1', '1'); } catch (e3) {}
      _ckr.innerHTML = '🔔 明天会来喊你';
      showToast('好嘞，明天打开铺子就提醒你抽新签', 'ok');
    };
    if (typeof Notification !== 'undefined' &&
        Notification.permission === 'granted') { _grant(); return; }
    /* R2350g（R104-P1-2）：denied 不能再落进 _grant()——权限已被拒还
     * 翻牌打标，明天根本喊不了却让用户以为开着。如实回退。 */
    if (typeof Notification !== 'undefined' &&
        Notification.permission === 'denied') {
      showToast('浏览器把通知关掉了，去地址栏旁边改权限，或明天自己回来看看也行', 'info');
      return;
    }
    if (typeof Notification !== 'undefined' && Notification.requestPermission) {
      Notification.requestPermission().then(function (p) {
        if (p === 'granted') _grant();
        else showToast('浏览器不让发通知，没关系，明天自己回来看看也行', 'info');
      }).catch(function () {
        showToast('浏览器不让发通知，明天自己回来看看也行', 'info');
      });
      return;
    }
    /* 无 Notification 环境——仍然存标记，次日开屏 toast 兜底提醒。 */
    _grant();
  });
  /* R2350f（R102-P2-13）：「安利铺子」——应用级分享出口，不挂结果件。
   * 复制 钩子文案+链接；支持系统分享面板的走面板。 */
  var _shops = box.querySelector('#shopShare');
  if (_shops) _shops.addEventListener('click', function () {
    var _url = location.origin + '/?from=share';
    var _txt = '我在「小满的解忧铺」抽日签/翻黄历/测桃花，来一起玩 ' + _url;
    var _ok = function () { showToast('安利文案已复制：发给闺蜜吧', 'ok'); };
    var _bad = function () { showToast('复制没成功，手动复制地址栏链接吧', 'warn'); };
    if (navigator.share) {
      navigator.share({ title: '小满的解忧铺', text: _txt, url: _url })
        .catch(function () {});
      return;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(_txt).then(_ok, _bad);
    } else {
      try {
        var _ta2 = document.createElement('textarea');
        _ta2.value = _txt; _ta2.style.position = 'fixed';
        _ta2.style.opacity = '0';
        document.body.appendChild(_ta2); _ta2.select();
        document.execCommand('copy') ? _ok() : _bad();
        _ta2.remove();
      } catch (e4) { _bad(); }
    }
  });
  if (!box.dataset.bound) {
    box.dataset.bound = '1';
    box.addEventListener('click', function (e) {
      /* R3264（R48）：周目标设置——点 3/5/7 直接存 goal 并重渲。 */
      var _goalBtn = e.target.closest('.ck-goal-opt');
      if (_goalBtn && _goalBtn.dataset.g) {
        try { localStorage.setItem('checkin:goal', _goalBtn.dataset.g); } catch (eG) {}
        /* R3321-P2：重渲前就地翻 aria-pressed（重渲后新钮已带对态）。 */
        box.querySelectorAll('.ck-goal-opt').forEach(function (x) {
          x.setAttribute('aria-pressed', x === _goalBtn ? 'true' : 'false');
        });
        renderCheckin(dateKey);
        return;
      }
      /* R2350j：收编到打卡选项组内——许愿瓶等复用 .checkin-opt
       * 皮相的按钮（无 data-opt）不能被当成打卡签重渲。 */
      const btn = e.target.closest('.checkin-opts .checkin-opt');
      if (!btn || !dateKey || !btn.dataset.opt || btn.disabled) return;
      /* R230n（R25-P2-1）：dateKey 是渲染时刻闭包——挂过零点的陈旧 tab
       * 绑定着昨天，点击会把「昨天」写进去、清理循环再把「今天」误删。
       * 点击时重算今天：变了就先整卡重渲成今天，再接着写今日键。
       * 注意：重渲后原按钮已脱离 DOM，picked 态按 opt 在新按钮上重标。 */
      const opt = btn.dataset.opt;
      /* R2350g（R106-F6）：点打卡顺手翻日——隔夜 tab 的卡面先换新天
       * 再写今日键。 */
      try { if (window.__onDayFlip) window.__onDayFlip(); } catch (eF) {}
      var _today = todayIso();
      if (_today && dateKey !== _today) {
        dateKey = _today;
        renderCheckin(_today);
      }
      /* R3251：落盘前再读一次今日键——已抽过（陈旧 DOM/双击/
       * 他页签先打）就只重渲不覆写。抽过的签今日不可更换。 */
      var _ex = null;
      try { _ex = window.localStorage.getItem('checkin:' + dateKey); }
      catch (eX) {}
      if (_ex) { renderCheckin(dateKey); return; }
      /* R230q（R28-P3-7）：先落盘再标 picked——原先 catch 后仍无条件
       * 打勾，写失败也显示「已打卡」静默丢数据（隐私模式/quota）。 */
      try {
        window.localStorage.setItem('checkin:' + dateKey, opt);
        /* R3250c：翻牌签力——按签面语义给三维度之一 +1~3 加持
         * （同日同签同值，确定性可复验）。写入后 renderCheckin 与
         * 维度彩条同步显形。 */
        try {
          var _bdMap = {'吃瓜运':'感情','摸鱼运':'感情','甜甜运':'感情',
            '上岸运':'做事','顺顺签':'做事','破水逆运':'做事',
            '暴富签':'钱袋'};
          var _bd = _bdMap[opt] ||
            ['感情','做事','钱袋'][_hashNum(dateKey + '|' + opt) % 3];
          var _bn = 1 + _hashNum(dateKey + '|buff|' + opt) % 3;
          window.localStorage.setItem('checkinBuff:' + dateKey,
            JSON.stringify({d: _bd, n: _bn}));
          window.__ckJustPicked = opt;
          /* 旗标要活过两次渲染（本函数一次 + loadDaily 重拉一次），
           * 不能在 renderCheckin 里即读即清——1.5s 后自清兜底。 */
          setTimeout(function () {
            try { window.__ckJustPicked = null; } catch (eJP) {}
          }, 1500);
        } catch (eB) {}
        /* R230j（R22-P3-2）：checkin:* 清理收口。
         * R230y（R36-P1-3）：连签是留客钩子——不再写今日删昨日，
         * 改为保留最近 90 天，超过才清。 */
        var _cutoff = 'checkin:' + _isoShift(dateKey, -150);
        var _cutoff2 = 'dailyRevealed:' + _isoShift(dateKey, -150);
        var _cutoff3 = 'checkinBuff:' + _isoShift(dateKey, -150);
        for (var _ci = window.localStorage.length - 1; _ci >= 0; _ci--) {
          var _ck = window.localStorage.key(_ci);
          /* R39-P3-1：dailyRevealed:* 此前无 GC，每年 365 个废键——
           * 与 checkin:* 同一 90 天收口。 */
          /* R2349（R65-P2-4）：checkinCeleb 同收（尾段是日期）。 */
          var _ckd = _ck && _ck.indexOf('checkinCeleb:') === 0
            ? 'checkinCeleb:' + _ck.slice(_ck.lastIndexOf(':') + 1) : null;
          /* R3314（R3309-P2）：mood/moodlv/journal/ritual/usage:d/
           * rlast 日期后缀键此前永不 GC——每年每族 ~365 个废键，
           * 拖慢全仓 localStorage 遍历。同一 150 天收口；moodjar/
           * usage:v/usage:first/mood:lv 等非日期键不动。 */
          var _fam = null;
          if (_ck) {
            ['mood:', 'moodlv:', 'journal:', 'ritual:', 'usage:d:',
             'rlast:', 'mood:dream:', 'weeklyLetter:', 'monthlyLetter:',
             /* R3396-P2-1：'ansb:' 无日期后缀键，从族表清出（死项）。 */
             'pilePick:', 'qian:', 'manifest:'].forEach(function (_p) {
              if (_ck.indexOf(_p) === 0) _fam = _p;
            });
          }
          /* R3328（审-中/低）：monthlyLetter:YYYY-MM 尾段按
           * YYYY-MM 比（非 YYYY-MM-DD）；checkinCeleb 与启动段
           * 统一 150 天口径（此前打卡路径 90/启动 150 双口径）。 */
          var _famCut = _fam === 'monthlyLetter:'
            ? _isoShift(dateKey, -150).slice(0, 7)
            : _isoShift(dateKey, -150);
          /* R3395-P2-1：日期尾按最后一段比——qian:t:<date> 的尾段
           * 是 't:YYYY-MM-DD'，按 fam 前缀切永远失配、永不回收；
           * 与启动兜底 _gks 同一 lastIndexOf 口径。 */
          var _famTailOk = _fam
            ? (_fam === 'monthlyLetter:'
              ? /^\d{4}-\d{2}$/.test(_ck.slice(_fam.length))
              : /^\d{4}-\d{2}-\d{2}$/.test(
                  _ck.slice(_ck.lastIndexOf(':') + 1)))
            : false;
          /* 同理：比较也要按尾段——qian:t:<d> 整键排在 'qian:<cut>'
           * 之后，整键比永不命中。 */
          var _famTail = _fam && _fam !== 'monthlyLetter:'
            ? _ck.slice(_ck.lastIndexOf(':') + 1)
            : _ck;
          if (_ck && ((_ck.indexOf('checkin:') === 0 && _ck < _cutoff) ||
              (_ck.indexOf('dailyRevealed:') === 0 && _ck < _cutoff2) ||
              (_ck.indexOf('checkinBuff:') === 0 && _ck < _cutoff3) ||
              (_fam && _famTailOk &&
               (_fam === 'monthlyLetter:' ? _ck < _fam + _famCut
                                         : _famTail < _famCut)) ||
              (_ckd && _ckd < 'checkinCeleb:' +
                _isoShift(dateKey, -150)))) {
            window.localStorage.removeItem(_ck);
          }
        }
      } catch (e2) {
        showToast('这次打卡没存上（存储不可用）', 'warn');
        return;
      }
      /* R3264（R41）：签到微庆祝——抽中签时也飘一颗 ✨ 星星。 */
      _microCelebrate(btn);
      /* R230y：整卡重渲——picked 态、连签天数、点阵、反馈一次同步
       * （原手改 class/textContent 会让新打卡的连签数滞后到下次渲染） */
      renderCheckin(dateKey);
      /* R3250c：签力加持写在维度彩条上——维度区是 loadDaily 里渲染
       * 的，不重拉的话 +n 角标要等下次进页才显形。/api/daily 有缓存，
       * 重拉成本只是一次本地往返。 */
      try { loadDaily(); } catch (eLD) {}
      /* R3343：打完卡立刻同步合拍集合（force 破 6h 节流）——
       * 对方今天若也打了，下一秒就能看见合拍+1。 */
      try { _coupleSync(true); } catch (eCP) {}
      /* R3264（R46）：签到身份反馈——抽完卡给一句「正在成为」。 */
      try { showToast(_identityPhrase(), 'ok'); } catch (eI) {}
      /* R233f（R43-P2-3）：整卡重渲销毁了聚焦钮，焦点丢 BODY 从头爬
       * ——落回新渲出的 picked 钮。 */
      var _pk = box.querySelector('.checkin-opt.picked');
      if (_pk) { try { _pk.focus(); } catch (ef) {} }
      /* R231h（R39-P3-2）：已装为 PWA 时把连签数打到 app 角标——
       * 未安装/不支持的浏览器静默跳过。 */
      try {
        if (navigator.setAppBadge) {
          var _bs = _checkinStreak(_checkinAll(), dateKey);
          if (_bs > 0) navigator.setAppBadge(_bs).catch(function () {});
        }
      } catch (e4) {}
      /* R231h（R39-P3-3）：里程碑仪式——连签 3/7/14/30 的当天给一张
       * 小庆典卡（可直发分享图）；同一天同一档不重复弹。 */
      try {
        var _ns = _checkinStreak(_checkinAll(), dateKey);
        var _mspec = 'checkinCeleb:' + _ns + ':' + dateKey;
        /* R2349t（R88-10）：连签档补 60/100——百日选手和满月选手
         * 不该是同一张脸。键结构 checkinCeleb:N:date 与 90 天 GC 兼容。 */
        /* R3314（R3309-P0）：去重键是 _mspec，原写 _mk——未声明变量
         * 抛 ReferenceError 被外层 catch 静默吞掉，里程碑卡上线即哑火。 */
        if ([3, 7, 14, 30, 60, 100].indexOf(_ns) >= 0 &&
            !localStorage.getItem(_mspec)) {
          localStorage.setItem(_mspec, '1');
          _checkinCelebrate(_ns, opt);
        }
      } catch (e3) {}
    });
  }
  /* R3343：渲染间隙顺手对一次合拍（6h 节流，CP 档不齐/无
   * crypto.subtle 内部自己跳）。打卡成功路径是 force 直调。 */
  try { _coupleSync(false); } catch (eCP2) {}
}
/* R231h：连签里程碑卡——轻量模态，标题+一句+分享图按钮。 */
function _checkinCelebrate(streak, opt) {
  /* R2349g（R68-P2）：里程碑文案 1→3 句池按日轮换——连打多年不再
   * 只见同一句。 */
  var _MILES = {
    3: ['小满贯开头啦', '三天连成线啦', '三连达成，好兆头'],
    7: ['整一周，仪式感拿捏', '七连达成，习惯上身', '一周不断，很可以'],
    14: ['半月不断，稳稳的', '十四天连签，坚持发光', '半个月啦，厉害'],
    30: ['满月级选手，了不起', '三十天连签，传说级别', '满月达成，膜拜'],
    60: ['双满月成就，两轮月圆你都在', '六十天连签，稳定得像月亮',
         '双满月达成，这毅力离谱了'],
    100: ['百日传说达成，你是镇铺之宝', '一百天连签，离谱但真实',
          '百日不间断，小满给你磕一个']
  };
  var bd = document.createElement('div');
  bd.className = 'celeb-backdrop';
  bd.innerHTML =
    /* R2349t（R88-12）：档位差异化——标题前置档徽 emoji + data-tier
     * 描边分档（CSS 侧），3 天与 100 天不再同一张脸。 */
    '<div class="celeb-card" data-tier="' + esc(String(streak)) +
    '" role="dialog" aria-modal="true" aria-label="连签里程碑">' +
    '<img src="/static/cream/poster-mascot.png" alt="" class="celeb-img">' +
    '<div class="celeb-title">' +
    ({3: '🌱', 7: '🎀', 14: '🌗', 30: '🌕', 60: '💮', 100: '🏮'}[streak] ||
     '🎉') + ' 连续 ' + streak + ' 天打卡达成</div>' +
    '<div class="celeb-sub">' + esc(_dayPick(
      _MILES[streak] || [''], 'mile|' + streak)) +
    '，记得明天也来</div>' +
    '<div class="celeb-row">' +
    '<button type="button" class="celeb-share">📸 晒一下</button>' +
    /* R3319（规划C）：7 天起送连签限定壁纸——里程碑奖励落实物，
     * 同日出图、纪念标落款，可直接晒。 */
    (streak >= 7
      ? '<button type="button" class="celeb-wap">🎁 领限定壁纸</button>'
      : '') +
    '<button type="button" class="celeb-x">收下好运</button>' +
    '</div></div>';
  /* R233f（R43-P1-1）：celeb 此前是假模态——焦点不进、Esc 不关、
   * Tab 穿透遮罩、关后焦点丢 BODY。补齐 dialog 语义+焦点圈+归还。 */
  var _trig = document.activeElement;
  var _celebKey = function (e) {
    if (e.key === 'Escape' || e.keyCode === 27) { _close(); return; }
    if (e.key === 'Tab' || e.keyCode === 9) {
      var _f = bd.querySelectorAll('button,[href],[tabindex]:not([tabindex="-1"])');
      if (!_f.length) return;
      var _first = _f[0], _last = _f[_f.length - 1];
      if (e.shiftKey && document.activeElement === _first) {
        e.preventDefault(); _last.focus();
      } else if (!e.shiftKey && document.activeElement === _last) {
        e.preventDefault(); _first.focus();
      } else if (!bd.contains(document.activeElement)) {
        e.preventDefault(); _first.focus();
      }
    }
  };
  var _close = function () {
    document.removeEventListener('keydown', _celebKey);
    _mainInert(false);
    if (bd.parentNode) bd.remove();
    /* 焦点归还：触发钮已被打卡重渲销毁 → 落回新打的 picked 钮 */
    /* R3321-P3：_trig 可能是 body/非交互元素（控制台直调）——
     * 归还前再查一遍「可聚焦」，否则一样丢回 body。 */
    var _trigOk = _trig && _trig.isConnected &&
      (_trig.matches('button,a,[tabindex]:not([tabindex="-1"]),input,' +
       'select,textarea') || _trig.tabIndex >= 0);
    var back = _trigOk ? _trig :
      (document.querySelector('.checkin-opt.picked') || el('dailyCard'));
    if (back && back.focus) { try { back.focus(); } catch (ef) {} }
  };
  bd.addEventListener('click', function (e) {
    if (e.target === bd || e.target.closest('.celeb-x')) _close();
  });
  var sh = bd.querySelector('.celeb-share');
  if (sh) sh.addEventListener('click', function () {
    var p = downloadPoster({ streak: streak, pick: opt }, 'checkin');
    if (p && p.catch) p.catch(function () {});
    _close();
  });
  /* R3319（规划C）：连签限定壁纸——种子/落款/文件名带纪念标；
   * 壁纸 chunk 惰性加载，downloadWallpaper 存根已代理参数。 */
  var wp = bd.querySelector('.celeb-wap');
  if (wp) wp.addEventListener('click', function () {
    var _j = window.__lastDaily;
    if (!_j) { showToast('今日运势还没出来，等它算好再领～', 'warn'); return; }
    downloadWallpaper(_j, {
      tag: '连签 ' + streak + ' 天纪念 · 小满的解忧铺',
      fname: '连签' + streak + '天'
    });
    _close();
  });
  /* R2349h（R69-P2-10）：先挂节点再 inert 并把 bd 传入 except——
   * 模态下侧栏三件套也入 inert；原顺序靠「还没挂」侥幸躲坑。 */
  document.body.appendChild(bd);
  _mainInert(true, bd);
  document.addEventListener('keydown', _celebKey);
  var _fb = bd.querySelector('.celeb-share') || bd.querySelector('.celeb-x');
  if (_fb) { try { _fb.focus(); } catch (e2) {} }
}
/* R230y（R36-P1-4）：「我的生日」本地 profile——任一本人表单提交
 * 成功后写入 localStorage，其余同人表单的空值/仍带预填标记的字段
 * 自动代入；用户手动改过的字段（input/change 清 data-me）永不覆盖。
 * 合婚 B 侧独立存 me:partner；起名是孩子生日，不参与。 */
/* R2343（R59-gap5）：接续条时态——_hl0.d 距今天几天→昨天/前几天/之前。 */
function _hlAgoWord(dstr) {
  var dd = 1;
  try {
    var p = String(dstr || '').split('-');
    if (p.length === 3) {
      var t0 = new Date(); t0.setHours(0, 0, 0, 0);
      dd = Math.round((t0 - new Date(+p[0], +p[1] - 1, +p[2])) / 86400000);
    }
  } catch (e) { dd = 1; }
  return dd <= 1 ? '昨天' : (dd < 8 ? '前几天' : '之前');
}
function _meGet(key) {
  try {
    var j = null;
    try {
      j = JSON.parse(window.localStorage.getItem(key) || 'null');
    } catch (eLS) { j = null; }
    /* R3303-P3：隐私模式拒写 localStorage——档案落不了盘就退回
     * 会话内存档，封面门/判词个性化本会话内照样工作（不跨会话）。 */
    if (!j || typeof j !== 'object') {
      try {
        var _sj = (window.__meSessionMap && window.__meSessionMap[key]) || null;
        if (_sj && typeof _sj === 'object') j = _sj;
      } catch (eSM) {}
    }
    if (!j || typeof j !== 'object') return null;
    /* R3239：手工写坏的脏档兜底——y/m/d/h 必须是有限数（字符串
     * 数字归一），脏值删键；g/n/lunar 是字符串域不动。否则
     * "abc" 年份会被回填进所有表单、档案条渲染出乱码。 */
    ['y', 'm', 'd', 'h'].forEach(function (k) {
      if (j[k] == null || j[k] === '') return;
      var n = Number(j[k]);
      if (Number.isFinite(n)) j[k] = n; else delete j[k];
    });
    return j;
  } catch (e) { return null; }
}
/* R2501（R142-P1-3 收尾）：出厂示例生日（1990-5-15 等）原样提交就静默
 * 写进「我的档案」，污染次日判词/生日横幅。输入值仍与 HTML 出厂
 * defaultValue 一致、select 仍停首选项 = 用户没动过，这种提交不写档。 */
function _fieldsUntouched(ids) {
  for (var i = 0; i < ids.length; i++) {
    var node = document.getElementById(ids[i]);
    if (!node) continue;
    var untouched = (node.dataset.invite !== '1')
      && (node.dataset.touched !== '1')
      && ((node.tagName === 'SELECT')
        ? (node.selectedIndex <= 0)
        : (String(node.value) === String(node.defaultValue)));
    if (!untouched) return false;
  }
  return true;
}
function _meSave(key, rec) {
  /* R3306-P2：wipe 墓碑快照——写前比对（见下），入口先取一份
   * （调用方 await 完才进本函数的场景靠它挡住陈旧写）。 */
  try { window.__meSaveWipeAt = localStorage.getItem('wipeAt'); }
  catch (eW0) {}
  /* R233n：合并写——nick 等补充键只有个别表单维护，其他表单提交时
   * 传全量 y/m/d/h/g 若无 n，直接覆盖会把 nick 抹掉。合并后旧键保留；
   * 显式传 '' 仍可清掉某键（'' 会覆盖旧值）。 */
  var old = {};
  try {
    var _oj = JSON.parse(window.localStorage.getItem(key) || 'null');
    if (_oj && typeof _oj === 'object') old = _oj;
  } catch (e0) {}
  /* R2345（R61-P1-4）：写库时就净化昵称——脏值不落地，直写
   * localStorage 绕过本函数的极端路径另有 _chatFacts 处兜底。 */
  if ('n' in rec) rec = Object.assign({}, rec, {n: _meNickClean(rec.n)});
  var _merged = Object.assign(old, rec);
  /* R3320-P1-2：未来年生辰统一收口——所有直写 _meSave 的路径
   * （bazi 表单/dailyAsk/昵称单改等）合并后生辰在未来即整写
   * 拒收。解读照跑不落档，手滑不污染回填矩阵。 */
  try {
    var _fyT = new Date(+_merged.y, +_merged.m - 1, +_merged.d);
    var _fyN = new Date(); _fyN.setHours(23, 59, 59, 0);
    if (+_merged.y && _fyT > _fyN) {
      showToast('这个生日还没到哦——帮你排了盘，但不写进档案', 'info');
      return;
    }
  } catch (eFY0) {}
  /* R3306-P2：在途写无免疫——lunar 换算/异步链回包时另一 tab 刚
   * wipe 完，旧生辰落盘=复活。写前重读墓碑，变了即弃写。 */
  try {
    var _w0 = localStorage.getItem('wipeAt');
    if (_w0 !== (window.__meSaveWipeAt || null)) {
      return;
    }
  } catch (eW) {}
  try {
    window.localStorage.setItem(key, JSON.stringify(_merged));
  } catch (e) {
    /* R2345（R63-P2-4）：checkin 写坏有 toast——me 是同原则更重的
     * 字段（生辰），写失败不能再静默。 */
    try { showToast('档案没存上：再试一次看看', 'warn'); } catch (e3) {}
  }
  try {
    (window.__meSessionMap = window.__meSessionMap || {})[key] = _merged;
  } catch (eSM) {}
  /* R2343（R59-gap4）：同页写入不触发 storage 事件——昵称存完立刻
   * 刷新空态招呼/档案条，改完不用刷新就看到名字。 */
  try { _chatChipsPersonalize(); _renderMeStrip(); } catch (e2) {}
  /* R3243：档案写全后独立副卡就地藏（_bindDailyAsk 在主页模块
   * 闭包里够不着——此处行内 hidden 即可，刷新由 loadDaily 后
   * 的 _bindDailyAsk 幂等兜底）。 */
  try { var _dA = el('dailyAsk'); if (_dA) _dA.hidden = true; } catch (eDA) {}
  /* R3185：存档即回填——此前只在 init 跑一次 _meFillAll，
   * 同会话里「合婚存了生日→开星座本命盘」仍是出厂 2000/6/15，
   * 得重填一遍（用户眼里就是「你根本没记住我」）。data-touched
   * 字段不动，只填没动过/此前由档案填的格。 */
  try { _meFillAll(); } catch (e4) {}
}
/* R3239：档案落档统一器——此前各表单「农历不落档」（R3206 防农历数
 * 进公历坐标系）遍地开花；换算端点上线后统一成：农历→换算公历坐标+
 * 农历原值标注（与礼物表单/主排盘同口径）；公历显式传 lunar:null 清
 * 旧标注（_meSave 是合并写，不传键会把旧农历贴到新生日上）。
 * opts.n 传了才动昵称键（'' 按 _meSave 语义清昵称）；换算失败不落档
 * 也不挡解读（静默——解读已拿到，档案弱保存可下轮补）。 */
async function _meSaveFromBirth(key, opts) {
  /* R3306-P2：wipe 墓碑必须在 await 前取——换算回包落地时另一
   * tab 若刚「忘掉一切」，本次生辰不得再落盘（含会话档）。 */
  var _w0 = null;
  try { _w0 = localStorage.getItem('wipeAt'); } catch (eW) {}
  try {
    var rec = { h: opts.h, g: opts.g, lunar: null };
    if ('n' in opts) rec.n = opts.n;
    if (opts.lunar) {
      var cj = await postJSON('/api/lunar/convert',
        { y: opts.y, m: opts.m, d: opts.d,
          leap: (opts.leap ? 1 : 0) });
      if (!cj || !cj.solar) return;
      try {
        if (localStorage.getItem('wipeAt') !== _w0) return;
      } catch (eW2) {}
      rec.y = cj.year; rec.m = cj.month; rec.d = cj.day;
      rec.lunar = '农历' + opts.y + '年' + opts.m + '月' + opts.d + '日' +
        (opts.leap ? '（闰）' : '');
    } else {
      rec.y = opts.y; rec.m = opts.m; rec.d = opts.d;
    }
    /* R3313（审-P2-1）：换人不留旧名——y/m/d 任一变了而本次没给
     * 新名，旧昵称挂到新档案上（新 TA 被叫成旧 TA）。清键让
     * _meSave 合并写把 n 覆盖成 ''。 */
    if (!('n' in rec)) {
      try {
        var _old = _meGet(key);
        if (_old && (Number(_old.y) !== Number(rec.y) ||
                     Number(_old.m) !== Number(rec.m) ||
                     Number(_old.d) !== Number(rec.d))) {
          rec.n = '';
        }
      } catch (eN) {}
    }
    /* R3320-P1-2：未来年由 _meSave 统一收口（含农历换算后的
     * 公历坐标）——此处不再重复判，直接落。 */
    _meSave(key, rec);
  } catch (e) {}
}
/* ids = {y:'th_year', m:'th_month', d:'th_day', h:'th_hour', g:'th_gender'} *
 * 字段表用字面量不用模块级 var——init() 的调用点在本块之前，var 赋值
 * 尚未执行，二次加载（localStorage 已有 me）会对 undefined.forEach 抛错
 * 把 init 整条链炸断（实测：深链/ai-polish/渲染全灭）。 */
function _meFill(key, ids) {
  var rec = _meGet(key);
  if (!rec) return;
  ['y', 'm', 'd', 'h', 'g', 'n'].forEach(function (k) {
    var e = el(ids[k]);
    if (!e) return;
    var v = rec[k];
    if (v == null || v === '') return;
    /* R2343（R59-BROKEN）：硬编码 value= 默认值让非空判定恒真——
     * 表单档案代入从未生效过。值还停在出厂默认即视同未动过可回填；
     * select 无 defaultValue，用「还停在首选项」近似。受邀链回填的
     * 字段带 data-invite，跳过。R2501：data-touched 表示用户本 tab
     * 实际碰过，即使后来改回默认值/首选项也不能被跨 tab 档案回填覆盖。
     * R3247：data-celeb=明星自动填——档案回填不得盖掉公开生日。 */
    if (e.dataset.invite === '1' || e.dataset.touched === '1' ||
        e.dataset.celeb === '1') return;
    var _untouched = (e.tagName === 'SELECT') ? (e.selectedIndex <= 0)
      : (e.value === '' || e.value === e.defaultValue);
    if (_untouched || e.dataset.me === '1') {
      e.value = String(v);
      e.dataset.me = '1';
    }
  });
}
/* R2349t（R88-9 修正）：_visitCount 原定义在 init() 内——聊天空态
 * 也用它判「第 N 次来」，提升到模块级（语义不变：同日不重复计）。 */
function _visitCount() {
  try {
    var v = String(localStorage.getItem('visits') || '').split(',')
      .filter(Boolean);
    var t = todayIso();
    if (v.indexOf(t) < 0) {
      /* R3339（审-中）：visits 日期集——写前重读并集，另一 tab
       * 同日先写的轨迹不再被整表压掉（集语义去重）。 */
      var cur = String(localStorage.getItem('visits') || '').split(',')
        .filter(Boolean);
      cur.forEach(function (d) { if (v.indexOf(d) < 0) v.push(d); });
      v.push(t);
      if (v.length > 400) v = v.slice(-400);
      localStorage.setItem('visits', v.join(','));
    }
    return v.length;
  } catch (e) { return 0; }
}
/* R2349t（R88-1/8）：「今天是不是我生日」与「距上次来访隔了几天」——
 * 封面/日签/聊天空态/打卡四处共用同一口径。 */
/* R2350g（R106-F2）：2/29 生日的平年口径——三处此前分裂：_isMyBirthday
 * 精确日永不命中（全年不弹），两处倒计时 new Date(y,1,29) 溢进 3/1。
 * 统一映射：平年 2/29 → 2/28 庆生。 */
function _bdayInYear(m, d, y) {
  m = Number(m); d = Number(d);
  if (m === 2 && d === 29 &&
      !(y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0))) {
    d = 28;
  }
  return new Date(y, m - 1, d);
}
function _isMyBirthday() {
  try {
    var _m = _meGet('me');
    if (!_m || !_m.y || !_m.m || !_m.d) return false;
    var _t = new Date();
    var _bd = _bdayInYear(_m.m, _m.d, _t.getFullYear());
    return _bd.getMonth() === _t.getMonth() &&
      _bd.getDate() === _t.getDate();
  } catch (e) { return false; }
}
function _visitsGap() {
  /* 距上一次来访（不含今天）隔了几天；首访/异常回 0。 */
  try {
    var _v = String(localStorage.getItem('visits') || '').split(',')
      .filter(Boolean);
    var _t0 = todayIso();
    var _prev = _v.filter(function (k) { return k < _t0; }).sort();
    if (!_prev.length) return 0;
    var _a = new Date(_prev[_prev.length - 1] + 'T00:00:00');
    var _b = new Date(_t0 + 'T00:00:00');
    return Math.round((_b - _a) / 86400000);
  } catch (e) { return 0; }
}
function _meFillAll() {
  _meFill('me', { y: 'year', m: 'month', d: 'day', h: 'hour', g: 'gender' });
  _meFill('me', { y: 'b_year', m: 'b_month', d: 'b_day', h: 'b_hour', g: 'b_gender', n: 'b_nick' });
  _meFill('me', { y: 'th_year', m: 'th_month', d: 'th_day', h: 'th_hour', g: 'th_gender' });
  /* R2348（R66-P2）：邀请链落地时受邀者=B 侧=本人——档案源要翻成 me
   * （原写死 me:partner，受邀者存的伴侣档多半就是发起人自己→两侧同盘）。 */
  if (window.__hhInviteMode) {
    /* R3242f：受邀者=B 侧=本人——昵称也该随 me.n 回填（原只填了
     * 生辰，受邀者每次还得手打自己名字）。 */
    _meFill('me', { y: 'hh_b_year', m: 'hh_b_month', d: 'hh_b_day', h: 'hh_b_hour', g: 'hh_b_gender', n: 'hh_b_name' });
  } else {
    /* R3242f：常态 A 侧=「我」——me.n 回填 hh_a_name（提交侧
     * a_name 本来就写 me.n，回填不同步会造成「存了却不带」。 */
    _meFill('me', { y: 'hh_a_year', m: 'hh_a_month', d: 'hh_a_day', h: 'hh_a_hour', g: 'hh_a_gender', n: 'hh_a_name' });
    /* R3161：昵称随档案回填——R3160 存的 TA 昵称再测合婚不丢。 */
    _meFill('me:partner', { y: 'hh_b_year', m: 'hh_b_month', d: 'hh_b_day', h: 'hh_b_hour', g: 'hh_b_gender', n: 'hh_b_name' });
  }
  try { _renderMeStrip(); } catch (e) {}
}
/* R231g（R39-P1-5）：「我的小档案」汇总行——存过生日的用户进首页
 * 就看到档案卡（生日自动代入的明示+打卡数+TA档案），点「改」开抽屉。 */
function _renderMeStrip() {
  var card = el('dailyCard');
  if (!card) return;
  var box = el('dailyMe');
  if (!box) {
    box = document.createElement('div');
    box.id = 'dailyMe'; box.className = 'daily-me';
    var meta = card.querySelector('.daily-meta');
    if (meta && meta.parentNode) {
      meta.parentNode.insertBefore(box, meta.nextSibling);
    } else { card.appendChild(box); }
  }
  var me = _meGet('me');
  if (!me || !me.y) { box.hidden = true; return; }
  var ck = 0;
  try {
    for (var i = 0; i < localStorage.length; i++) {
      var k = localStorage.key(i);
      if (k && k.indexOf('checkin:') === 0) ck++;
    }
  } catch (e) {}
  var partner = _meGet('me:partner');
  /* R233n（R47-Top5-4）：有昵称就喊名字——「小鱼的小档案」比
   * 「你的小档案」更像为她开的铺。 */
  var txt = '🧸 ' + (me.n ? me.n + ' 的小档案' : '你的小档案') +
    ' · ' + me.y + '年' + me.m + '月' + me.d + '日' +
    (me.lunar ? '（' + me.lunar + '）' : '') +
    '（测算时自动代入）';
  if (ck) txt += ' · 打过 ' + ck + ' 次卡';
  if (partner && partner.y) txt += ' · 也存了TA的';
  box.innerHTML = '<span class="daily-me-txt">' + esc(txt) + '</span>' +
    '<button type="button" class="daily-me-edit">改</button>';
  var btn = box.querySelector('.daily-me-edit');
  if (btn) btn.addEventListener('click', function () {
    var bd = el('birthDrawer');
    if (!bd) return;
    /* R233f（R43-P1-2）：抽屉在 #view-xingzuo 里——此前只给隐藏视图内
     * 的 details 置 open，用户只见一次莫名滚动（死钮）。先切视图再开。 */
    if (typeof showView === 'function') showView('xingzuo');
    bd.open = true;
    bd.scrollIntoView({behavior: _rmBehavior()});   /* R233k：reduced-motion 漏点 */
    var _fy = el('b_year');
    if (_fy) { try { _fy.focus({preventScroll:true}); } catch (e) {} }
  });
  box.hidden = false;
}
/* R231g（R39-P2-3）：聊天空态个性化——存过档案的用户，chips 换成
 * 跟自己相关的入口（本命盘/合不合/接着上次问）。 */
function _chatChipsPersonalize() {
  var box = document.getElementById('chatEmpty');
  if (!box) return;
  var chips = box.querySelectorAll('.chat-chip');
  if (!chips.length) return;
  var me = _meGet('me');
  /* R233n（R47-Top5-4）：有昵称，空态招呼喊名字。 */
  var _hi = box.querySelector('.chat-empty-hi');
  var _sub = box.querySelector('.chat-empty-sub');
  /* R2349t（R88-7/8/9）：空态招呼一次决策——时段 > 久归 > 昵称 >
   * 第 N 次，一次只出一句（深夜问心事是最高频也最脆弱的场景）。 */
  var _hh2 = new Date().getHours();
  var _gap2 = _visitsGap();
  var _nn2 = (me && me.n) || '';
  var _hiTxt = null;
  /* R2349z（R96-P2-1）：生日分支补进空态——封面/日签/打卡三处都有
   * 生日态，独漏这里；优先级最高（生日 > 时段 > 久归 > 昵称）。 */
  var _bday = false;
  try { _bday = _isMyBirthday(); } catch (eB) {}
  if (_bday) {
    _hiTxt = (_nn2 ? _nn2 + '，' : '') + '生日快乐 🎂 今天先给你占个彩头';
  } else if (_hh2 >= 23 || _hh2 < 5) {
    _hiTxt = (_nn2 ? _nn2 + '，' : '') + '夜深了，睡不着的话我在这儿 🌙';
  } else if (_hh2 >= 5 && _hh2 < 10) {
    _hiTxt = (_nn2 ? _nn2 + '，' : '') + '早啊，新的一天先看看运 ☀️';
  } else if (_gap2 > 3) {
    _hiTxt = (_nn2 ? _nn2 + '，' : '') + '好久没来了，最近怎么样 ✨';
  } else if (_nn2) {
    _hiTxt = _nn2 + '，我是小满 ✨';
  } else if (_visitCount() > 3) {
    _hiTxt = '第 ' + _visitCount() + ' 次来坐～今天想看点什么 ✨';
  }
  if (_hi && _hiTxt) _hi.textContent = _hiTxt;
  /* R3263（R21）：记忆显化——聊天空态顶部列出最近 3 条事由，
   * 让用户直接感知「小满记得」。只显示有记录时。 */
  /* R3264（R26）：记忆芯片可点击——点击事由预填输入框，
   * 用户可以直接续聊该话题。 */
  try {
    var _mems = _chatTopicsArr().slice(-3).reverse();
    var _memEl = box.querySelector('.chat-empty-memory');
    if (_mems.length) {
      if (!_memEl) {
        _memEl = document.createElement('p');
        _memEl.className = 'chat-empty-memory';
        var _cbox4 = box.querySelector('.chat-empty-chips');
        if (_cbox4 && _cbox4.parentNode) {
          _cbox4.parentNode.insertBefore(_memEl, _cbox4);
        } else { box.appendChild(_memEl); }
      }
      _memEl.innerHTML = '📌 小满记得你提过：' +
        _mems.map(function (x) {
          return '<button type="button" class="chat-empty-chip" ' +
            'data-topic="' + esc(x.t) + '">' + esc(x.t) +
            '（' + x.d.slice(5).replace('-', '月') +
            '日）</button>';
        }).join('、');
      _memEl.querySelectorAll('.chat-empty-chip').forEach(function (b) {
        b.addEventListener('click', function () {
          var _inp = el('chatInput');
          if (!_inp) return;
          _inp.value = '小满，我还想聊聊' + this.dataset.topic + '的事';
          try { _inp.focus(); _inp.setSelectionRange(_inp.value.length, _inp.value.length); } catch (eF) {}
        });
      });
    } else if (_memEl) { _memEl.remove(); }
  } catch (eM3) {}
  /* R3264（R30）：7 天轻见面记录——只计数、不催促、不断裂惩罚。 */
  try {
    var _wv = _weekVisits();
    var _wvEl = box.querySelector('.chat-empty-week');
    if (_wv > 0) {
      if (!_wvEl) {
        _wvEl = document.createElement('p');
        _wvEl.className = 'chat-empty-week';
        var _cbox5 = box.querySelector('.chat-empty-chips');
        if (_cbox5 && _cbox5.parentNode) {
          _cbox5.parentNode.insertBefore(_wvEl, _cbox5);
        } else { box.appendChild(_wvEl); }
      }
      /* R3314（R3309-P2）：usage:d:* 按天去重计数，「次」虚——
       * 改成与数据口径一致的「天」。 */
      _wvEl.innerHTML = '🌾 这周小满陪了你 ' + _wv + ' 天 ' +
        '<button type="button" id="shareWeekly" class="chat-empty-chip">📊 生成本周小报</button>';
      var _sw = el('shareWeekly');
      if (_sw) _sw.addEventListener('click', function () {
        _shareWeekly();
      });
    } else if (_wvEl) { _wvEl.remove(); }
  } catch (eW2) {}
  /* R3264（R45）：主动 check-in 文案——根据上次打开距今天数，
   * 在聊天空态给小满一句「想你」问候。 */
  try {
    var _last = localStorage.getItem('usage:last') || '';
    var _ckEl = box.querySelector('.chat-empty-checkin');
    if (/^\d{4}-\d{2}-\d{2}$/.test(_last)) {
      var _diff = Math.round(
        (Date.parse(todayIso() + 'T00:00:00') - Date.parse(_last + 'T00:00:00')) / 86400000);
      if (_diff >= 1) {
        if (!_ckEl) {
          _ckEl = document.createElement('p');
          _ckEl.className = 'chat-empty-checkin';
          var _cbox5 = box.querySelector('.chat-empty-chips');
          if (_cbox5 && _cbox5.parentNode) {
            _cbox5.parentNode.insertBefore(_ckEl, _cbox5);
          } else { box.appendChild(_ckEl); }
        }
        var _ckTxt = _diff === 1 ? '🌾 昨天没见你，小满今天也在'
                    : _diff === 2 ? '🌾 两天没见你，小满这盏灯还亮着'
                    : '🌾 你不在的日子小满也在，今天想测什么？';
        _ckEl.textContent = _ckTxt;
      } else if (_ckEl) { _ckEl.remove(); }
    } else if (_ckEl) { _ckEl.remove(); }
  } catch (eC) {}
  /* R3264（R51）：心情→下一步推荐——按最近心情给轻推荐，
   * 把情绪日志和功能联动起来。 */
  try {
    /* R3314：读真心情键（mood:<date> 0-3），不是签运档 mood:lv。 */
    var _moodNow = _latestMoodIdx();
    var _msEl = box.querySelector('.chat-empty-suggest');
    var _suggest = {
      '0': '今天累的话，去解个梦缓缓 🌙',
      '1': '心平平的，抽张塔罗问问今天想躲什么 🃏',
      '2': '状态不错，翻翻日签把好运接住 ✨',
      '3': '今天心情亮，去黄历挑个好时辰开工 📅'
    };
    var _msTxt = _suggest[_moodNow] || '';
    if (_msTxt) {
      if (!_msEl) {
        _msEl = document.createElement('p');
        _msEl.className = 'chat-empty-suggest';
        var _cbox6 = box.querySelector('.chat-empty-chips');
        if (_cbox6 && _cbox6.parentNode) {
          _cbox6.parentNode.insertBefore(_msEl, _cbox6);
        } else { box.appendChild(_msEl); }
      }
      _msEl.textContent = _msTxt;
    } else if (_msEl) { _msEl.remove(); }
  } catch (eS) {}
  /* R3264（R31）：记忆事实板——让用户看见小满记住了什么。
   * 折叠块内列档案、最近事由、近 7 天心情、最常问的功能。 */
  try {
    /* R3336：聊过天后节点住在工具位——回到空态时归位重建。 */
    var _fb = document.querySelector('.chat-facts');
    if (!_fb) {
      _fb = document.createElement('details');
      _fb.className = 'chat-facts';
    }
    var _cbox6 = box.querySelector('.chat-empty-chips');
    if (_cbox6 && _cbox6.parentNode) {
      _cbox6.parentNode.insertBefore(_fb, _cbox6);
    } else { box.appendChild(_fb); }
    var _me2 = null;
    try { _me2 = _meGet('me'); } catch (eM) {}
    var _bd = (_me2 && _me2.y)
      ? _me2.y + '年' + _me2.m + '月' + _me2.d + '日' : '还没告诉我';
    var _topV = _usageTop() || '还没怎么聊';
    var _latestMood = _latestMoodIdx();
    var _moodTxt = _latestMood !== '' ? _MOOD_META[+_latestMood].t : '—';
    var _topicTxt = _chatTopicsArr().slice(-3).map(function (x) {
      return esc(x.t); }).join('、') || '—';
    /* R3264（R37）：记忆可忘——每个事实带「× 忘」按钮，
     * 用户可一键清掉单条记忆（生日/事由/心情），与小满隐私优先
     * 人设一致。 */
    var _rows = [
      { fk: 'birthday', label: '你的生日', value: esc(_bd) },
      { fk: 'topics', label: '最近提过', value: _topicTxt },
      { fk: 'mood', label: '最近心情', value: esc(_moodTxt) },
      { fk: 'usage', label: '你常问', value: esc(_topV) }];
    var _fbHtml = '<summary>🧸 小满知道这些</summary>' +
      '<div class="chat-facts-body">';
    _rows.forEach(function (r) {
      _fbHtml += '<div class="chat-fact-row"><span>' + esc(r.label) +
        '：' + r.value + '</span>' +
        (r.fk !== 'usage' ? '<button type="button" ' +
          'class="chat-fact-forget" data-fk="' + r.fk + '">× 忘</button>' : '') +
        '</div>';
    });
    _fbHtml += '</div>';
    _fb.innerHTML = _fbHtml;
    if (!_fb.dataset.bound) {
      _fb.dataset.bound = '1';
      _fb.addEventListener('click', function (ev) {
        var b = ev.target.closest('.chat-fact-forget');
        if (!b) return;
        var fk = b.dataset.fk;
        try {
          if (fk === 'birthday') {
            localStorage.removeItem('me');
            /* R3339（审-高）：×忘生日同病——内存档不清档案条照样
             * 渲染，直到刷新才真忘。 */
            try { delete (window.__meSessionMap || {}).me; } catch (eMM) {}
          }
          else if (fk === 'topics') localStorage.removeItem('chat:topics');
          else if (fk === 'mood') {
            localStorage.removeItem('mood:lv');
            localStorage.removeItem('mood:' + todayIso());
            localStorage.removeItem('moodlv:' + todayIso());
          }
        } catch (eC) {}
        showToast('小满记住了，这件事以后不提了', 'ok');
        _microCelebrate(b);
        _chatChipsPersonalize();
      });
    }
  } catch (eF) {}
  /* R3264（R33）：今日小确幸——只问一句话，本地保存 journal:<date>。 */
  try {
    /* R3336：同上——持久工具位与空态之间归位。 */
    var _jb = document.querySelector('.chat-journal');
    if (!_jb) {
      _jb = document.createElement('details');
      _jb.className = 'chat-journal';
    }
    var _cbox7 = box.querySelector('.chat-empty-chips');
    if (_cbox7 && _cbox7.parentNode) {
      _cbox7.parentNode.insertBefore(_jb, _cbox7);
    } else { box.appendChild(_jb); }
    var _jval = '';
    try { _jval = localStorage.getItem('journal:' + todayIso()) || ''; } catch (eJ) {}
    /* R3336（审-中）：小确幸只进不出——30 个键零回看。加「收过的小事」
     * 最近 10 条回看条（今天之下，写态/读态都挂）。 */
    var _jPast = [];
    try {
      for (var _ji = window.localStorage.length - 1; _ji >= 0; _ji--) {
        var _jk = window.localStorage.key(_ji);
        if (_jk && _jk.indexOf('journal:') === 0 &&
            _jk.slice(8) < todayIso()) {
          var _jv = window.localStorage.getItem(_jk);
          if (_jv) _jPast.push([_jk.slice(8), _jv]);
        }
      }
      _jPast.sort(function (a, b) { return a[0] < b[0] ? 1 : -1; });
    } catch (eJP) {}
    var _jPastHtml = _jPast.length
      ? '<div class="chat-journal-past">收过的小事：' +
        _jPast.slice(0, 10).map(function (e2) {
          return '<div class="chat-journal-item"><i>' +
            esc(e2[0].slice(5)) + '</i>' + esc(e2[1]) + '</div>';
        }).join('') + '</div>'
      : '';
    if (_jval) {
      _jb.innerHTML = '<summary>📝 今天一件小事</summary>' +
        '<div class="chat-journal-body">' +
        '<p class="chat-journal-done">今天的：' + esc(_jval) + '</p>' +
        _jPastHtml + '</div>';
    } else {
      _jb.innerHTML = '<summary>📝 今天一件小事</summary>' +
        '<div class="chat-journal-body">' +
        '<input id="journalInput" type="text" maxlength="40" ' +
        /* R3321-P3：仅 placeholder 作名——补 aria-label。 */
        'aria-label="写一件今天的小事" ' +
        'placeholder="比如「喝到了一杯好喝的茶」">' +
        '<button id="journalSave" type="button">记下</button>' +
        _jPastHtml + '</div>';
      var _jsBtn = el('journalSave');
      var _jsInp = el('journalInput');
      if (_jsBtn && _jsInp) {
        _jsBtn.addEventListener('click', function () {
          var v = _jsInp.value.trim();
          if (!v) return;
          /* R3336（审-中）：情绪自由文本过危机闸——「活着没意思」
           * 原样落键零承接是破口。命中不存、给承接句。 */
          if (feCrisis(v)) { showToast(_CRISIS_FE_REPLY, 'warn'); return; }
          try { localStorage.setItem('journal:' + todayIso(), v); } catch (eS) {}
          _jb.innerHTML = '<summary>📝 今天一件小事</summary>' +
            '<div class="chat-journal-body">' +
            '<p class="chat-journal-done">今天的：' + esc(String(v)) + '</p></div>';
          _microCelebrate(_jsBtn);
          showToast('小满替你收好今天的一件小事～' + '\n' + _identityPhrase(), 'ok');
        });
      }
    }
  } catch (eJ2) {}
  /* R3259（UX-STRATEGY-NEXT N1）：小满在店状态行——她有她自己的日子，
   * 不是等你点开才活的按钮。确定性按时段切文案。 */
  var _shop = box.querySelector('.chat-empty-shop');
  if (_shop) _shop.textContent = _xmShopLine();
  /* R3262（R18）：久归便签——你攒的色点小满替你收着。
   * 只在大于 3 天没来时挂一行，不打扰日常。 */
  try {
    var _mjTotal = 0;
    try {
      _mjTotal = Math.max(0, parseInt(localStorage.getItem('moodjar:total') || '0', 10) || 0);
    } catch (eMJT) {}
    var _mjNote = box.querySelector('.chat-empty-moodjar');
    if (_gap2 > 3 && _mjTotal > 0) {
      if (!_mjNote) {
        _mjNote = document.createElement('p');
        _mjNote.className = 'chat-empty-moodjar';
        var _cbox3 = box.querySelector('.chat-empty-chips');
        if (_cbox3 && _cbox3.parentNode) {
          _cbox3.parentNode.insertBefore(_mjNote, _cbox3);
        } else { box.appendChild(_mjNote); }
      }
      _mjNote.textContent = '你攒的 ' + _mjTotal +
        ' 个色点都在罐子里，小满替你收着';
    } else if (_mjNote) { _mjNote.remove(); }
  } catch (eMJ2) {}
  /* R3260（UX-PLAN-R6 R9）：深夜创可贴入口——23-05 点空态多一颗
   * 「带张创可贴走」钮，点出海报模态（一句能存图带走的话 +
   * 夜灯场景卡）。深夜用户要的不是功能是件小物。 */
  /* R3336：创可贴钮同被移栽——document 级找回归位，幂等判重照走。 */
  var _band = document.querySelector('.chat-empty-bandaid');
  /* R3261（R16）：水逆期创可贴全天供应——求助高峰不只在深夜。 */
  var _mercOn = false;
  try {
    _mercOn = !!(window.__lastDaily && window.__lastDaily.mercury &&
                 window.__lastDaily.mercury.on);
  } catch (eMC) {}
  if (_hh2 >= 23 || _hh2 < 5 || _mercOn) {
    if (!_band) {
      _band = document.createElement('button');
      _band.type = 'button';
      _band.className = 'chat-chip chat-empty-bandaid';
      _band.addEventListener('click', function () {
        /* R3261：水逆白天档用日间场景，深夜档用夜灯场景。 */
        var _nh = new Date().getHours();
        var _night = (_nh >= 23 || _nh < 5);
        var _im = new Image();
        _im.src = _night ? '/static/cream/bear-scene-bad.jpg'
                         : '/static/cream/bear-scene-mid.jpg';
        _im.onload = function () {
          downloadPoster({ _art: _im,
            _artCap: _night ? '今夜小夜灯' : '慢慢来的日子' },
            'bandaid');
        };
        _im.onerror = function () { downloadPoster({}, 'bandaid'); };
      });
    }
    /* R3336：归位——节点可能在工具位也可能在空态，幂等插回 chips 后。 */
    var _cbox3 = box.querySelector('.chat-empty-chips');
    if (_cbox3 && _cbox3.parentNode) {
      _cbox3.parentNode.insertBefore(_band, _cbox3.nextSibling);
    } else { box.appendChild(_band); }
    _band.textContent = (_hh2 >= 23 || _hh2 < 5)
      ? '🌙 带张创可贴走' : '🩹 带张创可贴走';
  } else if (_band && _band.parentNode === box) { _band.remove(); }
  /* R3260（UX-PLAN-R6）：小满便签——久未归（≥3 天没来）时，
   * 空态最上方多一张她留的字条。AI 陪伴产品的共识：主动关怀
   * 的正确形态是「写进会话的消息」而不是推送——这张便签只在她
   * 打开侧栏时在场，不弹窗不通知。久归 > 话题（那条事由记忆行
   * 在更下面管 ≥2 天回访）。 */
  var _note = box.querySelector('.chat-empty-note');
  var _noteTxt = null;
  /* 深夜不禁便签——「好久没来了」管的是缺席，夜语管的是时刻，
   * 两件事不冲突；只让位给生日（那天有更重要的招呼）。 */
  if (_gap2 >= 3 && !_bday) {
    try {
      var _tpn = _chatTopicsArr(), _tlast = null, _tlastD = '';
      _tpn.forEach(function (x) {
        if (x && x.d > _tlastD && typeof x.t === 'string') {
          _tlast = x.t; _tlastD = x.d;
        }
      });
      _noteTxt = _dayPick([
        '你有一阵没来了。不催你——签每天都替你收着，想看看就说一声',
        '好几天没见。铺子照开，你的位置一直留着',
        '这几天过得怎么样？路过就来坐坐，不用挑日子'
      ], 'note-gap');
      if (_tlast) {
        _noteTxt += '。上次你问起「' + _gSlice(_tlast, 6) +
          '」的事——后来顺不顺，想聊随时在';
        /* 便签已提了这事——下面 memo 行再说一遍就重复了 */
        box.dataset.noteTopic = _tlast;
      } else { delete box.dataset.noteTopic; }
    } catch (eNT) {}
  }
  if (_noteTxt) {
    if (!_note) {
      _note = document.createElement('div');
      _note.className = 'chat-empty-note';
      var _hiP = box.querySelector('.chat-empty-hi');
      if (_hiP && _hiP.parentNode) {
        _hiP.parentNode.insertBefore(_note, _hiP);
      } else { box.insertBefore(_note, box.firstChild); }
    }
    _note.innerHTML =
      '<span class="chat-empty-note-who">小满留的便签</span>' +
      '<span class="chat-empty-note-txt">' + esc(_noteTxt) + '</span>';
  } else if (_note) { _note.remove(); }
  if (_sub) {
    if (_bday) {
      _sub.textContent = '生日这天的签，是一年一次的限定款';
    } else if (_hh2 >= 23 || _hh2 < 5) {
      _sub.textContent = '深夜的问心事也有人接，想说就说';
    } else if (_gap2 > 3) {
      _sub.textContent = '这几天攒的运都给你留着呢';
    }
  }
  if (me && me.y) {
    chips[chips.length - 1].textContent = '看看我的本命盘';
    chips[chips.length - 1].setAttribute('data-ask', '帮我看看我的八字命盘');
  }
  var p = _meGet('me:partner');
  if (p && p.y && chips[1]) {
    chips[1].textContent = '我们俩最近合不合';
    chips[1].setAttribute('data-ask', '看看我和TA最近的缘分');
  }
  var hl = null;
  try { hl = (JSON.parse(localStorage.getItem('hlask') || '[]') || [])[0]; }
  catch (e) {}
  if (hl && hl.q && chips[0]) {
    chips[0].textContent = '接着上次：' + _gSlice(hl.q, 8);
    chips[0].setAttribute('data-ask', hl.q);
  }
  /* R3134（调研：测测「预置问题贴档案」）：chips 贴着刚出的结果卡——
   * 最新 LAST_RESULT 在 30 分钟内时，首 chip 换成该卡的追问
   * （判词刚出最容易想问的就是「那我怎么办/哪里会磨」）。 */
  var _FOLLOWUP = {
    hehun: '我们最可能为什么吵架、怎么磨',
    tarot: '这组牌最要我注意什么',
    liuyao: '这卦让我接下来先做什么',
    bazi: '我接下来的运往哪走',
    taohua: '我的桃花从哪个门进来',
    qiming: '这几个名字你最推哪个',
    xzm: '我们俩相处要注意什么',
    daily: '今天要留意什么',
    huangli: '今天做什么最顺',
    dream: '这个梦是在提醒我什么'
  };
  var _fk = null, _fts = 0;
  for (var _kv in LAST_RESULT) {
    var _e2 = LAST_RESULT[_kv];
    if (_e2 && _e2.json && (_e2.ts || 0) > _fts &&
        Date.now() - (_e2.ts || 0) < 30 * 60e3) {
      _fk = _kv; _fts = _e2.ts;
    }
  }
  if (_fk && _FOLLOWUP[_fk] && chips[0]) {
    var _fq = _FOLLOWUP[_fk];
    /* R3214：解梦追问带真实象征名——「这个梦是在提醒我什么」泛，
     * 「梦里那个『被追赶』和我最近什么关系」接得住。 */
    if (_fk === 'dream') {
      var _ds = ((((LAST_RESULT.dream || {}).json) || {}).symbols) || [];
      if (_ds.length && _ds[0].name) {
        _fq = '梦里那个「' + _ds[0].name + '」和我最近的事有关系吗';
      }
    }
    chips[0].textContent = _fq;
    chips[0].setAttribute('data-ask', _fq);
  }
  /* R3190：深夜/清晨做（噩）梦醒来的典型时刻——首 chip 还停在
   * 出厂「今天运势怎么样」就太不解风情；没被 hl 续聊/结果追问
   * 占用时换成梦的入口。 */
  if (chips[0] && (_hh2 >= 22 || _hh2 < 9) &&
      chips[0].textContent === '今天运势怎么样') {
    chips[0].textContent = '做了个梦，讲给你听 🌙';
    chips[0].setAttribute('data-ask', '我刚做了个梦，想讲给你听');
  }
  /* R3259（UX-STRATEGY-NEXT N4）：小满记忆——上次聊过的事由桶
   * （chatSend 里存的 chat:topics），隔 ≥2 天再开聊时空态底部
   * 多一行「上次你问起X的事——想再看看就说一声」。
   * 测测体验报告原话：跨会话记忆是「陌生人→电子闺蜜」的分水岭。 */
  try {
    var _memo = box.querySelector('.chat-empty-memo');
    /* R3260（实测抓到的死代码）：写入端 _chatTopicLog 存的是数组
     * [{d,t,v}]，这里却按 {主题:日期} 对象读——for-in 在数组上拿
     * 到的是下标、值是对象，全部跳闸，记忆行从未亮过。读回真实
     * 结构；顺道把「事由×今日签面」交叉尾巴补上（N4 原案）。 */
    var _tp2 = _chatTopicsArr();
    var _best = null, _bestD = '';
    _tp2.forEach(function (x) {
      if (!x || typeof x.t !== 'string' || !x.t ||
          typeof x.d !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(x.d))
        return;
      var _gap = Math.floor(
        (new Date(todayIso() + 'T00:00:00') - new Date(x.d + 'T00:00:00')) /
        86400000);
      if (_gap >= 2 && x.d > _bestD &&
          box.dataset.noteTopic !== x.t) { _best = x.t; _bestD = x.d; }
    });
    if (_best) {
      if (!_memo) {
        _memo = document.createElement('p');
        _memo.className = 'chat-empty-memo';
        var _cbox = box.querySelector('.chat-empty-chips');
        if (_cbox && _cbox.parentNode) {
          _cbox.parentNode.insertBefore(_memo, _cbox.nextSibling);
        } else { box.appendChild(_memo); }
      }
      var _mm = _bestD.slice(5).replace('-', '月') + '日';
      /* 事由×今日签面：顺日鼓励再聊，缓日先递杯热的——都实话实说。 */
      var _dlv = (window.__lastDaily && window.__lastDaily.level) || '';
      var _mtail = (_dlv === '吉' || _dlv === '小吉')
        ? '——今天签面偏顺，正好再聊聊'
        : (_dlv === '凶'
           ? '——今天签面偏缓，先喝杯热的再说'
           : '——想再看看就跟我说');
      _memo.textContent = '📌 上次你聊起' + _best + '的事（' + _mm +
        '）' + _mtail;
    } else if (_memo) { _memo.remove(); }
  } catch (eTP2) {}
  /* R3260（UX-PLAN-R6→R7）：未闭合事件跟进——「明天面试」这类话头
   * 隔天再问「怎么样了」。跟进行可以点：点了预填输入框，她只需
   * 补结局。出现在便签/记忆行之后，一条就够，不多嘴。 */
  try {
    var _evts = JSON.parse(localStorage.getItem('chat:events') || '[]');
    if (!Array.isArray(_evts)) _evts = [];
    var _fol = box.querySelector('.chat-empty-follow');
    var _pick = -1;
    for (var _ei = 0; _ei < _evts.length; _ei++) {
      var _ev = _evts[_ei];
      if (!_ev || _ev.closed || (_ev.asked || 0) >= 2) continue;
      if (Date.now() - (_ev.ts || 0) < 864e5) continue;
      if (_ev.lastAsk === todayIso()) continue;
      _pick = _ei; break;
    }
    if (_pick >= 0) {
      if (!_fol) {
        _fol = document.createElement('button');
        _fol.type = 'button';
        _fol.className = 'chat-empty-follow';
        var _cbox2 = box.querySelector('.chat-empty-chips');
        if (_cbox2 && _cbox2.parentNode) {
          _cbox2.parentNode.insertBefore(_fol, _cbox2);
        } else { box.appendChild(_fol); }
      }
      var _ek = _evts[_pick].k;
      _fol.textContent = '🔔 上次你说「' + _ek + '」——后来怎么样了';
      _fol.onclick = function () {
        var _in = el('chatInput');
        if (_in) {
          _in.value = '上次说「' + _ek + '」这事，';
          _in.focus();
        }
      };
      _evts[_pick].asked = (_evts[_pick].asked || 0) + 1;
      _evts[_pick].lastAsk = todayIso();
      /* R3339（审-中）：整表压写丢另一 tab 的事件——写前并集。 */
      _lsUnionWrite('chat:events', _evts,
        function (e) { return e && e.k; }, 10);
      window.__chatPendingEvt = _pick;
    } else if (_fol) { _fol.remove(); window.__chatPendingEvt = null; }
  } catch (eFL) {}
  /* R3260（UX-PLAN-R6 R10）：档案回访——命盘类结果 ≥14 天没再
   * 看时提醒一句（电子玄学复购调研：报告要「后续连接」，免费版
   * 对应「定期轻更新」的回访理由）。只挑档案感强的品类，
   * 日抛型（日签/塔罗/六爻）不算档案。 */
  try {
    var _arch = box.querySelector('.chat-empty-arch');
    var _ARCH = { bazi: '命盘', birth: '本命盘', hehun: '合盘' };
    var _ak = null, _ad = '', _adays = 0;
    Object.keys(_ARCH).forEach(function (vk) {
      var d0 = null;
      try { d0 = localStorage.getItem('rlast:' + vk); } catch (e0) {}
      if (!d0 || !/^\d{4}-\d{2}-\d{2}$/.test(d0)) return;
      var g = Math.floor(
        (new Date(todayIso() + 'T00:00:00') -
         new Date(d0 + 'T00:00:00')) / 864e5);
      if (g >= 14 && g > _adays) { _ak = vk; _ad = d0; _adays = g; }
    });
    if (_ak) {
      if (!_arch) {
        _arch = document.createElement('p');
        _arch.className = 'chat-empty-arch';
        box.appendChild(_arch);
      }
      _arch.textContent = '📋 你的' + _ARCH[_ak] + '上次看是 ' +
        _ad.slice(5).replace('-', '月') + '日（' + _adays +
        ' 天前）——换季了，想重新看看就点上面的卡';
    } else if (_arch) { _arch.remove(); }
  } catch (eAR) {}
}
/* R231g（R39-P1-4）：装到桌面提示——beforeinstallprompt 只在可装
 * 环境才触发（iOS Safari 不发此事件，天然不出现）。7 天内关过不再烦。 */
var _deferredInstall = null;
window.addEventListener('beforeinstallprompt', function (e) {
  e.preventDefault();
  _deferredInstall = e;
  /* R3264（R28）：显式「加到桌面」按钮——在首页露出来，
   * 用户可主动安装，不再只等 8s 后的横幅。 */
  try {
    var _ipw = el('installPwaWrap');
    if (_ipw) _ipw.hidden = false;
  } catch (e3) {}
  /* R2350d（R100-P1-3）：beforeinstallprompt 在首屏早期就发——
   * 左下角横幅会盖住刚渲染的日卡（主视觉位）。延迟到 8s 后、且
   * 只在首访兴趣建立后（留在 home）才出。 */
  setTimeout(function () {
    try { _renderInstallTip(); } catch (e2) {}
  }, 8000);
});
function _renderInstallTip() {
  if (el('installTip')) return;
  if (window.matchMedia &&
      window.matchMedia('(display-mode: standalone)').matches) return;
  /* R2349（R65-P1-4）：iOS Safari 不发 beforeinstallprompt——主受众
   * 是 iPhone，恰在最大盘上没引导。检测 iOS UA 给手动步骤提示。 */
  var _ios = /iP(hone|ad|od)/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (navigator.standalone === true) return;   /* iOS standalone 也不显示 */
  try {
    var ds = localStorage.getItem('installTipDismissed');
    if (ds && Date.now() - Date.parse(ds) < 7 * 864e5) return;
  } catch (e) {}
  /* R2350d（R100-P1-3 续）：当前不在 home 视图（已在别的功能页
   * 深度使用中）不打断。 */
  var _vv = document.querySelector('.view.active');
  if (_vv && _vv.id && _vv.id !== 'view-home') return;
  var bar = document.createElement('div');
  bar.className = 'install-tip'; bar.id = 'installTip';
  /* R233f（R43-P3-13）：静默出现读屏无感知——role=status 出现即播。 */
  bar.setAttribute('role', 'status');
  if (_ios) {
    /* R2349m（R76-P0-1）：iOS 微信 webview 无底部分享栏也没有
     * 「添加到主屏幕」——原 Safari 指引是条死路。三分支：
     * 微信→右上角···去 Safari 打开；Safari→底部分享；其他 iOS
     * webview→同微信口径引导去 Safari。 */
    var _wx = /MicroMessenger/i.test(navigator.userAgent);
    /* R2353（R110-P2-4）：小红书 webview「···」菜单是「在浏览器打开」，
     * 通用 iOS 口径「复制链接去 Safari」不准——补 XHS 分支。 */
    var _xhs = /xhsdiscover|XHSAPP|discover\//i.test(navigator.userAgent);
    var _isSafari = /Safari/i.test(navigator.userAgent) &&
      !/CriOS|FxiOS|EdgiOS|MicroMessenger|QQ/i.test(navigator.userAgent);
    bar.innerHTML = '<span>🏠 ' +
      (_wx ? '点右上「···」→「在 Safari 打开」，再点分享→加到主屏幕'
           : _xhs ? '点右上「···」→「在浏览器打开」，再点分享→加到主屏幕'
           : _isSafari ? '点底部「分享」→「添加到主屏幕」，明天直接来'
           : '复制链接去 Safari 打开，再「添加到主屏幕」') + '</span>' +
      '<button type="button" class="install-tip-go">知道了</button>' +
      '<button type="button" class="install-tip-x" aria-label="先不了">✕</button>';
  } else {
    bar.innerHTML = '<span>🏠 把小满放进桌面，明天直接来</span>' +
      '<button type="button" class="install-tip-go">装好</button>' +
      '<button type="button" class="install-tip-x" aria-label="先不了">✕</button>';
  }
  var go = bar.querySelector('.install-tip-go');
  var xx = bar.querySelector('.install-tip-x');
  /* R2349h（R69-P2-7）：自毁前先还焦点到功能区落点。 */
  var _retire = function () {
    var _nx = el('funcGrid');
    if (_nx && _nx.focus) { try { _nx.focus(); } catch (e) {} }
    bar.remove();
  };
  if (go) go.addEventListener('click', function () {
    if (!_deferredInstall) { _retire(); return; }
    var d = _deferredInstall; _deferredInstall = null;
    try { d.prompt(); } catch (e) {}
    _retire();
  });
  if (xx) xx.addEventListener('click', function () {
    try { localStorage.setItem('installTipDismissed', new Date().toISOString()); }
    catch (e) {}
    _retire();
  });
  document.body.appendChild(bar);
}
/* 用户手动输入即解除预填标记——下次 _meFill 不再碰这个字段 */
['input', 'change'].forEach(function (ev) {
  document.addEventListener(ev, function (e) {
    if (e.target && e.target.dataset) {
      /* R2501：记住用户是否实际碰过本 tab 的字段。select 改回首项后
       * selectedIndex 又回到 0，单看值会误判为“仍未动过”。 */
      if (['INPUT', 'SELECT', 'TEXTAREA'].indexOf(e.target.tagName) >= 0) {
        e.target.dataset.touched = '1';
      }
      if (e.target.dataset.me) {
        delete e.target.dataset.me;
      }
    }
  }, true);
});
/* R2364（R119-P1-3）：多 Tab 串改——别的标签页改了档案（me/me:partner），
 * 本页仍带 data-me 预填标的字段显示的是旧值，提交会拿串改值合盘。
 * 原生 storage 事件跨 Tab 触发：把这类字段的结果容器标陈旧提示。 */
window.addEventListener('storage', function (e) {
  if (e.key !== 'me' && e.key !== 'me:partner') return;
  document.querySelectorAll('[data-me]').forEach(function (f) {
    if (f.id) _markStale(f.id);
  });
});
/* R233p：签墙渲染——最近 21 个打卡日倒序，每格 M/D + 签面，
 * 点击格 toast 当日反馈句。 */
function _renderCheckinAlbum(dateKey) {
  var host = document.getElementById('checkinAlbum');
  if (!host) return;
  var all = _checkinAll();
  if (!Object.keys(all).length) {
    host.innerHTML = '<div class="ck-album-empty">签册还空着，抽一签就开张</div>';
    return;
  }
  /* R2350c（R97-P2-3）：原只渲有签日——断签月的缺口在网格里不
   * 存在，「集满」拉力弱。改锚今天回看 21 槽：有签日可点出签句，
   * 缺签日灰槽悬停「这天没来」，尾部附 N/21 进度。 */
  var html = '<div class="ck-album-grid" role="list">';
  var _hit = 0;
  for (var _b = 20; _b >= 0; _b--) {
    var dk = _isoShift(dateKey, -_b);
    var opt = all[dk];
    var pp = String(dk).split('-');
    if (opt) {
      var fb = pickCheckinFeedback(opt, dk);
      _hit++;
      /* R2349h（R69-P1-4）：role=listitem 会把原生 button 语义吃掉——
       * SR 只报「列表项」不报可激活。格仍由父级 role=list 承载语义。 */
      /* R3253：签册图鉴化——有签日挂签面熊缩略图，攒签从
       * 「攒一串字」变成「集一册图」（集卡心是留存硬钩）。 */
      var _a = CHECKIN_ART[opt]
        ? '<img class="ck-alb-art" src="/static/cream/' + CHECKIN_ART[opt] +
          '.jpg" alt="" loading="lazy" decoding="async" ' +
          'onerror="this.remove()">'
        : '';
      html += '<button type="button" class="ck-album-cell" ' +
        'data-fb="' + esc(fb) + '" title="' + esc(dk) + '　' + esc(fb) + '">' +
        '<i>' + esc(pp[1] || '') + '/' + esc(pp[2] || '') + '</i>' + _a +
        '<b>' + esc(opt) + '</b></button>';
    } else {
      html += '<span class="ck-album-cell ck-album-miss" ' +
        'title="' + esc(dk) + '　这天没来"><i>' +
        esc(pp[1] || '') + '/' + esc(pp[2] || '') + '</i><b>·</b></span>';
    }
  }
  host.innerHTML = html + '</div>' +
    '<div class="ck-album-prog">近 21 天攒了 ' + _hit + '/21' +
    (_hit >= 21 ? '，集满啦 🎉' : '') + '</div>';
}
function pickCheckinFeedback(opt, dateKey) {
  const pool = CHECKIN_FEEDBACK[opt] || CHECKIN_FEEDBACK._default || [];
  let h = 0; const s = String(dateKey) + opt;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  /* R39-P0-5：打卡完成的瞬间是植「明天再来」的黄金位——句尾按日轮换
   * 一句收口。 */
  /* R2349g（R68-P1-2）：closers 3→7 句、盐位与 body 拆开（原同 hash
   * 同模，body/closer 同步重复）——整句组合数翻约 2.3 倍。 */
  var closers = ['明天再来挑一个～', '连签路上，明天见 🌱',
                 '明天也给自己挑个好运搭子吧', '明天的小满也在等你',
                 '攒着好运，明天继续', '这签先收好，明天再抽',
                 '明天见，签筒一直在'];
  var h2 = (h * 2654435761) >>> 0;
  /* R2345（R59-leftover）：存过昵称就喊名字——打卡是最日常的触点，
   * 「小鱼，今天这签挑得妙」比无主语更像陪伴。 */
  var _nick = '';
  try {
    var _me = _meGet('me');
    _nick = (_me && _me.n) ? _meNickClean(_me.n) : '';
  } catch (e) {}
  return (_nick ? _nick + '，' : '') +
    (pool[h % Math.max(1, pool.length)] || '') +
    '　' + closers[h2 % closers.length];
}

/* R2350j（R107-Top5-4）：许愿瓶 lite——localStorage 单愿望封存，
 * 无后端。结构 {t: 愿望文, c: 分类, ts: 毫秒戳}。 */
var _WISH_CATS = ['感情', '事业', '学业', '财运', '健康', '小秘密'];
function _wishGet() {
  try {
    var w = JSON.parse(localStorage.getItem('wishbottle') || 'null');
    return (w && typeof w.t === 'string' && w.t) ? w : null;
  } catch (e) { return null; }
}
function _wishSet(w) {
  try { localStorage.setItem('wishbottle', JSON.stringify(w)); } catch (e) {}
}
function _wishClear() {
  try { localStorage.removeItem('wishbottle'); } catch (e) {}
}
function _wishDays(w) {
  var ts = (w && +w.ts) || Date.now();
  return Math.max(0, Math.floor((Date.now() - ts) / 86400000));
}
/* R3337：愿望回音——「成真啦」不再是删掉愿望，而是收进成真集
 * wishfulfilled（[{t,c,ts,fu}]，cap 30）：还愿的仪式感是许愿的
 * 正反馈闭环——愿望有结局，瓶子才敢再丢。 */
var _ECHO_LINES = [
  '成了就是成了，这个愿望下班啦',
  '愿望到货——你等它的这些天没白等',
  '它兑现了。给自己记一笔',
  '许愿→成真，这条链你走通了一次',
  '瓶子没白躺，它帮你存到今天'
];
function _wishEchoGet() {
  try {
    var a = JSON.parse(localStorage.getItem('wishfulfilled') || '[]');
    return Array.isArray(a) ? a : [];
  } catch (e) { return []; }
}
function _wishEchoAdd(w) {
  try {
    var a = _wishEchoGet();
    a.unshift({ t: w.t, c: w.c, ts: w.ts, fu: Date.now() });
    /* R3339（审-中）：写前并集——unshift 新头型 head-cap 保新。 */
    _lsUnionWrite('wishfulfilled', a,
      function (x) { return x && (String(x.ts) + '|' + String(x.fu)); },
      30);
  } catch (e) {}
}
function _wishEchoStrip() {
  var a = _wishEchoGet();
  if (!a.length) return '';
  var html = '<div class="ck-wish-echolist">✨ 成真集 · ' + a.length +
    ' 个愿望成了';
  for (var i = 0; i < Math.min(5, a.length); i++) {
    html += '<div class="ck-wish-echo-item">「' + esc(a[i].t) +
      '」<b>成了</b></div>';
  }
  return html + '</div>';
}
function _wishSummary() {
  var w = _wishGet();
  var en = _wishEchoGet().length;
  var tail = en ? '，还愿 ×' + en : '';
  if (!w) return (en ? '（' : '，写个愿望丢进去') +
    (en ? '还愿 ×' + en + '）' : '');
  var d = _wishDays(w);
  return '（' + (d === 0 ? '今天刚丢的' : '愿望躺了 ' + d + ' 天') +
    tail + '）';
}
function _renderWishBottle(edit) {
  var host = document.getElementById('wishBottleBody');
  if (!host) return;
  var w = _wishGet();
  if (w && !edit) {
    var d = _wishDays(w);
    host.innerHTML =
      '<div class="ck-wish-card">' +
        '<div class="ck-wish-meta">' + esc(w.c || '小秘密') + ' · ' +
          (d === 0 ? '今天丢进来的' : '躺了 ' + d + ' 天') + '</div>' +
        '<div class="ck-wish-text">「' + esc(w.t) + '」</div>' +
        '<div class="ck-wish-meta">' + esc(_dayPick([
          '它还在这儿，等你哪天来认领',
          '愿望说出口才算数——你说出来了',
          '躺着躺着，说不定哪天就成真了', '瓶子帮你记着，你只管往前走'],
          'wish|' + (w.ts || 0))) + '</div>' +
        '<div class="ck-wish-actions">' +
          '<button type="button" class="checkin-opt" data-wish="done">成真啦 🎉</button>' +
          '<button type="button" class="checkin-opt" data-wish="edit">换个愿望</button>' +
          '<button type="button" class="checkin-opt" data-wish="keep">继续躺着</button>' +
        '</div></div>' +
      _wishEchoStrip();
    return;
  }
  host.innerHTML =
    '<div class="ck-wish-card">' +
      '<textarea id="wishText" class="ck-wish-input" maxlength="60" rows="2" ' +
        /* R3321-P3：仅 placeholder 作名——输入后名丢，补 aria-label。 */
        'aria-label="写一个愿望" ' +
        'placeholder="比如：希望下个月面试顺利…">' +
        esc(w ? w.t : '') + '</textarea>' +
      /* R2514（审-P2）：分类 chips 此前只有 picked class——选中态
       * 不进无障碍树（rtab/hl-chip/checkin-opt 全站都有 aria-pressed）。
       * 补 aria-pressed + role=group。 */
      '<div class="ck-wish-cats" role="group" aria-label="愿望分类">' +
        _WISH_CATS.map(function (c) {
        var _pk = !!(w && w.c === c);
        return '<button type="button" class="checkin-opt' +
          (_pk ? ' picked' : '') + '" aria-pressed="' + _pk +
          '" data-wish="cat" data-arg="' +
          esc(c) + '">' + esc(c) + '</button>';
      }).join('') + '</div>' +
      '<div class="ck-wish-actions">' +
        '<button type="button" class="checkin-opt" data-wish="save">丢进瓶子 🫙</button>' +
      '</div>' +
      '<div class="ck-wish-meta">只有你的浏览器记得它，写给自己看的</div>' +
    '</div>' +
    _wishEchoStrip();
}
function _renderWishEcho(w) {
  /* 还愿卡——愿望被点「成真啦」后的一瞬庆祝画面。 */
  var host = document.getElementById('wishBottleBody');
  if (!host) return;
  host.innerHTML =
    '<div class="ck-wish-card ck-wish-echo">' +
      '<div class="ck-wish-stamp">成了</div>' +
      '<div class="ck-wish-text">「' + esc(w.t) + '」</div>' +
      '<div class="ck-wish-meta">' + esc(_dayPick(_ECHO_LINES,
        'echo|' + (w.fu || 0))) + '</div>' +
      '<div class="ck-wish-actions">' +
        '<button type="button" class="checkin-opt" data-wish="new">再许一个 🫙</button>' +
      '</div></div>' +
    _wishEchoStrip();
}
function _wishRefreshSummary() {
  var s = document.querySelector('#dailyCheckin .ck-wish summary');
  if (s) s.innerHTML = '🫙 许愿瓶' + _wishSummary();
}
function _wishAction(act, arg, dateKey) {
  if (act === 'cat') {
    var host = document.getElementById('wishBottleBody');
    if (!host) return;
    var chips = host.querySelectorAll('.ck-wish-cats .checkin-opt');
    for (var i = 0; i < chips.length; i++) {
      var _on = chips[i].dataset.arg === arg &&
        !chips[i].classList.contains('picked');
      chips[i].classList.toggle('picked', _on);
      chips[i].setAttribute('aria-pressed', _on ? 'true' : 'false');   /* R2514 */
    }
    return;
  }
  if (act === 'save') {
    var ta = document.getElementById('wishText');
    var t = ta ? ta.value.trim() : '';
    if (!t) { showToast('先写点什么再丢进去～', 'warn'); return; }
    /* R3336（审-中）：许愿瓶自由文本过危机闸。 */
    if (feCrisis(t)) { showToast(_CRISIS_FE_REPLY, 'warn'); return; }
    var cat = '';
    var host2 = document.getElementById('wishBottleBody');
    var sel = host2 ? host2.querySelector('.ck-wish-cats .checkin-opt.picked') : null;
    if (sel) cat = sel.dataset.arg || '';
    _wishSet({ t: t.slice(0, 60), c: cat || '小秘密', ts: Date.now() });
    showToast(_dayPick(['瓶子收好了，等它慢慢发酵',
                       '愿望已封存，过几天再来看看',
                       '装进瓶子啦，今天起算'], 'wishs'), 'info');
    _renderWishBottle();
    _wishRefreshSummary();
    return;
  }
  if (act === 'done') {
    var w0 = _wishGet();
    if (!w0) { _renderWishBottle(); return; }
    _wishEchoAdd(w0);
    _wishClear();
    showToast('替你开心 🎉 已收进成真集', 'info');
    _renderWishEcho({ t: w0.t, fu: Date.now() });
    _wishRefreshSummary();
    return;
  }
  if (act === 'edit' || act === 'new') { _renderWishBottle(true); return; }
  if (act === 'keep') {
    showToast(_dayPick(['好，让它再躺会儿', '愿望继续躺着，你也继续',
                       '瓶子盖好了，回头见'], 'wishk'), 'info');
  }
}

/* R3350：肯定语收集册——今日咒语行尾 ❤️ 收进「我的咒语册」。
 * mantraFav=[{t:咒语原文,d:收藏日ISO,ts}] cap 40，去重键 t|d
 * （同句跨天算新一条——每天那句是那一页）。结构照抄 wishfulfilled：
 * 备份 _EXACT、wipe 清单、导入白名单+形状校验、跨 tab storage
 * 监听；全本机零 API 零台账。 */
var _MANTRA_FAV_TOAST = [
  '收好啦，这句以后归你',
  '存进咒语册了，想它随时翻',
  '这句话今天跟你走',
  '好句配好日子，收下了',
  '收进册子啦，攒着攒着就是一本小书'
];
function _mantraFavAll() {
  try {
    var a = JSON.parse(localStorage.getItem('mantraFav') || '[]');
    return Array.isArray(a) ? a : [];
  } catch (e) { return []; }
}
function _mantraFavHas(t, d) {
  return _mantraFavAll().some(function (x) {
    return x && x.t === t && x.d === d; });
}
function _mantraFavAdd(t, d) {
  try {
    var a = _mantraFavAll();
    a.unshift({ t: t, d: d, ts: Date.now() });
    /* 写前并集同 wishfulfilled——unshift 新头型 head-cap 保新，
     * 满 40 最旧的让位出册。 */
    _lsUnionWrite('mantraFav', a,
      function (x) { return x && (String(x.t) + '|' + String(x.d)); },
      40);
  } catch (e) {}
}
function _mantraFavDel(ts) {
  try {
    var a = _mantraFavAll().filter(function (x) {
      return x && String(x.ts) !== String(ts); });
    localStorage.setItem('mantraFav', JSON.stringify(a));
  } catch (e) {}
}
/* ── R3376 显化打卡环 ──────────────────────────────────────────
 * 「今日念一遍」记 manifest:<YYYY-MM-DD>=1——每天念咒语的连续
 * 天数进咒语册头与首页 meta。今天没念时从昨天往回数（断签前
 * 的连胜仍活着）。 */
function _manifestDone(d) {
  try { return localStorage.getItem('manifest:' + d) === '1'; }
  catch (e) { return false; }
}
function _manifestStreak() {
  var n = 0, t = new Date();
  if (!_manifestDone(todayIso())) t.setDate(t.getDate() - 1);
  for (;;) {
    var ds = t.getFullYear() + '-' +
      String(t.getMonth() + 1).padStart(2, '0') + '-' +
      String(t.getDate()).padStart(2, '0');
    if (!_manifestDone(ds)) break;
    n++;
    if (n > 400) break;
    t.setDate(t.getDate() - 1);
  }
  return n;
}
/* R3378：连念里程碑档（3/7/14/30/60/100）——与连签 _checkinCelebrate
 * 同档；今天已念过返回 0，否则返回新连胜数让调用方决定文案。 */
var _MANIFEST_MILES = {
  3: '三天连成线，咒语开始长在你身上',
  7: '整一周天天念，愿望在路上',
  14: '十四天连念，心诚则灵',
  30: '满月连念，坚持发光',
  60: '六十天连念，稳定得像月亮',
  100: '百日连念，你是镇铺之宝'
};
function _manifestMark() {
  var _was = _manifestDone(todayIso());
  try { localStorage.setItem('manifest:' + todayIso(), '1'); }
  catch (e) {}
  return _was ? 0 : _manifestStreak();
}
function _mantraFavSync(t, d) {
  /* 今日咒语行尾钮——同句今日已收显「已收」实心态。 */
  var b = el('mantraFav');
  if (!b) return;
  if (!t) { b.hidden = true; return; }
  var got = _mantraFavHas(t, d);
  b.hidden = false;
  b.textContent = got ? '❤️ 已收' : '🤍';
  b.classList.toggle('got', got);
  b.setAttribute('aria-pressed', got ? 'true' : 'false');
  b.title = got ? '这句已经在咒语册里啦' : '把这句收进咒语册';
  b.setAttribute('aria-label', got ? '今日咒语已收藏' : '收藏今日咒语');
}
function _mantraBookMeta() {
  /* 册入口——日卡 meta 行小链，攒了才现身（空册不占地）。
   * R3376：连念天数并进小链（念环的每日钩）。 */
  var n = _mantraFavAll().length;
  var _mst0 = n ? _manifestStreak() : 0;
  _dailyMetaItem('dailyMantraBook', n
    ? '<button type="button" class="mantra-book-link" id="mantraBookGo">' +
      '📖 咒语册 · 已攒 ' + n + ' 句' +
      (_mst0 ? ' · 连念 ' + _mst0 + ' 天' : '') + '</button>'
    : '');
  var g = el('mantraBookGo');
  if (g && !g.dataset.bound) {
    g.dataset.bound = '1';
    g.addEventListener('click', function () {
      try { showView('mantra'); } catch (eG) {}
    });
  }
}
function _renderMantraBook() {
  /* 只在册页在屏时渲——storage 跨 tab 同步也走这里，早退零成本。 */
  var vw = el('view-mantra');
  if (!vw || !vw.classList.contains('active')) return;
  var body = el('mantraBookBody');
  if (!body) return;
  var a = _mantraFavAll();
  if (!a.length) {
    body.innerHTML = '<div class="ph-empty">册子还空着呢——' +
      '看到喜欢的那句，点旁边的小心心 🤍 就收进来啦</div>';
  } else {
    /* R3376 显化打卡环：「今日念一遍」——点过记 manifest:<date>
     * 并把今日咒语顺手进剪贴板；连念天数进册头。 */
    var _mst = _manifestStreak(), _mdone = _manifestDone(todayIso());
    body.innerHTML = '<div class="mb-count">攒了 <strong>' + a.length +
      '</strong> 句 · 满 40 最旧的先出册</div>' +
      '<div class="mb-ritual"><button type="button" class="mb-today' +
        (_mdone ? ' got' : '') + '" data-mb="today"' +
        (_mdone ? ' disabled' : '') + '>' +
        (_mdone ? '✅ 今日已念' : '📿 今日念一遍') +
        (_mst ? ' · 连念 ' + _mst + ' 天' : '') + '</button>' +
        (_mdone ? ''
               : '<span class="mb-rit-tip">点一下，今天的咒语顺手帮你复制</span>') +
      '</div>' +
      '<div class="mb-grid">' +
      a.map(function (x) {
        return '<div class="mb-cell">' +
          '<div class="mb-t">「' + esc(x.t) + '」</div>' +
          /* R3362（R3361 审-P2）：ISO 日期裸贴与全站「10月4日」
           * 口径不一；「再念一遍」名不符实（实际是复制）。 */
          '<div class="mb-d">' + esc(String(x.d || '')
            .replace(/^(\d{4})-(\d{1,2})-(\d{1,2}).*/,
              function (_, y, m, d) {
                return (+m) + '月' + (+d) + '日（' + y + '）';
              })) + ' 收的</div>' +
          '<div class="mb-acts">' +
            '<button type="button" class="mb-act" data-mb="copy" data-ts="' +
              esc(String(x.ts)) + '" title="复制这句">存个档</button>' +
            '<button type="button" class="mb-act mb-del" data-mb="del" ' +
              'data-ts="' + esc(String(x.ts)) +
              '" title="从咒语册删掉" aria-label="删除这条咒语">请出册子</button>' +
          '</div></div>';
      }).join('') + '</div>';
  }
  /* 委托绑在容器上（innerHTML 重渲不掉绑定）——copy/del 同链路。 */
  if (!body.dataset.bound) {
    body.dataset.bound = '1';
    body.addEventListener('click', function (ev) {
      var b = ev.target && ev.target.closest
        ? ev.target.closest('[data-mb]') : null;
      if (!b) return;
      var act = b.dataset.mb, ts = b.dataset.ts;
      if (act === 'today') {
        var _stNew = _manifestMark();
        try {
          var _mt3 = el('dailyMantra');
          var _mtxt = (_mt3 && _mt3.dataset)
            ? String(_mt3.dataset.m || '') : '';
          if (_mtxt && navigator.clipboard &&
              navigator.clipboard.writeText) {
            navigator.clipboard.writeText(_mtxt).catch(function () {});
          }
        } catch (eMT) {}
        showToast(
          _stNew && _MANIFEST_MILES[_stNew]
            ? '📿 连念 ' + _stNew + ' 天达成——' +
              _MANIFEST_MILES[_stNew] + '，明天接着来'
            : '今日咒语念过一遍啦——明天接着来', 'ok');
        _renderMantraBook();
        _mantraBookMeta();
        return;
      }
      if (act === 'copy') {
        var _hitItem = _mantraFavAll().filter(function (x) {
          return x && String(x.ts) === String(ts); })[0];
        if (!_hitItem) return;
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(String(_hitItem.t)).then(
              function () { showToast('咒语复制好啦，去贴上吧', 'ok'); },
              function () { showToast('长按那句手动复制', 'warn'); });
          } else { throw new Error('no clipboard'); }
        } catch (eMC2) { showToast('长按那句手动复制', 'info'); }
        return;
      }
      if (act === 'del') {
        _mantraFavDel(ts);
        _renderMantraBook();
        _mantraBookMeta();
        /* 删的若是今天这句，行尾钮翻回可收态。 */
        try {
          var _mt2 = el('dailyMantra');
          if (_mt2) {
            _mantraFavSync(String(_mt2.dataset.m || ''),
                           String(_mt2.dataset.d || todayIso()));
          }
        } catch (eMS) {}
        showToast('这句先请出册子啦', 'info');
      }
    });
  }
}

/* R3381（调研·裂变引擎）：默契挑战——我答 5 题生成 hash 邀请链，
 * 朋友打开答题自动对分+可晒图+回敬新链。答案全程走 location.hash
 * （不进服务器日志/链接预览爬虫），本机只记你的昵称 mochi:nick。 */
/* init() 在 defer 脚本 eval 中途跑——数据若用 var 赋值则深链落地
 * 时尚未初始化。改用函数声明，hoist 连函数体一起可用。 */
/* R3386 双题库：闺蜜版(bestie) + 对象版(love)。pack 挂在 hash
 * v1 第 4 字段/v2 第 6 字段——旧链没 pack 自动闺蜜版向后兼容。 */
function _mcQS(pack) {
  if (pack === 'love') {
    return [
      { q: '约会最想去？', o: ['咖啡馆窝着', '出门爬山', '宅家点外卖', '看展/演出'] },
      { q: '吵架后谁先低头？', o: ['我先', 'TA 先', '看谁占理', '冷静完自然好'] },
      { q: '最戳心的礼物？', o: ['手写的信', '实用好物', '贵重心意', '一场旅行'] },
      { q: '理想的一周见面频率？', o: ['天天见', '两三天一回', '一周一回', '各自忙有空聚'] },
      { q: '睡前最想听 TA 说？', o: ['晚安我爱你', '今天辛苦了', '明天见', '别玩了快睡'] }
    ];
  }
  return [
    { q: '奶茶点几分糖？', o: ['无糖清口', '三分刚好', '五分甜', '全糖快乐'] },
    { q: '理想的周末是？', o: ['宅家充电', '出门撒野', '睡到自然醒再说'] },
    { q: 'TA 迟到 10 分钟，你？', o: ['有点气', '没事我也刚到', '我比 TA 还晚'] },
    { q: '睡前最后一件事？', o: ['再刷会儿手机', '想明天穿啥', '听点小歌'] },
    { q: '下雨天最想？', o: ['窝在被窝里', '出门踩水', '来杯热乎的'] }
  ];
}
function _mcPackOf(p) { return p === 'love' ? 'love' : 'bestie'; }
function _mcTIERS() {
  return [
    [5, '灵魂搭子', '五题全中——你们共享一个脑回路'],
    [4, '很懂彼此', '就一道没对上，已经很会了'],
    [3, '舒服的朋友', '一半的默契，剩下的慢慢了解'],
    [2, '还在互相猜', '差异才是聊天的素材'],
    [0, '平行宇宙', '完全互补型——你们是彼此的另一面']
  ];
}
function _mcEnc(s) {
  try {
    return btoa(unescape(encodeURIComponent(String(s))))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  } catch (e) { return ''; }
}
function _mcDec(s) {
  try {
    s = String(s).replace(/-/g, '+').replace(/_/g, '/');
    while (s.length % 4) s += '=';
    return decodeURIComponent(escape(atob(s)));
  } catch (e) { return ''; }
}
function _mcParse() {
  var h = '';
  try { h = String(location.hash || ''); } catch (e) {}
  var m = h.match(/^#(mc|mcr)=([A-Za-z0-9_-]+)/);
  /* #mc=/#mcr= 前缀在而载荷对不上（字符集/截断）——是弄丢的挑战书，
   * 不该静默回落出题卡让人误以为链是自己发的。 */
  if (!m) return /^#mc[rs]?=/.test(h) ? { mode: 'bad' } : null;
  var p = _mcDec(m[2]).split('|');
  if (m[1] === 'mc' && p[0] === 'v1' && /^[0-3]{5}$/.test(p[2] || '')) {
    return { mode: 'guest', nick: String(p[1] || '').slice(0, 12),
             ans: p[2], pack: _mcPackOf(p[3]) };
  }
  if (m[1] === 'mcr' && p[0] === 'v2' && /^[0-3]{5}$/.test(p[3] || '') &&
      /^[0-3]{5}$/.test(p[4] || '')) {
    return { mode: 'result', hn: String(p[1] || '').slice(0, 12),
             gn: String(p[2] || '').slice(0, 12), ha: p[3], ga: p[4],
             pack: _mcPackOf(p[5]) };
  }
  return { mode: 'bad' };
}
function _mcScore(ha, ga) {
  var hits = 0, matched = [], missed = [];
  for (var i = 0; i < _mcQS().length; i++) {
    var a = +ha[i], b = +ga[i];
    if (a === b) { hits++; matched.push(i); } else { missed.push(i); }
  }
  var tier = _mcTIERS()[_mcTIERS().length - 1];
  for (var t = 0; t < _mcTIERS().length; t++) {
    if (hits >= _mcTIERS()[t][0]) { tier = _mcTIERS()[t]; break; }
  }
  return { hits: hits, pct: Math.round(hits / _mcQS().length * 100),
           tier: tier[1], line: tier[2], matched: matched,
           missed: missed };
}
function _mcCompareHtml(hn, gn, ha, ga, pack) {
  var s = _mcScore(ha, ga);
  var rows = _mcQS(pack).map(function (q, i) {
    var a = q.o[+ha[i]] || '—', b = q.o[+ga[i]] || '—';
    var ok = (+ha[i] === +ga[i]);
    return '<div class="mc-row' + (ok ? ' hit' : '') + '">' +
      '<div class="mc-row-q">' + (ok ? '💞' : '🍃') + ' ' + esc(q.q) +
      '</div><div class="mc-row-a">' + esc(hn) + '：' + esc(a) +
      '<br>' + esc(gn) + '：' + esc(b) + '</div></div>';
  }).join('');
  return '<div class="mc-score"><b>' + s.pct + '%</b><span>' +
    esc(hn) + ' × ' + esc(gn) + ' · ' + esc(s.tier) + '</span>' +
    '<p>' + esc(s.line) + '</p></div>' + rows;
}
/* R3383 谁最懂你榜：受邀者回传的成绩条按昵称落本机榜——
 * 出题人视角看「哪个朋友最懂我」，攒榜=再发新挑战的留存钩。
 * 走 mochi: 前缀，备份/跨账号清扫同族收编，纯本机不上服务器。 */
function _mcBoard() {
  var a = [];
  try { a = JSON.parse(localStorage.getItem('mochi:board') || '[]'); }
  catch (e) {}
  return Array.isArray(a) ? a.filter(function (x) {
    return x && typeof x.n === 'string' && typeof x.s === 'number';
  }) : [];
}
function _mcBoardSave(a) {
  try {
    localStorage.setItem('mochi:board', JSON.stringify(a.slice(0, 20)));
  } catch (e) {}
}
/* 只有「我是这份挑战的出题人」才记榜——路过的看客打开成绩条
 * 不污染榜。同昵称重答只更新最新分不占新坑。返回名次（0 起）。 */
function _mcBoardRecord(hn, gn, pct) {
  var me = '';
  try { me = localStorage.getItem('mochi:nick') || ''; } catch (e) {}
  if (!me || me !== hn || !gn) return -1;
  var a = _mcBoard(), i;
  for (i = 0; i < a.length; i++) {
    /* R3395-P2-4：result 渲染会调此函数——同分重写属渲染副作用，
     * 同值 setItem 虽不发 storage 事件，但变化写会让邻 tab 重渲
     * 再写（回环）。同分早退，只让真正的新分落键。 */
    if (a[i].n === gn && a[i].s === pct) return i;
    if (a[i].n === gn) { a[i].s = pct; a[i].t = Date.now(); break; }
  }
  if (i >= a.length) a.push({ n: gn, s: pct, t: Date.now() });
  a.sort(function (x, y) { return (y.s - x.s) || (y.t - x.t); });
  _mcBoardSave(a);
  for (i = 0; i < a.length; i++) { if (a[i].n === gn) return i; }
  return -1;
}
function _mcBoardHtml() {
  var a = _mcBoard();
  if (!a.length) return '';
  var medals = ['🥇', '🥈', '🥉'];
  var rows = a.slice(0, 8).map(function (e, i) {
    return '<div class="mc-brow"><span class="mc-bmedal">' +
      (medals[i] || String(i + 1)) + '</span><b>' + esc(e.n) +
      '</b><span class="mc-bs">' + Math.round(e.s) + ' 分</span></div>';
  }).join('');
  return '<div class="mc-board"><div class="mc-btitle">🏆 谁最懂你' +
    '<span class="mc-bcount">' + a.length + ' 位应战</span>' +
    '<button type="button" class="mc-bwipe" data-mc="bshare">📸 晒榜</button>' +
    '<button type="button" class="mc-bwipe" data-mc="wipe">清空</button>' +
    '</div>' + rows + '</div>';
}
function _mcQuizHtml(ctx) {
  var _pk = (ctx && ctx.pack) || 'bestie';
  var qs = _mcQS(_pk).map(function (q, i) {
    return '<div class="mc-q" id="mochiQ' + i + '">' +
      '<div class="mc-q-t">' + (i + 1) + '. ' + esc(q.q) + '</div>' +
      '<div class="mc-opts">' + q.o.map(function (o, j) {
        return '<button type="button" class="mc-opt" data-mc="opt" ' +
          'data-q="' + i + '" data-o="' + j + '">' + esc(o) + '</button>';
      }).join('') + '</div></div>';
  }).join('');
  if (!ctx || !ctx.hostAns) {
    var nick = '';
    try { nick = localStorage.getItem('mochi:nick') || ''; } catch (eN) {}
    return '<div class="mc-head">挑你会选的答案——答完生成挑战书发给 TA，' +
      '看 TA 有多懂你</div>' +
      '<div class="mc-packs">' +
      '<button type="button" class="mc-pack' + (_pk === 'bestie' ? ' on' : '') +
      '" data-mc="pack" data-pack="bestie">🧋 出给闺蜜</button>' +
      '<button type="button" class="mc-pack' + (_pk === 'love' ? ' on' : '') +
      '" data-mc="pack" data-pack="love">💗 出给对象</button></div>' +
      '<label class="mc-nick-lab" for="mochiNick">你叫什么（对方会看到）</label>' +
      '<input id="mochiNick" class="mc-nick" maxlength="12" ' +
      'placeholder="比如：小满 / 桃子" value="' + esc(nick) + '">' + qs +
      '<div id="mochiBar" class="mc-bar">已答 0/5</div>' +
      '<button type="button" id="mochiMake" class="mc-go" data-mc="make" ' +
      'disabled>生成默契挑战书 🥤</button>';
  }
  return '<div class="mc-head">「<b>' + esc(ctx.who || 'TA') +
    '</b>」给你出了一套' +
    (_pk === 'love' ? '心动' : '') + '默契题' +
    (_pk === 'love' ? '<span class="mc-packtag">对象题</span>' : '') +
    '——凭直觉答，别纠结</div>' + qs +
    '<div id="mochiBar" class="mc-bar">已答 0/5</div>' +
    '<button type="button" id="mochiDone" class="mc-go" data-mc="done" ' +
    'disabled>看我们的默契分</button>';
}
function _mcAnsRead(box) {
  var ans = '     '.split('');
  box.querySelectorAll('.mc-opt.on').forEach(function (b) {
    var q = +b.dataset.q;
    if (q >= 0 && q < 5) ans[q] = b.dataset.o;
  });
  return ans.join('');
}
function _renderMochi() {
  var box = el('mochiBox');
  if (!box) return;
  var st = _mcParse();
  if (st && st.mode === 'bad') {
    box.innerHTML = '<div class="ph-empty">这份挑战书在路上弄丢了——' +
      '让 TA 重发一份给你吧</div>';
    return;
  }
  if (st && st.mode === 'result') {
    var _sc2 = _mcScore(st.ha, st.ga);
    var _rk = _mcBoardRecord(st.hn, st.gn, _sc2.pct);
    var _rkLine = '';
    if (_rk >= 0) {
      var _bn = _mcBoard().length;
      _rkLine = '<p class="mc-rank">你收到的 ' + _bn +
        ' 份答卷里，TA 排第 <b>' + (_rk + 1) + '</b></p>';
    }
    box.innerHTML = '<div class="mc-head">「<b>' + esc(st.gn || 'TA') +
      '</b>」答完了「' + esc(st.hn || '你') + '」的' +
      (st.pack === 'love' ? '心动默契题' : '默契题') + '</div>' +
      _mcCompareHtml(st.hn || '出题人', st.gn || '答题人', st.ha, st.ga,
                     st.pack) +
      _rkLine +
      '<div class="mc-acts">' +
      '<button type="button" id="mochiShare" class="mc-go" ' +
      'data-mc="share">📸 晒这张成绩条</button>' +
      '<button type="button" id="mochiHost" class="ghost" ' +
      'data-mc="host">我也出一套题</button></div>';
    try {
      box.dataset.ga = st.ga; box.dataset.ha = st.ha;
      box.dataset.hn = st.hn || 'TA'; box.dataset.gn = st.gn || 'TA';
      box.dataset.pack = st.pack || 'bestie';
    } catch (eRD) {}
    return;
  }
  box.innerHTML = _mcBoardHtml() +
    _mcQuizHtml(st && st.mode === 'guest'
      ? { who: st.nick, hostAns: st.ans, pack: st.pack }
      : { pack: box.dataset.pack || 'bestie' });
}
/* 委托绑容器——innerHTML 重渲不掉绑定。 */
(function () {
  var box = document.getElementById('mochiBox');
  if (!box) return;
  box.addEventListener('click', function (ev) {
    var b = ev.target && ev.target.closest
      ? ev.target.closest('[data-mc]') : null;
    if (!b) return;
    var act = b.dataset.mc;
    if (act === 'pack') {
      /* 题库不同保留已选答案无意义——切题=重出，只护住昵称输入。 */
      try {
        box.dataset.nick = (el('mochiNick') || {}).value || '';
        box.dataset.pack = b.dataset.pack || 'bestie';
      } catch (ePK) {}
      _renderMochi();
      var _nk = el('mochiNick');
      if (_nk && box.dataset.nick) _nk.value = box.dataset.nick;
      return;
    }
    if (act === 'opt') {
      var q = b.dataset.q;
      box.querySelectorAll('#mochiQ' + q + ' .mc-opt').forEach(
        function (x) { x.classList.remove('on'); });
      b.classList.add('on');
      var done = _mcAnsRead(box).replace(/ /g, '').length;
      var bar = el('mochiBar');
      if (bar) bar.textContent = '已答 ' + done + '/5';
      ['mochiMake', 'mochiDone'].forEach(function (id) {
        var g = el(id);
        if (g) g.disabled = (done < 5);
      });
      return;
    }
    var st = _mcParse();
    if (act === 'make') {
      var nick = '';
      try {
        /* R3395-P1-2：昵称里的 | 是载荷字段分隔符——不剔会拼出
         * 死链（受邀方落地出「弄丢了」卡，host 无感知）。 */
        nick = String((el('mochiNick') || {}).value || '')
          .replace(/\|/g, '').trim().slice(0, 12);
      } catch (eN1) {}
      if (!nick) {
        showToast('先写个名字——对方答题时要看到是谁出的', 'warn');
        return;
      }
      var ans = _mcAnsRead(box);
      if (ans.indexOf(' ') !== -1) return;
      try { localStorage.setItem('mochi:nick', nick); } catch (eN2) {}
      var link = location.origin + '/?view=mochi#mc=' +
        _mcEnc('v1|' + nick + '|' + ans + '|' +
               (box.dataset.pack || 'bestie'));
      box.innerHTML = '<div class="mc-head">挑战书包好啦——' +
        '发给 TA，看 TA 有多懂你</div>' +
        '<input id="mochiLink" class="mc-link" readonly ' +
        'value="' + esc(link) + '">' +
        '<div class="mc-acts">' +
        '<button type="button" id="mochiCopy" class="mc-go" ' +
        'data-mc="copy">复制挑战书 🔗</button>' +
        '<button type="button" id="mochiHost" class="ghost" ' +
        'data-mc="host">重新出一套</button></div>' +
        '<p class="mc-note">答案跟着链接走，不上服务器；' +
        'TA 答完会自动对分</p>';
      return;
    }
    if (act === 'done' && st && st.mode === 'guest') {
      var ga = _mcAnsRead(box);
      if (ga.indexOf(' ') !== -1) return;
      var s = _mcScore(st.ans, ga);
      var mn = '';
      try { mn = localStorage.getItem('mochi:nick') || ''; } catch (eM) {}
      box.innerHTML = '<div class="mc-head">你和「<b>' +
        esc(st.nick || 'TA') + '</b>」的默契结果出来啦</div>' +
        _mcCompareHtml(st.nick || 'TA', '你', st.ans, ga, st.pack) +
        '<label class="mc-nick-lab" for="mochiMe">你叫什么' +
        '（发成绩给 TA 时显示）</label>' +
        '<input id="mochiMe" class="mc-nick" maxlength="12" ' +
        'placeholder="比如：桃子" value="' + esc(mn) + '">' +
        '<div class="mc-acts">' +
        '<button type="button" id="mochiShare" class="mc-go" ' +
        'data-mc="share">📸 晒默契分</button>' +
        '<button type="button" id="mochiFlip" class="mc-go" ' +
        'data-mc="flip">发给 TA 看成绩</button>' +
        '<button type="button" id="mochiHost2" class="ghost" ' +
        'data-mc="host">我也出一套给 TA</button></div>';
      try { box.dataset.ga = ga; box.dataset.ha = st.ans;
            box.dataset.hn = st.nick || 'TA';
            box.dataset.pack = st.pack || 'bestie'; } catch (eD) {}
      return;
    }
    if (act === 'copy') {
      var lk = el('mochiLink');
      var v = lk ? lk.value : '';
      if (!v) return;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(v).then(function () {
            showToast('挑战书复制好啦，去发给 TA 吧', 'ok');
          }, function () { showToast('长按链接手动复制', 'warn'); });
        } else {
          if (lk.select) lk.select();
          showToast('长按链接手动复制', 'info');
        }
      } catch (eC) { showToast('长按链接手动复制', 'info'); }
      return;
    }
    if (act === 'share') {
      var _d = box.dataset || {};
      var _ga2 = _d.ga || '', _ha2 = _d.ha || '', _hn2 = _d.hn || 'TA';
      if (!_ga2 || !_ha2) return;
      var gn2 = _d.gn || String((el('mochiMe') || {}).value || '').trim()
        .slice(0, 12) || '我';
      var s2 = _mcScore(_ha2, _ga2);
      return downloadPoster({
        _mc: { hn: _hn2, gn: gn2, pct: s2.pct, tier: s2.tier,
               line: s2.line,
               matched: s2.matched.map(function (i) {
                 return _mcQS(_d.pack)[i].q.replace(/[？?]$/, ''); }),
               missed: s2.missed.map(function (i) {
                 return _mcQS(_d.pack)[i].q.replace(/[？?]$/, ''); }) },
        date: todayIso() }, 'mochi');
    }
    if (act === 'flip') {
      var _d2 = box.dataset || {};
      if (!_d2.ga || !_d2.ha) return;
      var gn3 = String((el('mochiMe') || {}).value || '')
        .replace(/\|/g, '').trim().slice(0, 12);
      if (!gn3) {
        showToast('先写你的名字——TA 打开要知道是谁答的', 'warn');
        return;
      }
      try { localStorage.setItem('mochi:nick', gn3); } catch (eN3) {}
      var rlink = location.origin + '/?view=mochi#mcr=' +
        _mcEnc('v2|' + (_d2.hn || 'TA') + '|' + gn3 + '|' +
               _d2.ha + '|' + _d2.ga + '|' + (_d2.pack || 'bestie'));
      var card = '<div class="mc-head">成绩条包好啦——发回去，' +
        '让 TA 看看你们多默契</div>' +
        '<input id="mochiLink" class="mc-link" readonly ' +
        'value="' + esc(rlink) + '">' +
        '<div class="mc-acts">' +
        '<button type="button" id="mochiCopy" class="mc-go" ' +
        'data-mc="copy">复制成绩条 🔗</button>' +
        '<button type="button" id="mochiHost2" class="ghost" ' +
        'data-mc="host">我也出一套给 TA</button></div>';
      box.innerHTML = card;
      return;
    }
    if (act === 'bshare') {
      var _ba = _mcBoard();
      if (!_ba.length) { showToast('榜还空着——先发挑战给 TA 们', 'info'); return; }
      var _bhn = '';
      try { _bhn = localStorage.getItem('mochi:nick') || '我'; } catch (eBH) {}
      return downloadPoster({
        _mcb: { hn: _bhn, n: _ba.length,
                rows: _ba.slice(0, 8).map(function (e) {
                  return { n: e.n, s: Math.round(e.s) }; }) },
        date: todayIso() }, 'mochi');
    }
    if (act === 'wipe') {
      try { localStorage.removeItem('mochi:board'); } catch (eW) {}
      showToast('榜清空啦', 'ok');
      _renderMochi();
      return;
    }
    if (act === 'host') {
      try {
        if (location.hash) {
          history.replaceState(null, '', location.pathname +
            location.search);
        }
      } catch (eH) {}
      _renderMochi();
      return;
    }
  });
  /* 同视图内 hash 变化（贴了新链）即重渲。 */
  window.addEventListener('hashchange', function () {
    var vw = el('view-mochi');
    if (vw && vw.classList.contains('active')) _renderMochi();
  });
})();

/* R3388：每日一签——观音灵签百签真本（卜易居籤版系）。
 * 语料懒载 /static/qian_data.js → window.QIAN（83KB 不堵首屏）。
 * 同日同签：qian:<iso> 存签号——一天里重抽还是那一支
 * （与掷筊「同一件事今天再掷也是这个筊」同口径）；
 * 连下签暖心调节：昨+前连续两支 low，今天池子剔 low——
 * 观音不忍心看你连着低（签小签同款机制，贴安抚基调）。
 * 历史：qian:hist JSON [{d,n}] 倒序 30 条，备份/wipe/GC 走 qian: 前缀。 */
var _qianJsLoad = null;
function _qianData(cb) {
  if (window.QIAN) { cb(); return; }
  if (!_qianJsLoad) {
    _qianJsLoad = new Promise(function (res, rej) {
      var s = document.createElement('script');
      s.src = '/static/qian_data.js' + _assetSuffix();
      s.onload = function () { res(); };
      s.onerror = function () {
        _qianJsLoad = null;
        rej(new Error('签文没加载上：网好了再点一次'));
      };
      document.head.appendChild(s);
    });
  }
  _qianJsLoad.then(function () { cb(); }).catch(function (e) {
    /* R3396-P2-10：懒载挂掉时别只剩一闪的 toast——签页写内联
     * 空态（ph-empty 惯例），点「重试」重新进视图即重拉。 */
    toast(e && e.message ? e.message : '签文没加载上');
    var _bx = document.getElementById('qianBox');
    if (_bx) _bx.innerHTML =
      '<div class="ph-empty" style="text-align:center;padding:28px;">' +
      '<div style="font-size:32px;">🎋</div>' +
      '<div>签文没加载上——检查下网再试</div>' +
      '<button class="mc-go" type="button" onclick="_renderQian()" ' +
      'style="margin-top:10px;">重试</button></div>';
  });
}
function _qianIdxOf(dk) {
  try {
    var v = parseInt(localStorage.getItem('qian:' + dk) || '', 10);
    return (v >= 1 && v <= 100) ? v : 0;
  } catch (e) { return 0; }
}
function _qianHist() {
  try {
    var h = JSON.parse(localStorage.getItem('qian:hist') || '[]');
    return Array.isArray(h) ? h.filter(function (x) {
      return x && typeof x.d === 'string' && x.n >= 1 && x.n <= 100;
    }).slice(0, 30) : [];
  } catch (e) { return []; }
}
/* R3391：问事签——抽签前选所问（不求甚解的随缘也可）。话题随签
 * 进卡面/海报/聊上下文；qian:t:<date> 日期键随 qian: 族进
 * GC/wipe/备份三链。 */
var _QIAN_TOPICS = ['随缘', '感情', '事业', '财运', '学业', '健康', '家宅'];
var _qianPickedTopic = '随缘';
function _qianTopic(dk) {
  try {
    var t = localStorage.getItem('qian:t:' + dk) || '';
    return _QIAN_TOPICS.indexOf(t) > 0 ? t : '';
  } catch (e) { return ''; }
}
function _qianDraw(topic) {
  var dk = todayIso(), had = _qianIdxOf(dk);
  if (had) return had;  /* 今天的签已抽过——同一支 */
  var pool = [];
  for (var i = 0; i < QIAN.length; i++) pool.push(i + 1);
  /* 连下签调节：回看昨/前两天的签，连 low 则今天剔 low 池。 */
  var lows = 0;
  for (var back = 1; back <= 2; back++) {
    var d = new Date(); d.setDate(d.getDate() - back);
    var dk2 = d.getFullYear() + '-' +
      String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0');
    var idx2 = _qianIdxOf(dk2);
    if (idx2 && QIAN[idx2 - 1] && QIAN[idx2 - 1].tier === 'low') lows++;
    else break;
  }
  if (lows >= 2) {
    pool = pool.filter(function (n) { return QIAN[n - 1].tier !== 'low'; });
  }
  var n = pool[Math.floor(Math.random() * pool.length)];
  try {
    localStorage.setItem('qian:' + dk, String(n));
    if (topic && topic !== '随缘')
      localStorage.setItem('qian:t:' + dk, topic);
    var h = _qianHist();
    h.unshift({ d: dk, n: n });
    localStorage.setItem('qian:hist', JSON.stringify(h.slice(0, 30)));
  } catch (e) {}
  _qianFactWrite(n);
  return n;
}
/* R3390：当日签面事实——聊签话题经 _chatFacts 注入。独立小键
 * 而非现读 QIAN：懒载语料没落页时（今天抽过但没进签页）仍能注。 */
function _qianFactWrite(n) {
  try {
    var q = QIAN[n - 1]; if (!q) return;
    var tp = _qianTopic(todayIso());
    localStorage.setItem('qian:fact', JSON.stringify({
      d: todayIso(),
      t: '她今天在小满铺「每日一签」' + (tp ? '问' + tp + '事' : '') +
         '抽到第' + n + '签（' + q.luck + '·' + q.name +
         '），签诗：「' + q.poem.join('，') +
         '」；她想聊签就照这支的意思说，不懂就带她去签页细看'
    }));
  } catch (e) {}
}
function _qianSlipHtml(n, opts) {
  var q = QIAN[n - 1]; if (!q) return '';
  var o = opts || {};
  var _luckCls = q.tier === 'top' ? 'q-top' : (q.tier === 'mid' ? 'q-mid' : 'q-low');
  var _tp = _qianTopic(o.review ? o.review : todayIso());
  var h = '<div class="qian-slip' + (o.review ? ' is-review' : '') + '">';
  if (o.review) {
    h += '<div class="qian-review-tag">📅 ' + esc(o.review) + ' 抽的那支</div>';
  }
  h += '<div class="qian-head"><span class="qian-no">第' + n + '签</span>' +
       (_tp ? '<span class="qian-topic-tag">问' + esc(_tp) + '</span>' : '') +
       '<span class="qian-luck ' + _luckCls + '">' + esc(q.luck) + '</span></div>' +
       '<div class="qian-name">' + esc(q.name) + ' · ' + esc(q.gong) + '</div>' +
       '<div class="qian-poem">' +
       q.poem.map(function (l) { return '<div>' + esc(l) + '</div>'; }).join('') +
       '</div>' +
       '<div class="qian-say">💬 ' + esc(q.say) + '</div>' +
       '<details class="qian-det"><summary>解曰与典故</summary>' +
       '<div class="qian-det-body">' +
       '<div class="qian-yi">' + esc(q.yi) + '</div>' +
       '<div class="qian-jie">' + esc(q.jie) + '</div>' +
       (q.story ? '<div class="qian-story"><b>典故</b> ' + esc(q.story) + '</div>' : '') +
       '</div></details>';
  h += '<div class="qian-acts">' +
       /* R3396-P2-2：回看签的晒图带被回看日期——海报日期/话题应
        * 取签那天，不取今天。 */
       '<button class="mc-go" type="button" data-qian="share" data-n="' + n + '"' +
       (o.review ? ' data-d="' + esc(o.review) + '"' : '') + '>' +
       '📸 晒这支签</button>' +
       (o.review
         ? '<button class="ghost" type="button" data-qian="back">回到今天的签</button>'
         : '<div class="qian-note">今天的签不会变——明天再来抽一支</div>') +
       '</div></div>';
  return h;
}
function _qianHistHtml() {
  var h = _qianHist(); if (!h.length) return '';
  var rows = h.slice(0, 7).map(function (x, i) {
    var q = window.QIAN ? QIAN[x.n - 1] : null;
    if (!q) return '';
    var md = x.d.slice(5).replace('-', '月') + '日';
    return '<button class="qian-hrow" type="button" data-qian="hist" data-n="' + x.n +
           '" data-d="' + esc(x.d) + '"><span>' + esc(md) + '</span>' +
           '<span>第' + x.n + '签 · ' + esc(q.luck) + '</span>' +
           '<span class="qian-hname">' + esc(q.name) + '</span></button>';
  }).join('');
  return '<div class="qian-hist"><div class="qian-htitle">最近抽过的签</div>' +
         rows + '</div>';
}
function _renderQian(review) {
  var qnBoxEl = document.getElementById('qianBox'); if (!qnBoxEl) return;
  _qianData(function () {
    var dk = todayIso(), idx = _qianIdxOf(dk);
    if (review && review.n) {
      qnBoxEl.innerHTML = _qianSlipHtml(review.n, { review: review.d }) +
        _qianHistHtml();
      return;
    }
    if (idx) {
      _qianFactWrite(idx);
      qnBoxEl.innerHTML = _qianSlipHtml(idx) + _qianHistHtml();
      return;
    }
    var _chips = _QIAN_TOPICS.map(function (t) {
      return '<button type="button" class="qian-tpick' +
        (t === _qianPickedTopic ? ' is-on' : '') +
        '" data-qian="topic" data-t="' + esc(t) + '">' + esc(t) + '</button>';
    }).join('');
    qnBoxEl.innerHTML =
      '<div class="qian-tube" id="qianTube">' +
        '<div class="qian-tube-img" aria-hidden="true">🎋</div>' +
        '<div class="qian-tube-t">心里默念一件想问的事</div>' +
        '<div class="qian-tube-s">观音灵签一百签 · 真签文真典故</div>' +
        '<div class="qian-topics">' + _chips + '</div>' +
        '<button class="mc-go qian-draw" type="button" data-qian="draw">' +
        '摇一支今日签</button>' +
        '<div class="qian-note">一天一支——今天的签抽了就不会变</div>' +
      '</div>' + _qianHistHtml();
  });
}
(function _qianBind() {
  document.addEventListener('click', function (e) {
    var b = e.target && e.target.closest
      ? e.target.closest('[data-qian]') : null;
    if (!b) return;
    var act = b.dataset.qian;
    if (act === 'topic') {
      _qianPickedTopic = b.dataset.t || '随缘';
      b.parentNode.querySelectorAll('.qian-tpick').forEach(function (x) {
        x.classList.toggle('is-on', x === b);
      });
    } else if (act === 'draw') {
      var tube = document.getElementById('qianTube');
      if (tube) tube.classList.add('is-shaking');
      b.disabled = true;
      /* 摇签仪式感：筒晃 ~1.1s 再出签——「等一等才出来」是仪式本体。 */
      setTimeout(function () {
        _qianDraw(_qianPickedTopic);
        _renderQian();
      }, 1100);
    } else if (act === 'hist') {
      var n2 = parseInt(b.dataset.n || '0', 10);
      if (n2) _renderQian({ n: n2, d: b.dataset.d || '' });
    } else if (act === 'back') {
      _renderQian();
    } else if (act === 'share') {
      var n3 = parseInt(b.dataset.n || '0', 10);
      var q3 = window.QIAN && QIAN[n3 - 1];
      if (!q3) return;
      var _sd = (b.dataset.d && /^\d{4}-\d{2}-\d{2}$/.test(b.dataset.d))
        ? b.dataset.d : todayIso();
      downloadPoster({ _qian: {
          n: n3, name: q3.name, luck: q3.luck,
          poem: q3.poem, say: q3.say,
          topic: _qianTopic(_sd) },
        date: _sd }, 'qian');
    }
  });
})();

/* R3335：烦恼粉碎机——写下来的烦心事当场粉碎，原文永不落盘
 * （隐私即卖点：碎掉就是真没了），只累计当天件数 shred:<date>。
 * 件数是纯计数不迁移：不进备份（换机不带这种一次性痕迹），
 * 进 wipe 清单与 150 天 GC。 */
var _SHRED_SOOTHE = [
  '碎啦——这事从今天起不归你管了',
  '纸都碎了，它压不住你了',
  '扔出去的东西不用捡回来',
  '行了，翻篇。今天剩下的是你的',
  '碎干净了。喝口水，这页不翻了',
  '它配不上你的好心情——已粉碎',
  '到此为止，这件事从你的清单上划掉了',
  '碎完了。烦人的事不值得过夜',
  '帮你处理掉了，别回头捡',
  '纸屑都吹走了，你也往前走走'
];
function _shredCount(dateKey) {
  try {
    /* R3354（审-低）：负值计数原样透出「碎了 -5 件」——取 0 下限。 */
    return Math.max(0, parseInt(localStorage.getItem('shred:' + dateKey) || '0', 10) || 0);
  } catch (e) { return 0; }
}
function _shredRefreshSummary(dateKey) {
  var s = document.getElementById('shredSum');
  if (!s) return;
  var n = _shredCount(dateKey || todayIso());
  s.textContent = n ? '，今天碎了 ' + n + ' 件' : '';
}
function _renderShredder(stage) {
  var host = document.getElementById('shredBody');
  if (!host) return;
  var dk = todayIso();
  var n = _shredCount(dk);
  if (stage === 'done') {
    host.innerHTML =
      '<div class="ck-wish-card">' +
        '<div class="ck-shred-done">🗑️ ' +
          esc(_dayPick(_SHRED_SOOTHE, 'shred|' + dk + '|' + n)) + '</div>' +
        '<div class="ck-wish-meta">' +
          (n > 1 ? '今天一共碎了 ' + n + ' 件，手挺快' :
                  '原文没存任何地方——碎了就真没了') + '</div>' +
        '<div class="ck-wish-actions">' +
          '<button type="button" class="checkin-opt" data-shred="again">再碎一件</button>' +
          '<button type="button" class="checkin-opt" data-shred="wish">顺手丢个愿望 🫙</button>' +
        '</div></div>';
    return;
  }
  host.innerHTML =
    '<div class="ck-wish-card">' +
      '<textarea id="shredText" class="ck-wish-input" maxlength="120" rows="3" ' +
        'aria-label="写下压着的事" ' +
        'placeholder="压着你的事写下来——写完就碎，小满不留档"></textarea>' +
      '<div class="ck-wish-actions">' +
        '<button type="button" class="checkin-opt" data-shred="go">碎掉它 🗑️</button>' +
      '</div>' +
      (n ? '<div class="ck-wish-meta">今天已经碎了 ' + n + ' 件</div>' :
           '<div class="ck-wish-meta">写完的内容不会存任何地方</div>') +
    '</div>';
  var ta = document.getElementById('shredText');
  if (ta) ta.focus();
}
function _shredAction(act, dateKey) {
  var host = document.getElementById('shredBody');
  if (!host) return;
  if (act === 'again') { _renderShredder(); return; }
  if (act === 'wish') {
    var w = document.querySelector('#dailyCheckin .ck-wish');
    if (w) {
      w.open = true;
      _renderWishBottle();
      var wt = document.getElementById('wishText');
      if (wt) { wt.focus(); }
      w.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    return;
  }
  if (act !== 'go') return;
  var ta = document.getElementById('shredText');
  var t = ta ? ta.value.trim() : '';
  if (!t) { showToast('先写点什么，才有得碎', 'warn'); return; }
  /* 粉碎动画：纸条裁成 7 条百叶窗切片，各自错落飘落。
   * 切片渲染完计一次件——动画期间防连点。 */
  var paper = document.createElement('div');
  paper.className = 'ck-shred-stage';
  var paperEl = document.createElement('div');
  paperEl.className = 'ck-shred-paper';
  paperEl.textContent = t;
  paper.appendChild(paperEl);
  host.innerHTML = '';
  host.appendChild(paper);
  var H = Math.max(48, paperEl.offsetHeight || 64);
  var SL = 7, sh = Math.ceil(H / SL), i;
  paper.style.height = H + 'px';
  paperEl.style.display = 'none';
  for (i = 0; i < SL; i++) {
    var sl = document.createElement('div');
    sl.className = 'ck-shred-slice';
    sl.style.top = (i * sh) + 'px';
    sl.style.height = Math.min(sh, H - i * sh) + 'px';
    var sliceIn = document.createElement('div');
    sliceIn.className = 'ck-shred-slice-in';
    sliceIn.textContent = t;
    sliceIn.style.top = (-i * sh) + 'px';
    sl.appendChild(sliceIn);
    sl.style.animationDelay = (i * 0.055) + 's';
    sl.style.setProperty('--rot', ((i % 2 ? 1 : -1) * (8 + i * 5)) + 'deg');
    paper.appendChild(sl);
  }
  try {
    localStorage.setItem('shred:' + dateKey,
      String(_shredCount(dateKey) + 1));
  } catch (eS) {}
  _shredRefreshSummary(dateKey);
  setTimeout(function () { _renderShredder('done'); }, 1050);
}

/* R2341（R57-P2-6）：地支→生肖映射提模块级——海报与卡面同口径 */
var _ZHI_ANIMAL = {'子':'鼠','丑':'牛','寅':'虎','卯':'兔','辰':'龙','巳':'蛇',
                   '午':'马','未':'羊','申':'猴','酉':'鸡','戌':'狗','亥':'猪'};
function _zhiToAnimal(v) {
  return _pStr(v).split('/').map(function (z) {
    return _ZHI_ANIMAL[z.trim()] || z.trim();
  }).join('、');
}
/** R215b：温柔模式首屏的生日人话线（年支→生肖）。 */
function baziBirthdayLine(paipan) {
  try {
    const yz = String((paipan && paipan.render) || '').split(/\s+/)[0] || '';
    const m = yz.match(/^(.)(.)/);
    if (m && _ZHI_ANIMAL[m[2]]) return '你是属' + _ZHI_ANIMAL[m[2]] + '的呀：这张小卡就是你的底色。';
  } catch (e) { /* 兜底走通用句 */ }
  return '这是你的生辰底色：展开可以看细节哦。';
}

/* R218a-03：人设卡——10 套日主人设模板（甲乙丙丁戊己庚辛壬癸），数据池
 * 与 src/guji/copy_bank.json#gan_persona 同源（aditive 复制）。后端 paipan.render
 * 形如「庚午年 辛巳月 庚辰日 壬午时　日主：庚　大运：逆」——正则取「日主：X」
 * 的 X 拿来做字典 key。前端纯展示，零后端依赖。 */
var _BAZI_PERSONAS = {
  '甲': { nick: '大树型人格', emoji: '🌳', desc: '直球有担当，朋友里的定海神针',
          kw1: '原则感', kw2: '担当', tone: '#3E8E5A' },
  '乙': { nick: '柔韧藤蔓系', emoji: '🌿', desc: '以柔克刚，哪里都能活得很好',
          kw1: '柔韧', kw2: '共情', tone: '#5BA379' },
  '丙': { nick: '小太阳',     emoji: '☀️', desc: '热情外放，自带打光板',
          kw1: '热烈', kw2: '感染力', tone: '#E89C42' },
  '丁': { nick: '氛围感小夜灯', emoji: '🕯️', desc: '细腻温暖，总能看见别人的情绪',
          kw1: '细腻', kw2: '共情', tone: '#D86A4A' },
  '戊': { nick: '人间靠山',   emoji: '⛰️', desc: '稳重靠谱，说到做到',
          kw1: '稳', kw2: '靠谱', tone: '#815934' },
  '己': { nick: '全能后勤王', emoji: '🌾', desc: '包容能干，默默把一切安排好',
          kw1: '包容', kw2: '细心', tone: '#A8884A' },
  '庚': { nick: '锋利小刀型', emoji: '⚔️', desc: '果敢利落，讨厌拖泥带水',
          kw1: '决断', kw2: '干脆', tone: '#7A5C2E' },
  '辛': { nick: '精致主义家', emoji: '💎', desc: '讲究细节，审美在线',
          kw1: '精致', kw2: '审美', tone: '#B8A89A' },
  '壬': { nick: '机智水流派', emoji: '💧', desc: '脑子活，办法总比困难多',
          kw1: '灵活', kw2: '机智', tone: '#5A8AB8' },
  '癸': { nick: '温柔治愈师', emoji: '🌸', desc: '心思细软，共情力满格',
          kw1: '温柔', kw2: '治愈', tone: '#D89AB8' }
};
function baziPersonaCard(j) {
  try {
    var p = (j && j.paipan) || {};
    var renderStr = String(p.render || '');
    /* render 形如「庚午年 … 日主：庚　大运：逆」——抓日主 */
    var m = renderStr.match(/日主：\s*([甲乙丙丁戊己庚辛壬癸])/);
    var master = m ? m[1] : '';
    var persona = _BAZI_PERSONAS[master];
    if (!persona) {
      /* 后端没传日主时回退到甲（最通用），不破坏首屏视觉。 */
      persona = _BAZI_PERSONAS['甲'];
    }
    return '<div class="bazi-persona" style="border-left:4px solid ' +
      persona.tone + ';">' +
      '<div class="bazi-persona-emoji">' + persona.emoji + '</div>' +
      '<div class="bazi-persona-body">' +
      '<div class="bazi-persona-nick">' + esc(persona.nick) + '</div>' +
      '<div class="bazi-persona-desc">' + esc(persona.desc) + '</div>' +
      '<div class="bazi-persona-kws">' +
      '<span class="bazi-persona-kw">' + esc(persona.kw1) + '</span>' +
      '<span class="bazi-persona-kw">' + esc(persona.kw2) + '</span>' +
      '</div>' +
      '</div></div>';
  } catch (e) { return ''; }
}

/* ── 排盘历史（2026-08-28 水墨改版 C2）：列表 / 复看 / 删除 / 导出 ── */
(function () {
  'use strict';
  async function phFetch(url, opts) {
    /* R228k：与 api() 同款的 20s 超时——raw fetch 也不能让排盘历史
     * 的 busy/在途态永远卡住。
     * R230l（R24-P3-1）：AbortSignal.timeout 需 2022 中后浏览器——
     * 老 Android WebView/旧 Safari 上此前无任何超时，挂起连接=永卡
     * busy。补 api() 同款 AbortController+setTimeout 回退。 */
    opts = opts || {};
    var _ctl = null, _t = null;
    if (!opts.signal) {
      if (typeof AbortSignal !== 'undefined' && AbortSignal.timeout) {
        opts.signal = AbortSignal.timeout(API_TIMEOUT_MS);
      } else if (typeof AbortController !== 'undefined') {
        _ctl = new AbortController();
        _t = setTimeout(function () { _ctl.abort(); }, API_TIMEOUT_MS);
        opts.signal = _ctl.signal;
      }
    }
    var r;
    try {
      r = await fetch(url, opts);
    } finally {
      if (_t) clearTimeout(_t);
    }
    if (!r.ok) {
      let m = '这条记录找不到了，刷新列表看看';
      /* R230v（R34-#22）：422 的 detail 是 pydantic 数组——取首条 msg，
       * 不再落进「没查到」的误导文案。
       * R2349j（R71-P2）：拿到的串先过人话化（405「Method Not Allowed」
       * 等透传、英文 msg 兜底都被吃掉）。 */
      try { const j = await r.json();
        if (j && typeof j.detail === 'string') m = j.detail;
        else if (j && Array.isArray(j.detail) && j.detail.length &&
                 j.detail[0] && j.detail[0].msg) m = j.detail[0].msg;
        m = _humanizeErr(m);
      } catch (e) {}
      /* R2400（R139-P1-2）：裸 Error 没有 .status——下游 401/403
       * 「门匙失效不走镜像」判据从此真的够得着。 */
      var _err = new Error(m);
      _err.status = r.status;
      throw _err;
    }
    return r.json();
  }
  /* R2502：在途合并 + 详情保留。被动刷新（跨 tab storage 事件、
   * BroadcastChannel 脏标）此前无条件清掉正在读的详情卡；并发调用
   * 也无去重（后到写覆盖先到写）。preserve=true 的路径不动详情，
   * 只在其对应行已消失时才收。 */
  var _PH_LIST_BUSY = false;
  var _PH_LIST_PEND;   /* 待跑的 preserve 意图（undefined=无） */
  async function loadPaipanHistory(preserveDetail) {
    const listEl = document.getElementById('historyList');
    if (!listEl) return;
    if (_PH_LIST_BUSY) {          /* R2502：并发去重——记最新意图补跑 */
      _PH_LIST_PEND = preserveDetail;
      return;
    }
    _PH_LIST_BUSY = true;
    try {
      await _loadPaipanHistoryInner(listEl, preserveDetail);
    } finally {
      _PH_LIST_BUSY = false;
      if (_PH_LIST_PEND !== undefined) {
        var _p = _PH_LIST_PEND;
        _PH_LIST_PEND = undefined;
        loadPaipanHistory(_p);
      }
    }
  }
  async function _loadPaipanHistoryInner(listEl, preserveDetail) {
    const detailEl = document.getElementById('historyDetail');
    if (detailEl && !preserveDetail) {
      detailEl.hidden = true; detailEl.innerHTML = '';
      delete detailEl.dataset.rid;
    }
    listEl.innerHTML = '<div class="ph-empty">加载中…</div>';
    try {
      const j = await phFetch('/api/paipan/history?limit=50');
      /* R2349t（R87-P2-1）：禁用态此前被读成「还没用过」——
       * 「都会收在这里」与永不写的事实矛盾；台账关闭时说真话。 */
      if (j.disabled) {
        listEl.innerHTML = '<div class="ph-empty">记录功能没开，命盘照算，只是不留档 ✨</div>';
        return;
      }
      /* R2363：云端照常时顺手推镜像（只进不出，老记录自然滚动淘汰）。 */
      var _mm = _phMirrorLoad();
      _phMirrorList(_mm, j.items);
      _phMirrorSave(_mm);
      if (!j.items || !j.items.length) {
        /* R2363（R116-P0-1）：云端空但本机有镜像——这是睡醒清盘后
         * 的「本机留档」态，照旧列出记录并标明出处（不是「还没用过」）。 */
        if (_phRenderMirrorList(listEl, _mm)) return;
        /* R2350f（R102-P2-11）：空态加行动出口——罗列品类但没一个能点，
         * 新客读完只能自己回首页找。 */
        listEl.innerHTML = '<div class="ph-empty">还没有占卜记录，命盘、桃花、合婚、塔罗、六爻、起名都会收在这里 ✨' +
          '<div style="margin-top:10px;display:flex;gap:8px;justify-content:center;">' +
          /* R2502：view-daily 不存在——showView('daily') 落回首页却把
           * __inView 置真、标题拼成「daily · …」半吊子态。直接链 home。 */
          '<button type="button" class="ghost" data-view="home">✨ 去抽今日一签</button>' +
          '<button type="button" class="ghost" data-view="taohua">🌺 测测桃花</button></div></div>';
        listEl.querySelectorAll('[data-view]').forEach(function (_b) {
          _b.addEventListener('click', function () {
            if (typeof showView === 'function') showView(_b.dataset.view);
          });
        });
        return;
      }
      /* R2400（R127-P2-7）：云端/本机合渲——镜像里有而本页没有的行
       * （清盘前旧档、翻页窗外旧档）按 ts 归位标「本机留档」；id 撞号
       * 云端为准（同号是否同条在 _phMirrorList 里已裁决）。 */
      var _cloudIds = {};
      /* R2400（R138-P1-2）：复合键去重——同 id 不同 ts 不再互顶。 */
      j.items.forEach(function (it) {
        _cloudIds[String(it.id) + '|' + String(it.ts || '')] = 1;
      });
      var _localIds = {};
      var _rows = j.items.slice();
      Object.keys(_mm.items || {}).forEach(function (k) {
        if (!_cloudIds[k]) {
          var _o = _mm.items[k];
          _localIds[String(_o.id) + '|' + String(_o.ts || '')] = 1;
          _rows.push({ id: _o.id, ts: _o.ts, name: _o.name, type: _o.type,
                       question: _o.question,
                       result_summary: _o.result_summary });
        }
      });
      if (_rows.length !== j.items.length) {
        _rows.sort(function (a, b) {
          return String(b.ts || '').localeCompare(String(a.ts || ''));
        });
      }
      listEl.innerHTML = _rows.map(function (it) {
        const ts = _fmtWhen(it.ts);
        const q = it.question ? '<span class="ph-q">问：' + esc(it.question) + '</span>' : '';
        /* R230z（R36-P1-1）：品类徽标——历史不再只收命盘 */
        /* R2349j（R71-P2）：未知 type 不原值上屏（技术字段名出戏）。 */
        const tLabel = _PH_TYPE_LABEL[it.type] || '记录';
        const render = (it.result_summary && it.result_summary.paipan_render) || '';
        /* R230a-44（R15-P3）：it.id 当前恒为 int，但多行拼接模式逃过单行
         * innerHTML 闸——将来字符串列入同一模式即成洞，先按 esc 纪律统一。 */
        var _mir = _localIds[String(it.id) + '|' + String(it.ts || '')]
          ? ' data-mirror="1"' : '';
        return '<div class="ph-item" data-id="' + esc(String(it.id)) + '"' +
          _mir +
          /* R3200：类型筛选——行元素带 type 供 chip 隐藏过滤 */
          ' data-type="' + esc(it.type || 'bazi') + '">' +
          '<div class="ph-head"><span class="ph-type ph-t-' + esc(it.type || 'bazi') + '">' +
          esc(tLabel) + '</span>' +
          '<span class="ph-name">' + esc(it.name || ('记录 #' + it.id)) + '</span>' +
          '<span class="ph-ts">' + esc(ts) + '</span>' +
          (_localIds[String(it.id) + '|' + String(it.ts || '')]
            ? '<span class="ph-type" style="opacity:.7;">本机留档</span>' : '') +
          '</div>' + q +
          '<div class="ph-render">' + esc(render) + '</div>' +
          '<div class="ph-actions"><button type="button" class="ghost ph-open">查看</button>' +
          '<button type="button" class="ghost ph-del">删除</button></div></div>';
      }).join('');
      /* R2502：被动刷新保留详情——但若正在读的那条已被别 tab 删掉，
       * 行没了就收详情（留死详情比清屏更糟）。 */
      if (preserveDetail && detailEl && !detailEl.hidden &&
          detailEl.dataset.rid &&
          !listEl.querySelector('.ph-item[data-id="' +
              String(detailEl.dataset.rid).replace(/"/g, '') + '"]')) {
        detailEl.hidden = true; detailEl.innerHTML = '';
        delete detailEl.dataset.rid;
      }
      _phRenderFilter(_rows);   /* R3200：类型筛选 chip 行 */
    } catch (e) {
      /* R2400（R127-P1-3）：镜像只补「够不到」不补「不让看」——
       * 断网/5xx 时回退本机留档（与详情、收藏同口径）；401/403
       * 门匙问题走错误态，留档不出。 */
      if (!(e && (e.status === 401 || e.status === 403)) &&
          _phRenderMirrorList(listEl, _phMirrorLoad())) return;
      listEl.innerHTML = '<div class="ph-empty">加载失败：' + esc(_humanizeErr(e.message)) + '（可点上方『刷新』重试）</div>';
      /* R2343（R58-P2-3）：与全站「错误必 toast」口径一致——被动加载
       * 失败也即时可感。 */
      try { showToast('历史台账没拉成功：' + _humanizeErr(e.message), 'warn'); } catch (e0) {}
    }
  }
  document.addEventListener('click', async function (ev) {
    const tg = ev.target;
    if (!tg || !tg.classList) return;
    const item = tg.closest('.ph-item');
    if (item && tg.classList.contains('ph-del')) {
      const id = item.getAttribute('data-id');
      /* R228f：原生 confirm() 与全局 toast 体系不一致——改两段式 inline
       * 确认：首点把按钮武装成「再点一次确认」，3 秒内再点才真删。 */
      if (tg.dataset.armed !== '1') {
        tg.dataset.armed = '1';
        var _origTxt = tg.textContent;
        tg.textContent = '再点一次确认删除';
        /* R233f（R43-P3-19）：聚焦中按钮 textContent 变化读屏多半不重播
         * ——同步 aria-label，武装态可被朗读。 */
        tg.setAttribute('aria-label', '再点一次确认删除');
        tg.classList.add('ph-del-armed');
        setTimeout(function () {
          tg.dataset.armed = '';
          tg.textContent = _origTxt;
          tg.removeAttribute('aria-label');
          tg.classList.remove('ph-del-armed');
        }, 3000);
        return;
      }
      /* R230t（R33-P2-3）：确认后立刻收 armed+在途锁——原先 3s 窗口内
       * 第三点会再发一个 DELETE 撞 404，误报「删除失败」。 */
      tg.dataset.armed = '';
      if (tg.dataset.inflight === '1') return;
      tg.dataset.inflight = '1';
      /* R3362（R3360 审-P1）：镜像行的 id 来自清盘前的旧库——服务端
       * id 重排后该号可能已派给无关新记录，发 DELETE 即误删云端一条。
       * 镜像行只本地摘除，不碰云端。 */
      if (item.dataset.mirror === '1') {
        var _ml = _phMirrorLoad(); _phMirrorDrop(_ml, id); _phMirrorSave(_ml);
        if (item.isConnected) item.remove();
        showToast('本机留档已摘掉', 'info');
        tg.dataset.inflight = '';
        return;
      }
      try {
        await phFetch('/api/paipan/history/' + id, { method: 'DELETE' });
        /* R2363：删成功了顺手把镜像里的也摘掉（两边口径一致）。 */
        var _md = _phMirrorLoad(); _phMirrorDrop(_md, id); _phMirrorSave(_md);
        /* R233f（R43-P2-4）：列表重建销毁聚焦钮 → 落回列表容器 */
        loadPaipanHistory().then(function () {
          var _hl = el('historyList');
          if (_hl) { try { _hl.focus(); } catch (ef) {} }
        }, function () {});
        /* R230n续（R23-P3-6）：删除成功广播脏标，其他 tab 同步刷新。 */
        try {
          if (window.BroadcastChannel) {
            var _bc2 = new BroadcastChannel('paipan_history');
            _bc2.postMessage('dirty'); _bc2.close();
          }
        } catch (e2) {}
      }
      /* R228c：错误反馈统一走 toast 体系，不用原生 alert */
      catch (e) {
        /* R2363：404 = 云端已清——视同删成功，把镜像也摘掉、行摘走。 */
        if (/(404|没查到|不存在)/.test(e && e.message || '')) {
          var _md2 = _phMirrorLoad(); _phMirrorDrop(_md2, id); _phMirrorSave(_md2);
          if (item.isConnected) item.remove();
        } else {
          /* R3319-P2：裸 e.message 出屏（「删除失败：Failed to fetch」）
           * ——先过人话化闸。 */
          showToast('删除失败：' + _humanizeErr(e.message), 'error');
        }
      }
      finally { tg.dataset.inflight = '0'; }
      return;
    }
    if (item && tg.classList.contains('ph-open')) {
      const id = item.getAttribute('data-id');
      /* R233k（R45-P2）：连点两条历史并发取详情，后到覆盖先到——
       * 代际号丢弃过期响应（_XZ_GEN 先例）。 */
      var _g = ++_PH_OPEN_GEN;
      var rec;
      /* R2400（R124-P2-2）：点「查看」到详情上屏期间零反馈——
       * 钮忙时态，慢网下不再像没点上。 */
      var _origLabel = tg.textContent;
      tg.textContent = '翻开中…';
      tg.disabled = true;
      try {
        rec = await phFetch('/api/paipan/history/' + id);
        /* R2363：能拿到就推进镜像——打开过的记录清盘后仍可复看。 */
        var _mo = _phMirrorLoad(); _phMirrorDetail(_mo, rec); _phMirrorSave(_mo);
      } catch (e0) {
        /* R2363：云端取不到（404/清盘）→ 读本机镜像详情
         * R2400（R127-P1-2）：同号详情先对 ts——清盘重排后 id 撞号，
         * ts 不符的是串档旧尸，不上屏（_phMirrorDetailFor 顺手摘尸）。 */
        /* R2400（R139-P1-2）：门匙失效 401/403 不走镜像详情——
         * 「过期设备不该再看数据」与列表面同一口径。 */
        if (e0 && (e0.status === 401 || e0.status === 403)) {
          if (tg.isConnected) { tg.textContent = _origLabel; tg.disabled = false; }
          showToast('门匙失效了，重新输口令进门再翻记录', 'warn');
          return;
        }
        var _mmx = _phMirrorLoad();
        rec = _phMirrorDetailFor(_mmx, id);
        if (rec) { _phMirrorDetail(_mmx, rec); }   /* 刷新最近打开序 */
        _phMirrorSave(_mmx);   /* 摘尸/序位变更落盘（同值不写） */
        if (!rec) {
          if (tg.isConnected) { tg.textContent = _origLabel; tg.disabled = false; }
          showToast('这条云端已清、本机只留了摘要行，以后点过的记录会整条留在你设备上', 'warn');
          if (/(404|没查到)/.test(e0 && e0.message || '') && item.isConnected) {
            item.remove();
          }
          return;
        }
      }
      if (tg.isConnected) { tg.textContent = _origLabel; tg.disabled = false; }
      try {
        if (_g !== _PH_OPEN_GEN) return;
        const detailEl = document.getElementById('historyDetail');
        /* R230z（R36-P1-1）：按品类回放对应渲染器 */
        var _builder = _PH_BUILDERS[rec.type || 'bazi'] || _PH_BUILDERS.bazi;
        if (detailEl && _builder) {
          /* 六个 build*Result 渲染器内部全量 esc()，与闸白名单里的
           * buildBaziResult( 同等信任级——间接调用只为按 type 分发 */
          detailEl.innerHTML = _builder(rec.result || {});   // esc-reviewed
          /* R231d（R37-F16）：复看里的分享钮此前是死钮/缺位——原视图
           * 的 on() 绑定按 id 命中首个元素，复看副本永远点不动；
           * tarot/liuyao 则根本没钮。统一在复看卡顶部补一个真钮，
           * 走存档的 rec.result 直接出海报（内嵌死钮由 CSS 隐藏）。 */
          var _type = rec.type || 'bazi';
          /* R232a（R40-A6）：复看回显「当时问的是什么/给谁算的」——
           * name/question/ts 一直存着但从前不回显，复看卡光秃秃。 */
          var _meta = [];
          if (rec.name) _meta.push(esc(rec.name));
          if (rec.ts) _meta.push(esc(String(rec.ts).slice(0, 16)));
          if (rec.question) _meta.push('问「' + esc(rec.question) + '」');
          /* R3316（审-P2）：降级留档不上分享钮——只剩摘要行的
           * 记录 rec.result={}，点下去出半空白海报。 */
          var _hasRes = !!(rec.result &&
                           Object.keys(rec.result).length);
          detailEl.insertAdjacentHTML('afterbegin',
            (_meta.length
              ? '<div class="ph-meta">' + _meta.join(' · ') + '</div>' : '') +
            (_hasRes
              ? '<button class="ghost fav-btn ph-share" type="button" ' +
                'id="phShareBtn" title="生成分享图">📸 分享这张图</button>'
              : ''));
          var _psb = detailEl.querySelector('#phShareBtn');
          if (_psb) _psb.addEventListener('click', function () {
            try {
              /* R3353（审-P3）：台账分享海报副标用记录日——出图
               * 日期可追溯到这张记录，不是点开生成那天。 */
              var _rj = Object.assign({}, rec.result || {},
                { _posterDate: String(rec.ts || '').slice(0, 10) });
              var _p = downloadPoster(_rj, _type);
              if (_p && _p.catch) _p.catch(function (e) {
                showToast('分享图生成失败：' +
                  (e && _humanizeErr(e.message) || '稍后再试'), 'warn');
              });
            } catch (e) {
              showToast('分享图生成失败：' +
                (e && _humanizeErr(e.message) || '稍后再试'), 'warn');
            }
          });
          /* R2502：记下详情归属行——被动刷新时按它判定行还在不在。 */
          detailEl.dataset.rid = String(id);
          detailEl.hidden = false;
          detailEl.scrollIntoView({ behavior: _rmBehavior() });
          /* R2506（审-U2）：焦点跟到详情面板——与删除路径结束后
           * historyList.focus() 同纪律（此前焦点停在已滚离的行钮上）。 */
          try { detailEl.focus({ preventScroll: true }); } catch (eF) {}
        }
      } catch (e) {
        showToast('读取失败：' + _humanizeErr(e.message), 'error');
        /* R230k（R23-P3-6）：多标签页里 B 删过的行在 A 仍是陈旧行——
         * 复看撞 404 时顺手把该行摘出列表，不留死入口。 */
        if (/(404|没查到)/.test(e && e.message || '') && item.isConnected) {
          item.remove();
        }
      }
    }
  });
  /* R230n续（R23-P3-6）：跨 tab 脏标监听——别页新建/删除排盘后，
   * 本页历史视图若在展示中就地重载（陈旧行不再留死入口）。 */
  try {
    if (window.BroadcastChannel) {
      var _phBC = new BroadcastChannel('paipan_history');
      _phBC.onmessage = function (e) {
        if (!e || e.data !== 'dirty') return;
        /* R2400（R139-P2-5）：dirty 先于台账落库 ~60ms 广播——
         * 立即重拉读到不含新行的列表。缓 400ms 再拉。 */
        var hv = document.getElementById('view-history');
        if (hv && hv.classList.contains('active')) {
          /* R2502：同 storage 口径——被动刷新保留在读详情。 */
          setTimeout(function () { loadPaipanHistory(true); }, 400);
        }
      };
    }
  } catch (e) {}
  function phBind() {
    const card = document.querySelector('.func-card[data-view="history"]');
    if (card) card.addEventListener('click', function () { setTimeout(loadPaipanHistory, 0); });
    /* R230t（R33-P3-5/6）：刷新/导出无锁——双击各弹一遍。 */
    var _phLast = { rf: 0, ex: 0 };
    /* R3200：类型筛选 chip——委托在容器上（渲染会重建内部）。 */
    var _hf = document.getElementById('historyFilter');
    if (_hf) _hf.addEventListener('click', function (ev) {
      var c = ev.target.closest && ev.target.closest('.ph-fchip');
      if (!c) return;
      _phTypeFilter = c.getAttribute('data-t') || '';
      _hf.querySelectorAll('.ph-fchip').forEach(function (x) {
        var _on = (x.getAttribute('data-t') || '') === _phTypeFilter;
        x.classList.toggle('on', _on);
        x.setAttribute('aria-pressed', _on ? 'true' : 'false');
      });
      _phApplyFilter();
    });
    const rf = document.getElementById('historyRefresh');
    if (rf) rf.addEventListener('click', function () {
      if (performance.now() - _phLast.rf < 800) return;
      _phLast.rf = performance.now();
      loadPaipanHistory();
    });
    const ex = document.getElementById('historyExport');
    if (ex) ex.addEventListener('click', function () {
      if (performance.now() - _phLast.ex < 1500) return;
      _phLast.ex = performance.now();
      /* R2353（R110-P1-1）：微信/触屏端 window.open(attachment) 静默
       * 丢弃——取回 CSV 文本改走展示式弹层。 */
      if (_exportShowOnly()) {
        fetch('/api/paipan/history/export', { credentials: 'same-origin' })
          .then(function (r) {
            return r.ok ? r.text() : Promise.reject(new Error('csv ' + r.status));
          })
          .then(function (csv) {
            _showTextExportModal('排盘台账备份',
              csv, '点「复制全部」，存到备忘录或发给文件传输助手');
          })
          .catch(function () {
            showToast('台账暂时取不来，稍后再试试', 'warn');
          });
      } else {
        window.open('/api/paipan/history/export', '_blank');
      }
    });
    /* R231a（R36-P3-3）：备份我的数据 = 台账全量 JSON + 浏览器侧键
     * （打卡/me 双档/问一嘴足迹/主题/口吻）。换设备一键带走。 */
    /* R3358：bundle 构建抽成共享函数——导出按钮与账号云同步
     * 共用同一份「我的数据」口径。 */
    /* R3372-P2-2：本机「个人数据」键白名单收敛成唯一定义——备份
     * 导出/云备份包/跨账号清扫/拉回 diff/备份导入共用一张表。
     * uiTheme 本就在备份里（THEME_KEY 同键，随账号走），换主
     * 清扫收它是对的——B 拉回自己的主题；wipe 留它是刻意的
     * 「忘掉不翻主题」。voiceMode/chatSessionId 是死键/会话锚，
     * 清扫要收但备份与导入不收。 */
    var _DATA_RE = /^(checkin:|dailyRevealed:|checkinCeleb:|checkinBuff:|mood:|moodlv:|moodjar:|ritual:|journal:|usage:|rlast:|read:scroll:|me$|me:partner$|hlask$|visits$|welcomed$|wishbottle$|wishfulfilled$|mantraFav$|installTipDismissed$|ret_tip$|uiTheme$|voiceMode$|chatSessionId$|chat:topics$|chat:cards$|chat:events$|chatTranscript(:|$)|remind:|notify:time$|returnBannerDismissed$|futureLetters(:|$)|pilePick:|weeklyLetter:|monthlyLetter:|couple:|shred:|manifest:|mochi:|qian:|ansb:)/;
    var _NO_BACKUP_RE = /^(voiceMode|chatSessionId)$/;
    /* sessionStorage 侧同口径（wipe 与换主清扫共用）——邀请态/
     * 分享归因/聊天会话锚/结果缓存都是跟「这个人」绑的。 */
    var _SDATA_RE = /^(chatSessionId|chatTranscript|trAskedToday|hhInvite|shareBy|chatTopicFactDone|chatCardsFactDone|chatBootId|ly:lastq|ly:lastcast|chatClosed)$|^shareBy:|^lastResult:/;
    async function _buildBackupBundle() {
        /* R2349y（R95-P2-5）：台账禁用态下 export_json 404——此前整个
         * 备份中止，连本机偏好都带不走。降级 records:[] 并明说。 */
        var j;
        var _noLedger = false;
        try {
          j = await phFetch('/api/paipan/history/export_json');
        } catch (eEx) { j = { records: [] }; _noLedger = true; }
        var local = {};
        /* R39-P3-1：dailyRevealed/visits 收进备份白名单——换机不丢
         * 连拆记录与「第 N 次开铺」计数。 */
        /* R232a（R40-R3）：welcomed/installTipDismissed 补进白名单——
         * 换机后不再重见新手引导与安装提示。 */
        /* R2349t（R87-P1-3）：checkinCeleb 里程碑标记/ret_tip 也
         * 进备份——换机后庆典不重弹、提示不重见。 */
        /* R2349y（R95-P3-4）：'me' 前缀过宽会把未来任何 me* 键
         * 扫进备份——精确键与前缀键分开：前缀只留给日期后缀键。 */
        var _PREF = ['checkin:', 'dailyRevealed:', 'checkinCeleb:',
                     'mood:', 'moodlv:', 'rlast:', 'usage:', 'ritual:',
                     'journal:',
                     /* R3325：大众占卜每日选堆 */
                     'pilePick:',
                     /* R3329：周/月信已弹标随备份走 */
                     'weeklyLetter:', 'monthlyLetter:',
                     /* R3328：打卡 buff 足迹也随备份走 */
                     'checkinBuff:',
                     /* R3262（R17）：心情罐子解锁表跟心情历一起备份 */
                     'moodjar:',
                     /* R3264（R52）：古籍阅读进度记忆 */
                     'read:scroll:',
                     /* R3336（审-中）：corrupt 救援备份同族导出 */
                     'futureLetters:',
                     /* R3345（审-中）：聊天记录换机——wipe 已收
                      * chatTranscript 前缀、备份却不带，口径不一致
                      * 且换机全丢无提示。sid 桶+lastsid 同族导出。 */
                     'chatTranscript:',
                     /* R3351（审-P1）：couple:/shred: wipe 收编但导出
                      * 漏——修好合拍链后换机会静默丢交集与碎纸计数。 */
                     'couple:', 'shred:'];
        /* R2508（审-P2-1）：wishbottle 是用户亲笔愿望文本——备份
         * 不带它就是「全量带走」漏项（且 wipe 也收不到它，见下）。 */
        /* R3163：chat:topics/chat:cards（跨天画像+卡片记忆）漏出备份——
         * 换机后小满「不记得她」成预期内落差；wipe 已收编这两键，
         * 备份带齐才对称。 */
        var _EXACT = ['me', 'me:partner', 'hlask', 'visits', 'welcomed',
                      'installTipDismissed', 'ret_tip', 'wishbottle',
                      'chat:topics', 'chat:cards', 'remind:1',
                      'chat:events', 'mood:lv', 'notify:time',
                      'returnBannerDismissed', 'futureLetters',
                      /* R3337：成真集是亲笔愿望文本的延续——备份带上 */
                      'wishfulfilled',
                      /* R3350：咒语册同族——收来的句子也是亲笔痕迹 */
                      'mantraFav'];
        for (var i = 0; i < window.localStorage.length; i++) {
          var k = window.localStorage.key(i);
          if (!k) continue;
          /* R3372-P2-2：收敛到共享 _DATA_RE——修一处全链生效；
           * _NO_BACKUP_RE 拦死键/会话锚不进备份。顺带补回
           * chatTranscript 裸键与 remind: 前缀（此前口径漏收）。 */
          var _hit = _DATA_RE.test(k) && !_NO_BACKUP_RE.test(k);
          if (_hit) {
            try { local[k] = window.localStorage.getItem(k); } catch (e) {}
          }
        }
        /* R3265：voiceMode 键下线——只剩 THEME_KEY 需要进备份。 */
        [THEME_KEY].forEach(function (k) {
          try {
            var v = window.localStorage.getItem(k);
            if (v != null) local[k] = v;
          } catch (e) {}
        });
        /* R2349t（R87-P1-3）：favorites（合婚 CP 双方生辰+心水名单）
         * 在服务端表——备份不带它就是「全量带走」名不副实。 */
        var _favs = [];
        try {
          var _pf = await phFetch('/api/user/prefs');
          _favs = (_pf && _pf.favorites) || [];
        } catch (eFv) {}
        /* R2400（R127-P1-4）：云端空/拉不到时拿本机留档兜底——清盘态
         * 点「备份」不该导出一本空账（设备上唯一的副本要带走）。 */
        if (!_favs.length) _favs = _favMirrorLoad();
        /* R2400（R138-P0-2/P1-3）：研究线程/手记此前无出口——清盘
         * 永丢且「忘掉」也不清。备份带线程摘要+每线程轮次。 */
        var _threads = [];
        try {
          /* R2500（R143-P1-3）：limit=500 够到全部线程——此前默认前 50
           * 条，第 51+ 条备份不到。truncated 仍有 200 帽外残余但已限窄。 */
          var _tl = await api('/api/threads?status=all&limit=500',
                              { silent: true });
          var _tlArr = (_tl && _tl.threads) || [];
          for (var _ti = 0; _ti < _tlArr.length; _ti++) {
            try {
              var _td = await api('/api/threads/' +
                                  encodeURIComponent(_tlArr[_ti].id),
                                  { silent: true });
              /* R2500（R143-P1-2/D2）：claims/手记入包——此前只带 turns
               * 清盘恢复后手记原文永丢。 */
              _threads.push({ id: _tlArr[_ti].id, topic: _tlArr[_ti].topic,
                              status: _tlArr[_ti].status,
                              opened_at: _tlArr[_ti].opened_at,
                              updated_at: _tlArr[_ti].updated_at,
                              turns: (_td && _td.turns) || [],
                              claims: (_td && _td.claims) || [] });
            } catch (eTd) {}
          }
        } catch (eTl) {}
        /* R3339（审-中）：云端空/拉不到时线程也拿本机留档顶——
         * 题头能带走（turns/claims 云端已清带不走）。 */
        if (!_threads.length) {
          try {
            /* R3369（审-P2-3）：镜像壳题头进包会占 (topic, opened_at)
             * 去重键把后来带真内容的备份顶掉——服务端虽已做补内容
             * 合并，壳行仍标 shell:true 明示「没料」。 */
            _threads = (_thrMirrorLoad().items || []).map(function (x) {
              return { id: x.id, topic: x.topic, status: x.status,
                       opened_at: x.opened_at, updated_at: x.updated_at,
                       turns: [], claims: [], shell: true };
            });
          } catch (eTM) {}
        }
        /* R3369（审-P1-3）：孤儿手记（删过线程留下的研究笔记）
         * 此前备份根本不带——清盘永丢。打包带走。 */
        var _orphans = [];
        try {
          var _ocl = await api('/api/claims?orphaned=true&limit=200',
                               { silent: true });
          _orphans = (_ocl && _ocl.claims) || [];
        } catch (eOc) {}
        var _recsOut = j.records || [];
        if (!_recsOut.length) {
          var _mmB = _phMirrorLoad();
          var _seen = {};
          _recsOut = Object.keys(_mmB.details).map(function (k) {
            _seen[k] = 1; return _mmB.details[k];
          });
          /* R2500（R143-P1-1）：镜像 items 只有摘要行（无 req/result）
           * ——空壳进包落库后 (ts,name,type) 去重键被占，之后带真内容
           * 的备份对该条永远 skip。只收有内容的行。 */
          Object.keys(_mmB.items).forEach(function (k) {
            var _it = _mmB.items[k];
            var _hasBody = _it && (_it.req || _it.result) &&
              (Object.keys(_it.req || {}).length ||
               Object.keys(_it.result || {}).length);
            if (!_seen[k] && _hasBody) _recsOut.push(_it);
          });
          _recsOut.sort(function (a, b) {
            return String(b.ts || '').localeCompare(String(a.ts || ''));
          });
        }
        var bundle = { app: '小满的解忧铺', kind: 'backup', version: 1,
                       exported_at: j.exported_at || new Date().toISOString(),
                       browser: local, records: _recsOut,
                       favorites: _favs, threads: _threads,
                       orphan_claims: _orphans,
                       _noLedger: _noLedger };
        return bundle;
    }
    var _exj = document.getElementById('historyExportJson');
    if (_exj) _exj.addEventListener('click', async function () {
      try {
        var bundle = await _buildBackupBundle();
        var _noLedger = !!bundle._noLedger;
        delete bundle._noLedger;
        var _recsOut = bundle.records || [];
        var _favs = bundle.favorites || [];
        var _threads = bundle.threads || [];
        /* R2353（R110-P1-1）：触屏/微信里 blob a[download] 静默丢弃
         * 还误报「已下载」——改展示式弹层+复制。 */
        if (_exportShowOnly()) {
          _showTextExportModal('我的数据备份',
            JSON.stringify(bundle, null, 2),
            '点「复制全部」，存到备忘录或发给文件传输助手，换新设备时贴回导入' +
            /* R3329（审-P3）：点名未来信——信在备份里，不点名用户
             * 可能不知道带到了。 */
            '（含生辰昵称、心情愿望与未来信，存哪儿自己留心）');
          return;
        }
        var blob = new Blob([JSON.stringify(bundle, null, 2)],
                            { type: 'application/json' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        /* R2349k（R72-B6）：toISOString 是 UTC 日——东八区 0-8 点导出的
         * 文件名会写昨天。本地日用 sv 语法的 toLocaleDateString。 */
        a.download = '小满-我的数据-' +
          new Date().toLocaleDateString('sv') + '.json';
        a.click();
        setTimeout(function () { URL.revokeObjectURL(a.href); }, 3000);
        /* R2349y（R95-P2-4）：备份含明文生辰/昵称/提问——
         * toast 明说让用户存的时候留心。 */
        /* R3345（审-低）：favorites/threads 实际入包却不点名——
         * 用户不知道带走了什么。各段计数明示。 */
        showToast((_noLedger && !_recsOut.length
          ? '台账没开，只备份了本机偏好'
          : '备份已下载：' + _recsOut.length + ' 条记录' +
            (_favs.length ? ' + ' + _favs.length + ' 对合婚' : '') +
            (_threads.length ? ' + ' + _threads.length + ' 条线程' : '') +
            ' + 本机偏好') +
          '（含生辰昵称、心情愿望与未来信，存哪儿自己留心）', 'info');
      } catch (e) {
        showToast('备份失败：' + _humanizeErr(e.message), 'error');
      }
    });
    /* R2345（R63-P1-3）：「忘掉我的数据」——两段式确认后清：
     * ① localStorage 个人键（me/me:partner/hlask/checkin:前缀/
     *   dailyRevealed:前缀/visits/welcomed + 孤儿 chatSessionId 等）；
     * ② 服务端 paipan_history 台账整表。主题/口吻偏好保留。 */
    var _hw = document.getElementById('historyWipe');
    if (_hw) _hw.addEventListener('click', function () {
      if (_hw.dataset.armed !== '1') {
        _hw.dataset.armed = '1';
        var _ot = _hw.textContent;
        _hw.textContent = '再点一次：生辰/昵称/记录全清';
        _hw.setAttribute('aria-label', '再点一次确认清空我的数据');
        _hw.classList.add('ph-del-armed');
        setTimeout(function () {
          _hw.dataset.armed = '';
          _hw.textContent = _ot;
          _hw.removeAttribute('aria-label');
          _hw.classList.remove('ph-del-armed');
        }, 4000);
        return;
      }
      _hw.dataset.armed = '';
      if (_hw.dataset.inflight === '1') return;
      _hw.dataset.inflight = '1';
      var _done = function (serverOk) {
        _hw.dataset.inflight = '';
        try {
          var _rm = [];
          for (var i = 0; i < localStorage.length; i++) {
            var k = localStorage.key(i);
            /* R2349（R65-P2-4）：checkinCeleb:*（里程碑已弹标记）此前
           * 游离在清除清单外——一起收。 */
          /* R2508（审-P2-1）：wishbottle（许愿瓶自由文本）此前游离在
           * 清除清单外——「忘掉我的数据」后愿望仍幸存重渲，隐私破洞。 */
          /* R3339（审-低）：installTipDismissed/ret_tip/voiceMode（死键
           * 可被旧备份导回）此前游离在清除清单外——实测 wipe 后残留。 */
          /* R3350：mantraFav（咒语册句子）也是个人化数据，「忘掉我的
           * 数据」一起收——与 wishfulfilled 同族口径。 */
          if (k && (/^(me(:partner)?|hlask|visits|welcomed|wishbottle|wishfulfilled|mantraFav|chatSessionId|chat:topics|chat:cards|chat:events|mood:lv|notify:time|returnBannerDismissed|paipan_mirror_v1|paipan_mirror_del_v1|favorites_mirror_v1|threads_seen_v1|threads_mirror_v1|installTipDismissed|ret_tip|voiceMode)$/
                .test(k) || k.indexOf('remind:') === 0 ||
                /* R3339（审-中）：transcript 改 sid 命名空间后裸名匹配
                 * 漏收 chatTranscript:<sid>/:lastsid——前缀全覆盖。 */
                k.indexOf('chatTranscript') === 0 ||
                k.indexOf('checkin:') === 0 ||
                k.indexOf('checkinBuff:') === 0 ||
                k.indexOf('dailyRevealed:') === 0 ||
                k.indexOf('checkinCeleb:') === 0 ||
                /* R3260：R1-R7 新增键——心情历（mood:<date>/moodlv:<date>）
                 * 与使用足迹（usage:*）此前游离在清除清单外，
                 * 「忘掉我的数据」后幸存=隐私破洞。 */
                k.indexOf('mood:') === 0 ||
                k.indexOf('moodlv:') === 0 ||
                /* R3262（R17）：心情罐子解锁表也是个人化数据，一起清。 */
                k.indexOf('moodjar:') === 0 ||
                /* R3264（R32）：今日仪式记录也是个人足迹，一起清。 */
                k.indexOf('ritual:') === 0 ||
                /* R3264（R33）：今日小确幸也是个人足迹，一起清。 */
                k.indexOf('journal:') === 0 ||
                /* R3264（R52）：古籍阅读进度记忆 */
                k.indexOf('read:scroll:') === 0 ||
                k.indexOf('usage:') === 0 ||
                k.indexOf('rlast:') === 0 ||
                /* R3325：未来信+每日选堆也是个人足迹 */
                /* R3336（审-中）：futureLetters:corrupt 救援备份键
                 * 同族收掉——「忘掉」后信件原文不得残留。 */
                k.indexOf('futureLetters') === 0 ||
                k.indexOf('pilePick:') === 0 ||
                /* R3329（审-P3）：周/月信已弹标不收 wipe——「忘掉」
                 * 后信卡复弹。 */
                k.indexOf('weeklyLetter:') === 0 ||
                k.indexOf('monthlyLetter:') === 0 ||
                /* R3335：碎念件数也是足迹 */
                k.indexOf('shred:') === 0 ||
                /* R3343：couple:shared 内嵌规范生日串（PII）+ 同步
                 * 时间戳——「忘掉我的数据」必须收。 */
                k.indexOf('couple:') === 0 ||
                /* R3358：轻账号凭据也是个人数据——「忘掉」要登出。 */
                k.indexOf('xmaccount') === 0 ||
                /* R3389（审-高）：默契挑战（昵称+答题记录+默契榜）、
                 * 每日一签、显化打卡三族个人足迹此前漏出 wipe 清单
                 * ——「忘掉我的数据」后幸存=隐私破洞，收。 */
                k.indexOf('mochi:') === 0 ||
                k.indexOf('qian:') === 0 ||
                k.indexOf('manifest:') === 0 ||
                /* R3394：答案之书问句/翻页足迹属个人数据——wipe 收。 */
                k.indexOf('ansb:') === 0)) _rm.push(k);
          }
          _rm.forEach(function (k) { localStorage.removeItem(k); });
          /* R2349q（R82-P1-3）：chatSessionId/chatTranscript/lastResult:*
           * 在 sessionStorage——wipe 只扫 localStorage 时聊天数据全幸存。
           * 连同活跃会话快照一起清。 */
          /* R2349y（R95-P2-2）：shareBy/shareBy:done 留着的是「发起人
           * 昵称」——他人昵称属个人信息，一起清。 */
          var _sr = [];
          for (var j2 = 0; j2 < sessionStorage.length; j2++) {
            var sk = sessionStorage.key(j2);
            /* R3261（R15）：ly:lastq/ly:lastcast 存的是六爻问句原文
             * ——「忘掉我的数据」后问题幸存=隐私破洞，收进清单；
             * chatBootId 一并清（重启失忆一致性）。 */
            /* R3339（审-低）：chatClosed 独漏——同类键全收了它不收，
             * 「开新话题」残留跨「忘掉」幸存。 */
            if (sk && (/^(chatSessionId|chatTranscript|trAskedToday|hhInvite|shareBy|shareBy:done|chatTopicFactDone|chatCardsFactDone|chatBootId|ly:lastq|ly:lastcast|chatClosed)$/
                .test(sk) || sk.indexOf('shareBy:') === 0 ||
                sk.indexOf('lastResult:') === 0)) _sr.push(sk);
          }
          _sr.forEach(function (k) { sessionStorage.removeItem(k); });
        } catch (e) {}
        /* R2349y（R95-P1-2）：sessionStorage 被禁时聊天 sid/记录落
         * 页内存 _MEM_STORE——上面那轮遍历碰不到它，wipe 后同 tab
         * 继续聊会接回服务端旧 sid（含昵称/生辰 facts）——「忘掉」
         * 破洞。内存面一并清。 */
        try { _MEM_STORE._m = {}; } catch (eM) {}
        /* R2349y（R95-P2-2）：分享者昵称/邀请发起人/上次日签的
         * 内存态同样要清。 */
        try { window.__shareBy = ''; } catch (eSB) {}
        try { window.__hhInviteBy = ''; } catch (eHI) {}
        try { window.__lastDaily = null; } catch (eLD) {}
        /* R3339（审-高）：__meSessionMap 是会话内存档（隐私模式回落面）
         * ——wipe 不清它，_meGet 立刻把已删生辰返给档案条/_chatFacts，
         * 「忘掉一切」同会话内形同虚设（实测 hidden=false 复活）。 */
        try { window.__meSessionMap = {}; } catch (eMSM) {}
        /* R3339（审-中）：已擦问句会在下一条聊天以「她上次来聊过」
         * 注入——wipe 不落这股内存态，旧问句跨「忘掉」进 LLM 请求。 */
        try { CHAT_RESUME_FACT = ''; } catch (eRF) {}
        /* R3339（审-中）：邀请/话题内存态越「忘掉」仍生效——
         * hehun 受邀位判定与待办话题一并置空。 */
        try { window.__shareFromView = null; } catch (eFV) {}
        try { window.__hhInviteMode = null; } catch (eIM) {}
        try { window.__chatPendingEvt = null; } catch (ePE) {}
        /* R2349t（R87-P1-2）：wipe 复活封堵——只清存储键不够：
         * ① 各表单里已回填的生辰还在，任一点击就把档案写回；
         * ② LAST_RESULT/CHAT_LAST_FACTS 内存态还带已删上下文；
         * ③ _trAsked 内存集不清。一并收口。 */
        try {
          ['year', 'month', 'day', 'hour', 'gender',
           'b_year', 'b_month', 'b_day', 'b_hour', 'b_gender', 'b_nick',
           'th_year', 'th_month', 'th_day', 'th_hour', 'th_gender',
           'hh_a_year', 'hh_a_month', 'hh_a_day', 'hh_a_hour',
           'hh_a_gender', 'hh_a_name',
           'hh_b_year', 'hh_b_month', 'hh_b_day', 'hh_b_hour',
           'hh_b_gender', 'hh_b_name'].forEach(function (_fid) {
            var _f = document.getElementById(_fid);
            /* R2349y（R95-P2-3）：手输的生日（input 事件即删
             * data-me 标记）、邀请链字段（data-invite）此前漏清——
             * wipe 语义是「忘掉」全部个人字段，不是只清回填的。 */
            if (_f) {
              _f.value = '';
              delete _f.dataset.me;
              delete _f.dataset.invite;
              delete _f.dataset.touched;
            }
          });
        } catch (e2a) {}
        /* R2349y（R95-P3-6）：聊天侧栏气泡同 tab 还挂着旧对话——
         * 顺手清 DOM（存储已清，纯观感一致）。 */
        try {
          var _cf = document.getElementById('chatFlow');
          if (_cf) _cf.innerHTML = '';
        } catch (eCF) {}
        try { LAST_RESULT = {}; } catch (e2b) {}
        try { if (typeof CHAT_LAST_FACTS !== 'undefined') CHAT_LAST_FACTS = []; } catch (e2c) {}
        try { _trAsked = null; } catch (e2d) {}
        try { sessionStorage.removeItem('chatBootId'); } catch (e2e) {}
        try { renderCheckin(todayIso()); } catch (e2f) {}
        try { _renderMeStrip(); } catch (e2) {}
        /* R3358：wipe 已收 xmaccount 凭据——账号卡回到未登录态。 */
        try { if (window.__acctRender) window.__acctRender(); } catch (eAR) {}
        /* R3328（审-低）：loadPaipanHistory 重渲会顺手重建
         * paipan_mirror_v1 空镜像——「忘掉」后连镜像壳也不留，
         * 重渲落定后再擦一遍镜像键。 */
        try {
          var _pr = loadPaipanHistory();
          if (_pr && _pr.then) _pr.then(function () {
            ['paipan_mirror_v1', 'paipan_mirror_del_v1']
              .forEach(function (mk) {
                try { localStorage.removeItem(mk); } catch (e) {}
              });
          }, function () {});
        } catch (e3) {}
        /* R2349y（R95-P1-3/P3-9）：写完才落 wipeAt 墓碑（先写会被
         * 上面的清扫误删）——其他 tab 收到事件自清表单/会话态；
         * 台账 dirty 广播让其他 tab 的历史列表就地刷新。 */
        try { localStorage.setItem('wipeAt', String(Date.now())); } catch (eWA) {}
        try {
          if (window.BroadcastChannel) {
            new BroadcastChannel('paipan_history').postMessage('dirty');
          }
        } catch (eBC) {}
        showToast(serverOk
          ? '都忘掉啦，本机档案和台账都空了'
          : '本机档案清了，台账没连上：联网后再点一次', serverOk ? 'info' : 'warn');
      };
      /* R2349（R65-P1-2）：收藏表（合婚CP/心水名单）含双方生辰+昵称，
       * 「忘掉我的数据」承诺必须覆盖——与台账一起清。
       * R2400（R138-P1-3）：研究线程/手记（knowledge.db）此前无删除
       * 路径——点「忘掉」后还残留在服务端。逐条 DELETE 一并清。 */
      /* R2500（R143-P1-3/P2-4）：改调全清端点——逐条 DELETE 只够到前
       * 50 条（51+ 连全部 turn 留库）且 derived claims 原文不清；
       * 「忘掉」语义必须覆盖整表。 */
      var _threadsDel = api('/api/threads', { method: 'DELETE', silent: true })
        .catch(function () {});
      /* R3339（审-低）：user_prefs 表（recent/死写端点攒的键）也在
       * 「忘掉」面里——theme 后端刻意保留。 */
      var _prefsDel = api('/api/user/prefs', { method: 'DELETE', silent: true })
        .catch(function () {});
      Promise.all([
        phFetch('/api/paipan/history', { method: 'DELETE' }),
        phFetch('/api/favorites', { method: 'DELETE' }),
        _threadsDel,
        _prefsDel
      ]).then(function () { _phMirrorClear(); _favMirrorClear(); _favListInvalidate(); _done(true); })
        /* R2400（R127-P2-1）：云端没连上时本机镜像也一并清（_done
         * 里的键扫描已收镜像键）——不然「本机档案清了」是假的。 */
        .catch(function () { _phMirrorClear(); _favMirrorClear(); _done(false); });
    });
    /* R3358：轻账号（昵称+口令码）。凭据存 xmaccount={n,p}——口令码
     * 即登录钥匙，6 位码明文存本机是轻账号的通行口径（不是银行密
     * 码）；「忘掉我的数据」连它一起清（wipe 正则已收）。 */
    var _acctCard = document.getElementById('accountCard');
    if (_acctCard) (function () {
      var _KEY = 'xmaccount';
      var _SYNC_KEY = 'xmaccount:lastsync';
      /* R3363-P2-10：拉回也留个戳——「上次同步」只记上传会让
       * 刚拉回的用户以为自己没拉上。 */
      var _PULL_KEY = 'xmaccount:lastpull';
      /* R3363-P1-7：本机数据的「上一任主人」——登 A 号登 B 号时
       * 残留私密键会混进 B 的备份推上云，靠它判要不要先清扫。 */
      var _OWNER_KEY = 'xmaccount:owner';
      /* R3363-P1-8：设备戳打进备份包——拉回时发现包是别的设备
       * 最近传的，能提醒「另一台设备有更新」。 */
      var _DEV_KEY = 'xmaccount:dev';
      var _PEND_KEY = 'xmaccount:pending';
      /* R3372-P2-1：云端备份的 updated_at 戳——push 带上做乐观
       * 并发前置，另一台设备先推过就拒写回来提示先拉回。 */
      var _CLOUDTS_KEY = 'xmaccount:cloudts';
      /* R3363-P1-2/P1-7：备份白名单键族——拉回快照 diff 与
       * 跨账号清扫共用同一张口径表（与导入白名单同族）。 */
      /* R3372-P2-2：_DATA_RE 已上移到 phBind 顶（共享唯一定义）——
       * 本 IIFE 直接引用外层变量，不再另存一份。 */
      function _dataKeys() {
        var _ks = [];
        try {
          for (var _i = 0; _i < localStorage.length; _i++) {
            var _k = localStorage.key(_i);
            if (_k && _DATA_RE.test(_k)) _ks.push(_k);
          }
        } catch (e) {}
        return _ks;
      }
      function _devId() {
        var _dv = '';
        try {
          _dv = localStorage.getItem(_DEV_KEY) || '';
          if (!_dv) {
            _dv = Math.random().toString(36).slice(2, 10);
            localStorage.setItem(_DEV_KEY, _dv);
          }
        } catch (e) {}
        return _dv;
      }
      function _clearAccountKeys() {
        /* R3363-P2-13：threads_seen_v1 已读标记也是跟账号走的——
         * 切号后沿用上任的已读=串味，收进清除面。 */
        [_SYNC_KEY, _PULL_KEY, _PEND_KEY, _CLOUDTS_KEY,
         'paipan_mirror_v1', 'paipan_mirror_del_v1',
         'favorites_mirror_v1', 'threads_mirror_v1',
         'threads_seen_v1'].forEach(function (mk) {
          try { localStorage.removeItem(mk); } catch (e) {}
        });
      }
      function _sweepForNewOwner() {
        /* R3363-P1-7：换号前的本机清扫——把上一任留下的白名单
         * 私密键与视图键全收，再拉回，不碰新凭据/设备戳/owner。 */
        /* R3372-P2-2a：sessionStorage 也进清扫面——hhInvite/shareBy*/
        /* shareBy:* /chatSessionId 等跟「这个人」绑的键此前换主
         * 后残留（wipe 收、这里漏），B 会看到 A 的邀请态与会话锚。 */
        _dataKeys().forEach(function (k) {
          try { localStorage.removeItem(k); } catch (e) {}
        });
        try {
          var _ss = [];
          for (var _si = 0; _si < sessionStorage.length; _si++) {
            var _sk = sessionStorage.key(_si);
            if (_sk && _SDATA_RE.test(_sk)) _ss.push(_sk);
          }
          _ss.forEach(function (k) {
            try { sessionStorage.removeItem(k); } catch (e) {}
          });
        } catch (eSS) {}
        _clearAccountKeys();
      }
      var _nick = document.getElementById('acctNick');
      var _pass = document.getElementById('acctPass');
      var _form = document.getElementById('acctForm');
      var _logged = document.getElementById('acctLogged');
      var _status = document.getElementById('acctStatus');
      var _who = document.getElementById('acctWho');
      var _lastSync = document.getElementById('acctLastSync');
      var _backend = '', _issue = '';
      function _creds() {
        try {
          var cj = JSON.parse(localStorage.getItem(_KEY) || 'null');
          return (cj && cj.n && cj.p) ? cj : null;
        } catch (e) { return null; }
      }
      function _saveCreds(n, p) {
        try {
          localStorage.setItem(_KEY, JSON.stringify({ n: n, p: p }));
        } catch (e) {}
      }
      function _acctRender() {
        var c = _creds();
        if (c) {
          _form.hidden = true;
          _logged.hidden = false;
          _who.textContent = c.n;
          var _ls = '', _lp = '';
          try { _ls = localStorage.getItem(_SYNC_KEY) || ''; } catch (e) {}
          try { _lp = localStorage.getItem(_PULL_KEY) || ''; } catch (e) {}
          _lastSync.textContent = _ls
            ? ('上次上传 ' + _ls + (_lp ? ' · 上次拉回 ' + _lp : ''))
            : (_lp ? ('没传过 · 上次拉回 ' + _lp) : '还没同步过');
        } else {
          _form.hidden = false;
          _logged.hidden = true;
        }
        /* R3362（R3361 审-P1）：「存本机库」是工程黑话——明说能力
         * 边界：本地后端上注册登录能用，但服务端一清盘什么都没了。 */
        _status.textContent = _issue ? _issue
          : (_backend === 'libsql'
            ? '云端已接' : (_backend === 'local'
              ? '云端没接通——备份留不住，换设备拉不回' : '查一下云端…'));
      }
      window.__acctRender = _acctRender;
      /* R3363-P1-5：B tab 的 storage 事件报「凭据换了昵称」——
       * 免登出切号也要走登出同款的镜像/戳清除，不然新账号看到
       * 旧账号的视图、还把数据推串号。 */
      window.__acctCredsChanged = function (oldRaw) {
        try {
          var _oc = JSON.parse(oldRaw || 'null');
          var _nc = _creds();
          if (_oc && _oc.n && _nc && _nc.n !== _oc.n) {
            /* R3372-P0-2b：多 Tab 换主同口径——只清镜像不够，共享
             * localStorage 里 A 的私密键会混进 B 的自动推；与
             * 单 Tab 换主同款，整份清扫（幂等，与发起 tab 互补）。 */
            _sweepForNewOwner();
          }
        } catch (e) {}
      };
      var _syncBusy = false, _pullBusy = false;
      async function _push(showOk, keepAlive) {
        var c = _creds();
        if (!c) return;
        /* R3363-P2-11：拉回在途时 push 会和导入交错产出撕裂
         * bundle（LS 段与服务端段取自不同时刻）——等拉回落地。 */
        if (_pullBusy) {
          var _wP = Date.now();
          while (_pullBusy && Date.now() - _wP < 15000) {
            await new Promise(function (r) { setTimeout(r, 200); });
          }
          if (_pullBusy) return;
        }
        /* R3362（冒烟实锤）：手动点「立刻同步」撞上自动推在途——
         * 旧版静默 return，用户点了没反应。手动点等在途落完再推。 */
        if (_syncBusy) {
          if (!showOk) return;
          var _w0 = Date.now();
          while (_syncBusy && Date.now() - _w0 < 15000) {
            await new Promise(function (r) { setTimeout(r, 200); });
          }
          if (_syncBusy) {
            showToast('同步还在路上，稍等下再点', 'warn');
            return;
          }
        }
        _syncBusy = true;
        try {
          var bundle = await _buildBackupBundle();
          delete bundle._noLedger;
          /* R3362（R3359 审-P2）：payload 服务端帽 1.2MB——台账/线程
           * 养肥后超限恒 422，自动推静默失败用户以为在同步。超限先
           * 裁尾部台账与线程，保住偏好与近期记录。 */
          /* R3363-P1-8：备份包带设备戳——拉回时发现「这包不是我
           * 这台最近传的」能点出多设备在同时写。 */
          bundle.dev = _devId();
          bundle.ver2 = 1;
          var _pl = JSON.stringify(bundle);
          /* R3363-P1-3：keepalive 体上限 64KiB——养肥的备份必
           * 超限，hide 保命推静默 TypeError。 */
          /* R3372-P0-1：缩水包绝不上云——此前超限只推偏好段，
           * 服务端无条件覆盖会把云端全量降成 ~370B 空壳，台账
           * /收藏/线程静默蒸发。超限就放弃本次推（数据在本机
           * 完好），置 pending 由开页/下次前台推补回全量。 */
          if (keepAlive && _pl.length > 60000) {
            try { localStorage.setItem(_PEND_KEY, '1'); } catch (e) {}
            return;
          }
          var _trimmed = false;
          while (_pl.length > 1100000) {
            var _cut = false;
            if (Array.isArray(bundle.records) && bundle.records.length) {
              bundle.records.pop(); _cut = true;
            }
            if (Array.isArray(bundle.threads) && bundle.threads.length) {
              bundle.threads.pop(); _cut = true;
            }
            if (!_cut) break;
            _trimmed = true;
            _pl = JSON.stringify(bundle);
          }
          /* R3362（R3359 审-P0）：必须走 postJSON——裸 api() POST 不
           * 带 Content-Type，浏览器发 text/plain 恒 422。 */
          /* R3372-P2-1：带上本机记的云端戳——另一台设备先推过
           * 服务端拒写回 conflict，不再静默 LWW 互踩。 */
          var _cts = null;
          try { _cts = localStorage.getItem(_CLOUDTS_KEY) || null; }
          catch (eC) {}
          var r = await postJSON('/api/account/backup/push', {
            nickname: c.n, passcode: c.p, payload: _pl,
            base_updated_at: _cts },
            { silent: !showOk, keepalive: !!keepAlive });
          if (r && r.ok && _trimmed && showOk) {
            showToast('数据攒多了——云里只带了近期部分', 'warn');
          }
          if (r && r.ok) {
            try {
              localStorage.setItem(_SYNC_KEY,
                new Date().toLocaleString('sv').slice(0, 16));
              if (r.updated_at) {
                localStorage.setItem(_CLOUDTS_KEY, r.updated_at);
              }
              if (_pl.length <= 60000 || !keepAlive) {
                localStorage.removeItem(_PEND_KEY);
              }
            } catch (e) {}
            _acctRender();
            if (showOk) {
              showToast('同步好啦，换台设备登这个名字就能拉回', 'info');
            }
          } else if (r && r.conflict) {
            /* R3372-P2-1：并发冲突——云端戳记下，提示先拉回；
             * 不 showOk 的静默推也照样提示（这是数据安全问题）。 */
            try {
              if (r.updated_at) {
                localStorage.setItem(_CLOUDTS_KEY, r.updated_at);
              }
            } catch (eU) {}
            showToast(r.msg ||
              '另一台设备刚推了新备份——先点「从云端拉回」再同步',
              'warn');
          } else if (showOk) {
            showToast((r && r.msg) || '没同步上，过会儿再试', 'warn');
          }
        } catch (e) {
          if (showOk) {
            showToast('没同步上：' + _humanizeErr(e.message || e), 'warn');
          }
        } finally { _syncBusy = false; }
      }
      window.__acctPush = _push;
      var _pullArm = false, _pullArmT = null;
      async function _pull() {
        var c = _creds();
        if (!c) return;
        /* R3363-P2-11：零在途锁时双点=双份导入（双倍请求+双 toast）；
         * 与 push 互不感知还会产出撕裂 bundle。 */
        if (_pullBusy) {
          showToast('拉回还在路上，稍等下', 'warn');
          return;
        }
        _pullBusy = true;
        /* R3363-P1-2：拉回发起时给白名单键拍快照——在途窗口里
         * 本机被改的键（刚写的心情/刚打的卡）不该被云端旧值盖掉，
         * 落地时 diff 保住本机新值并点名。 */
        var _snap = {};
        _dataKeys().forEach(function (k) {
          try { _snap[k] = localStorage.getItem(k); } catch (e) {}
        });
        try {
          var r = await postJSON('/api/account/backup/pull', {
            nickname: c.n, passcode: c.p }, { silent: true });
          if (r && r.ok && r.payload) {
            try {
              var _b0 = JSON.parse(r.payload);
              var _ex = Date.parse((_b0 && _b0.exported_at) || '');
              var _ls0 = Date.parse(
                (localStorage.getItem(_SYNC_KEY) || '')
                .replace(' ', 'T'));
              /* R3363-P2-9：原生 confirm 换两段式按钮（全站口径）——
               * 云端比本机上次同步旧 60s+，再点一次才拉回。 */
              if (_ex && _ls0 && _ex < _ls0 - 60000 && !_pullArm) {
                _pullArm = true;
                if (_pullArmT) clearTimeout(_pullArmT);
                _pullArmT = setTimeout(function () {
                  _pullArm = false;
                }, 8000);
                showToast('云端这份比本机上次传的旧，会盖掉较新的' +
                          '东西——8 秒内再点一次「从云端拉回」确认',
                          'warn');
                return;
              }
              _pullArm = false;
              /* R3363-P1-8：包上设备戳与本机不同且比上次上传
               * 新——另一台设备刚写过，点一句不拦路。 */
              if (_b0 && _b0.dev && _b0.dev !== _devId() &&
                  _ex && _ls0 && _ex > _ls0 + 60000) {
                showToast('另一台设备最近也同步过——已拉回最新这份',
                          'info');
              }
              /* R3363-P2-14：旧版页面打的包没有 ver2——新功能的
               * 键可能没带，明说不静默。 */
              if (_b0 && !_b0.ver2) {
                showToast('这份备份是旧版本打的，新功能的数据可能' +
                          '没带齐', 'warn');
              }
            } catch (eCmp) {}
            await _importBackupText(r.payload,
              { changed: _snap });
            try {
              localStorage.setItem(_PULL_KEY,
                new Date().toLocaleString('sv').slice(0, 16));
              /* R3372-P2-1：拉回后记云端戳——下次 push 以这份为
               * 基线，刚拉过的版本再推回不会误报冲突。 */
              if (r.updated_at) {
                localStorage.setItem(_CLOUDTS_KEY, r.updated_at);
              }
            } catch (e) {}
            /* R3363-P1-6：拉回后本 tab 各视图（档案条/打卡/心情/
             * 主题/账号卡）全是旧渲染，反而是别的 tab 靠 storage
             * 事件更新了——低频大动作直接重载最一致。 */
            /* R3370-低-11：1.2s 重载把「导入好了」toast 几乎瞬杀
             * ——拉到 3.5s 让确认读得完。 */
            setTimeout(function () {
              try { location.reload(); } catch (eRL) {}
            }, 3500);
          } else {
            showToast((r && r.msg) || '云端还没有备份', 'warn');
          }
        } catch (e) {
          showToast('拉不回来：' + _humanizeErr(e.message || e), 'error');
        } finally { _pullBusy = false; }
      }
      function _readFields() {
        var n = (_nick.value || '').trim();
        var p = (_pass.value || '').trim();
        if (!n) { showToast('先给自己起个名', 'warn'); return null; }
        if (p.length < 6) {
          showToast('口令码至少 6 位', 'warn');
          return null;
        }
        return { n: n, p: p };
      }
      document.getElementById('acctRegister')
        .addEventListener('click', async function () {
          var f = _readFields();
          if (!f) return;
          try {
            var r = await postJSON('/api/account/register', {
              nickname: f.n, passcode: f.p }, { silent: true });
            if (r && r.ok) {
              /* R3363-P1-7b：注册同样要查前任——共用设备上上一任
               * 没登出，新号注册首推会把 TA 的私密键一起送进
               * 新账号的云备份，先清扫再推。 */
              var _prevReg = '';
              try { _prevReg = localStorage.getItem(_OWNER_KEY) || ''; } catch (e) {}
              if (_prevReg && _prevReg !== f.n) {
                _sweepForNewOwner();
                showToast('本机留着「' + _prevReg +
                  '」的数据，已替你清干净', 'info');
              }
              _saveCreds(f.n, f.p);
              try { localStorage.setItem(_OWNER_KEY, f.n); } catch (e) {}
              /* R3372-低-5：localStorage 硬禁（极端隐私模式）时凭据
               * 落不了盘——注册在服务端建成了但登录态留不住，明说
               * 不然刷新就变陌生人用户还以为是 bug。 */
              if (!_creds()) {
                showToast('这个浏览器存不了登录态（可能是极致隐私模式）' +
                          '——刷新后要重新登录', 'warn');
              }
              _acctRender();
              showToast('注册好啦，正在给你同步第一份备份', 'info');
              /* R3363-P1-4：注册首推用 keepalive——注册即关页时
               * 普通 fetch 会被掐，首份备份静默丢（此时包小，不
               * 会撞 64KiB 上限）。 */
              _push(false, true);
            } else {
              showToast((r && r.msg) || '没注册上，过会儿再试', 'warn');
            }
          } catch (e) {
            showToast('没注册上：' + _humanizeErr(e.message || e), 'error');
          }
        });
      document.getElementById('acctLogin')
        .addEventListener('click', async function () {
          var f = _readFields();
          if (!f) return;
          try {
            var r = await postJSON('/api/account/login', {
              nickname: f.n, passcode: f.p }, { silent: true });
            if (r && r.ok) {
              /* R3363-P1-7：登 A 号再登 B 号——本机残留的 A 私密
               * 键（心情/日记/聊天）会先清扫再拉回，不然下回自动推
               * 把 A 的东西打进 B 的云备份。 */
              var _prevOwner = '';
              try {
                _prevOwner = localStorage.getItem(_OWNER_KEY) || '';
              } catch (e0) {}
              if (_prevOwner && _prevOwner !== f.n) {
                _sweepForNewOwner();
                showToast('这台设备上还有上一个账号的数据，' +
                          '已经帮你清开', 'info');
              }
              _saveCreds(f.n, f.p);
              try { localStorage.setItem(_OWNER_KEY, f.n); } catch (e) {}
              /* R3372-低-5：localStorage 硬禁时登录态留不住，明说。 */
              if (!_creds()) {
                showToast('这个浏览器存不了登录态（可能是极致隐私模式）' +
                          '——刷新后要重新登录', 'warn');
              }
              _acctRender();
              /* 登录即拉回——这是换设备的主场景；云端没备份时
               * _pull 会明说「先在原设备同步一次」。 */
              await _pull();
            } else {
              showToast((r && r.msg) || '名字或口令码不对', 'warn');
            }
          } catch (e) {
            showToast('登不上：' + _humanizeErr(e.message || e), 'error');
          }
        });
      document.getElementById('acctSyncNow')
        .addEventListener('click', function () { _push(true); });
      document.getElementById('acctPull')
        .addEventListener('click', function () { _pull(); });
      document.getElementById('acctLogout')
        .addEventListener('click', function () {
          try {
            localStorage.removeItem(_KEY);
            /* R3362（R3359/60 审-P2/P1）：lastsync 与四组镜像键是
             * 跟「这个账号」绑的视图——登出不收，下个账号先看到别人
             * 的同步时间与旧镜像行（跨账号串味）。 */
            /* R3372-P0-2：owner 要留到下一任落地——登出删它会让
             * 换主清扫永不可达（登录侧 _prevOwner 恒空），A 的私密
             * 键原样混进 B 的云备份。同号再登不触发清扫，数据留住。 */
            _clearAccountKeys();
          } catch (e) {}
          _acctRender();
          showToast('已退出——云端备份还在，哪天登回来就能拉回', 'info');
        });
      /* 后台/关页时自动推一份——visibilitychange 比 beforeunload
       * 在移动端靠谱（iOS 不一定给 unload 机会）。
       * R3362（R3359 审-P2）：普通 fetch 在 hidden/关页时可能被
       * 浏览器直接掐断——keepalive:true 让请求熬过页面隐藏。 */
      document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden' && _creds()) {
          _push(false, true);
        }
      });
      /* 云端形态探测：libsql=生产态；local=本机兜底（明说）。 */
      api('/api/account/status', { silent: true }).then(function (r) {
        _backend = (r && r.backend) || '';
        /* R3362（R3360 审-P2）：半配状态（只配 URL 或 token 之一）
         * 此前显示「云端已接」而全请求 401——issue 原样上屏点名。 */
        _issue = (r && r.issue) || '';
        _acctRender();
      }).catch(function () { _acctRender(); });
      _acctRender();
      /* R3372-P0-1b：pending 真消费——上次后台 keepalive 推被
       * 跳过时留下标记；开页有凭据就补推一份全量，不让云端
       * 停在旧包（此前 pending 只写不读=死代码，云端永远补不回）。 */
      try {
        if (localStorage.getItem(_PEND_KEY) === '1' && _creds()) {
          _push(false, false);
        }
      } catch (eP2) {}
    })();
    var _imb = document.getElementById('historyImportBtn');
    var _imf = document.getElementById('historyImportFile');
    if (_imb && _imf) {
      _imb.addEventListener('click', function () {
        /* R2500（R143-P2-8）：触屏/微信里导出是文本弹层「贴回导入」——
         * 导入侧同样给文本弹层，闭环对称；桌面端照旧文件选择器。 */
        if (_exportShowOnly()) { _showTextImportModal(_importBackupText); }
        else { _imf.click(); }
      });
      _imf.addEventListener('change', async function () {
        var f = _imf.files && _imf.files[0];
        _imf.value = '';
        if (!f) return;
        /* R2349y（R95-P2-6）：超大文件全量读入会冻结 tab——20MB 上限；
         * version 不校验则未来结构变更会按 v1 静默半导入。 */
        if (f.size > 20 * 1024 * 1024) {
          showToast('备份太大啦，换个小点的试试', 'warn');
          return;
        }
        await _importBackupText(await f.text());
      });
    }
  }
  /* R2500（R143-P2-8）：备份导入主路径抽成文本入口——文件读入与
   * 粘贴弹层共用。 */
  async function _importBackupText(_txt, _opt) {
        /* R3363-P1-1：wipe 墓碑——拉回/导入在途时用户点「忘掉
         * 我的数据」，落地写键前必须重看墓碑，不然已擦键复活。 */
        var _wipe0 = null;
        try { _wipe0 = localStorage.getItem('wipeAt'); } catch (eW0) {}
        /* R3363-P1-2：_opt.changed={键:快照值}——拉回发起时拍的
         * 本机值；落地发现键在途被改过，保住本机新值不盖。 */
        var _changed = (_opt && _opt.changed) || null;
        var _kept = [];
        var bundle = null;
        try { bundle = JSON.parse(_txt); } catch (ePJ) {}
        if (bundle && bundle.kind === 'backup' && bundle.version === 1) {
          /* ok */ } else if (bundle && bundle.kind === 'backup') {
          showToast('这版备份格式不认识：用小满最新版导出的再试', 'warn');
          return;
        } else if (bundle) {
          showToast('这不是小满的备份文件', 'error');
          return;
        } else {
          /* R3320-P1-1②：解析失败与传输失败分说——JSON 都读不出来
           * 才说「读不懂」，网络断不能背这个锅。 */
          showToast('备份文本没贴全——从开头到结尾原样整段贴进来',
            'error');
          return;
        }
        try {
          /* R3363-P1-1：写键前重看墓碑——在途期间本机刚 wipe
           * 过就不能落，已擦键复活=「忘掉」承诺破洞。 */
          try {
            if (localStorage.getItem('wipeAt') !== _wipe0) {
              showToast('刚「忘掉一切」过，这份导入没落进去', 'warn');
              return;
            }
          } catch (eW1) {}
          var local = bundle.browser || {};
          Object.keys(local).forEach(function (k) {
            /* 只收认识的键——备份文件是用户可控输入，不写任意键 */
            /* R2349t（R87-P1-1）：checkin: 值直拼 innerHTML——值域
             * 收进词表白名单（词表外的签名存进来也是炸渲染的脏值）；
             * 键名限长——「checkin:」+8000 字符键此前照存。 */
            /* R2349y（R95-P2-1）：checkinCeleb:/ret_tip 导得出导不回
             * ——收进白名单。 */
            /* R3314（R3310-P1）：备份导出含心情/仪式/足迹全家桶，导入
             * 侧白名单此前只有老键族——mood/moodlv/moodjar/journal/
             * ritual/usage/read:scroll/rlast/chat:events/notify:time/
             * returnBannerDismissed 全被静默丢弃=换机丢档。补齐并逐族
             * 做形状校验（备份文件是用户可控输入，校验口径与导出对齐）。 */
            /* R3329（审-P1）：futureLetters/pilePick:/weeklyLetter:/
             * monthlyLetter: 导得出导不回——换机丢信丢选堆。补齐
             * 白名单并逐族做形状校验（用户可控输入）。 */
            /* R3336（审-中）：checkinBuff: 导得出导不回（静默丢 buff）
             * + wishfulfilled（成真集）+ futureLetters:corrupt 收编，
             * 逐族形状校验。 */
            /* R3339（审-低）：voiceMode 是下线死键——白名单收它等于
             * 旧备份往本机种死数据，剔除。 */
            /* R3350：mantraFav（咒语册）同族收编——导得出也要导得回。 */
            /* R3351（审-P1）：couple:/shred: 同族收编——合拍交集与
             * 碎纸计数换机不再静默丢。 */
            /* R3354（审-P1）：chatTranscript 族同收编——导得出
             * 导不回，换机聊天记录静默丢。(:|$) 同时覆盖裸键。 */
            /* R3372-P2-2：导入白名单同样收敛到共享 _DATA_RE——
             * remind: 前缀、uiTheme 等口径与导出/清扫一致；
             * _NO_BACKUP_RE 拦死键/会话锚不被旧备份复活。 */
            if (!_DATA_RE.test(k) || _NO_BACKUP_RE.test(k) ||
                k.length > 64 ||
                typeof local[k] !== 'string' || local[k].length >= 8192) {
              return;
            }
            /* 值域校验（脏值不落库）：
             * mood:<date>=0-3；moodlv:<date> 与 mood:lv=g/l；
             * moodjar:total/unlocked=非负整数；ritual:<date>=1；
             * usage:v/d:=非负整数/1；rlast/usage:first/returnBannerDismissed
             * =日期；read:scroll:*=非负整数；notify:time=HH:MM；
             * chat:events=JSON 数组。 */
            var _v = local[k];
            /* R3328（审-低）：mood:dream:* 是自由文本梦境随记——
             * 被 mood: 值校验 ^[0-3]$ 误杀，排除本检查。 */
            if (k.indexOf('mood:') === 0 && k !== 'mood:lv' &&
                k.indexOf('mood:dream:') !== 0 &&
                !/^[0-3]$/.test(_v)) return;
            /* R3328（审-低）：mood:dream 值只限长——形状已由
             * 键尾日期校验担。 */
            if (k.indexOf('mood:dream:') === 0 && _v.length > 500) return;
            /* R3328（审-中）：checkin:goal（周目标数）与
             * checkin:goal-celebrated:<date>（里程碑已弹标）在导出
             * 白名单里却被日期尾段+词表校验误杀——单独形态放行。 */
            if (k === 'checkin:goal' &&
                !(/^\d{1,2}$/.test(_v) && +_v >= 1 && +_v <= 30)) return;
            if (k.indexOf('checkin:goal-celebrated:') === 0 &&
                (!/^\d{4}-\d{2}-\d{2}$/.test(k.slice(24)) ||
                 _v !== '1')) return;
            if ((k === 'mood:lv' || k.indexOf('moodlv:') === 0) &&
                !/^[gl]$/.test(_v)) return;
            if (k.indexOf('moodjar:') === 0 && !/^\d+$/.test(_v)) return;
            if (k.indexOf('ritual:') === 0 &&
                (!/^\d{4}-\d{2}-\d{2}$/.test(k.slice(7)) || _v !== '1'))
              return;
            if (k.indexOf('usage:v:') === 0 && !/^\d+$/.test(_v)) return;
            if (k.indexOf('usage:d:') === 0 &&
                (!/^\d{4}-\d{2}-\d{2}$/.test(k.slice(8)) || _v !== '1'))
              return;
            if (k === 'usage:first' &&
                !/^\d{4}-\d{2}-\d{2}$/.test(_v)) return;
            if (k.indexOf('rlast:') === 0 &&
                !/^\d{4}-\d{2}-\d{2}$/.test(_v)) return;
            if (k.indexOf('read:scroll:') === 0 && !/^\d+$/.test(_v)) return;
            /* R3329（审-P3）：HH:MM 形状过了 99:99 也过——补范围闸
             *（写处同闸）。 */
            if (k === 'notify:time' &&
                (!/^\d{2}:\d{2}$/.test(_v) || +_v.slice(0, 2) > 23 ||
                 +_v.slice(3) > 59)) return;
            /* R3329：新族形状校验——信：数组+id≤32/text≤1024/双日期
             * ISO/opened bool；堆：键尾日期+{i∈0-2,d.name≤64,r≤500}；
             * 周/月信已弹标：键尾 YYYY-MM 或 YYYY-MM(-DD)+值 '1'。 */
            if (k === 'futureLetters') {
              try {
                var _fa = JSON.parse(_v);
                if (!Array.isArray(_fa) || _fa.length > 50) return;
                var _fok = _fa.every(function (lt) {
                  return lt && typeof lt === 'object' &&
                    typeof lt.id === 'string' && lt.id.length <= 32 &&
                    typeof lt.text === 'string' && lt.text.length <= 1024 &&
                    /^\d{4}-\d{2}-\d{2}$/.test(lt.deliver || '') &&
                    /^\d{4}-\d{2}-\d{2}$/.test(lt.created || '') &&
                    (lt.opened === true || lt.opened === false);
                });
                if (!_fok) return;
              } catch (eFA) { return; }
            }
            if (k.indexOf('pilePick:') === 0) {
              if (!/^\d{4}-\d{2}-\d{2}$/.test(k.slice(9))) return;
              try {
                var _po = JSON.parse(_v);
                if (!_po || typeof _po !== 'object') return;
                var _pok = Object.keys(_po).every(function (tpc) {
                  var e2 = _po[tpc];
                  return e2 && typeof e2 === 'object' &&
                    (e2.i === 0 || e2.i === 1 || e2.i === 2) &&
                    e2.d && typeof e2.d.name === 'string' &&
                    e2.d.name.length <= 64 &&
                    (!e2.r || (typeof e2.r === 'string' &&
                     e2.r.length <= 500));
                });
                if (!_pok) return;
              } catch (ePA) { return; }
            }
            /* R3336（审-中）：checkinBuff:<date>={d,n}、wishfulfilled=
             * 成真集数组、futureLetters:corrupt=裸串只限长。 */
            if (k.indexOf('checkinBuff:') === 0) {
              if (!/^\d{4}-\d{2}-\d{2}$/.test(k.slice(12))) return;
              try {
                var _bo = JSON.parse(_v);
                if (!_bo || typeof _bo !== 'object' ||
                    typeof _bo.d !== 'string' || _bo.d.length > 8 ||
                    !(parseInt(_bo.n, 10) >= 1 && parseInt(_bo.n, 10) <= 9))
                  return;
              } catch (eBO) { return; }
            }
            if (k === 'wishfulfilled') {
              try {
                var _wa = JSON.parse(_v);
                if (!Array.isArray(_wa) || _wa.length > 30) return;
                var _wok = _wa.every(function (_we) {
                  return _we && typeof _we === 'object' &&
                    typeof _we.t === 'string' && _we.t.length <= 60 &&
                    (!_we.c || (typeof _we.c === 'string' && _we.c.length <= 8));
                });
                if (!_wok) return;
              } catch (eWA) { return; }
            }
            /* R3350：mantraFav=咒语册数组——[{t≤40, d:YYYY-MM-DD,
             * ts:number}]，同 wishfulfilled 族逐字段校验。 */
            if (k === 'mantraFav') {
              try {
                var _ma = JSON.parse(_v);
                if (!Array.isArray(_ma) || _ma.length > 40) return;
                var _mok = _ma.every(function (_me) {
                  return _me && typeof _me === 'object' &&
                    typeof _me.t === 'string' && _me.t.length <= 40 &&
                    /^\d{4}-\d{2}-\d{2}$/.test(_me.d || '') &&
                    typeof _me.ts === 'number';
                });
                if (!_mok) return;
              } catch (eMA) { return; }
            }
            if ((k.indexOf('weeklyLetter:') === 0 ||
                 k.indexOf('monthlyLetter:') === 0) && _v !== '1') return;
            if (k.indexOf('weeklyLetter:') === 0 &&
                !/^\d{4}-\d{2}-\d{2}$/.test(k.slice(13))) return;
            if (k.indexOf('monthlyLetter:') === 0 &&
                !/^\d{4}-\d{2}$/.test(k.slice(14))) return;
            /* R3351（审-P1）：couple:shared={ck≤128,shared日期数组
             * ≤400,total非负整数}；couple:syncts=数字戳；
             * shred:<date>=非负整数计数。 */
            if (k === 'couple:shared') {
              try {
                var _co = JSON.parse(_v);
                if (!_co || typeof _co !== 'object' ||
                    typeof _co.ck !== 'string' || _co.ck.length > 128 ||
                    !Array.isArray(_co.shared) || _co.shared.length > 400 ||
                    !_co.shared.every(function (d) {
                      return /^\d{4}-\d{2}-\d{2}$/.test(d); }) ||
                    !(Number.isInteger(_co.total) && _co.total >= 0))
                  return;
              } catch (eCO) { return; }
            }
            if (k === 'couple:syncts' && !/^\d+$/.test(_v)) return;
            if (k.indexOf('shred:') === 0 &&
                (!/^\d{4}-\d{2}-\d{2}$/.test(k.slice(6)) ||
                 !/^\d{1,4}$/.test(_v))) return;
            /* R3354（审-P1）：chatTranscript:<sid>/裸键=消息数组
             * [{r:'me'|'ai',t≤2000,a?{view≤24,label≤40,anchor≤16}}]
             * ≤50 条（与 _chatTsSave 写出口径）；:lastsid=≤64 串。 */
            if (k === 'chatTranscript:lastsid' && _v.length > 64) return;
            if (k === 'chatTranscript' ||
                (k.indexOf('chatTranscript:') === 0 &&
                 k !== 'chatTranscript:lastsid')) {
              try {
                var _ta = JSON.parse(_v);
                if (!Array.isArray(_ta) || _ta.length > 50) return;
                var _tok = _ta.every(function (_tm) {
                  return _tm && typeof _tm === 'object' &&
                    (_tm.r === 'me' || _tm.r === 'ai') &&
                    typeof _tm.t === 'string' && _tm.t.length <= 2000 &&
                    (!_tm.a || (typeof _tm.a === 'object' &&
                      typeof _tm.a.view === 'string' &&
                      _tm.a.view.length <= 24 &&
                      typeof _tm.a.label === 'string' &&
                      _tm.a.label.length <= 40 &&
                      (!_tm.a.anchor ||
                        (typeof _tm.a.anchor === 'string' &&
                         _tm.a.anchor.length <= 16))));
                });
                if (!_tok) return;
              } catch (eTS) { return; }
            }
            if (k === 'returnBannerDismissed' &&
                !/^\d{4}-\d{2}-\d{2}$/.test(_v)) return;
            if (k === 'chat:events') {
              try { if (!Array.isArray(JSON.parse(_v))) return; }
              catch (eCE) { return; }
            }
            /* R3339（审-中）：chat:topics/chat:cards 同族裸数组键零
             * 校验——'garbage-not-json' 实测原样落库还随导出再打包。
             * 照 chat:events 同款 JSON+Array 门禁。 */
            if (k === 'chat:topics' || k === 'chat:cards') {
              try { if (!Array.isArray(JSON.parse(_v))) return; }
              catch (eTC) { return; }
            }
            /* R2349y（R95-P3-1）：日期后缀键不做形状校验会收进
             * 「checkin:hello-world」这种脏格（伪造未来日永不进 GC）。
             * 三类日期键的尾段必须是合法 YYYY-MM-DD。 */
            var _dsfx = (k.indexOf('checkin:') === 0 &&
                         k !== 'checkin:goal' &&
                         k.indexOf('checkin:goal-celebrated:') !== 0)
              ? k.slice(8)
              : k.indexOf('dailyRevealed:') === 0 ? k.slice(14)
              : k.indexOf('checkinCeleb:') === 0
                ? k.slice(k.lastIndexOf(':') + 1)
              : k.indexOf('mood:dream:') === 0 ? k.slice(11)
              : k.indexOf('mood:') === 0 && k !== 'mood:lv' ? k.slice(5)
              : k.indexOf('moodlv:') === 0 ? k.slice(7)
              : k.indexOf('journal:') === 0 ? k.slice(8)
              : null;
            if (_dsfx !== null && !/^\d{4}-\d{2}-\d{2}$/.test(_dsfx)) return;
            if (k.indexOf('checkin:') === 0 &&
                k !== 'checkin:goal' &&
                k.indexOf('checkin:goal-celebrated:') !== 0 &&
                CHECKIN_OPT_POOL.indexOf(local[k]) < 0 &&
                !CHECKIN_FEEDBACK[local[k]]) {
              return;
            }
            /* R2349y（R95-P3-7）：visits/hlask 值形状校验——
             * 任意字符串入库会让计数虚高。 */
            if (k === 'visits' &&
                !/^\d{4}-\d{2}-\d{2}(,\d{4}-\d{2}-\d{2})*$/
                  .test(local[k])) return;
            if (k === 'hlask') {
              try { if (!Array.isArray(JSON.parse(local[k]))) return; }
              catch (eH) { return; }
            }
            if (k.indexOf('checkinCeleb:') === 0 && local[k] !== '1') return;
            /* R2349y（R95-P3-3）：me*.n 导入绕过 _meNickClean——
             * 脏昵称入库。解析+净化后再落。 */
            if (k === 'me' || k === 'me:partner') {
              try {
                var _mo = JSON.parse(local[k]);
                if (!_mo || typeof _mo !== 'object') return;
                _mo.n = _meNickClean(_mo.n);
                local[k] = JSON.stringify(_mo);
              } catch (eMe) { return; }
            }
            /* R2508（审-P2-1）：wishbottle 还原也要过形状校验——
             * 归一化 {t,c,ts}，脏 JSON/脏字段不直接落库（渲染层
             * 虽有 esc()，形状闸与 me 同款收口更稳）。 */
            if (k === 'wishbottle') {
              try {
                var _wo = JSON.parse(local[k]);
                if (!_wo || typeof _wo !== 'object') return;
                _wo = { t: String(_wo.t || '').slice(0, 200),
                        c: String(_wo.c || '小秘密').slice(0, 16),
                        ts: +_wo.ts || Date.now() };
                if (!_wo.t) return;
                local[k] = JSON.stringify(_wo);
              } catch (eW) { return; }
            }
            /* R3363-P1-2：拉回在途窗口里本机改过的键保住——
             * 快照值 ≠ 现值（或快照里没有这条=在途新建的），
             * 且现值与云端值不同时，留本机不盖。 */
            if (_changed) {
              try {
                var _cur = window.localStorage.getItem(k);
                var _had = Object.prototype.hasOwnProperty
                  .call(_changed, k);
                if ((_had ? _cur !== _changed[k] : _cur !== null) &&
                    _cur !== local[k]) {
                  _kept.push(k);
                  return;
                }
              } catch (eD) {}
            }
            /* R3363-P2-15：visits 导入做集合并集——整表覆盖会丢
             * 本机独有的来访日、「第 N 次开铺」计数可倒退。 */
            if (k === 'visits') {
              try {
                var _vs = {};
                String(window.localStorage.getItem('visits') || '')
                  .split(',').forEach(function (d) {
                    if (d) _vs[d] = 1;
                  });
                String(local[k]).split(',').forEach(function (d) {
                  if (d) _vs[d] = 1;
                });
                local[k] = Object.keys(_vs).sort().join(',');
              } catch (eV) {}
            }
            try { window.localStorage.setItem(k, local[k]); } catch (e) {}
          });
          /* R3372-低-3：白名单过了但形状校验没过的键此前静默丢
           * ——合法数据被误杀用户零感知。回读比对数出真实丢弃数
           * 进完成提示（visits 是并集合并不算丢，_kept 保键不算丢）。 */
          var _dropN = 0;
          Object.keys(local).forEach(function (k) {
            if (!_DATA_RE.test(k) || _NO_BACKUP_RE.test(k) ||
                k.length > 64 || typeof local[k] !== 'string' ||
                local[k].length >= 8192) return;
            if (k === 'visits' || _kept.indexOf(k) >= 0) return;
            try {
              if (window.localStorage.getItem(k) !== local[k]) _dropN++;
            } catch (eDK) {}
          });
          var n = 0, _nThr = 0;
          /* R2349y（R95-P3-5）：records 含非 dict 元素时后端
           * list[dict] 整体 422——本地键已写入才报失败，口径误导。
           * 先过滤掉。 */
          var _recs = (bundle.records || []).filter(function (r) {
            return r && typeof r === 'object' && !Array.isArray(r);
          });
          var _impBody = { records: _recs.slice(0, 500) };
          /* R2400（R138-P1-3 跟进）：备份包带的研究线程/手记同样
           * 回灌——此前只认 records 被静默丢掉。形状收敛与 records 同款。 */
          var _thr = (bundle.threads || []).filter(function (t) {
            return t && typeof t === 'object' && !Array.isArray(t);
          });
          /* R3363-P1-1：服务端台账段同受墓碑约束——拉回在途时
           * wipe 过的，records/favorites 也不再回灌进库。 */
          try {
            if (localStorage.getItem('wipeAt') !== _wipe0) {
              showToast('刚「忘掉一切」过，这份导入没落进去', 'warn');
              return;
            }
          } catch (eW2) {}
          if (_recs.length || _thr.length) {
            /* R3320-P1-1①：单次 POST 撞服务端 512KB 体界——
             * ~11 条排盘记录即 413「读不懂」。按 ~280KB 分批顺发，
             * 端点幂等去重可安全分片；threads 随首批走。 */
            var _CHUNK = 280 * 1024;
            var _batches = [], _cur = [], _curSize = 0;
            _recs.slice(0, 500).forEach(function (r) {
              var _rs = JSON.stringify(r).length + 1;
              if (_cur.length && _curSize + _rs > _CHUNK) {
                _batches.push(_cur); _cur = []; _curSize = 0;
              }
              _cur.push(r); _curSize += _rs;
            });
            if (_cur.length) _batches.push(_cur);
            var _newRecs = [];
            for (var _bi = 0; _bi < _batches.length; _bi++) {
              var _impBody = { records: _batches[_bi] };
              const rj = await postJSON('/api/paipan/history/import', _impBody);
              n += (rj.imported || 0);
              if (Array.isArray(rj.new_records)) {
                _newRecs = _newRecs.concat(rj.new_records);
              }
            }
            /* R3339（审-中）：threads 独立分批——此前挂首个 records
             * 批裸发，肥线程包破 512KB → 首个 POST 413 连坐全丢
             * （实测台账恒 0）；且 .slice(0,50) 让 51+ 线程静默丢尾。
             * 同 _CHUNK 字节预算 + schema 50 条/批双闸，批失败计数
             * 不连坐 records。单线程超预算计 skipped 不硬发。 */
            var _thrSkipped = 0;
            if (_thr.length) {
              var _tb = [], _tCur = [], _tSize = 0;
              _thr.forEach(function (t) {
                var _ts = JSON.stringify(t).length + 1;
                if (_ts > _CHUNK) { _thrSkipped++; return; }
                if (_tCur.length &&
                    (_tCur.length >= 50 || _tSize + _ts > _CHUNK)) {
                  _tb.push(_tCur); _tCur = []; _tSize = 0;
                }
                _tCur.push(t); _tSize += _ts;
              });
              if (_tCur.length) _tb.push(_tCur);
              for (var _ti2 = 0; _ti2 < _tb.length; _ti2++) {
                try {
                  const rtj = await postJSON('/api/paipan/history/import',
                    { records: [], threads: _tb[_ti2] });
                  _nThr += (rtj.threads_imported || 0);
                  _thrSkipped += (rtj.threads_truncated || 0);
                } catch (eTI) { _thrSkipped += _tb[_ti2].length; }
              }
            }
            /* R2400（R127-P2-5）：导入回灌详情——后端返回新行
             * {id,ts,name,type}，按去重键（与后端同口径截断）匹配
             * 本地 bundle 行，把完整 req/result 写进镜像详情——
             * Render 清盘后点开留档依旧有完整排盘。 */
            if (n && _newRecs.length) {
              var _mmI = _phMirrorLoad();
              var _byKey = {};
              _recs.forEach(function (r) {
                /* R2500（R143-P2-7/B1）：同 (ts,name,type) 两条不同内容
                 * 后端留第一条——本地 _byKey 也要先胜者后跳过，不然被
                 * 跳行的内容会错装到保留行的 id 上。 */
                var _bk = String(r.ts || '').slice(0, 32) + '|' +
                          String(r.name || '').slice(0, 200) + '|' +
                          String(r.type || '');
                if (!_byKey[_bk]) _byKey[_bk] = r;
              });
              _newRecs.forEach(function (nr) {
                var _row = _byKey[String(nr.ts || '') + '|' +
                                  String(nr.name || '') + '|' +
                                  String(nr.type || '')];
                if (_row) {
                  _phMirrorDetail(_mmI, {
                    id: nr.id, ts: String(nr.ts || ''),
                    name: String(nr.name || ''),
                    question: String(_row.question || '').slice(0, 200) || null,
                    type: String(nr.type || ''),
                    req: _row.req || {}, result: _row.result || {} });
                }
              });
              _phMirrorSave(_mmI);
            }
          }
          /* R2349t（R87-P1-3）：favorites 回灌——POST 端幂等去重
           * 已具备（INSERT OR IGNORE + 同键查重）。 */
          if (Array.isArray(bundle.favorites) && bundle.favorites.length) {
            var _fvN = 0, _fvBad = 0;
            for (var _fi = 0; _fi < bundle.favorites.length && _fi < 500; _fi++) {
              var _fv = bundle.favorites[_fi];
              if (!_fv || typeof _fv !== 'object') { _fvBad++; continue; }
              try {
                await postJSON('/api/favorites', {
                  type: String(_fv.type || 'misc').slice(0, 32),
                  ref_id: String(_fv.ref_id || '').slice(0, 64),
                  title: String(_fv.title || '').slice(0, 200) });
                _fvN++;
              } catch (eFI) { _fvBad++; }
            }
          }
          /* R3369（审-P1-3）：孤儿手记回灌——逐条 POST orphan:true，
           * 服务端按 claim+method 幂等去重，重灌不翻倍。 */
          var _nOrph = 0, _orphBad = 0;
          if (Array.isArray(bundle.orphan_claims) &&
              bundle.orphan_claims.length) {
            for (var _oi = 0;
                 _oi < bundle.orphan_claims.length && _oi < 200; _oi++) {
              var _oc = bundle.orphan_claims[_oi];
              if (!_oc || typeof _oc !== 'object' || !_oc.claim) {
                _orphBad++; continue;
              }
              try {
                await postJSON('/api/threads', {
                  kind: String(_oc.kind || 'note').slice(0, 32),
                  claim: String(_oc.claim || '').slice(0, 2000),
                  method: String(_oc.method || 'backup-import')
                    .slice(0, 200),
                  confidence: _oc.confidence || null,
                  orphan: true });
                _nOrph++;
              } catch (eOC) { _orphBad++; }
            }
          }
          /* R2349y（R95-P2-8/P3-8）：收藏失败条数点名，不再并进
           * 「记录」计数混口径。 */
          /* R2500（R143-P3-11）：线程不并进「记录」计数——口径分说。 */
          _favListInvalidate();
          /* R3363-P2-12：同设备登出→重登同号——记录全被去重
           * （_newRecs 空）时详情面一条不重建，清盘后留档点「查看」
           * 是空的。拉回后按去重键把 bundle 的完整 req/result 补回
           * 镜像详情（_phMirrorDetail 自带 25 条 LRU 帽）。 */
          if (_recs.length) {
            try {
              var _hl = await api('/api/paipan/history?limit=100',
                { silent: true });
              var _idByKey = {};
              ((_hl && _hl.items) || []).forEach(function (it) {
                var _hk = String(it.ts || '') + '|' +
                          String(it.name || '') + '|' +
                          String(it.type || '');
                if (!_idByKey[_hk]) _idByKey[_hk] = it.id;
              });
              if (Object.keys(_idByKey).length) {
                var _mm2 = _phMirrorLoad();
                var _seen2 = {};
                _recs.slice(0, 500).forEach(function (r) {
                  var _bk2 = String(r.ts || '').slice(0, 32) + '|' +
                            String(r.name || '').slice(0, 200) + '|' +
                            String(r.type || '');
                  /* 同去重键先胜者后跳过（与后端同口径），别让被
                   * 跳行的内容错装到保留行的 id 上。 */
                  if (_seen2[_bk2]) return;
                  _seen2[_bk2] = 1;
                  var _sid = _idByKey[String(r.ts || '') + '|' +
                                      String(r.name || '') + '|' +
                                      String(r.type || '')];
                  if (_sid != null) {
                    var _rk = String(_sid) + '|' + String(r.ts || '');
                    if (!(_mm2.details && _mm2.details[_rk])) {
                      _phMirrorDetail(_mm2, {
                        id: _sid, ts: String(r.ts || ''),
                        name: String(r.name || ''),
                        question: String(r.question || '')
                          .slice(0, 200) || null,
                        type: String(r.type || ''),
                        req: r.req || {}, result: r.result || {} });
                    }
                  }
                });
                _phMirrorSave(_mm2);
              }
            } catch (eMR) {}
          }
          var _msg = '导入好了：多了 ' + n + ' 条记录' +
            (_nThr ? ' + ' + _nThr + ' 个研究线程' : '') +
            (_fvN ? ' + ' + _fvN + ' 条收藏' : '') +
            /* R3320-P1-1③：视图其实已就地刷新——「刷新后生效」
             * 是虚惊文案，去掉括号。 */
            '，偏好也回来了' +
            /* R3363-P1-2：在途被改键保住本机的条数点名——
             * 静默留本地值用户不知道哪些没跟云端走。 */
            (_kept.length
              ? '；' + _kept.length + ' 条本机较新的没盖' : '') +
            /* R3339（审-中）：线程批丢/超重如实报——「导到一半断了」
             * 不点名的静默丢尾违背披露纪律。 */
            (_thrSkipped ? '；' + _thrSkipped + ' 个研究线程太大没导进去' : '') +
            (_nOrph ? ' + ' + _nOrph + ' 条散落笔记' : '') +
            (_fvBad ? '；' + _fvBad + ' 条收藏类型不认识没导进去' : '') +
            /* R3372-低-3：校验丢弃也点名——合法数据被规则误杀
             * 不该静默。 */
            (_dropN ? '；' + _dropN + ' 条没认出来跳过了' : '') +
            /* R3372-低-6：聊天会话锚不跟机走——小满记得文字
             * 不记得语境，明说免误解。 */
            '；聊天上下文不跟机走，接着聊就行';
          showToast(_msg, 'info');
          /* R2349y（R95-P3-9）：批量导入后广播 dirty——其他 tab 的
           * 历史视图就地刷新（原只有单删时发）。
           * R3363-低-17：channel 用完即关，反复拉回不再漏建。 */
          try {
            if (window.BroadcastChannel) {
              var _bc2 = new BroadcastChannel('paipan_history');
              _bc2.postMessage('dirty');
              _bc2.close();
            }
          } catch (eBC2) {}
          loadPaipanHistory();
        } catch (e) {
          /* R3320-P1-1②：能走到这只剩传输失败——本地偏好与已传
           * 分批都落了，文案说真话不甩「读不懂」。 */
          showToast('偏好已恢复，记录导到一半断了：联网后再点一次导入',
            'error');
        }
  }
  /* R2500（R143-P2-8）：粘贴导入弹层——与导出文本弹层对称
   * （textarea 可编辑 + 导入按钮）。 */
  function _showTextImportModal(onImport) {
    var _ex2 = document.getElementById('posterModal');
    if (_ex2) { closePosterModal(); if (_ex2.isConnected) _ex2.remove(); }
    var bd = document.createElement('div');
    bd.id = 'posterModal';
    bd.className = 'poster-modal-backdrop';
    _posterTrigger = document.activeElement;
    bd.innerHTML =
      '<div class="poster-modal" role="dialog" aria-modal="true" aria-label="导入备份">' +
        '<div class="poster-modal-head">' +
          '<span class="poster-modal-title">📦 导入备份</span>' +
          '<button type="button" class="poster-modal-close" aria-label="关闭">×</button>' +
        '</div>' +
        '<div class="poster-modal-body">' +
          '<textarea class="export-modal-ta" aria-label="粘贴备份内容" ' +
            'placeholder="把之前在备忘录/文件传输助手里存的备份文本整段贴进来"></textarea>' +
        '</div>' +
        '<div class="poster-modal-tip">💡 贴的是「我的数据备份」那段备份文本：含生辰昵称，别贴进公开群</div>' +
        '<div class="poster-modal-actions">' +
          '<button type="button" class="poster-act" id="importPasteGo">✨ 导入这份备份</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(bd);
    try {
      history.pushState({
        view: (history.state && history.state.view) || 'home',
        modal: 'poster' }, '');
      window.__modalPushed = true;
    } catch (ePS) {}
    requestAnimationFrame(function () { bd.classList.add('open'); });
    _mainInert(true, bd);
    var _pcc = bd.querySelector('.poster-modal-close');
    _pcc.addEventListener('click', closePosterModal);
    bd.addEventListener('click', function (e) {
      if (e.target === bd) closePosterModal();
    });
    _posterOnKey = function (e) {
      if (e.key === 'Escape' || e.keyCode === 27) closePosterModal();
    };
    document.addEventListener('keydown', _posterOnKey);
    bd.querySelector('#importPasteGo').addEventListener('click', async function () {
      var _v = (bd.querySelector('textarea').value || '').trim();
      if (!_v) { showToast('先把备份文本贴进来再点', 'warn'); return; }
      try { JSON.parse(_v); }
      catch (eJ) { showToast('这段不是完整的备份文本，从头「{」到尾「}」整段贴', 'warn'); return; }
      closePosterModal();
      await onImport(_v);
    });
    _pcc.focus();
  }
  /* R231d（R37-F3）：?view=history 深链/F5 补加载——IIFE 内函数经
   * window 暴露给 showView 的视图钩子。 */
  window.__loadPaipanHistory = loadPaipanHistory;
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', phBind);
  else phBind();
})();

/* ── v2：星座页「我的本命盘」——生日→太阳星座+四柱+五行+日主解读（因人而异）── */
(function () {
  'use strict';
  var SIGN_DATE = [
    [1, 20, '水瓶'], [2, 19, '双鱼'], [3, 21, '白羊'], [4, 20, '金牛'],
    [5, 21, '双子'], [6, 22, '巨蟹'], [7, 23, '狮子'], [8, 23, '处女'],
    [9, 23, '天秤'], [10, 24, '天蝎'], [11, 22, '射手'], [12, 22, '摩羯']];
  function sunSign(m, d) {
    for (var i = SIGN_DATE.length - 1; i >= 0; i--) {
      if ((m === SIGN_DATE[i][0] && d >= SIGN_DATE[i][1]) || m > SIGN_DATE[i][0]) {
        if ((m > SIGN_DATE[i][0]) || (m === SIGN_DATE[i][0] && d >= SIGN_DATE[i][1])) return SIGN_DATE[i][2];
      }
    }
    return '摩羯';
  }
  /* R3174：宫格高亮「我的星座」要用——IIFE 内函数外露，避免十二宫
   * 渲染处再抄一份日期表。 */
  window.__sunSign = sunSign;
  var SIGN_TXT = {
    '白羊': '行动派小白羊，想到就冲，热情藏不住，偶尔上头但永远鲜活。',
    '金牛': '金牛的你嘴上佛系心里有数，认定的人和喜欢的东西特别长情。',
    '双子': '双子小机灵鬼，脑瓜转得飞快，聊天永远不冷场，情绪来得快去得也快。',
    '巨蟹': '巨蟹的你软乎乎重感情，照顾朋友一把好手，只是偶尔想太多。',
    '狮子': '狮子座自带小太阳体质，大方讲义气，被夸一句能开心三天。',
    '处女': '处女的你看着高冷其实心超细，默默把一切都安排妥帖。',
    '天秤': '天秤小天使自带社交光环，追求平衡美好，选择困难但审美一流。',
    '天蝎': '天蝎的你外冷内热，爱恨分明，认定的事九头牛都拉不回来。',
    '射手': '射手座自由的小风，乐观爱玩，天生会把气氛带起来。',
    '摩羯': '摩羯的你人间清醒，默默努力型选手，稳稳的安全感担当。',
    '水瓶': '水瓶座小外星人，脑洞清奇想法多，有趣灵魂本魂。',
    '双鱼': '双鱼的你温柔爱做梦，共情力满格，是朋友们的树洞担当。'
  };
  async function doBirthReading() {
    var out = document.getElementById('birthResult');
    if (!out) return;
    var y = Number((document.getElementById('b_year') || {}).value);
    var m = Number((document.getElementById('b_month') || {}).value);
    var d = Number((document.getElementById('b_day') || {}).value);
    var hv = (document.getElementById('b_hour') || {}).value;
    var g = (document.getElementById('b_gender') || {}).value || '女';
    if (!y || !m || !d || m < 1 || m > 12 || d < 1 || d > 31 || y < 1900 || y > 2100) {
      _failField(!y || y < 1900 || y > 2100 ? 'b_year'
        : (m < 1 || m > 12 ? 'b_month' : 'b_day'),
        'birthResult', '日期看起来不太对，检查一下年月日再试～');
      return;
    }
    var _bLunar = val('b_cal') === 'lunar';
    var _brb = _bLunar ? null : _badYmdField('b_year', 'b_month', 'b_day');
    if (_brb) {
      _failField(_brb, 'birthResult',
        '这一天不存在。' + m + ' 月没有 ' + d + ' 号');
      return;
    }
    if (_bLunar && (d < 1 || d > 30)) {
      _failField('b_day', 'birthResult', '农历的日填 1–30'); return;
    }
    busy('birthResult', '正在排你的本命盘…');
    try {
      /* R233x（R56-P1）：本命盘流日此前锚服务器日——跨零点/时区
       * 边缘与日签/黄历错位；与 dailyDetail 同款 client 日。 */
      var body = { year: y, month: m, day: d, hour: (hv === '' ? 12 : Number(hv)), gender: g,
        /* R3232：时辰留空此前静默按午时排（主表单的 hour_known
         * 闸这个抽屉漏接）——补上，后端「没填时辰」明示才生效。 */
        hour_known: (hv !== ''),
        ask_date: todayIso() };
      _lunarPack(_bLunar, _LUNAR_KEYS_STD, y, m, d,
                 checked('b_leap'), body);
      /* R2500（R142-P1-3）：示例生日原样提交不落档——同日但 nick 想
       * 单存的走星座页显式存。
       * R3206：农历入档跳过（me 档案是公历坐标系）。 */
      /* R3239：农历抽屉提交曾整体跳过落档——统一走 _meSaveFromBirth
       * （换算成公历坐标+农历原值标注）。改完生日再 loadDaily 一次：
       * 此前判词锚旧档案，档案条说「测算时自动代入」但眼前的卡没换
       * （次日才生效）。 */
      var _meDirty = !_fieldsUntouched(
        ['b_year','b_month','b_day','b_hour','b_gender']);
      if (_meDirty) {
        await _meSaveFromBirth('me', {
          lunar: _bLunar, y: y, m: m, d: d,
          h: (hv === '' ? null : Number(hv)), g: g,
          n: (document.getElementById('b_nick') || {}).value || '',
          leap: checked('b_leap') });
        try { await loadDaily(); } catch (eD) {}
      }
      _meFillAll();   /* R230y */
      /* R228k：raw fetch → postJSON——白拿 20s 超时、非2xx toast 与
       * 422 中文人话化（原来手写的 r.ok 分支与 api() 重复且漏超时）。 */
      var j = await postJSON('/api/bazi', body);
      /* R3308（审-中3）：星座判座改后端节气精判（paipan.sun_sign
       * 键）——本地固定日期表在交界日（3/20、1/20 这类 ±1 天漂移年）
       * 会错座。后端缺键/判不出时退回本地表兜底。 */
      var sign = ((j.paipan || {}).sun_sign) || sunSign(m, d);
      var fe = ((j.calc || {}).five_elements || {}).counts || {};
      var wxLine = Object.keys(fe).map(function (k) { return k + ' ' + fe[k]; }).join(' · ');
      var missing = ((j.calc || {}).five_elements || {}).missing || [];
      /* R3218：五行分布补人话落点——最旺/最弱各一词，镜像 voice.WX_TAG
       * （selftest wx.tag.parity 钉防双侧漂移）。 */
      var _WX_TAG = {'木':'向上长、有主心骨','火':'热、快、要回应',
        '土':'稳、认死理、能托底','金':'利落、有边界感','水':'活、会转弯、能沉住'};
      var _feVals = Object.keys(fe).filter(function(k){return fe[k] != null;});
      var wxNote = '';
      if (_feVals.length >= 3) {
        var _hi = _feVals.reduce(function(a,b){return fe[a]>=fe[b]?a:b;});
        var _lo = _feVals.reduce(function(a,b){return fe[a]<=fe[b]?a:b;});
        if (_hi !== _lo)
          wxNote = '　<span class="wx-note">' + esc(_hi) + '最旺（' +
            esc(_WX_TAG[_hi] || '') + '），' + esc(_lo) +
            '偏弱一点</span>';
      }
      var pp = ((j.paipan || {}).render || '').split('　')[0] || '';
      var warm1 = (((j.warm || {}).reply || [])[0]) || '';
      var html = '<div class="birth-card">';
      html += '<div class="birth-head"><img class="birth-img" src="/static/cream/zodiac-' +
        ({'白羊':'aries','金牛':'taurus','双子':'gemini','巨蟹':'cancer','狮子':'leo','处女':'virgo','天秤':'libra','天蝎':'scorpio','射手':'sagittarius','摩羯':'capricorn','水瓶':'aquarius','双鱼':'pisces'}[sign] || 'aries') +
        '.jpg" alt="" onerror="this.classList.add(\'is-missing\')">' +
        '<div><div class="birth-sign">你是' + esc(sign) + '座</div>' +
        '<div class="birth-sub">' + esc(SIGN_TXT[sign] || '') + '</div></div></div>';
      html += '<div class="birth-block"><span class="birth-label">你的四柱</span><span class="birth-val">' + esc(_pillarsHonest(pp, j.hour_known)) + '</span></div>';
      html += '<div class="birth-block"><span class="birth-label">五行分布</span><span class="birth-val">' + esc(wxLine || '—') + (missing.length ? '　<strong>缺 ' + esc(missing.join('')) + '</strong>' : '　五行不缺') + wxNote + '</span></div>';
      /* R3232（用户实测）：填了生辰几时，解读里此前一个字不提——
       * 后端 warm.reply 的时柱行（R3232 新增）在这格里上卡，
       * 「填了跟没填一样」的观感消掉。 */
      if (hv !== '') {
        var _hourLine = (((j.warm || {}).reply || []).filter(function (l) {
          return l.indexOf('时柱「') === 0; }))[0];
        if (_hourLine) {
          html += '<div class="birth-block"><span class="birth-label">出生时辰</span>' +
            '<span class="birth-val">' + esc(_hourLine) + '</span></div>';
        }
      }
      if (warm1) html += '<div class="birth-block"><span class="birth-label">小满悄悄说</span><span class="birth-val">' + esc(warm1) + '</span></div>';
      /* R3164：本命盘卡补 AI 解读块——走 /api/bazi 响应带 ai_task_id，
       * 此前没挂 render/poll，受众高频钩子卡少了口语段。 */
      html += renderAiPolish(j);
      html += '<button class="ghost fav-btn" type="button" id="shareBirth" ' +
        'title="生成分享图">📸 分享图</button>';
      html += '<div class="birth-note">以上由排盘引擎按你输入的生日实时计算，同生日同时辰的人解读也会不同。仅供娱乐，不构成决策依据 ✨</div></div>';
      /* R2350d（R100-P0-1）：busy() 挂的 is-working 此前永不摘除
       * （唯一绕过 paint() 的 busy 流）——整卡恒半透且子元素
       * pointer-events:none，分享钮/聊聊都是假的。 */
      out.classList.remove('is-working');
      out.innerHTML = html;
      attachChatEntry(out);   /* R230k（R23-P2-1）：本命盘卡挂聊天入口 */
      pollAiPolish('birthResult', j.ai_task_id);   /* R3164 */
      /* R231d（R37-F14）：本命盘挂分享钮——「你是X座」天生海报素材 */
      var _sbb = out.querySelector('#shareBirth');
      if (_sbb) _sbb.addEventListener('click', function () {
        /* R233t（R51-P1-5）：星座名随 j 透传进海报 */
        var _bj = Object.assign({}, j, { _birth_sign: sign });
        var _p = downloadPoster(_bj, 'birth');
        if (_p && _p.catch) _p.catch(function () {});
      });
      try { rememberResult('bazi', j, '我的本命盘', body); } catch (e) {}
    } catch (err) {
      /* R2349j（R71-P1-18）：非 API 异常（TypeError 等）裸英文先过人话化。 */
      out.classList.remove('is-working');   /* R2350d：同 P0-1，失败路径也摘 */
      out.innerHTML = '<div class="ph-empty">网络开小差了：' + esc(_humanizeErr(err.message)) + '，稍后再试～</div>';
    }
  }
  var _birthBusy = 0;   /* R8 P2-2：裸 click 不经 on()，自加在途锁。
   * R3259（用户实测「点多次后卡住了」）：锁内串了 meSave→loadDaily→
   * postJSON 三个 await——任何一环的 promise 楔死（弱网/旧壳/服务端
   * 挂起）都会让布尔锁永真、按钮点击被静默吞掉=全站观感「卡死」。
   * 改时间戳租约：>26s 的在途视为僵死，新点击强夺重跑；忙态再点
   * 给 toast 反馈而不是静默吞。 */
  async function _birthGuard(ev) {
    if (_birthBusy && Date.now() - _birthBusy < 26000) {
      try { showToast('还在排盘中，稍等一下下～', 'info'); } catch (eT) {}
      return;
    }
    var _lease = Date.now();
    _birthBusy = _lease;
    /* 只清自己这轮的租约——楔死的旧请求若晚到复位，不得把
     * 新一轮在途的时间戳抹掉（否则并发双击白防）。 */
    try { await doBirthReading(ev); } finally {
      if (_birthBusy === _lease) _birthBusy = 0;
    }
  }
  function bind() {
    var btn = document.getElementById('birthSubmit');
    if (btn) btn.addEventListener('click', _birthGuard);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
  else bind();
})();

/* ── v3（P5）：白名单 markdown 渲染，见 renderRichText 内注释 ── */
function renderRichText(raw) {
  var s = esc(String(raw == null ? '' : raw));
  s = s.replace(/\*\*([^\n*]+)\*\*/g, '<strong>$1</strong>');
  /* R227b：没配对的 **（跨行/嵌套/半对）一律吃掉，不许把符号露给用户 */
  s = s.replace(/\*{2,}/g, '');
  s = s.replace(/(^|[^*])\*([^\n*]+)\*/g, '$1<em>$2</em>');
  s = s.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  var lines = s.split(/\n/);
  var out = [], inList = false;
  for (var i = 0; i < lines.length; i++) {
    var ln = lines[i];
    if (/^\s*[-•]\s+/.test(ln)) {
      if (!inList) { out.push('<ul class="rt-list">'); inList = true; }
      out.push('<li>' + ln.replace(/^\s*[-•]\s+/, '') + '</li>');
    } else {
      if (inList) { out.push('</ul>'); inList = false; }
      if (ln.trim() === '') { out.push('<br>'); }
      else { out.push(ln); }
    }
  }
  if (inList) out.push('</ul>');
  return out.join('\n');
}
/* ── v3（P4）：内部引文清洗——「書名 @ADDR (file.txt) · 层」→「書名 · 层」── */
/* R2349v（R92-P1-3）：古籍域行话收口。
 * _rmMarks：语料里的章节标记 `**` 是源码记号，直接贴上屏就是裸奔
 * （聊天域 R227b 修过同款，这边补上）。
 * _SCHEME_CN：编址方式英文 id → 中文名（ascheme 下拉同款口径）。 */
function _rmMarks(t) {
  return String(t == null ? '' : t).replace(/\*\*/g, '');
}

var _SCHEME_CN = { zhouyi: '周易', bcv: '圣经章节', yilin: '易林',
  booksec: '书章节', play: '剧本', euclid: '欧几里得' };

function humanCite(citation) {
  var s = String(citation == null ? '' : citation);
  s = s.replace(/\s*@(\?|[^\s·]{0,})/g, '');             /* 去 @ADDR / @?（v4：@ 后非空白非·的尾巴一并清） */
  s = s.replace(/\s*\([^)]*\.txt\)/gi, '');               /* 去 (file.txt) */
  /* R2349v（R92-P1-3）：[tls]/[wyg] 这类内部版本标签直出没人看得懂，
   * 折成中文版本名。
   * R3221：全称翻译成藏书口径（SBCK=四部丛刊、tls=通行本…），
   * 未识别的直接归「通行本」，不再露字母代号。 */
  var _ED_CN = { sbck: '四部丛刊', tls: '通行', chant: '汉达古籍',
    wyg: '文渊阁四库', kanripo: 'Kanripo 古籍', gutenberg: '古腾堡文库',
    ctext: '中哲文库', w: '四库', j: '通行', douay: '杜埃' };
  s = s.replace(/\s*\[([A-Za-z0-9]+)\]/g, function (m, t) {
    return ' · ' + (_ED_CN[t.toLowerCase()] || '通行') + '本';
  });
  /* R2350b（R98-P2-14）：引注尾巴残留的分段标记「 ! 」清掉
   * （实测「卦45（萃） ! · 經」直贴屏）。 */
  s = s.replace(/\s*!\s*/g, ' ');
  s = s.replace(/\s{2,}/g, ' ');
  return s.trim();
}

/* ── R229u：离线感知——SW 兜住壳后用户仍可能不知道断网，操作只会收到
 * 泛泛的「网络不太好」。offline/online 事件给一条明确状态提示。 */
(function () {
  window.addEventListener('offline', function () {
    showToast(_dayPick(['当前离线：数据暂时刷不出来，恢复网络后再试','现在离线啦：连上网再戳我','离线中，数据先歇一会儿'], 'off'), 'warn');
  });
  window.addEventListener('online', function () {
    showToast('网络回来了～', 'info');
    /* R2506（审-U1）：日签卡死卡兜底——上次 loadDaily 失败后
     * __lastDaily 仍空，回网自动重拉一次（DAILY_GEN 挡旧响应）。 */
    if (!window.__lastDaily) { try { loadDaily(); } catch (e) {} }
  });
  /* R230d（R16-P1-5）：冷启动就离线（PWA 壳由 SW 兜住）时给同一条提示——
   * offline 事件只在「由在线转离线」时发，启动即离线它不发。 */
  if (navigator.onLine === false) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        showToast(_dayPick(['当前离线：数据暂时刷不出来，恢复网络后再试','现在离线啦：连上网再戳我','离线中，数据先歇一会儿'], 'off'), 'warn');
      });
    } else {
      showToast(_dayPick(['当前离线：数据暂时刷不出来，恢复网络后再试','现在离线啦：连上网再戳我','离线中，数据先歇一会儿'], 'off'), 'warn');
    }
  }
})();

/* ── R233j（R46-P1）：日盐问候层——品牌 tagline / 每日卡封面句 /
 * 固定高频句每天换一句，复访不再「app 好懒」。DOM ready 后覆写。 ── */
(function () {
  function _apply() {
    try {
      var tl = document.querySelector('.brand-tagline');
      /* R2349g（R68-P1-1）：首屏 tagline 4→9——每日必见位，原池
       * 一周必撞。 */
      if (tl) tl.textContent = _dayPick([
        '今天也要好好生活呀 ✨',
        '今天的小满也很想你',
        '慢慢来，今天刚刚好',
        '拆开今天，里面有好东西',
        '今日份好运已到账',
        '把今天过成想要的样子',
        '今天的宇宙站在你这边',
        '好运正在路上，请查收',
        '温柔一点，今天也是'], 'tagline');
      /* 回访者的封面句已被「小满第 N 次」接管——只在首访日轮换。 */
      var _v = String(localStorage.getItem('visits') || '')
        .split(',').filter(Boolean).length;
      var cv = document.querySelector('.daily-cover-txt');
      /* R2349g（R68-P1-1）：拆礼封面句 4→8。 */
      if (cv && _v <= 1) cv.textContent = _dayPick([
        '🎀 点开看看，今天你的玄学搭子运',
        '🎀 今天的小包裹，拆开看看',
        '🎀 今日运势已打包，等你来拆',
        '🎀 敲一敲，今天给你留了惊喜',
        '🎀 今天的运气，拆开了才算数',
        '🎀 给你留了个小惊喜，点开看',
        '🎀 今天的礼物藏在里面',
        '🎀 拆一个不试试手气？'], 'cover');
    } catch (e) {}
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _apply);
  } else { _apply(); }
})();

/* ════ R3394 答案之书（调研爆款复刻：默念→翻页→一句答案+提示+小动作）════
 * 54 条小满声口答案，顺势/再想想/缓一缓三种风向；问句只进本机历史
 * 与聊上下文，不进服务器。ansb:hist 进备份/wipe/GC 三链。 */
var _ANSB = [
  ['去吧，心在点头的方向','犹豫的背面常常是想要','今天就把第一步迈出去'],
  ['这事比你以为的顺手','准备其实已经够了','选最近的那个开口先聊'],
  ['签都替你点过两次头了','直觉这次是对的','三天内给自己一个答复'],
  ['推开这扇门，风是顺的','阻力多半来自想象','把最难的一句先说出口'],
  ['去吧，答案藏在行动里','想清楚了七成就能走','今晚写下第一步'],
  ['时候到了，伸手就行','机会不喜欢等人','给自己定一个开动的点'],
  ['这条路灯是亮的','你的担心比路本身大','约那个能帮你的人'],
  ['这次可以赌一把小的','输得起的局都值得试','先投一点点试试水'],
  ['就它了，别再货比三家','选择太多才是陷阱','删掉备选清单'],
  ['答案是「可以」','你其实早就知道了','直接答应下来'],
  ['大胆点，运气在线','今天的气势够用','做那件你一直想做的小事'],
  ['往前走，别回头','回头只会让你重想一遍','把退路先放一放'],
  ['值得，去见一面吧','缘分要当面才算数','发出那句约见的话'],
  ['开口吧，对方在等','沉默不会替你表达','发出去那条草稿'],
  ['这个决定是温的','心里踏实就是信号','告诉一个人你的决定'],
  ['去吧，别辜负这股劲','想做的事都该被善待','今晚就动手第一页'],
  ['稳了，这件事是你的','能力刚好配得上野心','把计划落成日期'],
  ['试一试，天不会塌','最坏的结果你也接得住','设一个止损线再出发'],
  ['再想想，答案在路上','现在急的是情绪不是事','睡一觉明天再看'],
  ['差一点点火候','还有一个变量没落地','把不确定的列出来'],
  ['问问那个走过的人','别人的坑就是你的灯','发消息请教一位前辈'],
  ['可以，但换个方式','目标对，路径绕了','把方案 B 写三行'],
  ['先把手头的收个尾','旧账不清新账难开','今天清一件拖着的事'],
  ['等一个信号再动','这事急不得也慢不得','定一个「再等等」的期限'],
  ['一半一半，看你添哪边','结果取决于你下注的力气','写下支持/反对各三条'],
  ['先照顾好自己再说','状态不对答案就不准','今晚早点睡'],
  ['问反了，先问想要什么','方向比速度重要','写下你最想要的一个字'],
  ['条件还差一块拼图','缺的不是运气是信息','去把缺的那个数补上'],
  ['可以，但别全押','留一手不是不信任','把鸡蛋分两个篮子放'],
  ['现在开口，话会变味','情绪没过就别谈事','先散个步回来再决定'],
  ['这题有第三种解法','别困在要么要么里','写下第三条路长什么样'],
  ['先问自己愿不愿','别人的期待不是你的','把「应该」划掉重写'],
  ['值得，但值得慢点来','快的东西容易回弹','把日程往后挪一周'],
  ['先试试小的那步','大决定可以拆小走','做那步最不疼的'],
  ['有人比你更在意这事','听听对方的版本','约出来聊十五分钟'],
  ['方向对，步子急了','慢就是快的另一种写法','把计划砍一半再执行'],
  ['这次算了，有更好的在排队','错过这班还有下一班','把它从清单划掉'],
  ['缓缓，心里没点头的别去','勉强的事做不出好结果','今天先不答应'],
  ['先别动，风还没转向','现在出手事倍功半','下周再问一遍'],
  ['这个坑你看见了就别跳','直觉的劝退要认真听','礼貌地说一次不'],
  ['不值得为它熬夜','消耗大于收获的事早放手','今晚不带这事上床'],
  ['这段先放下，手会轻一点','攥太紧的东西留不住','删一条执念'],
  ['回头路还开着，别硬撑','退出不等于失败','给自己留一个台阶'],
  ['等等，对方还没准备好','节奏不对再真也难受','这周不主动联系'],
  ['这个「要不要」本身就是答案','真正想要的不会纠结','放进三个月后的清单'],
  ['先存钱，这事花钱不值','冲动消费缓三天','加进购物车别结算'],
  ['别急，水还没烧开','提前揭盖汤会泄气','设个提醒再看'],
  ['今天不适合硬碰硬','赢了的争吵也是输','换个日子再谈'],
  ['先照顾好身体这关','累的时候决定都会偏','今天十点前睡'],
  ['缓缓，答案会自己浮上来','强行想是想不清的','去洗个热水澡'],
  ['这一步先不迈','看不清的地方不落脚','原地站稳就好'],
  ['今天适合收，不适合放','能量低的时段守成','把决定推到明天'],
  ['不用证明给任何人看','你的节奏不需要观众批准','关掉比较频道'],
  ['这次轮不到你扛','把别人的责任还回去','说一句「这不归我」']
];
var _ansbPending = 0;
function _ansbHist() {
  try {
    var h = JSON.parse(localStorage.getItem('ansb:hist') || '[]');
    return Array.isArray(h) ? h.slice(0, 20) : [];
  } catch (e) { return []; }
}
function _ansbBookHtml() {
  return '<div class="ansb-book">' +
    '<div class="ansb-book-emoji" aria-hidden="true">📖</div>' +
    '<div class="ansb-book-t">心里默念一个问题——</div>' +
    '<div class="ansb-book-s">工作/感情/那件拿不定的事，都行</div>' +
    '<input class="ansb-q" id="ansbQ" type="text" maxlength="40" ' +
      /* R3396-P2-5：原句「只存在你手机里」是假承诺——写下的问题会
       * 进和小满的聊天上下文（她聊起来接得住），文案按实说。 */
      'placeholder="也可以写下来，聊起来小满接得住" ' +
      'aria-label="你心里默念的问题">' +
    '<button class="mc-go ansb-flip" type="button" data-ansb="flip">' +
      '🙏 默念三秒，翻一页</button>' +
    '<div class="ansb-note">答案不负责对错，只负责帮你听见自己</div>' +
  '</div>' + _ansbHistHtml();
}
function _ansbHistHtml() {
  var h = _ansbHist(); if (!h.length) return '';
  return '<div class="ansb-hist"><div class="ansb-htitle">最近翻过的页</div>' +
    h.map(function (x) {
      return '<div class="ansb-hrow">' +
        '<span class="ansb-hd">' + esc(x.d || '') + '</span>' +
        (x.q ? '<span class="ansb-hq">「' + esc(x.q) + '」</span>' : '') +
        '<span class="ansb-ha">' + esc(x.a || '') + '</span></div>';
    }).join('') + '</div>';
}
function _ansbCardHtml(i, q) {
  var r = _ANSB[i]; if (!r) return '';
  return '<div class="ansb-card"' +
    (q ? ' data-q="' + esc(q) + '"' : '') + '>' +
    '<div class="ansb-bookmark" aria-hidden="true">— 翻到的这一页 —</div>' +
    '<div class="ansb-answer">' + esc(r[0]) + '</div>' +
    '<div class="ansb-rows">' +
      '<div class="ansb-row"><span class="ansb-rk">书里还说</span>' +
        '<span>' + esc(r[1]) + '</span></div>' +
      '<div class="ansb-row"><span class="ansb-rk">可以试</span>' +
        '<span>' + esc(r[2]) + '</span></div>' +
    '</div>' +
    '<div class="ansb-acts">' +
      '<button class="ghost" type="button" data-ansb="again">📖 换个问法再翻</button>' +
      '<button class="ghost" type="button" data-ansb="share" data-i="' + i + '">' +
        '📸 晒这一页</button>' +
    '</div></div>' + _ansbHistHtml();
}
function _ansbFlip(q) {
  var i = Math.floor(Math.random() * _ANSB.length);
  try {
    var h = _ansbHist();
    h.unshift({ d: todayIso().slice(5), q: (q || '').slice(0, 12),
                a: _ANSB[i][0] });
    localStorage.setItem('ansb:hist', JSON.stringify(h.slice(0, 20)));
    /* 聊上下文事实：当天翻过书页 → 小满知道翻到哪句。 */
    localStorage.setItem('ansb:fact', JSON.stringify({
      d: todayIso(),
      t: '她今天翻了答案之书' + (q ? '（问：「' + q.slice(0, 20) + '」）' : '') +
         '，翻到的一句是「' + _ANSB[i][0] + '」；她想聊可以顺着这句说'
    }));
  } catch (e) {}
  return i;
}
function _renderAnsb() {
  var bx = document.getElementById('ansbBox');
  if (!bx) return;
  bx.innerHTML = _ansbBookHtml();
}
(function _ansbBind() {
  document.addEventListener('click', function (e) {
    var b = e.target && e.target.closest
      ? e.target.closest('[data-ansb]') : null;
    if (!b) return;
    var act = b.dataset.ansb;
    if (act === 'flip') {
      if (_ansbPending) return;
      _ansbPending = 1;
      var qEl = document.getElementById('ansbQ');
      var q = qEl ? qEl.value.trim() : '';
      var bx = document.getElementById('ansbBox');
      /* 翻书仪式：~1.6s 翻页动画——「书在替你找」的体感是功能本体。 */
      var bk = bx && bx.querySelector('.ansb-book');
      if (bk) bk.classList.add('is-flipping');
      b.disabled = true;
      setTimeout(function () {
        var i = _ansbFlip(q);
        if (bx) bx.innerHTML = _ansbCardHtml(i, q);
        _ansbPending = 0;
      }, 1600);
    } else if (act === 'again') {
      _renderAnsb();
    } else if (act === 'share') {
      var i = parseInt(b.dataset.i || '0', 10);
      var r = _ANSB[i]; if (!r) return;
      var _cd = b.closest('.ansb-card');
      var qq = _cd ? (_cd.dataset.q || '') : '';
      downloadPoster({ _ansb: { a: r[0], h: r[1], d: r[2], q: qq },
        date: todayIso() }, 'ansb');
    }
  });
})();
