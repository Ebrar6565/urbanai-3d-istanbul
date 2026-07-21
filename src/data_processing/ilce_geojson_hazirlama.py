from pathlib import Path
import json

import pandas as pd


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

ham_geojson_yolu = Path(
    "data/raw/istanbul_ilce_sinirlari.geojson"
)

ilce_analiz_yolu = Path(
    "data/processed/ilce_kutuphane_analizi.csv"
)

oncelik_puani_yolu = Path(
    "data/processed/ilce_oncelik_puanlari.csv"
)

cikti_yolu = Path(
    "data/processed/istanbul_ilce_oncelik.geojson"
)


# --------------------------------------------------
# VERİLERİ OKU
# --------------------------------------------------

geojson_verisi = json.loads(
    ham_geojson_yolu.read_text(
        encoding="utf-8"
    )
)

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
        "Öncelik dosyasında eksik sütunlar var: "
        f"{sorted(eksik_oncelik_sutunlari)}"
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


# --------------------------------------------------
# 39 İLÇELİK TABLOYA ÖNCELİK PUANLARINI EKLE
# --------------------------------------------------

birlesik_ilce_verisi = ilce_analizi.merge(
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


# --------------------------------------------------
# İLÇE ADINA GÖRE ARAMA SÖZLÜĞÜ OLUŞTUR
# --------------------------------------------------

ilce_bilgi_sozlugu = (
    birlesik_ilce_verisi
    .set_index("İlçe")
    .to_dict(orient="index")
)


# --------------------------------------------------
# RENK FONKSİYONU
# --------------------------------------------------

def oncelik_rengi(oncelik_seviyesi):
    """
    İlçenin öncelik seviyesine göre RGBA rengi döndürür.

    İlk üç sayı:
        Kırmızı, yeşil ve mavi renk değerleridir.

    Son sayı:
        Saydamlık değeridir.
        255 tamamen kapalı,
        0 tamamen görünmez demektir.
    """

    if oncelik_seviyesi == "Yüksek":
        return [220, 60, 60, 185]

    if oncelik_seviyesi == "Orta":
        return [245, 160, 60, 180]

    if oncelik_seviyesi == "Düşük":
        return [65, 125, 190, 175]

    # Öncelik puanı oluşturulamayan ilçeler.
    return [130, 130, 130, 145]


# --------------------------------------------------
# GEOJSON KAYITLARINI ZENGİNLEŞTİR
# --------------------------------------------------

eslesmeyen_ilceler = []

for feature in geojson_verisi["features"]:

    properties = feature.setdefault(
        "properties",
        {},
    )

    ilce_adi = str(
        properties.get("name", "")
    ).strip()

    if ilce_adi not in ilce_bilgi_sozlugu:
        eslesmeyen_ilceler.append(ilce_adi)
        continue

    ilce_bilgisi = ilce_bilgi_sozlugu[
        ilce_adi
    ]

    oncelik_puani = ilce_bilgisi[
        "Öncelik Puanı"
    ]

    puan_var_mi = pd.notna(
        oncelik_puani
    )


    # ----------------------------------------------
    # ÖNCELİK PUANI BULUNAN 29 İLÇE
    # ----------------------------------------------

    if puan_var_mi:
        oncelik_puani = float(
            oncelik_puani
        )

        oncelik_seviyesi = str(
            ilce_bilgisi[
                "Öncelik Seviyesi"
            ]
        )

        oncelik_sirasi = int(
            ilce_bilgisi[
                "Öncelik Sırası"
            ]
        )

        nufus_puani = float(
            ilce_bilgisi[
                "Nüfus Puanı"
            ]
        )

        hizmet_acigi_puani = float(
            ilce_bilgisi[
                "Hizmet Açığı Puanı"
            ]
        )

        # 100 taban yüksekliği, düşük puanlı ilçelerin
        # de 3D görünümde fark edilmesini sağlar.
        #
        # Bu yükseklik gerçek arazi veya bina
        # yüksekliği değildir.
        yukseklik = (
            100
            + oncelik_puani * 15
        )


    # ----------------------------------------------
    # VERİ DOĞRULAMASI GEREKEN 10 İLÇE
    # ----------------------------------------------

    else:
        oncelik_puani = None
        oncelik_seviyesi = (
            "Veri doğrulaması gerekli"
        )
        oncelik_sirasi = None
        nufus_puani = None
        hizmet_acigi_puani = None

        # Bu ilçeleri düz bırakmak yerine,
        # haritada fark edilmeleri için çok az yükselti.
        yukseklik = 40


    # ----------------------------------------------
    # GEOJSON PROPERTIES ALANINI GÜNCELLE
    # ----------------------------------------------

    properties.update(
        {
            "district": ilce_adi,

            "population": int(
                ilce_bilgisi[
                    "Toplam Nüfus"
                ]
            ),

            "library_count": int(
                ilce_bilgisi[
                    "Kütüphane Sayısı"
                ]
            ),

            "libraries_per_100k": round(
                float(
                    ilce_bilgisi[
                        "100 Bin Kişiye Düşen Kütüphane"
                    ]
                ),
                3,
            ),

            "data_status": str(
                ilce_bilgisi[
                    "Veri Durumu"
                ]
            ),

            "priority_rank": oncelik_sirasi,

            "population_score": (
                round(nufus_puani, 3)
                if nufus_puani is not None
                else None
            ),

            "service_gap_score": (
                round(hizmet_acigi_puani, 3)
                if hizmet_acigi_puani is not None
                else None
            ),

            "priority_score": (
                round(oncelik_puani, 3)
                if oncelik_puani is not None
                else None
            ),

            "priority_level": (
                oncelik_seviyesi
            ),

            "elevation": round(
                yukseklik,
                2,
            ),

            "fill_color": oncelik_rengi(
                oncelik_seviyesi
            ),
        }
    )


# --------------------------------------------------
# SON KONTROLLER
# --------------------------------------------------

if eslesmeyen_ilceler:
    raise ValueError(
        "GeoJSON ile analiz verisi arasında "
        "eşleşmeyen ilçeler var: "
        f"{sorted(eslesmeyen_ilceler)}"
    )


feature_sayisi = len(
    geojson_verisi["features"]
)

puanli_ilce_sayisi = sum(
    feature["properties"][
        "priority_score"
    ] is not None
    for feature in geojson_verisi["features"]
)

dogrulama_gereken_sayi = (
    feature_sayisi
    - puanli_ilce_sayisi
)


if feature_sayisi != 39:
    raise ValueError(
        "GeoJSON içinde 39 ilçe bulunamadı. "
        f"Bulunan sayı: {feature_sayisi}"
    )


# --------------------------------------------------
# ZENGİNLEŞTİRİLMİŞ GEOJSON'U KAYDET
# --------------------------------------------------

cikti_yolu.parent.mkdir(
    parents=True,
    exist_ok=True,
)

cikti_yolu.write_text(
    json.dumps(
        geojson_verisi,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)


# --------------------------------------------------
# SONUÇLARI GÖSTER
# --------------------------------------------------

print(
    f"GeoJSON içindeki toplam ilçe: "
    f"{feature_sayisi}"
)

print(
    f"Öncelik puanı eklenen ilçe: "
    f"{puanli_ilce_sayisi}"
)

print(
    f"Veri doğrulaması gereken ilçe: "
    f"{dogrulama_gereken_sayi}"
)

print(
    "\nİlk 5 ilçenin eklenen bilgileri:"
)

for feature in geojson_verisi["features"][:5]:

    properties = feature["properties"]

    print(
        f"- {properties['district']}: "
        f"puan={properties['priority_score']}, "
        f"seviye={properties['priority_level']}, "
        f"nüfus={properties['population']}"
    )


print(
    f"\nZenginleştirilmiş GeoJSON kaydedildi: "
    f"{cikti_yolu}"
)