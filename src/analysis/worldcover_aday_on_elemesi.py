from __future__ import annotations

import argparse
import json
import math
import re
import unicodedata
import warnings

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import planetary_computer
import pystac_client
import rasterio

from rasterio.enums import Resampling
from rasterio.errors import WindowError
from rasterio.features import geometry_mask
from rasterio.transform import from_origin
from rasterio.vrt import WarpedVRT
from rasterio.windows import Window, from_bounds, transform as window_transform
from shapely.geometry import mapping


# ==========================================================
# PROJE VE VERİ AYARLARI
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

STAC_API_ADRESI = (
    "https://planetarycomputer.microsoft.com/api/stac/v1"
)

WORLDCOVER_KOLEKSIYONU = "esa-worldcover"

COGRAFI_CRS = "EPSG:4326"

ISTANBUL_METRIK_CRS = "EPSG:32635"

WORLDCOVER_COZUNURLUK_METRE = 10

WORLDCOVER_KAPSAMA_ESIGI = 95.0


# ==========================================================
# WORLDCOVER SINIFLARI
# ==========================================================

# ESA WorldCover:
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
# UrbanAI için sade sınıflar:
#
# 1 = Yapılaşmış
# 2 = Bitkisel / yeşil
# 3 = Açık / çıplak
# 4 = Su / sulak

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

SINIF_ESLEME_DIZISI = np.zeros(
    256,
    dtype=np.uint8,
)

for kaynak_sinif, hedef_sinif in (
    WORLDCOVER_SADELESTIRME.items()
):
    SINIF_ESLEME_DIZISI[
        kaynak_sinif
    ] = hedef_sinif


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
    Analiz ilçesini, WorldCover yılını ve
    oluşturulacak yeni aday sayısını okur.
    """

    parser = argparse.ArgumentParser(
        description=(
            "İlçedeki bütün hizmet boşluğu adaylarını "
            "ESA WorldCover ile ön elemeden geçirir."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help="Analiz edilecek ilçe. Örnek: Pendik",
    )

    parser.add_argument(
        "--yil",
        type=int,
        choices=[
            2020,
            2021,
        ],
        default=2021,
        help="ESA WorldCover yılı. Varsayılan: 2021",
    )

    parser.add_argument(
        "--ilk-aday",
        type=int,
        default=5,
        help=(
            "Ön elemeden sonra seçilecek aday sayısı. "
            "Varsayılan: 5"
        ),
    )

    argumanlar = parser.parse_args()

    argumanlar.ilce = argumanlar.ilce.strip()

    if not argumanlar.ilce:
        parser.error(
            "--ilce değeri boş bırakılamaz."
        )

    if argumanlar.ilk_aday <= 0:
        parser.error(
            "--ilk-aday sıfırdan büyük olmalıdır."
        )

    return argumanlar


# ==========================================================
# GÜVENLİ İLÇE ADI
# ==========================================================

def slug_olustur(
    metin: str,
) -> str:
    """
    İlçe adını klasörlerde kullanılabilecek
    güvenli biçime dönüştürür.
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
    worldcover_yili: int,
) -> dict[str, Path]:
    """
    Girdi ve çıktı yollarını oluşturur.
    """

    cikti_klasoru = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
        / f"worldcover_{worldcover_yili}"
        / "candidate_screening"
    )

    return {
        "hizmet_hucreleri_geojson": (
            PROJE_KOKU
            / "data"
            / "processed"
            / "hizmet_boslugu_hucreleri.geojson"
        ),

        "on_siralama_csv": (
            PROJE_KOKU
            / "data"
            / "processed"
            / "aday_hucre_on_siralama.csv"
        ),

        "cikti_klasoru": (
            cikti_klasoru
        ),

        "tum_adaylar_csv": (
            cikti_klasoru
            / "worldcover_tum_adaylar.csv"
        ),

        "tum_adaylar_geojson": (
            cikti_klasoru
            / "worldcover_tum_adaylar.geojson"
        ),

        "kentsel_adaylar_csv": (
            cikti_klasoru
            / "worldcover_kentsel_on_inceleme_adaylari.csv"
        ),

        "yeni_ilk_aday_csv": (
            cikti_klasoru
            / "worldcover_yeni_ilk_adaylar.csv"
        ),

        "yeni_ilk_aday_geojson": (
            cikti_klasoru
            / "worldcover_yeni_ilk_adaylar.geojson"
        ),

        "analiz_ozeti_json": (
            cikti_klasoru
            / "worldcover_aday_on_elemesi_ozeti.json"
        ),
    }


