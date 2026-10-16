const api = {
  async get(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(await r.text());
    return r.status === 204 ? null : r.json();
  },
  async send(method, url, body) {
    const r = await fetch(url, {
      method,
      headers: {'Content-Type': 'application/json'},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error(await r.text());
    return r.status === 204 ? null : r.json();
  },
};

const state = {
  groups: [],
  currentGroupId: null,
  prompts: [],
  editingGroupId: null,
  editingPromptId: null,
};

state.filters = {
  search: "",
  favoritesOnly: false,
  minRating: 0,
  sort: "favorite",
};

state.theme = "dark";

const $ = (id) => document.getElementById(id); /* jQuery emulate */

function cfgClass(cfg) {
  const g = window.QIQI.cfgGreen, o = window.QIQI.cfgOrange;
  if (cfg >= g[0] && cfg <= g[1]) return 'cfg-green';
  if (cfg >= o[0] && cfg <= o[1]) return 'cfg-orange';
  return 'cfg-red';
}

function renderMeta() {
  const g = window.QIQI.cfgGreen, o = window.QIQI.cfgOrange;
  $('meta').textContent =
    `cfg зелёная: ${g[0]}–${g[1]}, оранжевая: ${o[0]}–${o[1]}, по умолчанию: ${window.QIQI.defaultCfg}`;
}

async function loadGroups() {
  state.groups = await api.get('/api/groups');
  const ul = $('groupsList');
  ul.innerHTML = '';
  for (const g of state.groups) {
    const li = document.createElement('li');
    li.dataset.id = g.id;
    if (g.id === state.currentGroupId) li.classList.add('active');
    li.innerHTML = `
      <span class="name">${escapeHtml(g.name)}</span>
      <span class="cnt">${g.prompts_count}</span>
    `;
    li.onclick = () => selectGroup(g.id);
    li.ondblclick = (e) => { e.stopPropagation(); openGroupModal(g.id); };
    ul.appendChild(li);
  }
}

async function selectGroup(id) {
  state.currentGroupId = id;
  const g = state.groups.find(x => x.id === id);
  $('currentGroupName').textContent = g ? g.name : '—';
  $('newPromptBtn').disabled = !id;
  try {
    await api.send('PATCH', '/api/settings', { last_group_id: id });
  } catch (e) { /* не критично */ }
  await loadGroups();
  await loadPrompts();
}

async function loadPrompts() {
  if (!state.currentGroupId) {
    state.prompts = [];
    $('promptsList').innerHTML = '';
    return;
  }
  state.prompts = await api.get(`/api/prompts?${filtersToQuery()}`);
  renderPrompts();
}

function renderPrompts() {
  const box = $('promptsList');
  box.innerHTML = '';
  if (!state.prompts.length) {
    box.innerHTML = '<div style="color:#8b8f99;padding:20px">Промптов пока нет. Нажми «+ промпт».</div>';
    return;
  }
  for (const p of state.prompts) {
    const card = document.createElement('div');
    card.className = 'prompt-card';
    const excerpt = (p.positive || '').slice(0, 180);
    card.innerHTML = `
      <div class="title-row">
        ${p.favorite ? '<span class="fav">★</span>' : ''}
        <span class="title">${escapeHtml(p.title || '(без названия)')}</span>
        <span class="cfg-badge ${cfgClass(p.cfg)}">${p.cfg}</span>
        ${p.no_negative ? '<span class="cfg-badge cfg-red" title="без негатива">no-neg</span>' : ''}
      </div>
      <div class="excerpt">${escapeHtml(excerpt)}</div>
      <div class="footer">
        <span>${escapeHtml((p.comment || '').slice(0, 80))}</span>
      </div>
    `;
    card.onclick = () => openPromptModal(p.id);
    box.appendChild(card);
  }
}

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

// ---------- group modal ----------

function openGroupModal(id = null) {
  state.editingGroupId = id;
  const modal = $('groupModal');
  const isNew = id == null;
  $('groupModalTitle').textContent = isNew ? 'Новая группа' : 'Группа';
  $('groupDeleteBtn').style.display = isNew ? 'none' : 'inline-block';
  if (isNew) {
    $('groupName').value = '';
    $('groupComment').value = '';
  } else {
    const g = state.groups.find(x => x.id === id);
    $('groupName').value = g.name;
    $('groupComment').value = g.comment || '';
  }
  modal.classList.remove('hidden');
  setTimeout(() => { $('groupName').focus(); $('groupName').select(); }, 0);
}

async function saveGroup() {
  const name = $('groupName').value.trim();
  const comment = $('groupComment').value;
  if (!name) return alert('Название обязательно');
  if (state.editingGroupId == null) {
    const g = await api.send('POST', '/api/groups', {name, comment});
    state.currentGroupId = g.id;
  } else {
    await api.send('PATCH', `/api/groups/${state.editingGroupId}`, {name, comment});
  }
  $('groupModal').classList.add('hidden');
  await loadGroups();
  await loadPrompts();
}

async function deleteGroup() {
  if (!confirm('Удалить группу со всеми промптами?')) return;
  await api.send('DELETE', `/api/groups/${state.editingGroupId}`);
  if (state.currentGroupId === state.editingGroupId) state.currentGroupId = null;
  $('groupModal').classList.add('hidden');
  await loadGroups();
  await loadPrompts();
}

// ---------- prompt modal ----------

// ---------- prompt modal ----------

const CFG_MAX = 6; // верхняя граница слайдера

function setCfgSlider(value) {
  const slider = $('pCfg');
  const v = Number.isFinite(value) ? value : window.QIQI.defaultCfg;
  const clamped = Math.max(0, Math.min(CFG_MAX, v));
  slider.value = String(clamped);
  updateCfgVisual();
}

function updateCfgVisual() {
  const slider = $('pCfg');
  const v = parseFloat(slider.value);
  $('pCfgValue').textContent = v.toFixed(1);

  slider.classList.remove('cfg-green', 'cfg-orange', 'cfg-red');
  slider.classList.add(cfgClass(v));
}

function applyNoNegative() {
  const noNeg = $('pNoNegative').checked;
  const slider = $('pCfg');
  if (noNeg) {
    setCfgSlider(1.0);
    slider.disabled = true;
  } else {
    slider.disabled = false;
  }
}

function openPromptModal(id = null) {
  state.editingPromptId = id;
  const modal = $('promptModal');
  const isNew = id == null;
  $('promptModalTitle').textContent = isNew ? 'Новый промпт' : 'Промпт';
  $('promptDeleteBtn').style.display = isNew ? 'none' : 'inline-block';

  if (isNew) {
    $('pTitle').value = '';
    $('pPositive').value = '';
    $('pNegative').value = '';
    $('pNoNegative').checked = false;
    $('pFavorite').checked = false;
    $('pComment').value = '';
    setCfgSlider(window.QIQI.defaultCfg);
    $('pCfg').disabled = false;
  } else {
    const p = state.prompts.find(x => x.id === id);
    $('pTitle').value = p.title || '';
    $('pPositive').value = p.positive || '';
    $('pNegative').value = p.negative || '';
    $('pNoNegative').checked = !!p.no_negative;
    $('pFavorite').checked = !!p.favorite;
    $('pComment').value = p.comment || '';
    setCfgSlider(p.cfg);
    applyNoNegative();
  }

  modal.classList.remove('hidden');

  // фокус в "Название"
  setTimeout(() => {
    $('pTitle').focus();
    $('pTitle').select();
  }, 0);
}

async function savePrompt() {
  const noNeg = $('pNoNegative').checked;
  const payload = {
    group_id: state.currentGroupId,
    title: $('pTitle').value,
    positive: $('pPositive').value,
    negative: $('pNegative').value,
    no_negative: noNeg,
    cfg: noNeg ? 1.0 : (parseFloat($('pCfg').value) || 0),
    favorite: $('pFavorite').checked,
    comment: $('pComment').value,
  };
  if (state.editingPromptId == null) {
    await api.send('POST', '/api/prompts', payload);
  } else {
    await api.send('PATCH', `/api/prompts/${state.editingPromptId}`, payload);
  }
  $('promptModal').classList.add('hidden');
  await loadPrompts();
  await loadGroups();
}

async function deletePrompt() {
  if (!confirm('Удалить промпт?')) return;
  await api.send('DELETE', `/api/prompts/${state.editingPromptId}`);
  $('promptModal').classList.add('hidden');
  await loadPrompts();
  await loadGroups();
}

// ---------- theme ----------

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.setAttribute("data-theme", theme);
  $('themeToggle').textContent = theme === "dark" ? "🌙" : "☀️";
}

async function toggleTheme() {
  const next = state.theme === "dark" ? "light" : "dark";
  applyTheme(next);
  try {
    await api.send('PATCH', '/api/settings', { theme: next });
  } catch (e) {
    console.warn('Не удалось сохранить тему', e);
  }
}

// ---------- filters ----------

function filtersToQuery() {
  const p = new URLSearchParams();
  if (state.currentGroupId) p.set('group_id', state.currentGroupId);
  if (state.filters.search) p.set('search', state.filters.search);
  if (state.filters.favoritesOnly) p.set('favorites_only', 'true');
  if (state.filters.minRating > 0) p.set('min_rating', state.filters.minRating);
  p.set('sort', state.filters.sort);
  return p.toString();
}

function bindFilters() {
  let debounce = null;
  $('fSearch').addEventListener('input', () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      state.filters.search = $('fSearch').value.trim();
      loadPrompts();
    }, 200);
  });
  $('fFav').addEventListener('change', () => {
    state.filters.favoritesOnly = $('fFav').checked;
    loadPrompts();
  });
  $('fMinRating').addEventListener('input', () => {
    state.filters.minRating = parseInt($('fMinRating').value, 10) || 0;
    loadPrompts();
  });
  $('fSort').addEventListener('change', () => {
    state.filters.sort = $('fSort').value;
    loadPrompts();
  });
  $('fReset').addEventListener('click', () => {
    state.filters = { search: "", favoritesOnly: false, minRating: 0, sort: "favorite" };
    $('fSearch').value = "";
    $('fFav').checked = false;
    $('fMinRating').value = 0;
    $('fSort').value = "favorite";
    loadPrompts();
  });
}

