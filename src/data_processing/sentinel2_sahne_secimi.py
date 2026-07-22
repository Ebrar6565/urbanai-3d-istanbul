from __future__ import annotations

import argparse
import json
import re
import unicodedata

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pystac_client


# ==========================================================
# PROJE YOLLARI
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]


# ==========================================================
# STAC AYARLARI
# ==========================================================

STAC_API_ADRESI = (
    "https://planetarycomputer.microsoft.com/api/stac/v1"
)

KOLEKSIYON_ADI = "sentinel-2-l2a"


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
    Sentinel-2 sahne arama ayarlarını
    komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Seçilen ilçe için uygun Sentinel-2 "
            "L2A uydu sahnesini arar ve seçer."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help=(
            "Uydu sahnesi seçilecek ilçe. "
            "Örnek: Esenyurt"
        ),
    )

    parser.add_argument(
        "--arama-gun-sayisi",
        type=int,
        default=550,
        help=(
            "Bugünden geriye doğru aranacak gün sayısı. "
            "Varsayılan: 550"
        ),
    )

    parser.add_argument(
        "--bulut-esigi",
        type=float,
        default=20.0,
        help=(
            "İlk aramada kullanılacak en yüksek "
            "bulut oranı. Varsayılan: 20"
        ),
    )

    parser.add_argument(
        "--yedek-bulut-esigi",
        type=float,
        default=40.0,
        help=(
            "İlk aramada sonuç bulunamazsa kullanılacak "
            "yedek bulut eşiği. Varsayılan: 40"
        ),
    )

    parser.add_argument(
        "--cok-dusuk-bulut-esigi",
        type=float,
        default=1.0,
        help=(
            "Bu oranın altındaki sahneler pratikte çok "
            "düşük bulutlu kabul edilir. Bu sahneler "
            "arasından en yenisi seçilir. Varsayılan: 1"
        ),
    )

    parser.add_argument(
        "--maksimum-sahne",
        type=int,
        default=50,
        help=(
            "STAC servisinden alınacak en fazla sahne "
            "sayısı. Varsayılan: 50"
        ),
    )

    argumanlar = parser.parse_args()

    argumanlar.ilce = argumanlar.ilce.strip()

    if not argumanlar.ilce:
        parser.error(
            "--ilce değeri boş bırakılamaz."
        )

    if argumanlar.arama_gun_sayisi <= 0:
        parser.error(
            "--arama-gun-sayisi sıfırdan büyük olmalıdır."
        )

    if argumanlar.bulut_esigi <= 0:
        parser.error(
            "--bulut-esigi sıfırdan büyük olmalıdır."
        )

    if argumanlar.yedek_bulut_esigi <= 0:
        parser.error(
            "--yedek-bulut-esigi sıfırdan büyük olmalıdır."
        )

    if argumanlar.cok_dusuk_bulut_esigi < 0:
        parser.error(
            "--cok-dusuk-bulut-esigi negatif olamaz."
        )

    if argumanlar.maksimum_sahne <= 0:
        parser.error(
            "--maksimum-sahne sıfırdan büyük olmalıdır."
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
    Seçilen ilçeye ait girdi ve çıktı
    dosya yollarını oluşturur.
    """

    islenmis_klasor = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
    )

    return {
        "islenmis_klasor": islenmis_klasor,

        "bbox_csv": (
            islenmis_klasor
            / "pilot_uydu_bbox.csv"
        ),

        "pilot_ayarlar_json": (
            islenmis_klasor
            / "pilot_ayarlar.json"
        ),

        "sahne_adaylari_csv": (
            islenmis_klasor
            / "sentinel2_sahne_adaylari.csv"
        ),

        "secilen_sahne_json": (
            islenmis_klasor
            / "secilen_sentinel2_sahnesi.json"
        ),
    }


# ==========================================================
# PİLOT AYARLARINI OKUMA
# ==========================================================

def pilot_ayarlarini_oku(
    ayarlar_yolu: Path,
) -> dict[str, Any]:
    """
    Pilot alan hazırlama aşamasında kaydedilen
    ayar dosyasını okur.
    """

    if not ayarlar_yolu.exists():
        return {}

    try:
        return json.loads(
            ayarlar_yolu.read_text(
                encoding="utf-8"
            )
        )

    except json.JSONDecodeError:
        return {}


# ==========================================================
# BİRLEŞİK BBOX HESAPLAMA
# ==========================================================

def birlesik_bbox_oku(
    bbox_csv_yolu: Path,
) -> list[float]:
    """
    İlçedeki bütün pilot yamaları kapsayan
    tek bir sınır kutusu oluşturur.

    Sıra:
    min_boylam, min_enlem, max_boylam, max_enlem
    """

    if not bbox_csv_yolu.exists():
        raise FileNotFoundError(
            "İlçeye ait pilot BBOX dosyası bulunamadı:\n"
            f"{bbox_csv_yolu}\n\n"
            "Önce pilot_uydu_alanlari_hazirlama.py "
            "dosyasını bu ilçe için çalıştır."
        )

    bbox_dataframe = pd.read_csv(
        bbox_csv_yolu
    )

    gerekli_sutunlar = [
        "min_longitude",
        "min_latitude",
        "max_longitude",
        "max_latitude",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in bbox_dataframe.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "BBOX dosyasında eksik sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    for sutun in gerekli_sutunlar:

        bbox_dataframe[
            sutun
        ] = pd.to_numeric(
            bbox_dataframe[
                sutun
            ],
            errors="coerce",
        )

    bbox_dataframe = bbox_dataframe.dropna(
        subset=gerekli_sutunlar
    )

    if bbox_dataframe.empty:
        raise ValueError(
            "BBOX dosyasında geçerli koordinat bulunamadı."
        )

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
# STAC KATALOĞUNA BAĞLANMA
# ==========================================================

def stac_kataloguna_baglan():
    """
    Planetary Computer STAC kataloğuna bağlanır.
    """

    return pystac_client.Client.open(
        STAC_API_ADRESI
    )


# ==========================================================
# SENTINEL-2 SAHNELERİNİ ARAMA
# ==========================================================

def sahneleri_ara(
    katalog,
    bbox: list[float],
    arama_gun_sayisi: int,
    bulut_esigi: float,
    maksimum_sahne: int,
) -> list[Any]:
    """
    Tarih, BBOX ve bulut oranına göre
    Sentinel-2 L2A sahnelerini arar.
    """

    bitis_zamani = datetime.now(
        timezone.utc
    )

    baslangic_zamani = (
        bitis_zamani
        - timedelta(
            days=arama_gun_sayisi
        )
    )

    tarih_araligi = (
        f"{baslangic_zamani:%Y-%m-%d}"
        "/"
        f"{bitis_zamani:%Y-%m-%d}"
    )

    arama = katalog.search(
        collections=[
            KOLEKSIYON_ADI,
        ],
        bbox=bbox,
        datetime=tarih_araligi,
        query={
            "eo:cloud_cover": {
                "lt": bulut_esigi,
            }
        },
        max_items=maksimum_sahne,
    )

    return list(
        arama.items()
    )


# ==========================================================
# SAHNE TABLOSU OLUŞTURMA
# ==========================================================

def sahne_tablosu_olustur(
    sahneler: list[Any],
) -> pd.DataFrame:
    """
    Sentinel-2 sahne metadata bilgilerini
    karşılaştırılabilir tabloya dönüştürür.
    """

    kayitlar: list[
        dict[str, Any]
    ] = []

    for sahne in sahneler:

        ozellikler = sahne.properties

        goruntu_tarihi = (
            sahne.datetime
            or ozellikler.get(
                "datetime"
            )
        )

        bulut_orani = ozellikler.get(
            "eo:cloud_cover"
        )

        nodata_orani = ozellikler.get(
            "s2:nodata_pixel_percentage"
        )

        kayitlar.append(
            {
                "item_id": str(
                    sahne.id
                ),

                "datetime": (
                    goruntu_tarihi.isoformat()
                    if hasattr(
                        goruntu_tarihi,
                        "isoformat",
                    )
                    else str(
                        goruntu_tarihi
                    )
                ),

                "cloud_cover_pct": (
                    float(
                        bulut_orani
                    )
                    if bulut_orani is not None
                    else None
                ),

                "platform": (
                    ozellikler.get(
                        "platform"
                    )
                ),

                "nodata_pixel_pct": (
                    float(
                        nodata_orani
                    )
                    if nodata_orani is not None
                    else None
                ),

                "asset_count": len(
                    sahne.assets
                ),

                "asset_keys": ",".join(
                    sorted(
                        sahne.assets.keys()
                    )
                ),
            }
        )

    dataframe = pd.DataFrame(
        kayitlar
    )

    if dataframe.empty:
        return dataframe

    dataframe[
        "datetime_parsed"
    ] = pd.to_datetime(
        dataframe[
            "datetime"
        ],
        errors="coerce",
        utc=True,
    )

    dataframe[
        "cloud_cover_pct"
    ] = pd.to_numeric(
        dataframe[
            "cloud_cover_pct"
        ],
        errors="coerce",
    )

    dataframe = dataframe.dropna(
        subset=[
            "item_id",
            "datetime_parsed",
            "cloud_cover_pct",
        ]
    ).copy()

    return dataframe


# ==========================================================
# NİHAİ SAHNEYİ SEÇME
# ==========================================================

def nihai_sahneyi_sec(
    sahne_tablosu: pd.DataFrame,
    cok_dusuk_bulut_esigi: float,
) -> tuple[
    pd.DataFrame,
    pd.Series,
    str,
]:
    """
    Çok düşük bulutlu sahneler arasından
    en yeni olanı seçer.

    Çok düşük bulutlu sahne yoksa önce
    en düşük bulut oranını tercih eder.
    """

    if sahne_tablosu.empty:
        raise ValueError(
            "Seçilebilecek Sentinel-2 sahnesi bulunamadı."
        )

    cok_acik_sahneler = sahne_tablosu[
        sahne_tablosu[
            "cloud_cover_pct"
        ]
        <= cok_dusuk_bulut_esigi
    ].copy()

    if not cok_acik_sahneler.empty:

        sirali_tablo = (
            sahne_tablosu
            .assign(
                very_low_cloud=(
                    sahne_tablosu[
                        "cloud_cover_pct"
                    ]
                    <= cok_dusuk_bulut_esigi
                )
            )
            .sort_values(
                by=[
                    "very_low_cloud",
                    "datetime_parsed",
                    "cloud_cover_pct",
                ],
                ascending=[
                    False,
                    False,
                    True,
                ],
            )
            .reset_index(
                drop=True
            )
        )

        secim_yontemi = (
            f"Bulut oranı %{cok_dusuk_bulut_esigi} "
            "ve altında olan sahneler arasından "
            "en yeni tarih seçildi."
        )

    else:

        sirali_tablo = (
            sahne_tablosu
            .assign(
                very_low_cloud=False
            )
            .sort_values(
                by=[
                    "cloud_cover_pct",
                    "datetime_parsed",
                ],
                ascending=[
                    True,
                    False,
                ],
            )
            .reset_index(
                drop=True
            )
        )

        secim_yontemi = (
            "Çok düşük bulutlu sahne bulunamadığı için "
            "önce en düşük bulut oranı, eşit durumda "
            "en yeni tarih seçildi."
        )

    sirali_tablo[
        "selection_rank"
    ] = range(
        1,
        len(
            sirali_tablo
        ) + 1,
    )

    secilen_sahne = (
        sirali_tablo.iloc[0]
    )

    return (
        sirali_tablo,
        secilen_sahne,
        secim_yontemi,
    )


# ==========================================================
# ÇIKTILARI KAYDETME
# ==========================================================

def ciktilari_kaydet(
    sirali_tablo: pd.DataFrame,
    secilen_sahne: pd.Series,
    secim_yontemi: str,
    ilce_adi: str,
    ilce_slug: str,
    birlesik_bbox: list[float],
    kullanilan_bulut_esigi: float,
    cok_dusuk_bulut_esigi: float,
    arama_gun_sayisi: int,
    pilot_ayarlari: dict[str, Any],
    yollar: dict[str, Path],
) -> None:
    """
    Sahne adaylarını CSV, seçilen sahneyi
    JSON dosyası olarak kaydeder.
    """

    yollar[
        "islenmis_klasor"
    ].mkdir(
        parents=True,
        exist_ok=True,
    )

    kaydedilecek_tablo = (
        sirali_tablo
        .drop(
            columns=[
                "datetime_parsed",
            ],
            errors="ignore",
        )
    )

    kaydedilecek_tablo.to_csv(
        yollar[
            "sahne_adaylari_csv"
        ],
        index=False,
        encoding="utf-8-sig",
    )

    platform_degeri = (
        None
        if pd.isna(
            secilen_sahne[
                "platform"
            ]
        )
        else str(
            secilen_sahne[
                "platform"
            ]
        )
    )

    metadata = {
        "project": (
            "UrbanAI 3D İstanbul"
        ),

        "district_name": ilce_adi,

        "district_slug": ilce_slug,

        "collection": KOLEKSIYON_ADI,

        "item_id": str(
            secilen_sahne[
                "item_id"
            ]
        ),

        "datetime": (
            secilen_sahne[
                "datetime_parsed"
            ].isoformat()
        ),

        "cloud_cover_pct": float(
            secilen_sahne[
                "cloud_cover_pct"
            ]
        ),

        "platform": platform_degeri,

        "nodata_pixel_pct": (
            None
            if pd.isna(
                secilen_sahne[
                    "nodata_pixel_pct"
                ]
            )
            else float(
                secilen_sahne[
                    "nodata_pixel_pct"
                ]
            )
        ),

        "selection_method": (
            secim_yontemi
        ),

        "search_bbox": (
            birlesik_bbox
        ),

        "search_days": (
            arama_gun_sayisi
        ),

        "cloud_threshold_used": (
            kullanilan_bulut_esigi
        ),

        "very_low_cloud_threshold": (
            cok_dusuk_bulut_esigi
        ),

        "candidate_scene_count": len(
            sirali_tablo
        ),

        "required_rgb_assets": [
            "B04",
            "B03",
            "B02",
        ],

        "cloud_cover_note": (
            "Bulut oranı Sentinel-2 sahnesinin metadata "
            "değeridir. Pilot alanlar RGB görüntüler "
            "üretildikten sonra ayrıca görsel olarak "
            "kontrol edilmelidir."
        ),

        "pilot_settings": (
            pilot_ayarlari
        ),

        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
    }

    yollar[
        "secilen_sahne_json"
    ].write_text(
        json.dumps(
            metadata,
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
    ilce_slug: str,
    birlesik_bbox: list[float],
    kullanilan_bulut_esigi: float,
    sirali_tablo: pd.DataFrame,
    secilen_sahne: pd.Series,
    secim_yontemi: str,
    yollar: dict[str, Path],
) -> None:
    """
    Seçilen sahneyi terminalde özetler.
    """

    print()
    print("=" * 95)
    print("SENTINEL-2 UYDU SAHNESİ SEÇİLDİ")
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
        "Birleşik sorgu BBOX:",
        birlesik_bbox,
    )

    print(
        "Kullanılan bulut eşiği:",
        f"%{kullanilan_bulut_esigi}",
    )

    print(
        "Bulunan geçerli sahne sayısı:",
        len(
            sirali_tablo
        ),
    )

    print()
    print(
        "Seçim yöntemi:"
    )

    print(
        " ",
        secim_yontemi,
    )

    print()
    print(
        "Seçilen sahne:"
    )

    print(
        "  Item ID:",
        secilen_sahne[
            "item_id"
        ],
    )

    print(
        "  Tarih:",
        secilen_sahne[
            "datetime_parsed"
        ].isoformat(),
    )

    print(
        "  Bulut oranı:",
        f"%{secilen_sahne['cloud_cover_pct']:.6f}",
    )

    print(
        "  Platform:",
        secilen_sahne[
            "platform"
        ],
    )

    print()
    print(
        "Seçim sırasındaki ilk 5 sahne:"
    )

    gosterilecek_sutunlar = [
        "selection_rank",
        "datetime",
        "cloud_cover_pct",
        "platform",
        "item_id",
    ]

    print(
        sirali_tablo[
            gosterilecek_sutunlar
        ]
        .head(5)
        .to_string(
            index=False
        )
    )

    print()
    print(
        "Sahne adayları CSV:"
    )

    print(
        f"  {yollar['sahne_adaylari_csv']}"
    )

    print()
    print(
        "Seçilen sahne metadata:"
    )

    print(
        f"  {yollar['secilen_sahne_json']}"
    )

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    Seçilen ilçe için en uygun Sentinel-2
    sahnesini arar, sıralar ve kaydeder.
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
        f"  Arama süresi: "
        f"{argumanlar.arama_gun_sayisi} gün"
    )

    print(
        f"  Bulut eşiği: "
        f"%{argumanlar.bulut_esigi}"
    )

    print(
        f"  Çok düşük bulut eşiği: "
        f"%{argumanlar.cok_dusuk_bulut_esigi}"
    )

    print()
    print(
        "Pilot alanların birleşik BBOX değeri okunuyor..."
    )

    birlesik_bbox = birlesik_bbox_oku(
        yollar[
            "bbox_csv"
        ]
    )

    pilot_ayarlari = pilot_ayarlarini_oku(
        yollar[
            "pilot_ayarlar_json"
        ]
    )

    print(
        "Planetary Computer STAC kataloğuna bağlanılıyor..."
    )

    katalog = stac_kataloguna_baglan()

    print(
        f"%{argumanlar.bulut_esigi} bulut eşiğiyle "
        "Sentinel-2 sahneleri aranıyor..."
    )

    sahneler = sahneleri_ara(
        katalog,
        birlesik_bbox,
        argumanlar.arama_gun_sayisi,
        argumanlar.bulut_esigi,
        argumanlar.maksimum_sahne,
    )

    kullanilan_bulut_esigi = (
        argumanlar.bulut_esigi
    )

    if not sahneler:

        print(
            f"%{argumanlar.bulut_esigi} altında "
            "sahne bulunamadı."
        )

        print(
            f"Arama eşiği "
            f"%{argumanlar.yedek_bulut_esigi} "
            "olarak genişletiliyor..."
        )

        sahneler = sahneleri_ara(
            katalog,
            birlesik_bbox,
            argumanlar.arama_gun_sayisi,
            argumanlar.yedek_bulut_esigi,
            argumanlar.maksimum_sahne,
        )

        kullanilan_bulut_esigi = (
            argumanlar.yedek_bulut_esigi
        )

    if not sahneler:
        raise RuntimeError(
            "Belirlenen tarih aralığında uygun "
            "Sentinel-2 sahnesi bulunamadı."
        )

    print(
        "Sahne metadata tablosu hazırlanıyor..."
    )

    sahne_tablosu = sahne_tablosu_olustur(
        sahneler
    )

    print(
        "Nihai Sentinel-2 sahnesi seçiliyor..."
    )

    (
        sirali_tablo,
        secilen_sahne,
        secim_yontemi,
    ) = nihai_sahneyi_sec(
        sahne_tablosu,
        argumanlar.cok_dusuk_bulut_esigi,
    )

    print(
        "Sahne seçim sonuçları kaydediliyor..."
    )

    ciktilari_kaydet(
        sirali_tablo,
        secilen_sahne,
        secim_yontemi,
        ilce_adi,
        ilce_slug,
        birlesik_bbox,
        kullanilan_bulut_esigi,
        argumanlar.cok_dusuk_bulut_esigi,
        argumanlar.arama_gun_sayisi,
        pilot_ayarlari,
        yollar,
    )

    terminal_ozetini_yazdir(
        ilce_adi,
        ilce_slug,
        birlesik_bbox,
        kullanilan_bulut_esigi,
        sirali_tablo,
        secilen_sahne,
        secim_yontemi,
        yollar,
    )


if __name__ == "__main__":
    main()