# ==========================================================
# ANA HİZMET HÜCRELERİNİ OKUMA
# ==========================================================

def hizmet_hucrelerini_oku(
    dosya_yolu: Path,
    ilce_adi: str,
) -> gpd.GeoDataFrame:
    """
    Ana hizmet boşluğu GeoJSON dosyasından
    seçilen ilçenin candidate_review=Evet
    hücrelerini okur.
    """

    if not dosya_yolu.exists():
        raise FileNotFoundError(
            "Hizmet boşluğu hücre dosyası bulunamadı:\n"
            f"{dosya_yolu}"
        )

    hucreler = gpd.read_file(
        dosya_yolu
    )

    gerekli_sutunlar = [
        "cell_id",
        "district_name",
        "nearest_library_name",
        "nearest_library_distance_km",
        "candidate_review",
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
        raise ValueError(
            "Hizmet hücre dosyasında koordinat sistemi yok."
        )

    ilce_maskesi = (
        hucreler[
            "district_name"
        ]
        .astype(str)
        .str.strip()
        .str.casefold()
        .eq(
            ilce_adi.casefold()
        )
    )

    aday_maskesi = (
        hucreler[
            "candidate_review"
        ]
        .astype(str)
        .str.strip()
        .str.casefold()
        .eq("evet")
    )

    adaylar = hucreler[
        ilce_maskesi
        & aday_maskesi
    ].copy()

    adaylar[
        "cell_id"
    ] = adaylar[
        "cell_id"
    ].astype(str)

    adaylar[
        "nearest_library_distance_km"
    ] = pd.to_numeric(
        adaylar[
            "nearest_library_distance_km"
        ],
        errors="coerce",
    )

    adaylar = adaylar.dropna(
        subset=[
            "cell_id",
            "nearest_library_distance_km",
            "geometry",
        ]
    ).copy()

    adaylar = adaylar[
        ~adaylar.geometry.is_empty
    ].copy()

    if adaylar.empty:
        raise ValueError(
            f"{ilce_adi} için analiz edilecek "
            "hizmet boşluğu adayı bulunamadı."
        )

    return gpd.GeoDataFrame(
        adaylar,
        geometry="geometry",
        crs=hucreler.crs,
    )


# ==========================================================
# ÖN SIRALAMA VERİLERİNİ OKUMA
# ==========================================================

def on_siralama_verilerini_oku(
    dosya_yolu: Path,
    ilce_adi: str,
) -> pd.DataFrame:
    """
    İhtiyaç puanlarını ve mevcut aday
    sıralamalarını okur.
    """

    if not dosya_yolu.exists():
        raise FileNotFoundError(
            "Aday hücre ön sıralama dosyası bulunamadı:\n"
            f"{dosya_yolu}"
        )

    siralama = pd.read_csv(
        dosya_yolu,
        encoding="utf-8-sig",
    )

    gerekli_sutunlar = [
        "cell_id",
        "district_name",
        "district_candidate_rank",
        "global_candidate_rank",
        "preliminary_need_score",
        "global_preliminary_score",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in siralama.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "Ön sıralama dosyasında eksik sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    ilce_siralama = siralama[
        siralama[
            "district_name"
        ]
        .astype(str)
        .str.strip()
        .str.casefold()
        .eq(
            ilce_adi.casefold()
        )
    ].copy()

    ilce_siralama[
        "cell_id"
    ] = ilce_siralama[
        "cell_id"
    ].astype(str)

    sayisal_sutunlar = [
        "district_candidate_rank",
        "global_candidate_rank",
        "preliminary_need_score",
        "global_preliminary_score",
    ]

    for sutun in sayisal_sutunlar:
        ilce_siralama[
            sutun
        ] = pd.to_numeric(
            ilce_siralama[
                sutun
            ],
            errors="coerce",
        )

    ilce_siralama = ilce_siralama.drop_duplicates(
        subset=[
            "cell_id",
        ],
        keep="first",
    )

    return ilce_siralama[
        gerekli_sutunlar
    ].copy()


# ==========================================================
# HÜCRELER VE PUANLARI BİRLEŞTİRME
# ==========================================================

def aday_verilerini_birlestir(
    adaylar: gpd.GeoDataFrame,
    siralama: pd.DataFrame,
) -> gpd.GeoDataFrame:
    """
    Geometriler ile ön ihtiyaç puanlarını
    cell_id üzerinden birleştirir.
    """

    birlesik = adaylar.merge(
        siralama.drop(
            columns=[
                "district_name",
            ],
            errors="ignore",
        ),
        on="cell_id",
        how="left",
        validate="one_to_one",
    )

    eksik_siralama = birlesik[
        "preliminary_need_score"
    ].isna().sum()

    if eksik_siralama > 0:
        print(
            f"Uyarı: {eksik_siralama} hücrenin "
            "ön ihtiyaç puanı bulunamadı."
        )

    birlesik[
        "preliminary_need_score"
    ] = birlesik[
        "preliminary_need_score"
    ].fillna(
        birlesik[
            "nearest_library_distance_km"
        ]
    )

    birlesik[
        "district_candidate_rank"
    ] = birlesik[
        "district_candidate_rank"
    ].fillna(
        999999
    ).astype(int)

    return gpd.GeoDataFrame(
        birlesik,
        geometry="geometry",
        crs=adaylar.crs,
    )


# ==========================================================
# WORLDCOVER SORGU BBOX'U
# ==========================================================

def birlesik_bbox_hesapla(
    adaylar: gpd.GeoDataFrame,
) -> list[float]:
    """
    İlçedeki bütün adayları kapsayan WGS84
    sınır kutusunu hesaplar.
    """

    adaylar_cografi = adaylar.to_crs(
        COGRAFI_CRS
    )

    minx, miny, maxx, maxy = (
        adaylar_cografi.total_bounds
    )

    return [
        float(minx),
        float(miny),
        float(maxx),
        float(maxy),
    ]


# ==========================================================
# WORLDCOVER STAC VERİLERİNİ BULMA
# ==========================================================

def worldcover_ogelerini_bul(
    bbox: list[float],
    worldcover_yili: int,
) -> list[Any]:
    """
    Aday alanla kesişen ESA WorldCover
    STAC öğelerini bulur.
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

    ogeler = []

    for oge in arama.items():

        if "map" not in oge.assets:
            continue

        ogeler.append(
            planetary_computer.sign(
                oge
            )
        )

    if not ogeler:
        raise RuntimeError(
            "Aday alanla kesişen ESA WorldCover "
            "raster verisi bulunamadı."
        )

    return sorted(
        ogeler,
        key=lambda oge: str(
            oge.id
        ),
    )


# ==========================================================
# İLÇE GENELİ ORTAK RASTER GRİDİ
# ==========================================================

def ortak_grid_olustur(
    adaylar_metrik: gpd.GeoDataFrame,
) -> tuple[
    Any,
    int,
    int,
]:
    """
    Bütün adayları kapsayan tek 10 metrelik
    raster gridi oluşturur.
    """

    minx, miny, maxx, maxy = (
        adaylar_metrik.total_bounds
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
            "İlçe için geçerli raster gridi oluşturulamadı."
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
# WORLDCOVER MOZAIĞINI BİR KEZ OKUMA
# ==========================================================

def worldcover_mozaigini_oku(
    worldcover_ogeleri: list[Any],
    hedef_transform,
    hedef_genislik: int,
    hedef_yukseklik: int,
) -> np.ndarray:
    """
    İlçenin bütün aday hücreleri için WorldCover
    verisini yalnızca bir defa ortak gride okur.
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

        for sira, oge in enumerate(
            worldcover_ogeleri,
            start=1,
        ):

            print(
                f"  WorldCover raster parçası "
                f"{sira}/{len(worldcover_ogeleri)} okunuyor..."
            )

            map_asset = oge.assets[
                "map"
            ]

            with rasterio.open(
                map_asset.href
            ) as kaynak:

                if kaynak.crs is None:
                    raise ValueError(
                        "WorldCover rasterında "
                        "koordinat sistemi bulunamadı."
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

                    with warnings.catch_warnings():

                        warnings.filterwarnings(
                            "ignore",
                            message=(
                                "Setting the shape on a "
                                "NumPy array has been deprecated.*"
                            ),
                            category=DeprecationWarning,
                        )

                        parca = np.asarray(
                            donusturulmus.read(
                                1
                            )
                        ).copy()

            doldurulacak_maskesi = (
                (birlesik_raster == 0)
                & (parca != 0)
            )

            birlesik_raster[
                doldurulacak_maskesi
            ] = parca[
                doldurulacak_maskesi
            ]

    return birlesik_raster


# ==========================================================
# TEK HÜCRE PENCERESİNİ ÇIKARMA
# ==========================================================

def hucre_raster_penceresini_al(
    worldcover_rasteri: np.ndarray,
    ana_transform,
    geometri,
) -> tuple[
    np.ndarray,
    np.ndarray,
]:
    """
    İlçe rasterından yalnızca aday hücreye denk
    gelen küçük pencereyi çıkarır.
    """

    pencere = from_bounds(
        *geometri.bounds,
        transform=ana_transform,
    )

    pencere = (
        pencere
        .round_offsets()
        .round_lengths()
    )

    raster_siniri = Window(
        col_off=0,
        row_off=0,
        width=worldcover_rasteri.shape[1],
        height=worldcover_rasteri.shape[0],
    )

    try:
        pencere = pencere.intersection(
            raster_siniri
        )

    except WindowError as hata:
        raise ValueError(
            "Aday hücre ortak rasterın dışında kaldı."
        ) from hata

    satir_baslangic = int(
        pencere.row_off
    )

    satir_bitis = int(
        pencere.row_off
        + pencere.height
    )

    sutun_baslangic = int(
        pencere.col_off
    )

    sutun_bitis = int(
        pencere.col_off
        + pencere.width
    )

    raster_parcasi = worldcover_rasteri[
        satir_baslangic:satir_bitis,
        sutun_baslangic:sutun_bitis,
    ]

    if raster_parcasi.size == 0:
        raise ValueError(
            "Aday hücre için boş raster penceresi oluştu."
        )

    parca_transformu = window_transform(
        pencere,
        ana_transform,
    )

    geometri_maskesi = geometry_mask(
        geometries=[
            mapping(
                geometri
            )
        ],
        out_shape=raster_parcasi.shape,
        transform=parca_transformu,
        invert=True,
        all_touched=False,
    )

    return (
        raster_parcasi,
        geometri_maskesi,
    )


# ==========================================================
# SINIF ORANLARINI HESAPLAMA
# ==========================================================

def sinif_oranlarini_hesapla(
    worldcover_parcasi: np.ndarray,
    geometri_maskesi: np.ndarray,
) -> dict[str, Any]:
    """
    Tek aday hücrenin arazi örtüsü oranlarını
    hesaplar.
    """

    sade_raster = SINIF_ESLEME_DIZISI[
        worldcover_parcasi
    ]

    sade_raster[
        ~geometri_maskesi
    ] = 0

    aday_piksel_sayisi = int(
        geometri_maskesi.sum()
    )

    siniflandirilmis_piksel = int(
        (
            sade_raster
            > 0
        ).sum()
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

    oranlar: dict[str, Any] = {
        "candidate_pixel_count": (
            aday_piksel_sayisi
        ),

        "classified_pixel_count": (
            siniflandirilmis_piksel
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

    for sinif_kodu, sutun_adi in (
        sinif_sutunlari.items()
    ):

        piksel_sayisi = int(
            (
                sade_raster
                == sinif_kodu
            ).sum()
        )

        oran = (
            (
                piksel_sayisi
                / siniflandirilmis_piksel
                * 100
            )
            if siniflandirilmis_piksel > 0
            else 0.0
        )

        oranlar[
            f"{sutun_adi}_pct"
        ] = round(
            oran,
            2,
        )

    return oranlar


# ==========================================================
# ÖN ELEME DURUMU
# ==========================================================

def on_eleme_durumu_belirle(
    oranlar: dict[str, Any],
) -> tuple[
    str,
    bool,
    str,
]:
    """
    Arazi örtüsünü kesin uygunluk kararı vermeden
    yalnızca kentsel bağlam ön elemesine dönüştürür.
    """

    kapsama = float(
        oranlar[
            "worldcover_coverage_pct"
        ]
    )

    yapilasmis = float(
        oranlar[
            "built_up_pct"
        ]
    )

    yesil = float(
        oranlar[
            "vegetation_pct"
        ]
    )

    acik = float(
        oranlar[
            "open_bare_pct"
        ]
    )

    su = float(
        oranlar[
            "water_wetland_pct"
        ]
    )

    if kapsama < WORLDCOVER_KAPSAMA_ESIGI:

        return (
            "worldcover_verisi_yetersiz",
            False,
            (
                "WorldCover kapsaması ön eleme için "
                "yeterli değildir."
            ),
        )

    if su >= 30:

        return (
            "su_veya_sulak_alan_baskin",
            False,
            (
                "Hücrede su veya sulak alan oranı "
                "yüksektir."
            ),
        )

    if (
        yapilasmis < 5
        and yesil >= 80
    ):

        return (
            "yerlesim_disi_yesil_bolge",
            False,
            (
                "Yapılaşmış alan çok düşük, bitkisel "
                "ve yeşil alan oranı çok yüksektir."
            ),
        )

    if yapilasmis >= 30:

        return (
            "kentsel_baglami_guclu",
            True,
            (
                "Hücre belirgin bir yapılaşmış alan "
                "bağlamı taşımaktadır."
            ),
        )

    if yapilasmis >= 10:

        return (
            "kentsel_baglami_var",
            True,
            (
                "Hücrede ön incelemeye değer ölçüde "
                "yapılaşmış alan bulunmaktadır."
            ),
        )

    return (
        "ek_veriyle_incelenmeli",
        False,
        (
            "Hücre açıkça yerleşim dışı değildir; "
            "ancak kentsel bağlamı tek başına yeterli "
            "güçte değildir."
        ),
    )


# ==========================================================
# BÜTÜN ADAYLARI ANALİZ ETME
# ==========================================================

def adaylari_analiz_et(
    adaylar: gpd.GeoDataFrame,
    worldcover_rasteri: np.ndarray,
    ana_transform,
) -> pd.DataFrame:
    """
    İlçedeki bütün hizmet boşluğu adaylarını
    ortak WorldCover rasterı üzerinden analiz eder.
    """

    adaylar_metrik = adaylar.to_crs(
        ISTANBUL_METRIK_CRS
    )

    sonuc_kayitlari: list[
        dict[str, Any]
    ] = []

    toplam = len(
        adaylar_metrik
    )

    for sira, aday in enumerate(
        adaylar_metrik.itertuples(),
        start=1,
    ):

        if (
            sira == 1
            or sira % 25 == 0
            or sira == toplam
        ):
            print(
                f"  {sira}/{toplam} hücre analiz edildi..."
            )

        geometri = aday.geometry

        if not geometri.is_valid:
            geometri = geometri.buffer(
                0
            )

        (
            raster_parcasi,
            geometri_maskesi,
        ) = hucre_raster_penceresini_al(
            worldcover_rasteri,
            ana_transform,
            geometri,
        )

        oranlar = sinif_oranlarini_hesapla(
            raster_parcasi,
            geometri_maskesi,
        )

        (
            on_eleme_durumu,
            kentsel_on_inceleme,
            on_eleme_aciklamasi,
        ) = on_eleme_durumu_belirle(
            oranlar
        )

        sonuc_kayitlari.append(
            {
                "cell_id": str(
                    aday.cell_id
                ),

                "worldcover_coverage_pct": (
                    oranlar[
                        "worldcover_coverage_pct"
                    ]
                ),

                "built_up_pct": (
                    oranlar[
                        "built_up_pct"
                    ]
                ),

                "vegetation_pct": (
                    oranlar[
                        "vegetation_pct"
                    ]
                ),

                "open_bare_pct": (
                    oranlar[
                        "open_bare_pct"
                    ]
                ),

                "water_wetland_pct": (
                    oranlar[
                        "water_wetland_pct"
                    ]
                ),

                "candidate_pixel_count": (
                    oranlar[
                        "candidate_pixel_count"
                    ]
                ),

                "classified_pixel_count": (
                    oranlar[
                        "classified_pixel_count"
                    ]
                ),

                "landcover_screening_status": (
                    on_eleme_durumu
                ),

                "urban_context_screening_pass": int(
                    kentsel_on_inceleme
                ),

                "landcover_screening_explanation": (
                    on_eleme_aciklamasi
                ),
            }
        )

    return pd.DataFrame(
        sonuc_kayitlari
    )


# ==========================================================
# YENİ ADAYLARI SEÇME
# ==========================================================

def yeni_adaylari_sec(
    sonuc_gdf: gpd.GeoDataFrame,
    ilk_aday_sayisi: int,
) -> tuple[
    gpd.GeoDataFrame,
    gpd.GeoDataFrame,
]:
    """
    Kentsel bağlam ön elemesinden geçen hücreleri,
    mevcut ihtiyaç puanını koruyarak sıralar.
    """

    kentsel_adaylar = sonuc_gdf[
        sonuc_gdf[
            "urban_context_screening_pass"
        ]
        == 1
    ].copy()

    kentsel_adaylar = kentsel_adaylar.sort_values(
        by=[
            "preliminary_need_score",
            "built_up_pct",
            "nearest_library_distance_km",
        ],
        ascending=[
            False,
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )

    kentsel_adaylar[
        "screened_candidate_rank"
    ] = (
        np.arange(
            len(
                kentsel_adaylar
            )
        )
        + 1
    )

    yeni_ilk_adaylar = kentsel_adaylar.head(
        ilk_aday_sayisi
    ).copy()

    return (
        gpd.GeoDataFrame(
            kentsel_adaylar,
            geometry="geometry",
            crs=sonuc_gdf.crs,
        ),

        gpd.GeoDataFrame(
            yeni_ilk_adaylar,
            geometry="geometry",
            crs=sonuc_gdf.crs,
        ),
    )


# ==========================================================
# ÇIKTILARI KAYDETME
# ==========================================================

def ciktilari_kaydet(
    sonuc_gdf: gpd.GeoDataFrame,
    kentsel_adaylar: gpd.GeoDataFrame,
    yeni_ilk_adaylar: gpd.GeoDataFrame,
    ilce_adi: str,
    ilce_slug: str,
    worldcover_yili: int,
    worldcover_ogeleri: list[Any],
    yollar: dict[str, Path],
) -> None:
    """
    CSV, GeoJSON ve analiz özeti çıktılarını kaydeder.
    """

    yollar[
        "cikti_klasoru"
    ].mkdir(
        parents=True,
        exist_ok=True,
    )

    sonuc_gdf.drop(
        columns=[
            "geometry",
        ],
        errors="ignore",
    ).to_csv(
        yollar[
            "tum_adaylar_csv"
        ],
        index=False,
        encoding="utf-8-sig",
    )

    sonuc_gdf.to_file(
        yollar[
            "tum_adaylar_geojson"
        ],
        driver="GeoJSON",
    )

    kentsel_adaylar.drop(
        columns=[
            "geometry",
        ],
        errors="ignore",
    ).to_csv(
        yollar[
            "kentsel_adaylar_csv"
        ],
        index=False,
        encoding="utf-8-sig",
    )

    yeni_ilk_adaylar.drop(
        columns=[
            "geometry",
        ],
        errors="ignore",
    ).to_csv(
        yollar[
            "yeni_ilk_aday_csv"
        ],
        index=False,
        encoding="utf-8-sig",
    )

    yeni_ilk_adaylar.to_file(
        yollar[
            "yeni_ilk_aday_geojson"
        ],
        driver="GeoJSON",
    )

    durum_sayilari = (
        sonuc_gdf[
            "landcover_screening_status"
        ]
        .value_counts()
        .to_dict()
    )

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

        "analyzed_candidate_count": int(
            len(
                sonuc_gdf
            )
        ),

        "urban_context_candidate_count": int(
            len(
                kentsel_adaylar
            )
        ),

        "selected_candidate_count": int(
            len(
                yeni_ilk_adaylar
            )
        ),

        "screening_status_counts": {
            str(anahtar): int(
                deger
            )
            for anahtar, deger in (
                durum_sayilari.items()
            )
        },

        "source_item_ids": [
            str(
                oge.id
            )
            for oge in worldcover_ogeleri
        ],

        "selection_method": (
            "Önce WorldCover ile açıkça yerleşim dışı, "
            "su veya yetersiz kapsamalı hücreler ayrılmış; "
            "kentsel bağlam ön elemesinden geçen hücrelerde "
            "mevcut preliminary_need_score sıralaması "
            "korunmuştur."
        ),

        "screening_rules": {
            "insufficient_coverage": (
                "WorldCover kapsaması <%95"
            ),

            "water_wetland_dominant": (
                "Su veya sulak alan >=%30"
            ),

            "non_urban_green": (
                "Yapılaşmış <%5 ve yeşil alan >=%80"
            ),

            "strong_urban_context": (
                "Yapılaşmış alan >=%30"
            ),

            "urban_context": (
                "Yapılaşmış alan >=%10"
            ),
        },

        "planning_warning": (
            "Bu ön eleme imar, parsel, mülkiyet veya "
            "yapılabilirlik kararı değildir. WorldCover "
            "yalnızca arazi örtüsü ve kentsel bağlam "
            "göstergesi olarak kullanılmıştır."
        ),

        "created_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
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


# ==========================================================
# TERMİNAL ÖZETİ
# ==========================================================

def terminal_ozetini_yazdir(
    ilce_adi: str,
    worldcover_yili: int,
    sonuc_gdf: gpd.GeoDataFrame,
    kentsel_adaylar: gpd.GeoDataFrame,
    yeni_ilk_adaylar: gpd.GeoDataFrame,
    yollar: dict[str, Path],
) -> None:
    """
    Analiz sonucunu terminalde özetler.
    """

    print()
    print("=" * 95)
    print(
        "WORLDCOVER ADAY ÖN ELEME ANALİZİ TAMAMLANDI"
    )
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
        "Analiz edilen hizmet boşluğu adayı:",
        len(
            sonuc_gdf
        ),
    )

    print(
        "Kentsel bağlam ön elemesinden geçen:",
        len(
            kentsel_adaylar
        ),
    )

    print(
        "Yeni seçilen aday:",
        len(
            yeni_ilk_adaylar
        ),
    )

    print()
    print(
        "Ön eleme durumları:"
    )

    durumlar = (
        sonuc_gdf[
            "landcover_screening_status"
        ]
        .value_counts()
    )

    for durum, sayi in (
        durumlar.items()
    ):
        print(
            f"  {durum}: {sayi}"
        )

    print()
    print(
        "Yeni ilk adaylar:"
    )

    for kayit in (
        yeni_ilk_adaylar.itertuples()
    ):

        print()
        print(
            f"  {int(kayit.screened_candidate_rank)}. "
            f"{kayit.cell_id}"
        )

        print(
            f"    Ön ihtiyaç puanı: "
            f"{float(kayit.preliminary_need_score):.2f}"
        )

        print(
            f"    Kütüphaneye uzaklık: "
            f"{float(kayit.nearest_library_distance_km):.2f} km"
        )

        print(
            f"    Yapılaşmış alan: "
            f"%{float(kayit.built_up_pct):.2f}"
        )

        print(
            f"    Yeşil alan: "
            f"%{float(kayit.vegetation_pct):.2f}"
        )

        print(
            f"    Açık / çıplak alan: "
            f"%{float(kayit.open_bare_pct):.2f}"
        )

        print(
            f"    Ön eleme durumu: "
            f"{kayit.landcover_screening_status}"
        )

    print()
    print(
        "Yeni aday GeoJSON:"
    )

    print(
        f"  {yollar['yeni_ilk_aday_geojson']}"
    )

    print()
    print(
        "Tüm aday sonuçları:"
    )

    print(
        f"  {yollar['tum_adaylar_csv']}"
    )

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    İlçedeki bütün hizmet boşluğu adaylarını
    WorldCover ile ön elemeden geçirir.
    """

    argumanlar = argumanlari_oku()

    ilce_adi = (
        argumanlar.ilce
    )

    worldcover_yili = (
        argumanlar.yil
    )

    ilk_aday_sayisi = (
        argumanlar.ilk_aday
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

    print(
        f"  Seçilecek yeni aday: {ilk_aday_sayisi}"
    )

    print()
    print(
        "Hizmet boşluğu adayları okunuyor..."
    )

    adaylar = hizmet_hucrelerini_oku(
        yollar[
            "hizmet_hucreleri_geojson"
        ],
        ilce_adi,
    )

    print(
        f"  Bulunan aday hücre: {len(adaylar)}"
    )

    print(
        "Ön ihtiyaç sıralaması okunuyor..."
    )

    siralama = on_siralama_verilerini_oku(
        yollar[
            "on_siralama_csv"
        ],
        ilce_adi,
    )

    adaylar = aday_verilerini_birlestir(
        adaylar,
        siralama,
    )

    print(
        "WorldCover sorgu alanı hesaplanıyor..."
    )

    bbox = birlesik_bbox_hesapla(
        adaylar
    )

    print(
        "ESA WorldCover verisi aranıyor..."
    )

    worldcover_ogeleri = (
        worldcover_ogelerini_bul(
            bbox,
            worldcover_yili,
        )
    )

    print(
        f"  Bulunan raster parçası: "
        f"{len(worldcover_ogeleri)}"
    )

    adaylar_metrik = adaylar.to_crs(
        ISTANBUL_METRIK_CRS
    )

    (
        hedef_transform,
        hedef_genislik,
        hedef_yukseklik,
    ) = ortak_grid_olustur(
        adaylar_metrik
    )

    print(
        "İlçe geneli ortak WorldCover rasterı hazırlanıyor..."
    )

    print(
        f"  Raster boyutu: "
        f"{hedef_genislik} x {hedef_yukseklik} piksel"
    )

    worldcover_rasteri = (
        worldcover_mozaigini_oku(
            worldcover_ogeleri,
            hedef_transform,
            hedef_genislik,
            hedef_yukseklik,
        )
    )

    print(
        "Aday hücreler ortak raster üzerinden "
        "analiz ediliyor..."
    )

    arazi_sonuclari = adaylari_analiz_et(
        adaylar,
        worldcover_rasteri,
        hedef_transform,
    )

    sonuc_gdf = adaylar.merge(
        arazi_sonuclari,
        on="cell_id",
        how="left",
        validate="one_to_one",
    )

    sonuc_gdf = gpd.GeoDataFrame(
        sonuc_gdf,
        geometry="geometry",
        crs=adaylar.crs,
    )

    (
        kentsel_adaylar,
        yeni_ilk_adaylar,
    ) = yeni_adaylari_sec(
        sonuc_gdf,
        ilk_aday_sayisi,
    )

    print(
        "Analiz çıktıları kaydediliyor..."
    )

    ciktilari_kaydet(
        sonuc_gdf,
        kentsel_adaylar,
        yeni_ilk_adaylar,
        ilce_adi,
        ilce_slug,
        worldcover_yili,
        worldcover_ogeleri,
        yollar,
    )

    terminal_ozetini_yazdir(
        ilce_adi,
        worldcover_yili,
        sonuc_gdf,
        kentsel_adaylar,
        yeni_ilk_adaylar,
        yollar,
    )


if __name__ == "__main__":
    main()