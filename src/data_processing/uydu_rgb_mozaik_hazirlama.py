from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio

from PIL import Image
from rasterio.enums import ColorInterp
from rasterio.merge import merge


# ==========================================================
# PROJE KÖKÜ
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]


# ==========================================================
# KOORDİNAT SİSTEMİ
# ==========================================================

ISTANBUL_METRIK_CRS = "EPSG:32635"


# ==========================================================
# PNG GÖRSELLEŞTİRME AYARLARI
# ==========================================================

ALT_YUZDELIK = 2

UST_YUZDELIK = 98


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
    Mozaik hazırlanacak ilçeyi komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Seçilen ilçenin Sentinel-2 RGB GeoTIFF "
            "yamalarını birleştirerek coğrafi mozaik "
            "oluşturur."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help=(
            "Mozaik hazırlanacak ilçe adı. "
            "Örnek: Esenyurt"
        ),
    )

    argumanlar = parser.parse_args()

    argumanlar.ilce = argumanlar.ilce.strip()

    if not argumanlar.ilce:
        parser.error(
            "--ilce değeri boş bırakılamaz."
        )

    return argumanlar


# ==========================================================
# GÜVENLİ DOSYA VE KLASÖR ADI
# ==========================================================

def slug_olustur(
    metin: str,
) -> str:
    """
    İlçe adını güvenli klasör adına dönüştürür.

    Küçükçekmece -> kucukcekmece
    Bağcılar     -> bagcilar
    Ümraniye     -> umraniye
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
# İLÇEYE ÖZEL DOSYA YOLLARI
# ==========================================================

def dosya_yollarini_olustur(
    ilce_slug: str,
) -> dict[str, Path]:
    """
    Seçilen ilçenin bütün girdi ve çıktı
    dosya yollarını oluşturur.
    """

    islenmis_klasor = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
    )

    ham_uydu_klasoru = (
        PROJE_KOKU
        / "data"
        / "raw"
        / "satellite"
        / ilce_slug
    )

    rgb_geotiff_klasoru = (
        ham_uydu_klasoru
        / "rgb_geotiff"
    )

    mozaik_klasoru = (
        ham_uydu_klasoru
        / "mosaic"
    )

    frontend_gorsel_klasoru = (
        PROJE_KOKU
        / "frontend"
        / "assets"
        / "sentinel2"
        / ilce_slug
    )

    return {
        "islenmis_klasor": islenmis_klasor,

        "rgb_manifest_csv": (
            islenmis_klasor
            / "rgb_yama_manifest.csv"
        ),

        "uydu_yamalari_geojson": (
            islenmis_klasor
            / "pilot_uydu_yamalari.geojson"
        ),

        "secilen_sahne_json": (
            islenmis_klasor
            / "secilen_sentinel2_sahnesi.json"
        ),

        "rgb_geotiff_klasoru": (
            rgb_geotiff_klasoru
        ),

        "mozaik_klasoru": (
            mozaik_klasoru
        ),

        "mozaik_geotiff": (
            mozaik_klasoru
            / f"{ilce_slug}_pilot_rgb_mozaik.tif"
        ),

        "mozaik_png": (
            frontend_gorsel_klasoru
            / f"{ilce_slug}_pilot_rgb_mozaik.png"
        ),

        "ortusme_matrisi_csv": (
            islenmis_klasor
            / "yama_ortusme_matrisi.csv"
        ),

        "mozaik_ozeti_json": (
            islenmis_klasor
            / "rgb_mozaik_ozeti.json"
        ),

        "mozaik_html": (
            PROJE_KOKU
            / "frontend"
            / f"{ilce_slug}_pilot_rgb_mozaik.html"
        ),
    }


# ==========================================================
# JSON DOSYASI OKUMA
# ==========================================================

def json_dosyasi_oku(
    dosya_yolu: Path,
) -> dict[str, Any]:
    """
    JSON dosyasını güvenli şekilde okur.
    """

    if not dosya_yolu.exists():
        return {}

    try:
        return json.loads(
            dosya_yolu.read_text(
                encoding="utf-8"
            )
        )

    except json.JSONDecodeError:
        return {}


# ==========================================================
# RGB MANİFEST DOSYASINI OKUMA
# ==========================================================

def rgb_manifestini_oku(
    manifest_yolu: Path,
    beklenen_ilce_slug: str,
) -> pd.DataFrame:
    """
    Daha önce üretilen RGB yamalarının
    manifest tablosunu okur.
    """

    if not manifest_yolu.exists():
        raise FileNotFoundError(
            "RGB yama manifest dosyası bulunamadı:\n"
            f"{manifest_yolu}\n\n"
            "Önce sentinel2_rgb_yamalari.py dosyasını "
            "bu ilçe için çalıştır."
        )

    dataframe = pd.read_csv(
        manifest_yolu
    )

    gerekli_sutunlar = [
        "patch_id",
        "cell_id",
        "district_name",
        "district_slug",
        "district_candidate_rank",
        "geotiff_path",
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

    farkli_ilce_kayitlari = dataframe[
        dataframe[
            "district_slug"
        ]
        .astype(str)
        .str.strip()
        .ne(
            beklenen_ilce_slug
        )
    ]

    if not farkli_ilce_kayitlari.empty:
        raise ValueError(
            "RGB manifest dosyasında farklı ilçeye "
            "ait kayıtlar bulundu."
        )

    dataframe[
        "district_candidate_rank"
    ] = pd.to_numeric(
        dataframe[
            "district_candidate_rank"
        ],
        errors="coerce",
    )

    dataframe = dataframe.dropna(
        subset=[
            "patch_id",
            "district_candidate_rank",
        ]
    ).copy()

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

    if dataframe.empty:
        raise ValueError(
            "RGB manifest dosyasında geçerli yama bulunamadı."
        )

    return dataframe


# ==========================================================
# GEOTIFF DOSYALARINI BULMA
# ==========================================================

def geotiff_dosyalarini_bul(
    manifest: pd.DataFrame,
    rgb_geotiff_klasoru: Path,
) -> list[Path]:
    """
    Manifest tablosundaki patch kimliklerinden
    taşınabilir GeoTIFF dosya yolları oluşturur.

    Manifest içindeki mutlak yol farklı bir bilgisayara
    taşındığında bozulabileceği için önce proje içindeki
    standart klasör kullanılır.
    """

    dosyalar: list[Path] = []

    eksik_dosyalar: list[Path] = []

    for kayit in manifest.itertuples():

        patch_id = str(
            kayit.patch_id
        )

        standart_yol = (
            rgb_geotiff_klasoru
            / f"{patch_id}_rgb.tif"
        )

        if standart_yol.exists():
            dosyalar.append(
                standart_yol
            )
            continue

        manifest_yolu = Path(
            str(
                kayit.geotiff_path
            )
        )

        if manifest_yolu.exists():
            dosyalar.append(
                manifest_yolu
            )
            continue

        eksik_dosyalar.append(
            standart_yol
        )

    if eksik_dosyalar:
        hata_metni = "\n".join(
            str(dosya)
            for dosya in eksik_dosyalar
        )

        raise FileNotFoundError(
            "Bazı RGB GeoTIFF dosyaları bulunamadı:\n"
            f"{hata_metni}"
        )

    if not dosyalar:
        raise FileNotFoundError(
            "Birleştirilecek RGB GeoTIFF dosyası bulunamadı."
        )

    return dosyalar


# ==========================================================
# YAMA GEOMETRİLERİNİ OKUMA
# ==========================================================

def uydu_yamalarini_oku(
    geojson_yolu: Path,
    beklenen_ilce_slug: str,
) -> gpd.GeoDataFrame:
    """
    Pilot uydu yaması geometrilerini okur.
    """

    if not geojson_yolu.exists():
        raise FileNotFoundError(
            "Pilot uydu yamaları GeoJSON dosyası "
            "bulunamadı:\n"
            f"{geojson_yolu}"
        )

    yamalar = gpd.read_file(
        geojson_yolu
    )

    gerekli_sutunlar = [
        "patch_id",
        "geometry",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in yamalar.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Uydu yamaları GeoJSON dosyasında "
            "eksik sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    if "district_slug" in yamalar.columns:

        farkli_ilce = yamalar[
            yamalar[
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
                "Uydu yamaları dosyasında farklı ilçeye "
                "ait geometriler bulundu."
            )

    if yamalar.crs is None:
        yamalar = yamalar.set_crs(
            "EPSG:4326"
        )

    yamalar = yamalar.sort_values(
        by="patch_id",
        ascending=True,
    ).reset_index(
        drop=True
    )

    return yamalar


# ==========================================================
# YAMA ÖRTÜŞME MATRİSİ
# ==========================================================

def ortusme_matrisini_olustur(
    yamalar: gpd.GeoDataFrame,
) -> tuple[
    pd.DataFrame,
    dict[str, Any],
]:
    """
    Uydu yamalarının birbirleriyle olan
    coğrafi örtüşme oranını hesaplar.

    Hesap:
    kesişim alanı / küçük yamanın alanı × 100
    """

    yamalar_metrik = yamalar.to_crs(
        ISTANBUL_METRIK_CRS
    )

    patch_idleri = (
        yamalar_metrik[
            "patch_id"
        ]
        .astype(str)
        .tolist()
    )

    matris = pd.DataFrame(
        0.0,
        index=patch_idleri,
        columns=patch_idleri,
    )

    en_yuksek_ortusme = {
        "patch_1": None,
        "patch_2": None,
        "overlap_pct": 0.0,
    }

    for birinci_index, birinci_yama in (
        yamalar_metrik.iterrows()
    ):

        birinci_id = str(
            birinci_yama[
                "patch_id"
            ]
        )

        birinci_geometri = (
            birinci_yama.geometry
        )

        birinci_alan = float(
            birinci_geometri.area
        )

        for ikinci_index, ikinci_yama in (
            yamalar_metrik.iterrows()
        ):

            ikinci_id = str(
                ikinci_yama[
                    "patch_id"
                ]
            )

            ikinci_geometri = (
                ikinci_yama.geometry
            )

            ikinci_alan = float(
                ikinci_geometri.area
            )

            if birinci_index == ikinci_index:

                ortusme_orani = 100.0

            else:

                kesisim_alani = float(
                    birinci_geometri
                    .intersection(
                        ikinci_geometri
                    )
                    .area
                )

                kucuk_alan = min(
                    birinci_alan,
                    ikinci_alan,
                )

                if kucuk_alan <= 0:
                    ortusme_orani = 0.0
                else:
                    ortusme_orani = (
                        kesisim_alani
                        / kucuk_alan
                        * 100
                    )

            matris.loc[
                birinci_id,
                ikinci_id,
            ] = round(
                ortusme_orani,
                2,
            )

            if (
                birinci_index < ikinci_index
                and ortusme_orani
                > en_yuksek_ortusme[
                    "overlap_pct"
                ]
            ):
                en_yuksek_ortusme = {
                    "patch_1": birinci_id,
                    "patch_2": ikinci_id,
                    "overlap_pct": round(
                        ortusme_orani,
                        2,
                    ),
                }

    matris.index.name = "patch_id"

    return (
        matris,
        en_yuksek_ortusme,
    )


# ==========================================================
# RGB MOZAIK OLUŞTURMA
# ==========================================================

def rgb_mozaik_olustur(
    geotiff_dosyalari: list[Path],
) -> tuple[
    np.ndarray,
    Any,
    Any,
]:
    """
    RGB GeoTIFF yamalarını koordinatlarına göre
    tek bir raster görüntüde birleştirir.

    Bütün görüntüler aynı Sentinel-2 sahnesinden
    geldiği için örtüşen alanlarda ilk piksel değeri
    kullanılabilir.
    """

    acik_rasterlar = []

    try:

        referans_crs = None

        referans_bant_sayisi = None

        referans_dtype = None

        for dosya_yolu in geotiff_dosyalari:

            raster = rasterio.open(
                dosya_yolu
            )

            if raster.count != 3:
                raster.close()

                raise ValueError(
                    "RGB GeoTIFF dosyası üç bantlı değil:\n"
                    f"{dosya_yolu}"
                )

            if raster.crs is None:
                raster.close()

                raise ValueError(
                    "GeoTIFF dosyasında koordinat sistemi yok:\n"
                    f"{dosya_yolu}"
                )

            if referans_crs is None:

                referans_crs = raster.crs

                referans_bant_sayisi = (
                    raster.count
                )

                referans_dtype = (
                    raster.dtypes[0]
                )

            else:

                if raster.crs != referans_crs:
                    raster.close()

                    raise ValueError(
                        "GeoTIFF dosyalarının koordinat "
                        "sistemleri birbirinden farklı."
                    )

                if raster.count != referans_bant_sayisi:
                    raster.close()

                    raise ValueError(
                        "GeoTIFF bant sayıları birbirinden farklı."
                    )

                if raster.dtypes[0] != referans_dtype:
                    raster.close()

                    raise ValueError(
                        "GeoTIFF veri tipleri birbirinden farklı."
                    )

            acik_rasterlar.append(
                raster
            )

        mozaik, mozaik_transformu = merge(
            acik_rasterlar,
            nodata=0,
            method="first",
        )

    finally:

        for raster in acik_rasterlar:
            raster.close()

    if mozaik.size == 0:
        raise ValueError(
            "RGB mozaik oluşturulamadı."
        )

    return (
        mozaik,
        mozaik_transformu,
        referans_crs,
    )


# ==========================================================
# MOZAIK GEOTIFF KAYDETME
# ==========================================================

def mozaik_geotiff_kaydet(
    mozaik: np.ndarray,
    transform,
    crs,
    cikti_yolu: Path,
) -> None:
    """
    Birleştirilen RGB mozaik görüntüsünü
    coğrafi GeoTIFF olarak kaydeder.
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    bant_sayisi, yukseklik, genislik = (
        mozaik.shape
    )

    profil = {
        "driver": "GTiff",
        "height": yukseklik,
        "width": genislik,
        "count": bant_sayisi,
        "dtype": mozaik.dtype,
        "crs": crs,
        "transform": transform,
        "compress": "deflate",
        "predictor": 2,
        "tiled": True,
        "nodata": 0,
    }

    with rasterio.open(
        cikti_yolu,
        "w",
        **profil,
    ) as hedef:

        hedef.write(
            mozaik
        )

        hedef.colorinterp = (
            ColorInterp.red,
            ColorInterp.green,
            ColorInterp.blue,
        )


