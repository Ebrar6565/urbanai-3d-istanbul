/**
 * uydu-goruntuleri.js
 * Uydu Görüntüleri Page Script
 */
'use strict';

let currentDistrictPatches = [];
let currentSelectedPatch = null;

async function initUyduGoruntuleri() {
  try {
    const [ozet, uyduIlcelerData] = await Promise.all([
      API.getOzet(),
      API.getUyduIlceler(),
    ]);

    updateTopBarInfo(ozet.analiz_yili || 2025, 'Güncel');

    const ilceler = uyduIlcelerData.ilceler || uyduIlcelerData.uydu_ilceler || [];

    const distSelect = document.getElementById('sat-district-select');
    if (distSelect && ilceler.length > 0) {
      distSelect.innerHTML = ilceler.map(item => {
        const count = item.toplam_yama || item.yama_sayisi || 0;
        return `<option value="${esc(item.ilce)}">${esc(item.ilce)} (${count} yama)</option>`;
      }).join('');

      // Check query param for district or default to first
      const params = new URLSearchParams(window.location.search);
      const paramIlce = params.get('ilce');

      const targetDistrict = (paramIlce && ilceler.some(x => x.ilce === paramIlce)) ? paramIlce : ilceler[0].ilce;
      distSelect.value = targetDistrict;

      await loadDistrictPatches(targetDistrict);
    } else if (distSelect) {
      distSelect.innerHTML = '<option value="">Uydu ilçesi bulunamadı</option>';
    }

    if (distSelect) {
      distSelect.addEventListener('change', async () => {
        const val = distSelect.value;
        if (val) await loadDistrictPatches(val);
      });
    }

    const patchSelect = document.getElementById('sat-patch-select');
    if (patchSelect) {
      patchSelect.addEventListener('change', () => {
        const val = patchSelect.value;
        if (val) {
          const patch = currentDistrictPatches.find(p => p.yama_id === val);
          if (patch) displayPatchDetails(patch);
        }
      });
    }

  } catch (err) {
    const errorObj = {
      page: 'uydu_goruntuleri.html',
      url: err.url || (API_BASE_URL + '/api/uydu-ilceler'),
      status: err.status || 0,
      responseBody: err.body || '',
      message: err.message,
      stack: err.stack
    };
    console.error('[Uydu Goruntuleri] Error:', errorObj);
    const panel = document.getElementById('sat-metadata-panel');
    if (panel) {
      panel.innerHTML = '<div class="state-msg error">Uydu verileri yüklenemedi.<br>' + esc(err.message) + '</div>';
    }
  }
}

async function loadDistrictPatches(ilceName) {
  const patchSelect = document.getElementById('sat-patch-select');
  if (patchSelect) patchSelect.innerHTML = '<option value="">Yamaklar yükleniyor…</option>';

  try {
    const data = await API.getUyduGoruntuleri(ilceName);
    currentDistrictPatches = data.uydu_goruntuleri || [];

    if (currentDistrictPatches.length === 0) {
      if (patchSelect) patchSelect.innerHTML = '<option value="">Yama bulunamadı</option>';
      showEmptyPatch();
      return;
    }

    if (patchSelect) {
      patchSelect.innerHTML = currentDistrictPatches.map((p, idx) =>
        `<option value="${esc(p.yama_id)}">${esc(p.yama_id)} — Hücre: ${esc(p.hucre_id)} (#${idx + 1})</option>`
      ).join('');
    }

    // Select first patch
    displayPatchDetails(currentDistrictPatches[0]);

  } catch (err) {
    const errorObj = {
      page: 'uydu_goruntuleri.html',
      url: err.url || (API_BASE_URL + '/api/uydu-goruntuleri?ilce=' + encodeURIComponent(ilceName)),
      status: err.status || 0,
      responseBody: err.body || '',
      message: err.message,
      stack: err.stack
    };
    console.error('[Uydu Goruntuleri] District load error:', errorObj);
    showEmptyPatch(err.message);
  }
}

function showEmptyPatch(errMsg) {
  const imgPreview = document.getElementById('sat-img-preview');
  const imgLoading = document.getElementById('sat-img-loading');
  const panel = document.getElementById('sat-metadata-panel');

  if (imgPreview) imgPreview.style.display = 'none';
  if (imgLoading) {
    imgLoading.textContent = errMsg ? 'Görüntü yüklenemedi: ' + errMsg : 'Bu ilçe için uydu yaması bulunamadı.';
    imgLoading.style.display = 'block';
  }
  if (panel) {
    panel.innerHTML = '<div class="state-msg">' + (errMsg ? 'Hata: ' + esc(errMsg) : 'Uydu yaması bulunamadı.') + '</div>';
  }
}

