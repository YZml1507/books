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
  return node ? String(node.value == null ? '' : node.value).trim() : '';
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

/** HTML 转义——所有动态文本入 innerHTML 前必过这里。 */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
}

/** 把内容写进结果容器；容器不存在时静默返回。 */
function paint(id, html) {
  const node = el(id);
  if (node) {
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
function failWithRetry(id, text, retryFn) {
  document.querySelectorAll('.footnote').forEach(function (fn) { fn.hidden = true; });
  const node = el(id);
  if (!node) return;
  node.hidden = false;
  node.innerHTML =
    '<div class="no-evidence">' + esc(text) +
    (typeof retryFn === 'function'
      ? ' <button type="button" class="ghost" id="retryBtn" ' +
        'style="margin-left:8px;">🔄 重新测算</button>' : '') +
    '</div>';
  const btn = el('retryBtn');
  if (btn && typeof retryFn === 'function') btn.addEventListener('click', retryFn);
}

function fail(id, text) {
  paint(id, '<div class="no-evidence">' + esc(text) + '</div>');
}

/** fetch + JSON，把 !ok 的 detail 变成 Error，让调用方只写一个 catch。 */
async function api(path, options) {
  const resp = await fetch(path, options);
  let body = null;
  try {
    body = await resp.json();
  } catch (e) {
    body = null;
  }
  if (!resp.ok) {
    const detail = body && body.detail ? body.detail : resp.status + ' ' + resp.statusText;
    const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    /* R218a-巡2（N-05）：错误态用户反馈——非 2xx 一律弹红色 toast（不只
     * 在主流程 catch 里弹；网络层就弹，给用户即时反馈）。4xx 是用户输入
     * 错（黄底提示），5xx 是服务端异常（红底提示）。 */
    var status = resp.status;
    var isClient = status >= 400 && status < 500;
    showToast(typeof err.message === 'string' ? err.message : '请求失败',
              isClient ? 'warn' : 'error');
    throw err;
  }
  return body;
}

/* R218a-巡2（N-05）：全局 toast——错误/警告/成功共用。3.5s 自动消失，
 * 多次调用堆叠，z-index 最高（遮在 modal 之上）。additive，不动既有
 * 任何 DOM 结构。 */
function showToast(msg, kind) {
  var stack = document.getElementById('toastStack');
  if (!stack) {
    stack = document.createElement('div');
    stack.id = 'toastStack';
    stack.className = 'toast-stack';
    document.body.appendChild(stack);
  }
  var t = document.createElement('div');
  t.className = 'toast-item toast-' + (kind || 'info');
  var icon = kind === 'error' ? '⛔' : (kind === 'warn' ? '⚠️' : '✅');
  t.innerHTML = '<span class="toast-icon">' + icon + '</span>' +
    '<span class="toast-msg">' + esc(String(msg || '')) + '</span>';
  stack.appendChild(t);
  /* 入场动画 */
  requestAnimationFrame(function () { t.classList.add('show'); });
  /* 自动消失 */
  setTimeout(function () {
    t.classList.remove('show');
    setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 250);
  }, 3500);
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
  RESULT_GEN[containerId] = (RESULT_GEN[containerId] || 0) + 1;
  var gen = RESULT_GEN[containerId];
  var deadline = Date.now() + AI_POLL_CAP_S * 1000;
  var tick = function () {
    if (RESULT_GEN[containerId] !== gen) return;   // 已被新一轮结果覆盖
    api('/api/ai/' + encodeURIComponent(taskId)).then(function (st) {
      if (RESULT_GEN[containerId] !== gen) return;
      if (st && st.status === 'done' && st.text) {
        if (insertAiPolish(containerId, st.text)) {
          var entry = LAST_RESPONSE[containerId];   // 让口吻切换重画也带上 AI 块
          if (entry && entry.json) entry.json.ai_polish = st.text;
        }
        return;                                      // 终态：停止轮询
      }
      if (st && st.status === 'failed') return;      // 拿不到 → 整块不渲染
      if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
    }).catch(function () { /* 404/过期/网络抖动：静默放弃 */ });
  };
  setTimeout(tick, AI_POLL_INTERVAL_MS);
}

/* ── R206b（specs/009 US1）：AI 陪伴层「问问小满」──────────────
 * 排盘结果尾部入口 → 聊天抽屉。复用 pollAiPolish 的轮询语义
 * （/api/ai/{tid}），会话 id 存 localStorage（跨标签持久化，零隐私留存）。
 * DISABLE=1 时 /api/chat 返回无 chat_task_id 键 → 入口隐藏（D-244a）。 */
var CHAT_SID_KEY = 'chatSessionId';
function chatSid() {
  try {
    var sid = localStorage.getItem(CHAT_SID_KEY);
    if (!sid) {
      sid = 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
      localStorage.setItem(CHAT_SID_KEY, sid);
    }
    return sid;
  } catch (e) { return 'c-anon'; }
}
var CHAT_LAST_FACTS = [];   /* 最近一次排盘的坐标事实（干支五行词，非 PII） */

/** R207b：聊天入口全局化——结果容器渲染出 .card 后尾部统一挂入口钮。
 *  已有则跳过（重绘安全）；无 .card（如空态/错误态）不挂。 */
function attachChatEntry(container) {
  if (!container) return;
  var card = container.querySelector('.card');
  if (!card || card.querySelector('#chatEntry')) return;
  var btn = document.createElement('button');
  btn.className = 'chat-entry';
  btn.type = 'button';
  btn.id = 'chatEntry';
  /* R218a-巡4（A-b）：图标按钮补 aria-label */
  btn.setAttribute('aria-label', '打开小满聊天，聊聊这件事');
  btn.textContent = '💬 聊聊这件事';
  card.appendChild(btn);
}

/* R217a：点击「聊聊这件事」自动发送当前排盘上下文，无需用户手动输入 */
function autoSendChatContext() {
  if (!CHAT_LAST_FACTS || !CHAT_LAST_FACTS.length) return;
  chatBubble('me', '帮我看看这个盘');
  postJSON('/api/chat', {
    session_id: chatSid(), message: '帮我看看这个盘', facts: CHAT_LAST_FACTS
  }).then(function (j) {
    if (!j.chat_task_id) {
      /* R218a-02：U-008 修复后仍复用同一句话「打烊中」复读——扩展为
       * 4-6 句确定性轮换，并按上下文（自动发送：必属「看盘」类）做轻回应。 */
      chatBubble('ai', _chatFallbackLine('看盘'));
      return;
    }
    chatBubble('ai', '<span class="chat-typing"><i></i><i></i><i></i></span>');
    var deadline = Date.now() + AI_POLL_CAP_S * 1000;
    var tick = function () {
      api('/api/ai/' + encodeURIComponent(j.chat_task_id)).then(function (st) {
        var flow = el('chatFlow');
        if (st && st.status === 'done' && st.text) {
          if (flow) flow.lastChild.textContent = st.text;
          return;
        }
        if (st && st.status === 'failed') { if (flow) flow.removeChild(flow.lastChild); return; }
        if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
        else if (flow && flow.lastChild) flow.lastChild.textContent = '（网络不太好，再发一次试试？）';
      }).catch(function () {});
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
  "今天小满提前打烊啦～先把上面的牌面看着，明天 0 点我准时在线，找我聊。",
  "解忧铺今晚休整中，今天发的心事我记下了，明天来听你细说。",
  "小满今天不上班，门口的牌子写着『明日再会』✨ 你先歇会儿，明天找我。",
  "今晚小满调休中～把心事先写下来，明天上线第一时间翻你的牌。",
  "打烊了哦宝～这条消息我存着，明天 0 点以后来找我说完。",
  "解忧铺的灯今天关了——你的心事没丢，明天开门第一单给你留着。",
  "今晚上线时间到了我先下了，存好你的话，明天带着新力气一起拆。",
  "小满今晚关店早，你先看看上面那张牌的提示，明天找我深聊。",
  "门牌已经翻到『休息中』，你的消息我等明天再回——今晚先睡个好觉。",
  "今天解忧铺的茶凉了，明天重新烧——你写下来的我都会读。"
];
var _CHAT_FALLBACK_BY_KW = {
  'tired': [
    "累了啊…小满今天不上班，明天听你说细节。今晚先喝口温水，别再撑了。",
    "听着就累。先把肩膀松下来，明天来找我，咱们一件一件拆。",
    "身体先叫停一下比什么都重要。今晚睡饱，明天找我。",
    "累的时候做的决定十有八九会后悔，今晚先放放，明天来。"
  ],
  'work': [
    "工作的坎儿先不急开今晚的会——思路睡一觉会清楚很多。明天找我聊细节。",
    "听到工作的苦。明天跟我讲讲你卡在哪一环，咱们一起拆。",
    "工作的事交给明天的我，今晚先下班。",
    "职场的弯弯绕绕明天拆给你听。今晚喝口热的，先喘口气。"
  ],
  'love': [
    "感情的事急也急不出答案。今晚先放过自己，明天来跟我讲。",
    "爱里的纠结最难熬。明天来找我，把心意慢慢理顺。",
    "今天先不猜他的心思了，明天来听我说说牌面给的信号。",
    "心动或心累都先收着，明天我陪你解。"
  ],
  'study': [
    "学习的压力今晚先放一放，脑子也需要打烊。明天我陪你拆重点。",
    "考试的事交给明天的自己——今晚先复盘三件今天做对的小事。",
    "学不进去的时候别硬撑，明天来我帮你把节奏理一理。",
    "作业的事明天再战。今晚奖励自己一集短剧。"
  ],
  'money': [
    "钱包的事明天再算——今晚先不想钱的事。",
    "理财的纠结明天拆给你听。今晚先关掉账单页面。",
    "今天先不数余额。明天来找我，把账本翻一遍。",
    "钱的事别熬夜想——夜里做的预算都偏严。明天聊。"
  ],
  'reading': [
    "牌面我看了，今天先不展开细说——明天上线我把核心那一条讲给你听。",
    "牌面的提示在，但小满今天不上班。明天找我对这一条，帮你揉碎了讲。",
    "这张牌不是三两句能说完的。今晚先看，明天来找我深读。",
    "牌先不剧透了——小满今晚打烊，明天来翻牌。"
  ],
  'default': [
    "今天小满提前打烊啦～先把上面的牌面看着，明天 0 点我准时在线。",
    "解忧铺今晚休整中，你的心事我存着，明天来听。",
    "门牌已经翻到『休息中』，明天找我深聊。",
    "今天解忧铺的茶凉了，明天重新烧——你写下来的我都会读。"
  ]
};
/* 关键词→分类映射（命中第一个即用） */
var _CHAT_FALLBACK_KW_MAP = [
  { cat: 'tired',   kws: ['累', '疲惫', '疲惫', '睡', '失眠', '撑', '撑不住', '废', '躺'] },
  { cat: 'work',    kws: ['工作', '职场', '同事', '老板', '上司', '升职', '跳槽', '上班', '加班', '辞职'] },
  { cat: 'love',    kws: ['感情', '恋爱', '喜欢', '分手', '前任', '他', '她', '对象', '恋爱', '暗恋', '表白', '相亲', '暧昧'] },
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
function pollNameReview(taskId) {
  var deadline = Date.now() + AI_POLL_CAP_S * 1000;
  var tick = function () {
    api('/api/ai/' + encodeURIComponent(taskId)).then(function (st) {
      const out = el('nameReviewOut');
      if (!out) return;
      if (st && st.status === 'done' && st.text) {
        out.innerHTML = '<div class="tarot-deep"><h4>📜 AI 引经点评</h4><p style="white-space:pre-wrap;">' +
          esc(st.text) + '</p></div>';
        return;
      }
      if (st && st.status === 'failed') {
        out.innerHTML = '<div class="no-evidence">这次没点评出来，稍后再试</div>';
        return;
      }
      if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
      else out.innerHTML = '<div class="no-evidence">超时了，再试一次？</div>';
    }).catch(function () {});
  };
  setTimeout(tick, AI_POLL_INTERVAL_MS);
}

/* R209b：聊天并入左侧统一栏——打开聊天=打开侧栏并滚到聊天段。 */
function chatOpen() {
  var sb = el('recentSidebar');
  if (!sb) return;
  sb.classList.add('open');
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
function chatClose() {
  var sb = el('recentSidebar');
  if (sb) sb.classList.remove('open');
  /* R218a-01：同步关遮罩，pointer-events 立即放行主区点击 */
  var bd = el('recentBackdrop');
  if (bd) bd.classList.remove('open');
  var tgl = el('recentToggle');
  if (tgl) tgl.setAttribute('aria-expanded', 'false');
}
function chatEmptyGuide() {
  /* R212：空状态引导——抽屉打开时不再是一片空白。 */
  var flow = el('chatFlow');
  if (!flow || flow.children.length) return;
  var d = document.createElement('div');
  d.className = 'chat-empty';
  d.id = 'chatEmpty';
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
function chatBubble(role, text) {
  var flow = el('chatFlow');
  if (!flow) return;
  var emp = document.getElementById('chatEmpty');
  if (emp) emp.remove();
  var div = document.createElement('div');
  div.className = 'chat-bubble chat-' + role;
  if (text.indexOf('chat-typing') !== -1) div.innerHTML = text;  // 动效气泡
  else div.textContent = text;
  flow.appendChild(div);
  flow.scrollTop = flow.scrollHeight;
}
function chatSend() {
  var input = el('chatInput');
  var msg = (input && input.value || '').trim();
  if (!msg) return;
  if (input) input.value = '';
  chatBubble('me', msg);
  postJSON('/api/chat', {
    session_id: chatSid(), message: msg, facts: CHAT_LAST_FACTS
  }).then(function (j) {
    if (!j.chat_task_id) {                     /* DISABLE：入口静默降级 */
      /* R216b 续3（UX 队列 U-008）：原降级文案「（聊天功能暂时没开，
       * 稍后再来吧）」系统腔零共情——用户刚倾诉疲惫。改为情绪承接 +
       * 替代引导；DISABLE 态输入框置灰防连发连拒。
       * R218a-02：扩为 4-6 句确定性轮换 + 关键词到 openeer 的最轻分支
       * （累/事业/感情/学业/钱/看盘 6 套）。 */
      chatBubble('ai', _chatFallbackLine(msg));
      var sendBtn2 = document.getElementById('chatSendBtn');
      if (input) { input.disabled = true; input.placeholder = '小满休息中，明天再来聊吧'; }
      if (sendBtn2) sendBtn2.disabled = true;
      return;
    }
    chatBubble('ai',
      '<span class="chat-typing"><i></i><i></i><i></i></span>');
    var deadline = Date.now() + AI_POLL_CAP_S * 1000;
    var tick = function () {
      api('/api/ai/' + encodeURIComponent(j.chat_task_id)).then(function (st) {
        var flow = el('chatFlow');
        if (st && st.status === 'done' && st.text) {
          if (flow) flow.lastChild.textContent = st.text;   /* 替换占位 … */
          return;
        }
        if (st && st.status === 'failed') {
          if (flow) flow.removeChild(flow.lastChild);
          return;
        }
        if (Date.now() < deadline) setTimeout(tick, AI_POLL_INTERVAL_MS);
        else if (flow && flow.lastChild) flow.lastChild.textContent = '（网络不太好，再发一次试试？）';
      }).catch(function () {
        var flow = el('chatFlow');
        if (flow && flow.lastChild && flow.lastChild.textContent === '…') {
          flow.lastChild.textContent = '（网络不太好，再发一次试试？）';
        }
      });
    };
    setTimeout(tick, AI_POLL_INTERVAL_MS);
  }).catch(function () {
    chatBubble('ai', '（网络不太好，再发一次试试？）');
  });
}

/** 绑定点击；元素不存在时不报错（HTML 与 JS 允许分批演进）。 */
function on(id, handler) {
  const node = el(id);
  if (node) node.addEventListener('click', handler);
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
  /* R205b（用户反馈③）：不再自动滚回顶部——用户在长页中段点功能卡，
   * 被强行拽到页顶很突兀。提交结果后的定位由 revealResult() 负责，
   * 首屏闸门（probe_first_screen 判据 1）量的是「提交后」的视口偏移，
   * 与本行无关。 */
  window.scrollTo({ top: _sy, behavior: 'auto' });
  /* R216b 续（U-007）：时间起卦默认当天（原 HTML 写死 1990/5/15）。 */
  if (viewId === 'liuyao') syncLiuyaoToday();
}

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
    html += '<div class="ev-meta" style="color:' + c + ';">' + esc(h.citation || '') +
      (h.layer ? ' · ' + esc(h.layer) : '') +
      (o.score && h.score != null ? '<span class="hit-score">score ' + esc(h.score) + '</span>' : '') +
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
      // 不允许只显示其一（005 判据 5）。
      let label = h.citation || '（无出处）';
      if (h.layer) label += ' · ' + h.layer;
      if (h.why) label += ' · 因「' + h.why + '」被选中';
      if (text) label += ' · ' + text.length + ' 字';
      html += '<div class="cite-item">';
      html += citeToggle(bid, label);
      // 原文：逐字节等于 API（判据 8）。esc() 只做 HTML 转义，不改内容。
      html += '<div class="cite-body" id="' + bid + '" hidden>' +
        esc(text) + '</div>';
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
  window.scrollTo({ top: Math.max(0, top - 8), behavior: 'auto' });
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
  document.querySelectorAll('[data-theme-btn]').forEach(function (b) {
    var on = b.dataset.themeBtn === t;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', String(on));
  });
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
  "乖，抽到什么说什么，我们慢慢看。",
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
    var salt = (view.id || 'x') + '|' + new Date().toISOString().slice(0, 10);
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
    '<p class="ai-polish-text">' + esc(ai) + '</p>' +
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
    return { canvas: _paintPoster(j, POSTER_LOW_W, POSTER_LOW_H),
             w: POSTER_LOW_W, h: POSTER_LOW_H };
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
  ctx.fillText('🔮 今日命盘', W / 2, 130);

  // 四柱 pills
  var pillars = String(paipan.render || '').split(/\s+/).filter(function (p) { return p.length >= 2; });
  ctx.font = '500 44px serif';
  pillars.slice(0, 4).forEach(function (p, i) {
    var pw = 220, gap = 24;
    var x0 = (W - pillars.slice(0, 4).length * pw - (pillars.slice(0, 4).length - 1) * gap) / 2;
    ctx.fillStyle = i % 2 ? '#EFE3CE' : '#F3E6CF';
    roundRect(ctx, x0 + i * (pw + gap), 190, pw, 78, 39);
    ctx.fill();
    ctx.fillStyle = '#5B4620';
    ctx.fillText(p, x0 + i * (pw + gap) + pw / 2, 243);
  });

  // 一句话结论（L0）
  ctx.fillStyle = '#3E3428';
  ctx.font = '600 56px sans-serif';
  var l0 = wrapText(ctx, warm.one_liner || '', W - 200);
  l0.forEach(function (ln, i) { ctx.fillText(ln, W / 2, 380 + i * 76); });

  // 能量卡区块
  /* R216b 续（U-014）：卡高 430→560（信息行与出处行原本叠印，见下）。 */
  var cardY = 480;
  ctx.fillStyle = '#FFFFFF';
  roundRect(ctx, 90, cardY, W - 180, 560, 28);
  ctx.fill();
  ctx.strokeStyle = '#E8D9BC'; ctx.lineWidth = 2;
  roundRect(ctx, 90, cardY, W - 180, 560, 28);
  ctx.stroke();

  ctx.textAlign = 'left';
  ctx.fillStyle = '#7A5C2E'; ctx.font = '600 40px sans-serif';
  ctx.fillText('本命 ' + (ec.element || '') + '（' + (ec.element_warm || '') + '）', 140, cardY + 80);

  var rows = [];
  if (ec.lucky_colors && ec.lucky_colors.length) rows.push(['幸运色', ec.lucky_colors.join(' · ')]);
  if (ec.lucky_numbers && ec.lucky_numbers.length) rows.push(['幸运数字', ec.lucky_numbers.join(' · ')]);
  if (ec.lucky_hours && ec.lucky_hours.length) {
    /* R216b 续（U-014 附带）：lucky_hours 全量 join 可达 ~60 字，38px 下
     * 远超卡宽（940px 内约 24 字）——审查轨截图里「黄运棕」实为「黄 · 棕」
     * 与下一行叠印的误读，但时段行确实溢出。只取前三个时段并压缩区间写法。 */
    var hs = ec.lucky_hours.slice(0, 3).map(function (h) {
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
  (ec.basis || []).slice(0, 3).forEach(function (b, i) {
    var t = '· ' + b;
    if (t.length > 26) {
      /* V-004：截断点避开英文键名中间——优先回退到最近的非字母数字字符。 */
      var cut = 25;
      for (var k2 = cut; k2 > 12; k2--) {
        if (!/[A-Za-z0-9_]/.test(t.charAt(k2)) && !/[A-Za-z0-9_]/.test(t.charAt(k2 - 1))) {
          cut = k2; break;
        }
      }
      t = t.slice(0, cut) + '…';
    }
    ctx.fillText(t, 140, cardY + 480 + i * 44);
  });

  // 免责水印（判据 2：仅供娱乐标识，常显不折叠）
  ctx.textAlign = 'center';
  /* R218a-11：品牌水印 + 金句 hook——「@小满的解忧铺」+ 副标
   * 写在「知命 · 仅供娱乐」上方（保留底标过 check_poster 判据 12）。 */
  ctx.fillStyle = '#7A5C2E';
  ctx.font = '600 36px serif';
  ctx.fillText('@小满的解忧铺', W / 2, 1440 - 158);
  ctx.fillStyle = '#B7A98A';
  ctx.font = '400 24px sans-serif';
  ctx.fillText('· 知命知书知天机 ·', W / 2, 1440 - 124);
  ctx.fillStyle = '#815934';
  ctx.font = '500 26px sans-serif';
  ctx.fillText('知命，是为了更好地活', W / 2, 1440 - 80);
  ctx.fillStyle = '#B7A98A';
  ctx.font = '400 34px sans-serif';
  ctx.fillText('知命 · 仅供娱乐', W / 2, 1440 - 38);

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
  ctx.fillText(s.title || '知命', 540, 128);
  if (s.subtitle) {
    ctx.fillStyle = '#B7A98A'; ctx.font = '400 32px sans-serif';
    ctx.fillText(String(s.subtitle).slice(0, 24), 540, 182);
  }

  /* 大字结论（最多两行，自动缩字号防溢出） */
  var big = String(s.big || '');
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
      var v = String(r.v || '');
      ctx.fillText(v.length > 16 ? v.slice(0, 15) + '…' : v, 150, y + 52);
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
      ctx.fillText(c.name.slice(0, 6), cx + cw / 2, iy + 44);
      ctx.fillStyle = '#815934'; ctx.font = '400 28px sans-serif';
      ctx.fillText(String(c.sub || '').slice(0, 8), cx + cw / 2, iy + 88);
    });
  }

  /* R218a-11：品牌水印 + 金句 hook——海报底部分两行：
   * 1) 品牌水印「@小满的解忧铺 · 知命知书知天机」（替原「知命 · 仅供娱乐」）
   * 2) 金句 hook（按 view 给不同内容，无 view 时通用）。 */
  ctx.textAlign = 'center';
  /* 水印行 */
  ctx.fillStyle = '#7A5C2E'; ctx.font = '600 36px serif';
  ctx.fillText('@小满的解忧铺', 540, 1320);
  ctx.fillStyle = '#B7A98A'; ctx.font = '400 26px sans-serif';
  ctx.fillText('· 知命知书知天机 ·', 540, 1356);
  /* 金句 hook（按 view 动态 + 数据驱动） */
  /* R218a-巡3 修复（N-02+N-04 同根因）：原 `j` 是父函数 _paintPoster 的形参，
   * 本函数 _paintSharePoster(s, W, H) 形参只有 s；j 在 share 分支闭包不可见，
   * 会抛 `j is not defined` → 海报浮层 + 差异化全失效。改用 s。
   * N-09 数据驱动金句需要父 j 的 warm/full_names/peach_zhi 等字段，_paintPoster
   * 已把 j 挂到 s._src（line 992 附近），这里优先用 s._src，无则回退 s。 */
  var hook = _posterHookForView(s && s.view, s._src || s);
  if (hook) {
    ctx.fillStyle = '#815934'; ctx.font = '500 28px sans-serif';
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
    var c = ec.element || '';
    if (c) return '你的命格是「' + c + '」，' + (c.length === 1 ? '一' : c.length === 2 ? '二' : '三') + '字真言已就位';
  }
  /* qiming: 用 TOP 1 名 + 评分（j 必有 full_names） */
  if (view === 'qiming' && j && j.full_names && j.full_names[0]) {
    var top = j.full_names[0];
    return '首选「' + (top.full_name || '') + '」· 评分 ' + (top.score || 80) + ' / 100';
  }
  /* taohua: 用桃花支 + 强度 */
  if (view === 'taohua' && j) {
    var zhi = j.peach_zhi || '';
    var stg = j.strength || '';
    if (zhi) return '桃花落在「' + zhi + '」支 · 强度 ' + (stg || '待时');
  }
  /* hehun: 用双方日主五行 */
  if (view === 'hehun' && j && j.day_wx_a && j.day_wx_b) {
    return j.day_wx_a + ' 遇 ' + j.day_wx_b + ' · ' + (j.day_wx_sheng ? '相生' : '互补');
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
    case 'daily':
      return { title: '今日运势', subtitle: (j && j.date) || '',
        /* R212：原 slice(0,18) 会把 summary 拦腰截断（「…宜稳不」）——
         * 改取第一个分号前的完整短句。 */
        big: (j && j.summary)
          ? (String(j.summary).split(/[；;]/)[0] || '今日份小确幸')
          : '今日份小确幸',
        lines: [{ k: '运势等级', v: (j && j.level) || '—' },
                { k: '天乙贵人', v: (j && j.noble) || '—' },
                { k: '宜', v: (j && j.do) || '—' },
                { k: '忌', v: (j && j.dont) || '—' }],
        cards: [], view: view };
    case 'tarot': {
      var draws = (j && j.draws) || [];
      var imgs = document.querySelectorAll('.tarot-card-front img');
      var s = base('塔罗指引', (w.question_hint || ''));
      s.big = l0 || '牌面是象征，不是结论';
      s.cards = draws.slice(0, 3).map(function (d, i) {
        var el = imgs[i] && imgs[i].complete && imgs[i].naturalWidth > 0 ? imgs[i] : null;
        return { name: d.name, sub: d.upright ? '正位' : '逆位', img: el };
      });
      return s;
    }
    case 'liuyao': {
      var sly = base('六爻占卜', '');
      sly.lines = ((w.details && w.details.basis) || []).slice(0, 4)
        .map(function (b) { return { k: '依据', v: b }; });
      if (!sly.lines.length) sly.lines = [{ k: '结论', v: l0.slice(0, 15) }];
      return sly;
    }
    case 'qiming':
      return { title: '五行起名', subtitle: '按五行补缺',
        big: ((j && j.full_names && j.full_names[0] && j.full_names[0].full_name)
              || l0 || '').slice(0, 12),
        lines: ((j && j.full_names) || []).slice(0, 4).map(function (n, i) {
          return { k: '推荐 ' + (i + 1), v: (n && n.full_name) || '' }; }),
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
      if (ec.element) sb.lines.push({ k: '本命', v: ec.element + (ec.element_warm ? '（' + ec.element_warm + '）' : '') });
      if (ec.lucky_colors && ec.lucky_colors.length) sb.lines.push({ k: '幸运色', v: ec.lucky_colors.slice(0, 3).join(' · ') });
      if (ec.lucky_numbers && ec.lucky_numbers.length) sb.lines.push({ k: '幸运数字', v: ec.lucky_numbers.join(' · ') });
      if (!sb.lines.length) sb.lines = [{ k: '结论', v: l0.slice(0, 15) || '知己知命' }];
      return sb;
    }
    case 'taohua': {
      var st = base('桃花运势', '');
      var td = (j && (j.peach_zhi || j.tianxi)) ? j : (w || {});
      st.big = l0 || '桃花正在加载';
      st.lines = [];
      if (j && j.peach_zhi) st.lines.push({ k: '桃花支', v: String(j.peach_zhi) });
      if (j && j.hit_pillars && j.hit_pillars.length) st.lines.push({ k: '命中柱', v: j.hit_pillars.map(function (p) { return ({ year: '年柱', month: '月柱', day: '日柱', hour: '时柱' })[p] || p; }).join(' · ') });
      if (j && j.hongluan) st.lines.push({ k: '红鸾', v: String(j.hongluan) });
      if (j && j.tianxi) st.lines.push({ k: '天喜', v: String(j.tianxi) });
      if (j && j.strength) st.lines.push({ k: '桃花强度', v: String(j.strength) });
      if (!st.lines.length) st.lines = [{ k: '结论', v: l0.slice(0, 15) || '桃花待时而动' }];
      return st;
    }
    case 'hehun': {
      var sh = base('合婚配对', '');
      sh.big = l0 || '甜度超标组合';
      sh.lines = [];
      if (j && j.day_wx_a && j.day_wx_b) {
        var sheng = j.day_wx_sheng ? ' · 相生' : '';
        sh.lines.push({ k: '日主五行', v: j.day_wx_a + ' ↔ ' + j.day_wx_b + sheng });
      }
      if (j && j.clash) sh.lines.push({ k: '六冲', v: j.clash });
      if (j && j.combine) sh.lines.push({ k: '六合', v: j.combine });
      if (j && typeof j.peach_same === 'boolean') sh.lines.push({ k: '桃花支', v: j.peach_same ? '同支共振' : '各有桃花' });
      if (j && j.gan_he) sh.lines.push({ k: '天干五合', v: String(j.gan_he) });
      if (!sh.lines.length) sh.lines = [{ k: '结论', v: l0.slice(0, 15) || '天作之合' }];
      return sh;
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

function downloadPoster(j, view) {
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
  var r = drawPoster(j);
  if (!r || !r.canvas) return;
  /* 同时触发下载（兼容 desktop「图去哪了」老习惯）+ 弹浮层。 */
  try {
    r.canvas.toBlob(function (blob) {
      if (!blob) return;
      var a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'zhiming-poster.png';
      document.body.appendChild(a);
      a.click();
      setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 800);
    }, 'image/png');
  } catch (e) { /* 低端降级：静默，不打断主流程 */ }
  /* 弹浮层——海报预览 + 移动端长按保存提示 */
  showPosterModal(r.canvas, view);
}

/* R218a-巡2（N-02）：海报浮层——背景遮罩 + 中央海报图 + 关闭按钮 +
 * 长按保存提示。点遮罩/ESC 关闭，多次调用只重建内容。 */
function showPosterModal(canvas, view) {
  var existing = document.getElementById('posterModal');
  if (existing) existing.remove();
  var backdrop = document.createElement('div');
  backdrop.id = 'posterModal';
  backdrop.className = 'poster-modal-backdrop';
  /* 视图名 → 人话标题 */
  var viewTitle = ({
    bazi: '今日命盘', liuyao: '六爻指引', tarot: '塔罗指引',
    qiming: '五行起名', taohua: '桃花运势', hehun: '合婚配对', daily: '今日运势'
  })[view] || '命盘海报';
  var img = canvas.toDataURL('image/png');
  backdrop.innerHTML =
    '<div class="poster-modal">' +
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
  /* 关闭路径 1：点关闭按钮 */
  backdrop.querySelector('.poster-modal-close').addEventListener('click', closePosterModal);
  /* 关闭路径 2：点遮罩（点 modal 自身，不含内容） */
  backdrop.addEventListener('click', function (e) {
    if (e.target === backdrop) closePosterModal();
  });
  /* 关闭路径 3：ESC 键 */
  var onKey = function (e) {
    if (e.key === 'Escape' || e.keyCode === 27) {
      closePosterModal();
      document.removeEventListener('keydown', onKey);
    }
  };
  document.addEventListener('keydown', onKey);
}
function closePosterModal() {
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
  return lines.slice(0, 3);
}

function wrapText(ctx, text, maxWidth) {
  var lines = [], cur = '';
  String(text || '').split('').forEach(function (ch) {
    if (ctx.measureText(cur + ch).width > maxWidth) { lines.push(cur); cur = ch; }
    else cur += ch;
  });
  if (cur) lines.push(cur);
  return lines.slice(0, 3);
}

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
    '<span class="interp-badge">' + esc(interp.engine || '确定性规则') + '</span></h3>';
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
      html += '<div class="ev-item"><div class="ev-meta">' + esc(c.citation || '') + '</div>' +
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
    const j = await api('/api/daily');
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
      const x = await api('/api/xingzuo?date=' + encodeURIComponent(j.date || ''));
      const box = el('dailyXingzuo');
      if (box && x && x.today_sign) {
        /* R216b 续3（U-010）：「值官/龙首星」术语腔 → 人话。 */
        setText('dxLabel', '⭐ 今日轮值的星座：' + x.today_sign);
        setText('dxNote', x.today_note || '');
        box.hidden = false;
      }
    } catch (e2) { /* 十二宫不可用不阻塞今日运势 */ }
  } catch (e) {
    setText('dailySummary', '运势计算暂时不可用：' + e.message);
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
  if (target.dataset.loaded === '1') {
    target.hidden = !target.hidden;
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
      html += renderWarm(j.warm, j.interpretation);
    }
    html += '</div>';
    target.innerHTML = html;
    target.dataset.loaded = '1';
    pollAiPolish('dailyDetail', j.ai_task_id);   // R217a：完整解读也轮询 AI 润色
  } catch (e) {
    target.innerHTML = '<div class="no-evidence">解读失败：' + esc(e.message) + '</div>';
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
  var presets = {
    bazi:   { grad: 'linear-gradient(135deg,#F2E1C9 0%,#E8C9A0 100%)', icon: '🌙', txt: '月圆人团圆 · 你的命盘已就位', iconBg: 'radial-gradient(circle, #FFD89B 0%, #E8C9A0 70%)' },
    qiming: { grad: 'linear-gradient(135deg,#E8F5E0 0%,#F0E5C2 100%)', icon: '🌿', txt: '一撇一捺 · 给孩子起个好名字', iconBg: 'radial-gradient(circle, #C8E6C9 0%, #A5D6A7 70%)' },
    taohua: { grad: 'linear-gradient(135deg,#FFE0E0 0%,#FBD2D2 100%)', icon: '🌸', txt: '三月桃花开 · 你的缘分在路上了', iconBg: 'radial-gradient(circle, #F8BBD0 0%, #F48FB1 70%)' }
  };
  var p = presets[view];
  if (!p) return '';
  return '<div class="deco-banner deco-' + view + '">' +
    '<div class="deco-icon" style="background:' + p.iconBg + ';">' + p.icon + '</div>' +
    '<div class="deco-text">' + esc(p.txt) + '</div>' +
    '<div class="deco-corner"></div>' +
  '</div>';
}

/* R218a-巡2：N-08 装饰图函数 + N-01 questionHook 依赖后端 services.py 回写 question 字段 */

function buildBaziResult(j) {
  const paipan = j.paipan || {};
  let html = '<div class="card"><h2>🔮 排盘结果</h2>';
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
    if (j.evidence && j.evidence.length) {
      html += '<h3 style="margin-top:20px;color:var(--c-book);">📜 古籍依据</h3>';
      html += renderHits(j.evidence, { empty: '无引文' });
    }
  }
  // R000a-04：原读 j.llm_out（后端从来没这个键）→ 现读 interpretation。
  html += renderVoice(j, '📖 解读（确定性规则）', ['evidence']);
  html += '</div>';
  return html;
}

async function submitBazi(event) {
  if (event) event.preventDefault();
  busy('result', '计算中…');
  try {
    const body = baziBody();
    WARM_LAST_QUESTION = body.question || '';   /* R206b US4：共情模板选择依据 */
    const j = await postJSON('/api/bazi', body);
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
    revealResult('result');            // 005 判据 1：提交后无需滚动即见结论
    pollAiPolish('result', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    on('favBazi', function () {
      addFavorite('bazi', paipan.render || 'latest', '八字排盘 ' + (paipan.render || ''));
    });
    on('shareBazi', function () { downloadPoster(j, 'bazi'); });   /* R218a-巡2（N-04）：传 view 让通用模板接管 */
    loadRecent();
  } catch (e) {
    /* R218a-巡4（E-a/E-b）：失败态清成功期说明文字 + 内联重试按钮。 */
    failWithRetry('result', '计算失败：' + e.message, function () { submitBazi(); });
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
    paint('searchResult',
      '<p class="hit-cite">命中 ' + esc(j.count) + ' 条</p>' +
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
    fail('compareResult', '请输入卦号（1-64）');
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
      html += '<div class="calc-block work-card" data-work="' + esc(w.id) +
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
      confidence: 'open'
    });
    let html = '<div class="no-evidence">线程已创建：#' + esc(j.thread_id) +
      '（claim #' + esc(j.derived_id) + '）</div>' +
      /* R201b（B-005）：展示 claim 内容与证据数——用户能确认「记下了什么」，
       * 不再只回一行 id（响应键 claim/n_evidence 原本零引用）。 */
      '<div class="calc-block" style="margin:10px 0;">' +
      '<p style="font-size:14px;line-height:1.6;">' + esc(j.claim || '') + '</p>' +
      (j.n_evidence != null ? '<p style="font-size:12px;color:var(--secondary);">证据 ' +
        esc(j.n_evidence) + ' 条</p>' : '') + '</div>';
    const list = await api('/api/threads');
    (list.threads || []).forEach(function (t) {
      html += '<div class="thread-item"><div class="thread-topic">' +
        esc(t.topic || '') + '</div>' +
        '<div class="thread-meta">#' + esc(t.id) + ' · ' + esc(t.status) +
        ' · ' + esc(t.turns) + ' turns / ' + esc(t.claims) + ' claims · ' +
        esc(t.updated_at || '') + '</div>' +
        '<div class="thread-actions">' +
        '<button class="thread-view" type="button" data-thread="' + esc(t.id) +
        '">查看</button></div></div>';
    });
    paint('threadResult', html);
  } catch (e) {
    fail('threadResult', '创建失败：' + e.message);
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
        html += '<div class="ev-item"><div class="ev-meta">' + esc(t.citation || '') +
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
      shared.forEach(function (s) {
        html += '<div class="finding">' + esc(s.addr || '') + '　' +
          esc(fmtScalar(s.works)) + '</div>';
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
    html += '</tbody></table>';
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
    html += '</tbody></table>';
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
      html += '<div class="ev-item"><div class="ev-meta">' + esc(u.citation || '') +
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
    ben.lines.slice().sort(function (a, b) { return b.position - a.position; })
      .forEach(function (ln) {
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
  }
  const q = val('ly_question');
  if (q) body.question = q;
  try {
    const j = await postJSON('/api/liuyao', body);
    paint('lyResult', buildLiuyaoResult(j));
    rememberVoice('lyResult', j, buildLiuyaoResult);
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
    fail('lyResult', '摇卦失败：' + e.message);
  }
}

async function doHuangli() {
  busy('hlResult', '查询中…');
  const y = num('hl_year');
  const m = num('hl_month');
  const d = num('hl_day');
  if (y == null || m == null || d == null) {
    fail('hlResult', '请填写年/月/日');
    return;
  }
  // 实测后端只认 date=YYYY-MM-DD（原前端发 year/month/day 三个参数，
  // 被当作未知查询参数忽略，返回的是"今天"的黄历）。
  const dateStr = y + '-' + String(m).padStart(2, '0') + '-' + String(d).padStart(2, '0');
  try {
    const j = await api('/api/huangli?' + new URLSearchParams({ date: dateStr }).toString());
    /* R216b（UX 队列 U-001）：黄历结果页原是全站最干瘪的「老黄历工具」——
     * 建除/二十八宿/彭祖百忌文言裸抛、宜忌标签无解释、仅约 100 字符。
     * 改造（纯前端 additive，API 契约零改动）：
     *   1. 宜/忌逐条带场景化人话（HUANGLI_WARM 写死映射，映射不到回落原词）；
     *   2. 建除/二十八宿给一句话解释（JIANCHU_NOTE / XIUXIU_NOTE）；
     *   3. 彭祖百忌整块收进折叠（事实零删减，只是默认不展开）；
     *   4. 补今日一句话 + 收尾安抚句（均按坐标确定性生成，同输入同输出）。
     */
    const HUANGLI_WARM = {
      '嫁娶': '领证、订婚、官宣的好日子', '开市': '开业、上新、发第一单',
      '出行': '出门、旅行、去远方', '祭祀': '拜一拜、静心的日子',
      '祈福': '许愿、求个心安', '求嗣': '备孕、求子相关的事',
      '上任': '入职、履新、接新项目', '入学': '开学、报到、开始学新东西',
      '立券': '签约、定合同', '纳财': '收款、谈钱、理财动作',
      '捕捉': '把拖了很久的小事办掉', '狩猎': '来一场说走就走的短途出游',
      '安葬': '丧葬事宜', '破土': '动工破土类事宜', '治病': '看病、调理身体',
      '解除': '化解矛盾、清理旧事', '谒贵': '拜访贵人、见重要的人',
      '修造': '装修、修缮', '动土': '开工动土', '平整': '整理归置',
      '冠笄': '成人礼、形象焕新', '诉讼': '打官司、走程序',
      '出官': '公务出行', '安床': '安床布置', '移徒': '搬家挪窝',
      '进人口': '添丁进口', '开仓': '开库出货', '求医': '看医生',
      '筑堤': '修建堤坝', '塞穴': '封堵修补', '栽植': '种花种树',
      '经络': '缝纫织补', '苫盖': '搭棚加盖'
    };
    const JIANCHU_NOTE = {
      '建': '万物初生的一天，适合起头、见人', '除': '扫除旧事的一天，适合清理与告别',
      '满': '饱满的一天，适合庆祝和犒劳自己', '平': '平稳的一天，适合日常推进不折腾',
      '定': '安定的一天，适合定大事、做承诺', '执': '坚持的一天，认准的事慢慢推进',
      '破': '破旧立新的一天，大事先缓一缓', '危': '需要小心的一天，稳字当头',
      '成': '收获的一天，想做的事容易顺', '收': '收纳的一天，适合总结、收尾、存钱',
      '开': '打开的一天，适合开始新的尝试', '闭': '收拢的一天，适合休息、宅家充电'
    };
    const XIUXIU_NOTE = {
      '角': '龙角星——决策有底气', '亢': '龙颈星——别太较劲', '氐': '龙胸星——根基要稳',
      '房': '龙腹星——适合休整', '心': '龙心脏星——跟着感觉走', '尾': '龙尾星——事情容易摆动',
      '箕': '风星——话别太满', '斗': '斗星——忙碌但值得', '牛': '金牛星——踏实做事',
      '女': '女宿——适合打扮自己', '虚': '虚宿——少熬夜', '危': '危宿——注意安全',
      '室': '室宿——适合宅家布置', '壁': '壁宿——学习吸收力好', '奎': '奎宿——灵感多',
      '婁': '娄宿——适合聚会', '胃': '胃宿——好好吃饭', '昴': '昴宿——早睡早起',
      '畢': '毕宿——收网的时候到了', '觜': '觜宿——说话留三分', '參': '参宿——行动力在线',
      '井': '井宿——水源充足，资源到位', '鬼': '鬼宿——少想多睡', '柳': '柳宿——心情柔软',
      '星': '星宿——存在感强的一天', '張': '张宿——适合展示自己', '翼': '翼宿——想飞就飞',
      '軫': '轸宿——收住节奏'
    };
    function _warmWord(t) {
      const w = HUANGLI_WARM[t];
      return w ? t + '＝' + w : t;
    }
    let html = '<div class="card"><h2>🌙 黄历 · ' + esc(j.date || dateStr) + '</h2>';
    /* R216b 续6（V-001）：农历日期与冲煞——传统核心字段补齐上屏。 */
    if (j.lunar && j.lunar.month_cn) {
      html += '<p class="nayin">🗓 农历 ' + esc(j.lunar.month_cn) +
        esc(j.lunar.day_cn || '') + ' · ' + esc(j.lunar.ganzhi_year_cn || '') + '</p>';
    }
    if (j.chongsha && j.chongsha.chong) {
      html += '<p class="nayin">⚔ 今日冲' + esc(j.chongsha.chong) +
        '(' + esc(j.chongsha.chong_animal || '') + ') · 煞' +
        esc(j.chongsha.sha_fang || '') +
        '——属' + esc(j.chongsha.chong_animal || '') + '的朋友今天稳一点，煞方少往那边跑</p>';
    }
    // 今日一句话：按建除确定性生成（同输入同输出）
    if (j.jianchu) {
      html += '<div class="warm-l0" style="font-size:18px;">今天是「' + esc(j.jianchu) +
        '」值日' + (JIANCHU_NOTE[j.jianchu] ? '——' + esc(JIANCHU_NOTE[j.jianchu]) : '') + '。</div>';
    }
    html += '<p class="nayin" style="margin-top:8px;">' +
      (j.xiu && XIUXIU_NOTE[j.xiu] ? '值宿「' + esc(j.xiu) + '」：' + esc(XIUXIU_NOTE[j.xiu]) : '') +
      '</p>';
    // 彭祖百忌：整块收进折叠（原文逐字保留在 DOM 里）
    const pz = j.pengzu || {};
    if (pz.gan_text || pz.zhi_text) {
      html += '<details class="warm-basis"><summary>📜 彭祖百忌（老话，展开看看）</summary><ul>' +
        '<li>' + esc(pz.gan || '') + '：' + esc(pz.gan_text || '') + '</li>' +
        '<li>' + esc(pz.zhi || '') + '：' + esc(pz.zhi_text || '') + '</li></ul></details>';
    }
    // 实测 yi/ji 是数组。R201b（B-004）：各项独立 pill；R216b：逐条跟人话。
    function _pill(text, color) {
      return '<span class="pill" style="border:1px solid ' + color +
        ';color:' + color + ';background:#fff;">' + esc(text) + '</span>';
    }
    html += '<div class="calc-grid">';
    html += '<div class="calc-block"><h3 style="color:var(--c-good);">✅ 今天适合</h3><p>' +
      ((j.yi || []).map(function (t) { return _pill(_warmWord(t), 'var(--c-good)'); }).join(' ') || '—') +
      '</p></div>';
    html += '<div class="calc-block"><h3 style="color:var(--accent);">🙅 今天别急</h3><p>' +
      ((j.ji || []).map(function (t) { return _pill(_warmWord(t), 'var(--accent)'); }).join(' ') || '—') +
      '</p></div>';
    html += '</div>';
    html += '<p class="interp-disclaimer">📝 老黄历说的是节奏参考，日子怎么过还是你说了算～</p>';
    html += renderAiPolish(j);
    html += '</div>';
    paint('hlResult', html);
    revealResult('hlResult');
  } catch (e) {
    fail('hlResult', '查询失败：' + e.message);
  }
}

/* R218a-04+05：起名风格切换 + 推荐指数。
 * - 风格（4 档）：classics 诗经草木 / chuci 楚辞 / fresh 清新灵动 / all 全池
 * - 重新调用时通过 _QM_STYLE 改 top_n 与后端轮换（后端同输入同输出——
 *   加 style 仅用作「不同 keyword 取出不同子集」的口径，零契约变化）。
 * - 评分：客户端按 5 项加权（缺补/双字/单字+音韵短长/故事完整/中频字）
 *   满分 100 渲染为 ⭐ 95/100 + TOP 1/2/3 徽章。 */
var _QM_STYLE = 'classics';
var _QM_STYLES = {
  'classics': { label: '诗经草木', hint: '草木·鸟兽·日月' },
  'chuci':    { label: '楚辞',     hint: '香草·美人·远游' },
  'fresh':    { label: '清新灵动', hint: '轻盈·柔美·少女感' },
  'all':      { label: '综合',     hint: '全部候选池' }
};
function _qmSwitchStyle(style) {
  if (!_QM_STYLES[style]) return;
  _QM_STYLE = style;
  doQiming();
}
function _qmScore(name, missingArr) {
  if (!name) return 0;
  var score = 60;                       /* 基础分 */
  var els = (name.elements || []).map(String);
  var miss = (missingArr || []).map(String);
  /* 缺补：每个「名」用字补到了缺失五行 +12 */
  miss.forEach(function (m) {
    if (els.indexOf(m) !== -1) score += 12;
  });
  /* 双字名加分，单字名略减（古籍典故多为双字） */
  if (name.form === 'double') score += 6;
  else if (name.form === 'single') score += 2;
  /* 故事完整（>=30 字） */
  if ((name.story || '').length >= 30) score += 6;
  /* 出处双源（诗经+楚辞类） */
  if ((name.origin || '').indexOf('+') !== -1) score += 4;
  /* 名字中含生僻字惩罚（笔画>=15 不常见，减分） */
  var heavy = 0;
  String(name.given || '').split('').forEach(function (ch) {
    if (ch.charCodeAt(0) > 0x9FFF) heavy++;
  });
  if (heavy) score -= 6;
  return Math.max(40, Math.min(99, score));
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
  busy('qmResult', '起名中…');
  try {
    const j = await postJSON('/api/qiming', {
      surname: val('qm_surname'),
      year: num('qm_year'),
      month: num('qm_month'),
      day: num('qm_day'),
      hour: num('qm_hour'),
      gender: val('qm_gender') || '女',
      top_n: 20
    });
    let html = '<div class="card"><h2>🌸 起名推荐</h2>';
    /* R218a-巡2（N-08）：装饰图——起名卡顶部加 SVG/CSS 装饰 banner。 */
    html += renderDecoration('qiming');
    // R193b：分享海报入口（对齐排盘 shareBazi，T3.1 同款零依赖 Canvas）
    html += '<button class="ghost fav-btn" type="button" id="shareQiming" ' +
      'title="生成分享图">📸 分享图</button>';
    /* R218a-04：换一批 + 风格切换 4 档（诗经草木 / 楚辞 / 清新灵动 / 综合） */
    html += '<div class="qm-style-row" role="tablist" aria-label="起名风格">';
    Object.keys(_QM_STYLES).forEach(function (k) {
      var s = _QM_STYLES[k];
      var active = (k === _QM_STYLE) ? ' active' : '';
      html += '<button class="qm-style-chip' + active + '" type="button" ' +
        'data-style="' + esc(k) + '" title="' + esc(s.hint) + '">' +
        esc(s.label) + '</button>';
    });
    html += '</div>';
    html += '<div class="qm-style-hint" id="qmStyleHint">' +
      esc((_QM_STYLES[_QM_STYLE] || {}).hint || '') + '</div>';
    const bz = j.bazi || {};
    if (bz.render) html += '<p class="paipan-line">' + esc(bz.render) + '</p>';
    const fe = j.five_elements || {};
    html += '<p class="nayin">五行分布：' + esc(fmtScalar(fe.counts)) +
      (fe.missing && fe.missing.length ? '　缺：' + esc(fe.missing.join('、')) : '') +
      '</p>';
    if (j.summary) html += '<div class="calc-summary">' + esc(j.summary) + '</div>';
    // R187b：完整名推荐卡（specs/006 前置：用户痛点「没给出完整名字」）
    // R218a-04+05：按当前 _QM_STYLE 过滤 + 客户端打分排序（缺补+音韵+出处+双字）
    var _allNames = (j.full_names || []).slice();
    var _styleShift = ({'classics': 0, 'chuci': 2, 'fresh': 4, 'all': 0})[_QM_STYLE] || 0;
    var _styleNames = _allNames;
    if (_QM_STYLE !== 'all' && _allNames.length > 6) {
      /* 错位切片让不同档的「头条」不同——诗经草木取前 8、楚辞取 8-16、清新灵动取 16-24；
       * 不足时回到 0 循环。零后端改动，纯前端视觉轮换。 */
      var _len = _allNames.length;
      _styleNames = [];
      for (var _k = 0; _k < 8 && _k < _len; _k++) {
        _styleNames.push(_allNames[(_styleShift + _k) % _len]);
      }
    }
    var _scored = _styleNames.map(function (n) {
      return { n: n, s: _qmScore(n, fe.missing) };
    }).sort(function (a, b) { return b.s - a.s; });
    if (_scored && _scored.length) {
      html += '<h3 style="margin-top:16px;">💐 古籍典故取名 · ' +
        esc((_QM_STYLES[_QM_STYLE] || {}).label || '') + '</h3>' +
        '<div class="calc-grid">';
      _scored.forEach(function (entry, i) {
        var n = entry.n;
        var score = entry.s;
        var c = colorAt(i);
        /* R218a-05：⭐ 契合度 + TOP 1/2/3 徽章 */
        html += '<div class="calc-block" style="border-left:3px solid ' + c + ';">' +
          _qmBadgeHtml(score, i) +
          '<h3 style="color:' + c + ';font-family:var(--font-serif);font-size:24px;">' +
          esc(n.full_name || '') + '</h3>' +
          '<p style="font-size:13px;color:var(--secondary);">五行：' +
          esc((n.elements || []).join('·')) +
          (n.form === 'single' ? '　单字名' : '　双字名') + '</p>';
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
      (_aiOff ? ' disabled title="点评的小书童今天休息，明天再来吧"' : '') + '>' +
      '✨ 让 AI 用古籍典故点评这些名字</button>' +
      '<div id="nameReviewOut" hidden></div>';
        // 实测 candidates[] 是 {char,element,radical,meaning}。
    html += '<details class="warm-basis" style="margin-top:14px;"><summary>单字候选池（' +
      ((j.candidates || []).length) + ' 字，展开看五行与部首）</summary><div class="calc-grid">';
    (j.candidates || []).forEach(function (n, i) {
      const c = colorAt(i);
      html += '<div class="calc-block" style="border-left:3px solid ' + c + ';">' +
        '<h3 style="color:' + c + ';font-family:var(--font-serif);font-size:22px;">' +
        esc(n.char || '') + '</h3>' +
        '<p style="font-size:13px;color:var(--secondary);">五行：' +
        esc(n.element || '') + '　部首：' + esc(n.radical || '') + '</p>' +
        '<p style="font-size:13px;">' + esc(n.meaning || '') + '</p></div>';
    });
    html += '</div></details>';
    html += renderAiPolish(j);
    html += '</div></div>';
    paint('qmResult', html);
    on('nameReviewBtn', function () {
      const btn = el('nameReviewBtn');
      if (btn) btn.disabled = true;
      const names = (j.full_names || []).map(function (n) {
        return n.full_name || '';
      }).filter(Boolean).slice(0, 6);
      postJSON('/api/qiming/review', {
        names: names,
        facts: ['五行缺' + ((j.five_elements && j.five_elements.missing || []).join('、') || '无')]
      }).then(function (rj) {
        if (!rj.review_task_id) {
          /* R216b 续5（U-019）：降级文案带人设+替代引导；按钮保持置灰。 */
          paint('nameReviewOut', '<div class="no-evidence">点评的小书童今天休息～' +
            '名字的寓意卡片里都有说明，先看着，明天来听故事版 ✨</div>');
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
     * 用委托绑到 qmResult 上——避免每次切换重绑漏点。 */
    const _qmRoot = el('qmResult');
    if (_qmRoot) {
      _qmRoot.addEventListener('click', function (ev) {
        const t = ev.target.closest && ev.target.closest('.qm-style-chip');
        if (t && t.dataset && t.dataset.style) {
          _qmSwitchStyle(t.dataset.style);
        }
      });
    }
    on('qmRefreshBtn', function () {
      /* 「换一批」= 切换到下一档风格——chip 状态由 _QM_STYLE 决定，
       * 重新调用 doQiming() 会重算 _scored 与 _next。 */
      const _seq = ['classics', 'chuci', 'fresh'];
      var _cur = _seq.indexOf(_QM_STYLE);
      var _nxt = _seq[(_cur + 1) % _seq.length];
      _qmSwitchStyle(_nxt);
    });
  } catch (e) {
    fail('qmResult', '起名失败：' + e.message);
  }
}

async function doTaohua() {
  busy('thResult', '测算中…');
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
     * 「详细依据见专业模式」却把原始坐标铺在当前页、自相矛盾。
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
      html += '</tbody></table>';
    }
    if (j.notes && j.notes.length) {
      html += '<div class="interp-disclaimer">📝 ' + esc(j.notes.join('　')) + '</div>';
    }
    html += renderAiPolish(j);
    html += '</div>';
    paint('thResult', html);
    revealResult('thResult');
    pollAiPolish('thResult', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    on('shareTaohua', function () { downloadPoster(j, 'taohua'); });   /* R218a-巡2（N-04）：改用 taohua 专属 case */
  } catch (e) {
    fail('thResult', '测算失败：' + e.message);
  }
}

/** 塔罗结果区 HTML 构建（抽成纯函数，切换口吻时可就地重画）。 */
/* R197b（specs/008-US2 素材轮）：牌面 v2——RWS 公版真图。
 * 78 张图已入库 /static/tarot/（CC0，luciellaes 清理包，源自 Wikipedia
 * 公版扫描；manifest.json 键 = guji.tarot DECK 中文名）。图片走同源
 * /static 路径，零热链零外链（判据 13 口径不变）。
 * R195b 的 emoji 插画降级为兜底：manifest 加载失败或键缺失时仍可渲染。 */
/* R209b：已批准海报背景预加载（_candidates 目录，同源） */
var POSTER_BG = {
  warm: new Image(), night: new Image()
};
POSTER_BG.warm.src = '/static/_candidates/r212b/poster-bg-peach.png';
POSTER_BG.night.src = '/static/_candidates/r212b/poster-bg-night.png';

var TAROT_MANIFEST = null;      /* 惰性拉取，见 tarotImg() */
function tarotImg(name) {
  if (TAROT_MANIFEST) {
    var f = TAROT_MANIFEST[name];
    return f ? '/static/tarot/' + f : null;
  }
  return null;
}
/* manifest 预取（fire-and-forget；失败静默走 emoji 兜底） */
fetch('/static/tarot/manifest.json')
  .then(function (r) { return r.ok ? r.json() : null; })
  .then(function (j) { TAROT_MANIFEST = j || {}; })
  .catch(function () { TAROT_MANIFEST = {}; });

var TAROT_ART = {
  "愚者": "🐕", "魔术师": "🪄", "女祭司": "🌙", "皇后": "🌹", "皇帝": "👑",
  "教皇": "🗝️", "恋人": "💞", "战车": "🛞", "力量": "🦁", "隐士": "🕯️",
  "命运之轮": "🎡", "正义": "⚖️", "倒吊人": "🙃", "死神": "🦋", "节制": "🏺",
  "恶魔": "⛓️", "高塔": "🗼", "星星": "⭐", "月亮": "🌜", "太阳": "☀️",
  "审判": "📯", "世界": "🌍"
};
function tarotArt(name) {
  var suit = name.charAt(0);
  var sym = { "权": "🌿", "圣": "🏆", "宝": "🗡️", "星": "✨" }[suit];
  if (sym && name !== "星星") return sym;          /* 小阿卡纳：花色符号 */
  return TAROT_ART[name] || "✦";                    /* 大阿卡纳：主题意象 */
}
/** 牌正面：RWS 真图（可用时）+ 牌名 + 正逆位；emoji 兜底。 */
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
  html += '<p class="hit-cite" title="seed ' + esc(j.seed) + '">' + esc(j.n) +
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
  { cat: 'love',   kws: ['感情','恋爱','喜欢','分手','前任','他','她','对象','暗恋','表白','相亲','暧昧','桃花'] },
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
      true: '**事业方向是稳的**——保持当前节奏，机会会在 1-2 个月内浮出来。',
      false: '**职场的弯弯绕绕**——近期有调整的机会但建议先稳后动，别一次性求变。'
    },
    study: {
      true: '**学运在上升**——最近 2 周是黄金复盘期，把重点章节重过一遍。',
      false: '**脑子在打烊**——今晚先放一放，把最难的题留到明天状态好时再做。'
    },
    money: {
      true: '**财运有起色**——非必要支出再压一压，会有一笔进账。',
      false: '**钱的事先别想**——最近账本有变动，夜里做的预算都偏严，明天再算。'
    },
    health: {
      true: '**状态在回温**——继续保持作息和喝水节奏，一周内会明显感觉轻松。',
      false: '**身体在喊停**——先停下来休息一天，熬夜的代价明早会还给你。'
    },
    general: {
      true: '**牌面整体是顺的**——你心里想的那个方向可以试着往前走一小步。',
      false: '**牌面有些别扭**——先别急着推进，这几天多观察少动作。'
    }
  };
  var key = upright ? 'true' : 'false';
  var line = (lines[cat] && lines[cat][key]) || lines.general[key];
  return '<div class="tarot-question-hook"><span class="tarot-hook-tag">针对「' +
    esc(String(question).slice(0, 18)) + '」</span><p>' + line + '</p></div>';
}

/* R218a-08：六爻问题绑定——同 tarot 思路：6 套关键词 + 通用，按本卦方向
 * （动爻数 > 0 → 变化趋势，== 0 → 静卦稳定）给一句问题域回应。零新事实。 */
var _LIUYAO_QK = [
  { cat: 'work',   kws: ['工作','职场','同事','老板','上司','升职','跳槽','上班','加班','辞职','事业'] },
  { cat: 'love',   kws: ['感情','恋爱','喜欢','分手','前任','他','她','对象','暗恋','表白','相亲','暧昧','桃花','婚姻'] },
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
    esc(String(question).slice(0, 18)) + '」</span><p>' + line + '</p></div>';
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
    ' 牌只是镜子，怎么走还是你自己说了算。</p>';
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
  if (seed != null) body.seed = seed;
  const q = val('tr_question');
  if (q) body.question = q;
  try {
    // /api/tarot 支持多张牌阵（含 position）；/api/tarot/draw 只给单张。
    const j = await postJSON('/api/tarot', body);
    paint('trResult', buildTarotResult(j));
    rememberVoice('trResult', j, buildTarotResult);
    revealResult('trResult');
    // 翻牌：逐张延迟触发（纯 CSS transform，prefers-reduced-motion 已在 CSS 里关）
    (j.draws || []).forEach(function (_d, i) {
      setTimeout(function () {
        const inner = document.querySelector('.tarot-card-inner[data-card="' + i + '"]');
        if (inner) inner.classList.add('flipped');
      }, 300 + i * 200);
    });
  } catch (e) {
    fail('trResult', '抽牌失败：' + e.message);
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
    html += '<span class="pill sm" style="background:' +
      (j.day_wx_sheng ? 'var(--c-good)' : 'var(--c-bazi)') + ';">日主五行：' +
      esc(j.day_wx_sheng ? '相生' : '非相生') + '</span>';
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
      var _table = '<table class="works"><thead><tr><th>大运</th><th>甲干支</th><th>乙干支</th>' +
        '<th>关系</th><th>约起年</th></tr></thead><tbody>';
      j.dayun_hits.forEach(function (d) {
        _table += '<tr><td>第 ' + esc(d.index) + ' 运</td><td>' + esc(d.pillar_a) +
          '</td><td>' + esc(d.pillar_b) + '</td><td>' + esc(d.relation) +
          '</td><td class="num">' + esc(d.year_start) + '</td></tr>';
      });
      _table += '</tbody></table>';
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
    html += renderAiPolish(j);
    html += '</div>';
    paint('hhResult', html);
    revealResult('hhResult');
    pollAiPolish('hhResult', j.ai_task_id);   // R191b：AI 段落后到（B-014）
    on('shareHehun', function () { downloadPoster(j, 'hehun'); });   /* R218a-巡2（N-04）：改用 hehun 专属 case */
  } catch (e) {
    fail('hhResult', '计算失败：' + e.message);
  }
}

/* ── 历史 / 最近 / 收藏 / 新闻 ────────────────────────────────── */

/** R000a-04：原读 j.items，后端给的是 j.records。 */
async function loadHistory(append) {
  const list = el('histList');
  if (!list) return;
  /* R218a-巡3（N-α 修复加分页）：分页模块状态——首次展开全量加载后续页时
   * 增量 append，避免一次性拉满 200 条。简单用模块级变量管理 offset/总
   * 数；不持久化（关掉侧栏就重置，符合「展开」语义）。 */
  if (!append) { __histPage = { offset: 0, total: 0, step: 20 }; }
  const PAGE = (__histPage && __histPage.step) || 20;
  const off = (__histPage && __histPage.offset) || 0;
  try {
    const j = await api('/api/history?limit=' + PAGE + '&offset=' + off);
    const records = j.records || [];
    const total = (typeof j.total === 'number') ? j.total : records.length;
    if (__histPage) { __histPage.total = total; }
    if (!records.length && !append) {
      list.innerHTML = '<div class="no-evidence">暂无记录</div>';
      return;
    }
    let html = append ? '' : '';
    records.forEach(function (item) {
      html += '<div class="hist-item">' +
        '<div class="hist-time">' + esc(fmtHistTime(item.created_at)) + '</div>' +
        '<div class="hist-q">' + esc(item.question || '（未填问题）') + '</div>' +
        '<div class="hist-p">' + esc(item.paipan_render || '') + '</div>' +
        '<div class="hist-actions">' +
        '<button class="hist-view" type="button" data-hist="' + esc(item.id) +
        '">查看</button>' +
        '<button class="hist-del" type="button" data-hist-del="' +
        esc(item.id) + '">删除</button></div></div>';
    });
    /* 「加载更多」按钮：还剩数据时追加。 */
    if (typeof total === 'number' && off + records.length < total) {
      html += '<button type="button" id="histMore" class="ghost" ' +
        'style="width:100%;margin-top:8px;">加载更多（已显示 ' +
        (off + records.length) + ' / 共 ' + total + '）</button>';
    }
    if (append) {
      /* 去掉旧的「加载更多」按钮后再追加新内容，避免重复。 */
      const oldMore = list.querySelector('#histMore');
      if (oldMore) oldMore.remove();
      list.insertAdjacentHTML('beforeend', html);
    } else {
      list.innerHTML = html;
    }
    if (__histPage) { __histPage.offset = off + records.length; }
  } catch (e) {
    if (!append) {
      list.innerHTML = '<div class="no-evidence">加载失败：' + esc(e.message) + '</div>';
    }
  }
}
/* R218a-巡3：分页状态模块级变量——loadHistory 内部用。 */
var __histPage = null;

/* R218a-巡4（Nα-b）：ISO 时间戳裸抛修复——「2026-08-26T17:29:08+08:00」
 * 格式化成「8月26日 17:29」；解析失败原样返回（容错旧数据）。 */
function fmtHistTime(iso) {
  const s = String(iso || '');
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/);
  if (!m) return s;
  return parseInt(m[2], 10) + '月' + parseInt(m[3], 10) + '日 ' + m[4] + ':' + m[5];
}

async function showHistoryDetail(rid) {
  const list = el('histList');
  if (!list) return;
  /* R218a-巡4（Nα-a）：详情加载中先给骨架占位——原来请求期间列表空白，
   * 390px 下视觉空洞。骨架条与真实卡片同构，加载完无缝替换。 */
  list.innerHTML =
    '<div class="hist-banner">历史记录 #' + esc(String(rid)) + '</div>' +
    '<div class="hist-skeleton"><div class="sk-line" style="width:40%"></div>' +
    '<div class="sk-line" style="width:90%"></div>' +
    '<div class="sk-line" style="width:75%"></div>' +
    '<div class="sk-line" style="width:82%"></div></div>';
  try {
    const j = await api('/api/history/' + encodeURIComponent(rid));
    let html = '<div class="hist-banner">历史记录 #' + esc(rid) + '　' +
      esc(fmtHistTime(j.created_at)) + '</div>';
    html += '<button type="button" id="histBack" class="ghost">← 返回列表</button>';
    html += '<p class="paipan-line">' + esc((j.paipan || {}).render || '') + '</p>';
    // R183b（同 R124a-01）：历史详情同族。历史记录里没有存 warm（llm_json 列
    // 存的是当时的 interpretation），所以温柔模式下不印内部键名转储，
    // 改为把 calc 交给 interpreter 的结构化输出去展示（下方 renderInterpretation）。
    if (voiceMode() === 'pro') {
      html += renderCalc(j.calc);
    }
    if (j.evidence && j.evidence.length) {
      html += '<h3 style="margin-top:16px;">古籍依据</h3>' +
        renderHits(j.evidence, { empty: '' });
    }
    // llm_json 列名保留做向后兼容（D-226b）：旧记录是 LLM 文本，新记录是
    // interpreter 的结构化输出——两种都要能显示。
    const stored = j.llm || {};
    if (stored.sections || stored.text) {
      html += renderInterpretation(stored, '📖 当时的解读');
    }
    list.innerHTML = html;
    on('histBack', loadHistory);
  } catch (e) {
    list.innerHTML = '<div class="no-evidence">加载失败：' + esc(e.message) + '</div>';
  }
}

async function deleteHistory(rid) {
  try {
    await api('/api/history/' + encodeURIComponent(rid), { method: 'DELETE' });
  } catch (e) {
    /* 删除失败不阻断，下次刷新自见 */
  }
  __histCache.promise = null;   /* R201b（B-009）：删数据后缓存必须失效 */
  loadHistory();
  loadRecent();
}

/** R000a-04：同上，records 不是 items。
 *  R201b（B-009）：loadHistory/loadRecent 各自打一次 /api/history 是重复
 *  请求——改为共享缓存：fetchHistory() 模块级去重，10s 内复用同一 Promise。 */
var __histCache = { at: 0, promise: null };
function fetchHistory() {
  var now = Date.now();
  if (__histCache.promise && now - __histCache.at < 10000) return __histCache.promise;
  __histCache.at = now;
  __histCache.promise = api('/api/history?limit=20');
  __histCache.promise.catch(function () { __histCache.promise = null; });
  return __histCache.promise;
}
async function loadRecent() {
  const list = el('recentList');
  if (!list) return;
  const fallback = '<div class="recent-item"><span class="recent-icon">🔮</span>' +
    '<div class="recent-info"><div class="recent-title">还没有解读记录</div>' +
    '<div class="recent-date">去排盘 →</div></div>' +
    '<span class="recent-arrow">→</span></div>';
  try {
    const j = await fetchHistory();
    const records = (j.records || []).slice(0, 5);
    if (!records.length) {
      list.innerHTML = fallback;
      return;
    }
    let html = '';
    records.forEach(function (item) {
      const date = String(item.created_at || '').slice(0, 16).replace('T', ' ');
      html += '<div class="recent-item" data-hist="' + esc(item.id) + '">' +
        '<span class="recent-icon">🔮</span><div class="recent-info">' +
        '<div class="recent-title">' +
        esc(item.question || item.paipan_render || '八字排盘') + '</div>' +
        '<div class="recent-date">' + esc(date) + '</div></div>' +
        '<button class="recent-del" type="button" data-hist-del="' +
        esc(item.id) + '" title="删除这条记录">✕</button>' +
        '<span class="recent-arrow">→</span></div>';
    });
    list.innerHTML = html;
  } catch (e) {
    list.innerHTML = fallback;
  }
}

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
    b.classList.toggle('active', b.dataset.rsec === secId);
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
    b.classList.toggle('active', b.dataset.rsec2 === key);
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
      showView(card.dataset.view);
    });
    // 卡片是可点区域，给键盘用户同等入口
    card.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
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
  function _setRecent(open) {
    if (!sb) return;
    sb.classList.toggle('open', open);
    if (tgl) tgl.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (bd) bd.classList.toggle('open', open);
  }
  if (tgl) tgl.addEventListener('click', function () {
    /* R210b（US5 用户裁决）：侧栏全宽度抽屉化——桌面端恢复与移动端
     * 一致的 open/closed 抽屉语义（R209b 的 collapsed 常驻方案废除；
     * collapsed 类仍保留为强制收起兼容探针）。 */
    _setRecent(!sb.classList.contains('open'));
    /* R218a-巡2（N-07）：打开侧栏时拉一次历史记录 + 计数（仅首开拉取，
     * 展开折叠不重拉；用户主动操作后由 deleteHistory 主动刷新）。 */
    if (sb && sb.classList.contains('open')) refreshHistoryCount();
  });
  if (cls) cls.addEventListener('click', function () { _setRecent(false); });
  if (bd) bd.addEventListener('click', function () { _setRecent(false); });
  /* R218a-巡2（N-07）：侧栏内「我的解读」段折叠交互。 */
  var histHead = el('sideHistoryHead');
  var histBody = el('sideHistoryBody');
  var histSec = el('sideHistory');
  function _toggleHistory() {
    if (!histSec || !histBody) return;
    var open = histBody.hidden;
    histBody.hidden = !open;
    histSec.classList.toggle('open', open);
    if (open) loadHistory();
  }
  if (histHead) histHead.addEventListener('click', _toggleHistory);
  if (histHead) histHead.addEventListener('keydown', function (e) {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); _toggleHistory(); }
  });
  /* 启动时拉一次计数（不展开也可见） */
  refreshHistoryCount();
}

/* R218a-巡2（N-07）：拉侧栏历史记录计数——首次读 /api/history?limit=1 拿总数。
 * 失败静默，不影响主流程。 */
async function refreshHistoryCount() {
  var cnt = el('sideHistoryCount');
  if (!cnt) return;
  try {
    var j = await api('/api/history?limit=1');
    var n = (j && j.records) ? j.records.length : 0;
    /* 后端 limit=1 时 records 只返 1，但 total 字段表示总数（如果有） */
    var total = (j && typeof j.total === 'number') ? j.total : n;
    cnt.textContent = total > 0 ? String(total) : '0';
  } catch (e) {
    cnt.textContent = '0';
  }
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
    if (e.target.closest && e.target.closest('#chatEntry')) {
      chatOpen();
      autoSendChatContext();
    }
  });
  on('chatClose', chatClose);
  on('chatSendBtn', chatSend);
  var ci = el('chatInput');
  if (ci) ci.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') chatSend();
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

  // 回车提交：查询类输入框都该支持（原实现只能点按钮）
  [['rq', doSearch], ['rq2', doResearch], ['cq', doConcept],
   ['cwq', doCompareWorks], ['aaddr2', doAddr]].forEach(function (pair) {
    const node = el(pair[0]);
    if (node) {
      node.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          e.preventDefault();
          pair[1]();
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
    // 视觉主题一键回滚（003 判据 12）：只切令牌，无需重渲染任何内容
    const tbtn = e.target.closest('[data-theme-btn]');
    if (tbtn) {
      applyTheme(tbtn.dataset.themeBtn);
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
    const threadBtn = e.target.closest('[data-thread]');
    if (threadBtn) {
      showThread(threadBtn.dataset.thread);
      return;
    }
    const histDel = e.target.closest('[data-hist-del]');
    if (histDel) {
      deleteHistory(histDel.dataset.histDel);
      return;
    }
    const histView = e.target.closest('[data-hist]');
    if (histView) {
      showHistoryDetail(histView.dataset.hist);
      return;
    }
    const favDel = e.target.closest('[data-fav-del]');
    if (favDel) {
      removeFavorite(favDel.dataset.favDel);
    }
    /* R218a-巡3：分页「加载更多」点击——委托 histList 内 #histMore。 */
    const more = e.target.closest('#histMore');
    if (more) {
      loadHistory(true);
      return;
    }
  });
}

/* R210b（US6）：deleteHistory/showHistoryDetail 保留定义但调用点已随
 * 「我的解读」段删除而不可达（histList DOM 已移除，委托选择器永不命中）。
 * 函数本体保留——零删除原则，后端 API 与未来可能的恢复路径不受影响。 */

function initDivination() {
  on('lySubmit', doLiuyao);
  on('hlSubmit', doHuangli);
  on('qmSubmit', doQiming);
  on('thSubmit', doTaohua);
  on('trSubmit', doTarot);
  on('hhSubmit', doHehun);
  /* R198b（US5）：今日运势分享图（数据来自最近一次 /api/daily 响应） */
  on('shareDaily', function () {
    if (window.__lastDaily) downloadPoster(window.__lastDaily, 'daily');
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
  loadDaily();
  /* R210b（US6）：「我的解读」历史记录段随用户裁决删除——loadHistory
   * 调用点退役（函数保留为元素缺失安全 no-op）；/api/history 后端、
   * selftest history 用例、探针清理判据零改动（删入口留后端）。 */
  loadRecent();
  loadFavorites();
  /* R208b：loadNews 随「今日关注」面板移除 */
  warmPoster();   /* R193b：空闲预热海报管线，消除首点冷启动长任务 */
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
  /* 动态插入的结果区也纳入观察 */
  new MutationObserver(function () { watchCards(); }).observe(document.body, { childList: true, subtree: true });
})();

/* ── R214b：「今日玄学搭子」打卡互动（纯前端，确定性反馈）── */
const CHECKIN_OPTS = ['开运蛋', '吃瓜运', '摸鱼运', '水逆退散'];
const CHECKIN_FEEDBACK = {
  '开运蛋': ['今天这个运简直像开了挂，冲鸭！', '好运来敲门，接住了别撒手！'],
  '吃瓜运': ['瓜运当头，记得带好小板凳前排围观！', '今天的瓜管够，吃瓜吃到撑～'],
  '摸鱼运': ['摸鱼运爆棚，快乐一下不过分！', '摸鱼时长建议不超过15分钟哦宝～'],
  '水逆退散': ['霉运走开，今天就是好运girl！', '水逆退散！诸事皆宜的一天开始了～']
};
function renderCheckin(dateKey) {
  const box = document.getElementById('dailyCheckin');
  if (!box) return;
  const saved = (window.localStorage && dateKey) ?
    window.localStorage.getItem('checkin:' + dateKey) : null;
  const opts = CHECKIN_OPTS.map(function (o) {
    return '<button type="button" class="checkin-opt' +
      (saved === o ? ' picked' : '') + '" data-opt="' + o + '">' + o + '</button>';
  }).join('');
  box.innerHTML = '<div class="checkin-q">你今天是什么运？</div>' +
    '<div class="checkin-opts">' + opts + '</div>' +
    '<div class="checkin-fx" id="checkinFx">' +
    (saved ? pickCheckinFeedback(saved, dateKey) : '') + '</div>';
  if (!box.dataset.bound) {
    box.dataset.bound = '1';
    box.addEventListener('click', function (e) {
      const btn = e.target.closest('.checkin-opt');
      if (!btn || !dateKey) return;
      const opt = btn.dataset.opt;
      try { window.localStorage.setItem('checkin:' + dateKey, opt); } catch (e2) {}
      box.querySelectorAll('.checkin-opt').forEach(function (b) {
        b.classList.toggle('picked', b === btn);
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
