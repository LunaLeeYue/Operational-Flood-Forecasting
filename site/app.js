"use strict";

const state = {
    opacity: 0.75,
    inputIndex: 0,
    showInputs: false,
    layerRequest: 0,
    regionRequest: 0,
    catalog: null,
    regionId: null,
    region: null,
    leadIndex: 0,
    rasterLayer: null,
};

const elements = {
    aoiSelect: document.getElementById("aoi-select"),
    updateButton: document.getElementById("update-btn"),
    statusBox: document.getElementById("status-box"),
    statusText: document.getElementById("status-text"),
    loading: document.getElementById("loading"),
    loadingText: document.getElementById("loading-text"),
    observationDate: document.getElementById("observation-date"),
    generatedAt: document.getElementById("generated-at"),
    modelLabel: document.getElementById("model-label"),
};

const map = L.map("map", {
    zoomSnap: 0.25,
    zoomDelta: 0.25,
    wheelPxPerZoomLevel: 240,
}).setView([34.2, -91.5], 6);
const streets = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 18,
}).addTo(map);

const satellite = L.tileLayer("https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    attribution: 'Imagery © Esri, Vantor, Earthstar Geographics, and the GIS User Community',
    maxZoom: 18,
});
// Keep visual controls on the map, separate from the observation timeline.
const mapControls = L.control({ position: "topright" });
mapControls.onAdd = () => {
    const panel = L.DomUtil.create("div", "map-controls");
    panel.innerHTML = `<button class="map-controls-toggle" type="button" aria-label="Expand map settings" aria-expanded="false" aria-controls="map-settings" title="Map settings">&#9666;</button>
        <div id="map-settings" hidden><label for="basemap-select">Basemap</label>
        <select id="basemap-select" aria-label="Basemap">
            <option value="streets">Street map</option><option value="satellite">Satellite imagery</option>
        </select>
        <label for="opacity-slider">Layer opacity <output id="opacity-value">75%</output></label>
        <input id="opacity-slider" aria-label="Layer opacity" type="range" min="0" max="100" step="1" value="75">
        <div class="opacity-endpoints"><span>Hidden</span><span>Opaque</span></div></div>`;
    const toggle = panel.querySelector(".map-controls-toggle");
    toggle.addEventListener("click", () => {
        const expanded = toggle.getAttribute("aria-expanded") !== "true";
        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.setAttribute("aria-label", expanded ? "Collapse map settings" : "Expand map settings");
        toggle.innerHTML = expanded ? "&#9656;" : "&#9666;";
        panel.querySelector("#map-settings").hidden = !expanded;
        panel.classList.toggle("expanded", expanded);
    });
    L.DomEvent.disableClickPropagation(panel);
    L.DomEvent.disableScrollPropagation(panel);
    return panel;
};
mapControls.addTo(map);
const opacitySlider = document.getElementById("opacity-slider");
const inputSlider = document.getElementById("input-slider");
const inputToggle = document.getElementById("show-inputs");
function updateInputControls() {
    const inputs = state.region?.input_assets || [];
    inputToggle.disabled = !inputs.length;
    if (!inputs.length) state.showInputs = false;
    inputToggle.checked = state.showInputs;
    inputSlider.disabled = !inputs.length;
    inputSlider.max = Math.max(0, inputs.length - 1);
    inputSlider.value = state.inputIndex;
    document.getElementById("input-date").textContent = inputs[state.inputIndex]?.date || "Unavailable";
    document.getElementById("history-count").textContent = `${inputs.length} days`;
    document.getElementById("input-start").textContent = inputs[0]?.date || "—";
    document.getElementById("input-end").textContent = inputs.at(-1)?.date || "—";
    document.getElementById("input-position").textContent = inputs.length ? `Day ${state.inputIndex + 1} of ${inputs.length}` : "No observations";
    document.getElementById("input-prev").disabled = !inputs.length || state.inputIndex === 0;
    document.getElementById("input-next").disabled = !inputs.length || state.inputIndex >= inputs.length - 1;
    inputSlider.setAttribute("aria-valuetext", inputs.length ? `${inputs[state.inputIndex]?.date}, day ${state.inputIndex + 1} of ${inputs.length}` : "Unavailable");
    inputSlider.style.setProperty("--progress", `${inputs.length > 1 ? state.inputIndex / (inputs.length - 1) * 100 : 0}%`);
    document.getElementById("input-ticks").innerHTML = inputs.map((_, index) =>
        `<span class="${index === state.inputIndex ? "selected" : ""}" style="left:${inputs.length > 1 ? index / (inputs.length - 1) * 100 : 0}%">${index + 1}</span>`).join("");
    document.getElementById("input-help").textContent = inputs.length
        ? `Drag to show an input image; uncheck to return to the forecast.`
        : "Input images are not available for this publication.";
}
function applyOpacity() {
    state.opacity = Number(opacitySlider.value) / 100;
    document.getElementById("opacity-value").textContent = `${opacitySlider.value}%`;
    state.rasterLayer?.setOpacity(state.opacity);
}
opacitySlider.addEventListener("input", applyOpacity);
opacitySlider.addEventListener("change", applyOpacity);
document.getElementById("basemap-select").addEventListener("change", event => {
    map.removeLayer(streets);
    map.removeLayer(satellite);
    (event.target.value === "satellite" ? satellite : streets).addTo(map);
});
inputToggle.addEventListener("change", () => {
    state.showInputs = inputToggle.checked;
    updateInputControls();
    loadForecastLayers();
});
inputSlider.addEventListener("input", () => {
    state.inputIndex = Number(inputSlider.value);
    state.showInputs = true;
    updateInputControls();
    loadForecastLayers();
});

