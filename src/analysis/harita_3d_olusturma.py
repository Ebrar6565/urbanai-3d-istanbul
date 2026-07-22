from pathlib import Path
import json
import sqlite3

import pydeck as pdk


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

veritabani_yolu = Path(
    "data/database/urbanai.db"
)

harita_cikti_yolu = Path(
    "frontend/kutuphane_oncelik_haritasi_3d.html"
)


# --------------------------------------------------
# VERİ TABANI BAĞLANTISI
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

    # SQL sonuçlarındaki sütunlara isimleriyle
    # erişmemizi sağlar.
    baglanti.row_factory = sqlite3.Row

    baglanti.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return baglanti


# --------------------------------------------------
# KÜTÜPHANE HİZMET TÜRÜ ID'SİNİ GETİR
# --------------------------------------------------

def kutuphane_hizmet_turu_id_getir(
    baglanti
):
    """
    service_types tablosundaki Kütüphane
    hizmet türünün veri tabanı kimliğini getirir.
    """

    sonuc = baglanti.execute(
        """
        SELECT id
        FROM service_types
        WHERE name = ?;
        """,
        (
            "Kütüphane",
        ),
    ).fetchone()

    if sonuc is None:
        raise ValueError(
            "Veri tabanında Kütüphane hizmet "
            "türü bulunamadı."
        )

    return sonuc["id"]


# --------------------------------------------------
# ÖNCELİK SEVİYESİNE GÖRE RENK BELİRLE
# --------------------------------------------------

def oncelik_rengi_belirle(
    oncelik_seviyesi,
    oncelik_puani,
):
    """
    İlçe alanında kullanılacak RGBA rengini döndürür.
    """

    # Öncelik puanı hesaplanmamış ilçeler gri.
    if oncelik_puani is None:
        return [
            130,
            130,
            130,
            210,
        ]

    if oncelik_seviyesi == "Yüksek":
        return [
            220,
            60,
            60,
            210,
        ]

    if oncelik_seviyesi == "Orta":
        return [
            245,
            160,
            60,
            210,
        ]

    # Düşük öncelikli ilçeler mavi.
    return [
        65,
        125,
        190,
        210,
    ]


# --------------------------------------------------
# İLÇE GEOJSON VERİSİNİ VERİ TABANINDAN GETİR
# --------------------------------------------------

