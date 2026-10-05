const state = {
  all: [],
  navigation: [],
  tree: new Map(),
  moviesBySource: [],
  current: [],
  filtered: [],
  selectedSection: "",
  selectedTab: "",
  expandedTab: "",
  selectedSource: -1,
  page: 1,
  pageSize: 50,
};

const elements = {
  sections: document.querySelector("#section-tabs"),
  categories: document.querySelector("#category-tabs"),
  selection: document.querySelector("#selection"),
  rows: document.querySelector("#movie-rows"),
  status: document.querySelector("#status"),
  updated: document.querySelector("#updated"),
  search: document.querySelector("#search"),
  pageSize: document.querySelector("#page-size"),
  firstPage: document.querySelector("#first-page"),
  previous: document.querySelector("#previous"),
  pageNumber: document.querySelector("#page-number"),
  pageTotal: document.querySelector("#page-total"),
  jumpPage: document.querySelector("#jump-page"),
  next: document.querySelector("#next"),
  lastPage: document.querySelector("#last-page"),
};

const integerFormat = new Intl.NumberFormat("zh-CN");

function makeCell(className, text) {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = text;
  return cell;
}

function makeButton(label, active, onClick, className = "nav-button", count = null) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.classList.toggle("is-active", active);
  button.setAttribute("aria-pressed", String(active));
  const text = document.createElement("span");
  text.className = "button-label";
  text.textContent = label;
  button.append(text);
  if (count !== null) {
    const badge = document.createElement("small");
    badge.textContent = integerFormat.format(count);
    button.append(badge);
  }
  button.addEventListener("click", onClick);
  return button;
}

function openMovie(url) {
  window.open(url, "_blank", "noopener,noreferrer");
}

function buildTree() {
  state.tree = new Map();
  state.navigation.forEach((source, sourceIndex) => {
    if (!state.tree.has(source.section)) state.tree.set(source.section, new Map());
    const tabs = state.tree.get(source.section);
    if (!tabs.has(source.tab)) tabs.set(source.tab, []);
    tabs.get(source.tab).push(sourceIndex);
  });
}

function selectFirstSource() {
  const tabs = state.tree.get(state.selectedSection);
  if (!tabs) return;
  if (!tabs.has(state.selectedTab)) state.selectedTab = tabs.keys().next().value;
  const sources = tabs.get(state.selectedTab);
  if (!sources.includes(state.selectedSource)) state.selectedSource = sources[0];
}

function renderNavigation() {
  selectFirstSource();
  const sectionFragment = document.createDocumentFragment();
  state.tree.forEach((_, section) => {
    sectionFragment.append(makeButton(section, section === state.selectedSection, () => {
      state.selectedSection = section;
      state.selectedTab = state.tree.get(section).keys().next().value;
      state.expandedTab = state.selectedTab;
      state.selectedSource = -1;
      updateSelection();
    }, "section-button"));
  });
  elements.sections.replaceChildren(sectionFragment);

  const tabs = state.tree.get(state.selectedSection);
  const tabFragment = document.createDocumentFragment();
  tabs.forEach((sourceIndexes, tab) => {
    const active = tab === state.selectedTab;
    const expanded = tab === state.expandedTab;
    const item = document.createElement("section");
    item.className = "category-item";
    const tabButton = makeButton(tab, active, () => {
      if (expanded) {
        state.expandedTab = "";
        renderNavigation();
        return;
      }
      state.expandedTab = tab;
      if (active) {
        renderNavigation();
        return;
      }
      state.selectedTab = tab;
      state.selectedSource = -1;
      updateSelection();
    }, "category-button");
    tabButton.setAttribute("aria-label", tab);
    tabButton.setAttribute("aria-expanded", String(expanded));
    item.append(tabButton);

    if (expanded) {
      const grouped = new Map();
      sourceIndexes.forEach((sourceIndex) => {
        const source = state.navigation[sourceIndex];
        const group = source.group || "";
        if (!grouped.has(group)) grouped.set(group, []);
        grouped.get(group).push(sourceIndex);
      });
      const values = document.createElement("div");
      values.className = "accordion-values";
      grouped.forEach((groupSourceIndexes, group) => {
        const wrapper = document.createElement("div");
        wrapper.className = "value-group";
        if (group) {
          const heading = document.createElement("p");
          heading.className = "value-group__title";
          heading.textContent = group;
          wrapper.append(heading);
        }
        const buttons = document.createElement("div");
        buttons.className = "value-buttons";
        groupSourceIndexes.forEach((sourceIndex) => {
          const source = state.navigation[sourceIndex];
          const valueButton = makeButton(source.value, sourceIndex === state.selectedSource, () => {
            state.selectedSource = sourceIndex;
            updateSelection();
            if (window.innerWidth <= 960 && typeof closeDrawer === "function") {
              closeDrawer();
            }
          }, "value-button", state.moviesBySource[sourceIndex].length);
          if (source.section === "分类排行榜" && source.tab === "精选豆列") {
            valueButton.classList.add("is-truncated");
            valueButton.title = source.value;
          }
          buttons.append(valueButton);
        });
        wrapper.append(buttons);
        values.append(wrapper);
      });
      item.append(values);
    }
    tabFragment.append(item);
  });
  elements.categories.replaceChildren(tabFragment);
}

