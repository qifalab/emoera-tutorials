/* ============================================================
   Emoera 前端 · 单文件应用
   - hash 路由：#/daily/*（每日速报）与 #/tutorial/*（教程平台）
   - 合并了原 switchbar.js / app.js / tutorial.js 的全部能力
   - 依赖后端 API（/api/v1/*），纯静态、零构建
   ============================================================ */
"use strict";

/* ---------------- 常量与工具 ---------------- */
const API_BASE = (() => {
  if (window.API_BASE_URL) return window.API_BASE_URL.replace(/\/$/, "");
  const host = window.location.hostname || "127.0.0.1";
  if (host === "localhost" || host === "127.0.0.1") return `http://${host}:8000`;
  return "http://127.0.0.1:8000";
})();

const $ = (id) => document.getElementById(id);
const on = (el, evt, fn) => { if (el) el.addEventListener(evt, fn); };

function escapeHtml(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function escapeAttr(s) { return escapeHtml(s).replace(/'/g, "&#39;"); }

/* 把正文里的 URL 自动转成可点击超链接（保留 https? 协议、保留 # 锚点），
   非 URL 文本仍走 escapeHtml 转义，防 XSS。 */
function linkify(text) {
  const esc = escapeHtml(text);
  // 匹配 http/https 开头的链接，含可选的 #fragment 锚点
  return esc.replace(
    /(https?:\/\/[^\s<>"'()]+)/gi,
    (url) => {
      // 剥掉可能被转义回来的 &amp;，还原为真实 URL 再放进 href
      const clean = url.replace(/&amp;/g, "&");
      return `<a href="${clean}" target="_blank" rel="noopener noreferrer" class="inline-link">${url}</a>`;
    }
  );
}

/* ---------------- Markdown 渲染管线 ----------------
   依赖 vendor：marked（解析）+ highlight.js（代码高亮）+ DOMPurify（XSS 过滤）。
   渲染策略：
   1. 用 marked 解析 Markdown → HTML；
   2. marked 的 renderer 里对代码块做高亮：优先用围栏指定的语言，未指定则用
      hljs.highlightAuto 自动识别语言；
   3. 整个 HTML 过一遍 DOMPurify（白名单）再插入 DOM，彻底防 XSS。
*/
/* 代码块可切换语言的下拉选项（与工具栏保持一致） */
const CODE_LANGS = [
  ["auto", "自动识别"],
  ["python", "Python"], ["javascript", "JavaScript"], ["typescript", "TypeScript"],
  ["java", "Java"], ["c", "C"], ["cpp", "C++"], ["csharp", "C#"],
  ["go", "Go"], ["rust", "Rust"], ["bash", "Bash"], ["sql", "SQL"],
  ["json", "JSON"], ["yaml", "YAML"], ["html", "HTML"], ["css", "CSS"],
  ["markdown", "Markdown"], ["plaintext", "纯文本"],
];

function mdRenderer() {
  const renderer = new marked.Renderer();
  renderer.code = function (code, lang) {
    const text = (code || "").replace(/\n$/, "");
    let highlighted = "";
    let usedLang = lang || "";
    if (window.hljs) {
      try {
        if (lang && hljs.getLanguage(lang)) {
          highlighted = hljs.highlight(text, { language: lang }).value;
        } else {
          // 未指定或未知语言：自动识别
          const auto = hljs.highlightAuto(text);
          highlighted = auto.value;
          usedLang = auto.language || lang || "";
        }
      } catch (e) {
        highlighted = escapeHtml(text);
      }
    } else {
      highlighted = escapeHtml(text);
    }
    const langOpts = CODE_LANGS.map(([v, n]) =>
      `<option value="${v}"${v === (usedLang || "auto") ? " selected" : ""}>${n}</option>`).join("");
    const langLabel = usedLang ? `<span class="code-lang">${escapeHtml(usedLang)}</span>` : "";
    return `<div class="code-block" data-raw="${escapeAttr(text)}"><div class="code-head">${langLabel}<select class="code-lang-select">${langOpts}</select><button class="code-copy" type="button">复制</button></div><pre><code>${highlighted}</code></pre></div>`;
  };
  return renderer;
}

function renderMarkdown(md) {
  if (!md) return "";
  // 安全兜底：marked 未加载时退回纯文本链接化（linkify 内部已 escapeHtml，
  // 只生成受控的 <a> 标签，绝对不注入原始 HTML，杜绝 XSS）。
  if (!window.marked) return linkify(md);
  let html = "";
  try {
    const renderer = mdRenderer();
    marked.setOptions({ renderer, breaks: true, gfm: true });
    html = marked.parse(md);
  } catch (e) {
    return linkify(md);
  }
  // XSS 过滤：允许图片、链接、代码块等安全标签；DOMPurify 缺失时退回纯文本。
  if (window.DOMPurify) {
    html = DOMPurify.sanitize(html, {
      ADD_ATTR: ["target", "rel"],
      ALLOW_DATA_ATTR: false,
    });
  } else {
    // DOMPurify 也未加载：任何 markdown HTML 都不可信，退回纯文本链接化，宁缺毋滥。
    return linkify(md);
  }
  // 正文中相对路径图片（如 /uploads/xxx.png）补全为后端地址，修复显示失败
  return absolutizeImages(html);
}

/* 为渲染后的 HTML 绑定交互（代码块复制按钮 + 语言切换） */
function bindRenderedContent(root) {
  if (!root) return;
  root.querySelectorAll(".code-copy").forEach((btn) => {
    btn.addEventListener("click", () => {
      const code = btn.closest(".code-block").querySelector("code");
      if (!code) return;
      const text = code.innerText;
      (navigator.clipboard ? navigator.clipboard.writeText(text) : Promise.reject())
        .then(() => { btn.textContent = "已复制"; setTimeout(() => { btn.textContent = "复制"; }, 1200); })
        .catch(() => {
          // 回退方案
          const ta = document.createElement("textarea");
          ta.value = text; document.body.appendChild(ta); ta.select();
          try { document.execCommand("copy"); btn.textContent = "已复制"; setTimeout(() => { btn.textContent = "复制"; }, 1200); } catch (e) {}
          ta.remove();
        });
    });
  });
  // 语言切换：手动改代码块高亮语言
  root.querySelectorAll(".code-lang-select").forEach((sel) => {
    sel.addEventListener("change", () => {
      const block = sel.closest(".code-block");
      const codeEl = block.querySelector("code");
      const raw = block.dataset.raw || "";
      const lang = sel.value;
      let html = "";
      if (window.hljs) {
        try {
          if (lang === "plaintext") {
            html = escapeHtml(raw);
          } else if (lang === "auto") {
            html = hljs.highlightAuto(raw).value;
          } else if (hljs.getLanguage(lang)) {
            html = hljs.highlight(raw, { language: lang }).value;
          } else {
            html = hljs.highlightAuto(raw).value;
          }
        } catch (e) { html = escapeHtml(raw); }
      } else {
        html = escapeHtml(raw);
      }
      codeEl.innerHTML = html;
      const label = block.querySelector(".code-lang");
      if (label) {
        if (lang === "auto") {
          const auto = window.hljs ? hljs.highlightAuto(raw).language || "" : "";
          label.textContent = auto || "auto";
        } else if (lang === "plaintext") {
          label.textContent = "text";
        } else {
          label.textContent = lang;
        }
      }
    });
  });
}

/* 列表卡片用：把 Markdown 压成纯文本摘要（去掉语法符号），
   避免在列表里渲染完整 HTML + 代码高亮，性能更好、更干净。 */
function mdExcerpt(md, maxLen = 120) {
  if (!md) return "";
  let text = String(md)
    .replace(/```[\s\S]*?```/g, " [代码块] ")   // 代码块折叠
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, " [图片] ") // 图片折叠
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")   // 链接留文字
    .replace(/[#>*_`~|]/g, "")                 // 去掉 Markdown 符号
    .replace(/\s+/g, " ")
    .trim();
  if (text.length > maxLen) text = text.slice(0, maxLen) + "…";
  return escapeHtml(text);
}

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d)) return "";
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function fmtSize(n) {
  n = Number(n) || 0;
  if (n >= 1e6) return (n / 1e6).toFixed(1) + " MB";
  if (n >= 1e3) return (n / 1e3).toFixed(1) + " KB";
  return n + " B";
}
function fmtCount(n) {
  n = Number(n) || 0;
  if (n >= 1e6) return (n / 1e6).toFixed(1).replace(/\.0$/, "") + "M";
  if (n >= 1e3) return (n / 1e3).toFixed(1).replace(/\.0$/, "") + "k";
  return String(n);
}

/* 媒体 URL 补全：把相对路径（/uploads/xxx）补成可访问的后端绝对地址。
   前端零构建、与后端跨端口部署时，相对路径会 404——这是教程页图片显示失败的主因。 */
function resolveMediaUrl(u) {
  const s = String(u || "").trim();
  if (!s) return "";
  if (/^(https?:)?\/\//i.test(s)) return s;       // 已绝对
  if (s.startsWith("/uploads/")) return API_BASE + "/uploads/inline/" + s.slice("/uploads/".length); // 位图走内联预览
  if (s.startsWith("/")) return API_BASE + s;      // 根相对路径 → 拼后端
  return s;
}

/* 把渲染后 HTML 里的相对路径 img src 补全为后端地址（DOMPurify 过滤之后做）。 */
function absolutizeImages(html) {
  if (!html || typeof html !== "string") return html;
  return html.replace(/<img\b[^>]*\bsrc="([^"]+)"/gi, (whole, src) => {
    if (/^(https?:)?\/\//i.test(src) || src.startsWith("data:")) return whole;
    if (src.startsWith("/uploads/")) return whole.replace(src, API_BASE + "/uploads/inline/" + src.slice("/uploads/".length));
    if (src.startsWith("/")) return whole.replace(src, API_BASE + src);
    return whole;
  });
}

/* ---------------- 会话 ---------------- */
const USER_KEY = "emoera_user";
/* 安全：令牌不再存 localStorage（XSS 可被窃取）。
   登录时后端会写 httpOnly Cookie，前端所有请求由统一 fetch 包装自动携带。
   这里仅保留用户信息用于界面展示（用户名/头像/角色），不包含任何凭证。 */
const getToken = () => "";
const getUser = () => { try { return JSON.parse(localStorage.getItem(USER_KEY) || "null"); } catch { return null; } };
const setSession = (t, u) => { if (u) localStorage.setItem(USER_KEY, JSON.stringify(u)); };
const clearSession = () => { localStorage.removeItem(USER_KEY); };
const authHeaders = (extra = {}) => ({ "Content-Type": "application/json", ...extra });
const requireLogin = () => { alert("请先登录"); location.hash = "#/tutorial/login"; };

/* 统一 fetch 包装：
   1. 自动携带 httpOnly Cookie（credentials:include，跨域凭据）
   2. 极度向后兼容：若 localStorage 存有旧 token 也带上（迁移期兜底）
   所有业务代码继续直接调用全局 fetch，无需改动。 */
(function wrapFetch() {
  const legacyToken = localStorage.getItem("emoera_token") || "";
  const _orig = window.fetch.bind(window);
  window.fetch = (url, opts = {}) => {
    const o = { ...opts, credentials: "include" };
    if (legacyToken) {
      const h = { ...(opts.headers || {}) };
      if (!h["Authorization"]) h["Authorization"] = "Bearer " + legacyToken;
      o.headers = h;
    }
    return _orig(url, o);
  };
})();

function avatarChar(u) { return (u || "?").slice(0, 1).toUpperCase(); }
function avatarHue(u) {
  let h = 0;
  for (const ch of String(u || "")) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

/* ---------------- 主题 ---------------- */
function applyTheme() {
  const dark = document.documentElement.dataset.theme === "dark";
  const btn = $("themeBtn");
  if (btn) btn.textContent = dark ? "☀️" : "🌙";
  // 同步代码高亮主题（github 浅色 / github-dark 暗色）
  const light = $("hljsLight");
  const darkCss = $("hljsDark");
  if (light && darkCss) {
    light.disabled = dark;
    darkCss.disabled = !dark;
  }
}
function toggleTheme() {
  const dark = document.documentElement.dataset.theme === "dark";
  document.documentElement.dataset.theme = dark ? "light" : "dark";
  localStorage.setItem("emoera-theme", dark ? "light" : "dark");
  applyTheme();
}

/* ---------------- 路由与导航 ---------------- */
const NAV = {
  daily: [
    { path: "home", label: "首页", icon: "🏠" },
    { path: "news", label: "时事", icon: "🗞️" },
    { path: "world", label: "世界", icon: "🌍" },
    { path: "meme", label: "新梗", icon: "😂" },
    { path: "cloud", label: "云厂商", icon: "☁️" },
    { path: "cloud_native", label: "云原生", icon: "⚙️" },
    { path: "ai_cloud", label: "AI上云", icon: "🤖" },
    { path: "ai_models", label: "AI模型", icon: "🧠" },
  ],
  tutorial: [
    { path: "platform", label: "平台首页", icon: "🏠" },
    { path: "resources", label: "资源中心", icon: "📚" },
    { path: "upload", label: "上传资源", icon: "⬆️" },
    { path: "favorites", label: "我的收藏", icon: "⭐" },
    { path: "my_resources", label: "我的上传", icon: "📁" },
  ],
};

const SECTION_MAP = {
  news: ["news"], world: ["world"], meme: ["meme_cn", "meme_global"],
  cloud: ["cloud_vendor"], cloud_native: ["cloud_native"], ai_cloud: ["ai_cloud"],
};
const CAT_META = {
  news: { icon: "🗞️" }, world: { icon: "🌍" },
  meme_cn: { icon: "🇨🇳" }, meme_global: { icon: "🌐" },
  cloud_vendor: { icon: "☁️" }, cloud_native: { icon: "⚙️" }, ai_cloud: { icon: "🤖" },
};
const HOME_ENTRIES = [
  ["news", "🗞️", "今日时事", "知乎日报 · 36氪 · 澎湃 · Google 新闻中文"],
  ["world", "🌍", "世界动态", "BBC · NYT · Reuters · Google News"],
  ["meme", "😂", "近日新梗", "国内 + 国外，梗图与热词一网打尽"],
  ["cloud", "☁️", "云服务厂商日报", "AWS · Azure · 阿里云 · 谷歌云 · Cloudflare"],
  ["cloud_native", "⚙️", "云原生 & 开源热榜", "Kubernetes · CNCF · Serverless · 开源基础设施"],
  ["ai_cloud", "🤖", "AI 上云动态", "OpenAI · Hugging Face · 通义 · Mistral"],
  ["ai_models", "🧠", "AI 模型推荐", "CivitAI 生图 · HF 大模型 · 各类 AI 资源站"],
];

function parseHash() {
  const raw = (location.hash || "#/daily/home").replace(/^#/, "");
  const [pathPart, queryPart] = raw.split("?");
  const seg = (pathPart || "/daily/home").split("/").filter(Boolean);
  const board = seg[0] || "daily";
  const page = seg[1] || (board === "daily" ? "home" : "platform");
  const query = new URLSearchParams(queryPart || "");
  return { board, page, query };
}

function renderHeader(state) {
  document.querySelectorAll(".board-tab").forEach((a) => {
    a.classList.toggle("active", a.dataset.board === state.board);
  });
  const pills = $("navPills");
  const items = NAV[state.board] || NAV.daily;
  if (pills) {
    // 方形紧凑按钮置顶：当前展示页面对应按钮变蓝（bg-primary → 这里用 active 高亮）
    pills.innerHTML = items.map((it) => {
      const active = state.page === it.path;
      return `<a class="nav-pill${active ? " active" : ""}" href="#/${state.board}/${it.path}" data-nav="${it.path}" role="tab" aria-selected="${active}">
        <span class="nav-pill-icon">${it.icon}</span><span class="nav-pill-label">${it.label}</span></a>`;
    }).join("");
  }
  const area = $("userArea");
  if (area) {
    const u = getUser();
    if (u) {
      const hue = avatarHue(u.username);
      area.innerHTML = `<a class="nav-user" href="#/tutorial/profile" title="个人中心">
        <span class="nav-avatar" style="background:hsl(${hue},62%,52%)">${escapeHtml(avatarChar(u.username))}</span>
        <span class="nav-username">${escapeHtml(u.username)}</span></a>`;
      const nb = $("notifyBtn");
      if (nb) { nb.style.display = ""; pollUnread(); }
    } else {
      area.innerHTML = `<a class="btn btn-ghost btn-sm" href="#/tutorial/login">🔑 登录</a>`;
      const nb = $("notifyBtn");
      if (nb) { nb.style.display = "none"; }
    }
  }
  const g = $("generatedAt");
  if (g) g.textContent = "";
  bindHeaderExtras();
}

/* 通知角标轮询 */
let _unreadTimer = null;
async function pollUnread() {
  if (!getUser()) return;
  try {
    const res = await fetch(`${API_BASE}/api/v1/notifications/unread-count`);
    if (!res.ok) return;
    const data = await res.json();
    const badge = $("notifyBadge");
    if (badge) {
      badge.textContent = data.unread > 99 ? "99+" : String(data.unread);
      badge.hidden = data.unread <= 0;
    }
  } catch (e) { /* 忽略 */ }
}

function bindHeaderExtras() {
  const notifyBtn = $("notifyBtn");
  on(notifyBtn, "click", () => { location.hash = "#/tutorial/notifications"; });

  const input = $("globalSearchInput");
  const suggest = $("globalSearchSuggest");
  if (!input) return;
  let debounce = null;
  on(input, "input", () => {
    clearTimeout(debounce);
    const q = input.value.trim();
    if (!q) { if (suggest) suggest.hidden = true; return; }
    debounce = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/v1/resources/search?q=${encodeURIComponent(q)}&sort=hottest`);
        if (!res.ok) return;
        const data = await res.json();
        if (!suggest) return;
        if (!data.length) {
          suggest.innerHTML = `<div class="ss-empty">未找到“${escapeHtml(q)}”相关资源</div>`;
        } else {
          suggest.innerHTML = data.slice(0, 8).map((r) =>
            `<a class="ss-item" href="#/tutorial/resource?id=${escapeAttr(r.id)}">
              <span class="ss-title">${escapeHtml(r.title)}</span>
              <span class="ss-cat">${escapeHtml(r.category || "教程")}</span>
            </a>`).join("") +
            `<a class="ss-more" href="#/tutorial/search?q=${encodeURIComponent(q)}">查看全部结果 →</a>`;
        }
        suggest.hidden = false;
      } catch (e) { /* 忽略 */ }
    }, 220);
  });
  on(input, "keydown", (e) => {
    if (e.key === "Enter") {
      const q = input.value.trim();
      if (q) { if (suggest) suggest.hidden = true; location.hash = `#/tutorial/search?q=${encodeURIComponent(q)}`; }
    }
  });
  document.addEventListener("click", (e) => {
    if (suggest && !suggest.contains(e.target) && e.target !== input) suggest.hidden = true;
  });
}

/* ---------------- 视图：速报 ---------------- */
function renderDailyHome() {
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">每日速读 · AI 聚合</h1>
      <p class="hero-sub">时事、世界、新梗、云——七大频道，分国内 / 国外，随你看。</p>
    </section>
    <div class="entry-grid">
      ${HOME_ENTRIES.map(([p, icon, title, desc]) =>
        `<a class="entry-card" href="#/daily/${p}">
          <span class="entry-icon">${icon}</span>
          <h3>${title}</h3>
          <p>${desc}</p>
        </a>`).join("")}
    </div>
  </div>`;
}

function renderItems(items, key) {
  if (!items || !items.length) return `<li class="item-empty">该板块暂无条目。</li>`;
  return items.map((item, i) => {
    const hasUrl = !!(item.url && String(item.url).trim());
    const safeUrl = escapeAttr(item.url || "");
    const sourceNode = item.source
      ? (hasUrl
          ? `<a class="item-source" href="${safeUrl}" target="_blank" rel="noopener">🔗 ${escapeHtml(item.source)}</a>`
          : `<span class="item-source">🔗 ${escapeHtml(item.source)}</span>`)
      : "";
    const timeNode = item.published_at ? `<span>${escapeHtml(fmtTime(item.published_at).slice(5))}</span>` : "";
    const metaInner = [sourceNode, timeNode].filter(Boolean).join('<span class="dot"></span>');
    const tags = (item.tags || []).map((t) => `<span class="tag">#${escapeHtml(t)}</span>`).join("");
    const summary = item.summary ? `<div class="item-summary">${escapeHtml(item.summary)}</div>` : "";
    const aiSummary = item.summary_ai
      ? `<div class="item-ai"><span class="item-ai-badge">🤖 AI 总结</span><span class="item-ai-text">${escapeHtml(item.summary_ai)}</span></div>`
      : "";
    const refNode = hasUrl
      ? `<a class="item-ref" href="${safeUrl}" target="_blank" rel="noopener">查看引用 / 原文 ↗</a>`
      : (item.source ? `<span class="item-ref-static">引用来源：${escapeHtml(item.source)}</span>` : "");
    return `<li class="item" data-url="${safeUrl}">
      <span class="item-rank">${i + 1}</span>
      <div class="item-body">
        <div class="item-title">${escapeHtml(item.title)}</div>
        ${metaInner ? `<div class="item-meta">${metaInner}</div>` : ""}
        ${summary}${aiSummary}
        ${tags ? `<div class="item-tags">${tags}</div>` : ""}
        ${refNode ? `<div class="item-ref-row">${refNode}</div>` : ""}
      </div>
    </li>`;
  }).join("");
}

function renderSectionCard(sec) {
  const meta = CAT_META[sec.key] || { icon: "📌" };
  const summary = sec.summary ? `<div class="section-summary">${escapeHtml(sec.summary)}</div>` : "";
  return `<section class="section-card">
    <div class="section-head">
      <span class="section-icon">${meta.icon}</span>
      <h2 class="section-title">${escapeHtml(sec.title)}</h2>
      <span class="section-count">${(sec.items || []).length} 条</span>
    </div>
    ${summary}
    <ul class="item-list">${renderItems(sec.items, sec.key)}</ul>
  </section>`;
}

function renderLoader(text = "正在加载…") {
  return `<div class="loading"><div class="spinner"></div><p>${escapeHtml(text)}</p></div>`;
}

let currentPage = null;

function renderSectionPage(title, sub, cats) {
  currentPage = { type: "section", cats };
  return `<div class="page">
    <section class="hero hero-row">
      <div>
        <h1 class="hero-title">${title}</h1>
        <p class="hero-sub">${sub}</p>
      </div>
      <button class="btn btn-primary" id="refreshBtn">🔄 刷新</button>
    </section>
    <div id="statusBar"></div>
    <div id="sections" class="sections">${renderLoader()}</div>
  </div>`;
}

async function loadSectionPage(refresh = false) {
  const { cats } = currentPage || { cats: [] };
  const sections = $("sections");
  if (!sections || !cats.length) return;
  sections.innerHTML = renderLoader(refresh ? "正在重新抓取并生成速报…" : "正在加载…");
  try {
    const results = await Promise.all(cats.map(async (c) => {
      const res = await fetch(`${API_BASE}/api/v1/news/section/${c}${refresh ? "?refresh=true" : ""}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    }));
    sections.innerHTML = results.map(renderSectionCard).join("");
  } catch (err) {
    sections.innerHTML = `<div class="empty"><p>⚠️ 无法连接后端（${escapeHtml(String(err.message))}）</p>
      <p style="margin-top:8px;font-size:13px">请确认后端已在 ${escapeHtml(API_BASE)} 启动。</p></div>`;
  }
}
/* ---------------- 视图：AI 模型推荐 ---------------- */
function renderModelItem(item, i) {
  const safeUrl = escapeAttr(item.url || "");
  const hasUrl = !!safeUrl;
  const img = item.image_url
    ? `<div class="model-thumb"><img loading="lazy" src="${escapeAttr(resolveMediaUrl(item.image_url))}" alt="${escapeAttr(item.name)}" referrerpolicy="no-referrer" onerror="this.parentNode.style.display='none'" /></div>`
    : "";
  const stats = [
    item.downloads ? `<span title="下载量">⬇️ ${fmtCount(item.downloads)}</span>` : "",
    item.likes ? `<span title="点赞">❤️ ${fmtCount(item.likes)}</span>` : "",
    item.updated_at ? `<span title="更新时间">🕒 ${escapeHtml(item.updated_at)}</span>` : "",
  ].filter(Boolean).join('<span class="dot"></span>');
  const tags = (item.tags || []).map((t) => `<span class="tag">#${escapeHtml(t)}</span>`).join("");
  const sourceNode = item.source ? `<span class="model-source">🔗 ${escapeHtml(item.source)}</span>` : "";
  const refNode = hasUrl ? `<a class="item-ref" href="${safeUrl}" target="_blank" rel="noopener">前往下载 / 查看 ↗</a>` : "";
  return `<li class="model-card" data-url="${safeUrl}">
    ${img}
    <div class="model-body">
      <div class="model-title">${escapeHtml(item.name)}</div>
      ${item.description ? `<div class="model-desc">${escapeHtml(item.description)}</div>` : ""}
      <div class="item-meta">${sourceNode}${stats ? '<span class="dot"></span>' + stats : ""}</div>
      ${tags ? `<div class="item-tags">${tags}</div>` : ""}
      ${refNode ? `<div class="item-ref-row">${refNode}</div>` : ""}
    </div>
  </li>`;
}

function renderModelSection(sec) {
  const cards = (sec.items || []).map(renderModelItem).join("") || `<li class="item-empty">该板块暂无内容。</li>`;
  const summary = sec.summary ? `<div class="section-summary">${escapeHtml(sec.summary)}</div>` : "";
  return `<section class="section-card">
    <div class="section-head">
      <span class="section-icon">🧩</span>
      <h2 class="section-title">${escapeHtml(sec.title)}</h2>
      <span class="section-count">${(sec.items || []).length} 个</span>
    </div>
    ${summary}
    <ul class="model-grid">${cards}</ul>
  </section>`;
}

function renderAiModelsPage() {
  currentPage = { type: "ai_models" };
  return `<div class="page">
    <section class="hero hero-row">
      <div>
        <h1 class="hero-title">🧠 AI 模型推荐</h1>
        <p class="hero-sub">CivitAI 生图 · Hugging Face 大模型 · 各类 AI 资源站</p>
      </div>
      <button class="btn btn-primary" id="refreshBtn">🔄 刷新</button>
    </section>
    <div id="statusBar"></div>
    <div id="sections" class="sections">${renderLoader()}</div>
  </div>`;
}

async function loadAiModelsPage(refresh = false) {
  const sections = $("sections");
  const status = $("statusBar");
  if (!sections) return;
  if (status) status.innerHTML = "";
  sections.innerHTML = renderLoader(refresh ? "正在重新抓取今日最火模型…" : "正在加载…");
  try {
    const res = await fetch(`${API_BASE}/api/v1/ai-models${refresh ? "?refresh=true" : ""}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    sections.innerHTML = (data.sections || []).map(renderModelSection).join("");
    if (status && data.note) status.innerHTML = `<div class="status-bar">ℹ️ ${escapeHtml(data.note)}</div>`;
  } catch (err) {
    sections.innerHTML = `<div class="empty"><p>⚠️ 无法连接后端（${escapeHtml(String(err.message))}）</p>
      <p style="margin-top:8px;font-size:13px">请确认后端已在 ${escapeHtml(API_BASE)} 启动。</p></div>`;
  }
}
/* ---------------- 视图：教程平台 ---------------- */
function renderPlatformHome() {
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">教程平台</h1>
      <p class="hero-sub">任何人都能上传教程 / 模型 / 资料，管理员审核通过后对所有人可见。</p>
    </section>
    <section class="block">
      <div class="block-head">
        <h2>📰 每日速报</h2>
        <span class="block-sub">时事 / 世界 / 新梗 / AI 模型，点开即看</span>
      </div>
      <div class="chip-row">
        ${HOME_ENTRIES.map(([p, icon, title]) => `<a class="channel-chip" href="#/daily/${p}">${icon} ${title}</a>`).join("")}
      </div>
    </section>
    <section class="block">
      <div class="block-head">
        <h2>📚 资源中心</h2>
        <span class="block-sub">用户上传、管理员审核后公开可见</span>
      </div>
      <div class="entry-grid" style="margin-top:16px">
        <a class="entry-card" href="#/tutorial/resources">
          <span class="entry-icon">📖</span><h3>浏览公开资源</h3>
          <p>已通过审核的教程、资料、附件，支持搜索 / 分类 / 排序</p>
        </a>
        <a class="entry-card" href="#/tutorial/upload">
          <span class="entry-icon">⬆️</span><h3>上传我的资源</h3>
          <p>图文 + 可选附件（视频 / PDF / 压缩包），提交后等待审核</p>
        </a>
        <a class="entry-card" href="#/tutorial/favorites">
          <span class="entry-icon">⭐</span><h3>我的收藏</h3>
          <p>收藏的优质资源，随点随看</p>
        </a>
        <a class="entry-card" href="#/tutorial/my_resources">
          <span class="entry-icon">📁</span><h3>我的上传</h3>
          <p>查看审核状态与被驳回原因</p>
        </a>
        <a class="entry-card" href="#/tutorial/login">
          <span class="entry-icon">🔑</span><h3>登录 / 注册</h3>
          <p>登录后即可点赞、收藏、评论、上传</p>
        </a>
      </div>
    </section>
  </div>`;
}

/* ---------------- 资源中心 ---------------- */
let resState = { category: "", q: "", sort: "latest" };

async function loadCategories() {
  const catList = $("resCats");
  if (!catList) return;
  try {
    const res = await fetch(`${API_BASE}/api/v1/resources/categories`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const cats = data.categories || [];
    catList.innerHTML =
      `<li><a class="cat-item ${resState.category === "" ? "active" : ""}" data-cat="">全部</a></li>` +
      cats.map((c) =>
        `<li><a class="cat-item ${resState.category === c.name ? "active" : ""}" data-cat="${escapeAttr(c.name)}">${escapeHtml(c.name)} <span class="cat-count">${c.count}</span></a></li>`
      ).join("");
  } catch (e) { /* 分类加载失败不影响列表 */ }
}

/* 加载固定分类选项填充下拉（上传/编辑页），并保留当前选中值 */
async function loadCategoryOptions(selectEl, current) {
  if (!selectEl) return;
  try {
    const res = await fetch(`${API_BASE}/api/v1/resources/category-options`);
    if (!res.ok) return;
    const data = await res.json();
    const opts = data.options || [];
    if (!opts.length) return;
    selectEl.innerHTML = opts.map((o) =>
      `<option value="${escapeAttr(o)}"${o === current ? " selected" : ""}>${escapeHtml(o)}</option>`).join("");
  } catch (e) { /* 失败保留默认 */ }
}

async function loadResources() {
  const list = $("resList");
  const loading = $("resLoading");
  const empty = $("resEmpty");
  if (loading) loading.hidden = false;
  if (empty) empty.hidden = true;
  const params = new URLSearchParams();
  if (resState.category) params.set("category", resState.category);
  if (resState.q) params.set("q", resState.q);
  if (resState.sort && resState.sort !== "latest") params.set("sort", resState.sort);
  const qs = params.toString();
  try {
    const res = await fetch(`${API_BASE}/api/v1/resources${qs ? "?" + qs : ""}`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (empty) {
      empty.hidden = data.length > 0;
      if (!data.length) {
        empty.textContent = resState.category || resState.q
          ? "🔍 没有匹配的资源，试试调整筛选条件。"
          : "暂无公开资源，去上传第一个吧！";
      }
    }
    if (list) list.innerHTML = data.map(renderResourceCard).join("");
  } catch (err) {
    if (empty) { empty.hidden = false; empty.textContent = "⚠️ 无法连接后端：" + err.message; }
  } finally {
    if (loading) loading.hidden = true;
  }
}

function renderResourceCard(r) {
  const tags = (r.tags || []).map((t) => `<span class="tag">#${escapeHtml(t)}</span>`).join("");
  let action = "";
  if (r.file_path) {
    action = `<a class="res-action" href="${API_BASE}${escapeAttr(r.file_path)}" target="_blank" rel="noopener"
      data-download="${escapeAttr(r.id)}">⬇️ 下载附件（${escapeHtml(fmtSize(r.file_size))}）</a>`;
  } else if (r.link) {
    action = `<a class="res-action" href="${escapeAttr(r.link)}" target="_blank" rel="noopener"
      data-download="${escapeAttr(r.id)}">🔗 查看外部链接</a>`;
  } else {
    action = `<span class="res-action disabled">（无附件 / 链接）</span>`;
  }
  const fileMeta = r.file_name ? `<span title="文件名">📎 ${escapeHtml(r.file_name)}</span>` : "";
  const cover = r.image_url
    ? `<div class="res-cover"><img src="${escapeAttr(resolveMediaUrl(r.image_url))}" alt="${escapeAttr(r.title)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.style.display='none'" /></div>`
    : "";
  return `<li class="res-card">
    ${cover}
    <a class="res-card-main" href="#/tutorial/resource?id=${escapeAttr(r.id)}">
      <div class="res-head">
        <span class="res-cat">${escapeHtml(r.category || "教程")}</span>
        <span class="res-title">${escapeHtml(r.title)}</span>
      </div>
      ${r.description ? `<div class="res-desc">${mdExcerpt(r.description)}</div>` : ""}
      <div class="res-meta">
        <span title="作者">👤 <a class="res-author" href="#/tutorial/user?id=${escapeAttr(r.author_id || "")}">${escapeHtml(r.author_name || "匿名")}</a></span>
        <span title="发布时间">🕒 ${escapeHtml(fmtTime(r.created_at))}</span>
        <span title="下载量">⬇️ ${r.downloads || 0}</span>
        ${fileMeta}
      </div>
      ${tags ? `<div class="item-tags">${tags}</div>` : ""}
    </a>
    <div class="res-action-row">
      ${action}
      <span class="res-spacer"></span>
      <button class="res-like" data-like="${escapeAttr(r.id)}" title="点赞">👍 <span class="count">${r.likes || 0}</span></button>
      <button class="res-fav" data-fav="${escapeAttr(r.id)}" title="收藏">⭐ <span class="count">${r.favorites || 0}</span></button>
      <span class="res-comment-count" title="评论">💬 ${r.comment_count || 0}</span>
    </div>
  </li>`;
}

function renderResourcesPage() {
  currentPage = { type: "resources" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">📚 资源中心</h1>
      <p class="hero-sub">以下资源均已通过管理员审核，可自由下载或查看。</p>
    </section>
    <div class="res-toolbar">
      <input id="resSearch" type="search" placeholder="🔍 搜索标题 / 简介 / 标签 / 作者…" />
      <button id="resSearchBtn" class="btn btn-primary">搜索</button>
      <select id="resSort" class="res-sort">
        <option value="latest">🕒 最新</option>
        <option value="hottest">🔥 最热</option>
        <option value="downloads">⬇️ 最多下载</option>
        <option value="likes">👍 最多点赞</option>
      </select>
      <span id="resClearBtn" class="btn-link" hidden>清空筛选</span>
    </div>
    <div class="res-layout">
      <aside class="res-sidebar">
        <h4>🏷️ 分类</h4>
        <ul id="resCats" class="cat-list"><li><a class="cat-item active" data-cat="">全部</a></li></ul>
      </aside>
      <div class="res-main">
        <div id="resLoading" class="loading">正在加载资源…</div>
        <ul id="resList" class="res-list"></ul>
        <div id="resEmpty" class="empty" hidden>暂无公开资源。</div>
      </div>
    </div>
  </div>`;
}

function initResourceFilters() {
  const searchInput = $("resSearch");
  const searchBtn = $("resSearchBtn");
  const clearBtn = $("resClearBtn");
  const catList = $("resCats");
  const resList = $("resList");
  const sortSel = $("resSort");

  const applySearch = () => {
    resState.q = searchInput ? searchInput.value.trim() : "";
    if (clearBtn) clearBtn.hidden = !(resState.q || resState.category);
    loadResources();
  };
  on(searchBtn, "click", applySearch);
  on(searchInput, "keydown", (e) => { if (e.key === "Enter") applySearch(); });
  on(clearBtn, "click", () => {
    resState.q = ""; resState.category = "";
    if (searchInput) searchInput.value = "";
    if (clearBtn) clearBtn.hidden = true;
    loadCategories();
    loadResources();
  });
  on(catList, "click", (e) => {
    const a = e.target.closest("a.cat-item");
    if (!a) return;
    resState.category = a.dataset.cat || "";
    catList.querySelectorAll(".cat-item").forEach((x) => x.classList.toggle("active", x === a));
    if (clearBtn) clearBtn.hidden = !(resState.q || resState.category);
    loadResources();
  });
  on(sortSel, "change", () => {
    resState.sort = sortSel ? sortSel.value : "latest";
    loadResources();
  });
  on(resList, "click", (e) => {
    const dl = e.target.closest("a[data-download]");
    if (dl) {
      const id = dl.dataset.download;
      if (id) fetch(`${API_BASE}/api/v1/resources/${id}/download`, { method: "POST" }).catch(() => {});
      return;
    }
    const likeBtn = e.target.closest("button[data-like]");
    if (likeBtn) { handleLike(likeBtn.dataset.like, likeBtn); return; }
    const favBtn = e.target.closest("button[data-fav]");
    if (favBtn) { handleFavorite(favBtn.dataset.fav, favBtn); return; }
  });
}

async function handleLike(resId, btn) {
  if (!getUser()) { requireLogin(); return; }
  try {
    const res = await fetch(`${API_BASE}/api/v1/resources/${resId}/like`, { method: "POST", headers: authHeaders() });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
    btn.classList.toggle("active", data.liked);
    const countEl = btn.querySelector(".count");
    if (countEl) countEl.textContent = data.likes;
  } catch (err) { alert("操作失败：" + err.message); }
}

async function handleFavorite(resId, btn) {
  if (!getUser()) { requireLogin(); return; }
  try {
    const res = await fetch(`${API_BASE}/api/v1/resources/${resId}/favorite`, { method: "POST", headers: authHeaders() });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
    btn.classList.toggle("active", data.favorited);
    const countEl = btn.querySelector(".count");
    if (countEl) countEl.textContent = data.favorites;
  } catch (err) { alert("操作失败：" + err.message); }
}
/* ---------------- 上传资源 ---------------- */
function mdToolbarHtml(prefix) {
  return `<div class="md-toolbar" id="${prefix}Toolbar">
    <button type="button" data-md="bold" title="加粗"><b>B</b></button>
    <button type="button" data-md="italic" title="斜体"><i>I</i></button>
    <button type="button" data-md="h" title="标题">H</button>
    <button type="button" data-md="link" title="链接">🔗</button>
    <button type="button" data-md="img" title="插入图片">🖼️</button>
    <button type="button" data-md="code" title="行内代码">` + escapeHtml("</>") + `</button>
    <button type="button" data-md="codeblock" title="代码块">📋</button>
    <select class="md-lang" id="${prefix}Lang" title="代码块语言">
      <option value="">自动识别语言</option>
      <option value="python">Python</option>
      <option value="javascript">JavaScript</option>
      <option value="typescript">TypeScript</option>
      <option value="java">Java</option>
      <option value="c">C</option>
      <option value="cpp">C++</option>
      <option value="csharp">C#</option>
      <option value="go">Go</option>
      <option value="rust">Rust</option>
      <option value="bash">Bash</option>
      <option value="sql">SQL</option>
      <option value="json">JSON</option>
      <option value="yaml">YAML</option>
      <option value="html">HTML</option>
      <option value="css">CSS</option>
      <option value="markdown">Markdown</option>
    </select>
    <button type="button" data-md="quote" title="引用">❝</button>
    <button type="button" data-md="list" title="无序列表">•</button>
    <button type="button" data-md="listol" title="有序列表">1.</button>
    <button type="button" data-md="table" title="表格">▦</button>
    <span class="md-hint">支持 Markdown</span>
  </div>`;
}

function renderUploadPage() {
  currentPage = { type: "upload" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">⬆️ 上传资源</h1>
      <p class="hero-sub">填写标题与正文（支持 Markdown：代码块 / 图片 / 表格等），可附文件或外链。提交后进入待审核队列。</p>
    </section>
    <div style="max-width:760px">
      <form id="uploadForm" class="tut-form card" style="padding:24px">
        <label class="field">
          <span>标题 *</span>
          <input id="resTitle" type="text" maxlength="120" placeholder="例如：Stable Diffusion 入门教程" required />
        </label>
        <label class="field">
          <span>分类（从固定选项中选择）</span>
          <select id="resCategory" class="res-cat-select">
            <option value="教程">教程</option>
            <option value="模型">模型</option>
            <option value="资料">资料</option>
          </select>
        </label>
        <label class="field">
          <span>封面图 URL（可选，列表卡片展示）</span>
          <input id="resImage" type="text" maxlength="2000" placeholder="https://…" />
        </label>
        <label class="field">
          <span>正文（Markdown）</span>
          ${mdToolbarHtml("res")}
          <textarea id="resDesc" maxlength="50000" rows="12" placeholder="支持 Markdown 语法…&#10;&#10;代码块示例：&#10;\`\`\`python&#10;print('hello'）&#10;\`\`\`&#10;&#10;图片：![描述](https://图片地址)"></textarea>
          <div class="md-preview" id="resPreview" hidden></div>
        </label>
        <label class="field">
          <span>标签（逗号分隔）</span>
          <input id="resTags" type="text" maxlength="200" placeholder="AI, 绘画, 入门" />
        </label>
        <label class="field">
          <span>外链（可选）</span>
          <input id="resLink" type="text" maxlength="2000" placeholder="https://…" />
        </label>
        <label class="field">
          <span>附件文件（可选）</span>
          <input id="resFile" type="file" />
          <small id="fileNote"></small>
          <small>允许类型：图片 / PDF / 文档 / 压缩包 / 音视频；单文件 ≤ 200MB</small>
        </label>
        <div style="margin-top:4px">
          <button id="uploadSubmit" type="submit" class="btn btn-primary">提交审核</button>
        </div>
        <div id="uploadStatus" class="tut-status" hidden></div>
      </form>
    </div>
  </div>`;
}

/* 给 textarea 绑定 Markdown 工具栏（前缀区分上传/编辑页） */
function bindMdToolbar(prefix) {
  const toolbar = $(prefix + "Toolbar");
  const ta = $(prefix === "res" ? "resDesc" : "editDesc");
  const langSel = $(prefix + "Lang");
  if (!toolbar || !ta) return;

  const surround = (before, after, placeholder) => {
    const s = ta.selectionStart, e = ta.selectionEnd;
    const sel = ta.value.slice(s, e) || placeholder || "";
    const inserted = before + sel + after;
    ta.value = ta.value.slice(0, s) + inserted + ta.value.slice(e);
    ta.focus();
    const pos = s + before.length + sel.length + after.length;
    ta.setSelectionRange(pos, pos);
    ta.dispatchEvent(new Event("input"));
  };

  toolbar.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-md]");
    if (!btn) return;
    const kind = btn.dataset.md;
    const lang = langSel ? langSel.value : "";
    switch (kind) {
      case "bold": surround("**", "**", "加粗文字"); break;
      case "italic": surround("*", "*", "斜体文字"); break;
      case "h": surround("## ", "", "标题"); break;
      case "link": surround("[", "](https://)", "链接文字"); break;
      case "img": surround("![", "](https://)", "图片描述"); break;
      case "code": surround("`", "`", "code"); break;
      case "codeblock":
        surround("```" + lang + "\n", "\n```", "代码"); break;
      case "quote": surround("> ", "", "引用内容"); break;
      case "list": surround("- ", "", "列表项"); break;
      case "listol": surround("1. ", "", "列表项"); break;
      case "table": surround("\n| 列1 | 列2 |\n| --- | --- |\n| 内容 | 内容 |\n", "", ""); break;
    }
  });
}

/* 绑定实时预览（可选：输入时预览 Markdown） */
function bindMdPreview(prefix) {
  const ta = $(prefix === "res" ? "resDesc" : "editDesc");
  const preview = $(prefix === "res" ? "resPreview" : "editPreview");
  if (!ta || !preview) return;
  ta.addEventListener("input", () => {
    const md = ta.value.trim();
    if (md) {
      preview.hidden = false;
      preview.innerHTML = renderMarkdown(md);
      bindRenderedContent(preview);
    } else {
      preview.hidden = true;
    }
  });
}

async function initUpload() {
  const form = $("uploadForm");
  const status = $("uploadStatus");
  const fileInput = $("resFile");
  const fileNote = $("fileNote");
  if (fileInput && fileNote) {
    fileInput.addEventListener("change", () => {
      fileNote.textContent = fileInput.files.length
        ? `已选择：${fileInput.files[0].name}（${fmtSize(fileInput.files[0].size)}）`
        : "";
    });
  }
  if (!form) return;
  bindMdToolbar("res");
  bindMdPreview("res");
  loadCategoryOptions($("resCategory"), "教程");
  if (!getUser()) {
    setStatus(status, "请先登录后再上传（右上角「登录」）。", true);
    form.querySelectorAll("input, textarea, button").forEach((e) => (e.disabled = true));
    return;
  }
  on(form, "submit", async (e) => {
    e.preventDefault();
    const fd = new FormData();
    fd.append("title", $("resTitle").value.trim());
    fd.append("description", $("resDesc").value.trim());
    fd.append("category", $("resCategory").value.trim() || "教程");
    fd.append("tags", $("resTags").value.trim());
    fd.append("link", $("resLink").value.trim());
    fd.append("image_url", $("resImage").value.trim());
    if (fileInput && fileInput.files.length) fd.append("file", fileInput.files[0]);
    const btn = $("uploadSubmit");
    btn.disabled = true; btn.textContent = "上传中…";
    setStatus(status, "");
    try {
      const res = await fetch(`${API_BASE}/api/v1/resources`, {
        method: "POST",
        body: fd,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
      setStatus(status, "✅ 上传成功！已提交审核，管理员通过后将公开显示。");
      form.reset();
      if (fileNote) fileNote.textContent = "";
    } catch (err) {
      setStatus(status, "❌ 上传失败：" + err.message, true);
    } finally {
      btn.disabled = false; btn.textContent = "提交审核";
    }
  });
}

/* ---------------- 登录 / 注册 ---------------- */
function renderLoginPage() {
  currentPage = { type: "login" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">🔑 登录 / 注册</h1>
      <p class="hero-sub">注册后即可上传资源；填写管理员邀请码即可成为管理员。</p>
    </section>
    <div class="auth-wrap">
      <div class="auth-col">
        <h3>登录</h3>
        <form id="loginForm" class="tut-form">
          <label class="field"><span>用户名</span><input id="loginUser" type="text" maxlength="32" required /></label>
          <label class="field"><span>密码</span><input id="loginPass" type="password" required /></label>
          <div><button id="loginSubmit" type="submit" class="btn btn-primary">登录</button></div>
        </form>
      </div>
      <div class="auth-col">
        <h3>注册</h3>
        <form id="regForm" class="tut-form">
          <label class="field"><span>用户名（2-32 字）</span><input id="regUser" type="text" minlength="2" maxlength="32" required /></label>
          <label class="field"><span>密码（≥6 位）</span><input id="regPass" type="password" minlength="6" required /></label>
          <label class="field"><span>管理员邀请码（可选）</span><input id="regInvite" type="text" maxlength="64" placeholder="填对邀请码即成为管理员" /></label>
          <div><button id="regSubmit" type="submit" class="btn btn-primary">注册并登录</button></div>
        </form>
      </div>
    </div>
    <div id="authStatus" class="tut-status auth-status" hidden></div>
  </div>`;
}

async function initLogin() {
  const loginForm = $("loginForm");
  const regForm = $("regForm");
  const status = $("authStatus");
  if (getUser()) { setStatus(status, "当前已登录：" + getUser().username); }

  on(loginForm, "submit", async (e) => {
    e.preventDefault();
    const btn = $("loginSubmit");
    btn.disabled = true;
    try {
      const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: $("loginUser").value.trim(), password: $("loginPass").value }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
      setSession(data.token, data.user);
      setStatus(status, "✅ 登录成功，正在跳转…");
      setTimeout(() => { location.hash = "#/tutorial/profile"; }, 400);
    } catch (err) {
      setStatus(status, "❌ " + err.message, true);
    } finally { btn.disabled = false; }
  });

  on(regForm, "submit", async (e) => {
    e.preventDefault();
    const btn = $("regSubmit");
    btn.disabled = true;
    try {
      const invite = $("regInvite");
      const res = await fetch(`${API_BASE}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: $("regUser").value.trim(),
          password: $("regPass").value,
          invite_code: invite ? invite.value.trim() : "",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
      setSession(data.token, data.user);
      const roleNote = data.user.role === "admin" ? "（你已成为管理员）" : "";
      setStatus(status, "✅ 注册成功" + roleNote + "，正在跳转…");
      setTimeout(() => { location.hash = "#/tutorial/profile"; }, 400);
    } catch (err) {
      setStatus(status, "❌ " + err.message, true);
    } finally { btn.disabled = false; }
  });
}
/* ---------------- 资源编辑 ---------------- */
let editResId = "";

function renderEditPage() {
  currentPage = { type: "edit" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">✏️ 编辑资源</h1>
      <p class="hero-sub">修改标题 / 正文 / 分类 / 标签 / 外链，保存后需重新审核。</p>
    </section>
    <div style="max-width:760px">
      <form id="editForm" class="tut-form card" style="padding:24px">
        <label class="field">
          <span>标题 *</span>
          <input id="editTitle" type="text" maxlength="120" required />
        </label>
        <label class="field">
          <span>分类（从固定选项中选择）</span>
          <select id="editCategory" class="res-cat-select">
            <option value="教程">教程</option>
            <option value="模型">模型</option>
            <option value="资料">资料</option>
          </select>
        </label>
        <label class="field">
          <span>封面图 URL（可选）</span>
          <input id="editImage" type="text" maxlength="2000" placeholder="https://…" />
        </label>
        <label class="field">
          <span>正文（Markdown）</span>
          ${mdToolbarHtml("edit")}
          <textarea id="editDesc" maxlength="50000" rows="12" placeholder="支持 Markdown 语法…"></textarea>
          <div class="md-preview" id="editPreview" hidden></div>
        </label>
        <label class="field">
          <span>标签（逗号分隔）</span>
          <input id="editTags" type="text" maxlength="200" placeholder="AI, 绘画, 入门" />
        </label>
        <label class="field">
          <span>外链（可选）</span>
          <input id="editLink" type="text" maxlength="2000" placeholder="https://…" />
          <small>仅支持 http/https，内网地址与可执行文件链接会被拦截</small>
        </label>
        <div style="margin-top:4px;display:flex;gap:10px">
          <button id="editSubmit" type="submit" class="btn btn-primary">保存修改</button>
          <a class="btn btn-ghost" href="#/tutorial/my_resources">取消</a>
        </div>
        <div id="editStatus" class="tut-status" hidden></div>
      </form>
    </div>
  </div>`;
}

async function loadEditPage() {
  const id = new URLSearchParams(location.hash.split("?")[1] || "").get("id");
  if (!id) { location.hash = "#/tutorial/my_resources"; return; }
  if (!getUser()) { requireLogin(); return; }
  editResId = id;
  try {
    const res = await fetch(`${API_BASE}/api/v1/resources/mine`, { headers: authHeaders() });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const mine = await res.json();
    const rec = mine.find((r) => r.id === id);
    if (!rec) {
      setStatus($("editStatus"), "⚠️ 找不到该资源，或它不是你的上传。", true);
      return;
    }
    $("editTitle").value = rec.title || "";
    $("editCategory").value = rec.category || "教程";
    $("editImage").value = rec.image_url || "";
    $("editDesc").value = rec.description || "";
    $("editTags").value = (rec.tags || []).join(", ");
    $("editLink").value = rec.link || "";
    loadCategoryOptions($("editCategory"), rec.category || "教程");
  } catch (err) {
    setStatus($("editStatus"), "⚠️ 加载失败：" + err.message, true);
  }
}

async function initEdit() {
  const form = $("editForm");
  if (!form) return;
  bindMdToolbar("edit");
  bindMdPreview("edit");
  on(form, "submit", async (e) => {
    e.preventDefault();
    const btn = $("editSubmit");
    const status = $("editStatus");
    btn.disabled = true;
    btn.textContent = "保存中…";
    setStatus(status, "");
    const tags = $("editTags").value.split(",").map((t) => t.trim()).filter(Boolean);
    try {
      const res = await fetch(`${API_BASE}/api/v1/resources/${editResId}`, {
        method: "PUT",
        headers: authHeaders(),
        body: JSON.stringify({
          title: $("editTitle").value.trim(),
          description: $("editDesc").value.trim(),
          category: $("editCategory").value.trim() || "教程",
          tags,
          link: $("editLink").value.trim(),
          image_url: $("editImage").value.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
      setStatus(status, "✅ 已保存，重新进入待审核队列。");
      setTimeout(() => { location.hash = "#/tutorial/my_resources"; }, 700);
    } catch (err) {
      setStatus(status, "❌ 保存失败：" + err.message, true);
    } finally {
      btn.disabled = false;
      btn.textContent = "保存修改";
    }
  });
}

/* ---------------- 资源详情 ---------------- */
let detailResId = "";

function renderResourcePage() {
  currentPage = { type: "resource" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">📄 资源详情</h1>
      <p class="hero-sub">点赞 / 收藏 / 评论 · 评论支持楼中楼回复</p>
    </section>
    <div id="detailLoading" class="loading">正在加载资源详情…</div>
    <div id="detailWrap" hidden></div>
  </div>`;
}

async function loadResourceDetail() {
  const id = new URLSearchParams(location.hash.split("?")[1] || "").get("id");
  if (!id) { const w = $("detailWrap"); if (w) { w.hidden = false; w.innerHTML = `<div class="empty">缺少资源 ID。</div>`; } return; }
  detailResId = id;
  const loading = $("detailLoading");
  const wrap = $("detailWrap");
  if (loading) loading.hidden = false;
  try {
    // 认证交给 httpOnly Cookie，由全局 fetch 包装自动携带
    const res = await fetch(`${API_BASE}/api/v1/resources/${id}`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    renderDetail(data);
    if (loading) loading.hidden = true;
    if (wrap) wrap.hidden = false;
    // 单独按当前排序拉评论
    loadCommentsWithSort();
  } catch (err) {
    if (loading) loading.hidden = true;
    if (wrap) { wrap.hidden = false; wrap.innerHTML = `<div class="empty">⚠️ 加载失败：${escapeHtml(err.message)}</div>`; }
  }
}

async function loadCommentsWithSort() {
  const list = $("commentList");
  if (!list || !detailResId) return;
  try {
    const res = await fetch(`${API_BASE}/api/v1/resources/${detailResId}/comments?sort=${commentSort}`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const comments = await res.json();
    renderComments(comments);
  } catch (e) { /* 忽略 */ }
}

function renderDetail(data) {
  const r = data.resource;
  const tags = (r.tags || []).map((t) => `<span class="tag">#${escapeHtml(t)}</span>`).join("");
  let action = "";
  if (r.file_path) {
    action = `<a class="res-action" href="${API_BASE}${escapeAttr(r.file_path)}" target="_blank" rel="noopener noreferrer"
      data-download="${escapeAttr(r.id)}">⬇️ 下载附件（${escapeHtml(fmtSize(r.file_size))}）</a>`;
  } else if (r.link) {
    action = `<a class="res-action" href="${escapeAttr(r.link)}" target="_blank" rel="noopener noreferrer"
      data-download="${escapeAttr(r.id)}">🔗 查看外部链接</a>`;
  } else {
    action = `<span class="res-action disabled">（无附件 / 链接）</span>`;
  }
  const fileMeta = r.file_name ? `<span>📎 ${escapeHtml(r.file_name)}</span>` : "";
  const me = getUser();
  // 作者本人可编辑；作者本人或管理员可删帖
  const canEdit = !!(me && me.id === r.author_id);
  const canDelete = !!(me && (me.id === r.author_id || me.role === "admin"));
  const editBtn = canEdit
    ? `<button class="btn btn-ghost btn-sm" id="editResBtn" data-edit="${escapeAttr(r.id)}">✏️ 编辑</button>`
    : "";
  const delBtn = canDelete
    ? `<button class="btn btn-ghost btn-sm danger" id="delResBtn" data-del="${escapeAttr(r.id)}" title="${me && me.role === "admin" && me.id !== r.author_id ? "管理员删除（可填原因）" : "删除帖子"}">🗑️ 删除</button>`
    : "";
  const cover = r.image_url
    ? `<div class="detail-cover"><img src="${escapeAttr(resolveMediaUrl(r.image_url))}" alt="${escapeAttr(r.title)}" referrerpolicy="no-referrer" onerror="this.style.display='none'" /></div>`
    : "";
  const wrap = $("detailWrap");
  wrap.innerHTML = `
    <div class="detail-card">
      <div class="res-head">
        <span class="res-cat">${escapeHtml(r.category || "教程")}</span>
        <h2 class="res-title">${escapeHtml(r.title)}</h2>
        <span class="res-head-actions">${editBtn}${delBtn}</span>
      </div>
      ${cover}
      ${r.description ? `<div class="res-desc md-body">${renderMarkdown(r.description)}</div>` : ""}
      <div class="res-meta">
        <span>👤 <a class="res-author" href="#/tutorial/user?id=${escapeAttr(r.author_id || "")}">${escapeHtml(r.author_name || "匿名")}</a></span>
        <span>🕒 ${escapeHtml(fmtTime(r.created_at))}</span>
        <span>⬇️ ${r.downloads || 0}</span>
        ${fileMeta}
      </div>
      ${tags ? `<div class="item-tags">${tags}</div>` : ""}
      <div class="res-action-row">
        ${action}
        <span class="res-spacer"></span>
        <button class="res-like ${data.liked ? "active" : ""}" data-like="${escapeAttr(r.id)}">👍 <span class="count">${r.likes || 0}</span></button>
        <button class="res-fav ${data.favorited ? "active" : ""}" data-fav="${escapeAttr(r.id)}">⭐ <span class="count">${r.favorites || 0}</span></button>
      </div>
    </div>
    <div class="detail-comments">
      <div class="detail-comments-head">
        <h3>💬 评论（${data.comments.length}）</h3>
        <div class="comment-sort">
          <button class="csort-btn ${commentSort === "time" ? "active" : ""}" data-csort="time">🕒 按时间</button>
          <button class="csort-btn ${commentSort === "hot" ? "active" : ""}" data-csort="hot">🔥 按热度</button>
        </div>
      </div>
      <div id="commentInput" class="comment-input">
        <textarea id="commentText" placeholder="写下你的评论或提问…"></textarea>
        <button id="commentSubmit" class="btn btn-primary">发表评论</button>
      </div>
      <ul id="commentList" class="comment-list"></ul>
    </div>`;
  renderComments(data.comments);
  bindDetailActions();
  bindRenderedContent(wrap);
}

let commentSort = "time";

function renderComments(comments) {
  const list = $("commentList");
  if (!list) return;
  if (!comments.length) {
    list.innerHTML = `<li class="item-empty">还没有评论，来抢沙发～</li>`;
    return;
  }
  const me = getUser();
  const top = comments.filter((c) => !c.parent_id);
  const replies = comments.filter((c) => c.parent_id);
  const byParent = {};
  replies.forEach((c) => { (byParent[c.parent_id] = byParent[c.parent_id] || []).push(c); });
  list.innerHTML = top.map((c) => renderComment(c, byParent, me)).join("");
}

function renderComment(c, byParent, me) {
  const children = (byParent[c.id] || []).map((r) => renderReply(r, me)).join("");
  const hue = avatarHue(c.author_name);
  const isMine = !!(me && me.id === c.author_id);
  const isAdmin = !!(me && me.role === "admin");
  const canDelete = isMine || isAdmin;
  const replyBtn = `<button class="btn-link" data-reply="${escapeAttr(c.id)}" data-reply-to="${escapeAttr(c.author_name)}">回复</button>`;
  const likeBtn = `<button class="btn-link cmt-like ${c.liked ? "active" : ""}" data-clike="${escapeAttr(c.id)}">👍 <span class="count">${c.likes || 0}</span></button>`;
  const delBtn = canDelete ? `<button class="btn-link danger" data-cdel="${escapeAttr(c.id)}">删除</button>` : "";
  const blockBtn = (me && me.id !== c.author_id) ? `<button class="btn-link danger" data-cblock="${escapeAttr(c.author_id)}" data-cname="${escapeAttr(c.author_name)}">屏蔽</button>` : "";
  return `
    <li class="comment-item">
      <a class="comment-avatar" href="#/tutorial/user?id=${escapeAttr(c.author_id)}" title="查看 ${escapeAttr(c.author_name)} 的主页"
         style="background:hsl(${hue},62%,52%)">${escapeHtml(avatarChar(c.author_name))}</a>
      <div class="comment-main">
        <div class="comment-head">
          <a class="comment-author" href="#/tutorial/user?id=${escapeAttr(c.author_id)}">${escapeHtml(c.author_name)}</a>
          ${isAdmin ? `<span class="admin-tag">管理员</span>` : ""}
          <span class="comment-time">${escapeHtml(fmtTime(c.created_at))}</span>
        </div>
        <div class="comment-content">${escapeHtml(c.content)}</div>
        <div class="comment-foot">${replyBtn}${likeBtn}${delBtn}${blockBtn}</div>
        ${children ? `<ul class="comment-list reply-list">${children}</ul>` : ""}
      </div>
    </li>`;
}

function renderReply(r, me) {
  const hue = avatarHue(r.author_name);
  const isMine = !!(me && me.id === r.author_id);
  const isAdmin = !!(me && me.role === "admin");
  const canDelete = isMine || isAdmin;
  const replyBtn = `<button class="btn-link" data-reply="${escapeAttr(r.id)}" data-reply-to="${escapeAttr(r.author_name)}">回复</button>`;
  const likeBtn = `<button class="btn-link cmt-like ${r.liked ? "active" : ""}" data-clike="${escapeAttr(r.id)}">👍 <span class="count">${r.likes || 0}</span></button>`;
  const delBtn = canDelete ? `<button class="btn-link danger" data-cdel="${escapeAttr(r.id)}">删除</button>` : "";
  const blockBtn = (me && me.id !== r.author_id) ? `<button class="btn-link danger" data-cblock="${escapeAttr(r.author_id)}" data-cname="${escapeAttr(r.author_name)}">屏蔽</button>` : "";
  return `
    <li class="comment-item reply">
      <a class="comment-avatar" href="#/tutorial/user?id=${escapeAttr(r.author_id)}" style="background:hsl(${hue},62%,52%)">${escapeHtml(avatarChar(r.author_name))}</a>
      <div class="comment-main">
        <div class="comment-head">
          <a class="comment-author" href="#/tutorial/user?id=${escapeAttr(r.author_id)}">${escapeHtml(r.author_name)}</a>
          ${isAdmin ? `<span class="admin-tag">管理员</span>` : ""}
          <span class="comment-time">${escapeHtml(fmtTime(r.created_at))}</span>
        </div>
        <div class="comment-content">${escapeHtml(r.content)}</div>
        <div class="comment-foot">${replyBtn}${likeBtn}${delBtn}${blockBtn}</div>
      </div>
    </li>`;
}

function bindDetailActions() {
  const wrap = $("detailWrap");
  on(wrap, "click", (e) => {
    const dl = e.target.closest("a[data-download]");
    if (dl) {
      fetch(`${API_BASE}/api/v1/resources/${dl.dataset.download}/download`, { method: "POST" }).catch(() => {});
      return;
    }
    const likeBtn = e.target.closest("button[data-like]");
    if (likeBtn) { handleLike(likeBtn.dataset.like, likeBtn); return; }
    const favBtn = e.target.closest("button[data-fav]");
    if (favBtn) { handleFavorite(favBtn.dataset.fav, favBtn); return; }
    const replyBtn = e.target.closest("button[data-reply]");
    if (replyBtn) {
      const ta = $("commentText");
      ta.dataset.parentId = replyBtn.dataset.reply;
      ta.placeholder = `回复 @${replyBtn.dataset.replyTo}：`;
      ta.focus();
      return;
    }
    const editBtn = e.target.closest("button[data-edit]");
    if (editBtn) {
      location.hash = `#/tutorial/edit?id=${encodeURIComponent(editBtn.dataset.edit)}`;
      return;
    }
    const delBtn = e.target.closest("button[data-del]");
    if (delBtn) { handleResourceDelete(delBtn.dataset.del); return; }
    const clikeBtn = e.target.closest("button[data-clike]");
    if (clikeBtn) { handleCommentLike(clikeBtn.dataset.clike, clikeBtn); return; }
    const cdelBtn = e.target.closest("button[data-cdel]");
    if (cdelBtn) { handleCommentDelete(cdelBtn.dataset.cdel); return; }
    const cblockBtn = e.target.closest("button[data-cblock]");
    if (cblockBtn) { handleCommentBlock(cblockBtn.dataset.cblock, cblockBtn.dataset.cname); return; }
    const csortBtn = e.target.closest("button[data-csort]");
    if (csortBtn) {
      commentSort = csortBtn.dataset.csort;
      document.querySelectorAll(".csort-btn").forEach((b) => b.classList.toggle("active", b === csortBtn));
      loadCommentsWithSort();
      return;
    }
  });
  const submit = $("commentSubmit");
  const ta = $("commentText");
  on(submit, "click", async () => {
    if (!getUser()) { requireLogin(); return; }
    const content = ta.value.trim();
    if (!content) { alert("评论内容不能为空"); return; }
    const parentId = ta.dataset.parentId || null;
    try {
      const res = await fetch(`${API_BASE}/api/v1/resources/${detailResId}/comments`, {
        method: "POST",
        headers: authHeaders(),
        body: JSON.stringify({ content, parent_id: parentId }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
      ta.value = "";
      delete ta.dataset.parentId;
      ta.placeholder = "写下你的评论或提问…";
      loadCommentsWithSort();
      loadResourceDetail();
    } catch (err) { alert("评论失败：" + err.message); }
  });
}

async function handleResourceDelete(resId) {
  if (!getUser()) { requireLogin(); return; }
  const me = getUser();
  let reason = "";
  if (me && me.role === "admin") {
    reason = window.prompt("删除原因（可选，将通知作者）：") || "";
  }
  if (!confirm("确定删除这篇帖子？此操作不可撤销。")) return;
  try {
    const qs = reason ? `?reason=${encodeURIComponent(reason)}` : "";
    const res = await fetch(`${API_BASE}/api/v1/resources/${resId}${qs}`, {
      method: "DELETE", headers: authHeaders(),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
    alert("已删除");
    location.hash = "#/tutorial/resources";
  } catch (err) { alert("删除失败：" + err.message); }
}

async function handleCommentLike(commentId, btn) {
  if (!getUser()) { requireLogin(); return; }
  try {
    const res = await fetch(`${API_BASE}/api/v1/resources/${detailResId}/comments/${commentId}/like`, {
      method: "POST", headers: authHeaders(),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
    btn.classList.toggle("active", data.liked);
    const countEl = btn.querySelector(".count");
    if (countEl) countEl.textContent = data.likes;
  } catch (err) { alert("操作失败：" + err.message); }
}

async function handleCommentDelete(commentId) {
  if (!getUser()) { requireLogin(); return; }
  if (!confirm("确定删除这条评论？")) return;
  try {
    const res = await fetch(`${API_BASE}/api/v1/resources/${detailResId}/comments/${commentId}`, {
      method: "DELETE", headers: authHeaders(),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
    loadCommentsWithSort();
  } catch (err) { alert("删除失败：" + err.message); }
}

async function handleCommentBlock(userId, userName) {
  if (!getUser()) { requireLogin(); return; }
  if (!confirm(`确定屏蔽 ${userName}？屏蔽后双方无法互相评论、查看主页、私信。`)) return;
  try {
    const res = await fetch(`${API_BASE}/api/v1/notifications/blocks`, {
      method: "POST", headers: authHeaders(), body: JSON.stringify({ user_id: userId }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
    alert("已屏蔽");
    loadCommentsWithSort();
  } catch (err) { alert("屏蔽失败：" + err.message); }
}

/* ---------------- 我的收藏 / 我的上传 ---------------- */
function renderMyListPage(kind) {
  currentPage = { type: "mylist", kind };
  const title = kind === "favorites" ? "⭐ 我的收藏" : "📁 我的上传";
  const sub = kind === "favorites" ? "收藏的优质资源，随点随看" : "查看审核状态与被驳回原因";
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">${title}</h1>
      <p class="hero-sub">${sub}</p>
    </section>
    <div id="resLoading" class="loading">正在加载…</div>
    <ul id="resList" class="res-list"></ul>
    <div id="resEmpty" class="empty" hidden>${kind === "favorites" ? "还没有收藏任何资源。" : "你还没有上传过资源。"}</div>
  </div>`;
}

async function loadMyList(kind) {
  const list = $("resList");
  const empty = $("resEmpty");
  const loading = $("resLoading");
  if (loading) loading.hidden = false;
  if (empty) empty.hidden = true;
  try {
    const url = kind === "favorites"
      ? `${API_BASE}/api/v1/resources/favorites`
      : `${API_BASE}/api/v1/resources/mine`;
    const res = await fetch(url, { headers: authHeaders() });
    if (res.status === 401) { requireLogin(); return; }
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (empty) {
      empty.hidden = data.length > 0;
      if (!data.length) empty.textContent = kind === "favorites" ? "还没有收藏任何资源。" : "你还没有上传过资源。";
    }
    if (list) list.innerHTML = (kind === "favorites" ? data.map(renderResourceCard) : data.map(renderMyCard)).join("");
  } catch (err) {
    if (empty) { empty.hidden = false; empty.textContent = "⚠️ 加载失败：" + err.message; }
  } finally {
    if (loading) loading.hidden = true;
  }
}

function renderMyCard(r) {
  const tags = (r.tags || []).map((t) => `<span class="tag">#${escapeHtml(t)}</span>`).join("");
  const statusMap = {
    pending: ["待审核", "pending"],
    approved: ["已通过", "approved"],
    rejected: ["已驳回", "rejected"],
  };
  const [label, cls] = statusMap[r.status] || ["未知", "pending"];
  const note = r.review_note ? `<div class="res-note">驳回原因：${escapeHtml(r.review_note)}</div>` : "";
  const fileMeta = r.file_name ? `<span>📎 ${escapeHtml(r.file_name)}</span>` : "";
  return `<li class="res-card">
    <div class="res-head">
      <span class="res-cat">${escapeHtml(r.category || "教程")}</span>
      <span class="res-title">${escapeHtml(r.title)}</span>
      <span class="res-status ${cls}">${label}</span>
      <a class="btn-link" href="#/tutorial/edit?id=${escapeAttr(r.id)}" style="margin-left:auto">✏️ 编辑</a>
    </div>
    ${r.description ? `<div class="res-desc">${mdExcerpt(r.description)}</div>` : ""}
    <div class="res-meta">
      <span>🕒 ${escapeHtml(fmtTime(r.created_at))}</span>
      <span>⬇️ ${r.downloads || 0}</span>
      ${fileMeta}
    </div>
    ${tags ? `<div class="item-tags">${tags}</div>` : ""}
    ${note}
  </li>`;
}
/* ---------------- 个人中心 ---------------- */
function renderProfilePage() {
  currentPage = { type: "profile" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">👤 个人中心</h1>
      <p class="hero-sub">账号信息与统计</p>
    </section>
    <div class="profile-wrap">
      <section class="profile-card">
        <div class="profile-head">
          <span class="avatar" id="profileAvatar">👤</span>
          <div class="profile-info">
            <div class="profile-name" id="profileName">—</div>
            <div class="profile-meta" id="profileMeta">加载中…</div>
          </div>
          <button class="btn btn-ghost" id="profileLogout">退出登录</button>
        </div>
        <div class="profile-stats" id="profileStats"></div>
      </section>
      <section class="profile-menu">
        <a class="profile-menu-item" href="#/tutorial/favorites">
          <span class="pm-icon">⭐</span><div class="pm-text"><b>我的收藏</b><small>收藏的优质资源</small></div><span class="pm-arrow">›</span>
        </a>
        <a class="profile-menu-item" href="#/tutorial/my_resources">
          <span class="pm-icon">📁</span><div class="pm-text"><b>我的上传</b><small>查看审核状态与驳回原因</small></div><span class="pm-arrow">›</span>
        </a>
        <a class="profile-menu-item" href="#/tutorial/upload">
          <span class="pm-icon">⬆️</span><div class="pm-text"><b>上传资源</b><small>发布教程 / 模型 / 资料</small></div><span class="pm-arrow">›</span>
        </a>
        <a class="profile-menu-item" href="#/tutorial/settings">
          <span class="pm-icon">⚙️</span><div class="pm-text"><b>设置</b><small>AI 配置 · 隐私 · 通知偏好</small></div><span class="pm-arrow">›</span>
        </a>
        <a class="profile-menu-item" href="#/tutorial/admin" id="profileAdmin" style="display:none">
          <span class="pm-icon">🛡️</span><div class="pm-text"><b>管理后台</b><small>审核资源、查看平台数据</small></div><span class="pm-arrow">›</span>
        </a>
      </section>
    </div>
  </div>`;
}

async function renderProfile() {
  const u = getUser();
  if (!u) { requireLogin(); return; }

  const avatar = $("profileAvatar");
  const name = $("profileName");
  const meta = $("profileMeta");
  const stats = $("profileStats");
  const adminEntry = $("profileAdmin");

  if (avatar) {
    const hue = avatarHue(u.username);
    avatar.style.background = `hsl(${hue},62%,52%)`;
    avatar.textContent = avatarChar(u.username);
  }
  if (name) name.textContent = u.username;
  if (meta) {
    const role = u.role === "admin" ? "管理员" : "普通用户";
    const since = u.created_at ? "注册于 " + fmtTime(u.created_at).slice(0, 10) : "";
    meta.textContent = [role, since].filter(Boolean).join(" · ");
  }
  if (adminEntry) adminEntry.style.display = u.role === "admin" ? "" : "none";

  if (stats) {
    stats.innerHTML = `<div class="ps-item"><b>—</b><span>收藏</span></div>
      <div class="ps-item"><b>—</b><span>上传</span></div>`;
    try {
      const [favRes, mineRes] = await Promise.all([
        fetch(`${API_BASE}/api/v1/resources/favorites`, { headers: authHeaders() }),
        fetch(`${API_BASE}/api/v1/resources/mine`, { headers: authHeaders() }),
      ]);
      let favCount = 0, mineCount = 0;
      if (favRes.ok) favCount = (await favRes.json()).length;
      if (mineRes.ok) mineCount = (await mineRes.json()).length;
      stats.innerHTML = `<div class="ps-item"><b>${favCount}</b><span>收藏</span></div>
        <div class="ps-item"><b>${mineCount}</b><span>上传</span></div>`;
    } catch (e) { /* 统计失败保持占位 */ }
  }

  const logoutBtn = $("profileLogout");
  on(logoutBtn, "click", async () => {
    try {
      await fetch(`${API_BASE}/api/v1/auth/logout`, { method: "POST", headers: authHeaders() });
    } catch (e) { /* 忽略网络错误 */ }
    clearSession();
    location.hash = "#/tutorial/platform";
  });
}

/* ---------------- 管理后台 ---------------- */
function renderAdminPage() {
  currentPage = { type: "admin" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">🛡️ 管理后台</h1>
      <p class="hero-sub">平台数据概览 + 资源审核。通过后立即在资源中心公开。</p>
    </section>
    <section class="dash">
      <h3 class="dash-title">📊 数据概览</h3>
      <div id="adminStats" class="stats-grid"><div class="loading">正在加载统计…</div></div>
      <div id="adminStatsErr" class="empty" hidden></div>
    </section>
    <section class="dash">
      <h3 class="dash-title">📥 待审核队列</h3>
      <div id="adminLoading" class="loading">正在加载审核队列…</div>
      <ul id="adminList" class="res-list"></ul>
      <div id="adminEmpty" class="empty" hidden>🎉 当前没有待审核或已驳回的资源。</div>
    </section>
    <section class="dash">
      <h3 class="dash-title">🗂️ 分类管理</h3>
      <p class="block-sub" style="margin-bottom:12px">上传资源时用户从这些固定分类中选择；增删立即生效。</p>
      <div class="cat-manage">
        <div class="cat-manage-input">
          <input id="newCatName" type="text" maxlength="40" placeholder="新分类名，如：插件" />
          <button id="addCatBtn" class="btn btn-primary btn-sm">➕ 添加分类</button>
        </div>
        <ul id="catManageList" class="cat-manage-list"></ul>
      </div>
    </section>
  </div>`;
}

async function loadAdminStats() {
  const grid = $("adminStats");
  const err = $("adminStatsErr");
  if (!grid) return;
  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/resources/stats`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) {
      if (err) { err.hidden = false; err.textContent = "⚠️ 需要管理员权限，请先以管理员身份登录。"; }
      grid.hidden = true; return;
    }
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    renderAdminStats(data);
  } catch (e) {
    if (err) { err.hidden = false; err.textContent = "⚠️ 统计加载失败：" + e.message; }
  }
}

function renderAdminStats(s) {
  const grid = $("adminStats");
  if (!grid) return;
  const cards = [
    { icon: "👥", label: "注册用户", value: s.users.total, sub: `管理员 ${s.users.admins}` },
    { icon: "📦", label: "资源总数", value: s.resources.total, sub: `已通过 ${s.resources.approved}` },
    { icon: "⏳", label: "待审核", value: s.resources.pending, sub: `已驳回 ${s.resources.rejected}` },
    { icon: "⬇️", label: "总下载量", value: s.interactions.downloads, sub: "" },
    { icon: "👍", label: "总点赞", value: s.interactions.likes, sub: "" },
    { icon: "⭐", label: "总收藏", value: s.interactions.favorites, sub: "" },
    { icon: "💬", label: "总评论", value: s.interactions.comments, sub: "" },
    { icon: "🗂️", label: "分类数", value: (s.categories || []).length, sub: "" },
  ];
  const cardsHtml = cards.map((c) => `
    <div class="stat-card">
      <div class="stat-icon">${c.icon}</div>
      <div>
        <div class="stat-value">${c.value}</div>
        <div class="stat-label">${escapeHtml(c.label)}</div>
        ${c.sub ? `<div class="stat-sub">${escapeHtml(c.sub)}</div>` : ""}
      </div>
    </div>`).join("");
  const cats = (s.categories || []).map((c) =>
    `<li><span>${escapeHtml(c.name)}</span><span class="stat-cat-count">${c.count}</span></li>`).join("");
  const top = (s.top_resources || []).slice(0, 5).map((r) =>
    `<li><span class="stat-top-title" title="${escapeAttr(r.title)}">${escapeHtml(r.title)}</span><span class="stat-top-count">⬇️ ${r.downloads || 0}</span></li>`).join("");
  grid.innerHTML = `
    <div class="stat-cards">${cardsHtml}</div>
    <div class="stat-extra">
      <div class="stat-panel">
        <h4>🗂️ 分类分布</h4>
        <ul class="stat-list">${cats || `<li class="item-empty">暂无已通过资源</li>`}</ul>
      </div>
      <div class="stat-panel">
        <h4>⬇️ 下载排行 Top5</h4>
        <ul class="stat-list">${top || `<li class="item-empty">暂无下载记录</li>`}</ul>
      </div>
    </div>`;
}

async function loadAdminQueue() {
  const list = $("adminList");
  const loading = $("adminLoading");
  const empty = $("adminEmpty");
  if (loading) loading.hidden = false;
  if (empty) empty.hidden = true;
  try {
    const res = await fetch(`${API_BASE}/api/v1/admin/resources/pending`, { headers: authHeaders() });
    if (res.status === 401 || res.status === 403) {
      if (empty) { empty.hidden = false; empty.textContent = "⚠️ 需要管理员权限，请先以管理员身份登录。"; }
      return;
    }
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (!data.length) { if (empty) empty.hidden = false; if (list) list.innerHTML = ""; return; }
    if (list) list.innerHTML = data.map(renderAdminCard).join("");
  } catch (err) {
    if (empty) { empty.hidden = false; empty.textContent = "⚠️ 加载失败：" + err.message; }
  } finally {
    if (loading) loading.hidden = true;
  }
}

function renderAdminCard(r) {
  const tags = (r.tags || []).map((t) => `<span class="tag">#${escapeHtml(t)}</span>`).join("");
  let fileLine = "";
  if (r.file_path) {
    fileLine = `<div class="res-meta"><span>📎 ${escapeHtml(r.file_name)}（${escapeHtml(fmtSize(r.file_size))}）</span>
      <a href="${API_BASE}${escapeAttr(r.file_path)}" target="_blank" rel="noopener">预览附件 ↗</a></div>`;
  } else if (r.link) {
    fileLine = `<div class="res-meta"><a href="${escapeAttr(r.link)}" target="_blank" rel="noopener">🔗 外部链接 ↗</a></div>`;
  }
  const note = r.review_note ? `<div class="res-note">上次驳回原因：${escapeHtml(r.review_note)}</div>` : "";
  return `<li class="res-card" id="card-${escapeAttr(r.id)}">
    <div class="res-head">
      <span class="res-cat">${escapeHtml(r.category || "教程")}</span>
      <span class="res-title">${escapeHtml(r.title)}</span>
      <span class="res-status ${r.status}">${r.status === "rejected" ? "已驳回" : "待审核"}</span>
    </div>
    ${r.description ? `<div class="res-desc">${mdExcerpt(r.description)}</div>` : ""}
    <div class="res-meta"><span>👤 ${escapeHtml(r.author_name || "匿名")}</span>
      <span>🕒 ${escapeHtml(fmtTime(r.created_at))}</span></div>
    ${fileLine}
    ${tags ? `<div class="item-tags">${tags}</div>` : ""}
    ${note}
    <div class="admin-actions">
      <button class="btn-approve" data-id="${escapeAttr(r.id)}">✅ 通过</button>
      <button class="btn-reject" data-id="${escapeAttr(r.id)}">❌ 驳回</button>
    </div>
  </li>`;
}

async function initAdminActions() {
  const list = $("adminList");
  if (list) {
    on(list, "click", async (e) => {
      const btn = e.target.closest("button[data-id]");
      if (!btn) return;
      const id = btn.dataset.id;
      const action = btn.classList.contains("btn-approve") ? "approve" : "reject";
      const note = action === "reject" ? (window.prompt("驳回原因（可选）：") || "") : "";
      btn.disabled = true;
      try {
        const res = await fetch(`${API_BASE}/api/v1/admin/resources/${id}/review`, {
          method: "POST",
          headers: authHeaders(),
          body: JSON.stringify({ action, note }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.detail || ("HTTP " + res.status));
        const card = $("card-" + id);
        if (card) card.remove();
        const remaining = list.querySelectorAll(".res-card").length;
        const empty = $("adminEmpty");
        if (remaining === 0 && empty) empty.hidden = false;
        loadAdminStats();
      } catch (err) {
        alert("操作失败：" + err.message);
        btn.disabled = false;
      }
    });
  }
  loadCategoryManage();
}

/* 管理后台：分类增删 */
async function loadCategoryManage() {
  const listEl = $("catManageList");
  if (!listEl) return;
  const render = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/admin/resources/categories`, { headers: authHeaders() });
      if (!res.ok) { listEl.innerHTML = `<li class="item-empty">⚠️ 加载失败</li>`; return; }
      const data = await res.json();
      const cats = data.categories || [];
      listEl.innerHTML = cats.map((c) =>
        `<li class="cat-manage-item">
          <span class="tag">#${escapeHtml(c)}</span>
          <button class="btn-link danger" data-rmcat="${escapeAttr(c)}">移除</button>
        </li>`).join("") || `<li class="item-empty">暂无分类</li>`;
      listEl.querySelectorAll("[data-rmcat]").forEach((btn) => on(btn, "click", async () => {
        if (!confirm(`确定移除分类「${btn.dataset.rmcat}」？已有资源不受影响。`)) return;
        const r = await fetch(`${API_BASE}/api/v1/admin/resources/categories`, {
          method: "POST", headers: authHeaders(),
          body: JSON.stringify({ action: "remove", name: btn.dataset.rmcat }),
        });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) { alert(d.detail || "移除失败"); return; }
        render();
      }));
    } catch (e) { listEl.innerHTML = `<li class="item-empty">⚠️ 加载失败：${escapeHtml(e.message)}</li>`; }
  };
  await render();
  on($("addCatBtn"), "click", async () => {
    const nameInput = $("newCatName");
    const name = nameInput.value.trim();
    if (!name) { alert("请输入分类名"); return; }
    const r = await fetch(`${API_BASE}/api/v1/admin/resources/categories`, {
      method: "POST", headers: authHeaders(),
      body: JSON.stringify({ action: "add", name }),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { alert(d.detail || "添加失败"); return; }
    nameInput.value = "";
    render();
  });
}
/* ---------------- 搜索页 ---------------- */
function renderSearchPage() {
  const q = new URLSearchParams(location.hash.split("?")[1] || "").get("q") || "";
  currentPage = { type: "search" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">🔍 全站搜索</h1>
      <p class="hero-sub">搜索已通过的教程 / 模型 / 资料资源</p>
    </section>
    <div class="search-hero">
      <input id="searchBigInput" type="search" placeholder="输入关键词搜索标题 / 简介 / 标签 / 作者…" value="${escapeAttr(q)}" autocomplete="off" />
      <button id="searchBigBtn" class="btn btn-primary">搜索</button>
    </div>
    <div class="res-toolbar" style="margin-top:16px">
      <select id="searchSort" class="res-sort">
        <option value="latest">🕒 最新</option>
        <option value="hottest">🔥 最热</option>
        <option value="downloads">⬇️ 最多下载</option>
        <option value="likes">👍 最多点赞</option>
      </select>
    </div>
    <div id="searchLoading" class="loading" style="margin-top:16px">正在搜索…</div>
    <ul id="searchList" class="res-list"></ul>
    <div id="searchEmpty" class="empty" hidden></div>
  </div>`;
}

async function loadSearchPage() {
  const q = new URLSearchParams(location.hash.split("?")[1] || "").get("q") || "";
  const input = $("searchBigInput");
  const list = $("searchList");
  const empty = $("searchEmpty");
  const loading = $("searchLoading");
  const sortSel = $("searchSort");
  if (!list) return;
  let sort = "latest";

  const doSearch = async () => {
    const kw = (input ? input.value.trim() : q) || q;
    if (!kw) {
      if (empty) { empty.hidden = false; empty.textContent = "请输入搜索关键词"; }
      if (loading) loading.hidden = true;
      if (list) list.innerHTML = "";
      return;
    }
    if (loading) loading.hidden = false;
    if (empty) empty.hidden = true;
    try {
      const res = await fetch(`${API_BASE}/api/v1/resources/search?q=${encodeURIComponent(kw)}&sort=${sort}`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      if (empty) { empty.hidden = data.length > 0; if (!data.length) empty.textContent = `未找到“${kw}”相关资源`; }
      if (list) list.innerHTML = data.map(renderResourceCard).join("");
      // 重新绑定点赞/收藏
      if (list) list.onclick = null;
      bindResourceListActions(list);
    } catch (err) {
      if (empty) { empty.hidden = false; empty.textContent = "⚠️ 搜索失败：" + err.message; }
    } finally {
      if (loading) loading.hidden = true;
    }
  };

  on($("searchBigBtn"), "click", () => { location.hash = `#/tutorial/search?q=${encodeURIComponent((input ? input.value.trim() : "") || "")}`; doSearch(); });
  if (input) on(input, "keydown", (e) => { if (e.key === "Enter") doSearch(); });
  if (sortSel) on(sortSel, "change", () => { sort = sortSel.value; doSearch(); });
  if (q) doSearch();
}

function bindResourceListActions(list) {
  on(list, "click", (e) => {
    const dl = e.target.closest("a[data-download]");
    if (dl) {
      const id = dl.dataset.download;
      if (id) fetch(`${API_BASE}/api/v1/resources/${id}/download`, { method: "POST" }).catch(() => {});
      return;
    }
    const likeBtn = e.target.closest("button[data-like]");
    if (likeBtn) { handleLike(likeBtn.dataset.like, likeBtn); return; }
    const favBtn = e.target.closest("button[data-fav]");
    if (favBtn) { handleFavorite(favBtn.dataset.fav, favBtn); return; }
  });
}
/* ---------------- 通知中心 ---------------- */
function renderNotificationsPage() {
  currentPage = { type: "notifications" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">🔔 消息通知</h1>
      <p class="hero-sub">私信与系统通知（点赞 / 回复 / 系统消息）</p>
    </section>
    <div class="notify-layout">
      <aside class="notify-sidebar">
        <button class="notify-tab active" data-tab="all">🔔 全部通知</button>
        <button class="notify-tab" data-tab="unread">✨ 未读</button>
        <button class="notify-tab" data-tab="messages">💬 私信</button>
        <button class="notify-tab" data-tab="blocked">🚫 屏蔽名单</button>
        <button class="notify-tab" data-tab="config">⚙️ 通知设置</button>
      </aside>
      <div class="notify-main" id="notifyMain"></div>
    </div>
  </div>`;
}

async function loadNotificationsPage() {
  if (!getUser()) { requireLogin(); return; }
  const main = $("notifyMain");
  const tabs = document.querySelectorAll(".notify-tab");
  let currentTab = "all";

  const renderTab = async (tab) => {
    currentTab = tab;
    tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
    if (!main) return;
    main.innerHTML = `<div class="loading">加载中…</div>`;
    try {
      if (tab === "messages") {
        const res = await fetch(`${API_BASE}/api/v1/notifications/messages/peers`);
        if (!res.ok) throw new Error("HTTP " + res.status);
        const peers = await res.json();
        main.innerHTML = peers.length
          ? `<ul class="dm-list">${peers.map((p) => `
            <li class="dm-item" data-peer="${escapeAttr(p.peer_id)}">
              <span class="dm-avatar" style="background:hsl(${avatarHue(p.peer_name)},62%,52%)">${escapeHtml(avatarChar(p.peer_name))}</span>
              <div class="dm-body">
                <div class="dm-head"><b>${escapeHtml(p.peer_name)}</b>${p.unread ? `<span class="dm-unread">${p.unread}</span>` : ""}</div>
                <div class="dm-last">${escapeHtml(p.last_content || "")}</div>
              </div>
            </li>`).join("")}</ul>`
          : `<div class="empty">暂无私信</div>`;
        main.querySelectorAll(".dm-item").forEach((li) => on(li, "click", () => openConversation(li.dataset.peer, li.querySelector(".dm-head b").textContent)));
      } else if (tab === "blocked") {
        const res = await fetch(`${API_BASE}/api/v1/notifications/blocks`);
        if (!res.ok) throw new Error("HTTP " + res.status);
        const blocks = await res.json();
        main.innerHTML = blocks.length
          ? `<ul class="block-list">${blocks.map((b) => `
            <li class="block-item">
              <span>${escapeHtml(b.username || b.user_id)}</span>
              <button class="btn btn-ghost btn-sm" data-unblock="${escapeAttr(b.user_id)}">解除屏蔽</button>
            </li>`).join("")}</ul>`
          : `<div class="empty">尚未屏蔽任何人</div>`;
        main.querySelectorAll("[data-unblock]").forEach((btn) => on(btn, "click", async () => {
          await fetch(`${API_BASE}/api/v1/notifications/blocks/${btn.dataset.unblock}`, { method: "DELETE" });
          renderTab("blocked");
        }));
      } else if (tab === "config") {
        main.innerHTML = renderNotifyConfig();
        initNotifyConfig();
      } else {
        const unreadOnly = tab === "unread" ? "?unread=1" : "";
        const res = await fetch(`${API_BASE}/api/v1/notifications${unreadOnly}`);
        if (!res.ok) throw new Error("HTTP " + res.status);
        const data = await res.json();
        const items = data.notifications || [];
        main.innerHTML = items.length
          ? `<button class="btn btn-ghost btn-sm" id="markAllRead" style="margin-bottom:12px">全部已读</button>
             <ul class="notif-list">${items.map(renderNotificationItem).join("")}</ul>`
          : `<div class="empty">${tab === "unread" ? "没有未读通知" : "暂无通知"}</div>`;
        const mar = $("markAllRead");
        if (mar) on(mar, "click", async () => {
          await fetch(`${API_BASE}/api/v1/notifications/read`, { method: "POST" });
          renderTab(currentTab);
          pollUnread();
        });
        main.querySelectorAll("[data-notif]").forEach((a) => on(a, "click", async () => {
          await fetch(`${API_BASE}/api/v1/notifications/read/${a.dataset.notif}`, { method: "POST" });
          pollUnread();
        }));
      }
    } catch (err) {
      main.innerHTML = `<div class="empty">⚠️ 加载失败：${escapeHtml(err.message)}</div>`;
    }
  };

  tabs.forEach((t) => on(t, "click", () => renderTab(t.dataset.tab)));
  renderTab("all");
}

function renderNotificationItem(n) {
  const iconMap = { like_comment: "👍", like_post: "❤️", reply_comment: "💬", reply_post: "💬", system: "⚙️" };
  const icon = iconMap[n.type] || "🔔";
  const cls = n.is_read ? "" : " unread";
  const inner = n.link ? `<a class="notif-item${cls}" data-notif="${escapeAttr(n.id)}" href="${escapeAttr(n.link)}">` : `<div class="notif-item${cls}" data-notif="${escapeAttr(n.id)}">`;
  const close = n.link ? "</a>" : "</div>";
  return `${inner}
    <span class="notif-icon">${icon}</span>
    <div class="notif-body">
      <div class="notif-text">${escapeHtml(n.content)}</div>
      <div class="notif-time">${escapeHtml(fmtTime(n.created_at))}</div>
    </div>${close}`;
}

let activeConversation = null;
async function openConversation(peerId, peerName) {
  const main = $("notifyMain");
  if (!main) return;
  activeConversation = { peerId, peerName };
  await renderConversation();
}

async function renderConversation() {
  const main = $("notifyMain");
  if (!main || !activeConversation) return;
  const { peerId, peerName } = activeConversation;
  try {
    const res = await fetch(`${API_BASE}/api/v1/notifications/messages/${peerId}`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const msgs = await res.json();
    const me = getUser();
    main.innerHTML = `
      <div class="chat-head">
        <button class="btn-link" id="backToPeers">← 返回</button>
        <b>与 ${escapeHtml(peerName)} 的私信</b>
      </div>
      <div class="chat-body">
        ${msgs.map((m) => {
          const mine = m.from_id === me.id;
          return `<div class="chat-msg ${mine ? "mine" : ""}">
            <div class="chat-bubble">${escapeHtml(m.content)}</div>
            <div class="chat-time">${escapeHtml(fmtTime(m.created_at))}</div>
          </div>`;
        }).join("")}
      </div>
      <div class="chat-input">
        <textarea id="chatText" placeholder="发送私信…"></textarea>
        <button id="chatSend" class="btn btn-primary">发送</button>
      </div>`;
    on($("backToPeers"), "click", () => {
      activeConversation = null;
      const tabs = document.querySelectorAll(".notify-tab");
      tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === "messages"));
      loadNotificationsPage();
    });
    on($("chatSend"), "click", async () => {
      const ta = $("chatText");
      const content = ta.value.trim();
      if (!content) return;
      const r = await fetch(`${API_BASE}/api/v1/notifications/messages`, {
        method: "POST", headers: authHeaders(),
        body: JSON.stringify({ to_id: peerId, content }),
      });
      if (!r.ok) { const d = await r.json().catch(() => ({})); alert(d.detail || "发送失败"); return; }
      renderConversation();
    });
  } catch (err) {
    main.innerHTML = `<div class="empty">⚠️ 加载失败：${escapeHtml(err.message)}</div>`;
  }
}

function renderNotifyConfig() {
  return `<div class="profile-wrap">
    <section class="profile-card">
      <h3 style="margin-bottom:14px">⚙️ 通知与隐私设置</h3>
      <label class="switch-row"><span>点赞提醒 <small>有人赞我的评论时通知我</small></span>
        <input type="checkbox" class="nf-switch" data-key="notify_like" /></label>
      <label class="switch-row"><span>回复提醒 <small>有人回复我的评论/帖子时通知我</small></span>
        <input type="checkbox" class="nf-switch" data-key="notify_reply" /></label>
      <label class="switch-row"><span>公开我的收藏 <small>允许他人查看我的收藏列表</small></span>
        <input type="checkbox" class="nf-switch" data-key="show_favorites" /></label>
    </section>
    <section class="profile-card">
      <h3 style="margin-bottom:14px">✏️ 个人签名</h3>
      <textarea id="bioText" maxlength="200" placeholder="介绍一下自己…" rows="4" style="width:100%"></textarea>
      <div style="margin-top:12px;text-align:right"><button id="saveProfile" class="btn btn-primary">保存</button></div>
    </section>
  </div>`;
}

async function initNotifyConfig() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/users/me/profile`);
    const data = await res.json();
    const prof = (data.user && data.user.profile) || {};
    document.querySelectorAll(".nf-switch").forEach((sw) => {
      sw.checked = !!prof[sw.dataset.key];
    });
    const bio = $("bioText");
    if (bio) bio.value = prof.bio || "";
  } catch (e) {}
  document.querySelectorAll(".nf-switch").forEach((sw) => on(sw, "change", () => saveProfile()));
  on($("saveProfile"), "click", () => saveProfile());
}

async function saveProfile() {
  const body = { bio: ($("bioText") || {}).value };
  document.querySelectorAll(".nf-switch").forEach((sw) => { body[sw.dataset.key] = sw.checked; });
  try {
    const res = await fetch(`${API_BASE}/api/v1/users/me/profile`, {
      method: "PATCH", headers: authHeaders(), body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    alert("✅ 已保存");
  } catch (e) { alert("保存失败：" + e.message); }
}

/* ---------------- 用户主页（他人视角） ---------------- */
function renderUserPage() {
  currentPage = { type: "user" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">👤 用户主页</h1>
      <p class="hero-sub">查看用户资料与公开动态</p>
    </section>
    <div id="userWrap" class="loading">加载中…</div>
  </div>`;
}

async function loadUserPage() {
  const mid = (location.hash.split("?")[1] || "").split("&").find((p) => p.startsWith("id="));
  const userId = mid ? decodeURIComponent(mid.slice(3)) : "";
  if (!userId) { $("userWrap").innerHTML = `<div class="empty">缺少用户 ID</div>`; return; }
  try {
    const res = await fetch(`${API_BASE}/api/v1/users/${encodeURIComponent(userId)}/profile`);
    if (!res.ok) {
      const d = await res.json().catch(() => ({}));
      $("userWrap").className = "empty";
      $("userWrap").innerHTML = `<div class="empty">⚠️ ${escapeHtml(d.detail || "无法查看该用户")}</div>`;
      return;
    }
    const data = await res.json();
    const u = data.user;
    const hue = avatarHue(u.username);
    const me = getUser();
    const canMsg = !!me && me.id !== u.id;
    $("userWrap").className = "";
    $("userWrap").innerHTML = `
      <div class="profile-wrap">
        <section class="profile-card">
          <div class="profile-head">
            <span class="avatar" style="background:hsl(${hue},62%,52%)">${escapeHtml(avatarChar(u.username))}</span>
            <div class="profile-info">
              <div class="profile-name">${escapeHtml(u.username)}</div>
              <div class="profile-meta">${u.role === "admin" ? "管理员" : "普通用户"} · 注册于 ${escapeHtml(fmtTime(u.created_at).slice(0, 10))}</div>
            </div>
            <div style="display:flex;gap:8px">
              ${canMsg ? `<button class="btn btn-primary btn-sm" id="dmUserBtn">💬 私信</button>` : ""}
              ${me && me.id !== u.id ? `<button class="btn btn-ghost btn-sm" id="blockUserBtn">🚫 屏蔽</button>` : ""}
            </div>
          </div>
          ${(u.profile && u.profile.bio) ? `<div class="profile-bio">${escapeHtml(u.profile.bio)}</div>` : ""}
          <div class="profile-stats">
            <div class="ps-item"><b>${data.stats.uploads}</b><span>上传</span></div>
            <div class="ps-item"><b>${data.stats.likes_received}</b><span>获赞</span></div>
            <div class="ps-item"><b>${data.stats.favorites_received}</b><span>被收藏</span></div>
            <div class="ps-item"><b>${data.stats.comments_made}</b><span>评论</span></div>
          </div>
        </section>
      </div>`;
    const dmBtn = $("dmUserBtn");
    if (dmBtn) on(dmBtn, "click", () => {
      location.hash = "#/tutorial/notifications";
      setTimeout(() => { const t = document.querySelector('.notify-tab[data-tab="messages"]'); if (t) t.click(); }, 200);
      // 直接打开与该用户的会话
      setTimeout(() => openConversation(u.id, u.username), 350);
    });
    const blockBtn = $("blockUserBtn");
    if (blockBtn) on(blockBtn, "click", async () => {
      if (!confirm(`确定屏蔽 ${u.username}？屏蔽后双方无法互相评论、查看主页、私信。`)) return;
      const r = await fetch(`${API_BASE}/api/v1/notifications/blocks`, {
        method: "POST", headers: authHeaders(), body: JSON.stringify({ user_id: u.id }),
      });
      if (r.ok) { alert("已屏蔽"); location.hash = "#/tutorial/platform"; }
      else { const d = await r.json().catch(() => ({})); alert(d.detail || "屏蔽失败"); }
    });
  } catch (e) {
    $("userWrap").className = "empty";
    $("userWrap").innerHTML = `<div class="empty">⚠️ 加载失败：${escapeHtml(e.message)}</div>`;
  }
}

/* ---------------- 设置页（分栏） ---------------- */
function renderSettingsPage() {
  currentPage = { type: "settings" };
  return `<div class="page">
    <section class="hero">
      <h1 class="hero-title">⚙️ 设置</h1>
      <p class="hero-sub">AI 配置 · 账户隐私 · 通知偏好</p>
    </section>
    <div class="settings-layout">
      <aside class="settings-nav">
        <button class="settings-tab active" data-tab="ai">🤖 AI 设置</button>
        <button class="settings-tab" data-tab="privacy">🔒 隐私设置</button>
        <button class="settings-tab" data-tab="notify">🔔 通知偏好</button>
        <button class="settings-tab" data-tab="account">👤 账户设置</button>
      </aside>
      <div class="settings-main" id="settingsMain"></div>
    </div>
  </div>`;
}

async function loadSettingsPage() {
  if (!getUser()) { requireLogin(); return; }
  const main = $("settingsMain");
  const tabs = document.querySelectorAll(".settings-tab");
  const renderTab = async (tab) => {
    tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === tab));
    if (tab === "ai") {
      main.innerHTML = aiSettingsPanelHtml();
      bindAiSettingsPanel();
    } else if (tab === "privacy") {
      main.innerHTML = `<div class="profile-card"><h3 style="margin-bottom:14px">🔒 隐私设置</h3>${renderNotifyConfig()}</div>`;
      initNotifyConfig();
    } else if (tab === "notify") {
      main.innerHTML = `<div class="profile-card"><h3 style="margin-bottom:14px">🔔 通知偏好</h3>${renderNotifyConfig()}</div>`;
      initNotifyConfig();
    } else if (tab === "account") {
      const u = getUser();
      main.innerHTML = `<div class="profile-card">
        <h3 style="margin-bottom:14px">👤 账户信息</h3>
        <div class="acc-row"><span>用户名</span><b>${escapeHtml(u.username)}</b></div>
        <div class="acc-row"><span>角色</span><b>${u.role === "admin" ? "管理员" : "普通用户"}</b></div>
        <div class="acc-row"><span>注册时间</span><b>${escapeHtml(fmtTime(u.created_at))}</b></div>
        <div style="margin-top:16px"><button id="accLogout" class="btn btn-ghost">退出登录</button></div>
      </div>`;
      on($("accLogout"), "click", async () => {
        try { await fetch(`${API_BASE}/api/v1/auth/logout`, { method: "POST" }); } catch (e) {}
        clearSession();
        location.hash = "#/tutorial/platform";
      });
    }
  };
  tabs.forEach((t) => on(t, "click", () => renderTab(t.dataset.tab)));
  renderTab("ai");
}

/* AI 设置面板（从弹窗改造为分栏内嵌，复用原逻辑） */
function aiSettingsPanelHtml() {
  return `<div class="profile-card">
    <h3 style="margin-bottom:14px">🤖 AI 服务配置</h3>
    <p class="hint" style="margin-bottom:16px">配置 OpenAI 兼容接口（DeepSeek / OpenAI / 通义 / 智谱 等），Key 仅保存在本地后端，不会上传到第三方。</p>
    <label class="field"><span>服务商模板</span><select id="cfgProvider"><option value="">— 自定义 —</option></select><small>选择后自动填入 Base URL</small></label>
    <label class="field"><span>API Base URL</span><input id="cfgBaseUrl" type="text" placeholder="https://api.deepseek.com/v1" /><small>仅支持公网 https/http，内网地址会被安全拦截</small></label>
    <div class="field"><span>模型</span>
      <div class="model-row">
        <input id="cfgModel" type="text" list="modelList" placeholder="deepseek-chat / gpt-4o-mini" />
        <button id="fetchModelsBtn" class="btn btn-ghost btn-sm" type="button" title="从服务商自动拉取模型列表">🔄 获取模型</button>
      </div>
      <datalist id="modelList"></datalist>
      <small id="modelsStatus" class="key-status"></small>
    </div>
    <label class="field"><span>API Key</span><input id="cfgApiKey" type="password" placeholder="sk-..." autocomplete="off" /><small id="keyStatus" class="key-status"></small>
      <button id="clearKeyBtn" class="btn-link" type="button" hidden>🗑️ 清除已保存的 Key</button></label>
    <label class="field" id="adminTokenField" hidden><span>管理令牌</span><input id="cfgAdminToken" type="password" placeholder="后端 EMOERA_ADMIN_TOKEN 的值" autocomplete="off" /><small>修改 / 测试配置需要该令牌</small></label>
    <div id="testResult" class="test-result" hidden></div>
    <div style="margin-top:16px;display:flex;gap:10px">
      <button id="testBtn" class="btn btn-ghost">测试连接</button>
      <span class="flex-spacer"></span>
      <button id="saveBtn" class="btn btn-primary">保存</button>
    </div>
  </div>`;
}

function bindAiSettingsPanel() {
  // 复用原 openSettings 的载入逻辑（内嵌版）
  loadProviders();
  (async () => {
    try {
      const res = await fetch(`${API_BASE}/api/v1/settings/ai`);
      if (!res.ok) return;
      const cfg = await res.json();
      $("cfgBaseUrl").value = cfg.base_url || "";
      $("cfgModel").value = cfg.model || "";
      $("cfgApiKey").value = "";
      $("cfgAdminToken").value = "";
      $("keyStatus").textContent = cfg.api_key_set ? `✅ 已配置 Key（${cfg.api_key_masked}）` : "尚未配置 Key";
      $("modelsStatus").textContent = "";
      $("adminTokenField").hidden = !cfg.admin_token_required;
      currentAiConfig = cfg;
      $("clearKeyBtn").hidden = !cfg.api_key_set;
    } catch (e) { $("keyStatus").textContent = "⚠️ 无法读取配置：" + e.message; }
  })();
  on($("cfgProvider"), "change", () => {
    const p = providers.find((x) => x.key === $("cfgProvider").value);
    if (p) $("cfgBaseUrl").value = p.base_url;
  });
  on($("testBtn"), "click", testConnection);
  on($("fetchModelsBtn"), "click", fetchModels);
  on($("clearKeyBtn"), "click", clearKey);
  on($("saveBtn"), "click", saveSettings);
}


let currentAiConfig = null;

function setStatus(el, text, isErr = false) {
  if (!el) return;
  el.hidden = !text;
  el.textContent = text;
  el.className = isErr ? "tut-status err" : "tut-status";
}

async function loadProviders() {
  try {
    const res = await fetch(`${API_BASE}/api/v1/settings/providers`);
    if (!res.ok) return;
    const data = await res.json();
    providers = data.providers || [];
    const select = $("cfgProvider");
    if (select) {
      select.innerHTML = '<option value="">— 自定义 —</option>' +
        providers.map((p) => `<option value="${escapeAttr(p.key)}">${escapeHtml(p.name)}</option>`).join("");
    }
  } catch (e) { /* 失败不影响使用 */ }
}

async function openSettings() {
  const modal = $("settingsModal");
  const testResult = $("testResult");
  if (testResult) testResult.hidden = true;
  if (!providers.length) await loadProviders();
  try {
    const res = await fetch(`${API_BASE}/api/v1/settings/ai`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const cfg = await res.json();
    $("cfgBaseUrl").value = cfg.base_url || "";
    $("cfgModel").value = cfg.model || "";
    $("cfgApiKey").value = "";
    $("cfgAdminToken").value = "";
    $("keyStatus").textContent = cfg.api_key_set
      ? `✅ 已配置 Key（${cfg.api_key_masked}）`
      : "尚未配置 Key";
    $("modelsStatus").textContent = "";
    $("adminTokenField").hidden = !cfg.admin_token_required;
    if (cfg.admin_token_required) {
      $("keyStatus").textContent = "🔒 后端已启用管理令牌，保存/测试需填写令牌";
    }
    currentAiConfig = cfg;
    $("clearKeyBtn").hidden = !cfg.api_key_set;
  } catch (err) {
    $("keyStatus").textContent = "⚠️ 无法读取配置：" + err.message;
  }
  modal.hidden = false;
}

function closeSettings() {
  const modal = $("settingsModal");
  if (modal) modal.hidden = true;
  const testResult = $("testResult");
  if (testResult) testResult.hidden = true;
}

function currentPayload() {
  const p = { base_url: $("cfgBaseUrl").value.trim(), model: $("cfgModel").value.trim() };
  const keyVal = $("cfgApiKey").value.trim();
  if (keyVal) p.api_key = keyVal;
  const tokenVal = $("cfgAdminToken").value.trim();
  if (tokenVal) p.admin_token = tokenVal;
  return p;
}

async function testConnection() {
  const payload = currentPayload();
  const testResult = $("testResult");
  const testBtn = $("testBtn");
  testResult.hidden = true;
  testBtn.disabled = true;
  testBtn.textContent = "测试中…";
  try {
    const res = await fetch(`${API_BASE}/api/v1/settings/ai/test`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    testResult.hidden = false;
    if (res.ok) {
      testResult.className = "test-result ok";
      testResult.textContent = `✅ ${data.message}（${data.model || ""}）`;
    } else {
      testResult.className = "test-result fail";
      testResult.textContent = `❌ ${data.detail || ("HTTP " + res.status)}`;
    }
  } catch (err) {
    testResult.hidden = false;
    testResult.className = "test-result fail";
    testResult.textContent = "❌ 请求失败：" + err.message;
  } finally {
    testBtn.disabled = false;
    testBtn.textContent = "测试连接";
  }
}

async function fetchModels() {
  const payload = currentPayload();
  const modelsStatus = $("modelsStatus");
  const fetchModelsBtn = $("fetchModelsBtn");
  if (!$("cfgApiKey").value.trim() && !(currentAiConfig && currentAiConfig.api_key_set)) {
    modelsStatus.textContent = "请先填写 API Key";
    modelsStatus.style.color = "var(--destructive)";
    return;
  }
  fetchModelsBtn.disabled = true;
  fetchModelsBtn.textContent = "获取中…";
  modelsStatus.textContent = "正在从服务商拉取模型列表…";
  modelsStatus.style.color = "var(--muted-foreground)";
  try {
    const res = await fetch(`${API_BASE}/api/v1/settings/ai/models`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    $("modelList").innerHTML = data.models.map((m) => `<option value="${escapeAttr(m)}"></option>`).join("");
    modelsStatus.textContent = `✅ ${data.message}`;
    modelsStatus.style.color = "var(--success)";
  } catch (err) {
    modelsStatus.textContent = "❌ " + err.message;
    modelsStatus.style.color = "var(--destructive)";
  } finally {
    fetchModelsBtn.disabled = false;
    fetchModelsBtn.textContent = "🔄 获取模型";
  }
}

async function saveSettings() {
  const payload = currentPayload();
  const saveBtn = $("saveBtn");
  if (!payload.base_url && !payload.model && !payload.api_key && !payload.admin_token) {
    return;
  }
  saveBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/api/v1/settings/ai`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    closeSettings();
    if (payload.api_key) {
      if (currentAiConfig) currentAiConfig.api_key_set = true;
      $("clearKeyBtn").hidden = false;
    }
    // 保存后刷新当前视图
    if (currentPage && currentPage.type === "section") loadSectionPage(true);
    else if (currentPage && currentPage.type === "ai_models") loadAiModelsPage(true);
  } catch (err) {
    alert("保存失败：" + err.message);
  } finally {
    saveBtn.disabled = false;
  }
}

async function clearKey() {
  if (!window.confirm("确定要清除已保存的 API Key 吗？此操作不可撤销。")) return;
  const body = { api_key: "" };
  const token = $("cfgAdminToken").value.trim();
  if (token) body.admin_token = token;
  try {
    const res = await fetch(`${API_BASE}/api/v1/settings/ai`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    if (currentAiConfig) currentAiConfig.api_key_set = false;
    $("clearKeyBtn").hidden = true;
    $("keyStatus").textContent = "🗑️ 已清除 Key";
    $("cfgApiKey").value = "";
  } catch (err) {
    alert("清除失败：" + err.message);
  }
}

/* ---------------- 路由表与启动 ---------------- */
function renderPage(state) {
  const app = $("app");
  if (!app) return;

  let html = "";
  if (state.board === "daily") {
    if (state.page === "home") html = renderDailyHome();
    else if (state.page === "ai_models") html = renderAiModelsPage();
    else if (SECTION_MAP[state.page]) {
      const meta = {
        news: ["🗞️ 今日时事", "来自各大中文资讯源的最新动态"],
        world: ["🌍 世界动态", "BBC · NYT · Reuters · Google News"],
        meme: ["😂 近日新梗", "国内 + 国外，梗图与热词一网打尽"],
        cloud: ["☁️ 云服务厂商日报", "AWS · Azure · 阿里云 · 谷歌云 · Cloudflare"],
        cloud_native: ["⚙️ 云原生 & 开源热榜", "Kubernetes · CNCF · Serverless · 开源基础设施"],
        ai_cloud: ["🤖 AI 上云动态", "OpenAI · Hugging Face · 通义 · Mistral"],
      }[state.page] || [state.page, ""];
      html = renderSectionPage(meta[0], meta[1], SECTION_MAP[state.page]);
    } else {
      html = renderDailyHome();
    }
  } else {
    switch (state.page) {
      case "platform": html = renderPlatformHome(); break;
      case "resources": html = renderResourcesPage(); break;
      case "upload": html = renderUploadPage(); break;
      case "favorites": html = renderMyListPage("favorites"); break;
      case "my_resources": html = renderMyListPage("mine"); break;
      case "resource": html = renderResourcePage(); break;
      case "edit": html = renderEditPage(); break;
      case "login": html = renderLoginPage(); break;
      case "profile": html = renderProfilePage(); break;
      case "user": html = renderUserPage(); break;
      case "admin": html = renderAdminPage(); break;
      case "search": html = renderSearchPage(); break;
      case "notifications": html = renderNotificationsPage(); break;
      case "settings": html = renderSettingsPage(); break;
      default: html = renderPlatformHome();
    }
  }
  app.innerHTML = html;
  window.scrollTo({ top: 0 });
  renderHeader(state);

  // 依据视图执行初始化
  if (state.board === "daily") {
    if (SECTION_MAP[state.page]) loadSectionPage(false);
    else if (state.page === "ai_models") loadAiModelsPage(false);
  } else {
    switch (state.page) {
      case "resources": initResourceFilters(); loadCategories(); loadResources(); break;
      case "resource": loadResourceDetail(); break;
      case "edit": loadEditPage(); initEdit(); break;
      case "favorites": loadMyList("favorites"); break;
      case "my_resources": loadMyList("mine"); break;
      case "upload": initUpload(); break;
      case "login": initLogin(); break;
      case "profile": renderProfile(); break;
      case "user": loadUserPage(); break;
      case "admin": loadAdminStats(); loadAdminQueue(); initAdminActions(); break;
      case "search": loadSearchPage(); break;
      case "notifications": loadNotificationsPage(); break;
      case "settings": loadSettingsPage(); break;
    }
  }
}

function route() {
  const state = parseHash();
  if (state.board === "daily") {
    if (state.page !== "home" && state.page !== "ai_models" && !SECTION_MAP[state.page]) {
      location.hash = "#/daily/home";
      return;
    }
  } else {
    const valid = ["platform", "resources", "upload", "favorites", "my_resources", "resource", "edit", "login", "profile", "user", "admin", "search", "notifications", "settings"];
    if (!valid.includes(state.page)) {
      location.hash = "#/tutorial/platform";
      return;
    }
  }
  renderPage(state);
}

function bindGlobalEvents() {
  on($("settingsBtn"), "click", () => { location.hash = "#/tutorial/settings"; });
  on($("themeBtn"), "click", toggleTheme);
  on($("testBtn"), "click", testConnection);
  on($("fetchModelsBtn"), "click", fetchModels);
  on($("clearKeyBtn"), "click", clearKey);
  on($("saveBtn"), "click", saveSettings);

  const modal = $("settingsModal");
  if (modal) {
    modal.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", closeSettings));
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && !modal.hidden) closeSettings();
  });

  // 事件委托：速报条目 / 模型卡片点击打开外链
  const app = $("app");
  on(app, "click", (e) => {
    if (e.target.closest("a, button, input, textarea, select, label")) return;
    const item = e.target.closest(".item, .model-card");
    if (!item) return;
    const url = item.dataset.url;
    if (url) window.open(url, "_blank", "noopener");
  });

  // 刷新按钮（速报 / 模型页动态渲染）
  on(app, "click", (e) => {
    const btn = e.target.closest("#refreshBtn");
    if (!btn) return;
    if (currentPage && currentPage.type === "ai_models") loadAiModelsPage(true);
    else if (currentPage && currentPage.type === "section") loadSectionPage(true);
  });
}

applyTheme();
bindGlobalEvents();
window.addEventListener("hashchange", route);
route();

