"use strict";

let globalLoadingCount = 0;

function showGlobalLoading() {
  globalLoadingCount += 1;
  const indicator = document.getElementById("globalLoadingIndicator");
  if (indicator && !indicator.open) indicator.showModal();
}

function hideGlobalLoading() {
  globalLoadingCount = Math.max(0, globalLoadingCount - 1);
  const indicator = document.getElementById("globalLoadingIndicator");
  if (indicator?.open && globalLoadingCount === 0) indicator.close();
}

const nativeFetch = window.fetch.bind(window);
window.fetch = async (...arguments_) => {
  showGlobalLoading();
  try {
    return await nativeFetch(...arguments_);
  } finally {
    hideGlobalLoading();
  }
};

const API_BASE_PATH = "/api";
const TRANSLATIONS_URL = "./assets/i18n/et.json";
const DEFAULT_CONFIDENCE = Number(window.LIIKLUS_CONFIG?.defaultConfidence || 0.45);
const state = {
  translations: {},
  user: null,
  csrfToken: null,
  selectedFile: null,
  previewUrl: null,
  results: [],
  candidates: [],
  packages: [],
  selectedCandidateIds: new Set(),
  handlingUnauthorized: false,
};
const elements = {};

document.addEventListener("DOMContentLoaded", initialize);

async function initialize() {
  cacheElements();
  bindEvents();
  await loadTranslations();
  applyTranslations();
  try {
    await loadCurrentUser();
    showApplication();
  } catch (error) {
    if (error.status !== 401) showLoginMessage(error.message, true);
    await showLogin();
  }
}

function cacheElements() {
  document.querySelectorAll("[id]").forEach((element) => { elements[element.id] = element; });
}

function bindEvents() {
  elements.globalLoadingIndicator.addEventListener("cancel", (event) => event.preventDefault());
  elements.chooseButton.addEventListener("click", openFilePicker);
  elements.replaceButton.addEventListener("click", openFilePicker);
  elements.imageInput.addEventListener("change", () => selectFile(elements.imageInput.files[0]));
  elements.detectForm.addEventListener("submit", submitImage);
  elements.dropZone.addEventListener("click", (event) => { if (!event.target.closest("button")) openFilePicker(); });
  elements.dropZone.addEventListener("keydown", (event) => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); openFilePicker(); } });
  elements.dropZone.addEventListener("dragover", (event) => { event.preventDefault(); elements.dropZone.classList.add("is-dragging"); });
  elements.dropZone.addEventListener("dragleave", () => elements.dropZone.classList.remove("is-dragging"));
  elements.dropZone.addEventListener("drop", (event) => { event.preventDefault(); elements.dropZone.classList.remove("is-dragging"); selectFile(event.dataTransfer.files[0]); });
  elements.threeLevelsInput.addEventListener("change", () => { elements.confidenceInput.disabled = elements.threeLevelsInput.checked; });
  elements.detectionAreaInput.addEventListener("change", updateDetectionAreaOverlays);
  elements.crossClassDedupInput.addEventListener("change", updateCrossClassControls);
  elements.crossClassIouInput.addEventListener("change", () => { clearResults(); clearMessage(elements.requestMessage); });
  elements.profileSelect.addEventListener("change", () => handleProfileChange());
  elements.modelSelect.addEventListener("change", () => { clearResults(); clearMessage(elements.requestMessage); });
  elements.candidateButton.addEventListener("click", () => elements.candidateDialog.showModal());
  elements.cancelCandidateButton.addEventListener("click", () => elements.candidateDialog.close());
  elements.candidateForm.addEventListener("submit", saveCandidate);
  elements.viewJsonButton.addEventListener("click", openJsonDialog);
  elements.downloadJsonButton.addEventListener("click", downloadJson);
  elements.closeJsonButton.addEventListener("click", () => elements.jsonDialog.close());
  elements.closeImageButton.addEventListener("click", () => elements.imageDialog.close());
  elements.logoutButton.addEventListener("click", logout);
  elements.analysisTab.addEventListener("click", () => switchView("analysis"));
  elements.trainingTab.addEventListener("click", () => switchView("training"));
  elements.trainingFilterForm.addEventListener("submit", (event) => { event.preventDefault(); loadTrainingData(); });
  elements.trainingPackageFilter.addEventListener("change", loadTrainingData);
  elements.selectAllCandidates.addEventListener("change", toggleAllCandidates);
  elements.packageCreateForm.addEventListener("submit", createPackage);
  elements.addToPackageButton.addEventListener("click", addSelectedToPackage);
  elements.packageSelect.addEventListener("change", () => { updateAddButton(); loadSelectedPackage(); });
  window.addEventListener("beforeunload", revokePreviewUrl);
}

async function loadTranslations() {
  const response = await fetch(TRANSLATIONS_URL, { credentials: "same-origin" });
  if (!response.ok) throw new Error("Translations unavailable");
  state.translations = await response.json();
}

