"use strict";

const state = {
    catalog: null,
    regionId: null,
    region: null,
    leadIndex: 0,
    displayMode: "raster",
    rasterLayer: null,
    pointLayer: null,
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

const map = L.map("map").setView([34.2, -91.5], 6);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap contributors",
    maxZoom: 18,
}).addTo(map);

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
    if (state.pointLayer) {
        map.removeLayer(state.pointLayer);
        state.pointLayer = null;
    }
}

function colorForValue(value) {
    if (value < 0.3) return "#0000ff";
    if (value < 0.5) return "#00ffff";
    if (value < 0.7) return "#ffff00";
    if (value < 0.9) return "#ff7f00";
    return "#ff0000";
}

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
    const asset = state.region.assets[state.leadIndex];
    if (!asset) return;

    showLoading(`Loading forecast for ${asset.date}…`);
    clearForecastLayers();
    try {
        if (state.displayMode === "raster" || state.displayMode === "both") {
            state.rasterLayer = L.imageOverlay(
                cacheBusted(asset.raster),
                state.region.bounds,
                { opacity: 0.72, interactive: false }
            ).addTo(map);
        }

        if (state.displayMode === "points" || state.displayMode === "both") {
            const geojson = await fetchJson(asset.points);
            state.pointLayer = L.geoJSON(geojson, {
                pointToLayer: (feature, latlng) => L.circleMarker(latlng, {
                    radius: 5,
                    fillColor: colorForValue(feature.properties.water_fraction),
                    color: "#202020",
                    weight: 1,
                    opacity: 0.85,
                    fillOpacity: 0.8,
                }),
                onEachFeature: (feature, layer) => {
                    const value = (feature.properties.water_fraction * 100).toFixed(1);
                    layer.bindPopup(
                        `<strong>Water Fraction:</strong> ${value}%<br>` +
                        `<strong>Level:</strong> ${feature.properties.flood_level}`
                    );
                },
            }).addTo(map);
        }
        showStatus(`Showing ${asset.date} forecast (${state.displayMode})`, "success");
    } catch (error) {
        clearForecastLayers();
        showStatus(`Could not load forecast: ${error.message}`, "error");
    } finally {
        hideLoading();
    }
}

async function selectRegion(regionId) {
    state.regionId = regionId;
    state.leadIndex = 0;
    const catalogRegion = state.catalog.regions[regionId];
    showLoading(`Loading ${catalogRegion.name}…`);
    clearForecastLayers();
    try {
        state.region = await fetchJson(catalogRegion.latest);
        map.fitBounds(state.region.bounds, { padding: [12, 12] });
        updateDateButtons();
        updateMetadata();
        await loadForecastLayers();
    } catch (error) {
        state.region = null;
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
        state.leadIndex = Number(button.dataset.index);
        updateDateButtons();
        loadForecastLayers();
    });
});

document.querySelectorAll(".mode-btn").forEach((button) => {
    button.addEventListener("click", () => {
        state.displayMode = button.dataset.mode;
        document.querySelectorAll(".mode-btn").forEach((candidate) => {
            candidate.classList.toggle("active", candidate === button);
        });
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