function updateSelection() {
  selectFirstSource();
  renderNavigation();
  const source = state.navigation[state.selectedSource];
  state.current = state.moviesBySource[state.selectedSource] || [];
  const path = [source.section, source.tab, source.group, source.value]
    .filter((part, index, values) => part && values.indexOf(part) === index);
  elements.selection.textContent = path.join(" / ");
  const mobileSel = document.getElementById("mobileCurrentSelection");
  if (mobileSel) mobileSel.textContent = path.join(" / ");
  state.page = 1;
  applySearch();
}

function render() {
  const totalPages = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));
  state.page = Math.min(state.page, totalPages);
  const start = (state.page - 1) * state.pageSize;
  const visible = state.filtered.slice(start, start + state.pageSize);
  const fragment = document.createDocumentFragment();

  if (visible.length === 0) {
    const row = document.createElement("tr");
    const cell = makeCell("message", "没有找到匹配的影视条目");
    cell.colSpan = 5;
    row.append(cell);
    fragment.append(row);
  } else {
    visible.forEach((movie, index) => {
      const row = document.createElement("tr");
      row.dataset.url = movie.url;
      row.tabIndex = 0;
      row.setAttribute("role", "link");
      row.setAttribute("aria-label", `在豆瓣打开《${movie.title}》`);
      row.addEventListener("click", () => openMovie(movie.url));
      row.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openMovie(movie.url);
        }
      });
      row.append(
        makeCell("rank", integerFormat.format(start + index + 1)),
        makeCell("id", movie.id),
        makeCell("title", movie.title),
        makeCell("number rating", Number(movie.rating).toFixed(1)),
        makeCell("number", integerFormat.format(movie.rating_count)),
      );
      fragment.append(row);
    });
  }

  elements.rows.replaceChildren(fragment);
  const query = elements.search.value.trim();
  elements.status.textContent = query
    ? `在 ${integerFormat.format(state.current.length)} 部作品中找到 ${integerFormat.format(state.filtered.length)} 部`
    : `共 ${integerFormat.format(state.current.length)} 部影视作品`;
  elements.pageNumber.max = String(totalPages);
  elements.pageNumber.value = String(state.page);
  elements.pageTotal.textContent = `/ ${totalPages} 页`;
  elements.firstPage.disabled = state.page <= 1;
  elements.previous.disabled = state.page <= 1;
  elements.next.disabled = state.page >= totalPages;
  elements.lastPage.disabled = state.page >= totalPages;
  elements.pageNumber.disabled = state.filtered.length === 0;
  elements.jumpPage.disabled = state.filtered.length === 0;
}

function applySearch() {
  const query = elements.search.value.trim().toLocaleLowerCase("zh-CN");
  state.filtered = query
    ? state.current.filter((movie) => movie.id.includes(query) || movie.title.toLocaleLowerCase("zh-CN").includes(query))
    : state.current;
  state.page = 1;
  render();
}

elements.search.addEventListener("input", applySearch);
elements.pageSize.addEventListener("change", () => {
  state.pageSize = Number(elements.pageSize.value);
  state.page = 1;
  render();
});

function scrollToResults() {
  window.scrollTo({ top: document.querySelector(".toolbar").offsetTop, behavior: "smooth" });
}