# ==========================================================
# BANTLARI 8 BİT GÖRSEL DEĞERLERE ÇEVİRME
# ==========================================================

def bandi_8_bit_yap(
    bant: np.ndarray,
    gecerli_maske: np.ndarray,
) -> np.ndarray:
    """
    Ham Sentinel-2 değerlerini PNG için
    0-255 arasına dönüştürür.
    """

    gecerli_pikseller = bant[
        gecerli_maske
    ]

    gecerli_pikseller = (
        gecerli_pikseller[
            gecerli_pikseller > 0
        ]
    )

    if gecerli_pikseller.size == 0:
        return np.zeros(
            bant.shape,
            dtype=np.uint8,
        )

    alt_deger = np.percentile(
        gecerli_pikseller,
        ALT_YUZDELIK,
    )

    ust_deger = np.percentile(
        gecerli_pikseller,
        UST_YUZDELIK,
    )

    if ust_deger <= alt_deger:
        ust_deger = alt_deger + 1

    normalize_bant = (
        (
            bant.astype(
                np.float32
            )
            - alt_deger
        )
        / (
            ust_deger
            - alt_deger
        )
        * 255
    )

    normalize_bant = np.clip(
        normalize_bant,
        0,
        255,
    )

    normalize_bant[
        ~gecerli_maske
    ] = 0

    return normalize_bant.astype(
        np.uint8
    )