def ilce_geojson_verisini_getir(
    baglanti,
    hizmet_turu_id,
):
    """
    districts ve district_metrics tablolarını
    birleştirerek PyDeck'in kullanabileceği bir
    GeoJSON FeatureCollection oluşturur.
    """

    sonuclar = baglanti.execute(
        """
        SELECT
            districts.id,
            districts.name,
            districts.population_2025,
            districts.geometry_geojson,

            district_metrics.facility_count,
            district_metrics.priority_score,
            district_metrics.priority_rank,
            district_metrics.priority_level,
            district_metrics.data_status

        FROM districts

        LEFT JOIN district_metrics
            ON district_metrics.district_id =
               districts.id

           AND district_metrics.service_type_id = ?

           AND district_metrics.analysis_year = ?

        ORDER BY districts.name;
        """,
        (
            hizmet_turu_id,
            2025,
        ),
    ).fetchall()

    features = []

    for satir in sonuclar:

        ilce_adi = satir["name"]

        geometri_metni = satir[
            "geometry_geojson"
        ]

        if geometri_metni is None:
            raise ValueError(
                f"{ilce_adi} ilçesinin geometrisi "
                "veri tabanında bulunamadı."
            )

        try:
            geometri = json.loads(
                geometri_metni
            )

        except json.JSONDecodeError as hata:
            raise ValueError(
                f"{ilce_adi} ilçesinin GeoJSON "
                "geometrisi geçersiz."
            ) from hata


        oncelik_puani = satir[
            "priority_score"
        ]

        oncelik_sirasi = satir[
            "priority_rank"
        ]

        oncelik_seviyesi = satir[
            "priority_level"
        ]

        nufus = satir[
            "population_2025"
        ]

        kutuphane_sayisi = satir[
            "facility_count"
        ]


        if kutuphane_sayisi is None:
            kutuphane_sayisi = 0


        # Öncelik puanı bulunan ilçelerin
        # gösterim değerlerini hazırla.
        if oncelik_puani is not None:

            oncelik_puani_gosterim = (
                f"{oncelik_puani:.1f}"
            )

            oncelik_sirasi_gosterim = (
                str(oncelik_sirasi)
            )

            yukseklik = (
                40
                + oncelik_puani * 6
            )

            not_metni = (
                "Yükseklik, görselleştirme amacıyla "
                "öncelik puanından üretilmiştir."
            )

        # Puanı hesaplanmayan ilçeler için
        # yanıltıcı sayı göstermiyoruz.
        else:

            oncelik_puani_gosterim = (
                "Hesaplanmadı"
            )

            oncelik_sirasi_gosterim = (
                "Hesaplanmadı"
            )

            oncelik_seviyesi = (
                "Veri doğrulaması gerekli"
            )

            # Gri ilçelerin haritada tamamen düz
            # görünmemesi için küçük bir yükseklik.
            yukseklik = 20

            not_metni = (
                "İBB veri setindeki kayıt durumu "
                "doğrulanmalıdır."
            )


        renk = oncelik_rengi_belirle(
            oncelik_seviyesi,
            oncelik_puani,
        )


        feature = {
            "type": "Feature",

            "properties": {
                "district_id": satir["id"],

                "district": ilce_adi,

                "display_name": (
                    f"{ilce_adi} İlçe Önceliği"
                ),

                "object_type": (
                    "İlçe hizmet önceliği"
                ),

                "population": nufus,

                "library_count": (
                    kutuphane_sayisi
                ),

                "priority_score": (
                    oncelik_puani
                ),

                "priority_rank": (
                    oncelik_sirasi
                ),

                "priority_level": (
                    oncelik_seviyesi
                ),

                "data_status": satir[
                    "data_status"
                ],

                "fill_color": renk,

                # Bu değer gerçek arazi veya bina
                # yüksekliği değildir.
                "elevation": yukseklik,

                "priority_score_display": (
                    oncelik_puani_gosterim
                ),

                "priority_rank_display": (
                    oncelik_sirasi_gosterim
                ),

                "population_display": (
                    f"{nufus:,}"
                    .replace(",", ".")
                    if nufus is not None
                    else "Bilinmiyor"
                ),

                "library_count_display": (
                    str(kutuphane_sayisi)
                ),

                "note": not_metni,
            },

            "geometry": geometri,
        }

        features.append(
            feature
        )


    if len(features) != 39:
        raise ValueError(
            "Harita için 39 ilçe bekleniyordu. "
            f"Bulunan ilçe: {len(features)}"
        )


    return {
        "type": "FeatureCollection",
        "features": features,
    }


# --------------------------------------------------
# KÜTÜPHANE NOKTALARINI VERİ TABANINDAN GETİR
# --------------------------------------------------

