from pathlib import Path
import sqlite3


# --------------------------------------------------
# VERİ TABANI YOLU
# --------------------------------------------------

veritabani_yolu = Path(
    "data/database/urbanai.db"
)


# --------------------------------------------------
# VERİ TABANI BAĞLANTISI
# --------------------------------------------------

def baglanti_olustur():

    if not veritabani_yolu.exists():
        raise FileNotFoundError(
            f"Veri tabanı bulunamadı: "
            f"{veritabani_yolu}"
        )

    baglanti = sqlite3.connect(
        veritabani_yolu
    )

    baglanti.execute(
        "PRAGMA foreign_keys = ON;"
    )

    return baglanti


# --------------------------------------------------
# TABLO KAYIT SAYILARI
# --------------------------------------------------

def tablo_sayilarini_goster(baglanti):

    tablolar = [
        "districts",
        "service_types",
        "facilities",
        "district_metrics",
    ]

    print("TABLO KAYIT SAYILARI")
    print("-" * 35)

    for tablo in tablolar:

        sorgu = (
            f"SELECT COUNT(*) FROM {tablo};"
        )

        kayit_sayisi = baglanti.execute(
            sorgu
        ).fetchone()[0]

        print(
            f"{tablo:<20} "
            f"{kayit_sayisi}"
        )


# --------------------------------------------------
# KOORDİNAT DURUMLARI
# --------------------------------------------------

def koordinat_durumlarini_goster(
    baglanti
):

    sonuclar = baglanti.execute(
        """
        SELECT
            coordinate_status,
            COUNT(*)

        FROM facilities

        GROUP BY coordinate_status

        ORDER BY coordinate_status;
        """
    ).fetchall()

    print("\nKOORDİNAT DURUMLARI")
    print("-" * 35)

    for durum, sayi in sonuclar:
        print(
            f"{durum:<20} "
            f"{sayi}"
        )


# --------------------------------------------------
# ÖNCELİKLİ İLÇELER
# --------------------------------------------------

def oncelikli_ilceleri_goster(
    baglanti
):

    sonuclar = baglanti.execute(
        """
        SELECT
            district_metrics.priority_rank,
            districts.name,
            district_metrics.population,
            district_metrics.facility_count,
            district_metrics.priority_score,
            district_metrics.priority_level

        FROM district_metrics

        INNER JOIN districts
            ON districts.id =
               district_metrics.district_id

        WHERE district_metrics.priority_score
              IS NOT NULL

        ORDER BY
            district_metrics.priority_rank

        LIMIT 10;
        """
    ).fetchall()

    print("\nÖNCELİKLİ İLK 10 İLÇE")
    print("-" * 75)

    for (
        sira,
        ilce,
        nufus,
        kutuphane_sayisi,
        puan,
        seviye,
    ) in sonuclar:

        print(
            f"{sira:>2}. "
            f"{ilce:<18} | "
            f"Nüfus: {nufus:>8,} | "
            f"Kütüphane: {kutuphane_sayisi:>2} | "
            f"Puan: {puan:>6.3f} | "
            f"{seviye}"
        )


# --------------------------------------------------
# VERİ DOĞRULAMASI GEREKEN İLÇELER
# --------------------------------------------------

def dogrulama_gereken_ilceleri_goster(
    baglanti
):

    sonuclar = baglanti.execute(
        """
        SELECT
            districts.name,
            district_metrics.population,
            district_metrics.facility_count,
            district_metrics.data_status

        FROM district_metrics

        INNER JOIN districts
            ON districts.id =
               district_metrics.district_id

        WHERE district_metrics.priority_score
              IS NULL

        ORDER BY districts.name;
        """
    ).fetchall()

    print(
        "\nVERİ DOĞRULAMASI GEREKEN İLÇELER"
    )

    print("-" * 60)

    for (
        ilce,
        nufus,
        kutuphane_sayisi,
        veri_durumu,
    ) in sonuclar:

        print(
            f"{ilce:<18} | "
            f"Nüfus: {nufus:>8,} | "
            f"Kayıt: {kutuphane_sayisi} | "
            f"{veri_durumu}"
        )


# --------------------------------------------------
# ANA ÇALIŞMA
# --------------------------------------------------

def main():

    with baglanti_olustur() as baglanti:

        tablo_sayilarini_goster(
            baglanti
        )

        koordinat_durumlarini_goster(
            baglanti
        )

        oncelikli_ilceleri_goster(
            baglanti
        )

        dogrulama_gereken_ilceleri_goster(
            baglanti
        )


if __name__ == "__main__":
    main()