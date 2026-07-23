from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


# ==========================================================
# PROJE KÖKÜ
# ==========================================================

PROJE_KOKU = Path(__file__).resolve().parents[2]

VARSAYILAN_WORLDCOVER_YILI = 2021


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
    Değerlendirilecek ilçe ve WorldCover yılını
    komut satırından alır.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Kütüphane hizmet ihtiyacı ile arazi "
            "örtüsü bilgisini iki ayrı değerlendirme "
            "ekseni hâlinde sunar."
        )
    )

    parser.add_argument(
        "--ilce",
        required=True,
        help=(
            "Değerlendirilecek ilçe adı. "
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
        default=VARSAYILAN_WORLDCOVER_YILI,
        help=(
            "Kullanılacak WorldCover yılı. "
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
    Türkçe ilçe adını güvenli dosya ve klasör
    adına dönüştürür.

    Örnek:
    Küçükçekmece -> kucukcekmece
    Bağcılar     -> bagcilar
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
    Girdi ve çıktı dosyalarının yollarını oluşturur.
    """

    ilce_uydu_klasoru = (
        PROJE_KOKU
        / "data"
        / "processed"
        / "satellite"
        / ilce_slug
    )

    worldcover_klasoru = (
        ilce_uydu_klasoru
        / f"worldcover_{worldcover_yili}"
    )

    degerlendirme_klasoru = (
        ilce_uydu_klasoru
        / "candidate_evaluation"
    )

    return {
        "worldcover_csv": (
            worldcover_klasoru
            / "worldcover_aday_hucre_ozeti.csv"
        ),

        "degerlendirme_klasoru": (
            degerlendirme_klasoru
        ),

        "degerlendirme_csv": (
            degerlendirme_klasoru
            / "aday_bolge_iki_eksen_degerlendirmesi.csv"
        ),

        "degerlendirme_json": (
            degerlendirme_klasoru
            / "aday_bolge_iki_eksen_degerlendirmesi.json"
        ),

        "degerlendirme_html": (
            PROJE_KOKU
            / "frontend"
            / f"{ilce_slug}_aday_bolge_degerlendirmesi.html"
        ),
    }


# ==========================================================
# WORLDCOVER SONUÇLARINI OKUMA
# ==========================================================

def worldcover_sonuclarini_oku(
    csv_yolu: Path,
) -> pd.DataFrame:
    """
    WorldCover aday hücre sonuçlarını okur
    ve gerekli sütunları doğrular.
    """

    if not csv_yolu.exists():
        raise FileNotFoundError(
            "WorldCover aday sonuç dosyası bulunamadı:\n"
            f"{csv_yolu}\n\n"
            "Önce worldcover_arazi_ortusu_hazirlama.py "
            "dosyasını çalıştır."
        )

    dataframe = pd.read_csv(
        csv_yolu
    )

    gerekli_sutunlar = [
        "cell_id",
        "district_name",
        "district_candidate_rank",
        "nearest_library_name",
        "nearest_library_distance_km",
        "built_up_pct",
        "vegetation_pct",
        "open_bare_pct",
        "water_wetland_pct",
        "worldcover_coverage_pct",
        "dominant_landcover_class",
    ]

    eksik_sutunlar = [
        sutun
        for sutun in gerekli_sutunlar
        if sutun not in dataframe.columns
    ]

    if eksik_sutunlar:
        raise ValueError(
            "WorldCover sonuç dosyasında eksik "
            "sütunlar var:\n"
            + "\n".join(
                eksik_sutunlar
            )
        )

    ihtiyac_sutunu = None

    for sutun in [
        "preliminary_need_score",
        "global_preliminary_score",
    ]:
        if sutun in dataframe.columns:
            ihtiyac_sutunu = sutun
            break

    if ihtiyac_sutunu is None:
        raise ValueError(
            "WorldCover sonuç dosyasında hizmet "
            "ihtiyacı puanı bulunamadı."
        )

    dataframe[
        "service_need_source_column"
    ] = ihtiyac_sutunu

    dataframe[
        "service_need_score"
    ] = pd.to_numeric(
        dataframe[
            ihtiyac_sutunu
        ],
        errors="coerce",
    )

    sayisal_sutunlar = [
        "district_candidate_rank",
        "nearest_library_distance_km",
        "built_up_pct",
        "vegetation_pct",
        "open_bare_pct",
        "water_wetland_pct",
        "worldcover_coverage_pct",
        "service_need_score",
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
            "cell_id",
            "district_candidate_rank",
            "service_need_score",
            "built_up_pct",
            "vegetation_pct",
            "open_bare_pct",
            "water_wetland_pct",
        ]
    ).copy()

    dataframe[
        "district_candidate_rank"
    ] = (
        dataframe[
            "district_candidate_rank"
        ]
        .astype(int)
    )

    if dataframe.empty:
        raise ValueError(
            "Değerlendirilebilecek geçerli aday "
            "hücre bulunamadı."
        )

    return dataframe


# ==========================================================
# HİZMET İHTİYACI SEVİYESİ
# ==========================================================

def hizmet_ihtiyaci_seviyesi(
    puan: float,
) -> str:
    """
    Sayısal hizmet ihtiyacı puanını
    anlaşılır bir seviyeye dönüştürür.
    """

    if puan >= 90:
        return "Çok yüksek"

    if puan >= 75:
        return "Yüksek"

    if puan >= 50:
        return "Orta"

    return "Düşük"


# ==========================================================
# YAPILAŞMA SEVİYESİ
# ==========================================================

def yapilasma_seviyesi(
    oran: float,
) -> str:
    """
    Yapılaşmış alan oranını sözel seviyeye çevirir.
    """

    if oran >= 75:
        return "Çok yoğun"

    if oran >= 50:
        return "Yoğun"

    if oran >= 30:
        return "Orta"

    return "Düşük"


# ==========================================================
# AÇIK ALAN SEVİYESİ
# ==========================================================

def acik_alan_seviyesi(
    oran: float,
) -> str:
    """
    Açık veya çıplak alan oranını
    sözel seviyeye dönüştürür.
    """

    if oran >= 25:
        return "Görece yüksek"

    if oran >= 10:
        return "Orta"

    return "Düşük"


# ==========================================================
# KENTSEL TALEP BAĞLAMI
# ==========================================================

def kentsel_talep_baglami(
    yapilasma_orani: float,
) -> str:
    """
    Yapılaşmış alan oranını kentsel talep bağlamında
    yorumlar.

    Bu değer gerçek nüfus yoğunluğu değildir.
    """

    if yapilasma_orani >= 75:
        return "Kentsel yoğunluk göstergesi güçlü"

    if yapilasma_orani >= 50:
        return "Kentsel yoğunluk göstergesi orta-yüksek"

    if yapilasma_orani >= 30:
        return "Kentsel yoğunluk göstergesi orta"

    return "Kentsel yoğunluk göstergesi düşük"


# ==========================================================
# YER İNCELEME DURUMU
# ==========================================================

def yer_inceleme_durumu_belirle(
    yapilasma_orani: float,
    yesil_alan_orani: float,
    acik_alan_orani: float,
    su_orani: float,
) -> tuple[str, str, int]:
    """
    Arazi örtüsüne göre yer inceleme durumunu belirler.

    Üçüncü değer yalnızca tabloda gruplama ve sıralama
    için kullanılan kategori sırasıdır; uygunluk puanı
    değildir.
    """

    if su_orani >= 10:
        return (
            "Çevresel kısıt kontrolü gerekli",
            (
                "Su veya sulak alan oranı yüksektir. "
                "Çevresel ve teknik inceleme yapılmadan "
                "aday alan olarak değerlendirilmemelidir."
            ),
            5,
        )

    if (
        acik_alan_orani >= 20
        and yesil_alan_orani < 35
    ):
        return (
            "Ön saha ve parsel incelemesine öncelikli",
            (
                "Açık veya çıplak alan oranı görece "
                "yüksektir. Alanın mülkiyet, imar ve "
                "gerçek kullanım durumu araştırılmalıdır."
            ),
            1,
        )

    if yesil_alan_orani >= 35:
        return (
            "Yeşil alan niteliği araştırılmalı",
            (
                "Bitkisel veya yeşil alan oranı yüksektir. "
                "Alan park, tarım, korunan alan veya özel "
                "mülkiyet olabilir."
            ),
            3,
        )

    if acik_alan_orani >= 10:
        return (
            "İkinci düzey saha incelemesi",
            (
                "Orta düzeyde açık alan sinyali vardır. "
                "Parsel ve güncel saha görüntüsüyle "
                "doğrulanmalıdır."
            ),
            2,
        )

    if yapilasma_orani >= 75:
        return (
            "Yer bulunabilirliği sınırlı olabilir",
            (
                "Bölge çok yoğun yapılaşmıştır ve açık "
                "alan oranı düşüktür. Hizmet talebi güçlü "
                "olabilir ancak yeni tesis alanı bulmak "
                "zor olabilir."
            ),
            4,
        )

    return (
        "Ek verilerle değerlendirilmelidir",
        (
            "Arazi örtüsü tek başına güçlü bir yer "
            "inceleme sinyali üretmemektedir. Parsel, "
            "imar ve ulaşım verileri gereklidir."
        ),
        4,
    )


# ==========================================================
# GENEL AÇIKLAMA METNİ
# ==========================================================

def genel_aciklama_olustur(
    hizmet_seviyesi: str,
    talep_baglami: str,
    yer_durumu: str,
    yer_aciklamasi: str,
) -> str:
    """
    İki eksenli değerlendirmeyi tek açıklama
    metninde birleştirir.
    """

    return (
        f"Hizmet ihtiyacı {hizmet_seviyesi.lower()} "
        f"düzeydedir. {talep_baglami}. "
        f"Yer inceleme durumu: {yer_durumu}. "
        f"{yer_aciklamasi} "
        "Bu değerlendirme kesin kütüphane yeri kararı "
        "değildir; güncel nüfus, parsel, mülkiyet, imar, "
        "ulaşım ve saha verileriyle doğrulanmalıdır."
    )


# ==========================================================
# İKİ EKSENLİ DEĞERLENDİRME
# ==========================================================

def adaylari_degerlendir(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Adayları iki ayrı eksende değerlendirir:

    1. Hizmet ihtiyacı
    2. Yer inceleme durumu

    Tek bir birleşik uygunluk puanı oluşturmaz.
    """

    sonuc = dataframe.copy()

    oran_sutunlari = [
        "service_need_score",
        "built_up_pct",
        "vegetation_pct",
        "open_bare_pct",
        "water_wetland_pct",
        "worldcover_coverage_pct",
    ]

    for sutun in oran_sutunlari:
        sonuc[
            sutun
        ] = sonuc[
            sutun
        ].clip(
            lower=0,
            upper=100,
        )

    sonuc[
        "service_need_level"
    ] = sonuc[
        "service_need_score"
    ].map(
        hizmet_ihtiyaci_seviyesi
    )

    sonuc[
        "urbanization_level"
    ] = sonuc[
        "built_up_pct"
    ].map(
        yapilasma_seviyesi
    )

    sonuc[
        "open_area_level"
    ] = sonuc[
        "open_bare_pct"
    ].map(
        acik_alan_seviyesi
    )

    sonuc[
        "urban_demand_context"
    ] = sonuc[
        "built_up_pct"
    ].map(
        kentsel_talep_baglami
    )

    yer_sonuclari = sonuc.apply(
        lambda satir: yer_inceleme_durumu_belirle(
            yapilasma_orani=float(
                satir[
                    "built_up_pct"
                ]
            ),
            yesil_alan_orani=float(
                satir[
                    "vegetation_pct"
                ]
            ),
            acik_alan_orani=float(
                satir[
                    "open_bare_pct"
                ]
            ),
            su_orani=float(
                satir[
                    "water_wetland_pct"
                ]
            ),
        ),
        axis=1,
    )

    sonuc[
        "site_review_status"
    ] = yer_sonuclari.map(
        lambda deger: deger[0]
    )

    sonuc[
        "site_review_explanation"
    ] = yer_sonuclari.map(
        lambda deger: deger[1]
    )

    sonuc[
        "site_review_category_order"
    ] = yer_sonuclari.map(
        lambda deger: deger[2]
    )

    sonuc[
        "evaluation_text"
    ] = sonuc.apply(
        lambda satir: genel_aciklama_olustur(
            hizmet_seviyesi=str(
                satir[
                    "service_need_level"
                ]
            ),
            talep_baglami=str(
                satir[
                    "urban_demand_context"
                ]
            ),
            yer_durumu=str(
                satir[
                    "site_review_status"
                ]
            ),
            yer_aciklamasi=str(
                satir[
                    "site_review_explanation"
                ]
            ),
        ),
        axis=1,
    )

    sonuc = sonuc.sort_values(
        by=[
            "service_need_score",
            "nearest_library_distance_km",
        ],
        ascending=[
            False,
            False,
        ],
    ).reset_index(
        drop=True
    )

    sonuc[
        "service_need_rank"
    ] = range(
        1,
        len(
            sonuc
        ) + 1,
    )

    tercih_edilen_sutunlar = [
        "service_need_rank",
        "cell_id",
        "district_name",
        "district_candidate_rank",
        "nearest_library_name",
        "nearest_library_distance_km",
        "service_need_score",
        "service_need_level",
        "built_up_pct",
        "urbanization_level",
        "urban_demand_context",
        "vegetation_pct",
        "open_bare_pct",
        "open_area_level",
        "water_wetland_pct",
        "worldcover_coverage_pct",
        "dominant_landcover_class",
        "site_review_status",
        "site_review_explanation",
        "site_review_category_order",
        "evaluation_text",
    ]

    return sonuc[
        tercih_edilen_sutunlar
    ].copy()


# ==========================================================
# ÇIKTILARI KAYDETME
# ==========================================================

def ciktilari_kaydet(
    sonuc: pd.DataFrame,
    ilce_adi: str,
    ilce_slug: str,
    worldcover_yili: int,
    yollar: dict[str, Path],
) -> None:
    """
    Değerlendirmeyi CSV ve JSON olarak kaydeder.
    """

    yollar[
        "degerlendirme_klasoru"
    ].mkdir(
        parents=True,
        exist_ok=True,
    )

    sonuc.to_csv(
        yollar[
            "degerlendirme_csv"
        ],
        index=False,
        encoding="utf-8-sig",
    )

    ozet = {
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

        "candidate_count": len(
            sonuc
        ),

        "evaluation_axes": {
            "service_need": (
                "Kütüphane hizmet açığını ve mevcut "
                "aday ihtiyacı sıralamasını gösterir."
            ),

            "site_review": (
                "WorldCover arazi örtüsüne göre hangi "
                "tür ayrıntılı incelemenin gerektiğini "
                "gösteren kategorik değerlendirmedir."
            ),
        },

        "no_combined_score_note": (
            "Hizmet ihtiyacı ile yer bulunabilirliği "
            "farklı planlama soruları olduğu için tek "
            "bir uygunluk puanında birleştirilmemiştir."
        ),

        "important_warning": (
            "Sonuçlar kesin tesis yeri veya yatırım "
            "kararı değildir."
        ),

        "required_future_data": [
            "Güncel nüfus dağılımı",
            "Parsel sınırları",
            "Mülkiyet bilgisi",
            "İmar durumu",
            "Toplu taşıma erişimi",
            "Yol ve yaya erişimi",
            "Güncel saha doğrulaması",
        ],

        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "candidates": sonuc.to_dict(
            orient="records"
        ),
    }

    yollar[
        "degerlendirme_json"
    ].write_text(
        json.dumps(
            ozet,
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8",
    )


# ==========================================================
# HTML KARTLARI
# ==========================================================

def aday_kartlarini_olustur(
    sonuc: pd.DataFrame,
) -> str:
    """
    Her aday için iki eksenli HTML kartı oluşturur.
    """

    kartlar: list[str] = []

    for kayit in sonuc.itertuples():

        kartlar.append(
            f"""
            <article class="candidate-card">

                <div class="card-header">
                    <span class="rank">
                        Hizmet ihtiyacı sırası:
                        {int(kayit.service_need_rank)}
                    </span>

                    <span class="need-score">
                        {float(kayit.service_need_score):.2f}
                    </span>
                </div>

                <h2>
                    {html.escape(str(kayit.cell_id))}
                </h2>

                <div class="axis-grid">

                    <section class="axis-panel">
                        <div class="axis-label">
                            1. Hizmet ihtiyacı
                        </div>

                        <div class="axis-value">
                            {html.escape(str(kayit.service_need_level))}
                        </div>

                        <p>
                            En yakın kütüphaneye
                            <strong>
                                {float(kayit.nearest_library_distance_km):.2f}
                                km
                            </strong>
                            uzaklıktadır.
                        </p>

                        <p>
                            {html.escape(str(kayit.urban_demand_context))}
                        </p>
                    </section>

                    <section class="axis-panel site-panel">
                        <div class="axis-label">
                            2. Yer inceleme durumu
                        </div>

                        <div class="site-status">
                            {html.escape(str(kayit.site_review_status))}
                        </div>

                        <p>
                            {html.escape(
                                str(
                                    kayit.site_review_explanation
                                )
                            )}
                        </p>
                    </section>

                </div>

                <div class="metrics">
                    <div>
                        <span>Yapılaşmış alan</span>

                        <strong>
                            %{float(kayit.built_up_pct):.2f}
                            —
                            {html.escape(str(kayit.urbanization_level))}
                        </strong>
                    </div>

                    <div>
                        <span>Bitkisel / yeşil alan</span>

                        <strong>
                            %{float(kayit.vegetation_pct):.2f}
                        </strong>
                    </div>

                    <div>
                        <span>Açık / çıplak alan</span>

                        <strong>
                            %{float(kayit.open_bare_pct):.2f}
                            —
                            {html.escape(str(kayit.open_area_level))}
                        </strong>
                    </div>

                    <div>
                        <span>Su / sulak alan</span>

                        <strong>
                            %{float(kayit.water_wetland_pct):.2f}
                        </strong>
                    </div>

                    <div>
                        <span>WorldCover kapsaması</span>

                        <strong>
                            %{float(kayit.worldcover_coverage_pct):.2f}
                        </strong>
                    </div>
                </div>

                <div class="evaluation">
                    <strong>Genel açıklama</strong>

                    <p>
                        {html.escape(str(kayit.evaluation_text))}
                    </p>
                </div>

            </article>
            """
        )

    return "".join(
        kartlar
    )


# ==========================================================
# HTML SAYFASI
# ==========================================================

def html_sayfasi_olustur(
    sonuc: pd.DataFrame,
    ilce_adi: str,
    worldcover_yili: int,
    html_yolu: Path,
) -> None:
    """
    İki eksenli değerlendirme sayfasını oluşturur.
    """

    html_yolu.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    kartlar_html = aday_kartlarini_olustur(
        sonuc
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
        İki Eksenli Aday Değerlendirmesi
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
            padding: 36px 24px;
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
            max-width: 930px;
            margin: 0;
            color: #667085;
            line-height: 1.65;
        }}

        main {{
            padding: 28px 24px 50px;
        }}

        .notice {{
            margin-bottom: 24px;
            padding: 17px 19px;
            border-left: 4px solid #d97706;
            border-radius: 9px;
            background: #fffbeb;
            line-height: 1.65;
        }}

        .grid {{
            display: grid;
            gap: 22px;
        }}

        .candidate-card {{
            padding: 21px;
            border: 1px solid #dce3eb;
            border-radius: 15px;
            background: #ffffff;
        }}

        .card-header {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 14px;
        }}

        .rank {{
            padding: 6px 10px;
            border-radius: 999px;
            background: #dbeafe;
            color: #1d4ed8;
            font-size: 12px;
            font-weight: 700;
        }}

        .need-score {{
            display: flex;
            align-items: center;
            justify-content: center;
            min-width: 67px;
            height: 43px;
            padding: 0 10px;
            border-radius: 11px;
            background: #172033;
            color: #ffffff;
            font-size: 17px;
            font-weight: 700;
        }}

        h2 {{
            margin: 18px 0 15px;
            font-size: 23px;
        }}

        .axis-grid {{
            display: grid;
            grid-template-columns:
                repeat(2, minmax(0, 1fr));
            gap: 15px;
            margin-bottom: 18px;
        }}

        .axis-panel {{
            padding: 17px;
            border: 1px solid #dbe5ef;
            border-radius: 12px;
            background: #eff6ff;
        }}

        .site-panel {{
            background: #f8fafc;
        }}

        .axis-label {{
            margin-bottom: 9px;
            color: #667085;
            font-size: 12px;
            font-weight: 700;
            text-transform: uppercase;
        }}

        .axis-value,
        .site-status {{
            margin-bottom: 9px;
            font-size: 18px;
            font-weight: 700;
        }}

        .axis-panel p {{
            margin: 6px 0 0;
            color: #475467;
            font-size: 13px;
            line-height: 1.55;
        }}

        .metrics {{
            display: grid;
            gap: 9px;
        }}

        .metrics div {{
            display: flex;
            justify-content: space-between;
            gap: 15px;
            padding-top: 9px;
            border-top: 1px solid #edf1f5;
            font-size: 13px;
        }}

        .metrics span {{
            color: #667085;
        }}

        .metrics strong {{
            max-width: 60%;
            text-align: right;
        }}

        .evaluation {{
            margin-top: 18px;
            padding: 15px;
            border-radius: 10px;
            background: #f8fafc;
            line-height: 1.6;
        }}

        .evaluation p {{
            margin: 8px 0 0;
            color: #475467;
            font-size: 13px;
        }}

        @media (max-width: 700px) {{
            .axis-grid {{
                grid-template-columns: 1fr;
            }}
        }}

        @media (max-width: 520px) {{
            .metrics div {{
                flex-direction: column;
            }}

            .metrics strong {{
                max-width: none;
                text-align: left;
            }}
        }}
    </style>
</head>

<body>
    <header>
        <div class="container">
            <h1>
                {html.escape(ilce_adi)}
                İki Eksenli Aday Bölge Değerlendirmesi
            </h1>

            <p class="subtitle">
                Kütüphane hizmet ihtiyacı ile
                {worldcover_yili} yılı arazi örtüsü
                bilgileri ayrı planlama soruları olarak
                değerlendirilmiştir. Tek bir uygunluk
                puanı üretilmemiştir.
            </p>
        </div>
    </header>

    <main class="container">

        <section class="notice">
            <strong>Hizmet ihtiyacı</strong>, bölgede
            kütüphane hizmet açığının gücünü gösterir.

            <br><br>

            <strong>Yer inceleme durumu</strong>, arazinin
            doğrudan uygun olduğunu değil, sonraki aşamada
            hangi tür saha, parsel, imar veya çevresel
            kontrolün gerektiğini gösterir.
        </section>

        <section class="grid">
            {kartlar_html}
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
    sonuc: pd.DataFrame,
    ilce_adi: str,
    yollar: dict[str, Path],
) -> None:
    """
    İki eksenli değerlendirmeyi terminalde özetler.
    """

    print()
    print("=" * 95)
    print("İKİ EKSENLİ ADAY BÖLGE DEĞERLENDİRMESİ TAMAMLANDI")
    print("=" * 95)

    print()
    print(
        "İlçe:",
        ilce_adi,
    )

    print(
        "Değerlendirilen aday:",
        len(
            sonuc
        ),
    )

    print()
    print(
        "Hizmet ihtiyacı ve yer inceleme sonuçları:"
    )

    for kayit in sonuc.itertuples():

        print()
        print(
            f"  {int(kayit.service_need_rank)}. hizmet "
            f"ihtiyacı sırası — {kayit.cell_id}"
        )

        print(
            f"    Hizmet ihtiyacı: "
            f"{kayit.service_need_level} "
            f"({kayit.service_need_score:.2f})"
        )

        print(
            f"    Kütüphaneye uzaklık: "
            f"{kayit.nearest_library_distance_km:.2f} km"
        )

        print(
            f"    Yer inceleme durumu: "
            f"{kayit.site_review_status}"
        )

        print(
            f"    Yapılaşmış alan: "
            f"%{kayit.built_up_pct:.2f}"
        )

        print(
            f"    Açık alan: "
            f"%{kayit.open_bare_pct:.2f}"
        )

    print()
    print(
        "Değerlendirme CSV:"
    )

    print(
        f"  {yollar['degerlendirme_csv']}"
    )

    print()
    print(
        "Değerlendirme JSON:"
    )

    print(
        f"  {yollar['degerlendirme_json']}"
    )

    print()
    print(
        "Değerlendirme sayfası:"
    )

    print(
        f"  {yollar['degerlendirme_html']}"
    )

    print()
    print("=" * 95)


# ==========================================================
# ANA PROGRAM
# ==========================================================

def main() -> None:
    """
    Seçilen ilçe için iki eksenli aday
    bölge değerlendirmesi oluşturur.
    """

    argumanlar = argumanlari_oku()

    ilce_adi = argumanlar.ilce

    ilce_slug = slug_olustur(
        ilce_adi
    )

    yollar = dosya_yollarini_olustur(
        ilce_slug,
        argumanlar.yil,
    )

    print()
    print(
        "Analiz ayarları:"
    )

    print(
        f"  İlçe: {ilce_adi}"
    )

    print(
        f"  WorldCover yılı: {argumanlar.yil}"
    )

    print()
    print(
        "Hizmet ihtiyacı ve arazi örtüsü "
        "sonuçları okunuyor..."
    )

    worldcover_sonuclari = (
        worldcover_sonuclarini_oku(
            yollar[
                "worldcover_csv"
            ]
        )
    )

    print(
        "Adaylar iki ayrı eksende değerlendiriliyor..."
    )

    sonuc = adaylari_degerlendir(
        worldcover_sonuclari
    )

    print(
        "Değerlendirme sonuçları kaydediliyor..."
    )

    ciktilari_kaydet(
        sonuc,
        ilce_adi,
        ilce_slug,
        argumanlar.yil,
        yollar,
    )

    print(
        "İki eksenli değerlendirme sayfası oluşturuluyor..."
    )

    html_sayfasi_olustur(
        sonuc,
        ilce_adi,
        argumanlar.yil,
        yollar[
            "degerlendirme_html"
        ],
    )

    terminal_ozetini_yazdir(
        sonuc,
        ilce_adi,
        yollar,
    )


if __name__ == "__main__":
    main()