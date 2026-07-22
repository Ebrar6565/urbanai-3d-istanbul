from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any

import folium
import geopandas as gpd
import pandas as pd

from folium.features import GeoJsonPopup, GeoJsonTooltip
from folium.plugins import MarkerCluster

from shapely import make_valid
from shapely.geometry import box, shape
from shapely.ops import unary_union
from shapely.strtree import STRtree


# ==========================================================
# PROJE YOLLARI
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

VERITABANI_YOLU = (
    PROJE_KOKU
    / "data"
    / "database"
    / "urbanai.db"
)

ISLENMIS_VERI_KLASORU = (
    PROJE_KOKU
    / "data"
    / "processed"
)

FRONTEND_KLASORU = (
    PROJE_KOKU
    / "frontend"
)


# ==========================================================
# ÇIKTI DOSYALARI
# ==========================================================

CSV_CIKTI_YOLU = (
    ISLENMIS_VERI_KLASORU
    / "hizmet_boslugu_hucreleri.csv"
)

GEOJSON_CIKTI_YOLU = (
    ISLENMIS_VERI_KLASORU
    / "hizmet_boslugu_hucreleri.geojson"
)

HARITA_CIKTI_YOLU = (
    FRONTEND_KLASORU
    / "hizmet_boslugu_haritasi.html"
)


# ==========================================================
# ANALİZ AYARLARI
# ==========================================================

HIZMET_TURU = "Kütüphane"

ONCELIKLI_ILCE_SAYISI = 5

HUCRE_BOYUTU_METRE = 750

MINIMUM_HUCRE_ALAN_ORANI = 0.10


# İstanbul için metre bazlı hesaplama yapılabilecek
# UTM koordinat sistemi.
METRIK_KOORDINAT_SISTEMI = "EPSG:32635"

COGRAFI_KOORDINAT_SISTEMI = "EPSG:4326"


# ==========================================================
# HİZMET BOŞLUĞU SINIFLARI
# ==========================================================

HIZMET_RENKLERI = {
    "Hizmete yakın": "#22c55e",
    "Orta uzaklık": "#facc15",
    "Hizmet açığı yüksek": "#f97316",
    "Güçlü aday inceleme alanı": "#dc2626",
}


# ==========================================================
# VERİ TABANI BAĞLANTISI
# ==========================================================

def veritabanina_baglan() -> sqlite3.Connection:
    """
    SQLite veri tabanına bağlantı oluşturur.
    """

    if not VERITABANI_YOLU.exists():
        raise FileNotFoundError(
            "Veri tabanı bulunamadı:\n"
            f"{VERITABANI_YOLU}"
        )

    baglanti = sqlite3.connect(
        VERITABANI_YOLU
    )

    baglanti.row_factory = sqlite3.Row

    return baglanti


# ==========================================================
# GEOJSON GEOMETRİSİNİ OKUMA
# ==========================================================

def geojson_geometrisini_oku(
    geojson_metni: str,
):
    """
    Veri tabanında metin olarak saklanan GeoJSON
    geometrisini Shapely geometrisine dönüştürür.

    Geometry, Feature ve FeatureCollection yapılarını
    destekler.
    """

    if not geojson_metni:
        raise ValueError(
            "İlçe geometrisi boş."
        )

    geojson_verisi = json.loads(
        geojson_metni
    )

    geojson_turu = geojson_verisi.get(
        "type"
    )

    if geojson_turu == "Feature":
        geometri = shape(
            geojson_verisi["geometry"]
        )

    elif geojson_turu == "FeatureCollection":
        geometriler = [
            shape(feature["geometry"])
            for feature
            in geojson_verisi["features"]
            if feature.get("geometry")
        ]

        if not geometriler:
            raise ValueError(
                "FeatureCollection içinde "
                "geometri bulunamadı."
            )

        geometri = unary_union(
            geometriler
        )

    else:
        geometri = shape(
            geojson_verisi
        )

    if not geometri.is_valid:
        geometri = make_valid(
            geometri
        )

    return geometri


