from html import escape
from pathlib import Path

import folium
import pandas as pd
from folium.plugins import MarkerCluster

# Dosya yolları
veri_yolu = Path(
    "data/processed/ibb_kutuphaneleri_koordinatli.csv"
)

harita_yolu = Path(
    "frontend/kutuphane_haritasi.html"
)


# Koordinatlandırılmış veriyi oku
veri = pd.read_csv(veri_yolu)


# Nominatim tarafından döndürülen adresleri hazırla
bulunan_adres = veri["Bulunan Adres"].fillna("").astype(str)


# Dönen adresin bir kütüphane veya kitaplık kaydı
# içerip içermediğini kontrol et
kutuphane_eslesmesi = bulunan_adres.str.contains(
    r"kütüphane|kitaplık|kitaplığ|library",
    case=False,
    regex=True,
)


# Yalnızca koordinatı olan ve güvenilir görünen
# kayıtları haritada kullan
koordinatli_veri = veri[
    veri["Enlem"].notna()
    & veri["Boylam"].notna()
    & kutuphane_eslesmesi
].copy()


if koordinatli_veri.empty:
    raise ValueError(
        "Haritada gösterilecek koordinatlı kayıt bulunamadı."
    )


# Haritanın başlangıç merkezini noktaların ortalamasından hesapla
merkez_enlem = koordinatli_veri["Enlem"].mean()
merkez_boylam = koordinatli_veri["Boylam"].mean()


harita = folium.Map(
    location=[merkez_enlem, merkez_boylam],
    zoom_start=10,
    tiles="OpenStreetMap",
)


# İşaretçilerin ekleneceği kümeyi oluştur
isaretci_kumesi = MarkerCluster(
    name="Kütüphaneler"
).add_to(harita)


# Her kütüphane için haritaya bir işaretçi ekle
for _, satir in koordinatli_veri.iterrows():
    kutuphane_adi = escape(str(satir["Kütüphane Adı"]))
    ilce_adi = escape(str(satir["İlçe Adı"]))
    adres = escape(str(satir["Adres"]))
    calisma_saatleri = escape(str(satir["Çalışma Saatleri"]))
    calisma_gunleri = escape(str(satir["Çalışma Günleri"]))

    bilgi_kutusu = f"""
    <strong>{kutuphane_adi}</strong><br>
    İlçe: {ilce_adi}<br>
    Adres: {adres}<br>
    Çalışma saatleri: {calisma_saatleri}<br>
    Çalışma günleri: {calisma_gunleri}
    """

    folium.Marker(
        location=[
            satir["Enlem"],
            satir["Boylam"],
        ],
        tooltip=kutuphane_adi,
        popup=folium.Popup(
            bilgi_kutusu,
            max_width=350,
        ),
    ).add_to(isaretci_kumesi)


# Haritayı bütün işaretçiler görünecek şekilde ayarla
sinirlar = koordinatli_veri[
    ["Enlem", "Boylam"]
].values.tolist()

harita.fit_bounds(sinirlar)


# frontend klasörü yoksa oluştur
harita_yolu.parent.mkdir(
    parents=True,
    exist_ok=True,
)


# Haritayı HTML dosyası olarak kaydet
harita.save(harita_yolu)


print("Harita başarıyla oluşturuldu.")
print(f"Haritadaki kütüphane sayısı: {len(koordinatli_veri)}")
print(f"Harita dosyası: {harita_yolu}")