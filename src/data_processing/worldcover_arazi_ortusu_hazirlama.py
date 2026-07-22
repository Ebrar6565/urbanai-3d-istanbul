from __future__ import annotations

import argparse
import html
import json
import math
import re
import unicodedata

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio

from PIL import Image
from rasterio.enums import Resampling
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from shapely.geometry import mapping


# ==========================================================
# PROJE AYARLARI
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

STAC_API_ADRESI = (
    "https://planetarycomputer.microsoft.com/api/stac/v1"
)

WORLDCOVER_KOLEKSIYONU = "esa-worldcover"

COGRAFI_CRS = "EPSG:4326"

ISTANBUL_METRIK_CRS = "EPSG:32635"

WORLDCOVER_COZUNURLUK_METRE = 10


# ==========================================================
# WORLDCOVER SINIFLARINI SADELEŞTİRME
# ==========================================================

# ESA WorldCover özgün sınıfları:
#
# 10  = Ağaç örtüsü
# 20  = Çalılık
# 30  = Çayır
# 40  = Tarım alanı
# 50  = Yapılaşmış alan
# 60  = Çıplak / seyrek bitkili alan
# 70  = Kar ve buz
# 80  = Kalıcı su
# 90  = Otsu sulak alan
# 95  = Mangrov
# 100 = Yosun ve liken
#
# Projemiz için bunları dört ana gruba indiriyoruz.

WORLDCOVER_SADELESTIRME = {
    10: 2,
    20: 2,
    30: 2,
    40: 2,
    50: 1,
    60: 3,
    70: 3,
    80: 4,
    90: 4,
    95: 4,
    100: 2,
}


