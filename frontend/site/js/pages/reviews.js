import { api } from '../api.js';
import { can, decisionTone } from '../config.js';
import { fmtMoney, openClusterDrawer, sectionHead } from '../components.js';
import { emptyState, errorBox, errorMessage, esc, fmtTime, statStrip, table, toast } from '../ui.js';

const EXPORTS = [
  { path: '/api/exports/clusters.csv', file: 'jobmerge-clusters.csv', label: '客户发布清单 CSV', hint: '与客户检索列表逐项一致，一行一个可发布岗位' },
  { path: '/api/exports/posts.csv', file: 'jobmerge-posts.csv', label: '原始来稿口径 CSV', hint: '内部用：薪资原值 → 归一值 + 口径说明' },
  { path: '/api/exports/reviews.csv', file: 'jobmerge-reviews.csv', label: '复核记录 CSV', hint: '结论、复核人与备注（重算后仍保留）' },
  { path: '/api/exports/runs.csv', file: 'jobmerge-runs.csv', label: '运行记录 CSV', hint: '每次归并的输入/产出/不可比占比' },
];

/** 发布口径核对条：待复核 / 可发布 / 已撤回 / 已拆分，与客户清单同版本。 */
function publicationStrip(publication) {
  if (!publication) return '';
  return `<div class="panel-body">${statStrip([
    { label: '发布版本', value: `v${publication.version_no}`, hint: publication.status === 'active' ? '当前生效' : '已失效' },
    { label: '待复核', value: publication.pending_count, hint: '未审核，不进入客户视图' },
    { label: '可发布', value: publication.published_count, hint: '客户列表 / 导出行数' },
    { label: '已撤回', value: publication.withdrawn_count, hint: `其中过期 ${publication.expired_count}` },
  ])}</div>`;
}

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
    let counts = null;
    try {
      const jobs = [
        api.get('/api/reviews/pending', { limit: 20 }),
        api.get('/api/reviews', { limit: 20 }),
        api.get('/api/reviews/counts'),
      ];
      if (can(ctx.user.role, 'audit:read')) jobs.push(api.get('/api/audit', { limit: 30 }));
      const results = await Promise.all(jobs);
      pending = results[0];
      history = results[1];
      counts = results[2];
      audit = results[3]?.items || null;
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', render);
      return;
    }
    const publication = counts?.publication || null;

    view.innerHTML = `
      <div class="workbench">
        <section class="panel">
          ${sectionHead('05', '发布口径核对', publication ? `发布版本 v${publication.version_no} · ${publication.rule_version}` : '')}
          ${publicationStrip(publication)}
          <div class="panel-note">
            只有审核通过（确认合并 / 保持原样）且未过期的岗位进入客户视图；拆分结论会把原合并行撤下，
            簇内每条原始岗位各自成为一行。规则或阈值变化时旧版本立即失效，这里与客户列表按同一版本切换。
          </div>
        </section>

        <section class="panel">
          ${sectionHead('06', '待复核队列', `${pending.total} 个簇等待人工确认`)}
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
                      {
                        key: 'cluster',
                        label: '发布版本',
                        className: 'tight',
                        render: (row) => (row.cluster?.status === 'archived' ? '<span class="mono muted">原簇已重算</span>' : ''),
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
