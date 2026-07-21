from pathlib import Path

import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

veri_yolu = Path(
    "data/processed/ilce_oncelik_puanlari.csv"
)

cikti_yolu = Path(
    "data/processed/agirlik_duyarlilik_sonuclari.csv"
)


# --------------------------------------------------
# VERİYİ OKU
# --------------------------------------------------

veri = pd.read_csv(veri_yolu)


# --------------------------------------------------
# İLK KONTROLLER
# --------------------------------------------------

print("Veri boyutu:")
print(veri.shape)

print("\nSütunlar:")
print(veri.columns.tolist())

print("\nİlk 5 kayıt:")

print(
    veri[
        [
            "İlçe",
            "Nüfus Puanı",
            "Hizmet Açığı Puanı",
            "Öncelik Puanı",
        ]
    ]
    .head()
    .to_string(index=False)
)

# --------------------------------------------------
# AĞIRLIK SENARYOLARINI HESAPLA
# --------------------------------------------------

# Senaryo 1:
# %70 hizmet açığı + %30 nüfus
veri["Senaryo 70-30 Puanı"] = (
    veri["Hizmet Açığı Puanı"] * 0.70
    + veri["Nüfus Puanı"] * 0.30
).round(3)


# Senaryo 2:
# %60 hizmet açığı + %40 nüfus
veri["Senaryo 60-40 Puanı"] = (
    veri["Hizmet Açığı Puanı"] * 0.60
    + veri["Nüfus Puanı"] * 0.40
).round(3)


# Senaryo 3:
# %50 hizmet açığı + %50 nüfus
veri["Senaryo 50-50 Puanı"] = (
    veri["Hizmet Açığı Puanı"] * 0.50
    + veri["Nüfus Puanı"] * 0.50
).round(3)


# --------------------------------------------------
# HER SENARYONUN SIRASINI HESAPLA
# --------------------------------------------------

veri["Senaryo 70-30 Sırası"] = (
    veri["Senaryo 70-30 Puanı"]
    .rank(
        method="min",
        ascending=False,
    )
    .astype(int)
)

veri["Senaryo 60-40 Sırası"] = (
    veri["Senaryo 60-40 Puanı"]
    .rank(
        method="min",
        ascending=False,
    )
    .astype(int)
)

veri["Senaryo 50-50 Sırası"] = (
    veri["Senaryo 50-50 Puanı"]
    .rank(
        method="min",
        ascending=False,
    )
    .astype(int)
)


# --------------------------------------------------
# 60-40 SENARYOSUNU ESKİ PUANLA KONTROL ET
# --------------------------------------------------

en_buyuk_fark = (
    veri["Senaryo 60-40 Puanı"]
    - veri["Öncelik Puanı"]
).abs().max()

print(
    "\nMevcut öncelik puanı ile "
    "60-40 senaryosu arasındaki en büyük fark:"
)

print(en_buyuk_fark)


# --------------------------------------------------
# SENARYO SONUÇLARINI GÖSTER
# --------------------------------------------------

senaryolar = [
    (
        "Senaryo 70-30",
        "Senaryo 70-30 Puanı",
        "Senaryo 70-30 Sırası",
    ),
    (
        "Senaryo 60-40",
        "Senaryo 60-40 Puanı",
        "Senaryo 60-40 Sırası",
    ),
    (
        "Senaryo 50-50",
        "Senaryo 50-50 Puanı",
        "Senaryo 50-50 Sırası",
    ),
]

for senaryo_adi, puan_sutunu, sira_sutunu in senaryolar:
    print(f"\n{senaryo_adi} — İlk 10 ilçe:")

    sonuc = (
        veri[
            [
                "İlçe",
                puan_sutunu,
                sira_sutunu,
            ]
        ]
        .sort_values(
            by=sira_sutunu,
            ascending=True,
        )
        .head(10)
    )

    print(
        sonuc.to_string(index=False)
    )
    # --------------------------------------------------
# SIRALAMA KARARLILIĞINI HESAPLA
# --------------------------------------------------

sira_sutunlari = [
    "Senaryo 70-30 Sırası",
    "Senaryo 60-40 Sırası",
    "Senaryo 50-50 Sırası",
]

veri["En İyi Sıra"] = (
    veri[sira_sutunlari].min(axis=1)
)

veri["En Kötü Sıra"] = (
    veri[sira_sutunlari].max(axis=1)
)

veri["Sıra Değişim Aralığı"] = (
    veri["En Kötü Sıra"]
    - veri["En İyi Sıra"]
)


# --------------------------------------------------
# KARARLILIK SEVİYESİNİ BELİRLE
# --------------------------------------------------

veri["Sıralama Kararlılığı"] = "Duyarlı"

veri.loc[
    veri["Sıra Değişim Aralığı"] <= 2,
    "Sıralama Kararlılığı",
] = "Kararlı"

veri.loc[
    veri["Sıra Değişim Aralığı"] == 0,
    "Sıralama Kararlılığı",
] = "Çok kararlı"


# --------------------------------------------------
# KARARLILIK SONUÇLARINI GÖSTER
# --------------------------------------------------

print(
    "\nAna modelde ilk 10 ilçenin "
    "senaryolara göre sıralama kararlılığı:"
)

print(
    veri[
        [
            "İlçe",
            "Senaryo 70-30 Sırası",
            "Senaryo 60-40 Sırası",
            "Senaryo 50-50 Sırası",
            "Sıra Değişim Aralığı",
            "Sıralama Kararlılığı",
        ]
    ]
    .sort_values(
        by="Senaryo 60-40 Sırası",
        ascending=True,
    )
    .head(10)
    .to_string(index=False)
)


# --------------------------------------------------
# SONUÇLARI DOSYAYA KAYDET
# --------------------------------------------------

veri = veri.sort_values(
    by="Senaryo 60-40 Sırası",
    ascending=True,
).reset_index(drop=True)

cikti_yolu.parent.mkdir(
    parents=True,
    exist_ok=True,
)

veri.to_csv(
    cikti_yolu,
    index=False,
    encoding="utf-8-sig",
)

print(
    f"\nDuyarlılık sonuçları kaydedildi: {cikti_yolu}"
)