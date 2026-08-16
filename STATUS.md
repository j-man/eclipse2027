# STATUS — Eclipse 2027 → kaikki täydelliset pimennykset 1986–2066

Valmis ja testattu. PLAN.md:n neljä vaatimusta ja viisi hyväksymiskriteeriä
täyttyvät, ja TASK 2–12 on toteutettu. 94 selaintarkistusta + 7 vertailua
julkaistuun ennusteeseen menevät läpi.

## Miten ajetaan

```bash
# kerran: riippuvuudet
python3 -m venv .venv && .venv/bin/pip install numpy skyfield

# PLAN.md:n pimennys 2027-08-02 + sivun oletus 2026-08-12 (n. 18 s;
# lataa de440s.bsp ensimmäisellä kerralla, ~32 MB)
.venv/bin/python gen_data.py

# koko luettelo 1986–2066 (n. 20 s haku + n. 5 min generointi)
.venv/bin/python find_eclipses.py         # → data/index.json (59 pimennystä)
.venv/bin/python gen_data.py --all        # → data/eclipses/YYYY-MM-DD.js

# sivu: avaa suoraan selaimessa
xdg-open web/index.html
# tai palvele projektin JUURESTA (ei web/-hakemistosta)
python3 -m http.server 8000               # → http://localhost:8000/web/
```

Molemmat toimivat. `web/index.html` lataa oletuspimennyksen ja luettelon
`<script>`-tageilla, joten `file://` ei törmää fetch()-CORS-rajoitukseen, ja
muiden pimennysten data haetaan tarvittaessa `../data/eclipses/`-hakemistosta
samalla tempulla. **Huom:** aiempi ohje `cd web && python3 -m http.server` ei
enää riitä — se ei näe `../data/`-hakemistoa, joten muut kuin oletuspimennys
jäävät lataamatta. Palvele juuresta tai avaa tiedostona.

Näppäimet: väli = play/pause, nuoli vasen/oikea = askel minuutti kerrallaan.
Kartan klikkaus siirtää kellon siihen hetkeen (ks. alla).

### Testit

```bash
.venv/bin/python check_oracle.py     # 7 vertailua julkaistuun ennusteeseen

.venv/bin/pip install playwright && .venv/bin/playwright install chromium
.venv/bin/python check.py            # 63 tarkistusta oikeassa selaimessa
.venv/bin/python check.py --shots     # + kuvakaappaukset shots/-hakemistoon
```

## Mitä tehty

**`gen_data.py`** — laskee pimennyksen alusta asti, ainoa ulkoinen syöte on
JPL DE440s -efemeridi (DE421 kattoi vain ~1900–2050, DE440s koko
1986–2066). Kriteeri on suunnitelman mukainen: piste on umbrassa kun
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
npm:ää. Kolme käsin kirjoitettua tiedostoa + generoidut datatiedostot.

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

### TASK 6 — kaikki täydelliset pimennykset 1986–2066 (valmis)

**59 pimennystä**, joissa on täydellinen vaihe: 53 täydellistä ja 6 hybridiä.
Data yhteensä **10,5 MB**, ladataan vasta kun pimennys valitaan.

Luettelo johdetaan efemeridistä, ei verkosta. `find_eclipses.py` etsii ensin
uudetkuut (81 vuotta, 6 h ruudukko, geometriset paikat riittävät ja ovat
kymmenen kertaa halvempia kuin valonkulkukorjatut) ja tutkii sitten ne 572,
joissa erotuskulma on alle 4°. Ratkaiseva oivallus: **testi tehdään varjon
akselilla, ei ruudukolla.** Akseli on Auringon keskipisteestä Kuun keskipisteen
kautta kulkeva suora; siinä kohtaa missä se osuu ellipsoidiin, varjo on syvin,
joten yksi piste ratkaisee koko kysymyksen:

    täydellinen  kun  r_kuu − r_aurinko − erotus > 0
    rengasmainen kun  r_aurinko − r_kuu − erotus > 0

Molempia näyttävä on hybridi. Ruudukko, joka on tarpeeksi karkea pyyhkäisemään
80 vuotta, astuisi suoraan muutaman kilometrin levyisen umbran yli — juuri niitä
hybridejä ei löytyisi. Koko haku kestää **19 s**.

Validointi TASK6:n antamia tunnettuja faktoja vastaan (`check.py` 8a–8g):

