from __future__ import annotations

import json
import sqlite3

from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    Request,
)

from fastapi.responses import FileResponse


# ==========================================================
# PROJE VE VERİ TABANI YOLLARI
# ==========================================================

PROJE_KOKU = Path(
    __file__
).resolve().parents[2]

VERITABANI_YOLU = (
    PROJE_KOKU
    / "data"
    / "database"
    / "urbanai.db"
)

FRONTEND_KOKU = (
    PROJE_KOKU
    / "frontend"
)


# ==========================================================
# API ROUTER
# ==========================================================

router = APIRouter(
    tags=[
        "Uydu Görüntüleri",
    ]
)


# ==========================================================
# VERİ TABANI BAĞLANTISI
# ==========================================================

def baglanti_olustur() -> sqlite3.Connection:
    """
    UrbanAI SQLite veri tabanına bağlanır.
    """

    if not VERITABANI_YOLU.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "UrbanAI veri tabanı bulunamadı: "
                f"{VERITABANI_YOLU}"
            ),
        )

    baglanti = sqlite3.connect(
        VERITABANI_YOLU
    )

    baglanti.row_factory = sqlite3.Row

    baglanti.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return baglanti


# ==========================================================
# TABLO KONTROLÜ
# ==========================================================

def tablo_var_mi(
    baglanti: sqlite3.Connection,
    tablo_adi: str,
) -> bool:
    """
    SQLite veri tabanında tablonun bulunup
    bulunmadığını kontrol eder.
    """

    sonuc = baglanti.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1;
        """,
        (
            tablo_adi,
        ),
    ).fetchone()

    return sonuc is not None


def uydu_tablolarini_kontrol_et(
    baglanti: sqlite3.Connection,
) -> None:
    """
    Uydu API’sinin ihtiyaç duyduğu tabloları
    kontrol eder.
    """

    gerekli_tablolar = [
        "satellite_scenes",
        "satellite_patches",
    ]

    eksik_tablolar = [
        tablo_adi
        for tablo_adi in gerekli_tablolar
        if not tablo_var_mi(
            baglanti,
            tablo_adi,
        )
    ]

    if eksik_tablolar:
        raise HTTPException(
            status_code=503,
            detail=(
                "Uydu veri tabloları bulunamadı: "
                + ", ".join(
                    eksik_tablolar
                )
            ),
        )


# ==========================================================
# JSON YARDIMCILARI
# ==========================================================

def json_liste_oku(
    deger: Any,
) -> list[str]:
    """
    JSON biçiminde saklanan sahne kimliklerini
    güvenli şekilde listeye dönüştürür.
    """

    if deger is None:
        return []

    metin = str(
        deger
    ).strip()

    if not metin:
        return []

    try:
        sonuc = json.loads(
            metin
        )

    except json.JSONDecodeError:
        return [
            parca.strip()
            for parca in metin.split(",")
            if parca.strip()
        ]

    if not isinstance(
        sonuc,
        list,
    ):
        return []

    return [
        str(
            eleman
        )
        for eleman in sonuc
        if str(
            eleman
        ).strip()
    ]


def json_sozluk_oku(
    deger: Any,
) -> dict[str, Any]:
    """
    JSON biçimindeki sahne metadata bilgisini
    güvenli biçimde sözlüğe dönüştürür.
    """

    if deger is None:
        return {}

    metin = str(
        deger
    ).strip()

    if not metin:
        return {}

    try:
        sonuc = json.loads(
            metin
        )

    except json.JSONDecodeError:
        return {}

    if not isinstance(
        sonuc,
        dict,
    ):
        return {}

    return sonuc


# ==========================================================
# DOSYA YOLU KONTROLÜ
# ==========================================================

def png_dosya_yolunu_bul(
    png_relative_path: Any,
) -> Path:
    """
    Veri tabanındaki göreli PNG yolunu gerçek
    dosya yoluna dönüştürür.

    Yolun frontend klasörü dışına çıkmasına
    izin verilmez.
    """

    if png_relative_path is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Uydu yamasına ait PNG yolu "
                "veri tabanında bulunamadı."
            ),
        )

    goreli_yol = str(
        png_relative_path
    ).strip()

    if not goreli_yol:
        raise HTTPException(
            status_code=404,
            detail=(
                "Uydu yamasına ait PNG yolu boş."
            ),
        )

    goreli_yol = goreli_yol.replace(
        "\\",
        "/",
    )

    dosya_yolu = (
        FRONTEND_KOKU
        / goreli_yol
    ).resolve()

    frontend_koku = (
        FRONTEND_KOKU.resolve()
    )

    try:
        dosya_yolu.relative_to(
            frontend_koku
        )

    except ValueError as hata:
        raise HTTPException(
            status_code=400,
            detail=(
                "Geçersiz uydu görüntüsü dosya yolu."
            ),
        ) from hata

    if not dosya_yolu.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                "Uydu görüntüsü dosyası bulunamadı: "
                f"{goreli_yol}"
            ),
        )

    if not dosya_yolu.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                "Uydu görüntüsü yolu bir dosya değil."
            ),
        )

    return dosya_yolu


# ==========================================================
# SQL SEÇİM ALANLARI
# ==========================================================

UYDU_SECIM_ALANLARI = """
    SELECT
        satellite_patches.id
            AS id,

        satellite_patches.district_name
            AS district_name,

        satellite_patches.district_slug
            AS district_slug,

        satellite_patches.patch_id
            AS patch_id,

        satellite_patches.cell_id
            AS cell_id,

        satellite_patches.district_candidate_rank
            AS district_candidate_rank,

        satellite_patches.nearest_library_distance_km
            AS nearest_library_distance_km,

        satellite_patches.width_pixels
            AS width_pixels,

        satellite_patches.height_pixels
            AS height_pixels,

        satellite_patches.band_count
            AS band_count,

        satellite_patches.raster_dtype
            AS raster_dtype,

        satellite_patches.raster_crs
            AS raster_crs,

        satellite_patches.valid_pixel_pct
            AS valid_pixel_pct,

        satellite_patches.requested_area_coverage_pct
            AS requested_area_coverage_pct,

        satellite_patches.coverage_status
            AS coverage_status,

        satellite_patches.analysis_ready
            AS analysis_ready,

        satellite_patches.min_longitude
            AS min_longitude,

        satellite_patches.min_latitude
            AS min_latitude,

        satellite_patches.max_longitude
            AS max_longitude,

        satellite_patches.max_latitude
            AS max_latitude,

        satellite_patches.png_relative_path
            AS png_relative_path,

        satellite_patches.source_item_ids_json
            AS source_item_ids_json,

        satellite_patches.updated_at_utc
            AS patch_updated_at_utc,

        satellite_scenes.item_id
            AS main_scene_item_id,

        satellite_scenes.acquisition_datetime_utc
            AS acquisition_datetime_utc,

        satellite_scenes.cloud_cover_pct
            AS cloud_cover_pct,

        satellite_scenes.platform
            AS platform,

        satellite_scenes.collection_name
            AS collection_name,

        satellite_scenes.selection_method
            AS selection_method,

        satellite_scenes.metadata_json
            AS scene_metadata_json

    FROM satellite_patches

    LEFT JOIN satellite_scenes
        ON satellite_scenes.district_slug =
           satellite_patches.district_slug

       AND satellite_scenes.is_current = 1
