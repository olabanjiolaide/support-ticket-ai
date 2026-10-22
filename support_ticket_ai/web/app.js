"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const form = byId("ticket-form");
  const modelMode = byId("model-mode");
  const requestCheck = byId("check-multiple-requests");
  const input = byId("ticket");
  const submit = byId("submit");
  const clear = byId("clear");
  const examples = [...document.querySelectorAll("[data-example]")];
  const maxLength = 2000;
  const messages = {
    account: "I cannot reset my password.",
    payment: "I was charged twice for my subscription.",
    order: "Where can I track my order?",
  };
  let ready = false;
  let busy = false;
  let checking = false;
  let supportsRequestCheck = false;
  let activePrediction = null;
  let cancelled = false;
  let lastResult = null;

  async function request(path, options = {}, controller = new AbortController()) {
    const timer = setTimeout(() => controller.abort(), 15000);
    try {
      return await fetch(path, {
        ...options,
        signal: controller.signal,
        cache: "no-store",
      });
    } finally {
      clearTimeout(timer);
    }
  }

  function showState(state) {
    byId("result-idle").hidden = state !== "idle";
    byId("result-loading").hidden = state !== "loading";
    byId("result-success").hidden = state !== "success";
    byId("result-panel").setAttribute("aria-busy", String(state === "loading"));
    byId("result-panel").dataset.state = state;
    byId("result-status").textContent = state === "success" ? "READY FOR REVIEW" : state === "loading" ? "READING MESSAGE" : "AWAITING REQUEST";
    byId("compose-step").classList.toggle("current", state !== "success");
    byId("review-step").classList.toggle("current", state === "success");
    byId("jump-result").hidden = state !== "success";
    for (const id of ["compose-step", "review-step"]) {
      if (byId(id).classList.contains("current")) byId(id).setAttribute("aria-current", "step");
      else byId(id).removeAttribute("aria-current");
    }
  }

  function updateControls() {
    const count = Array.from(input.value).length;
    const overLimit = count > maxLength;
    byId("character-count").textContent =
      `${count.toLocaleString("en-US")} / 2,000`;
    byId("character-count").classList.toggle("over-limit", overLimit);
    byId("input-progress-bar").style.width = `${Math.min(count / maxLength, 1) * 100}%`;
    byId("input-progress-bar").parentElement.classList.toggle("over-limit", overLimit);
    byId("copy-result").disabled = busy || !lastResult;
    input.setCustomValidity(overLimit ? "Use 2,000 characters or fewer." : "");
    input.setAttribute("aria-invalid", String(overLimit));
    submit.disabled = busy || !ready || !input.value.trim() || overLimit;
    clear.disabled = busy || !input.value;
    modelMode.disabled = busy;
    requestCheck.disabled = busy || modelMode.value !== "semantic" || !supportsRequestCheck;
    input.disabled = busy;
    examples.forEach((button) => {
      button.disabled = busy;
    });
    byId("submit-label").textContent = busy
      ? "Reading request…"
      : "Suggest category";
    byId("submit-arrow").hidden = busy;
    byId("submit-spinner").hidden = !busy;
  }

  function clearError() {
    byId("form-error").hidden = true;
    byId("form-error").textContent = "";
  }

  function edit() {
    lastResult = null;
    byId("copy-feedback").textContent = "";
    byId("input-hint").textContent = "Plain language works best.";
    clearError();
    showState("idle");
    byId("json-response").textContent = "";
    document.querySelector(".response-details").open = false;
    updateControls();
  }

  function setService(available, message = "") {
    ready = available;
    const status = byId("service-status");
    status.classList.remove("checking", "unavailable");
    status.classList.toggle("unavailable", !available);
    byId("service-label").textContent = available
      ? "Model ready"
      : "Model unavailable";
    byId("connection-notice").hidden = available;
    byId("connection-message").textContent = message;
    updateControls();
  }

  function showModel() {
    const semantic = modelMode.value === "semantic";
    byId("model-description").textContent = semantic
      ? "Active: Semantic encoder + scope gate · experimental. Every suggestion needs human review."
      : "Active: Word baseline. Every suggestion needs human review.";
    byId("semantic-notice").hidden = !semantic;
    byId("request-check-controls").hidden = !semantic;
  }

  async function checkReadiness() {
    if (checking) return;
    const mode = modelMode.value;
    checking = true;
    byId("retry").disabled = true;
    try {
      const catalog = await request("/models");
      if (catalog.ok) {
        const data = await catalog.json();
        const semantic = data.modes?.find((item) => item.mode === "semantic");
        supportsRequestCheck = Boolean(semantic?.available && semantic?.supports_multiple_request_check);
        if (!supportsRequestCheck) requestCheck.checked = false;
        byId("semantic-option").disabled = !semantic?.available;
        byId("semantic-option").textContent = semantic?.available
          ? "Semantic · experimental" : "Semantic · experimental (not loaded)";
      }
      const response = await request(`/readyz?mode=${mode}`);
      if (mode === modelMode.value) setService(
        response.ok,
        "The selected model is not ready. Check the local server configuration, then retry.",
      );
    } catch {
      if (mode === modelMode.value) setService(false, "Cannot connect to the local server. Keep it running, then check again.");
    } finally {
      checking = false;
      byId("retry").disabled = false;
      if (mode !== modelMode.value) checkReadiness();
    }
  }

  modelMode.addEventListener("change", () => {
    requestCheck.checked = false;
    ready = false;
    edit();
    showModel();
    byId("service-status").classList.add("checking");
    byId("service-label").textContent = "Checking model";
    checkReadiness();
  });

  requestCheck.addEventListener("change", edit);

  function resizeInput() {
    input.style.height = "auto";
    input.style.height = `${Math.min(Math.max(input.scrollHeight, 170), 360)}px`;
  }

  input.addEventListener("input", resizeInput);
  input.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !event.isComposing) {
      event.preventDefault();
      if (!submit.disabled) form.requestSubmit();
    }
  });
  byId("cancel-request").addEventListener("click", () => {
    cancelled = true;
    activePrediction?.abort();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && busy) {
      cancelled = true;
      activePrediction?.abort();
    }
  });
  byId("copy-result").addEventListener("click", async () => {
    if (!lastResult) return;
    const snapshot = lastResult;
    const text = `${byId("category").textContent}\nHuman review required\n${snapshot.review_reason ?? "Confirm the category before routing this request."}\nUncalibrated model score: ${snapshot.uncalibrated_probability.toFixed(3)}`;
    try {
      await navigator.clipboard.writeText(text);
      if (lastResult === snapshot) byId("copy-feedback").textContent = "Result copied. Customer message not included.";
    } catch {
      if (lastResult === snapshot) byId("copy-feedback").textContent = "Copy unavailable. Select text in the API response below to copy manually.";
    }
  });

  const themeButton = byId("theme-toggle");
  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    themeButton.textContent = theme === "dark" ? "Light theme" : "Dark theme";
    themeButton.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} theme`);
    themeButton.setAttribute("aria-pressed", String(theme === "dark"));
  }
  let savedTheme;
  try { savedTheme = localStorage.getItem("support-ticket-theme"); } catch { /* Storage can be unavailable. */ }
  setTheme(["light", "dark"].includes(savedTheme) ? savedTheme : matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
  themeButton.addEventListener("click", () => {
    const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    setTheme(theme);
    try { localStorage.setItem("support-ticket-theme", theme); } catch { /* Theme still works in this tab. */ }
  });

  input.addEventListener("input", edit);
  clear.addEventListener("click", () => {
    input.value = "";
    resizeInput();
    edit();
    input.focus();
  });
  examples.forEach((button) =>
    button.addEventListener("click", () => {
      input.value = messages[button.dataset.example];
      resizeInput();
      edit();
      input.focus();
    }),
  );
  byId("retry").addEventListener("click", checkReadiness);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (
      busy ||
      !ready ||
      !input.value.trim() ||
      Array.from(input.value).length > maxLength
    )
      return;
    busy = true;
    lastResult = null;
    byId("json-response").textContent = "";
    byId("copy-feedback").textContent = "";
    document.querySelector(".response-details").open = false;
    clearError();
    showState("loading");
    updateControls();
    let completed = false;
    cancelled = false;
    activePrediction = new AbortController();
    const started = performance.now();
    byId("loading-description").textContent = "Finding the most likely category.";
    const loadingTimer = setInterval(() => {
      const seconds = Math.floor((performance.now() - started) / 1000);
      byId("loading-description").textContent = `Still reading… ${seconds}s elapsed. You can cancel below.`;
    }, 1000);
    const requestedMode = modelMode.value;
    const requestedCheck = requestedMode === "semantic" && requestCheck.checked;
    try {
      const response = await request("/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: input.value, mode: requestedMode,
          ...(requestedCheck ? { check_multiple_requests: true } : {}) }),
      }, activePrediction);
      if (!response.ok) {
        if (response.status === 503) {
          setService(
            false,
            "The model is not ready. Check your local server and try again.",
          );
          throw new Error(
            "The model is currently unavailable. Check its status above, then retry.",
          );
        }
        if (response.status === 422)
          throw new Error(
            "The request could not be read. Use a nonempty message of up to 2,000 characters.",
          );
        throw new Error(
          "The suggestion could not be completed. Please try again.",
        );
      }
      const result = await response.json();
      if ((result.model_mode ?? "word") !== requestedMode) throw new Error("The response did not match the selected model. Please retry.");
      if ((result.multiple_request_check_enabled ?? false) !== requestedCheck) throw new Error("The response did not match the separate-request setting. Please retry.");
      const decision = result.decision ?? "suggestion";
      const abstained = decision === "abstain";
      if (
        !["suggestion", "abstain"].includes(decision) ||
        (abstained
          ? result.suggested_category !== null
          : typeof result.suggested_category !== "string" ||
            !result.suggested_category) ||
        typeof result.uncalibrated_probability !== "number" ||
        !Number.isFinite(result.uncalibrated_probability) ||
        result.uncalibrated_probability < 0 ||
        result.uncalibrated_probability > 1 ||
        result.requires_human_review !== true
      ) {
        throw new Error(
          "The server returned an unexpected response. Please try again.",
        );
      }
      byId("category").textContent = abstained
        ? "No reliable suggestion"
        : result.suggested_category
            .toLowerCase()
            .replaceAll("_", " ")
            .replace(/\b\w/g, (letter) => letter.toUpperCase());
      byId("result-kicker").textContent = abstained
        ? "MANUAL CLASSIFICATION NEEDED"
        : "SUGGESTED CATEGORY";
      byId("result-subtitle").textContent = abstained
        ? result.multiple_requests_detected
          ? "More than one request may need attention."
          : "The experimental review rules withheld a category."
        : "A starting point for the right handoff.";
      byId("review-description").textContent = requestedMode === "semantic"
        ? result.review_reason
        : abstained
        ? "Read the request and choose a category manually."
        : "Confirm the category before routing this request.";
      byId("score").textContent = result.uncalibrated_probability.toFixed(3);
      byId("json-response").textContent = JSON.stringify(result, null, 2);
      byId("result-model-label").textContent = requestedMode === "semantic" ? "Semantic · experimental" : "Word baseline";
      lastResult = result;
      byId("workspace-announcement").textContent = abstained ? "No category suggested. Human review needed." : `Suggested category: ${byId("category").textContent}. Human review required.`;
      showState("success");
      completed = true;
    } catch (error) {
      showState("idle");
      if (cancelled) {
        byId("input-hint").textContent = "Cancelled in this tab. You can edit and try again.";
        byId("workspace-announcement").textContent = "Request cancelled in this tab. Server processing may continue.";
        return;
      }
      byId("form-error").textContent =
        error.name === "AbortError"
          ? "The request took too long. Check your local server and try again."
          : error instanceof TypeError
            ? "Connection lost. Keep your local server running and try again."
            : error.message;
      byId("form-error").hidden = false;
    } finally {
      clearInterval(loadingTimer);
      activePrediction = null;
      busy = false;
      updateControls();
      if (completed) byId("category").focus();
      else if (cancelled) input.focus();
      else byId("form-error").focus();
    }
  });

  showModel();
  updateControls();
  checkReadiness();
  window.addEventListener("online", checkReadiness);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !busy) checkReadiness(); });
  setInterval(() => { if (!document.hidden && !busy) checkReadiness(); }, 30000);
})();
