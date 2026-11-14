import { api } from '../api.js';
import { ENUMS, can } from '../config.js';
import { clusterStatusBadge, fmtMoney, fmtPct, sectionHead } from '../components.js';
import { barList, emptyState, errorBox, errorMessage, esc, fmtTime, kv, statStrip, table, trendChart } from '../ui.js';

function latestRunBlock(latest) {
  if (!latest) {
    return emptyState({ title: '还没有归并运行', hint: '去「归并结果」发起一次归并，或等 07:40 的定时任务。' });
  }
  const metrics = latest.metrics || {};
  return `${kv([
    ['运行编号', `<span class="mono">${esc(latest.run_no)}</span>`],
    ['状态', `<span class="badge ${latest.status === 'success' ? 'ok' : 'warn'}">${esc(ENUMS.runStatus[latest.status] || latest.status)}</span>`],
    ['相似度阈值', `<span class="mono">${Number(latest.threshold).toFixed(2)}</span>`],
    ['输入 / 输出', `${latest.posts_in} 条 → ${latest.clusters_out} 簇`],
    ['消重条数', `<b class="tabular">${latest.dupes_removed}</b>`],
    ['两两比较', `${metrics.pairs ?? '—'} 对 / 连边 ${metrics.edges ?? '—'} 条`],
    ['不可比占比', fmtPct(metrics.noncomparable_rate || 0)],
    ['开始时间', fmtTime(latest.started_at)],
  ])}
  <div class="dotted"></div>
  <div class="ledger">
    ${(metrics.unparsed_samples || [])
      .map(
        (item) =>
          `<div class="row"><span class="mono">${esc(item.raw)}</span><b>不可比</b></div>`,
      )
      .join('')}
  </div>`;
}

function publicationBlock(publication) {
  if (!publication) {
    return emptyState({ title: '暂无发布版本', hint: '等待运营复核后生成客户可检索清单。' });
  }
  return `${kv([
    ['发布版本', `<span class="mono">v${publication.version_no}</span>`],
    ['状态', `<span class="badge ${publication.status === 'active' ? 'ok' : 'warn'}">${publication.status === 'active' ? '生效中' : '已失效'}</span>`],
    ['可检索岗位', `<b class="tabular">${publication.published_count}</b>`],
    ['已撤回', `${publication.withdrawn_count}（过期 ${publication.expired_count}）`],
    ['口径版本', `<span class="mono">${esc(publication.rule_version)}</span>`],
    ['生成时间', fmtTime(publication.created_at)],
  ])}
  <div class="panel-note">客户检索与报表只读取本版本里已审核通过、未过期的岗位。</div>`;
}

