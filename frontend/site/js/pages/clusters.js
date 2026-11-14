import { api } from '../api.js';
import { ENUMS, can } from '../config.js';
import { bindFilters, clusterStatusBadge, clusterTable, filterBar, fmtMoney, fmtPct, openClusterDrawer, sectionHead } from '../components.js';
import { emptyState, errorBox, errorMessage, esc, field, fmtTime, kv, toast } from '../ui.js';

const state = { q: '', status: '', multi: '', needsReview: '' };

function runForm(role) {
  if (!can(role, 'run:create')) {
    return '<div class="panel-note">当前角色只读，不能发起归并。</div>';
  }
  return `<form id="run-form" class="coupon-form">
    ${field({
      label: '相似度阈值',
      name: 'threshold',
      options: [0.7, 0.75, 0.82, 0.86, 0.9].map((value) => ({ value: String(value), label: value.toFixed(2) })),
      value: '0.82',
    })}
    <button class="btn accent" type="submit">按当前口径重新归并</button>
  </form>`;
}

export const clustersPage = {
  async render(view, ctx) {
    const render = () => clustersPage.render(view, ctx);
    let clusters;
    let runs;
    try {
      [clusters, runs] = await Promise.all([
        api.get('/api/clusters', {
          q: state.q,
          status: state.status,
          multi: state.multi === 'true' ? 'true' : '',
          needs_review: state.needsReview === '' ? '' : state.needsReview,
          limit: 60,
        }),
        api.get('/api/runs', { limit: 5 }),
      ]);
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', render);
      return;
    }
    const latest = runs.items[0];
    const metrics = latest?.metrics || {};

    view.innerHTML = `
      <div class="workbench">
        <section class="panel">
          ${sectionHead('04', '归并结果', `${clusters.total} 个归并簇 · 本次显示 ${clusters.items.length} 个`)}
          <div class="panel-body">
            ${filterBar({
              fields: [
                { label: '搜索', name: 'q', value: state.q, placeholder: '公司 / 职位 / 指纹', grow: true },
                {
                  label: '状态',
                  name: 'status',
                  value: state.status,
                  options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.clusterStatus).map(([value, label]) => ({ value, label }))],
                },
                {
                  label: '成员数',
                  name: 'multi',
                  value: state.multi,
                  options: [
                    { value: '', label: '全部' },
                    { value: 'true', label: '仅多成员簇' },
                  ],
                },
                {
                  label: '待复核',
                  name: 'needs_review',
                  value: state.needsReview,
                  options: [
                    { value: '', label: '全部' },
                    { value: 'true', label: '是' },
                    { value: 'false', label: '否' },
                  ],
                },
              ],
              actions: can(ctx.user.role, 'export:read')
                ? '<button class="btn sm ghost" id="export-clusters">导出归并清单 CSV</button>'
                : '',
            })}
          </div>
          ${clusterTable(clusters.items, ctx.user.role)}
          <div class="panel-note">点击任一行查看成员对照、相似度与复核表单；导出 CSV 的行数 = 当前运行的归并簇数。</div>
        </section>

        <div class="side-stack">
          <section class="panel">
            ${sectionHead('A', '发起归并', '算法 B · dedupe.py')}
            <div class="panel-body">
              ${runForm(ctx.user.role)}
              ${
                latest
                  ? `<div style="margin-top:10px">${kv([
                      ['最近运行', `<span class="mono">${esc(latest.run_no)}</span>`],
                      ['状态', `<span class="badge ${latest.status === 'success' ? 'ok' : 'warn'}">${esc(ENUMS.runStatus[latest.status] || latest.status)}</span>`],
                      ['输入 / 输出', `${latest.posts_in} 条 → ${latest.clusters_out} 簇`],
                      ['消重', `<b class="tabular">${latest.dupes_removed}</b> 条`],
                      ['阈值', `<span class="mono">${Number(latest.threshold).toFixed(2)}</span>`],
                      ['待复核 / 过期', `${metrics.needs_review ?? '—'} / ${metrics.expired_clusters ?? '—'}`],
                      ['完成时间', fmtTime(latest.finished_at)],
                    ])}</div>`
                  : emptyState({ title: '还没有归并运行', hint: '点上面的按钮发起一次。' })
              }
            </div>
          </section>
          <section class="panel">
            ${sectionHead('B', '分块与连边', 'blocking key')}
            <div class="panel-body ledger">
              <div class="row"><span>分块数</span><b>${metrics.blocks ?? '—'}</b></div>
              <div class="row"><span>两两比较</span><b>${metrics.pairs ?? '—'}</b></div>
              <div class="row"><span>连边数</span><b>${metrics.edges ?? '—'}</b></div>
              <div class="row"><span>多成员簇</span><b>${metrics.multi_clusters ?? '—'}</b></div>
              <div class="row"><span>平均置信度</span><b>${metrics.avg_confidence !== undefined ? Number(metrics.avg_confidence).toFixed(3) : '—'}</b></div>
              <div class="row"><span>不可比占比</span><b>${fmtPct(metrics.noncomparable_rate || 0)}</b></div>
            </div>
            <div class="panel-note">分块键 = 公司归一 + 城市 + 薪资档（5000 元一档）；score ≥ 阈值连边，并查集聚类。</div>
          </section>
        </div>
      </div>`;

    bindFilters(view, (values) => {
      state.q = values.q || '';
      state.status = values.status || '';
      state.multi = values.multi || '';
      state.needsReview = values.needs_review || '';
      render();
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        openClusterDrawer(ctx, Number(row.dataset.id), { onDone: render });
      });
    });
    view.querySelector('#export-clusters')?.addEventListener('click', async () => {
      try {
        await api.download('/api/exports/clusters.csv', 'jobmerge-clusters.csv');
        toast('归并清单 CSV 已开始下载');
      } catch (err) {
        toast(errorMessage(err), 'err');
      }
    });
    view.querySelector('#run-form')?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const form = event.target;
      const button = form.querySelector('button[type=submit]');
      button.disabled = true;
      button.textContent = '归并中…';
      try {
        const run = await api.post('/api/runs', { trigger: 'manual', threshold: Number(form.threshold.value) });
        toast(`归并完成：${run.posts_in} 条 → ${run.clusters_out} 簇，消重 ${run.dupes_removed} 条`);
        await render();
      } catch (err) {
        toast(errorMessage(err), 'err');
        button.disabled = false;
        button.textContent = '按当前口径重新归并';
      }
    });
  },
};

export default clustersPage;
