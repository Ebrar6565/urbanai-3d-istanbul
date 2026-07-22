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
from rasterio.transform import array_bounds
from rasterio.windows import Window
from shapely.geometry import box


# ==========================================================
# PROJE KÖKÜ
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]


# ==========================================================
# KOORDİNAT SİSTEMİ
# ==========================================================

COGRAFI_CRS = "EPSG:4326"


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
    Segmentasyon giriş parçalarının ayarlarını
    komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Seçilen ilçenin Sentinel-2 RGB mozaiğini "
            "segmentasyon modeli için sabit boyutlu "
            "coğrafi parçalara ayırır."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help=(
            "Segmentasyon girdisi hazırlanacak ilçe. "
            "Örnek: Esenyurt"
        ),
    )

    parser.add_argument(
        "--karo-boyutu",
        type=int,
        default=128,
        help=(
            "Her segmentasyon karosunun piksel cinsinden "
            "genişliği ve yüksekliği. Varsayılan: 128"
        ),
    )

    parser.add_argument(
        "--adim",
        type=int,
        default=96,
        help=(
            "Karo başlangıçları arasındaki piksel adımı. "
            "Karo boyutundan küçük olması karoların "
            "örtüşmesini sağlar. Varsayılan: 96"
        ),
    )

    parser.add_argument(
        "--min-gecerli-oran",
        type=float,
        default=25.0,
        help=(
            "Kaydedilecek bir karoda bulunması gereken "
            "en düşük geçerli piksel yüzdesi. "
            "Varsayılan: 25"
        ),
    )

    argumanlar = parser.parse_args()

    argumanlar.ilce = argumanlar.ilce.strip()

    if not argumanlar.ilce:
        parser.error(
            "--ilce değeri boş bırakılamaz."
        )

    if argumanlar.karo_boyutu <= 0:
        parser.error(
            "--karo-boyutu sıfırdan büyük olmalıdır."
        )

    if argumanlar.adim <= 0:
        parser.error(
            "--adim sıfırdan büyük olmalıdır."
        )

    if argumanlar.adim > argumanlar.karo_boyutu:
        parser.error(
            "--adim, --karo-boyutu değerinden "
            "büyük olmamalıdır."
        )

    if not (
        0
        <= argumanlar.min_gecerli_oran
        <= 100
    ):
        parser.error(
            "--min-gecerli-oran 0 ile 100 "
            "arasında olmalıdır."
        )

    return argumanlar


# ==========================================================
# GÜVENLİ DOSYA VE KLASÖR ADI
# ==========================================================

def slug_olustur(
    metin: str,
) -> str:
    """
    İlçe adını güvenli dosya ve klasör adına dönüştürür.
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
    İlçeye özel girdi ve çıktı yollarını oluşturur.
    """

    islenmis_klasor = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
    )

    mozaik_klasoru = (
        PROJE_KOKU
        / "data"
        / "raw"
        / "satellite"
        / ilce_slug
        / "mosaic"
    )

    segmentasyon_klasoru = (
        islenmis_klasor
        / "segmentation_input"
    )

    frontend_klasoru = (
        PROJE_KOKU
        / "frontend"
        / "assets"
        / "sentinel2"
        / ilce_slug
        / "segmentation_tiles"
    )

    return {
        "mozaik_geotiff": (
            mozaik_klasoru
            / f"{ilce_slug}_pilot_rgb_mozaik.tif"
        ),

        "mozaik_ozeti_json": (
            islenmis_klasor
            / "rgb_mozaik_ozeti.json"
        ),

        "segmentasyon_klasoru": (
            segmentasyon_klasoru
        ),

        "geotiff_klasoru": (
            segmentasyon_klasoru
            / "geotiff"
        ),

        "png_klasoru": frontend_klasoru,

        "manifest_csv": (
            segmentasyon_klasoru
            / "segmentasyon_karo_manifest.csv"
        ),

        "karo_geojson": (
            segmentasyon_klasoru
            / "segmentasyon_karo_sinirlari.geojson"
        ),

        "ayarlar_json": (
            segmentasyon_klasoru
            / "segmentasyon_girdi_ayarlari.json"
        ),

        "galeri_html": (
            PROJE_KOKU
            / "frontend"
            / f"{ilce_slug}_segmentasyon_girdileri.html"
        ),
    }


