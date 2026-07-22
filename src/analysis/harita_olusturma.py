from html import escape
from pathlib import Path
import sqlite3

import folium

from branca.element import Element
from folium.plugins import MarkerCluster, Search


# --------------------------------------------------
# 1. DOSYA YOLLARI
# --------------------------------------------------

veritabani_yolu = Path(
    "data/database/urbanai.db"
)

harita_yolu = Path(
    "frontend/kutuphane_haritasi.html"
)


# --------------------------------------------------
# 2. VERİ TABANI BAĞLANTISI
# --------------------------------------------------

def baglanti_olustur():
    """
    UrbanAI SQLite veri tabanına bağlantı oluşturur.
    """

    if not veritabani_yolu.exists():
        raise FileNotFoundError(
            "Veri tabanı bulunamadı: "
            f"{veritabani_yolu}\n"
            "Önce veri tabanı oluşturma ve veri "
            "aktarma dosyalarını çalıştırın."
        )

    baglanti = sqlite3.connect(
        veritabani_yolu
    )

    # Sorgu sonuçlarındaki sütunlara
    # isimleriyle erişmemizi sağlar.
    baglanti.row_factory = sqlite3.Row

    baglanti.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return baglanti


# --------------------------------------------------
# 3. GÜVENİLİR KÜTÜPHANELERİ GETİR
# --------------------------------------------------

def guvenilir_kutuphaneleri_getir(
    baglanti
):
    """
    Veri tabanından yalnızca güvenilir ve
    koordinatı bulunan kütüphaneleri getirir.
    """

    sonuclar = baglanti.execute(
        """
        SELECT
            facilities.id,

            facilities.name
                AS kutuphane_adi,

            districts.name
                AS ilce_adi,

            facilities.address,

            facilities.working_hours,

            facilities.working_days,

            facilities.latitude,

            facilities.longitude,

            facilities.coordinate_status

        FROM facilities

        INNER JOIN districts
            ON districts.id =
               facilities.district_id

        INNER JOIN service_types
            ON service_types.id =
               facilities.service_type_id

        WHERE service_types.name = ?

          AND facilities.coordinate_status =
              'verified'

          AND facilities.latitude IS NOT NULL

          AND facilities.longitude IS NOT NULL

        ORDER BY facilities.name;
        """,
        (
            "Kütüphane",
        ),
    ).fetchall()

    if not sonuclar:
        raise ValueError(
            "Haritada gösterilecek güvenilir "
            "koordinatlı kütüphane bulunamadı."
        )

    return sonuclar


# --------------------------------------------------
# 4. BOŞ METİNLERİ DÜZENLE
# --------------------------------------------------

def metni_hazirla(
    deger,
    varsayilan="Bilgi bulunamadı",
):
    """
    None ve boş metinleri okunabilir bir
    açıklamaya dönüştürür.
    """

    if deger is None:
        return varsayilan

    temiz_deger = str(deger).strip()

    if temiz_deger == "":
        return varsayilan

    return temiz_deger


# --------------------------------------------------
# 5. ANA ÇALIŞMA AKIŞI
# --------------------------------------------------