SADE_SINIFLAR = {
    0: {
        "name": "Geçersiz / veri yok",
        "color": (0, 0, 0, 0),
    },

    1: {
        "name": "Yapılaşmış alan",
        "color": (220, 50, 47, 255),
    },

    2: {
        "name": "Bitkisel ve yeşil alan",
        "color": (46, 125, 50, 255),
    },

    3: {
        "name": "Açık veya çıplak alan",
        "color": (205, 160, 90, 255),
    },

    4: {
        "name": "Su ve sulak alan",
        "color": (40, 105, 190, 255),
    },
}


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
    Analiz edilecek ilçeyi ve WorldCover yılını
    komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Seçilen ilçenin aday hizmet hücrelerinde "
            "ESA WorldCover arazi örtüsü oranlarını hesaplar."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help=(
            "Analiz edilecek ilçe adı. "
            "Örnek: Esenyurt"
        ),
    )

    parser.add_argument(
        "--yil",
        type=int,
        choices=[
            2020,
            2021,
        ],
        default=2021,
        help=(
            "Kullanılacak ESA WorldCover yılı. "
            "Varsayılan: 2021"
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
# GÜVENLİ KLASÖR ADI
# ==========================================================

def slug_olustur(
    metin: str,
) -> str:
    """
    İlçe adını güvenli dosya ve klasör adına dönüştürür.

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
# DOSYA YOLLARI
# ==========================================================

def dosya_yollarini_olustur(
    ilce_slug: str,
    worldcover_yili: int,
) -> dict[str, Path]:
    """
    İlçeye ve WorldCover yılına özel
    girdi ve çıktı yollarını oluşturur.
    """

    uydu_islenmis_klasoru = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
    )

    worldcover_klasoru = (
        uydu_islenmis_klasoru
        / f"worldcover_{worldcover_yili}"
    )

    frontend_gorsel_klasoru = (
        PROJE_KOKU
        / "frontend"
        / "assets"
        / "sentinel2"
        / ilce_slug
        / f"worldcover_{worldcover_yili}"
    )

    return {
        "pilot_aday_geojson": (
            uydu_islenmis_klasoru
            / "pilot_aday_hucreleri.geojson"
        ),

        "worldcover_klasoru": (
            worldcover_klasoru
        ),

        "maske_geotiff_klasoru": (
            worldcover_klasoru
            / "geotiff"
        ),

        "maske_png_klasoru": (
            frontend_gorsel_klasoru
        ),

        "aday_ozeti_csv": (
            worldcover_klasoru
            / "worldcover_aday_hucre_ozeti.csv"
        ),

        "analiz_ozeti_json": (
            worldcover_klasoru
            / "worldcover_analiz_ozeti.json"
        ),

        "galeri_html": (
            PROJE_KOKU
            / "frontend"
            / (
                f"{ilce_slug}_worldcover_"
                f"{worldcover_yili}_aday_alanlari.html"
            )
        ),
    }


# ==========================================================
# ADAY HÜCRELERİ OKUMA
# ==========================================================

def aday_hucreleri_oku(
    geojson_yolu: Path,
    ilce_slug: str,
) -> gpd.GeoDataFrame:
    """
    İlçeye ait gerçek aday hizmet hücrelerini okur.
    """

    if not geojson_yolu.exists():
        raise FileNotFoundError(
            "Pilot aday hücreleri dosyası bulunamadı:\n"
            f"{geojson_yolu}\n\n"
            "Önce pilot_uydu_alanlari_hazirlama.py "
            "dosyasını bu ilçe için çalıştır."
        )

    adaylar = gpd.read_file(
        geojson_yolu
    )

    gerekli_sutunlar = [
        "cell_id",
        "district_name",
        "district_candidate_rank",
        "nearest_library_distance_km",
        "geometry",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in adaylar.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Aday hücre dosyasında eksik sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    if adaylar.crs is None:
        raise ValueError(
            "Aday hücre dosyasında koordinat sistemi yok."
        )

    adaylar[
        "cell_id"
    ] = (
        adaylar[
            "cell_id"
        ]
        .astype(str)
    )

    adaylar[
        "district_candidate_rank"
    ] = pd.to_numeric(
        adaylar[
            "district_candidate_rank"
        ],
        errors="coerce",
    )

    adaylar = adaylar.dropna(
        subset=[
            "cell_id",
            "district_candidate_rank",
            "geometry",
        ]
    ).copy()

    adaylar[
        "district_candidate_rank"
    ] = (
        adaylar[
            "district_candidate_rank"
        ]
        .astype(int)
    )

    adaylar[
        "_district_slug"
    ] = (
        adaylar[
            "district_name"
        ]
        .astype(str)
        .map(
            slug_olustur
        )
    )

    farkli_ilce = adaylar[
        adaylar[
            "_district_slug"
        ]
        != ilce_slug
    ]

    if not farkli_ilce.empty:
        raise ValueError(
            "Aday hücre dosyasında farklı ilçeye ait "
            "kayıtlar bulundu."
        )

    adaylar = adaylar.drop(
        columns=[
            "_district_slug",
        ],
        errors="ignore",
    )

    adaylar = adaylar.sort_values(
        by="district_candidate_rank",
        ascending=True,
    ).reset_index(
        drop=True
    )

    if adaylar.empty:
        raise ValueError(
            "Analiz edilecek aday hücre bulunamadı."
        )

    return gpd.GeoDataFrame(
        adaylar,
        geometry="geometry",
        crs=adaylar.crs,
    )


# ==========================================================
# WORLDCOVER SORGUSU İÇİN BBOX
# ==========================================================

def birlesik_bbox_hesapla(
    adaylar: gpd.GeoDataFrame,
) -> list[float]:
    """
    Bütün aday hücreleri kapsayan WGS84
    sınır kutusunu hesaplar.
    """

    adaylar_cografi = adaylar.to_crs(
        COGRAFI_CRS
    )

    minx, miny, maxx, maxy = (
        adaylar_cografi.total_bounds
    )

    return [
        float(
            minx
        ),
        float(
            miny
        ),
        float(
            maxx
        ),
        float(
            maxy
        ),
    ]


# ==========================================================
# WORLDCOVER STAC ÖĞELERİNİ BULMA
# ==========================================================

def worldcover_ogelerini_bul(
    bbox: list[float],
    worldcover_yili: int,
) -> list[Any]:
    """
    Aday hücrelerle kesişen ESA WorldCover
    STAC öğelerini bulur ve erişim adreslerini imzalar.
    """

    katalog = pystac_client.Client.open(
        STAC_API_ADRESI
    )

    tarih_araligi = (
        f"{worldcover_yili}-01-01"
        "/"
        f"{worldcover_yili}-12-31"
    )

    arama = katalog.search(
        collections=[
            WORLDCOVER_KOLEKSIYONU,
        ],
        bbox=bbox,
        datetime=tarih_araligi,
    )

    ogeler = list(
        arama.items()
    )

    if not ogeler:
        raise RuntimeError(
            f"{worldcover_yili} yılı için aday alanlarla "
            "kesişen ESA WorldCover verisi bulunamadı."
        )

    imzali_ogeler = []

    for oge in ogeler:

        if "map" not in oge.assets:
            continue

        imzali_ogeler.append(
            planetary_computer.sign(
                oge
            )
        )

    if not imzali_ogeler:
        raise RuntimeError(
            "WorldCover STAC öğelerinde 'map' "
            "raster asseti bulunamadı."
        )

    imzali_ogeler = sorted(
        imzali_ogeler,
        key=lambda oge: str(
            oge.id
        ),
    )

    return imzali_ogeler


# ==========================================================
# ADAY HÜCRE İÇİN 10 METRELİK GRID
# ==========================================================

def aday_gridini_olustur(
    geometri,
) -> tuple[
    Any,
    int,
    int,
]:
    """
    Aday hücrenin çevresinde 10 metre çözünürlüklü,
    UTM tabanlı raster grid oluşturur.
    """

    minx, miny, maxx, maxy = (
        geometri.bounds
    )

    cozunurluk = (
        WORLDCOVER_COZUNURLUK_METRE
    )

    minx = (
        math.floor(
            minx
            / cozunurluk
        )
        * cozunurluk
    )

    miny = (
        math.floor(
            miny
            / cozunurluk
        )
        * cozunurluk
    )

    maxx = (
        math.ceil(
            maxx
            / cozunurluk
        )
        * cozunurluk
    )

    maxy = (
        math.ceil(
            maxy
            / cozunurluk
        )
        * cozunurluk
    )

    genislik = int(
        round(
            (
                maxx
                - minx
            )
            / cozunurluk
        )
    )

    yukseklik = int(
        round(
            (
                maxy
                - miny
            )
            / cozunurluk
        )
    )

    if (
        genislik <= 0
        or yukseklik <= 0
    ):
        raise ValueError(
            "Aday hücre için geçerli raster grid "
            "oluşturulamadı."
        )

    transform = from_origin(
        minx,
        maxy,
        cozunurluk,
        cozunurluk,
    )

    return (
        transform,
        genislik,
        yukseklik,
    )


# ==========================================================
# WORLDCOVER VERİSİNİ HEDEF GRIDE OKUMA
# ==========================================================

def worldcover_rasterini_oku(
    worldcover_ogeleri: list[Any],
    hedef_transform,
    hedef_genislik: int,
    hedef_yukseklik: int,
) -> np.ndarray:
    """
    WorldCover rasterlarını aday hücrenin
    10 metrelik UTM gridine dönüştürür.

    Birden fazla WorldCover parçası varsa
    boş pikseller birleştirilir.
    """

    birlesik_raster = np.zeros(
        (
            hedef_yukseklik,
            hedef_genislik,
        ),
        dtype=np.uint8,
    )

    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_MULTIRANGE="YES",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
    ):

        for oge in worldcover_ogeleri:

            map_asset = oge.assets[
                "map"
            ]

            with rasterio.open(
                map_asset.href
            ) as kaynak:

                if kaynak.crs is None:
                    raise ValueError(
                        "WorldCover rasterında koordinat "
                        "sistemi bulunamadı."
                    )

                with WarpedVRT(
                    kaynak,
                    crs=ISTANBUL_METRIK_CRS,
                    transform=hedef_transform,
                    width=hedef_genislik,
                    height=hedef_yukseklik,
                    resampling=Resampling.nearest,
                    nodata=0,
                ) as donusturulmus:

                    parca = donusturulmus.read(
                        1
                    )

            doldurulacak_pikseller = (
                (
                    birlesik_raster
                    == 0
                )
                & (
                    parca
                    != 0
                )
            )

            birlesik_raster[
                doldurulacak_pikseller
            ] = parca[
                doldurulacak_pikseller
            ]

    return birlesik_raster


# ==========================================================
# ADAY HÜCRE GEOMETRİ MASKESİ
# ==========================================================

def aday_geometri_maskesi_olustur(
    geometri,
    transform,
    genislik: int,
    yukseklik: int,
) -> np.ndarray:
    """
    Yalnızca gerçek aday hücrenin içinde kalan
    raster piksellerini işaretler.

    True  = aday hücrenin içinde
    False = aday hücrenin dışında
    """

    return geometry_mask(
        geometries=[
            mapping(
                geometri
            )
        ],
        out_shape=(
            yukseklik,
            genislik,
        ),
        transform=transform,
        invert=True,
        all_touched=False,
    )


# ==========================================================
# WORLDCOVER SINIFLARINI SADELEŞTİRME
# ==========================================================

def siniflari_sadelestir(
    worldcover_rasteri: np.ndarray,
    aday_maskesi: np.ndarray,
) -> np.ndarray:
    """
    WorldCover'ın 11 sınıfını projemizde
    kullanacağımız dört sınıfa dönüştürür.
    """

    sade_raster = np.zeros(
        worldcover_rasteri.shape,
        dtype=np.uint8,
    )

    for kaynak_sinif, hedef_sinif in (
        WORLDCOVER_SADELESTIRME.items()
    ):

        sade_raster[
            worldcover_rasteri
            == kaynak_sinif
        ] = hedef_sinif

    sade_raster[
        ~aday_maskesi
    ] = 0

    return sade_raster


# ==========================================================
# GEOTIFF KAYDETME
# ==========================================================

def sade_maske_geotiff_kaydet(
    cikti_yolu: Path,
    sade_raster: np.ndarray,
    transform,
) -> None:
    """
    Sadeleştirilmiş arazi sınıf maskesini
    coğrafi GeoTIFF olarak kaydeder.
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    profil = {
        "driver": "GTiff",
        "height": sade_raster.shape[0],
        "width": sade_raster.shape[1],
        "count": 1,
        "dtype": "uint8",
        "crs": ISTANBUL_METRIK_CRS,
        "transform": transform,
        "nodata": 0,
        "compress": "deflate",
    }

    with rasterio.open(
        cikti_yolu,
        "w",
        **profil,
    ) as hedef:

        hedef.write(
            sade_raster,
            1,
        )

        hedef.set_band_description(
            1,
            "simplified_worldcover_class",
        )

        hedef.update_tags(
            class_0="Geçersiz veya veri yok",
            class_1="Yapılaşmış alan",
            class_2="Bitkisel ve yeşil alan",
            class_3="Açık veya çıplak alan",
            class_4="Su ve sulak alan",
        )


# ==========================================================
# RENKLİ PNG KAYDETME
# ==========================================================

def sade_maske_png_kaydet(
    cikti_yolu: Path,
    sade_raster: np.ndarray,
) -> None:
    """
    Sade sınıf maskesini renkli ve şeffaf
    PNG önizlemesi olarak kaydeder.
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    yukseklik, genislik = (
        sade_raster.shape
    )

    rgba = np.zeros(
        (
            yukseklik,
            genislik,
            4,
        ),
        dtype=np.uint8,
    )

    for sinif_kodu, sinif_bilgisi in (
        SADE_SINIFLAR.items()
    ):

        rgba[
            sade_raster
            == sinif_kodu
        ] = sinif_bilgisi[
            "color"
        ]

    Image.fromarray(
        rgba,
        mode="RGBA",
    ).save(
        cikti_yolu,
        format="PNG",
        optimize=True,
    )


# ==========================================================
# SINIF ORANLARINI HESAPLAMA
# ==========================================================

def sinif_oranlarini_hesapla(
    worldcover_rasteri: np.ndarray,
    sade_raster: np.ndarray,
    aday_maskesi: np.ndarray,
) -> dict[str, Any]:
    """
    Aday hücre içindeki arazi sınıflarının
    piksel sayılarını, alanlarını ve oranlarını hesaplar.

    Yüzdeler yalnızca sınıflandırılabilen
    WorldCover pikselleri üzerinden hesaplanır.
    """

    aday_piksel_sayisi = int(
        aday_maskesi.sum()
    )

    siniflandirilmis_maskesi = (
        sade_raster
        > 0
    )

    siniflandirilmis_piksel = int(
        siniflandirilmis_maskesi.sum()
    )

    worldcover_verili_piksel = int(
        (
            aday_maskesi
            & (
                worldcover_rasteri
                > 0
            )
        ).sum()
    )

    bilinmeyen_sinif_piksel = (
        worldcover_verili_piksel
        - siniflandirilmis_piksel
    )

    kapsama_orani = (
        (
            siniflandirilmis_piksel
            / aday_piksel_sayisi
            * 100
        )
        if aday_piksel_sayisi > 0
        else 0.0
    )

    sonuc: dict[str, Any] = {
        "candidate_pixel_count": (
            aday_piksel_sayisi
        ),

        "classified_pixel_count": (
            siniflandirilmis_piksel
        ),

        "unknown_source_class_pixel_count": (
            bilinmeyen_sinif_piksel
        ),

        "worldcover_coverage_pct": round(
            kapsama_orani,
            2,
        ),
    }

    sinif_sutunlari = {
        1: "built_up",
        2: "vegetation",
        3: "open_bare",
        4: "water_wetland",
    }

    piksel_alani_m2 = (
        WORLDCOVER_COZUNURLUK_METRE
        * WORLDCOVER_COZUNURLUK_METRE
    )

    for sinif_kodu, sutun_adi in (
        sinif_sutunlari.items()
    ):

        sinif_piksel_sayisi = int(
            (
                sade_raster
                == sinif_kodu
            ).sum()
        )

        sinif_orani = (
            (
                sinif_piksel_sayisi
                / siniflandirilmis_piksel
                * 100
            )
            if siniflandirilmis_piksel > 0
            else 0.0
        )

        sinif_alani_km2 = (
            sinif_piksel_sayisi
            * piksel_alani_m2
            / 1_000_000
        )

        sonuc[
            f"{sutun_adi}_pixel_count"
        ] = sinif_piksel_sayisi

        sonuc[
            f"{sutun_adi}_pct"
        ] = round(
            sinif_orani,
            2,
        )

        sonuc[
            f"{sutun_adi}_area_km2"
        ] = round(
            sinif_alani_km2,
            4,
        )

    return sonuc


# ==========================================================
# BASKIN SINIFI BULMA
# ==========================================================

def baskin_sinifi_bul(
    oranlar: dict[str, Any],
) -> str:
    """
    Aday hücrede yüzde olarak en fazla bulunan
    arazi sınıfını belirler.
    """

    sinif_oranlari = {
        "Yapılaşmış alan": (
            oranlar[
                "built_up_pct"
            ]
        ),

        "Bitkisel ve yeşil alan": (
            oranlar[
                "vegetation_pct"
            ]
        ),

        "Açık veya çıplak alan": (
            oranlar[
                "open_bare_pct"
            ]
        ),

        "Su ve sulak alan": (
            oranlar[
                "water_wetland_pct"
            ]
        ),
    }

    return max(
        sinif_oranlari,
        key=sinif_oranlari.get,
    )


# ==========================================================
# BÜTÜN ADAY HÜCRELERİ ANALİZ ETME
# ==========================================================

def adaylari_analiz_et(
    adaylar: gpd.GeoDataFrame,
    worldcover_ogeleri: list[Any],
    ilce_slug: str,
    worldcover_yili: int,
    yollar: dict[str, Path],
) -> pd.DataFrame:
    """
    Bütün aday hücrelerin WorldCover
    arazi örtüsü analizini gerçekleştirir.
    """

    adaylar_metrik = adaylar.to_crs(
        ISTANBUL_METRIK_CRS
    )

    sonuc_kayitlari: list[
        dict[str, Any]
    ] = []

    for aday in adaylar_metrik.itertuples():

        cell_id = str(
            aday.cell_id
        )

        print(
            f"  {cell_id} analiz ediliyor..."
        )

        geometri = (
            aday.geometry
        )

        (
            hedef_transform,
            hedef_genislik,
            hedef_yukseklik,
        ) = aday_gridini_olustur(
            geometri
        )

        worldcover_rasteri = (
            worldcover_rasterini_oku(
                worldcover_ogeleri,
                hedef_transform,
                hedef_genislik,
                hedef_yukseklik,
            )
        )

        aday_maskesi = (
            aday_geometri_maskesi_olustur(
                geometri,
                hedef_transform,
                hedef_genislik,
                hedef_yukseklik,
            )
        )

        sade_raster = siniflari_sadelestir(
            worldcover_rasteri,
            aday_maskesi,
        )

        oranlar = sinif_oranlarini_hesapla(
            worldcover_rasteri,
            sade_raster,
            aday_maskesi,
        )

        baskin_sinif = baskin_sinifi_bul(
            oranlar
        )

        guvenli_cell_id = re.sub(
            r"[^A-Za-z0-9_-]+",
            "_",
            cell_id,
        )

        geotiff_yolu = (
            yollar[
                "maske_geotiff_klasoru"
            ]
            / (
                f"{guvenli_cell_id}_"
                f"worldcover_{worldcover_yili}.tif"
            )
        )

        png_yolu = (
            yollar[
                "maske_png_klasoru"
            ]
            / (
                f"{guvenli_cell_id}_"
                f"worldcover_{worldcover_yili}.png"
            )
        )

        sade_maske_geotiff_kaydet(
            geotiff_yolu,
            sade_raster,
            hedef_transform,
        )

        sade_maske_png_kaydet(
            png_yolu,
            sade_raster,
        )

        png_relative_path = (
            f"assets/sentinel2/"
            f"{ilce_slug}/"
            f"worldcover_{worldcover_yili}/"
            f"{guvenli_cell_id}_"
            f"worldcover_{worldcover_yili}.png"
        )

        kayit = {
            "cell_id": cell_id,

            "district_name": str(
                aday.district_name
            ),

            "district_slug": (
                ilce_slug
            ),

            "district_candidate_rank": int(
                aday.district_candidate_rank
            ),

            "nearest_library_name": str(
                aday.nearest_library_name
            ),

            "nearest_library_distance_km": float(
                aday.nearest_library_distance_km
            ),

            "candidate_geometry_area_km2": round(
                float(
                    geometri.area
                )
                / 1_000_000,
                4,
            ),

            "dominant_landcover_class": (
                baskin_sinif
            ),

            "worldcover_year": (
                worldcover_yili
            ),

            "worldcover_geotiff_path": str(
                geotiff_yolu
            ),

            "worldcover_png_path": str(
                png_yolu
            ),

            "worldcover_png_relative_path": (
                png_relative_path
            ),

            **oranlar,
        }

        if hasattr(
            aday,
            "preliminary_need_score",
        ):
            kayit[
                "preliminary_need_score"
            ] = float(
                aday.preliminary_need_score
            )

        if hasattr(
            aday,
            "global_preliminary_score",
        ):
            kayit[
                "global_preliminary_score"
            ] = float(
                aday.global_preliminary_score
            )

        sonuc_kayitlari.append(
            kayit
        )

    sonuc_dataframe = pd.DataFrame(
        sonuc_kayitlari
    )

    sonuc_dataframe = (
        sonuc_dataframe
        .sort_values(
            by="district_candidate_rank",
            ascending=True,
        )
        .reset_index(
            drop=True
        )
    )

    return sonuc_dataframe


# ==========================================================
# ÇIKTILARI KAYDETME
# ==========================================================

def ciktilari_kaydet(
    sonuc_dataframe: pd.DataFrame,
    ilce_adi: str,
    ilce_slug: str,
    worldcover_yili: int,
    bbox: list[float],
    worldcover_ogeleri: list[Any],
    yollar: dict[str, Path],
) -> dict[str, Any]:
    """
    Aday özet tablosunu ve analiz metadata
    dosyasını kaydeder.
    """

    yollar[
        "worldcover_klasoru"
    ].mkdir(
        parents=True,
        exist_ok=True,
    )

    sonuc_dataframe.to_csv(
        yollar[
            "aday_ozeti_csv"
        ],
        index=False,
        encoding="utf-8-sig",
    )

    kaynak_oge_idleri = [
        str(
            oge.id
        )
        for oge in worldcover_ogeleri
    ]

    analiz_ozeti = {
        "project": (
            "UrbanAI 3D İstanbul"
        ),

        "district_name": (
            ilce_adi
        ),

        "district_slug": (
            ilce_slug
        ),

        "worldcover_year": (
            worldcover_yili
        ),

        "worldcover_collection": (
            WORLDCOVER_KOLEKSIYONU
        ),

        "worldcover_asset": (
            "map"
        ),

        "spatial_resolution_m": (
            WORLDCOVER_COZUNURLUK_METRE
        ),

        "candidate_cell_count": len(
            sonuc_dataframe
        ),

        "search_bbox": (
            bbox
        ),

        "source_item_ids": (
            kaynak_oge_idleri
        ),

        "source_license": (
            "CC-BY-4.0"
        ),

        "source_attribution": (
            "ESA WorldCover, Planetary Computer "
            "üzerinden erişildi."
        ),

        "simplified_classes": {
            "0": (
                "Geçersiz veya veri yok"
            ),

            "1": (
                "Yapılaşmış alan"
            ),

            "2": (
                "Bitkisel ve yeşil alan"
            ),

            "3": (
                "Açık veya çıplak alan"
            ),

            "4": (
                "Su ve sulak alan"
            ),
        },

        "original_to_simplified_mapping": {
            str(
                kaynak_sinif
            ): hedef_sinif
            for kaynak_sinif, hedef_sinif in (
                WORLDCOVER_SADELESTIRME.items()
            )
        },

        "percentage_note": (
            "Arazi yüzdeleri yalnızca aday hücrenin "
            "içindeki ve sade sınıflardan birine "
            "atanabilen WorldCover pikselleri üzerinden "
            "hesaplanmıştır."
        ),

        "planning_warning": (
            "WorldCover arazi örtüsü verisi parsel, imar, "
            "mülkiyet veya yapı yapılabilirlik bilgisi "
            "değildir. Sonuçlar yalnızca ön inceleme ve "
            "karar desteği amacıyla kullanılmalıdır."
        ),

        "temporal_warning": (
            f"Analiz {worldcover_yili} yılı arazi örtüsü "
            "verisine dayanmaktadır. Güncel arazi kullanımı "
            "değişmiş olabilir."
        ),

        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }

    yollar[
        "analiz_ozeti_json"
    ].write_text(
        json.dumps(
            analiz_ozeti,
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8",
    )

    return analiz_ozeti


# ==========================================================
# HTML GALERİSİ
# ==========================================================

def galeri_html_olustur(
    ilce_adi: str,
    worldcover_yili: int,
    sonuc_dataframe: pd.DataFrame,
    galeri_yolu: Path,
) -> None:
    """
    Aday hücrelerin renkli arazi maskelerini ve
    sınıf oranlarını HTML sayfasında gösterir.
    """

    galeri_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    kartlar: list[str] = []

    for kayit in sonuc_dataframe.itertuples():

        cell_id = html.escape(
            str(
                kayit.cell_id
            )
        )

        maske_yolu = html.escape(
            str(
                kayit.worldcover_png_relative_path
            )
        )

        en_yakin_kutuphane = html.escape(
            str(
                kayit.nearest_library_name
            )
        )

        baskin_sinif = html.escape(
            str(
                kayit.dominant_landcover_class
            )
        )

        kartlar.append(
            f"""
            <article class="candidate-card">
                <div class="image-panel">
                    <img
                        src="{maske_yolu}"
                        alt="{cell_id} WorldCover arazi örtüsü maskesi"
                    >
                </div>

                <div class="candidate-body">
                    <span class="rank-badge">
                        {int(kayit.district_candidate_rank)}. aday
                    </span>

                    <h2>{cell_id}</h2>

                    <p class="dominant">
                        Baskın arazi sınıfı:
                        <strong>{baskin_sinif}</strong>
                    </p>

                    <div class="land-values">
                        <div>
                            <span class="class-dot built"></span>
                            Yapılaşmış
                            <strong>
                                %{float(kayit.built_up_pct):.2f}
                            </strong>
                        </div>

                        <div>
                            <span class="class-dot vegetation"></span>
                            Bitkisel / yeşil
                            <strong>
                                %{float(kayit.vegetation_pct):.2f}
                            </strong>
                        </div>

                        <div>
                            <span class="class-dot open"></span>
                            Açık / çıplak
                            <strong>
                                %{float(kayit.open_bare_pct):.2f}
                            </strong>
                        </div>

                        <div>
                            <span class="class-dot water"></span>
                            Su / sulak alan
                            <strong>
                                %{float(kayit.water_wetland_pct):.2f}
                            </strong>
                        </div>
                    </div>

                    <dl>
                        <div>
                            <dt>En yakın kütüphane</dt>
                            <dd>{en_yakin_kutuphane}</dd>
                        </div>

                        <div>
                            <dt>Kütüphaneye uzaklık</dt>
                            <dd>
                                {float(kayit.nearest_library_distance_km):.2f}
                                km
                            </dd>
                        </div>

                        <div>
                            <dt>WorldCover kapsaması</dt>
                            <dd>
                                %{float(kayit.worldcover_coverage_pct):.2f}
                            </dd>
                        </div>

                        <div>
                            <dt>Aday hücre alanı</dt>
                            <dd>
                                {float(kayit.candidate_geometry_area_km2):.4f}
                                km²
                            </dd>
                        </div>
                    </dl>
                </div>
            </article>
            """
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
        {html.escape(ilce_adi)}
        WorldCover Aday Alanları
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
            padding: 36px 24px 28px;
            background: #ffffff;
            border-bottom: 1px solid #dbe2ea;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        h1 {{
            margin: 0 0 12px;
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

        .notice {{
            margin-bottom: 22px;
            padding: 16px 18px;
            border-left: 4px solid #2563eb;
            border-radius: 9px;
            background: #eff6ff;
            line-height: 1.6;
        }}

        .warning {{
            border-left-color: #d97706;
            background: #fffbeb;
        }}

        .legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin-bottom: 24px;
            padding: 15px;
            border: 1px solid #dce3eb;
            border-radius: 12px;
            background: #ffffff;
        }}

        .legend span {{
            display: flex;
            align-items: center;
            gap: 7px;
            font-size: 13px;
        }}

        .class-dot {{
            display: inline-block;
            width: 13px;
            height: 13px;
            flex: 0 0 13px;
            border-radius: 3px;
        }}

        .built {{
            background: rgb(220, 50, 47);
        }}

        .vegetation {{
            background: rgb(46, 125, 50);
        }}

        .open {{
            background: rgb(205, 160, 90);
        }}

        .water {{
            background: rgb(40, 105, 190);
        }}

        .grid {{
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(340px, 1fr));
            gap: 20px;
        }}

        .candidate-card {{
            overflow: hidden;
            border: 1px solid #dce3eb;
            border-radius: 14px;
            background: #ffffff;
        }}

        .image-panel {{
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 300px;
            padding: 18px;
            background:
                repeating-conic-gradient(
                    #eef2f6 0% 25%,
                    #ffffff 0% 50%
                )
                50% / 20px 20px;
        }}

        .image-panel img {{
            display: block;
            width: 100%;
            max-height: 340px;
            object-fit: contain;
            image-rendering: pixelated;
        }}

        .candidate-body {{
            padding: 18px;
        }}

        .rank-badge {{
            display: inline-block;
            margin-bottom: 9px;
            padding: 5px 9px;
            border-radius: 999px;
            background: #dbeafe;
            color: #1d4ed8;
            font-size: 12px;
            font-weight: 700;
        }}

        h2 {{
            margin: 0 0 10px;
            font-size: 20px;
        }}

        .dominant {{
            margin: 0 0 16px;
            color: #475467;
            line-height: 1.5;
        }}

        .land-values {{
            display: grid;
            gap: 9px;
            margin-bottom: 17px;
        }}

        .land-values div {{
            display: grid;
            grid-template-columns: 14px 1fr auto;
            align-items: center;
            gap: 8px;
            font-size: 13px;
        }}

        dl {{
            display: grid;
            gap: 9px;
            margin: 0;
        }}

        dl div {{
            display: flex;
            justify-content: space-between;
            gap: 14px;
            padding-top: 9px;
            border-top: 1px solid #edf1f5;
        }}

        dt {{
            color: #667085;
            font-size: 12px;
        }}

        dd {{
            margin: 0;
            max-width: 58%;
            text-align: right;
            font-size: 12px;
            font-weight: 700;
        }}
    </style>
</head>

<body>
    <header>
        <div class="container">
            <h1>
                {html.escape(ilce_adi)}
                Aday Alan Arazi Örtüsü
            </h1>

            <p class="subtitle">
                Hizmet boşluğu analizinden seçilen gerçek
                aday hücrelerin {worldcover_yili} yılı
                ESA WorldCover arazi örtüsü dağılımları.
            </p>
        </div>
    </header>

    <main class="container">

        <section class="notice">
            Bu aşamada model eğitilmemiştir.
            Hazır ESA WorldCover arazi örtüsü haritası
            aday hücrelerin koordinatlarıyla eşleştirilmiş
            ve sınıf pikselleri sayılmıştır.
        </section>

        <section class="notice warning">
            Arazi örtüsü sonucu, bölgenin hukuken veya
            teknik olarak kütüphane yapımına uygun olduğunu
            göstermez. Parsel, imar, mülkiyet, ulaşım ve
            güncel saha bilgileri ayrıca incelenmelidir.
        </section>

        <section class="legend">
            <span>
                <i class="class-dot built"></i>
                Yapılaşmış alan
            </span>

            <span>
                <i class="class-dot vegetation"></i>
                Bitkisel ve yeşil alan
            </span>

            <span>
                <i class="class-dot open"></i>
                Açık veya çıplak alan
            </span>

            <span>
                <i class="class-dot water"></i>
                Su ve sulak alan
            </span>
        </section>

        <section class="grid">
            {"".join(kartlar)}
        </section>

    </main>
</body>
</html>
    """

    galeri_yolu.write_text(
        sayfa,
        encoding="utf-8",
    )


# ==========================================================
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozetini_yazdir(
    ilce_adi: str,
    worldcover_yili: int,
    sonuc_dataframe: pd.DataFrame,
    worldcover_ogeleri: list[Any],
    yollar: dict[str, Path],
) -> None:
    """
    WorldCover analiz sonuçlarını terminalde gösterir.
    """

    print()
    print("=" * 95)
    print("WORLDCOVER ADAY ARAZİ ÖRTÜSÜ ANALİZİ TAMAMLANDI")
    print("=" * 95)

    print()
    print(
        "İlçe:",
        ilce_adi,
    )

    print(
        "WorldCover yılı:",
        worldcover_yili,
    )

    print(
        "Analiz edilen aday hücre:",
        len(
            sonuc_dataframe
        ),
    )

    print(
        "Kullanılan WorldCover raster parçası:",
        len(
            worldcover_ogeleri
        ),
    )

    print()
    print(
        "Aday hücre sonuçları:"
    )

    for kayit in (
        sonuc_dataframe.itertuples()
    ):

        print()
        print(
            f"  {int(kayit.district_candidate_rank)}. aday "
            f"— {kayit.cell_id}"
        )

        print(
            f"    Kütüphaneye uzaklık: "
            f"{kayit.nearest_library_distance_km:.2f} km"
        )

        print(
            f"    Yapılaşmış alan: "
            f"%{kayit.built_up_pct:.2f}"
        )

        print(
            f"    Bitkisel / yeşil alan: "
            f"%{kayit.vegetation_pct:.2f}"
        )

        print(
            f"    Açık / çıplak alan: "
            f"%{kayit.open_bare_pct:.2f}"
        )

        print(
            f"    Su / sulak alan: "
            f"%{kayit.water_wetland_pct:.2f}"
        )

        print(
            f"    Baskın sınıf: "
            f"{kayit.dominant_landcover_class}"
        )

        print(
            f"    WorldCover kapsaması: "
            f"%{kayit.worldcover_coverage_pct:.2f}"
        )

    print()
    print(
        "Aday özet tablosu:"
    )

    print(
        f"  {yollar['aday_ozeti_csv']}"
    )

    print()
    print(
        "Analiz metadata dosyası:"
    )

    print(
        f"  {yollar['analiz_ozeti_json']}"
    )

    print()
    print(
        "Arazi örtüsü galerisi:"
    )

    print(
        f"  {yollar['galeri_html']}"
    )

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    Seçilen ilçenin gerçek aday hücreleri için
    ESA WorldCover arazi örtüsü analizi yapar.
    """

    argumanlar = argumanlari_oku()

    ilce_adi = (
        argumanlar.ilce
    )

    worldcover_yili = (
        argumanlar.yil
    )

    ilce_slug = slug_olustur(
        ilce_adi
    )

    yollar = dosya_yollarini_olustur(
        ilce_slug,
        worldcover_yili,
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

    print(
        f"  WorldCover yılı: {worldcover_yili}"
    )

    print()
    print(
        "Gerçek aday hizmet hücreleri okunuyor..."
    )

    adaylar = aday_hucreleri_oku(
        yollar[
            "pilot_aday_geojson"
        ],
        ilce_slug,
    )

    print(
        "WorldCover sorgu alanı hesaplanıyor..."
    )

    bbox = birlesik_bbox_hesapla(
        adaylar
    )

    print(
        "ESA WorldCover verisi STAC servisinde aranıyor..."
    )

    worldcover_ogeleri = (
        worldcover_ogelerini_bul(
            bbox,
            worldcover_yili,
        )
    )

    print(
        "Aday hücrelerin arazi örtüsü "
        "oranları hesaplanıyor..."
    )

    sonuc_dataframe = (
        adaylari_analiz_et(
            adaylar,
            worldcover_ogeleri,
            ilce_slug,
            worldcover_yili,
            yollar,
        )
    )

    print(
        "Analiz sonuçları kaydediliyor..."
    )

    ciktilari_kaydet(
        sonuc_dataframe,
        ilce_adi,
        ilce_slug,
        worldcover_yili,
        bbox,
        worldcover_ogeleri,
        yollar,
    )

    print(
        "Arazi örtüsü inceleme sayfası oluşturuluyor..."
    )

    galeri_html_olustur(
        ilce_adi,
        worldcover_yili,
        sonuc_dataframe,
        yollar[
            "galeri_html"
        ],
    )

    terminal_ozetini_yazdir(
        ilce_adi,
        worldcover_yili,
        sonuc_dataframe,
        worldcover_ogeleri,
        yollar,
    )


if __name__ == "__main__":
    main()