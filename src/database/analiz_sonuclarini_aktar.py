from pathlib import Path
import sqlite3

import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

veritabani_yolu = Path(
    "data/database/urbanai.db"
)

ilce_analiz_yolu = Path(
    "data/processed/ilce_kutuphane_analizi.csv"
)

oncelik_puani_yolu = Path(
    "data/processed/ilce_oncelik_puanlari.csv"
)


# --------------------------------------------------
# VERİLERİ OKU
# --------------------------------------------------

ilce_analizi = pd.read_csv(
    ilce_analiz_yolu
)

oncelik_puanlari = pd.read_csv(
    oncelik_puani_yolu
)


# --------------------------------------------------
# GEREKLİ SÜTUNLARI KONTROL ET
# --------------------------------------------------

gerekli_analiz_sutunlari = {
    "İlçe",
    "Toplam Nüfus",
    "Kütüphane Sayısı",
    "100 Bin Kişiye Düşen Kütüphane",
    "Bir Kütüphaneye Düşen Kişi",
    "Veri Durumu",
}

gerekli_oncelik_sutunlari = {
    "İlçe",
    "Öncelik Sırası",
    "Nüfus Puanı",
    "Hizmet Açığı Puanı",
    "Öncelik Puanı",
    "Öncelik Seviyesi",
}


eksik_analiz_sutunlari = (
    gerekli_analiz_sutunlari
    - set(ilce_analizi.columns)
)

eksik_oncelik_sutunlari = (
    gerekli_oncelik_sutunlari
    - set(oncelik_puanlari.columns)
)


if eksik_analiz_sutunlari:
    raise ValueError(
        "İlçe analiz dosyasında eksik sütunlar var: "
        f"{sorted(eksik_analiz_sutunlari)}"
    )


if eksik_oncelik_sutunlari:
    raise ValueError(
        "Öncelik puanı dosyasında eksik sütunlar var: "
        f"{sorted(eksik_oncelik_sutunlari)}"
    )


# --------------------------------------------------
# KAYIT SAYILARINI KONTROL ET
# --------------------------------------------------

if len(ilce_analizi) != 39:
    raise ValueError(
        "İlçe analiz dosyasında 39 ilçe bekleniyordu. "
        f"Bulunan kayıt: {len(ilce_analizi)}"
    )


if len(oncelik_puanlari) != 29:
    raise ValueError(
        "Öncelik puanı dosyasında 29 ilçe "
        "bekleniyordu. "
        f"Bulunan kayıt: {len(oncelik_puanlari)}"
    )


# --------------------------------------------------
# İLÇE ADLARINI TEMİZLE
# --------------------------------------------------

ilce_analizi["İlçe"] = (
    ilce_analizi["İlçe"]
    .astype(str)
    .str.strip()
)

oncelik_puanlari["İlçe"] = (
    oncelik_puanlari["İlçe"]
    .astype(str)
    .str.strip()
)


# Aynı ilçe iki kez bulunmamalı.
if ilce_analizi["İlçe"].duplicated().any():
    tekrarlar = ilce_analizi.loc[
        ilce_analizi["İlçe"].duplicated(
            keep=False
        ),
        "İlçe",
    ].tolist()

    raise ValueError(
        "İlçe analiz dosyasında tekrarlanan "
        f"ilçeler var: {tekrarlar}"
    )


if oncelik_puanlari["İlçe"].duplicated().any():
    tekrarlar = oncelik_puanlari.loc[
        oncelik_puanlari["İlçe"].duplicated(
            keep=False
        ),
        "İlçe",
    ].tolist()

    raise ValueError(
        "Öncelik dosyasında tekrarlanan "
        f"ilçeler var: {tekrarlar}"
    )


# --------------------------------------------------
# ANALİZ VE ÖNCELİK TABLOLARINI BİRLEŞTİR
# --------------------------------------------------

birlesik_veri = ilce_analizi.merge(
    oncelik_puanlari[
        [
            "İlçe",
            "Öncelik Sırası",
            "Nüfus Puanı",
            "Hizmet Açığı Puanı",
            "Öncelik Puanı",
            "Öncelik Seviyesi",
        ]
    ],
    on="İlçe",
    how="left",
    validate="one_to_one",
)


# Birleştirmeden sonra 39 ilçe korunmalı.
if len(birlesik_veri) != 39:
    raise ValueError(
        "Birleştirilmiş tabloda 39 ilçe "
        "bulunamadı."
    )


# İlçe kütüphane sayılarının toplamı,
# facilities tablosuna aktardığımız 72 kayıtla
# aynı olmalı.
toplam_kutuphane_sayisi = int(
    birlesik_veri[
        "Kütüphane Sayısı"
    ].sum()
)

