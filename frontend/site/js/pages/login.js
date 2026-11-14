import { api } from '../api.js';
import { session } from '../store.js';
import { BRAND } from '../config.js';
import { errorMessage, esc, toast } from '../ui.js';

export const loginPage = {
  async render(root, ctx) {
    root.className = 'login-host';
    root.innerHTML = `
      <div class="login">
        <section class="login-brief">
          <div class="masthead-line">
            <b>云雀岗位归并台</b>
            <span>${esc(BRAND.edition)} · ${esc(BRAND.issue)}</span>
          </div>
          <div class="kicker">招聘版面 · 岗位归并版</div>
          <h1>${esc(BRAND.title)}<br /><em>每日取报</em></h1>
          <p class="tagline">${esc(BRAND.loginLead)}</p>
          <div class="lead-columns">
            ${BRAND.loginColumns.map((text) => `<p>${esc(text)}</p>`).join('')}
          </div>
          <div class="brief-points">
            ${BRAND.loginPoints
              .map(([no, text]) => `<div class="brief-point"><i>${esc(no)}</i><span>${esc(text)}</span></div>`)
              .join('')}
          </div>
          <div class="eyebrow">${esc(BRAND.org)} · 内部取报窗口</div>
        </section>
        <section class="login-form-wrap">
          <div class="coupon">
            <div class="coupon-head">
              <div class="brand">取 报 单</div>
              <div class="sub">SUBSCRIPTION · 岗位运营组</div>
            </div>
            <form class="login-card" id="login-form" novalidate>
              <div class="field">
                <label for="email">邮箱</label>
                <input id="email" name="email" type="email" autocomplete="username" value="admin@${esc(BRAND.short)}.io" required />
              </div>
              <div class="field">
                <label for="password">密码</label>
                <input id="password" name="password" type="password" autocomplete="current-password" value="Demo@2026" required />
              </div>
              <div class="form-error" id="login-error" role="alert"></div>
              <button class="btn accent" id="login-submit" type="submit">取今日岗位归并版</button>
              <div class="login-hint">
                演示账号（密码 Demo@2026）<br />
                admin@${esc(BRAND.short)}.io · 管理员（渠道 / 阈值 / 导出 / 审计）<br />
                analyst@${esc(BRAND.short)}.io · 运营专员（归并 / 复核）<br />
                viewer@${esc(BRAND.short)}.io · 客户只读（公司名脱敏）
              </div>
            </form>
          </div>
        </section>
      </div>`;

    const form = root.querySelector('#login-form');
    const errorNode = root.querySelector('#login-error');
    const submit = root.querySelector('#login-submit');
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      errorNode.textContent = '';
      submit.disabled = true;
      submit.textContent = '正在核对订阅信息…';
      try {
        const result = await api.post('/api/auth/login', {
          email: form.email.value.trim(),
          password: form.password.value,
        });
        session.set(result.access_token, result.user);
        toast(`欢迎回来，${result.user.display_name}`);
        location.hash = '#/overview';
        await ctx.reload();
      } catch (err) {
        errorNode.textContent = err.code === 'AUTH_INVALID' ? '账号或密码不正确' : errorMessage(err);
      } finally {
        submit.disabled = false;
        submit.textContent = '取今日岗位归并版';
      }
    });
  },
};

export default loginPage;