# ==========================================================
# MOZAIK PNG KAYDETME
# ==========================================================

def mozaik_png_kaydet(
    mozaik: np.ndarray,
    cikti_yolu: Path,
) -> dict[str, Any]:
    """
    Mozaik GeoTIFF verisinden PNG önizlemesi üretir.

    Geçerli ve boş piksel oranlarını döndürür.
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    gecerli_maske = np.any(
        mozaik > 0,
        axis=0,
    )

    toplam_piksel = int(
        gecerli_maske.size
    )

    gecerli_piksel = int(
        gecerli_maske.sum()
    )

    bos_piksel = (
        toplam_piksel
        - gecerli_piksel
    )

    gecerli_piksel_orani = (
        gecerli_piksel
        / toplam_piksel
        * 100
        if toplam_piksel > 0
        else 0.0
    )

    bos_piksel_orani = (
        bos_piksel
        / toplam_piksel
        * 100
        if toplam_piksel > 0
        else 0.0
    )

    kirmizi = bandi_8_bit_yap(
        mozaik[0],
        gecerli_maske,
    )

    yesil = bandi_8_bit_yap(
        mozaik[1],
        gecerli_maske,
    )

    mavi = bandi_8_bit_yap(
        mozaik[2],
        gecerli_maske,
    )

    rgb_8_bit = np.stack(
        [
            kirmizi,
            yesil,
            mavi,
        ],
        axis=-1,
    )

    goruntu = Image.fromarray(
        rgb_8_bit
    )

    goruntu.save(
        cikti_yolu,
        format="PNG",
        optimize=True,
    )

    return {
        "total_pixel_count": (
            toplam_piksel
        ),

        "valid_pixel_count": (
            gecerli_piksel
        ),

        "empty_pixel_count": (
            bos_piksel
        ),

        "valid_pixel_pct": round(
            gecerli_piksel_orani,
            2,
        ),

        "empty_pixel_pct": round(
            bos_piksel_orani,
            2,
        ),
    }


# ==========================================================
# RASTER TEKNİK ÖZELLİKLERİNİ HESAPLAMA
# ==========================================================

def raster_ozelliklerini_hesapla(
    mozaik: np.ndarray,
    transform,
    piksel_istatistikleri: dict[str, Any],
) -> dict[str, Any]:
    """
    Mozaik rasterın çözünürlük ve yaklaşık
    geçerli alan büyüklüğünü hesaplar.
    """

    piksel_genisligi_m = abs(
        float(
            transform.a
        )
    )

    piksel_yuksekligi_m = abs(
        float(
            transform.e
        )
    )

    piksel_alani_m2 = (
        piksel_genisligi_m
        * piksel_yuksekligi_m
    )

    gecerli_alan_km2 = (
        piksel_istatistikleri[
            "valid_pixel_count"
        ]
        * piksel_alani_m2
        / 1_000_000
    )

    toplam_kapsama_alani_km2 = (
        piksel_istatistikleri[
            "total_pixel_count"
        ]
        * piksel_alani_m2
        / 1_000_000
    )

    return {
        "width_pixels": int(
            mozaik.shape[2]
        ),

        "height_pixels": int(
            mozaik.shape[1]
        ),

        "band_count": int(
            mozaik.shape[0]
        ),

        "dtype": str(
            mozaik.dtype
        ),

        "pixel_width_m": round(
            piksel_genisligi_m,
            4,
        ),

        "pixel_height_m": round(
            piksel_yuksekligi_m,
            4,
        ),

        "pixel_area_m2": round(
            piksel_alani_m2,
            4,
        ),

        "valid_area_km2": round(
            gecerli_alan_km2,
            4,
        ),

        "bounding_rectangle_area_km2": round(
            toplam_kapsama_alani_km2,
            4,
        ),
    }


# ==========================================================
# MOZAIK ÖZETİNİ KAYDETME
# ==========================================================

def mozaik_ozetini_kaydet(
    ilce_adi: str,
    ilce_slug: str,
    geotiff_dosyalari: list[Path],
    mozaik: np.ndarray,
    transform,
    crs,
    piksel_istatistikleri: dict[str, Any],
    en_yuksek_ortusme: dict[str, Any],
    sahne_metadata: dict[str, Any],
    yollar: dict[str, Path],
) -> dict[str, Any]:
    """
    Mozaik üretiminin teknik ve coğrafi
    özetini JSON dosyasına kaydeder.
    """

    raster_ozellikleri = (
        raster_ozelliklerini_hesapla(
            mozaik,
            transform,
            piksel_istatistikleri,
        )
    )

    ozet = {
        "project": (
            "UrbanAI 3D İstanbul"
        ),

        "district_name": ilce_adi,

        "district_slug": ilce_slug,

        "source_patch_count": len(
            geotiff_dosyalari
        ),

        "source_geotiffs": [
            str(
                dosya
            )
            for dosya in geotiff_dosyalari
        ],

        "width_pixels": (
            raster_ozellikleri[
                "width_pixels"
            ]
        ),

        "height_pixels": (
            raster_ozellikleri[
                "height_pixels"
            ]
        ),

        "band_count": (
            raster_ozellikleri[
                "band_count"
            ]
        ),

        "dtype": (
            raster_ozellikleri[
                "dtype"
            ]
        ),

        "crs": str(
            crs
        ),

        "pixel_width_m": (
            raster_ozellikleri[
                "pixel_width_m"
            ]
        ),

        "pixel_height_m": (
            raster_ozellikleri[
                "pixel_height_m"
            ]
        ),

        "pixel_area_m2": (
            raster_ozellikleri[
                "pixel_area_m2"
            ]
        ),

        "valid_area_km2": (
            raster_ozellikleri[
                "valid_area_km2"
            ]
        ),

        "bounding_rectangle_area_km2": (
            raster_ozellikleri[
                "bounding_rectangle_area_km2"
            ]
        ),

        "valid_pixel_pct": (
            piksel_istatistikleri[
                "valid_pixel_pct"
            ]
        ),

        "empty_pixel_pct": (
            piksel_istatistikleri[
                "empty_pixel_pct"
            ]
        ),

        "highest_overlap_pair": (
            en_yuksek_ortusme
        ),

        "sentinel_item_id": (
            sahne_metadata.get(
                "item_id"
            )
        ),

        "sentinel_datetime": (
            sahne_metadata.get(
                "datetime"
            )
        ),

        "cloud_cover_pct": (
            sahne_metadata.get(
                "cloud_cover_pct"
            )
        ),

        "platform": (
            sahne_metadata.get(
                "platform"
            )
        ),

        "mosaic_geotiff_path": str(
            yollar[
                "mozaik_geotiff"
            ]
        ),

        "mosaic_png_path": str(
            yollar[
                "mozaik_png"
            ]
        ),

        "overlap_matrix_path": str(
            yollar[
                "ortusme_matrisi_csv"
            ]
        ),

        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "processing_note": (
            "Aynı Sentinel-2 sahnesinden üretilen "
            "örtüşen RGB yamaları coğrafi koordinatları "
            "korunarak birleştirildi. Örtüşen alanlarda "
            "ilk raster değeri kullanıldı."
        ),

        "machine_learning_note": (
            "Örtüşen yamalar bağımsız eğitim ve doğrulama "
            "örnekleri olarak ayrılmamalıdır. Veri bölme "
            "işlemi coğrafi gruplar üzerinden yapılmalıdır."
        ),

        "usage_note": (
            "PNG yalnızca görsel inceleme içindir. "
            "Segmentasyon aşamasında GeoTIFF kullanılmalıdır."
        ),
    }

    yollar[
        "mozaik_ozeti_json"
    ].parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    yollar[
        "mozaik_ozeti_json"
    ].write_text(
        json.dumps(
            ozet,
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8",
    )

    return ozet


# ==========================================================
# HTML SAYFASI OLUŞTURMA
# ==========================================================

def html_sayfasi_olustur(
    ilce_adi: str,
    ilce_slug: str,
    ozet: dict[str, Any],
    ortusme_matrisi: pd.DataFrame,
    html_yolu: Path,
) -> None:
    """
    Mozaik görüntüsünü, teknik ölçümleri ve
    örtüşme matrisini HTML sayfasında gösterir.
    """

    html_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tablo_html = (
        ortusme_matrisi
        .round(2)
        .to_html(
            classes="overlap-table",
            border=0,
        )
    )

    en_yuksek_ortusme = (
        ozet[
            "highest_overlap_pair"
        ]
    )

    item_id = html.escape(
        str(
            ozet.get(
                "sentinel_item_id"
            )
            or "Bilinmiyor"
        )
    )

    tarih = html.escape(
        str(
            ozet.get(
                "sentinel_datetime"
            )
            or "Bilinmiyor"
        )
    )

    platform = html.escape(
        str(
            ozet.get(
                "platform"
            )
            or "Bilinmiyor"
        )
    )

    mozaik_relative_path = (
        f"assets/sentinel2/"
        f"{ilce_slug}/"
        f"{ilce_slug}_pilot_rgb_mozaik.png"
    )

    sayfa = f"""