function jumpToPage() {
  const totalPages = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));
  const requestedPage = Number.parseInt(elements.pageNumber.value, 10);
  if (!Number.isFinite(requestedPage)) {
    elements.pageNumber.value = String(state.page);
    return;
  }
  state.page = Math.min(totalPages, Math.max(1, requestedPage));
  render();
  scrollToResults();
}

elements.firstPage.addEventListener("click", () => {
  state.page = 1;
  render();
  scrollToResults();
});
elements.previous.addEventListener("click", () => {
  state.page -= 1;
  render();
  scrollToResults();
});
elements.jumpPage.addEventListener("click", jumpToPage);
elements.pageNumber.addEventListener("keydown", (event) => {
  if (event.key === "Enter") jumpToPage();
});
elements.next.addEventListener("click", () => {
  state.page += 1;
  render();
  scrollToResults();
});
elements.lastPage.addEventListener("click", () => {
  state.page = Math.max(1, Math.ceil(state.filtered.length / state.pageSize));
  render();
  scrollToResults();
});

fetch("data/movies.json?v=20260811-7")
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then((payload) => {
    state.all = payload.movies;
    state.navigation = payload.navigation;
    state.moviesBySource = state.navigation.map(() => []);
    state.all.forEach((movie) => {
      movie.sources.forEach((sourceIndex) => {
        if (state.moviesBySource[sourceIndex]) state.moviesBySource[sourceIndex].push(movie);
      });
    });
    buildTree();
    state.selectedSection = state.tree.keys().next().value;
    state.selectedTab = state.tree.get(state.selectedSection).keys().next().value;
    state.expandedTab = state.selectedTab;
    if (payload.generated_at) {
      const updated = new Date(payload.generated_at);
      elements.updated.textContent = `数据更新时间：${updated.toLocaleString("zh-CN", { hour12: false })}`;
    }
    elements.search.disabled = false;
    elements.pageSize.disabled = false;
    updateSelection();
  })
  .catch((error) => {
    elements.status.textContent = "数据载入失败";
    const row = document.createElement("tr");
    const cell = makeCell("message", `无法载入排行榜数据：${error.message}`);
    cell.colSpan = 5;
    row.append(cell);
    elements.rows.replaceChildren(row);
  });


// ---- 主题切换系统与移动端抽屉控制器 ----
const themeToggleBtn = document.getElementById("theme-toggle-btn");
const mobileThemeToggle = document.getElementById("mobile-theme-toggle");
const drawerLayer = document.getElementById("mobile-drawer-layer");
const drawerToggle = document.getElementById("mobile-drawer-toggle");
const drawerClose = document.getElementById("mobile-drawer-close");
const drawerBackdrop = document.getElementById("mobile-drawer-backdrop");
const formulaModal = document.getElementById("formula-modal");
const closeFormulaModalBtn = document.getElementById("closeFormulaModal");
const mobileDrawerFormula = document.getElementById("mobileDrawerFormula");
const mobileDrawerSearch = document.getElementById("mobileDrawerSearch");
const mobileSectionNav = document.getElementById("mobile-section-nav");

function getStoredTheme() {
  const saved = localStorage.getItem("douban_movies_theme");
  if (saved === "dark" || saved === "light") return saved;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  const isDark = theme === "dark";
  document.documentElement.setAttribute("data-theme", isDark ? "dark" : "light");
  try {
    localStorage.setItem("douban_movies_theme", theme);
  } catch (_) {}

  const navSun = document.getElementById("theme-icon-sun");
  const navMoon = document.getElementById("theme-icon-moon");
  if (navSun) navSun.style.display = isDark ? "none" : "inline-block";
  if (navMoon) navMoon.style.display = isDark ? "inline-block" : "none";

  const drawerSun = document.getElementById("drawer-theme-icon-sun");
  const drawerMoon = document.getElementById("drawer-theme-icon-moon");
  if (drawerSun) drawerSun.style.display = isDark ? "none" : "inline-block";
  if (drawerMoon) drawerMoon.style.display = isDark ? "inline-block" : "none";
}

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme") || getStoredTheme();
  applyTheme(current === "dark" ? "light" : "dark");
}

applyTheme(getStoredTheme());

