/* Local wall-clock time for a point on Earth, with no backend and no network.
 *
 * Two halves:
 *
 *   1. coordinates -> IANA zone name, from the box table below;
 *   2. IANA zone name + instant -> UTC offset, from Intl.DateTimeFormat.
 *
 * Only (2) has to be exact, and the browser's own tz database does it: asking
 * Intl to format the *eclipse's* instant in a named zone gives the offset that
 * will be in force on that date, summer time and all, which is the whole reason
 * zone names are carried around instead of offsets. Hardcoding "Spain is +2"
 * would be right for August and wrong for the same map in January, and would go
 * stale besides - Egypt brought summer time back in 2023 and Kazakhstan merged
 * its two zones in 2024.
 *
 * (1) is an approximation and is treated as one. The boxes are national, or
 * sub-national where a country spans several zones, latitude/longitude
 * rectangles; first match wins. They are right in the interior of a country and
 * can be wrong within a few tens of kilometres of a land border between two
 * zones - a rectangle cannot follow a river, so the boxes along the Rio Grande,
 * the Yalu and the Fergana valley are drawn to hug one bank and take the error
 * on the other. Where no box matches - ocean, Antarctica, a gap - there is no
 * zone name to be had, and the offset falls back to longitude/15, the nautical
 * convention, reported with a tilde (~UTC+2) so that an estimate is never
 * dressed up as a fact.
 */