function applyTranslations() {
  document.title = translate("app.document_title");
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = translate(element.dataset.i18n, { defaultConfidence: formatNumber(DEFAULT_CONFIDENCE, 2) });
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = translate(element.dataset.i18nPlaceholder, { defaultConfidence: formatNumber(DEFAULT_CONFIDENCE, 2) });
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => element.setAttribute("aria-label", translate(element.dataset.i18nAriaLabel)));
  document.querySelectorAll("[data-i18n-title]").forEach((element) => { element.title = translate(element.dataset.i18nTitle); });
  document.querySelectorAll("[data-i18n-alt]").forEach((element) => { element.alt = translate(element.dataset.i18nAlt); });
}

function translate(key, values = {}) {
  let text = state.translations[key] || key;
  Object.entries(values).forEach(([name, value]) => { text = text.replaceAll(`{${name}}`, String(value)); });
  return text;
}

async function apiRequest(path, options = {}, responseType = "json") {
  const method = (options.method || "GET").toUpperCase();
  const headers = { ...(options.headers || {}) };
  if (!(options.body instanceof FormData) && options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  if (state.csrfToken && !["GET", "HEAD"].includes(method)) headers["X-CSRF-Token"] = state.csrfToken;
  const response = await fetch(`${API_BASE_PATH}${path}`, { ...options, headers, credentials: "same-origin" });
  if (response.status === 401 && state.user && path !== "/auth/google") {
    await handleExpiredSession();
    const error = new Error("");
    error.status = 401;
    error.handled = true;
    throw error;
  }
  if (response.ok) {
    if (response.status === 204) return null;
    return responseType === "blob" ? response.blob() : response.json();
  }
  let payload = {};
  try { payload = await response.json(); } catch (_) { /* empty */ }
  const error = new Error(payload.detail || translate("errors.http", { status: response.status, detail: translate("errors.request") }));
  error.status = response.status;
  throw error;
}

async function handleExpiredSession() {
  if (state.handlingUnauthorized) return;
  state.handlingUnauthorized = true;
  state.user = null;
  state.csrfToken = null;
  try {
    await showLogin();
  } finally {
    state.handlingUnauthorized = false;
  }
}

async function loadCurrentUser() {
  state.user = await apiRequest("/auth/me");
  state.csrfToken = state.user.csrf_token;
  elements.currentUser.textContent = state.user.display_name || state.user.email;
  renderQuickTags(state.user.training_quick_tags || []);
  renderProfiles(state.user.camera_profiles || [], state.user.default_camera_profile);
  configureCrossClassDedup();
}

function renderProfiles(profiles, defaultProfile) {
  elements.profileSelect.replaceChildren();
  profiles.forEach((profile) => {
    const option = document.createElement("option");
    option.value = profile.code;
    option.textContent = profile.name;
    elements.profileSelect.append(option);
  });
  elements.profileSelect.value = defaultProfile;
  handleProfileChange(false);
}

function selectedProfile() {
  return (state.user?.camera_profiles || []).find((profile) => profile.code === elements.profileSelect.value) || null;
}

function profileDefaultConfidence() {
  return Number(selectedProfile()?.default_confidence ?? DEFAULT_CONFIDENCE);
}

function handleProfileChange(clear = true) {
  const profile = selectedProfile();
  renderModels(profile?.models || [], profile?.default_model || "");
  elements.confidenceInput.value = "";
  elements.confidenceInput.placeholder = formatNumber(profileDefaultConfidence(), 2);
  elements.confidenceHelp.textContent = translate("upload.confidence_help", { defaultConfidence: formatNumber(profileDefaultConfidence(), 2) });
  elements.detectionAreaInput.checked = true;
  elements.detectionAreaRow.classList.toggle("hidden", !profileHasDetectionArea(profile));
  if (clear) {
    clearResults();
    clearMessage(elements.requestMessage);
  }
}

function renderModels(models, defaultModel) {
  elements.modelSelect.replaceChildren();
  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    elements.modelSelect.append(option);
  });
  elements.modelSelect.value = defaultModel;
}

function configureCrossClassDedup() {
  elements.crossClassDedupInput.checked = Number(state.user.cross_class_dedup_default) === 1;
  elements.crossClassIouInput.value = String(state.user.cross_class_iou_threshold_default);
  updateCrossClassControls(false);
}

function updateCrossClassControls(clear = true) {
  const enabled = elements.crossClassDedupInput.checked;
  elements.crossClassThresholdGroup.classList.toggle("hidden", !enabled);
  elements.crossClassIouInput.disabled = !enabled;
  if (clear) {
    clearResults();
    clearMessage(elements.requestMessage);
  }
}

