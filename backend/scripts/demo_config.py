"""演示账号与种子数据：4 渠道 / 160 条原始岗位 / 1 次归并运行 / 3 条已复核结论。

数据构造是确定性的（固定锚点时间、无随机数），因此：
- 两次 seed 的 SEED_SUMMARY 逐字一致；
- 归并算法在同一份数据上必然得到 118 簇（21 个多成员簇，42 条重复被消掉）。

口径说明：
- 21 个「重复组」每组 3 条，分别挂在 3 个不同渠道上；
- 其中 12 组带 13 薪写法差异或公司名写法差异 → 算法标记 needs_review；
- 97 个单条岗位里有 18 条薪资不可比（12 条面议 + 6 条不可解析），8 条已过期。
"""
from __future__ import annotations

from datetime import datetime, timedelta

DEMO_PASSWORD = "Demo@2026"

ORG = "云雀招聘聚合 · 岗位运营组"
ANCHOR = datetime(2026, 11, 14, 9, 30)

DEMO_USERS = [
    ("admin@jobmerge.io", "林可", "admin"),
    ("analyst@jobmerge.io", "周棠", "analyst"),
    ("viewer@jobmerge.io", "陈默", "viewer"),
]

CHANNELS = [
    {
        "code": "zhaopin",
        "name": "智联招聘 · 主站",
        "kind": "site",
        "crawl_cron": "0 6 * * *",
        "endpoint": "https://www.zhaopin.com/sou/jl530",
        "note": "综合门户，岗位量大、公司名多为全称",
        "crawl_offset_hours": 2,
    },
    {
        "code": "boss",
        "name": "BOSS 直聘 · 接口",
        "kind": "api",
        "crawl_cron": "0 7 * * *",
        "endpoint": "https://open.example-boss.cn/v1/jobs",
        "note": "接口返回，薪资常带「·13薪」后缀",
        "crawl_offset_hours": 3,
    },
    {
        "code": "lagou",
        "name": "拉勾网 · 主站",
        "kind": "site",
        "crawl_cron": "0 8 * * *",
        "endpoint": "https://www.lagou.com/wn/jobs",
        "note": "互联网岗位为主，公司名常省略「有限公司」",
        "crawl_offset_hours": 5,
    },
    {
        "code": "liepin",
        "name": "猎聘 · 接口",
        "kind": "api",
        "crawl_cron": "30 6 * * *",
        "endpoint": "https://open.example-liepin.cn/api/job/search",
        "note": "中高端岗位，年薪写法较多，部分字段为空",
        "crawl_offset_hours": 6,
    },
]

DEGREES = ["本科", "大专", "硕士", "不限"]
EXPERIENCES = ["3-5年", "1-3年", "5-10年", "不限"]
CITIES = ["北京", "上海", "深圳", "杭州", "广州", "成都"]

