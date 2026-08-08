# Eclipse 2027 — interaktiivinen pimennyskartta

Itsenäinen projekti. Lue tämä kokonaan ennen kuin teet mitään.

## Tavoite

Selaimessa toimiva sivu **2.8.2027 täydellisestä auringonpimennyksestä**, samaan
tapaan kuin https://eclipse2026.is/where-to-see (referenssikuvat tässä
hakemistossa: `reference-iceland-2026.png`, `reference-spain-2026.png` — katso ne).

Vaatimukset:
1. **Satelliittikartta** jota voi zoomata ja liikuttaa (Leaflet + Esri World
   Imagery -tiilet, ei API-avaimia).
2. **Totaliteettivyöhyke** kartalla: pohjois- ja eteläreuna, keskilinja,
   puolittain läpinäkyvä tumma vyöhyke välissä. Lisäksi kestokäyrät
   (1m / 2m / 4m / 6m) jos data taipuu — eivät pakollisia v1:ssä.
3. **Animoitu umbra**: tumma ellipsi joka liikkuu kartalla pimennyksen
   todellista rataa todellisella nopeudella. Kontrollit kuten videossa
   (referenssikuvien alalaita): play/pause, nopeuskerroin (esim. 1×/60×/300×/600×),
   aikaslideri, UTC-kellonäyttö ("HH:MM:SS UTC · 2 AUG").
4. **Malaga-markkeri**: käyttäjän suunniteltu katselupaikka (~3 min
   totaliteetti). Popup jossa paikalliset ajat jos data antaa.

## Työtapa — TÄRKEIN SÄÄNTÖ

**Karu tulos 10 sekunnissa voittaa tarkan joka kestää 2 tuntia.** Iteroi:
ensin JOTAIN ruudulle, sitten tarkenna. Yksikään laskenta- tai generointiajo ei
saa kestää yli 60 sekuntia — jos kestää, karkeista (isompi aika-askel, harvempi
grid, vektoroi). Pitkät ajot vasta lopuksi viimeistelynä, jos tarpeen.

## Data — LASKETAAN ITSE, ilman ulkoisia lähteitä

Python + skyfield (de421.bsp — skyfield lataa sen itse; tämä on efemeridi, ei
"ulkoinen lähde" tässä mielessä). EI haeta valmiita polkuja verkosta — koko
pointti on laskea itse. Mutta NOPEASTI:

**Kriteeri:** piste on umbrassa hetkellä t kun havaitsijan näkökulmasta
erotuskulma(Aurinko, Kuu) + Auringon kulmasäde < Kuun kulmasäde.
Kulmasäde = asin(R/etäisyys); R_sun = 696 000 km, R_moon = 1 737.4 km.

**Nopeus tulee vektoroinnista, ei menetelmästä:**
- Rakenna KOKO lat/lon-grid kerralla: `wgs84.latlon(lat_array, lon_array)`
  hyväksyy numpy-taulukot → yksi observe()-kutsu antaa kaikkien pisteiden
  erotuskulmat kerralla. EI silmukkaa pisteiden yli, EI scipy-optimointia,
  EI pistekohtaista binäärihakua.
- Vaihe 1 (sekunteja): karkea haku — aika-askel 300 s, globaali grid 1°.
  Löytyy missä ja milloin umbra on. Tulosta eteneminen joka askeleella.
- Vaihe 2 (kymmeniä sekunteja): tarkennus — aika-askel 60 s, paikallinen grid
  edellisen askeleen keskipisteen ympärillä (±4°, 0.1°). Umbra-polygoni =
  umbra-pisteiden konveksi verho; keskipiste = centroid; polun reunat =
  polygonien verhokäyrä; kesto pisteessä lasketaan keskilinjapisteille
  (montako aika-askelta piste täyttää ehdon × askel).
- Kokonaisaika saa olla korkeintaan ~60 s. Jos ylittyy, karkeista lisää.

**Validointi heti vaiheen 1 jälkeen, ennen mitään muuta:** polku kulkee
Gibraltarin salmen yli ~09:47 UTC ja Luxorin ~10:07 UTC, maksimikesto ~6 min
23 s Luxorin seudulla, Malaga on vyöhykkeessä (~3 min). Jos ei täsmää,
pysähdy ja korjaa — yleisin virhe on koordinaattikehys (käytä skyfieldin
apparent()-paikkoja havaitsijasta, älä rakenna omaa varjokartiota).

## Rakenne

```
/home/jmm/eclipse2027/
  PLAN.md, reference-*.png     (annettu)
  gen_data.py                  → data/eclipse2027.json
  data/eclipse2027.json
  web/index.html  web/app.js  web/style.css
```

JSON-muoto (ohjeellinen — muuta jos parempi):
```json
{"meta": {"date": "2027-08-02", "step_s": 60},
 "path": {"north": [[lat,lon],...], "south": [...], "center": [[lat,lon,"HH:MM:SS","durS"],...]},
 "umbra": [{"t": "09:47:00", "c": [lat,lon], "w_km": 258, "h_km": 300, "az_deg": 100}, ...]}
```

Ei buildia, ei npm:ää: Leaflet CDN:stä, kolme käsin kirjoitettua web-tiedostoa.
Sivun pitää auetta suoraan `file://`-polusta TAI `python3 -m http.server`illä
web/-hakemistosta (jos fetch() vaatii, mainitse README-rivillä).

## Ulkoasu

Tumma, hillitty, referenssikuvien henki: kontrollipalkki alhaalla pyöristettynä
tummana kapselina, kello oikealla omana laatikkonaan, vyöhyke tummana
läpinäkyvänä, keskilinja punaisena, kestokäyrät oranssi/keltainen. Ei
ylimääräistä UI-roinaa.

## Hyväksymiskriteerit (testaa itse ennen valmiiksi julistamista)

1. Sivu aukeaa, kartta näkyy, zoom/pan toimii.
2. Vyöhyke ja keskilinja kulkevat Atlantilta Gibraltarin ja Luxorin kautta
   Intian valtamerelle.
3. Play liikuttaa umbraa sulavasti länsi→itä, kello etenee, slideria voi raahata.
4. Malaga-markkeri on vyöhykkeen sisällä.
5. Kokonaisajo (datageneraatio) alle 60 s.

Kirjoita loppuun lyhyt `STATUS.md`: mitä tehty, mitä jäi, miten ajetaan.
