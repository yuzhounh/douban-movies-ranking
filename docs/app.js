const state = {
  all: [],
  filtered: [],
  page: 1,
  pageSize: 50,
};

const elements = {
  rows: document.querySelector("#movie-rows"),
  status: document.querySelector("#status"),
  updated: document.querySelector("#updated"),
  search: document.querySelector("#search"),
  pageSize: document.querySelector("#page-size"),
  previous: document.querySelector("#previous"),
  next: document.querySelector("#next"),
  pageInfo: document.querySelector("#page-info"),
};

const integerFormat = new Intl.NumberFormat("zh-CN");

function makeCell(className, text) {
  const cell = document.createElement("td");
  if (className) cell.className = className;
  cell.textContent = text;
  return cell;
}

function openMovie(url) {
  window.open(url, "_blank", "noopener,noreferrer");
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
  elements.status.textContent = state.filtered.length === state.all.length
    ? `共 ${integerFormat.format(state.all.length)} 部影视作品`
    : `找到 ${integerFormat.format(state.filtered.length)} 部作品`;
  elements.pageInfo.textContent = `第 ${state.page} / ${totalPages} 页`;
  elements.previous.disabled = state.page <= 1;
  elements.next.disabled = state.page >= totalPages;
}

function applySearch() {
  const query = elements.search.value.trim().toLocaleLowerCase("zh-CN");
  state.filtered = query
    ? state.all.filter((movie) => movie.id.includes(query) || movie.title.toLocaleLowerCase("zh-CN").includes(query))
    : state.all;
  state.page = 1;
  render();
}

elements.search.addEventListener("input", applySearch);
elements.pageSize.addEventListener("change", () => {
  state.pageSize = Number(elements.pageSize.value);
  state.page = 1;
  render();
});
elements.previous.addEventListener("click", () => {
  state.page -= 1;
  render();
  window.scrollTo({ top: document.querySelector(".toolbar").offsetTop, behavior: "smooth" });
});
elements.next.addEventListener("click", () => {
  state.page += 1;
  render();
  window.scrollTo({ top: document.querySelector(".toolbar").offsetTop, behavior: "smooth" });
});

fetch("data/movies.json?v=20260810-1")
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then((payload) => {
    state.all = payload.movies;
    state.filtered = state.all;
    if (payload.generated_at) {
      const updated = new Date(payload.generated_at);
      elements.updated.textContent = `数据更新时间：${updated.toLocaleString("zh-CN", { hour12: false })}`;
    }
    elements.search.disabled = false;
    elements.pageSize.disabled = false;
    render();
  })
  .catch((error) => {
    elements.status.textContent = "数据载入失败";
    elements.rows.innerHTML = `<tr><td colspan="5" class="message">无法载入排行榜数据：${error.message}</td></tr>`;
  });
