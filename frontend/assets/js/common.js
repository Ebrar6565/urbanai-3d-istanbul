/**
 * common.js
 * UrbanAI 3D Istanbul Shared Frontend Utilities
 */
'use strict';

function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function fmtNum(val, decimals = 0) {
  if (typeof val !== 'number' || isNaN(val)) return '—';
  return val.toLocaleString('tr-TR', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function updateTopBarInfo(analizYili, sonGuncelleme) {
  const elYear = document.getElementById('topbar-analiz-yili');
  const elDate = document.getElementById('topbar-son-guncelleme');
  if (elYear && analizYili) {
    elYear.textContent = 'Analiz Yılı: ' + analizYili;
  }
  if (elDate && sonGuncelleme) {
    elDate.textContent = 'Son Güncelleme: ' + sonGuncelleme;
  }
}
