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
import rasterio

from PIL import Image


# ==========================================================
# PROJE KÖKÜ
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]


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
    Geçerlilik maskeleri hazırlanacak ilçeyi
    komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Segmentasyon karolarındaki gerçek uydu verisi "
            "ve veri bulunmayan pikseller için geçerlilik "
            "maskeleri oluşturur."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help=(
            "Geçerlilik maskesi hazırlanacak ilçe. "
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
# DOSYA YOLLARI
# ==========================================================

def dosya_yollarini_olustur(
    ilce_slug: str,
) -> dict[str, Path]:
    """
    İlçeye özel girdi ve çıktı yollarını oluşturur.
    """

    segmentasyon_klasoru = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
        / "segmentation_input"
    )

    maske_ana_klasoru = (
        segmentasyon_klasoru
        / "validity_masks"
    )

    frontend_maske_klasoru = (
        PROJE_KOKU
        / "frontend"
        / "assets"
        / "sentinel2"
        / ilce_slug
        / "validity_masks"
    )

    return {
        "segmentasyon_klasoru": (
            segmentasyon_klasoru
        ),

        "manifest_csv": (
            segmentasyon_klasoru
            / "segmentasyon_karo_manifest.csv"
        ),

        "standart_geotiff_klasoru": (
            segmentasyon_klasoru
            / "geotiff"
        ),

        "maske_ana_klasoru": (
            maske_ana_klasoru
        ),

        "maske_geotiff_klasoru": (
            maske_ana_klasoru
            / "geotiff"
        ),

        "maske_png_klasoru": (
            frontend_maske_klasoru
        ),

        "ozet_json": (
            maske_ana_klasoru
            / "gecerlilik_maskesi_ozeti.json"
        ),

        "galeri_html": (
            PROJE_KOKU
            / "frontend"
            / f"{ilce_slug}_segmentasyon_gecerlilik_maskeleri.html"
        ),
    }


# ==========================================================
# MANİFEST DOSYASINI OKUMA
# ==========================================================