| tarkistus | tulos |
|---|---|
| lukumäärä 55–65 | 59 ✓ |
| 7 nimettyä pimennystä, päivämäärät tarkalleen | kaikki löytyivät ✓ |
| 2009-07-22 on 2000-luvun pisin, ~6m39s | 402 s (+3 s) ✓ |
| 2017-08-21 ~2m40s (Hopkinsville KY) | 162,5 s (+2,3 s) ✓ |
| 2024-04-08 ~4m28s (Torreón) | 270,1 s (+2,0 s) ✓ |
| kaikilla luettelon pimennyksillä on datatiedosto | 59/59 ✓ |

Erot ovat sitä samaa +2 s:n Kuun sädekonventiota jonka TASK 5 mittasi.
Huomaa että 1991-07-11 (6m57s) on listan pisin, mutta se on 1900-lukua;
"vuosisadan pisin" tarkoittaa 2000-lukua, ja testi rajaa sen niin.

**Rajatapaukset:**

- **Päivämääräraja.** 15 polkua ylittää ±180°. Ne eivät ole katkaistu saumasta
  vaan pituusasteet kirjoitetaan **jatkuvina** (…179, 181, …), jolloin Leaflet
  piirtää ne suoraan seuraavaan maailmankopioon ja vyöhyke, keskilinja ja
  jokainen umbran ääriviiva pysyvät yhtenä kappaleena. Katkaisu jättäisi
  näkyvän raon juuri sinne missä varjo on kiinnostavin. `worldCopyJump` on
  siksi pois päältä: kartan keskipisteen kiertäminen veisi geometrian
  maailmanleveyden päähän näkyvästä kopiosta. Klikkaustesti siirtää
  klikatun pituusasteen kunkin ruudun omalle kierrokselle ennen vertailua.
- **Napa-alueet.** 12 polkua yltää yli 70° leveydelle, 2015-03-20 aina
  88,9°N asti. Mercator ei piirrä yli ~85°, joten aloitusnäkymän rajat
  leikataan ±84°:een — muuten koko ruutu menisi tyhjään tilaan.
- **Hybridit joiden täydellinen vaihe on lyhyt.** Neljä hybridiä
  (1986-10-03, 1987-03-29, 2005-04-08, 2049-11-25) epäonnistui ensimmäisellä
  ajolla: globaali 1°/300 s haku ei näe umbraa joka on pinnalla alle minuutin.
  Nyt generaattori putoaa takaisin **akselihakuun** (`axis_scan`) kun ruudukko
  ei löydä mitään, ja valitsee aika-askeleen niin että lyhyestäkin vaiheesta
  tulee ≥24 ruutua. 1986-10-03 kestää keskilinjalla **2 sekuntia** ja on nyt
  mukana 27 ruudulla — juuri se on hybridin kiinnostavin osa.
- **Epäonnistuminen ei kaada ajoa**: virhe kirjataan, pimennys ohitetaan ja
  se poistetaan luettelosta, jottei sivu tarjoa dataa jota ei ole.

Käyttöliittymä: pudotusvalikko vasemmassa ylänurkassa, rivit muotoa
`2027-08-02 · total · 6m25s · Morocco - Europe - Egypt - Indian Ocean`.
Valinta lataa datan `<script>`-injektiolla, purkaa vanhat tasot, rakentaa uudet
ja lentää polulle. Paikkamerkit ovat 2027-kohtaisia ja näkyvät vain sille.
Aluetunnisteet johdetaan karkeista laatikoista polun koordinaateista — ne ovat
tarkoituksella likimääräisiä, ihmisen vihje eikä maantieteellinen väite.

Refaktorointi: yhden pimennyksen putki on nyt funktio `generate(date, …)`,
ja `eclipse_core.py` sai jaetut akseligeometriat. Molemmat tarkistettiin
ajamalla 2027 uudelleen — JSON oli tavulleen identtinen (paitsi `source`,
joka nyt kertoo DE440s:n, kuten pitääkin).

### TASK 7 — pimennysvalitsin näkyväksi (valmis)