(function () {
  'use strict';

  // [south, north, west, east, IANA zone].
  //
  // Order matters, and the ordering constraints that are not obvious are
  // commented. Enclaves and small countries come before the larger boxes that
  // would swallow them; where two neighbours share an offset the order is
  // cosmetic (it only decides which name a tooltip shows) and the boxes are
  // left loose. Where neighbours differ by an hour the boxes are cut to the
  // border, because there the order decides whether the clock is right.
  var BOXES = [
    // -- Atlantic islands, enclaves, microstates ---------------------------
    [63.2, 66.6, -24.6, -13.4, 'Atlantic/Reykjavik'],
    [61.3, 62.5, -7.8, -6.2, 'Atlantic/Faroe'],
    [36.8, 39.9, -31.4, -24.9, 'Atlantic/Azores'],
    [32.3, 33.3, -17.4, -16.2, 'Atlantic/Madeira'],
    [27.4, 29.6, -18.4, -13.2, 'Atlantic/Canary'],
    [14.7, 17.3, -25.4, -22.6, 'Atlantic/Cape_Verde'],
    [35.85, 35.96, -5.42, -5.25, 'Africa/Ceuta'],
    [35.24, 35.36, -3.05, -2.88, 'Africa/Ceuta'],        // Melilla
    [36.09, 36.18, -5.38, -5.31, 'Europe/Gibraltar'],
    [43.71, 43.78, 7.36, 7.47, 'Europe/Monaco'],
    [42.42, 42.66, 1.40, 1.79, 'Europe/Andorra'],
    [35.75, 36.10, 14.15, 14.60, 'Europe/Malta'],
    // -- western Europe ----------------------------------------------------
    [49.9, 50.6, -6.5, -4.5, 'Europe/London'],           // Cornwall
    [50.0, 58.8, -5.35, 1.9, 'Europe/London'],
    [51.3, 55.45, -10.7, -5.35, 'Europe/Dublin'],
    [55.4, 61.0, -8.8, 1.0, 'Europe/London'],
    [41.0, 42.2, -8.9, -6.2, 'Europe/Lisbon'],
    [36.9, 42.2, -9.6, -6.9, 'Europe/Lisbon'],
    // Two boxes for Spain: one that reaches east to Catalonia would otherwise
    // reach south to Algiers as well, an hour away.
    [35.9, 43.9, -9.4, -0.3, 'Europe/Madrid'],
    [37.8, 43.9, -0.3, 3.4, 'Europe/Madrid'],
    [38.5, 40.2, 1.1, 4.4, 'Europe/Madrid'],             // Balearics
    // North-west Africa here rather than further down: Spain must win over
    // Algeria along the Andalusian coast (+2 against +1), and Tunisia must win
    // over the Italian box, which reaches south past Tunis.
    [27.6, 35.95, -13.3, -1.7, 'Africa/Casablanca'],
    [21.35, 27.7, -17.2, -8.6, 'Africa/El_Aaiun'],
    [30.5, 37.1, -2.2, 9.0, 'Africa/Algiers'],
    [30.2, 37.6, 7.5, 11.6, 'Africa/Tunis'],
    [19.4, 33.2, 13.0, 25.2, 'Africa/Tripoli'],
    [23.0, 33.2, 9.3, 13.0, 'Africa/Tripoli'],           // clear of Niger
    [41.3, 43.1, 8.4, 9.7, 'Europe/Paris'],              // Corsica
    [41.2, 51.2, -5.3, 8.4, 'Europe/Paris'],
    [49.4, 51.6, 2.5, 6.5, 'Europe/Brussels'],
    [50.7, 53.7, 3.3, 7.3, 'Europe/Amsterdam'],
    [49.4, 50.2, 5.7, 6.6, 'Europe/Luxembourg'],
    [45.8, 47.9, 5.9, 10.6, 'Europe/Zurich'],
    [46.3, 49.1, 9.5, 17.2, 'Europe/Vienna'],
    [47.2, 55.1, 5.8, 15.1, 'Europe/Berlin'],
    [54.5, 57.8, 8.0, 15.3, 'Europe/Copenhagen'],
    // -- the Nordics. Finland keeps +3 where Sweden and Norway are on +2, and
    // the three share long land borders, so Finland is traced first (the Torne
    // valley, the Käsivarsi arm, the Utsjoki strip) and its neighbours fill in
    // around it. Kautokeino ends up on Finnish time; nothing else does.
    [59.7, 60.5, 19.3, 21.1, 'Europe/Mariehamn'],
    [59.7, 64.0, 21.0, 31.6, 'Europe/Helsinki'],
    [64.0, 68.55, 23.4, 31.6, 'Europe/Helsinki'],
    [68.55, 69.15, 20.4, 23.6, 'Europe/Helsinki'],       // Käsivarsi
    [68.55, 70.1, 25.6, 29.1, 'Europe/Helsinki'],        // Utsjoki, Inari
    [55.2, 60.5, 10.9, 19.5, 'Europe/Stockholm'],
    [60.5, 64.0, 11.0, 21.0, 'Europe/Stockholm'],
    [64.0, 69.1, 14.0, 24.2, 'Europe/Stockholm'],
    [69.0, 71.4, 17.0, 31.2, 'Europe/Oslo'],             // Finnmark
    [57.9, 63.0, 4.5, 13.0, 'Europe/Oslo'],
    [62.0, 66.5, 9.0, 17.5, 'Europe/Oslo'],
    [66.0, 71.3, 13.0, 31.2, 'Europe/Oslo'],
    // -- central and eastern Europe: +2 and +3 meet along the Polish border,
    // so Kaliningrad, Lithuania and Poland are all cut back to it.
    [54.3, 55.4, 19.6, 22.9, 'Europe/Kaliningrad'],
    [54.4, 56.5, 20.9, 26.9, 'Europe/Vilnius'],
    [53.9, 54.4, 23.5, 26.9, 'Europe/Vilnius'],
    [57.5, 59.8, 21.7, 28.3, 'Europe/Tallinn'],
    [55.6, 58.1, 20.9, 28.3, 'Europe/Riga'],
    [49.0, 52.0, 14.1, 23.7, 'Europe/Warsaw'],
    [52.0, 54.9, 14.1, 23.65, 'Europe/Warsaw'],
    [48.5, 51.1, 12.0, 18.9, 'Europe/Prague'],
    [47.7, 49.7, 16.8, 22.6, 'Europe/Bratislava'],
    [45.7, 48.6, 16.1, 22.9, 'Europe/Budapest'],
    [45.4, 46.9, 13.3, 16.6, 'Europe/Ljubljana'],
    [42.3, 46.6, 13.4, 19.5, 'Europe/Zagreb'],
    [42.5, 45.3, 15.7, 19.7, 'Europe/Sarajevo'],
    [41.8, 43.6, 18.4, 20.4, 'Europe/Podgorica'],
    [42.2, 46.2, 18.8, 23.1, 'Europe/Belgrade'],
    [39.6, 42.7, 19.2, 21.1, 'Europe/Tirane'],
    [40.8, 42.4, 20.4, 23.1, 'Europe/Skopje'],
    [36.6, 38.4, 12.3, 16.3, 'Europe/Rome'],             // Sicily
    [38.0, 42.1, 8.0, 18.6, 'Europe/Rome'],
    [42.0, 47.1, 6.6, 14.1, 'Europe/Rome'],
    // The east Aegean islands are Greek (+2) inside a Turkish coastline (+3),
    // so they are named one by one ahead of both national boxes.
    [35.85, 36.50, 27.70, 28.30, 'Europe/Athens'],       // Rhodes
    [36.70, 36.95, 26.85, 27.35, 'Europe/Athens'],       // Kos
    [37.60, 37.90, 26.50, 27.10, 'Europe/Athens'],       // Samos
    [38.10, 38.65, 25.80, 26.25, 'Europe/Athens'],       // Chios
    [38.85, 39.45, 25.80, 26.70, 'Europe/Athens'],       // Lesbos
    [34.70, 41.80, 19.30, 26.00, 'Europe/Athens'],
    [34.50, 35.80, 32.20, 34.70, 'Asia/Nicosia'],
    // The Turkish box runs to the Caucasus, so Georgia, Armenia and Azerbaijan
    // (+4 against Turkey's +3) are named before it.
    [41.0, 43.6, 40.0, 46.8, 'Asia/Tbilisi'],
    [38.8, 41.3, 43.4, 46.7, 'Asia/Yerevan'],
    [38.3, 41.9, 44.7, 50.4, 'Asia/Baku'],
    [35.80, 42.20, 25.60, 44.90, 'Europe/Istanbul'],
    [41.20, 44.30, 22.30, 28.70, 'Europe/Sofia'],
    [45.40, 48.50, 26.60, 30.20, 'Europe/Chisinau'],
    [43.60, 48.30, 20.20, 29.80, 'Europe/Bucharest'],
    [44.30, 52.40, 22.10, 40.30, 'Europe/Kyiv'],
    [51.20, 56.20, 23.10, 32.80, 'Europe/Minsk'],
    // -- Central Asia and Russia -------------------------------------------
    // Kyrgyzstan is +6 among neighbours on +5, so its box is pulled back from
    // Tashkent and from the Tajik half of the Fergana valley.
    [40.6, 43.05, 69.8, 80.3, 'Asia/Bishkek'],
    [39.1, 40.6, 71.5, 80.3, 'Asia/Bishkek'],
    [36.6, 41.1, 67.3, 75.2, 'Asia/Dushanbe'],
    [37.1, 45.7, 55.9, 73.2, 'Asia/Tashkent'],
    [37.6, 42.8, 52.4, 66.7, 'Asia/Ashgabat'],
    [35.1, 37.6, 60.0, 66.7, 'Asia/Ashgabat'],           // clear of Mashhad
    // Kazakhstan has been one zone on +5 since 2024. Five boxes, because its
    // northern border steps up and down against Russian +4, +5, +6 and +7.
    [40.5, 55.45, 66.5, 70.8, 'Asia/Almaty'],
    [40.5, 51.3, 47.5, 58.0, 'Asia/Almaty'],
    [40.5, 53.5, 58.0, 66.5, 'Asia/Almaty'],
    [40.5, 54.2, 70.8, 76.0, 'Asia/Almaty'],
    [40.5, 53.5, 76.0, 87.4, 'Asia/Almaty'],
    // The Volga and Urals regions are a staircase of +3, +4 and +5, so the ones
    // that are not on Moscow time are named before the two big boxes.
    [45.0, 48.6, 44.9, 49.2, 'Europe/Astrakhan'],
    [50.0, 52.9, 45.0, 50.5, 'Europe/Saratov'],
    [51.7, 54.8, 47.9, 52.6, 'Europe/Samara'],
    [55.9, 58.5, 51.0, 54.5, 'Europe/Izhevsk'],
    [61.5, 68.5, 45.0, 66.0, 'Europe/Moscow'],           // Komi
    [59.0, 61.5, 45.0, 54.0, 'Europe/Moscow'],
    [43.0, 55.0, 27.3, 45.0, 'Europe/Moscow'],
    [55.0, 82.0, 27.3, 50.0, 'Europe/Moscow'],
    [48.0, 82.0, 50.0, 68.0, 'Asia/Yekaterinburg'],
    [50.0, 76.0, 68.0, 76.0, 'Asia/Omsk'],
    [50.0, 78.0, 76.0, 86.0, 'Asia/Novosibirsk'],
    [49.0, 79.0, 86.0, 100.0, 'Asia/Krasnoyarsk'],
    [50.0, 78.0, 100.0, 114.0, 'Asia/Irkutsk'],
    [45.8, 54.5, 141.5, 145.5, 'Asia/Sakhalin'],         // before Vladivostok
    [43.5, 51.0, 145.5, 156.5, 'Asia/Sakhalin'],         // the Kurils
    [42.0, 60.0, 130.0, 140.6, 'Asia/Vladivostok'],      // clear of Hokkaido
    [50.0, 55.5, 140.6, 141.6, 'Asia/Vladivostok'],      // the lower Amur
    [53.0, 76.0, 114.0, 140.0, 'Asia/Yakutsk'],
    [55.0, 66.0, 140.0, 160.0, 'Asia/Magadan'],
    [50.0, 63.0, 155.0, 180.0, 'Asia/Kamchatka'],
    [62.0, 71.0, 170.0, 180.0, 'Asia/Anadyr'],
    [64.0, 68.0, -180.0, -169.0, 'Asia/Anadyr'],
    // -- the Middle East ---------------------------------------------------
    // Afghanistan is on the half hour, so its two boxes follow the Durand line
    // closely enough to keep Peshawar and Quetta on Pakistani time.
    [31.0, 38.5, 60.9, 71.2, 'Asia/Kabul'],
    [29.3, 31.5, 61.7, 66.4, 'Asia/Kabul'],
    // Iran is on the half hour and its box spans the whole Gulf, so every state
    // around that coast is named ahead of it.
    [29.0, 37.4, 38.7, 48.6, 'Asia/Baghdad'],
    [28.5, 30.1, 46.5, 48.5, 'Asia/Kuwait'],
    [25.7, 26.4, 50.3, 50.8, 'Asia/Bahrain'],
    [24.4, 26.2, 50.7, 51.7, 'Asia/Qatar'],
    [22.6, 26.1, 51.5, 56.4, 'Asia/Dubai'],
    [16.6, 26.4, 51.9, 59.9, 'Asia/Muscat'],
    [12.1, 19.0, 42.5, 53.2, 'Asia/Aden'],
    [31.20, 31.60, 34.20, 34.60, 'Asia/Gaza'],
    [31.70, 31.90, 35.10, 35.32, 'Asia/Jerusalem'],
    [31.35, 32.55, 34.95, 35.57, 'Asia/Hebron'],
    [29.40, 33.40, 34.20, 35.90, 'Asia/Jerusalem'],
    [33.0, 34.7, 35.0, 36.7, 'Asia/Beirut'],
    [32.2, 37.4, 35.6, 42.4, 'Asia/Damascus'],
    [29.1, 33.4, 34.9, 39.4, 'Asia/Amman'],
    [26.0, 29.4, 34.5, 38.5, 'Asia/Riyadh'],             // Tabuk, Hejaz north
    [16.3, 32.2, 38.5, 50.3, 'Asia/Riyadh'],             // clear of Sudan
    [17.5, 26.5, 50.3, 55.7, 'Asia/Riyadh'],             // clear of the Gulf
    [25.0, 39.8, 44.0, 63.4, 'Asia/Tehran'],
    // -- South Asia: India needs six boxes, because Pakistan (+5), Nepal
    // (+5:45), Bangladesh (+6) and Tibet (+8) all crowd around it.
    [26.3, 30.5, 80.0, 88.3, 'Asia/Kathmandu'],
    [26.7, 28.4, 88.7, 92.2, 'Asia/Thimphu'],
    [20.5, 26.7, 88.7, 89.9, 'Asia/Dhaka'],
    [20.5, 25.3, 89.9, 92.7, 'Asia/Dhaka'],              // clear of Assam
    [5.8, 10.0, 79.5, 82.0, 'Asia/Colombo'],
    [-0.7, 7.2, 72.5, 74.0, 'Indian/Maldives'],
    [23.6, 32.0, 60.8, 72.0, 'Asia/Karachi'],
    [28.0, 37.1, 66.0, 74.6, 'Asia/Karachi'],
    [6.7, 35.7, 68.1, 80.0, 'Asia/Kolkata'],
    [6.7, 31.0, 80.0, 84.0, 'Asia/Kolkata'],
    [8.0, 21.5, 84.0, 88.0, 'Asia/Kolkata'],
    [21.5, 28.2, 84.0, 89.0, 'Asia/Kolkata'],
    [21.0, 28.4, 89.0, 92.5, 'Asia/Kolkata'],
    [24.0, 29.6, 92.5, 97.5, 'Asia/Kolkata'],
    // -- East and South-East Asia ------------------------------------------
    [9.5, 20.0, 92.1, 98.6, 'Asia/Yangon'],
    [19.0, 28.6, 92.1, 101.2, 'Asia/Yangon'],
    [5.5, 20.5, 97.3, 105.7, 'Asia/Bangkok'],
    [13.9, 22.6, 100.0, 107.7, 'Asia/Vientiane'],
    [10.3, 14.7, 102.3, 107.7, 'Asia/Phnom_Penh'],
    [8.1, 23.4, 102.1, 109.6, 'Asia/Ho_Chi_Minh'],
    [45.0, 52.0, 87.7, 96.0, 'Asia/Hovd'],
    [41.5, 52.2, 87.7, 120.0, 'Asia/Ulaanbaatar'],
    [34.3, 49.2, 73.4, 96.4, 'Asia/Urumqi'],             // Xinjiang, +6
    [22.1, 22.6, 113.8, 114.5, 'Asia/Hong_Kong'],
    [22.1, 22.3, 113.5, 113.65, 'Asia/Macau'],
    [21.9, 25.4, 119.3, 122.1, 'Asia/Taipei'],
    // Korea and Japan before China: the Chinese box is one zone from Kashgar to
    // the Yellow Sea and would otherwise reach across both.
    [37.6, 41.0, 124.7, 130.8, 'Asia/Pyongyang'],
    [33.0, 38.7, 124.5, 131.0, 'Asia/Seoul'],
    [24.0, 29.0, 122.9, 131.5, 'Asia/Tokyo'],            // Ryukyu
    [29.0, 36.0, 129.2, 141.0, 'Asia/Tokyo'],            // Kyushu, west Honshu
    [33.0, 41.7, 134.0, 142.5, 'Asia/Tokyo'],            // east Honshu
    [41.3, 45.7, 139.3, 146.0, 'Asia/Tokyo'],            // Hokkaido
    [18.1, 53.6, 73.5, 135.1, 'Asia/Shanghai'],
    [4.6, 21.2, 116.9, 126.6, 'Asia/Manila'],
    [1.2, 1.5, 103.6, 104.1, 'Asia/Singapore'],
    [4.0, 5.1, 114.0, 115.4, 'Asia/Brunei'],
    // Sumatra is +7 and peninsular Malaysia +8; the strait is the border.
    [4.0, 6.0, 95.0, 99.0, 'Asia/Jakarta'],              // Aceh
    [0.8, 4.5, 95.0, 100.8, 'Asia/Jakarta'],             // Sumatra's east coast
    [0.5, 1.5, 103.5, 105.0, 'Asia/Jakarta'],            // Riau islands
    [0.8, 7.4, 99.6, 119.3, 'Asia/Kuala_Lumpur'],
    [2.8, 8.1, 131.1, 134.7, 'Pacific/Palau'],
    [-9.5, -8.1, 124.0, 127.4, 'Asia/Dili'],
    [-10.6, -10.35, 105.5, 105.8, 'Indian/Christmas'],   // before Indonesia
    [-12.3, -11.8, 96.75, 97.0, 'Indian/Cocos'],
    [-11.1, 6.1, 95.0, 111.5, 'Asia/Jakarta'],
    [-11.1, 4.5, 111.5, 125.0, 'Asia/Makassar'],
    [-9.2, 2.6, 125.0, 141.1, 'Asia/Jayapura'],
    // -- Africa: the +0 / +1 / +2 / +3 seams decide which boxes must be tight
    [21.9, 31.7, 24.6, 36.9, 'Africa/Cairo'],
    [12.3, 18.1, 36.4, 43.2, 'Africa/Asmara'],
    [10.9, 12.8, 41.7, 43.5, 'Africa/Djibouti'],
    [8.6, 22.3, 22.0, 35.5, 'Africa/Khartoum'],
    [13.0, 22.3, 35.5, 38.6, 'Africa/Khartoum'],         // the Red Sea coast
    [-1.7, 12.0, 40.9, 51.5, 'Africa/Mogadishu'],
    [-4.7, 5.1, 33.9, 41.9, 'Africa/Nairobi'],
    [-1.5, 4.3, 29.5, 35.1, 'Africa/Kampala'],
    [-2.9, -1.0, 28.8, 30.9, 'Africa/Kigali'],
    [-4.5, -2.3, 28.9, 30.9, 'Africa/Bujumbura'],
    [-11.8, -0.9, 29.3, 40.5, 'Africa/Dar_es_Salaam'],
    [3.4, 7.0, 27.5, 35.3, 'Africa/Juba'],
    [7.0, 12.3, 24.1, 34.0, 'Africa/Juba'],
    [3.4, 15.0, 32.9, 48.0, 'Africa/Addis_Ababa'],
    [-17.2, -9.3, 32.6, 36.0, 'Africa/Blantyre'],
    [-18.1, -8.2, 22.0, 33.7, 'Africa/Lusaka'],
    [-22.5, -15.6, 25.2, 33.1, 'Africa/Harare'],
    [-27.0, -10.4, 30.2, 41.0, 'Africa/Maputo'],
    [-30.7, -28.5, 27.0, 29.5, 'Africa/Maseru'],
    [-27.4, -25.7, 30.7, 32.2, 'Africa/Mbabane'],
    [-26.9, -24.6, 20.0, 26.0, 'Africa/Gaborone'],
    [-24.6, -17.8, 20.0, 29.4, 'Africa/Gaborone'],
    [-35.0, -22.1, 16.4, 33.0, 'Africa/Johannesburg'],
    [-18.1, -17.4, 20.0, 25.3, 'Africa/Windhoek'],       // the Caprivi strip
    [-29.0, -17.4, 11.6, 25.3, 'Africa/Windhoek'],
    [-17.4, -4.3, 11.6, 22.0, 'Africa/Luanda'],
    [-13.0, -10.5, 22.0, 24.1, 'Africa/Luanda'],         // the Cazombo salient
    [2.2, 11.1, 14.4, 27.5, 'Africa/Bangui'],
    [-13.5, 5.4, 25.0, 31.4, 'Africa/Lubumbashi'],       // eastern DR Congo, +2
    [-6.0, 5.4, 12.1, 25.0, 'Africa/Kinshasa'],
    [-5.1, 3.8, 11.0, 18.7, 'Africa/Brazzaville'],
    [-4.0, 2.4, 8.6, 14.6, 'Africa/Libreville'],
    [0.8, 3.8, 8.4, 11.4, 'Africa/Malabo'],
    [-0.1, 1.8, 6.4, 7.5, 'Africa/Sao_Tome'],
    [1.6, 13.1, 8.4, 16.3, 'Africa/Douala'],
    [7.4, 23.5, 13.4, 22.0, 'Africa/Ndjamena'],
    [15.0, 23.5, 13.4, 24.0, 'Africa/Ndjamena'],
    [11.6, 23.6, 0.6, 16.0, 'Africa/Niamey'],
    [4.2, 13.9, 2.8, 14.7, 'Africa/Lagos'],
    [6.1, 12.5, 1.6, 2.8, 'Africa/Porto-Novo'],
    [9.0, 12.5, 0.7, 3.9, 'Africa/Porto-Novo'],
    [6.0, 11.2, 0.0, 1.6, 'Africa/Lome'],
    [4.7, 11.2, -3.3, 1.3, 'Africa/Accra'],
    [9.4, 15.1, -5.6, 2.4, 'Africa/Ouagadougou'],
    [4.3, 10.8, -8.7, -2.4, 'Africa/Abidjan'],
    [10.1, 25.1, -12.3, 4.3, 'Africa/Bamako'],           // +0, so before Algeria
    [18.9, 31.0, -8.7, 12.0, 'Africa/Algiers'],          // the Algerian Sahara
    [13.0, 13.9, -16.9, -13.7, 'Africa/Banjul'],
    [10.9, 12.7, -16.8, -13.6, 'Africa/Bissau'],
    [12.3, 16.7, -17.6, -11.3, 'Africa/Dakar'],
    [14.7, 27.3, -17.1, -4.8, 'Africa/Nouakchott'],
    [7.1, 12.7, -15.1, -7.6, 'Africa/Conakry'],
    [6.9, 10.0, -13.4, -10.2, 'Africa/Freetown'],
    [4.3, 8.6, -11.5, -7.3, 'Africa/Monrovia'],
    [-25.7, -11.9, 43.1, 50.6, 'Indian/Antananarivo'],
    [-12.5, -11.3, 43.2, 44.6, 'Indian/Comoro'],
    [-13.1, -12.6, 44.9, 45.3, 'Indian/Mayotte'],
    [-20.6, -19.9, 57.2, 57.9, 'Indian/Mauritius'],
    [-21.4, -20.8, 55.2, 55.9, 'Indian/Reunion'],
    [-4.9, -3.7, 55.2, 56.0, 'Indian/Mahe'],
    [-16.1, -15.8, -5.9, -5.6, 'Atlantic/St_Helena'],
    // -- northern North America --------------------------------------------
    [75.5, 78.5, -71.0, -64.0, 'America/Thule'],
    [72.0, 81.5, -25.0, -11.3, 'America/Danmarkshavn'],
    [61.5, 74.5, -96.0, -61.5, 'America/Iqaluit'],
    [51.0, 60.5, -67.0, -55.5, 'America/Goose_Bay'],     // Labrador, before Greenland
    [59.7, 84.0, -62.0, -11.3, 'America/Nuuk'],
    [46.6, 55.5, -59.5, -52.5, 'America/St_Johns'],
    [43.3, 48.1, -67.5, -59.5, 'America/Halifax'],
    [32.2, 32.45, -64.95, -64.6, 'Atlantic/Bermuda'],
    [45.0, 62.0, -79.5, -57.1, 'America/Toronto'],       // Quebec
    [43.0, 50.0, -83.5, -74.3, 'America/Toronto'],       // southern Ontario
    [48.3, 58.0, -90.5, -79.5, 'America/Toronto'],
    [48.9, 60.1, -102.1, -95.2, 'America/Winnipeg'],
    [48.9, 60.1, -110.1, -101.3, 'America/Regina'],      // no summer time
    [48.9, 70.0, -120.1, -102.0, 'America/Edmonton'],
    [60.0, 69.7, -141.1, -123.8, 'America/Whitehorse'],
    [48.2, 60.1, -133.2, -118.0, 'America/Vancouver'],
    [54.5, 71.5, -169.9, -130.0, 'America/Anchorage'],
    [51.2, 53.0, -179.9, -169.9, 'America/Adak'],
    [18.8, 22.4, -160.4, -154.7, 'Pacific/Honolulu'],
    // The Rio Grande is a diagonal and these are rectangles, so each border box
    // hugs the Mexican bank: Nuevo Laredo lands on Mexican time and Laredo,
    // three kilometres away, does not.
    [25.5, 26.12, -99.2, -97.1, 'America/Mexico_City'],
    [26.1, 27.75, -100.5, -99.50, 'America/Mexico_City'],
    [27.7, 29.0, -101.4, -100.51, 'America/Mexico_City'],
    [29.0, 29.45, -101.6, -100.92, 'America/Mexico_City'],
    [29.2, 29.75, -105.0, -104.40, 'America/Mexico_City'],
    [31.3, 31.755, -106.6, -106.2, 'America/Ciudad_Juarez'],
    [30.5, 32.535, -117.2, -114.6, 'America/Tijuana'],
    [26.0, 31.33, -115.1, -108.5, 'America/Hermosillo'], // no summer time
    [21.0, 27.1, -112.0, -105.5, 'America/Mazatlan'],    // clear of Chihuahua
    [31.33, 37.0, -114.9, -109.0, 'America/Phoenix'],    // no summer time
    [24.4, 32.0, -85.6, -79.9, 'America/New_York'],      // Florida, Georgia
    [30.0, 47.5, -85.0, -66.9, 'America/New_York'],
    [25.8, 49.4, -104.1, -85.0, 'America/Chicago'],
    [31.33, 49.1, -114.1, -104.0, 'America/Denver'],
    // Pacific time stops at the Idaho and Montana lines, not at a meridian:
    // Boise and Kalispell are Mountain, the Idaho panhandle is not.
    [32.53, 42.0, -124.6, -114.1, 'America/Los_Angeles'],
    [42.0, 49.1, -124.6, -116.9, 'America/Los_Angeles'],
    [45.5, 49.1, -117.3, -115.0, 'America/Los_Angeles'],
    // -- Middle America and the Caribbean ----------------------------------
    [17.8, 21.7, -89.3, -86.7, 'America/Cancun'],
    [15.8, 18.5, -89.3, -87.4, 'America/Belize'],
    [13.6, 17.9, -92.3, -88.2, 'America/Guatemala'],
    [13.1, 14.5, -90.2, -87.6, 'America/El_Salvador'],
    [12.9, 16.6, -89.4, -83.1, 'America/Tegucigalpa'],
    [10.7, 15.1, -87.7, -82.6, 'America/Managua'],
    [8.0, 11.3, -85.9, -82.5, 'America/Costa_Rica'],
    [7.1, 9.7, -83.1, -77.1, 'America/Panama'],
    [14.5, 32.8, -105.7, -86.7, 'America/Mexico_City'],
    [19.8, 23.3, -85.0, -74.1, 'America/Havana'],
    [20.9, 27.3, -79.1, -72.7, 'America/Nassau'],
    [17.7, 18.6, -78.4, -76.2, 'America/Jamaica'],
    [17.9, 20.1, -74.5, -71.6, 'America/Port-au-Prince'],
    [17.5, 19.95, -72.1, -68.3, 'America/Santo_Domingo'],
    [12.0, 18.6, -67.3, -59.4, 'America/Puerto_Rico'],   // and the Lesser Antilles
    // -- South America -----------------------------------------------------
    [7.5, 12.3, -73.4, -59.8, 'America/Caracas'],
    [0.6, 7.5, -67.3, -59.8, 'America/Caracas'],
    [-4.3, 13.5, -79.1, -66.8, 'America/Bogota'],
    [1.2, 8.6, -61.4, -56.5, 'America/Guyana'],
    [1.8, 6.0, -58.1, -53.9, 'America/Paramaribo'],
    [2.1, 5.8, -54.6, -51.6, 'America/Cayenne'],
    [-1.5, 0.8, -92.1, -89.2, 'Pacific/Galapagos'],
    [-5.1, 1.5, -81.1, -75.2, 'America/Guayaquil'],
    [-11.2, -7.1, -74.0, -66.6, 'America/Rio_Branco'],   // Acre, -5
    [-18.4, 0.0, -81.4, -68.6, 'America/Lima'],
    [-23.0, -9.6, -69.7, -57.4, 'America/La_Paz'],
    [-25.0, -17.5, -70.5, -66.9, 'America/Santiago'],
    [-56.0, -25.0, -75.7, -70.0, 'America/Santiago'],
    [-27.7, -19.2, -62.7, -54.2, 'America/Asuncion'],
    [-35.0, -30.1, -58.0, -53.1, 'America/Montevideo'],
    [-52.5, -51.0, -61.4, -57.7, 'Atlantic/Stanley'],    // before Argentina
    [-55.0, -53.9, -38.1, -35.7, 'Atlantic/South_Georgia'],
    [-55.2, -21.7, -73.6, -53.6, 'America/Argentina/Buenos_Aires'],
    [-14.0, 5.3, -73.0, -56.5, 'America/Manaus'],        // Amazonas, -4
    [-18.1, -7.3, -61.6, -50.2, 'America/Cuiaba'],       // Mato Grosso, -4
    [-4.0, 5.3, -56.5, -45.0, 'America/Belem'],
    [-33.8, -2.8, -58.0, -34.7, 'America/Sao_Paulo'],
    [-27.3, -27.0, -109.5, -109.2, 'Pacific/Easter'],
    // -- Oceania -----------------------------------------------------------
    [-35.2, -13.5, 112.9, 129.0, 'Australia/Perth'],
    [-26.0, -10.9, 129.0, 138.0, 'Australia/Darwin'],
    [-38.1, -26.0, 129.0, 141.0, 'Australia/Adelaide'],
    [-43.7, -39.5, 143.8, 148.5, 'Australia/Hobart'],
    [-39.2, -33.9, 140.9, 150.1, 'Australia/Melbourne'],
    [-37.6, -28.1, 141.0, 153.7, 'Australia/Sydney'],
    [-29.2, -9.9, 138.0, 153.7, 'Australia/Brisbane'],   // no summer time
    [-29.2, -28.9, 167.8, 168.1, 'Pacific/Norfolk'],
    [-47.4, -34.0, 166.4, 178.6, 'Pacific/Auckland'],
    [-44.3, -43.6, -176.9, -175.9, 'Pacific/Chatham'],
    [-11.7, -1.0, 140.8, 156.0, 'Pacific/Port_Moresby'],
    [-12.0, -5.0, 155.5, 167.0, 'Pacific/Guadalcanal'],
    [-22.9, -19.5, 163.5, 168.2, 'Pacific/Noumea'],
    [-20.3, -13.0, 166.5, 170.3, 'Pacific/Efate'],
    [-21.0, -12.4, 176.8, 180.0, 'Pacific/Fiji'],
    [-21.0, -12.4, -180.0, -178.2, 'Pacific/Fiji'],
    [-10.8, -5.6, 176.0, 179.9, 'Pacific/Funafuti'],
    [-22.4, -15.5, -176.3, -173.7, 'Pacific/Tongatapu'],
    [-14.4, -13.2, -178.3, -176.1, 'Pacific/Wallis'],
    [-14.1, -13.4, -172.9, -171.4, 'Pacific/Apia'],
    [-14.4, -14.1, -171.1, -169.4, 'Pacific/Pago_Pago'],
    [-19.2, -18.9, -170.0, -169.7, 'Pacific/Niue'],
    [-22.0, -8.9, -166.1, -157.1, 'Pacific/Rarotonga'],
    [1.6, 2.1, -157.6, -157.1, 'Pacific/Kiritimati'],
    [-4.7, -2.7, -172.0, -171.0, 'Pacific/Kanton'],
    [-2.7, 3.5, 172.0, 177.0, 'Pacific/Tarawa'],
    [-0.6, -0.4, 166.85, 167.05, 'Pacific/Nauru'],
    [4.5, 14.7, 160.7, 172.2, 'Pacific/Majuro'],
    [5.2, 7.5, 157.0, 163.5, 'Pacific/Pohnpei'],
    [5.2, 9.7, 149.0, 154.0, 'Pacific/Chuuk'],
    [13.2, 15.3, 144.6, 145.9, 'Pacific/Guam'],
    [-18.0, -14.0, -152.0, -148.0, 'Pacific/Tahiti'],
    [-10.6, -7.8, -140.9, -138.0, 'Pacific/Marquesas'],
    [-23.4, -22.9, -135.2, -134.6, 'Pacific/Gambier']
  ];

  // -- zone name -> offset, via the browser's own tz database ---------------

  var fmtCache = {};

  // null for a name this browser's tz database does not know, which is how an
  // unknown zone degrades to the longitude estimate instead of throwing.
  function formatter(zone) {
    if (!(zone in fmtCache)) {
      try {
        fmtCache[zone] = new Intl.DateTimeFormat('en-US', {
          timeZone: zone, hourCycle: 'h23',
          year: 'numeric', month: '2-digit', day: '2-digit',
          hour: '2-digit', minute: '2-digit', second: '2-digit'
        });
      } catch (err) {
        fmtCache[zone] = null;
      }
    }
    return fmtCache[zone];
  }

  // The offset is read rather than looked up: format the instant in the zone,
  // read the broken-down local fields back, and see how far they are from UTC.
  // Whatever the tz database says about summer time on that date is already
  // baked into the answer.
  function offsetSec(zone, ms) {
    var f = formatter(zone);
    if (!f) return null;
    var p = {};
    f.formatToParts(new Date(ms)).forEach(function (x) { p[x.type] = x.value; });
    if (!p.year) return null;
    var asUTC = Date.UTC(+p.year, +p.month - 1, +p.day,
                         +p.hour % 24, +p.minute, +p.second);
    return Math.round((asUTC - ms) / 1000);
  }

  // The zone's own abbreviation when it has one ("CEST"); empty when the tz
  // database only offers a numeric name, in which case the offset label the page
  // already shows says the same thing twice.
  function abbrev(zone, ms) {
    try {
      var parts = new Intl.DateTimeFormat('en-GB', {
        timeZone: zone, timeZoneName: 'short', hour: 'numeric'
      }).formatToParts(new Date(ms));
      for (var i = 0; i < parts.length; i++) {
        if (parts[i].type === 'timeZoneName') {
          return /^(GMT|UTC)/.test(parts[i].value) ? '' : parts[i].value;
        }
      }
    } catch (err) { /* fall through */ }
    return '';
  }

  // -- coordinates -> zone --------------------------------------------------

  function zoneAt(lat, lon) {
    lon = ((lon + 540) % 360) - 180;
    for (var i = 0; i < BOXES.length; i++) {
      var b = BOXES[i];
      if (lat >= b[0] && lat <= b[1] && lon >= b[2] && lon <= b[3]) return b[4];
    }
    return null;
  }

  // -- the public shape -----------------------------------------------------

  // A place is either a named zone - from a marker, or from the box table - or a
  // bare longitude, which yields the nautical estimate and nothing more.
  function at(lat, lon) {
    return { zone: zoneAt(lat, lon), lon: lon };
  }

  function named(zone, lon) {
    return { zone: zone || null, lon: lon === undefined ? 0 : lon };
  }

  function pad2(n) { return (n < 10 ? '0' : '') + n; }

  function label(sec, exact) {
    var a = Math.abs(sec);
    var m = Math.round(a % 3600 / 60);
    return (exact ? '' : '~') + 'UTC' + (sec < 0 ? '−' : '+') +
           Math.floor(a / 3600) + (m ? ':' + pad2(m) : '');
  }

  // Everything the page needs to print one instant at one place:
  //   offset      seconds east of UTC, DST-correct for this very instant
  //   exact       false when it came from longitude/15 rather than a zone
  //   label       "UTC+2" / "~UTC+2" / "UTC−3:30"
  //   localSec    seconds since local midnight, for the page's own hms()
  //   dayShift    local calendar date minus UTC calendar date, in days
  function stamp(place, ms) {
    ms = Math.round(ms / 1000) * 1000;
    var off = place && place.zone !== null ? offsetSec(place.zone, ms) : null;
    var exact = off !== null;
    var zone = exact ? place.zone : null;
    if (!exact) {
      var est = Math.round((place ? place.lon : 0) / 15);
      off = Math.max(-12, Math.min(14, est)) * 3600;
    }
    var localMs = ms + off * 1000;
    return {
      zone: zone, exact: exact, offset: off, label: label(off, exact),
      abbr: zone ? abbrev(zone, ms) : '',
      localSec: (Math.floor(localMs / 1000) % 86400 + 86400) % 86400,
      localMs: localMs,
      dayShift: Math.floor(localMs / 86400000) - Math.floor(ms / 86400000)
    };
  }

  window.TZ = { at: at, named: named, zoneAt: zoneAt, stamp: stamp,
                offsetSec: offsetSec, boxes: BOXES };
})();