if toplam_kutuphane_sayisi != 72:
    raise ValueError(
        "İlçe kütüphane sayılarının toplamı "
        f"72 değil: {toplam_kutuphane_sayisi}"
    )


# --------------------------------------------------
# SQL İÇİN DEĞER DÖNÜŞTÜRME FONKSİYONLARI
# --------------------------------------------------

def float_veya_none(deger):
    """
    Sayısal değeri float'a dönüştürür.

    Boş veya NaN değerlerde None döndürür.
    Python'daki None, SQLite'ta NULL olur.
    """

    if pd.isna(deger):
        return None

    return float(deger)


def int_veya_none(deger):
    """
    Sayısal değeri tam sayıya dönüştürür.

    Boş veya NaN değerlerde None döndürür.
    """

    if pd.isna(deger):
        return None

    return int(
        float(deger)
    )


def metin_veya_none(deger):
    """
    Boş metin ve NaN değerleri None'a çevirir.
    """

    if pd.isna(deger):
        return None

    temiz_deger = str(deger).strip()

    if temiz_deger == "":
        return None

    return temiz_deger


# --------------------------------------------------
# VERİ TABANI BAĞLANTISI
# --------------------------------------------------

def veritabani_baglantisi_olustur():

    if not veritabani_yolu.exists():
        raise FileNotFoundError(
            "Veri tabanı bulunamadı. Önce "
            "veritabani_olustur.py dosyasını çalıştır."
        )

    baglanti = sqlite3.connect(
        veritabani_yolu
    )

    baglanti.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return baglanti


# --------------------------------------------------
# İLÇE ID DEĞERLERİNİ GETİR
# --------------------------------------------------

def ilce_idlerini_getir(baglanti):

    sonuc = baglanti.execute(
        """
        SELECT
            name,
            id
        FROM districts;
        """
    ).fetchall()

    return {
        ilce_adi: ilce_id
        for ilce_adi, ilce_id in sonuc
    }


# --------------------------------------------------
# KÜTÜPHANE HİZMET TÜRÜ ID DEĞERİNİ GETİR
# --------------------------------------------------

def kutuphane_hizmet_turu_id_getir(
    baglanti
):

    sonuc = baglanti.execute(
        """
        SELECT id
        FROM service_types
        WHERE name = ?;
        """,
        (
            "Kütüphane",
        ),
    ).fetchone()

    if sonuc is None:
        raise ValueError(
            "Kütüphane hizmet türü bulunamadı."
        )

    return sonuc[0]


# --------------------------------------------------
# ANALİZ SONUÇLARINI VERİ TABANINA AKTAR
# --------------------------------------------------

def analiz_sonuclarini_aktar(
    baglanti,
    ilce_idleri,
    hizmet_turu_id,
):

    analiz_ilceleri = set(
        birlesik_veri["İlçe"]
    )

    veritabani_ilceleri = set(
        ilce_idleri.keys()
    )

    eslesmeyen_ilceler = sorted(
        analiz_ilceleri
        - veritabani_ilceleri
    )

    if eslesmeyen_ilceler:
        raise ValueError(
            "Veri tabanında bulunmayan ilçeler var: "
            f"{eslesmeyen_ilceler}"
        )


    islenen_kayit_sayisi = 0

    for _, satir in birlesik_veri.iterrows():

        ilce_adi = satir["İlçe"]

        ilce_id = ilce_idleri[
            ilce_adi
        ]

        oncelik_puani = float_veya_none(
            satir["Öncelik Puanı"]
        )


        # Öncelik puanı bulunmayan ilçeler
        # düşük öncelikli değildir.
        #
        # Bunları veri doğrulaması gereken
        # ilçeler olarak saklıyoruz.
        if oncelik_puani is None:
            oncelik_seviyesi = (
                "Veri doğrulaması gerekli"
            )

            oncelik_sirasi = None

        else:
            oncelik_seviyesi = (
                metin_veya_none(
                    satir["Öncelik Seviyesi"]
                )
            )

            oncelik_sirasi = (
                int_veya_none(
                    satir["Öncelik Sırası"]
                )
            )


        baglanti.execute(
            """
            INSERT INTO district_metrics (
                district_id,
                service_type_id,
                analysis_year,
                population,
                facility_count,
                service_per_100k,
                people_per_facility,
                population_score,
                service_gap_score,
                priority_score,
                priority_level,
                data_status,
                priority_rank
            )
            VALUES (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )

            ON CONFLICT(
                district_id,
                service_type_id,
                analysis_year
            )
            DO UPDATE SET
                population =
                    excluded.population,

                facility_count =
                    excluded.facility_count,

                service_per_100k =
                    excluded.service_per_100k,

                people_per_facility =
                    excluded.people_per_facility,

                population_score =
                    excluded.population_score,

                service_gap_score =
                    excluded.service_gap_score,

                priority_score =
                    excluded.priority_score,

                priority_level =
                    excluded.priority_level,

                data_status =
                    excluded.data_status,

                priority_rank =
                    excluded.priority_rank;
            """,
            (
                ilce_id,
                hizmet_turu_id,
                2025,

                int(
                    satir["Toplam Nüfus"]
                ),

                int(
                    satir["Kütüphane Sayısı"]
                ),

                float_veya_none(
                    satir[
                        "100 Bin Kişiye Düşen Kütüphane"
                    ]
                ),

                int_veya_none(
                    satir[
                        "Bir Kütüphaneye Düşen Kişi"
                    ]
                ),

                float_veya_none(
                    satir["Nüfus Puanı"]
                ),

                float_veya_none(
                    satir[
                        "Hizmet Açığı Puanı"
                    ]
                ),

                oncelik_puani,

                oncelik_seviyesi,

                metin_veya_none(
                    satir["Veri Durumu"]
                ),

                oncelik_sirasi,
            ),
        )

        islenen_kayit_sayisi += 1

    return islenen_kayit_sayisi


