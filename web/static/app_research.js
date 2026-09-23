/* R2400（R122-P1-1 下）：古籍域/研究台懒加载 chunk——app.js 里 15 个
 * 研究台 handler（检索/研究/编址/比对/书目/线程/两书对照/概念/读书三子页）
 * 整体搬出主包。app.js 留同名 stub，首次进 ?view=read 或点研究台按钮时
 * _loadResearchJs() 注入本文件，真身覆盖同名 stub。
 * 约束（与 app_poster.js 同款）：
 *  - 只放 read/research 域私有函数；被主域共享的（renderHits/fmtScalar/
 *    humanCite/_SCHEME_CN/_rmMarks/colorAt/busy/fail/paint/esc/api/
 *    postJSON/showToast/guardedCall/val/num/_failField/_dayPick/
 *    activateRsec/activateBssec/_ASCHEME_FIELDS/_threadStatus）留 app.js，
 *    本文件按全局名直接引用（经典脚本共享 window 级变量）。
 *  - 不写模块级 DOM 副作用——本文件在用户已进页后才解析。 */

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
  if (maxAddr != null) {
    params.set('max_addresses', String(Math.min(Math.max(maxAddr, 1), 6)));
    /* R2350e（R101-P2-7）：钳位与 tr_n 同口径——静默吃掉用户填的
     * 99 会让人以为生效了；照塔罗做法给一句轻提示。 */
    if (maxAddr > 6 || maxAddr < 1)
      showToast('每处最多取 6 条，已按范围内处理', 'info');
  }
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
        html += '<li>' + esc(/* R2349v（R92-P1-3）：链路行话翻人话 */
          ({search:'先按整句找', 'search-fallback':'整句没命中，换子句翻',
            witnesses:'同一位置各版本对照', compare:'并排比对异文',
            'link-hop':'顺着卦序往下翻'})[s.action] || s.action || '') +
          ' 「' + esc(s.query || '') + '」 → 翻到 ' +
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
          html += '<div class="finding">' + esc(_rmMarks(f.line || f.note || '')) + '</div>';
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
  /* R2350e（R101-P1-3 附带）：addr 侧同款爻位校验。 */
  const _ayv = val('ayao');
  if (_ayv && !/^(初|二|三|四|五|上)(九|六)$|^用(九|六)$/.test(_ayv)) {
    _failField('ayao', 'addrResult',
      '爻位写法不对——填「初九」「九二」…「上六」，或乾坤专属的「用九/用六」');
    return;
  }
  const params = new URLSearchParams();
  var _asch0 = val('ascheme') || 'zhouyi';
  params.set('scheme', _asch0);
  /* R2350e（R101-P2-5/P2-6）：①卦号走 num()——「5.9」不再原文外发
   * 吃 422；②按当前编址方式白名单收参——隐藏字段的残值（切到 bcv
   * 后 aguan/ayao 旧值）不再随 query 发出。 */
  var _asend = _ASCHEME_FIELDS[_asch0] || [];
  if (_asend.indexOf('aguan') >= 0 && num('aguan') != null)
    params.set('gua', String(num('aguan')));
  if (_asend.indexOf('ayao') >= 0 && _ayv) params.set('yao', _ayv);
  if (_asend.indexOf('aname') >= 0 && val('aname'))
    params.set('addr_name', val('aname'));
  if (_asend.indexOf('aaddr1') >= 0 && val('aaddr1'))
    params.set('addr1', val('aaddr1'));
  if (_asend.indexOf('aaddr2') >= 0 && val('aaddr2'))
    params.set('addr2', val('aaddr2'));
  try {
    const j = await api('/api/addr?' + params.toString());
    /* R2400（R125-P2）：结果头此前直出裸 scheme 名（zhouyi）——
     * 用下拉框同款中文标签。 */
    var _aschOpt = document.querySelector('#ascheme option:checked');
    var _aschLabel = (_aschOpt && _aschOpt.textContent) || j.scheme;
    paint('addrResult',
      '<p class="hit-cite">' + esc(_aschLabel) + ' · 翻到 ' + esc(j.count) + ' 条</p>' +
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
  /* R2350e（R101-P1-3 附带）：爻位词表校验——「abc」这类非法爻名
   * 此前直发后端，渲染出「说法不一样+无差异」自相矛盾卡。 */
  const _cyv = val('cyao');
  if (_cyv && !/^(初|二|三|四|五|上)(九|六)$|^用(九|六)$/.test(_cyv)) {
    _failField('cyao', 'compareResult',
      '爻位写法不对——填「初九」「九二」…「上六」，或乾坤专属的「用九/用六」');
    return;
  }
  const params = new URLSearchParams({ gua: String(gua) });
  if (_cyv) params.set('yao', _cyv);
  try {
    const j = await api('/api/compare?' + params.toString());
    /* R2350e（R101-P1-3）：后端 no_witness 三态此前未消费——
     * 「卦28·用九」这类合法但无比对材料的查询渲染成
     * 「几种版本说法不一样+无差异发现」自相矛盾卡。第三态单列。 */
    if (j.no_witness) {
      paint('compareResult',
        '<h3>' + esc(j.addr || '') + '</h3>' +
        '<div class="no-evidence">📖 这一处没找到可比对的版本材料' +
        '——换个卦爻，或不带爻位整卦比对试试。</div>');
      return;
    }
    let html = '<h3>' + esc(j.addr || '') +
      (j.reference ? '　以《' + esc(j.reference) + '》为底本' : '') + '　' +
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
          esc(_rmMarks(f.line || (f.kind + ' @' + f.at + ' ' + f.base))) + '</div>';
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

/** 书目卡片点击 → 打开这本书（读书 tab 的结构页）。
 * R2349v（R92-P2-4）：此前点书卡跳检索页+硬塞默认词「無爲」——
 * 英文书稳定 0 命中，「打开书」的意图落空成「按书过滤的搜索」。 */
function searchByWork(workId) {
  var wf = el('bswork');
  if (wf) wf.value = workId;
  activateRsec('rsec-bookstudy');
  activateBssec('bs-structure');
  showToast('翻开了这本书的结构——点章节看正文', 'info');
}

/** 研究线程：原来发 {topic}，后端要 {kind,claim,method} → 必然 422
 *  （R000a-05）。这里按 ThreadRecordRequest 发一条 refusal 型 claim——
 *  refusal 是唯一允许无证据的 kind（G7：「证据不足」本身是合法研究输出），
 *  正好适配"新建一个空线程"这个语义。 */
async function doThread() {
  busy('threadResult', '创建中…');
  const topic = val('tq') || '新线程';
  /* R2349v（R92-P2-6）：空主题原来静默开一条「新线程」——先内联提示，
   * 用户知道自己在建什么。 */
  if (!val('tq')) {
    var _tq = el('tq');
    if (_tq && !_tq.value.trim()) { showToast('先写个主题名，比如「无为在不同本子的差异」', 'info'); return; }
  }
  try {
    try { localStorage.setItem('threads_seen_v1', '1'); } catch (eTS) {}
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

async function _threadListHtml() {
  /* R2349z（R96-P1-1a）：收起的/聊完的线程此前从列表永久消失——
   * 后端 resume() 只查 open。加状态过滤 chip，默认仍「进行中」。 */
  const list = await api('/api/threads?status=' +
                         encodeURIComponent(_threadStatus));
  var html = '<div class="thread-filters" style="display:flex;gap:6px;' +
    'margin-bottom:8px;flex-wrap:wrap;">' +
    [['open', '进行中'], ['parked', '先收起'], ['closed', '已结束']]
      .map(function (kv) {
        return '<button type="button" class="chip' +
          (_threadStatus === kv[0] ? ' active' : '') +
          '" data-thread-filter="' + kv[0] + '">' + kv[1] + '</button>';
      }).join('') + '</div>';
  /* R2400（R124-P1-1）：0 条线程时只剩筛选条+整片空白——按状态给
   * 相应的空态句（进行中没有就引导开一个，收起/结束是正常空空）。 */
  if (!(list.threads || []).length) {
    /* R2400（R138-P0-2）：清盘后谎称「还没开过」——本地标记住
     * 「有过线程」；空+见过 = 云端被清，说真话。 */
    var _seenT = false;
    try { _seenT = localStorage.getItem('threads_seen_v1') === '1'; }
    catch (eS) {}
    var _emptyTxt = _seenT
      ? '云端的研究记录被服务重启清掉了——这类笔记只存服务器上，重启就没啦。'
      : {open: '还没有进行中的研究线程——搜个词顺手开一个？',
         parked: '没有先收起的线程。',
         closed: '还没有聊完的线程。'}[_threadStatus];
    return html + '<div class="ph-empty" style="margin-top:10px;">' +
      _emptyTxt + '</div>';
  }
  try { localStorage.setItem('threads_seen_v1', '1'); } catch (eT) {}
  (list.threads || []).forEach(function (t) {
    /* R232d（R40-A12）：opened_at 一直在回——补上「开题日期」让老线程
     * 一眼可辨新旧（updated_at 只记最近动静）。 */
    var _opened = t.opened_at ? (' · 开题 ' + esc(t.opened_at)) : '';
    html += '<div class="thread-item"><div class="thread-topic">' +
      esc(t.topic || '') + '</div>' +
      '<div class="thread-meta">#' + esc(t.id) + ' · ' +
      /* R2349z（R96-P1-1b）：'shelved' 是死键——后端枚举是
       * open/parked/closed，收起的线程此前渲染裸 'parked'。 */
      esc({open:'进行中', closed:'已结束', parked:'先收起'}[t.status] || t.status) +
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

async function deleteThread(tid, btn) {
  /* R2400（R124-P2-3）：原生 confirm() 与全局两段式口径不一致——
   * 对齐排盘历史的「再点一次确认」武装模式（3s 窗口）。 */
  if (btn) {
    if (btn.dataset.armed !== '1') {
      btn.dataset.armed = '1';
      var _origTxt = btn.textContent;
      btn.textContent = '再点确认';
      btn.setAttribute('aria-label', '再点一次确认删除这条线程');
      setTimeout(function () {
        btn.dataset.armed = '';
        btn.textContent = _origTxt;
        btn.removeAttribute('aria-label');
      }, 3000);
      return;
    }
    btn.dataset.armed = '';
  }
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
    var _KIND_CN = { thread: '线程', summary: '笔记', note: '笔记',
      answer: '结论', link: '关联', diff: '比对', refusal: '存疑' };
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
    /* R2349v（R92-P2-6）：「证据回查：0 条还能对得上」对空线程是噪音。 */
    if (j.verify && (j.verify.ok || j.verify.stale)) {
      html += '<div class="interp-basis">证据回查：' + esc(j.verify.ok) +
        ' 条还能对得上' + (j.verify.stale ? '，' + esc(j.verify.stale) +
        ' 条过期了' : '') + '</div>';
    }
    /* R2349v（R92-P1-2）：线程此前只能开/看/删——后端记 claim /
     * 改状态全套接口空转。详情页补「记一条」表单 + 状态钮。 */
    /* R2349z（R96-P1-1c）：详情页此前无回列表入口——再点 tab 也因
     * threadResult 非空不重画，只能刷新页面。 */
    html += '<div style="margin-bottom:10px;">' +
      '<button type="button" class="thread-view" data-thread-back="1">' +
      '← 回列表</button></div>' +
      '<div class="thread-note" style="margin-top:14px;">' +
      '<label for="threadNote" style="font-size:13px;color:var(--secondary);">' +
      '记一条（这条线程的心得/结论）</label>' +
      '<textarea id="threadNote" class="question-input" rows="2" maxlength="2000" ' +
      'placeholder="比如：比较了几个本子，道德经 X 章的说法不一样…"></textarea>' +
      '<div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap;">' +
      '<button type="button" class="thread-view" data-thread-note="' + esc(tid) +
      '">记下来</button>' +
      '<button type="button" class="thread-view" data-thread-status="' + esc(tid) +
      '|open">继续聊</button>' +
      '<button type="button" class="thread-view" data-thread-status="' + esc(tid) +
      '|parked">先收起</button>' +
      '<button type="button" class="thread-view" data-thread-status="' + esc(tid) +
      '|closed">这条聊完了</button>' +
      '<button type="button" class="thread-del" data-thread-del="' + esc(tid) +
      '" aria-label="删除线程 #' + esc(tid) + '">删</button></div></div>';
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
    let html = '<h3>《' + esc(j.title || j.work_id) + '》 · 编址：' +
      esc(_SCHEME_CN[j.scheme] || j.scheme) +
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
    let html = '<h3>' + esc(j.work_id) + ' · ' + esc(_SCHEME_CN[j.scheme] || j.scheme) + ' 第 ' +
      esc(j.section) + ' 节 · ' + esc(j.n_units) + ' 段</h3>';
    (j.units || []).forEach(function (u) {
      html += '<div class="ev-item"><div class="ev-meta">' + esc(humanCite(u.citation || '')) +
        (u.addr2 ? ' · ' + esc(u.addr2) : '') + (u.layer ? ' · ' + esc(u.layer) : '') +
        (u.suspect ? ' ⚠ 存疑' : '') + '</div>' +
        '<div class="ev-text">' + esc(_rmMarks(u.text || '')) + '</div></div>';
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
