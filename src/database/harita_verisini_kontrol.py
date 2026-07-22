from pathlib import Path
import json
import sqlite3


# --------------------------------------------------
# VERİ TABANI YOLU
# --------------------------------------------------

veritabani_yolu = Path(
    "data/database/urbanai.db"
)


# --------------------------------------------------
# VERİ TABANI BAĞLANTISI
# --------------------------------------------------

def baglanti_olustur():

    if not veritabani_yolu.exists():
        raise FileNotFoundError(
            f"Veri tabanı bulunamadı: "
            f"{veritabani_yolu}"
        )

    baglanti = sqlite3.connect(
        veritabani_yolu
    )

    # Sorgu sonuçlarında sütunlara isimleriyle
    # erişebilmemizi sağlar.
    baglanti.row_factory = sqlite3.Row

    baglanti.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return baglanti


# --------------------------------------------------
# KÜTÜPHANE HİZMET TÜRÜ ID'Sİ
# --------------------------------------------------

def kutuphane_hizmet_turu_id_getir(
    baglanti
):

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
            "Kütüphane hizmet türü bulunamadı."
        )

    return sonuc["id"]


# --------------------------------------------------
# İLÇE HARİTA VERİSİNİ GETİR
# --------------------------------------------------

def ilce_harita_verisini_getir(
    baglanti,
    hizmet_turu_id,
):

    sonuclar = baglanti.execute(
        """
        SELECT
            districts.id,
            districts.name,
            districts.population_2025,
            districts.geometry_geojson,

            district_metrics.facility_count,
            district_metrics.service_per_100k,
            district_metrics.people_per_facility,
            district_metrics.priority_score,
            district_metrics.priority_level,
            district_metrics.data_status,
            district_metrics.priority_rank

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

    geojson_features = []

    for satir in sonuclar:

        if satir["geometry_geojson"] is None:
            raise ValueError(
                f"{satir['name']} ilçesinin "
                "geometrisi bulunamadı."
            )

        geometri = json.loads(
            satir["geometry_geojson"]
        )

        feature = {
            "type": "Feature",

            "properties": {
                "district_id": satir["id"],
                "name": satir["name"],
                "population": (
                    satir["population_2025"]
                ),
                "facility_count": (
                    satir["facility_count"]
                ),
                "service_per_100k": (
                    satir["service_per_100k"]
                ),
                "people_per_facility": (
                    satir["people_per_facility"]
                ),
                "priority_score": (
                    satir["priority_score"]
                ),
                "priority_level": (
                    satir["priority_level"]
                ),
                "data_status": (
                    satir["data_status"]
                ),
                "priority_rank": (
                    satir["priority_rank"]
                ),
            },

            "geometry": geometri,
        }

        geojson_features.append(
            feature
        )

    return {
        "type": "FeatureCollection",
        "features": geojson_features,
    }


# --------------------------------------------------
# GÜVENİLİR KÜTÜPHANE NOKTALARINI GETİR
# --------------------------------------------------

def kutuphane_noktalarini_getir(
    baglanti,
    hizmet_turu_id,
):

    sonuclar = baglanti.execute(
        """
        SELECT
            facilities.id,
            facilities.name,
            districts.name AS district_name,
            facilities.address,
            facilities.found_address,
            facilities.latitude,
            facilities.longitude,
            facilities.coordinate_status

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

    return [
        {
            "id": satir["id"],
            "name": satir["name"],
            "district_name": (
                satir["district_name"]
            ),
            "address": satir["address"],
            "found_address": (
                satir["found_address"]
            ),
            "latitude": satir["latitude"],
            "longitude": satir["longitude"],
            "coordinate_status": (
                satir["coordinate_status"]
            ),
        }
        for satir in sonuclar
    ]


# --------------------------------------------------
# ANA ÇALIŞMA
# --------------------------------------------------

def main():

    with baglanti_olustur() as baglanti:

        hizmet_turu_id = (
            kutuphane_hizmet_turu_id_getir(
                baglanti
            )
        )

        ilce_geojson = (
            ilce_harita_verisini_getir(
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


    ilce_sayisi = len(
        ilce_geojson["features"]
    )

    kutuphane_sayisi = len(
        kutuphane_noktalari
    )


    print(
        "VERİ TABANINDAN HARİTA VERİSİ"
    )

    print("-" * 45)

    print(
        f"İlçe geometrisi sayısı: "
        f"{ilce_sayisi}"
    )

    print(
        f"Güvenilir kütüphane noktası: "
        f"{kutuphane_sayisi}"
    )


    puanli_ilce_sayisi = sum(
        1
        for feature
        in ilce_geojson["features"]
        if feature["properties"][
            "priority_score"
        ] is not None
    )

    dogrulama_gereken_sayi = (
        ilce_sayisi
        - puanli_ilce_sayisi
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
        "\nİlk 5 güvenilir kütüphane noktası:"
    )

    for kutuphane in kutuphane_noktalari[:5]:

        print(
            f"- {kutuphane['name']} | "
            f"{kutuphane['district_name']} | "
            f"{kutuphane['latitude']:.6f}, "
            f"{kutuphane['longitude']:.6f}"
        )


if __name__ == "__main__":
    main()
    