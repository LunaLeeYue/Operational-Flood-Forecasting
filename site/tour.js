"use strict";
(() => {
    const el = id => document.getElementById(id);
    const dialog = el('quick-tour');
    const preference = 'flood-viewer-hide-tour-v1';
    const seen = 'flood-viewer-tour-seen-v1';
    const read = (storage, key) => {try {return window[storage].getItem(key) === 'true';} catch {return false;}};
    const write = (storage, key, value) => {try {window[storage].setItem(key, String(value));} catch { /* The tour still works without browser storage. */ }};
    const steps = [
        {title: 'Two ways to explore', text: 'Use NRT Forecast for the latest 3-day outlook. Retrospective lets you compare historical forecasts with observations.', mode: 'nrt', target: '.mode-switch'},
        {title: 'Choose your region', text: 'Select UMAP or WLC. The map and available data update for the selected region.', mode: 'nrt', target: '#aoi-select'},
        {title: 'Explore the latest forecast', text: 'Choose a forecast date. Below it, Input observations lets you browse the images used by the model. Expand the small arrow on the map to change the basemap or layer opacity.', mode: 'nrt', target: '#date-selector'},
        {title: 'Pick a historical target date', text: 'Choose a date with the calendar, or use the arrows to move between available dates. The date is the day being forecast and observed.', mode: 'retro', target: '.retro-date-navigation'},
        {title: 'Compare lead times and layers', text: '1-day, 2-day and 3-day show forecasts for the same target date using different input cutoffs. Drag the Curtain divider, or use Toggle to switch between forecast and observation.', mode: 'retro', target: '#retro-leads'},
        {title: 'Read the verification results', text: 'MAE and RMSE appear above the map; lower values mean smaller errors. Valid pixel number shows how many paired pixels were used. Clouds and invalid pixels are excluded. You can reopen this guide with Quick tour.', mode: 'retro', target: '#retro-metrics'},
    ];
    let index = 0, previousMode = 'nrt', previousFocus;
    function positionHighlight() {
        if (!dialog.open) return;
        const target = document.querySelector(steps[index].target);
        const highlight = el('tour-highlight');
        if (!target || !target.getClientRects().length) {
            highlight.hidden = true;
            dialog.removeAttribute('data-side');
            dialog.style.left = `${Math.max(12,(window.innerWidth-dialog.offsetWidth)/2)}px`;
            dialog.style.top = `${Math.max(12,(window.innerHeight-dialog.offsetHeight)/2)}px`;
            return;
        }
        const rect = target.getBoundingClientRect();
        const container = target.closest('#sidebar');
        const bounds = container ? container.getBoundingClientRect() : {top:0,bottom:window.innerHeight};
        const top = Math.max(rect.top, bounds.top), bottom = Math.min(rect.bottom, bounds.bottom);
        highlight.hidden = bottom <= top;
        Object.assign(highlight.style, {left:`${Math.max(2,rect.left-5)}px`,top:`${Math.max(2,top-5)}px`,width:`${Math.min(rect.width+10,window.innerWidth-4)}px`,height:`${bottom-top+10}px`});
        const pad = 12, gap = 18, width = dialog.offsetWidth, height = dialog.offsetHeight;
        const viewportWidth = window.innerWidth, viewportHeight = window.innerHeight;
        const clamp = (value, min, max) => Math.max(min, Math.min(value, Math.max(min,max)));
        const centerX = rect.left + rect.width/2, centerY = (top+bottom)/2;
        const candidates = [
            {side:'right', x:rect.right+gap, y:clamp(top,pad,viewportHeight-height-pad)},
            {side:'bottom', x:clamp(centerX-width/2,pad,viewportWidth-width-pad), y:bottom+gap},
            {side:'left', x:rect.left-gap-width, y:clamp(top,pad,viewportHeight-height-pad)},
            {side:'top', x:clamp(centerX-width/2,pad,viewportWidth-width-pad), y:top-gap-height},
        ];
        let placement = candidates.find(p => p.x>=pad && p.y>=pad && p.x+width<=viewportWidth-pad && p.y+height<=viewportHeight-pad);
        if (!placement) {
            // On short screens use the side with most room and keep navigation reachable.
            placement = bottom < viewportHeight-top ? candidates[1] : candidates[3];
            placement = {...placement, x:clamp(placement.x,pad,viewportWidth-width-pad), y:clamp(placement.y,pad,viewportHeight-height-pad)};
        }
        dialog.dataset.side = placement.side;
        dialog.style.left = `${placement.x}px`;
        dialog.style.top = `${placement.y}px`;
        const arrow = placement.side==='right' || placement.side==='left'
            ? clamp(centerY-placement.y,20,height-20) : clamp(centerX-placement.x,20,width-20);
        dialog.style.setProperty('--tour-arrow',`${arrow}px`);
    }
    function render() {
        const step = steps[index];
        el(`${step.mode}-mode`).click();
        el('tour-count').textContent = `STEP ${index+1} OF ${steps.length}`;
        el('tour-title').textContent = step.title;
        el('tour-description').textContent = step.text;
        el('tour-back').disabled = index === 0;
        el('tour-next').textContent = index === steps.length-1 ? 'Finish' : 'Next';
        const target = document.querySelector(step.target);
        if (target?.closest('#sidebar')) target.scrollIntoView({block:'nearest'});
        positionHighlight();
        el('tour-next').focus({preventScroll:true});
    }
    function open() {
        if (dialog.open) return;
        previousMode = el('retro-mode').getAttribute('aria-pressed') === 'true' ? 'retro' : 'nrt';
        previousFocus = document.activeElement;
        index = 0;
        el('tour-dismiss').checked = read('localStorage', preference);
        dialog.showModal(); render();
        write('sessionStorage', seen, true);
    }
    el('tour-launch').addEventListener('click', open);
    el('tour-back').addEventListener('click', () => {if(index>0){index--;render();}});
    el('tour-next').addEventListener('click', () => {if(index<steps.length-1){index++;render();}else dialog.close();});
    el('tour-skip').addEventListener('click', () => dialog.close());
    el('tour-dismiss').addEventListener('change', event => write('localStorage', preference, event.target.checked));
    dialog.addEventListener('close', () => {
        el('tour-highlight').hidden = true;
        el(`${previousMode}-mode`).click();
        previousFocus?.focus({preventScroll:true});
    });
    window.addEventListener('resize', positionHighlight);
    el('sidebar').addEventListener('scroll', positionHighlight);
    const metricsObserver = new MutationObserver(positionHighlight);
    metricsObserver.observe(el('retro-metrics'), {attributes:true,attributeFilter:['hidden']});
    function autoStart() {
        if (read('localStorage', preference) || read('sessionStorage', seen)) return;
        const loading = el('loading');
        if (!loading.classList.contains('show')) {open();return;}
        const observer = new MutationObserver(() => {
            if (!loading.classList.contains('show')) {observer.disconnect(); if(!read('sessionStorage',seen)) open();}
        });
        observer.observe(loading, {attributes:true,attributeFilter:['class']});
    }
    autoStart();
})();
