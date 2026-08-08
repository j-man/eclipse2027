# STATUS — Eclipse 2027

Valmis ja testattu. Kaikki neljä vaatimusta ja viisi hyväksymiskriteeriä täyttyvät.

## Miten ajetaan

```bash
# kerran: riippuvuudet
python3 -m venv .venv && .venv/bin/pip install numpy skyfield

# data (n. 9 s; lataa de421.bsp ensimmäisellä kerralla, ~17 MB)
.venv/bin/python gen_data.py

# sivu: avaa suoraan selaimessa
xdg-open web/index.html
# tai
cd web && python3 -m http.server 8000     # → http://localhost:8000
```

Molemmat toimivat. `web/index.html` lataa datan `web/eclipse2027.js`:stä
`<script>`-tagilla, joten `file://` ei törmää fetch()-CORS-rajoitukseen.
`gen_data.py` kirjoittaa saman sisällön myös muodossa `data/eclipse2027.json`.

Näppäimet: väli = play/pause, nuoli vasen/oikea = askel minuutti kerrallaan.
Kartan klikkaus siirtää kellon siihen hetkeen (ks. alla).

### Testit

```bash
.venv/bin/pip install playwright && .venv/bin/playwright install chromium
.venv/bin/python check.py            # 24 tarkistusta oikeassa selaimessa
.venv/bin/python check.py --shots     # + kuvakaappaukset shots/-hakemistoon
```

## Mitä tehty

**`gen_data.py`** — laskee pimennyksen alusta asti, ainoa ulkoinen syöte on
JPL DE421 -efemeridi. Kriteeri on suunnitelman mukainen: piste on umbrassa kun
`erotuskulma(Aurinko, Kuu) + Auringon kulmasäde < Kuun kulmasäde`, ja lisäksi
Auringon on oltava horisontin yläpuolella (ilman tätä ehto täyttyy myös Maan
yöpuolella). Kokonaisaika **8,9 s**:

| vaihe | aika | mitä |
|---|---|---|
| 1 | 2,2 s | karkea haku: globaali 1° grid, 300 s askel, koko vuorokausi |
| 2 | 4,2 s | keskilinja ja umbran ääriviivat 60 s askelin, 205 ruutua |
| 3 | 1,1 s | kestot, vyöhykkeen reunat ja kestokäyrät |
| 4 | 1,3 s | Malagan ja Luxorin paikalliset ajat |

Nopeus tulee kahdesta asiasta:

1. **Auringon ja Kuun näennäispaikat lasketaan kerran per aika-askel Maan
   keskipisteestä**, ja topokeskinen vektori on sen jälkeen pelkkä vähennys
   koko numpy-taulukolle. Tämä ristiinvalidoitiin skyfieldin täyttä
   havaitsijakohtaista `observe().apparent()`-putkea vastaan: ero **alle
   0,02 kaarisekuntia**, eli ~5000× hienompi kuin 0,1° hila.
2. **Maan pyörähdysmatriisi nostettiin silmukan ulkopuolelle** (`SkyTable`).
   Skyfield laskee ITRS→GCRS-kierron uudelleen jokaiselle
   (havaitsija, aika) -parille; vaihe 3 kesti alun perin 183 s ja lyheni
   **1,1 sekuntiin** kun matriisi lasketaan kerran per aika-askel ja
   sovelletaan einsumilla.

Umbran ääriviiva haetaan säteittäisesti keskipisteestä 60 suuntaan (ei
konveksia verhoa) — reunapisteet ovat samoissa suuntakulmissa joka ruudussa,
joten selain voi interpoloida ne kärki kärjeltä sulavaksi liikkeeksi.
Vyöhykkeen reunat ja kestokäyrät tulevat poikittaisprofiileista: jokaisessa
keskilinjan pisteessä lasketaan kesto 121 pisteessä kohtisuoraan kulkusuuntaa
vastaan, ja reuna on kohta jossa kesto menee nollaan (kestokäyrät vastaavasti
1/2/4/6 minuutin kohdalta).

**`web/`** — Leaflet CDN:stä, Esri World Imagery -tiilet, ei buildia eikä
npm:ää. Kolme käsin kirjoitettua tiedostoa + generoitu datatiedosto.

### TASK 2 — kartan klikkaus (valmis)

Klikkaus mihin tahansa kartalla: animaatio pysäytetään, kello ja slideri
siirtyvät hetkeen jolloin umbran keskipiste on lähimpänä klikattua pistettä,
ja umbra piirretään sen mukaisesti. Play jatkaa uudesta ajasta, nuolinäppäimet
askeltavat edelleen minuutin, väli toggloi.

Aika ei nappaa lähimpään ruutuun vaan klikkaus **projisoidaan keskilinjan
jokaiselle 60 s jaksolle** ja lähin projektio voittaa, joten tulos on jatkuva.

Jos piste on totaliteettivyöhykkeen sisällä, klikkauskohtaan tulee pieni popup:
kesto, maksimin UTC-aika ja totaliteetin alku/loppu. **Uutta dataa ei tarvittu**
— kesto luetaan suoraan umbran ääriviivoista: piste on varjossa niiden kahden
hetken välillä, joina liikkuva ääriviiva ylittää sen, ja ylitykset haetaan
puolitushaulla samasta interpoloidusta ääriviivasta jonka animaatio piirtää.
Tämä ristiinvalidoitiin `gen_data.py`:n riippumattomasti laskemia arvoja
vastaan: **ero enintään ~2 s** (Malaga 114,3 s vs 115,4 s; Luxor 383,4 s vs
382,8 s; keskilinjan otokset koko polulta ≤ 2,1 s). Jäännösvirhe tulee 60 s
näytteenoton lineaarisesta interpoloinnista ja on selvästi pienempi kuin
laskennan oma ~2 s systemaattinen ero julkaistuihin ennusteisiin.

