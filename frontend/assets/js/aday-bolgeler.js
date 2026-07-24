/**
 * aday-bolgeler.js  v=5
 * UrbanAI 3D Istanbul -- Aday Bolgeler page
 */

'use strict';

/* ── Configuration ─────────────────────────────────────────── */
const BASE_URL = (typeof window.API_BASE_URL !== 'undefined') ? window.API_BASE_URL : 'http://127.0.0.1:8001';

/* ── AXIS 1: score → fill colour ───────────────────────────── */
function fillColour(puan) {
  if (puan >= 97) return '#1E3A8A';
  if (puan >= 92) return '#1D4ED8';
  if (puan >= 87) return '#3B82F6';
  if (puan >= 82) return '#60A5FA';
  return '#BFDBFE';
}

/* ── AXIS 2: site-review status → border colour ───────────── */
const REVIEW_MAP = new Map([
  ['Ön saha ve parsel incelemesine öncelikli', '#15803D'],
  ['İkinci düzey saha incelemesi',             '#D97706'],
  ['Yeşil alan niteliği araştırılmalı',        '#7E22CE'],
  ['Yer bulunabilirliği sınırlı olabilir',      '#DC2626'],
  ['Çevresel kısıt kontrolü gerekli',         '#0891B2'],
  ['Ek verilerle değerlendirilmelidir',        '#475569'],
  ['\u00d6n saha ve parsel incelemesine \u00f6ncelikli', '#15803D'],
  ['\u0130kinci d\u00fczey saha incelemesi',             '#D97706'],
  ['Ye\u015fil alan niteli\u011fi ara\u015ft\u0131r\u0131lmal\u0131', '#7E22CE'],
  ['Yer bulunabilirli\u011fi s\u0131n\u0131rl\u0131 olabilir', '#DC2626'],
  ['\u00c7evresel k\u0131s\u0131t kontrol\u00fc gerekli',    '#0891B2'],
  ['Ek verilerle de\u011ferlendirilmelidir',               '#475569'],
]);
function borderColour(durum) {
  return REVIEW_MAP.get(durum) || '#475569';
}

/* ── State ─────────────────────────────────────────────────── */
let allCandidates  = [];   // all from GET /api/aday-bolgeler
let districtList   = [];   // current district candidates
let selectedCand   = null;
let patches        = [];   // response.uydu_goruntuleri
let geoLayers      = {};   // hucre_id -> L.geoJSON layer
let map            = null;
let mapReady       = false;
let legendControl  = null;

/* ── DOM refs ──────────────────────────────────────────────── */
let elSelector, elSearch, elList, elCount,
    elDetail, elDistLabel, elYearBadge, elMapLoading;

function grabDOMRefs() {
  elSelector   = document.getElementById('district-selector');
  elSearch     = document.getElementById('cell-search');
  elList       = document.getElementById('candidate-list');
  elCount      = document.getElementById('candidate-count');
  elDetail     = document.getElementById('detail-content');
  elDistLabel  = document.getElementById('district-label');
  elYearBadge  = document.getElementById('year-badge');
  elMapLoading = document.getElementById('map-loading');
}

/* ── Map initialisation ─────────────────────────────────────── */
function initMap() {
  if (typeof window.L === 'undefined') {
    console.warn('[AB] Leaflet (window.L) is not available.');
    if (elMapLoading) {
      elMapLoading.textContent = 'Harita yüklenemedi (Leaflet kütüphanesi eksik).';
      elMapLoading.hidden = false;
    }
    mapReady = false;
    return false;
  }

  try {
    const mapContainer = document.getElementById('map');
    if (!mapContainer) {
      mapReady = false;
      return false;
    }

    map = L.map('map', {
      center: [41.01, 28.98],
      zoom: 10,
      zoomControl: false,
    });

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '© OpenStreetMap contributors © CARTO',
      subdomains: 'abcd',
      maxZoom: 19,
    }).addTo(map);

    L.control.zoom({ position: 'topright' }).addTo(map);

    mapReady = true;
    addMapLegends();

    setTimeout(() => { if (map) map.invalidateSize(); }, 100);
    return true;
  } catch (err) {
    console.error('[AB] Map init failed:', err);
    if (elMapLoading) {
      elMapLoading.textContent = 'Harita başlatılamadı.';
      elMapLoading.hidden = false;
    }
    mapReady = false;
    return false;
  }
}