# ==========================================================
# ÖNCELİKLİ İLÇELERİ OKUMA
# ==========================================================

def oncelikli_ilceleri_oku(
    baglanti: sqlite3.Connection,
) -> gpd.GeoDataFrame:
    """
    Öncelik sırasına göre ilk beş ilçeyi
    veri tabanından okur.
    """

    sorgu = """
        SELECT
            d.id AS district_id,
            d.name AS district_name,
            d.population_2025,
            d.geometry_geojson,
            d.geometry_source,
            dm.facility_count,
            dm.service_per_100k,
            dm.people_per_facility,
            dm.priority_score,
            dm.priority_level,
            dm.priority_rank,
            dm.data_status,
            dm.analysis_year
        FROM districts AS d
        INNER JOIN district_metrics AS dm
            ON dm.district_id = d.id
        INNER JOIN service_types AS st
            ON st.id = dm.service_type_id
        WHERE
            st.name = ?
            AND dm.priority_score IS NOT NULL
            AND d.geometry_geojson IS NOT NULL
        ORDER BY
            dm.priority_rank ASC
        LIMIT ?
    """

    ilceler_dataframe = pd.read_sql_query(
        sorgu,
        baglanti,
        params=(
            HIZMET_TURU,
            ONCELIKLI_ILCE_SAYISI,
        ),
    )

    if ilceler_dataframe.empty:
        raise ValueError(
            "Öncelikli ilçe verisi bulunamadı."
        )

    geometriler = [
        geojson_geometrisini_oku(
            geojson_metni
        )
        for geojson_metni
        in ilceler_dataframe[
            "geometry_geojson"
        ]
    ]

    ilceler_dataframe = (
        ilceler_dataframe.drop(
            columns=[
                "geometry_geojson",
            ]
        )
    )

    ilceler_geo_dataframe = (
        gpd.GeoDataFrame(
            ilceler_dataframe,
            geometry=gpd.GeoSeries(
                geometriler,
                crs=COGRAFI_KOORDINAT_SISTEMI,
            ),
            crs=COGRAFI_KOORDINAT_SISTEMI,
        )
    )

    return ilceler_geo_dataframe


# ==========================================================
# DOĞRULANMIŞ KÜTÜPHANELERİ OKUMA
# ==========================================================

def dogrulanmis_kutuphaneleri_oku(
    baglanti: sqlite3.Connection,
) -> gpd.GeoDataFrame:
    """
    İstanbul genelindeki doğrulanmış koordinatlı
    kütüphane kayıtlarını okur.

    Mesafe hesabında yalnızca aynı ilçedeki değil,
    İstanbul'daki bütün doğrulanmış kütüphaneler
    kullanılır.
    """

    sorgu = """
        SELECT
            f.id AS facility_id,
            f.name AS facility_name,
            d.name AS facility_district,
            f.address,
            f.latitude,
            f.longitude,
            f.coordinate_status
        FROM facilities AS f
        INNER JOIN districts AS d
            ON d.id = f.district_id
        INNER JOIN service_types AS st
            ON st.id = f.service_type_id
        WHERE
            st.name = ?
            AND f.coordinate_status = 'verified'
            AND f.latitude IS NOT NULL
            AND f.longitude IS NOT NULL
        ORDER BY
            f.name
    """

    kutuphaneler_dataframe = pd.read_sql_query(
        sorgu,
        baglanti,
        params=(
            HIZMET_TURU,
        ),
    )

    if kutuphaneler_dataframe.empty:
        raise ValueError(
            "Doğrulanmış koordinatlı "
            "kütüphane bulunamadı."
        )

    kutuphaneler_geo_dataframe = (
        gpd.GeoDataFrame(
            kutuphaneler_dataframe,
            geometry=gpd.points_from_xy(
                kutuphaneler_dataframe[
                    "longitude"
                ],
                kutuphaneler_dataframe[
                    "latitude"
                ],
            ),
            crs=COGRAFI_KOORDINAT_SISTEMI,
        )
    )

    return kutuphaneler_geo_dataframe