for (const [id, direction] of [["input-prev", -1], ["input-next", 1]]) {
    document.getElementById(id).addEventListener("click", () => {
        const count = state.region?.input_assets?.length || 0;
        if (!count) return;
        state.inputIndex = Math.max(0, Math.min(count - 1, state.inputIndex + direction));
        state.showInputs = true;
        updateInputControls();
        loadForecastLayers();
    });
}

function cacheBusted(path) {
    const separator = path.includes("?") ? "&" : "?";
    return `${path}${separator}v=${Date.now()}`;
}

async function fetchJson(path) {
    const response = await fetch(cacheBusted(path), { cache: "no-store" });
    if (!response.ok) {
        throw new Error(`${path}: HTTP ${response.status}`);
    }
    return response.json();
}

function showLoading(message) {
    elements.loadingText.textContent = message;
    elements.loading.classList.add("show");
}

function hideLoading() {
    elements.loading.classList.remove("show");
}

function showStatus(message, type = "info") {
    elements.statusBox.className = `status ${type}`;
    elements.statusText.textContent = message;
}

function clearForecastLayers() {
    if (state.rasterLayer) {
        map.removeLayer(state.rasterLayer);
        state.rasterLayer = null;
    }

}

// Use the same 256-color jet lookup table as the published raster.
const legend = L.control({ position: "bottomright" });
legend.onAdd = () => {
    const panel = L.DomUtil.create("div", "forecast-legend");
    panel.setAttribute("role", "img");
    panel.setAttribute("aria-label", "Water fraction color scale: 0 to 100 percent, dark blue through cyan, yellow and red");
    panel.innerHTML = `<div class="legend-title">Water fraction (%)</div>
        <div class="legend-scale"><canvas width="1" height="256" aria-hidden="true"></canvas>
        <div class="legend-ticks">${[100, 80, 60, 40, 20, 0].map(value =>
            `<span style="top:${100 - value}%">${value}</span>`).join("")}</div></div>`;
    const context = panel.querySelector("canvas").getContext("2d");
    WATER_COLORS.forEach((color, index) => {
        context.fillStyle = color;
        context.fillRect(0, 255 - index, 1, 1);
    });
    L.DomEvent.disableClickPropagation(panel);
    L.DomEvent.disableScrollPropagation(panel);
    return panel;
};
legend.addTo(map);

