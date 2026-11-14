import { api } from './api.js';
import { BRAND, NAV, ROLE_LABELS, ROLE_NOTES, can } from './config.js';
import { session } from './store.js';
import { errorMessage, esc, toast } from './ui.js';
import loginPage from './pages/login.js';
import overviewPage from './pages/overview.js';
import channelsPage from './pages/channels.js';
import postsPage from './pages/posts.js';
import clustersPage from './pages/clusters.js';
import reviewsPage from './pages/reviews.js';

const routes = [
  { path: '#/overview', page: overviewPage, permission: 'overview:read' },
  { path: '#/channels', page: channelsPage, permission: 'channel:read' },
  { path: '#/posts', page: postsPage, permission: 'post:read' },
  { path: '#/clusters', page: clustersPage, permission: 'cluster:read' },
  { path: '#/reviews', page: reviewsPage, permission: 'cluster:read' },
];

let currentUser = null;
let listening = false;

function setActiveNav(path) {
  document.querySelectorAll('.rail nav a').forEach((link) => {
    link.classList.toggle('active', link.getAttribute('href') === path);
  });
}

function forbidden(view, ctx) {
  view.innerHTML = `<section class="panel"><div class="empty" data-testid="forbidden">
    <div class="mark">本版不向该角色开放</div>
    <p>当前角色是「${esc(ROLE_LABELS[ctx.user.role] || ctx.user.role)}」，这个版面需要更高权限。</p>
    <button class="btn ghost" data-back>回到头版</button>
  </div></section>`;
  view.querySelector('[data-back]')?.addEventListener('click', () => {
    location.hash = '#/overview';
  });
}

async function renderLogin() {
  currentUser = null;
  const root = document.getElementById('app');
  root.className = '';
  await loginPage.render(root, { reload: boot });
}

async function renderRoute() {
  const view = document.getElementById('view');
  if (!view || !currentUser) return;
  const raw = location.hash || '#/overview';
  const [path, qs] = raw.split('?');
  const query = Object.fromEntries(new URLSearchParams(qs || ''));
  if (path === '#/login') {
    session.clear();
    return renderLogin();
  }
  const route = routes.find((item) => item.path === path) || routes[0];
  if (!can(currentUser.role, route.permission)) {
    setActiveNav('');
    return forbidden(view, { user: currentUser });
  }
  setActiveNav(route.path);
  view.innerHTML = '<div class="empty"><div class="mark">排字中…</div></div>';
  const ctx = {
    user: currentUser,
    query,
    navigate: (hash) => {
      location.hash = hash;
    },
    reload: boot,
    logout,
  };
  try {
    await route.page.render(view, ctx);
  } catch (err) {
    view.innerHTML = `<div class="error-box"><span>${esc(errorMessage(err))}</span><button class="btn sm ghost" data-retry>重试</button></div>`;
    view.querySelector('[data-retry]')?.addEventListener('click', () => renderRoute());
  }
}

function logout() {
  session.clear();
  toast('已退出登录');
  location.hash = '#/login';
  boot();
}

function renderShell() {
  const root = document.getElementById('app');
  root.className = '';
  const navItems = NAV.filter((item) => can(currentUser.role, item.permission));
  root.innerHTML = `
    <div class="shell">
      <aside class="rail">
        <div class="rail-mark">
          <b>${esc(BRAND.nameplate)}</b>
          <small>JOB MERGE · 版面导读</small>
        </div>
        <nav>
          ${navItems
            .map(
              (item) =>
                `<a href="${item.to}" data-nav="${item.to.replace('#/', '')}" data-testid="nav-${item.to.replace('#/', '')}"><i>${item.no}</i>${esc(item.label)}</a>`,
            )
            .join('')}
        </nav>
        <div class="rail-foot">
          <b>${esc(BRAND.org)}</b>
          <span>${esc(ROLE_LABELS[currentUser.role] || currentUser.role)} · ${esc(currentUser.display_name)}</span>
          <span class="mono" id="worker-state" data-testid="worker-state">后台归并 · 检测中</span>
          <button class="btn sm ghost" id="logout" style="margin-top:4px">退出登录</button>
        </div>
      </aside>
      <div class="main">
        <header class="topbar">
          <div>
            <div class="nameplate">云雀<em>岗位归并台</em></div>
            <h1>${esc(BRAND.title)}</h1>
            <div class="sub">${esc(BRAND.subtitle)}</div>
          </div>
          <div class="topbar-meta">
            <div class="who">
              <b data-testid="who-name">${esc(currentUser.display_name)}</b>
              <div class="tiny">${esc(currentUser.email)}</div>
              <div class="tiny">${esc(ROLE_NOTES[currentUser.role] || '')}</div>
            </div>
          </div>
        </header>
        <div class="topbar-rule"></div>
        <div class="dateline" style="margin:8px var(--pad) 0">
          <span>${esc(BRAND.edition)}</span>
          <span>${esc(BRAND.issue)}</span>
          <span id="masthead-stats">渠道 — / 来稿 — / 归并后 — / 待复核 —</span>
          <span class="spacer"></span>
          <span>内部工作台 · 每日 07:40 自动归并</span>
        </div>
        <section class="view" id="view"></section>
      </div>
    </div>`;
  root.querySelector('#logout')?.addEventListener('click', logout);
  api
    .get('/api/overview')
    .then((data) => {
      const worker = document.getElementById('worker-state');
      if (worker) worker.textContent = data.worker_alive ? '后台归并 · 在岗' : '后台归并 · 心跳超时';
      const stats = document.getElementById('masthead-stats');
      if (stats) {
        stats.textContent = `渠道 ${data.channels_enabled}/${data.channels_total} · 来稿 ${data.posts_total} 条 · 归并后 ${data.clusters_total} 簇 · 待复核 ${data.pending_total}`;
      }
    })
    .catch(() => {});
}

async function boot() {
  if (!listening) {
    window.addEventListener('hashchange', () => {
      if (!session.token()) return renderLogin();
      renderRoute();
    });
    listening = true;
  }
  if (!session.token()) return renderLogin();
  try {
    const me = await api.get('/api/auth/me');
    currentUser = me.user;
    session.setUser(me.user);
  } catch {
    session.clear();
    return renderLogin();
  }
  renderShell();
  await renderRoute();
}

boot();
