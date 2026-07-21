from pathlib import Path
import json

import pandas as pd
import pydeck as pdk


# --------------------------------------------------
# DOSYA YOLLARI
# --------------------------------------------------

ilce_geojson_yolu = Path(
    "data/processed/istanbul_ilce_oncelik.geojson"
)

koordinat_veri_yolu = Path(
    "data/processed/ibb_kutuphaneleri_koordinatli.csv"
)

harita_cikti_yolu = Path(
    "frontend/kutuphane_oncelik_haritasi_3d.html"
)


# --------------------------------------------------
# İLÇE GEOJSON VERİSİNİ OKU
# --------------------------------------------------

ilce_geojson = json.loads(
    ilce_geojson_yolu.read_text(
        encoding="utf-8"
    )
)


# --------------------------------------------------
# İLÇE BİLGİ KUTULARINI HAZIRLA
# --------------------------------------------------

for feature in ilce_geojson["features"]:

    properties = feature["properties"]

    ilce_adi = properties["district"]

    oncelik_puani = properties[
        "priority_score"
    ]

    oncelik_sirasi = properties[
        "priority_rank"
    ]


    # Öncelik puanı bulunan ilçelerde
    # sayıyı okunaklı metne dönüştür.
    if oncelik_puani is not None:
        oncelik_puani_gosterim = (
            f"{oncelik_puani:.1f}"
        )

        oncelik_sirasi_gosterim = (
            str(oncelik_sirasi)
        )

    # Puanı hesaplanmamış ilçelerde
    # yanıltıcı bir sayı göstermek yerine açıklama yaz.
    else:
        oncelik_puani_gosterim = (
            "Hesaplanmadı"
        )

        oncelik_sirasi_gosterim = (
            "Hesaplanmadı"
        )


    properties.update(
        {
            "display_name": (
                f"{ilce_adi} İlçe Önceliği"
            ),

            "object_type": (
                "İlçe hizmet önceliği"
            ),

            "priority_score_display": (
                oncelik_puani_gosterim
            ),

            "priority_rank_display": (
                oncelik_sirasi_gosterim
            ),

            "population_display": (
                f"{properties['population']:,}"
                .replace(",", ".")
            ),

            "library_count_display": (
                str(
                    properties[
                        "library_count"
                    ]
                )
            ),

            "note": (
                "Yükseklik, görselleştirme amacıyla "
                "öncelik puanından üretilmiştir."
                if oncelik_puani is not None
                else
                "İBB veri setindeki kayıt durumu "
                "doğrulanmalıdır."
            ),
        }
    )


# --------------------------------------------------
# KÜTÜPHANE KOORDİNATLARINI OKU
# --------------------------------------------------

koordinat_verisi = pd.read_csv(
    koordinat_veri_yolu
)


# --------------------------------------------------
# KOORDİNATLARI SAYISAL DEĞERE DÖNÜŞTÜR
# --------------------------------------------------

koordinat_verisi["Enlem"] = pd.to_numeric(
    koordinat_verisi["Enlem"],
    errors="coerce",
)

koordinat_verisi["Boylam"] = pd.to_numeric(
    koordinat_verisi["Boylam"],
    errors="coerce",
)


# --------------------------------------------------
# GEÇERLİ KOORDİNATLARI BELİRLE
# --------------------------------------------------

koordinati_bulunan = (
    koordinat_verisi["Enlem"].notna()
    & koordinat_verisi["Boylam"].notna()
)


# --------------------------------------------------
# BULUNAN ADRESİN GÜVENİLİRLİĞİNİ KONTROL ET
# --------------------------------------------------

kutuphane_ifadesi = (
    r"kütüphane|kitaplık|kitaplığ|library"
)

adresi_guvenilir = (
    koordinat_verisi["Bulunan Adres"]
    .astype(str)
    .str.contains(
        kutuphane_ifadesi,
        case=False,
        na=False,
        regex=True,
    )
)


