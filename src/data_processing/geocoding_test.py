from geopy.geocoders import Nominatim


geolocator = Nominatim(
    user_agent="urbanai-3d-istanbul/1.0 "
    "(github.com/Ebrar6565/urbanai-3d-istanbul)"
)

adres = "Atatürk Kitaplığı, Beyoğlu, İstanbul, Türkiye"
konum = geolocator.geocode(
    adres,
    language="tr",
    country_codes="tr",
    timeout=10,
)

if konum is None:
    print("Adres için koordinat bulunamadı.")
else:
    print("Bulunan adres:")
    print(konum.address)

    print("\nEnlem:")
    print(konum.latitude)

    print("\nBoylam:")
    print(konum.longitude)