Otsikkokortti **on** nyt valitsin: koko kortti on `<button>`, jossa on ▾-nuoli,
rivi `31 / 59 pimennystä · täydellinen` ja hover/focus-nosto; lista avautuu
kortin alle, vanha erillinen `<select>` on poistettu. Ensikäynnillä nuoli
sykkii 3 s (localStorage-lippu kirjataan heti kun vihje alkaa, joten sivun
sulkeminen kesken animaation ei tuo sitä uudelleen). Enter/väli avaa,
nuolinäppäimet selaavat listaa, Esc sulkee, klikkaus muualle sulkee. Versio 6.
Samalla korjautui piilevä vika: napin päällä välilyönti laukaisi sekä napin
oman toiminnon että globaalin play/pause-oikotien, jotka kumosivat toisensa.

### TASK 8 — selkeämpi valitsin ja 2026-08-12 oletukseksi (valmis)

Sivu avautuu nyt **12.8.2026** pimennykseen (Islanti → Espanja, neljä päivää
tästä päivästä); oletus on määritelty yhdessä paikassa, `find_eclipses.py`:n
`DEFAULT_ECLIPSE`-vakiossa, ja kulkee selaimeen `data/index.json`:in
`default`-kentässä — `app.js`:ssä on vain varafallback jos luetteloa ei saada
ladattua lainkaan. 2027-08-02 säilyy listassa ja pitää edelleen omat
`data/eclipse2027.json`-tiedostonsa ja paikkamerkkinsä (`PLAN_DATE`).
Kortin sisällä on nyt oma **napilta näyttävä rivi** `Valitse pimennys (59) ▾`
— oma pinta, reunus, hover-tila ja isompi nuoli; pelkkä klikattava otsikko ei
ollut affordanssi. Lista on sarakkeistettu (päivä | tyyppi | kesto | alue),
jaettu vuosikymmenotsikoilla, menneet himmennetty, valittu korostettu ja
seuraava tuleva merkitty `SEURAAVA`-lipulla (laskettu selaimen kellosta, ei
käännösajasta). Versio 7.

### TASK 9 — lähivuodet korostettuna (valmis)

Listassa on nyt kolme korostustasoa eikä enempää: menneet himmennettyinä,
**matkasuunnitteluetäisyydellä olevat** (tästä vuodesta +2, eli nyt
2026-08-12, 2027-08-02 ja 2028-07-22) nostettuna keltaisella
reunapalkilla ja hillityllä pohjalla, muut siltä väliltä. Korostus pysyy
samassa aksenttisävyssä kuin valittu rivi, joten se ei luo uutta kategoriaa;
`SEURAAVA`-lippu on ainoa toinen väri. Vuosiraja lasketaan selaimen kellosta,
joten se pysyy oikeana ensi vuonnakin. **Versionumero seuraa nyt
tehtävänumeroa** (v9); se oli karannut kaksi jäljessä, koska TASK 5 oli
pelkkä validointilisä joka ei koskenut sivuun.

### TASK 10 — paikallinen aika UTC:n rinnalle (valmis)

Kellonajat näytetään nyt klikatun paikan omassa vyöhykkeessä ja UTC perässä
(`11:07:41 (UTC+2) — 09:07:41 UTC`); merkit kantavat IANA-nimen datassa ja
klikkaus hakee sen `web/tz.js`:n laatikkotaulusta, minkä jälkeen selaimen oma
tz-tietokanta antaa pimennyksen päivän oikean kesäaikasiirron. Laskenta ja
tallennetut ajat pysyvät UTC:na. Sinne mihin taulu ei ulotu — meri ja osa
sisämaan rajoista — jää pituuspiiriarvio, joka näytetään aina tildellä
(`~UTC−3`). **Huom:** Luxor on UTC+3 eikä tehtävän olettama UTC+2, koska
Egypti otti kesäajan takaisin 2023 (v10).

### TASK 11 — kolme kelloa: paikka, katsoja, UTC (valmis)

Popupit näyttävät nyt jokaisesta tapahtumasta kolme aikaa sarakkeina —
paikallinen, **sinun aikasi** (selaimen oma vyöhyke `Intl`:stä, ei
laatikkotaulusta) ja UTC — vyöhykkeet nimettynä kertaalleen otsikkorivillä,
jotta rivit pysyvät yhden rivin korkuisina ja paikan sarake korostuneena.
Katsojan sarake jää pois kun se osuisi samaan siirtoon kuin paikka (esim.
Kairosta Luxoria katsottaessa). Yläkellon jättämä paikka + UTC on ennallaan:
se näyttää aikajanan kohdan, ei tapahtuma-aikaa (v11).

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

