from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from shapely.geometry import mapping


# ==========================================================
# PROJE KÖKÜ
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

VERITABANI_YOLU = (
    PROJE_KOKU
    / "data"
    / "database"
    / "urbanai.db"
)

COGRAFI_CRS = "EPSG:4326"


# ==========================================================
# TÜRKÇE KARAKTER DÖNÜŞÜMÜ
# ==========================================================

TURKCE_KARAKTER_TABLOSU = str.maketrans(
    {
        "ç": "c",
        "Ç": "c",
        "ğ": "g",
        "Ğ": "g",
        "ı": "i",
        "İ": "i",
        "ö": "o",
        "Ö": "o",
        "ş": "s",
        "Ş": "s",
        "ü": "u",
        "Ü": "u",
    }
)


# ==========================================================
# KOMUT SATIRI ARGÜMANLARI
# ==========================================================

def argumanlari_oku() -> argparse.Namespace:
    """
    Veritabanına aktarılacak ilçe ve analiz
    yıllarını komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Aday bölge değerlendirme sonuçlarını "
            "UrbanAI SQLite veritabanına aktarır."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help="Aktarılacak ilçe adı. Örnek: Esenyurt",
    )

    parser.add_argument(
        "--analiz-yili",
        type=int,
        default=2026,
        help="Hizmet ihtiyacı analiz yılı. Varsayılan: 2026",
    )

    parser.add_argument(
        "--worldcover-yili",
        type=int,
        choices=[
            2020,
            2021,
        ],
        default=2021,
        help="Kullanılan WorldCover yılı. Varsayılan: 2021",
    )

    argumanlar = parser.parse_args()

    argumanlar.ilce = argumanlar.ilce.strip()

    if not argumanlar.ilce:
        parser.error(
            "--ilce değeri boş bırakılamaz."
        )

    return argumanlar


# ==========================================================
# GÜVENLİ KLASÖR ADI
# ==========================================================

def slug_olustur(
    metin: str,
) -> str:
    """
    Türkçe ilçe adını güvenli klasör adına dönüştürür.

    Örnek:
    Esenyurt      -> esenyurt
    Küçükçekmece -> kucukcekmece
    """

    temiz_metin = (
        metin
        .translate(
            TURKCE_KARAKTER_TABLOSU
        )
        .lower()
        .strip()
    )

    temiz_metin = unicodedata.normalize(
        "NFKD",
        temiz_metin,
    )

    temiz_metin = "".join(
        karakter
        for karakter in temiz_metin
        if not unicodedata.combining(
            karakter
        )
    )

    temiz_metin = re.sub(
        r"[^a-z0-9]+",
        "_",
        temiz_metin,
    )

    temiz_metin = temiz_metin.strip(
        "_"
    )

    if not temiz_metin:
        raise ValueError(
            "İlçe adından güvenli klasör adı oluşturulamadı."
        )

    return temiz_metin


# ==========================================================
# DOSYA YOLLARI
# ==========================================================

def dosya_yollarini_olustur(
    ilce_slug: str,
) -> dict[str, Path]:
    """
    Veritabanı ve aday bölge GeoJSON yollarını oluşturur.
    """

    aday_degerlendirme_klasoru = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
        / "candidate_evaluation"
    )

    return {
        "veritabani": VERITABANI_YOLU,

        "aday_geojson": (
            aday_degerlendirme_klasoru
            / "aday_bolge_degerlendirme_haritasi.geojson"
        ),
    }


# ==========================================================
# BOŞ DEĞER TEMİZLEME
# ==========================================================

def temiz_deger(
    deger: Any,
) -> Any:
    """
    Pandas NaN değerlerini SQLite için None değerine
    dönüştürür.
    """

    if deger is None:
        return None

    try:
        if pd.isna(
            deger
        ):
            return None

    except (
        TypeError,
        ValueError,
    ):
        pass

    return deger


# ==========================================================
# ADAY VERİLERİNİ OKUMA
# ==========================================================

def aday_verilerini_oku(
    geojson_yolu: Path,
) -> gpd.GeoDataFrame:
    """
    Harita için oluşturulan birleştirilmiş
    aday bölge GeoJSON dosyasını okur.
    """

    if not geojson_yolu.exists():
        raise FileNotFoundError(
            "Aday bölge değerlendirme GeoJSON dosyası "
            "bulunamadı:\n"
            f"{geojson_yolu}\n\n"
            "Önce aday_bolge_degerlendirme_haritasi.py "
            "dosyasını çalıştır."
        )

    adaylar = gpd.read_file(
        geojson_yolu
    )

    gerekli_sutunlar = [
        "cell_id",
        "district_name",
        "service_need_rank",
        "service_need_score",
        "service_need_level",
        "nearest_library_name",
        "nearest_library_distance_km",
        "built_up_pct",
        "vegetation_pct",
        "open_bare_pct",
        "water_wetland_pct",
        "worldcover_coverage_pct",
        "site_review_status",
        "site_review_explanation",
        "evaluation_text",
        "geometry",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in adaylar.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Aday bölge GeoJSON dosyasında eksik "
            "sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    if adaylar.crs is None:
        raise ValueError(
            "Aday bölge GeoJSON dosyasında "
            "koordinat sistemi bulunamadı."
        )

    adaylar = adaylar.to_crs(
        COGRAFI_CRS
    )

    adaylar[
        "cell_id"
    ] = (
        adaylar[
            "cell_id"
        ]
        .astype(str)
        .str.strip()
    )

    adaylar[
        "district_name"
    ] = (
        adaylar[
            "district_name"
        ]
        .astype(str)
        .str.strip()
    )

    adaylar = adaylar.dropna(
        subset=[
            "cell_id",
            "district_name",
            "geometry",
        ]
    ).copy()

    adaylar = adaylar[
        ~adaylar.geometry.is_empty
    ].copy()

    if adaylar.empty:
        raise ValueError(
            "Veritabanına aktarılabilecek aday "
            "bölge bulunamadı."
        )

    return adaylar


# ==========================================================
# VERİTABANI BAĞLANTISI
# ==========================================================

def veritabanina_baglan(
    veritabani_yolu: Path,
) -> sqlite3.Connection:
    """
    SQLite veritabanına bağlantı oluşturur.
    """

    veritabani_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    baglanti = sqlite3.connect(
        veritabani_yolu
    )

    baglanti.row_factory = sqlite3.Row

    baglanti.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return baglanti


# ==========================================================
# ADAY BÖLGE TABLOSU
# ==========================================================

def aday_bolge_tablosunu_olustur(
    baglanti: sqlite3.Connection,
) -> None:
    """
    candidate_areas tablosunu bulunmuyorsa oluşturur.
    """

    baglanti.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            cell_id TEXT NOT NULL,
            district_name TEXT NOT NULL,

            analysis_year INTEGER NOT NULL,
            worldcover_year INTEGER NOT NULL,

            service_need_rank INTEGER,
            service_need_score REAL,
            service_need_level TEXT,

            nearest_library_name TEXT,
            nearest_library_distance_km REAL,

            built_up_pct REAL,
            vegetation_pct REAL,
            open_bare_pct REAL,
            water_wetland_pct REAL,
            worldcover_coverage_pct REAL,

            site_review_status TEXT,
            site_review_explanation TEXT,
            evaluation_text TEXT,

            center_latitude REAL,
            center_longitude REAL,

            geometry_geojson TEXT NOT NULL,

            updated_at_utc TEXT NOT NULL,

            UNIQUE (
                district_name,
                cell_id,
                analysis_year,
                worldcover_year
            )
        );
        """
    )

    baglanti.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_candidate_areas_district
        ON candidate_areas (
            district_name
        );
        """
    )

    baglanti.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_candidate_areas_need_score
        ON candidate_areas (
            service_need_score DESC
        );
        """
    )

    baglanti.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_candidate_areas_site_status
        ON candidate_areas (
            site_review_status
        );
        """
    )

    baglanti.commit()


# ==========================================================
# TEK ADAY KAYDINI HAZIRLAMA
# ==========================================================

def aday_kaydini_hazirla(
    satir: pd.Series,
    analiz_yili: int,
    worldcover_yili: int,
    zaman_bilgisi: str,
) -> tuple[Any, ...]:
    """
    GeoDataFrame satırını SQLite'a yazılabilecek
    bir kayıt hâline dönüştürür.
    """

    geometri = satir[
        "geometry"
    ]

    merkez_noktasi = (
        geometri
        .representative_point()
    )

    geometri_json = json.dumps(
        mapping(
            geometri
        ),
        ensure_ascii=False,
    )

    return (
        str(
            satir[
                "cell_id"
            ]
        ),

        str(
            satir[
                "district_name"
            ]
        ),

        analiz_yili,

        worldcover_yili,

        temiz_deger(
            satir[
                "service_need_rank"
            ]
        ),

        temiz_deger(
            satir[
                "service_need_score"
            ]
        ),

        temiz_deger(
            satir[
                "service_need_level"
            ]
        ),

        temiz_deger(
            satir[
                "nearest_library_name"
            ]
        ),

        temiz_deger(
            satir[
                "nearest_library_distance_km"
            ]
        ),

        temiz_deger(
            satir[
                "built_up_pct"
            ]
        ),

        temiz_deger(
            satir[
                "vegetation_pct"
            ]
        ),

        temiz_deger(
            satir[
                "open_bare_pct"
            ]
        ),

        temiz_deger(
            satir[
                "water_wetland_pct"
            ]
        ),

        temiz_deger(
            satir[
                "worldcover_coverage_pct"
            ]
        ),

        temiz_deger(
            satir[
                "site_review_status"
            ]
        ),

        temiz_deger(
            satir[
                "site_review_explanation"
            ]
        ),

        temiz_deger(
            satir[
                "evaluation_text"
            ]
        ),

        float(
            merkez_noktasi.y
        ),

        float(
            merkez_noktasi.x
        ),

        geometri_json,

        zaman_bilgisi,
    )


# ==========================================================
# ADAYLARI VERİTABANINA AKTARMA
# ==========================================================

def adaylari_veritabanina_aktar(
    baglanti: sqlite3.Connection,
    adaylar: gpd.GeoDataFrame,
    analiz_yili: int,
    worldcover_yili: int,
) -> int:
    """
    Aday bölgeleri candidate_areas tablosuna ekler.

    Aynı kayıt daha önce varsa günceller.
    """

    zaman_bilgisi = datetime.now(
        timezone.utc
    ).isoformat()

    sql_sorgusu = """
        INSERT INTO candidate_areas (
            cell_id,
            district_name,
            analysis_year,
            worldcover_year,
            service_need_rank,
            service_need_score,
            service_need_level,
            nearest_library_name,
            nearest_library_distance_km,
            built_up_pct,
            vegetation_pct,
            open_bare_pct,
            water_wetland_pct,
            worldcover_coverage_pct,
            site_review_status,
            site_review_explanation,
            evaluation_text,
            center_latitude,
            center_longitude,
            geometry_geojson,
            updated_at_utc
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT (
            district_name,
            cell_id,
            analysis_year,
            worldcover_year
        )
        DO UPDATE SET
            service_need_rank =
                excluded.service_need_rank,

            service_need_score =
                excluded.service_need_score,

            service_need_level =
                excluded.service_need_level,

            nearest_library_name =
                excluded.nearest_library_name,

            nearest_library_distance_km =
                excluded.nearest_library_distance_km,

            built_up_pct =
                excluded.built_up_pct,

            vegetation_pct =
                excluded.vegetation_pct,

            open_bare_pct =
                excluded.open_bare_pct,

            water_wetland_pct =
                excluded.water_wetland_pct,

            worldcover_coverage_pct =
                excluded.worldcover_coverage_pct,

            site_review_status =
                excluded.site_review_status,

            site_review_explanation =
                excluded.site_review_explanation,

            evaluation_text =
                excluded.evaluation_text,

            center_latitude =
                excluded.center_latitude,

            center_longitude =
                excluded.center_longitude,

            geometry_geojson =
                excluded.geometry_geojson,

            updated_at_utc =
                excluded.updated_at_utc;
    """

    kayitlar = [
        aday_kaydini_hazirla(
            satir=satir,
            analiz_yili=analiz_yili,
            worldcover_yili=worldcover_yili,
            zaman_bilgisi=zaman_bilgisi,
        )
        for _, satir in adaylar.iterrows()
    ]

    baglanti.executemany(
        sql_sorgusu,
        kayitlar,
    )

    baglanti.commit()

    return len(
        kayitlar
    )


# ==========================================================
# VERİTABANI KONTROLÜ
# ==========================================================

def kayitlari_kontrol_et(
    baglanti: sqlite3.Connection,
    ilce_adi: str,
    analiz_yili: int,
    worldcover_yili: int,
) -> list[sqlite3.Row]:
    """
    Aktarılan aday bölgeleri tekrar veritabanından okur.
    """

    sorgu = """
        SELECT
            cell_id,
            district_name,
            service_need_rank,
            service_need_score,
            service_need_level,
            nearest_library_distance_km,
            site_review_status,
            built_up_pct,
            vegetation_pct,
            open_bare_pct
        FROM candidate_areas
        WHERE district_name = ?
          AND analysis_year = ?
          AND worldcover_year = ?
        ORDER BY
            service_need_rank ASC,
            service_need_score DESC;
    """

    sonuc = baglanti.execute(
        sorgu,
        (
            ilce_adi,
            analiz_yili,
            worldcover_yili,
        ),
    ).fetchall()

    return sonuc


# ==========================================================
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozetini_yazdir(
    ilce_adi: str,
    aktarilan_kayit_sayisi: int,
    kayitlar: list[sqlite3.Row],
    veritabani_yolu: Path,
) -> None:
    """
    Veritabanı aktarım sonucunu terminalde gösterir.
    """

    print()
    print("=" * 95)
    print("ADAY BÖLGELER VERİTABANINA AKTARILDI")
    print("=" * 95)

    print()
    print(
        "İlçe:",
        ilce_adi,
    )

    print(
        "Aktarılan veya güncellenen kayıt:",
        aktarilan_kayit_sayisi,
    )

    print(
        "Veritabanında bulunan ilçe kaydı:",
        len(
            kayitlar
        ),
    )

    print()
    print(
        "Veritabanı kayıtları:"
    )

    for kayit in kayitlar:

        print()
        print(
            f"  {kayit['service_need_rank']}. sıra "
            f"— {kayit['cell_id']}"
        )

        print(
            f"    Hizmet ihtiyacı: "
            f"{kayit['service_need_level']} "
            f"({kayit['service_need_score']:.2f})"
        )

        print(
            f"    Kütüphaneye uzaklık: "
            f"{kayit['nearest_library_distance_km']:.2f} km"
        )

        print(
            f"    Yer inceleme durumu: "
            f"{kayit['site_review_status']}"
        )

    print()
    print(
        "SQLite veritabanı:"
    )

    print(
        f"  {veritabani_yolu}"
    )

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    Aday bölge değerlendirmelerini SQLite
    veritabanına aktarır.
    """

    argumanlar = argumanlari_oku()

    ilce_adi = argumanlar.ilce

    ilce_slug = slug_olustur(
        ilce_adi
    )

    yollar = dosya_yollarini_olustur(
        ilce_slug
    )

    print()
    print(
        "Aktarım ayarları:"
    )

    print(
        f"  İlçe: {ilce_adi}"
    )

    print(
        f"  Analiz yılı: {argumanlar.analiz_yili}"
    )

    print(
        f"  WorldCover yılı: "
        f"{argumanlar.worldcover_yili}"
    )

    print()
    print(
        "Aday bölge GeoJSON dosyası okunuyor..."
    )

    adaylar = aday_verilerini_oku(
        yollar[
            "aday_geojson"
        ]
    )

    print(
        "SQLite veritabanına bağlanılıyor..."
    )

    with veritabanina_baglan(
        yollar[
            "veritabani"
        ]
    ) as baglanti:

        print(
            "candidate_areas tablosu kontrol ediliyor..."
        )

        aday_bolge_tablosunu_olustur(
            baglanti
        )

        print(
            "Aday bölgeler veritabanına aktarılıyor..."
        )

        aktarilan_kayit_sayisi = (
            adaylari_veritabanina_aktar(
                baglanti=baglanti,
                adaylar=adaylar,
                analiz_yili=argumanlar.analiz_yili,
                worldcover_yili=(
                    argumanlar.worldcover_yili
                ),
            )
        )

        print(
            "Aktarılan kayıtlar kontrol ediliyor..."
        )

        kayitlar = kayitlari_kontrol_et(
            baglanti=baglanti,
            ilce_adi=ilce_adi,
            analiz_yili=argumanlar.analiz_yili,
            worldcover_yili=(
                argumanlar.worldcover_yili
            ),
        )

    terminal_ozetini_yazdir(
        ilce_adi=ilce_adi,
        aktarilan_kayit_sayisi=(
            aktarilan_kayit_sayisi
        ),
        kayitlar=kayitlar,
        veritabani_yolu=yollar[
            "veritabani"
        ],
    )


if __name__ == "__main__":
    main()