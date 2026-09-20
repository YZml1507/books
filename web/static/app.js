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
  return String(s || '').replace(/[\u200B-\u200D\uFEFF]/g, '').trim();
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
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}

/** 把内容写进结果容器；容器不存在时静默返回。 */
function paint(/* v3-fx-guard */id, html) {
  const node = el(id);
  if (node) {
    /* R228n：结果区无 aria-live 时读屏零播报——polite 注入即读。
     * role=status 自带 polite，双写兼容老读屏。 */
    if (!node.hasAttribute('aria-live')) {
      node.setAttribute('aria-live', 'polite');
      node.setAttribute('role', 'status');
    }
    node.hidden = false;
    node.innerHTML = html;
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
  paint(id, '<div class="no-evidence">' + esc(text) + '</div>');
}

/* R218a-巡4（E-a/E-b）：失败态——清掉成功期说明文字 + 内联「重新测算」
 * 重试按钮。retry 用闭包记住上次提交动作，点击即原样 re-dispatch。 */
/* R229z续17：JS 运行时错/非 JSON 响应的 message 是英文技术原文
 * （"Cannot read properties of null"、"Failed to fetch"……），直接贴上屏
 * 违和且泄漏实现细节。fail/failWithRetry 统一过一遍：把英文技术片段
 * 换成人话尾巴（前面中文前缀「查询失败：」保留）。 */
function _humanizeErr(text) {
  if (typeof text !== 'string') return '出了点小状况，稍后再试';
  return text.replace(
    /(?:Failed to fetch|Load failed|Network request failed|Cannot read propert\w+|is not defined|is not a function|out of range|Unexpected token|Script error|AbortError|TimeoutError)[^。；\n]*/gi,
    '网络或服务出了点小状况');
}
function failWithRetry(id, text, retryFn) {
  document.querySelectorAll('.footnote').forEach(function (fn) { fn.hidden = true; });
  const node = el(id);
  if (!node) return;
  node.hidden = false;
  node.innerHTML =
    '<div class="no-evidence">' + esc(_humanizeErr(text)) +
    (typeof retryFn === 'function'
      ? ' <button type="button" class="ghost" id="retryBtn" ' +
        'style="margin-left:8px;">🔄 重新测算</button>' : '') +
    '</div>';
  const btn = el('retryBtn');
  if (btn && typeof retryFn === 'function') btn.addEventListener('click', retryFn);
}

function fail(id, text) {
  paint(id, '<div class="no-evidence">' + esc(_humanizeErr(text)) + '</div>');
}

/** R228i：Pydantic 422 的 detail 是 [{loc:[...,field],msg}] 数组，
 * 以前 JSON.stringify 原样弹给用户。翻成中文人话。 */
var _FIELD_CN = { year: '年份', month: '月份', day: '日期', hour: '时辰',
  minute: '分钟',
  gender: '性别', surname: '姓氏', names: '候选名', session_id: '会话标识',
  message: '消息', q: '查询词', work_id: '书号', seed: '种子数',
  a_year: '甲年', a_month: '甲月', a_day: '甲日',
  a_hour: '甲时辰', a_gender: '甲性别',
  b_year: '乙年', b_month: '乙月', b_day: '乙日',
  b_hour: '乙时辰', b_gender: '乙性别', calendar_type: '历法',
  scope: '范围', range_start: '区间起始', range_end: '区间结束',
  ask_date: '起问日', ask_hour: '起问时', location: '所在地',
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
async function api(path, options) {
  options = options || {};
  /* R228k：fetch 无超时——请求挂起时 busy() 占位与 on() 在途锁永不复位，
   * 只能刷新页面。AbortSignal.timeout 存在就用，否则手工 controller。 */
  var _ctl = null, _t = null;
  if (!options.signal) {
    if (typeof AbortSignal !== 'undefined' && AbortSignal.timeout) {
      options.signal = AbortSignal.timeout(API_TIMEOUT_MS);
    } else if (typeof AbortController !== 'undefined') {
      _ctl = new AbortController();
      _t = setTimeout(function () { _ctl.abort(); }, API_TIMEOUT_MS);
      options.signal = _ctl.signal;
    }
  }
  var resp;
  try {
    resp = await fetch(path, options);
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
  } finally { if (_t) clearTimeout(_t); }
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
      detail = resp.status >= 500 ? '服务开小差了（' + resp.status + '），稍后再试'
        : (resp.status === 404 ? '要找的内容不在了' : '请求被婉拒了（' + resp.status + '）');
    }
    /* R229z续23（R11-#2）：detail 为对象时 JSON.stringify 会把
     * {"msg":"field required"} 原文吐进 toast——先取中文可读的子键，
     * 都没有就走人话兜底。
     * R230f续2（R16-P2-4）：typeof []==='object'——pydantic 422 的 detail
     * 数组在这里先被换成裸「请求没走通（422）」，_humanize422 根本拿
     * 不到（实测填空年份/超长问题只出裸码）。数组要留给人话化。 */
    if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
      detail = detail.msg || detail.error || detail.message
        || '请求没走通（' + resp.status + '）';
    }
    const err = new Error(Array.isArray(detail) ? _humanize422(detail)
      : (typeof detail === 'string' ? detail : '请求没走通（' + resp.status + '）'));
    /* R218a-巡2（N-05）：错误态用户反馈——非 2xx 一律弹红色 toast（不只
     * 在主流程 catch 里弹；网络层就弹，给用户即时反馈）。4xx 是用户输入
     * 错（黄底提示），5xx 是服务端异常（红底提示）。 */
    var status = resp.status;
    var isClient = status >= 400 && status < 500;
    err.status = status;   /* R8 P2-9：让轮询方对 404 早退（任务不存在） */
    if (!options.silent) {
      showToast(typeof err.message === 'string' ? err.message : '请求失败',
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
    '<span class="toast-msg">' + esc(_msgStr) + '</span>';
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

/** 把 AI 块插进已渲染的结果区末尾；容器不存在/已插过返回 false。 */
function insertAiPolish(containerId, text) {
  var node = el(containerId);
  if (!node || !text) return false;
  if (node.querySelector('.ai-polish')) return false;
  var wrap = document.createElement('div');
  wrap.innerHTML = renderAiPolish({ ai_polish: text });
  var block = wrap.firstElementChild;
  if (!block) return false;
  node.appendChild(block);
  return true;
}

/** 轮询 AI 任务直到终态/超时；任何错误静默停止（D-244a：失败不可见）。 */
function pollAiPolish(containerId, taskId) {
  if (!taskId) return;
  AI_PENDING[containerId] = taskId;   /* R230q：切走再回来可恢复 */
  RESULT_GEN[containerId] = (RESULT_GEN[containerId] || 0) + 1;
  var gen = RESULT_GEN[containerId];
  var deadline = Date.now() + AI_POLL_CAP_S * 1000;
  var _done = function () { delete AI_PENDING[containerId]; };
  var tick = function () {
    if (RESULT_GEN[containerId] !== gen) return;   // 已被新一轮结果覆盖
    /* R230q（R28-P3-8）：后台/断网暂停取数 */
    if (_aiPollGate()) {
      if (Date.now() < deadline) setTimeout(tick, 2000);
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
      if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
      else _done();
    }).catch(function () { /* 404/过期/网络抖动：静默放弃 */ _done(); });
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
function _chatStore() {
  try { return window.sessionStorage; } catch (e) { return null; }
}
function chatSid() {
  try {
    var _st = _chatStore() || localStorage;
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
    var s = (_chatStore() || localStorage).getItem(CHAT_TS_KEY);
    var arr = s ? JSON.parse(s) : [];
    return Array.isArray(arr) ? arr : [];
  } catch (e) { return []; }
}
function _chatTsSave(role, text) {
  try {
    var arr = _chatTsRead();
    arr.push({ r: role === 'me' ? 'me' : 'ai', t: String(text || '').slice(0, 2000) });
    if (arr.length > 50) arr = arr.slice(-50);
    (_chatStore() || localStorage).setItem(CHAT_TS_KEY, JSON.stringify(arr));
  } catch (e) {}
}
function _chatTsClear() {
  try { (_chatStore() || localStorage).removeItem(CHAT_TS_KEY); } catch (e) {}
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
}

/* R219b（P0-2）：把缓存的响应拼成「带数据的第一句」+ 结构化 facts。
 * 返回 {msg, facts}；无缓存时回落到旧的通用句（不阻断交互）。 */
function buildChatContext(viewKey) {
  var entry = LAST_RESULT[viewKey];
  var j = entry ? entry.json : null;
  var q = entry ? (entry.question || '') : '';
  var facts = [];
  var msg = '';
  if (!j) {
    var GENERIC = {
      bazi: '帮我看这个盘', taohua: '桃花怎么样', tarot: '牌面说什么',
      liuyao: '卦象怎么看', hehun: '这两人配吗', huangli: '今天能做什么',
      qiming: '这些名字怎么样', xingzuo: '今天运势怎么样'
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
    msg = '甲方日柱' + (a.day || '—') + '（日主' + (a.day_master || '—') +
      '），乙方日柱' + (b.day || '—') + '（日主' + (b.day_master || '—') +
      '），这两人配吗';
    facts = ['甲方日柱：' + (a.day || '—'), '乙方日柱：' + (b.day || '—')];
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
  } else if (viewKey === 'xingzuo') {
    var today = (j.signs || []).filter(function (s) { return s.is_today; })[0];
    /* R229z续23（R11-#23/#36）：「今天是 2026-…」双空格＋「值宫」术语 */
    msg = '今天是' + (j.date || '') + '，'
      + ((today && today.sign) || '—') + '当值，我今天运势怎么样';
    facts = ['今日当值宫：' + ((today && today.sign) || '—')];
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
  if (!card || card.querySelector('.chat-entry')) return;
  var btn = document.createElement('button');
  btn.className = 'chat-entry';
  btn.type = 'button';
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
    try { (_chatStore() || localStorage).removeItem(CHAT_SID_KEY); } catch (e) {}
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
function autoSendChatContext() {
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
  postJSON('/api/chat', {
    /* R230l（R24-P2-3）：黄历事实的「今天」锚浏览器本地日——服务器
     * UTC vs 浏览器 CST 跨零点窗口整天错位。 */
    session_id: chatSid(), message: msg, facts: facts,
    client_date: todayIso()
  }).then(function (j) {
    if (!j.chat_task_id) {
      /* R218a-02：U-008 修复后仍复用同一句话「打烊中」复读——扩展为
       * 4-6 句确定性轮换，并按上下文（自动发送：必属「看盘」类）做轻回应。 */
      chatBubble('ai', _chatFallbackLine('看盘'));
      return;
    }
    /* R228c：raw 仅内部动效用；保存气泡节点引用——轮询写回不再赌
     * flow.lastChild（竞态下会覆盖/删掉用户自己刚发的消息）。 */
    var _ty = chatBubble('ai',
      '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span>', {raw: true});
    var deadline = Date.now() + AI_POLL_CAP_S * 1000;
    var tick = function () {
      /* R230q（R28-P3-8）：后台标签页/断网时轮询空转烧预算——暂停取数，
       * 恢复后再探；预算照样走，到点降级行为不变。 */
      if (_aiPollGate()) {
        if (Date.now() < deadline) setTimeout(tick, 2000);
        else if (_ty) { _ty.textContent = '（网络不太好，再发一次试试？）';
          _chatTsSave('ai', '（网络不太好，再发一次试试？）'); }
        return;
      }
      api('/api/ai/' + encodeURIComponent(j.chat_task_id), { silent: true }).then(function (st) {
        if (!_ty) return;
        if (st && st.status === 'done' && st.text) {
          /* R227b：写回要走 renderRichText——textContent 会让 ** 原样露出 */
          _ty.innerHTML = renderRichText(st.text);
          _chatTsSave('ai', st.text);            /* R230q：transcript 留档 */
          if (st.closed) _chatClosedHint(_ty);   /* R230d（P2-7） */
          return;
        }
        if (st && st.status === 'failed') {
          _ty.innerHTML = renderRichText('（小满这次没接住，再说一遍试试？）');
          _chatTsSave('ai', '（小满这次没接住，再说一遍试试？）');
          return;
        }
        if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
        else { _ty.textContent = '（网络不太好，再发一次试试？）';
          _chatTsSave('ai', '（网络不太好，再发一次试试？）'); }
      }).catch(function (e) {
        /* R228c：瞬时抖动原来直接杀死轮询（catch 空转，typing 永转圈）。
         * 截止前继续排，超时才降级文案。R8 P2-9：404 任务不存在早退。 */
        if (e && e.status === 404) {
          if (_ty) { _ty.textContent = '（这次没接住，再发一次试试？）';
            _chatTsSave('ai', '（这次没接住，再发一次试试？）'); }
          return;
        }
        if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
        else if (_ty) { _ty.textContent = '（网络不太好，再发一次试试？）';
          _chatTsSave('ai', '（网络不太好，再发一次试试？）'); }
      });
    };
    setTimeout(tick, AI_POLL_INTERVAL_MS);
  }).catch(function () {
    chatBubble('ai', '（网络不太好，再发一次试试？）');
  });
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
    "累的时候做的决定十有八九会后悔，先放放，回头来。"
  ],
  'work': [
    "工作的坎儿先不急开会——思路睡一觉会清楚很多，回头找我聊细节。",
    "听到工作的苦。回头跟我讲讲你卡在哪一环，咱们一起拆。",
    "工作的事先放我这儿，你今晚先下班。",
    "职场的弯弯绕绕回来拆给你听。先喝口热的，喘口气。"
  ],
  'love': [
    "感情的事急也急不出答案。先放过自己，回头来跟我讲。",
    "爱里的纠结最难熬。回头来找我，把心意慢慢理顺。",
    "先不猜他的心思了，回头来听我说说牌面给的信号。",
    "心动或心累都先收着，回来我陪你解。"
  ],
  'study': [
    "学习的压力先放一放，脑子也需要打烊。回头我陪你拆重点。",
    "考试的事先交给睡一觉的自己——先复盘三件今天做对的小事。",
    "学不进去的时候别硬撑，回头来我帮你把节奏理一理。",
    "作业的事回头再战。先奖励自己一集短剧。"
  ],
  'money': [
    "钱包的事回头再算——先不想钱的事。",
    "理财的纠结回来拆给你听。先关掉账单页面。",
    "先不数余额。回头来找我，把账本翻一遍。",
    "钱的事别熬夜想——夜里做的预算都偏严。回头聊。"
  ],
  'default': [
    "今天小满提前打烊啦～先把上面的牌面看着，我一直在这。",
    "解忧铺这会儿休整中，你的心事我存着，随时来听。",
    "门牌已经翻到『休息中』，回头找我深聊。",
    "解忧铺的茶凉了，重新烧上了——你写下来的我都会读。"
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
  var idx = (_CHAT_FALLBACK_COUNTER + ((message || '').length | 0)) % pool.length;
  return pool[idx];
}

/** R207b：起名点评轮询——复用 /api/ai/{tid}，done 渲染点评卡。 */
/* R230d（R16-P3-3）：终态时把 nameReviewBtn 解灰——此前按钮在点击后
 * 永久 disabled，点评成功后想换换说法再点一次都没门（只能靠整卡重绘）。 */
function _nameReviewDone() {
  var b = el('nameReviewBtn');
  if (b) b.disabled = false;
}
function pollNameReview(taskId) {
  var deadline = Date.now() + AI_POLL_CAP_S * 1000;
  var tick = function () {
    if (_aiPollGate()) {   /* R230q（R28-P3-8）：后台/断网暂停取数 */
      if (Date.now() < deadline) setTimeout(tick, 2000);
      else { var o0 = el('nameReviewOut'); if (o0) o0.innerHTML =
        '<div class="no-evidence">超时了，再试一次？</div>'; _nameReviewDone(); }
      return;
    }
    api('/api/ai/' + encodeURIComponent(taskId), { silent: true }).then(function (st) {
      const out = el('nameReviewOut');
      if (!out) { _nameReviewDone(); return; }
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
      if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
      else { out.innerHTML = '<div class="no-evidence">超时了，再试一次？</div>'; _nameReviewDone(); }
    }).catch(function (e) {
      /* R228c：同上——瞬时抖动不该杀死轮询。R8 P2-9：404 早退。 */
      var out2 = el('nameReviewOut');
      if (e && e.status === 404) {
        if (out2) out2.innerHTML = '<div class="no-evidence">这次没点评出来，稍后再试</div>';
        _nameReviewDone();
        return;
      }
      if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
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
function _mainInert(on) {
  var w = document.querySelector('.wrap');
  if (!w) return;
  w.inert = on;
  if (_NO_INERT) sbFocusable(w, !on);
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
  im.src = '/static/_candidates/r212b/icon-set-moon-cat.png';
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
  /* D-006：追踪发送次数，第一条自动发后允许追问 1 次，第 2 次回复后才锁 */
  _CHAT_SEND_COUNT = (_CHAT_SEND_COUNT || 0) + 1;
  postJSON('/api/chat', {
    session_id: chatSid(), message: msg, facts: CHAT_LAST_FACTS,
    client_date: todayIso()   /* R230l */
  }).then(function (j) {
    if (!j.chat_task_id) {                     /* DISABLE：入口静默降级 */
      /* R216b 续3（UX 队列 U-008）：原降级文案「（聊天功能暂时没开，
       * 稍后再来吧）」系统腔零共情——用户刚倾诉疲惫。改为情绪承接 +
       * 替代引导；DISABLE 态输入框置灰防连发连拒。
       * R218a-02：扩为 4-6 句确定性轮换 + 关键词到 openeer 的最轻分支
       * （累/事业/感情/学业/钱/看盘 6 套）。 */
      chatBubble('ai', _chatFallbackLine(msg));
      var sendBtn2 = document.getElementById('chatSendBtn');
      /* D-006：第一条自动发后允许追问 1 次，累计发送 ≥2 次后才锁 */
      if (_CHAT_SEND_COUNT >= 2) {
        if (input) { input.disabled = true; input.placeholder = '小满休息中，回头再来聊吧'; }
        if (sendBtn2) sendBtn2.disabled = true;
      }
      return;
    }
    /* R228c：同 autoSendChatContext——节点引用写回 + catch 续排。 */
    var _ty = chatBubble('ai',
      '<span class="chat-typing" aria-hidden="true"><i></i><i></i><i></i></span>', {raw: true});
    var deadline = Date.now() + AI_POLL_CAP_S * 1000;
    var tick = function () {
      if (_aiPollGate()) {   /* R230q（R28-P3-8）：后台/断网暂停取数 */
        if (Date.now() < deadline) setTimeout(tick, 2000);
        else if (_ty) { _ty.textContent = '（网络不太好，再发一次试试？）';
          _chatTsSave('ai', '（网络不太好，再发一次试试？）'); }
        return;
      }
      api('/api/ai/' + encodeURIComponent(j.chat_task_id), { silent: true }).then(function (st) {
        if (!_ty) return;
        if (st && st.status === 'done' && st.text) {
          /* R227b：写回要走 renderRichText——textContent 会让 ** 原样露出 */
          _ty.innerHTML = renderRichText(st.text);
          _chatTsSave('ai', st.text);            /* R230q：transcript 留档 */
          if (st.closed) _chatClosedHint(_ty);   /* R230d（P2-7） */
          return;
        }
        if (st && st.status === 'failed') {
          _ty.innerHTML = renderRichText('（小满这次没接住，再说一遍试试？）');
          _chatTsSave('ai', '（小满这次没接住，再说一遍试试？）');
          return;
        }
        if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
        else { _ty.textContent = '（网络不太好，再发一次试试？）';
          _chatTsSave('ai', '（网络不太好，再发一次试试？）'); }
      }).catch(function (e) {
        /* R8 P2-9：404 = 任务已不在（重启/过期）——别再轮满 40s，直接降级。 */
        if (e && e.status === 404) {
          if (_ty) { _ty.textContent = '（这次没接住，再发一次试试？）';
            _chatTsSave('ai', '（这次没接住，再发一次试试？）'); }
          return;
        }
        if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
        else if (_ty) { _ty.textContent = '（网络不太好，再发一次试试？）';
          _chatTsSave('ai', '（网络不太好，再发一次试试？）'); }
      });
    };
    setTimeout(tick, AI_POLL_INTERVAL_MS);
  }).catch(function () {
    /* R230q（R28-P3-11）：发送失败把已打文案放回输入框，离线不丢稿 */
    if (input && !input.disabled) input.value = msg;
    /* 已贴出的 me 气泡同时从 transcript 与 DOM 回收——重试不再双发同句 */
    try {
      var _arr = _chatTsRead();
      if (_arr.length && _arr[_arr.length - 1].r === 'me' &&
          _arr[_arr.length - 1].t === msg) {
        _arr.pop();
        (_chatStore() || localStorage).setItem(CHAT_TS_KEY, JSON.stringify(_arr));
        var _bbs = document.querySelectorAll('#chatFlow .chat-me');
        if (_bbs.length && _bbs[_bbs.length - 1].textContent === msg) {
          _bbs[_bbs.length - 1].remove();
        }
      }
    } catch (e2) {}
    chatBubble('ai', '（网络不太好，再发一次试试？）');
  });
}

/** 绑定点击；元素不存在时不报错（HTML 与 JS 允许分批演进）。
 * R228c：统一在途防重——handler 未落地前连点直接忽略。全站提交按钮
 * 走 on() 一处生效，替代逐按钮挂 disabled/flag 的老办法。
 * R230q（R28-P1-1）：锁改为按 key 共享的注册表——Enter 键路径与按钮
 * 点击此前各执一把锁（Enter 直接调 handler），连按回车可并发发请求
 * （#tq 每秒刷出一条永久线程）。现在 Enter/点击共用同 key 同锁。 */
var _ON_BUSY = {};
function guardedCall(key, handler, ev) {
  if (_ON_BUSY[key]) return;
  _ON_BUSY[key] = true;
  Promise.resolve(handler(ev)).catch(function (e) {
    console.warn('[on] handler error', e);
  }).then(function () { _ON_BUSY[key] = false; });
}
function on(id, handler) {
  const node = el(id);
  if (!node) return;
  node.addEventListener('click', function (ev) {
    guardedCall(id, handler, ev);
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
  } else if (isHome && window.__lastFuncCard) {
    try { window.__lastFuncCard.focus({ preventScroll: true }); }
    catch (e0) { try { window.__lastFuncCard.focus(); } catch (e1) {} }
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
       * init 深链回跳原视图，结果页也可整链分享。 */
      history.pushState({ view: viewId }, '',
        '?view=' + encodeURIComponent(viewId));
    } else if (isHome && !window.__suppressPush &&
        /[?&]view=/.test(location.search)) {
      /* 回首页清掉 ?view=——否则挂着旧参数的 F5 会被深链拽回上一视图 */
      history.pushState({ view: 'home' }, '', '/');
    }
  } catch (e) { /* file:// 环境无 history API */ }
  /* R216b 续（U-007）：时间起卦默认当天（原 HTML 写死 1990/5/15）。 */
  if (viewId === 'liuyao') syncLiuyaoToday();
  /* R222b（E-301 P0）：黄历同理——原 HTML 写死 2026/8/19 */
  if (viewId === 'huangli') hlInitToday();
  /* C-002-fix：星座视图进入时自动加载今日运势 */
  if (viewId === 'xingzuo') doXingzuo(false);   /* R228f：重进同日复用已渲染，不再重拉+跳动 */
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
    return '<div class="no-evidence">' + esc(o.empty || '无命中') + '</div>';
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
      (o.score && h.score != null ? '<span class="hit-score" title="BM25 相关度：负分，越接近 0 越相关">score ' +
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
    return '<div class="no-evidence">' + esc(o.empty || '无引文') + '</div>';
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
        (h.citation ? '<div class="ev-src">出处：' + esc(h.citation) + '</div>' : '') +
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
    return localStorage.getItem(THEME_KEY) === 'legacy' ? 'legacy' : 'aa';
  } catch (e) {
    return 'aa';
  }
}

function applyTheme(theme) {
  var t = theme === 'legacy' ? 'legacy' : 'aa';
  if (t === 'legacy') {
    document.documentElement.setAttribute('data-theme', 'legacy');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  try {
    localStorage.setItem(THEME_KEY, t);
  } catch (e) { /* 存不了就只在本次会话生效 */ }
}

/** R206b（US4）：共情模板族——确定性选择，同输入同输出。 */
var WARM_EMPATHY = {
  "感情": "感情的事最怕自己闷着，我们一起看看盘里怎么说。",
  "事业": "工作上的事悬着心吧？先看看盘里的信号，再说下一步。",
  "学业": "学习上有点累了吧？盘里有些线索给你参考。",
  "健康": "身体是自己的，先深呼吸，我们温和地看看盘里的提醒。"
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
    if (q.indexOf(k) !== -1) return WARM_EMPATHY[k];
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
  if (!warm) return renderInterpretation(interp, '📖 解读（确定性规则）');
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
    '<span class="ai-polish-badge">AI 生成 · 仅供娱乐 · 再点一次可能不一样</span></div>' +
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
  ctx.font = '600 64px serif';
  ctx.textAlign = 'center';
  /* R230r（R29-#3）：legacy 版式混用 W 与 1080 逻辑坐标——750 档下标题/
   * pills/能量卡/水印集体左移、首 pill 被裁。几何值全部钉回 1080 逻辑系。 */
  ctx.fillText('🔮 今日命盘', 540, 130);

  // 四柱 pills
  var pillars = String(paipan.render || '').split(/\s+/).filter(function (p) { return p.length >= 2; });
  ctx.font = '500 44px serif';
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
  ctx.font = '600 56px sans-serif';
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
  ctx.fillStyle = '#7A5C2E'; ctx.font = '600 40px sans-serif';
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
  ctx.font = '400 38px sans-serif';
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
  ctx.fillStyle = '#9A8A6C'; ctx.font = '400 30px sans-serif';
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
  ctx.font = '600 36px serif';
  ctx.fillText('@小满的解忧铺', 540, 1440 - 158);
  ctx.fillStyle = '#B7A98A';
  ctx.font = '400 24px sans-serif';
  ctx.fillText('· 知命知书知天机 ·', 540, 1440 - 124);
  ctx.fillStyle = '#815934';
  ctx.font = '500 26px sans-serif';
  ctx.fillText('知命，是为了更好地活', 540, 1440 - 80);
  ctx.fillStyle = '#B7A98A';
  ctx.font = '400 34px sans-serif';
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
  var bgImg = POSTER_BG.warm;
  if (bgImg && bgImg.complete && bgImg.naturalWidth) {
    ctx.drawImage(bgImg, 0, 0, 1080, 1440);
  } else {
    var bg = ctx.createLinearGradient(0, 0, 0, 1440);
    bg.addColorStop(0, '#FDF8F0'); bg.addColorStop(1, '#F6EDE0');
    ctx.fillStyle = bg; ctx.fillRect(0, 0, 1080, 1440);
  }
  ctx.textAlign = 'center';

  /* 标题 + 副题 */
  ctx.fillStyle = '#7A5C2E'; ctx.font = '600 60px serif';
  ctx.fillText(_pStr(s.title) || '知命', 540, 128);
  if (s.subtitle) {
    ctx.fillStyle = '#B7A98A'; ctx.font = '400 32px sans-serif';
    ctx.fillText(_gSlice(s.subtitle, 24), 540, 182);
  }

  /* 大字结论（最多两行，自动缩字号防溢出） */
  var big = _pStr(s.big);
  ctx.fillStyle = '#3E3428';
  var bigSize = big.length > 14 ? 62 : (big.length > 9 ? 76 : 92);
  ctx.font = '600 ' + bigSize + 'px sans-serif';
  /* R212：三行上限（原两行导致「宜稳不」截断感），行距随字号自适应 */
  var words = wrapText3(ctx, big, 900);
  var bigGap = Math.round(bigSize * 1.35);
  words.forEach(function (ln, i) { ctx.fillText(ln, 540, 300 + i * bigGap); });

  /* 键值行卡片 */
  var lines = (s.lines || []).slice(0, 4);
  /* R212：随大字行数下移卡片，避免重叠 */
  var cardY = (s.cards && s.cards.length ? 500 : 520) + Math.max(0, words.length - 2) * 60;
  if (lines.length) {
    var lh = Math.min(120, 900 / lines.length);
    ctx.fillStyle = '#FFFFFF';
    _roundRectPath(ctx, 90, cardY - 60, 900, lines.length * lh + 40, 28); ctx.fill();
    ctx.strokeStyle = '#E8D9BC'; ctx.lineWidth = 2;
    _roundRectPath(ctx, 90, cardY - 60, 900, lines.length * lh + 40, 28); ctx.stroke();
    ctx.textAlign = 'left';
    lines.forEach(function (r, i) {
      var y = cardY + i * lh + 10;
      ctx.fillStyle = '#B7A98A'; ctx.font = '400 34px sans-serif';
      ctx.fillText(r.k, 150, y);
      ctx.fillStyle = '#3E3428'; ctx.font = '500 40px sans-serif';
      var v = _pStr(r.v);
      ctx.fillText(Array.from(v).length > 16 ? _gSlice(v, 15) + '…' : v,
                   150, y + 52);
    });
    ctx.textAlign = 'center';
  }

  /* 卡片区（塔罗：RWS 真图直绘；其他：文字卡） */
  var cards = (s.cards || []).slice(0, 3);
  if (cards.length) {
    var cw = 250, ch = 420, gap = (1080 - cards.length * cw) / (cards.length + 1);
    var cy = 880;
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
      ctx.fillStyle = '#3E3428'; ctx.font = '600 38px sans-serif';
      ctx.fillText(_gSlice(c.name, 6), cx + cw / 2, iy + 44);
      ctx.fillStyle = '#815934'; ctx.font = '400 28px sans-serif';
      ctx.fillText(_gSlice(c.sub, 8), cx + cw / 2, iy + 88);
    });
  }

  /* R218a-11：品牌水印 + 金句 hook——海报底部分两行：
   * 1) 品牌水印「@小满的解忧铺 · 知命知书知天机」（替原「知命 · 仅供娱乐」）
   * 2) 金句 hook（按 view 给不同内容，无 view 时通用）。 */
  ctx.textAlign = 'center';
  /* 水印行 */
  ctx.fillStyle = '#7A5C2E'; ctx.font = '600 36px serif';
  ctx.fillText('@小满的解忧铺', 540, 1320);
  /* R230r（R29-#11）：免责声明是合规件——花纹底图上浅棕字几乎不可读，
   * 给文字垫一条半透明米白衬底，任何背景下都可读。 */
  ctx.fillStyle = 'rgba(253,248,240,0.78)';
  _roundRectPath(ctx, 540 - 340, 1330, 680, 42, 21); ctx.fill();
  ctx.fillStyle = '#8A7A56'; ctx.font = '400 26px sans-serif';
  /* R229z续23（R11-#3）：分享图会离站传播，免责必须跟着走 */
  ctx.fillText('· 知命知书知天机 · 仅供娱乐 ·', 540, 1356);
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
    ctx.font = '500 ' + _hs + 'px sans-serif';
    while (_hs > 16 && ctx.measureText(hook).width > 980) {
      _hs -= 2; ctx.font = '500 ' + _hs + 'px sans-serif';
    }
    if (ctx.measureText(hook).width > 980) hook = _gSlice(hook, 34) + '…';
    ctx.fillStyle = '#815934';
    ctx.fillText(hook, 540, 1400);
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
    if (c) return '你的命格是「' + c + '」，' + (c.length === 1 ? '一' : c.length === 2 ? '二' : '三') + '字真言已就位';
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
    if (zhi) return '桃花落在「' + zhi + '」支 · 强度 ' + (stg || '待时');
  }
  /* hehun: 用双方日主五行（R230r：畸形字段先过 _pStr，不画 [object Object]） */
  var _ha = _pStr(j && j.day_wx_a), _hb = _pStr(j && j.day_wx_b);
  if (view === 'hehun' && _ha && _hb) {
    return _ha + ' 遇 ' + _hb + ' · ' +
      (j.day_wx_sheng ? '相生' : (j.day_wx_same ? '同气' : '互补'));
  }
  /* 默认文案版（R218a-11 原版） */
  var hooks = {
    'liuyao': '卦不骗人，帮你读',
    'daily':  '今日运势 · 听小满慢慢说'
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
    return { title: title, subtitle: subtitle, big: l0 || title,
             lines: [], cards: [], view: view };
  }
  switch (view) {
    /* R230r（R29-#1/#2）：入图字段一律过 _pArr/_pStr——后端 schema 漂移
     * 把 yi 传成字符串、clash 传成对象时不再崩分享链或画出 [object Object]。 */
    case 'daily':
      return { title: '今日运势', subtitle: _pStr(j && j.date),
        /* R212：原 slice(0,18) 会把 summary 拦腰截断（「…宜稳不」）——
         * 改取第一个分号前的完整短句。 */
        big: (j && j.summary)
          ? (String(j.summary).split(/[；;]/)[0] || '今日份小确幸')
          : '今日份小确幸',
        /* R229z续23（R11-#8）：海报与卡面同口径——凶→缓 */
        lines: [{ k: '运势等级', v: _pStr((j && j.level) === '凶' ? '缓' : (j && j.level)) || '—' },
                { k: '天乙贵人', v: _pStr(j && j.noble) || '—' },
                { k: '宜', v: _pStr(j && j.do) || '—' },
                { k: '忌', v: _pStr(j && j.dont) || '—' }],
        cards: [], view: view };
    case 'tarot': {
      var draws = _pArr(j && j.draws);
      var imgs = document.querySelectorAll('.tarot-card-front img');
      var s = base('塔罗指引', _pStr(j && j.question));
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
      var sxz = base('星座日运', _pStr(j && j.date));
      var _xzTd = _pArr(j && j.signs).filter(function (s) { return s && s.is_today; })[0];
      sxz.big = _pStr(j && j.today_sign) || '今日值宫';
      var _xzl = [];
      if (_xzTd && _xzTd.love) _xzl.push({ k: '爱情', v: _gSlice(_xzTd.love, 24) });
      if (_xzTd && _xzTd.career) _xzl.push({ k: '事业', v: _gSlice(_xzTd.career, 24) });
      if (_xzTd && _xzTd.wealth) _xzl.push({ k: '财运', v: _gSlice(_xzTd.wealth, 24) });
      sxz.lines = _xzl.slice(0, 3);
      return sxz;
    }
    case 'liuyao': {
      var sly = base('六爻占卜', '');
      sly.lines = _pArr(w.details && w.details.basis).slice(0, 4)
        .map(function (b) { return { k: '依据', v: _pStr(b) }; });
      if (!sly.lines.length) sly.lines = [{ k: '结论', v: _gSlice(l0, 15) }];
      return sly;
    }
    case 'qiming':
      return { title: '五行起名', subtitle: '按五行补缺',
        big: _gSlice((_pArr(j && j.full_names)[0] || {}).full_name || l0, 12),
        lines: _pArr(j && j.full_names).slice(0, 4).map(function (n, i) {
          return { k: '推荐 ' + (i + 1), v: _pStr(n && n.full_name) }; }),
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
      if (_pStr(j && j.peach_zhi)) st.lines.push({ k: '桃花支', v: _pStr(j.peach_zhi) });
      var _hp = _pArr(j && j.hit_pillars);
      if (_hp.length) st.lines.push({ k: '命中柱', v: _hp.map(function (p) { return ({ year: '年柱', month: '月柱', day: '日柱', hour: '时柱' })[p] || _pStr(p); }).join(' · ') });
      if (_pStr(j && j.hongluan)) st.lines.push({ k: '红鸾', v: _pStr(j.hongluan) });
      if (_pStr(j && j.tianxi)) st.lines.push({ k: '天喜', v: _pStr(j.tianxi) });
      if (_pStr(j && j.strength)) st.lines.push({ k: '桃花强度', v: _pStr(j.strength) });
      if (!st.lines.length) st.lines = [{ k: '结论', v: _gSlice(l0, 15) || '桃花待时而动' }];
      return st;
    }
    case 'hehun': {
      var sh = base('合婚配对', '');
      sh.big = l0 || '甜度超标组合';
      sh.lines = [];
      var _wa = _pStr(j && j.day_wx_a), _wb = _pStr(j && j.day_wx_b);
      if (_wa && _wb) {
        var sheng = j.day_wx_sheng ? ' · 相生' : (j.day_wx_same ? ' · 比和' : '');
        sh.lines.push({ k: '日主五行', v: _wa + ' ↔ ' + _wb + sheng });
      }
      var _cl = _pStr(j && j.clash), _cb = _pStr(j && j.combine);
      if (_cl) sh.lines.push({ k: '六冲', v: _cl });
      if (_cb) sh.lines.push({ k: '六合', v: _cb });
      if (j && typeof j.peach_same === 'boolean') sh.lines.push({ k: '桃花支', v: j.peach_same ? '同支共振' : '各有桃花' });
      var _gh = _pStr(j && j.gan_he);
      if (_gh) sh.lines.push({ k: '天干五合', v: _gh });
      if (!sh.lines.length) sh.lines = [{ k: '结论', v: _gSlice(l0, 15) || '天作之合' }];
      return sh;
    }
    /* R229z续25：黄历分享图——唯一没海报的核心视图补齐（宜/忌/建除/值宿/
     * 冲煞/相冲提示全取自确定性字段，离站海报同样带仅供娱乐页脚）。 */
    case 'huangli': {
      var jh = j || {};
      var lun = jh.lunar || {};
      var shl = base('今日宜忌',
        (jh.date || '') +
        ((lun.month_cn || lun.day_cn) ? ' · 农历' + (lun.month_cn || '') + (lun.day_cn || '') : ''));
      var yiL = _pArr(jh.yi), jiL = _pArr(jh.ji);
      shl.big = yiL.length ? ('宜 ' + yiL.slice(0, 3).join(' · ')) : '今日平稳';
      shl.lines = [];
      if (yiL.length) shl.lines.push({ k: '宜', v: yiL.slice(0, 5).join(' · ') });
      if (jiL.length) shl.lines.push({ k: '忌', v: jiL.slice(0, 5).join(' · ') });
      if (jh.jianchu) shl.lines.push({ k: '建除', v: _pStr(jh.jianchu) });
      if (jh.xiu) shl.lines.push({ k: '值宿', v: _pStr(jh.xiu) });
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
  /* R230q（R28-P3-13）：连点分享每次都真下载——下载目录堆 N 张同名图
   * 还触发浏览器「多次下载」权限弹窗。4s 内同视图只给预览浮层。 */
  var _vkey = view || 'default';
  var _dup = (Date.now() - (_POSTER_LAST[_vkey] || 0)) < 4000;
  /* R193b：外壳返回 {canvas,w,h}；auto 模式 >50ms 自动降级 750×1000。
   * R198b（US5）：view 传入时先 buildShareData 注入 j.share（通用模板）；
   * 不传则保持 bazi 专属旧版式。
   * R218a-巡2（N-02 虚标重做）：画完海报后**弹浮层**给用户看——之前
   * `canvas.toBlob()` 静默触发下载，用户在小红书场景下完全不知道图
   * 在哪、怎么用。本轮补 modal：海报图 + 关闭按钮（点遮罩/ESC 都关）
   * + 长按图片保存到相册的提示文案。下载仍走 toBlob（兼容 desktop）
   * 浮层只是补一层视觉反馈。 */
  if (view) {
    var s = buildShareData(view, j);
    if (s) j = Object.assign({}, j, { share: s });
  }
  /* R230r（R29-#6）：背景图 requestIdleCallback 异步加载——点就画会拿到
   * 渐变底、过会再点拿到真图，同一输入两种产出。绘制前等它加载
   * （1.5s 超时/失败都回落渐变，保证确定性口径「同一时点同一产出」）。 */
  var _bg = POSTER_BG.warm;
  if (_bg && _bg.src && !(_bg.complete && _bg.naturalWidth)) {
    try {
      await Promise.race([
        (_bg.decode ? _bg.decode() : new Promise(function (res, rej) {
          _bg.onload = res; _bg.onerror = rej;
        })),
        new Promise(function (res) { setTimeout(res, 1500); })]);
    } catch (e) { /* 加载失败走渐变兜底 */ }
  }
  var r = drawPoster(j);
  /* R230r（R29-#12）：画不出来要有回音——原来静默 return 像没点到。 */
  if (!r || !r.canvas) {
    showToast('这张图没画出来，再点一次试试', 'warn');
    return;
  }
  /* 同时触发下载（兼容 desktop「图去哪了」老习惯）+ 弹浮层。 */
  try {
    if (_dup) {
      showToast('这张图刚保存过了，长按/右键可直接再存', 'info');
    } else {
      _POSTER_LAST[_vkey] = Date.now();
      r.canvas.toBlob(function (blob) {
        if (!blob) return;
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        /* R230r（R29-#9）：文件名带视图+日期——连存多张不再全是同名。 */
        var _d = new Date();
        var _ymd = _d.getFullYear() +
          ('0' + (_d.getMonth() + 1)).slice(-2) + ('0' + _d.getDate()).slice(-2);
        a.download = 'zhiming-' + _vkey + '-' + _ymd + '.png';
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
  /* 视图名 → 人话标题 */
  var viewTitle = ({
    bazi: '今日命盘', liuyao: '六爻指引', tarot: '塔罗指引',
    qiming: '五行起名', taohua: '桃花运势', hehun: '合婚配对', daily: '今日运势',
    huangli: '今日宜忌'
  })[view] || '命盘海报';
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
        '<img class="poster-modal-img" src="' + img + '" alt="命盘海报">' +
      '</div>' +
      '<div class="poster-modal-tip">💡 长按图片可保存到相册 · 桌面端已自动下载到下载文件夹</div>' +
    '</div>';
  document.body.appendChild(backdrop);
  /* 触发动画 */
  requestAnimationFrame(function () { backdrop.classList.add('open'); });
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
    if (e.key === 'Tab' || e.keyCode === 9) {
      e.preventDefault();
      var _c = backdrop.querySelector('.poster-modal-close');
      if (_c) _c.focus();
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
/* R228d：焦点归还触发的分享钮（读屏/键盘用户不丢位） */
  if (_posterTrigger && _posterTrigger.focus) {
    try { _posterTrigger.focus(); } catch (e) {}
    _posterTrigger = null;
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
    if (ctx.measureText(cur + ch).width > maxWidth) { lines.push(cur); cur = ch; }
    else cur += ch;
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
    return String(t).replace(/（G[0-9]+[：:][^）]*）/g, '').replace(/\(G[0-9]+:[^)]*\)/g, '');
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
    html += '<div class="interp-basis">依据字段：' + esc(interp.basis.join(' / ')) + '</div>';
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
    const [j, x] = await Promise.all([
      /* R230h（R20-F6）：显式带浏览器日——跨零点时服务器「今天」
       * 与用户本地「今天」可能差一天。 */
      api('/api/daily?date=' + todayIso()),
      api('/api/xingzuo?date=' + todayIso(), { silent: true }).catch(function () { return null; })
    ]);
    window.__lastDaily = j;   /* R198b（US5）：shareDaily 用 */
    const dateEl = el('dailyDate');
    if (dateEl) dateEl.textContent = j.date || '今天';
    const level = j.level || '平';
    const levelEl = el('dailyLevel');
    if (levelEl) {
      /* R216b 续3（UX 队列 U-009）：凶日不吓人——标签柔化（「稍缓」），
       * 紧跟一句安抚话术；吉/平保持原样。 */
      levelEl.textContent = (level === '凶') ? '缓' : level;
      levelEl.className = 'daily-level ' +
        (level === '吉' ? 'good' : level === '凶' ? 'bad soft' : 'mid');
      levelEl.title = level === '凶' ? '传统黄历今日标注为「凶」' : '';
    }
    const starsEl = el('dailyStars');
    if (starsEl) {
      starsEl.innerHTML = renderStars(level);
      /* R229z续23（R10-#16）：读屏播报「吉·五星」而非逐个星符 */
      starsEl.setAttribute('aria-label', '今日运势：' +
        (level === '吉' ? '吉，五星' : level === '凶' ? '缓，一星' : '平，三星'));
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
        '「缓」不是坏日子——只是提醒你今天别硬冲，稳稳的也很好。' : '';
      sooth.hidden = (level !== '凶');
    }
    setText('dailyNoble', j.noble || '—');
    setText('dailyDo', j.do || '—');
    setText('dailyDont', j.dont || '—');
    renderCheckin(j.date);   // R214b：今日玄学搭子打卡互动
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
  }
}

function renderStars(level) {
  const good = '<span class="star-good">★</span>';
  const mid = '<span class="star-mid">☆</span>';
  const bad = '<span class="star-bad">★</span>';
  if (level === '吉') return good.repeat(5);
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
  target.innerHTML = '<div class="no-evidence">正在推算今日完整解读…</div>';
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
    const ad = val('ask_date');
    if (ad) body.ask_date = ad;
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
  var presets = {
    bazi:    { icon: '/static/cream/cream-icon-bazi.jpg',    txt: '你的命盘已就位', grad: 'linear-gradient(120deg,#FFF1F3,#E4D4FF)' },
    qiming:  { icon: '/static/cream/cream-icon-qiming.jpg',  txt: '给孩子起个好名字', grad: 'linear-gradient(120deg,#F0FFF4,#E4FFE9)' },
    taohua:  { icon: '/static/cream/cream-icon-taohua.jpg',  txt: '你的缘分在路上了', grad: 'linear-gradient(120deg,#FFE4E9,#FFD6E0)' },
    tarot:   { icon: '/static/cream/cream-icon-tarot.jpg',   txt: '静心抽牌，答案就在眼前', grad: 'linear-gradient(120deg,#F3EBFF,#FFE4E9)' },
    hehun:   { icon: '/static/cream/cream-icon-hehun.jpg',   txt: '缘分配对，一拍即合', grad: 'linear-gradient(120deg,#FFE4E9,#FFF1F3)' },
    huangli: { icon: '/static/cream/cream-icon-huangli.jpg', txt: '择个好日子，事事顺心', grad: 'linear-gradient(120deg,#FFF8E1,#FFE9C9)' },
    xingzuo: { icon: '/static/cream/cream-icon-xingzuo.jpg', txt: '星空为你指路', grad: 'linear-gradient(120deg,#E4F0FF,#E4D4FF)' },
    liuyao:  { icon: '/static/cream/cream-icon-liuyao.jpg',  txt: '心诚则灵，卦象自明', grad: 'linear-gradient(120deg,#FFF1F3,#F3EBFF)' }
  };
  var p = presets[view];
  if (!p) return '';
  return '<div class="deco-banner deco-' + view + '" style="background:' + p.grad + ';">' +
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
        ? renderHits(j.evidence, { empty: '无引文' })
        : '<p style="color:var(--secondary);font-size:13px;">这次没检索到可引的古籍原文——坐标还在，解读照常。</p>';
    }
  }
  // R000a-04：原读 j.llm_out（后端从来没这个键）→ 现读 interpretation。
  html += renderVoice(j, '📖 解读（确定性规则）', ['evidence']);
  html += '</div>';
  return html;
}

var _submitBaziBusy = false;   /* R8 P2-2：form submit 不经 on()，自加在途锁 */
var _submitBaziLast = { key: '', ts: 0 };   /* R230q（R28-P3-14）同参防抖 */
async function submitBazi(event) {
  if (event) event.preventDefault();
  if (_submitBaziBusy) return;   // 连点/回车连击 → 只发一次，防并发覆盖
  _submitBaziBusy = true;
  busy('result', '计算中…');
  try {
    const body = baziBody();
    /* R230q（R28-P3-14）：锁随响应释放后连击仍会各发一遍——同参数
     * 1.5s 内复用上次结果（历史台账不再被刷出重复行）。 */
    var _bkey = JSON.stringify(body);
    if (_bkey === _submitBaziLast.key &&
        Date.now() - _submitBaziLast.ts < 1500) {
      paint('result', '<div class="no-evidence">这盘刚算过，结果就是上面那张～</div>');
      return;
    }
    /* R230f续4（R16-P2-4b）：与出生抽屉同一套预检——空/越界不走
     * 请求，直接站内中文提示（原来要等一轮 422）。 */
    if (body.year == null || body.month == null || body.day == null
        || body.year < 1900 || body.year > 2100
        || body.month < 1 || body.month > 12 || body.day < 1 || body.day > 31) {
      paint('result', '<div class="no-evidence">日期看起来不太对，检查一下年月日再试～</div>');
      return;
    }
    WARM_LAST_QUESTION = body.question || '';   /* R206b US4：共情模板选择依据 */
    const j = await postJSON('/api/bazi', body);
    /* 只在成功后记账——失败重试（failWithRetry）不该被同参防抖拦 */
    _submitBaziLast = { key: _bkey, ts: Date.now() };
    const paipan = j.paipan || {};
    /* R206b US1：给陪伴层喂坐标事实（干支五行词，非 PII——不含生日） */
    try {
      const _warmFacts = (j.warm && j.warm.details || [])
        .map(function (d) { return d.title + '：' + (d.lines || []).slice(0, 2).join('；'); })
        .slice(0, 3);
      const _pp = paipan.render || '';
      CHAT_LAST_FACTS = (_pp ? ['四柱：' + _pp] : []).concat(_warmFacts);
    } catch (e) { CHAT_LAST_FACTS = []; }
    paint('result', buildBaziResult(j));
    rememberVoice('result', j, buildBaziResult);
    rememberResult('bazi', j, body.question || '', body);   /* R219b（P0-2）：聊聊上下文；v2 补 body（性别） */
    revealResult('result');            // 005 判据 1：提交后无需滚动即见结论
    /* R230n续（R23-P3-6）：排盘成功广播脏标——其他 tab 的历史列表即时失效。 */
    try {
      if (window.BroadcastChannel) {
        new BroadcastChannel('paipan_history').postMessage('dirty');
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
    fail('searchResult', '请输入查询词');
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
    fail('researchResult', '请输入查询词');
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
      html += '<div class="no-evidence">已拒答（G7 证据不足）：' +
        esc(j.reason || '命中全部位于质量闸门标记区') + '</div>';
    }
    if (j.steps && j.steps.length) {
      html += '<h3>检索链路</h3><ol class="step-list">';
      j.steps.forEach(function (s) {
        html += '<li>' + esc(s.action || '') + ' 「' + esc(s.query || '') + '」 → found ' +
          esc(s.found) + ' / kept ' + esc(s.kept) +
          (s.note ? '（' + esc(s.note) + '）' : '') + '</li>';
      });
      html += '</ol>';
    }
    if (j.comparisons && j.comparisons.length) {
      html += '<h3>同址版本分歧</h3>';
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
      '<p class="hit-cite">' + esc(j.scheme) + ' · 命中 ' + esc(j.count) + ' 条</p>' +
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
    let html = '<h3>' + esc(j.addr || '') + '　基准：' + esc(j.reference || '') +
      '　' + (j.agree ? '各见证一致' : '存在差异') + '</h3>';
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
      fail('worksResult', '暂无书目');
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
        '<p style="font-size:11px;color:var(--secondary);">单元 · 编址率 ' +
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
  doSearch();
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
    let html = '<div class="no-evidence">线程已创建：#' + esc(j.thread_id) +
      '（claim #' + esc(j.derived_id) + '）</div>' +
      /* R201b（B-005）：展示 claim 内容与证据数——用户能确认「记下了什么」，
       * 不再只回一行 id（响应键 claim/n_evidence 原本零引用）。 */
      '<div class="calc-block" style="margin:10px 0;">' +
      '<p style="font-size:14px;line-height:1.6;">' + esc(j.claim || '') + '</p>' +
      (j.n_evidence != null ? '<p style="font-size:12px;color:var(--secondary);">证据 ' +
        esc(j.n_evidence) + ' 条</p>' : '') + '</div>';
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
    html += '<div class="thread-item"><div class="thread-topic">' +
      esc(t.topic || '') + '</div>' +
      '<div class="thread-meta">#' + esc(t.id) + ' · ' + esc(t.status) +
      ' · ' + esc(t.turns) + ' turns / ' + esc(t.claims) + ' claims · ' +
      esc(t.updated_at || '') + '</div>' +
      '<div class="thread-actions">' +
      '<button class="thread-view" type="button" data-thread="' + esc(t.id) +
      '">查看</button>' +
      '<button class="thread-del" type="button" data-thread-del="' + esc(t.id) +
      '" aria-label="删除线程 #' + esc(t.id) + '">删</button></div></div>';
  });
  return html;
}

async function deleteThread(tid) {
  if (!window.confirm('删掉这条线程？（里面的研究结论会保留为独立记录）')) return;
  try {
    await api('/api/threads/' + encodeURIComponent(tid), { method: 'DELETE' });
    showToast('线程已删除', 'success');
    /* 列表与详情共用 threadResult——重拉列表覆盖回列表态 */
    const html = await _threadListHtml();
    paint('threadResult', html || '<div class="no-evidence">暂无线程</div>');
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
        '">' + esc(t.role) + '：' + esc(t.text || '') + '</div>';
    });
    (j.claims || []).forEach(function (c) {
      html += '<div class="claim-box"><span class="claim-kind">' + esc(c.kind) +
        '</span>' + esc(c.claim || '') +
        '<span class="claim-conf">' + esc(c.confidence || '') + '</span>';
      (c.evidence || []).forEach(function (ev) {
        html += '<div class="claim-ev">' + esc(ev.role) + ' · ' + esc(ev.work_id) +
          ' @' + esc(ev.page_anchor || '') + '：' + esc(ev.quote || '') + '</div>';
      });
      html += '</div>';
    });
    if (j.verify) {
      html += '<div class="interp-basis">证据回查：ok ' + esc(j.verify.ok) +
        ' / stale ' + esc(j.verify.stale) + '</div>';
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
        '<h3 style="color:' + c + ';">《' + esc(w.title || w.work_id) + '》 命中 ' +
        esc(w.n_hits) + ' 条' + (w.truncated ? '（已截断）' : '') + '</h3>' +
        '<p style="font-size:12px;color:var(--secondary);">层分布：' +
        esc(fmtScalar(w.layers)) + '</p>';
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
      html += '<h3 style="margin-top:16px;">两书同址命中（分歧起点）</h3>';
      // R228o：shared_addresses 项只有 {addr}（research.compare_works），
      // 两书命中是集合语义本身——旧代码读不存在的 s.works 会渲染出
      // "undefined"（契约探针实测抓获的真漂移）。
      shared.forEach(function (s) {
        html += '<div class="finding">' + esc(s.addr || '') + '</div>';
      });
    } else {
      html += '<div class="no-evidence">两书无共享地址命中</div>';
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
    fail('conceptResult', '请输入概念词');
    return;
  }
  try {
    const j = await api('/api/concept?' + new URLSearchParams({ q: q }).toString());
    let html = '<h3>「' + esc(j.concept || q) + '」在 ' + esc(j.works_with_hits) +
      ' 部书中有命中' + (j.truncated ? '（扫描上限 ' + esc(j.scan_limit) + '）' : '') +
      '</h3>';
    html += '<table class="works"><thead><tr><th>书</th><th>命中</th><th>层分布</th>' +
      '</tr></thead><tbody>';
    (j.census || []).forEach(function (row) {
      html += '<tr><td>《' + esc(row.title || row.work_id) + '》</td>' +
        '<td class="num">' + esc(row.n_hits) + '</td>' +
        '<td>' + esc(fmtScalar(row.layers)) + '</td></tr>';
    });
    html += '</tbody></table></div>';
    const shared = j.shared_addresses || [];
    if (shared.length) {
      html += '<h3 style="margin-top:16px;">同址多见证地图</h3>';
      shared.forEach(function (s) {
        html += '<div class="finding">' + esc(s.addr || '') + '　' +
          esc(fmtScalar(s.works)) + '</div>';
      });
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
    fail('bsStructure', '请输入书 ID（如 KR1a0001）');
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
    html += '<table class="works"><thead><tr><th>节</th><th>单元</th><th>字数</th>' +
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
    fail('bsChapter', '请输入书 ID（如 KR1a0001）');
    return;
  }
  if (!scheme) {
    fail('bsChapter', 'scheme 不能为空（NULL 体系的书请用「结构」页看文件节）');
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
      esc(j.section) + ' 节 · ' + esc(j.n_units) + ' 单元</h3>';
    (j.units || []).forEach(function (u) {
      html += '<div class="ev-item"><div class="ev-meta">' + esc(humanCite(u.citation || '')) +
        (u.addr2 ? ' · ' + esc(u.addr2) : '') + (u.layer ? ' · ' + esc(u.layer) : '') +
        (u.suspect ? ' ⚠ suspect' : '') + '</div>' +
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
    fail('bsSummary', '请输入书 ID（如 KR1a0001）');
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
    [
      ['体裁', j.genre], ['地址体系', j.scheme], ['节数', j.n_sections],
      ['单元数', j.n_units], ['总字数', j.total_chars],
      ['层分布', fmtScalar(j.layers)], ['未编址单元', j.unaddressed_units],
      ['质量标记单元', j.suspect_units], ['跳字单元', j.skipped_chars_units],
      ['最大节', fmtScalar(j.largest_section)],
      ['最小节', fmtScalar(j.smallest_section)]
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
        html += '<div class="yao-row' + (ln.moving ? ' moving' : '') + '">' +
          '<span class="yao-name">' + esc(YAO_NAME[ln.position] || ('第' + ln.position + '爻')) +
          '</span><span class="yao-sym">' +
          esc((ln.symbol || (ln.yang ? '⚊' : '⚋')) ) + mark + '</span></div>';
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
    html += renderVoice(j, '📖 卦象转述（确定性规则）', ['ben_jing', 'bian_jing']);
  }
  /* R221b：交叉引用收口 7/7——六爻不收生日，引今天值宫 × 动爻多寡。
   * 放在 if/else 之外：温柔版与专业版都该看到这段。 */
  if (j.cross_ref && j.cross_ref.message) {
    html += '<div class="cross-ref"><span class="cross-ref-icon">☯️</span>' +
      esc(j.cross_ref.message) + '</div>';
  }
  html += '</div>';
  return html;
}

/* R216b 续（U-007）：时间起卦的年月日默认取「打开页面的当天」——原 HTML
 * 写死 1990/5/15，用户不看日期直接摇就会用错时间坐标。进视图时同步一次。 */
function syncLiuyaoToday() {
  const t = new Date();
  const setv = function (id, v) { const e2 = document.getElementById(id); if (e2) e2.value = v; };
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
  }
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
      fail('lyResult', '年份要在 1900–2100 之间');
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
  return '<span class="qm-score" title="契合度评分：缺补权重·音韵·出处完整">⭐ ' +
    score + '/100</span>' + badge;
}

async function doQiming() {
  if (_qmBusy) return;                        /* R230j */
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
          esc(n.full_name || '') + '</h3>' +
          '<p style="font-size:13px;color:var(--secondary);">五行：' +
          esc((n.elements || []).join('·')) +
          (n.form === 'single' ? '　单字名' : '　双字名') + '</p>' +
          '<div class="qm-parts">' + chips + '</div>';
        if (n.story) {
          html += '<p style="font-size:13px;margin-top:4px;">📜 ' + esc(n.story) + '</p>';
        } else if (n.meanings) {
          html += '<p style="font-size:13px;">' + esc(n.meanings) + '</p>';
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
    /* R229z续23（R11-#4）：起名卡此前全程无免责徽标 */
    html += '<div style="font-size:12px;color:var(--muted);margin-top:10px;">名字综合古籍意象与五行给的参考，仅供娱乐——孩子的名字还是家里人说了算 ✨</div>';
    html += '</div></div>';
    paint('qmResult', html);
    rememberResult('qiming', j, '', { gender: val('qm_gender') });   /* v2：补性别（用户反馈 bug F3） */
    on('nameReviewBtn', function () {
      const btn = el('nameReviewBtn');
      if (btn) btn.disabled = true;
      const names = (j.full_names || []).map(function (n) {
        return n.full_name || '';
      }).filter(Boolean).slice(0, 6);
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
  busy('thResult', '计算中…');
  try {
    const j = await postJSON('/api/taohua', {
      year: num('th_year'),
      month: num('th_month'),
      day: num('th_day'),
      hour: num('th_hour'),
      gender: val('th_gender') || '女'
    });
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
      html += '<h3 style="margin-top:16px;">大运桃花应期</h3>' +
        '<table class="works"><thead><tr><th>运</th><th>干支</th><th>约起年</th>' +
        '</tr></thead><tbody>';
      j.dayun_hits.forEach(function (d) {
        html += '<tr><td>第 ' + esc(d.index) + ' 运</td><td>' + esc(d.pillar) +
          '</td><td class="num">' + esc(d.year_start) + '</td></tr>';
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
    html += '</div>';
    paint('thResult', html);
    rememberResult('taohua', j, '', { gender: val('th_gender') });   /* v2：补性别 */
    revealResult('thResult');
    pollAiPolish('thResult', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    on('shareTaohua', function () { downloadPoster(j, 'taohua'); });   /* R218a-巡2（N-04）：改用 taohua 专属 case */
  } catch (e) {
    failWithRetry('thResult', '测算失败：' + e.message, function () { doTaohua(); });
  }
}



/* ── v4 交接修复：上一轮恢复函数时丢失的常量块，自 v3 快照原样找回 ── */
/* R209b：已批准海报背景预加载（_candidates 目录，同源） */
var POSTER_BG = {
  /* R230r（R29-#6）：night 预加载后没有任何绘制方使用——白拉一张图，摘掉。 */
  warm: new Image()
};
var TAROT_MANIFEST = null;      /* 惰性拉取，见 tarotImg() */

/* R228k：原来顶层立刻拉三张图（~95KB）——海报背景只在点「存成图」才用，
 * manifest 只在塔罗视图才用。挪进 requestIdleCallback（无此 API 则
 * load 后 2s），首屏瀑布不再为低频路径买单。 */
function _idlePrefetch() {
  POSTER_BG.warm.src = '/static/_candidates/r212b/poster-bg-peach.png';
  fetch('/static/tarot/manifest.json')
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (j) { TAROT_MANIFEST = j || {}; })
    .catch(function () { TAROT_MANIFEST = {}; });
}
if (typeof requestIdleCallback === 'function') {
  requestIdleCallback(_idlePrefetch, { timeout: 4000 });
} else {
  window.addEventListener('load', function () { setTimeout(_idlePrefetch, 2000); });
}

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
  var art = img
    ? '<div class="tart"><img src="' + img + '" alt="' + esc(d.name) + '"></div>' +
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
      '<div class="tarot-card-face tarot-card-back"><img class="tbimg" src="/static/tarot/card-back.jpg" alt=""></div>' +
      '<div class="tarot-card-face tarot-card-front">' + tarotFace(d) + '</div>' +
      '</div></div>' +
      '<div class="tarot-pos">' + esc(d.position || ('第' + (i + 1) + '张')) +
      '</div></div>';
  });
  html += '</div>';
  /* R207b：塔罗深读——多牌综合叙事 + 针对用户的具体指引。
   * 确定性模板层（同输入同输出），写死前端不动 voice 基线。 */
  html += tarotDeepRead(j.draws || [], j.question);
  /* R221b：交叉引用收口 7/7——塔罗不收生日，引今天值宫 × 牌面正逆同调 */
  if (j.cross_ref && j.cross_ref.message) {
    html += '<div class="cross-ref"><span class="cross-ref-icon">🔮</span>' +
      esc(j.cross_ref.message) + '</div>';
  }
  html += renderVoice(j, '📖 牌面转述（确定性规则）');
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
      false: '**身体在喊停**——先停下来休息一天，熬夜的代价明早会还给你。'
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
      quiet: '**对应你问的身体**：当下状态稳，保持就好——别熬最深的夜、吃最凉的。',
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
  return html;
}


async function doTarot() {
  busy('trResult', '抽牌中…');
  /* R216b 续（U-006）：Seed 字段收进高级折叠，留空=用户不关心复验，
   * 前端自动生成一个编号（仅用于「同牌可复验」说明，不影响体验）。 */
  const seedRaw = val('tr_seed');
  const seed = (seedRaw === '' || seedRaw == null) ?
    (Date.now() % 1000000) : num('tr_seed');
  const n = num('tr_n');
  const body = { n: n == null ? 3 : Math.min(Math.max(n, 1), 10) };
  /* R230d（R16-P2-5）：静默钳位会让用户以为抽了输入的张数——
   * 超界时吱一声（防呆提示，不阻断）。 */
  if (n != null && n !== body.n) {
    showToast('牌数最多 10 张，已按 ' + body.n + ' 张抽', 'info');
  }
  if (seed != null) body.seed = seed;
  const q = val('tr_question');
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
      trBtn.textContent = '🔀 分享图';
      trBtn.style.margin = '10px 0 0';
      trCard.appendChild(trBtn);
      trBtn.addEventListener('click', function () { downloadPoster(j, 'tarot'); });
    }
    // 翻牌：逐张延迟触发（纯 CSS transform，prefers-reduced-motion 已在 CSS 里关）
    (j.draws || []).forEach(function (_d, i) {
      setTimeout(function () {
        const inner = document.querySelector('.tarot-card-inner[data-card="' + i + '"]');
        if (inner) inner.classList.add('flipped');
      }, 300 + i * 200);
    });
  } catch (e) {
    failWithRetry('trResult', '抽牌失败：' + e.message, function () { doTarot(); });
  }
}


async function doHehun() {
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
      b_gender: val('hh_b_gender') || '女'
    });
    const a = j.a_bazi || {};
    const b = j.b_bazi || {};
    let html = '<div class="card"><h2>💕 八字合婚</h2>';
    // R193b：分享海报入口（对齐排盘 shareBazi，T3.1 同款零依赖 Canvas）
    html += '<button class="ghost fav-btn" type="button" id="shareHehun" ' +
      'title="生成分享图">📸 分享图</button>';
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
      '<h3 style="color:var(--c-bazi);">甲</h3>' +
      '<p style="font-family:var(--font-serif);font-size:18px;">' +
      esc(a.year || '') + ' · ' + esc(a.day || '') + '</p>' +
      '<p style="font-size:13px;color:var(--secondary);">日主：' +
      esc(a.day_master || '') + '（' + esc(j.day_wx_a || '') + '）</p></div>';
    html += '<div class="calc-block" style="border-left:3px solid var(--c-hehun);">' +
      '<h3 style="color:var(--c-hehun);">乙</h3>' +
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
      ((j.day_wx_sheng || j.day_wx_same) ? 'var(--c-good)' : 'var(--c-bazi)') + ';">日主五行：' +
      esc(j.day_wx_sheng ? '相生' : (j.day_wx_same ? '比和' : '非相生')) + '</span>';
    html += '<span class="pill sm" style="background:var(--c-taohua);">桃花（' +
      esc(j.peach_a || '') + '/' + esc(j.peach_b || '') + '）：' +
      esc(j.peach_same ? '重叠' : '不同') + '</span>';
    // R204b（D-257b）：天干五合 + 十神互见 pill（yinyuan skill 融入）
    if (j.gan_he) {
      html += '<span class="pill sm" style="background:var(--c-good);">日干五合：天生对味</span>';
    }
    if (j.god_a_sees_b && j.god_b_sees_a) {
      html += '<span class="pill sm" style="background:var(--secondary);">十神互见：' +
        esc(j.god_a_sees_b) + '/' + esc(j.god_b_sees_a) + '</span>';
    }
    html += '</div>';
    if (j.render) html += '<div class="calc-summary">' + esc(j.render) + '</div>';
    if (j.dayun_hits && j.dayun_hits.length) {
      /* R216b 续5（UX 队列 U-004）：warm 模式下 8 行干支大运表信息过载，
       * 收进默认折叠（事实零删减）；pro 模式保持平铺。 */
      /* R228n：五列表 320px 下 min-content 超容器 11px→整页横滚；
       * 外包 .table-scroll 让表自己滚。 */
      var _table = '<div class="table-scroll"><table class="works"><thead><tr><th>大运</th><th>甲干支</th><th>乙干支</th>' +
        '<th>关系</th><th>约起年</th></tr></thead><tbody>';
      j.dayun_hits.forEach(function (d) {
        _table += '<tr><td>第 ' + esc(d.index) + ' 运</td><td>' + esc(d.pillar_a) +
          '</td><td>' + esc(d.pillar_b) + '</td><td>' + esc(d.relation) +
          '</td><td class="num">' + esc(d.year_start) + '</td></tr>';
      });
      _table += '</tbody></table></div>';
      if (voiceMode() === 'warm') {
        html += '<details class="warm-basis"><summary>📅 大运冲合表（' +
          j.dayun_hits.length + ' 行，展开看）</summary>' + _table + '</details>';
      } else {
        html += '<h3 style="margin-top:16px;">大运冲合应期</h3>' + _table;
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
    html += '</div>';
    paint('hhResult', html);
    rememberResult('hehun', j, '');   /* R219b（P0-2）：双方日柱进第一句 */
    revealResult('hhResult');
    pollAiPolish('hhResult', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    on('shareHehun', function () { downloadPoster(j, 'hehun'); });   /* R218a-巡2（N-04）：改用 hehun 专属 case */
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
  ds.value = String(Math.min(d, days));
}


function xzShiftDay(step) {
  var parts = xzDateStr().split('-');
  var d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  d.setDate(d.getDate() + step);
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
async function doXingzuo(force) {
  xzInitDate();
  var dateStr = xzDateStr();
  var _xzBox = el('xzResult');
  if (!force && _xzLastDate === dateStr && _xzBox && _xzBox.children.length) return;
  busy('xzResult', '查询中…');
  try {
    var j = await api('/api/xingzuo?date=' + encodeURIComponent(dateStr));
    var html = '<div class="xz-result">';
    if (j.today_sign) {
      /* C-002-fix：星座配图 + 今日值宫 */
      var _tk = ({'白羊':'aries','金牛':'taurus','双子':'gemini','巨蟹':'cancer','狮子':'leo','处女':'virgo','天秤':'libra','天蝎':'scorpio','射手':'sagittarius','摩羯':'capricorn','水瓶':'aquarius','双鱼':'pisces'})[j.today_sign] || 'aries';
      html += '<div class="xz-today"><img class="xz-today-img" src="/static/cream/zodiac-' + _tk + '.jpg" alt="" onerror="this.classList.add(\'is-missing\')"><span class="xz-today-label">今日值宫</span><span class="xz-today-sign">' + esc(j.today_sign) + '</span></div>';
      /* C-002：星座详情页——爱情/事业/财运分维度 */
      var _todayDetail = (j.signs || []).filter(function (s) { return s.is_today; })[0];
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
        html += '<div class="xz-card' + cls + '"><img class="xz-card-img" src="/static/cream/zodiac-' + _zk + '.jpg" alt="' + esc(s.sign) + '" loading="lazy" onerror="this.classList.add(\'is-missing\')"><div class="xz-card-body"><span class="xz-name">' + esc(s.sign) + '</span><span class="xz-note">' + esc(s.note) + '</span></div></div>';
      });
      html += '</div>';
    }
    /* R229z续23（R11-#5）：星座结果卡补免责 */
    html += '<div style="font-size:12px;color:var(--muted);margin-top:10px;">星座日运看个开心，不构成任何建议 ✨</div>';
    html += '</div>';
    paint('xzResult', html);
    _xzLastDate = dateStr;   /* R228f */
    rememberResult('xingzuo', j, '');   /* R219b（P0-2）：今日值宫进第一句 */
    revealResult('xzResult');
    /* R230d（R16-P2-2）：星座分享按钮（其他五个测算页都有，独缺这里）。 */
    var xzCard2 = el('xzResult');
    if (xzCard2 && !document.getElementById('shareXingzuo')) {
      var xzBtn = document.createElement('button');
      xzBtn.className = 'ghost fav-btn';
      xzBtn.id = 'shareXingzuo'; xzBtn.title = '生成分享图';
      xzBtn.textContent = '🔀 分享图';
      xzBtn.style.margin = '10px 0 0';
      xzCard2.appendChild(xzBtn);
      xzBtn.addEventListener('click', function () { downloadPoster(j, 'xingzuo'); });
    }
  } catch (e) {
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
  '搬家': ['移徙', '移徒', '入宅', '修造', '平整'], '挪窝': ['移徙', '移徒'],
  '远行': ['出行'], '装修': ['修造', '动土'],
  '开业': ['开市', '纳财'], '开张': ['开市'], '签约': ['立券', '纳财'], '合同': ['立券'],
  '出行': ['出行', '远行'], '旅行': ['出行', '远行'], '旅游': ['出行', '远行'],
  '出差': ['出行', '远行'], '出游': ['出行', '远行'], '出国': ['出行', '远行'],
  '出门': ['出行', '远行'],
  '收款': ['纳财'], '理财': ['纳财'], '看病': ['求医', '治病', '求医疗病'],
  '种花': ['栽植', '栽种'],
  '理发': ['冠笄'], '剪发': ['冠笄'], '剪头': ['冠笄'], '剃头': ['冠笄'],
  '美发': ['冠笄'], '烫头': ['冠笄'],
  '手术': ['求医', '治病', '求医疗病'], '开刀': ['求医'], '体检': ['求医'], '洗牙': ['求医'],
  '拔牙': ['求医'], '医美': ['求医'], '整容': ['求医'],
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
  '运动': ['健身'], '唱k': ['唱歌'],
  '许愿': ['祈福', '求嗣'], '拜拜': ['祭祀'], '祭灶': ['祭祀'], '祭祖': ['祭祀'], '考试': ['入学'], '上学': ['入学'],
  '开学': ['入学'],
  /* R230h（R20-F1）：与后端 _CHAT_SCENE_TERMS 同步增键（parity 钉扎）。 */
  '备孕': ['求嗣'], '求子': ['求嗣'], '要孩子': ['求嗣'], '生子': ['求嗣'],
  '怀孕': ['求嗣']
};
function _hlSceneAlias(sc) { return (HL_SCENE_ALIAS[sc] || []).slice(); }
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
  s = s.replace(/(除夕|春节|春節|大年初一|元宵节|元宵節|端午节|端午節|端午|七夕|中秋节|中秋節|中秋|重阳节|重陽節|重阳|重陽|腊八节|臘八節|腊八|臘八|清明节|清明節|清明|立春|雨水|惊蛰|驚蟄|春分|谷雨|穀雨|立夏|芒种|芒種|夏至|处暑|處暑|白露|秋分|寒露|霜降|立冬|冬至|大暑|小暑|元旦|新年|情人节|情人節|妇女节|婦女節|植树节|植樹節|愚人节|愚人節|劳动节|勞動節|青年节|青年節|儿童节|兒童節|建党节|建黨節|建军节|建軍節|教师节|教師節|国庆节|國慶節|国庆|國慶|万圣节|萬聖節|平安夜|圣诞节|聖誕節|圣诞|聖誕|跨年|母亲节|母親節|父亲节|父親節|感恩节|感恩節|中元节|中元節|中元|小年|双十一|雙十一|光棍节|光棍節|月底|月末|月初|下个?月|上个?月|这个?月|\d{1,2}\s*[月\/\-.]\s*\d{1,2}\s*[日号]?|\d{1,2}\s*[号日])(的?前[一二三四五六两]?[天日]?|的?后[一二三四五六两]?[天日]?|之前|之后|当天|当日)?/g, '');
  /* 多字节后缀（前一天/次日/的后三天…）总是日期修饰，无锚直接剥；
   * 裸「前/后」只在串尾剥（「前后矛盾」是真词）。 */
  s = s.replace(/(前一天|前两天|前三天|头一天|头两天|的后?一?两?三天|的后两天|之后|后一天|后两天|次日|第二天|当天|当日)/g, '');
  s = s.replace(/[前后]$/, '');
  s = s.replace(/^(我|我们|咱|俺)?\s*((想|想要|打算|准备|计划|要|去|做|搞|弄|干|知道|看看|问问|问下|求问|感觉|感到|觉得)+)/, '');
  s = s.replace(/(适不适合|可不可以|能不能|行不行|宜不宜|好不好|合不合适|吉利不吉利|适合|可以|能|宜|吉利|合适|稳妥|怎么样|怎么办|咋办|行吗|如何|的话|好吗)/g, '');
  /* 「地」不进助词表——「外地/地铁」是真字；连接词单独剥。 */
  s = s.replace(/[吗呢吧啊呀？?!！!，,。.、~～\s的了]/g, '');
  /* 「去/到」不进全局表——「去年→年」「到家→家」是真字伤害；句首/能后的
   * 「去爬山」由上行引导剥离覆盖。 */
  s = s.replace(/(帮|给|跟|和|与|向|让|为|个|只|把|被|在)/g, '');
  s = s.replace(/^(去|做|干|搞)+/, '');
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
  if (/周末|週末/.test(s)) {
    var b3 = base || new Date();
    return (5 - ((b3.getDay() + 6) % 7) + 7) % 7; /* 下个周六 */
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
function _hlNoSceneNote(yi, ji, day, conflict) {
  /* R228c：「没直接管」生硬且与后端口径不齐，统一「没直接提」。
   * R230h（R20-F7）：相冲词摘出主推行（与 _hlVerdictHtml 同款）。 */
  var _cfl = {}; (conflict || []).forEach(function (w) { _cfl[w] = 1; });
  var _yi = yi.filter(function (w) { return !_cfl[w]; });
  var _ji = ji.filter(function (w) { return !_cfl[w]; });
  return '这个黄历没直接提——' + (day || '今天') + '主推【' + (_yi.join('、') || '无') + '】' +
    (_ji.length ? '，忌【' + _ji.join('、') + '】' : '') +
    '；没在宜忌里的事照常安排不犯冲～想问具体的事就带上它，比如「适合搬家吗」。';
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
  var hitJi = _hit(ji, aliases, JI_MAP);
  var why = '（' + day + '黄历主推' + (_yiClean.length ? '【' + _yiClean.join('、') + '】' : '的内容不多') +
    (_jiClean.length ? '，忌【' + _jiClean.join('、') + '】' : '') + '）';
  var verdict;
  if (hitYi.length && !hitJi.length) {
    verdict = day + '适合' + sc + ' ✅ —— 凭据：宜项里有【' + hitYi.join('、') + '】' + why;
  } else if (hitJi.length && !hitYi.length) {
    verdict = day + '不宜' + sc + ' 🚫 —— 因为忌项里有【' + hitJi.join('、') + '】' + why;
  } else if (hitYi.length && hitJi.length) {
    /* R228c：补谓语——「今天搬家宜忌都有」不通，「今天搬家的宜忌都有」
     * 与兄弟分支「今天适合/不宜搬家」同构。 */
    verdict = day + sc + '的宜忌都有 —— 宜【' + hitYi.join('、') + '】但也忌【' + hitJi.join('、') + '】，想做就把节奏放稳、别赶大动作';
  } else {
    /* R228c：同句「黄历/老黄历」混用统一为「黄历」（全站功能名口径）。 */
    verdict = day + '黄历的宜忌里没有直接提到' + sc + ' —— 不是不支持，只是黄历' + day + '没为它背书（' +
      (yi.length ? '主推【' + yi.join('、') + '】' : day + '宜项不多') +
      '）；' + sc + '可照常安排，想要黄历背书可以翻后面几天挑宜' + sc + '的日子';
  }
  return '<div class="hl-verdict" id="hlVerdict">' + esc(verdict) + '</div>';
}

/* 黄历页的跨调用状态（场景/目标日文案/滚动位/问一嘴待写标记）。
 * R228a：以前挂在 doHuangli 函数对象属性上（doHuangli._scene …）——合法
 * 但踩中 probe_dollar_misuse「函数当对象用」红线，换成纯数据对象更干净。 */
var _HL = {scene: '', dayWord: '', keepSy: null, pendingAskNote: false};

/* R229z：本地 _hlDayOffset 解不动、但后端能解的日期词（节日/农历）——
 * 命中时问一嘴提交走 /api/huangli/resolve_date 兜底。与后端
 * _HOLIDAY_SOLAR/_HOLIDAY_LUNAR/除夕/清明 对齐维护。 */
/* R229z续9：节气词也走兜底（小满=吉祥物名不进；大雪/小雪/大寒/小寒
 * 天气歧义不进——与后端 _SOLAR_TERMS 同表）。 */
var _HL_COMPLEX_DATE = /农历|農曆|阴历|陰曆|旧历|舊曆|闰|閏|正月|冬月|腊月|臘月|除夕|春节|春節|大年初一|元宵|端午|七夕|中秋|重阳|重陽|腊八|臘八|清明|立春|雨水|惊蛰|驚蟄|春分|谷雨|穀雨|立夏|芒种|芒種|夏至|处暑|處暑|白露|秋分|寒露|霜降|立冬|冬至|大暑|小暑|元旦|新年|情人|植树|植樹|愚人|劳动|勞動|五一|青年|儿童|兒童|六一|建党|建黨|建军|建軍|教师|教師|国庆|國慶|万圣|萬聖|平安|圣诞|聖誕|跨年|母亲节|母親節|父亲节|父親節|感恩|中元|小年|双十一|雙十一|光棍/;

/* 「问一嘴」无事项词时的中性提示（当日主推+引导）——提交主路径与
 * resolve_date 兜底复用。 */
function _hlShowNeutral() {
  var _lr = LAST_RESULT['huangli'] && LAST_RESULT['huangli'].json;
  var note = _hlNoSceneNote((_lr && _lr.yi) || [], (_lr && _lr.ji) || [],
    _HL.dayWord || '今天', (_lr && _lr.conflict) || []);
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
async function doHuangli(offset, reveal, spokenWord) {
  if (_hlBusy) return;
  _hlBusy = true;
  try { return await _doHuangli(offset, reveal, spokenWord); }
  finally { _hlBusy = false; }
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
    const j = await api('/api/huangli?' + new URLSearchParams({ date: dateStr }).toString());
    var YI_MAP = {
      '嫁娶': '表白 / 约会好日子', '开市': '开业 / 发新作品', '出行': '出门走走',
      '祭祀': '整理心情', '祈福': '许愿', '求嗣': '备孕', '上任': '入职接项目',
      '入学': '开学学新东西', '立券': '签合同', '纳财': '收款理财', '修造': '装修修缮',
      '动土': '开工', '平整': '整理归置', '安床': '布置房间',
      '冠笄': '形象焕新', '解除': '化解矛盾', '治病': '看病调理', '栽植': '种花种树',
      '捕捉': '清掉拖了很久的小事', '求医': '看医生', '破土': '动工', '安葬': '告别过去'
    };
    var JI_MAP = {
      '出行': '长途奔波容易累', '安葬': '不适合告别式', '祈福': '心诚则灵不必急在今天',
      '开市': '大动作先缓缓', '嫁娶': '感情大事另择日', '动土': '工地噪音惹人烦',
      '诉讼': '容易吵起来', '纳财': '破财风险高，钱包看紧点',   /* R228c：原句「破小心的钱包」不通 */
      '移徙': '搬家挪窝放一放', '移徒': '搬家挪窝放一放',   /* R229z续22：移徒是异体字，词表统一移徙 */
    };
    var yi = (j.yi || []);
    var ji = (j.ji || []);
    var lunar = j.lunar || {};
    var cs = j.cross_ref || {};
    var yiSet = {}; yi.forEach(function (x) { yiSet[x] = true; });
    var html = '';
    /* 头部：日期 + 农历干支 */
    html += '<div class="hl-head" style="background:linear-gradient(120deg,#FFF8E1,#FFE9C9);border-radius:16px;padding:14px 16px;margin-bottom:12px;">';
    html += '<div style="font-size:20px;font-weight:800;color:#7A5F33;">' + esc(j.date || dateStr) + '</div>';
    /* R230n（R25-1.3）：记下本卡实际展示的公历日——跨零点自刷新靠它
     * 判「这张卡是不是昨天的快照」。 */
    if (_hlBox) _hlBox.dataset.shownDate = j.date || dateStr;
    /* R228c：month_cn 本身已带「月」（后端 MONTH_CN 表生成时即带），
     * 再拼一个就成「八月月十九」——直接 month_cn+day_cn。
     * 注意：注释里别写「模块.文件」式点号串——probe_contract 会当字段读取。 */
    /* R229z续19：1900-01-31 前农历表无数据（月名/干支全空）——
     * 「农历  · 」空串残影换成直白说明。 */
    var _lunarTxt = (lunar.month_cn || '') + (lunar.day_cn || '');
    html += '<div style="font-size:13px;color:var(--secondary);margin-top:2px;">' +
      (_lunarTxt
        ? '农历 ' + esc(_lunarTxt) + ' · ' + esc(lunar.ganzhi_year_cn || '')
        : '农历：这一天早于历法表起点（1900-01-31），宜忌仍按干支推') +
      '</div>';
    if (cs && cs.message) html += '<div style="font-size:13px;color:var(--primary-ink);margin-top:6px;">✨ ' + esc(cs.message) + '</div>';
    /* R229z续21c：干支年双口径错位日（春节↔立春窗口）才出现的说明行 */
    if (j.year_note) html += '<div style="font-size:12px;color:var(--muted);margin-top:4px;">📅 ' + esc(j.year_note) + '</div>';
    html += '</div>';
    /* 宜/忌 双色大卡 */
    html += '<div class="hl-yiji" style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">';
    /* R229z续21（R9-P1-2）：宜∩忌同见的词（黄历自相矛盾项，约 22% 日子）
     * 标※并在卡下方附说明——不然同一词两头出现像渲染坏了。 */
    var _conflict = Array.isArray(j.conflict) ? j.conflict : [];
    var _cflSet = {};
    _conflict.forEach(function (w) { _cflSet[w] = 1; });
    html += '<div class="hl-yi" style="background:rgba(135,217,166,.16);border:1px solid rgba(95,167,119,.35);border-radius:16px;padding:12px;">';
    html += '<div style="font-weight:800;color:#3E7A52;margin-bottom:6px;">✅ 宜</div>';
    html += yi.length ? '<div style="display:flex;flex-wrap:wrap;gap:6px;">' +
      yi.map(function (w) {
        var hot = (_HL.scene &&
                   (w.indexOf(_HL.scene) !== -1 || (YI_MAP[w] || '').indexOf(_HL.scene) !== -1));
        return '<span class="hl-pill' + (hot ? ' hl-hot' : '') + '" title="' + esc(YI_MAP[w] || '') + '">' + esc(w) + (_cflSet[w] ? '※' : '') + '</span>';
      }).join('') + '</div>' : '<div class="ph-empty">' + esc(_dayWord) + '没什么特别适宜的</div>';
    html += '</div>';
    html += '<div class="hl-ji" style="background:rgba(255,143,171,.13);border:1px solid rgba(226,98,138,.3);border-radius:16px;padding:12px;">';
    html += '<div style="font-weight:800;color:#C2527B;margin-bottom:6px;">🚫 忌</div>';
    html += ji.length ? '<div style="display:flex;flex-wrap:wrap;gap:6px;">' +
      ji.map(function (w) {
        return '<span class="hl-pill hl-pill-ji" title="' + esc(JI_MAP[w] || '') + '">' + esc(w) + (_cflSet[w] ? '※' : '') + '</span>';
      }).join('') + '</div>' : '<div class="ph-empty">没有特别要避开的</div>';
    html += '</div></div>';
    if (_conflict.length) {
      html += '<div style="font-size:12px;color:var(--muted);margin-top:6px;">※ ' +
        esc(_conflict.join('、')) + ' 宜忌两边都见——黄历自己都打架的日子，' +
        '这类事想做就把节奏放缓，不赶大动作</div>';
    }
    /* 场景 chips：点选高亮匹配宜项
     * R230q（R28-P3-12）：打印时整块隐藏——原先只藏 chip 按钮，
     * 「我打算：」「点一个场景…」两段说明成孤儿文字悬在纸上。 */
    var SCENES = ['搬家', '开业', '约会', '面试', '出行', '签约'];
    html += '<div class="hl-interactive" style="margin-top:14px;"><div style="font-size:13px;color:var(--secondary);margin-bottom:6px;">我打算：</div><div style="display:flex;flex-wrap:wrap;gap:6px;" id="hlScenes">';
    html += SCENES.map(function (s) {
      var ok = yi.some(function (w) { return (YI_MAP[w] || '').indexOf(s) !== -1 || w.indexOf(s) !== -1; });
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
      html += _hlVerdictHtml(_HL.scene, yi, ji, YI_MAP, JI_MAP, _dayWord, j.conflict);
    }
    /* R227b-fix：问一嘴带日期词但没事项词（「明天怎么样」）——翻完那一天
     * 后把主推+引导兜底按目标日写回，不再把「今天」的宜忌安到明天头上。 */
    if (_HL.pendingAskNote) {
      _HL.pendingAskNote = false;
      html += '<div class="hl-verdict" id="hlVerdict">' +
        esc(_hlNoSceneNote(yi, ji, _dayWord, j.conflict)) + '</div>';
    }
    /* v5（用户反馈）：「问一嘴」——用户自由输入「今天适不适合面试」这类问题，
     * 场景词库匹配后给同款带所以然的结论。 */
    html += '<div class="hl-ask" style="margin-top:10px;display:flex;gap:8px;">' +
      '<input id="hlAskInput" class="hl-ask-input" type="text" maxlength="30" aria-label="问一嘴：今天适不适合某事" placeholder="问一嘴：今天适不适合面试/搬家…">' +
      '<button type="button" id="hlAskBtn" class="hl-ask-btn">问</button>' +
      '</div>';
    html += '<div style="font-size:12px;color:var(--muted);margin-top:6px;">点一个场景，看看' + esc(_dayWord) + '合不合适（✓ = 宜项里有它）</div></div>';
    /* 冲煞（R228a TYPE 修复）：后端给的是 {chong, chong_animal, sha_fang}
     * dict，整个 esc() 会渲染成 [object Object]——拼成「冲虎煞南」人话。 */
    var _csTxt = '';
    if (j.chongsha) {
      _csTxt = (typeof j.chongsha === 'string') ? j.chongsha :
        ('冲' + (j.chongsha.chong_animal || j.chongsha.chong || '') +
         (j.chongsha.sha_fang ? '煞' + j.chongsha.sha_fang : ''));
    }
    if (_csTxt) html += '<div class="hl-cs" style="margin-top:12px;font-size:13px;color:var(--secondary);">冲煞：' + esc(_csTxt) + '</div>';
    /* R230a-2：彭祖百忌——接口一直返回但卡面从未露出（黄历标配的两句老话）。
     * 小字收在免责前，不抢戏。 */
    var _pz = j.pengzu || {};
    var _pzTxt = (_pz.gan_text || '') + ((_pz.gan_text && _pz.zhi_text) ? ' · ' : '') + (_pz.zhi_text || '');
    if (_pzTxt) html += '<div style="font-size:12px;color:var(--muted);margin-top:10px;">彭祖百忌：' + esc(_pzTxt) + '</div>';
    /* R230a-11：黄历交叉引用——后端 _cross_ref_huangli 一直返回但卡面
     * 从未露出（星座值宫×当日干支的人话一句）。 */
    if (j.cross_ref && j.cross_ref.message) {
      html += '<div class="cross-ref"><span class="cross-ref-icon">⭐</span>' +
        esc(j.cross_ref.message) + '</div>';
    }
    html += '<div style="font-size:12px;color:var(--muted);margin-top:12px;">黄历按传统历法规则计算，仅供娱乐，不构成决策依据——大事还是相信自己的判断 ✨</div>';
    /* R230d（R16-P2-6）：黄历卡没有 .card 容器，paint 的自动挂钮
     * 找不到宿主——手动挂「聊聊这件事」（其他五个视图都有）。 */
    html += '<button class="chat-entry" type="button" ' +
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
        if (!box || !gj || _HL.scene !== _gsc ||
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
          return '<button type="button" class="hl-daychip" data-hldate="' +
            esc(String(gd.date || '')) + '">' + esc(lab) + '</button>';
        }).join('');
        var tip = document.createElement('div');
        tip.className = 'hl-gooddays';
        tip.innerHTML = '<span class="hl-gooddays-label">近期宜' +
          esc(_gsc) + '：</span>' + chips;
        if (box.nextSibling) box.parentNode.insertBefore(tip, box.nextSibling);
        else box.parentNode.appendChild(tip);
        tip.querySelectorAll('[data-hldate]').forEach(function (b) {
          b.addEventListener('click', function () {
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
    failWithRetry('hlResult', '查询失败：' + e.message,
                  function () { doHuangli(offset, reveal, spokenWord); });
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
      var inp = document.getElementById('hlAskInput');
      var q = inp ? zwClean(inp.value) : '';   /* R230k */
      if (!q) {
        if (inp) inp.placeholder = '先输入想问的事，比如：今天适不适合面试';
        /* R230f续2（R16-P2-4）：placeholder 若已是这段文字则界面纹丝不动，
         * 加一张 toast 让空提交有可感反馈。 */
        showToast('先写一句想问的事再问我哦', 'info');
        return;
      }
      var KNOWN = ['搬家','开业','约会','面试','出行','签约','表白','相亲','结婚','领证','求职','上班','入职','挪窝','装修','开张','合同','旅行','出差','出游','收款','理财','看病','种花'];
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
      var off = _hlDayOffset(q);
      /* R229z：节日/农历等本地解不动的日期词——_hlDayOffset 返回 null 且
       * 词表命中时走 /api/huangli/resolve_date；解出翻页，解不出回退
       * 显示日（与既有 off=null 路径等价）。 */
      if (off == null && _HL_COMPLEX_DATE.test(q)) {
        api('/api/huangli/resolve_date?q=' + encodeURIComponent(q) +
            '&base=' + todayIso(),   /* R230l（R24-P3-4） */
            { silent: true }).then(function (r) {
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
  if (val('bswork')) entry.load();
}

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
    var closed = false;
    document.querySelectorAll('details[open]').forEach(function (d) {
      d.open = false; closed = true;
    });
    if (sb && sb.classList.contains('open')) { _setRecent(false); closed = true; }
    /* 海报模态开着时 Esc 归它（_posterOnKey）——别顺手回首页。 */
    if (!closed && window.__inView && !document.getElementById('posterModal')) {
      showView('home');
    }
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
  /* R206b（US1）：聊天抽屉绑定。chatEntry 是动态按钮（结果区重绘），
   * 用委托绑到 document。 */
  document.addEventListener('click', function (e) {
    if (e.target.closest && e.target.closest('.chat-entry')) {
      chatOpen();
      autoSendChatContext();
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
    chatSend();
  });
  var ci = el('chatInput');
  if (ci) ci.addEventListener('keydown', function (e) {
    /* R230q：与 chatSendBtn 的 on() 点击同锁——连按 Enter 不再并发发消息 */
    if (e.key === 'Enter') guardedCall('chatSendBtn', chatSend, e);
  });
  /* R228q：移动键盘弹出会把侧栏输入框顶出可视区（visualViewport 收缩，
   * 但侧栏是 fixed 布局不跟随）——键盘开合时把输入框滚回视口内。
   * 只在聊天输入聚焦状态下生效；不支持 visualViewport 的环境静默跳过。 */
  if (window.visualViewport) {
    window.visualViewport.addEventListener('resize', function () {
      var inp = el('chatInput');
      if (!inp || document.activeElement !== inp) return;
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
  on('lySubmit', doLiuyao);
  on('hlSubmit', doHuangli);
  on('qmSubmit', doQiming);
  on('thSubmit', doTaohua);
  on('trSubmit', doTarot);
  on('hhSubmit', doHehun);
  /* R229z续23（R10-#14）：占卜系视图不是 <form>，输入框回车无响应——
   * 视图级委托：任意 input 按 Enter = 点本视图主提交钮（原生 form 语义）。 */
  var _ENTER_SUBMIT = {
    'view-liuyao': 'lySubmit', 'view-tarot': 'trSubmit',
    'view-qiming': 'qmSubmit', 'view-taohua': 'thSubmit',
    'view-hehun': 'hhSubmit',
    /* R230d（R16-P1-4）：黄历 y/m/d 三个数字框回车=查这一天
     * （hlAskInput 自带 Enter 绑问一嘴，已被下面的 id 排护栏拦住）。
     * 抽屉输入 b_* 在 <form> 内、原生可回车，不在此列。 */
    'view-huangli': 'hlSubmit'
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
  /* R220b（P1-1）：日期导航——箭头翻天、今天/明天快捷、三 select 改即查 */
  on('xzPrev', function () { return xzShiftDay(-1); });
  on('xzNext', function () { return xzShiftDay(1); });
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

function init() {
  applyTheme(uiTheme());       // 003 判据 12：加载时应用已保存的主题
  /* R198b（US4）：时辰感知背景——按本地小时设五档 daypart。
   * 纯属性设置零动画；不读时钟入任何计算结果（voice 硬纪律不受影响）。 */
  var __h = new Date().getHours();
  var __dp = (__h < 6) ? 'night' : (__h < 10) ? 'dawn' : (__h < 15) ? 'morning'
           : (__h < 19) ? 'noon' : (__h < 22) ? 'dusk' : 'night';
  document.documentElement.setAttribute('data-daypart', __dp);
  initViews();
  initBazi();
  initReading();
  initDivination();
  /* R230q（R28-P2-4）：sid 跨刷新存活则气泡也跨刷新恢复——否则
   * 新消息悄悄接进看不见的上一轮上下文。 */
  _chatTsRestore();
  loadDaily();
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
  var _onDayFlip = function () {
    var t = todayIso();
    if (!t || t === _lastDay) return;
    var prev = _lastDay;
    _lastDay = t;
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
    if (!document.hidden) _onDayFlip();
  });
  setInterval(_onDayFlip, 60000);
  window.addEventListener('storage', function (e) {
    if (e && e.key && e.key.indexOf('checkin:') === 0) {
      renderCheckin(todayIso());
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
    if (!_vp) {
      var _seg = location.pathname.replace(/^\/+|\/+$/g, '');
      if (_seg && _seg.indexOf('/') < 0) _vp = _seg;
    }
    if (_vp) {
      if (document.getElementById('view-' + _vp) &&
          document.querySelector('.func-card[data-view="' + _vp + '"]')) {
        var _hold = window.__suppressPush;
        window.__suppressPush = true;
        try { showView(_vp); } finally { window.__suppressPush = _hold; }
      } else {
        showToast('这个入口不存在，先带你回首页', 'info');
      }
    }
  } catch (e) {}
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
/* ── R213b：微交互特效（点击涟漪 + 星星迸发 / 滑动拖尾 / 卡片入场）──
 * 纪律：全部只动 transform/opacity（check_plain_first 判据 2 门柱安全）；
 * prefers-reduced-motion 下整体停用。 */
(function () {
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  /* 点击涟漪 + 星星迸发 */
  document.addEventListener('click', function (e) {
    var host = e.target.closest('.card, .btn, button, .chat-entry');
    var x = e.clientX, y = e.clientY;
    var ripple = document.createElement('div');
    ripple.className = 'fx-ripple';
    ripple.style.left = x + 'px'; ripple.style.top = y + 'px';
    (host || document.body).appendChild(ripple);
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
const CHECKIN_OPTS = ['开运蛋', '吃瓜运', '摸鱼运', '破水逆运'];
const CHECKIN_FEEDBACK = {
  '开运蛋': ['今天这个运简直像开了挂，冲鸭！', '好运来敲门，接住了别撒手！'],
  '吃瓜运': ['瓜运当头，记得带好小板凳前排围观！', '今天的瓜管够，吃瓜吃到撑～'],
  '摸鱼运': ['摸鱼运爆棚，快乐一下不过分！', '摸鱼时长建议不超过15分钟哦～'],
  '破水逆运': ['霉运走开，今天就是好运本运！', '破水逆运！诸事皆宜的一天开始了～']
};
function renderCheckin(dateKey) {
  const box = document.getElementById('dailyCheckin');
  if (!box) return;
  /* R228h：window.localStorage 属性本身在隐私模式下读就抛——整个 getter 进 try */
  let saved = null;
  try { saved = dateKey ? window.localStorage.getItem('checkin:' + dateKey) : null; }
  catch (e0) { saved = null; }
  const opts = CHECKIN_OPTS.map(function (o) {
    return '<button type="button" class="checkin-opt' +
      (saved === o ? ' picked' : '') + '" data-opt="' + o + '" ' +
      'aria-pressed="' + (saved === o) + '">' + o + '</button>';
  }).join('');
  /* R229z续23（R10-#17）：选项组补 role=group + 问题文本锚点，
   * 反馈区 aria-live——选完有朗读回执。 */
  box.innerHTML = '<div class="checkin-q" id="checkinQ">挑一个今天的好运搭子：</div>' +
    '<div class="checkin-opts" role="group" aria-labelledby="checkinQ">' + opts + '</div>' +
    '<div class="checkin-fx" id="checkinFx" aria-live="polite">' +
    (saved ? pickCheckinFeedback(saved, dateKey) : '') + '</div>';
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
        /* R230j（R22-P3-2）：checkin:* 每日一键永不清理——写今日键时
         * 顺手清掉非今日的旧键（一年 ~365 键的无界增长收口）。 */
        for (var _ci = window.localStorage.length - 1; _ci >= 0; _ci--) {
          var _ck = window.localStorage.key(_ci);
          if (_ck && _ck.indexOf('checkin:') === 0 &&
              _ck !== 'checkin:' + dateKey) {
            window.localStorage.removeItem(_ck);
          }
        }
      } catch (e2) {
        showToast('这次打卡没存上（存储不可用）', 'warn');
        return;
      }
      box.querySelectorAll('.checkin-opt').forEach(function (b) {
        var on = (b.dataset && b.dataset.opt === opt);
        b.classList.toggle('picked', on);
        b.setAttribute('aria-pressed', String(on));   /* R228d */
      });
      const fx = document.getElementById('checkinFx');
      if (fx) fx.textContent = pickCheckinFeedback(opt, dateKey);
    });
  }
}
function pickCheckinFeedback(opt, dateKey) {
  const pool = CHECKIN_FEEDBACK[opt] || [];
  let h = 0; const s = String(dateKey) + opt;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return pool[h % Math.max(1, pool.length)] || '';
}

/** R215b：温柔模式首屏的生日人话线（年支→生肖）。 */
function baziBirthdayLine(paipan) {
  try {
    const yz = String((paipan && paipan.render) || '').split(/\s+/)[0] || '';
    const m = yz.match(/^(.)(.)/);
    const animals = {'子':'鼠','丑':'牛','寅':'虎','卯':'兔','辰':'龙','巳':'蛇',
                     '午':'马','未':'羊','申':'猴','酉':'鸡','戌':'狗','亥':'猪'};
    if (m && animals[m[2]]) return '你是属' + animals[m[2]] + '的呀——这张小卡就是你的底色。';
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
      let m = '没查到这条记录（' + r.status + '）';
      try { const j = await r.json(); if (j && typeof j.detail === 'string') m = j.detail; } catch (e) {}
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
        listEl.innerHTML = '<div class="ph-empty">还没有排盘记录，去首页看看你的盘吧 ✨</div>';
        return;
      }
      listEl.innerHTML = j.items.map(function (it) {
        const ts = (it.ts || '').replace('T', ' ');
        const q = it.question ? '<span class="ph-q">问：' + esc(it.question) + '</span>' : '';
        const render = (it.result_summary && it.result_summary.paipan_render) || '';
        /* R230a-44（R15-P3）：it.id 当前恒为 int，但多行拼接模式逃过单行
         * innerHTML 闸——将来字符串列入同一模式即成洞，先按 esc 纪律统一。 */
        return '<div class="ph-item" data-id="' + esc(String(it.id)) + '">' +
          '<div class="ph-head"><span class="ph-name">' + esc(it.name || ('记录 #' + it.id)) + '</span>' +
          '<span class="ph-ts">' + esc(ts) + '</span></div>' + q +
          '<div class="ph-render">' + esc(render) + '</div>' +
          '<div class="ph-actions"><button type="button" class="ghost ph-open">复看</button>' +
          '<button type="button" class="ghost ph-del">删除</button></div></div>';
      }).join('');
    } catch (e) {
      listEl.innerHTML = '<div class="ph-empty">加载失败：' + esc(_humanizeErr(e.message)) + '（可点上方『刷新』重试）</div>';
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
        tg.classList.add('ph-del-armed');
        setTimeout(function () {
          tg.dataset.armed = '';
          tg.textContent = _origTxt;
          tg.classList.remove('ph-del-armed');
        }, 3000);
        return;
      }
      try {
        await phFetch('/api/paipan/history/' + id, { method: 'DELETE' });
        loadPaipanHistory();
        /* R230n续（R23-P3-6）：删除成功广播脏标，其他 tab 同步刷新。 */
        try {
          if (window.BroadcastChannel) {
            new BroadcastChannel('paipan_history').postMessage('dirty');
          }
        } catch (e2) {}
      }
      /* R228c：错误反馈统一走 toast 体系，不用原生 alert */
      catch (e) { showToast('删除失败：' + e.message, 'error'); }
      return;
    }
    if (item && tg.classList.contains('ph-open')) {
      const id = item.getAttribute('data-id');
      try {
        const rec = await phFetch('/api/paipan/history/' + id);
        const detailEl = document.getElementById('historyDetail');
        if (detailEl && typeof buildBaziResult === 'function') {
          detailEl.innerHTML = buildBaziResult(rec.result || {});
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
    const rf = document.getElementById('historyRefresh');
    if (rf) rf.addEventListener('click', loadPaipanHistory);
    const ex = document.getElementById('historyExport');
    if (ex) ex.addEventListener('click', function () { window.open('/api/paipan/history/export', '_blank'); });
  }
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
      out.innerHTML = '<div class="ph-empty">日期看起来不太对，检查一下年月日再试～</div>';
      return;
    }
    out.innerHTML = '<div class="ph-empty">正在排你的本命盘…</div>';
    try {
      var body = { year: y, month: m, day: d, hour: (hv === '' ? 12 : Number(hv)), gender: g };
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
        '<div><div class="birth-sign">你是 ' + esc(sign) + '座</div>' +
        '<div class="birth-sub">' + esc(SIGN_TXT[sign] || '') + '</div></div></div>';
      html += '<div class="birth-block"><span class="birth-label">你的四柱</span><span class="birth-val">' + esc(pp) + '</span></div>';
      html += '<div class="birth-block"><span class="birth-label">五行分布</span><span class="birth-val">' + esc(wxLine || '—') + (missing.length ? '　<strong>缺 ' + esc(missing.join('')) + '</strong>' : '　五行不缺') + '</span></div>';
      if (warm1) html += '<div class="birth-block"><span class="birth-label">小满悄悄说</span><span class="birth-val">' + esc(warm1) + '</span></div>';
      html += '<div class="birth-note">以上由排盘引擎按你输入的生日实时计算，同生日同时辰的人解读也会不同。仅供娱乐，不构成决策依据 ✨</div></div>';
      out.innerHTML = html;
      attachChatEntry(out);   /* R230k（R23-P2-1）：本命盘卡挂聊天入口 */
      try { rememberResult('bazi', j, '我的本命盘', body); } catch (e) {}
    } catch (err) {
      out.innerHTML = '<div class="ph-empty">网络开小差了：' + esc(err.message) + '，稍后再试～</div>';
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
    showToast('当前离线——数据暂时刷不出来，恢复网络后再试', 'warn');
  });
  window.addEventListener('online', function () {
    showToast('网络回来了～', 'info');
  });
  /* R230d（R16-P1-5）：冷启动就离线（PWA 壳由 SW 兜住）时给同一条提示——
   * offline 事件只在「由在线转离线」时发，启动即离线它不发。 */
  if (navigator.onLine === false) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function () {
        showToast('当前离线——数据暂时刷不出来，恢复网络后再试', 'warn');
      });
    } else {
      showToast('当前离线——数据暂时刷不出来，恢复网络后再试', 'warn');
    }
  }
})();
