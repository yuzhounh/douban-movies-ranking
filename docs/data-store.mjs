// Shared by desktop and mobile. Full titles/IDs are requested only for a search.
export class MovieData {
  constructor(base = "data/", fetcher = (url, options) => fetch(url, options), { timeoutMs = 30_000 } = {}) {
    this.base = base;
    this.fetcher = fetcher;
    this.timeoutMs = timeoutMs;
    this.caches = { source: new Map(), members: new Map(), page: new Map() };
    this.pending = new Map();
    this.active = 0;
    this.waiters = [];
  }

  async json(name, options) {
    if (this.active >= 3) await new Promise(resolve => this.waiters.push(resolve));
    else this.active += 1;
    // Each physical request owns its deadline; all shared readers keep the same
    // result, and a stalled response body cannot hold a download slot forever.
    const controller = new AbortController();
    const forwardAbort = () => controller.abort(options.signal.reason);
    if (options?.signal?.aborted) forwardAbort();
    else options?.signal?.addEventListener("abort", forwardAbort, { once: true });
    let timer;
    try {
      const timeout = new Promise((_, reject) => {
        timer = setTimeout(() => {
          const error = new Error("读取排行榜超时，请重试");
          error.name = "TimeoutError";
          reject(error);
          controller.abort(error);
        }, this.timeoutMs);
      });
      const read = async () => {
        const response = await this.fetcher(this.base + name, { ...options, signal: controller.signal });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
      };
      return await Promise.race([read(), timeout]);
    } finally {
      clearTimeout(timer);
      options?.signal?.removeEventListener("abort", forwardAbort);
      const next = this.waiters.shift();
      if (next) next();
      else this.active -= 1;
    }
  }

  async cached(kind, name, limit) {
    const cache = this.caches[kind];
    if (cache.has(name)) {
      const value = cache.get(name);
      cache.delete(name);
      cache.set(name, value);
      return value;
    }
    if (this.pending.has(name)) return this.pending.get(name);
    const request = this.json(name).then(value => {
      cache.set(name, value);
      while (cache.size > limit) cache.delete(cache.keys().next().value);
      return value;
    }).finally(() => this.pending.delete(name));
    this.pending.set(name, request);
    return request;
  }

  async init() {
    this.manifest = await this.json("manifest.json", { cache: "no-cache" });
    if (this.manifest.format !== 1 || this.manifest.page_size !== 100) {
      throw new Error("不支持的数据格式，请刷新页面");
    }
    return this.manifest;
  }

  source(index) {
    return this.cached("source", this.manifest.navigation[index].data, 4);
  }

  async search(source, query) {
    if (!query) return null;
    if (!this.searchRequest) {
      this.searchRequest = this.json(this.manifest.search).then(rows => rows.map(([id, title]) =>
        [id, title.toLocaleLowerCase("zh-CN")])).catch(error => {
        this.searchRequest = null;
        throw error;
      });
    }
    const [descriptor, search] = await Promise.all([this.source(source), this.searchRequest]);
    const members = await this.cached("members", descriptor.index, 3);
    const positions = [];
    members.forEach((index, position) => {
      const [id, title] = search[index];
      if (id.includes(query) || title.includes(query)) positions.push(position);
    });
    return positions;
  }

  async page(source, positions, offset, limit, isCurrent = () => true) {
    const descriptor = await this.source(source);
    if (!isCurrent()) return [];
    const total = positions === null ? descriptor.count : positions.length;
    const selected = positions === null
      ? Array.from({ length: Math.max(0, Math.min(limit, total - offset)) }, (_, i) => offset + i)
      : positions.slice(offset, offset + limit);
    const numbers = [...new Set(selected.map(position => Math.floor(position / 100)))];
    const pages = new Map();
    let next = 0;
    await Promise.all(Array.from({ length: Math.min(3, numbers.length) }, async () => {
      while (next < numbers.length && isCurrent()) {
        const number = numbers[next++];
        const rows = await this.cached("page", descriptor.pages[number], 8);
        pages.set(number, rows);
      }
    }));
    if (!isCurrent()) return [];
    return selected.map(position => pages.get(Math.floor(position / 100))[position % 100]);
  }
}
