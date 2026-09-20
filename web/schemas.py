"""web/schemas.py — 请求模型与校验（原 app.py 内联的 Pydantic 层）。

分层职责（宪法 III「分层架构不可越界」在 web 层的落地）：
    schemas.py    只做**输入形状与值域校验**，不碰业务、不碰 DB
    services.py   编排 src/guji 的业务模块，返回纯 dict
    routers/*.py  只做 HTTP 绑定：解析 → 调 service → 抛 HTTPException
    deps.py       路径常量与资源句柄（Corpus/KnowledgeBase 的生命周期）

校验纪律保持与重构前逐字一致（web selftest 的 err.* 断言逐条依赖这些
中文报错文本与状态码：非法输入 400、排盘计算失败 422）。
"""
from __future__ import annotations

from datetime import date

import re

from pydantic import BaseModel, Field, field_validator

YEAR_LO, YEAR_HI = 1900, 2100
SCOPES = ("day", "range", "life")
CALENDARS = ("solar", "lunar")
GENDERS = ("男", "女")

# R230k（R23-P3-4）：零宽格式符（ZWSP/ZWNJ/ZWJ/BOM）不在 str.strip()
# 的空白集合里——纯零宽串会过「非空」检查，落成空白气泡/空白排盘问句。
_ZW_RE = re.compile(r"[\u200b-\u200d\ufeff]")


def strip_zw(s: str | None) -> str | None:
    if s is None:
        return None
    s = _ZW_RE.sub("", s).strip()
    return s or None


class ValidationError(ValueError):
    """业务校验失败（路由层转 HTTP 400）。

    与 Pydantic 的 422 区分：Pydantic 管"形状不对"（缺字段/类型错），
    本异常管"值域不对"（年份越界、scope 非法……），照原契约转 400。
    """


class ComputeError(ValueError):
    """排盘/计算失败（路由层转 HTTP 422）——合法参数但组合非法，如 2 月 30 日。"""


class NotFoundError(LookupError):
    """资源不存在（路由层转 HTTP 404）——如历史记录 id、研究线程 tid 不存在。"""


def _check_ymdh(tag: str, year: int, month: int, day: int, hour: int) -> None:
    """合婚两侧共用的值域校验（报错文本与重构前逐字一致）。"""
    if not (YEAR_LO <= year <= YEAR_HI):
        raise ValidationError(f"{tag}年份需在 {YEAR_LO}-{YEAR_HI}，收到 {year}")
    if not (1 <= month <= 12):
        raise ValidationError(f"{tag}月份需在 1-12，收到 {month}")
    if not (1 <= day <= 31):
        raise ValidationError(f"{tag}日需在 1-31，收到 {day}")
    if not (0 <= hour <= 23):
        raise ValidationError(f"{tag}时辰需在 0-23，收到 {hour}")


