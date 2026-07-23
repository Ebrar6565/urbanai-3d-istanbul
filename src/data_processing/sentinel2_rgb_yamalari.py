from __future__ import annotations

import argparse
import json
import re
import unicodedata

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio

from PIL import Image
from rasterio.enums import ColorInterp, Resampling
from rasterio.transform import from_bounds
from rasterio.warp import reproject, transform_bounds


# ==========================================================
# PROJE VE STAC AYARLARI
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

STAC_API_ADRESI = (
    "https://planetarycomputer.microsoft.com/api/stac/v1"
)

KOLEKSIYON_ADI = "sentinel-2-l2a"

COGRAFI_CRS = "EPSG:4326"

# İstanbul analizlerinde ortak hedef koordinat sistemi.
CIKTI_CRS = "EPSG:32635"

HEDEF_COZUNURLUK_METRE = 10.0

SAHNE_ZAMAN_TOLERANSI_DAKIKA = 3

ANALIZE_HAZIR_ESIGI = 95.0


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
# ARGÜMANLAR
# ==========================================================

def argumanlari_oku() -> argparse.Namespace:
    """
    İşlenecek ilçeyi komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Aynı Sentinel-2 geçişine ait birden fazla "
            "karoyu birleştirerek tam RGB yamaları üretir."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help=(
            "RGB yamaları oluşturulacak ilçe. "
            "Örnek: Pendik"
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
# SLUG
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
    ).strip("_")

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
    İlçeye ait girdi ve çıktı yollarını oluşturur.
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
    }


# ==========================================================
# JSON OKUMA
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
# SEÇİLEN ANA SAHNEYİ OKUMA
# ==========================================================

def secilen_sahneyi_oku(
    sahne_json_yolu: Path,
    beklenen_ilce_slug: str,
) -> dict[str, Any]:
    """
    Sahne seçim aşamasındaki ana Sentinel-2
    sahnesinin metadata bilgilerini okur.
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
            "Seçilen sahne farklı bir ilçeye ait.\n"
            f"Beklenen: {beklenen_ilce_slug}\n"
            f"Metadata: {metadata_slug}"
        )

    if str(
        metadata["collection"]
    ) != KOLEKSIYON_ADI:
        raise ValueError(
            "Seçilen sahne beklenen Sentinel-2 "
            "koleksiyonuna ait değil."
        )

    return metadata


# ==========================================================
# BBOX VERİLERİNİ OKUMA
# ==========================================================