async function showLogin() {
  elements.appShell.classList.add("hidden");
  elements.loginView.classList.remove("hidden");
  elements.googleButton.replaceChildren();
  try {
    const config = await apiRequest("/auth/google/config");
    await waitForGoogle();
    window.google.accounts.id.initialize({ client_id: config.client_id, callback: handleGoogleCredential });
    window.google.accounts.id.renderButton(elements.googleButton, {
      theme: "outline",
      size: "large",
      text: "signin_with",
      shape: "rectangular",
    });
  } catch (error) {
    showLoginMessage(translate("errors.google"), true);
  }
}

function waitForGoogle() {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const timer = setInterval(() => {
      attempts += 1;
      if (window.google?.accounts?.id) { clearInterval(timer); resolve(); }
      else if (attempts > 50) { clearInterval(timer); reject(new Error("Google unavailable")); }
    }, 100);
  });
}

async function handleGoogleCredential(value) {
  try {
    await apiRequest("/auth/google", { method: "POST", body: JSON.stringify({ id_token: value.credential }) });
    await loadCurrentUser();
    showApplication();
  } catch (error) { showLoginMessage(error.message, true); }
}

function showApplication() {
  elements.loginView.classList.add("hidden");
  elements.appShell.classList.remove("hidden");
  refreshTrainingCount();
}

async function logout() {
  await apiRequest("/auth/logout", { method: "POST" });
  state.user = null; state.csrfToken = null;
  await showLogin();
}

function showLoginMessage(message, error = false) {
  elements.loginMessage.textContent = message;
  elements.loginMessage.classList.toggle("error", error);
}

function openFilePicker() { elements.imageInput.click(); }

function selectFile(file) {
  if (!file) return;
  elements.threeLevelsInput.checked = false;
  elements.detectionAreaInput.checked = true;
  elements.confidenceInput.disabled = false;
  state.selectedFile = file;
  revokePreviewUrl();
  state.previewUrl = URL.createObjectURL(file);
  elements.sourcePreview.src = state.previewUrl;
  elements.selectedFilename.textContent = file.name;
  elements.selectedFileMeta.textContent = translate("upload.file_meta", { type: file.type, size: formatBytes(file.size) });
  elements.dropZone.classList.add("hidden");
  elements.selectionPanel.classList.remove("hidden");
  elements.analyzeButton.disabled = false;
  elements.candidateButton.disabled = false;
  elements.candidateButton.textContent = translate("candidate.open");
  clearResults(); clearMessage(elements.requestMessage);
}

async function submitImage(event) {
  event.preventDefault();
  if (!state.selectedFile) return;
  setSubmitting(true); clearMessage(elements.requestMessage);
  try {
    const levels = elements.threeLevelsInput.checked ? comparisonLevels() : [singleLevel()];
    state.results = await Promise.all(levels.map(analyzeAtLevel));
    renderResults();
  } catch (error) { showMessage(elements.requestMessage, error.message, true); }
  finally { setSubmitting(false); }
}

function comparisonLevels() {
  const defaultConfidence = profileDefaultConfidence();
  return [defaultConfidence, Math.max(0.01, round2(defaultConfidence - 0.20)), Math.max(0.01, round2(defaultConfidence - 0.40))];
}

function singleLevel() {
  const value = elements.confidenceInput.value.trim();
  return value === "" ? profileDefaultConfidence() : Number(value);
}

async function analyzeAtLevel(level) {
  const body = new FormData(); body.append("file", state.selectedFile, state.selectedFile.name);
  const query = new URLSearchParams({ profile: elements.profileSelect.value, conf: String(level), model: elements.modelSelect.value, ...crossClassRequestOptions() });
  return apiRequest(`/detect/image?${query}`, { method: "POST", body });
}

function crossClassRequestOptions() {
  if (!elements.crossClassDedupInput.checked) return { cross_class_dedup: "0" };
  const options = { cross_class_dedup: "1" };
  const threshold = elements.crossClassIouInput.value.trim();
  if (threshold !== "") options.cross_class_iou_threshold = threshold;
  return options;
}