class BaziRequest(BaseModel):
    year: int = Field(..., description="公历年份（calendar_type=solar 时直接使用）")
    month: int = Field(..., description="月 1-12")
    day: int = Field(..., description="日 1-31")
    hour: int = Field(..., description="时 0-23")
    # R230f（R18-P1-1）：节气当小时内出生，整数时辰会被截到节前一侧
    # （如立春 17:07 时 17:30 出生的盘年柱/月柱全错）。可选分钟字段——
    # 不给按 :00 算（与旧行为一致），给了走真实时刻。
    minute: int | None = Field(None, description="分 0-59，可选")
    # R230a-7（R13-P1-3）：时辰留空时前端补 12 并置 False——后端拿到
    # 标志给提示，不再静默按午时排。旧客户端不传此键 → 默认 True 兼容。
    hour_known: bool = True
    gender: str = "男"
    # R229c：自由文本上限 200（TarotRequest 同款）——否则超长串原样回显
    # 进 warm.reply 撑破横屏（R5 审计 P1，实测 scrollWidth 3105px）。
    question: str | None = Field(None, max_length=200)
    calendar_type: str = "solar"          # solar | lunar
    lunar_year: int | None = None
    lunar_month: int | None = None
    lunar_day: int | None = None
    lunar_leap: bool = False              # 是否闰月
    scope: str = "day"                    # day | range | life
    range_start: str | None = Field(None, description="范围起点 YYYY-MM-DD")
    range_end: str | None = Field(None, description="范围终点 YYYY-MM-DD")
    ask_date: str | None = Field(None, description="问事日期 YYYY-MM-DD，默认今天")
    ask_hour: int | None = Field(None, description="问事时辰 0-23，默认不比对流时")
    # R229n（R6-#8）：location 加界——此前无 max_length，任意长串会被
    # 原样 echo 进响应与 LLM facts 链（与 question 200 字同纪律）。
    location: str | None = Field(None, max_length=100,
                               description="问事地点（可选，仅提示用）")

    def validate_ranges(self) -> None:
        """值域校验：非法输入抛 ValidationError（路由层转 400 中文报错）。

        报错文本与校验顺序与重构前逐字一致——web selftest 的 err.bazi.*
        逐条断言这些消息与状态码，改动措辞即改动契约。
        """
        if self.calendar_type not in CALENDARS:
            raise ValidationError("历法只能是 solar 或 lunar")
        if self.scope not in SCOPES:
            raise ValidationError(f"范围只能是 {'/'.join(SCOPES)}")
        self.question = strip_zw(self.question)   # R230k
        if self.calendar_type == "lunar":
            if not (self.lunar_year and self.lunar_month and self.lunar_day):
                raise ValidationError("农历输入需提供农历年月日")
            if not (1 <= self.lunar_month <= 12):
                raise ValidationError("农历月需在 1-12")
            if not (1 <= self.lunar_day <= 30):
                raise ValidationError("农历日需在 1-30")
        else:
            if not (YEAR_LO <= self.year <= YEAR_HI):
                raise ValidationError(
                    f"年份需在 {YEAR_LO}-{YEAR_HI} 之间（节气表适用范围）")
            if not (1 <= self.month <= 12):
                raise ValidationError("月份需在 1-12")
            if not (1 <= self.day <= 31):
                raise ValidationError("日需在 1-31")
        if not (0 <= self.hour <= 23):
            raise ValidationError("时辰需在 0-23")
        # R230f：分钟可选但给了就必须合法
        if self.minute is not None and not (0 <= self.minute <= 59):
            raise ValidationError("分钟需在 0-59")
        if self.gender not in GENDERS:
            raise ValidationError("性别只能是 男 或 女")
        if self.ask_hour is not None and not (0 <= self.ask_hour <= 23):
            raise ValidationError("占卜时辰需在 0-23")
        if self.ask_date is not None:
            try:
                d = date.fromisoformat(self.ask_date)
            except ValueError:
                raise ValidationError("占卜日期需为 YYYY-MM-DD 格式") from None
            if not (YEAR_LO <= d.year <= YEAR_HI):
                raise ValidationError(
                    f"占卜年份需在 {YEAR_LO}-{YEAR_HI} 之间")
        if self.scope == "range":
            if not (self.range_start and self.range_end):
                raise ValidationError("范围=range 需提供区间起止（range_start 和 range_end）")
            try:
                date.fromisoformat(self.range_start)
                date.fromisoformat(self.range_end)
            except ValueError:
                raise ValidationError(
                    "range_start/range_end 需为 YYYY-MM-DD 格式") from None


class AskRequest(BaseModel):
    q: str = Field(..., min_length=1, max_length=200, description="研究问题/检索词")
    allow_damaged: bool = False
    max_addresses: int = Field(3, ge=1, le=6)


class ThreadEvidence(BaseModel):
    """R228i：work_id/file 无校验时，verify() 会 os.path.join(raw_dir, work_id)
    后 glob *.txt 读任意目录——绝对路径与 ../ 都能穿透（实测 oracle 成立）。
    work_id 只许语料目录名形态；file 只作展示用不碰盘，只限长度。"""
    work_id: str = Field("", max_length=64)
    file: str = Field("", max_length=200)
    quote: str = Field("", max_length=2000)
    raw_start: int | None = None
    raw_end: int | None = None
    page_anchor: str | None = Field(None, max_length=200)
    scheme: str | None = Field(None, max_length=32)
    addr1: int | None = None
    addr2: str | None = Field(None, max_length=64)
    role: str = Field("supports", max_length=32)

    @field_validator("work_id")
    @classmethod
    def _work_id_safe(cls, v: str) -> str:
        if not v:
            return v                    # 空 work_id（纯文字 claim）合法
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", v):
            raise ValidationError("work_id 只接受语料目录名（字母数字._-）")
        if ".." in v:
            raise ValidationError("work_id 不允许含 ..")
        return v

    @field_validator("quote")
    @classmethod
    def _quote_required_with_source(cls, v: str, info) -> str:
        # R230a-32（R14-P2-4）：给了出处（work_id）却不给引文，等于声称
        # 有凭据但不可核验——verify() 对空 quote 是恒真漏洞。
        if info.data.get("work_id") and not v.strip():
            raise ValidationError("给了出处就得给引文（quote 不能为空）")
        return v


