from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio

from PIL import Image
from rasterio.enums import ColorInterp
from rasterio.errors import WindowError
from rasterio.warp import transform_bounds
from rasterio.windows import Window, from_bounds


# ==========================================================
# PROJE YOLU
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]


# ==========================================================
# STAC VE RASTER AYARLARI
# ==========================================================

STAC_API_ADRESI = (
    "https://planetarycomputer.microsoft.com/api/stac/v1"
)

KOLEKSIYON_ADI = "sentinel-2-l2a"

COGRAFI_CRS = "EPSG:4326"

RGB_BANTLARI = {
    "red": "B04",
    "green": "B03",
    "blue": "B02",
}

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
    RGB uydu görüntüsü üretilecek ilçeyi
    komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Seçilen ilçe için Sentinel-2 RGB "
            "uydu görüntüsü yamaları oluşturur."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help=(
            "RGB yamaları oluşturulacak ilçe. "
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
# GÜVENLİ KLASÖR ADI
# ==========================================================

def slug_olustur(
    metin: str,
) -> str:
    """
    İlçe adını dosya ve klasörlerde kullanılabilecek
    güvenli bir ada dönüştürür.

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
    Seçilen ilçenin girdi ve çıktı yollarını oluşturur.
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

    png_klasoru = (
        PROJE_KOKU
        / "frontend"
        / "assets"
        / "sentinel2"
        / ilce_slug
    )

    return {
        "islenmis_klasor": islenmis_klasor,

        "bbox_csv": (
            islenmis_klasor
            / "pilot_uydu_bbox.csv"
        ),

        "secilen_sahne_json": (
            islenmis_klasor
            / "secilen_sentinel2_sahnesi.json"
        ),

        "rgb_manifest_csv": (
            islenmis_klasor
            / "rgb_yama_manifest.csv"
        ),

        "rgb_geotiff_klasoru": (
            ham_uydu_klasoru
            / "rgb_geotiff"
        ),

        "rgb_png_klasoru": (
            png_klasoru
        ),

        "galeri_html": (
            PROJE_KOKU
            / "frontend"
            / f"{ilce_slug}_sentinel2_rgb.html"
        ),
    }


# ==========================================================
# JSON DOSYASI OKUMA
# ==========================================================

def json_dosyasi_oku(
    dosya_yolu: Path,
) -> dict[str, Any]:
    """
    JSON dosyasını güvenli biçimde okur.
    """

    if not dosya_yolu.exists():
        raise FileNotFoundError(
            "Gerekli JSON dosyası bulunamadı:\n"
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
            "JSON dosyası geçerli biçimde değil:\n"
            f"{dosya_yolu}"
        ) from hata


# ==========================================================
# SEÇİLEN SAHNE METADATA DOSYASINI OKUMA
# ==========================================================

def secilen_sahneyi_oku(
    sahne_json_yolu: Path,
    beklenen_ilce_slug: str,
) -> dict[str, Any]:
    """
    Sahne seçim aşamasında kaydedilen
    kesin Sentinel-2 sahnesini okur.
    """

    metadata = json_dosyasi_oku(
        sahne_json_yolu
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
            "Seçilen sahne metadata dosyasında "
            "eksik alanlar var:\n"
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
            "Seçilen sahne farklı bir ilçeye ait.\n"
            f"Beklenen: {beklenen_ilce_slug}\n"
            f"Metadata: {metadata_slug}"
        )

    if (
        str(
            metadata[
                "collection"
            ]
        )
        != KOLEKSIYON_ADI
    ):
        raise ValueError(
            "Seçilen sahne beklenen Sentinel-2 "
            "koleksiyonuna ait değil."
        )

    return metadata


# ==========================================================
# PİLOT BBOX VERİLERİNİ OKUMA
# ==========================================================

def bbox_verilerini_oku(
    bbox_csv_yolu: Path,
    beklenen_ilce_slug: str,
) -> pd.DataFrame:
    """
    Seçilen ilçenin pilot uydu yaması
    koordinatlarını okur.
    """

    if not bbox_csv_yolu.exists():
        raise FileNotFoundError(
            "Pilot uydu BBOX dosyası bulunamadı:\n"
            f"{bbox_csv_yolu}\n\n"
            "Önce pilot_uydu_alanlari_hazirlama.py "
            "dosyasını bu ilçe için çalıştır."
        )

    dataframe = pd.read_csv(
        bbox_csv_yolu
    )

    gerekli_sutunlar = [
        "patch_id",
        "cell_id",
        "district_name",
        "district_candidate_rank",
        "nearest_library_distance_km",
        "min_longitude",
        "min_latitude",
        "max_longitude",
        "max_latitude",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in dataframe.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Pilot BBOX dosyasında eksik sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    if "district_slug" in dataframe.columns:

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
                "BBOX dosyasında farklı ilçeye ait "
                "kayıtlar bulundu."
            )

    sayisal_sutunlar = [
        "district_candidate_rank",
        "nearest_library_distance_km",
        "min_longitude",
        "min_latitude",
        "max_longitude",
        "max_latitude",
    ]

    for sutun in sayisal_sutunlar:

        dataframe[
            sutun
        ] = pd.to_numeric(
            dataframe[
                sutun
            ],
            errors="coerce",
        )

    dataframe = dataframe.dropna(
        subset=[
            "patch_id",
            "cell_id",
            "district_candidate_rank",
            "min_longitude",
            "min_latitude",
            "max_longitude",
            "max_latitude",
        ]
    ).copy()

    if dataframe.empty:
        raise ValueError(
            "BBOX dosyasında geçerli pilot alan bulunamadı."
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
# STAC SAHNESİNİ GETİRME
# ==========================================================

def stac_sahnesini_getir(
    item_id: str,
):
    """
    JSON dosyasında kesinleştirilen Sentinel-2
    sahnesini STAC servisinden getirir.
    """

    katalog = pystac_client.Client.open(
        STAC_API_ADRESI
    )

    arama = katalog.search(
        collections=[
            KOLEKSIYON_ADI,
        ],
        ids=[
            item_id,
        ],
        max_items=1,
    )

    sahneler = list(
        arama.items()
    )

    if not sahneler:
        raise RuntimeError(
            "Seçilen Sentinel-2 sahnesi "
            "STAC servisinde bulunamadı:\n"
            f"{item_id}"
        )

    sahne = planetary_computer.sign(
        sahneler[0]
    )

    return sahne


# ==========================================================
# STAC ASSET BULMA
# ==========================================================

def asset_bul(
    sahne,
    asset_adi: str,
):
    """
    Sentinel-2 sahnesindeki istenen bandı bulur.
    """

    if asset_adi in sahne.assets:
        return sahne.assets[
            asset_adi
        ]

    hedef_anahtar = asset_adi.lower()

    for anahtar, asset in sahne.assets.items():

        if anahtar.lower() == hedef_anahtar:
            return asset

    mevcut_assetler = ", ".join(
        sorted(
            sahne.assets.keys()
        )
    )

    raise KeyError(
        f"{asset_adi} bandı sahnede bulunamadı.\n"
        f"Mevcut asset anahtarları:\n"
        f"{mevcut_assetler}"
    )


# ==========================================================
# RASTER PENCERESİNİ OKUMA
# ==========================================================

def band_yamasini_oku(
    asset_href: str,
    bbox: list[float],
) -> tuple[
    np.ndarray,
    Any,
    Any,
]:
    """
    Sentinel-2 rasterının tamamını indirmeden
    sadece istenen coğrafi pencereyi okur.

    BBOX sırası:
    min_boylam, min_enlem, max_boylam, max_enlem
    """

    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        GDAL_HTTP_MULTIRANGE="YES",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.TIF",
    ):

        with rasterio.open(
            asset_href
        ) as kaynak:

            if kaynak.crs is None:
                raise ValueError(
                    "Uydu bandında koordinat sistemi bulunamadı."
                )

            sol, alt, sag, ust = transform_bounds(
                COGRAFI_CRS,
                kaynak.crs,
                bbox[0],
                bbox[1],
                bbox[2],
                bbox[3],
                densify_pts=21,
            )

            pencere = from_bounds(
                sol,
                alt,
                sag,
                ust,
                transform=kaynak.transform,
            )

            pencere = (
                pencere
                .round_offsets()
                .round_lengths()
            )

            raster_siniri = Window(
                col_off=0,
                row_off=0,
                width=kaynak.width,
                height=kaynak.height,
            )

            try:
                pencere = pencere.intersection(
                    raster_siniri
                )

            except WindowError as hata:
                raise ValueError(
                    "Pilot alan seçilen uydu sahnesinin "
                    "raster sınırları dışında kaldı."
                ) from hata

            if (
                pencere.width <= 0
                or pencere.height <= 0
            ):
                raise ValueError(
                    "Uydu görüntüsü için geçerli "
                    "raster penceresi oluşturulamadı."
                )

            bant = kaynak.read(
                1,
                window=pencere,
            )

            yama_transformu = (
                kaynak.window_transform(
                    pencere
                )
            )

            koordinat_sistemi = kaynak.crs

    return (
        bant,
        yama_transformu,
        koordinat_sistemi,
    )


# ==========================================================
# RGB GEOTIFF KAYDETME
# ==========================================================

def rgb_geotiff_kaydet(
    cikti_yolu: Path,
    rgb_verisi: np.ndarray,
    transform,
    crs,
) -> None:
    """
    B04, B03 ve B02 bantlarını üç bantlı
    coğrafi GeoTIFF olarak kaydeder.
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    bant_sayisi, yukseklik, genislik = (
        rgb_verisi.shape
    )

    profil = {
        "driver": "GTiff",
        "height": yukseklik,
        "width": genislik,
        "count": bant_sayisi,
        "dtype": rgb_verisi.dtype,
        "crs": crs,
        "transform": transform,
        "compress": "deflate",
        "nodata": 0,
    }

    with rasterio.open(
        cikti_yolu,
        "w",
        **profil,
    ) as hedef:

        hedef.write(
            rgb_verisi
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
    Ham Sentinel-2 piksel değerlerini PNG
    önizlemesi için 0-255 arasına dönüştürür.
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
# PNG ÖNİZLEME KAYDETME
# ==========================================================

def png_onizleme_kaydet(
    cikti_yolu: Path,
    rgb_verisi: np.ndarray,
) -> float:
    """
    RGB GeoTIFF verisinden tarayıcıda görüntülenebilen
    PNG önizlemesi oluşturur.

    Geçerli piksel oranını döndürür.
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    gecerli_maske = np.any(
        rgb_verisi > 0,
        axis=0,
    )

    gecerli_piksel_orani = (
        gecerli_maske.mean()
        * 100
    )

    kirmizi = bandi_8_bit_yap(
        rgb_verisi[0],
        gecerli_maske,
    )

    yesil = bandi_8_bit_yap(
        rgb_verisi[1],
        gecerli_maske,
    )

    mavi = bandi_8_bit_yap(
        rgb_verisi[2],
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

    return round(
        float(
            gecerli_piksel_orani
        ),
        2,
    )


# ==========================================================
# TEK PİLOT YAMAYI OLUŞTURMA
# ==========================================================

def tek_yamayi_olustur(
    sahne,
    bbox_kaydi: pd.Series,
    yollar: dict[str, Path],
    ilce_slug: str,
) -> dict[str, Any]:
    """
    Tek pilot alanın B04, B03 ve B02 bantlarını
    okuyarak GeoTIFF ve PNG üretir.
    """

    patch_id = str(
        bbox_kaydi[
            "patch_id"
        ]
    )

    bbox = [
        float(
            bbox_kaydi[
                "min_longitude"
            ]
        ),
        float(
            bbox_kaydi[
                "min_latitude"
            ]
        ),
        float(
            bbox_kaydi[
                "max_longitude"
            ]
        ),
        float(
            bbox_kaydi[
                "max_latitude"
            ]
        ),
    ]

    bant_verileri: list[
        np.ndarray
    ] = []

    referans_transform = None

    referans_crs = None

    referans_boyut = None

    for bant_etiketi in [
        "red",
        "green",
        "blue",
    ]:

        asset_adi = RGB_BANTLARI[
            bant_etiketi
        ]

        asset = asset_bul(
            sahne,
            asset_adi,
        )

        (
            bant,
            bant_transformu,
            bant_crs,
        ) = band_yamasini_oku(
            asset.href,
            bbox,
        )

        if referans_boyut is None:

            referans_boyut = bant.shape

            referans_transform = (
                bant_transformu
            )

            referans_crs = bant_crs

        elif bant.shape != referans_boyut:

            raise ValueError(
                f"{patch_id} için RGB bant boyutları "
                "birbirinden farklı çıktı.\n"
                f"Beklenen: {referans_boyut}\n"
                f"Bulunan: {bant.shape}\n"
                f"Bant: {asset_adi}"
            )

        bant_verileri.append(
            bant
        )

    rgb_verisi = np.stack(
        bant_verileri,
        axis=0,
    )

    geotiff_yolu = (
        yollar[
            "rgb_geotiff_klasoru"
        ]
        / f"{patch_id}_rgb.tif"
    )

    png_yolu = (
        yollar[
            "rgb_png_klasoru"
        ]
        / f"{patch_id}_rgb.png"
    )

    rgb_geotiff_kaydet(
        geotiff_yolu,
        rgb_verisi,
        referans_transform,
        referans_crs,
    )

    gecerli_piksel_orani = (
        png_onizleme_kaydet(
            png_yolu,
            rgb_verisi,
        )
    )

    png_relative_path = (
        f"assets/sentinel2/"
        f"{ilce_slug}/"
        f"{patch_id}_rgb.png"
    )

    return {
        "patch_id": patch_id,

        "cell_id": str(
            bbox_kaydi[
                "cell_id"
            ]
        ),

        "district_name": str(
            bbox_kaydi[
                "district_name"
            ]
        ),

        "district_slug": ilce_slug,

        "district_candidate_rank": int(
            bbox_kaydi[
                "district_candidate_rank"
            ]
        ),

        "nearest_library_distance_km": float(
            bbox_kaydi[
                "nearest_library_distance_km"
            ]
        ),

        "width_pixels": int(
            rgb_verisi.shape[2]
        ),

        "height_pixels": int(
            rgb_verisi.shape[1]
        ),

        "band_count": int(
            rgb_verisi.shape[0]
        ),

        "dtype": str(
            rgb_verisi.dtype
        ),

        "crs": str(
            referans_crs
        ),

        "valid_pixel_pct": (
            gecerli_piksel_orani
        ),

        "min_longitude": bbox[0],

        "min_latitude": bbox[1],

        "max_longitude": bbox[2],

        "max_latitude": bbox[3],

        "geotiff_path": str(
            geotiff_yolu
        ),

        "png_path": str(
            png_yolu
        ),

        "png_relative_path": (
            png_relative_path
        ),
    }


# ==========================================================
# RGB MANİFEST DOSYASINI KAYDETME
# ==========================================================

def manifest_kaydet(
    yama_sonuclari: list[
        dict[str, Any]
    ],
    manifest_yolu: Path,
) -> None:
    """
    Oluşturulan bütün RGB yamalarının teknik
    bilgilerini CSV dosyasına kaydeder.
    """

    manifest_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataframe = pd.DataFrame(
        yama_sonuclari
    )

    dataframe = dataframe.sort_values(
        by="district_candidate_rank",
        ascending=True,
    )

    dataframe.to_csv(
        manifest_yolu,
        index=False,
        encoding="utf-8-sig",
    )


# ==========================================================
# SAHNE METADATA DOSYASINI GÜNCELLEME
# ==========================================================

def sahne_metadata_guncelle(
    metadata: dict[str, Any],
    sahne,
    yama_sonuclari: list[
        dict[str, Any]
    ],
    yollar: dict[str, Path],
) -> None:
    """
    Seçilen sahne metadata dosyasına
    RGB üretim bilgilerini ekler.
    """

    guncel_metadata = dict(
        metadata
    )

    guncel_metadata[
        "available_assets"
    ] = sorted(
        sahne.assets.keys()
    )

    guncel_metadata[
        "rgb_assets"
    ] = RGB_BANTLARI

    guncel_metadata[
        "rgb_patch_count"
    ] = len(
        yama_sonuclari
    )

    guncel_metadata[
        "rgb_manifest_csv"
    ] = str(
        yollar[
            "rgb_manifest_csv"
        ]
    )

    guncel_metadata[
        "rgb_gallery_html"
    ] = str(
        yollar[
            "galeri_html"
        ]
    )

    guncel_metadata[
        "rgb_generated_at_utc"
    ] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    guncel_metadata[
        "rgb_patches"
    ] = yama_sonuclari

    guncel_metadata[
        "rgb_processing_note"
    ] = (
        "GeoTIFF dosyaları ham Sentinel-2 bant "
        "değerlerini ve coğrafi bilgiyi korur. "
        "PNG dosyaları yalnızca görsel kontrol için "
        "yüzdelik kontrast germe işleminden geçirilmiştir."
    )

    yollar[
        "secilen_sahne_json"
    ].write_text(
        json.dumps(
            guncel_metadata,
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8",
    )


# ==========================================================
# HTML GALERİSİ
# ==========================================================

def galeri_html_olustur(
    ilce_adi: str,
    ilce_slug: str,
    metadata: dict[str, Any],
    yama_sonuclari: list[
        dict[str, Any]
    ],
    galeri_yolu: Path,
) -> None:
    """
    İlçeye ait RGB yamalarını karşılaştırmalı
    bir HTML sayfasında gösterir.
    """

    galeri_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    kartlar: list[str] = []

    sirali_sonuclar = sorted(
        yama_sonuclari,
        key=lambda kayit: (
            kayit[
                "district_candidate_rank"
            ]
        ),
    )

    for yama in sirali_sonuclar:

        patch_id = html.escape(
            yama[
                "patch_id"
            ]
        )

        cell_id = html.escape(
            yama[
                "cell_id"
            ]
        )

        png_relative_path = html.escape(
            yama[
                "png_relative_path"
            ]
        )

        kartlar.append(
            f"""
            <article class="patch-card">
                <img
                    src="{png_relative_path}"
                    alt="{patch_id} Sentinel-2 RGB uydu görüntüsü"
                >

                <div class="patch-body">
                    <span class="rank-badge">
                        {yama["district_candidate_rank"]}. aday
                    </span>

                    <h2>{patch_id}</h2>

                    <dl>
                        <div>
                            <dt>Hücre</dt>
                            <dd>{cell_id}</dd>
                        </div>

                        <div>
                            <dt>Kütüphaneye uzaklık</dt>
                            <dd>
                                {yama["nearest_library_distance_km"]:.2f} km
                            </dd>
                        </div>

                        <div>
                            <dt>Görüntü boyutu</dt>
                            <dd>
                                {yama["width_pixels"]}
                                ×
                                {yama["height_pixels"]}
                                piksel
                            </dd>
                        </div>

                        <div>
                            <dt>Geçerli piksel</dt>
                            <dd>
                                %{yama["valid_pixel_pct"]:.2f}
                            </dd>
                        </div>
                    </dl>
                </div>
            </article>
            """
        )

    item_id = html.escape(
        str(
            metadata[
                "item_id"
            ]
        )
    )

    platform = html.escape(
        str(
            metadata.get(
                "platform"
            )
            or "Bilinmiyor"
        )
    )

    tarih_metni = str(
        metadata[
            "datetime"
        ]
    )

    try:
        tarih = pd.to_datetime(
            tarih_metni,
            utc=True,
        ).strftime(
            "%d.%m.%Y"
        )

    except (
        ValueError,
        TypeError,
    ):
        tarih = html.escape(
            tarih_metni
        )

    bulut_orani = float(
        metadata[
            "cloud_cover_pct"
        ]
    )

    secim_yontemi = html.escape(
        str(
            metadata.get(
                "selection_method"
            )
            or "Belirtilmedi"
        )
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
        {html.escape(ilce_adi)} Sentinel-2 RGB Alanları
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
            padding: 38px 24px 28px;
            background: #ffffff;
            border-bottom: 1px solid #dbe2ea;
        }}

        .header-inner,
        main {{
            max-width: 1250px;
            margin: 0 auto;
        }}

        h1 {{
            margin: 0 0 12px;
            font-size: 30px;
        }}

        .subtitle {{
            max-width: 880px;
            margin: 0;
            color: #657083;
            line-height: 1.6;
        }}

        .metadata {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 22px;
        }}

        .metadata span {{
            padding: 8px 11px;
            border: 1px solid #d9e0e8;
            border-radius: 999px;
            background: #f8fafc;
            font-size: 13px;
        }}

        main {{
            padding: 30px 24px 50px;
        }}

        .notice {{
            margin-bottom: 24px;
            padding: 16px 18px;
            border-left: 4px solid #2563eb;
            border-radius: 8px;
            background: #eff6ff;
            color: #334155;
            line-height: 1.6;
        }}

        .grid {{
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
        }}

        .patch-card {{
            overflow: hidden;
            border: 1px solid #dce3eb;
            border-radius: 14px;
            background: #ffffff;
            box-shadow: 0 10px 28px rgba(15, 23, 42, 0.07);
        }}

        .patch-card img {{
            display: block;
            width: 100%;
            aspect-ratio: 1 / 1;
            object-fit: cover;
            background: #dbe3ec;
        }}

        .patch-body {{
            padding: 17px;
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
            margin: 0 0 15px;
            font-size: 19px;
        }}

        dl {{
            display: grid;
            gap: 10px;
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
            color: #6b7280;
            font-size: 13px;
        }}

        dd {{
            margin: 0;
            text-align: right;
            font-size: 13px;
            font-weight: 700;
        }}

        code {{
            word-break: break-all;
        }}
    </style>
</head>

<body>
    <header>
        <div class="header-inner">
            <h1>
                {html.escape(ilce_adi)} Sentinel-2 RGB Alanları
            </h1>

            <p class="subtitle">
                Hizmet boşluğu analizinden seçilen pilot
                hücrelerin gerçek renkli Sentinel-2
                görüntüleri. Sistem ilçe parametresiyle
                çalıştığı için aynı işlem başka ilçelere
                de uygulanabilir.
            </p>

            <div class="metadata">
                <span>İlçe kodu: {html.escape(ilce_slug)}</span>
                <span>Tarih: {tarih}</span>
                <span>Platform: {platform}</span>
                <span>Bulut oranı: %{bulut_orani:.4f}</span>
                <span>Yama sayısı: {len(yama_sonuclari)}</span>
            </div>
        </div>
    </header>

    <main>
        <section class="notice">
            <strong>Seçim yöntemi:</strong>
            {secim_yontemi}

            <br><br>

            <strong>Sentinel-2 sahne kimliği:</strong>
            <code>{item_id}</code>

            <br><br>

            PNG dosyaları yalnızca görsel inceleme
            içindir. Semantik segmentasyon aşamasında
            coğrafi bilgiyi ve ham piksel değerlerini
            koruyan GeoTIFF dosyaları kullanılacaktır.
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
    ilce_slug: str,
    metadata: dict[str, Any],
    yama_sonuclari: list[
        dict[str, Any]
    ],
    yollar: dict[str, Path],
) -> None:
    """
    RGB yama üretim sonuçlarını terminalde gösterir.
    """

    print()
    print("=" * 95)
    print("SENTINEL-2 RGB YAMALARI HAZIRLANDI")
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
        "Sentinel-2 sahnesi:",
        metadata[
            "item_id"
        ],
    )

    print(
        "Sahne tarihi:",
        metadata[
            "datetime"
        ],
    )

    print(
        "Bulut oranı:",
        f"%{float(metadata['cloud_cover_pct']):.6f}",
    )

    print(
        "Oluşturulan RGB yaması:",
        len(
            yama_sonuclari
        ),
    )

    print()
    print(
        "RGB yama sonuçları:"
    )

    for yama in sorted(
        yama_sonuclari,
        key=lambda kayit: (
            kayit[
                "district_candidate_rank"
            ]
        ),
    ):

        print()
        print(
            f"  {yama['patch_id']}"
        )

        print(
            f"    Hücre: "
            f"{yama['cell_id']}"
        )

        print(
            f"    Boyut: "
            f"{yama['width_pixels']} x "
            f"{yama['height_pixels']} piksel"
        )

        print(
            f"    Geçerli piksel: "
            f"%{yama['valid_pixel_pct']:.2f}"
        )

        print(
            f"    GeoTIFF: "
            f"{yama['geotiff_path']}"
        )

        print(
            f"    PNG: "
            f"{yama['png_path']}"
        )

    print()
    print(
        "RGB manifest dosyası:"
    )

    print(
        f"  {yollar['rgb_manifest_csv']}"
    )

    print()
    print(
        "RGB karşılaştırma sayfası:"
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
    Seçilen ilçe için daha önce kesinleştirilmiş
    Sentinel-2 sahnesinden RGB yamalarını üretir.
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
        "Seçilen Sentinel-2 sahnesi okunuyor..."
    )

    metadata = secilen_sahneyi_oku(
        yollar[
            "secilen_sahne_json"
        ],
        ilce_slug,
    )

    print(
        "Pilot uydu BBOX alanları okunuyor..."
    )

    bbox_dataframe = bbox_verilerini_oku(
        yollar[
            "bbox_csv"
        ],
        ilce_slug,
    )

    print(
        "Seçilen sahne STAC servisinden getiriliyor..."
    )

    sahne = stac_sahnesini_getir(
        str(
            metadata[
                "item_id"
            ]
        )
    )

    print(
        "RGB bantları kontrol ediliyor..."
    )

    for asset_adi in RGB_BANTLARI.values():

        asset_bul(
            sahne,
            asset_adi,
        )

    yollar[
        "rgb_geotiff_klasoru"
    ].mkdir(
        parents=True,
        exist_ok=True,
    )

    yollar[
        "rgb_png_klasoru"
    ].mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "Pilot RGB görüntüleri hazırlanıyor..."
    )

    yama_sonuclari: list[
        dict[str, Any]
    ] = []

    for _, bbox_kaydi in (
        bbox_dataframe.iterrows()
    ):

        patch_id = str(
            bbox_kaydi[
                "patch_id"
            ]
        )

        print(
            f"  {patch_id} işleniyor..."
        )

        yama_sonucu = tek_yamayi_olustur(
            sahne,
            bbox_kaydi,
            yollar,
            ilce_slug,
        )

        yama_sonuclari.append(
            yama_sonucu
        )

    print(
        "RGB manifest tablosu kaydediliyor..."
    )

    manifest_kaydet(
        yama_sonuclari,
        yollar[
            "rgb_manifest_csv"
        ],
    )

    print(
        "Sahne metadata dosyası güncelleniyor..."
    )

    sahne_metadata_guncelle(
        metadata,
        sahne,
        yama_sonuclari,
        yollar,
    )

    print(
        "RGB karşılaştırma sayfası oluşturuluyor..."
    )

    galeri_html_olustur(
        ilce_adi,
        ilce_slug,
        metadata,
        yama_sonuclari,
        yollar[
            "galeri_html"
        ],
    )

    terminal_ozetini_yazdir(
        ilce_adi,
        ilce_slug,
        metadata,
        yama_sonuclari,
        yollar,
    )


if __name__ == "__main__":
    main()