function renderResults() {
  const comparison = state.results.length > 1;
  elements.resultModel.textContent = state.results[0]?.model || "—";
  elements.resultProfile.textContent = state.results[0]?.profile?.name || "—";
  elements.singleResult.classList.toggle("hidden", comparison);
  elements.comparisonTable.classList.toggle("hidden", !comparison);
  elements.differencePanel.classList.toggle("hidden", !comparison);
  elements.comparisonImages.classList.toggle("hidden", !comparison);
  if (comparison) renderComparison(); else renderSingle(state.results[0]);
  renderTrainingHistory(state.results.find((result) => result.training_history)?.training_history || null);
  elements.resultsCard.classList.remove("hidden");
  elements.resultsCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderSingle(result) {
  elements.countGrid.replaceChildren();
  Object.entries(result.counts).forEach(([name, count]) => elements.countGrid.append(createCountCard(classLabel(name), count)));
  elements.countGrid.append(createCountCard(translate("results.total"), result.total, true));
  elements.annotatedImage.src = imageDataUrl(result);
  configureDetectionAreaOverlay(elements.detectionAreaOverlay, result);
  elements.annotatedImage.onclick = () => openLargeImage(imageDataUrl(result), result);
  elements.resultCaption.textContent = translate("results.caption", { filename: result.filename || "—" });
  elements.resultFilename.textContent = result.filename || "—";
  elements.resultImageSize.textContent = translate("results.image_size_value", result.image_size);
  elements.resultConfidence.textContent = formatNumber(result.conf, 2);
  elements.resultCrossClassDedup.textContent = translate(result.cross_class_dedup === 1 ? "common.on" : "common.off");
  const dedupEnabled = result.cross_class_dedup === 1;
  elements.resultCrossClassIouRow.classList.toggle("hidden", !dedupEnabled);
  elements.resultCrossClassIou.textContent = dedupEnabled ? formatNumber(result.cross_class_iou_threshold, 2) : "";
  elements.resultDuration.textContent = translate("results.processing_time_value", { duration: formatNumber(result.processing_duration_ms, 1) });
  elements.resultReceivedAt.textContent = formatDateTime(result.request_received_at);
  renderDetections(result.detections || []);
}

function renderComparison() {
  const table = document.createElement("table");
  const caption = table.createCaption();
  const firstResult = state.results[0];
  const dedupText = `${translate("results.cross_class_dedup")}: ${translate(firstResult?.cross_class_dedup === 1 ? "common.on" : "common.off")}`;
  const thresholdText = firstResult?.cross_class_dedup === 1 ? ` · ${translate("results.cross_class_iou")}: ${formatNumber(firstResult.cross_class_iou_threshold, 2)}` : "";
  caption.textContent = `${translate("results.model")}: ${firstResult?.model || "—"} · ${dedupText}${thresholdText}`;
  const head = document.createElement("thead");
  head.innerHTML = `<tr><th></th>${state.results.map((result) => `<th>${escapeHtml(translate("results.level", { conf: formatNumber(result.conf, 2) }))}</th>`).join("")}</tr>`;
  table.append(head);
  const body = document.createElement("tbody");
  [...Object.keys(firstResult?.counts || {}), "total"].forEach((name) => {
    const row = document.createElement("tr");
    const label = name === "total" ? translate("results.total") : classLabel(name);
    row.innerHTML = `<th>${escapeHtml(label)}</th>${state.results.map((result) => `<td>${name === "total" ? result.total : result.counts[name]}</td>`).join("")}`;
    body.append(row);
  });
  table.append(body); elements.comparisonTable.replaceChildren(table);
  const differences = comparisonDifferences();
  elements.differencePanel.replaceChildren();
  const title = document.createElement("h3"); title.textContent = translate("results.differences"); elements.differencePanel.append(title);
  if (!differences.length) { const p = document.createElement("p"); p.textContent = translate("results.no_differences"); elements.differencePanel.append(p); }
  else { const list = document.createElement("ul"); differences.forEach((text) => { const item = document.createElement("li"); item.textContent = text; list.append(item); }); elements.differencePanel.append(list); }
  elements.comparisonImages.replaceChildren();
  state.results.forEach((result) => {
    const figure = document.createElement("figure"); const title = document.createElement("figcaption");
    title.textContent = `${translate("results.level", { conf: formatNumber(result.conf, 2) })} · ${result.total}`;
    const visual = document.createElement("div"); visual.className = "result-image-visual";
    const image = document.createElement("img"); image.src = imageDataUrl(result); image.alt = translate("results.image_alt"); image.addEventListener("click", () => openLargeImage(image.src, result));
    const overlay = createDetectionAreaOverlay(result);
    visual.append(image); if (overlay) visual.append(overlay);
    figure.append(title, visual); elements.comparisonImages.append(figure);
  });
}

function comparisonDifferences() {
  const messages = [];
  for (let index = 1; index < state.results.length; index += 1) {
    const higher = state.results[index - 1].detections || [];
    const lower = state.results[index].detections || [];
    const matched = new Set();
    higher.forEach((detection) => {
      let best = -1; let bestIou = 0;
      lower.forEach((candidate, candidateIndex) => { if (!matched.has(candidateIndex) && candidate.class === detection.class) { const value = boxIou(detection.bbox_xyxy, candidate.bbox_xyxy); if (value > bestIou) { bestIou = value; best = candidateIndex; } } });
      if (best >= 0 && bestIou >= 0.7) matched.add(best);
    });
    lower.forEach((detection, detectionIndex) => {
      if (!matched.has(detectionIndex)) messages.push(translate("results.added_detection", { conf: formatNumber(state.results[index].conf, 2), className: classLabel(detection.class), confidence: formatNumber(detection.confidence, 3), coordinates: detection.bbox_xyxy.join(", ") }));
    });
  }
  return messages;
}

function boxIou(a, b) {
  const intersection = Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) * Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
  const union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection;
  return union > 0 ? intersection / union : 0;
}