def main():

    # ----------------------------------------------
    # VERİ TABANINDAN VERİYİ AL
    # ----------------------------------------------

    with baglanti_olustur() as baglanti:

        kutuphaneler = (
            guvenilir_kutuphaneleri_getir(
                baglanti
            )
        )


    # ----------------------------------------------
    # HARİTANIN MERKEZİNİ HESAPLA
    # ----------------------------------------------

    merkez_enlem = sum(
        float(
            kutuphane["latitude"]
        )
        for kutuphane in kutuphaneler
    ) / len(kutuphaneler)


    merkez_boylam = sum(
        float(
            kutuphane["longitude"]
        )
        for kutuphane in kutuphaneler
    ) / len(kutuphaneler)


    # ----------------------------------------------
    # TEMEL HARİTAYI OLUŞTUR
    # ----------------------------------------------

    harita = folium.Map(
        location=[
            merkez_enlem,
            merkez_boylam,
        ],

        zoom_start=10,

        tiles="OpenStreetMap",
    )


    # ----------------------------------------------
    # MARKER CLUSTER OLUŞTUR
    # ----------------------------------------------

    isaretci_kumesi = MarkerCluster(
        name="Kütüphaneler"
    ).add_to(harita)


    # ----------------------------------------------
    # ARAMA İÇİN GEOJSON LİSTESİ
    # ----------------------------------------------

    arama_ozellikleri = []


    # ----------------------------------------------
    # KÜTÜPHANELERİ HARİTAYA EKLE
    # ----------------------------------------------

    for kutuphane in kutuphaneler:

        # Arama sisteminde kullanılacak ham isim.
        kutuphane_adi_ham = metni_hazirla(
            kutuphane["kutuphane_adi"],
            "İsimsiz kütüphane",
        )


        # Bilgi kutusunda gösterilecek metinleri
        # HTML açısından güvenli hâle getir.
        kutuphane_adi = escape(
            kutuphane_adi_ham
        )

        ilce_adi = escape(
            metni_hazirla(
                kutuphane["ilce_adi"]
            )
        )

        adres = escape(
            metni_hazirla(
                kutuphane["address"]
            )
        )

        calisma_saatleri = escape(
            metni_hazirla(
                kutuphane["working_hours"]
            )
        )

        calisma_gunleri = escape(
            metni_hazirla(
                kutuphane["working_days"]
            )
        )


        enlem = float(
            kutuphane["latitude"]
        )

        boylam = float(
            kutuphane["longitude"]
        )


        # ------------------------------------------
        # TIKLANDIĞINDA AÇILACAK BİLGİ KUTUSU
        # ------------------------------------------

        bilgi_kutusu = f"""
        <div style="
            font-family: Arial, Helvetica, sans-serif;
            min-width: 230px;
        ">
            <strong>{kutuphane_adi}</strong>
            <br><br>

            <b>İlçe:</b>
            {ilce_adi}
            <br>

            <b>Adres:</b>
            {adres}
            <br>

            <b>Çalışma saatleri:</b>
            {calisma_saatleri}
            <br>

            <b>Çalışma günleri:</b>
            {calisma_gunleri}
        </div>
        """


        # ------------------------------------------
        # GÖRÜNEN KÜTÜPHANE İŞARETÇİSİ
        # ------------------------------------------

        folium.Marker(
            location=[
                enlem,
                boylam,
            ],

            tooltip=kutuphane_adi,

            popup=folium.Popup(
                bilgi_kutusu,
                max_width=350,
            ),
        ).add_to(
            isaretci_kumesi
        )


        # ------------------------------------------
        # ARAMA İÇİN GEOJSON KAYDI
        # ------------------------------------------

        arama_ozellikleri.append(
            {
                "type": "Feature",

                "geometry": {
                    "type": "Point",

                    # GeoJSON koordinat sırası:
                    # önce boylam, sonra enlem.
                    "coordinates": [
                        boylam,
                        enlem,
                    ],
                },

                "properties": {
                    "kutuphane_adi": (
                        kutuphane_adi_ham
                    ),
                },
            }
        )


    # ----------------------------------------------
    # ARAMA GEOJSON VERİSİ
    # ----------------------------------------------

    arama_verisi = {
        "type": "FeatureCollection",
        "features": arama_ozellikleri,
    }


    # Arama noktalarını görünmez yapıyoruz.
    # Gerçek görünen işaretçiler MarkerCluster
    # katmanında bulunuyor.
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


    # ----------------------------------------------
    # ARAMA KUTUSUNU EKLE
    # ----------------------------------------------

    Search(
        layer=arama_geojson,

        search_label="kutuphane_adi",

        geom_type="Point",

        search_zoom=16,

        placeholder="Kütüphane ara...",

        collapsed=False,
    ).add_to(harita)


    # ----------------------------------------------
    # HARİTAYI BÜTÜN NOKTALARA SIĞDIR
    # ----------------------------------------------

    sinirlar = [
        [
            float(
                kutuphane["latitude"]
            ),

            float(
                kutuphane["longitude"]
            ),
        ]

        for kutuphane
        in kutuphaneler
    ]


    harita.fit_bounds(
        sinirlar
    )


    # ----------------------------------------------
    # ANA SAYFAYA DÖN BUTONU
    # ----------------------------------------------

    ana_sayfa_butonu = """
    <a
        id="urbanai-ana-sayfa-butonu"
        href="index.html"
    >
        <span>←</span>
        Ana sayfaya dön
    </a>

    <style>
        #urbanai-ana-sayfa-butonu {
            position: fixed;
            top: 18px;
            right: 18px;
            z-index: 10000;

            display: inline-flex;
            align-items: center;
            gap: 8px;

            padding: 11px 15px;

            border:
                1px solid
                rgba(255, 255, 255, 0.22);

            border-radius: 10px;

            color: white;

            background:
                rgba(22, 27, 34, 0.92);

            font-family:
                Arial,
                Helvetica,
                sans-serif;

            font-size: 13px;
            font-weight: 700;

            text-decoration: none;

            box-shadow:
                0 4px 16px
                rgba(0, 0, 0, 0.25);

            backdrop-filter: blur(8px);

            transition:
                background 0.18s ease,
                transform 0.18s ease;
        }

        #urbanai-ana-sayfa-butonu:hover {
            background:
                rgba(35, 95, 159, 0.96);

            transform:
                translateY(-2px);
        }

        @media (max-width: 600px) {
            #urbanai-ana-sayfa-butonu {
                top: 10px;
                right: 10px;

                padding: 9px 12px;

                font-size: 11px;
            }
        }
    </style>
    """


    harita.get_root().html.add_child(
        Element(
            ana_sayfa_butonu
        )
    )


    # ----------------------------------------------
    # HARİTAYI HTML OLARAK KAYDET
    # ----------------------------------------------

    harita_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    harita.save(
        harita_yolu
    )


    # ----------------------------------------------
    # TERMINAL BİLGİLERİ
    # ----------------------------------------------

    print(
        "2D kütüphane haritası "
        "başarıyla oluşturuldu."
    )

    print(
        "Veri kaynağı: "
        "data/database/urbanai.db"
    )

    print(
        f"Haritadaki güvenilir kütüphane: "
        f"{len(kutuphaneler)}"
    )

    print(
        f"Arama sistemindeki kayıt sayısı: "
        f"{len(arama_ozellikleri)}"
    )

    print(
        f"Harita dosyası: "
        f"{harita_yolu}"
    )


if __name__ == "__main__":
    main()