# ---- 21 个重复组（每组 3 条，跨 3 个渠道）----
# companies: 3 条的公司名写法；titles: 3 条的职位写法；salaries: 3 条的薪资写法
DUP_GROUPS = [
    # 完全同写法（不触发复核）
    {"companies": ("云雀数智科技有限公司",) * 3, "titles": ("Java开发工程师", "Java 开发工程师（急聘）", "Java开发工程师-双休"), "city": "北京", "salaries": ("10-15K",) * 3},
    {"companies": ("泓源信息技术有限公司",) * 3, "titles": ("数据分析师",) * 3, "city": "上海", "salaries": ("12-18K",) * 3},
    {"companies": ("拾光网络科技有限公司",) * 3, "titles": ("前端开发工程师",) * 3, "city": "深圳", "salaries": ("15-20K",) * 3},
    {"companies": ("长风供应链有限公司",) * 3, "titles": ("运营专员",) * 3, "city": "杭州", "salaries": ("8-12K",) * 3},
    # 写法混乱但折月后区间相同（不触发复核）
    {"companies": ("南屿数据科技有限公司",) * 3, "titles": ("测试工程师",) * 3, "city": "北京", "salaries": ("10-15K", "月薪10000-15000元", "10000-15000元/月")},
    {"companies": ("知舟软件服务有限公司",) * 3, "titles": ("产品经理",) * 3, "city": "广州", "salaries": ("15-20K", "月薪15000-20000元", "15000-20000元/月")},
    {"companies": ("禾木智能科技有限公司",) * 3, "titles": ("运维工程师",) * 3, "city": "成都", "salaries": ("20-30K", "月薪20000-30000元", "20000-30000元/月")},
    {"companies": ("白鹭数字科技有限公司",) * 3, "titles": ("运营专员",) * 3, "city": "成都", "salaries": ("8-12K", "月薪8000-12000元", "8000-12000元/月")},
    # 13 薪写法差异（触发复核）
    {"companies": ("白石数字营销有限公司",) * 3, "titles": ("Java开发工程师", "Java 开发工程师（后端）", "Java开发工程师"), "city": "北京", "salaries": ("10-15K", "10-15K", "10-15K·13薪")},
    {"companies": ("青柠电子商务有限公司",) * 3, "titles": ("前端开发工程师",) * 3, "city": "上海", "salaries": ("10-15K", "10-15K", "10-15K·13薪")},
    {"companies": ("星野云计算有限公司",) * 3, "titles": ("数据分析师",) * 3, "city": "深圳", "salaries": ("10-15K", "10-15K", "10-15K·13薪")},
    {"companies": ("砺行人力资源有限公司",) * 3, "titles": ("测试工程师",) * 3, "city": "杭州", "salaries": ("10-15K", "10-15K", "10-15K·13薪")},
    {"companies": ("合川网络科技有限公司",) * 3, "titles": ("运营专员",) * 3, "city": "广州", "salaries": ("10-15K", "10-15K", "10-15K·13薪")},
    {"companies": ("鹿鸣智能科技有限公司",) * 3, "titles": ("算法工程师",) * 3, "city": "北京", "salaries": ("15-20K", "15-20K", "15-20K·13薪")},
    {"companies": ("朴石信息技术有限公司",) * 3, "titles": ("Java开发工程师",) * 3, "city": "上海", "salaries": ("15-20K", "15-20K", "15-20K·13薪")},
    {"companies": ("澄海数据科技有限公司",) * 3, "titles": ("测试工程师",) * 3, "city": "深圳", "salaries": ("15-20K", "15-20K", "15-20K·13薪")},
    # 公司名写法差异（触发复核）
    {"companies": ("元朔智能科技（北京）有限公司", "元朔智能科技有限公司", "元朔智能科技"), "titles": ("前端开发工程师", "前端 开发工程师（急聘）", "前端开发工程师"), "city": "北京", "salaries": ("12-18K",) * 3},
    {"companies": ("沐恩云计算有限公司", "沐恩云计算", "沐恩云计算（上海）有限公司"), "titles": ("产品经理",) * 3, "city": "上海", "salaries": ("15-20K",) * 3},
    {"companies": ("嘉禾数字营销有限公司", "嘉禾数字营销", "嘉禾数字营销（深圳）有限公司"), "titles": ("数据分析师",) * 3, "city": "深圳", "salaries": ("10-15K",) * 3},
    {"companies": ("恒益通软件服务有限公司", "恒益通软件服务", "恒益通软件服务（杭州）有限公司"), "titles": ("运维工程师",) * 3, "city": "杭州", "salaries": ("12-18K",) * 3},
    # 年薪写法（不触发复核）
    {"companies": ("云栖信息科技有限公司",) * 3, "titles": ("算法工程师",) * 3, "city": "北京", "salaries": ("年薪18万",) * 3},
]

# ---- 97 个单条岗位 ----
UNIQUE_PREFIXES = [
    "启明", "远山", "泓源", "拾光", "南屿", "知舟", "禾木", "长风", "青柠", "白石",
    "云栖", "星野", "砺行", "合川", "鹿鸣", "朴石", "澄海", "元朔", "沐恩", "嘉禾",
]
UNIQUE_SUFFIXES = [
    "数据科技", "网络科技", "信息技术", "电子商务", "软件服务",
    "智能科技", "数字营销", "人力资源", "云计算", "供应链",
]
TITLE_POOL = [
    "Java开发工程师", "前端开发工程师", "测试工程师", "数据分析师",
    "运维工程师", "产品经理", "算法工程师", "运营专员",
]
TITLE_VARIANTS = [
    "{title}", "{title}", "{title}（急聘）", "{title} - 双休", "{title}", "{title}",
]
NORMAL_SALARIES = [
    "8-12K", "10-18K", "12-20K", "6-9千", "15-25K·14薪", "20-30K",
    "年薪30万", "4000-6000元/月", "8-12K·13薪", "1万-1.5万/月", "9-14K", "11-16K",
]
NEGOTIABLE_SALARIES = ["面议", "薪资面议", "面议，可谈"]
UNPARSED_SALARIES = ["12-8K", "100元/天", "待遇从优，具体面聊", "薪资：见合同", "3000-800", "按单结算"]
UNIQUE_PLAN = {"negotiable": 12, "unparsed": 6, "expired": 8, "normal": 71}


def _months_ago(days: int) -> datetime:
    return ANCHOR - timedelta(days=days)


