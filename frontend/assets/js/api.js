/**
 * api.js
 * UrbanAI 3D Istanbul FastAPI Integration Methods
 */
'use strict';

async function apiFetch(endpoint) {
  const url = API_BASE_URL + endpoint;
  const res = await fetch(url);
  if (!res.ok) {
    let body = '';
    try { body = await res.text(); } catch (_) {}
    const err = new Error('HTTP ' + res.status + ' ' + res.statusText);
    err.url = url;
    err.status = res.status;
    err.body = body;
    throw err;
  }
  return res.json();
}

const API = {
  getOzet: () => apiFetch('/api/ozet'),
  getOncelikliIlceler: (limit = 10) => apiFetch('/api/oncelikli-ilceler?limit=' + limit),
  getIlceler: () => apiFetch('/api/ilceler'),
  getIlce: (ilceAd) => apiFetch('/api/ilceler/' + encodeURIComponent(ilceAd)),
  getKutuphaneler: (ilce = '', limit = 100) => {
    let ep = '/api/kutuphaneler?limit=' + limit;
    if (ilce) ep += '&ilce=' + encodeURIComponent(ilce);
    return apiFetch(ep);
  },
  getAdayBolgeler: (ilce = '', geometri = false) => {
    let ep = '/api/aday-bolgeler';
    const params = [];
    if (ilce) params.push('ilce=' + encodeURIComponent(ilce));
    if (geometri) params.push('geometri=true');
    if (params.length) ep += '?' + params.join('&');
    return apiFetch(ep);
  },
  getUyduIlceler: () => apiFetch('/api/uydu-ilceler'),
  getUyduGoruntuleri: (ilce = '') => {
    let ep = '/api/uydu-goruntuleri';
    if (ilce) ep += '?ilce=' + encodeURIComponent(ilce);
    return apiFetch(ep);
  },
  getUyduGoruntusu: (patchId) => apiFetch('/api/uydu-goruntuleri/' + encodeURIComponent(patchId)),
};
