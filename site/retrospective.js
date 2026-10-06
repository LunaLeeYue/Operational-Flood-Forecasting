"use strict";
(() => {
    const el = id => document.getElementById(id);
    const retro = {map: null, runs: [], allRuns: [], metadata: null, lead: 1, asset: null, target: null, view: 'curtain', hasObservation: false, observation: false, layers: [], request: 0, active: false};
    function clipLayers() {
        if (retro.layers.length !== 2) return;
        const split = Number(el('curtain-slider').value);
        el('curtain-line').style.left = `${split}%`;
        const bounds = el('retro-map').getBoundingClientRect();
        const seam = bounds.left + bounds.width * split / 100;
        retro.layers.forEach((layer, index) => {
            const image = layer.getElement();
            if (!image) return;
            const rect = image.getBoundingClientRect();
            const percent = Math.max(0, Math.min(100, (seam - rect.left) / rect.width * 100));
            image.style.clipPath = retro.view === 'curtain'
                ? (index === 0 ? `inset(0 ${100-percent}% 0 0)` : `inset(0 0 0 ${percent}%)`)
                : 'none';
            image.style.visibility = retro.view === 'curtain' || index === Number(retro.observation) ? 'visible' : 'hidden';
        });
    }
    function clear() {
        retro.layers.forEach(layer => retro.map.removeLayer(layer));
        retro.layers = [];
        el('curtain-ui').hidden = true;
    }
    function status(message, type='info') {
        el('retro-status').className = `status ${type}`;
        el('retro-status').textContent = message;
    }
    function updateView() {
        el('curtain-mode').classList.toggle('active', retro.view === 'curtain');
        el('toggle-mode').classList.toggle('active', retro.view === 'toggle');
        el('curtain-mode').setAttribute('aria-pressed', String(retro.view === 'curtain'));
        el('toggle-mode').setAttribute('aria-pressed', String(retro.view === 'toggle'));
        el('retro-toggle').hidden = retro.view !== 'toggle' || !retro.hasObservation;
        el('curtain-mode').disabled = !retro.hasObservation;
        el('toggle-mode').disabled = !retro.hasObservation;
        el('retro-toggle').textContent = retro.observation ? 'Show forecast' : 'Show observation';
        el('curtain-ui').hidden = retro.view !== 'curtain' || retro.layers.length !== 2;
        const asset = retro.asset;
        el('retro-map-label').textContent = !retro.hasObservation && asset ? `${asset.date} · Forecast (observation pending)` : asset ? `${asset.date} · ${asset.lead_day}-day lead · ${retro.view === 'curtain' ? 'Forecast | Observation' : (retro.observation ? 'NOAA observation' : 'Retrospective forecast')}` : '';
        clipLayers();
    }
    async function showLead() {
        const request = ++retro.request;
        clear(); retro.metadata=null; retro.asset=null; retro.hasObservation=false;
        el('retro-window').textContent=''; el('retro-provenance').textContent=''; updateView();
        el('retro-leads').querySelectorAll('button').forEach(button => button.classList.toggle('active', Number(button.dataset.lead) === retro.lead));
        const entry = retro.target?.leads[String(retro.lead)];
        if (!entry) {status('This lead time is not available for the selected target date.', 'warning'); return;}
        status(`Loading ${retro.lead}-day lead forecast for ${retro.target.date}…`);
        try {
            const response = await fetch(entry.metadata);
            if (!response.ok) throw new Error('Could not load this historical forecast.');
            const metadata = await response.json();
            if (request !== retro.request) return;
            const asset = metadata.assets.find(item => item.date === retro.target.date && item.lead_day === retro.lead);
            if (!asset?.observation) throw new Error('Matched forecast and observation are unavailable.');
            retro.metadata=metadata; retro.asset=asset; retro.hasObservation=true;
            el('retro-provenance').textContent=metadata.provenance === 'operational_archive'
                ? `Original operational forecast saved at ${metadata.generated_at}.`
                : 'Retrospective reconstruction from archived inputs; original issued output was not retained.';
            el('retro-window').textContent=`Target: ${asset.date} · ${asset.lead_day}-day lead. ${metadata.model.history_days}-day input: ${metadata.input_dates[0]} – ${metadata.latest_observation_date}.`;
            if (retro.needsFit) {retro.map.stop(); retro.map.fitBounds(metadata.bounds,{padding:[15,15],animate:false}); retro.needsFit=false;}
            const images = [asset.raster, asset.observation].map(url => {
                const layer = L.imageOverlay(url, metadata.bounds, {opacity: 0.75, interactive: false});
                retro.layers.push(layer);
                return new Promise((resolve,reject) => {
                    layer.once('load', resolve);
                    layer.once('error', () => reject(new Error('Comparison image is unavailable.')));
                    layer.addTo(retro.map);
                });
            });
            updateView();
            await Promise.all(images);
            if (request !== retro.request) return;
            updateView();
            status(`Comparing ${asset.date}: ${asset.lead_day}-day lead forecast and same-day NOAA observation.`, 'success');
        } catch (error) {
            if (request !== retro.request) return;
            clear(); retro.asset=null; retro.hasObservation=false; updateView(); status(error.message, 'warning');
        }
    }
    function updateDateNavigation() {
        const chosen=el('retro-date').value;
        el('retro-prev').disabled=!retro.runs.some(target=>target.date<chosen);
        el('retro-next').disabled=!retro.runs.some(target=>target.date>chosen);
    }
    function stepDate(direction) {
        const chosen=el('retro-date').value;
        const target=direction<0 ? retro.runs.filter(item=>item.date<chosen).at(-1) : retro.runs.find(item=>item.date>chosen);
        if (target) {el('retro-date').value=target.date; selectDate();}
    }
    async function selectDate() {
        updateDateNavigation();
        ++retro.request; clear(); retro.metadata=null; retro.asset=null; retro.hasObservation=false;
        el('retro-leads').replaceChildren(); el('retro-window').textContent=''; el('retro-provenance').textContent=''; updateView();
        retro.needsFit=true;
        retro.target=retro.runs.find(target => target.date === el('retro-date').value);
        if (!retro.target) {status('No observed comparison is available for this target date.', 'warning'); return;}
        if (!retro.target.leads[String(retro.lead)]) retro.lead=Number(Object.keys(retro.target.leads)[0]);
        [1,2,3].forEach(lead => {
            const button=document.createElement('button'); button.className='date-btn';
            button.textContent=`${lead}-day`; button.dataset.lead=lead;
            button.disabled=!retro.target.leads[String(lead)];
            button.addEventListener('click',()=>{retro.lead=lead;showLead();});
            el('retro-leads').appendChild(button);
        });
        await showLead();
    }
    async function selectRegion() {
        const available=retro.allRuns.filter(run=>(run.region_id || 'wlc')===el('retro-region').value);
        retro.runs=available.sort((a,b)=>a.date.localeCompare(b.date));
        el('retro-provenance').textContent='';
        if (!retro.runs.length) {
            ++retro.request; clear(); retro.metadata=null; retro.asset=null; retro.hasObservation=false;
            el('retro-leads').replaceChildren(); el('retro-window').textContent='';
            el('retro-available').textContent='No archived dates yet.';
            el('retro-date').disabled=true; updateDateNavigation(); updateView();
            status('No precomputed dates yet for this region.','info'); return;
        }
        el('retro-date').disabled=false;
        el('retro-date').min=retro.runs[0].date;
        el('retro-date').max=retro.runs.at(-1).date;
        if (!retro.runs.some(run=>run.date===el('retro-date').value)) el('retro-date').value=retro.runs.at(-1).date;
        el('retro-available').textContent='Historical forecasts are available from September 2026.';
        await selectDate();
    }
    async function initRetro() {
        if (retro.map) {retro.map.invalidateSize(); return;}
        retro.map = L.map('retro-map', {zoomSnap:0.25,zoomDelta:0.25,wheelPxPerZoomLevel:240}).setView([30.2,-92.85],8);
        const road=L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:18,attribution:'© OpenStreetMap contributors'}).addTo(retro.map);
        const satellite=L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',{maxZoom:18,attribution:'Imagery © Esri, Vantor, Earthstar Geographics, GIS User Community'});
        L.control.layers({'Street map':road,'Satellite':satellite},null,{position:'topright'}).addTo(retro.map);
        const legendControl=L.control({position:'bottomright'});
        legendControl.onAdd=()=>{
            const panel=L.DomUtil.create('div','retro-legend');
            panel.innerHTML='<strong>Water fraction (%)</strong><div></div><span>0</span><span>100</span>';
            panel.querySelector('div').style.background=`linear-gradient(to right, ${WATER_COLORS.join(',')})`;
            return panel;
        };legendControl.addTo(retro.map);
        retro.map.on('move zoom resize viewreset',clipLayers);
        // Update clipping throughout Leaflet's CSS zoom animation.
        let animateUntil=0;
        const animate=()=>{clipLayers();if(performance.now()<animateUntil)requestAnimationFrame(animate);};
        retro.map.on('zoomanim',()=>{animateUntil=performance.now()+350;requestAnimationFrame(animate);});
        try {
            const response=await fetch('validation/catalog.json');
            if(!response.ok)throw new Error('Retrospective catalog unavailable.');
            retro.allRuns=(await response.json()).targets || [];
            await selectRegion();
        }catch(error){status(error.message,'warning');}
    }
    function switchMode(historical) {
        retro.active=historical;
        el('nrt-sidebar').hidden=historical; el('map').hidden=historical;
        el('retro-sidebar').hidden=!historical; el('retro-map-shell').hidden=!historical;
        el('container').classList.toggle('retrospective-active',historical);
        el('nrt-mode').classList.toggle('active',!historical);el('retro-mode').classList.toggle('active',historical);
        el('nrt-mode').setAttribute('aria-pressed',String(!historical));el('retro-mode').setAttribute('aria-pressed',String(historical));
        if(historical)initRetro();else window.dispatchEvent(new Event('nrt-visible'));
    }
    el('nrt-mode').addEventListener('click',()=>switchMode(false));
    el('retro-mode').addEventListener('click',()=>switchMode(true));
    el('retro-region').addEventListener('change',selectRegion);
    el('retro-prev').addEventListener('click',()=>stepDate(-1));
    el('retro-next').addEventListener('click',()=>stepDate(1));
    el('retro-date').addEventListener('change',selectDate);
    el('curtain-slider').addEventListener('input',clipLayers);
    el('curtain-mode').addEventListener('click',()=>{retro.view='curtain';updateView();});
    el('toggle-mode').addEventListener('click',()=>{retro.view='toggle';updateView();});
    el('retro-toggle').addEventListener('click',()=>{retro.observation=!retro.observation;updateView();});
})();
