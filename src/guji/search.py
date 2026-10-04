"""Retrieval over the 古籍 index, addressable by 卦/爻 and filterable by layer.

The reason this is not a thin wrapper over FTS5: char-segmenting a CJK query turns it
into multiple tokens, and bare multi-token FTS5 MATCH is an implicit AND anywhere in the
document. Searching 見群龍无首 would then match any unit containing those five characters
in any order or position. Quoting the segmented string forces a phrase match, which is
what a 古籍 lookup means. A hit-count test cannot catch this — it must be checked against
the returned text.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass

from .variants import fold, segment_cjk


# R230a-30（R14-P1-1）+ R230c（R17-P1-3 下沉共享）：简体查询词的保守简→繁
# 重试表。只收单义字（一对一映射，古籍语境不会错）；云/后/余/只/干/几/征/
# 系/台/面/松/咸/曲/谷/卜/丑/于/舍/历/困/蒙/涂/辟/向/须/御/折/钟/朱/致/
# 脏/伙/签 等一对多或简繁同字易错者一律不收——宁可不命中也不给错方向。
# 只对查询词生效，语料侧 fold 不变。web services 与 mcp_server 共用此表。
S2T_RETRY = {p[0]: p[1] for p in (  # noqa: E501 — 数据表，逐对显式
    "潜潛 龙龍 马馬 门門 问問 闻聞 见見 无無 为為 与與 车車 长長 风風 飞飛 鸟鳥 "
    "鱼魚 龟龜 万萬 书書 乐樂 礼禮 学學 师師 处處 变變 数數 断斷 时時 东東 "
    "国國 离離 兑兌 阴陰 阳陽 传傳 说說 记記 经經 义義 圣聖 贞貞 来來 跃躍 "
    "渊淵 饮飲 军軍 众眾 妇婦 户戶 庙廟 泽澤 电電 岁歲 昼晝 进進 动動 穷窮 "
    "达達 败敗 兴興 乱亂 顺順 应應 当當 据據 敌敵 刚剛 险險 丽麗 战戰 劳勞 "
    "润潤 热熱 视視 听聽 觉覺 声聲 语語 辞辭 艺藝 医醫 亿億 忆憶 营營 蝇蠅 "
    "踊踴 忧憂 优優 邮郵 誉譽 园園 员員 圆圓 远遠 愿願 运運 酝醞 杂雜 赃贓 "
    "凿鑿 枣棗 灶竈 斋齋 毡氈 赵趙 证證 郑鄭 织織 职職 纸紙 挚摯 掷擲 滞滯 "
    "种種 烛燭 庄莊 桩樁 妆妝 壮壯 状狀 浊濁 资資 总總 纵縱 丰豐 "
    "涣渙 节節 济濟 谦謙 随隨 蛊蠱 临臨 观觀 贲賁 剥剝 颐頤 习習 恒恆 晋晉 "
    "损損 渐漸 归歸 术術 药藥 权權 杀殺 满滿 岗崗 体體 肤膚 灵靈 厉厲 厌厭 "
    "县縣 备備 伞傘 举舉 乌烏 买買 卖賣 亲親 亵褻 仅僅 从從 仑侖 仓倉 仪儀 "
    "们們 价價 会會 伟偉 伤傷 伦倫 伪偽 伫佇 剑劍 剂劑 剧劇 劝勸 办辦 务務 "
    "励勵 劲勁 势勢 勋勳 区區 协協 却卻 参參 双雙 叙敘 号號 叹嘆 吃喫 "
    "启啟 吴吳 唤喚 嘱囑 团團 围圍 图圖 场場 坏壞 块塊 坚堅 坛壇 坝壩 坟墳 "
    "坠墜 垒壘 垦墾 垫墊 堑塹 堕墮 墙牆 壳殼 壶壺 头頭 夹夾 夺奪 奋奮 奖獎 "
    "奥奧 妈媽 妩嫵 妪嫗 姗姍 娄婁 娅婭 娆嬈 娇嬌 娈孌 娱娛 娲媧 娴嫻 婴嬰 "
    "婵嬋 婶嬸 媪媼 嫒嬡 嫔嬪 嫘嫘 嫠嫠 嫣嫣 嫦嫦 嫩嫩 嬉嬉 嬷嬤 孀孀 孪孿 "
    "宁寧 宝寶 实實 宠寵 审審 宪憲 宫宮 宽寬 宾賓 寝寢 对對 导導 将將 尔爾 "
    "尘塵 尝嘗 尧堯 尴尷 层層 屉屜 届屆 属屬 屡屢 屿嶼 岂豈 岖嶇 岘峴 岚嵐 "
    "岛島 岭嶺 峡峽 峣嶢 峤嶠 峥崢 峦巒 崭嶄 嵘嶸 嶔嶔 巅巔 巋巋 巍巍 "
    # R3305（审-P1-1）：名句原文在库却报「命中 1/0 条」——伪完整度。补一批
    # 古籍语境单义映射（每字仍只收一对一者；云/后/余/几/干等一对多不收）。
    "载載 积積 遥遙 刍芻 鲲鯤 纪紀 鸡雞 机機 华華 边邊 过過 这這 还還 "
    "谁誰 难難 虽雖 间間 关關 点點 灭滅 灯燈 旧舊 树樹 泪淚 红紅 绿綠 "
    "丝絲 细細 终終 绝絕 线線 结結 绕繞 给給 统統 继繼 缘緣 绳繩 网網 "
    "罗羅 罚罰 罢罷 鸣鳴 鸦鴉 鸭鴨 鹅鵝 鹏鵬 鹊鵲 鹤鶴 鹰鷹 麦麥 黄黃 "
    "齐齊 齿齒 龄齡 认認 让讓 讨討 训訓 议議 讯訊 讲講 讳諱 讶訝 许許 "
    "论論 讼訟 讽諷 设設 访訪 诀訣 评評 识識 诉訴 诊診 词詞 译譯 试試 "
    "诗詩 诚誠 话話 诞誕 询詢 该該 详詳 误誤 诱誘 诲誨 请請 诸諸 读讀 "
    "课課 调調 谅諒 谈談 谊誼 谋謀 谍諜 谎謊 谐諧 谕諭 谓謂 谚諺 谜謎 "
    "谢謝 谣謠 谨謹 谬謬 俭儉 侠俠 侣侶 侥僥 侦偵 侧側 "
    "侨僑 侩儈 侪儕 侬儂 俣俁 俦儔 俨儼 俩倆 俪儷 债債 倾傾 偬傯 偻僂 "
    "偾僨 偿償 傥儻 傧儐 储儲 傩儺 呛嗆 呜嗚 咏詠 咙嚨 咛嚀 咝噝 "
    "响響 哑啞 哒噠 哓嘵 哔嗶 哕噦 哗嘩 哙噲 哜嚌 哝噥 哟喲 唛嘜 唝嗊 "
    "唠嘮 唡啢 唢嗩 啧嘖 啬嗇 啭囀 啮齧 啴囅 啸嘯 喷噴 喽嘍 喾嚳 "
    "嗫囁 嗳噯 嘘噓 嘤嚶 嘱囑 噜嚕 嚣囂 严嚴 囵圇 囹圉 "
    # R3347（审-P1-2）：zhconv 全量补位——原表缺 ~2000 个常用
    # 简化字（气/极/陈/弃/汉/铁/盐/类/独/个/杨/汤…一字未映射整句
    # 静默漏命中）。已剔：① AMBIG 集（一对多/简繁同字刻意不收）；
    # ② 古籍双义字 15 个（占里游夸仆帘尸凶划托斗采昵筑腊厘——
    # 简体字形在繁体语料中也合法，误转方向）。
    "专專 业業 丛叢 丢丟 两兩 个個 乔喬 乡鄉 争爭 亏虧 亘亙 亚亞 产產 亩畝 亸嚲 伛傴 伡俥 伣俔 伥倀 伧傖 佣傭 佥僉 侭儘 俫倈 "
    "傤儎 儿兒 兖兗 党黨 兰蘭 兹茲 养養 兽獸 冁囅 内內 冈岡 册冊 写寫 农農 冯馮 决決 况況 冻凍 净淨 凄悽 凉涼 减減 凑湊 凛凜 "
    "凤鳳 凫鳧 凭憑 凯凱 击擊 刘劉 则則 创創 删刪 别別 刬剗 刭剄 刹剎 刽劊 刾㓨 刿劌 剀剴 剐剮 劢勱 勚勩 匀勻 匦匭 匮匱 单單 "
    "卢盧 卤滷 卧臥 卫衛 卺巹 厂廠 厅廳 压壓 厍厙 厐龎 厕廁 厢廂 厣厴 厦廈 厨廚 厩廄 厮廝 叁叄 叆靉 叇靆 叠疊 叶葉 叽嘰 吁籲 "
    "吓嚇 吕呂 吗嗎 吣唚 吨噸 呐吶 呒嘸 呓囈 呕嘔 呖嚦 呗唄 呙咼 咤吒 咨諮 唇脣 啯嘓 啰囉 喂餵 囱囪 圹壙 坜壢 坞塢 垄壟 垅壠 "
    "垆壚 垩堊 垭埡 垯墶 垱壋 垲塏 垴堖 埘塒 埙壎 埚堝 塆壪 壸壼 够夠 奁奩 奂奐 妫嬀 姹奼 婳嫿 媭嬃 嫱嬙 孙孫 寻尋 寿壽 尽盡 "
    "屃屓 屦屨 岩巖 岽崬 岿巋 峃嶨 峄嶧 峰峯 崂嶗 崃崍 崄嶮 嵚嶔 嵝嶁 巩鞏 巯巰 币幣 帅帥 帏幃 帐帳 帜幟 带帶 帧幀 帮幫 帱幬 "
    "帻幘 帼幗 幂冪 并並 广廣 庆慶 床牀 庐廬 庑廡 库庫 庞龐 废廢 庼廎 廪廩 开開 异異 弃棄 弑弒 张張 弥彌 弪弳 弯彎 弹彈 强強 "
    "录錄 彟彠 彦彥 彨彲 彻徹 径徑 徕徠 忏懺 忾愾 怀懷 态態 怂慫 怃憮 怄慪 怅悵 怆愴 怜憐 怼懟 怿懌 恋戀 恳懇 恶惡 恸慟 恹懨 "
    "恺愷 恻惻 恼惱 恽惲 悦悅 悫愨 悬懸 悭慳 悮悞 悯憫 惊驚 惧懼 惨慘 惩懲 惫憊 惬愜 惭慚 惮憚 惯慣 愠慍 愤憤 愦憒 慑懾 慭憖 "
    "懑懣 懒懶 懔懍 戆戇 戋戔 戏戲 戗戧 戬戩 戯戱 扑撲 执執 扩擴 扪捫 扫掃 扬揚 扰擾 抚撫 抛拋 抟摶 抠摳 抡掄 抢搶 护護 报報 "
    "担擔 拟擬 拢攏 拣揀 拥擁 拦攔 拧擰 拨撥 择擇 挂掛 挛攣 挜掗 挝撾 挞撻 挟挾 挠撓 挡擋 挢撟 挣掙 挤擠 挥揮 挦撏 捝挩 捞撈 "
    "捡撿 换換 捣搗 掳擄 掴摑 掸撣 掺摻 掼摜 揽攬 揾搵 揿撳 搀攙 搁擱 搂摟 搄揯 搅攪 携攜 摄攝 摅攄 摆擺 摇搖 摈擯 摊攤 撄攖 "
    "撑撐 撵攆 撷擷 撸擼 撺攛 擜㩵 擞擻 攒攢 敚敓 敛斂 敩斆 斓斕 斩斬 旷曠 旸暘 昙曇 昽曨 显顯 晒曬 晓曉 晔曄 晕暈 晖暉 暂暫 "
    "暅𣈶 暧曖 朴樸 杠槓 条條 杨楊 杩榪 杰傑 极極 构構 枞樅 枢樞 枥櫪 枧梘 枨棖 枪槍 枫楓 枭梟 柜櫃 柠檸 柽檉 栀梔 栅柵 标標 "
    "栈棧 栉櫛 栊櫳 栋棟 栌櫨 栎櫟 栏欄 栖棲 栗慄 样樣 栾欒 桠椏 桡橈 桢楨 档檔 桤榿 桥橋 桦樺 桧檜 桨槳 桪樳 梦夢 梼檮 梾棶 "
    "梿槤 检檢 棁梲 棂欞 椁槨 椝槼 椟櫝 椠槧 椢槶 椤欏 椫樿 椭橢 椮槮 楼樓 榄欖 榅榲 榇櫬 榈櫚 榉櫸 榝樧 槚檟 槛檻 槟檳 槠櫧 "
    "横橫 樯檣 樱櫻 橥櫫 橱櫥 橹櫓 橼櫞 檩檁 欢歡 欤歟 欧歐 歼殲 殁歿 殇殤 残殘 殒殞 殓殮 殚殫 殡殯 殴毆 毁毀 毂轂 毕畢 毙斃 "
    "毵毿 毶𣯶 氇氌 气氣 氢氫 氩氬 氲氳 汇匯 汉漢 汤湯 汹洶 沟溝 没沒 沣灃 沤漚 沥瀝 沦淪 沧滄 沨渢 沩潙 沪滬 泞濘 泶澩 泷瀧 "
    "泸瀘 泺濼 泻瀉 泼潑 泾涇 洁潔 洒灑 洼窪 浃浹 浅淺 浆漿 浇澆 浈湞 浉溮 测測 浍澮 浏瀏 浐滻 浑渾 浒滸 浓濃 浔潯 浕濜 涌湧 "
    "涚涗 涛濤 涝澇 涞淶 涟漣 涠潿 涡渦 涢溳 涤滌 涧澗 涨漲 涩澀 淀澱 渌淥 渍漬 渎瀆 渑澠 渔漁 渖瀋 渗滲 温溫 湾灣 湿溼 溁濚 "
    "溃潰 溅濺 溆漵 溇漊 滗潷 滚滾 滟灩 滠灄 滢瀅 滤濾 滥濫 滦灤 滨濱 滩灘 滪澦 漤灠 潆瀠 潇瀟 潋瀲 潍濰 潴瀦 澛瀂 澜瀾 濑瀨 "
    "濒瀕 灏灝 灾災 灿燦 炀煬 炉爐 炖燉 炜煒 炝熗 炼煉 炽熾 烁爍 烂爛 烃烴 烟煙 烦煩 烧燒 烨燁 烩燴 烫燙 烬燼 焕煥 焖燜 焘燾 "
    "煴熅 熏燻 爱愛 爷爺 牍牘 牦犛 牵牽 牺犧 犊犢 犷獷 犸獁 犹猶 狈狽 狝獮 狞獰 独獨 狭狹 狮獅 狯獪 狰猙 狱獄 狲猻 猃獫 猎獵 "
    "猕獼 猡玀 猪豬 猫貓 猬蝟 献獻 獭獺 玑璣 玙璵 玚瑒 玛瑪 玮瑋 环環 现現 玱瑲 玺璽 珐琺 珑瓏 珰璫 珲琿 琎璡 琏璉 琐瑣 琼瓊 "
    "瑶瑤 瑷璦 瑸璸 璎瓔 瓒瓚 瓮甕 瓯甌 画畫 畅暢 畴疇 疖癤 疗療 疟瘧 疠癘 疡瘍 疬癧 疭瘲 疮瘡 疯瘋 疱皰 疴痾 痈癰 痉痙 痒癢 "
    "痖瘂 痨癆 痪瘓 痫癇 痳痲 痴癡 瘅癉 瘆瘮 瘗瘞 瘘瘻 瘪癟 瘫癱 瘾癮 瘿癭 癞癩 癣癬 癫癲 皂皁 皑皚 皱皺 皲皸 盏盞 盐鹽 监監 "
    "盗盜 盘盤 眍瞘 眦眥 眬矓 睁睜 睐睞 睑瞼 瞆瞶 瞒瞞 瞩矚 矫矯 矶磯 矾礬 矿礦 砀碭 码碼 砖磚 砗硨 砚硯 砜碸 砺礪 砻礱 砾礫 "
    "础礎 硁硜 硕碩 硖硤 硗磽 硙磑 硚礄 确確 硵磠 硷礆 碍礙 碛磧 碜磣 碱鹼 祃禡 祎禕 祢禰 祯禎 祷禱 祸禍 禀稟 禄祿 禅禪 秃禿 "
    "秆稈 秘祕 称稱 秽穢 秾穠 稆穭 税稅 稣穌 稳穩 穑穡 穞穭 窃竊 窍竅 窎窵 窑窯 窜竄 窝窩 窥窺 窦竇 窭窶 竖豎 竞競 笃篤 笋筍 "
    "笔筆 笕筧 笺箋 笼籠 笾籩 筚篳 筛篩 筜簹 筝箏 筹籌 筼篔 筿篠 简簡 箓籙 箦簀 箧篋 箨籜 箩籮 箪簞 箫簫 篑簣 篓簍 篮籃 篯籛 "
    "篱籬 簖籪 籁籟 籴糴 类類 籼秈 粜糶 粝糲 粤粵 粪糞 粮糧 粽糉 糁糝 糇餱 糍餈 紧緊 絷縶 緼縕 縆緪 纟糹 纠糾 纡紆 纣紂 纤纖 "
    "纥紇 约約 级級 纨紈 纩纊 纫紉 纬緯 纭紜 纮紘 纯純 纰紕 纱紗 纲綱 纳納 纴紝 纶綸 纷紛 纹紋 纺紡 纻紵 纼紖 纽紐 纾紓 绀紺 "
    "绁紲 绂紱 练練 组組 绅紳 绉縐 绊絆 绋紼 绌絀 绍紹 绎繹 绐紿 绑綁 绒絨 绔絝 绖絰 绗絎 绘繪 绚絢 绛絳 络絡 绞絞 绠綆 绡綃 "
    "绢絹 绣繡 绤綌 绥綏 绦絛 绨綈 绩績 绪緒 绫綾 绬緓 续續 绮綺 绯緋 绰綽 绱鞝 绲緄 维維 绵綿 绶綬 绷繃 绸綢 绹綯 绺綹 绻綣 "
    "综綜 绽綻 绾綰 缀綴 缁緇 缂緙 缃緗 缄緘 缅緬 缆纜 缇緹 缈緲 缉緝 缊縕 缋繢 缌緦 缍綞 缎緞 缏緶 缐線 缑緱 缒縋 缓緩 缔締 "
    "缕縷 编編 缗緡 缙縉 缚縛 缛縟 缜縝 缝縫 缞縗 缟縞 缠纏 缡縭 缢縊 缣縑 缤繽 缥縹 缦縵 缧縲 缨纓 缩縮 缪繆 缫繅 缬纈 缭繚 "
    "缮繕 缯繒 缰繮 缱繾 缲繰 缳繯 缴繳 缵纘 罂罌 罴羆 羁羈 羟羥 羡羨 群羣 翘翹 翙翽 翚翬 耢耮 耧耬 耸聳 耻恥 聂聶 聋聾 聍聹 "
    "联聯 聩聵 聪聰 肃肅 肠腸 肮骯 肴餚 肾腎 肿腫 胀脹 胁脅 胆膽 胜勝 胧朧 胨腖 胪臚 胫脛 胶膠 脉脈 脍膾 脐臍 脑腦 脓膿 脔臠 "
    "脚腳 脱脫 脶腡 脸臉 腌醃 腘膕 腭齶 腻膩 腼靦 腽膃 腾騰 膑臏 膻羶 臜臢 舆輿 舣艤 舰艦 舱艙 舻艫 艰艱 艳豔 芈羋 芗薌 芜蕪 "
    "芦蘆 苁蓯 苇葦 苈藶 苋莧 苌萇 苍蒼 苎薴 苧薴 茎莖 茏蘢 茑蔦 茔塋 茕煢 茧繭 荆荊 荐薦 荙薘 荚莢 荛蕘 荜蓽 荝萴 荞蕎 荟薈 "
    "荠薺 荡蕩 荣榮 荤葷 荥滎 荦犖 荧熒 荨蕁 荩藎 荪蓀 荫蔭 荬蕒 荭葒 荮葤 莅蒞 莱萊 莲蓮 莳蒔 莴萵 莶薟 莸蕕 莹瑩 莺鶯 莼蓴 "
    "萚蘀 萝蘿 萤螢 萦縈 萧蕭 萨薩 葱蔥 蒀蒕 蒇蕆 蒉蕢 蒋蔣 蒌蔞 蒏醟 蓝藍 蓟薊 蓠蘺 蓣蕷 蓥鎣 蓦驀 蔂虆 蔷薔 蔹蘞 蔺藺 蔼藹 "
    "蕰薀 蕲蘄 蕴蘊 薮藪 藓蘚 藴蘊 蘖櫱 虏虜 虑慮 虚虛 虬虯 虮蟣 虱蝨 虾蝦 虿蠆 蚀蝕 蚁蟻 蚂螞 蚃蠁 蚕蠶 蚝蠔 蚬蜆 蛎蠣 蛏蟶 "
    "蛮蠻 蛰蟄 蛱蛺 蛲蟯 蛳螄 蛴蠐 蜕蛻 蜗蝸 蝈蟈 蝉蟬 蝎蠍 蝼螻 蝾蠑 螀螿 螨蟎 蟏蠨 衅釁 衔銜 补補 衬襯 衮袞 袄襖 袅嫋 袆褘 "
    "袜襪 袭襲 袯襏 装裝 裆襠 裈褌 裢褳 裣襝 裤褲 裥襉 褛褸 褴襤 襕襴 觃覎 规規 觅覓 觇覘 览覽 觊覬 觋覡 觌覿 觍覥 觎覦 觏覯 "
    "觐覲 觑覷 觞觴 触觸 觯觶 訚誾 詟讋 誊謄 讠訁 计計 订訂 讣訃 讥譏 讦訐 讧訌 讪訕 讫訖 讬託 讱訒 讴謳 讵詎 讷訥 讹訛 讻訩 "
    "诂詁 诃訶 诅詛 诇詗 诈詐 诋詆 诌謅 诎詘 诏詔 诐詖 诒詒 诓誆 诔誄 诖詿 诘詰 诙詼 诛誅 诜詵 诟詬 诠詮 诡詭 诣詣 诤諍 诧詫 "
    "诨諢 诩詡 诪譸 诫誡 诬誣 诮誚 诰誥 诳誑 诵誦 诶誒 诹諏 诺諾 诼諑 诽誹 诿諉 谀諛 谂諗 谄諂 谆諄 谇誶 谉讅 谌諶 谏諫 谑謔 "
    "谒謁 谔諤 谖諼 谗讒 谘諮 谙諳 谛諦 谝諞 谞諝 谟謨 谠讜 谡謖 谤謗 谥諡 谧謐 谩謾 谪謫 谫譾 谭譚 谮譖 谯譙 谰讕 谱譜 谲譎 "
    "谳讞 谴譴 谵譫 谶讖 豮豶 贝貝 负負 贠貟 贡貢 财財 责責 贤賢 账賬 货貨 质質 贩販 贪貪 贫貧 贬貶 购購 贮貯 贯貫 贰貳 贱賤 "
    "贳貰 贴貼 贵貴 贶貺 贷貸 贸貿 费費 贺賀 贻貽 贼賊 贽贄 贾賈 贿賄 赀貲 赁賃 赂賂 赅賅 赆贐 赇賕 赈賑 赉賚 赊賒 赋賦 赌賭 "
    "赍齎 赎贖 赏賞 赐賜 赑贔 赒賙 赓賡 赔賠 赕賧 赖賴 赗賵 赘贅 赙賻 赚賺 赛賽 赜賾 赝贗 赞贊 赟贇 赠贈 赡贍 赢贏 赣贛 赪赬 "
    "赶趕 趋趨 趱趲 趸躉 跄蹌 跖蹠 跞躒 践踐 跶躂 跷蹺 跸蹕 跹躚 跻躋 踌躊 踪蹤 踬躓 踯躑 蹑躡 蹒蹣 蹰躕 蹿躥 躏躪 躜躦 躯軀 "
    "輼轀 轧軋 轨軌 轩軒 轪軑 轫軔 转轉 轭軛 轮輪 软軟 轰轟 轱軲 轲軻 轳轤 轴軸 轵軹 轶軼 轷軤 轸軫 轹轢 轺軺 轻輕 轼軾 轾輊 "
    "轿轎 辀輈 辁輇 辂輅 较較 辄輒 辅輔 辆輛 辇輦 辈輩 辉輝 辊輥 辋輞 辌輬 辍輟 辎輜 辏輳 辐輻 辑輯 辒轀 输輸 辔轡 辕轅 辖轄 "
    "辗輾 辘轆 辙轍 辚轔 辩辯 辫辮 辽遼 迁遷 迈邁 违違 连連 迟遲 迩邇 迳逕 迹跡 适適 选選 逊遜 递遞 逦邐 逻邏 遗遺 邓鄧 邝鄺 "
    "邬鄔 邹鄒 邺鄴 邻鄰 郁鬱 郏郟 郐鄶 郓鄆 郦酈 郧鄖 郸鄲 酂酇 酦醱 酱醬 酽釅 酾釃 酿釀 醖醞 释釋 鉴鑑 銮鑾 錾鏨 钅釒 钆釓 "
    "钇釔 针針 钉釘 钊釗 钋釙 钌釕 钍釷 钎釺 钏釧 钐釤 钑鈒 钒釩 钓釣 钔鍆 钕釹 钖鍚 钗釵 钘鈃 钙鈣 钚鈈 钛鈦 钜鉅 钝鈍 钞鈔 "
    "钠鈉 钡鋇 钢鋼 钣鈑 钤鈐 钥鑰 钦欽 钧鈞 钨鎢 钩鉤 钪鈧 钫鈁 钬鈥 钭鈄 钮鈕 钯鈀 钰鈺 钱錢 钲鉦 钳鉗 钴鈷 钵鉢 钶鈳 钷鉕 "
    "钸鈽 钹鈸 钺鉞 钻鑽 钼鉬 钽鉭 钾鉀 钿鈿 铀鈾 铁鐵 铂鉑 铃鈴 铄鑠 铅鉛 铆鉚 铇鉋 铈鈰 铉鉉 铊鉈 铋鉍 铌鈮 铍鈹 铎鐸 铏鉶 "
    "铐銬 铑銠 铒鉺 铓鋩 铔錏 铕銪 铖鋮 铗鋏 铘鋣 铙鐃 铚銍 铛鐺 铜銅 铝鋁 铞銱 铟銦 铠鎧 铡鍘 铢銖 铣銑 铤鋌 铥銩 铦銛 铧鏵 "
    "铨銓 铩鎩 铪鉿 铫銚 铬鉻 铭銘 铮錚 铯銫 铰鉸 铱銥 铲鏟 铳銃 铴鐋 铵銨 银銀 铷銣 铸鑄 铹鐒 铺鋪 铻鋙 铼錸 铽鋱 链鏈 铿鏗 "
    "销銷 锁鎖 锂鋰 锃鋥 锄鋤 锅鍋 锆鋯 锇鋨 锈鏽 锉銼 锊鋝 锋鋒 锌鋅 锍鋶 锎鐦 锏鐧 锐銳 锑銻 锒鋃 锓鋟 锔鋦 锕錒 锖錆 锗鍺 "
    "锘鍩 错錯 锚錨 锛錛 锜錡 锝鍀 锞錁 锟錕 锠錩 锡錫 锢錮 锣鑼 锤錘 锥錐 锦錦 锧鑕 锨鍁 锩錈 锪鍃 锫錇 锬錟 锭錠 键鍵 锯鋸 "
    "锰錳 锱錙 锲鍥 锳鍈 锴鍇 锵鏘 锶鍶 锷鍔 锸鍤 锹鍬 锺鍾 锻鍛 锼鎪 锽鍠 锾鍰 锿鎄 镀鍍 镁鎂 镂鏤 镃鎡 镄鐨 镅鎇 镆鏌 镇鎮 "
    "镈鎛 镉鎘 镊鑷 镋钂 镌鐫 镍鎳 镎鎿 镏鎦 镐鎬 镑鎊 镒鎰 镓鎵 镔鑌 镕鎔 镖鏢 镗鏜 镘鏝 镙鏍 镚鏰 镛鏞 镜鏡 镝鏑 镞鏃 镟鏇 "
    "镠鏐 镡鐔 镢钁 镣鐐 镤鏷 镥鑥 镦鐓 镧鑭 镨鐠 镩鑹 镪鏹 镫鐙 镬鑊 镭鐳 镮鐶 镯鐲 镰鐮 镱鐿 镲鑔 镳鑣 镴鑞 镵鑱 镶鑲 闩閂 "
    "闪閃 闫閆 闬閈 闭閉 闯闖 闰閏 闱闈 闲閒 闳閎 闵閔 闶閌 闷悶 闸閘 闹鬧 闺閨 闼闥 闽閩 闾閭 闿闓 阀閥 阁閣 阂閡 阃閫 阄鬮 "
    "阅閱 阆閬 阇闍 阈閾 阉閹 阊閶 阋鬩 阌閿 阍閽 阎閻 阏閼 阐闡 阑闌 阒闃 阓闠 阔闊 阕闋 阖闔 阗闐 阘闒 阙闕 阚闞 阛闤 队隊 "
    "阵陣 阶階 际際 陆陸 陇隴 陈陳 陉陘 陕陝 陦隯 陧隉 陨隕 隐隱 隶隸 隽雋 雇僱 雏雛 雠讎 雳靂 雾霧 霁霽 霉黴 霡霢 霭靄 靓靚 "
    "靔靝 静靜 靥靨 鞑韃 鞒鞽 鞯韉 鞲韝 韦韋 韧韌 韨韍 韩韓 韪韙 韫韞 韬韜 韵韻 页頁 顶頂 顷頃 顸頇 项項 顼頊 顽頑 顾顧 顿頓 "
    "颀頎 颁頒 颂頌 颃頏 预預 颅顱 领領 颇頗 颈頸 颉頡 颊頰 颋頲 颌頜 颍潁 颎熲 颏頦 频頻 颒頮 颓頹 颔頷 颕頴 颖穎 颗顆 题題 "
    "颙顒 颚顎 颛顓 颜顏 额額 颞顳 颟顢 颠顛 颡顙 颢顥 颣纇 颤顫 颥顬 颦顰 颧顴 飏颺 飐颭 飑颮 飒颯 飓颶 飔颸 飕颼 飖颻 飗飀 "
    "飘飄 飙飆 飚飈 飨饗 餍饜 饣飠 饤飣 饥飢 饦飥 饧餳 饨飩 饩餼 饪飪 饫飫 饬飭 饭飯 饯餞 饰飾 饱飽 饲飼 饳飿 饴飴 饵餌 饶饒 "
    "饷餉 饸餄 饹餎 饺餃 饻餏 饼餅 饽餑 饾餖 饿餓 馀餘 馁餒 馂餕 馃餜 馄餛 馅餡 馆館 馇餷 馈饋 馉餶 馊餿 馋饞 馌饁 馍饃 馎餺 "
    "馏餾 馐饈 馑饉 馒饅 馓饊 馔饌 馕饢 驭馭 驮馱 驯馴 驰馳 驱驅 驲馹 驳駁 驴驢 驵駔 驶駛 驷駟 驸駙 驹駒 驺騶 驻駐 驼駝 驽駑 "
    "驾駕 驿驛 骀駘 骁驍 骂罵 骃駰 骄驕 骅驊 骆駱 骇駭 骈駢 骉驫 骊驪 骋騁 验驗 骍騂 骎駸 骏駿 骐騏 骑騎 骒騍 骓騅 骔騌 骕驌 "
    "骖驂 骗騙 骘騭 骙騤 骚騷 骛騖 骜驁 骝騮 骞騫 骟騸 骠驃 骡騾 骢驄 骣驏 骤驟 骥驥 骦驦 骧驤 髅髏 髋髖 髌髕 鬓鬢 鬶鬹 魇魘 "
    "魉魎 鱽魛 鱾魢 鱿魷 鲀魨 鲁魯 鲂魴 鲃䰾 鲄魺 鲅鮁 鲆鮃 鲇鮎 鲈鱸 鲉鮋 鲊鮓 鲋鮒 鲌鮊 鲍鮑 鲎鱟 鲏鮍 鲐鮐 鲑鮭 鲒鮚 鲓鮳 "
    "鲔鮪 鲕鮞 鲖鮦 鲗鰂 鲘鮜 鲙鱠 鲚鱭 鲛鮫 鲜鮮 鲝鮺 鲞鯗 鲟鱘 鲠鯁 鲡鱺 鲢鰱 鲣鰹 鲤鯉 鲥鰣 鲦鰷 鲧鯀 鲨鯊 鲩鯇 鲪鮶 鲫鯽 "
    "鲬鯒 鲭鯖 鲮鯪 鲯鯕 鲰鯫 鲱鯡 鲳鯧 鲴鯝 鲵鯢 鲶鯰 鲷鯛 鲸鯨 鲹鰺 鲺鯴 鲻鯔 鲼鱝 鲽鰈 鲾鰏 鲿鱨 鳀鯷 鳁鰮 鳂鰃 鳃鰓 鳄鱷 "
    "鳅鰍 鳆鰒 鳇鰉 鳈鰁 鳉鱂 鳊鯿 鳋鰠 鳌鰲 鳍鰭 鳎鰨 鳏鰥 鳐鰩 鳑鰟 鳒鰜 鳓鰳 鳔鰾 鳕鱈 鳖鱉 鳗鰻 鳘鰵 鳙鱅 鳚䲁 鳛鰼 鳜鱖 "
    "鳝鱔 鳞鱗 鳟鱒 鳠鱯 鳡鱤 鳢鱧 鳣鱣 鳤䲘 鸠鳩 鸢鳶 鸤鳲 鸥鷗 鸧鶬 鸨鴇 鸩鴆 鸪鴣 鸫鶇 鸬鸕 鸮鴞 鸯鴦 鸰鴒 鸱鴟 鸲鴝 鸳鴛 "
    "鸴鷽 鸵鴕 鸶鷥 鸷鷙 鸸鴯 鸹鴰 鸺鵂 鸻鴴 鸼鵃 鸽鴿 鸾鸞 鸿鴻 鹀鵐 鹁鵓 鹂鸝 鹃鵑 鹄鵠 鹆鵒 鹇鷳 鹈鵜 鹉鵡 鹋鶓 鹌鵪 鹍鵾 "
    "鹎鵯 鹐鵮 鹑鶉 鹒鶊 鹓鵷 鹔鷫 鹕鶘 鹖鶡 鹗鶚 鹘鶻 鹙鶖 鹚鷀 鹛鶥 鹜鶩 鹝鷊 鹞鷂 鹟鶲 鹠鶹 鹡鶺 鹢鷁 鹣鶼 鹥鷖 鹦鸚 鹧鷓 "
    "鹨鷚 鹩鷯 鹪鷦 鹫鷲 鹬鷸 鹭鷺 鹮䴉 鹯鸇 鹱鸌 鹲鸏 鹳鸛 鹴鸘 鹾鹺 麸麩 麹麴 麺麪 麽麼 黉黌 黡黶 黩黷 黪黲 黾黽 鼋黿 鼌鼂 "
    "鼍鼉 鼗鞀 鼹鼴 齑齏 龀齔 龁齕 龂齗 龃齟 龅齙 龆齠 龇齜 龈齦 龉齬 龊齪 龋齲 龌齷 龚龔 龛龕").split()
    if len(p) == 2 and p[0] != p[1]}  # len 守卫：手滑拼出三字词即静默丢弃

# R3305（审-P1-1）：一对多/简繁同字——上表有意不收的字。query 含它们时
# 简体侧可能漏命中而 q2==q 不触发重试，服务层据此披露「换繁体再查」。
AMBIG_S2T_CHARS = frozenset(
    "云后余只干几征系台面松咸曲谷卜丑于舍历困蒙涂辟向须御折钟朱致脏伙签"
    "复范胡姜借冲亨克累获蔑藩苹盖苏虫蜡准丧发么岳"
    "仆仇凶划制升占卷厘夸奸家尸帘志托斗昵板游筑腊采里")


def s2t_retry(q: str) -> str:
    """按保守映射把简体查询词翻成繁体候选——无变化时返回原串（调用方据此
    决定是否重试与是否披露 hint）。"""
    return "".join(S2T_RETRY.get(ch, ch) for ch in q)


def fts_phrase(q: str) -> str:
    """Segmented, folded, and quoted so FTS5 treats it as an adjacent phrase."""
    import unicodedata
    # R3369（审-低-1）：兼容字符 NFKC 归一——U+F900 相容表意文字、
    # 全角形、旧字形先折成通行形再走 fold，「廉」不会再漏「廉」。
    seg = segment_cjk(fold(unicodedata.normalize("NFKC", q))).replace('"', '')
    # R228z续：C0 控制字符剥掉——\x00 会让 FTS5 报 "unterminated string"
    # （内部按 C 串截断），别的控制符也不构成任何检索意义。
    seg = "".join(ch for ch in seg if ord(ch) >= 0x20)
    return f'"{seg}"'


def render_citation(*, work_id: str, title: str | None = None,
                    attribution: str | None = None, edition: str | None = None,
                    page_anchor: str | None = None, file: str = "",
                    scheme: str | None = None, addr_name: str | None = None,
                    gua: int | None = None, yao: str | None = None,
                    skipped_chars: int = 0, suspect: str | None = None) -> str:
    """出处渲染的**唯一实现**（`Hit.citation()` 与 bazi_lookup 共用）。

    为什么抽成模块级函数（R179b，D-231b）：`/api/bazi` 的 evidence 走
    `bazi_lookup.retrieve_fast()`，它返回裸 dict 而非 `Hit`，于是响应里
    根本没有 `citation` 键，前端 `esc(ev.citation||'')` 把出处静默渲染成
    空串——原文有了、出处没了（审查轨 R118a-03 实测）。

    修法上**绝不能在 bazi_lookup 里再拼一遍同样的格式**：同一条渲染规则
    存在两份拷贝、对同样的字节给出不同结论，正是 LESSONS.md L-01 记录的
    真实事故（变体折叠表两份拷贝给出相反结论）。故把格式收成本函数，
    两个调用点都指向它。

    每个组成部分都能在源文件里核验，不做任何推断。披露标记（! 表示引文
    非连续、? 表示地址被质量闸门标记）是出处的一部分，不是可选附加——
    隐藏自己省略了什么的出处，是本项目视为最严重的失败模式。
    """
    who = f"{title or work_id}"
    if attribution:
        who += f"（{attribution}）"
    addr = ""
    if gua is not None or addr_name:
        if scheme == "zhouyi":
            nm = f"（{addr_name}）" if addr_name else ""
            addr = f" 卦{gua}{nm}"
            if yao:
                addr += f"·{yao}"
        else:
            # Generic rendering for any other scheme, e.g. "Genesis 1:1".
            parts = [p for p in (addr_name, str(gua) if gua else None) if p]
            addr = " " + " ".join(parts) + (f":{yao}" if yao else "")
    ed = f" [{edition}]" if edition else ""
    marks = ("!" if skipped_chars else "") + ("?" if suspect else "")
    tail = f" {marks}" if marks else ""
    return f"{who}{ed}{addr} @{page_anchor or '?'} ({file}){tail}"


@dataclass
class Hit:
    work_id: str
    title: str | None
    attribution: str | None
    edition: str | None
    page_anchor: str | None
    gua: int | None            # = addr1
    yao: str | None            # = addr2
    layer: str
    text: str
    file: str
    score: float
    scheme: str | None = None
    addr_name: str | None = None
    skipped_chars: int = 0
    suspect: str | None = None

    @property
    def contiguous(self) -> bool:
        """Is `text` a contiguous run of the source, or an envelope with material removed?"""
        return self.skipped_chars == 0

    def disclosure(self) -> str:
        """What the citation does not otherwise say. Empty when there is nothing to disclose.

        Two things a reader cannot see from the text alone, and both were measured rather
        than assumed (probes/probe_disclosure.py, data/catalog/quality_report.json):

          * 54.1% of units skip material inside their own cited range (median 62 chars,
            max 7,388) because same-address runs were merged across an interleaved layer.
            Quoting 經 while silently dropping the 注 between its halves is conventional
            practice, but leaving it undisclosed is not honest citation.
          * 20 units sit at an address the quality gate flagged as damaged. Returning
            KR1a0006 卦61 上九翰青登于天 with no warning presents OCR corruption as text.
        """
        bits = []
        if self.skipped_chars:
            bits.append(f"⚠ 非连续引文：区间内另有 {self.skipped_chars:,} 字未包含"
                        f"（{self.layer}层过滤）")
        if self.suspect:
            bits.append(f"⚠ 该地址已被质量闸门标记：{self.suspect}")
        return "  ".join(bits)

    def citation(self) -> str:
        """Every component is verifiable in the source file; nothing is inferred."""
        return render_citation(
            work_id=self.work_id, title=self.title, attribution=self.attribution,
            edition=self.edition, page_anchor=self.page_anchor, file=self.file,
            scheme=self.scheme, addr_name=self.addr_name, gua=self.gua,
            yao=self.yao, skipped_chars=self.skipped_chars, suspect=self.suspect)


_SELECT = """
SELECT u.work_id, w.title, w.attribution, w.edition, u.page_anchor,
       u.scheme, u.addr_name, u.addr1 AS gua, u.addr2 AS yao,
       u.layer, u.text, u.file, u.skipped_chars, u.suspect
