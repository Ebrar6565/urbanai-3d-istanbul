from __future__ import annotations

import argparse
import json
import re
import sqlite3
import unicodedata

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import rasterio

from pyproj import Transformer
from shapely.geometry import box
from shapely.ops import transform as shapely_transform


# ==========================================================
# PROJE YOLLARI VE AYARLAR
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

VERITABANI_YOLU = (
    PROJE_KOKU
    / "data"
    / "database"
    / "urbanai.db"
)

COGRAFI_CRS = "EPSG:4326"

ISTANBUL_METRIK_CRS = "EPSG:32635"

HAZIR_KAPSAMA_ESIGI = 95.0


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
    Veritabanına aktarılacak ilçeyi komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Sentinel-2 sahne ve RGB yama bilgilerini "
            "UrbanAI SQLite veritabanına aktarır."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help="Aktarılacak ilçe adı. Örnek: Pendik",
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
    İlçe adını güvenli klasör adına dönüştürür.
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

    temiz_metin = temiz_metin.strip("_")

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
    İlçeye ait sahne, manifest ve veritabanı
    yollarını oluşturur.
    """

    islenmis_klasor = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
    )

    return {
        "metadata_json": (
            islenmis_klasor
            / "secilen_sentinel2_sahnesi.json"
        ),

        "manifest_csv": (
            islenmis_klasor
            / "rgb_yama_manifest.csv"
        ),

        "veritabani": VERITABANI_YOLU,
    }


# ==========================================================
# JSON OKUMA
# ==========================================================

def json_dosyasi_oku(
    dosya_yolu: Path,
) -> dict[str, Any]:
    """
    JSON dosyasını okuyup sözlük olarak döndürür.
    """

    if not dosya_yolu.exists():
        raise FileNotFoundError(
            "Metadata JSON dosyası bulunamadı:\n"
            f"{dosya_yolu}"
        )

    try:
        return json.loads(
            dosya_yolu.read_text(
                encoding="utf-8"
            )
        )

    except json.JSONDecodeError as hata:
        raise ValueError(
            "Metadata JSON dosyası geçerli değil:\n"
            f"{dosya_yolu}"
        ) from hata


# ==========================================================
# SAHNE METADATA OKUMA
# ==========================================================

def sahne_metadata_oku(
    metadata_yolu: Path,
    beklenen_ilce_slug: str,
) -> dict[str, Any]:
    """
    Seçilmiş Sentinel-2 sahnesinin metadata
    dosyasını okur ve doğrular.
    """

    metadata = json_dosyasi_oku(
        metadata_yolu
    )

    gerekli_alanlar = [
        "item_id",
        "datetime",
        "cloud_cover_pct",
        "collection",
    ]

    eksik_alanlar = [
        alan
        for alan in gerekli_alanlar
        if alan not in metadata
    ]

    if eksik_alanlar:
        raise ValueError(
            "Sahne metadata dosyasında eksik alanlar var:\n"
            + "\n".join(
                eksik_alanlar
            )
        )

    metadata_slug = str(
        metadata.get(
            "district_slug",
            "",
        )
    ).strip()

    if (
        metadata_slug
        and metadata_slug != beklenen_ilce_slug
    ):
        raise ValueError(
            "Metadata farklı bir ilçeye ait.\n"
            f"Beklenen: {beklenen_ilce_slug}\n"
            f"Bulunan: {metadata_slug}"
        )

    return metadata


# ==========================================================
# RGB MANİFEST OKUMA
# ==========================================================

def rgb_manifest_oku(
    manifest_yolu: Path,
    beklenen_ilce_slug: str,
) -> pd.DataFrame:
    """
    İlçeye ait RGB yama manifest dosyasını okur.
    """

    if not manifest_yolu.exists():
        raise FileNotFoundError(
            "RGB manifest dosyası bulunamadı:\n"
            f"{manifest_yolu}\n\n"
            "Önce sentinel2_rgb_yamalari.py dosyasını çalıştır."
        )

    dataframe = pd.read_csv(
        manifest_yolu
    )

    gerekli_sutunlar = [
        "patch_id",
        "cell_id",
        "district_name",
        "district_candidate_rank",
        "nearest_library_distance_km",
        "width_pixels",
        "height_pixels",
        "band_count",
        "dtype",
        "crs",
        "valid_pixel_pct",
        "min_longitude",
        "min_latitude",
        "max_longitude",
        "max_latitude",
        "geotiff_path",
        "png_path",
        "png_relative_path",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in dataframe.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "RGB manifest dosyasında eksik sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    if "district_slug" in dataframe.columns:
        farkli_ilce = dataframe[
            dataframe[
                "district_slug"
            ]
            .astype(str)
            .str.strip()
            .ne(
                beklenen_ilce_slug
            )
        ]

        if not farkli_ilce.empty:
            raise ValueError(
                "Manifest dosyasında farklı ilçeye "
                "ait kayıt bulundu."
            )

    sayisal_sutunlar = [
        "district_candidate_rank",
        "nearest_library_distance_km",
        "width_pixels",
        "height_pixels",
        "band_count",
        "valid_pixel_pct",
        "min_longitude",
        "min_latitude",
        "max_longitude",
        "max_latitude",
    ]

    for sutun in sayisal_sutunlar:
        dataframe[sutun] = pd.to_numeric(
            dataframe[sutun],
            errors="coerce",
        )

    dataframe = dataframe.dropna(
        subset=[
            "patch_id",
            "cell_id",
            "district_name",
            "district_candidate_rank",
            "geotiff_path",
        ]
    ).copy()

    if dataframe.empty:
        raise ValueError(
            "Manifestte aktarılabilecek RGB yaması bulunamadı."
        )

    dataframe[
        "district_candidate_rank"
    ] = dataframe[
        "district_candidate_rank"
    ].astype(int)

    dataframe = dataframe.sort_values(
        by="district_candidate_rank",
        ascending=True,
    ).reset_index(
        drop=True
    )

    return dataframe


# ==========================================================
# PROJEYE GÖRELİ DOSYA YOLU
# ==========================================================

def projeye_goreli_yol(
    dosya_yolu: Any,
) -> str | None:
    """
    Mutlak dosya yolunu proje köküne göre göreli
    ve taşınabilir bir yola dönüştürür.
    """

    if dosya_yolu is None:
        return None

    yol_metni = str(
        dosya_yolu
    ).strip()

    if not yol_metni:
        return None

    yol = Path(
        yol_metni
    )

    try:
        return (
            yol.resolve()
            .relative_to(
                PROJE_KOKU.resolve()
            )
            .as_posix()
        )

    except (
        ValueError,
        OSError,
    ):
        return yol.as_posix()


# ==========================================================
# KAYNAK SAHNE KİMLİKLERİ
# ==========================================================

def kaynak_sahne_kimliklerini_bul(
    manifest_satiri: pd.Series,
    metadata: dict[str, Any],
) -> list[str]:
    """
    Bir yamanın hangi Sentinel sahnelerinden
    üretildiğini belirler.

    Mevcut tek-sahne kodunda metadata item_id kullanılır.
    Çoklu sahne desteğinde manifest sütunu varsa
    otomatik olarak onu okuyabilir.
    """

    olasi_sutunlar = [
        "source_item_ids_json",
        "source_item_ids",
    ]

    for sutun in olasi_sutunlar:
        if sutun not in manifest_satiri.index:
            continue

        deger = manifest_satiri[
            sutun
        ]

        if pd.isna(
            deger
        ):
            continue

        if isinstance(
            deger,
            list,
        ):
            return [
                str(item_id)
                for item_id in deger
                if str(item_id).strip()
            ]

        metin = str(
            deger
        ).strip()

        if not metin:
            continue

        try:
            json_degeri = json.loads(
                metin
            )

            if isinstance(
                json_degeri,
                list,
            ):
                return [
                    str(item_id)
                    for item_id in json_degeri
                    if str(item_id).strip()
                ]

        except json.JSONDecodeError:
            return [
                parca.strip()
                for parca in metin.split(",")
                if parca.strip()
            ]

    return [
        str(
            metadata[
                "item_id"
            ]
        )
    ]


# ==========================================================
# GERÇEK BBOX KAPSAMA ORANI
# ==========================================================

def kapsama_orani_hesapla(
    geotiff_yolu: Path,
    min_longitude: float,
    min_latitude: float,
    max_longitude: float,
    max_latitude: float,
) -> float | None:
    """
    GeoTIFF'in istenen 1500x1500 metre BBOX alanının
    yüzde kaçını gerçekten kapsadığını hesaplar.

    Böylece yalnızca indirilen dar şeritteki piksellerin
    geçerli olması, tam kapsam sanılmaz.
    """

    if not geotiff_yolu.exists():
        return None

    try:
        with rasterio.open(
            geotiff_yolu
        ) as kaynak:

            if kaynak.crs is None:
                return None

            raster_geometrisi = box(
                kaynak.bounds.left,
                kaynak.bounds.bottom,
                kaynak.bounds.right,
                kaynak.bounds.top,
            )

            raster_donusturucu = Transformer.from_crs(
                kaynak.crs,
                ISTANBUL_METRIK_CRS,
                always_xy=True,
            )

            raster_metrik = shapely_transform(
                raster_donusturucu.transform,
                raster_geometrisi,
            )

        istenen_geometri = box(
            min_longitude,
            min_latitude,
            max_longitude,
            max_latitude,
        )

        bbox_donusturucu = Transformer.from_crs(
            COGRAFI_CRS,
            ISTANBUL_METRIK_CRS,
            always_xy=True,
        )

        istenen_metrik = shapely_transform(
            bbox_donusturucu.transform,
            istenen_geometri,
        )

        istenen_alan = float(
            istenen_metrik.area
        )

        if istenen_alan <= 0:
            return None

        ortak_alan = float(
            raster_metrik
            .intersection(
                istenen_metrik
            )
            .area
        )

        oran = (
            ortak_alan
            / istenen_alan
            * 100
        )

        oran = max(
            0.0,
            min(
                100.0,
                oran,
            ),
        )

        return round(
            oran,
            2,
        )

    except (
        rasterio.errors.RasterioError,
        ValueError,
        OSError,
    ):
        return None


# ==========================================================
# KAPSAMA DURUMU
# ==========================================================

def kapsama_durumu_belirle(
    kapsama_orani: float | None,
) -> tuple[str, int]:
    """
    Kapsama oranını durum ve analiz hazırlığı
    değerine dönüştürür.
    """

    if kapsama_orani is None:
        return (
            "hesaplanamadi",
            0,
        )

    if kapsama_orani >= HAZIR_KAPSAMA_ESIGI:
        return (
            "tam",
            1,
        )

    if kapsama_orani >= 80:
        return (
            "buyuk_olcude_tam",
            0,
        )

    return (
        "kismi",
        0,
    )


# ==========================================================
# VERİTABANI BAĞLANTISI
# ==========================================================

def veritabanina_baglan(
    veritabani_yolu: Path,
) -> sqlite3.Connection:
    """
    UrbanAI SQLite veritabanına bağlanır.
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
# UYDU TABLOLARI
# ==========================================================