<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">

    <meta
        name="viewport"
        content="width=device-width, initial-scale=1.0"
    >

    <title>
        {html.escape(ilce_adi)} Sentinel-2 RGB Mozaik
    </title>

    <style>
        * {{
            box-sizing: border-box;
        }}

        body {{
            margin: 0;
            background: #f3f6fb;
            color: #172033;
            font-family: Arial, sans-serif;
        }}

        header {{
            padding: 34px 24px;
            background: #ffffff;
            border-bottom: 1px solid #dbe2ea;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        h1 {{
            margin: 0 0 10px;
        }}

        .subtitle {{
            max-width: 900px;
            margin: 0;
            color: #667085;
            line-height: 1.6;
        }}

        main {{
            padding: 28px 24px 50px;
        }}

        .metrics {{
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(180px, 1fr));
            gap: 14px;
            margin-bottom: 24px;
        }}

        .metric {{
            padding: 16px;
            border: 1px solid #dce3eb;
            border-radius: 12px;
            background: #ffffff;
        }}

        .metric-label {{
            color: #667085;
            font-size: 12px;
        }}

        .metric-value {{
            margin-top: 7px;
            font-size: 21px;
            font-weight: 700;
        }}

        .panel {{
            margin-bottom: 24px;
            padding: 20px;
            border: 1px solid #dce3eb;
            border-radius: 14px;
            background: #ffffff;
        }}

        .mosaic-image {{
            display: block;
            width: 100%;
            max-height: 720px;
            object-fit: contain;
            border-radius: 10px;
            background: #101827;
        }}

        .note {{
            margin-top: 15px;
            padding: 14px;
            border-left: 4px solid #2563eb;
            background: #eff6ff;
            line-height: 1.6;
        }}

        .warning {{
            border-left-color: #d97706;
            background: #fffbeb;
        }}

        .table-wrapper {{
            overflow-x: auto;
        }}

        .overlap-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .overlap-table th,
        .overlap-table td {{
            padding: 10px;
            border: 1px solid #dce3eb;
            text-align: center;
        }}

        .overlap-table th {{
            background: #f8fafc;
        }}

        code {{
            word-break: break-all;
        }}
    </style>