function renderTrainingHistory(history) {
  elements.trainingHistory.replaceChildren();
  elements.trainingHistory.classList.toggle("hidden", !history);
  const activeHistory = Boolean(history?.selections?.some((item) => item.file_available));
  elements.candidateButton.disabled = activeHistory || !state.selectedFile;
  elements.candidateButton.textContent = translate(activeHistory ? "candidate.already" : "candidate.open");
  if (!history) return;
  history.selections.forEach((selection) => {
    const block = document.createElement("div");
    const candidate = document.createElement("p");
    candidate.innerHTML = `<strong>${escapeHtml(translate("history.candidate"))}:</strong> ${escapeHtml(formatDateTime(selection.candidate_at))} · ${escapeHtml(selection.candidate_by)}${selection.file_available ? "" : ` · ${escapeHtml(translate("history.deleted"))}`}`;
    block.append(candidate);
    const selected = document.createElement("p"); selected.innerHTML = `<strong>${escapeHtml(translate("history.selected"))}:</strong>`; block.append(selected);
    if (!selection.packages.length) { const text = document.createElement("span"); text.textContent = translate("history.not_selected"); block.append(text); }
    else { const list = document.createElement("ul"); selection.packages.forEach((item) => { const li = document.createElement("li"); li.textContent = `${item.package_name} · ${formatDateTime(item.added_at)} · ${item.added_by_name || item.added_by_email}`; list.append(li); }); block.append(list); }
    elements.trainingHistory.append(block);
  });
}

function renderQuickTags(tags) {
  elements.candidateTags.replaceChildren();
  tags.forEach((tag) => { const label = document.createElement("label"); label.className = "tag-choice"; const input = document.createElement("input"); input.type = "checkbox"; input.value = tag; label.append(input, document.createTextNode(tag)); elements.candidateTags.append(label); });
}

async function saveCandidate(event) {
  event.preventDefault();
  const selectedTags = [...elements.candidateTags.querySelectorAll("input:checked")].map((input) => input.value);
  const reason = elements.candidateReason.value.trim();
  const body = new FormData(); body.append("file", state.selectedFile, state.selectedFile.name); body.append("reason", reason); body.append("tags", JSON.stringify(selectedTags)); body.append("profile", elements.profileSelect.value); body.append("model", elements.modelSelect.value);
  Object.entries(crossClassRequestOptions()).forEach(([name, value]) => body.append(name, value));
  try {
    await apiRequest("/training-pool", { method: "POST", body });
    elements.candidateDialog.close(); elements.candidateForm.reset();
    elements.candidateButton.disabled = true; elements.candidateButton.textContent = translate("candidate.already");
    showMessage(elements.requestMessage, translate("candidate.saved")); refreshTrainingCount();
  } catch (error) { showMessage(elements.requestMessage, error.message, true); }
}

function switchView(view) {
  const training = view === "training";
  elements.analysisView.classList.toggle("hidden", training); elements.trainingView.classList.toggle("hidden", !training);
  elements.analysisTab.classList.toggle("is-active", !training); elements.trainingTab.classList.toggle("is-active", training);
  if (training) loadTrainingData();
}

async function refreshTrainingCount() {
  try { const data = await apiRequest("/training-pool?limit=1"); elements.trainingCount.textContent = `(${data.total})`; }
  catch (_) { elements.trainingCount.textContent = ""; }
}

async function loadTrainingData() {
  try {
    const query = encodeURIComponent(elements.trainingFilter.value.trim());
    const packageFilter = encodeURIComponent(elements.trainingPackageFilter.value);
    const [candidateData, packages] = await Promise.all([apiRequest(`/training-pool?q=${query}&package=${packageFilter}&limit=200`), apiRequest("/training-packages")]);
    state.candidates = candidateData.items; state.packages = packages; state.selectedCandidateIds.clear();
    elements.trainingTotal.textContent = String(candidateData.total); elements.trainingCount.textContent = `(${candidateData.total})`;
    renderPackageFilter(); renderCandidates(); renderPackages(); renderPackageSelect(); updateAddButton();
  } catch (error) { showMessage(elements.trainingMessage, error.message, true); }
}