if (themeToggleBtn) themeToggleBtn.addEventListener("click", toggleTheme);
if (mobileThemeToggle) mobileThemeToggle.addEventListener("click", toggleTheme);

function openDrawer() {
  if (drawerLayer) {
    drawerLayer.removeAttribute("hidden");
    drawerLayer.hidden = false;
    document.body.style.overflow = "hidden";
    renderMobileSections();
  }
}

function closeDrawer() {
  if (drawerLayer) {
    drawerLayer.setAttribute("hidden", "");
    drawerLayer.hidden = true;
    document.body.style.overflow = "";
  }
}

if (drawerToggle) drawerToggle.addEventListener("click", openDrawer);
if (drawerClose) drawerClose.addEventListener("click", closeDrawer);
if (drawerBackdrop) drawerBackdrop.addEventListener("click", closeDrawer);

window.addEventListener("keydown", (e) => {
  const isInputActive = ["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName);
  if ((e.key === "d" || e.key === "D") && !isInputActive) {
    e.preventDefault();
    toggleTheme();
  } else if (e.key === "Escape") {
    if (formulaModal && !formulaModal.hidden) {
      closeFormulaModal();
    } else if (drawerLayer && !drawerLayer.hidden) {
      closeDrawer();
    }
  }
});

function openFormulaModal() {
  if (formulaModal) {
    formulaModal.removeAttribute("hidden");
    formulaModal.hidden = false;
    document.body.style.overflow = "hidden";
  }
}

function closeFormulaModal() {
  if (formulaModal) {
    formulaModal.setAttribute("hidden", "");
    formulaModal.hidden = true;
    document.body.style.overflow = "";
  }
}

if (closeFormulaModalBtn) closeFormulaModalBtn.addEventListener("click", closeFormulaModal);
if (formulaModal) {
  formulaModal.addEventListener("click", (e) => {
    if (e.target === formulaModal) closeFormulaModal();
  });
}
if (mobileDrawerFormula) {
  mobileDrawerFormula.addEventListener("click", () => {
    closeDrawer();
    openFormulaModal();
  });
}
if (mobileDrawerSearch) {
  mobileDrawerSearch.addEventListener("click", () => {
    closeDrawer();
    if (elements.search) {
      elements.search.focus();
      elements.search.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  });
}

function renderMobileSections() {
  if (!mobileSectionNav || !state.tree || state.tree.size === 0) return;
  mobileSectionNav.replaceChildren();
  state.tree.forEach((_, section) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "mobile-nav-item";
    if (section === state.selectedSection) btn.classList.add("is-active");
    btn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="m9 18 6-6-6-6"/></svg>
      <span>${section}</span>
    `;
    btn.addEventListener("click", () => {
      state.selectedSection = section;
      state.selectedTab = state.tree.get(section).keys().next().value;
      state.expandedTab = state.selectedTab;
      state.selectedSource = -1;
      updateSelection();
      closeDrawer();
    });
    mobileSectionNav.append(btn);
  });
}

function checkNavbarWrap() {
  const isNarrow = window.innerWidth <= 720;
  document.body.classList.toggle("header-collapsed", isNarrow);
}
window.addEventListener("resize", checkNavbarWrap);
checkNavbarWrap();


// 动态响应式转移 Catalog 导航节点（桌面端放入左侧侧边栏，移动端放入侧滑抽屉）
function syncCatalogPlacement() {
  const isMobile = window.innerWidth <= 960;
  const desktopSlot = document.getElementById("desktop-catalog-slot");
  const drawerSlot = document.getElementById("drawer-catalog-slot");
  const catalog = document.getElementById("catalog");
  if (!catalog || !desktopSlot || !drawerSlot) return;

  if (isMobile) {
    if (drawerSlot.firstElementChild !== catalog) {
      drawerSlot.appendChild(catalog);
    }
  } else {
    if (desktopSlot.firstElementChild !== catalog) {
      desktopSlot.appendChild(catalog);
    }
  }
}

window.addEventListener("resize", syncCatalogPlacement);
syncCatalogPlacement();

const openDrawerFromFilter = document.getElementById("openDrawerFromFilter");
if (openDrawerFromFilter) {
  openDrawerFromFilter.addEventListener("click", openDrawer);
}
