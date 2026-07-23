from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely import union_all
from shapely.geometry import box


# ==========================================================
# PROJE VE KOORDİNAT AYARLARI
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

HUCRE_GEOJSON_YOLU = (
    PROJE_KOKU
    / "data"
    / "processed"
    / "hizmet_boslugu_hucreleri.geojson"
)

ADAY_SIRALAMA_CSV_YOLU = (
    PROJE_KOKU
    / "data"
    / "processed"
    / "aday_hucre_on_siralama.csv"
)

COGRAFI_CRS = "EPSG:4326"
METRIK_CRS = "EPSG:32635"


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


def slug_olustur(
    metin: str,
) -> str:
    """
    İlçe adını güvenli dosya ve klasör adına dönüştürür.
    """

    temiz = (
        metin
        .translate(
            TURKCE_KARAKTER_TABLOSU
        )
        .lower()
        .strip()
    )

    temiz = unicodedata.normalize(
        "NFKD",
        temiz,
    )

    temiz = "".join(
        karakter
        for karakter in temiz
        if not unicodedata.combining(
            karakter
        )
    )

    temiz = re.sub(
        r"[^a-z0-9]+",
        "_",
        temiz,
    ).strip("_")

    if not temiz:
        raise ValueError(
            "İlçe adından güvenli klasör adı oluşturulamadı."
        )

    return temiz


# ==========================================================
# KOMUT SATIRI ARGÜMANLARI
# ==========================================================