/* ── Map Legends (Stacked cleanly in bottomleft control) ────── */
function addMapLegends() {
  if (typeof window.L === 'undefined' || !map) return;

  if (legendControl) {
    try { map.removeControl(legendControl); } catch (_) {}
  }

  legendControl = L.control({ position: 'bottomleft' });
  legendControl.onAdd = () => {
    const container = L.DomUtil.create('div', 'legend-container');
    container.innerHTML =
      '<div class="legend-card">' +
        '<h4>Dolgu — Hizmet İhtiyacı</h4>' +
        row('#1E3A8A', '97–100 En yüksek') +
        row('#1D4ED8', '92–96.99 Çok yüksek') +
        row('#3B82F6', '87–91.99 Yüksek') +
        row('#60A5FA', '82–86.99 Orta-yüksek') +
        row('#BFDBFE', '&lt; 82 Düşük') +
      '</div>' +
      '<div class="legend-card" style="margin-top: 6px;">' +
        '<h4>Sınır — Yer İnceleme Durumu</h4>' +
        lrow('#15803D', 'Ön saha incelemesi') +
        lrow('#D97706', 'İkinci düzey saha') +
        lrow('#7E22CE', 'Yeşil alan araştırılmalı') +
        lrow('#DC2626', 'Yer bulunabilirliği sınırlı') +
        lrow('#0891B2', 'Çevresel kısıt') +
        lrow('#475569', 'Ek verilerle değerlendirme') +
      '</div>';
    return container;
  };
  legendControl.addTo(map);

  function row(col, label) {
    return '<div class="legend-row"><span class="legend-swatch" style="background:' + col + '"></span><span>' + label + '</span></div>';
  }
  function lrow(col, label) {
    return '<div class="legend-row"><span class="legend-line-swatch" style="background:' + col + '"></span><span>' + label + '</span></div>';
  }
}

/* ── API helper ─────────────────────────────────────────────── */
async function localApiFetch(url) {
  const res = await fetch(url);
  if (!res.ok) {
    let body = '';
    try { body = await res.text(); } catch (_) {}
    const err = new Error('HTTP ' + res.status + ' ' + res.statusText);
    err.url    = url;
    err.status = res.status;
    err.body   = body;
    throw err;
  }
  return res.json();
}

/* ── Boot sequence ───────────────────────────────────────────── */
async function initializeApp() {
  grabDOMRefs();
  
  // Safe map init — failure will not stop API candidate loading
  initMap();

  showListMsg('Adaylar yükleniyor…');

  try {
    const data = await localApiFetch(BASE_URL + '/api/aday-bolgeler');

    if (!data || !Array.isArray(data.aday_bolgeler)) {
      throw new Error('response.aday_bolgeler bir dizi değil. Alınan: ' + JSON.stringify(data).slice(0, 200));
    }

    allCandidates = data.aday_bolgeler;

    if (allCandidates.length === 0) {
      showListMsg('Hiç aday bölge bulunamadı.');
      if (elSelector) elSelector.innerHTML = '<option value="">Aday bulunamadı</option>';
      return;
    }

    // Build district selector from unique candidate.ilce values
    const districts = [...new Set(
      allCandidates.map(c => c.ilce).filter(Boolean)
    )].sort((a, b) => a.localeCompare(b, 'tr'));

    populateSelector(districts);

    // Check query params for initial district
    const urlParams = new URLSearchParams(window.location.search);
    const paramIlce = urlParams.get('ilce');
    const targetDistrict = (paramIlce && districts.includes(paramIlce)) ? paramIlce : districts[0];

    if (elSelector) elSelector.value = targetDistrict;
    await loadDistrict(targetDistrict);

  } catch (err) {
    const errorObj = {
      page: 'aday_bolgeler.html',
      url: err.url || (BASE_URL + '/api/aday-bolgeler'),
      status: err.status || 0,
      responseBody: err.body || '',
      message: err.message,
      stack: err.stack
    };
    console.error('[AB] initializeApp failed:', errorObj);
    showListMsg(
      'API bağlantısı kurulamadı.\n' +
      'URL: ' + errorObj.url + '\n' +
      'Hata: ' + err.message,
      true
    );
    if (elSelector) elSelector.innerHTML = '<option value="">Yükleme hatası</option>';
  }
}