def manifesti_oku(
    manifest_yolu: Path,
    beklenen_ilce_slug: str,
) -> pd.DataFrame:
    """
    Segmentasyon karo manifestini okur ve
    seçilen ilçeye ait olduğunu doğrular.
    """

    if not manifest_yolu.exists():
        raise FileNotFoundError(
            "Segmentasyon karo manifesti bulunamadı:\n"
            f"{manifest_yolu}\n\n"
            "Önce segmentasyon_girdisi_hazirlama.py "
            "dosyasını bu ilçe için çalıştır."
        )

    manifest = pd.read_csv(
        manifest_yolu
    )

    gerekli_sutunlar = [
        "tile_id",
        "district_slug",
        "valid_pixel_pct",
        "geotiff_path",
        "png_relative_path",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in manifest.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Segmentasyon manifestinde eksik sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    farkli_ilce_kayitlari = manifest[
        manifest[
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
            "Manifest dosyasında farklı ilçeye ait "
            "segmentasyon karoları bulundu."
        )

    manifest[
        "valid_pixel_pct"
    ] = pd.to_numeric(
        manifest[
            "valid_pixel_pct"
        ],
        errors="coerce",
    )

    manifest = manifest.dropna(
        subset=[
            "tile_id",
        ]
    ).copy()

    manifest = manifest.sort_values(
        by=[
            "tile_row",
            "tile_column",
        ],
        ascending=True,
    ).reset_index(
        drop=True
    )

    if manifest.empty:
        raise ValueError(
            "Manifest dosyasında geçerli karo bulunamadı."
        )

    return manifest


# ==========================================================
# KARO GEOTIFF YOLUNU BULMA
# ==========================================================

def karo_geotiff_yolunu_bul(
    kayit: pd.Series,
    standart_geotiff_klasoru: Path,
) -> Path:
    """
    Önce proje içindeki standart yolu kontrol eder.

    Manifest içindeki mutlak yol farklı bir
    bilgisayara taşındığında bozulabileceği için
    standart proje yolu önceliklidir.
    """

    tile_id = str(
        kayit[
            "tile_id"
        ]
    )

    standart_yol = (
        standart_geotiff_klasoru
        / f"{tile_id}.tif"
    )

    if standart_yol.exists():
        return standart_yol

    manifest_yolu = Path(
        str(
            kayit[
                "geotiff_path"
            ]
        )
    )

    if manifest_yolu.exists():
        return manifest_yolu

    raise FileNotFoundError(
        "Segmentasyon karo GeoTIFF dosyası bulunamadı:\n"
        f"{standart_yol}"
    )


# ==========================================================
# GEÇERLİLİK MASKESİ HESAPLAMA
# ==========================================================

def gecerlilik_maskesi_hesapla(
    rgb_verisi: np.ndarray,
) -> np.ndarray:
    """
    RGB bantlarından geçerlilik maskesi oluşturur.

    En az bir bantta sıfırdan büyük değer varsa
    piksel geçerli kabul edilir.

    Çıktı:
    1 = Gerçek uydu verisi var
    0 = Veri yok
    """

    if rgb_verisi.ndim != 3:
        raise ValueError(
            "RGB raster verisi üç boyutlu değil."
        )

    return np.any(
        rgb_verisi > 0,
        axis=0,
    ).astype(
        np.uint8
    )


# ==========================================================
# MASKE GEOTIFF KAYDETME
# ==========================================================

def maske_geotiff_kaydet(
    cikti_yolu: Path,
    maske: np.ndarray,
    profil: dict[str, Any],
) -> None:
    """
    Geçerlilik maskesini coğrafi GeoTIFF olarak kaydeder.

    Değerler:
    1 = geçerli
    0 = geçersiz
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    maske_profili = profil.copy()

    maske_profili.update(
        {
            "driver": "GTiff",
            "height": maske.shape[0],
            "width": maske.shape[1],
            "count": 1,
            "dtype": "uint8",
            "nodata": 0,
            "compress": "deflate",
        }
    )

    with rasterio.open(
        cikti_yolu,
        "w",
        **maske_profili,
    ) as hedef:

        hedef.write(
            maske,
            1,
        )

        hedef.set_band_description(
            1,
            "valid_data_mask",
        )


# ==========================================================
# MASKE PNG KAYDETME
# ==========================================================

def maske_png_kaydet(
    cikti_yolu: Path,
    maske: np.ndarray,
) -> None:
    """
    Maskeyi görsel kontrol için siyah-beyaz PNG
    biçiminde kaydeder.

    Beyaz = gerçek veri
    Siyah = veri yok
    """

    cikti_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    maske_png = (
        maske
        * 255
    ).astype(
        np.uint8
    )

    Image.fromarray(
        maske_png
    ).save(
        cikti_yolu,
        format="PNG",
        optimize=True,
    )


# ==========================================================
# BÜTÜN MASKELERİ OLUŞTURMA
# ==========================================================

def maskeleri_olustur(
    manifest: pd.DataFrame,
    ilce_slug: str,
    yollar: dict[str, Path],
) -> tuple[
    pd.DataFrame,
    dict[str, Any],
]:
    """
    Bütün segmentasyon karoları için
    geçerlilik maskesi oluşturur.
    """

    guncel_manifest = (
        manifest.copy()
    )

    maske_sonuclari: list[
        dict[str, Any]
    ] = []

    for index, kayit in (
        guncel_manifest.iterrows()
    ):

        tile_id = str(
            kayit[
                "tile_id"
            ]
        )

        geotiff_yolu = (
            karo_geotiff_yolunu_bul(
                kayit,
                yollar[
                    "standart_geotiff_klasoru"
                ],
            )
        )

        with rasterio.open(
            geotiff_yolu
        ) as kaynak:

            if kaynak.count != 3:
                raise ValueError(
                    f"{tile_id} üç bantlı RGB karo değil."
                )

            if kaynak.crs is None:
                raise ValueError(
                    f"{tile_id} için koordinat sistemi bulunamadı."
                )

            rgb_verisi = kaynak.read()

            maske = gecerlilik_maskesi_hesapla(
                rgb_verisi
            )

            raster_profili = (
                kaynak.profile.copy()
            )

        toplam_piksel = int(
            maske.size
        )

        gecerli_piksel = int(
            maske.sum()
        )

        gecersiz_piksel = (
            toplam_piksel
            - gecerli_piksel
        )

        gecerli_oran = (
            gecerli_piksel
            / toplam_piksel
            * 100
            if toplam_piksel > 0
            else 0.0
        )

        gecersiz_oran = (
            gecersiz_piksel
            / toplam_piksel
            * 100
            if toplam_piksel > 0
            else 0.0
        )

        manifest_gecerli_oran = (
            float(
                kayit[
                    "valid_pixel_pct"
                ]
            )
            if pd.notna(
                kayit[
                    "valid_pixel_pct"
                ]
            )
            else None
        )

        if manifest_gecerli_oran is None:
            oran_farki = None
        else:
            oran_farki = abs(
                gecerli_oran
                - manifest_gecerli_oran
            )

        maske_geotiff_yolu = (
            yollar[
                "maske_geotiff_klasoru"
            ]
            / f"{tile_id}_valid_mask.tif"
        )

        maske_png_yolu = (
            yollar[
                "maske_png_klasoru"
            ]
            / f"{tile_id}_valid_mask.png"
        )

        maske_png_relative_path = (
            f"assets/sentinel2/"
            f"{ilce_slug}/"
            f"validity_masks/"
            f"{tile_id}_valid_mask.png"
        )

        maske_geotiff_kaydet(
            maske_geotiff_yolu,
            maske,
            raster_profili,
        )

        maske_png_kaydet(
            maske_png_yolu,
            maske,
        )

        guncel_manifest.loc[
            index,
            "valid_mask_geotiff_path",
        ] = str(
            maske_geotiff_yolu
        )

        guncel_manifest.loc[
            index,
            "valid_mask_png_path",
        ] = str(
            maske_png_yolu
        )

        guncel_manifest.loc[
            index,
            "valid_mask_png_relative_path",
        ] = (
            maske_png_relative_path
        )

        guncel_manifest.loc[
            index,
            "valid_mask_pixel_pct",
        ] = round(
            gecerli_oran,
            2,
        )

        guncel_manifest.loc[
            index,
            "invalid_mask_pixel_pct",
        ] = round(
            gecersiz_oran,
            2,
        )

        maske_sonuclari.append(
            {
                "tile_id": tile_id,

                "total_pixel_count": (
                    toplam_piksel
                ),

                "valid_pixel_count": (
                    gecerli_piksel
                ),

                "invalid_pixel_count": (
                    gecersiz_piksel
                ),

                "valid_pixel_pct": round(
                    gecerli_oran,
                    2,
                ),

                "invalid_pixel_pct": round(
                    gecersiz_oran,
                    2,
                ),

                "manifest_valid_pixel_pct": (
                    manifest_gecerli_oran
                ),

                "valid_percentage_difference": (
                    None
                    if oran_farki is None
                    else round(
                        oran_farki,
                        4,
                    )
                ),

                "mask_geotiff_path": str(
                    maske_geotiff_yolu
                ),

                "mask_png_path": str(
                    maske_png_yolu
                ),

                "mask_png_relative_path": (
                    maske_png_relative_path
                ),
            }
        )

    sonuc_dataframe = pd.DataFrame(
        maske_sonuclari
    )

    ozet = {
        "tile_count": len(
            sonuc_dataframe
        ),

        "average_valid_pixel_pct": round(
            float(
                sonuc_dataframe[
                    "valid_pixel_pct"
                ].mean()
            ),
            2,
        ),

        "minimum_valid_pixel_pct": round(
            float(
                sonuc_dataframe[
                    "valid_pixel_pct"
                ].min()
            ),
            2,
        ),

        "maximum_valid_pixel_pct": round(
            float(
                sonuc_dataframe[
                    "valid_pixel_pct"
                ].max()
            ),
            2,
        ),

        "total_valid_pixel_count": int(
            sonuc_dataframe[
                "valid_pixel_count"
            ].sum()
        ),

        "total_invalid_pixel_count": int(
            sonuc_dataframe[
                "invalid_pixel_count"
            ].sum()
        ),
    }

    return (
        guncel_manifest,
        ozet,
    )


# ==========================================================
# ÇIKTILARI KAYDETME
# ==========================================================

def ciktilari_kaydet(
    guncel_manifest: pd.DataFrame,
    ozet: dict[str, Any],
    ilce_adi: str,
    ilce_slug: str,
    yollar: dict[str, Path],
) -> None:
    """
    Güncellenmiş manifesti ve maske özetini kaydeder.
    """

    yollar[
        "maske_ana_klasoru"
    ].mkdir(
        parents=True,
        exist_ok=True,
    )

    guncel_manifest.to_csv(
        yollar[
            "manifest_csv"
        ],
        index=False,
        encoding="utf-8-sig",
    )

    ozet_json = {
        "project": (
            "UrbanAI 3D İstanbul"
        ),

        "district_name": (
            ilce_adi
        ),

        "district_slug": (
            ilce_slug
        ),

        "mask_values": {
            "0": (
                "Veri bulunmayan piksel"
            ),

            "1": (
                "Geçerli Sentinel-2 pikseli"
            ),
        },

        "summary": ozet,

        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "machine_learning_usage": (
            "Model tahmini yalnızca maske değeri 1 olan "
            "piksellerde kullanılmalıdır. Maske değeri 0 "
            "olan pikseller sonuç rasterında nodata veya "
            "ignore_index olarak işaretlenmelidir."
        ),

        "warning": (
            "Siyah alanlar gerçek bir arazi sınıfı değildir. "
            "Mozaik sınır kutusunda uydu yaması bulunmayan "
            "bölgelerdir."
        ),
    }

    yollar[
        "ozet_json"
    ].write_text(
        json.dumps(
            ozet_json,
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8",
    )


# ==========================================================
# KARŞILAŞTIRMA GALERİSİ
# ==========================================================

def galeri_html_olustur(
    ilce_adi: str,
    manifest: pd.DataFrame,
    ozet: dict[str, Any],
    galeri_yolu: Path,
) -> None:
    """
    RGB karo ve geçerlilik maskesini
    yan yana gösteren HTML sayfası oluşturur.
    """

    galeri_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    kartlar: list[str] = []

    for kayit in manifest.itertuples():

        tile_id = html.escape(
            str(
                kayit.tile_id
            )
        )

        rgb_yolu = html.escape(
            str(
                kayit.png_relative_path
            )
        )

        maske_yolu = html.escape(
            str(
                kayit.valid_mask_png_relative_path
            )
        )

        kartlar.append(
            f"""
            <article class="tile-card">
                <h2>{tile_id}</h2>

                <div class="image-grid">
                    <div>
                        <div class="image-label">
                            RGB uydu karosu
                        </div>

                        <img
                            src="{rgb_yolu}"
                            alt="{tile_id} RGB uydu karosu"
                        >
                    </div>

                    <div>
                        <div class="image-label">
                            Geçerlilik maskesi
                        </div>

                        <img
                            src="{maske_yolu}"
                            alt="{tile_id} geçerlilik maskesi"
                        >
                    </div>
                </div>

                <div class="stats">
                    <span>
                        Geçerli:
                        %{float(kayit.valid_mask_pixel_pct):.2f}
                    </span>

                    <span>
                        Veri yok:
                        %{float(kayit.invalid_mask_pixel_pct):.2f}
                    </span>
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
        {html.escape(ilce_adi)} Geçerlilik Maskeleri
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

        .notice {{
            margin-bottom: 24px;
            padding: 16px 18px;
            border-left: 4px solid #2563eb;
            border-radius: 8px;
            background: #eff6ff;
            line-height: 1.6;
        }}

        .grid {{
            display: grid;
            grid-template-columns:
                repeat(auto-fit, minmax(430px, 1fr));
            gap: 20px;
        }}

        .tile-card {{
            padding: 17px;
            border: 1px solid #dce3eb;
            border-radius: 14px;
            background: #ffffff;
        }}

        .tile-card h2 {{
            margin: 0 0 14px;
            font-size: 17px;
        }}

        .image-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }}

        .image-label {{
            margin-bottom: 7px;
            color: #667085;
            font-size: 12px;
        }}

        .image-grid img {{
            display: block;
            width: 100%;
            aspect-ratio: 1 / 1;
            object-fit: cover;
            border-radius: 9px;
            background: #000000;
        }}

        .stats {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            margin-top: 13px;
            padding-top: 12px;
            border-top: 1px solid #edf1f5;
            font-size: 13px;
            font-weight: 700;
        }}

        @media (max-width: 600px) {{
            .grid {{
                grid-template-columns: 1fr;
            }}

            .image-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>

<body>
    <header>
        <div class="container">
            <h1>
                {html.escape(ilce_adi)}
                Segmentasyon Geçerlilik Maskeleri
            </h1>

            <p class="subtitle">
                Siyah mozaik boşluklarının gerçek bir arazi
                sınıfı olarak değerlendirilmesini önlemek
                için her segmentasyon karosuna geçerlilik
                maskesi eklenmiştir.
            </p>
        </div>
    </header>

    <main class="container">

        <section class="metrics">
            <div class="metric">
                <div class="metric-label">
                    Karo sayısı
                </div>

                <div class="metric-value">
                    {ozet["tile_count"]}
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

            <div class="metric">
                <div class="metric-label">
                    En düşük geçerli piksel
                </div>

                <div class="metric-value">
                    %{ozet["minimum_valid_pixel_pct"]:.2f}
                </div>
            </div>

            <div class="metric">
                <div class="metric-label">
                    En yüksek geçerli piksel
                </div>

                <div class="metric-value">
                    %{ozet["maximum_valid_pixel_pct"]:.2f}
                </div>
            </div>
        </section>

        <section class="notice">
            <strong>Beyaz alan:</strong>
            Model tahmini yapılabilecek gerçek Sentinel-2
            pikselleridir.

            <br>

            <strong>Siyah alan:</strong>
            Uydu verisi bulunmayan mozaik boşluklarıdır.
            Model sonucu bu alanlarda dikkate alınmayacaktır.
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
    ozet: dict[str, Any],
    yollar: dict[str, Path],
) -> None:
    """
    Maske oluşturma sonuçlarını terminalde gösterir.
    """

    print()
    print("=" * 95)
    print("SEGMENTASYON GEÇERLİLİK MASKELERİ HAZIRLANDI")
    print("=" * 95)

    print()
    print(
        "İlçe:",
        ilce_adi,
    )

    print(
        "Maske oluşturulan karo:",
        ozet[
            "tile_count"
        ],
    )

    print(
        "Ortalama geçerli piksel oranı:",
        f"%{ozet['average_valid_pixel_pct']:.2f}",
    )

    print(
        "En düşük geçerli piksel oranı:",
        f"%{ozet['minimum_valid_pixel_pct']:.2f}",
    )

    print(
        "En yüksek geçerli piksel oranı:",
        f"%{ozet['maximum_valid_pixel_pct']:.2f}",
    )

    print(
        "Toplam geçerli piksel:",
        ozet[
            "total_valid_pixel_count"
        ],
    )

    print(
        "Toplam veri bulunmayan piksel:",
        ozet[
            "total_invalid_pixel_count"
        ],
    )

    print()
    print(
        "Güncellenmiş karo manifesti:"
    )

    print(
        f"  {yollar['manifest_csv']}"
    )

    print()
    print(
        "Geçerlilik maskesi özet dosyası:"
    )

    print(
        f"  {yollar['ozet_json']}"
    )

    print()
    print(
        "Maske karşılaştırma galerisi:"
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
    Segmentasyon karoları için geçerlilik
    maskelerini oluşturur.
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
        "Segmentasyon karo manifesti okunuyor..."
    )

    manifest = manifesti_oku(
        yollar[
            "manifest_csv"
        ],
        ilce_slug,
    )

    print(
        "Segmentasyon karoları için "
        "geçerlilik maskeleri oluşturuluyor..."
    )

    (
        guncel_manifest,
        ozet,
    ) = maskeleri_olustur(
        manifest,
        ilce_slug,
        yollar,
    )

    print(
        "Maske sonuçları kaydediliyor..."
    )

    ciktilari_kaydet(
        guncel_manifest,
        ozet,
        ilce_adi,
        ilce_slug,
        yollar,
    )

    print(
        "Maske karşılaştırma galerisi oluşturuluyor..."
    )

    galeri_html_olustur(
        ilce_adi,
        guncel_manifest,
        ozet,
        yollar[
            "galeri_html"
        ],
    )

    terminal_ozetini_yazdir(
        ilce_adi,
        ozet,
        yollar,
    )


if __name__ == "__main__":
    main()