function displayPatchDetails(patch) {
  currentSelectedPatch = patch;

  // 1. Display Image
  const imgPreview = document.getElementById('sat-img-preview');
  const imgLoading = document.getElementById('sat-img-loading');
  const frameLabel = document.getElementById('sat-frame-label');
  const gsdLabel   = document.getElementById('sat-gsd-label');

  const rawUrl = patch.gorsel?.goruntu_url || '';
  let imgUrl = '';
  if (rawUrl) {
    try {
      imgUrl = new URL(rawUrl, API_BASE_URL).href;
    } catch (_) {
      imgUrl = rawUrl;
    }
  }

  if (imgPreview && imgUrl) {
    imgPreview.src = imgUrl;
    imgPreview.style.display = 'block';
    if (imgLoading) imgLoading.style.display = 'none';
  } else if (imgLoading) {
    imgLoading.textContent = 'Görüntü bulunamadı';
    imgLoading.style.display = 'block';
    if (imgPreview) imgPreview.style.display = 'none';
  }

  if (frameLabel) frameLabel.textContent = `Sentinel-2 / ${patch.yama_id || 'YAMA'}`;
  if (gsdLabel && patch.raster) {
    gsdLabel.textContent = `Boyut: ${patch.raster.genislik_piksel || 156}x${patch.raster.yukseklik_piksel || 156}`;
  }

  // 2. Display Metadata Panel
  const panel = document.getElementById('sat-metadata-panel');
  if (!panel) return;

  const scene = patch.uydu_sahnesi || {};
  const raster = patch.raster || {};
  const quality = patch.kalite || {};
  const aday = patch.aday || {};

  const dateStr = scene.goruntu_tarihi_utc
    ? new Date(scene.goruntu_tarihi_utc).toLocaleString('tr-TR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
    : '—';

  const cloudPct = typeof scene.bulut_orani_yuzde === 'number' ? scene.bulut_orani_yuzde.toFixed(3) + '%' : '0.0%';
  const covPct = typeof quality.gercek_alan_kapsama_yuzde === 'number' ? quality.gercek_alan_kapsama_yuzde.toFixed(1) + '%' : '100%';

  panel.innerHTML = `
    <div style="padding: 16px; background: var(--surface-container-low); border-bottom: 1px solid var(--border-gray);">
      <div style="font-size: 10px; font-weight: 700; color: var(--secondary); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px;">YAMA ÖZELLİKLERİ</div>
      <h3 style="font-size: 18px; font-weight: 700; color: var(--primary); margin: 0;">${esc(patch.yama_id)}</h3>
      <div style="font-size: 12px; color: var(--on-surface-variant); margin-top: 2px;">İlçe: ${esc(patch.ilce?.ad || '—')}</div>
    </div>

    <div style="padding: 16px; display: flex; flex-direction: column; gap: 16px;">

      <!-- Kimlik Bilgileri -->
      <div>
        <h4 style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--on-surface-variant); margin-bottom: 8px; border-bottom: 1px solid var(--border-gray); padding-bottom: 4px;">KİMLİK BİLGİLERİ</h4>
        <div style="display: flex; flex-direction: column; gap: 6px; font-size: 12px;">
          <div style="display: flex; justify-content: space-between;">
            <span>Aday Sırası</span>
            <strong style="font-family: var(--font-mono);">#${String(aday.ilce_ici_sira || 1).padStart(4, '0')}</strong>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span>Hücre Kimliği</span>
            <span style="font-family: var(--font-mono); background: var(--surface-container-low); padding: 1px 6px; border-radius: 4px;">${esc(patch.hucre_id)}</span>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span>Yama ID</span>
            <span style="font-family: var(--font-mono);">${esc(patch.yama_id)}</span>
          </div>
        </div>
      </div>

      <!-- Sensör ve Platform -->
      <div>
        <h4 style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--on-surface-variant); margin-bottom: 8px; border-bottom: 1px solid var(--border-gray); padding-bottom: 4px;">SENSÖR VE PLATFORM</h4>
        <div style="display: flex; flex-direction: column; gap: 6px; font-size: 12px;">
          <div style="display: flex; justify-content: space-between;">
            <span>Platform</span>
            <strong>🚀 ${esc(scene.platform || 'Sentinel-2')}</strong>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span>Görüntü Tarihi</span>
            <span>${dateStr}</span>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span>Bulut Oranı</span>
            <span style="font-family: var(--font-mono); color: var(--error); font-weight: 700;">${cloudPct}</span>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span>Kapsama Oranı</span>
            <span style="font-family: var(--font-mono); color: var(--secondary); font-weight: 700;">${covPct}</span>
          </div>
        </div>
      </div>

      <!-- Status Card -->
      <div style="padding: 10px 12px; background: rgba(37,100,137,0.06); border: 1px solid rgba(37,100,137,0.18); border-radius: 6px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
          <span style="font-size: 10px; font-weight: 700; color: var(--secondary); text-transform: uppercase;">ANALİZE HAZIR</span>
          <span class="badge badge-high">L2A</span>
        </div>
        <div style="font-size: 11px; color: var(--on-surface-variant); line-height: 1.4;">
          Radyometrik ve atmosferik düzeltmeler doğrulanmıştır (L2A Ürünü).
        </div>
      </div>

      <!-- Uzamsal Bilgiler -->
      <div>
        <h4 style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--on-surface-variant); margin-bottom: 8px; border-bottom: 1px solid var(--border-gray); padding-bottom: 4px;">UZAMSAL BİLGİLER</h4>
        <div style="display: flex; flex-direction: column; gap: 6px; font-size: 12px;">
          <div style="display: flex; justify-content: space-between;">
            <span>Piksel Boyutu</span>
            <span>${raster.genislik_piksel || 156}px × ${raster.yukseklik_piksel || 156}px</span>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span>Koordinat Sistemi</span>
            <span style="font-family: var(--font-mono); font-size: 11px;">${esc(raster.koordinat_sistemi || 'EPSG:32635')}</span>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span>Kütüphaneye Uzaklık</span>
            <strong style="color: var(--primary);">${typeof aday.en_yakin_kutuphaneye_uzaklik_km === 'number' ? aday.en_yakin_kutuphaneye_uzaklik_km.toFixed(2) + ' km' : '—'}</strong>
          </div>
        </div>
      </div>

      <!-- Action Button -->
      <a href="./aday_bolgeler.html?ilce=${encodeURIComponent(patch.ilce?.ad || '')}" style="display: block; width: 100%; padding: 10px; background: var(--primary); color: #ffffff; text-align: center; font-weight: 700; border-radius: 6px; text-decoration: none; font-size: 12px; margin-top: 8px;">
        ADAY BÖLGEDE GÖSTER
      </a>

    </div>
  `;
}

document.addEventListener('DOMContentLoaded', initUyduGoruntuleri);
