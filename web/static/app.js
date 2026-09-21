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
function num(id) {
  const raw = val(id);
  if (raw === '') return null;
  const n = parseInt(raw, 10);
  return Number.isNaN(n) ? null : n;
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
  return md + '日 · ' + _weekdayCn(d);
}
function _signNo(dateStr) {
  var src = 'sign|' + String(dateStr || todayIso()), h = 0;
  for (var i = 0; i < src.length; i++) h = (h * 31 + src.charCodeAt(i)) >>> 0;
  return h % 64 + 1;
}

/* R2349l（R73-P1-1）：签号 1–64 ↔ 周易 64 卦——每日一签从此有真签文。
 * 每项「卦名 · 一句白话签意」（白话是我们写的安抚口径，不冒充卦辞）。 */
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
  bsChapter: '章节', bsSummary: '知识卡', nameReviewOut: '名字点评' };
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
  if (node && node.innerHTML.trim() &&
      !node.querySelector('.no-evidence:only-child') &&
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
    showToast(_humanizeErr(text), 'warn');
    _srSay('有点小状况——看看页面提示');
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
    showToast(_humanizeErr(text), 'warn');
    _srSay('有点小状况——看看页面提示');
    return;
  }
  _paintSilent = true;
  paint(id, '<div class="no-evidence">' + esc(_humanizeErr(text)) + '</div>');
  _paintSilent = false;
  _srSay('有点小状况——看看页面提示');
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
  max_addresses: '地址数', per_work: '每书条数', addr_name: '节名',
  ref_id: '对象', title: '标题', text: '内容', work: '书号' };
function _humanize422(detail) {
  try {
    var first = detail[0] || {};
    var loc = first.loc || [];
    var field = String(loc[loc.length - 1] || '');
    var cn = _FIELD_CN[field];
    var msg = String(first.msg || '');
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
  let html = '<div class="card"><h2>💕 八字合婚' +
    (_hn ? ' <small style="font-size:15px;color:var(--primary-ink);">' +
    esc(_hn) + '</small>' : '') + '</h2>';
  // R193b：分享海报入口（对齐排盘 shareBazi，T3.1 同款零依赖 Canvas）
  /* R233n：三枚 fav-btn 全按 right:24/84px 绝对定位会互叠——本卡
   * 三钮改用 .hh-btns flex 行（静态流，gap 间隔）。 */
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
    html += '<div class="hh-score">合拍指数 <strong>' +
      esc(String(j.match_score)) + '</strong><span class="hh-score-sub">/99</span></div>';
  }
  // R187b：人话视图置顶（specs/005 US4）
  if (j.warm) {
    html += '<div class="warm-wrap"><div class="warm-l0">' +
      esc(j.warm.one_liner || '') + '</div><div class="warm-reply">';
    (j.warm.reply || []).forEach(function (ln) {
      html += '<p>' + esc(ln) + '</p>';
    });
    html += '</div>';
    if (j.warm.badge) html += '<div class="warm-badge">' + esc(j.warm.badge) + '</div>';
    html += '</div>';
  }
  html += '<div class="calc-grid">';
  html += '<div class="calc-block" style="border-left:3px solid var(--c-bazi);">' +
    '<h3 style="color:var(--c-bazi);">' + esc(j.a_name || '甲') + '</h3>' +
    '<p style="font-family:var(--font-serif);font-size:18px;">' +
    esc(a.year || '') + ' · ' + esc(a.day || '') + '</p>' +
    '<p style="font-size:13px;color:var(--secondary);">日主：' +
    esc(a.day_master || '') + '（' + esc(j.day_wx_a || '') + '）</p></div>';
  html += '<div class="calc-block" style="border-left:3px solid var(--c-hehun);">' +
    '<h3 style="color:var(--c-hehun);">' + esc(j.b_name || '乙') + '</h3>' +
    '<p style="font-family:var(--font-serif);font-size:18px;">' +
    esc(b.year || '') + ' · ' + esc(b.day || '') + '</p>' +
    '<p style="font-size:13px;color:var(--secondary);">日主：' +
    esc(b.day_master || '') + '（' + esc(j.day_wx_b || '') + '）</p></div>';
  html += '</div><div class="pill-row">';
  const relLabel = j.clash ? '六冲' : j.combine ? '六合' : '无冲合';
  const relColor = j.clash ? 'var(--c-bazi)' : j.combine ? 'var(--c-good)' : 'var(--secondary)';
  html += '<span class="pill sm" style="background:' + relColor + ';">年支（' +
    esc(j.year_zhi_a || '') + '×' + esc(j.year_zhi_b || '') + '）：' +
    esc(relLabel) + '</span>';
  /* R230a-7（R13-P0-2）：同五行显示「比和」而非「非相生」 */
  html += '<span class="pill sm" style="background:' +
    ((j.day_wx_sheng || j.day_wx_same) ? 'var(--c-good)' : 'var(--c-bazi)') + ';"' +
    ' title="两人的日主五行关系">五行底子：' +
    esc(j.day_wx_sheng ? '相生' : (j.day_wx_same ? '比和' : '非相生')) + '</span>';
  html += '<span class="pill sm" style="background:var(--c-taohua);">桃花（' +
    esc(j.peach_a || '') + '/' + esc(j.peach_b || '') + '）：' +
    esc(j.peach_same ? '重叠' : '不同') + '</span>';
  // R204b（D-257b）：天干五合 + 十神互见 pill（yinyuan skill 融入）
  if (j.gan_he) {
    html += '<span class="pill sm" style="background:var(--c-good);">日干五合：天生对味</span>';
  }
  if (j.god_a_sees_b && j.god_b_sees_a) {
    /* R233g（R44-P1）：pill 里裸神煞名 → 随行白话（你眼里的TA/TA眼里的你）。 */
    var _GP = {比肩:'同类',劫财:'对手',食神:'玩伴',伤官:'点子王',偏财:'惊喜',
               正财:'稳定',七杀:'压力',正官:'靠山',偏印:'直觉',正印:'底气'};
    html += '<span class="pill sm" style="background:var(--secondary);" ' +
      'title="十神互见：互相在对方盘里的角色">互看：你眼里TA是「' +
      esc(_GP[j.god_a_sees_b] || j.god_a_sees_b) + '」· TA眼里你是「' +
      esc(_GP[j.god_b_sees_a] || j.god_b_sees_a) + '」</span>';
  }
  html += '</div>';
  if (j.render) html += '<div class="calc-summary">' + esc(j.render) + '</div>';
  if (j.dayun_hits && j.dayun_hits.length) {
    /* R216b 续5（UX 队列 U-004）：warm 模式下 8 行干支大运表信息过载，
     * 收进默认折叠（事实零删减）；pro 模式保持平铺。 */
    /* R228n：五列表 320px 下 min-content 超容器 11px→整页横滚；
     * 外包 .table-scroll 让表自己滚。 */
    /* R232b（R40-W9）：加「约几岁」列——「几岁」比「哪年」对目标
     * 用户更直觉（后端 start_age_a/_b 早算好了没露）。 */
    var _table = '<div class="table-scroll"><table class="works"><thead><tr><th>大运</th><th>甲干支</th><th>乙干支</th>' +
      '<th>关系</th><th>约起年</th><th>约几岁</th></tr></thead><tbody>';
    j.dayun_hits.forEach(function (d) {
      var _ages = (d.start_age_a != null || d.start_age_b != null)
        ? (d.start_age_a ?? '—') + '/' + (d.start_age_b ?? '—') : '';
      _table += '<tr><td>第 ' + esc(d.index) + ' 运</td><td>' + esc(d.pillar_a) +
        '</td><td>' + esc(d.pillar_b) + '</td><td>' + esc(d.relation) +
        '</td><td class="num">' + esc(d.year_start) + '</td>' +
        '<td class="num">' + esc(_ages) + '</td></tr>';
    });
    _table += '</tbody></table></div>';
    if (voiceMode() === 'warm') {
      html += '<details class="warm-basis"><summary>📅 大运合拍表（' +
        j.dayun_hits.length + ' 行，展开看）</summary>' + _table + '</details>';
    } else {
      html += '<h3 style="margin-top:16px;">十年一轮的节奏表</h3>' + _table;
    }
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
  return html;
}

/* R230z（R36-P1-1）：渲染体抽为顶层 builder——历史台账「复看」
 * 按 rec.type 回放同一渲染；do* 里只剩 paint 一行。 */
function buildTaohuaResult(j) {
  let html = '<div class="card"><h2>🌺 桃花运</h2>';
  /* R218a-巡2（N-08）：装饰图——桃花卡顶部加 SVG/CSS 装饰 banner。 */
  html += renderDecoration('taohua');
  // R193b：分享海报入口（对齐排盘 shareBazi，T3.1 同款零依赖 Canvas）
  html += '<button class="ghost fav-btn" type="button" id="shareTaohua" ' +
    'title="生成分享图">📸 分享图</button>';
  const bz = j.bazi || {};
  // R187b：人话视图置顶（specs/005 US4——先说人话，再看坐标）
  if (j.warm) {
    html += '<div class="warm-wrap"><div class="warm-l0">' +
      esc(j.warm.one_liner || '') + '</div><div class="warm-reply">';
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
      html += '<span class="pill" style="background:' + colorAt(i) + ';">' +
        esc(bz[k]) + '</span>';
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
    html += '<h3 style="margin-top:16px;">桃花什么时候旺</h3>' +
      '<div class="table-scroll"><table class="works"><thead><tr><th>运</th><th>干支</th><th>约起年</th>' +
      '<th>约几岁</th></tr></thead><tbody>';
    j.dayun_hits.forEach(function (d) {
      html += '<tr><td>第 ' + esc(d.index) + ' 运</td><td>' + esc(d.pillar) +
        '</td><td class="num">' + esc(d.year_start) + '</td>' +
        '<td class="num">' + esc(d.start_age != null ? d.start_age : '') +
        '</td></tr>';
    });
    html += '</tbody></table></div>';
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
  html += tailHook('taohua');
  html += '</div>';
  return html;
}

/* R230z（R36-P1-1）：渲染体抽为顶层 builder——历史台账「复看」
 * 按 rec.type 回放同一渲染；do* 里只剩 paint 一行。 */
function buildQimingResult(j) {
  let html = '<div class="card"><h2>🌸 起名推荐</h2>';
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
  html += '<div class="qm-style-hint" id="qmStyleHint">' +
    esc((_QM_STYLES[_QM_STYLE] || {}).hint || '') + '</div>';
  const bz = j.bazi || {};
  if (bz.render) html += '<p class="paipan-line">' + esc(bz.render) + '</p>';
  const fe = j.five_elements || {};
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
      '<span style="font-size:12px;color:var(--secondary);font-weight:400;">　评分口径：五行补缺+典籍出处+寓意+音形+气质契合</span></h3>' +
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
        '<p style="font-size:13px;color:var(--secondary);">五行：' +
        esc((n.elements || []).join('·')) +
        (n.form === 'single' ? '　单字名' : '　双字名') + '</p>' +
        '<div class="qm-parts">' + chips + '</div>';
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
    /* R218a-04：「换一批」总入口——按当前风格顺位 +1 重新选 8 个 */
    var _next = ({'classics': 'chuci', 'chuci': 'fresh',
                  'fresh': 'classics', 'all': 'classics'})[_QM_STYLE] || 'classics';
    html += '<div class="qm-refresh-row">' +
      '<button class="chat-entry" type="button" id="qmRefreshBtn" ' +
      'title="按 ' + esc(_QM_STYLES[_next].label) + ' 风格再来 8 个">' +
      '🔄 换一批（' + esc(_QM_STYLES[_next].label) + '）</button>' +
      '<span class="qm-refresh-hint" id="qmRefreshHint"></span>' +
      '</div>';
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
      '<p style="font-size:13px;color:var(--secondary);">五行：' +
      esc(n.element || '') + '　出处：' + esc(n.radical || '') + '</p>' +
      '<p style="font-size:13px;">' + esc(n.meaning || '') + '</p></div>';
  });
  html += '</div></details>';
  /* R220b：交叉引用铺到起名——太阳星座气质给挑名字一个参考角度 */
  if (j.cross_ref && j.cross_ref.message) {
    html += '<div class="cross-ref"><span class="cross-ref-icon">✨</span>' +
      esc(j.cross_ref.message) + '</div>';
  }
  html += renderAiPolish(j);
  html += tailHook('qiming');
  /* R229z续23（R11-#4）：起名卡此前全程无免责徽标 */
  html += '<div style="font-size:12px;color:var(--muted);margin-top:10px;">名字综合古籍意象与五行给的参考，仅供娱乐——孩子的名字还是家里人说了算 ✨</div>';
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
      detail = '这条消息有点怪——换个说法再发我';
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
  if (kind === 'error') {
    t.addEventListener('mouseenter', function () { clearTimeout(_tmr); });
    t.addEventListener('mouseleave', function () {
      _tmr = setTimeout(function () {
        t.classList.remove('show');
        setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 250);
      }, 3000);
    });
    t.addEventListener('focusin', function () { clearTimeout(_tmr); });
  }
}

function postJSON(path, payload) {
  return api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
}

/* ── AI 段落后到（R191b，B-014 / specs/006 判据 9/10、D-251b）──────
 * 后端不再同步等 LLM（实测开启 LLM 时端点阻塞 35s）。响应带 ai_task_id
 * 时前端渲染完确定性主体就轮询 /api/ai/{id}；拿到文本就地追加 .ai-polish
 * 容器。failed / 404 / 超时 → 整块不渲染——降级语义与 D-244a 完全一致，
 * LLM 永远不是承重墙。RESULT_GEN 是「结果区世代号」：同一容器发起新请求
 * 会令旧轮询自动作废，防止慢任务回来后污染新一轮结果。 */
var RESULT_GEN = {};
var AI_POLL_INTERVAL_MS = 500;
var AI_POLL_CAP_S = 40;            // 与后端 _POLL_CAP_S 对齐

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
      d.className = 'chat-bubble chat-ai';
      d.style.opacity = '.72';
      d.style.fontSize = '.9em';
      d.textContent = '（小满刚换了新脑子，前面聊的细节可能记不全啦）';
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
  var d = document.createElement('div');
  d.className = 'chat-bubble chat-ai';
  d.style.opacity = '.72';
  d.style.fontSize = '.9em';
  d.textContent = '（隔得有点久，前面聊的细节小满可能记不全啦）';
  ty.parentNode.insertBefore(d, ty);
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
  showToast('小满又补了一句 ✦', 'info');
  return true;
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
          var entry = LAST_RESPONSE[containerId];   // 让口吻切换重画也带上 AI 块
          if (entry && entry.json) entry.json.ai_polish = st.text;
        }
        _done();
        return;                                      // 终态：停止轮询
      }
      if (st && st.status === 'failed') { _done(); return; }  // 拿不到 → 整块不渲染
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
  } catch (e) { return 'c-anon'; }
}
var CHAT_LAST_FACTS = [];   /* 最近一次排盘的坐标事实（干支五行词，非 PII） */
var _CHAT_SEND_COUNT = 0;   /* D-006：追踪聊天发送次数，第一条自动发后允许追问 1 次 */

/* R230q（R28-P2-4）：sid 在 sessionStorage 里跨刷新存活，但气泡清空后
 * 新消息会悄悄接进用户看不见的上一轮上下文。把气泡 transcript 与 sid
 * 同介质存储，刷新后原样重渲（上限 50 条与 chatBubble 裁剪一致）。 */
var CHAT_TS_KEY = 'chatTranscript';
function _chatTsRead() {
  try {
    var s = (_chatStore() || _MEM_STORE).getItem(CHAT_TS_KEY);
    var arr = s ? JSON.parse(s) : [];
    return Array.isArray(arr) ? arr : [];
  } catch (e) { return []; }
}
function _chatTsSave(role, text) {
  try {
    var arr = _chatTsRead();
    arr.push({ r: role === 'me' ? 'me' : 'ai', t: String(text || '').slice(0, 2000) });
    if (arr.length > 50) arr = arr.slice(-50);
    (_chatStore() || _MEM_STORE).setItem(CHAT_TS_KEY, JSON.stringify(arr));
  } catch (e) {}
}
function _chatTsClear() {
  try { (_chatStore() || _MEM_STORE).removeItem(CHAT_TS_KEY); } catch (e) {}
}
function _chatTsRestore() {
  /* 刷新后把存下的气泡重渲回来；nosave 防止重渲又双写 transcript。 */
  _chatTsRead().forEach(function (m) {
    chatBubble(m.r === 'me' ? 'me' : 'ai', m.t, { nosave: true });
  });
}

/* R219b（P0-2）：各视图最近一次 API 响应缓存——「聊聊这件事」要把真实牌面/
 * 盘面/结果拼进第一句话，AI 才有东西可解。键 = 视图短名（bazi/taohua/
 * tarot/liuyao/hehun/huangli/qiming/xingzuo），值 = {json, question}。
 * 只存内存，随刷新丢弃（不落库——历史记录功能已按用户裁决删除）。 */
var LAST_RESULT = {};
function rememberResult(viewKey, json, question, body) {
  /* v2：多存一份 body（含 gender 等），供 buildChatContext 拼性别。 */
  LAST_RESULT[viewKey] = { json: json || {}, question: question || '',
                           body: body || {} };
  /* R233m（R45-P3）：sessionStorage 续接——刷新后「聊聊这件事」不再
   * 退化成无上下文泛化句。tab 关闭即焚，不落 localStorage。 */
  try {
    var _js = JSON.stringify(LAST_RESULT[viewKey]);
    if (_js.length < 200000) sessionStorage.setItem('lastResult:' + viewKey, _js);
  } catch (e) {}
  /* R233r（R49-P3-2）：新结果落地顺带刷新空态 chips 语境。 */
  try { _chatChipsPersonalize(); } catch (e) {}
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
      daily: '今天运势怎么样'
    };
    return { msg: GENERIC[viewKey] || '帮我看看这个结果', facts: [] };
  }
  if (viewKey === 'tarot') {
    var cards = (j.draws || []).map(function (d) {
      return d.name + '·' + (d.upright ? '正位' : '逆位') +
        (d.position ? '（' + d.position + '）' : '');
    });
    msg = '我抽了' + (cards.join('、') || '牌') +
      (q ? '，问题是「' + q + '」' : '') + '，帮我解读';
    facts = cards.map(function (c) { return '牌：' + c; });
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
  } else if (viewKey === 'hehun') {
    var a = j.a_bazi || {}, b = j.b_bazi || {};
    /* R229z续23（R11-#10）：A/B → 甲/乙，与表单/422 口径统一 */
    msg = '我的日柱' + (a.day || '—') + '（日主' + (a.day_master || '—') +
      '），TA 的日柱' + (b.day || '—') + '（日主' + (b.day_master || '—') +
      '），我俩配吗';
    facts = ['我的日柱：' + (a.day || '—'), 'TA 的日柱：' + (b.day || '—')];
    if (j.day_wx_sheng !== undefined) {
      /* R230a-7（R13-P0-2）：同五行是比和，不是相克 */
      facts.push('日主五行：' + (j.day_wx_sheng ? '相生' :
                                 (j.day_wx_same ? '比和' : '相克')));
    }
  } else if (viewKey === 'huangli') {
    var yi = (j.yi || []).slice(0, 3).join('、');
    var ji = (j.ji || []).slice(0, 3).join('、');
    msg = '今天是' + (j.date || '今天') + '，宜' + (yi || '—') + '，忌' +
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
  } else if (viewKey === 'liuyao') {
    var ben = j.ben || {};
    var moving = (ben.moving_lines || []).join('、');
    msg = '我摇到的是' + (ben.gua_name || '—') + '卦（第' +
      (ben.gua_number || '—') + '卦）' + (moving ? '，动爻在' + moving : '') +
      (q ? '，问的是「' + q + '」' : '') + '，这卦怎么看';
    facts = ['本卦：' + (ben.gua_name || '—')];
    if (moving) facts.push('动爻：' + moving);
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
  } else if (viewKey === 'xingzuo') {
    var today = (j.signs || []).filter(function (s) { return s.is_today; })[0];
    /* R229z续23（R11-#23/#36）：「今天是 2026-…」双空格＋「值宫」术语 */
    msg = '今天是' + (j.date || '') + '，'
      + ((today && today.sign) || '—') + '座当班，我今天运势怎么样';
    facts = ['今天轮到' + ((today && today.sign) || '—') + '座当班'];
  } else {
    msg = '帮我看看这个结果';
  }
  return { msg: msg, facts: facts.slice(0, 6) };
}

/** R207b：聊天入口全局化——结果容器渲染出 .card 后尾部统一挂入口钮。
 *  已有则跳过（重绘安全）；无 .card（如空态/错误态）不挂。 */
function attachChatEntry(container) {
  if (!container) return;
  /* R230k（R23-P2-1）：星座结果根节点是 .xz-result、本命盘抽屉是
   * .birth-card——都不含 .card，入口钮一直挂不上（实测这三面计数=0）。
   * 选择器放宽到已知结果壳。 */
  var card = container.querySelector('.card, .xz-result, .birth-card');
  /* R230t（R33-P1-1）：判重走 data-chat-entry 而非类名——qmRefreshBtn/
   * nameReviewBtn 也用 .chat-entry 做样式，此前会误判「已有入口」跳过。 */
  if (!card || card.querySelector('[data-chat-entry]')) return;
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
}

/* R230d（R16-P2-7）：轮数封顶后此前只复读收尾文案，用户没有任何
 * 出路提示。后端 rec.closed=True 时在气泡尾部挂「开新话题」引导钮——
 * 点了换新 sid（旧会话仍在内存，只是不再继续聊）。 */
function _chatClosedHint(bubble) {
  if (!bubble || bubble.querySelector('.chat-reset')) return;
  var row = document.createElement('div');
  row.className = 'chat-reset';
  row.style.marginTop = '8px';
  var b = document.createElement('button');
  b.type = 'button'; b.className = 'chat-chip';
  b.setAttribute('aria-label', '清空本轮聊天，开个新话题');
  b.textContent = '🌱 聊够啦？开个新话题';
  b.addEventListener('click', function () {
    /* R230t（R33-P2-4）：清 transcript+换 sid 此前一点即执行——
     * 两点确认与排盘删除同款（3s 内再点才真清）。 */
    if (b.dataset.armed !== '1') {
      b.dataset.armed = '1';
      b.textContent = '这轮聊天记录会清空，再点一次确认';
      setTimeout(function () {
        if (b.isConnected) { b.dataset.armed = '0'; b.textContent = '🌱 聊够啦？开个新话题'; }
      }, 3000);
      return;
    }
    try { (_chatStore() || _MEM_STORE).removeItem(CHAT_SID_KEY); } catch (e) {}
    chatSid();   /* 重新生成 sid */
    _chatTsClear();   /* R230q：新话题起新 transcript——旧气泡重渲会污染新会话 */
    var _flow = el('chatFlow');
    if (_flow) _flow.innerHTML = '';
    _CHAT_SEND_COUNT = 0;
    chatBubble('ai', '新话题开张～想聊什么？');
    row.remove();
  });
  row.appendChild(b);
  bubble.appendChild(row);
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
   'bazi'].forEach(function (k) {
    if (!viewKey && viewId.indexOf(k) !== -1) viewKey = k;
  });
  var ctx = buildChatContext(viewKey);
  var msg = ctx.msg;
  /* facts 优先用本视图的结构化坐标；为空时回落到排盘时存的 CHAT_LAST_FACTS */
  var facts = (ctx.facts && ctx.facts.length) ? ctx.facts : CHAT_LAST_FACTS;
  chatBubble('me', msg);
  /* R230t（R32-P2-16）：自动发与手发同口径计数——此前自动发不计数，
   * 同一会话两套禁用行为并存（「允许追问 1 次」的语义本就该含自动条）。 */
  _CHAT_SEND_COUNT = (_CHAT_SEND_COUNT || 0) + 1;
/* R230v（R34-#3）：同 chatSend——捕获 sid 防跨话题幻影写回。 */
  var _sid0 = chatSid();
  var _ty0 = chatBubble('ai', '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span>', {raw: true});   /* R2343 */
  postJSON('/api/chat', {
    /* R230l（R24-P2-3）：黄历事实的「今天」锚浏览器本地日——服务器
     * UTC vs 浏览器 CST 跨零点窗口整天错位。 */
    session_id: _sid0, message: msg, facts: _chatFacts(facts),
    client_date: todayIso()
  }).then(function (j) {
    if (!j.chat_task_id) {
      if (_ty0) { _ty0.remove(); _ty0 = null; }
      /* R218a-02：U-008 修复后仍复用同一句话「打烊中」复读——扩展为
       * 4-6 句确定性轮换，并按上下文（自动发送：必属「看盘」类）做轻回应。 */
      chatBubble('ai', _chatFallbackLine('看盘'), { nosave: true });
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
      '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span>', {raw: true});
    _pollChatReply(j.chat_task_id, _ty, _sid0);   /* R233r：共用轮询体（含排队预算） */
  }).catch(function () {
    if (_ty0) { _ty0.remove(); _ty0 = null; }
    chatBubble('ai', '（' + _dayPick(['网络不太好，再发一次试试？','信号飘了，一会儿再戳我','刚才没接到，再发一次吧～'],'net') + '）', { nosave: true });
  });
}

/* R233r（R49-P3-3）：两处轮询体抽出共用——chatSend 与
 * autoSendChatContext 此前逐字各持一份 ~75 行（且 autoSend 版漏声明
 * _queueCap，排队态引用未定义变量会炸掉整个 tick）。
 * 约定：tid=任务id；ty=typing气泡节点；sid0=发送时sid。 */
function _pollChatReply(tid, ty, sid0) {
  var deadline = performance.now() + AI_POLL_CAP_S * 1000;
  var _queueCap = performance.now() + 90000;
  var _wait = AI_POLL_INTERVAL_MS;
  var _failTxt = function () {
    return '（' + _dayPick(['网络不太好，再发一次试试？','信号飘了，一会儿再戳我','刚才没接到，再发一次吧～'],'net') + '）';
  };
  var tick = function () {
    if (sid0 !== chatSid()) return;   /* 换过 sid 的旧任务落地即弃 */
    if (_aiPollGate()) {              /* 后台/断网暂停取数，预算照走 */
      if (performance.now() < deadline) setTimeout(tick, 2000);
      else if (ty) { ty.textContent = _failTxt(); }
      return;
    }
    api('/api/ai/' + encodeURIComponent(tid), { silent: true }).then(function (st) {
      if (!ty || sid0 !== chatSid()) return;
      if (st && st.status === 'done' && st.text) {
        _chatBootNote(st, ty);       /* 重启失忆插分隔 */
        _chatFreshNote(st, ty);      /* TTL 回收分隔 */
        ty.innerHTML = renderRichText(st.text);
        _chatTsSave('ai', st.text);
        if (st.closed) _chatClosedHint(ty);
        return;
      }
      if (st && st.status === 'failed') {
        ty.innerHTML = renderRichText('（小满这次没接住，再说一遍试试？）');
        return;
      }
      if (st && st.status === 'pending' && st.queued) {
        /* 服务端排队中——生成预算从起动起算。 */
        if (performance.now() < _queueCap) {
          setTimeout(tick, _wait); _wait = _aiBackoff(_wait);
        } else { ty.textContent = '（小满有点忙，再发一次试试？）'; }
        return;
      }
      if (performance.now() < deadline) { setTimeout(tick, _wait); _wait = _aiBackoff(_wait); }
      else { ty.textContent = _failTxt(); }
    }).catch(function (e) {
      /* 404 = 任务已不在（重启/过期）——早退不轮满预算。 */
      if (e && e.status === 404) {
        if (ty) { ty.textContent = '（这次没接住，再发一次试试？）'; }
        return;
      }
      if (performance.now() < deadline) { setTimeout(tick, _wait); _wait = _aiBackoff(_wait); }
      else if (ty) { ty.textContent = _failTxt(); }
    });
  };
  setTimeout(tick, AI_POLL_INTERVAL_MS);
}

/* R218a-02：聊天降级文案池 + 关键词到 openeer 的最轻量级分支。
 * 数据池与 src/guji/copy_bank.json#chat_fallback_openers 同源（aditive 复制），
 * 选句策略：同 session 内消息序号 = 轮换种子（同用户复读也变），关键词匹配
 * 命中后取对应池的第 (counter % pool_size) 句。零 API 契约变更、零后端改动。 */