function renderCandidates() {
  elements.candidateGrid.replaceChildren();
  if (!state.candidates.length) { const p = document.createElement("p"); p.textContent = translate("training.empty"); elements.candidateGrid.append(p); return; }
  state.candidates.forEach((candidate) => {
    const card = document.createElement("article"); card.className = "candidate-card";
    const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.addEventListener("change", () => { if (checkbox.checked) state.selectedCandidateIds.add(candidate.public_id); else state.selectedCandidateIds.delete(candidate.public_id); updateAddButton(); });
    const image = document.createElement("img"); image.loading = "lazy"; image.src = `${API_BASE_PATH}/training-pool/${candidate.public_id}/image?thumbnail=true`; image.alt = candidate.original_filename; image.addEventListener("click", () => openLargeImage(`${API_BASE_PATH}/training-pool/${candidate.public_id}/image`));
    const body = document.createElement("div"); const name = document.createElement("h3"); name.textContent = candidate.original_filename; const reason = document.createElement("p"); reason.textContent = candidate.reason;
    const meta = document.createElement("p"); meta.className = "muted"; meta.textContent = translate("training.candidate_by", { name: candidate.candidate_by_name || candidate.candidate_by_email, date: formatDateTime(candidate.created) });
    const tags = document.createElement("div"); tags.className = "saved-tags"; (candidate.tags || []).forEach((tag) => { const badge = document.createElement("span"); badge.textContent = tag; tags.append(badge); });
    const counts = document.createElement("p"); counts.className = "muted"; counts.textContent = Object.entries(candidate.detections_summary?.counts || {}).map(([name, count]) => `${classLabel(name)}: ${count}`).join(" · ");
    const packages = document.createElement("div"); packages.className = "candidate-packages"; const packageLabel = document.createElement("strong"); packageLabel.textContent = translate("training.candidate_packages"); packages.append(packageLabel);
    if (!(candidate.packages || []).length) { const empty = document.createElement("span"); empty.textContent = translate("training.package_filter_none"); packages.append(empty); }
    else { const list = document.createElement("ul"); candidate.packages.forEach((item) => { const row = document.createElement("li"); row.textContent = `${item.package_name} · ${item.added_by_name || item.added_by_email} · ${formatDateTime(item.added_at)}`; list.append(row); }); packages.append(list); }
    const remove = document.createElement("button"); remove.type = "button"; remove.className = "danger-button compact"; remove.textContent = translate("training.delete"); remove.addEventListener("click", () => deleteCandidate(candidate.public_id));
    body.append(name); if (candidate.reason) body.append(reason); if (tags.childElementCount) body.append(tags); body.append(counts, meta, packages, remove); card.append(checkbox, image, body); elements.candidateGrid.append(card);
  });
}

function renderPackageFilter() {
  const selected = elements.trainingPackageFilter.value;
  elements.trainingPackageFilter.replaceChildren();
  const all = document.createElement("option"); all.value = ""; all.textContent = translate("training.package_filter_all"); elements.trainingPackageFilter.append(all);
  const none = document.createElement("option"); none.value = "__none__"; none.textContent = translate("training.package_filter_none"); elements.trainingPackageFilter.append(none);
  state.packages.forEach((item) => { const option = document.createElement("option"); option.value = item.public_id; option.textContent = item.package_name; elements.trainingPackageFilter.append(option); });
  if ([...elements.trainingPackageFilter.options].some((option) => option.value === selected)) elements.trainingPackageFilter.value = selected;
}

function renderPackages() {
  elements.packageList.replaceChildren();
  if (!state.packages.length) { const p = document.createElement("p"); p.textContent = translate("training.package_empty"); elements.packageList.append(p); return; }
  state.packages.forEach((item) => {
    const card = document.createElement("article"); card.className = "package-card";
    const heading = document.createElement("h3"); heading.textContent = item.package_name;
    const details = document.createElement("p"); details.textContent = `${translate("training.package_count", { count: item.image_count })} · ${translate(item.first_downloaded_at ? "training.package_locked" : "training.package_open")}`;
    const creator = document.createElement("p"); creator.className = "muted"; creator.textContent = translate("training.created_by", { name: item.created_by_name || item.created_by_email });
    card.append(heading, details, creator);
    if (item.last_downloaded_at) { const last = document.createElement("p"); last.className = "muted"; last.textContent = translate("training.last_download", { name: item.last_downloaded_by_name, date: formatDateTime(item.last_downloaded_at) }); card.append(last); }
    const actions = document.createElement("div"); actions.className = "card-actions";
    const view = document.createElement("button"); view.type = "button"; view.className = "secondary-button"; view.textContent = translate("training.view_contents"); view.addEventListener("click", () => showPackageContents(item.public_id));
    const download = document.createElement("button"); download.type = "button"; download.textContent = translate("training.download"); download.disabled = Number(item.image_count) === 0; download.addEventListener("click", () => downloadPackage(item)); actions.append(view, download); card.append(actions);
    elements.packageList.append(card);
  });
}

function renderPackageSelect() {
  elements.packageSelect.replaceChildren(); const placeholder = document.createElement("option"); placeholder.value = ""; placeholder.textContent = translate("training.select_package"); elements.packageSelect.append(placeholder);
  state.packages.filter((item) => !item.first_downloaded_at).forEach((item) => { const option = document.createElement("option"); option.value = item.public_id; option.textContent = item.package_name; elements.packageSelect.append(option); });
  elements.packageContents.classList.add("hidden");
}