def uydu_tablolarini_olustur(
    baglanti: sqlite3.Connection,
) -> None:
    """
    Uydu sahnesi ve uydu yamaları tablolarını
    bulunmuyorsa oluşturur.
    """

    baglanti.execute(
        """
        CREATE TABLE IF NOT EXISTS satellite_scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            district_name TEXT NOT NULL,
            district_slug TEXT NOT NULL,

            item_id TEXT NOT NULL,
            acquisition_datetime_utc TEXT NOT NULL,

            cloud_cover_pct REAL,
            platform TEXT,
            collection_name TEXT,
            selection_method TEXT,

            metadata_json TEXT NOT NULL,

            is_current INTEGER NOT NULL DEFAULT 1,

            updated_at_utc TEXT NOT NULL,

            UNIQUE (
                district_slug,
                item_id
            )
        );
        """
    )

    baglanti.execute(
        """
        CREATE TABLE IF NOT EXISTS satellite_patches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            district_name TEXT NOT NULL,
            district_slug TEXT NOT NULL,

            patch_id TEXT NOT NULL,
            cell_id TEXT NOT NULL,

            district_candidate_rank INTEGER,
            nearest_library_distance_km REAL,

            width_pixels INTEGER,
            height_pixels INTEGER,
            band_count INTEGER,
            raster_dtype TEXT,
            raster_crs TEXT,

            valid_pixel_pct REAL,
            requested_area_coverage_pct REAL,
            coverage_status TEXT NOT NULL,
            analysis_ready INTEGER NOT NULL DEFAULT 0,

            min_longitude REAL,
            min_latitude REAL,
            max_longitude REAL,
            max_latitude REAL,

            geotiff_path TEXT,
            png_path TEXT,
            png_relative_path TEXT,

            source_item_ids_json TEXT NOT NULL,

            updated_at_utc TEXT NOT NULL,

            UNIQUE (
                district_slug,
                patch_id
            )
        );
        """
    )

    baglanti.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_satellite_scenes_district
        ON satellite_scenes (
            district_slug
        );
        """
    )

    baglanti.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_satellite_patches_district
        ON satellite_patches (
            district_slug
        );
        """
    )

    baglanti.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_satellite_patches_cell
        ON satellite_patches (
            cell_id
        );
        """
    )

    baglanti.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_satellite_patches_ready
        ON satellite_patches (
            analysis_ready
        );
        """
    )

    baglanti.commit()