Rajatapaukset:
- **Polun ulkopuolella** ei näytetä popupia, vain kello siirtyy — ei arvailla.
- Jos piste on jo ensimmäisessä tai viimeisessä ruudussa, totaliteetti on
  alkanut ennen laskettua ikkunaa tai päättyy sen jälkeen. Silloin popup
  näyttää **vain maksimiajan**, ei kestoa, koska luku olisi aliarvio.
- **Markkerien klikkaukset** kuuluvat edelleen markkereille: Leaflet ei
  välitä klikkausta kartalle kun interaktiivinen taso nappaa sen, ja kaikki
  ratatasot (vyöhyke, käyrät, umbra, kestokäyrien tekstit) on piirretty
  `interactive: false` -asetuksella, joten ne eivät syö klikkauksia.
- **Raahaus ei laukaise klikkausta** (Leafletin oma `_draggableMoved`-tarkistus);
  testattu oikealla hiiren vedolla.

## Validointi

| | laskettu | suunnitelman odotus |
|---|---|---|
| Polun alku | 08:25 UTC, Atlantti 44°W | — |
| Gibraltarin salmi | **08:48 UTC** | 09:47 UTC ← katso alla |
| Luxor | 10:02:07–10:08:30 UTC | ~10:07 UTC ✓ |
| Maksimikesto | 6 min 25 s | ~6 min 23 s ✓ |
| Luxorin kesto | 6 min 23 s | ✓ |
| Malaga | vyöhykkeen sisällä, 1 min 55 s | vyöhykkeessä ✓, ~3 min ← katso alla |
| Polun loppu | 11:49 UTC, Intian valtameri 90°E | ✓ |

### Kaksi poikkeamaa suunnitelman lukuihin

**Gibraltar 08:48 UTC, ei 09:47.** Suunnitelman luku on ilmeisesti tunnin pielessä.
Meidän aikamme on sisäisesti johdonmukainen: Gibraltarista Luxoriin on 38°
pituuspiiriä eli n. 3800 km, ja meillä siihen kuluu 80 min (≈790 m/s, oikea
suuruusluokka umbran nopeudelle). Suunnitelman parivaljakko 09:47 → 10:07
tarkoittaisi 20 minuuttia eli 3,2 km/s, mikä on mahdotonta — sillä nopeudella
totaliteetti ei kestäisi missään 6 minuuttia. Luxorin aika ja maksimikesto
täsmäävät suunnitelmaan tarkasti, joten mitään yleistä aikasiirtymää ei ole.
Espanjan paikallisaikana 08:48 UTC = **10:48 CEST**.

**Malaga saa 1 min 55 s, ei ~3 min.** Malagan keskusta (36,7213°N) on lähellä
vyöhykkeen pohjoisreunaa: keskilinja kulkee 35,73°N, ja pohjoisraja on tuolla
pituuspiirillä 36,86°N. Malaga on siis sisällä, mutta vain n. 15 km reunasta.
Sen sijaan **Tarifa 4 min 42 s** ja **Gibraltar 4 min 28 s** — jos tavoite on
pitkä totaliteetti, kannattaa siirtyä ~80 km lounaaseen salmen suulle.
Kestokäyrät kartalla näyttävät tämän suoraan.

## Mitä jäi

- **Keskilinjan kestokäyrä on hyvin litteä maksiminsa ympärillä** (385,1 s vs
  385,3 s usean sadan kilometrin matkalla), joten `meta.max_duration_at`
  (26,90°N 30,98°E, 10:00 UTC) heilahtelee numeerisesti eikä osu tarkalleen
  julkaistuun suurimman pimennyksen pisteeseen (n. 25,5°N 33,2°E). Kesto
  itsessään on oikea ±2 s. Ei vaikuta karttaan.
- Kesto on n. 2 s pidempi kuin julkaistut ennusteet, koska laskenta käyttää
  Kuun keskisädettä eikä todellista reunaprofiilia (vuoret ja laaksot Kuun
  reunalla). Tämä on odotettu ero, ei virhe.
- Kartalla ei ole osittaisen pimennyksen prosenttikäyriä (95 %, 99 % kuten
  referenssikuvissa) — ne eivät olleet vaatimuksissa.
- Klikkauspopup näyttää totaliteetin, ei osittaisen pimennyksen prosenttia
  eikä kontaktiaikoja C1/C4 — ne vaatisivat penumbran, jota ei lasketa.
  Merkityille paikoille (Malaga, Luxor) nämä ovat popupissa.

## Tiedostot

```
gen_data.py            datageneraattori (numpy + skyfield)
check.py               hyväksymistestit selaimessa (playwright)
data/eclipse2027.json  data suunnitelman muodossa
web/index.html         sivu
web/app.js             kartta, animaatio, kontrollit
web/style.css          tumma ulkoasu
web/eclipse2027.js     sama data window.ECLIPSE_DATA:na (file://-tuki)
shots/                 kuvakaappaukset testiajosta
de421.bsp              skyfieldin lataama efemeridi (ei versionhallintaan)
```