export const overviewPage = {
  async render(view, ctx) {
    view.innerHTML = '<div class="empty"><div class="mark">排版中…</div></div>';
    let data;
    try {
      data = await api.get('/api/overview');
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', () => overviewPage.render(view, ctx));
      return;
    }
    const salary = data.salary;
    const latest = data.latest_run;
    const noncomparable = salary.negotiable + salary.unparsed;
    const viewer = ctx.user.role === 'viewer';
    const publication = data.publication;
    view.innerHTML = `
      <section class="lead-story">
        <div class="kicker">头版 · 归并综述</div>
        <h2>${data.channels_enabled} 个在用渠道来稿 ${data.posts_total} 条，归并后 ${data.clusters_total} 条岗位进入检索</h2>
        <p class="deck">
          ${
            viewer
              ? `当前发布版本 v${publication?.version_no ?? '—'}，只统计已审核通过且未过期的岗位；
                 ${noncomparable} 条来稿薪资不可比（占 <b>${fmtPct(salary.noncomparable_rate)}</b>），不参与可比排序；
                 ${publication?.withdrawn_count ?? 0} 条岗位已撤回（含过期下线）。`
              : `同期消重 <b>${data.dupes_removed}</b> 条重复挂载，多成员簇 <b>${data.clusters_multi}</b> 个；
                 ${noncomparable} 条岗位薪资不可比（占 <b>${fmtPct(salary.noncomparable_rate)}</b>），其中 ${salary.unparsed} 条无法解析已进不可比清单；
                 ${data.clusters_expired} 个簇因岗位过期下线。`
          }
        </p>
        <div class="lead-figures">
          <div class="fig"><b>${data.posts_total}</b><span>原始来稿</span></div>
          <div class="fig"><b>${data.clusters_total}</b><span>归并后岗位</span></div>
          <div class="fig"><b>${viewer ? (publication?.published_count ?? 0) : data.dupes_removed}</b><span>${viewer ? '可检索岗位' : '消重条数'}</span></div>
          <div class="fig"><b class="red">${fmtPct(salary.noncomparable_rate)}</b><span>薪资不可比占比</span></div>
        </div>
      </section>

      ${statStrip(
        viewer
          ? [
              { label: '在用渠道', value: `${data.channels_enabled}/${data.channels_total}`, hint: '采集计划已登记' },
              { label: '原始岗位', value: data.posts_total, hint: '各渠道来稿合计' },
              { label: '可检索岗位', value: publication?.published_count ?? 0, hint: `发布版本 v${publication?.version_no ?? '—'}` },
              { label: '已撤回', value: publication?.withdrawn_count ?? 0, hint: `其中过期 ${publication?.expired_count ?? 0}` },
            ]
          : [
              { label: '在用渠道', value: `${data.channels_enabled}/${data.channels_total}`, hint: '采集计划已登记' },
              { label: '原始岗位', value: data.posts_total, hint: `已过期 ${data.posts_expired} 条` },
              { label: '归并后', value: data.clusters_total, hint: `多成员簇 ${data.clusters_multi} 个` },
              { label: '待复核', value: data.pending_total, hint: `历史结论 ${data.reviews_total} 条` },
            ],
      )}
      ${
        viewer
          ? ''
          : `<div class="panel-note" style="margin:0 var(--pad)">
              发布版本 v${publication?.version_no ?? '—'}：待复核 ${data.publish_stats?.pending ?? 0} · 可发布 ${data.publish_stats?.published ?? 0} · 已撤回 ${data.publish_stats?.withdrawn ?? 0}（过期 ${data.publish_stats?.expired ?? 0}）。
              客户视图与导出只含「可发布」。
            </div>`
      }

      <div class="grid-2">
        <section class="panel">
          ${sectionHead('02', '薪资口径分布', '算法 A')}
          <div class="panel-body">
            ${barList(
              data.salary_mix.map((item) => ({
                label: item.label,
                count: item.count,
                tone: { parsed: 'ok', negotiable: 'warn', unparsed: 'accent' }[item.key] || '',
              })),
            )}
            <div class="panel-note">
              已归一 ${salary.parsed} 条 · 面议 ${salary.negotiable} 条 · 不可比 ${salary.unparsed} 条；解析失败率 ${fmtPct(salary.fail_rate)}。
            </div>
          </div>
        </section>
        <section class="panel">
          ${sectionHead('03', '渠道来稿量', '原始计数')}
          <div class="panel-body">
            ${barList(data.channel_mix.map((item) => ({ label: item.name, count: item.count })))}
            <div class="panel-note">渠道配置与采集计划在「渠道与采集」版面维护，仅管理员可改。</div>
          </div>
        </section>
      </div>

      <div class="grid-2">
        <section class="panel">
          ${sectionHead('04', viewer ? '近 7 日发布节奏' : '近 7 日归并次数', 'runs / day')}
          <div class="panel-body">${trendChart(data.trend)}</div>
        </section>
        <section class="panel">
          ${sectionHead('05', viewer ? '当前发布版本' : '最新归并运行', viewer ? (publication ? `v${publication.version_no}` : '暂无') : latest ? latest.run_no : '暂无')}
          <div class="panel-body">${viewer ? publicationBlock(publication) : latestRunBlock(latest)}</div>
        </section>
      </div>

      <section class="panel">
        ${sectionHead('06', viewer ? '可检索岗位（节选）' : '成员最多的归并簇', viewer ? '当前发布版本 · 已脱敏' : 'golden record 已就位')}
        ${
          data.top_clusters.length
            ? table({
                rows: data.top_clusters,
                columns: [
                  {
                    key: 'company',
                    label: '公司 / 职位',
                    render: (row) => `<b>${esc(row.company)}</b><div class="cell-sub">${esc(row.title)}</div>`,
                  },
                  { key: 'city', label: '城市', className: 'tight' },
                  { key: 'monthly_median', label: '月薪中位', className: 'num', render: (row) => fmtMoney(row.monthly_median) },
                  { key: 'member_count', label: '成员 / 渠道', className: 'num', render: (row) => `${row.member_count} / ${row.channel_count}` },
                  { key: 'confidence', label: '置信度', className: 'num', render: (row) => Number(row.confidence).toFixed(3) },
                  { key: 'status_label', label: '状态', render: (row) => clusterStatusBadge(row) },
                ],
              })
            : emptyState({
                title: viewer ? '暂无已发布的岗位' : '还没有归并结果',
                hint: viewer ? '当前发布版本里还没有已审核通过的岗位。' : '先发起一次归并。',
              })
        }
        ${
          can(ctx.user.role, 'cluster:read')
            ? `<div class="panel-note">${
                viewer
                  ? '客户视图仅展示已审核通过、未过期的岗位；公司名已脱敏。'
                  : '点击任一行可跳到「归并结果」查看成员对照与复核。'
              }</div>`
            : ''
        }
      </section>`;
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        location.hash = '#/clusters';
      });
    });
  },
};

export default overviewPage;