### TASK 12 — paikalliset olot mistä tahansa pisteestä (valmis)

Klikkaus polun ulkopuolella kertoi ennen vain kellonajan. Nyt jokainen piste
vastaa: näkyykö pimennys, kuinka suuri peitto on (pinta-alana ja magnitudina)
ja milloin se alkaa, on suurimmillaan ja loppuu — samat kolme kelloa kuin
ennenkin. Jos aurinko laskee kesken pimennyksen, se sanotaan; jos pimennys ei
näy lainkaan, sekin sanotaan.

Datatiedostoihin tuli `local`-lohko: aurinko ja kuu maakiinteässä kehyksessä
minuutin välein koko osittaisen vaiheen yli (~30 kB per pimennys). Selain
laskee niistä saman geometrian kuin `eclipse_core` — erotus kahta kulmasädettä
vasten, aurinko horisontin yläpuolella — joten mikään ei ole esilaskettua
ruudukkoa. Helsinki 2026-08-12: magnitudi 0,833 klo 17:52:42 UTC, aurinko 2,4°
korkeudella, ja se laskee ennen pimennyksen loppua. v12.

### TASK 13 — radan päiden mahdottomat pisteet (valmis)

2033-03-30 piirtyi kartalle kiilana, joka työntyi Jäämereltä Mongoliaan asti.
Vika ei ollut päivämääräraja, vaikka siltä näytti: datassa ei ole yhtäkään yli
180 asteen pituusloikkaa, sillä `near_branch` purkaa pituudet jatkuviksi jo
generoitaessa. Vika oli `cross`-funktiossa.

`cross` etsii kohdan, jossa kestoprofiili leikkaa halutun tason, ja
ekstrapoloi reunan kahdesta viimeisestä sisäpuolisesta näytteestä, koska kesto
käyttäytyy reunalla neliöjuuren tavoin. Radan päissä umbra on enää viiste
terminaattoria pitkin, profiili litistyy, kulmakerroin menee lähelle nollaa ja
ekstrapolaatio karkaa. Se palautti 5446 km ikkunasta, jota oli näytteistetty
vain 1200 km:iin — eli rajapisteen tuhansien kilometrien päähän radalta,
leveyspiirille 37 astetta radalla, joka kulkee 58–86°N.

Leikkauskohta on rakenteeltaan kahden näytteen välissä: `dur[i]` on tason
yläpuolella ja `dur[j]` sen alapuolella. Tulos rajataan nyt tähän väliin.
Lisäksi profiilin kävely alkaa siitä umbrasta, joka on tämän ruudun alla
(paikallinen maksimi nollasiirtymästä lähtien) eikä koko näytteistetyn viivan
korkeimmasta kohdasta, ja poikkisuuntainen näytteistys on katkaistu 1200
kilometriin — havaitut puolileveydet ovat 30–600 km, ja rajaamaton ikkuna
harvensi näytevälin 83 kilometriin puolen asteen levyisellä radalla.

Sama vika oli kolmessa pimennyksessä 59:stä: 2033-03-30, 2003-11-23 ja
2021-12-04. Kaikki kolme on generoitu uudelleen ja kaikkien leveyspiirit ovat
nyt radan omissa rajoissa (2033: 58,1–86,2°N). Regressio: 2026-08-12 ja
2027-08-02 generoitiin myös uudelleen — keskilinja ja umbran kehät pisteelleen
samat, rajaviivoista muuttui 3/94 ja 18/205 pistettä radan äärimmäisissä
päissä enintään 22 km, mikä on juuri se korjaus jota haettiin. check.py 94/94.

`gen_data.py` tarkistaa nyt valmiin geometrian ennen kirjoittamista
(`validate_geometry`): peräkkäisten pisteiden leveysero saa olla enintään 12
astetta ja etäisyys 4000 km. Leveyspiiri on mittari siksi, että se on
fysikaalisesti rajattu — 56 puhtaassa datatiedostossa suurin askel on 9,1
astetta, kolmessa rikkinäisessä 15,2, 45,5 ja 106,6. Pituuspiirille ei voi
asettaa vastaavaa rajaa, koska napojen lähellä rata pyyhkäisee kymmeniä
asteita ruutua kohti. Tarkistus kaataa generoinnin sen sijaan että päästäisi
tällaisen datan sivulle, ja kaikki 59 tiedostoa läpäisevät sen. `check.py`
ottaa uuden kuvan `alaska-2033`. v13.