def kutuphane_noktalarini_getir(
    baglanti,
    hizmet_turu_id,
):
    """
    facilities tablosundaki güvenilir koordinatlı
    kütüphaneleri PyDeck ColumnLayer biçimine
    dönüştürür.
    """

    sonuclar = baglanti.execute(
        """
        SELECT
            facilities.id,
            facilities.name,
            facilities.address,
            facilities.latitude,
            facilities.longitude,
            facilities.coordinate_status,

            districts.name AS district_name

        FROM facilities

        INNER JOIN districts
            ON districts.id =
               facilities.district_id

        WHERE facilities.service_type_id = ?

          AND facilities.coordinate_status =
              'verified'

          AND facilities.latitude IS NOT NULL

          AND facilities.longitude IS NOT NULL

        ORDER BY facilities.name;
        """,
        (
            hizmet_turu_id,
        ),
    ).fetchall()


    kutuphane_noktalari = []

    for satir in sonuclar:

        kutuphane_adi = satir[
            "name"
        ]

        ilce_adi = satir[
            "district_name"
        ]

        adres = (
            satir["address"]
            or "Adres bilgisi bulunamadı."
        )


        kutuphane_noktalari.append(
            {
                "id": satir["id"],

                # ColumnLayer için önce boylam,
                # sonra enlem kullanılır.
                "longitude": float(
                    satir["longitude"]
                ),

                "latitude": float(
                    satir["latitude"]
                ),

                # Bu değer gerçek bina yüksekliği
                # değildir. Noktaların görünür olması
                # için kullanılan kısa sütun değeridir.
                "elevation": 55,

                "fill_color": [
                    25,
                    85,
                    180,
                    235,
                ],

                # İlçe alanlarıyla aynı tooltip
                # yapısını kullanabilmek için bilgiler
                # properties içinde tutulur.
                "properties": {
                    "display_name": (
                        kutuphane_adi
                    ),

                    "object_type": (
                        "Mevcut kütüphane"
                    ),

                    "district": ilce_adi,

                    "priority_score_display": (
                        "İlçe alanına bakınız"
                    ),

                    "priority_rank_display": (
                        "İlçe alanına bakınız"
                    ),

                    "priority_level": (
                        "İlçe alanına bakınız"
                    ),

                    "population_display": (
                        "İlçe alanına bakınız"
                    ),

                    "library_count_display": (
                        "İlçe alanına bakınız"
                    ),

                    "note": (
                        f"Adres: {adres}"
                    ),
                },
            }
        )


    if len(kutuphane_noktalari) != 51:
        raise ValueError(
            "Harita için 51 güvenilir kütüphane "
            "noktası bekleniyordu. "
            f"Bulunan kayıt: "
            f"{len(kutuphane_noktalari)}"
        )


    return kutuphane_noktalari


# --------------------------------------------------
# HARİTA AÇIKLAMA PANELİ
# --------------------------------------------------

