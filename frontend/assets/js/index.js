/**
 * index.js
 * Genel Bakış Page Script
 */
'use strict';

let map = null;

function initIndexMap() {
  const mapEl = document.getElementById('index-map');
  if (!mapEl || typeof window.L === 'undefined') return;

  map = L.map('index-map', {
    center: [41.01, 28.98],
    zoom: 10,
    zoomControl: true,
  });

  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    attribution: '© OpenStreetMap contributors © CARTO',
    subdomains: 'abcd',
    maxZoom: 19,
  }).addTo(map);
}

async function loadIndexData() {
  initIndexMap();

  try {
    const [ozet, oncelikli] = await Promise.all([
      API.getOzet(),
      API.getOncelikliIlceler(10),
    ]);

    // Populate Topbar & KPI
    updateTopBarInfo(ozet.analiz_yili || 2025, 'Güncel');

    const counts = ozet.tablo_kayit_sayilari || {};
    const coords = ozet.koordinat_durumlari || {};

    document.getElementById('kpi-ilce').textContent = counts.districts || 39;
    document.getElementById('kpi-kutuphane').textContent = counts.facilities || 72;
    document.getElementById('kpi-dogrulanmis').textContent = coords.verified || 51;
    document.getElementById('kpi-hesaplanan').textContent = counts.district_metrics || 39;
    document.getElementById('kpi-aday').textContent = ozet.puanli_ilce_sayisi || 29;

    // Populate Table
    const tbody = document.getElementById('priority-table-body');
    const ilceler = oncelikli.ilceler || [];

    if (ilceler.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="state-msg">Öncelikli ilçe verisi bulunamadı.</td></tr>';
      return;
    }

    const rowsHtml = ilceler.map(item => {
      const statusBadge = item.oncelik_seviyesi === 'Yüksek'
        ? '<span class="badge badge-critical">KRİTİK</span>'
        : (item.oncelik_seviyesi === 'Orta'
          ? '<span class="badge badge-high">YÜKSEK</span>'
          : '<span class="badge badge-low">NORMAL</span>');

      return `<tr onclick="window.location.href='./ilce_analizi.html?ilce=${encodeURIComponent(item.ilce)}'">
        <td style="font-family: var(--font-mono); font-weight: 600;">${String(item.sira).padStart(2, '0')}</td>
        <td style="font-weight: 700; color: var(--primary);">${esc(item.ilce)}</td>
        <td style="font-family: var(--font-mono);">${fmtNum(item.nufus)}</td>
        <td style="font-family: var(--font-mono); text-align: center;">${item.kutuphane_sayisi}</td>
        <td style="font-family: var(--font-mono); font-weight: 700; color: var(--secondary); text-align: center;">${typeof item.oncelik_puani === 'number' ? item.oncelik_puani.toFixed(1) : '—'}</td>
        <td>${statusBadge}</td>
      </tr>`;
    }).join('');

    tbody.innerHTML = rowsHtml;

    // Mark key locations on map
    if (map && typeof window.L !== 'undefined') {
      const coordsMap = {
        'Esenyurt': [41.0336, 28.67],
        'Pendik': [40.87, 29.23],
        'Küçükçekmece': [41.00, 28.78],
        'Bağcılar': [41.03, 28.84],
        'Ümraniye': [41.02, 29.09],
      };

      ilceler.slice(0, 5).forEach(item => {
        const pt = coordsMap[item.ilce];
        if (pt) {
          L.circleMarker(pt, {
            radius: 8,
            fillColor: item.oncelik_seviyesi === 'Yüksek' ? '#d00000' : '#256489',
            color: '#ffffff',
            weight: 2,
            fillOpacity: 0.8,
          }).bindPopup(`<b>${esc(item.ilce)}</b><br>Öncelik Puanı: ${item.oncelik_puani.toFixed(1)}`).addTo(map);
        }
      });
    }

  } catch (err) {
    console.error('[Genel Bakis] Error loading data:', err);
    const tbody = document.getElementById('priority-table-body');
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="6" class="state-msg error">API bağlantısı kurulamadı.<br>' + esc(err.message) + '</td></tr>';
    }
  }
}

document.addEventListener('DOMContentLoaded', loadIndexData);
