"use strict";

const API_BASE_PATH = "/api";
const TRANSLATIONS_URL = "./assets/i18n/et.json";
const DEFAULT_CONFIDENCE = window.LIIKLUS_CONFIG?.defaultConfidence || "—";

const state = {
  translations: {},
  selectedFile: null,
  previewUrl: null,
  isSubmitting: false,
  result: null,
};

const elements = {};

document.addEventListener("DOMContentLoaded", initialize);

async function initialize() {
  cacheElements();
  bindEvents();

  try {
    const response = await fetch(TRANSLATIONS_URL, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`Translation request failed: ${response.status}`);
    state.translations = await response.json();
    applyTranslations();
  } catch (error) {
    console.error(error);
  }
}

function cacheElements() {
  Object.assign(elements, {
    form: document.querySelector("#detectForm"),
    fileInput: document.querySelector("#imageInput"),
    dropZone: document.querySelector("#dropZone"),
    chooseButton: document.querySelector("#chooseButton"),
    replaceButton: document.querySelector("#replaceButton"),
    selectionPanel: document.querySelector("#selectionPanel"),
    selectionStatus: document.querySelector("#selectionStatus"),
    sourcePreview: document.querySelector("#sourcePreview"),
    selectedFilename: document.querySelector("#selectedFilename"),
    selectedFileMeta: document.querySelector("#selectedFileMeta"),
    confidenceInput: document.querySelector("#confidenceInput"),
    analyzeButton: document.querySelector("#analyzeButton"),
    requestMessage: document.querySelector("#requestMessage"),
    resultsCard: document.querySelector("#resultsCard"),
    countGrid: document.querySelector("#countGrid"),
    annotatedImage: document.querySelector("#annotatedImage"),
    resultCaption: document.querySelector("#resultCaption"),
    resultFilename: document.querySelector("#resultFilename"),
    resultImageSize: document.querySelector("#resultImageSize"),
    resultConfidence: document.querySelector("#resultConfidence"),
    resultDuration: document.querySelector("#resultDuration"),
    resultReceivedAt: document.querySelector("#resultReceivedAt"),
    detectionsDetails: document.querySelector("#detectionsDetails"),
    detectionsSummary: document.querySelector("#detectionsSummary"),
    detectionsBody: document.querySelector("#detectionsBody"),
    viewJsonButton: document.querySelector("#viewJsonButton"),
    newImageButton: document.querySelector("#newImageButton"),
    jsonDialog: document.querySelector("#jsonDialog"),
    downloadJsonButton: document.querySelector("#downloadJsonButton"),
    closeJsonButton: document.querySelector("#closeJsonButton"),
    jsonOutput: document.querySelector("#jsonOutput"),
  });
}

function bindEvents() {
  elements.chooseButton.addEventListener("click", openFilePicker);
  elements.replaceButton.addEventListener("click", openFilePicker);
  elements.fileInput.addEventListener("change", () => selectFile(elements.fileInput.files[0]));
  elements.form.addEventListener("submit", submitImage);
  elements.viewJsonButton.addEventListener("click", openJsonDialog);
  elements.downloadJsonButton.addEventListener("click", downloadJson);
  elements.closeJsonButton.addEventListener("click", () => elements.jsonDialog.close());
  elements.newImageButton.addEventListener("click", resetForNewImage);
  elements.dropZone.addEventListener("click", (event) => {
    if (event.target.closest("button")) return;
    openFilePicker();
  });
  elements.dropZone.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openFilePicker();
    }
  });
  elements.dropZone.addEventListener("dragover", handleDragOver);
  elements.dropZone.addEventListener("dragleave", handleDragLeave);
  elements.dropZone.addEventListener("drop", handleDrop);
}

function applyTranslations() {
  document.title = translate("app.document_title");
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = translate(element.dataset.i18n, {
      defaultConfidence: DEFAULT_CONFIDENCE,
    });
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
    element.placeholder = translate(element.dataset.i18nPlaceholder, {
      defaultConfidence: DEFAULT_CONFIDENCE,
    });
  });
  document.querySelectorAll("[data-i18n-aria-label]").forEach((element) => {
    element.setAttribute("aria-label", translate(element.dataset.i18nAriaLabel));
  });
  document.querySelectorAll("[data-i18n-title]").forEach((element) => {
    element.title = translate(element.dataset.i18nTitle);
  });
  document.querySelectorAll("[data-i18n-alt]").forEach((element) => {
    element.alt = translate(element.dataset.i18nAlt);
  });
}