async function loadSelectedPackage() {
  const packageId = elements.packageSelect.value;
  elements.packageContents.classList.toggle("hidden", !packageId);
  if (!packageId) return;
  await showPackageContents(packageId);
}

async function showPackageContents(packageId) {
  elements.packageContents.replaceChildren();
  elements.packageContents.classList.remove("hidden");
  try {
    const item = await apiRequest(`/training-packages/${packageId}`);
    const heading = document.createElement("h3"); heading.textContent = `${translate("training.package_contents")}: ${item.package_name}`; elements.packageContents.append(heading);
    const list = document.createElement("ul");
    item.items.forEach((image) => {
      const row = document.createElement("li"); const text = document.createElement("span"); text.textContent = `${image.original_filename} · ${formatDateTime(image.added_at)} · ${image.added_by}`; row.append(text);
      if (!item.first_downloaded_at) { const remove = document.createElement("button"); remove.type = "button"; remove.className = "secondary-button compact"; remove.textContent = translate("training.remove_from_package"); remove.addEventListener("click", () => removeFromPackage(packageId, image.id)); row.append(remove); }
      list.append(row);
    });
    elements.packageContents.append(list);
    elements.packageContents.scrollIntoView({ behavior: "smooth", block: "nearest" });
  } catch (error) { showMessage(elements.trainingMessage, error.message, true); }
}

async function removeFromPackage(packageId, imageId) {
  try { await apiRequest(`/training-packages/${packageId}/images/${imageId}`, { method: "DELETE" }); await loadTrainingData(); }
  catch (error) { showMessage(elements.trainingMessage, error.message, true); }
}

function toggleAllCandidates() {
  state.selectedCandidateIds.clear();
  elements.candidateGrid.querySelectorAll('input[type="checkbox"]').forEach((input, index) => { input.checked = elements.selectAllCandidates.checked; if (input.checked) state.selectedCandidateIds.add(state.candidates[index].public_id); });
  updateAddButton();
}

function updateAddButton() { elements.addToPackageButton.disabled = !elements.packageSelect.value || state.selectedCandidateIds.size === 0; }

async function createPackage(event) {
  event.preventDefault(); clearMessage(elements.trainingMessage);
  try { await apiRequest("/training-packages", { method: "POST", body: JSON.stringify({ name: elements.packageName.value.trim() }) }); elements.packageCreateForm.reset(); showMessage(elements.trainingMessage, translate("training.package_created")); await loadTrainingData(); }
  catch (error) { showMessage(elements.trainingMessage, error.message, true); }
}

async function addSelectedToPackage() {
  try { const result = await apiRequest(`/training-packages/${elements.packageSelect.value}/images`, { method: "POST", body: JSON.stringify({ image_ids: [...state.selectedCandidateIds] }) }); showMessage(elements.trainingMessage, translate("training.added", { count: result.added_count })); await loadTrainingData(); }
  catch (error) { showMessage(elements.trainingMessage, error.message, true); }
}

async function downloadPackage(item) {
  try { const blob = await apiRequest(`/training-packages/${item.public_id}/download`, { method: "POST" }, "blob"); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `${safeFilename(item.package_name)}.zip`; link.click(); URL.revokeObjectURL(url); await loadTrainingData(); }
  catch (error) { showMessage(elements.trainingMessage, error.message, true); }
}

async function deleteCandidate(id) {
  if (!window.confirm(translate("training.delete_confirm"))) return;
  try { await apiRequest(`/training-pool/${id}`, { method: "DELETE" }); showMessage(elements.trainingMessage, translate("training.deleted")); await loadTrainingData(); }
  catch (error) { showMessage(elements.trainingMessage, error.message, true); }
}

function openJsonDialog() { const values = displayResults(); elements.jsonOutput.textContent = JSON.stringify(values.length === 1 ? values[0] : values, null, 2); elements.jsonDialog.showModal(); }
function displayResults() { return state.results.map((result) => { const copy = structuredClone(result); if (copy.annotated_image) delete copy.annotated_image.base64; return copy; }); }
function downloadJson() { const value = state.results.length === 1 ? displayResults()[0] : displayResults(); const url = URL.createObjectURL(new Blob([`${JSON.stringify(value, null, 2)}\n`], { type: "application/json" })); const link = document.createElement("a"); link.href = url; link.download = `${safeFilename(state.selectedFile?.name || "tuvastus")}-tuvastus.json`; link.click(); URL.revokeObjectURL(url); }
function openLargeImage(src, result = null) { elements.largeImage.src = src; configureDetectionAreaOverlay(elements.largeDetectionAreaOverlay, result); elements.imageDialog.showModal(); }
function imageDataUrl(result) { return `data:${result.annotated_image.media_type};base64,${result.annotated_image.base64}`; }

