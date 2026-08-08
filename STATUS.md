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
.venv/bin/python check_oracle.py     # 7 vertailua julkaistuun ennusteeseen

.venv/bin/pip install playwright && .venv/bin/playwright install chromium
.venv/bin/python check.py            # 32 tarkistusta oikeassa selaimessa
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
| 4 | 1,5 s | yhdeksän paikkakunnan paikalliset olosuhteet |

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

### TASK 3 — lisää paikkamerkit (valmis)

Merkit ovat `gen_data.py`:n `MARKERS`-listassa kuten ennenkin (ei staattista
listaa app.js:ssä), ja data on ajettu uudelleen. Yhdeksän paikkaa:

| paikka | kesto | maksimi UTC | paikallinen |
|---|---|---|---|
| Sevilla | **ei totaliteettia** | 08:47:33 | 10:47 CEST |
| Malaga | 1 min 55 s | 08:49:06 | 10:49 CEST |
| Cadiz | 2 min 57 s | 08:46:53 | 10:46 CEST |
| Gibraltar | 4 min 29 s | 08:47:48 | 10:47 CEST |
| Tarifa | 4 min 40 s | 08:47:28 | 10:47 CEST |
| Ceuta | 4 min 50 s | 08:47:46 | 10:47 CEST |
| Sfax | 5 min 41 s | 09:11:39 | 10:11 CET |
| Luxor | 6 min 23 s | 10:05:19 | 13:05 EEST |
| Wadi Lahmy Azur Resort | 6 min 15 s | 10:13:18 | 13:13 EEST |

**Sevilla jää vyöhykkeen ulkopuolelle** — 70 km pohjoisrajasta, magnitudi
0,979. Etäisyys on tarkistettu kahdella riippumattomalla tavalla: generaattorin
piste–jana-etäisyydellä raja­viivaan (69,6 km) ja suoralla vertailulla
pohjoisrajan leveysasteeseen Sevillan pituuspiirillä (36,762°N vs 37,389°N =
0,627° = 70 km). Merkki piirretään silti, mutta **onttona harmaana pisteenä**
täytetyn keltaisen sijaan, ja popup kertoo "98 % osittainen ·
totaliteettivyöhykkeen ulkopuolella — 70 km reunasta" ilman totaliteettirivejä.
Muut kahdeksan ovat vyöhykkeen sisällä; testi tarkistaa jokaisen merkin
kartalle piirrettyä vyöhykepolygonia vastaan, ei pelkkää dataa.

Popupeissa on nyt myös **maksimin kellonaika** kaikille paikoille. Paikallinen
vyöhyke mainitaan kerran alaviitteessä eikä joka rivillä, jolloin rivit mahtuvat
yhdelle riville.

Ei pysyviä tekstilappuja kartalla: nimi tulee hoverilla (`bindTooltip`),
olosuhteet klikkauksella. Eteläisen Espanjan kuusi merkkiä ovat 200 km säteellä
toisistaan, joten aina näkyvät nimet menisivät päällekkäin uloszoomattaessa.
Pisteet itsessään sulautuvat maailmanzoomilla yhdeksi täpläksi — se on
tarkoituksellista, ei tekstisotkua, ja zoomaus erottaa ne heti.

Kaksi korjausta jotka tulivat tämän mukana:

- **Luxor oli merkitty EET (UTC+2), nyt EEST (UTC+3).** Egypti palautti
  kesäajan 2023, ja nykylain mukaan 2.8.2027 osuu kesäaikaan. Neljän vuoden
  päähän ulottuva DST-oletus on aina epävarma, mutta tämä on paras arvio
  voimassa olevien sääntöjen perusteella. Tunisia (Sfax) on UTC+1 ympäri
  vuoden, Espanja ja Ceuta UTC+2 elokuussa.
- **`max_obscuration` → `max_magnitude`.** Kenttä sisälsi alusta asti
  magnitudin `(r_s + r_m − sep) / 2r_s` eli Auringon *halkaisijasta* peitetyn
  osuuden, ei obskuraatiota (peitetty *pinta-ala*). Nimi oli väärä; arvo ei
  muuttunut. Ei näkynyt aiemmin missään, koska kumpikaan silloisista
  merkeistä ei ollut osittainen.

### TASK 4 — versionumero nurkassa (valmis)

`v4` vasemmassa alanurkassa (attribuutio on oikeassa); numero on `VERSION`-vakio
`web/app.js`:n alussa, ja `gen_data.py` lisää lyhyen git-hashin (`v4 · 4f2a1c9`)
jos hakemisto sattuu olemaan git-checkout — nyt ei ole, joten hash jää pois.

### TASK 5 — vertailu julkaistuun ennusteeseen (valmis)

`check_oracle.py` vertaa laskentaamme riippumattomaan julkaistuun ennusteeseen.
**Lähde:** Fred Espenak, NASA/GSFC, *Path of the Total Solar Eclipse of 2027
Aug 02*, <https://eclipse.gsfc.nasa.gov/SEpath/SEpath2001/SE2027Aug02Tpath.html>,
haettu 8.8.2026. (EclipseWise palauttaa 403 automaattiselle haulle; NASA GSFC
on saman tekijän julkaisu.) Vertailuarvot on kirjoitettu tiedostoon *sellaisenaan*
lähteen omassa muodossa (`"25°38.3'N"`, `"06m22.7s"`) ja jäsennetään koodissa,
jotta taulukon voi tarkistaa lähdesivua vasten rivi riviltä ilman laskutoimituksia.