function updateDateButtons() {
    document.querySelectorAll("#date-selector .date-btn").forEach((button, index) => {
        const asset = state.region?.assets?.[index];
        button.textContent = asset ? asset.date : `Day +${index + 1}`;
        button.disabled = !asset;
        button.classList.toggle("active", index === state.leadIndex);
    });
}

function updateMetadata() {
    elements.observationDate.textContent = state.region.latest_observation_date;
    elements.generatedAt.textContent = new Date(state.region.generated_at).toLocaleString();
    elements.modelLabel.textContent =
        `${state.region.model.history_days}-day history → ` +
        `${state.region.model.forecast_days}-day forecast`;
}

async function loadForecastLayers() {
    if (!state.region) return;
    const region = state.region;
    const isInput = state.showInputs;
    const asset = isInput ? region.input_assets?.[state.inputIndex] : region.assets[state.leadIndex];
    if (!asset) return;
    const request = ++state.layerRequest;
    const label = `${asset.date} ${isInput ? "input observation" : "forecast"}`;
    showLoading(`Loading ${label}…`);
    clearForecastLayers();
    try {
        {
            const layer = L.imageOverlay(cacheBusted(asset.raster), region.bounds,
                { opacity: state.opacity, interactive: false });
            state.rasterLayer = layer;
            await new Promise((resolve, reject) => {
                layer.once("load", resolve);
                layer.once("error", () => reject(new Error("Image could not be loaded")));
                layer.addTo(map);
            });
            if (request !== state.layerRequest) return;
        }
        if (request === state.layerRequest) showStatus(`Showing ${label}`, "success");
    } catch (error) {
        if (request !== state.layerRequest) return;
        clearForecastLayers();
        showStatus(`Could not load ${label}: ${error.message}`, "error");
    } finally {
        if (request === state.layerRequest) hideLoading();
    }
}

async function selectRegion(regionId) {
    const request = ++state.regionRequest;
    ++state.layerRequest;
    state.region = null;
    updateInputControls();
    state.regionId = regionId;
    state.leadIndex = 0;
    const catalogRegion = state.catalog.regions[regionId];
    showLoading(`Loading ${catalogRegion.name}…`);
    clearForecastLayers();
    try {
        const region = await fetchJson(catalogRegion.latest);
        if (request !== state.regionRequest) return;
        state.region = region;
        state.inputIndex = Math.max(0, (region.input_assets?.length || 0) - 1);
        updateInputControls();
        map.fitBounds(state.region.bounds, { padding: [12, 12] });
        updateDateButtons();
        updateMetadata();
        await loadForecastLayers();
    } catch (error) {
        if (request !== state.regionRequest) return;
        state.region = null;
        updateInputControls();
        showStatus(`Forecast is not available yet: ${error.message}`, "warning");
        hideLoading();
    }
}

async function initialize() {
    showLoading("Reading the latest forecast catalog…");
    try {
        state.catalog = await fetchJson("data/catalog.json");
        const entries = Object.entries(state.catalog.regions);
        if (!entries.length) throw new Error("The forecast catalog is empty");

        elements.aoiSelect.replaceChildren();
        entries.forEach(([regionId, region]) => {
            const option = document.createElement("option");
            option.value = regionId;
            option.textContent = region.name;
            elements.aoiSelect.appendChild(option);
        });
        await selectRegion(entries[0][0]);
    } catch (error) {
        showStatus(
            `No published forecast yet. Run the GitHub Action once: ${error.message}`,
            "warning"
        );
        hideLoading();
    }
}

elements.aoiSelect.addEventListener("change", (event) => selectRegion(event.target.value));

document.querySelectorAll("#date-selector .date-btn").forEach((button) => {
    button.addEventListener("click", () => {
        state.showInputs = false;
        updateInputControls();
        state.leadIndex = Number(button.dataset.index);
        updateDateButtons();
        loadForecastLayers();
    });
});

elements.updateButton.addEventListener("click", async () => {
    elements.updateButton.disabled = true;
    try {
        await initialize();
    } finally {
        elements.updateButton.disabled = false;
    }
});

initialize();