class ThreadRecordRequest(BaseModel):
    """研究线程写入（R34b）：一条 derived claim + 可选证据（G8 纪律）。"""
    kind: str = Field(..., description="summary | diff | link | answer | refusal")
    claim: str = Field(..., min_length=1, max_length=2000)
    method: str = Field(..., min_length=1, max_length=100)
    # R229n（R6-#4）：evidence/confidence/topic 加界——此前无上限，单请求
    # 可携数千条 evidence 批量写库（写放大）。与 facts ≤20×500 同纪律。
    evidence: list[ThreadEvidence] = Field(default_factory=list,
                                           max_length=64)
    confidence: str | None = Field(None, max_length=50)
    thread_id: int | None = None
    # R228s：thread_id 缺席时后端自动开新线程，topic 作线程题
    topic: str | None = Field(None, max_length=100)

    @field_validator("claim", "method", "topic", "confidence")
    @classmethod
    def _no_c0(cls, v: str | None) -> str | None:
        # R230a-36（R14-P2-4 续）：C0 控制字符在写路径剥掉——读路径
        # （fts_phrase）已剥，写路径不剥会让含 \x00 的 claim 永不可被
        # derived_fts 检回（不对称）。
        return v if v is None else "".join(
            ch for ch in v if ord(ch) >= 0x20)


class LiuyaoRequest(BaseModel):
    method: str = "coins"        # coins | time
    seed: int | None = None      # coins 法：可选 seed（复验用），不传则真随机
    year: int | None = None      # time 法：公历年/月/日/时
    month: int | None = None
    day: int | None = None
    hour: int | None = None
    question: str | None = Field(None, max_length=200)

    def validate_ranges(self) -> None:
        if self.method not in ("coins", "time"):
            raise ValidationError(f"起卦方式需为 coins|time，收到 {self.method}")
        if self.method != "time":
            return
        if not all(v is not None for v in (self.year, self.month,
                                           self.day, self.hour)):
            raise ValidationError("时间起卦需年份、月份、日、时辰")
        if not (YEAR_LO <= self.year <= YEAR_HI):
            raise ValidationError(f"年份需在 {YEAR_LO}-{YEAR_HI}，收到 {self.year}")
        if not (1 <= self.month <= 12):
            raise ValidationError(f"月份需在 1-12，收到 {self.month}")
        if not (1 <= self.day <= 31):
            raise ValidationError(f"日需在 1-31，收到 {self.day}")
        if not (0 <= self.hour <= 23):
            raise ValidationError(f"时辰需在 0-23，收到 {self.hour}")


class QimingRequest(BaseModel):
    surname: str = Field(..., description="姓氏（单字）")
    year: int = Field(..., description="公历年")
    month: int = Field(..., description="月 1-12")
    day: int = Field(..., description="日 1-31")
    hour: int = Field(..., description="时 0-23")
    gender: str = "男"
    # R228j：top_n 此前无界（文档面只写了建议范围），大值让响应膨胀；
    # style 无枚举校验——拼错的值静默按 all 出结果，用户以为没生效。
    top_n: int = Field(20, ge=1, le=50)
    seed: int | None = Field(None, description="随机种子（换一批时传入，None=默认确定性输出）")
    style: str = Field("all", description="v3（P3）风格档：classics=诗经类 / chuci=楚辞类 / fresh=柔美 / all=全部")

    def validate_ranges(self) -> None:
        if not (YEAR_LO <= self.year <= YEAR_HI):
            raise ValidationError(f"年份需在 {YEAR_LO}-{YEAR_HI}，收到 {self.year}")
        if not self.surname or len(self.surname) != 1:
            raise ValidationError("姓氏需为单字")
        # R228j：style 枚举——非法值不许静默当 all
        if self.style not in ("all", "classics", "chuci", "fresh"):
            raise ValidationError("风格只能是 all/classics/chuci/fresh")
        if not (1 <= self.month <= 12):
            raise ValidationError(f"月份需在 1-12，收到 {self.month}")
        if not (1 <= self.day <= 31):
            raise ValidationError(f"日需在 1-31，收到 {self.day}")
        if not (0 <= self.hour <= 23):
            raise ValidationError(f"时辰需在 0-23，收到 {self.hour}")
        if self.gender not in GENDERS:
            raise ValidationError(f"性别需为 男/女，收到 {self.gender}")


class ChatRequest(BaseModel):
    """AI 陪伴层请求（R206b，specs/009 US1；D-259b）。

    message 上限 500 字（防滥用）；facts 由前端从已得排盘结果透传
    （坐标事实字符串，非 PII——不含生日，只有干支五行词）。"""
    session_id: str = Field(..., description="会话 id（前端生成 UUID）")
    message: str = Field(..., description="用户消息（≤500 字）")
    facts: list[str] | None = None

    def validate_ranges(self) -> None:
        if not self.session_id or len(self.session_id) > 64:
            raise ValidationError("session_id 需为 1-64 字符")
        msg = strip_zw(self.message) or ""      # R230k：零宽剥后可为空
        if not msg:
            raise ValidationError("消息不能为空")
        if len(msg) > 500:
            raise ValidationError(f"消息超长（≤500 字），收到 {len(msg)} 字")
        # R228r：facts 无界可塞爆 LLM system prompt——限条数+单条长度。
        for f in (self.facts or []):
            if not isinstance(f, str) or len(f) > 500:
                raise ValidationError("facts 单条需为 ≤500 字字符串")
        if self.facts and len(self.facts) > 20:
            raise ValidationError("facts 最多 20 条")