# ==========================================================
# KARO BAŞLANGIÇ KONUMU HESAPLAMA
# ==========================================================

def baslangic_konumlarini_hesapla(
    toplam_boyut: int,
    karo_boyutu: int,
    adim: int,
) -> list[int]:
    """
    Rasterın tamamını kapsayacak karo başlangıçlarını
    hesaplar.

    Son karo, rasterın son kenarına hizalanır.
    """

    if toplam_boyut <= karo_boyutu:
        return [
            0
        ]

    konumlar = list(
        range(
            0,
            toplam_boyut - karo_boyutu + 1,
            adim,
        )
    )

    son_konum = (
        toplam_boyut
        - karo_boyutu
    )

    if konumlar[-1] != son_konum:
        konumlar.append(
            son_konum
        )

    return sorted(
        set(
            konumlar
        )
    )


# ==========================================================
# MOZAIK KONTRAST DEĞERLERİNİ HESAPLAMA
# ==========================================================

def global_kontrast_degerlerini_hesapla(
    mozaik: np.ndarray,
) -> list[tuple[float, float]]:
    """
    Bütün karolarda aynı görsel kontrastın kullanılması
    için mozaik genelindeki bant yüzdeliklerini hesaplar.
    """

    gecerli_maske = np.any(
        mozaik > 0,
        axis=0,
    )

    kontrast_degerleri: list[
        tuple[float, float]
    ] = []

    for bant in mozaik:

        gecerli_pikseller = bant[
            gecerli_maske
        ]

        gecerli_pikseller = (
            gecerli_pikseller[
                gecerli_pikseller > 0
            ]
        )

        if gecerli_pikseller.size == 0:
            kontrast_degerleri.append(
                (
                    0.0,
                    1.0,
                )
            )

            continue

        alt_deger = float(
            np.percentile(
                gecerli_pikseller,
                ALT_YUZDELIK,
            )
        )

        ust_deger = float(
            np.percentile(
                gecerli_pikseller,
                UST_YUZDELIK,
            )
        )

        if ust_deger <= alt_deger:
            ust_deger = (
                alt_deger
                + 1
            )

        kontrast_degerleri.append(
            (
                alt_deger,
                ust_deger,
            )
        )

    return kontrast_degerleri


# ==========================================================
# BANTLARI 8 BİT DEĞERE ÇEVİRME
# ==========================================================

def bandi_8_bit_yap(
    bant: np.ndarray,
    gecerli_maske: np.ndarray,
    alt_deger: float,
    ust_deger: float,
) -> np.ndarray:
    """
    Bir bandı, mozaik genelindeki sabit kontrast
    değerlerini kullanarak 0-255 arasına dönüştürür.
    """

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
# KARO GEOTIFF KAYDETME
# ==========================================================

def karo_geotiff_kaydet(
    cikti_yolu: Path,
    karo: np.ndarray,
    transform,
    crs,
) -> None:
    """
    Segmentasyon karosunu üç bantlı
    coğrafi GeoTIFF olarak kaydeder.
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    bant_sayisi, yukseklik, genislik = (
        karo.shape
    )

    profil = {
        "driver": "GTiff",
        "height": yukseklik,
        "width": genislik,
        "count": bant_sayisi,
        "dtype": karo.dtype,
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
            karo
        )

        hedef.colorinterp = (
            ColorInterp.red,
            ColorInterp.green,
            ColorInterp.blue,
        )


# ==========================================================
# KARO PNG KAYDETME
# ==========================================================

def karo_png_kaydet(
    cikti_yolu: Path,
    karo: np.ndarray,
    kontrast_degerleri: list[
        tuple[float, float]
    ],
) -> None:
    """
    Karoyu tarayıcıda incelenebilecek RGB PNG
    biçiminde kaydeder.
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    gecerli_maske = np.any(
        karo > 0,
        axis=0,
    )

    bantlar_8_bit = []

    for bant_index in range(
        karo.shape[0]
    ):

        alt_deger, ust_deger = (
            kontrast_degerleri[
                bant_index
            ]
        )

        bantlar_8_bit.append(
            bandi_8_bit_yap(
                karo[
                    bant_index
                ],
                gecerli_maske,
                alt_deger,
                ust_deger,
            )
        )

    rgb_8_bit = np.stack(
        bantlar_8_bit,
        axis=-1,
    )

    Image.fromarray(
        rgb_8_bit
    ).save(
        cikti_yolu,
        format="PNG",
        optimize=True,
    )