function populateSelector(districts) {
  if (!elSelector) return;
  elSelector.innerHTML = '';
  districts.forEach(ilce => {
    const opt = document.createElement('option');
    opt.value = ilce;
    opt.textContent = ilce;
    elSelector.appendChild(opt);
  });
}

/* ── District loading ────────────────────────────────────────── */
async function loadDistrict(ilce) {
  selectedCand = null;
  patches      = [];

  // Filter from already-fetched allCandidates
  districtList = allCandidates.filter(c => c.ilce === ilce);

  renderList(districtList);
  if (elDistLabel) elDistLabel.textContent = ilce;

  // Year badge from first candidate
  const first = districtList[0];
  if (first && elYearBadge) {
    const parts = [];
    if (first.analiz_yili)     parts.push('Analiz: ' + first.analiz_yili);
    if (first.worldcover_yili) parts.push('WC: '    + first.worldcover_yili);
    if (parts.length) {
      elYearBadge.textContent = parts.join(' · ');
      elYearBadge.hidden = false;
    } else {
      elYearBadge.hidden = true;
    }
  } else if (elYearBadge) {
    elYearBadge.hidden = true;
  }

  // Clear old map layers if map is ready
  clearLayers();

  // Fetch geometry + satellite in parallel
  showMapLoading(true);
  try {
    const [geoRes, satRes] = await Promise.allSettled([
      localApiFetch(BASE_URL + '/api/aday-bolgeler?ilce=' + encodeURIComponent(ilce) + '&geometri=true'),
      localApiFetch(BASE_URL + '/api/uydu-goruntuleri?ilce=' + encodeURIComponent(ilce)),
    ]);

    if (geoRes.status === 'fulfilled' && geoRes.value) {
      const geoData = geoRes.value;
      const geoMap = {};
      (geoData.aday_bolgeler || []).forEach(c => {
        if (c.hucre_id && c.geometri) geoMap[c.hucre_id] = c.geometri;
      });
      districtList.forEach(c => {
        if (geoMap[c.hucre_id]) c.geometri = geoMap[c.hucre_id];
      });
    } else {
      console.warn('[AB] Geometry fetch failed or empty:', geoRes.reason);
    }

    if (satRes.status === 'fulfilled' && satRes.value) {
      patches = satRes.value.uydu_goruntuleri || [];
    } else {
      console.warn('[AB] Satellite fetch failed or empty:', satRes.reason);
      patches = [];
    }

    renderMapLayers(districtList);

  } catch (err) {
    console.error('[AB] loadDistrict geo/sat failed:', err);
  } finally {
    showMapLoading(false);
  }

  // Auto-select first candidate
  if (districtList.length > 0) {
    selectCandidate(districtList[0]);
  } else {
    showDetailPlaceholder();
  }
}

/* ── Map layer management ────────────────────────────────────── */
function clearLayers() {
  if (!mapReady || !map || typeof window.L === 'undefined') return;
  Object.values(geoLayers).forEach(l => {
    try { if (map.hasLayer(l)) map.removeLayer(l); } catch (_) {}
  });
  geoLayers = {};
}