**2050-05-20 ei korjaantunut, eikä tämä muutos koske sitä.** Sen rata on yhä
9 ruutua ja 8 sekuntia: `axis_scan` pitää vain `total`-pisteet, joten
hybridipimennyksen rengasmaiset osuudet jäävät kokonaan pois ja jäljelle jää
se hetki, jona umbra oikeasti koskettaa maata. Lyhyt punainen totaliteetti
keltaisin rengasmaisin päin vaatii rengasmaisen radan tuen — oma työnsä.

### TASK 14 — napaseutujen geometria häivytetään (valmis)

Web-Mercator venyttää navoille päin rajatta, ja rata joka nousee korkealle
arktiselle leveydelle piirtyy ristiin meneviksi sahalaitaisiksi viivoiksi.
Ne luetaan piirtovirheeksi, vaikka data on oikein. Kukaan ei katso
täydellistä pimennystä 85. leveyspiiriltä, joten geometria häivytetään:
täysi peitto 72 asteeseen asti, kokonaan poissa 80 asteessa, ja sama
molemmilla pallonpuoliskoilla. Vain esitystapa — dataan ei koskettu.

Häivytys koskee kaikkia staattisia viivoja: keskilinjaa, pohjois- ja
etelärajaa, kestokäyriä ja niiden 1m/2m-nimilappuja sekä rajojen välistä
varjonauhaa. Kukin viiva pilkotaan jaksoihin, joilla on sama läpinäkyvyys,
ja jaksot jakavat rajapisteensä niin ettei saumoja synny. Segmentti
piirretään heikomman päänsä mukaan, joten mikään 80 asteen yläpuolelle
yltävä ei jää näkyviin. Läpinäkyvyys kvantisoidaan 24 portaaseen: kahdeksan
porrasta näkyi Etelämantereen jäällä harmaina suorakaiteina.

Varjonauha rakennetaan nyt kaistaleena, jossa pohjois- ja etelärajaa
kuljetaan suhteellisen sijainnin mukaan eikä indeksi indeksiltä. Rajat
näytteistetään toisistaan riippumatta eivätkä ole välttämättä yhtä pitkiä
(2033: 51 ja 49 pistettä), joten vanha `north.concat(south.reverse())`
pariutti eri kohdat keskenään.

Umbra jätettiin häivyttämättä. Se on animaatio, se kertoo missä varjo juuri
nyt on, ja se on yksi umpinainen kuvio — venytettynäkin siisti, ei
sahalaitainen. Rata häviää sen alta, varjo kulkee loppuun.

**2026-08-12 muuttuu, toisin kuin tiketissä oletettiin.** Sen rata yltää
89,1 asteeseen: 217 pistettä 618:sta on häivytysalueella ja 112 katoaa
kokonaan. Kartan yläreunaan asti suihkunnut viivaviuhka on poissa ja
jäljelle jää puhdas nauha Grönlannista Islannin kautta Espanjaan — juuri se
mitä tiketti haki, mutta oletuspimennys näyttää nyt erilaiselta.
2027-08-02 ei muutu: sen suurin leveys on 36,8 astetta, joten jokainen
häivytyskerroin on tasan 1. check.py 94/94. v14.

## Tiedostot

```
eclipse_core.py        jaettu fysiikka (umbrakriteeri, SkyTable, varjon akseli)
find_eclipses.py       pimennysten haku efemeridistä 1986–2066
gen_data.py            datageneraattori (numpy + skyfield)
check.py               hyväksymistestit selaimessa (playwright)
check_oracle.py        vertailu NASA/GSFC:n julkaistuun ennusteeseen
data/index.json        luettelo: 59 pimennystä
data/eclipses/*.js     yksi tiedosto per pimennys (10,5 MB yhteensä)
data/eclipse2027.json  oletuspimennys suunnitelman muodossa
web/index.html         sivu
web/app.js             kartta, animaatio, kontrollit
web/style.css          tumma ulkoasu
web/eclipse2027.js     oletusdata window.ECLIPSE_DATA:na (file://-tuki)
web/eclipse-index.js   luettelo window.ECLIPSE_INDEX:nä
shots/                 kuvakaappaukset testiajosta
de440s.bsp             skyfieldin lataama efemeridi (ei versionhallintaan)
```