# ==========================================================
# SAHNE KAYDINI EKLEME / GÜNCELLEME
# ==========================================================

def sahneyi_veritabanina_yaz(
    baglanti: sqlite3.Connection,
    ilce_adi: str,
    ilce_slug: str,
    metadata: dict[str, Any],
    zaman_bilgisi: str,
) -> None:
    """
    Seçilmiş Sentinel-2 sahnesini veritabanına
    ekler veya günceller.
    """

    baglanti.execute(
        """
        UPDATE satellite_scenes
        SET is_current = 0
        WHERE district_slug = ?;
        """,
        (
            ilce_slug,
        ),
    )

    baglanti.execute(
        """
        INSERT INTO satellite_scenes (
            district_name,
            district_slug,
            item_id,
            acquisition_datetime_utc,
            cloud_cover_pct,
            platform,
            collection_name,
            selection_method,
            metadata_json,
            is_current,
            updated_at_utc
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?
        )
        ON CONFLICT (
            district_slug,
            item_id
        )
        DO UPDATE SET
            district_name =
                excluded.district_name,

            acquisition_datetime_utc =
                excluded.acquisition_datetime_utc,

            cloud_cover_pct =
                excluded.cloud_cover_pct,

            platform =
                excluded.platform,

            collection_name =
                excluded.collection_name,

            selection_method =
                excluded.selection_method,

            metadata_json =
                excluded.metadata_json,

            is_current = 1,

            updated_at_utc =
                excluded.updated_at_utc;
        """,
        (
            ilce_adi,
            ilce_slug,
            str(
                metadata[
                    "item_id"
                ]
            ),
            str(
                metadata[
                    "datetime"
                ]
            ),
            float(
                metadata[
                    "cloud_cover_pct"
                ]
            ),
            str(
                metadata.get(
                    "platform"
                )
                or ""
            ),
            str(
                metadata[
                    "collection"
                ]
            ),
            str(
                metadata.get(
                    "selection_method"
                )
                or ""
            ),
            json.dumps(
                metadata,
                ensure_ascii=False,
            ),
            zaman_bilgisi,
        ),
    )