function renderMapLayers(candidates) {
  if (!mapReady || !map || typeof window.L === 'undefined') return;
  const bounds = [];

  candidates.forEach(c => {
    if (!c.geometri) return;
    const fc = fillColour(c.hizmet_ihtiyaci?.puan ?? 0);
    const bc = borderColour(c.yer_inceleme?.durum ?? '');

    try {
      const layer = L.geoJSON(c.geometri, {
        style: {
          fillColor:   fc,
          fillOpacity: 0.45,
          color:       bc,
          weight:      1.5,
          dashArray:   '5,3',
          opacity:     0.85,
        },
      });
      layer.on('click', () => selectCandidate(c));
      layer.addTo(map);
      geoLayers[c.hucre_id] = layer;

      const b = layer.getBounds();
      if (b && typeof b.isValid === 'function' && b.isValid()) bounds.push(b);
    } catch (err) {
      console.warn('[AB] Layer render error for cell:', c.hucre_id, err);
    }
  });

  if (bounds.length > 0) {
    try {
      const combined = bounds.reduce((acc, b) => acc.extend(b), L.latLngBounds(bounds[0]));
      map.fitBounds(combined, { padding: [40, 40] });
      setTimeout(() => { if (map) map.invalidateSize(); }, 50);
    } catch (_) {}
  }
}

function highlightLayer(hucreId) {
  if (!mapReady || !map || typeof window.L === 'undefined') return;
  Object.entries(geoLayers).forEach(([id, layer]) => {
    const c  = districtList.find(x => x.hucre_id === id);
    const fc = fillColour(c?.hizmet_ihtiyaci?.puan ?? 0);
    const bc = borderColour(c?.yer_inceleme?.durum ?? '');
    if (id === hucreId) {
      layer.setStyle({ fillOpacity: 0.75, weight: 3.5, dashArray: null, color: bc, fillColor: fc });
      try { layer.bringToFront(); } catch (_) {}
      // NOTE: Do NOT call fitBounds here — preserve district-wide map extent so all 5 polygons stay visible!
      try {
        const b = layer.getBounds();
        if (b && typeof b.isValid === 'function' && b.isValid()) {
          const center = b.getCenter();
          if (!map.getBounds().contains(center)) {
            map.panTo(center, { animate: true });
          }
        }
      } catch (_) {}
    } else {
      layer.setStyle({ fillOpacity: 0.45, weight: 1.5, dashArray: '5,3', color: bc, fillColor: fc });
    }
  });
}

/* ── Candidate list rendering ────────────────────────────────── */
function showListMsg(msg, isError) {
  if (!elList) return;
  const cls = isError ? 'state-msg error' : 'state-msg';
  const html = esc(msg).replace(/\n/g, '<br>');
  elList.innerHTML = '<div class="' + cls + '">' + html + '</div>';
  if (elCount) elCount.textContent = 'N=0';
}

function renderList(candidates) {
  if (!elList) return;
  if (elCount) elCount.textContent = 'N=' + candidates.length;

  if (candidates.length === 0) {
    elList.innerHTML = '<div class="state-msg">Bu ilçe için aday bölge bulunamadı.</div>';
    return;
  }

  const frag = document.createDocumentFragment();
  candidates.forEach(c => {
    const hi    = c.hizmet_ihtiyaci || {};
    const yi    = c.yer_inceleme    || {};
    const puan  = typeof hi.puan === 'number' ? hi.puan.toFixed(2) : '—';
    const sira  = hi.sira  ?? '—';
    const seviye= hi.seviye ?? '—';
    const durum = yi.durum  ?? '—';

    const row = document.createElement('div');
    row.className       = 'candidate-row';
    row.dataset.hucreId = c.hucre_id;
    row.setAttribute('role', 'option');
    row.setAttribute('tabindex', '0');
    row.innerHTML =
      '<div class="cand-left">' +
        '<span class="cand-rank">#' + sira + '</span>' +
        '<span class="cand-id">'   + esc(c.hucre_id) + '</span>' +
        '<span class="cand-review" title="' + esc(durum) + '">' + esc(durum) + '</span>' +
      '</div>' +
      '<div class="cand-right">' +
        '<span class="cand-score">' + puan + '</span>' +
        '<span class="cand-level">' + esc(seviye) + '</span>' +
      '</div>';

    row.addEventListener('click', () => selectCandidate(c));
    row.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') selectCandidate(c); });
    frag.appendChild(row);
  });

  elList.innerHTML = '';
  elList.appendChild(frag);
}

