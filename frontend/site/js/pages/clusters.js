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

/** 客户只读的侧栏：发布版本与检索口径说明，不出现内部复核 / 运行细节。 */
function publicSidePanel(publication) {
  return `<section class="panel">
    ${sectionHead('A', '检索口径', '仅已审核岗位')}
    <div class="panel-body">
      ${kv([
        ['发布版本', `<span class="mono">v${publication?.version_no ?? '—'}</span>`],
        ['可检索岗位', `<b class="tabular">${publication?.published_count ?? '—'}</b>`],
        ['最近发布', fmtTime(publication?.created_at)],
        ['口径说明', esc(publication?.rule_version || '—')],
      ])}
    </div>
    <div class="panel-note">客户视图只包含已审核通过且未过期的岗位；公司名已脱敏，内部薪资依据与归并指纹不在客户入口展示。</div>
  </section>`;
}

/** 内部侧栏：发起归并 + 分块与连边。 */
function runPanel(ctx, latest, metrics) {
  return `<section class="panel">
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
    </section>`;
}

export const clustersPage = {
  async render(view, ctx) {
    const render = () => clustersPage.render(view, ctx);
    const viewer = ctx.user.role === 'viewer';
    let clusters;
    let runs = { items: [] };
    try {
      const jobs = [
        api.get('/api/clusters', {
          q: state.q,
          status: state.status,
          multi: state.multi === 'true' ? 'true' : '',
          needs_review: state.needsReview === '' ? '' : state.needsReview,
          limit: 60,
        }),
      ];
      if (!viewer) jobs.push(api.get('/api/runs', { limit: 5 }));
      const results = await Promise.all(jobs);
      clusters = results[0];
      if (!viewer) runs = results[1];
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', render);
      return;
    }
    const latest = runs.items[0];
    const metrics = latest?.metrics || {};
    const publication = clusters.publication;

    view.innerHTML = `
      <div class="workbench">
        <section class="panel">
          ${sectionHead(
            '04',
            viewer ? '可检索岗位' : '归并结果',
            viewer
              ? `发布版本 v${publication?.version_no ?? '—'} · ${clusters.total} 个可检索岗位（已审核、未过期）`
              : `${clusters.total} 个归并簇 · 本次显示 ${clusters.items.length} 个`,
          )}
          <div class="panel-body">
            ${filterBar({
              fields: [
                { label: '搜索', name: 'q', value: state.q, placeholder: viewer ? '职位 / 公司' : '公司 / 职位 / 指纹', grow: true },
                ...(viewer
                  ? []
                  : [
                      {
                        label: '状态',
                        name: 'status',
                        value: state.status,
                        options: [
                          { value: '', label: '全部' },
                          ...Object.entries(ENUMS.clusterStatus).map(([value, label]) => ({ value, label })),
                        ],
                      },
                    ]),
                {
                  label: '成员数',
                  name: 'multi',
                  value: state.multi,
                  options: [
                    { value: '', label: '全部' },
                    { value: 'true', label: '仅多成员簇' },
                  ],
                },
                ...(viewer
                  ? []
                  : [
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
                    ]),
              ],
              actions: can(ctx.user.role, 'export:read')
                ? '<button class="btn sm ghost" id="export-clusters">导出客户发布清单 CSV</button>'
                : '',
            })}
            ${
              publication
                ? `<div class="panel-note">当前发布版本 v${publication.version_no}：待复核 ${publication.pending_count} · 可发布 ${publication.published_count} · 已撤回 ${publication.withdrawn_count}（过期 ${publication.expired_count}）。客户列表与导出都只含「可发布」。</div>`
                : ''
            }
          </div>
          ${clusterTable(clusters.items, ctx.user.role)}
          <div class="panel-note">
            ${
              viewer
                ? '此处只展示已审核通过且未过期的岗位；同一职位已按复核结论拆分的，会各自独立出现。'
                : '点击任一行查看成员对照、相似度与复核表单；导出 CSV 的行数 = 发布版本的可发布岗位数，与客户列表逐项一致。'
            }
          </div>
        </section>

        <div class="side-stack">
          ${viewer ? publicSidePanel(publication) : runPanel(ctx, latest, metrics)}
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
