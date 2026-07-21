from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

analiz_veri_yolu = Path(
    "data/processed/ilce_kutuphane_analizi.csv"
)

grafik_cikti_yolu = Path(
    "frontend/assets/hizmet_orani_en_dusuk_10_ilce.png"
)


# --------------------------------------------------
# ANALİZ VERİSİNİ OKU
# --------------------------------------------------

analiz_verisi = pd.read_csv(
    analiz_veri_yolu
)


# --------------------------------------------------
# KÜTÜPHANE KAYDI BULUNAN İLÇELERİ SEÇ
# --------------------------------------------------

kayit_bulunan_ilceler = analiz_verisi[
    analiz_verisi["Kütüphane Sayısı"] > 0
].copy()


# --------------------------------------------------
# HİZMET ORANI EN DÜŞÜK 10 İLÇEYİ SEÇ
# --------------------------------------------------

en_dusuk_10_ilce = (
    kayit_bulunan_ilceler
    .sort_values(
        by="100 Bin Kişiye Düşen Kütüphane",
        ascending=True,
    )
    .head(10)
)


# --------------------------------------------------
# GRAFİĞİ OLUŞTUR
# --------------------------------------------------

fig, ax = plt.subplots(
    figsize=(12, 7)
)

cubuklar = ax.barh(
    en_dusuk_10_ilce["İlçe"],
    en_dusuk_10_ilce[
        "100 Bin Kişiye Düşen Kütüphane"
    ],
)


# En düşük değerin grafiğin üstünde görünmesini sağlar.
ax.invert_yaxis()


# --------------------------------------------------
# ÇUBUKLARIN ÜZERİNE DEĞERLERİ YAZ
# --------------------------------------------------

for cubuk, deger in zip(
    cubuklar,
    en_dusuk_10_ilce[
        "100 Bin Kişiye Düşen Kütüphane"
    ],
):
    ax.text(
        cubuk.get_width() + 0.005,
        cubuk.get_y() + cubuk.get_height() / 2,
        f"{deger:.3f}",
        va="center",
    )


# --------------------------------------------------
# BAŞLIK VE EKSEN BİLGİLERİ
# --------------------------------------------------

ax.set_title(
    "İBB Kütüphane Kaydı Bulunan İlçeler Arasında\n"
    "Hizmet Oranı En Düşük 10 İlçe"
)

ax.set_xlabel(
    "100 Bin Kişiye Düşen İBB Kütüphane Kaydı"
)

ax.set_ylabel(
    "İlçe"
)

ax.grid(
    axis="x",
    linestyle="--",
    alpha=0.4,
)


# --------------------------------------------------
# GRAFİĞİ KAYDET
# --------------------------------------------------

grafik_cikti_yolu.parent.mkdir(
    parents=True,
    exist_ok=True,
)

plt.tight_layout()
plt.subplots_adjust(
    left=0.20,
    right=0.94,
    top=0.88,
    bottom=0.12,
)

plt.savefig(
    grafik_cikti_yolu,
    dpi=200,
    bbox_inches="tight",
)

plt.close()


# --------------------------------------------------
# SONUCU GÖSTER
# --------------------------------------------------

print(
    "Grafiğe eklenen ilçeler:"
)

print(
    en_dusuk_10_ilce[
        [
            "İlçe",
            "100 Bin Kişiye Düşen Kütüphane",
        ]
    ].to_string(index=False)
)

print(
    f"\nGrafik kaydedildi: {grafik_cikti_yolu}"
)