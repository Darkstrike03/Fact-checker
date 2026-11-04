(() => {
  "use strict";

  const CONFIG = window.FACTLY_CONFIG || {};
  const STORAGE = {
    apiBaseUrl: "factly.apiBaseUrl",
    accessCode: "factly.accessCode",
    model: "factly.model",
  };
  const HEALTH_TIMEOUT = 15000;
  const HEALTH_RETRY_MS = 10000;
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
    loadedModels: [],
    model: readStorage(STORAGE.model) || CONFIG.primaryModel || "",
    busy: false,
    localDemo: false,
    evaluationLoaded: false,
    healthRetryTimer: null,
    lastResult: null,
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
    modelSelect: $("modelSelect"),
    modelStatus: $("modelStatus"),
    charCount: $("charCount"),
    suggestions: $("suggestions"),
    evidenceButton: $("evidenceButton"),
    evidenceCount: $("evidenceCount"),
    evidencePanel: $("evidencePanel"),
    evidenceContent: $("evidenceContent"),
    closeEvidence: $("closeEvidence"),
    evidenceScrim: $("evidenceScrim"),
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

  function clearHealthRetry() {
    if (state.healthRetryTimer) {
      window.clearTimeout(state.healthRetryTimer);
      state.healthRetryTimer = null;
    }
  }

  function scheduleHealthRetry() {
    if (state.healthRetryTimer) return;
    state.healthRetryTimer = window.setTimeout(() => {
      state.healthRetryTimer = null;
      if (!state.busy) refreshHealth();
    }, HEALTH_RETRY_MS);
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
    clearHealthRetry();
    if (!state.apiBaseUrl) {
      setConnection("unknown", "Not configured");
      if (showSettingsStatus) setSettingsStatus("Enter a backend URL first.", "error");
      return false;
    }
    try {
      const health = await apiRequest("/health", { timeout: HEALTH_TIMEOUT });
      state.localDemo = Boolean(health.local_demo);
      const lm = health.lm_studio || {};
      if (lm.reachable) {
        const count = Array.isArray(lm.chat_models) ? lm.chat_models.length : 0;
        setConnection("online", `Backend + LM Studio (${count} available)`);
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
      scheduleHealthRetry();
      return false;
    } catch (error) {
      setConnection("offline", "Backend offline");
      if (showSettingsStatus) {
        setSettingsStatus(error.message || "Backend is unreachable.", "error");
      }
      scheduleHealthRetry();
      return false;
    }
  }

  function modelKey(value) {
    return String(value || "").trim().toLowerCase().replace(/\\/g, "/");
  }

  function modelIsLoaded(model) {
    const key = modelKey(model);
    return state.loadedModels.some((loaded) => {
      const loadedKey = modelKey(loaded);
      return (
        loadedKey === key ||
        loadedKey.split("/").pop() === key.split("/").pop()
      );
    });
  }

  function populateModelSelect(select, models, preferred) {
    const current = preferred || select.value;
    const unique = Array.from(new Set(models.filter(Boolean)));
    select.replaceChildren();
    for (const model of unique) {
      const option = document.createElement("option");
      option.value = model;
      option.textContent = `${modelLabel(model)}${modelIsLoaded(model) ? " · loaded" : ""}`;
      select.append(option);
    }
    if (current && unique.includes(current)) {
      select.value = current;
    } else if (unique.length) {
      select.value = unique[0];
    }
  }

  function updateModelStatus(message = "", loading = false) {
    if (!dom.modelStatus) return;
    dom.modelStatus.classList.toggle("loading", loading);
    if (message) {
      dom.modelStatus.textContent = message;
      return;
    }
    const model = dom.modelSelect ? dom.modelSelect.value : state.model;
    if (!model) {
      dom.modelStatus.textContent = "No model selected";
    } else if (modelIsLoaded(model)) {
      dom.modelStatus.textContent = "Ready · one model loaded";
    } else {
      dom.modelStatus.textContent = "Loads on first check";
    }
  }

  async function loadModels() {
    let models = [];
    let loaded = [];
    try {
      const payload = await apiRequest("/models", { timeout: HEALTH_TIMEOUT });
      models = Array.isArray(payload.models) ? payload.models : [];
      loaded = Array.isArray(payload.loaded) ? payload.loaded : [];
      const fallback = [payload.default, payload.secondary].filter(Boolean);
      models = Array.from(new Set([...models, ...fallback]));
      state.loadedModels = loaded;
      if (!state.model && payload.default) state.model = payload.default;
    } catch (error) {
      models = [];
    }
    if (!models.length) {
      models = [
        CONFIG.primaryModel || "liquid/lfm2.5-1.2b",
        CONFIG.secondaryModel || "qwen3-0.6b",
      ];
    }
    state.models = models;
    const preferred = state.model || CONFIG.primaryModel || models[0];
    populateModelSelect(dom.modelSelect, models, preferred);
    state.model = dom.modelSelect.value;
    writeStorage(STORAGE.model, state.model);
    updateModelStatus();
  }

  async function selectModel() {
    const model = dom.modelSelect.value;
    if (!model) return;
    state.model = model;
    writeStorage(STORAGE.model, model);
    updateModelStatus();

    if (!state.localDemo && !state.accessCode) {
      updateModelStatus("Connect to switch models");
      return;
    }
    if (modelIsLoaded(model) && state.loadedModels.length === 1) {
      updateModelStatus();
      return;
    }
    if (!modelIsLoaded(model) && state.loadedModels.length === 1) {
      updateModelStatus("Switching model — unloading the previous one…", true);
    } else {
      updateModelStatus("Loading model…", true);
    }
    dom.modelSelect.disabled = true;
    try {
      const payload = await apiRequest("/models/select", {
        method: "POST",
        body: { model },
        timeout: 180000,
      });
      state.loadedModels = Array.isArray(payload.loaded) ? payload.loaded : [model];
      populateModelSelect(dom.modelSelect, state.models, model);
      updateModelStatus("Ready · one model loaded");
    } catch (error) {
      updateModelStatus("Will load on the next check");
    } finally {
      dom.modelSelect.disabled = false;
    }
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
    closeEvidencePanel();
    if (target === "evaluation") loadEvaluation();
    if (target === "check") dom.claimInput.focus({ preventScroll: true });
  }

  function closeSidebar() {
    dom.body.classList.remove("sidebar-open");
  }

  function openSidebar() {
    dom.body.classList.add("sidebar-open");
  }

  function openEvidencePanel() {
    dom.body.classList.add("evidence-open");
    if (dom.closeEvidence) {
      window.setTimeout(() => dom.closeEvidence.focus({ preventScroll: true }), 60);
    }
  }

  function closeEvidencePanel() {
    dom.body.classList.remove("evidence-open");
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
      const health = await apiRequest("/health", { timeout: HEALTH_TIMEOUT });
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
    state.lastResult = null;
    if (dom.evidenceCount) dom.evidenceCount.textContent = "0";
    if (dom.evidenceContent) {
      dom.evidenceContent.replaceChildren();
      const empty = el("div", "evidence-empty");
      empty.append(el("p", "", "Run a check to see the passages behind the answer."));
      dom.evidenceContent.append(empty);
    }
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

  function assistantHead() {
    const head = el("div", "assistant-head");
    const mark = el("span", "assistant-mark");
    mark.append(icon("sparkle"));
    const text = el("div");
    text.append(el("strong", "", "Factly"));
    text.append(el("span", "", " · evidence-grounded answer"));
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
          : `Still working — the first check can load a model and take 45–60s… ${seconds}s`;
    }, 1000);
    return { message, timer };
  }

  function appendError(messageText) {
    const message = el("div", "message assistant");
    const card = el("div", "assistant-card");
    card.append(assistantHead());
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
    if (dom.evidenceContent) {
      dom.evidenceContent.replaceChildren();
      const panelError = el("div", "callout error");
      panelError.append(icon("warning"));
      panelError.append(el("span", "", "Evidence is unavailable for this request."));
      dom.evidenceContent.append(panelError);
    }
  }

  function metaChip(label) {
    const chip = el("span", "meta-chip", label);
    return chip;
  }

  function answerCard(output, quality) {
    const label = ["SUPPORTED", "REFUTED", "UNVERIFIED"].includes(output.label)
      ? output.label
      : "UNVERIFIED";
    const card = el("article", `answer-card ${label.toLowerCase()}`);
    const top = el("div", "answer-top");
    top.append(el("span", `badge ${label.toLowerCase()}`, label));
    top.append(el("span", "answer-kicker", "Bottom line"));
    if (output.confidence) {
      top.append(el("span", "confidence-chip", `${output.confidence} confidence`));
    }
    if (quality && quality.relevance_label) {
      top.append(
        el("span", "evidence-strength", `Evidence: ${quality.relevance_label}`),
      );
    }
    card.append(top);

    card.append(
      el(
        "p",
        "answer-text",
        output.answer || output.reason || "No answer was returned for this claim.",
      ),
    );
    if (output.reason && output.reason !== output.answer) {
      card.append(el("p", "answer-why", output.reason));
    }

    const actions = el("div", "answer-actions");
    const evidence = (state.lastResult && state.lastResult.evidence) || {};
    const selected = evidence.selected || [];
    if (selected.length) {
      const button = el("button", "ghost-button", `View evidence (${selected.length})`);
      button.type = "button";
      button.addEventListener("click", openEvidencePanel);
      actions.append(button);
    }
    if (actions.childElementCount) card.append(actions);
    return card;
  }

  function evidenceItem(item, number, used) {
    const card = el("article", "evidence-item");
    const head = el("div", "evidence-item-head");
    head.append(el("span", "evidence-number", `[${number}]`));
    const title = el("div", "evidence-item-title");
    const url = safeUrl(item.url);
    if (url) {
      const link = el("a", "", item.title || hostLabel(url) || "Untitled source");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      title.append(link, icon("external"));
    } else {
      title.append(el("span", "", item.title || "Untitled source"));
    }
    head.append(title);
    card.append(head);
    if (item.text) card.append(el("p", "evidence-snippet", item.text));

    const meta = el("div", "evidence-meta");
    meta.append(el("span", "", hostLabel(item.url) || "source"));
    if (item.published_at) meta.append(el("span", "", item.published_at));
    const score = Number(item.score);
    if (Number.isFinite(score) && score > 0) {
      meta.append(
        el("span", "relevance", `relevance ${Math.round(Math.min(1, score) * 100)}%`),
      );
    }
    if (used) meta.append(el("span", "", "used in verdict"));
    card.append(meta);
    return card;
  }

  function setEvidencePending(claim) {
    if (dom.evidenceCount) dom.evidenceCount.textContent = "0";
    if (!dom.evidenceContent) return;
    dom.evidenceContent.replaceChildren();
    const pending = el("div", "evidence-empty");
    pending.append(el("p", "", `Reading sources for: ${claim}`));
    dom.evidenceContent.append(pending);
  }

  function renderEvidencePanel(payload) {
    state.lastResult = payload;
    const evidence = payload.evidence || {};
    const selected = evidence.selected || [];
    const candidates = evidence.candidates || selected;
    if (dom.evidenceCount) dom.evidenceCount.textContent = String(selected.length);
    if (!dom.evidenceContent) return;
    dom.evidenceContent.replaceChildren();

    if (evidence.error) {
      const warning = el("div", "callout warning");
      warning.append(icon("warning"));
      warning.append(el("span", "", `Retrieval note: ${evidence.error}`));
      dom.evidenceContent.append(warning);
    }

    if (!selected.length) {
      const empty = el("div", "callout warning");
      empty.append(icon("warning"));
      empty.append(
        el(
          "span",
          "",
          "No usable evidence was retrieved. Factly therefore returns UNVERIFIED instead of guessing.",
        ),
      );
      dom.evidenceContent.append(empty);
      return;
    }

    const summary = el("div", "evidence-summary");
    summary.append(metaChip(providerLabel(evidence.provider)));
    summary.append(metaChip(`${evidence.selected.length} used`));
    summary.append(metaChip(`${candidates.length} retrieved`));
    if (payload.quality && payload.quality.source_count) {
      summary.append(metaChip(`${payload.quality.source_count} sources`));
    }
    dom.evidenceContent.append(summary);

    const section = el("section", "evidence-section");
    section.append(el("h3", "", "Used in the verdict"));
    const list = el("ol", "evidence-list");
    selected.forEach((item, index) => {
      list.append(evidenceItem(item, index + 1, true));
    });
    section.append(list);
    dom.evidenceContent.append(section);

    if (candidates.length > selected.length) {
      const more = el("details", "evidence-more");
      more.append(
        el(
          "summary",
          "",
          `More retrieved passages (${candidates.length - selected.length})`,
        ),
      );
      const moreList = el("ol", "evidence-more-list");
      candidates.slice(selected.length).forEach((item, index) => {
        moreList.append(evidenceItem(item, selected.length + index + 1, false));
      });
      more.append(moreList);
      dom.evidenceContent.append(more);
    }
  }

  function renderAssistant(payload, loading) {
    const message = el("div", "message assistant");
    const card = el("div", "assistant-card");
    card.append(assistantHead());

    const output = (payload.models || [])[0] || {};
    const evidence = payload.evidence || {};
    const meta = el("div", "meta-row");
    meta.append(metaChip(modelLabel(output.model)));
    meta.append(metaChip(providerLabel(evidence.provider)));
    meta.append(metaChip(`${evidence.pages || 0} pages`));
    if (evidence.cached) meta.append(metaChip("cached snapshot"));
    const latency = Number(output.latency_seconds);
    if (Number.isFinite(latency) && latency > 0) {
      meta.append(metaChip(`${latency.toFixed(1)}s`));
    }
    card.append(meta);

    if (evidence.error) {
      const warning = el("div", "callout warning");
      warning.append(icon("warning"));
      warning.append(el("span", "", `Retrieval note: ${evidence.error}`));
      card.append(warning);
    }

    if (!output.label) {
      const callout = el("div", "callout error");
      callout.append(icon("warning"));
      callout.append(
        el("span", "", output.reason || "The model did not return a usable verdict."),
      );
      card.append(callout);
    } else {
      card.append(answerCard(output, payload.quality));
    }

    const rawDetails = (payload.models || [])
      .filter((item) => item.raw_response)
      .map((item) => {
        const details = el("details", "details");
        details.append(el("summary", "", `Raw output — ${modelLabel(item.model)}`));
        details.append(el("pre", "", item.raw_response));
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
    if (!state.accessCode && !state.localDemo) {
      openSettings("Enter the shared access code to use the fact-check API.");
      return;
    }

    state.busy = true;
    dom.submitButton.disabled = true;
    if (dom.modelSelect) dom.modelSelect.disabled = true;
    hideWelcome();
    appendUserMessage(claim);
    dom.claimInput.value = "";
    updateCharCount();
    autoResize();
    setEvidencePending(claim);
    const loading = appendLoading();
    const model = dom.modelSelect.value || state.model;
    const payload = { claim, model };

    try {
      const result = await apiRequest("/check", {
        method: "POST",
        body: payload,
        timeout: 180000,
      });
      window.clearInterval(loading.timer);
      const usedModel = ((result.models || [])[0] || {}).model || model;
      state.model = usedModel;
      state.loadedModels = [usedModel];
      populateModelSelect(dom.modelSelect, state.models, usedModel);
      updateModelStatus("Ready · one model loaded");
      renderEvidencePanel(result);
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
      if (dom.modelSelect) dom.modelSelect.disabled = false;
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
    dom.modelSelect.addEventListener("change", selectModel);
    dom.evidenceButton.addEventListener("click", openEvidencePanel);
    dom.closeEvidence.addEventListener("click", closeEvidencePanel);
    dom.evidenceScrim.addEventListener("click", closeEvidencePanel);
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        closeEvidencePanel();
        closeSidebar();
      }
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
    updateModelStatus();
    dom.claimInput.focus({ preventScroll: true });
    refreshHealth();
    loadModels();
  }

  init();
})();
