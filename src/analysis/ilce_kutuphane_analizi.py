from pathlib import Path

import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

kutuphane_veri_yolu = Path(
    "data/processed/ibb_kutuphaneleri_temiz.csv"
)

nufus_veri_yolu = Path(
    "data/processed/ibb_2025_ilce_nufuslari.csv"
)

cikti_yolu = Path(
    "data/processed/ilce_kutuphane_analizi.csv"
)


# --------------------------------------------------
# VERİLERİ OKU
# --------------------------------------------------

kutuphane_verisi = pd.read_csv(
    kutuphane_veri_yolu
)

nufus_verisi = pd.read_csv(
    nufus_veri_yolu
)


# --------------------------------------------------
# İLK KONTROLLER
# --------------------------------------------------

print("Kütüphane verisi boyutu:")
print(kutuphane_verisi.shape)

print("\nNüfus verisi boyutu:")
print(nufus_verisi.shape)

print("\nKütüphane verisinin sütunları:")
print(kutuphane_verisi.columns.tolist())

print("\nNüfus verisinin sütunları:")
print(nufus_verisi.columns.tolist())

# --------------------------------------------------
# İLÇELERE GÖRE KÜTÜPHANE SAYISI
# --------------------------------------------------

ilce_kutuphane_sayilari = (
    kutuphane_verisi
    .groupby("İlçe Adı")
    .size()
    .reset_index(name="Kütüphane Sayısı")
)

ilce_kutuphane_sayilari = (
    ilce_kutuphane_sayilari
    .sort_values(
        by="Kütüphane Sayısı",
        ascending=False,
    )
    .reset_index(drop=True)
)

print("\nİlçelere göre kütüphane sayıları:")

print(
    ilce_kutuphane_sayilari
    .to_string(index=False)
)
# --------------------------------------------------
# NÜFUS VE KÜTÜPHANE VERİLERİNİ BİRLEŞTİR
# --------------------------------------------------

analiz_verisi = nufus_verisi.merge(
    ilce_kutuphane_sayilari,
    left_on="İlçe",
    right_on="İlçe Adı",
    how="left",
)

# Kütüphane kaydı bulunmayan ilçelerde oluşan
# boş değerleri 0 yap.
analiz_verisi["Kütüphane Sayısı"] = (
    analiz_verisi["Kütüphane Sayısı"]
    .fillna(0)
    .astype(int)
)

# Birleştirme sonrası gereksiz kalan sütunu kaldır.
analiz_verisi = analiz_verisi.drop(
    columns=["İlçe Adı"]
)

print("\nBirleştirilmiş veri boyutu:")
print(analiz_verisi.shape)

print("\nKütüphane kaydı bulunmayan ilçeler:")

print(
    analiz_verisi.loc[
        analiz_verisi["Kütüphane Sayısı"] == 0,
        ["İlçe", "Toplam Nüfus", "Kütüphane Sayısı"],
    ].to_string(index=False)
)


# --------------------------------------------------
# HİZMET ERİŞİM GÖSTERGELERİNİ HESAPLA
# --------------------------------------------------

analiz_verisi[
    "100 Bin Kişiye Düşen Kütüphane"
] = (
    analiz_verisi["Kütüphane Sayısı"]
    / analiz_verisi["Toplam Nüfus"]
    * 100_000
).round(3)


# Kütüphane sayısı 0 olan ilçelerde bölme yapılamaz.
# Bu nedenle 0 değerlerini geçici olarak boş değer yapıyoruz.
guvenli_kutuphane_sayisi = (
    analiz_verisi["Kütüphane Sayısı"]
    .where(
        analiz_verisi["Kütüphane Sayısı"] > 0
    )
)

analiz_verisi[
    "Bir Kütüphaneye Düşen Kişi"
] = (
    analiz_verisi["Toplam Nüfus"]
    / guvenli_kutuphane_sayisi
).round().astype("Int64")


# --------------------------------------------------
# SONUÇLARI SIRALA
# --------------------------------------------------

analiz_verisi = analiz_verisi.sort_values(
    by=[
        "100 Bin Kişiye Düşen Kütüphane",
        "Toplam Nüfus",
    ],
    ascending=[True, False],
).reset_index(drop=True)


print(
    "\n100 bin kişiye düşen kütüphane sayısı "
    "en düşük 15 ilçe:"
)

print(
    analiz_verisi[
        [
            "İlçe",
            "Toplam Nüfus",
            "Kütüphane Sayısı",
            "100 Bin Kişiye Düşen Kütüphane",
            "Bir Kütüphaneye Düşen Kişi",
        ]
    ]
    .head(15)
    .to_string(index=False)
)

# --------------------------------------------------
# VERİ DURUMUNU BELİRLE
# --------------------------------------------------

analiz_verisi["Veri Durumu"] = (
    "İBB veri setinde kayıt var"
)

analiz_verisi.loc[
    analiz_verisi["Kütüphane Sayısı"] == 0,
    "Veri Durumu",
] = "İBB veri setinde kayıt yok"
# --------------------------------------------------
# VERİ DURUMUNU BELİRLE
# --------------------------------------------------

analiz_verisi["Veri Durumu"] = (
    "İBB veri setinde kayıt var"
)

analiz_verisi.loc[
    analiz_verisi["Kütüphane Sayısı"] == 0,
    "Veri Durumu",
] = "İBB veri setinde kayıt yok"


# --------------------------------------------------
# KAYIT BULUNAN İLÇELERİ AYRI İNCELE
# --------------------------------------------------

kayit_bulunan_ilceler = analiz_verisi[
    analiz_verisi["Kütüphane Sayısı"] > 0
].copy()

kayit_bulunan_ilceler = (
    kayit_bulunan_ilceler
    .sort_values(
        by="100 Bin Kişiye Düşen Kütüphane",
        ascending=True,
    )
)

print(
    "\nİBB kütüphane kaydı bulunan ilçeler arasında "
    "hizmet oranı en düşük 10 ilçe:"
)

print(
    kayit_bulunan_ilceler[
        [
            "İlçe",
            "Toplam Nüfus",
            "Kütüphane Sayısı",
            "100 Bin Kişiye Düşen Kütüphane",
            "Bir Kütüphaneye Düşen Kişi",
        ]
    ]
    .head(10)
    .to_string(index=False)
    
)
# --------------------------------------------------
# ANALİZ TABLOSUNU KAYDET
# --------------------------------------------------

cikti_yolu.parent.mkdir(
    parents=True,
    exist_ok=True,
)

analiz_verisi.to_csv(
    cikti_yolu,
    index=False,
    encoding="utf-8-sig",
)

print(f"\nAnaliz dosyası kaydedildi: {cikti_yolu}")