from html import escape
from pathlib import Path

import folium
import pandas as pd
from folium.plugins import MarkerCluster, Search


# --------------------------------------------------
# 1. DOSYA YOLLARI
# --------------------------------------------------

veri_yolu = Path(
    "data/processed/ibb_kutuphaneleri_koordinatli.csv"
)

harita_yolu = Path(
    "frontend/kutuphane_haritasi.html"
)


# --------------------------------------------------
# 2. KOORDİNATLI VERİYİ OKU
# --------------------------------------------------

veri = pd.read_csv(veri_yolu)


# --------------------------------------------------
# 3. GÜVENİLİR KOORDİNATLARI SEÇ
# --------------------------------------------------

# Nominatim tarafından döndürülen adresleri
# boş değerlerden arındırarak metne dönüştür.
bulunan_adres = (
    veri["Bulunan Adres"]
    .fillna("")
    .astype(str)
)


# Bulunan adresin gerçekten kütüphane veya
# kitaplık kaydına benzeyip benzemediğini kontrol et.
kutuphane_eslesmesi = bulunan_adres.str.contains(
    r"kütüphane|kitaplık|kitaplığ|library",
    case=False,
    regex=True,
)


# Haritada yalnızca:
# - enlemi bulunan,
# - boylamı bulunan,
# - güvenilir görünen
# kayıtları kullan.
koordinatli_veri = veri[
    veri["Enlem"].notna()
    & veri["Boylam"].notna()
    & kutuphane_eslesmesi
].copy()


# Hiç uygun kayıt kalmamışsa programı anlaşılır
# bir hata mesajıyla durdur.
if koordinatli_veri.empty:
    raise ValueError(
        "Haritada gösterilecek güvenilir koordinatlı "
        "kayıt bulunamadı."
    )


# --------------------------------------------------
# 4. HARİTANIN MERKEZİNİ HESAPLA
# --------------------------------------------------

merkez_enlem = koordinatli_veri["Enlem"].mean()
merkez_boylam = koordinatli_veri["Boylam"].mean()


# --------------------------------------------------
# 5. TEMEL HARİTAYI OLUŞTUR
# --------------------------------------------------

harita = folium.Map(
    location=[
        merkez_enlem,
        merkez_boylam,
    ],
    zoom_start=10,
    tiles="OpenStreetMap",
)


# --------------------------------------------------
# 6. MARKER CLUSTER OLUŞTUR
# --------------------------------------------------

# Görünen mavi işaretçiler bu kümenin
# içerisinde tutulacak.
isaretci_kumesi = MarkerCluster(
    name="Kütüphaneler"
).add_to(harita)


# --------------------------------------------------
# 7. ARAMA İÇİN BOŞ GEOJSON LİSTESİ
# --------------------------------------------------

# Arama kutusunun kullanacağı bütün kütüphane
# kayıtlarını bu listede toplayacağız.
arama_ozellikleri = []


# --------------------------------------------------
# 8. KÜTÜPHANELERİ HARİTAYA EKLE
# --------------------------------------------------

for _, satir in koordinatli_veri.iterrows():

    # Aramada kullanılacak ham isim.
    # HTML escape uygulanmıyor çünkü bu değer
    # HTML olarak gösterilmeyecek.
    kutuphane_adi_ham = str(
        satir["Kütüphane Adı"]
    ).strip()

    # Bilgi kutusunda gösterilecek metinleri
    # güvenli HTML biçimine dönüştür.
    kutuphane_adi = escape(
        kutuphane_adi_ham
    )

    ilce_adi = escape(
        str(satir["İlçe Adı"])
    )

    adres = escape(
        str(satir["Adres"])
    )

    calisma_saatleri = escape(
        str(satir["Çalışma Saatleri"])
    )

    calisma_gunleri = escape(
        str(satir["Çalışma Günleri"])
    )


    # Marker tıklandığında açılacak bilgi kutusu.
    bilgi_kutusu = f"""
    <strong>{kutuphane_adi}</strong><br>
    İlçe: {ilce_adi}<br>
    Adres: {adres}<br>
    Çalışma saatleri: {calisma_saatleri}<br>
    Çalışma günleri: {calisma_gunleri}
    """


    # ----------------------------------------------
    # GÖRÜNEN KÜTÜPHANE İŞARETÇİSİ
    # ----------------------------------------------

    folium.Marker(
        location=[
            float(satir["Enlem"]),
            float(satir["Boylam"]),
        ],
        tooltip=kutuphane_adi,
        popup=folium.Popup(
            bilgi_kutusu,
            max_width=350,
        ),
    ).add_to(isaretci_kumesi)


    # ----------------------------------------------
    # ARAMA İÇİN GEOJSON KAYDI
    # ----------------------------------------------

    arama_ozellikleri.append(
        {
            "type": "Feature",

            "geometry": {
                "type": "Point",

                # GeoJSON'da koordinat sıralaması:
                # önce boylam, sonra enlem.
                "coordinates": [
                    float(satir["Boylam"]),
                    float(satir["Enlem"]),
                ],
            },

            "properties": {
                "kutuphane_adi": kutuphane_adi_ham,
            },
        }
    )


# --------------------------------------------------
# 9. ARAMA GEOJSON KATMANINI OLUŞTUR
# --------------------------------------------------

arama_verisi = {
    "type": "FeatureCollection",
    "features": arama_ozellikleri,
}


# Arama noktaları haritada görünmesin diye
# tamamen saydam CircleMarker kullanıyoruz.
arama_geojson = folium.GeoJson(
    data=arama_verisi,
    name="Kütüphane Arama Verisi",
    marker=folium.CircleMarker(
        radius=1,
        opacity=0,
        fill=True,
        fill_opacity=0,
    ),
).add_to(harita)


# --------------------------------------------------
# 10. ARAMA KUTUSUNU EKLE
# --------------------------------------------------

Search(
    layer=arama_geojson,

    # GeoJSON properties içindeki alan adı.
    search_label="kutuphane_adi",

    # Aranan nesneler nokta geometrisidir.
    geom_type="Point",

    # Sonuç seçildiğinde yakınlaşma seviyesi.
    search_zoom=16,

    placeholder="Kütüphane ara...",

    # Arama kutusu başlangıçta açık görünsün.
    collapsed=False,
).add_to(harita)


# --------------------------------------------------
# 11. HARİTAYI BÜTÜN NOKTALARA SIĞDIR
# --------------------------------------------------

sinirlar = koordinatli_veri[
    ["Enlem", "Boylam"]
].values.tolist()

harita.fit_bounds(sinirlar)


# --------------------------------------------------
# 12. HARİTAYI HTML OLARAK KAYDET
# --------------------------------------------------

harita_yolu.parent.mkdir(
    parents=True,
    exist_ok=True,
)

harita.save(harita_yolu)


# --------------------------------------------------
# 13. TERMINAL BİLGİLERİ
# --------------------------------------------------

print("Harita başarıyla oluşturuldu.")

print(
    f"Haritadaki kütüphane sayısı: "
    f"{len(koordinatli_veri)}"
)

print(
    f"Arama sistemindeki kayıt sayısı: "
    f"{len(arama_ozellikleri)}"
)

print(
    f"Harita dosyası: {harita_yolu}"
)