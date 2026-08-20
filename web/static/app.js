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
  }
}

function busy(id, text) {
  paint(id, '<div class="no-evidence">' + esc(text) + '</div>');
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
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
  }
  return body;
}

function postJSON(path, payload) {
  return api(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
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
  window.scrollTo({ top: 0, behavior: 'smooth' });
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

/** warm 视图（guji.voice 的输出）。四层结构，见 plan §1.2。
 *  判据 7：badge 渲染在能量卡之后、details 之前——不压轴收尾。
 *  判据 4：basis 推导链进 <details> 折叠，展开后逐字不变。 */
function renderWarm(warm, interp) {
  if (!warm) return renderInterpretation(interp, '📖 解读（确定性规则）');
  var html = '<div class="warm-wrap">';
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
  (warm.details || []).forEach(function (d) {
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
  // L3 citations：古籍原文，与 warm 文案视觉可辨（US2.5）
  var cites = warm.citations || [];
  if (cites.length) {
    html += '<div class="interp-sec cite-block"><h4>📜 古籍原文依据</h4>';
    cites.forEach(function (c) {
      html += '<div class="ev-item"><div class="ev-meta">' +
        esc(c.citation || '') + '</div><div class="ev-text">' +
        esc(c.text || '') + '</div></div>';
    });
    html += '</div>';
  }
  html += '</div>';
  return html;
}

/* 上一次响应缓存：切换口吻时就地重画，不重发请求。
 * 键 = 结果容器 id，值 = {json, proTitle, render}。render 是"用这份 json
 * 重画整个结果区"的闭包——切换只影响解读段，但结果区是一次性拼出来的
 * 字符串，所以整块重画最简单也最不容易漏。 */
var LAST_RESPONSE = {};

/** 按当前模式渲染解读区。warm 数据缺失时自动回落专业分支。 */
function renderVoice(j, proTitle) {
  var html = renderModeSwitch();
  if (voiceMode() === 'warm' && j && j.warm) {
    html += renderWarm(j.warm, j.interpretation);
  } else {
    html += renderInterpretation(j ? j.interpretation : null, proTitle);
  }
  return html;
}

/** 重画所有已渲染过的结果区（切换口吻时调用）。 */
function rerenderVoice() {
  Object.keys(LAST_RESPONSE).forEach(function (containerId) {
    var entry = LAST_RESPONSE[containerId];
    if (entry && typeof entry.render === 'function') {
      paint(containerId, entry.render(entry.json));
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
  let html = '<h3 style="margin-top:20px;color:var(--c-tarot);">' +
    esc(title || '📖 解读') +
    '<span class="interp-badge">' + esc(interp.engine || '确定性规则') + '</span></h3>';
  const secs = interp.sections || [];
  if (secs.length) {
    secs.forEach(function (s) {
      html += '<div class="interp-sec"><h4>' + esc(s.title || '') + '</h4><ul>';
      (s.lines || []).forEach(function (ln) {
        html += '<li>' + esc(ln) + '</li>';
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
    html += '<div class="interp-disclaimer">' + esc(interp.disclaimer) + '</div>';
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
    const dateEl = el('dailyDate');
    if (dateEl) dateEl.textContent = j.date || '今天';
    const level = j.level || '平';
    const levelEl = el('dailyLevel');
    if (levelEl) {
      levelEl.textContent = level;
      // 原实现用 `.daily-level平` 这种含中文的类名，CSS 里同款——已改为
      // good/mid/bad 三个 ASCII 类（styles.css 同步）。
      levelEl.className = 'daily-level ' +
        (level === '吉' ? 'good' : level === '凶' ? 'bad' : 'mid');
    }
    const starsEl = el('dailyStars');
    if (starsEl) starsEl.innerHTML = renderStars(level);
    setText('dailySummary', j.summary || '');
    setText('dailyNoble', j.noble || '—');
    setText('dailyDo', j.do || '—');
    setText('dailyDont', j.dont || '—');
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
      gender: '男',
      scope: 'day',
      question: '今天运势如何？'
    });
    let html = '<div class="card"><h2>🔍 今日完整解读</h2>';
    html += '<p class="paipan-line">' + esc((j.paipan || {}).render || '') + '</p>';
    html += renderCalc(j.calc);
    html += renderInterpretation(j.interpretation, '📖 今日解读');
    html += '</div>';
    target.innerHTML = html;
    target.dataset.loaded = '1';
  } catch (e) {
    target.innerHTML = '<div class="no-evidence">解读失败：' + esc(e.message) + '</div>';
  }
}

/* ── 八字排盘 ──────────────────────────────────────────────── */

function baziBody() {
  const calendar = val('calendar_type') || 'solar';
  const scope = val('scope') || 'day';
  const body = {
    year: num('year'),
    month: num('month'),
    day: num('day'),
    hour: num('hour'),
    gender: val('gender') || '男',
    calendar_type: calendar,
    scope: scope
  };
  if (calendar === 'lunar') {
    // 农历输入复用同三个输入框（HTML 只有一组年月日），后端要 lunar_* 键。
    body.lunar_year = body.year;
    body.lunar_month = body.month;
    body.lunar_day = body.day;
    body.lunar_leap = checked('lunar_leap');
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
function buildBaziResult(j) {
  const paipan = j.paipan || {};
  let html = '<div class="card"><h2>🔮 排盘结果</h2>';
  html += '<button class="ghost fav-btn" type="button" id="favBazi" ' +
    'title="收藏">❤️ 收藏</button>';
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
  if (paipan.warn && paipan.warn.length) {
    html += '<p class="warn">' + esc(paipan.warn.join('；')) + '</p>';
  }
  html += renderCalc(j.calc);
  if (j.evidence && j.evidence.length) {
    html += '<h3 style="margin-top:20px;color:var(--c-book);">📜 古籍依据</h3>';
    html += renderHits(j.evidence, { empty: '无引文' });
  }
  // R000a-04：原读 j.llm_out（后端从来没这个键）→ 现读 interpretation。
  html += renderVoice(j, '📖 解读（确定性规则）');
  html += '</div>';
  return html;
}

async function submitBazi(event) {
  if (event) event.preventDefault();
  busy('result', '计算中…');
  try {
    const j = await postJSON('/api/bazi', baziBody());
    const paipan = j.paipan || {};
    paint('result', buildBaziResult(j));
    rememberVoice('result', j, buildBaziResult);
    on('favBazi', function () {
      addFavorite('bazi', paipan.render || 'latest', '八字排盘 ' + (paipan.render || ''));
    });
    loadHistory();
    loadRecent();
  } catch (e) {
    fail('result', '计算失败：' + e.message);
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
      html += '<div class="calc-block work-card" data-work="' + esc(w.id) +
        '" style="border-left:3px solid ' + c + ';">' +
        '<h3 style="color:' + c + ';font-size:14px;">' + esc(w.title || w.id) + '</h3>' +
        '<p style="font-size:12px;color:var(--secondary);">' + esc(w.id) +
        ' · ' + esc(w.source || '') + '</p>' +
        '<p style="font-size:18px;color:' + c + ';font-weight:600;">' +
        esc(w.units == null ? '?' : w.units) + '</p>' +
        '<p style="font-size:11px;color:var(--secondary);">单元</p></div>';
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
      '（claim #' + esc(j.derived_id) + '）</div>';
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
  html += '<p class="paipan-line" style="color:var(--c-liuyao);">' +
    esc(ben.gua_name || '') + '（第 ' + esc(ben.gua_number) + ' 卦）</p>';
  // 实测 lines[] 是 {position,yang,moving,symbol}，moving_lines[] 是数字。
  if (ben.lines && ben.lines.length) {
    html += '<div class="pill-row">';
    ben.lines.forEach(function (ln) {
      html += '<span class="pill sm" style="background:' +
        (ln.moving ? 'var(--c-bazi)' : 'var(--secondary)') + ';">' +
        esc(ln.position) + ' ' + esc(ln.symbol || (ln.yang ? '⚊' : '⚋')) + '</span>';
    });
    html += '</div>';
  }
  if (ben.moving_lines && ben.moving_lines.length) {
    html += '<p>动爻：' + esc(ben.moving_lines.join('、')) + '</p>';
  } else {
    html += '<p>无动爻（静卦）</p>';
  }
  if (bian.gua_name) {
    html += '<p style="margin-top:8px;color:var(--secondary);">变卦：' +
      esc(bian.gua_name) + '（第 ' + esc(bian.gua_number) + ' 卦）</p>';
  }
  if (j.ben_jing && j.ben_jing.length) {
    html += '<h3 style="margin-top:16px;color:var(--c-book);">本卦經文</h3>' +
      renderHits(j.ben_jing, { empty: '' });
  }
  if (j.bian_jing && j.bian_jing.length) {
    html += '<h3 style="margin-top:16px;color:var(--c-book);">变卦經文</h3>' +
      renderHits(j.bian_jing, { empty: '' });
  }
  html += renderVoice(j, '📖 卦象转述（确定性规则）');
  html += '</div>';
  return html;
}

async function doLiuyao() {
  busy('lyResult', '摇卦中…');
  // 实测后端只认 coins|time（HTML 里原来的 "dice" 会得到 400）。
  const method = val('ly_method') === 'coins' ? 'coins' : 'time';
  const body = { method: method };
  if (method === 'coins') {
    const seed = num('ly_seed');
    if (seed != null) body.seed = seed;
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
    let html = '<div class="card"><h2>🌙 黄历 ' + esc(j.date || dateStr) + '</h2>';
    html += '<div class="pill-row">';
    if (j.jianchu) {
      html += '<span class="pill sm" style="background:var(--c-huangli);color:var(--text);">建除：' +
        esc(j.jianchu) + '</span>';
    }
    if (j.xiu) {
      html += '<span class="pill sm" style="background:var(--c-tarot);">二十八宿：' +
        esc(j.xiu) + '</span>';
    }
    html += '</div>';
    // 实测 pengzu 是 {gan,zhi,gan_text,zhi_text} 对象（不是字符串）。
    const pz = j.pengzu || {};
    if (pz.gan_text || pz.zhi_text) {
      html += '<div class="calc-block"><h3>彭祖百忌</h3><ul>' +
        '<li>' + esc(pz.gan || '') + '：' + esc(pz.gan_text || '') + '</li>' +
        '<li>' + esc(pz.zhi || '') + '：' + esc(pz.zhi_text || '') + '</li></ul></div>';
    }
    // 实测 yi/ji 是数组（不是字符串）。
    html += '<div class="calc-grid">';
    html += '<div class="calc-block" style="border-left:3px solid var(--c-good);">' +
      '<h3 style="color:var(--c-good);">✅ 宜</h3><p>' +
      esc((j.yi || []).join('、') || '—') + '</p></div>';
    html += '<div class="calc-block" style="border-left:3px solid var(--c-bazi);">' +
      '<h3 style="color:var(--c-bazi);">❌ 忌</h3><p>' +
      esc((j.ji || []).join('、') || '—') + '</p></div>';
    html += '</div></div>';
    paint('hlResult', html);
  } catch (e) {
    fail('hlResult', '查询失败：' + e.message);
  }
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
      gender: val('qm_gender') || '男',
      top_n: 20
    });
    let html = '<div class="card"><h2>🌸 起名推荐</h2>';
    const bz = j.bazi || {};
    if (bz.render) html += '<p class="paipan-line">' + esc(bz.render) + '</p>';
    const fe = j.five_elements || {};
    html += '<p class="nayin">五行分布：' + esc(fmtScalar(fe.counts)) +
      (fe.missing && fe.missing.length ? '　缺：' + esc(fe.missing.join('、')) : '') +
      '</p>';
    if (j.summary) html += '<div class="calc-summary">' + esc(j.summary) + '</div>';
    // 实测 candidates[] 是 {char,element,radical,meaning}。
    html += '<div class="calc-grid">';
    (j.candidates || []).forEach(function (n, i) {
      const c = colorAt(i);
      html += '<div class="calc-block" style="border-left:3px solid ' + c + ';">' +
        '<h3 style="color:' + c + ';font-family:var(--font-serif);font-size:22px;">' +
        esc(n.char || '') + '</h3>' +
        '<p style="font-size:13px;color:var(--secondary);">五行：' +
        esc(n.element || '') + '　部首：' + esc(n.radical || '') + '</p>' +
        '<p style="font-size:13px;">' + esc(n.meaning || '') + '</p></div>';
    });
    html += '</div></div>';
    paint('qmResult', html);
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
      gender: val('th_gender') || '男'
    });
    let html = '<div class="card"><h2>🌺 桃花运</h2>';
    const bz = j.bazi || {};
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
      ['命中柱', (j.hit_pillars || []).join('、') || '无'],
      ['红鸾', j.hongluan], ['红鸾落柱', (j.hongluan_pillar || []).join('、') || '无'],
      ['天喜', j.tianxi], ['天喜落柱', (j.tianxi_pillar || []).join('、') || '无'],
      ['强弱', j.strength]
    ].forEach(function (pair, i) {
      html += '<div class="calc-block" style="border-left:3px solid ' + colorAt(i) +
        ';"><h3>' + esc(pair[0]) + '</h3><p>' + esc(fmtScalar(pair[1])) + '</p></div>';
    });
    html += '</div>';
    if (j.render) {
      html += '<div class="calc-summary" style="border-left-color:var(--c-taohua);">' +
        esc(j.render) + '</div>';
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
    html += '</div>';
    paint('thResult', html);
  } catch (e) {
    fail('thResult', '测算失败：' + e.message);
  }
}

/** 塔罗结果区 HTML 构建（抽成纯函数，切换口吻时可就地重画）。 */
function buildTarotResult(j) {
  let html = '<div class="card"><h2>✨ 塔罗占卜</h2>';
  html += '<p class="hit-cite">seed ' + esc(j.seed) + ' · ' + esc(j.n) + ' 张（固定 seed 必得同样牌面，可复验）</p>';
  html += '<div class="tarot-grid">';
  (j.draws || []).forEach(function (d, i) {
    html += '<div class="tarot-cell"><div class="tarot-card-wrap">' +
      '<div class="tarot-card-inner" data-card="' + i + '">' +
      '<div class="tarot-card-face tarot-card-back">知</div>' +
      '<div class="tarot-card-face tarot-card-front">' +
      '<div class="tname">' + esc(d.name) + '</div>' +
      '<div class="tmeaning">' + esc(d.upright ? '正位' : '逆位') + '<br>' +
      esc(d.upright ? d.upright_kw : d.reversed_kw) + '</div></div>' +
      '</div></div>' +
      '<div class="tarot-pos">' + esc(d.position || ('第' + (i + 1) + '张')) +
      '</div></div>';
  });
  html += '</div>';
  html += renderVoice(j, '📖 牌面转述（确定性规则）');
  html += '</div>';
  return html;
}

async function doTarot() {
  busy('trResult', '抽牌中…');
  const seed = num('tr_seed');
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
      a_gender: val('hh_a_gender') || '男',
      b_year: num('hh_b_year'),
      b_month: num('hh_b_month'),
      b_day: num('hh_b_day'),
      b_hour: num('hh_b_hour'),
      b_gender: val('hh_b_gender') || '女'
    });
    const a = j.a_bazi || {};
    const b = j.b_bazi || {};
    let html = '<div class="card"><h2>💕 八字合婚</h2><div class="calc-grid">';
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
    html += '</div>';
    if (j.render) html += '<div class="calc-summary">' + esc(j.render) + '</div>';
    if (j.dayun_hits && j.dayun_hits.length) {
      html += '<h3 style="margin-top:16px;">大运冲合应期</h3>' +
        '<table class="works"><thead><tr><th>大运</th><th>甲干支</th><th>乙干支</th>' +
        '<th>关系</th><th>约起年</th></tr></thead><tbody>';
      j.dayun_hits.forEach(function (d) {
        html += '<tr><td>第 ' + esc(d.index) + ' 运</td><td>' + esc(d.pillar_a) +
          '</td><td>' + esc(d.pillar_b) + '</td><td>' + esc(d.relation) +
          '</td><td class="num">' + esc(d.year_start) + '</td></tr>';
      });
      html += '</tbody></table>';
    }
    if (j.notes && j.notes.length) {
      html += '<div class="interp-disclaimer">📝 ' + esc(j.notes.join('　')) + '</div>';
    }
    html += '</div>';
    paint('hhResult', html);
  } catch (e) {
    fail('hhResult', '计算失败：' + e.message);
  }
}

/* ── 历史 / 最近 / 收藏 / 新闻 ────────────────────────────────── */

/** R000a-04：原读 j.items，后端给的是 j.records。 */
async function loadHistory() {
  const list = el('histList');
  if (!list) return;
  try {
    const j = await api('/api/history?limit=20');
    const records = j.records || [];
    if (!records.length) {
      list.innerHTML = '<div class="no-evidence">暂无记录</div>';
      return;
    }
    let html = '';
    records.forEach(function (item) {
      html += '<div class="hist-item">' +
        '<div class="hist-time">' + esc(item.created_at || '') + '</div>' +
        '<div class="hist-q">' + esc(item.question || '（未填问题）') + '</div>' +
        '<div class="hist-p">' + esc(item.paipan_render || '') + '</div>' +
        '<div class="hist-actions">' +
        '<button class="hist-view" type="button" data-hist="' + esc(item.id) +
        '">查看</button>' +
        '<button class="hist-del" type="button" data-hist-del="' + esc(item.id) +
        '">删除</button></div></div>';
    });
    list.innerHTML = html;
  } catch (e) {
    list.innerHTML = '<div class="no-evidence">加载失败：' + esc(e.message) + '</div>';
  }
}

async function showHistoryDetail(rid) {
  const list = el('histList');
  if (!list) return;
  try {
    const j = await api('/api/history/' + encodeURIComponent(rid));
    let html = '<div class="hist-banner">历史记录 #' + esc(rid) + '　' +
      esc(j.created_at || '') + '</div>';
    html += '<button type="button" id="histBack" class="ghost">← 返回列表</button>';
    html += '<p class="paipan-line">' + esc((j.paipan || {}).render || '') + '</p>';
    html += renderCalc(j.calc);
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
  loadHistory();
  loadRecent();
}

/** R000a-04：同上，records 不是 items。 */
async function loadRecent() {
  const list = el('recentList');
  if (!list) return;
  const fallback = '<div class="recent-item"><span class="recent-icon">🔮</span>' +
    '<div class="recent-info"><div class="recent-title">还没有解读记录</div>' +
    '<div class="recent-date">去排盘 →</div></div>' +
    '<span class="recent-arrow">→</span></div>';
  try {
    const j = await api('/api/history?limit=5');
    const records = j.records || [];
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
        '<span class="recent-arrow">→</span></div>';
    });
    list.innerHTML = html;
  } catch (e) {
    list.innerHTML = fallback;
  }
}

async function loadFavorites() {
  const list = el('favoritesList');
  if (!list) return;
  const fallback = '<div class="recent-item"><span class="recent-icon">🌟</span>' +
    '<div class="recent-info"><div class="recent-title">还没有收藏，' +
    '看到喜欢的解读就点 ❤️ 吧</div><div class="recent-date">去排盘 →</div></div>' +
    '<span class="recent-arrow">→</span></div>';
  try {
    const j = await api('/api/user/prefs');
    const favs = j.favorites || [];
    if (!favs.length) {
      list.innerHTML = fallback;
      return;
    }
    const icons = { bazi: '🔮', tarot: '✨', book: '📜', thread: '🧶' };
    let html = '';
    favs.forEach(function (f) {
      html += '<div class="recent-item"><span class="recent-icon">' +
        esc(icons[f.type] || '⭐') + '</span><div class="recent-info">' +
        '<div class="recent-title">' + esc(f.title || '') + '</div>' +
        '<div class="recent-date">' + esc(String(f.created_at || '').slice(0, 16)) +
        '</div></div>' +
        '<button class="hist-del" type="button" data-fav-del="' + esc(f.id) +
        '">移除</button></div>';
    });
    list.innerHTML = html;
  } catch (e) {
    list.innerHTML = fallback;
  }
}

async function addFavorite(type, refId, title) {
  try {
    await postJSON('/api/favorites', { type: type, ref_id: String(refId), title: title });
    loadFavorites();
    return true;
  } catch (e) {
    return false;
  }
}

async function removeFavorite(fid) {
  try {
    await api('/api/favorites/' + encodeURIComponent(fid), { method: 'DELETE' });
  } catch (e) {
    /* 忽略 */
  }
  loadFavorites();
}

async function loadNews() {
  const list = el('newsList');
  if (!list) return;
  list.innerHTML = '<div class="no-evidence">加载中…</div>';
  try {
    const j = await api('/api/external/news');
    let html = '';
    (j.sources || []).forEach(function (s) {
      if (!s.ok) return;
      html += '<div class="news-src">' + esc(s.title) + '</div>';
      (s.items || []).forEach(function (it) {
        html += '<div class="news-item"><a href="' + esc(it.link) +
          '" target="_blank" rel="noopener noreferrer">' + esc(it.title || '') + '</a>' +
          '<span class="news-time">' + esc(it.published || '') + '</span></div>';
      });
    });
    list.innerHTML = html || '<div class="no-evidence">暂无新闻（外部资讯需代理可用）</div>';
    const meta = el('newsMeta');
    if (meta) {
      meta.textContent = j.error
        ? '外部资讯不可用：' + j.error
        : '抓取时间：' + (j.fetched_at || '—');
    }
  } catch (e) {
    list.innerHTML = '<div class="no-evidence">刷新失败：' + esc(e.message) + '</div>';
  }
}

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
  on('newsRefresh', loadNews);
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
  });
}

function initDivination() {
  on('lySubmit', doLiuyao);
  on('hlSubmit', doHuangli);
  on('qmSubmit', doQiming);
  on('thSubmit', doTaohua);
  on('trSubmit', doTarot);
  on('hhSubmit', doHehun);
}

function init() {
  initViews();
  initBazi();
  initReading();
  initDivination();
  loadDaily();
  loadHistory();
  loadRecent();
  loadFavorites();
  loadNews();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
