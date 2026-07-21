from pathlib import Path

import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

ham_veri_yolu = Path(
    "data/raw/ibb_nufus_bilgileri.xlsx"
)

cikti_yolu = Path(
    "data/processed/ibb_2025_ilce_nufuslari.csv"
)


# --------------------------------------------------
# EXCEL DOSYASINI OKU
# --------------------------------------------------

veri = pd.read_excel(
    ham_veri_yolu,
    sheet_name="Sheet0",
)


# --------------------------------------------------
# EN GÜNCEL YILI BUL
# --------------------------------------------------

en_guncel_yil = veri["Yıl"].max()

guncel_veri = veri[
    veri["Yıl"] == en_guncel_yil
].copy()


# --------------------------------------------------
# İLÇE ADLARINI TEMİZLE
# --------------------------------------------------

guncel_veri["İlçe"] = (
    guncel_veri["İlçe"]
    .astype(str)
    .str.strip()
)


# --------------------------------------------------
# ERKEK VE KADIN YAŞ SÜTUNLARINI BUL
# --------------------------------------------------

erkek_sutunlari = [
    sutun
    for sutun in guncel_veri.columns
    if str(sutun).startswith("Erkek")
]

kadin_sutunlari = [
    sutun
    for sutun in guncel_veri.columns
    if str(sutun).startswith("Kadın")
]


# --------------------------------------------------
# SAYISAL DEĞERLERE DÖNÜŞTÜR
# --------------------------------------------------

nufus_sutunlari = (
    erkek_sutunlari
    + kadin_sutunlari
)

guncel_veri[nufus_sutunlari] = (
    guncel_veri[nufus_sutunlari]
    .apply(
        pd.to_numeric,
        errors="coerce",
    )
    .fillna(0)
)


# --------------------------------------------------
# TOPLAM NÜFUSLARI HESAPLA
# --------------------------------------------------

guncel_veri["Erkek Nüfus"] = (
    guncel_veri[erkek_sutunlari]
    .sum(axis=1)
    .astype(int)
)

guncel_veri["Kadın Nüfus"] = (
    guncel_veri[kadin_sutunlari]
    .sum(axis=1)
    .astype(int)
)

guncel_veri["Toplam Nüfus"] = (
    guncel_veri["Erkek Nüfus"]
    + guncel_veri["Kadın Nüfus"]
)


# --------------------------------------------------
# SADE TABLOYU OLUŞTUR
# --------------------------------------------------

ilce_nufuslari = guncel_veri[
    [
        "Yıl",
        "İlçe",
        "ilce_kodu",
        "Erkek Nüfus",
        "Kadın Nüfus",
        "Toplam Nüfus",
    ]
].copy()


ilce_nufuslari = ilce_nufuslari.sort_values(
    by="İlçe"
).reset_index(drop=True)


# --------------------------------------------------
# KONTROLLER
# --------------------------------------------------

if len(ilce_nufuslari) != 39:
    print(
        "UYARI: Güncel yılda 39 ilçe bulunamadı."
    )

if ilce_nufuslari["İlçe"].duplicated().any():
    print(
        "UYARI: Tekrarlanan ilçe kayıtları var."
    )


# --------------------------------------------------
# DOSYAYI KAYDET
# --------------------------------------------------

cikti_yolu.parent.mkdir(
    parents=True,
    exist_ok=True,
)

ilce_nufuslari.to_csv(
    cikti_yolu,
    index=False,
    encoding="utf-8-sig",
)


# --------------------------------------------------
# SONUÇLARI GÖSTER
# --------------------------------------------------

print(f"Kullanılan yıl: {en_guncel_yil}")

print(
    f"İlçe sayısı: "
    f"{len(ilce_nufuslari)}"
)

print(
    f"İstanbul toplam nüfusu: "
    f"{ilce_nufuslari['Toplam Nüfus'].sum():,}"
)

print("\nNüfusu en yüksek 10 ilçe:")

print(
    ilce_nufuslari[
        ["İlçe", "Toplam Nüfus"]
    ]
    .sort_values(
        by="Toplam Nüfus",
        ascending=False,
    )
    .head(10)
    .to_string(index=False)
)

print(
    f"\nDosya kaydedildi: {cikti_yolu}"
)