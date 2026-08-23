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

from pydantic import BaseModel, Field

YEAR_LO, YEAR_HI = 1900, 2100
SCOPES = ("day", "range", "life")
CALENDARS = ("solar", "lunar")
GENDERS = ("男", "女")


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
        raise ValidationError(f"{tag} 年份须在 {YEAR_LO}-{YEAR_HI}，收到 {year}")
    if not (1 <= month <= 12):
        raise ValidationError(f"{tag} month 须在 1-12，收到 {month}")
    if not (1 <= day <= 31):
        raise ValidationError(f"{tag} day 须在 1-31，收到 {day}")
    if not (0 <= hour <= 23):
        raise ValidationError(f"{tag} hour 须在 0-23，收到 {hour}")


class BaziRequest(BaseModel):
    year: int = Field(..., description="公历年份（calendar_type=solar 时直接使用）")
    month: int = Field(..., description="月 1-12")
    day: int = Field(..., description="日 1-31")
    hour: int = Field(..., description="时 0-23")
    gender: str = "男"
    question: str | None = None
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
    location: str | None = Field(None, description="问事地点（可选，仅提示用）")

    def validate_ranges(self) -> None:
        """值域校验：非法输入抛 ValidationError（路由层转 400 中文报错）。

        报错文本与校验顺序与重构前逐字一致——web selftest 的 err.bazi.*
        逐条断言这些消息与状态码，改动措辞即改动契约。
        """
        if self.calendar_type not in CALENDARS:
            raise ValidationError("calendar_type 只能是 solar 或 lunar")
        if self.scope not in SCOPES:
            raise ValidationError(f"scope 只能是 {'/'.join(SCOPES)}")
        if self.calendar_type == "lunar":
            if not (self.lunar_year and self.lunar_month and self.lunar_day):
                raise ValidationError("农历输入需提供 lunar_year/month/day")
            if not (1 <= self.lunar_month <= 12):
                raise ValidationError("lunar_month 需在 1-12")
            if not (1 <= self.lunar_day <= 30):
                raise ValidationError("lunar_day 需在 1-30")
        else:
            if not (YEAR_LO <= self.year <= YEAR_HI):
                raise ValidationError(
                    f"year 需在 {YEAR_LO}-{YEAR_HI} 之间（节气表适用范围）")
            if not (1 <= self.month <= 12):
                raise ValidationError("month 需在 1-12")
            if not (1 <= self.day <= 31):
                raise ValidationError("day 需在 1-31")
        if not (0 <= self.hour <= 23):
            raise ValidationError("hour 需在 0-23")
        if self.gender not in GENDERS:
            raise ValidationError("gender 只能是 男 或 女")
        if self.ask_hour is not None and not (0 <= self.ask_hour <= 23):
            raise ValidationError("ask_hour 需在 0-23")
        if self.ask_date is not None:
            try:
                d = date.fromisoformat(self.ask_date)
            except ValueError:
                raise ValidationError("ask_date 需为 YYYY-MM-DD 格式") from None
            if not (YEAR_LO <= d.year <= YEAR_HI):
                raise ValidationError(
                    f"ask_date 年份需在 {YEAR_LO}-{YEAR_HI} 之间")
        if self.scope == "range":
            if not (self.range_start and self.range_end):
                raise ValidationError("scope=range 需提供 range_start 和 range_end")
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
    work_id: str = ""
    file: str = ""
    quote: str = ""
    raw_start: int | None = None
    raw_end: int | None = None
    page_anchor: str | None = None
    scheme: str | None = None
    addr1: int | None = None
    addr2: str | None = None
    role: str = "supports"


class ThreadRecordRequest(BaseModel):
    """研究线程写入（R34b）：一条 derived claim + 可选证据（G8 纪律）。"""
    kind: str = Field(..., description="summary | diff | link | answer | refusal")
    claim: str = Field(..., min_length=1, max_length=2000)
    method: str = Field(..., min_length=1, max_length=100)
    evidence: list[ThreadEvidence] = Field(default_factory=list)
    confidence: str | None = None
    thread_id: int | None = None