guvenilir_kutuphaneler = koordinat_verisi[
    koordinati_bulunan
    & adresi_guvenilir
].copy()


# --------------------------------------------------
# PYDECK İÇİN KÜTÜPHANE NOKTALARINI HAZIRLA
# --------------------------------------------------

kutuphane_noktalari = []

for _, satir in guvenilir_kutuphaneler.iterrows():

    kutuphane_adi = str(
        satir["Kütüphane Adı"]
    )

    ilce_adi = str(
        satir["İlçe Adı"]
    )

    adres = str(
        satir["Adres"]
    )

    kutuphane_noktalari.append(
        {
            # ColumnLayer konumu için:
            "longitude": float(
                satir["Boylam"]
            ),

            "latitude": float(
                satir["Enlem"]
            ),

            # Mevcut kütüphaneler çok kısa
            # mavi sütunlar olarak gösterilecek.
            #
            # Bu değer gerçek bina yüksekliği değildir.
            "elevation": 55,

            "fill_color": [
                25,
                85,
                180,
                235,
            ],

            # İlçe alanları ve kütüphane noktalarında
            # aynı bilgi kutusunu kullanabilmek için
            # açıklamalar properties içinde tutuluyor.
            "properties": {
                "display_name": kutuphane_adi,

                "object_type": (
                    "Mevcut kütüphane"
                ),

                "district": ilce_adi,

                "priority_score_display": (
                    "İlçe alanına bakınız"
                ),

                "priority_rank_display": (
                    "İlçe alanına bakınız"
                ),

                "priority_level": (
                    "İlçe alanına bakınız"
                ),

                "population_display": (
                    "İlçe alanına bakınız"
                ),

                "library_count_display": (
                    "İlçe alanına bakınız"
                ),

                "note": (
                    f"Adres: {adres}"
                ),
            },
        }
    )


# --------------------------------------------------
# İLÇE GEOJSON KATMANI
# --------------------------------------------------

ilce_katmani = pdk.Layer(
    "GeoJsonLayer",

    data=ilce_geojson,

    # GeoJSON içindeki polygon ve multipolygon
    # geometrilerinin içini doldur.
    filled=True,

    # İlçe sınır çizgilerini göster.
    stroked=True,

    # İlçe alanlarını yükseklikli hâle getir.
    extruded=True,

    # Renk her ilçenin properties alanından gelir.
    get_fill_color=(
        "properties.fill_color"
    ),

    # Yükseklik her ilçenin properties alanından gelir.
    get_elevation=(
        "properties.elevation"
    ),

    # İlçe sınır çizgisinin rengi.
    get_line_color=[
        255,
        255,
        255,
        210,
    ],

    line_width_min_pixels=1,

    # Polygon üzerine gelindiğinde bilgi alınabilsin.
    pickable=True,

    # Fareyle üzerine gelinen alanı vurgula.
    auto_highlight=True,

    highlight_color=[
        255,
        255,
        255,
        80,
    ],

    # Polygon kenarlarında tel kafes çizgisi gösterme.
    wireframe=False,

    opacity=0.82,
)


# --------------------------------------------------
# MEVCUT KÜTÜPHANE KATMANI
# --------------------------------------------------

kutuphane_katmani = pdk.Layer(
    "ColumnLayer",

    data=kutuphane_noktalari,

    get_position=[
        "longitude",
        "latitude",
    ],

    get_elevation="elevation",

    get_fill_color="fill_color",

    # Mevcut kütüphanelerin tabanı,
    # ilçe alanlarına göre küçük tutulur.
    radius=110,

    disk_resolution=12,

    elevation_scale=1,

    extruded=True,

    pickable=True,

    auto_highlight=True,
)


# --------------------------------------------------
# BAŞLANGIÇ KAMERA GÖRÜNÜMÜ
# --------------------------------------------------

