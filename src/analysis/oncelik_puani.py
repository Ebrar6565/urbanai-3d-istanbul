from pathlib import Path

import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

analiz_veri_yolu = Path(
    "data/processed/ilce_kutuphane_analizi.csv"
)

cikti_yolu = Path(
    "data/processed/ilce_oncelik_puanlari.csv"
)


# --------------------------------------------------
# ANALİZ VERİSİNİ OKU
# --------------------------------------------------

analiz_verisi = pd.read_csv(
    analiz_veri_yolu
)



# --------------------------------------------------
# İLÇELERİ VERİ DURUMUNA GÖRE AYIR
# --------------------------------------------------

kayit_bulunan_ilceler = analiz_verisi[
    analiz_verisi["Kütüphane Sayısı"] > 0
].copy()

dogrulama_gereken_ilceler = analiz_verisi[
    analiz_verisi["Kütüphane Sayısı"] == 0
].copy()


# --------------------------------------------------
# İLK KONTROLLER
# --------------------------------------------------

print(
    f"Toplam ilçe sayısı: "
    f"{len(analiz_verisi)}"
)

print(
    f"Kütüphane kaydı bulunan ilçe sayısı: "
    f"{len(kayit_bulunan_ilceler)}"
)

print(
    f"Veri doğrulaması gereken ilçe sayısı: "
    f"{len(dogrulama_gereken_ilceler)}"
)

print(
    "\nVeri doğrulaması gereken ilçeler:"
)

print(
    dogrulama_gereken_ilceler[
        [
            "İlçe",
            "Toplam Nüfus",
            "Kütüphane Sayısı",
        ]
    ].to_string(index=False)
)

# --------------------------------------------------
# MİN-MAX NORMALİZASYONU
# --------------------------------------------------

def min_max_puani(seri):
    en_dusuk = seri.min()
    en_yuksek = seri.max()

    if en_yuksek == en_dusuk:
        return pd.Series(
            0,
            index=seri.index,
            dtype=float,
        )

    return (
        (seri - en_dusuk)
        / (en_yuksek - en_dusuk)
        * 100
    )


# Nüfusu yüksek ilçelerin puanı daha yüksek olur.
kayit_bulunan_ilceler["Nüfus Puanı"] = (
    min_max_puani(
        kayit_bulunan_ilceler["Toplam Nüfus"]
    )
)


# Hizmet oranı düşük ilçelerin ihtiyaç puanı
# daha yüksek olmalıdır.
hizmet_orani_puani = min_max_puani(
    kayit_bulunan_ilceler[
        "100 Bin Kişiye Düşen Kütüphane"
    ]
)

kayit_bulunan_ilceler["Hizmet Açığı Puanı"] = (
    100 - hizmet_orani_puani
)


# Sonuçları üç basamağa yuvarla.
kayit_bulunan_ilceler[
    ["Nüfus Puanı", "Hizmet Açığı Puanı"]
] = (
    kayit_bulunan_ilceler[
        ["Nüfus Puanı", "Hizmet Açığı Puanı"]
    ]
    .round(3)
)


# --------------------------------------------------
# NORMALİZASYON SONUÇLARINI GÖSTER
# --------------------------------------------------

print(
    "\nNüfus ve hizmet açığı puanları:"
)

print(
    kayit_bulunan_ilceler[
        [
            "İlçe",
            "Toplam Nüfus",
            "100 Bin Kişiye Düşen Kütüphane",
            "Nüfus Puanı",
            "Hizmet Açığı Puanı",
        ]
    ]
    .sort_values(
        by="Hizmet Açığı Puanı",
        ascending=False,
    )
    .head(10)
    .to_string(index=False)
)

# --------------------------------------------------
# ÖNCELİK PUANINI HESAPLA
# --------------------------------------------------

hizmet_acigi_agirligi = 0.60
nufus_agirligi = 0.40

kayit_bulunan_ilceler["Öncelik Puanı"] = (
    kayit_bulunan_ilceler["Hizmet Açığı Puanı"]
    * hizmet_acigi_agirligi
    +
    kayit_bulunan_ilceler["Nüfus Puanı"]
    * nufus_agirligi
).round(3)


# --------------------------------------------------
# ÖNCELİK SIRASINI OLUŞTUR
# --------------------------------------------------

kayit_bulunan_ilceler = (
    kayit_bulunan_ilceler
    .sort_values(
        by="Öncelik Puanı",
        ascending=False,
    )
    .reset_index(drop=True)
)

kayit_bulunan_ilceler["Öncelik Sırası"] = (
    kayit_bulunan_ilceler.index + 1
)


# --------------------------------------------------
# ÖNCELİK SEVİYESİNİ BELİRLE
# --------------------------------------------------

kayit_bulunan_ilceler["Öncelik Seviyesi"] = (
    "Düşük"
)

kayit_bulunan_ilceler.loc[
    kayit_bulunan_ilceler["Öncelik Puanı"] >= 60,
    "Öncelik Seviyesi",
] = "Orta"

kayit_bulunan_ilceler.loc[
    kayit_bulunan_ilceler["Öncelik Puanı"] >= 80,
    "Öncelik Seviyesi",
] = "Yüksek"


# --------------------------------------------------
# SONUÇLARI GÖSTER
# --------------------------------------------------

print(
    "\nYeni kütüphane hizmet noktası açısından "
    "öncelikli 10 ilçe:"
)

print(
    kayit_bulunan_ilceler[
        [
            "Öncelik Sırası",
            "İlçe",
            "Toplam Nüfus",
            "Kütüphane Sayısı",
            "Nüfus Puanı",
            "Hizmet Açığı Puanı",
            "Öncelik Puanı",
            "Öncelik Seviyesi",
        ]
    ]
    .head(10)
    .to_string(index=False)
)



# --------------------------------------------------
# ÖNCELİK PUANLARINI KAYDET
# --------------------------------------------------

kaydedilecek_sutunlar = [
    "Öncelik Sırası",
    "İlçe",
    "Toplam Nüfus",
    "Kütüphane Sayısı",
    "100 Bin Kişiye Düşen Kütüphane",
    "Bir Kütüphaneye Düşen Kişi",
    "Nüfus Puanı",
    "Hizmet Açığı Puanı",
    "Öncelik Puanı",
    "Öncelik Seviyesi",
]

oncelik_sonuclari = kayit_bulunan_ilceler[
    kaydedilecek_sutunlar
].copy()

cikti_yolu.parent.mkdir(
    parents=True,
    exist_ok=True,
)

oncelik_sonuclari.to_csv(
    cikti_yolu,
    index=False,
    encoding="utf-8-sig",
)

print(
    f"\nÖncelik puanları kaydedildi: {cikti_yolu}"
)