class LiuyaoRequest(BaseModel):
    method: str = "coins"        # coins | time
    seed: int | None = None      # coins 法：可选 seed（复验用），不传则真随机
    year: int | None = None      # time 法：公历年/月/日/时
    month: int | None = None
    day: int | None = None
    hour: int | None = None
    question: str | None = None

    def validate_ranges(self) -> None:
        if self.method not in ("coins", "time"):
            raise ValidationError(f"method 须为 coins|time，收到 {self.method}")
        if self.method != "time":
            return
        if not all(v is not None for v in (self.year, self.month,
                                           self.day, self.hour)):
            raise ValidationError("时间起卦需 year/month/day/hour")
        if not (YEAR_LO <= self.year <= YEAR_HI):
            raise ValidationError(f"year 须在 {YEAR_LO}-{YEAR_HI}，收到 {self.year}")
        if not (1 <= self.month <= 12):
            raise ValidationError(f"month 须在 1-12，收到 {self.month}")
        if not (1 <= self.day <= 31):
            raise ValidationError(f"day 须在 1-31，收到 {self.day}")
        if not (0 <= self.hour <= 23):
            raise ValidationError(f"hour 须在 0-23，收到 {self.hour}")


class QimingRequest(BaseModel):
    surname: str = Field(..., description="姓氏（单字）")
    year: int = Field(..., description="公历年")
    month: int = Field(..., description="月 1-12")
    day: int = Field(..., description="日 1-31")
    hour: int = Field(..., description="时 0-23")
    gender: str = "男"
    top_n: int = 20

    def validate_ranges(self) -> None:
        if not (YEAR_LO <= self.year <= YEAR_HI):
            raise ValidationError(f"年份须在 {YEAR_LO}-{YEAR_HI}，收到 {self.year}")
        if not self.surname or len(self.surname) != 1:
            raise ValidationError("surname 须为单字姓氏")
        if not (1 <= self.month <= 12):
            raise ValidationError(f"month 须在 1-12，收到 {self.month}")
        if not (1 <= self.day <= 31):
            raise ValidationError(f"day 须在 1-31，收到 {self.day}")
        if not (0 <= self.hour <= 23):
            raise ValidationError(f"hour 须在 0-23，收到 {self.hour}")
        if self.gender not in GENDERS:
            raise ValidationError(f"gender 须为 男/女，收到 {self.gender}")


class ChatRequest(BaseModel):
    """AI 陪伴层请求（R206b，specs/009 US1；D-259b）。

    message 上限 500 字（防滥用）；facts 由前端从已得排盘结果透传
    （坐标事实字符串，非 PII——不含生日，只有干支五行词）。"""
    session_id: str = Field(..., description="会话 id（前端生成 UUID）")
    message: str = Field(..., description="用户消息（≤500 字）")
    facts: list[str] | None = None

    def validate_ranges(self) -> None:
        if not self.session_id or len(self.session_id) > 64:
            raise ValidationError("session_id 须为 1-64 字符")
        msg = (self.message or "").strip()
        if not msg:
            raise ValidationError("message 不能为空")
        if len(msg) > 500:
            raise ValidationError(f"message 超长（≤500 字），收到 {len(msg)} 字")


class TarotRequest(BaseModel):
    seed: int = Field(42, description="随机种子（固定 seed → 固定牌面，可复验）")
    n: int = Field(3, description="抽牌张数 1-10，默认 3（过去/现在/未来）")
    question: str | None = None


class TarotDrawRequest(BaseModel):
    seed: int | None = None
    n: int = 1
    question: str | None = None


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


# R178b（D-229b）：原 `DailyRequest` 已删除——`/api/daily` 的 `date` 改为
# 查询参数（原来声明为 GET 的请求体模型，查询串被忽略，是 bug 不是契约）。
# 保留一个空壳只会让人以为它还在用，故整体移除。


class FavoriteAddRequest(BaseModel):
    type: str
    ref_id: str
    title: str
