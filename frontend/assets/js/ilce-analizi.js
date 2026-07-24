/**
 * ilce-analizi.js
 * İlçe Analizi Page Script
 */
'use strict';

let allOncelikliList = [];
let selectedIlceName = '';

async function initIlceAnalizi() {
  try {
    const [ozet, oncelikli] = await Promise.all([
      API.getOzet(),
      API.getOncelikliIlceler(39),
    ]);

    updateTopBarInfo(ozet.analiz_yili || 2025, 'Güncel');

    allOncelikliList = oncelikli.ilceler || [];

    // Check query param
    const params = new URLSearchParams(window.location.search);
    const paramIlce = params.get('ilce');

    renderDistrictTable(allOncelikliList);

    // Initial selected district
    if (paramIlce && allOncelikliList.some(item => item.ilce.toLowerCase() === paramIlce.toLowerCase())) {
      const match = allOncelikliList.find(item => item.ilce.toLowerCase() === paramIlce.toLowerCase());
      selectDistrict(match.ilce);
    } else if (allOncelikliList.length > 0) {
      selectDistrict(allOncelikliList[0].ilce);
    }

    bindFilterEvents();

  } catch (err) {
    console.error('[Ilce Analizi] Error:', err);
    const tbody = document.getElementById('ilce-table-body');
    if (tbody) {
      tbody.innerHTML = '<tr><td colspan="7" class="state-msg error">API verileri yüklenemedi.<br>' + esc(err.message) + '</td></tr>';
    }
  }
}

function bindFilterEvents() {
  const selectFilter = document.getElementById('priority-filter');
  const searchInput  = document.getElementById('ilce-search-input');

  const filterAction = () => {
    const level = selectFilter ? selectFilter.value : 'all';
    const query = searchInput ? searchInput.value.trim().toLowerCase() : '';

    let filtered = allOncelikliList;

    if (level !== 'all') {
      filtered = filtered.filter(item => item.oncelik_seviyesi === level);
    }

    if (query) {
      filtered = filtered.filter(item => item.ilce.toLowerCase().includes(query));
    }

    renderDistrictTable(filtered);
  };

  if (selectFilter) selectFilter.addEventListener('change', filterAction);
  if (searchInput) searchInput.addEventListener('input', filterAction);
}

function renderDistrictTable(list) {
  const tbody = document.getElementById('ilce-table-body');
  const info = document.getElementById('district-count-info');

  if (info) {
    info.textContent = 'Analiz edilen ilçe sayısı: ' + list.length;
  }

  if (!tbody) return;

  if (list.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="state-msg">Filtre kriterlerine uygun ilçe bulunamadı.</td></tr>';
    return;
  }

  const html = list.map(item => {
    const isSelected = item.ilce === selectedIlceName;
    const isHigh = item.oncelik_seviyesi === 'Yüksek';
    const isMed  = item.oncelik_seviyesi === 'Orta';
    const badge = isHigh
      ? '<span class="badge badge-critical">KRİTİK</span>'
      : (isMed ? '<span class="badge badge-high">YÜKSEK</span>' : '<span class="badge badge-low">DÜŞÜK</span>');

    const score = typeof item.oncelik_puani === 'number' ? item.oncelik_puani.toFixed(1) : '—';
    const per100k = typeof item.yuz_bin_kisiye_kutuphane === 'number'
      ? (item.nufus / (item.kutuphane_sayisi || 1)).toLocaleString('tr-TR', { maximumFractionDigits: 0 }) + ' / küt.'
      : '—';

    return `<tr class="${isSelected ? 'selected' : ''}" style="${isSelected ? 'background: var(--surface-container-low); border-left: 3px solid var(--secondary);' : ''}" onclick="selectDistrict('${esc(item.ilce)}')">
      <td style="padding-left: 20px; font-weight: 700; color: var(--primary);">${esc(item.ilce)}</td>
      <td style="font-family: var(--font-mono);">${fmtNum(item.nufus)}</td>
      <td style="font-family: var(--font-mono); text-align: center;">${item.kutuphane_sayisi}</td>
      <td>
        <div style="display: flex; align-items: center; gap: 8px;">
          <div style="width: 70px; height: 6px; background: var(--surface-container-highest); border-radius: 3px; overflow: hidden;">
            <div style="height: 100%; width: ${Math.min(100, Math.max(0, score))}%; background: ${isHigh ? '#d00000' : '#256489'};"></div>
          </div>
          <span style="font-family: var(--font-mono); font-weight: 700; color: ${isHigh ? '#d00000' : '#256489'};">${score}</span>
        </div>
      </td>
      <td style="font-size: 12px; color: var(--on-surface-variant);">${per100k}</td>
      <td style="font-family: var(--font-mono); font-weight: 700; text-align: center;">${String(item.sira).padStart(2, '0')}</td>
      <td>${badge}</td>
    </tr>`;
  }).join('');

  tbody.innerHTML = html;
}