Jotta testi kohdistuu oikeasti siihen koodiin joka tuottaa kartan datan, jaettu
fysiikka on siirretty uuteen `eclipse_core.py`:hyn, jonka sekä `gen_data.py`
että `check_oracle.py` tuovat. Refaktorointi tarkistettiin ajamalla generaattori
uudelleen: JSON oli tavulleen identtinen.

17 keskilinjan pistettä koko polulta (Atlantti → Gibraltar → Tunisia → Libya →
Luxor → Punaisenmeren rannikko → Arabia → Intian valtameri):

| suure | tulos | vaatimus |
|---|---|---|
| kesto | **+1,4 … +2,1 s**, ka. +1,86 s | [−3, +5] s ✓ |
| maksimin aika | **+3,5 … +5,0 s**, ka. +4,41 s | ±30 s ✓ |
| suurin pimennys (10:06:37,7 UT) | kesto +2,0 s, aika +4,9 s | ✓ |
| polun leveys (5 hetkeä) | **+1,8 … +2,8 km** / ~250 km | ±4 km ✓ |
| julkaistut rajapisteet | 0,3 km ja 1,9 km omasta reunastamme | < 6 km ✓ |
| Madrid (negatiivinen testi) | ei totaliteettia, magnitudi 0,879 | ✓ |

**Molemmat systemaattiset erot selvitettiin mittaamalla, ei arvaamalla:**

- **Kesto +1,9 s.** Kesto muuttuu **3 s jokaista Kuun säteen kilometriä kohti**
  (mitattu: 1736,0 km → 380,6 s, 1739,0 km → 389,6 s). Espenakin taulukon
  382,7 s toistuu säteellä ≈ 1736,6 km, kun me käytämme PLAN.md:n määräämää
  IAU:n keskisädettä 1737,4 km — pienempi umbrakontaktien sädekonventio. 0,8 km
  × 3 s/km = 2,4 s, eli koko ero. Emme vaihtaneet sädettä: PLAN.md määrittelee sen.
- **Aika +4,4 s.** Keskilinjamme kulkee ~3,4 km Espenakin linjan länsipuolella;
  radansuuntainen osuus 3,3 km jaettuna varjon nopeudella maanpinnalla
  (0,668 km/s) = 4,9 s Luxorissa — tarkalleen havaittu ero. Osa tästä on ΔT:tä:
  skyfield käyttää 69,1 s, Espenak 71,7 s. Kun skyfield pakotetaan Espenakin
  arvoon, hajonta polun yli litistyy (+3,5…+5,0 s → +3,4…+3,7 s), mutta jäljelle
  jää tasainen +3,6 s. Poikittaissuunnassa ero on vain ~1 km, minkä vuoksi
  kestot täsmäävät niin hyvin.

**Testi löysi oikean virheen.** Ensimmäisellä ajolla polun leveys oli
+2,6 … +7,8 km liian suuri, ja vaihtelu oli tasan yhden poikittaisnäytteen
suuruinen. Syy: `cross()` interpoloi rajan viimeisen sisäpuolisen näytteen ja
sen ulkopuolisen naapurin välillä, mutta ulkopuolisen kesto on kova nolla, joka
ei kerro *missä* reuna on — vain että se on ennen sitä. Tämä työnsi rajan lähes
ulkopuolisen näytteen päälle. Nyt reuna ekstrapoloidaan kahdesta viimeisestä
*sisäpuolisesta* näytteestä, joissa sqrt-laki oikeasti pätee. Leveysero putosi
**+2,6…+7,8 km → +1,8…+2,8 km** ja on nyt tasainen, eli sen selittää pelkkä
Kuun säteen valinta. Vyöhyke oli aiemmin ~2,7 % liian leveä; paikkakuntien
kestot eivät muuttuneet (ne eivät riipu rajaviivoista).

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
  Merkityille yhdeksälle paikalle nämä ovat popupissa.
- Kesäaikaoletukset ovat neljän vuoden päässä eivätkä siksi varmoja; UTC-ajat
  ovat aina oikein, paikallisajat riippuvat siitä pysyvätkö säännöt voimassa.

## Tiedostot

```
eclipse_core.py        jaettu fysiikka (umbrakriteeri, SkyTable, olosuhteet)
gen_data.py            datageneraattori (numpy + skyfield)
check.py               hyväksymistestit selaimessa (playwright)
check_oracle.py        vertailu NASA/GSFC:n julkaistuun ennusteeseen
data/eclipse2027.json  data suunnitelman muodossa
web/index.html         sivu
web/app.js             kartta, animaatio, kontrollit
web/style.css          tumma ulkoasu
web/eclipse2027.js     sama data window.ECLIPSE_DATA:na (file://-tuki)
shots/                 kuvakaappaukset testiajosta
de421.bsp              skyfieldin lataama efemeridi (ei versionhallintaan)
```
