import { api } from '../api.js';
import { ENUMS, can } from '../config.js';
import { bindFilters, filterBar, sectionHead } from '../components.js';
import { drawer, emptyState, errorBox, errorMessage, esc, field, fmtTime, kv, table, toast } from '../ui.js';

const state = { q: '', kind: '', enabled: '' };

function openChannel(ctx, channel, reload) {
  const editable = can(ctx.user.role, 'channel:write');
  const { root, close } = drawer({
    title: channel.name,
    subtitle: `${channel.code} · ${channel.kind_label} · 采集计划 ${channel.crawl_cron}`,
    body: `${kv([
      ['渠道编码', `<span class="mono">${esc(channel.code)}</span>`],
      ['接入方式', esc(channel.kind_label)],
      ['采集入口', channel.endpoint ? `<span class="mono">${esc(channel.endpoint)}</span>` : '—'],
      ['采集计划', `<span class="mono">${esc(channel.crawl_cron)}</span>`],
      ['已入库岗位', `${channel.post_count} 条（含过期 ${channel.expired_count} 条）`],
      ['最近采集', fmtTime(channel.last_crawled_at)],
      ['负责人', esc(channel.owner)],
      ['状态', channel.enabled ? '<span class="badge ok">启用</span>' : '<span class="badge warn">停用</span>'],
      ['备注', esc(channel.note || '—')],
    ])}
    <div class="panel-note">停用后该渠道的原始岗位不参与下一次归并（历史簇保留）。</div>`,
    footer: editable
      ? `<div style="display:flex;gap:8px">
          <button class="btn ghost" data-toggle>${channel.enabled ? '停用该渠道' : '重新启用'}</button>
          <button class="btn ghost" data-close>关闭</button>
        </div>`
      : '<span class="mono muted">只读角色仅可查看渠道配置</span>',
  });
  root.querySelector('[data-toggle]')?.addEventListener('click', async () => {
    try {
      await api.patch(`/api/channels/${channel.id}`, { enabled: !channel.enabled });
      toast(channel.enabled ? '渠道已停用' : '渠道已启用');
      close();
      await reload();
    } catch (err) {
      toast(errorMessage(err), 'err');
    }
  });
}

function openCreate(ctx, reload) {
  const { root, close } = drawer({
    title: '登记采集渠道',
    subtitle: '一次登记，后续归并都按这份采集计划取数',
    body: `<form id="channel-form" style="display:grid;gap:12px">
      ${field({ label: '渠道编码（小写字母/数字）', name: 'code', placeholder: 'ganji' })}
      ${field({ label: '渠道名称', name: 'name', placeholder: '赶集网 · 主站' })}
      ${field({
        label: '接入方式',
        name: 'kind',
        value: 'site',
        options: Object.entries(ENUMS.channelKind).map(([value, label]) => ({ value, label })),
      })}
      ${field({ label: '采集计划（5 段 cron）', name: 'crawl_cron', value: '0 9 * * *' })}
      ${field({ label: '采集入口', name: 'endpoint', placeholder: 'https://…' })}
      ${field({ label: '备注', name: 'note' })}
      <div class="form-error" id="channel-error"></div>
      <button class="btn accent" type="submit">保存渠道</button>
    </form>`,
  });
  root.querySelector('#channel-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.target;
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    try {
      await api.post('/api/channels', {
        code: form.code.value.trim(),
        name: form.name.value.trim(),
        kind: form.kind.value,
        crawl_cron: form.crawl_cron.value.trim(),
        endpoint: form.endpoint.value.trim() || null,
        note: form.note.value.trim() || null,
      });
      toast('渠道已登记');
      close();
      await reload();
    } catch (err) {
      root.querySelector('#channel-error').textContent =
        err.code === 'CONFLICT' ? '渠道编码已存在，请换一个' : errorMessage(err);
      button.disabled = false;
    }
  });
}

export const channelsPage = {
  async render(view, ctx) {
    const render = () => channelsPage.render(view, ctx);
    let data;
    try {
      data = await api.get('/api/channels', { q: state.q, kind: state.kind, enabled: state.enabled });
    } catch (err) {
      view.innerHTML = errorBox(errorMessage(err));
      view.querySelector('#retry-btn')?.addEventListener('click', render);
      return;
    }
    const activeCron = data.items.filter((item) => item.enabled).length;
    view.innerHTML = `
      <section class="panel">
        ${sectionHead('02', '渠道与采集任务', `${data.total} 个渠道 · ${activeCron} 个在采集`)}
        <div class="panel-body">
          ${filterBar({
            fields: [
              { label: '搜索', name: 'q', value: state.q, placeholder: '名称 / 编码', grow: true },
              {
                label: '接入方式',
                name: 'kind',
                value: state.kind,
                options: [{ value: '', label: '全部' }, ...Object.entries(ENUMS.channelKind).map(([value, label]) => ({ value, label }))],
              },
              {
                label: '状态',
                name: 'enabled',
                value: state.enabled,
                options: [
                  { value: '', label: '全部' },
                  { value: 'true', label: '启用' },
                  { value: 'false', label: '停用' },
                ],
              },
            ],
            actions: can(ctx.user.role, 'channel:write')
              ? '<button class="btn sm accent" id="new-channel">登记采集渠道</button>'
              : '',
          })}
        </div>
        ${
          data.items.length
            ? table({
                rows: data.items,
                columns: [
                  { key: 'code', label: '编码', className: 'mono' },
                  { key: 'name', label: '渠道名称', render: (row) => `<b>${esc(row.name)}</b>` },
                  { key: 'kind_label', label: '接入方式', className: 'tight' },
                  { key: 'crawl_cron', label: '采集计划', className: 'mono' },
                  { key: 'post_count', label: '已入库', className: 'num' },
                  { key: 'expired_count', label: '含过期', className: 'num' },
                  { key: 'last_crawled_at', label: '最近采集', render: (row) => fmtTime(row.last_crawled_at) },
                  {
                    key: 'enabled',
                    label: '状态',
                    render: (row) => (row.enabled ? '<span class="badge ok">启用</span>' : '<span class="badge warn">停用</span>'),
                  },
                ],
              })
            : emptyState({ title: '还没有登记渠道', hint: '管理员可以登记第一个采集渠道。' })
        }
        <div class="panel-note">点击任一行查看采集入口、已入库量与最近采集时间；停用后不参与下一次归并。</div>
      </section>`;

    bindFilters(view, (values) => {
      state.q = values.q || '';
      state.kind = values.kind || '';
      state.enabled = values.enabled || '';
      render();
    });
    view.querySelectorAll('table.data tbody tr').forEach((row) => {
      row.addEventListener('click', () => {
        const channel = data.items.find((item) => String(item.id) === row.dataset.id);
        if (channel) openChannel(ctx, channel, render);
      });
    });
    view.querySelector('#new-channel')?.addEventListener('click', () => openCreate(ctx, render));
  },
};

export default channelsPage;