# ==========================================================
# YAMA KAYDINI EKLEME / GÜNCELLEME
# ==========================================================

def yamayi_veritabanina_yaz(
    baglanti: sqlite3.Connection,
    ilce_adi: str,
    ilce_slug: str,
    manifest_satiri: pd.Series,
    metadata: dict[str, Any],
    zaman_bilgisi: str,
) -> dict[str, Any]:
    """
    Tek bir RGB uydu yamasını veritabanına
    ekler veya günceller.
    """

    geotiff_yolu = Path(
        str(
            manifest_satiri[
                "geotiff_path"
            ]
        )
    )

    kapsama_orani = kapsama_orani_hesapla(
        geotiff_yolu=geotiff_yolu,
        min_longitude=float(
            manifest_satiri[
                "min_longitude"
            ]
        ),
        min_latitude=float(
            manifest_satiri[
                "min_latitude"
            ]
        ),
        max_longitude=float(
            manifest_satiri[
                "max_longitude"
            ]
        ),
        max_latitude=float(
            manifest_satiri[
                "max_latitude"
            ]
        ),
    )

    (
        kapsama_durumu,
        analiz_hazir,
    ) = kapsama_durumu_belirle(
        kapsama_orani
    )

    kaynak_sahneler = kaynak_sahne_kimliklerini_bul(
        manifest_satiri,
        metadata,
    )

    baglanti.execute(
        """
        INSERT INTO satellite_patches (
            district_name,
            district_slug,
            patch_id,
            cell_id,
            district_candidate_rank,
            nearest_library_distance_km,
            width_pixels,
            height_pixels,
            band_count,
            raster_dtype,
            raster_crs,
            valid_pixel_pct,
            requested_area_coverage_pct,
            coverage_status,
            analysis_ready,
            min_longitude,
            min_latitude,
            max_longitude,
            max_latitude,
            geotiff_path,
            png_path,
            png_relative_path,
            source_item_ids_json,
            updated_at_utc
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        ON CONFLICT (
            district_slug,
            patch_id
        )
        DO UPDATE SET
            district_name =
                excluded.district_name,

            cell_id =
                excluded.cell_id,

            district_candidate_rank =
                excluded.district_candidate_rank,

            nearest_library_distance_km =
                excluded.nearest_library_distance_km,

            width_pixels =
                excluded.width_pixels,

            height_pixels =
                excluded.height_pixels,

            band_count =
                excluded.band_count,

            raster_dtype =
                excluded.raster_dtype,

            raster_crs =
                excluded.raster_crs,

            valid_pixel_pct =
                excluded.valid_pixel_pct,

            requested_area_coverage_pct =
                excluded.requested_area_coverage_pct,

            coverage_status =
                excluded.coverage_status,

            analysis_ready =
                excluded.analysis_ready,

            min_longitude =
                excluded.min_longitude,

            min_latitude =
                excluded.min_latitude,

            max_longitude =
                excluded.max_longitude,

            max_latitude =
                excluded.max_latitude,

            geotiff_path =
                excluded.geotiff_path,

            png_path =
                excluded.png_path,

            png_relative_path =
                excluded.png_relative_path,

            source_item_ids_json =
                excluded.source_item_ids_json,

            updated_at_utc =
                excluded.updated_at_utc;
        """,
        (
            ilce_adi,
            ilce_slug,
            str(
                manifest_satiri[
                    "patch_id"
                ]
            ),
            str(
                manifest_satiri[
                    "cell_id"
                ]
            ),
            int(
                manifest_satiri[
                    "district_candidate_rank"
                ]
            ),
            float(
                manifest_satiri[
                    "nearest_library_distance_km"
                ]
            ),
            int(
                manifest_satiri[
                    "width_pixels"
                ]
            ),
            int(
                manifest_satiri[
                    "height_pixels"
                ]
            ),
            int(
                manifest_satiri[
                    "band_count"
                ]
            ),
            str(
                manifest_satiri[
                    "dtype"
                ]
            ),
            str(
                manifest_satiri[
                    "crs"
                ]
            ),
            float(
                manifest_satiri[
                    "valid_pixel_pct"
                ]
            ),
            kapsama_orani,
            kapsama_durumu,
            analiz_hazir,
            float(
                manifest_satiri[
                    "min_longitude"
                ]
            ),
            float(
                manifest_satiri[
                    "min_latitude"
                ]
            ),
            float(
                manifest_satiri[
                    "max_longitude"
                ]
            ),
            float(
                manifest_satiri[
                    "max_latitude"
                ]
            ),
            projeye_goreli_yol(
                manifest_satiri[
                    "geotiff_path"
                ]
            ),
            projeye_goreli_yol(
                manifest_satiri[
                    "png_path"
                ]
            ),
            str(
                manifest_satiri[
                    "png_relative_path"
                ]
            ),
            json.dumps(
                kaynak_sahneler,
                ensure_ascii=False,
            ),
            zaman_bilgisi,
        ),
    )

    return {
        "patch_id": str(
            manifest_satiri[
                "patch_id"
            ]
        ),

        "cell_id": str(
            manifest_satiri[
                "cell_id"
            ]
        ),

        "width_pixels": int(
            manifest_satiri[
                "width_pixels"
            ]
        ),

        "height_pixels": int(
            manifest_satiri[
                "height_pixels"
            ]
        ),

        "valid_pixel_pct": float(
            manifest_satiri[
                "valid_pixel_pct"
            ]
        ),

        "coverage_pct": kapsama_orani,

        "coverage_status": kapsama_durumu,

        "analysis_ready": bool(
            analiz_hazir
        ),

        "source_item_ids": kaynak_sahneler,
    }