def aciklama_panelini_getir():

    return """
<div id="urbanai-bilgi-paneli">
    <div class="urbanai-baslik">
        UrbanAI 3D İstanbul
    </div>

    <div class="urbanai-alt-baslik">
        Kütüphane Hizmeti İlçe Öncelik Haritası
    </div>

    <div class="urbanai-ayrac"></div>

    <div class="urbanai-aciklama">
        <span class="urbanai-renk urbanai-yuksek"></span>
        <span>Yüksek öncelik</span>
    </div>

    <div class="urbanai-aciklama">
        <span class="urbanai-renk urbanai-orta"></span>
        <span>Orta öncelik</span>
    </div>

    <div class="urbanai-aciklama">
        <span class="urbanai-renk urbanai-dusuk"></span>
        <span>Düşük öncelik</span>
    </div>

    <div class="urbanai-aciklama">
        <span class="urbanai-renk urbanai-dogrulama"></span>
        <span>Veri doğrulaması gerekli</span>
    </div>

    <div class="urbanai-aciklama">
        <span class="urbanai-kutuphane-isareti"></span>
        <span>Mevcut kütüphane</span>
    </div>

    <div class="urbanai-ayrac"></div>

    <div class="urbanai-not">
        İlçe yüksekliği, nüfus ve İBB kütüphane
        kayıtlarından hesaplanan öncelik puanının
        görsel karşılığıdır. Gerçek arazi veya bina
        yüksekliğini göstermez.
    </div>

    <div class="urbanai-kaynak">
        Veri kaynağı: UrbanAI SQLite veri tabanı<br>
        Analiz yılı: 2025
    </div>
</div>

<a
    id="urbanai-ana-sayfa-butonu"
    href="index.html"
>
    <span>←</span>
    Ana sayfaya dön
</a>

<style>
    #urbanai-bilgi-paneli {
        position: fixed;
        top: 18px;
        left: 18px;
        z-index: 9999;

        width: 280px;
        box-sizing: border-box;

        padding: 15px 16px;

        background: rgba(22, 27, 34, 0.92);
        color: white;

        border: 1px solid rgba(255, 255, 255, 0.20);
        border-radius: 10px;

        font-family:
            Arial,
            Helvetica,
            sans-serif;

        box-shadow:
            0 4px 16px rgba(0, 0, 0, 0.28);

        pointer-events: none;
    }

    .urbanai-baslik {
        margin-bottom: 3px;
        font-size: 18px;
        font-weight: 700;
    }

    .urbanai-alt-baslik {
        color: rgba(255, 255, 255, 0.82);
        font-size: 13px;
        line-height: 1.35;
    }

    .urbanai-ayrac {
        height: 1px;
        margin: 11px 0;

        background:
            rgba(255, 255, 255, 0.18);
    }

    .urbanai-aciklama {
        display: flex;
        align-items: center;
        gap: 9px;

        margin: 7px 0;

        font-size: 13px;
    }

    .urbanai-renk {
        display: inline-block;

        width: 16px;
        height: 16px;

        border:
            1px solid rgba(255, 255, 255, 0.65);

        border-radius: 4px;
    }

    .urbanai-yuksek {
        background:
            rgba(220, 60, 60, 0.95);
    }

    .urbanai-orta {
        background:
            rgba(245, 160, 60, 0.95);
    }

    .urbanai-dusuk {
        background:
            rgba(65, 125, 190, 0.95);
    }

    .urbanai-dogrulama {
        background:
            rgba(130, 130, 130, 0.95);
    }

    .urbanai-kutuphane-isareti {
        display: inline-block;

        width: 10px;
        height: 18px;

        margin-left: 3px;
        margin-right: 3px;

        background:
            rgba(25, 85, 180, 1);

        border:
            1px solid rgba(255, 255, 255, 0.80);

        border-radius: 3px;
    }

    .urbanai-not {
        color: rgba(255, 255, 255, 0.75);

        font-size: 11px;
        line-height: 1.45;
    }

    .urbanai-kaynak {
        margin-top: 8px;

        color: rgba(255, 255, 255, 0.60);

        font-size: 10px;
        line-height: 1.4;
    }

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
            1px solid rgba(255, 255, 255, 0.22);

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
            0 4px 16px rgba(0, 0, 0, 0.25);

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
        #urbanai-bilgi-paneli {
            top: 10px;
            left: 10px;

            width: 225px;

            padding: 11px 12px;
        }

        .urbanai-baslik {
            font-size: 15px;
        }

        .urbanai-alt-baslik,
        .urbanai-aciklama {
            font-size: 11px;
        }

        .urbanai-not {
            font-size: 10px;
        }

        #urbanai-ana-sayfa-butonu {
            top: 10px;
            right: 10px;

            padding: 9px 11px;

            font-size: 11px;
        }
    }
</style>
"""


# --------------------------------------------------
# ANA ÇALIŞMA AKIŞI
# --------------------------------------------------