"""


# ==========================================================
# API CEVABI OLUŞTURMA
# ==========================================================

def uydu_kaydini_hazirla(
    satir: sqlite3.Row,
    request: Request,
) -> dict[str, Any]:
    """
    SQLite satırını frontend için anlaşılır,
    iç içe JSON yapısına dönüştürür.
    """

    metadata = json_sozluk_oku(
        satir[
            "scene_metadata_json"
        ]
    )

    kaynak_sahneler = json_liste_oku(
        satir[
            "source_item_ids_json"
        ]
    )

    mozaik_sahneleri = metadata.get(
        "mosaic_item_ids",
        [],
    )

    if not isinstance(
        mozaik_sahneleri,
        list,
    ):
        mozaik_sahneleri = []

    min_boylam = satir[
        "min_longitude"
    ]

    min_enlem = satir[
        "min_latitude"
    ]

    max_boylam = satir[
        "max_longitude"
    ]

    max_enlem = satir[
        "max_latitude"
    ]

    merkez_enlem = None
    merkez_boylam = None

    if (
        min_boylam is not None
        and min_enlem is not None
        and max_boylam is not None
        and max_enlem is not None
    ):
        merkez_boylam = (
            float(
                min_boylam
            )
            + float(
                max_boylam
            )
        ) / 2

        merkez_enlem = (
            float(
                min_enlem
            )
            + float(
                max_enlem
            )
        ) / 2

    goruntu_url = str(
        request.url_for(
            "uydu_yama_gorseli",
            patch_id=satir[
                "patch_id"
            ],
        )
    )

    detay_url = str(
        request.url_for(
            "uydu_yama_detayi",
            patch_id=satir[
                "patch_id"
            ],
        )
    )

    return {
        "id": satir[
            "id"
        ],

        "yama_id": satir[
            "patch_id"
        ],

        "hucre_id": satir[
            "cell_id"
        ],

        "ilce": {
            "ad": satir[
                "district_name"
            ],

            "slug": satir[
                "district_slug"
            ],
        },

        "aday": {
            "ilce_ici_sira": satir[
                "district_candidate_rank"
            ],

            "en_yakin_kutuphaneye_uzaklik_km": (
                satir[
                    "nearest_library_distance_km"
                ]
            ),
        },

        "uydu_sahnesi": {
            "ana_sahne_id": satir[
                "main_scene_item_id"
            ],

            "kaynak_sahne_idleri": (
                kaynak_sahneler
            ),

            "mozaik_sahne_idleri": [
                str(
                    sahne_id
                )
                for sahne_id in mozaik_sahneleri
            ],

            "goruntu_tarihi_utc": satir[
                "acquisition_datetime_utc"
            ],

            "bulut_orani_yuzde": satir[
                "cloud_cover_pct"
            ],

            "platform": satir[
                "platform"
            ],

            "koleksiyon": satir[
                "collection_name"
            ],

            "secim_yontemi": satir[
                "selection_method"
            ],

            "isleme_modu": metadata.get(
                "rgb_processing_mode"
            ),
        },

        "raster": {
            "genislik_piksel": satir[
                "width_pixels"
            ],

            "yukseklik_piksel": satir[
                "height_pixels"
            ],

            "bant_sayisi": satir[
                "band_count"
            ],

            "veri_tipi": satir[
                "raster_dtype"
            ],

            "koordinat_sistemi": satir[
                "raster_crs"
            ],
        },

        "kalite": {
            "gecerli_piksel_yuzde": satir[
                "valid_pixel_pct"
            ],

            "gercek_alan_kapsama_yuzde": (
                satir[
                    "requested_area_coverage_pct"
                ]
            ),

            "kapsama_durumu": satir[
                "coverage_status"
            ],

            "analize_hazir": bool(
                satir[
                    "analysis_ready"
                ]
            ),
        },

        "konum": {
            "bbox": {
                "min_boylam": min_boylam,
                "min_enlem": min_enlem,
                "max_boylam": max_boylam,
                "max_enlem": max_enlem,
            },

            "merkez": {
                "enlem": merkez_enlem,
                "boylam": merkez_boylam,
            },
        },

        "gorsel": {
            "png_goreli_yolu": satir[
                "png_relative_path"
            ],

            "goruntu_url": (
                goruntu_url
            ),
        },

        "detay_url": detay_url,

        "guncellenme_zamani_utc": satir[
            "patch_updated_at_utc"
        ],
    }


# ==========================================================
# UYDU VERİSİ BULUNAN İLÇELER
# ==========================================================

@router.get(
    "/api/uydu-ilceler",
    name="uydu_ilceleri",
)
def uydu_ilcelerini_getir():
    """
    Uydu görüntüsü verisi bulunan ilçeleri ve
    yama sayılarını listeler.
    """

    with baglanti_olustur() as baglanti:
        uydu_tablolarini_kontrol_et(
            baglanti
        )

        sonuclar = baglanti.execute(
            """
            SELECT
                satellite_patches.district_name
                    AS district_name,

                satellite_patches.district_slug
                    AS district_slug,

                COUNT(*)
                    AS patch_count,

                SUM(
                    CASE
                        WHEN satellite_patches.analysis_ready = 1
                        THEN 1
                        ELSE 0
                    END
                )
                    AS ready_patch_count,

                satellite_scenes.item_id
                    AS main_scene_item_id,

                satellite_scenes.acquisition_datetime_utc
                    AS acquisition_datetime_utc,

                satellite_scenes.cloud_cover_pct
                    AS cloud_cover_pct,

                satellite_scenes.platform
                    AS platform,

                MAX(
                    satellite_patches.updated_at_utc
                )
                    AS updated_at_utc

            FROM satellite_patches

            LEFT JOIN satellite_scenes
                ON satellite_scenes.district_slug =
                   satellite_patches.district_slug

               AND satellite_scenes.is_current = 1

            GROUP BY
                satellite_patches.district_name,
                satellite_patches.district_slug,
                satellite_scenes.item_id,
                satellite_scenes.acquisition_datetime_utc,
                satellite_scenes.cloud_cover_pct,
                satellite_scenes.platform

            ORDER BY
                satellite_patches.district_name;
            """
        ).fetchall()

    ilceler = [
        {
            "ilce": satir[
                "district_name"
            ],

            "ilce_slug": satir[
                "district_slug"
            ],

            "toplam_yama": satir[
                "patch_count"
            ],

            "analize_hazir_yama": satir[
                "ready_patch_count"
            ],

            "ana_sahne_id": satir[
                "main_scene_item_id"
            ],

            "goruntu_tarihi_utc": satir[
                "acquisition_datetime_utc"
            ],

            "bulut_orani_yuzde": satir[
                "cloud_cover_pct"
            ],

            "platform": satir[
                "platform"
            ],

            "guncellenme_zamani_utc": satir[
                "updated_at_utc"
            ],
        }
        for satir in sonuclar
    ]

    return {
        "toplam_ilce": len(
            ilceler
        ),

        "ilceler": ilceler,
    }


# ==========================================================
# UYDU GÖRÜNTÜLERİNİ LİSTELEME
# ==========================================================

@router.get(
    "/api/uydu-goruntuleri",
    name="uydu_goruntuleri",
)
def uydu_goruntulerini_getir(
    request: Request,

    ilce: str | None = Query(
        default=None,
        description=(
            "Uydu görüntülerinin filtreleneceği "
            "ilçe adı. Örnek: Pendik"
        ),
    ),

    hucre_id: str | None = Query(
        default=None,
        description=(
            "Belirli bir hizmet hücresine göre filtre."
        ),
    ),

    sadece_hazir: bool = Query(
        default=True,
        description=(
            "Yalnızca analize hazır uydu yamalarını döndürür."
        ),
    ),

    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description=(
            "Döndürülecek en fazla uydu yaması."
        ),
    ),
):
    """
    Uydu RGB yamalarını, sahne metadata bilgisini,
    görüntü kalitesini ve doğrudan görüntü adresini
    döndürür.
    """

    kosullar: list[str] = []
    parametreler: list[Any] = []

    if ilce:
        kosullar.append(
            """
            LOWER(
                satellite_patches.district_name
            ) = LOWER(?)
            """
        )

        parametreler.append(
            ilce.strip()
        )

    if hucre_id:
        kosullar.append(
            """
            satellite_patches.cell_id = ?
            """
        )

        parametreler.append(
            hucre_id.strip()
        )

    if sadece_hazir:
        kosullar.append(
            """
            satellite_patches.analysis_ready = 1
            """
        )

    where_metni = ""

    if kosullar:
        where_metni = (
            " WHERE "
            + " AND ".join(
                kosullar
            )
        )

    sql = (
        UYDU_SECIM_ALANLARI
        + where_metni
        + """
        ORDER BY
            satellite_patches.district_name,
            satellite_patches.district_candidate_rank,
            satellite_patches.patch_id

        LIMIT ?;
        """
    )

    parametreler.append(
        limit
    )

    with baglanti_olustur() as baglanti:
        uydu_tablolarini_kontrol_et(
            baglanti
        )

        sonuclar = baglanti.execute(
            sql,
            parametreler,
        ).fetchall()

    yamalar = [
        uydu_kaydini_hazirla(
            satir,
            request,
        )
        for satir in sonuclar
    ]

    return {
        "filtreler": {
            "ilce": ilce,
            "hucre_id": hucre_id,
            "sadece_hazir": sadece_hazir,
            "limit": limit,
        },

        "toplam_kayit": len(
            yamalar
        ),

        "uydu_goruntuleri": yamalar,
    }


# ==========================================================
# TEK UYDU YAMASI DETAYI
# ==========================================================

@router.get(
    "/api/uydu-goruntuleri/{patch_id}",
    name="uydu_yama_detayi",
)
def uydu_yama_detayini_getir(
    patch_id: str,
    request: Request,
):
    """
    Belirli bir uydu yamasının bütün metadata
    ve kalite bilgilerini döndürür.
    """

    patch_id = patch_id.strip()

    if not patch_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Yama kimliği boş bırakılamaz."
            ),
        )

    with baglanti_olustur() as baglanti:
        uydu_tablolarini_kontrol_et(
            baglanti
        )

        sonuclar = baglanti.execute(
            UYDU_SECIM_ALANLARI
            + """
            WHERE satellite_patches.patch_id = ?

            ORDER BY
                satellite_patches.updated_at_utc DESC;
            """,
            (
                patch_id,
            ),
        ).fetchall()

    if not sonuclar:
        raise HTTPException(
            status_code=404,
            detail=(
                f"'{patch_id}' kimlikli uydu "
                "yaması bulunamadı."
            ),
        )

    if len(
        sonuclar
    ) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Aynı yama kimliği birden fazla "
                "ilçede bulundu."
            ),
        )

    return uydu_kaydini_hazirla(
        sonuclar[0],
        request,
    )


# ==========================================================
# UYDU PNG GÖRSELİNİ SUNMA
# ==========================================================

@router.get(
    "/api/uydu-goruntuleri/{patch_id}/gorsel",
    name="uydu_yama_gorseli",
    response_class=FileResponse,
)
def uydu_yama_gorselini_getir(
    patch_id: str,
):
    """
    Uydu yamasının RGB PNG önizlemesini doğrudan
    tarayıcıya gönderir.
    """

    patch_id = patch_id.strip()

    if not patch_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Yama kimliği boş bırakılamaz."
            ),
        )

    with baglanti_olustur() as baglanti:
        uydu_tablolarini_kontrol_et(
            baglanti
        )

        sonuclar = baglanti.execute(
            """
            SELECT
                png_relative_path

            FROM satellite_patches

            WHERE patch_id = ?

            ORDER BY
                updated_at_utc DESC;
            """,
            (
                patch_id,
            ),
        ).fetchall()

    if not sonuclar:
        raise HTTPException(
            status_code=404,
            detail=(
                f"'{patch_id}' kimlikli uydu "
                "yaması bulunamadı."
            ),
        )

    if len(
        sonuclar
    ) > 1:
        raise HTTPException(
            status_code=409,
            detail=(
                "Aynı yama kimliği birden fazla "
                "ilçede bulundu."
            ),
        )

    dosya_yolu = png_dosya_yolunu_bul(
        sonuclar[0][
            "png_relative_path"
        ]
    )

    return FileResponse(
        path=dosya_yolu,
        media_type="image/png",
    )