def bbox_verilerini_oku(
    bbox_csv_yolu: Path,
    beklenen_ilce_slug: str,
) -> pd.DataFrame:
    """
    İlçeye ait pilot uydu yamalarının BBOX
    koordinatlarını okur.
    """

    if not bbox_csv_yolu.exists():
        raise FileNotFoundError(
            "Pilot uydu BBOX dosyası bulunamadı:\n"
            f"{bbox_csv_yolu}\n\n"
            "Önce pilot_uydu_alanlari_hazirlama.py "
            "dosyasını çalıştır."
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
                "BBOX dosyasında farklı ilçeye "
                "ait kayıt bulundu."
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

    return dataframe.sort_values(
        by="district_candidate_rank",
        ascending=True,
    ).reset_index(
        drop=True
    )


# ==========================================================
# BİRLEŞİK SORGU BBOX
# ==========================================================

def birlesik_bbox_hesapla(
    bbox_dataframe: pd.DataFrame,
) -> list[float]:
    """
    Bütün pilot alanları kapsayan birleşik BBOX'u
    hesaplar.
    """

    return [
        float(
            bbox_dataframe[
                "min_longitude"
            ].min()
        ),

        float(
            bbox_dataframe[
                "min_latitude"
            ].min()
        ),

        float(
            bbox_dataframe[
                "max_longitude"
            ].max()
        ),

        float(
            bbox_dataframe[
                "max_latitude"
            ].max()
        ),
    ]


# ==========================================================
# AYNI UYDU GEÇİŞİNDEKİ KAROLARI GETİRME
# ==========================================================

def ayni_gecis_sahnelerini_getir(
    metadata: dict[str, Any],
    bbox_dataframe: pd.DataFrame,
):
    """
    Ana sahneyle aynı zaman aralığında çekilmiş,
    pilot alanla kesişen bütün Sentinel-2
    karolarını STAC servisinden getirir.
    """

    secilen_tarih = pd.to_datetime(
        metadata[
            "datetime"
        ],
        utc=True,
    ).to_pydatetime()

    baslangic = (
        secilen_tarih
        - timedelta(
            minutes=(
                SAHNE_ZAMAN_TOLERANSI_DAKIKA
            )
        )
    )

    bitis = (
        secilen_tarih
        + timedelta(
            minutes=(
                SAHNE_ZAMAN_TOLERANSI_DAKIKA
            )
        )
    )

    sorgu_bbox = birlesik_bbox_hesapla(
        bbox_dataframe
    )

    katalog = pystac_client.Client.open(
        STAC_API_ADRESI
    )

    arama = katalog.search(
        collections=[
            KOLEKSIYON_ADI,
        ],

        bbox=sorgu_bbox,

        datetime=(
            f"{baslangic.isoformat()}/"
            f"{bitis.isoformat()}"
        ),

        max_items=100,
    )

    beklenen_platform = str(
        metadata.get(
            "platform",
            "",
        )
    ).strip().lower()

    sahneler = []

    for sahne in arama.items():

        sahne_tarihi = sahne.datetime

        if sahne_tarihi is None:
            continue

        if sahne_tarihi.tzinfo is None:
            sahne_tarihi = (
                sahne_tarihi.replace(
                    tzinfo=timezone.utc
                )
            )

        zaman_farki_saniye = abs(
            (
                sahne_tarihi
                - secilen_tarih
            ).total_seconds()
        )

        if zaman_farki_saniye > (
            SAHNE_ZAMAN_TOLERANSI_DAKIKA
            * 60
        ):
            continue

        sahne_platformu = str(
            sahne.properties.get(
                "platform",
                "",
            )
        ).strip().lower()

        if (
            beklenen_platform
            and sahne_platformu
            and sahne_platformu
            != beklenen_platform
        ):
            continue

        sahneler.append(
            planetary_computer.sign(
                sahne
            )
        )

    if not sahneler:
        raise RuntimeError(
            "Seçilen Sentinel-2 geçişine ait "
            "uygun karo bulunamadı."
        )

    ana_item_id = str(
        metadata[
            "item_id"
        ]
    )

    sahneler.sort(
        key=lambda sahne: (
            0
            if sahne.id == ana_item_id
            else 1,

            float(
                sahne.properties.get(
                    "eo:cloud_cover",
                    999,
                )
            ),

            sahne.id,
        )
    )

    return sahneler


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

    hedef_anahtar = (
        asset_adi.lower()
    )

    for anahtar, asset in (
        sahne.assets.items()
    ):
        if (
            anahtar.lower()
            == hedef_anahtar
        ):
            return asset

    raise KeyError(
        f"{asset_adi} bandı "
        f"{sahne.id} sahnesinde bulunamadı."
    )


# ==========================================================
# HEDEF RASTER GRİDİ
# ==========================================================

def hedef_grid_olustur(
    bbox: list[float],
) -> tuple[Any, int, int]:
    """
    Coğrafi BBOX'u ortak hedef koordinat sistemine
    dönüştürüp yaklaşık 10 metre çözünürlüklü
    sabit bir raster gridi oluşturur.
    """

    sol, alt, sag, ust = transform_bounds(
        COGRAFI_CRS,
        CIKTI_CRS,
        bbox[0],
        bbox[1],
        bbox[2],
        bbox[3],
        densify_pts=21,
    )

    genislik = max(
        1,
        int(
            np.ceil(
                (
                    sag
                    - sol
                )
                / HEDEF_COZUNURLUK_METRE
            )
        ),
    )

    yukseklik = max(
        1,
        int(
            np.ceil(
                (
                    ust
                    - alt
                )
                / HEDEF_COZUNURLUK_METRE
            )
        ),
    )

    hedef_transform = from_bounds(
        sol,
        alt,
        sag,
        ust,
        genislik,
        yukseklik,
    )

    return (
        hedef_transform,
        genislik,
        yukseklik,
    )


# ==========================================================
# TEK ASSETİ HEDEF GRİDE DÖNÜŞTÜRME
# ==========================================================

def asseti_hedef_gride_yansit(
    asset_href: str,
    hedef_transform,
    genislik: int,
    yukseklik: int,
) -> np.ndarray:
    """
    Farklı Sentinel karolarındaki raster bandını
    ortak hedef koordinat sistemine dönüştürür.
    """

    hedef = np.zeros(
        (
            yukseklik,
            genislik,
        ),
        dtype=np.uint16,
    )

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

            reproject(
                source=rasterio.band(
                    kaynak,
                    1,
                ),

                destination=hedef,

                src_transform=(
                    kaynak.transform
                ),

                src_crs=(
                    kaynak.crs
                ),

                src_nodata=(
                    kaynak.nodata
                    if kaynak.nodata is not None
                    else 0
                ),

                dst_transform=(
                    hedef_transform
                ),

                dst_crs=(
                    CIKTI_CRS
                ),

                dst_nodata=0,

                resampling=(
                    Resampling.bilinear
                ),
            )

    return hedef


# ==========================================================
# TEK BANDIN ÇOKLU KARO MOZAIĞI
# ==========================================================

def band_mozaigi_olustur(
    sahneler,
    asset_adi: str,
    hedef_transform,
    genislik: int,
    yukseklik: int,
) -> tuple[np.ndarray, list[str]]:
    """
    Aynı Sentinel geçişine ait karolardaki tek
    bandı ortak hedef gridde birleştirir.
    """

    mozaik = np.zeros(
        (
            yukseklik,
            genislik,
        ),
        dtype=np.uint16,
    )

    katkida_bulunan_sahneler: list[str] = []

    for sahne in sahneler:

        try:
            asset = asset_bul(
                sahne,
                asset_adi,
            )

            parca = asseti_hedef_gride_yansit(
                asset.href,
                hedef_transform,
                genislik,
                yukseklik,
            )

        except (
            KeyError,
            rasterio.errors.RasterioError,
            OSError,
            ValueError,
        ):
            continue

        yeni_piksel_maskesi = (
            (mozaik == 0)
            & (parca > 0)
        )

        if np.any(
            yeni_piksel_maskesi
        ):
            mozaik[
                yeni_piksel_maskesi
            ] = parca[
                yeni_piksel_maskesi
            ]

            katkida_bulunan_sahneler.append(
                sahne.id
            )

    return (
        mozaik,
        katkida_bulunan_sahneler,
    )


# ==========================================================
# RGB GEOTIFF KAYDETME
# ==========================================================

def rgb_geotiff_kaydet(
    cikti_yolu: Path,
    rgb_verisi: np.ndarray,
    transform,
) -> None:
    """
    Üç bantlı coğrafi GeoTIFF dosyası oluşturur.
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
        "crs": CIKTI_CRS,
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
# PNG KONTRAST DÖNÜŞÜMÜ
# ==========================================================

def bandi_8_bit_yap(
    bant: np.ndarray,
    gecerli_maske: np.ndarray,
) -> np.ndarray:
    """
    Ham Sentinel değerlerini PNG önizlemesi için
    0-255 aralığına dönüştürür.
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
        ust_deger = (
            alt_deger
            + 1
        )

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
# PNG ÖNİZLEME
# ==========================================================

def png_onizleme_kaydet(
    cikti_yolu: Path,
    rgb_verisi: np.ndarray,
) -> float:
    """
    PNG önizlemesini kaydeder ve gerçek geçerli
    piksel oranını döndürür.
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Bir pikselin geçerli sayılması için üç RGB
    # bandının da veri içermesi gerekir.
    gecerli_maske = np.all(
        rgb_verisi > 0,
        axis=0,
    )

    gecerli_piksel_orani = (
        gecerli_maske.mean()
        * 100
    )

    rgb_8_bit = np.stack(
        [
            bandi_8_bit_yap(
                rgb_verisi[0],
                gecerli_maske,
            ),

            bandi_8_bit_yap(
                rgb_verisi[1],
                gecerli_maske,
            ),

            bandi_8_bit_yap(
                rgb_verisi[2],
                gecerli_maske,
            ),
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
# TEK YAMA ÜRETİMİ
# ==========================================================

def tek_yamayi_olustur(
    sahneler,
    bbox_kaydi: pd.Series,
    yollar: dict[str, Path],
    ilce_slug: str,
) -> dict[str, Any]:
    """
    Tek pilot alan için aynı geçişteki karoları
    kullanarak tam RGB yaması üretir.
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

    (
        hedef_transform,
        genislik,
        yukseklik,
    ) = hedef_grid_olustur(
        bbox
    )

    bant_verileri: list[np.ndarray] = []

    kaynak_sahne_kimlikleri: set[str] = set()

    for bant_etiketi in [
        "red",
        "green",
        "blue",
    ]:

        asset_adi = RGB_BANTLARI[
            bant_etiketi
        ]

        (
            bant_mozaigi,
            katkida_bulunan_sahneler,
        ) = band_mozaigi_olustur(
            sahneler,
            asset_adi,
            hedef_transform,
            genislik,
            yukseklik,
        )

        bant_verileri.append(
            bant_mozaigi
        )

        kaynak_sahne_kimlikleri.update(
            katkida_bulunan_sahneler
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
        hedef_transform,
    )

    gecerli_piksel_orani = (
        png_onizleme_kaydet(
            png_yolu,
            rgb_verisi,
        )
    )

    analiz_hazir = (
        gecerli_piksel_orani
        >= ANALIZE_HAZIR_ESIGI
    )

    kapsama_durumu = (
        "tam"
        if analiz_hazir
        else "kismi"
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

        "crs": CIKTI_CRS,

        "valid_pixel_pct": (
            gecerli_piksel_orani
        ),

        "requested_area_coverage_pct": (
            gecerli_piksel_orani
        ),

        "coverage_status": (
            kapsama_durumu
        ),

        "analysis_ready": int(
            analiz_hazir
        ),

        "source_scene_count": len(
            kaynak_sahne_kimlikleri
        ),

        "source_item_ids_json": json.dumps(
            sorted(
                kaynak_sahne_kimlikleri
            ),
            ensure_ascii=False,
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
# MANİFEST KAYDETME
# ==========================================================

def manifest_kaydet(
    yama_sonuclari: list[dict[str, Any]],
    manifest_yolu: Path,
) -> None:
    """
    Bütün uydu yamalarının teknik bilgilerini
    CSV dosyasına kaydeder.
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
# METADATA GÜNCELLEME
# ==========================================================

def sahne_metadata_guncelle(
    metadata: dict[str, Any],
    sahneler,
    yama_sonuclari: list[dict[str, Any]],
    yollar: dict[str, Path],
) -> None:
    """
    Metadata dosyasına çoklu karo işleme
    bilgilerini ekler.
    """

    guncel_metadata = dict(
        metadata
    )

    guncel_metadata[
        "rgb_processing_mode"
    ] = (
        "same_acquisition_multi_tile_mosaic"
    )

    guncel_metadata[
        "mosaic_item_ids"
    ] = [
        sahne.id
        for sahne in sahneler
    ]

    guncel_metadata[
        "mosaic_item_count"
    ] = len(
        sahneler
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
        "rgb_generated_at_utc"
    ] = datetime.now(
        timezone.utc
    ).isoformat()

    guncel_metadata[
        "rgb_patches"
    ] = yama_sonuclari

    guncel_metadata[
        "rgb_processing_note"
    ] = (
        "Aynı Sentinel-2 geçişine ait karolar "
        "EPSG:32635 hedef gridine dönüştürülerek "
        "birleştirilmiştir. GeoTIFF dosyaları "
        "coğrafi bilgiyi ve ham yansıma değerlerini "
        "korur. PNG dosyaları yalnızca önizlemedir."
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
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozetini_yazdir(
    ilce_adi: str,
    metadata: dict[str, Any],
    sahneler,
    yama_sonuclari: list[dict[str, Any]],
    yollar: dict[str, Path],
) -> None:
    """
    Çoklu karo üretim sonucunu terminalde gösterir.
    """

    print()
    print("=" * 95)
    print(
        "ÇOKLU KARO DESTEKLİ SENTINEL-2 "
        "RGB YAMALARI HAZIRLANDI"
    )
    print("=" * 95)

    print()
    print(
        "İlçe:",
        ilce_adi,
    )

    print(
        "Ana Sentinel-2 sahnesi:",
        metadata[
            "item_id"
        ],
    )

    print(
        "Aynı geçişte kullanılan karo:",
        len(
            sahneler
        ),
    )

    for sahne in sahneler:
        print(
            f"  - {sahne.id}"
        )

    print()
    print(
        "Oluşturulan RGB yaması:",
        len(
            yama_sonuclari
        ),
    )

    hazir_sayisi = sum(
        int(
            yama[
                "analysis_ready"
            ]
        )
        for yama in yama_sonuclari
    )

    print(
        "Analize hazır yama:",
        hazir_sayisi,
    )

    print(
        "Kısmi yama:",
        len(
            yama_sonuclari
        )
        - hazir_sayisi,
    )

    print()
    print(
        "RGB yama sonuçları:"
    )

    for yama in yama_sonuclari:

        print()
        print(
            f"  {yama['patch_id']} "
            f"— {yama['cell_id']}"
        )

        print(
            f"    Boyut: "
            f"{yama['width_pixels']} x "
            f"{yama['height_pixels']} piksel"
        )

        print(
            f"    Gerçek alan kapsaması: "
            f"%{yama['requested_area_coverage_pct']:.2f}"
        )

        print(
            f"    Kullanılan kaynak karo: "
            f"{yama['source_scene_count']}"
        )

        print(
            f"    Analize hazır: "
            f"{'EVET' if yama['analysis_ready'] else 'HAYIR'}"
        )

    print()
    print(
        "RGB manifest dosyası:"
    )

    print(
        f"  {yollar['rgb_manifest_csv']}"
    )

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    Aynı uydu geçişindeki birden fazla karoyu
    birleştirerek seçilen ilçenin RGB yamalarını üretir.
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
        "Aynı uydu geçişine ait Sentinel-2 "
        "karoları aranıyor..."
    )

    sahneler = ayni_gecis_sahnelerini_getir(
        metadata,
        bbox_dataframe,
    )

    print(
        f"Bulunan uygun karo sayısı: "
        f"{len(sahneler)}"
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
        "Çoklu karo destekli RGB yamaları hazırlanıyor..."
    )

    yama_sonuclari: list[dict[str, Any]] = []

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
            sahneler,
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
        sahneler,
        yama_sonuclari,
        yollar,
    )

    terminal_ozetini_yazdir(
        ilce_adi,
        metadata,
        sahneler,
        yama_sonuclari,
        yollar,
    )


if __name__ == "__main__":
    main()