# ==========================================================
# VERİTABANINA AKTARIM
# ==========================================================

def uydu_verilerini_aktar(
    baglanti: sqlite3.Connection,
    ilce_adi: str,
    ilce_slug: str,
    metadata: dict[str, Any],
    manifest: pd.DataFrame,
) -> list[dict[str, Any]]:
    """
    Sahne ve RGB yama bilgilerini SQLite
    veritabanına aktarır.
    """

    zaman_bilgisi = datetime.now(
        timezone.utc
    ).isoformat()

    sahneyi_veritabanina_yaz(
        baglanti=baglanti,
        ilce_adi=ilce_adi,
        ilce_slug=ilce_slug,
        metadata=metadata,
        zaman_bilgisi=zaman_bilgisi,
    )

    yama_sonuclari: list[
        dict[str, Any]
    ] = []

    for _, manifest_satiri in manifest.iterrows():

        yama_sonucu = yamayi_veritabanina_yaz(
            baglanti=baglanti,
            ilce_adi=ilce_adi,
            ilce_slug=ilce_slug,
            manifest_satiri=manifest_satiri,
            metadata=metadata,
            zaman_bilgisi=zaman_bilgisi,
        )

        yama_sonuclari.append(
            yama_sonucu
        )

    baglanti.commit()

    return yama_sonuclari


