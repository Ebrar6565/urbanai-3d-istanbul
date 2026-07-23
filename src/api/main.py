from pathlib import Path
import sqlite3

from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException, Query


# --------------------------------------------------
# PROJE VE VERİ TABANI YOLLARI
# --------------------------------------------------

# Bu dosya:
# proje_koku/src/api/main.py
#
# parents[2] ile proje ana klasörüne çıkıyoruz.
proje_koku = Path(
    __file__
).resolve().parents[2]


veritabani_yolu = (
    proje_koku
    / "data"
    / "database"
    / "urbanai.db"
)


# --------------------------------------------------
# FASTAPI UYGULAMASI
# --------------------------------------------------

app = FastAPI(
    title="UrbanAI 3D İstanbul API",

    description=(
        "İstanbul ilçe, kütüphane ve "
        "hizmet önceliği verilerini sunan API."
    ),

    version="0.1.0",
)

# --------------------------------------------------
# CORS AYARLARI
# --------------------------------------------------

# Frontend 8000 portunda, API ise 8001 portunda
# çalıştığı için tarayıcı bunları farklı kaynaklar
# olarak değerlendirir.
izin_verilen_adresler = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]


app.add_middleware(
    CORSMiddleware,

    # Yalnızca yerel frontend adresleri
    # API'ye tarayıcı üzerinden erişebilir.
    allow_origins=izin_verilen_adresler,

    # Şu anda kullanıcı girişi, cookie veya
    # kimlik doğrulama kullanmıyoruz.
    allow_credentials=False,

    # Mevcut API uçlarımız yalnızca veri okuyor.
    allow_methods=[
        "GET",
    ],

    # Tarayıcının gönderdiği standart başlıklara
    # izin veriyoruz.
    allow_headers=[
        "*",
    ],
)

# --------------------------------------------------
# VERİ TABANI BAĞLANTISI
# --------------------------------------------------

def baglanti_olustur():
    """
    SQLite veri tabanına bağlantı oluşturur.
    """

    if not veritabani_yolu.exists():
        raise FileNotFoundError(
            "UrbanAI veri tabanı bulunamadı: "
            f"{veritabani_yolu}"
        )

    baglanti = sqlite3.connect(
        veritabani_yolu
    )

    # SQL sonuçlarındaki sütunlara isimleriyle
    # ulaşmamızı sağlar.
    baglanti.row_factory = sqlite3.Row

    baglanti.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return baglanti


# --------------------------------------------------
# ANA API ADRESİ
# --------------------------------------------------

@app.get(
    "/",
    tags=["Sistem"],
)
def ana_sayfa():
    """
    API'nin çalışıp çalışmadığını kontrol eder.
    """

    return {
        "proje": "UrbanAI 3D İstanbul",
        "api_durumu": "çalışıyor",
        "veri_tabani": "SQLite",
        "dokumantasyon": "/docs",
    }


# --------------------------------------------------
# VERİ TABANI ÖZETİ
# --------------------------------------------------

@app.get(
    "/api/ozet",
    tags=["Analiz"],
)
def veri_tabani_ozeti():
    """
    Veri tabanındaki temel kayıt sayılarını döndürür.
    """

    with baglanti_olustur() as baglanti:

        tablo_adlari = [
            "districts",
            "service_types",
            "facilities",
            "district_metrics",
        ]

        tablo_sayilari = {}

        for tablo_adi in tablo_adlari:

            kayit_sayisi = baglanti.execute(
                f"""
                SELECT COUNT(*)
                FROM {tablo_adi};
                """
            ).fetchone()[0]

            tablo_sayilari[
                tablo_adi
            ] = kayit_sayisi


        koordinat_sonuclari = (
            baglanti.execute(
                """
                SELECT
                    coordinate_status,
                    COUNT(*) AS kayit_sayisi

                FROM facilities

                GROUP BY coordinate_status

                ORDER BY coordinate_status;
                """
            ).fetchall()
        )


        koordinat_durumlari = {
            satir["coordinate_status"]:
                satir["kayit_sayisi"]

            for satir
            in koordinat_sonuclari
        }


        puanli_ilce_sayisi = (
            baglanti.execute(
                """
                SELECT COUNT(*)

                FROM district_metrics

                WHERE priority_score
                      IS NOT NULL;
                """
            ).fetchone()[0]
        )


        dogrulama_gereken_sayi = (
            baglanti.execute(
                """
                SELECT COUNT(*)

                FROM district_metrics

                WHERE priority_score
                      IS NULL;
                """
            ).fetchone()[0]
        )


    return {
        "tablo_kayit_sayilari":
            tablo_sayilari,

        "koordinat_durumlari":
            koordinat_durumlari,

        "puanli_ilce_sayisi":
            puanli_ilce_sayisi,

        "veri_dogrulamasi_gereken_ilce":
            dogrulama_gereken_sayi,

        "analiz_yili": 2025,
    }