function translate(key, values = {}) {
  const template = state.translations[key] || key;
  return Object.entries(values).reduce(
    (text, [name, value]) => text.replaceAll(`{${name}}`, String(value)),
    template,
  );
}

function openFilePicker() {
  if (!state.isSubmitting) {
    elements.fileInput.value = "";
    elements.fileInput.click();
  }
}

function handleDragOver(event) {
  event.preventDefault();
  if (!state.isSubmitting) elements.dropZone.classList.add("is-dragging");
}

function handleDragLeave(event) {
  if (!elements.dropZone.contains(event.relatedTarget)) {
    elements.dropZone.classList.remove("is-dragging");
  }
}

function handleDrop(event) {
  event.preventDefault();
  elements.dropZone.classList.remove("is-dragging");
  if (!state.isSubmitting) selectFile(event.dataTransfer.files[0]);
}

function selectFile(file) {
  clearMessage();
  if (!file) return;

  revokePreviewUrl();
  state.selectedFile = file;
  state.previewUrl = URL.createObjectURL(file);
  elements.sourcePreview.src = state.previewUrl;
  elements.sourcePreview.alt = file.name;
  elements.selectedFilename.textContent = file.name;
  elements.selectedFileMeta.textContent = translate("upload.file_meta", {
    type: formatFileType(file.type),
    size: formatBytes(file.size),
  });
  elements.dropZone.classList.add("hidden");
  elements.selectionPanel.classList.remove("hidden");
  elements.selectionStatus.textContent = translate("upload.selected_status");
  elements.analyzeButton.disabled = false;
  clearResults();
}

function formatFileType(mediaType) {
  if (mediaType === "image/png") return "PNG";
  if (mediaType === "image/jpeg") return "JPEG";
  return mediaType || "—";
}

function formatBytes(bytes) {
  const formatter = new Intl.NumberFormat("et-EE", { maximumFractionDigits: 1 });
  if (bytes < 1024) return `${formatter.format(bytes)} B`;
  if (bytes < 1024 * 1024) return `${formatter.format(bytes / 1024)} KiB`;
  return `${formatter.format(bytes / (1024 * 1024))} MiB`;
}

async function submitImage(event) {
  event.preventDefault();
  if (!state.selectedFile || state.isSubmitting) return;

  const confidence = elements.confidenceInput.value.trim();
  setSubmitting(true);
  clearMessage();
  const body = new FormData();
  body.append("file", state.selectedFile, state.selectedFile.name);
  const query = confidence === "" ? "" : `?conf=${encodeURIComponent(confidence)}`;

  try {
    const result = await apiRequest(`/detect/image${query}`, { method: "POST", body });
    renderResult(result);
  } catch (error) {
    showMessage(error.message || translate("errors.request"), true);
  } finally {
    setSubmitting(false);
  }
}

async function apiRequest(path, options = {}) {
  let response;
  try {
    response = await fetch(`${API_BASE_PATH}${path}`, {
      ...options,
      credentials: "same-origin",
      headers: { Accept: "application/json", ...(options.headers || {}) },
    });
  } catch (error) {
    throw new Error(translate("errors.connection"), { cause: error });
  }

  const payload = await parseJson(response);
  if (response.ok) return payload;
  if (response.status === 401) throw new Error(translate("errors.unauthorized"));
  if (response.status === 403) throw new Error(translate("errors.forbidden"));

  throw new Error(translate("errors.http", {
    status: response.status,
    detail: extractErrorDetail(payload),
  }));
}

async function parseJson(response) {
  try {
    return await response.json();
  } catch (error) {
    throw new Error(translate("errors.invalid_response"), { cause: error });
  }
}

function extractErrorDetail(payload) {
  if (typeof payload?.detail === "string") return payload.detail;
  if (Array.isArray(payload?.detail)) {
    return payload.detail.map((item) => item.msg).filter(Boolean).join("; ") || translate("errors.request");
  }
  return translate("errors.request");
}