# ==========================================================
# SEGMENTASYON KAROLARINI OLUŞTURMA
# ==========================================================

def segmentasyon_karolarini_olustur(
    mozaik_yolu: Path,
    ilce_slug: str,
    karo_boyutu: int,
    adim: int,
    min_gecerli_oran: float,
    yollar: dict[str, Path],
) -> tuple[
    pd.DataFrame,
    gpd.GeoDataFrame,
    dict[str, Any],
]:
    """
    RGB mozaiği örtüşmeli ve sabit boyutlu
    segmentasyon karolarına ayırır.
    """

    if not mozaik_yolu.exists():
        raise FileNotFoundError(
            "RGB mozaik GeoTIFF bulunamadı:\n"
            f"{mozaik_yolu}\n\n"
            "Önce uydu_rgb_mozaik_hazirlama.py "
            "dosyasını bu ilçe için çalıştır."
        )

    manifest_kayitlari: list[
        dict[str, Any]
    ] = []

    geometri_kayitlari: list[
        dict[str, Any]
    ] = []

    with rasterio.open(
        mozaik_yolu
    ) as kaynak:

        if kaynak.count != 3:
            raise ValueError(
                "Segmentasyon girdisi olarak kullanılacak "
                "mozaik üç bantlı RGB değildir."
            )

        if kaynak.crs is None:
            raise ValueError(
                "RGB mozaikte koordinat sistemi bulunamadı."
            )

        mozaik = kaynak.read()

        kontrast_degerleri = (
            global_kontrast_degerlerini_hesapla(
                mozaik
            )
        )

        sutun_konumlari = (
            baslangic_konumlarini_hesapla(
                kaynak.width,
                karo_boyutu,
                adim,
            )
        )

        satir_konumlari = (
            baslangic_konumlarini_hesapla(
                kaynak.height,
                karo_boyutu,
                adim,
            )
        )

        toplam_aday_karo = (
            len(
                sutun_konumlari
            )
            * len(
                satir_konumlari
            )
        )

        kaydedilen_karo_sayisi = 0

        atlanan_karo_sayisi = 0

        for satir_sirasi, satir_baslangici in enumerate(
            satir_konumlari,
            start=1,
        ):

            for sutun_sirasi, sutun_baslangici in enumerate(
                sutun_konumlari,
                start=1,
            ):

                pencere = Window(
                    col_off=sutun_baslangici,
                    row_off=satir_baslangici,
                    width=karo_boyutu,
                    height=karo_boyutu,
                )

                karo = kaynak.read(
                    window=pencere,
                    boundless=True,
                    fill_value=0,
                )

                gecerli_maske = np.any(
                    karo > 0,
                    axis=0,
                )

                gecerli_piksel_orani = float(
                    gecerli_maske.mean()
                    * 100
                )

                if (
                    gecerli_piksel_orani
                    < min_gecerli_oran
                ):
                    atlanan_karo_sayisi += 1

                    continue

                kaydedilen_karo_sayisi += 1

                karo_id = (
                    f"{ilce_slug.upper()}_"
                    f"SEG_{satir_sirasi:02d}_"
                    f"{sutun_sirasi:02d}"
                )

                karo_transformu = (
                    kaynak.window_transform(
                        pencere
                    )
                )

                geotiff_yolu = (
                    yollar[
                        "geotiff_klasoru"
                    ]
                    / f"{karo_id}.tif"
                )

                png_yolu = (
                    yollar[
                        "png_klasoru"
                    ]
                    / f"{karo_id}.png"
                )

                karo_geotiff_kaydet(
                    geotiff_yolu,
                    karo,
                    karo_transformu,
                    kaynak.crs,
                )

                karo_png_kaydet(
                    png_yolu,
                    karo,
                    kontrast_degerleri,
                )

                alt, sol, ust, sag = (
                    0,
                    0,
                    karo.shape[1],
                    karo.shape[2],
                )

                bati, guney, dogu, kuzey = (
                    array_bounds(
                        ust - alt,
                        sag - sol,
                        karo_transformu,
                    )
                )

                karo_geometrisi = box(
                    bati,
                    guney,
                    dogu,
                    kuzey,
                )

                png_relative_path = (
                    f"assets/sentinel2/"
                    f"{ilce_slug}/"
                    f"segmentation_tiles/"
                    f"{karo_id}.png"
                )

                manifest_kaydi = {
                    "tile_id": karo_id,

                    "district_slug": (
                        ilce_slug
                    ),

                    "tile_row": (
                        satir_sirasi
                    ),

                    "tile_column": (
                        sutun_sirasi
                    ),

                    "row_offset_px": int(
                        satir_baslangici
                    ),

                    "column_offset_px": int(
                        sutun_baslangici
                    ),

                    "width_pixels": int(
                        karo.shape[2]
                    ),

                    "height_pixels": int(
                        karo.shape[1]
                    ),

                    "valid_pixel_pct": round(
                        gecerli_piksel_orani,
                        2,
                    ),

                    "crs": str(
                        kaynak.crs
                    ),

                    "pixel_width_m": abs(
                        float(
                            karo_transformu.a
                        )
                    ),

                    "pixel_height_m": abs(
                        float(
                            karo_transformu.e
                        )
                    ),

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

                manifest_kayitlari.append(
                    manifest_kaydi
                )

                geometri_kayitlari.append(
                    {
                        **manifest_kaydi,
                        "geometry": (
                            karo_geometrisi
                        ),
                    }
                )

    if not manifest_kayitlari:
        raise ValueError(
            "Belirlenen geçerli piksel eşiğini geçen "
            "segmentasyon karosu bulunamadı."
        )

    manifest = pd.DataFrame(
        manifest_kayitlari
    )

    karo_geometrileri = gpd.GeoDataFrame(
        geometri_kayitlari,
        geometry="geometry",
        crs=kaynak.crs,
    )

    karo_geometrileri = (
        karo_geometrileri
        .to_crs(
            COGRAFI_CRS
        )
    )

    ozet = {
        "total_candidate_tile_count": (
            toplam_aday_karo
        ),

        "saved_tile_count": (
            kaydedilen_karo_sayisi
        ),

        "skipped_tile_count": (
            atlanan_karo_sayisi
        ),

        "average_valid_pixel_pct": round(
            float(
                manifest[
                    "valid_pixel_pct"
                ].mean()
            ),
            2,
        ),

        "minimum_valid_pixel_pct": round(
            float(
                manifest[
                    "valid_pixel_pct"
                ].min()
            ),
            2,
        ),

        "maximum_valid_pixel_pct": round(
            float(
                manifest[
                    "valid_pixel_pct"
                ].max()
            ),
            2,
        ),
    }

    return (
        manifest,
        karo_geometrileri,
        ozet,
    )


# ==========================================================
# ÇIKTILARI KAYDETME
# ==========================================================

def ciktilari_kaydet(
    manifest: pd.DataFrame,
    karo_geometrileri: gpd.GeoDataFrame,
    ilce_adi: str,
    ilce_slug: str,
    karo_boyutu: int,
    adim: int,
    min_gecerli_oran: float,
    ozet: dict[str, Any],
    yollar: dict[str, Path],
) -> None:
    """
    Segmentasyon karo manifestini, coğrafi sınırları
    ve işlem ayarlarını kaydeder.
    """

    yollar[
        "segmentasyon_klasoru"
    ].mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest.to_csv(
        yollar[
            "manifest_csv"
        ],
        index=False,
        encoding="utf-8-sig",
    )

    yollar[
        "karo_geojson"
    ].write_text(
        karo_geometrileri.to_json(
            ensure_ascii=False
        ),
        encoding="utf-8",
    )

    ayarlar = {
        "project": (
            "UrbanAI 3D İstanbul"
        ),

        "district_name": ilce_adi,

        "district_slug": ilce_slug,

        "tile_size_pixels": (
            karo_boyutu
        ),

        "stride_pixels": (
            adim
        ),

        "tile_overlap_pixels": (
            karo_boyutu
            - adim
        ),

        "minimum_valid_pixel_pct": (
            min_gecerli_oran
        ),

        "summary": ozet,

        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "purpose": (
            "Bu karolar İstanbul uydu mozaiğinde "
            "eğitilmiş veya önceden eğitilmiş bir "
            "semantik segmentasyon modelinin çıkarım "
            "yapması için hazırlanmıştır."
        ),

        "training_warning": (
            "Bu karolar etiketli eğitim verisi değildir. "
            "Birbirleriyle örtüştükleri için bağımsız "
            "eğitim ve doğrulama örnekleri olarak "
            "ayrılmamalıdır."
        ),
    }

    yollar[
        "ayarlar_json"
    ].write_text(
        json.dumps(
            ayarlar,
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
    manifest: pd.DataFrame,
    ozet: dict[str, Any],
    galeri_yolu: Path,
) -> None:
    """
    Segmentasyon girdilerini karşılaştırmalı
    HTML sayfasında gösterir.
    """

    galeri_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    kartlar = []

    for kayit in manifest.itertuples():

        kartlar.append(
            f"""
            <article class="tile-card">
                <img
                    src="{html.escape(kayit.png_relative_path)}"
                    alt="{html.escape(kayit.tile_id)} segmentasyon girdisi"
                >

                <div class="tile-body">
                    <h2>
                        {html.escape(kayit.tile_id)}
                    </h2>

                    <dl>
                        <div>
                            <dt>Konum</dt>
                            <dd>
                                Satır {kayit.tile_row},
                                sütun {kayit.tile_column}
                            </dd>
                        </div>

                        <div>
                            <dt>Boyut</dt>
                            <dd>
                                {kayit.width_pixels}
                                ×
                                {kayit.height_pixels}
                            </dd>
                        </div>

                        <div>
                            <dt>Geçerli piksel</dt>
                            <dd>
                                %{kayit.valid_pixel_pct:.2f}
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
        {html.escape(ilce_adi)} Segmentasyon Girdileri
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
            max-width: 1250px;
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
                repeat(auto-fit, minmax(175px, 1fr));
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

        .notice {{
            margin-bottom: 24px;
            padding: 16px 18px;
            border-left: 4px solid #d97706;
            border-radius: 8px;
            background: #fffbeb;
            line-height: 1.6;
        }}

        .grid {{
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(240px, 1fr));
            gap: 18px;
        }}

        .tile-card {{
            overflow: hidden;
            border: 1px solid #dce3eb;
            border-radius: 14px;
            background: #ffffff;
        }}

        .tile-card img {{
            display: block;
            width: 100%;
            aspect-ratio: 1 / 1;
            object-fit: cover;
            background: #111827;
            image-rendering: auto;
        }}

        .tile-body {{
            padding: 15px;
        }}

        h2 {{
            margin: 0 0 13px;
            font-size: 17px;
        }}

        dl {{
            display: grid;
            gap: 8px;
            margin: 0;
        }}

        dl div {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding-top: 8px;
            border-top: 1px solid #edf1f5;
        }}

        dt {{
            color: #667085;
            font-size: 12px;
        }}

        dd {{
            margin: 0;
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
                Segmentasyon Girdileri
            </h1>

            <p class="subtitle">
                Sentinel-2 RGB mozaiği, semantik
                segmentasyon modelinin çıkarım aşamasında
                kullanılması için sabit boyutlu ve coğrafi
                bilgili karolara ayrılmıştır.
            </p>
        </div>
    </header>

    <main class="container">

        <section class="metrics">
            <div class="metric">
                <div class="metric-label">
                    Aday karo
                </div>

                <div class="metric-value">
                    {ozet["total_candidate_tile_count"]}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Kaydedilen karo
                </div>

                <div class="metric-value">
                    {ozet["saved_tile_count"]}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Atlanan karo
                </div>

                <div class="metric-value">
                    {ozet["skipped_tile_count"]}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    Ortalama geçerli piksel
                </div>

                <div class="metric-value">
                    %{ozet["average_valid_pixel_pct"]:.2f}
                </div>
            </div>
        </section>

        <section class="notice">
            Bu karolar İstanbul için hazırlanmış model
            girdileridir; henüz sınıf etiketi içermez.
            Örtüşen karoların farklı eğitim ve doğrulama
            gruplarına konulması veri sızıntısına yol açar.
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
    karo_boyutu: int,
    adim: int,
    min_gecerli_oran: float,
    ozet: dict[str, Any],
    yollar: dict[str, Path],
) -> None:
    """
    Segmentasyon girdi hazırlama sonuçlarını
    terminalde gösterir.
    """

    print()
    print("=" * 95)
    print("SEGMENTASYON GİRDİ KAROLARI HAZIRLANDI")
    print("=" * 95)

    print()
    print(
        "İlçe:",
        ilce_adi,
    )

    print(
        "Karo boyutu:",
        f"{karo_boyutu} x "
        f"{karo_boyutu} piksel",
    )

    print(
        "Adım:",
        f"{adim} piksel",
    )

    print(
        "Karolar arasındaki örtüşme:",
        f"{karo_boyutu - adim} piksel",
    )

    print(
        "En düşük geçerli piksel eşiği:",
        f"%{min_gecerli_oran}",
    )

    print()
    print(
        "Üretilmesi mümkün karo:",
        ozet[
            "total_candidate_tile_count"
        ],
    )

    print(
        "Kaydedilen karo:",
        ozet[
            "saved_tile_count"
        ],
    )

    print(
        "Atlanan karo:",
        ozet[
            "skipped_tile_count"
        ],
    )

    print(
        "Ortalama geçerli piksel oranı:",
        f"%{ozet['average_valid_pixel_pct']:.2f}",
    )

    print()
    print(
        "Karo manifesti:"
    )

    print(
        f"  {yollar['manifest_csv']}"
    )

    print()
    print(
        "Karo sınırları:"
    )

    print(
        f"  {yollar['karo_geojson']}"
    )

    print()
    print(
        "Segmentasyon girdi galerisi:"
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
    İlçenin RGB mozaiğini segmentasyon
    girdilerine dönüştürür.
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
        f"  Karo boyutu: "
        f"{argumanlar.karo_boyutu} piksel"
    )

    print(
        f"  Adım: "
        f"{argumanlar.adim} piksel"
    )

    print(
        f"  Minimum geçerli oran: "
        f"%{argumanlar.min_gecerli_oran}"
    )

    print()
    print(
        "RGB mozaik segmentasyon karolarına ayrılıyor..."
    )

    (
        manifest,
        karo_geometrileri,
        ozet,
    ) = segmentasyon_karolarini_olustur(
        yollar[
            "mozaik_geotiff"
        ],
        ilce_slug,
        argumanlar.karo_boyutu,
        argumanlar.adim,
        argumanlar.min_gecerli_oran,
        yollar,
    )

    print(
        "Segmentasyon girdi dosyaları kaydediliyor..."
    )

    ciktilari_kaydet(
        manifest,
        karo_geometrileri,
        ilce_adi,
        ilce_slug,
        argumanlar.karo_boyutu,
        argumanlar.adim,
        argumanlar.min_gecerli_oran,
        ozet,
        yollar,
    )

    print(
        "Segmentasyon girdi galerisi oluşturuluyor..."
    )

    galeri_html_olustur(
        ilce_adi,
        manifest,
        ozet,
        yollar[
            "galeri_html"
        ],
    )

    terminal_ozetini_yazdir(
        ilce_adi,
        argumanlar.karo_boyutu,
        argumanlar.adim,
        argumanlar.min_gecerli_oran,
        ozet,
        yollar,
    )


if __name__ == "__main__":
    main()