def main():

    baglanti = baglanti_olustur()

    try:
        hizmet_turu_id = (
            kutuphane_hizmet_turu_id_getir(
                baglanti
            )
        )

        ilce_geojson = (
            ilce_geojson_verisini_getir(
                baglanti,
                hizmet_turu_id,
            )
        )

        kutuphane_noktalari = (
            kutuphane_noktalarini_getir(
                baglanti,
                hizmet_turu_id,
            )
        )

    finally:
        baglanti.close()


    # --------------------------------------------------
    # İLÇE GEOJSON KATMANI
    # --------------------------------------------------

    ilce_katmani = pdk.Layer(
        "GeoJsonLayer",

        data=ilce_geojson,

        filled=True,
        stroked=True,
        extruded=True,

        get_fill_color=(
            "properties.fill_color"
        ),

        get_elevation=(
            "properties.elevation"
        ),

        get_line_color=[
            255,
            255,
            255,
            210,
        ],

        line_width_min_pixels=1,

        pickable=True,

        auto_highlight=True,

        highlight_color=[
            255,
            255,
            255,
            80,
        ],

        wireframe=False,

        opacity=0.82,
    )


    # --------------------------------------------------
    # MEVCUT KÜTÜPHANE KATMANI
    # --------------------------------------------------

    kutuphane_katmani = pdk.Layer(
        "ColumnLayer",

        data=kutuphane_noktalari,

        get_position=[
            "longitude",
            "latitude",
        ],

        get_elevation="elevation",

        get_fill_color="fill_color",

        radius=110,

        disk_resolution=12,

        elevation_scale=1,

        extruded=True,

        pickable=True,

        auto_highlight=True,
    )


    # --------------------------------------------------
    # BAŞLANGIÇ KAMERA GÖRÜNÜMÜ
    # --------------------------------------------------

    baslangic_gorunumu = pdk.ViewState(
        latitude=41.02,
        longitude=28.97,

        zoom=9.15,

        pitch=40,

        bearing=0,
    )


    # --------------------------------------------------
    # ORTAK BİLGİ KUTUSU
    # --------------------------------------------------

    bilgi_kutusu = {
        "html": """
            <b>{properties.display_name}</b><br/>
            Öncelik: {properties.priority_score_display}
            — {properties.priority_level}<br/>
            Sıra: {properties.priority_rank_display}<br/>
            Nüfus: {properties.population_display}<br/>
            İBB kütüphane kaydı:
            {properties.library_count_display}<br/>
            <span style="color: #bbbbbb;">
                {properties.note}
            </span>
        """,

        "style": {
            "backgroundColor": (
                "rgba(25, 25, 25, 0.92)"
            ),

            "color": "white",

            "fontSize": "11px",

            "padding": "8px",

            "maxWidth": "230px",

            "borderRadius": "6px",
        },
    }


    # --------------------------------------------------
    # HARİTA NESNESİNİ OLUŞTUR
    # --------------------------------------------------

    harita_3d = pdk.Deck(
        layers=[
            ilce_katmani,
            kutuphane_katmani,
        ],

        initial_view_state=(
            baslangic_gorunumu
        ),

        map_provider="carto",

        map_style="light",

        tooltip=bilgi_kutusu,

        show_error=True,
    )


    # --------------------------------------------------
    # HARİTA HTML KODUNU ÜRET
    # --------------------------------------------------

    harita_html = harita_3d.to_html(
        as_string=True,
        open_browser=False,
    )


    # --------------------------------------------------
    # AÇIKLAMA PANELİNİ HTML'E EKLE
    # --------------------------------------------------

    if "</body>" not in harita_html:
        raise ValueError(
            "PyDeck tarafından üretilen HTML "
            "içinde </body> etiketi bulunamadı."
        )


    aciklama_paneli = (
        aciklama_panelini_getir()
    )


    harita_html = harita_html.replace(
        "</body>",
        aciklama_paneli + "\n</body>",
    )


    # --------------------------------------------------
    # HTML DOSYASINI KAYDET
    # --------------------------------------------------

    harita_cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )


    harita_cikti_yolu.write_text(
        harita_html,
        encoding="utf-8",
    )


    # --------------------------------------------------
    # SONUÇLARI KONTROL ET
    # --------------------------------------------------

    toplam_ilce_sayisi = len(
        ilce_geojson["features"]
    )


    puanli_ilce_sayisi = sum(
        feature["properties"][
            "priority_score"
        ] is not None

        for feature
        in ilce_geojson["features"]
    )


    dogrulama_gereken_sayi = (
        toplam_ilce_sayisi
        - puanli_ilce_sayisi
    )


    print(
        "Veri kaynağı: "
        "data/database/urbanai.db"
    )

    print(
        f"3D ilçe alanı sayısı: "
        f"{toplam_ilce_sayisi}"
    )

    print(
        f"Öncelik puanı bulunan ilçe: "
        f"{puanli_ilce_sayisi}"
    )

    print(
        f"Veri doğrulaması gereken ilçe: "
        f"{dogrulama_gereken_sayi}"
    )

    print(
        f"Gösterilen mevcut kütüphane: "
        f"{len(kutuphane_noktalari)}"
    )

    print(
        "\n3D ilçe öncelik haritası "
        f"kaydedildi: {harita_cikti_yolu}"
    )


if __name__ == "__main__":
    main()