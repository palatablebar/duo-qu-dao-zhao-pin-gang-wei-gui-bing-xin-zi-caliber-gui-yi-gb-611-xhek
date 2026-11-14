import { api } from '../api.js';
import { ENUMS, can, decisionTone } from '../config.js';
import { fmtMoney, fmtPct, openClusterDrawer, sectionHead } from '../components.js';
import { emptyState, errorBox, errorMessage, esc, fmtTime, table, toast } from '../ui.js';

const EXPORTS = [
  { path: '/api/exports/clusters.csv', file: 'jobmerge-clusters.csv', label: '归并清单 CSV', hint: '一行一个归并簇，含月薪中位与置信度' },
  { path: '/api/exports/posts.csv', file: 'jobmerge-posts.csv', label: '岗位口径 CSV', hint: '薪资原值 → 归一值 + 口径说明' },
  { path: '/api/exports/reviews.csv', file: 'jobmerge-reviews.csv', label: '复核记录 CSV', hint: '结论、复核人与备注' },
  { path: '/api/exports/runs.csv', file: 'jobmerge-runs.csv', label: '运行记录 CSV', hint: '每次归并的输入/产出/不可比占比' },
];

function auditPanel(items) {
  if (!items) return '';
  return `<section class="panel">
    ${sectionHead('C', '审计日志', `最近 ${items.length} 条 · 仅管理员可见`)}
    ${
      items.length
        ? table({
            rows: items,
            columns: [
              { key: 'created_at', label: '时间', render: (row) => fmtTime(row.created_at) },
              { key: 'actor_email', label: '操作人', className: 'mono' },
              { key: 'actor_role', label: '角色', className: 'tight' },
              { key: 'action_label', label: '动作' },
              { key: 'entity', label: '对象', className: 'tight' },
              { key: 'layer', label: '层', render: (row) => `<span class="badge">${esc(row.layer)}</span>` },
              {
                key: 'detail',
                label: '详情',
                render: (row) => `<span class="mono muted">${esc(JSON.stringify(row.detail || {}))}</span>`,
              },
            ],
          })
        : emptyState({ title: '还没有审计记录', hint: '登录、归并、复核、导出都会留痕。' })
    }
  </section>`;
}

export const reviewsPage = {
  async render(view, ctx) {
    const render = () => reviewsPage.render(view, ctx);
    let pending;
    let history;
    let audit = null;
    try {
      const jobs = [api.get('/api/reviews/pending', { limit: 20 }), api.get('/api/reviews', { limit: 20 })];
      if (can(ctx.user.role, 'audit:read')) jobs.push(api.get('/api/audit', { limit: 30 }));
      const results = await Promise.all(jobs);
      pending = results[0];
      history = results[1];
      audit = results[2]?.items || null;
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', render);
      return;
    }

    view.innerHTML = `
      <div class="workbench">
        <section class="panel">
          ${sectionHead('05', '待复核队列', `${pending.total} 个簇等待人工确认`)}
          ${
            pending.items.length
              ? table({
                  rows: pending.items,
                  columns: [
                    {
                      key: 'company_display',
                      label: '公司 / 职位',
                      render: (row) => `<b>${esc(row.company_display)}</b><div class="cell-sub">${esc(row.title_display)} · ${esc(row.fingerprint)}</div>`,
                    },
                    { key: 'city', label: '城市', className: 'tight' },
                    { key: 'member_count', label: '成员 / 渠道', className: 'num', render: (row) => `${row.member_count} / ${row.channel_count}` },
                    { key: 'salary_basis', label: '薪资写法', className: 'mono' },
                    { key: 'monthly_median', label: '月薪中位', className: 'num', render: (row) => fmtMoney(row.monthly_median) },
                    { key: 'confidence', label: '置信度', className: 'num', render: (row) => Number(row.confidence).toFixed(3) },
                    { key: 'reason', label: '触发复核', render: (row) => `<span class="cell-sub">${esc(row.reason)}</span>` },
                  ],
                })
              : emptyState({ title: '队列已清空', hint: '所有需要人工确认的归并簇都已给出结论。' })
          }
          <div class="panel-note">点击任一行打开簇详情：左侧成员对照、右侧直接提交合并/拆分结论（会写审计）。</div>
        </section>

        <div class="side-stack">
          <section class="panel">
            ${sectionHead('A', '导出发布清单', 'UTF-8 BOM · Excel 直开')}
            <div class="panel-body" style="display:grid;gap:8px">
              ${
                can(ctx.user.role, 'export:read')
                  ? EXPORTS.map(
                      (item) => `<button class="btn ghost" data-export="${item.path}" data-file="${item.file}">
                        ${esc(item.label)}<div class="cell-sub">${esc(item.hint)}</div>
                      </button>`,
                    ).join('')
                  : '<div class="panel-note">只读角色不能导出；导出接口对 viewer 返回 403。</div>'
              }
            </div>
          </section>

          <section class="panel">
            ${sectionHead('B', '最近复核结论', `${history.total} 条`)}
            ${
              history.items.length
                ? table({
                    rows: history.items,
                    columns: [
                      { key: 'decision', label: '结论', render: (row) => `<span class="badge ${decisionTone(row.decision)}">${esc(row.decision_label || row.decision)}</span>` },
                      {
                        key: 'cluster',
                        label: '簇',
                        render: (row) => `<b>${esc(row.cluster?.company_display || '—')}</b><div class="cell-sub">${esc(row.cluster?.title_display || '')}</div>`,
                      },
                      {
                        key: 'reviewer',
                        label: '复核人',
                        className: 'mono',
                        render: (row) => esc(String(row.reviewer || '').split('@')[0]),
                      },
                      { key: 'updated_at', label: '时间', className: 'tight', render: (row) => fmtTime(row.updated_at) },
                    ],
                  })
                : emptyState({ title: '还没有复核结论', hint: '从待复核队列挑一个开始。' })
            }
          </section>
        </div>
      </div>
      ${auditPanel(audit)}`;

    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const clusterId = Number(row.dataset.id);
        if (clusterId) openClusterDrawer(ctx, clusterId, { onDone: render });
      });
    });
    view.querySelectorAll('[data-export]').forEach((button) => {
      button.addEventListener('click', async () => {
        try {
          await api.download(button.dataset.export, button.dataset.file);
          toast('已开始下载');
        } catch (err) {
          toast(errorMessage(err), 'err');
        }
      });
    });
  },
};

export default reviewsPage;