# ==========================================================
# VERİTABANI KONTROLÜ
# ==========================================================

def veritabani_kayitlarini_oku(
    baglanti: sqlite3.Connection,
    ilce_slug: str,
) -> list[sqlite3.Row]:
    """
    Aktarılan ilçenin uydu yama kayıtlarını
    veritabanından tekrar okur.
    """

    return baglanti.execute(
        """
        SELECT
            patch_id,
            cell_id,
            width_pixels,
            height_pixels,
            valid_pixel_pct,
            requested_area_coverage_pct,
            coverage_status,
            analysis_ready,
            source_item_ids_json
        FROM satellite_patches
        WHERE district_slug = ?
        ORDER BY
            district_candidate_rank ASC;
        """,
        (
            ilce_slug,
        ),
    ).fetchall()


# ==========================================================
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozetini_yazdir(
    ilce_adi: str,
    metadata: dict[str, Any],
    kayitlar: list[sqlite3.Row],
    veritabani_yolu: Path,
) -> None:
    """
    Uydu metadata aktarım sonucunu terminalde gösterir.
    """

    print()
    print("=" * 95)
    print("UYDU SAHNESİ VE RGB YAMALARI VERİTABANINA AKTARILDI")
    print("=" * 95)

    print()
    print(
        "İlçe:",
        ilce_adi,
    )

    print(
        "Sentinel-2 sahnesi:",
        metadata[
            "item_id"
        ],
    )

    print(
        "Aktarılan RGB yaması:",
        len(
            kayitlar
        ),
    )

    hazir_sayisi = sum(
        int(
            kayit[
                "analysis_ready"
            ]
        )
        for kayit in kayitlar
    )

    print(
        "Analize hazır yama:",
        hazir_sayisi,
    )

    print(
        "Eksik veya kısmi yama:",
        len(
            kayitlar
        )
        - hazir_sayisi,
    )

    print()
    print(
        "Yama kalite sonuçları:"
    )

    for kayit in kayitlar:

        kapsama = kayit[
            "requested_area_coverage_pct"
        ]

        kapsama_metni = (
            f"%{float(kapsama):.2f}"
            if kapsama is not None
            else "Hesaplanamadı"
        )

        hazir_metni = (
            "EVET"
            if kayit[
                "analysis_ready"
            ]
            else "HAYIR"
        )

        print()
        print(
            f"  {kayit['patch_id']} "
            f"— {kayit['cell_id']}"
        )

        print(
            f"    Görüntü boyutu: "
            f"{kayit['width_pixels']} x "
            f"{kayit['height_pixels']} piksel"
        )

        print(
            f"    Geçerli piksel: "
            f"%{kayit['valid_pixel_pct']:.2f}"
        )

        print(
            f"    Gerçek alan kapsaması: "
            f"{kapsama_metni}"
        )

        print(
            f"    Kapsama durumu: "
            f"{kayit['coverage_status']}"
        )

        print(
            f"    Analize hazır: "
            f"{hazir_metni}"
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
    İlçenin Sentinel-2 sahne ve RGB yama
    bilgilerini veritabanına aktarır.
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
        f"  Güvenli ilçe adı: {ilce_slug}"
    )

    print()
    print(
        "Sentinel-2 sahne metadata dosyası okunuyor..."
    )

    metadata = sahne_metadata_oku(
        yollar[
            "metadata_json"
        ],
        ilce_slug,
    )

    print(
        "RGB yama manifest dosyası okunuyor..."
    )

    manifest = rgb_manifest_oku(
        yollar[
            "manifest_csv"
        ],
        ilce_slug,
    )

    print(
        "UrbanAI SQLite veritabanına bağlanılıyor..."
    )

    with veritabanina_baglan(
        yollar[
            "veritabani"
        ]
    ) as baglanti:

        print(
            "Uydu veri tabloları kontrol ediliyor..."
        )

        uydu_tablolarini_olustur(
            baglanti
        )

        print(
            "Sahne ve RGB yamaları veritabanına aktarılıyor..."
        )

        uydu_verilerini_aktar(
            baglanti=baglanti,
            ilce_adi=ilce_adi,
            ilce_slug=ilce_slug,
            metadata=metadata,
            manifest=manifest,
        )

        print(
            "Aktarılan kayıtlar kontrol ediliyor..."
        )

        kayitlar = veritabani_kayitlarini_oku(
            baglanti,
            ilce_slug,
        )

    terminal_ozetini_yazdir(
        ilce_adi=ilce_adi,
        metadata=metadata,
        kayitlar=kayitlar,
        veritabani_yolu=yollar[
            "veritabani"
        ],
    )


if __name__ == "__main__":
    main()