# --------------------------------------------------
# ÖNCELİKLİ İLÇELER
# --------------------------------------------------

@app.get(
    "/api/oncelikli-ilceler",
    tags=["Analiz"],
)
def oncelikli_ilceleri_getir(

    limit: int = Query(
        default=10,
        ge=1,
        le=39,
        description=(
            "Döndürülecek ilçe sayısı"
        ),
    ),
):
    """
    Öncelik puanına göre sıralanmış ilçeleri döndürür.
    """

    with baglanti_olustur() as baglanti:

        sonuclar = baglanti.execute(
            """
            SELECT
                district_metrics.priority_rank
                    AS sira,

                districts.name
                    AS ilce,

                district_metrics.population
                    AS nufus,

                district_metrics.facility_count
                    AS kutuphane_sayisi,

                district_metrics.service_per_100k
                    AS yuz_bin_kisiye_kutuphane,

                district_metrics.priority_score
                    AS oncelik_puani,

                district_metrics.priority_level
                    AS oncelik_seviyesi

            FROM district_metrics

            INNER JOIN districts
                ON districts.id =
                   district_metrics.district_id

            INNER JOIN service_types
                ON service_types.id =
                   district_metrics.service_type_id

            WHERE service_types.name = ?

              AND district_metrics.analysis_year = ?

              AND district_metrics.priority_score
                  IS NOT NULL

            ORDER BY
                district_metrics.priority_rank

            LIMIT ?;
            """,
            (
                "Kütüphane",
                2025,
                limit,
            ),
        ).fetchall()


    ilceler = [
        dict(satir)
        for satir in sonuclar
    ]


    return {
        "hizmet_turu": "Kütüphane",
        "analiz_yili": 2025,
        "sonuc_sayisi": len(ilceler),
        "ilceler": ilceler,
    }
# --------------------------------------------------
# KÜTÜPHANELERİ GETİR
# --------------------------------------------------

@app.get(
    "/api/kutuphaneler",
    tags=["Kütüphaneler"],
)
def kutuphaneleri_getir(

    ilce: str | None = Query(
        default=None,
        description=(
            "Kütüphanelerin filtreleneceği ilçe adı. "
            "Boş bırakılırsa bütün ilçeler kullanılır."
        ),
    ),

    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description=(
            "Döndürülecek en fazla kütüphane sayısı"
        ),
    ),
):
    """
    Güvenilir koordinatı bulunan kütüphaneleri
    listeler.

    İlçe parametresi verilirse sonuçları yalnızca
    o ilçeye göre filtreler.
    """

    with baglanti_olustur() as baglanti:

        sonuclar = baglanti.execute(
            """
            SELECT
                facilities.id,

                facilities.name
                    AS kutuphane_adi,

                districts.name
                    AS ilce,

                facilities.address
                    AS adres,

                facilities.working_hours
                    AS calisma_saatleri,

                facilities.working_days
                    AS calisma_gunleri,

                facilities.latitude
                    AS enlem,

                facilities.longitude
                    AS boylam,

                facilities.coordinate_status
                    AS koordinat_durumu

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

              AND (
                    ? IS NULL
                    OR districts.name = ?
              )

            ORDER BY
                districts.name,
                facilities.name

            LIMIT ?;
            """,
            (
                "Kütüphane",
                ilce,
                ilce,
                limit,
            ),
        ).fetchall()


    kutuphaneler = [
        dict(satir)
        for satir in sonuclar
    ]


    return {
        "hizmet_turu": "Kütüphane",

        "ilce_filtresi": ilce,

        "sonuc_sayisi": len(
            kutuphaneler
        ),

        "yalnizca_guvenilir_koordinatlar":
            True,

        "kutuphaneler": kutuphaneler,
    }
# --------------------------------------------------
# BÜTÜN İLÇELERİ GETİR
# --------------------------------------------------