var _CHAT_FALLBACK_DEFAULT = [
  "今天小满提前打烊啦～先把上面的牌面看着，想聊的时候随时来，我一直在这。",
  "解忧铺这会儿休整中，发的心事我记下了——随时回来听我细说。",
  "小满现在不上班，门口的牌子写着『歇业中』✨ 你先歇会儿，想聊再来。",
  "这会儿小满调休中～把心事先写下来，我一回来就翻你的牌。",
  "打烊了哦～这条消息我存着，下回开门接着说。",
  "解忧铺的灯这会儿关了——你的心事没丢，开门第一单给你留着。",
  "我先歇一会儿，存好你的话，回来带着力气一起拆。",
  "小满今晚关店早，你先看看上面那张牌的提示，回来找我深聊。",
  "门牌已经翻到『休息中』，你的消息我存着——先睡个好觉。",
  "解忧铺的茶这会儿凉了，重新烧上了——你写下来的我都会读。"
];
var _CHAT_FALLBACK_BY_KW = {
  'tired': [
    "累了啊…小满这会儿不在岗，细节留着我回来听。先喝口温水，别再撑了。",
    "听着就累。先把肩膀松下来，回头来找我，咱们一件一件拆。",
    "身体先叫停一下比什么都重要。先睡饱，回头找我。",
    "累的时候做的决定十有八九会后悔，先放放，回头来。",
    "辛苦了。今晚把待办关掉，明天的你再收拾残局也来得及。",
    "先给自己续杯热水。你的累我记着了，回来慢慢说。"
  ],
  'work': [
    "工作的坎儿先不急开会——思路睡一觉会清楚很多，回头找我聊细节。",
    "听到工作的苦。回头跟我讲讲你卡在哪一环，咱们一起拆。",
    "工作的事先放我这儿，你今晚先下班。",
    "职场的弯弯绕绕回来拆给你听。先喝口热的，喘口气。",
    "班先下了，委屈先搁我这儿。回头咱们一条一条过。",
    "这份活不決定你的价值——先歇，回来慢慢说。"
  ],
  'love': [
    "感情的事急也急不出答案。先放过自己，回头来跟我讲。",
    "爱里的纠结最难熬。回头来找我，把心意慢慢理顺。",
    "先不猜他的心思了，回头来听我说说牌面给的信号。",
    "心动或心累都先收着，回来我陪你解。",
    "那个人怎么想先放放——你先照顾好今晚的自己。",
    "感情里没有标准答案，你讲得开心最要紧。回头细聊。"
  ],
  'study': [
    "学习的压力先放一放，脑子也需要打烊。回头我陪你拆重点。",
    "考试的事先交给睡一觉的自己——先复盘三件今天做对的小事。",
    "学不进去的时候别硬撑，回头来我帮你把节奏理一理。",
    "作业的事回头再战。先奖励自己一集短剧。",
    "分数是一时的，你一直在往前走就很棒。回头聊。",
    "背不进去就先合上书本，去倒杯水。回来我陪你理思路。"
  ],
  'money': [
    "钱包的事回头再算——先不想钱的事。",
    "理财的纠结回来拆给你听。先关掉账单页面。",
    "先不数余额。回头来找我，把账本翻一遍。",
    "钱的事别熬夜想——夜里做的预算都偏严。回头聊。",
    "挣钱是长跑，今天先不比配速。回头帮你看看开源思路。",
    "钱包君也需要假期——先吃顿好的（预算内），回头再算。"
  ],
  'default': [
    "今天小满提前打烊啦～先把上面的牌面看着，我一直在这。",
    "解忧铺这会儿休整中，你的心事我存着，随时来听。",
    "门牌已经翻到『休息中』，回头找我深聊。",
    "解忧铺的茶凉了，重新烧上了——你写下来的我都会读。",
    "小满去后院浇水了，你的话挂在门口的风铃上——回来就听。",
    "这会儿我在整理书架，你的那一条排第一个。"
  ]
};
/* 关键词→分类映射（命中第一个即用） */
var _CHAT_FALLBACK_KW_MAP = [
  { cat: 'tired',   kws: ['累', '疲惫', '睡', '失眠', '撑', '撑不住', '废', '躺'] },
  { cat: 'work',    kws: ['工作', '职场', '同事', '老板', '上司', '升职', '跳槽', '上班', '加班', '辞职'] },
  { cat: 'love',    kws: ['感情', '恋爱', '喜欢', '分手', '前任', '对象', '暗恋', '表白', '相亲', '暧昧'] },
  { cat: 'study',   kws: ['学习', '考试', '作业', '考研', '高考', '中考', '成绩', '课程', '论文', '答辩'] },
  { cat: 'money',   kws: ['钱', '工资', '消费', '理财', '账单', '余额', '省钱', '欠款', '花呗'] },
  { cat: 'reading', kws: ['牌', '卦', '命', '盘', '解盘', '看看', '解读', '分析', '看'] }
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
  return pool[idx];
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
function pollNameReview(taskId) {
  var _gen = _NR_GEN;
  var deadline = performance.now() + AI_POLL_CAP_S * 1000;   /* R230t（R31-P2-9）：轮询预算用单调钟——系统时钟回拨不再冻死轮询 */
  var _wait = AI_POLL_INTERVAL_MS;    /* R230t（R32-P2-20）：退避轮询 */
  var tick = function () {
    if (_gen !== _NR_GEN) { _nameReviewDone(); return; }   /* 新点评接管 */
    if (_aiPollGate()) {   /* R230q（R28-P3-8）：后台/断网暂停取数 */
      if (performance.now() < deadline) setTimeout(tick, 2000);
      else { var o0 = el('nameReviewOut'); if (o0) o0.innerHTML =
        '<div class="no-evidence">超时了，再试一次？</div>'; _nameReviewDone(); }
      return;
    }
    api('/api/ai/' + encodeURIComponent(taskId), { silent: true }).then(function (st) {
      const out = el('nameReviewOut');
      if (!out || _gen !== _NR_GEN) { _nameReviewDone(); return; }
      if (st && st.status === 'done' && st.text) {
        out.innerHTML = '<div class="tarot-deep"><h4>📜 AI 点评</h4><p style="white-space:pre-wrap;">' +
          renderRichText(st.text) + '</p></div>';   /* R227b：esc 会让 ** 原样露出 */
        _nameReviewDone();
        return;
      }
      if (st && st.status === 'failed') {
        out.innerHTML = '<div class="no-evidence">这次没点评出来，稍后再试</div>';
        _nameReviewDone();
        return;
      }
      if (performance.now() < deadline) { setTimeout(tick, _wait); _wait = _aiBackoff(_wait); }
      else { out.innerHTML = '<div class="no-evidence">超时了，再试一次？</div>'; _nameReviewDone(); }
    }).catch(function (e) {
      /* R228c：同上——瞬时抖动不该杀死轮询。R8 P2-9：404 早退。 */
      var out2 = el('nameReviewOut');
      if (e && e.status === 404) {
        if (out2) out2.innerHTML = '<div class="no-evidence">这次没点评出来，稍后再试</div>';
        _nameReviewDone();
        return;
      }
      if (performance.now() < deadline) { setTimeout(tick, _wait); _wait = _aiBackoff(_wait); }
      else { if (out2) out2.innerHTML = '<div class="no-evidence">超时了，再试一次？</div>'; _nameReviewDone(); }
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
  if (flow) setTimeout(function () {
    flow.scrollTop = flow.scrollHeight;
    var inp = el('chatInput');
    if (inp && window.innerWidth > 767) inp.focus();
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
  t.textContent = '我是小满，解忧铺的店员。\n最近有什么心事，都可以跟我说说——\n仅供陪伴，不构成任何建议。';
  d.appendChild(t);
  flow.appendChild(d);
}
function chatBubble(role, text, opts) {
  var flow = el('chatFlow');
  if (!flow) return null;
  /* R228c：清掉所有空态块（静态 #chatEmpty + JS 注入的 .chat-empty）——
   * 原来只删 getElementById 第一个，注入那份会残留夹在气泡之间。 */
  document.querySelectorAll('.chat-empty').forEach(function (n) { n.remove(); });
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
  flow.scrollTop = flow.scrollHeight;
  return div;   /* 轮询写回用节点引用，不赌 lastChild */
}
/* R233r（R49-P0）：危机词前端镜像——后端 _CRISIS_PAT 只在任务真起
 * 时才跑得着；DISABLE/限流/排队满时 spawn 返回 None，此前危机会被
 * _chatFallbackLine 卖萌句吞掉。本地镜像词表+转介文案，不发请求。 */
var _CRISIS_FE_PAT = new RegExp(
  '不想活|想死|自杀|自残|伤害自己|活着没意思|想不开|轻生|跳楼|抑郁|' +
  '活不下去|活着好累|想消失|不想在了|烧炭|割腕|跳河|上吊|安眠药|' +
  'suicide|kill\\s*myself|end\\s*it', 'i');
var _CRISIS_FE_REPLY = '这个话题有点重，我不太敢乱说。如果心里真的很难受，' +
  '全国心理援助热线 12356（24 小时，免费）随时能打通，跟信任的朋友聊聊' +
  '也会好一些——我一直都在，陪你聊聊别的也行。';

/* R233r（R49-Top5-2）：chatSend 兜底 facts——不走排盘直接开聊时
 * CHAT_LAST_FACTS 恒空；按当前活跃视图从 LAST_RESULT 拼坐标。 */
function _activeViewFacts() {
  var v = document.querySelector('.view.active');
  var vid = v ? v.id : '', key = '';
  ['taohua', 'tarot', 'liuyao', 'hehun', 'huangli', 'qiming', 'xingzuo',
   'bazi'].forEach(function (k) {
    if (!key && vid.indexOf(k) !== -1) key = k;
  });
  if (!key) key = 'daily';   /* 首页无 .view 壳——daily 卡上下文兜底 */
  var c = buildChatContext(key);
  return (c && c.facts) || [];
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

function _chatFacts(facts) {
  var _f = (facts || []).slice();
  try {
    var _me = _meGet('me');
    var _n = _me ? _meNickClean(_me.n) : '';
    if (_n) _f.unshift('她叫' + _n + '——聊天时自然地喊她名字，别每句都喊');
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
  if (_CRISIS_FE_PAT.test(msg)) {
    chatBubble('ai', _CRISIS_FE_REPLY);
    return;
  }
  /* D-006：追踪发送次数，第一条自动发后允许追问 1 次，第 2 次回复后才锁 */
  _CHAT_SEND_COUNT = (_CHAT_SEND_COUNT || 0) + 1;
  /* R230v（R34-#3）：捕获发送时 sid——在途回复遇上「开个新话题」换 sid
   * 时，旧任务落地不得把回复写进新 transcript（幻影气泡）。 */
  var _sid0 = chatSid();
  /* R2343（R58-P2-2）：发送即有 typing 三点——此前要等 chat_task_id
   * 回来才出现，慢服务下静默 20 秒像没发出去。 */
  var _ty0 = chatBubble('ai', '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span>', {raw: true});
  postJSON('/api/chat', {
    session_id: _sid0, message: msg,
    facts: _chatFacts((CHAT_LAST_FACTS && CHAT_LAST_FACTS.length)
      ? CHAT_LAST_FACTS : _activeViewFacts()),   /* R233r：无排盘按视图兜底 */
    client_date: todayIso()   /* R230l */
  }).then(function (j) {
    if (!j.chat_task_id) {                     /* DISABLE：入口静默降级 */
      if (_ty0) { _ty0.remove(); _ty0 = null; }
      /* R216b 续3（UX 队列 U-008）：原降级文案「（聊天功能暂时没开，
       * 稍后再来吧）」系统腔零共情——用户刚倾诉疲惫。改为情绪承接 +
       * 替代引导；DISABLE 态输入框置灰防连发连拒。
       * R218a-02：扩为 4-6 句确定性轮换 + 关键词到 openeer 的最轻分支
       * （累/事业/感情/学业/钱/看盘 6 套）。 */
      chatBubble('ai', _chatFallbackLine(msg), { nosave: true });
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
      '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span>', {raw: true});
    _pollChatReply(j.chat_task_id, _ty, _sid0);   /* R233r：共用轮询体（含排队预算） */
  }).catch(function (e) {
    if (_ty0) { _ty0.remove(); _ty0 = null; }
    /* R230t（R32-P2-19）：4xx 是内容被拦（消息超长/facts 超限等），
     * 不是网络问题——保留已发气泡、如实报服务端文案，别回收成「被吞了」。 */
    if (e && e.status >= 400 && e.status < 500) {
      chatBubble('ai', '（' + (e.message || '这条没发出去') + '）',
                 { nosave: true });
      return;
    }
    /* R230q（R28-P3-11）：发送失败把已打文案放回输入框，离线不丢稿 */
    if (input && !input.disabled) input.value = msg;
    /* 已贴出的 me 气泡同时从 transcript 与 DOM 回收——重试不再双发同句 */
    try {
      var _arr = _chatTsRead();
      if (_arr.length && _arr[_arr.length - 1].r === 'me' &&
          _arr[_arr.length - 1].t === msg) {
        _arr.pop();
        (_chatStore() || _MEM_STORE).setItem(CHAT_TS_KEY, JSON.stringify(_arr));
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
    if (_btn && _btn.tagName === 'BUTTON') {
      _btn.disabled = false;
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
  document.querySelectorAll('.view').forEach(function (v) {
    v.classList.remove('active');
  });
  const target = el('view-' + viewId);
  if (target) target.classList.add('active');
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
      ((document.querySelector('.func-card[data-view="' + viewId + '"] .func-name') || {}).textContent || viewId);
    document.title = (_vn ? (_vn + ' · ') : '') + '小满的解忧铺 · 知命';
  } catch (eT) {}
  window.__inView = !isHome;
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
  window.__suppressPush = true;
  try {
    showView((e.state && e.state.view) ? e.state.view : 'home');
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
    return '<div class="no-evidence">' + esc(o.empty || '这次没翻到——换个词试试？') + '</div>';
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
      (o.score && h.score != null ? '<span class="hit-score" title="BM25 相关度：负分，越接近 0 越相关">相关度 ' +
        esc(Number(h.score).toFixed(1)) + '</span>' : '') +
      '</div>';
    html += '<div class="ev-text">' + esc(h.text || '') + '</div>';
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
    return '<div class="no-evidence">' + esc(o.empty || '这次没翻到——换个词试试？') + '</div>';
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
   * 两次确认补拉；期间用户主动滚动（滚轮/触摸/按键）则不补。 */
  var _userMoved = false;
  var _stop = function () { _userMoved = true; };
  window.addEventListener('wheel', _stop, { passive: true, once: true });
  window.addEventListener('touchmove', _stop, { passive: true, once: true });
  window.addEventListener('keydown', _stop, { passive: true, once: true });
  var _confirm = function () {
    if (_userMoved) return;
    if (Math.abs(window.scrollY - target) > 4) window.scrollTo({ top: target, behavior: 'auto' });
  };
  requestAnimationFrame(function () { requestAnimationFrame(_confirm); });
  setTimeout(_confirm, 260);
  /* R230j（R22-P2-1）：once 监听在用户无滚轮/触摸/按键时永不自行
   * 回收，每次提交积 3 个（55 次提交实测 +150）。最后一次 _confirm
   * 跑完后三监听使命已尽——主动摘掉。 */
  setTimeout(function () {
    window.removeEventListener('wheel', _stop);
    window.removeEventListener('touchmove', _stop);
    window.removeEventListener('keydown', _stop);
  }, 300);
}

/* ── 口吻模式（004 US3：一键切回）─────────────────────────────
 * warm = 温柔口吻（默认，用户指示的正面回应）；pro = 专业模式。
 * 专业模式渲染路径**完全不变**——warm 是新增分支（判据 9）。
 * 选择存 localStorage，下次打开保持（US3.4）。 */
var VOICE_KEY = 'voiceMode';

function voiceMode() {
  try {
    var v = localStorage.getItem(VOICE_KEY);
    return v === 'pro' ? 'pro' : 'warm';
  } catch (e) {
    return 'warm';       // 隐私模式下 localStorage 可能抛异常
  }
}

function setVoiceMode(mode) {
  try {
    localStorage.setItem(VOICE_KEY, mode === 'pro' ? 'pro' : 'warm');
  } catch (e) { /* 存不了就只在本次会话生效 */ }
}

/** 模式切换控件。44×44 起（003 判据 1），两态都有可见焦点环。 */
function renderModeSwitch() {
  var m = voiceMode();
  return '<div class="mode-switch" role="group" aria-label="解读口吻">' +
    '<button type="button" class="mode-btn' + (m === 'warm' ? ' active' : '') +
    '" data-voice="warm" aria-pressed="' + (m === 'warm') + '">🌸 温柔版</button>' +
    '<button type="button" class="mode-btn' + (m === 'pro' ? ' active' : '') +
    '" data-voice="pro" aria-pressed="' + (m === 'pro') + '">📐 专业版</button>' +
    '</div>';
}

/* ── 视觉主题（003 US5 / 判据 12：审美方向可一键回滚）───────────
 * aa     = R183b 的无障碍配色（默认；31 处对比度不足已归零）
 * legacy = R183b 之前的原配色（对照用；**不满足判据 3**，那正是它的意义）
 * 只切 <html data-theme>，CSS 侧只覆盖令牌不碰规则集——所以回滚路径
 * 不需要反向修改任何组件样式，不可能漏。 */
var THEME_KEY = 'uiTheme';

function uiTheme() {
  try {
    var v = localStorage.getItem(THEME_KEY);
    if (v === 'legacy' || v === 'dark') return v;
    /* R2340：没存过就跟系统深浅色走（睡前场景占大头） */
    if (v == null && window.matchMedia &&
        matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
  } catch (e) {}
  return 'aa';
}

function applyTheme(theme) {
  var t = (theme === 'legacy' || theme === 'dark') ? theme : 'aa';
  /* R2340：theme-color meta 跟着换——浏览器地址栏/PWA 顶栏同色。 */
  var _meta = document.querySelector('meta[name="theme-color"]');
  if (t === 'aa') {
    document.documentElement.removeAttribute('data-theme');
    if (_meta) _meta.setAttribute('content', '#FFF8E7');
  } else {
    document.documentElement.setAttribute('data-theme', t);
    if (_meta) _meta.setAttribute('content',
      t === 'dark' ? '#221D20' : '#F7F3EA');
  }
  /* R2349j（R70-P1-23）：原生控件（select 下拉/日期框/滚动条）随主题——
   * meta color-scheme 写死 light 时深色下控件仍按浅色画。CSS 侧也有
   * html[data-theme="dark"]{color-scheme:dark}，meta 双保险。 */
  var _cs = document.querySelector('meta[name="color-scheme"]');
  if (_cs) _cs.setAttribute('content', t === 'dark' ? 'dark' : 'light');
  try {
    localStorage.setItem(THEME_KEY, t);
  } catch (e) { /* 存不了就只在本次会话生效 */ }
}

/** R206b（US4）：共情模板族——确定性选择，同输入同输出。 */
/* R233j（R46-P1）：四个主题各升 3 句池——高频首屏句不再撞。 */
var WARM_EMPATHY = {
  "感情": ["感情的事最怕自己闷着，我们一起看看盘里怎么说。",
           "心动或心堵，盘里都有线索——慢慢看，不急。",
           "感情这条线别自己扛，先听听盘面想说什么。"],
  "事业": ["工作上的事悬着心吧？先看看盘里的信号，再说下一步。",
           "卡住的活儿先放一放，看看盘面给的节奏。",
           "事业这事儿急不来，先瞅瞅盘里的风向。"],
  "学业": ["学习上有点累了吧？盘里有些线索给你参考。",
           "备考/赶工都辛苦了，看看今天的能量点在哪。",
           "学业不看出身看节奏——盘里的提示先听听。"],
  "健康": ["身体是自己的，先深呼吸，我们温和地看看盘里的提醒。",
           "身体发来的小信号别硬扛，先听听盘里怎么说。",
           "照顾好自己最重要——盘里的提醒只当参考，不舒服就看医生。"]
};
/* R216b 续3（UX 队列 U-012）：开场白从固定单句改 6 句轮换池——
 * 按「功能视图 + 日期」sha1 确定性抽取（同 copy_bank 纪律：同输入
 * 同输出，不违反确定性判据），连续用不同功能不再听到同一句。 */
var WARM_EMPATHY_POOL = [
  "来了就好。不管今天怎么样，先看看盘想对你说什么。",
  "别急，我帮你瞧瞧——先看看它想对你说什么。",
  "抽到什么说什么，我们慢慢看。",
  "你来了，它也在。一起看看今天的信号。",
  "这结果挺有意思的，听我慢慢说给你听。",
  "放心，不吓人——我把它们翻译成人话给你。"
];
var WARM_EMPATHY_DEFAULT = "来了就好。不管今天怎么样，先看看盘想对你说什么。";
/* R206b 补记：首版把提问挂在函数属性上被 probe_dollar_misuse 判
 * 「函数当对象访问属性」FAIL（本仓铁律），改模块级变量 WARM_LAST_QUESTION。 */
var WARM_LAST_QUESTION = "";
var LAST_BAZI_LUNAR = false;   /* R216b 续5（U-021）：本次提交是否农历输入 */
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
function renderWarm(warm, interp, evidence) {
  if (!warm) return renderInterpretation(interp, '📖 小满的解读');
  var html = '<div class="warm-wrap">';
  /* R206b（specs/009 US4 接住感）：L0 上一句共情——确定性模板族
   * （按提问主题选，无提问走通用款），同输入同输出不违反确定性判据。
   * 写死在前端而非 voice.py：voice 输出被 voice_baseline.json 逐字节
   * 钉住，前端追加层 additive 零基线风险。
   * R207b：聊天入口已由 paint() 全局统一注入（含塔罗/桃花等所有结果卡），
   * 此处不再单独渲染。 */
  html += '<div class="warm-empathy"><span>' +
    esc(warmEmpathy(WARM_LAST_QUESTION)) + '</span></div>';
  // L0 一句话：首屏第一眼就是它（判据 1/3）
  html += '<div class="warm-l0">' + esc(warm.one_liner || '') + '</div>';
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
    html += '<div class="energy-card">';
    html += '<div class="energy-head">本命 <strong>' + esc(ec.element || '') +
      '</strong>（' + esc(ec.element_warm || '') + '）· ' +
      esc(ec.element_note || '') + '</div>';
    html += '<div class="energy-grid">';
    if (ec.lucky_colors && ec.lucky_colors.length) {
      html += '<div class="energy-item"><span class="energy-k">幸运色</span>' +
        '<span class="energy-v">' + esc(ec.lucky_colors.join(' · ')) +
        '</span></div>';
    }
    if (ec.lucky_numbers && ec.lucky_numbers.length) {
      html += '<div class="energy-item"><span class="energy-k">幸运数字</span>' +
        '<span class="energy-v">' + esc(ec.lucky_numbers.join(' · ')) +
        '</span></div>';
    }
    if (ec.lucky_hours && ec.lucky_hours.length) {
      html += '<div class="energy-item"><span class="energy-k">幸运时段</span>' +
        '<span class="energy-v">' + esc(ec.lucky_hours.join('、')) +
        '</span></div>';
    }
    if (ec.keywords && ec.keywords.length) {
      html += '<div class="energy-item"><span class="energy-k">今日关键词</span>' +
        '<span class="energy-v">' + esc(ec.keywords.join(' / ')) +
        '</span></div>';
    }
    /* R233c（R40-W10）：helper_element（生我之行=补餽方向）此前零露出——
     * 能量卡只说「你是什么」，不说「多沾什么」。 */
    if (ec.helper_element) {
      html += '<div class="energy-item"><span class="energy-k">补一补</span>' +
        '<span class="energy-v">多沾点「' + esc(ec.helper_element) +
        '」系的能量</span></div>';
    }
    html += '</div>';
    // 幸运项的规则出处：判据 10 要求可追溯，不能只给结果
    if (ec.basis && ec.basis.length) {
      html += '<details class="warm-basis"><summary>这几项是怎么来的</summary><ul>';
      ec.basis.forEach(function (b) {
        html += '<li>' + esc(b) + '</li>';
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
  if (voiceMode() === 'warm' && (warm.details || []).length) {
    html += '<details class="warm-basis warm-pro-fold"><summary>📜 想看专业依据？（' +
      warm.details.length + ' 项，展开慢慢看）</summary>';
    (warm.details || []).forEach(function (d) {
      html += '<div class="interp-sec"><h4>' + esc(d.title || '') + '</h4><ul>';
      (d.lines || []).forEach(function (ln) {
        html += '<li>' + esc(annotatePowers(ln)) + '</li>';
      });
      html += '</ul>';
      if (d.basis && d.basis.length) {
        html += '<details class="warm-basis"><summary>推导依据（' +
          esc(d.basis.length) + ' 条）</summary><ul>';
        d.basis.forEach(function (b) {
          html += '<li>' + esc(b) + '</li>';
        });
        html += '</ul></details>';
      }
      html += '</div>';
    });
    html += '</details>';
  } else (warm.details || []).forEach(function (d) {
    html += '<div class="interp-sec"><h4>' + esc(d.title || '') + '</h4><ul>';
    (d.lines || []).forEach(function (ln) {
      html += '<li>' + esc(ln) + '</li>';
    });
    html += '</ul>';
    if (d.basis && d.basis.length) {
      html += '<details class="warm-basis"><summary>推导依据（' +
        esc(d.basis.length) + ' 条）</summary><ul>';
      d.basis.forEach(function (b) {
        html += '<li>' + esc(b) + '</li>';
      });
      html += '</ul></details>';
    }
    html += '</div>';
  });
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
    var t = '· ' + _pStr(b);
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
  ctx.fillText('@小满的解忧铺', 540, 1440 - 158);
  ctx.fillStyle = '#B7A98A';
  ctx.font = '400 24px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  ctx.fillText('· 知命知趣知自己 ·', 540, 1440 - 124);
  ctx.fillStyle = '#815934';
  ctx.font = '500 26px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  ctx.fillText('知命，是为了更好地活', 540, 1440 - 80);
  ctx.fillStyle = '#B7A98A';
  ctx.font = '400 34px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  ctx.fillText('知命 · 仅供娱乐', 540, 1440 - 38);

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
  ctx.fillStyle = _ink.title; ctx.font = '60px "ZCOOL KuaiLe","LXGW WenKai","Noto Serif TC",serif';
  ctx.fillText(_pStr(s.title) || '知命', 540, 128);
  if (s.subtitle) {
    ctx.fillStyle = _ink.sub; ctx.font = '400 32px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
    /* R2349（R65-P2-7）：底图星芒装饰会压副题行——给文字一圈
     * 奶白晕影（shadowBlur 沿字形外扩），字浮在星上仍可读。
     * R2349m：深底晕影换深色（白晕在夜紫上反而更糊）。 */
    ctx.save();
    ctx.shadowColor = _ink.halo;
    ctx.shadowBlur = _bgKey === 'lilac' ? 14 : 10;
    ctx.fillText(_gSlice(s.subtitle, 24), 540, 182);
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
  var _lineCap = { daily: 5, 'checkin-week': 7, taohua: 5, hehun: 6,
                   huangli: 6, birth: 5, bazi: 5 }[s.view] || 4;
  var lines = (s.lines || []).slice(0, _lineCap);
  /* R212：随大字行数下移卡片，避免重叠 */
  var cardY = (s.cards && s.cards.length ? 500 : 520) + Math.max(0, words.length - 2) * 60;
  if (lines.length) {
    /* R233t：底部水印 y≈1330，卡片区 y≈880——明细区硬顶 1260，
     * 行数多时收行高（最低 64px 可容 7 行）。 */
    var lh = Math.min(120, Math.max(64, (1260 - cardY) / lines.length));
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
        var _mEq = v.match(/等\s*\d+\s*项?$/);
        var _keep = _mEq ? _mEq[0] : '';
        _vv = _gSlice(v, Math.max(6, 21 - Array.from(_keep).length)) +
          '…' + _keep;
      }
      ctx.fillText(_vv, 150, y + 52);
    });
    ctx.textAlign = 'center';
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
  ctx.fillText('@小满的解忧铺', 540, 1320);
  /* R230r（R29-#11）：免责声明是合规件——花纹底图上浅棕字几乎不可读，
   * 给文字垫一条半透明米白衬底，任何背景下都可读。 */
  ctx.fillStyle = 'rgba(253,248,240,0.78)';
  _roundRectPath(ctx, 540 - 340, 1330, 680, 42, 21); ctx.fill();
  ctx.fillStyle = '#8A7A56'; ctx.font = '400 26px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  /* R229z续23（R11-#3）：分享图会离站传播，免责必须跟着走 */
  ctx.fillText('· 知命知趣知自己 · 仅供娱乐 ·', 540, 1356);
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
    ctx.fillStyle = 'rgba(253,248,240,0.78)';
    _roundRectPath(ctx, 65, 1366, 950, 68, 22); ctx.fill();
    ctx.fillStyle = '#815934';
    ctx.fillText(hook, 540, 1396);
  }
  /* R231d（R37-F1/F10）：回流 CTA——海报底部一行邀请语，收到图的人
   * 知道去哪儿玩同款（部署域名未定时只引品牌名，不画裸 URL）。 */
  /* R2341：hook 缺席时 CTA 也要有衬底（P1-1 同根因） */
  if (!hook) {
    ctx.fillStyle = 'rgba(253,248,240,0.78)';
    _roundRectPath(ctx, 65, 1366, 950, 68, 22); ctx.fill();
  }
  ctx.fillStyle = '#7A5C2E';
  ctx.font = '400 26px "LXGW WenKai","PingFang SC","Microsoft YaHei",sans-serif';
  ctx.fillText('测你的同款 → 搜「小满的解忧铺」', 540, 1422);
  /* R230x（P2-8）：右下角小满吉祥物贴纸——圆形裁切+奶油色衬底，
   * 与底图区隔成「贴纸」观感；图未加载则跳过不画。 */
  if (POSTER_MASCOT.complete && POSTER_MASCOT.naturalWidth) {
    try {
      /* R2341（R57-P1-3）：tarot 卡片区 (880-1300) 与右下贴纸
       * (1216-1340) 重叠压第三张牌——有卡片时挪右上角。 */
      var _mx = 974, _my = cards.length ? 76 : 1278;
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
    if (zhi) return '桃花信号' +
      ({strong: '最近正旺', mid: '在慢慢升温', weak: '还在酝酿'}[stg] || '待时而动') +
      '，留意「' + zhi + '」这个方向';
  }
  /* hehun: 用双方日主五行（R230r：畸形字段先过 _pStr，不画 [object Object]） */
  var _ha = _pStr(j && j.day_wx_a), _hb = _pStr(j && j.day_wx_b);
  if (view === 'hehun' && _ha && _hb) {
    return _ha + ' 遇 ' + _hb + ' · ' +
      (j.day_wx_sheng ? '相生' : (j.day_wx_same ? '同气' : '互补'));
  }
  /* 默认文案版（R218a-11 原版）；
   * R233t（R51-P2-17）：5 个 view 共用同一句万能胶水——每 view 一句
   * 贴语境的。 */
  var hooks = {
    'liuyao': '卦不骗人，帮你读',
    'daily':  '今日运势 · 听小满慢慢说',
    'tarot':  '牌已经替你说了',
    'xingzuo': '星星今天这么安排',
    'checkin': '新的一天，小满还在等你',
    'checkin-week': '一周七天，天天有签',
    'huangli': '老黄历今天这么说',
    'birth':  '这张小卡是你的底色'
  };
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
    var _defSub = todayIso().slice(5).replace('-', '月') + '日 · ' +
      _weekdayCn(todayIso());
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
      var _ds = { title: '今日运势', subtitle: _dsub,
        /* R212：原 slice(0,18) 会把 summary 拦腰截断（「…宜稳不」）——
         * 改取第一个分号前的完整短句。 */
        big: (j && j.summary)
          ? (String(j.summary).split(/[；;]/)[0] || '今日份小确幸')
          : '今日份小确幸',
        /* R229z续23（R11-#8）：海报与卡面同口径——凶→缓 */
        lines: [{ k: '运势等级', v: _pStr((j && j.level) === '凶' ? '缓' : (j && j.level)) || '—' },
                /* R233t（R51-P2-14）：地支原文「丑/未」上天书——转生肖。 */
                { k: '天乙贵人', v: _pStr(j && j.noble) ?
                  _zhiToAnimal(j.noble) : '—' },
                { k: '宜', v: _pStr(j && j.do) || '—' },
                { k: '忌', v: _pStr(j && j.dont) || '—' }],
        cards: [], view: view };
      _ds.lines.unshift({ k: '签诗', v: _dpoem });
      return _ds;
    }
    case 'tarot': {
      var draws = _pArr(j && j.draws);
      /* R233t（R51-P1-7）：卡图不再按 DOM 顺序抓——复看/重渲后 DOM
       * 序与 draws 可能错位；改用 draws[].img/src 数据键（若有）。 */
      var imgs = document.querySelectorAll('.tarot-card-front img');
      var s = base('塔罗指引', _pStr(j && j.question) ? '问：' + _gSlice(_pStr(j.question), 18) : _pStr(j && j.question));
      /* R219b（P1-4）：海报兜底句去掉「牌面是象征，不是结论」免责套话 */
      s.big = l0 || '今天这几张牌，值得你看一眼';
      s.cards = draws.slice(0, 3).map(function (d, i) {
        var el = imgs[i] && imgs[i].complete && imgs[i].naturalWidth > 0 ? imgs[i] : null;
        return { name: _pStr(d && d.name), sub: (d && d.upright) ? '正位' : '逆位', img: el };
      });
      return s;
    }
    /* R230d（R16-P2-2）：星座日运分享图——值宫 + 三维度摘要。 */
    case 'xingzuo': {
      /* R233t（R51-P1-6）：大字只印俩字星座名太孤——判词当大字，
       * 星座名挪副标。 */
      var _xzTd0 = _pArr(j && j.signs).filter(function (s) { return s && s.is_today; })[0];
      var sxz = base('星座日运',
        (_pStr(j && j.today_sign) || '今日') + '座 · ' + _cnDateSub(j && j.date));
      var _xzTd = _xzTd0;
      sxz.big = _clauseCut(_pStr((j && j.today_note) || (_xzTd0 && _xzTd0.note) || l0) || '今日当班', 22);
      var _xzl = [];
      if (_xzTd && _xzTd.love) _xzl.push({ k: '爱情', v: _gSlice(_xzTd.love, 24) });
      if (_xzTd && _xzTd.career) _xzl.push({ k: '事业', v: _gSlice(_xzTd.career, 24) });
      if (_xzTd && _xzTd.wealth) _xzl.push({ k: '财运', v: _gSlice(_xzTd.wealth, 24) });
      sxz.lines = _xzl.slice(0, 3);
      return sxz;
    }
    case 'liuyao': {
      var sly = base('六爻占卜', '');
      /* R233t（R51-P2-13）：4 行全叫「依据」分不清——位置化标签。 */
      var _lyLbl = ['卦象', '提示', '走势', '备注'];
      /* R2349m（R75-P2-1）：明细行与 hook 大字逐字重复时剔掉——不当复读机 */
      sly.lines = _pArr(w.details && w.details.basis)
        .filter(function (b) { return _pStr(b) !== l0; }).slice(0, 4)
        .map(function (b, i) { return { k: _lyLbl[i] || '看点', v: _pStr(b) }; });
      /* R2341（R57-P2-2）：basis 空时退化行复读大字——改画卦名/
       * 动爻这些已有字段，明细区不当复读机。 */
      if (!sly.lines.length) {
        var _lg = _pStr((j && (j.gua || j.gua_name || j.hexagram)));
        var _lm = _pStr((j && (j.moving || j.dong_yao)));
        if (_lg || _lm) sly.lines = [
          { k: '起到的卦', v: _lg || '—' },
          { k: '动爻', v: _lm || '—' }];
        else sly.lines = [{ k: '结论', v: _clauseCut(l0, 18) }];
      }
      return sly;
    }
    case 'qiming':
      /* R2349m（R75-P2-6）：副题补日期——其余视图副题都带时效。 */
      /* R2349m（R75-P2-7）：海报补五行行——「五行起名」主题缺席；
       * 真实缺行/偏弱兜底分开说（与后端口径一致不谎报）。 */
      var _qfe = (j && j.five_elements) || {};
      var _qmiss = _pArr(_qfe.missing), _qweak = _pArr(_qfe.weak);
      var _qfeLine = _qmiss.length ? ('缺 ' + _qmiss.join('、') + ' · 专补它')
        : (_qweak.length ? ('五行俱全 · 偏弱补 ' + _qweak.join('、'))
           : '五行俱全');
      return { title: '五行起名',
        subtitle: '按五行补缺 · ' + _cnDateSub(todayIso()),
        big: _gSlice((_pArr(j && j.full_names)[0] || {}).full_name || l0, 12),
        lines: [{ k: '五行', v: _qfeLine }].concat(
          _pArr(j && j.full_names).slice(0, 3).map(function (n, i) {
            return { k: '推荐 ' + (i + 1), v: _pStr(n && n.full_name) }; })),
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
      var _bir = base('我的本命盘', _cnDateSub(todayIso()));
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
      if (_bfx) _bir.lines.push({ k: '五行偏旺', v: _gSlice(_bfx, 20) });
      if (_bec.element) _bir.lines.push({ k: '本命', v: _pStr(_bec.element) });
      if (!_bir.lines.length) _bir.lines = [{ k: '结论', v: '知己知命' }];
      return _bir;
    }
    case 'checkin': {
      /* R233n（R47-Top5-2）：首日也走这张海报——连签 ≥3 标题挂天数，
       * 否则挂「今天的签」，big 主打抽中的签面（晒点更足）。 */
      var _stk = Number(j && j.streak) || 0;
      /* R233q（R47-P2 续）：满月款标记——连签 ≥30 的海报挂限定标，
       * 给「晒出去」再加一层稀缺感。 */
      var _ck = base(_stk >= 30 ?
          '🌕 满月款 · 连续 ' + _pStr(j && j.streak) + ' 天来小满打卡' :
          _stk >= 3 ?
          '我连续 ' + _pStr(j && j.streak) + ' 天来小满打卡' : '今天的小满签',
        _weekdayCn('') + ' · ' + todayIso());
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
        (_wd[0] ? String(_wd[0].date).slice(5) : '') + ' ~ ' +
        (_wd[6] ? String(_wd[6].date).slice(5) : ''));
      _wk.big = '本周打卡 ' + _hit + '/7 天' +
        (j && j.streak >= 3 ? ' · 连签 ' + j.streak + ' 天' : '');
      _wk.lines = _wd.map(function (d) {
        var dd = String(d.date || '');
        return { k: _weekdayCn(dd) + ' ' + dd.slice(5).replace('-', '/'),
                 v: d.opt || '· 歇了一天' };
      });
      return _wk;
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
      st.big = l0 || '桃花正在加载';
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
      /* R231d（R37-F17）：缘分指数——确定性字段凑一个一眼数字
       * （小红书 CP 晒图最吃量化分）：六合+15 / 天干五合+10 /
       * 日主相生+10 / 同五行比和+6 / 桃花同支+5，六冲-15，夹 40–98。 */
      /* R233t（R51-P0-1）：clash/combine/gan_he 是布尔——此前过
       * _pStr 变 'false' 字符串（非空恒真）：海报画上「六冲 false」，
       * 且缘分指数任何配对恒 85。一律用原始布尔 + 中文映射上图。 */
      var _sc = 60;
      if (j && j.combine === true) _sc += 15;
      if (j && j.gan_he === true) _sc += 10;
      if (j && j.day_wx_sheng) _sc += 10;
      else if (j && j.day_wx_same) _sc += 6;
      if (j && j.peach_same === true) _sc += 5;
      if (j && j.clash === true) _sc -= 15;
      _sc = Math.max(40, Math.min(98, _sc));
      sh.lines.push({ k: '缘分指数', v: String(_sc) });
      var _wa = _pStr(j && j.day_wx_a), _wb = _pStr(j && j.day_wx_b);
      if (_wa && _wb) {
        var sheng = j.day_wx_sheng ? ' · 相生' : (j.day_wx_same ? ' · 比和' : '');
        sh.lines.push({ k: '日主五行', v: _wa + ' ↔ ' + _wb + sheng });
      }
      /* R233t（R51-P2-14）：「六冲/六合」行话不上图——人话映射。 */
      if (j && j.clash === true) sh.lines.push({ k: '需要磨合', v: '冲合有磕绊' });
      if (j && j.combine === true) sh.lines.push({ k: '天作之合', v: '日主相合' });
      if (j && typeof j.peach_same === 'boolean') sh.lines.push({ k: '桃花支', v: j.peach_same ? '同支共振' : '各有桃花' });
      if (j && j.gan_he === true) sh.lines.push({ k: '天干五合', v: '有' });
      if (!sh.lines.length) sh.lines = [{ k: '结论', v: _gSlice(l0, 15) || '天作之合' }];
      return sh;
    }
    /* R229z续25：黄历分享图——唯一没海报的核心视图补齐（宜/忌/建除/值宿/
     * 冲煞/相冲提示全取自确定性字段，离站海报同样带仅供娱乐页脚）。 */
    case 'huangli': {
      var jh = j || {};
      var lun = jh.lunar || {};
      var shl = base('今日宜忌',
        _cnDateSub(jh.date) +
        ((lun.month_cn || lun.day_cn) ? ' · 农历' + (lun.month_cn || '') + (lun.day_cn || '') : ''));
      var yiL = _pArr(jh.yi), jiL = _pArr(jh.ji);
      /* R230y（R36-P2-4）：海报上印白话——「宜 上任·谒贵」发出去没人懂，
       * 过映射表转人话，未命中词保留原味。 */
      var _yiP = yiL.map(function (x) { return _HL_YI_MAP[x] || _pStr(x); });
      var _jiP = jiL.map(function (x) { return _HL_JI_MAP[x] || _pStr(x); });
      /* R233t（R51-P1-8）：大字只放最有梗的一条宜——原三词拼接
       * wrapText 切出孤行「 · 许愿」悬在半空。 */
      shl.big = _yiP.length ? ('今日宜' + _yiP[0]) : '今日平稳';
      shl.lines = [];
      /* R233t（R51-P1-8）：「前 2 条全量 + 等 N 件」不再拦腰截词。 */
      var _yiT = _yiP.slice(0, 2).join(' · ') +
        (_yiP.length > 2 ? '　等 ' + _yiP.length + ' 件' : '');
      var _jiT = _jiP.slice(0, 2).join(' · ') +
        (_jiP.length > 2 ? '　等 ' + _jiP.length + ' 件' : '');
      if (_yiP.length) shl.lines.push({ k: '宜', v: _yiT });
      if (_jiP.length) shl.lines.push({ k: '忌', v: _jiT });
      /* R2341（R57-P2-5）：单字行合并「建除·X / 值宿·Y」省一行 */
      if (jh.jianchu || jh.xiu) shl.lines.push({ k: '神煞',
        v: (jh.jianchu ? '建除·' + _pStr(jh.jianchu) : '') +
           ((jh.jianchu && jh.xiu) ? '　' : '') +
           (jh.xiu ? '值宿·' + _pStr(jh.xiu) : '') });
      if (jh.chongsha) {
        var _cs = (typeof jh.chongsha === 'string') ? jh.chongsha :
          (typeof jh.chongsha === 'object' && jh.chongsha ?
            ('冲' + _pStr(jh.chongsha.chong_animal || jh.chongsha.chong) +
             (jh.chongsha.sha_fang ? '煞' + _pStr(jh.chongsha.sha_fang) : '')) : '');
        if (_cs.replace(/[冲煞]/g, '')) shl.lines.push({ k: '冲煞', v: _cs });
      }
      var _cf = _pArr(jh.conflict);
      if (_cf.length) {
        shl.lines.push({ k: '注意', v: _cf.slice(0, 3).map(_pStr).join('·') + ' 宜忌两边都见' });
      }
      return shl;
    }
    default:
      return null;
  }
}

function warmPoster() {
  try {
    var cv = _paintPoster({}, POSTER_FULL_W, POSTER_FULL_H);
    if (cv) cv.width = cv.height = 1;   /* 解除大位图引用 */
  } catch (e) { /* 预热失败不影响任何主流程 */ }
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
  return t + '知命，是为了更好地活@小满的解忧铺·知命知趣知自己' +
    '仅供娱乐测你的同款→搜「」' ;
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
    } else if (_isTouch) {
      /* 触屏端不触发 a[download]——弹层长按保存即可 */
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
  showPosterModal(r.canvas, view);
}

/* R218a-巡2（N-02）：海报浮层——背景遮罩 + 中央海报图 + 关闭按钮 +
 * 长按保存提示。点遮罩/ESC 关闭，多次调用只重建内容。 */
function showPosterModal(canvas, view) {
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
        ((typeof navigator !== 'undefined' &&
          (navigator.maxTouchPoints > 0 || 'ontouchstart' in window))
          ? '长按图片可保存到相册 · 发给闺蜜一起测～'
          : '已自动下载到下载文件夹 · 也可右键另存 · 发给闺蜜一起测～') +
        '</div>' +
      /* R231d（R37-F2）：分享动作行——复制链接（任何环境可用）+ 系统
       * 分享面板（支持 Web Share 的移动浏览器才出现）。 */
      '<div class="poster-modal-actions">' +
        '<button type="button" class="poster-act" id="posterCopyLink">🔗 复制链接</button>' +
        ((typeof navigator !== 'undefined' && navigator.share)
          ? '<button type="button" class="poster-act" id="posterSysShare">📤 分享给朋友</button>' : '') +
      '</div>' +
    '</div>';
  document.body.appendChild(backdrop);
  /* 复制本视图深链——朋友打开直达同一页 */
  var _pcl = backdrop.querySelector('#posterCopyLink');
  if (_pcl) _pcl.addEventListener('click', function () {
    /* R231d（R39-P2-1）：带 from=share 便于落地页换承接文案 */
    var url = location.origin + '/?view=' + encodeURIComponent(view || 'home') + '&from=share';
    var ok = function () { showToast(_dayPick(['链接已复制，发给 TA 吧','复制好啦，发给 TA 看看','已复制——等 TA 打开'], 'copy'), 'ok'); };
    var bad = function () { showToast('复制没成功，手动复制地址栏里的链接吧', 'warn'); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(ok, bad);
    } else {
      try {
        var _ta = document.createElement('textarea');
        _ta.value = url; _ta.style.position = 'fixed'; _ta.style.opacity = '0';
        document.body.appendChild(_ta); _ta.select();
        document.execCommand('copy') ? ok() : bad();
        _ta.remove();
      } catch (e) { bad(); }
    }
  });
  /* 系统分享面板——优先分享图文件，不支持文件则退文本+链接 */
  var _pss = backdrop.querySelector('#posterSysShare');
  if (_pss) _pss.addEventListener('click', function () {
    var url = location.origin + '/?view=' + encodeURIComponent(view || 'home') + '&from=share';
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
  m.classList.remove('open');
  setTimeout(function () { if (m.parentNode) m.parentNode.removeChild(m); }, 200);
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
      if (ctx.measureText(cur + ch).width > maxWidth) { lines.push(cur); cur = ch; }
      else cur += ch;
    });
    if (cur) lines.push(cur);
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
  var cut = _gSlice(t, n);
  var seps = ['。','！','？','；','，','——'];
  var pos = -1;
  seps.forEach(function (sep) {
    var p = cut.lastIndexOf(sep);
    if (p >= 0) pos = Math.max(pos, p + sep.length);
  });
  if (pos >= 6) return _gSlice(cut, pos);
  return cut;
}
function _pArr(v) { return Array.isArray(v) ? v : []; }
function _pStr(v) {
  if (v == null || typeof v === 'object') return '';
  return String(v);
}
function _gSlice(v, n) { return Array.from(_pStr(v)).slice(0, n).join(''); }

/* 上一次响应缓存：切换口吻时就地重画，不重发请求。
 * 键 = 结果容器 id，值 = {json, proTitle, render}。render 是"用这份 json
 * 重画整个结果区"的闭包——切换只影响解读段，但结果区是一次性拼出来的
 * 字符串，所以整块重画最简单也最不容易漏。 */
var LAST_RESPONSE = {};

/** 按当前模式渲染解读区。warm 数据缺失时自动回落专业分支。
 *  evidenceKeys：本响应里存放**全文**引文的键名（各功能不同：排盘是
 *  evidence，六爻是 ben_jing/bian_jing）。warm 分支用它们喂 renderCiteTree，
 *  以满足 005 判据 8（展开原文与 API 逐字节一致）。 */
function renderVoice(j, proTitle, evidenceKeys) {
  var html = renderModeSwitch();
  if (voiceMode() === 'warm' && j && j.warm) {
    var ev = [];
    (evidenceKeys || ['evidence']).forEach(function (k) {
      if (j[k] && j[k].length) ev = ev.concat(j[k]);
    });
    html += renderWarm(j.warm, j.interpretation, ev);
  } else {
    /* R216b 续（UX 队列 U-015）：voiceMode 是 localStorage 持久态，普通
     * 用户点过一次「专业版」后所有功能永久变成开发者视图且找不到退路。
     * 在 pro 结果卡头部加一条常显的返回提示条（点击即回温柔版并重画）。
     * 只加提示、不改任何 pro 渲染内容——判据 9 的逐字节口径零风险。 */
    html += '<div class="pro-notice">📐 当前是专业视角（坐标与推导链原样展示）。' +
      '<button type="button" class="pro-back-btn" data-voice="warm">🌸 回到温柔版</button></div>';
    html += renderInterpretation(j ? j.interpretation : null, proTitle);
  }
  html += renderAiPolish(j);
  return html;
}

/** 重画所有已渲染过的结果区（切换口吻时调用）。 */
function rerenderVoice() {
  Object.keys(LAST_RESPONSE).forEach(function (containerId) {
    var entry = LAST_RESPONSE[containerId];
    if (entry && typeof entry.render === 'function') {
      paint(containerId, entry.render(entry.json));
      /* R195b（用户报告 bug）：重画会重建 DOM，.flipped 全部丢失——
       * 塔罗牌面退回背面「知」且不再恢复。重画发生在用户**已经看过**
       * 牌面之后（切换口吻），所以恢复语义是"全部翻开"，不重播动画。
       * （变量名避开函数名——probe_dollar 静态闸门禁「函数名.属性」。） */
      var host = document.getElementById(containerId);
      if (host) host.querySelectorAll('.tarot-card-inner').forEach(function (c) {
        c.classList.add('flipped');
      });
    }
  });
}

/** 记住这次响应与重画方式，供切换口吻时就地重画。 */
function rememberVoice(containerId, json, renderFn) {
  LAST_RESPONSE[containerId] = { json: json, render: renderFn };
}

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
    var _BASIS_CN = {
      'paipan.render': '命盘四柱', 'paipan.nayin': '纳音',
      'calc.five_elements': '五行分布', 'calc.ten_gods': '十神',
      'calc.relations': '地支关系', 'calc.day_luck': '流日',
      'calc.summary': '总评', 'warm': '温柔版', 'cross_ref': '交叉印证'
    };
    var _basisCn = interp.basis.map(function (b) {
      var _hit = Object.keys(_BASIS_CN).filter(function (k) {
        return b.indexOf(k) === 0; })[0];
      return _hit ? _BASIS_CN[_hit] : String(b).split('.').pop();
    });
    html += '<div class="interp-basis" title="' +
      esc(interp.basis.join(' / ')) + '">依据：' +
      esc(_basisCn.join(' / ')) + '</div>';
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
    const c = colorAt(i);
    i += 1;
    html += '<div class="calc-block" style="border-left:3px solid ' + c + ';">' +
      '<h3 style="color:' + c + ';">' + esc(k) + '</h3>';
    if (Array.isArray(v)) {
      html += '<ul>';
      v.forEach(function (item) {
        if (item && typeof item === 'object') {
          const parts = [];
          Object.keys(item).forEach(function (ik) {
            if (ik === 'basis') return;
            parts.push('<strong>' + esc(ik) + '</strong>：' + esc(fmtScalar(item[ik])));
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
        html += '<li><strong>' + esc(ik) + '</strong>：' + esc(fmtScalar(v[ik])) + '</li>';
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
function fmtScalar(v) {
  if (v == null) return '—';
  if (Array.isArray(v)) {
    return v.map(function (x) {
      return (x && typeof x === 'object')
        ? Object.keys(x).map(function (k) { return k + ':' + fmtScalar(x[k]); }).join(' ')
        : fmtScalar(x);
    }).join('、') || '—';
  }
  if (typeof v === 'object') {
    return Object.keys(v).map(function (k) {
      return k + ' ' + fmtScalar(v[k]);
    }).join('、') || '—';
  }
  if (typeof v === 'boolean') return v ? '是' : '否';
  return String(v);
}

/* ── 每日运势 ──────────────────────────────────────────────── */

async function loadDaily() {
  try {
    /* R228k：/api/xingzuo 缺省即算今天——不再等 daily 回包再串行发，
     * 首屏 23ms 变并行。silent+catch=null 保持原有的失败静默降级。 */
    const _today = todayIso();
    /* R2349l（R73-P1-3）：档案里有生日 → 带 bday 让日卡出
     * 「你的日主×今天」个性行；没有就省略（nil 键不进缓存）。 */
    var _me0 = _meGet('me');
    var _bday0 = (_me0 && _me0.y && _me0.m && _me0.d)
      ? ('&bday=' + _me0.y + '-' + String(_me0.m).padStart(2, '0') +
         '-' + String(_me0.d).padStart(2, '0')) : '';
    const [j, x, tm] = await Promise.all([
      /* R230h（R20-F6）：显式带浏览器日——跨零点时服务器「今天」
       * 与用户本地「今天」可能差一天。 */
      api('/api/daily?date=' + _today + _bday0),
      api('/api/xingzuo?date=' + _today, { silent: true }).catch(function () { return null; }),
      /* R39-P0-1：明天预告——每日回访的最短钩子，走 daily_cache 幂等
       * 成本≈0。 */
      api('/api/daily?date=' + _isoShift(_today, 1), { silent: true })
        .catch(function () { return null; })
    ]);
    window.__lastDaily = j;   /* R198b（US5）：shareDaily 用 */
    const dateEl = el('dailyDate');
    /* R233q：日期补星期——「2026-09-20 周日」比裸日期更像签 */
    if (dateEl) dateEl.textContent =
      (j.date || '今天') + (j.date ? ' ' + _weekdayCn(j.date) : '');
    const level = j.level || '平';
    const levelEl = el('dailyLevel');
    if (levelEl) {
      /* R216b 续3（UX 队列 U-009）：凶日不吓人——标签柔化（「稍缓」），
       * 紧跟一句安抚话术；吉/平保持原样。 */
      levelEl.textContent = (level === '凶') ? '缓' : level;
      /* R230y（R36-P2-7）：小吉档 → 四星蜜桃色盘 */
      levelEl.className = 'daily-level ' +
        (level === '吉' ? 'good' : level === '小吉' ? 'sml' :
         level === '凶' ? 'bad soft' : 'mid');
      /* R233g（R44-P2）：tooltip 把吓人的「凶」塞回悬停——改为白话 */
      levelEl.title = level === '凶' ? '今天能量偏低，宜稳宜慢' : '';
    }
    const starsEl = el('dailyStars');
    if (starsEl) {
      starsEl.innerHTML = renderStars(level);
      /* R229z续23（R10-#16）：读屏播报「吉·五星」而非逐个星符 */
      starsEl.setAttribute('aria-label', '今日运势：' +
        (level === '吉' ? '吉，五星' : level === '小吉' ? '小吉，四星' :
         level === '凶' ? '缓，一星' : '平，三星'));
      /* U-009 附带：星级加图例，一星不再语义不明。 */
      var legend = document.getElementById('dailyStarsLegend');
      if (!legend && starsEl.parentElement) {
        legend = document.createElement('span');
        legend.id = 'dailyStarsLegend';
        legend.className = 'stars-legend';
        starsEl.parentElement.appendChild(legend);
      }
      if (legend) legend.textContent =
        level === '吉' ? '（五星 · 顺）' :
        level === '小吉' ? '（四星 · 小顺）' :
        level === '凶' ? '（今日能量偏低 · 宜稳宜慢）' : '（三星 · 平稳）';
    }
    setText('dailySummary', j.summary || '');
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
      sooth.textContent = (level === '凶') ?
        /* R2349g（R68-P1-1）：凶日安抚句 3→8——凶是 4 档里最能被记住的
         * 日子，原池 60 天单句能出现 8 次。 */
        _dayPick(['「缓」不是坏日子——只是提醒你今天别硬冲，稳稳的也很好。',
                  '「缓」是让你慢下来，不是让你怕——慢一点反而顺。',
                  '今天能量偏低就把事放小——泡个澡早点睡也算赢。',
                  '低气压天适合摆烂式养生——允许自己今天只做 60 分。',
                  '今天不拼运气拼休息——把节奏放缓就是最优解。',
                  '阴天就宅——点个外卖刷刷剧，明天再战。',
                  '今天的你不需要很厉害，安稳度过就是满分。',
                  '能量低的日子适合充电——早睡一小时比啥都管用。'], 'xiong') : '' ;
      sooth.hidden = (level !== '凶');
    }
    /* R2341（R57-P2-6）：贵人地支转生肖——与海报同口径 */
    setText('dailyNoble', j.noble ? _zhiToAnimal(j.noble) : '—');
    /* R2349g（R68-P0-2）：合拍生肖第二层 */
    setText('dailyPal', j.noble_liuhe ? _zhiToAnimal(j.noble_liuhe) : '—');
    setText('dailyDo', j.do || '—');
    setText('dailyDont', j.dont || '—');
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
          }
        });
      }
    }
    /* R2349k（R72-A2）：节日行——首页日卡也要说「今天是中秋」。 */
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
        _fv.innerHTML = '🎉 今天是<strong>' + esc(j.festival.join('、')) + '</strong>';
        _fv.hidden = false;
      } else { _fv.hidden = true; _fv.innerHTML = ''; }
    }
    /* R2349l（R73-P1-3/P1-4/P2-9）：个性行 + 开运三件套 + 水逆态——
     * 三条 meta 行同一个惰性挂载点。 */
    var _metaRow = document.querySelector('#dailyCard .daily-meta');
    function _dailyMetaItem(id, html) {
      var n = el(id);
      if (!n) {
        n = document.createElement('div');
        n.id = id; n.className = 'daily-meta-item';
        if (_metaRow) _metaRow.appendChild(n);
      }
      if (html) { n.innerHTML = html; n.hidden = false; }  // esc-reviewed（各调用点 esc() 字段，文本键原样）
      else { n.hidden = true; n.innerHTML = ''; }
    }
    if (j.personal && j.personal.line) {
      _dailyMetaItem('dailyPersonal',
        '🪞 ' + esc(j.personal.line) +
        (j.personal.year_line
          ? '<br><span style="font-size:12px;opacity:.85;">' +
            '📅 ' + esc(j.personal.year_line) + '</span>' : ''));
    } else {
      /* 没档案时轻引导——「存个生日这条就是你的了」（R73-P1-3） */
      _dailyMetaItem('dailyPersonal',
        '<button type="button" class="daily-personal-cta" id="dailyPersonalCta">' +
        '🪞 存个生日，这条运势就是你的了</button>');
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
        '🎨 开运色 <strong>' + esc(j.lucky.color || '—') + '</strong>' +
        ' · 幸运数 <strong>' + esc(j.lucky.num || '—') + '</strong>' +
        (j.lucky.color_word
          ? '<span class="daily-lucky-word">' + esc(j.lucky.color_word) + '</span>' : ''));
    } else { _dailyMetaItem('dailyLucky', ''); }
    if (j.mercury && j.mercury.on) {
      _dailyMetaItem('dailyMercury',
        '💫 水逆中 · 第' + j.mercury.day_no + '天（到 ' +
        esc(String(j.mercury.until || '').slice(5).replace('-', '月')) + '日）——心放宽，事多检查');
    } else { _dailyMetaItem('dailyMercury', ''); }
    /* R2349l（R73-P1-2）：每日一牌——日期哈希做 seed 的确定性单抽
     * （同一天同一张），点击展开牌意；失败静默不打扰日卡。 */
    (function () {
      var _seed = 0, _src = 'tarot|' + _today;
      for (var i = 0; i < _src.length; i++) {
        _seed = (_seed * 31 + _src.charCodeAt(i)) >>> 0;
      }
      /* 走 /api/tarot/draw（单抽、不写台账）——/api/tarot 每次调用都
       * save_async，日卡自动抽会把排盘历史灌满日更牌。 */
      postJSON('/api/tarot/draw', { seed: _seed, n: 1 })
        .then(function (tj) {
          var d = (tj && tj.card) || null;
          if (!d || !d.name) return;
          _dailyMetaItem('dailyTarot',
            '🃏 今日牌：<strong>' + esc(d.name) + '</strong>' +
            ' · ' + (d.upright ? '正位' : '逆位') +
            '<button type="button" class="sign-peek" id="tarotPeekBtn">牌意</button>');
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
            _tc.innerHTML = '<strong>' + esc(d.name) +
              ' · ' + (d.upright ? '正位' : '逆位') + '</strong>' +
              '<span>' + esc(d.upright ? (d.upright_kw || '') :
                                       (d.reversed_kw || '')) +
              (d.meaning ? ' —— ' + esc(d.meaning) : '') + '</span>';
          }
          var _tb = el('tarotPeekBtn');
          if (_tb && !_tb.dataset.bound) {
            _tb.dataset.bound = '1';
            _tb.addEventListener('click', function () {
              var c2 = el('tarotCard');
              if (c2) {
                c2.hidden = !c2.hidden;
                _tb.textContent = c2.hidden ? '牌意' : '收起';
              }
            });
          }
        })
        .catch(function () { _dailyMetaItem('dailyTarot', ''); });
    })();
    /* R2349l（R73-P1-8）：新月许愿/满月复盘——农历初一十五窗口的
     * 仪式行（后端 daily 的 moon 派生键）。 */
    if (j.moon && j.moon.label) {
      _dailyMetaItem('dailyMoon',
        (j.moon.phase === '满月' ? '🌕 ' : '🌑 ') +
        '<strong>' + esc(j.moon.label) + '</strong> —— ' +
        esc(j.moon.line || ''));
    } else { _dailyMetaItem('dailyMoon', ''); }
    /* R2349l（R73-P1-15）：周日给「本周辛苦了→下周哪天顺」，
     * 周一给「新的一周看宜忌」——跳黄历页，周条本就在那。 */
    (function () {
      var _wd = new Date().getDay();
      if (_wd === 0) {
        _dailyMetaItem('dailyWeekHint',
          '🗓 这周辛苦了——<button type="button" ' +
          'class="sign-peek" id="dailyWeekGo">看看下周哪天顺</button>');
      } else if (_wd === 1) {
        _dailyMetaItem('dailyWeekHint',
          '🗓 新的一周——<button type="button" ' +
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
          var bd = new Date(yy, c.m - 1, c.d);
          if (bd < _t0) bd = new Date(yy + 1, c.m - 1, c.d);
          var dd = Math.round((bd - _t0) / 86400000);
          if (dd > 0 && dd <= 30 && (!_best || dd < _best.dd)) {
            _best = { dd: dd, n: c.n };
          }
        });
        if (_best) {
          _dailyMetaItem('dailyBdayCtd',
            '🎁 ' + esc(_best.n) + '的生日还有 <strong>' +
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
        (j.term.tip ? '——' + esc(j.term.tip) : '');  // esc-reviewed
      _tbar.hidden = false;
    } else if (_tbar) { _tbar.hidden = true; }
    renderCheckin(j.date);   // R214b：今日玄学搭子打卡互动
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
        _tmrEl.textContent = '🌙 明天「' +
          (tm.level === '凶' ? '缓' : (tm.level || '平')) + '」· 宜 ' +
          (tm.do || '平常心') + '——' +
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
      try { _hl0 = (JSON.parse(localStorage.getItem('hlask') || '[]') || [])[0]; }
      catch (e0) {}
      /* R2349k（R72-B4）：接续条比较/话术都锚「问的那天」（a），
       * 老足迹没 a 时回落 d。 */
      var _hlA = _hl0 && (_hl0.a || _hl0.d);
      if (_hl0 && _hl0.q && _hlA && _hlA < _today) {
        _recEl.innerHTML = '<button type="button" class="daily-recall-btn" ' +
          'data-hlask-q="' + esc(_hl0.q) + '">💬 ' + _hlAgoWord(_hlA) + '你问了「' +
          esc(_gSlice(_hl0.q, 14)) + '」——今天再看看？</button>';
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
  } catch (e) {
    /* R228c：失败态补全——dailyDate 别停在「加载中…」，分享钮也给提示
     * 而不是静默无操作。 */
    setText('dailyDate', '今天');
    setText('dailySummary', '运势计算暂时不可用：' + _humanizeErr(e.message));
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
    if (_bme && _bme.y &&
        Number(_bme.m) === _bdt.getMonth() + 1 &&
        Number(_bme.d) === _bdt.getDate()) {
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
        '今天你生日——全场最大，宜收下所有夸奖 ' +
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
    // R183b（同 R124a-01）：内部键名转储只在专业模式出现。
    // 本卡片没有自己的模式切换控件（它是首页运势的展开），跟随全局 voiceMode。
    if (voiceMode() === 'pro') {
      html += renderCalc(j.calc);
      html += renderInterpretation(j.interpretation, '📖 今日解读');
    } else {
      /* v4（用户裁决）：默认只给「一句话 + 前 3 条要点」的轻摘要，
       * 完整版（能量卡/专业依据/古籍原文）收进二级折叠，不再全量铺开。
       * 摘要只取后端既有字段原句，不自造事实；pro 模式保持全量直出。 */
      var _w = j.warm || {};
      var _pts = (Array.isArray(_w.reply) && _w.reply.length) ? _w.reply.slice(0, 3) : [];
      if (!_pts.length && (_w.details || []).length) {
        _w.details.slice(0, 3).forEach(function (d) {
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
      html += '<details class="daily-full pro-drawer"><summary>展开完整解读 ▾</summary>' +
        '<div class="daily-full-body">' + renderWarm(j.warm, j.interpretation) + '</div>' +
        '</details>';
    }
    html += '</div>';
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
    attachChatEntry(target);   /* R230k（R23-P2-1）：直写 innerHTML 不走 paint——手动挂 */
    pollAiPolish('dailyDetail', j.ai_task_id);   // R217a：完整解读也轮询 AI 润色
  } catch (e) {
    target.innerHTML = '<div class="no-evidence">解读失败：' + esc(_humanizeErr(e.message)) + '</div>';
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

/** 排盘结果区的 HTML 构建（抽成纯函数，切换口吻时可就地重画）。 */
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
  html += '<button class="ghost fav-btn" type="button" id="shareBazi" ' +
    'title="生成分享图">📸 分享图</button>';
  if (voiceMode() === 'pro') {
    /* R215b：专业模式保留原排盘标签（判据 9 口径不动）。 */
    html += '<div class="pill-row">';
    String(paipan.render || '').split(/\s+/).forEach(function (p, i) {
      if (p.length >= 2) {
        html += '<span class="pill" style="background:' + colorAt(i) + ';">' +
          esc(p) + '</span>';
      }
    });
    html += '</div>';
    if (paipan.nayin && paipan.nayin.length) {
      html += '<p class="nayin">纳音：' + esc(paipan.nayin.join(' · ')) + '</p>';
    }
  } else {
    /* R215b：温柔模式首屏去工具感——四柱/纳音收进折叠「看看你的生辰小卡」，
     * 首屏只有一句人话生日线。事实零改动，只是呈现位置后移。 */
    html += '<p class="bazi-birthday">' + esc(baziBirthdayLine(paipan)) + '</p>';
    /* R218a-03：人设卡——按日主五行分支从 copy_bank.gan_persona 选一套。
     * 视觉锚点：左条+人设短句+1-2 关键词气泡。让「我是什么命格」秒级可达。 */
    html += baziPersonaCard(j);
    if (LAST_BAZI_LUNAR) {
      /* R216b 续5（U-021）：农历输入时告知已换算，用户可核对。 */
      html += '<p class="nayin">🗓 你输入的是农历生日，四柱按公历换算得出' +
        '——遇到闰月也可以对照上面的日子核对。</p>';
    }
    html += '<details class="paipan-fold"><summary>看看你的生辰小卡</summary>' +
      '<div class="pill-row">';
    String(paipan.render || '').split(/\s+/).forEach(function (p, i) {
      if (p.length >= 2) {
        html += '<span class="pill" style="background:' + colorAt(i) + ';">' +
          esc(p) + '</span>';
      }
    });
    html += '</div>';
    if (paipan.nayin && paipan.nayin.length) {
      html += '<p class="nayin">纳音：' + esc(paipan.nayin.join(' · ')) + '</p>';
    }
    html += '</details>';
  }
  if (paipan.warn && paipan.warn.length) {
    html += '<p class="warn">' + esc(paipan.warn.join('；')) + '</p>';
  }
  // R183b（审查轨 R124a-01，003 判据 14）：renderCalc 是 calc 字典的**原样
  // 转储**，键名就是后端内部字段名（ten_gods / five_elements / day_luck …）。
  // 它此前在 renderVoice 之前**无条件**执行，于是温柔模式首屏也印满变量名
  // ——用户看到程序变量名和看到 [object Object] 一样廉价。
  //
  // 只在专业模式渲染它：
  //   * 专业模式需要它（原始坐标逐项可核验），且判据 9 要求这条路径逐字节
  //     不变，故一个字符都不改。
  //   * 温柔模式不需要它——warm.details 承载的是**同一批事实**的白话版
  //     （五行强弱/十神格局/地支关系/流日流时，含 分布：木1.1 这类数字），
  //     信息不丢，只是不再用内部键名做小标题。
  // R185b（005 判据 1/2/5）：**warm 与专业模式的版面顺序不同，这是有意的。**
  //
  // 专业模式（下面的 pro 分支）保持 R183b 的顺序一字不动：
  //   renderCalc → 古籍全文（renderHits）→ renderVoice
  // 判据 9 与 web/baselines/pro_render_baseline.json 的 h3 顺序数组
  // （ten_gods/five_elements/relations/day_luck/📜 古籍依据/📖 解读）钉死了它。
  //
  // warm 模式改为：renderVoice（大白话）→ 古籍三级折叠（在 renderWarm 内部）。
  // 原因是实测：古籍全文占结果区 92% 字数、单段最高 12,219px，把它排在
  // 大白话之前 = 用户要滚 71,094px 才看到那句 11 字的人话（005 §1）。
  // 古籍不再单独渲染于此——它由 renderWarm 经 renderCiteTree 渲染**一次**
  // （判据 5，清偿 R128a-01 的重复渲染）。
  if (voiceMode() === 'pro') {
    html += renderCalc(j.calc);
    if (j.evidence) {
      html += '<h3 style="margin-top:20px;color:var(--c-book);">📜 古籍依据</h3>';
      /* R228r：空数组此前整块不渲染——用户分不清「没检索」和「检索没中」；
       * 渲染空态文案说明。 */
      html += j.evidence.length
        ? renderHits(j.evidence, { empty: '这条没有古籍引文' })
        : '<p style="color:var(--secondary);font-size:13px;">这次没翻到能引用的古籍原文——不影响解读，往下看～</p>';
    }
  }
  // R000a-04：原读 j.llm_out（后端从来没这个键）→ 现读 interpretation。
  html += renderVoice(j, '📖 小满的解读', ['evidence']);
  html += tailHook('bazi');
  html += '</div>';
  return html;
}

var _submitBaziBusy = false;   /* R8 P2-2：form submit 不经 on()，自加在途锁 */
var _submitBaziLast = { key: '', ts: 0 };   /* R230q（R28-P3-14）同参防抖 */
async function submitBazi(event) {
  if (event) event.preventDefault();
  if (_submitBaziBusy) return;   // 连点/回车连击 → 只发一次，防并发覆盖
  /* R230t（R33-P1-2）：同参防抖判定提到 busy() 之前——原先 busy 先清屏
   * 再 paint 提示，把刚渲染的结果卡整段顶掉（「上面那张」已不存在）。
   * 现在命中防抖只弹 toast，结果卡原样保留。 */
  var _bkey0 = JSON.stringify(baziBody());
  if (_bkey0 === _submitBaziLast.key &&
      performance.now() - _submitBaziLast.ts < 1500) {
    showToast('这盘刚算过，结果就是上面那张～', 'info');
    return;
  }
  _submitBaziBusy = true;
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
        || body.month < 1 || body.month > 12 || body.day < 1 || body.day > 31) {
      /* R233k：预检失败聚焦出错格 + toast（此前只有屏外一行灰字）。 */
      var _fb = (body.year == null || body.year < 1900 || body.year > 2100) ? 'year'
        : (body.month == null || body.month < 1 || body.month > 12) ? 'month' : 'day';
      _failField(_fb, 'result', '日期看起来不太对，检查一下年月日再试～');
      return;
    }
    /* R233k（R45-Top5-1）：1-31 合法但当月不存在（2/31）也在前端拦。 */
    var _badd = _badYmdField('year', 'month', 'day');
    if (_badd) {
      _failField(_badd, 'result',
        '这一天不存在——' + num('month') + ' 月没有 ' + num('day') + ' 号');
      return;
    }
    WARM_LAST_QUESTION = body.question || '';   /* R206b US4：共情模板选择依据 */
    const j = await postJSON('/api/bazi', body);
    /* 只在成功后记账——失败重试（failWithRetry）不该被同参防抖拦 */
    _submitBaziLast = { key: _bkey0, ts: performance.now() };
    /* R230y：本人表单成功提交 → 存「我的生日」并代入其余同人表单 */
    if (body.calendar_type === 'solar') {
      _meSave('me', { y: body.year, m: body.month, d: body.day,
        h: body.hour_known ? body.hour : null, g: body.gender });
      _meFillAll();
    }
    const paipan = j.paipan || {};
    /* R206b US1：给陪伴层喂坐标事实（干支五行词，非 PII——不含生日） */
    try {
      const _warmFacts = (j.warm && j.warm.details || [])
        .map(function (d) { return d.title + '：' + (d.lines || []).slice(0, 2).join('；'); })
        .slice(0, 3);
      const _pp = paipan.render || '';
      CHAT_LAST_FACTS = (_pp ? ['四柱：' + _pp] : []).concat(_warmFacts);
      /* R233r（R49-Top5-2）：能量卡坐标补上——元素/幸运色/幸运数字
       * 是用户聊「我今天穿什么色」类问题的锚。 */
      var _ec0 = (j.warm && j.warm.energy_card) || {};
      if (_ec0.element) CHAT_LAST_FACTS.push('本命元素：' + _ec0.element);
      var _lc0 = _ec0.lucky_colors, _ln0 = _ec0.lucky_numbers;
      if (_lc0 && _lc0.length) CHAT_LAST_FACTS.push('幸运色：' + _lc0.join('、'));
      if (_ln0 && _ln0.length) CHAT_LAST_FACTS.push('幸运数字：' + _ln0.join('、'));
    } catch (e) { CHAT_LAST_FACTS = []; }
    paint('result', buildBaziResult(j));
    rememberVoice('result', j, buildBaziResult);
    rememberResult('bazi', j, body.question || '', body);   /* R219b（P0-2）：聊聊上下文；v2 补 body（性别） */
    revealResult('result');            // 005 判据 1：提交后无需滚动即见结论
    /* R230n续（R23-P3-6）：排盘成功广播脏标——其他 tab 的历史列表即时失效。 */
    try {
      if (window.BroadcastChannel) {
        var _bc = new BroadcastChannel('paipan_history');
        _bc.postMessage('dirty'); _bc.close();
      }
    } catch (e) {}
    pollAiPolish('result', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    on('shareBazi', function () { downloadPoster(j, 'bazi'); });   /* R218a-巡2（N-04）：传 view 让通用模板接管 */
    /* R219b（P0-4）：历史记录不再落库，无「最近解读」列表可刷新。 */
  } catch (e) {
    /* R218a-巡4（E-a/E-b）：失败态清成功期说明文字 + 内联重试按钮。 */
    failWithRetry('result', '计算失败：' + e.message, function () { submitBazi(); });
  } finally {
    _submitBaziBusy = false;
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

async function doSearch() {
  busy('searchResult', '检索中…');
  const params = new URLSearchParams();
  const q = val('rq');
  if (!q) {
    fail('searchResult', '先写个想查的词，比如「无为」');
    return;
  }
  params.set('q', q);
  if (val('rlayer')) params.set('layer', val('rlayer'));
  if (val('rwork')) params.set('work', val('rwork'));
  try {
    const j = await api('/api/search?' + params.toString());
    const searchCountLine = (j.truncated && j.total > j.count)
      ? '命中 ' + esc(j.count) + ' 条（共 ' + esc(j.total) + ' 条，显示前 ' + esc(j.count) + '）'
      : '命中 ' + esc(j.count) + ' 条';
    paint('searchResult',
      (j.hint ? '<p class="hit-cite">' + esc(j.hint) + '</p>' : '') +
      '<p class="hit-cite">' + searchCountLine + '</p>' +
      renderHits(j.hits, { empty: '🔍 无命中，换个词试试？', score: true }));
  } catch (e) {
    fail('searchResult', '检索失败：' + e.message);
  }
}

async function doResearch() {
  busy('researchResult', '研究中…');
  const q = val('rq2');
  if (!q) {
    fail('researchResult', '先写个想查的词，比如「无为」');
    return;
  }
  const params = new URLSearchParams({ q: q });
  const maxAddr = num('rmax');
  // 后端值域是 1-6（超出返回 400），前端先钳制，避免把 400 当成"坏了"。
  if (maxAddr != null) params.set('max_addresses', String(Math.min(Math.max(maxAddr, 1), 6)));
  try {
    const j = await api('/api/research?' + params.toString());
    let html = '';
    if (j.refused) {
      /* R233g（R44-P0-2）：判据编号不上屏。 */
      html += '<div class="no-evidence">这个问题库里没对上的材料，不作推测——' +
        esc(j.reason || '换个说法再问问看') + '</div>';
    }
    if (j.steps && j.steps.length) {
      html += '<h3>检索链路</h3><ol class="step-list">';
      j.steps.forEach(function (s) {
        html += '<li>' + esc(s.action || '') + ' 「' + esc(s.query || '') + '」 → 翻到 ' +
          esc(s.found) + ' 处、留下 ' + esc(s.kept) + ' 处' +
          (s.note ? '（' + esc(s.note) + '）' : '') + '</li>';
      });
      html += '</ol>';
    }
    if (j.comparisons && j.comparisons.length) {
      html += '<h3>同一位置，不同书的说法不一样</h3>';
      j.comparisons.forEach(function (cmp) {
        html += '<div class="finding">' + esc(cmp.addr || '') + '：' +
          esc((cmp.findings || []).length) + ' 处差异</div>';
        (cmp.findings || []).slice(0, 5).forEach(function (f) {
          html += '<div class="finding">' + esc(f.line || f.note || '') + '</div>';
        });
      });
    }
    // R000a-04：原读 j.addresses（后端从来没这个键）→ 现读 evidence。
    html += '<h3>证据集</h3>' +
      renderHits(j.evidence, { empty: '🔍 无命中，换个词试试？' });
    if (j.flagged && j.flagged.length) {
      html += '<h3>质量闸门标记（默认不采信）</h3>' +
        renderHits(j.flagged, { empty: '' });
    }
    paint('researchResult', html);
  } catch (e) {
    fail('researchResult', '研究失败：' + e.message);
  }
}

async function doAddr() {
  busy('addrResult', '定位中…');
  const params = new URLSearchParams();
  params.set('scheme', val('ascheme') || 'zhouyi');
  if (val('aguan')) params.set('gua', val('aguan'));
  if (val('ayao')) params.set('yao', val('ayao'));
  if (val('aname')) params.set('addr_name', val('aname'));
  if (val('aaddr1')) params.set('addr1', val('aaddr1'));
  if (val('aaddr2')) params.set('addr2', val('aaddr2'));
  try {
    const j = await api('/api/addr?' + params.toString());
    paint('addrResult',
      '<p class="hit-cite">' + esc(j.scheme) + ' · 翻到 ' + esc(j.count) + ' 条</p>' +
      renderHits(j.hits, { empty: '🔍 无命中，换个定位参数？' }));
  } catch (e) {
    fail('addrResult', '定位失败：' + e.message);
  }
}

async function doCompare() {
  busy('compareResult', '比对中…');
  const gua = num('cgua');
  if (gua == null) {
    fail('compareResult', '卦号要填 1–64 之间的数字');
    return;
  }
  const params = new URLSearchParams({ gua: String(gua) });
  if (val('cyao')) params.set('yao', val('cyao'));
  try {
    const j = await api('/api/compare?' + params.toString());
    let html = '<h3>' + esc(j.addr || '') + '　以《' + esc(j.reference || '') + '》为底本　' +
      (j.agree ? '几种版本说法一致' : '几种版本说法不一样') + '</h3>';
    const witnesses = j.witnesses || {};
    const citations = j.citations || {};
    const ids = Object.keys(witnesses);
    if (ids.length) {
      html += '<div class="cmp-grid">';
      ids.forEach(function (wid) {
        html += '<div class="cmp-wit"><h3>' + esc(citations[wid] || wid) + '</h3>' +
          '<p>' + esc(witnesses[wid]) + '</p></div>';
      });
      html += '</div>';
    }
    // 实测字段：findings[].line（已格式化的一行）+ kind/at/base/others/note。
    if (j.findings && j.findings.length) {
      html += '<h3 style="margin-top:16px;">差异明细</h3>';
      j.findings.forEach(function (f, i) {
        html += '<div class="finding" style="border-left-color:' + colorAt(i) + ';">' +
          esc(f.line || (f.kind + ' @' + f.at + ' ' + f.base)) + '</div>';
      });
    } else {
      html += '<div class="no-evidence">🔍 无差异发现，换个卦爻试试？</div>';
    }
    paint('compareResult', html);
  } catch (e) {
    fail('compareResult', '比对失败：' + e.message);
  }
}

async function doWorks() {
  busy('worksResult', '加载中…');
  try {
    const j = await api('/api/works');
    const works = j.works || [];
    if (!works.length) {
      fail('worksResult', '书目还没翻出来——点「列出」试试');
      return;
    }
    let html = '<p class="hit-cite">共 ' + esc(j.total) + ' 部</p><div class="work-grid">';
    works.forEach(function (w, i) {
      const c = colorAt(i);
      // 实测键名是 id / units（不是 work_id / count）。
      // B-008（R201b）：补展示 genre 与编址率 addressed/anchored——
      // 可编址率是本项目核心质量指标。
      const rate = w.units ? Math.round((w.addressed || 0) / w.units * 100) : null;
      const anchoredRate = w.units ? Math.round((w.anchored || 0) / w.units * 100) : null;
      /* R228d：整卡可点但纯 div 时键盘不可达——补 role/tabindex，
       * Enter/Space 触发在 initReading 的全局 keydown 委托里。 */
      html += '<div class="calc-block work-card" role="button" tabindex="0" data-work="' + esc(w.id) +
        '" style="border-left:3px solid ' + c + ';">' +
        '<h3 style="color:' + c + ';font-size:14px;">' + esc(w.title || w.id) + '</h3>' +
        '<p style="font-size:12px;color:var(--secondary);">' + esc(w.id) +
        (w.genre ? ' · ' + esc(w.genre) : '') +
        ' · ' + esc(w.source || '') + '</p>' +
        '<p style="font-size:18px;color:' + c + ';font-weight:600;">' +
        esc(w.units == null ? '?' : w.units) + '</p>' +
        '<p style="font-size:11px;color:var(--secondary);">段落 · 已编址 ' +
        esc(rate == null ? '?' : rate + '%') +
        (anchoredRate == null ? '' : '（锚定 ' + anchoredRate + '%）') + '</p></div>';
    });
    html += '</div>';
    paint('worksResult', html);
  } catch (e) {
    fail('worksResult', '加载失败：' + e.message);
  }
}

/** 书目卡片点击 → 回到检索页按该书过滤。事件委托在 initReading 里绑。 */
function searchByWork(workId) {
  const workField = el('rwork');
  if (workField) workField.value = workId;
  if (!val('rq')) {
    const q = el('rq');
    if (q) q.value = '無爲';       // 没有查询词时给一个必然有命中的默认词
  }
  activateRsec('rsec-search');
  /* R233k（R45-P2）：裸调绕锁，连点不同书后到覆盖先到——进锁+最新优先。 */
  guardedCall('searchBtn', doSearch, null, true);
}

/** 研究线程：原来发 {topic}，后端要 {kind,claim,method} → 必然 422
 *  （R000a-05）。这里按 ThreadRecordRequest 发一条 refusal 型 claim——
 *  refusal 是唯一允许无证据的 kind（G7：「证据不足」本身是合法研究输出），
 *  正好适配"新建一个空线程"这个语义。 */
async function doThread() {
  busy('threadResult', '创建中…');
  const topic = val('tq') || '新线程';
  try {
    const j = await postJSON('/api/threads', {
      kind: 'refusal',
      claim: '开题：' + topic + '（尚无证据，待检索后补充）',
      method: 'web-new-thread',
      confidence: 'open',
      topic: topic   /* R228s：后端用 topic 真开 thread 行，claim 绑定其上 */
    });
    let html = '<div class="no-evidence">线程开好了（#' + esc(j.thread_id) + '）</div>' +
      /* R201b（B-005）：展示 claim 内容与证据数——用户能确认「记下了什么」，
       * 不再只回一行 id（响应键 claim/n_evidence 原本零引用）。 */
      '<div class="calc-block" style="margin:10px 0;">' +
      '<p style="font-size:14px;line-height:1.6;">' + esc(j.claim || '') + '</p>' +
      (j.n_evidence != null ? '<p style="font-size:12px;color:var(--secondary);">翻到 ' +
        esc(j.n_evidence) + ' 条材料</p>' : '') + '</div>';
    /* R228l：创建与拉列表分两段 try——第二步失败时不能报「创建失败」，
     * 那会误导用户重试造出重复线程。 */
    try {
      html += await _threadListHtml();
    } catch (e2) {
      html += '<div class="no-evidence">线程已创建，列表刷新失败：' +
        esc(e2.message) + '</div>';
    }
    paint('threadResult', html);
  } catch (e) {
    fail('threadResult', '创建失败：' + e.message);
  }
}

/* R230q（R28-P1-1b）：线程列表渲染抽出来——删除后整块重画用同一模板。
 * 每条补「删」按钮（data-thread-del）：空壳线程此前没有任何清理入口。 */
async function _threadListHtml() {
  const list = await api('/api/threads');
  var html = '';
  (list.threads || []).forEach(function (t) {
    /* R232d（R40-A12）：opened_at 一直在回——补上「开题日期」让老线程
     * 一眼可辨新旧（updated_at 只记最近动静）。 */
    var _opened = t.opened_at ? (' · 开题 ' + esc(t.opened_at)) : '';
    html += '<div class="thread-item"><div class="thread-topic">' +
      esc(t.topic || '') + '</div>' +
      '<div class="thread-meta">#' + esc(t.id) + ' · ' +
      esc({open:'进行中', closed:'已结束', shelved:'先收起'}[t.status] || t.status) +
      ' · 聊了 ' + esc(t.turns) + ' 轮 / 记了 ' + esc(t.claims) + ' 条 · ' +
      esc(t.updated_at || '') + _opened + '</div>' +
      '<div class="thread-actions">' +
      '<button class="thread-view" type="button" data-thread="' + esc(t.id) +
      '">查看</button>' +
      '<button class="thread-del" type="button" data-thread-del="' + esc(t.id) +
      '" aria-label="删除线程 #' + esc(t.id) + '">删</button></div></div>';
  });
  /* R232d（R40-A12）：线程超 50 条被截断——如实披露总数，
   * 不再让用户以为列表就这么多。 */
  if (list.truncated && list.total != null) {
    html += '<div class="thread-meta" style="margin-top:8px;">线程有点多（共 ' +
      esc(list.total) + ' 条），先看最近的 ' + esc(list.limit || 50) +
      ' 条</div>';
  }
  return html;
}

async function deleteThread(tid) {
  if (!window.confirm('删掉这条线程？里面记下的研究结论会留着')) return;
  try {
    await api('/api/threads/' + encodeURIComponent(tid), { method: 'DELETE' });
    showToast(_dayPick(['线程已删除','这条研究记录清掉了','已删除，列表干净了'], 'del'), 'success');
    /* 列表与详情共用 threadResult——重拉列表覆盖回列表态 */
    const html = await _threadListHtml();
    paint('threadResult', html || '<div class="no-evidence">还没有研究线程——上面写个主题就能开一条</div>');
  } catch (e) {
    showToast('删除失败：' + e.message, 'warn');
  }
}

async function showThread(tid) {
  busy('threadResult', '加载线程 #' + tid + '…');
  try {
    const j = await api('/api/threads/' + encodeURIComponent(tid));
    let html = '<h3>线程 #' + esc(tid) + '</h3>';
    (j.turns || []).forEach(function (t) {
      html += '<div class="' + (t.role === 'user' ? 'turn-user' : 'turn-assistant') +
        '">' + (t.role === 'user' ? '你' : '小满') + '：' + esc(t.text || '') + '</div>';
    });
    /* R233y（R54-P1-13）：kind/confidence/role 枚举翻中文，
     * 不再 JSON 直出。 */
    var _KIND_CN = { thread: '线程', summary: '笔记', answer: '结论',
      link: '关联', diff: '比对', refusal: '存疑' };
    var _CONF_CN = { high: '把握高', mid: '把握中', low: '把握低',
      open: '进行中' };
    var _ROLE_CN = { supports: '支持', contradicts: '反驳',
      context: '背景' };
    (j.claims || []).forEach(function (c) {
      html += '<div class="claim-box"><span class="claim-kind">' +
        esc(_KIND_CN[c.kind] || c.kind) +
        '</span>' + esc(c.claim || '') +
        '<span class="claim-conf">' +
        esc(_CONF_CN[c.confidence] || c.confidence || '') +
        /* R232d：method/created_at 此前零读——补上让论断可追溯 */
        (c.method ? ' · ' + esc(c.method) : '') +
        (c.created_at ? ' · ' + esc(c.created_at) : '') + '</span>';
      (c.evidence || []).forEach(function (ev) {
        html += '<div class="claim-ev">' +
          esc(_ROLE_CN[ev.role] || ev.role) + ' · ' + esc(ev.work_id) +
          ' @' + esc(ev.page_anchor || '') + '：' + esc(ev.quote || '') + '</div>';
      });
      html += '</div>';
    });
    if (j.verify) {
      html += '<div class="interp-basis">证据回查：' + esc(j.verify.ok) +
        ' 条还能对得上' + (j.verify.stale ? '，' + esc(j.verify.stale) +
        ' 条过期了' : '') + '</div>';
    }
    paint('threadResult', html);
  } catch (e) {
    fail('threadResult', '加载失败：' + e.message);
  }
}

/* ── 读书：两书对照 / 概念研究（R000a-02：原本完全没有处理器）───── */

async function doCompareWorks() {
  busy('cwResult', '对照中…');
  const params = new URLSearchParams({
    work_a: val('cwa'),
    work_b: val('cwb'),
    q: val('cwq')
  });
  try {
    const j = await api('/api/compare_works?' + params.toString());
    if (j.error) {
      fail('cwResult', j.error);
      return;
    }
    let html = '<h3>概念「' + esc(j.concept || '') + '」两书对照</h3><div class="cmp-grid">';
    (j.works || []).forEach(function (w, i) {
      const c = colorAt(i);
      html += '<div class="cmp-wit" style="border-left:3px solid ' + c + ';">' +
        '<h3 style="color:' + c + ';">《' + esc(w.title || w.work_id) + '》 翻到 ' +
        esc(w.n_hits) + ' 条' + (w.truncated ? '（只展示前几条）' : '') + '</h3>' +
        '<p style="font-size:12px;color:var(--secondary);">' +
        (w.attribution ? '底本：' + esc(w.attribution) + ' · ' : '') +
        '各层命中：' + esc(fmtScalar(w.layers)) + '</p>';
      (w.top || []).forEach(function (t) {
        html += '<div class="ev-item"><div class="ev-meta">' + esc(humanCite(t.citation || '')) +
          (t.layer ? ' · ' + esc(t.layer) : '') + '</div>' +
          '<div class="ev-text">' + esc(t.text || '') + '</div>' +
          (t.disclosure ? '<div class="ev-disc">' + esc(t.disclosure) + '</div>' : '') +
          '</div>';
      });
      html += '</div>';
    });
    html += '</div>';
    const shared = j.shared_addresses || [];
    if (shared.length) {
      html += '<h3 style="margin-top:16px;">两本书在同一位置都讲了这件事</h3>';
      // R228o：shared_addresses 项只有 {addr}（research.compare_works），
      // 两书命中是集合语义本身——旧代码读不存在的 s.works 会渲染出
      // "undefined"（契约探针实测抓获的真漂移）。
      shared.forEach(function (s) {
        html += '<div class="finding">' + esc(s.addr || '') + '</div>';
      });
    } else {
      html += '<div class="no-evidence">两本书没在同一位置对上这个词</div>';
    }
    paint('cwResult', html);
  } catch (e) {
    fail('cwResult', '对照失败：' + e.message);
  }
}

async function doConcept() {
  busy('conceptResult', '研究中…');
  const q = val('cq');
  if (!q) {
    fail('conceptResult', '先写个概念，比如「无为」');
    return;
  }
  try {
    const j = await api('/api/concept?' + new URLSearchParams({ q: q }).toString());
    let html = '<h3>「' + esc(j.concept || q) + '」在 ' + esc(j.works_with_hits) +
      ' 部书中有命中' + (j.truncated ? '（扫描上限 ' + esc(j.scan_limit) + '）' : '') +
      '</h3>';
    html += '<div class="table-scroll"><table class="works"><thead><tr><th>书</th><th>命中</th><th>层分布</th>' +
      '</tr></thead><tbody>';
    (j.census || []).forEach(function (row) {
      html += '<tr><td>《' + esc(row.title || row.work_id) + '》' +
        /* R232d：底本归属（kanripo/tls/…）一直在回——同名书区分版本 */
        (row.attribution ? '<div style="font-size:11px;color:var(--muted);">' +
          esc(row.attribution) + '</div>' : '') + '</td>' +
        '<td class="num">' + esc(row.n_hits) + '</td>' +
        '<td>' + esc(fmtScalar(row.layers)) + '</td></tr>';
    });
    html += '</tbody></table></div>';
    /* R232d（R40-A13）：0 命中时后端专门回了引导语 hint，
     * 此前前端不渲染——空结果只剩一张空表。 */
    if (!(j.census || []).length && j.hint) {
      html += '<p class="hit-cite">' + esc(j.hint) + '</p>';
    }
    const shared = j.shared_addresses || [];
    if (shared.length) {
      html += '<h3 style="margin-top:16px;">同一位置的多种说法</h3>';
      shared.forEach(function (s) {
        html += '<div class="finding">' + esc(s.addr || '') + '　' +
          esc(fmtScalar(s.works)) + '</div>';
      });
      /* R232d：共享址超 30 条被截断——如实披露总数（shared_total 一直在回）。 */
      if (j.shared_truncated && j.shared_total) {
        html += '<div class="finding" style="color:var(--muted);">共 ' +
          esc(j.shared_total) + ' 处同址，先看前 30</div>';
      }
    }
    const first = (j.census || [])[0];
    if (first && first.top && first.top.length) {
      html += '<h3 style="margin-top:16px;">《' + esc(first.title || first.work_id) +
        '》原文样例</h3>' + renderHits(first.top, { empty: '' });
    }
    paint('conceptResult', html);
  } catch (e) {
    fail('conceptResult', '研究失败：' + e.message);
  }
}

/* ── 读书：结构 / 章节 / 摘要（原三个子标签无绑定，R000a-03）────── */

async function doBookStructure() {
  const workId = val('bswork');
  if (!workId) {
    fail('bsStructure', '先填书号（比如 KR1a0001），书目页能找到');
    return;
  }
  busy('bsStructure', '加载结构…');
  try {
    const j = await api('/api/bookstudy/structure?' +
      new URLSearchParams({ work_id: workId }).toString());
    if (j.error) {
      fail('bsStructure', j.error);
      return;
    }
    let html = '<h3>《' + esc(j.title || j.work_id) + '》 scheme=' + esc(j.scheme) +
      ' · ' + esc(j.n_sections) + ' 节 / ' + esc(j.n_units) + ' 单元</h3>';
    html += '<div class="table-scroll"><table class="works"><thead><tr><th>节</th><th>单元</th><th>字数</th>' +
      '<th>层</th><th>样例</th></tr></thead><tbody>';
    (j.sections || []).forEach(function (s) {
      html += '<tr><td>' + esc(s.label || '') + '</td>' +
        '<td class="num">' + esc(s.n_units) + '</td>' +
        '<td class="num">' + esc(s.chars) + '</td>' +
        '<td>' + esc(fmtScalar(s.layers)) + '</td>' +
        '<td>' + esc((s.sample || '').slice(0, 40)) + '</td></tr>';
    });
    html += '</tbody></table></div>';
    paint('bsStructure', html);
  } catch (e) {
    fail('bsStructure', '加载失败：' + e.message);
  }
}

async function doBookChapter() {
  const workId = val('bswork');
  const scheme = val('bsscheme');
  if (!workId) {
    fail('bsChapter', '先填书号（比如 KR1a0001），书目页能找到');
    return;
  }
  if (!scheme) {
    fail('bsChapter', '先选一个编址方式；没有编址的书去「结构」页看');
    return;
  }
  busy('bsChapter', '加载章节…');
  const params = new URLSearchParams({ work_id: workId, scheme: scheme });
  if (val('bsaddr1')) params.set('addr1', val('bsaddr1'));
  try {
    const j = await api('/api/bookstudy/chapter?' + params.toString());
    if (j.error) {
      fail('bsChapter', j.error);
      return;
    }
    let html = '<h3>' + esc(j.work_id) + ' · ' + esc(j.scheme) + ' 第 ' +
      esc(j.section) + ' 节 · ' + esc(j.n_units) + ' 段</h3>';
    (j.units || []).forEach(function (u) {
      html += '<div class="ev-item"><div class="ev-meta">' + esc(humanCite(u.citation || '')) +
        (u.addr2 ? ' · ' + esc(u.addr2) : '') + (u.layer ? ' · ' + esc(u.layer) : '') +
        (u.suspect ? ' ⚠ 存疑' : '') + '</div>' +
        '<div class="ev-text">' + esc(u.text || '') + '</div></div>';
    });
    paint('bsChapter', html);
  } catch (e) {
    fail('bsChapter', '加载失败：' + e.message);
  }
}

async function doBookSummary() {
  const workId = val('bswork');
  if (!workId) {
    fail('bsSummary', '先填书号（比如 KR1a0001），书目页能找到');
    return;
  }
  busy('bsSummary', '加载摘要…');
  try {
    const j = await api('/api/bookstudy/summary?' +
      new URLSearchParams({ work_id: workId }).toString());
    if (j.error) {
      fail('bsSummary', j.error);
      return;
    }
    let html = '<h3>《' + esc(j.title || j.work_id) + '》知识卡</h3><div class="calc-grid">';
    /* R233y（R54-P1-19）：知识卡字段名半行话化翻一遍。 */
    [
      ['体裁', j.genre], ['编址方式', j.scheme], ['章节数', j.n_sections],
      ['段落数', j.n_units], ['总字数', j.total_chars],
      ['各层命中', fmtScalar(j.layers)], ['未编址段落', j.unaddressed_units],
      ['存疑段落', j.suspect_units], ['缺字段落', j.skipped_chars_units],
      ['最长一节', fmtScalar(j.largest_section)],
      ['最短一节', fmtScalar(j.smallest_section)]
    ].forEach(function (pair, i) {
      if (pair[1] == null) return;
      html += '<div class="calc-block" style="border-left:3px solid ' + colorAt(i) +
        ';"><h3>' + esc(pair[0]) + '</h3><p>' + esc(fmtScalar(pair[1])) + '</p></div>';
    });
    html += '</div>';
    paint('bsSummary', html);
  } catch (e) {
    fail('bsSummary', '加载失败：' + e.message);
  }
}

/* ── 六爻 / 黄历 / 起名 / 桃花 / 塔罗 / 合婚 ───────────────────── */

/** 六爻结果区 HTML 构建（抽成纯函数，切换口吻时可就地重画）。 */
function buildLiuyaoResult(j) {
  const ben = j.ben || {};
  const bian = j.bian || {};
  let html = '<div class="card"><h2>🔮 六爻卦象</h2>';
  /* R216b 续（UX 队列 U-007）：解读先给人话结论（warm.reply 已是结论式，
   * 这里把它提到坐标区之前常显），再画卦象。
   * R216b 续4（U-022）：本块仅 warm 模式渲染；warm 模式下页尾
   * renderVoice 跳过（见下）——否则同一批解读文案与免责 badge 出现两遍。 */
  const warm = j.warm || {};
  /* R218a-08：问题绑定首屏 hook——用户问工作/感情/学业/财运时，
   * 在 warm.reply 之前给一句「针对你问的 X」让用户秒级感到被听到。
   * 6 套关键词模板 + 通用兜底。 */
  if (j.question) {
    html += liuyaoQuestionHook(j.question, ben, bian);
  }
  if (voiceMode() === 'warm' && warm.reply && warm.reply.length) {
    html += '<div class="warm-wrap"><div class="warm-l0" style="font-size:17px;">' +
      esc(warm.one_liner || '') + '</div><div class="warm-reply">';
    warm.reply.slice(0, 3).forEach(function (ln) {
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
    html += '<div class="yao-stack">';
    /* R228o：跨行链式改为命名中间变量——契约探针逐行归因，
     * 也让「降序取爻位」的意图更直白。 */
    var _sortedLines = ben.lines.slice()
      .sort(function (a, b) { return b.position - a.position; });
    _sortedLines.forEach(function (ln) {
        const mark = ln.moving ? (ln.yang ? ' ○' : ' ×') : '';
        /* R230x（V-5）：爻画真图形——阳=通长实条、阴=断两截，动爻加红点。
         * 原 ⚊/⚋ 字形在部分机型渲染成小横线、卦感弱；mark 文本保留。 */
        var _yaoCls = ln.yang ? 'yang' : 'yin';
        var _yaoBars = ln.yang ? '<i></i>' : '<i></i><i></i>';
        html += '<div class="yao-row' + (ln.moving ? ' moving' : '') + '">' +
          '<span class="yao-name">' + esc(YAO_NAME[ln.position] || ('第' + ln.position + '爻')) +
          '</span><span class="yao-sym" role="img" aria-label="' +
          (ln.yang ? '阳爻' : '阴爻') + (ln.moving ? '，动爻' : '') + '">' +
          '<span class="yao-bar ' + _yaoCls + '">' + _yaoBars + '</span>' +
          (ln.moving ? '<span class="yao-dot"></span>' : '') +
          '<span class="yao-mark">' + esc(mark) + '</span></span></div>';
      });
    html += '</div>';
  }
  if (ben.moving_lines && ben.moving_lines.length) {
    html += '<p>动爻：' + esc(ben.moving_lines.join('、')) + ' 爻——变化从这里发生</p>';
  } else {
    html += '<p>无动爻（静卦）——当下格局稳住，变化的劲不明显</p>';
  }
  if (bian.gua_name) {
    html += '<p style="margin-top:8px;color:var(--secondary);">变卦：' +
      esc(bian.gua_name) + '（第 ' + esc(bian.gua_number) + ' 卦）</p>';
  }
  // 同 buildBaziResult：經文全文只在专业模式平铺；warm 模式由 renderWarm
  // 经 renderCiteTree 折叠渲染一次（005 判据 2/3/5）。
  if (voiceMode() === 'pro') {
    if (j.ben_jing && j.ben_jing.length) {
      html += '<h3 style="margin-top:16px;color:var(--c-book);">本卦經文</h3>' +
        renderHits(j.ben_jing, { empty: '' });
    }
    if (j.bian_jing && j.bian_jing.length) {
      html += '<h3 style="margin-top:16px;color:var(--c-book);">变卦經文</h3>' +
        renderHits(j.bian_jing, { empty: '' });
    }
  }
  /* R216b 续4（U-022）：warm 模式下解读已在头部常显，页尾不再经
   * renderWarm 二次渲染同一批 reply 与 badge；pro 模式走原路径
   * （卦象转述 + 古籍平铺），判据 9 口径零改动。
   * 注意：warm 跳过时古籍折叠树也不渲染（renderCiteTree 由 renderWarm
   * 驱动）——但头部块已含 badge，坐标事实完整，无信息丢失。 */
  if (voiceMode() === 'warm') {
    /* U-022 配套：warm 跳过 renderWarm 后，經文原文改由独立折叠承载
     * （事实零删减：展开可核验；不经 renderCiteTree 是因为它会连带
     * 渲染 reply）。 */
    const evAll = [].concat(j.ben_jing || [], j.bian_jing || []);
    if (evAll.length) {
      html += '<details class="warm-basis"><summary>📜 卦爻辞原文（' +
        evAll.length + ' 段，展开对照）</summary>' +
        renderHits(evAll, { empty: '' }) + '</details>';
    }
  } else {
    html += renderVoice(j, '📖 卦象解读', ['ben_jing', 'bian_jing']);
  }
  /* R221b：交叉引用收口 7/7——六爻不收生日，引今天值宫 × 动爻多寡。
   * 放在 if/else 之外：温柔版与专业版都该看到这段。 */
  if (j.cross_ref && j.cross_ref.message) {
    html += '<div class="cross-ref"><span class="cross-ref-icon">☯️</span>' +
      esc(j.cross_ref.message) +
      crossDirBadge(j.cross_ref, 'gua_direction', '卦象') + '</div>';
  }
  html += tailHook('liuyao');
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
    doHuangli(0, true);
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
  if (_hlWeekDone) return;
  _hlWeekDone = true;
  var box = el('hlWeek');
  if (!box) return;
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
    var WD = ['日', '一', '二', '三', '四', '五', '六'];
    var html = '<div class="hl-week-title">📅 未来 7 天宜忌速览' +
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
    box.addEventListener('click', function (e) {
      var c = e.target.closest('.hl-week-cell');
      if (!c) return;
      box.querySelectorAll('.hl-week-cell').forEach(function (x) {
        x.classList.remove('active');
      });
      c.classList.add('active');
      /* R233f（R43-P2-5）：激活格同步 aria-current——读屏知道在看哪天 */
      box.querySelectorAll('.hl-week-cell').forEach(function (x) {
        x.removeAttribute('aria-current');
      });
      c.setAttribute('aria-current', 'date');
      /* R2349k（R72-B7）：点击当刻用本地日换算偏移——跨零点打开的
       * 页面点格子仍落到格子上写的那天。 */
      var _wdd = c.dataset.hldate;
      var _wdt = new Date(); _wdt.setHours(0, 0, 0, 0);
      var _woff = Math.round(
        (new Date(_wdd + 'T00:00:00') - _wdt) / 86400000);
      if (!isFinite(_woff)) return;
      doHuangli(_woff);
    });
  } catch (e) { box.hidden = true; }
}

async function doLiuyao() {
  busy('lyResult', '摇卦中…');
  // 实测后端只认 coins|time（HTML 里原来的 "dice" 会得到 400）。
  const method = val('ly_method') === 'coins' ? 'coins' : 'time';
  const body = { method: method };
  if (method === 'coins') {
    /* R216b 续（U-006）：同塔罗——高级折叠里的 Seed 留空即自动生成。 */
    const seedRaw = val('ly_seed');
    if (seedRaw !== '' && seedRaw != null) body.seed = num('ly_seed');
  } else {
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
    var _lb = _badYmdField('ly_year', 'ly_month', 'ly_day');
    if (_lb) {
      _failField(_lb, 'lyResult',
        '这一天不存在——' + num('ly_month') + ' 月没有 ' + num('ly_day') + ' 号');
      return;
    }
  }
  const q = val('ly_question');
  if (q) body.question = q;
  body.client_date = todayIso();   /* R230m：今日值宫锚本地日 */
  try {
    const j = await postJSON('/api/liuyao', body);
    paint('lyResult', buildLiuyaoResult(j));
    rememberVoice('lyResult', j, buildLiuyaoResult);
    rememberResult('liuyao', j, val('ly_question') || '');   /* R219b（P0-2） */
    revealResult('lyResult');          // 005 判据 1 场景 5：不是只修排盘
    /* R198b（US5）：六爻分享图——结果卡尾部注入按钮（对齐 shareBazi 模式） */
    var lyCard = document.querySelector('#lyResult .card');
    if (lyCard && !document.getElementById('shareLiuyao')) {
      var lyBtn = document.createElement('button');
      lyBtn.className = 'ghost fav-btn'; lyBtn.type = 'button';
      lyBtn.id = 'shareLiuyao'; lyBtn.title = '生成分享图';
      lyBtn.textContent = '📸 分享图';
      lyBtn.style.margin = '10px 0 0';
      lyCard.appendChild(lyBtn);
      lyBtn.addEventListener('click', function () { downloadPoster(j, 'liuyao'); });
    }
  } catch (e) {
    /* R230d（R16-P1-3）：与 bazi 同一条内联重试——此前只有 bazi 有。 */
    failWithRetry('lyResult', '摇卦失败：' + e.message, function () { doLiuyao(); });
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
/* D-004：批次偏移——每次换一批 +8，循环一轮后才重复 */
var _qmBatchOffset = 0;
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
function _qmSwitchStyle(style) {
  if (!_QM_STYLES[style] || _qmBusy) return;   /* R230j：chip 连点在途锁 */
  _QM_STYLE = style;
  _qmBatchOffset = 0;
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

async function doQiming() {
  if (_qmBusy) return;                        /* R230j */
  /* R233k（R45-§3）：预检前置——空字段/非法日此前要等一轮 422。 */
  if (!val('qm_surname')) { _failField('qm_surname', 'qmResult', '姓氏先填上哦'); return; }
  if (num('qm_year') == null || num('qm_month') == null || num('qm_day') == null) {
    _failField(num('qm_year') == null ? 'qm_year'
      : (num('qm_month') == null ? 'qm_month' : 'qm_day'),
      'qmResult', '年月日先填上再算哦');
    return;
  }
  var _qb = _badYmdField('qm_year', 'qm_month', 'qm_day');
  if (_qb) {
    _failField(_qb, 'qmResult',
      '这一天不存在——' + num('qm_month') + ' 月没有 ' + num('qm_day') + ' 号');
    return;
  }
  _qmBusy = true;
  busy('qmResult', '起名中…');
  try {
    const j = await postJSON('/api/qiming', {
      surname: val('qm_surname'),
      year: num('qm_year'),
      month: num('qm_month'),
      day: num('qm_day'),
      hour: num('qm_hour'),
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
      style: _QM_STYLE || 'all'    /* v3（P3）：风格档后端过滤 */
    });
    paint('qmResult', buildQimingResult(j));
    _qmFavsRender();   /* R230z（R36-P2-3）：心水名单行+♡点亮 */
    rememberResult('qiming', j, '', { gender: val('qm_gender') });   /* v2：补性别（用户反馈 bug F3） */
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
        if (!rj.review_task_id) {
          /* R216b 续5（U-019）：降级文案带人设+替代引导；按钮保持置灰。 */
          paint('nameReviewOut', '<div class="no-evidence">小满点评今天休息～' +
            '名字的寓意卡片里都有说明，先看着，回头来听故事版 ✨</div>');
          const o = el('nameReviewOut'); if (o) o.hidden = false;
          if (btn) btn.disabled = false;
          return;
        }
        const out = el('nameReviewOut');
        if (out) { out.hidden = false; out.innerHTML = '<div class="no-evidence">AI 正在翻书找典故…</div>'; }
        pollNameReview(rj.review_task_id);
      }).catch(function () {
        if (btn) btn.disabled = false;
      });
    });
    revealResult('qmResult');
    pollAiPolish('qmResult', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    on('shareQiming', function () { downloadPoster(j, 'qiming'); });   /* R198b 通用模板 */
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
    on('qmRefreshBtn', function () {
      /* D-004-fix：换一批 = 新种子 + 重新请求后端 */
      /* R224b：同上——初值已是 1，直接 +1 */
      _qmSeed = (_qmSeed || 0) + 1;
      doQiming();
    });
  } catch (e) {
    failWithRetry('qmResult', '起名失败：' + e.message, function () { doQiming(); });
  } finally {
    _qmBusy = false;                          /* R230j */
  }
}




async function doTaohua() {
  /* R233k（R45-§3）：同批预检——空字段/非法日前端先拦。 */
  if (num('th_year') == null || num('th_month') == null || num('th_day') == null) {
    _failField(num('th_year') == null ? 'th_year'
      : (num('th_month') == null ? 'th_month' : 'th_day'),
      'thResult', '年月日先填上再算哦');
    return;
  }
  var _tb = _badYmdField('th_year', 'th_month', 'th_day');
  if (_tb) {
    _failField(_tb, 'thResult',
      '这一天不存在——' + num('th_month') + ' 月没有 ' + num('th_day') + ' 号');
    return;
  }
  busy('thResult', '计算中…');
  try {
    const j = await postJSON('/api/taohua', {
      year: num('th_year'),
      month: num('th_month'),
      day: num('th_day'),
      hour: num('th_hour'),
      gender: val('th_gender') || '女'
    });
    _meSave('me', { y: num('th_year'), m: num('th_month'), d: num('th_day'),
      h: num('th_hour'), g: val('th_gender') || '女' });
    _meFillAll();   /* R230y */
    paint('thResult', buildTaohuaResult(j));
    rememberResult('taohua', j, '', { gender: val('th_gender') });   /* v2：补性别 */
    revealResult('thResult');
    pollAiPolish('thResult', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    on('shareTaohua', function () { downloadPoster(j, 'taohua'); });   /* R218a-巡2（N-04）：改用 taohua 专属 case */
  } catch (e) {
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
var _POSTER_TITLES = {
  bazi: '今日命盘', liuyao: '六爻指引', tarot: '塔罗指引',
  qiming: '五行起名', taohua: '桃花运势', hehun: '合婚配对',
  daily: '今日运势', huangli: '今日宜忌', xingzuo: '星座日运',
  birth: '我的本命盘', checkin: '打卡连签', 'checkin-week': '本周签运'
};
var _POSTER_BG_BY_VIEW = { tarot: 'lilac', xingzuo: 'lilac', birth: 'lilac',
  taohua: 'sakura', hehun: 'sakura', qiming: 'dream', checkin: 'warm',
  /* R2349d：日签/黄历海报走薄荷山月——高频分享面多一层色系新鲜度。 */
  daily: 'mint', huangli: 'mint', liuyao: 'celadon' };
/* R2349l.8：分享文案按视图定制——通用「测你的同款」太冷，给每视图
 * 一句带钩子的邀请语（小红书转发口径）。 */
var _SHARE_TEXT = {
  hehun: '我和 TA 的合拍指数出炉了，测测你们的 →',
  tarot: '我今天抽到的三张牌有点准，你也来抽 →',
  bazi: '我的命盘解读出来了，看看你的 →',
  daily: '我今天的日签领到了，看看你抽到什么签 →',
  xingzuo: '看看你今天星座运势 →',
  qiming: '古籍里挑的名字有点美，给娃试试 →',
  taohua: '我的今日桃花信号，你的呢 →',
  liuyao: '刚摇了一卦，卦象有点东西 →',
  huangli: '今天宜忌帮你查好了 →',
  checkin: '我在小满打卡攒签运，一起吗 →',
  birth: '我的本命盘出来了，看看你的 →'};
function _shareText(view) {
  return (_SHARE_TEXT[view] || '测你的同款') + ' 小满的解忧铺 ';
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
          '🌙 关系靠处不靠算——想复测随时来',
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
            '🌙 十二宫明天再排班，记得来']
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
  '冠笄': '形象焕新', '解除': '化解矛盾', '治病': '看病调理',   '捕捉': '收网——拖欠的事该了了', '安葬': '送行送别（白事）', '破土': '动工',
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
  fetch('/static/tarot/manifest.json', _preOpt)
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { TAROT_MANIFEST = j || {}; })
    .catch(function () { TAROT_MANIFEST = {}; });
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
    ? '<div class="tart"><img src="' + img + '" alt="' + esc(d.name) + '"' + _rev +
      ' onerror="this.outerHTML=\'' + esc(tarotArt(d.name)) + '\'"></div>' +
      '<div class="tinfo">'
    : '<div class="tart">' + tarotArt(d.name) + '</div><div class="tinfo">';
  return art +
    '<div class="tname">' + esc(d.name) + '</div>' +
    '<div class="tmeaning">' + esc(d.upright ? '正位' : '逆位') + '<br>' +
    esc(d.upright ? d.upright_kw : d.reversed_kw) + '</div></div>';
}


function buildTarotResult(j) {
  let html = '<div class="card"><h2>✨ 塔罗占卜</h2>';
  /* R216b 续（U-006）：工程口吻复验说明人话化；seed 编号收进 title 悬停
   * 可见（专业用户仍可复验），不再平铺在正文。 */
  html += '<p class="hit-cite" title="复验编号 ' + esc(j.seed) + '">' + esc(j.n) +
    ' 张牌 · 同一天问同一件事，翻到的就是这几张</p>';
  /* R218a-07：综合结论首屏 hook——三张牌翻完前用户先看到一句针对问题的
   * 直接回答，再下钻逐牌解读。j.question 是用户输入关键词。 */
  if (j.question) {
    html += tarotQuestionHook(j.question, j.draws || []);
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
  html += tailHook('tarot');
  html += '</div>';
  return html;
}


/** R207b：塔罗深读模板族。三段式：连起来看 → 你该留意 → 现在可以做。
 *  全部由牌名/正逆位/位置组合生成，零新事实、零吉凶断言。 */
var TAROT_POS_HINT = {
  "过去": "它说的是你已经走过的路——现在的感受很多来自那段经历",
  "现在": "这是你此刻的状态，也是三张里最值得先看清的一张",
  "未来": "它指向事情的走向，但走向会随你的选择变化",
  "阻碍": "这张牌说的是挡在路上的东西——往往是心里的某个念头",
  "环境": "这是你周围的氛围和别人的态度，不全是你能控制的",
  "建议": "这张牌是牌阵给你的提醒，最值得记住的一张",
  "结果": "如果一切照旧，事情大概率是这样收场"
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


function tarotQuestionHook(question, draws) {
  var cat = _tarotClassify(question);
  var main = (draws && draws.length) ? (draws[Math.min(1, draws.length - 1)] || draws[0]) : null;
  var upright = main && main.upright;
  var lines = {
    love: {
      true: '**整体是顺的**——你心里想的那个方向可以试着往前走一小步，缘分正在慢慢靠近。',
      false: '**现在有点拧**——先别急着给关系下结论，等心里那股劲过去再决定。'
    },
    work: {
      true: '**事业方向是稳的**——保持当前节奏，机会在慢慢冒头，多留意主动递过来的信号。',
      false: '**职场的弯弯绕绕**——近期有调整的机会但建议先稳后动，别一次性求变。'
    },
    study: {
      true: '**学运在上升**——最近 2 周是黄金复盘期，把重点章节重过一遍。',
      false: '**脑子在打烊**——今晚先放一放，把最难的题留到明天状态好时再做。'
    },
    money: {
      true: '**财运有起色**——非必要支出再压一压，留意收入上的小动静。',
      false: '**钱的事先别想**——夜里做的预算都偏严，明天再看账本更清楚。'
    },
    health: {
      true: '**状态在回温**——继续保持作息和喝水节奏，会越来越轻快。',
      false: '**身体在喊停**——今天先放自己一马，好好睡一觉。身体的事，医生和检查结果最准～'
    },
    general: {
      true: '**牌面整体是顺的**——你心里想的那个方向可以试着往前走一小步。',
      false: '**牌面有些别扭**——先别急着推进，这几天多观察少动作。'
    }
  };
  var key = upright ? 'true' : 'false';
  var line = (lines[cat] && lines[cat][key]) || lines.general[key];
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


function liuyaoQuestionHook(question, ben, bian) {
  var cat = _liuyaoClassify(question);
  var moving = (ben && ben.moving_lines && ben.moving_lines.length) || 0;
  var changed = !!bian && !!bian.gua_name;
  var lines = {
    work: {
      moving: '**对应你问的工作**：近期有调整的机会，但建议先稳后动——动爻不在当位，基础打牢再考虑主动求变。',
      quiet: '**对应你问的工作**：当下格局稳住（静卦），不急着推进——把手里这一摊做扎实比换赛道更划算。',
      changed: '**对应你问的工作**：这件事有变数，先别求一步到位，分几步走更稳。'
    },
    love: {
      moving: '**对应你问的感情**：心里有变化在酝酿——不急着表态，给情绪一段落地的空间。',
      quiet: '**对应你问的感情**：当下关系是稳的，珍惜眼前比追求新关系更值得。',
      changed: '**对应你问的感情**：这段关系到了一个转折点——变卦指向什么，你心里其实有数。'
    },
    study: {
      moving: '**对应你问的学习**：方法有调整空间——动爻提示换一种思路比死磕更管用。',
      quiet: '**对应你问的学习**：节奏是稳的，继续按计划走，重点章节再过一遍。',
      changed: '**对应你问的学习**：会换一种考法/题型/方向——保持弹性，别押宝单一路径。'
    },
    money: {
      moving: '**对应你问的财运**：有一笔进/出在酝酿——动爻提醒你预算要留余量。',
      quiet: '**对应你问的财运**：收支平衡，按现有计划存就好——别追新机会。',
      changed: '**对应你问的财运**：账本会有一笔变化，先别做大决定，等落地再算。'
    },
    health: {
      moving: '**对应你问的身体**：作息该调整了——动爻提示睡眠或饮食有一个可以改善的点。',
      quiet: '**对应你问的身体**：状态稳，保持作息就好——别熬夜别贪凉，拿不准就去查个明白。',
      changed: '**对应你问的身体**：会有小波动，先把睡眠和心情稳住。'
    },
    general: {
      moving: '**对应你问的事**：变化在酝酿，先别急——给趋势一段落地的空间。',
      quiet: '**对应你问的事**：当下是稳的，按现有节奏走最划算。',
      changed: '**对应你问的事**：这件事有变数，分几步走比一步到位更稳。'
    }
  };
  var key = moving ? 'moving' : (changed ? 'changed' : 'quiet');
  var line = (lines[cat] && lines[cat][key]) || lines.general[key];
  return '<div class="tarot-question-hook"><span class="tarot-hook-tag">针对「' +
    esc(String(question).slice(0, 18)) + '」</span><p>' + renderRichText(line) + '</p></div>';
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
      esc(names.join('、')) + ' —— 把它们连起来，其实是这样一个过程：</p>';
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
    var hint = TAROT_POS_HINT[pos] ||
      ('这一步说的是「' + pos + '」的位置');
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
  // 第三段：行动建议（按主牌正/逆位给方向感，不给断言）
  var main = draws[Math.min(1, draws.length - 1)] || draws[0];
  html += '<p class="tarot-advice">' +
    (main.upright
      ? '牌面整体是顺的：你心里想的那个方向可以试着往前走一小步，不用一下子做很大的决定。'
      : '牌面有些别扭：先别急着推进，这几天多观察少动作，等心里那股拧劲过去了再决定。') +
    /* R222b（E-302 P0）：此处原有「牌只是镜子，怎么走还是你自己说了算。」
     * ——多一个「自己」躲过了禁用词 grep（审查轨渲染后扫 innerText 才抓到）。
     * 前半句刚给了具体建议（往前走一小步 / 先别急着推进），这句免责声明
     * 正好把建议抵消掉，属用户明令禁用的套话，整句删除不做替换。 */
    '</p>';
  html += '</div>';
  /* R230y（R36-P2-1）：同日同问 seed 固定——提示文案跟着结果走，
   * 口吻切换重渲时不丢。 */
  if (_trNoteDay) {
    html += '<p class="hit-cite">同一问题今天牌面不变——想再问就换个问题，或明天再来看看～</p>';
  }
  return html;
}


/* R230y（R36-P2-1）：一事一天一问——同一问题同一天派生同一 seed，
 * 连点不再出互相矛盾的牌面；换问题/隔天自然换牌。 */
var _trNoteDay = '';
async function doTarot() {
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
      _trNoteDay = todayIso();
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
  /* R230d（R16-P2-5）：静默钳位会让用户以为抽了输入的张数——
   * 超界时吱一声（防呆提示，不阻断）。 */
  if (n != null && n !== body.n) {
    showToast('牌数最多 10 张，已按 ' + body.n + ' 张抽', 'info');
  }
  if (seed != null) body.seed = seed;
  const q = q0;
  if (q) body.question = q;
  body.client_date = todayIso();   /* R230m：今日值宫锚本地日 */
  try {
    // /api/tarot 支持多张牌阵（含 position）；/api/tarot/draw 只给单张。
    const j = await postJSON('/api/tarot', body);
    paint('trResult', buildTarotResult(j));
    rememberVoice('trResult', j, buildTarotResult);
    rememberResult('tarot', j, q || '');   /* R219b（P0-2）：牌名+正逆位进第一句 */
    revealResult('trResult');
    /* R230d（R16-P2-2）：塔罗分享按钮——buildShareData 的 tarot case
     * 早就画好了，页面上却从没挂入口（liuyao 同模式）。 */
    var trCard = el('trResult');
    if (trCard && !document.getElementById('shareTarot')) {
      var trBtn = document.createElement('button');
      trBtn.className = 'ghost fav-btn';
      trBtn.id = 'shareTarot'; trBtn.title = '生成分享图';
      trBtn.textContent = '📸 分享图';   /* R231d（R37-F11）：全站统一 📸 */
      trBtn.style.margin = '10px 0 0';
      trCard.appendChild(trBtn);
      trBtn.addEventListener('click', function () { downloadPoster(j, 'tarot'); });
    }
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
    failWithRetry('trResult', '抽牌失败：' + e.message, function () { doTarot(); });
  }
}


async function doHehun() {
  /* R233k（R45-§3）：双侧预检——空字段/非法日前端先拦。
   * R2349（R65-P1-5）：邀请态下 A 侧=TA、B 侧=我——措辞随视角翻转。 */
  var _hs = window.__hhInviteMode
    ? [['hh_a_year','hh_a_month','hh_a_day','TA 的'],
       ['hh_b_year','hh_b_month','hh_b_day','你的']]
    : [['hh_a_year','hh_a_month','hh_a_day','你的'],
       ['hh_b_year','hh_b_month','hh_b_day','TA 的']];
  for (var _hi = 0; _hi < _hs.length; _hi++) {
    var _hp = _hs[_hi];
    if (num(_hp[0]) == null || num(_hp[1]) == null || num(_hp[2]) == null) {
      _failField(num(_hp[0]) == null ? _hp[0]
        : (num(_hp[1]) == null ? _hp[1] : _hp[2]),
        'hhResult', _hp[3] + '年月日先填上哦');
      return;
    }
    var _hb = _badYmdField(_hp[0], _hp[1], _hp[2]);
    if (_hb) {
      _failField(_hb, 'hhResult',
        _hp[3] + '日期不存在——' + num(_hp[1]) + ' 月没有 ' + num(_hp[2]) + ' 号');
      return;
    }
  }
  busy('hhResult', '计算中…');
  try {
    const j = await postJSON('/api/hehun', {
      a_year: num('hh_a_year'),
      a_month: num('hh_a_month'),
      a_day: num('hh_a_day'),
      a_hour: num('hh_a_hour'),
      a_gender: val('hh_a_gender') || '女',
      b_year: num('hh_b_year'),
      b_month: num('hh_b_month'),
      b_day: num('hh_b_day'),
      b_hour: num('hh_b_hour'),
      b_gender: val('hh_b_gender') || '女',
      /* R230z（R36-P1-2）：昵称（可空）——后端回显进结果/海报/历史 */
      a_name: (val('hh_a_name') || '').trim() || null,
      b_name: (val('hh_b_name') || '').trim() || null
    });
    /* R230z（R36-P1-2）：昵称前端注入响应——结果卡/海报共用 j 一处 */
    j.a_name = (val('hh_a_name') || '').trim() || null;
    j.b_name = (val('hh_b_name') || '').trim() || null;
    /* R230y：A=我，B=TA——两条 profile 分开存
     * R233n续：邀请链落地时视角相反——受邀者填的 B 才是「自己」，
     * A（发起人）落到 me:partner。手改过 A 侧则恢复默认。 */
    if (window.__hhInviteMode) {
      _meSave('me', { y: num('hh_b_year'), m: num('hh_b_month'),
        d: num('hh_b_day'), h: num('hh_b_hour'), g: val('hh_b_gender') || '女' });
      _meSave('me:partner', { y: num('hh_a_year'), m: num('hh_a_month'),
        d: num('hh_a_day'), h: num('hh_a_hour'), g: val('hh_a_gender') || '女' });
    } else {
      _meSave('me', { y: num('hh_a_year'), m: num('hh_a_month'),
        d: num('hh_a_day'), h: num('hh_a_hour'), g: val('hh_a_gender') || '女' });
      _meSave('me:partner', { y: num('hh_b_year'), m: num('hh_b_month'),
        d: num('hh_b_day'), h: num('hh_b_hour'), g: val('hh_b_gender') || '女' });
    }
    _meFillAll();
    paint('hhResult', buildHehunResult(j));
    rememberResult('hehun', j, '');   /* R219b（P0-2）：双方日柱进第一句 */
    revealResult('hhResult');
    pollAiPolish('hhResult', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    on('shareHehun', function () { downloadPoster(j, 'hehun'); });   /* R218a-巡2（N-04）：改用 hehun 专属 case */
    /* R233n（R47-Top5-1）：邀请链——把 A 侧生辰编进 ?view=hehun 参数，
     * 对方打开即预填+提示「轮到你了」。 */
    on('hhInvite', function () {
      try {
        var _u = location.origin + location.pathname + '?view=hehun&from=invite' +
          '&ay=' + encodeURIComponent(val('hh_a_year') || '') +
          '&am=' + encodeURIComponent(val('hh_a_month') || '') +
          '&ad=' + encodeURIComponent(val('hh_a_day') || '') +
          '&ah=' + encodeURIComponent(val('hh_a_hour') || '') +
          '&ag=' + encodeURIComponent(val('hh_a_gender') || '') +
          '&an=' + encodeURIComponent(val('hh_a_name') || '');
        var _ok = function () {
          showToast(_dayPick(['邀请链接复制好了（里面有你的生辰，发给信任的人哦）',
            '链接已备好——TA 打开就能接着测（链接含你的生辰信息）',
            '复制成功——记得链接里带着你的生日，发给熟人就好'], 'hhinv'));
        };
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(_u).then(_ok, function () {
            _legacy();
          });
        } else { _legacy(); }
        /* R233t（R51-P2-18a）：clipboard API 缺失/被拒时此前直接弹
         * 「复制好了」但实际没复制——受邀人收到空气。走 execCommand。 */
        function _legacy() {
          try {
            var _ta = document.createElement('textarea');
            _ta.value = _u; _ta.style.cssText = 'position:fixed;opacity:0';
            document.body.appendChild(_ta); _ta.select();
            document.execCommand('copy') ? _ok() :
              showToast('复制没成功——手动复制地址栏链接也行', 'warn');
            _ta.remove();
          } catch (e2) {
            showToast('复制没成功——手动复制地址栏链接也行', 'warn');
          }
        }
      } catch (e) { showToast('邀请链接没生成成功，再试一次？', 'warn'); }
    });
    /* R230z（R36-P1-2）：存这对 → /api/favorites，下次一键回填 */
    on('hhSavePair', async function () {
      var btn = el('hhSavePair');
      if (btn) btn.disabled = true;
      var _an = (val('hh_a_name') || '').trim(), _bn = (val('hh_b_name') || '').trim();
      var ref = [num('hh_a_year'), num('hh_a_month'), num('hh_a_day'),
        num('hh_a_hour'), val('hh_a_gender') || '女',
        num('hh_b_year'), num('hh_b_month'), num('hh_b_day'),
        num('hh_b_hour'), val('hh_b_gender') || '女',
        _an.slice(0, 8), _bn.slice(0, 8)].join('|');
      try {
        await postJSON('/api/favorites', {
          type: 'hehun', ref_id: ref.slice(0, 64),
          title: (_an || '我') + ' × ' + (_bn || 'TA')
        });
        showToast('已存下这对～下次点上面的标签就能直接填', 'info');
        _hhFavsRender();
      } catch (e) {
        showToast('没存上：' + e.message, 'error');
      } finally {
        if (btn) btn.disabled = false;
      }
    });
  } catch (e) {
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
    /* v2 修复：年份范围扩为 1900-2100（原只有今年±1，用户没法查自己生日的星座） */
    for (var yy = 1900; yy <= 2100; yy++) {
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
    showToast(y + ' 年 ' + m + ' 月没有 ' + d + ' 号——按 ' +
      m + ' 月 ' + days + ' 号查了', 'info');
  }
  ds.value = String(Math.min(d, days));
}


function xzShiftDay(step) {
  var parts = xzDateStr().split('-');
  var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  d.setDate(d.getDate() + step);
  /* R2349k（R72-B8）：历法表界 1900–2100——越界此前给 select 塞进
   * 不存在的选项、xzDateStr 读空回落今天（看着像「跳回今天」）。
   * 钳在边界日并告诉用户。 */
  var _lo = new Date(1900, 0, 1), _hi = new Date(2100, 11, 31);
  if (d < _lo) {
    xzSetDate(1900, 1, 1);
    showToast('黄历表最早到 1900 年，再往前翻不到啦', 'info');
    return doXingzuo(true);
  }
  if (d > _hi) {
    xzSetDate(2100, 12, 31);
    showToast('黄历表最远到 2100 年，再往后翻不到啦', 'info');
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
          '</div>';
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
      html += '<div class="xz-grid">';
      j.signs.forEach(function (s) {
        var cls = s.is_today ? ' xz-active' : '';
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
        html += '<div class="xz-card' + cls + (_stt ? ' xz-tap' : '') + '"' +
          (_stt ? ' title="' + esc(_stt) + '"' : '') +
          '><img class="xz-card-img" src="/static/cream/zodiac-' + _zk + '.jpg" alt="' + esc(s.sign) + '" loading="lazy" onerror="this.classList.add(\'is-missing\')"><div class="xz-card-body"><span class="xz-name">' + esc(s.sign) + '</span>' +
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
      _xzg.addEventListener('click', function (e) {
        var c = e.target && e.target.closest
          ? e.target.closest('.xz-card.xz-tap') : null;
        if (!c) return;
        var tri = c.querySelector('.xz-tri');
        if (!tri) return;
        tri.hidden = !tri.hidden;
        var mo = c.querySelector('.xz-more');
        if (mo) mo.textContent = tri.hidden ? '三运 ›' : '收起 ‹';
      });
    }
    _xzLastDate = dateStr;   /* R228f */
    _xzRenderedOn = todayIso();   /* R2349k（R72-B2） */
    rememberResult('xingzuo', j, '');   /* R219b（P0-2）：今日值宫进第一句 */
    revealResult('xzResult');
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
  '面试': ['上任'], '求职': ['上任'], '上班': ['上任'], '入职': ['上任'],
  '约会': ['嫁娶'], '表白': ['嫁娶'], '相亲': ['嫁娶'], '结婚': ['嫁娶'], '领证': ['嫁娶'],
  /* R229q：与服务端 _CHAT_SCENE_TERMS 逐键同构（probe_date_parity 钉扎）。
   * 「入宅」入搬家系；「平整」上行注释已带。 */
  /* R2349n（R77-P2-6）：「移徒」异体字死词摘除——词表统一为移徙。 */
  '搬家': ['移徙', '入宅', '修造', '平整'], '挪窝': ['移徙'],
  '远行': ['出行'], '装修': ['修造', '动土'],
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
  '手术': ['求医', '治病', '求医疗病'], '开刀': ['求医'],
  '体检': ['求医', '治病', '求医疗病'], '洗牙': ['求医', '治病', '求医疗病'],
  '拔牙': ['求医', '治病', '求医疗病'], '医美': ['求医', '治病', '求医疗病'],
  '整容': ['求医', '治病', '求医疗病'],
  '借钱': ['纳财'], '讨债': ['纳财'], '还钱': ['纳财'], '还贷': ['纳财'],
  '辞职': ['解除'], '离职': ['解除'], '跳槽': ['解除'], '换工作': ['解除'],
  '解除合同': ['解除'], '毁约': ['解除'], '退婚': ['解除'], '分手': ['解除'],
  '说拜拜': ['解除'], '拜拜了': ['解除'], '再见': ['解除'],
  '宠物': ['进人口'], '养猫': ['进人口'], '养狗': ['进人口'],
  '钓鱼': ['捕捉'], '捕捞': ['捕捉'], '种菜': ['栽种'], '诉讼': ['诉讼'],
  '打官司': ['诉讼'], '和解': ['解除'], '动工': ['动土', '破土'],
  /* R229w：逛街/购物/聚餐系落地真规范词（后端 _CHAT_SCENE_TERMS 同构，
   * probe_date_parity 钉扎）——出门类→出行，聚餐类→出行+谒贵。 */
  '买东西': ['出行'], '购物': ['出行'], '逛街': ['出行'],
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
  'do脸': ['求医'], '水光针': ['求医'], '双眼皮': ['求医'], '微整': ['求医'],
  '见家长': ['谒贵','嫁娶'], '见父母': ['谒贵','嫁娶'],
  /* R2349d：「见男朋友家长」里「见家长」不连续——补「家长」兜底。 */
  '家长': ['谒贵','嫁娶'], '订婚': ['嫁娶'],
  '提亲': ['嫁娶'], '彩礼': ['纳财'], '产检': ['求医'], '求婚': ['嫁娶'],
  '离婚': ['解除'],
  '抢票': ['纳财'], '开票': ['纳财'], '演唱会': ['出行','谒贵'],
  '签售会': ['出行','谒贵'], '见爱豆': ['出行','谒贵'], '音乐节': ['出行'],
  '应援': ['出行'],
  '接猫': ['进人口'], '领养': ['进人口'], '接新猫': ['进人口'],
  '接小猫': ['进人口'], '绝育': ['求医'], '打疫苗': ['求医'], '疫苗': ['求医'],
  '看房': ['出行','入宅'], '搬新窝': ['移徙','入宅'], '续租': ['立券','移徙'],
  '租房': ['立券','入宅'],
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
  '纹身': ['求医', '冠笄'], '割双眼皮': ['求医'],
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
  '打耳洞': ['求医'],
  '种睫毛': ['冠笄'], '漂发': ['冠笄'],
  '剧本杀': ['出行','谒贵'], '密室': ['出行'], '桌游': ['出行','谒贵'],
  '露营': ['出行'], '爬山': ['出行','登山'], '徒步': ['出行','登山'],
  '野餐': ['出行'], '断联': ['解除','祈福'], '冷战': ['解除']
};
function _hlSceneAlias(sc) { return (HL_SCENE_ALIAS[sc] || []).slice(); }
/* R2349n（R77-P0-1）：与后端 _TERM_FAMILIES 同构——忌侧判定按同义族
 * 判（问搬家而忌栏有动土 → 判「宜忌都有」不判「宜」）。 */
var _HL_FAMILIES = [
  ['修造', '动土', '破土', '塞穴', '筑堤', '破屋坏垣', '竖柱', '上梁'],
  ['出行', '远行', '归家', '移徙', '入宅', '乘船', '登山'],
  ['开市', '立券', '纳财', '开仓', '交易', '置产'],
  ['嫁娶', '求嗣', '进人口', '纳采', '订盟'],
  ['上任', '求名', '入学'],
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
var _T2S = {
  '適':'适','嗎':'吗','麼':'么','會':'会','個':'个','這':'这','裡':'里','裏':'里',
  '對':'对','說':'说','話':'话','問':'问','聽':'听','來':'来','時':'时','現':'现',
  '點':'点','頭':'头','髮':'发','換':'换','簽':'签','約':'约','結':'结','證':'证',
  '領':'领','裝':'装','張':'张','業':'业','職':'职','學':'学','試':'试','遠':'远',
  '遊':'游','國':'国','門':'门','間':'间','錢':'钱','財':'财','買':'买','賣':'卖',
  '價':'价','醫':'医','藥':'药','養':'养','貓':'猫','魚':'鱼','鳥':'鸟','種':'种',
  '運':'运','氣':'气','勢':'势','曆':'历','歷':'历','黃':'黄','還':'还','見':'见',
  '長':'长','親':'亲','屬':'属','喪':'丧','動':'动','離':'离','準':'准','備':'备',
  '處':'处','幾':'几','緊':'紧','擇':'择','幹':'干','臺':'台','週':'周','禮':'礼','樣':'样',
  /* R229z：节日/农历问法繁体（与 services._T2S 同表，parity 钉扎） */
  '節':'节','婦':'妇','萬':'万','兒':'儿','誕':'诞','慶':'庆','陽':'阳','舊':'旧',
  '農':'农','陰':'阴','號':'号','餘':'余',
  /* 节气繁体（驚蟄/穀雨） */
  '驚':'惊','蟄':'蛰','穀':'谷','竈':'灶'
};
function _t2s(s) {
  return String(s || '').replace(/./g, function (ch) { return _T2S[ch] || ch; });
}
function _hlExtractScene(q) {
  var s = String(q || '');
  /* R229j：交替顺序约束——「X周末」复合词必须先于裸「本周/这周/周末」，
   * 否则「打算这周末…」被剥成「末…」；裸曜日（周五/礼拜天）殿后。 */
  s = s.replace(/(大后[天日]|大後天|后[天日]|後天|明晚|后晚|後晚|今晚|昨晚|今夜|明[天日]|明[儿兒]|明日|今[天日]|今日|昨[天日]|大前[天日]|前[天日]|过[两兩][天日]|这两天|这几天|那几天|那一天|那天|这一天|这天|最近|哪天|几时|几号|何时|啥时候|什么时候|(本周|这周|本週|這週|这週|這周)[一二三四五六日天]|(本|这|這|下)(周|週|礼拜|禮拜)末|本周|这周|本週|這週|这週|這周|周末|週末|下下(周|週|礼拜|禮拜)[一二三四五六日天]|下下(周|週|礼拜|禮拜)末|下下(周|週|礼拜|禮拜)|下(周|週|礼拜|禮拜)[一二三四五六日天]|下(周|週|礼拜|禮拜)|(周|週|礼拜|禮拜|星期)[一二三四五六日天]|一大早|凌晨|早上|上午|中午|下午|傍晚|晚上|夜里|白天|现在|当下|前年|去年|今年|明年|后年|後年|往年)/g, '');
  /* R229z：新日期词也要剥——节日/农历/绝对日期/月内相对/前后缀，
   * 否则「国庆节前一天摆摊」会残成「国庆节前一天摆摊」。 */
  s = s.replace(/(农历|農曆|阴历|陰曆|旧历|舊曆)?(闰|閏)?[正一二两三四五六七八九十冬腊\d]{1,2}月[初廿一二三四五六七八九十\d]{1,3}[日号]?/g, '');
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
  var _nxm = _s0.match(/下[个个]月(\d{1,2})[号日]?(?![线楼室幢座栋层院门])/);
  if (_nxm) {
    var bN = base || new Date();
    var _o1 = _pick([_mkd(bN.getFullYear(), bN.getMonth() + 1, +_nxm[1])]);
    return _o1 === null ? null : _o1 + _suf(_nxm.index + _nxm[0].length);
  }
  var _pm = _s0.match(/上[个个]月(\d{1,2})[号日]?(?![线楼室幢座栋层院门])/);
  if (_pm) {
    var bP = base || new Date();
    var _o2 = _pick([_mkd(bP.getFullYear(), bP.getMonth() - 1, +_pm[1])]);
    return _o2 === null ? null : _o2 + _suf(_pm.index + _pm[0].length);
  }
  var _tsm = _s0.match(/这[个个]月(\d{1,2})[号日]?(?![线楼室幢座栋层院门])/);
  if (_tsm) {
    var bT = base || new Date();
    var _o3 = _pick([_mkd(bT.getFullYear(), bT.getMonth(), +_tsm[1])]);
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
  var _bd = _s0.match(/(^|[^\d月\/\-])(\d{1,2})\s*[号日](?![\d日线楼室幢座栋层院门])/);
  if (_bd) {
    var bB = base || new Date();
    var _o7 = _pick([_mkd(bB.getFullYear(), bB.getMonth(), +_bd[2]),
                     _mkd(bB.getFullYear(), bB.getMonth() + 1, +_bd[2])]);
    return _o7 === null ? null : _o7 + _suf(_bd.index + _bd[0].length);
  }
  /* R229f：「本周X/这周X」此前无解析静默按今天判（同 R228r 类）。 */
  var mw = s.match(/(本周|这周|本週|這週|这週|這周)([一二三四五六日天])/);
  if (mw) {
    var wdw = _wdIdx(mw[2]);
    var bw = base || new Date();
    return wdw - ((bw.getDay() + 6) % 7);       /* 可负——本周已过的日子 */
  }
  /* R229y续：「下下周X/下下周末」——"下下周一"自身含"下周"，会被下面
   * 通配截胡差整 7 天。先接住：以「再下一个周一」为基准。 */
  if (/下下(周|週|礼拜|禮拜)末/.test(s)) {
    var bn0 = base || new Date();
    return (14 - ((bn0.getDay() + 6) % 7)) + 5; /* 再下周一 +5 */
  }
  var mn = s.match(/下下(周|週|礼拜|禮拜)([一二三四五六日天])/);
  if (mn) {
    var wdn = _wdIdx(mn[2]);
    var bn = base || new Date();
    return (14 - ((bn.getDay() + 6) % 7)) + wdn;
  }
  if (/下下(周|週|礼拜|禮拜)/.test(s)) {
    var bn2 = base || new Date();
    return 14 - ((bn2.getDay() + 6) % 7);         /* 「下下周」→ 再下周一 */
  }
  /* R229e：「下周末/下週末」必须先于「下周」通配——否则被吃成下周一，
   * 而用户说的是下周的周六。 */
  if (/下(周|週|礼拜|禮拜)末/.test(s)) {
    var b0 = base || new Date();
    return (7 - ((b0.getDay() + 6) % 7)) + 5;   /* 下个周一 +5 = 下周六 */
  }
  /* 下周X / 下礼拜X：以下个周一为基准的曜日偏移（对齐服务端口径）。 */
  var m = s.match(/下(周|週|礼拜|禮拜)([一二三四五六日天])/);
  if (m) {
    var wd = _wdIdx(m[2]);
    var b = base || new Date();
    var todayWd = (b.getDay() + 6) % 7;           /* 周一=0 */
    return (7 - todayWd) + wd;
  }
  if (/下(周|週|礼拜|禮拜)/.test(s)) {
    var b2 = base || new Date();
    return 7 - ((b2.getDay() + 6) % 7);           /* 「下周」→ 下个周一 */
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
      var _bc = new Date(bB2.getFullYear(), _meR.m - 1, _meR.d);
      if (_bc < _bd0) _bc = new Date(bB2.getFullYear() + 1, _meR.m - 1, _meR.d);
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
  return ((_HL.pastDay ? '这天已经过去啦，就当复盘看看——' : '') +
    /* R2349n（R77-P2-4）：补宾语——「这个黄历没直接提」主谓残缺。 */
    '这事黄历没直接提——' + (day || '今天') + '主推【' + (_yi.join('、') || '无') + '】' +
    (_ji.length ? '，忌【' + _ji.join('、') + '】' : '') +
    '；没在宜忌里的事照常安排不犯冲～想问具体的事就带上它，比如「适合搬家吗」。');
}
function _hlVerdictHtml(sc, yi, ji, YI_MAP, JI_MAP, day, conflict) {
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
    verdict = day + '适合' + sc + ' ✅ —— 宜项里就有【' + hitYi.join('、') + '】' + why;
  } else if (hitJi.length && !hitYi.length) {
    verdict = day + '不宜' + sc + ' 🚫 —— 忌项里写着【' + hitJi.join('、') + '】' + why;
  } else if (hitYi.length && hitJi.length) {
    /* R228c：补谓语——「今天搬家宜忌都有」不通，「今天搬家的宜忌都有」
     * 与兄弟分支「今天适合/不宜搬家」同构。 */
    verdict = day + sc + '的宜忌都有 —— 宜【' + hitYi.join('、') + '】但也忌【' + hitJi.join('、') + '】，想做就把节奏放稳、别赶大动作';
  } else {
    /* R228c：同句「黄历/老黄历」混用统一为「黄历」（全站功能名口径）。 */
    verdict = day + '黄历的宜忌里没有直接提到' + sc + ' —— 不是不支持，只是黄历' + day + '没为它背书（' +
      (yi.length ? '主推【' + yi.join('、') + '】' : day + '宜项不多') +
      /* R2349（R64-P2）：措辞统一「适合」口径——「宜分手」读感怪。 */
      '）；' + sc + '可照常安排，想要黄历背书可以翻后面几天挑适合' + sc + '的日子';
  }
  /* R233g（R44-P1-7）：医疗类问法（看病/手术/体检/医美→求医治病）
   * 判词尾部必带「听医生的」口径——黄历不背书医疗决策。 */
  var _MED = ['求医', '治病', '求医疗病', '开刀'];
  var _med = _MED.some(function (m) { return sc.indexOf(m) !== -1; }) ||
    aliases.some(function (a) { return _MED.indexOf(a) !== -1; });
  if (_med) verdict += '（看病这种事，医生说了算——黄历不作数哦。）';
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
/* R229z续9：节气词也走兜底（小满=吉祥物名不进；大雪/小雪/大寒/小寒
 * 天气歧义不进——与后端 _SOLAR_TERMS 同表）。 */
var _HL_COMPLEX_DATE = /农历|農曆|阴历|陰曆|旧历|舊曆|闰|閏|正月|冬月|腊月|臘月|除夕|春节|春節|大年初一|元宵|端午|七夕|中秋|重阳|重陽|腊八|臘八|清明|立春|雨水|惊蛰|驚蟄|春分|谷雨|穀雨|立夏|芒种|芒種|夏至|立秋|处暑|處暑|白露|秋分|寒露|霜降|立冬|冬至|大暑|小暑|元旦|新年|情人|植树|植樹|愚人|劳动|勞動|五一|青年|儿童|兒童|六一|建党|建黨|建军|建軍|教师|教師|国庆|國慶|万圣|萬聖|平安|圣诞|聖誕|跨年|母亲节|母親節|父亲节|父親節|感恩|中元|小年|双十一|雙十一|光棍|下个?月|上个?月|这个?月|本个?月|月底|月末|月初/;

/* 「问一嘴」无事项词时的中性提示（当日主推+引导）——提交主路径与
 * resolve_date 兜底复用。 */
function _hlShowNeutral() {
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
      fail('hlResult', '请先选一个日期～');
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
  var _offShown = _abs ? offset : null;
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
    html += '<div style="font-size:20px;font-weight:800;color:#7A5F33;">' + esc(j.date || dateStr) + '</div>';
    /* R230n（R25-1.3）：记下本卡实际展示的公历日——跨零点自刷新靠它
     * 判「这张卡是不是昨天的快照」。 */
    if (_hlBox) _hlBox.dataset.shownDate = j.date || dateStr;
    _HL.renderedOn = todayIso();   /* R2349k（R72-B1）：渲染日戳，隔夜重查用 */
    /* R228c：month_cn 本身已带「月」（后端 MONTH_CN 表生成时即带），
     * 再拼一个就成「八月月十九」——直接 month_cn+day_cn。
     * 注意：注释里别写「模块.文件」式点号串——probe_contract 会当字段读取。 */
    /* R229z续19：1900-01-31 前农历表无数据（月名/干支全空）——
     * 「农历  · 」空串残影换成直白说明。 */
    var _lunarTxt = (lunar.month_cn || '') + (lunar.day_cn || '');
    html += '<div style="font-size:13px;color:var(--secondary);margin-top:2px;">' +
      (_lunarTxt
        ? '农历 ' + esc(_lunarTxt) + ' · ' + esc(lunar.ganzhi_year_cn || '')
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
        return f === '月破' ? '月破日——大事缓一缓就好'
          : f === '四离' ? '四离日——节气前一天，宜收不宜开'
          : f === '四绝' ? '四绝日——立季前一天，大事留到后天'
          : f === '杨公忌' ? '杨公忌日——老传统提醒稳着点，小事照常' : f;
      }).join('、');
      /* R2349k（R72-C1）：「今天逢」写死——翻过去/未来日照样顶「今天」，
       * 跟 _dayWord 走。 */
      html += '<div class="hl-flag">🌙 ' + esc(_dayWord) + '逢' + esc(_flTxt) + '</div>';
    }
    if (cs && cs.message) html += '<div class="hl-csmsg">✨ ' + esc(cs.message) + '</div>';
    /* R2349k（R72-A2）：节日行——中秋节/立秋/母亲节这天值得说出来。 */
    if (j.festival && j.festival.length) {
      html += '<div class="hl-festival">🎉 ' + esc(_dayWord) + '是' +
        esc(j.festival.join('、')) + '</div>';
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
    if (_conflict.length) {
      html += '<div style="font-size:12px;color:var(--muted);margin-top:6px;">※ ' +
        esc(_conflict.join('、')) + ' 在宜忌两边打架——黄历自己都矛盾的日子，' +
        '这类事想做就把节奏放缓，不赶大动作</div>';
    }
    /* 场景 chips：点选高亮匹配宜项
     * R230q（R28-P3-12）：打印时整块隐藏——原先只藏 chip 按钮，
     * 「我打算：」「点一个场景…」两段说明成孤儿文字悬在纸上。 */
    var SCENES = ['搬家', '开业', '约会', '面试', '出行', '签约'];
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
      var _hJ = ji.filter(function (w) {
        return _als.some(function (a) {
          return w.indexOf(a) !== -1 || a.indexOf(w) !== -1; });
      });
      var ok = _hY.length && !_hJ.length;
      /* R229z续23（R10-#9）：选中态同步 aria-pressed——读屏能知道选了哪个
       * 场景；判定文案同时并进 aria-label（title 悬停键盘/读屏不可达，#21） */
      var _on = _HL.scene === s;
      var _hint = ok ? _dayWord + '适合' : _dayWord + '不宜';
      return '<button type="button" class="hl-scene' + (_on ? ' active' : '') +
        '" data-scene="' + esc(s) + '" aria-pressed="' + _on +
        '" aria-label="' + esc(s + '，' + _hint) + '" title="' + _hint + '">' +
        esc(s) + (ok ? ' ✓' : '') + '</button>';
    }).join('');
    html += '</div>';
    /* v4：显式结论——点选场景后卡内直接给一句人话答案，不再只靠 ✓ 自己猜 */
    if (_HL.scene) {
      html += _hlVerdictHtml(_HL.scene, yi, ji, YI_MAP, JI_MAP, _dayWord, _conflict);
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
          '——大事缓一缓再定就好</span>';
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
    /* R233w（R52-P3-9）：交节当日透明化——±15min 精度边界直接亮给用户。 */
    if (j.term_today) _jx.push('交节：' + j.term_today.name + ' ' +
      j.term_today.time);
    if (_jx.length) {
      html += '<div style="font-size:12px;color:var(--muted);margin-top:6px;">' +
        esc(_jx.join(' · ')) + '</div>';
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
    if (j.cross_ref && j.cross_ref.message) {
      html += '<div class="cross-ref"><span class="cross-ref-icon">⭐</span>' +
        esc(j.cross_ref.message) + '</div>';
    }
    html += tailHook('huangli');
    html += '<div style="font-size:12px;color:var(--muted);margin-top:12px;">黄历按传统历法规则计算，仅供娱乐，不构成决策依据——大事还是相信自己的判断 ✨</div>';
    /* R230d（R16-P2-6）：黄历卡没有 .card 容器，paint 的自动挂钮
     * 找不到宿主——手动挂「聊聊这件事」（其他五个视图都有）。 */
    html += '<button class="chat-entry" type="button" data-chat-entry ' +
      'aria-label="打开小满聊天，聊聊这件事">💬 聊聊这件事</button>';
    paint('hlResult', html);
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
            !_hlBoxG || _hlBoxG.dataset.shownDate !== _gsrc ||
            !Array.isArray(gj.good_days) || !gj.good_days.length) return;
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
            _tt = '宜：' + _gy.slice(0, 4).join('、');
            if (_gj.length) {
              _tt += '　忌：' + _gj.slice(0, 3).join('、');
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
          return '<button type="button" class="hl-daychip' +
            (_fl.length ? ' has-flag' : '') + '" data-hldate="' +
            esc(String(gd.date || '')) + '"' +
            (_tt ? ' title="' + esc(_tt) + '"' : '') + '>' +
            esc(lab) + '</button>';
        }).join('');
        /* R230v（R34-#8）：去重——重渲/重注窗口重叠时先清旧条，不叠双份。 */
        var _oldGd = box.parentNode && box.parentNode.querySelector('.hl-gooddays');
        if (_oldGd) _oldGd.remove();
        /* R2349l.7（R74-P2-a）：凶日排序沉底+窗口截 6——若被截部分里
         * 还有逢凶日，榜尾补一行说明，⚠ 标记不至于完全不可见。 */
        var _sunk = _days.slice(6).reduce(function (n, gd) {
          return n + ((gd.flags || []).length ? 1 : 0);
        }, 0);
        var tip = document.createElement('div');
        tip.className = 'hl-gooddays';
        /* R2349（R64-P2）：「近期宜分手」直译刺耳——换「适合」口径。 */
        tip.innerHTML = '<span class="hl-gooddays-label">近期适合' +
          esc(_gsc) + '：</span>' + chips +
          (_sunk ? '<span class="hl-gooddays-note">（另 ' + _sunk +
            ' 天逢凶日未列出）</span>' : '');
        if (box.nextSibling) box.parentNode.insertBefore(tip, box.nextSibling);
        else box.parentNode.appendChild(tip);
        tip.querySelectorAll('[data-hldate]').forEach(function (b) {
          b.addEventListener('click', function () {
            /* R230v（R34-#6）：吉日 chip 也走取最新排队，不再吞点。 */
            /* 点击时刻才换算偏移——跨零点不漂（R20-F3）。 */
            var pp = String(b.dataset.hldate || '').split('-');
            if (pp.length !== 3) return;
            var t = new Date(+pp[0], (+pp[1]) - 1, +pp[2]);
            var t0 = new Date(); t0.setHours(0, 0, 0, 0);
            doHuangli(Math.round((t - t0) / 86400000), true);
          });
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
      /* R230v（R34-#6）：在途不拦——问一嘴请求进取最新队列。 */
      var inp = document.getElementById('hlAskInput');
      var q = inp ? zwClean(inp.value) : '';   /* R230k */
      if (!q) {
        if (inp) inp.placeholder = '先输入想问的事，比如：今天适不适合面试';
        /* R230f续2（R16-P2-4）：placeholder 若已是这段文字则界面纹丝不动，
         * 加一张 toast 让空提交有可感反馈。 */
        showToast('先写一句想问的事再问我哦', 'info');
        return;
      }
      /* R230z（R36-P2-5）：足迹落库——记问题+当前显示日（日期词改写的
       * 分支会在跳转后由卡面日期自然对上）。 */
      /* R2349k（R72-B4）：足迹记两个日子——d 是被问的卡面日（chip 前缀
       * 用），a 是问的那一天（接续条「X天前你问了」的锚——此前锚在
       * d 上，正在翻未来日时「刚才问的」会算成「几天前」。 */
      var _hd0 = document.querySelector('#hlResult .hl-head div');
      var _ds0 = _hd0 ? _hd0.textContent.trim() : '';
      _hlAskLog(q, /^\d{4}-\d{2}-\d{2}$/.test(_ds0) ? _ds0 : todayIso(),
                todayIso());
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
        showToast('你的生日还没存——在首页「我的小档案」填一下，我就能翻那天的黄历', 'info');
        _HL.scene = '';
        _hlShowNeutral();
        return;
      }
      /* R229z：节日/农历等本地解不动的日期词——_hlDayOffset 返回 null 且
       * 词表命中时走 /api/huangli/resolve_date；解出翻页，解不出回退
       * 显示日（与既有 off=null 路径等价）。 */
      if (off == null && _HL_COMPLEX_DATE.test(q)) {
        api('/api/huangli/resolve_date?q=' + encodeURIComponent(q) +
            '&base=' + todayIso(),   /* R230l（R24-P3-4） */
            { silent: true }).then(function (r) {
          /* R2349k（R72-A3）：词命中但日子不存在（下个月31号）——
           * 如实提示，不回退显示日乱判。 */
          if (r && r.invalid) {
            showToast(r.invalid, 'warn');
            var _v0 = document.getElementById('hlVerdict');
            if (_v0) _v0.textContent = r.invalid;
            return;
          }
          var off2 = null;
          if (r && r.date) {
            var rp = r.date.split('-');
            var _t0 = new Date(); _t0.setHours(0, 0, 0, 0);
            off2 = Math.round((new Date(+rp[0], +rp[1] - 1, +rp[2]) - _t0) / 86400000);
          }
          _HL.scene = sc || '';
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
        return;
      }
      _HL.scene = sc;
      if (off != null) {
        _HL.keepSy = window.scrollY;
        doHuangli(off, false);
        return;
      }
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
    if (_tr && (_tr.querySelector('.ph-empty') || !_tr.innerHTML.trim())) {
      guardedCall('threads-load', function () {
        return _threadListHtml().then(function (h) {
          paint('threadResult', h ||
            '<div class="no-evidence">还没有研究线程——写个主题就能开一条～</div>');
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
  if (val('bswork')) guardedCall('bsload-' + key, function () { return entry.load(); }, null, true);
}

var _PH_OPEN_GEN = 0;   /* R233k：历史复看代际号 */

/* ── 初始化 ────────────────────────────────────────────────── */

function initViews() {
  document.querySelectorAll('.func-card').forEach(function (card) {
    card.addEventListener('click', function () {
      window.__lastFuncCard = card;   /* R228d：回首页时焦点归还这里 */
      showView(card.dataset.view);
    });
    // 卡片是可点区域，给键盘用户同等入口
    card.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        window.__lastFuncCard = card;
        showView(card.dataset.view);
      }
    });
  });
  /* R200b（US3）：顶层返回条 → 回首页（簇页/叶页通用） */
  var back = el('viewBack');
  if (back) back.addEventListener('click', function () { showView('home'); });
  /* R205b（用户反馈①）：最近解读侧边栏 开/收 */
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
  /* R219b（P0-4）：侧栏「我的解读」折叠段与计数刷新随历史记录功能删除。 */
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
  /* R2340：深浅色切换——aa↔dark↔legacy 轮转（legacy 是回滚主题）。 */
  var _tt = el('themeToggle');
  if (_tt) {
    var _ttIcon = function () {
      var _dk = uiTheme() === 'dark';
      _tt.textContent = _dk ? '☀️' : '🌙';
      _tt.setAttribute('aria-label',
        _dk ? '切回浅色模式' : '切换深色模式');
      /* R2349h（R69-P3-12）：状态进可访问树。 */
      _tt.setAttribute('aria-pressed', String(_dk));
    };
    _ttIcon();
    _tt.addEventListener('click', function () {
      applyTheme(uiTheme() === 'dark' ? 'aa' : 'dark');
      _ttIcon();
      showToast(uiTheme() === 'dark' ? '夜间模式开啦～看着不累眼睛' :
                '回到奶油白啦', 'info');
    });
  }
  /* R206b（US1）：聊天抽屉绑定。chatEntry 是动态按钮（结果区重绘），
   * 用委托绑到 document。 */
  document.addEventListener('click', function (e) {
    /* R230t（R33-P1-1）：.chat-entry 是样式类，换一批/AI点评也在用——
     * 委托判定改走 data-chat-entry，误伤才停止（实测点「换一批」
     * 会拉开聊天侧栏还自动发一条上下文消息）。 */
    if (e.target.closest && e.target.closest('[data-chat-entry]')) {
      /* R230v（R34-#11）：委托路径过同一把 chatSendBtn 锁——双击
       * 「聊聊这件事」不再双发气泡+双任务（_autoSendBusy 管函数体，
       * guardedCall 管与手发互斥）。 */
      guardedCall('chatSendBtn', function () {
        chatOpen();
        autoSendChatContext();
        return Promise.resolve();
      }, e);
    }
  });
  on('chatSendBtn', chatSend);
  /* R223b（E-304 P1）：空态话题 chip——点一下把问题填进输入框并直接发送。
   * 用事件委托绑在容器上（chatEmpty 会被 chatBubble 整块 remove）。 */
  var _emptyBox = document.getElementById('chatEmpty');
  if (_emptyBox) _emptyBox.addEventListener('click', function (ev) {
    var chip = ev.target.closest && ev.target.closest('.chat-chip');
    if (!chip || !chip.dataset || !chip.dataset.ask) return;
    var input2 = el('chatInput');
    if (input2) input2.value = chip.dataset.ask;
    guardedCall('chatSendBtn', chatSend, ev);   /* R230v（R34-#11） */
  });
  var ci = el('chatInput');
  /* R233r（R49-P3-1）：空发后提示语粘住——用户一开始打字就复位。 */
  if (ci) ci.addEventListener('input', function () {
    if (ci.placeholder === '先写点什么再发哦') ci.placeholder = '说说你的心情…';
  });
  if (ci) ci.addEventListener('keydown', function (e) {
    /* R230q：与 chatSendBtn 的 on() 点击同锁——连按 Enter 不再并发发消息 */
    if (e.key === 'Enter') guardedCall('chatSendBtn', chatSend, e);
  });
  /* R228q：移动键盘弹出会把侧栏输入框顶出可视区（visualViewport 收缩，
   * 但侧栏是 fixed 布局不跟随）——键盘开合时把输入框滚回视口内。
   * 只在聊天输入聚焦状态下生效；不支持 visualViewport 的环境静默跳过。
   * R2349m（R76-P0-2）：iOS 键盘只缩 visualViewport，fixed 侧栏锚在
   * 不变的 layout viewport——scrollIntoView 对 fixed 元素按构造无效。
   * 改为直接换算侧栏 bottom = 被键盘吃掉的高度。 */
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', function () {
      var inp = el('chatInput');
      var sb = document.querySelector('.recent-sidebar');
      if (!inp || document.activeElement !== inp || !sb ||
          !sb.classList.contains('open')) return;
      var vv = window.visualViewport;
      var eaten = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      /* 键盘弹出：侧栏底抬高到键盘上沿；收起：回落 0。 */
      sb.style.bottom = eaten > 60 ? eaten + 'px' : '';
      setTimeout(function () {
        inp.scrollIntoView({ block: 'end', inline: 'nearest' });
      }, 250);
    });
  }
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

  // 回车提交：查询类输入框都该支持（原实现只能点按钮）
  /* R230d（R16-P1-4）：补 tq/bswork/aguan/ayao/aname/aaddr1——这几个输入框
   * 此前按 Enter 无反应，只能伸手去点按钮。
   * R230q（R28-P1-1）：pair[1] 是与对应 on() 按钮共用的锁 key——
   * Enter 连打与连点同防重（bswork 无 on() 按钮，自占一键）。 */
  [['rq', 'searchBtn', doSearch], ['rq2', 'researchBtn', doResearch],
   ['cq', 'conceptBtn', doConcept],
   ['cwq', 'cwBtn', doCompareWorks], ['aaddr2', 'addrBtn', doAddr],
   ['tq', 'threadBtn', doThread],
   ['bswork', 'bswork', doBookStructure], ['aguan', 'addrBtn', doAddr],
   ['ayao', 'addrBtn', doAddr],
   ['aname', 'addrBtn', doAddr], ['aaddr1', 'addrBtn', doAddr]
  ].forEach(function (pair) {
    const node = el(pair[0]);
    if (node) {
      node.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
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
    // 口吻切换（US3）：只重渲染当前结果区，不重发请求——重发会让
    // /api/bazi 再往 history.db 写一行（用户数据不该被切换动作污染，
    // US3.3「已有数据不受影响」）。用 LAST_RESPONSE 缓存重画。
    const vbtn = e.target.closest('[data-voice]');
    if (vbtn) {
      setVoiceMode(vbtn.dataset.voice);
      rerenderVoice();
      return;
    }
    // 古籍引文树的三级折叠（005 US2）。事件委托——折叠件是动态生成的，
    // 且切换口吻会整块重画（rerenderVoice），逐个绑定处理器会漏。
    const cbtn = e.target.closest('[data-cite-toggle]');
    if (cbtn) {
      toggleCite(cbtn);
      return;
    }

    const workCard = e.target.closest('.work-card[data-work]');
    if (workCard) {
      searchByWork(workCard.dataset.work);
      return;
    }
    /* R230q（R28-P1-1b）：线程删除入口——先于 data-thread 判（删按钮
     * 与查看同卡片，避免冒泡误进详情）。 */
    const threadDel = e.target.closest('[data-thread-del]');
    if (threadDel) {
      deleteThread(threadDel.dataset.threadDel);
      return;
    }
    const threadBtn = e.target.closest('[data-thread]');
    if (threadBtn) {
      showThread(threadBtn.dataset.thread);
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
    };
    _lym.addEventListener('change', _lyTimeSync);
    _lyTimeSync();
  }
  on('lySubmit', doLiuyao);
  on('hlSubmit', doHuangli);
  on('qmSubmit', doQiming);
  on('thSubmit', doTaohua);
  on('trSubmit', doTarot);
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
          box.innerHTML = '<div class="tarot-album-count">已收集 <strong>' +
            cnt + '</strong> / ' + esc(String(cj.total)) +
            ' 张——多抽几签，把牌册点亮 ✨</div>' +
            '<div class="tarot-album-grid">' +
            cj.deck.map(function (n) {
              return '<div class="tarot-cell' + (got[n] ? ' got' : '') +
                '">' + esc(got[n] ? n : '？') + '</div>';
            }).join('') + '</div>';
        }).catch(function () {});
      });
    }
  })();
  on('hhSubmit', doHehun);
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
    'view-xingzuo': 'birthSubmit'
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
    try {
      var _rel = el('xzm_rel');
      var mj = await api('/api/xzmatch?a=' + encodeURIComponent(sa2.value) +
                         '&b=' + encodeURIComponent(sb2.value) +
                         (_rel && _rel.value
                          ? '&rel=' + encodeURIComponent(_rel.value) : ''));
      box.innerHTML = '<div class="hh-score" style="margin-top:0;">' +
        esc(mj.a) + '座 × ' + esc(mj.b) + '座 · 合拍指数 <strong>' +
        esc(String(mj.score)) + '</strong>/99 ' +
        '<span class="daily-lucky-word">' + esc(mj.label) + '</span></div>' +
        '<div style="margin-top:8px;color:var(--secondary);font-size:14px;">' +
        esc(mj.line) + '</div>' +
        '<div style="margin-top:8px;font-size:12px;color:var(--secondary);">' +
        '想更准？补个生辰试试八字合婚 →</div>';
    } catch (e) {
      box.innerHTML = '<div class="ph-empty" style="padding:12px;">' +
        esc((e && e.message) || '速配没跑出来，再点一次试试') + '</div>';
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
    /* R228c：失败态下静默 return 用户无感——给 toast 提示 */
    if (window.__lastDaily) downloadPoster(window.__lastDaily, 'daily');
    else showToast('今日运势还没出来，等它算好再分享～', 'warn');
  });
}

/* ── R230z（R36）：favorites 窄面接线 + 历史全品类 + 问一嘴足迹 ─────────
 * favorites API（/api/favorites + /api/user/prefs.favorites）后端一直在，
 * 本轮接两个窄入口：合婚「存这对」chips、起名「♡心水名单」——不复活
 * R208b 删掉的通用收藏面板。 */

var _favListInflight = null;
async function _favList() {
  /* R2348（R67-P2）：合婚/起名两个 favorites 渲染各调一次——冷启瀑布
   * 实测同秒两条重复 GET。合并在途请求（不是 memoize：收藏会增删，
   * 每次渲染要新读；但同一 tick 的并发调用共享一份）。 */
  if (_favListInflight) return _favListInflight;
  _favListInflight = (async function () {
    try {
      const j = await api('/api/user/prefs', { silent: true });
      return (j && j.favorites) || [];
    } catch (e) { return []; }
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
      return '<button type="button" class="fav-chip" data-hh-fav="' +
        esc(f.ref_id || '') + '">' + esc(f.title || '一对') + '</button>';
    }).join('');
}

function _hhFavFill(ref) {
  var p = String(ref || '').split('|');
  if (p.length < 10) return;
  var ids = ['hh_a_year', 'hh_a_month', 'hh_a_day', 'hh_a_hour', 'hh_a_gender',
             'hh_b_year', 'hh_b_month', 'hh_b_day', 'hh_b_hour', 'hh_b_gender'];
  ids.forEach(function (id, i) {
    var e = el(id);
    if (!e || p[i] === '' || p[i] == null) return;
    e.value = p[i];
    delete e.dataset.me;   /* chip 回填=用户主动行为，不算 profile 预填 */
  });
  var an = el('hh_a_name'), bn = el('hh_b_name');
  if (an && p[10]) an.value = p[10];
  if (bn && p[11]) bn.value = p[11];
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
    window.localStorage.setItem('hlask', JSON.stringify(list.slice(0, 12)));
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
        showToast(_dayPick(['收进心水名单啦','放进心水夹了～','这个名字归你了'], 'fav'), 'info');
        _qmFavsRender();
      })
      .catch(function (e) { showToast('没存上：' + e.message, 'error'); })
      .finally(function () { qf.dataset.inflight = ''; })
      .finally(function () { qf.disabled = false; });
    return;
  }
  var qd = t.closest('[data-qm-fav-del]');
  if (qd) {
    /* R233k（R45-§8）：裸 fetch 无超时/无 inflight，双击双发。 */
    if (qd.dataset.inflight === '1') return;
    qd.dataset.inflight = '1';
    api('/api/favorites/' + encodeURIComponent(qd.dataset.qmFavDel),
        { method: 'DELETE', silent: true })
      .then(function () { _qmFavsRender(); })
      .catch(function () { showToast('摘失败，稍后再试', 'warn'); })
      .finally(function () { qd.dataset.inflight = '0'; });
    return;
  }
  /* 测过的 CP chip → 回填表单并直接合婚 */
  var hc = t.closest('[data-hh-fav]');
  if (hc) { _hhFavFill(hc.dataset.hhFav); return; }
  /* 问一嘴足迹 chip → 把问题原样再问一遍（日期词按当下重算，
   * 比钉死那天更贴近用户意图） */
  var hq = t.closest('[data-hlask-q]');
  if (hq) {
    var _q = hq.dataset.hlaskQ || '';
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
  qiming: function (j) { return buildQimingResult(j); }
};
var _PH_TYPE_LABEL = { bazi: '命盘', taohua: '桃花', hehun: '合婚',
                       tarot: '塔罗', liuyao: '六爻', qiming: '起名' };

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
  _applyDaypart();
  initViews();
  initBazi();
  initReading();
  initDivination();
  _meFillAll();   /* R230y（R36-P1-4）：生日 profile 代入同人表单 */
  _chatChipsPersonalize();   /* R231g（R39-P2-3）：聊天空态 chips 个性化 */
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
  function _visitCount() {
    try {
      var v = String(localStorage.getItem('visits') || '').split(',')
        .filter(Boolean);
      var t = todayIso();
      if (v.indexOf(t) < 0) {
        v.push(t);
        if (v.length > 400) v = v.slice(-400);
        localStorage.setItem('visits', v.join(','));
      }
      return v.length;
    } catch (e) { return 0; }
  }
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
        (_mini
          ? _dayPick(['今天的礼物在上面——点开看看',
                      '今日包裹已就位，点这条拆',
                      '小礼物等着呢——点一下拆开'], 'revisit-mini')
          : _dayPick(['小满第 ' + _n + ' 次为你开铺，拆开看看今天的运',
                      '第 ' + _n + ' 次见面啦，今天也给你包了礼物',
                      '又来啦——第 ' + _n + ' 次开铺，今天的运在里面',
                      '第 ' + _n + ' 次重逢，今天的包裹热着呢'],
                     'revisit'));
    }
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
    _cov.addEventListener('click', _reveal);
    _cov.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); _reveal(); }
    });
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
  warmPoster();   /* R193b：空闲预热海报管线，消除首点冷启动长任务 */

  /* R230n（R25-1.2/1.3/2.1）：回访三件套——
   * 1) 跨零点自刷新：回前台或每 60s 检查浏览器日；变了则重跑
   *    loadDaily/renderCheckin，已展示的「昨天」黄历/星座卡按今天重查
   *    （用户自选日期的结果不动——只有显示日恰是旧今天才换）。
   * 2) checkin 跨 tab 同步：storage 事件命中 checkin:* 即重渲。 */
  var _lastDay = todayIso();
  /* R232a（R40-R1）：dailyRevealed/checkin GC 原来只挂在打卡点击里——
   * 只拆信封不打卡的用户键无限累积。启动时跑一次兜底。 */
  try {
    var _gc0 = _isoShift(_lastDay, -90);
    for (var _gi = window.localStorage.length - 1; _gi >= 0; _gi--) {
      var _gk = window.localStorage.key(_gi);
      /* R2349（R65-P2-4）：checkinCeleb:N:YYYY-MM-DD 此前不在 GC——
       * 里程碑标记虽轻但白攒；按尾段日期同一 90 天口径收。 */
      var _gkd = _gk && _gk.indexOf('checkinCeleb:') === 0
        ? _gk.slice(_gk.lastIndexOf(':') + 1) : null;
      if (_gk && ((_gk.indexOf('checkin:') === 0 && _gk.slice(8) < _gc0) ||
          (_gk.indexOf('dailyRevealed:') === 0 && _gk.slice(14) < _gc0) ||
          (_gkd && _gkd < _gc0))) {
        window.localStorage.removeItem(_gk);
      }
    }
    /* R2345（R63-P2-5）：c26bdce 时代 chat sid/记录放 localStorage，
     * R230n 迁到 sessionStorage 后旧键无人清——启动兜底一并收掉。 */
    ['chatSessionId', 'chatTranscript'].forEach(function (k) {
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
  setInterval(function () { _applyDaypart(); _onDayFlip(); }, 60000);
  window.addEventListener('storage', function (e) {
    if (!e || !e.key) return;
    if (e.key.indexOf('checkin:') === 0) {
      renderCheckin(todayIso());
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
    /* R230t（R31-P2-2）：口吻/皮肤跨 tab 同步——别处改了这里就地
     * 生效，不再要刷新才跟上。 */
    if (e.key === VOICE_KEY) { rerenderVoice(); return; }
    if (e.key === THEME_KEY) { applyTheme(uiTheme()); }
    /* R232a（R40-R2）：生日档案跨 tab 同步——A tab 改了生日，
     * B tab 表单下次进页才跟太迟，就地重填未手改字段。 */
    if (e.key === 'me' || e.key === 'me:partner') { _meFillAll(); }
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
                     birth: 'xingzuo' };
      if (_alias[_vp]) _vp = _alias[_vp];
      var _vpOk = (_vp === 'home') ||
        (document.getElementById('view-' + _vp) &&
         document.querySelector('.func-card[data-view="' + _vp + '"]'));
      if (_vpOk) {
        /* R233n（R47-Top5-1）：合婚邀请链落地——?view=hehun&ay&am&ad
         * &ah&ag&an 把发起人的盘预填进 A 侧，受邀者只需填自己。
         * R2349（R65-P2-1）：剥参后 F5 预填静默丢——值存 sessionStorage
         *（tab 级，关窗即焚，不进历史/书签），刷新后从这儿回灌。 */
        var _qsAll = new URLSearchParams(location.search);
        var _invA = _qsAll.get('ay');
        if (_vp === 'hehun' && !_invA) {
          try {
            var _sv = sessionStorage.getItem('hhInvite');
            if (_sv) _qsAll = new URLSearchParams(_sv);
          } catch (eSS) {}
          _invA = _qsAll.get('ay');
        }
        if (_vp === 'hehun' && _invA) {
          [['ay','hh_a_year'],['am','hh_a_month'],['ad','hh_a_day'],
           ['ah','hh_a_hour'],['ag','hh_a_gender'],['an','hh_a_name']
          ].forEach(function (p) {
            var v = _qsAll.get(p[0]), elx = document.getElementById(p[1]);
            /* 不置 data-me——非空值本身就不被 _meFill 覆盖（置 1 反而
             * 放行：受邀者自己的档案会盖掉发起人数据）。
             * R233r（R50-#17）：时辰留空时也要把默认值清成空——
             * 「未知时辰」比静默按 10 点算诚实。 */
            if (elx && v != null &&
                (v !== '' || elx.tagName !== 'SELECT')) {
              elx.value = v;
              /* R2343：邀请值免疫档案回填（meFill 现在会盖默认值） */
              elx.dataset.invite = '1';
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
          ['hh_a_year','hh_a_month','hh_a_day','hh_a_hour','hh_a_gender',
           'hh_a_name'].forEach(function (_id) {
            var _ae = document.getElementById(_id);
            if (_ae) _ae.addEventListener('input', function () {
              window.__hhInviteMode = false;
            }, { once: true });
          });
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
              '&an=' + encodeURIComponent(_qsAll.get('an') || ''));
          } catch (eSS2) {}
          try {
            history.replaceState(null, '',
              location.pathname + '?view=hehun');
          } catch (e5) {}
          setTimeout(function () {
            showToast('TA 的信息已经填好啦——轮到你了 💕');
            var _by = document.getElementById('hh_b_year');
            if (_by) { try { _by.focus(); } catch (e) {} }
          }, 350);
        }
        var _hold = window.__suppressPush;
        window.__suppressPush = true;
        try { showView(_vp); } finally { window.__suppressPush = _hold; }
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
                _vpRaw === 'checkin-week') {
              var _dc = document.getElementById('dailyCard');
              if (_dc) _dc.scrollIntoView({ behavior: _rmBehavior(), block: 'start' });
            } else if (_vpRaw === 'birth') {
              var _bd = document.getElementById('birthDrawer');
              if (_bd) _bd.open = true;
            }
          }, 300);
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
          showToast('日签每天更新——点第一张卡看今天的 ✨', 'ok');
        }, 1500);
      }
    } catch (e) {}
    try {
      var _qs = new URLSearchParams(location.search);
      if (_qs.get('from') === 'share') {
        /* R2349l（R73-P1-13）：接力承接按来源视图说话——
         * 「TA 抽了塔罗，看看你的」比通用一句更有接力感。 */
        var _sv = _qs.get('view') || '';
        var _relay = {
          tarot: '朋友在晒她抽的塔罗牌——点下面抽你的 🃏',
          daily: '朋友在晒今日运势——看看你今天什么运 ✨',
          hehun: '朋友在晒合婚指数——你和 TA 也来一对 💕',
          bazi: '朋友在晒她的八字盘——你的盘也排一排 🔮',
          xingzuo: '朋友在晒今日星座运——看看你的宫今天说啥 ⭐',
          qiming: '朋友在晒起的好名字——你的名字也测测 🌸',
          taohua: '朋友在晒桃花信号——你的桃花今天啥情况 🌺',
          liuyao: '朋友摇了一卦——心里有件事也来摇一爻 🎲',
        };
        var _rt = _relay[_sv] || '朋友在晒她的运势——来测测你的 ✨';
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
    try {
      _from = new URLSearchParams(location.search).get('from');
    } catch (e) {}
    var _txtEl = bar.querySelector('.welcome-txt');
    if (_txtEl && _from === 'share') {
      /* R2349l（R73-P1-13）：新客落地也按接力视图说话。 */
      var _sv2 = null;
      try { _sv2 = new URLSearchParams(location.search).get('view'); } catch (e) {}
      var _relayBar = {
        tarot: '朋友抽了塔罗牌喊你接力——点「塔罗占卜」抽你的 🃏',
        daily: '朋友在晒今日运势——日签卡就在上面，看看你的 ✨',
        hehun: '朋友约你合婚——点「八字合婚」测你俩的合拍度 💕',
      };
      _txtEl.textContent = _relayBar[_sv2] ||
        '朋友在晒她的运势，来测测你的——点一张卡就能开始 ✨';
    } else if (_txtEl && _from === 'invite') {
      _txtEl.textContent = 'TA 约你来合婚——填好你的生日就能对上盘 💕';
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

/* ── R213b：微交互特效（点击涟漪 + 星星迸发 / 滑动拖尾 / 卡片入场）──
 * 纪律：全部只动 transform/opacity（check_plain_first 判据 2 门柱安全）；
 * prefers-reduced-motion 下整体停用。 */
(function () {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  /* 点击涟漪 + 星星迸发 */
  document.addEventListener('click', function (e) {
    /* R233k（R45-§1）：涟漪白名单收窄到真交互元素——原 list 含 .card
     * 兜底，点纯文本/空白处也放烟花（每次 ~7 个一次性 DOM 节点，
     * 还制造「可点假象」）。点到非交互区直接不放。 */
    var host = e.target.closest(
      'button, .btn, .func-card, #dailyCover, .work-card, .chat-entry,' +
      '.hl-chip, .hl-scene, .hl-daychip, .hl-week-cell, .checkin-opt,' +
      '.rtab, .chat-chip, .xz-chip, .qm-style-chip, .mode-btn, .fav-chip,' +
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
    for (var i = 0; i < 6; i++) {
      var s = document.createElement('span');
      s.className = 'fx-spark';
      s.style.left = x + 'px'; s.style.top = y + 'px';
      var ang = Math.random() * Math.PI * 2, dist = 24 + Math.random() * 30;
      s.style.setProperty('--dx', Math.cos(ang) * dist + 'px');
      s.style.setProperty('--dy', Math.sin(ang) * dist - 18 + 'px');
      s.style.animationDelay = (i * 30) + 'ms';
      document.body.appendChild(s);
      setTimeout(function (n) { return function () { n.remove(); }; }(s), 700 + i * 30);
    }
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
/* R233j（R46-P1）：与 copy_bank.json checkin.feedback 对齐。
 * R2349g（R68-P2）：此前「对齐」注释在说谎——json 缺 4 签+default，
 * 已补齐（options/feedback 全 9 池）。前端这份仍是唯一消费方。 */
const CHECKIN_FEEDBACK = {
  '开运蛋': ['今天这个运简直像开了挂，冲鸭！', '好运来敲门，接住了别撒手！', '哇这个运，今天走路都带风～', '恭喜抽到隐藏款好运！', '好运正在派送中，今天请保持微笑收货～', '开运蛋孵化成功，今天就是你的幸运日本日！'],
  '吃瓜运': ['瓜运当头，记得带好小板凳前排围观！', '今天的瓜管够，吃瓜吃到撑～', '前方瓜田已备好，快来蹲！', '今日瓜源充足，放心吃～', '瓜田守护者就是你，今天的瓜又大又甜～', '吃瓜群众已就位，精彩剧情马上开场！'],
  '摸鱼运': ['摸鱼运爆棚，快乐一下不过分！', '摸鱼时长建议不超过15分钟哦～', '今日摸鱼许可证已签发，适度摸～', '摸鱼有理，偷懒无罪，今天你最大～', '摸鱼搭子已上线，劳逸结合才是真谛～', '摸鱼运加持，记得摸完鱼把正事也收个尾～'],
  '破水逆运': ['霉运走开，今天就是好运本运！', '破水逆运！诸事皆宜的一天开始了～', '水逆已被小满击退，今天顺顺顺！', '退退退！水逆已被赶走，好运来～', '水逆退散符已生效，今天横着走都没事～', '霉运清零成功，接下来都是上坡路！'],
  '暴富签': ['暴富签已签收，财神今天站你这边！', '今天的你是被钱眷顾的体质，大胆冲～', '暴富签生效中——先定一个小目标！', '财运雷达全开，今天的羊毛记得薅～', '今天的理财灵感特别灵，记下来！', '暴富签加持，偏财正财都向你靠拢～'],
  '甜甜运': ['甜甜运已加载，今天的糖度超标！', '今天的空气都是蜜桃味的～', '甜甜运在线，笑一下好运加倍～', '今天是被人间温柔包围的一天～', '甜甜运送达：有人正在偷偷想你～', '甜系 buff 已挂，今天甜度管够～'],
  '上岸运': ['上岸运满格——目标已经在向你招手！', '今天离上岸又近了一步，稳住！', '上岸运护航，该背的背该做的做～', '岸就在前方，今天别停！', '上岸签加持，努力会被看见的～', '今天做的每道题都在铺路，上岸稳了～'],
  '顺顺签': ['顺顺签生效——今天一路绿灯！', '今天主打一个事事顺遂～', '顺顺签到手，水逆什么的都不存在～', '今天的节奏刚好，顺势而行就行～', '顺顺签保佑：想要的都在路上～', '今天宜顺水推舟，忌跟自己较劲～'],
  /* 兜底：存档里的旧签名轮换出池后仍可读回执 */
  '_default': ['这个签收好了，今天的运归你管～', '好运已领取，今天的能量满格！', '签已到手，今天的日子你做主～']
};
/* R230y（R36-P1-3）：打卡沉淀——checkin:* 键保留最近 90 天，
 * 渲染连续天数 + 近 7 天点阵 + 「昨天你选了X」召回。 */
function _checkinAll() {
  var set = {};
  try {
    for (var i = 0; i < window.localStorage.length; i++) {
      var k = window.localStorage.key(i);
      if (k && k.indexOf('checkin:') === 0) {
        set[String(k).slice(8)] = window.localStorage.getItem(k);
      }
    }
  } catch (e) {}
  return set;
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
  const opts = _todays.map(function (o) {
    return '<button type="button" class="checkin-opt' +
      (saved === o ? ' picked' : '') + '" data-opt="' + o + '" ' +
      'aria-pressed="' + (saved === o) + '">' + o + '</button>';
  }).join('');
  /* R229z续23（R10-#17）：选项组补 role=group + 问题文本锚点，
   * 反馈区 aria-live——选完有朗读回执。 */
  var _meta = '';
  if (_streak >= 2) {
    _meta += '已连续 ' + _streak + ' 天打卡';
    if (_streak === 3) _meta += ' · 小满贯开头啦';
    else if (_streak === 7) _meta += ' · 整一周，仪式感拿捏';
    else if (_streak >= 30) _meta += ' · 满月级选手';
    else if (_streak >= 14) _meta += ' · 半月不断';
    /* R39-P2-4：里程碑之间补倒计时——4→7、8→14 的空白带不再无目标 */
    if (!/小满贯|整一周|半月不断|满月级/.test(_meta)) {
      var _mile = [[3, '小满贯'], [7, '整一周'], [14, '半月不断'], [30, '满月级选手']];
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
    /* R39-P0-3：断签温柔召回——历史打过卡但昨天空 → 接住而不是沉默。 */
    _meta += '歇了几天也没关系，今天重新开张就算数 🌱';
  }
  box.innerHTML = '<div class="checkin-q" id="checkinQ">' +
    /* R2349g（R68-P1-1）：打卡问句 3→6。 */
    esc(_dayPick(['挑一个今天的好运搭子：', '今天的运，你挑哪款：',
                  '选一个接住今天的好运：', '今天想要哪张签：',
                  '抽一个陪你过今天：', '今天的幸运签是哪一个：'], 'ckq')) + ' ' +
    '<span class="checkin-dots" aria-hidden="true">' + _dots + '</span>' +
    (_meta ? '<span class="checkin-meta">' + _meta + '</span>' : '') + '</div>' +
    '<div class="checkin-opts" role="group" aria-labelledby="checkinQ">' + opts + '</div>' +
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
    '<div class="checkin-fx" id="checkinFx" aria-live="polite">' +
    (saved ? pickCheckinFeedback(saved, dateKey) : '') + '</div>' +
    /* R233p（R47-P2）：签册——存量 checkin:* 渲成可回看的迷你签墙
     * （details 懒渲染，点开才算 DOM；集齐感是小红书留存钩子）。 */
    (Object.keys(_ckAll).length ?
      '<details class="ck-album"><summary>📒 看看我的签册' +
      '（' + Object.keys(_ckAll).length + '）</summary>' +
      '<div class="ck-album-body" id="checkinAlbum"></div></details>' : '');
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
  var _cks = box.querySelector('#checkinShare');
  if (_cks) _cks.addEventListener('click', function () {
    var _p = downloadPoster({ streak: _streak, pick: saved }, 'checkin');
    if (_p && _p.catch) _p.catch(function () {});
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
  if (!box.dataset.bound) {
    box.dataset.bound = '1';
    box.addEventListener('click', function (e) {
      const btn = e.target.closest('.checkin-opt');
      if (!btn || !dateKey) return;
      /* R230n（R25-P2-1）：dateKey 是渲染时刻闭包——挂过零点的陈旧 tab
       * 绑定着昨天，点击会把「昨天」写进去、清理循环再把「今天」误删。
       * 点击时重算今天：变了就先整卡重渲成今天，再接着写今日键。
       * 注意：重渲后原按钮已脱离 DOM，picked 态按 opt 在新按钮上重标。 */
      const opt = btn.dataset.opt;
      var _today = todayIso();
      if (_today && dateKey !== _today) {
        dateKey = _today;
        renderCheckin(_today);
      }
      /* R230q（R28-P3-7）：先落盘再标 picked——原先 catch 后仍无条件
       * 打勾，写失败也显示「已打卡」静默丢数据（隐私模式/quota）。 */
      try {
        window.localStorage.setItem('checkin:' + dateKey, opt);
        /* R230j（R22-P3-2）：checkin:* 清理收口。
         * R230y（R36-P1-3）：连签是留客钩子——不再写今日删昨日，
         * 改为保留最近 90 天，超过才清。 */
        var _cutoff = 'checkin:' + _isoShift(dateKey, -90);
        var _cutoff2 = 'dailyRevealed:' + _isoShift(dateKey, -90);
        for (var _ci = window.localStorage.length - 1; _ci >= 0; _ci--) {
          var _ck = window.localStorage.key(_ci);
          /* R39-P3-1：dailyRevealed:* 此前无 GC，每年 365 个废键——
           * 与 checkin:* 同一 90 天收口。 */
          /* R2349（R65-P2-4）：checkinCeleb 同收（尾段是日期）。 */
          var _ckd = _ck && _ck.indexOf('checkinCeleb:') === 0
            ? 'checkinCeleb:' + _ck.slice(_ck.lastIndexOf(':') + 1) : null;
          if (_ck && ((_ck.indexOf('checkin:') === 0 && _ck < _cutoff) ||
              (_ck.indexOf('dailyRevealed:') === 0 && _ck < _cutoff2) ||
              (_ckd && _ckd < 'checkinCeleb:' +
                _isoShift(dateKey, -90)))) {
            window.localStorage.removeItem(_ck);
          }
        }
      } catch (e2) {
        showToast('这次打卡没存上（存储不可用）', 'warn');
        return;
      }
      /* R230y：整卡重渲——picked 态、连签天数、点阵、反馈一次同步
       * （原手改 class/textContent 会让新打卡的连签数滞后到下次渲染） */
      renderCheckin(dateKey);
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
        var _mk = 'checkinCeleb:' + _ns + ':' + dateKey;
        if ([3, 7, 14, 30].indexOf(_ns) >= 0 &&
            !localStorage.getItem(_mk)) {
          localStorage.setItem(_mk, '1');
          _checkinCelebrate(_ns, opt);
        }
      } catch (e3) {}
    });
  }
}
/* R231h：连签里程碑卡——轻量模态，标题+一句+分享图按钮。 */
function _checkinCelebrate(streak, opt) {
  /* R2349g（R68-P2）：里程碑文案 1→3 句池按日轮换——连打多年不再
   * 只见同一句。 */
  var _MILES = {
    3: ['小满贯开头啦', '三天连成线啦', '三连达成，好兆头'],
    7: ['整一周，仪式感拿捏', '七连达成，习惯上身', '一周不断，很可以'],
    14: ['半月不断，稳稳的', '十四天连签，坚持发光', '半个月啦，厉害'],
    30: ['满月级选手，了不起', '三十天连签，传说级别', '满月达成，膜拜']
  };
  var bd = document.createElement('div');
  bd.className = 'celeb-backdrop';
  bd.innerHTML =
    '<div class="celeb-card" role="dialog" aria-modal="true" aria-label="连签里程碑">' +
    '<img src="/static/cream/poster-mascot.png" alt="" class="celeb-img">' +
    '<div class="celeb-title">连续 ' + streak + ' 天打卡达成 🎉</div>' +
    '<div class="celeb-sub">' + esc(_dayPick(
      _MILES[streak] || [''], 'mile|' + streak)) +
    '——记得明天也来</div>' +
    '<div class="celeb-row">' +
    '<button type="button" class="celeb-share">📸 晒一下</button>' +
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
    var back = (_trig && _trig.isConnected) ? _trig :
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
    var j = JSON.parse(window.localStorage.getItem(key) || 'null');
    return (j && typeof j === 'object') ? j : null;
  } catch (e) { return null; }
}
function _meSave(key, rec) {
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
  try {
    window.localStorage.setItem(key, JSON.stringify(
      Object.assign(old, rec)));
  } catch (e) {
    /* R2345（R63-P2-4）：checkin 写坏有 toast——me 是同原则更重的
     * 字段（生辰），写失败不能再静默。 */
    try { showToast('档案没存上——再试一次看看', 'warn'); } catch (e3) {}
  }
  /* R2343（R59-gap4）：同页写入不触发 storage 事件——昵称存完立刻
   * 刷新空态招呼/档案条，改完不用刷新就看到名字。 */
  try { _chatChipsPersonalize(); _renderMeStrip(); } catch (e2) {}
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
     * 字段带 data-invite，跳过。 */
    if (e.dataset.invite === '1') return;
    var _untouched = (e.tagName === 'SELECT') ? (e.selectedIndex <= 0)
      : (e.value === '' || e.value === e.defaultValue);
    if (_untouched || e.dataset.me === '1') {
      e.value = String(v);
      e.dataset.me = '1';
    }
  });
}
function _meFillAll() {
  _meFill('me', { y: 'year', m: 'month', d: 'day', h: 'hour', g: 'gender' });
  _meFill('me', { y: 'b_year', m: 'b_month', d: 'b_day', h: 'b_hour', g: 'b_gender', n: 'b_nick' });
  _meFill('me', { y: 'th_year', m: 'th_month', d: 'th_day', h: 'th_hour', g: 'th_gender' });
  /* R2348（R66-P2）：邀请链落地时受邀者=B 侧=本人——档案源要翻成 me
   * （原写死 me:partner，受邀者存的伴侣档多半就是发起人自己→两侧同盘）。 */
  if (window.__hhInviteMode) {
    _meFill('me', { y: 'hh_b_year', m: 'hh_b_month', d: 'hh_b_day', h: 'hh_b_hour', g: 'hh_b_gender' });
  } else {
    _meFill('me', { y: 'hh_a_year', m: 'hh_a_month', d: 'hh_a_day', h: 'hh_a_hour', g: 'hh_a_gender' });
    _meFill('me:partner', { y: 'hh_b_year', m: 'hh_b_month', d: 'hh_b_day', h: 'hh_b_hour', g: 'hh_b_gender' });
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
  if (_hi && me && me.n) _hi.textContent = me.n + '，我是小满 ✨';
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
}
/* R231g（R39-P1-4）：装到桌面提示——beforeinstallprompt 只在可装
 * 环境才触发（iOS Safari 不发此事件，天然不出现）。7 天内关过不再烦。 */
var _deferredInstall = null;
window.addEventListener('beforeinstallprompt', function (e) {
  e.preventDefault();
  _deferredInstall = e;
  try { _renderInstallTip(); } catch (e2) {}
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
    var _isSafari = /Safari/i.test(navigator.userAgent) &&
      !/CriOS|FxiOS|EdgiOS|MicroMessenger|QQ/i.test(navigator.userAgent);
    bar.innerHTML = '<span>🏠 ' +
      (_wx ? '点右上「···」→「在 Safari 打开」，再点分享→加到主屏幕'
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
    if (e.target && e.target.dataset && e.target.dataset.me) {
      delete e.target.dataset.me;
    }
  }, true);
});
/* R233p：签墙渲染——最近 21 个打卡日倒序，每格 M/D + 签面，
 * 点击格 toast 当日反馈句。 */
function _renderCheckinAlbum(dateKey) {
  var host = document.getElementById('checkinAlbum');
  if (!host) return;
  var all = _checkinAll();
  var days = Object.keys(all).sort().slice(-21).reverse();
  if (!days.length) {
    host.innerHTML = '<div class="ck-album-empty">签册还空着——抽一签就开张</div>';
    return;
  }
  var html = '<div class="ck-album-grid" role="list">';
  days.forEach(function (dk) {
    var opt = all[dk] || '';
    var pp = String(dk).split('-');
    var fb = pickCheckinFeedback(opt, dk);
    /* R2349h（R69-P1-4）：role=listitem 会把原生 button 语义吃掉——
     * SR 只报「列表项」不报可激活。格仍由父级 role=list 承载语义。 */
    html += '<button type="button" class="ck-album-cell" ' +
      'data-fb="' + esc(fb) + '" title="' + esc(dk) + '　' + esc(fb) + '">' +
      '<i>' + esc(pp[1] || '') + '/' + esc(pp[2] || '') + '</i>' +
      '<b>' + esc(opt) + '</b></button>';
  });
  host.innerHTML = html + '</div>';
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
    if (m && _ZHI_ANIMAL[m[2]]) return '你是属' + _ZHI_ANIMAL[m[2]] + '的呀——这张小卡就是你的底色。';
  } catch (e) { /* 兜底走通用句 */ }
  return '这是你的生辰底色——展开可以看细节哦。';
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
      throw new Error(m);
    }
    return r.json();
  }
  async function loadPaipanHistory() {
    const listEl = document.getElementById('historyList');
    if (!listEl) return;
    const detailEl = document.getElementById('historyDetail');
    if (detailEl) { detailEl.hidden = true; detailEl.innerHTML = ''; }
    listEl.innerHTML = '<div class="ph-empty">加载中…</div>';
    try {
      const j = await phFetch('/api/paipan/history?limit=50');
      if (!j.items || !j.items.length) {
        listEl.innerHTML = '<div class="ph-empty">还没有占卜记录——命盘、桃花、合婚、塔罗、六爻、起名都会收在这里 ✨</div>';
        return;
      }
      listEl.innerHTML = j.items.map(function (it) {
        const ts = (it.ts || '').replace('T', ' ');
        const q = it.question ? '<span class="ph-q">问：' + esc(it.question) + '</span>' : '';
        /* R230z（R36-P1-1）：品类徽标——历史不再只收命盘 */
        /* R2349j（R71-P2）：未知 type 不原值上屏（技术字段名出戏）。 */
        const tLabel = _PH_TYPE_LABEL[it.type] || '记录';
        const render = (it.result_summary && it.result_summary.paipan_render) || '';
        /* R230a-44（R15-P3）：it.id 当前恒为 int，但多行拼接模式逃过单行
         * innerHTML 闸——将来字符串列入同一模式即成洞，先按 esc 纪律统一。 */
        return '<div class="ph-item" data-id="' + esc(String(it.id)) + '">' +
          '<div class="ph-head"><span class="ph-type ph-t-' + esc(it.type || 'bazi') + '">' +
          esc(tLabel) + '</span>' +
          '<span class="ph-name">' + esc(it.name || ('记录 #' + it.id)) + '</span>' +
          '<span class="ph-ts">' + esc(ts) + '</span></div>' + q +
          '<div class="ph-render">' + esc(render) + '</div>' +
          '<div class="ph-actions"><button type="button" class="ghost ph-open">查看</button>' +
          '<button type="button" class="ghost ph-del">删除</button></div></div>';
      }).join('');
    } catch (e) {
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
      try {
        await phFetch('/api/paipan/history/' + id, { method: 'DELETE' });
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
      catch (e) { showToast('删除失败：' + e.message, 'error'); }
      finally { tg.dataset.inflight = '0'; }
      return;
    }
    if (item && tg.classList.contains('ph-open')) {
      const id = item.getAttribute('data-id');
      /* R233k（R45-P2）：连点两条历史并发取详情，后到覆盖先到——
       * 代际号丢弃过期响应（_XZ_GEN 先例）。 */
      var _g = ++_PH_OPEN_GEN;
      try {
        const rec = await phFetch('/api/paipan/history/' + id);
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
          detailEl.insertAdjacentHTML('afterbegin',
            (_meta.length
              ? '<div class="ph-meta">' + _meta.join(' · ') + '</div>' : '') +
            '<button class="ghost fav-btn ph-share" type="button" ' +
            'id="phShareBtn" title="生成分享图">📸 分享这张图</button>');
          var _psb = detailEl.querySelector('#phShareBtn');
          if (_psb) _psb.addEventListener('click', function () {
            try {
              var _p = downloadPoster(rec.result || {}, _type);
              if (_p && _p.catch) _p.catch(function (e) {
                showToast('分享图生成失败：' + (e && e.message || '稍后再试'), 'warn');
              });
            } catch (e) {
              showToast('分享图生成失败：' + (e && e.message || '稍后再试'), 'warn');
            }
          });
          detailEl.hidden = false;
          detailEl.scrollIntoView({ behavior: _rmBehavior() });
        }
      } catch (e) {
        showToast('读取失败：' + e.message, 'error');
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
        var hv = document.getElementById('view-history');
        if (hv && hv.classList.contains('active')) loadPaipanHistory();
      };
    }
  } catch (e) {}
  function phBind() {
    const card = document.querySelector('.func-card[data-view="history"]');
    if (card) card.addEventListener('click', function () { setTimeout(loadPaipanHistory, 0); });
    /* R230t（R33-P3-5/6）：刷新/导出无锁——双击各弹一遍。 */
    var _phLast = { rf: 0, ex: 0 };
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
      window.open('/api/paipan/history/export', '_blank');
    });
    /* R231a（R36-P3-3）：备份我的数据 = 台账全量 JSON + 浏览器侧键
     * （打卡/me 双档/问一嘴足迹/主题/口吻）。换设备一键带走。 */
    var _exj = document.getElementById('historyExportJson');
    if (_exj) _exj.addEventListener('click', async function () {
      try {
        const j = await phFetch('/api/paipan/history/export_json');
        var local = {};
        /* R39-P3-1：dailyRevealed/visits 收进备份白名单——换机不丢
         * 连拆记录与「第 N 次开铺」计数。 */
        /* R232a（R40-R3）：welcomed/installTipDismissed 补进白名单——
         * 换机后不再重见新手引导与安装提示。 */
        ['checkin:', 'dailyRevealed:', 'me', 'me:partner', 'hlask', 'visits',
         'welcomed', 'installTipDismissed'].forEach(function (pref) {
          try {
            for (var i = 0; i < window.localStorage.length; i++) {
              var k = window.localStorage.key(i);
              if (k && (k === pref || k.indexOf(pref) === 0)) {
                local[k] = window.localStorage.getItem(k);
              }
            }
          } catch (e) {}
        });
        [VOICE_KEY, THEME_KEY].forEach(function (k) {
          try {
            var v = window.localStorage.getItem(k);
            if (v != null) local[k] = v;
          } catch (e) {}
        });
        var bundle = { app: '小满的解忧铺', kind: 'backup', version: 1,
                       exported_at: j.exported_at || new Date().toISOString(),
                       browser: local, records: j.records || [] };
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
        showToast('备份已下载：' + (j.records || []).length + ' 条记录 + 本机偏好', 'info');
      } catch (e) {
        showToast('备份失败：' + e.message, 'error');
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
        _hw.textContent = '再点一次——生辰/昵称/记录全清';
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
          if (k && (/^(me(:partner)?|hlask|visits|welcomed|chatSessionId|chatTranscript)$/
                .test(k) || k.indexOf('checkin:') === 0 ||
                k.indexOf('dailyRevealed:') === 0 ||
                k.indexOf('checkinCeleb:') === 0)) _rm.push(k);
          }
          _rm.forEach(function (k) { localStorage.removeItem(k); });
        } catch (e) {}
        try { _renderMeStrip(); } catch (e2) {}
        try { loadPaipanHistory(); } catch (e3) {}
        showToast(serverOk
          ? '都忘掉啦——本机档案和台账都空了'
          : '本机档案清了，台账没连上——联网后再点一次', serverOk ? 'info' : 'warn');
      };
      /* R2349（R65-P1-2）：收藏表（合婚CP/心水名单）含双方生辰+昵称，
       * 「忘掉我的数据」承诺必须覆盖——与台账一起清。 */
      Promise.all([
        phFetch('/api/paipan/history', { method: 'DELETE' }),
        phFetch('/api/favorites', { method: 'DELETE' })
      ]).then(function () { _done(true); })
        .catch(function () { _done(false); });
    });
    var _imb = document.getElementById('historyImportBtn');
    var _imf = document.getElementById('historyImportFile');
    if (_imb && _imf) {
      _imb.addEventListener('click', function () { _imf.click(); });
      _imf.addEventListener('change', async function () {
        var f = _imf.files && _imf.files[0];
        _imf.value = '';
        if (!f) return;
        try {
          var bundle = JSON.parse(await f.text());
          if (!bundle || bundle.kind !== 'backup') {
            showToast('这不是小满的备份文件', 'error');
            return;
          }
          var local = bundle.browser || {};
          Object.keys(local).forEach(function (k) {
            /* 只收认识的键——备份文件是用户可控输入，不写任意键 */
            if (/^(checkin:|dailyRevealed:|me$|me:partner$|hlask$|visits$|welcomed$|installTipDismissed$|voiceMode$|uiTheme$)/
                .test(k) && typeof local[k] === 'string' &&
                local[k].length < 8192) {
              try { window.localStorage.setItem(k, local[k]); } catch (e) {}
            }
          });
          var n = 0;
          if (Array.isArray(bundle.records) && bundle.records.length) {
            const rj = await postJSON('/api/paipan/history/import',
                                      { records: bundle.records.slice(0, 500) });
            n = rj.imported || 0;
          }
          showToast('导入好了：多了 ' + n + ' 条记录，偏好也回来了（刷新后生效）', 'info');
          loadPaipanHistory();
        } catch (e) {
          showToast('导入失败：' + e.message, 'error');
        }
      });
    }
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
    var _brb = _badYmdField('b_year', 'b_month', 'b_day');
    if (_brb) {
      _failField(_brb, 'birthResult',
        '这一天不存在——' + m + ' 月没有 ' + d + ' 号');
      return;
    }
    busy('birthResult', '正在排你的本命盘…');
    try {
      /* R233x（R56-P1）：本命盘流日此前锚服务器日——跨零点/时区
       * 边缘与日签/黄历错位；与 dailyDetail 同款 client 日。 */
      var body = { year: y, month: m, day: d, hour: (hv === '' ? 12 : Number(hv)), gender: g,
        ask_date: todayIso() };
      _meSave('me', { y: y, m: m, d: d, h: (hv === '' ? null : Number(hv)), g: g,
        n: (document.getElementById('b_nick') || {}).value || '' });
      _meFillAll();   /* R230y */
      /* R228k：raw fetch → postJSON——白拿 20s 超时、非2xx toast 与
       * 422 中文人话化（原来手写的 r.ok 分支与 api() 重复且漏超时）。 */
      var j = await postJSON('/api/bazi', body);
      var sign = sunSign(m, d);
      var fe = ((j.calc || {}).five_elements || {}).counts || {};
      var wxLine = Object.keys(fe).map(function (k) { return k + ' ' + fe[k]; }).join(' · ');
      var missing = ((j.calc || {}).five_elements || {}).missing || [];
      var pp = ((j.paipan || {}).render || '').split('　')[0] || '';
      var warm1 = (((j.warm || {}).reply || [])[0]) || '';
      var html = '<div class="birth-card">';
      html += '<div class="birth-head"><img class="birth-img" src="/static/cream/zodiac-' +
        ({'白羊':'aries','金牛':'taurus','双子':'gemini','巨蟹':'cancer','狮子':'leo','处女':'virgo','天秤':'libra','天蝎':'scorpio','射手':'sagittarius','摩羯':'capricorn','水瓶':'aquarius','双鱼':'pisces'}[sign] || 'aries') +
        '.jpg" alt="" onerror="this.classList.add(\'is-missing\')">' +
        '<div><div class="birth-sign">你是' + esc(sign) + '座</div>' +
        '<div class="birth-sub">' + esc(SIGN_TXT[sign] || '') + '</div></div></div>';
      html += '<div class="birth-block"><span class="birth-label">你的四柱</span><span class="birth-val">' + esc(pp) + '</span></div>';
      html += '<div class="birth-block"><span class="birth-label">五行分布</span><span class="birth-val">' + esc(wxLine || '—') + (missing.length ? '　<strong>缺 ' + esc(missing.join('')) + '</strong>' : '　五行不缺') + '</span></div>';
      if (warm1) html += '<div class="birth-block"><span class="birth-label">小满悄悄说</span><span class="birth-val">' + esc(warm1) + '</span></div>';
      html += '<button class="ghost fav-btn" type="button" id="shareBirth" ' +
        'title="生成分享图">📸 分享图</button>';
      html += '<div class="birth-note">以上由排盘引擎按你输入的生日实时计算，同生日同时辰的人解读也会不同。仅供娱乐，不构成决策依据 ✨</div></div>';
      out.innerHTML = html;
      attachChatEntry(out);   /* R230k（R23-P2-1）：本命盘卡挂聊天入口 */
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
      out.innerHTML = '<div class="ph-empty">网络开小差了：' + esc(_humanizeErr(err.message)) + '，稍后再试～</div>';
    }
  }
  var _birthBusy = false;   /* R8 P2-2：裸 click 不经 on()，自加在途锁 */
  async function _birthGuard(ev) {
    if (_birthBusy) return;
    _birthBusy = true;
    try { await doBirthReading(ev); } finally { _birthBusy = false; }
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
function humanCite(citation) {
  var s = String(citation == null ? '' : citation);
  s = s.replace(/\s*@(\?|[^\s·]{0,})/g, '');             /* 去 @ADDR / @?（v4：@ 后非空白非·的尾巴一并清） */
  s = s.replace(/\s*\([^)]*\.txt\)/gi, '');               /* 去 (file.txt) */
  s = s.replace(/\s{2,}/g, ' ');
  return s.trim();
}

/* ── R229u：离线感知——SW 兜住壳后用户仍可能不知道断网，操作只会收到
 * 泛泛的「网络不太好」。offline/online 事件给一条明确状态提示。 */
(function () {
  window.addEventListener('offline', function () {
    showToast(_dayPick(['当前离线——数据暂时刷不出来，恢复网络后再试','现在离线啦——连上网再戳我','离线中，数据先歇一会儿'], 'off'), 'warn');
  });
  window.addEventListener('online', function () {
    showToast('网络回来了～', 'info');
  });
  /* R230d（R16-P1-5）：冷启动就离线（PWA 壳由 SW 兜住）时给同一条提示——
   * offline 事件只在「由在线转离线」时发，启动即离线它不发。 */
  if (navigator.onLine === false) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        showToast(_dayPick(['当前离线——数据暂时刷不出来，恢复网络后再试','现在离线啦——连上网再戳我','离线中，数据先歇一会儿'], 'off'), 'warn');
      });
    } else {
      showToast(_dayPick(['当前离线——数据暂时刷不出来，恢复网络后再试','现在离线啦——连上网再戳我','离线中，数据先歇一会儿'], 'off'), 'warn');
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
