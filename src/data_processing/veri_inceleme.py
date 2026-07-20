from pathlib import Path

import pandas as pd


dosya_yolu = Path("data/raw/ibb_kutuphaneleri.xlsx")

veri = pd.read_excel(dosya_yolu)


print("\n=== İLK 5 SATIR ===")
print(veri.head().to_string(index=False))


print("\n=== VERİ SETİNİN BOYUTU ===")
print(f"Satır sayısı: {veri.shape[0]}")
print(f"Sütun sayısı: {veri.shape[1]}")


print("\n=== SÜTUN İSİMLERİ ===")
for sira, sutun in enumerate(veri.columns, start=1):
    print(f"{sira}. {sutun}")


print("\n=== SÜTUNLARIN VERİ TİPLERİ ===")
print(veri.dtypes)


print("\n=== EKSİK DEĞER SAYILARI ===")
print(veri.isna().sum())


print("\n=== TEKRAR EDEN SATIR SAYISI ===")
print(veri.duplicated().sum())
print("\n=== EKSİK ÇALIŞMA BİLGİSİ OLAN KAYITLAR ===")

eksik_calisma_bilgileri = veri[
    veri[["Çalışma Saatleri", "Çalışma Günleri"]]
    .isna()
    .any(axis=1)
]

print(
    eksik_calisma_bilgileri[
        [
            "Kütüphane Adı",
            "İlçe Adı",
            "Çalışma Saatleri",
            "Çalışma Günleri",
        ]
    ].to_string(index=False)
)


print("\n=== TEKRAR EDEN SATIRLAR ===")

tekrar_edenler = veri[veri.duplicated(keep=False)]

print(f"Tekrar eden satır sayısı: {len(tekrar_edenler)}")

if tekrar_edenler.empty:
    print("Tamamen aynı olan tekrar eden satır bulunmuyor.")
else:
    print(tekrar_edenler.to_string(index=False))


print("\n=== İLÇELERE GÖRE KÜTÜPHANE SAYILARI ===")

ilce_sayilari = veri["İlçe Adı"].value_counts()

print(ilce_sayilari.to_string())