"use strict";

(() => {
  const byId = (id) => document.getElementById(id);
  const form = byId("ticket-form");
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

  async function request(path, options = {}) {
    const controller = new AbortController();
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
  }

  function updateControls() {
    const count = Array.from(input.value).length;
    const overLimit = count > maxLength;
    byId("character-count").textContent =
      `${count.toLocaleString("en-US")} / 2,000`;
    byId("character-count").classList.toggle("over-limit", overLimit);
    input.setCustomValidity(overLimit ? "Use 2,000 characters or fewer." : "");
    input.setAttribute("aria-invalid", String(overLimit));
    submit.disabled = busy || !ready || !input.value.trim() || overLimit;
    clear.disabled = busy || !input.value;
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

  async function checkReadiness() {
    if (checking) return;
    checking = true;
    byId("retry").disabled = true;
    try {
      const response = await request("/readyz");
      setService(
        response.ok,
        "The model is not ready. Load a trained model on your local server, then check again.",
      );
    } catch {
      setService(
        false,
        "Cannot connect to the local server. Keep it running, then check again.",
      );
    } finally {
      checking = false;
      byId("retry").disabled = false;
    }
  }

  input.addEventListener("input", edit);
  clear.addEventListener("click", () => {
    input.value = "";
    edit();
    input.focus();
  });
  examples.forEach((button) =>
    button.addEventListener("click", () => {
      input.value = messages[button.dataset.example];
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
    clearError();
    showState("loading");
    updateControls();
    let completed = false;
    try {
      const response = await request("/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: input.value }),
      });
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
      if (
        typeof result.suggested_category !== "string" ||
        !result.suggested_category ||
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
      byId("category").textContent = result.suggested_category
        .toLowerCase()
        .replaceAll("_", " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
      byId("score").textContent = result.uncalibrated_probability.toFixed(3);
      byId("json-response").textContent = JSON.stringify(result, null, 2);
      showState("success");
      completed = true;
    } catch (error) {
      showState("idle");
      byId("form-error").textContent =
        error.name === "AbortError"
          ? "The request took too long. Check your local server and try again."
          : error instanceof TypeError
            ? "Connection lost. Keep your local server running and try again."
            : error.message;
      byId("form-error").hidden = false;
    } finally {
      busy = false;
      updateControls();
      if (completed) byId("category").focus();
      else byId("form-error").focus();
    }
  });

  updateControls();
  checkReadiness();
  setInterval(checkReadiness, 30000);
})();
