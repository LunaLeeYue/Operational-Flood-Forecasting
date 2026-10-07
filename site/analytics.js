"use strict";
(() => {
    // Public Web Analytics site token, not a Cloudflare account/API credential.
    // Leave empty until the owner supplies the snippet from their dashboard.
    const token = 'c5d0c955a613411382268bfeb297d586';
    if (!/^[a-f0-9]{32}$/i.test(token)) return;
    if (location.hostname !== 'lunaleeyue.github.io') return;
    const script = document.createElement('script');
    script.type = 'module';
    script.src = 'https://static.cloudflareinsights.com/beacon.min.js';
    script.setAttribute('data-cf-beacon', JSON.stringify({token}));
    document.body.appendChild(script);
})();