# --------------------------------------------------
# SONUÇ ÖZETİNİ GETİR
# --------------------------------------------------

def sonuc_ozetini_getir(
    baglanti,
    hizmet_turu_id,
):

    toplam_kayit = baglanti.execute(
        """
        SELECT COUNT(*)
        FROM district_metrics
        WHERE service_type_id = ?
          AND analysis_year = ?;
        """,
        (
            hizmet_turu_id,
            2025,
        ),
    ).fetchone()[0]


    puanli_ilce_sayisi = baglanti.execute(
        """
        SELECT COUNT(*)
        FROM district_metrics
        WHERE service_type_id = ?
          AND analysis_year = ?
          AND priority_score IS NOT NULL;
        """,
        (
            hizmet_turu_id,
            2025,
        ),
    ).fetchone()[0]


    dogrulama_gereken_sayi = baglanti.execute(
        """
        SELECT COUNT(*)
        FROM district_metrics
        WHERE service_type_id = ?
          AND analysis_year = ?
          AND priority_score IS NULL;
        """,
        (
            hizmet_turu_id,
            2025,
        ),
    ).fetchone()[0]


    oncelikli_ilceler = baglanti.execute(
        """
        SELECT
            districts.name,
            district_metrics.priority_score,
            district_metrics.priority_level,
            district_metrics.priority_rank

        FROM district_metrics

        INNER JOIN districts
            ON districts.id =
               district_metrics.district_id

        WHERE district_metrics.service_type_id = ?
          AND district_metrics.analysis_year = ?
          AND district_metrics.priority_score
              IS NOT NULL

        ORDER BY
            district_metrics.priority_rank ASC

        LIMIT 5;
        """,
        (
            hizmet_turu_id,
            2025,
        ),
    ).fetchall()


    return (
        toplam_kayit,
        puanli_ilce_sayisi,
        dogrulama_gereken_sayi,
        oncelikli_ilceler,
    )


# --------------------------------------------------
# ANA ÇALIŞMA AKIŞI
# --------------------------------------------------

def main():

    with veritabani_baglantisi_olustur() as baglanti:

        ilce_idleri = ilce_idlerini_getir(
            baglanti
        )

        hizmet_turu_id = (
            kutuphane_hizmet_turu_id_getir(
                baglanti
            )
        )

        islenen_kayit_sayisi = (
            analiz_sonuclarini_aktar(
                baglanti,
                ilce_idleri,
                hizmet_turu_id,
            )
        )

        (
            toplam_kayit,
            puanli_ilce_sayisi,
            dogrulama_gereken_sayi,
            oncelikli_ilceler,
        ) = sonuc_ozetini_getir(
            baglanti,
            hizmet_turu_id,
        )


    print(
        f"İşlenen analiz kaydı: "
        f"{islenen_kayit_sayisi}"
    )

    print(
        f"Veri tabanındaki analiz kaydı: "
        f"{toplam_kayit}"
    )

    print(
        f"Öncelik puanı bulunan ilçe: "
        f"{puanli_ilce_sayisi}"
    )

    print(
        f"Veri doğrulaması gereken ilçe: "
        f"{dogrulama_gereken_sayi}"
    )


    print(
        "\nVeri tabanındaki öncelikli ilk 5 ilçe:"
    )

    for (
        ilce_adi,
        oncelik_puani,
        oncelik_seviyesi,
        oncelik_sirasi,
    ) in oncelikli_ilceler:

        print(
            f"- {oncelik_sirasi}. "
            f"{ilce_adi} | "
            f"puan={oncelik_puani:.3f} | "
            f"{oncelik_seviyesi}"
        )


if __name__ == "__main__":
    main()