function profileHasDetectionArea(profile) { return Array.isArray(profile?.roi_polygon) && profile.roi_polygon.length >= 3; }
function resultProfile(result) { return (state.user?.camera_profiles || []).find((profile) => profile.code === result?.profile?.code) || null; }
function detectionAreaPath(points) {
  const polygon = points.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x * 1000} ${y * 1000}`).join(" ");
  return { outside: `M 0 0 H 1000 V 1000 H 0 Z ${polygon} Z` };
}
function configureDetectionAreaOverlay(overlay, result) {
  const profile = resultProfile(result);
  if (!profileHasDetectionArea(profile)) { overlay.classList.add("hidden"); return; }
  const path = detectionAreaPath(profile.roi_polygon);
  overlay.querySelector(".detection-area-shade").setAttribute("d", path.outside);
  overlay.querySelector(".detection-area-boundary").setAttribute("points", profile.roi_polygon.map(([x, y]) => `${x * 1000},${y * 1000}`).join(" "));
  overlay.classList.toggle("hidden", !elements.detectionAreaInput.checked);
}
function createDetectionAreaOverlay(result) {
  if (!profileHasDetectionArea(resultProfile(result))) return null;
  const namespace = "http://www.w3.org/2000/svg";
  const overlay = document.createElementNS(namespace, "svg");
  overlay.setAttribute("viewBox", "0 0 1000 1000"); overlay.setAttribute("preserveAspectRatio", "none"); overlay.setAttribute("aria-hidden", "true"); overlay.classList.add("detection-area-overlay");
  const shade = document.createElementNS(namespace, "path"); shade.classList.add("detection-area-shade"); shade.setAttribute("fill-rule", "evenodd");
  const boundary = document.createElementNS(namespace, "polygon"); boundary.classList.add("detection-area-boundary");
  overlay.append(shade, boundary); configureDetectionAreaOverlay(overlay, result); return overlay;
}
function updateDetectionAreaOverlays() { document.querySelectorAll(".detection-area-overlay").forEach((overlay) => overlay.classList.toggle("hidden", !elements.detectionAreaInput.checked)); }

function createCountCard(label, count, total = false) { const card = document.createElement("div"); card.className = `count-card${total ? " is-total" : ""}`; card.innerHTML = `<span class="count-label">${escapeHtml(label)}</span><strong class="count-value">${count}</strong>`; return card; }
function renderDetections(detections) { elements.detectionsSummary.textContent = translate("detections.summary", { count: detections.length }); elements.detectionsBody.replaceChildren(); detections.forEach((detection) => { const row = document.createElement("tr"); [classLabel(detection.class), formatNumber(detection.confidence, 3), detection.bbox_xyxy.join(", ")].forEach((value) => { const cell = document.createElement("td"); cell.textContent = value; row.append(cell); }); elements.detectionsBody.append(row); }); }
function classLabel(name) {
  const translated = state.translations[`classes.${name}`];
  if (translated) return translated;
  const profileClass = selectedProfile()?.classes?.find((item) => item.code === name);
  return profileClass?.name || name;
}
function formatNumber(value, digits) { return new Intl.NumberFormat("et-EE", { maximumFractionDigits: digits }).format(value); }
function formatDateTime(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : new Intl.DateTimeFormat("et-EE", { dateStyle: "medium", timeStyle: "medium" }).format(date); }
function formatBytes(bytes) { return bytes < 1024 * 1024 ? `${formatNumber(bytes / 1024, 1)} KiB` : `${formatNumber(bytes / (1024 * 1024), 1)} MiB`; }
function round2(value) { return Math.round((value + Number.EPSILON) * 100) / 100; }
function safeFilename(value) { return value.replace(/\.[^.]+$/, "").replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-") || "download"; }
function escapeHtml(value) { const div = document.createElement("div"); div.textContent = String(value); return div.innerHTML; }
function showMessage(element, message, error = false) { element.textContent = message; element.classList.toggle("error", error); }
function clearMessage(element) { showMessage(element, "", false); }
function setSubmitting(value) { const activeHistory = state.results.some((result) => result.training_history?.selections?.some((item) => item.file_available)); elements.analyzeButton.disabled = value || !state.selectedFile; elements.replaceButton.disabled = value; elements.threeLevelsInput.disabled = value; elements.crossClassDedupInput.disabled = value; elements.crossClassIouInput.disabled = value || !elements.crossClassDedupInput.checked; elements.profileSelect.disabled = value; elements.modelSelect.disabled = value; elements.confidenceInput.disabled = value || elements.threeLevelsInput.checked; elements.candidateButton.disabled = value || !state.selectedFile || activeHistory; elements.analyzeButton.textContent = translate(value ? "upload.analyzing" : "upload.analyze"); }
function clearResults() { state.results = []; elements.resultsCard.classList.add("hidden"); elements.trainingHistory.classList.add("hidden"); elements.comparisonImages.replaceChildren(); }
function revokePreviewUrl() { if (state.previewUrl) URL.revokeObjectURL(state.previewUrl); state.previewUrl = null; }

