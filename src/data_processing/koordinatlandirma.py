from pathlib import Path

import pandas as pd
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim


# Dosya yolları
girdi_yolu = Path(
    "data/processed/ibb_kutuphaneleri_temiz.csv"
)

cikti_yolu = Path(
    "data/processed/ibb_kutuphaneleri_koordinatli.csv"
)


# Daha önce oluşturulmuş koordinatlı dosya varsa onu aç.
# Böylece program tekrar çalıştırıldığında eski sonuçlar kaybolmaz.
if cikti_yolu.exists():
    veri = pd.read_csv(cikti_yolu)
    print("Daha önce kaydedilmiş koordinatlandırma sonuçları açıldı.")
else:
    veri = pd.read_csv(girdi_yolu)

    veri["Enlem"] = float("nan")
    veri["Boylam"] = float("nan")
    veri["Koordinat Sorgusu"] = pd.NA
    veri["Bulunan Adres"] = pd.NA


# Nominatim bağlantısı
geolocator = Nominatim(
    user_agent=(
        "urbanai-3d-istanbul/1.0 "
        "(github.com/Ebrar6565/urbanai-3d-istanbul)"
    )
)


# İstekler arasında en az 1,1 saniye bekle
geocode = RateLimiter(
    geolocator.geocode,
    min_delay_seconds=1.1,
    max_retries=2,
    error_wait_seconds=5,
    swallow_exceptions=True,
)


# Henüz koordinatı bulunmamış kayıtları seç
eksik_koordinatlar = veri[
    veri["Enlem"].isna() | veri["Boylam"].isna()
]

# Koordinatı eksik olan bütün kayıtları işle
islenilecek_kayitlar = eksik_koordinatlar


for indeks, satir in islenilecek_kayitlar.iterrows():
    kutuphane_adi = satir["Kütüphane Adı"]
    ilce_adi = satir["İlçe Adı"]

    sorgu = (
        f"{kutuphane_adi}, "
        f"{ilce_adi}, İstanbul, Türkiye"
    )

    print(f"\nAranıyor: {sorgu}")

    konum = geocode(
        sorgu,
        language="tr",
        country_codes="tr",
        timeout=10,
    )

    # Kütüphane adıyla bulunamazsa açık adresi dene
    if konum is None:
        sorgu = (
            f"{satir['Adres']}, "
            f"{ilce_adi}, İstanbul, Türkiye"
        )

        print(f"İkinci sorgu deneniyor: {sorgu}")

        konum = geocode(
            sorgu,
            language="tr",
            country_codes="tr",
            timeout=10,
        )

    veri.at[indeks, "Koordinat Sorgusu"] = sorgu

    if konum is None:
        print("Koordinat bulunamadı.")
    else:
        veri.at[indeks, "Enlem"] = konum.latitude
        veri.at[indeks, "Boylam"] = konum.longitude
        veri.at[indeks, "Bulunan Adres"] = konum.address

        print(f"Bulundu: {konum.latitude}, {konum.longitude}")
        print(f"Adres: {konum.address}")

    # Her kayıttan sonra sonucu sakla.
    # Program yarıda kapanırsa bulunan sonuçlar kaybolmaz.
    veri.to_csv(
        cikti_yolu,
        index=False,
        encoding="utf-8-sig",
    )


bulunan_sayi = veri["Enlem"].notna().sum()

print("\nKoordinatlandırma testi tamamlandı.")
print(f"Koordinatı bulunan toplam kayıt: {bulunan_sayi}")
print(f"Çıktı dosyası: {cikti_yolu}")