# ==========================================================
# HÜCRELERİ OLUŞTURMA
# ==========================================================

def ilceleri_hucrelere_bol(
    ilceler_metrik: gpd.GeoDataFrame,
) -> tuple[
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
]:
    """
    İlçe sınırlarını 750 x 750 metrelik hücrelere böler.

    İlçe sınırında kalan çok küçük geometrik parçaların
    analizi bozmasını önlemek için hücrenin en az yüzde
    10'unun ilçe içerisinde olması gerekir.
    """

    hucre_kayitlari: list[
        dict[str, Any]
    ] = []

    merkez_kayitlari: list[
        dict[str, Any]
    ] = []

    tam_hucre_alani = (
        HUCRE_BOYUTU_METRE
        * HUCRE_BOYUTU_METRE
    )

    for ilce in ilceler_metrik.itertuples():

        ilce_geometrisi = ilce.geometry

        if not ilce_geometrisi.is_valid:
            ilce_geometrisi = make_valid(
                ilce_geometrisi
            )

        min_x, min_y, max_x, max_y = (
            ilce_geometrisi.bounds
        )

        baslangic_x = (
            math.floor(
                min_x
                / HUCRE_BOYUTU_METRE
            )
            * HUCRE_BOYUTU_METRE
        )

        baslangic_y = (
            math.floor(
                min_y
                / HUCRE_BOYUTU_METRE
            )
            * HUCRE_BOYUTU_METRE
        )

        bitis_x = (
            math.ceil(
                max_x
                / HUCRE_BOYUTU_METRE
            )
            * HUCRE_BOYUTU_METRE
        )

        bitis_y = (
            math.ceil(
                max_y
                / HUCRE_BOYUTU_METRE
            )
            * HUCRE_BOYUTU_METRE
        )

        ilce_hucre_sayaci = 1

        for x_koordinati in range(
            int(baslangic_x),
            int(bitis_x),
            HUCRE_BOYUTU_METRE,
        ):

            for y_koordinati in range(
                int(baslangic_y),
                int(bitis_y),
                HUCRE_BOYUTU_METRE,
            ):

                tam_hucre = box(
                    x_koordinati,
                    y_koordinati,
                    (
                        x_koordinati
                        + HUCRE_BOYUTU_METRE
                    ),
                    (
                        y_koordinati
                        + HUCRE_BOYUTU_METRE
                    ),
                )

                if not tam_hucre.intersects(
                    ilce_geometrisi
                ):
                    continue

                kesilmis_hucre = (
                    tam_hucre.intersection(
                        ilce_geometrisi
                    )
                )

                if kesilmis_hucre.is_empty:
                    continue

                hucre_alan_orani = (
                    kesilmis_hucre.area
                    / tam_hucre_alani
                )

                if (
                    hucre_alan_orani
                    < MINIMUM_HUCRE_ALAN_ORANI
                ):
                    continue

                hucre_kimligi = (
                    f"{ilce.district_id}-"
                    f"{ilce_hucre_sayaci:04d}"
                )

                analiz_noktasi = (
                    kesilmis_hucre
                    .representative_point()
                )

                hucre_kayitlari.append(
                    {
                        "cell_id": hucre_kimligi,
                        "district_id": (
                            ilce.district_id
                        ),
                        "district_name": (
                            ilce.district_name
                        ),
                        "population_2025": (
                            ilce.population_2025
                        ),
                        "facility_count": (
                            ilce.facility_count
                        ),
                        "service_per_100k": (
                            ilce.service_per_100k
                        ),
                        "priority_score": (
                            ilce.priority_score
                        ),
                        "priority_level": (
                            ilce.priority_level
                        ),
                        "priority_rank": (
                            ilce.priority_rank
                        ),
                        "analysis_year": (
                            ilce.analysis_year
                        ),
                        "cell_area_ratio": (
                            hucre_alan_orani
                        ),
                        "geometry": (
                            kesilmis_hucre
                        ),
                    }
                )

                merkez_kayitlari.append(
                    {
                        "cell_id": hucre_kimligi,
                        "geometry": analiz_noktasi,
                    }
                )

                ilce_hucre_sayaci += 1

    if not hucre_kayitlari:
        raise ValueError(
            "Hiçbir analiz hücresi üretilemedi."
        )

    hucreler_geo_dataframe = (
        gpd.GeoDataFrame(
            hucre_kayitlari,
            geometry="geometry",
            crs=METRIK_KOORDINAT_SISTEMI,
        )
    )

    merkezler_geo_dataframe = (
        gpd.GeoDataFrame(
            merkez_kayitlari,
            geometry="geometry",
            crs=METRIK_KOORDINAT_SISTEMI,
        )
    )

    return (
        hucreler_geo_dataframe,
        merkezler_geo_dataframe,
    )


