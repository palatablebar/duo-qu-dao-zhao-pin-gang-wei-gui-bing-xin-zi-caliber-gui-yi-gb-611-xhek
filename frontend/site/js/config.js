/**
 * 项目品牌、导航、角色权限与枚举文案（前端唯一定义处）。
 * 后端对应：backend/src/constants/{roles,enums}.py；README 列出全部出现位置。
 */
export const BRAND = {
  short: 'jobmerge',
  title: '多渠道招聘岗位归并与薪资口径归一',
  nameplate: '云雀岗位归并台',
  org: '云雀招聘聚合 · 岗位运营组',
  edition: '第 47 期',
  issue: '2026-11-14',
  subtitle: '把 4 个渠道的原始来稿归一、归并、复核，再交给检索服务与客户报表。',
  loginLead:
    '同一岗位在 4–6 个渠道重复挂，薪资写法各不相同：8-12K·13薪、年薪18万、4000-6000元/月、面议。取一份当日「岗位归并版」，先看口径，再看结论。',
  loginColumns: [
    '岗位运营组每天从 12 个渠道的采集器收岗位，过去在 Excel 里人工挑重复、手算月薪，再导给检索侧。同一职位在结果页刷屏，客户投诉排在前三。',
    '本版把「原始岗位 → 薪资口径归一 → 指纹分块 → 相似度归并 → 人工复核 → 发布清单」做成一条可追溯的线：每条结论都能指回原始岗位行与渠道。',
    '薪资口径统一折算为月薪：名义区间 × 12 ÷ 发薪月数；年薪先 ÷ 12。面议与不可解析的岗位单独标记，不参与可比排序。',
    '归并阈值默认 0.82：低于阈值的岗位不会被强行合并，需要人工在复核版面逐条给结论。合并、拆分、保持原样三种结论都会写进审计，可回溯到原始岗位行。',
    '发布清单以 CSV 导出，一行一个归并簇，带月薪中位、渠道数、成员数与置信度；检索服务按这份清单清洗重复岗，客户报表按同一口径出数。',
  ],
  loginPoints: [
    ['01', '渠道与采集计划集中登记，谁在什么时候抓过、抓回多少条都可查。'],
    ['02', '算法 A 把 6 类薪资写法折成同一口径，并给出归一说明与置信度。'],
    ['03', '算法 B 按公司+城市+薪资档分块，相似度 ≥ 0.82 连边聚类，人工可合并/拆分。'],
  ],
};

export const NAV = [
  { to: '#/overview', no: '01', label: '头版总览', permission: 'overview:read' },
  { to: '#/channels', no: '02', label: '渠道与采集', permission: 'channel:read' },
  { to: '#/posts', no: '03', label: '原始岗位', permission: 'post:read' },
  { to: '#/clusters', no: '04', label: '归并结果', permission: 'cluster:read' },
  { to: '#/reviews', no: '05', label: '复核与导出', permission: 'cluster:read' },
];

export const ROLE_LABELS = {
  admin: '平台管理员',
  analyst: '岗位运营专员',
  viewer: '客户只读',
};

export const ROLE_NOTES = {
  admin: '可维护渠道与阈值、发起归并、导出清单、查看审计。',
  analyst: '可发起归并、复核归并簇；渠道配置只读。',
  viewer: '只读：精确公司名已脱敏，不能发起归并、复核或导出。',
};

export const PERMISSIONS = {
  admin: [
    'overview:read', 'channel:read', 'channel:write', 'post:read',
    'cluster:read', 'cluster:review', 'run:read', 'run:create',
    'export:read', 'audit:read',
  ],
  analyst: [
    'overview:read', 'channel:read', 'post:read',
    'cluster:read', 'cluster:review', 'run:read', 'run:create', 'export:read',
  ],
  viewer: ['overview:read', 'channel:read', 'post:read', 'cluster:read'],
};

export const ENUMS = {
  parseStatus: { parsed: '已归一', negotiable: '面议', unparsed: '不可比' },
  clusterStatus: { active: '在架', expired: '已过期', merged: '已拆散待重算' },
  decision: { merge: '确认合并', split: '拆分为独立岗位', keep: '保持原样' },
  runStatus: { queued: '排队中', running: '执行中', success: '成功', partial: '部分成功', failed: '失败' },
  trigger: { manual: '手动', schedule: '定时', seed: '初始化' },
  channelKind: { site: '招聘站点', api: '接口对接', file: '文件导入', manual: '手工登记' },
  degree: { any: '不限', college: '大专', bachelor: '本科', master: '硕士', doctor: '博士' },
  experience: { any: '不限', '1-3': '1-3 年', '3-5': '3-5 年', '5-10': '5-10 年', '10+': '10 年以上' },
};

export function can(role, permission) {
  return (PERMISSIONS[role] || []).includes(permission);
}

export function statusTone(status) {
  return { active: 'ok', expired: 'warn', merged: 'info' }[status] || 'info';
}

export function parseTone(status) {
  return { parsed: 'ok', negotiable: 'warn', unparsed: 'high' }[status] || 'info';
}

export function decisionTone(decision) {
  return { merge: 'ok', split: 'danger', keep: 'info' }[decision] || 'info';
}