function renderResult(result) {
  if (!result?.counts || !result?.annotated_image?.base64 || !result?.image_size) {
    throw new Error(translate("errors.invalid_response"));
  }

  state.result = result;
  elements.countGrid.replaceChildren();
  Object.entries(result.counts).forEach(([className, count]) => {
    elements.countGrid.append(createCountCard(classLabel(className), count));
  });
  elements.countGrid.append(createCountCard(translate("results.total"), result.total, true));

  elements.annotatedImage.src = `data:${result.annotated_image.media_type};base64,${result.annotated_image.base64}`;
  elements.resultCaption.textContent = translate("results.caption", { filename: result.filename || "—" });
  elements.resultFilename.textContent = result.filename || "—";
  elements.resultImageSize.textContent = translate("results.image_size_value", result.image_size);
  elements.resultConfidence.textContent = formatNumber(result.conf, 2);
  elements.resultDuration.textContent = translate("results.processing_time_value", {
    duration: formatNumber(result.processing_duration_ms, 1),
  });
  elements.resultReceivedAt.textContent = formatDateTime(result.request_received_at);
  renderDetections(result.detections || []);
  elements.resultsCard.classList.remove("hidden");
  elements.resultsCard.scrollIntoView({ behavior: "smooth", block: "start" });
}

function openJsonDialog() {
  if (!state.result) return;
  elements.jsonOutput.textContent = JSON.stringify(displayJsonResult(), null, 2);
  elements.jsonDialog.showModal();
}

function displayJsonResult() {
  const displayResult = structuredClone(state.result);
  if (displayResult.annotated_image) {
    delete displayResult.annotated_image.base64;
  }
  return displayResult;
}

function downloadJson() {
  if (!state.result) return;
  const json = `${JSON.stringify(displayJsonResult(), null, 2)}\n`;
  const blobUrl = URL.createObjectURL(new Blob([json], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = blobUrl;
  link.download = jsonDownloadFilename(state.result.filename);
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(blobUrl);
}

function jsonDownloadFilename(filename) {
  const basename = (filename || "tuvastus").replace(/\.[^.]+$/, "");
  const safeBasename = basename.replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-") || "tuvastus";
  return `${safeBasename}-tuvastus.json`;
}

function createCountCard(label, count, isTotal = false) {
  const card = document.createElement("div");
  card.className = `count-card${isTotal ? " is-total" : ""}`;
  const labelElement = document.createElement("span");
  labelElement.className = "count-label";
  labelElement.textContent = label;
  const valueElement = document.createElement("strong");
  valueElement.className = "count-value";
  valueElement.textContent = String(count);
  card.append(labelElement, valueElement);
  return card;
}

function renderDetections(detections) {
  elements.detectionsSummary.textContent = translate("detections.summary", { count: detections.length });
  elements.detectionsBody.replaceChildren();
  detections.forEach((detection) => {
    const row = document.createElement("tr");
    const classCell = document.createElement("td");
    classCell.textContent = classLabel(detection.class);
    const confidenceCell = document.createElement("td");
    confidenceCell.textContent = formatNumber(detection.confidence, 3);
    const boxCell = document.createElement("td");
    boxCell.textContent = detection.bbox_xyxy.join(", ");
    row.append(classCell, confidenceCell, boxCell);
    elements.detectionsBody.append(row);
  });
  elements.detectionsDetails.open = false;
}

function classLabel(className) {
  const key = `classes.${className}`;
  return state.translations[key] || className;
}

function formatNumber(value, maximumFractionDigits) {
  return new Intl.NumberFormat("et-EE", { maximumFractionDigits }).format(value);
}

function formatDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("et-EE", { dateStyle: "medium", timeStyle: "medium" }).format(date);
}

function setSubmitting(isSubmitting) {
  state.isSubmitting = isSubmitting;
  elements.analyzeButton.disabled = isSubmitting || !state.selectedFile;
  elements.replaceButton.disabled = isSubmitting;
  elements.confidenceInput.disabled = isSubmitting;
  elements.analyzeButton.textContent = translate(isSubmitting ? "upload.analyzing" : "upload.analyze");
}

function showMessage(message, isError = false) {
  elements.requestMessage.textContent = message;
  elements.requestMessage.classList.toggle("error", isError);
}

function clearMessage() {
  elements.requestMessage.textContent = "";
  elements.requestMessage.classList.remove("error");
}

function clearResults() {
  state.result = null;
  elements.resultsCard.classList.add("hidden");
  elements.annotatedImage.removeAttribute("src");
  elements.countGrid.replaceChildren();
  elements.detectionsBody.replaceChildren();
}

function resetForNewImage() {
  state.selectedFile = null;
  elements.fileInput.value = "";
  elements.selectionPanel.classList.add("hidden");
  elements.dropZone.classList.remove("hidden");
  elements.selectionStatus.textContent = translate("upload.empty_status");
  elements.analyzeButton.disabled = true;
  clearMessage();
  clearResults();
  revokePreviewUrl();
  elements.dropZone.focus();
}

function revokePreviewUrl() {
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = null;
}

window.addEventListener("beforeunload", revokePreviewUrl);