</head>

<body>
    <header>
        <div class="container">
            <h1>
                {html.escape(ilce_adi)}
                Sentinel-2 RGB Mozaik
            </h1>

            <p class="subtitle">
                Hizmet boşluğu analizinden seçilen
                {ozet["source_patch_count"]} uydu yaması,
                coğrafi koordinatları korunarak tek bir
                raster görüntüde birleştirilmiştir.
            </p>
        </div>
    </header>

    <main class="container">

        <section class="metrics">
            <div class="metric">
                <div class="metric-label">
                    Kaynak yama
                </div>

                <div class="metric-value">
                    {ozet["source_patch_count"]}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Mozaik boyutu
                </div>

                <div class="metric-value">
                    {ozet["width_pixels"]}
                    ×
                    {ozet["height_pixels"]}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Geçerli piksel
                </div>

                <div class="metric-value">
                    %{ozet["valid_pixel_pct"]:.2f}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Geçerli alan
                </div>

                <div class="metric-value">
                    {ozet["valid_area_km2"]:.2f} km²
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    En yüksek örtüşme
                </div>

                <div class="metric-value">
                    %{en_yuksek_ortusme["overlap_pct"]:.2f}
                </div>
            </div>
        </section>

        <section class="panel">
            <h2>
                Birleştirilmiş RGB görüntüsü
            </h2>

            <img
                class="mosaic-image"
                src="{mozaik_relative_path}"
                alt="{html.escape(ilce_adi)} pilot alanlarının birleştirilmiş Sentinel-2 RGB görüntüsü"
            >

            <div class="note">
                PNG yalnızca görsel inceleme için
                hazırlanmıştır. Semantik segmentasyon
                aşamasında ham piksel değerlerini ve
                koordinat bilgisini koruyan GeoTIFF
                kullanılacaktır.
            </div>

            <div class="note warning">
                Örtüşen uydu yamaları birbirinden bağımsız
                eğitim ve doğrulama verisi değildir.
                Makine öğrenmesi veri ayrımı coğrafi
                gruplar üzerinden yapılmalıdır.
            </div>
        </section>

        <section class="panel">
            <h2>
                Yama örtüşme matrisi
            </h2>

            <p>
                Her değer, iki uydu yamasının daha küçük
                olan yamanın alanına göre yüzde kaç
                örtüştüğünü gösterir.
            </p>

            <div class="table-wrapper">
                {tablo_html}
            </div>
        </section>

        <section class="panel">
            <h2>
                Uydu sahnesi
            </h2>

            <p>
                <strong>Sahne kimliği:</strong>
                <code>{item_id}</code>
            </p>

            <p>
                <strong>Tarih:</strong>
                {tarih}
            </p>

            <p>
                <strong>Platform:</strong>
                {platform}
            </p>

            <p>
                <strong>Koordinat sistemi:</strong>
                {html.escape(str(ozet["crs"]))}
            </p>

            <p>
                <strong>Piksel çözünürlüğü:</strong>
                {ozet["pixel_width_m"]:.2f}
                ×
                {ozet["pixel_height_m"]:.2f} metre
            </p>
        </section>

    </main>
