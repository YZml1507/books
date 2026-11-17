# -*- coding: utf-8 -*-
import io, sys
CSS="/opt/books/app/web/static/styles.css"
with io.open(CSS,"r",encoding="utf-8") as f: c=f.read()
OLD = """/* R3205 续：超矮视口（568px 级老机/横屏）再收一档——卡帽 ~306px。 */
@media (max-width:600px) and (max-height:600px){
  .daily-card:has(> .daily-cover:not(.open):not(.mini)) .daily-cover img{
    width:132px;}
}"""
NEW = OLD + """
/* R24（用户实测「封面图没有显示全」）：桌面档封面图是 200px 宽（约 190px 高），
 * 加 padding-top:min(15vh,130px) + 两行 CTA，在「宽而矮」的桌面窗下会把图和
 * 文字顶出卡帽（max-height:min(42vh,400px)）。实测 1400×540：图超卡底 5px、
 * CTA 超 46px；1400×620：CTA 仍超 20px。R3205 只修了 max-width:600px，
 * 漏了 min-width:601px 且矮的这一档。 */
@media (min-width:601px) and (max-height:720px){
  .daily-card:has(> .daily-cover:not(.open):not(.mini)) .daily-cover{
    padding-top:min(8vh, 64px); gap:8px;}
  .daily-card:has(> .daily-cover:not(.open):not(.mini)) .daily-cover img{
    width:132px;}
}
@media (min-width:601px) and (max-height:600px){
  .daily-card:has(> .daily-cover:not(.open):not(.mini)) .daily-cover{
    padding-top:min(6vh, 48px);}
  .daily-card:has(> .daily-cover:not(.open):not(.mini)) .daily-cover img{
    width:112px;}
}"""
if c.count(OLD)!=1: sys.exit("FAIL anchor count=%d"%c.count(OLD))
if "R24（用户实测「封面图没有显示全」）" in c: sys.exit("FAIL 已打过")
c=c.replace(OLD,NEW,1)
with io.open(CSS,"w",encoding="utf-8") as f: f.write(c)
print("R24 cover OK")