class NameReviewRequest(BaseModel):
    """AI 起名点评请求（R207b）。names ≤6 个。"""
    names: list[str] = Field(..., description="候选完整名列表（≤6）")
    facts: list[str] | None = None

    def validate_ranges(self) -> None:
        clean = [n for n in (self.names or []) if n.strip()]
        if not clean:
            raise ValidationError("候选名不能为空")
        if len(clean) > 6:
            raise ValidationError(f"候选名最多 6 个，收到 {len(clean)} 个")
        for n in clean:
            if len(n) > 8:
                raise ValidationError(f"名字过长：{n[:8]}…")
        # R230a-6（R12-P2-6）：facts 此前无校验——单请求可塞 ~50 万字进
        # prompt（仅全局 512KB 体帽兜底）。与 ChatRequest 同款界。
        if self.facts:
            if len(self.facts) > 20:
                raise ValidationError("facts 最多 20 条")
            for f in self.facts:
                if not isinstance(f, str) or len(f) > 500:
                    raise ValidationError("facts 单条需为 ≤500 字字符串")


class TarotRequest(BaseModel):
    seed: int = Field(42, description="随机种子（固定 seed → 固定牌面，可复验）")
    # R228j：文档写 1-10 但此前无 Field 界——n=9999 内部钳制改语义，改边界即拒
    n: int = Field(3, ge=1, le=10, description="抽牌张数 1-10，默认 3（过去/现在/未来）")
    question: str | None = Field(None, max_length=200)


class TarotDrawRequest(BaseModel):
    seed: int | None = None
    n: int = Field(1, ge=1, le=10)
    question: str | None = Field(None, max_length=200)


class PrefsRequest(BaseModel):
    """用户偏好写入：自由键值（theme / recent_modules / …）。

    原实现直接收裸 dict 参数，FastAPI 把它当请求体但不做任何形状校验。
    这里用 `model_config extra='allow'` 保留"任意键"的原契约，同时让
    OpenAPI 有一个具名模型，且非 JSON-object 请求体在边界即被拒。
    """
    model_config = {"extra": "allow"}

    def to_dict(self) -> dict:
        return self.model_dump()


class HehunRequest(BaseModel):
    """八字合婚（R121b，D-167b）：两人公历生日（同 BaziRequest 的 solar 约定）。"""
    a_year: int = Field(..., description="甲 公历年")
    a_month: int = Field(..., description="甲 月 1-12")
    a_day: int = Field(..., description="甲 日 1-31")
    a_hour: int = Field(..., description="甲 时 0-23")
    a_gender: str = "男"
    b_year: int = Field(..., description="乙 公历年")
    b_month: int = Field(..., description="乙 月 1-12")
    b_day: int = Field(..., description="乙 日 1-31")
    b_hour: int = Field(..., description="乙 时 0-23")
    b_gender: str = "女"

    def validate_ranges(self) -> None:
        _check_ymdh("甲", self.a_year, self.a_month, self.a_day, self.a_hour)
        _check_ymdh("乙", self.b_year, self.b_month, self.b_day, self.b_hour)
        # R228i：gender 此前零校验——非法值落进 dayun_dir 的 else 分支
        # 按「逆」静默排大运（bazi.py:324），输出错误结果还打了 200。
        if self.a_gender not in GENDERS:
            raise ValidationError("甲方性别需为 男 或 女")
        if self.b_gender not in GENDERS:
            raise ValidationError("乙方性别需为 男 或 女")


# R178b（D-229b）：原 `DailyRequest` 已删除——`/api/daily` 的 `date` 改为
# 查询参数（原来声明为 GET 的请求体模型，查询串被忽略，是 bug 不是契约）。
# 保留一个空壳只会让人以为它还在用，故整体移除。


class FavoriteAddRequest(BaseModel):
    """R228j：三字段此前零界——type 无白名单、ref_id/title 无长度上限，
    一次请求可无限写行。favorites 表无上限，参考 KEEP_MAX 语义先卡输入面。"""
    type: str = Field(..., max_length=32)
    ref_id: str = Field(..., max_length=64)
    title: str = Field(..., max_length=200)

    @field_validator("type")
    @classmethod
    def _type_whitelist(cls, v: str) -> str:
        if v not in ("bazi", "taohua", "hehun", "qiming", "liuyao",
                     "huangli", "xingzuo", "tarot", "daily", "book",
                     "thread"):
            raise ValidationError("收藏类型未知")
        return v
