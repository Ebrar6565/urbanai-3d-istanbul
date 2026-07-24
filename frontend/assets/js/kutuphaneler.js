/**
 * kutuphaneler.js
 * UrbanAI 3D İstanbul — Kütüphaneler Page Logic
 */
'use strict';

let map = null;
let markersLayer = null;
let markerMap = {}; // lib.id -> L.circleMarker
let allLibraries = [];
let selectedLibId = null;

function initKutuphaneMap() {
  const mapEl = document.getElementById('kutuphane-map');
  if (!mapEl) return false;

  if (typeof window.L === 'undefined') {
    console.warn('[Kutuphaneler] Leaflet (window.L) is not defined.');
    mapEl.innerHTML = '<div class="state-msg error" style="position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: var(--surface-container-low);">Harita kütüphanesi (Leaflet) yüklenemedi.</div>';
    return false;
  }

  try {
    map = L.map('kutuphane-map', {
      center: [41.01, 28.98],
      zoom: 11,
      zoomControl: false,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap contributors © CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map);

    L.control.zoom({ position: 'bottomleft' }).addTo(map);

    markersLayer = L.layerGroup().addTo(map);
    return true;
  } catch (err) {
    console.error('[Kutuphaneler] Map init error:', err);
    mapEl.innerHTML = '<div class="state-msg error" style="position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: var(--surface-container-low);">Harita başlatılamadı.</div>';
    return false;
  }
}

async function loadKutuphanelerData() {
  initKutuphaneMap();

  try {
    const [ozet, libData, ilcelerData] = await Promise.all([
      API.getOzet(),
      API.getKutuphaneler('', 100),
      API.getIlceler(),
    ]);

    updateTopBarInfo(ozet.analiz_yili || 2025, 'Güncel');

    allLibraries = libData.kutuphaneler || [];

    // Populate district filter dropdown
    const selectEl = document.getElementById('lib-district-select');
    if (selectEl && ilcelerData.ilceler) {
      selectEl.innerHTML = '<option value="">Tüm İlçeler</option>' +
        ilcelerData.ilceler.map(ilce => `<option value="${esc(ilce)}">${esc(ilce)}</option>`).join('');
    }

    renderLibraries(allLibraries);
    bindFilterEvents();

  } catch (err) {
    const errorObj = {
      page: 'kutuphaneler.html',
      url: err.url || (API_BASE_URL + '/api/kutuphaneler?limit=100'),
      status: err.status || 0,
      responseBody: err.body || '',
      message: err.message,
      stack: err.stack
    };
    console.error('[Kutuphaneler] Error:', errorObj);

    const countBadge = document.getElementById('lib-count-badge');
    const listBody = document.getElementById('lib-list-body');

    if (countBadge) countBadge.textContent = 'HATA';
    if (listBody) {
      listBody.innerHTML = '<div class="state-msg error">API verileri yüklenemedi.<br>URL: ' + esc(errorObj.url) + '<br>Hata: ' + esc(err.message) + '</div>';
    }
  }
}

function bindFilterEvents() {
  const searchInput = document.getElementById('lib-search-input');
  const districtSelect = document.getElementById('lib-district-select');

  const filterAction = () => {
    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';
    const district = districtSelect ? districtSelect.value : '';

    let filtered = allLibraries;

    if (district) {
      filtered = filtered.filter(lib => lib.ilce === district);
    }

    if (query) {
      filtered = filtered.filter(lib =>
        (lib.kutuphane_adi && lib.kutuphane_adi.toLowerCase().includes(query)) ||
        (lib.adres && lib.adres.toLowerCase().includes(query)) ||
        (lib.ilce && lib.ilce.toLowerCase().includes(query))
      );
    }

    renderLibraries(filtered);
  };

  if (searchInput) searchInput.addEventListener('input', filterAction);
  if (districtSelect) districtSelect.addEventListener('change', filterAction);
}

function renderLibraries(list) {
  const countBadge = document.getElementById('lib-count-badge');
  const listBody = document.getElementById('lib-list-body');

  if (countBadge) {
    countBadge.textContent = list.length + ' KAYIT';
  }

  if (!listBody) return;

  // Clear map markers
  if (markersLayer) {
    markersLayer.clearLayers();
  }
  markerMap = {};

  if (list.length === 0) {
    listBody.innerHTML = '<div class="state-msg">Seçilen filtre kriterlerine uygun kütüphane bulunamadı.</div>';
    return;
  }

  const bounds = [];

  // Render list items & markers
  const listHtml = list.map(lib => {
    const isSelected = lib.id === selectedLibId;
    const hasCoords = typeof lib.enlem === 'number' && typeof lib.boylam === 'number' && !isNaN(lib.enlem) && !isNaN(lib.boylam);

    if (hasCoords && markersLayer && typeof window.L !== 'undefined' && map) {
      const marker = L.circleMarker([lib.enlem, lib.boylam], {
        radius: isSelected ? 8 : 6,
        fillColor: isSelected ? '#d00000' : '#256489',
        color: '#ffffff',
        weight: isSelected ? 3 : 1.5,
        fillOpacity: 0.85,
      });

      marker.bindPopup(`
        <div style="font-family: var(--font-sans); padding: 4px;">
          <strong style="font-size: 13px; color: var(--primary);">${esc(lib.kutuphane_adi)}</strong>
          <div style="font-size: 11px; color: var(--on-surface-variant); margin-top: 4px;">📍 ${esc(lib.adres || lib.ilce)}</div>
          <div style="font-size: 11px; color: var(--secondary); margin-top: 2px;">Saatler: ${esc(lib.calisma_saatleri || '09:00-18:00')} (${esc(lib.calisma_gunleri || 'Hergün')})</div>
        </div>
      `);

      marker.on('click', () => selectLibrary(lib.id, false));
      markersLayer.addLayer(marker);
      markerMap[lib.id] = marker;

      bounds.push([lib.enlem, lib.boylam]);
    }

    return `
      <div class="lib-card-item ${isSelected ? 'selected' : ''}" data-id="${lib.id}" style="padding: 16px; border-bottom: 1px solid var(--border-gray); cursor: pointer; transition: background 120ms; ${isSelected ? 'background: var(--surface-container-low); border-left: 4px solid var(--secondary);' : ''}" onclick="selectLibrary(${lib.id}, true)">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 4px;">
          <h4 style="font-size: 14px; font-weight: 700; color: var(--primary); margin: 0;">${esc(lib.kutuphane_adi)}</h4>
          <span class="badge ${hasCoords ? 'badge-low' : 'badge-medium'}" style="font-size: 9px;">${hasCoords ? 'DOĞRULANMIŞ' : 'İlçe Merkezi'}</span>
        </div>
        <div style="font-size: 12px; color: var(--on-surface-variant); margin-bottom: 8px; display: flex; align-items: center; gap: 4px;">
          <span class="material-symbols-outlined" style="font-size: 14px;">location_on</span>
          <span>${esc(lib.ilce)} — ${esc(lib.adres || 'Adres bilgisi mevcut')}</span>
        </div>
        <div style="font-size: 11px; color: var(--on-surface-variant); display: flex; justify-content: space-between; background: var(--surface-container-low); padding: 6px 8px; border-radius: 4px;">
          <span>Çalışma Günleri: <strong>${esc(lib.calisma_gunleri || 'Hergün')}</strong></span>
          <span>Saatler: <strong>${esc(lib.calisma_saatleri || '09:00-18:00')}</strong></span>
        </div>
      </div>
    `;
  }).join('');

  listBody.innerHTML = listHtml;

  if (bounds.length > 0 && map && typeof window.L !== 'undefined') {
    try {
      map.fitBounds(bounds, { padding: [40, 40] });
    } catch (_) {}
  }
}

function selectLibrary(id, panMap = true) {
  selectedLibId = id;
  const lib = allLibraries.find(x => x.id === id);
  if (!lib) return;

  // Highlight list item
  document.querySelectorAll('.lib-card-item').forEach(el => {
    const isThis = String(el.dataset.id) === String(id);
    el.classList.toggle('selected', isThis);
    el.style.background = isThis ? 'var(--surface-container-low)' : '';
    el.style.borderLeft = isThis ? '4px solid var(--secondary)' : '';
    if (isThis) el.scrollIntoView({ block: 'nearest' });
  });

  // Highlight marker
  Object.entries(markerMap).forEach(([mId, marker]) => {
    const isThis = String(mId) === String(id);
    marker.setStyle({
      fillColor: isThis ? '#d00000' : '#256489',
      radius: isThis ? 9 : 6,
      weight: isThis ? 3 : 1.5,
    });
    if (isThis && !marker.isPopupOpen()) {
      marker.openPopup();
    }
  });

  // Pan map if coordinates exist
  if (panMap && lib.enlem && lib.boylam && map) {
    map.panTo([lib.enlem, lib.boylam], { animate: true });
  }
}

document.addEventListener('DOMContentLoaded', loadKutuphanelerData);