def argumanlari_oku() -> argparse.Namespace:
    """
    İlçe, aday kaynağı, aday sayısı ve yama boyutunu okur.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Seçilen ilçe için uydu görüntüsü "
            "pilot analiz alanlarını hazırlar."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help="Analiz edilecek ilçe. Örnek: Pendik",
    )

    parser.add_argument(
        "--aday-kaynagi",
        choices=[
            "on_siralama",
            "worldcover",
        ],
        default="on_siralama",
        help=(
            "Aday kaynağı: on_siralama veya worldcover. "
            "Varsayılan: on_siralama"
        ),
    )

    parser.add_argument(
        "--worldcover-yili",
        type=int,
        choices=[
            2020,
            2021,
        ],
        default=2021,
        help="WorldCover ön eleme yılı. Varsayılan: 2021",
    )

    parser.add_argument(
        "--aday-sayisi",
        type=int,
        default=5,
        help="Seçilecek aday sayısı. Varsayılan: 5",
    )

    parser.add_argument(
        "--yama-boyutu",
        type=int,
        default=1500,
        help=(
            "Uydu yaması kenar uzunluğu, metre. "
            "Varsayılan: 1500"
        ),
    )

    args = parser.parse_args()

    args.ilce = args.ilce.strip()

    if not args.ilce:
        parser.error(
            "--ilce değeri boş bırakılamaz."
        )

    if args.aday_sayisi <= 0:
        parser.error(
            "--aday-sayisi sıfırdan büyük olmalıdır."
        )

    if args.yama_boyutu <= 0:
        parser.error(
            "--yama-boyutu sıfırdan büyük olmalıdır."
        )

    return args


# ==========================================================
# DOSYA YOLLARI
# ==========================================================

def dosya_yollarini_olustur(
    ilce_slug: str,
    worldcover_yili: int,
) -> dict[str, Path]:
    """
    İlçeye ait girdi ve çıktı dosyalarının yollarını oluşturur.
    """

    islenmis_klasor = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
    )

    return {
        "islenmis": (
            islenmis_klasor
        ),

        "worldcover_aday": (
            islenmis_klasor
            / f"worldcover_{worldcover_yili}"
            / "candidate_screening"
            / "worldcover_yeni_ilk_adaylar.geojson"
        ),

        "pilot_aday": (
            islenmis_klasor
            / "pilot_aday_hucreleri.geojson"
        ),

        "uydu_yamalari": (
            islenmis_klasor
            / "pilot_uydu_yamalari.geojson"
        ),

        "uydu_bbox": (
            islenmis_klasor
            / "pilot_uydu_bbox.csv"
        ),

        "birlesik_alan": (
            islenmis_klasor
            / "pilot_birlesik_alan.geojson"
        ),

        "ayarlar": (
            islenmis_klasor
            / "pilot_ayarlar.json"
        ),
    }


# ==========================================================
# YARDIMCI FONKSİYONLAR
# ==========================================================

def sayisal_sutun_hazirla(
    dataframe: pd.DataFrame,
    sutun: str,
    varsayilan: float,
) -> None:
    """
    Sütunu sayısal biçime dönüştürür.
    """

    if sutun not in dataframe.columns:
        dataframe[
            sutun
        ] = varsayilan

    dataframe[
        sutun
    ] = pd.to_numeric(
        dataframe[
            sutun
        ],
        errors="coerce",
    ).fillna(
        varsayilan
    )


def metin_sutunu_hazirla(
    dataframe: pd.DataFrame,
    sutun: str,
    varsayilan: str,
) -> None:
    """
    Sütunu metin biçimine dönüştürür.
    """

    if sutun not in dataframe.columns:
        dataframe[
            sutun
        ] = varsayilan

    dataframe[
        sutun
    ] = (
        dataframe[
            sutun
        ]
        .fillna(
            varsayilan
        )
        .astype(str)
    )


def geojson_kaydet(
    dataframe: gpd.GeoDataFrame,
    dosya_yolu: Path,
) -> None:
    """
    GeoDataFrame verisini UTF-8 GeoJSON olarak kaydeder.
    """

    dosya_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    dosya_yolu.write_text(
        dataframe.to_json(
            ensure_ascii=False,
            drop_id=True,
        ),
        encoding="utf-8",
    )


def goreli_yol(
    dosya_yolu: Path,
) -> str:
    """
    Dosya yolunu proje köküne göre göreli hale getirir.
    """

    try:
        return (
            dosya_yolu
            .resolve()
            .relative_to(
                PROJE_KOKU.resolve()
            )
            .as_posix()
        )

    except ValueError:
        return dosya_yolu.as_posix()


# ==========================================================
# ANA HİZMET HÜCRELERİNİ OKUMA
# ==========================================================

def ana_hucreleri_oku() -> gpd.GeoDataFrame:
    """
    Bütün hizmet boşluğu hücrelerini okur.
    """

    if not HUCRE_GEOJSON_YOLU.exists():
        raise FileNotFoundError(
            "Hizmet hücre dosyası bulunamadı:\n"
            f"{HUCRE_GEOJSON_YOLU}"
        )

    hucreler = gpd.read_file(
        HUCRE_GEOJSON_YOLU
    )

    gerekli_sutunlar = [
        "cell_id",
        "district_name",
        "nearest_library_name",
        "nearest_library_distance_km",
        "geometry",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in hucreler.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Hizmet hücre dosyasında eksik sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    if hucreler.crs is None:
        hucreler = hucreler.set_crs(
            COGRAFI_CRS
        )

    hucreler[
        "cell_id"
    ] = hucreler[
        "cell_id"
    ].astype(str)

    hucreler[
        "_district_slug"
    ] = (
        hucreler[
            "district_name"
        ]
        .astype(str)
        .map(
            slug_olustur
        )
    )

    return gpd.GeoDataFrame(
        hucreler,
        geometry="geometry",
        crs=hucreler.crs,
    )


# ==========================================================
# ESKİ ÖN SIRALAMA KAYNAĞI
# ==========================================================

def on_siralamadan_aday_sec(
    ilce_adi: str,
    aday_sayisi: int,
) -> tuple[
    gpd.GeoDataFrame,
    Path,
]:
    """
    Mevcut ön ihtiyaç sıralamasından aday seçer.
    """

    if not ADAY_SIRALAMA_CSV_YOLU.exists():
        raise FileNotFoundError(
            "Aday sıralama dosyası bulunamadı:\n"
            f"{ADAY_SIRALAMA_CSV_YOLU}"
        )

    hedef_slug = slug_olustur(
        ilce_adi
    )

    hucreler = ana_hucreleri_oku()

    siralama = pd.read_csv(
        ADAY_SIRALAMA_CSV_YOLU,
        encoding="utf-8-sig",
    )

    gerekli_sutunlar = [
        "cell_id",
        "district_name",
        "district_candidate_rank",
        "global_candidate_rank",
        "global_preliminary_score",
        "preliminary_need_score",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in siralama.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Aday sıralama dosyasında eksik sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    siralama[
        "cell_id"
    ] = siralama[
        "cell_id"
    ].astype(str)

    siralama[
        "_district_slug"
    ] = (
        siralama[
            "district_name"
        ]
        .astype(str)
        .map(
            slug_olustur
        )
    )

    sayisal_sutun_hazirla(
        siralama,
        "district_candidate_rank",
        999999,
    )

    ilce_siralamasi = (
        siralama[
            siralama[
                "_district_slug"
            ]
            == hedef_slug
        ]
        .sort_values(
            "district_candidate_rank"
        )
        .head(
            aday_sayisi
        )
        .copy()
    )

    if ilce_siralamasi.empty:
        raise ValueError(
            f"{ilce_adi} için aday bulunamadı."
        )

    aktarilacak_sutunlar = [
        "cell_id",
        "global_candidate_rank",
        "district_candidate_rank",
        "global_preliminary_score",
        "preliminary_need_score",
    ]

    for istege_bagli_sutun in [
        "global_distance_score",
        "district_distance_score",
    ]:
        if istege_bagli_sutun in ilce_siralamasi.columns:
            aktarilacak_sutunlar.append(
                istege_bagli_sutun
            )

    secilen = hucreler.merge(
        ilce_siralamasi[
            aktarilacak_sutunlar
        ],
        on="cell_id",
        how="inner",
        validate="one_to_one",
    )

    secilen = secilen.drop(
        columns=[
            "_district_slug",
        ],
        errors="ignore",
    )

    secilen[
        "source_candidate_rank"
    ] = secilen[
        "district_candidate_rank"
    ]

    secilen[
        "original_district_candidate_rank"
    ] = secilen[
        "district_candidate_rank"
    ]

    secilen[
        "candidate_source"
    ] = "preliminary_ranking"

    return (
        gpd.GeoDataFrame(
            secilen,
            geometry="geometry",
            crs=hucreler.crs,
        ),
        ADAY_SIRALAMA_CSV_YOLU,
    )


# ==========================================================
# WORLDCOVER ÖN ELEME KAYNAĞI
# ==========================================================

def worldcover_adaylarini_sec(
    ilce_adi: str,
    aday_sayisi: int,
    worldcover_yili: int,
    kaynak_yolu: Path,
) -> tuple[
    gpd.GeoDataFrame,
    Path,
]:
    """
    WorldCover ön elemesinden seçilen adayları okur.
    """

    if not kaynak_yolu.exists():
        raise FileNotFoundError(
            "WorldCover aday dosyası bulunamadı:\n"
            f"{kaynak_yolu}\n\n"
            "Önce worldcover_aday_on_elemesi.py "
            "dosyasını çalıştır."
        )

    hedef_slug = slug_olustur(
        ilce_adi
    )

    adaylar = gpd.read_file(
        kaynak_yolu
    )

    if adaylar.crs is None:
        adaylar = adaylar.set_crs(
            COGRAFI_CRS
        )

    gerekli_sutunlar = [
        "cell_id",
        "district_name",
        "screened_candidate_rank",
        "nearest_library_name",
        "nearest_library_distance_km",
        "preliminary_need_score",
        "geometry",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in adaylar.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "WorldCover aday dosyasında eksik sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    adaylar[
        "cell_id"
    ] = adaylar[
        "cell_id"
    ].astype(str)

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

    sayisal_sutun_hazirla(
        adaylar,
        "screened_candidate_rank",
        999999,
    )

    adaylar = (
        adaylar[
            adaylar[
                "_district_slug"
            ]
            == hedef_slug
        ]
        .sort_values(
            "screened_candidate_rank"
        )
        .head(
            aday_sayisi
        )
        .copy()
    )

    if adaylar.empty:
        raise ValueError(
            f"{ilce_adi} için WorldCover "
            "ön eleme adayı bulunamadı."
        )

    if "district_candidate_rank" in adaylar.columns:
        adaylar[
            "original_district_candidate_rank"
        ] = pd.to_numeric(
            adaylar[
                "district_candidate_rank"
            ],
            errors="coerce",
        ).fillna(
            -1
        )

    else:
        adaylar[
            "original_district_candidate_rank"
        ] = -1

    adaylar[
        "source_candidate_rank"
    ] = adaylar[
        "screened_candidate_rank"
    ].astype(int)

    # Sonraki bütün işlemler yeni 1–N sırasını kullanır.
    adaylar[
        "district_candidate_rank"
    ] = np.arange(
        1,
        len(
            adaylar
        )
        + 1,
    )

    adaylar[
        "candidate_source"
    ] = "worldcover_screening"

    adaylar[
        "worldcover_year"
    ] = worldcover_yili

    adaylar = adaylar.drop(
        columns=[
            "_district_slug",
        ],
        errors="ignore",
    )

    return (
        gpd.GeoDataFrame(
            adaylar,
            geometry="geometry",
            crs=adaylar.crs,
        ),
        kaynak_yolu,
    )


# ==========================================================
# ADAY ŞEMASINI NORMALLEŞTİRME
# ==========================================================

def adaylari_normalize_et(
    adaylar: gpd.GeoDataFrame,
    ilce_adi: str,
) -> gpd.GeoDataFrame:
    """
    Farklı aday kaynaklarını ortak sütun yapısına getirir.
    """

    sonuc = adaylar.copy()

    metin_sutunu_hazirla(
        sonuc,
        "district_name",
        ilce_adi,
    )

    metin_sutunu_hazirla(
        sonuc,
        "nearest_library_name",
        "Bilinmiyor",
    )

    metin_sutunu_hazirla(
        sonuc,
        "candidate_source",
        "unknown",
    )

    varsayilanlar = {
        "district_candidate_rank": 999999,
        "source_candidate_rank": 999999,
        "original_district_candidate_rank": -1,
        "global_candidate_rank": -1,
        "nearest_library_distance_km": 0.0,
        "global_preliminary_score": 0.0,
        "preliminary_need_score": 0.0,
    }

    for sutun, varsayilan in varsayilanlar.items():
        sayisal_sutun_hazirla(
            sonuc,
            sutun,
            varsayilan,
        )

    for sutun in [
        "district_candidate_rank",
        "source_candidate_rank",
        "global_candidate_rank",
    ]:
        sonuc[
            sutun
        ] = sonuc[
            sutun
        ].astype(int)

    sonuc = (
        sonuc
        .sort_values(
            "district_candidate_rank"
        )
        .reset_index(
            drop=True
        )
    )

    if sonuc.empty:
        raise ValueError(
            "Pilot aday hücre bulunamadı."
        )

    return gpd.GeoDataFrame(
        sonuc,
        geometry="geometry",
        crs=adaylar.crs,
    )


# ==========================================================
# UYDU YAMALARINI OLUŞTURMA
# ==========================================================

def uydu_yamalarini_olustur(
    adaylar: gpd.GeoDataFrame,
    ilce_adi: str,
    ilce_slug: str,
    yama_boyutu: int,
) -> gpd.GeoDataFrame:
    """
    Her adayın çevresinde kare uydu sorgu alanı oluşturur.
    """

    adaylar_metrik = adaylar.to_crs(
        METRIK_CRS
    )

    yarim_yama = (
        yama_boyutu
        / 2
    )

    istege_bagli_sutunlar = [
        "original_district_candidate_rank",
        "screened_candidate_rank",
        "worldcover_year",
        "built_up_pct",
        "vegetation_pct",
        "open_bare_pct",
        "water_wetland_pct",
        "worldcover_coverage_pct",
        "landcover_screening_status",
        "urban_context_screening_pass",
        "landcover_screening_explanation",
    ]

    kayitlar: list[
        dict[str, Any]
    ] = []

    for _, aday in adaylar_metrik.iterrows():
        merkez = (
            aday.geometry
            .representative_point()
        )

        kayit: dict[str, Any] = {
            "patch_id": (
                f"{ilce_slug.upper()}_"
                f"{int(aday['district_candidate_rank']):02d}"
            ),

            "cell_id": str(
                aday[
                    "cell_id"
                ]
            ),

            "district_name": (
                ilce_adi
            ),

            "district_slug": (
                ilce_slug
            ),

            "district_candidate_rank": int(
                aday[
                    "district_candidate_rank"
                ]
            ),

            "source_candidate_rank": int(
                aday[
                    "source_candidate_rank"
                ]
            ),

            "candidate_source": str(
                aday[
                    "candidate_source"
                ]
            ),

            "global_candidate_rank": int(
                aday[
                    "global_candidate_rank"
                ]
            ),

            "nearest_library_name": str(
                aday[
                    "nearest_library_name"
                ]
            ),

            "nearest_library_distance_km": float(
                aday[
                    "nearest_library_distance_km"
                ]
            ),

            "global_preliminary_score": float(
                aday[
                    "global_preliminary_score"
                ]
            ),

            "preliminary_need_score": float(
                aday[
                    "preliminary_need_score"
                ]
            ),

            "patch_width_m": (
                yama_boyutu
            ),

            "patch_height_m": (
                yama_boyutu
            ),

            "geometry": box(
                merkez.x - yarim_yama,
                merkez.y - yarim_yama,
                merkez.x + yarim_yama,
                merkez.y + yarim_yama,
            ),
        }

        for sutun in istege_bagli_sutunlar:
            if sutun not in aday.index:
                continue

            if pd.isna(
                aday[
                    sutun
                ]
            ):
                continue

            deger = aday[
                sutun
            ]

            if isinstance(
                deger,
                np.integer,
            ):
                deger = int(
                    deger
                )

            elif isinstance(
                deger,
                np.floating,
            ):
                deger = float(
                    deger
                )

            elif isinstance(
                deger,
                np.bool_,
            ):
                deger = bool(
                    deger
                )

            kayit[
                sutun
            ] = deger

        kayitlar.append(
            kayit
        )

    yamalar = gpd.GeoDataFrame(
        kayitlar,
        geometry="geometry",
        crs=METRIK_CRS,
    )

    return yamalar.to_crs(
        COGRAFI_CRS
    )


# ==========================================================
# BBOX BİLGİLERİ
# ==========================================================

def bbox_bilgilerini_ekle(
    yamalar: gpd.GeoDataFrame,
) -> gpd.GeoDataFrame:
    """
    Uydu sorgu alanlarının sınır koordinatlarını hesaplar.
    """

    sonuc = yamalar.copy()

    sinirlar = sonuc.geometry.bounds

    sonuc[
        "min_longitude"
    ] = sinirlar[
        "minx"
    ].round(7)

    sonuc[
        "min_latitude"
    ] = sinirlar[
        "miny"
    ].round(7)

    sonuc[
        "max_longitude"
    ] = sinirlar[
        "maxx"
    ].round(7)

    sonuc[
        "max_latitude"
    ] = sinirlar[
        "maxy"
    ].round(7)

    return gpd.GeoDataFrame(
        sonuc,
        geometry="geometry",
        crs=yamalar.crs,
    )


# ==========================================================
# ÇIKTILARI KAYDETME
# ==========================================================

def ciktilari_kaydet(
    adaylar: gpd.GeoDataFrame,
    yamalar: gpd.GeoDataFrame,
    ilce_adi: str,
    ilce_slug: str,
    args: argparse.Namespace,
    kaynak_dosyasi: Path,
    yollar: dict[str, Path],
) -> None:
    """
    Pilot aday, uydu yaması, BBOX ve ayar dosyalarını kaydeder.
    """

    yollar[
        "islenmis"
    ].mkdir(
        parents=True,
        exist_ok=True,
    )

    geojson_kaydet(
        adaylar.to_crs(
            COGRAFI_CRS
        ),
        yollar[
            "pilot_aday"
        ],
    )

    geojson_kaydet(
        yamalar,
        yollar[
            "uydu_yamalari"
        ],
    )

    birlesik_alan = gpd.GeoDataFrame(
        [
            {
                "district_name": (
                    ilce_adi
                ),

                "district_slug": (
                    ilce_slug
                ),

                "candidate_source": (
                    args.aday_kaynagi
                ),

                "patch_count": len(
                    yamalar
                ),

                "patch_size_m": (
                    args.yama_boyutu
                ),

                "geometry": union_all(
                    list(
                        yamalar.geometry
                    )
                ),
            }
        ],
        geometry="geometry",
        crs=yamalar.crs,
    )

    geojson_kaydet(
        birlesik_alan,
        yollar[
            "birlesik_alan"
        ],
    )

    temel_sutunlar = [
        "patch_id",
        "cell_id",
        "district_name",
        "district_slug",
        "district_candidate_rank",
        "source_candidate_rank",
        "candidate_source",
        "global_candidate_rank",
        "nearest_library_name",
        "nearest_library_distance_km",
        "global_preliminary_score",
        "preliminary_need_score",
        "patch_width_m",
        "patch_height_m",
        "min_longitude",
        "min_latitude",
        "max_longitude",
        "max_latitude",
    ]

    istege_bagli_sutunlar = [
        "original_district_candidate_rank",
        "screened_candidate_rank",
        "worldcover_year",
        "built_up_pct",
        "vegetation_pct",
        "open_bare_pct",
        "water_wetland_pct",
        "worldcover_coverage_pct",
        "landcover_screening_status",
        "urban_context_screening_pass",
        "landcover_screening_explanation",
    ]

    bbox_sutunlari = (
        temel_sutunlar
        + [
            sutun
            for sutun in istege_bagli_sutunlar
            if sutun in yamalar.columns
        ]
    )

    yamalar[
        bbox_sutunlari
    ].to_csv(
        yollar[
            "uydu_bbox"
        ],
        index=False,
        encoding="utf-8-sig",
    )

    ayarlar = {
        "project": (
            "UrbanAI 3D İstanbul"
        ),

        "district_name": (
            ilce_adi
        ),

        "district_slug": (
            ilce_slug
        ),

        "candidate_source": (
            args.aday_kaynagi
        ),

        "worldcover_year": (
            args.worldcover_yili
            if args.aday_kaynagi == "worldcover"
            else None
        ),

        "requested_candidate_count": (
            args.aday_sayisi
        ),

        "created_candidate_count": len(
            adaylar
        ),

        "patch_size_m": (
            args.yama_boyutu
        ),

        "source_candidate_file": goreli_yol(
            kaynak_dosyasi
        ),

        "source_cell_file": goreli_yol(
            HUCRE_GEOJSON_YOLU
        ),

        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
    }

    yollar[
        "ayarlar"
    ].write_text(
        json.dumps(
            ayarlar,
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8",
    )


# ==========================================================
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozeti(
    ilce_adi: str,
    ilce_slug: str,
    args: argparse.Namespace,
    yamalar: gpd.GeoDataFrame,
    yollar: dict[str, Path],
) -> None:
    """
    Oluşturulan adayları terminalde gösterir.
    """

    print()
    print("=" * 95)
    print("PİLOT UYDU ANALİZ ALANLARI HAZIRLANDI")
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
        "Aday kaynağı:",
        args.aday_kaynagi,
    )

    print(
        "Seçilen aday:",
        len(
            yamalar
        ),
    )

    print(
        "Yama boyutu:",
        f"{args.yama_boyutu} x "
        f"{args.yama_boyutu} metre",
    )

    print()
    print(
        "Seçilen pilot adaylar:"
    )

    sirali_yamalar = yamalar.sort_values(
        "district_candidate_rank"
    )

    for yama in sirali_yamalar.itertuples():
        print()
        print(
            f"  {int(yama.district_candidate_rank)}. "
            f"{yama.patch_id} — {yama.cell_id}"
        )

        print(
            "    Kütüphaneye uzaklık:",
            f"{float(yama.nearest_library_distance_km):.2f} km",
        )

        print(
            "    Ön ihtiyaç puanı:",
            f"{float(yama.preliminary_need_score):.2f}",
        )

        if hasattr(
            yama,
            "built_up_pct",
        ):
            print(
                "    Yapılaşmış alan:",
                f"%{float(yama.built_up_pct):.2f}",
            )

        print(
            "    BBOX:",
            f"{yama.min_longitude}, "
            f"{yama.min_latitude}, "
            f"{yama.max_longitude}, "
            f"{yama.max_latitude}",
        )

    print()
    print(
        "Pilot aday GeoJSON:"
    )

    print(
        f"  {yollar['pilot_aday']}"
    )

    print()
    print(
        "BBOX tablosu:"
    )

    print(
        f"  {yollar['uydu_bbox']}"
    )

    print()
    print(
        "Analiz ayarları:"
    )

    print(
        f"  {yollar['ayarlar']}"
    )

    print()
    print(
        "Not: Bu sürüm ilçe adına özel HTML üretmez."
    )

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    args = argumanlari_oku()

    ilce_adi = args.ilce

    ilce_slug = slug_olustur(
        ilce_adi
    )

    yollar = dosya_yollarini_olustur(
        ilce_slug,
        args.worldcover_yili,
    )

    print()
    print(
        "Analiz ayarları:"
    )

    print(
        f"  İlçe: {ilce_adi}"
    )

    print(
        f"  Aday kaynağı: {args.aday_kaynagi}"
    )

    print(
        f"  Aday sayısı: {args.aday_sayisi}"
    )

    print(
        f"  Yama boyutu: {args.yama_boyutu} metre"
    )

    print()
    print(
        "Pilot aday hücreler okunuyor..."
    )

    if args.aday_kaynagi == "worldcover":
        adaylar, kaynak_dosyasi = (
            worldcover_adaylarini_sec(
                ilce_adi=ilce_adi,
                aday_sayisi=args.aday_sayisi,
                worldcover_yili=args.worldcover_yili,
                kaynak_yolu=yollar[
                    "worldcover_aday"
                ],
            )
        )

    else:
        adaylar, kaynak_dosyasi = (
            on_siralamadan_aday_sec(
                ilce_adi=ilce_adi,
                aday_sayisi=args.aday_sayisi,
            )
        )

    adaylar = adaylari_normalize_et(
        adaylar,
        ilce_adi,
    )

    if len(
        adaylar
    ) < args.aday_sayisi:
        print(
            f"Uyarı: {args.aday_sayisi} yerine "
            f"{len(adaylar)} aday bulundu."
        )

    print(
        "Uydu sorgu yamaları oluşturuluyor..."
    )

    yamalar = uydu_yamalarini_olustur(
        adaylar=adaylar,
        ilce_adi=ilce_adi,
        ilce_slug=ilce_slug,
        yama_boyutu=args.yama_boyutu,
    )

    yamalar = bbox_bilgilerini_ekle(
        yamalar
    )

    print(
        "Çıktılar kaydediliyor..."
    )

    ciktilari_kaydet(
        adaylar=adaylar,
        yamalar=yamalar,
        ilce_adi=ilce_adi,
        ilce_slug=ilce_slug,
        args=args,
        kaynak_dosyasi=kaynak_dosyasi,
        yollar=yollar,
    )

    terminal_ozeti(
        ilce_adi=ilce_adi,
        ilce_slug=ilce_slug,
        args=args,
        yamalar=yamalar,
        yollar=yollar,
    )


if __name__ == "__main__":
    main()