@app.get(
    "/api/ilceler",
    tags=["İlçeler"],
)
def ilceleri_getir():
    """
    İstanbul'un 39 ilçesini kütüphane hizmeti
    analiz sonuçlarıyla birlikte döndürür.
    """

    with baglanti_olustur() as baglanti:

        sonuclar = baglanti.execute(
            """
            SELECT
                districts.id,

                districts.name
                    AS ilce,

                districts.population_2025
                    AS nufus,

                district_metrics.facility_count
                    AS kutuphane_sayisi,

                district_metrics.service_per_100k
                    AS yuz_bin_kisiye_kutuphane,

                district_metrics.people_per_facility
                    AS kutuphane_basina_kisi,

                district_metrics.priority_score
                    AS oncelik_puani,

                district_metrics.priority_level
                    AS oncelik_seviyesi,

                district_metrics.priority_rank
                    AS oncelik_sirasi,

                district_metrics.data_status
                    AS veri_durumu

            FROM districts

            LEFT JOIN district_metrics
                ON district_metrics.district_id =
                   districts.id

               AND district_metrics.analysis_year = ?

            LEFT JOIN service_types
                ON service_types.id =
                   district_metrics.service_type_id

            WHERE service_types.name = ?

            ORDER BY districts.name;
            """,
            (
                2025,
                "Kütüphane",
            ),
        ).fetchall()


    ilceler = [
        dict(satir)
        for satir in sonuclar
    ]


    return {
        "sehir": "İstanbul",
        "hizmet_turu": "Kütüphane",
        "analiz_yili": 2025,
        "sonuc_sayisi": len(ilceler),
        "ilceler": ilceler,
    }


# --------------------------------------------------
# TEK İLÇENİN DETAYINI GETİR
# --------------------------------------------------

@app.get(
    "/api/ilceler/{ilce_adi}",
    tags=["İlçeler"],
)
def ilce_detayini_getir(
    ilce_adi: str,
):
    """
    Seçilen ilçenin analiz bilgilerini ve veri
    tabanındaki kütüphane kayıtlarını döndürür.
    """

    with baglanti_olustur() as baglanti:

        ilce_sonucu = baglanti.execute(
            """
            SELECT
                districts.id,

                districts.name
                    AS ilce,

                districts.district_code
                    AS ilce_kodu,

                districts.population_2025
                    AS nufus,

                district_metrics.facility_count
                    AS kutuphane_sayisi,

                district_metrics.service_per_100k
                    AS yuz_bin_kisiye_kutuphane,

                district_metrics.people_per_facility
                    AS kutuphane_basina_kisi,

                district_metrics.population_score
                    AS nufus_puani,

                district_metrics.service_gap_score
                    AS hizmet_acigi_puani,

                district_metrics.priority_score
                    AS oncelik_puani,

                district_metrics.priority_level
                    AS oncelik_seviyesi,

                district_metrics.priority_rank
                    AS oncelik_sirasi,

                district_metrics.data_status
                    AS veri_durumu

            FROM districts

            LEFT JOIN district_metrics
                ON district_metrics.district_id =
                   districts.id

               AND district_metrics.analysis_year = ?

            LEFT JOIN service_types
                ON service_types.id =
                   district_metrics.service_type_id

            WHERE districts.name = ?

              AND service_types.name = ?;
            """,
            (
                2025,
                ilce_adi,
                "Kütüphane",
            ),
        ).fetchone()


        if ilce_sonucu is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"'{ilce_adi}' isimli ilçe "
                    "veri tabanında bulunamadı."
                ),
            )


        kutuphane_sonuclari = baglanti.execute(
            """
            SELECT
                facilities.id,

                facilities.name
                    AS kutuphane_adi,

                facilities.address
                    AS adres,

                facilities.working_hours
                    AS calisma_saatleri,

                facilities.working_days
                    AS calisma_gunleri,

                facilities.latitude
                    AS enlem,

                facilities.longitude
                    AS boylam,

                facilities.coordinate_status
                    AS koordinat_durumu

            FROM facilities

            INNER JOIN districts
                ON districts.id =
                   facilities.district_id

            INNER JOIN service_types
                ON service_types.id =
                   facilities.service_type_id

            WHERE districts.name = ?

              AND service_types.name = ?

            ORDER BY facilities.name;
            """,
            (
                ilce_adi,
                "Kütüphane",
            ),
        ).fetchall()


    kutuphaneler = [
        dict(satir)
        for satir in kutuphane_sonuclari
    ]


    return {
        "analiz_yili": 2025,

        "hizmet_turu": "Kütüphane",

        "ilce_bilgileri":
            dict(ilce_sonucu),

        "veri_tabanindaki_kutuphane_kaydi":
            len(kutuphaneler),

        "kutuphaneler":
            kutuphaneler,
    }

from src.api.aday_bolgeler import router as aday_bolgeler_router

app.include_router(aday_bolgeler_router)