</body>
</html>
    """

    html_yolu.write_text(
        sayfa,
        encoding="utf-8",
    )


# ==========================================================
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozetini_yazdir(
    ilce_adi: str,
    ilce_slug: str,
    ozet: dict[str, Any],
    yollar: dict[str, Path],
) -> None:
    """
    Mozaik sonuçlarını terminalde gösterir.
    """

    en_yuksek = (
        ozet[
            "highest_overlap_pair"
        ]
    )

    print()
    print("=" * 95)
    print("SENTINEL-2 RGB MOZAIK HAZIRLANDI")
    print("=" * 95)

    print()
    print(
        "İlçe:",
        ilce_adi,
    )

    print(
        "Güvenli ilçe adı:",
        ilce_slug,
    )

    print(
        "Birleştirilen RGB yama sayısı:",
        ozet[
            "source_patch_count"
        ],
    )

    print(
        "Mozaik görüntü boyutu:",
        f"{ozet['width_pixels']} x "
        f"{ozet['height_pixels']} piksel",
    )

    print(
        "Piksel çözünürlüğü:",
        f"{ozet['pixel_width_m']:.2f} x "
        f"{ozet['pixel_height_m']:.2f} metre",
    )

    print(
        "Geçerli piksel oranı:",
        f"%{ozet['valid_pixel_pct']:.2f}",
    )

    print(
        "Mozaikteki geçerli yaklaşık alan:",
        f"{ozet['valid_area_km2']:.4f} km²",
    )

    print()
    print(
        "En yüksek örtüşen yama çifti:"
    )

    print(
        f"  {en_yuksek['patch_1']} "
        f"ve "
        f"{en_yuksek['patch_2']}"
    )

    print(
        f"  Örtüşme oranı: "
        f"%{en_yuksek['overlap_pct']:.2f}"
    )

    print()
    print(
        "Mozaik GeoTIFF:"
    )

    print(
        f"  {yollar['mozaik_geotiff']}"
    )

    print()
    print(
        "Mozaik PNG:"
    )

    print(
        f"  {yollar['mozaik_png']}"
    )

    print()
    print(
        "Örtüşme matrisi:"
    )

    print(
        f"  {yollar['ortusme_matrisi_csv']}"
    )

    print()
    print(
        "Mozaik özet dosyası:"
    )

    print(
        f"  {yollar['mozaik_ozeti_json']}"
    )

    print()
    print(
        "Mozaik inceleme sayfası:"
    )

    print(
        f"  {yollar['mozaik_html']}"
    )

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    Seçilen herhangi bir ilçe için RGB yamalarını
    birleştirir, örtüşmeyi hesaplar ve mozaik üretir.
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
        "Analiz ayarları:"
    )

    print(
        f"  İlçe: {ilce_adi}"
    )

    print(
        f"  Güvenli ilçe adı: {ilce_slug}"
    )

    print()
    print(
        "RGB yama manifest dosyası okunuyor..."
    )

    manifest = rgb_manifestini_oku(
        yollar[
            "rgb_manifest_csv"
        ],
        ilce_slug,
    )

    print(
        "RGB GeoTIFF dosyaları kontrol ediliyor..."
    )

    geotiff_dosyalari = (
        geotiff_dosyalarini_bul(
            manifest,
            yollar[
                "rgb_geotiff_klasoru"
            ],
        )
    )

    print(
        "Pilot uydu yaması geometrileri okunuyor..."
    )

    uydu_yamalari = uydu_yamalarini_oku(
        yollar[
            "uydu_yamalari_geojson"
        ],
        ilce_slug,
    )

    print(
        "Uydu yaması örtüşme matrisi hesaplanıyor..."
    )

    (
        ortusme_matrisi,
        en_yuksek_ortusme,
    ) = ortusme_matrisini_olustur(
        uydu_yamalari
    )

    yollar[
        "ortusme_matrisi_csv"
    ].parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    ortusme_matrisi.to_csv(
        yollar[
            "ortusme_matrisi_csv"
        ],
        encoding="utf-8-sig",
    )

    print(
        "RGB GeoTIFF yamaları birleştiriliyor..."
    )

    (
        mozaik,
        mozaik_transformu,
        mozaik_crs,
    ) = rgb_mozaik_olustur(
        geotiff_dosyalari
    )

    print(
        "Mozaik GeoTIFF kaydediliyor..."
    )

    mozaik_geotiff_kaydet(
        mozaik,
        mozaik_transformu,
        mozaik_crs,
        yollar[
            "mozaik_geotiff"
        ],
    )

    print(
        "Mozaik PNG önizlemesi oluşturuluyor..."
    )

    piksel_istatistikleri = (
        mozaik_png_kaydet(
            mozaik,
            yollar[
                "mozaik_png"
            ],
        )
    )

    print(
        "Sentinel-2 sahne metadata bilgisi okunuyor..."
    )

    sahne_metadata = json_dosyasi_oku(
        yollar[
            "secilen_sahne_json"
        ]
    )

    print(
        "Mozaik özet bilgileri kaydediliyor..."
    )

    ozet = mozaik_ozetini_kaydet(
        ilce_adi,
        ilce_slug,
        geotiff_dosyalari,
        mozaik,
        mozaik_transformu,
        mozaik_crs,
        piksel_istatistikleri,
        en_yuksek_ortusme,
        sahne_metadata,
        yollar,
    )

    print(
        "Mozaik inceleme sayfası oluşturuluyor..."
    )

    html_sayfasi_olustur(
        ilce_adi,
        ilce_slug,
        ozet,
        ortusme_matrisi,
        yollar[
            "mozaik_html"
        ],
    )

    terminal_ozetini_yazdir(
        ilce_adi,
        ilce_slug,
        ozet,
        yollar,
    )


if __name__ == "__main__":
    main()