/* ── Candidate selection ─────────────────────────────────────── */
function selectCandidate(candidate) {
  selectedCand = candidate;

  document.querySelectorAll('.candidate-row').forEach(row => {
    row.classList.toggle('selected', row.dataset.hucreId === candidate.hucre_id);
  });

  const sel = document.querySelector('.candidate-row[data-hucre-id="' + candidate.hucre_id + '"]');
  if (sel) sel.scrollIntoView({ block: 'nearest' });

  highlightLayer(candidate.hucre_id);

  const patch = patches.find(p => p.hucre_id === candidate.hucre_id) || null;
  renderDetail(candidate, patch);

  const detailPanel = document.getElementById('detail-panel');
  if (window.innerWidth < 700 && detailPanel) {
    detailPanel.classList.add('open');
  }
}

/* ── Detail panel ────────────────────────────────────────────── */
function showDetailPlaceholder() {
  const detailPanel = document.getElementById('detail-panel');
  if (detailPanel) detailPanel.classList.remove('open');
  if (elDetail) {
    elDetail.innerHTML =
      '<div class="detail-placeholder">' +
      '<span class="material-symbols-outlined">map</span>' +
      '<p>Listeden bir aday bölge seçin.</p>' +
      '</div>';
  }
}

function renderDetail(c, patch) {
  if (!elDetail) return;
  const hi    = c.hizmet_ihtiyaci       || {};
  const ku    = c.en_yakin_kutuphane    || {};
  const ao    = c.arazi_ortusu          || {};
  const yi    = c.yer_inceleme          || {};
  const durum = yi.durum                || '—';
  const bc    = borderColour(durum);

  const fmt  = v => typeof v === 'number' ? v.toFixed(2) : (v ?? '—');
  const pct  = v => typeof v === 'number' ? v.toFixed(1) : '0';

  /* library card */
  const libHtml = ku.ad
    ? '<div class="det-lib-card">' +
        '<div class="det-field"><strong>En yakın kütüphane:</strong> ' + esc(ku.ad) + '</div>' +
        '<div class="det-field"><strong>Kütüphaneye uzaklık:</strong> ' + fmt(ku.uzaklik_km) + ' km</div>' +
      '</div>'
    : '';

  /* satellite */
  let imgUrl = '';
  if (patch && patch.gorsel && patch.gorsel.goruntu_url) {
    try {
      imgUrl = new URL(patch.gorsel.goruntu_url, BASE_URL).href;
    } catch (_) {
      imgUrl = patch.gorsel.goruntu_url;
    }
  }

  const satHtml = imgUrl
    ? '<div class="sentinel-frame">' +
        '<img src="' + esc(imgUrl) + '" alt="Sentinel-2 RGB önizleme" loading="lazy">' +
        '<span class="sentinel-badge">RGB 4-3-2</span>' +
      '</div>'
    : '<p class="sentinel-empty">Bu aday bölge için uydu önizlemesi bulunamadı.</p>';

  /* general eval */
  const genelHtml = c.genel_degerlendirme
    ? '<p class="review-genel">' + esc(c.genel_degerlendirme) + '</p>' : '';

  elDetail.innerHTML =
    /* Identification */
    '<div class="det-ident">' +
      '<div class="det-id-row">' +
        '<span class="det-cell-id">Hücre: ' + esc(c.hucre_id) + '</span>' +
        '<button class="det-close" id="det-close-btn" title="Kapat">' +
          '<span class="material-symbols-outlined">close</span>' +
        '</button>' +
      '</div>' +
      '<div class="det-field-list">' +
        '<div class="det-field"><strong>Hizmet ihtiyacı sırası:</strong> #' + (hi.sira ?? '—') + '</div>' +
        '<div class="det-field"><strong>Hizmet ihtiyacı puanı:</strong> ' + fmt(hi.puan) + '</div>' +
        '<div class="det-field"><strong>Hizmet ihtiyacı seviyesi:</strong> ' + esc(hi.seviye ?? '—') + '</div>' +
      '</div>' +
      libHtml +
    '</div>' +

    /* Body */
    '<div class="det-body">' +

      /* Section 2: inceleme */
      '<div class="det-section">' +
        '<h3 class="det-section-heading">İnceleme Durumu</h3>' +
        '<div class="review-card">' +
          '<span class="material-symbols-outlined ms-filled review-icon" style="color:' + bc + '">assignment_late</span>' +
          '<div class="review-text-wrap">' +
            '<div class="review-durum" style="color:' + bc + '">' + esc(durum) + '</div>' +
            (yi.aciklama ? '<div class="review-aciklama">' + esc(yi.aciklama) + '</div>' : '') +
            genelHtml +
          '</div>' +
        '</div>' +
      '</div>' +

      /* Section 3: arazi ortusu */
      '<div class="det-section">' +
        '<h3 class="det-section-heading">Arazi Örtüsü' + (c.worldcover_yili ? ' — ' + c.worldcover_yili : '') + '</h3>' +
        '<div class="lc-bars">' +
          lcBar('Yapılaşmış alan', ao.yapilasmis_alan_yuzde, '#26384A') +
          lcBar('Bitkisel / yeşil alan', ao.bitkisel_yesil_alan_yuzde, '#3E7C59') +
          lcBar('Açık / çıplak alan', ao.acik_ciplak_alan_yuzde, '#B77932') +
          lcBar('Su / sulak alan', ao.su_sulak_alan_yuzde, '#256489') +
        '</div>' +
        '<div class="lc-footer">' +
          (ao.worldcover_kapsama_yuzde != null ? '<span>Kapsam: %' + pct(ao.worldcover_kapsama_yuzde) + '</span>' : '') +
          (c.worldcover_yili ? '<span>Yıl: ' + c.worldcover_yili + '</span>' : '') +
        '</div>' +
      '</div>' +

      /* Section 4: satellite */
      '<div class="det-section">' +
        '<h3 class="det-section-heading">Sentinel-2 RGB Önizleme</h3>' +
        satHtml +
      '</div>' +

      /* Action */
      '<button class="det-action-btn" id="det-action-btn">Aday ayrıntılarını görüntüle</button>' +

    '</div>';

  document.getElementById('det-close-btn')?.addEventListener('click', () => {
    const detailPanel = document.getElementById('detail-panel');
    if (detailPanel) detailPanel.classList.remove('open');
    if (window.innerWidth >= 700) showDetailPlaceholder();
  });

  document.getElementById('det-action-btn')?.addEventListener('click', () => {
    window.open(BASE_URL + '/api/aday-bolgeler/' + encodeURIComponent(c.hucre_id), '_blank');
  });
}