# ==========================================================
# HİZMET SINIFI BELİRLEME
# ==========================================================

def hizmet_boslugu_sinifi_belirle(
    mesafe_metre: float,
) -> str:
    """
    En yakın kütüphaneye olan uzaklığı
    hizmet boşluğu sınıfına dönüştürür.
    """

    if mesafe_metre <= 1000:
        return "Hizmete yakın"

    if mesafe_metre <= 2000:
        return "Orta uzaklık"

    if mesafe_metre <= 3000:
        return "Hizmet açığı yüksek"

    return "Güçlü aday inceleme alanı"


# ==========================================================
# EN YAKIN KÜTÜPHANEYİ BULMA
# ==========================================================

def en_yakin_kutuphaneleri_hesapla(
    hucreler_metrik: gpd.GeoDataFrame,
    merkezler_metrik: gpd.GeoDataFrame,
    kutuphaneler_metrik: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Her hücrenin analiz noktasına en yakın
    doğrulanmış kütüphaneyi bulur.
    """

    kutuphane_geometrileri = list(
        kutuphaneler_metrik.geometry
    )

    if not kutuphane_geometrileri:
        raise ValueError(
            "Mesafe hesabı için "
            "kütüphane geometrisi bulunamadı."
        )

    mekansal_agac = STRtree(
        kutuphane_geometrileri
    )

    mesafe_kayitlari: list[
        dict[str, Any]
    ] = []

    for merkez in merkezler_metrik.itertuples():

        en_yakin_indeks = int(
            mekansal_agac.nearest(
                merkez.geometry
            )
        )

        kutuphane = (
            kutuphaneler_metrik.iloc[
                en_yakin_indeks
            ]
        )

        mesafe_metre = float(
            merkez.geometry.distance(
                kutuphane.geometry
            )
        )

        hizmet_sinifi = (
            hizmet_boslugu_sinifi_belirle(
                mesafe_metre
            )
        )

        mesafe_kayitlari.append(
            {
                "cell_id": merkez.cell_id,
                "nearest_library_id": (
                    int(
                        kutuphane[
                            "facility_id"
                        ]
                    )
                ),
                "nearest_library_name": (
                    kutuphane[
                        "facility_name"
                    ]
                ),
                "nearest_library_district": (
                    kutuphane[
                        "facility_district"
                    ]
                ),
                "nearest_library_distance_m": (
                    round(
                        mesafe_metre,
                        2,
                    )
                ),
                "nearest_library_distance_km": (
                    round(
                        mesafe_metre / 1000,
                        3,
                    )
                ),
                "service_gap_class": (
                    hizmet_sinifi
                ),
                "candidate_review": (
                    "Evet"
                    if mesafe_metre > 3000
                    else "Hayır"
                ),
            }
        )

    mesafe_dataframe = pd.DataFrame(
        mesafe_kayitlari
    )

    sonuc = hucreler_metrik.merge(
        mesafe_dataframe,
        on="cell_id",
        how="left",
    )

    sonuc = gpd.GeoDataFrame(
        sonuc,
        geometry="geometry",
        crs=METRIK_KOORDINAT_SISTEMI,
    )

    sonuc[
        "cell_area_km2"
    ] = (
        sonuc.geometry.area
        / 1_000_000
    ).round(4)

    return sonuc


# ==========================================================
# MERKEZ KOORDİNATLARINI EKLEME
# ==========================================================

def merkez_koordinatlarini_ekle(
    hucreler_metrik: gpd.GeoDataFrame,
    merkezler_metrik: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Hücrelerin analiz noktalarını enlem ve boylam
    değerlerine dönüştürerek tabloya ekler.
    """

    merkezler_cografi = (
        merkezler_metrik.to_crs(
            COGRAFI_KOORDINAT_SISTEMI
        )
    )

    merkez_koordinatlari = pd.DataFrame(
        {
            "cell_id": (
                merkezler_cografi[
                    "cell_id"
                ]
            ),
            "center_longitude": (
                merkezler_cografi
                .geometry
                .x
                .round(6)
            ),
            "center_latitude": (
                merkezler_cografi
                .geometry
                .y
                .round(6)
            ),
        }
    )

    sonuc = hucreler_metrik.merge(
        merkez_koordinatlari,
        on="cell_id",
        how="left",
    )

    sonuc = gpd.GeoDataFrame(
        sonuc,
        geometry="geometry",
        crs=METRIK_KOORDINAT_SISTEMI,
    )

    return sonuc


# ==========================================================
# CSV VE GEOJSON KAYDETME
# ==========================================================

def ciktilari_kaydet(
    hucreler_metrik: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Analiz sonucunu CSV ve GeoJSON biçimlerinde kaydeder.
    """

    ISLENMIS_VERI_KLASORU.mkdir(
        parents=True,
        exist_ok=True,
    )

    hucreler_cografi = (
        hucreler_metrik.to_crs(
            COGRAFI_KOORDINAT_SISTEMI
        )
    )

    hucreler_cografi[
        "priority_score"
    ] = (
        hucreler_cografi[
            "priority_score"
        ].round(3)
    )

    hucreler_cografi[
        "cell_area_ratio"
    ] = (
        hucreler_cografi[
            "cell_area_ratio"
        ].round(3)
    )

    csv_sutunlari = [
        "cell_id",
        "district_id",
        "district_name",
        "population_2025",
        "facility_count",
        "service_per_100k",
        "priority_score",
        "priority_level",
        "priority_rank",
        "analysis_year",
        "cell_area_ratio",
        "cell_area_km2",
        "center_latitude",
        "center_longitude",
        "nearest_library_id",
        "nearest_library_name",
        "nearest_library_district",
        "nearest_library_distance_m",
        "nearest_library_distance_km",
        "service_gap_class",
        "candidate_review",
    ]

    csv_dataframe = pd.DataFrame(
        hucreler_cografi.drop(
            columns=[
                "geometry",
            ]
        )
    )

    csv_dataframe[
        csv_sutunlari
    ].to_csv(
        CSV_CIKTI_YOLU,
        index=False,
        encoding="utf-8-sig",
    )

    geojson_sutunlari = (
        csv_sutunlari
        + [
            "geometry",
        ]
    )

    geojson_metni = (
        hucreler_cografi[
            geojson_sutunlari
        ].to_json(
            ensure_ascii=False
        )
    )

    GEOJSON_CIKTI_YOLU.write_text(
        geojson_metni,
        encoding="utf-8",
    )

    return hucreler_cografi


# ==========================================================
# HARİTA BAŞLIK PANELİ
# ==========================================================

def harita_baslik_paneli_ekle(
    harita: folium.Map,
) -> None:
    """
    Haritanın sol üst bölümüne bilgi paneli ekler.
    """

    panel_html = """
    <div style="
        position: fixed;
        top: 18px;
        left: 55px;
        z-index: 9999;
        width: 330px;
        padding: 16px 18px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 8px 28px rgba(0,0,0,0.16);
        font-family: Arial, sans-serif;
        color: #172033;
    ">
        <div style="
            font-size: 16px;
            font-weight: 700;
            margin-bottom: 7px;
        ">
            Kütüphane Hizmet Boşluğu Haritası
        </div>

        <div style="
            font-size: 11px;
            line-height: 1.55;
            color: #5e6878;
        ">
            Öncelikli ilk 5 ilçe, 750 × 750 metrelik
            hücrelerle analiz edilmiştir. Mesafeler
            İstanbul'daki 51 doğrulanmış İBB kütüphane
            noktasının tamamına göre hesaplanmıştır.
        </div>
    </div>
    """

    harita.get_root().html.add_child(
        folium.Element(
            panel_html
        )
    )


# ==========================================================
# HARİTA LEJANTI
# ==========================================================

def harita_lejanti_ekle(
    harita: folium.Map,
) -> None:
    """
    Haritanın sağ alt bölümüne renk açıklaması ekler.
    """

    lejant_html = """
    <div style="
        position: fixed;
        right: 20px;
        bottom: 25px;
        z-index: 9999;
        width: 245px;
        padding: 15px;
        border-radius: 12px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 8px 28px rgba(0,0,0,0.16);
        font-family: Arial, sans-serif;
        font-size: 11px;
        color: #172033;
    ">
        <div style="
            font-weight: 700;
            margin-bottom: 10px;
        ">
            En yakın kütüphaneye uzaklık
        </div>

        <div style="margin-bottom: 7px;">
            <span style="
                display: inline-block;
                width: 14px;
                height: 14px;
                margin-right: 7px;
                background: #22c55e;
                border-radius: 3px;
                vertical-align: middle;
            "></span>
            0–1 km: Hizmete yakın
        </div>

        <div style="margin-bottom: 7px;">
            <span style="
                display: inline-block;
                width: 14px;
                height: 14px;
                margin-right: 7px;
                background: #facc15;
                border-radius: 3px;
                vertical-align: middle;
            "></span>
            1–2 km: Orta uzaklık
        </div>

        <div style="margin-bottom: 7px;">
            <span style="
                display: inline-block;
                width: 14px;
                height: 14px;
                margin-right: 7px;
                background: #f97316;
                border-radius: 3px;
                vertical-align: middle;
            "></span>
            2–3 km: Hizmet açığı yüksek
        </div>

        <div>
            <span style="
                display: inline-block;
                width: 14px;
                height: 14px;
                margin-right: 7px;
                background: #dc2626;
                border-radius: 3px;
                vertical-align: middle;
            "></span>
            3 km üzeri: Aday inceleme alanı
        </div>
    </div>
    """

    harita.get_root().html.add_child(
        folium.Element(
            lejant_html
        )
    )


# ==========================================================
# ETKİLEŞİMLİ HARİTA OLUŞTURMA
# ==========================================================

def hizmet_boslugu_haritasi_olustur(
    hucreler_cografi: gpd.GeoDataFrame,
    ilceler_cografi: gpd.GeoDataFrame,
    kutuphaneler_cografi: gpd.GeoDataFrame,
) -> None:
    """
    Hücreler, ilçe sınırları ve mevcut kütüphaneler
    ile etkileşimli Folium haritası oluşturur.
    """

    FRONTEND_KLASORU.mkdir(
        parents=True,
        exist_ok=True,
    )

    harita = folium.Map(
        location=[
            41.02,
            28.97,
        ],
        zoom_start=10,
        tiles="CartoDB positron",
        control_scale=True,
    )

    ilce_sinirlari_katmani = folium.GeoJson(
        data=ilceler_cografi[
            [
                "district_name",
                "priority_rank",
                "priority_score",
                "geometry",
            ]
        ].to_json(
            ensure_ascii=False
        ),
        name="Öncelikli ilçe sınırları",
        style_function=lambda feature: {
            "fillColor": "transparent",
            "color": "#172033",
            "weight": 2.5,
            "fillOpacity": 0,
        },
        tooltip=GeoJsonTooltip(
            fields=[
                "district_name",
                "priority_rank",
                "priority_score",
            ],
            aliases=[
                "İlçe:",
                "Öncelik sırası:",
                "Öncelik puanı:",
            ],
            sticky=True,
        ),
    )

    ilce_sinirlari_katmani.add_to(
        harita
    )

    hucre_katmani = folium.GeoJson(
        data=hucreler_cografi.to_json(
            ensure_ascii=False
        ),
        name="Hizmet boşluğu hücreleri",
        style_function=lambda feature: {
            "fillColor": HIZMET_RENKLERI.get(
                feature[
                    "properties"
                ][
                    "service_gap_class"
                ],
                "#94a3b8",
            ),
            "color": "#ffffff",
            "weight": 0.6,
            "fillOpacity": 0.66,
        },
        highlight_function=lambda feature: {
            "weight": 2.5,
            "color": "#111827",
            "fillOpacity": 0.86,
        },
        tooltip=GeoJsonTooltip(
            fields=[
                "district_name",
                "nearest_library_distance_km",
                "service_gap_class",
            ],
            aliases=[
                "İlçe:",
                "En yakın kütüphane uzaklığı:",
                "Hizmet durumu:",
            ],
            localize=True,
            sticky=True,
        ),
        popup=GeoJsonPopup(
            fields=[
                "cell_id",
                "district_name",
                "priority_rank",
                "priority_score",
                "nearest_library_name",
                "nearest_library_district",
                "nearest_library_distance_km",
                "service_gap_class",
                "candidate_review",
            ],
            aliases=[
                "Hücre kimliği:",
                "İlçe:",
                "İlçe öncelik sırası:",
                "İlçe öncelik puanı:",
                "En yakın kütüphane:",
                "Kütüphanenin ilçesi:",
                "Uzaklık (km):",
                "Hizmet boşluğu sınıfı:",
                "Ayrıntılı inceleme adayı:",
            ],
            localize=True,
            labels=True,
            sticky=False,
        ),
    )

    hucre_katmani.add_to(
        harita
    )

    kutuphane_kumesi = MarkerCluster(
        name="Doğrulanmış kütüphaneler"
    )

    for kutuphane in (
        kutuphaneler_cografi.itertuples()
    ):

        popup_metni = f"""
        <div style="
            min-width: 220px;
            font-family: Arial, sans-serif;
        ">
            <strong>
                {kutuphane.facility_name}
            </strong>

            <br><br>

            <b>İlçe:</b>
            {kutuphane.facility_district}

            <br>

            <b>Koordinat durumu:</b>
            Doğrulanmış
        </div>
        """

        folium.CircleMarker(
            location=[
                kutuphane.latitude,
                kutuphane.longitude,
            ],
            radius=5,
            color="#1d4ed8",
            weight=2,
            fill=True,
            fill_color="#3b82f6",
            fill_opacity=0.95,
            tooltip=kutuphane.facility_name,
            popup=folium.Popup(
                popup_metni,
                max_width=320,
            ),
        ).add_to(
            kutuphane_kumesi
        )

    kutuphane_kumesi.add_to(
        harita
    )

    toplam_sinir = (
        ilceler_cografi.total_bounds
    )

    harita.fit_bounds(
        [
            [
                toplam_sinir[1],
                toplam_sinir[0],
            ],
            [
                toplam_sinir[3],
                toplam_sinir[2],
            ],
        ]
    )

    harita_baslik_paneli_ekle(
        harita
    )

    harita_lejanti_ekle(
        harita
    )

    folium.LayerControl(
        collapsed=False
    ).add_to(
        harita
    )

    harita.save(
        HARITA_CIKTI_YOLU
    )


# ==========================================================
# SONUÇ ÖZETİNİ YAZDIRMA
# ==========================================================

def analiz_ozetini_yazdir(
    hucreler: gpd.GeoDataFrame,
    ilceler: gpd.GeoDataFrame,
    kutuphaneler: gpd.GeoDataFrame,
) -> None:
    """
    Terminalde okunabilir analiz özeti gösterir.
    """

    print()
    print("=" * 70)
    print("KÜTÜPHANE HİZMET BOŞLUĞU ANALİZİ TAMAMLANDI")
    print("=" * 70)

    print()
    print(
        "Analize alınan öncelikli ilçeler:"
    )

    for ilce in ilceler.itertuples():
        print(
            f"  {ilce.priority_rank}. "
            f"{ilce.district_name} "
            f"(puan: {ilce.priority_score:.3f})"
        )

    print()
    print(
        "Doğrulanmış kütüphane sayısı:",
        len(kutuphaneler),
    )

    print(
        "Oluşturulan toplam hücre sayısı:",
        len(hucreler),
    )

    print()
    print(
        "Hizmet boşluğu sınıfları:"
    )

    sinif_sayilari = (
        hucreler[
            "service_gap_class"
        ]
        .value_counts()
    )

    for sinif_adi, adet in (
        sinif_sayilari.items()
    ):
        print(
            f"  {sinif_adi}: {adet}"
        )

    aday_sayisi = int(
        (
            hucreler[
                "candidate_review"
            ]
            == "Evet"
        ).sum()
    )

    print()
    print(
        "Ayrıntılı incelemeye alınabilecek "
        f"hücre sayısı: {aday_sayisi}"
    )

    print()
    print(
        "CSV çıktısı:"
    )
    print(
        f"  {CSV_CIKTI_YOLU}"
    )

    print()
    print(
        "GeoJSON çıktısı:"
    )
    print(
        f"  {GEOJSON_CIKTI_YOLU}"
    )

    print()
    print(
        "Etkileşimli harita:"
    )
    print(
        f"  {HARITA_CIKTI_YOLU}"
    )

    print()
    print("=" * 70)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    Hizmet boşluğu analizinin bütün adımlarını
    sırasıyla çalıştırır.
    """

    print()
    print(
        "Veri tabanına bağlanılıyor..."
    )

    baglanti = veritabanina_baglan()

    try:
        print(
            "Öncelikli ilçeler okunuyor..."
        )

        ilceler_cografi = (
            oncelikli_ilceleri_oku(
                baglanti
            )
        )

        print(
            "Doğrulanmış kütüphaneler okunuyor..."
        )

        kutuphaneler_cografi = (
            dogrulanmis_kutuphaneleri_oku(
                baglanti
            )
        )

    finally:
        baglanti.close()

    print(
        "Koordinatlar metre tabanlı sisteme "
        "dönüştürülüyor..."
    )

    ilceler_metrik = (
        ilceler_cografi.to_crs(
            METRIK_KOORDINAT_SISTEMI
        )
    )

    kutuphaneler_metrik = (
        kutuphaneler_cografi.to_crs(
            METRIK_KOORDINAT_SISTEMI
        )
    )

    print(
        "İlçe sınırları hücrelere bölünüyor..."
    )

    (
        hucreler_metrik,
        merkezler_metrik,
    ) = ilceleri_hucrelere_bol(
        ilceler_metrik
    )

    print(
        "En yakın kütüphane mesafeleri "
        "hesaplanıyor..."
    )

    hucreler_metrik = (
        en_yakin_kutuphaneleri_hesapla(
            hucreler_metrik,
            merkezler_metrik,
            kutuphaneler_metrik,
        )
    )

    print(
        "Hücre merkez koordinatları "
        "ekleniyor..."
    )

    hucreler_metrik = (
        merkez_koordinatlarini_ekle(
            hucreler_metrik,
            merkezler_metrik,
        )
    )

    print(
        "CSV ve GeoJSON çıktıları "
        "kaydediliyor..."
    )

    hucreler_cografi = (
        ciktilari_kaydet(
            hucreler_metrik
        )
    )

    print(
        "Etkileşimli hizmet boşluğu "
        "haritası oluşturuluyor..."
    )

    hizmet_boslugu_haritasi_olustur(
        hucreler_cografi,
        ilceler_cografi,
        kutuphaneler_cografi,
    )

    analiz_ozetini_yazdir(
        hucreler_cografi,
        ilceler_cografi,
        kutuphaneler_cografi,
    )


if __name__ == "__main__":
    main()