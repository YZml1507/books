# -*- coding: utf-8 -*-
"""R28-c：登录/注册表单样式。用户原话「登录和注册页面好丑好丑，排版有问题」。"""
import io, sys
C = "/opt/books/app/web/static/styles.css"
with io.open(C, "r", encoding="utf-8") as f:
    c = f.read()

ANCHOR = ".acct-tip { font-size: 12px; color: var(--secondary); line-height: 1.5; }"
if c.count(ANCHOR) != 1:
    sys.exit("FAIL[anchor] count=%d" % c.count(ANCHOR))
if ".acct-tabs{" in c:
    sys.exit("FAIL[dup]")

NEW = ANCHOR + """

/* ---- R28-c：登录/注册表单重做 ----------------------------------------
   旧版三处硬伤：① 性别组和两颗同款 .ghost 按钮挤在同一行，主次不分；
   ② 生辰四格 flex-wrap，窄屏折成参差不齐的两行；③ 输入框没有统一的
   边框/圆角/内距，靠全局 input 样式兜底。 */
.acct-tabs{
  display:flex; gap:4px; padding:4px; margin-bottom:4px;
  background:var(--cream, #fdf6ec); border-radius:999px;
  border:1px solid rgba(180,140,90,.22);
}
.acct-tab{
  flex:1; min-height:38px; padding:0 10px;
  font-size:14px; font-weight:600; letter-spacing:.02em;
  color:var(--secondary); background:transparent;
  border:0; border-radius:999px; cursor:pointer;
  transition:background .18s ease, color .18s ease;
  -webkit-tap-highlight-color:transparent;
}
.acct-tab.is-on{
  color:#fff;
  background:linear-gradient(135deg,var(--accent-ink),var(--accent,#e2a76f));
  box-shadow:0 2px 8px rgba(160,110,60,.28);
}
.acct-form input{
  width:100%; min-height:44px; padding:10px 14px;
  font-size:16px; color:var(--ink,#3b2f26);
  background:#fff; border:1px solid rgba(180,140,90,.32);
  border-radius:14px; outline:none;
  transition:border-color .18s ease, box-shadow .18s ease;
}
.acct-form input:focus{
  border-color:var(--accent-ink);
  box-shadow:0 0 0 3px rgba(226,167,111,.22);
}
.acct-form input::placeholder{ color:var(--muted); }
/* 生辰四格定宽四栏，不再 wrap——窄屏也是整齐的一行 */
.acct-birth-row{
  display:grid; grid-template-columns:repeat(3,1fr) 1.15fr;
  gap:6px; margin-top:6px;
}
.acct-birth-row input{
  min-width:0; text-align:center; padding:10px 4px; font-size:15px;
}
.acct-gender{ margin:10px 0 2px; }
.acct-gender-row{ display:grid; grid-template-columns:1fr 1fr; gap:8px; margin-top:6px; }
.acct-gender-btn{
  min-height:44px; font-size:14px; font-weight:600;
  border-radius:14px; border:1px dashed rgba(180,140,90,.4);
  background:#fff; color:var(--secondary);
}
.acct-gender-btn.is-on{
  border-style:solid; border-color:var(--accent-ink);
  color:var(--accent-ink); background:rgba(226,167,111,.14);
}
.acct-gender-note{ display:block; margin-top:6px; font-size:11px; color:var(--muted); }
/* 主操作：唯一、满宽、有重量——不再和次要按钮并排让人猜 */
.acct-go{
  width:100%; min-height:48px; margin-top:6px;
  font-size:16px; font-weight:700; letter-spacing:.04em; color:#fff;
  background:linear-gradient(135deg,var(--accent-ink),var(--accent,#e2a76f));
  border:0; border-radius:16px; cursor:pointer;
  box-shadow:0 4px 14px rgba(160,110,60,.3);
  transition:transform .14s ease, box-shadow .18s ease, filter .18s ease;
  -webkit-tap-highlight-color:transparent;
}
.acct-go:hover{ filter:brightness(1.05); box-shadow:0 6px 18px rgba(160,110,60,.36); }
.acct-go:active{ transform:translateY(1px); box-shadow:0 2px 8px rgba(160,110,60,.28); }
/* 深色模式下输入框别糊成一片 */
@media (prefers-color-scheme: dark){
  .acct-form input{ background:rgba(255,255,255,.07); color:inherit; }
  .acct-gender-btn{ background:rgba(255,255,255,.05); color:inherit; }
  .acct-gender-btn.is-on{ background:rgba(226,167,111,.2); }
}
/* 「我的」里备份工具和记忆卡的呼吸 */
#myTools{ margin-top:14px; }
#myTools .ph-hint{ margin-top:8px; }"""

c = c.replace(ANCHOR, NEW, 1)
with io.open(C, "w", encoding="utf-8") as f:
    f.write(c)
print("css OK")