def _unique_company(index: int) -> str:
    prefix = UNIQUE_PREFIXES[index % len(UNIQUE_PREFIXES)]
    suffix = UNIQUE_SUFFIXES[(index // len(UNIQUE_PREFIXES)) % len(UNIQUE_SUFFIXES)]
    return f"{prefix}{suffix}有限公司"


def _post(
    *,
    seed_key: str,
    external_id: str,
    channel_code: str,
    company_raw: str,
    title_raw: str,
    city: str,
    salary_raw: str,
    degree: str,
    experience: str,
    published_at: datetime,
    expire_at: datetime | None,
    index: int,
) -> dict:
    return {
        "seed_key": seed_key,
        "external_id": external_id,
        "channel_code": channel_code,
        "company_raw": company_raw,
        "title_raw": title_raw,
        "city": city,
        "salary_raw": salary_raw,
        "degree": degree,
        "experience": experience,
        "published_at": published_at,
        "expire_at": expire_at,
        "raw_text": (
            f"{company_raw} 招聘 {title_raw}｜{city}｜{salary_raw}｜{degree}｜{experience}｜"
            f"来源渠道 {channel_code}，采集批次 b{index // 10:03d}。"
        ),
    }


def build_posts() -> list[dict]:
    """构造 160 条原始岗位（21×3 重复组 + 97 单条），顺序固定。"""
    channel_codes = [item["code"] for item in CHANNELS]
    posts: list[dict] = []

    for group_index, group in enumerate(DUP_GROUPS):
        base = group_index * 3
        for member in range(3):
            channel_code = channel_codes[(group_index + member) % len(channel_codes)]
            posts.append(
                _post(
                    seed_key=f"seed-post-{base + member + 1:03d}",
                    external_id=f"g{group_index + 1:02d}-{member + 1}",
                    channel_code=channel_code,
                    company_raw=group["companies"][member],
                    title_raw=group["titles"][member],
                    city=group["city"],
                    salary_raw=group["salaries"][member],
                    degree=DEGREES[group_index % len(DEGREES)],
                    experience=EXPERIENCES[group_index % len(EXPERIENCES)],
                    published_at=_months_ago((group_index * 3 + member) % 18),
                    expire_at=ANCHOR + timedelta(days=30),
                    index=base + member,
                )
            )

    total_unique = UNIQUE_PLAN["negotiable"] + UNIQUE_PLAN["unparsed"] + UNIQUE_PLAN["expired"] + UNIQUE_PLAN["normal"]
    for slot in range(total_unique):
        if slot < UNIQUE_PLAN["negotiable"]:
            salary = NEGOTIABLE_SALARIES[slot % len(NEGOTIABLE_SALARIES)]
            expired = False
        elif slot < UNIQUE_PLAN["negotiable"] + UNIQUE_PLAN["unparsed"]:
            offset = slot - UNIQUE_PLAN["negotiable"]
            salary = UNPARSED_SALARIES[offset % len(UNPARSED_SALARIES)]
            expired = False
        elif slot < UNIQUE_PLAN["negotiable"] + UNIQUE_PLAN["unparsed"] + UNIQUE_PLAN["expired"]:
            offset = slot - UNIQUE_PLAN["negotiable"] - UNIQUE_PLAN["unparsed"]
            salary = NORMAL_SALARIES[offset % len(NORMAL_SALARIES)]
            expired = True
        else:
            salary = NORMAL_SALARIES[slot % len(NORMAL_SALARIES)]
            expired = False

        company = _unique_company(slot)
        title = TITLE_VARIANTS[slot % len(TITLE_VARIANTS)].format(title=TITLE_POOL[slot % len(TITLE_POOL)])
        channel_code = channel_codes[slot % len(channel_codes)]
        posts.append(
            _post(
                seed_key=f"seed-post-{63 + slot + 1:03d}",
                external_id=f"u{slot + 1:03d}",
                channel_code=channel_code,
                company_raw=company,
                title_raw=title,
                city=CITIES[slot % len(CITIES)],
                salary_raw=salary,
                degree=DEGREES[slot % len(DEGREES)],
                experience=EXPERIENCES[(slot + 1) % len(EXPERIENCES)],
                published_at=_months_ago(slot % 21),
                expire_at=ANCHOR - timedelta(days=5 + slot % 4) if expired else ANCHOR + timedelta(days=45),
                index=63 + slot,
            )
        )

    return posts


POSTS = build_posts()

# 3 条历史复核结论：把 needs_review 簇里指纹最小的 3 个固定下来
SEED_REVIEWS = [
    {"decision": "merge", "reviewer": "analyst@jobmerge.io", "note": "确认三条为同一岗位，渠道间仅薪资写法不同。"},
    {"decision": "merge", "reviewer": "admin@jobmerge.io", "note": "公司名全称/简称已核对为同一主体，保留合并。"},
    {"decision": "keep", "reviewer": "analyst@jobmerge.io", "note": "先保持现状，等渠道侧补齐学历字段再定。"},
]

SEED_RUNS = [
    {"seed_key": "seed-run-merge-1", "trigger": "seed", "operator": "admin@jobmerge.io", "threshold": 0.82},
]
