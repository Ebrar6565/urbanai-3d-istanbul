from pathlib import Path

import pandas as pd


# Proje içerisindeki dosya yolları
ham_veri_yolu = Path("data/raw/ibb_kutuphaneleri.xlsx")
temiz_veri_yolu = Path("data/processed/ibb_kutuphaneleri_temiz.csv")


# Ham Excel verisini oku
veri = pd.read_excel(ham_veri_yolu)


# Sütun adlarının başındaki ve sonundaki boşlukları kaldır
veri.columns = veri.columns.str.strip()


# Metin içeren sütunlar
metin_sutunlari = [
    "Kütüphane Adı",
    "İlçe Adı",
    "Adres",
    "Telefon",
    "Çalışma Saatleri",
    "Çalışma Günleri",
]


# Metin sütunlarındaki gereksiz boşlukları temizle
for sutun in metin_sutunlari:
    veri[sutun] = veri[sutun].astype("string").str.strip()


# Telefon numaralarındaki satır sonlarını daha okunabilir hale getir
veri["Telefon"] = veri["Telefon"].str.replace(
    r"[\r\n]+",
    " / ",
    regex=True,
)


# Aynı ilçenin farklı yazımlarını standartlaştır
ilce_duzeltmeleri = {
    "K.Çekmece": "Küçükçekmece",
}

veri["İlçe Adı"] = veri["İlçe Adı"].replace(ilce_duzeltmeleri)


# Çalışma bilgisi eksik olan kayıtları işaretle
veri["Çalışma Bilgisi Eksik"] = veri[
    ["Çalışma Saatleri", "Çalışma Günleri"]
].isna().any(axis=1)


# Eksik çalışma bilgilerini anlaşılır bir ifadeyle doldur
veri["Çalışma Saatleri"] = veri["Çalışma Saatleri"].fillna("Bilinmiyor")
veri["Çalışma Günleri"] = veri["Çalışma Günleri"].fillna("Bilinmiyor")


# Varsa tamamen aynı tekrar eden satırları kaldır
veri = veri.drop_duplicates()


# Veriyi ilçe ve kütüphane adına göre sırala
veri = veri.sort_values(
    by=["İlçe Adı", "Kütüphane Adı"]
).reset_index(drop=True)


# Çıktı klasörü yoksa oluştur
temiz_veri_yolu.parent.mkdir(parents=True, exist_ok=True)


# Temiz veriyi CSV dosyası olarak kaydet
veri.to_csv(
    temiz_veri_yolu,
    index=False,
    encoding="utf-8-sig",
)


print("Veri temizleme tamamlandı.")
print(f"Toplam kayıt sayısı: {len(veri)}")
print(f"Çıktı dosyası: {temiz_veri_yolu}")

print("\nİlçelere göre temizlenmiş kütüphane sayıları:")
print(veri["İlçe Adı"].value_counts().to_string())

print("\nÇalışma bilgisi eksik kayıt sayısı:")
print(veri["Çalışma Bilgisi Eksik"].sum())