(() => {
  "use strict";

  const CONFIG = window.FACTLY_CONFIG || {};
  const STORAGE = {
    apiBaseUrl: "factly.apiBaseUrl",
    accessCode: "factly.accessCode",
  };
  const MODEL_LABELS = {
    "liquid/lfm2.5-1.2b": "LFM2.5 1.2B",
    "qwen3-0.6b": "Qwen3 0.6B",
  };
  const PROVIDER_LABELS = {
    brave: "Brave Search",
    google_news: "Google News RSS",
    wikipedia: "Wikipedia",
    none: "No provider",
  };
  const ICONS = {
    external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 13v5a2 2 0 01-2 2H6a2 2 0 01-2-2V8a2 2 0 012-2h5"/>',
    sparkle: '<path d="M12 2.5l1.9 6.1L20 10.5l-6.1 1.9L12 18.5l-1.9-6.1L4 10.5l6.1-1.9L12 2.5z"/>',
    warning: '<path d="M12 3l9 17H3L12 3z"/><path d="M12 9v5M12 17h.01"/>',
    check: '<path d="M5 12l5 5L20 7"/>',
  };

  const state = {
    apiBaseUrl: normalizeBase(readStorage(STORAGE.apiBaseUrl) || CONFIG.apiBaseUrl || ""),
    accessCode: readStorage(STORAGE.accessCode) || "",
    models: [],
    busy: false,
    evaluationLoaded: false,
  };

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  };

  const $ = (id) => document.getElementById(id);

  const dom = {
    body: document.body,
    sidebar: $("sidebar"),
    sidebarScrim: $("sidebarScrim"),
    menuButton: $("menuButton"),
    settingsButton: $("settingsButton"),
    settingsButtonTop: $("settingsButtonTop"),
    newCheckButton: $("newCheckButton"),
    connectionBadge: $("connectionBadge"),
    connectionDot: $("connectionDot"),
    connectionText: $("connectionText"),
    sidebarDot: $("sidebarDot"),
    sidebarStatus: $("sidebarStatus"),
    hero: $("hero"),
    transcript: $("transcript"),
    claimForm: $("claimForm"),
    claimInput: $("claimInput"),
    submitButton: $("submitButton"),
    compareToggle: $("compareToggle"),
    primaryModel: $("primaryModel"),
    secondaryModel: $("secondaryModel"),
    modelPickers: $("modelPickers"),
    bertToggle: $("bertToggle"),
    charCount: $("charCount"),
    suggestions: $("suggestions"),
    views: {
      check: $("view-check"),
      evaluation: $("view-evaluation"),
      how: $("view-how"),
    },
    evaluationStatus: $("evaluationStatus"),
    evaluationTables: $("evaluationTables"),
    settingsDialog: $("settingsDialog"),
    settingsForm: $("settingsForm"),
    backendUrlInput: $("backendUrlInput"),
    accessCodeInput: $("accessCodeInput"),
    accessCodeHint: $("accessCodeHint"),
    closeSettings: $("closeSettings"),
    testConnectionButton: $("testConnectionButton"),
    settingsStatus: $("settingsStatus"),
  };

  class ApiError extends Error {
    constructor(message, status = 0) {
      super(message);
      this.name = "ApiError";
      this.status = status;
    }
  }

  function readStorage(key) {
    try {
      return window.localStorage.getItem(key);
    } catch (error) {
      return null;
    }
  }

  function writeStorage(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      return;
    }
  }

  function normalizeBase(value) {
    return String(value || "").trim().replace(/\/+$/, "");
  }

  function normalizeUrl(value) {
    const candidate = normalizeBase(value);
    if (!candidate) return "";
    try {
      const parsed = new URL(candidate);
      return parsed.protocol === "http:" || parsed.protocol === "https:"
        ? parsed.href.replace(/\/+$/, "")
        : "";
    } catch (error) {
      return "";
    }
  }

  function safeUrl(value) {
    try {
      const parsed = new URL(String(value || ""));
      return parsed.protocol === "http:" || parsed.protocol === "https:"
        ? parsed.href
        : null;
    } catch (error) {
      return null;
    }
  }

  function hostLabel(value) {
    const url = safeUrl(value);
    if (!url) return "";
    try {
      return new URL(url).hostname.replace(/^www\./, "");
    } catch (error) {
      return "";
    }
  }

  function modelLabel(value) {
    return MODEL_LABELS[value] || value || "Unknown model";
  }

  function providerLabel(value) {
    return PROVIDER_LABELS[value] || value || "Unknown provider";
  }

  function icon(name, className) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    if (className) svg.setAttribute("class", className);
    svg.innerHTML = ICONS[name] || "";
    return svg;
  }

  function formatPercent(value, digits = 1) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return `${(number * 100).toFixed(digits)}%`;
  }

  function formatNumber(value, digits = 4) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return number.toFixed(digits);
  }

  function formatCi(ci) {
    if (!ci || !Number.isFinite(Number(ci.low)) || !Number.isFinite(Number(ci.high))) {
      return "—";
    }
    return `${formatPercent(ci.low)}–${formatPercent(ci.high)}`;
  }

  function setConnection(kind, text) {
    const safeKind = ["online", "warning", "offline"].includes(kind) ? kind : "unknown";
    dom.connectionBadge.className = `connection-badge ${safeKind}`;
    dom.connectionDot.className = `status-dot ${safeKind}`;
    dom.sidebarDot.className = `status-dot ${safeKind}`;
    dom.connectionText.textContent = text;
    dom.sidebarStatus.textContent = text;
  }

  function setSettingsStatus(message, kind = "") {
    dom.settingsStatus.className = `settings-status ${kind}`.trim();
    dom.settingsStatus.textContent = message || "";
  }

  async function apiRequest(path, options = {}) {
    const base = state.apiBaseUrl;
    if (!base) {
      throw new ApiError("Backend URL is not configured.", 0);
    }
    const controller = new AbortController();
    const timeout = options.timeout || 150000;
    const timer = window.setTimeout(() => controller.abort(), timeout);
    const headers = {
      "Content-Type": "application/json",
      ...(state.accessCode ? { "X-Access-Code": state.accessCode } : {}),
      ...(options.headers || {}),
    };
    try {
      const response = await fetch(`${base}${path}`, {
        method: options.method || "GET",
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
        signal: controller.signal,
      });
      const raw = await response.text();
      let payload = null;
      if (raw) {
        try {
          payload = JSON.parse(raw);
        } catch (error) {
          payload = null;
        }
      }
      if (!response.ok) {
        const detail =
          payload && typeof payload.detail === "string"
            ? payload.detail
            : `Request failed with HTTP ${response.status}.`;
        throw new ApiError(detail, response.status);
      }
      return payload || {};
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error && error.name === "AbortError") {
        throw new ApiError("The request timed out. Live retrieval can take a while.", 0);
      }
      throw new ApiError(
        "Could not reach the backend. Check the tunnel URL and that the API is running.",
        0,
      );
    } finally {
      window.clearTimeout(timer);
    }
  }

  async function refreshHealth(showSettingsStatus = false) {
    if (!state.apiBaseUrl) {
      setConnection("unknown", "Not configured");
      if (showSettingsStatus) setSettingsStatus("Enter a backend URL first.", "error");
      return false;
    }
    try {
      const health = await apiRequest("/health", { timeout: 8000 });
      const lm = health.lm_studio || {};
      if (lm.reachable) {
        const count = Array.isArray(lm.chat_models) ? lm.chat_models.length : 0;
        setConnection("online", `Backend + LM Studio (${count} models)`);
        if (showSettingsStatus) {
          setSettingsStatus("Connected. LM Studio is reachable.", "success");
        }
        return true;
      }
      setConnection("warning", "Backend online · LM Studio offline");
      if (showSettingsStatus) {
        setSettingsStatus(
          "Backend reached, but LM Studio is offline. Start its local server.",
          "error",
        );
      }
      return false;
    } catch (error) {
      setConnection("offline", "Backend offline");
      if (showSettingsStatus) {
        setSettingsStatus(error.message || "Backend is unreachable.", "error");
      }
      return false;
    }
  }

  function populateModelSelect(select, models, preferred) {
    const current = preferred || select.value;
    const unique = Array.from(new Set(models.filter(Boolean)));
    select.replaceChildren();
    for (const model of unique) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = modelLabel(model);
      select.append(option);
    }
    if (current && unique.includes(current)) {
      select.value = current;
    } else if (unique.length) {
      select.value = unique[0];
    }
  }

  async function loadModels() {
    let models = [];
    try {
      const payload = await apiRequest("/models", { timeout: 8000 });
      models = Array.isArray(payload.models) ? payload.models : [];
      const fallback = [payload.default, payload.secondary].filter(Boolean);
      models = Array.from(new Set([...models, ...fallback]));
    } catch (error) {
      models = [];
    }
    if (!models.length) {
      models = [CONFIG.primaryModel || "liquid/lfm2.5-1.2b", CONFIG.secondaryModel || "qwen3-0.6b"];
    }
    state.models = models;
    populateModelSelect(
      dom.primaryModel,
      models,
      dom.primaryModel.value || CONFIG.primaryModel,
    );
    populateModelSelect(
      dom.secondaryModel,
      models,
      dom.secondaryModel.value || CONFIG.secondaryModel || models[1],
    );
  }

  function setView(view) {
    const target = dom.views[view] ? view : "check";
    for (const [name, section] of Object.entries(dom.views)) {
      section.classList.toggle("active", name === target);
    }
    document.querySelectorAll("[data-view-link]").forEach((button) => {
      button.classList.toggle("active", button.dataset.viewLink === target);
    });
    closeSidebar();
    if (target === "evaluation") loadEvaluation();
    if (target === "check") dom.claimInput.focus({ preventScroll: true });
  }

  function closeSidebar() {
    dom.body.classList.remove("sidebar-open");
  }

  function openSidebar() {
    dom.body.classList.add("sidebar-open");
  }

  function openSettings(message = "") {
    dom.backendUrlInput.value = state.apiBaseUrl;
    dom.accessCodeInput.value = state.accessCode;
    dom.accessCodeHint.textContent =
      CONFIG.accessCodeHint || "Use the shared code from the project owner.";
    if (message) setSettingsStatus(message, "error");
    else setSettingsStatus("");
    if (typeof dom.settingsDialog.showModal === "function") {
      if (!dom.settingsDialog.open) dom.settingsDialog.showModal();
    } else {
      dom.settingsDialog.setAttribute("open", "");
    }
    window.setTimeout(() => dom.backendUrlInput.focus(), 40);
  }

  function closeSettings() {
    if (typeof dom.settingsDialog.close === "function") {
      dom.settingsDialog.close();
    } else {
      dom.settingsDialog.removeAttribute("open");
    }
  }

  function saveSettings() {
    const base = normalizeUrl(dom.backendUrlInput.value);
    if (!base) {
      setSettingsStatus("Enter a valid http:// or https:// backend URL.", "error");
      return;
    }
    state.apiBaseUrl = base;
    state.accessCode = dom.accessCodeInput.value.trim();
    writeStorage(STORAGE.apiBaseUrl, state.apiBaseUrl);
    writeStorage(STORAGE.accessCode, state.accessCode);
    closeSettings();
    refreshHealth();
    loadModels();
  }

  async function testConnection() {
    const base = normalizeUrl(dom.backendUrlInput.value);
    if (!base) {
      setSettingsStatus("Enter a valid backend URL first.", "error");
      return;
    }
    const previous = state.apiBaseUrl;
    state.apiBaseUrl = base;
    dom.testConnectionButton.disabled = true;
    setSettingsStatus("Testing connection…");
    try {
      const health = await apiRequest("/health", { timeout: 8000 });
      const lm = health.lm_studio || {};
      if (lm.reachable) {
        setSettingsStatus("Backend reached. LM Studio is online.", "success");
      } else {
        setSettingsStatus("Backend reached, but LM Studio is not.", "error");
      }
    } catch (error) {
      setSettingsStatus(error.message || "Could not reach the backend.", "error");
    } finally {
      state.apiBaseUrl = previous;
      dom.testConnectionButton.disabled = false;
    }
  }

  function hideWelcome() {
    dom.hero.classList.add("hidden");
    dom.suggestions.classList.add("hidden");
  }

  function showWelcome() {
    dom.hero.classList.remove("hidden");
    dom.suggestions.classList.remove("hidden");
    dom.transcript.replaceChildren();
    dom.claimInput.value = "";
    updateCharCount();
    autoResize();
    dom.claimInput.focus({ preventScroll: true });
  }

  function autoResize() {
    dom.claimInput.style.height = "auto";
    dom.claimInput.style.height = `${Math.min(dom.claimInput.scrollHeight, 180)}px`;
  }

  function updateCharCount() {
    dom.charCount.textContent = `${dom.claimInput.value.length} / 600`;
  }

  function appendUserMessage(claim) {
    const message = el("div", "message user");
    message.append(el("div", "user-bubble", claim));
    dom.transcript.append(message);
  }

  function assistantHead(mode) {
    const head = el("div", "assistant-head");
    const mark = el("span", "assistant-mark");
    mark.append(icon("sparkle"));
    const text = el("div");
    text.append(el("strong", "", "Factly"));
    text.append(
      el(
        "span",
        "",
        mode === "compare" ? " · comparing two local models" : " · evidence-grounded verdict",
      ),
    );
    head.append(mark, text);
    return head;
  }

  function appendLoading() {
    const card = el("div", "loading-card");
    card.append(el("span", "spinner"));
    const copy = el("div", "loading-copy");
    const title = el("strong", "", "Reading the web");
    const detail = el("span", "", "Searching, fetching pages, and ranking evidence… 0s");
    copy.append(title, detail);
    card.append(copy);
    const message = el("div", "message assistant");
    message.append(card);
    dom.transcript.append(message);
    message.scrollIntoView({ behavior: "smooth", block: "end" });
    const started = Date.now();
    const timer = window.setInterval(() => {
      const seconds = Math.round((Date.now() - started) / 1000);
      detail.textContent =
        seconds < 25
          ? `Searching, fetching pages, and ranking evidence… ${seconds}s`
          : `Still working — live retrieval can take 20–40s… ${seconds}s`;
    }, 1000);
    return { message, timer };
  }

  function appendError(messageText) {
    const message = el("div", "message assistant");
    const card = el("div", "assistant-card");
    card.append(assistantHead("check"));
    const callout = el("div", "callout error");
    callout.append(icon("warning"));
    callout.append(el("span", "", messageText));
    card.append(callout);
    const actions = el("div", "dialog-actions");
    const settings = el("button", "ghost-button", "Open connection settings");
    settings.type = "button";
    settings.addEventListener("click", () => openSettings(messageText));
    actions.append(settings);
    card.append(actions);
    message.append(card);
    dom.transcript.append(message);
    message.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  function metaChip(label) {
    const chip = el("span", "meta-chip", label);
    return chip;
  }

  function verdictCard(output) {
    const card = el("article", "verdict-card");
    const top = el("div", "verdict-top");
    top.append(el("span", "model-name", modelLabel(output.model)));
    const label = output.label === "SUPPORTED" || output.label === "REFUTED" ? output.label : null;
    const badge = el(
      "span",
      `badge ${label === "SUPPORTED" ? "supported" : label === "REFUTED" ? "refuted" : "neutral"}`,
      label || "No verdict",
    );
    top.append(badge);
    card.append(top);
    card.append(
      el(
        "p",
        "verdict-reason",
        output.reason || "No reason was returned for this claim.",
      ),
    );
    const latency = Number(output.latency_seconds);
    const details = [
      Number.isFinite(latency) ? `${latency.toFixed(1)}s` : "—",
      output.retried ? "retried for a strict label" : "single pass",
    ];
    card.append(el("div", "verdict-meta", details.join(" · ")));
    return card;
  }

  function sourceCard(item) {
    const card = el("article", "source-card");
    const url = safeUrl(item.url);
    const titleRow = el("div", "source-title");
    if (url) {
      const link = el("a", "", item.title || hostLabel(url) || "Untitled source");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      titleRow.append(link, icon("external"));
    } else {
      titleRow.append(el("span", "", item.title || "Untitled source"));
    }
    card.append(titleRow);
    if (item.text) card.append(el("p", "source-snippet", item.text));
    const foot = el("div", "source-foot");
    foot.append(el("span", "", hostLabel(item.url) || "source"));
    const score = Number(item.score);
    if (Number.isFinite(score) && score > 0) {
      foot.append(el("span", "source-score", `${Math.round(Math.min(1, score) * 100)}% match`));
    }
    card.append(foot);
    return card;
  }

  function renderAssistant(payload, loading) {
    const message = el("div", "message assistant");
    const card = el("div", "assistant-card");
    card.append(assistantHead(payload.mode));

    const meta = el("div", "meta-row");
    const evidence = payload.evidence || {};
    meta.append(metaChip(providerLabel(evidence.provider)));
    meta.append(metaChip(`${evidence.pages || 0} pages`));
    if (evidence.cached) meta.append(metaChip("cached snapshot"));
    meta.append(metaChip(payload.mode === "compare" ? "2 models" : "1 model"));
    if (payload.bert && !payload.bert.error) {
      meta.append(metaChip(`BERT ${payload.bert.label || "hint"}`));
    }
    card.append(meta);

    if (evidence.error) {
      const warning = el("div", "callout warning");
      warning.append(icon("warning"));
      warning.append(el("span", "", `Retrieval note: ${evidence.error}`));
      card.append(warning);
    }

    const verdictGrid = el(
      "div",
      `verdict-grid${payload.models && payload.models.length > 1 ? "" : " single"}`,
    );
    for (const output of payload.models || []) {
      verdictGrid.append(verdictCard(output));
    }
    card.append(verdictGrid);

    const evidenceHead = el("div", "evidence-head");
    evidenceHead.append(el("h3", "", "Evidence used"));
    evidenceHead.append(
      el(
        "span",
        "",
        evidence.selected && evidence.selected.length
          ? `${evidence.selected.length} sentences ranked by relevance`
          : "no usable evidence",
      ),
    );
    card.append(evidenceHead);

    if (evidence.selected && evidence.selected.length) {
      const grid = el("div", "source-grid");
      for (const item of evidence.selected) grid.append(sourceCard(item));
      card.append(grid);
    } else {
      const callout = el("div", "callout warning");
      callout.append(icon("warning"));
      callout.append(
        el(
          "span",
          "",
          "No usable evidence was retrieved, so the evidence-only policy returned no verdict.",
        ),
      );
      card.append(callout);
    }

    const rawDetails = (payload.models || [])
      .filter((output) => output.raw_response)
      .map((output) => {
        const details = el("details", "details");
        details.append(el("summary", "", `Raw output — ${modelLabel(output.model)}`));
        details.append(el("pre", "", output.raw_response));
        return details;
      });
    for (const details of rawDetails) card.append(details);

    message.append(card);
    if (loading && loading.message && loading.message.parentNode) {
      loading.message.replaceWith(message);
    } else {
      dom.transcript.append(message);
    }
    message.scrollIntoView({ behavior: "smooth", block: "end" });
  }

  async function submitClaim(claimOverride) {
    if (state.busy) return;
    const claim = String(claimOverride || dom.claimInput.value || "").trim();
    if (!claim) {
      dom.claimInput.focus();
      return;
    }
    if (!state.apiBaseUrl) {
      openSettings("Add the current backend tunnel URL to start checking claims.");
      return;
    }
    if (!state.accessCode) {
      openSettings("Enter the shared access code to use the fact-check API.");
      return;
    }

    state.busy = true;
    dom.submitButton.disabled = true;
    hideWelcome();
    appendUserMessage(claim);
    dom.claimInput.value = "";
    updateCharCount();
    autoResize();
    const loading = appendLoading();
    const compare = dom.compareToggle.checked;
    const payload = {
      claim,
      use_bert: dom.bertToggle.checked,
    };
    if (compare) {
      payload.primary_model = dom.primaryModel.value;
      payload.secondary_model = dom.secondaryModel.value;
    } else {
      payload.model = dom.primaryModel.value;
    }

    try {
      const result = await apiRequest(compare ? "/compare" : "/check", {
        method: "POST",
        body: payload,
      });
      window.clearInterval(loading.timer);
      renderAssistant(result, loading);
      refreshHealth();
    } catch (error) {
      window.clearInterval(loading.timer);
      if (loading.message && loading.message.parentNode) loading.message.remove();
      appendError(error.message || "The fact check failed.");
      if (error.status === 401) {
        openSettings("The access code was rejected. Check it and try again.");
      }
    } finally {
      state.busy = false;
      dom.submitButton.disabled = false;
      dom.claimInput.focus({ preventScroll: true });
    }
  }

  function formatModel(value) {
    return modelLabel(value);
  }

  function formatPrompt(value) {
    return value === "few_shot" ? "Few-shot" : value === "zero_shot" ? "Zero-shot" : value || "—";
  }

  function evaluationSection(title, subtitle, rows) {
    const section = el("section", "eval-section");
    section.append(el("h3", "", title));
    section.append(el("p", "", subtitle));
    const wrap = el("div", "table-wrap");
    const table = el("table");
    const thead = el("thead");
    const header = el("tr");
    for (const [label, numeric] of [
      ["Model", false],
      ["Prompt", false],
      ["N", true],
      ["Accuracy", true],
      ["Macro F1", true],
      ["Weighted F1", true],
      ["95% CI", true],
    ]) {
      const th = el("th", numeric ? "num" : "", label);
      header.append(th);
    }
    thead.append(header);
    table.append(thead);
    const tbody = el("tbody");
    const best = rows.reduce(
      (winner, row) =>
        !winner || Number(row.macro_f1) > Number(winner.macro_f1) ? row : winner,
      null,
    );
    for (const row of rows) {
      const tr = el("tr", row === best ? "best-row" : "");
      tr.append(el("td", "", formatModel(row.model)));
      tr.append(el("td", "", formatPrompt(row.prompt)));
      tr.append(el("td", "num", String(row.n ?? "—")));
      tr.append(el("td", "num", formatPercent(row.accuracy)));
      tr.append(el("td", "num", formatNumber(row.macro_f1)));
      tr.append(el("td", "num", formatNumber(row.weighted_f1)));
      tr.append(el("td", "num", formatCi(row.bootstrap_accuracy_ci)));
      tbody.append(tr);
    }
    table.append(tbody);
    wrap.append(table);
    section.append(wrap);
    return section;
  }

  async function loadEvaluation() {
    if (state.evaluationLoaded) return;
    state.evaluationLoaded = true;
    dom.evaluationStatus.className = "callout";
    dom.evaluationStatus.textContent = "Loading evaluation summary…";
    try {
      const payload = await apiRequest("/evaluation/summary", { timeout: 10000 });
      const gold = Array.isArray(payload.gold) ? payload.gold : [];
      const retrieval = Array.isArray(payload.retrieval_sample) ? payload.retrieval_sample : [];
      dom.evaluationTables.replaceChildren();
      if (gold.length) {
        dom.evaluationTables.append(
          evaluationSection(
            "Gold evidence · full test split",
            "All 401 test claims with the dataset's gold evidence. This isolates classification from retrieval quality.",
            gold,
          ),
        );
      }
      if (retrieval.length) {
        dom.evaluationTables.append(
          evaluationSection(
            "Retrieved evidence · 60-claim sample",
            "Class-stratified sample (19 SUPPORTED / 41 REFUTED). Mostly search snippets; a pilot end-to-end retrieval result.",
            retrieval,
          ),
        );
      }
      dom.evaluationStatus.hidden = true;
    } catch (error) {
      state.evaluationLoaded = false;
      dom.evaluationStatus.className = "callout error";
      dom.evaluationStatus.textContent = `${error.message} Start the backend to load live results, or view the methodology on GitHub.`;
    }
  }

  function bindEvents() {
    document.querySelectorAll("[data-view-link]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        setView(button.dataset.viewLink);
      });
    });
    dom.menuButton.addEventListener("click", openSidebar);
    dom.sidebarScrim.addEventListener("click", closeSidebar);
    dom.settingsButton.addEventListener("click", () => openSettings());
    dom.settingsButtonTop.addEventListener("click", () => openSettings());
    dom.newCheckButton.addEventListener("click", () => {
      setView("check");
      showWelcome();
    });
    dom.closeSettings.addEventListener("click", closeSettings);
    dom.settingsDialog.addEventListener("click", (event) => {
      if (event.target === dom.settingsDialog) closeSettings();
    });
    dom.settingsForm.addEventListener("submit", (event) => {
      event.preventDefault();
      saveSettings();
    });
    dom.testConnectionButton.addEventListener("click", testConnection);
    dom.claimForm.addEventListener("submit", (event) => {
      event.preventDefault();
      submitClaim();
    });
    dom.claimInput.addEventListener("input", () => {
      updateCharCount();
      autoResize();
    });
    dom.claimInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        submitClaim();
      }
    });
    dom.compareToggle.addEventListener("change", () => {
      dom.secondaryModel.disabled = !dom.compareToggle.checked;
      dom.modelPickers.classList.toggle("disabled", !dom.compareToggle.checked);
    });
    dom.suggestions.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-claim]");
      if (!button) return;
      dom.claimInput.value = button.dataset.claim;
      updateCharCount();
      autoResize();
      submitClaim(button.dataset.claim);
    });
    window.addEventListener("online", () => refreshHealth());
    window.addEventListener("offline", () => setConnection("offline", "Browser offline"));
  }

  function init() {
    bindEvents();
    dom.secondaryModel.disabled = !dom.compareToggle.checked;
    dom.modelPickers.classList.toggle("disabled", !dom.compareToggle.checked);
    dom.claimInput.focus({ preventScroll: true });
    refreshHealth();
    loadModels();
  }

  init();
})();