async function selectDistrict(ilceName) {
  selectedIlceName = ilceName;

  renderDistrictTable(allOncelikliList);

  const panel = document.getElementById('ilce-detail-panel');
  if (!panel) return;

  panel.innerHTML = '<div class="state-msg">' + esc(ilceName) + ' detayları yükleniyor…</div>';

  try {
    const data = await API.getIlce(ilceName);
    const info = data.ilce_bilgileri || {};
    const libs = data.kutuphaneler || [];

    const isHigh = info.oncelik_seviyesi === 'Yüksek';
    const badgeColor = isHigh ? '#d00000' : '#256489';

    const libListHtml = libs.length > 0
      ? libs.map(lib => `
          <div style="padding: 10px 12px; background: var(--surface-container-low); border: 1px solid var(--border-gray); border-radius: 6px; margin-bottom: 8px;">
            <div style="font-size: 13px; font-weight: 700; color: var(--primary); margin-bottom: 4px;">${esc(lib.kutuphane_adi)}</div>
            <div style="font-size: 12px; color: var(--on-surface-variant); margin-bottom: 2px;">📍 ${esc(lib.adres || lib.ilce)}</div>
            <div style="font-size: 11px; color: var(--on-surface-variant); display: flex; justify-content: space-between;">
              <span>Saatler: ${esc(lib.calisma_saatleri || '09:00-18:00')}</span>
              <span>Günler: ${esc(lib.calisma_gunleri || 'Hergün')}</span>
            </div>
          </div>
        `).join('')
      : '<p style="font-size: 12px; color: var(--on-surface-variant); font-style: italic;">Bu ilçe için veri tabanında kayıtlı aktif kütüphane bulunamadı.</p>';

    panel.innerHTML = `
      <!-- Header Banner -->
      <div style="padding: 20px; background: var(--primary); color: #ffffff; flex-shrink: 0;">
        <div style="font-size: 10px; font-weight: 700; text-transform: uppercase; opacity: 0.8; margin-bottom: 4px;">DETAYLI İLÇE ANALİZİ</div>
        <h2 style="font-size: 22px; font-weight: 700; margin: 0;">${esc(info.ilce || ilceName)}</h2>
      </div>

      <div style="padding: 20px; display: flex; flex-direction: column; gap: 20px;">

        <!-- Priority Card -->
        <div style="padding: 12px 16px; background: ${isHigh ? 'rgba(208,0,0,0.06)' : 'rgba(37,100,137,0.06)'}; border: 1px solid ${isHigh ? 'rgba(208,0,0,0.2)' : 'rgba(37,100,137,0.2)'}; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div style="font-size: 10px; font-weight: 700; color: ${badgeColor}; text-transform: uppercase;">ÖNCELİK DURUMU</div>
            <div style="font-size: 14px; font-weight: 700; color: ${badgeColor};">${esc(info.oncelik_seviyesi || 'Normal')}</div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 10px; font-weight: 700; color: ${badgeColor}; text-transform: uppercase;">SIRALAMA</div>
            <div style="font-size: 24px; font-weight: 800; color: ${badgeColor}; line-height: 1;">#${String(info.oncelik_sirasi || '—').padStart(2, '0')}</div>
          </div>
        </div>

        <!-- Metrics Grid -->
        <div>
          <h4 style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--on-surface-variant); margin-bottom: 10px; border-bottom: 1px solid var(--border-gray); padding-bottom: 4px;">TEMEL VERİLER</h4>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
            <div style="padding: 10px; background: var(--surface-container-low); border: 1px solid var(--border-gray); border-radius: 6px;">
              <div style="font-size: 11px; color: var(--on-surface-variant);">İlçe Nüfusu</div>
              <div style="font-size: 16px; font-weight: 700; color: var(--primary); margin-top: 2px;">${fmtNum(info.nufus)}</div>
            </div>
            <div style="padding: 10px; background: var(--surface-container-low); border: 1px solid var(--border-gray); border-radius: 6px;">
              <div style="font-size: 11px; color: var(--on-surface-variant);">Kütüphane Sayısı</div>
              <div style="font-size: 16px; font-weight: 700; color: var(--primary); margin-top: 2px;">${info.kutuphane_sayisi || 0} Adet</div>
            </div>
          </div>
        </div>

        <!-- Scores Section -->
        <div>
          <h4 style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--on-surface-variant); margin-bottom: 10px; border-bottom: 1px solid var(--border-gray); padding-bottom: 4px;">ANALİZ PUANLARI</h4>
          <div style="display: flex; flex-direction: column; gap: 10px;">
            <div>
              <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
                <span>Hizmet Açığı Puanı</span>
                <strong style="color: ${badgeColor};">${typeof info.hizmet_acigi_puani === 'number' ? info.hizmet_acigi_puani.toFixed(1) : '—'}</strong>
              </div>
              <div style="height: 6px; background: var(--surface-container-highest); border-radius: 3px; overflow: hidden;">
                <div style="height: 100%; width: ${Math.min(100, Math.max(0, info.hizmet_acigi_puani || 0))}%; background: ${badgeColor};"></div>
              </div>
            </div>
            <div>
              <div style="display: flex; justify-content: space-between; font-size: 12px; margin-bottom: 4px;">
                <span>Genel Öncelik Puanı</span>
                <strong style="color: ${badgeColor};">${typeof info.oncelik_puani === 'number' ? info.oncelik_puani.toFixed(1) : '—'}</strong>
              </div>
              <div style="height: 6px; background: var(--surface-container-highest); border-radius: 3px; overflow: hidden;">
                <div style="height: 100%; width: ${Math.min(100, Math.max(0, info.oncelik_puani || 0))}%; background: ${badgeColor};"></div>
              </div>
            </div>
          </div>
        </div>

        <!-- Libraries List -->
        <div>
          <h4 style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--on-surface-variant); margin-bottom: 10px; border-bottom: 1px solid var(--border-gray); padding-bottom: 4px;">MEVCUT KÜTÜPHANELER (${libs.length})</h4>
          ${libListHtml}
        </div>

        <!-- Action Link -->
        <a href="./aday_bolgeler.html?ilce=${encodeURIComponent(info.ilce || ilceName)}" style="display: block; width: 100%; padding: 12px; background: var(--secondary); color: #ffffff; text-align: center; font-weight: 700; border-radius: 6px; text-decoration: none; font-size: 13px;">
          ADAY BÖLGELERİ İNCELE
        </a>

      </div>
    `;

  } catch (err) {
    console.error('[Ilce Analizi] Select error:', err);
    panel.innerHTML = '<div class="state-msg error">İlçe detayları yüklenemedi.<br>' + esc(err.message) + '</div>';
  }
}

document.addEventListener('DOMContentLoaded', initIlceAnalizi);