baslangic_gorunumu = pdk.ViewState(
    # İstanbul'un yaklaşık merkezi.
    latitude=41.02,
    longitude=28.97,

    zoom=9.15,

    # Haritaya eğimli bakış:
    pitch=40,

    # Haritayı fazla döndürmeden doğal yönünde göster.
    bearing=0,
)


# --------------------------------------------------
# ORTAK BİLGİ KUTUSU
# --------------------------------------------------


bilgi_kutusu = {
    "html": """
        <b>{properties.display_name}</b><br/>
        Öncelik: {properties.priority_score_display}
        — {properties.priority_level}<br/>
        Sıra: {properties.priority_rank_display}<br/>
        Nüfus: {properties.population_display}<br/>
        İBB kütüphane kaydı:
        {properties.library_count_display}<br/>
        <span style="color: #bbbbbb;">
            {properties.note}
        </span>
    """,

    "style": {
        "backgroundColor": "rgba(25, 25, 25, 0.92)",
        "color": "white",
        "fontSize": "11px",
        "padding": "8px",
        "maxWidth": "230px",
        "borderRadius": "6px",
    },
}


# --------------------------------------------------
# HARİTA NESNESİNİ OLUŞTUR
# --------------------------------------------------

harita_3d = pdk.Deck(
    layers=[
        # İlçe alanları altta bulunur.
        ilce_katmani,

        # Mevcut kütüphaneler üstte gösterilir.
        kutuphane_katmani,
    ],

    initial_view_state=baslangic_gorunumu,

    map_provider="carto",

    map_style="light",

    tooltip=bilgi_kutusu,

    show_error=True,
)


## --------------------------------------------------
# HARİTA BAŞLIĞI VE RENK AÇIKLAMASI
# --------------------------------------------------

aciklama_paneli = """
<div id="urbanai-bilgi-paneli">
    <div class="urbanai-baslik">
        UrbanAI 3D İstanbul
    </div>

    <div class="urbanai-alt-baslik">
        Kütüphane Hizmeti İlçe Öncelik Haritası
    </div>

    <div class="urbanai-ayrac"></div>

    <div class="urbanai-aciklama">
        <span class="urbanai-renk urbanai-yuksek"></span>
        <span>Yüksek öncelik</span>
    </div>

    <div class="urbanai-aciklama">
        <span class="urbanai-renk urbanai-orta"></span>
        <span>Orta öncelik</span>
    </div>

    <div class="urbanai-aciklama">
        <span class="urbanai-renk urbanai-dusuk"></span>
        <span>Düşük öncelik</span>
    </div>

    <div class="urbanai-aciklama">
        <span class="urbanai-renk urbanai-dogrulama"></span>
        <span>Veri doğrulaması gerekli</span>
    </div>

    <div class="urbanai-aciklama">
        <span class="urbanai-kutuphane-isareti"></span>
        <span>Mevcut kütüphane</span>
    </div>

    <div class="urbanai-ayrac"></div>

    <div class="urbanai-not">
        İlçe yüksekliği, nüfus ve İBB kütüphane
        kayıtlarından hesaplanan öncelik puanının
        görsel karşılığıdır. Gerçek arazi veya bina
        yüksekliğini göstermez.
    </div>

    <div class="urbanai-kaynak">
        Analiz yılı: 2025
    </div>
</div>


<style>
    #urbanai-bilgi-paneli {
        position: fixed;
        top: 18px;
        left: 18px;
        z-index: 9999;

        width: 280px;
        box-sizing: border-box;

        padding: 15px 16px;

        background: rgba(22, 27, 34, 0.92);
        color: white;

        border: 1px solid rgba(255, 255, 255, 0.20);
        border-radius: 10px;

        font-family:
            Arial,
            Helvetica,
            sans-serif;

        box-shadow:
            0 4px 16px rgba(0, 0, 0, 0.28);

        /*
        Panel yalnızca bilgi vermek için kullanılıyor.
        Fare hareketlerini engellememesi için harita
        etkileşimleri panelin arkasında devam eder.
        */
        pointer-events: none;
    }

    .urbanai-baslik {
        margin-bottom: 3px;

        font-size: 18px;
        font-weight: 700;
    }

    .urbanai-alt-baslik {
        color: rgba(255, 255, 255, 0.82);

        font-size: 13px;
        line-height: 1.35;
    }

    .urbanai-ayrac {
        height: 1px;

        margin: 11px 0;

        background:
            rgba(255, 255, 255, 0.18);
    }

    .urbanai-aciklama {
        display: flex;
        align-items: center;
        gap: 9px;

        margin: 7px 0;

        font-size: 13px;
    }

    .urbanai-renk {
        display: inline-block;

        width: 16px;
        height: 16px;

        border: 1px solid
            rgba(255, 255, 255, 0.65);

        border-radius: 4px;
    }

    .urbanai-yuksek {
        background:
            rgba(220, 60, 60, 0.95);
    }

    .urbanai-orta {
        background:
            rgba(245, 160, 60, 0.95);
    }

    .urbanai-dusuk {
        background:
            rgba(65, 125, 190, 0.95);
    }

    .urbanai-dogrulama {
        background:
            rgba(130, 130, 130, 0.95);
    }

    .urbanai-kutuphane-isareti {
        display: inline-block;

        width: 10px;
        height: 18px;

        margin-left: 3px;
        margin-right: 3px;

        background:
            rgba(25, 85, 180, 1);

        border:
            1px solid rgba(255, 255, 255, 0.80);

        border-radius: 3px;
    }

    .urbanai-not {
        color: rgba(255, 255, 255, 0.75);

        font-size: 11px;
        line-height: 1.45;
    }

    .urbanai-kaynak {
        margin-top: 8px;

        color: rgba(255, 255, 255, 0.60);

        font-size: 10px;
    }

    /*
    Ekran dar olduğunda panelin fazla yer
    kaplamaması için boyutunu küçült.
    */
    @media (max-width: 600px) {
        #urbanai-bilgi-paneli {
            top: 10px;
            left: 10px;

            width: 235px;

            padding: 11px 12px;
        }

        .urbanai-baslik {
            font-size: 15px;
        }

        .urbanai-alt-baslik,
        .urbanai-aciklama {
            font-size: 11px;
        }

        .urbanai-not {
            font-size: 10px;
        }
    }
</style>
"""


