from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

veri_yolu = Path(
    "data/processed/ilce_oncelik_puanlari.csv"
)

grafik_yolu = Path(
    "frontend/assets/oncelikli_10_ilce.png"
)


# --------------------------------------------------
# VERİYİ OKU
# --------------------------------------------------

veri = pd.read_csv(veri_yolu)


# --------------------------------------------------
# İLK 10 İLÇEYİ SEÇ
# --------------------------------------------------

oncelikli_10_ilce = (
    veri
    .sort_values(
        by="Öncelik Puanı",
        ascending=False,
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
    oncelikli_10_ilce["İlçe"],
    oncelikli_10_ilce["Öncelik Puanı"],
)

ax.invert_yaxis()


# --------------------------------------------------
# DEĞERLERİ ÇUBUKLARIN YANINA YAZ
# --------------------------------------------------

for cubuk, deger in zip(
    cubuklar,
    oncelikli_10_ilce["Öncelik Puanı"],
):
    ax.text(
        cubuk.get_width() + 0.5,
        cubuk.get_y() + cubuk.get_height() / 2,
        f"{deger:.1f}",
        va="center",
    )


# --------------------------------------------------
# BAŞLIK VE EKSENLER
# --------------------------------------------------

ax.set_title(
    "Yeni Kütüphane Hizmet Noktası Açısından\n"
    "Öncelikli 10 İlçe"
)

ax.set_xlabel(
    "Öncelik Puanı"
)

ax.set_ylabel(
    "İlçe"
)

ax.set_xlim(
    0,
    105,
)

ax.grid(
    axis="x",
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


print("Grafiğe eklenen ilçeler:")

print(
    oncelikli_10_ilce[
        [
            "Öncelik Sırası",
            "İlçe",
            "Öncelik Puanı",
            "Öncelik Seviyesi",
        ]
    ].to_string(index=False)
)

print(
    f"\nGrafik kaydedildi: {grafik_yolu}"
)