// ---------- bindings ----------

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Сначала тянем мета-настройки (cfg-зоны, default_cfg).
  try {
    const meta = await api.get('/api/meta');
    window.QIQI = {
      cfgGreen: meta.cfg_green,
      cfgOrange: meta.cfg_orange,
      defaultCfg: meta.default_cfg,
    };
  } catch (e) {
    console.warn('Не удалось получить /api/meta, использую значения по умолчанию', e);
  }

  try {
    const meta = await api.get('/api/meta');
    window.QIQI = {
      cfgGreen: meta.cfg_green,
      cfgOrange: meta.cfg_orange,
      defaultCfg: meta.default_cfg,
    };
  } catch (e) { /* ... */ }

  let settings = { theme: "dark", last_group_id: null };
  try {
    settings = await api.get('/api/settings');
  } catch (e) { console.warn('settings недоступны', e); }

  applyTheme(settings.theme || "dark");
  bindFilters();
  $('themeToggle').addEventListener('click', toggleTheme);

  renderMeta();
  await loadGroups();

  if (settings.last_group_id && state.groups.some(g => g.id === settings.last_group_id)) {
    await selectGroup(settings.last_group_id);
  }

  $('newGroupBtn').onclick = () => openGroupModal(null);
  $('groupSaveBtn').onclick = saveGroup;
  $('groupDeleteBtn').onclick = deleteGroup;

  $('newPromptBtn').onclick = () => openPromptModal(null);
  $('promptSaveBtn').onclick = savePrompt;
  $('promptDeleteBtn').onclick = deletePrompt;

  $('pCfg').addEventListener('input', updateCfgVisual);
    $('pNoNegative').addEventListener('change', applyNoNegative);

  document.querySelectorAll('[data-close]').forEach(b => {
    b.onclick = () => b.closest('.modal').classList.add('hidden');
  });
  document.querySelectorAll('.modal').forEach(m => {
    m.addEventListener('click', (e) => {
      if (e.target === m) m.classList.add('hidden');
    });
  });
});

document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  const open = document.querySelector('.modal:not(.hidden)');
  if (open) open.classList.add('hidden');
});

