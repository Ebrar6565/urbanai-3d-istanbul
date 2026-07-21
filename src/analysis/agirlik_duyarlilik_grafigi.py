from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

veri_yolu = Path(
    "data/processed/agirlik_duyarlilik_sonuclari.csv"
)

grafik_yolu = Path(
    "frontend/assets/agirlik_duyarlilik_ilk_5.png"
)


# --------------------------------------------------
# VERİYİ OKU
# --------------------------------------------------

veri = pd.read_csv(veri_yolu)


# --------------------------------------------------
# ANA MODELDE İLK 5 İLÇEYİ SEÇ
# --------------------------------------------------

ilk_5_ilce = (
    veri
    .sort_values(
        by="Senaryo 60-40 Sırası",
        ascending=True,
    )
    .head(5)
    .copy()
)


# --------------------------------------------------
# GRAFİK KONUM AYARLARI
# --------------------------------------------------

ilceler = ilk_5_ilce["İlçe"]

x_konumlari = np.arange(
    len(ilceler)
)

cubuk_genisligi = 0.24


# --------------------------------------------------
# GRAFİĞİ OLUŞTUR
# --------------------------------------------------

fig, ax = plt.subplots(
    figsize=(12, 7)
)

cubuk_70_30 = ax.bar(
    x_konumlari - cubuk_genisligi,
    ilk_5_ilce["Senaryo 70-30 Puanı"],
    cubuk_genisligi,
    label="%70 hizmet açığı + %30 nüfus",
)

cubuk_60_40 = ax.bar(
    x_konumlari,
    ilk_5_ilce["Senaryo 60-40 Puanı"],
    cubuk_genisligi,
    label="%60 hizmet açığı + %40 nüfus",
)

cubuk_50_50 = ax.bar(
    x_konumlari + cubuk_genisligi,
    ilk_5_ilce["Senaryo 50-50 Puanı"],
    cubuk_genisligi,
    label="%50 hizmet açığı + %50 nüfus",
)


# --------------------------------------------------
# PUANLARI ÇUBUKLARIN ÜZERİNE YAZ
# --------------------------------------------------

for cubuk_grubu in [
    cubuk_70_30,
    cubuk_60_40,
    cubuk_50_50,
]:
    ax.bar_label(
        cubuk_grubu,
        fmt="%.1f",
        padding=3,
        fontsize=8,
    )


# --------------------------------------------------
# BAŞLIK VE EKSENLER
# --------------------------------------------------

ax.set_title(
    "Öncelikli İlk 5 İlçenin\n"
    "Ağırlık Senaryolarına Göre Puanları"
)

ax.set_xlabel(
    "İlçe"
)

ax.set_ylabel(
    "Öncelik Puanı"
)

ax.set_xticks(
    x_konumlari,
    ilceler,
)

ax.set_ylim(
    0,
    105,
)

ax.legend(
    title="Ağırlık senaryosu"
)

ax.grid(
    axis="y",
    linestyle="--",
    alpha=0.4,
)


# --------------------------------------------------
# GRAFİĞİ KAYDET
# --------------------------------------------------

grafik_yolu.parent.mkdir(
    parents=True,
    exist_ok=True,
)

plt.tight_layout()

plt.savefig(
    grafik_yolu,
    dpi=200,
    bbox_inches="tight",
)

plt.close()


# --------------------------------------------------
# SONUÇLARI GÖSTER
# --------------------------------------------------

print(
    "Grafiğe eklenen ilçeler ve senaryo puanları:"
)

print(
    ilk_5_ilce[
        [
            "İlçe",
            "Senaryo 70-30 Puanı",
            "Senaryo 60-40 Puanı",
            "Senaryo 50-50 Puanı",
            "Sıralama Kararlılığı",
        ]
    ].to_string(index=False)
)

print(
    f"\nGrafik kaydedildi: {grafik_yolu}"
)