FROM unit u JOIN work w ON w.id = u.work_id
"""

# R3246：layer 过滤把 planner 骗上 idx_unit_layer（經层≈半库）——地址查询
# 绑了 addr1/addr2 时 (scheme,addr1,addr2) 恒为最优，INDEXED BY 定死计划
# （layer=經 + 卦1：4.6ms→0.5ms）。仅 addr_name 的查询仍走 idx_unit_name
# 不加提示。索引名由 build_index 统一产出，改名会同时更新此处。
_SELECT_AIDX = _SELECT.replace(
    "FROM unit u JOIN", "FROM unit u INDEXED BY idx_unit_addr JOIN")


# R3238：coverage() 是 unit 全表聚合（~70ms/次），语料重建前结果不变——
# 按 (路径, mtime_ns, size) 键控缓存，重建/换库自动失效；Row 是快照与
# 连接无关，跨 Corpus 实例共享安全（与 knowledge._SCHEMA_OK 同模式）。
_COVERAGE_CACHE: dict[tuple[str, int, int], list] = {}

# R3241：addr2/addr_name 的存在性校验（typo 门）单列无覆盖索引——
# SELECT 1 ... WHERE col=? LIMIT 1 是整索引扫 5.6ms/次。值域集合按
# (路径, mtime_ns, size, 列) 键控缓存：存在性 == 集合成员判定，
# 一次性 DISTINCT 扫描摊销到进程生命周期。
_DISTINCT_CACHE: dict[tuple[str, int, int, str], set] = {}


class Corpus:
    def __init__(self, db_path: str):
        self._db_path = db_path
        # R230c（R17-P2-3/P2-6/P2-9）：sqlite3.connect 对缺失路径会顺手建
        # 0B 残库，让后续所有 `os.path.exists` 入口失效——先挡存在性/非空/
        # schema 再开，缺索引的入口得到的是一句人话不是 traceback。
        if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
            raise FileNotFoundError(
                f"索引缺失或为空：{db_path}（先跑 scripts/build_index.py）")
        self.db = sqlite3.connect(db_path)
        self.db.row_factory = sqlite3.Row
        try:
            has_work = self.db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='work'").fetchone()
            if not has_work:
                self.db.close()
                raise FileNotFoundError(
                    f"索引缺表（残库）：{db_path}（先跑 scripts/build_index.py）")
            if not self.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') "
                    "AND name='unit'").fetchone():
                self.db.close()
                raise FileNotFoundError(
                    f"索引缺表（残库）：{db_path}（先跑 scripts/build_index.py）")
            # R230i（R21-P2-3）：列级漂移（pre-D015 直列 gua/gua_name 等旧版
            # 索引）此前走 DatabaseError 泛文案「存储暂时不可用」——明示
            # 「索引版本过旧，请重建」更可操作。
            _need = {"work_id", "layer", "page_anchor", "file", "text",
                     "raw_start", "skipped_chars", "suspect", "scheme",
                     "addr_name", "addr1", "addr2"}
            # R2523（审-P3-10）：本 PRAGMA 原在 try 外——损坏库在这里抛
            # DatabaseError 时 self.db 泄漏（微观竞态，但收进同一闸语义更对）。
            have = {r[1] for r in self.db.execute("PRAGMA table_info(unit)")}
            missing = _need - have
            if missing:
                self.db.close()
                raise FileNotFoundError(
                    f"索引版本过旧（缺列：{'、'.join(sorted(missing))}）："
                    f"{db_path}（请跑 scripts/build_index.py 重建）")
        except sqlite3.DatabaseError:
            # R230i（R21-P1-6）：库文件损坏此前走 DatabaseError→503
            # 「稍后再试」——误导（永远不会自己好）。给可操作文案。
            self.db.close()
            raise FileNotFoundError(
                f"索引文件损坏：{db_path}（请跑 scripts/build_index.py 重建）"
            ) from None

    def close(self):
        self.db.close()

    def stats(self) -> dict:
        q = ("SELECT (SELECT count(*) FROM work) w, (SELECT count(*) FROM unit) u, "
             "(SELECT count(*) FROM unit WHERE addr1 IS NOT NULL) g, "
             "(SELECT count(*) FROM unit WHERE addr2 IS NOT NULL) y")
        r = self.db.execute(q).fetchone()
        return {"works": r["w"], "units": r["u"], "with_gua": r["g"], "with_yao": r["y"]}

    def coverage(self) -> list[sqlite3.Row]:
        try:
            _st = os.stat(self._db_path)
            _key = (os.path.abspath(self._db_path),
                    _st.st_mtime_ns, _st.st_size)
        except OSError:
            _key = None
        if _key is not None and _key in _COVERAGE_CACHE:
            return _COVERAGE_CACHE[_key]
        rows = self.db.execute("""
            SELECT w.id, w.title, w.genre, count(u.id) units,
                   sum(u.addr1 IS NOT NULL) addressed,
                   sum(u.addr2 IS NOT NULL) yao_addressed,
                   sum(u.page_anchor IS NOT NULL) anchored
            FROM work w LEFT JOIN unit u ON u.work_id = w.id
            GROUP BY w.id ORDER BY w.genre, w.id""").fetchall()
        if _key is not None:
            # 同路径只留最新键——重建一次换一条，不让旧 (mtime,size) 滞留
            _COVERAGE_CACHE[_key] = rows
            for _k in [k for k in _COVERAGE_CACHE
                       if k[0] == _key[0] and k != _key]:
                del _COVERAGE_CACHE[_k]
        return rows

    # has_value 的服务列白名单——f-string 进 SQL 只认这几个自有常量列名。
    _HAS_VALUE_COLS = frozenset({"layer", "scheme", "addr_name",
                                 "addr1", "addr2"})

    def has_value(self, col: str, value, scheme: str | None = None) -> bool:
        """列值存在性（typo 门）。== `SELECT 1 ... WHERE col=? LIMIT 1`
        的真值，无覆盖索引的列从全索引扫 5.6ms 降到缓存命中 ~µs。

        R3305（审-P2-1）：可传 scheme 做分桶存在性——全局 DISTINCT 会
        跨 scheme 污染（bcv 的节号让 zhouyi 的爻校验误放行）。scheme
        传 'none' 表示无编址作品（IS NULL），None = 全局不滤。
        """
        if col not in self._HAS_VALUE_COLS:
            raise ValueError(f"has_value 未授权列名: {col!r}")
        _sc = None if scheme in (None, "none") else scheme
        _sc_null = (scheme == "none")
        try:
            _st = os.stat(self._db_path)
            _key = (os.path.abspath(self._db_path),
                    _st.st_mtime_ns, _st.st_size, col + "|" + str(scheme))
        except OSError:
            _key = None
        if _key is None or _key not in _DISTINCT_CACHE:
            _sql = f"SELECT DISTINCT {col} FROM unit"
            _args: list = []
            if _sc_null:
                _sql += " WHERE scheme IS NULL"
            elif _sc is not None:
                _sql += " WHERE scheme = ?"
                _args.append(_sc)
            vals = {r[0] for r in self.db.execute(_sql, _args)
                    if r[0] is not None}
            if _key is not None:
                _DISTINCT_CACHE[_key] = vals
                for _k in [k for k in _DISTINCT_CACHE
                           if k[0] == _key[0] and k[3] == _key[3]
                           and k != _key]:
                    del _DISTINCT_CACHE[_k]
        return value in _DISTINCT_CACHE[_key]

    def _search_where(self, query: str, gua, yao, layer, work_id, genre,
                      scheme, addr_name, addr1, addr2
                      ) -> tuple[str, list]:
        sql = """
            FROM unit_fts
            JOIN unit u ON u.id = unit_fts.rowid
            JOIN work w ON w.id = u.work_id
            WHERE unit_fts MATCH ?"""
        args: list = [fts_phrase(query)]
        # 'none' 哨兵 = scheme IS NULL（页锚点作品）；None = 不过滤。
        scheme_eq = "none" if scheme is not None and str(scheme).lower() == "none" \
            else scheme
        for col, val in (("u.addr1", gua if gua is not None else addr1),
                         ("u.addr2", yao if yao is not None else addr2),
                         ("u.scheme", scheme_eq), ("u.addr_name", addr_name),
                         ("u.layer", layer),
                         ("u.work_id", work_id), ("w.genre", genre)):
            if val is not None:
                sql += (f" AND {col} IS NULL" if val == "none"
                        else f" AND {col} = ?")
                if val != "none":
                    args.append(val)
        return sql, args

    def search(self, query: str, limit: int = 10, gua: int | None = None,
               yao: str | None = None, layer: str | None = None,
               work_id: str | None = None, genre: str | None = None,
               scheme: str | None = None, addr_name: str | None = None,
               addr1: int | None = None, addr2: str | None = None) -> list[Hit]:
        """`gua`/`yao` are convenience aliases for `addr1`/`addr2` (D-016). They are kept
        because 卦/爻 is what a 周易 caller means, but they carry no special status in
        storage — a Bible caller passes addr_name/addr1/addr2 through the same path."""
        where, args = self._search_where(query, gua, yao, layer, work_id,
                                         genre, scheme, addr_name, addr1, addr2)
        sql = ("""
            SELECT u.work_id, w.title, w.attribution, w.edition, u.page_anchor,
                   u.scheme, u.addr_name, u.addr1 AS gua, u.addr2 AS yao,
                   u.layer, u.text, u.file, u.skipped_chars, u.suspect,
                   bm25(unit_fts) AS score """ + where + " ORDER BY score LIMIT ?")
        args.append(limit)
        return [self._hit(r) for r in self.db.execute(sql, args)]

    def search_count(self, query: str, gua=None, yao=None, layer=None,
                     work_id=None, genre=None, scheme=None, addr_name=None,
                     addr1=None, addr2=None) -> int:
        """命中总数（R230a-30：count 原是截断后条数，UI 无法说「共 Y 条」）。"""
        # R3240：无 unit/work 列过滤时 count 不需要 join——纯 FTS doclist
        # 计数实测 1.6ms vs 带 join 10ms（join 无损已证：fts→unit、unit→work
        # 双向零孤儿）。过滤都在 unit/work 列上，任一出现即回 join 路径。
        if all(v is None for v in (gua, yao, layer, work_id, genre,
                                   scheme, addr_name, addr1, addr2)):
            return self.db.execute(
                "SELECT count(*) FROM unit_fts WHERE unit_fts MATCH ?",
                [fts_phrase(query)]).fetchone()[0]
        where, args = self._search_where(query, gua, yao, layer, work_id,
                                         genre, scheme, addr_name, addr1, addr2)
        return self.db.execute("SELECT count(*) " + where, args).fetchone()[0]

    def at_address(self, gua: int, yao: str | None = None,
                   layer: str | None = None, limit: int = 50) -> list[Hit]:
        """Every edition's text at one canonical address — no query string involved.
        This is the operation that page anchors cannot do (D-005).

        Restricted to scheme='zhouyi': this method answers 「what does each
        witness read at 卦N·爻」, and 卦 addressing IS the zhouyi scheme. Without
        the filter, a Bible chapter number could collide with a 卦 number
        (Psalms 99 == 卦99), which would make the impossible-address gate
        (eval_g7 卦99) return Psalms text instead of refusing. The collision is
        real, not hypothetical: measured after Douay was ingested with
        scheme='bcv', addr1=chapter.
        """
        sql = _SELECT_AIDX + " WHERE u.addr1 = ? AND u.scheme = 'zhouyi'"
        args: list = [gua]
        if yao:
            sql += " AND u.addr2 = ?"
            args.append(yao)
        if layer:
            sql += " AND u.layer = ?"
            args.append(layer)
        sql += " ORDER BY u.work_id, u.raw_start LIMIT ?"
        args.append(limit)
        return [self._hit(r, score=0.0) for r in self.db.execute(sql, args)]

    def compare(self, gua: int, yao: str, per_work: int = 2) -> dict[str, list[Hit]]:
        """Group one address's text by work: the shape 'compare the commentators' needs."""
        out: dict[str, list[Hit]] = {}
        for h in self.at_address(gua, yao, limit=400):
            out.setdefault(h.work_id, [])
            if len(out[h.work_id]) < per_work:
                out[h.work_id].append(h)
        return out

    def at_scheme(self, scheme: str | None, addr_name: str | None = None,
                  addr1: int | None = None, addr2: str | None = None,
                  layer: str | None = None, limit: int = 50,
                  work_id: str | None = None) -> list[Hit]:
        """Generic address lookup for ANY scheme — 卦/爻 for zhouyi, 卷:章 for bcv,
        幕:場 for play, BOOK:proposition for euclid, etc. `at_address` stays the
        zhouyi-only convenience (D-005: Psalms 99 == 卦99 collision); this is the
        scheme-scoped form used by the web addr view, where the caller declares the
        scheme explicitly so no cross-scheme collision can occur.

        scheme=None / 'none' 表示无编址（页锚点）作品——R230a-33 前 SCHEME_LABELS
        靠字面键 'None' 防呆，传字符串 'None' 会变成查 scheme='None' 恒零命中。
        """
        # R3246：绑了 addr1/addr2 时用 _SELECT_AIDX 定死计划防 layer 骗到
        # idx_unit_layer；只按 addr_name 时 idx_unit_name 更优，不加提示。
        _sel = (_SELECT_AIDX if scheme is not None
                and str(scheme).lower() != "none"
                and (addr1 is not None or addr2 is not None)
                else _SELECT)
        if scheme is None or str(scheme).lower() == "none":
            sql = _sel + " WHERE u.scheme IS NULL"
            args: list = []
        else:
            sql = _sel + " WHERE u.scheme = ?"
            args = [scheme]
        for col, val in (("u.addr_name", addr_name), ("u.addr1", addr1),
                         ("u.addr2", addr2), ("u.layer", layer),
                         ("u.work_id", work_id)):
            if val is not None:
                sql += f" AND {col} = ?"
                args.append(val)
        sql += " ORDER BY u.work_id, u.raw_start LIMIT ?"
        args.append(limit)
        return [self._hit(r, score=0.0) for r in self.db.execute(sql, args)]

    def units_by_id(self, unit_ids: list[int], limit: int = 50) -> list[Hit]:
        """Fetch units by primary key. The link table speaks unit ids (G4), and this is
        the read-back for a hop: `link.dst_unit` -> the unit it points at."""
        if not unit_ids:
            return []
        ids = [int(i) for i in unit_ids[:limit]]
        ph = ",".join("?" * len(ids))
        sql = _SELECT + f" WHERE u.id IN ({ph}) ORDER BY u.work_id, u.raw_start"
        return [self._hit(r, score=0.0) for r in self.db.execute(sql, ids)]

    @staticmethod
    def _hit(r: sqlite3.Row, score: float | None = None) -> Hit:
        # Explicit field names: positional construction silently misassigns if the
        # SELECT column order is ever edited.
        return Hit(
            work_id=r["work_id"], title=r["title"], attribution=r["attribution"],
            edition=r["edition"], page_anchor=r["page_anchor"], gua=r["gua"],
            yao=r["yao"], layer=r["layer"], text=r["text"], file=r["file"],
            score=score if score is not None else r["score"],
            scheme=r["scheme"], addr_name=r["addr_name"],
            skipped_chars=r["skipped_chars"] or 0, suspect=r["suspect"],
        )