# --------------------------------------------------
# HARİTA HTML KODUNU METİN OLARAK ÜRET
# --------------------------------------------------

harita_html = harita_3d.to_html(
    as_string=True,
    open_browser=False,
)


# --------------------------------------------------
# AÇIKLAMA PANELİNİ HTML DOSYASINA EKLE
# --------------------------------------------------

if "</body>" not in harita_html:
    raise ValueError(
        "Pydeck tarafından üretilen HTML içinde "
        "</body> etiketi bulunamadı."
    )


harita_html = harita_html.replace(
    "</body>",
    aciklama_paneli + "\n</body>",
)


# --------------------------------------------------
# HTML DOSYASINI KAYDET
# --------------------------------------------------

harita_cikti_yolu.parent.mkdir(
    parents=True,
    exist_ok=True,
)

harita_cikti_yolu.write_text(
    harita_html,
    encoding="utf-8",
)
# --------------------------------------------------
# SONUÇLARI KONTROL ET
# --------------------------------------------------

toplam_ilce_sayisi = len(
    ilce_geojson["features"]
)

puanli_ilce_sayisi = sum(
    feature["properties"][
        "priority_score"
    ] is not None
    for feature in ilce_geojson["features"]
)

dogrulama_gereken_sayi = (
    toplam_ilce_sayisi
    - puanli_ilce_sayisi
)


print(
    f"3D ilçe alanı sayısı: "
    f"{toplam_ilce_sayisi}"
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
    f"Gösterilen mevcut kütüphane: "
    f"{len(kutuphane_noktalari)}"
)

print(
    f"\n3D ilçe öncelik haritası kaydedildi: "
    f"{harita_cikti_yolu}"
)