function lcBar(label, val, colour) {
  const pct = typeof val === 'number' ? Math.min(100, Math.max(0, val)) : 0;
  const display = typeof val === 'number' ? val.toFixed(1) : '0';
  return '<div class="lc-bar-row">' +
    '<div class="lc-label-row"><span>' + esc(label) + '</span><span>%' + display + '</span></div>' +
    '<div class="lc-track"><div class="lc-fill" style="width:' + pct + '%;background:' + colour + '"></div></div>' +
  '</div>';
}

/* ── Utility ─────────────────────────────────────────────────── */
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function showMapLoading(show) {
  if (elMapLoading) elMapLoading.hidden = !show;
}

/* ── Cell-ID search ─────────────────────────────────────────── */
function handleSearch(q) {
  q = q.trim().toLowerCase();
  const list = q
    ? districtList.filter(c => c.hucre_id?.toLowerCase().includes(q))
    : districtList;
  renderList(list);
  if (list.length === 1) selectCandidate(list[0]);
}

/* ── Events ─────────────────────────────────────────────────── */
function bindEvents() {
  if (elSelector) {
    elSelector.addEventListener('change', async () => {
      const ilce = elSelector.value;
      if (ilce) {
        if (elSearch) elSearch.value = '';
        await loadDistrict(ilce);
      }
    });
  }

  if (elSearch) {
    elSearch.addEventListener('input', () => handleSearch(elSearch.value));
  }
}

/* ── Entry point ─────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  try {
    await initializeApp();
    bindEvents();
  } catch (err) {
    console.error('[AB] top-level error:', err);
  }
});
